"""Background producer: 100 ms ticks -> pipelined XADD to the Redis Stream."""
from __future__ import annotations

import heapq
import itertools
import json
import logging
import queue
import threading
import time
import uuid
from collections import deque

import numpy as np
import redis

from app.generator import card_id  # noqa: F401  (kept for symmetry / debugging)

log = logging.getLogger("producer")
TICK = 0.1
MAX_DUE_PER_TICK = 500
SESSION_P = 0.08                 # same as training: 8% of txns spawn 1-3 follow-ups
PROFILE_TTL_S = 2_592_000


class Producer(threading.Thread):
    def __init__(self, state, pool, factory, r: redis.Redis, cfg):
        super().__init__(daemon=True, name="producer")
        self.state, self.pool, self.factory, self.r, self.cfg = state, pool, factory, r, cfg
        self.heap: list = []                  # (due_epoch, seq, payload: dict event | int card idx)
        self.seq = itertools.count()
        self.acc = 0.0
        self._lag_t, self._throttle = 0.0, False
        self._win: deque = deque()
        self.stop_evt = threading.Event()

    def prewarm(self, now: float, horizon_s: float = 1200.0) -> int:
        """Start as if already running for `horizon_s`: pending follow-ups + their originals in Redis."""
        rng, pool = self.factory.rng, self.pool
        n_sessions = int(self.state.base_rps * horizon_s * SESSION_P)
        if n_sessions <= 0:
            return 0
        idx = pool.sample(n_sessions)
        t0 = now - rng.uniform(0, horizon_s, n_sessions)
        amt = np.clip(rng.lognormal(np.log(pool.avg_amt[idx].astype(np.float64)), 0.7), 0.5, 5000)

        pipe = self.r.pipeline(transaction=False)
        kept_cards: list[int] = []
        for k, (ci, t, a) in enumerate(zip(idx.tolist(), t0.tolist(), amt.tolist())):
            due = [t + float(d) for d in rng.uniform(30, 1200, int(rng.integers(1, 4)))]
            due = [d for d in due if d > now]            # only follow-ups still in the future
            if not due:
                continue
            for d in due:
                heapq.heappush(self.heap, (d, next(self.seq), ci))
            key = f"win:c{ci:07d}"
            pipe.zadd(key, {f"warm{int(now)}x{k}|{round(a, 2)!r}": int(t * 1000)})
            pipe.expire(key, 7200)
            kept_cards.append(ci)
        if kept_cards:
            self._seed(pipe, np.unique(np.asarray(kept_cards, dtype=np.int64)))
        pipe.execute()
        return len(kept_cards)
    
    # ---------- loop ----------
    def run(self) -> None:
        nxt = time.perf_counter()
        while not self.stop_evt.is_set():
            nxt += TICK
            try:
                self._tick(time.time())
            except Exception as e:            # e.g. Redis down: log, back off, keep running
                log.exception("tick failed")
                self.state.last_error = f"{type(e).__name__}: {e}"
                self.stop_evt.wait(1.0)
                nxt = time.perf_counter()
            delay = nxt - time.perf_counter()
            if delay > 0:
                self.stop_evt.wait(delay)
            else:
                nxt = time.perf_counter()     # fell behind: don't spiral

    def _tick(self, now: float) -> None:
        st = self.state
        while True:                           # pull newly planned attack events
            try:
                due, ev = st.attack_q.get_nowait()
            except queue.Empty:
                break
            heapq.heappush(self.heap, (due, next(self.seq), ev))
        self._update_eps(now)
        snap = st.snapshot(now)
        if not snap["running"]:
            return
        if self._throttled(now):
            st.throttled_ticks += 1
            return

        events, followers = [], []
        while self.heap and self.heap[0][0] <= now and len(events) + len(followers) < MAX_DUE_PER_TICK:
            _, _, payload = heapq.heappop(self.heap)
            (events if isinstance(payload, dict) else followers).append(payload)
        drift, replay = snap["drift"], snap["replay"]
        if followers:
            events += self.factory.legit(np.asarray(followers, dtype=np.int64), drift)

        self.acc += snap["rps"] * TICK
        k = int(self.acc)
        self.acc -= k
        if replay is not None:
            if k:
                events += replay.next_batch(k)
            if replay.done:
                st.end_replay()
        elif k:
            idx = self.pool.sample(k)
            events += self.factory.legit(idx, drift)
            rng = self.factory.rng
            for ci in idx[rng.random(k) < SESSION_P].tolist():
                for _ in range(int(rng.integers(1, 4))):
                    heapq.heappush(self.heap, (now + float(rng.uniform(30, 1200)),
                                               next(self.seq), int(ci)))
        if events:
            self._emit(events, now)

    # ---------- backpressure ----------
    def _backlog(self) -> int:
        try:
            for g in self.r.xinfo_groups(self.cfg.stream):
                if g["name"] == self.cfg.group:
                    return int(g.get("lag") or 0)
            return int(self.r.xlen(self.cfg.stream))     # group not created yet (worker never ran)
        except redis.exceptions.ResponseError:
            return 0                                      # stream doesn't exist yet

    def _throttled(self, now: float) -> bool:
        if now - self._lag_t >= 0.5:
            self._lag_t = now
            self.state.backlog = self._backlog()
            self._throttle = self.state.backlog > self.cfg.max_backlog
        return self._throttle

    def _update_eps(self, now: float) -> None:
        while self._win and now - self._win[0][0] > 5:
            self._win.popleft()
        self.state.actual_eps = sum(n for _, n in self._win) / 5.0

    # ---------- emit ----------
    def _seed(self, pipe, idx: np.ndarray) -> None:
        """Give never-seen cards a training-like purchase history (hist_mean for amount_ratio)."""
        pool, rng = self.pool, self.factory.rng
        new = idx[~pool.seeded[idx]]
        if new.size == 0:
            return
        pool.seeded[new] = True
        # prior txns ~ activity * (random point in the 20-day train window) * 1.16 (sessions)
        k = np.minimum(rng.poisson(pool.lam[new] * 1.16 * rng.uniform(0, 20, new.size)), 24)
        avg = pool.avg_amt[new].astype(np.float64)
        draws = np.clip(rng.lognormal(np.log(avg)[:, None], 0.7, (new.size, 24)), 0.5, 5000)
        sums = (draws * (np.arange(24)[None, :] < k[:, None])).sum(axis=1)
        for i, c, s in zip(new.tolist(), k.tolist(), sums.tolist()):
            if c == 0:
                continue                                  # no history: first txn has ratio 1.0, like training
            key = f"prof:c{i:07d}"
            pipe.hsetnx(key, "cnt", c)
            pipe.hsetnx(key, "sum", repr(s))
            pipe.expire(key, PROFILE_TTL_S)

    def _emit(self, events: list[dict], now: float) -> None:
        n, now_ms = len(events), int(now * 1000)
        pipe = self.r.pipeline(transaction=False)
        idx = [e["_idx"] for e in events if "_idx" in e]
        if idx:
            self._seed(pipe, np.unique(np.asarray(idx, dtype=np.int64)))
        step, counts = TICK * 1000 / n, {}
        for i, e in enumerate(events):
            e.pop("_idx", None)
            e["txn_id"] = uuid.uuid4().hex
            e["ts_ms"] = now_ms + int(i * step)           # spread inside the tick, monotonic
            pipe.xadd(self.cfg.stream, {"data": json.dumps(e, separators=(",", ":"))},
                      maxlen=self.cfg.stream_maxlen, approximate=True)
            counts[e["pattern"]] = counts.get(e["pattern"], 0) + 1
        pipe.execute()
        self.state.record(counts, n)
        self._win.append((now, n))