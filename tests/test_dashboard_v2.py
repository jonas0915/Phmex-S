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


def test_sentinel_deploy_ts_matches_2026_04_02_06_01_utc():
    """Sentinel deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC.
    (Moved from test_sentinel_chart.py — the PNG chart is gone, but this
    constant is now the era cutoff for /api/equity?era=sentinel.)"""
    from datetime import datetime, timezone
    import web_dashboard as wd
    expected = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
    assert wd.SENTINEL_DEPLOY_TS == expected
