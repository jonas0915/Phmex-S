"""monitor_daemon paper-main exclusion (2026-08-26 main-book demotion).

Two layers under test:
1. Log layer — paper-main closes now log "[PAPER] Position closed: ..."
   (bot.py _close_paper_main borrows the slot wrapper's _log_prefix), so the
   daemon's existing "[PAPER]" match catches them.
2. State layer (belt) — even if the log format drifts, exit lines matching a
   mode=="paper" row in trading_state.json are excluded from hourly-loss and
   consecutive-loss-streak alerts, and paper-tagged open positions never
   count toward the drawdown-suppression locked-margin sum.
"""
import json
import logging
import os
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import monitor_daemon
import bot as bot_module
from bot import Phmex2Bot, _sim_paper_fee
from risk_manager import Position, RiskManager

SYMBOL = "BTC/USDT:USDT"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exit_line(sym=SYMBOL, side="LONG", pnl=-1.50, paper_marker=False,
               ts="2026-08-26 10:00:00"):
    """A risk_manager-format 'Position closed' log line."""
    prefix = "[PAPER] " if paper_marker else ""
    sign = "+" if pnl >= 0 else ""
    return (f"{ts} [INFO] {prefix}Position closed: {side} {sym} | "
            f"Exit: 100.0000 | PnL: {sign}{pnl:.2f} USDT ({sign}{pnl:.2f}%) | "
            f"Reason: stop_loss")


def _paper_state_row(sym=SYMBOL, pnl=-1.50, closed_at=None):
    return {"symbol": sym, "side": "long", "pnl_usdt": pnl, "mode": "paper",
            "closed_at": closed_at if closed_at is not None else time.time()}


def _make_position(**overrides):
    base = dict(symbol=SYMBOL, side="long", entry_price=100.0, amount=1.0,
                margin=10.0, stop_loss=98.8, take_profit=101.6)
    base.update(overrides)
    return Position(**base)


def _bare_rm():
    """RiskManager without __init__ side effects (mirrors test_paper_main)."""
    rm = RiskManager.__new__(RiskManager)
    rm.positions = {}
    rm.closed_trades = []
    rm.trade_results = []
    rm.peak_balance = 0.0
    rm.is_paper = False          # MAIN convention: stays False even in paper mode
    rm._log_prefix = ""
    rm._save_state = lambda: None
    return rm


def _bare_bot(rm=None):
    b = object.__new__(Phmex2Bot)
    b.risk = rm if rm is not None else _bare_rm()
    b.exchange = MagicMock()
    b.slots = []
    b.cycle_count = 7
    b._pos_lock = threading.Lock()
    b._closing = set()
    b._tp_skip_since = {}
    b._pair_cooldown = {}
    b._pair_loss_streak = {}
    b._trade_results = __import__("collections").deque(maxlen=5)
    b._regime_pause_until = 0.0
    b._persist_trade_results = lambda: None
    return b


# ---------------------------------------------------------------------------
# 1. Log layer — [PAPER]-marked exits excluded (bot.py contract)
# ---------------------------------------------------------------------------

def test_paper_marked_exit_excluded_from_hourly_exits():
    lines = [_exit_line(pnl=-3.0, paper_marker=True), _exit_line(pnl=-1.0)]
    entries, exits = monitor_daemon.analyze_recent_trades(lines)
    assert len(exits) == 1
    assert monitor_daemon.parse_pnl(exits[0]) == pytest.approx(-1.0)
    # Hourly-loss aggregation (run_monitor step 4) therefore sums real only
    assert sum(monitor_daemon.parse_pnl(e) for e in exits) == pytest.approx(-1.0)


