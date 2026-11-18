"""Calibration: simulator baseline must look like training; drift knobs must move PSI."""
import json
from pathlib import Path

import numpy as np
import pytest

from app.generator import ZERO_DRIFT, CardPool, EventFactory

META = Path(__file__).resolve().parents[2] / "scoring-api" / "artifacts" / "metadata.json"
STATIC = ["amount", "distance_km", "account_age_days", "hour", "merchant_cat", "is_online"]
KNOB_TO_FEATURE = {"amount": "amount", "distance": "distance_km", "online": "is_online", "night": "hour"}


def psi(exp, act, eps=1e-4):
    e, a = np.clip(exp, eps, None), np.clip(act, eps, None)
    return float(np.sum((a - e) * np.log(a / e)))


def psi_vs_reference(spec, x):
    x = np.asarray(x, dtype=float)
    if spec["type"] == "categorical":
        vals = np.array(spec["values"], dtype=float)
        counts = np.array([(x == v).sum() for v in vals] + [(~np.isin(x, vals)).sum()], dtype=float)
        exp = np.array(spec["proportions"] + [0.0])
    else:
        edges = np.array(spec["edges"])
        idx = np.searchsorted(edges, x, side="right")
        counts = np.bincount(idx, minlength=len(edges) + 1).astype(float)
        exp = np.array(spec["proportions"])
    return psi(exp, counts / counts.sum())


@pytest.fixture(scope="module")
def ref():
    if not META.exists():
        pytest.skip("train the model first (scoring-api: python -m ml.train)")
    return json.loads(META.read_text())["psi_reference"]


@pytest.fixture(scope="module")
def fx():
    pool = CardPool(300_000, seed=1)
    return EventFactory(pool, 5, 6), pool


def sample(fx, drift, n=30_000):
    factory, pool = fx
    ev = factory.legit(pool.sample(n), drift)
    return {f: np.array([e[f] for e in ev], dtype=float) for f in STATIC}


def test_baseline_matches_training(fx, ref):
    cols = sample(fx, ZERO_DRIFT)
    print()
    for f in STATIC:
        v = psi_vs_reference(ref[f], cols[f])
        print(f"  baseline PSI {f:<18} {v:.4f}")
        assert v < 0.05, f"{f} baseline PSI {v:.3f} too high: generator not matching training"


@pytest.mark.parametrize("knob,feature", KNOB_TO_FEATURE.items())
def test_drift_knob_moves_psi(fx, ref, knob, feature):
    drift = {**ZERO_DRIFT, knob: 1.0}
    v = psi_vs_reference(ref[feature], sample(fx, drift)[feature])
    print(f"\n  {knob}=1.0 -> PSI({feature}) = {v:.3f}")
    assert v > 0.25


def test_attack_plan_shape(fx):
    factory, _ = fx
    cid, evs = factory.plan_attack("card_testing", 0.0, 6.0)
    assert 5 <= len(evs) <= 15
    assert all(e["label"] == 1 and e["card_id"] == cid for _, e in evs)
    assert evs[-1][1]["amount"] >= 20 and evs[0][1]["amount"] < 10
    offsets = [o for o, _ in evs]
    assert offsets == sorted(offsets)