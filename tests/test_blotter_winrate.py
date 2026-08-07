"""Blotter strategy chips carry win rates (owner request 2026-08-06).

Each chip shows the full-ledger win rate for the strategy it filters to
(ALL chip = every strategy), computed from ALL rows — not just the 100
rendered — and excluding min_margin_skip bookkeeping records.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_dashboard as wd


def _states(trades_by_slot):
    """Minimal slot_states shape: {"5m_scalp": main, "<slot>": ...}."""
    return {
        sid: {"closed_trades": trades}
        for sid, trades in trades_by_slot.items()
    }


def _trade(strat, pnl, reason="take_profit", ts=1_785_900_000):
    return {"symbol": "SOL/USDT:USDT", "side": "long", "strategy": strat,
            "pnl_usdt": pnl, "net_pnl": pnl, "fees_usdt": 0.0,
            "exit_reason": reason, "closed_at": ts, "opened_at": ts - 60}


def test_chips_show_win_rate():
    states = _states({
        "5m_scalp": [_trade("stratA", 1.0), _trade("stratA", -1.0),
                     _trade("stratA", 2.0), _trade("stratA", 1.0)],  # 3/4 = 75%
        "SLOT_X": [_trade("stratB", -0.5), _trade("stratB", 0.5)],   # 1/2 = 50%
    })
    html = wd._build_blotter_panel(slot_states=states)
    assert "75%" in html   # stratA chip
    assert "50%" in html   # stratB chip
    assert "67%" in html   # ALL chip: 4/6 wins


def test_win_rate_excludes_min_margin_skip():
    states = _states({
        "5m_scalp": [_trade("stratA", 1.0), _trade("stratA", -1.0),
                     _trade("stratA", 0.0, reason="min_margin_skip")],
    })
    html = wd._build_blotter_panel(slot_states=states)
    # 1 win / 2 real trades = 50%, NOT 1/3 = 33%
    assert "50%" in html
    assert "33%" not in html


def test_each_row_shows_trade_roi_percent():
    states = _states({
        "5m_scalp": [dict(_trade("stratA", 1.25), margin=5.0),    # +25.0%
                     dict(_trade("stratA", -0.75), margin=5.0)],  # -15.0%
    })
    rows = wd.collect_blotter_rows(slot_states=states)
    by_net = {r["net"]: r for r in rows}
    assert by_net[1.25]["roi"] == 25.0
    assert by_net[-0.75]["roi"] == -15.0
    html = wd._build_blotter_panel(slot_states=states)
    assert "+25.0%" in html
    assert "-15.0%" in html


def test_row_roi_missing_margin_renders_dash():
    t = _trade("stratA", 1.0)
    t.pop("margin", None)
    rows = wd.collect_blotter_rows(slot_states=_states({"5m_scalp": [t]}))
    assert rows[0]["roi"] is None
    html = wd._build_blotter_panel(slot_states=_states({"5m_scalp": [t]}))
    assert "&mdash;" in html  # no margin -> no fake percentage


def test_win_rate_uses_full_ledger_not_rendered_rows():
    # 30 old losers + 5 recent winners; render only the 5 newest rows.
    trades = ([_trade("stratA", -1.0, ts=1_785_000_000 + i) for i in range(30)]
              + [_trade("stratA", 1.0, ts=1_785_900_000 + i) for i in range(5)])
    html = wd._build_blotter_panel(limit=5, slot_states=_states({"5m_scalp": trades}))
    # Full ledger: 5/35 = 14%. Rendered-only would say 100%.
    assert "14%" in html
    assert "100%" not in html
