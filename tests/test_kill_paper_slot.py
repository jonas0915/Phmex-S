"""Kill-sentinel paper-slot guard (2026-07-16 review finding).

The old `.kill_<slot>` handler closed slot positions via UNCONDITIONAL real
exchange orders. For a PAPER slot whose symbol overlaps a real main-bot
position, that reduceOnly order could REDUCE the REAL position. The fix routes
paper slots through _close_slot_position (paper book) and never touches the
exchange. These tests pin both sides of the branch.
"""
import os
from types import SimpleNamespace

import pytest

import bot as botmod
from strategy_slot import StrategySlot


class KillFakeExchange:
    def __init__(self):
        self.calls = []

    def close_long(self, symbol, amount):
        self.calls.append(("close_long", symbol, amount))
        return {"id": "x1"}

    def close_short(self, symbol, amount):
        self.calls.append(("close_short", symbol, amount))
        return {"id": "x2"}

    def cancel_open_orders(self, symbol):
        self.calls.append(("cancel_open_orders", symbol))


def _bare_bot(slot, ws_last=None):
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = [slot]
    b.exchange = KillFakeExchange()
    b.ws_feed = SimpleNamespace(last_price=lambda s: ws_last)
    b.risk = SimpleNamespace(positions={}, _drawdown_pause_until=0.0)
    b._trading_paused = False
    b._pause_logged = False
    b._halt_main_logged = False
    return b


def _slot(slot_id, paper, tmp_path):
    s = StrategySlot(slot_id=slot_id, strategy_name="bb_mean_reversion",
                     timeframe="5m", max_positions=1, capital_pct=0.0,
                     paper_mode=paper)
    # place a fake open position in the slot book
    s.risk.positions["BTC/USDT:USDT"] = SimpleNamespace(
        side="long", amount=0.001, entry_price=60000.0, margin=6.0,
        pnl_usdt=lambda px: (px - 60000.0) * 0.001,
        pnl_percent=lambda px: (px - 60000.0) / 60000.0 * 100,
    )
    return s


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # sentinel globs are cwd-relative
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_exit", lambda *a, **k: None)
    return tmp_path


def test_kill_paper_slot_never_touches_exchange(sandbox, monkeypatch):
    slot = _slot("KP_TEST", paper=True, tmp_path=sandbox)
    closed = []
    monkeypatch.setattr(slot.risk, "close_position",
                        lambda sym, px, reason: closed.append((sym, px, reason)))
    b = _bare_bot(slot, ws_last=(61000.0, 0.0))
    open(".kill_KP_TEST", "w").close()

    b._process_sentinels()

    assert b.exchange.calls == []                      # exchange NEVER touched
    assert closed == [("BTC/USDT:USDT", 61000.0, "killed")]  # paper book closed @ WS price
    assert slot.enabled is False
    assert not os.path.exists(".kill_KP_TEST")         # sentinel consumed


def test_kill_paper_slot_falls_back_to_entry_price(sandbox, monkeypatch):
    slot = _slot("KP_TEST2", paper=True, tmp_path=sandbox)
    closed = []
    monkeypatch.setattr(slot.risk, "close_position",
                        lambda sym, px, reason: closed.append((sym, px, reason)))
    b = _bare_bot(slot, ws_last=None)                  # WS cache empty
    open(".kill_KP_TEST2", "w").close()

    b._process_sentinels()

    assert b.exchange.calls == []
    assert closed == [("BTC/USDT:USDT", 60000.0, "killed")]  # entry-price fallback


def test_kill_live_slot_still_uses_exchange(sandbox, monkeypatch):
    slot = _slot("KL_TEST", paper=False, tmp_path=sandbox)
    slot.paper_mode = False
    slot.risk.is_paper = False
    b = _bare_bot(slot)
    open(".kill_KL_TEST", "w").close()

    b._process_sentinels()

    assert ("close_long", "BTC/USDT:USDT", 0.001) in b.exchange.calls  # live path intact
    assert not os.path.exists(".kill_KL_TEST")
