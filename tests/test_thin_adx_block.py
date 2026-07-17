"""F5 (2026-07-17): thin-tape ∧ high-1h-ADX entry block for htf_l2_anticipation.

Debug-verified toxic cell (3 rounds + independent verification): lifetime
−$29.22 @ 47% WR; 99% of July 2026's bleed (−$21.09 on 26 trades @ 42% WR).
Thin-only is +$6.86 lifetime and high-ADX-on-active-tape mildly negative —
ONLY the conjunction is blocked. In-sample evidence: forward grading
pre-registered for any un-halt. Blocks are gotAway-logged (reason thin_adx).
"""
import inspect
from types import SimpleNamespace

import bot as botmod
from config import Config


def _bot():
    return object.__new__(botmod.Phmex2Bot)


def test_blocks_conjunction_only():
    b = _bot()
    thin = {"trade_count": 12}
    active = {"trade_count": 80}
    assert b._thin_adx_blocked("htf_l2_anticipation", thin, 40.0) is True
    assert b._thin_adx_blocked("htf_l2_anticipation", thin, 30.0) is False   # thin-only: allowed
    assert b._thin_adx_blocked("htf_l2_anticipation", active, 40.0) is False  # high-ADX active tape: allowed
    assert b._thin_adx_blocked("htf_l2_anticipation", active, 30.0) is False


def test_boundary_values():
    b = _bot()
    edge = {"trade_count": 20}   # tc <= 20 is thin (7/10 study definition)
    assert b._thin_adx_blocked("htf_l2_anticipation", edge, 35.0) is True
    assert b._thin_adx_blocked("htf_l2_anticipation", {"trade_count": 21}, 35.0) is False
    assert b._thin_adx_blocked("htf_l2_anticipation", edge, 34.9) is False


def test_other_strategies_unaffected():
    b = _bot()
    thin = {"trade_count": 5}
    assert b._thin_adx_blocked("htf_confluence_pullback", thin, 50.0) is False
    assert b._thin_adx_blocked("5m_mean_revert", thin, 50.0) is False


def test_missing_data_fails_open():
    b = _bot()
    assert b._thin_adx_blocked("htf_l2_anticipation", None, 40.0) is True  # no flow → tc 0 = thin
    assert b._thin_adx_blocked("htf_l2_anticipation", {"trade_count": 5}, None) is False  # no ADX → allow


def test_flag_disables(monkeypatch):
    b = _bot()
    monkeypatch.setattr(Config, "HTF_THIN_ADX_BLOCK_ENABLED", False)
    assert b._thin_adx_blocked("htf_l2_anticipation", {"trade_count": 5}, 50.0) is False


def test_wired_into_entry_loop_with_gotaway():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    call_idx = src.find("_thin_adx_blocked(")
    assert call_idx != -1, "entry loop must consult the thin_adx block"
    block_region = src[call_idx:call_idx + 800]
    assert '"thin_adx"' in block_region, "blocks must be gotAway-logged as thin_adx"
    assert "continue" in block_region
