#!/usr/bin/env python3
"""
Phmex-S HTML Dashboard — read-only web monitor.
Reads trading_state.json and bot.log only. Zero API calls, zero bot imports.

Usage:  python web_dashboard.py
Open:   http://127.0.0.1:8050
"""
import io
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from collections import defaultdict
from html import escape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import matplotlib
matplotlib.use("Agg")  # MUST be before pyplot import
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_DIR, "trading_state.json")
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "bot.log")
HOST = "0.0.0.0"
PORT = 8050
CHART_INTERVAL = 30  # seconds between chart refreshes
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# ── Chart cache ──────────────────────────────────────────────────────────
_chart_cache = {}  # name -> PNG bytes
_chart_lock = threading.Lock()


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def read_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"peak_balance": 0, "closed_trades": []}


def tail_log(n: int = 500) -> list[str]:
    try:
        result = subprocess.run(
            ["tail", "-n", str(n), LOG_FILE],
            capture_output=True, text=True, timeout=5
        )
        return [strip_ansi(line) for line in result.stdout.splitlines()]
    except Exception:
        return []


# ── Log parsing ──────────────────────────────────────────────────────────
def parse_open_positions(lines: list[str]) -> list[dict]:
    positions = {}
    for line in lines:
        # Opened or synced positions (with entry price)
        m = re.search(r'Position opened: (\w+) ([\w/:.]+) \| Entry: ([\d.]+)', line)
        if m:
            positions[m.group(2)] = {"side": m.group(1), "symbol": m.group(2), "entry": float(m.group(3))}
        m = re.search(r'\[SYNC\] Loaded (\w+) ([\w/:.]+) \| Entry: ([\d.]+)', line)
        if m:
            positions[m.group(2)] = {"side": m.group(1), "symbol": m.group(2), "entry": float(m.group(3))}
        # Closed positions — remove
        m = re.search(r'Position closed: \w+ ([\w/:.]+)', line)
        if m:
            positions.pop(m.group(1), None)
        # [HOLD] lines confirm a position is still open (may lack entry price)
        m = re.search(r'\[HOLD\] ([\w/:.]+)', line)
        if m:
            sym = m.group(1)
            if sym not in positions:
                positions[sym] = {"side": "?", "symbol": sym, "entry": 0}
    return list(positions.values())


def parse_latest_cycle(lines: list[str]) -> str:
    for line in reversed(lines):
        m = re.search(r'Cycle #(\d+) \| Positions: (\d+)', line)
        if m:
            return f"Cycle #{m.group(1)} | Positions: {m.group(2)}"
    return "Unknown"


def parse_regime_status(lines: list[str]) -> str:
    for line in reversed(lines):
        if "[REGIME]" in line:
            m = re.search(r'\[REGIME\] (.+)', line)
            if m:
                return m.group(1)
        if "[DRAWDOWN]" in line:
            m = re.search(r'\[DRAWDOWN\] (.+)', line)
            if m:
                return m.group(1)
    return "Normal"


def parse_watchlist(lines: list[str]) -> dict:
    """Parse current watchlist: active pairs from HOLD lines, scanner pairs with scores, and open positions."""
    base_pairs = []
    scanner_pairs = []  # list of {symbol, score, momentum, vol_spike, atr, change_24h, trend}
    open_symbols = set()
    hold_pairs = set()  # pairs the bot is actively scanning (from [HOLD] lines)

    # Walk forward to get latest state
    for line in lines:
        # Base trading pairs (logged at startup)
        m = re.search(r'Trading pairs: (.+)', line)
        if m:
            base_pairs = [s.strip() for s in m.group(1).split(',')]

        # Scanner updated pairs (logged when scanner completes)
        m = re.search(r'\[SCANNER\] Updated pairs: (.+)', line)
        if m:
            base_pairs = [s.strip() for s in m.group(1).split(',')]

        # [HOLD] lines — these show every pair the bot is actively watching
        m = re.search(r'\[HOLD\] ([\w/:.]+)', line)
        if m:
            hold_pairs.add(m.group(1))

        # Scanner results with scores
        m = re.search(r'(\S+/USDT:USDT)\s+score=([\d.]+) \| 10c=([\-\+\d.]+)% \| vol=([\d.]+)x \| atr=([\d.]+)% \| 24h=\s*([\-\+\d.]+)% (↑|↓)', line)
        if m:
            scanner_pairs.append({
                "symbol": m.group(1),
                "score": float(m.group(2)),
                "momentum": float(m.group(3)),
                "vol_spike": float(m.group(4)),
                "atr": float(m.group(5)),
                "change_24h": float(m.group(6)),
                "trend": m.group(7),
            })

        # Scanner updated — reset scanner list to only keep latest batch
        if '[SCALPSCAN] Top' in line:
            scanner_pairs = []

        # Track open positions
        m = re.search(r'Position opened: \w+ ([\w/:.]+)', line)
        if m:
            open_symbols.add(m.group(1))
        m = re.search(r'\[SYNC\] Loaded \w+ ([\w/:.]+)', line)
        if m:
            open_symbols.add(m.group(1))
        m = re.search(r'Position closed: \w+ ([\w/:.]+)', line)
        if m:
            open_symbols.discard(m.group(1))

    # Use hold_pairs as the primary watchlist if available (most accurate, from recent cycles)
    if hold_pairs:
        base_pairs = sorted(hold_pairs)

    return {
        "base_pairs": base_pairs,
        "scanner_pairs": scanner_pairs,
        "open_symbols": open_symbols,
    }


def get_recent_activity(lines: list[str], n: int = 12) -> list[str]:
    activity = []
    keywords = ["ENTRY:", "Position closed:", "EARLY EXIT", "TIME EXIT",
                "HARD_TIME_EXIT", "REGIME", "DRAWDOWN", "SCANNER"]
    for line in reversed(lines):
        if any(kw in line for kw in keywords):
            activity.append(line.strip())
            if len(activity) >= n:
                break
    return list(reversed(activity))


