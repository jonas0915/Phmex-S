#!/usr/bin/env python3
"""
Phmex-S HTML Dashboard — read-only web monitor.
Reads trading_state.json and bot.log only. Zero API calls, zero bot imports.

Usage:  python web_dashboard.py
Open:   http://127.0.0.1:8050
"""
import glob as _glob
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

CA_TZ = ZoneInfo("America/Los_Angeles")

def _now_ca():
    return datetime.now(CA_TZ)

def _from_ts(ts):
    return datetime.fromtimestamp(ts, CA_TZ)
from collections import defaultdict
from html import escape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_DIR, "trading_state.json")
PAPER_STATE_FILE = os.path.join(PROJECT_DIR, "trading_state_5m_liq_cascade.json")
NARROW_STATE_FILE = os.path.join(PROJECT_DIR, "trading_state_5m_narrow.json")
NARROW_BLOCKED_FILE = os.path.join(PROJECT_DIR, "trading_state_5m_narrow_blocked.json")
FACTORY_STATE_FILE = os.path.join(PROJECT_DIR, "strategy_factory_state.json")
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "bot.log")
HOST = "127.0.0.1"
PORT = 8050
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# ── Static assets (vendored uPlot — the ONLY files /static/ will serve) ──
STATIC_DIR = os.path.join(PROJECT_DIR, "static")
STATIC_FILES = {
    "uplot.iife.min.js": "application/javascript; charset=utf-8",
    "uplot.min.css": "text/css; charset=utf-8",
}

# ── Watcher-enabled cache (30s TTL — avoids per-poll grep/seek) ──────────
_watcher_cache: dict = {"v": None, "ts": 0.0}

# ── Sentinel-era anchors ─────────────────────────────────────────────────
# Sentinel deployed 2026-04-01 23:01 PT (= 2026-04-02 06:01 UTC), trade #342+
SENTINEL_DEPLOY_TS = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def _gate_stats(log_file: str, max_age_hours: int = 24) -> dict:
    """Parse bot.log for gate rejection counts over the last max_age_hours."""
    import re as _re
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    counts = {}
    label_map = [
        ("Tape gate",      "[TAPE GATE]"),
        ("OB gate",        "[OB GATE]"),
        ("Ensemble <4/7",  "ENSEMBLE SKIP"),
        ("Time block",     "time_block"),
        ("ADX too low",    "ADX"),
        ("Low volume",     "low vol"),
        ("No confluence",  "No confluence"),
        ("Choppy market",  "Choppy"),
        ("Cooldown",       "cooldown"),
        ("QUIET regime",   "QUIET regime"),
        ("Divergence",     "divergence"),
    ]
    try:
        with open(log_file, "r", errors="replace") as fh:
            for line in fh:
                if not any(kw.lower() in line.lower() for _, kw in label_map):
                    continue
                ts_match = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if ts < cutoff:
                            continue
                    except ValueError:
                        pass
                for label, keyword in label_map:
                    if keyword.lower() in line.lower():
                        counts[label] = counts.get(label, 0) + 1
                        break
    except (FileNotFoundError, PermissionError):
        pass
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _reconcile_status(max_age_hours: int = 24) -> dict:
    """Parse reconcile.log for CLEAN streak and last drift message."""
    import re as _re
    from datetime import datetime, timedelta, timezone
    import os as _os
    rec_log = _os.path.expanduser("~/Library/Logs/Phmex-S/reconcile.log")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    results = []
    try:
        with open(rec_log, "r", errors="replace") as fh:
            for line in fh:
                if "discrepanc" not in line.lower() and "CLEAN" not in line and "DRIFT" not in line:
                    continue
                ts_match = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if ts >= cutoff:
                            results.append(line.strip())
                    except ValueError:
                        pass
    except (FileNotFoundError, PermissionError):
        return {"streak": 0, "last": "reconcile.log not found", "drifts": []}
    clean_streak = 0
    drifts = []
    for line in reversed(results):
        if "Total discrepancies: 0" in line or "CLEAN" in line:
            clean_streak += 1
        else:
            drifts.append(line)
            break
    last = results[-1] if results else "No reconcile runs in last 24h"
    return {"streak": clean_streak, "last": last, "drifts": drifts[:3]}


def _net_pnl(t: dict) -> float:
    """Return net_pnl when present (post-fees), else fall back to gross pnl_usdt."""
    n = t.get("net_pnl")
    return n if n is not None else t.get("pnl_usdt", 0)


def _real_fee(t: dict) -> float:
    """Return real fees_usdt when present, else estimate (margin*lev*0.06%*2)."""
    f = t.get("fees_usdt")
    if f is not None:
        return f
    m = t.get("margin", 0) or 0
    return m * 10 * 0.0006 * 2 if m > 0 else 0


def read_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"peak_balance": 0, "closed_trades": []}


def read_paper_state() -> dict:
    """Read paper slot state file. Returns empty structure if missing."""
    try:
        with open(PAPER_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"peak_balance": 0, "closed_trades": []}


def read_narrow_state() -> dict:
    """Read 5m_narrow paper slot state file. Returns empty structure if missing."""
    try:
        with open(NARROW_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"peak_balance": 0, "closed_trades": [], "blocked_counts": {}}


def _build_narrow_panel(state: dict) -> str:
    """Build the NARROW (paper) panel — trade stats plus blocked-signal counts."""
    trades = state.get("closed_trades", []) or []
    try:
        with open(NARROW_BLOCKED_FILE) as f:
            blocked = json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        blocked = {"blocked_symbol": 0, "blocked_hour": 0, "blocked_ensemble": 0}
    b_sym = int(blocked.get("blocked_symbol", 0) or 0)
    b_hr = int(blocked.get("blocked_hour", 0) or 0)
    b_ens = int(blocked.get("blocked_ensemble", 0) or 0)

    if not trades and b_sym == 0 and b_hr == 0 and b_ens == 0:
        body = '<div style="color:var(--text-dim);text-align:center;padding:12px;font-size:0.85em">Awaiting first trade.</div>'
        return f'''<div class="glass-card dash-item paper-card" data-id="narrow-panel">
            <h2><span class="paper-badge">PAPER</span> NARROW (paper)</h2>
            {body}
        </div>'''

    stats = compute_stats(trades)
    total = stats["total"]
    wr = stats["win_rate"]
    pnl = stats["total_pnl"]
    wr_cls = "positive" if wr >= 50 else "negative" if wr < 30 else ""
    pnl_cls = "positive" if pnl >= 0 else "negative"

    def _row(label, val, cls=""):
        return (
            f'<div class="compare-row">'
            f'<span class="compare-label">{escape(label)}</span>'
            f'<span class="compare-paper {cls}" style="grid-column:2 / span 2;text-align:right">{val}</span>'
            f'</div>'
        )

    def _blocked_row(label, val):
        # Highlighted block-count row
        color = "var(--warning)" if val > 0 else "var(--text-dim)"
        return (
            f'<div class="compare-row" style="background:rgba(210,153,34,0.05);border-radius:3px">'
            f'<span class="compare-label">{escape(label)}</span>'
            f'<span class="compare-paper" style="grid-column:2 / span 2;text-align:right;color:{color};font-weight:600">{val}</span>'
            f'</div>'
        )

    return f'''<div class="glass-card dash-item paper-card" data-id="narrow-panel">
        <h2><span class="paper-badge">PAPER</span> NARROW (paper)</h2>
        <div class="compare-section-title">Performance</div>
        {_row("Trades", total)}
        {_row("Win Rate", f"{wr:.1f}%", wr_cls)}
        {_row("Net PnL", f"${pnl:+.2f}", pnl_cls)}
        <div class="compare-section-title" style="margin-top:10px">Blocked Signals</div>
        {_blocked_row("blocked_symbol", b_sym)}
        {_blocked_row("blocked_hour", b_hr)}
        {_blocked_row("blocked_ensemble", b_ens)}
    </div>'''


def read_factory_state() -> dict:
    """Read strategy factory state. Returns empty structure if missing."""
    try:
        with open(FACTORY_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"strategies": {}, "pipeline_log": []}


def read_all_slot_states() -> dict[str, dict]:
    """Discover and read all trading_state_*.json files. Returns {slot_id: state_dict}.
    Also maps 5m_scalp → main trading_state.json (the live slot has no sidecar file)."""
    slots = {}
    for path in _glob.glob(os.path.join(PROJECT_DIR, "trading_state_*.json")):
        fname = os.path.basename(path)
        if fname.endswith("_mode.json") or fname.endswith("_blocked.json"):
            continue  # sidecars (promotion flag / blocked counts), not slot state files
        # Extract slot_id: trading_state_5m_liq_cascade.json → 5m_liq_cascade
        slot_id = fname.replace("trading_state_", "").replace(".json", "")
        try:
            with open(path, "r") as f:
                slots[slot_id] = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            slots[slot_id] = {"peak_balance": 0, "closed_trades": []}
    # 5m_scalp uses the bot's main trading_state.json (no sidecar file).
    main_state_path = os.path.join(PROJECT_DIR, "trading_state.json")
    if os.path.exists(main_state_path):
        try:
            with open(main_state_path, "r") as f:
                slots["5m_scalp"] = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            slots["5m_scalp"] = {"peak_balance": 0, "closed_trades": []}
    return slots


def detect_sentinel_files() -> dict:
    """Check for active sentinel files (Phase 1 IPC). Returns {type: [details]}."""
    sentinels = {"paused": False, "kills": [], "pauses": [], "promotes": [], "demotes": [], "restart": False}
    if os.path.exists(os.path.join(PROJECT_DIR, ".pause_trading")):
        sentinels["paused"] = True
    if os.path.exists(os.path.join(PROJECT_DIR, ".restart_bot")):
        sentinels["restart"] = True
    for pat, key in [(".kill_*", "kills"), (".pause_*", "pauses"), (".promote_*", "promotes"), (".demote_*", "demotes")]:
        for path in _glob.glob(os.path.join(PROJECT_DIR, pat)):
            name = os.path.basename(path)
            # Skip .pause_trading (already handled above)
            if name == ".pause_trading":
                continue
            slot_id = name.split("_", 1)[1] if "_" in name else name
            sentinels[key].append(slot_id)
    return sentinels


