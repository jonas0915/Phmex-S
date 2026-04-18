#!/usr/bin/env python3
"""
Phmex-S HTML Dashboard — read-only web monitor.
Reads trading_state.json and bot.log only. Zero API calls, zero bot imports.

Usage:  python web_dashboard.py
Open:   http://127.0.0.1:8050
"""
import io
import glob as _glob
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CA_TZ = ZoneInfo("America/Los_Angeles")

def _now_ca():
    return datetime.now(CA_TZ)

def _from_ts(ts):
    return datetime.fromtimestamp(ts, CA_TZ)
from collections import defaultdict
from html import escape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import matplotlib
matplotlib.use("Agg")  # MUST be before pyplot import
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_DIR, "trading_state.json")
PAPER_STATE_FILE = os.path.join(PROJECT_DIR, "trading_state_5m_liq_cascade.json")
FACTORY_STATE_FILE = os.path.join(PROJECT_DIR, "strategy_factory_state.json")
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "bot.log")
HOST = "127.0.0.1"
PORT = 8050
CHART_INTERVAL = 30  # seconds between chart refreshes
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# ── Chart cache ──────────────────────────────────────────────────────────
_chart_cache = {}  # name -> PNG bytes
_chart_lock = threading.Lock()


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


def read_factory_state() -> dict:
    """Read strategy factory state. Returns empty structure if missing."""
    try:
        with open(FACTORY_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"strategies": {}, "pipeline_log": []}


def read_all_slot_states() -> dict[str, dict]:
    """Discover and read all trading_state_*.json files. Returns {slot_id: state_dict}."""
    slots = {}
    for path in _glob.glob(os.path.join(PROJECT_DIR, "trading_state_*.json")):
        fname = os.path.basename(path)
        # Extract slot_id: trading_state_5m_liq_cascade.json → 5m_liq_cascade
        slot_id = fname.replace("trading_state_", "").replace(".json", "")
        try:
            with open(path, "r") as f:
                slots[slot_id] = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            slots[slot_id] = {"peak_balance": 0, "closed_trades": []}
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
    """Build performance audit with breakdowns and collapsible trade log."""
    if not trades:
        return '<div style="color:#7e8aa0;text-align:center;padding:20px">No trades to audit</div>'

    # Collect stats
    pair_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    strat_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    exit_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})
    side_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0})

    for t in trades:
        pnl = _net_pnl(t)
        sym = t.get("symbol", "?").replace("/USDT:USDT", "")
        strat = t.get("strategy", "") or ""
        if not strat or strat in ("unknown", "synced"):
            strat = "pre-tracking"
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

    recent_rows = ""
    for i, t in enumerate(reversed(trades[-30:])):
        trade_num = len(trades) - i
        recent_rows += _build_trade_row(t, trade_num, len(trades))

    older_rows = ""
    if len(trades) > 30:
        for i, t in enumerate(reversed(trades[:-30])):
            trade_num = len(trades) - 30 - i
            older_rows += _build_trade_row(t, trade_num, len(trades))

    log_header = '<thead><tr><th>#</th><th>Ver</th><th>Side</th><th>Pair</th><th>PnL</th><th>ROI</th><th>Exit</th><th>Dur</th><th>Closed</th></tr></thead>'

    older_section = ""
    if older_rows:
        older_section = f'''
        <details style="margin-top:8px">
            <summary style="cursor:pointer;color:var(--accent);font-size:0.8em;font-weight:500;padding:6px 0">Show {len(trades)-30} older trades</summary>
            <div class="table-wrap" style="max-height:400px;overflow-y:auto">
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
        <div style="font-size:0.72em;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Recent Trades ({min(30,len(trades))} of {len(trades)})</div>
        <div class="table-wrap" style="max-height:350px;overflow-y:auto">
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

    return f'''<div class="glass-card dash-item" data-id="sessions">
        <h2>Sessions</h2>
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
}

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
        stage = strat_info.get("stage", "unknown")

        # Override stage if sentinel files active
        if slot_id in sentinels.get("kills", []):
            stage = "killed"
        elif slot_id in sentinels.get("pauses", []):
            stage = "paused"
        elif slot_id in sentinels.get("promotes", []):
            stage = "promoting"
        elif slot_id in sentinels.get("demotes", []):
            stage = "demoting"

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
    pipeline = factory.get("pipeline_log", [])
    log_html = ""
    if pipeline:
        for entry in pipeline[-5:]:
            ts = entry.get("time", "")[:16].replace("T", " ")
            log_html += f'<div style="font-size:0.68em;color:var(--text-dim);padding:2px 0;font-family:\'JetBrains Mono\',monospace">{ts} — {escape(entry.get("strategy", ""))} — {escape(entry.get("event", ""))}</div>'
        log_html = f'<div class="compare-section-title" style="margin-top:10px">Pipeline Log</div>{log_html}'

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
    pnls = [_net_pnl(t) for t in trades]
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
    ax.set_title("Cumulative PnL (net)", color="#cdd6f4", fontsize=13)
    ax.tick_params(colors="#a6adc8")
    ax.grid(True, alpha=0.15, color="#585b70")
    for spine in ax.spines.values():
        spine.set_color("#585b70")
    return _fig_to_png(fig)



