"""Tests for the durable-trail SL ratchet (2026-06 Part B).

Covers:
  A. Exchange.move_stop_loss — atomic amend, fallback place-then-cancel,
     complete-or-raise (old SL never cancelled before replacement confirmed).
  B. The bot.py [DURABLE SL] block arithmetic — target selection, ratchet-only,
     0.1%-of-price throttle (replicated as pure math, same formulas).
  C. Position.exchange_sl_price / sl_ratcheted state round-trip via
     RiskManager._save_state/_load_state with a temp state file.
  D. check_positions exit-reason classification regression
     (trailing_stop vs stop_loss vs take_profit).

No network, no live trading_state.json, no bot loop.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exchange as exchange_mod
from config import Config
from exchange import Exchange
from risk_manager import Position, RiskManager

SYMBOL = "BTC/USDT:USDT"


# ---------------------------------------------------------------------------
# A. move_stop_loss with mocked ccxt client
# ---------------------------------------------------------------------------

@pytest.fixture
def live_exchange(monkeypatch):
    """Exchange instance with a MagicMock ccxt client, forced live mode,
    time.sleep no-op. Never touches the network."""
    monkeypatch.setattr(Config, "MODE", "live")
    monkeypatch.setattr(exchange_mod.time, "sleep", lambda *a, **k: None)
    ex = Exchange.__new__(Exchange)  # skip __init__ (would build a real client)
    ex.client = MagicMock()
    # Precision helpers pass values through unchanged
    ex.client.price_to_precision.side_effect = lambda s, p: str(p)
    ex.client.amount_to_precision.side_effect = lambda s, a: str(a)
    return ex


def test_amend_success_first_try(live_exchange):
    ex = live_exchange
    ex.client.edit_order.return_value = {"id": "amended-1"}
    ex.client.fetch_open_orders.return_value = [{"id": "amended-1"}]

    result = ex.move_stop_loss(SYMBOL, "long", 0.5, 99.0, "old-1")

    assert result == "amended-1"
    assert ex.client.edit_order.call_count == 1
    ex.client.cancel_order.assert_not_called()
    ex.client.create_order.assert_not_called()

    # Param shape of the amend call
    args, kwargs = ex.client.edit_order.call_args
    assert args[0] == "old-1"
    assert args[1] == SYMBOL
    assert args[2] == "market"
    assert args[3] == "sell"          # long -> sell side SL
    assert args[5] is None            # market amend, no limit price
    params = kwargs["params"]
    assert params["reduceOnly"] is True
    assert params["triggerPrice"] == 99.0
    assert params["triggerDirection"] == "descending"  # long SL fires downward


def test_amend_fails_fallback_places_then_cancels(live_exchange):
    ex = live_exchange
    ex.client.edit_order.side_effect = Exception("amend rejected")
    ex.client.create_order.return_value = {"id": "new-2"}
    ex.client.fetch_open_orders.return_value = [{"id": "new-2"}]
    ex.client.cancel_order.return_value = {}

    result = ex.move_stop_loss(SYMBOL, "short", 1.0, 105.0, "old-2")

    assert result == "new-2"
    assert ex.client.edit_order.call_count == 3
    assert ex.client.create_order.call_count == 1
    ex.client.cancel_order.assert_called_once_with("old-2", SYMBOL)

    # Old SL is cancelled strictly AFTER the new one is placed
    names = [c[0] for c in ex.client.mock_calls]
    assert names.index("create_order") < names.index("cancel_order")

    # Fallback param shape (short -> buy side, ascending trigger)
    args, kwargs = ex.client.create_order.call_args
    assert args[0] == SYMBOL and args[1] == "market" and args[2] == "buy"
    params = kwargs["params"]
    assert params["reduceOnly"] is True
    assert params["triggerPrice"] == 105.0
    assert params["triggerDirection"] == "ascending"


def test_amend_and_fallback_fail_raises_old_sl_untouched(live_exchange):
    ex = live_exchange
    ex.client.edit_order.side_effect = Exception("amend rejected")
    ex.client.create_order.side_effect = Exception("place rejected")

    with pytest.raises(RuntimeError):
        ex.move_stop_loss(SYMBOL, "long", 0.5, 99.0, "old-3")

    assert ex.client.edit_order.call_count == 3
    assert ex.client.create_order.call_count == 3
    ex.client.cancel_order.assert_not_called()  # old SL must stay resting


def test_software_sl_id_raises_value_error(live_exchange):
    ex = live_exchange
    with pytest.raises(ValueError):
        ex.move_stop_loss(SYMBOL, "long", 0.5, 99.0, "software")
    ex.client.edit_order.assert_not_called()
    ex.client.create_order.assert_not_called()
    ex.client.cancel_order.assert_not_called()


def test_paper_mode_is_noop(monkeypatch):
    monkeypatch.setattr(Config, "MODE", "paper")
    ex = Exchange.__new__(Exchange)
    ex.client = MagicMock()
    assert ex.move_stop_loss(SYMBOL, "long", 0.5, 99.0, "old-9") == "old-9"
    assert ex.client.mock_calls == []


# ---------------------------------------------------------------------------
# B. [DURABLE SL] target/throttle arithmetic (replicates bot.py block)
# ---------------------------------------------------------------------------

BAND = 0.012  # DURABLE_TRAIL_BAND_PCT default 1.2 / 100


def _durable_target(side, stop_loss, peak_price, trailing_armed, band=BAND):
    """Mirror of the bot.py [DURABLE SL] target computation."""
    durable_floor = None
    if trailing_armed and peak_price > 0:
        durable_floor = peak_price * (1 - band) if side == "long" else peak_price * (1 + band)
    candidates = [v for v in (stop_loss, durable_floor) if v is not None]
    return max(candidates) if side == "long" else min(candidates)


def _should_move(side, target, current_resting, price):
    """Mirror of the bot.py ratchet-only + >=0.1% throttle gate."""
    improvement = (target - current_resting) if side == "long" else (current_resting - target)
    return not (improvement <= 0 or improvement / price < 0.001)


def test_config_default_band_is_1_2_pct():
    assert Config.DURABLE_TRAIL_BAND_PCT == 1.2


def test_long_target_is_max_of_stoploss_and_band_floor():
    # Floor wins when above stop_loss
    assert _durable_target("long", 100.0, 110.0, True) == pytest.approx(110.0 * 0.988)
    # Breakeven lock wins when above the floor (Q2 coordination)
    assert _durable_target("long", 109.0, 110.0, True) == 109.0
    # Trail not armed -> target is just stop_loss
    assert _durable_target("long", 100.0, 110.0, False) == 100.0


def test_short_target_is_min_of_stoploss_and_band_ceiling():
    assert _durable_target("short", 100.0, 90.0, True) == pytest.approx(90.0 * 1.012)
    assert _durable_target("short", 90.5, 90.0, True) == 90.5
    assert _durable_target("short", 100.0, 90.0, False) == 100.0


def test_throttle_blocks_sub_0_1_pct_improvement():
    price = 100.0
    # 0.05% improvement — blocked
    assert _should_move("long", 100.05, 100.0, price) is False
    # just under 0.1% — blocked (exact 0.001 boundary is FP-sensitive in the
    # bot's own arithmetic, so test clearly-below / clearly-above)
    assert _should_move("long", 100.09, 100.0, price) is False
    # 0.125% — allowed
    assert _should_move("long", 100.125, 100.0, price) is True
    # 0.2% — allowed
    assert _should_move("long", 100.20, 100.0, price) is True
    # short mirror
    assert _should_move("short", 99.95, 100.0, price) is False
    assert _should_move("short", 99.80, 100.0, price) is True


def test_ratchet_blocks_negative_or_zero_improvement():
    assert _should_move("long", 99.0, 100.0, 100.0) is False   # would loosen
    assert _should_move("long", 100.0, 100.0, 100.0) is False  # no change
    assert _should_move("short", 101.0, 100.0, 100.0) is False # would loosen


# ---------------------------------------------------------------------------
# C. Position state round-trip (exchange_sl_price / sl_ratcheted)
# ---------------------------------------------------------------------------

def _make_position(**overrides):
    base = dict(
        symbol=SYMBOL, side="long", entry_price=100.0, amount=1.0,
        margin=10.0, stop_loss=98.8, take_profit=101.6,
    )
    base.update(overrides)
    return Position(**base)


def test_state_round_trip_persists_durable_fields(tmp_path):
    state_file = str(tmp_path / "test_state_durable.json")

    rm1 = RiskManager(state_file=state_file)
    pos = _make_position()
    pos.exchange_sl_price = 1.23
    pos.sl_ratcheted = True
    pos.sl_order_id = "live-sl-1"
    rm1.positions[SYMBOL] = pos
    rm1._save_state()

    assert os.path.exists(state_file)

    rm2 = RiskManager(state_file=state_file)
    assert SYMBOL in rm2.positions
    restored = rm2.positions[SYMBOL]
    assert restored.exchange_sl_price == 1.23
    assert restored.sl_ratcheted is True


def test_old_state_file_without_durable_keys_loads_defaults(tmp_path):
    state_file = str(tmp_path / "test_state_legacy.json")
    legacy = {
        "peak_balance": 50.0,
        "closed_trades": [],
        "trade_results": [],
        "positions": {
            SYMBOL: {
                "symbol": SYMBOL, "side": "long",
                "entry_price": 100.0, "amount": 1.0, "margin": 10.0,
                "stop_loss": 98.8, "take_profit": 101.6,
                # no exchange_sl_price / sl_ratcheted keys (pre-durable-trail file)
            }
        },
    }
    with open(state_file, "w") as f:
        json.dump(legacy, f)

    rm = RiskManager(state_file=state_file)
    assert SYMBOL in rm.positions
    pos = rm.positions[SYMBOL]
    assert pos.exchange_sl_price is None
    assert pos.sl_ratcheted is False


# ---------------------------------------------------------------------------
# D. check_positions exit-reason classification regression
# ---------------------------------------------------------------------------

def _rm_with(pos):
    rm = RiskManager.__new__(RiskManager)  # no state file I/O
    rm.positions = {pos.symbol: pos}
    return rm


def test_armed_trail_in_profit_tags_trailing_stop(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    # Margin chosen so ROI < 5% at this price: update_trailing_stop won't
    # re-arm/move the trail, isolating the classification logic.
    pos = _make_position(margin=100.0, take_profit=None,
                         trailing_stop_price=104.0, peak_price=105.0)
    rm = _rm_with(pos)
    # price 103.9 <= trail 104.0 triggers should_stop_loss; pnl +3.9 USDT > 0
    result = rm.check_positions({SYMBOL: 103.9})
    assert result == [(SYMBOL, "trailing_stop")]


def test_hard_sl_no_trail_tags_stop_loss(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    pos = _make_position(margin=100.0, take_profit=120.0)
    rm = _rm_with(pos)
    # price 98.0 <= stop_loss 98.8, trail never armed (ROI negative), pnl < 0
    result = rm.check_positions({SYMBOL: 98.0})
    assert result == [(SYMBOL, "stop_loss")]


def test_tp_hit_tags_take_profit(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    pos = _make_position(margin=10000.0, take_profit=120.0)
    rm = _rm_with(pos)
    # huge margin -> ROI ~0.2%, no trail armed; price >= TP
    result = rm.check_positions({SYMBOL: 120.5})
    assert result == [(SYMBOL, "take_profit")]