def tail_log(n: int = 500) -> list[str]:
    try:
        result = subprocess.run(
            ["tail", "-n", str(n), LOG_FILE],
            capture_output=True, text=True, timeout=5
        )
        return [strip_ansi(line) for line in result.stdout.splitlines()]
    except Exception as e:
        print(f"[DASH] tail_log failed: {e}", flush=True)
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

        # Scanner results with scores — current SCALPSCAN format (post-2026-04-16 composite scanner):
        # "  INJ/USDT:USDT             score=0.628 (hist=0.90 x mkt=0.00) | vol=$3,284,863 | 24h= -3.9%"
        m = re.search(r'(\S+/USDT:USDT)\s+score=([\d.]+) \(hist=([\d.]+) x mkt=([\d.]+)\) \| vol=\$[\d,]+ \| 24h=\s*([\-\+]?[\d.]+)%', line)
        if m:
            change_24h = float(m.group(5))
            scanner_pairs.append({
                "symbol": m.group(1),
                "score": float(m.group(2)),
                "hist_score": float(m.group(3)),
                "mkt_score": float(m.group(4)),
                "change_24h": change_24h,
                "trend": "↑" if change_24h >= 0 else "↓",
                # Legacy fields kept for any consumer expecting the old shape
                "momentum": 0.0,
                "vol_spike": 0.0,
                "atr": 0.0,
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


def build_audit_table(trades: list[dict], index_offset: int = 0) -> str:
    """Build performance audit with breakdowns and collapsible trade log.

    index_offset: when called with a slice (e.g., Sentinel-era trades), pass the
    number of trades that come BEFORE this slice in the full closed_trades list.
    Used so the version-segmenting (Genesis/Patch/.../Sentinel) labels each
    trade by its absolute trade number, not its position within the slice.
    """
    if not trades:
        return '<div style="color:#7e8aa0;text-align:center;padding:20px">No trades to audit</div>'

    # Collect stats
    pair_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    strat_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    exit_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    side_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})

    # Strategies removed from the live ensemble — kept in history but flagged so users
    # know these numbers are archive data, not current live performance.
    RETIRED_STRATEGIES = {
        "htf_confluence_pullback",  # culled 2026-05-02 (post-cull n=18, 22% WR)
        "momentum_continuation",    # culled 2026-04-26 (Option A, n=11/30d)
        "htf_confluence_vwap",      # historical, not in current ensemble
        "bb_reversion",             # alias renamed to bb_mean_reversion (paper slot)
        "trend_scalp",
        "trend_pullback",
        "keltner_squeeze",
        "vwap_reversion",
        "confluence_sma_vwap",
        "funding_contrarian",
        "adaptive",
    }
    for t in trades:
        pnl = _net_pnl(t)
        sym = t.get("symbol", "?").replace("/USDT:USDT", "")
        strat = t.get("strategy", "") or ""
        if not strat or strat in ("unknown", "synced"):
            strat = "pre-tracking"
        elif strat in RETIRED_STRATEGIES:
            strat = f"{strat} (retired)"
        reason = t.get("exit_reason") or t.get("reason") or "unknown"
        side = t.get("side", "?").upper()
        is_win = pnl > 0

        for key, bucket in [(sym, pair_stats), (strat, strat_stats), (reason, exit_stats), (side, side_stats)]:
            bucket[key]["trades"] += 1
            bucket[key]["pnl"] += pnl
            if is_win:
                bucket[key]["wins"] += 1
            else:
                bucket[key]["losses"] += 1

    def _compact_table(title, stats_dict, sort_by="pnl"):
        items = sorted(stats_dict.items(), key=lambda x: x[1][sort_by], reverse=True)
        rows = ""
        for name, s in items:
            wr = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
            pnl_cls = "positive" if s["pnl"] >= 0 else "negative"
            wr_cls = "positive" if wr >= 50 else "negative"
            rows += f'''<tr>
                <td class="pair-cell">{escape(str(name))}</td>
                <td style="text-align:center">{s["trades"]}</td>
                <td class="{wr_cls}" style="text-align:center;font-weight:600">{wr:.0f}%</td>
                <td class="{pnl_cls}" style="text-align:right;font-weight:600;font-family:'JetBrains Mono',monospace">${s["pnl"]:+.2f}</td>
            </tr>'''
        col_name = title.replace("By ", "")
        return f'''<div class="audit-section">
            <h3>{escape(title)}</h3>
            <div class="table-wrap"><table>
                <thead><tr><th>{escape(col_name)}</th><th style="text-align:center">N</th><th style="text-align:center">WR</th><th style="text-align:right">PnL</th></tr></thead>
                <tbody>{rows}</tbody>
            </table></div>
        </div>'''

    # Trade log (last 30 shown, rest behind toggle)
    def _build_trade_row(t, trade_num, total):
        pnl = _net_pnl(t)
        pct = t.get("pnl_pct", 0)
        cls = "win" if pnl > 0 else "loss"
        sym = escape(t.get("symbol", "?").replace("/USDT:USDT", ""))
        side = escape(t.get("side", "?").upper())
        reason = escape(t.get("exit_reason") or t.get("reason") or "?")
        side_cls = "side-long" if side == "LONG" else "side-short"
        closed_at = t.get("closed_at", 0)
        opened_at = t.get("opened_at", 0)
        time_str = _from_ts(closed_at).strftime("%m/%d %I:%M%p").lower() if closed_at > 0 else "--"
        duration = ""
        if closed_at > 0 and opened_at > 0:
            dur_min = (closed_at - opened_at) / 60
            duration = f"{dur_min/60:.1f}h" if dur_min >= 60 else f"{dur_min:.0f}m"
        margin_val = t.get("margin", 0)
        fee_est = _real_fee(t)
        trade_idx = trade_num - 1
        if trade_idx <= 18: version = "Genesis"
        elif trade_idx <= 68: version = "Patch"
        elif trade_idx <= 80: version = "Filter"
        elif trade_idx <= 105: version = "Razor"
        elif trade_idx <= 156: version = "Razor v2.1"
        elif trade_idx <= 217: version = "Clarity"
        elif trade_idx <= 246: version = "v5-v9"
        elif trade_idx <= 341: version = "Pipeline"
        else: version = "Sentinel"
        ver_colors = {"Genesis": "#888", "Patch": "#4a9eff", "Filter": "#2ecc71", "Razor": "#e74c3c", "Razor v2.1": "#f39c12", "Clarity": "#9b59b6", "v5-v9": "#a6e3a1", "Pipeline": "#fab387", "Sentinel": "#00d4aa"}
        ver_color = ver_colors.get(version, "#888")
        return f'''<tr class="{cls}">
            <td>{trade_num}</td>
            <td style="color:{ver_color};font-size:0.8em;font-weight:600">{version}</td>
            <td><span class="side-badge {side_cls}">{side}</span></td>
            <td class="pair-cell">{sym}</td>
            <td class="pnl-cell">${pnl:+.2f}</td>
            <td class="pnl-cell">{pct:+.1f}%</td>
            <td class="reason-cell">{reason}</td>
            <td class="time-cell">{duration}</td>
            <td class="time-cell">{time_str}</td>
        </tr>'''

    # Show last 100 inline (was 30), older still behind collapsible. Full searchable
    # table with filters is at /trades — link added in the section heading below.
    INLINE_LIMIT = 100
    recent_rows = ""
    for i, t in enumerate(reversed(trades[-INLINE_LIMIT:])):
        trade_num = index_offset + len(trades) - i
        recent_rows += _build_trade_row(t, trade_num, len(trades))

    older_rows = ""
    if len(trades) > INLINE_LIMIT:
        for i, t in enumerate(reversed(trades[:-INLINE_LIMIT])):
            trade_num = index_offset + len(trades) - INLINE_LIMIT - i
            older_rows += _build_trade_row(t, trade_num, len(trades))

    log_header = '<thead><tr><th>#</th><th>Ver</th><th>Side</th><th>Pair</th><th>PnL</th><th>ROI</th><th>Exit</th><th>Dur</th><th>Closed</th></tr></thead>'

    older_section = ""
    if older_rows:
        older_section = f'''
        <details style="margin-top:8px">
            <summary style="cursor:pointer;color:var(--accent);font-size:0.8em;font-weight:500;padding:6px 0">Show {len(trades)-INLINE_LIMIT} older trades</summary>
            <div class="table-wrap" style="max-height:600px;overflow-y:auto">
            <table>{log_header}<tbody>{older_rows}</tbody></table>
            </div>
        </details>'''

    return f'''
    <div class="audit-grid">
        {_compact_table("By Exit Reason", exit_stats)}
        {_compact_table("By Pair", pair_stats)}
        {_compact_table("By Side", side_stats)}
        {_compact_table("By Strategy", strat_stats)}
    </div>
    <div style="margin-top:10px">
        <div style="font-size:0.72em;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
            <span>Recent Trades ({min(INLINE_LIMIT,len(trades))} of {len(trades)})</span>
            <a href="/trades" target="_blank" style="font-size:0.85em;color:var(--accent);text-decoration:none">Full table + filters →</a>
        </div>
        <div class="table-wrap" style="max-height:500px;overflow-y:auto">
        <table>{log_header}<tbody>{recent_rows}</tbody></table>
        </div>
        {older_section}
    </div>'''


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "total_pnl": 0, "total_fees": 0, "real_pnl": 0,
                "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
                "best": 0, "worst": 0, "max_dd": 0, "max_dd_pct": 0}
    wins = [t for t in trades if _net_pnl(t) > 0]
    losses = [t for t in trades if _net_pnl(t) <= 0]
    # total_pnl is now NET (post-fees) — this is the honest number
    total_pnl = sum(_net_pnl(t) for t in trades)
    gp = sum(_net_pnl(t) for t in wins) if wins else 0
    gl = abs(sum(_net_pnl(t) for t in losses)) if losses else 0
    best = max(_net_pnl(t) for t in trades)
    worst = min(_net_pnl(t) for t in trades)

    # Max drawdown from cumulative net curve
    cum = 0
    peak = 0
    max_dd = 0
    max_dd_pct = 0
    for t in trades:
        cum += _net_pnl(t)
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * 100) if peak > 0 else 0

    # Real fees from exchange capture (falls back to estimate for old trades)
    total_fees = sum(_real_fee(t) for t in trades)
    real_pnl = total_pnl  # already net

    return {
        "total": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "total_pnl": total_pnl, "total_fees": total_fees, "real_pnl": real_pnl,
        "avg_win": gp / len(wins) if wins else 0,
        "avg_loss": gl / len(losses) if losses else 0,
        "profit_factor": gp / gl if gl > 0 else float('inf'),
        "best": best, "worst": worst, "max_dd": max_dd, "max_dd_pct": max_dd_pct,
    }