def _make_pnl_by_reason(trades: list[dict]) -> bytes:
    if not trades:
        return b""
    reason_pnl = defaultdict(float)
    reason_count = defaultdict(int)
    for t in trades:
        r = t.get("exit_reason") or t.get("reason") or "unknown"
        reason_pnl[r] += _net_pnl(t)
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







def refresh_charts():
    """Regenerate all charts and cache as PNG bytes."""
    state = read_state()
    trades = state.get("closed_trades", [])
    charts = {}
    if trades:
        charts["cumulative_pnl"] = _make_cumulative_pnl(trades)
        charts["pnl_by_reason"] = _make_pnl_by_reason(trades)
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

        if br is None:
            br_cell, br_pass = '<span class="muted">&mdash;</span>', False
        elif br > 0.55 or br < 0.45:
            br_cell = f'<span class="l2-ok">{br:.2f}</span>'
            br_pass = True
        else:
            br_cell = f'<span class="l2-fail">{br:.2f}</span>'
            br_pass = False

        if cvd is None:
            cvd_cell, cvd_pass = '<span class="muted">&mdash;</span>', False
        elif abs(cvd) > 0.1:
            cvd_cell = f'<span class="l2-ok">{cvd:+.2f}</span>'
            cvd_pass = True
        else:
            cvd_cell = f'<span class="l2-fail">{cvd:+.2f}</span>'
            cvd_pass = False

        if bd > 0 and ad > 0:
            ratio = bd / ad
            if abs(ratio - 1.0) > 0.2:
                depth_cell = f'<span class="l2-ok">{ratio:.2f}&times;</span>'
                depth_pass = True
            else:
                depth_cell = f'<span class="l2-fail">{ratio:.2f}&times;</span>'
                depth_pass = False
        else:
            depth_cell, depth_pass = '<span class="muted">&mdash;</span>', False

        whale = '&#128011;' if abs(lt) > 0.2 else '&nbsp;'
        whale_cell = f'<span class="l2-whale">{whale} {lt:+.2f}</span>' if lt else f'<span>{whale}</span>'

        passing = sum([br_pass, cvd_pass, depth_pass])
        if passing == 3:
            ready_cell = '<span class="l2-ready">&#9989; 3/3</span>'
        elif passing >= 1:
            ready_cell = f'<span class="l2-partial">&#128992; {passing}/3</span>'
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


