"""Main-book PAPER mode in scripts/daily_report.py (owner demotion 2026-08-26).

Since the .paper_main sentinel, simulated main fills land in
trading_state.json tagged mode="paper". The owner's ground truth is
"sum ALL trading_state*.json for real PnL" — so paper-tagged rows must be
split out and labeled PAPER, never summed into any real-money total.
Historical rows carry NO mode field = real money (regression-locked here).
"""
import os
import sys

import pytest

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


# ── Pre-registered paper forward tests (informed_flow_btc_alt_cascade_v2) ────
# Project rule (CLAUDE.md): every bot update propagates to Telegram — the daily
# report (markdown + Telegram summary) must show the 2026-09-20 pre-registered
# paper slot, labeled PAPER, outside every real-money total. Dead sims were
# pulled from this report 2026-07-03, so the section is driven by an explicit
# registry (PAPER_FORWARD_TESTS) — only forward tests with a live verdict line.
import json
from datetime import datetime

IFC = "informed_flow_btc_alt_cascade_v2"
IFC_PREREG = "docs/superpowers/specs/2026-09-20-informed_flow_btc_alt_cascade_v2-prereg.md"
IFC_REG_TS = 1789933835


def _ifc_rows(date_str):
    """Two paper closes today at 11 PM PT (risk_manager paper shape: no mode
    key; late-evening so they post-date the 12:50 PM PT registration even when
    date_str is the registration day itself) + one row two days before
    registration that the since-registration line must exclude."""
    noon = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=23, tzinfo=dr.CA_TZ).timestamp()
    return [
        {"symbol": "DOGE/USDT:USDT", "side": "short", "net_pnl": 4.76, "pnl_usdt": 5.0,
         "fees_usdt": 0.24, "exit_reason": "take_profit", "strategy": IFC,
         "opened_at": noon - 3 * 3600, "closed_at": noon - 60},
        {"symbol": "XRP/USDT:USDT", "side": "short", "net_pnl": -3.24, "pnl_usdt": -3.0,
         "fees_usdt": 0.24, "exit_reason": "stop_loss", "strategy": IFC,
         "opened_at": noon - 2 * 3600, "closed_at": noon + 1800},
        {"symbol": "ADA/USDT:USDT", "side": "short", "net_pnl": 9.99, "pnl_usdt": 10.0,
         "fees_usdt": 0.01, "exit_reason": "take_profit", "strategy": IFC,
         "opened_at": IFC_REG_TS - 2 * 86400 - 3600, "closed_at": IFC_REG_TS - 2 * 86400},   # pre-registration
    ]


@pytest.fixture
def report_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "BOT_DIR", str(tmp_path))
    monkeypatch.setattr(dr, "STATE_FILE", str(tmp_path / "trading_state.json"))
    monkeypatch.setattr(dr, "LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setattr(dr, "REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(dr, "PAPER_MAIN_SENTINEL", str(tmp_path / ".paper_main"))
    (tmp_path / "reports").mkdir()
    (tmp_path / "trading_state.json").write_text(json.dumps({"peak_balance": 100.0, "closed_trades": []}))
    return tmp_path


def test_paper_forward_test_registry_pins_the_frozen_facts():
    reg = {e["slot_id"]: e for e in dr.PAPER_FORWARD_TESTS}
    assert IFC in reg
    e = reg[IFC]
    assert "laggard" in e["name"].lower()
    assert e["registered_ts"] == IFC_REG_TS and e["verdict_n"] == 50
    assert e["kill_net_usd"] == -10.0 and e["inconclusive_hard_n"] == 100
    assert e["prereg"] == IFC_PREREG
    assert "TP 250" in e["desc"] and "SL 150" in e["desc"] and "7h" in e["desc"]
    assert "BTC" in e["desc"] and "16 alts" in e["desc"]
    assert "n>=50" in e["verdict"] and "-$10" in e["verdict"] and "n=100" in e["verdict"]
    assert "CI lower > 0" in e["verdict"]


def test_paper_forward_test_registry_matches_the_adjudicator():
    sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))
    from lab_adjudicator import adjudicate
    for e in dr.PAPER_FORWARD_TESTS:
        cfg = adjudicate.EXPERIMENTS[e["slot_id"]]
        assert e["registered_ts"] == cfg["registered_ts"]
        assert e["verdict_n"] == cfg["verdict_n"]
        assert e["kill_net_usd"] == cfg["kill_net_usd"]
        assert e["inconclusive_hard_n"] == cfg["inconclusive_hard_n"]
        assert e["prereg"] == cfg["prereg"]
        assert os.path.exists(os.path.join(BOT_DIR, e["prereg"]))


