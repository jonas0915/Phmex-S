"""U4 (2026-07-23 safety bundle): drawdown peak persistence + hysteresis +
MAX_DRAWDOWN_PERCENT wire-in.

Before: every drawdown-pause cooldown expiry reset peak_balance to the current
balance ("fresh start") — lifetime DD tracking was erased (STATS showed 0.0%
at a true 27% DD; the true-peak 30.5% DD on 7/21 would have hit the SEVERE
tier). Config.MAX_DRAWDOWN_PERCENT (.env 20.0) was referenced nowhere. Slot
RiskManagers had peak_balance 0 -> _drawdown_percent dead.

After: expiry clears the pause but KEEPS the peak; a tier may only re-trip at
DD >= pause-level + 2.0pts, or after DD recovers below the tier boundary
(re-arm). The >50% stale-restart reset stays (now WARNING + Telegram, as any
peak lowering must be). MAX_DD halt: DD >= MAX_DRAWDOWN_PERCENT blocks ALL
entries (main + slots) until .clear_dd_halt or recovery below threshold.
NOTE (owner-approved): the peak persists FORWARD from current values only —
the historical 46.36 peak is NOT retro-restored.
"""
import inspect
import os
import time
from types import SimpleNamespace

import pytest

import bot as botmod
import notifier
import risk_manager
import strategy_slot
from config import Config
from risk_manager import RiskManager
from strategy_slot import StrategySlot


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture
def tg(monkeypatch):
    sent = []
    monkeypatch.setattr(notifier, "send", lambda msg: sent.append(msg))
    monkeypatch.setattr(botmod.notifier, "send", lambda msg: sent.append(msg))
    return sent


def _rm(sandbox, peak=100.0):
    rm = RiskManager(state_file=str(sandbox / "u4_state.json"))
    rm.peak_balance = peak
    return rm


# ── peak persistence + hysteresis (risk_manager.can_open_trade) ────────────

def test_cooldown_expiry_keeps_peak(sandbox):
    rm = _rm(sandbox)
    rm._drawdown_pause_until = time.time() - 1  # expired
    assert rm.can_open_trade(95.0) is True      # dd 5% — nothing trips
    assert rm.peak_balance == 100.0             # peak NOT reset to balance
    assert rm._drawdown_pause_until == 0


def test_hysteresis_blocks_immediate_retrip_then_allows_at_plus2(sandbox):
    rm = _rm(sandbox)
    # First trip: dd 21% -> ELEVATED pause
    assert rm.can_open_trade(79.0) is False
    assert rm._drawdown_pause_until > time.time()
    # Expire the pause: same dd must NOT re-trip (perma-pause guard)
    rm._drawdown_pause_until = time.time() - 1
    assert rm.can_open_trade(79.0) is True
    assert rm.peak_balance == 100.0
    assert rm._drawdown_pause_until == 0
    # Under +2pts: still no re-trip
    assert rm.can_open_trade(78.0) is True      # dd 22% < 21+2
    # At/past +2pts: tier re-trips
    assert rm.can_open_trade(77.0) is False     # dd 23% >= 23


def test_recovery_above_tier_boundary_rearms(sandbox):
    rm = _rm(sandbox)
    assert rm.can_open_trade(79.0) is False     # trip at dd 21, tier 20
    rm._drawdown_pause_until = time.time() - 1
    assert rm.can_open_trade(79.0) is True      # hysteresis holds
    assert rm.can_open_trade(85.0) is True      # dd 15% < 20 -> re-armed
    assert rm.can_open_trade(79.5) is False     # fresh dd 20.5% trips again


def test_soft_tier_hysteresis_no_perma_pause(sandbox):
    rm = _rm(sandbox)
    rm.can_open_trade(90.0)                     # dd 10% -> soft 15min pause set
    assert rm._drawdown_pause_until > time.time()
    rm._drawdown_pause_until = time.time() - 1  # expire
    rm.can_open_trade(90.0)                     # same dd: must NOT re-arm pause
    assert rm._drawdown_pause_until == 0
    rm.can_open_trade(87.0)                     # dd 13% >= 10+2 -> soft re-fires
    assert rm._drawdown_pause_until > time.time()


