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