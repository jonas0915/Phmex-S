"""Mode-blind consumer fixes for the 8/26 main-book paper demotion.

New simulated main-book rows carry mode=="paper" and must never pollute
real-money reporting or fire false alarms. Historical rows have NO mode
field, are real money, and must keep counting exactly as before.

Covers: scripts/overwatch.py, scripts/reconcile_phemex.py,
scripts/strategy_tracker.py, scripts/weekly_forensics.py,
scripts/sprint_checkpoint.py, scripts/telegram_commander.py,
scripts/l2x_lab/postentry_drift.py.
"""
import json
import os
import sys
import time
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import overwatch


def _real_row(pnl, closed_at=None, **kw):
    """Historical real-money row: no mode field."""
    row = {"symbol": "BTC/USDT:USDT", "side": "long", "pnl_usdt": pnl,
           "net_pnl": pnl, "closed_at": closed_at or time.time()}
    row.update(kw)
    return row


def _paper_row(pnl, closed_at=None, **kw):
    """New simulated row: mode=="paper"."""
    row = _real_row(pnl, closed_at, **kw)
    row["mode"] = "paper"
    return row


# ── overwatch.real_trades ────────────────────────────────────────────────────

def test_real_trades_drops_only_paper():
    rows = [_real_row(1.0), _paper_row(2.0), {"mode": "live", "pnl_usdt": 3.0}]
    kept = overwatch.real_trades(rows)
    assert len(kept) == 2
    assert all(t.get("mode") != "paper" for t in kept)
    assert any(t.get("mode") == "live" for t in kept)  # live tags untouched


def test_real_trades_identity_without_paper_rows():
    """Regression: zero paper rows => the filter is a no-op (same objects, same order)."""
    rows = [_real_row(1.0), _real_row(-2.0), {"mode": "live", "pnl_usdt": 0.5}]
    assert overwatch.real_trades(rows) == rows


# ── overwatch.check_report_accuracy ──────────────────────────────────────────

def _write_report(tmp_path, date_str, trades, wr, pnl):
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    (reports / f"{date_str}.md").write_text(
        f"# Daily Report\nTrades: {trades}\nWin Rate: {wr:.1f}%\nNet PnL: ${pnl:+.2f}\n"
    )
    return reports


