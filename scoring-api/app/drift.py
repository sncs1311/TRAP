"""Rolling-window Population Stability Index against the training reference."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import redis

from app.schema import FEATURE_NAMES

WARN, ALERT = 0.10, 0.25


def psi(expected: np.ndarray, actual: np.ndarray, eps: float = 1e-4) -> float:
    e, a = np.clip(expected, eps, None), np.clip(actual, eps, None)
    return float(np.sum((a - e) * np.log(a / e)))


def level(v: float) -> str:
    return "stable" if v < WARN else ("moderate" if v < ALERT else "significant")


class DriftMonitor:
    def __init__(self, r: redis.Redis, reference: dict, window_min: int, min_samples: int):
        self.r, self.window, self.min_samples = r, window_min, min_samples
        self.features = list(reference)
        self._exp: dict[str, np.ndarray] = {}
        self._vals: dict[str, np.ndarray] = {}
        self._edges: dict[str, np.ndarray] = {}
        for f, spec in reference.items():
            exp = np.array(spec["proportions"], dtype=float)
            if spec["type"] == "categorical":
                self._vals[f] = np.array(spec["values"], dtype=float)
                exp = np.append(exp, 0.0)               # extra bin: unseen category
            else:
                self._edges[f] = np.array(spec["edges"], dtype=float)
            self._exp[f] = exp

    def _bins(self, f: str, x: np.ndarray) -> np.ndarray:
        if f in self._vals:
            vals = self._vals[f]
            idx = np.searchsorted(vals, x)
            safe = np.minimum(idx, len(vals) - 1)
            return np.where(vals[safe] == x, safe, len(vals))
        return np.searchsorted(self._edges[f], x, side="right")   # same rule as training reference

    def record(self, X: np.ndarray, scores: np.ndarray) -> None:
        minute = int(time.time() // 60)
        ttl = (self.window + 5) * 60
        pipe = self.r.pipeline(transaction=False)
        for f in self.features:
            col = scores if f == "score" else X[:, FEATURE_NAMES.index(f)]
            counts = np.bincount(self._bins(f, col.astype(float)), minlength=len(self._exp[f]))
            key = f"psi:cur:{f}:{minute}"
            for b in np.nonzero(counts)[0]:
                pipe.hincrby(key, int(b), int(counts[b]))
            pipe.expire(key, ttl)
        pipe.execute()

    def compute(self) -> dict:
        now_min = int(time.time() // 60)
        pipe = self.r.pipeline(transaction=False)
        for f in self.features:
            for i in range(self.window):
                pipe.hgetall(f"psi:cur:{f}:{now_min - i}")
        raw = iter(pipe.execute())

        feats: dict[str, dict] = {}
        for f in self.features:
            counts = np.zeros(len(self._exp[f]))
            for _ in range(self.window):
                for b, c in next(raw).items():
                    counts[int(b)] += int(c)
            n = int(counts.sum())
            if n < self.min_samples:
                feats[f] = {"psi": None, "status": "insufficient_data", "n_samples": n}
            else:
                v = psi(self._exp[f], counts / n)
                feats[f] = {"psi": round(v, 4), "status": level(v), "n_samples": n}

        valid = {f: d for f, d in feats.items() if d["psi"] is not None}
        if valid:
            overall = max(d["psi"] for d in valid.values())
            status = level(overall)
            drivers = sorted(valid, key=lambda f: -valid[f]["psi"])[:3]
        else:
            overall, status, drivers = None, "insufficient_data", []
        return {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "window_minutes": self.window,
            "n_samples": max((d["n_samples"] for d in feats.values()), default=0),
            "overall_psi": overall, "status": status, "top_drivers": drivers,
            "thresholds": {"moderate": WARN, "significant": ALERT},
            "features": feats,
        }

    def reset(self) -> int:
        n = 0
        for k in self.r.scan_iter("psi:cur:*", count=500):
            n += self.r.delete(k)
        return n