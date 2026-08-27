"""Main-book PAPER mode in scripts/daily_report.py (owner demotion 2026-08-26).

Since the .paper_main sentinel, simulated main fills land in
trading_state.json tagged mode="paper". The owner's ground truth is
"sum ALL trading_state*.json for real PnL" — so paper-tagged rows must be
split out and labeled PAPER, never summed into any real-money total.
Historical rows carry NO mode field = real money (regression-locked here).
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

import daily_report as dr  # noqa: E402


def test_split_paper_separates_tagged_rows():
    rows = [{"net_pnl": 1.0}, {"net_pnl": -2.0, "mode": "paper"},
            {"net_pnl": 3.0, "mode": "live"}]
    real, paper = dr.split_paper(rows)
    assert [t["net_pnl"] for t in real] == [1.0, 3.0]
    assert [t["net_pnl"] for t in paper] == [-2.0]


def test_split_paper_no_mode_rows_are_real_regression():
    # Historical ledger (pre-8/26): every row lacks a mode field — the split
    # must be a no-op on the real side (same rows, same order, none dropped).
    rows = [{"net_pnl": x} for x in (0.5, -1.2, 2.0)]
    real, paper = dr.split_paper(rows)
    assert real == rows
    assert paper == []


def test_split_paper_empty_and_none():
    assert dr.split_paper([]) == ([], [])
    assert dr.split_paper(None) == ([], [])


def test_paper_rows_never_inflate_real_totals():
    # A huge sim winner must not leak into the real-money sum.
    rows = [{"net_pnl": 1.0}, {"net_pnl": 50.0, "mode": "paper"}]
    real, paper = dr.split_paper(rows)
    assert sum(dr._net(t) for t in real) == 1.0
    assert sum(dr._net(t) for t in paper) == 50.0


def test_main_is_paper_reads_sentinel(monkeypatch, tmp_path):
    monkeypatch.setattr(dr, "PAPER_MAIN_SENTINEL",
                        str(tmp_path / ".paper_main"))
    assert dr.main_is_paper() is False
    (tmp_path / ".paper_main").write_text("owner demotion 8/26\n")
    assert dr.main_is_paper() is True