def build_audit_table(trades: list[dict]) -> str:
    """Build a comprehensive performance audit table with all trades and breakdowns."""
    if not trades:
        return '<div style="color:#7e8aa0;text-align:center;padding:20px">No trades to audit</div>'

    # Per-pair breakdown
    pair_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    # Per-strategy breakdown
    strat_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    # Per-exit-reason breakdown
    exit_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    # Per-side breakdown
    side_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    # Hourly breakdown
    hourly_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})

    for t in trades:
        pnl = t.get("pnl_usdt", 0)
        sym = t.get("symbol", "?").replace("/USDT:USDT", "")
        strat = t.get("strategy", "") or ""
        if not strat or strat in ("unknown", "synced"):
            strat = "pre-tracking"
        reason = t.get("reason", "unknown")
        side = t.get("side", "?").upper()
        closed_at = t.get("closed_at", 0)
        hour = datetime.fromtimestamp(closed_at).strftime("%H:00") if closed_at > 0 else "??"
        is_win = pnl > 0

        for key, bucket in [(sym, pair_stats), (strat, strat_stats), (reason, exit_stats), (side, side_stats), (hour, hourly_stats)]:
            bucket[key]["trades"] += 1
            bucket[key]["pnl"] += pnl
            if is_win:
                bucket[key]["wins"] += 1
            else:
                bucket[key]["losses"] += 1

    def _render_breakdown(title, stats_dict, sort_by="pnl"):
        items = sorted(stats_dict.items(), key=lambda x: x[1][sort_by], reverse=True)
        rows = ""
        for name, s in items:
            wr = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
            pnl_cls = "positive" if s["pnl"] >= 0 else "negative"
            wr_cls = "positive" if wr >= 50 else "negative"
            rows += f'''<tr>
                <td class="pair-cell">{escape(str(name))}</td>
                <td style="text-align:center">{s["trades"]}</td>
                <td style="text-align:center">{s["wins"]}</td>
                <td style="text-align:center">{s["losses"]}</td>
                <td class="{wr_cls}" style="text-align:center;font-weight:600">{wr:.0f}%</td>
                <td class="{pnl_cls}" style="text-align:right;font-weight:600;font-family:'JetBrains Mono',monospace">${s["pnl"]:+.2f}</td>
            </tr>'''
        return f'''<div class="audit-section">
            <h3>{title}</h3>
            <div class="table-wrap"><table>
                <thead><tr><th>{title.split(" ")[-1]}</th><th style="text-align:center">Trades</th><th style="text-align:center">W</th><th style="text-align:center">L</th><th style="text-align:center">WR%</th><th style="text-align:right">PnL</th></tr></thead>
                <tbody>{rows}</tbody>
            </table></div>
        </div>'''

    # Full trade log (all trades, newest first)
    all_rows = ""
    for i, t in enumerate(reversed(trades)):
        pnl = t.get("pnl_usdt", 0)
        pct = t.get("pnl_pct", 0)
        cls = "win" if pnl > 0 else "loss"
        sym = escape(t.get("symbol", "?").replace("/USDT:USDT", ""))
        side = escape(t.get("side", "?").upper())
        reason = escape(t.get("reason", "?"))
        raw_strat = t.get("strategy", "") or ""
        strat = escape(raw_strat if raw_strat and raw_strat not in ("unknown", "synced") else "pre-tracking")
        side_cls = "side-long" if side == "LONG" else "side-short"
        closed_at = t.get("closed_at", 0)
        opened_at = t.get("opened_at", 0)
        time_str = datetime.fromtimestamp(closed_at).strftime("%m/%d %I:%M%p").lower() if closed_at > 0 else "--"
        duration = ""
        if closed_at > 0 and opened_at > 0:
            dur_min = (closed_at - opened_at) / 60
            if dur_min >= 60:
                duration = f"{dur_min/60:.1f}h"
            else:
                duration = f"{dur_min:.0f}m"
        entry = t.get("entry_price", 0)
        entry_str = f"{entry:.4f}" if entry > 0 else "--"
        # Estimated fees: 0.06% taker per side × 2 sides × notional (margin × 10x leverage)
        margin_val = t.get("margin", 0)
        fee_est = margin_val * 10 * 0.0006 * 2 if margin_val > 0 else 0
        # Version model name based on trade index (0-indexed)
        trade_idx = len(trades) - i - 1  # 0-indexed position in original list
        trade_num = trade_idx + 1  # 1-indexed for display
        if trade_idx <= 18:
            version = "Genesis"
        elif trade_idx <= 68:
            version = "Patch"
        elif trade_idx <= 80:
            version = "Filter"
        elif trade_idx <= 105:
            version = "Razor"
        elif trade_idx <= 156:
            version = "Razor v2.1"
        else:
            version = "Sentinel"
        ver_colors = {
            "Genesis": "#888", "Patch": "#4a9eff", "Filter": "#2ecc71",
            "Razor": "#e74c3c", "Razor v2.1": "#f39c12", "Sentinel": "#9b59b6",
        }
        ver_color = ver_colors.get(version, "#888")

        all_rows += f'''<tr class="{cls}">
            <td>{trade_num}</td>
            <td style="color:{ver_color};font-size:0.8em;font-weight:600">{version}</td>
            <td><span class="side-badge {side_cls}">{side}</span></td>
            <td class="pair-cell">{sym}</td>
            <td class="pnl-cell">{pnl:+.2f}</td>
            <td class="pnl-cell">{pct:+.1f}%</td>
            <td style="color:var(--negative);font-size:0.85em">-${fee_est:.2f}</td>
            <td class="reason-cell">{reason}</td>
            <td style="font-size:0.85em;color:var(--text-dim)">{strat}</td>
            <td class="time-cell">{duration}</td>
            <td class="time-cell">{time_str}</td>
        </tr>'''

    exit_definitions = '''<div class="audit-section">
        <h3>Exit Types</h3>
        <div style="font-size:0.82em;line-height:1.7;color:var(--text-secondary)">
            <div style="margin-bottom:6px"><span style="color:var(--positive);font-weight:600">early_exit</span> — Momentum reversal while in profit (ROI &ge; 3%). Needs 2-of-3 reversal signals, or 1-of-3 at 8%+ ROI.</div>
            <div style="margin-bottom:6px"><span style="color:var(--accent-blue);font-weight:600">flat_exit</span> — Stagnant trade after 4 hrs. Exits if ROI is between -4% and +4%. Catches trades going nowhere.</div>
            <div style="margin-bottom:6px"><span style="color:var(--accent-cyan);font-weight:600">exchange_close</span> — SL or TP triggered on the exchange itself. Bot detects position is gone and records it.</div>
            <div style="margin-bottom:6px"><span style="color:var(--warning);font-weight:600">stop_loss</span> — Software SL fallback. Trailing stop or breakeven SL triggered by the bot&#39;s own price checks.</div>
            <div style="margin-bottom:6px"><span style="color:var(--positive);font-weight:600">take_profit</span> — Software TP triggered by bot. Rarely fires — early_exit usually catches profits first.</div>
            <div style="margin-bottom:6px"><span style="color:var(--negative);font-weight:600">time_exit</span> — Soft clock limit (15-45 min by strategy). Exits if losing at soft limit. Deep losses (&lt; -6%) cut at half soft limit.</div>
            <div><span style="color:var(--negative);font-weight:600">hard_time_exit</span> — Hard clock limit (45-120 min). Unconditional exit unless ROI &ge; 5% (then extended 50%).</div>
        </div>
    </div>'''

    return f'''
    <div class="audit-grid">
        {_render_breakdown("By Pair", pair_stats)}
        {_render_breakdown("By Strategy", strat_stats)}
        {_render_breakdown("By Exit Reason", exit_stats)}
        {_render_breakdown("By Side", side_stats)}
        {_render_breakdown("By Hour", hourly_stats, sort_by="trades")}
        {exit_definitions}
    </div>
    <div class="glass-card audit-log" style="margin-top:12px">
        <h2>Full Trade Log ({len(trades)} trades)</h2>
        <div class="table-wrap" style="max-height:500px;overflow-y:auto">
        <table>
            <thead><tr><th>#</th><th>Model</th><th>Side</th><th>Pair</th><th>PnL</th><th>ROI</th><th>Fees</th><th>Exit</th><th>Strategy</th><th>Duration</th><th>Closed</th></tr></thead>
            <tbody>{all_rows}</tbody>
        </table>
        </div>
    </div>'''


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "total_pnl": 0, "total_fees": 0, "real_pnl": 0,
                "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
                "best": 0, "worst": 0, "max_dd": 0, "max_dd_pct": 0}
    wins = [t for t in trades if t.get("pnl_usdt", 0) > 0]
    losses = [t for t in trades if t.get("pnl_usdt", 0) <= 0]
    total_pnl = sum(t.get("pnl_usdt", 0) for t in trades)
    gp = sum(t["pnl_usdt"] for t in wins) if wins else 0
    gl = abs(sum(t["pnl_usdt"] for t in losses)) if losses else 0
    best = max(t.get("pnl_usdt", 0) for t in trades)
    worst = min(t.get("pnl_usdt", 0) for t in trades)

    # Max drawdown from cumulative curve
    cum = 0
    peak = 0
    max_dd = 0
    max_dd_pct = 0
    for t in trades:
        cum += t.get("pnl_usdt", 0)
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * 100) if peak > 0 else 0

    # Estimated fees: margin × leverage × 0.06% taker × 2 sides per trade
    total_fees = sum(t.get("margin", 0) * 10 * 0.0006 * 2 for t in trades)
    real_pnl = total_pnl - total_fees

    return {
        "total": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "total_pnl": total_pnl, "total_fees": total_fees, "real_pnl": real_pnl,
        "avg_win": gp / len(wins) if wins else 0,
        "avg_loss": gl / len(losses) if losses else 0,
        "profit_factor": gp / gl if gl > 0 else float('inf'),
        "best": best, "worst": worst, "max_dd": max_dd, "max_dd_pct": max_dd_pct,
    }


