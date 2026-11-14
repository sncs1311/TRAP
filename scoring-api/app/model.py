"""Model wrapper: scoring, SHAP, and human-readable reason codes."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
import shap
import xgboost as xgb

from app.schema import FEATURE_NAMES, MERCHANT_CATEGORIES

MIN_REASON_SHAP = 0.25   # log-odds contribution needed to surface a reason

REASON_TEXT = {
    "amount": lambda v: f"Unusually large amount (${v:,.2f})",
    "hour": lambda v: f"Unusual time of day ({int(v):02d}:00)",
    "merchant_cat": lambda v: f"High-risk merchant category ({MERCHANT_CATEGORIES[int(v)].replace('_', ' ')})",
    "is_online": lambda v: "Online (card-not-present) purchase" if v else "In-person purchase pattern",
    "distance_km": lambda v: f"Transaction {v:,.0f} km from the cardholder's usual location",
    "is_foreign": lambda v: "Foreign transaction",
    "account_age_days": lambda v: f"Higher-risk account profile (account age {v:,.0f} days)",
    "txn_count_1m": lambda v: f"{int(v)} transactions in the last minute (rapid-fire velocity)",
    "txn_count_10m": lambda v: f"{int(v)} transactions in the last 10 minutes",
    "txn_count_1h": lambda v: f"{int(v)} transactions in the last hour",
    "amount_ratio": lambda v: f"Amount is {v:.1f}x this card's typical spend",
    "spend_ratio_1h": lambda v: f"Spent {v:.1f}x the card's typical transaction amount in the last hour",
}


class FraudModel:
    def __init__(self, model_path: Path, meta_path: Path):
        self.booster = xgb.Booster()
        self.booster.load_model(str(model_path))
        self.meta = json.loads(Path(meta_path).read_text())
        assert self.meta["feature_names"] == FEATURE_NAMES, "feature contract mismatch"
        self.threshold: float = self.meta["threshold"]
        self.version: str = self.meta["trained_at"]
        self.explainer = shap.TreeExplainer(self.booster)
        self.base_value = float(np.ravel(self.explainer.expected_value)[0])
        self._lock = threading.Lock()
        warm = np.zeros((1, len(FEATURE_NAMES)), dtype=np.float32)   # warm-up
        self.predict(warm)
        self.shap_values(warm)

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        with self._lock:
            return self.booster.inplace_predict(X)

    def shap_values(self, X: np.ndarray) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        with self._lock:
            return np.asarray(self.explainer.shap_values(X))

    def explain(self, row: np.ndarray, sv: np.ndarray, top_k: int = 8, max_reasons: int = 4) -> dict:
        order = np.argsort(-np.abs(sv))
        contributions = [
            {"feature": FEATURE_NAMES[i], "value": float(row[i]), "shap": round(float(sv[i]), 4)}
            for i in order[:top_k]
        ]
        pos = [i for i in order if sv[i] >= MIN_REASON_SHAP][:max_reasons]
        if not pos:                                    # fall back to the strongest positive driver
            pos = [i for i in order if sv[i] > 0][:1]
        reasons = [
            {"feature": FEATURE_NAMES[i], "text": REASON_TEXT[FEATURE_NAMES[i]](row[i]),
             "shap": round(float(sv[i]), 4)}
            for i in pos
        ]
        return {"contributions": contributions, "reasons": reasons}