"""Ablation study: leakage (account_age_days) and generator-shortcut (distance_km) checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, precision_recall_curve

from app.schema import FEATURE_NAMES
from ml.data_gen import DAY_MS, generate_dataset

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "transactions.parquet"
OUT = BASE / "artifacts" / "ablation.json"

FEATURE_SETS = {
    "all": FEATURE_NAMES,
    "-account_age_days": [f for f in FEATURE_NAMES if f != "account_age_days"],
    "-distance_km": [f for f in FEATURE_NAMES if f != "distance_km"],
    "-both": [f for f in FEATURE_NAMES if f not in ("account_age_days", "distance_km")],
}


def time_split(df: pd.DataFrame):
    day = df["ts_ms"] // DAY_MS
    return df[day < 20], df[(day >= 20) & (day < 25)], df[day >= 25]


def strict_split(df: pd.DataFrame, seed: int, frac: float = 0.3):
    """Held-out cards never appear in train/valid; test = future days on those cards."""
    rng = np.random.default_rng(seed)
    cards = df["card_id"].unique()
    held = rng.choice(cards, int(len(cards) * frac), replace=False)
    is_held = df["card_id"].isin(held)
    day = df["ts_ms"] // DAY_MS
    tr = df[~is_held & (day < 20)]
    va = df[~is_held & (day >= 20) & (day < 25)]
    te = df[is_held & (day >= 25)]
    return tr, va, te


def fit_eval(tr, va, te, feats, seed) -> dict:
    ytr, yva, yte = tr["label"].to_numpy(), va["label"].to_numpy(), te["label"].to_numpy()
    spw = float(np.sqrt((ytr == 0).sum() / max((ytr == 1).sum(), 1)))
    model = xgb.XGBClassifier(
        n_estimators=800, learning_rate=0.05, max_depth=5, min_child_weight=2,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
        scale_pos_weight=spw, tree_method="hist", eval_metric="aucpr",
        early_stopping_rounds=50, n_jobs=-1, random_state=seed,
    )
    model.fit(tr[feats], ytr, eval_set=[(va[feats], yva)], verbose=False)
    pva = model.predict_proba(va[feats])[:, 1]
    pte = model.predict_proba(te[feats])[:, 1]

    p, r, t = precision_recall_curve(yva, pva)
    f1 = 2 * p[:-1] * r[:-1] / (p[:-1] + r[:-1] + 1e-12)
    thr = float(t[np.argmax(f1)])                  # threshold chosen on valid only
    pred = pte >= thr
    tp = int((pred & (yte == 1)).sum())
    fp = int((pred & (yte == 0)).sum())
    fn = int((~pred & (yte == 1)).sum())
    return {
        "auc_pr": float(average_precision_score(yte, pte)),
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
        "n_test_fraud": int(yte.sum()),
    }


def main(seed: int, repeats: int) -> None:
    if DATA.exists():
        df = pd.read_parquet(DATA)
    else:
        df = generate_dataset(seed=seed)
    print(f"rows={len(df):,} fraud_rate={df.label.mean():.3%}\n")

    results = {}
    for name, feats in FEATURE_SETS.items():
        print(f"== {name} ({len(feats)} features)")
        tr, va, te = time_split(df)
        results[name] = {"time_split": fit_eval(tr, va, te, feats, seed)}

        runs = []
        for k in range(repeats):
            tr, va, te = strict_split(df, seed=seed + k)
            runs.append(fit_eval(tr, va, te, feats, seed))
        results[name]["strict_split"] = {
            m: float(np.mean([r[m] for r in runs])) for m in ("auc_pr", "precision", "recall")
        }
        results[name]["strict_split"]["auc_pr_std"] = float(np.std([r["auc_pr"] for r in runs]))

    rows = []
    for name, res in results.items():
        t, s = res["time_split"], res["strict_split"]
        rows.append({
            "feature_set": name,
            "AUC-PR time": round(t["auc_pr"], 3),
            "AUC-PR strict": round(s["auc_pr"], 3),
            "strict std": round(s["auc_pr_std"], 3),
            "P strict": round(s["precision"], 3),
            "R strict": round(s["recall"], 3),
        })
    print("\n" + pd.DataFrame(rows).to_string(index=False))

    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    main(a.seed, a.repeats)