# ── HTML rendering ───────────────────────────────────────────────────────
def build_content() -> str:
    """Build just the inner content HTML (no head/style/script shell)."""
    state = read_state()
    trades = state.get("closed_trades", [])
    stats = compute_stats(trades)
    paper_state = read_paper_state()
    paper_trades = paper_state.get("closed_trades", [])
    factory_state = read_factory_state()
    all_slot_states = read_all_slot_states()
    sentinels = detect_sentinel_files()
    lines = tail_log(500)
    cycle = parse_latest_cycle(lines)
    regime = parse_regime_status(lines)
    activity = get_recent_activity(lines, n=15)
    # Watchlist needs more history to capture position opens/closes and scanner updates
    wl_lines = tail_log(3000)
    watchlist = parse_watchlist(wl_lines)
    now = _now_ca().strftime("%I:%M:%S %p")
    date_str = _now_ca().strftime("%b %d, %Y")

    # Read balance snapshots from bot log STATS lines (tail only — avoid full scan)
    balance = 0
    balance_start_of_day = 0
    _log_file = os.path.join(os.path.dirname(__file__), "logs", "bot.log")
    _today_date_str = _now_ca().strftime("%Y-%m-%d")
    if os.path.exists(_log_file):
        try:
            _tail_lines = subprocess.check_output(
                ["tail", "-n", "2000", _log_file], text=True, errors="replace"
            ).splitlines()
        except Exception:
            _tail_lines = []
        _first_today = False
        for _ln in _tail_lines:
            _m2 = re.search(r'Balance: ([\d.]+) USDT', _ln)
            if _m2:
                _bv = float(_m2.group(1))
                balance = _bv
                if not _first_today and _today_date_str in _ln:
                    balance_start_of_day = _bv
                    _first_today = True
        if balance_start_of_day == 0:
            balance_start_of_day = balance

    audit_html = build_audit_table(trades)
    paper_html = _build_paper_comparison(trades, paper_trades)
    slots_html = _build_slots_overview(all_slot_states, factory_state, sentinels)

    session_html = _build_session_card(trades, paper_trades, balance=balance, balance_start=balance_start_of_day)

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
            <div class="chart-box"><img src="/chart/pnl_by_reason" alt="PnL by Reason"></div>
        </div>"""
    else:
        chart_section = '<div class="glass-card" style="text-align:center;padding:40px"><p style="color:#7e8aa0">No trades yet — charts appear after first closed trade</p></div>'

    # Daily stats
    today_start = _now_ca().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    # Use closed_at for TODAY so trade count and balance delta reconcile
    # (balance delta is cash-basis = realized PnL settled today)
    today_trades = [t for t in trades if t.get("closed_at", 0) >= today_start]
    has_daily = any(t.get("opened_at", 0) > 0 or t.get("closed_at", 0) > 0 for t in trades)
    daily_pnl = sum(_net_pnl(t) for t in today_trades)  # net (post-fees)
    daily_fees = sum(_real_fee(t) for t in today_trades)
    daily_real_pnl = daily_pnl  # already net
    daily_count = len(today_trades)
    daily_wins = sum(1 for t in today_trades if _net_pnl(t) > 0)
    daily_wr = (daily_wins / daily_count * 100) if daily_count > 0 else 0
    current_balance = balance if balance > 0 else state.get("peak_balance", 0)
    daily_pct = (daily_pnl / (current_balance - daily_pnl) * 100) if has_daily and (current_balance - daily_pnl) > 0 else 0

    balance_change = balance - balance_start_of_day

    # Current drawdown from peak (use actual balance, not cumulative PnL)
    peak_bal = state.get("peak_balance", 0)
    if peak_bal > 0 and current_balance > 0:
        current_dd = max(0, peak_bal - current_balance)
        current_dd_pct = (current_dd / peak_bal * 100)
    else:
        current_dd = 0
        current_dd_pct = 0

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
    bal_change_cls = "positive" if balance_change >= 0 else "negative"

    return f"""
<!-- Top bar -->
<div class="top-bar">
    <div class="top-left">
        <div class="logo">PHMEX-S</div>
        <div class="logo-sub">Trading Desk</div>
    </div>
    <div class="top-center">
        <span class="regime-badge {regime_cls}">{escape(regime)}</span>
    </div>
    <div class="top-right">
        <div class="clock">{now}</div>
        <div class="date">{date_str} &middot; {escape(cycle)}</div>
    </div>
</div>

<!-- Status bar -->
<div class="status-bar">
    <div class="status-item">
        <span class="status-label">BAL</span>
        <span class="status-value">${balance:.2f}</span>
        <span class="status-sub">pk ${state.get('peak_balance',0):.2f}</span>
    </div>
    <div class="status-item">
        <span class="status-label">TODAY</span>
        <span class="status-value {bal_change_cls}">${balance_change:+.2f}</span>
        <span class="status-sub">{daily_count}t {daily_wr:.0f}%</span>
    </div>
    <div class="status-item">
        <span class="status-label">ALL</span>
        <span class="status-value {pnl_cls}">${stats['total_pnl']:+.2f}</span>
        <span class="status-sub">{stats['wins']}W/{stats['losses']}L {stats['win_rate']:.0f}%</span>
    </div>
    <div class="status-item">
        <span class="status-label">DD</span>
        <span class="status-value negative">${current_dd:.2f}</span>
        <span class="status-sub">{current_dd_pct:.1f}%</span>
    </div>