def test_report_accuracy_agrees_with_real_only_totals(tmp_path, monkeypatch):
    """Daily report shows real-only numbers; the check must derive the same
    totals even when paper rows exist on the same day."""
    now = time.time()
    date_str = datetime.fromtimestamp(now, tz=overwatch.PT_TZ).strftime("%Y-%m-%d")
    state = {"closed_trades": [
        _real_row(2.0, now), _real_row(-1.0, now),
        _paper_row(50.0, now), _paper_row(-50.0, now),
    ]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    reports = _write_report(tmp_path, date_str, trades=2, wr=50.0, pnl=1.0)

    monkeypatch.setattr(overwatch, "STATE_FILE", str(state_file))
    monkeypatch.setattr(overwatch, "REPORTS_DIR", str(reports))
    result = overwatch.check_report_accuracy()
    assert result.severity == "OK", result.message


def test_report_accuracy_still_catches_real_mismatch(tmp_path, monkeypatch):
    """Filter must not blind the check: a genuinely wrong report still warns."""
    now = time.time()
    date_str = datetime.fromtimestamp(now, tz=overwatch.PT_TZ).strftime("%Y-%m-%d")
    state = {"closed_trades": [_real_row(2.0, now), _real_row(-1.0, now)]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    reports = _write_report(tmp_path, date_str, trades=5, wr=80.0, pnl=9.99)

    monkeypatch.setattr(overwatch, "STATE_FILE", str(state_file))
    monkeypatch.setattr(overwatch, "REPORTS_DIR", str(reports))
    result = overwatch.check_report_accuracy()
    assert result.severity == "WARNING"


# ── overwatch.check_fee_capture ──────────────────────────────────────────────

def _exit_time_str(ago_sec=3600):
    return datetime.fromtimestamp(time.time() - ago_sec).strftime("%Y-%m-%d %H:%M:%S")


def test_fee_capture_skips_paper_rows(tmp_path, monkeypatch):
    """A paper sim with no fee field must not raise a fee-capture warning."""
    state = {"closed_trades": [
        _real_row(1.0, exit_time=_exit_time_str(), fee=0.05),
        _paper_row(1.0, exit_time=_exit_time_str()),  # no fee — sim
    ]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(overwatch, "STATE_FILE", str(state_file))
    result = overwatch.check_fee_capture()
    assert result.severity == "OK", result.message


def test_fee_capture_still_flags_real_missing_fee(tmp_path, monkeypatch):
    state = {"closed_trades": [_real_row(1.0, exit_time=_exit_time_str())]}  # no fee
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(overwatch, "STATE_FILE", str(state_file))
    result = overwatch.check_fee_capture()
    assert result.severity == "WARNING"


# ── reconcile_phemex.load_closed_trades ──────────────────────────────────────

def test_reconcile_skips_paper_rows(tmp_path, monkeypatch):
    from scripts import reconcile_phemex
    from pathlib import Path
    now = time.time()
    state = {"closed_trades": [
        _real_row(1.0, now), _paper_row(2.0, now), _real_row(-0.5, now),
    ]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(reconcile_phemex, "STATE_FILE", Path(state_file))
    got = reconcile_phemex.load_closed_trades(since_ms=0)
    assert len(got) == 2
    assert all(t.get("mode") != "paper" for t in got)


def test_reconcile_no_paper_rows_unchanged(tmp_path, monkeypatch):
    from scripts import reconcile_phemex
    from pathlib import Path
    now = time.time()
    rows = [_real_row(1.0, now), _real_row(2.0, now)]
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps({"closed_trades": rows}))
    monkeypatch.setattr(reconcile_phemex, "STATE_FILE", Path(state_file))
    got = reconcile_phemex.load_closed_trades(since_ms=0)
    assert [t["pnl_usdt"] for t in got] == [1.0, 2.0]


# ── strategy_tracker.read_states grand total ─────────────────────────────────

def test_strategy_tracker_total_excludes_paper(tmp_path, monkeypatch):
    from scripts import strategy_tracker
    state = {"closed_trades": [
        _real_row(3.0), _real_row(-1.0), _paper_row(100.0),
    ]}
    (tmp_path / "trading_state.json").write_text(json.dumps(state))
    monkeypatch.setattr(strategy_tracker, "ROOT", str(tmp_path))
    rows, total = strategy_tracker.read_states()
    assert total == 2.0
    assert rows[0]["n"] == 2
    assert rows[0]["wr"] == 50.0


def test_strategy_tracker_total_unchanged_without_paper(tmp_path, monkeypatch):
    from scripts import strategy_tracker
    state = {"closed_trades": [_real_row(3.0), _real_row(-1.0),
                               {"mode": "live", "pnl_usdt": 0.5, "net_pnl": 0.5}]}
    (tmp_path / "trading_state.json").write_text(json.dumps(state))
    monkeypatch.setattr(strategy_tracker, "ROOT", str(tmp_path))
    rows, total = strategy_tracker.read_states()
    assert total == 2.5
    assert rows[0]["n"] == 3


# ── weekly_forensics.load_recent_trades ──────────────────────────────────────

def test_weekly_forensics_excludes_paper(tmp_path, monkeypatch):
    from scripts import weekly_forensics
    from pathlib import Path
    now = time.time()
    state = {"closed_trades": [_real_row(1.0, now), _paper_row(2.0, now)]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(weekly_forensics, "STATE_FILE", Path(state_file))
    got = weekly_forensics.load_recent_trades(days=7)
    assert len(got) == 1
    assert "mode" not in got[0]


# ── sprint_checkpoint.live_pnl_since_sprint ──────────────────────────────────

def test_sprint_checkpoint_excludes_paper(tmp_path, monkeypatch):
    from scripts import sprint_checkpoint
    from pathlib import Path
    now = time.time()
    state = {"closed_trades": [_real_row(4.0, now), _paper_row(100.0, now)]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(sprint_checkpoint, "STATE_PATH", Path(state_file))
    got = sprint_checkpoint.live_pnl_since_sprint()
    assert got["trades"] == 1
    assert got["net_pnl"] == 4.0


# ── telegram_commander._is_paper ─────────────────────────────────────────────

def test_telegram_is_paper_helper():
    tc = pytest.importorskip("scripts.telegram_commander")
    assert tc._is_paper({"mode": "paper"}) is True
    assert tc._is_paper({"mode": "live"}) is False
    assert tc._is_paper({}) is False  # historical no-mode row = real money


# ── l2x_lab postentry_drift.load_trades ──────────────────────────────────────

def test_postentry_drift_excludes_paper(tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    from scripts.l2x_lab import postentry_drift
    from pathlib import Path
    now = time.time()

    def _l2(pnl, paper=False):
        row = {"strategy": "htf_l2_anticipation", "symbol": "BTC/USDT:USDT",
               "side": "long", "opened_at": now - 600, "entry_price": 100.0,
               "pnl_usdt": pnl, "closed_at": now}
        if paper:
            row["mode"] = "paper"
        return row

    state = {"closed_trades": [_l2(1.0), _l2(2.0, paper=True)]}
    state_file = tmp_path / "trading_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(postentry_drift, "STATE_FILE", Path(state_file))
    trades, phantoms = postentry_drift.load_trades()
    assert len(trades) == 1
    assert phantoms == 0
    assert trades[0].get("mode") != "paper"


# ── overwatch.real_position_syms (phantom false-alarm guard) ─────────────────

def test_real_position_syms_excludes_paper_positions():
    """An open paper position ("paper": true) never exists on the exchange —
    it must not be reported as a phantom by check_position_desync."""
    state = {"positions": {
        "BTC/USDT:USDT": {"side": "long", "entry_price": 100.0},
        "ETH/USDT:USDT": {"side": "short", "entry_price": 50.0, "paper": True},
    }}
    assert overwatch.real_position_syms(state) == {"BTC/USDT:USDT"}


def test_real_position_syms_identity_without_paper():
    state = {"positions": {"BTC/USDT:USDT": {"side": "long"},
                           "XRP/USDT:USDT": {"side": "short"}}}
    assert overwatch.real_position_syms(state) == {"BTC/USDT:USDT", "XRP/USDT:USDT"}
    assert overwatch.real_position_syms({}) == set()
    assert overwatch.real_position_syms({"positions": None}) == set()
