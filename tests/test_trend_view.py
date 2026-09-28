"""TREND tab (pivot plan docs/2026-09-27-pivot-plan.md): the Donchian BTC/ETH
paper books, book-vs-rule fidelity, and the rule vs plain-hold benchmark.
Read-only, file-driven, zero exchange calls."""
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

import trend_view as tv

DAY = 86400


def _ts(d: str, hours: float = 0.0) -> float:
    return (datetime.fromisoformat(d).replace(tzinfo=timezone.utc) + timedelta(hours=hours)).timestamp()


def _trade(o, c, margin, net, reason="donchian_rebalance", fees=0.01):
    return {"opened_at": o, "closed_at": c, "margin": margin, "net_pnl": net,
            "fees_usdt": fees, "exit_reason": reason, "entry_price": 100.0, "exit_price": 101.0}


# ── book weight / fidelity ────────────────────────────────────────────────
def test_book_weight_sums_margin_held_at_time_over_base():
    st = {"closed_trades": [_trade(_ts("2026-07-01", 1), _ts("2026-07-03", 1), 30.0, 0.1)],
          "positions": {"X": {"opened_at": _ts("2026-07-02", 1), "margin": 20.0, "entry_price": 1.0}}}
    assert tv.book_weight_at(st, _ts("2026-07-02", 6)) == pytest.approx(0.50)
    assert tv.book_weight_at(st, _ts("2026-07-04", 6)) == pytest.approx(0.20)
    assert tv.book_weight_at(st, _ts("2026-06-30", 6)) == 0.0


def test_fidelity_samples_book_six_hours_after_the_utc_close_that_follows_the_signal_date():
    # signal for 7/01 is traded after the 7/02 00:00 UTC close; sample at 7/02 06:00 UTC
    st = {"closed_trades": [_trade(_ts("2026-07-02", 0.5), _ts("2026-07-03", 0.5), 40.0, 0.0)], "positions": {}}
    days = [{"date": "2026-07-01", "w": 0.40}, {"date": "2026-07-02", "w": 0.10}, {"date": "2026-07-03", "w": 0.0}]
    rows = tv.fidelity_rows(st, days)
    assert [r["date"] for r in rows] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert [round(r["book_w"], 2) for r in rows] == [0.40, 0.0, 0.0]
    assert [r["breach"] for r in rows] == [False, False, False]      # |0-0.10| is not > 0.10
    days[1]["w"] = 0.25
    assert [r["breach"] for r in tv.fidelity_rows(st, days)] == [False, True, False]


def test_breaches_in_last_14_days_counts_only_the_trailing_window():
    rows = [{"date": f"2026-08-{d:02d}", "breach": d in (1, 10, 20, 21)} for d in range(1, 22)]
    assert tv.breaches_last_14(rows) == 3      # 8/08..8/21 window holds 10, 20, 21


# ── rule vs hold benchmark ────────────────────────────────────────────────
def test_benchmarks_before_fees():
    days = [{"date": "d0", "w": 0.5, "close": 100.0}, {"date": "d1", "w": 0.0, "close": 110.0},
            {"date": "d2", "w": 0.0, "close": 99.0}]
    b = tv.benchmarks(days)
    assert b["replica"] == pytest.approx(0.5 * 100 * 0.10)                  # only step 0 held
    assert b["avg_w"] == pytest.approx(0.25)
    assert b["hold_const_w"] == pytest.approx(0.25 * 100 * (0.10 + (99 / 110 - 1)))
    assert b["static_buy"] == pytest.approx(0.25 * 100 * (99 / 100 - 1))
    assert b["steps"] == 2
    assert tv.benchmarks(days[:1]) is None


# ── book summary ──────────────────────────────────────────────────────────
def test_book_summary_counts_stops_rebalances_net_fees_and_marks_open_position():
    st = {"closed_trades": [_trade(0, 1, 30, 1.00), _trade(1, 2, 30, -0.40, reason="donchian_stop", fees=0.02)],
          "positions": {"ETH/USDT:USDT": {"opened_at": 5, "margin": 30.0, "entry_price": 2000.0}}}
    s = tv.book_summary(st, last_close=2100.0)
    assert s["n"] == 2 and s["n_stops"] == 1 and s["n_rebal"] == 1
    assert s["net"] == pytest.approx(0.60) and s["fees"] == pytest.approx(0.03)
    assert s["wins"] == 1
    assert s["open_notional"] == pytest.approx(30.0)
    assert s["open_upnl"] == pytest.approx(30.0 * (2100 / 2000 - 1))
    assert s["kill_room"] == pytest.approx(0.60 + 15.0)