</div>

<!-- 3-column grid -->
<div class="dash-grid" id="dash-grid">
    <!-- Left column: Slots, Sessions -->
    <div class="dash-col">
        {slots_html}
        {session_html}
    </div>

    <!-- Center column: Charts, Audit + Trade Log -->
    <div class="dash-col">
        {chart_section}
        <div class="glass-card dash-item" data-id="audit">
            <h2>Performance Audit</h2>
            <div class="perf-summary">
                <div class="perf-summary-item"><span class="stat-label">Avg Win</span><span class="stat-value positive">${stats['avg_win']:.2f}</span></div>
                <div class="perf-summary-item"><span class="stat-label">Avg Loss</span><span class="stat-value negative">${stats['avg_loss']:.2f}</span></div>
                <div class="perf-summary-item"><span class="stat-label">Best Trade</span><span class="stat-value positive">${stats['best']:+.2f}</span></div>
                <div class="perf-summary-item"><span class="stat-label">Worst Trade</span><span class="stat-value negative">${stats['worst']:+.2f}</span></div>
            </div>
            {audit_html}
        </div>
    </div>

    <!-- Right column: Activity, Watchlist, Paper, Shadow -->
    <div class="dash-col">
        <div class="glass-card dash-item" data-id="activity">
            <h2>Activity Feed</h2>
            <div class="activity-legend">
                <span class="legend-dot" style="color:var(--positive)">&#9679; Entry</span>
                <span class="legend-dot" style="color:var(--accent)">&#9679; Exit</span>
                <span class="legend-dot" style="color:var(--warning)">&#9679; System</span>
            </div>
            <div class="activity-scroll">
            {activity_html if activity_html else '<div class="activity-line act-default">No recent activity</div>'}
            </div>
        </div>
        <div class="glass-card dash-item" data-id="watchlist">
            <h2>Watchlist</h2>
            {_build_watchlist_html(watchlist)}
        </div>
        {_build_l2_monitor_panel()}
        {_build_reconcile_card()}
        {_build_observability_panel()}
        {paper_html}
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
    --bg-deep: #0d1117;
    --panel-bg: #161b22;
    --panel-border: #21262d;
    --text-primary: #c9d1d9;
    --text-secondary: #8b949e;
    --text-dim: #484f58;
    --accent: #39d2c0;
    --positive: #3fb950;
    --negative: #f85149;
    --warning: #d29922;
    --border-subtle: #21262d;
    --hover-bg: #1c2128;
}}

body {{
    background: var(--bg-deep);
    color: var(--text-primary);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
    padding: 0;
}}

#content {{
    width: 100%;
    padding: 0;
    position: relative;
}}

/* ── Top bar ── */
.top-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    background: var(--panel-bg);
    border-bottom: 1px solid var(--panel-border);
    position: sticky;
    top: 0;
    z-index: 100;
}}
.top-left {{ display: flex; align-items: baseline; gap: 10px; }}
.logo {{
    font-size: 1.1em;
    font-weight: 700;
    letter-spacing: 3px;
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
}}
.logo-sub {{
    font-size: 0.6em;
    font-weight: 500;
    letter-spacing: 4px;
    color: var(--text-dim);
    text-transform: uppercase;
}}
.top-center {{ text-align: center; }}
.top-right {{ text-align: right; }}
.clock {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.1em;
    font-weight: 500;
    color: var(--text-primary);
    letter-spacing: 1px;
}}
.date {{
    font-size: 0.7em;
    color: var(--text-secondary);
    margin-top: 1px;
    font-family: 'JetBrains Mono', monospace;
}}

/* Regime badge */
.regime-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 3px;
    font-size: 0.7em;
    font-weight: 600;
    letter-spacing: 0.5px;
    font-family: 'JetBrains Mono', monospace;
}}
.regime-normal {{
    background: rgba(63,185,80,0.1);
    color: var(--positive);
    border: 1px solid rgba(63,185,80,0.25);
}}
.regime-warn {{
    background: rgba(210,153,34,0.1);
    color: var(--warning);
    border: 1px solid rgba(210,153,34,0.25);
    animation: pulse-warn 2s ease-in-out infinite;
}}
.regime-info {{
    background: rgba(57,210,192,0.1);
    color: var(--accent);
    border: 1px solid rgba(57,210,192,0.25);
}}
@keyframes pulse-warn {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.7; }}
}}

