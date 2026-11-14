"""Training-serving parity: Redis online features must equal offline training features."""
import numpy as np
import pandas as pd
import pytest
import redis
from sklearn.metrics import average_precision_score

from app.config import settings
from app.events import Transaction
from app.features import FeatureExtractor
from app.model import FraudModel
from app.schema import FEATURE_NAMES

PARQUET = settings.model_path.parents[1] / "data" / "transactions.parquet"
TEST_REDIS = "redis://localhost:6379/15"      # isolated DB, flushed by the test


@pytest.fixture(scope="module")
def df():
    if not PARQUET.exists():
        pytest.skip("run `python -m ml.train` first")
    return pd.read_parquet(PARQUET)


def test_online_features_match_offline(df):
    r = redis.Redis.from_url(TEST_REDIS, decode_responses=True)
    r.flushdb()
    rng = np.random.default_rng(0)
    fraud_cards = df.loc[df.label == 1, "card_id"].unique()[:150]
    other_cards = rng.choice(df["card_id"].unique(), 150, replace=False)
    sub = df[df.card_id.isin(np.concatenate([fraud_cards, other_cards]))]
    sub = sub.sort_values("ts_ms", kind="mergesort")      # replay in time order

    ext = FeatureExtractor(r)
    recs = sub[["txn_id", "card_id", "ts_ms", "amount", "merchant_cat", "is_online",
                "distance_km", "is_foreign", "account_age_days"]].to_dict("records")
    online = []
    for i in range(0, len(recs), 64):                      # also exercises pipelining
        batch = [Transaction(txn_id=str(x["txn_id"]), card_id=str(x["card_id"]),
                             ts_ms=int(x["ts_ms"]), amount=float(x["amount"]),
                             merchant_cat=int(x["merchant_cat"]), is_online=int(x["is_online"]),
                             distance_km=float(x["distance_km"]), is_foreign=int(x["is_foreign"]),
                             account_age_days=float(x["account_age_days"]))
                 for x in recs[i:i + 64]]
        online.append(ext.extract_batch(batch))
    online = np.vstack(online)
    offline = sub[FEATURE_NAMES].to_numpy(dtype=float)

    ok = np.isclose(online, offline, rtol=1e-6, atol=1e-6).all(axis=1)
    print(f"\nrows={len(ok):,}  exact-match rows={ok.mean():.4%}")
    if (~ok).any():
        diff = np.abs(online - offline)[~ok].max(axis=0)
        print("max abs diff on mismatching rows:", dict(zip(FEATURE_NAMES, diff.round(4))))
    r.flushdb()
    assert ok.mean() >= 0.999      # allow rare same-millisecond ties


def test_model_reproduces_training_auc(df):
    model = FraudModel(settings.model_path, settings.meta_path)
    te = df[df.ts_ms // 86_400_000 >= 25]
    p = model.predict(te[FEATURE_NAMES].to_numpy(np.float32))
    ap = average_precision_score(te["label"], p)
    print(f"\nserved AUC-PR={ap:.4f}  trained AUC-PR={model.meta['metrics']['auc_pr_test']:.4f}")
    assert abs(ap - model.meta["metrics"]["auc_pr_test"]) < 0.01