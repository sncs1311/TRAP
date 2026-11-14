"""Online feature extraction. Follows the contract in app/schema.py exactly."""
from __future__ import annotations

import numpy as np
import redis

from app.events import Transaction
from app.schema import FEATURE_NAMES

WINDOW_TTL_S = 7200

# KEYS: window zset, card profile hash
# ARGV: ts, amount, member, lo1m, lo10m, lo1h, ttl      (lo* = ts - window, exclusive bound)
_LUA = r"""
local win, prof = KEYS[1], KEYS[2]
local amount = tonumber(ARGV[2])
local lo1m, lo10m = tonumber(ARGV[4]), tonumber(ARGV[5])

-- card history BEFORE this txn (contract: hist_mean excludes the current txn)
local pcnt = tonumber(redis.call('HGET', prof, 'cnt')) or 0
local psum = tonumber(redis.call('HGET', prof, 'sum')) or 0

if redis.call('ZADD', win, ARGV[1], ARGV[3]) == 1 then
  redis.call('HINCRBY', prof, 'cnt', 1)
  redis.call('HINCRBYFLOAT', prof, 'sum', ARGV[2])
else
  -- redelivered event: already in the profile, remove it from the "previous" view
  pcnt = pcnt - 1
  psum = psum - amount
end

redis.call('ZREMRANGEBYSCORE', win, '-inf', ARGV[6])                 -- drop <= t-1h
local items = redis.call('ZRANGEBYSCORE', win, '(' .. ARGV[6], ARGV[1], 'WITHSCORES')

local c1, c10, c60, s60 = 0, 0, 0, 0
for i = 1, #items, 2 do
  local sc  = tonumber(items[i + 1])
  local amt = tonumber(string.match(items[i], '|([^|]+)$'))
  c60 = c60 + 1
  s60 = s60 + amt
  if sc > lo10m then c10 = c10 + 1 end
  if sc > lo1m  then c1  = c1  + 1 end
end

redis.call('EXPIRE', win, tonumber(ARGV[7]))
redis.call('EXPIRE', prof, 2592000)
return {c1, c10, c60, tostring(s60), pcnt, tostring(psum)}
"""


class FeatureExtractor:
    def __init__(self, r: redis.Redis):
        self.r = r
        self._script = r.register_script(_LUA)

    def extract_batch(self, txns: list[Transaction]) -> np.ndarray:
        """One pipelined round trip; per-card ordering = order of `txns`."""
        pipe = self.r.pipeline(transaction=False)
        for t in txns:
            ts = t.ts_ms
            self._script(
                keys=[f"win:{t.card_id}", f"prof:{t.card_id}"],
                args=[ts, repr(t.amount), f"{t.txn_id}|{t.amount!r}",
                      ts - 60_000, ts - 600_000, ts - 3_600_000, WINDOW_TTL_S],
                client=pipe,
            )
        out = pipe.execute()

        rows = np.empty((len(txns), len(FEATURE_NAMES)), dtype=np.float64)
        for i, (t, res) in enumerate(zip(txns, out)):
            c1, c10, c60 = int(res[0]), int(res[1]), int(res[2])
            s60, pcnt, psum = float(res[3]), int(res[4]), float(res[5])
            hist = psum / pcnt if pcnt > 0 else t.amount
            if hist <= 0:
                hist = t.amount
            f = {
                "amount": t.amount,
                "hour": t.hour_value(),
                "merchant_cat": t.merchant_cat,
                "is_online": t.is_online,
                "distance_km": t.distance_km,
                "is_foreign": t.is_foreign,
                "account_age_days": t.account_age_days,
                "txn_count_1m": c1,
                "txn_count_10m": c10,
                "txn_count_1h": c60,
                "amount_ratio": t.amount / hist,
                "spend_ratio_1h": s60 / hist,
            }
            rows[i] = [f[n] for n in FEATURE_NAMES]
        return rows