# ── Chart generation ────────────────────────────────────────────────────
def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor="#1e1e2e", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _make_cumulative_pnl(trades: list[dict]) -> bytes:
    if not trades:
        return b""
    pnls = [t.get("pnl_usdt", 0) for t in trades]
    cum = []
    r = 0
    for p in pnls:
        r += p
        cum.append(r)
    x = list(range(1, len(cum) + 1))

    fig, ax = plt.subplots(figsize=(9, 4), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")
    ax.plot(x, cum, color="#89b4fa", linewidth=2, marker="o", markersize=3)
    ax.fill_between(x, cum, 0, where=[c >= 0 for c in cum], color="#a6e3a1", alpha=0.15)
    ax.fill_between(x, cum, 0, where=[c < 0 for c in cum], color="#f38ba8", alpha=0.15)
    ax.axhline(y=0, color="#585b70", linestyle="--", alpha=0.5)
    ax.set_xlabel("Trade #", color="#cdd6f4")
    ax.set_ylabel("Cumulative PnL (USDT)", color="#cdd6f4")
    ax.set_title("Cumulative PnL", color="#cdd6f4", fontsize=13)
    ax.tick_params(colors="#a6adc8")
    ax.grid(True, alpha=0.15, color="#585b70")
    for spine in ax.spines.values():
        spine.set_color("#585b70")
    return _fig_to_png(fig)


def _make_pnl_by_pair(trades: list[dict]) -> bytes:
    if not trades:
        return b""
    pair_pnl = defaultdict(float)
    for t in trades:
        sym = t.get("symbol", "?").replace("/USDT:USDT", "")
        pair_pnl[sym] += t.get("pnl_usdt", 0)
    sorted_p = sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)
    syms = [p[0] for p in sorted_p]
    vals = [p[1] for p in sorted_p]
    colors = ["#a6e3a1" if v >= 0 else "#f38ba8" for v in vals]

    fig, ax = plt.subplots(figsize=(9, 4), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")
    ax.bar(syms, vals, color=colors, alpha=0.85, edgecolor="#585b70", linewidth=0.5)
    ax.axhline(y=0, color="#585b70", linewidth=0.8)
    ax.set_ylabel("PnL (USDT)", color="#cdd6f4")
    ax.set_title("PnL by Pair", color="#cdd6f4", fontsize=13)
    ax.tick_params(colors="#a6adc8")
    ax.grid(True, alpha=0.15, color="#585b70", axis="y")
    plt.xticks(rotation=45, ha="right")
    for spine in ax.spines.values():
        spine.set_color("#585b70")
    return _fig_to_png(fig)


def _make_pnl_by_reason(trades: list[dict]) -> bytes:
    if not trades:
        return b""
    reason_pnl = defaultdict(float)
    reason_count = defaultdict(int)
    for t in trades:
        r = t.get("reason", "unknown")
        reason_pnl[r] += t.get("pnl_usdt", 0)
        reason_count[r] += 1
    reasons = list(reason_pnl.keys())
    vals = [reason_pnl[r] for r in reasons]
    counts = [reason_count[r] for r in reasons]
    colors = ["#a6e3a1" if v >= 0 else "#f38ba8" for v in vals]

    fig, ax = plt.subplots(figsize=(7, 4), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")
    bars = ax.bar(reasons, vals, color=colors, alpha=0.85, edgecolor="#585b70", linewidth=0.5)
    for bar, c in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{c}t", ha="center", va="bottom", fontsize=8, color="#a6adc8")
    ax.axhline(y=0, color="#585b70", linewidth=0.8)
    ax.set_ylabel("PnL (USDT)", color="#cdd6f4")
    ax.set_title("PnL by Exit Reason", color="#cdd6f4", fontsize=13)
    ax.tick_params(colors="#a6adc8")
    ax.grid(True, alpha=0.15, color="#585b70", axis="y")
    for spine in ax.spines.values():
        spine.set_color("#585b70")
    return _fig_to_png(fig)


def _make_trade_pnl(trades: list[dict]) -> bytes:
    if not trades:
        return b""
    pnls = [t.get("pnl_usdt", 0) for t in trades]
    colors = ["#a6e3a1" if p >= 0 else "#f38ba8" for p in pnls]

    fig, ax = plt.subplots(figsize=(9, 4), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")
    ax.bar(range(len(pnls)), pnls, color=colors, alpha=0.85, edgecolor="#585b70", linewidth=0.3)
    ax.axhline(y=0, color="#585b70", linewidth=0.8)
    ax.set_xlabel("Trade #", color="#cdd6f4")
    ax.set_ylabel("PnL (USDT)", color="#cdd6f4")
    ax.set_title("Individual Trade PnL", color="#cdd6f4", fontsize=13)
    ax.tick_params(colors="#a6adc8")
    ax.grid(True, alpha=0.15, color="#585b70", axis="y")
    for spine in ax.spines.values():
        spine.set_color("#585b70")
    return _fig_to_png(fig)


def refresh_charts():
    """Regenerate all charts and cache as PNG bytes."""
    state = read_state()
    trades = state.get("closed_trades", [])
    charts = {}
    if trades:
        charts["cumulative_pnl"] = _make_cumulative_pnl(trades)
        charts["pnl_by_pair"] = _make_pnl_by_pair(trades)
        charts["pnl_by_reason"] = _make_pnl_by_reason(trades)
        charts["trade_pnl"] = _make_trade_pnl(trades)
    with _chart_lock:
        _chart_cache.update(charts)


def chart_thread_loop():
    """Background thread that periodically refreshes charts."""
    while True:
        try:
            refresh_charts()
        except Exception as e:
            print(f"[CHART] Error refreshing charts: {e}")
        time.sleep(CHART_INTERVAL)


def _build_watchlist_html(wl: dict) -> str:
    """Render watchlist as a grid of coin tiles with status dots."""
    base = wl["base_pairs"]
    scanner = {s["symbol"]: s for s in wl["scanner_pairs"]}
    open_syms = wl["open_symbols"]

    # Merge: all unique symbols, open first, then scanner, then base
    seen = set()
    ordered = []
    # Open positions first
    for sym in sorted(open_syms):
        if sym not in seen:
            ordered.append(sym)
            seen.add(sym)
    # Scanner pairs next
    for sym in scanner:
        if sym not in seen:
            ordered.append(sym)
            seen.add(sym)
    # Base pairs last
    for sym in base:
        if sym not in seen:
            ordered.append(sym)
            seen.add(sym)

    if not ordered:
        return '<div style="color:#6c7086;font-size:0.85em">No pairs detected yet</div>'

    html = '<div class="watchlist-grid">'
    for sym in ordered:
        short = escape(sym.replace("/USDT:USDT", ""))
        is_open = sym in open_syms
        is_scanner = sym in scanner

        if is_open:
            dot_cls = "dot-open"
            status = "OPEN"
        elif is_scanner:
            dot_cls = "dot-scanner"
            status = "Scanner"
        else:
            dot_cls = "dot-base"
            status = "Base"

        score_html = ""
        meta_parts = [status]
        if is_scanner and sym in scanner:
            s = scanner[sym]
            score_html = f'<span class="wl-score">{s["score"]:.1f}</span>'
            meta_parts.append(f'{s["change_24h"]:+.1f}% {s["trend"]}')

        html += f'''<div class="wl-item">
            <span class="dot {dot_cls}"></span><span class="sym">{short}</span>{score_html}
            <div class="meta">{" &middot; ".join(meta_parts)}</div>
        </div>'''
    html += '</div>'
    return html


# ── HTML rendering ───────────────────────────────────────────────────────
def build_content() -> str:
    """Build just the inner content HTML (no head/style/script shell)."""
    state = read_state()
    trades = state.get("closed_trades", [])
    stats = compute_stats(trades)
    lines = tail_log(500)
    cycle = parse_latest_cycle(lines)
    regime = parse_regime_status(lines)
    activity = get_recent_activity(lines, n=15)
    # Watchlist needs more history to capture position opens/closes and scanner updates
    wl_lines = tail_log(3000)
    watchlist = parse_watchlist(wl_lines)
    now = datetime.now().strftime("%I:%M:%S %p")
    date_str = datetime.now().strftime("%b %d, %Y")

    audit_html = build_audit_table(trades)

    # Activity feed
    activity_html = ""
    for line in activity:
        trimmed = escape(line[:140] + "..." if len(line) > 140 else line)
        # Color-code by type
        line_cls = "act-entry" if "ENTRY:" in line else "act-exit" if "closed:" in line else "act-system" if any(k in line for k in ["REGIME", "DRAWDOWN", "SCANNER"]) else "act-default"
        activity_html += f"<div class='activity-line {line_cls}'>{trimmed}</div>"

    # Chart availability
    with _chart_lock:
        has_charts = bool(_chart_cache)

    chart_section = ""
    if has_charts:
        chart_section = """
        <div class="charts-grid">
            <div class="chart-box"><img src="/chart/cumulative_pnl" alt="Cumulative PnL"></div>
            <div class="chart-box"><img src="/chart/pnl_by_pair" alt="PnL by Pair"></div>
            <div class="chart-box"><img src="/chart/pnl_by_reason" alt="PnL by Reason"></div>
            <div class="chart-box"><img src="/chart/trade_pnl" alt="Trade PnL"></div>
        </div>"""
    else:
        chart_section = '<div class="glass-card" style="text-align:center;padding:40px"><p style="color:#7e8aa0">No trades yet — charts appear after first closed trade</p></div>'

    # Daily stats
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_trades = [t for t in trades if t.get("closed_at", 0) >= today_start]
    has_daily = any(t.get("closed_at", 0) > 0 for t in trades)
    daily_pnl = sum(t.get("pnl_usdt", 0) for t in today_trades)
    daily_fees = sum(t.get("margin", 0) * 10 * 0.0006 * 2 for t in today_trades)
    daily_real_pnl = daily_pnl - daily_fees
    daily_count = len(today_trades)
    daily_wins = sum(1 for t in today_trades if t.get("pnl_usdt", 0) > 0)
    daily_wr = (daily_wins / daily_count * 100) if daily_count > 0 else 0
    current_balance = state.get("peak_balance", 0)
    daily_pct = (daily_pnl / (current_balance - daily_pnl) * 100) if has_daily and (current_balance - daily_pnl) > 0 else 0

    # Current drawdown from peak
    peak_bal = state.get("peak_balance", 0)
    # Estimate current balance: peak - max_dd + recent trades
    cumulative = 0
    running_peak = 0
    for t in trades:
        cumulative += t.get("pnl_usdt", 0)
        running_peak = max(running_peak, cumulative)
    current_dd = running_peak - cumulative  # current drawdown in $
    current_dd_pct = (current_dd / peak_bal * 100) if peak_bal > 0 else 0

    pf = stats['profit_factor']
    pf_str = f"{pf:.2f}" if pf != float('inf') else "---"
    real_pnl_cls = "positive" if stats['real_pnl'] >= 0 else "negative"
    daily_real_cls = "positive" if daily_real_pnl >= 0 else "negative"

    # Regime status badge
    regime_cls = "regime-normal" if regime == "Normal" else "regime-warn" if "pause" in regime.lower() or "halt" in regime.lower() else "regime-info"

    # Win rate color
    wr_cls = "positive" if stats['win_rate'] >= 50 else "negative"
    daily_wr_cls = "positive" if daily_wr >= 50 else "negative"
    pnl_cls = "positive" if stats['total_pnl'] >= 0 else "negative"
    daily_pnl_cls = "positive" if daily_pnl >= 0 else "negative"

    return f"""
<!-- Top bar -->
<div class="top-bar">
    <div class="top-left">
        <div class="logo">PHMEX-S</div>
        <div class="logo-sub">Trading Desk Data</div>
    </div>
    <div class="top-center">
        <span class="regime-badge {regime_cls}">{escape(regime)}</span>
    </div>
    <div class="top-right">
        <div class="clock">{now}</div>
        <div class="date">{date_str} &middot; {escape(cycle)}</div>
    </div>
</div>

<!-- Hero metrics -->
<div class="hero-row">
    <div class="hero-card">
        <div class="hero-label">Total PnL</div>
        <div class="hero-value {pnl_cls}">${stats['total_pnl']:+.2f}</div>
    </div>
    <div class="hero-card">
        <div class="hero-label">Win Rate</div>
        <div class="hero-value {wr_cls}">{stats['win_rate']:.1f}%</div>
        <div class="hero-sub">{stats['wins']}W / {stats['losses']}L of {stats['total']}</div>
    </div>
    <div class="hero-card">
        <div class="hero-label">Today</div>
        <div class="hero-value {daily_pnl_cls}">{f'${daily_pnl:+.2f}' if has_daily else 'N/A'}</div>
        <div class="hero-sub">{f'{daily_count} trades &middot; {daily_wr:.0f}% WR' if has_daily else 'No trades yet'}</div>
    </div>
    <div class="hero-card">
        <div class="hero-label">Peak Balance</div>
        <div class="hero-value">${state.get('peak_balance',0):.2f}</div>
    </div>
    <div class="hero-card">
        <div class="hero-label">Profit Factor</div>
        <div class="hero-value">{pf_str}</div>
    </div>
    <div class="hero-card">
        <div class="hero-label">Drawdown</div>
        <div class="hero-value negative">${current_dd:.2f}</div>
        <div class="hero-sub">{current_dd_pct:.1f}% from peak</div>
    </div>
    <div class="hero-card">
        <div class="hero-label">Est. Fees Paid</div>
        <div class="hero-value negative">${stats['total_fees']:.2f}</div>
        <div class="hero-sub">~${stats['total_fees']/max(stats['total'],1):.2f}/trade &middot; today ${daily_fees:.2f}</div>
    </div>
</div>

<!-- Draggable grid -->
<div class="dash-grid" id="dash-grid">
    <div class="glass-card dash-item" data-id="watchlist">
        <h2 class="drag-handle">Watchlist</h2>
        {_build_watchlist_html(watchlist)}
    </div>
    <div class="glass-card dash-item" data-id="performance">
        <h2 class="drag-handle">Performance</h2>
        <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-value {wr_cls}">{stats['win_rate']:.1f}%</span></div>
        <div class="stat-row"><span class="stat-label">Avg Win</span><span class="stat-value positive">${stats['avg_win']:.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Avg Loss</span><span class="stat-value negative">${stats['avg_loss']:.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Best Trade</span><span class="stat-value positive">${stats['best']:+.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Worst Trade</span><span class="stat-value negative">${stats['worst']:+.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Max DD %</span><span class="stat-value negative">{stats['max_dd_pct']:.1f}%</span></div>
        <div class="stat-row"><span class="stat-label">Max Drawdown</span><span class="stat-value negative">${stats['max_dd']:.2f}</span></div>
        <div class="stat-row"><span class="stat-label">Current DD %</span><span class="stat-value {"negative" if current_dd > 0 else "positive"}">{f'{current_dd_pct:.1f}%' if current_dd > 0 else '0.0%'}</span></div>
        <div class="stat-row"><span class="stat-label">Current DD</span><span class="stat-value {"negative" if current_dd > 0 else "positive"}">{f'${current_dd:.2f}' if current_dd > 0 else '$0.00'}</span></div>
    </div>
    <div class="glass-card dash-item" data-id="today">
        <h2 class="drag-handle">Today&apos;s Session</h2>
        <div class="stat-row"><span class="stat-label">Trades</span><span class="stat-value">{daily_count if has_daily else 'N/A'}</span></div>
        <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-value {daily_wr_cls}">{f'{daily_wr:.0f}%' if has_daily else 'N/A'}</span></div>
        <div class="stat-row"><span class="stat-label">PnL</span><span class="stat-value {daily_pnl_cls}">{f'${daily_pnl:+.2f}' if has_daily else 'N/A'}</span></div>
        <div class="stat-row"><span class="stat-label">Daily %</span><span class="stat-value {daily_pnl_cls}">{f'{daily_pct:+.1f}%' if has_daily else 'N/A'}</span></div>
        <div class="stat-row"><span class="stat-label">DD %</span><span class="stat-value {"negative" if current_dd > 0 else "positive"}">{f'{current_dd_pct:.1f}%' if current_dd > 0 else '0.0%'}</span></div>
        <div class="stat-row"><span class="stat-label">Drawdown</span><span class="stat-value {"negative" if current_dd > 0 else "positive"}">{f'${current_dd:.2f}' if current_dd > 0 else '$0.00'}</span></div>
        <div class="stat-row"><span class="stat-label">W / L</span><span class="stat-value">{f'{daily_wins} / {daily_count - daily_wins}' if has_daily else 'N/A'}</span></div>
    </div>
    <div class="glass-card dash-item" data-id="charts">
        <h2 class="drag-handle">Charts</h2>
        {chart_section}
    </div>
    <div class="glass-card dash-item" data-id="activity">
        <h2 class="drag-handle">Activity Feed</h2>
        <div class="activity-legend">
            <span class="legend-dot" style="color:var(--positive)">&#9679; Entry</span>
            <span class="legend-dot" style="color:var(--accent-blue)">&#9679; Exit</span>
            <span class="legend-dot" style="color:var(--warning)">&#9679; System</span>
        </div>
        <div class="activity-scroll">
        {activity_html if activity_html else '<div class="activity-line act-default">No recent activity</div>'}
        </div>
    </div>
    <div class="glass-card dash-item" data-id="audit">
        <h2 class="drag-handle">Performance Audit</h2>
        {audit_html}
    </div>
</div>

<div class="footer">
    Auto-refresh 20s &middot; Charts {CHART_INTERVAL}s &middot; Read-only &middot; Zero API calls
</div>"""


def build_html() -> str:
    """Full HTML page with shell + content."""
    content = build_content()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PHMEX_S Trading Desk Data</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{ margin:0; padding:0; box-sizing:border-box; }}

:root {{
    --bg-deep: #0a0e1a;
    --bg-mid: #111827;
    --glass-bg: rgba(17, 24, 39, 0.65);
    --glass-border: rgba(100, 140, 200, 0.12);
    --glass-highlight: rgba(120, 160, 220, 0.06);
    --text-primary: #e2e8f0;
    --text-secondary: #7e8aa0;
    --text-dim: #4a5568;
    --accent-blue: #60a5fa;
    --accent-cyan: #22d3ee;
    --accent-teal: #2dd4bf;
    --positive: #34d399;
    --negative: #f87171;
    --warning: #fbbf24;
    --border-subtle: rgba(100, 140, 200, 0.08);
}}

body {{
    background: var(--bg-deep);
    color: var(--text-primary);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
}}

/* SF skyline background */
body::before {{
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        /* Sky gradient — golden hour over the bay */
        linear-gradient(180deg,
            #0a0e1a 0%,
            #0f172a 25%,
            #1a1f3a 50%,
            #1e2744 70%,
            #1a2640 85%,
            #162035 100%
        );
    z-index: -3;
}}

/* Skyline silhouette */
body::after {{
    content: '';
    position: fixed;
    bottom: 0; left: 0; right: 0;
    height: 280px;
    background: linear-gradient(0deg, rgba(10,14,26,0.95) 0%, transparent 100%);
    z-index: -1;
    pointer-events: none;
}}

/* Ambient glow — city lights reflecting on bay */
.skyline-glow {{
    position: fixed;
    bottom: 0; left: 0; right: 0;
    height: 200px;
    background:
        radial-gradient(ellipse 60% 40% at 30% 100%, rgba(96,165,250,0.04) 0%, transparent 70%),
        radial-gradient(ellipse 50% 35% at 70% 100%, rgba(34,211,238,0.03) 0%, transparent 70%);
    z-index: -2;
    pointer-events: none;
}}

#content {{
    max-width: 1600px;
    margin: 0 auto;
    padding: 12px 20px 30px;
    position: relative;
}}