def test_stale_restart_reset_kept_and_alerts(sandbox, tg):
    rm = _rm(sandbox)
    rm.set_initial_balance(40.0)                # >50% dd -> stale reset stays
    assert rm.peak_balance == 40.0
    assert any("peak" in m.lower() for m in tg), "peak lowering must Telegram"


# ── MAX_DRAWDOWN_PERCENT hard halt (bot side) ──────────────────────────────

def _bare_bot(sandbox, peak=100.0, slots=None):
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = slots or []
    b.risk = RiskManager(state_file=str(sandbox / "u4_main_state.json"))
    b.risk.peak_balance = peak
    return b


def test_max_dd_halt_trips_and_blocks_all_entries(sandbox, tg, monkeypatch):
    monkeypatch.setattr(Config, "MAX_DRAWDOWN_PERCENT", 20.0)
    b = _bare_bot(sandbox)
    assert b._check_max_dd_halt(79.0) is True   # dd 21% >= 20%
    assert os.path.exists(".max_dd_halt")
    assert b._slot_entries_blocked() is True    # slots blocked too
    assert len(tg) == 1                         # Telegram once on trip
    assert b._check_max_dd_halt(79.0) is True
    assert len(tg) == 1                         # no re-spam


def test_max_dd_halt_clears_on_sentinel_with_rearm_latch(sandbox, tg, monkeypatch):
    monkeypatch.setattr(Config, "MAX_DRAWDOWN_PERCENT", 20.0)
    b = _bare_bot(sandbox)
    assert b._check_max_dd_halt(79.0) is True
    open(".clear_dd_halt", "w").close()         # owner clears
    assert b._check_max_dd_halt(79.0) is False
    assert not os.path.exists(".max_dd_halt")
    # latch: still-breached DD must not instantly re-trip
    assert b._check_max_dd_halt(79.0) is False
    # recovery below threshold re-arms (latch file removed)…
    assert b._check_max_dd_halt(90.0) is False
    assert not os.path.exists(".clear_dd_halt")
    # …so a NEW breach trips again
    assert b._check_max_dd_halt(78.0) is True


def test_max_dd_halt_clears_on_recovery(sandbox, tg, monkeypatch):
    monkeypatch.setattr(Config, "MAX_DRAWDOWN_PERCENT", 20.0)
    b = _bare_bot(sandbox)
    assert b._check_max_dd_halt(79.0) is True
    assert b._check_max_dd_halt(85.0) is False  # dd 15% < 20 -> auto-clear
    assert not os.path.exists(".max_dd_halt")


def test_slot_peak_initializes_for_live_slots_only(sandbox):
    live = StrategySlot(slot_id="LIVE_X", strategy_name="htf_l2_anticipation",
                        timeframe="5m", paper_mode=False)
    paper = StrategySlot(slot_id="PAPER_X", strategy_name="htf_l2_anticipation",
                         timeframe="5m", paper_mode=True)
    b = _bare_bot(sandbox, slots=[live, paper])
    assert live.risk.peak_balance == 0.0
    b._update_slot_peaks(34.0)
    assert live.risk.peak_balance == 34.0       # guard now live
    assert paper.risk.peak_balance == 0.0       # paper untouched


def test_run_cycle_wired_to_max_dd_and_slot_peaks():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    assert "_check_max_dd_halt(" in src
    assert "_update_slot_peaks(" in src


def test_dashboard_surfaces_max_dd_halt(sandbox, monkeypatch):
    import web_dashboard
    monkeypatch.setattr(web_dashboard, "PROJECT_DIR", str(sandbox))
    open(sandbox / ".max_dd_halt", "w").close()
    badge = web_dashboard._slot_status_html("HTF_L2", [], set(), {})
    assert "MAX-DD HALT" in badge
