r"""Compare training reference vs live PSI bins for one feature.
Usage (project root): scoring-api\.venv\Scripts\python scripts\inspect_drift.py txn_count_1h [window_min]
"""
import json
import math
import sys
import time
from pathlib import Path

import redis

feat = sys.argv[1] if len(sys.argv) > 1 else "txn_count_1h"
window = int(sys.argv[2]) if len(sys.argv) > 2 else 5

meta_path = Path(__file__).resolve().parents[1] / "scoring-api" / "artifacts" / "metadata.json"
spec = json.loads(meta_path.read_text())["psi_reference"][feat]
exp = list(spec["proportions"])

if spec["type"] == "numeric":
    e = spec["edges"]
    labels = [f"< {e[0]:g}"] + [f"{e[i-1]:g} to < {e[i]:g}" for i in range(1, len(e))] + [f">= {e[-1]:g}"]
else:
    labels = [f"== {v:g}" for v in spec["values"]] + ["unseen"]
    exp.append(0.0)

r = redis.Redis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
now = int(time.time() // 60)
live = [0] * len(exp)
for i in range(window):
    for b, c in r.hgetall(f"psi:cur:{feat}:{now - i}").items():
        live[int(b)] += int(c)
n = sum(live)

print(f"{feat}: {n} live samples in last {window} min\n")
print(f"{'bin':<22}{'training':>10}{'live':>10}{'psi part':>10}")
total = 0.0
for lab, e_, c in zip(labels, exp, live):
    a = c / n if n else 0.0
    ee, aa = max(e_, 1e-4), max(a, 1e-4)
    part = (aa - ee) * math.log(aa / ee)
    total += part
    print(f"{lab:<22}{e_:>10.2%}{a:>10.2%}{part:>10.4f}")
print(f"\nPSI = {total:.4f}")