"""Scoring & MLOps API  ->  uvicorn app.main:app --port 8010"""
from __future__ import annotations

from contextlib import asynccontextmanager

import numpy as np
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Database
from app.engine import build_engine
from app.events import Transaction
from app.schema import FEATURE_NAMES


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = build_engine(settings)
    app.state.db = Database(settings.database_url)
    yield
    app.state.db.close()
    app.state.engine.r.close()


app = FastAPI(title="SentinelStream Scoring API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_methods=["*"], allow_headers=["*"])


def _after_score(results, X, scores) -> None:
    """Runs after the HTTP response is sent (keeps persistence out of scoring latency)."""
    eng, db = app.state.engine, app.state.db
    eng.record_drift(X, scores)
    eng.metrics.record(
        {"processed": len(results),
         "alerts": sum(r["decision"] != "approve" for r in results),
         "declines": sum(r["decision"] == "decline" for r in results)},
        "lat:api", [r["latency_ms"] for r in results])
    db.insert_results(results)


@app.post("/score")
def score(tx: Transaction, bg: BackgroundTasks):
    results, X, scores = app.state.engine.score_batch([tx], source="api")
    bg.add_task(_after_score, results, X, scores)
    return results[0]


@app.post("/ingest", status_code=202)
def ingest(tx: Transaction):
    """Publish one event to the Redis Stream (worker scores it asynchronously)."""
    msg_id = app.state.engine.r.xadd(settings.stream, {"data": tx.model_dump_json()},
                                     maxlen=100_000, approximate=True)
    return {"stream_id": msg_id, "txn_id": tx.txn_id}


@app.get("/explain/{txn_id}")
def explain(txn_id: str):
    row = app.state.db.get_transaction(txn_id)
    if not row:
        raise HTTPException(404, "transaction not found")
    model = app.state.engine.model
    x = np.array([[row["features"][n] for n in FEATURE_NAMES]], dtype=np.float64)
    sv = model.shap_values(x)[0]
    return {"txn_id": txn_id, "score": row["score"], "decision": row["decision"],
            "base_value": round(model.base_value, 4), **model.explain(x[0], sv)}


@app.get("/metrics")
def metrics():
    eng = app.state.engine
    return {**eng.metrics.snapshot(settings),
            "model": {"version": eng.model.version, "threshold": eng.model.threshold,
                      "auc_pr_test": eng.model.meta["metrics"]["auc_pr_test"]}}


@app.get("/drift")
def drift():
    return app.state.engine.drift.compute()


@app.post("/drift/reset")
def drift_reset():
    return {"cleared_keys": app.state.engine.drift.reset()}


@app.get("/health")
def health():
    eng = app.state.engine
    return {"status": "ok", "redis": bool(eng.r.ping()), "postgres": app.state.db.ping(),
            "model_version": eng.model.version}