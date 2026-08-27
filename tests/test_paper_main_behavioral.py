"""Behavioral paper-guard tests for the MAIN book (.paper_main era, 2026-08-26).

Closes the audit gaps left by the source-text-presence tests in
test_paper_main.py: instead of asserting the guard EXISTS in bot.py source,
these tests EXECUTE the real in-cycle block code (extracted verbatim from
_run_cycle / start by the same comment markers the textual tests key on,
compiled and run against a real Phmex2Bot object with a MagicMock exchange).

Covered behaviorally, paper AND live mirror for each:
  1. In-cycle blocks: partial-TP, SL-verify sweep, durable-trail
     move_stop_loss, startup-restore place_sl_tp.
  2. Exit reasons: trend-flip, adverse_exit, time_exit, software-SL/TP
     to_close routing. (The watcher path is already behavioral in
     test_paper_main.py::test_watcher_paper_position_simulated_close.)
  3. Holistic no-op regression: with NO sentinel and NO paper tags, the entry
     decision path, the exit loop, and the reconciler behave exactly as
     pre-build — exchange mocks called as before, sentinel never consulted on
     position-keyed paths.
  4. adjudicate.grade_main_resize15: partial-TP groups (symbol+opened_at) are
     mode-homogeneous — a paper pair is fully excluded, a real pair fully
     counted, and a leaked mixed group can never be half-counted.

If a block's marker comments are renamed in bot.py, _cycle_block raises — the
test fails loudly rather than silently testing nothing.
"""
import inspect
import os
import sys
import textwrap
import time
from unittest.mock import MagicMock

import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

import bot as bot_module
from bot import Phmex2Bot, _build_position_owners
from config import Config
from lab_adjudicator import adjudicate as adj

# Reuse the established fixtures/helpers from the existing paper-main tests.
from test_paper_main import SYMBOL, _bare_bot, _bare_rm, _make_position, _signal

ETH = "ETH/USDT:USDT"


# ---------------------------------------------------------------------------
# Block driver — executes REAL production code slices from bot.py
# ---------------------------------------------------------------------------

def _cycle_block(start: str, end: str, method=None) -> str:
    """Extract the verbatim source between two marker lines of a bot method
    (default _run_cycle). Raises StopIteration if a marker is missing —
    a renamed block fails these tests loudly instead of skipping silently."""
    src = inspect.getsource(method if method is not None else Phmex2Bot._run_cycle)
    lines = src.splitlines(keepends=True)
    si = next(i for i, l in enumerate(lines) if start in l)
    ei = next(i for i, l in enumerate(lines) if end in l and i > si)
    return textwrap.dedent("".join(lines[si:ei]))


def _drive_block(b, start: str, end: str, method=None, wrap_loop=False, **extra):
    """Compile and execute a production block against bot instance `b`.
    Module globals (logger, notifier, Config, _sim_paper_fee, ...) resolve to
    bot.py's own — monkeypatches on bot_module apply. `extra` supplies the
    loop-local names the block expects (prices, ohlcv_cache, symbol, ...).
    wrap_loop wraps the slice in a one-pass loop so bare `continue` compiles
    (used for slices cut out of the entry for-loop). Returns the namespace."""
    block = _cycle_block(start, end, method)
    if wrap_loop:
        block = "for _once in (0,):\n" + textwrap.indent(block, "    ")
    ns = {**vars(bot_module), "self": b, **extra}
    exec(compile(block, "bot.py::" + start.strip("# ").split(" ")[0], "exec"), ns)
    return ns


def _mock_notifier(monkeypatch, *names):
    mocks = {}
    for n in names:
        m = MagicMock()
        monkeypatch.setattr(bot_module.notifier, n, m)
        mocks[n] = m
    return mocks


# ---------------------------------------------------------------------------
# 1a. Partial take-profit block (bot.py ~1667-1739)
# ---------------------------------------------------------------------------

PARTIAL_START = "# Partial take-profit — scale out half"
PARTIAL_END = "# Early exit check — momentum reversal"