/* ── Top bar ── */
.top-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0 16px;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 20px;
}}
.top-left {{ display: flex; align-items: baseline; gap: 10px; }}
.logo {{
    font-size: 1.3em;
    font-weight: 700;
    letter-spacing: 3px;
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.logo-sub {{
    font-size: 0.65em;
    font-weight: 500;
    letter-spacing: 4px;
    color: var(--text-dim);
    text-transform: uppercase;
}}
.top-center {{ text-align: center; }}
.top-right {{ text-align: right; }}
.clock {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.4em;
    font-weight: 500;
    color: var(--text-primary);
    letter-spacing: 1px;
}}
.date {{
    font-size: 0.75em;
    color: var(--text-secondary);
    margin-top: 2px;
}}

/* Regime badge */
.regime-badge {{
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.75em;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
.regime-normal {{
    background: rgba(52,211,153,0.12);
    color: var(--positive);
    border: 1px solid rgba(52,211,153,0.2);
}}
.regime-warn {{
    background: rgba(251,191,36,0.12);
    color: var(--warning);
    border: 1px solid rgba(251,191,36,0.2);
    animation: pulse-warn 2s ease-in-out infinite;
}}
.regime-info {{
    background: rgba(96,165,250,0.12);
    color: var(--accent-blue);
    border: 1px solid rgba(96,165,250,0.2);
}}
@keyframes pulse-warn {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.7; }}
}}

