"""Equity source for drawdown/peak/halt tracking (_equity_for_drawdown).

Root cause (2026-07-07): real_balance was `free + main-bot margin_in_use`, but
live SLOT positions' margin (e.g. 5m_mean_revert's $15 XRP short) lives outside
self.risk.positions — so equity read $15 low and the drawdown monitor fired a
false "32.1% — SEVERE" 1.5h entry pause (plus 8 earlier 8-17% misfires, all
matching a position-margin/peak signature). Fix: prefer the EXCHANGE's own
total-equity number (get_equity, cached from the same fetch_balance call),
falling back to the old sum only when the cache is unset (returns 0).
"""
from bot import _equity_for_drawdown


def test_prefers_exchange_equity_when_available():
    # 7/7 incident numbers: free 42.30 (slot margin held), exchange total 57.30
    assert _equity_for_drawdown(exchange_equity=57.30, free_plus_main_margin=42.30) == 57.30


def test_falls_back_when_equity_cache_unset():
    # get_equity returns 0.0 before the first successful fetch_balance
    assert _equity_for_drawdown(exchange_equity=0.0, free_plus_main_margin=42.30) == 42.30


def test_falls_back_on_negative_garbage():
    assert _equity_for_drawdown(exchange_equity=-1.0, free_plus_main_margin=50.0) == 50.0


def test_incident_would_not_have_fired():
    # With the fix, drawdown at 7:20 AM 7/7 = (62.27-57.30)/62.27 = 8.0%, not 32.1%
    peak = 62.27
    eq = _equity_for_drawdown(exchange_equity=57.30, free_plus_main_margin=42.30)
    dd = (peak - eq) / peak
    assert dd < 0.30  # SEVERE tier (30%) must not fire
    assert abs(dd - 0.0798) < 0.001