def test_partial_tp_paper_no_exchange_and_mode_paper(monkeypatch):
    monkeypatch.setattr(Config, "PARTIAL_TP_ROI", 10.0)
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_partial_tp")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position(amount=2.0, margin=20.0)
    pos.paper = True
    rm.positions[SYMBOL] = pos

    # entry 100, price 110, margin 20 -> ROI (10*2)/20*100 = 100% >= 10% trigger
    _drive_block(b, PARTIAL_START, PARTIAL_END, prices={SYMBOL: 110.0})

    assert b.exchange.method_calls == []      # no half-close order, nothing
    row = rm.closed_trades[-1]
    assert row["mode"] == "paper"
    assert row["reason"] == "partial_tp"
    assert row["exit_price"] == 110.0
    # Runner half remains open, still paper-tagged
    assert rm.positions[SYMBOL].amount == pytest.approx(1.0)
    assert rm.positions[SYMBOL].paper is True
    assert rm.positions[SYMBOL].scaled_out is True
    nm["notify_paper_exit"].assert_called_once()
    assert nm["notify_paper_exit"].call_args.kwargs.get("slot") == "main"
    nm["notify_partial_tp"].assert_not_called()


def test_partial_tp_live_reaches_exchange(monkeypatch):
    """Mirror: an untagged position DOES place the real half-close order and
    the runner-TP cancel — live behavior unchanged."""
    monkeypatch.setattr(Config, "PARTIAL_TP_ROI", 10.0)
    monkeypatch.setattr(Config, "PARTIAL_RUNNER_TP_ROI", 25.0)
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_partial_tp")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position(amount=2.0, margin=20.0, tp_order_id="tp-1")
    rm.positions[SYMBOL] = pos
    b.exchange.close_long.return_value = {"id": "half-1"}
    b.exchange.extract_order_fee.return_value = 0.05
    b.exchange.cancel_order_by_id.return_value = True
    b._extract_fill_price = MagicMock(return_value=110.0)

    _drive_block(b, PARTIAL_START, PARTIAL_END, prices={SYMBOL: 110.0})

    b.exchange.close_long.assert_called_once_with(SYMBOL, 1.0)
    row = rm.closed_trades[-1]
    assert row["reason"] == "partial_tp"
    assert "mode" not in row                  # real row: no mode field ever
    b.exchange.cancel_order_by_id.assert_called_once_with(SYMBOL, "tp-1")
    assert pos.tp_order_id == "software"
    nm["notify_partial_tp"].assert_called_once()
    nm["notify_paper_exit"].assert_not_called()


# ---------------------------------------------------------------------------
# 1b. SL-verify sweep (bot.py ~1882-1904)
# ---------------------------------------------------------------------------

SLVERIFY_START = "# Verify SL orders still active"
SLVERIFY_END = "# Time-based exit — close stale positions"


def test_sl_verify_paper_never_touches_exchange():
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position(sl_order_id="sl-1")   # NOT "software" — would be verified if live
    pos.paper = True
    rm.positions[SYMBOL] = pos

    _drive_block(b, SLVERIFY_START, SLVERIFY_END)

    # Guard fires before verify_sl_order: zero exchange interaction of any kind
    assert b.exchange.method_calls == []
    assert pos.sl_order_id == "sl-1"           # untouched


def test_sl_verify_live_replaces_missing_sl():
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position(sl_order_id="sl-1")   # untagged
    rm.positions[SYMBOL] = pos
    b.exchange.verify_sl_order.return_value = False
    b.exchange.place_sl_tp.return_value = {"sl_order_id": "sl-2", "tp_order_id": "tp-2"}

    _drive_block(b, SLVERIFY_START, SLVERIFY_END)

    b.exchange.verify_sl_order.assert_called_once_with(SYMBOL, "sl-1")
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    b.exchange.place_sl_tp.assert_called_once_with(SYMBOL, "long", 1.0, 98.8, 101.6)
    assert pos.sl_order_id == "sl-2"
    assert pos.exchange_sl_price == 98.8