def _build_reconcile_card() -> str:
    """Reconciliation status vs Phemex exchange truth.

    Reads ~/Library/Logs/Phmex-S/reconcile.log written every 4h by
    scripts/reconcile_phemex.py (launchd: com.phmex.reconcile).
    """
    log_path = Path.home() / "Library" / "Logs" / "Phmex-S" / "reconcile.log"
    if not log_path.exists():
        return '''<div class="glass-card dash-item" data-id="reconcile">
            <h2>Reconciliation vs Phemex</h2>
            <div style="color:var(--text-dim);font-size:0.8em;padding:6px 0">No reconciliation data yet</div>
        </div>'''
    try:
        mtime = log_path.stat().st_mtime
        text = log_path.read_text(errors="replace")
    except Exception as e:
        return f'''<div class="glass-card dash-item" data-id="reconcile">
            <h2>Reconciliation vs Phemex</h2>
            <div style="color:var(--negative);font-size:0.8em">Read error: {escape(str(e))}</div>
        </div>'''

    runs = text.split("=== Phemex Reconciliation")
    if len(runs) < 2:
        return '''<div class="glass-card dash-item" data-id="reconcile">
            <h2>Reconciliation vs Phemex</h2>
            <div style="color:var(--text-dim);font-size:0.8em">Waiting for first run</div>
        </div>'''
    latest = runs[-1]

    discrepancies = 0
    max_drift = 0.0
    symbol_count = 0
    for line in latest.splitlines():
        line = line.strip()
        if line.startswith("Discrepancies"):
            try:
                discrepancies = int(line.split(":")[-1].strip())
            except Exception:
                pass
        if "/USDT:USDT" in line:
            symbol_count += 1
            parts = line.split()
            try:
                dnet = float(parts[-2 if "<--" in line else -1].replace("DIFF", "").strip() or 0)
            except Exception:
                dnet = 0.0
            if abs(dnet) > abs(max_drift):
                max_drift = dnet

    age_hours = (time.time() - mtime) / 3600
    if age_hours > 8:
        status_icon = "&#128308;"  # red circle
        status_text = "STALE"
        status_color = "var(--negative)"
    elif discrepancies > 0:
        status_icon = "&#128993;"  # yellow circle
        status_text = f"DRIFT ({discrepancies})"
        status_color = "var(--warning)"
    else:
        status_icon = "&#128994;"  # green circle
        status_text = "CLEAN"
        status_color = "var(--positive)"

    last_ts = datetime.fromtimestamp(mtime, tz=CA_TZ).strftime("%b %d %I:%M %p")
    age_str = f"{int(age_hours)}h ago" if age_hours >= 1 else f"{int(age_hours*60)}m ago"

    return f'''<div class="glass-card dash-item" data-id="reconcile">
        <h2>Reconciliation vs Phemex</h2>
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.78em;line-height:1.7">
            <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #21262d">
                <span style="color:var(--text-dim)">Status</span>
                <span style="color:{status_color};font-weight:700">{status_icon} {status_text}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #21262d">
                <span style="color:var(--text-dim)">Last run</span>
                <span>{last_ts}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #21262d">
                <span style="color:var(--text-dim)">Age</span>
                <span>{age_str}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #21262d">
                <span style="color:var(--text-dim)">Symbols</span>
                <span>{symbol_count}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:3px 0">
                <span style="color:var(--text-dim)">Max drift</span>
                <span class="{'negative' if abs(max_drift) > 0.05 else ''}">${max_drift:+.2f}</span>
            </div>
        </div>
    </div>'''


def _build_observability_panel() -> str:
    """Build Phase 2c observability HTML panel (Gate Rejection Breakdown only).

    Note: Reconcile Status card was removed to eliminate duplication with
    _build_reconcile_card(); reconcile data is now shown in one place only.
    """
    from html import escape as _esc
    stats = _gate_stats(LOG_FILE)
    if stats:
        total_blocks = sum(stats.values())
        gate_rows = ""
        for label, count in list(stats.items())[:8]:
            pct = count / total_blocks * 100 if total_blocks else 0
            gate_rows += f'<tr><td style="padding:4px 8px;font-size:13px">{_esc(label)}</td><td style="padding:4px 8px;text-align:right;font-family:monospace">{count:,}</td><td style="padding:4px 8px;text-align:right;color:#888;font-size:12px">{pct:.0f}%</td></tr>'
        gates_html = f'<div style="margin-bottom:8px;color:#888;font-size:12px">{total_blocks:,} total blocks (last 24h)</div><div class="table-wrap"><table><thead><tr><th>Gate</th><th style="text-align:right">Blocks</th><th style="text-align:right">%</th></tr></thead><tbody>{gate_rows}</tbody></table></div>'
    else:
        gates_html = '<div style="color:#888;font-size:13px">No gate rejections found in log</div>'

    return f'''<div class="glass-card dash-item" data-id="obs-gates">
        <h2>Gate Rejection Breakdown (24h)</h2>
        {gates_html}
    </div>'''


def _build_session_card(trades: list[dict], paper_trades: list[dict], **_kwargs) -> str:
    """Build SESSION PERFORMANCE as a horizontal row of 4 time-of-day tiles."""
    SESSIONS = [
        ("Early AM", "12-6 AM", "&#127747;", "#cba6f7"),
        ("Morning", "6 AM-12 PM", "&#9728;&#65039;", "#a6e3a1"),
        ("Afternoon", "12-8 PM", "&#9925;", "#fab387"),
        ("Night", "8 PM-12 AM", "&#9789;&#65039;", "#89b4fa"),
    ]

    def _classify_hour(hour: int) -> int:
        if hour < 6: return 0
        elif hour < 12: return 1
        elif hour < 20: return 2
        else: return 3

    def _compute(trade_list):
        stats = [{"trades": 0, "wins": 0, "pnl": 0.0} for _ in range(4)]
        for t in trade_list:
            ts = t.get("opened_at", 0)
            if ts <= 0: continue
            idx = _classify_hour(_from_ts(ts).hour)
            pnl = _net_pnl(t)
            stats[idx]["trades"] += 1
            stats[idx]["pnl"] += pnl
            if pnl > 0: stats[idx]["wins"] += 1
        return stats

    today_start = _now_ca().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_live = [t for t in trades if t.get("opened_at", 0) >= today_start]

    td = _compute(today_live)
    al = _compute(trades)

    # Build 4 tiles
    tiles = ""
    for i, (label, hours, _icon, color) in enumerate(SESSIONS):
        t_s, a_s = td[i], al[i]
        # Today stats
        if t_s["trades"] > 0:
            t_wr = (t_s["wins"] / t_s["trades"] * 100)
            t_pnl_cls = "positive" if t_s["pnl"] >= 0 else "negative"
            t_wr_cls = "positive" if t_wr >= 50 else "negative"
            today_html = f'''<span class="{t_pnl_cls}" style="font-weight:600">${t_s["pnl"]:+.2f}</span>
                <span style="color:var(--text-dim);font-size:0.85em">{t_s["trades"]}t</span>
                <span class="{t_wr_cls}" style="font-size:0.85em">{t_wr:.0f}%</span>'''
        else:
            today_html = '<span style="color:var(--text-dim)">--</span>'
        # All-time stats
        if a_s["trades"] > 0:
            a_wr = (a_s["wins"] / a_s["trades"] * 100)
            a_pnl_cls = "positive" if a_s["pnl"] >= 0 else "negative"
            a_wr_cls = "positive" if a_wr >= 50 else "negative"
            all_html = f'''<span class="{a_pnl_cls}" style="font-weight:600">${a_s["pnl"]:+.2f}</span>
                <span style="color:var(--text-dim);font-size:0.85em">{a_s["trades"]}t</span>
                <span class="{a_wr_cls}" style="font-size:0.85em">{a_wr:.0f}%</span>'''
        else:
            all_html = '<span style="color:var(--text-dim)">--</span>'

        tiles += f'''<div style="text-align:center;padding:8px 6px;border-top:2px solid {color};background:var(--bg-deep);border-radius:0 0 3px 3px">
            <div style="font-size:0.72em;font-weight:600;color:{color};font-family:'JetBrains Mono',monospace">{escape(label)}</div>
            <div style="font-size:0.6em;color:var(--text-dim);margin-bottom:6px;font-family:'JetBrains Mono',monospace">{hours} PT</div>
            <div style="font-size:0.6em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:2px;font-family:'JetBrains Mono',monospace">Today</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.75em;display:flex;flex-direction:column;align-items:center;gap:1px">{today_html}</div>
            <div style="font-size:0.6em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.04em;margin:5px 0 2px;font-family:'JetBrains Mono',monospace">All Time</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.75em;display:flex;flex-direction:column;align-items:center;gap:1px">{all_html}</div>
        </div>'''

    # Today total across all 4 sessions
    today_total_trades = sum(s["trades"] for s in td)
    today_total_wins = sum(s["wins"] for s in td)
    today_total_pnl = sum(s["pnl"] for s in td)
    if today_total_trades > 0:
        today_total_wr = today_total_wins / today_total_trades * 100
        tt_pnl_cls = "positive" if today_total_pnl >= 0 else "negative"
        tt_wr_cls = "positive" if today_total_wr >= 50 else "negative"
        total_html = (
            f'<span class="{tt_pnl_cls}" style="font-weight:700;font-size:1.05em">${today_total_pnl:+.2f}</span>'
            f'<span style="color:var(--text-dim);font-size:0.85em;margin-left:10px">{today_total_trades}t</span>'
            f'<span class="{tt_wr_cls}" style="font-size:0.85em;margin-left:8px">{today_total_wr:.0f}%</span>'
        )
    else:
        total_html = '<span style="color:var(--text-dim)">no trades today</span>'
    today_total_bar = (
        f'<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;'
        f'background:var(--bg-deep);border-radius:3px;margin-bottom:8px;font-family:\'JetBrains Mono\',monospace">'
        f'<span style="font-size:0.72em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em">Today Total</span>'
        f'<span style="font-size:0.85em">{total_html}</span>'
        f'</div>'
    )

    return f'''<div class="glass-card dash-item" data-id="sessions">
        <h2>Sessions</h2>
        {today_total_bar}
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px">{tiles}</div>
    </div>'''


