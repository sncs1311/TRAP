"""Stream consumer  ->  python -m app.worker"""
from __future__ import annotations

import logging
import time
from collections import deque

import redis

from app.config import settings
from app.db import Database
from app.engine import build_engine
from app.events import Transaction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")


class Worker:
    def __init__(self):
        self.s = settings
        self.engine = build_engine(settings)
        self.r = self.engine.r
        self.db = Database(settings.database_url)
        self.window: deque = deque()
        self.last_reclaim = self.last_snap = 0.0
        self._ensure_group()

    # ---------- stream plumbing ----------
    def _ensure_group(self) -> None:
        try:
            self.r.xgroup_create(self.s.stream, self.s.group, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def to_dlq(self, msg_id: str, fields: dict | None, reason: str) -> None:
        pipe = self.r.pipeline(transaction=True)
        pipe.xadd(self.s.dlq_stream, {"original_id": msg_id, "reason": reason,
                                      "data": (fields or {}).get("data", "")},
                  maxlen=10_000, approximate=True)
        pipe.xack(self.s.stream, self.s.group, msg_id)
        pipe.execute()
        self.engine.metrics.record({"dlq": 1})
        log.warning("DLQ %s: %s", msg_id, reason)

    # ---------- processing ----------
    def _commit(self, txns: list[Transaction], ids: list[str]) -> bool:
        """Score + persist + ACK. Returns False (leaving messages pending) on failure."""
        try:
            results, X, scores = self.engine.score_batch(txns, source="stream")
            self.db.insert_results(results)
        except Exception:
            log.exception("batch of %d failed; leaving un-ACKed for redelivery", len(txns))
            try:
                self.engine.metrics.record({"errors": len(txns)})
            except Exception:
                pass
            return False
        self.r.xack(self.s.stream, self.s.group, *ids)
        n = len(results)
        per_event = results[0]["latency_ms"] / n
        self.engine.record_drift(X, scores)
        self.engine.metrics.record(
            {"processed": n,
             "alerts": sum(r["decision"] != "approve" for r in results),
             "declines": sum(r["decision"] == "decline" for r in results)},
            "lat:worker", [per_event] * n)
        return True

    def process(self, entries: list) -> None:
        txns, ids = [], []
        for msg_id, fields in entries:
            if fields is None:                         # entry trimmed from the stream
                self.r.xack(self.s.stream, self.s.group, msg_id)
                continue
            try:
                txns.append(Transaction.model_validate_json(fields["data"]))
                ids.append(msg_id)
            except Exception as e:                     # bad JSON / missing field / validation
                self.to_dlq(msg_id, fields, f"invalid_payload: {str(e)[:200]}")
        if not txns:
            return
        if not self._commit(txns, ids) and len(txns) > 1:
            for tx, mid in zip(txns, ids):             # isolate a poison pill
                self._commit([tx], [mid])

    def reclaim(self) -> None:
        """Re-deliver messages idle too long; send over-retried ones to the DLQ."""
        res = self.r.xautoclaim(self.s.stream, self.s.group, self.s.consumer,
                                min_idle_time=self.s.claim_idle_ms, start_id="0-0",
                                count=self.s.batch_size)
        claimed = res[1]
        if not claimed:
            return
        ids = [m[0] for m in claimed]
        pend = self.r.xpending_range(self.s.stream, self.s.group, min=ids[0], max=ids[-1],
                                     count=1000, consumername=self.s.consumer)
        deliveries = {p["message_id"]: p["times_delivered"] for p in pend}
        retry = []
        for mid, fields in claimed:
            if fields is not None and deliveries.get(mid, 0) > self.s.max_retries:
                self.to_dlq(mid, fields, f"max_retries_exceeded({deliveries[mid]})")
            else:
                retry.append((mid, fields))
        if retry:
            log.info("reclaimed %d pending messages", len(retry))
            self.process(retry)

    # ---------- housekeeping ----------
    def _tick(self, n: int) -> None:
        now = time.time()
        if n:
            self.window.append((now, n))
        while self.window and now - self.window[0][0] > 5:
            self.window.popleft()
        eps = sum(c for _, c in self.window) / 5.0
        self.r.hset("metrics:gauges", mapping={"eps": round(eps, 1)})

    def _snapshot_drift(self) -> None:
        snap = self.engine.drift.compute()
        if snap["status"] != "insufficient_data":
            self.db.insert_psi(snap)

    def run(self) -> None:
        log.info("worker %s consuming %s (group %s)", self.s.consumer, self.s.stream, self.s.group)
        while True:
            try:
                now = time.time()
                if now - self.last_reclaim > 5:
                    self.last_reclaim = now
                    self.reclaim()
                resp = self.r.xreadgroup(self.s.group, self.s.consumer, {self.s.stream: ">"},
                                         count=self.s.batch_size, block=self.s.block_ms)
                entries = resp[0][1] if resp else []
                if entries:
                    self.process(entries)
                self._tick(len(entries))
                if now - self.last_snap > self.s.psi_snapshot_secs:
                    self.last_snap = now
                    self._snapshot_drift()
            except redis.exceptions.ResponseError as e:
                if "NOGROUP" in str(e):
                    self._ensure_group()
                else:
                    log.exception("redis error"); time.sleep(1)
            except redis.exceptions.ConnectionError:
                log.error("redis unavailable, retrying"); time.sleep(1)


if __name__ == "__main__":
    try:
        Worker().run()
    except KeyboardInterrupt:
        log.info("shutting down")