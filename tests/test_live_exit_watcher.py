"""Tests for the tier-2 live exit watcher (2026-06-11).

Spec: docs/superpowers/specs/2026-06-11-live-exit-watcher-design.md

Covers:
  A. risk_manager.evaluate_exit — classification parity with check_positions
     (trailing_stop / stop_loss / take_profit / None) AND the non-mutation
     guarantee (never ratchets trailing_stop_price / peak_price).
  B. Phmex2Bot._live_exit_watcher_loop single iteration — breach closes once
     with the watcher's reason, claim released in finally.
  C. Double-close prevention — pre-claimed symbol in _closing is skipped with
     zero exchange calls (and the foreign claim is NOT discarded).
  D. Stale/absent WS price — no action.
  E. Close order returns None — position stays in risk.positions, claim released.
  F. ws_feed.last_price accessor — (close, age) when cached, None when not.
  G. Flag gating — watcher spawn in bot.start() is guarded by
     Config.is_live() and Config.LIVE_EXIT_WATCHER (source-level guard; see note).

No network, no live files, no bot main loop. conftest.py routes logging to
logs/test_run.log via PHMEX_LOG_FILE — never bot.log.
"""
import os
import sys
import threading
import time as real_time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as bot_module
from bot import Phmex2Bot
from config import Config
from risk_manager import Position, RiskManager
from ws_feed import WSDataFeed

SYMBOL = "BTC/USDT:USDT"
BOT_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot.py")


def _make_position(**overrides):
    base = dict(
        symbol=SYMBOL, side="long", entry_price=100.0, amount=1.0,
        margin=10.0, stop_loss=98.8, take_profit=101.6,
    )
    base.update(overrides)
    return Position(**base)


def _rm_with(pos):
    """RiskManager without state-file I/O (mirrors test_durable_trail)."""
    rm = RiskManager.__new__(RiskManager)
    rm.positions = {pos.symbol: pos}
    return rm


# ---------------------------------------------------------------------------
# A. evaluate_exit — classification parity + non-mutation
# ---------------------------------------------------------------------------

PARITY_CASES = [
    # (position kwargs, price, expected reason)
    # Armed trail, in profit, price <= trail -> trailing_stop.
    # margin=100 keeps ROI < 5% so check_positions' update_trailing_stop
    # cannot move the trail before classifying (clean comparison).
    (dict(margin=100.0, take_profit=None,
          trailing_stop_price=104.0, peak_price=105.0), 103.9, "trailing_stop"),
    # Hard SL breach, trail never armed, pnl < 0 -> stop_loss.
    (dict(margin=100.0, take_profit=120.0), 98.0, "stop_loss"),
    # TP breach (huge margin -> tiny ROI, trail never arms) -> take_profit.
    (dict(margin=10000.0, take_profit=120.0), 120.5, "take_profit"),
    # No level breached -> None.
    (dict(margin=100.0, take_profit=120.0), 100.5, None),
]


@pytest.mark.parametrize("pos_kwargs,price,expected", PARITY_CASES,
                         ids=["trailing_stop", "stop_loss", "take_profit", "no_breach"])
def test_evaluate_exit_matches_check_positions(monkeypatch, pos_kwargs, price, expected):
    """The watcher's classifier must agree with the 60s cycle's classifier
    on identically-configured positions (regression guard lessons.md:306)."""
    monkeypatch.setattr(Config, "TRAILING_STOP", True)

    rm_watch = _rm_with(_make_position(**pos_kwargs))
    assert rm_watch.evaluate_exit(SYMBOL, price) == expected

    rm_cycle = _rm_with(_make_position(**pos_kwargs))
    cycle_result = rm_cycle.check_positions({SYMBOL: price})
    assert cycle_result == ([(SYMBOL, expected)] if expected else [])


def test_evaluate_exit_never_ratchets_trail_or_peak(monkeypatch):
    """Enforcement-only semantics: at a price that WOULD ratchet both
    peak_price and trailing_stop_price via update_trailing_stop, evaluate_exit
    must leave both fields untouched (design spec section 2)."""
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    monkeypatch.setattr(Config, "LEVERAGE", 10)
    kwargs = dict(margin=10.0, take_profit=None,
                  trailing_stop_price=104.0, peak_price=105.0)

    # Sanity: prove price 106.0 ratchets a clone (ROI 60% -> 5% trail tier,
    # peak 105 -> 106, trail 104 -> ~105.47). If this stops ratcheting, the
    # non-mutation assertion below would be vacuous.
    clone = _make_position(**kwargs)
    clone.update_trailing_stop(106.0)
    assert clone.peak_price == 106.0
    assert clone.trailing_stop_price > 104.0

    pos = _make_position(**kwargs)
    rm = _rm_with(pos)
    reason = rm.evaluate_exit(SYMBOL, 106.0)
    assert reason is None  # 106 above trail, no TP set -> no breach
    assert pos.trailing_stop_price == 104.0
    assert pos.peak_price == 105.0


