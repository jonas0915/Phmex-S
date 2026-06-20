"""TDD for scripts/st2_lab/features.py — causal feature engineering.

Honesty invariant under test: every engineered feature at index i is computed from
ONLY recs[:i+1] (no lookahead). A feature that peeks at future snapshots would leak
the label and manufacture an artifact — exactly the failure mode the lab exists to
avoid. test_no_lookahead_causality is the load-bearing test here.
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import features as F  # noqa: E402


def _rec(ts, price, imb=0.4, br=0.7, tc=10, cvd=0.0, ltb=0.0, spread=0.05, hour=12):
    return {"ts": ts, "symbol": "X", "price": float(price), "imbalance": float(imb),
            "spread_pct": float(spread), "buy_ratio": float(br), "trade_count": int(tc),
            "cvd_slope": float(cvd), "large_trade_bias": float(ltb),
            "divergence_bullish": False, "divergence_bearish": False, "hour": hour}


def test_feature_names_nonempty():
    names = F.feature_names()
    assert isinstance(names, tuple)
    assert len(names) > 0


def test_features_added_to_each_record_passthrough_preserved():
    recs = [_rec(0, 100), _rec(10, 101), _rec(20, 102)]
    out = F.compute_features(recs, lookback=2)
    assert len(out) == 3
    for o in out:
        for k in F.feature_names():
            assert k in o, f"missing engineered feature {k}"
        # raw passthrough fields survive
        assert "price" in o and "imbalance" in o and "ts" in o


def test_imbalance_delta():
    recs = [_rec(0, 100, imb=0.3), _rec(10, 101, imb=0.5)]
    out = F.compute_features(recs, lookback=2)
    assert out[0]["imbalance_delta"] == 0.0
    assert abs(out[1]["imbalance_delta"] - 0.2) < 1e-9


def test_cvd_accel():
    recs = [_rec(0, 100, cvd=1.0), _rec(10, 101, cvd=1.5)]
    out = F.compute_features(recs, lookback=2)
    assert out[0]["cvd_accel"] == 0.0
    assert abs(out[1]["cvd_accel"] - 0.5) < 1e-9


def test_buy_ratio_delta():
    recs = [_rec(0, 100, br=0.6), _rec(10, 101, br=0.75)]
    out = F.compute_features(recs, lookback=2)
    assert out[0]["buy_ratio_delta"] == 0.0
    assert abs(out[1]["buy_ratio_delta"] - 0.15) < 1e-9


def test_price_momentum_insufficient_history_is_zero():
    recs = [_rec(0, 100), _rec(10, 110)]
    out = F.compute_features(recs, lookback=3)
    assert out[1]["price_mom"] == 0.0   # i=1 < lookback=3 -> no full window


def test_price_momentum_value():
    recs = [_rec(t * 10, 100 + t) for t in range(4)]  # prices 100,101,102,103
    out = F.compute_features(recs, lookback=2)
    assert abs(out[2]["price_mom"] - (102 - 100) / 100) < 1e-9  # 0.02
    assert abs(out[3]["price_mom"] - (103 - 101) / 101) < 1e-9


def test_imb_mean_trailing():
    recs = [_rec(0, 100, imb=0.4), _rec(10, 100, imb=0.6), _rec(20, 100, imb=0.5)]
    out = F.compute_features(recs, lookback=2)
    assert abs(out[0]["imb_mean"] - 0.4) < 1e-9
    assert abs(out[1]["imb_mean"] - 0.5) < 1e-9          # mean(0.4,0.6)
    assert abs(out[2]["imb_mean"] - 0.5) < 1e-9          # mean(0.4,0.6,0.5)


def test_spread_regime_neutral_at_start():
    recs = [_rec(0, 100, spread=0.05)]
    out = F.compute_features(recs, lookback=2)
    assert abs(out[0]["spread_regime"] - 1.0) < 1e-6     # spread / its own median


def test_spread_regime_elevated():
    recs = [_rec(0, 100, spread=0.05), _rec(10, 100, spread=0.05), _rec(20, 100, spread=0.15)]
    out = F.compute_features(recs, lookback=2)
    assert abs(out[2]["spread_regime"] - 3.0) < 1e-6     # 0.15 / median(0.05,0.05,0.15)=0.05


def test_realized_vol_zero_on_flat_prices():
    recs = [_rec(t * 10, 100) for t in range(5)]
    out = F.compute_features(recs, lookback=4)
    assert out[-1]["realized_vol"] == 0.0


def test_realized_vol_positive_on_moves():
    recs = [_rec(0, 100), _rec(10, 101), _rec(20, 100), _rec(30, 101)]
    out = F.compute_features(recs, lookback=4)
    assert out[-1]["realized_vol"] > 0.0


def test_no_lookahead_causality():
    recs = [_rec(t * 10, 100 + (t % 3), imb=0.3 + 0.01 * t, cvd=0.1 * t,
                 spread=0.05 + 0.001 * t, br=0.6 + 0.005 * t) for t in range(10)]
    full = F.compute_features(recs, lookback=3)
    for i in range(len(recs)):
        prefix = F.compute_features(recs[:i + 1], lookback=3)
        assert prefix[-1] == full[i], f"feature at i={i} depends on future rows"


def test_empty_input():
    assert F.compute_features([]) == []


def test_deterministic():
    recs = [_rec(t * 10, 100 + t, imb=0.3 + 0.02 * t) for t in range(6)]
    assert F.compute_features(recs, lookback=3) == F.compute_features(recs, lookback=3)
