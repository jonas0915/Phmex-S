"""Paper-mode exclusion for display/report/ranking consumers (8/26 main-book
paper demotion — post-audit cleanup).

New simulated main-book rows carry mode=="paper" (closed rows) / "paper": true
(open position dicts) and must never pollute real-money PnL/WR/positions or
the kill-switch inputs. Historical rows have NO mode field, are real money,
and must keep counting exactly as before (identity regression: with zero
paper rows every output is unchanged).

Covers: recalibration.py, scanner.py, chart.py, dashboard.py, war_room.py,
trading_desk.py, daily_review.py, scripts/code_health.py.
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recalibration
import scanner
import chart
import dashboard
import daily_review
import trading_desk
import war_room
from scripts import code_health


def _real_row(pnl, closed_at=None, **kw):
    """Historical real-money row: no mode field."""
    row = {"symbol": "BTC/USDT:USDT", "side": "long", "pnl_usdt": pnl,
           "net_pnl": pnl, "pnl_pct": pnl, "reason": "take_profit",
           "strategy": "confluence",
           "opened_at": (closed_at or time.time()) - 600,
           "closed_at": closed_at or time.time()}
    row.update(kw)
    return row


def _paper_row(pnl, closed_at=None, **kw):
    """New simulated main-book row: mode=="paper"."""
    row = _real_row(pnl, closed_at, **kw)
    row["mode"] = "paper"
    return row


def _write_state(path, closed_trades, positions=None):
    with open(path, "w") as f:
        json.dump({"peak_balance": 100.0, "positions": positions or {},
                   "closed_trades": closed_trades}, f)
    return str(path)


# ── recalibration.load_trades (feeds kill_switch_check / edge_decay_check) ──

def test_recalibration_load_trades_excludes_paper(tmp_path):
    state = _write_state(tmp_path / "trading_state.json",
                         [_real_row(1.0), _paper_row(-50.0), _real_row(-2.0)])
    trades = recalibration.load_trades(state)  # abs path overrides dirname join
    assert len(trades) == 2
    assert all(t.get("mode") != "paper" for t in trades)
    # the huge paper loss must not reach kill-switch inputs
    metrics = recalibration.compute_metrics(trades)
    assert metrics["pnl"] == -1.0


def test_recalibration_load_trades_identity_without_paper(tmp_path):
    rows = [_real_row(1.0), _real_row(-2.0), _real_row(0.5, mode="live")]
    state = _write_state(tmp_path / "trading_state.json", rows)
    assert recalibration.load_trades(state) == rows  # no-op: same rows, order


def test_recalibration_kill_switch_not_tripped_by_paper(tmp_path):
    # 60 paper losers + 30 real winners: mode-blind would fire negative-Kelly
    # KILL; the filter must leave a clean positive book.
    rows = [_paper_row(-1.0) for _ in range(60)] + [_real_row(0.5) for _ in range(30)]
    state = _write_state(tmp_path / "trading_state.json", rows)
    trades = recalibration.load_trades(state)
    metrics = recalibration.compute_metrics(trades)
    assert metrics["trades"] == 30
    assert recalibration.kill_switch_check(metrics) == []


# ── scanner._compute_history_scores (symbol ranking) ─────────────────────────

def test_scanner_history_scores_exclude_paper(tmp_path):
    # SOL: 2 real winners; 3 paper disasters must not tank its score.
    rows = ([_real_row(0.5, symbol="SOL/USDT:USDT") for _ in range(2)]
            + [_paper_row(-5.0, symbol="SOL/USDT:USDT") for _ in range(3)])
    state = _write_state(tmp_path / "trading_state.json", rows)
    scores = scanner._compute_history_scores(state_path=state, min_trades=2)
    assert "SOL/USDT:USDT" in scores
    assert scores["SOL/USDT:USDT"] > 0.5  # positive avg → above-neutral score


def test_scanner_history_scores_identity_without_paper(tmp_path):
    rows = [_real_row(0.5, symbol="SOL/USDT:USDT"),
            _real_row(-0.2, symbol="SOL/USDT:USDT")]
    state = _write_state(tmp_path / "trading_state.json", rows)
    with_filter = scanner._compute_history_scores(state_path=state, min_trades=2)
    # ground truth computed the pre-fix way (no filter at all)
    import math
    avg = (0.5 + -0.2) / 2
    assert with_filter["SOL/USDT:USDT"] == 1.0 / (1.0 + math.exp(-10.0 * avg))


def test_scanner_paper_rows_dont_meet_min_trades(tmp_path):
    # only paper rows for a symbol → absent from scores (neutral default)
    rows = [_paper_row(9.0, symbol="DOGE/USDT:USDT") for _ in range(5)]
    state = _write_state(tmp_path / "trading_state.json", rows)
    assert scanner._compute_history_scores(state_path=state, min_trades=2) == {}


# ── chart._real_trades ───────────────────────────────────────────────────────

def test_chart_real_trades_excludes_paper():
    rows = [_real_row(1.0), _paper_row(2.0), _real_row(-1.0, mode="live")]
    kept = chart._real_trades(rows)
    assert len(kept) == 2
    assert all(t.get("mode") != "paper" for t in kept)


def test_chart_real_trades_identity_without_paper():
    rows = [_real_row(1.0), _real_row(-1.0)]
    assert chart._real_trades(rows) == rows


# ── dashboard.py (terminal) ──────────────────────────────────────────────────

def test_dashboard_real_trades_excludes_paper():
    rows = [_real_row(1.0), _paper_row(2.0)]
    kept = dashboard._real_trades(rows)
    assert kept == rows[:1]


def test_dashboard_render_stats_exclude_paper(monkeypatch, capsys):
    monkeypatch.setattr(os, "system", lambda *_: 0)  # don't clear the terminal
    rows = [_real_row(1.0, symbol="BTC/USDT:USDT"),
            _paper_row(99.0, symbol="FAKE/USDT:USDT")]
    dashboard.render({"peak_balance": 50.0, "closed_trades": rows}, [])
    out = capsys.readouterr().out
    assert "Trades: 1 | Wins: 1 | Losses: 0" in out
    assert "Total PnL: $+1.00" in out          # paper +99 not blended
    assert "FAKE/USDT:USDT" not in out          # paper row not in recent trades
    assert "Paper (sim): 1 trades" in out       # labeled, not blended


def test_dashboard_render_identity_without_paper(monkeypatch, capsys):
    monkeypatch.setattr(os, "system", lambda *_: 0)
    rows = [_real_row(1.0), _real_row(-0.5)]
    dashboard.render({"peak_balance": 50.0, "closed_trades": rows}, [])
    out = capsys.readouterr().out
    assert "Trades: 2 | Wins: 1 | Losses: 1" in out
    assert "Paper (sim)" not in out  # zero paper rows → no extra line


def test_dashboard_open_positions_skip_paper_lines():
    lines = [
        "2026-08-26 10:00:00 [INFO] Position opened: SHORT SUI/USDT:USDT | Entry: 0.7500 | x",
        "2026-08-26 10:01:00 [INFO] [PAPER] Position opened: LONG ETH/USDT:USDT | Entry: 2400.0000 | x",
    ]
    positions = dashboard.parse_open_positions(lines)
    assert [p["symbol"] for p in positions] == ["SUI/USDT:USDT"]


# ── war_room.py ──────────────────────────────────────────────────────────────

def test_war_room_api_excludes_paper(monkeypatch, tmp_path):
    rows = [_real_row(1.0), _paper_row(2.0), _real_row(-1.0)]
    state = _write_state(tmp_path / "trading_state.json", rows)
    monkeypatch.setattr(war_room, "STATE_FILE", state)
    monkeypatch.setattr(war_room, "LOG_FILE", str(tmp_path / "bot.log"))
    resp = war_room._build_api_response()
    assert resp["total_trades"] == 2
    assert all(t.get("mode") != "paper" for t in resp["recent_trades"])


def test_war_room_api_identity_without_paper(monkeypatch, tmp_path):
    rows = [_real_row(1.0), _real_row(-1.0)]
    state = _write_state(tmp_path / "trading_state.json", rows)
    monkeypatch.setattr(war_room, "STATE_FILE", state)
    monkeypatch.setattr(war_room, "LOG_FILE", str(tmp_path / "bot.log"))
    resp = war_room._build_api_response()
    assert resp["total_trades"] == 2
    assert resp["recent_trades"] == rows


def test_war_room_paper_close_line_not_a_close_event():
    lines = [
        "2026-08-26 10:29:32 [INFO] [PAPER] Position closed: SHORT SOL/USDT:USDT | Exit: 97.1500 | PnL: +0.06 USDT (+1.16%) | Reason: hard_time_exit\n",
        "2026-08-26 10:30:00 [INFO] Position closed: SHORT LTC/USDT:USDT | Exit: 49.4600 | PnL: +1.08 USDT (+14.35%) | Reason: early_exit\n",
    ]
    events = war_room._parse_log_events(lines)
    closes = [e for e in events if e.get("type") == "close"]
    assert len(closes) == 1
    assert closes[0]["symbol"] == "LTC/USDT:USDT"


# ── trading_desk.py ──────────────────────────────────────────────────────────

def _desk_response(monkeypatch, tmp_path, rows):
    state = _write_state(tmp_path / "trading_state.json", rows)
    monkeypatch.setattr(trading_desk, "STATE_FILE", state)
    monkeypatch.setattr(trading_desk, "LOG_FILE", str(tmp_path / "bot.log"))
    monkeypatch.setattr(trading_desk, "BASE_DIR", str(tmp_path))  # hermetic slots
    return trading_desk._build_api_response()


def test_trading_desk_api_excludes_paper(monkeypatch, tmp_path):
    now = time.time()
    rows = [_real_row(1.0, closed_at=now, symbol="BTC/USDT:USDT"),
            _paper_row(99.0, closed_at=now, symbol="FAKE/USDT:USDT")]
    resp = _desk_response(monkeypatch, tmp_path, rows)
    assert resp["total_trades"] == 1
    assert all(t.get("mode") != "paper" for t in resp["recent_trades"])
    assert resp["today"]["count"] == 1
    assert resp["today"]["pnl"] == 1.0                    # +99 sim not blended
    assert dict(resp["top_pairs"]).get("FAKE") is None    # paper pair absent
    assert sum(s["count"] for s in resp["strat_stats"].values()) == 1


def test_trading_desk_api_identity_without_paper(monkeypatch, tmp_path):
    now = time.time()
    rows = [_real_row(1.0, closed_at=now), _real_row(-0.4, closed_at=now)]
    resp = _desk_response(monkeypatch, tmp_path, rows)
    assert resp["total_trades"] == 2
    assert resp["recent_trades"] == rows
    assert resp["today"]["count"] == 2
    assert resp["today"]["pnl"] == 0.6


def test_trading_desk_paper_close_line_not_a_close_event():
    lines = [
        "2026-08-26 20:00:08 [INFO] [PAPER] Position closed: LONG ETH/USDT:USDT | Exit: 2493.5500 | PnL: +0.61 USDT (+12.14%) | Reason: hard_time_exit\n",
        "2026-08-26 20:01:00 [INFO] Position closed: SHORT LTC/USDT:USDT | Exit: 49.4600 | PnL: +1.08 USDT (+14.35%) | Reason: early_exit\n",
    ]
    events = trading_desk._parse_log_events(lines)
    closes = [e for e in events if e.get("type") == "close"]
    assert len(closes) == 1
    assert closes[0]["symbol"] == "LTC/USDT:USDT"


# ── daily_review.py (log parser) ─────────────────────────────────────────────

_REAL_CLOSE = ("2026-08-26 10:30:00 [INFO] Position closed: SHORT LTC/USDT:USDT | "
               "Exit: 49.4600 | PnL: +1.08 USDT (+14.35%) | Reason: early_exit")
_PAPER_CLOSE = ("2026-08-26 10:29:32 [INFO] [PAPER] Position closed: SHORT SOL/USDT:USDT | "
                "Exit: 97.1500 | PnL: +0.06 USDT (+1.16%) | Reason: hard_time_exit")


def test_daily_review_skips_paper_close_lines():
    trades = daily_review.parse_trades_from_log([_PAPER_CLOSE, _REAL_CLOSE], "2026-08-26")
    assert len(trades) == 1
    assert trades[0]["symbol"] == "LTC/USDT:USDT"


def test_daily_review_identity_without_paper_lines():
    trades = daily_review.parse_trades_from_log([_REAL_CLOSE], "2026-08-26")
    assert len(trades) == 1
    assert trades[0]["pnl"] == 1.08


# ── scripts/code_health.py check_entry_health ────────────────────────────────

def _cycling_log(tmp_path):
    log = tmp_path / "bot.log"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.write_text(f"{now} [INFO] Cycle #100 | Positions: 0\n")
    return str(log)


def _setup_entry_health(monkeypatch, tmp_path, closed, positions=None,
                        paper_main=False):
    monkeypatch.setattr(code_health, "LOG_FILE", _cycling_log(tmp_path))
    monkeypatch.setattr(code_health, "STATE_FILE",
                        _write_state(tmp_path / "trading_state.json", closed,
                                     positions))
    monkeypatch.setattr(code_health, "BOT_DIR", str(tmp_path))
    if paper_main:
        (tmp_path / ".paper_main").touch()


def test_entry_health_identity_recent_real_entry(monkeypatch, tmp_path):
    # zero paper rows, no sentinel, fresh real entry → same OK text as before
    _setup_entry_health(monkeypatch, tmp_path, [_real_row(1.0)])
    res = code_health.check_entry_health()
    assert res.severity == "OK"
    assert "last filled entry 0.2h ago" in res.message
    assert "paper" not in res.message  # identity: no paper mention


def test_entry_health_identity_stale_real_entry(monkeypatch, tmp_path):
    # zero paper rows, no sentinel, 72h-old entry → same WARNING text as before
    old = time.time() - 72 * 3600
    _setup_entry_health(monkeypatch, tmp_path, [_real_row(1.0, closed_at=old)])
    res = code_health.check_entry_health()
    assert res.severity == "WARNING"
    assert "no filled entry in 72h" in res.message
    assert "paper" not in res.message


def test_entry_health_paper_activity_does_not_mask_real_dry_spell(monkeypatch, tmp_path):
    # no sentinel: fresh PAPER entries must NOT make a stale real funnel look healthy
    old = time.time() - 72 * 3600
    _setup_entry_health(monkeypatch, tmp_path,
                        [_real_row(1.0, closed_at=old), _paper_row(1.0)])
    res = code_health.check_entry_health()
    assert res.severity == "WARNING"
    assert "no filled entry in 72h" in res.message
    assert "paper-sim entry" in res.message  # reported separately, not blended


def test_entry_health_paper_main_zero_real_entries_ok(monkeypatch, tmp_path):
    # .paper_main present: zero real entries is by design when paper is active
    old = time.time() - 72 * 3600
    _setup_entry_health(monkeypatch, tmp_path,
                        [_real_row(1.0, closed_at=old), _paper_row(0.5)],
                        paper_main=True)
    res = code_health.check_entry_health()
    assert res.severity == "OK"
    assert "paper-main active" in res.message
    assert "real entry 72.2h ago" in res.message
    assert "paper entry 0.2h ago" in res.message


def test_entry_health_paper_main_open_paper_position_ok(monkeypatch, tmp_path):
    old = time.time() - 72 * 3600
    _setup_entry_health(monkeypatch, tmp_path, [_real_row(1.0, closed_at=old)],
                        positions={"ETH/USDT:USDT": {"symbol": "ETH/USDT:USDT",
                                                     "paper": True}},
                        paper_main=True)
    res = code_health.check_entry_health()
    assert res.severity == "OK"
    assert "paper entry 0.0h ago" in res.message


def test_entry_health_paper_main_zero_activity_still_flags(monkeypatch, tmp_path):
    # sentinel present but NOTHING (real or paper) in 48h → still a WARNING
    old = time.time() - 72 * 3600
    _setup_entry_health(monkeypatch, tmp_path,
                        [_real_row(1.0, closed_at=old),
                         _paper_row(0.5, closed_at=old)],
                        paper_main=True)
    res = code_health.check_entry_health()
    assert res.severity == "WARNING"
    assert "no entry of ANY kind" in res.message