def _build_paper_comparison(live_trades: list[dict], paper_trades: list[dict]) -> str:
    """Build side-by-side Live vs Paper (liq_cascade) comparison card."""
    live_stats = compute_stats(live_trades)
    paper_stats = compute_stats(paper_trades)

    today_start = _now_ca().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    live_today = [t for t in live_trades if t.get("opened_at", 0) >= today_start]
    paper_today = [t for t in paper_trades if t.get("opened_at", 0) >= today_start]
    live_today_stats = compute_stats(live_today)
    paper_today_stats = compute_stats(paper_today)

    has_paper = len(paper_trades) > 0

    def _stat_col(label, live_val, paper_val, is_pnl=False, is_pct=False):
        def _fmt(val, has_data):
            if not has_data:
                return ("", "--")
            if is_pnl:
                return ("positive" if val >= 0 else "negative", f"${val:+.2f}")
            elif is_pct:
                return ("positive" if val >= 50 else "negative", f"{val:.1f}%")
            else:
                return ("", str(val))
        l_cls, l_str = _fmt(live_val, True)
        p_cls, p_str = _fmt(paper_val, has_paper)
        return f'''<div class="compare-row">
            <span class="compare-label">{label}</span>
            <span class="compare-live {l_cls}">{l_str}</span>
            <span class="compare-paper {p_cls}">{p_str}</span>
        </div>'''

    # Recent paper trades list (last 5)
    # Gate tag summary for paper trades
    gate_summary = ""
    tagged = [t for t in paper_trades if t.get("gate_tags") and t["gate_tags"] != "none"]
    untagged = [t for t in paper_trades if not t.get("gate_tags") or t["gate_tags"] == "none"]
    if paper_trades:
        _would_pass = len(untagged)
        _would_block = len(tagged)
        _pass_pnl = sum(_net_pnl(t) for t in untagged)
        _block_pnl = sum(_net_pnl(t) for t in tagged)
        _pass_wr = (sum(1 for t in untagged if _net_pnl(t) > 0) / len(untagged) * 100) if untagged else 0
        _block_wr = (sum(1 for t in tagged if _net_pnl(t) > 0) / len(tagged) * 100) if tagged else 0
        _pass_cls = "positive" if _pass_pnl >= 0 else "negative"
        _block_cls = "positive" if _block_pnl >= 0 else "negative"
        gate_summary = f'''<div class="compare-section-title" style="margin-top:10px">Gate Shadow Tags</div>
            <div class="compare-row">
                <span class="compare-label">Would PASS live</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:0.8em;color:var(--text-primary)">{_would_pass}t / {_pass_wr:.0f}%</span>
                <span class="{_pass_cls}" style="font-family:'JetBrains Mono',monospace;font-size:0.8em">${_pass_pnl:+.2f}</span>
            </div>
            <div class="compare-row">
                <span class="compare-label">Would be BLOCKED</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:0.8em;color:var(--text-primary)">{_would_block}t / {_block_wr:.0f}%</span>
                <span class="{_block_cls}" style="font-family:'JetBrains Mono',monospace;font-size:0.8em">${_block_pnl:+.2f}</span>
            </div>'''

    recent_paper = ""
    if has_paper:
        last5 = paper_trades[-5:]
        for t in reversed(last5):
            pnl = _net_pnl(t)
            sym = escape(t.get("symbol", "?").replace("/USDT:USDT", ""))
            side = t.get("side", "?").upper()
            reason = escape(t.get("exit_reason") or t.get("reason") or "?")
            tags = t.get("gate_tags", "")
            tag_badge = ""
            if tags and tags != "none":
                tag_badge = f'<span style="font-size:0.6em;padding:1px 4px;border-radius:2px;background:rgba(248,81,73,0.1);color:#f85149;border:1px solid rgba(248,81,73,0.2);margin-left:3px">{escape(tags)}</span>'
            elif tags == "none":
                tag_badge = '<span style="font-size:0.6em;padding:1px 4px;border-radius:2px;background:rgba(63,185,80,0.1);color:#3fb950;border:1px solid rgba(63,185,80,0.2);margin-left:3px">PASS</span>'
            cls = "positive" if pnl > 0 else "negative"
            side_cls = "side-long" if side == "LONG" else "side-short"
            closed_at = t.get("closed_at", 0)
            time_str = _from_ts(closed_at).strftime("%m/%d %I:%M%p").lower() if closed_at > 0 else "--"
            recent_paper += f'''<div class="paper-trade-row">
                <span class="side-badge {side_cls}" style="font-size:0.7em">{side}</span>
                <span style="color:var(--text-primary);font-weight:500">{sym}</span>
                <span class="{cls}" style="font-family:'JetBrains Mono',monospace;font-weight:600">${pnl:+.2f}</span>
                <span style="color:var(--text-dim);font-size:0.85em">{reason}</span>
                {tag_badge}
                <span style="color:var(--text-dim);font-size:0.8em;font-family:'JetBrains Mono',monospace">{time_str}</span>
            </div>'''
    else:
        recent_paper = '<div style="color:var(--text-dim);text-align:center;padding:12px;font-size:0.85em">Paper slot not active yet.</div>'

    return f'''<div class="glass-card dash-item paper-card" data-id="paper-comparison">
        <h2><span class="paper-badge">PAPER</span> Live vs Liq Cascade</h2>
        <div class="compare-header">
            <span class="compare-label"></span>
            <span class="compare-col-label live-label">LIVE</span>
            <span class="compare-col-label paper-label">PAPER</span>
        </div>
        <div class="compare-section-title">All Time</div>
        {_stat_col("Trades", live_stats["total"], paper_stats["total"])}
        {_stat_col("Win Rate", live_stats["win_rate"], paper_stats["win_rate"], is_pct=True)}
        {_stat_col("PnL", live_stats["total_pnl"], paper_stats["total_pnl"], is_pnl=True)}
        {_stat_col("Profit Factor", round(live_stats["profit_factor"], 2) if live_stats["profit_factor"] != float("inf") else 0, round(paper_stats["profit_factor"], 2) if paper_stats["profit_factor"] != float("inf") else 0)}
        {_stat_col("Avg Win", live_stats["avg_win"], paper_stats["avg_win"], is_pnl=True)}
        {_stat_col("Avg Loss", -live_stats["avg_loss"], -paper_stats["avg_loss"], is_pnl=True)}
        <div class="compare-section-title" style="margin-top:10px">Today</div>
        {_stat_col("Trades", live_today_stats["total"], paper_today_stats["total"])}
        {_stat_col("Win Rate", live_today_stats["win_rate"], paper_today_stats["win_rate"], is_pct=True)}
        {_stat_col("PnL", live_today_stats["total_pnl"], paper_today_stats["total_pnl"], is_pnl=True)}
        {gate_summary}
        <div class="compare-section-title" style="margin-top:10px">Recent Paper Trades</div>
        {recent_paper}
    </div>'''


# ── Slot lifecycle overview ─────────────────────────────────────────────
# Mapping from slot_id to strategy name — keep in sync with bot.py
_SLOT_STRATEGY_MAP = {
    "5m_scalp": "confluence",
    "5m_mean_revert": "bb_mean_reversion",
    "5m_liq_cascade": "liq_cascade",
    "5m_narrow": "narrow_filter",
    "5m_narrow_blocked": "narrow_filter",
}

# Slots that run LIVE (not paper). All others default to paper.
def _live_slot_ids():
    """Live slots: the main bot (5m_scalp) plus any slot promoted via mode sidecar."""
    ids = {"5m_scalp"}
    for path in _glob.glob(os.path.join(PROJECT_DIR, "trading_state_*_mode.json")):
        try:
            with open(path) as f:
                if not json.load(f).get("paper_mode", True):
                    ids.add(os.path.basename(path).replace("trading_state_", "").replace("_mode.json", ""))
        except Exception:
            pass
    return ids


def _compute_kelly_raw(trades: list[dict]) -> float:
    """Mirror RiskManager.calculate_kelly_raw — needs ≥20 trades, returns negative if no edge."""
    if len(trades) < 20:
        return 0.0
    wins = [t for t in trades if _net_pnl(t) > 0]
    losses = [t for t in trades if _net_pnl(t) <= 0]
    if not wins or not losses:
        return 0.0
    wr = len(wins) / len(trades)
    avg_win = sum(_net_pnl(t) for t in wins) / len(wins)
    avg_loss = abs(sum(_net_pnl(t) for t in losses) / len(losses))
    if avg_win == 0:
        return 0.0
    return (wr * avg_win - (1 - wr) * avg_loss) / avg_win


def _compute_slot_stage(slot_id: str, trades: list[dict], factory_stage: str,
                        sentinels: dict) -> str:
    """Single source of truth for slot status. Mirrors StrategySlot.is_killed
    so the dashboard matches what the bot logs as `[SLOT] X (MODE/STATUS)`."""
    # Sentinel kills take highest priority
    if slot_id in sentinels.get("kills", []):
        return "killed"
    if slot_id in sentinels.get("pauses", []):
        return "paused"
    if slot_id in sentinels.get("promotes", []):
        return "promoting"
    if slot_id in sentinels.get("demotes", []):
        return "demoting"
    # Live slot is whatever the bot is configured to run live (5m_scalp). Don't
    # apply Kelly auto-kill to it: its trade history is the main trading_state.json
    # (lifetime live trades, includes pre-Sentinel iterations), not the slot's
    # sidecar — the bot itself uses an empty sidecar so its is_killed never trips.
    if slot_id in _live_slot_ids():
        return "live"
    # Paper slots: auto-kill at 50+ trades AND negative Kelly (strategy_slot.py:70-78)
    if len(trades) >= 50 and _compute_kelly_raw(trades) < 0:
        return "killed"
    # Factory stage overrides only if it's a known label (avoid "unknown" fallback).
    if factory_stage in ("paper", "killed", "hypothesis"):
        return factory_stage
    return "paper"


