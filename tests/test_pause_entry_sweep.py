"""F2 (2026-07-17): pause/halt must cancel resting ENTRY orders (never SL/TP).

Bug class: a PostOnly entry order left resting (e.g. after a failed cancel)
can fill DURING a halt, creating a ghost position (4/13 incident, likely 6/14
ghost origin). Neither the daily-loss kill switch nor pause processing swept
resting entry orders. Fix: Exchange.cancel_entry_orders(symbol) skips
reduceOnly protective orders; _process_sentinels runs a one-shot sweep on the
pause transition edge, gated by Config.CANCEL_ENTRIES_ON_PAUSE.
"""
from types import SimpleNamespace

import exchange as exmod
import bot as botmod
from config import Config


class SweepFakeClient:
    def __init__(self, orders):
        self.orders = orders
        self.cancelled = []

    def fetch_open_orders(self, symbol):
        return self.orders

    def cancel_order(self, order_id, symbol):
        self.cancelled.append(order_id)


def _bare_exchange(orders, monkeypatch):
    monkeypatch.setattr(exmod.Config, "is_live", staticmethod(lambda: True))
    ex = object.__new__(exmod.Exchange)
    ex.client = SweepFakeClient(orders)
    return ex


def test_cancel_entry_orders_skips_reduce_only(monkeypatch):
    orders = [
        {"id": "entry1", "reduceOnly": False, "info": {}},
        {"id": "sl1", "reduceOnly": True, "info": {}},
        {"id": "tp1", "reduceOnly": None, "info": {"reduceOnly": True}},
        {"id": "entry2", "info": {}},
    ]
    ex = _bare_exchange(orders, monkeypatch)
    n = ex.cancel_entry_orders("BTC/USDT:USDT")
    assert n == 2
    assert ex.client.cancelled == ["entry1", "entry2"]


def test_cancel_entry_orders_fetch_failure_returns_zero(monkeypatch):
    ex = _bare_exchange([], monkeypatch)

    def boom(symbol):
        raise RuntimeError("api down")
    ex.client.fetch_open_orders = boom
    assert ex.cancel_entry_orders("BTC/USDT:USDT") == 0


class SweepFakeExchange:
    def __init__(self):
        self.swept = []
        self.fail_symbols = set()

    def cancel_entry_orders(self, symbol):
        if symbol in self.fail_symbols:
            raise RuntimeError("boom")
        self.swept.append(symbol)
        return 1


def _bare_bot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    b = object.__new__(botmod.Phmex2Bot)
    b.exchange = SweepFakeExchange()
    b.slots = []
    b.ws_feed = None
    b.active_pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    return b


def test_pause_transition_sweeps_once(tmp_path, monkeypatch):
    b = _bare_bot(tmp_path, monkeypatch)
    (tmp_path / ".pause_trading").write_text("999\nMANUAL PAUSE")
    b._process_sentinels()
    assert sorted(b.exchange.swept) == sorted(b.active_pairs)
    b._process_sentinels()  # still paused: must NOT sweep again
    assert len(b.exchange.swept) == len(b.active_pairs)


def test_pause_clear_resets_sweep_flag(tmp_path, monkeypatch):
    b = _bare_bot(tmp_path, monkeypatch)
    sentinel = tmp_path / ".pause_trading"
    sentinel.write_text("999\nMANUAL PAUSE")
    b._process_sentinels()
    sentinel.unlink()
    b._process_sentinels()  # pause cleared → flag resets
    sentinel.write_text("999\nMANUAL PAUSE 2")
    b._process_sentinels()  # new pause episode → sweeps again
    assert len(b.exchange.swept) == 2 * len(b.active_pairs)


def test_sweep_failure_isolated(tmp_path, monkeypatch):
    b = _bare_bot(tmp_path, monkeypatch)
    b.exchange.fail_symbols = {"BTC/USDT:USDT"}
    (tmp_path / ".pause_trading").write_text("999\nMANUAL PAUSE")
    b._process_sentinels()  # must not raise
    assert b.exchange.swept == ["ETH/USDT:USDT"]


def test_flag_disables_sweep(tmp_path, monkeypatch):
    b = _bare_bot(tmp_path, monkeypatch)
    monkeypatch.setattr(Config, "CANCEL_ENTRIES_ON_PAUSE", False)
    (tmp_path / ".pause_trading").write_text("999\nMANUAL PAUSE")
    b._process_sentinels()
    assert b.exchange.swept == []
