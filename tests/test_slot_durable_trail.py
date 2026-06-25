"""Tests for the durable-trail SL ratchet ported to LIVE strategy slots (2026-06-24).

The main-bot durable trail (bot.py:987-1032) ratchets the resting exchange SL up as
the trail arms. Slots previously had only a static entry SL/TP — a winning slot trade
could round-trip to the stop (the XLM 5m_mean_revert −14.2% loss, 2026-06-24). This
ports the ratchet into the slot exit loop via Bot._ratchet_slot_durable_sl, opt-in per
slot (StrategySlot.durable_trail_enabled).

Covers:
  A. StrategySlot.durable_trail_enabled field (default off).
  B. Bot._ratchet_slot_durable_sl — amends when armed; no-ops for disabled/paper/
     software-SL/not-armed; survives an amend failure without corrupting state.

No network, no live state files, no bot loop. The durable-floor/throttle ARITHMETIC is
already covered in test_durable_trail.py; these tests assert the slot WIRING.
"""
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as bot_mod
from bot import Phmex2Bot
from config import Config
from risk_manager import Position
from strategy_slot import StrategySlot

SYMBOL = "XLM/USDT:USDT"


# ---------------------------------------------------------------------------
# A. StrategySlot opt-in field
# ---------------------------------------------------------------------------

def test_strategyslot_durable_trail_defaults_off():
    slot = StrategySlot(slot_id="t_off", strategy_name="bb_mean_reversion", timeframe="5m")
    assert slot.durable_trail_enabled is False


def test_strategyslot_durable_trail_can_opt_in():
    slot = StrategySlot(slot_id="t_on", strategy_name="bb_mean_reversion",
                        timeframe="5m", durable_trail_enabled=True)
    assert slot.durable_trail_enabled is True


# ---------------------------------------------------------------------------
# B. Bot._ratchet_slot_durable_sl wiring
# ---------------------------------------------------------------------------

def _bot():
    """A Bot shell with just the attributes the ratchet helper touches."""
    b = Phmex2Bot.__new__(Phmex2Bot)
    b._closing = set()
    b.exchange = MagicMock()
    b.exchange.move_stop_loss.return_value = "live-sl-2"
    return b


def _slot(*, paper_mode=False, durable_trail_enabled=True):
    """Lightweight slot stand-in (avoids RiskManager state-file I/O)."""
    return types.SimpleNamespace(
        slot_id="5m_mean_revert",
        paper_mode=paper_mode,
        durable_trail_enabled=durable_trail_enabled,
        risk=MagicMock(),
    )


def _armed_short(**overrides):
    """A short already in profit far enough that the trail arms at price=99 (+10% ROI)."""
    base = dict(symbol=SYMBOL, side="short", entry_price=100.0, amount=1.0,
                margin=10.0, stop_loss=101.2, take_profit=98.4)
    base.update(overrides)
    pos = Position(**base)
    pos.sl_order_id = "live-sl-1"
    pos.exchange_sl_price = 101.2
    return pos


def test_ratchet_amends_when_armed_live_enabled(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(), _armed_short()

    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 99.0)  # +10% ROI short

    assert b.exchange.move_stop_loss.call_count == 1
    args = b.exchange.move_stop_loss.call_args[0]
    assert args[0] == SYMBOL and args[1] == "short" and args[4] == "live-sl-1"
    target = args[3]
    assert target < 101.2                      # ratcheted tighter (down for a short)
    assert pos.sl_order_id == "live-sl-2"       # new id captured
    assert pos.exchange_sl_price == target
    assert pos.sl_ratcheted is True
    slot.risk._save_state.assert_called_once()  # persisted so it survives a sleep/restart


def test_ratchet_noop_when_slot_disabled(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(durable_trail_enabled=False), _armed_short()
    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 99.0)
    b.exchange.move_stop_loss.assert_not_called()
    assert pos.sl_ratcheted is False


def test_ratchet_noop_when_paper(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(paper_mode=True), _armed_short()
    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 99.0)
    b.exchange.move_stop_loss.assert_not_called()


def test_ratchet_noop_software_sl(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(), _armed_short()
    pos.sl_order_id = "software"
    pos.exchange_sl_price = None
    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 99.0)
    b.exchange.move_stop_loss.assert_not_called()


def test_ratchet_noop_when_not_in_profit(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(), _armed_short()
    # price 100.5 = -5% ROI for a short: trail never arms, nothing to ratchet.
    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 100.5)
    b.exchange.move_stop_loss.assert_not_called()
    assert pos.sl_ratcheted is False


def test_ratchet_noop_when_symbol_closing(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(), _armed_short()
    b._closing.add(SYMBOL)  # a close is already in flight this cycle
    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 99.0)
    b.exchange.move_stop_loss.assert_not_called()


def test_ratchet_survives_amend_failure_without_corrupting_state(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b, slot, pos = _bot(), _slot(), _armed_short()
    b.exchange.move_stop_loss.side_effect = RuntimeError("amend rejected — old SL resting")

    b._ratchet_slot_durable_sl(slot, SYMBOL, pos, 99.0)  # must not raise

    assert pos.sl_order_id == "live-sl-1"      # unchanged — old SL still rests
    assert pos.exchange_sl_price == 101.2       # not advanced on failure
    assert pos.sl_ratcheted is False            # never claims protection it doesn't have
