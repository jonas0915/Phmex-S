"""2026-09-03: main-book REGIME pause must not freeze the live slot.

Bug: the "3/5 losses — pausing 30 min" branch in `_run_cycle` returned BEFORE
`_evaluate_all_slots`, so for 30 min the LIVE 5m_mean_revert slot got no
entries, no software exits and no durable-SL ratchet (only the exchange-resting
SL/TP protected an open position). Since the main book went PAPER (8/26) every
trade feeding that 3/5 window is a simulation — four paper-loss streaks froze
the real-money slot on 8/28, 8/29, 9/1 and 9/2. The `_trading_paused` (F1,
7/17) and `.halt_main_entries` branches already service slots before returning;
the regime branch must mirror them.

Semantics pinned here: the regime filter is a MAIN-book signal-quality pause,
not an account-risk halt, so it must not block slot entries either —
`_slot_entries_blocked` stays keyed on .pause_trading / .max_dd_halt / the
drawdown pause only.
"""
import inspect
import time
from types import SimpleNamespace

import bot as botmod


def _regime_block():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    start = src.find("if time.time() < self._regime_pause_until:")
    end = src.find("# Pre-compute indicators", start)
    assert start != -1 and end != -1 and start < end
    return src[start:end]


def test_regime_pause_branch_services_slots_before_return():
    block = _regime_block()
    assert "return" in block, "regime branch must still skip main entries"
    assert "_evaluate_all_slots(" in block, (
        "regime pause branch must call _evaluate_all_slots before returning, "
        "mirroring the _trading_paused and .halt_main_entries branches"
    )
    assert block.find("_evaluate_all_slots(") < block.rfind("return"), (
        "slots must be serviced BEFORE the early return"
    )


def test_regime_pause_does_not_block_slot_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b = object.__new__(botmod.Phmex2Bot)
    b.risk = SimpleNamespace(_drawdown_pause_until=0.0)
    b._regime_pause_until = time.time() + 1800
    assert b._slot_entries_blocked() is False, (
        "a main-book regime pause is not an account halt; slot entries proceed"
    )