def test_book_summary_empty_book():
    s = tv.book_summary({"closed_trades": [], "positions": {}}, last_close=None)
    assert s["n"] == 0 and s["net"] == 0.0 and s["open_notional"] == 0.0 and s["open_upnl"] is None


def test_days_to_review():
    assert tv.days_to_review(date(2026, 9, 27)) == 17
    assert tv.days_to_review(date(2026, 10, 14)) == 0
    assert tv.days_to_review(date(2026, 10, 20)) == -6


# ── HTML ──────────────────────────────────────────────────────────────────
def _fixture_inputs():
    days = [{"date": "2026-07-01", "w": 0.3, "close": 100.0, "n_long": 3},
            {"date": "2026-07-02", "w": 0.3, "close": 104.0, "n_long": 3}]
    st = {"closed_trades": [_trade(_ts("2026-07-02", 0.5), _ts("2026-07-03", 0.5), 30.0, 0.9)], "positions": {}}
    return {"BTC": st, "ETH": st}, {"BTC": days, "ETH": days}


def test_trend_content_renders_both_books_and_honest_labels():
    states, signals = _fixture_inputs()
    html = tv.build_trend_content(states, signals, today=date(2026, 9, 27))
    for needle in ('id="trend-BTC"', 'id="trend-ETH"', "PAPER", "10/14/2026", "17 days",
                   "before fees", "funding", "Rule vs plain hold", "Fidelity"):
        assert needle in html, needle
    assert "LIVE" not in html.replace("no live", "")       # never implies a live book


def test_trend_content_survives_missing_files():
    html = tv.build_trend_content({}, {}, today=date(2026, 9, 27))
    assert "no state file" in html and "no signal file" in html


# ── real data regression (history up to 9/27 is immutable) ───────────────
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _real(sym):
    sp = os.path.join(REPO, f"trading_state_DONCHIAN_{sym}.json")
    gp = os.path.join(REPO, f"donchian_signal_{sym}.json")
    if not (os.path.exists(sp) and os.path.exists(gp)):
        pytest.skip("Donchian state/signal files not present")
    days = [d for d in json.load(open(gp))["days"] if d["date"] <= "2026-09-27"]
    return json.load(open(sp)), days


def test_real_fidelity_matches_the_verified_9_27_breach_days():
    st, days = _real("ETH")
    assert [r["date"][5:] for r in tv.fidelity_rows(st, days) if r["breach"]] == \
        ["07-26", "07-27", "09-10", "09-15", "09-16", "09-17"]
    st, days = _real("BTC")
    assert not [r for r in tv.fidelity_rows(st, days) if r["breach"]]


def test_real_benchmarks_match_the_verified_9_27_figures():
    b = tv.benchmarks(_real("BTC")[1])
    assert (round(b["replica"], 2), round(b["hold_const_w"], 2), round(b["static_buy"], 2)) == (6.45, 7.16, 7.81)
    b = tv.benchmarks(_real("ETH")[1])
    assert (round(b["replica"], 2), round(b["hold_const_w"], 2), round(b["static_buy"], 2)) == (5.53, 8.19, 9.12)


# ── dashboard wiring ──────────────────────────────────────────────────────
def test_trend_page_shell_has_nav_content_and_polls_its_own_endpoint():
    import web_dashboard as wd
    page = wd.build_trend_html()
    assert page.startswith("<!DOCTYPE html>")
    assert 'id="trend-grid"' in page and 'id="trend-content"' in page
    assert "fetch('/api/trend')" in page
    assert "/static/uplot.iife.min.js" in page and "drawTrendCharts" in page
    assert 'href="/"' in page and 'href="/trend"' in page


def test_main_page_links_to_the_trend_tab():
    import web_dashboard as wd
    page = wd.build_html()
    assert 'href="/trend"' in page and 'id="tabs"' in page


