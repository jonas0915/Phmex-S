"""fee_math: the desk's single source of break-even arithmetic (spec §3)."""
import math
import pytest

from research.swarm.lib import fee_math as fm


@pytest.mark.parametrize("symbol,expected", [
    ("BTC", "BTC"),
    ("BTC_USDT_USDT", "BTC"),
    ("BTC/USDT:USDT", "BTC"),
    ("btc/usdt", "BTC"),
])
def test_base_symbol_normalizes_forms(symbol, expected):
    assert fm.base_symbol(symbol) == expected


@pytest.mark.parametrize("x,expected", [(25, 0.730), (50, 0.615), (100, 0.558), (300, 0.519), (1000, 0.506)])
def test_p_star_matches_spec_table(x, expected):
    # Table values are 3-dp with half-up rounding; use approx with 1e-3 tolerance
    # to handle IEEE 754 float precision (e.g., 0.5575 becomes 0.55749999...)
    assert fm.p_star(x) == pytest.approx(expected, abs=1e-3)


def test_p_star_rejects_nonpositive_target():
    with pytest.raises(ValueError):
        fm.p_star(0)


def test_net_bps_subtracts_full_round_trip_cost():
    assert fm.net_bps(20.0) == pytest.approx(8.5)
    assert fm.C_BPS == pytest.approx(fm.FEES_RT_BPS + fm.ADVERSE_BPS)


def test_time_to_verdict_weeks():
    assert fm.time_to_verdict_weeks(10.0) == pytest.approx(5.0)
    assert math.isinf(fm.time_to_verdict_weeks(0.0))


def test_position_notional_default_is_200_dollars():
    # $200 capital, 10% margin at risk per position, 10x → $200 notional
    assert fm.position_notional() == pytest.approx(200.0)


def test_lot_check_btc_one_lot_at_200_notional():
    r = fm.lot_check("BTC", 200.0)
    assert r == {"ok": True, "lots": 2, "lot_usd": 77.74}


def test_lot_check_btc_fails_below_one_lot():
    r = fm.lot_check("BTC", 50.0)
    assert r["ok"] is False and r["lots"] == 0


def test_lot_check_unknown_symbol_uses_min_order_value():
    r = fm.lot_check("ZZZ", 5.0)
    assert r["ok"] is True and r["lot_usd"] is None
