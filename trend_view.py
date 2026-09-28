"""TREND tab for web_dashboard.py — the pivot target (docs/2026-09-27-pivot-plan.md):
the Donchian BTC/ETH trend books, still PAPER until the 10/14/2026 review.

Pure, file-driven, zero exchange calls. Every figure is computed from
trading_state_DONCHIAN_<SYM>.json (the paper book) and donchian_signal_<SYM>.json
(the rule's own daily replica). Methods match the 9/27 verification:
- book weight = paper notional held (margin at 1x) / $100 base (donchian_slot.BASE_NOTIONAL_USDT)
- fidelity = book w sampled 6h after the 00:00 UTC close that follows each signal date,
  |book w - replica w| > 0.10 is a breach day (spec: > 3 breaches in 14 days = BUG)
- benchmarks are BEFORE fees: replica = sum w_i x $100 x next-day return;
  plain hold = the same average w held every day / bought once at the first close.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SYMBOLS = ("BTC", "ETH")
BASE_NOTIONAL = 100.0          # donchian_slot.BASE_NOTIONAL_USDT
FIDELITY_TOL = 0.10            # spec: daily |bot w - replica w| > 0.10
FIDELITY_MAX_BREACHES = 3      # spec: > 3 days in 14d -> BUG
MAX_EXPOSURE = 2.0             # donchian_slot.VOL_CAP: w (position / $100 base) never exceeds 2.0
KILL_LINE = -15.0              # spec: net <= -$15 on the $100 base -> retire
REVIEW_DATE = date(2026, 10, 14)
SAMPLE_HOURS = 6               # after the 00:00 UTC roll (5:00 PM PT)
PT = ZoneInfo("America/Los_Angeles")


def load_inputs(project_dir: str) -> tuple[dict, dict]:
    """({sym: state}, {sym: signal days}) — missing/unreadable files are simply absent."""
    states, signals = {}, {}
    for sym in SYMBOLS:
        try:
            with open(os.path.join(project_dir, f"trading_state_DONCHIAN_{sym}.json")) as f:
                states[sym] = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        try:
            with open(os.path.join(project_dir, f"donchian_signal_{sym}.json")) as f:
                signals[sym] = json.load(f).get("days") or []
        except (OSError, json.JSONDecodeError):
            pass
    return states, signals


def _intervals(state: dict) -> list:
    out = [(t.get("opened_at") or 0, t.get("closed_at") or 0, t.get("margin") or 0.0)
           for t in state.get("closed_trades") or []]
    out += [(p.get("opened_at") or 0, float("inf"), p.get("margin") or 0.0)
            for p in (state.get("positions") or {}).values()]
    return out


def book_weight_at(state: dict, ts: float) -> float:
    return sum(m for a, b, m in _intervals(state) if a <= ts < b) / BASE_NOTIONAL


def _sample_ts(day: str) -> float:
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return (d + timedelta(days=1, hours=SAMPLE_HOURS)).timestamp()


def fidelity_rows(state: dict, days: list) -> list:
    rows = []
    for d in days:
        bw = book_weight_at(state, _sample_ts(d["date"]))
        rows.append({"date": d["date"], "book_w": bw, "rule_w": d["w"],
                     "breach": abs(bw - d["w"]) > FIDELITY_TOL + 1e-12})
    return rows


def breaches_last_14(rows: list) -> int:
    return sum(1 for r in rows[-14:] if r["breach"])


def benchmarks(days: list):
    if len(days) < 2:
        return None
    steps = len(days) - 1
    rets = [days[i + 1]["close"] / days[i]["close"] - 1 for i in range(steps)]
    replica = sum(days[i]["w"] * BASE_NOTIONAL * rets[i] for i in range(steps))
    avg_w = sum(d["w"] for d in days[:-1]) / steps
    return {"steps": steps, "replica": replica, "avg_w": avg_w,
            "hold_const_w": sum(avg_w * BASE_NOTIONAL * r for r in rets),
            "static_buy": avg_w * BASE_NOTIONAL * (days[-1]["close"] / days[0]["close"] - 1),
            "first": days[0]["date"], "last": days[-1]["date"]}


def book_summary(state: dict, last_close):
    trades = state.get("closed_trades") or []
    net = sum(t.get("net_pnl") or 0.0 for t in trades)
    reasons = [t.get("exit_reason") or t.get("reason") or "" for t in trades]
    positions = list((state.get("positions") or {}).values())
    open_notional = sum(p.get("margin") or 0.0 for p in positions)
    upnl = None
    if positions and last_close:
        upnl = sum((p.get("margin") or 0.0) * (last_close / p["entry_price"] - 1)
                   for p in positions if p.get("entry_price"))
    return {"n": len(trades), "net": net, "fees": sum(t.get("fees_usdt") or 0.0 for t in trades),
            "wins": sum(1 for t in trades if (t.get("net_pnl") or 0) > 0),
            "n_stops": sum(1 for r in reasons if "stop" in r),
            "n_rebal": sum(1 for r in reasons if "rebalance" in r),
            "open_notional": open_notional, "open_upnl": upnl,
            "open_since": min((p.get("opened_at") or 0) for p in positions) if positions else None,
            "kill_room": net - KILL_LINE, "recent": trades[-8:],
            "leverage": (sum((p.get("amount") or 0.0) * (p.get("entry_price") or 0.0) for p in positions)
                         / open_notional) if positions and open_notional else None,
            "exposure_x": sum((p.get("amount") or 0.0) * (p.get("entry_price") or 0.0) for p in positions)
                          / BASE_NOTIONAL,
            "roi_pct": net / BASE_NOTIONAL * 100,
            "roi_pct_incl_open": (net + (upnl or 0.0)) / BASE_NOTIONAL * 100,
            "win_rate_pct": (sum(1 for t in trades if (t.get("net_pnl") or 0) > 0) / len(trades) * 100)
                            if trades else None}


def equity_curve(state: dict, days: list):
    """Cumulative return on the $100 base at each daily close: closed net (after modelled
    fees) booked by the sample time + every position held then, marked at that close.
    Sampled like fidelity (6h after the roll that follows the signal date); plotted at
    the 00:00 UTC close that ends the day."""
    if not days:
        return None
    trades = state.get("closed_trades") or []
    held = [(t.get("opened_at") or 0, t.get("closed_at") or 0, t.get("margin") or 0.0, t.get("entry_price"))
            for t in trades]
    held += [(p.get("opened_at") or 0, float("inf"), p.get("margin") or 0.0, p.get("entry_price"))
             for p in (state.get("positions") or {}).values()]
    t_out, v_out, labels = [], [], []
    for d in days:
        ts = _sample_ts(d["date"])
        closed = sum(t.get("net_pnl") or 0.0 for t in trades if (t.get("closed_at") or 0) <= ts)
        mark = sum(m * (d["close"] / e - 1) for a, b, m, e in held if a <= ts < b and e)
        close_ts = datetime.fromisoformat(d["date"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
        t_out.append(close_ts.timestamp())
        v_out.append((closed + mark) / BASE_NOTIONAL * 100)
        labels.append(f"{int(d['date'][5:7])}/{int(d['date'][8:10])}")
    peak, max_dd = float("-inf"), 0.0
    for v in v_out:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
    return {"t": t_out, "v": v_out, "label": labels, "max_dd_pct": max_dd}


def days_to_review(today: date) -> int:
    return (REVIEW_DATE - today).days


# ── HTML ──────────────────────────────────────────────────────────────────
def _usd(x, signed=True) -> str:
    if x is None:
        return "&mdash;"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    txt = f"{'+' if signed and x > 0 else ''}{'-' if x < 0 else ''}${abs(x):,.2f}"
    return f"<span class='{cls}'>{txt}</span>" if cls else txt


def _pct(x) -> str:
    if x is None:
        return "&mdash;"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    txt = f"{'+' if x > 0 else ''}{x:.2f}%"
    return f"<span class='{cls}'>{txt}</span>" if cls else txt


def _pt(ts) -> str:
    if not ts:
        return "&mdash;"
    local = datetime.fromtimestamp(ts, tz=PT)          # owner reads times in PT, wherever the Mac is
    return local.strftime("%-m/%-d %-I:%M %p") + " PT"


def _book_card(sym: str, state, days, today: date = None, live: bool = False) -> str:
    title = f"DONCHIAN {sym} &mdash; TREND BOOK ({'LIVE' if live else 'PAPER'})"
    if state is None:
        return f"<div class='panel' id=\"trend-{sym}\"><div class='ptitle'>{title}</div>no state file for {sym}</div>"
    last = days[-1] if days else None
    s = book_summary(state, last["close"] if last else None)
    wr = f"{s['wins']}/{s['n']}" if s["n"] else "&mdash;"
    rule_now = (f"{last['w']:.3f} ({last.get('n_long', '?')}/9 sub-models long) at the "
                f"{last['date']} close ${last['close']:,.2f}") if last else "no signal file"
    curve = equity_curve(state, days)
    roi = s["roi_pct"]
    rows = [
        (_roi_label(days, today),
         f"<b>{_pct(roi)}</b> &middot; ${BASE_NOTIONAL:,.2f} &rarr; ${BASE_NOTIONAL + s['net']:,.2f} closed"
         f" &middot; incl. open position {_pct(s['roi_pct_incl_open'])}"),
        ("Win rate", (f"<b>{s['win_rate_pct']:.0f}%</b> ({s['wins']}/{s['n']} exits closed green; "
                      "most exits are rebalances of the same trend)") if s["n"] else "&mdash;"),
        ("Max drawdown (daily closes)", _pct(-curve["max_dd_pct"]) if curve else "&mdash;"),
        ("Leverage",
         (f"<b>{s['leverage']:.2f}x</b> (position value / margin) &middot; exposure "
          f"{s['exposure_x']:.2f}x of the ${BASE_NOTIONAL:,.0f} capital (design max {MAX_EXPOSURE:.1f}x)")
         if s["leverage"] is not None else
         f"flat &middot; exposure 0.00x of the ${BASE_NOTIONAL:,.0f} capital (design max {MAX_EXPOSURE:.1f}x)"),
        ("Position now", f"${s['open_notional']:,.2f} long (w {s['open_notional'] / BASE_NOTIONAL:.3f}), "
                         f"since {_pt(s['open_since'])}" if s["open_notional"] else "flat"),
        ("Open P&amp;L at last daily close", _usd(s["open_upnl"])),
        ("Rule wants", rule_now),
        ("Closed P&amp;L (after modelled fees)", f"{_usd(s['net'])} &middot; fees ${s['fees']:,.2f}"),
        ("Exits", f"{s['n']} ({s['n_rebal']} rebalances, {s['n_stops']} stops) &middot; winners {wr}"),
        ("Kill line", f"&minus;$15.00 &middot; room {_usd(s['kill_room'], signed=False)}"),
    ]
    if live:
        lt = [t for t in state.get("closed_trades") or [] if t.get("mode") == "live"]
        rows.insert(0, ("Live trades (real money)",
                        f"<b>{len(lt)} closed</b> &middot; net {_usd(sum(t.get('net_pnl') or 0.0 for t in lt))} "
                        f"&middot; kill line &minus;$26 &rarr; back to paper"))
    body = "".join(f"<tr><td class='dim'>{k}</td><td>{v}</td></tr>" for k, v in rows)
    recent = "".join(
        f"<tr><td>{_pt(t.get('closed_at'))}</td><td>{html.escape((t.get('exit_reason') or '').replace('donchian_', ''))}</td>"
        f"<td>{_usd(t.get('net_pnl'))}</td></tr>" for t in reversed(s["recent"]))
    return (f"<div class='panel' id=\"trend-{sym}\"><div class='ptitle'>{title}</div>"
            f"<table>{body}</table>"
            f"<div class='sub'>Cumulative return on the $100 base at each daily close "
            f"(after modelled fees, open position marked; excludes funding)</div>"
            f"<div class=\"trend-chart\" id=\"chart-{sym}\"></div>"
            f"<div class='sub'>Last {len(s['recent'])} exits (a rebalance resizes the same trend; it is not a new trade)</div>"
            f"<table><tr class='dim'><th>CLOSED</th><th>WHY</th><th>NET</th></tr>{recent}</table></div>")


def _roi_label(days: list, today) -> str:
    """Total ROI is since the book's first daily close; while that start is in the current
    year it is also the year-to-date figure, so say so (drops off by itself next year)."""
    if not days:
        return f"Total ROI on the ${BASE_NOTIONAL:,.0f} starting capital"
    start = date.fromisoformat(days[0]["date"])
    label = f"Total ROI on the ${BASE_NOTIONAL:,.0f} starting capital (since {start.month}/{start.day}/{start.year}"
    if today is not None and today.year == start.year:
        label += f" &mdash; also {today.year} YTD"
    return label + ")"


def _bench_panel(signals: dict) -> str:
    rows = ""
    for sym in SYMBOLS:
        b = benchmarks(signals.get(sym) or [])
        if not b:
            rows += f"<tr><td>{sym}</td><td colspan='4'>no signal file</td></tr>"
            continue
        verdict = "rule ahead" if b["replica"] > b["hold_const_w"] else "plain hold ahead"
        rows += (f"<tr><td>{sym}</td><td>{_usd(b['replica'])}</td><td>{_usd(b['hold_const_w'])}</td>"
                 f"<td>{_usd(b['static_buy'])}</td><td>{verdict}</td></tr>")
    first = next((benchmarks(signals[s]) for s in SYMBOLS if benchmarks(signals.get(s) or [])), None)
    span = f"{first['first']} &rarr; {first['last']}, {first['steps']} daily steps" if first else ""
    return ("<div class='panel' id=\"trend-bench\"><div class='ptitle'>Rule vs plain hold (before fees)</div>"
            "<div class='sig-desc'>Does the trend rule's timing add anything? <b>Rule</b> = the rule's own daily "
            "replica on the $100 base. <b>Hold</b> = holding the rule's AVERAGE position every day. "
            "<b>Buy once</b> = that average position bought at the first close. If hold beats the rule, the "
            f"timing has not earned anything yet. {span}.</div>"
            "<table><tr class='dim'><th></th><th>RULE</th><th>HOLD</th><th>BUY ONCE</th><th></th></tr>"
            f"{rows}</table></div>")


def _fidelity_panel(states: dict, signals: dict) -> str:
    rows = ""
    for sym in SYMBOLS:
        st, days = states.get(sym), signals.get(sym) or []
        if st is None or not days:
            rows += f"<tr><td>{sym}</td><td colspan='3'>no state file or no signal file</td></tr>"
            continue
        fr = fidelity_rows(st, days)
        last14 = breaches_last_14(fr)
        dates = ", ".join(r["date"][5:] for r in fr if r["breach"]) or "none"
        flag = "BUG (&gt;3 in 14d)" if last14 > FIDELITY_MAX_BREACHES else "ok"
        rows += f"<tr><td>{sym}</td><td>{last14}</td><td>{flag}</td><td>{dates}</td></tr>"
    return ("<div class='panel' id=\"trend-fidelity\"><div class='ptitle'>Fidelity &mdash; is the paper book "
            "following the rule?</div><div class='sig-desc'>Each day the paper position (6h after the 5:00 PM PT "
            "roll) is compared with what the rule wanted. A gap over 0.10 is a breach day; more than 3 in any "
            "14 days is a BUG under the spec. The 9/9&ndash;9/20 days are the wind-down, when the bot was "
            "stopped with positions frozen.</div>"
            "<table><tr class='dim'><th></th><th>LAST 14D</th><th></th><th>ALL BREACH DAYS</th></tr>"
            f"{rows}</table></div>")


def curves(states: dict, signals: dict) -> dict:
    """{sym: {t, v, label, max_dd_pct}} for the per-book charts (absent when a file is missing)."""
    out = {}
    for sym in SYMBOLS:
        if states.get(sym) is not None and signals.get(sym):
            out[sym] = equity_curve(states[sym], signals[sym])
    return out


def _mode_line(live_ids) -> str:
    live = [s for s in SYMBOLS if f"DONCHIAN_{s}" in live_ids]
    if not live:
        return "Both books are <b>PAPER</b> &mdash; no live orders, no money at risk."
    paper = [s for s in SYMBOLS if s not in live]
    return (f"{'/'.join(live)} is <b>LIVE</b> (real money: 2x the rule's size on account equity, "
            f"2x isolated, resting stop &minus;15% ratcheting, TP +25%, kill line &minus;$26)"
            + (f"; {'/'.join(paper)} is <b>PAPER</b>." if paper else "."))


def build_trend_content(states: dict, signals: dict, today: date, live_ids=frozenset()) -> str:
    left = days_to_review(today)
    when = (f"{left} days away" if left > 0 else "today" if left == 0 else f"{-left} days ago")
    header = ("<div class='panel' id=\"trend-status\"><div class='ptitle'>Pivot status</div>"
              "<div>Target: a slow, long-or-flat trend follower on BTC and ETH only (plan: "
              f"docs/2026-09-27-pivot-plan.md). {_mode_line(live_ids)} "
              f"Review: <b>Wed 10/14/2026</b> ({when}). Agreed test: both books positive and fidelity clean "
              "&rarr; the ETH-only one-lot live build is offered.</div>"
              "<div class='sig-desc'>Paper P&amp;L does not include funding. Measured 9/27 over the last 100 "
              "settlements: longs paid about 0.41% (BTC) and 0.35% (ETH) of the position per 30 days.</div></div>")
    cards = "".join(_book_card(sym, states.get(sym), signals.get(sym) or [], today,
                               live=f"DONCHIAN_{sym}" in live_ids) for sym in SYMBOLS)
    return (f"<div id=\"trend-grid\">{header}{cards}{_bench_panel(signals)}"
            f"{_fidelity_panel(states, signals)}</div>")
