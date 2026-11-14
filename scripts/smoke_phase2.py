"""End-to-end smoke test. Needs API (:8010) and worker running."""
import json
import statistics
import time
import urllib.request
import uuid

import redis

API = "http://127.0.0.1:8010"


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def txn(card, amount, ts_ms, **kw):
    base = dict(card_id=card, amount=amount, ts_ms=ts_ms, merchant_cat=0, is_online=0,
                distance_km=3.0, is_foreign=0, account_age_days=900)
    return {**base, **kw}


print("health:", call("/health"))
now = int(time.time() * 1000)

print("\n[1] normal purchase")
r = call("/score", txn("smoke-normal", 35.0, now))
print(f"    score={r['score']:.4f} decision={r['decision']} latency={r['latency_ms']}ms")

print("\n[2] card-testing attack on a card with normal history")
card = "smoke-ct-" + uuid.uuid4().hex[:6]
for k, hrs in enumerate((48, 24, 3)):                         # old history, oldest first
    call("/score", txn(card, 30 + 5 * k, now - hrs * 3_600_000, account_age_days=45))
t0 = int(time.time() * 1000)
for k in range(8):
    r = call("/score", txn(card, 2.5 + k, t0 + k * 5000, is_online=1, is_foreign=1,
                           distance_km=3500, merchant_cat=7, account_age_days=45))
    print(f"    tiny #{k + 1}: score={r['score']:.3f} {r['decision']:<8} "
          f"count_1m={int(r['features']['txn_count_1m'])}")
r = call("/score", txn(card, 450.0, t0 + 50_000, is_online=1, is_foreign=1,
                       distance_km=3500, merchant_cat=8, account_age_days=45))
print(f"    BIG   : score={r['score']:.3f} {r['decision']} latency={r['latency_ms']}ms")
for x in r["reasons"]:
    print(f"       - {x['text']}  (shap {x['shap']:+.2f})")

print("\n[3] latency over 100 /score calls (server-side vs client round trip)")
srv, cli = [], []
for i in range(100):
    t = time.perf_counter()
    r = call("/score", txn(f"lat-{i}", 20 + i, int(time.time() * 1000)))
    cli.append((time.perf_counter() - t) * 1000)
    srv.append(r["latency_ms"])
q = lambda v, p: sorted(v)[int(len(v) * p) - 1]
print(f"    server p50={statistics.median(srv):.2f}ms p95={q(srv, .95):.2f}ms | "
      f"client p50={statistics.median(cli):.2f}ms p95={q(cli, .95):.2f}ms")

print("\n[4] stream path: 20 valid events + 1 poison message")
for i in range(20):
    call("/ingest", txn(f"stream-{i}", 25 + i, int(time.time() * 1000)))
rc = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
rc.xadd("txn:events", {"data": "this-is-not-json"})
time.sleep(3)
m = call("/metrics")
print(json.dumps({k: m[k] for k in ("counters", "stream", "worker_latency_ms_per_event",
                                    "api_latency_ms", "throughput_eps")}, indent=2))
print("\ndrift:", json.dumps({k: call("/drift")[k] for k in ("status", "n_samples")}))