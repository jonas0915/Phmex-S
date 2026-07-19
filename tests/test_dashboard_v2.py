"""Dashboard v2 "Terminal Pro" shell tests (Task 1)."""
import re
import sys

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")


def test_shell_structure():
    import web_dashboard as wd
    html = wd.build_html()
    # chart node must live OUTSIDE the swapped #content div
    content_pos = html.index('id="content"')
    equity_pos = html.index('id="equity-root"')
    assert equity_pos > html.index("<body")
    content_div = re.search(r'<div id="content".*?</div>\s*<!-- /content -->', html, re.S)
    assert content_div is not None
    assert 'id="equity-root"' not in content_div.group(0)
    # terminal palette present, old palette gone
    assert "#000204" in html and "#f0a500" in html
    assert "fonts.googleapis.com" not in html


def test_ticker_present():
    import web_dashboard as wd
    c = wd.build_content()
    assert 'class="ticker"' in c or 'id="ticker"' in wd.build_html()


def test_equity_endpoint_shape(tmp_path, monkeypatch):
    import web_dashboard as wd
    data = wd.build_equity_series("all")
    assert set(data.keys()) == {"t", "v", "meta"}
    assert len(data["t"]) == len(data["v"]) == len(data["meta"])
    if data["meta"]:
        m = data["meta"][0]
        assert {"sym", "strat", "pnl", "reason", "win"} <= set(m.keys())


def test_equity_sentinel_era_subset():
    import web_dashboard as wd
    a = wd.build_equity_series("all"); s = wd.build_equity_series("sentinel")
    assert len(s["t"]) <= len(a["t"])


def test_merged_blotter_rows():
    import web_dashboard as wd
    rows = wd.collect_blotter_rows(limit=500)
    assert isinstance(rows, list)
    if rows:
        r = rows[0]
        assert {"id", "time_pt", "sym", "side", "strat", "net", "reason", "owner"} <= set(r.keys())
        ts = [x["ts"] for x in rows]
        assert ts == sorted(ts, reverse=True)  # newest first


def test_trade_detail_endpoint():
    import web_dashboard as wd
    rows = wd.collect_blotter_rows(limit=5)
    if rows:
        d = wd.build_trade_detail(rows[0]["id"])
        assert "snapshot" in d  # dict or the string "no snapshot recorded"


def test_trade_detail_resolves_dotted_slot_id(tmp_path, monkeypatch):
    # Slot ids can contain a dot (live example: "ST2.0"). The blotter id is
    # "owner:index", so the drill-down must resolve "ST2.0:0". Regression: the
    # owner-validation regex used to reject the dot, so EVERY ST2.0 trade detail
    # returned {"error": "not found"} (and the flaky endpoint test failed whenever
    # the newest blotter row was an ST2.0 trade).
    import json
    import web_dashboard as wd
    state = {"closed_trades": [{"symbol": "ETH/USDT:USDT", "side": "short",
             "strategy": "ST2.0", "entry_snapshot": {"ob": {"imbalance": 0.4}}}]}
    (tmp_path / "trading_state_ST2.0.json").write_text(json.dumps(state))
    monkeypatch.setattr(wd, "PROJECT_DIR", str(tmp_path))
    d = wd.build_trade_detail("ST2.0:0")
    assert "error" not in d
    assert "snapshot" in d
    assert d["trade"]["owner"] == "ST2.0"


def test_trade_detail_rejects_path_traversal_owner():
    # owner is interpolated into a filename — a slash / traversal must stay rejected
    # even though the dot is now an allowed owner character.
    import web_dashboard as wd
    assert wd.build_trade_detail("../secret:0") == {"error": "not found"}
    assert wd.build_trade_detail("a/b:0") == {"error": "not found"}


SAMPLE_LOG = """
2026-06-12 09:52:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.3)
2026-06-12 09:52:09 [DEBUG] [STRAT] l2_anticipation: 1h ADX 23.2 < 25
2026-06-12 09:52:09 [DEBUG] [HOLD] INJ/USDT:USDT — No confluence signal (1h ADX=23.2)
2026-06-12 09:53:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.9)
"""


def test_parse_pair_adx():
    import web_dashboard as wd
    adx = wd.parse_pair_adx(SAMPLE_LOG.strip().splitlines())
    assert adx["ZEC/USDT:USDT"] == 15.9     # newest wins
    assert adx["INJ/USDT:USDT"] == 23.2
    assert "DOGE/USDT:USDT" not in adx      # absent pair stays absent — never guess


def test_guardrail_panel_math(tmp_path, monkeypatch):
    import web_dashboard as wd
    html = wd._build_slots_guardrails()
    assert "SLOTS" in html.upper()
    # if 5m_mean_revert is live, headroom string present
    import json, os
    mode = os.path.join(wd.PROJECT_DIR, "trading_state_5m_mean_revert_mode.json")
    if os.path.exists(mode) and not json.load(open(mode)).get("paper_mode", True):
        assert "headroom" in html.lower() or "HDRM" in html


def test_sentinel_deploy_ts_matches_2026_04_02_06_01_utc():
    """Sentinel deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC.
    (Moved from test_sentinel_chart.py — the PNG chart is gone, but this
    constant is now the era cutoff for /api/equity?era=sentinel.)"""
    from datetime import datetime, timezone
    import web_dashboard as wd
    expected = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
    assert wd.SENTINEL_DEPLOY_TS == expected


def test_htf_l2_paper_signal_box_present():
    """HTF_L2_PAPER probe (2026-07-18) must surface on the dashboard (project
    rule: every bot update propagates to Telegram AND dashboard). The box maps
    slot_id -> trading_state_HTF_L2_PAPER.json via the generic signal-card
    loop, and its title must stay distinct from the MAIN LIVE htf_l2 box."""
    import web_dashboard as wd
    boxes = {b[0]: b[1] for b in wd._SIGNAL_BOXES}
    assert "HTF_L2_PAPER" in boxes
    assert "PAPER" in boxes["HTF_L2_PAPER"]
    assert boxes["HTF_L2_PAPER"] != boxes["5m_scalp"]   # main-live box untouched
    assert "MAIN LIVE" in boxes["5m_scalp"]
