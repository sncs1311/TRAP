r"""Measure host->Redis and host->Postgres costs in isolation.
Run: scoring-api\.venv\Scripts\python scripts\profile_io.py
"""
import time

import psycopg
import redis
from psycopg.types.json import Jsonb


def timeit(fn, n):
    xs = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t0) * 1000)
    xs.sort()
    return f"p50={xs[len(xs) // 2]:7.2f}  p95={xs[int(len(xs) * .95) - 1]:7.2f} ms"


r = redis.Redis.from_url("redis://127.0.0.1:6379/0")
print("REDIS (host -> container)")
print("  PING                 ", timeit(r.ping, 500))


def pipe10():
    p = r.pipeline(transaction=False)
    for i in range(10):
        p.hincrby("prof:test", str(i), 1)
    p.execute()


print("  pipeline of 10 cmds  ", timeit(pipe10, 300))
r.delete("prof:test")

FEATS = {f"f{i}": float(i) for i in range(12)}
ROW = ("x", 1, 2.0, Jsonb(FEATS))

for host in ("127.0.0.1", "localhost"):
    url = f"postgresql://sentinel:sentinel@{host}:5433/sentinelstream"
    print(f"\nPOSTGRES via {host}:5433")
    t0 = time.perf_counter()
    conn = psycopg.connect(url, autocommit=True)
    print(f"  connect              {(time.perf_counter() - t0) * 1000:7.2f} ms")
    conn.execute("CREATE TABLE IF NOT EXISTS _prof (a text, b int, c float8, d jsonb)")
    print("  SELECT 1             ", timeit(lambda: conn.execute("SELECT 1").fetchone(), 200))
    ins = "INSERT INTO _prof VALUES (%s,%s,%s,%s)"
    print("  1 INSERT, sync on    ", timeit(lambda: conn.execute(ins, ROW), 100))

    def batch100():
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(ins, [ROW] * 100)

    print("  100-row executemany  ", timeit(batch100, 30))
    conn.execute("SET synchronous_commit = off")
    print("  1 INSERT, sync off   ", timeit(lambda: conn.execute(ins, ROW), 100))
    print("  100-row, sync off    ", timeit(batch100, 30))
    conn.execute("DROP TABLE _prof")
    conn.close()