/* ── Status bar (replaces hero row) ── */
.status-bar {{
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 8px 16px;
    background: var(--panel-bg);
    border-bottom: 1px solid var(--panel-border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78em;
    overflow-x: auto;
    white-space: nowrap;
}}
.status-item {{
    display: flex;
    align-items: center;
    gap: 6px;
}}
.status-label {{
    color: var(--text-dim);
    text-transform: uppercase;
    font-size: 0.85em;
    letter-spacing: 0.5px;
}}
.status-value {{
    font-weight: 600;
    color: var(--text-primary);
}}
.status-sub {{
    color: var(--text-dim);
    font-size: 0.9em;
}}

/* ── 3-column grid ── */
.dash-grid {{
    display: grid;
    grid-template-columns: 30% 45% 25%;
    height: calc(100vh - 90px);
    overflow: hidden;
}}
.dash-col {{
    overflow-y: auto;
    padding: 8px;
    scrollbar-width: thin;
    scrollbar-color: rgba(57,210,192,0.15) transparent;
}}
.dash-col::-webkit-scrollbar {{ width: 4px; }}
.dash-col::-webkit-scrollbar-thumb {{ background: rgba(57,210,192,0.15); border-radius: 2px; }}

/* ── Panel card (replaces glass-card) ── */
.glass-card {{
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 4px;
    padding: 12px;
    margin-bottom: 8px;
}}

.dash-item {{
    overflow: auto;
    min-width: 0;
    scrollbar-width: thin;
    scrollbar-color: rgba(57,210,192,0.15) transparent;
    position: relative;
}}
.dash-item::-webkit-scrollbar {{ width: 4px; height: 4px; }}
.dash-item::-webkit-scrollbar-thumb {{ background: rgba(57,210,192,0.15); border-radius: 2px; }}

/* Section titles */

.glass-card h2 {{
    font-size: 10px;
    font-weight: 600;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--panel-border);
    font-family: 'JetBrains Mono', monospace;
}}

