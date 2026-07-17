"""Audit findings on the F1-F6 bundle (2026-07-17 review agent) — all three fixed.

A1: gate_tags must survive a restart (same bug class as the old entry_snapshot
    loss — forensic attributes must persist).
A2: the F5 [THIN-ADX] gate must appear in the dashboard's gate label_map
    (CLAUDE.md reporting-propagation rule — silent gates are reporting lies).
A3: ETH-TSM paper entries and Donchian adjustments must honor the pause guard —
    F1 newly exposed these paths to run during .pause_trading.
"""
import inspect

import bot as botmod
import web_dashboard as wd
from risk_manager import Position, RiskManager


def test_gate_tags_survive_save_load(tmp_path):
    rm = RiskManager(state_file="nonexistent_audit_fixture.json")
    rm.state_file = str(tmp_path / "state.json")
    rm.positions = {}
    rm.closed_trades = []
    p = Position(symbol="BTC/USDT:USDT", side="long", entry_price=60000.0,
                 amount=0.001, margin=6.0, stop_loss=59280.0, take_profit=60960.0)
    p.gate_tags = "sg_thin_tape,sg_htf_adx_hi"
    rm.positions["BTC/USDT:USDT"] = p
    rm._save_state()
    rm2 = RiskManager(state_file="nonexistent_audit_fixture.json")
    rm2.state_file = rm.state_file
    rm2.positions = {}
    rm2._load_state()
    assert getattr(rm2.positions["BTC/USDT:USDT"], "gate_tags", None) == "sg_thin_tape,sg_htf_adx_hi"


def test_thin_adx_in_dashboard_label_map():
    src = inspect.getsource(wd._gate_stats)
    assert "THIN-ADX" in src, (
        "F5 gate must be visible in the dashboard gate panel (reporting-propagation rule)"
    )


def test_tsm_paper_entry_honors_pause():
    src = inspect.getsource(botmod.Phmex2Bot._tsm_try_entry)
    assert "_slot_entries_blocked()" in src, (
        "ETH-TSM paper entry must honor the global pause guard"
    )


def test_donchian_adjust_honors_pause():
    src = inspect.getsource(botmod.Phmex2Bot._donchian_adjust_position)
    assert "_slot_entries_blocked()" in src, (
        "Donchian rebalance/entry must honor the global pause guard"
    )