def test_paper_main_close_log_line_carries_paper_marker(monkeypatch, caplog):
    """bot.py _close_paper_main must emit the exact '[PAPER] Position closed'
    format the daemon matches (mirrors slot paper closes)."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos
    monkeypatch.setattr(bot_module.notifier, "notify_paper_exit", MagicMock())

    with caplog.at_level(logging.INFO, logger="DegenCryt"):
        b._close_paper_main(SYMBOL, pos, 99.0, "stop_loss")

    closed = [r.getMessage() for r in caplog.records
              if "Position closed" in r.getMessage()]
    assert len(closed) == 1
    assert closed[0].startswith("[PAPER] Position closed:")
    # Daemon contract: excluded with no state help needed
    assert monitor_daemon.is_paper_exit_line(closed[0]) is True
    _, exits = monitor_daemon.analyze_recent_trades(closed)
    assert exits == []
    # Prefix restored — the next real close logs clean
    assert rm._log_prefix == ""


def test_real_close_log_line_unchanged(caplog):
    """Real-money closes keep the unmarked format and still count."""
    rm = _bare_rm()
    rm.positions[SYMBOL] = _make_position()

    with caplog.at_level(logging.INFO, logger="DegenCryt"):
        rm.close_position(SYMBOL, 99.0, "stop_loss", fees_usdt=0.01)

    closed = [r.getMessage() for r in caplog.records
              if "Position closed" in r.getMessage()]
    assert len(closed) == 1
    assert not closed[0].startswith("[PAPER]")
    assert monitor_daemon.is_paper_exit_line(closed[0]) is False
    _, exits = monitor_daemon.analyze_recent_trades(closed)
    assert len(exits) == 1


def test_close_paper_main_restores_prefix_on_error(monkeypatch):
    """The [PAPER] prefix swap must not leak if close_position raises."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos
    monkeypatch.setattr(rm, "close_position",
                        MagicMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        b._close_paper_main(SYMBOL, pos, 99.0, "stop_loss")
    assert rm._log_prefix == ""


# ---------------------------------------------------------------------------
# 2. State layer — belt vs log-format drift
# ---------------------------------------------------------------------------

def test_recent_paper_closes_reads_state_rows():
    now = time.time()
    state = {"closed_trades": [
        _paper_state_row(pnl=-1.5, closed_at=now),              # in window
        _paper_state_row(pnl=-9.0, closed_at=now - 4 * 3600),   # too old
        {"symbol": SYMBOL, "pnl_usdt": -2.0, "closed_at": now},  # real, no mode
    ]}
    keys = monitor_daemon.recent_paper_closes(minutes=180, state=state)
    assert keys == {(SYMBOL, -1.5)}


def test_recent_paper_closes_reads_state_file(tmp_path, monkeypatch):
    path = tmp_path / "trading_state.json"
    path.write_text(json.dumps({"closed_trades": [_paper_state_row(pnl=-0.75)]}))
    monkeypatch.setattr(monitor_daemon, "STATE_FILE", str(path))
    assert monitor_daemon.recent_paper_closes(minutes=180) == {(SYMBOL, -0.75)}


def test_unmarked_paper_exit_dropped_via_state_match():
    """Log-drift scenario: a paper close line WITHOUT the [PAPER] marker is
    still excluded because a mode=='paper' state row matches (symbol, pnl)."""
    paper_closes = {(SYMBOL, -3.0)}
    lines = [_exit_line(pnl=-3.0), _exit_line(pnl=-1.0)]
    _, exits = monitor_daemon.analyze_recent_trades(lines, paper_closes)
    assert len(exits) == 1
    assert monitor_daemon.parse_pnl(exits[0]) == pytest.approx(-1.0)


def test_streak_ignores_paper_losses_marked_and_state_matched():
    """Consecutive-loss streak counts real losses only: 3 paper losses (one
    marked, two state-matched) between real trades must not inflate it."""
    paper_closes = {(SYMBOL, -2.0)}
    lines = [
        _exit_line(pnl=1.0),                       # real win — breaks streak
        _exit_line(pnl=-4.0, paper_marker=True),   # paper (marked)
        _exit_line(pnl=-2.0),                      # paper (state-matched)
        _exit_line(pnl=-2.0),                      # paper (state-matched)
        _exit_line(pnl=-1.0),                      # real loss
        _exit_line(pnl=-0.5),                      # real loss
    ]
    assert monitor_daemon.check_consecutive_losses(lines, paper_closes) == 2


def test_streak_unchanged_without_paper_activity():
    """Regression: no paper rows => same answer as the historical behavior."""
    lines = [_exit_line(pnl=1.0), _exit_line(pnl=-1.0), _exit_line(pnl=-1.2)]
    assert monitor_daemon.check_consecutive_losses(lines) == 2
    assert monitor_daemon.check_consecutive_losses(lines, set()) == 2


def test_parse_symbol():
    assert monitor_daemon.parse_symbol(_exit_line(sym="ETH/USDT:USDT")) == "ETH/USDT:USDT"
    assert monitor_daemon.parse_symbol("garbage line") is None


# ---------------------------------------------------------------------------
# 3. Drawdown suppression — locked margin excludes paper positions
# ---------------------------------------------------------------------------

def test_locked_real_margin_excludes_paper_positions():
    positions = {
        "ETH/USDT:USDT": {"margin": 15.0, "paper": False},
        "SOL/USDT:USDT": {"margin": 15.0, "paper": True},   # sim: no real margin
        "OLD/USDT:USDT": {"margin": 10.0},                  # historical: no tag
        "JUNK": "not-a-dict",
    }
    assert monitor_daemon.locked_real_margin(positions) == pytest.approx(25.0)


def test_locked_real_margin_empty():
    assert monitor_daemon.locked_real_margin({}) == 0