def _build_slots_overview(all_slots: dict[str, dict], factory: dict, sentinels: dict) -> str:
    """Build a card showing all slots with lifecycle stage, trade count, and status."""
    strategies = factory.get("strategies", {})

    # Sentinel status banner
    banner = ""
    if sentinels.get("paused"):
        banner = '<div style="background:rgba(248,81,73,0.08);border:1px solid rgba(248,81,73,0.2);color:var(--negative);padding:6px 10px;border-radius:3px;margin-bottom:8px;text-align:center;font-weight:600;font-family:\'JetBrains Mono\',monospace;font-size:0.8em">TRADING PAUSED</div>'
    if sentinels.get("restart"):
        banner += '<div style="background:rgba(210,153,34,0.08);border:1px solid rgba(210,153,34,0.2);color:var(--warning);padding:6px 10px;border-radius:3px;margin-bottom:8px;text-align:center;font-weight:600;font-family:\'JetBrains Mono\',monospace;font-size:0.8em">RESTART PENDING</div>'

    # Build slot rows
    rows = ""
    # Known active slots first, then any discovered extras
    known_order = ["5m_scalp", "5m_mean_revert", "5m_liq_cascade"]
    # Add any discovered slots not in known_order
    extra_slots = [s for s in all_slots if s not in known_order and s not in ("v8_245trades",)]
    ordered = known_order + extra_slots

    for slot_id in ordered:
        state = all_slots.get(slot_id, {"closed_trades": []})
        trades = state.get("closed_trades", [])
        n_trades = len(trades)

        # Determine strategy name and stage from factory
        strat_name = _SLOT_STRATEGY_MAP.get(slot_id, slot_id)
        strat_info = strategies.get(strat_name, {})
        factory_stage = strat_info.get("stage", "")
        stage = _compute_slot_stage(slot_id, trades, factory_stage, sentinels)

        # Stage badge styling
        stage_styles = {
            "live": ("rgba(63,185,80,0.08)", "#3fb950", "rgba(63,185,80,0.2)"),
            "paper": ("rgba(57,210,192,0.08)", "#39d2c0", "rgba(57,210,192,0.2)"),
            "killed": ("rgba(248,81,73,0.08)", "#f85149", "rgba(248,81,73,0.2)"),
            "paused": ("rgba(210,153,34,0.08)", "#d29922", "rgba(210,153,34,0.2)"),
            "promoting": ("rgba(210,153,34,0.08)", "#d29922", "rgba(210,153,34,0.2)"),
            "demoting": ("rgba(210,153,34,0.08)", "#d29922", "rgba(210,153,34,0.2)"),
            "hypothesis": ("rgba(139,148,158,0.08)", "#8b949e", "rgba(139,148,158,0.2)"),
        }
        bg, fg, bdr = stage_styles.get(stage, stage_styles["hypothesis"])

        # Compute basic metrics
        wr = 0
        pnl = 0
        if n_trades > 0:
            wins = sum(1 for t in trades if _net_pnl(t) > 0)
            wr = (wins / n_trades) * 100
            pnl = sum(_net_pnl(t) for t in trades)

        wr_cls = "positive" if wr >= 40 else "negative" if wr < 30 else ""
        pnl_cls = "positive" if pnl > 0 else "negative" if pnl < 0 else ""

        rows += f'''<div style="display:grid;grid-template-columns:1fr auto auto auto;gap:6px;align-items:center;padding:5px 0;border-bottom:1px solid #21262d">
            <div>
                <span style="font-family:'JetBrains Mono',monospace;font-size:0.78em;font-weight:500;color:var(--text-primary)">{escape(slot_id)}</span>
                <span style="display:inline-block;font-size:0.6em;padding:1px 5px;border-radius:3px;margin-left:4px;background:{bg};color:{fg};border:1px solid {bdr};font-weight:600;text-transform:uppercase;letter-spacing:0.04em;font-family:'JetBrains Mono',monospace">{escape(stage)}</span>
            </div>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.72em;color:var(--text-dim);text-align:right">{n_trades}t</span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.72em;text-align:right" class="{wr_cls}">{wr:.0f}%</span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.72em;text-align:right" class="{pnl_cls}">${pnl:+.2f}</span>
        </div>'''

    # Pipeline log (last 5 events)
    # Pipeline log — only render entries from the last 30 days. Older entries are
    # historical noise (March hypothesis registrations, etc.) that mislead more than inform.
    pipeline = factory.get("pipeline_log", [])
    log_html = ""
    if pipeline:
        from datetime import datetime as _dt, timedelta as _td
        cutoff = _dt.now() - _td(days=30)
        recent = []
        for entry in pipeline:
            ts_raw = entry.get("time", "")
            try:
                ts_dt = _dt.fromisoformat(ts_raw.replace("Z", "+00:00").split(".")[0])
                if ts_dt.replace(tzinfo=None) >= cutoff:
                    recent.append(entry)
            except (ValueError, AttributeError):
                continue
        if recent:
            for entry in recent[-5:]:
                ts = entry.get("time", "")[:16].replace("T", " ")
                log_html += f'<div style="font-size:0.68em;color:var(--text-dim);padding:2px 0;font-family:\'JetBrains Mono\',monospace">{ts} — {escape(entry.get("strategy", ""))} — {escape(entry.get("event", ""))}</div>'
            log_html = f'<div class="compare-section-title" style="margin-top:10px">Pipeline Log (30d)</div>{log_html}'

    return f'''<div class="glass-card dash-item" data-id="slots-overview">
        <h2>Slot Lifecycle</h2>
        {banner}
        <div style="display:grid;grid-template-columns:1fr auto auto auto;gap:6px;padding:0 0 3px;border-bottom:1px solid #21262d;margin-bottom:3px">
            <span style="font-size:0.65em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;font-family:'JetBrains Mono',monospace">Slot</span>
            <span style="font-size:0.65em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;text-align:right;font-family:'JetBrains Mono',monospace">N</span>
            <span style="font-size:0.65em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;text-align:right;font-family:'JetBrains Mono',monospace">WR</span>
            <span style="font-size:0.65em;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;text-align:right;font-family:'JetBrains Mono',monospace">PnL</span>
        </div>
        {rows}
        {log_html}
    </div>'''


# ── Equity series (JSON for the client-side uPlot chart) ────────────────
def build_equity_series(era: str = "sentinel") -> dict:
    """Cumulative NET PnL series for /api/equity — rendered client-side by uPlot.

    Merges main closed_trades with live-promoted slots' LIVE-mode closed trades
    (slot trades carry mode=="live"), sorted by close timestamp.
    era="sentinel" reuses the exact cutoff the removed PNG sentinel chart
    used: (opened_at or closed_at) >= SENTINEL_DEPLOY_TS. era="all" = everything.
    Returns {"t": [unix_ts], "v": [cum_net], "meta": [per-trade dict]}.
    """
    rows = [("main", t) for t in read_state().get("closed_trades", []) or []]
    for slot_id in sorted(_live_slot_ids()):
        if slot_id == "5m_scalp":
            continue  # main trading_state.json already merged above
        try:
            with open(os.path.join(PROJECT_DIR, f"trading_state_{slot_id}.json")) as f:
                slot_trades = json.load(f).get("closed_trades", []) or []
        except Exception:
            continue
        rows.extend((slot_id, t) for t in slot_trades if t.get("mode") == "live")
    if era == "sentinel":
        # Same cutoff logic as the removed _make_cumulative_pnl_sentinel.
        rows = [(o, t) for o, t in rows
                if (t.get("opened_at") or t.get("closed_at") or 0) >= SENTINEL_DEPLOY_TS]
    rows.sort(key=lambda r: r[1].get("closed_at") or r[1].get("opened_at") or 0)

    ts, vals, meta = [], [], []
    cum = 0.0
    for owner, t in rows:
        net = _net_pnl(t)
        cum += net
        x = t.get("closed_at") or t.get("opened_at") or 0
        if not x:
            # 19 earliest trades predate timestamping. A time-scaled x-axis
            # would plot them at 1970 — fold their PnL into the baseline
            # instead of fabricating an x position.
            continue
        try:
            time_pt = _from_ts(x).strftime("%-m/%-d %-I:%M %p PT")
        except Exception:
            time_pt = "?"
        ts.append(x)
        vals.append(round(cum, 4))
        meta.append({
            "sym": str(t.get("symbol") or "?").replace("/USDT:USDT", ""),
            "strat": str(t.get("strategy") or owner),
            "pnl": round(net, 4),
            "reason": str(t.get("exit_reason") or t.get("reason") or ""),
            "win": net > 0,
            "time_pt": time_pt,
        })
    return {"t": ts, "v": vals, "meta": meta}


# ── Blotter (merged main + slots) + trade drill-down ─────────────────────
def _blotter_sources() -> list[tuple[str, str]]:
    """(owner, abs_path) pairs for every closed-trades source.
    Skips _mode.json (promotion flag) and _blocked.json (blocked counts)
    sidecars — same skip rule as read_all_slot_states."""
    sources = [("main", STATE_FILE)]
    for path in sorted(_glob.glob(os.path.join(PROJECT_DIR, "trading_state_*.json"))):
        fname = os.path.basename(path)
        if fname.endswith("_mode.json") or fname.endswith("_blocked.json"):
            continue
        sources.append((fname.replace("trading_state_", "").replace(".json", ""), path))
    return sources


def collect_blotter_rows(limit: int = 500) -> list[dict]:
    """Merged blotter: main closed_trades (owner "main") + every slot state's
    closed_trades (owner = slot_id). Stable id = "owner:index_in_that_file"
    (files are append-only, so the index never moves). Newest first."""
    rows = []
    for owner, path in _blotter_sources():
        try:
            with open(path) as f:
                trades = json.load(f).get("closed_trades", []) or []
        except Exception:
            continue
        for i, t in enumerate(trades):
            ts = t.get("closed_at") or t.get("opened_at") or 0
            try:
                time_pt = _from_ts(ts).strftime("%-m/%-d %-I:%M %p") if ts else "?"
            except Exception:
                time_pt = "?"
            # Main trades are the live bot. A slot trade is live ONLY when the
            # record itself carries mode=="live" (stamped at fill time, post-
            # promotion) — same rule build_equity_series uses. Trades closed
            # while the slot was still paper stay tagged paper.
            mode = "live" if owner == "main" else (t.get("mode") or "paper")
            rows.append({
                "id": f"{owner}:{i}",
                "ts": ts,
                "time_pt": time_pt,
                "sym": str(t.get("symbol") or "?").replace("/USDT:USDT", ""),
                "side": str(t.get("side") or "?"),
                "strat": str(t.get("strategy") or ""),
                "net": round(_net_pnl(t), 4),
                "reason": str(t.get("exit_reason") or t.get("reason") or ""),
                "owner": owner,
                "mode": mode,
            })
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows[:limit]


def build_trade_detail(trade_id: str) -> dict:
    """Drill-down payload for one blotter row id ("owner:index").
    Re-reads the owning state file; unknown/malformed id → {"error": "not found"}."""
    try:
        owner, idx_s = str(trade_id).split(":", 1)
        idx = int(idx_s)
        # owner becomes part of a filename — allow only safe slot-id chars.
        if idx < 0 or not re.fullmatch(r"[A-Za-z0-9_]+", owner):
            return {"error": "not found"}
        path = STATE_FILE if owner == "main" else os.path.join(
            PROJECT_DIR, f"trading_state_{owner}.json")
        with open(path) as f:
            t = (json.load(f).get("closed_trades", []) or [])[idx]
    except Exception:
        return {"error": "not found"}
    try:
        opened, closed = t.get("opened_at") or 0, t.get("closed_at") or 0
        def _fmt(ts):
            try:
                return _from_ts(ts).strftime("%-m/%-d %-I:%M:%S %p PT") if ts else "?"
            except Exception:
                return "?"
        snap = t.get("entry_snapshot")
        return {
            "trade": {
                "sym": str(t.get("symbol") or "?").replace("/USDT:USDT", ""),
                "side": str(t.get("side") or "?"),
                "strat": str(t.get("strategy") or ""),
                "entry_price": t.get("entry_price") or t.get("entry"),
                "exit_price": t.get("exit_price") or t.get("exit"),
                "net": round(_net_pnl(t), 6),
                "gross": t.get("pnl_usdt"),
                "confidence": t.get("confidence"),
                "layers": t.get("ensemble_layers"),
                "opened_pt": _fmt(opened),
                "closed_pt": _fmt(closed),
                "duration_s": t.get("duration_s"),
                "reason": str(t.get("exit_reason") or t.get("reason") or ""),
                "owner": owner,
                "mode": t.get("mode") or ("live" if owner == "main" else "paper"),
            },
            "snapshot": snap if isinstance(snap, dict) else "no snapshot recorded",
            "gate_tags": t.get("gate_tags"),
            "fees": {
                "fees_usdt": round(_real_fee(t), 6),
                "funding_usdt": t.get("funding_usdt"),
                "fees_source": t.get("fees_source") or "estimated",
            },
            "basis": "net",
        }
    except Exception:
        return {"error": "not found"}


