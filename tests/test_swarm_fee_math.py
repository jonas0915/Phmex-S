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


# ---------------------------------------------------------------------------
# max_concurrent (2026-09-21, after the cascade_v2 paper kill): the portfolio cap that
# guarantees one simultaneous cluster of stops cannot alone breach the dollar kill cap.
# ---------------------------------------------------------------------------

def test_max_concurrent_sl150_at_200_notional_is_3():
    # stop_loss_usd = 200 * (150 + 11.5) / 1e4 = 3.23; floor(10 / 3.23) = 3
    assert fm.max_concurrent(150) == 3
    assert isinstance(fm.max_concurrent(150), int)


def test_max_concurrent_cluster_of_stops_never_breaches_cap():
    for sl in (25, 60, 100, 150, 300):
        k = fm.max_concurrent(sl)
        stop_usd = fm.position_notional() * (sl + fm.C_BPS) / 1e4
        assert k >= 1 and k * stop_usd <= 10.0 < (k + 1) * stop_usd


def test_max_concurrent_floors_at_one_when_a_single_stop_exceeds_the_cap():
    assert fm.max_concurrent(1000) == 1          # one $202 stop already > $10
    assert fm.max_concurrent(150, notional_usd=2000.0) == 1


def test_max_concurrent_scales_with_cap_and_cost():
    assert fm.max_concurrent(150, kill_net_usd=20.0) == 6
    assert fm.max_concurrent(150, cost_bps=0.0) == 3       # 10 / 3.00 = 3.33 -> 3
    assert fm.max_concurrent(100, cost_bps=0.0) == 5       # 10 / 2.00 = 5


def test_max_concurrent_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        fm.max_concurrent(0)
    with pytest.raises(ValueError):
        fm.max_concurrent(150, kill_net_usd=0)
