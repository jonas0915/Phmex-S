"""STATS line must keep printing while entries are halted/paused (2026-07-16).

Bug: the every-10-cycles `=== STATS ===` block sat at the end of _run_cycle,
after the regime-pause / _trading_paused / .halt_main_entries early returns.
Since the 7/13 main-entries halt, zero STATS lines printed, starving every
balance surface that parses it (web_dashboard._latest_balance, trading_desk
stats block, scripts/daily_report.py, monitor_daemon) down to $0 / bogus DD.

Fix under test: a `_maybe_print_stats` helper called once BEFORE all early
returns, preserving the 2026-04-26 API-failure guard verbatim.
"""
import inspect
from types import SimpleNamespace

import bot as botmod


def _bare_bot(cycle_count):
    b = object.__new__(botmod.Phmex2Bot)
    b.cycle_count = cycle_count
    calls = []
    b.risk = SimpleNamespace(print_stats=lambda bal: calls.append(bal))
    return b, calls


def test_prints_stats_on_10th_cycle():
    b, calls = _bare_bot(cycle_count=20)
    b._maybe_print_stats(real_balance=41.90, available=10.0, margin_in_use=0.0)
    assert calls == [41.90]


def test_skips_on_non_10th_cycle():
    b, calls = _bare_bot(cycle_count=7)
    b._maybe_print_stats(real_balance=41.90, available=10.0, margin_in_use=0.0)
    assert calls == []


def test_api_failure_guard_preserved():
    # get_balance returned 0 while margin is in use -> almost certainly an API
    # failure (401/network). Must NOT log STATS (2026-04-26 incident: false
    # drawdown alerts via monitor_daemon).
    b, calls = _bare_bot(cycle_count=10)
    b._maybe_print_stats(real_balance=6.0, available=0.0, margin_in_use=6.0)
    assert calls == []


def test_stats_call_precedes_all_early_returns_in_run_cycle():
    # Regression guard: the helper call must appear in _run_cycle BEFORE the
    # regime-pause return, the _trading_paused return, and the
    # .halt_main_entries return — and the old inline end-of-cycle block must
    # be gone (no double print).
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    call_idx = src.find("_maybe_print_stats(")
    assert call_idx != -1, "_run_cycle no longer calls _maybe_print_stats"
    # Match the exact guard statements (a comment at the call site mentions the
    # bare names, so bare-token search would false-positive on it).
    for marker in ("if time.time() < self._regime_pause_until:",
                   "if getattr(self, '_trading_paused', False):",
                   'if os.path.exists(".halt_main_entries"):'):
        marker_idx = src.find(marker)
        assert marker_idx != -1, f"marker {marker!r} not found in _run_cycle"
        assert call_idx < marker_idx, (
            f"_maybe_print_stats must be called before the {marker!r} early return"
        )
    assert src.count("_maybe_print_stats(") == 1, "STATS must print exactly once per cycle"
    assert "print_stats(" not in src.replace("_maybe_print_stats(", ""), (
        "old inline risk.print_stats block still present in _run_cycle"
    )