/* ── Hero metrics row ── */
.hero-row {{
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
    margin-bottom: 20px;
}}
.hero-card {{
    background: var(--glass-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 16px 18px;
    text-align: center;
    transition: border-color 0.3s;
}}
.hero-card:hover {{
    border-color: rgba(96,165,250,0.25);
}}
.hero-label {{
    font-size: 0.7em;
    font-weight: 500;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 6px;
}}
.hero-value {{
    font-size: 1.6em;
    font-weight: 700;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
}}
.hero-sub {{
    font-size: 0.72em;
    color: var(--text-dim);
    margin-top: 4px;
}}

/* ── Draggable grid ── */
.dash-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
}}

/* ── Glass card ── */
.glass-card {{
    background: var(--glass-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 16px 18px;
    transition: border-color 0.3s, box-shadow 0.2s;
}}
.glass-card:hover {{
    border-color: rgba(96,165,250,0.2);
}}

/* Resizable + draggable cards */
.dash-item {{
    resize: both;
    overflow: auto;
    min-width: 280px;
    min-height: 120px;
    scrollbar-width: thin;
    scrollbar-color: rgba(96,165,250,0.15) transparent;
    position: relative;
}}
.dash-item::-webkit-scrollbar {{ width: 5px; height: 5px; }}
.dash-item::-webkit-scrollbar-thumb {{ background: rgba(96,165,250,0.2); border-radius: 3px; }}
.dash-item::-webkit-resizer {{ display: block; }}

/* Drag handle */
.drag-handle {{
    cursor: grab;
    user-select: none;
    -webkit-user-select: none;
    position: relative;
    padding-right: 20px;
}}
.drag-handle:active {{ cursor: grabbing; }}
.drag-handle::after {{
    content: '\u2630';
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.9em;
    color: var(--text-dim);
    opacity: 0.4;
}}
.drag-handle:hover::after {{ opacity: 0.8; }}

/* Dragging state */
.dash-item.dragging {{
    opacity: 0.5;
    border: 2px dashed var(--accent-blue);
}}
.dash-item.drag-over {{
    border-color: var(--accent-cyan);
    box-shadow: 0 0 12px rgba(34,211,238,0.15);
}}

.glass-card h2 {{
    font-size: 0.78em;
    font-weight: 600;
    color: var(--accent-blue);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-subtle);
}}