def _build_watchlist_html(wl: dict, positions: dict | None = None) -> str:
    """Render watchlist as a grid of coin tiles with status dots.

    positions: live state positions dict (trading_state.json), used to show the
    exchange-resting SL on open-position tiles.
    """
    positions = positions or {}
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
        if is_open:
            pos = positions.get(sym) or {}
            # Prefer the exchange-resting SL (durable trailing stop) so the tile
            # never shows internal stop_loss while the resting order sits elsewhere.
            # Old state files lack exchange_sl_price — fall back to stop_loss.
            sl_val = pos.get("exchange_sl_price")
            sl_label = "Exch SL"
            if sl_val is None:
                sl_val = pos.get("stop_loss")
                sl_label = "SL"
            if sl_val:
                meta_parts.append(f"{sl_label} {sl_val:.6g}")
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


def _build_l2_monitor_panel() -> str:
    """Render the L2 Anticipation Signal Monitor panel from l2_snapshot.json."""
    import html as _html
    try:
        with open("l2_snapshot.json") as f:
            data = json.load(f)
    except FileNotFoundError:
        return (
            '<div class="glass-card dash-item" data-id="l2monitor">'
            '<h2>&#128225; L2 Anticipation Monitor</h2>'
            '<div class="muted">No L2 snapshot yet &mdash; bot is starting up.</div>'
            '</div>'
        )
    except Exception as e:
        return (
            '<div class="glass-card dash-item" data-id="l2monitor">'
            '<h2>&#128225; L2 Anticipation Monitor</h2>'
            f'<div class="muted">Snapshot unreadable &mdash; {_html.escape(str(e))}</div>'
            '</div>'
        )

    updated_at = data.get("updated_at", 0)
    age_sec = max(0, int(time.time() - updated_at))
    stale = age_sec > 120
    symbols = data.get("symbols", {})

    if not symbols:
        return (
            '<div class="glass-card dash-item" data-id="l2monitor">'
            '<h2>&#128225; L2 Anticipation Monitor</h2>'
            '<div class="muted">No symbols in snapshot.</div>'
            '</div>'
        )

    rows = []
    for sym in sorted(symbols.keys()):
        s = symbols[sym]
        tc = s.get("trade_count", 0) or 0
        short_sym = sym.split("/")[0]

        if tc < 5:
            rows.append(
                f'<tr><td>{_html.escape(short_sym)}</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">no feed</td></tr>'
            )
            continue

        br = s.get("buy_ratio")
        cvd = s.get("cvd_slope")
        bd = s.get("bid_depth_usdt") or 0
        ad = s.get("ask_depth_usdt") or 0
        lt = s.get("large_trade_bias", 0) or 0

        # Direction per signal: +1 long, -1 short, 0 neutral
        if br is None:
            br_cell, br_dir = '<span class="muted">&mdash;</span>', 0
        elif br > 0.55:
            br_cell, br_dir = f'<span class="l2-ok">{br:.2f}&#8593;</span>', 1
        elif br < 0.45:
            br_cell, br_dir = f'<span class="l2-ok">{br:.2f}&#8595;</span>', -1
        else:
            br_cell, br_dir = f'<span class="l2-fail">{br:.2f}</span>', 0

        if cvd is None:
            cvd_cell, cvd_dir = '<span class="muted">&mdash;</span>', 0
        elif cvd > 0.1:
            cvd_cell, cvd_dir = f'<span class="l2-ok">{cvd:+.2f}&#8593;</span>', 1
        elif cvd < -0.1:
            cvd_cell, cvd_dir = f'<span class="l2-ok">{cvd:+.2f}&#8595;</span>', -1
        else:
            cvd_cell, cvd_dir = f'<span class="l2-fail">{cvd:+.2f}</span>', 0

        if bd > 0 and ad > 0:
            ratio = bd / ad
            if ratio > 1.2:
                depth_cell, depth_dir = f'<span class="l2-ok">{ratio:.2f}&times;&#8593;</span>', 1
            elif ratio < 0.83:
                depth_cell, depth_dir = f'<span class="l2-ok">{ratio:.2f}&times;&#8595;</span>', -1
            else:
                depth_cell, depth_dir = f'<span class="l2-fail">{ratio:.2f}&times;</span>', 0
        else:
            depth_cell, depth_dir = '<span class="muted">&mdash;</span>', 0

        whale = '&#128011;' if abs(lt) > 0.2 else '&nbsp;'
        whale_cell = f'<span class="l2-whale">{whale} {lt:+.2f}</span>' if lt else f'<span>{whale}</span>'

        # Aligned direction: all 3 leaning same way (no opposites, at least 1 directional)
        dirs = [d for d in (br_dir, cvd_dir, depth_dir) if d != 0]
        long_count = sum(1 for d in dirs if d == 1)
        short_count = sum(1 for d in dirs if d == -1)
        if long_count == 3:
            ready_cell = '<span class="l2-ready">&#9989; LONG 3/3</span>'
        elif short_count == 3:
            ready_cell = '<span class="l2-ready">&#9989; SHORT 3/3</span>'
        elif long_count > 0 and short_count > 0:
            ready_cell = f'<span class="l2-partial">&#9888;&#65039; MIXED {long_count}L/{short_count}S</span>'
        elif long_count > 0:
            ready_cell = f'<span class="l2-partial">&#128992; LONG {long_count}/3</span>'
        elif short_count > 0:
            ready_cell = f'<span class="l2-partial">&#128992; SHORT {short_count}/3</span>'
        else:
            ready_cell = '<span class="l2-fail">&#128308; 0/3</span>'

        rows.append(
            f'<tr><td>{_html.escape(short_sym)}</td>'
            f'<td class="l2-cell">{br_cell}</td>'
            f'<td class="l2-cell">{cvd_cell}</td>'
            f'<td class="l2-cell">{depth_cell}</td>'
            f'<td class="l2-cell">{whale_cell}</td>'
            f'<td class="l2-cell">{ready_cell}</td></tr>'
        )

    stale_banner = ''
    if stale:
        stale_banner = (
            f'<div class="l2-stale">Snapshot stale &mdash; last update {age_sec}s ago</div>'
        )

    table_html = (
        '<table class="l2-table">'
        '<thead><tr>'
        '<th>Symbol</th>'
        '<th>buy_ratio</th>'
        '<th>cvd_slope</th>'
        '<th>depth b/a</th>'
        '<th>whale</th>'
        '<th>READY</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
    )

    return (
        '<div class="glass-card dash-item" data-id="l2monitor">'
        '<h2>&#128225; L2 Anticipation Monitor</h2>'
        f'<div class="muted">Live snapshot &mdash; updated {age_sec}s ago</div>'
        f'{stale_banner}'
        f'{table_html}'
        '</div>'
    )


# ── Ticker helpers (Terminal Pro shell) ─────────────────────────────────
def _latest_balance(lines: list = None) -> float:
    """Last 'Balance: X USDT' from the bot-log STATS lines (the state JSON has
    no balance field). 0.0 if unavailable.
    Pass pre-fetched log lines to avoid a redundant tail_log call."""
    try:
        src = lines if lines is not None else tail_log(2000)
        for line in reversed(src):
            m = re.search(r'Balance: ([\d.]+) USDT', line)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return 0.0


def _today_net_pnl(state: dict) -> float:
    """Sum of NET pnl for main-state trades closed today (PT midnight onward)."""
    try:
        today_start = _now_ca().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return sum(_net_pnl(t) for t in state.get("closed_trades", [])
                   if t.get("closed_at", 0) >= today_start)
    except Exception:
        return 0.0


def _drawdown_pct(state: dict, balance: float = 0.0) -> float:
    """Current drawdown from peak balance, in percent (always >= 0)."""
    try:
        peak = state.get("peak_balance", 0) or 0
        bal = balance or _latest_balance()
        if peak > 0 and bal > 0:
            return max(0.0, (peak - bal) / peak * 100)
    except Exception:
        pass
    return 0.0


def _mr_headroom():
    """Demote headroom for the live 5m_mean_revert slot: $5 budget + net PnL of
    its LIVE-mode trades. None when the slot is paper (or files unreadable) —
    the ticker omits the segment entirely in that case."""
    try:
        with open(os.path.join(PROJECT_DIR, "trading_state_5m_mean_revert_mode.json")) as f:
            if json.load(f).get("paper_mode", True):
                return None
        with open(os.path.join(PROJECT_DIR, "trading_state_5m_mean_revert.json")) as f:
            trades = json.load(f).get("closed_trades", []) or []
        live_net = sum(_net_pnl(t) for t in trades if t.get("mode") == "live")
        return 5.0 + live_net
    except Exception:
        return None


def _watcher_enabled() -> bool:
    """True if '[LIVE EXIT] watcher enabled' was logged AFTER the most recent
    'Volume scanner ON' line (i.e. after the last bot start). Reads the last
    ~200KB of bot.log; falls back to a full-file grep when the startup markers
    have scrolled out of the tail window (long-running bot). Result cached 30s."""
    now = time.time()
    if now - _watcher_cache["ts"] < 30 and _watcher_cache["v"] is not None:
        return _watcher_cache["v"]
    result = False
    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 200_000))
            text = f.read().decode("utf-8", errors="replace")
        idx = text.rfind("Volume scanner ON")
        if idx != -1:
            result = "[LIVE EXIT] watcher enabled" in text[idx:]
        elif "[LIVE EXIT] watcher enabled" in text:
            # watcher line in the tail with no later scanner restart → enabled
            result = True
        else:
            # Neither marker in the tail window — grep the whole file (fast C grep).
            out = subprocess.run(
                ["grep", "-F", "-n", "-e", "Volume scanner ON",
                 "-e", "[LIVE EXIT] watcher enabled", LOG_FILE],
                capture_output=True, text=True, timeout=5,
            ).stdout
            last_scan = last_watch = -1
            for ln in out.splitlines():
                no, _, rest = ln.partition(":")
                if not no.isdigit():
                    continue
                if "Volume scanner ON" in rest:
                    last_scan = int(no)
                elif "[LIVE EXIT] watcher enabled" in rest:
                    last_watch = int(no)
            result = last_watch != -1 and last_watch > last_scan
    except Exception:
        pass
    _watcher_cache["v"] = result
    _watcher_cache["ts"] = now
    return result


