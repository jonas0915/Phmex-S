"""MCP server paper-main split (2026-08-26 main-book demotion).

phmex_status / phmex_pnl real-money numbers must exclude mode=="paper" rows
and "paper": true open positions, while reporting sims in explicit paper_*
fields (visible, never blended). Historical rows carry NO mode field and are
real money — they must keep counting exactly as before.
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _real_row(pnl, closed_at=None, **kw):
    """Historical real-money row: no mode field."""
    row = {"symbol": "BTC/USDT:USDT", "side": "long", "pnl_usdt": pnl,
           "closed_at": closed_at if closed_at is not None else time.time()}
    row.update(kw)
    return row


def _paper_row(pnl, closed_at=None, **kw):
    """New simulated row: mode=="paper"."""
    row = _real_row(pnl, closed_at, **kw)
    row["mode"] = "paper"
    return row


def _pos(margin=15.0, paper=False):
    return {"side": "short", "entry_price": 100.0, "amount": 1.0,
            "margin": margin, "stop_loss": 101.2, "take_profit": 98.4,
            "opened_at": time.time() - 600, "strategy": "confluence",
            "paper": paper}


@pytest.fixture
def write_state(tmp_path, monkeypatch):
    def _write(state):
        path = tmp_path / "trading_state.json"
        path.write_text(json.dumps(state))
        monkeypatch.setattr(mcp_server, "STATE_FILE", str(path))
        return str(path)
    return _write


# ---------------------------------------------------------------------------
# phmex_status
# ---------------------------------------------------------------------------

def test_status_real_numbers_exclude_paper(write_state):
    write_state({
        "positions": {"ETH/USDT:USDT": _pos(paper=False),
                      "SOL/USDT:USDT": _pos(paper=True)},
        "closed_trades": [
            _real_row(2.0), _real_row(-1.0),
            _paper_row(50.0), _paper_row(-50.0),
        ],
        "peak_balance": 90.0,
    })
    out = mcp_server.phmex_status()
    assert out["trades_today"] == 2
    assert out["pnl_today_usdt"] == pytest.approx(1.0)
    assert out["open_positions"] == 1
    # Sims reported separately, not hidden
    assert out["paper_trades_today"] == 2
    assert out["paper_pnl_today_usdt"] == pytest.approx(0.0)
    assert out["paper_open_positions"] == 1


def test_status_backward_compatible_shape(write_state):
    """All pre-existing keys survive (add fields, never rename)."""
    write_state({"positions": {}, "closed_trades": [], "peak_balance": 90.0})
    out = mcp_server.phmex_status()
    for key in ("running", "pid", "last_log_ts", "open_positions",
                "trades_today", "pnl_today_usdt", "peak_balance", "paused"):
        assert key in out


def test_status_no_mode_rows_still_count_as_real(write_state):
    """Regression: historical rows (no mode field) are real money."""
    write_state({"positions": {}, "closed_trades": [_real_row(3.0)]})
    out = mcp_server.phmex_status()
    assert out["trades_today"] == 1
    assert out["pnl_today_usdt"] == pytest.approx(3.0)
    assert out["paper_trades_today"] == 0


# ---------------------------------------------------------------------------
# phmex_pnl
# ---------------------------------------------------------------------------

def test_pnl_excludes_paper_and_reports_separately(write_state):
    write_state({"closed_trades": [
        _real_row(2.0), _real_row(2.0), _real_row(-1.0),
        _paper_row(50.0), _paper_row(-50.0),
    ]})
    out = mcp_server.phmex_pnl("all")
    assert out["trades"] == 3
    assert out["pnl_usdt"] == pytest.approx(3.0)
    assert out["win_rate"] == pytest.approx(round(2 / 3, 3))
    assert out["avg_win"] == pytest.approx(2.0)
    assert out["avg_loss"] == pytest.approx(-1.0)
    # A +$50 sim must never leak into real best/worst
    assert out["best"] == pytest.approx(2.0)
    assert out["worst"] == pytest.approx(-1.0)
    assert out["paper_trades"] == 2
    assert out["paper_pnl_usdt"] == pytest.approx(0.0)
    assert out["paper_win_rate"] == pytest.approx(0.5)


def test_pnl_all_paper_period_reports_zero_real(write_state):
    """Paper-only activity => real aggregates are empty but sims still shown."""
    write_state({"closed_trades": [_paper_row(5.0), _paper_row(-2.0)]})
    out = mcp_server.phmex_pnl("today")
    assert out["trades"] == 0
    assert out["pnl_usdt"] == 0
    assert out["win_rate"] is None
    assert out["paper_trades"] == 2
    assert out["paper_pnl_usdt"] == pytest.approx(3.0)


def test_pnl_no_mode_and_live_mode_rows_are_real(write_state):
    """Only mode=='paper' is excluded — no-mode and mode=='live' both count."""
    write_state({"closed_trades": [
        _real_row(1.0), _real_row(0.5, mode="live"), _paper_row(9.0),
    ]})
    out = mcp_server.phmex_pnl("all")
    assert out["trades"] == 2
    assert out["pnl_usdt"] == pytest.approx(1.5)
    assert out["paper_trades"] == 1


def test_pnl_period_cutoff_still_applies_to_paper_fields(write_state):
    """Paper fields respect the same period window as real fields."""
    old = time.time() - 40 * 86400
    write_state({"closed_trades": [_paper_row(9.0, closed_at=old), _real_row(1.0)]})
    out = mcp_server.phmex_pnl("week")
    assert out["trades"] == 1
    assert out["paper_trades"] == 0


# ---------------------------------------------------------------------------
# phmex_recent_trades / phmex_open_positions — flagged, not hidden
# ---------------------------------------------------------------------------

def test_recent_trades_flags_paper_rows_not_hidden(write_state):
    write_state({"closed_trades": [_real_row(1.0), _paper_row(-2.0)]})
    out = mcp_server.phmex_recent_trades(limit=10)
    assert len(out) == 2                      # sims visible
    by_pnl = {t["pnl_usdt"]: t for t in out}
    assert by_pnl[-2.0]["paper"] is True
    assert by_pnl[1.0]["paper"] is False


def test_open_positions_flags_paper_not_hidden(write_state):
    write_state({"positions": {"ETH/USDT:USDT": _pos(paper=False),
                               "SOL/USDT:USDT": _pos(paper=True)}})
    out = mcp_server.phmex_open_positions()
    assert len(out) == 2                      # sims visible
    flags = {p["symbol"]: p["paper"] for p in out}
    assert flags["ETH/USDT:USDT"] is False
    assert flags["SOL/USDT:USDT"] is True
