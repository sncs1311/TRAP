"""Train XGBoost fraud model, evaluate (AUC-PR), build SHAP + PSI references."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shap
import xgboost as xgb
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

from app.schema import FEATURE_NAMES, PSI_FEATURES
from ml.data_gen import DAY_MS, generate_dataset

BASE = Path(__file__).resolve().parents[1]
ARTIFACTS = BASE / "artifacts"
DATA = BASE / "data"


def build_reference(x: np.ndarray, max_discrete: int = 12, n_bins: int = 10) -> dict:
    """Baseline distribution for PSI: categorical values or quantile bins."""
    uniq = np.unique(x)
    if len(uniq) <= max_discrete:
        counts = np.array([(x == u).sum() for u in uniq])
        return {"type": "categorical", "values": uniq.tolist(),
                "proportions": (counts / len(x)).tolist()}
    edges = np.unique(np.quantile(x, np.linspace(0, 1, n_bins + 1)[1:-1]))
    idx = np.searchsorted(edges, x, side="right")
    counts = np.bincount(idx, minlength=len(edges) + 1)
    return {"type": "numeric", "edges": edges.tolist(),
            "proportions": (counts / len(x)).tolist()}


def latency_smoke_test(model, explainer, X_np, n=300) -> dict:
    booster = model.get_booster()
    pred, shp = [], []
    for i in range(n):
        row = X_np[i:i + 1]
        t0 = time.perf_counter(); booster.inplace_predict(row)
        pred.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter(); explainer.shap_values(row)
        shp.append((time.perf_counter() - t0) * 1000)
    return {"predict_p50_ms": float(np.percentile(pred, 50)),
            "predict_p99_ms": float(np.percentile(pred, 99)),
            "shap_p50_ms": float(np.percentile(shp, 50)),
            "shap_p99_ms": float(np.percentile(shp, 99))}


def main(cards: int, seed: int) -> None:
    ARTIFACTS.mkdir(exist_ok=True); DATA.mkdir(exist_ok=True)

    print("[1/6] Generating synthetic dataset ...")
    df = generate_dataset(n_cards=cards, seed=seed)
    df.to_parquet(DATA / "transactions.parquet", index=False)
    print(f"      rows={len(df):,}  fraud={int(df.label.sum()):,} ({df.label.mean():.3%})")
    print("      fraud patterns:", df[df.label == 1].pattern.value_counts().to_dict())

    print("[2/6] Time-based split (train d0-19 / valid d20-24 / test d25-29) ...")
    day = df["ts_ms"] // DAY_MS
    tr, va, te = df[day < 20], df[(day >= 20) & (day < 25)], df[day >= 25]
    Xtr, ytr = tr[FEATURE_NAMES], tr["label"].to_numpy()
    Xva, yva = va[FEATURE_NAMES], va["label"].to_numpy()
    Xte, yte = te[FEATURE_NAMES], te["label"].to_numpy()
    print(f"      train={len(tr):,} valid={len(va):,} test={len(te):,} "
          f"(test fraud={int(yte.sum())})")

    print("[3/6] Training XGBoost ...")
    spw = float(np.sqrt((ytr == 0).sum() / max((ytr == 1).sum(), 1)))
    model = xgb.XGBClassifier(
        n_estimators=800, learning_rate=0.05, max_depth=5, min_child_weight=2,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
        scale_pos_weight=spw, tree_method="hist", eval_metric="aucpr",
        early_stopping_rounds=50, n_jobs=-1, random_state=seed,
    )
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    print(f"      best_iteration={model.best_iteration}  scale_pos_weight={spw:.1f}")

    print("[4/6] Evaluating ...")
    pva = model.predict_proba(Xva)[:, 1]
    pte = model.predict_proba(Xte)[:, 1]
    p, r, t = precision_recall_curve(yva, pva)
    f1 = 2 * p[:-1] * r[:-1] / (p[:-1] + r[:-1] + 1e-12)
    thr = float(t[np.argmax(f1)])                      # threshold chosen on VALID only

    pred = pte >= thr
    tp = int((pred & (yte == 1)).sum()); fp = int((pred & (yte == 0)).sum())
    fn = int((~pred & (yte == 1)).sum())
    metrics = {
        "auc_pr_test": float(average_precision_score(yte, pte)),
        "auc_roc_test": float(roc_auc_score(yte, pte)),
        "baseline_auc_pr": float(yte.mean()),
        "threshold": thr,
        "precision_test": tp / max(tp + fp, 1),
        "recall_test": tp / max(tp + fn, 1),
        "alert_rate_test": float(pred.mean()),
    }
    print(f"      AUC-PR (test) : {metrics['auc_pr_test']:.4f}   "
          f"(random baseline = {metrics['baseline_auc_pr']:.4f})")
    print(f"      AUC-ROC (test): {metrics['auc_roc_test']:.4f}")
    print(f"      @thr={thr:.3f} -> precision={metrics['precision_test']:.3f} "
          f"recall={metrics['recall_test']:.3f} alert_rate={metrics['alert_rate_test']:.3%}")

    print("[5/6] SHAP ...")
    explainer = shap.TreeExplainer(model)
    fraud_te = Xte[yte == 1]
    sample = np.concatenate([
        fraud_te.index.to_numpy()[:300],
        Xte[yte == 0].sample(1700, random_state=seed).index.to_numpy(),
    ])
    sv = explainer.shap_values(Xte.loc[sample])
    importance = np.abs(sv).mean(axis=0)
    order = np.argsort(importance)[::-1]
    print("      global importance (mean |SHAP|):")
    for i in order[:6]:
        print(f"        {FEATURE_NAMES[i]:<18} {importance[i]:.3f}")

    top = int(np.argmax(pte))
    row_sv = explainer.shap_values(Xte.iloc[[top]])[0]
    print(f"      example: top-scored test txn (score={pte[top]:.3f}, "
          f"label={yte[top]}, pattern={te.iloc[top].pattern})")
    for i in np.argsort(np.abs(row_sv))[::-1][:4]:
        print(f"        {FEATURE_NAMES[i]:<18} value={Xte.iloc[top, i]:>10.2f}  shap={row_sv[i]:+.3f}")

    lat = latency_smoke_test(model, explainer, Xte.to_numpy(np.float32))
    print("      latency smoke test (single row, ms): "
          + "  ".join(f"{k}={v:.2f}" for k, v in lat.items()))

    print("[6/6] Saving artifacts ...")
    booster = model.get_booster()[: model.best_iteration + 1]   # drop early-stopping tail trees
    booster.save_model(str(ARTIFACTS / "model.json"))
    ref_df = tr.copy()
    psi_reference = {f: build_reference(ref_df[f].to_numpy(np.float64)) for f in PSI_FEATURES}
    psi_reference["score"] = build_reference(pva.astype(np.float64))
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "xgboost_version": xgb.__version__,
        "feature_names": FEATURE_NAMES,
        "threshold": thr,
        "metrics": metrics,
        "latency_smoke_ms": lat,
        "n_train": len(tr), "n_valid": len(va), "n_test": len(te),
        "fraud_rate": float(df.label.mean()),
        "shap_global_importance": {FEATURE_NAMES[i]: float(importance[i]) for i in order},
        "psi_reference": psi_reference,
    }
    (ARTIFACTS / "metadata.json").write_text(json.dumps(meta, indent=2))

    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    pt, rt, _ = precision_recall_curve(yte, pte)
    ax[0].plot(rt, pt); ax[0].axhline(yte.mean(), ls="--", c="gray")
    ax[0].set(title=f"PR curve (test) AUC-PR={metrics['auc_pr_test']:.3f}",
              xlabel="Recall", ylabel="Precision")
    ax[1].barh([FEATURE_NAMES[i] for i in order[::-1]], importance[order[::-1]])
    ax[1].set(title="Mean |SHAP| (global importance)")
    fig.tight_layout(); fig.savefig(ARTIFACTS / "training_report.png", dpi=130)
    print(f"      wrote {ARTIFACTS}/model.json, metadata.json, training_report.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", type=int, default=15_000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    main(a.cards, a.seed)