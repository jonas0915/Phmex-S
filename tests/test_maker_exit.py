"""Tests for the opt-in maker-exit patience window (fix prepared 2026-06-11).

Covers, with a fully mocked ccxt client (no network, no live state):
  1. Config defaults — MAKER_EXIT_ENABLED off, patience 30s, clamp 45s.
  2. Maker fill within patience -> limit order returned, no market call.
  3. Patience expiry -> cancel-by-id BEFORE reduceOnly market fallback.
  4. Cancel failure -> still market-closes (double-close guarded by reduceOnly).
  5. PostOnly rejection -> immediate market fallback (no patience burn).
  6. Flag OFF -> legacy 4s window (8 x 0.5s polls) is byte-for-byte preserved.
  7. Partial fill on expiry -> remainder market-closed once, never the full size.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exchange as exchange_mod
from config import Config
from exchange import Exchange

SYMBOL = "BTC/USDT:USDT"
AMOUNT = 1.0
ASK = 100.1
BID = 99.9


@pytest.fixture
def live_exchange(monkeypatch):
    """Exchange with MagicMock ccxt client, live mode, maker exit ON (45s),
    time.sleep no-op. Never touches the network."""
    monkeypatch.setattr(Config, "MODE", "live")
    monkeypatch.setattr(Config, "MAKER_EXIT_ENABLED", True)
    monkeypatch.setattr(Config, "MAKER_EXIT_PATIENCE_S", 44.0)  # 22 polls x 2s
    monkeypatch.setattr(exchange_mod.time, "sleep", lambda *a, **k: None)
    ex = Exchange.__new__(Exchange)  # skip __init__ (would build a real client)
    ex.client = MagicMock()
    ex.client.price_to_precision.side_effect = lambda s, p: str(p)
    ex.client.amount_to_precision.side_effect = lambda s, a: str(a)
    # close_long/close_short read the book for the touch price
    ex.get_order_book = lambda symbol, depth=5: {"best_ask": ASK, "best_bid": BID}
    return ex


# ---------------------------------------------------------------------------
# 1. Config surface
# ---------------------------------------------------------------------------

def test_maker_exit_disabled_by_default():
    # .env has no MAKER_EXIT_* keys (config-only change), so these are the
    # shipped defaults: deploying the code changes nothing until opt-in.
    assert os.getenv("MAKER_EXIT_ENABLED") is None
    assert os.getenv("MAKER_EXIT_PATIENCE_S") is None
    assert Config.MAKER_EXIT_ENABLED is False
    assert Config.MAKER_EXIT_PATIENCE_S == 30.0


def test_patience_hard_clamp_constant():
    # Watchdog budget: bot.py signal.alarm(180); 3 exits x 45s = 135s ceiling.
    assert Exchange.MAKER_EXIT_PATIENCE_MAX_S == 45.0


def test_oversized_patience_is_clamped(live_exchange, monkeypatch):
    ex = live_exchange
    monkeypatch.setattr(Config, "MAKER_EXIT_PATIENCE_S", 300.0)
    ex.client.create_order.return_value = {"id": "x1"}
    ex.client.fetch_order.return_value = {"status": "open", "filled": 0}
    ex._try_limit_exit(SYMBOL, "sell", AMOUNT, ASK)
    # clamped to 45s -> int(45/2) = 22 polls, not 150
    assert ex.client.fetch_order.call_count == 23  # 22 polls + 1 post-cancel check


# ---------------------------------------------------------------------------
# 2. Maker fill within patience
# ---------------------------------------------------------------------------

def test_maker_fill_within_patience_no_market(live_exchange):
    ex = live_exchange
    filled = {"id": "x1", "status": "closed", "average": ASK, "filled": AMOUNT}
    ex.client.create_order.return_value = {"id": "x1"}
    ex.client.fetch_order.return_value = filled

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == filled
    ex.client.create_market_sell_order.assert_not_called()
    ex.client.cancel_order.assert_not_called()
    # PostOnly + reduceOnly on the resting limit
    args, kwargs = ex.client.create_order.call_args
    assert args[0] == SYMBOL and args[1] == "limit" and args[2] == "sell"
    assert kwargs["params"] == {"reduceOnly": True, "timeInForce": "PostOnly"}


def test_fill_on_late_poll_still_returned(live_exchange):
    ex = live_exchange
    filled = {"id": "x1", "status": "closed", "average": ASK, "filled": AMOUNT}
    ex.client.create_order.return_value = {"id": "x1"}
    # open for 20 polls, fills on the 21st (within the 22-poll patience)
    ex.client.fetch_order.side_effect = [{"status": "open", "filled": 0}] * 20 + [filled]

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == filled
    ex.client.create_market_sell_order.assert_not_called()
    ex.client.cancel_order.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Patience expiry -> cancel then market fallback
# ---------------------------------------------------------------------------

def test_patience_expiry_cancels_then_markets(live_exchange):
    ex = live_exchange
    ex.client.create_order.return_value = {"id": "x1"}
    ex.client.fetch_order.return_value = {"status": "open", "filled": 0}
    ex.client.create_market_sell_order.return_value = {"id": "m1", "status": "closed"}

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == {"id": "m1", "status": "closed"}
    ex.client.cancel_order.assert_called_once_with("x1", SYMBOL)
    ex.client.create_market_sell_order.assert_called_once()
    args, kwargs = ex.client.create_market_sell_order.call_args
    assert args[0] == SYMBOL
    assert kwargs["params"] == {"reduceOnly": True}
    # The resting limit is cancelled strictly BEFORE the market order
    names = [c[0] for c in ex.client.mock_calls]
    assert names.index("cancel_order") < names.index("create_market_sell_order")
    # Full patience used: 22 polls + 1 post-cancel check
    assert ex.client.fetch_order.call_count == 23


def test_short_side_expiry_cancels_then_markets_buy(live_exchange):
    ex = live_exchange
    ex.client.create_order.return_value = {"id": "s1"}
    ex.client.fetch_order.return_value = {"status": "open", "filled": 0}
    ex.client.create_market_buy_order.return_value = {"id": "m2", "status": "closed"}

    result = ex.close_short(SYMBOL, AMOUNT)

    assert result == {"id": "m2", "status": "closed"}
    # Buy-to-close rests at the best bid (maker side for a buyer)
    args, kwargs = ex.client.create_order.call_args
    assert args[1] == "limit" and args[2] == "buy" and args[4] == BID
    ex.client.cancel_order.assert_called_once_with("s1", SYMBOL)
    names = [c[0] for c in ex.client.mock_calls]
    assert names.index("cancel_order") < names.index("create_market_buy_order")


# ---------------------------------------------------------------------------
# 4. Cancel failure -> still market-closes (double-close guard)
# ---------------------------------------------------------------------------

def test_cancel_failure_still_market_closes(live_exchange):
    ex = live_exchange
    ex.client.create_order.return_value = {"id": "x1"}
    ex.client.fetch_order.return_value = {"status": "open", "filled": 0}
    ex.client.cancel_order.side_effect = Exception("api hiccup")
    ex.client.create_market_sell_order.return_value = {"id": "m1", "status": "closed"}

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == {"id": "m1", "status": "closed"}
    ex.client.create_market_sell_order.assert_called_once()


def test_cancel_and_fetch_failure_still_market_closes(live_exchange):
    ex = live_exchange
    ex.client.create_order.return_value = {"id": "x1"}
    # polls see open; post-cancel fetch raises too
    ex.client.fetch_order.side_effect = [{"status": "open", "filled": 0}] * 22 + [Exception("down")]
    ex.client.cancel_order.side_effect = Exception("down")
    ex.client.create_market_sell_order.return_value = {"id": "m1", "status": "closed"}

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == {"id": "m1", "status": "closed"}
    ex.client.create_market_sell_order.assert_called_once()


def test_cancel_failure_because_filled_returns_limit_no_market(live_exchange):
    """Cancel fails because the order just filled — must return the limit fill
    and NOT also market-close (that would be the double-close)."""
    ex = live_exchange
    filled = {"id": "x1", "status": "closed", "average": ASK, "filled": AMOUNT}
    ex.client.create_order.return_value = {"id": "x1"}
    ex.client.fetch_order.side_effect = [{"status": "open", "filled": 0}] * 22 + [filled]
    ex.client.cancel_order.side_effect = Exception("order already filled")

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == filled
    ex.client.create_market_sell_order.assert_not_called()


# ---------------------------------------------------------------------------
# 5. PostOnly rejection -> immediate market, no patience burn
# ---------------------------------------------------------------------------

def test_post_only_rejection_immediate_market(live_exchange):
    ex = live_exchange
    ex.client.create_order.return_value = {"id": "x1"}
    # Phemex cancels a would-cross PostOnly order: status canceled, nothing filled
    ex.client.fetch_order.return_value = {"status": "canceled", "filled": 0}
    ex.client.create_market_sell_order.return_value = {"id": "m1", "status": "closed"}

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == {"id": "m1", "status": "closed"}
    # Detected on the FIRST poll — does not sit through the 22-poll window
    assert ex.client.fetch_order.call_count == 1
    ex.client.cancel_order.assert_not_called()  # order already dead
    ex.client.create_market_sell_order.assert_called_once()


def test_create_order_exception_falls_back_to_market(live_exchange):
    ex = live_exchange
    ex.client.create_order.side_effect = Exception("39999 post-only reject")
    ex.client.create_market_sell_order.return_value = {"id": "m1", "status": "closed"}

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == {"id": "m1", "status": "closed"}
    ex.client.fetch_order.assert_not_called()
    ex.client.create_market_sell_order.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Flag OFF -> legacy 4s window preserved (deploy-time no-op)
# ---------------------------------------------------------------------------

def test_flag_off_keeps_legacy_4s_window(live_exchange, monkeypatch):
    ex = live_exchange
    monkeypatch.setattr(Config, "MAKER_EXIT_ENABLED", False)
    sleeps = []
    monkeypatch.setattr(exchange_mod.time, "sleep", lambda s: sleeps.append(s))
    ex.client.create_order.return_value = {"id": "x1"}
    ex.client.fetch_order.return_value = {"status": "open", "filled": 0}
    ex.client.create_market_sell_order.return_value = {"id": "m1", "status": "closed"}

    result = ex.close_long(SYMBOL, AMOUNT)

    assert result == {"id": "m1", "status": "closed"}
    # 8 polls x 0.5s = the pre-fix 4 seconds, byte-for-byte
    assert sleeps == [0.5] * 8
    assert ex.client.fetch_order.call_count == 9  # 8 polls + 1 post-cancel check
    ex.client.cancel_order.assert_called_once_with("x1", SYMBOL)


# ---------------------------------------------------------------------------
# 7. Partial fill on expiry -> remainder only, never full-size double close
# ---------------------------------------------------------------------------

def test_partial_fill_on_expiry_markets_remainder_only(live_exchange):
    ex = live_exchange
    partial = {"id": "x1", "status": "canceled", "filled": 0.4}
    ex.client.create_order.side_effect = [
        {"id": "x1"},                      # the resting limit
        {"id": "m1", "status": "closed"},  # the remainder market order
    ]
    ex.client.fetch_order.side_effect = [{"status": "open", "filled": 0}] * 22 + [partial]

    result = ex.close_long(SYMBOL, AMOUNT)

    # Returns the partially-filled limit; close_long does NOT market the full size
    assert result == partial
    ex.client.create_market_sell_order.assert_not_called()
    # Remainder market order: 1.0 - 0.4 = 0.6, reduceOnly
    args, kwargs = ex.client.create_order.call_args
    assert args[0] == SYMBOL and args[1] == "market" and args[2] == "sell"
    assert args[3] == pytest.approx(0.6)
    assert kwargs["params"] == {"reduceOnly": True}
