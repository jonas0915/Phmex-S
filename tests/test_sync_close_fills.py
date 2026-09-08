"""exchange_close fee capture (2026-09-07): sum ALL reduce-side post-entry fills,
skip Phemex funding-settlement rows, VWAP the exit price; return fee 0.0 when
nothing matched so close_position's estimator floor + fees_pending applies."""
from types import SimpleNamespace

import pytest

from bot import _close_fills_summary


def _tr(ts_s, side, price, amount, fee_cost, trade_type="1"):
    return {"timestamp": int(ts_s * 1000), "side": side, "price": price, "amount": amount,
            "fee": {"cost": fee_cost}, "fees": [{"cost": fee_cost}],
            "info": {"tradeType": trade_type, "action": "13" if trade_type == "4" else "1"}}


def _pos(side="short", opened_at=1000.0):
    return SimpleNamespace(side=side, opened_at=opened_at)


def test_sums_all_reduce_fills_and_vwaps_price():
    recent = [
        _tr(999, "sell", 100.0, 1.0, 0.01),       # entry (before opened_at) — ignored
        _tr(2000, "buy", 101.0, 0.6, 0.036),      # partial close
        _tr(2001, "buy", 103.0, 0.4, 0.025),      # rest of close
    ]
    px, fee = _close_fills_summary(recent, _pos())
    assert fee == pytest.approx(0.061)
    assert px == pytest.approx((101.0 * 0.6 + 103.0 * 0.4) / 1.0)


def test_skips_funding_rows_and_same_side_reentry():
    recent = [
        _tr(1500, "sell", 100.0, 1.0, -0.0017, trade_type="4"),  # funding settlement
        _tr(1600, "sell", 100.0, 1.0, 0.015),                    # a NEW short entry (same side) — not a close
        _tr(2000, "buy", 102.0, 1.0, 0.06),
    ]
    px, fee = _close_fills_summary(recent, _pos())
    assert fee == pytest.approx(0.06) and px == 102.0


def test_no_close_fill_returns_none_and_zero_fee():
    recent = [_tr(999, "sell", 100.0, 1.0, 0.01)]
    assert _close_fills_summary(recent, _pos()) == (None, 0.0)
    assert _close_fills_summary([], _pos()) == (None, 0.0)


def test_fee_cost_none_falls_back_to_fees_list_and_zero():
    recent = [{"timestamp": 2_000_000, "side": "buy", "price": 5.0, "amount": 2.0,
               "fee": {"cost": None}, "fees": [{"cost": 0.004}], "info": {"tradeType": "1"}}]
    assert _close_fills_summary(recent, _pos()) == (5.0, pytest.approx(0.004))
    recent[0]["fees"] = []
    assert _close_fills_summary(recent, _pos()) == (5.0, 0.0)   # → estimator floor downstream