/* ── Stats ── */
.stat-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 0.82em;
    border-bottom: 1px solid rgba(33,38,45,0.5);
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
table {{ width: 100%; border-collapse: collapse; font-size: 0.8em; }}
thead th {{
    text-align: left;
    color: var(--text-dim);
    font-weight: 500;
    font-size: 0.82em;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--panel-border);
}}
tbody td {{
    padding: 6px 8px;
    border-bottom: 1px solid rgba(33,38,45,0.5);
    color: var(--text-secondary);
}}
tbody tr:hover {{ background: var(--hover-bg); }}
tr.win .pnl-cell {{ color: var(--positive); font-weight: 600; }}
tr.loss .pnl-cell {{ color: var(--negative); font-weight: 600; }}
.pair-cell {{ color: var(--text-primary); font-weight: 500; }}
.reason-cell {{ font-size: 0.9em; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.time-cell {{ font-family: 'JetBrains Mono', monospace; font-size: 0.9em; color: var(--text-dim); }}
.empty-row {{ text-align: center; color: var(--text-dim); padding: 20px; }}

/* Side badge */
.side-badge {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.8em;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
.side-long {{
    background: rgba(63,185,80,0.1);
    color: var(--positive);
}}
.side-short {{
    background: rgba(248,81,73,0.1);
    color: var(--negative);
}}

/* ── Charts ── */
.charts-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}}
.chart-box {{
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 4px;
    padding: 6px;
    text-align: center;
}}
.chart-box img {{
    width: 100%;
    border-radius: 2px;
}}

/* ── L2 Anticipation Monitor ── */
.l2-table {{ width: 100%; border-collapse: collapse; font-size: 0.78rem; margin-top: 0.4rem; }}
.l2-table th {{ text-align: left; padding: 0.3rem 0.4rem; font-weight: 600; color: var(--muted); border-bottom: 1px solid rgba(255,255,255,0.1); }}
.l2-table td {{ padding: 0.3rem 0.4rem; border-bottom: 1px solid rgba(255,255,255,0.05); }}
.l2-cell {{ text-align: center; font-variant-numeric: tabular-nums; }}
.l2-ok {{ color: var(--positive); font-weight: 600; }}
.l2-fail {{ color: var(--negative); font-weight: 600; }}
.l2-ready {{ color: var(--positive); font-weight: 700; }}
.l2-partial {{ color: var(--warning); font-weight: 600; }}
.l2-whale {{ color: var(--accent); }}
.l2-stale {{ background: rgba(251,146,60,0.15); color: var(--warning); padding: 0.3rem 0.6rem; border-radius: 4px; margin: 0.4rem 0; font-size: 0.8rem; }}

/* ── Watchlist ── */
.watchlist-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
    gap: 4px;
}}
.wl-item {{
    background: var(--bg-deep);
    border: 1px solid var(--panel-border);
    border-radius: 3px;
    padding: 6px 8px;
    font-size: 0.78em;
}}
.wl-item:hover {{
    background: var(--hover-bg);
}}
.wl-item .sym {{
    font-weight: 600;
    color: var(--text-primary);
    font-size: 0.9em;
}}
.wl-item .meta {{
    color: var(--text-dim);
    font-size: 0.72em;
    margin-top: 2px;
}}
.wl-item .dot {{
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    margin-right: 3px;
    vertical-align: middle;
}}
.dot-open {{
    background: var(--positive);
}}
.dot-scanner {{
    background: var(--accent);
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
    scrollbar-color: rgba(57,210,192,0.15) transparent;
}}
.activity-scroll::-webkit-scrollbar {{ width: 3px; }}
.activity-scroll::-webkit-scrollbar-thumb {{ background: rgba(57,210,192,0.15); border-radius: 2px; }}
.activity-line {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65em;
    padding: 3px 4px;
    border-radius: 2px;
    margin-bottom: 1px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.activity-line:hover {{
    background: var(--hover-bg);
    white-space: normal;
    word-break: break-all;
}}
.act-entry {{ color: var(--positive); }}
.act-exit {{ color: var(--accent); }}
.act-system {{ color: var(--warning); }}
.act-default {{ color: var(--text-dim); }}
.activity-legend {{ display:flex; gap:10px; padding:3px 0 6px; font-size:0.7rem; }}
.legend-dot {{ display:flex; align-items:center; gap:3px; }}

/* ── Audit ── */
.audit-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 8px;
    margin-bottom: 8px;
}}
.audit-section {{
    background: var(--bg-deep);
    border: 1px solid var(--panel-border);
    border-radius: 4px;
    padding: 10px 12px;
}}
.audit-section h3 {{
    font-size: 10px;
    font-weight: 600;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
    font-family: 'JetBrains Mono', monospace;
}}
.audit-section table {{ font-size: 0.78em; }}
.audit-section thead th {{
    font-size: 0.8em;
    padding: 4px 5px;
}}
.audit-section tbody td {{
    padding: 3px 5px;
    font-size: 0.9em;
}}
.audit-log .table-wrap {{
    scrollbar-width: thin;
    scrollbar-color: rgba(57,210,192,0.15) transparent;
}}
.audit-log .table-wrap::-webkit-scrollbar {{ width: 3px; }}
.audit-log .table-wrap::-webkit-scrollbar-thumb {{ background: rgba(57,210,192,0.15); border-radius: 2px; }}

/* ── Paper comparison ── */
.paper-card {{
    border-color: var(--panel-border);
    background: var(--panel-bg);
}}
.paper-badge {{
    display: inline-block;
    background: rgba(57,210,192,0.1);
    color: var(--accent);
    border: 1px solid rgba(57,210,192,0.25);
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 0.85em;
    letter-spacing: 1px;
    margin-right: 6px;
    vertical-align: middle;
    font-family: 'JetBrains Mono', monospace;
}}
.compare-header {{
    display: grid;
    grid-template-columns: 1fr 80px 80px;
    gap: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--panel-border);
    margin-bottom: 4px;
}}
.compare-col-label {{
    font-size: 0.65em;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    text-align: right;
    font-family: 'JetBrains Mono', monospace;
}}
.live-label {{ color: var(--positive); }}
.paper-label {{ color: var(--accent); }}
.compare-section-title {{
    font-size: 10px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 5px 0 2px;
    border-bottom: 1px solid rgba(33,38,45,0.5);
    font-family: 'JetBrains Mono', monospace;
}}
.compare-row {{
    display: grid;
    grid-template-columns: 1fr 80px 80px;
    gap: 6px;
    align-items: center;
    padding: 3px 0;
    font-size: 0.82em;
    border-bottom: 1px solid rgba(33,38,45,0.5);
}}
.compare-label {{ color: var(--text-secondary); font-weight: 400; }}
.compare-live, .compare-v10, .compare-paper {{
    text-align: right;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    font-size: 0.92em;
}}
.compare-paper {{ color: var(--accent); }}
.paper-trade-row {{
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 3px 0;
    font-size: 0.78em;
    border-bottom: 1px solid rgba(33,38,45,0.5);
}}
.paper-trade-row:last-child {{ border-bottom: none; }}

