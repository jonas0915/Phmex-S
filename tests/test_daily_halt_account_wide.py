"""U3 (2026-07-23 safety bundle): ACCOUNT-WIDE daily loss halt.

Before: _should_halt_daily_loss read only the MAIN book's closed_trades, so
live-slot losses were invisible (100% of the 7/20-7/23 bleed was the HTF_L2
slot), and the check sat BELOW the _trading_paused / .halt_main_entries early
returns — unreachable during any pause/halt.

After: _today_net_all_books sums today's PT-date net across main PLUS every
slot's mode=="live" records; _maybe_daily_loss_halt is evaluated ABOVE those
early returns in _run_cycle. Threshold formula (max(3%, $5 floor)) and
.daily_loss_override semantics unchanged. The halt writes the .pause_trading
sentinel, which _slot_entries_blocked already enforces for slot entries.
"""
import inspect
import os
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import bot as botmod
import risk_manager
import strategy_slot
from config import Config
from strategy_slot import StrategySlot


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    return tmp_path


def _mk_slot(slot_id="HTF_L2"):
    return StrategySlot(
        slot_id=slot_id, strategy_name="htf_l2_anticipation",
        timeframe="5m", max_positions=2, capital_pct=0.0, paper_mode=True,
        loss_cap_usdt=-999.0, kelly_min_trades=10**9,
    )


def _bare_bot(slots=None, main_trades=None):
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = slots or []
    b.risk = SimpleNamespace(positions={}, closed_trades=main_trades or [],
                             _drawdown_pause_until=0.0)
    return b


def _trade(net, mode=None, closed_at=None):
    t = {"symbol": "ETH/USDT:USDT", "opened_at": time.time() - 600,
         "closed_at": closed_at if closed_at is not None else time.time(),
         "net_pnl": net, "pnl_usdt": net}
    if mode is not None:
        t["mode"] = mode
    return t


def test_today_net_sums_slot_live_records(sandbox):
    slot = _mk_slot()
    slot.risk.closed_trades = [
        _trade(-3.0, mode="live"),
        _trade(-9.9, mode="live", closed_at=time.time() - 86400 * 2),  # not today
        _trade(-7.0),          # paper (no mode) — ignored
        _trade(-7.0, mode="paper"),  # paper — ignored
    ]
    b = _bare_bot(slots=[slot], main_trades=[_trade(-1.5)])
    assert abs(b._today_net_all_books() - (-4.5)) < 1e-9


def test_slot_losses_alone_trip_halt_and_block_slot_entries(sandbox):
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(-6.0, mode="live")]
    b = _bare_bot(slots=[slot])
    assert b._maybe_daily_loss_halt(100.0) is True  # floor $5 < $6
    assert os.path.exists(".pause_trading")
    with open(".pause_trading") as f:
        f.readline()
        assert f.readline().startswith("DAILY LOSS HALT")
    assert b._slot_entries_blocked() is True
    assert getattr(b, "_trading_paused", False) is True


def test_split_main_slot_losses_sum_past_threshold(sandbox):
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(-3.0, mode="live")]
    b = _bare_bot(slots=[slot], main_trades=[_trade(-2.5)])
    assert b._maybe_daily_loss_halt(100.0) is True  # −5.5 <= −5 floor


def test_paper_losses_ignored(sandbox):
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(-20.0), _trade(-20.0, mode="paper")]
    b = _bare_bot(slots=[slot])
    assert b._maybe_daily_loss_halt(100.0) is False
    assert not os.path.exists(".pause_trading")


def test_halt_state_set_even_while_paused(sandbox):
    """Regression: with the pause flag already up (but no sentinel on disk —
    e.g. another pause path just cleared its file), a breaching loss must
    still set the daily-loss halt state."""
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(-6.0, mode="live")]
    b = _bare_bot(slots=[slot])
    b._trading_paused = True
    assert b._maybe_daily_loss_halt(100.0) is True
    assert os.path.exists(".pause_trading")


def test_existing_sentinel_not_clobbered(sandbox):
    with open(".pause_trading", "w") as f:
        f.write(f"{int(time.time())}\nmanual pause via Telegram\n")
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(-6.0, mode="live")]
    b = _bare_bot(slots=[slot])
    assert b._maybe_daily_loss_halt(100.0) is True  # entries stay halted
    with open(".pause_trading") as f:
        f.readline()
        assert f.readline().startswith("manual pause")  # reason untouched


def test_override_still_works(sandbox):
    today = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    with open(".daily_loss_override", "w") as f:
        f.write(today + "\n")
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(-6.0, mode="live")]
    b = _bare_bot(slots=[slot])
    assert b._maybe_daily_loss_halt(100.0) is False
    assert not os.path.exists(".pause_trading")


def test_daily_loss_check_hoisted_above_early_returns():
    """The evaluation must run BEFORE the _trading_paused and
    .halt_main_entries early returns in _run_cycle (it was below them —
    unreachable during any pause/halt)."""
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    call = src.index("self._maybe_daily_loss_halt(")
    assert call < src.index("if getattr(self, '_trading_paused', False):")
    assert call < src.index('os.path.exists(".halt_main_entries")')
