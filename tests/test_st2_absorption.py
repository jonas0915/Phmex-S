"""Tests for ST2.0 book×tape absorption short (2026-06-13)."""
import pandas as pd
import pytest
from strategies import st2_absorption, Signal, STRATEGIES, ST2_IMB_MIN, ST2_BR_MIN, ST2_MIN_TRADES

DF = pd.DataFrame({"close": [1.0] * 30})


def test_registered():
    assert STRATEGIES.get("ST2.0") is st2_absorption


def test_fires_on_absorption():
    s = st2_absorption(DF, {"imbalance": 0.35}, {"buy_ratio": 0.65, "trade_count": 40})
    assert s.signal == Signal.SELL
    assert s.strength >= 0.80  # must clear the slot's 0.80 strength gate
    assert "ST2.0" in s.reason


def test_exactly_at_thresholds_fires():
    s = st2_absorption(DF, {"imbalance": ST2_IMB_MIN},
                       {"buy_ratio": ST2_BR_MIN, "trade_count": ST2_MIN_TRADES})
    assert s.signal == Signal.SELL


@pytest.mark.parametrize("ob,flow", [
    ({"imbalance": 0.20}, {"buy_ratio": 0.70, "trade_count": 40}),   # book not bid-heavy enough
    ({"imbalance": 0.40}, {"buy_ratio": 0.50, "trade_count": 40}),   # tape not buying enough
    ({"imbalance": 0.40}, {"buy_ratio": 0.70, "trade_count": 5}),    # tape too thin
])
def test_holds_when_condition_unmet(ob, flow):
    assert st2_absorption(DF, ob, flow).signal == Signal.HOLD


def test_holds_on_missing_data():
    assert st2_absorption(DF, None, {"buy_ratio": 0.7, "trade_count": 40}).signal == Signal.HOLD
    assert st2_absorption(DF, {"imbalance": 0.4}, None).signal == Signal.HOLD


def test_is_short_only():
    # ST2.0 never goes long — it only fades bid-heavy-being-bought (short)
    for imb in (-0.5, -0.3, 0.0, 0.3, 0.5):
        for br in (0.0, 0.3, 0.6, 0.9):
            s = st2_absorption(DF, {"imbalance": imb}, {"buy_ratio": br, "trade_count": 40})
            assert s.signal in (Signal.SELL, Signal.HOLD)
            assert s.signal != Signal.BUY