/* ── Session breakdown ── */
.session-section {{
    margin-bottom: 4px;
}}
.session-section-title {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-bottom: 4px;
    padding-bottom: 3px;
    border-bottom: 1px solid var(--panel-border);
    font-family: 'JetBrains Mono', monospace;
}}
.session-divider {{
    height: 1px;
    background: var(--panel-border);
    margin: 8px 0;
}}
.session-row {{
    padding: 5px 0;
    border-bottom: 1px solid rgba(33,38,45,0.5);
}}
.session-row:last-child {{ border-bottom: none; }}
.session-name {{
    font-size: 0.8em;
    color: var(--text-primary);
    font-weight: 500;
    margin-bottom: 3px;
}}
.session-label-text {{
    vertical-align: middle;
}}
.session-morning .session-name {{ color: #3fb950; }}
.session-afternoon .session-name {{ color: #d29922; }}
.session-night .session-name {{ color: #39d2c0; }}
.session-detail-stats {{
    display: flex;
    gap: 8px;
    font-size: 0.78em;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary);
    margin-bottom: 3px;
}}
.session-stat-item {{
    white-space: nowrap;
}}
.session-bar-wrap {{
    height: 4px;
    background: rgba(33,38,45,0.8);
    border-radius: 2px;
    overflow: hidden;
}}
.session-bar {{
    height: 100%;
    border-radius: 2px;
}}

/* ── Performance summary row (inside audit card) ── */
.perf-summary {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin-bottom: 10px;
    padding: 8px 0;
    border-bottom: 1px solid var(--panel-border);
}}
.perf-summary-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 0.82em;
}}
.perf-summary-item .stat-label {{
    font-size: 0.8em;
}}
.perf-summary-item .stat-value {{
    font-size: 1em;
}}

/* ── Footer ── */
.footer {{
    text-align: center;
    color: var(--text-dim);
    font-size: 0.65em;
    letter-spacing: 0.5px;
    padding: 8px 0 4px;
    font-family: 'JetBrains Mono', monospace;
}}

/* ── Responsive ── */
@media (max-width: 1200px) {{
    .dash-grid {{ grid-template-columns: 1fr 1fr; height: auto; }}
}}
@media (max-width: 800px) {{
    .dash-grid {{ grid-template-columns: 1fr; height: auto; }}
}}
@media (max-width: 768px) {{
    .top-bar {{ flex-direction: column; gap: 6px; text-align: center; }}
    .top-left {{ justify-content: center; }}
    .status-bar {{ flex-wrap: wrap; }}
}}
</style>
</head>
<body>
<div id="content">
{content}
</div>
<script>
(function() {{
  /* ── Auto-refresh ── */
  async function refresh() {{
    try {{
      const resp = await fetch('/api/content');
      if (!resp.ok) return;
      const html = await resp.text();
      const scrollPositions = {{}};
      document.querySelectorAll('.dash-col').forEach((col, i) => {{
        scrollPositions[i] = col.scrollTop;
      }});
      const mainScroll = window.scrollY;
      document.getElementById('content').innerHTML = html;
      document.querySelectorAll('.dash-col').forEach((col, i) => {{
        if (scrollPositions[i] !== undefined) col.scrollTop = scrollPositions[i];
      }});
      window.scrollTo(0, mainScroll);
      document.querySelectorAll('.chart-box img').forEach(img => {{
        const src = img.getAttribute('src').split('?')[0];
        img.src = src + '?t=' + Date.now();
      }});
    }} catch(e) {{}}
  }}
  setInterval(refresh, 20000);
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
