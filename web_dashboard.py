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
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

CA_TZ = ZoneInfo("America/Los_Angeles")
# CA_TZ is the DISPLAY zone (Jonas is California-based, thinks in PT).
# bot.log writes NAIVE timestamps in the Mac's LOCAL time — and that zone TRAVELS:
# the Mac auto-sets TZ by location (Eastern while travelling East, Pacific at home).
# Pinning the parse to a fixed zone mislabels by the travel delta (was pinned to
# America/New_York → 3h off once back in CA, fixed 2026-06-23). So parse bot.log
# times with .astimezone() (interpret naive as the CURRENT system-local zone) —
# self-corrects wherever the host is. See memory/reference_mac_timezone.md.

def _now_ca():
    return datetime.now(CA_TZ)

def _from_ts(ts):
    return datetime.fromtimestamp(ts, CA_TZ)
from collections import defaultdict
from html import escape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_DIR, "trading_state.json")
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "bot.log")
HOST = "0.0.0.0"  # bind all interfaces so phones on the same LAN can reach it (read-only dashboard)
PORT = 8050

# Access token — gates every request so the read-only dashboard (balance/PnL/positions)
# isn't exposed unauthenticated on untrusted networks the laptop may join (0.0.0.0 binds
# every interface, not just home WiFi). Persisted in a gitignored file so it survives
# restarts and is never committed. Auto-generated on first run.
TOKEN_FILE = os.path.join(PROJECT_DIR, ".dashboard_token")
def _load_or_create_token():
    try:
        with open(TOKEN_FILE) as _f:
            _t = _f.read().strip()
            if _t:
                return _t
    except FileNotFoundError:
        pass
    _t = secrets.token_urlsafe(24)
    with open(TOKEN_FILE, "w") as _f:
        _f.write(_t)
    os.chmod(TOKEN_FILE, 0o600)
    return _t
DASHBOARD_TOKEN = _load_or_create_token()
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# ── Static assets (vendored uPlot — the ONLY files /static/ will serve) ──
STATIC_DIR = os.path.join(PROJECT_DIR, "static")
STATIC_FILES = {
    "uplot.iife.min.js": "application/javascript; charset=utf-8",
    "uplot.min.css": "text/css; charset=utf-8",
}

# ── Watcher-enabled cache (30s TTL — avoids per-poll grep/seek) ──────────
_watcher_cache: dict = {"v": None, "ts": 0.0}

# ── Gate-stats cache (30s TTL — full bot.log parse, called 2× per poll) ──
_gate_stats_cache: dict = {"v": None, "ts": 0.0, "path": None}

# ── Sentinel-era anchors ─────────────────────────────────────────────────
# Sentinel deployed 2026-04-01 23:01 PT (= 2026-04-02 06:01 UTC), trade #342+
SENTINEL_DEPLOY_TS = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def _gate_stats(log_file: str, max_age_hours: int = 24) -> dict:
    """Parse bot.log for gate rejection counts over the last max_age_hours.

    Result is cached for 30 seconds (keyed by log_file path).  If called with
    a non-default path (e.g. from tests passing a sample file) the cache is
    bypassed so that isolated test runs never bleed into each other.
    """
    import re as _re
    from datetime import datetime, timedelta

    _now = time.time()
    # Cache hit: same path, fresh enough
    if (
        log_file == LOG_FILE
        and _gate_stats_cache["path"] == log_file
        and _gate_stats_cache["v"] is not None
        and _now - _gate_stats_cache["ts"] < 30
    ):
        return _gate_stats_cache["v"]

    cutoff = datetime.now(CA_TZ) - timedelta(hours=max_age_hours)
    counts = {}
    label_map = [
        ("Drift gate",     "[DRIFT GATE]"),
        ("Tape gate",      "[TAPE GATE]"),
        ("OB gate",        "[OB GATE]"),
        ("Ensemble <4/7",  "ENSEMBLE SKIP"),
        # "No confluence" MUST outrank "ADX": every idle HOLD line reads
        # "No confluence signal (1h ADX=...)" and first-match-wins was
        # mislabeling 91% of them as "ADX too low" even when ADX passed.
        ("No confluence",  "No confluence"),
        ("ADX too low",    "ADX"),
        ("Low volume",     "low vol"),
        ("Choppy market",  "Choppy"),
        ("Cooldown",       "cooldown"),
        ("QUIET regime",   "QUIET regime"),
        ("Divergence",     "divergence"),
        ("MR RSI floor",   "[MR RSI FLOOR]"),
        ("MR re-quote",    "[MR REQUOTE]"),
    ]
    try:
        with open(log_file, "r", errors="replace") as fh:
            for line in fh:
                if not any(kw.lower() in line.lower() for _, kw in label_map):
                    continue
                ts_match = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
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
    result = dict(sorted(counts.items(), key=lambda x: -x[1]))

    # Only populate cache for the canonical log file path
    if log_file == LOG_FILE:
        _gate_stats_cache["v"] = result
        _gate_stats_cache["ts"] = _now
        _gate_stats_cache["path"] = log_file

    return result


def _reconcile_status(max_age_hours: int = 24) -> dict:
    """Parse reconcile.log for CLEAN streak and last drift message."""
    import re as _re
    from datetime import datetime, timedelta
    import os as _os
    rec_log = _os.path.expanduser("~/Library/Logs/Phmex-S/reconcile.log")
    cutoff = datetime.now(CA_TZ) - timedelta(hours=max_age_hours)
    results = []
    try:
        with open(rec_log, "r", errors="replace") as fh:
            for line in fh:
                if "discrepanc" not in line.lower() and "CLEAN" not in line and "DRIFT" not in line:
                    continue
                ts_match = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
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