/* ── Stats ── */
.stat-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    font-size: 0.85em;
    border-bottom: 1px solid rgba(100,140,200,0.04);
}}
.stat-row:last-child {{ border-bottom: none; }}
.stat-label {{ color: var(--text-secondary); font-weight: 400; }}
.stat-value {{
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.95em;
}}
.positive {{ color: var(--positive); }}
.negative {{ color: var(--negative); }}

/* ── Table ── */
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; }}
thead th {{
    text-align: left;
    color: var(--text-dim);
    font-weight: 500;
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-subtle);
}}
tbody td {{
    padding: 8px 10px;
    border-bottom: 1px solid rgba(100,140,200,0.04);
    color: var(--text-secondary);
}}
tbody tr:hover {{ background: rgba(96,165,250,0.04); }}
tr.win .pnl-cell {{ color: var(--positive); font-weight: 600; }}
tr.loss .pnl-cell {{ color: var(--negative); font-weight: 600; }}
.pair-cell {{ color: var(--text-primary); font-weight: 500; }}
.reason-cell {{ font-size: 0.9em; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.time-cell {{ font-family: 'JetBrains Mono', monospace; font-size: 0.9em; color: var(--text-dim); }}
.empty-row {{ text-align: center; color: var(--text-dim); padding: 20px; }}

/* Side badge */
.side-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
.side-long {{
    background: rgba(52,211,153,0.12);
    color: var(--positive);
}}
.side-short {{
    background: rgba(248,113,113,0.12);
    color: var(--negative);
}}

/* ── Charts ── */
.charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 12px;
}}
.chart-box {{
    background: var(--glass-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 10px;
    text-align: center;
}}
.chart-box img {{
    width: 100%;
    border-radius: 8px;
    opacity: 0.95;
}}

/* ── Watchlist ── */
.watchlist-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 6px;
}}
.wl-item {{
    background: rgba(30,40,60,0.6);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 0.8em;
    transition: border-color 0.2s, background 0.2s;
}}
.wl-item:hover {{
    border-color: rgba(96,165,250,0.3);
    background: rgba(40,55,80,0.6);
}}
.wl-item .sym {{
    font-weight: 600;
    color: var(--text-primary);
    font-size: 0.95em;
}}
.wl-item .meta {{
    color: var(--text-dim);
    font-size: 0.75em;
    margin-top: 3px;
}}
.wl-item .dot {{
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
}}
.dot-open {{
    background: var(--positive);
    box-shadow: 0 0 6px rgba(52,211,153,0.5);
}}
.dot-scanner {{
    background: var(--accent-cyan);
    box-shadow: 0 0 6px rgba(34,211,238,0.4);
}}
.dot-base {{ background: var(--text-dim); }}
.wl-score {{
    float: right;
    color: var(--warning);
    font-weight: 600;
    font-size: 0.8em;
    font-family: 'JetBrains Mono', monospace;
}}

