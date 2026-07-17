"""F3 (2026-07-17): failed entry-order cancels must be swept, not forgotten.

Bug class: in _try_limit_entry, when the patience-window cancel RAISES and
neither fetch_order nor ground truth finds a fill, the function returns None
and the order id is dropped — the order can still be live on the exchange and
fill hours later (4/13 incident; likely origin of the 6/14 ghost short).
Fix: register the id in _pending_cancel_sweep; sweep_pending_cancels() retries
each cycle from the reconcile call site; adoption of any late fill remains the
existing orphan scan's job (sweep never adopts, preventing double-adoption).
"""
import inspect
import time

import ccxt
import exchange as exmod
import bot as botmod


class F3FakeClient:
    def __init__(self):
        self.cancel_error = RuntimeError("cancel rejected")
        self.cancelled = []

    def create_order(self, symbol, typ, side, amount, price, params=None):
        return {"id": "o1", "status": "open"}

    def fetch_order(self, order_id, symbol):
        raise RuntimeError("fetch down")

    def cancel_order(self, order_id, symbol):
        if self.cancel_error:
            raise self.cancel_error
        self.cancelled.append(order_id)


def _bare_exchange(monkeypatch):
    monkeypatch.setattr(exmod.Config, "is_live", staticmethod(lambda: True))
    ex = object.__new__(exmod.Exchange)
    ex.client = F3FakeClient()
    ex._pending_cancel_sweep = {}
    ex._round_price = lambda s, p: p
    ex.get_open_positions = lambda: []
    ex._position_ground_truth = lambda *a, **k: None
    return ex


def test_cancel_fail_registers_pending_sweep(monkeypatch):
    ex = _bare_exchange(monkeypatch)
    result = ex._try_limit_entry("BTC/USDT:USDT", "long", 0.001, 60000.0, patience_s=0.0)
    assert result is None
    assert "BTC/USDT:USDT" in ex._pending_cancel_sweep
    assert ex._pending_cancel_sweep["BTC/USDT:USDT"]["order_id"] == "o1"


def test_clean_cancel_does_not_register(monkeypatch):
    ex = _bare_exchange(monkeypatch)
    ex.client.cancel_error = None  # cancel succeeds
    result = ex._try_limit_entry("BTC/USDT:USDT", "long", 0.001, 60000.0, patience_s=0.0)
    assert result is None
    assert ex._pending_cancel_sweep == {}


def test_sweep_confirms_dead_order(monkeypatch):
    ex = _bare_exchange(monkeypatch)
    ex.client.cancel_error = None
    ex._pending_cancel_sweep["BTC/USDT:USDT"] = {"order_id": "o9", "ts": time.time()}
    expired = ex.sweep_pending_cancels()
    assert expired == []
    assert ex._pending_cancel_sweep == {}
    assert ex.client.cancelled == ["o9"]


def test_sweep_resolves_on_order_not_found(monkeypatch):
    ex = _bare_exchange(monkeypatch)
    ex.client.cancel_error = ccxt.OrderNotFound("gone")
    ex._pending_cancel_sweep["BTC/USDT:USDT"] = {"order_id": "o9", "ts": time.time()}
    expired = ex.sweep_pending_cancels()
    assert expired == []
    assert ex._pending_cancel_sweep == {}


def test_sweep_keeps_on_persistent_failure(monkeypatch):
    ex = _bare_exchange(monkeypatch)
    ex._pending_cancel_sweep["BTC/USDT:USDT"] = {"order_id": "o9", "ts": time.time()}
    expired = ex.sweep_pending_cancels()
    assert expired == []
    assert "BTC/USDT:USDT" in ex._pending_cancel_sweep


def test_sweep_ttl_expiry_drops_and_returns(monkeypatch):
    ex = _bare_exchange(monkeypatch)
    ex._pending_cancel_sweep["BTC/USDT:USDT"] = {"order_id": "o9", "ts": time.time() - 90000}
    expired = ex.sweep_pending_cancels()
    assert len(expired) == 1
    assert expired[0]["order_id"] == "o9"
    assert ex._pending_cancel_sweep == {}


def test_run_cycle_calls_sweep_alongside_reconcile():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    sync_idx = src.find("_sync_exchange_closes(prices)")
    assert sync_idx != -1
    assert "sweep_pending_cancels(" in src, "_run_cycle must sweep pending cancels"


def test_exchange_init_creates_registry():
    src = inspect.getsource(exmod.Exchange.__init__)
    assert "_pending_cancel_sweep" in src
