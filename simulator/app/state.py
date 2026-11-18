"""Shared, thread-safe chaos controls (API threads write, producer thread reads)."""
from __future__ import annotations

import queue
import threading

from app.generator import KNOBS, ZERO_DRIFT


class ChaosState:
    def __init__(self, base_rps: float, running: bool):
        self.lock = threading.RLock()
        self.default_rps = base_rps
        self.running = running
        self.base_rps = base_rps
        self.burst_rps, self.burst_until = 0.0, 0.0
        self.d_start, self.d_target = dict(ZERO_DRIFT), dict(ZERO_DRIFT)
        self.d_t0, self.d_ramp = 0.0, 0.0
        self.attack_q: queue.Queue = queue.Queue()
        self.replay, self.replay_file = None, None
        # stats
        self.emitted = 0
        self.by_pattern: dict[str, int] = {}
        self.throttled_ticks = 0
        self.attacks_launched = 0
        self.actual_eps = 0.0
        self.backlog = 0
        self.last_error: str | None = None

    # ---- drift ----
    def _progress(self, now: float) -> float:
        if self.d_ramp <= 0:
            return 1.0
        return min(1.0, max(0.0, (now - self.d_t0) / self.d_ramp))

    def drift_now(self, now: float) -> dict:
        with self.lock:
            f = self._progress(now)
            return {k: self.d_start[k] + (self.d_target[k] - self.d_start[k]) * f for k in KNOBS}

    def set_drift(self, target: dict, ramp: float, now: float) -> None:
        with self.lock:
            self.d_start = self.drift_now(now)           # ramp from wherever we are right now
            self.d_target = {k: float(target.get(k, 0.0)) for k in KNOBS}
            self.d_t0, self.d_ramp = now, float(ramp)

    # ---- traffic ----
    def start_burst(self, rps: float, duration: float, now: float) -> None:
        with self.lock:
            self.burst_rps, self.burst_until = rps, now + duration

    def start_replay(self, replay, name: str, rps: float | None) -> None:
        with self.lock:
            self.replay, self.replay_file = replay, name
            if rps:
                self.base_rps = rps

    def end_replay(self) -> None:
        with self.lock:
            self.replay, self.replay_file = None, None

    def reset(self) -> None:
        with self.lock:
            self.running, self.base_rps = True, self.default_rps
            self.burst_rps = self.burst_until = 0.0
            self.d_start, self.d_target = dict(ZERO_DRIFT), dict(ZERO_DRIFT)
            self.d_ramp = 0.0
            self.replay, self.replay_file = None, None

    # ---- producer-facing ----
    def snapshot(self, now: float) -> dict:
        with self.lock:
            return {"running": self.running,
                    "rps": self.burst_rps if now < self.burst_until else self.base_rps,
                    "drift": self.drift_now(now), "replay": self.replay}

    def record(self, counts: dict, n: int) -> None:
        with self.lock:
            self.emitted += n
            for k, v in counts.items():
                self.by_pattern[k] = self.by_pattern.get(k, 0) + v

    # ---- dashboard-facing ----
    def status(self, now: float, heap_size: int) -> dict:
        with self.lock:
            cur = self.drift_now(now)
            burst_left = max(0.0, self.burst_until - now)
            return {
                "running": self.running,
                "mode": "replay" if self.replay else "synthetic",
                "replay": ({"file": self.replay_file, "rows_sent": self.replay.count}
                           if self.replay else None),
                "rps_target": self.base_rps,
                "rps_effective": self.burst_rps if burst_left > 0 else self.base_rps,
                "burst": {"active": burst_left > 0, "rps": self.burst_rps,
                          "seconds_left": round(burst_left, 1)},
                "drift": {"current": {k: round(v, 3) for k, v in cur.items()},
                          "target": self.d_target, "ramp_seconds": self.d_ramp,
                          "progress": round(self._progress(now), 3),
                          "active": any(v > 0.001 for v in cur.values())
                                    or any(v > 0.001 for v in self.d_target.values())},
                "emitted": self.emitted, "by_pattern": dict(self.by_pattern),
                "actual_eps": round(self.actual_eps, 1), "backlog": self.backlog,
                "throttled_ticks": self.throttled_ticks,
                "attacks_launched": self.attacks_launched,
                "scheduled_pending": heap_size, "last_error": self.last_error,
            }