# ---------------------------------------------------------------------------
# 1c. Durable-trail move_stop_loss ratchet (bot.py ~1939-1991)
# ---------------------------------------------------------------------------

TRAIL_START = "# Break-even and trailing stop updates"
TRAIL_END = "# Check exit conditions for open positions"


def test_durable_trail_paper_ratchets_software_but_never_amends(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position(sl_order_id="sl-1", exchange_sl_price=98.8)
    pos.paper = True
    rm.positions[SYMBOL] = pos

    # price 110 >= entry + 1R (101.2) -> check_breakeven lifts SL to 100.25
    _drive_block(b, TRAIL_START, TRAIL_END, prices={SYMBOL: 110.0})

    # Software level DID ratchet (guard sits after check_breakeven)...
    assert pos.stop_loss == pytest.approx(100.25)
    # ...but the exchange was never amended — no order exists to amend.
    b.exchange.move_stop_loss.assert_not_called()
    assert b.exchange.method_calls == []
    assert pos.exchange_sl_price == 98.8       # unchanged
    assert pos.sl_ratcheted is False


def test_durable_trail_live_moves_stop_loss(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position(sl_order_id="sl-1", exchange_sl_price=98.8)  # untagged
    rm.positions[SYMBOL] = pos
    b.exchange.move_stop_loss.return_value = "sl-2"

    _drive_block(b, TRAIL_START, TRAIL_END, prices={SYMBOL: 110.0})

    b.exchange.move_stop_loss.assert_called_once()
    args = b.exchange.move_stop_loss.call_args.args
    assert args[0] == SYMBOL and args[1] == "long" and args[2] == 1.0
    assert args[3] == pytest.approx(100.25)    # breakeven target
    assert args[4] == "sl-1"
    assert pos.sl_order_id == "sl-2"
    assert pos.exchange_sl_price == pytest.approx(100.25)
    assert pos.sl_ratcheted is True


# ---------------------------------------------------------------------------
# 1d. Startup restore place_sl_tp (bot.py start(), ~1142-1156)
# ---------------------------------------------------------------------------

STARTUP_START = "# Place exchange SL/TP for synced positions"
STARTUP_END = "# Add synced symbols to active pairs"


def test_startup_restore_paper_skipped_live_gets_sl_tp():
    """One restored paper position + one restored live position: the live one
    gets exchange SL/TP re-placed, the paper phantom NEVER does."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    paper_pos = _make_position(sl_order_id=None)
    paper_pos.paper = True
    live_pos = _make_position(symbol=ETH, sl_order_id=None)
    rm.positions = {SYMBOL: paper_pos, ETH: live_pos}
    b.exchange.place_sl_tp.return_value = {"sl_order_id": "sl-x", "tp_order_id": "tp-x"}

    _drive_block(b, STARTUP_START, STARTUP_END, method=Phmex2Bot.start)

    assert b.exchange.place_sl_tp.call_count == 1
    assert b.exchange.place_sl_tp.call_args.args[0] == ETH
    b.exchange.cancel_open_orders.assert_called_once_with(ETH)
    assert paper_pos.sl_order_id is None       # phantom left alone
    assert live_pos.sl_order_id == "sl-x"
    assert live_pos.exchange_sl_price == 98.8


# ---------------------------------------------------------------------------
# 2. Exit reasons — trend-flip, adverse_exit, time_exit, software SL/TP loop
#    (watcher path is already behavioral in test_paper_main.py)
# ---------------------------------------------------------------------------

FLIP_START = "# Trend-flip exit"
FLIP_END = "# Adverse exit — bail out"
ADV_START = "# Adverse exit — bail out"
ADV_END = "# Shadow adverse-exit logging"
TIME_START = "# Time-based exit — close stale positions"
TIME_END = "# Break-even and trailing stop updates"
TOCLOSE_START = "# Check exit conditions for open positions"
TOCLOSE_END = "# Part B shadow-logger"


def _flip_stub(side, htf_df):
    return True, "trend_flip_exit"


def test_trend_flip_paper_close_no_exchange(monkeypatch):
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    b._htf_cache = {SYMBOL: (None, 0.0)}
    pos = _make_position(strategy="htf_confluence_pullback")
    pos.paper = True
    rm.positions[SYMBOL] = pos

    _drive_block(b, FLIP_START, FLIP_END, prices={SYMBOL: 99.0},
                 _check_htf_trend_flip_exit=_flip_stub)

    assert b.exchange.method_calls == []
    row = rm.closed_trades[-1]
    assert row["mode"] == "paper"
    assert row["reason"] == "trend_flip_exit"
    assert row["exit_price"] == 99.0
    nm["notify_paper_exit"].assert_called_once()
    nm["notify_exit"].assert_not_called()


def test_trend_flip_live_real_close(monkeypatch):
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    b._htf_cache = {SYMBOL: (None, 0.0)}
    pos = _make_position(strategy="htf_confluence_pullback")   # untagged
    rm.positions[SYMBOL] = pos
    b.exchange.close_long.return_value = {"id": "c1"}
    b.exchange.extract_order_fee.return_value = 0.02
    b._extract_fill_price = MagicMock(return_value=99.0)

    _drive_block(b, FLIP_START, FLIP_END, prices={SYMBOL: 99.0},
                 _check_htf_trend_flip_exit=_flip_stub)

    b.exchange.close_long.assert_called_once_with(SYMBOL, 1.0)
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    row = rm.closed_trades[-1]
    assert row["reason"] == "trend_flip_exit"
    assert "mode" not in row
    nm["notify_exit"].assert_called_once()
    nm["notify_paper_exit"].assert_not_called()


def test_adverse_exit_paper_close_no_exchange(monkeypatch):
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    pos.should_adverse_exit = lambda cycle, price: True
    rm.positions[SYMBOL] = pos

    _drive_block(b, ADV_START, ADV_END, prices={SYMBOL: 99.0})

    assert b.exchange.method_calls == []
    row = rm.closed_trades[-1]
    assert row["mode"] == "paper"
    assert row["reason"] == "adverse_exit"
    nm["notify_paper_exit"].assert_called_once()
    nm["notify_exit"].assert_not_called()


def test_adverse_exit_live_real_close(monkeypatch):
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()                      # untagged
    pos.should_adverse_exit = lambda cycle, price: True
    rm.positions[SYMBOL] = pos
    b.exchange.close_long.return_value = {"id": "c1"}
    b.exchange.extract_order_fee.return_value = 0.02
    b._extract_fill_price = MagicMock(return_value=99.0)

    _drive_block(b, ADV_START, ADV_END, prices={SYMBOL: 99.0})

    b.exchange.close_long.assert_called_once_with(SYMBOL, 1.0)
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    row = rm.closed_trades[-1]
    assert row["reason"] == "adverse_exit"
    assert "mode" not in row
    nm["notify_exit"].assert_called_once()


def test_time_exit_paper_close_no_exchange(monkeypatch):
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    pos.should_time_exit = lambda cycle, current_price=0.0: (True, False)  # soft
    rm.positions[SYMBOL] = pos

    # price 99 -> in the red, soft exit fires as "time_exit"
    _drive_block(b, TIME_START, TIME_END, prices={SYMBOL: 99.0})

    assert b.exchange.method_calls == []
    row = rm.closed_trades[-1]
    assert row["mode"] == "paper"
    assert row["reason"] == "time_exit"
    nm["notify_paper_exit"].assert_called_once()
    nm["notify_exit"].assert_not_called()


def test_time_exit_live_real_close(monkeypatch):
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()                      # untagged
    pos.should_time_exit = lambda cycle, current_price=0.0: (True, False)
    rm.positions[SYMBOL] = pos
    b.exchange.close_long.return_value = {"id": "c1"}
    b.exchange.extract_order_fee.return_value = 0.02
    b._extract_fill_price = MagicMock(return_value=99.0)

    _drive_block(b, TIME_START, TIME_END, prices={SYMBOL: 99.0})

    b.exchange.close_long.assert_called_once_with(SYMBOL, 1.0, urgent=False)
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    row = rm.closed_trades[-1]
    assert row["reason"] == "time_exit"
    assert "mode" not in row
    nm["notify_exit"].assert_called_once()


def test_software_sltp_loop_routes_paper_to_sim_close(monkeypatch):
    """The cycle's to_close loop itself (not a hand call) must route a paper
    SL breach to _close_paper_main with zero exchange interaction."""
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos

    _drive_block(b, TOCLOSE_START, TOCLOSE_END, prices={SYMBOL: 98.5})

    assert b.exchange.method_calls == []
    row = rm.closed_trades[-1]
    assert row["mode"] == "paper"
    assert row["reason"] == "stop_loss"
    assert row["exit_price"] == 98.5
    nm["notify_paper_exit"].assert_called_once()
    nm["notify_exit"].assert_not_called()


# ---------------------------------------------------------------------------
# Entry decision path — behavioral both ways (sentinel present / absent)
# ---------------------------------------------------------------------------

ENTRY_START = "if _main_paper():"
ENTRY_END = "if order:"


def _entry_ns(b, **overrides):
    ns = dict(
        symbol=SYMBOL, direction="long", margin=15.0, price=100.0,
        atr_val=0.0, regime="medium", strat_name="confluence",
        signal=_signal(), confidence=5, layers=["rsi", "macd"],
        htf_df=None, df=MagicMock(), ob=None, flow=None,
        _shadow_gates={}, available=100.0,
    )
    ns.update(overrides)
    return ns


def test_entry_branch_sentinel_present_no_open_order(monkeypatch):
    """With _main_paper() True, the REAL entry-loop branch routes to the paper
    helper and the exchange sees nothing — behavioral upgrade of the
    source-index test in test_paper_main.py."""
    b = _bare_bot()
    paper_pos = MagicMock(margin=15.0)
    b._open_paper_main_position = MagicMock(return_value=paper_pos)
    b._log_entry_snapshot = MagicMock(return_value={})

    ns = _drive_block(b, ENTRY_START, ENTRY_END, wrap_loop=True,
                      _main_paper=lambda bot_dir=".": True, **_entry_ns(b))

    assert b.exchange.method_calls == []       # no open_long/short, no SL/TP
    b._open_paper_main_position.assert_called_once()
    call = b._open_paper_main_position.call_args
    assert call.args[:4] == (SYMBOL, "long", 15.0, 100.0)
    assert "order" not in ns                   # paper branch continue'd out


def test_entry_branch_no_sentinel_reaches_real_order(tmp_path, monkeypatch):
    """Holistic no-op (entry): no .paper_main on disk -> the REAL _main_paper
    is consulted once, returns False, and the exchange open_long fires with
    the exact pre-build arguments."""
    monkeypatch.chdir(tmp_path)                # no sentinel anywhere
    spy = MagicMock(wraps=bot_module._main_paper)
    b = _bare_bot()
    b._open_paper_main_position = MagicMock()
    b.exchange.open_long.return_value = {"id": "entry-1"}

    ns = _drive_block(b, ENTRY_START, ENTRY_END, wrap_loop=True,
                      _main_paper=spy, **_entry_ns(b))

    assert spy.call_count == 1
    b.exchange.open_long.assert_called_once_with(SYMBOL, 15.0, 100.0)
    b.exchange.open_short.assert_not_called()
    b._open_paper_main_position.assert_not_called()
    assert ns["order"] == {"id": "entry-1"}


# ---------------------------------------------------------------------------
# 3. Holistic no-op regression — no sentinel, no tags: pre-build behavior
# ---------------------------------------------------------------------------

def test_no_sentinel_exit_loop_identical_and_never_consults_sentinel(monkeypatch):
    """Untagged position, SL breach: the to_close loop places the real market
    close exactly as pre-build, the row carries NO mode field, and the
    sentinel helper is never consulted anywhere on the exit path."""
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    sentinel_spy = MagicMock(wraps=bot_module._main_paper)
    monkeypatch.setattr(bot_module, "_main_paper", sentinel_spy)
    nm = _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit")
    rm = _bare_rm()
    b = _bare_bot(rm)
    rm.positions[SYMBOL] = _make_position()    # untagged
    b.exchange.close_long.return_value = {"id": "c1"}
    b.exchange.extract_order_fee.return_value = 0.03
    b._extract_fill_price = MagicMock(return_value=98.5)

    _drive_block(b, TOCLOSE_START, TOCLOSE_END, prices={SYMBOL: 98.5})

    b.exchange.close_long.assert_called_once_with(SYMBOL, 1.0, urgent=True)
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    row = rm.closed_trades[-1]
    assert row["reason"] == "stop_loss"
    assert "mode" not in row                   # real rows never gain a mode key
    nm["notify_exit"].assert_called_once()
    nm["notify_paper_exit"].assert_not_called()
    assert sentinel_spy.call_count == 0        # exits key on the tag, never the sentinel


def test_no_sentinel_reconciler_owners_include_all_mains(monkeypatch):
    """Untagged book: _build_position_owners returns every main position for
    reconciliation, exactly as pre-build, without consulting the sentinel."""
    sentinel_spy = MagicMock(wraps=bot_module._main_paper)
    monkeypatch.setattr(bot_module, "_main_paper", sentinel_spy)
    rm = _bare_rm()
    rm.positions = {SYMBOL: _make_position(), ETH: _make_position(symbol=ETH)}

    owners = _build_position_owners(rm, [])

    assert owners == {SYMBOL: (rm, None), ETH: (rm, None)}
    assert sentinel_spy.call_count == 0


def test_no_sentinel_untagged_blocks_all_reach_exchange(monkeypatch):
    """Sweep the four guarded blocks with an untagged position and no
    sentinel: every one reaches its real exchange call (pre-build behavior),
    and none consults the sentinel."""
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    monkeypatch.setattr(Config, "PARTIAL_TP_ROI", 10.0)
    monkeypatch.setattr(Config, "PARTIAL_RUNNER_TP_ROI", 0.0)
    sentinel_spy = MagicMock(wraps=bot_module._main_paper)
    monkeypatch.setattr(bot_module, "_main_paper", sentinel_spy)
    _mock_notifier(monkeypatch, "notify_paper_exit", "notify_exit",
                   "notify_partial_tp")

    # partial-TP
    rm = _bare_rm(); b = _bare_bot(rm)
    rm.positions[SYMBOL] = _make_position(amount=2.0, margin=20.0)
    b.exchange.close_long.return_value = {"id": "o"}
    b.exchange.extract_order_fee.return_value = 0.05
    b._extract_fill_price = MagicMock(return_value=110.0)
    _drive_block(b, PARTIAL_START, PARTIAL_END, prices={SYMBOL: 110.0})
    b.exchange.close_long.assert_called_once()

    # SL-verify
    rm = _bare_rm(); b = _bare_bot(rm)
    rm.positions[SYMBOL] = _make_position(sl_order_id="sl-1")
    b.exchange.verify_sl_order.return_value = True
    _drive_block(b, SLVERIFY_START, SLVERIFY_END)
    b.exchange.verify_sl_order.assert_called_once_with(SYMBOL, "sl-1")

    # durable trail
    rm = _bare_rm(); b = _bare_bot(rm)
    rm.positions[SYMBOL] = _make_position(sl_order_id="sl-1", exchange_sl_price=98.8)
    b.exchange.move_stop_loss.return_value = "sl-2"
    _drive_block(b, TRAIL_START, TRAIL_END, prices={SYMBOL: 110.0})
    b.exchange.move_stop_loss.assert_called_once()

    # startup restore
    rm = _bare_rm(); b = _bare_bot(rm)
    rm.positions[SYMBOL] = _make_position(sl_order_id=None)
    b.exchange.place_sl_tp.return_value = {"sl_order_id": "s", "tp_order_id": "t"}
    _drive_block(b, STARTUP_START, STARTUP_END, method=Phmex2Bot.start)
    b.exchange.place_sl_tp.assert_called_once()

    assert sentinel_spy.call_count == 0


# ---------------------------------------------------------------------------
# 4. adjudicate.grade_main_resize15 — partial-TP groups are mode-homogeneous
# ---------------------------------------------------------------------------

CFG = {"deployed_ts": 1_786_333_620.0,  # 8/9/2026 8:47 PM PT (same as tripwire tests)
       "trip_n": 10, "trip_net": -3.0, "hard_net": -6.0, "min_margin": 10.0}


def _row(net, margin=7.5, opened_off=100, symbol="BTC/USDT", mode=None):
    r = {"strategy": "htf_l2_anticipation", "exit_reason": "partial_tp",
         "symbol": symbol, "opened_at": CFG["deployed_ts"] + opened_off,
         "closed_at": CFG["deployed_ts"] + opened_off + 60,
         "net_pnl": net, "margin": margin}
    if mode is not None:
        r["mode"] = mode
    return r


def test_resize15_paper_pair_excluded_real_pair_counted(tmp_path):
    """Two partial-TP groups, one real, one paper: the paper pair (both
    halves tagged) is FULLY excluded, the real pair is FULLY counted as one
    grouped trade — groups stay mode-homogeneous."""
    real_pair = [_row(1.0, opened_off=100), _row(0.5, opened_off=100)]
    paper_pair = [_row(-4.0, opened_off=200, symbol="ETH/USDT", mode="paper"),
                  _row(-4.0, opened_off=200, symbol="ETH/USDT", mode="paper")]
    r = adj.grade_main_resize15(real_pair + paper_pair, CFG, bot_dir=str(tmp_path))
    assert r["n_trades"] == 1                       # only the real group
    assert r["net_usd"] == pytest.approx(1.5)       # sim -8 never entered
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".halt_main_entries")


def test_resize15_mixed_group_leak_never_half_counts(tmp_path):
    """Corruption case the 8/26 conventions forbid: ONE group (same
    symbol+opened_at) with a paper half and a real half. The paper half drops
    before grouping, the lone real half (margin 7.5 < min_margin 10) then
    fails the group margin floor — the group contributes NOTHING. A tag leak
    can therefore never half-count a trade into the real-money line, and no
    sentinel is written."""
    mixed = [_row(-5.0, opened_off=100),                    # real half
             _row(2.0, opened_off=100, mode="paper")]       # leaked paper half
    r = adj.grade_main_resize15(mixed, CFG, bot_dir=str(tmp_path))
    assert r["n_trades"] == 0
    assert r["net_usd"] == pytest.approx(0.0)
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".halt_main_entries")


def test_resize15_paper_flood_around_real_group_boundaries(tmp_path):
    """Real full-margin single + paper flood sharing NEITHER symbol nor
    opened_at with it: real trade counts exactly once with its own net; the
    flood (deep sim losses past both trip lines) writes no sentinel."""
    real = [_row(-2.0, margin=14.0, opened_off=100)]
    flood = [_row(-3.0, margin=14.0, opened_off=300 + i * 10, mode="paper")
             for i in range(12)]                    # sim net -36
    r = adj.grade_main_resize15(real + flood, CFG, bot_dir=str(tmp_path))
    assert r["n_trades"] == 1
    assert r["net_usd"] == pytest.approx(-2.0)
    assert r["status"] == adj.WATCH                 # -2.0 above both trip lines
    assert not os.path.exists(tmp_path / ".halt_main_entries")
