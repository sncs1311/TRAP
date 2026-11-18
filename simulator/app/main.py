"""Traffic & Chaos Simulator  ->  uvicorn app.main:app --host 127.0.0.1 --port 4010"""
from __future__ import annotations

import os
import json
import logging
import threading
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import settings
from app.generator import KNOBS, ZERO_DRIFT, CardPool, EventFactory
from app.producer import Producer
from app.replay import CsvReplay
from app.state import ChaosState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PRESETS = {
    "mild":   {"amount": 0.2, "distance": 0.0, "online": 0.3, "night": 0.3},
    "severe": {"amount": 1.0, "distance": 0.6, "online": 1.0, "night": 1.0},
}
_attack_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    r.ping()
    pool = CardPool(settings.pool_size, settings.seed)
    factory = EventFactory(pool, settings.seed + 7, settings.seed + 11)
    chaos = ChaosState(settings.base_rps, settings.autostart)
    producer = Producer(chaos, pool, factory, r, settings)
    if os.getenv("PREWARM", "1") == "1":
        n = producer.prewarm(time.time())
        logging.getLogger("sim").info("pre-warmed %d sessions", n)
    producer.start()
    app.state.r, app.state.factory, app.state.chaos, app.state.producer = r, factory, chaos, producer
    yield
    producer.stop_evt.set()
    producer.join(timeout=3)
    r.close()


app = FastAPI(title="SentinelStream Simulator", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_methods=["*"], allow_headers=["*"])


# ---------- request models ----------
class RpsReq(BaseModel):
    rps: float = Field(ge=0, le=5000)


class BurstReq(BaseModel):
    rps: float = Field(300, ge=1, le=5000)
    duration_s: float = Field(20, ge=1, le=300)


class AttackReq(BaseModel):
    kind: Literal["card_testing", "takeover"] = "card_testing"
    n_attacks: int = Field(1, ge=1, le=50)
    interval_s: float = Field(6.0, ge=0.5, le=60)     # mean gap between attack txns
    spread_s: float = Field(5.0, ge=0, le=120)        # attacks start randomly within this window


class DriftReq(BaseModel):
    preset: Literal["mild", "severe"] | None = None
    amount: float | None = Field(None, ge=0, le=1)
    distance: float | None = Field(None, ge=0, le=1)
    online: float | None = Field(None, ge=0, le=1)
    night: float | None = Field(None, ge=0, le=1)
    ramp_seconds: float = Field(30.0, ge=0, le=600)   # 0 = instant


class ClearReq(BaseModel):
    ramp_seconds: float = Field(0.0, ge=0, le=600)
    reset_psi: bool = True


class ReplayReq(BaseModel):
    file: str
    rps: float | None = Field(None, ge=1, le=5000)
    limit: int | None = Field(None, ge=1)
    loop: bool = False


# ---------- endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok", "redis": bool(app.state.r.ping())}


@app.get("/status")
def status():
    return app.state.chaos.status(time.time(), len(app.state.producer.heap))


@app.post("/control/start")
def start():
    app.state.chaos.running = True
    return {"running": True}


@app.post("/control/stop")
def stop():
    app.state.chaos.running = False
    return {"running": False}


@app.post("/control/rps")
def set_rps(req: RpsReq):
    app.state.chaos.base_rps = req.rps
    return {"rps_target": req.rps}


@app.post("/control/burst")
def burst(req: BurstReq):
    app.state.chaos.start_burst(req.rps, req.duration_s, time.time())
    return {"burst_rps": req.rps, "duration_s": req.duration_s}


@app.post("/control/attack")
def attack(req: AttackReq):
    now, cards, total = time.time(), [], 0
    with _attack_lock:
        for _ in range(req.n_attacks):
            start_in = float(app.state.factory.attack_rng.uniform(0, req.spread_s))
            cid, events = app.state.factory.plan_attack(req.kind, start_in, req.interval_s)
            cards.append(cid)
            total += len(events)
            for off, ev in events:
                app.state.chaos.attack_q.put((now + off, ev))
    app.state.chaos.attacks_launched += req.n_attacks
    return {"kind": req.kind, "launched": req.n_attacks, "events_scheduled": total, "card_ids": cards}


@app.post("/control/drift")
def set_drift(req: DriftReq):
    target = dict(PRESETS[req.preset]) if req.preset else dict(ZERO_DRIFT)
    explicit = {k: getattr(req, k) for k in KNOBS if getattr(req, k) is not None}
    if not req.preset and not explicit:
        raise HTTPException(400, "give a preset or at least one of: " + ", ".join(KNOBS))
    target.update(explicit)                           # unspecified knobs end at 0
    app.state.chaos.set_drift(target, req.ramp_seconds, time.time())
    return {"target": target, "ramp_seconds": req.ramp_seconds}


def _reset_psi() -> dict:
    try:
        rq = urllib.request.Request(settings.scoring_api_url + "/drift/reset", data=b"{}",
                                    headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(rq, timeout=3) as resp:
            return json.load(resp)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@app.post("/control/drift/clear")
def clear_drift(req: ClearReq | None = None):
    req = req or ClearReq()
    app.state.chaos.set_drift(ZERO_DRIFT, req.ramp_seconds, time.time())
    out = {"cleared": True, "ramp_seconds": req.ramp_seconds}
    if req.reset_psi:
        out["psi_reset"] = _reset_psi()
    return out


@app.post("/control/replay")
def replay(req: ReplayReq):
    if Path(req.file).name != req.file:
        raise HTTPException(400, "file must be a bare filename inside simulator/data/")
    path = settings.data_dir / req.file
    if not path.exists():
        raise HTTPException(404, f"{path} not found")
    try:
        rep = CsvReplay(path, req.limit, req.loop)
    except ValueError as e:
        raise HTTPException(400, str(e))
    app.state.chaos.start_replay(rep, req.file, req.rps)
    return {"replaying": req.file, "rps": app.state.chaos.base_rps}


@app.post("/control/replay/stop")
def replay_stop():
    app.state.chaos.end_replay()
    return {"mode": "synthetic"}


@app.post("/control/reset")
def reset():
    app.state.chaos.reset()
    return {"reset": True}