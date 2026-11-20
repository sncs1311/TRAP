r"""TRAP benchmark.

Run with the scoring-api venv (it has redis + psycopg):
    scoring-api\.venv\Scripts\python scripts\benchmark.py --quick
    scoring-api\.venv\Scripts\python scripts\benchmark.py

Needs: docker containers, API (:8010) and worker running. Simulator is paused during the run.
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import platform
import random
import statistics
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import redis

API_HOST, API_PORT = "127.0.0.1", 8010
API = f"http://{API_HOST}:{API_PORT}"
SIM = "http://127.0.0.1:4010"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
DB_URL = os.getenv("DATABASE_URL", "postgresql://trap:trap@127.0.0.1:5433/trap")
STREAM, GROUP = "txn:events", "scorers"
DOCS = Path(__file__).resolve().parents[1] / "docs"
RUN = uuid.uuid4().hex[:6]
MERCH_W = [25, 20, 12, 18, 4, 8, 6, 4, 2, 1]


# ---------------------------------------------------------------- helpers
def die(msg: str) -> None:
    print(f"\nERROR: {msg}")
    sys.exit(1)


def http_json(method: str, url: str, body=None, timeout: float = 10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def pct(vals, p):
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))]


def summ(vals) -> dict:
    if not vals:
        return {"n": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0}
    return {"n": len(vals), "mean": round(statistics.fmean(vals), 2),
            "p50": round(pct(vals, 50), 2), "p95": round(pct(vals, 95), 2),
            "p99": round(pct(vals, 99), 2), "max": round(max(vals), 2)}


def md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def normal_payload(card: str, rng: random.Random) -> dict:
    return {
        "card_id": card,
        "amount": round(min(5000.0, max(0.5, rng.lognormvariate(math.log(40), 0.7))), 2),
        "merchant_cat": rng.choices(range(10), MERCH_W)[0],
        "is_online": int(rng.random() < 0.30),
        "distance_km": round(rng.expovariate(1 / 8.0), 2),
        "is_foreign": 0,
        "account_age_days": rng.randint(30, 3650),
        "hour": rng.randint(7, 21),
    }


def attack_payload(card: str, rng: random.Random) -> dict:
    return {
        "card_id": card, "amount": round(rng.uniform(150, 600), 2), "merchant_cat": 8,
        "is_online": 1, "distance_km": round(rng.uniform(2000, 6000), 1), "is_foreign": 1,
        "account_age_days": rng.randint(30, 120), "hour": 3,
    }


def group_info(r):
    try:
        for g in r.xinfo_groups(STREAM):
            if g["name"] == GROUP:
                return g
    except redis.exceptions.ResponseError:
        pass
    return None


def wait_idle(r, timeout: float = 120.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        g = group_info(r)
        if g and not (g.get("lag") or 0) and not g["pending"]:
            return True
        time.sleep(0.25)
    return False


def processed(r) -> int:
    return int(r.hget("metrics:counters", "processed") or 0)


def preflight(r) -> None:
    try:
        h = http_json("GET", API + "/health", timeout=5)
    except Exception as e:
        die(f"scoring API not reachable at {API} ({e})")
    if h.get("status") != "ok":
        die(f"API unhealthy: {h}")
    if group_info(r) is None:
        die("consumer group not found: start the worker (python -m app.worker)")
    try:
        alive = any(c["idle"] < 5000 for c in r.xinfo_consumers(STREAM, GROUP))
    except Exception:
        alive = False
    if not alive:
        die("no active stream worker: start it (python -m app.worker)")


# ---------------------------------------------------------------- A: /score sequential
def score_sequential(n, warmup, make, tag, seed=7):
    rng = random.Random(seed)
    conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=15)
    hdr = {"Content-Type": "application/json"}
    cli, srv, flagged = [], [], 0
    for i in range(warmup + n):
        body = json.dumps(make(f"bench-{tag}-{RUN}-{i}", rng))
        t0 = time.perf_counter()
        conn.request("POST", "/score", body, hdr)
        resp = conn.getresponse()
        raw = resp.read()
        ms = (time.perf_counter() - t0) * 1000
        if resp.status != 200:
            raise RuntimeError(f"/score returned {resp.status}: {raw[:200]!r}")
        if i >= warmup:
            out = json.loads(raw)
            cli.append(ms)
            srv.append(out["latency_ms"])
            flagged += out["decision"] != "approve"
    conn.close()
    return cli, srv, flagged


# ---------------------------------------------------------------- B: /score concurrent
def score_concurrent(threads, total, seed=100):
    per = max(1, total // threads)
    out = [None] * threads
    barrier = threading.Barrier(threads + 1)

    def work(k):
        rng = random.Random(seed + k)
        hdr = {"Content-Type": "application/json"}
        conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=30)

        def call(tag):
            body = json.dumps(normal_payload(f"bench-c{threads}-{RUN}-{k}-{tag}", rng))
            t0 = time.perf_counter()
            conn.request("POST", "/score", body, hdr)
            resp = conn.getresponse()
            resp.read()
            return resp.status, (time.perf_counter() - t0) * 1000

        try:
            for i in range(20):
                call(f"w{i}")
        except Exception:
            pass
        barrier.wait(timeout=60)
        lat, err = [], 0
        for i in range(per):
            try:
                st, ms = call(i)
                if st == 200:
                    lat.append(ms)
                else:
                    err += 1
            except Exception:
                err += 1
                conn.close()        # http.client reconnects on the next request
        out[k] = (lat, err)
        conn.close()

    ths = [threading.Thread(target=work, args=(k,)) for k in range(threads)]
    for t in ths:
        t.start()
    barrier.wait(timeout=60)
    t0 = time.perf_counter()
    for t in ths:
        t.join()
    elapsed = time.perf_counter() - t0
    lat = [x for o in out if o for x in o[0]]
    err = sum(o[1] for o in out if o)
    return {"clients": threads, "completed": len(lat), "errors": err,
            "rps": round(len(lat) / elapsed, 1), "client_ms": summ(lat)}


# ---------------------------------------------------------------- C: stream drain throughput
def stream_drain(r, n, seed):
    rng = random.Random(seed)
    now = int(time.time() * 1000)
    msgs = []
    for _ in range(n):                                   # generate BEFORE the timer starts
        ev = normal_payload(f"bench-s-{RUN}-{rng.randrange(200_000)}", rng)
        ev["txn_id"] = uuid.uuid4().hex
        ev["ts_ms"] = now
        msgs.append(json.dumps(ev, separators=(",", ":")))
    base = processed(r)
    t0 = time.perf_counter()
    for i in range(0, n, 1000):
        pipe = r.pipeline(transaction=False)
        for m in msgs[i:i + 1000]:
            pipe.xadd(STREAM, {"data": m}, maxlen=200_000, approximate=True)
        pipe.execute()
    t_enq = time.perf_counter() - t0
    deadline = t0 + 180
    while processed(r) - base < n:
        if time.perf_counter() > deadline:
            return {"error": "timeout", "events": n, "done": processed(r) - base}
        time.sleep(0.02)
    elapsed = time.perf_counter() - t0
    return {"events": n, "seconds": round(elapsed, 2), "eps": round(n / elapsed),
            "enqueue_seconds": round(t_enq, 2)}


# ---------------------------------------------------------------- D: end-to-end latency
def e2e_level(r, pg, rate, seconds, seed):
    stop = threading.Event()
    sent = [0]

    def pacer():
        rng = random.Random(seed)
        tick, acc = 0.05, 0.0
        nxt = time.perf_counter()
        while not stop.is_set():
            nxt += tick
            acc += rate * tick
            k = int(acc)
            acc -= k
            if k:
                now = int(time.time() * 1000)
                pipe = r.pipeline(transaction=False)
                for _ in range(k):
                    ev = normal_payload(f"bench-e-{RUN}-{rng.randrange(200_000)}", rng)
                    ev["txn_id"] = uuid.uuid4().hex
                    ev["ts_ms"] = now
                    pipe.xadd(STREAM, {"data": json.dumps(ev, separators=(",", ":"))},
                              maxlen=200_000, approximate=True)
                pipe.execute()
                sent[0] += k
            d = nxt - time.perf_counter()
            if d > 0:
                stop.wait(d)
            else:
                nxt = time.perf_counter()

    t_start = time.perf_counter()
    th = None
    if rate > 0:
        th = threading.Thread(target=pacer, daemon=True)
        th.start()
        time.sleep(1.0)                                  # let the load reach steady state

    rng = random.Random(seed + 1)
    cur = pg.cursor()
    lat, timeouts = [], 0
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        txn_id = uuid.uuid4().hex
        ev = normal_payload(f"bench-p-{RUN}-{uuid.uuid4().hex[:8]}", rng)
        ev["txn_id"] = txn_id
        ev["ts_ms"] = int(time.time() * 1000)
        payload = json.dumps(ev, separators=(",", ":"))
        t0 = time.perf_counter()
        r.xadd(STREAM, {"data": payload}, maxlen=200_000, approximate=True)
        while True:
            cur.execute("SELECT 1 FROM transactions WHERE txn_id = %s", (txn_id,))
            if cur.fetchone():
                lat.append((time.perf_counter() - t0) * 1000)
                break
            if time.perf_counter() - t0 > 15:
                timeouts += 1
                break
            time.sleep(0.0005)
        time.sleep(0.1)

    elapsed = time.perf_counter() - t_start
    stop.set()
    if th:
        th.join()
    wait_idle(r, 180)
    return {"offered_eps": rate, "achieved_eps": round(sent[0] / elapsed) if rate else 0,
            "probes": summ(lat), "timeouts": timeouts}


# ---------------------------------------------------------------- cleanup
def cleanup(r) -> None:
    n = 0
    for pat in ("win:bench-*", "prof:bench-*"):
        batch = []
        for k in r.scan_iter(pat, count=1000):
            batch.append(k)
            if len(batch) >= 1000:
                n += r.delete(*batch)
                batch = []
        if batch:
            n += r.delete(*batch)
    with psycopg.connect(DB_URL, autocommit=True) as pg:
        cur = pg.execute("DELETE FROM transactions WHERE card_id LIKE 'bench-%'")
        rows = cur.rowcount
    print(f"cleanup: removed {n} Redis keys and {rows} Postgres rows (benchmark data only)")


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small run (~1-2 min) to check everything works")
    ap.add_argument("--keep", action="store_true", help="do not delete benchmark rows/keys afterwards")
    ap.add_argument("--n", type=int, default=5000, help="/score calls for the latency test")
    ap.add_argument("--stream-n", type=int, default=20000, help="events per throughput run")
    ap.add_argument("--repeats", type=int, default=3, help="throughput runs")
    ap.add_argument("--probe-seconds", type=int, default=12, help="seconds per end-to-end load level")
    ap.add_argument("--levels", default="", help="comma-separated offered eps for end-to-end, e.g. 0,100,300")
    ap.add_argument("--sections", default="score,conc,stream,e2e")
    a = ap.parse_args()
    if a.quick:
        a.n, a.stream_n, a.repeats, a.probe_seconds = 1000, 5000, 1, 6
    secs = set(a.sections.split(","))

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    preflight(r)
    res = {"env": {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "python": platform.python_version(), "os": platform.platform(),
                   "cpu": platform.processor(), "logical_cpus": os.cpu_count(),
                   "note": "load generator, API, worker, Redis and Postgres (Docker) all on one machine"},
           "params": vars(a)}
    md = []

    sim_was_running = None
    try:
        st = http_json("GET", SIM + "/status", timeout=3)
        sim_was_running = bool(st["running"])
        http_json("POST", SIM + "/control/stop", {})
        print("simulator paused for the benchmark")
    except Exception:
        print("warning: simulator not reachable (fine, continuing)")

    try:
        if not wait_idle(r, 90):
            die("stream did not drain before the benchmark started")
        capacity = None

        if "score" in secs:
            print(f"\n[A] /score latency, sequential, keep-alive ({a.n} calls + 200 warm-up) ...")
            rows, res["score"] = [], {}
            for name, mk, n, tag in (("normal traffic", normal_payload, a.n, "n"),
                                     ("high-risk (SHAP path)", attack_payload, max(200, a.n // 5), "a")):
                cli, srv, fl = score_sequential(n, 200, mk, tag)
                c, s = summ(cli), summ(srv)
                res["score"][name] = {"client_ms": c, "server_ms": s, "flagged_pct": round(100 * fl / n, 1)}
                rows.append([name, n, c["p50"], c["p95"], c["p99"], c["max"],
                             s["p50"], s["p95"], s["p99"], f"{100 * fl / n:.0f}%"])
            t = md_table(["Scenario", "n", "Client p50", "p95", "p99", "max",
                          "Server p50", "p95", "p99", "Flagged"], rows)
            md += ["### /score latency (ms)", t, ""]
            print(t)
            ok = res["score"]["normal traffic"]["server_ms"]["p99"] < 15
            print(f"server-side p99 < 15 ms on normal traffic: {'YES' if ok else 'NO'}")
            time.sleep(2)

        if "conc" in secs:
            print("\n[B] /score under concurrency ...")
            rows, res["concurrency"] = [], []
            for th in (4, 16):
                o = score_concurrent(th, 1000 if a.quick else 4000)
                res["concurrency"].append(o)
                c = o["client_ms"]
                rows.append([th, o["rps"], c["p50"], c["p95"], c["p99"], o["errors"]])
            t = md_table(["Clients", "Req/s", "Client p50", "p95", "p99", "Errors"], rows)
            md += ["### /score concurrency (ms)", t, ""]
            print(t)
            time.sleep(3)

        if "stream" in secs:
            print(f"\n[C] stream drain throughput ({a.repeats} x {a.stream_n} events) ...")
            runs = []
            for i in range(a.repeats):
                wait_idle(r, 120)
                o = stream_drain(r, a.stream_n, seed=1000 + i)
                runs.append(o)
                print(f"   run {i + 1}: {o}")
            good = [o["eps"] for o in runs if "eps" in o]
            res["stream"] = {"runs": runs}
            if good:
                capacity = statistics.median(good)
                res["stream"].update({"median_eps": capacity, "min_eps": min(good), "max_eps": max(good)})
            t = md_table(["Run", "Events", "Seconds", "Events/s"],
                         [[i + 1, o.get("events"), o.get("seconds", "-"), o.get("eps", o.get("error"))]
                          for i, o in enumerate(runs)])
            md += ["### Stream throughput (XADD -> score -> Postgres commit)", t, ""]
            if good:
                md.append(f"Median: **{capacity:.0f} events/s** (single worker, batch size 100)\n")
            print(t)

        if "e2e" in secs:
            if a.levels:
                levels = [int(x) for x in a.levels.split(",")]
            elif capacity:
                levels = [0] + [max(10, int(round(capacity * f, -1))) for f in (0.25, 0.5, 0.8)]
            else:
                levels = [0, 100, 300]
            print(f"\n[D] end-to-end latency (enqueue -> row visible in Postgres), levels {levels} ...")
            rows, res["e2e"] = [], []
            with psycopg.connect(DB_URL, autocommit=True) as pg:
                for lv in levels:
                    wait_idle(r, 180)
                    o = e2e_level(r, pg, lv, a.probe_seconds, seed=lv + 7)
                    util = f"{100 * lv / capacity:.0f}%" if capacity else "-"
                    o["utilization"] = util
                    res["e2e"].append(o)
                    p = o["probes"]
                    rows.append([lv, util, o["achieved_eps"], p["n"], p["p50"], p["p95"], p["p99"],
                                 p["max"], o["timeouts"]])
                    print(f"   offered {lv} eps: p50={p['p50']} p95={p['p95']} p99={p['p99']} ms "
                          f"(timeouts={o['timeouts']})")
            t = md_table(["Offered eps", "% of capacity", "Achieved eps", "Probes", "p50 ms", "p95",
                          "p99", "max", "Timeouts"], rows)
            md += ["### End-to-end latency, enqueue to persisted decision", t, ""]
            print(t)
    finally:
        if sim_was_running:
            try:
                http_json("POST", SIM + "/control/start", {})
                print("\nsimulator resumed")
            except Exception:
                print("\nwarning: could not resume the simulator; run: python scripts\\chaos.py start")
        try:
            http_json("POST", API + "/drift/reset", {})
        except Exception:
            pass
        if not a.keep:
            try:
                cleanup(r)
            except Exception as e:
                print(f"cleanup failed ({e}); safe to ignore")

    DOCS.mkdir(exist_ok=True)
    hist_path = DOCS / "benchmark_results.json"
    hist = []
    if hist_path.exists():
        try:
            hist = json.loads(hist_path.read_text(encoding="utf-8"))
        except Exception:
            hist = []
    hist.append(res)
    hist_path.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    header = (f"_Run {res['env']['date']} on {res['env']['os']}, {res['env']['logical_cpus']} logical CPUs, "
              f"Python {res['env']['python']}. Everything ran on one machine._\n")
    (DOCS / "benchmark_latest.md").write_text(header + "\n" + "\n".join(md), encoding="utf-8")
    print(f"\nwrote {hist_path} and {DOCS / 'benchmark_latest.md'}")


if __name__ == "__main__":
    main()