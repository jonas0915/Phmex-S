"""extract_order_fee must not record $0 when the exchange omits fee.cost.

Bug (project_bot_performance_audit_2026-06-29, r2_fee_research): 55-62% of live
trades logged fees_usdt=0 because Phemex market fills often return
fee={'cost': None, 'rate': 0.0006, ...}. The code only read fee['cost'] and
returned 0.0 — never computing cost from the rate the exchange DOES provide.
These tests pin the computed-fee fallback (rate x notional). Measurement-only:
no order placement / sizing / SL-TP behavior is involved.
"""

import pytest
from unittest.mock import Mock

from config import Config
from exchange import Exchange


@pytest.fixture(autouse=True)
def live_and_pinned_fees(monkeypatch):
    monkeypatch.setattr(Config, "MODE", "live")  # extract_order_fee no-ops unless live
    monkeypatch.setattr(Config, "TAKER_FEE_PERCENT", 0.06)
    monkeypatch.setattr(Config, "MAKER_FEE_PERCENT", 0.01)


def _ex():
    ex = Exchange.__new__(Exchange)  # skip __init__/API; extract_order_fee only needs self.client
    ex.client = Mock()               # fallbacks unused in these in-order cases
    return ex


def test_uses_explicit_cost_when_present():
    """Regression: an exchange-reported cost is used verbatim, not recomputed."""
    ex = _ex()
    order = {"id": "1", "symbol": "DOGE/USDT:USDT",
             "cost": 100.0, "fee": {"cost": 0.0123, "currency": "USDT"}}
    assert ex.extract_order_fee(order, "DOGE/USDT:USDT") == pytest.approx(0.0123)


def test_computes_fee_from_rate_when_cost_missing():
    """fee.cost=None but fee.rate present -> notional * rate (this is the bug)."""
    ex = _ex()
    order = {"id": "2", "symbol": "DOGE/USDT:USDT", "cost": 100.0,
             "fee": {"cost": None, "rate": 0.0006, "currency": "USDT"}}
    # 100 notional * 0.0006 = 0.06, NOT 0.0
    assert ex.extract_order_fee(order, "DOGE/USDT:USDT") == pytest.approx(0.06)


def test_computes_fee_from_takerOrMaker_when_no_rate():
    """No cost and no rate, but takerOrMaker='taker' -> notional * TAKER_FEE."""
    ex = _ex()
    order = {"id": "3", "symbol": "DOGE/USDT:USDT", "cost": 100.0,
             "takerOrMaker": "taker", "fee": {"cost": None, "currency": "USDT"}}
    assert ex.extract_order_fee(order, "DOGE/USDT:USDT") == pytest.approx(0.06)


def test_computes_from_filled_times_price_when_no_cost_field():
    """Notional falls back to filled * average when 'cost' is absent."""
    ex = _ex()
    order = {"id": "4", "symbol": "DOGE/USDT:USDT",
             "filled": 1000.0, "average": 0.1,   # notional = 100
             "takerOrMaker": "maker", "fee": {"cost": None}}
    # maker: 100 * 0.0001 = 0.01
    assert ex.extract_order_fee(order, "DOGE/USDT:USDT") == pytest.approx(0.01)


def test_returns_zero_when_no_notional_resolvable():
    """Truly nothing to compute from -> 0.0 (caller keeps fees_pending)."""
    ex = _ex()
    order = {"id": "5", "symbol": "DOGE/USDT:USDT", "fee": {"cost": None}}
    assert ex.extract_order_fee(order, "DOGE/USDT:USDT") == 0.0
