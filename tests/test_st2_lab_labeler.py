"""TDD for scripts/st2_lab/labeler.py — adverse-fill-aware labeled dataset.

The core honesty property: an ST2.0 maker SHORT only becomes a labeled example if a
resting offer would actually have FILLED (an uptick lifts it within the window). A
signal where price drops away from the offer never fills and is DROPPED — it is NOT
counted as a free win. That favorable-but-unfilled case is exactly what the naive
100%-fill replay wrongly kept (sandbox +0.31 vs live -0.14). test_unfilled_signal_
is_dropped guards it.
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import labeler as L      # noqa: E402
from st2_lab import features as F      # noqa: E402

PARAMS = {"imb_min": 0.35, "br_min": 0.60, "min_trades": 8,
          "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6}
ADV1 = {"enabled": True, "fill_window_snaps": 1, "maker_edge_pct": 0.1}
ADV2 = {"enabled": True, "fill_window_snaps": 2, "maker_edge_pct": 0.1}


def _sig(ts, price):
    """A snapshot that PASSES ST2.0 base entry conditions."""
    return {"ts": ts, "symbol": "X", "price": float(price), "imbalance": 0.4,
            "spread_pct": 0.05, "buy_ratio": 0.7, "trade_count": 10,
            "cvd_slope": 0.0, "large_trade_bias": 0.0,
            "divergence_bullish": False, "divergence_bearish": False, "hour": 12}


def _filler(ts, price):
    """A price-action snapshot that does NOT pass entry conditions (low buy_ratio)."""
    r = _sig(ts, price)
    r.update({"imbalance": 0.1, "buy_ratio": 0.3, "trade_count": 2})
    return r


def test_unfilled_signal_is_dropped():
    # signal at 100; price drops away from the 100.1 offer for the whole window -> no fill
    by = {"X": [_sig(0, 100), _filler(10, 99.5), _filler(20, 99.0)]}
    res = L.label_dataset(by, PARAMS, ADV2)
    assert res["n_signals"] == 1
    assert res["n_filled"] == 0
    assert res["examples"] == []
    assert res["fill_rate"] == 0.0


def test_filled_signal_becomes_example_with_net():
    # signal at 100; next snap 100.2 lifts the 100.1 offer -> fill; then 98.0 hits TP
    by = {"X": [_sig(0, 100), _filler(10, 100.2), _filler(20, 98.0)]}
    res = L.label_dataset(by, PARAMS, ADV1)
    assert res["n_filled"] == 1
    ex = res["examples"][0]
    assert ex["filled"] is True and ex["tradeable"] is True
    assert ex["win"] is True
    assert abs(ex["net"] - 1.56) < 1e-6        # 0.016 move * 100 notional - 0.04 fee
    assert abs(ex["net_roi"] - 0.156) < 1e-6   # net / 10 margin
    assert ex["source"] == "sim" and ex["weight"] == 1.0


def test_examples_carry_engineered_features():
    by = {"X": [_sig(0, 100), _filler(10, 100.2), _filler(20, 98.0)]}
    ex = L.label_dataset(by, PARAMS, ADV1)["examples"][0]
    for k in F.feature_names():
        assert k in ex, f"labeled example missing engineered feature {k}"


def test_fill_rate_matches_adverse_params():
    # two independent signals: A fills (next snap lifts offer), B does not (price drops)
    by = {"X": [_sig(0, 100), _filler(10, 100.5),
                _sig(1000, 200), _filler(1010, 199)]}
    res = L.label_dataset(by, PARAMS, ADV1)   # window=1
    assert res["n_signals"] == 2
    assert res["n_filled"] == 1
    assert abs(res["fill_rate"] - 0.5) < 1e-9


def test_non_signal_snapshots_excluded():
    by = {"X": [_filler(0, 100), _filler(10, 101)]}
    res = L.label_dataset(by, PARAMS, ADV1)
    assert res["n_signals"] == 0
    assert res["examples"] == []


def test_real_trades_unioned_with_higher_weight():
    real = [{"imbalance": 0.4, "buy_ratio": 0.7, "trade_count": 10, "spread_pct": 0.05,
             "cvd_slope": 0.0, "large_trade_bias": 0.0, "divergence_bullish": False,
             "divergence_bearish": False, "hour": 12, "net": 2.0}]
    res = L.label_dataset({}, PARAMS, ADV1, real_records=real, real_weight=3.0)
    assert res["n_real"] == 1
    reals = [e for e in res["examples"] if e["source"] == "real"]
    assert len(reals) == 1
    r = reals[0]
    assert r["weight"] == 3.0
    assert r["filled"] is True
    assert abs(r["net"] - 2.0) < 1e-9
    assert abs(r["net_roi"] - 0.2) < 1e-9     # 2.0 / 10 margin
    assert r["win"] is True


def test_calibrate_picks_params_closest_to_target_fill_rate():
    # one signal; with edge 0.1% (offer 100.1) it never fills; with edge 0.0 it fills
    by = {"X": [_sig(0, 100), _filler(10, 100.05)]}
    grid = [{"fill_window_snaps": 1, "maker_edge_pct": 0.1},
            {"fill_window_snaps": 1, "maker_edge_pct": 0.0}]
    low = L.calibrate_adverse(by, PARAMS, target_fill_rate=0.2, grid=grid)
    assert low["maker_edge_pct"] == 0.1       # closest to the 0.0 fill rate
    assert low["enabled"] is True
    assert abs(low["sim_fill_rate"] - 0.0) < 1e-9
    high = L.calibrate_adverse(by, PARAMS, target_fill_rate=0.9, grid=grid)
    assert high["maker_edge_pct"] == 0.0      # closest to the 1.0 fill rate
    assert abs(high["sim_fill_rate"] - 1.0) < 1e-9


def test_empty_dataset():
    res = L.label_dataset({}, PARAMS, ADV1)
    assert res["n_signals"] == 0
    assert res["examples"] == []
    assert res["fill_rate"] == 0.0
    assert res["n_real"] == 0


def test_deterministic():
    by = {"X": [_sig(0, 100), _filler(10, 100.2), _filler(20, 98.0)]}
    assert L.label_dataset(by, PARAMS, ADV1) == L.label_dataset(by, PARAMS, ADV1)
