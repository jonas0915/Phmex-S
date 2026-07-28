"""Persistent slot kills (2026-07-28).

Incident: ETH_TSM_28 was killed 7/27 (.kill_ sentinel → enabled=False,
position closed, "killed" trade recorded) yet re-entered a paper ETH long
the next day. Two stacked gaps:
  1. enabled=False was memory-only — the 4:08 PM restart resurrected it.
  2. _evaluate_eth_tsm never checked slot.enabled at all, so even the live
     process would have re-entered at the next daily roll.
Fixes under test: killed_at persisted in the mode sidecar (set_killed /
_load_mode), and enabled gates in the TSM and Donchian evaluators.
"""
import inspect
import json
import os

import pytest

import bot as botmod
import risk_manager
import strategy_slot
from strategy_slot import StrategySlot


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    return tmp_path


def _mk_slot():
    return StrategySlot(
        slot_id="KILLME", strategy_name="htf_l2_anticipation",
        timeframe="5m", max_positions=1, capital_pct=0.0, paper_mode=True,
    )


def test_set_killed_disables_and_persists(sandbox):
    slot = _mk_slot()
    assert slot.enabled is True
    slot.set_killed()
    assert slot.enabled is False
    assert slot.killed_at is not None
    data = json.load(open(slot._mode_sidecar))
    assert data["killed_at"] == slot.killed_at


def test_killed_slot_stays_dead_after_restart(sandbox):
    _mk_slot().set_killed()
    reborn = _mk_slot()  # fresh construction = restart; _load_mode runs in __post_init__
    assert reborn.enabled is False, "restart resurrected a killed slot"
    assert reborn.killed_at is not None


def test_unkilled_slot_unaffected(sandbox):
    slot = _mk_slot()
    slot._save_mode()  # sidecar exists with killed_at=None
    reborn = _mk_slot()
    assert reborn.enabled is True
    assert reborn.killed_at is None


def test_kill_sentinel_path_uses_set_killed():
    """The .kill_ handler must persist via set_killed(), not bare enabled=False."""
    src = inspect.getsource(botmod.Phmex2Bot._check_control_sentinels
                            if hasattr(botmod.Phmex2Bot, "_check_control_sentinels")
                            else botmod.Phmex2Bot)
    kill_block = src[src.index('".kill_"') - 500: src.index('".kill_"') + 1500]
    assert "slot.set_killed()" in kill_block


def test_tsm_evaluator_gates_on_enabled():
    src = inspect.getsource(botmod.Phmex2Bot._evaluate_eth_tsm)
    gate = src.index("if not slot.enabled:")
    daily = src.index("(2) daily evaluation")
    assert gate < daily, "enabled gate must precede daily signal evaluation"


def test_donchian_evaluator_gates_on_enabled():
    src = inspect.getsource(botmod.Phmex2Bot._evaluate_donchian)
    assert "if not slot.enabled:" in src
