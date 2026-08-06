"""Honest paper-entry pricing (2026-08-05, from the I3 fill-reval audit).

Defect: paper slot entries recorded the per-cycle cached price, which goes
stale 1-3 minutes across the ~90s loop — the I3 audit found 41% of the
SR_BOUNCE v2 book's profit came from phantom entries at prices the market
had already left (LTC "bought" 44.15 while the tape printed 44.21-44.26).

Fix under test: _fresh_paper_entry_price(ws_feed, exchange, symbol, cached)
returns (price, age_s, source) preferring a fresh WS tick (age <= 10s, same
bound as the live exit watcher), then a REST ticker, then the cached price
explicitly flagged so the staleness is recorded, never hidden. Never raises.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import _fresh_paper_entry_price, PAPER_PX_MAX_AGE_S


class FakeWS:
    def __init__(self, result=None, raises=False):
        self._result, self._raises = result, raises

    def last_price(self, symbol):
        if self._raises:
            raise RuntimeError("ws boom")
        return self._result


class FakeExchange:
    def __init__(self, ticker=None, raises=False):
        self._ticker, self._raises = ticker, raises
        self.calls = 0

    def get_ticker(self, symbol):
        self.calls += 1
        if self._raises:
            raise RuntimeError("rest boom")
        return self._ticker


def test_fresh_ws_price_wins():
    ws = FakeWS(result=(100.5, 3.0))
    ex = FakeExchange(ticker={"last": 999.0})
    price, age, src = _fresh_paper_entry_price(ws, ex, "SOL/USDT:USDT", 98.0)
    assert (price, age, src) == (100.5, 3.0, "ws")
    assert ex.calls == 0  # no REST call when WS is fresh


def test_stale_ws_falls_back_to_rest():
    ws = FakeWS(result=(100.5, PAPER_PX_MAX_AGE_S + 35.0))
    ex = FakeExchange(ticker={"last": 101.2})
    price, age, src = _fresh_paper_entry_price(ws, ex, "SOL/USDT:USDT", 98.0)
    assert (price, age, src) == (101.2, 0.0, "rest")


def test_no_ws_no_rest_returns_cached_flagged():
    ex = FakeExchange(ticker=None)
    price, age, src = _fresh_paper_entry_price(None, ex, "SOL/USDT:USDT", 99.0)
    assert price == 99.0
    assert src == "cached"
    assert age == -1.0  # unknown age is flagged, not faked


def test_ws_raises_rest_raises_never_propagates():
    ws = FakeWS(raises=True)
    ex = FakeExchange(raises=True)
    price, age, src = _fresh_paper_entry_price(ws, ex, "SOL/USDT:USDT", 97.5)
    assert (price, src) == (97.5, "cached")


def test_zero_or_missing_ticker_last_is_not_a_price():
    ws = FakeWS(result=None)
    ex = FakeExchange(ticker={"last": 0.0})
    price, age, src = _fresh_paper_entry_price(ws, ex, "SOL/USDT:USDT", 96.0)
    assert (price, src) == (96.0, "cached")
