"""Synthetic historical transaction generator (~0.5% fraud, 30 days)."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from app.schema import WINDOWS_MS

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
KEY_STRIDE = 10_000_000_000  # > max ts_ms so (card, ts) packs into one sortable int64

HOUR_W = np.array([0.5, 0.3, 0.2, 0.2, 0.3, 0.6,            # 00-05
                   1.5, 2.5, 3.5,                            # 06-08
                   4, 4.5, 5, 5.5, 5.5, 5, 4.5, 4.5, 4.5,    # 09-17
                   5, 5, 4, 3,                               # 18-21
                   1.5, 0.8])                                # 22-23
HOUR_P = HOUR_W / HOUR_W.sum()

LEGIT_MERCH_P = np.array([.25, .20, .12, .18, .04, .08, .06, .04, .02, .01])
FRAUD_MERCH_P = np.array([.02, .02, .02, .10, .08, .06, .02, .30, .20, .18])


def _legit_rows(rng, card_id, ts_ms, avg_amt, age_base) -> pd.DataFrame:
    n = len(card_id)
    amount = np.clip(rng.lognormal(np.log(avg_amt[card_id]), 0.7), 0.5, 5000)
    is_foreign = rng.random(n) < 0.02
    distance = rng.exponential(8.0, n)
    travelling = (rng.random(n) < 0.03) & ~is_foreign
    distance = np.where(travelling, rng.uniform(100, 2000, n), distance)
    distance = np.where(is_foreign, rng.uniform(500, 8000, n), distance)
    return pd.DataFrame({
        "card_id": card_id,
        "ts_ms": ts_ms,
        "amount": amount,
        "merchant_cat": rng.choice(10, n, p=LEGIT_MERCH_P),
        "is_online": (rng.random(n) < 0.30).astype(np.int8),
        "distance_km": distance,
        "is_foreign": is_foreign.astype(np.int8),
        "account_age_days": age_base[card_id] + ts_ms // DAY_MS,
        "label": 0,
        "pattern": "legit",
    })


def _fraud_events(rng, n_target, n_cards, avg_amt, age_base, days) -> pd.DataFrame:
    # Newer accounts are mildly more likely to be targeted
    card_p = 1.0 / (age_base + 30.0)
    card_p /= card_p.sum()
    frames, total = [], 0
    while total < n_target:
        card = int(rng.choice(n_cards, p=card_p))
        avg = avg_amt[card]
        kind = rng.choice(["testing", "takeover", "subtle"], p=[0.40, 0.40, 0.20])
        hour = rng.integers(0, 6) if rng.random() < 0.5 else rng.integers(6, 24)
        start = int(rng.integers(2, days)) * DAY_MS + int(hour) * HOUR_MS + int(rng.integers(0, HOUR_MS))

        if kind == "testing":      # card-testing: burst of tiny online txns, then a big one
            n = int(rng.integers(5, 16))
            ts = start + np.cumsum(rng.exponential(12_000, n)).astype(np.int64)
            amount = rng.uniform(0.5, 9.99, n)
            k = int(rng.integers(1, 3))
            amount[-k:] = np.clip(avg * rng.uniform(3, 10, k), 20, 5000)
            online = np.ones(n, dtype=np.int8)
            foreign = np.full(n, rng.random() < 0.4)
            distance = rng.uniform(50, 6000, n)
            merch = rng.choice(10, n, p=FRAUD_MERCH_P)
        elif kind == "takeover":   # stolen card: few large, high-risk purchases
            n = int(rng.integers(2, 6))
            ts = start + np.cumsum(rng.exponential(300_000, n)).astype(np.int64)
            amount = np.clip(avg * rng.uniform(3, 15, n), 30, 5000)
            online = (rng.random(n) < 0.8).astype(np.int8)
            foreign = np.full(n, rng.random() < 0.5)
            distance = rng.uniform(300, 8000, n)
            merch = rng.choice(10, n, p=FRAUD_MERCH_P)
        else:                      # subtle: looks almost normal (caps achievable AUC-PR)
            n = int(rng.integers(1, 3))
            ts = start + np.cumsum(rng.exponential(900_000, n)).astype(np.int64)
            amount = np.clip(avg * rng.uniform(1, 3, n), 5, 5000)
            online = (rng.random(n) < 0.5).astype(np.int8)
            foreign = np.zeros(n, dtype=bool)
            distance = rng.exponential(15.0, n)
            merch = rng.choice(10, n, p=0.5 * LEGIT_MERCH_P + 0.5 * FRAUD_MERCH_P)

        ts = np.minimum(ts, days * DAY_MS - 1)
        frames.append(pd.DataFrame({
            "card_id": np.full(n, card), "ts_ms": ts, "amount": amount,
            "merchant_cat": merch, "is_online": online,
            "distance_km": distance, "is_foreign": foreign.astype(np.int8),
            "account_age_days": age_base[card] + ts // DAY_MS,
            "label": 1, "pattern": kind,
        }))
        total += n
    return pd.concat(frames, ignore_index=True)


def add_velocity_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute window + history features following app/schema.py's contract."""
    df = df.sort_values(["card_id", "ts_ms"], kind="mergesort").reset_index(drop=True)
    key = df["card_id"].to_numpy(np.int64) * KEY_STRIDE + df["ts_ms"].to_numpy(np.int64)
    amt = df["amount"].to_numpy(np.float64)
    cs = np.concatenate([[0.0], np.cumsum(amt)])

    right = np.searchsorted(key, key, side="right")          # includes current txn
    spend_1h = None
    for name, w in WINDOWS_MS.items():
        left = np.searchsorted(key, key - w, side="right")   # window is (t-w, t]
        df[f"txn_count_{name}"] = right - left
        if name == "1h":
            spend_1h = cs[right] - cs[left]

    g = df.groupby("card_id")["amount"]
    prev_cnt = g.cumcount().to_numpy()
    prev_sum = (g.cumsum() - df["amount"]).to_numpy()
    hist_mean = np.where(prev_cnt > 0, prev_sum / np.maximum(prev_cnt, 1), amt)
    df["amount_ratio"] = amt / hist_mean
    df["spend_ratio_1h"] = spend_1h / hist_mean
    return df


