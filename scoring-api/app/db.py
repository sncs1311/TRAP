"""PostgreSQL persistence (sync psycopg3 pool)."""
from __future__ import annotations

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

SQL_TXN = """
INSERT INTO transactions (txn_id, card_id, ts_ms, amount, features, score, decision,
                          model_version, latency_ms, source, true_label, pattern)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (txn_id) DO NOTHING"""

SQL_ALERT = """
INSERT INTO fraud_alerts (txn_id, card_id, score, decision, reasons, shap)
VALUES (%s,%s,%s,%s,%s,%s)
ON CONFLICT (txn_id) DO NOTHING"""

SQL_PSI = """
INSERT INTO psi_snapshots (feature, psi, status, n_samples) VALUES (%s,%s,%s,%s)"""


class Database:
    def __init__(self, url: str, max_size: int = 8):
        self.pool = ConnectionPool(url, min_size=1, max_size=max_size, open=True,
                                   kwargs={"row_factory": dict_row})
        self.pool.wait()

    def insert_results(self, results: list[dict]) -> None:
        txn_rows = [(r["txn_id"], r["card_id"], r["ts_ms"], r["amount"], Jsonb(r["features"]),
                     r["score"], r["decision"], r["model_version"], r["latency_ms"],
                     r["source"], r["true_label"], r["pattern"]) for r in results]
        alert_rows = [(r["txn_id"], r["card_id"], r["score"], r["decision"],
                       Jsonb(r["reasons"]), Jsonb(r["contributions"]))
                      for r in results if r["decision"] != "approve"]
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(SQL_TXN, txn_rows)
            if alert_rows:
                cur.executemany(SQL_ALERT, alert_rows)

    def insert_psi(self, snap: dict) -> None:
        rows = [(f, d["psi"], d["status"], d["n_samples"])
                for f, d in snap["features"].items() if d["psi"] is not None]
        rows.append(("__overall__", snap["overall_psi"], snap["status"], snap["n_samples"]))
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(SQL_PSI, rows)

    def get_transaction(self, txn_id: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT txn_id, score, decision, features FROM transactions WHERE txn_id = %s",
                (txn_id,)).fetchone()

    def ping(self) -> bool:
        with self.pool.connection() as conn:
            return conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1

    def close(self) -> None:
        self.pool.close()

    def recent_transactions(self, limit: int) -> list[dict]:
        with self.pool.connection() as conn:
            return conn.execute(
                """SELECT txn_id, card_id, ts_ms, amount, score, decision, latency_ms,
                          source, true_label, pattern, scored_at
                   FROM transactions ORDER BY scored_at DESC LIMIT %s""",
                (limit,)).fetchall()

    def list_alerts(self, status: str, limit: int) -> list[dict]:
        where, params = "", []
        if status != "all":
            where = "WHERE a.status = %s"
            params.append(status)
        params.append(limit)
        with self.pool.connection() as conn:
            return conn.execute(
                f"""SELECT a.alert_id, a.txn_id, a.card_id, a.score, a.decision, a.reasons,
                           a.shap, a.status, a.created_at,
                           t.amount, t.ts_ms, t.pattern, t.true_label, t.latency_ms
                    FROM fraud_alerts a JOIN transactions t ON t.txn_id = a.txn_id
                    {where}
                    ORDER BY a.created_at DESC LIMIT %s""",
                params).fetchall()

    def add_feedback(self, txn_id: str, label: str, analyst: str, note: str | None) -> dict | None:
        status = "confirmed_fraud" if label == "fraud" else "false_positive"
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM transactions WHERE txn_id = %s", (txn_id,))
            if cur.fetchone() is None:
                return None
            cur.execute(
                """INSERT INTO analyst_feedback (txn_id, label, analyst, note)
                   VALUES (%s, %s, %s, %s) RETURNING feedback_id""",
                (txn_id, label, analyst, note))
            feedback_id = cur.fetchone()["feedback_id"]
            cur.execute("UPDATE fraud_alerts SET status = %s WHERE txn_id = %s", (status, txn_id))
            updated = cur.rowcount == 1
        return {"feedback_id": feedback_id, "txn_id": txn_id, "label": label,
                "alert_status": status if updated else None, "alert_updated": updated}

    def stats(self) -> dict:
        with self.pool.connection() as conn:
            alerts = conn.execute(
                "SELECT status, count(*) AS n FROM fraud_alerts GROUP BY status").fetchall()
            recent = conn.execute(
                """SELECT decision, count(*) AS n FROM transactions
                   WHERE scored_at > now() - interval '60 seconds' GROUP BY decision""").fetchall()
        by_status = {r["status"]: r["n"] for r in alerts}
        by_decision = {r["decision"]: r["n"] for r in recent}
        reviewed = by_status.get("confirmed_fraud", 0) + by_status.get("false_positive", 0)
        return {
            "alerts": {"open": by_status.get("open", 0),
                       "confirmed_fraud": by_status.get("confirmed_fraud", 0),
                       "false_positive": by_status.get("false_positive", 0)},
            "analyst_precision": (by_status.get("confirmed_fraud", 0) / reviewed) if reviewed else None,
            "last_60s": {"approve": by_decision.get("approve", 0),
                         "review": by_decision.get("review", 0),
                         "decline": by_decision.get("decline", 0),
                         "total": sum(by_decision.values())},
        }

    def psi_history(self, feature: str, minutes: int) -> list[dict]:
        with self.pool.connection() as conn:
            return conn.execute(
                """SELECT captured_at, psi, status, n_samples FROM psi_snapshots
                   WHERE feature = %s AND captured_at > now() - %s::int * interval '1 minute'
                   ORDER BY captured_at ASC""",
                (feature, minutes)).fetchall()