def test_paper_slot_summaries_today_and_since_registration(report_dir):
    date_str = "2026-09-21"
    (report_dir / f"trading_state_{IFC}.json").write_text(
        json.dumps({"closed_trades": _ifc_rows(date_str), "positions": {
            "LINK/USDT:USDT": {"side": "short", "entry_price": 12.0}}}))
    out = dr.paper_slot_summaries(date_str)
    assert [s["slot_id"] for s in out] == [IFC]
    s = out[0]
    assert s["trades"] == 2 and s["wins"] == 1 and s["losses"] == 1
    assert abs(s["pnl_today"] - 1.52) < 1e-9
    assert s["n_since_reg"] == 2                     # pre-registration row excluded
    assert abs(s["net_since_reg"] - 1.52) < 1e-9
    assert s["open"] == 1
    assert s["killed"] is False


def test_paper_slot_summaries_missing_state_file_is_zero_not_absent(report_dir):
    out = dr.paper_slot_summaries("2026-09-21")
    assert len(out) == 1 and out[0]["trades"] == 0 and out[0]["n_since_reg"] == 0


def test_paper_slot_summaries_never_counts_live_rows_as_sim(report_dir):
    date_str = "2026-09-21"
    rows = _ifc_rows(date_str)
    rows[0]["mode"] = "live"                         # hypothetical real fill — not a sim
    (report_dir / f"trading_state_{IFC}.json").write_text(json.dumps({"closed_trades": rows}))
    s = dr.paper_slot_summaries(date_str)[0]
    assert s["trades"] == 1 and abs(s["pnl_today"] + 3.24) < 1e-9


def test_paper_slot_summaries_reports_kill_sentinel(report_dir):
    (report_dir / f".kill_{IFC}").write_text("registered KILL\n")
    assert dr.paper_slot_summaries("2026-09-21")[0]["killed"] is True


def test_generate_report_renders_the_paper_slot_section(report_dir, monkeypatch):
    date_str = datetime.now(dr.CA_TZ).strftime("%Y-%m-%d")
    (report_dir / f"trading_state_{IFC}.json").write_text(
        json.dumps({"closed_trades": _ifc_rows(date_str), "positions": {}}))
    captured = {}
    monkeypatch.setattr(dr, "send_telegram", lambda *a, **k: captured.update(k) or captured.update({"args": a}))
    path = dr.generate_report()
    md = open(path).read()
    assert "## Paper Forward Test: BTC→alt laggard short (v2)" in md
    assert f"slot `{IFC}`" in md
    assert "Sim trades today: 2 (1W / 1L)" in md
    assert "Sim Net PnL today: $1.52 (NOT real money)" in md
    assert "Since registration: n=2 / 50, net $1.52" in md
    assert "KILL" in md and "n>=50" in md and IFC_PREREG in md
    # real-money totals untouched by the sim rows
    assert "- Trades: 0 (0W / 0L)" in md
    assert "- Net PnL: $0.00" in md


def test_telegram_summary_renders_the_paper_slot_block(report_dir, monkeypatch):
    date_str = datetime.now(dr.CA_TZ).strftime("%Y-%m-%d")
    (report_dir / f"trading_state_{IFC}.json").write_text(
        json.dumps({"closed_trades": _ifc_rows(date_str), "positions": {}}))
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    posted = {}
    import requests
    monkeypatch.setattr(requests, "post", lambda url, json=None, timeout=None: posted.update(json))
    dr.send_telegram("", date_str, 87.12, [], 0.0, 0.0)
    msg = posted["text"]
    assert "📄 <b>PAPER Forward Test: BTC→alt laggard short (v2)</b>" in msg
    assert "2 sim trades | 50% WR | +$1.52 (NOT real money)" in msg
    assert "Since registration: n=2/50, +$1.52" in msg
    assert "Verdict: KILL" in msg
    # parse_mode=HTML — the verdict's raw <, >, & must be entity-escaped or
    # Telegram rejects the whole daily report (400 can't parse entities)
    assert "n&gt;=50 &amp; net&lt;=$0" in msg
    assert "<=" not in msg.split("Verdict:", 1)[1] and ">=" not in msg.split("Verdict:", 1)[1]