def test_evaluate_exit_unknown_symbol_or_falsy_price_is_none():
    rm = _rm_with(_make_position())
    assert rm.evaluate_exit("DOGE/USDT:USDT", 100.0) is None
    assert rm.evaluate_exit(SYMBOL, 0.0) is None  # falsy price guard


# ---------------------------------------------------------------------------
# Watcher harness — bare Phmex2Bot (init is heavy: exchange, scanner, WS)
# ---------------------------------------------------------------------------

@pytest.fixture
def watcher_bot(monkeypatch):
    """Phmex2Bot via object.__new__ with only the attributes the watcher loop
    touches. time.sleep in bot.py is patched so the first sleep of the loop
    flips running=False -> exactly one body iteration, instantly."""
    monkeypatch.setattr(Config, "TRAILING_STOP", True)

    b = object.__new__(Phmex2Bot)
    b.running = True
    b._pos_lock = threading.Lock()
    b._closing = set()

    pos = _make_position(take_profit=None, trailing_stop_price=104.0,
                         peak_price=105.0, margin=100.0)
    b.risk = _rm_with(pos)
    b.risk.close_position = MagicMock()

    b.exchange = MagicMock()
    b.exchange.close_long.return_value = {"id": "close-1", "symbol": SYMBOL}
    b.exchange.close_short.return_value = {"id": "close-2", "symbol": SYMBOL}
    b.exchange.extract_order_fee.return_value = 0.0123

    b._ws_feed = MagicMock()
    b._ws_feed.last_price.return_value = (103.9, 2.0)  # fresh breach by default

    # Heavy real methods stubbed on the instance: _extract_fill_price sleeps
    # 1.5s + hits exchange.client; _set_cooldown_if_loss touches cooldown
    # dicts + notifier the bare bot doesn't have.
    b._extract_fill_price = MagicMock(return_value=103.85)
    b._set_cooldown_if_loss = MagicMock()

    monkeypatch.setattr(bot_module.notifier, "notify_exit", MagicMock())
    monkeypatch.setattr(bot_module.notifier, "send", MagicMock())

    def stop_after_first_sleep(_secs):
        b.running = False
    monkeypatch.setattr(bot_module.time, "sleep", stop_after_first_sleep)
    return b


# ---------------------------------------------------------------------------
# B. Single iteration: breach -> close once, watcher's reason, claim released
# ---------------------------------------------------------------------------

def test_breach_closes_once_with_watcher_reason(watcher_bot):
    b = watcher_bot
    pos = b.risk.positions[SYMBOL]

    b._live_exit_watcher_loop()

    b.exchange.close_long.assert_called_once_with(SYMBOL, pos.amount)
    b.exchange.close_short.assert_not_called()

    # close_position gets the fill price and the watcher's classified reason
    b.risk.close_position.assert_called_once_with(
        SYMBOL, 103.85, "trailing_stop", fees_usdt=0.0123)
    b._extract_fill_price.assert_called_once_with(
        {"id": "close-1", "symbol": SYMBOL}, 103.9, is_exit=True)
    b._set_cooldown_if_loss.assert_called_once_with(
        SYMBOL, pos.pnl_percent(103.85))
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    bot_module.notifier.notify_exit.assert_called_once()

    # Claim released after the close (finally block)
    assert b._closing == set()


def test_short_breach_uses_close_short(watcher_bot):
    b = watcher_bot
    pos = _make_position(side="short", stop_loss=101.2, take_profit=98.4,
                         margin=100.0)
    b.risk.positions = {SYMBOL: pos}
    b._ws_feed.last_price.return_value = (101.5, 1.0)  # short hard-SL breach

    b._live_exit_watcher_loop()

    b.exchange.close_short.assert_called_once_with(SYMBOL, pos.amount)
    b.exchange.close_long.assert_not_called()
    b.risk.close_position.assert_called_once_with(
        SYMBOL, 103.85, "stop_loss", fees_usdt=0.0123)
    assert b._closing == set()


# ---------------------------------------------------------------------------
# C. Double-close prevention: pre-claimed symbol is skipped entirely
# ---------------------------------------------------------------------------

