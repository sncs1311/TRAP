"""Event generator. Distributions mirror scoring-api/ml/data_gen.py (keep them in sync)."""
from __future__ import annotations

import numpy as np

HOUR_W = np.array([0.5, 0.3, 0.2, 0.2, 0.3, 0.6,
                   1.5, 2.5, 3.5,
                   4, 4.5, 5, 5.5, 5.5, 5, 4.5, 4.5, 4.5,
                   5, 5, 4, 3,
                   1.5, 0.8])
HOUR_P = HOUR_W / HOUR_W.sum()
NIGHT_W = np.array([9, 9, 8, 7, 6, 5] + [1] * 16 + [3, 5], dtype=float)   # drift target: night-heavy
NIGHT_P = NIGHT_W / NIGHT_W.sum()

LEGIT_MERCH_P = np.array([.25, .20, .12, .18, .04, .08, .06, .04, .02, .01])
FRAUD_MERCH_P = np.array([.02, .02, .02, .10, .08, .06, .02, .30, .20, .18])

KNOBS = ("amount", "distance", "online", "night")
ZERO_DRIFT = {k: 0.0 for k in KNOBS}
AMOUNT_GAIN, DIST_GAIN, ONLINE_GAIN = 2.0, 4.0, 0.5      # intensity 1.0 => x3, x5, 30% -> 80%


class CardPool:
    """Virtual card population; attributes live in arrays, activity-weighted like training."""

    def __init__(self, n: int, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.n = n
        self.avg_amt = np.exp(rng.normal(np.log(40.0), 0.6, n)).astype(np.float32)
        self.age_base = rng.integers(30, 3650, n).astype(np.int32)
        lam = rng.gamma(2.0, 0.25, n)                    # txns/day, as in training
        self.lam = lam.astype(np.float32)
        self.cdf = np.cumsum(lam)
        self.cdf /= self.cdf[-1]
        self.seeded = np.zeros(n, dtype=bool)            # profile written to Redis already?
        self._rng = np.random.default_rng(seed + 1)

    def sample(self, k: int) -> np.ndarray:
        idx = np.searchsorted(self.cdf, self._rng.random(k))
        return np.minimum(idx, self.n - 1)


def card_id(i: int) -> str:
    return f"c{int(i):07d}"


class EventFactory:
    def __init__(self, pool: CardPool, seed: int = 7, attack_seed: int = 11):
        self.pool = pool
        self.rng = np.random.default_rng(seed)            # producer thread only
        self.attack_rng = np.random.default_rng(attack_seed)   # request threads (locked by caller)

    # ---------- legitimate traffic ----------
    def legit(self, idx: np.ndarray, drift: dict) -> list[dict]:
        n = len(idx)
        if n == 0:
            return []
        rng, pool = self.rng, self.pool
        avg = pool.avg_amt[idx].astype(np.float64)
        amount = np.clip(rng.lognormal(np.log(avg), 0.7), 0.5, 5000)
        is_foreign = rng.random(n) < 0.02
        distance = rng.exponential(8.0, n)
        travelling = (rng.random(n) < 0.03) & ~is_foreign
        distance = np.where(travelling, rng.uniform(100, 2000, n), distance)
        distance = np.where(is_foreign, rng.uniform(500, 8000, n), distance)
        online = rng.random(n) < (0.30 + ONLINE_GAIN * drift["online"])
        hour_p = (1 - drift["night"]) * HOUR_P + drift["night"] * NIGHT_P
        hour = rng.choice(24, n, p=hour_p)
        merch = rng.choice(10, n, p=LEGIT_MERCH_P)
        age = pool.age_base[idx] + rng.integers(0, 30, n)
        amount = amount * (1 + AMOUNT_GAIN * drift["amount"])
        distance = distance * (1 + DIST_GAIN * drift["distance"])

        return [
            {"_idx": i, "card_id": card_id(i), "amount": a, "merchant_cat": m, "is_online": o,
             "distance_km": d, "is_foreign": f, "account_age_days": g, "hour": h,
             "label": 0, "pattern": "legit"}
            for i, a, m, o, d, f, g, h in zip(
                idx.tolist(), amount.round(2).tolist(), merch.tolist(), online.astype(int).tolist(),
                distance.round(2).tolist(), is_foreign.astype(int).tolist(), age.tolist(), hour.tolist())
        ]

    # ---------- attacks ----------
    def plan_attack(self, kind: str, start_in: float, interval_s: float):
        """Returns (card_id, [(offset_seconds, event), ...]). Mirrors the training fraud patterns."""
        rng, pool = self.attack_rng, self.pool
        cand = rng.integers(0, pool.n, 500)               # newer accounts are likelier targets
        w = 1.0 / (pool.age_base[cand] + 30.0)
        card = int(rng.choice(cand, p=w / w.sum()))
        avg = float(pool.avg_amt[card])
        age = int(pool.age_base[card] + rng.integers(0, 30))
        hour = int(rng.integers(0, 6)) if rng.random() < 0.5 else int(rng.integers(6, 24))

        if kind == "card_testing":      # burst of tiny online txns, then 1-2 big ones
            n = int(rng.integers(5, 16))
            offs = start_in + np.cumsum(rng.exponential(interval_s, n))
            amount = rng.uniform(0.5, 9.99, n)
            k = int(rng.integers(1, 3))
            amount[-k:] = np.clip(avg * rng.uniform(3, 10, k), 20, 5000)
            online = np.ones(n, dtype=int)
            foreign = rng.random() < 0.4
            distance = rng.uniform(50, 6000, n)
        else:                           # takeover: few large, high-risk purchases
            n = int(rng.integers(2, 6))
            offs = start_in + np.cumsum(rng.exponential(interval_s * 5, n))
            amount = np.clip(avg * rng.uniform(3, 15, n), 30, 5000)
            online = (rng.random(n) < 0.8).astype(int)
            foreign = rng.random() < 0.5
            distance = rng.uniform(300, 8000, n)
        merch = rng.choice(10, n, p=FRAUD_MERCH_P)

        events = [
            (float(o), {"_idx": card, "card_id": card_id(card), "amount": round(float(a), 2),
                        "merchant_cat": int(m), "is_online": int(on), "distance_km": round(float(d), 2),
                        "is_foreign": int(foreign), "account_age_days": age, "hour": hour,
                        "label": 1, "pattern": kind})
            for o, a, m, on, d in zip(offs, amount, merch, online, distance)
        ]
        return card_id(card), events