def test_api_trend_payload_is_the_trend_content():
    import web_dashboard as wd
    payload = wd.build_trend_payload()
    assert set(payload) == {"content", "curves"} and 'id="trend-grid"' in payload["content"]
    for sym in ("BTC", "ETH"):
        c = payload["curves"].get(sym)
        if c is not None:
            assert len(c["t"]) == len(c["v"]) == len(c["label"]) and c["t"] == sorted(c["t"])


def test_times_render_in_pacific_regardless_of_host_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    import time as _t
    _t.tzset()
    try:
        # 2026-09-28 00:00:37 UTC = 9/27 5:00 PM PDT
        assert tv._pt(_ts("2026-09-28", 37 / 3600)) == "9/27 5:00 PM PT"
    finally:
        monkeypatch.delenv("TZ")
        _t.tzset()



# ── performance: ROI %, win rate, equity curve ────────────────────────────
def test_book_summary_reports_roi_pct_and_win_rate_pct():
    st = {"closed_trades": [_trade(0, 1, 30, 1.00), _trade(1, 2, 30, -0.40), _trade(2, 3, 30, 0.90)],
          "positions": {"X": {"opened_at": 5, "margin": 50.0, "entry_price": 100.0}}}
    s = tv.book_summary(st, last_close=102.0)
    assert s["roi_pct"] == pytest.approx(1.50)                   # closed net / $100 base
    assert s["roi_pct_incl_open"] == pytest.approx(1.50 + 1.00)  # + open 50 x 2%
    assert s["win_rate_pct"] == pytest.approx(200 / 3)
    assert tv.book_summary({"closed_trades": [], "positions": {}}, None)["win_rate_pct"] is None


def test_equity_curve_marks_closed_plus_open_at_each_daily_close():
    o1, c1 = _ts("2026-07-02", 0.5), _ts("2026-07-04", 0.5)
    st = {"closed_trades": [dict(_trade(o1, c1, 50.0, 2.0), entry_price=100.0)],
          "positions": {"X": {"opened_at": _ts("2026-07-04", 0.5), "margin": 20.0, "entry_price": 110.0}}}
    days = [{"date": "2026-07-01", "w": 0.5, "close": 100.0}, {"date": "2026-07-02", "w": 0.5, "close": 104.0},
            {"date": "2026-07-03", "w": 0.2, "close": 110.0}, {"date": "2026-07-04", "w": 0.2, "close": 99.0}]
    c = tv.equity_curve(st, days)
    assert c["label"] == ["7/1", "7/2", "7/3", "7/4"]
    # 7/1: 50 open at 100 -> 0; 7/2: 50 x 4% = 2.0; 7/3: closed +2.0, 20 open at 110 -> 0; 7/4: 2.0 + 20 x (-10%)
    assert c["v"] == pytest.approx([0.0, 2.0, 2.0, 0.0])
    assert c["t"][0] == pytest.approx(_ts("2026-07-02"))        # plotted at the close that ends the day
    assert c["max_dd_pct"] == pytest.approx(2.0)
    assert tv.equity_curve(st, []) is None


def test_trend_content_shows_roi_win_rate_and_a_chart_per_book():
    states, signals = _fixture_inputs()
    html = tv.build_trend_content(states, signals, today=date(2026, 9, 27))
    for needle in ("Total ROI", "Win rate", "Max drawdown", 'id="chart-BTC"', 'id="chart-ETH"'):
        assert needle in html, needle


def test_real_equity_curve_ends_at_book_net_plus_open_mark_on_9_27():
    for sym, want in (("BTC", 6.49), ("ETH", 6.87)):
        st, days = _real(sym)
        c = tv.equity_curve(st, days)
        assert c["label"][0] == "7/16" and c["label"][-1] == "9/27"
        assert round(c["v"][-1], 2) == want, sym


def test_roi_label_says_ytd_only_while_the_book_started_this_year():
    states, signals = _fixture_inputs()                      # book starts 2026-07-01
    html = tv.build_trend_content(states, signals, today=date(2026, 9, 27))
    assert "Total ROI on the $100 starting capital (since 7/1/2026 &mdash; also 2026 YTD)" in html
    assert "$100.00 &rarr; $100.90" in html                  # capital -> capital + closed net (+0.90)
    html = tv.build_trend_content(states, signals, today=date(2027, 1, 5))
    assert "Total ROI on the $100 starting capital (since 7/1/2026)" in html and "YTD" not in html