def test_preclaimed_symbol_is_skipped_with_no_exchange_calls(watcher_bot):
    b = watcher_bot
    b._closing.add(SYMBOL)  # 60s cycle (or a prior watcher pass) owns the close

    b._live_exit_watcher_loop()

    b.exchange.close_long.assert_not_called()
    b.exchange.close_short.assert_not_called()
    b.risk.close_position.assert_not_called()
    b.exchange.cancel_open_orders.assert_not_called()
    # The watcher must NOT discard a claim it didn't make
    assert SYMBOL in b._closing
    assert SYMBOL in b.risk.positions


# ---------------------------------------------------------------------------
# D. Stale / missing WS price -> no action (cycle stays the authority)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lp", [(103.9, 11.0), None],
                         ids=["age_over_10s", "no_ws_data"])
def test_stale_or_missing_ws_price_takes_no_action(watcher_bot, lp):
    b = watcher_bot
    b._ws_feed.last_price.return_value = lp  # breach price but stale / absent

    b._live_exit_watcher_loop()

    b.exchange.close_long.assert_not_called()
    b.exchange.close_short.assert_not_called()
    b.risk.close_position.assert_not_called()
    assert SYMBOL in b.risk.positions
    assert b._closing == set()


# ---------------------------------------------------------------------------
# E. Close order returns None -> position intact, claim released
# ---------------------------------------------------------------------------

def test_failed_close_order_leaves_position_and_releases_claim(watcher_bot):
    b = watcher_bot
    b.exchange.close_long.return_value = None  # order rejected / API failure

    b._live_exit_watcher_loop()

    b.exchange.close_long.assert_called_once()
    b.risk.close_position.assert_not_called()
    b.exchange.cancel_open_orders.assert_not_called()
    bot_module.notifier.notify_exit.assert_not_called()
    assert SYMBOL in b.risk.positions          # cycle will retry
    assert b._closing == set()                 # claim released in finally


# ---------------------------------------------------------------------------
# F. ws_feed.last_price accessor
# ---------------------------------------------------------------------------

def test_last_price_returns_close_and_age_when_cached():
    feed = WSDataFeed([SYMBOL], "1m")  # light __init__, no network until start()
    feed._cache[SYMBOL] = [
        [1718000000000, 1.0, 2.0, 0.5, 1.4, 50.0],
        [1718000060000, 1.4, 2.1, 1.0, 1.5, 100.0],
    ]
    feed._last_update[SYMBOL] = real_time.time() - 3.0

    result = feed.last_price(SYMBOL)
    assert result is not None
    price, age = result
    assert price == 1.5            # forming-candle close of the LAST candle
    assert 2.5 <= age <= 10.0      # ~3s old (loose bound for slow CI)


def test_last_price_returns_none_when_empty_or_partial():
    feed = WSDataFeed([SYMBOL], "1m")
    assert feed.last_price(SYMBOL) is None            # nothing cached
    assert feed.last_price("DOGE/USDT:USDT") is None  # unknown symbol

    feed._cache[SYMBOL] = [[1718000000000, 1.0, 2.0, 0.5, 1.5, 100.0]]
    assert feed.last_price(SYMBOL) is None  # candles but no _last_update yet

    feed._cache[SYMBOL] = []
    feed._last_update[SYMBOL] = real_time.time()
    assert feed.last_price(SYMBOL) is None  # update ts but empty candle list


# ---------------------------------------------------------------------------
# G. Flag gating
# ---------------------------------------------------------------------------
# NOTE: invoking Phmex2Bot.start() under mocks is impractical (exchange
# position sync, scanner threads, SIGALRM handlers, the main cycle loop), so
# the spawn gate is verified at source level: the Thread(...) spawn for
# _live_exit_watcher_loop must sit directly under the
# `Config.is_live() and Config.LIVE_EXIT_WATCHER and self._ws_feed` guard.
# This catches accidental removal of the kill-switch without running start().

def test_watcher_spawn_is_gated_by_live_mode_and_flag_in_source():
    with open(BOT_PY) as f:
        src = f.read()
    spawn_idx = src.index("target=self._live_exit_watcher_loop")
    guard_region = src[max(0, spawn_idx - 400):spawn_idx]
    assert "if Config.is_live() and Config.LIVE_EXIT_WATCHER and self._ws_feed:" in guard_region, (
        "Watcher thread spawn is no longer guarded by the live-mode + "
        "LIVE_EXIT_WATCHER flag conditional — kill switch broken?")


def test_live_exit_watcher_flag_is_boolean():
    # Parsed at import from LIVE_EXIT_WATCHER env (default "true").
    assert isinstance(Config.LIVE_EXIT_WATCHER, bool)
