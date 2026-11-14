"""Scoring pipeline shared by the API (/score) and the stream worker."""
from __future__ import annotations

import time

import numpy as np
import redis

from app.config import Settings
from app.drift import DriftMonitor
from app.events import Transaction
from app.features import FeatureExtractor
from app.model import FraudModel


class Metrics:
    """Counters, gauges and latency samples live in Redis so API + worker share them."""

    def __init__(self, r: redis.Redis):
        self.r = r

    def record(self, counters: dict, lat_key: str | None = None, lat_values=()) -> None:
        pipe = self.r.pipeline(transaction=False)
        for k, v in counters.items():
            if v:
                pipe.hincrby("metrics:counters", k, int(v))
        if lat_key and len(lat_values):
            pipe.lpush(lat_key, *[round(float(x), 3) for x in lat_values])
            pipe.ltrim(lat_key, 0, 4999)
        pipe.execute()

    def snapshot(self, s: Settings) -> dict:
        out: dict = {
            "counters": {k: int(v) for k, v in self.r.hgetall("metrics:counters").items()},
            "throughput_eps": float(self.r.hget("metrics:gauges", "eps") or 0.0),
        }
        for name, key in (("api_latency_ms", "lat:api"), ("worker_latency_ms_per_event", "lat:worker")):
            vals = np.array(self.r.lrange(key, 0, -1), dtype=float)
            out[name] = ({"n": int(vals.size),
                          "p50": round(float(np.percentile(vals, 50)), 3),
                          "p95": round(float(np.percentile(vals, 95)), 3),
                          "p99": round(float(np.percentile(vals, 99)), 3)}
                         if vals.size else {"n": 0})
        stream = {"length": self.r.xlen(s.stream), "pending": 0, "lag": None,
                  "dlq_length": self.r.xlen(s.dlq_stream)}
        try:
            for g in self.r.xinfo_groups(s.stream):
                if g["name"] == s.group:
                    stream["pending"], stream["lag"] = g["pending"], g.get("lag")
        except redis.exceptions.ResponseError:
            pass
        out["stream"] = stream
        return out


class ScoringEngine:
    def __init__(self, r, model: FraudModel, extractor: FeatureExtractor,
                 drift: DriftMonitor, metrics: Metrics, settings: Settings):
        self.r, self.model, self.extractor = r, model, extractor
        self.drift, self.metrics, self.s = drift, metrics, settings

    def score_batch(self, txns: list[Transaction], source: str):
        """Returns (results, X, scores). latency_ms covers features+predict+SHAP, not DB writes."""
        t0 = time.perf_counter()
        X = self.extractor.extract_batch(txns)
        scores = self.model.predict(X)
        thr = self.model.threshold
        review = min(self.s.review_score, thr)

        results = []
        for tx, x, sc in zip(txns, X, scores):
            sc = float(sc)
            decision = "decline" if sc >= thr else ("review" if sc >= review else "approve")
            results.append({
                "txn_id": tx.txn_id, "card_id": tx.card_id, "ts_ms": tx.ts_ms, "amount": tx.amount,
                "score": round(sc, 6), "decision": decision, "threshold": round(thr, 4),
                "features": {n: float(v) for n, v in zip(self.model.meta["feature_names"], x)},
                "reasons": [], "contributions": [],
                "model_version": self.model.version, "source": source,
                "true_label": tx.label, "pattern": tx.pattern,
            })

        flagged = [i for i, r in enumerate(results) if r["decision"] != "approve"]
        if flagged:                                    # SHAP only where a human will look
            sv = self.model.shap_values(X[flagged])
            for j, i in enumerate(flagged):
                results[i].update(self.model.explain(X[i], sv[j]))

        lat = (time.perf_counter() - t0) * 1000
        for r in results:
            r["latency_ms"] = round(lat, 3)
        return results, X, scores

    def record_drift(self, X: np.ndarray, scores: np.ndarray) -> None:
        self.drift.record(X, scores)


def build_engine(s: Settings) -> ScoringEngine:
    r = redis.Redis.from_url(s.redis_url, decode_responses=True)
    r.ping()
    model = FraudModel(s.model_path, s.meta_path)
    drift = DriftMonitor(r, model.meta["psi_reference"], s.psi_window_min, s.psi_min_samples)
    return ScoringEngine(r, model, FeatureExtractor(r), drift, Metrics(r), s)