def generate_dataset(n_cards=15_000, days=30, fraud_rate=0.005, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    avg_amt = np.exp(rng.normal(np.log(40.0), 0.6, n_cards))
    age_base = rng.integers(30, 3650, n_cards)

    # Baseline legit traffic: per-card Poisson rate, daytime-weighted hours
    lam = rng.gamma(2.0, 0.25, n_cards)                      # ~0.5 txns/day/card
    per_card = rng.poisson(lam * days)
    card_id = np.repeat(np.arange(n_cards), per_card)
    n = len(card_id)
    ts = (rng.integers(0, days, n) * DAY_MS
          + rng.choice(24, n, p=HOUR_P) * HOUR_MS
          + rng.integers(0, HOUR_MS, n))

    # "Shopping sessions": ~8% of txns spawn 1-3 follow-ups within 20 min
    idx = np.where(rng.random(n) < 0.08)[0]
    rep = rng.integers(1, 4, len(idx))
    fu_card = np.repeat(card_id[idx], rep)
    fu_ts = np.minimum(np.repeat(ts[idx], rep) + rng.integers(30_000, 1_200_000, rep.sum()),
                       days * DAY_MS - 1)
    legit = _legit_rows(rng, np.concatenate([card_id, fu_card]),
                        np.concatenate([ts, fu_ts]), avg_amt, age_base)

    n_fraud = int(fraud_rate * len(legit) / (1 - fraud_rate))
    fraud = _fraud_events(rng, n_fraud, n_cards, avg_amt, age_base, days)

    df = pd.concat([legit, fraud], ignore_index=True)
    df = add_velocity_features(df)
    df["hour"] = (df["ts_ms"] // HOUR_MS) % 24
    df = df.sort_values("ts_ms").reset_index(drop=True)
    df.insert(0, "txn_id", np.arange(len(df)))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", type=int, default=15_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/transactions.parquet")
    a = ap.parse_args()
    d = generate_dataset(a.cards, seed=a.seed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(a.out, index=False)
    print(f"rows={len(d):,} fraud_rate={d.label.mean():.4%} -> {a.out}")