def _sim_net_pnl(t: dict) -> float:
    """Honest net for a PAPER (sim) trade. The slot paper writer records
    fees_usdt but does NOT deduct them (net_pnl == pnl_usdt on most sim rows),
    silently overstating sim results. Deduct at render time when the recorded
    net clearly never subtracted fees; trust records that did."""
    net = t.get("net_pnl")
    pnl = t.get("pnl_usdt", 0)
    fees = t.get("fees_usdt") or 0
    if net is not None and abs(net - pnl) > 1e-9:
        return net          # writer already deducted something — trust it
    return pnl - fees


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
        m = re.search(r'(\S+/USDT:USDT)\s+score=([\d.]+) \(hist=([\d.]+) x mkt=([\d.]+)\) \| vol=\$([\d,]+) \| 24h=\s*([\-\+]?[\d.]+)%', line)
        if m:
            change_24h = float(m.group(6))
            scanner_pairs.append({
                "symbol": m.group(1),
                "score": float(m.group(2)),
                "hist_score": float(m.group(3)),
                "mkt_score": float(m.group(4)),
                "vol_usd": float(m.group(5).replace(",", "")),
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


ADX_HOLD_RE = re.compile(r'\[HOLD\] (\S+) — No confluence signal \(1h ADX=([\d.]+)\)')


def parse_pair_adx(lines: list[str]) -> dict[str, float]:
    """Latest 1h ADX per pair from [HOLD] lines. Forward iteration so the
    newest line wins. Pairs with no HOLD line stay ABSENT — never invent."""
    adx: dict[str, float] = {}
    for line in lines:
        m = ADX_HOLD_RE.search(line)
        if m:
            try:
                adx[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
    return adx


# Fill/exit events are the only price-bearing lines the bot logs — there is no
# per-cycle mark price. Newest occurrence wins; symbols never seen stay absent.
_PRICE_RES = [
    re.compile(r'\[FILL\] ([\w/:.]+) real entry price: ([\d.]+)'),
    re.compile(r'\[SYNC\] ([\w/:.]+) real exit fill: ([\d.]+)'),
    re.compile(r'\[LIVE EXIT\] ([\w/:.]+) \S+ @ ([\d.]+)'),
    re.compile(r'Position opened: \w+ ([\w/:.]+) \| Entry: ([\d.]+)'),
    re.compile(r'Position closed: \w+ ([\w/:.]+) \| Exit: ([\d.]+)'),
]


def _parse_last_prices(lines: list[str]) -> dict[str, float]:
    """Last logged price per symbol from the tail already read this request.
    Used for the POSITIONS uPnL column — NO API calls; missing symbol → no uPnL."""
    prices: dict[str, float] = {}
    for line in lines:
        for pat in _PRICE_RES:
            m = pat.search(line)
            if m:
                try:
                    prices[m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
    return prices


def _snapshot_prices(max_age_s: float = 30.0) -> dict[str, float]:
    """Live per-symbol mark price from l2_snapshot.json (`last_price`, written
    by the bot's WS feed ~every 5s). Preferred over log-parsed fill prices for
    the POSITIONS uPnL column because fill prices freeze for a trade's whole
    life. Returns {} when the file is missing, stale (bot down), or last_price
    isn't populated yet (field ships 2026-07-08; None until the bot restarts
    on the new code — uPnL falls back to log prices until then).
    Freshness: per-symbol embedded `updated_at`, falling back to the top-level
    `updated_at`, falling back to file mtime — must be within max_age_s.
    Each price is keyed by the full symbol AND its base (pre-'/') so lookups
    survive format drift between the snapshot and position dicts.
    File read only — NO API calls, preserving dashboard bot-independence."""
    path = os.path.join(PROJECT_DIR, "l2_snapshot.json")
    try:
        mtime = os.path.getmtime(path)
        with open(path) as f:
            snap = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(snap, dict):
        return {}
    now = time.time()
    snap_ts = snap.get("updated_at") or mtime
    prices: dict[str, float] = {}
    for sym, s in (snap.get("symbols") or {}).items():
        if not isinstance(s, dict):
            continue
        px = s.get("last_price")
        if not isinstance(px, (int, float)) or isinstance(px, bool) or px <= 0:
            continue  # None/absent = bot not on new code yet; skip, don't invent
        ts = s.get("updated_at") or snap_ts
        try:
            if now - float(ts) > max_age_s:
                continue  # stale snapshot (bot down) — fall back to log prices
        except (TypeError, ValueError):
            continue
        prices[str(sym)] = float(px)
        prices.setdefault(str(sym).split("/")[0], float(px))
    return prices


def _reconcile_summary() -> dict:
    """Data behind the old reconcile card, reduced to OK / non-OK.
    Same rules as the card: STALE when the last run is >8h old, DRIFT when the
    latest run reports discrepancies, otherwise OK (missing log = OK, nothing
    actionable to show)."""
    log_path = Path.home() / "Library" / "Logs" / "Phmex-S" / "reconcile.log"
    try:
        if not log_path.exists():
            return {"ok": True}
        mtime = log_path.stat().st_mtime
        runs = log_path.read_text(errors="replace").split("=== Phemex Reconciliation")
        if len(runs) < 2:
            return {"ok": True}
        discrepancies = 0
        for line in runs[-1].splitlines():
            if line.strip().startswith("Discrepancies"):
                try:
                    discrepancies = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
        age_hours = (time.time() - mtime) / 3600
        if age_hours > 8:
            return {"ok": False, "msg": f"reconcile STALE — last run {int(age_hours)}h ago"}
        if discrepancies > 0:
            return {"ok": False, "msg": f"reconcile DRIFT — {discrepancies} discrepancies vs Phemex"}
        return {"ok": True}
    except Exception:
        return {"ok": True}


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


# ── Slot guardrails (SLOTS + GUARDRAILS panel) ──────────────────────────
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


def _slot_modes() -> dict[str, dict]:
    """Mode sidecars: {slot_id: {"paper_mode", "capital_pct", "promoted_at"}}."""
    modes: dict[str, dict] = {}
    for path in _glob.glob(os.path.join(PROJECT_DIR, "trading_state_*_mode.json")):
        slot_id = os.path.basename(path).replace("trading_state_", "").replace("_mode.json", "")
        try:
            with open(path) as f:
                modes[slot_id] = json.load(f) or {}
        except Exception:
            pass
    return modes


def _kelly_wr_rr(trades: list[dict]) -> float:
    """Kelly the way strategy_slot.should_auto_demote computes it — wr − (1−wr)/rr,
    but over ALL trades. The kill switch (strategy_slot.is_killed) fires when
    this is negative at ≥50 trades.
    Boundary parity with calculate_kelly_raw — 0.0 when one side empty."""
    wins = [_net_pnl(t) for t in trades if _net_pnl(t) > 0]
    losses = [abs(_net_pnl(t)) for t in trades if _net_pnl(t) < 0]
    if not wins:
        return 0.0
    if not losses:
        return 0.0
    wr = len(wins) / len(trades)
    rr = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
    return wr - (1 - wr) / rr


def _build_slots_guardrails(slot_states: dict = None) -> str:
    """SLOTS + GUARDRAILS panel: per-slot status dot (LIVE green / paper amber /
    killed ✝ dim — killed = negative all-trades Kelly at ≥50 trades), trades ·
    WR · net PnL, and for promoted live slots the $5 demote-headroom depletion
    bar (strategy_slot.should_auto_demote: cap −$5.00 on live NET PnL,
    negative live-only Kelly armed at ≥10 live trades).
    Pass pre-loaded slot states to avoid re-reading every state file per poll."""
    if slot_states is None:
        slot_states = read_all_slot_states()
    modes = _slot_modes()
    live_ids = _live_slot_ids()
    known_order = ["5m_scalp", "5m_mean_revert", "5m_liq_cascade"]
    ordered = [s for s in known_order if s in slot_states]
    # v8_245trades is an archived state snapshot, not a slot (same skip as before)
    ordered += sorted(s for s in slot_states
                      if s not in known_order and s != "v8_245trades")

    def _stats_html(subset, pnl_fn=_net_pnl):
        sn = len(subset)
        swins = sum(1 for t in subset if pnl_fn(t) > 0)
        swr = swins / sn * 100 if sn else 0.0
        snet = sum(pnl_fn(t) for t in subset)
        scls = "pos" if snet > 0 else "neg" if snet < 0 else "dim"
        return f"{sn}t &middot; {swr:.0f}% &middot; <span class='{scls}'>${snet:+.2f}</span>"

    def _sim_row_html(sim_rows):
        # Sim stats are fee-adjusted at render time (the paper writer records
        # fees but doesn't deduct them) — hence the fee-adj tag.
        return (f"<tr class='dim'><td></td><td>sim</td>"
                f"<td>{_stats_html(sim_rows, _sim_net_pnl)}"
                f" <span style='font-size:8px'>fee-adj</span></td></tr>")

    rows = ""
    for slot_id in ordered:
        trades = (slot_states.get(slot_id) or {}).get("closed_trades") or []
        n = len(trades)
        name = escape(slot_id)
        # Never blend real money with sims, in ANY branch: live-mode trades and
        # paper sims always get separate stat rows (main-state 5m_scalp trades
        # carry no mode field — they are all real).
        live_rows = ([t for t in trades if t.get("mode") == "live"]
                     if slot_id != "5m_scalp" else trades)
        sim_rows = [t for t in trades if t.get("mode") != "live"] if slot_id != "5m_scalp" else []

        if slot_id in live_ids:
            rows += (f"<tr><td><span class='pos'>&#9679;</span> {name}</td>"
                     f"<td class='pos'>LIVE</td><td>{_stats_html(live_rows)}</td></tr>")
            if sim_rows:
                rows += _sim_row_html(sim_rows)
            mode = modes.get(slot_id)
            if mode and not mode.get("paper_mode", True):
                # Promoted slot — render the auto-demote guardrail state.
                live_trades = [t for t in trades if t.get("mode") == "live"]
                live_net = sum(_net_pnl(t) for t in live_trades)
                # per-slot loss cap from the mode sidecar (default -$5); ST2.0 runs -$10
                cap = abs(float(mode.get("loss_cap_usdt") or -5.0))
                kmt = int(mode.get("kelly_min_trades") or 10)
                hdrm = cap + live_net
                width = min(100.0, max(0.0, hdrm / cap * 100)) if cap else 0.0
                rows += (
                    "<tr><td colspan='3'>"
                    "<div class='dim' style='margin:3px 0 2px'>demote headroom</div>"
                    "<div style='height:7px;background:var(--bg);border:1px solid var(--border)'>"
                    f"<div style='width:{width:.0f}%;height:100%;"
                    "background:linear-gradient(90deg,#4af626,#f0a500)'></div></div>"
                    f"<div class='dim'>${hdrm:.2f} of ${cap:.2f} &middot; neg-Kelly @{kmt} live trades "
                    f"({len(live_trades)} so far)</div>"
                    "</td></tr>")
        elif n >= 50 and _kelly_wr_rr(trades) < 0:
            # Killed slot — a demoted slot may still hold real-money history
            # (e.g. ST2.0's 35 live trades): show it on its own row, never
            # blended into the sim stats.
            if live_rows:
                rows += (f"<tr class='dim'><td>&#10013; {name}</td><td>killed @{n}</td>"
                         f"<td>live {_stats_html(live_rows)}</td></tr>")
                rows += _sim_row_html(sim_rows)
            else:
                rows += (f"<tr class='dim'><td>&#10013; {name}</td><td>killed @{n}</td>"
                         f"<td>{_stats_html(sim_rows, _sim_net_pnl)}"
                         f" <span style='font-size:8px'>sim fee-adj</span></td></tr>")
        else:
            if live_rows:
                # Previously-promoted slot back on paper: keep its real record visible.
                rows += (f"<tr><td><span class='amb'>&#9679;</span> {name}</td>"
                         f"<td class='amb'>paper</td><td>live {_stats_html(live_rows)}</td></tr>")
                rows += _sim_row_html(sim_rows)
            else:
                rows += (f"<tr><td><span class='amb'>&#9679;</span> {name}</td>"
                         f"<td class='amb'>paper</td>"
                         f"<td>{_stats_html(sim_rows, _sim_net_pnl)}"
                         f" <span style='font-size:8px'>sim fee-adj</span></td></tr>")

    if not rows:
        rows = "<tr><td class='dim'>no slot state files found</td></tr>"
    return ('<div class="ptitle">SLOTS + GUARDRAILS</div>'
            '<div class="sig-desc">Each strategy slot\'s live/paper status, record and net '
            'PnL, plus the auto-demote headroom bar (how close it is to the &minus;$5 kill).</div>'
            f'<table>{rows}</table>')


# ── ST2.0 dedicated panel (book×tape absorption short — maker-fill experiment) ──
_ST2_FILL_RE = re.compile(r'\[SLOT LIVE\] ST2\.0 ENTRY SHORT')
_ST2_MISS_RE = re.compile(r'\[SLOT LIVE\] ST2\.0 .*no fill \(PostOnly miss\)')


def _st2_fill_stats() -> dict:
    """Parse logs/bot.log for ST2.0 maker fills vs PostOnly misses.

    Fill  = '[SLOT LIVE] ST2.0 ENTRY SHORT <sym> | Fill: ...'
    Miss  = '[SLOT LIVE] ST2.0 <sym> short — no fill (PostOnly miss), skipping'
    Lines are de-duplicated after ANSI-stripping (the same event can appear twice
    in bot.log — once colorized, once plain), so each event is counted once.
    Returns {fills, misses, total, rate} where rate is fill % of attempts.
    """
    fills = misses = 0
    seen: set = set()
    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            for raw in f:
                line = strip_ansi(raw).rstrip("\n")
                if "ST2.0" not in line:
                    continue
                if _ST2_FILL_RE.search(line):
                    if line not in seen:
                        seen.add(line)
                        fills += 1
                elif _ST2_MISS_RE.search(line):
                    if line not in seen:
                        seen.add(line)
                        misses += 1
    except FileNotFoundError:
        pass
    total = fills + misses
    rate = (fills / total * 100) if total else 0.0
    return {"fills": fills, "misses": misses, "total": total, "rate": rate}


# ── Per-signal tracking boxes ────────────────────────────────────────────
# One dedicated box per slot so each signal can be tracked independently.
# Each slot is defined by (slot_id, display title, status mode).  ST2.0 is the
# only one carrying the extra maker FILL-RATE headline (special case below).
#
# status mode:
#   "live"  → 5m_scalp (the main confluence bot, always live)
#   "mode"  → status driven by the _<slot>_mode.json sidecar (paper vs live)
#             plus the negative-Kelly kill switch (≥50 trades, Kelly<0)
#   "killed"→ generic: any paper slot with >=50 trades and negative Kelly is
#             shown KILLED by _slot_status_html (no dedicated box anymore)
#   "st2"   → ST2.0: DEMOTED to paper 2026-06-29 (mode sidecar); fill-rate
#             block renders only while live
#
# A .demote_<slot_id> flag file always overrides to DEMOTED (rollback latch).
# (slot_id, title, one-line description of what the strategy does)
_SIGNAL_BOXES = [
    ("5m_scalp",       "HTF_L2_ANTICIPATION &mdash; MAIN LIVE",
     "The main live bot's (only) strategy since the 2026-05-02 cull: HTF (1h) "
     "trend + VWAP context, entry confirmed by live L2 order-book &amp; tape "
     "rather than a closed candle. Stats below are htf_l2 trades only &mdash; "
     "retired strategies' history lives in the blotter/equity, not here."),
    ("5m_mean_revert", "5M_MEAN_REVERT &mdash; LIVE FORWARD TEST",
     "Bollinger-Band mean-reversion scalp &mdash; fades lower-BB bounces / upper-BB "
     "rejections in ranging (low-ADX) markets. LIVE since 2026-06-12; running the "
     "3-leg fill experiment (RSI&lt;22 long floor + maker re-quote + 45s entry patience)."),
    ("ST2.0",          "ST2.0 &mdash; BOOK&times;TAPE ABSORPTION SHORT (DEMOTED)",
     "Shorts a bid-heavy book being aggressively bought into (imbalance &ge; 0.35 &amp; "
     "buy-ratio 0.60&ndash;0.85), cvd/spread filtered. DEMOTED TO PAPER 2026-06-29 "
     "(35 live trades, no edge &mdash; execution adverse selection); paper sims only."),
    ("ETH_TSM_28",     "ETH-TSM-28 &mdash; SLOW TREND (PAPER)",
     "Daily-horizon time-series momentum: long 0.01 ETH when the 28-day return is "
     "in the top tercile of its own history; min 5-day hold, exit on tercile exit, "
     "&minus;8% exchange disaster stop only (no trail/TP/Kelly). Built 2026-07-06, "
     "ships PAPER; promote = .promote_ETH_TSM_28. Kill criteria graded by the "
     "nightly adjudicator (&minus;$10 net / 2 disaster stops / replica drift)."),
]
# 5m_liq_cascade and 5m_narrow boxes removed 2026-06-13 — both hard-KILLED
# in paper (neg Kelly), no longer tracked. State files kept; they still surface
# as one-line rows in the SLOTS + GUARDRAILS panel. The generic KILLED status in
# _slot_status_html stays for any future paper slot.


def _slot_status_html(slot_id: str, trades: list, live_ids: set, modes: dict) -> str:
    """Status badge for one slot box from REAL signals only:
      DEMOTED  — .demote_<slot_id> rollback flag present (highest priority)
      LIVE     — slot in _live_slot_ids() (main bot, or promoted mode sidecar)
      KILLED   — paper slot with ≥50 trades and negative all-trades Kelly
                 (parity with strategy_slot.is_killed / _build_slots_guardrails)
      PAPER    — everything else
    """
    if os.path.exists(os.path.join(PROJECT_DIR, f".demote_{slot_id}")):
        return "<span class='neg'>&#9679; DEMOTED</span>"
    # Status is driven by the mode sidecar (trading_state_<slot>_mode.json) via
    # _live_slot_ids(): LIVE only while the sidecar has paper_mode=False. ST2.0
    # follows the same rule — it was previously hardcoded LIVE here, which
    # mislabeled it after the negative-Kelly auto-demote flipped it to paper (the
    # demote writes the sidecar, not a .demote flag). Fixed 2026-06-15. Any
    # .demote_<slot> rollback flag above still wins.
    if slot_id in live_ids:
        return "<span class='pos'>&#9679; LIVE</span>"
    # Sidecar demotion (paper_mode=true written by auto/manual demote): a slot
    # with real-money history is DEMOTED, not "killed @<blended count>" — the
    # kill label conflated 35 live + 16 paper trades for ST2.0.
    mode = modes.get(slot_id)
    n_live_trades = sum(1 for t in trades if t.get("mode") == "live")
    if mode and mode.get("paper_mode", True) and n_live_trades:
        return f"<span class='neg'>&#9679; DEMOTED @{n_live_trades} live</span>"
    if len(trades) >= 50 and _kelly_wr_rr(trades) < 0:
        return f"<span class='dim'>&#10013; KILLED @{len(trades)}</span>"
    return "<span class='amb'>&#9679; PAPER</span>"


def _build_signal_card(slot_id: str, title: str, state: dict,
                       live_ids: set, modes: dict,
                       fill_stats: dict = None, desc: str = "") -> str:
    """Reusable per-slot tracking box. Renders status, trade count, win rate,
    net PnL (prefers net_pnl), avg win / avg loss, and the current open position
    — all from the slot's own state dict (REAL data, read upstream once).

    desc (optional): one-line plain-English summary of what the strategy does,
    shown as a small caption under the title.
    fill_stats (optional, ST2.0 only): {fills,misses,total,rate} dict from
    _st2_fill_stats() rendered as a headline MAKER FILL RATE block."""
    st = state or {}
    trades = st.get("closed_trades") or []
    positions = st.get("positions") or {}

    n = len(trades)
    wins = [_net_pnl(t) for t in trades if _net_pnl(t) > 0]
    losses = [_net_pnl(t) for t in trades if _net_pnl(t) < 0]
    wr = len(wins) / n * 100 if n else 0.0
    net = sum(_net_pnl(t) for t in trades)
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    net_cls = "pos" if net > 0 else "neg" if net < 0 else "dim"

    status_html = _slot_status_html(slot_id, trades, live_ids, modes)

    # Current open position(s) — side @ entry, else flat.
    if positions:
        pos_bits = []
        for sym, p in positions.items():
            side = escape(str(p.get("side", "?")))
            entry = p.get("entry_price", p.get("entry", 0)) or 0
            short = escape(str(sym).replace("/USDT:USDT", ""))
            pos_bits.append(f"{short} {side} @ {entry:.6g}" if entry
                            else f"{short} {side}")
        open_html = "<span class='amb'>" + " &middot; ".join(pos_bits) + "</span>"
    else:
        open_html = "<span class='dim'>flat</span>"

    # ST2.0-only headline: maker FILL RATE block.
    fill_block = ""
    if fill_stats is not None:
        rate_cls = ("pos" if fill_stats["rate"] >= 50
                    else "amb" if fill_stats["rate"] > 0 else "dim")
        fill_block = (
            "<div style='margin:4px 0;text-align:center'>"
            f"<div class='{rate_cls}' style='font-size:20px;font-weight:bold;line-height:1'>"
            f"{fill_stats['rate']:.0f}%</div>"
            "<div class='dim' style='font-size:8px;letter-spacing:1px'>MAKER FILL RATE</div>"
            f"<div class='dim' style='font-size:9px;margin-top:2px'>"
            f"<span class='pos'>{fill_stats['fills']} fill</span> &middot; "
            f"<span class='neg'>{fill_stats['misses']} miss</span> &middot; "
            f"{fill_stats['total']} attempts</div>"
            "</div>"
        )

    # Actual wins/losses counts (real records, not just a win-rate %).
    w_all, l_all = len(wins), len(losses)
    n_live = sum(1 for t in trades if t.get("mode") == "live")
    if 0 < n_live < n:
        # Slot has BOTH real (live) and simulated (paper) history — e.g. a slot
        # that traded live then auto-demoted to paper. Never conflate real money
        # with sim: split the actual W/L record and PnL by mode (2026-06-15).
        def _wl(ts, pnl_fn=_net_pnl):
            w = sum(1 for t in ts if pnl_fn(t) > 0)
            l = sum(1 for t in ts if pnl_fn(t) < 0)
            return w, l, sum(pnl_fn(t) for t in ts)
        live_ts = [t for t in trades if t.get("mode") == "live"]
        paper_ts = [t for t in trades if t.get("mode") != "live"]
        lw, ll, lnet = _wl(live_ts)
        # Sim stats fee-adjusted at render time (paper writer records fees but
        # doesn't deduct them from net_pnl).
        pw, pl, pnet = _wl(paper_ts, _sim_net_pnl)
        # Break-even trades (net==0) are neither W nor L; show them so W/L reconciles
        # to the trade count (else e.g. 11W/15L reads as 26 but live total is 27).
        l_be = len(live_ts) - lw - ll
        p_be = len(paper_ts) - pw - pl
        _lbe = f" / <span class='dim'>{l_be}BE</span>" if l_be else ""
        _pbe = f" / {p_be}BE" if p_be else ""
        lwr = lw / (lw + ll) * 100 if (lw + ll) else 0.0   # win rate excludes scratches
        pwr = pw / (pw + pl) * 100 if (pw + pl) else 0.0
        # avg win / avg loss on LIVE (real) trades — surfaces the loss/win asymmetry
        _lwins = [_net_pnl(t) for t in live_ts if _net_pnl(t) > 0]
        _llosses = [_net_pnl(t) for t in live_ts if _net_pnl(t) < 0]
        l_avgw = sum(_lwins) / len(_lwins) if _lwins else 0.0
        l_avgl = sum(_llosses) / len(_llosses) if _llosses else 0.0
        lcls = "pos" if lnet > 0 else "neg" if lnet < 0 else "dim"
        pcls = "pos" if pnet > 0 else "neg" if pnet < 0 else "dim"
        stats_rows = (
            f"<tr><td class='dim'>status</td><td>{status_html}</td></tr>"
            f"<tr><td class='dim'>trades</td><td><span class='amb'>{len(live_ts)} live</span>"
            f"<span class='dim' style='font-size:9px'> &middot; {len(paper_ts)} paper sim &middot; {n} total</span></td></tr>"
            f"<tr><td class='dim'>live (real)</td><td>"
            f"<span class='pos'>{lw}W</span> / <span class='neg'>{ll}L</span>{_lbe} "
            f"&middot; {lwr:.0f}% WR &middot; <span class='{lcls}'>${lnet:+.2f}</span>"
            f"<span class='dim' style='font-size:9px'> &middot; {len(live_ts)} tr</span></td></tr>"
            f"<tr><td class='dim'>paper (sim)</td><td>"
            f"{pw}W / {pl}L{_pbe} &middot; {pwr:.0f}% WR &middot; <span class='{pcls}'>${pnet:+.2f}</span>"
            f" <span class='dim' style='font-size:8px'>fee-adj</span></td></tr>"
            f"<tr><td class='dim'>net PnL (live)</td><td class='{lcls}'>${lnet:+.2f}</td></tr>"
            f"<tr><td class='dim'>avg win (live)</td><td class='pos'>${l_avgw:+.2f}</td></tr>"
            f"<tr><td class='dim'>avg loss (live)</td><td class='neg'>${l_avgl:+.2f}</td></tr>"
            f"<tr><td class='dim'>open</td><td>{open_html}</td></tr>"
        )
    elif slot_id == "5m_scalp" and n:
        # Main/htf_l2 card: same split-row design as the mean_revert box. All
        # main trades are real money, so the meaningful split is the CURRENT
        # CONFIG ERA (Jun 1+: 24h trading, partial-TP, cleared blacklist) vs
        # earlier history — mirrors live-vs-sim in layout.
        ERA_TS = 1780297200  # 2026-06-01 00:00 PT
        era_ts = [t for t in trades if (t.get("opened_at") or 0) >= ERA_TS]
        old_ts = [t for t in trades if (t.get("opened_at") or 0) < ERA_TS]

        def _rec(ts):
            w = sum(1 for t in ts if _net_pnl(t) > 0)
            l = sum(1 for t in ts if _net_pnl(t) < 0)
            be = len(ts) - w - l
            wr_ = w / (w + l) * 100 if (w + l) else 0.0
            return w, l, be, wr_, sum(_net_pnl(t) for t in ts)
        ew, el, ebe, ewr, enet = _rec(era_ts)
        ow, ol, obe, owr, onet = _rec(old_ts)
        _ebe = f" / <span class='dim'>{ebe}BE</span>" if ebe else ""
        _e_wins = [_net_pnl(t) for t in era_ts if _net_pnl(t) > 0]
        _e_losses = [_net_pnl(t) for t in era_ts if _net_pnl(t) < 0]
        e_avgw = sum(_e_wins) / len(_e_wins) if _e_wins else 0.0
        e_avgl = sum(_e_losses) / len(_e_losses) if _e_losses else 0.0
        ecls = "pos" if enet > 0 else "neg" if enet < 0 else "dim"
        ocls = "pos" if onet > 0 else "neg" if onet < 0 else "dim"
        stats_rows = (
            f"<tr><td class='dim'>status</td><td>{status_html}</td></tr>"
            f"<tr><td class='dim'>trades</td><td><span class='amb'>{len(era_ts)} current era</span>"
            f"<span class='dim' style='font-size:9px'> &middot; {len(old_ts)} earlier &middot; {n} total</span></td></tr>"
            f"<tr><td class='dim'>era (Jun+)</td><td>"
            f"<span class='pos'>{ew}W</span> / <span class='neg'>{el}L</span>{_ebe} "
            f"&middot; {ewr:.0f}% WR &middot; <span class='{ecls}'>${enet:+.2f}</span></td></tr>"
            f"<tr><td class='dim'>earlier</td><td class='dim'>"
            f"{ow}W / {ol}L &middot; {owr:.0f}% WR &middot; <span class='{ocls}'>${onet:+.2f}</span></td></tr>"
            f"<tr><td class='dim'>net PnL (era)</td><td class='{ecls}'>${enet:+.2f}</td></tr>"
            f"<tr><td class='dim'>avg win (era)</td><td class='pos'>${e_avgw:+.2f}</td></tr>"
            f"<tr><td class='dim'>avg loss (era)</td><td class='neg'>${e_avgl:+.2f}</td></tr>"
            f"<tr><td class='dim'>open</td><td>{open_html}</td></tr>"
        )
    else:
        stats_rows = (
            f"<tr><td class='dim'>status</td><td>{status_html}</td></tr>"
            f"<tr><td class='dim'>trades</td><td>{n}</td></tr>"
            f"<tr><td class='dim'>record</td><td>"
            f"<span class='pos'>{w_all}W</span> / <span class='neg'>{l_all}L</span> "
            f"&middot; {wr:.0f}%</td></tr>"
            f"<tr><td class='dim'>net PnL</td><td class='{net_cls}'>${net:+.2f}</td></tr>"
            f"<tr><td class='dim'>avg win</td><td class='pos'>${avg_win:+.2f}</td></tr>"
            f"<tr><td class='dim'>avg loss</td><td class='neg'>${avg_loss:+.2f}</td></tr>"
            f"<tr><td class='dim'>open</td><td>{open_html}</td></tr>"
        )

    desc_html = f'<div class="sig-desc">{desc}</div>' if desc else ""
    return (
        f'<div class="ptitle">{title}</div>'
        f"{desc_html}"
        f"{fill_block}"
        f"<table>{stats_rows}</table>"
    )


def _build_signals_section(slot_states: dict = None) -> str:
    """SIGNALS section: one dedicated tracking box per active slot (5m_scalp,
    5m_mean_revert, ST2.0).

    Reads slot states once (read_all_slot_states maps 5m_scalp → the main
    trading_state.json, so it is NOT double-counted against any sidecar — there
    is no trading_state_5m_scalp.json on disk). ST2.0 reads its own state file
    (51 trades: 35 live + 16 paper); its fill-rate block renders only while live.
    Read-only: no order/state writes, no bot imports."""
    if slot_states is None:
        slot_states = read_all_slot_states()
    live_ids = _live_slot_ids()
    modes = _slot_modes()

    cards = ""
    for slot_id, title, desc in _SIGNAL_BOXES:
        state = slot_states.get(slot_id) or {"closed_trades": [], "positions": {}}
        if slot_id == "5m_scalp":
            # The main box is the htf_l2_anticipation card: filter its stats to
            # that strategy so retired strategies' history doesn't blend in.
            # Open positions stay unfiltered (whatever the main bot holds).
            state = {
                "closed_trades": [t for t in (state.get("closed_trades") or [])
                                  if t.get("strategy") == "htf_l2_anticipation"
                                  and (t.get("exit_reason") or t.get("reason")) != "min_margin_skip"],
                "positions": state.get("positions") or {},
            }
        fill_stats = (_st2_fill_stats()
                      if slot_id == "ST2.0" and slot_id in live_ids else None)
        card = _build_signal_card(slot_id, title, state, live_ids, modes,
                                  fill_stats, desc)
        cards += f'<div class="panel sig-box" id="sig-{escape(slot_id)}">{card}</div>'
    return (f'<div id="signals-title">STRATEGIES</div>'
            f'<div id="signals-grid">{cards}</div>')


# ── Equity series (JSON for the client-side uPlot chart) ────────────────
def build_equity_series(era: str = "sentinel") -> dict:
    """Cumulative NET PnL series for /api/equity — rendered client-side by uPlot.

    Merges main closed_trades with every slot's LIVE-mode closed trades
    (slot trades carry mode=="live"), sorted by close timestamp. Keyed on the
    per-trade mode, NOT current promotion status — a demoted slot's real-money
    history (e.g. ST2.0's 35 live trades) must stay on the curve.
    era="sentinel" reuses the exact cutoff the removed PNG sentinel chart
    used: (opened_at or closed_at) >= SENTINEL_DEPLOY_TS. era="all" = everything.
    Returns {"t": [unix_ts], "v": [cum_net], "meta": [per-trade dict]}.
    """
    rows = [("main", t) for t in read_state().get("closed_trades", []) or []]
    for slot_id, state in sorted(read_all_slot_states().items()):
        if slot_id in ("5m_scalp", "v8_245trades"):
            continue  # main file already merged above; v8 is an archive snapshot
        slot_trades = (state or {}).get("closed_trades", []) or []
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


def collect_blotter_rows(limit: int = 500, slot_states: dict = None) -> list[dict]:
    """Merged blotter: main closed_trades (owner "main") + every slot state's
    closed_trades (owner = slot_id). Stable id = "owner:index_in_that_file"
    (files are append-only, so the index never moves). Newest first.
    Pass pre-loaded slot states (read_all_slot_states shape, where key
    "5m_scalp" IS the main trading_state.json) to avoid re-reading every state
    file per poll; direct callers without one load the files themselves."""
    if slot_states is not None:
        sources = [("main" if sid == "5m_scalp" else sid,
                    (st or {}).get("closed_trades") or [])
                   for sid, st in slot_states.items()
                   if sid != "v8_245trades"]  # archive snapshot, not a slot
    else:
        sources = []
        for owner, path in _blotter_sources():
            if owner == "v8_245trades":
                continue  # archive snapshot — its old main-bot trades would be mislabeled
            try:
                with open(path) as f:
                    sources.append((owner, json.load(f).get("closed_trades", []) or []))
            except Exception:
                continue
    rows = []
    for owner, trades in sources:
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
                # Sim rows fee-adjusted at render time (paper writer bug)
                "net": round(_net_pnl(t) if mode == "live" else _sim_net_pnl(t), 4),
                "reason": str(t.get("exit_reason") or t.get("reason") or ""),
                "owner": owner,
                "mode": mode,
            })
    # Secondary owner key makes tie-timestamp order deterministic regardless of
    # whether sources came from disk globbing or a pre-loaded slot_states dict.
    rows.sort(key=lambda r: (r["ts"], r["owner"]), reverse=True)
    return rows[:limit]


def build_trade_detail(trade_id: str, sym: str = None) -> dict:
    """Drill-down payload for one blotter row id ("owner:index").
    Re-reads the owning state file; unknown/malformed id → {"error": "not found"}.
    Optional sym cross-check: if the caller says which symbol it clicked and the
    record at that index holds a different one, the index moved → "stale id"."""
    try:
        owner, idx_s = str(trade_id).split(":", 1)
        idx = int(idx_s)
        # owner becomes part of a filename — allow only safe slot-id chars. The dot
        # is permitted because live slot ids contain it (e.g. "ST2.0"); the path
        # separator stays disallowed, so no traversal is possible.
        if idx < 0 or not re.fullmatch(r"[A-Za-z0-9_.]+", owner):
            return {"error": "not found"}
        path = STATE_FILE if owner == "main" else os.path.join(
            PROJECT_DIR, f"trading_state_{owner}.json")
        with open(path) as f:
            t = (json.load(f).get("closed_trades", []) or [])[idx]
    except Exception:
        return {"error": "not found"}
    rec_sym = str(t.get("symbol") or "")
    if sym and rec_sym and sym not in (rec_sym, rec_sym.replace("/USDT:USDT", "")):
        return {"error": "stale id"}
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
                **({"symbol": rec_sym} if rec_sym else {}),
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


# ── Ticker helpers (Terminal Pro shell) ─────────────────────────────────
def _latest_balance(lines: list = None) -> float:
    """Last balance-bearing bot-log line: '=== STATS === ... Balance: X USDT'
    (every 10 cycles) or the boot line 'Starting balance: X USDT' (bot.py:751).
    Without the boot line, every restart left a <=10-cycle window showing
    $0.00 (2026-07-16). The state JSON has no balance field. 0.0 if unavailable.
    Pass pre-fetched log lines to avoid a redundant tail_log call."""
    try:
        src = lines if lines is not None else tail_log(2000)
        for line in reversed(src):
            m = re.search(r'[Bb]alance: ([\d.]+) USDT', line)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return 0.0


def _today_net_pnl(state: dict) -> float:
    """Sum of NET pnl for ALL real-money trades closed today (PT midnight
    onward): main-state trades plus slot trades stamped mode=="live". Sim
    (paper) trades never count."""
    try:
        today_start = _now_ca().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        total = sum(_net_pnl(t) for t in state.get("closed_trades", [])
                    if t.get("closed_at", 0) >= today_start)
        for slot_id, sstate in read_all_slot_states().items():
            if slot_id in ("5m_scalp", "v8_245trades"):
                continue  # 5m_scalp IS the main state; v8 is an archive
            total += sum(_net_pnl(t) for t in (sstate or {}).get("closed_trades") or []
                         if t.get("mode") == "live" and t.get("closed_at", 0) >= today_start)
        return total
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


def _mr_headroom(slot_states: dict = None):
    """Demote headroom for the live 5m_mean_revert slot: $5 budget + net PnL of
    its LIVE-mode trades. None when the slot is paper (or files unreadable) —
    the ticker omits the segment entirely in that case.
    Pass pre-loaded slot_states dict to avoid re-reading state files."""
    try:
        # Resolve mode sidecar: prefer slot_states if provided, else direct read
        if slot_states is not None:
            mode_data = None
            # mode sidecar is NOT in slot_states (those are excluded by read_all_slot_states)
            # fall through to direct read for the mode sidecar only
        mode_path = os.path.join(PROJECT_DIR, "trading_state_5m_mean_revert_mode.json")
        with open(mode_path) as f:
            if json.load(f).get("paper_mode", True):
                return None
        # Resolve slot state: use preloaded dict when available
        if slot_states is not None and "5m_mean_revert" in slot_states:
            trades = slot_states["5m_mean_revert"].get("closed_trades", []) or []
        else:
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


def _open_pos_count(state: dict = None, slot_states: dict = None) -> int:
    """Open positions across main state + live-promoted slot state files.
    Pass pre-loaded state/slot_states to avoid re-reading files on each poll."""
    count = 0
    try:
        _state = state if state is not None else read_state()
        count += len(_state.get("positions") or {})
        live_ids = _live_slot_ids()
        for slot_id in live_ids:
            if slot_id == "5m_scalp":
                continue  # main trading_state.json already counted above
            if slot_states is not None and slot_id in slot_states:
                count += len(slot_states[slot_id].get("positions") or {})
            else:
                try:
                    with open(os.path.join(PROJECT_DIR, f"trading_state_{slot_id}.json")) as f:
                        count += len(json.load(f).get("positions") or {})
                except Exception:
                    pass
    except Exception:
        pass
    return count


def _trade_size_env() -> float:
    """Read TRADE_AMOUNT_USDT from .env at request time (NOT import time) so a
    size change + bot restart shows here without a dashboard restart."""
    try:
        for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
            if line.startswith("TRADE_AMOUNT_USDT="):
                return float(line.strip().split("=", 1)[1])
    except Exception:
        pass
    return None


def build_ticker(lines: list = None, slot_states: dict = None, state: dict = None) -> str:
    """One-line sticky status ticker (12-hour PT, NET basis).
    Pass pre-fetched lines/slot_states/state to avoid redundant file reads per poll."""
    # all log-derived strings must be escape()d (innerHTML sink)
    _state = state if state is not None else read_state()
    bal = _latest_balance(lines)
    today = _today_net_pnl(_state)
    arrow = "▲" if today >= 0 else "▼"
    cls = "pos" if today >= 0 else "neg"
    hdrm = _mr_headroom(slot_states)
    watcher = "ON" if _watcher_enabled() else "OFF"
    now = escape(_now_ca().strftime("%-I:%M:%S %p PT"))
    parts = ["PHMEX-S",
             f"BAL ${bal:.2f} <span class='{cls}'>{escape(arrow)}{abs(today):.2f}</span>"]
    if hdrm is not None:
        parts.append(f"MR-LIVE HDRM ${hdrm:.2f}")
    _sz = _trade_size_env()
    if _sz is not None:
        parts.append(f"SIZE ${_sz:g}")
    parts += [
        f"DD {_drawdown_pct(_state, bal):.1f}%",
        f"POS {_open_pos_count(_state, slot_states)}",
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
def _build_positions_panel(lines: list = None, slot_states: dict = None) -> str:
    """POSITIONS panel: main positions + LIVE slots' positions (owner-tagged).
    uPnL price source: fresh l2_snapshot.json last_price when available
    (_snapshot_prices, ~5s WS mark), else the symbol's last price in the log
    tail already read this request (_parse_last_prices) — the dashboard NEVER
    calls the exchange. Shows "—" when neither source has the symbol. Flat
    state shows the last merged close; a reconcile problem (DRIFT/STALE)
    renders as a single red line, nothing when clean."""
    lines = lines if lines is not None else tail_log(3000)
    if slot_states is None:
        slot_states = read_all_slot_states()
    prices = _parse_last_prices(lines)
    live_px = _snapshot_prices()

    pos_rows = []
    for owner in sorted(_live_slot_ids()):
        src = (slot_states.get(owner) or {}).get("positions") or {}
        owner_label = "main" if owner == "5m_scalp" else owner
        for sym, p in src.items():
            short = escape(str(sym).replace("/USDT:USDT", ""))
            side = str(p.get("side", "?"))[:5].upper()
            side_cls = "pos" if side.startswith("L") else "neg"
            entry = p.get("entry_price") or 0
            sl = p.get("exchange_sl_price") or p.get("stop_loss") or 0
            tp = p.get("take_profit") or 0
            opened = p.get("opened_at") or 0
            age = f"{(time.time() - opened) / 60:.0f}m" if opened else "&mdash;"
            # Prefer the live WS mark (fresh snapshot) over the frozen log
            # fill price; try the full symbol then the base for format drift.
            px = (live_px.get(sym) or live_px.get(str(sym).split("/")[0])
                  or prices.get(sym))
            amt = p.get("amount") or 0
            if px and entry and amt:
                upnl = (px - entry) * float(amt) * (1 if side.startswith("L") else -1)
                upnl_cell = f"<td class='{'pos' if upnl >= 0 else 'neg'}'>{upnl:+.2f}</td>"
            else:
                upnl_cell = "<td class='dim'>&mdash;</td>"
            pos_rows.append(
                f"<tr><td>{short}</td><td class='{side_cls}'>{side}</td>"
                f"<td>{entry:.6g}</td>{upnl_cell}<td>{sl:.6g}</td><td>{tp:.6g}</td>"
                f"<td>{age}</td><td class='dim'>{escape(str(p.get('strategy', '')))}</td>"
                f"<td class='dim'>{escape(owner_label)}</td></tr>"
            )

    if pos_rows:
        body = (
            "<table><tr class='dim'><th>SYM</th><th>SIDE</th><th>ENTRY</th><th>UPNL</th>"
            "<th>SL</th><th>TP</th><th>AGE</th><th>STRAT</th><th>OWNER</th></tr>"
            + "".join(pos_rows) + "</table>"
        )
    else:
        last_line = ""
        # "last:" must be the last REAL trade — a paper sim close here would
        # masquerade as live activity under the POSITIONS panel.
        last = [r for r in collect_blotter_rows(50, slot_states)
                if r["mode"] == "live"][:1]
        if last:
            r = last[0]
            net_cls = "pos" if r["net"] >= 0 else "neg"
            side = {"L": "LNG", "S": "SHT"}.get(r["side"][:1].upper(), escape(r["side"][:3].upper()))
            badge = "" if r["owner"] == "main" else f" [{escape(r['owner'])}]"
            last_line = (
                f"<div class='dim' style='margin-top:6px'>last: {escape(r['sym'])}{badge} "
                f"{side} closed {escape(r['time_pt'])} "
                f"<span class='{net_cls}'>{r['net']:+.2f}</span></div>"
            )
        body = "<div class='dim'>flat &mdash; no open positions</div>" + last_line

    rec = _reconcile_summary()
    rec_html = ("" if rec.get("ok") else
                f"<div class='neg' style='margin-top:5px'>&#9888; {escape(rec.get('msg', ''))}</div>")
    return ('<div class="ptitle">POSITIONS &mdash; MAIN + SLOTS</div>'
            '<div class="sig-desc">Positions open right now across the main bot and live '
            'slots &mdash; entry, unrealized PnL, stop/target, age, and the owning strategy.</div>'
            f'{body}{rec_html}')


def _build_blotter_panel(limit: int = 100, slot_states: dict = None) -> str:
    """BLOTTER panel body: merged main+slot rows, newest first, click-to-drill.
    Slot rows carry an owner badge — amber when the slot trade ran LIVE, dim
    for paper. Row ids feed drill() → GET /api/trade?id=owner:index."""
    rows = collect_blotter_rows(limit, slot_states)
    if not rows:
        return "<div class='dim'>no closed trades yet</div>"
    out = ("<table><tr class='dim'><th>TIME</th><th>SYM</th><th>SIDE</th>"
           "<th>MODE</th><th>STRAT</th><th>PNL</th><th>REASON</th></tr>")
    for r in rows:
        net_cls = "pos" if r["net"] >= 0 else "neg"
        side = r["side"][:1].upper()
        side = {"L": "LNG", "S": "SHT"}.get(side, escape(r["side"][:3].upper()))
        side_cls = "pos" if side == "LNG" else "neg"
        badge = ""
        if r["owner"] != "main":
            b_cls = "amb" if r["mode"] == "live" else "dim"
            badge = f" <span class='{b_cls}'>[{escape(r['owner'])}]</span>"
        # Real money vs simulation, unmissable per row (not just badge color).
        mode_cell = ("<td class='pos'>LIVE</td>" if r["mode"] == "live"
                     else "<td class='dim'>sim</td>")
        sim_cls = "" if r["mode"] == "live" else " class='dim'"
        # id is generated server-side as owner:index ([A-Za-z0-9_:] only) — safe in attr;
        # sym passed via data-sym to avoid JS-string escaping issues with special chars.
        out += (
            f"<tr{sim_cls} onclick=\"drill(this,this.dataset.id,this.dataset.sym)\" "
            f"data-id=\"{r['id']}\" data-sym=\"{escape(r['sym'])}\" style='cursor:pointer'>"
            f"<td>{escape(r['time_pt'])}</td>"
            f"<td>{escape(r['sym'])}{badge}</td>"
            f"<td class='{side_cls}'>{side}</td>"
            f"{mode_cell}"
            f"<td class='dim'>{escape(r['strat'][:16])}</td>"
            f"<td class='{net_cls}'>{r['net']:+.2f}</td>"
            f"<td class='dim'>{escape(r['reason'][:14])}</td></tr>"
        )
    return out + "</table>"


_SIGNAL_RE = re.compile(r'\[ENTRY\]|\[SLOT LIVE\] .* ENTRY|Position opened')


def _build_why_no_trades(lines: list = None) -> str:
    """WHY NO TRADES? panel body: per-pair 1h ADX vs the 25 entry gate,
    newest entry signal seen in the tail, and the top 24h gate blocker.
    Read-only log diagnostics; every section degrades to em-dash / no data.
    Pass pre-fetched log lines to avoid a redundant tail_log call."""
    lines = lines if lines is not None else tail_log(3000)
    adx = parse_pair_adx(lines)
    pairs = parse_watchlist(lines).get("base_pairs") or []

    # ── Per-pair ADX + 9-block bar scaled 0-45 (gate fires at 25) ──
    if pairs:
        rows = ""
        for sym in pairs:
            short = escape(str(sym).replace("/USDT:USDT", ""))
            val = adx.get(sym)
            if val is None:
                # No HOLD line for this pair in the tail — unknown, NOT zero.
                rows += (f"<tr><td>{short}</td><td class='dim'>&mdash;</td>"
                         f"<td class='dim'>&mdash;</td></tr>")
                continue
            filled = max(0, min(9, round(val / 45 * 9)))
            bar = "▓" * filled + "░" * (9 - filled)
            if val >= 25:
                rows += (f"<tr><td>{short}</td><td class='pos'>{val:.1f}</td>"
                         f"<td class='pos'>{bar} ✓</td></tr>")
            else:
                rows += (f"<tr><td>{short}</td><td>{val:.1f}</td>"
                         f"<td class='dim'>{bar}</td></tr>")
        adx_html = ("<table><tr class='dim'><th>PAIR</th><th>1H ADX</th>"
                    "<th>GATE 25</th></tr>" + rows + "</table>")
    else:
        adx_html = "<div class='dim'>no data &mdash; watchlist not in log tail</div>"

    # ── Last entry signal (log ts = local Eastern → render PT + relative) ──
    sig_html = "<div class='dim' style='margin-top:5px'>last signal: &mdash; none in log tail</div>"
    for line in reversed(lines):
        if _SIGNAL_RE.search(line):
            m = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
                    ts_pt = ts.astimezone(CA_TZ)
                    mins = max(0, int((datetime.now(CA_TZ) - ts_pt).total_seconds() // 60))
                    ago = f"{mins}m ago" if mins < 120 else f"{mins // 60}h {mins % 60}m ago"
                    sig_html = (f"<div style='margin-top:5px'>last signal: "
                                f"{escape(ts_pt.strftime('%-I:%M %p PT'))} "
                                f"<span class='dim'>({escape(ago)})</span></div>")
                except Exception:
                    pass
            break

    # ── Top gate blocker 24h (same counts source as the GATES panel) ──
    stats = _gate_stats(LOG_FILE)
    if stats:
        name, count = next(iter(stats.items()))  # _gate_stats sorts desc
        gate_html = f"<div class='dim'>top gate 24h: {escape(name)} &times;{count}</div>"
    else:
        gate_html = "<div class='dim'>top gate 24h: no data</div>"

    return adx_html + sig_html + gate_html


_OB_SPREAD_RE = re.compile(r'\[OB\] ([\w/:.]+) imb=\S+ spread=([\d.]+)%')

# Short tokens for the one-line 24h gate summary ("ens 169 · time 42 · …")
_GATE_SHORT = {
    "Tape gate": "tape", "OB gate": "ob", "Ensemble <4/7": "ens",
    "ADX too low": "adx", "Low volume": "vol",
    "No confluence": "conf", "Choppy market": "chop", "Cooldown": "cool",
    "QUIET regime": "quiet", "Divergence": "div",
    "MR RSI floor": "mr-rsi", "MR re-quote": "mr-rq",
}


def _parse_pair_spreads(lines: list[str]) -> dict[str, float]:
    """Latest spread%% per pair from [OB] lines. Forward iteration so the newest
    line wins. Pairs with no [OB] line in the tail stay ABSENT — never invent."""
    spreads: dict[str, float] = {}
    for line in lines:
        m = _OB_SPREAD_RE.search(line)
        if m:
            try:
                spreads[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
    return spreads


def _build_gates_watchlist(lines: list = None) -> str:
    """GATES 24H + WATCHLIST panel body.

    Top: one dim line of 24h gate-rejection counts (top 6 by count, _gate_stats).
    Middle: watchlist table SYM/VOL/SPREAD/RDY — same parse_watchlist data the old
    tile grid used; readiness dot keeps open=green / scanner=amber / base=dim.
    VOL comes from the latest scanner lines, SPREAD from [OB] lines; values not in
    the log tail render as em-dash — never invented.
    Bottom: compact per-symbol L2 readiness rows from l2_snapshot.json (same
    thresholds the old L2 monitor used).
    Pass pre-fetched log lines to avoid a redundant tail_log call."""
    lines = lines if lines is not None else tail_log(3000)

    # ── 24h gate counts, one dim line (top 6; _gate_stats sorts desc) ──
    stats = _gate_stats(LOG_FILE)
    if stats:
        parts = [f"{escape(_GATE_SHORT.get(name, name.lower()))} {count}"
                 for name, count in list(stats.items())[:6]]
        gates_html = "<div class='dim'>" + " &middot; ".join(parts) + "</div>"
    else:
        gates_html = "<div class='dim'>no gate rejections in 24h log</div>"

    # ── Watchlist table: open positions first, then scanner picks, then base ──
    wl = parse_watchlist(lines)
    scanner = {s["symbol"]: s for s in wl["scanner_pairs"]}
    open_syms = wl["open_symbols"]
    spreads = _parse_pair_spreads(lines)
    seen: set = set()
    ordered = []
    for sym in (*sorted(open_syms), *scanner, *wl["base_pairs"]):
        if sym not in seen:
            ordered.append(sym)
            seen.add(sym)
    if ordered:
        rows = ""
        for sym in ordered:
            short = escape(sym.replace("/USDT:USDT", ""))
            vol = (scanner.get(sym) or {}).get("vol_usd")
            if vol is not None:
                vol_cell = f"<td>{vol / 1e6:.1f}M</td>" if vol >= 1e6 else f"<td>{vol / 1e3:.0f}K</td>"
            else:
                vol_cell = "<td class='dim'>&mdash;</td>"
            spread = spreads.get(sym)
            spread_cell = (f"<td>{spread:.3g}%</td>" if spread is not None
                           else "<td class='dim'>&mdash;</td>")
            rdy_cls = "pos" if sym in open_syms else "amb" if sym in scanner else "dim"
            rows += (f"<tr><td>{short}</td>{vol_cell}{spread_cell}"
                     f"<td class='{rdy_cls}'>&#9679;</td></tr>")
        wl_html = ("<table style='margin-top:4px'><tr class='dim'><th>SYM</th>"
                   "<th>VOL</th><th>SPREAD</th><th>RDY</th></tr>" + rows + "</table>")
    else:
        wl_html = "<div class='dim' style='margin-top:4px'>no pairs in log tail</div>"

    # ── L2 readiness: per-symbol signal direction from l2_snapshot.json ──
    try:
        with open(os.path.join(PROJECT_DIR, "l2_snapshot.json")) as f:
            snap = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        snap = None
    if not snap or not snap.get("symbols"):
        l2_html = "<div class='dim' style='margin-top:6px'>L2: no snapshot</div>"
    else:
        age = max(0, int(time.time() - (snap.get("updated_at") or 0)))
        stale = " <span class='neg'>STALE</span>" if age > 120 else ""
        l2_rows = ""
        for sym in sorted(snap["symbols"]):
            s = snap["symbols"][sym]
            short = escape(sym.split("/")[0])
            if (s.get("trade_count") or 0) < 5:
                l2_rows += f"<div class='dim'>{short} no feed</div>"
                continue
            # Same per-signal thresholds as the old L2 monitor: buy_ratio
            # 0.45/0.55, cvd_slope ±0.1, bid/ask depth ratio 1.2/0.83.
            dirs = []
            br = s.get("buy_ratio")
            if br is not None:
                dirs.append(1 if br > 0.55 else -1 if br < 0.45 else 0)
            cvd = s.get("cvd_slope")
            if cvd is not None:
                dirs.append(1 if cvd > 0.1 else -1 if cvd < -0.1 else 0)
            bd, ad = s.get("bid_depth_usdt") or 0, s.get("ask_depth_usdt") or 0
            if bd > 0 and ad > 0:
                ratio = bd / ad
                dirs.append(1 if ratio > 1.2 else -1 if ratio < 0.83 else 0)
            n_long = sum(1 for d in dirs if d == 1)
            n_short = sum(1 for d in dirs if d == -1)
            if n_long == 3 or n_short == 3:
                l2_rows += (f"<div class='pos'>{short} "
                            f"{'LONG' if n_long == 3 else 'SHORT'} 3/3</div>")
            elif n_long and n_short:
                l2_rows += f"<div class='dim'>{short} MIXED {n_long}L/{n_short}S</div>"
            elif n_long or n_short:
                side, n = ("LONG", n_long) if n_long else ("SHORT", n_short)
                l2_rows += f"<div class='amb'>{short} {side} {n}/3</div>"
            else:
                l2_rows += f"<div class='dim'>{short} 0/3</div>"
        l2_html = (f"<div class='dim' style='margin-top:6px'>L2 READINESS "
                   f"&middot; {age}s ago{stale}</div>" + l2_rows)

    return gates_html + wl_html + l2_html


def build_content(lines: list = None, slot_states: dict = None, state: dict = None) -> str:
    """Inner HTML for the swapped #content node — the six-panel command grid.

    Request-scope load: slot states are read ONCE here and passed into every
    panel builder that needs them (positions, slots/guardrails, blotter), so a
    3s poll globs+parses the state files a single time.
    Pass pre-fetched lines/slot_states/state to avoid redundant file reads per poll.
    """
    slot_states = slot_states if slot_states is not None else read_all_slot_states()
    lines = lines if lines is not None else tail_log(3000)

    # Panel 1 — POSITIONS: main + live slots, uPnL from already-read log prices
    positions_html = _build_positions_panel(lines, slot_states)

    # Panel 2 — SLOTS + GUARDRAILS: status dots, kill switch, demote headroom
    slots_html = _build_slots_guardrails(slot_states)

    # Panel 3 — BLOTTER: main + all slots merged, click a row to drill down.
    blotter_html = _build_blotter_panel(slot_states=slot_states)

    # Panel 4 — WHY NO TRADES? diagnostics (per-pair ADX, last signal, top gate)
    why_html = _build_why_no_trades(lines)

    # Panel 5 — GATES + WATCHLIST: 24h gate counts, pair table, L2 readiness
    gates_html = _build_gates_watchlist(lines)

    # Panel 6 — SIGNALS: one dedicated tracking box per slot (incl. ST2.0 maker fill-rate)
    signals_html = _build_signals_section(slot_states)

    return f"""<div id="grid">
    <div class="panel" id="p-positions">
        {positions_html}
    </div>
    <div class="panel" id="p-slots">
        {slots_html}
    </div>
    <div class="panel" id="p-blotter">
        <div class="ptitle">BLOTTER &mdash; CLICK ROW TO DRILL DOWN</div>
        <div class="sig-desc">Most recent closed trades (main + slots): time, symbol, side,
        strategy, net PnL and exit reason. Click any row to drill into the full trade.</div>
        {blotter_html}
    </div>
    <div class="panel" id="p-why">
        <div class="ptitle">WHY NO TRADES?</div>
        <div class="sig-desc">Why the bot is idle: each pair's 1h ADX vs the 25 trend gate,
        the last signal seen, and which gate rejected the most in the last 24h.<br>
        <b>1H ADX</b> = trend strength on the 1-hour chart (0&ndash;~100; higher = stronger
        trend, up or down). <b>GATE 25</b> = the bot needs 1h ADX &ge; 25 to trade
        (&check; = passes); under 25 the pair is too choppy and is blocked.</div>
        {why_html}
    </div>
    <div class="panel" id="p-gates">
        <div class="ptitle">GATES 24H + WATCHLIST</div>
        <div class="sig-desc">Last-24h count of which gates blocked entries, plus a live
        watchlist &mdash; per-symbol volume, spread, and L2 order-book readiness (n/3).</div>
        {gates_html}
    </div>
</div>
<div class="sig-header">SIGNALS &mdash; PER-SLOT TRACKING</div>
{signals_html}"""


def build_html() -> str:
    """Full HTML page shell — sticky ticker / swapped #content grid /
    static #equity-root (outside the swap) / #feed.
    Single triple-read: lines/state/slot_states loaded once and threaded down."""
    _lines = tail_log(3000)
    _state = read_state()
    _slot_states = read_all_slot_states()
    ticker = build_ticker(_lines, _slot_states, _state)
    content = build_content(_lines, _slot_states, _state)
    feed = build_feed(_lines)
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
.sig-header {{ color:var(--amber); letter-spacing:2px; font-size:10px;
  text-transform:uppercase; padding:6px 3px 2px; }}
#signals-title {{ color:var(--amber); letter-spacing:2px; font-size:11px;
  text-transform:uppercase; font-weight:bold; padding:6px 6px 4px;
  border-bottom:1px solid #1a2412; margin:0 3px 3px; }}
#signals-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:3px;
  padding:0 3px 3px; }}
.sig-box {{ min-height:0; max-height:none; }}
.panel .ptitle {{ color:var(--amber); letter-spacing:1.5px; font-size:9px;
  text-transform:uppercase; border-bottom:1px solid #1a2412;
  padding-bottom:3px; margin-bottom:5px; }}
.sig-desc {{ color:var(--dim); font-size:9px; line-height:1.35;
  margin:-2px 0 6px; }}
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
.era-btn {{ background:none; border:1px solid var(--border); color:var(--dim);
  font:inherit; font-size:9px; letter-spacing:1px; padding:0 6px; cursor:pointer; }}
.era-btn.active {{ color:var(--amber); border-color:var(--amber); }}
#equity-chart {{ position:relative; }}
#eqtip {{ position:absolute; display:none; pointer-events:none; z-index:20;
  background:var(--panel); border:1px solid var(--amber); color:var(--txt);
  padding:3px 6px; font-size:10px; white-space:nowrap; }}
@media (max-width:700px){{
  #grid {{ grid-template-columns:1fr; }}
  #signals-grid {{ grid-template-columns:1fr; }}
  .panel {{ max-height:none; }}
  #ticker {{ white-space:normal; font-size:11px; }}
  #p-slots{{order:1}} #p-positions{{order:2}} #p-blotter{{order:3}}
  #p-why{{order:4}} #p-gates{{order:5}}
  #p-blotter tr:nth-child(n+12){{display:none}}
}}
@media (max-width:1100px) and (min-width:701px){{
  #signals-grid {{ grid-template-columns:repeat(2,1fr); }}
}}
</style>
</head>
<body>
<div id="ticker">{ticker}</div>
<div id="content">{content}</div><!-- /content -->
<div class="panel" id="equity-root" style="margin:0 3px;">
    <div class="ptitle"><span id="eq-title">EQUITY &mdash; loading&hellip;</span>
        <span style="float:right">
            <button class="era-btn" onclick="eqZoom(0.7)" title="Zoom in (or scroll-wheel up on chart)">+</button>
            <button class="era-btn" onclick="eqZoom(1.43)" title="Zoom out (or scroll-wheel down on chart)">&minus;</button>
            <button class="era-btn" onclick="eqZoomReset()" title="Reset zoom (or double-click chart)">&#8635;</button>
            <button class="era-btn active" id="era-sentinel" onclick="setEra('sentinel')">SENTINEL</button>
            <button class="era-btn" id="era-all" onclick="setEra('all')">ALL</button>
        </span>
    </div><div id="equity-chart"></div>
</div>
<div id="feed" class="panel">{feed}</div>
<div class="footer">Auto-refresh 3s &middot; Equity 10s &middot; Read-only &middot; Zero API calls &middot; NET basis<span id="upd"></span></div>
<script>
async function poll(){{
  try{{
    const r = await fetch('/api/content'); const j = await r.json();
    document.getElementById('ticker').innerHTML = j.ticker;
    // #content is replaced wholesale — save open blotter drill-down rows
    // (keyed by their stable owner:index id) and re-insert them after the
    // swap so an expanded row survives the 3s poll. Drill content is static
    // per trade, so re-using the saved HTML (no refetch) is correct.
    const openDrills = {{}};
    document.querySelectorAll('#content tr[data-drill]').forEach(x => {{
      openDrills[x.dataset.drill] = x.innerHTML;
    }});
    document.getElementById('content').innerHTML = j.content;
    for(const [id, html] of Object.entries(openDrills)){{
      const tr = document.querySelector('#content tr[data-id="'+CSS.escape(id)+'"]');
      if(tr){{
        const row = document.createElement('tr');
        row.dataset.drill = id;
        row.innerHTML = html;  // saved from our own escq()-sanitized render
        tr.after(row);
      }}
    }}
    document.getElementById('feed').innerHTML = j.feed;
    // live heartbeat: ticks every successful poll so static trade counts don't
    // read as "frozen". A stale time = the poll loop or server actually stopped.
    document.getElementById('upd').textContent = ' · updated ' + new Date().toLocaleTimeString();
  }}catch(e){{}}
}}
setInterval(poll, 3000); poll();

// ── Blotter drill-down. #content is replaced wholesale every 3s; poll()
// saves open drill rows by id and re-inserts them after the swap. ──
function escq(v){{ return String(v==null?'':v).replace(/&/g,'&amp;')
  .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
async function drill(tr, id, sym){{
  const next = tr.nextElementSibling;
  if(next && next.dataset && next.dataset.drill === id){{ next.remove(); return; }}
  let d;
  try{{
    const r = await fetch('/api/trade?id='+encodeURIComponent(id)+
      (sym ? '&sym='+encodeURIComponent(sym) : ''));
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
  row.innerHTML = '<td colspan="7" style="border-left:2px solid #f0a500;'+
    'padding:3px 6px;background:#0a0e08;">'+body+'</td>';
  tr.after(row);
}}

// ── Equity chart (uPlot, vendored at /static/, refreshed every 10s) ──
// plotEra tracks which era the live uPlot instance was built for: same era →
// flicker-free setData() update; era switch (or first load) → full rebuild.
let plot=null, era='sentinel', plotEra=null, eqMeta=[];
// Zoom state, preserved across refreshes so a zoomed view doesn't reset.
let eqZoomed=false, eqXMin=null, eqXMax=null;
// uPlot plugin: wheel-zoom at cursor, shift+wheel pan, dbl-click reset.
// (Drag-select zoom is uPlot-native via cursor.drag below.)
function wheelZoomPlugin(){{
  const factor=0.9;
  return {{ hooks:{{
    ready:(u)=>{{
      const over=u.over;
      over.addEventListener('wheel', (e)=>{{
        e.preventDefault();
        const xMin=u.scales.x.min, xMax=u.scales.x.max, xRange=xMax-xMin;
        if(!isFinite(xRange)||xRange<=0) return;
        if(e.shiftKey){{
          const dval=(e.deltaY<0?-1:1)*xRange*0.12;
          eqZoomed=true; eqXMin=xMin+dval; eqXMax=xMax+dval;
          u.setScale('x', {{min:eqXMin, max:eqXMax}}); return;
        }}
        const cLeft=u.cursor.left;
        if(cLeft==null||cLeft<0) return;
        const xVal=u.posToVal(cLeft,'x');
        const nf=e.deltaY<0?factor:1/factor;
        const newRange=xRange*nf, leftPct=(xVal-xMin)/xRange;
        eqZoomed=true; eqXMin=xVal-leftPct*newRange; eqXMax=eqXMin+newRange;
        u.setScale('x', {{min:eqXMin, max:eqXMax}});
      }}, {{passive:false}});
      over.addEventListener('dblclick', ()=>{{
        eqZoomed=false; eqXMin=null; eqXMax=null;
        const xs=u.data[0];
        if(xs&&xs.length){{ u.setScale('x', {{min:xs[0], max:xs[xs.length-1]}}); }}
      }});
    }},
    setSelect:(u)=>{{
      if(u.select.width>0){{
        eqZoomed=true;
        setTimeout(()=>{{ eqXMin=u.scales.x.min; eqXMax=u.scales.x.max; }},0);
      }}
    }},
  }} }};
}}
// Visible zoom controls (+ / - / reset) — drive the SAME zoom state as wheel/drag.
function eqZoom(nf){{  // nf<1 = zoom in, nf>1 = zoom out, centered on the current view
  if(!plot) return;
  const xMin=plot.scales.x.min, xMax=plot.scales.x.max, xRange=xMax-xMin;
  if(!isFinite(xRange)||xRange<=0) return;
  const c=(xMin+xMax)/2, nr=xRange*nf;
  eqZoomed=true; eqXMin=c-nr/2; eqXMax=c+nr/2;
  plot.setScale('x', {{min:eqXMin, max:eqXMax}});
}}
function eqZoomReset(){{
  if(!plot) return;
  eqZoomed=false; eqXMin=null; eqXMax=null;
  const xs=plot.data[0];
  if(xs&&xs.length){{ plot.setScale('x', {{min:xs[0], max:xs[xs.length-1]}}); }}
}}
async function loadEquity(){{
  const title=document.getElementById('eq-title');
  try{{
    if(typeof uPlot==='undefined') throw new Error('uPlot not loaded');
    const r=await fetch('/api/equity?era='+era); const d=await r.json();
    eqMeta=d.meta;
    const node=document.getElementById('equity-chart');
    if(plot && plotEra===era){{
      // Same era, chart exists: flicker-free data swap. The points-fill and
      // tooltip closures read the global eqMeta (already updated above).
      plot.setData([d.t,d.v]);
      // setData resets the x scale to the full range — restore the zoom.
      if(eqZoomed && eqXMin!=null){{ plot.setScale('x', {{min:eqXMin, max:eqXMax}}); }}
    }}else{{
      const opts={{width:node.clientWidth||800,
        height:180, scales:{{x:{{time:true}}}},
        series:[{{}}, {{label:'NET PnL', stroke:'#f0a500', width:1.5,
          points:{{show:true, size:5,
            fill:(u,si,i)=> eqMeta[i] && eqMeta[i].win ? '#4af626' : '#ff5555'}}}}],
        axes:[{{stroke:'#5a6b5a',grid:{{stroke:'#1a2412'}}}},{{stroke:'#5a6b5a',grid:{{stroke:'#1a2412'}}}}],
        cursor:{{drag:{{x:true,y:false}}}}, legend:{{show:false}},
        plugins:[wheelZoomPlugin()]}};
      if(plot){{ plot.destroy(); plot=null; }}
      node.innerHTML='';
      plot=new uPlot(opts,[d.t,d.v],node);
      plotEra=era;
      // Preserve a user's zoom window across the rebuild.
      if(eqZoomed && eqXMin!=null){{ plot.setScale('x', {{min:eqXMin, max:eqXMax}}); }}
      // tooltip: absolutely-positioned div fed from meta at the cursor's idx
      const tip=document.createElement('div'); tip.id='eqtip'; node.appendChild(tip);
      plot.over.addEventListener('mousemove', ()=>{{
        const i=plot.cursor.idx;
        if(i==null || !eqMeta[i]){{ tip.style.display='none'; return; }}
        const m=eqMeta[i], sign=m.pnl>=0?'+':'';
        tip.innerHTML=escq(m.time_pt)+' &middot; '+escq(m.sym)+' &middot; '+escq(m.strat)+
          ' &middot; <span class="'+(m.win?'pos':'neg')+'">'+sign+m.pnl.toFixed(2)+'</span>'+
          (m.reason?' &middot; '+escq(m.reason):'');
        tip.style.display='block';
        tip.style.left=Math.min(plot.cursor.left+14, Math.max(0,node.clientWidth-260))+'px';
        tip.style.top=(plot.cursor.top+12)+'px';
      }});
      plot.over.addEventListener('mouseleave', ()=>{{ tip.style.display='none'; }});
    }}
    document.getElementById('era-sentinel').classList.toggle('active', era==='sentinel');
    document.getElementById('era-all').classList.toggle('active', era==='all');
    title.textContent='EQUITY — CUMULATIVE NET PNL ('+era.toUpperCase()+' · '+d.t.length+' trades)';
  }}catch(e){{ title.textContent='EQUITY — chart assets missing'; }}
}}
function setEra(e){{ era=e; loadEquity(); }}
loadEquity(); setInterval(loadEquity, 10000);
</script>
</body>
</html>"""




# ── HTTP handler ─────────────────────────────────────────────────────────
class DashboardHandler(BaseHTTPRequestHandler):
    def _authed(self):
        """Token via ?key= (first load) or dash_token cookie (subsequent XHRs).
        Returns 'query' / 'cookie' / None. Constant-time compare."""
        key = (parse_qs(urlparse(self.path).query).get("key") or [None])[0]
        if key and secrets.compare_digest(key, DASHBOARD_TOKEN):
            return "query"
        raw = self.headers.get("Cookie")
        if raw:
            jar = SimpleCookie()
            jar.load(raw)
            if "dash_token" in jar and secrets.compare_digest(jar["dash_token"].value, DASHBOARD_TOKEN):
                return "cookie"
        return None

    def do_GET(self):
        auth = self._authed()
        if not auth:
            body = b"401 Unauthorized - append ?key=YOUR_TOKEN to the URL"
            self.send_response(401)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        _route = urlparse(self.path).path  # ignore ?key= so the token'd page load still routes to "/"
        if _route == "/" or _route == "/index.html":
            html = build_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html.encode())))
            self.send_header("Cache-Control", "no-store")
            # Set the cookie on page load so same-origin XHRs (3s/30s polls) authenticate
            # without the token in every URL. HttpOnly + SameSite=Strict; no Secure (no TLS).
            self.send_header("Set-Cookie", f"dash_token={DASHBOARD_TOKEN}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Strict")
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == "/api/content":
            _lines = tail_log(3000)       # single log tail for the entire poll
            _state = read_state()         # single state read
            _slot_states = read_all_slot_states()  # single slot-states glob+read
            payload = json.dumps({
                "ticker": build_ticker(_lines, _slot_states, _state),
                "content": build_content(_lines, _slot_states, _state),
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
            sym = (qs.get("sym") or [None])[0]
            data = json.dumps(build_trade_detail(tid, sym)).encode()
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
