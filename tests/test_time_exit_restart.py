"""Restart must not disable cycle-denominated exits (2026-08-04 audit).

Defect: bot.py resets cycle_count to 0 on every boot while a restored
position keeps its persisted entry_cycle from the previous run, so
cycles_held = current - entry goes deeply negative and the hard time exit
(and flat exit) cannot fire for days (TAO short held 27.3h vs ~6h design).

Fix under test:
1. Position rebases a stale entry_cycle (entry_cycle > current_cycle can
   only mean a prior run's counter) so timers re-arm from "now".
2. bot.py persists a monotonic global cycle counter across restarts so
   rebasing is a migration/defense path, not the normal path.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from risk_manager import Position


def _make_position(**overrides):
    base = dict(
        symbol="SOL/USDT:USDT", side="long", entry_price=100.0, amount=1.0,
        margin=5.0, stop_loss=98.5, take_profit=102.5,
    )
    base.update(overrides)
    return Position(**base)


# ---------------------------------------------------------------------------
# A. Stale entry_cycle rebase (the TAO defect)
# ---------------------------------------------------------------------------

def test_stale_entry_cycle_rebases_and_timer_rearms():
    """Position from a prior run (entry_cycle=1906) checked at cycle 5 of a
    fresh run must rebase to 5 — then the hard exit fires 240 cycles later,
    instead of staying inert until the new run reaches cycle 2146."""
    pos = _make_position(entry_cycle=1906)

    should_exit, _ = pos.should_time_exit(5)
    assert should_exit is False
    assert pos.entry_cycle == 5  # rebased to the current counter

    # One cycle before the hard limit: still holding.
    should_exit, _ = pos.should_time_exit(5 + 239)
    assert should_exit is False

    # At the 240-cycle hard limit (no price -> roi sentinel, no extension).
    should_exit, is_hard = pos.should_time_exit(5 + 240)
    assert should_exit is True
    assert is_hard is True


def test_stale_entry_cycle_rebases_flat_exit_too():
    """should_flat_exit shares the cycles_held math and must get the same
    rebase treatment."""
    pos = _make_position(entry_cycle=1906)

    assert pos.should_flat_exit(5, 100.0) is False
    assert pos.entry_cycle == 5
    # 240 cycles later at a flat price (roi ~0 inside [-4, 4)) -> exits.
    assert pos.should_flat_exit(5 + 240, 100.0) is True


def test_normal_timer_behavior_unchanged():
    """Sanity: fresh-run positions keep the existing 240-cycle behavior."""
    pos = _make_position(entry_cycle=100)
    assert pos.should_time_exit(100 + 239)[0] is False
    should_exit, is_hard = pos.should_time_exit(100 + 240)
    assert should_exit is True and is_hard is True
    assert pos.entry_cycle == 100  # no rebase when counter is sane


# ---------------------------------------------------------------------------
# B. Global cycle counter persistence (bot.py)
# ---------------------------------------------------------------------------

def test_cycle_count_roundtrip(tmp_path):
    from bot import _load_cycle_count, _save_cycle_count
    path = str(tmp_path / ".bot_cycles.json")
    _save_cycle_count(1428, path=path)
    assert _load_cycle_count(path=path) == 1428


def test_cycle_count_missing_file_is_zero(tmp_path):
    from bot import _load_cycle_count
    assert _load_cycle_count(path=str(tmp_path / "nope.json")) == 0


def test_cycle_count_corrupt_file_is_zero(tmp_path):
    from bot import _load_cycle_count
    path = str(tmp_path / ".bot_cycles.json")
    with open(path, "w") as f:
        f.write("{not json")
    assert _load_cycle_count(path=path) == 0


def test_save_cycle_count_is_atomic_json(tmp_path):
    from bot import _save_cycle_count
    path = str(tmp_path / ".bot_cycles.json")
    _save_cycle_count(7, path=path)
    with open(path) as f:
        data = json.load(f)
    assert data["cycle_count"] == 7
    assert not os.path.exists(path + ".tmp")  # temp file cleaned up