/* ── Activity feed ── */
.activity-card {{ max-height: 500px; }}
.activity-scroll {{
    max-height: 420px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(96,165,250,0.2) transparent;
}}
.activity-scroll::-webkit-scrollbar {{ width: 4px; }}
.activity-scroll::-webkit-scrollbar-thumb {{ background: rgba(96,165,250,0.2); border-radius: 2px; }}
.activity-line {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68em;
    padding: 4px 6px;
    border-radius: 4px;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: background 0.2s;
}}
.activity-line:hover {{
    background: rgba(96,165,250,0.06);
    white-space: normal;
    word-break: break-all;
}}
.act-entry {{ color: var(--positive); }}
.act-exit {{ color: var(--accent-blue); }}
.act-system {{ color: var(--warning); }}
.act-default {{ color: var(--text-dim); }}
.activity-legend {{ display:flex; gap:12px; padding:4px 0 8px; font-size:0.75rem; }}
.legend-dot {{ display:flex; align-items:center; gap:4px; }}

/* ── Audit ── */
.audit-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin-bottom: 8px;
}}
.audit-section {{
    background: rgba(20,30,50,0.5);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 12px 14px;
}}
.audit-section h3 {{
    font-size: 0.72em;
    font-weight: 600;
    color: var(--accent-cyan);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
}}
.audit-section table {{ font-size: 0.8em; }}
.audit-section thead th {{
    font-size: 0.82em;
    padding: 5px 6px;
}}
.audit-section tbody td {{
    padding: 4px 6px;
    font-size: 0.92em;
}}
.audit-log .table-wrap {{
    scrollbar-width: thin;
    scrollbar-color: rgba(96,165,250,0.2) transparent;
}}
.audit-log .table-wrap::-webkit-scrollbar {{ width: 4px; }}
.audit-log .table-wrap::-webkit-scrollbar-thumb {{ background: rgba(96,165,250,0.2); border-radius: 2px; }}