def _latest_cycle(lines: list = None) -> str:
    """Most recent cycle number from the log tail ('—' if unknown).
    Pass pre-fetched log lines to avoid a redundant tail_log call."""
    try:
        src = lines if lines is not None else tail_log(500)
        for line in reversed(src):
            m = re.search(r'Cycle #(\d+)', line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return "—"


def _open_pos_count() -> int:
    """Open positions across main state + live-promoted slot state files."""
    count = 0
    try:
        count += len(read_state().get("positions") or {})
        for slot_id in _live_slot_ids():
            if slot_id == "5m_scalp":
                continue  # main trading_state.json already counted above
            try:
                with open(os.path.join(PROJECT_DIR, f"trading_state_{slot_id}.json")) as f:
                    count += len(json.load(f).get("positions") or {})
            except Exception:
                pass
    except Exception:
        pass
    return count


def build_ticker(lines: list = None) -> str:
    """One-line sticky status ticker (12-hour PT, NET basis).
    Pass pre-fetched log lines to avoid redundant tail_log calls per poll."""
    # all log-derived strings must be escape()d (innerHTML sink)
    state = read_state()
    bal = _latest_balance(lines)
    today = _today_net_pnl(state)
    arrow = "▲" if today >= 0 else "▼"
    cls = "pos" if today >= 0 else "neg"
    hdrm = _mr_headroom()
    watcher = "ON" if _watcher_enabled() else "OFF"
    now = escape(_now_ca().strftime("%-I:%M:%S %p PT"))
    parts = ["PHMEX-S",
             f"BAL ${bal:.2f} <span class='{cls}'>{escape(arrow)}{abs(today):.2f}</span>"]
    if hdrm is not None:
        parts.append(f"MR-LIVE HDRM ${hdrm:.2f}")
    parts += [
        f"DD {_drawdown_pct(state, bal):.1f}%",
        f"POS {_open_pos_count()}",
        f"WATCHER <span class='{'pos' if watcher == 'ON' else 'neg'}'>{escape(watcher)}</span>",
        f"CYC {escape(_latest_cycle(lines))}",
        now,
    ]
    return " ▮ ".join(parts)


def build_feed(lines: list = None) -> str:
    """FEED panel inner HTML — extracted from the old Activity Feed card
    (same event parsing, terminal-pro classes).
    Pass pre-fetched log lines to avoid a redundant tail_log call."""
    try:
        src = lines if lines is not None else tail_log(3000)
        activity = get_recent_activity(src, n=15)
    except Exception:
        activity = []
    rows = ""
    for line in activity:
        trimmed = escape(line[:140] + "..." if len(line) > 140 else line)
        cls = ("pos" if "ENTRY:" in line else
               "amb" if "closed:" in line else
               "dim" if any(k in line for k in ("REGIME", "DRAWDOWN", "SCANNER")) else "")
        rows += f"<div class='feed-line {cls}'>{trimmed}</div>"
    if not rows:
        rows = "<div class='feed-line dim'>No recent activity</div>"
    return f'<div class="ptitle">FEED</div><div class="feed-scroll">{rows}</div>'


# ── HTML rendering ───────────────────────────────────────────────────────
def _build_blotter_panel(limit: int = 100) -> str:
    """BLOTTER panel body: merged main+slot rows, newest first, click-to-drill.
    Slot rows carry an owner badge — amber when the slot trade ran LIVE, dim
    for paper. Row ids feed drill() → GET /api/trade?id=owner:index."""
    rows = collect_blotter_rows(limit)
    if not rows:
        return "<div class='dim'>no closed trades yet</div>"
    out = ("<table><tr class='dim'><th>TIME</th><th>SYM</th><th>SIDE</th>"
           "<th>STRAT</th><th>PNL</th><th>REASON</th></tr>")
    for r in rows:
        net_cls = "pos" if r["net"] >= 0 else "neg"
        side = r["side"][:1].upper()
        side = {"L": "LNG", "S": "SHT"}.get(side, escape(r["side"][:3].upper()))
        side_cls = "pos" if side == "LNG" else "neg"
        badge = ""
        if r["owner"] != "main":
            b_cls = "amb" if r["mode"] == "live" else "dim"
            badge = f" <span class='{b_cls}'>[{escape(r['owner'])}]</span>"
        # id is generated server-side as owner:index ([A-Za-z0-9_:] only) — safe in attr
        out += (
            f"<tr onclick=\"drill(this,'{r['id']}')\" style='cursor:pointer'>"
            f"<td>{escape(r['time_pt'])}</td>"
            f"<td>{escape(r['sym'])}{badge}</td>"
            f"<td class='{side_cls}'>{side}</td>"
            f"<td class='dim'>{escape(r['strat'][:16])}</td>"
            f"<td class='{net_cls}'>{r['net']:+.2f}</td>"
            f"<td class='dim'>{escape(r['reason'][:14])}</td></tr>"
        )
    return out + "</table>"


def build_content(lines: list = None) -> str:
    """Inner HTML for the swapped #content node — the six-panel command grid.

    Task 1 shell: the SLOTS and GATES+WATCHLIST cells temporarily carry the
    legacy builders forward so the dashboard stays useful between tasks;
    Tasks 3-6 replace each placeholder with its terminal-pro builder.
    Pass pre-fetched log lines to avoid a redundant tail_log call.
    """
    state = read_state()
    positions = state.get("positions") or {}
    trades = state.get("closed_trades", [])
    factory_state = read_factory_state()
    all_slot_states = read_all_slot_states()
    sentinels = detect_sentinel_files()
    lines = lines if lines is not None else tail_log(3000)
    watchlist = parse_watchlist(lines)

    # Panel 1 — POSITIONS (full terminal-pro rebuild in Task 5)
    pos_rows = []
    for owner in sorted(_live_slot_ids()):
        if owner == "5m_scalp":
            src = positions
        else:
            try:
                with open(os.path.join(PROJECT_DIR, f"trading_state_{owner}.json")) as f:
                    src = json.load(f).get("positions") or {}
            except Exception:
                src = {}
        for sym, p in src.items():
            short = escape(str(sym).replace("/USDT:USDT", ""))
            side = str(p.get("side", "?"))[:5].upper()
            side_cls = "pos" if side.startswith("L") else "neg"
            entry = p.get("entry_price") or 0
            sl = p.get("exchange_sl_price") or p.get("stop_loss") or 0
            tp = p.get("take_profit") or 0
            opened = p.get("opened_at") or 0
            age = f"{(time.time() - opened) / 60:.0f}m" if opened else "&mdash;"
            pos_rows.append(
                f"<tr><td>{short}</td><td class='{side_cls}'>{side}</td>"
                f"<td>{entry:.6g}</td><td>{sl:.6g}</td><td>{tp:.6g}</td>"
                f"<td>{age}</td><td class='dim'>{escape(str(p.get('strategy', '')))}</td>"
                f"<td class='dim'>{escape(owner)}</td></tr>"
            )
    if pos_rows:
        positions_html = (
            "<table><tr class='dim'><th>SYM</th><th>SIDE</th><th>ENTRY</th><th>SL</th>"
            "<th>TP</th><th>AGE</th><th>STRAT</th><th>OWNER</th></tr>"
            + "".join(pos_rows) + "</table>"
        )
    else:
        last_line = ""
        if trades:
            lt = trades[-1]
            try:
                t_pt = _from_ts(lt.get("closed_at", 0)).strftime("%-I:%M %p")
            except Exception:
                t_pt = "?"
            net = _net_pnl(lt)
            net_cls = "pos" if net >= 0 else "neg"
            last_line = (
                f"<div class='dim' style='margin-top:6px'>last: "
                f"{escape(str(lt.get('symbol', '?')).replace('/USDT:USDT', ''))} "
                f"{escape(str(lt.get('side', '?'))[:3].upper())} closed {t_pt} "
                f"<span class='{net_cls}'>{net:+.2f}</span></div>"
            )
        positions_html = "<div class='dim'>flat &mdash; no open positions</div>" + last_line

    # Panel 2 — SLOTS + GUARDRAILS (legacy builder carried forward; Task 5 rebuilds)
    slots_html = _build_slots_overview(all_slot_states, factory_state, sentinels)

    # Panel 3 — BLOTTER: main + all slots merged, click a row to drill down.
    blotter_html = _build_blotter_panel()

    # Panel 5 — GATES + WATCHLIST (legacy builders carried forward; Task 6 rebuilds)
    gates_html = _build_observability_panel() + _build_watchlist_html(watchlist, positions)

    return f"""<div id="grid">
    <div class="panel" id="p-positions">
        <div class="ptitle">POSITIONS &mdash; MAIN + SLOTS</div>
        {positions_html}
    </div>
    <div class="panel" id="p-slots">
        <div class="ptitle">SLOTS + GUARDRAILS</div>
        {slots_html}
    </div>
    <div class="panel" id="p-blotter">
        <div class="ptitle">BLOTTER &mdash; CLICK ROW TO DRILL DOWN</div>
        {blotter_html}
    </div>
    <div class="panel" id="p-why">
        <div class="ptitle">WHY NO TRADES?</div>
        <div class="dim">live diagnostics land in Task 4</div>
    </div>
    <div class="panel" id="p-gates">
        <div class="ptitle">GATES 24H + WATCHLIST</div>
        {gates_html}
    </div>
    <div class="panel" id="p-reserved">
        <div class="ptitle">RESERVED</div>
        <div class="dim">equity chart renders below the grid</div>
    </div>
</div>"""


def build_html() -> str:
    """Full HTML page shell — sticky ticker / swapped #content grid /
    static #equity-root (outside the swap) / #feed."""
    ticker = build_ticker()
    content = build_content()
    feed = build_feed()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PHMEX-S &mdash; Terminal</title>
<link rel="stylesheet" href="/static/uplot.min.css">
<script src="/static/uplot.iife.min.js"></script>
<style>
:root {{
  --bg:#000204; --panel:#0a0e08; --border:#2d3a1e; --txt:#9eb89e;
  --amber:#f0a500; --pos:#4af626; --neg:#ff5555; --dim:#5a6b5a;
  /* TEMP aliases for legacy panel fragments carried into the grid — removed in Tasks 5-6 */
  --accent:#f0a500; --positive:#4af626; --negative:#ff5555; --warning:#f0a500;
  --text-primary:#9eb89e; --text-secondary:#9eb89e; --text-dim:#5a6b5a;
  --panel-bg:#0a0e08; --panel-border:#2d3a1e; --border-subtle:#2d3a1e; --hover-bg:#0a0e08;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--txt);
  font:11px/1.5 'SF Mono', Menlo, 'JetBrains Mono', monospace; }}
#ticker {{ position:sticky; top:0; z-index:10; background:var(--panel);
  color:var(--amber); border-bottom:1px solid var(--border);
  padding:5px 10px; white-space:nowrap; overflow:hidden; font-size:12px; }}
#grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:3px; padding:3px; }}
.panel {{ background:var(--panel); border:1px solid var(--border); padding:6px;
  min-height:120px; overflow-y:auto; max-height:46vh; }}
.panel .ptitle {{ color:var(--amber); letter-spacing:1.5px; font-size:9px;
  text-transform:uppercase; border-bottom:1px solid #1a2412;
  padding-bottom:3px; margin-bottom:5px; }}
.panel table {{ width:100%; border-collapse:collapse; font-size:10px; }}
.panel td, .panel th {{ padding:1px 5px 1px 0; text-align:left; }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .dim {{ color:var(--dim); }}
.amb {{ color:var(--amber); }}
#feed {{ margin:0 3px 3px; }}
.feed-scroll {{ max-height:150px; overflow-y:auto; }}
.feed-line {{ padding:1px 0; color:var(--txt); font-size:10px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.feed-line.pos {{ color:var(--pos); }} .feed-line.amb {{ color:var(--amber); }}
.feed-line.dim {{ color:var(--dim); }}
.footer {{ color:var(--dim); font-size:9px; padding:4px 10px 8px; }}
/* TEMP compat for legacy fragments (slots overview, gate table, watchlist) — Tasks 5-6 remove */
.positive {{ color:var(--pos); }} .negative {{ color:var(--neg); }} .muted {{ color:var(--dim); }}
.glass-card {{ margin-bottom:6px; }}
.glass-card h2 {{ color:var(--amber); font-size:9px; letter-spacing:1px;
  text-transform:uppercase; font-weight:600; margin:4px 0; }}
.watchlist-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); gap:3px; }}
.wl-item {{ border:1px solid var(--border); padding:3px 5px; font-size:10px; }}
.wl-item .meta {{ color:var(--dim); font-size:9px; }}
.wl-score {{ color:var(--amber); margin-left:4px; }}
.dot {{ display:inline-block; width:6px; height:6px; border-radius:50%; margin-right:4px; background:var(--dim); }}
.dot-open {{ background:var(--pos); }} .dot-scanner {{ background:var(--amber); }} .dot-base {{ background:var(--dim); }}
.era-btn {{ background:none; border:1px solid var(--border); color:var(--dim);
  font:inherit; font-size:9px; letter-spacing:1px; padding:0 6px; cursor:pointer; }}
.era-btn.active {{ color:var(--amber); border-color:var(--amber); }}
#equity-chart {{ position:relative; }}
#eqtip {{ position:absolute; display:none; pointer-events:none; z-index:20;
  background:var(--panel); border:1px solid var(--amber); color:var(--txt);
  padding:3px 6px; font-size:10px; white-space:nowrap; }}
</style>
</head>
<body>
<div id="ticker">{ticker}</div>
<div id="content">{content}</div><!-- /content -->
<div class="panel" id="equity-root" style="margin:0 3px;">
    <div class="ptitle"><span id="eq-title">EQUITY &mdash; loading&hellip;</span>
        <span style="float:right">
            <button class="era-btn active" id="era-sentinel" onclick="setEra('sentinel')">SENTINEL</button>
            <button class="era-btn" id="era-all" onclick="setEra('all')">ALL</button>
        </span>
    </div><div id="equity-chart"></div>
</div>
<div id="feed" class="panel">{feed}</div>
<div class="footer">Auto-refresh 3s &middot; Equity 30s &middot; Read-only &middot; Zero API calls &middot; NET basis</div>
<script>
async function poll(){{
  try{{
    const r = await fetch('/api/content'); const j = await r.json();
    document.getElementById('ticker').innerHTML = j.ticker;
    document.getElementById('content').innerHTML = j.content;
    document.getElementById('feed').innerHTML = j.feed;
  }}catch(e){{}}
}}
setInterval(poll, 3000); poll();

// ── Blotter drill-down. NOTE: #content is replaced wholesale every 3s, so
// an expanded row collapses on the next poll — acceptable for v1. ──
function escq(v){{ return String(v==null?'':v).replace(/&/g,'&amp;')
  .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
async function drill(tr, id){{
  const next = tr.nextElementSibling;
  if(next && next.dataset && next.dataset.drill === id){{ next.remove(); return; }}
  let d;
  try{{
    const r = await fetch('/api/trade?id='+encodeURIComponent(id));
    d = await r.json();
  }}catch(e){{ return; }}
  const tbl = tr.closest('table');
  if(tbl) tbl.querySelectorAll('tr[data-drill]').forEach(x=>x.remove());
  let body;
  if(d.error){{
    body = '<span class="neg">'+escq(d.error)+'</span>';
  }}else{{
    const t=d.trade||{{}}, f=d.fees||{{}}, s=d.snapshot, bits=[];
    if(t.confidence!=null) bits.push('conf '+escq(t.confidence)+'/7'+
      (t.layers?' ['+escq(t.layers)+']':''));
    if(s && typeof s==='object'){{
      const fl=s.flow||{{}}, ob=s.ob||{{}};
      if(fl.buy_ratio!=null) bits.push('buy_ratio '+escq(fl.buy_ratio));
      if(fl.cvd_slope!=null) bits.push('cvd_slope '+escq(fl.cvd_slope));
      if(fl.large_trade_bias!=null) bits.push('lt_bias '+escq(fl.large_trade_bias));
      if(ob.imbalance!=null) bits.push('ob_imb '+escq(ob.imbalance));
    }}else{{
      bits.push(escq(s));  // "no snapshot recorded"
    }}
    if(d.gate_tags) bits.push('tags: '+escq(d.gate_tags));
    const fee = (typeof f.fees_usdt==='number') ? '$'+f.fees_usdt.toFixed(4) : escq(f.fees_usdt);
    bits.push('fees '+fee+(f.fees_source?' ('+escq(f.fees_source)+')':'')+
      ' · '+escq(d.basis)+' basis');
    if(t.entry_price!=null) bits.push('entry '+escq(t.entry_price)+' → exit '+escq(t.exit_price));
    body = '<span class="amb">▼ SNAPSHOT</span> <span class="dim">'+bits.join(' · ')+'</span>';
  }}
  const row = document.createElement('tr');
  row.dataset.drill = id;
  // every dynamic value above went through escq() — safe innerHTML sink
  row.innerHTML = '<td colspan="6" style="border-left:2px solid #f0a500;'+
    'padding:3px 6px;background:#0a0e08;">'+body+'</td>';
  tr.after(row);
}}

// ── Equity chart (uPlot, vendored at /static/, refreshed every 30s) ──
let plot=null, era='sentinel', eqMeta=[];
async function loadEquity(){{
  const title=document.getElementById('eq-title');
  try{{
    if(typeof uPlot==='undefined') throw new Error('uPlot not loaded');
    const r=await fetch('/api/equity?era='+era); const d=await r.json();
    eqMeta=d.meta;
    const node=document.getElementById('equity-chart');
    const opts={{width:node.clientWidth||800,
      height:180, scales:{{x:{{time:true}}}},
      series:[{{}}, {{label:'NET PnL', stroke:'#f0a500', width:1.5,
        points:{{show:true, size:5,
          fill:(u,si,i)=> eqMeta[i] && eqMeta[i].win ? '#4af626' : '#ff5555'}}}}],
      axes:[{{stroke:'#5a6b5a',grid:{{stroke:'#1a2412'}}}},{{stroke:'#5a6b5a',grid:{{stroke:'#1a2412'}}}}],
      cursor:{{}}, legend:{{show:false}}}};
    if(plot){{ plot.destroy(); plot=null; }}
    node.innerHTML='';
    plot=new uPlot(opts,[d.t,d.v],node);
    // tooltip: absolutely-positioned div fed from meta at the cursor's idx
    const tip=document.createElement('div'); tip.id='eqtip'; node.appendChild(tip);
    plot.over.addEventListener('mousemove', ()=>{{
      const i=plot.cursor.idx;
      if(i==null || !eqMeta[i]){{ tip.style.display='none'; return; }}
      const m=eqMeta[i], sign=m.pnl>=0?'+':'';
      tip.innerHTML=m.time_pt+' &middot; '+m.sym+' &middot; '+m.strat+
        ' &middot; <span class="'+(m.win?'pos':'neg')+'">'+sign+m.pnl.toFixed(2)+'</span>'+
        (m.reason?' &middot; '+m.reason:'');
      tip.style.display='block';
      tip.style.left=Math.min(plot.cursor.left+14, Math.max(0,node.clientWidth-260))+'px';
      tip.style.top=(plot.cursor.top+12)+'px';
    }});
    plot.over.addEventListener('mouseleave', ()=>{{ tip.style.display='none'; }});
    document.getElementById('era-sentinel').classList.toggle('active', era==='sentinel');
    document.getElementById('era-all').classList.toggle('active', era==='all');
    title.textContent='EQUITY — CUMULATIVE NET PNL ('+era.toUpperCase()+' · '+d.t.length+' trades)';
  }}catch(e){{ title.textContent='EQUITY — chart assets missing'; }}
}}
function setEra(e){{ era=e; loadEquity(); }}
loadEquity(); setInterval(loadEquity, 30000);
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
            _lines = tail_log(3000)  # single log tail for the entire poll
            payload = json.dumps({
                "ticker": build_ticker(_lines),
                "content": build_content(_lines),
                "feed": build_feed(_lines),
            })
            data = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/trades" or self.path.startswith("/trades?"):
            # The standalone trades page is gone — the merged blotter on the
            # main dashboard replaced it (Task 3).
            self.send_response(301)
            self.send_header("Location", "/")
            self.end_headers()
        elif self.path.startswith("/api/trade"):
            qs = parse_qs(urlparse(self.path).query)
            tid = (qs.get("id") or [""])[0]
            data = json.dumps(build_trade_detail(tid)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/api/equity"):
            era = "sentinel"
            if "era=" in self.path:
                era = self.path.split("era=", 1)[1].split("&")[0]
            if era not in ("sentinel", "all"):
                era = "sentinel"
            data = json.dumps(build_equity_series(era)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/static/"):
            # Serve ONLY the two vendored uPlot files. basename() kills any
            # path-traversal attempt; the whitelist kills everything else.
            name = os.path.basename(self.path.split("?")[0])
            ctype = STATIC_FILES.get(name)
            data = b""
            if ctype:
                try:
                    with open(os.path.join(STATIC_DIR, name), "rb") as f:
                        data = f.read()
                except OSError:
                    data = b""
            if data:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
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