/* ── Footer ── */
.footer {{
    text-align: center;
    color: var(--text-dim);
    font-size: 0.7em;
    letter-spacing: 0.5px;
    padding: 16px 0 8px;
}}

/* ── Responsive ── */
@media (max-width: 1200px) {{
    .dash-grid {{ grid-template-columns: 1fr; }}
    .hero-row {{ grid-template-columns: repeat(3, 1fr); }}
}}
@media (max-width: 768px) {{
    .hero-row {{ grid-template-columns: repeat(2, 1fr); }}
    .top-bar {{ flex-direction: column; gap: 8px; text-align: center; }}
    .top-left {{ justify-content: center; }}
    #content {{ padding: 8px 12px 20px; }}
}}
</style>
</head>
<body>
<div class="skyline-glow"></div>
<div id="content">
{content}
</div>
<script>
(function() {{
  const STORAGE_KEY = 'phmex_dash_layout';

  /* ── Save/Load layout state ── */
  function saveLayout() {{
    const grid = document.getElementById('dash-grid');
    if (!grid) return;
    const state = {{}};
    grid.querySelectorAll('.dash-item').forEach((el, i) => {{
      const id = el.dataset.id;
      if (!id) return;
      state[id] = {{ order: i, w: el.style.width || '', h: el.style.height || '' }};
    }});
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }}

  function applyLayout() {{
    const grid = document.getElementById('dash-grid');
    if (!grid) return;
    let state;
    try {{ state = JSON.parse(localStorage.getItem(STORAGE_KEY)); }} catch(e) {{ return; }}
    if (!state) return;

    const items = Array.from(grid.querySelectorAll('.dash-item'));
    /* Apply saved sizes */
    items.forEach(el => {{
      const s = state[el.dataset.id];
      if (s) {{
        if (s.w) el.style.width = s.w;
        if (s.h) el.style.height = s.h;
      }}
    }});
    /* Reorder */
    items.sort((a, b) => {{
      const oa = (state[a.dataset.id] || {{}}).order ?? 99;
      const ob = (state[b.dataset.id] || {{}}).order ?? 99;
      return oa - ob;
    }});
    items.forEach(el => grid.appendChild(el));
    initDrag();
  }}

  /* ── Drag and drop ── */
  let dragEl = null;

  function initDrag() {{
    const grid = document.getElementById('dash-grid');
    if (!grid) return;

    grid.querySelectorAll('.dash-item').forEach(item => {{
      item.setAttribute('draggable', 'false');
      const handle = item.querySelector('.drag-handle');
      if (!handle) return;

      handle.addEventListener('mousedown', () => {{
        item.setAttribute('draggable', 'true');
      }});
      handle.addEventListener('mouseup', () => {{
        item.setAttribute('draggable', 'false');
      }});

      item.addEventListener('dragstart', (e) => {{
        dragEl = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.id);
      }});

      item.addEventListener('dragend', () => {{
        item.classList.remove('dragging');
        item.setAttribute('draggable', 'false');
        grid.querySelectorAll('.dash-item').forEach(el => el.classList.remove('drag-over'));
        dragEl = null;
        saveLayout();
      }});

      item.addEventListener('dragover', (e) => {{
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (item !== dragEl) item.classList.add('drag-over');
      }});

      item.addEventListener('dragleave', () => {{
        item.classList.remove('drag-over');
      }});

      item.addEventListener('drop', (e) => {{
        e.preventDefault();
        item.classList.remove('drag-over');
        if (!dragEl || dragEl === item) return;
        const allItems = Array.from(grid.querySelectorAll('.dash-item'));
        const fromIdx = allItems.indexOf(dragEl);
        const toIdx = allItems.indexOf(item);
        if (fromIdx < toIdx) {{
          item.parentNode.insertBefore(dragEl, item.nextSibling);
        }} else {{
          item.parentNode.insertBefore(dragEl, item);
        }}
        saveLayout();
      }});
    }});

    /* Save size on resize (via ResizeObserver) */
    const ro = new ResizeObserver(() => {{ saveLayout(); }});
    grid.querySelectorAll('.dash-item').forEach(el => ro.observe(el));
  }}

  /* ── Auto-refresh ── */
  let scrollY = 0;
  async function refresh() {{
    try {{
      const resp = await fetch('/api/content');
      if (!resp.ok) return;
      const html = await resp.text();
      scrollY = window.scrollY;
      document.getElementById('content').innerHTML = html;
      applyLayout();
      window.scrollTo(0, scrollY);
      document.querySelectorAll('.chart-box img').forEach(img => {{
        const src = img.getAttribute('src').split('?')[0];
        img.src = src + '?t=' + Date.now();
      }});
    }} catch(e) {{}}
  }}
  setInterval(refresh, 20000);

  /* Initial setup */
  applyLayout();
}})();
</script>
</body>
</html>"""


# ── HTTP handler ─────────────────────────────────────────────────────────
class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html = build_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html.encode())))
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == "/api/content":
            html = build_content()
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/chart/"):
            name = self.path[7:]  # strip "/chart/"
            with _chart_lock:
                data = _chart_cache.get(name, b"")
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress access logs


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    # Initial chart render
    print("Generating initial charts...")
    refresh_charts()

    # Start background chart thread
    t = threading.Thread(target=chart_thread_loop, daemon=True, name="chart-refresh")
    t.start()

    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Phmex-S Dashboard running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
