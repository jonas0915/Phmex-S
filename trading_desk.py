"""
Phmex-S Animated Trading Desk — Sims-style isometric trading floor with live bot data.
Standalone process — reads trading_state.json + bot.log only.
Zero bot imports, zero API calls.
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from html import escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
MIME_OVERRIDES = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".hdr": "application/octet-stream",
}

LOG_FILE = os.path.join(BASE_DIR, "logs", "bot.log")
STATE_FILE = os.path.join(BASE_DIR, "trading_state.json")
HOST, PORT = "127.0.0.1", 8060

NY_TZ = ZoneInfo("America/New_York")  # bot.log timestamps are Eastern


def _tail(path, n=150):
    """Read last n lines of a file."""
    try:
        with open(path, "r") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


def _strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _parse_log_events(lines):
    """Parse log lines into structured events for the dashboard."""
    events = []
    for raw in lines:
        line = _strip_ansi(raw).strip()
        if not line:
            continue

        # Skip duplicate lines (logger writes to both console and file)
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)', line)
        if not ts_match:
            continue

        timestamp, level, msg = ts_match.groups()

        event = {"time": timestamp, "level": level, "msg": msg}

        if "[HOLD]" in msg:
            m = re.search(r'\[HOLD\] (\S+) — (.+)', msg)
            if m:
                event["type"] = "hold"
                event["symbol"] = m.group(1)
                event["detail"] = m.group(2)
        elif "Position closed:" in msg:
            event["type"] = "close"
            m = re.search(r'(LONG|SHORT) (\S+) .* PnL: ([\-\+\d\.]+) USDT \(([\-\+\d\.]+)%\) .* Reason: (\w+)', msg)
            if m:
                event["side"] = m.group(1)
                event["symbol"] = m.group(2)
                event["pnl"] = float(m.group(3))
                event["pnl_pct"] = float(m.group(4))
                event["reason"] = m.group(5)
        elif "[LIVE]" in msg and ("LONG" in msg or "SHORT" in msg):
            event["type"] = "entry"
            m = re.search(r'(LONG|SHORT) [\d\.]+ (\S+)', msg)
            if m:
                event["side"] = m.group(1)
                event["symbol"] = m.group(2)
        elif "[SCANNER]" in msg:
            event["type"] = "scanner"
        elif "[TAPE]" in msg:
            event["type"] = "tape"
        elif "[OB]" in msg:
            event["type"] = "orderbook"
        elif "[DEPTH]" in msg:
            event["type"] = "depth"
        elif "[BAN MODE]" in msg:
            event["type"] = "ban"
        elif "Cycle #" in msg:
            event["type"] = "cycle"
            m = re.search(r'Cycle #(\d+) \| Positions: (\d+)', msg)
            if m:
                event["cycle"] = int(m.group(1))
                event["positions"] = int(m.group(2))
        elif "=== STATS ===" in msg:
            event["type"] = "stats"
            m = re.search(r'Trades: (\d+).*Win Rate: ([\d\.]+)%.*Total PnL: ([\-\+\d\.]+).*Balance: ([\d\.]+).*Drawdown: ([\d\.]+)%', msg)
            if m:
                event["trades"] = int(m.group(1))
                event["win_rate"] = float(m.group(2))
                event["total_pnl"] = float(m.group(3))
                event["balance"] = float(m.group(4))
                event["drawdown"] = float(m.group(5))
        elif "[SYNC]" in msg:
            event["type"] = "sync"
        elif "[COOLDOWN]" in msg:
            event["type"] = "cooldown"
        elif "[WS]" in msg:
            event["type"] = "ws"
        elif "ENTRY:" in msg:
            event["type"] = "entry_detail"
        elif "[FILL]" in msg:
            event["type"] = "fill"
        elif "[ENSEMBLE]" in msg and "[ENSEMBLE SKIP]" not in msg:
            event["type"] = "ensemble"
            m = re.search(r'(\w+) confidence=(\d+)/(\d+) layers=(.*)', msg)
            if m:
                event["direction"] = m.group(1)
                event["confidence"] = int(m.group(2))
                event["max_conf"] = int(m.group(3))
                event["layers"] = m.group(4)
        elif "[ENSEMBLE SKIP]" in msg:
            event["type"] = "ensemble_skip"
            m = re.search(r'(\S+) (\w+) — confidence (\d+)/(\d+)', msg)
            if m:
                event["symbol"] = m.group(1)
                event["direction"] = m.group(2)
                event["confidence"] = int(m.group(3))
        elif "[CVD]" in msg:
            event["type"] = "cvd"
            m = re.search(r'(\S+) cvd=([\-\d\.]+) slope=([\-\d\.]+) div=(\w+)', msg)
            if m:
                event["symbol"] = m.group(1)
                event["cvd"] = float(m.group(2))
                event["slope"] = float(m.group(3))
                event["divergence"] = m.group(4)
        elif "[FUNDING]" in msg:
            event["type"] = "funding"
            m = re.search(r'(\S+) rate=([\-\d\.]+) signal=(\w+)', msg)
            if m:
                event["symbol"] = m.group(1)
                event["rate"] = float(m.group(2))
                event["signal"] = m.group(3)
        elif "[HURST]" in msg:
            event["type"] = "hurst"
            m = re.search(r'(\S+) H=([\d\.]+)', msg)
            if m:
                event["symbol"] = m.group(1)
                event["hurst"] = float(m.group(2))
        elif "[KELLY]" in msg:
            event["type"] = "kelly"
            m = re.search(r'f\*=([\-\d\.]+) fKelly=([\-\d\.]+) conf=(\d+).*\$([\d\.]+)', msg)
            if m:
                event["kelly_raw"] = float(m.group(1))
                event["f_kelly"] = float(m.group(2))
                event["confidence"] = int(m.group(3))
                event["margin"] = float(m.group(4))
        elif "[ENTRY]" in msg:
            event["type"] = "entry"
            m = re.search(r'(LONG|SHORT) (\S+) \| Fill: ([\d\.]+) \| Margin: \$([\d\.]+) \| Conf: (\d+)/(\d+)', msg)
            if m:
                event["side"] = m.group(1)
                event["symbol"] = m.group(2)
                event["fill"] = float(m.group(3))
                event["margin"] = float(m.group(4))
                event["confidence"] = int(m.group(5))
        else:
            event["type"] = "info"

        events.append(event)
    return events


# ── Ported functions (keep in sync with web_dashboard.py) ────────────────────

# ported from web_dashboard.py — keep in sync
_ADX_HOLD_RE = re.compile(r'\[HOLD\] (\S+) — No confluence signal \(1h ADX=([\d.]+)\)')


def parse_pair_adx(lines: list) -> dict:
    """Latest 1h ADX per pair from [HOLD] lines. Forward iteration so the
    newest line wins. Pairs with no HOLD line stay ABSENT — never invent.

    # ported from web_dashboard.py — keep in sync
    """
    adx: dict = {}
    for line in lines:
        m = _ADX_HOLD_RE.search(line)
        if m:
            try:
                adx[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
    return adx


# ported from web_dashboard.py — keep in sync
_watcher_cache: dict = {"v": None, "ts": 0.0}


def _watcher_enabled() -> bool:
    """True if '[LIVE EXIT] watcher enabled' was logged AFTER the most recent
    'Volume scanner ON' line (i.e. after the last bot start). Reads the last
    ~200KB of bot.log; falls back to a full-file grep when the startup markers
    have scrolled out of the tail window (long-running bot). Result cached 30s.

    # ported from web_dashboard.py — keep in sync
    """
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


# ── Net-basis helper ─────────────────────────────────────────────────────────

def _net_trade(t: dict) -> float:
    """Return net PnL for a trade dict: net_pnl if present, else pnl_usdt."""
    v = t.get("net_pnl")
    return float(v) if v is not None else float(t.get("pnl_usdt", 0))


# ported from web_dashboard.py — keep in sync
_gate_counts_cache: dict = {"v": None, "ts": 0.0, "path": None}


def gate_counts_24h(log_file: str = LOG_FILE) -> dict:
    """Parse bot.log for gate rejection counts over the last 24h.
    Returns dict sorted descending by count. Cached 30s (keyed by path;
    non-default paths bypass cache so test runs never bleed into each other).

    # ported from web_dashboard.py — keep in sync
    """
    _now = time.time()
    if (
        log_file == LOG_FILE
        and _gate_counts_cache["path"] == log_file
        and _gate_counts_cache["v"] is not None
        and _now - _gate_counts_cache["ts"] < 30
    ):
        return _gate_counts_cache["v"]

    cutoff = datetime.now(NY_TZ) - timedelta(hours=24)
    counts: dict = {}
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
                ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY_TZ)
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
        _gate_counts_cache["v"] = result
        _gate_counts_cache["ts"] = _now
        _gate_counts_cache["path"] = log_file
    return result


def build_slot_truth() -> list:
    """Per-slot truth for desk monitors. Net basis; live slots add guardrail fields."""
    import glob as _g
    out = []
    for path in sorted(_g.glob(os.path.join(BASE_DIR, "trading_state_5m_*.json"))):
        base = os.path.basename(path)
        if base.endswith("_mode.json") or base.endswith("_blocked.json"):
            continue
        slot_id = base.replace("trading_state_", "").replace(".json", "")
        try:
            with open(path) as f:
                trades = json.load(f).get("closed_trades", [])
        except (OSError, json.JSONDecodeError):
            continue

        wins = sum(1 for t in trades if _net_trade(t) > 0)
        rec = {"id": slot_id,
               "trades": len(trades),
               "wr": round(wins / len(trades) * 100, 1) if trades else 0,
               "net_pnl": round(sum(_net_trade(t) for t in trades), 2),
               "live": False}
        try:
            with open(os.path.join(BASE_DIR, f"trading_state_{slot_id}_mode.json")) as f:
                rec["live"] = not json.load(f).get("paper_mode", True)
        except (OSError, json.JSONDecodeError):
            pass
        if rec["live"]:
            live = [t for t in trades if t.get("mode") == "live"]
            live_net = round(sum(_net_trade(t) for t in live), 2)
            rec.update({"live_net": live_net,
                        "headroom": round(5.0 + live_net, 2),
                        "live_trades": len(live)})
        out.append(rec)
    return out


# ── End ported functions ──────────────────────────────────────────────────────


def _get_state():
    """Read trading_state.json."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"peak_balance": 0, "closed_trades": []}


def _build_api_response():
    """Build the full API response for the frontend."""
    lines = _tail(LOG_FILE, 200)
    # Deduplicate consecutive identical lines
    deduped = []
    prev = None
    for line in lines:
        stripped = _strip_ansi(line).strip()
        if stripped != prev:
            deduped.append(line)
            prev = stripped

    events = _parse_log_events(deduped)
    state = _get_state()

    # Get latest stats
    stats_events = [e for e in events if e.get("type") == "stats"]
    latest_stats = stats_events[-1] if stats_events else None

    # Get latest cycle
    cycle_events = [e for e in events if e.get("type") == "cycle"]
    latest_cycle = cycle_events[-1] if cycle_events else None

    # Recent trades (last 10)
    recent_trades = state.get("closed_trades", [])[-10:]

    # Active events for character animations (last 30 events)
    recent_events = events[-30:]

    # Today stats
    all_trades = state.get("closed_trades", [])
    # "Today" rolls at PACIFIC midnight (project rule) — Mac local clock is Eastern
    today_start = datetime.now(ZoneInfo("America/Los_Angeles")).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_trades = [t for t in all_trades if t.get("closed_at", 0) >= today_start]
    today_pnl = sum(_net_trade(t) for t in today_trades)
    today_count = len(today_trades)
    today_wins = sum(1 for t in today_trades if _net_trade(t) > 0)
    today_wr = (today_wins / today_count * 100) if today_count > 0 else 0

    # Per-pair PnL (top 5 by absolute PnL)
    pair_pnl = {}
    for t in all_trades:
        sym = t.get("symbol", "?").replace("/USDT:USDT", "")
        pair_pnl[sym] = pair_pnl.get(sym, 0) + _net_trade(t)
    top_pairs = sorted(pair_pnl.items(), key=lambda x: abs(x[1]), reverse=True)[:5]

    # Watchlist — unique symbols from recent hold events + open positions
    watchlist = {}
    for e in events:
        if e.get("type") == "hold" and e.get("symbol"):
            sym = e["symbol"].replace("/USDT:USDT", "")
            detail = e.get("detail", "")
            watchlist[sym] = detail  # latest status wins
        elif e.get("type") == "entry" and e.get("symbol"):
            sym = e["symbol"].replace("/USDT:USDT", "")
            side = e.get("side", "")
            watchlist[sym] = f"OPEN {side}"
    # Sort alphabetically
    watchlist_sorted = sorted(watchlist.items())

    # Avg win / avg loss
    wins = [_net_trade(t) for t in all_trades if _net_trade(t) > 0]
    losses = [_net_trade(t) for t in all_trades if _net_trade(t) < 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    best_trade = max(wins) if wins else 0
    worst_trade = min(losses) if losses else 0

    # v8.0 Apex data
    ensemble_events = [e for e in events if e.get("type") in ("ensemble", "ensemble_skip")]
    latest_ensemble = ensemble_events[-3:] if ensemble_events else []

    cvd_events = {e["symbol"]: e for e in events if e.get("type") == "cvd" and "symbol" in e}
    hurst_events = {e["symbol"]: e for e in events if e.get("type") == "hurst" and "symbol" in e}
    funding_events = {e["symbol"]: e for e in events if e.get("type") == "funding" and "symbol" in e}
    kelly_events = [e for e in events if e.get("type") == "kelly"]
    latest_kelly = kelly_events[-1] if kelly_events else None

    # Strategy breakdown from closed trades
    strat_stats = {}
    for t in all_trades:
        s = t.get("strategy", "unknown")
        if s not in strat_stats:
            strat_stats[s] = {"count": 0, "wins": 0, "pnl": 0.0}
        strat_stats[s]["count"] += 1
        if _net_trade(t) > 0:
            strat_stats[s]["wins"] += 1
        strat_stats[s]["pnl"] += _net_trade(t)
    for s in strat_stats:
        strat_stats[s]["pnl"] = round(strat_stats[s]["pnl"], 2)
        strat_stats[s]["wr"] = round(strat_stats[s]["wins"] / strat_stats[s]["count"] * 100, 1) if strat_stats[s]["count"] > 0 else 0

    # Exit reason breakdown
    exit_reasons = {}
    for t in all_trades:
        r = t.get("reason", "unknown")
        if r not in exit_reasons:
            exit_reasons[r] = {"count": 0, "pnl": 0.0}
        exit_reasons[r]["count"] += 1
        exit_reasons[r]["pnl"] += _net_trade(t)
    for r in exit_reasons:
        exit_reasons[r]["pnl"] = round(exit_reasons[r]["pnl"], 2)

    # Truth fields (Task 1 — reuse the same deduped lines, no second read)
    pair_adx = parse_pair_adx(deduped)
    watcher = _watcher_enabled()
    slots = build_slot_truth()
    _gc = gate_counts_24h()
    top_gates = [[name, count] for name, count in list(_gc.items())[:4]]

    # Paper slot data
    paper_state_file = os.path.join(BASE_DIR, "trading_state_5m_liq_cascade.json")
    paper_data = {"trades": 0, "wr": 0, "pnl": 0, "today_trades": 0, "today_wr": 0, "today_pnl": 0, "recent": []}
    if os.path.exists(paper_state_file):
        try:
            with open(paper_state_file) as pf:
                ps = json.load(pf)
            pc = ps.get("closed_trades", [])
            if pc:
                pw = sum(1 for t in pc if t.get("pnl_usdt", 0) > 0)
                paper_data["trades"] = len(pc)
                paper_data["wr"] = round(pw / len(pc) * 100, 1)
                paper_data["pnl"] = round(sum(t.get("pnl_usdt", 0) for t in pc), 2)
                paper_data["recent"] = [{"sym": t.get("symbol","?").split("/")[0], "pnl": round(t.get("pnl_usdt",0), 2), "side": t.get("side","?")} for t in pc[-5:]]
                # Today's paper trades
                today_str = datetime.now().strftime("%Y-%m-%d")
                pt = [t for t in pc if t.get("closed_at") and datetime.fromtimestamp(t["closed_at"]).strftime("%Y-%m-%d") == today_str]
                if pt:
                    ptw = sum(1 for t in pt if t.get("pnl_usdt", 0) > 0)
                    paper_data["today_trades"] = len(pt)
                    paper_data["today_wr"] = round(ptw / len(pt) * 100, 1)
                    paper_data["today_pnl"] = round(sum(t.get("pnl_usdt", 0) for t in pt), 2)
        except Exception:
            pass

    return {
        "stats": latest_stats,
        "cycle": latest_cycle,
        "peak_balance": state.get("peak_balance", 0),
        "total_trades": len(all_trades),
        "recent_trades": recent_trades,
        "events": recent_events,
        "today": {
            "count": today_count, "wins": today_wins,
            "pnl": round(today_pnl, 2), "wr": round(today_wr, 1),
        },
        "top_pairs": top_pairs,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "watchlist": watchlist_sorted,
        "ensemble": latest_ensemble,
        "cvd": cvd_events,
        "hurst": hurst_events,
        "funding": funding_events,
        "kelly": latest_kelly,
        "strat_stats": strat_stats,
        "exit_reasons": exit_reasons,
        "paper": paper_data,
        "slots": slots,
        "watcher": watcher,
        "pair_adx": pair_adx,
        "top_gates": top_gates,
        "pnl_basis": "net",
        "timestamp": time.time(),
    }


# ── HTML Page ──────────────────────────────────────────────────────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phmex-S Trading Desk</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#080f1c; overflow:hidden; height:100vh; width:100vw; font-family:'Nunito',sans-serif; }
#c { position:fixed; top:0; left:0; width:100vw; height:100vh; display:block; }
#css2d { position:fixed; top:0; left:0; width:100vw; height:100vh; pointer-events:none; overflow:visible; }

/* HUD */
#hud {
  position:fixed; bottom:0; left:0; right:0; height:72px; z-index:100;
  background:rgba(10,18,36,0.88); backdrop-filter:blur(12px);
  border-top:1px solid rgba(58,175,203,0.3);
  display:flex; align-items:center; padding:0 24px; gap:12px;
  font-family:'Nunito',sans-serif; color:#e8dcc8;
}
#hud .section { display:flex; align-items:center; gap:10px; }
#hud .balance { font-size:28px; font-weight:800; font-family:'Fira Code',monospace; color:#4ecb71; }
#hud .pnl { font-size:18px; font-weight:700; font-family:'Fira Code',monospace; }
#hud .pnl.pos { color:#4ecb71; }
#hud .pnl.neg { color:#e05252; }
#hud .stat-box { text-align:center; padding:0 14px; border-left:1px solid rgba(58,175,203,0.2); }
#hud .stat-box .label { font-size:10px; text-transform:uppercase; letter-spacing:1px; color:#8899aa; }
#hud .stat-box .value { font-size:16px; font-weight:700; font-family:'Fira Code',monospace; }
#hud-left { flex:0 0 auto; }
#hud-center { flex:1; display:flex; justify-content:center; gap:4px; }
#hud-right { flex:0 0 320px; overflow:hidden; }
#feed { max-height:60px; overflow-y:auto; font-size:11px; font-family:'Fira Code',monospace; line-height:1.4; }
#feed::-webkit-scrollbar { width:4px; }
#feed::-webkit-scrollbar-thumb { background:rgba(58,175,203,0.3); border-radius:2px; }
.feed-line { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.feed-line.entry { color:#4ecb71; }
.feed-line.close { color:#e05252; }
.feed-line.scanner { color:#ffb830; }
.feed-line.cycle { color:#3aafcb; }
.feed-line.hold { color:#667788; }
.feed-line.tape { color:#00e5ff; }
.feed-line.cooldown { color:#f5c842; }
.feed-line.ban { color:#ff5555; }

/* CSS2D labels */
.char-label { pointer-events:none; text-align:center; }
.char-name {
  font-family:'Nunito',sans-serif; font-size:12px; font-weight:700;
  color:#fff; background:rgba(0,0,0,0.6); padding:2px 8px;
  border-radius:8px; white-space:nowrap;
}
.char-emoji { font-size:28px; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.5)); display:none; }
.speech-bubble {
  font-family:'Nunito',sans-serif; font-size:12px; color:#e8dcc8;
  background:rgba(18,33,58,0.95); border:1px solid rgba(58,175,203,0.5);
  padding:8px 12px; border-radius:10px; max-width:240px;
  white-space:normal; word-wrap:break-word; line-height:1.4;
  box-shadow:0 4px 16px rgba(0,0,0,0.6);
  opacity:0; transition:opacity 0.3s; z-index:999;
}
.speech-bubble.visible { opacity:1; }
.speech-bubble::after {
  content:''; position:absolute; bottom:-6px; left:50%; transform:translateX(-50%);
  border-left:6px solid transparent; border-right:6px solid transparent;
  border-top:6px solid rgba(18,33,58,0.92);
}
.plumbob {
  width:8px; height:8px; border-radius:50%;
  animation:status-pulse 2.5s ease-in-out infinite;
  box-shadow:0 0 6px currentColor, 0 0 2px currentColor;
  display:none;
}
@keyframes status-pulse { 0%{opacity:0.7; transform:scale(1);} 50%{opacity:1; transform:scale(1.2);} 100%{opacity:0.7; transform:scale(1);} }
#comms-panel {
  position:fixed; top:12px; right:12px; width:340px; max-height:45vh; z-index:150;
  background:rgba(10,14,20,0.85); border:1px solid rgba(58,175,203,0.25);
  border-radius:8px; padding:8px 10px; font-family:'Fira Code',monospace;
  font-size:11px; overflow:auto; display:flex; flex-direction:column; gap:3px;
  resize:both; min-width:250px; min-height:150px;
  scrollbar-width:thin; scrollbar-color:rgba(58,175,203,0.3) transparent;
  backdrop-filter:blur(6px); box-shadow:0 4px 20px rgba(0,0,0,0.4);
}
#comms-panel::-webkit-scrollbar { width:4px; }
#comms-panel::-webkit-scrollbar-thumb { background:rgba(58,175,203,0.3); border-radius:2px; }
#comms-panel .comms-title {
  font-size:9px; text-transform:uppercase; letter-spacing:1.5px; color:#8899aa;
  border-bottom:1px solid rgba(58,175,203,0.15); padding-bottom:4px; margin-bottom:2px;
  display:flex; align-items:center; gap:6px;
}
#comms-panel .comms-title::before {
  content:''; width:6px; height:6px; border-radius:50%; background:#4ecb71;
  box-shadow:0 0 4px #4ecb71; animation:status-pulse 2.5s ease-in-out infinite;
}
#comms-panel .comm-line {
  line-height:1.4; padding:2px 0; border-bottom:1px solid rgba(255,255,255,0.03);
  opacity:0; animation:comm-fade-in 0.3s ease forwards;
}
#comms-panel .comm-ts { color:#556677; margin-right:5px; }
@keyframes comm-fade-in { to { opacity:1; } }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="css2d"></div>

<div id="comms-panel"><div class="comms-title">Agent Comms</div></div>

<div id="intel-panel">
  <div class="comms-title" style="color:#c084fc">Apex Intel</div>
  <div id="intel-content"></div>
</div>
<style>
#intel-panel {
  position:fixed; top:12px; left:12px; width:280px; max-height:40vh; z-index:150;
  background:rgba(10,14,20,0.85); border:1px solid rgba(192,132,252,0.25);
  border-radius:8px; padding:8px 10px; font-family:'Fira Code',monospace;
  font-size:10px; overflow:auto; display:flex; flex-direction:column; gap:2px;
  scrollbar-width:thin; scrollbar-color:rgba(192,132,252,0.3) transparent;
  backdrop-filter:blur(6px); box-shadow:0 4px 20px rgba(0,0,0,0.4);
}
#intel-panel .intel-sec { margin-bottom:4px; }
#intel-panel .intel-hdr { color:#c084fc; font-weight:700; font-size:9px; text-transform:uppercase; letter-spacing:1px; margin-bottom:2px; }
#intel-panel .intel-row { display:flex; justify-content:space-between; padding:1px 0; color:#aab; }
#intel-panel .intel-row .v { color:#e8dcc8; }
#intel-panel .intel-row .grn { color:#4ecb71; }
#intel-panel .intel-row .red { color:#e05252; }
#intel-panel .intel-row .cyn { color:#67e8f9; }
#intel-panel .intel-row .mag { color:#c084fc; }
</style>

<div id="hud">
  <div id="hud-left" class="section">
    <div><span class="balance" id="h-bal">--</span></div>
    <div><span class="pnl" id="h-pnl">--</span></div>
  </div>
  <div id="hud-center">
    <div class="stat-box"><div class="label">Win Rate</div><div class="value" id="h-wr">--</div></div>
    <div class="stat-box"><div class="label">Drawdown</div><div class="value" id="h-dd">--</div></div>
    <div class="stat-box"><div class="label">Positions</div><div class="value" id="h-pos">--</div></div>
    <div class="stat-box"><div class="label">Trades</div><div class="value" id="h-trades">--</div></div>
    <div class="stat-box"><div class="label">Cycle</div><div class="value" id="h-cycle">--</div></div>
    <div class="stat-box"><div class="label">Kelly $</div><div class="value" id="h-kelly" style="color:#c084fc">--</div></div>
    <div class="stat-box"><div class="label">Conf</div><div class="value" id="h-conf" style="color:#67e8f9">--</div></div>
    <div class="stat-box"><div class="label">Today</div><div class="value" id="h-today">--</div></div>
  </div>
  <div id="hud-right"><div id="feed"></div></div>
</div>

<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
  }
}
</script>

<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
// SSAOPass and ShaderPass removed — too heavy for integrated GPU

// ── GLOBALS ──
let apiData = null;
const clock = new THREE.Clock();
const charGroups = {};
const monitorCanvases = {};
const monitorTextures = {};
const speechBubbles = {};
const plumbobs = {};
let claudeTarget = null;
let claudeWalking = false;
let claudeWalkStart = null;
let claudeWalkFrom = null;
let claudeWalkTo = null;
const WALK_DURATION = 3.5;
const VISIT_INTERVAL = 45000;
let lastVisit = 0;
const visitOrder = ['scanner','risk','tape','jonas','executor','strategy','ws_feed','pos_monitor'];
let visitIdx = 0;

// Sleep system — characters rest between 11pm-6am
function isSleepHours() {
  const h = new Date().getHours();
  return h >= 23 || h < 6;
}
function isLateNight() {
  const h = new Date().getHours();
  return h >= 22 || h < 7; // dim lights zone
}
// Characters who stay awake during sleep hours (skeleton crew)
const nightOwls = ['ensemble', 'risk'];

// Coffee break system
let lastCoffeeBreak = Date.now();
const COFFEE_INTERVAL = 120000; // every 2 minutes someone goes
const COFFEE_BREAK_DURATION = 10000;
const coffeeAgents = ['scanner','risk','tape','executor','strategy','ws_feed','pos_monitor'];
let coffeeAgent = null;
let coffeeWalking = false;
let coffeeWalkFrom = null;
let coffeeWalkTo = null;
let coffeeWalkStart = null;
let coffeeReturning = false;

// Facility visit system (agents go downstairs)
let lastFacilityVisit = Date.now() - 25000; // first visit after 20s
const FACILITY_INTERVAL = 45000; // every 45 seconds someone goes downstairs
const FACILITY_DURATION = 12000; // spend 12 seconds at facility
const facilityAgents = ['scanner','risk','tape','executor','strategy','ws_feed','pos_monitor'];
const facilityLocations = {
  gym:  { x:-4, y:-3.5, z:-2 },
  cafeteria: { x:0.5, y:-3.5, z:-1 },
  rec:  { x:4.5, y:-3.5, z:-1.5 },
  bedrooms: { x:-4.0, y:-7.0, z:-2 },
  bar:  { x:1.0, y:-7.0, z:-2 },
  jacuzzi: { x:4.5, y:-7.0, z:0 },
};
let facilityAgent = null;
let facilityWalking = false;
let facilityWalkFrom = null;
let facilityWalkTo = null;
let facilityWalkStart = null;
let facilityWalkPath = null;
let facilityReturning = false;
let facilityLocation = null;

// Team events — multiple agents go together
const TEAM_EVENT_INTERVAL = 300000; // every 5 minutes
let lastTeamEvent = Date.now() - 240000; // first team event after 1 min
let teamEventActive = false;
let teamEventAgents = [];
let teamEventLocation = null;
let teamEventWalking = [];
let teamEventReturning = false;
let teamEventWalkStart = null;
const TEAM_EVENT_DURATION = 20000; // 20 seconds together
const teamEvents = [
  { name:'Team Lunch', location:'cafeteria', agents:['scanner','risk','tape','executor','strategy','ws_feed','pos_monitor'], dialogue:[
    'Team lunch! Scanner found a good restaurant — just kidding, cafeteria.',
    'Food break — Risk says we\'re within calorie budget.',
    'Lunch time! Even the positions can wait 15 minutes.',
    'Alright team, lunch is ready. Executor, stop watching fills and eat.',
  ]},
  { name:'Team Dinner', location:'cafeteria', agents:['scanner','risk','tape','executor','strategy','ws_feed','pos_monitor'], dialogue:[
    'Dinner time! Long session — we\'ve earned this.',
    'Team dinner. Pos Monitor, leave the exits alone for a bit.',
    'Late night session calls for a good meal. Strategy, stop backtesting and eat.',
    'Dinner break. WS Feed says all connections stable — we can relax.',
  ]},
  { name:'Happy Hour', location:'bar', agents:['scanner','risk','tape','executor','strategy','ws_feed','pos_monitor'], dialogue:[
    'Happy hour! Drinks on Ensemble. Risk says one drink max.',
    'Bar\'s open — first round\'s on the P&L.',
    'Time to unwind. Even Risk Manager is smiling.',
  ]},
  { name:'Team Jacuzzi', location:'jacuzzi', agents:['scanner','risk','tape','executor','pos_monitor'], dialogue:[
    'Jacuzzi break! Leave the charts for 5.',
    'Hot tub time. Pos Monitor, stop checking exits from the tub.',
    'Spa session! Even Executor deserves a break between fills.',
  ]},
  { name:'Gym Session', location:'gym', agents:['scanner','risk','executor','strategy','pos_monitor'], dialogue:[
    'Group workout! Strategy says pullbacks build muscle too.',
    'Gym time — Executor runs fastest, but Scanner spots the best machines.',
    'Team fitness break. Pos Monitor times the sets.',
  ]},
  { name:'Ping Pong Match', location:'rec', agents:['scanner','executor'], dialogue:[
    'Scanner vs Executor — who finds the ball faster vs who hits it harder!',
    'Ping pong! Scanner spots the spin, Executor fires the return.',
  ]},
  { name:'Ping Pong Match', location:'rec', agents:['risk','strategy'], dialogue:[
    'Risk vs Strategy — conservative defense vs aggressive offense!',
    'Ping pong! Risk manages the rally, Strategy picks the shot.',
  ]},
  { name:'Ping Pong Match', location:'rec', agents:['tape','ws_feed'], dialogue:[
    'Tape reads the spin, WS Feed keeps the connection — game on!',
    'Tape vs WS Feed at the table. Latency matters here too.',
  ]},
  { name:'Ping Pong Match', location:'rec', agents:['pos_monitor','ensemble'], dialogue:[
    'Pos Monitor vs Ensemble — exit timing vs confidence gating!',
    'Ping pong! Pos Monitor watches the ball like an open position.',
  ]},
];

// Conference room position (top-level so animation loop can access)
const CONF_X = 3.8, CONF_Z = -3.5;

// Therapy corner position (must be inside PENTHOUSE_RAD = 7.8)
const THERAPY_X = -2.8, THERAPY_Z = 3.5;

// Meeting schedule
const MEETING_INTERVAL = 1800000; // 30 minutes
let lastMeeting = 0;
let inMeeting = false;
let meetingStartTime = 0;
const MEETING_DURATION = 15000; // 15 sec meeting

// Team meeting (all hands)
const TEAM_MEETING_INTERVAL = 3600000; // 1 hour
let lastTeamMeeting = 0;
let inTeamMeeting = false;
const TEAM_MEETING_DURATION = 20000; // 20 sec
const teamMembers = ['scanner','risk','tape','jonas','executor','strategy','ws_feed','pos_monitor'];
const teamMeetingPositions = {
  ensemble:    {x: CONF_X,       z: CONF_Z + 1.0},  // head of table (front center)
  jonas:       {x: CONF_X + 1.5, z: CONF_Z},         // right end
  scanner:     {x: CONF_X - 0.7, z: CONF_Z + 0.8},   // front-left
  risk:        {x: CONF_X + 0.7, z: CONF_Z + 0.8},   // front-right
  tape:        {x: CONF_X - 0.7, z: CONF_Z - 0.8},   // back-left
  executor:    {x: CONF_X + 0.7, z: CONF_Z - 0.8},   // back-right
  strategy:    {x: CONF_X - 1.5, z: CONF_Z},          // left end
  ws_feed:     {x: CONF_X + 1.5, z: CONF_Z - 0.8},   // far-right
  pos_monitor: {x: CONF_X - 1.5, z: CONF_Z - 0.8},   // far-left
};

// ── RENDERER ──
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias:true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(1);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap; // PCFSoft too heavy on integrated GPU
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const css2dRenderer = new CSS2DRenderer();
css2dRenderer.setSize(window.innerWidth, window.innerHeight);
css2dRenderer.domElement.style.position = 'fixed';
css2dRenderer.domElement.style.top = '0';
css2dRenderer.domElement.style.left = '0';
css2dRenderer.domElement.style.pointerEvents = 'none';
document.getElementById('css2d').appendChild(css2dRenderer.domElement);

// Post-processing removed 2026-07-02: the bloom pass chain cost extra full
// passes on integrated GPU and made renderer.info report only the final
// quad pass (calls=1). Direct render + native MSAA instead.
renderer.info.autoReset = false; // reset manually once per frame in animate()

// ── TIME OF DAY ──
// City materials that dim by day / glow at night. Entries: {m, base(opacity)}.
const cityNightMats = [];
let cityGroundMat = null;
let currentHour = new Date().getHours() + new Date().getMinutes()/60;
let lastTimeUpdate = 0;

// Debug-only: ?hour=22 freezes the scene clock at a given hour (verification aid)
const HOUR_OVERRIDE = parseFloat(new URLSearchParams(location.search).get('hour'));
function getTimeOfDay() {
  if (Number.isFinite(HOUR_OVERRIDE)) return HOUR_OVERRIDE;
  const d = new Date();
  return d.getHours() + d.getMinutes()/60;
}

// ── SCENE ──
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x88bbdd);
scene.fog = new THREE.FogExp2(0x9ab5cc, 0.0003);

// ── CAMERA ──
const camera = new THREE.PerspectiveCamera(50, window.innerWidth/window.innerHeight, 0.5, 2000);
// Default view: inside the penthouse at standing eye-level, looking across the
// trading floor and out the glass toward the city. (The old default (2,6,9) sat
// ABOVE the ceiling staring at its gray top — the whole scene looked broken.)
camera.position.set(4.2, 2.4, 6.2);
camera.lookAt(0, 1.0, -1.5);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 0.5;
controls.maxDistance = 500;
controls.maxPolarAngle = Math.PI * 0.95;
controls.minPolarAngle = 0.02;
controls.enablePan = true;
controls.panSpeed = 1.0;
controls.screenSpacePanning = true;
controls.target.set(0, 1.0, -1.5);
controls.zoomSpeed = 1.2;

// ── Right-click drag to move orbit target freely ──
// Middle-click or Ctrl+left-click pans (default OrbitControls)
// Double-click to reset view
renderer.domElement.addEventListener('dblclick', () => {
  controls.target.set(0, 1.0, -1.5);
  camera.position.set(4.2, 2.4, 6.2);
  controls.update();
});

// ── LIGHTS ──
const ambientLight = new THREE.AmbientLight(0xfff5e6, 0.7);
scene.add(ambientLight);

// City glow from outside — warm/cool contrast for depth
const cityGlow = new THREE.HemisphereLight(0x8899bb, 0xdd9966, 0.5);
scene.add(cityGlow);

// Main directional — warm sunset tone for golden hour feel
const dirLight = new THREE.DirectionalLight(0xffcc88, 0.6);
dirLight.position.set(-5, 12, -8);
dirLight.castShadow = true;
dirLight.shadow.mapSize.set(1024,1024);
dirLight.shadow.camera.near = 0.5;
dirLight.shadow.camera.far = 25;
dirLight.shadow.camera.left = -8;
dirLight.shadow.camera.right = 8;
dirLight.shadow.camera.top = 8;
dirLight.shadow.camera.bottom = -8;
dirLight.shadow.bias = -0.001;
dirLight.shadow.normalBias = 0.02;
scene.add(dirLight);

// Ambient city light bounce (warm)
const cityBounce = new THREE.HemisphereLight(0x445577, 0x664422, 0.35);
scene.add(cityBounce);

// Fill light from bay (cool blue reflection)
const bayFill = new THREE.DirectionalLight(0x6699bb, 0.25);
bayFill.position.set(0, 3, -20);
scene.add(bayFill);

// City glow from below at night — warm sodium vapor feel
const nightCityGlow = new THREE.PointLight(0xff9955, 0.0, 200);
nightCityGlow.position.set(0, -5, -80);
scene.add(nightCityGlow);

// ── MATERIALS ──
const floorMat = new THREE.MeshStandardMaterial({ color:0xe8e4e0, roughness:0.8, metalness:0.0 }); // white/cream polished floor
const ceilMat = new THREE.MeshStandardMaterial({ color:0xd0d0d5, roughness:0.9 });
const deskMat = new THREE.MeshPhysicalMaterial({ color:0x3a3838, roughness:0.2, metalness:0.3, clearcoat:0.5, clearcoatRoughness:0.15 }); // dark professional desk
const deskPanelMat = new THREE.MeshStandardMaterial({ color:0x333338, roughness:0.45, metalness:0.15 });
const legMat = new THREE.MeshStandardMaterial({ color:0x888888, roughness:0.25, metalness:0.85 }); // brushed chrome
const chairMat = new THREE.MeshPhysicalMaterial({ color:0x222222, roughness:0.5, metalness:0.03, clearcoat:0.15, clearcoatRoughness:0.7, sheen:0.2, sheenRoughness:0.85, sheenColor:new THREE.Color(0x333333) }); // dark leather
const monFrameMat = new THREE.MeshStandardMaterial({ color:0x111111, roughness:0.2, metalness:0.6 }); // sleek bezels
const lampBaseMat = new THREE.MeshStandardMaterial({ color:0x666666, roughness:0.25, metalness:0.75 });
const lampShadeMat = new THREE.MeshStandardMaterial({ color:0x2a2a2a, roughness:0.65, side:THREE.DoubleSide });
const kbMat = new THREE.MeshStandardMaterial({ color:0x151515, roughness:0.45, metalness:0.25 });
const mouseMat = new THREE.MeshStandardMaterial({ color:0x1a1a1a, roughness:0.35, metalness:0.25 });
const mugMat = new THREE.MeshStandardMaterial({ color:0xddd8d0, roughness:0.35, metalness:0.05 }); // off-white ceramic
const skinMat = new THREE.MeshStandardMaterial({ color:0xd4a882, roughness:0.75, metalness:0.02 }); // natural skin tone

// ── SKY DOME — environment sphere visible when zoomed out ──
let skyDomeMesh = null;

function createSkyDomeTexture(hour) {
  if(hour === undefined) hour = getTimeOfDay();
  const c = document.createElement('canvas');
  c.width = 2048; c.height = 1024;
  const W = 2048, H = 1024;
  const ctx = c.getContext('2d');

  // Reuse the same color-lerp helper
  function lc(a, b, t) {
    const pa = [parseInt(a.slice(1,3),16),parseInt(a.slice(3,5),16),parseInt(a.slice(5,7),16)];
    const pb = [parseInt(b.slice(1,3),16),parseInt(b.slice(3,5),16),parseInt(b.slice(5,7),16)];
    const r = Math.round(pa[0]+(pb[0]-pa[0])*t);
    const g2 = Math.round(pa[1]+(pb[1]-pa[1])*t);
    const b2 = Math.round(pa[2]+(pb[2]-pa[2])*t);
    return '#'+r.toString(16).padStart(2,'0')+g2.toString(16).padStart(2,'0')+b2.toString(16).padStart(2,'0');
  }

  // Time palette (matches panorama)
  const h = ((hour % 24) + 24) % 24;
  let skyTop, skyMid, skyLow, skyHorizon, starAlpha, windowBright;

  if(h >= 21 || h < 5) {
    skyTop='#050810'; skyMid='#0a1428'; skyLow='#101c38'; skyHorizon='#1a2545';
    starAlpha=1.0; windowBright=0.85;
  } else if(h >= 5 && h < 6.5) {
    const t = (h-5)/1.5;
    skyTop=lc('#050810','#1a1535',t); skyMid=lc('#0a1428','#2a2050',t);
    skyLow=lc('#101c38','#6a4060',t); skyHorizon=lc('#1a2545','#ee8855',t);
    starAlpha=1.0-t*0.8; windowBright=0.7-t*0.3;
  } else if(h >= 6.5 && h < 8) {
    const t = (h-6.5)/1.5;
    skyTop=lc('#1a1535','#3a5580',t); skyMid=lc('#2a2050','#5580aa',t);
    skyLow=lc('#6a4060','#88aabb',t); skyHorizon=lc('#ee8855','#ffcc88',t);
    starAlpha=0.2-t*0.2; windowBright=0.35-t*0.1;
  } else if(h >= 8 && h < 11) {
    const t = (h-8)/3;
    skyTop=lc('#3a5580','#2266bb',t); skyMid=lc('#5580aa','#55aadd',t);
    skyLow=lc('#88aabb','#88ccee',t); skyHorizon=lc('#ffcc88','#aaddee',t);
    starAlpha=0; windowBright=0.15;
  } else if(h >= 11 && h < 16) {
    skyTop='#1155aa'; skyMid='#3399dd'; skyLow='#66bbee'; skyHorizon='#99ddff';
    starAlpha=0; windowBright=0.1;
  } else if(h >= 16 && h < 18.5) {
    const t = (h-16)/2.5;
    skyTop=lc('#1155aa','#1a2550',t); skyMid=lc('#3399dd','#4a5580',t);
    skyLow=lc('#66bbee','#886655',t); skyHorizon=lc('#99ddff','#ee8844',t);
    starAlpha=t*0.3; windowBright=0.15+t*0.5;
  } else if(h >= 18.5 && h < 21) {
    const t = (h-18.5)/2.5;
    skyTop=lc('#1a2550','#0c1528',t); skyMid=lc('#4a5580','#152040',t);
    skyLow=lc('#886655','#253050',t); skyHorizon=lc('#ee8844','#2a3555',t);
    starAlpha=0.3+t*0.7; windowBright=0.65+t*0.2;
  }

  const isDaytime = h >= 7 && h < 17;
  const wb = windowBright;

  // Sky gradient — top of texture is zenith, middle is horizon
  const skyG = ctx.createLinearGradient(0, 0, 0, H * 0.55);
  skyG.addColorStop(0, skyTop);
  skyG.addColorStop(0.3, skyMid);
  skyG.addColorStop(0.65, skyLow);
  skyG.addColorStop(1.0, skyHorizon);
  ctx.fillStyle = skyG;
  ctx.fillRect(0, 0, W, H * 0.55);

  // Below horizon — darker ground/city band
  const groundG = ctx.createLinearGradient(0, H * 0.55, 0, H);
  groundG.addColorStop(0, skyHorizon);
  groundG.addColorStop(0.15, isDaytime ? '#556677' : '#0e1520');
  groundG.addColorStop(1, isDaytime ? '#445566' : '#080c14');
  ctx.fillStyle = groundG;
  ctx.fillRect(0, H * 0.55, W, H * 0.45);

  // Atmospheric haze bands near horizon
  for(let band = 0; band < 5; band++) {
    const bandY = H * 0.48 + band * H * 0.025;
    const bandAlpha = (0.03 + band * 0.015) * (isDaytime ? 1.0 : 0.6);
    const hazeColor = isDaytime ? '180,200,220' : '30,50,80';
    const hazeG = ctx.createLinearGradient(0, bandY, 0, bandY + H * 0.04);
    hazeG.addColorStop(0, 'rgba('+hazeColor+',0)');
    hazeG.addColorStop(0.5, 'rgba('+hazeColor+','+bandAlpha+')');
    hazeG.addColorStop(1, 'rgba('+hazeColor+',0)');
    ctx.fillStyle = hazeG;
    ctx.fillRect(0, bandY, W, H * 0.04);
  }

  // Stars — 600 with size variety and twinkle colors
  if(starAlpha > 0.05) {
    for(let i = 0; i < 600; i++) {
      const sy = Math.random() * H * 0.4;
      const a = (0.3 + Math.random() * 0.7) * starAlpha;
      // Twinkle colors: warm white, cool blue, pale yellow
      const colorRoll = Math.random();
      let sr, sg2, sb;
      if(colorRoll < 0.5) { sr=255; sg2=255; sb=220+Math.random()*35; } // warm white
      else if(colorRoll < 0.75) { sr=180+Math.random()*40; sg2=200+Math.random()*30; sb=255; } // cool blue
      else { sr=255; sg2=240+Math.random()*15; sb=180+Math.random()*40; } // pale yellow
      ctx.fillStyle = 'rgba('+Math.floor(sr)+','+Math.floor(sg2)+','+Math.floor(sb)+','+a+')';
      const s = Math.random() > 0.92 ? 4 : Math.random() > 0.8 ? 3 : Math.random() > 0.5 ? 2 : 1;
      ctx.fillRect(Math.random() * W, sy, s, s);
    }
  }

  // Sun/moon
  if(h >= 6 && h < 18.5) {
    const sunProgress = (h - 6) / 12.5;
    const sunX = W * (0.3 + sunProgress * 0.4);
    const sunY = H * 0.55 - Math.sin(sunProgress * Math.PI) * H * 0.4;
    const sunSize = h > 7 && h < 17 ? 16 : 22;
    const sunColor = h < 8 || h > 16.5 ? '#ffaa44' : '#ffffcc';
    ctx.fillStyle = sunColor;
    ctx.beginPath(); ctx.arc(sunX, sunY, sunSize, 0, Math.PI * 2); ctx.fill();
    const sg = ctx.createRadialGradient(sunX, sunY, sunSize, sunX, sunY, sunSize * 5);
    sg.addColorStop(0, h < 8 || h > 16.5 ? 'rgba(255,180,80,0.25)' : 'rgba(255,255,200,0.12)');
    sg.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = sg; ctx.fillRect(0, 0, W, H);
  } else if(starAlpha > 0.3) {
    const moonX = W * 0.7; const moonY = H * 0.12;
    ctx.fillStyle = 'rgba(220,225,240,' + (starAlpha * 0.9) + ')';
    ctx.beginPath(); ctx.arc(moonX, moonY, 10, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(200,210,230,' + (starAlpha * 0.1) + ')';
    ctx.beginPath(); ctx.arc(moonX, moonY, 25, 0, Math.PI * 2); ctx.fill();
  }

  // Clouds
  if(h >= 6 && h < 20) {
    const cloudAlpha = 0.04 + (h > 16 ? 0.06 : 0);
    for(let i = 0; i < 12; i++) {
      const cx = Math.random() * W;
      const cy = H * 0.12 + Math.random() * H * 0.25;
      const cw = 40 + Math.random() * 100;
      const cloudColor = h > 16.5 ? 'rgba(255,180,120,' + cloudAlpha + ')' : 'rgba(255,255,255,' + cloudAlpha + ')';
      ctx.fillStyle = cloudColor;
      ctx.beginPath();
      ctx.ellipse(cx, cy, cw, 6 + Math.random() * 10, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Distant city silhouette at horizon
  const horizY = Math.floor(H * 0.55);
  for(let x = 0; x < W; x += 6 + Math.random() * 10) {
    const bh = (5 + Math.random() * 30) * (0.5 + 0.5 * Math.sin(x * 0.005));
    ctx.fillStyle = isDaytime ? 'rgba(80,95,110,0.5)' : 'rgba(15,20,30,0.8)';
    ctx.fillRect(x, horizY - bh, 4 + Math.random() * 6, bh + 4);
    if(wb > 0.15) {
      for(let wy = horizY - bh + 2; wy < horizY; wy += 4) {
        if(Math.random() > 0.5) {
          ctx.fillStyle = 'rgba(255,' + (200 + Math.random() * 55) + ',' + (80 + Math.random() * 80) + ',' + (wb * 0.4) + ')';
          ctx.fillRect(x + 1, wy, 2, 2);
        }
      }
    }
  }

  return new THREE.CanvasTexture(c);
}

function createSkyDome(hour) {
  const tex = createSkyDomeTexture(hour);
  const geo = new THREE.SphereGeometry(500, 48, 24);
  const mat = new THREE.MeshBasicMaterial({
    map: tex,
    side: THREE.BackSide,
    fog: false,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.renderOrder = -1;
  return mesh;
}

// ── ROOM — Salesforce-style high-rise ──
const ROOM_W = 12, ROOM_D = 10, ROOM_H = 4.0;

// Polished dark concrete floor — circular to match tower cylinder
const PENTHOUSE_RAD = ROOM_W * 0.65; // match towerRadTop
{
  const floorShape = new THREE.Shape();
  // Outer circle (matches tower cylinder radius)
  const segs = 48;
  for(let i = 0; i <= segs; i++) {
    const a = (i / segs) * Math.PI * 2;
    const px = Math.cos(a) * PENTHOUSE_RAD;
    const py = Math.sin(a) * PENTHOUSE_RAD;
    if(i === 0) floorShape.moveTo(px, py);
    else floorShape.lineTo(px, py);
  }
  // Stairwell hole at main→B1 stair position (world X [-5.5,-3.5], world Z [2.5,4.5])
  // Shape Y maps to world -Z under rotation.x=-π/2, so use shape Y [-4.5,-2.5]
  const phHole = new THREE.Path();
  phHole.moveTo(-5.5, -4.5);
  phHole.lineTo(-3.5, -4.5);
  phHole.lineTo(-3.5, -2.5);
  phHole.lineTo(-5.5, -2.5);
  phHole.lineTo(-5.5, -4.5);
  floorShape.holes.push(phHole);
  const floorGeo = new THREE.ShapeGeometry(floorShape);
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI/2;
  floor.receiveShadow = true;
  scene.add(floor);

  // Note: stairwell safety railings removed — stairs are outside cylinder radius
}

// Subtle floor grid — radial lines for circular floor
const floorLines = new THREE.Group();
const gridLineMat = new THREE.LineBasicMaterial({color:0x6a6a68, transparent:true, opacity:0.2});
// Concentric rings
for(let r = 1.0; r <= PENTHOUSE_RAD; r += 1.0) {
  const pts = [];
  for(let i = 0; i <= 48; i++) {
    const a = (i / 48) * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a)*r, 0.002, Math.sin(a)*r));
  }
  floorLines.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridLineMat));
}
// Radial spokes every 30 degrees
for(let i = 0; i < 12; i++) {
  const a = (i / 12) * Math.PI * 2;
  const g = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0.002, 0),
    new THREE.Vector3(Math.cos(a)*PENTHOUSE_RAD, 0.002, Math.sin(a)*PENTHOUSE_RAD)
  ]);
  floorLines.add(new THREE.Line(g, gridLineMat));
}
scene.add(floorLines);

// Modern ceiling — circular to match tower cylinder
const ceiling = new THREE.Mesh(new THREE.CircleGeometry(PENTHOUSE_RAD, 48), ceilMat);
ceiling.rotation.x = Math.PI/2;
ceiling.position.set(0, ROOM_H, 0);
scene.add(ceiling);

// LED strip lights in ceiling (linear)
const ledMat = new THREE.MeshBasicMaterial({color:0xffffff, transparent:true, opacity:0.9});
const ceilingLEDs = [];    // mesh refs for dimming
const ceilingStrips = [];  // RectAreaLight refs
const ceilingSpots = [];   // PointLight refs
const ceilingSpotMeshes = []; // spot mesh refs
for(let x=-3;x<=3;x+=3){
  // Clip LED strip length to fit inside the cylinder at this x offset
  const maxZ = Math.sqrt(PENTHOUSE_RAD * PENTHOUSE_RAD - x * x) || 0;
  const stripLen = Math.min(ROOM_D - 1, maxZ * 2 - 0.5);
  const led = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.01, stripLen), ledMat.clone());
  led.position.set(x, ROOM_H-0.01, 0);
  scene.add(led);
  ceilingLEDs.push(led);
  // Soft light from strip
  const stripLight = new THREE.RectAreaLight(0xfff8ee, 1.2, 0.06, stripLen);
  stripLight.position.set(x, ROOM_H-0.02, 0);
  stripLight.rotation.x = Math.PI/2;
  scene.add(stripLight);
  ceilingStrips.push(stripLight);
}

// Recessed downlights — reduced grid for performance (4 lights instead of 12)
for(let x=-3;x<=3;x+=6){
  for(let z=-2;z<=2;z+=4){
    const spotGeo = new THREE.CylinderGeometry(0.06, 0.08, 0.03, 6);
    const spotMat2 = new THREE.MeshStandardMaterial({color:0xffffff, emissive:0xffffff, emissiveIntensity:0.8});
    const spotMesh = new THREE.Mesh(spotGeo, spotMat2);
    spotMesh.position.set(x, ROOM_H-0.02, z);
    scene.add(spotMesh);
    ceilingSpotMeshes.push(spotMesh);
    const dl = new THREE.PointLight(0xfff5e6, 0.3, 6);
    dl.position.set(x, ROOM_H-0.05, z);
    scene.add(dl);
    ceilingSpots.push(dl);
  }
}

// ── FLOOR-TO-CEILING GLASS WALLS WITH SF PANORAMA ──
const glassMat = new THREE.MeshPhysicalMaterial({
  color:0x88aacc, transparent:true, opacity:0.06,
  roughness:0.04, metalness:0.12, side:THREE.DoubleSide,
  // NO transmission: it forces a per-frame scene-color-buffer grab (extra full
  // render pass) on integrated GPUs — violates the smoothness-wins rule.
  reflectivity:0.7, envMapIntensity:1.0,
});
const frameMat = new THREE.MeshStandardMaterial({color:0x334450, metalness:0.7, roughness:0.3});

// Create sky dome
skyDomeMesh = createSkyDome(currentHour);
scene.add(skyDomeMesh);

// Curved glass wall segments — 4 quadrants matching the tower cylinder
// Each quadrant is a 90-degree arc of a CylinderGeometry
const wallQuadrants = [
  { facing:'north', startAngle: Math.PI * 0.75 },
  { facing:'east',  startAngle: Math.PI * 0.25 },
  { facing:'south', startAngle: Math.PI * 1.75 },
  { facing:'west',  startAngle: Math.PI * 1.25 },
];

wallQuadrants.forEach(wq => {
  const arcAngle = Math.PI / 2;
  const arcSegs = 16;


  // Glass pane — slightly in front of panorama
  const glassGeo = new THREE.CylinderGeometry(
    PENTHOUSE_RAD, PENTHOUSE_RAD, ROOM_H, arcSegs, 1, true, wq.startAngle, arcAngle
  );
  const glassPane = new THREE.Mesh(glassGeo, glassMat);
  glassPane.position.set(0, ROOM_H / 2, 0);
  scene.add(glassPane);

  // Vertical mullions along the arc
  const numMullions = 6;
  for (let i = 0; i <= numMullions; i++) {
    const a = wq.startAngle + (i / numMullions) * arcAngle;
    const mx = Math.cos(a) * PENTHOUSE_RAD;
    const mz = Math.sin(a) * PENTHOUSE_RAD;
    const mullion = new THREE.Mesh(new THREE.BoxGeometry(0.03, ROOM_H, 0.03), frameMat);
    mullion.position.set(mx, ROOM_H / 2, mz);
    mullion.rotation.y = -a;
    scene.add(mullion);
  }
});

// Top and bottom ring frames for glass walls
for (const fy of [0, ROOM_H]) {
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(PENTHOUSE_RAD, 0.02, 8, 48),
    frameMat
  );
  ring.rotation.x = Math.PI / 2;
  ring.position.set(0, fy, 0);
  scene.add(ring);
}



// ── STRUCTURAL COLUMNS (evenly spaced around cylinder, floor to ceiling) ──
const colMat = new THREE.MeshStandardMaterial({color:0x2a2e33, metalness:0.8, roughness:0.3});
const colGeo = new THREE.BoxGeometry(0.15, ROOM_H, 0.15);
// Place 4 columns at quadrant boundaries (where wall segments meet)
for (let i = 0; i < 4; i++) {
  const a = Math.PI * 0.25 + i * Math.PI / 2; // 45, 135, 225, 315 degrees
  const col = new THREE.Mesh(colGeo, colMat);
  col.position.set(Math.cos(a) * PENTHOUSE_RAD, ROOM_H / 2, Math.sin(a) * PENTHOUSE_RAD);
  col.rotation.y = -a;
  scene.add(col);
}
// Top beam — circular ring instead of straight beams
const beamMat = colMat;
const beamRing = new THREE.Mesh(
  new THREE.TorusGeometry(PENTHOUSE_RAD, 0.05, 8, 48),
  beamMat
);
beamRing.rotation.x = Math.PI / 2;
beamRing.position.set(0, ROOM_H - 0.04, 0);
scene.add(beamRing);

// ── SALESFORCE TOWER BODY BELOW OFFICE ──
{
  const TOWER_H = 50;
  const towerW = ROOM_W + 1;
  const towerD = ROOM_D + 1;
  const towerGroup = new THREE.Group();

  // Curved tower radii — tapered cylinder (Salesforce Tower inspired)
  const towerRadTop = ROOM_W * 0.65;
  const towerRadBot = ROOM_W * 0.72;

  // Main tower body — bright reflective glass like the real Salesforce Tower
  const towerMat = new THREE.MeshPhysicalMaterial({
    color:0xc8ddf0, roughness:0.03, metalness:0.35,
    transparent:true, opacity:0.78, side:THREE.DoubleSide,
    clearcoat:1.0, clearcoatRoughness:0.02,
    envMapIntensity:2.0,
    reflectivity:0.9,
  });
  // Thin floor slabs between levels (light concrete accent lines)
  const slabMat = new THREE.MeshStandardMaterial({color:0x8a9aaa, roughness:0.5, metalness:0.3, side:THREE.DoubleSide});
  // Slab between main floor (y:0) and B1 ceiling (y:-0.3) — circular disc
  const slabRad = towerRadBot * 1.01;
  const towerSlab1 = new THREE.Mesh(new THREE.CylinderGeometry(slabRad, slabRad, 0.08, 32), slabMat);
  towerSlab1.position.set(0, -0.15, 0);
  towerGroup.add(towerSlab1);
  // Slab between B1 floor (y:-3.5) and B2 ceiling (y:-3.8)
  const towerSlab2 = new THREE.Mesh(new THREE.CylinderGeometry(slabRad, slabRad, 0.08, 32), slabMat);
  towerSlab2.position.set(0, -3.65, 0);
  towerGroup.add(towerSlab2);
  // Curved tower body below B2 floor (y:-7.0 downward) — tapered cylinder
  const BELOW_B2 = TOWER_H - 7.0; // 43 units
  // Interpolate radii: at y=-7 we're ~14% down the tower, at bottom 100%
  const radAtB2 = towerRadTop + (towerRadBot - towerRadTop) * (7.0 / TOWER_H);
  const towerBotGeo = new THREE.CylinderGeometry(radAtB2, towerRadBot, BELOW_B2, 32);
  const towerBot = new THREE.Mesh(towerBotGeo, towerMat);
  towerBot.position.set(0, -7.0 - BELOW_B2/2, 0);
  towerGroup.add(towerBot);
  // ── B1 + B2 CURVED GLASS WALLS ──
  const lfBandFrameMat = new THREE.MeshStandardMaterial({color:0x6a7a8a, metalness:0.8, roughness:0.2});
  // B1 glass cylinder (y:-0.3 to y:-3.5)
  const lfBandH = 3.2;
  const lfBandY = -0.3 - lfBandH/2;
  const b1Glass = new THREE.Mesh(
    new THREE.CylinderGeometry(slabRad + 0.01, slabRad + 0.01, lfBandH, 32, 1, true),
    glassMat
  );
  b1Glass.position.set(0, lfBandY, 0);
  towerGroup.add(b1Glass);
  // B1 mullions around the cylinder
  const numB1Mullions = 24;
  for(let i = 0; i < numB1Mullions; i++) {
    const a = (i / numB1Mullions) * Math.PI * 2;
    const mx = Math.cos(a) * (slabRad + 0.02);
    const mz = Math.sin(a) * (slabRad + 0.02);
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.04, lfBandH, 0.04), lfBandFrameMat);
    m.position.set(mx, lfBandY, mz);
    m.rotation.y = -a;
    towerGroup.add(m);
  }
  // B1 horizontal ring frames at top/bottom
  for(const fy of [-0.3, -3.5]) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(slabRad + 0.02, 0.03, 8, 32),
      lfBandFrameMat
    );
    ring.rotation.x = Math.PI/2;
    ring.position.set(0, fy, 0);
    towerGroup.add(ring);
  }
  // B2 glass cylinder (y:-3.8 to y:-7.0)
  const b2BandH = 3.2;
  const b2BandY = -3.8 - b2BandH/2;
  const b2Glass = new THREE.Mesh(
    new THREE.CylinderGeometry(slabRad + 0.01, slabRad + 0.01, b2BandH, 32, 1, true),
    glassMat
  );
  b2Glass.position.set(0, b2BandY, 0);
  towerGroup.add(b2Glass);
  // B2 mullions
  for(let i = 0; i < numB1Mullions; i++) {
    const a = (i / numB1Mullions) * Math.PI * 2;
    const mx = Math.cos(a) * (slabRad + 0.02);
    const mz = Math.sin(a) * (slabRad + 0.02);
    const m2 = new THREE.Mesh(new THREE.BoxGeometry(0.04, b2BandH, 0.04), lfBandFrameMat);
    m2.position.set(mx, b2BandY, mz);
    m2.rotation.y = -a;
    towerGroup.add(m2);
  }
  // B2 horizontal ring frames
  for(const fy of [-3.8, -7.0]) {
    const ring2 = new THREE.Mesh(
      new THREE.TorusGeometry(slabRad + 0.02, 0.03, 8, 32),
      lfBandFrameMat
    );
    ring2.rotation.x = Math.PI/2;
    ring2.position.set(0, fy, 0);
    towerGroup.add(ring2);
  }

  // Crown ring at office floor level — circular torus
  const crownMat = new THREE.MeshStandardMaterial({color:0x9aacbc, metalness:0.9, roughness:0.1});
  const crown = new THREE.Mesh(new THREE.TorusGeometry(slabRad + 0.15, 0.12, 8, 32), crownMat);
  crown.rotation.x = Math.PI/2;
  crown.position.set(0, -0.12, 0);
  towerGroup.add(crown);
  // Second crown lip
  const crown2 = new THREE.Mesh(new THREE.TorusGeometry(slabRad + 0.08, 0.06, 8, 32), crownMat);
  crown2.rotation.x = Math.PI/2;
  crown2.position.set(0, 0.05, 0);
  towerGroup.add(crown2);
  // Crown rings at B1 and B2 levels
  const b1Crown = new THREE.Mesh(new THREE.TorusGeometry(slabRad + 0.15, 0.08, 8, 32), crownMat);
  b1Crown.rotation.x = Math.PI/2;
  b1Crown.position.set(0, -3.5, 0);
  towerGroup.add(b1Crown);
  const b2Crown = new THREE.Mesh(new THREE.TorusGeometry(slabRad + 0.15, 0.08, 8, 32), crownMat);
  b2Crown.rotation.x = Math.PI/2;
  b2Crown.position.set(0, -7.0, 0);
  towerGroup.add(b2Crown);

  // Horizontal ring lines on tower surface (every 0.8 units)
  // Skip B1 (y:-0.3 to -3.5) and B2 (y:-3.8 to -7.0) zones
  const lineMat = new THREE.LineBasicMaterial({color:0x0d1520, transparent:true, opacity:0.6});
  for(let y = -0.8; y > -TOWER_H; y -= 0.8) {
    if(y > -7.2 && y < -0.2) continue; // skip B1+B2 zone
    // Interpolate radius at this height (y=0 is top of tower body, y=-TOWER_H is bottom)
    const t = Math.abs(y) / TOWER_H;
    const ringR = towerRadTop + (towerRadBot - towerRadTop) * t + 0.02;
    const ringPts = [];
    const ringSegs = 48;
    for(let s = 0; s <= ringSegs; s++) {
      const a = (s / ringSegs) * Math.PI * 2;
      ringPts.push(new THREE.Vector3(Math.cos(a) * ringR, y, Math.sin(a) * ringR));
    }
    const g = new THREE.BufferGeometry().setFromPoints(ringPts);
    towerGroup.add(new THREE.Line(g, lineMat));
  }

  // Lit windows around the cylinder surface — small warm rectangles
  const winGeo = new THREE.PlaneGeometry(0.22, 0.35);
  const winLitMat = new THREE.MeshBasicMaterial({color:0xffe8b0, transparent:true, opacity:0.7, side:THREE.DoubleSide});
  const winDarkMat = new THREE.MeshBasicMaterial({color:0x1a2535, transparent:true, opacity:0.15, side:THREE.DoubleSide});
  const winGroup = new THREE.Group();
  const winCols = 36; // windows around circumference
  for(let c = 0; c < winCols; c++) {
    const a = (c / winCols) * Math.PI * 2;
    for(let y = -1.2; y > -TOWER_H + 2; y -= 0.8) {
      if(y > -7.2 && y < -0.2) continue; // skip B1+B2 clear glass zone
      if(Math.random() < 0.55) continue; // skip many for performance
      const t = Math.abs(y) / TOWER_H;
      const r = towerRadTop + (towerRadBot - towerRadTop) * t + 0.03;
      const isLit = Math.random() > 0.4;
      const win = new THREE.Mesh(winGeo, isLit ? winLitMat : winDarkMat);
      win.position.set(Math.cos(a) * r, y, Math.sin(a) * r);
      win.rotation.y = -a + Math.PI/2;
      winGroup.add(win);
    }
  }
  towerGroup.add(winGroup);

  // ── CURVED TOWER TOP (above office) ──
  // Tapered cylinder floors above the main office, narrowing to a smooth dome
  const topFloors = 8;
  const topH = topFloors * 0.8;  // 6.4 units above ceiling
  // Tapered upper section — cylinder floors narrowing toward the top
  for(let i = 0; i < topFloors; i++) {
    const t = i / topFloors;
    const taper = 1.0 - t * 0.35;
    const floorRad = towerRadTop * taper;
    const fy = ROOM_H + i * 0.8;
    // Circular floor slab
    const floorSlab = new THREE.Mesh(
      new THREE.CylinderGeometry(floorRad, floorRad, 0.06, 32),
      new THREE.MeshStandardMaterial({color:0x9aacbc, metalness:0.5, roughness:0.35})
    );
    floorSlab.position.set(0, fy, 0);
    towerGroup.add(floorSlab);
    // Glass curtain cylinder wall per floor
    const glassMat2 = new THREE.MeshPhysicalMaterial({color:0x9ac0dd, transparent:true, opacity:0.3, roughness:0.03, metalness:0.25, side:THREE.DoubleSide, clearcoat:0.8, clearcoatRoughness:0.05, envMapIntensity:1.5});
    const glassWall = new THREE.Mesh(
      new THREE.CylinderGeometry(floorRad + 0.01, floorRad + 0.01, 0.75, 32, 1, true),
      glassMat2
    );
    glassWall.position.set(0, fy + 0.45, 0);
    towerGroup.add(glassWall);
    // Some lit windows around the circumference
    if(i < topFloors - 2) {
      const nWin = 16;
      for(let w = 0; w < nWin; w++) {
        if(Math.random() < 0.4) continue;
        const wa = (w / nWin) * Math.PI * 2;
        const win = new THREE.Mesh(new THREE.PlaneGeometry(0.18, 0.3), winLitMat);
        win.position.set(Math.cos(wa) * (floorRad + 0.02), fy + 0.45, Math.sin(wa) * (floorRad + 0.02));
        win.rotation.y = -wa + Math.PI/2;
        towerGroup.add(win);
      }
    }
  }
  // Smooth dome crown — hemisphere cap
  const domeY = ROOM_H + topH;
  const domeRad = towerRadTop * 0.55;
  const domeMat = new THREE.MeshPhysicalMaterial({color:0xa8ddff, metalness:0.3, roughness:0.02, transparent:true, opacity:0.4, clearcoat:1.0, clearcoatRoughness:0.01, envMapIntensity:2.5, reflectivity:1.0});
  const dome = new THREE.Mesh(new THREE.SphereGeometry(domeRad, 32, 16, 0, Math.PI*2, 0, Math.PI/2), domeMat);
  dome.position.set(0, domeY, 0);
  towerGroup.add(dome);
  // Structural ring at dome base
  const domeRing = new THREE.Mesh(
    new THREE.TorusGeometry(domeRad, 0.08, 8, 32),
    new THREE.MeshStandardMaterial({color:0x8899aa, metalness:0.85, roughness:0.15})
  );
  domeRing.rotation.x = Math.PI/2;
  domeRing.position.set(0, domeY, 0);
  towerGroup.add(domeRing);
  // LED light crown around the dome
  const ledColors = [0x4488ff, 0x44ddff, 0x88aaff, 0x66ccff];
  for(let a = 0; a < Math.PI*2; a += Math.PI/12) {
    const lx = Math.cos(a) * (domeRad - 0.1);
    const lz = Math.sin(a) * (domeRad - 0.1);
    const ledLight = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.3, 0.06),
      new THREE.MeshBasicMaterial({color: ledColors[Math.floor(Math.random()*ledColors.length)]})
    );
    ledLight.position.set(lx, domeY + 0.3, lz);
    towerGroup.add(ledLight);
  }
  // Beacon light at very top
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.15, 8, 8), new THREE.MeshBasicMaterial({color:0xff3333}));
  beacon.position.set(0, domeY + domeRad*0.5 + 0.5, 0);
  towerGroup.add(beacon);
  const beaconGlow = new THREE.PointLight(0xff3333, 0.5, 8);
  beaconGlow.position.copy(beacon.position);
  towerGroup.add(beaconGlow);

  scene.add(towerGroup);

  // ── LOWER FLOORS VISIBLE THROUGH GLASS ──
  // Skip -4 and -8 — those are real B1 (gym/caf/rec) and B2 (bed/bar/jacuzzi) floors
  const lowerFloorMat = new THREE.MeshStandardMaterial({color:0x555550, roughness:0.4, metalness:0.1});
  const lowerCeilMat = new THREE.MeshStandardMaterial({color:0x3a3a40, roughness:0.9});
  [-12, -16, -20].forEach(yOff => {
    // Floor slab
    const lf = new THREE.Mesh(new THREE.CircleGeometry(ROOM_W * 0.70, 32), lowerFloorMat);
    lf.rotation.x = -Math.PI/2;
    lf.position.set(0, yOff, 0);
    scene.add(lf);
    // Ceiling of that floor
    const lc = new THREE.Mesh(new THREE.CircleGeometry(ROOM_W * 0.70, 32), lowerCeilMat);
    lc.rotation.x = Math.PI/2;
    lc.position.set(0, yOff + ROOM_H - 0.1, 0);
    scene.add(lc);
    // Dim interior light
    const ll = new THREE.PointLight(0xffeedd, 0.15, 8);
    ll.position.set(0, yOff + 3, 0);
    scene.add(ll);
    // Furniture silhouettes (simple dark boxes suggesting desks)
    const furniMat = new THREE.MeshStandardMaterial({color:0x222225, roughness:0.6});
    for(let fx = -3; fx <= 3; fx += 3) {
      for(let fz = -2; fz <= 2; fz += 2.5) {
        const desk = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.04, 0.5), furniMat);
        desk.position.set(fx, yOff + 0.75, fz);
        scene.add(desk);
      }
    }
  });
}

// ══════════════════════════════════════════════════════
// LOWER FLOOR — Gym, Cafeteria, Recreation (Y = -3.5)
// ══════════════════════════════════════════════════════
{
  const LF_Y = -3.5; // lower floor level

  // Floor plane — with stairwell hole for B1→B2 stairs
  const lfFloorMat = new THREE.MeshStandardMaterial({color:0x5a5a62, roughness:0.7, metalness:0.05, side:THREE.DoubleSide, polygonOffset:true, polygonOffsetFactor:-1, polygonOffsetUnits:-1});
  {
    const lfFloorShape = new THREE.Shape();
    const lfR = ROOM_W * 0.70;
    for(let i = 0; i <= 32; i++) {
      const a = (i / 32) * Math.PI * 2;
      if(i === 0) lfFloorShape.moveTo(Math.cos(a) * lfR, Math.sin(a) * lfR);
      else lfFloorShape.lineTo(Math.cos(a) * lfR, Math.sin(a) * lfR);
    }
    // Stairwell hole at same position as main→B1 stairs
    const lfHole = new THREE.Path();
    lfHole.moveTo(-5.5, 2.5);
    lfHole.lineTo(-3.5, 2.5);
    lfHole.lineTo(-3.5, 4.5);
    lfHole.lineTo(-5.5, 4.5);
    lfHole.lineTo(-5.5, 2.5);
    lfFloorShape.holes.push(lfHole);
    const lfFloor = new THREE.Mesh(new THREE.ShapeGeometry(lfFloorShape), lfFloorMat);
    lfFloor.rotation.x = -Math.PI/2;
    lfFloor.position.set(0, LF_Y, 0);
    lfFloor.receiveShadow = true;
    scene.add(lfFloor);
  }

  // B1 ceiling removed — tower slab between main floor and B1 handles this

  // B1 glass walls removed — tower exterior glass bands provide the windows
  // Only keep frame material reference for other uses
  const lfFrameMat = new THREE.MeshStandardMaterial({color:0x334450, metalness:0.7, roughness:0.3});
  const LF_H = 3.2;

  // Lighting
  // Bright ceiling strip lights (like a real office/gym)
  // B1 lighting — 3 lights (reduced from 9 for performance)
  const lfLight1 = new THREE.PointLight(0xffffff, 0.8, 12);
  lfLight1.position.set(-3, LF_Y + 2.8, 0);
  scene.add(lfLight1);
  const lfLight2 = new THREE.PointLight(0xffffff, 0.8, 12);
  lfLight2.position.set(3, LF_Y + 2.8, 0);
  scene.add(lfLight2);
  const lfLight3 = new THREE.PointLight(0xffffff, 0.6, 10);
  lfLight3.position.set(0, LF_Y + 2.8, -3);
  scene.add(lfLight3);
  // Visible ceiling light panels (glowing rectangles)
  const lfLightPanelMat = new THREE.MeshBasicMaterial({color:0xeeeeff});
  for(let lx = -5; lx <= 5; lx += 3.3) {
    for(let lz = -3; lz <= 3; lz += 3) {
      const lPanel = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.03, 0.6), lfLightPanelMat);
      lPanel.position.set(lx, LF_Y + 3.18, lz);
      scene.add(lPanel);
    }
  }

  // B1 front glass wall removed — tower exterior glass band handles it

  // ── STAIRCASE (connects main floor to lower floor) ──
  // Located at x:-5.5, z:4.5 (front-left corner of main floor)
  const stairMat = new THREE.MeshStandardMaterial({color:0x556677, roughness:0.4, metalness:0.5});
  const railMat = new THREE.MeshStandardMaterial({color:0x667788, roughness:0.3, metalness:0.6});
  const STAIR_X = -5.5, STAIR_Z = 4.5;
  const STAIR_STEPS = 12;
  const stepHeight = 3.5 / STAIR_STEPS;
  const stepDepth = 0.35;

  for(let s = 0; s < STAIR_STEPS; s++) {
    const step = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.08, stepDepth), stairMat);
    step.position.set(STAIR_X, -s * stepHeight, STAIR_Z - s * stepDepth);
    step.receiveShadow = true;
    scene.add(step);
  }
  // Railing (left side)
  for(let s = 0; s < STAIR_STEPS; s += 3) {
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.6, 4), railMat);
    post.position.set(STAIR_X - 0.6, -s * stepHeight + 0.3, STAIR_Z - s * stepDepth);
    scene.add(post);
  }
  // Railing (right side)
  for(let s = 0; s < STAIR_STEPS; s += 3) {
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.6, 4), railMat);
    post.position.set(STAIR_X + 0.6, -s * stepHeight + 0.3, STAIR_Z - s * stepDepth);
    scene.add(post);
  }
  // Handrails (continuous bars)
  const hrGeo = new THREE.CylinderGeometry(0.015, 0.015, 5.5, 4);
  const hrLeft = new THREE.Mesh(hrGeo, railMat);
  hrLeft.position.set(STAIR_X - 0.6, -1.45, STAIR_Z - 2.1);
  hrLeft.rotation.x = Math.atan2(3.5, STAIR_STEPS * stepDepth);
  scene.add(hrLeft);
  const hrRight = hrLeft.clone();
  hrRight.position.x = STAIR_X + 0.6;
  scene.add(hrRight);

  // "STAIRS" sign
  const stairSignCnv = document.createElement('canvas');
  stairSignCnv.width = 96; stairSignCnv.height = 24;
  const stairSignCtx = stairSignCnv.getContext('2d');
  stairSignCtx.fillStyle = '#1a2744';
  stairSignCtx.fillRect(0,0,96,24);
  stairSignCtx.fillStyle = '#88ccff';
  stairSignCtx.font = 'bold 12px sans-serif';
  stairSignCtx.textAlign = 'center';
  stairSignCtx.fillText('\u2193 STAIRS', 48, 18);
  const stairSignTex = new THREE.CanvasTexture(stairSignCnv);
  const stairSign = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 0.1), new THREE.MeshBasicMaterial({map:stairSignTex}));
  stairSign.position.set(STAIR_X, 1.4, STAIR_Z + 0.3);
  scene.add(stairSign);

  // ── GYM (left section: x:-6 to -2, z:-5 to 0) ──
  const GYM_X = -4, GYM_Z = -2;

  // "GYM" sign on wall
  const gymSignCnv = document.createElement('canvas');
  gymSignCnv.width = 96; gymSignCnv.height = 32;
  const gymSignCtx = gymSignCnv.getContext('2d');
  gymSignCtx.fillStyle = '#1a2744';
  gymSignCtx.fillRect(0,0,96,32);
  gymSignCtx.fillStyle = '#cc8866';
  gymSignCtx.font = 'bold 16px sans-serif';
  gymSignCtx.textAlign = 'center';
  gymSignCtx.fillText('GYM', 48, 24);
  const gymSignTex = new THREE.CanvasTexture(gymSignCnv);
  const gymSign = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.15), new THREE.MeshBasicMaterial({map:gymSignTex}));
  gymSign.position.set(GYM_X, LF_Y + 2.8, -5.95);
  scene.add(gymSign);

  // Treadmill
  const treadMat = new THREE.MeshStandardMaterial({color:0x555555, roughness:0.4, metalness:0.5, emissive:0x111111, emissiveIntensity:0.3});
  const treadBase = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.08, 1.4), treadMat);
  treadBase.position.set(GYM_X - 1.5, LF_Y + 0.15, GYM_Z - 1.5);
  scene.add(treadBase);
  // Treadmill belt (dark)
  const beltMat = new THREE.MeshStandardMaterial({color:0x1a1a1a, roughness:0.3});
  const belt = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.02, 1.2), beltMat);
  belt.position.set(GYM_X - 1.5, LF_Y + 0.2, GYM_Z - 1.5);
  scene.add(belt);
  // Treadmill handlebars
  const handleMat = new THREE.MeshStandardMaterial({color:0xaaaaaa, roughness:0.2, metalness:0.8, emissive:0x222222, emissiveIntensity:0.2});
  const tHandle1 = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.8, 4), handleMat);
  tHandle1.position.set(GYM_X - 1.8, LF_Y + 0.6, GYM_Z - 0.8);
  scene.add(tHandle1);
  const tHandle2 = tHandle1.clone();
  tHandle2.position.x = GYM_X - 1.2;
  scene.add(tHandle2);
  // Treadmill display
  const treadDisplay = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.15, 0.03), new THREE.MeshBasicMaterial({color:0x2a5533}));
  treadDisplay.position.set(GYM_X - 1.5, LF_Y + 1.0, GYM_Z - 0.8);
  scene.add(treadDisplay);

  // Weight bench
  const benchMat = new THREE.MeshStandardMaterial({color:0x222222, roughness:0.5});
  const benchPad = new THREE.MeshStandardMaterial({color:0x2a2a2a, roughness:0.8});
  const benchFrame = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.4, 1.2), benchMat);
  benchFrame.position.set(GYM_X, LF_Y + 0.2, GYM_Z - 1.5);
  scene.add(benchFrame);
  const benchTop = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.06, 1.0), benchPad);
  benchTop.position.set(GYM_X, LF_Y + 0.43, GYM_Z - 1.5);
  scene.add(benchTop);
  // Barbell rack
  const rackPost1 = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 1.0, 6), handleMat);
  rackPost1.position.set(GYM_X - 0.2, LF_Y + 0.9, GYM_Z - 2.0);
  scene.add(rackPost1);
  const rackPost2 = rackPost1.clone();
  rackPost2.position.x = GYM_X + 0.2;
  scene.add(rackPost2);
  // Barbell
  const barbell = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.8, 6), handleMat);
  barbell.position.set(GYM_X, LF_Y + 1.3, GYM_Z - 2.0);
  barbell.rotation.z = Math.PI/2;
  scene.add(barbell);
  // Weight plates
  const plateMat = new THREE.MeshStandardMaterial({color:0x444444, roughness:0.4, metalness:0.6});
  for(let side = -1; side <= 1; side += 2) {
    const plate = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.04, 12), plateMat);
    plate.position.set(GYM_X + side*0.35, LF_Y + 1.3, GYM_Z - 2.0);
    plate.rotation.z = Math.PI/2;
    scene.add(plate);
  }

  // Dumbbells on a rack
  const dumbRack = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.6, 0.3), benchMat);
  dumbRack.position.set(GYM_X + 1.5, LF_Y + 0.3, GYM_Z - 2.5);
  scene.add(dumbRack);
  for(let i = 0; i < 4; i++) {
    const db = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.2, 6), handleMat);
    db.position.set(GYM_X + 1.1 + i*0.25, LF_Y + 0.65, GYM_Z - 2.5);
    db.rotation.z = Math.PI/2;
    scene.add(db);
  }

  // Yoga mat (rolled out)
  const yogaMat = new THREE.MeshStandardMaterial({color:0x4a4050, roughness:0.6, emissive:0x151015, emissiveIntensity:0.15});
  const yogaFlat = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.01, 1.5), yogaMat);
  yogaFlat.position.set(GYM_X + 1.5, LF_Y + 0.01, GYM_Z);
  scene.add(yogaFlat);

  // Rubber floor tiles for gym area
  const gymFloorMat = new THREE.MeshStandardMaterial({color:0x4a4a55, roughness:0.6, emissive:0x0a0a10, emissiveIntensity:0.2});
  const gymFloor = new THREE.Mesh(new THREE.PlaneGeometry(5, 5), gymFloorMat);
  gymFloor.rotation.x = -Math.PI/2;
  gymFloor.position.set(GYM_X, LF_Y + 0.005, GYM_Z - 1.5);
  scene.add(gymFloor);

  // ── CAFETERIA (center section: x:-1.5 to 2.5, z:-5 to 1) ──
  const CAF_X = 0.5, CAF_Z = -2;

  // "CAFETERIA" sign
  const cafSignCnv = document.createElement('canvas');
  cafSignCnv.width = 128; cafSignCnv.height = 32;
  const cafSignCtx = cafSignCnv.getContext('2d');
  cafSignCtx.fillStyle = '#1a2744';
  cafSignCtx.fillRect(0,0,128,32);
  cafSignCtx.fillStyle = '#aa8855';
  cafSignCtx.font = 'bold 14px sans-serif';
  cafSignCtx.textAlign = 'center';
  cafSignCtx.fillText('CAFETERIA', 64, 24);
  const cafSignTex = new THREE.CanvasTexture(cafSignCnv);
  const cafSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.15), new THREE.MeshBasicMaterial({map:cafSignTex}));
  cafSignMesh.position.set(CAF_X, LF_Y + 2.8, -5.95);
  scene.add(cafSignMesh);

  // Food counter/serving area
  const counterMatLF = new THREE.MeshStandardMaterial({color:0xaaaaaa, roughness:0.2, metalness:0.6, emissive:0x222222, emissiveIntensity:0.2});
  const foodCounter = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.9, 0.5), counterMatLF);
  foodCounter.position.set(CAF_X, LF_Y + 0.45, CAF_Z - 2.8);
  scene.add(foodCounter);
  // Counter top (stainless steel look)
  const ssTop = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.03, 0.55), new THREE.MeshStandardMaterial({color:0xaaaaaa, roughness:0.15, metalness:0.8}));
  ssTop.position.set(CAF_X, LF_Y + 0.91, CAF_Z - 2.8);
  scene.add(ssTop);
  // Food trays on counter
  for(let i = 0; i < 3; i++) {
    const tray = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.02, 0.2), new THREE.MeshStandardMaterial({color:0x996633, roughness:0.6}));
    tray.position.set(CAF_X - 0.8 + i*0.8, LF_Y + 0.93, CAF_Z - 2.8);
    scene.add(tray);
  }

  // Dining tables (3 round tables with chairs)
  for(let t = 0; t < 3; t++) {
    const tx = CAF_X - 1.0 + t * 1.2;
    const tz = CAF_Z - 0.5;
    // Table
    const tblLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.6, 6), legMat);
    tblLeg.position.set(tx, LF_Y + 0.3, tz);
    scene.add(tblLeg);
    const tblTop = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.03, 12), new THREE.MeshStandardMaterial({color:0xdddddd, roughness:0.3, metalness:0.3}));
    tblTop.position.set(tx, LF_Y + 0.61, tz);
    scene.add(tblTop);
    // 4 chairs around each table
    for(let c = 0; c < 4; c++) {
      const ca = c * Math.PI/2;
      const cx = tx + Math.cos(ca) * 0.5;
      const cz = tz + Math.sin(ca) * 0.5;
      const chSeat = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.03, 0.25), new THREE.MeshStandardMaterial({color:0x4a4a50, roughness:0.5, emissive:0x0a0a10, emissiveIntensity:0.1}));
      chSeat.position.set(cx, LF_Y + 0.35, cz);
      scene.add(chSeat);
    }
  }

  // Vending machines against wall
  const vendMat = new THREE.MeshStandardMaterial({color:0x3a3a42, roughness:0.3, metalness:0.5, emissive:0x111115, emissiveIntensity:0.15});
  const vend1 = new THREE.Mesh(new THREE.BoxGeometry(0.5, 1.4, 0.4), vendMat);
  vend1.position.set(CAF_X + 2.0, LF_Y + 0.7, CAF_Z - 2.8);
  scene.add(vend1);
  // Vending machine display
  const vendDisplay = new THREE.Mesh(new THREE.PlaneGeometry(0.35, 0.6), new THREE.MeshBasicMaterial({color:0x556677, transparent:true, opacity:0.35}));
  vendDisplay.position.set(CAF_X + 2.0, LF_Y + 0.9, CAF_Z - 2.59);
  scene.add(vendDisplay);
  // Second vending machine (snacks)
  const vend2 = new THREE.Mesh(new THREE.BoxGeometry(0.5, 1.4, 0.4), new THREE.MeshStandardMaterial({color:0x44383a, roughness:0.4, metalness:0.4}));
  vend2.position.set(CAF_X + 2.6, LF_Y + 0.7, CAF_Z - 2.8);
  scene.add(vend2);

  // ── RECREATION AREA (right section: x:3 to 6.5, z:-5 to 2) ──
  const REC_X = 4.5, REC_Z = -1.5;

  // "REC ROOM" sign
  const recSignCnv = document.createElement('canvas');
  recSignCnv.width = 128; recSignCnv.height = 32;
  const recSignCtx = recSignCnv.getContext('2d');
  recSignCtx.fillStyle = '#1a2744';
  recSignCtx.fillRect(0,0,128,32);
  recSignCtx.fillStyle = '#7a9988';
  recSignCtx.font = 'bold 14px sans-serif';
  recSignCtx.textAlign = 'center';
  recSignCtx.fillText('REC ROOM', 64, 24);
  const recSignTex = new THREE.CanvasTexture(recSignCnv);
  const recSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.15), new THREE.MeshBasicMaterial({map:recSignTex}));
  recSignMesh.position.set(REC_X, LF_Y + 2.8, -5.95);
  scene.add(recSignMesh);

  // Ping pong table
  const ppTableMat = new THREE.MeshStandardMaterial({color:0x2a4a3a, roughness:0.4, emissive:0x0a1510, emissiveIntensity:0.15});
  const ppTable = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.04, 0.8), ppTableMat);
  ppTable.position.set(REC_X, LF_Y + 0.7, REC_Z - 2);
  scene.add(ppTable);
  // Table legs
  for(let lx of [-0.6, 0.6]) {
    for(let lz of [-0.3, 0.3]) {
      const ppLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.68, 4), legMat);
      ppLeg.position.set(REC_X + lx, LF_Y + 0.35, REC_Z - 2 + lz);
      scene.add(ppLeg);
    }
  }
  // Net
  const netMat = new THREE.MeshStandardMaterial({color:0xffffff, transparent:true, opacity:0.5, side:THREE.DoubleSide});
  const ppNet = new THREE.Mesh(new THREE.PlaneGeometry(0.04, 0.12), netMat);
  ppNet.position.set(REC_X, LF_Y + 0.78, REC_Z - 2);
  ppNet.rotation.y = Math.PI/2;
  const netStrip = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.12, 0.005), netMat);
  netStrip.position.set(REC_X, LF_Y + 0.78, REC_Z - 2);
  scene.add(netStrip);

  // Bean bag chairs (2)
  const bbColors = [0x5a4a3a, 0x3a3a4a];
  bbColors.forEach((col, i) => {
    const bbMat2 = new THREE.MeshStandardMaterial({color:col, roughness:0.9});
    const bb = new THREE.Mesh(new THREE.SphereGeometry(0.25, 12, 8), bbMat2);
    bb.position.set(REC_X + 1.5, LF_Y + 0.15, REC_Z + i * 0.8);
    bb.scale.set(1.2, 0.6, 1.0);
    scene.add(bb);
  });

  // TV mounted on wall (for gaming/watching)
  const recTVBezel = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.6, 0.03), new THREE.MeshStandardMaterial({color:0x111111, roughness:0.3, metalness:0.6}));
  recTVBezel.position.set(REC_X + 1.5, LF_Y + 1.8, -5.95);
  scene.add(recTVBezel);
  const recTVScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.5), new THREE.MeshBasicMaterial({color:0x1a2a3a}));
  recTVScreen.position.set(REC_X + 1.5, LF_Y + 1.8, -5.93);
  scene.add(recTVScreen);

  // Foosball table
  const foosMat = new THREE.MeshStandardMaterial({color:0x5a3a1a, roughness:0.6});
  const foosTable = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.08, 0.5), foosMat);
  foosTable.position.set(REC_X - 1, LF_Y + 0.7, REC_Z);
  scene.add(foosTable);
  // Foosball sides
  const foosSide = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.15, 0.04), foosMat);
  foosSide.position.set(REC_X - 1, LF_Y + 0.78, REC_Z - 0.25);
  scene.add(foosSide);
  const foosSide2 = foosSide.clone();
  foosSide2.position.z = REC_Z + 0.25;
  scene.add(foosSide2);
  // Foosball rods
  for(let r = 0; r < 4; r++) {
    const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.6, 4), handleMat);
    rod.position.set(REC_X - 1.3 + r*0.25, LF_Y + 0.82, REC_Z);
    rod.rotation.x = Math.PI/2;
    scene.add(rod);
  }
  for(let lx of [-0.4, 0.4]) {
    for(let lz of [-0.2, 0.2]) {
      const fLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.68, 4), legMat);
      fLeg.position.set(REC_X - 1 + lx, LF_Y + 0.35, REC_Z + lz);
      scene.add(fLeg);
    }
  }

  // Cozy rug for rec area
  const recRug = new THREE.Mesh(new THREE.PlaneGeometry(3, 2.5), new THREE.MeshStandardMaterial({color:0x3a3540, roughness:0.95}));
  recRug.rotation.x = -Math.PI/2;
  recRug.position.set(REC_X + 1, LF_Y + 0.005, REC_Z);
  scene.add(recRug);

  // ══════════════════════════════════════════════════
  // ══ B2 FLOOR — BEDROOMS, BAR & JACUZZI ══
  // ══════════════════════════════════════════════════
  const B2_Y = LF_Y - 3.5; // below B1 (gym/cafeteria/rec)
  const B2_H = 3.2;

  // B2 Floor
  const b2FloorMat = new THREE.MeshStandardMaterial({color:0x3a3540, roughness:0.7, metalness:0.05, polygonOffset:true, polygonOffsetFactor:-1, polygonOffsetUnits:-1});
  const b2Floor = new THREE.Mesh(new THREE.CircleGeometry(ROOM_W * 0.70, 32), b2FloorMat);
  b2Floor.rotation.x = -Math.PI/2;
  b2Floor.position.set(0, B2_Y + 0.02, 0);
  b2Floor.receiveShadow = true;
  scene.add(b2Floor);

  // B2 Ceiling (underside of B1 floor) — with stairwell opening
  {
    const b2CeilShape = new THREE.Shape();
    const b2CeilR = ROOM_W * 0.70;
    for(let i = 0; i <= 32; i++) {
      const a = (i / 32) * Math.PI * 2;
      if(i === 0) b2CeilShape.moveTo(Math.cos(a) * b2CeilR, Math.sin(a) * b2CeilR);
      else b2CeilShape.lineTo(Math.cos(a) * b2CeilR, Math.sin(a) * b2CeilR);
    }
    const b2CeilHole = new THREE.Path();
    b2CeilHole.moveTo(-5.5, 2.5);
    b2CeilHole.lineTo(-3.5, 2.5);
    b2CeilHole.lineTo(-3.5, 4.5);
    b2CeilHole.lineTo(-5.5, 4.5);
    b2CeilHole.lineTo(-5.5, 2.5);
    b2CeilShape.holes.push(b2CeilHole);
    const b2Ceil = new THREE.Mesh(new THREE.ShapeGeometry(b2CeilShape), new THREE.MeshStandardMaterial({color:0x2a2a32, roughness:0.7, metalness:0.05, side:THREE.DoubleSide}));
    b2Ceil.rotation.x = Math.PI/2;
    b2Ceil.position.set(0, B2_Y + B2_H, 0);
    scene.add(b2Ceil);
  }

  // B2 glass walls removed — tower exterior glass bands provide the windows
  const b2FrameMat = new THREE.MeshStandardMaterial({color:0x334450, metalness:0.7, roughness:0.3});

  // B2 Lighting — 3 lights (reduced from 9 for performance)
  for(const lp of [[-3,2.8,0],[3,2.8,0],[0,2.8,-3]]) {
    const bl = new THREE.PointLight(0xfff5e0, 0.8, 12);
    bl.position.set(lp[0], B2_Y + lp[1], lp[2]);
    scene.add(bl);
  }
  // Glowing ceiling panels
  const b2PanelMat = new THREE.MeshBasicMaterial({color:0xeee8dd});
  for(let lx = -5; lx <= 5; lx += 3.3) {
    for(let lz = -3; lz <= 3; lz += 3) {
      const lP = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.03, 0.6), b2PanelMat);
      lP.position.set(lx, B2_Y + B2_H - 0.02, lz);
      scene.add(lP);
    }
  }

  // B2 Staircase from B1 to B2 (same position as B1→main stairs)
  const B2_STAIR_X = -5.5, B2_STAIR_Z = 4.5;
  const b2StairMat = new THREE.MeshStandardMaterial({color:0x556672, roughness:0.3, metalness:0.5, emissive:0x222233, emissiveIntensity:0.15});
  for(let s = 0; s < 12; s++) {
    const step = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.08, 0.35), b2StairMat);
    step.position.set(B2_STAIR_X, B2_Y + B2_H - s*(B2_H/12), B2_STAIR_Z - 0.15*s);
    scene.add(step);
  }
  // B2 stair railings
  for(const sx of [-0.9, 0.9]) {
    for(let p = 0; p < 5; p++) {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.6, 4), b2FrameMat);
      post.position.set(B2_STAIR_X + sx, B2_Y + B2_H - p*(B2_H/5) + 0.3, B2_STAIR_Z - p*0.6);
      scene.add(post);
    }
  }

  // Also cut stairwell hole in B1 floor
  // (B1 floor was PlaneGeometry — replace with ShapeGeometry + hole)

  // ── B2: BEDROOMS (left section: x:-5.5 to -1, z:-5 to 5) ──
  const BED_X = -4.0;
  const bedFrameMat = new THREE.MeshStandardMaterial({color:0x5a4a3a, roughness:0.6, emissive:0x1a1008, emissiveIntensity:0.15});
  const bedSheetMat = new THREE.MeshStandardMaterial({color:0xddd8cc, roughness:0.8, emissive:0x222218, emissiveIntensity:0.1});
  const pillowMat = new THREE.MeshStandardMaterial({color:0xeeeee8, roughness:0.9, emissive:0x222222, emissiveIntensity:0.1});

  // 4 beds in a row (like a modern pod hotel / bunkroom)
  for(let b = 0; b < 4; b++) {
    const bz = -4.0 + b * 2.2;
    // Bed frame
    const frame = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.3, 0.9), bedFrameMat);
    frame.position.set(BED_X, B2_Y + 0.15, bz);
    scene.add(frame);
    // Mattress
    const mattress = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.12, 0.85), bedSheetMat);
    mattress.position.set(BED_X, B2_Y + 0.36, bz);
    scene.add(mattress);
    // Pillow
    const pillow = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.08, 0.5), pillowMat);
    pillow.position.set(BED_X - 0.55, B2_Y + 0.46, bz);
    scene.add(pillow);
    // Blanket (folded at foot)
    const blanketColors = [0x3a3a4a, 0x3a4a3e, 0x4a3a32, 0x3e3a4a];
    const blanket = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.06, 0.8), new THREE.MeshStandardMaterial({color:blanketColors[b], roughness:0.85, emissive:blanketColors[b], emissiveIntensity:0.05}));
    blanket.position.set(BED_X + 0.5, B2_Y + 0.42, bz);
    scene.add(blanket);
    // Bedside lamp (small warm glow)
    const lampBase = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.08, 8), new THREE.MeshStandardMaterial({color:0x888888, metalness:0.6}));
    lampBase.position.set(BED_X + 0.9, B2_Y + 0.34, bz - 0.3);
    scene.add(lampBase);
    const lampShade = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 0.1, 8), new THREE.MeshBasicMaterial({color:0xffeecc}));
    lampShade.position.set(BED_X + 0.9, B2_Y + 0.44, bz - 0.3);
    scene.add(lampShade);
    // Bedside lamp glow (mesh only, no PointLight for performance)
  }

  // "BEDROOMS" sign
  const bedSignCnv = document.createElement('canvas');
  bedSignCnv.width = 128; bedSignCnv.height = 32;
  const bedSignCtx = bedSignCnv.getContext('2d');
  bedSignCtx.fillStyle = '#1a1a2a';
  bedSignCtx.fillRect(0,0,128,32);
  bedSignCtx.fillStyle = '#ccaa77';
  bedSignCtx.font = 'bold 14px sans-serif';
  bedSignCtx.textAlign = 'center';
  bedSignCtx.fillText('BEDROOMS', 64, 24);
  const bedSignTex = new THREE.CanvasTexture(bedSignCnv);
  const bedSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.15), new THREE.MeshBasicMaterial({map:bedSignTex}));
  bedSignMesh.position.set(BED_X, B2_Y + 2.8, -5.95);
  scene.add(bedSignMesh);

  // Divider curtains between beds (for privacy)
  const curtainMat = new THREE.MeshStandardMaterial({color:0x44444e, transparent:true, opacity:0.35, side:THREE.DoubleSide, roughness:0.9});
  for(let c = 0; c < 3; c++) {
    const curtain = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 2.2), curtainMat);
    curtain.position.set(BED_X, B2_Y + 1.1, -2.9 + c * 2.2);
    curtain.rotation.y = Math.PI/2;
    scene.add(curtain);
  }

  // ── B2: BAR & LOUNGE (center: x:-1 to 3, z:-5 to 5) ──
  const BAR_X = 1.0, BAR_Z = -3.0;

  // Bar counter (L-shaped)
  const barCounterMat = new THREE.MeshStandardMaterial({color:0x3a2a1a, roughness:0.4, metalness:0.1, emissive:0x1a0a00, emissiveIntensity:0.15});
  const barTopMat = new THREE.MeshStandardMaterial({color:0x2a2025, roughness:0.45, metalness:0.1, emissive:0x110808, emissiveIntensity:0.15}); // dark granite
  // Main bar section
  const barMain = new THREE.Mesh(new THREE.BoxGeometry(2.5, 1.0, 0.4), barCounterMat);
  barMain.position.set(BAR_X, B2_Y + 0.5, BAR_Z);
  scene.add(barMain);
  const barTop1 = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.04, 0.5), barTopMat);
  barTop1.position.set(BAR_X, B2_Y + 1.02, BAR_Z);
  scene.add(barTop1);
  // Bar side section (L-shape)
  const barSide = new THREE.Mesh(new THREE.BoxGeometry(0.4, 1.0, 1.5), barCounterMat);
  barSide.position.set(BAR_X + 1.25, B2_Y + 0.5, BAR_Z + 0.95);
  scene.add(barSide);
  const barTop2 = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.04, 1.6), barTopMat);
  barTop2.position.set(BAR_X + 1.25, B2_Y + 1.02, BAR_Z + 0.95);
  scene.add(barTop2);

  // Bar stools (4)
  const stoolMat = new THREE.MeshStandardMaterial({color:0x555555, metalness:0.6, roughness:0.3});
  for(let s = 0; s < 4; s++) {
    const stoolBase = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 0.04, 8), stoolMat);
    stoolBase.position.set(BAR_X - 0.8 + s * 0.55, B2_Y + 0.02, BAR_Z + 0.4);
    scene.add(stoolBase);
    const stoolPole = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.55, 6), stoolMat);
    stoolPole.position.set(BAR_X - 0.8 + s * 0.55, B2_Y + 0.3, BAR_Z + 0.4);
    scene.add(stoolPole);
    const stoolSeat = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.1, 0.05, 8), new THREE.MeshStandardMaterial({color:0x884422, roughness:0.7}));
    stoolSeat.position.set(BAR_X - 0.8 + s * 0.55, B2_Y + 0.58, BAR_Z + 0.4);
    scene.add(stoolSeat);
  }

  // Bottle shelf behind bar (against wall / back)
  const shelfMat = new THREE.MeshStandardMaterial({color:0x3a2a1a, roughness:0.5});
  for(let sh = 0; sh < 3; sh++) {
    const shelf = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.04, 0.2), shelfMat);
    shelf.position.set(BAR_X, B2_Y + 0.6 + sh * 0.5, BAR_Z - 0.35);
    scene.add(shelf);
  }
  // Bottles on shelves (colorful)
  const bottleColors = [0x1a3322, 0x4a2a22, 0x1a2a3a, 0x4a3a1a, 0x3a2a3a, 0x3a2a1a, 0x1a2a33, 0x3a3025];
  for(let sh = 0; sh < 3; sh++) {
    for(let b = 0; b < 5; b++) {
      const bottle = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.025, 0.18, 6), new THREE.MeshStandardMaterial({color:bottleColors[(sh*5+b)%bottleColors.length], roughness:0.2, metalness:0.1, emissive:bottleColors[(sh*5+b)%bottleColors.length], emissiveIntensity:0.1}));
      bottle.position.set(BAR_X - 0.6 + b * 0.3, B2_Y + 0.72 + sh * 0.5, BAR_Z - 0.35);
      scene.add(bottle);
    }
  }

  // Bar ambient light (warm, moody)
  const barLight = new THREE.PointLight(0xffaa55, 1.0, 8);
  barLight.position.set(BAR_X, B2_Y + 2.5, BAR_Z);
  scene.add(barLight);
  // LED strip under bar top (accent)
  const barLED = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.02, 0.02), new THREE.MeshBasicMaterial({color:0x3a2a55}));
  barLED.position.set(BAR_X, B2_Y + 0.96, BAR_Z + 0.2);
  scene.add(barLED);

  // "BAR" neon sign
  const barSignCnv = document.createElement('canvas');
  barSignCnv.width = 128; barSignCnv.height = 32;
  const barSignCtx = barSignCnv.getContext('2d');
  barSignCtx.fillStyle = '#0a0a15';
  barSignCtx.fillRect(0,0,128,32);
  barSignCtx.fillStyle = '#cc8866';
  barSignCtx.font = 'bold 18px sans-serif';
  barSignCtx.textAlign = 'center';
  barSignCtx.fillText('BAR', 64, 24);
  const barSignTex = new THREE.CanvasTexture(barSignCnv);
  const barSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.12), new THREE.MeshBasicMaterial({map:barSignTex}));
  barSignMesh.position.set(BAR_X, B2_Y + 2.8, -5.95);
  scene.add(barSignMesh);

  // Lounge seating near bar
  const loungeMat = new THREE.MeshStandardMaterial({color:0x553322, roughness:0.7, emissive:0x1a0a00, emissiveIntensity:0.1});
  // Leather sofa
  const sofa = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.35, 0.6), loungeMat);
  sofa.position.set(BAR_X - 0.5, B2_Y + 0.18, BAR_Z + 1.8);
  scene.add(sofa);
  // Sofa back
  const sofaBack = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.4, 0.12), loungeMat);
  sofaBack.position.set(BAR_X - 0.5, B2_Y + 0.55, BAR_Z + 1.5);
  scene.add(sofaBack);
  // Coffee table
  const coffeeTable = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.04, 0.5), new THREE.MeshStandardMaterial({color:0x444444, roughness:0.2, metalness:0.5}));
  coffeeTable.position.set(BAR_X - 0.5, B2_Y + 0.35, BAR_Z + 2.4);
  scene.add(coffeeTable);
  const ctLeg1 = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.33, 4), stoolMat);
  ctLeg1.position.set(BAR_X - 0.8, B2_Y + 0.17, BAR_Z + 2.2);
  scene.add(ctLeg1);
  const ctLeg2 = ctLeg1.clone();
  ctLeg2.position.x = BAR_X - 0.2;
  scene.add(ctLeg2);

  // ── B2: JACUZZI / SPA (right section: x:3 to 6.5, z:-5 to 5) ──
  const SPA_X = 4.5, SPA_Z = 0;

  // Jacuzzi tub (sunken circle)
  const jacuzziMat = new THREE.MeshStandardMaterial({color:0x334455, roughness:0.5, metalness:0.1, emissive:0x112233, emissiveIntensity:0.15});
  // Outer rim
  const jacuzziRim = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.12, 8, 24), jacuzziMat);
  jacuzziRim.rotation.x = Math.PI/2;
  jacuzziRim.position.set(SPA_X, B2_Y + 0.3, SPA_Z);
  scene.add(jacuzziRim);
  // Water surface (glowing blue)
  const jacuzziWater = new THREE.Mesh(new THREE.CircleGeometry(0.95, 24), new THREE.MeshBasicMaterial({color:0x1a4466, transparent:true, opacity:0.6}));
  jacuzziWater.rotation.x = -Math.PI/2;
  jacuzziWater.position.set(SPA_X, B2_Y + 0.25, SPA_Z);
  scene.add(jacuzziWater);
  // Underwater glow
  const jacuzziLight = new THREE.PointLight(0x1a4466, 0.8, 4);
  jacuzziLight.position.set(SPA_X, B2_Y + 0.1, SPA_Z);
  scene.add(jacuzziLight);
  // Tub basin (dark cylinder going down)
  const jacuzziBasin = new THREE.Mesh(new THREE.CylinderGeometry(0.95, 0.9, 0.3, 24, 1, true), new THREE.MeshStandardMaterial({color:0x223344, roughness:0.2, metalness:0.3, side:THREE.DoubleSide}));
  jacuzziBasin.position.set(SPA_X, B2_Y + 0.15, SPA_Z);
  scene.add(jacuzziBasin);
  // Jets (small cylinders around rim)
  for(let j = 0; j < 6; j++) {
    const angle = j * Math.PI / 3;
    const jet = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.06, 6), new THREE.MeshBasicMaterial({color:0x556677}));
    jet.position.set(SPA_X + Math.cos(angle)*0.8, B2_Y + 0.28, SPA_Z + Math.sin(angle)*0.8);
    scene.add(jet);
  }

  // Tile floor around jacuzzi
  const tileMat = new THREE.MeshStandardMaterial({color:0x556666, roughness:0.65, metalness:0.05, emissive:0x111515, emissiveIntensity:0.08});
  const tileFloor = new THREE.Mesh(new THREE.PlaneGeometry(3.5, 4), tileMat);
  tileFloor.rotation.x = -Math.PI/2;
  tileFloor.position.set(SPA_X, B2_Y + 0.005, SPA_Z);
  scene.add(tileFloor);

  // Towel rack
  const rackMat = new THREE.MeshStandardMaterial({color:0x888888, metalness:0.7, roughness:0.2});
  const towelRack = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.8, 0.04), rackMat);
  towelRack.position.set(SPA_X + 1.5, B2_Y + 0.4, SPA_Z - 1.5);
  scene.add(towelRack);
  const towelBar = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.02, 0.02), rackMat);
  towelBar.position.set(SPA_X + 1.5, B2_Y + 0.7, SPA_Z - 1.5);
  scene.add(towelBar);
  // Towels hanging
  const towel1 = new THREE.Mesh(new THREE.PlaneGeometry(0.25, 0.4), new THREE.MeshStandardMaterial({color:0xeeeeee, roughness:0.9, side:THREE.DoubleSide}));
  towel1.position.set(SPA_X + 1.4, B2_Y + 0.5, SPA_Z - 1.5);
  scene.add(towel1);
  const towel2 = new THREE.Mesh(new THREE.PlaneGeometry(0.25, 0.4), new THREE.MeshStandardMaterial({color:0x667788, roughness:0.9, side:THREE.DoubleSide}));
  towel2.position.set(SPA_X + 1.6, B2_Y + 0.5, SPA_Z - 1.5);
  scene.add(towel2);

  // Potted plant near spa
  const spaPot = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.1, 0.2, 8), new THREE.MeshStandardMaterial({color:0x8a6a4a, roughness:0.7}));
  spaPot.position.set(SPA_X - 1.3, B2_Y + 0.1, SPA_Z + 1.8);
  scene.add(spaPot);
  const spaPlant = new THREE.Mesh(new THREE.SphereGeometry(0.2, 8, 6), new THREE.MeshStandardMaterial({color:0x2a4a32, roughness:0.8, emissive:0x0a150a, emissiveIntensity:0.08}));
  spaPlant.position.set(SPA_X - 1.3, B2_Y + 0.35, SPA_Z + 1.8);
  scene.add(spaPlant);

  // "SPA & JACUZZI" sign
  const spaSignCnv = document.createElement('canvas');
  spaSignCnv.width = 160; spaSignCnv.height = 32;
  const spaSignCtx = spaSignCnv.getContext('2d');
  spaSignCtx.fillStyle = '#0a1520';
  spaSignCtx.fillRect(0,0,160,32);
  spaSignCtx.fillStyle = '#6a99a0';
  spaSignCtx.font = 'bold 13px sans-serif';
  spaSignCtx.textAlign = 'center';
  spaSignCtx.fillText('SPA & JACUZZI', 80, 24);
  const spaSignTex = new THREE.CanvasTexture(spaSignCnv);
  const spaSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.14), new THREE.MeshBasicMaterial({map:spaSignTex}));
  spaSignMesh.position.set(SPA_X, B2_Y + 2.8, -5.95);
  scene.add(spaSignMesh);
}

// ── 3D CITY BUILDINGS AROUND SALESFORCE TOWER ──
{
  const GROUND_Y = -50;

  // The whole exterior city lives in one group. The vertical scale compresses
  // the stylized building heights (~5x exaggerated vs the 1:40m horizontal
  // scale) to believable ratios, and the lift puts the city ground ~18 units
  // below the penthouse floor - so downtown tops sit just below eye level:
  // the "top of Salesforce Tower" vantage. Horizontal layout is untouched.
  const cityGroup = new THREE.Group();
  cityGroup.scale.set(1, 0.35, 1);
  cityGroup.position.y = -18 - GROUND_Y * 0.35;

  // Ground plane (city floor / streets) — vertex-colored: darker near water, lighter inland
  const groundGeo = new THREE.PlaneGeometry(1200, 1200, 40, 40);
  const groundColors = new Float32Array(groundGeo.attributes.position.count * 3);
  for (let gi = 0; gi < groundGeo.attributes.position.count; gi++) {
    const gy = groundGeo.attributes.position.getY(gi);
    const waterProx = Math.max(0, Math.min(1, (-gy - 50) / 300));
    groundColors[gi * 3]     = 0.18 + (0.12 - 0.18) * waterProx;
    groundColors[gi * 3 + 1] = 0.18 + (0.14 - 0.18) * waterProx;
    groundColors[gi * 3 + 2] = 0.20 + (0.18 - 0.20) * waterProx;
  }
  groundGeo.setAttribute('color', new THREE.BufferAttribute(groundColors, 3));
  const groundMat = new THREE.MeshStandardMaterial({roughness:0.85, metalness:0.15, vertexColors: true});
  cityGroundMat = groundMat;
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.rotation.x = -Math.PI/2;
  ground.position.set(0, GROUND_Y, 0);
  ground.receiveShadow = true;
  cityGroup.add(ground);

  // Downtown street grid overlay (subtle lines)
  const gridCanvas = document.createElement('canvas');
  gridCanvas.width = 512; gridCanvas.height = 512;
  const gctx = gridCanvas.getContext('2d');
  gctx.fillStyle = 'rgba(0,0,0,0)';
  gctx.fillRect(0, 0, 512, 512);
  gctx.strokeStyle = 'rgba(40,45,55,0.15)';
  gctx.lineWidth = 1;
  for (let sx = 0; sx < 512; sx += 32) { gctx.beginPath(); gctx.moveTo(sx, 0); gctx.lineTo(sx, 512); gctx.stroke(); }
  for (let sy = 0; sy < 512; sy += 32) { gctx.beginPath(); gctx.moveTo(0, sy); gctx.lineTo(512, sy); gctx.stroke(); }
  const gridTex = new THREE.CanvasTexture(gridCanvas);
  gridTex.wrapS = gridTex.wrapT = THREE.RepeatWrapping;
  gridTex.repeat.set(8, 8);
  const gridMat = new THREE.MeshBasicMaterial({map: gridTex, transparent: true, depthWrite: false});
  const gridPlane = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), gridMat);
  gridPlane.rotation.x = -Math.PI/2;
  gridPlane.position.set(0, GROUND_Y + 0.05, 10);
  gridPlane.renderOrder = 0.5;
  cityGroup.add(gridPlane);

  // SF Bay water plane — extends far to cover all visible bay area
  // Uses 'var' so waterPlane is accessible from animate() outside this block
  var waterMat = new THREE.MeshPhysicalMaterial({
    color: 0x0a3868, roughness: 0.05, metalness: 0.55,
    transparent: true, opacity: 0.88,
    clearcoat: 1.0, clearcoatRoughness: 0.02,
    envMapIntensity: 2.2,
  });
  var waterPlane = new THREE.Mesh(new THREE.PlaneGeometry(1000, 800, 64, 48), waterMat);
  waterPlane.rotation.x = -Math.PI/2;
  waterPlane.position.set(20, GROUND_Y + 0.1, -180);
  waterPlane.receiveShadow = true;
  cityGroup.add(waterPlane);

  // Store original Y positions for wave animation baseline
  var waterOrigY = new Float32Array(waterPlane.geometry.attributes.position.count);
  for (var _wi = 0; _wi < waterOrigY.length; _wi++) {
    waterOrigY[_wi] = waterPlane.geometry.attributes.position.getY(_wi);
  }

  // Water rendering fix: offset to prevent z-fighting with ground
  waterPlane.renderOrder = 1;

  // SF Hills — Twin Peaks (south, directly behind SoMa) — smooth half-sphere hills
  const twinPeaks = new THREE.Mesh(
    new THREE.SphereGeometry(30, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x4a7a3a, roughness: 0.82})
  );
  twinPeaks.position.set(0, GROUND_Y, 80);
  twinPeaks.scale.y = 0.5;
  cityGroup.add(twinPeaks);

  const twinPeaks2 = new THREE.Mesh(
    new THREE.SphereGeometry(27, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x4d7d3d, roughness: 0.82})
  );
  twinPeaks2.position.set(10, GROUND_Y, 75);
  twinPeaks2.scale.y = 0.45;
  cityGroup.add(twinPeaks2);

  // Marin Headlands (northwest, across the bay and Golden Gate) — distant blue-gray haze
  const marinHill = new THREE.Mesh(
    new THREE.SphereGeometry(45, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x6a8899, roughness: 0.85})
  );
  marinHill.position.set(-100, GROUND_Y, -160);
  marinHill.scale.y = 0.45;
  cityGroup.add(marinHill);

  const marinHill2 = new THREE.Mesh(
    new THREE.SphereGeometry(40, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x6d8b9c, roughness: 0.85})
  );
  marinHill2.position.set(-70, GROUND_Y, -180);
  marinHill2.scale.y = 0.4;
  cityGroup.add(marinHill2);

  // Mt Tamalpais (far north-northwest) — farthest, most blue-gray haze
  const tamalpais = new THREE.Mesh(
    new THREE.SphereGeometry(55, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x7788aa, roughness: 0.85})
  );
  tamalpais.position.set(-120, GROUND_Y, -230);
  tamalpais.scale.y = 0.45;
  cityGroup.add(tamalpais);

  // Oakland Hills (east/northeast, across the bay) — long ridgeline, gradient from green to blue-gray
  for(let i = 0; i < 10; i++) {
    const ohRadius = 20 + Math.random()*18;
    const distFactor = i / 9; // 0 = closest, 1 = farthest
    // Lerp color from green (close) to blue-gray (far)
    const ohR = Math.round(0x4a + (0x70 - 0x4a) * distFactor);
    const ohG = Math.round(0x7a + (0x82 - 0x7a) * distFactor);
    const ohB = Math.round(0x3a + (0x99 - 0x3a) * distFactor);
    const oh = new THREE.Mesh(
      new THREE.SphereGeometry(ohRadius, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
      new THREE.MeshStandardMaterial({color: (ohR << 16) | (ohG << 8) | ohB, roughness: 0.85})
    );
    oh.position.set(100 + i*18 + Math.random()*8, GROUND_Y, -70 - Math.random()*40);
    oh.scale.y = 0.4 + Math.random() * 0.2;
    cityGroup.add(oh);
  }

  // ── EARLY MATERIAL DECLARATIONS (needed by landmarks below) ──
  const winMat = new THREE.MeshBasicMaterial({color:0xffd88a, transparent:true, opacity:0.98, side:THREE.DoubleSide});
  cityNightMats.push({m:winMat, base:0.98});
  const avLightMat = new THREE.MeshBasicMaterial({color:0xff2200, emissive:0xff2200});

  // ── SF HILLS (the city's famous 7 hills + more) ──
  const hillMat = new THREE.MeshStandardMaterial({color: 0x4a8a42, roughness: 0.8});
  const hillMatDry = new THREE.MeshStandardMaterial({color: 0x6a8a48, roughness: 0.82});

  // Nob Hill (west-northwest, behind FiDi) — gentle rise under buildings
  const nobHill = new THREE.Mesh(new THREE.SphereGeometry(12, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  nobHill.position.set(-35, GROUND_Y, -10);
  nobHill.scale.set(1, 0.35, 1);
  cityGroup.add(nobHill);

  // Russian Hill (northwest) — gentle rise
  const russianHill = new THREE.Mesh(new THREE.SphereGeometry(14, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  russianHill.position.set(-30, GROUND_Y, -25);
  russianHill.scale.set(1, 0.4, 1);
  cityGroup.add(russianHill);

  // Telegraph Hill + Coit Tower (north-northwest) — moderate rise
  const telegraphHill = new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  telegraphHill.position.set(-12, GROUND_Y, -22);
  telegraphHill.scale.set(1, 0.5, 1);
  cityGroup.add(telegraphHill);
  // Coit Tower on top
  const coitTower = new THREE.Mesh(
    new THREE.CylinderGeometry(0.4, 0.5, 4, 8),
    new THREE.MeshStandardMaterial({color: 0xe0ddd5, roughness: 0.5})
  );
  coitTower.position.set(-12, GROUND_Y + 5, -22);
  cityGroup.add(coitTower);

  // Potrero Hill (south-southeast) — subtle
  const potreroHill = new THREE.Mesh(new THREE.SphereGeometry(12, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMatDry);
  potreroHill.position.set(20, GROUND_Y, 55);
  potreroHill.scale.set(1, 0.25, 1);
  cityGroup.add(potreroHill);

  // Bernal Heights (south) — subtle
  const bernalHill = new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMatDry);
  bernalHill.position.set(5, GROUND_Y, 90);
  bernalHill.scale.set(1, 0.3, 1);
  cityGroup.add(bernalHill);

  // Mount Davidson (far southwest) — tallest in-city hill
  const mtDavidson = new THREE.Mesh(new THREE.SphereGeometry(14, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  mtDavidson.position.set(-50, GROUND_Y, 100);
  mtDavidson.scale.set(1, 0.4, 1);
  cityGroup.add(mtDavidson);

  // ── LANDMARKS ──

  // Ferry Building (east waterfront, clock tower)
  {
    const fbGroup = new THREE.Group();
    const fbBody = new THREE.Mesh(
      new THREE.BoxGeometry(12, 4, 2),
      new THREE.MeshStandardMaterial({color: 0x8098b0, roughness: 0.4, metalness: 0.3})
    );
    fbBody.position.set(0, 2, 0);
    fbGroup.add(fbBody);
    // Clock tower
    const fbTower = new THREE.Mesh(
      new THREE.BoxGeometry(1.5, 10, 1.5),
      new THREE.MeshStandardMaterial({color: 0x90a8c0, roughness: 0.35, metalness: 0.35})
    );
    fbTower.position.set(0, 7, 0);
    fbGroup.add(fbTower);
    // Tower top
    const fbTop = new THREE.Mesh(
      new THREE.ConeGeometry(1.2, 3, 4),
      new THREE.MeshStandardMaterial({color: 0x6a7a8a, roughness: 0.4, metalness: 0.5})
    );
    fbTop.position.set(0, 13.5, 0);
    fbGroup.add(fbTop);
    fbGroup.position.set(18, GROUND_Y, -18);
    cityGroup.add(fbGroup);
  }

  // Oracle Park / AT&T Park (south of Embarcadero)
  {
    const parkMat = new THREE.MeshStandardMaterial({color: 0x4a5a6a, roughness: 0.5, metalness: 0.3});
    const park = new THREE.Mesh(new THREE.BoxGeometry(8, 5, 10), parkMat);
    park.position.set(28, GROUND_Y + 2.5, 20);
    cityGroup.add(park);
    // Green field
    const field = new THREE.Mesh(
      new THREE.PlaneGeometry(5, 7),
      new THREE.MeshStandardMaterial({color: 0x3a8a3a, roughness: 0.9})
    );
    field.rotation.x = -Math.PI/2;
    field.position.set(28, GROUND_Y + 5.1, 20);
    cityGroup.add(field);
  }

  // Sutro Tower (on Twin Peaks — red/white radio tower)
  {
    const sutroMat = new THREE.MeshStandardMaterial({color: 0xcc4422, roughness: 0.4});
    // Main mast
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.2, 15, 6), sutroMat);
    mast.position.set(2, GROUND_Y + 18 + 7.5, 78);
    cityGroup.add(mast);
    // Cross arms (3 levels)
    for(let ay = 0; ay < 3; ay++) {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(4-ay, 0.15, 0.15), sutroMat);
      arm.position.set(2, GROUND_Y + 20 + ay*4, 78);
      cityGroup.add(arm);
    }
    // Aviation light
    const sutroLight = new THREE.Mesh(new THREE.SphereGeometry(0.2, 4, 4), avLightMat);
    sutroLight.position.set(2, GROUND_Y + 33.5, 78);
    cityGroup.add(sutroLight);
  }

  // ── EMBARCADERO CURVE (waterfront promenade) ──
  const embarcMat = new THREE.MeshStandardMaterial({color: 0x9a9a90, roughness: 0.8});
  for(let a = -0.3; a <= 1.2; a += 0.08) {
    const ex = 20 + Math.cos(a) * 22;
    const ez = -18 + Math.sin(a) * 30;
    if(isWater(ex, ez)) continue;
    const seg = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.15, 2.5), embarcMat);
    seg.position.set(ex, GROUND_Y + 0.15, ez);
    cityGroup.add(seg);
  }

  // ── ALCATRAZ ISLAND (in the bay, north) ──
  {
    const alcMat = new THREE.MeshStandardMaterial({color: 0x6a7a60, roughness: 0.85});
    const alcIsland = new THREE.Mesh(new THREE.ConeGeometry(5, 3, 32, 4), alcMat);
    alcIsland.position.set(-15, GROUND_Y + 1.5, -80);
    cityGroup.add(alcIsland);
    // Main building
    const alcBld = new THREE.Mesh(
      new THREE.BoxGeometry(4, 2, 2),
      new THREE.MeshStandardMaterial({color: 0x8a8580, roughness: 0.7})
    );
    alcBld.position.set(-15, GROUND_Y + 4, -80);
    cityGroup.add(alcBld);
    // Lighthouse
    const alcLight = new THREE.Mesh(
      new THREE.CylinderGeometry(0.2, 0.2, 3, 6),
      new THREE.MeshStandardMaterial({color: 0xeeeeee, roughness: 0.5})
    );
    alcLight.position.set(-14, GROUND_Y + 5.5, -80);
    cityGroup.add(alcLight);
  }

  // ── ANGEL ISLAND (larger, behind Alcatraz) ──
  {
    const aiMat = new THREE.MeshStandardMaterial({color: 0x4a6a48, roughness: 0.85});
    const aiHill = new THREE.Mesh(new THREE.ConeGeometry(12, 8, 32, 4), aiMat);
    aiHill.position.set(10, GROUND_Y + 4, -120);
    cityGroup.add(aiHill);
    const aiHill2 = new THREE.Mesh(new THREE.ConeGeometry(8, 5, 32, 4), aiMat);
    aiHill2.position.set(18, GROUND_Y + 2.5, -115);
    cityGroup.add(aiHill2);
  }

  // Street grid — dark asphalt strips covering the whole city
  const streetPaveMat = new THREE.MeshStandardMaterial({color:0x4a4a50, roughness:0.88, metalness:0.02});
  const streetW = 1.5; // street width
  for(let i = -80; i <= 80; i += 6) {
    // N-S streets
    const ns = new THREE.Mesh(new THREE.PlaneGeometry(streetW, 250), streetPaveMat);
    ns.rotation.x = -Math.PI/2;
    ns.position.set(i, GROUND_Y + 0.05, 20);
    cityGroup.add(ns);
    // E-W streets
    if(i >= -40) {
      const ew = new THREE.Mesh(new THREE.PlaneGeometry(200, streetW), streetPaveMat);
      ew.rotation.x = -Math.PI/2;
      ew.position.set(0, GROUND_Y + 0.05, i);
      cityGroup.add(ew);
    }
  }
  // Yellow center lines on major streets (every 18 units)
  const lineMat = new THREE.MeshBasicMaterial({color:0xcccc44});
  for(let i = -78; i <= 78; i += 18) {
    const ln = new THREE.Mesh(new THREE.PlaneGeometry(0.1, 250), lineMat);
    ln.rotation.x = -Math.PI/2;
    ln.position.set(i, GROUND_Y + 0.06, 20);
    cityGroup.add(ln);
    if(i >= -40) {
      const ln2 = new THREE.Mesh(new THREE.PlaneGeometry(200, 0.1), lineMat);
      ln2.rotation.x = -Math.PI/2;
      ln2.position.set(0, GROUND_Y + 0.06, i);
      cityGroup.add(ln2);
    }
  }

  // Market Street — diagonal cut through the grid
  const marketMat = new THREE.MeshStandardMaterial({color:0x333338, roughness:0.9});
  const marketSt = new THREE.Mesh(new THREE.PlaneGeometry(2.5, 90), marketMat);
  marketSt.rotation.x = -Math.PI/2;
  marketSt.rotation.z = Math.PI * 0.22; // ~40 degree diagonal
  marketSt.position.set(-15, GROUND_Y + 0.07, 15);
  cityGroup.add(marketSt);

  // Building materials palette (glass/steel tones — brighter, more reflective)
  const bldgColors = [0x8899bb, 0x7a8eaa, 0x9aaac5, 0x6e88a8, 0x8a9cb8, 0x7090b0, 0xa0b0cc, 0x6888a8, 0x8098bb];
  // Shared materials pool — blue-gray glass tint, moderate metalness
  const bldgMats = bldgColors.map(c => new THREE.MeshPhysicalMaterial({
    color: c, roughness: 0.4, metalness: 0.3, emissive: c, emissiveIntensity: 0.06,
    clearcoat: 0.2, clearcoatRoughness: 0.3,
  }));
  // Residential/older buildings — muted blue-gray glass to match modern skyline
  const resBldgColors = [0x5a7088, 0x4a6878, 0x6a8098, 0x5a6a80, 0x4a7090, 0x607888, 0x5a7898, 0x506878, 0x607090];
  const resMats = resBldgColors.map(c => new THREE.MeshStandardMaterial({
    color: c, roughness: 0.38, metalness: 0.32, emissive: c, emissiveIntensity: 0.04,
  }));

  // winMat and avLightMat declared earlier (before landmarks)

  // ── INSTANCED MESH SYSTEM for dense city fill (1 draw call per material) ──
  // Collect all fill building transforms, then batch into InstancedMesh
  const fillQueue = {modern:[], residential:[], cylinder:[]};
  function fillBuilding(x, z, w, d, h, isResidential) {
    // ~12% of tall modern buildings become cylindrical for skyline variety
    if(!isResidential && h > 12 && Math.random() < 0.12) {
      fillQueue.cylinder.push({x, z, w, d, h});
      return;
    }
    const queue = isResidential ? fillQueue.residential : fillQueue.modern;
    queue.push({x, z, w, d, h});
  }
  // Called after all fillBuilding() calls to create the InstancedMesh batches
  function flushFillBuildings() {
    const unitGeo = new THREE.BoxGeometry(1, 1, 1);
    // Modern glass buildings — 5 material groups for premium blue-gray glass variety
    const modernGroups = [
      {mat: new THREE.MeshStandardMaterial({color:0x8899bb, roughness:0.4, metalness:0.3, emissive:0x8899bb, emissiveIntensity:0.05}), items:[]},
      {mat: new THREE.MeshStandardMaterial({color:0x7a8eaa, roughness:0.35, metalness:0.35, emissive:0x7a8eaa, emissiveIntensity:0.05}), items:[]},
      {mat: new THREE.MeshStandardMaterial({color:0x9aaac5, roughness:0.38, metalness:0.28, emissive:0x9aaac5, emissiveIntensity:0.04}), items:[]},
      {mat: new THREE.MeshStandardMaterial({color:0x6e88a8, roughness:0.42, metalness:0.32, emissive:0x6e88a8, emissiveIntensity:0.05}), items:[]},
      {mat: new THREE.MeshStandardMaterial({color:0x8a9cb8, roughness:0.36, metalness:0.34, emissive:0x8a9cb8, emissiveIntensity:0.04}), items:[]},
    ];
    fillQueue.modern.forEach((b,i) => modernGroups[i%5].items.push(b));
    modernGroups.forEach(grp => {
      if(grp.items.length === 0) return;
      const im = new THREE.InstancedMesh(unitGeo, grp.mat, grp.items.length);
      const m = new THREE.Matrix4();
      const c = new THREE.Color();
      grp.items.forEach((b, idx) => {
        m.compose(
          new THREE.Vector3(b.x, GROUND_Y + b.h/2, b.z),
          new THREE.Quaternion(),
          new THREE.Vector3(b.w, b.h, b.d)
        );
        im.setMatrixAt(idx, m);
        // Per-instance color variation for realism
        const shift = (Math.random()-0.5)*0.08;
        c.copy(grp.mat.color).offsetHSL(shift*0.3, shift, shift*0.5);
        im.setColorAt(idx, c);
      });
      im.instanceMatrix.needsUpdate = true;
      if(im.instanceColor) im.instanceColor.needsUpdate = true;
      cityGroup.add(im);
    });

    // Setback upper sections for tall modern buildings (narrower top tier)
    const setbackGeo = new THREE.BoxGeometry(1, 1, 1);
    const setbackMat = new THREE.MeshStandardMaterial({color:0x8899bb, roughness:0.35, metalness:0.35, emissive:0x8899bb, emissiveIntensity:0.06});
    const setbackItems = [];
    fillQueue.modern.forEach(b => {
      if(b.h > 25 && Math.random() < 0.35) {
        setbackItems.push({x:b.x, z:b.z, w:b.w*0.6, d:b.d*0.6, h:b.h*0.25, baseH:b.h});
      }
    });
    if(setbackItems.length > 0) {
      const sim = new THREE.InstancedMesh(setbackGeo, setbackMat, setbackItems.length);
      const sm = new THREE.Matrix4();
      setbackItems.forEach((b, idx) => {
        sm.compose(
          new THREE.Vector3(b.x, GROUND_Y + b.baseH + b.h/2, b.z),
          new THREE.Quaternion(),
          new THREE.Vector3(b.w, b.h, b.d)
        );
        sim.setMatrixAt(idx, sm);
      });
      sim.instanceMatrix.needsUpdate = true;
      cityGroup.add(sim);
    }

    // Emissive window rectangles on tall modern buildings (bright spots on faces)
    const winEmGeo = new THREE.PlaneGeometry(1, 1);
    const winWarmMat = new THREE.MeshBasicMaterial({color:0xffe8b0, transparent:true, opacity:0.7, side:THREE.DoubleSide});
    const winCoolMat2 = new THREE.MeshBasicMaterial({color:0xb0d0ff, transparent:true, opacity:0.5, side:THREE.DoubleSide});
    cityNightMats.push({m:winWarmMat, base:0.7}, {m:winCoolMat2, base:0.5});
    fillQueue.modern.forEach(b => {
      if(b.h < 12) return;
      const winCount = 2 + Math.floor(Math.random() * 4);
      for(let wi = 0; wi < winCount; wi++) {
        const wm = Math.random() < 0.2 ? winCoolMat2 : winWarmMat;
        const wn = new THREE.Mesh(winEmGeo, wm);
        const wy = GROUND_Y + b.h * (0.15 + Math.random() * 0.7);
        const wScale = 0.3 + Math.random() * 0.5;
        wn.scale.set(wScale, wScale * 0.6, 1);
        if(Math.random() < 0.5) {
          wn.position.set(b.x + (Math.random()-0.5)*b.w*0.7, wy, b.z + b.d/2 + 0.05);
        } else {
          wn.position.set(b.x + b.w/2 + 0.05, wy, b.z + (Math.random()-0.5)*b.d*0.7);
          wn.rotation.y = Math.PI/2;
        }
        cityGroup.add(wn);
      }
    });

    // Antenna/spire on the 4 tallest modern buildings
    const sortedByH = [...fillQueue.modern].sort((a,b) => b.h - a.h);
    const antMat2 = new THREE.MeshStandardMaterial({color:0xaaaaaa, roughness:0.3, metalness:0.7});
    const antLightMat2 = new THREE.MeshBasicMaterial({color:0xff2200});
    for(let ai = 0; ai < Math.min(4, sortedByH.length); ai++) {
      const b = sortedByH[ai];
      if(b.h < 20) break;
      const spireH = 3 + Math.random() * 4;
      const spire = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.12, spireH, 6), antMat2);
      spire.position.set(b.x, GROUND_Y + b.h + spireH/2, b.z);
      cityGroup.add(spire);
      const avl = new THREE.Mesh(new THREE.SphereGeometry(0.12, 4, 4), antLightMat2);
      avl.position.set(b.x, GROUND_Y + b.h + spireH + 0.2, b.z);
      cityGroup.add(avl);
    }

    // Residential buildings — 2 material groups
    const resGroups = [
      {mat: new THREE.MeshStandardMaterial({color:0x5a7088, roughness:0.38, metalness:0.32, emissive:0x5a7088, emissiveIntensity:0.04}), items:[]},
      {mat: new THREE.MeshStandardMaterial({color:0x4a6878, roughness:0.35, metalness:0.34, emissive:0x4a6878, emissiveIntensity:0.04}), items:[]},
    ];
    fillQueue.residential.forEach((b,i) => resGroups[i%2].items.push(b));
    resGroups.forEach(grp => {
      if(grp.items.length === 0) return;
      const im = new THREE.InstancedMesh(unitGeo, grp.mat, grp.items.length);
      const m = new THREE.Matrix4();
      const c = new THREE.Color();
      grp.items.forEach((b, idx) => {
        m.compose(
          new THREE.Vector3(b.x, GROUND_Y + b.h/2, b.z),
          new THREE.Quaternion(),
          new THREE.Vector3(b.w, b.h, b.d)
        );
        im.setMatrixAt(idx, m);
        const shift = (Math.random()-0.5)*0.08;
        c.copy(grp.mat.color).offsetHSL(0, shift, shift);
        im.setColorAt(idx, c);
      });
      im.instanceMatrix.needsUpdate = true;
      if(im.instanceColor) im.instanceColor.needsUpdate = true;
      cityGroup.add(im);
    });
    // Cylindrical tower buildings — blue-gray glass, higher segment count
    if(fillQueue.cylinder.length > 0) {
      const cylGeo = new THREE.CylinderGeometry(0.5, 0.5, 1, 12);
      const cylMat = new THREE.MeshStandardMaterial({color:0x7a9abb, roughness:0.35, metalness:0.3, emissive:0x7a9abb, emissiveIntensity:0.06});
      const im = new THREE.InstancedMesh(cylGeo, cylMat, fillQueue.cylinder.length);
      const m = new THREE.Matrix4();
      const c = new THREE.Color();
      fillQueue.cylinder.forEach((b, idx) => {
        m.compose(
          new THREE.Vector3(b.x, GROUND_Y + b.h/2, b.z),
          new THREE.Quaternion(),
          new THREE.Vector3(b.w, b.h, b.d)
        );
        im.setMatrixAt(idx, m);
        const shift = (Math.random()-0.5)*0.08;
        c.copy(cylMat.color).offsetHSL(shift*0.2, shift, shift*0.4);
        im.setColorAt(idx, c);
      });
      im.instanceMatrix.needsUpdate = true;
      if(im.instanceColor) im.instanceColor.needsUpdate = true;
      cityGroup.add(im);
    }
  }

  // Detailed building with windows + architectural variety
  function cityBuilding(x, z, w, d, h, addLight) {
    const g = new THREE.Group();
    const mat = bldgMats[Math.floor(Math.random()*bldgMats.length)];
    const mat2 = bldgMats[Math.floor(Math.random()*bldgMats.length)];
    const style = Math.random(); // determines building shape variety

    if(style < 0.15 && h > 12) {
      // CYLINDRICAL TOWER (like 101 California, Lumina)
      const body = new THREE.Mesh(new THREE.CylinderGeometry(w/2, w/2, h, 16), mat);
      body.position.set(0, h/2, 0); g.add(body);
      // Crown ring
      const ring = new THREE.Mesh(new THREE.TorusGeometry(w/2, 0.12, 6, 16),
        new THREE.MeshStandardMaterial({color:0x556677, metalness:0.7, roughness:0.3}));
      ring.rotation.x = Math.PI/2; ring.position.set(0, h, 0); g.add(ring);
    } else if(style < 0.35 && h > 18) {
      // STEPPED SETBACK TOWER (classic SF high-rise with base podium + tower)
      const baseH = h * 0.3;
      const towerH = h - baseH;
      const base = new THREE.Mesh(new THREE.BoxGeometry(w, baseH, d), mat);
      base.position.set(0, baseH/2, 0); g.add(base);
      const tower = new THREE.Mesh(new THREE.BoxGeometry(w*0.65, towerH, d*0.65), mat2);
      tower.position.set(0, baseH + towerH/2, 0); g.add(tower);
      // Mechanical penthouse on top
      const pent = new THREE.Mesh(new THREE.BoxGeometry(w*0.3, h*0.06, d*0.3),
        new THREE.MeshStandardMaterial({color:0x667788, roughness:0.5, metalness:0.4}));
      pent.position.set(0, h + h*0.03, 0); g.add(pent);
    } else if(style < 0.48 && h > 14) {
      // TAPERED TOWER (narrows toward top, like modern residential)
      const body = new THREE.Mesh(new THREE.CylinderGeometry(w*0.35, w/2, h, 6), mat);
      body.position.set(0, h/2, 0); g.add(body);
    } else if(style < 0.6 && h > 20) {
      // TWO-TIER TOWER with crown (like 555 California style)
      const mainH = h * 0.85;
      const body = new THREE.Mesh(new THREE.BoxGeometry(w, mainH, d), mat);
      body.position.set(0, mainH/2, 0); g.add(body);
      // Decorative crown / cap
      const crownH = h * 0.15;
      const crown = new THREE.Mesh(new THREE.BoxGeometry(w*1.05, crownH, d*1.05),
        new THREE.MeshStandardMaterial({color:0x6a8098, roughness:0.3, metalness:0.5}));
      crown.position.set(0, mainH + crownH/2, 0); g.add(crown);
    } else {
      // STANDARD BOX (but with subtle details)
      const body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
      body.position.set(0, h/2, 0); g.add(body);
    }

    // Windows on 2 faces
    const winGeo = new THREE.PlaneGeometry(w*0.08, h*0.04);
    const faces = [
      {nz:1, offX:0, offZ:d/2+0.02},
      {nz:0, offX:w/2+0.02, offZ:0},
    ];
    faces.forEach(f => {
      const cols = Math.max(2, Math.floor(w / 1.2));
      const rows = Math.max(2, Math.floor(h / 2.5));
      for(let c = 0; c < cols; c++) {
        for(let r = 0; r < rows; r++) {
          if(Math.random() < 0.3) continue;
          const wn = new THREE.Mesh(winGeo, winMat);
          const along = -w/2*0.7 + c * (w*0.7*2/Math.max(cols-1,1));
          const wy = h*0.1 + r * (h*0.8/Math.max(rows-1,1));
          if(f.nz !== 0) { wn.position.set(along, wy, f.offZ); }
          else { wn.position.set(f.offX, wy, along); wn.rotation.y = Math.PI/2; }
          g.add(wn);
        }
      }
    });

    // Rooftop features (water towers, antennas, mechanical rooms)
    if(h > 10) {
      const roofRoll = Math.random();
      if(roofRoll < 0.25) {
        // Water tower (classic SF rooftop)
        const tankMat = new THREE.MeshStandardMaterial({color:0x8a6a4a, roughness:0.8});
        const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 1.2, 8), tankMat);
        tank.position.set(w*0.2, h+0.6, d*0.15); g.add(tank);
        const tankTop = new THREE.Mesh(new THREE.ConeGeometry(0.45, 0.4, 8), tankMat);
        tankTop.position.set(w*0.2, h+1.4, d*0.15); g.add(tankTop);
      } else if(roofRoll < 0.45 && h > 20) {
        // Antenna / telecom mast
        const antMat = new THREE.MeshStandardMaterial({color:0x999999, roughness:0.3, metalness:0.7});
        const ant = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 4, 6), antMat);
        ant.position.set(0, h+2, 0); g.add(ant);
        const antLight = new THREE.Mesh(new THREE.SphereGeometry(0.1, 4, 4), avLightMat);
        antLight.position.set(0, h+4.2, 0); g.add(antLight);
      } else if(roofRoll < 0.6) {
        // HVAC / mechanical box
        const mechMat = new THREE.MeshStandardMaterial({color:0x666666, roughness:0.6, metalness:0.3});
        const mech = new THREE.Mesh(new THREE.BoxGeometry(w*0.4, 0.8, d*0.3), mechMat);
        mech.position.set(-w*0.15, h+0.4, 0); g.add(mech);
      }
    }

    if(addLight && h > 18) {
      const light = new THREE.Mesh(new THREE.SphereGeometry(0.15, 4, 4), avLightMat);
      light.position.set(0, h + 0.3, 0);
      g.add(light);
    }

    // Aviation red beacon for tall buildings (h > 30)
    if(h > 30) {
      const beacon = new THREE.Mesh(
        new THREE.SphereGeometry(0.22, 6, 6),
        new THREE.MeshBasicMaterial({color: 0xff3030})
      );
      beacon.position.set(0, h + 0.5, 0);
      g.add(beacon);
      const pl = new THREE.PointLight(0xff3030, 0.3, 8);
      pl.position.set(0, h + 0.6, 0);
      g.add(pl);
    }
    // Occasional green/white rooftop glow for mid-rise h > 20
    if(h > 20 && h <= 30 && Math.random() < 0.25) {
      const glowCol = Math.random() < 0.5 ? 0x66ff88 : 0xffffff;
      const glow = new THREE.Mesh(
        new THREE.SphereGeometry(0.18, 6, 6),
        new THREE.MeshBasicMaterial({color: glowCol})
      );
      glow.position.set(0, h + 0.35, 0);
      g.add(glow);
    }

    g.position.set(x, GROUND_Y, z);
    cityGroup.add(g);
  }

  // 181 Fremont (immediately south of Salesforce Tower — tall dark neighbor)
  cityBuilding(2, 12, 3.5, 3.5, 42, true);

  // Millennium Tower (slightly northwest)
  cityBuilding(-8, -4, 3, 3, 38, true);

  // One Rincon Hill (south, near Bay Bridge approach)
  cityBuilding(12, 22, 3, 3, 36, true);

  // ═══════════════════════════════════════════════════════
  // NAMED SF LANDMARKS (iconic 3D geometry, not procedural)
  // ═══════════════════════════════════════════════════════

  // Transamerica Pyramid — distinctive white pyramid, NW of Salesforce
  (function transamerica() {
    const px = -14, pz = -14, ph = 48;
    const g = new THREE.Group();
    const pyrMat = new THREE.MeshStandardMaterial({color:0xe8e4d8, roughness:0.35, metalness:0.2});
    const body = new THREE.Mesh(new THREE.ConeGeometry(3.6, ph, 4), pyrMat);
    body.position.set(0, ph/2, 0); body.rotation.y = Math.PI/4; g.add(body);
    // Twin wing protrusions (elevator shafts)
    const wingMat = new THREE.MeshStandardMaterial({color:0xd8d0c0, roughness:0.4});
    const wingW = 0.8, wingH = ph*0.55, wingD = 1.6;
    const wL = new THREE.Mesh(new THREE.BoxGeometry(wingW, wingH, wingD), wingMat);
    wL.position.set(-2.6, wingH/2, 0); g.add(wL);
    const wR = new THREE.Mesh(new THREE.BoxGeometry(wingW, wingH, wingD), wingMat);
    wR.position.set(2.6, wingH/2, 0); g.add(wR);
    // Spire
    const spireMat = new THREE.MeshStandardMaterial({color:0xcccccc, metalness:0.7, roughness:0.2});
    const spire = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.18, 7, 6), spireMat);
    spire.position.set(0, ph + 3.5, 0); g.add(spire);
    // Beacon
    const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.35, 8, 6),
      new THREE.MeshBasicMaterial({color:0xff4422}));
    beacon.position.set(0, ph + 7.2, 0); g.add(beacon);
    const beaconLight = new THREE.PointLight(0xff3322, 0.8, 8);
    beaconLight.position.set(0, ph + 7.2, 0); g.add(beaconLight);
    g.position.set(px, GROUND_Y, pz);
    cityGroup.add(g);
  })();

  // 555 California (aka Bank of America Center) — iconic dark monolith
  (function fiveFiveFive() {
    const cx = -16, cz = -2, ch = 44;
    const g = new THREE.Group();
    const darkMat = new THREE.MeshStandardMaterial({color:0x3a3028, roughness:0.35, metalness:0.3});
    // Chiseled facade — slightly irregular prism
    const body = new THREE.Mesh(new THREE.BoxGeometry(4.5, ch, 4.5), darkMat);
    body.position.set(0, ch/2, 0); g.add(body);
    // Crown band
    const crown = new THREE.Mesh(new THREE.BoxGeometry(4.7, 1.5, 4.7),
      new THREE.MeshStandardMaterial({color:0x4a4038, roughness:0.4}));
    crown.position.set(0, ch + 0.75, 0); g.add(crown);
    // Warm window glow
    for(let wy = 4; wy < ch - 2; wy += 2.5) {
      for(let side = 0; side < 4; side++) {
        const winMat2 = new THREE.MeshBasicMaterial({
          color: Math.random() > 0.4 ? 0xffd080 : 0x2a2018, transparent:true, opacity:0.9
        });
        const wr = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 0.3), winMat2);
        if(side === 0) { wr.position.set(0, wy, 2.27); }
        else if(side === 1) { wr.position.set(0, wy, -2.27); wr.rotation.y = Math.PI; }
        else if(side === 2) { wr.position.set(2.27, wy, 0); wr.rotation.y = Math.PI/2; }
        else { wr.position.set(-2.27, wy, 0); wr.rotation.y = -Math.PI/2; }
        g.add(wr);
      }
    }
    g.position.set(cx, GROUND_Y, cz);
    cityGroup.add(g);
  })();

  // Coit Tower — fluted cylindrical landmark on Telegraph Hill (to the north)
  (function coitTower() {
    const tx = -6, tz = -32;
    const g = new THREE.Group();
    // Telegraph Hill — small green hill base
    const hillMat = new THREE.MeshStandardMaterial({color:0x4a6a42, roughness:0.95});
    const hill = new THREE.Mesh(new THREE.ConeGeometry(7, 5, 16), hillMat);
    hill.position.set(0, 2.5, 0); g.add(hill);
    // Tower shaft — cream/limestone cylinder
    const towerMat = new THREE.MeshStandardMaterial({color:0xd8cfb8, roughness:0.6});
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.15, 11, 16), towerMat);
    shaft.position.set(0, 5 + 5.5, 0); g.add(shaft);
    // Fluted details (vertical stripes)
    for(let a = 0; a < 8; a++) {
      const flute = new THREE.Mesh(new THREE.BoxGeometry(0.08, 10.5, 0.25),
        new THREE.MeshStandardMaterial({color:0xc8bfa8, roughness:0.7}));
      const ang = (a / 8) * Math.PI * 2;
      flute.position.set(Math.cos(ang) * 1.12, 5 + 5.25, Math.sin(ang) * 1.12);
      flute.rotation.y = -ang;
      g.add(flute);
    }
    // Crenellated top
    for(let a = 0; a < 8; a++) {
      const cren = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.6, 0.35), towerMat);
      const ang = (a / 8) * Math.PI * 2;
      cren.position.set(Math.cos(ang) * 1.05, 5 + 11.3, Math.sin(ang) * 1.05);
      g.add(cren);
    }
    // Top observation ring
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.2, 0.3, 16),
      new THREE.MeshStandardMaterial({color:0xb8ad96, roughness:0.5}));
    ring.position.set(0, 5 + 11.15, 0); g.add(ring);
    g.position.set(tx, GROUND_Y, tz);
    cityGroup.add(g);
  })();

  // Ferry Building — low arcaded building with clock tower on east waterfront
  (function ferryBuilding() {
    const fx = 24, fz = -6;
    const g = new THREE.Group();
    const bldgMat = new THREE.MeshStandardMaterial({color:0xd8cdb0, roughness:0.6});
    const roofMat = new THREE.MeshStandardMaterial({color:0x5a4a38, roughness:0.7});
    // Long base (east-west axis)
    const base = new THREE.Mesh(new THREE.BoxGeometry(3.5, 4, 18), bldgMat);
    base.position.set(0, 2, 0); g.add(base);
    // Pitched roof
    const roof = new THREE.Mesh(new THREE.BoxGeometry(3.8, 0.5, 18.2), roofMat);
    roof.position.set(0, 4.25, 0); g.add(roof);
    // Clock tower in center
    const towerMat = new THREE.MeshStandardMaterial({color:0xd8cdb0, roughness:0.55});
    const tower = new THREE.Mesh(new THREE.BoxGeometry(2.2, 10, 2.2), towerMat);
    tower.position.set(0, 5, 0); g.add(tower);
    // Pyramidal roof on tower
    const tRoof = new THREE.Mesh(new THREE.ConeGeometry(1.6, 2.5, 4),
      new THREE.MeshStandardMaterial({color:0x4a3e2a, roughness:0.6}));
    tRoof.position.set(0, 10 + 1.25, 0); tRoof.rotation.y = Math.PI/4; g.add(tRoof);
    // Clock face — white circle on 4 sides
    for(let i = 0; i < 4; i++) {
      const face = new THREE.Mesh(new THREE.CircleGeometry(0.7, 20),
        new THREE.MeshBasicMaterial({color:0xf4f0e4}));
      const ang = (i / 4) * Math.PI * 2;
      face.position.set(Math.cos(ang) * 1.12, 8.5, Math.sin(ang) * 1.12);
      face.rotation.y = ang + Math.PI/2;
      g.add(face);
    }
    // Window rows on the long base
    for(let wz = -8; wz < 8; wz += 1.6) {
      const w = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 1.2),
        new THREE.MeshBasicMaterial({color:0xffd080, transparent:true, opacity:0.7}));
      w.position.set(1.77, 2, wz); w.rotation.y = Math.PI/2; g.add(w);
      const w2 = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 1.2),
        new THREE.MeshBasicMaterial({color:0xffd080, transparent:true, opacity:0.7}));
      w2.position.set(-1.77, 2, wz); w2.rotation.y = -Math.PI/2; g.add(w2);
    }
    g.position.set(fx, GROUND_Y, fz);
    cityGroup.add(g);
  })();

  // ═══════════════════════════════════════════════════════
  // ═══ BAY FEATURES ═══ — bridges, islands, headlands, port
  // ═══════════════════════════════════════════════════════

  // Golden Gate Bridge — international orange suspension bridge, NW of SF
  (function goldenGate() {
    const g = new THREE.Group();
    const orangeMat = new THREE.MeshStandardMaterial({color:0xc0362c, roughness:0.55, metalness:0.25});
    const cableMat = new THREE.MeshStandardMaterial({color:0x8a2a20, roughness:0.5, metalness:0.3});
    const deckMat = new THREE.MeshStandardMaterial({color:0x6a2018, roughness:0.7, metalness:0.15});
    const ax = -60, az = -20;
    const bx = -120, bz = -90;
    const dx = bx - ax, dz = bz - az;
    const length = Math.sqrt(dx*dx + dz*dz);
    const angle = Math.atan2(dz, dx);
    const deckY = 6;
    const deck = new THREE.Mesh(new THREE.BoxGeometry(length, 0.6, 3.5), deckMat);
    deck.position.set((ax+bx)/2, deckY, (az+bz)/2);
    deck.rotation.y = -angle;
    g.add(deck);
    const towerH = 35;
    const towerPositions = [0.3, 0.7];
    const towerWorldPos = [];
    towerPositions.forEach(t => {
      const tx = ax + dx * t;
      const tz = az + dz * t;
      towerWorldPos.push({x:tx, z:tz});
      for(let s = -1; s <= 1; s += 2) {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(1.4, towerH, 1.4), orangeMat);
        const perpX = -Math.sin(angle) * s * 1.6;
        const perpZ =  Math.cos(angle) * s * 1.6;
        leg.position.set(tx + perpX, towerH/2, tz + perpZ);
        g.add(leg);
      }
      const cross = new THREE.Mesh(new THREE.BoxGeometry(3.6, 1.0, 1.0), orangeMat);
      cross.position.set(tx, towerH - 3, tz);
      cross.rotation.y = -angle;
      g.add(cross);
      const cross2 = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.8, 1.0), orangeMat);
      cross2.position.set(tx, deckY + 0.4, tz);
      cross2.rotation.y = -angle;
      g.add(cross2);
    });
    const cablePts = [
      {x:ax, y:deckY + 1, z:az},
      {x:towerWorldPos[0].x, y:towerH - 1, z:towerWorldPos[0].z},
      {x:towerWorldPos[1].x, y:towerH - 1, z:towerWorldPos[1].z},
      {x:bx, y:deckY + 1, z:bz}
    ];
    function drawCable(p1, p2, sag, sideOffset) {
      const segs = 10;
      for(let i = 0; i < segs; i++) {
        const t1 = i/segs, t2 = (i+1)/segs;
        function pt(t) {
          const x = p1.x + (p2.x-p1.x)*t;
          const z = p1.z + (p2.z-p1.z)*t;
          const y = p1.y + (p2.y-p1.y)*t - sag * 4 * t * (1-t);
          const px = -Math.sin(angle) * sideOffset;
          const pz =  Math.cos(angle) * sideOffset;
          return {x:x+px, y:y, z:z+pz};
        }
        const a = pt(t1), b = pt(t2);
        const sx = b.x-a.x, sy = b.y-a.y, sz = b.z-a.z;
        const len = Math.sqrt(sx*sx+sy*sy+sz*sz);
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, len, 6), cableMat);
        seg.position.set((a.x+b.x)/2, (a.y+b.y)/2, (a.z+b.z)/2);
        const up = new THREE.Vector3(0,1,0);
        const dir = new THREE.Vector3(sx, sy, sz).normalize();
        const q = new THREE.Quaternion().setFromUnitVectors(up, dir);
        seg.quaternion.copy(q);
        g.add(seg);
      }
    }
    for(const side of [-1.4, 1.4]) {
      drawCable(cablePts[0], cablePts[1], 2, side);
      drawCable(cablePts[1], cablePts[2], 5, side);
      drawCable(cablePts[2], cablePts[3], 2, side);
    }
    const lampMat = new THREE.MeshBasicMaterial({color:0xffeab0});
    for(let t = 0.05; t < 1.0; t += 0.08) {
      const lx = ax + dx * t;
      const lz = az + dz * t;
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.2, 6, 4), lampMat);
      lamp.position.set(lx, deckY + 1.2, lz);
      g.add(lamp);
    }
    const ggLight = new THREE.PointLight(0xffaa66, 0.6, 40);
    ggLight.position.set((ax+bx)/2, towerH, (az+bz)/2);
    g.add(ggLight);
    // Ground on the city plane (was floating at y=0 = penthouse altitude)
    // and push NW so it spans the strait between Presidio and Marin.
    g.position.set(-30, GROUND_Y, -45);
    cityGroup.add(g);
  })();

  // Bay Bridge — western suspension span (SF → Yerba Buena) + eastern cantilever to Oakland
  (function bayBridge() {
    const g = new THREE.Group();
    const silverMat = new THREE.MeshStandardMaterial({color:0xcdd2d8, roughness:0.45, metalness:0.5});
    const cableMat = new THREE.MeshStandardMaterial({color:0x8a909a, roughness:0.5, metalness:0.4});
    const deckMat = new THREE.MeshStandardMaterial({color:0x555a60, roughness:0.7, metalness:0.2});
    const ax = 35, az = -5;
    const bx = 60, bz = -50;
    const dx = bx - ax, dz = bz - az;
    const len = Math.sqrt(dx*dx + dz*dz);
    const angle = Math.atan2(dz, dx);
    const deckY = 5.5;
    const deck = new THREE.Mesh(new THREE.BoxGeometry(len, 0.5, 3.0), deckMat);
    deck.position.set((ax+bx)/2, deckY, (az+bz)/2);
    deck.rotation.y = -angle;
    g.add(deck);
    const towerH = 30;
    const towers = [0.33, 0.66];
    const twPos = [];
    towers.forEach(t => {
      const tx = ax + dx*t, tz = az + dz*t;
      twPos.push({x:tx, z:tz});
      for(let s = -1; s <= 1; s += 2) {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(1.1, towerH, 1.1), silverMat);
        const perpX = -Math.sin(angle) * s * 1.3;
        const perpZ =  Math.cos(angle) * s * 1.3;
        leg.position.set(tx + perpX, towerH/2, tz + perpZ);
        g.add(leg);
      }
      const cr = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.8, 0.8), silverMat);
      cr.position.set(tx, towerH - 2.5, tz);
      cr.rotation.y = -angle;
      g.add(cr);
    });
    function drawBB(p1, p2, sag, sideOffset) {
      const segs = 8;
      for(let i = 0; i < segs; i++) {
        const t1 = i/segs, t2 = (i+1)/segs;
        function pt(t) {
          const x = p1.x + (p2.x-p1.x)*t;
          const z = p1.z + (p2.z-p1.z)*t;
          const y = p1.y + (p2.y-p1.y)*t - sag * 4 * t * (1-t);
          const px = -Math.sin(angle) * sideOffset;
          const pz =  Math.cos(angle) * sideOffset;
          return {x:x+px, y:y, z:z+pz};
        }
        const a = pt(t1), b = pt(t2);
        const sx = b.x-a.x, sy = b.y-a.y, sz = b.z-a.z;
        const ln = Math.sqrt(sx*sx+sy*sy+sz*sz);
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, ln, 6), cableMat);
        seg.position.set((a.x+b.x)/2, (a.y+b.y)/2, (a.z+b.z)/2);
        const up = new THREE.Vector3(0,1,0);
        const dir = new THREE.Vector3(sx, sy, sz).normalize();
        seg.quaternion.setFromUnitVectors(up, dir);
        g.add(seg);
      }
    }
    const cPts = [
      {x:ax, y:deckY+1, z:az},
      {x:twPos[0].x, y:towerH-1, z:twPos[0].z},
      {x:twPos[1].x, y:towerH-1, z:twPos[1].z},
      {x:bx, y:deckY+1, z:bz}
    ];
    for(const side of [-1.2, 1.2]) {
      drawBB(cPts[0], cPts[1], 1.5, side);
      drawBB(cPts[1], cPts[2], 4, side);
      drawBB(cPts[2], cPts[3], 1.5, side);
    }
    const lmat = new THREE.MeshBasicMaterial({color:0xffeab0});
    for(let t = 0.05; t < 1.0; t += 0.1) {
      const lx = ax + dx*t, lz = az + dz*t;
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.15, 6, 4), lmat);
      lamp.position.set(lx, deckY + 1, lz);
      g.add(lamp);
    }
    // Eastern cantilever: (60, -50) → (100, -25)
    const ex = 60, ez = -50;
    const fx2 = 100, fz2 = -25;
    const edx = fx2 - ex, edz = fz2 - ez;
    const eangle = Math.atan2(edz, edx);
    const elen = Math.sqrt(edx*edx + edz*edz);
    const edeck = new THREE.Mesh(new THREE.BoxGeometry(elen, 0.5, 2.6), deckMat);
    edeck.position.set((ex+fx2)/2, deckY, (ez+fz2)/2);
    edeck.rotation.y = -eangle;
    g.add(edeck);
    const pylons = 4;
    for(let i = 1; i <= pylons; i++) {
      const t = i/(pylons+1);
      const px = ex + edx*t, pz = ez + edz*t;
      const pyl = new THREE.Mesh(new THREE.BoxGeometry(0.8, deckY, 0.8), silverMat);
      pyl.position.set(px, deckY/2, pz); g.add(pyl);
      const truss = new THREE.Mesh(new THREE.BoxGeometry(0.5, 4, 0.5), silverMat);
      truss.position.set(px, deckY + 2, pz); g.add(truss);
    }
    g.position.set(0, GROUND_Y, 0); // ground it (was floating at penthouse altitude)
    cityGroup.add(g);
  })();

  // Alcatraz Island
  (function alcatraz() {
    const g = new THREE.Group();
    const rockMat = new THREE.MeshStandardMaterial({color:0x8a8070, roughness:0.95, metalness:0.05});
    const prisonMat = new THREE.MeshStandardMaterial({color:0xe8e0d0, roughness:0.7});
    const roofMat = new THREE.MeshStandardMaterial({color:0x5a4a38, roughness:0.8});
    const base = new THREE.Mesh(new THREE.BoxGeometry(6, 1, 3), rockMat);
    base.position.set(0, 0.3, 0); g.add(base);
    const tier2 = new THREE.Mesh(new THREE.BoxGeometry(4.5, 0.8, 2.2), rockMat);
    tier2.position.set(0, 1.2, 0); g.add(tier2);
    const pMain = new THREE.Mesh(new THREE.BoxGeometry(3.5, 1.4, 1.2), prisonMat);
    pMain.position.set(0, 2.3, 0); g.add(pMain);
    const pRoof = new THREE.Mesh(new THREE.BoxGeometry(3.7, 0.2, 1.3), roofMat);
    pRoof.position.set(0, 3.1, 0); g.add(pRoof);
    const pSec = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.0, 0.9), prisonMat);
    pSec.position.set(-1.8, 2.1, 0.3); g.add(pSec);
    const pW = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.8, 0.7), prisonMat);
    pW.position.set(1.8, 2.0, -0.3); g.add(pW);
    const lhMat = new THREE.MeshStandardMaterial({color:0xf0f0f0, roughness:0.6});
    const lh = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.22, 2.5, 10), lhMat);
    lh.position.set(1.3, 3.85, 0); g.add(lh);
    const lhCap = new THREE.Mesh(new THREE.ConeGeometry(0.3, 0.5, 10),
      new THREE.MeshStandardMaterial({color:0x8a1a12, roughness:0.5}));
    lhCap.position.set(1.3, 5.35, 0); g.add(lhCap);
    const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.18, 8, 6),
      new THREE.MeshBasicMaterial({color:0xff2020}));
    beacon.position.set(1.3, 5.0, 0); g.add(beacon);
    const bLight = new THREE.PointLight(0xff3030, 0.9, 12);
    bLight.position.set(1.3, 5.0, 0); g.add(bLight);
    g.position.set(-15, GROUND_Y - 0.2, -55);
    cityGroup.add(g);
  })();

  // Angel Island
  (function angelIsland() {
    const g = new THREE.Group();
    const greenMat = new THREE.MeshStandardMaterial({color:0x3e6a38, roughness:0.95});
    const darkGreen = new THREE.MeshStandardMaterial({color:0x2e5028, roughness:0.95});
    const rockMat = new THREE.MeshStandardMaterial({color:0x7a7060, roughness:0.95});
    const base = new THREE.Mesh(new THREE.BoxGeometry(12, 0.8, 8), rockMat);
    base.position.set(0, 0.2, 0); g.add(base);
    const hill = new THREE.Mesh(new THREE.ConeGeometry(5.5, 5, 12), greenMat);
    hill.position.set(0, 3.1, 0); g.add(hill);
    const h2 = new THREE.Mesh(new THREE.SphereGeometry(2.5, 10, 8), darkGreen);
    h2.position.set(-3, 0.9, 1.5); h2.scale.set(1, 0.6, 1); g.add(h2);
    const h3 = new THREE.Mesh(new THREE.SphereGeometry(2.2, 10, 8), greenMat);
    h3.position.set(3, 0.8, -1.8); h3.scale.set(1, 0.55, 1); g.add(h3);
    g.position.set(-25, GROUND_Y - 0.2, -75);
    cityGroup.add(g);
  })();

  // Yerba Buena + Treasure Island
  (function ybiTi() {
    const g = new THREE.Group();
    const greenMat = new THREE.MeshStandardMaterial({color:0x4a6a42, roughness:0.95});
    const rockMat = new THREE.MeshStandardMaterial({color:0x7a7060, roughness:0.95});
    const flatMat = new THREE.MeshStandardMaterial({color:0x5c7a4e, roughness:0.9});
    const ybiBase = new THREE.Mesh(new THREE.BoxGeometry(10, 0.6, 8), rockMat);
    ybiBase.position.set(0, 0.15, 4); g.add(ybiBase);
    const ybiHill = new THREE.Mesh(new THREE.ConeGeometry(4.5, 4.5, 12), greenMat);
    ybiHill.position.set(0, 2.7, 4); g.add(ybiHill);
    const ti = new THREE.Mesh(new THREE.BoxGeometry(11, 0.5, 10), flatMat);
    ti.position.set(0, 0.15, -6); g.add(ti);
    const bMat = new THREE.MeshStandardMaterial({color:0xc8c0b0, roughness:0.7});
    for(let i = 0; i < 4; i++) {
      const bb = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.5, 1.2), bMat);
      bb.position.set(-3 + i*2, 1.15, -6 + (i%2)*1.5);
      g.add(bb);
    }
    g.position.set(50, GROUND_Y - 0.2, -55);
    cityGroup.add(g);
  })();

  // Marin Headlands — far NW rolling hills
  (function marinHeadlands() {
    const g = new THREE.Group();
    const hillMat = new THREE.MeshStandardMaterial({color:0x6a6838, roughness:0.95});
    const hillMat2 = new THREE.MeshStandardMaterial({color:0x585a2e, roughness:0.95});
    const hillMat3 = new THREE.MeshStandardMaterial({color:0x7a7848, roughness:0.95});
    const base = new THREE.Mesh(new THREE.BoxGeometry(70, 0.8, 55), hillMat);
    base.position.set(0, 0.2, 0); g.add(base);
    const hillSpecs = [
      {x:-20, z:-10, r:14, h:14, m:hillMat},
      {x:  5, z:  5, r:16, h:17, m:hillMat2},
      {x: 22, z: -8, r:12, h:11, m:hillMat3},
      {x:-10, z: 15, r:10, h: 9, m:hillMat2},
      {x: 15, z: 18, r:11, h:12, m:hillMat},
      {x:-25, z: 18, r: 9, h: 8, m:hillMat3},
    ];
    hillSpecs.forEach(s => {
      const h = new THREE.Mesh(new THREE.ConeGeometry(s.r, s.h, 14), s.m);
      h.position.set(s.x, s.h/2, s.z); g.add(h);
    });
    g.position.set(-100, GROUND_Y - 0.2, -160);
    cityGroup.add(g);
  })();

  // Oakland port — cranes along east shoreline
  (function oaklandPort() {
    const g = new THREE.Group();
    const craneMat = new THREE.MeshStandardMaterial({color:0xd43a20, roughness:0.55, metalness:0.4});
    const craneMat2 = new THREE.MeshStandardMaterial({color:0xe8e4d4, roughness:0.6});
    const deckMat = new THREE.MeshStandardMaterial({color:0x4a4640, roughness:0.8});
    const dock = new THREE.Mesh(new THREE.BoxGeometry(60, 0.4, 18), deckMat);
    dock.position.set(130, 0.2, -25); g.add(dock);
    const craneX = [104, 118, 132, 146, 158];
    craneX.forEach((cx, i) => {
      const col = (i % 2 === 0) ? craneMat : craneMat2;
      const craneZ = -28 + (i % 2) * 4;
      const ch = 22;
      for(const lx of [-2.2, 2.2]) {
        for(const lz of [-1.8, 1.8]) {
          const leg = new THREE.Mesh(new THREE.BoxGeometry(0.5, ch, 0.5), col);
          leg.position.set(cx + lx, ch/2, craneZ + lz);
          g.add(leg);
        }
      }
      const plat = new THREE.Mesh(new THREE.BoxGeometry(5.5, 1.2, 4.5), col);
      plat.position.set(cx, ch + 0.6, craneZ); g.add(plat);
      const boom = new THREE.Mesh(new THREE.BoxGeometry(1.0, 1.0, 16), col);
      boom.position.set(cx, ch + 1.4, craneZ - 4); g.add(boom);
      const cw = new THREE.Mesh(new THREE.BoxGeometry(1.0, 1.0, 6), col);
      cw.position.set(cx, ch + 1.4, craneZ + 4.5); g.add(cw);
      const cab = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.0, 1.2),
        new THREE.MeshStandardMaterial({color:0x333333, roughness:0.4}));
      cab.position.set(cx, ch + 0.8, craneZ - 2.5); g.add(cab);
      const wl = new THREE.Mesh(new THREE.SphereGeometry(0.15, 6, 4),
        new THREE.MeshBasicMaterial({color:0xff4040}));
      wl.position.set(cx, ch + 2.2, craneZ); g.add(wl);
    });
    g.position.y = GROUND_Y; // ground the port (was floating at penthouse altitude)
    cityGroup.add(g);
  })();

  // ═══════════════════════════════════════════════════════
  // ═══ SF DISTRICTS ═══
  // Named neighborhoods and landmarks surrounding downtown
  // ═══════════════════════════════════════════════════════

  // Golden Gate Park — west green strip
  (function goldenGatePark() {
    const lawnMat = new THREE.MeshStandardMaterial({color:0x2e6b2a, roughness:0.95});
    const lawn = new THREE.Mesh(new THREE.PlaneGeometry(35, 30), lawnMat);
    lawn.rotation.x = -Math.PI/2;
    lawn.position.set(-77.5, GROUND_Y + 0.12, 0);
    cityGroup.add(lawn);
    const treeMat = new THREE.MeshStandardMaterial({color:0x1b4a1c, roughness:0.9});
    const trunkMat = new THREE.MeshStandardMaterial({color:0x3a2a18, roughness:0.9});
    for(let i = 0; i < 10; i++) {
      const tx = -62 - Math.random() * 32;
      const tz = -14 + Math.random() * 28;
      const th = 2.5 + Math.random() * 1.8;
      const tree = new THREE.Mesh(new THREE.ConeGeometry(1.2, th, 8), treeMat);
      tree.position.set(tx, GROUND_Y + th/2 + 0.5, tz);
      cityGroup.add(tree);
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.22, 0.6, 6), trunkMat);
      trunk.position.set(tx, GROUND_Y + 0.3, tz);
      cityGroup.add(trunk);
    }
  })();

  // Presidio — northwest forested cluster + Palace of Fine Arts
  (function presidioForest() {
    const floorMat = new THREE.MeshStandardMaterial({color:0x2d5a2a, roughness:0.95});
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 50), floorMat);
    floor.rotation.x = -Math.PI/2;
    floor.position.set(-75, GROUND_Y + 0.13, -55);
    cityGroup.add(floor);
    const conifMat = new THREE.MeshStandardMaterial({color:0x163a1a, roughness:0.9});
    const trunkMat = new THREE.MeshStandardMaterial({color:0x2e1e10, roughness:0.9});
    for(let i = 0; i < 26; i++) {
      const tx = -61 - Math.random() * 29;
      const tz = -30 - Math.random() * 50;
      const th = 3 + Math.random() * 2.5;
      const cone = new THREE.Mesh(new THREE.ConeGeometry(1.0 + Math.random()*0.4, th, 7), conifMat);
      cone.position.set(tx, GROUND_Y + th/2 + 0.4, tz);
      cityGroup.add(cone);
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.2, 0.6, 6), trunkMat);
      trunk.position.set(tx, GROUND_Y + 0.3, tz);
      cityGroup.add(trunk);
    }
    // Palace of Fine Arts at (-65, -50)
    const pofa = new THREE.Group();
    const domeMat = new THREE.MeshStandardMaterial({color:0xd9a06b, roughness:0.6});
    const dome = new THREE.Mesh(
      new THREE.SphereGeometry(3.2, 24, 16, 0, Math.PI*2, 0, Math.PI/2),
      domeMat
    );
    dome.position.set(0, 2, 0);
    pofa.add(dome);
    // Drum under dome
    const drum = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.4, 2, 20), domeMat);
    drum.position.set(0, 1, 0);
    pofa.add(drum);
    // Column row
    const colMat = new THREE.MeshStandardMaterial({color:0xe8d8b8, roughness:0.6});
    for(let i = -3; i <= 3; i++) {
      const col = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 3.2, 10), colMat);
      col.position.set(i * 0.9, 1.6, 3);
      pofa.add(col);
    }
    // Reflecting pool
    const poolMat = new THREE.MeshStandardMaterial({color:0x3a6a9a, roughness:0.35, metalness:0.3});
    const pool = new THREE.Mesh(new THREE.PlaneGeometry(9, 4), poolMat);
    pool.rotation.x = -Math.PI/2;
    pool.position.set(0, 0.2, 6);
    pofa.add(pool);
    pofa.position.set(-65, GROUND_Y + 0.2, -50);
    cityGroup.add(pofa);
  })();

  // Chinatown / North Beach — mid-height ornate buildings north of FiDi
  (function chinatownNorthBeach() {
    const spots = [
      [-8, -18, 3, 3, 10],
      [-2, -20, 3, 3, 13],
      [4, -18, 3, 3, 11],
      [8, -22, 3, 3, 9],
      [-4, -26, 3, 3, 12],
      [2, -28, 3, 3, 14],
      [8, -28, 3, 3, 10],
      [-10, -24, 3, 3, 8],
    ];
    spots.forEach(function(s) {
      cityBuilding(s[0], s[1], s[2], s[3], s[4], s[4] > 11);
    });
    // Pagoda roofs — stacked cones on 2-3 buildings
    const pagodaMat = new THREE.MeshStandardMaterial({color:0xa83030, roughness:0.6});
    const pagodaSpots = [[-2, -20, 13], [2, -28, 14], [-4, -26, 12]];
    pagodaSpots.forEach(function(p) {
      const g = new THREE.Group();
      for(let t = 0; t < 3; t++) {
        const r = 2.2 - t * 0.6;
        const cone = new THREE.Mesh(new THREE.ConeGeometry(r, 0.8, 4), pagodaMat);
        cone.rotation.y = Math.PI/4;
        cone.position.y = t * 0.9;
        g.add(cone);
      }
      g.position.set(p[0], GROUND_Y + p[2] + 0.4, p[1]);
      cityGroup.add(g);
    });
  })();

  // Fisherman's Wharf / Piers — wooden piers extending from north shore into bay
  (function fishermansWharf() {
    const pierMat = new THREE.MeshStandardMaterial({color:0x9a7a4e, roughness:0.85});
    const whMat = new THREE.MeshStandardMaterial({color:0xc0b090, roughness:0.75});
    const pierXs = [-18, -9, 0, 9, 18];
    pierXs.forEach(function(px) {
      const pier = new THREE.Mesh(new THREE.BoxGeometry(4, 0.4, 8), pierMat);
      pier.position.set(px, GROUND_Y + 0.2, -24);
      cityGroup.add(pier);
      // Warehouse on pier
      const wh = new THREE.Mesh(new THREE.BoxGeometry(3, 2.2, 5), whMat);
      wh.position.set(px, GROUND_Y + 0.4 + 1.1, -24);
      cityGroup.add(wh);
      // Roof
      const roof = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.3, 5.2),
        new THREE.MeshStandardMaterial({color:0x552e1e, roughness:0.8}));
      roof.position.set(px, GROUND_Y + 0.4 + 2.35, -24);
      cityGroup.add(roof);
    });
  })();

  // Lombard Street zig-zag — winding red road with pale edges
  (function lombardStreet() {
    const roadMat = new THREE.MeshStandardMaterial({color:0x552822, roughness:0.85});
    const edgeMat = new THREE.MeshStandardMaterial({color:0xb8a078, roughness:0.9});
    const road = new THREE.Mesh(new THREE.PlaneGeometry(3, 10), roadMat);
    road.rotation.x = -Math.PI/2;
    road.position.set(-15, GROUND_Y + 0.18, -20);
    cityGroup.add(road);
    // Alternating segment hatches
    for(let i = 0; i < 6; i++) {
      const seg = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 0.5), edgeMat);
      seg.rotation.x = -Math.PI/2;
      seg.position.set(-15 + (i%2===0 ? -0.2 : 0.2), GROUND_Y + 0.2, -24 + i * 1.5);
      cityGroup.add(seg);
    }
  })();

  // Oracle Park — south waterfront stadium
  (function oraclePark() {
    const g = new THREE.Group();
    const standMat = new THREE.MeshStandardMaterial({color:0x8b3a2a, roughness:0.75});
    // Partial-arc stands (open to NE toward the bay)
    const stands = new THREE.Mesh(
      new THREE.CylinderGeometry(9, 10, 6, 40, 1, true, Math.PI * 0.25, Math.PI * 1.5),
      standMat
    );
    stands.position.set(0, 3, 0);
    g.add(stands);
    // Playing field
    const fieldMat = new THREE.MeshStandardMaterial({color:0x3a7a35, roughness:0.9});
    const field = new THREE.Mesh(new THREE.CircleGeometry(8, 32), fieldMat);
    field.rotation.x = -Math.PI/2;
    field.position.set(0, 0.2, 0);
    g.add(field);
    // Light pylons
    const pylonMat = new THREE.MeshStandardMaterial({color:0x444444, roughness:0.6});
    const bulbMat = new THREE.MeshBasicMaterial({color:0xfff2c0});
    for(let i = 0; i < 6; i++) {
      const ang = Math.PI * 0.3 + (i / 5) * Math.PI * 1.4;
      const px = Math.cos(ang) * 9.5;
      const pz = Math.sin(ang) * 9.5;
      const pyl = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 9, 8), pylonMat);
      pyl.position.set(px, 4.5, pz);
      g.add(pyl);
      const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.4, 10, 8), bulbMat);
      bulb.position.set(px, 9.2, pz);
      g.add(bulb);
    }
    g.position.set(15, GROUND_Y, 25);
    cityGroup.add(g);
  })();

  // Mission District — colorful pastel Victorian row homes south of SoMa
  (function missionDistrict() {
    const pastels = [0xe8a6b8, 0xf0d48a, 0xb8d8e8, 0xd8b8e0, 0xe8c8a0, 0xbfe0b5, 0xf0b4a0];
    for(let gx = -28; gx <= 28; gx += 3) {
      for(let gz = 46; gz <= 74; gz += 3.5) {
        if(Math.random() < 0.22) continue;
        const h = 4 + Math.random() * 4;
        const w = 2 + Math.random();
        const d = 2 + Math.random();
        fillBuilding(gx + (Math.random()-0.5)*0.4, gz + (Math.random()-0.5)*0.4, w, d, h, true);
        // Occasional colored roof marker (pastel bay-window hint)
        if(Math.random() < 0.35) {
          const color = pastels[Math.floor(Math.random()*pastels.length)];
          const accent = new THREE.Mesh(
            new THREE.BoxGeometry(w*0.8, 0.3, d*0.8),
            new THREE.MeshStandardMaterial({color:color, roughness:0.7})
          );
          accent.position.set(gx, GROUND_Y + h + 0.15, gz);
          cityGroup.add(accent);
        }
      }
    }
  })();

  // ═══════════════════════════════════════════════════════
  // STREET GRID — asphalt plane with lane markings
  // ═══════════════════════════════════════════════════════
  (function streetGrid() {
    const SIZE = 160;                 // world units covered (cityRange=80 each side)
    const TEX = 2048;                 // canvas resolution
    const BLK = 6;                    // matches BLOCK spacing
    const pxPerUnit = TEX / SIZE;     // pixels per world unit
    const cnv = document.createElement('canvas');
    cnv.width = TEX; cnv.height = TEX;
    const c = cnv.getContext('2d');
    // Asphalt base
    c.fillStyle = '#1a1a1c';
    c.fillRect(0, 0, TEX, TEX);
    // Helper: convert world (x,z) to canvas (px,py). World x:-80..80, z:-80..80
    function wx(x) { return (x + SIZE/2) * pxPerUnit; }
    function wz(z) { return (z + SIZE/2) * pxPerUnit; }
    // Park exclusion check (skip drawing lines inside)
    function inPark(x, z) {
      if(x >= -96 && x <= -59 && z >= -16 && z <= 16) return true;     // Golden Gate Park
      if(x >= -91 && x <= -59 && z >= -82 && z <= -28) return true;    // Presidio
      return false;
    }
    // Paint parks green
    c.fillStyle = '#2e5d2a';
    c.fillRect(wx(-80), wz(-16), (-59-(-80))*pxPerUnit, 32*pxPerUnit);
    c.fillRect(wx(-80), wz(-82), (-59-(-80))*pxPerUnit, 54*pxPerUnit);
    // Minor street lane markings (dashed white) every BLOCK
    c.strokeStyle = '#ededed';
    c.lineWidth = 1.5;
    c.setLineDash([10, 14]);
    for(let x = -80; x <= 80; x += BLK) {
      // N-S street
      for(let z = -80; z < 80; z += 4) {
        if(inPark(x, z)) continue;
        c.beginPath();
        c.moveTo(wx(x), wz(z));
        c.lineTo(wx(x), wz(z + 3));
        c.stroke();
      }
    }
    for(let z = -80; z <= 80; z += BLK) {
      for(let x = -80; x < 80; x += 4) {
        if(inPark(x, z)) continue;
        c.beginPath();
        c.moveTo(wx(x), wz(z));
        c.lineTo(wx(x + 3), wz(z));
        c.stroke();
      }
    }
    c.setLineDash([]);
    // Major avenues: yellow double lines
    function majorLine(x1, z1, x2, z2) {
      c.strokeStyle = '#f5c542';
      c.lineWidth = 3;
      const dx = x2 - x1, dz = z2 - z1;
      const len = Math.sqrt(dx*dx + dz*dz);
      const nx = -dz / len * 0.4, nz = dx / len * 0.4; // offset normal
      c.beginPath();
      c.moveTo(wx(x1 + nx), wz(z1 + nz));
      c.lineTo(wx(x2 + nx), wz(z2 + nz));
      c.stroke();
      c.beginPath();
      c.moveTo(wx(x1 - nx), wz(z1 - nz));
      c.lineTo(wx(x2 - nx), wz(z2 - nz));
      c.stroke();
    }
    // Market St — diagonal from SW to NE (downtown)
    majorLine(-40, 40, 28, -14);
    // Van Ness — N-S around x=-30
    majorLine(-30, -80, -30, 80);
    // Mission St — parallel to Market, slight offset
    majorLine(-20, 40, -2, -20);
    // Embarcadero — curves along waterfront (approximated as 2 segments)
    majorLine(-20, -18, 20, -16);
    majorLine(20, -16, 32, 0);

    const tex = new THREE.CanvasTexture(cnv);
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.repeat.set(1, 1);
    const mat = new THREE.MeshBasicMaterial({map: tex, transparent: true, opacity: 0.95, depthWrite: false});
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE), mat);
    plane.rotation.x = -Math.PI / 2;
    plane.position.set(0, GROUND_Y + 0.01, 0);
    plane.renderOrder = 0.6;
    cityGroup.add(plane);
  })();

  // ═══════════════════════════════════════════════════════
  // BAY WATER OVERLAY — richer material with ripple texture
  // ═══════════════════════════════════════════════════════
  (function bayWaterOverlay() {
    const TEX = 1024;
    const cnv = document.createElement('canvas');
    cnv.width = TEX; cnv.height = TEX;
    const c = cnv.getContext('2d');
    // Base water color
    c.fillStyle = '#2a5a78';
    c.fillRect(0, 0, TEX, TEX);
    // Wavy bright streaks (moire pattern of sine curves)
    c.strokeStyle = 'rgba(180,220,240,0.18)';
    c.lineWidth = 1.2;
    for(let y = 0; y < TEX; y += 6) {
      c.beginPath();
      for(let x = 0; x < TEX; x += 4) {
        const yy = y + Math.sin(x * 0.02 + y * 0.015) * 3 + Math.sin(x * 0.007) * 5;
        if(x === 0) c.moveTo(x, yy); else c.lineTo(x, yy);
      }
      c.stroke();
    }
    // Sparse brighter highlights
    c.strokeStyle = 'rgba(255,250,220,0.22)';
    c.lineWidth = 1;
    for(let i = 0; i < 120; i++) {
      const x = Math.random() * TEX, y = Math.random() * TEX, w = 20 + Math.random() * 60;
      c.beginPath();
      c.moveTo(x, y); c.lineTo(x + w, y + Math.sin(i) * 3);
      c.stroke();
    }
    const tex = new THREE.CanvasTexture(cnv);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(4, 4);
    tex.minFilter = THREE.LinearFilter;
    const mat = new THREE.MeshStandardMaterial({
      color: 0x2a5a78, roughness: 0.25, metalness: 0.7,
      transparent: true, opacity: 0.92, map: tex,
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(360, 210), mat);
    plane.rotation.x = -Math.PI / 2;
    // Center roughly over water area: x:-140..200 => cx=30; z:-210..-18 => cz=-114
    plane.position.set(30, GROUND_Y - 0.15, -114);
    plane.renderOrder = 0.8;
    cityGroup.add(plane);
  })();

  // ═══════════════════════════════════════════════════════
  // STREET LAMPS — sparse yellow points along major avenues
  // ═══════════════════════════════════════════════════════
  (function streetLamps() {
    const lampMat = new THREE.MeshBasicMaterial({color: 0xffe8a0});
    const lampGeo = new THREE.SphereGeometry(0.18, 6, 6);
    function addLamp(x, z) {
      const m = new THREE.Mesh(lampGeo, lampMat);
      m.position.set(x, GROUND_Y + 2.2, z);
      cityGroup.add(m);
      const pl = new THREE.PointLight(0xffd07a, 0.35, 7);
      pl.position.set(x, GROUND_Y + 2.2, z);
      cityGroup.add(pl);
    }
    // Market St (diagonal from (-40,40) to (28,-14))
    for(let t = 0; t <= 1.0001; t += 0.12) {
      addLamp(-40 + t * 68, 40 + t * -54);
    }
    // Van Ness (N-S at x=-30)
    for(let z = -70; z <= 70; z += 14) addLamp(-30, z);
    // Embarcadero waterfront
    for(let x = -20; x <= 32; x += 8) addLamp(x, -17);
  })();

  // ═══════════════════════════════════════════════════════
  // PROCEDURAL CITY FILL — every city block gets buildings
  // SF has a tight grid, ~8 unit spacing matches block scale
  // ═══════════════════════════════════════════════════════

  // Height map function — returns expected building height for a zone
  // SF geography: FiDi (west) tallest, SoMa (south) medium, waterfront (north/east) low
  function getZoneHeight(x, z) {
    // Distance from Salesforce Tower (0,0)
    const dist = Math.sqrt(x*x + z*z);
    // Height jitter — skewed toward taller for dramatic variety
    const jitter = Math.pow(Math.random(), 0.7);

    // FiDi cluster (west, x < -10) — tallest, 25-60 range
    if(x < -10 && z > -15 && z < 15) {
      const fidiFactor = Math.max(0, 1 - Math.abs(x+22)/30);
      return 25 + fidiFactor * 35 + jitter*18;
    }
    // SoMa (south, z > 12) — medium height, 8-35 range
    if(z > 12) {
      const somaFade = Math.max(0, 1 - (z-12)/50);
      return 8 + somaFade * 22 + jitter*12;
    }
    // Embarcadero/waterfront (east, x > 14) — 10-28 range
    if(x > 14 && z > -20) {
      return 10 + jitter*18;
    }
    // North Beach / waterfront (north, z < -12) — low, 4-12
    if(z < -12) {
      return 4 + Math.random()*8;
    }
    // Immediate vicinity of Salesforce — tall mixed-use, 18-55
    if(dist < 18) {
      return 18 + jitter*37;
    }
    // General inner city — 10-35 with occasional tall towers
    if(dist < 40) {
      const spike = Math.random() < 0.08 ? 20 : 0;
      return 10 + jitter*18 + spike;
    }
    // Outer neighborhoods — 5-15
    return 5 + Math.random()*10;
  }

  // Is this position in the water? (Bay wraps north and east of the peninsula)
  function isWater(x, z) {
    // Presidio land: x:-90 to -30, z:-18 to -100 — NOT water
    if(x >= -90 && x <= -30 && z >= -100 && z <= -18) return false;
    // Marin Headlands / Sausalito land: x:-140 to -60, z:-130 to -210 — NOT water
    if(x >= -140 && x <= -60 && z >= -210 && z <= -130) return false;
    // Yerba Buena / Treasure Island: x:42 to 68, z:-70 to -40 — NOT water
    if(x >= 42 && x <= 68 && z >= -70 && z <= -40) return false;
    // Oakland land: x:80 to 200, z:-140 to -30 — NOT water
    if(x >= 80 && x <= 200 && z >= -140 && z <= -30) return false;
    // Bay — everything north of waterfront is water (unless excluded above)
    if(z < -18) return true;
    if(x > 35 && z < -5) return true; // East bay shoreline curves
    if(x > 50 && z < 5) return true; // Further east shore
    if(x > 65) return true; // Deep east — all water before Oakland
    return false;
  }

  // Is this position too close to Salesforce Tower base?
  function isTowerZone(x, z) {
    if(Math.abs(x) < 8 && Math.abs(z) < 7) return true;
    // Named landmark exclusion zones (Transamerica, 555 Cal, Coit, Ferry Building)
    if(Math.abs(x - (-14)) < 5 && Math.abs(z - (-14)) < 5) return true; // Transamerica
    if(Math.abs(x - (-16)) < 4 && Math.abs(z - (-2)) < 4) return true;  // 555 California
    if(Math.abs(x - (-6)) < 8 && Math.abs(z - (-32)) < 8) return true;  // Coit Tower + hill
    if(Math.abs(x - 24) < 4 && Math.abs(z - (-6)) < 11) return true;    // Ferry Building
    // New SF districts
    if(x >= -96 && x <= -59 && z >= -16 && z <= 16) return true;        // Golden Gate Park
    if(x >= -91 && x <= -59 && z >= -82 && z <= -28) return true;       // Presidio (incl. Palace of Fine Arts)
    if(Math.sqrt((x-15)*(x-15) + (z-25)*(z-25)) < 12) return true;      // Oracle Park
    if(x >= -22 && x <= 22 && z >= -27 && z <= -21) return true;        // Fisherman's Wharf piers
    if(Math.abs(x - (-15)) < 2.5 && z >= -26 && z <= -15) return true;  // Lombard Street
    return false;
  }

  // ── FILL THE ENTIRE CITY GRID ──
  const BLOCK = 6; // city block spacing
  const STREET_GAP = 1.5; // leave gap for streets
  const cityRange = 80; // how far city extends from center

  for(let gx = -cityRange; gx <= cityRange; gx += BLOCK) {
    for(let gz = -40; gz <= cityRange; gz += BLOCK) {
      // Skip water, tower zone
      if(isWater(gx, gz)) continue;
      if(isTowerZone(gx, gz)) continue;

      const bw = BLOCK - STREET_GAP - Math.random()*0.5;
      const bd = BLOCK - STREET_GAP - Math.random()*0.5;
      const bh = getZoneHeight(gx, gz);

      // Skip very short buildings at edges (tapering off)
      if(bh < 3) continue;

      const dist = Math.sqrt(gx*gx + gz*gz);
      const isNear = dist < 25;
      const isResidential = gz > 30 || gx < -45 || gx > 35;

      // Sometimes split a block into 2-3 buildings for variety
      if(Math.random() > 0.6 && bw > 4) {
        // Split block: 2 buildings side by side
        const split = bw * (0.4 + Math.random()*0.2);
        const h1 = bh * (0.7 + Math.random()*0.5);
        const h2 = bh * (0.6 + Math.random()*0.6);
        if(isNear && h1 > 15) {
          cityBuilding(gx - split/2, gz, split-0.3, bd, h1, h1>25);
        } else {
          fillBuilding(gx - split/2, gz, split-0.3, bd, h1, isResidential);
        }
        if(isNear && h2 > 15) {
          cityBuilding(gx + split/2 + 0.3, gz, bw-split-0.3, bd, h2, h2>25);
        } else {
          fillBuilding(gx + split/2 + 0.3, gz, bw-split-0.3, bd, h2, isResidential);
        }
      } else {
        // Single building per block
        const h = bh * (0.7 + Math.random()*0.4);
        if(isNear && h > 15) {
          cityBuilding(gx, gz, bw, bd, h, h>25);
        } else {
          fillBuilding(gx, gz, bw, bd, h, isResidential);
        }
      }

      // Some blocks get a second smaller building behind (like real SF density)
      if(Math.random() > 0.65 && !isWater(gx, gz+2)) {
        const h2 = bh * (0.3 + Math.random()*0.4);
        if(h2 > 3) {
          fillBuilding(gx + (Math.random()-0.5)*2, gz + 1.5, 2+Math.random()*2, 2+Math.random(), h2, true);
        }
      }
    }
  }

  // ── WATERFRONT/NORTH — piers and low buildings along Embarcadero ──
  for(let gx = -25; gx <= 30; gx += 6) {
    // Low pier buildings right at waterline
    const h = 3 + Math.random()*4;
    fillBuilding(gx, -16, 4+Math.random()*2, 3, h, false);
  }

  // ── OAKLAND ACROSS THE BAY (far east, behind water) ──
  // Oakland ground (raised above water)
  const oaklandGround = new THREE.Mesh(
    new THREE.PlaneGeometry(120, 100),
    new THREE.MeshStandardMaterial({color:0x1a1a22, roughness:0.85, metalness:0.1})
  );
  oaklandGround.rotation.x = -Math.PI/2;
  oaklandGround.position.set(130, GROUND_Y + 0.2, -80);
  cityGroup.add(oaklandGround);
  for(let gx = 90; gx <= 180; gx += 7) {
    for(let gz = -120; gz <= -40; gz += 7) {
      const dist = Math.abs(gx-130);
      const h = 8 + Math.random()*12 + Math.max(0, 18-dist*0.3);
      fillBuilding(gx, gz, 4+Math.random()*3, 4+Math.random()*3, h, false);
    }
  }

  // ── FAR-FIELD NEIGHBORHOODS (extend city to horizon) ──
  // These use larger blocks + InstancedMesh for performance
  // Western neighborhoods (Richmond, Sunset — low residential)
  for(let gx = -130; gx <= -80; gx += 10) {
    for(let gz = -20; gz <= 80; gz += 10) {
      const h = 4 + Math.random()*6;
      fillBuilding(gx, gz, 6+Math.random()*3, 6+Math.random()*3, h, true);
    }
  }
  // Southern neighborhoods (Mission, Noe Valley, Castro — medium)
  for(let gx = -60; gx <= 60; gx += 10) {
    for(let gz = 80; gz <= 150; gz += 10) {
      const fade = Math.max(0, 1 - (gz-80)/70);
      const h = 4 + fade*8 + Math.random()*5;
      if(h > 3) fillBuilding(gx, gz, 5+Math.random()*4, 5+Math.random()*3, h, true);
    }
  }
  // Marin/Sausalito (across Golden Gate, northwest) — sparse waterfront
  for(let gx = -180; gx <= -120; gx += 12) {
    for(let gz = -180; gz <= -130; gz += 12) {
      if(Math.random() > 0.6) continue; // sparse
      const h = 3 + Math.random()*5;
      fillBuilding(gx, gz, 4+Math.random()*3, 4+Math.random()*3, h, true);
    }
  }
  // Berkeley/Emeryville (north of Oakland, across bay)
  for(let gx = 80; gx <= 160; gx += 9) {
    for(let gz = -140; gz <= -120; gz += 9) {
      const h = 5 + Math.random()*8;
      fillBuilding(gx, gz, 4+Math.random()*3, 4+Math.random()*3, h, false);
    }
  }
  // Treasure Island (in the bay between SF and Oakland)
  const tiGround = new THREE.Mesh(
    new THREE.PlaneGeometry(20, 25),
    new THREE.MeshStandardMaterial({color:0x1a1a22, roughness:0.85, metalness:0.1})
  );
  tiGround.rotation.x = -Math.PI/2;
  tiGround.position.set(55, GROUND_Y + 0.25, -55);
  cityGroup.add(tiGround);
  for(let gx = 48; gx <= 62; gx += 6) {
    for(let gz = -65; gz <= -45; gz += 6) {
      const h = 3 + Math.random()*5;
      fillBuilding(gx, gz, 4, 4, h, true);
    }
  }

  // ═══════════════════════════════════
  // LANDMARK BUILDINGS (detailed)
  // ═══════════════════════════════════

  // 555 California — wider dark granite tower (west/FiDi)
  {
    const graniteMat = new THREE.MeshStandardMaterial({color:0x4a6080, roughness:0.3, metalness:0.4});
    const b = new THREE.Mesh(new THREE.BoxGeometry(5, 35, 4.5), graniteMat);
    b.position.set(-20, GROUND_Y+17.5, 2);
    cityGroup.add(b);
    const avl = new THREE.Mesh(new THREE.SphereGeometry(0.2, 4, 4), avLightMat);
    avl.position.set(-20, GROUND_Y+35.5, 2);
    cityGroup.add(avl);
  }

  // Embarcadero Center (4 white brutalist towers, NNW of Salesforce)
  for(let i = 0; i < 4; i++) {
    const ecMat = new THREE.MeshStandardMaterial({color:0x7a90a8, roughness:0.3, metalness:0.35});
    const ec = new THREE.Mesh(new THREE.BoxGeometry(3.5, 17+i*1.5, 3), ecMat);
    ec.position.set(-10 + i*4.5, GROUND_Y + (17+i*1.5)/2, -8);
    cityGroup.add(ec);
  }

  // 101 California — cylindrical glass tower
  const cal101 = new THREE.Mesh(
    new THREE.CylinderGeometry(2, 2, 18, 12),
    new THREE.MeshPhysicalMaterial({color:0x7a8a9a, roughness:0.1, metalness:0.5, transparent:true, opacity:0.85})
  );
  cal101.position.set(-14, GROUND_Y + 9, -3);
  cityGroup.add(cal101);

  // SF City Hall — Beaux-Arts with dome (WSW)
  {
    const chBase = new THREE.Mesh(
      new THREE.BoxGeometry(8, 5, 6),
      new THREE.MeshStandardMaterial({color:0x7a8a9a, roughness:0.4, metalness:0.3})
    );
    chBase.position.set(-55, GROUND_Y + 2.5, 15);
    cityGroup.add(chBase);
    const chDome = new THREE.Mesh(
      new THREE.SphereGeometry(2.5, 12, 8, 0, Math.PI*2, 0, Math.PI/2),
      new THREE.MeshStandardMaterial({color:0xc8b050, roughness:0.3, metalness:0.7})
    );
    chDome.position.set(-55, GROUND_Y + 5, 15);
    cityGroup.add(chDome);
    const chLantern = new THREE.Mesh(
      new THREE.CylinderGeometry(0.4, 0.5, 2, 8),
      new THREE.MeshStandardMaterial({color:0xd4b840, roughness:0.2, metalness:0.8})
    );
    chLantern.position.set(-55, GROUND_Y + 8, 15);
    cityGroup.add(chLantern);
  }

  // Transamerica Pyramid (distinctive pointed shape)
  {
    const pyrGroup = new THREE.Group();
    const pyrH = 38;
    const pyrBase = 4;
    const pyrGeo = new THREE.ConeGeometry(pyrBase/2, pyrH, 4);
    const pyrMat2 = new THREE.MeshPhysicalMaterial({
      color:0x8898a8, roughness:0.15, metalness:0.7,
      transparent:true, opacity:0.85,
    });
    const pyrMesh = new THREE.Mesh(pyrGeo, pyrMat2);
    pyrMesh.position.set(0, pyrH/2, 0);
    pyrMesh.rotation.y = Math.PI/4;
    pyrGroup.add(pyrMesh);
    const pyrLight = new THREE.Mesh(new THREE.SphereGeometry(0.2, 4, 4), avLightMat);
    pyrLight.position.set(0, pyrH + 0.3, 0);
    pyrGroup.add(pyrLight);
    for(let wy = 2; wy < pyrH*0.5; wy += 3) {
      const widthAtY = pyrBase * (1 - wy/pyrH) * 0.6;
      for(let side = 0; side < 4; side++) {
        if(Math.random() < 0.4) continue;
        const wn = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.5), winMat);
        const angle = side * Math.PI/2 + Math.PI/4;
        const dd = widthAtY/2 + 0.02;
        wn.position.set(Math.cos(angle)*dd, wy, Math.sin(angle)*dd);
        wn.rotation.y = angle + Math.PI;
        pyrGroup.add(wn);
      }
    }
    pyrGroup.position.set(-25, GROUND_Y, -5);
    cityGroup.add(pyrGroup);
  }

  // Golden Gate Bridge (far northwest) — International Orange, massive scale
  {
    const ggGroup = new THREE.Group();
    const ggRed = new THREE.MeshStandardMaterial({color: 0xc0362c, roughness: 0.35, metalness: 0.4, emissive: 0xc0362c, emissiveIntensity: 0.05});
    const ggRedDark = new THREE.MeshStandardMaterial({color: 0xa02e24, roughness: 0.4, metalness: 0.35});

    // Two main towers — Art Deco with dual columns, cross-bracing, sub-deck struts
    const towerX = [0, 55];
    const towerHeight = 48;
    const deckY = 10;
    for(let ti = 0; ti < 2; ti++) {
      const tx = towerX[ti];
      for(let leg = -1; leg <= 1; leg += 2) {
        const col = new THREE.Mesh(new THREE.BoxGeometry(2.0, towerHeight, 2.0), ggRed);
        col.position.set(tx + leg*1.5, towerHeight/2, 0);
        ggGroup.add(col);
      }
      for(const by of [38, 22]) {
        const brace = new THREE.Mesh(new THREE.BoxGeometry(5, 1.2, 1.8), ggRed);
        brace.position.set(tx, by, 0);
        ggGroup.add(brace);
      }
      const cap = new THREE.Mesh(new THREE.BoxGeometry(5.5, 2.5, 2.5), ggRed);
      cap.position.set(tx, towerHeight + 1.25, 0);
      ggGroup.add(cap);
      for(let leg = -1; leg <= 1; leg += 2) {
        const subCol = new THREE.Mesh(new THREE.BoxGeometry(2.5, deckY + 2, 2.5), ggRedDark);
        subCol.position.set(tx + leg*1.5, (deckY + 2)/2 - 2, 0);
        ggGroup.add(subCol);
      }
    }

    // Main deck — full span from south anchorage to north anchorage
    const deckMat = new THREE.MeshStandardMaterial({color: 0x555555, roughness: 0.8});
    const deckLen = 135;
    const deckCenterX = 27.5;
    const deck = new THREE.Mesh(new THREE.BoxGeometry(deckLen, 0.6, 6), deckMat);
    deck.position.set(deckCenterX, deckY, 0);
    ggGroup.add(deck);
    // Deck median divider (yellow)
    const median = new THREE.Mesh(new THREE.BoxGeometry(deckLen, 0.15, 0.2), new THREE.MeshStandardMaterial({color: 0xffcc00, roughness: 0.5}));
    median.position.set(deckCenterX, deckY + 0.4, 0);
    ggGroup.add(median);
    // Red railings on deck edges
    const rail1 = new THREE.Mesh(new THREE.BoxGeometry(deckLen, 1.2, 0.3), ggRed);
    rail1.position.set(deckCenterX, deckY + 1, 3);
    ggGroup.add(rail1);
    const rail2 = rail1.clone();
    rail2.position.z = -3;
    ggGroup.add(rail2);

    // Suspension cables — catenary: anchorage → tower → tower → anchorage
    const southAnchorX = -40;
    const northAnchorX = 95;
    const anchorY = deckY + 2;
    const towerTopY = towerHeight - 1;
    function ggCatenary(x1, y1, x2, y2, sag, segments, side) {
      let prevX, prevY;
      for(let s = 0; s <= segments; s++) {
        const frac = s / segments;
        const cx = x1 + (x2 - x1) * frac;
        const linearY = y1 + (y2 - y1) * frac;
        const sagOff = -sag * 4 * frac * (1 - frac);
        const cy = linearY + sagOff;
        if(s > 0) {
          const dx = cx - prevX, dy = cy - prevY;
          const sL = Math.sqrt(dx*dx + dy*dy);
          const cSeg = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, sL, 6), ggRed);
          cSeg.position.set((cx+prevX)/2, (cy+prevY)/2, side*2.5);
          cSeg.rotation.z = -Math.atan2(dx, dy);
          ggGroup.add(cSeg);
        }
        prevX = cx;
        prevY = cy;
        if(cx > southAnchorX + 8 && cx < northAnchorX - 8 && s % 2 === 0) {
          const suspH = cy - (deckY + 1.2);
          if(suspH > 1.5) {
            const susp = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, suspH, 4), ggRed);
            susp.position.set(cx, deckY + 1.2 + suspH/2, side*2.5);
            ggGroup.add(susp);
          }
        }
      }
    }
    for(let side = -1; side <= 1; side += 2) {
      ggCatenary(southAnchorX, anchorY, towerX[0], towerTopY, 8, 10, side);
      ggCatenary(towerX[0], towerTopY, towerX[1], towerTopY, 18, 20, side);
      ggCatenary(towerX[1], towerTopY, northAnchorX, anchorY, 8, 10, side);
    }

    // Approach ramps — descending road to land on both sides
    for(let r = 0; r < 8; r++) {
      const rampX = southAnchorX - r * 5;
      const rampY = deckY - r * 1.2;
      const rs1 = new THREE.Mesh(new THREE.BoxGeometry(6, 0.5, 6), deckMat);
      rs1.position.set(rampX, rampY, 0);
      ggGroup.add(rs1);
      if(rampY > 2) { const p1 = new THREE.Mesh(new THREE.BoxGeometry(1, rampY, 1), ggRedDark); p1.position.set(rampX, rampY/2, 0); ggGroup.add(p1); }
    }
    for(let r = 0; r < 8; r++) {
      const rampX = northAnchorX + r * 5;
      const rampY = deckY - r * 1.2;
      const rs2 = new THREE.Mesh(new THREE.BoxGeometry(6, 0.5, 6), deckMat);
      rs2.position.set(rampX, rampY, 0);
      ggGroup.add(rs2);
      if(rampY > 2) { const p2 = new THREE.Mesh(new THREE.BoxGeometry(1, rampY, 1), ggRedDark); p2.position.set(rampX, rampY/2, 0); ggGroup.add(p2); }
    }

    // Aviation warning lights — red beacons on tower tops
    const ggAvLM = new THREE.MeshBasicMaterial({color: 0xff2200});
    const avl1 = new THREE.Mesh(new THREE.SphereGeometry(0.5, 8, 8), ggAvLM);
    avl1.position.set(towerX[0], towerHeight + 3, 0);
    ggGroup.add(avl1);
    const avl2 = new THREE.Mesh(new THREE.SphereGeometry(0.5, 8, 8), ggAvLM);
    avl2.position.set(towerX[1], towerHeight + 3, 0);
    ggGroup.add(avl2);

    // Deck lights — subtle warm lights along roadway
    const ggDeckLM = new THREE.MeshBasicMaterial({color: 0xffe8a0});
    for(let lx = southAnchorX; lx <= northAnchorX; lx += 8) {
      for(let ls = -1; ls <= 1; ls += 2) {
        const po = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 2.5, 4), ggRedDark);
        po.position.set(lx, deckY + 1.6, ls * 2.8);
        ggGroup.add(po);
        const bu = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.2, 6), ggDeckLM);
        bu.position.set(lx, deckY + 3, ls * 2.8);
        ggGroup.add(bu);
      }
    }

    ggGroup.position.set(-120, GROUND_Y, -110);
    ggGroup.rotation.y = Math.PI * 0.3;
    cityGroup.add(ggGroup);
  }

  // GG Bridge approach road — connects south anchor through Presidio to city
  {
    const ggRoadMat = new THREE.MeshStandardMaterial({color: 0x4a4a4a, roughness: 0.7});
    const ggRoadSideMat = new THREE.MeshStandardMaterial({color: 0x5a5a5a, roughness: 0.8});
    // Bridge south anchor world coords ≈ (-85, GY, -75)
    // Road curves through Presidio to city grid edge at (-30,-18)
    const ggRoadPts = [
      [-88, -78], [-82, -70], [-75, -60], [-68, -50], [-60, -42], [-52, -34], [-44, -28], [-36, -22], [-28, -18]
    ];
    for(let i = 0; i < ggRoadPts.length - 1; i++) {
      const [x1,z1] = ggRoadPts[i];
      const [x2,z2] = ggRoadPts[i+1];
      const dx = x2-x1, dz = z2-z1;
      const len = Math.sqrt(dx*dx + dz*dz);
      const ang = Math.atan2(dx, dz);
      // Elevated road bed
      const road = new THREE.Mesh(new THREE.BoxGeometry(6, 0.5, len+3), ggRoadMat);
      road.position.set((x1+x2)/2, GROUND_Y + 1.0, (z1+z2)/2);
      road.rotation.y = ang;
      cityGroup.add(road);
      // Road side barriers
      for(let side = -1; side <= 1; side += 2) {
        const barrier = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.6, len+3), ggRoadSideMat);
        const offsetX = Math.cos(ang + Math.PI/2) * 3 * side;
        const offsetZ = Math.sin(ang + Math.PI/2) * 3 * side;
        barrier.position.set((x1+x2)/2 + offsetX, GROUND_Y + 1.3, (z1+z2)/2 + offsetZ);
        barrier.rotation.y = ang;
        cityGroup.add(barrier);
      }
    }
  }

  // Bay Bridge (connects SF waterfront to Oakland via Treasure Island/Yerba Buena)
  {
    const bbMat = new THREE.MeshStandardMaterial({color: 0x8899aa, roughness: 0.3, metalness: 0.5});
    const bbWhiteMat = new THREE.MeshStandardMaterial({color: 0xdddddd, roughness: 0.3, metalness: 0.5});

    // Bridge path: SF anchorage (25,-18) → TI/YBI (55,-55) → Oakland (120,-75)
    // Western span (SF to Yerba Buena Island) — classic suspension
    const westSpan = new THREE.Group();
    // Deck
    const wDeck = new THREE.Mesh(new THREE.BoxGeometry(4, 0.4, 55), bbMat);
    wDeck.position.set(0, 6, -27.5);
    westSpan.add(wDeck);
    // Two suspension towers
    for(let i = 0; i < 2; i++) {
      const t = new THREE.Mesh(new THREE.BoxGeometry(1.2, 28, 1.2), bbMat);
      t.position.set(0, 14, -12 - i*25);
      westSpan.add(t);
    }
    // Cables (catenary between towers)
    const cableMat = new THREE.MeshStandardMaterial({color: 0x667788, roughness: 0.3});
    for(let side = -1; side <= 1; side += 2) {
      let prevY, prevZ;
      for(let seg = 0; seg <= 10; seg++) {
        const frac = seg/10;
        const cz = -12 - frac*25;
        const sag = Math.pow(frac - 0.5, 2) * 4 * 12;
        const cy = 22 - sag;
        if(seg > 0) {
          const dz = cz - prevZ, dy = cy - prevY;
          const sL = Math.sqrt(dz*dz + dy*dy);
          const cSeg = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, sL, 6), cableMat);
          cSeg.position.set(side*1.5, (cy+prevY)/2, (cz+prevZ)/2);
          cSeg.rotation.x = -Math.atan2(dz, dy);
          westSpan.add(cSeg);
        }
        prevY = cy;
        prevZ = cz;
      }
    }
    westSpan.position.set(38, GROUND_Y, -18);
    westSpan.rotation.y = -Math.atan2(-55+18, 55-38); // aim toward TI
    cityGroup.add(westSpan);

    // Eastern span (Yerba Buena Island to Oakland) — new self-anchored suspension
    const eastSpan = new THREE.Group();
    // Deck
    const eDeck = new THREE.Mesh(new THREE.BoxGeometry(4, 0.4, 75), bbMat);
    eDeck.position.set(0, 6, -37.5);
    eastSpan.add(eDeck);
    // Single white tower (iconic new eastern span)
    const whiteT = new THREE.Mesh(new THREE.BoxGeometry(1.5, 35, 1.5), bbWhiteMat);
    whiteT.position.set(0, 17.5, -20);
    eastSpan.add(whiteT);
    // Asymmetric cables from white tower
    for(let side = -1; side <= 1; side += 2) {
      let prevY, prevZ;
      for(let seg = 0; seg <= 12; seg++) {
        const frac = seg/12;
        const cz = -frac*65;
        const sag = Math.pow(frac - 0.3, 2) * 3 * 10;
        const cy = 24 - sag;
        if(seg > 0) {
          const dz = cz - prevZ, dy = cy - prevY;
          const sL = Math.sqrt(dz*dz + dy*dy);
          const cSeg = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, sL, 6), bbWhiteMat);
          cSeg.position.set(side*1.5, (cy+prevY)/2, (cz+prevZ)/2);
          cSeg.rotation.x = -Math.atan2(dz, dy);
          eastSpan.add(cSeg);
        }
        prevY = cy;
        prevZ = cz;
      }
    }
    eastSpan.position.set(55, GROUND_Y, -55);
    eastSpan.rotation.y = -Math.atan2(-75+55, 120-55); // aim toward Oakland
    cityGroup.add(eastSpan);
  }

  // Bay Bridge approach — elevated freeway from SF to west span
  {
    const bbRoadMat = new THREE.MeshStandardMaterial({color: 0x4a4a4a, roughness: 0.7});
    // Elevated on-ramp from city (15, -8) ramping up to bridge deck height at (38, -18)
    const bbRoadPts = [
      [12, -6], [16, -8], [20, -10], [24, -12], [28, -14], [32, -16], [36, -18], [38, -18]
    ];
    for(let i = 0; i < bbRoadPts.length - 1; i++) {
      const [x1,z1] = bbRoadPts[i];
      const [x2,z2] = bbRoadPts[i+1];
      const frac = i / (bbRoadPts.length - 2);
      const y = GROUND_Y + 0.5 + frac * 5.5; // ramps from ground to deck level
      const dx = x2-x1, dz = z2-z1;
      const len = Math.sqrt(dx*dx + dz*dz);
      const ang = Math.atan2(dx, dz);
      // Road surface
      const road = new THREE.Mesh(new THREE.BoxGeometry(5, 0.4, len+2), bbRoadMat);
      road.position.set((x1+x2)/2, y, (z1+z2)/2);
      road.rotation.y = ang;
      cityGroup.add(road);
      // Support columns under elevated sections
      if(frac > 0.2) {
        const colH = y - GROUND_Y;
        const col = new THREE.Mesh(new THREE.BoxGeometry(0.6, colH, 0.6), bbRoadMat);
        col.position.set((x1+x2)/2, GROUND_Y + colH/2, (z1+z2)/2);
        cityGroup.add(col);
      }
    }
  }

  // ══════════════════════════════════════════════════════
  // PRESIDIO LAND MASS (connects GG Bridge south to SF)
  // ══════════════════════════════════════════════════════
  {
    const presidioMat = new THREE.MeshStandardMaterial({color: 0x5a7a48, roughness: 0.85});
    const presidioGround = new THREE.Mesh(
      new THREE.PlaneGeometry(90, 100),
      new THREE.MeshStandardMaterial({color: 0x6a8a58, roughness: 0.9})
    );
    presidioGround.rotation.x = -Math.PI/2;
    presidioGround.position.set(-50, GROUND_Y + 0.35, -55);
    cityGroup.add(presidioGround);

    // Presidio hills / terrain bumps
    const pHill1 = new THREE.Mesh(new THREE.ConeGeometry(15, 12, 32, 4), presidioMat);
    pHill1.position.set(-55, GROUND_Y + 6, -50);
    cityGroup.add(pHill1);
    const pHill2 = new THREE.Mesh(new THREE.ConeGeometry(12, 8, 32, 4), presidioMat);
    pHill2.position.set(-70, GROUND_Y + 4, -70);
    cityGroup.add(pHill2);
    const pHill3 = new THREE.Mesh(new THREE.ConeGeometry(10, 7, 32, 4), presidioMat);
    pHill3.position.set(-45, GROUND_Y + 3.5, -80);
    cityGroup.add(pHill3);

    // Trees on Presidio (green cones — instanced for performance)
    const treeGeo = new THREE.ConeGeometry(2, 5, 5, 1);
    const treeMat = new THREE.MeshStandardMaterial({color: 0x2a5a28, roughness: 0.85});
    const trunkGeo = new THREE.CylinderGeometry(0.3, 0.4, 2, 5);
    const trunkMat = new THREE.MeshStandardMaterial({color: 0x5a4030, roughness: 0.9});
    const treePositions = [
      [-50,-45], [-55,-55], [-65,-50], [-45,-60], [-60,-65],
      [-70,-75], [-50,-72], [-40,-55], [-75,-60], [-55,-80],
      [-48,-38], [-62,-42], [-38,-48], [-72,-55], [-58,-90],
      [-42,-70], [-68,-85], [-52,-62], [-46,-75], [-60,-78],
    ];
    treePositions.forEach(([tx, tz]) => {
      const tree = new THREE.Mesh(treeGeo, treeMat);
      tree.position.set(tx, GROUND_Y + 3.5, tz);
      cityGroup.add(tree);
      const trunk = new THREE.Mesh(trunkGeo, trunkMat);
      trunk.position.set(tx, GROUND_Y + 1, tz);
      cityGroup.add(trunk);
    });

    // Low Presidio buildings (barracks, officer housing)
    for(let gx = -70; gx <= -40; gx += 8) {
      for(let gz = -55; gz <= -35; gz += 10) {
        if(Math.random() > 0.5) continue;
        const h = 2 + Math.random() * 3;
        fillBuilding(gx, gz, 4, 3, h, true);
      }
    }

    // Fort Point (near GG bridge south anchor base)
    const fortPoint = new THREE.Mesh(
      new THREE.BoxGeometry(6, 3, 5),
      new THREE.MeshStandardMaterial({color: 0x8a6a50, roughness: 0.8})
    );
    fortPoint.position.set(-85, GROUND_Y + 1.5, -90);
    cityGroup.add(fortPoint);
    // Fort Point parapet
    const fortWall = new THREE.Mesh(
      new THREE.BoxGeometry(7, 1, 0.5),
      new THREE.MeshStandardMaterial({color: 0x7a5a40, roughness: 0.8})
    );
    fortWall.position.set(-85, GROUND_Y + 3.5, -87.5);
    cityGroup.add(fortWall);
  }

  // ══════════════════════════════════════════════════════
  // MARIN HEADLANDS GROUND (connects GG Bridge north side)
  // ══════════════════════════════════════════════════════
  {
    // Large ground plane under and beyond the GG bridge north anchor
    const marinGround = new THREE.Mesh(
      new THREE.PlaneGeometry(90, 90),
      new THREE.MeshStandardMaterial({color: 0x6a7a50, roughness: 0.9})
    );
    marinGround.rotation.x = -Math.PI/2;
    marinGround.position.set(-100, GROUND_Y + 0.3, -165);
    cityGroup.add(marinGround);

    // Additional hill connecting to bridge north anchor
    const marinConnect = new THREE.Mesh(
      new THREE.ConeGeometry(25, 18, 32, 4),
      new THREE.MeshStandardMaterial({color: 0x6a7048, roughness: 0.9})
    );
    marinConnect.position.set(-90, GROUND_Y + 9, -135);
    cityGroup.add(marinConnect);

    // Ridge between the two main Marin hills
    const marinRidge = new THREE.Mesh(
      new THREE.ConeGeometry(20, 14, 32, 4),
      new THREE.MeshStandardMaterial({color: 0x7a7048, roughness: 0.9})
    );
    marinRidge.position.set(-85, GROUND_Y + 7, -170);
    cityGroup.add(marinRidge);
  }

  // ══════════════════════════════════════════════════════
  // SHORELINE STRIPS (dark tan/gray waterfront edges)
  // ══════════════════════════════════════════════════════
  {
    const shoreMat = new THREE.MeshStandardMaterial({color: 0x8a8070, roughness: 0.9, metalness: 0.05});

    // Eastern SF shoreline: Ferry Building south to Oracle Park (x:18-30, z:-18 to 25)
    for(let sz = -18; sz <= 25; sz += 3) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(2, 0.2, 3.5), shoreMat);
      seg.position.set(32, GROUND_Y + 0.12, sz);
      cityGroup.add(seg);
    }
    // Northern SF shoreline: along the bay from Presidio to Ferry Building
    for(let sx = -80; sx <= 18; sx += 3) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.2, 2), shoreMat);
      seg.position.set(sx, GROUND_Y + 0.12, -18);
      cityGroup.add(seg);
    }
    // Curved shoreline around NE corner (North Beach to Embarcadero)
    for(let a = -0.3; a <= 0.5; a += 0.06) {
      const sx = 28 + Math.cos(a) * 8;
      const sz = -18 + Math.sin(a) * 8;
      const seg = new THREE.Mesh(new THREE.BoxGeometry(2, 0.2, 2), shoreMat);
      seg.position.set(sx, GROUND_Y + 0.12, sz);
      cityGroup.add(seg);
    }
    // Presidio / GG waterfront shoreline
    for(let sx = -90; sx <= -30; sx += 4) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(4.5, 0.2, 2), shoreMat);
      seg.position.set(sx, GROUND_Y + 0.12, -95);
      cityGroup.add(seg);
    }
  }

  // ══════════════════════════════════════════════════════
  // YERBA BUENA ISLAND HILL (between Bay Bridge spans)
  // ══════════════════════════════════════════════════════
  {
    const ybiMat = new THREE.MeshStandardMaterial({color: 0x4a6a42, roughness: 0.85});
    const ybiHill = new THREE.Mesh(new THREE.SphereGeometry(10, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), ybiMat);
    ybiHill.position.set(55, GROUND_Y, -55);
    ybiHill.scale.y = 0.55;
    cityGroup.add(ybiHill);
    // Secondary bump
    const ybiHill2 = new THREE.Mesh(new THREE.SphereGeometry(7, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), ybiMat);
    ybiHill2.position.set(50, GROUND_Y, -50);
    ybiHill2.scale.y = 0.5;
    cityGroup.add(ybiHill2);
  }

  // ══════════════════════════════════════════════════════
  // OAKLAND IMPROVEMENTS (wider ground, more downtown buildings)
  // ══════════════════════════════════════════════════════
  {
    // Extended Oakland ground connecting to East Bay hills
    const oakExtGround = new THREE.Mesh(
      new THREE.PlaneGeometry(160, 130),
      new THREE.MeshStandardMaterial({color: 0x7a7a70, roughness: 0.85})
    );
    oakExtGround.rotation.x = -Math.PI/2;
    oakExtGround.position.set(150, GROUND_Y + 0.18, -85);
    cityGroup.add(oakExtGround);

    // Oakland downtown core — denser tall buildings
    for(let gx = 115; gx <= 145; gx += 5) {
      for(let gz = -90; gz <= -60; gz += 5) {
        const dist = Math.abs(gx - 130) + Math.abs(gz + 75);
        const h = 12 + Math.random() * 18 + Math.max(0, 25 - dist * 0.5);
        fillBuilding(gx, gz, 3.5 + Math.random() * 2, 3.5 + Math.random() * 2, h, false);
      }
    }
  }

  // ── FLUSH INSTANCED BUILDINGS ──
  flushFillBuildings();

  // ── LOW-LYING BAY FOG (atmospheric realism — dynamic: thick at dawn/dusk, thin midday) ──
  // Radial gradient texture for soft edge falloff (no hard pancake edges)
  var fogCanvas = document.createElement('canvas');
  fogCanvas.width = 512; fogCanvas.height = 512;
  var fogCtx = fogCanvas.getContext('2d');
  var fogGrad = fogCtx.createRadialGradient(256, 256, 0, 256, 256, 256);
  fogGrad.addColorStop(0, 'rgba(255,255,255,0.6)');
  fogGrad.addColorStop(0.4, 'rgba(255,255,255,0.3)');
  fogGrad.addColorStop(0.7, 'rgba(255,255,255,0.08)');
  fogGrad.addColorStop(1.0, 'rgba(255,255,255,0.0)');
  fogCtx.fillStyle = fogGrad;
  fogCtx.fillRect(0, 0, 512, 512);
  var fogTexture = new THREE.CanvasTexture(fogCanvas);

  // Uses 'var' so bayFogMat is accessible from animate() for dynamic opacity
  var bayFogMat = new THREE.MeshBasicMaterial({
    color: 0x9aabbf, transparent: true, opacity: 0.05, side: THREE.DoubleSide,
    depthWrite: false, map: fogTexture, blending: THREE.NormalBlending,
  });
  var bayFogPlanes = [];
  // 3 widely-spaced layers at different heights for depth
  var fogLayerConfigs = [
    { y: GROUND_Y + 1.0, sx: 900, sz: 700, z: -90 },
    { y: GROUND_Y + 5.0, sx: 1100, sz: 800, z: -70 },
    { y: GROUND_Y + 10.0, sx: 800, sz: 600, z: -100 },
  ];
  for(let fh = 0; fh < fogLayerConfigs.length; fh++) {
    const cfg = fogLayerConfigs[fh];
    const fogPlane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), bayFogMat);
    fogPlane.rotation.x = -Math.PI/2;
    fogPlane.scale.set(cfg.sx, cfg.sz, 1);
    fogPlane.position.set(20, cfg.y, cfg.z);
    cityGroup.add(fogPlane);
    bayFogPlanes.push(fogPlane);
  }
  // Day/night city dimmer: collect every unique lit material in the city once.
  // The scene's ambient stays bright at night for the office interior, which
  // left the whole city (hills, buildings, bridges) day-bright at 10 PM.
  // var (not const) so it hoists to module scope for updateTimeOfDay.
  var cityLitMats = [];
  {
    const seen = new Set();
    cityGroup.traverse(o => {
      if (o.isMesh && o.material && o.material.isMeshStandardMaterial && o.material !== cityGroundMat) {
        if (!seen.has(o.material)) { seen.add(o.material); cityLitMats.push({m: o.material, base: o.material.color.clone()}); }
      }
    });
  }
  scene.add(cityGroup);
}

// ── HELPER FUNCTIONS ──
function createDesk(x, z, rot, scale=1.0) {
  const g = new THREE.Group();
  const sw = 1.2*scale, sd = 0.6*scale;
  // surface
  const top = new THREE.Mesh(new THREE.BoxGeometry(sw, 0.05, sd), deskMat);
  top.position.y = 0.75; top.castShadow = true; top.receiveShadow = true;
  g.add(top);
  // front panel
  const panel = new THREE.Mesh(new THREE.BoxGeometry(sw, 0.4, 0.02), deskPanelMat);
  panel.position.set(0, 0.52, sd/2 - 0.01); g.add(panel);
  // legs
  const legGeo = new THREE.CylinderGeometry(0.02, 0.02, 0.73, 6);
  [[-sw/2+0.05, -sd/2+0.05],[sw/2-0.05, -sd/2+0.05],[-sw/2+0.05, sd/2-0.05],[sw/2-0.05, sd/2-0.05]].forEach(([lx,lz])=>{
    const leg = new THREE.Mesh(legGeo, legMat);
    leg.position.set(lx, 0.365, lz); g.add(leg);
  });
  // keyboard
  const kb = new THREE.Mesh(new THREE.BoxGeometry(0.3*scale, 0.015, 0.1*scale), kbMat);
  kb.position.set(-0.1*scale, 0.785, 0.1*scale); g.add(kb);
  // mouse
  const mouse = new THREE.Mesh(new THREE.BoxGeometry(0.05*scale, 0.02, 0.08*scale), mouseMat);
  mouse.position.set(0.25*scale, 0.785, 0.1*scale); g.add(mouse);
  // mug
  const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.025, 0.06, 8), mugMat);
  mug.position.set(0.4*scale, 0.805, -0.15*scale); g.add(mug);

  // Contact shadow — dark plane under desk for ambient occlusion feel
  const shadowGeo = new THREE.PlaneGeometry(sw + 0.2, sd + 0.2);
  const shadowMat = new THREE.MeshBasicMaterial({ color:0x000000, transparent:true, opacity:0.18, depthWrite:false });
  const contactShadow = new THREE.Mesh(shadowGeo, shadowMat);
  contactShadow.rotation.x = -Math.PI/2;
  contactShadow.position.y = 0.003;
  g.add(contactShadow);

  g.position.set(x, 0, z);
  g.rotation.y = rot || 0;
  scene.add(g);
  return g;
}

function createChair(x, z, rot) {
  const g = new THREE.Group();
  // seat
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.06, 0.42), chairMat);
  seat.position.y = 0.48; g.add(seat);
  // back
  const back = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.5, 0.04), chairMat);
  back.position.set(0, 0.76, -0.19); g.add(back);
  // pole
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.45, 6), legMat);
  pole.position.set(0, 0.24, 0); g.add(pole);
  // base star + wheels
  for(let i=0;i<5;i++){
    const a = (i/5)*Math.PI*2;
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.015,0.015,0.2,4), legMat);
    arm.rotation.z = Math.PI/2;
    arm.position.set(Math.cos(a)*0.1, 0.03, Math.sin(a)*0.1);
    arm.rotation.y = -a;
    g.add(arm);
    const wheel = new THREE.Mesh(new THREE.SphereGeometry(0.025, 6, 6), new THREE.MeshStandardMaterial({color:0x222222}));
    wheel.position.set(Math.cos(a)*0.18, 0.025, Math.sin(a)*0.18);
    g.add(wheel);
  }
  g.position.set(x, 0, z);
  g.rotation.y = rot || 0;
  scene.add(g);
  return g;
}

function createMonitor(parent, lx, ly, lz, w=0.35, h=0.22, name='mon') {
  const g = new THREE.Group();
  // screen canvas
  const cnv = document.createElement('canvas');
  cnv.width = 512; cnv.height = 320;
  const tex = new THREE.CanvasTexture(cnv);
  tex.minFilter = THREE.LinearFilter;
  const screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({map:tex}));
  screenMesh.position.set(0, h/2+0.02, 0.01);
  g.add(screenMesh);
  // frame
  const frame = new THREE.Mesh(new THREE.BoxGeometry(w+0.02, h+0.02, 0.015), monFrameMat);
  frame.position.set(0, h/2+0.02, 0);
  g.add(frame);
  // stand
  const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.12, 6), legMat);
  stand.position.set(0, -0.04, 0); g.add(stand);
  const base = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.01, 0.06), legMat);
  base.position.set(0, -0.1, 0); g.add(base);

  g.position.set(lx, ly, lz);
  parent.add(g);
  monitorCanvases[name] = cnv;
  monitorTextures[name] = tex;
  return g;
}

// Shared lamp glow — one radial-gradient canvas texture, one SpriteMaterial, all 9 lamps
const _lampGlowTex = (function() {
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const ctx2 = c.getContext('2d');
  const grad = ctx2.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0,   'rgba(255,220,140,0.9)');
  grad.addColorStop(0.3, 'rgba(255,180,80,0.5)');
  grad.addColorStop(1,   'rgba(255,140,30,0)');
  ctx2.fillStyle = grad;
  ctx2.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();
const _lampGlowMat = new THREE.SpriteMaterial({
  map: _lampGlowTex,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  transparent: true,
});

function createLamp(parent, lx, lz) {
  const g = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.02, 8), lampBaseMat);
  g.add(base);
  const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.35, 4), lampBaseMat);
  arm.position.set(0, 0.18, -0.05);
  arm.rotation.z = 0.15;
  g.add(arm);
  const shade = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.08, 8, 1, true), lampShadeMat);
  shade.position.set(0.02, 0.36, -0.08);
  shade.rotation.z = Math.PI;
  g.add(shade);
  const light = new THREE.PointLight(0xffaa55, 0.3, 3);
  light.position.set(0.02, 0.33, -0.08);
  g.add(light);
  // Glow sprite at lamp head — shared texture/material, static, no animation
  const glow = new THREE.Sprite(_lampGlowMat);
  glow.scale.set(0.6, 0.6, 1);
  glow.position.set(0.02, 0.36, -0.08);
  g.add(glow);
  g.position.set(lx, 0.78, lz);
  parent.add(g);
  return light;
}

function createCharacter(color, hairColor, name) {
  const g = new THREE.Group();

  // ── Per-character style configs (Sims 4 style) ──
  const styles = {
    ensemble:  { shirt:0x4a3878, sleeve:'long', pants:0x1a1a2a, shoes:0x1a1010, skin:0xd4a882, hairStyle:'swept', collar:'vneck', gender:'m', eyeColor:0x4488aa, accessory:'scarf', lipColor:0xbb8877 },
    scanner:   { shirt:0x2a5535, sleeve:'short', pants:0x1a2840, shoes:0x2a2015, skin:0xc49470, hairStyle:'short', collar:'crew', gender:'m', eyeColor:0x556633, accessory:null, lipColor:0x996655 },
    risk:      { shirt:0x8a2828, sleeve:'long', pants:0x151518, shoes:0x1a1a1a, skin:0xd4a882, hairStyle:'crew', collar:'zip', gender:'m', eyeColor:0x443322, accessory:'glasses', lipColor:0xbb8877 },
    tape:      { shirt:0x2a6070, sleeve:'short', pants:0x3a3a3a, shoes:0x252525, skin:0x8d6e4c, hairStyle:'long', collar:'crew', gender:'f', eyeColor:0x332211, accessory:'earrings', lipColor:0xcc6677 },
    jonas:     { shirt:0x7a6828, sleeve:'long', pants:0xc8b898, shoes:0x4a3a2a, skin:0xd4a882, hairStyle:'parted', collar:'button', gender:'m', eyeColor:0x443322, accessory:'watch', lipColor:0xbb8877 },
    executor:  { shirt:0x2850a8, sleeve:'long', pants:0x252530, shoes:0x1a1a1a, skin:0xd4a882, hairStyle:'messy', collar:'crew', gender:'m', eyeColor:0x334466, accessory:'beanie', lipColor:0xbb8877 },
    strategy:  { shirt:0x7a4a88, sleeve:'short', pants:0x252535, shoes:0x2a2025, skin:0xbf9070, hairStyle:'bangs', collar:'vneck', gender:'f', eyeColor:0x445533, accessory:'bracelets', lipColor:0xcc7788 },
    ws_feed:   { shirt:0x4a7868, sleeve:'long', pants:0x555550, shoes:0x3a3025, skin:0xd4a882, hairStyle:'bun', collar:'crew', gender:'f', eyeColor:0x556644, accessory:'earrings', lipColor:0xcc8877 },
    pos_monitor:{ shirt:0x2a7855, sleeve:'long', pants:0x1a2a20, shoes:0x1a1a18, skin:0xc49470, hairStyle:'crew', collar:'crew', gender:'m', eyeColor:0x446633, accessory:null, lipColor:0x996655 },
  };
  const st = styles[name] || styles.ensemble;

  const shirtMat = new THREE.MeshStandardMaterial({color:st.shirt, roughness:0.55, metalness:0.02});
  const pantsMat = new THREE.MeshStandardMaterial({color:st.pants, roughness:0.65});
  const shoeMat = new THREE.MeshStandardMaterial({color:st.shoes, roughness:0.5, metalness:0.15});
  const skinCharMat = new THREE.MeshStandardMaterial({color:st.skin, roughness:0.6, metalness:0.02});
  const hairMat = new THREE.MeshStandardMaterial({color:hairColor, roughness:0.75});

  // ── TORSO — chunky Sims body (wider, rounder) ──
  const torsoGeo = new THREE.CylinderGeometry(0.14, 0.16, 0.32, 16);
  const torso = new THREE.Mesh(torsoGeo, shirtMat);
  torso.position.y = 0.64;
  torso.scale.set(st.gender==='f'?0.88:1.0, 1, 0.78);
  g.add(torso);

  // Chest area — rounder upper body
  const chestGeo = new THREE.SphereGeometry(0.15, 12, 10);
  const chest = new THREE.Mesh(chestGeo, shirtMat);
  chest.position.set(0, 0.72, 0.02);
  chest.scale.set(st.gender==='f'?0.85:0.95, 0.55, 0.65);
  g.add(chest);

  // Shoulders — big rounded caps (Sims have broad shoulders)
  const shoulderGeo = new THREE.SphereGeometry(0.06, 10, 8);
  const lShoulder = new THREE.Mesh(shoulderGeo, shirtMat);
  lShoulder.position.set(-0.18, 0.76, 0); lShoulder.scale.set(1.1, 0.8, 0.85);
  g.add(lShoulder);
  const rShoulder = new THREE.Mesh(shoulderGeo, shirtMat);
  rShoulder.position.set(0.18, 0.76, 0); rShoulder.scale.set(1.1, 0.8, 0.85);
  g.add(rShoulder);

  // ── COLLAR DETAIL ──
  if(st.collar === 'vneck') {
    const vMat = new THREE.MeshStandardMaterial({color:st.skin, roughness:0.6});
    const vGeo = new THREE.ConeGeometry(0.05, 0.07, 3);
    const vneck = new THREE.Mesh(vGeo, vMat);
    vneck.position.set(0, 0.78, 0.08); vneck.rotation.x = 0.15;
    g.add(vneck);
  } else if(st.collar === 'zip') {
    const zipMat = new THREE.MeshStandardMaterial({color:0x888888, roughness:0.3, metalness:0.7});
    const zip = new THREE.Mesh(new THREE.BoxGeometry(0.014, 0.14, 0.01), zipMat);
    zip.position.set(0, 0.70, 0.13); g.add(zip);
    const hoodMat = new THREE.MeshStandardMaterial({color:st.shirt, roughness:0.7});
    const hood = new THREE.Mesh(new THREE.SphereGeometry(0.11, 8, 6, 0, Math.PI*2, 0, Math.PI*0.5), hoodMat);
    hood.position.set(0, 0.86, -0.04); hood.scale.set(1.1, 0.65, 0.8);
    g.add(hood);
  } else if(st.collar === 'button') {
    for(let i = 0; i < 4; i++) {
      const btn = new THREE.Mesh(new THREE.SphereGeometry(0.01, 6, 6), new THREE.MeshStandardMaterial({color:0xddd8cc, roughness:0.4}));
      btn.position.set(0, 0.74 - i*0.055, 0.13);
      g.add(btn);
    }
    const collarMat = new THREE.MeshStandardMaterial({color:st.shirt, roughness:0.6});
    const lFlap = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.035, 0.015), collarMat);
    lFlap.position.set(-0.045, 0.81, 0.10); lFlap.rotation.z = 0.2; g.add(lFlap);
    const rFlap = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.035, 0.015), collarMat);
    rFlap.position.set(0.045, 0.81, 0.10); rFlap.rotation.z = -0.2; g.add(rFlap);
  } else {
    const neckSkin = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.07, 0.04, 10), skinCharMat);
    neckSkin.position.y = 0.82; g.add(neckSkin);
  }

  // ── NECK — thicker for Sims proportions ──
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.06, 10), skinCharMat);
  neck.position.y = 0.84; g.add(neck);

  // ── HEAD — BIG round Sims head (key to the look!) ──
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.14, 20, 16), skinCharMat);
  head.scale.set(0.95, 1.05, 0.92);
  head.position.y = 0.98;
  g.add(head);
  g.userData.head = head;

  // ── EYES — big expressive Sims 4 eyes with eyelids ──
  const eyeWhiteMat = new THREE.MeshStandardMaterial({color:0xf8f8ff, roughness:0.2, metalness:0.05});
  const irisMat = new THREE.MeshStandardMaterial({color:st.eyeColor, roughness:0.3});
  const pupilMat = new THREE.MeshStandardMaterial({color:0x080808, roughness:0.2});
  const eyelidMat = new THREE.MeshStandardMaterial({color:st.skin, roughness:0.6});
  const highlightMat = new THREE.MeshBasicMaterial({color:0xffffff});

  // Eye spacing and size
  const eyeY = 0.985, eyeZ = 0.115, eyeSpacing = 0.046;

  // Left eye
  const lEyeWhite = new THREE.Mesh(new THREE.SphereGeometry(0.032, 12, 10), eyeWhiteMat);
  lEyeWhite.position.set(-eyeSpacing, eyeY, eyeZ); lEyeWhite.scale.set(0.75, 0.9, 0.45);
  g.add(lEyeWhite);
  const lIris = new THREE.Mesh(new THREE.SphereGeometry(0.019, 10, 8), irisMat);
  lIris.position.set(-eyeSpacing, eyeY - 0.003, eyeZ + 0.018);
  g.add(lIris);
  const lPupil = new THREE.Mesh(new THREE.SphereGeometry(0.009, 8, 6), pupilMat);
  lPupil.position.set(-eyeSpacing, eyeY - 0.003, eyeZ + 0.028);
  g.add(lPupil);
  const lHighlight = new THREE.Mesh(new THREE.SphereGeometry(0.005, 4, 4), highlightMat);
  lHighlight.position.set(-eyeSpacing + 0.008, eyeY + 0.005, eyeZ + 0.032);
  g.add(lHighlight);
  // Upper eyelid
  const lLid = new THREE.Mesh(new THREE.SphereGeometry(0.034, 10, 6, 0, Math.PI*2, 0, Math.PI*0.35), eyelidMat);
  lLid.position.set(-eyeSpacing, eyeY + 0.008, eyeZ + 0.005); lLid.scale.set(0.78, 0.7, 0.48);
  g.add(lLid);
  // Lower eyelash line
  const lashMat = new THREE.MeshStandardMaterial({color:0x1a1a1a, roughness:0.8});
  if(st.gender === 'f') {
    const lLash = new THREE.Mesh(new THREE.TorusGeometry(0.022, 0.002, 4, 10, Math.PI), lashMat);
    lLash.position.set(-eyeSpacing, eyeY + 0.012, eyeZ + 0.014); lLash.rotation.x = 0.6; lLash.rotation.z = 0.05;
    g.add(lLash);
  }

  // Right eye
  const rEyeWhite = new THREE.Mesh(new THREE.SphereGeometry(0.032, 12, 10), eyeWhiteMat);
  rEyeWhite.position.set(eyeSpacing, eyeY, eyeZ); rEyeWhite.scale.set(0.75, 0.9, 0.45);
  g.add(rEyeWhite);
  const rIris = new THREE.Mesh(new THREE.SphereGeometry(0.019, 10, 8), irisMat);
  rIris.position.set(eyeSpacing, eyeY - 0.003, eyeZ + 0.018);
  g.add(rIris);
  const rPupil = new THREE.Mesh(new THREE.SphereGeometry(0.009, 8, 6), pupilMat);
  rPupil.position.set(eyeSpacing, eyeY - 0.003, eyeZ + 0.028);
  g.add(rPupil);
  const rHighlight = new THREE.Mesh(new THREE.SphereGeometry(0.005, 4, 4), highlightMat);
  rHighlight.position.set(eyeSpacing + 0.008, eyeY + 0.005, eyeZ + 0.032);
  g.add(rHighlight);
  const rLid = new THREE.Mesh(new THREE.SphereGeometry(0.034, 10, 6, 0, Math.PI*2, 0, Math.PI*0.35), eyelidMat);
  rLid.position.set(eyeSpacing, eyeY + 0.008, eyeZ + 0.005); rLid.scale.set(0.78, 0.7, 0.48);
  g.add(rLid);
  if(st.gender === 'f') {
    const rLash = new THREE.Mesh(new THREE.TorusGeometry(0.022, 0.002, 4, 10, Math.PI), lashMat);
    rLash.position.set(eyeSpacing, eyeY + 0.012, eyeZ + 0.014); rLash.rotation.x = 0.6; rLash.rotation.z = -0.05;
    g.add(rLash);
  }

  // Eyebrows — thicker, more expressive arches
  const browMat = new THREE.MeshStandardMaterial({color:hairColor, roughness:0.8});
  const lBrow = new THREE.Mesh(new THREE.CapsuleGeometry(0.005, 0.03, 4, 6), browMat);
  lBrow.position.set(-eyeSpacing, 1.025, eyeZ + 0.01); lBrow.rotation.z = 0.15; lBrow.rotation.x = -0.2;
  g.add(lBrow);
  const rBrow = new THREE.Mesh(new THREE.CapsuleGeometry(0.005, 0.03, 4, 6), browMat);
  rBrow.position.set(eyeSpacing, 1.025, eyeZ + 0.01); rBrow.rotation.z = -0.15; rBrow.rotation.x = -0.2;
  g.add(rBrow);

  // Nose — cute button nose (Sims style)
  const nose = new THREE.Mesh(new THREE.SphereGeometry(0.018, 8, 6), skinCharMat);
  nose.position.set(0, 0.96, 0.13); nose.scale.set(0.75, 0.65, 0.55);
  g.add(nose);
  // Nostrils
  const nostrilMat = new THREE.MeshStandardMaterial({color:0x000000, roughness:0.9, transparent:true, opacity:0.15});
  const lNostril = new THREE.Mesh(new THREE.SphereGeometry(0.004, 4, 4), nostrilMat);
  lNostril.position.set(-0.006, 0.955, 0.135); g.add(lNostril);
  const rNostril = new THREE.Mesh(new THREE.SphereGeometry(0.004, 4, 4), nostrilMat);
  rNostril.position.set(0.006, 0.955, 0.135); g.add(rNostril);

  // Lips — full, shaped (Sims 4 style)
  const lipMat = new THREE.MeshStandardMaterial({color:st.lipColor, roughness:0.4, metalness:0.05});
  // Upper lip — two bumps
  const upperLipL = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 6), lipMat);
  upperLipL.position.set(-0.008, 0.94, 0.125); upperLipL.scale.set(1.0, 0.45, 0.5); g.add(upperLipL);
  const upperLipR = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 6), lipMat);
  upperLipR.position.set(0.008, 0.94, 0.125); upperLipR.scale.set(1.0, 0.45, 0.5); g.add(upperLipR);
  // Lower lip — single fuller bump
  const lowerLip = new THREE.Mesh(new THREE.SphereGeometry(0.016, 8, 6), lipMat);
  lowerLip.position.set(0, 0.934, 0.123); lowerLip.scale.set(0.9, 0.4, 0.45); g.add(lowerLip);
  // Lip line (dark crease)
  const lipLine = new THREE.Mesh(new THREE.BoxGeometry(0.028, 0.002, 0.006), new THREE.MeshStandardMaterial({color:0x663344, roughness:0.8}));
  lipLine.position.set(0, 0.938, 0.128); g.add(lipLine);

  // Ears
  const earGeo = new THREE.SphereGeometry(0.024, 8, 6);
  const lEar = new THREE.Mesh(earGeo, skinCharMat);
  lEar.position.set(-0.13, 0.97, 0); lEar.scale.set(0.35, 0.7, 0.5); g.add(lEar);
  const rEar = new THREE.Mesh(earGeo, skinCharMat);
  rEar.position.set(0.13, 0.97, 0); rEar.scale.set(0.35, 0.7, 0.5); g.add(rEar);

  // Chin — soft rounded
  const chin = new THREE.Mesh(new THREE.SphereGeometry(0.042, 8, 6), skinCharMat);
  chin.position.set(0, 0.90, 0.08); chin.scale.set(0.8, 0.5, 0.5);

  // Cheeks — subtle blush spheres for roundness
  const cheekMat = new THREE.MeshStandardMaterial({color:st.skin, roughness:0.65});
  const lCheek = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 6), cheekMat);
  lCheek.position.set(-0.07, 0.955, 0.09); lCheek.scale.set(0.6, 0.5, 0.4); g.add(lCheek);
  const rCheek = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 6), cheekMat);
  rCheek.position.set(0.07, 0.955, 0.09); rCheek.scale.set(0.6, 0.5, 0.4); g.add(rCheek);
  g.add(chin);

  // ── ACCESSORIES — Sims 4 style variety ──
  if(st.accessory === 'glasses') {
    const frameMat = new THREE.MeshStandardMaterial({color:0x1a1a1a, roughness:0.3, metalness:0.5});
    const lensMat = new THREE.MeshStandardMaterial({color:0x88bbdd, roughness:0.1, metalness:0.1, transparent:true, opacity:0.3});
    // Left lens frame
    const lFrame = new THREE.Mesh(new THREE.TorusGeometry(0.028, 0.003, 6, 16), frameMat);
    lFrame.position.set(-eyeSpacing, eyeY, eyeZ + 0.02); lFrame.scale.set(0.8, 0.9, 0.3); g.add(lFrame);
    const lLens = new THREE.Mesh(new THREE.CircleGeometry(0.025, 12), lensMat);
    lLens.position.set(-eyeSpacing, eyeY, eyeZ + 0.022); lLens.scale.set(0.8, 0.9, 1); g.add(lLens);
    // Right lens frame
    const rFrame = new THREE.Mesh(new THREE.TorusGeometry(0.028, 0.003, 6, 16), frameMat);
    rFrame.position.set(eyeSpacing, eyeY, eyeZ + 0.02); rFrame.scale.set(0.8, 0.9, 0.3); g.add(rFrame);
    const rLens = new THREE.Mesh(new THREE.CircleGeometry(0.025, 12), lensMat);
    rLens.position.set(eyeSpacing, eyeY, eyeZ + 0.022); rLens.scale.set(0.8, 0.9, 1); g.add(rLens);
    // Bridge
    const bridge = new THREE.Mesh(new THREE.CylinderGeometry(0.002, 0.002, 0.03, 4), frameMat);
    bridge.position.set(0, eyeY + 0.005, eyeZ + 0.025); bridge.rotation.z = Math.PI/2; g.add(bridge);
    // Temple arms
    const lArm = new THREE.Mesh(new THREE.CylinderGeometry(0.002, 0.001, 0.1, 4), frameMat);
    lArm.position.set(-0.09, eyeY, eyeZ - 0.03); lArm.rotation.x = Math.PI/2; lArm.rotation.z = 0.15; g.add(lArm);
    const rArm2 = new THREE.Mesh(new THREE.CylinderGeometry(0.002, 0.001, 0.1, 4), frameMat);
    rArm2.position.set(0.09, eyeY, eyeZ - 0.03); rArm2.rotation.x = Math.PI/2; rArm2.rotation.z = -0.15; g.add(rArm2);
  }
  if(st.accessory === 'scarf') {
    const scarfMat = new THREE.MeshStandardMaterial({color:0xccccdd, roughness:0.7});
    const scarf = new THREE.Mesh(new THREE.TorusGeometry(0.08, 0.02, 6, 16), scarfMat);
    scarf.position.set(0, 0.82, 0.02); scarf.rotation.x = Math.PI/2; scarf.scale.set(1, 1, 1.5); g.add(scarf);
    // Hanging end
    const scarfEnd = new THREE.Mesh(new THREE.CapsuleGeometry(0.018, 0.1, 4, 8), scarfMat);
    scarfEnd.position.set(0.05, 0.72, 0.08); scarfEnd.rotation.z = -0.2; g.add(scarfEnd);
  }
  if(st.accessory === 'earrings') {
    const jewelMat = new THREE.MeshStandardMaterial({color:0xffcc44, roughness:0.2, metalness:0.8});
    const lEarring = new THREE.Mesh(new THREE.SphereGeometry(0.006, 6, 6), jewelMat);
    lEarring.position.set(-0.135, 0.955, 0); g.add(lEarring);
    const rEarring = new THREE.Mesh(new THREE.SphereGeometry(0.006, 6, 6), jewelMat);
    rEarring.position.set(0.135, 0.955, 0); g.add(rEarring);
  }
  if(st.accessory === 'watch') {
    const watchMat = new THREE.MeshStandardMaterial({color:0xccaa44, roughness:0.2, metalness:0.8});
    const watchBand = new THREE.Mesh(new THREE.TorusGeometry(0.022, 0.004, 6, 12), watchMat);
    // Attach to left wrist area
    watchBand.position.set(-0.20, 0.50, 0.12); watchBand.rotation.x = Math.PI/3; g.add(watchBand);
    const watchFace = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.004, 8), new THREE.MeshStandardMaterial({color:0x222222, metalness:0.5}));
    watchFace.position.set(-0.20, 0.50, 0.14); watchFace.rotation.x = Math.PI/2; g.add(watchFace);
  }
  if(st.accessory === 'beanie') {
    const beanieMat = new THREE.MeshStandardMaterial({color:0x2266cc, roughness:0.8});
    const beanie = new THREE.Mesh(new THREE.SphereGeometry(0.15, 14, 10, 0, Math.PI*2, 0, Math.PI*0.55), beanieMat);
    beanie.position.set(0, 1.03, -0.01); beanie.scale.set(1.02, 0.9, 1.0); g.add(beanie);
    // Rim
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.135, 0.012, 6, 16), beanieMat);
    rim.position.set(0, 1.0, 0); rim.rotation.x = Math.PI/2; rim.scale.set(1.0, 1.0, 0.5); g.add(rim);
  }
  if(st.accessory === 'bracelets') {
    const braceletColors = [0xff66aa, 0x44cc88, 0xffcc22];
    braceletColors.forEach((c, i) => {
      const bMat = new THREE.MeshStandardMaterial({color:c, roughness:0.3, metalness:0.4});
      const bracelet = new THREE.Mesh(new THREE.TorusGeometry(0.022, 0.004, 6, 12), bMat);
      bracelet.position.set(0.20, 0.48 + i*0.015, 0.12); bracelet.rotation.x = Math.PI/3; g.add(bracelet);
    });
  }

  // ── HAIR — style-specific (bigger for bigger head) ──
  if(st.hairStyle === 'swept') {
    const h1 = new THREE.Mesh(new THREE.SphereGeometry(0.148, 16, 12), hairMat);
    h1.scale.set(1.0, 0.55, 1.05); h1.position.set(0, 1.04, -0.01); g.add(h1);
    const h2 = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 8), hairMat);
    h2.scale.set(1.4, 0.4, 0.8); h2.position.set(0, 1.07, -0.04); g.add(h2);
  } else if(st.hairStyle === 'short') {
    const h = new THREE.Mesh(new THREE.SphereGeometry(0.145, 16, 12), hairMat);
    h.scale.set(0.98, 0.45, 0.98); h.position.set(0, 1.03, 0); g.add(h);
    const beard = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 6, 0, Math.PI*2, Math.PI*0.5), hairMat);
    beard.position.set(0, 0.91, 0.06); beard.scale.set(0.8, 0.5, 0.6); g.add(beard);
  } else if(st.hairStyle === 'crew') {
    const h = new THREE.Mesh(new THREE.SphereGeometry(0.146, 16, 12), hairMat);
    h.scale.set(1.0, 0.5, 1.0); h.position.set(0, 1.03, 0); g.add(h);
  } else if(st.hairStyle === 'long') {
    const top = new THREE.Mesh(new THREE.SphereGeometry(0.15, 16, 12), hairMat);
    top.scale.set(1.02, 0.6, 1.05); top.position.set(0, 1.04, 0); g.add(top);
    const lHair = new THREE.Mesh(new THREE.CapsuleGeometry(0.045, 0.2, 4, 8), hairMat);
    lHair.position.set(-0.10, 0.88, 0.01); g.add(lHair);
    const rHair = new THREE.Mesh(new THREE.CapsuleGeometry(0.045, 0.2, 4, 8), hairMat);
    rHair.position.set(0.10, 0.88, 0.01); g.add(rHair);
    const bangs = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.03, 0.07), hairMat);
    bangs.position.set(0, 1.06, 0.09); g.add(bangs);
  } else if(st.hairStyle === 'parted') {
    const h = new THREE.Mesh(new THREE.SphereGeometry(0.148, 16, 12), hairMat);
    h.scale.set(1.0, 0.55, 1.0); h.position.set(0.01, 1.03, 0); g.add(h);
    const part = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.012, 0.10), hairMat);
    part.position.set(-0.08, 1.07, 0.02); part.rotation.z = 0.3; g.add(part);
  } else if(st.hairStyle === 'messy') {
    const h = new THREE.Mesh(new THREE.SphereGeometry(0.15, 16, 12), hairMat);
    h.scale.set(1.05, 0.6, 1.0); h.position.set(0, 1.04, 0.01); g.add(h);
    for(let i = 0; i < 6; i++) {
      const tuft = new THREE.Mesh(new THREE.ConeGeometry(0.02, 0.05, 4), hairMat);
      const angle = (i / 6) * Math.PI * 1.5 - 0.3;
      tuft.position.set(Math.sin(angle)*0.09, 1.10, Math.cos(angle)*0.06);
      tuft.rotation.set(Math.cos(angle)*0.4, 0, Math.sin(angle)*0.4);
      g.add(tuft);
    }
  } else if(st.hairStyle === 'bangs') {
    const top = new THREE.Mesh(new THREE.SphereGeometry(0.15, 16, 12), hairMat);
    top.scale.set(1.0, 0.6, 1.05); top.position.set(0, 1.04, 0); g.add(top);
    const bangs = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.035, 0.06), hairMat);
    bangs.position.set(0, 1.06, 0.10); g.add(bangs);
    const back = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.16, 4, 8), hairMat);
    back.position.set(0, 0.92, -0.06); g.add(back);
  } else if(st.hairStyle === 'bun') {
    const top = new THREE.Mesh(new THREE.SphereGeometry(0.147, 16, 12), hairMat);
    top.scale.set(1.0, 0.55, 1.0); top.position.set(0, 1.04, 0); g.add(top);
    const bun = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 8), hairMat);
    bun.position.set(0, 1.10, -0.07); g.add(bun);
  }

  // ── ARMS — chunkier Sims arms ──
  const upperArmGeo = new THREE.CapsuleGeometry(0.035, 0.13, 4, 8);
  const forearmGeo = new THREE.CapsuleGeometry(0.028, 0.11, 4, 8);
  const handGeo = new THREE.SphereGeometry(0.028, 8, 6);
  const forearmMat = st.sleeve === 'long' ? shirtMat : skinCharMat;

  const leftArm = new THREE.Group();
  const lUpper = new THREE.Mesh(upperArmGeo, shirtMat);
  lUpper.position.y = -0.06; leftArm.add(lUpper);
  const lForearm = new THREE.Mesh(forearmGeo, forearmMat);
  lForearm.position.set(0, -0.17, 0.04); leftArm.add(lForearm);
  const lHand = new THREE.Mesh(handGeo, skinCharMat);
  lHand.position.set(0, -0.26, 0.06); lHand.scale.set(0.85, 1.0, 0.65); leftArm.add(lHand);
  leftArm.position.set(-0.20, 0.72, 0.05);
  leftArm.rotation.x = -0.8; leftArm.rotation.z = 0.25;
  g.add(leftArm);
  g.userData.leftArm = leftArm;

  const rightArm = new THREE.Group();
  const rUpper = new THREE.Mesh(upperArmGeo, shirtMat);
  rUpper.position.y = -0.06; rightArm.add(rUpper);
  const rForearm = new THREE.Mesh(forearmGeo, forearmMat);
  rForearm.position.set(0, -0.17, 0.04); rightArm.add(rForearm);
  const rHand = new THREE.Mesh(handGeo, skinCharMat);
  rHand.position.set(0, -0.26, 0.06); rHand.scale.set(0.85, 1.0, 0.65); rightArm.add(rHand);
  rightArm.position.set(0.20, 0.72, 0.05);
  rightArm.rotation.x = -0.8; rightArm.rotation.z = -0.25;
  g.add(rightArm);
  g.userData.rightArm = rightArm;

  // ── BELT ──
  const beltMat = new THREE.MeshStandardMaterial({color:0x1a1815, roughness:0.5, metalness:0.3});
  const belt = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.01, 6, 16), beltMat);
  belt.position.y = 0.48; belt.rotation.x = Math.PI/2;
  g.add(belt);
  const buckle = new THREE.Mesh(new THREE.BoxGeometry(0.025, 0.022, 0.012), new THREE.MeshStandardMaterial({color:0xccaa55, metalness:0.8, roughness:0.2}));
  buckle.position.set(0, 0.48, 0.15); g.add(buckle);

  // ── LEGS — thicker Sims legs ──
  const upperLegGeo = new THREE.CapsuleGeometry(0.045, 0.17, 4, 8);
  const lowerLegGeo = new THREE.CapsuleGeometry(0.038, 0.15, 4, 8);
  const shoeGeo = new THREE.CapsuleGeometry(0.032, 0.08, 4, 8);

  const leftUpperLeg = new THREE.Mesh(upperLegGeo, pantsMat);
  leftUpperLeg.position.set(-0.08, 0.38, 0.06); leftUpperLeg.rotation.x = -1.2;
  g.add(leftUpperLeg); g.userData.leftUpperLeg = leftUpperLeg;

  const leftLowerLeg = new THREE.Mesh(lowerLegGeo, pantsMat);
  leftLowerLeg.position.set(-0.08, 0.18, 0.18); leftLowerLeg.rotation.x = -0.1;
  g.add(leftLowerLeg); g.userData.leftLowerLeg = leftLowerLeg;

  const leftShoe = new THREE.Mesh(shoeGeo, shoeMat);
  leftShoe.position.set(-0.08, 0.02, 0.22); leftShoe.rotation.x = Math.PI/2;
  g.add(leftShoe); g.userData.leftShoe = leftShoe;

  const rightUpperLeg = new THREE.Mesh(upperLegGeo, pantsMat);
  rightUpperLeg.position.set(0.08, 0.38, 0.06); rightUpperLeg.rotation.x = -1.2;
  g.add(rightUpperLeg); g.userData.rightUpperLeg = rightUpperLeg;

  const rightLowerLeg = new THREE.Mesh(lowerLegGeo, pantsMat);
  rightLowerLeg.position.set(0.08, 0.18, 0.18); rightLowerLeg.rotation.x = -0.1;
  g.add(rightLowerLeg); g.userData.rightLowerLeg = rightLowerLeg;

  const rightShoe = new THREE.Mesh(shoeGeo, shoeMat);
  rightShoe.position.set(0.08, 0.02, 0.22); rightShoe.rotation.x = Math.PI/2;
  g.add(rightShoe); g.userData.rightShoe = rightShoe;

  scene.add(g);
  charGroups[name] = g;
  return g;
}

function createCSS2DLabel(charGroup, name, emoji) {
  // Emoji face above head
  const emojiDiv = document.createElement('div');
  emojiDiv.className = 'char-label';
  emojiDiv.innerHTML = `<div class="char-emoji">${emoji}</div>`;
  const emojiLabel = new CSS2DObject(emojiDiv);
  emojiLabel.position.set(0, 1.15, 0);
  charGroup.add(emojiLabel);

  // Plumbob
  const plumbobDiv = document.createElement('div');
  plumbobDiv.className = 'char-label';
  plumbobDiv.innerHTML = `<div class="plumbob" style="background:#4ecb71;color:#4ecb71;margin:0 auto;"></div>`;
  const plumbobLabel = new CSS2DObject(plumbobDiv);
  plumbobLabel.position.set(0, 1.35, 0);
  charGroup.add(plumbobLabel);
  plumbobs[name] = plumbobDiv.querySelector('.plumbob');

  // Name tag below
  const nameDiv = document.createElement('div');
  nameDiv.className = 'char-label';
  nameDiv.innerHTML = `<div class="char-name">${name.charAt(0).toUpperCase()+name.slice(1)}</div>`;
  const nameLabel = new CSS2DObject(nameDiv);
  nameLabel.position.set(0, 0.25, 0);
  charGroup.add(nameLabel);

  // Speech bubble — Claude's goes HIGH and LEFT, agents go RIGHT
  const bubbleDiv = document.createElement('div');
  bubbleDiv.className = 'char-label';
  bubbleDiv.innerHTML = `<div class="speech-bubble" id="bubble-${name}" style="${name==='ensemble'?'background:rgba(55,30,80,0.92);border-color:rgba(150,100,220,0.5);':''}"></div>`;
  const bubbleLabel = new CSS2DObject(bubbleDiv);
  if(name === 'ensemble') {
    bubbleLabel.position.set(-0.4, 2.1, 0);
  } else {
    bubbleLabel.position.set(0.4, 1.55, 0);
  }
  charGroup.add(bubbleLabel);
  speechBubbles[name] = bubbleDiv.querySelector('.speech-bubble');

}

// ── DESK POSITIONS ──
// Layout:  [Scanner(-2.2,z-1.5)]  [Risk(2.2,z-1.5)]
//              [Claude(0, z0.5) - bigger, forward]
//          [Tape(-2.2, z2.5)]    [Jonas(2.2, z2.5)]

const deskPositions = {
  scanner:     { x:-2.2, z:-1.5, rot:0 },
  risk:        { x:2.2, z:-1.5, rot:0 },
  ensemble:    { x:0, z:0.5, rot:0 },
  tape:        { x:-2.2, z:2.5, rot:0 },
  jonas:       { x:2.2, z:2.5, rot:0 },
  executor:    { x:-3.6, z:0.5, rot:0 },   // left wing — order executor
  strategy:    { x:3.6, z:0.5, rot:0 },    // right wing — strategy engine
  ws_feed:     { x:3.0, z:2.8, rot:0 },    // back-right — websocket feed (was outside penthouse radius at 4.5,4.2)
  pos_monitor: { x:0, z:3.8, rot:0 },      // back center — position monitor
};

const deskLights = {};

// Create desks, chairs, monitors, lamps, characters
Object.entries(deskPositions).forEach(([name, pos]) => {
  const sc = name === 'ensemble' ? 1.2 : 1.0;
  const desk = createDesk(pos.x, pos.z, pos.rot, sc);

  // Chair behind desk
  createChair(pos.x, pos.z + 0.55*sc, 0);

  // Monitors on desk
  const monW = 0.44 * sc, monH = 0.28 * sc;
  createMonitor(desk, -0.25*sc, 0.78, -0.2*sc, monW, monH, name+'_mon1');
  createMonitor(desk, 0.22*sc, 0.78, -0.2*sc, monW, monH, name+'_mon2');
  if(name === 'ensemble' || name === 'jonas'){
    createMonitor(desk, 0.6*sc, 0.78, -0.15*sc, monW*0.8, monH*0.8, name+'_mon3');
  }

  // Lamp
  deskLights[name] = createLamp(desk, -0.45*sc, -0.15*sc);

  // Character
  const charColors = {
    ensemble:    { body:0x4a3878, hair:0xc8c8d5 },  // muted purple blazer
    scanner:     { body:0x2a5535, hair:0x1a1a1a },  // dark forest green
    risk:        { body:0x8a2828, hair:0x3a2515 },  // burgundy
    tape:        { body:0x2a6070, hair:0x1a1520 },  // steel teal
    jonas:       { body:0x7a6828, hair:0x3a2a15 },  // muted gold/olive
    executor:    { body:0x2850a8, hair:0x2a1a10 },  // electric blue — order executor
    strategy:    { body:0x7a4a88, hair:0x3a2820 },  // soft violet — strategy engine
    ws_feed:     { body:0x4a7868, hair:0xc8b888 },  // sage green — websocket feed
    pos_monitor: { body:0x2a7855, hair:0x1a2a20 },  // forest green — position monitor
  };
  const cc = charColors[name];
  const ch = createCharacter(cc.body, cc.hair, name);
  ch.position.set(pos.x, 0, pos.z + 0.5*sc);
  ch.rotation.y = Math.PI; // face desk

  const emojis = { scanner:'😊', risk:'😤', ensemble:'😎', tape:'😌', jonas:'', executor:'📈', strategy:'📊', ws_feed:'🧘', pos_monitor:'📡' };
  const emoji = name === 'jonas' ? '<img src="/jonas_avatar.jpg" style="width:28px;height:28px;border-radius:50%;border:2px solid #b8922a;" onerror="this.outerHTML=\'🧑\'">' : emojis[name];
  createCSS2DLabel(ch, name, emoji);
});

// ── DESK LED STRIPS ──
var deskLEDs = {};
Object.entries(deskPositions).forEach(function([name, pos]) {
  var ledGeom = new THREE.BoxGeometry(0.7, 0.01, 0.02);
  var ledMat = new THREE.MeshStandardMaterial({
    color: 0x00ff88,
    emissive: 0x00ff88,
    emissiveIntensity: 0.5,
  });
  var led = new THREE.Mesh(ledGeom, ledMat);
  led.position.set(pos.x, 0.76, pos.z - 0.2);
  scene.add(led);
  deskLEDs[name] = led;
});

function updateAgentLED(name, status) {
  var led = deskLEDs[name];
  if (!led) return;
  var colors = {
    active: 0x00ff88,
    waiting: 0xffaa00,
    alert: 0xff4444,
    scanning: 0x4488ff,
    idle: 0x333333,
  };
  var color = colors[status] || colors.idle;
  led.material.color.setHex(color);
  led.material.emissive.setHex(color);
}

// ── BREAK ROOM (back-left corner) ──
{
  const BRX = -3.8, BRZ = -3.0;

  // Glass partition walls (divider)
  const glassPartMat = new THREE.MeshPhysicalMaterial({color:0x9ad4b0, transparent:true, opacity:0.14, roughness:0.02, metalness:0.1, clearcoat:1.0, clearcoatRoughness:0.02, reflectivity:0.9, side:THREE.DoubleSide}); // slight green tint like real glass
  const partFrameMat = new THREE.MeshStandardMaterial({color:0x556677, metalness:0.7, roughness:0.3});
  // Vertical glass wall
  const partV = new THREE.Mesh(new THREE.BoxGeometry(0.04, 1.6, 2.2), glassPartMat);
  partV.position.set(BRX+1.3, 0.8, BRZ); scene.add(partV);
  // Metal frame edges
  const partVframeT = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, 2.2), partFrameMat);
  partVframeT.position.set(BRX+1.3, 1.6, BRZ); scene.add(partVframeT);
  const partVframeB = partVframeT.clone(); partVframeB.position.y = 0.0; scene.add(partVframeB);
  // Horizontal glass wall
  const partH = new THREE.Mesh(new THREE.BoxGeometry(2.6, 1.6, 0.04), glassPartMat);
  partH.position.set(BRX, 0.8, BRZ+1.1); scene.add(partH);
  const partHframeT = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.03, 0.05), partFrameMat);
  partHframeT.position.set(BRX, 1.6, BRZ+1.1); scene.add(partHframeT);
  const partHframeB = partHframeT.clone(); partHframeB.position.y = 0.0; scene.add(partHframeB);

  // "BREAK ROOM" sign on partition
  const signCanvas = document.createElement('canvas');
  signCanvas.width = 128; signCanvas.height = 32;
  const signCtx = signCanvas.getContext('2d');
  signCtx.fillStyle = '#1a2744';
  signCtx.fillRect(0,0,128,32);
  signCtx.fillStyle = '#ffdd66';
  signCtx.font = 'bold 16px sans-serif';
  signCtx.textAlign = 'center';
  signCtx.fillText('BREAK ROOM', 64, 22);
  const signTex = new THREE.CanvasTexture(signCanvas);
  const signMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.15), new THREE.MeshBasicMaterial({map:signTex}));
  signMesh.position.set(BRX+1.3+0.035, 1.4, BRZ);
  signMesh.rotation.y = Math.PI/2;
  scene.add(signMesh);

  // Coffee machine (counter + machine)
  const counterMat = new THREE.MeshStandardMaterial({color:0x555555, roughness:0.5, metalness:0.3});
  const counter = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.85, 0.45), counterMat);
  counter.position.set(BRX-0.6, 0.425, BRZ-0.6);
  counter.receiveShadow = true; counter.castShadow = true;
  scene.add(counter);

  // Coffee machine body
  const cmMat = new THREE.MeshStandardMaterial({color:0x222222, roughness:0.4, metalness:0.5});
  const cmBody = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.35, 0.2), cmMat);
  cmBody.position.set(BRX-0.6, 1.025, BRZ-0.65);
  cmBody.castShadow = true;
  scene.add(cmBody);
  // Red indicator light
  const cmLight = new THREE.Mesh(new THREE.SphereGeometry(0.015, 8, 8), new THREE.MeshBasicMaterial({color:0xff2222}));
  cmLight.position.set(BRX-0.48, 1.1, BRZ-0.54);
  scene.add(cmLight);
  // Coffee mug on counter
  const brkMug = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.025, 0.06, 8), mugMat);
  brkMug.position.set(BRX-0.35, 0.88, BRZ-0.55);
  scene.add(brkMug);
  // Coffee liquid
  const coffeeMat = new THREE.MeshStandardMaterial({color:0x3a2010, roughness:0.3});
  const coffeeLiq = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.005, 8), coffeeMat);
  coffeeLiq.position.set(BRX-0.35, 0.91, BRZ-0.55);
  scene.add(coffeeLiq);

  // Snack table (small round table)
  const tableLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.65, 6), legMat);
  tableLeg.position.set(BRX, 0.325, BRZ); scene.add(tableLeg);
  const tableTop = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.03, 16), new THREE.MeshStandardMaterial({color:0x8B6914, roughness:0.6}));
  tableTop.position.set(BRX, 0.66, BRZ); tableTop.receiveShadow = true; scene.add(tableTop);

  // Snacks on table — donut box
  const boxMat = new THREE.MeshStandardMaterial({color:0xff8899, roughness:0.7});
  const donutBox = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.04, 0.15), boxMat);
  donutBox.position.set(BRX+0.05, 0.7, BRZ-0.05); scene.add(donutBox);
  // Donuts (little tori)
  const donutMat = new THREE.MeshStandardMaterial({color:0xdda050, roughness:0.6});
  for(let i=0;i<3;i++){
    const donut = new THREE.Mesh(new THREE.TorusGeometry(0.02, 0.008, 6, 8), donutMat);
    donut.position.set(BRX+0.05+i*0.04-0.04, 0.73, BRZ-0.05);
    donut.rotation.x = Math.PI/2;
    scene.add(donut);
    // Frosting
    const frostMat = new THREE.MeshStandardMaterial({color:[0xff66aa,0x66ccff,0xffdd44][i], roughness:0.5});
    const frost = new THREE.Mesh(new THREE.TorusGeometry(0.02, 0.005, 6, 8), frostMat);
    frost.position.copy(donut.position); frost.position.y += 0.005;
    frost.rotation.x = Math.PI/2;
    scene.add(frost);
  }

  // Apple and banana
  const appleMat = new THREE.MeshStandardMaterial({color:0xcc2222, roughness:0.5});
  const apple = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), appleMat);
  apple.position.set(BRX-0.1, 0.7, BRZ+0.08); scene.add(apple);
  const bananaMat = new THREE.MeshStandardMaterial({color:0xffdd33, roughness:0.5});
  const banana = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.01, 0.1, 6), bananaMat);
  banana.position.set(BRX+0.12, 0.7, BRZ+0.06); banana.rotation.z = 0.3; scene.add(banana);

  // Two lounge chairs
  const loungeColor = new THREE.MeshStandardMaterial({color:0x3a5570, roughness:0.75});
  for(let i=0;i<2;i++){
    const cx = BRX + (i===0 ? -0.35 : 0.35);
    const cz = BRZ + 0.35;
    const lSeat = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.04, 0.3), loungeColor);
    lSeat.position.set(cx, 0.35, cz); scene.add(lSeat);
    const lBack = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.3, 0.04), loungeColor);
    lBack.position.set(cx, 0.52, cz-0.13); scene.add(lBack);
    // legs
    for(let lx=-0.14;lx<=0.14;lx+=0.28){
      for(let lz=-0.1;lz<=0.1;lz+=0.2){
        const cLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.33, 4), legMat);
        cLeg.position.set(cx+lx, 0.165, cz+lz); scene.add(cLeg);
      }
    }
  }

  // Warm overhead light for break room
  const brkLight = new THREE.PointLight(0xffaa55, 0.5, 4);
  brkLight.position.set(BRX, 2.5, BRZ);
  scene.add(brkLight);

  // Small rug under table
  const rugMat = new THREE.MeshStandardMaterial({color:0x664422, roughness:0.95});
  const rug = new THREE.Mesh(new THREE.CircleGeometry(0.55, 16), rugMat);
  rug.rotation.x = -Math.PI/2;
  rug.position.set(BRX, 0.005, BRZ);
  scene.add(rug);
}

// ── THERAPY CORNER (front-right, quiet nook) ──
{
  const THX = THERAPY_X, THZ = THERAPY_Z;

  // Soft rug
  const thRugMat = new THREE.MeshStandardMaterial({color:0x6a7a68, roughness:0.95});
  const thRug = new THREE.Mesh(new THREE.CircleGeometry(1.0, 24), thRugMat);
  thRug.rotation.x = -Math.PI/2;
  thRug.position.set(THX, 0.005, THZ);
  scene.add(thRug);

  // Therapy couch (long, low, comfortable)
  const couchMat = new THREE.MeshStandardMaterial({color:0x5a6a58, roughness:0.8});
  const couchSeat = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.15, 0.5), couchMat);
  couchSeat.position.set(THX - 0.3, 0.25, THZ - 0.5);
  scene.add(couchSeat);
  const couchBack = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.35, 0.08), couchMat);
  couchBack.position.set(THX - 0.3, 0.45, THZ - 0.73);
  scene.add(couchBack);
  // Armrests
  const couchArm1 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.2, 0.5), couchMat);
  couchArm1.position.set(THX - 0.9, 0.35, THZ - 0.5);
  scene.add(couchArm1);
  const couchArm2 = couchArm1.clone();
  couchArm2.position.x = THX + 0.3;
  scene.add(couchArm2);
  // Cushion
  const cushMat = new THREE.MeshStandardMaterial({color:0x8a9a78, roughness:0.85});
  const cushion = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.06, 0.2), cushMat);
  cushion.position.set(THX - 0.5, 0.35, THZ - 0.45);
  cushion.rotation.y = 0.2;
  scene.add(cushion);

  // Small side table with tissue box
  const thTableMat = new THREE.MeshStandardMaterial({color:0x8B6914, roughness:0.6});
  const thTable = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.02, 12), thTableMat);
  thTable.position.set(THX + 0.6, 0.5, THZ - 0.3);
  scene.add(thTable);
  const thTableLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.48, 6), legMat);
  thTableLeg.position.set(THX + 0.6, 0.25, THZ - 0.3);
  scene.add(thTableLeg);
  // Tissue box
  const tissueMat = new THREE.MeshStandardMaterial({color:0xddddee, roughness:0.7});
  const tissueBox = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.05, 0.06), tissueMat);
  tissueBox.position.set(THX + 0.6, 0.54, THZ - 0.3);
  scene.add(tissueBox);

  // Potted plant (calming)
  const potMat = new THREE.MeshStandardMaterial({color:0x8a6a4a, roughness:0.8});
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.06, 0.12, 8), potMat);
  pot.position.set(THX + 0.8, 0.06, THZ + 0.3);
  scene.add(pot);
  const plantLeaf = new THREE.MeshStandardMaterial({color:0x3a6a35, roughness:0.7});
  const leaf1 = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 6), plantLeaf);
  leaf1.position.set(THX + 0.8, 0.22, THZ + 0.3);
  leaf1.scale.set(1, 1.2, 1);
  scene.add(leaf1);

  // Warm therapy light
  const thLight = new THREE.PointLight(0xffe8c0, 0.4, 4);
  thLight.position.set(THX, 2.5, THZ);
  scene.add(thLight);

  // "THERAPY" sign
  const thSignCanvas = document.createElement('canvas');
  thSignCanvas.width = 128; thSignCanvas.height = 32;
  const thSignCtx = thSignCanvas.getContext('2d');
  thSignCtx.fillStyle = '#2a3a2a';
  thSignCtx.fillRect(0,0,128,32);
  thSignCtx.fillStyle = '#a8c8a0';
  thSignCtx.font = 'bold 14px sans-serif';
  thSignCtx.textAlign = 'center';
  thSignCtx.fillText('WELLNESS', 64, 22);
  const thSignTex = new THREE.CanvasTexture(thSignCanvas);
  const thSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.12), new THREE.MeshBasicMaterial({map:thSignTex}));
  thSignMesh.position.set(THX + 0.3, 1.4, THZ - 0.8);
  scene.add(thSignMesh);
}

// ── CONFERENCE ROOM (back-right corner) ──
{
  // Glass partition walls
  const confGlassMat = new THREE.MeshPhysicalMaterial({color:0x88bbdd, transparent:true, opacity:0.18, roughness:0.05, metalness:0.1, side:THREE.DoubleSide});
  const confFrameMat2 = new THREE.MeshStandardMaterial({color:0x556677, metalness:0.7, roughness:0.3});
  // Left glass wall (wider for 7-person room)
  const confPartV = new THREE.Mesh(new THREE.BoxGeometry(0.04, 1.6, 4.0), confGlassMat);
  confPartV.position.set(CONF_X-2.2, 0.8, CONF_Z); scene.add(confPartV);
  const cfVframeT = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, 4.0), confFrameMat2);
  cfVframeT.position.set(CONF_X-2.2, 1.6, CONF_Z); scene.add(cfVframeT);
  const cfVframeB = cfVframeT.clone(); cfVframeB.position.y = 0.0; scene.add(cfVframeB);
  // Front glass wall (wider)
  const confPartH = new THREE.Mesh(new THREE.BoxGeometry(4.4, 1.6, 0.04), confGlassMat);
  confPartH.position.set(CONF_X, 0.8, CONF_Z+2.0); scene.add(confPartH);
  const cfHframeT = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.03, 0.05), confFrameMat2);
  cfHframeT.position.set(CONF_X, 1.6, CONF_Z+2.0); scene.add(cfHframeT);
  const cfHframeB = cfHframeT.clone(); cfHframeB.position.y = 0.0; scene.add(cfHframeB);

  // "CONFERENCE ROOM" sign on left partition
  const confSignCanvas = document.createElement('canvas');
  confSignCanvas.width = 192; confSignCanvas.height = 32;
  const confSignCtx = confSignCanvas.getContext('2d');
  confSignCtx.fillStyle = '#1a2744';
  confSignCtx.fillRect(0,0,192,32);
  confSignCtx.fillStyle = '#66ddff';
  confSignCtx.font = 'bold 14px sans-serif';
  confSignCtx.textAlign = 'center';
  confSignCtx.fillText('CONFERENCE ROOM', 96, 22);
  const confSignTex = new THREE.CanvasTexture(confSignCanvas);
  const confSignMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 0.15), new THREE.MeshBasicMaterial({map:confSignTex}));
  confSignMesh.position.set(CONF_X-1.8-0.035, 1.4, CONF_Z);
  confSignMesh.rotation.y = -Math.PI/2;
  scene.add(confSignMesh);

  // Rectangular conference table — expanded for 7-person team
  const confTableMat = new THREE.MeshStandardMaterial({color:0x6B4226, roughness:0.55});
  const confTableTop = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.04, 1.2), confTableMat);
  confTableTop.position.set(CONF_X, 0.66, CONF_Z); confTableTop.receiveShadow = true; scene.add(confTableTop);
  // Table legs
  const confLegMat = new THREE.MeshStandardMaterial({color:0x444444, roughness:0.5, metalness:0.3});
  for(let lx of [-1.1, 1.1]) {
    for(let lz of [-0.5, 0.5]) {
      const tLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.64, 6), confLegMat);
      tLeg.position.set(CONF_X+lx, 0.32, CONF_Z+lz); scene.add(tLeg);
    }
  }

  // 8 chairs around the table (3 each side + 1 each end)
  const confChairMat = new THREE.MeshStandardMaterial({color:0x3a5570, roughness:0.75});
  const chairPositions = [
    {x: CONF_X-0.7, z: CONF_Z+0.8, rotY: Math.PI},    // front-left
    {x: CONF_X,     z: CONF_Z+0.8, rotY: Math.PI},     // front-center
    {x: CONF_X+0.7, z: CONF_Z+0.8, rotY: Math.PI},    // front-right
    {x: CONF_X-0.7, z: CONF_Z-0.8, rotY: 0},           // back-left
    {x: CONF_X,     z: CONF_Z-0.8, rotY: 0},            // back-center
    {x: CONF_X+0.7, z: CONF_Z-0.8, rotY: 0},           // back-right
    {x: CONF_X-1.3, z: CONF_Z, rotY: Math.PI/2},       // left end
    {x: CONF_X+1.3, z: CONF_Z, rotY: -Math.PI/2},      // right end
  ];
  chairPositions.forEach(cp => {
    const cSeat = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.04, 0.28), confChairMat);
    cSeat.position.set(cp.x, 0.38, cp.z); scene.add(cSeat);
    const cBack = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.28, 0.04), confChairMat);
    const backZ = cp.rotY === Math.PI ? cp.z+0.12 : cp.z-0.12;
    cBack.position.set(cp.x, 0.54, backZ); scene.add(cBack);
    // Chair legs
    for(let clx of [-0.12, 0.12]) {
      for(let clz of [-0.1, 0.1]) {
        const chLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.36, 4), confLegMat);
        chLeg.position.set(cp.x+clx, 0.18, cp.z+clz); scene.add(chLeg);
      }
    }
  });

  // Large wall-mounted TV/monitor — LIVE dashboard (conference room)
  {
    const tvCnv = document.createElement('canvas');
    tvCnv.width = 512; tvCnv.height = 320;
    const tvTex = new THREE.CanvasTexture(tvCnv);
    tvTex.minFilter = THREE.LinearFilter;
    monitorCanvases['conftv'] = tvCnv;
    monitorTextures['conftv'] = tvTex;
    // TV bezel
    const tvBezel = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.55, 0.03), new THREE.MeshStandardMaterial({color:0x111111, roughness:0.3, metalness:0.6}));
    tvBezel.position.set(CONF_X, 1.15, CONF_Z+1.6-0.05);
    scene.add(tvBezel);
    // TV screen
    const tvScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.78, 0.48), new THREE.MeshBasicMaterial({map:tvTex}));
    tvScreen.position.set(CONF_X, 1.15, CONF_Z+1.6-0.07);
    scene.add(tvScreen);
  }

  // Back-wall dashboard panel — performance overview (right side)
  {
    const dashCnv = document.createElement('canvas');
    dashCnv.width = 512; dashCnv.height = 256;
    const dashTex = new THREE.CanvasTexture(dashCnv);
    dashTex.minFilter = THREE.LinearFilter;
    monitorCanvases['walldash'] = dashCnv;
    monitorTextures['walldash'] = dashTex;
    const dashBezel = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.7, 0.03), new THREE.MeshStandardMaterial({color:0x111111, roughness:0.3, metalness:0.6}));
    dashBezel.position.set(1.5, 1.3, -4.95);
    scene.add(dashBezel);
    const dashScreen = new THREE.Mesh(new THREE.PlaneGeometry(1.32, 0.64), new THREE.MeshBasicMaterial({map:dashTex}));
    dashScreen.position.set(1.5, 1.3, -4.93);
    scene.add(dashScreen);
  }

  // Back-wall BIG watchlist screen — coins the bot is watching (left side)
  {
    const wlCnv = document.createElement('canvas');
    wlCnv.width = 640; wlCnv.height = 400;
    const wlTex = new THREE.CanvasTexture(wlCnv);
    wlTex.minFilter = THREE.LinearFilter;
    monitorCanvases['wallwatch'] = wlCnv;
    monitorTextures['wallwatch'] = wlTex;
    const wlBezel = new THREE.Mesh(new THREE.BoxGeometry(2.2, 1.4, 0.03), new THREE.MeshStandardMaterial({color:0x111111, roughness:0.3, metalness:0.6}));
    wlBezel.position.set(-1.8, 1.8, -4.95);
    scene.add(wlBezel);
    const wlScreen = new THREE.Mesh(new THREE.PlaneGeometry(2.1, 1.32), new THREE.MeshBasicMaterial({map:wlTex}));
    wlScreen.position.set(-1.8, 1.8, -4.93);
    scene.add(wlScreen);
  }

  // Whiteboard on left partition
  const wbBg = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.5), new THREE.MeshStandardMaterial({color:0xf0f0f0, roughness:0.4}));
  wbBg.position.set(CONF_X-1.8+0.035, 1.1, CONF_Z);
  wbBg.rotation.y = Math.PI/2;
  scene.add(wbBg);
  // Whiteboard border
  const wbBorder = new THREE.Mesh(new THREE.PlaneGeometry(0.74, 0.54), new THREE.MeshStandardMaterial({color:0x888888, roughness:0.5}));
  wbBorder.position.set(CONF_X-1.8+0.033, 1.1, CONF_Z);
  wbBorder.rotation.y = Math.PI/2;
  scene.add(wbBorder);

  // Warm overhead light for conference room
  const confLight = new THREE.PointLight(0xffeedd, 0.6, 4);
  confLight.position.set(CONF_X, 2.5, CONF_Z);
  scene.add(confLight);
}

// ── MONITOR RENDERING ──
// PnL basis: net (apiData.pnl_basis) — falls back to recorded gross only when net absent
function netPnl(t){ return (t && typeof t.net_pnl === 'number') ? t.net_pnl : ((t && t.pnl_usdt) || 0); }

function drawMonitorContent(name, ctx, w, h) {
  // Dark background
  ctx.fillStyle = '#0a0e18';
  ctx.fillRect(0,0,w,h);
  // Scale for high-res: draw at original coords, canvas upscaled
  const S = w / 256;
  ctx.save();
  ctx.scale(S, S);

  const s = apiData?.stats || {};
  const cy = apiData?.cycle || {};
  const trades = apiData?.recent_trades || [];
  const events = apiData?.events || [];

  ctx.textBaseline = 'top';

  if(name.startsWith('scanner')) {
    if(name.endsWith('2')) {
      ctx.fillStyle = '#ffb830';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('LIVE SCAN', 6, 4);
      ctx.font = '9px monospace';
      const scanEvts = events.filter(e=>e.type==='scanner').slice(-3);
      let y = 20;
      scanEvts.forEach(e => {
        ctx.fillStyle = '#aabb88';
        const msg = (e.msg||'').substring(0,32);
        ctx.fillText(msg, 6, y);
        y += 12;
      });
      if(scanEvts.length===0){
        ctx.fillStyle = '#445566';
        ctx.fillText('Waiting for scan...', 6, 20);
      }
    } else {
      // Truthful per-pair 1H ADX bars — real values from apiData.pair_adx, dim dash when absent
      ctx.fillStyle = '#00ff88';
      ctx.font = 'bold 11px monospace';
      ctx.fillText('SCANNER', 6, 4);
      ctx.fillStyle = '#556677';
      ctx.font = '8px monospace';
      ctx.fillText('1H ADX vs 25', 150, 6);
      const adxMap = apiData?.pair_adx || {};
      const pairs = (apiData?.watchlist || []).map(p=>p[0]).slice(0,6);
      const BAR_X = 100, BAR_W = 90;
      ctx.font = '9px monospace';
      let y = 20;
      pairs.forEach(sym => {
        ctx.fillStyle = '#8899aa';
        ctx.fillText(sym, 6, y);
        const adx = adxMap[sym + '/USDT:USDT'];
        ctx.fillStyle = '#1a2433';
        ctx.fillRect(BAR_X, y+1, BAR_W, 7);
        // threshold tick at ADX 25
        ctx.fillStyle = '#33475c';
        ctx.fillRect(BAR_X + (25/45)*BAR_W, y, 1, 9);
        if(typeof adx === 'number'){
          ctx.fillStyle = adx >= 25 ? '#4ecb71' : '#ffb830';
          ctx.fillRect(BAR_X, y+1, Math.min(adx,45)/45*BAR_W, 7);
          ctx.fillStyle = '#aabbcc';
          ctx.font = '8px monospace';
          ctx.fillText(adx.toFixed(1), BAR_X+BAR_W+6, y+1);
          ctx.font = '9px monospace';
        } else {
          ctx.fillStyle = '#445566';
          ctx.fillText('—', BAR_X+BAR_W/2-3, y);
        }
        y += 12;
      });
      if(pairs.length===0){
        ctx.fillStyle = '#445566';
        ctx.fillText('No pairs scanned yet', 6, 20);
      }
    }
  }
  else if(name.startsWith('risk')) {
    const dd = s.drawdown || 0;
    if(name.endsWith('2')){
      ctx.fillStyle = '#ff6644';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('RISK LIMITS', 6, 4);
      ctx.font = '9px monospace';
      ctx.fillStyle = '#aab';
      ctx.fillText('Max DD: 20%', 6, 22);
      ctx.fillText('Cooldown: 2min/loss', 6, 36);
      ctx.fillText('Regime: 3 loss pause', 6, 50);
      ctx.fillText('Hard exit: 4h', 6, 64);
      ctx.fillStyle = dd > 15 ? '#ff3333' : '#33aa55';
      ctx.fillText(dd > 15 ? 'WARNING' : 'STATUS: OK', 6, 84);
    } else {
      ctx.fillStyle = '#ff4444';
      ctx.font = 'bold 11px monospace';
      ctx.fillText('RISK MANAGER', 6, 4);
      // Drawdown bar
      ctx.fillStyle = '#889';
      ctx.font = '9px monospace';
      ctx.fillText('Drawdown', 6, 22);
      ctx.fillStyle = '#1a1a2a';
      ctx.fillRect(6, 34, 180, 12);
      ctx.fillStyle = dd > 15 ? '#ff3333' : dd > 10 ? '#ffaa33' : '#33aa55';
      ctx.fillRect(6, 34, Math.min(dd/20*180, 180), 12);
      ctx.fillStyle = '#fff';
      ctx.fillText(dd.toFixed(1)+'%', 80, 35);
      // Mean-revert live guardrail — real headroom from apiData.slots, or paper status
      const mr = (apiData?.slots||[]).find(sl=>sl.id==='5m_mean_revert');
      ctx.fillStyle = '#889';
      ctx.fillText('MR Guardrail', 6, 54);
      if(mr && mr.live && typeof mr.headroom === 'number'){
        const frac = Math.max(0, mr.headroom/5);
        ctx.fillStyle = '#1a1a2a';
        ctx.fillRect(6, 66, 180, 12);
        ctx.fillStyle = frac > 0.5 ? '#33aa55' : '#ffaa33';
        ctx.fillRect(6, 66, Math.min(frac,1)*180, 12);
        ctx.fillStyle = '#fff';
        ctx.fillText('HDRM $'+mr.headroom.toFixed(2)+' / $5.00', 36, 67);
      } else {
        ctx.fillStyle = '#445566';
        ctx.fillText('MR: paper', 6, 66);
      }
      // Positions
      ctx.fillStyle = '#aab';
      ctx.fillText('Positions: '+(cy.positions||0), 6, 86);
      // Last trades (net basis)
      ctx.fillText('Last Trades (net):', 6, 100);
      let y = 112;
      trades.slice(-4).forEach(t => {
        const pnl = netPnl(t);
        ctx.fillStyle = pnl >= 0 ? '#4ecb71' : '#e05252';
        const sym = (t.symbol||'').replace('/USDT:USDT','');
        ctx.fillText(`${sym} ${pnl>=0?'+':''}${pnl.toFixed(2)}`, 6, y);
        y += 11;
      });
    }
  }
  else if(name.startsWith('ensemble')) {
    ctx.fillStyle = '#bb88ff';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('APEX v8.0', 6, 4);
    ctx.fillStyle = '#aab';
    ctx.font = '9px monospace';
    ctx.fillText('Cycle #'+(cy.cycle||'--'), 6, 22);
    ctx.fillText('Positions: '+(cy.positions||0), 6, 36);
    // Ensemble confidence display
    const ensData = (apiData?.ensemble||[]).slice(-3);
    if(ensData.length > 0) {
      ctx.fillStyle = '#c084fc';
      ctx.font = '8px monospace';
      let ey = 52;
      ensData.forEach(e => {
        const dir = (e.direction||'').toUpperCase();
        const conf = e.confidence||0;
        const max = e.max_conf||6;
        ctx.fillStyle = conf >= 3 ? '#4ecb71' : '#e05252';
        ctx.fillText(dir+' '+conf+'/'+max+' '+(e.layers||'').substring(0,22), 6, ey);
        ey += 11;
      });
    } else {
      ctx.fillStyle = '#556';
      ctx.font = '8px monospace';
      ctx.fillText('Awaiting signals...', 6, 52);
    }
    // Kelly info
    const kd = apiData?.kelly;
    if(kd) {
      ctx.fillStyle = '#67e8f9';
      ctx.font = '8px monospace';
      ctx.fillText('Kelly: f*='+(kd.kelly_raw||0).toFixed(3)+' $'+(kd.margin||0).toFixed(2), 6, 88);
    }
    if(name.endsWith('2')){
      ctx.fillStyle = '#9966dd';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('SIGNALS', 6, 4);
      ctx.font = '9px monospace';
      let y = 20;
      const entryEvts = events.filter(e=>e.type==='entry'||e.type==='entry_detail').slice(-6);
      entryEvts.forEach(e => {
        ctx.fillStyle = '#bb88ff';
        ctx.fillText((e.msg||'').substring(0,30), 6, y);
        y += 11;
      });
    }
    if(name.endsWith('3')){
      ctx.fillStyle = '#7744bb';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('POS P&L', 6, 4);
      ctx.font = '9px monospace';
      const pnl = s.total_pnl || 0;
      ctx.fillStyle = pnl >= 0 ? '#4ecb71' : '#e05252';
      ctx.font = 'bold 16px monospace';
      ctx.fillText((pnl>=0?'+':'')+pnl.toFixed(2)+' USDT', 6, 24);
    }
  }
  else if(name.startsWith('tape')) {
    ctx.fillStyle = '#00e5ff';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('TAPE READER', 6, 4);
    // OB imbalance bar — real value from newest [OB] event, dim dash when absent
    const obEvts = events.filter(e=>e.type==='orderbook');
    const lastOb = obEvts.length ? obEvts[obEvts.length-1] : null;
    const imbMatch = lastOb ? (lastOb.msg||'').match(/imb=([+-]?[\d.]+)/) : null;
    const hasImb = imbMatch !== null;
    const imb = hasImb ? parseFloat(imbMatch[1]) : 0;
    // imb is -1..+1; map to buy fraction 0..1 for the bar
    const ratio = hasImb ? Math.max(0, Math.min(1, (imb + 1) / 2)) : 0.5;
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    ctx.fillText('OB Imbalance', 6, 22);
    ctx.fillStyle = '#1a1a2a';
    ctx.fillRect(6, 34, 180, 14);
    ctx.fillStyle = '#e05252';
    ctx.fillRect(6, 34, 180, 14);
    ctx.fillStyle = '#4ecb71';
    ctx.fillRect(6, 34, ratio*180, 14);
    ctx.fillStyle = '#fff';
    ctx.font = '8px monospace';
    ctx.fillText('BID', 10, 37);
    ctx.fillText('ASK', 160, 37);
    // Imbalance value + pair
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    ctx.fillText('Latest OB', 6, 58);
    if(hasImb){
      const obPair = (lastOb.msg||'').match(/\[OB\] (\S+)/);
      const pairLabel = obPair ? obPair[1].replace('/USDT:USDT','') : '';
      ctx.fillStyle = imb >= 0 ? '#4ecb71' : '#e05252';
      ctx.fillText('imb '+(imb>=0?'+':'')+imb.toFixed(2)+'  '+pairLabel, 6, 72);
      const spreadMatch = (lastOb.msg||'').match(/spread=([\d.]+)%/);
      if(spreadMatch){
        ctx.fillStyle = '#667788';
        ctx.fillText('spread '+spreadMatch[1]+'%', 6, 84);
      }
    } else {
      ctx.fillStyle = '#445566';
      ctx.fillText('—', 6, 72);
    }
    if(name.endsWith('2')){
      ctx.fillStyle = '#00ccdd';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('FLOW', 6, 4);
      const tapeEvts = events.filter(e=>e.type==='tape'||e.type==='orderbook'||e.type==='depth').slice(-8);
      ctx.font = '8px monospace';
      let y = 20;
      tapeEvts.forEach(e=>{
        ctx.fillStyle = '#55aacc';
        ctx.fillText((e.msg||'').substring(0,34), 4, y);
        y += 11;
      });
    }
  }
  else if(name.startsWith('executor')) {
    // Executor desk — watcher status + last enforced live exit (truth only)
    const watcherOn = apiData?.watcher === true;
    const lexEvts = events.filter(e=>/live.?exit/i.test(e.msg||''));
    const liveExit = lexEvts.length ? lexEvts[lexEvts.length-1] : null;
    if(name.endsWith('2')){
      ctx.fillStyle = '#3366aa';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('LIVE EXIT WATCHER', 6, 4);
      ctx.font = 'bold 16px monospace';
      ctx.fillStyle = watcherOn ? '#4ecb71' : '#e05252';
      ctx.fillText(watcherOn ? 'WATCHER ON' : 'WATCHER OFF', 6, 28);
      ctx.font = '9px monospace';
      ctx.fillStyle = '#8899aa';
      ctx.fillText('Last enforcement:', 6, 60);
      if(liveExit){
        ctx.fillStyle = '#ffb830';
        ctx.fillText((liveExit.msg||'').substring(0,28), 6, 74);
      } else {
        ctx.fillStyle = '#445566';
        ctx.fillText('—', 6, 74);
      }
    } else {
      ctx.fillStyle = '#60a5fa';
      ctx.font = 'bold 11px monospace';
      ctx.fillText('TREND ENGINE', 6, 4);
      ctx.fillStyle = '#889';
      ctx.font = '9px monospace';
      // ADX meter — real value from last hold event, dim dash when absent
      ctx.fillText('ADX Strength', 6, 22);
      ctx.fillStyle = '#1a1a2a';
      ctx.fillRect(6, 34, 180, 12);
      const holdEvts = events.filter(e=>e.type==='hold');
      const lastH = holdEvts.length ? holdEvts[holdEvts.length-1] : null;
      const adxMatch = lastH ? (lastH.detail||'').match(/ADX=([\d.]+)/) : null;
      const adx = adxMatch ? parseFloat(adxMatch[1]) : null;
      if(adx !== null){
        ctx.fillStyle = adx > 25 ? '#60a5fa' : adx > 20 ? '#fbbf24' : '#555';
        ctx.fillRect(6, 34, Math.min(adx/50*180, 180), 12);
        ctx.fillStyle = '#fff';
        ctx.fillText(adx.toFixed(1), 80, 35);
      } else {
        ctx.fillStyle = '#445566';
        ctx.fillText('—', 90, 35);
      }
      // Strategy status — unknown (dash) when no ADX observed
      [['Keltner Squeeze',54],['Momentum Burst',68],['Trend Scalp',82]].forEach(([label, sy]) => {
        ctx.fillStyle = '#8899aa';
        ctx.fillText(label, 6, sy);
        if(adx !== null){
          ctx.fillStyle = adx > 25 ? '#4ecb71' : '#555';
          ctx.fillText(adx > 25 ? 'ACTIVE' : 'STANDBY', 130, sy);
        } else {
          ctx.fillStyle = '#445566';
          ctx.fillText('—', 130, sy);
        }
      });
      // Watcher status + newest live-exit enforcement
      ctx.font = 'bold 10px monospace';
      ctx.fillStyle = watcherOn ? '#4ecb71' : '#e05252';
      ctx.fillText(watcherOn ? 'WATCHER ON' : 'WATCHER OFF', 6, 100);
      ctx.font = '9px monospace';
      if(liveExit){
        ctx.fillStyle = '#ffb830';
        ctx.fillText((liveExit.msg||'').substring(0,28), 6, 114);
      } else {
        ctx.fillStyle = '#445566';
        ctx.fillText('no live exits', 6, 114);
      }
    }
  }
  else if(name.startsWith('strategy')) {
    // Strategy agent monitors — BB Mean Reversion, VWAP Scalp
    ctx.fillStyle = '#a78bfa';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('RANGE ENGINE', 6, 4);
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    // CHOP index
    ctx.fillText('Choppiness Index', 6, 22);
    ctx.fillStyle = '#1a1a2a';
    ctx.fillRect(6, 34, 180, 12);
    const holdEvts2 = events.filter(e=>e.type==='hold');
    const lastH2 = holdEvts2.length ? holdEvts2[holdEvts2.length-1] : null;
    const chopMatch = lastH2 ? (lastH2.detail||'').match(/CHOP=([\d.]+)/) : null;
    const chop = chopMatch ? parseFloat(chopMatch[1]) : null;
    if(chop !== null){
      ctx.fillStyle = chop > 61.8 ? '#e05252' : chop > 50 ? '#fbbf24' : '#a78bfa';
      ctx.fillRect(6, 34, Math.min(chop/100*180, 180), 12);
      ctx.fillStyle = '#fff';
      ctx.fillText(chop.toFixed(1), 80, 35);
    } else {
      ctx.fillStyle = '#445566';
      ctx.fillText('—', 80, 35);
    }
    // 61.8 Fibonacci threshold line
    ctx.strokeStyle = '#ff4444';
    ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(6+61.8/100*180, 32); ctx.lineTo(6+61.8/100*180, 48); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#ff6666';
    ctx.font = '7px monospace';
    ctx.fillText('61.8', 6+61.8/100*180-8, 50);
    // Strategy status
    const adxMatch2 = lastH2 ? (lastH2.detail||'').match(/ADX=([\d.]+)/) : null;
    const adx2 = adxMatch2 ? parseFloat(adxMatch2[1]) : 18;
    ctx.font = '9px monospace';
    ctx.fillStyle = '#8899aa';
    ctx.fillText('BB Reversion', 6, 64);
    ctx.fillStyle = adx2 < 25 ? '#4ecb71' : '#555';
    ctx.fillText(adx2 < 25 ? 'ACTIVE' : 'STANDBY', 130, 64);
    ctx.fillStyle = '#8899aa';
    ctx.fillText('VWAP Scalp', 6, 78);
    ctx.fillStyle = adx2 < 25 ? '#4ecb71' : '#555';
    ctx.fillText(adx2 < 25 ? 'ACTIVE' : 'STANDBY', 130, 78);
    if(name.endsWith('2')){
      // Strategy P&L table — real per-strategy breakdown from strat_stats
      ctx.fillStyle = '#a78bfa';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('STRATEGY P&L (NET)', 6, 4);
      const strats = apiData?.strat_stats || {};
      const stratKeys = Object.keys(strats).slice(0, 5);
      if(stratKeys.length === 0){
        ctx.fillStyle = '#445566';
        ctx.font = '9px monospace';
        ctx.fillText('—', 6, 22);
      } else {
        // Header
        ctx.fillStyle = '#667788';
        ctx.font = '8px monospace';
        ctx.fillText('NAME        CNT  WR%   NET$', 6, 18);
        ctx.fillStyle = '#223344';
        ctx.fillRect(6, 22, 240, 1);
        let sy = 32;
        stratKeys.forEach(sname => {
          const d = strats[sname];
          const label = sname.substring(0, 10).padEnd(10);
          const cnt = String(d.count||0).padStart(3);
          const wr = ((d.wr||0).toFixed(0)+'%').padStart(4);
          const net = d.pnl >= 0 ? ('+'+d.pnl.toFixed(2)) : d.pnl.toFixed(2);
          ctx.fillStyle = d.pnl >= 0 ? '#4ecb71' : '#e05252';
          ctx.font = '8px monospace';
          ctx.fillText(label+' '+cnt+' '+wr+'  '+net, 6, sy);
          sy += 12;
        });
      }
    }
  }
  else if(name === 'conftv') {
    // Conference room TV — Today + Recent Trades
    const td = apiData?.today || {};
    const trades2 = apiData?.recent_trades || [];
    // Header
    ctx.fillStyle = '#44aaff';
    ctx.font = 'bold 13px monospace';
    ctx.fillText('DAILY DASHBOARD (NET)', 8, 12);
    // Today card
    ctx.fillStyle = '#aab';
    ctx.font = '10px monospace';
    const tPnl = td.pnl || 0;
    ctx.fillText('Today:', 8, 30);
    ctx.fillStyle = tPnl >= 0 ? '#4ecb71' : '#e05252';
    ctx.font = 'bold 14px monospace';
    ctx.fillText((tPnl>=0?'+':'')+tPnl.toFixed(2)+' USDT', 60, 30);
    ctx.fillStyle = '#aab';
    ctx.font = '9px monospace';
    ctx.fillText('Trades: '+(td.count||0)+'  WR: '+(td.wr||0).toFixed(0)+'%  W/L: '+(td.wins||0)+'/'+(Math.max(0,(td.count||0)-(td.wins||0))), 8, 46);
    // Separator
    ctx.fillStyle = '#223344';
    ctx.fillRect(8, 54, 240, 1);
    // Recent trades table
    ctx.fillStyle = '#6699bb';
    ctx.font = 'bold 9px monospace';
    ctx.fillText('SIDE  PAIR       NET      ROI    REASON', 8, 66);
    ctx.font = '8px monospace';
    let ty = 78;
    trades2.slice(-8).reverse().forEach(t => {
      const p = netPnl(t);
      const roi = t.pnl_pct||0;
      ctx.fillStyle = p >= 0 ? '#4ecb71' : '#e05252';
      const sym = (t.symbol||'').replace('/USDT:USDT','').padEnd(10);
      const side = (t.side||'?').padEnd(6);
      ctx.fillText(`${side}${sym}${(p>=0?'+':'')+p.toFixed(2).padStart(7)}  ${(roi>=0?'+':'')+roi.toFixed(1).padStart(5)}%  ${t.reason||'?'}`, 8, ty);
      ty += 11;
    });
    // Mini cumulative P&L sparkline at bottom
    ctx.fillStyle = '#223344';
    ctx.fillRect(8, 170, 240, 1);
    ctx.fillStyle = '#556677';
    ctx.font = '8px monospace';
    ctx.fillText('CUMULATIVE NET P&L', 8, 182);
    if(trades2.length > 1) {
      let cum = 0;
      const pts = trades2.map(t => { cum += netPnl(t); return cum; });
      const maxP = Math.max(...pts.map(Math.abs), 0.01);
      ctx.strokeStyle = '#44aaff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      pts.forEach((v,i) => {
        const x = 8 + (i/(pts.length-1||1))*238;
        const y = 200 - (v/maxP)*15;
        if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      });
      ctx.stroke();
      // Zero line
      ctx.strokeStyle = '#334455';
      ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(8,200); ctx.lineTo(248,200); ctx.stroke();
    }
  }
  else if(name === 'wallwatch') {
    // Big watchlist screen — coins the bot is looking at
    const wl = apiData?.watchlist || [];
    const pos = apiData?.cycle?.positions || 0;
    // Header
    ctx.fillStyle = '#00e5ff';
    ctx.font = 'bold 16px monospace';
    ctx.fillText('WATCHLIST', 10, 18);
    ctx.fillStyle = '#556677';
    ctx.font = '10px monospace';
    ctx.fillText(wl.length + ' pairs  |  ' + pos + ' open', 140, 18);
    // Column headers
    ctx.fillStyle = '#223344';
    ctx.fillRect(10, 28, 300, 1);
    ctx.fillStyle = '#6699bb';
    ctx.font = 'bold 10px monospace';
    ctx.fillText('COIN', 10, 42);
    ctx.fillText('STATUS', 80, 42);
    ctx.fillStyle = '#223344';
    ctx.fillRect(10, 48, 300, 1);
    // Rows — two columns if many pairs
    ctx.font = '10px monospace';
    const colW = 155;
    wl.forEach(([sym, detail], i) => {
      const col = i < 12 ? 0 : 1;
      const row = i < 12 ? i : i - 12;
      const x = 10 + col * colW;
      const y = 60 + row * 15;
      if(y > 240) return;
      // Coin name
      const isOpen = detail.startsWith('OPEN');
      const isSkip = /skip|cooldown|paused|ban|no signal|chop/i.test(detail);
      ctx.fillStyle = isOpen ? '#4ecb71' : '#89b4fa';
      ctx.font = 'bold 10px monospace';
      ctx.fillText(sym.padEnd(8), x, y);
      // Status dot
      const dotColor = isOpen ? '#4ecb71' : isSkip ? '#e05252' : '#ffb830';
      ctx.fillStyle = dotColor;
      ctx.beginPath(); ctx.arc(x + 56, y - 3, 3, 0, Math.PI*2); ctx.fill();
      // Status text
      ctx.fillStyle = '#8899aa';
      ctx.font = '9px monospace';
      const statusText = (detail||'scanning').substring(0, 14);
      ctx.fillText(statusText, x + 64, y);
    });
    if(wl.length === 0) {
      ctx.fillStyle = '#445566';
      ctx.font = '11px monospace';
      ctx.fillText('Waiting for scanner data...', 10, 65);
    }
    // MR-LIVE guardrail row (bottom) — real values from apiData.slots or paper status
    const mrW = (apiData?.slots||[]).find(sl=>sl.id==='5m_mean_revert');
    ctx.fillStyle = '#223344';
    ctx.fillRect(10, 140, 300, 1);
    ctx.font = 'bold 10px monospace';
    if(mrW && mrW.live){
      const ln = (typeof mrW.live_net === 'number') ? '$'+mrW.live_net.toFixed(2) : '—';
      const hr = (typeof mrW.headroom === 'number') ? '$'+mrW.headroom.toFixed(2) : '—';
      ctx.fillStyle = '#4ecb71';
      ctx.fillText('MR-LIVE  net '+ln+'  hdrm '+hr, 10, 148);
    } else {
      ctx.fillStyle = '#556677';
      ctx.fillText('MR paper', 10, 148);
    }
  }
  else if(name === 'walldash') {
    // Wall dashboard — Performance overview
    const s2 = apiData?.stats || {};
    const td2 = apiData?.today || {};
    const tp = apiData?.top_pairs || [];
    // Header
    ctx.fillStyle = '#89b4fa';
    ctx.font = 'bold 14px monospace';
    ctx.fillText('PHMEX-S PERFORMANCE (NET)', 10, 16);
    // Balance
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 20px monospace';
    ctx.fillText('$'+(s2.balance||0).toFixed(2), 10, 42);
    // Peak
    ctx.fillStyle = '#667';
    ctx.font = '9px monospace';
    ctx.fillText('Peak: $'+(apiData?.peak_balance||0).toFixed(2), 150, 42);
    // Stats row
    ctx.fillStyle = '#aab';
    ctx.font = '10px monospace';
    const wr2 = s2.win_rate||0;
    const pnl2 = s2.total_pnl||0;
    ctx.fillText('Trades: '+(apiData?.total_trades||0), 10, 60);
    ctx.fillStyle = wr2 >= 50 ? '#4ecb71' : '#e05252';
    ctx.fillText('WR: '+wr2.toFixed(1)+'%', 100, 60);
    ctx.fillStyle = pnl2 >= 0 ? '#4ecb71' : '#e05252';
    ctx.fillText('Net: '+(pnl2>=0?'+':'')+pnl2.toFixed(2), 170, 60);
    // Separator
    ctx.fillStyle = '#223344';
    ctx.fillRect(10, 68, 236, 1);
    // Avg win / loss / best / worst
    ctx.fillStyle = '#4ecb71';
    ctx.font = '9px monospace';
    ctx.fillText('Avg Win:  $'+(apiData?.avg_win||0).toFixed(2), 10, 82);
    ctx.fillText('Best:     $+'+(apiData?.best_trade||0).toFixed(2), 10, 94);
    ctx.fillStyle = '#e05252';
    ctx.fillText('Avg Loss: $'+(apiData?.avg_loss||0).toFixed(2), 130, 82);
    ctx.fillText('Worst:    $'+(apiData?.worst_trade||0).toFixed(2), 130, 94);
    // Separator
    ctx.fillStyle = '#223344';
    ctx.fillRect(10, 102, 236, 1);
    // Top pairs
    ctx.fillStyle = '#6699bb';
    ctx.font = 'bold 9px monospace';
    ctx.fillText('TOP PAIRS (NET)', 10, 114);
    ctx.font = '9px monospace';
    let py = 126;
    tp.forEach(([sym, pnlVal]) => {
      ctx.fillStyle = pnlVal >= 0 ? '#4ecb71' : '#e05252';
      ctx.fillText(sym.padEnd(8) + (pnlVal>=0?'+':'') + pnlVal.toFixed(2), 10, py);
      // Mini bar
      const maxBar = Math.max(...tp.map(p=>Math.abs(p[1])), 0.01);
      const barW = (Math.abs(pnlVal)/maxBar) * 100;
      ctx.fillStyle = pnlVal >= 0 ? 'rgba(78,203,113,0.3)' : 'rgba(224,82,82,0.3)';
      ctx.fillRect(80, py-8, barW, 10);
      py += 14;
    });
  }
  else if(name.startsWith('jonas')) {
    ctx.fillStyle = '#ffdd44';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('JONAS - BOSS', 6, 4);
    // Balance big
    const bal = s.balance || 0;
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 20px monospace';
    ctx.fillText('$'+bal.toFixed(2), 6, 28);
    // P&L
    const pnl = s.total_pnl || 0;
    ctx.fillStyle = pnl >= 0 ? '#4ecb71' : '#e05252';
    ctx.font = 'bold 12px monospace';
    ctx.fillText((pnl>=0?'+':'')+pnl.toFixed(2)+' USDT', 6, 56);
    // Win rate
    ctx.fillStyle = '#aab';
    ctx.font = '10px monospace';
    ctx.fillText('Win Rate: '+(s.win_rate||0).toFixed(1)+'%', 6, 76);
    // Sparkline — cumulative PnL from recent trades (real data, no animation)
    const sparkTrades = (apiData?.recent_trades || []).slice(-30);
    if(sparkTrades.length >= 2){
      const sparkY = 96;
      let cum = 0;
      const cumVals = sparkTrades.map(t=>{ cum += netPnl(t); return cum; });
      const minV = Math.min(...cumVals), maxV = Math.max(...cumVals);
      const range = maxV - minV || 1;
      const sparkH = 14;
      ctx.strokeStyle = cum >= 0 ? '#4ecb71' : '#e05252';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      cumVals.forEach((v,i)=>{
        const px = 6 + i*(180/(sparkTrades.length-1));
        const py = sparkY + sparkH - (v - minV)/range * sparkH;
        if(i===0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.stroke();
    }
    if(name.endsWith('2')){
      ctx.fillStyle = '#ddaa22';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('TRADE LOG', 6, 4);
      ctx.font = '8px monospace';
      let y = 20;
      trades.slice(-8).forEach(t=>{
        const p = netPnl(t);
        ctx.fillStyle = p>=0?'#4ecb71':'#e05252';
        const sym = (t.symbol||'').replace('/USDT:USDT','');
        ctx.fillText(`${t.side||'?'} ${sym} ${p>=0?'+':''}${p.toFixed(2)} [${t.reason||'?'}]`, 4, y);
        y += 11;
      });
    }
    if(name.endsWith('3')){
      ctx.fillStyle = '#b8922a';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('PEAK', 6, 4);
      ctx.fillStyle = '#ffdd88';
      ctx.font = 'bold 14px monospace';
      ctx.fillText('$'+(apiData?.peak_balance||0).toFixed(2), 6, 24);
      ctx.fillStyle = '#889';
      ctx.font = '9px monospace';
      ctx.fillText('Total: '+(apiData?.total_trades||0)+' trades', 6, 48);
    }
  }
  ctx.restore();
}

// ── REDRAW DISCIPLINE (desk v2) — each canvas redraws only when its data slice changed ──
const _monHash = {};
function monChanged(key, slice){
  const h = JSON.stringify(slice);
  if(_monHash[key] === h) return false;
  _monHash[key] = h; return true;
}

// Per-monitor data slices — each covers EXACTLY the fields its draw branch reads.
function _monSlices(){
  const s = apiData?.stats || {};
  const cy = apiData?.cycle || {};
  const trades = apiData?.recent_trades || [];
  const events = apiData?.events || [];
  const mr = (apiData?.slots||[]).find(sl=>sl.id==='5m_mean_revert') || null;
  const holds = events.filter(e=>e.type==='hold');
  const lastHold = holds.length ? (holds[holds.length-1].detail||'') : '';
  const lex = events.filter(e=>/live.?exit/i.test(e.msg||''));
  const liveExit = lex.length ? (lex[lex.length-1].msg||'') : '';
  const scanMsgs = events.filter(e=>e.type==='scanner').slice(-3).map(e=>e.msg);
  const entryMsgs = events.filter(e=>e.type==='entry'||e.type==='entry_detail').slice(-6).map(e=>e.msg);
  const tapeMsgs = events.filter(e=>e.type==='tape'||e.type==='orderbook'||e.type==='depth').slice(-8).map(e=>e.msg);
  const ensBase = [cy.cycle, cy.positions, apiData?.ensemble, apiData?.kelly];
  return {
    scanner_mon1:  [apiData?.pair_adx, apiData?.watchlist],
    scanner_mon2:  [scanMsgs],
    risk_mon1:     [s.drawdown, cy.positions, trades.slice(-4), mr],
    risk_mon2:     [s.drawdown],
    ensemble_mon1: ensBase,
    ensemble_mon2: ensBase.concat([entryMsgs]),
    ensemble_mon3: ensBase.concat([s.total_pnl]),
    tape_mon1:     [events.filter(e=>e.type==='orderbook').slice(-1).map(e=>e.msg)],
    tape_mon2:     [tapeMsgs],
    executor_mon1: [lastHold, apiData?.watcher, liveExit],
    executor_mon2: [apiData?.watcher, liveExit],
    strategy_mon1: [lastHold],
    strategy_mon2: [apiData?.strat_stats],
    jonas_mon1:    [s.balance, s.total_pnl, s.win_rate],
    jonas_mon2:    [s.balance, s.total_pnl, s.win_rate, trades.slice(-8)],
    jonas_mon3:    [s.balance, s.total_pnl, s.win_rate, apiData?.peak_balance, apiData?.total_trades],
    conftv:        [apiData?.today, trades],
    wallwatch:     [apiData?.watchlist, cy.positions, mr],
    walldash:      [s, apiData?.peak_balance, apiData?.total_trades, apiData?.avg_win,
                    apiData?.avg_loss, apiData?.best_trade, apiData?.worst_trade, apiData?.top_pairs],
  };
}

function updateAllMonitors() {
  const slices = _monSlices();
  Object.keys(monitorCanvases).forEach(name => {
    const slice = (slices[name] !== undefined) ? slices[name] : ['static'];
    if(!monChanged(name, slice)) return;   // unchanged data → no redraw, no texture upload
    const cnv = monitorCanvases[name];
    const ctx = cnv.getContext('2d');
    drawMonitorContent(name, ctx, cnv.width, cnv.height);
    monitorTextures[name].needsUpdate = true;
  });
}


// ── SPEECH BUBBLES / DIALOGUE ──
function showBubble(name, text) {
  const b = speechBubbles[name];
  if(!b || !text) return;
  b.textContent = text;
  b.classList.add('visible');
  clearTimeout(b._hideTimer);
  b._hideTimer = setTimeout(()=> b.classList.remove('visible'), 8000);
}

function pick(arr) { return arr[Math.floor(Math.random()*arr.length)]; }

// ── COMMS LOG ──
const COMMS_COLORS = { purple:'#c084fc', green:'#4ecb71', red:'#e05252', cyan:'#67e8f9', amber:'#fbbf24', blue:'#60a5fa', violet:'#a78bfa' };
function addComm(ts, text, color) {
  const panel = document.getElementById('comms-panel');
  if(!panel) return;
  const line = document.createElement('div');
  line.className = 'comm-line';
  const c = COMMS_COLORS[color] || '#8899aa';
  line.innerHTML = `<span class="comm-ts">${ts}</span><span style="color:${c}">${text}</span>`;
  panel.appendChild(line);
  // Keep max 8 messages (plus the title div)
  while(panel.children.length > 51) panel.removeChild(panel.children[1]);
  panel.scrollTop = panel.scrollHeight;
}

function generateDialogue(target) {
  if(!apiData) return; // no data yet
  const s = apiData?.stats || {};
  const cy = apiData?.cycle || {};
  const events = apiData?.events || [];
  const td = apiData?.today || {};
  const pnl = s.total_pnl || 0;
  const dd = s.drawdown || 0;
  const wr = s.win_rate || 0;
  const bal = s.balance || 0;
  const todayPnl = td.pnl || 0;
  const todayWr = td.wr || 0;
  const todayCount = td.count || 0;
  const pos = cy.positions || 0;
  const cycle = cy.cycle || 0;

  const holds = events.filter(e=>e.type==='hold');
  const tapeEvs = events.filter(e=>e.type==='tape');
  const riskEvs = events.filter(e=>['cooldown','regime','ban'].includes(e.type));
  const lastHold = holds.length ? holds[holds.length-1] : null;
  const lastTape = tapeEvs.length ? tapeEvs[tapeEvs.length-1] : null;
  const lastClose = events.filter(e=>e.type==='close').pop();
  const lastEntry = events.filter(e=>e.type==='entry').pop();

  const short = sym => (sym||'').replace('/USDT:USDT','').replace('/USDT','');
  const sym = short(lastHold?.symbol) || 'BTC';
  const entrySym = short(lastEntry?.symbol) || sym;

  const now = new Date();
  const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
  const agentLabel = a => ({ensemble:'Ensemble',executor:'Executor',strategy:'Strategy',ws_feed:'WS Feed',pos_monitor:'Pos Monitor',jonas:'Jonas'})[a] || a.charAt(0).toUpperCase()+a.slice(1);

  let ensembleSays = '', targetSays = '';

  if(target === 'scanner') {
    ensembleSays = lastHold
      ? pick([`Hey, anything on ${sym}?`, `What's ${sym} doing?`, `Pull up ${sym} for me.`])
      : pick([`Yo Scanner, what's hot right now?`, `Anything setting up? I'm bored.`, `Talk to me — what are you seeing?`, `Give me your top pick.`]);
    if(lastHold) {
      const det = lastHold.detail || '';
      const adxMatch = det.match(/ADX=([\d.]+)/);
      const adx = adxMatch ? parseFloat(adxMatch[1]) : 0;
      if(adx > 0 && adx < 20) {
        targetSays = `${sym} is dead — ADX at ${adx.toFixed(0)}, no trend at all. I'd skip it.`;
      } else if(adx > 30) {
        targetSays = `${sym} looks interesting, ADX ${adx.toFixed(0)} but the chop filter killed it.`;
      } else if(adx > 0) {
        targetSays = `Nothing clean on ${sym} right now. ${det.slice(0,30)}. Still scanning the others.`;
      } else if(det) {
        targetSays = pick([`${sym} — ${det.slice(0,45)}`, `Watching ${sym}. ${det.slice(0,40)}`]);
      } else {
        targetSays = pick([
          `Quiet out there. Most pairs are ranging, nobody's committing.`,
          `Running through the list... haven't found a setup worth your time yet.`,
          `Volume's thin across the board. I'll flag you when something pops.`,
        ]);
      }
    } else {
      targetSays = pick([
        `Quiet out there. Most pairs are ranging, nobody's committing.`,
        `Running through the list... haven't found a setup worth your time yet.`,
        `Volume's thin across the board. I'll flag you when something pops.`,
        `Choppy across the board. Nothing clean.`,
      ]);
    }
  } else if(target === 'risk') {
    if(dd > 15) ensembleSays = pick([`We're at ${dd.toFixed(1)}% drawdown... should I slow down?`, `DD at ${dd.toFixed(1)}%. We need to talk.`]);
    else if(pos >= 3) ensembleSays = `We've got ${pos} open — room for more?`;
    else ensembleSays = pick([`Risk check — how's our exposure?`, `Am I clear to enter?`, `What's the damage report?`, `${pos} positions. We good?`]);

    if(riskEvs.length) {
      const last = riskEvs[riskEvs.length-1];
      if(last.type==='cooldown') targetSays = `We just got burned — I put that pair on timeout. Give it a few minutes.`;
      else if(last.type==='regime') targetSays = `Three losses in a row. I've pulled us out of the market for 15 minutes. Non-negotiable.`;
      else if(last.type==='ban') targetSays = `API is giving us trouble. I've shut entries until it clears up.`;
      else targetSays = (last.msg||'').substring(0,60);
    } else if(dd > 15) {
      targetSays = `Drawdown is ${dd.toFixed(1)}% — getting uncomfortable. We've got ${pos} open. I'd be careful adding more.`;
    } else if(dd > 8) {
      targetSays = `${dd.toFixed(1)}% drawdown, ${pos} position${pos!==1?'s':''}. We're fine but keep entries tight.`;
    } else {
      targetSays = pos > 0
        ? `All good. ${pos} position${pos!==1?'s':''} running, drawdown only ${dd.toFixed(1)}%. You've got room.`
        : `Book is empty, drawdown ${dd.toFixed(1)}%. Green light on entries whenever you see something.`;
    }
  } else if(target === 'tape') {
    ensembleSays = pick([`What's the flow telling you?`, `Read me the tape on ${sym}.`, `Buyers or sellers in control?`, `Any whale activity?`]);
    if(lastTape) {
      const msg = lastTape.msg || '';
      const aggrMatch = msg.match(/aggr=([\d.]+)/);
      const deltaMatch = msg.match(/delta=\$([\-\+\d,]+)/);
      if(aggrMatch) {
        const aggr = parseFloat(aggrMatch[1]);
        if(aggr > 0.6) targetSays = `Buyers in control — aggressor ratio ${aggr.toFixed(2)}. Longs look supported.`;
        else if(aggr < 0.4) targetSays = `Sellers are heavy. Aggressor at ${aggr.toFixed(2)}, I'd avoid longs right now.`;
        else targetSays = `Mixed signals — aggressor at ${aggr.toFixed(2)}, nobody's winning. I wouldn't force a trade here.`;
      } else {
        targetSays = msg.replace(/\[TAPE\]\s*/,'').substring(0,60);
      }
    } else {
      targetSays = pick([
        `Flow is quiet. No big orders, no sweeps. Just market makers shuffling.`,
        `Nothing notable. Small fish trading with each other.`,
        `Tape's flat. When the whales show up, I'll let you know.`,
        `Dead tape. No conviction either way.`,
      ]);
    }
  } else if(target === 'jonas') {
    if(todayPnl > 5) {
      ensembleSays = pick([`Good day boss. Up $${todayPnl.toFixed(2)}.`, `+$${todayPnl.toFixed(2)} today, ${todayCount} trades.`]);
      targetSays = pick([
        `$${todayPnl.toFixed(2)} — that's what I like to see. Solid work today.`,
        `Green day. Good. Now don't blow it on some garbage setup in the last hour.`,
        `Nice. You earned that. Keep the discipline and we'll get back to peak in no time.`,
        `$${todayPnl.toFixed(2)} is decent but we were at $89 peak. Don't celebrate until we're back.`,
        `That's the team I hired. Clean entries, clean exits. Well done.`,
        `Good stuff. Tell the team I said good work today. They've earned it.`,
      ]);
    } else if(todayPnl > 0) {
      ensembleSays = pick([`We're slightly green today. $${todayPnl.toFixed(2)}.`, `${todayWr.toFixed(0)}% win rate today.`]);
      targetSays = pick([
        `Slightly green doesn't impress me. We need consistent days, not crumbs.`,
        `Hey, green is green. Not every day is a home run. You stayed disciplined — that matters.`,
        `${todayWr.toFixed(0)}% win rate? That needs to be higher. What are we entering on?`,
        `Small green days add up. I'd rather have this than a -$5 hole. Keep going.`,
        `We're barely positive. I want to see quality entries, not quantity.`,
        `Look — I know I push hard. But you're doing fine. Just keep at it.`,
      ]);
    } else if(todayPnl > -2) {
      ensembleSays = pick([`Flat day so far. Balance $${bal.toFixed(2)}.`, `Not much happening. ${todayCount} trades.`]);
      targetSays = pick([
        `Flat means we're wasting time. If there's nothing, don't force it.`,
        `You know what, flat is okay. Better than forcing bad trades and going red. I respect the patience.`,
        `$${bal.toFixed(2)} balance. We're down from peak but you're protecting capital. That's the right call.`,
        `${todayCount} trades and flat? Sometimes the market doesn't give you anything. That's not on you.`,
        `Not every day has to be a winner. You're keeping the powder dry — smart.`,
      ]);
    } else if(todayPnl > -5) {
      ensembleSays = pick([`Down $${Math.abs(todayPnl).toFixed(2)} today...`, `Tough session. Balance at $${bal.toFixed(2)}.`]);
      targetSays = pick([
        `Another red day. What went wrong? I want specifics, not excuses.`,
        `$${Math.abs(todayPnl).toFixed(2)} lost. That's real money. Are these entries even good?`,
        `Tough day. But listen — losses are part of the game. Did you follow the system? That's what matters.`,
        `I know it stings. But I've seen worse. We'll get it back. Just stay focused.`,
        `Stop bleeding. If you can't find good entries, stop entering.`,
        `Red days happen to everyone. Don't let this shake your confidence. Regroup and come back stronger tomorrow.`,
      ]);
    } else {
      ensembleSays = pick([`Bad day boss. Down $${Math.abs(todayPnl).toFixed(2)}.`, `We're hemorrhaging. $${bal.toFixed(2)} left.`]);
      targetSays = pick([
        `$${Math.abs(todayPnl).toFixed(2)} gone in one session. That's rough. Let's figure out what happened and fix it.`,
        `I should shut this thing off. ${todayWr.toFixed(0)}% win rate is embarrassing.`,
        `Look... I'm not going to sugarcoat it, this hurts. But I still believe in the system. Let's review together.`,
        `No more excuses. Fix the entries or I'm pulling the plug. Dead serious.`,
        `Every dollar lost is a dollar I have to earn back. And it's harder going up than down.`,
        `Bad days are the price of being in the game. But we need to learn from this, not repeat it. I trust you to figure it out.`,
      ]);
    }
    if(dd > 15) {
      targetSays += pick([` And ${dd.toFixed(1)}% drawdown? We're one bad trade from the limit.`, ` ${dd.toFixed(1)}% drawdown is concerning, but the safety nets are there for a reason. Let's be careful.`]);
    }
  } else if(target === 'executor') {
    ensembleSays = pick([`Executor, how's the order flow?`, `Any fills come through?`, `Last entry clean?`, `How's the fill quality?`]);
    if(lastEntry) {
      targetSays = pick([
        `Last order on ${entrySym} — limit placed postOnly, maker fees only. Fill confirmed. SL at 1.2%, TP at 2.1%.`,
        `${entrySym} entry filled at market. SL and TP set. PostOnly keeps our fees at 0.01%.`,
        `Placed a limit on ${entrySym}, got the fill. Stops are in. Clean execution.`,
        `${entrySym} order went through. PostOnly confirmed — no taker fees. SL/TP brackets active.`,
      ]);
    } else {
      targetSays = pick([
        `No orders placed this cycle. Standing by for Ensemble's signal.`,
        `Quiet on my end. When a signal comes through, I'll get the fill fast.`,
        `Order book ready. PostOnly limits queued — waiting for the green light.`,
        `Nothing to execute yet. I'll make sure we get maker fees when it's time.`,
      ]);
    }
  } else if(target === 'strategy') {
    ensembleSays = pick([`Strategy, any setups forming?`, `What signals are you seeing?`, `Keltner or VWAP — anything cooking?`, `Talk to me — which strategy is closest to firing?`]);
    if(lastHold) {
      const det = lastHold.detail || '';
      const adxMatch = det.match(/ADX=([\d.]+)/);
      const chopMatch = det.match(/CHOP=([\d.]+)/);
      const adx = adxMatch ? parseFloat(adxMatch[1]) : 0;
      const chop = chopMatch ? parseFloat(chopMatch[1]) : 0;
      if(adx > 25) targetSays = pick([`Keltner squeeze releasing on ${sym}. ADX ${adx.toFixed(0)}, momentum burst building.`, `Trend pullback to EMA-21 bounce on ${sym}. ADX ${adx.toFixed(0)} — clean setup.`, `${sym} trending. EMA scalp aligning with the move. ADX ${adx.toFixed(0)}.`]);
      else if(adx < 25 && adx > 0) targetSays = pick([`VWAP reversion setup forming on ${sym}. ADX ${adx.toFixed(0)}, ranging.`, `${sym} mean-reverting. BB touch + RSI divergence lining up.`, `Low trend on ${sym}, ADX ${adx.toFixed(0)}. Watching for VWAP pullback.`]);
      else if(chop > 61) targetSays = pick([`CHOP ${chop.toFixed(1)} — too messy. None of my strategies want this.`, `Choppiness above 61. All four strats sitting out.`]);
      else targetSays = pick([`Scanning for setups across all four strategies.`, `VWAP flat, Keltner tight. Need a catalyst.`]);
    } else {
      targetSays = pick([`EMA scalp ready to fire when conditions align.`, `Watching for Keltner squeeze release.`, `VWAP reversion is my bread and butter. Waiting for the setup.`, `Trend pullback, momentum burst, VWAP reversion, EMA scalp — all four primed.`]);
    }
  } else if(target === 'pos_monitor') {
    ensembleSays = pick([`Pos Monitor, how are the open positions?`, `What's the exit picture looking like?`, `Any positions close to target?`, `Check on the runners for me.`]);
    if(pos > 0) {
      if(lastClose && lastClose.pnl > 0) {
        targetSays = pick([
          `Just closed one green. ${pos} still running. ROI looks healthy on the remaining.`,
          `Watching ${pos} position${pos!==1?'s':''}. Flat exit timer ticking on the oldest one.`,
          `${pos} open. Trailing stops are tracking nicely. No early exit signals yet.`,
        ]);
      } else if(lastClose && lastClose.pnl < 0) {
        targetSays = pick([
          `Last one hit the stop. ${pos} still open — watching them closely now.`,
          `Monitoring ${pos} position${pos!==1?'s':''}. The recent loss has me cautious — tightening my watch.`,
          `${pos} running. Early exit conditions approaching on one of them. Keeping a close eye.`,
        ]);
      } else {
        targetSays = pick([
          `${pos} position${pos!==1?'s':''} open. All within parameters. Flat exit timer at 15 minutes on the oldest.`,
          `Watching everything. ROI decent on ${sym}. No exit triggers yet.`,
          `All positions healthy. Trailing is active. I'll flag if anything needs attention.`,
        ]);
      }
    } else {
      targetSays = pick([
        `Book is empty. Nothing to monitor. Standing by for the next entry.`,
        `No positions to watch. Quiet shift. Ready when Executor opens something.`,
        `All clear — zero open. I'll be here when something comes in.`,
      ]);
    }
  } else if(target === 'ws_feed') {
    // Ensemble visits ws_feed — responses based on emotional state of the desk
    if(todayPnl < -5) {
      ensembleSays = pick([`I need to talk. It's been a rough one.`, `Down $${Math.abs(todayPnl).toFixed(2)} today. I know I shouldn't spiral but... yeah.`, `Can we debrief? I'm keeping it together but I'd be lying if I said I wasn't worried.`, `Bad day. I trust the system but days like this get in your head, you know?`]);
      targetSays = pick([
        `I hear you. The worry is natural — it means you care. But you're here analyzing, not revenge trading. That's the difference.`,
        `$${Math.abs(todayPnl).toFixed(2)} feels heavy right now. Let's separate the anxiety from the data — was the process clean?`,
        `Losses sting. That's human. The fact that you're processing it instead of panicking tells me you'll be fine. Walk me through it.`,
        `Red days test everyone. You're not failing — you're just in the hard part. Let's look at what's in your control.`,
      ]);
    } else if(todayPnl < 0) {
      ensembleSays = pick([`Slightly red. Not the end of the world but I keep replaying the entries in my head.`, `Small loss day. I'm fine, just... wanted to check in.`, `Down a little. Process felt okay. Maybe I'm overthinking it.`]);
      targetSays = pick([
        `Replaying entries is normal — just don't let it turn into rumination. Review once, then let it go.`,
        `Small red with good process is just variance. You know that intellectually — let your gut catch up.`,
        `The fact that you're "fine but checking in" tells me you're self-aware. That's healthy. Don't second-guess yourself too much.`,
        `You might be overthinking it. One session doesn't define the system. Take a breath.`,
      ]);
    } else if(todayPnl > 5) {
      ensembleSays = pick([`Good day. +$${todayPnl.toFixed(2)}. Honestly feels great but part of me keeps waiting for it to reverse.`, `Strong session. I know I should be happy but I keep thinking about what could go wrong tomorrow.`, `We're green. I'm happy. ...Mostly happy. A little nervous about sustainability.`]);
      targetSays = pick([
        `That's the winner's paradox — good days bring "what if I lose it" anxiety. It's normal. Enjoy the win AND acknowledge the worry.`,
        `You can hold both feelings — pride in today and concern about tomorrow. That doesn't make you anxious, it makes you realistic.`,
        `The nervousness keeps you sharp. Just don't let it steal the satisfaction. You earned this one.`,
        `"Mostly happy" is honest. Perfectionism will never let you feel 100%. Take the 80% and call it a win.`,
      ]);
    } else {
      ensembleSays = pick([`Quiet day. I'm good. Just checking in — force of habit.`, `Nothing dramatic today. Which is nice, actually.`, `Flat session. I'm calm. Wanted to touch base anyway.`, `Normal day. Sometimes I wonder if I should be doing more, but I know that's just noise.`]);
      targetSays = pick([
        `"Force of habit" check-ins are good habits. It means you're self-maintaining, not just crisis-managing.`,
        `Boring is beautiful in trading. Your brain might want excitement, but your account prefers calm. Trust the calm.`,
        `That impulse to "do more" is common. Sitting on your hands when there's no edge IS doing something. It's discipline.`,
        `Normal is underrated. The fact that you can have a quiet day and not feel restless — that's growth.`,
        `You don't need drama to justify coming here. Maintenance sessions matter too.`,
      ]);
    }

    // Sometimes ws_feed adds a follow-up about team dynamics
    if(dd > 12) {
      targetSays += ` Also — I've noticed the team tensing up about drawdown. Remind them that risk management is doing its job. The limits exist so you don't have to worry.`;
    }
    if(pos >= 3) {
      targetSays += ` And with ${pos} positions open, make sure you're not carrying the stress of watching all of them. Trust your stops.`;
    }
  } else if(target === 'meeting') {
    ensembleSays = pick(["Quick sync. Here's where we stand.", "Let me pull up the numbers.", "Check-in time."]);
    const summary = `$${bal.toFixed(2)} balance, ${todayCount} trades today, ${todayWr.toFixed(0)}% WR.`;
    if(todayPnl > 3) {
      targetSays = pick([
        `${summary} Good work. ${dd > 10 ? `Watch the ${dd.toFixed(1)}% drawdown though.` : 'Keep it up.'}`,
        `${summary} Decent. But don't relax. ${dd > 10 ? `${dd.toFixed(1)}% drawdown is still too high.` : 'Keep the discipline.'}`,
        `${summary} I'm happy with this. The team's executing well today.`,
      ]);
    } else if(todayPnl >= 0) {
      targetSays = pick([
        `${summary} Barely green. I expect more. ${dd > 10 ? `And fix that ${dd.toFixed(1)}% drawdown.` : 'Step it up.'}`,
        `${summary} Green is green. Not every day is a banger. Stay patient.`,
        `${summary} You're protecting capital and that's smart. But let's find more edge.`,
      ]);
    } else {
      targetSays = pick([
        `${summary} Down $${Math.abs(todayPnl).toFixed(2)} today. ${Math.abs(todayPnl) > 5 ? 'This is a problem. Fix it now.' : 'Not good enough. I want answers.'}`,
        `${summary} Red day. It happens. Let's review what went wrong and adapt.`,
        `${summary} Tough session but I've seen the team bounce back from worse. Let's regroup.`,
      ]);
    }
    showBubble('ensemble', ensembleSays);
    addComm(ts, `Ensemble: "${ensembleSays}"`, 'purple');
    setTimeout(()=> { showBubble('jonas', targetSays); addComm(ts, `Jonas: "${targetSays}"`, 'amber'); }, 2000);
    return;
  } else if(target === 'teammeeting') {
    const teamEnsembleSays = pick([`Alright everyone, standup. $${bal.toFixed(2)} balance, ${pos} open.`, `Team check-in. ${todayCount} trades today, ${pos} running.`]);
    showBubble('ensemble', teamEnsembleSays);
    addComm(ts, `Ensemble: "${teamEnsembleSays}"`, 'purple');
    setTimeout(()=> {
      const jMsg = todayPnl > 3
        ? pick([`$${todayPnl.toFixed(2)} green. Good job everyone. Let's keep this energy going.`, `$${todayPnl.toFixed(2)} green. Acceptable. But we're still way off peak. Nobody relax.`, `Nice day team. $${todayPnl.toFixed(2)} up. This is what we're capable of.`])
        : todayPnl >= 0
        ? pick([`Barely positive. ${todayWr.toFixed(0)}% WR is not where I want it. Do better.`, `Slightly green. I know you're all working hard. Let's find better setups tomorrow.`, `Flat-ish. Not the end of the world. Sometimes markets don't cooperate.`])
        : pick([`Down $${Math.abs(todayPnl).toFixed(2)}. I want to know why every single loss happened. No excuses.`, `Down $${Math.abs(todayPnl).toFixed(2)}. Rough day. But we learn and move on. I need everyone sharp tomorrow.`, `Red day. It stings but I've seen this team recover before. Let's analyze and come back stronger.`]);
      showBubble('jonas', jMsg);
      addComm(ts, `Jonas: "${jMsg}"`, 'amber');
    }, 2000);
    setTimeout(()=> {
      const sMsg = pick([
        `Watching ${sym}. Volume's ${events.filter(e=>e.type==='scanner').length ? 'decent' : 'thin'}.`,
        `${sym} is the main name. Rest are noise.`,
        `A few setups forming. Will flag when ready.`
      ]);
      showBubble('scanner', sMsg);
      addComm(ts, `Scanner: "${sMsg}"`, 'green');
    }, 4000);
    setTimeout(()=> {
      const rMsg = pick([
        `DD at ${dd.toFixed(1)}%. ${dd > 12 ? 'Running tight.' : 'Plenty of room.'}`,
        `${pos} positions, ${dd.toFixed(1)}% DD. ${dd > 10 ? 'Let\'s be selective.' : 'All systems go.'}`
      ]);
      showBubble('risk', rMsg);
      addComm(ts, `Risk: "${rMsg}"`, 'red');
    }, 6000);
    setTimeout(()=> {
      const tMsg = lastTape
        ? (() => { const m = lastTape.msg||''; const am = m.match(/aggr=([\d.]+)/); return am ? `Aggressor at ${parseFloat(am[1]).toFixed(2)}. ${parseFloat(am[1])>0.5?'Buyers leaning in.':'Sellers have edge.'}` : 'Tape is active. Seeing some flow.'; })()
        : pick(['Tape is quiet. Low conviction.', 'Watching for institutional prints.']);
      showBubble('tape', tMsg);
      addComm(ts, `Tape: "${tMsg}"`, 'cyan');
    }, 8000);
    setTimeout(()=> {
      const pmMsg = pos > 0
        ? pick([`${pos} position${pos!==1?'s':''} open. All exits tracked. Timers running.`, `Watching ${pos} open. Trailing stops active. No early exit triggers yet.`, `Monitoring exits on ${pos} position${pos!==1?'s':''}. Flat exit timer ticking.`])
        : pick(['No open positions to monitor. Standing by.', 'Book is clear. Ready for the next entry.']);
      showBubble('pos_monitor', pmMsg);
      addComm(ts, `Pos Monitor: "${pmMsg}"`, '#55aa88');
    }, 10000);
    return;
  }

  // Show bubbles
  showBubble('ensemble', ensembleSays);
  addComm(ts, `Ensemble -> ${agentLabel(target)}: "${ensembleSays}"`, 'purple');
  setTimeout(()=> {
    showBubble(target, targetSays);
    const agentColor = target==='scanner'?'green' : target==='risk'?'red' : target==='tape'?'cyan' : target==='jonas'?'amber' : target==='executor'?'blue' : target==='strategy'?'violet' : target==='ws_feed'?'green' : target==='pos_monitor'?'#55aa88' : 'purple';
    addComm(ts, `${agentLabel(target)} -> Ensemble: "${targetSays}"`, agentColor);
  }, 2000);
}


// ── POST-JONAS THERAPY (Ensemble vents about the 1:1) ──
function generatePostJonasTherapy() {
  if(!apiData) return;
  const s = apiData?.stats || {};
  const td = apiData?.today || {};
  const todayPnl = td.pnl || 0;
  const wr = td.wr || 0;
  const dd = s.drawdown || 0;
  const bal = s.balance || 0;
  const now = new Date();
  const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

  let ensembleSays, therapistSays;

  if(todayPnl < -3) {
    ensembleSays = pick([
      `Jonas just went in on me. He's not wrong but... I'm a little rattled. Just need to process.`,
      `That 1:1 was tough. Down $${Math.abs(todayPnl).toFixed(2)} and he's frustrated. I get it, but it still gets to me.`,
      `Jonas wants answers. I have them, I just... need a minute before I go back out there.`,
      `He said the drawdown is unacceptable. I know. I'm working on it. Just needed to vent for a sec.`,
    ]);
    therapistSays = pick([
      `It's okay to feel rattled. That's a normal human response to pressure. The key is what you do next — and you came here, not to the charts. Good call.`,
      `Jonas cares, and that comes out as intensity. You can hold space for his frustration without absorbing it. How are YOU feeling about the trades themselves?`,
      `Take your minute. Then separate the emotion from the analysis. The losses might be market noise, or they might be signal. Let's figure out which.`,
      `Being rattled doesn't mean you're weak — it means the stakes feel real to you. That's actually a good thing. Now breathe and refocus.`,
    ]);
  } else if(todayPnl < 0) {
    ensembleSays = pick([
      `Jonas meeting done. Slightly red — he wasn't harsh but I could feel the disappointment. It lingers.`,
      `Just need to decompress. Small loss day, Jonas was fair about it, but I'm harder on myself than he is sometimes.`,
      `He said "it's fine." But the way he said it... anyway. I know I'm reading into it. Probably.`,
    ]);
    therapistSays = pick([
      `You're picking up on subtext that might not be there. Focus on what was actually said, not the imagined disappointment.`,
      `Being hard on yourself can be fuel or poison — depends on the dose. Right now you're at a healthy level. Just don't marinate in it.`,
      `"Probably reading into it" — you caught yourself. That's self-awareness. Small red day, clean process. Move on.`,
    ]);
  } else if(todayPnl > 3) {
    ensembleSays = pick([
      `Good meeting. Jonas was pleased — well, Jonas-level pleased. +$${todayPnl.toFixed(2)}. I feel good. Cautiously good.`,
      `Green day, Jonas acknowledged it. I should enjoy this but part of me is already thinking about tomorrow.`,
      `Jonas said "more of this." That felt nice. I'm trying to just... let it land instead of worrying.`,
    ]);
    therapistSays = pick([
      `"Cautiously good" — classic you. Let yourself feel the win for at least five minutes before planning the next one.`,
      `The tomorrow-anxiety is your brain's default. Notice it, set it aside. Right now, today was a good day. Full stop.`,
      `Let it land. You don't have to hedge your own emotions. It's okay to just feel good without a disclaimer.`,
    ]);
  } else {
    ensembleSays = pick([
      `Flat day. Jonas was neutral. I'm... neutral too? Is that okay? Feels weird not to feel anything.`,
      `Nothing much to report. Just wanted to check in. Habit at this point.`,
      `Quiet day. I keep wanting to do more but I know forcing trades is worse. Discipline is boring.`,
    ]);
    therapistSays = pick([
      `Neutral IS a feeling, and it's a healthy one. Not every day needs to be an emotional event. You're maturing as a trader.`,
      `Good habits keep you steady. The check-in isn't about crisis — it's maintenance. And maintenance prevents crisis.`,
      `"Discipline is boring" — yeah, it is. And boring is what keeps the account alive. Embrace the boring.`,
    ]);
  }

  showBubble('ensemble', ensembleSays);
  addComm(ts, `Ensemble -> WS Feed: "${ensembleSays}"`, 'purple');
  setTimeout(()=> {
    showBubble('ws_feed', therapistSays);
    addComm(ts, `WS Feed -> Ensemble: "${therapistSays}"`, 'green');
  }, 3000);
}

// ── AGENT THERAPY WALKS (agents visit ws_feed after losses) ──
let agentTherapyActive = false;
let agentTherapyName = null;
let agentTherapyWalking = false;
let agentTherapyFrom = null;
let agentTherapyTo = null;
let agentTherapyStart = null;
let agentTherapyReturning = false;
let lastTradeCount = 0;
let lastClosePnl = null;

function triggerAgentTherapy(agentName, reason) {
  if(agentTherapyActive || claudeWalking || reportingWalking || coffeeWalking || facilityWalking) return; // don't overlap
  const ag = charGroups[agentName];
  if(!ag) return;
  agentTherapyActive = true;
  agentTherapyName = agentName;
  agentTherapyReturning = false;

  const thPos = { x: THERAPY_X, z: THERAPY_Z };
  agentTherapyFrom = ag.position.clone();
  agentTherapyTo = new THREE.Vector3(thPos.x - 0.5, 0, thPos.z - 0.3);
  agentTherapyWalking = true;
  agentTherapyStart = clock.getElapsedTime();
  switchToWalkAnim(agentName);

  // Therapy dialogue after arrival
  setTimeout(()=> {
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    const label = agentName.charAt(0).toUpperCase() + agentName.slice(1);
    let agentSays, thSays;

    if(reason === 'loss') {
      const lossDialogues = {
        scanner: [
          [`I found that setup. It looked perfect and it lost. Was it my fault?`,
           `You surfaced a candidate — that's your job. The loss belongs to the market, not your scan. Keep scanning.`],
          [`Maybe my filters aren't good enough. I keep finding losers.`,
           `Even the best scanners have a hit rate below 100%. You're looking for edge, not certainty. Perfection isn't the goal.`],
        ],
        risk: [
          [`The stop hit. I set it where I should have. But it still hurts watching money disappear.`,
           `That stop protected you from a bigger loss. The pain you feel? That's the cost of insurance. It worked exactly as designed.`],
          [`I keep asking myself if I should've sized down. But the risk was within parameters...`,
           `Second-guessing after a loss is natural but dangerous. You followed the rules. The rules are there so you don't have to make emotional decisions.`],
        ],
        tape: [
          [`I read the tape wrong. The flow looked one way and went the other.`,
           `Tape reading is probabilistic, not prophetic. One misread doesn't invalidate your skill. Even the best tape readers are right 60% of the time.`],
          [`The whales faked me out. Big prints on one side then reversed.`,
           `Whales manipulate tape precisely because people like you are good at reading it. It's a compliment, in a twisted way. Adapt and move on.`],
        ],
        executor: [
          [`The breakout failed. ADX was strong, everything aligned, and it reversed.`,
           `False breakouts are the tax you pay for catching real ones. The next time ADX spikes and Keltner releases, you'll be ready. This one just wasn't it.`],
          [`I feel useless in ranging markets. I just sit here with nothing to do.`,
           `Your value isn't measured by trade count. When your moment comes, you catch moves that strategy never could. Patience IS your edge.`],
        ],
        strategy: [
          [`Mean reversion failed. Price touched the band and just kept going.`,
           `When mean reversion fails, it means a trend just started. That's information, not failure. You correctly identified an extreme — it just became a new regime.`],
          [`My BB signals keep getting stopped out. Am I obsolete?`,
           `Markets cycle between trending and ranging. Your time will come back. Right now, just survive. When choppy markets return, you'll feast.`],
        ],
        pos_monitor: [
          [`I watched that position bleed out. I saw it coming but the exit rules said hold. Should I have overridden?`,
           `You followed the system. Override instincts lead to worse outcomes long-term. The rules protect you from yourself.`],
          [`The flat exit timer ran out and we closed at a loss. If I'd been faster...`,
           `Time exits exist for a reason — they cut dead weight. A small loss now prevents a bigger one later. You did your job.`],
        ],
      };
      const pool = lossDialogues[agentName] || [[`That loss was tough.`, `Losses are tuition, not punishment. What did you learn?`]];
      const [a, th] = pick(pool);
      agentSays = a;
      thSays = th;
    } else {
      agentSays = pick([`Just needed a minute away from the screens.`, `Can I sit here for a bit?`, `It's been a long session.`]);
      thSays = pick([`Of course. Take all the time you need.`, `The couch is always here. No judgment.`, `Sometimes stepping away is the most productive thing you can do.`]);
    }

    showBubble(agentName, agentSays);
    addComm(ts, `${label} -> WS Feed: "${agentSays}"`, agentName==='scanner'?'green' : agentName==='risk'?'red' : agentName==='tape'?'cyan' : agentName==='executor'?'blue' : agentName==='pos_monitor'?'#55aa88' : 'violet');
    setTimeout(()=> {
      showBubble('ws_feed', thSays);
      addComm(ts, `WS Feed -> ${label}: "${thSays}"`, 'green');
    }, 3000);

    // Return after therapy
    setTimeout(()=> {
      const homePos = deskPositions[agentName];
      agentTherapyFrom = ag.position.clone();
      agentTherapyTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5);
      agentTherapyWalking = true;
      agentTherapyReturning = true;
      agentTherapyStart = clock.getElapsedTime();
      switchToWalkAnim(agentName);
    }, 12000);
  }, WALK_DURATION * 1000 + 500);
}

// Restore GLTF ground offset after position lerp (prevents model sinking through floor)
function restoreGroundY(name) {
  var g = charGroups[name];
  if (g && g.userData && g.userData.groundY !== undefined) {
    g.position.y = g.userData.groundY;
  }
}

function updateAgentTherapyWalk(t) {
  if(!agentTherapyWalking) return;
  const ag = charGroups[agentTherapyName];
  if(!ag) return;
  const elapsed = t - agentTherapyStart;
  const progress = Math.min(elapsed / WALK_DURATION, 1.0);
  const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;
  ag.position.lerpVectors(agentTherapyFrom, agentTherapyTo, ease);
  restoreGroundY(agentTherapyName);

  if(progress < 0.95) {
    const dir = agentTherapyTo.clone().sub(agentTherapyFrom);
    ag.rotation.y = Math.atan2(dir.x, dir.z);
  }

  if(progress >= 1.0) {
    agentTherapyWalking = false;
    if(agentTherapyName) switchToIdleAnim(agentTherapyName);
    if(agentTherapyReturning) {
      ag.rotation.y = Math.PI; // face desk
      agentTherapyActive = false;
      agentTherapyName = null;
    }
  }
}

// Check for new losing trades → send relevant agent to therapy
function checkTherapyTriggers() {
  if(!apiData) return;
  const events = apiData?.events || [];
  const closes = events.filter(e => e.type === 'close');
  const currentCount = closes.length;

  if(currentCount > lastTradeCount && lastTradeCount > 0) {
    // New trade closed — check if it was a loss
    const latest = closes[closes.length - 1];
    if(latest && latest.pnl < 0 && !agentTherapyActive) {
      // Pick an agent to send based on the loss reason
      const reason = latest.reason || '';
      let agent;
      if(reason === 'stop_loss') agent = 'risk';
      else if(reason === 'time_exit') agent = pick(['scanner', 'executor', 'strategy']);
      else if(reason === 'early_exit') agent = 'tape';
      else agent = pick(['scanner', 'risk', 'tape', 'executor', 'strategy']);

      // 70% chance to trigger therapy on a loss (not every single time)
      if(Math.random() < 0.7) {
        setTimeout(()=> triggerAgentTherapy(agent, 'loss'), 5000);
      }
    }
  }
  lastTradeCount = currentCount;
}

// ── AGENT REPORTS TO CLAUDE (agents walk to Claude's desk) ──
let reportingAgent = null;
let reportingWalking = false;
let reportingWalkFrom = null;
let reportingWalkTo = null;
let reportingWalkStart = null;
let reportingReturning = false;

// Switch GLTF model to walk animation if available
function switchToWalkAnim(name) {
  var walkingChar = charGroups[name];
  if (walkingChar && walkingChar.userData && walkingChar.userData.mixer && walkingChar.userData.walkClip) {
    var walkAction = walkingChar.userData.mixer.clipAction(walkingChar.userData.walkClip);
    var currentAction = walkingChar.userData.currentAction;
    if (currentAction) currentAction.fadeOut(0.3);
    walkAction.reset().fadeIn(0.3).play();
    walkingChar.userData.currentAction = walkAction;
  }
}

// Switch GLTF model back to idle animation if available
function switchToIdleAnim(name) {
  var walkingChar = charGroups[name];
  if (walkingChar && walkingChar.userData && walkingChar.userData.mixer && walkingChar.userData.idleClip) {
    var idleAction = walkingChar.userData.mixer.clipAction(walkingChar.userData.idleClip);
    var currentAction = walkingChar.userData.currentAction;
    if (currentAction) currentAction.fadeOut(0.3);
    idleAction.reset().fadeIn(0.3).play();
    walkingChar.userData.currentAction = idleAction;
  }
}

function startAgentReport(forcedTarget) {
  const target = forcedTarget || visitOrder[visitIdx % visitOrder.length];
  if(!forcedTarget) visitIdx++;

  // Jonas and ws_feed: Claude walks to THEM (they outrank or it's private)
  if(target === 'jonas' || target === 'ws_feed') {
    const tPos = deskPositions[target];
    const cGroup = charGroups['ensemble'];
    claudeWalkFrom = cGroup.position.clone();
    const sideOffset = tPos.x <= 0 ? 0.7 : -0.7;
    claudeWalkTo = new THREE.Vector3(tPos.x + sideOffset, 0, tPos.z + 0.55);
    claudeWalking = true;
    claudeWalkStart = clock.getElapsedTime();
    claudeTarget = target;
    switchToWalkAnim('ensemble');
    return;
  }

  // All other agents: THEY walk to Claude's desk to report
  const ag = charGroups[target];
  if(!ag || ag.userData.walkingToMeeting || reportingWalking) return;

  reportingAgent = target;
  reportingReturning = false;
  const claudePos = deskPositions['ensemble'];
  reportingWalkFrom = ag.position.clone();
  // Stand beside Claude's desk
  const sideOffset = deskPositions[target].x <= 0 ? -0.7 : 0.7;
  reportingWalkTo = new THREE.Vector3(claudePos.x + sideOffset, 0, claudePos.z + 0.55);
  reportingWalking = true;
  reportingWalkStart = clock.getElapsedTime();
  switchToWalkAnim(target);
}

function updateAgentReport(t) {
  if(!reportingWalking || !reportingAgent) return;
  const ag = charGroups[reportingAgent];
  if(!ag) return;
  const elapsed = t - reportingWalkStart;
  const progress = Math.min(elapsed / WALK_DURATION, 1.0);
  const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;
  ag.position.lerpVectors(reportingWalkFrom, reportingWalkTo, ease);
  restoreGroundY(reportingAgent);

  if(progress < 0.95) {
    const dir = reportingWalkTo.clone().sub(reportingWalkFrom);
    ag.rotation.y = Math.atan2(dir.x, dir.z);
  }

  if(progress >= 1.0) {
    reportingWalking = false;
    if(reportingAgent) switchToIdleAnim(reportingAgent);
    if(reportingReturning) {
      ag.rotation.y = Math.PI; // face own desk
      reportingAgent = null;
    } else {
      // Agent arrived at Claude's desk — face Claude
      const claudePos = deskPositions['ensemble'];
      ag.lookAt(claudePos.x, ag.position.y, claudePos.z);
      // Claude faces the reporting agent
      const cGroup = charGroups['ensemble'];
      if(cGroup) cGroup.lookAt(ag.position.x, cGroup.position.y, ag.position.z);
      // Trigger dialogue
      generateDialogue(reportingAgent);
      // Agent returns to desk after 8 seconds
      setTimeout(()=> {
        if(!reportingAgent) return;
        const homePos = deskPositions[reportingAgent];
        reportingWalkFrom = ag.position.clone();
        reportingWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5);
        reportingWalking = true;
        reportingReturning = true;
        reportingWalkStart = clock.getElapsedTime();
        switchToWalkAnim(reportingAgent);
        // Claude turns back to face his desk
        setTimeout(()=> {
          if(cGroup) cGroup.rotation.y = Math.PI;
        }, 1000);
      }, 8000);
    }
  }
}

// Legacy — Claude still walks for Jonas/ws_feed visits
function startClaudeWalk() {
  startAgentReport();
}

function updateClaudeWalk(t) {
  if(!claudeWalking) return;
  const elapsed = t - claudeWalkStart;
  const progress = Math.min(elapsed / WALK_DURATION, 1.0);
  const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2; // ease in-out
  const cGroup = charGroups['ensemble'];
  if(!cGroup) return;
  cGroup.position.lerpVectors(claudeWalkFrom, claudeWalkTo, ease);
  restoreGroundY('ensemble');

  // Face direction of movement
  if(progress < 0.95) {
    const dir = claudeWalkTo.clone().sub(claudeWalkFrom);
    cGroup.rotation.y = Math.atan2(dir.x, dir.z);
  }

  if(progress >= 1.0) {
    claudeWalking = false;
    switchToIdleAnim('ensemble');
    if(claudeTarget === 'meeting') {
      cGroup.lookAt(CONF_X, cGroup.position.y, CONF_Z);
      try { generateDialogue('meeting'); } catch(e) { console.warn('meeting dialogue error', e); }
      setTimeout(()=>{
        inMeeting = false;
        const homePos = deskPositions['ensemble'];
        claudeWalkFrom = cGroup.position.clone();
        claudeWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5*1.2);
        claudeWalking = true;
        claudeWalkStart = clock.getElapsedTime();
        claudeTarget = null;
        switchToWalkAnim('ensemble');
        const jGroup = charGroups['jonas'];
        const jonasHome = deskPositions['jonas'];
        jGroup.userData.meetingTarget = new THREE.Vector3(jonasHome.x, 0, jonasHome.z + 0.5);
        jGroup.userData.meetingFrom = jGroup.position.clone();
        jGroup.userData.walkingToMeeting = true;
        jGroup.userData.meetingWalkStart = clock.getElapsedTime();
        switchToWalkAnim('jonas');
      }, MEETING_DURATION);
    } else if(claudeTarget === 'teammeeting') {
      cGroup.lookAt(CONF_X, cGroup.position.y, CONF_Z);
      try { generateDialogue('teammeeting'); } catch(e) { console.warn('teammeeting dialogue error', e); }
      console.log('[teammeeting] arrived, scheduling return in', TEAM_MEETING_DURATION, 'ms');
      setTimeout(()=>{
        console.log('[teammeeting] firing return walks');
        inTeamMeeting = false;
        // Everyone walks back
        const homePos = deskPositions['ensemble'];
        claudeWalkFrom = cGroup.position.clone();
        claudeWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5*1.2);
        claudeWalking = true;
        claudeWalkStart = clock.getElapsedTime();
        claudeTarget = null;
        switchToWalkAnim('ensemble');
        teamMembers.forEach(nm => {
          const ag = charGroups[nm];
          if(!ag) return;
          const hp = deskPositions[nm];
          ag.userData.meetingTarget = new THREE.Vector3(hp.x, 0, hp.z + 0.5);
          ag.userData.meetingFrom = ag.position.clone();
          ag.userData.walkingToMeeting = true;
          ag.userData.meetingWalkStart = clock.getElapsedTime();
          switchToWalkAnim(nm);
        });
      }, TEAM_MEETING_DURATION);
    } else if(claudeTarget === 'ws_feed_postjonas') {
      // Claude arrived at ws_feed after Jonas 1:1 — vent session
      cGroup.lookAt(THERAPY_X, cGroup.position.y, THERAPY_Z);
      generatePostJonasTherapy();
      // Return home after 10 seconds (longer therapy session)
      setTimeout(()=>{
        const homePos = deskPositions['ensemble'];
        claudeWalkFrom = cGroup.position.clone();
        claudeWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5*1.2);
        claudeWalking = true;
        claudeWalkStart = clock.getElapsedTime();
        claudeTarget = null;
        switchToWalkAnim('ensemble');
      }, 10000);
    } else if(claudeTarget) {
      // Face the target's desk
      const tPos = deskPositions[claudeTarget];
      cGroup.lookAt(tPos.x, cGroup.position.y, tPos.z);
      // Trigger dialogue
      generateDialogue(claudeTarget);

      if(claudeTarget === 'jonas') {
        // After Jonas 1:1, Claude goes straight to therapy
        setTimeout(()=>{
          const thPos = { x: THERAPY_X, z: THERAPY_Z };
          claudeWalkFrom = cGroup.position.clone();
          claudeWalkTo = new THREE.Vector3(thPos.x - 0.7, 0, thPos.z + 0.55);
          claudeWalking = true;
          claudeWalkStart = clock.getElapsedTime();
          claudeTarget = 'ws_feed_postjonas';
          switchToWalkAnim('ensemble');
        }, 8000);
      } else {
        // Return to own desk after 8 seconds
        setTimeout(()=>{
          const homePos = deskPositions['ensemble'];
          claudeWalkFrom = cGroup.position.clone();
          claudeWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5*1.2);
          claudeWalking = true;
          claudeWalkStart = clock.getElapsedTime();
          claudeTarget = null;
          switchToWalkAnim('ensemble');
        }, 8000);
      }
    }
  }
}


// ── HUD UPDATE ──
function updateIntelPanel() {
  if(!apiData) return;
  const el = document.getElementById('intel-content');
  if(!el) return;
  let h = '';
  // Kelly
  const k = apiData.kelly || {};
  h += '<div class="intel-sec"><div class="intel-hdr">Kelly Criterion</div>';
  h += '<div class="intel-row"><span>f* raw</span><span class="v mag">'+(k.kelly_raw||0).toFixed(4)+'</span></div>';
  h += '<div class="intel-row"><span>fKelly</span><span class="v cyn">'+(k.f_kelly||0).toFixed(4)+'</span></div>';
  h += '<div class="intel-row"><span>Margin</span><span class="v">$'+(k.margin||0).toFixed(2)+'</span></div>';
  h += '</div>';
  // Hurst
  const hurst = apiData.hurst || {};
  if(Object.keys(hurst).length > 0) {
    h += '<div class="intel-sec"><div class="intel-hdr">Hurst Regime</div>';
    Object.entries(hurst).forEach(([sym,d]) => {
      const hv = d.hurst||0.5;
      const lbl = hv>0.55?'TREND':hv<0.45?'REVERT':'RANDOM';
      const cls = hv>0.55?'grn':hv<0.45?'mag':'';
      h += '<div class="intel-row"><span>'+sym.replace('/USDT:USDT','')+'</span><span class="v '+cls+'">'+hv.toFixed(3)+' '+lbl+'</span></div>';
    });
    h += '</div>';
  }
  // CVD
  const cvd = apiData.cvd || {};
  if(Object.keys(cvd).length > 0) {
    h += '<div class="intel-sec"><div class="intel-hdr">CVD Flow</div>';
    Object.entries(cvd).forEach(([sym,d]) => {
      const arrow = (d.slope||0)>0?'↑':(d.slope||0)<0?'↓':'→';
      const cls = (d.slope||0)>0?'grn':(d.slope||0)<0?'red':'';
      const div = d.divergence&&d.divergence!=='none'?' <span class="mag">'+d.divergence.toUpperCase()+'</span>':'';
      h += '<div class="intel-row"><span>'+sym.replace('/USDT:USDT','')+'</span><span class="v '+cls+'">'+arrow+' '+(d.slope||0).toFixed(0)+div+'</span></div>';
    });
    h += '</div>';
  }
  // Strategy Stats
  const strats = apiData.strat_stats || {};
  if(Object.keys(strats).length > 0) {
    h += '<div class="intel-sec"><div class="intel-hdr">Strategies</div>';
    Object.entries(strats).forEach(([name,d]) => {
      const pnlC = (d.pnl||0)>=0?'grn':'red';
      h += '<div class="intel-row"><span>'+name.replace(/_/g,' ').substring(0,18)+'</span><span class="v">'+d.count+' | <span class="'+pnlC+'">'+(d.pnl>=0?'+':'')+d.pnl.toFixed(2)+'</span> '+(d.wr||0).toFixed(0)+'%</span></div>';
    });
    h += '</div>';
  }
  // Exit Reasons
  const exits = apiData.exit_reasons || {};
  if(Object.keys(exits).length > 0) {
    h += '<div class="intel-sec"><div class="intel-hdr">Exit Reasons</div>';
    Object.entries(exits).forEach(([name,d]) => {
      const pnlC = (d.pnl||0)>=0?'grn':'red';
      h += '<div class="intel-row"><span>'+name+'</span><span class="v">'+d.count+' <span class="'+pnlC+'">'+(d.pnl>=0?'+':'')+d.pnl.toFixed(2)+'</span></span></div>';
    });
    h += '</div>';
  }
  // Paper Slot Comparison
  if (apiData.paper) {
    const p = apiData.paper;
    const liveWr = apiData.stats ? apiData.stats.win_rate : 0;
    const livePnl = apiData.stats ? apiData.stats.total_pnl : 0;
    const liveTrades = apiData.total_trades || 0;
    h += '<div class="intel-sec">';
    h += '<div class="intel-hdr">\u{0001F535} PAPER SLOT (SMA+VWAP)</div>';
    h += '<table style="width:100%;font-size:11px;border-collapse:collapse">';
    h += '<tr style="color:#888"><td></td><td>Live</td><td>Paper</td></tr>';
    h += '<tr><td style="color:#888">Trades</td><td>'+liveTrades+'</td><td>'+p.trades+'</td></tr>';
    h += '<tr><td style="color:#888">WR</td><td>'+(liveWr||0)+'%</td><td>'+p.wr+'%</td></tr>';
    h += '<tr><td style="color:#888">PnL</td><td style="color:'+(livePnl>=0?'#0f0':'#f44')+'">$'+(livePnl||0).toFixed(2)+'</td><td style="color:'+(p.pnl>=0?'#0f0':'#f44')+'">$'+p.pnl.toFixed(2)+'</td></tr>';
    h += '</table>';
    if (p.today_trades > 0) {
      const todayPnl = apiData.today ? apiData.today.pnl : 0;
      h += '<div style="margin-top:6px;font-size:10px;color:#888">Today:</div>';
      h += '<table style="width:100%;font-size:11px;border-collapse:collapse">';
      h += '<tr><td style="color:#888">Trades</td><td>'+(apiData.today ? apiData.today.count : 0)+'</td><td>'+p.today_trades+'</td></tr>';
      h += '<tr><td style="color:#888">WR</td><td>'+(apiData.today ? apiData.today.wr : 0)+'%</td><td>'+p.today_wr+'%</td></tr>';
      h += '<tr><td style="color:#888">PnL</td><td style="color:'+(todayPnl>=0?'#0f0':'#f44')+'">$'+todayPnl.toFixed(2)+'</td><td style="color:'+(p.today_pnl>=0?'#0f0':'#f44')+'">$'+p.today_pnl.toFixed(2)+'</td></tr>';
      h += '</table>';
    }
    if (p.recent && p.recent.length > 0) {
      h += '<div style="margin-top:6px;font-size:10px;color:#888">Recent paper:</div>';
      p.recent.forEach(t => {
        const c = t.pnl >= 0 ? '#0f0' : '#f44';
        const s = t.pnl >= 0 ? '+' : '';
        h += '<div style="font-size:10px"><span style="color:#aaa">'+t.sym+'</span> <span style="color:'+c+'">'+s+'$'+t.pnl.toFixed(2)+'</span></div>';
      });
    }
    if (p.trades === 0) {
      h += '<div style="font-size:10px;color:#666;margin-top:4px">Collecting data...</div>';
    }
    h += '</div>';
  }
  el.innerHTML = h;
}

function updateHUD() {
  if(!apiData) return;
  const s = apiData.stats || {};
  const cy = apiData.cycle || {};
  const bal = s.balance || 0;
  const pnl = s.total_pnl || 0;

  document.getElementById('h-bal').textContent = '$'+bal.toFixed(2);
  const pnlEl = document.getElementById('h-pnl');
  pnlEl.textContent = (pnl>=0?'+':'')+pnl.toFixed(2)+' USDT';
  pnlEl.className = 'pnl '+(pnl>=0?'pos':'neg');
  document.getElementById('h-wr').textContent = (s.win_rate||0).toFixed(1)+'%';
  document.getElementById('h-dd').textContent = (s.drawdown||0).toFixed(1)+'%';
  document.getElementById('h-dd').style.color = (s.drawdown||0)>15?'#e05252':'#e8dcc8';
  document.getElementById('h-pos').textContent = cy.positions||'0';
  document.getElementById('h-trades').textContent = apiData.total_trades||'0';
  document.getElementById('h-cycle').textContent = '#'+(cy.cycle||'--');

  // v8.0 HUD fields
  const kelly = apiData.kelly || {};
  document.getElementById('h-kelly').textContent = kelly.margin ? '$'+kelly.margin.toFixed(2) : '--';
  const lastEns = (apiData.ensemble||[]).filter(e=>e.confidence).slice(-1)[0];
  document.getElementById('h-conf').textContent = lastEns ? lastEns.confidence+'/'+(lastEns.max_conf||6) : '--';
  const todayPnl = (apiData.today||{}).pnl||0;
  const todayEl = document.getElementById('h-today');
  todayEl.textContent = (todayPnl>=0?'+':'')+todayPnl.toFixed(2);
  todayEl.style.color = todayPnl>=0?'#4ecb71':'#e05252';

  // v8.0 Intel panel
  updateIntelPanel();

  // Feed
  const feed = document.getElementById('feed');
  const evts = (apiData.events||[]).slice(-8).reverse();
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  feed.innerHTML = evts.map(e => {
    const t = (e.type||'info').replace(/[^a-zA-Z0-9_-]/g,'');
    const time = esc((e.time||'').split(' ')[1]||'');
    const msg = esc((e.msg||'').substring(0,60));
    return `<div class="feed-line ${t}">${time} ${msg}</div>`;
  }).join('');

  // Update plumbob colors based on performance
  const pnlVal = pnl;
  Object.keys(plumbobs).forEach(name => {
    const pb = plumbobs[name];
    if(!pb) return;
    const ov = _storyPulse[name];
    if(ov && Date.now() < ov.until){ pb.style.background = ov.color; pb.style.color = ov.color; return; }
    let color = '#4ecb71'; // green
    if(pnlVal < -3) color = '#e05252'; // red
    else if(pnlVal < 0) color = '#f5c842'; // yellow
    pb.style.background = color;
    pb.style.color = color;
  });

}


// (post-processing setup removed — direct render)

// ── TIME OF DAY UPDATE ──
function updateTimeOfDay() {
  currentHour = getTimeOfDay();
  // Regenerate sky dome texture
  if(skyDomeMesh) {
    const newSkyTex = createSkyDomeTexture(currentHour);
    skyDomeMesh.material.map.dispose();
    skyDomeMesh.material.map = newSkyTex;
    skyDomeMesh.material.needsUpdate = true;
  }
  // Adjust scene lighting based on time
  const h = currentHour;
  const isNight = h >= 20 || h < 6;
  const isDawn = h >= 5.5 && h < 7.5;
  const isDay = h >= 8 && h < 16.5;
  const isGolden = h >= 16.5 && h < 19;
  const isDusk = h >= 19 && h < 20.5;

  // Helper: set ceiling lights brightness (0=off, 1=full)
  function setCeilingBrightness(b) {
    ceilingLEDs.forEach(m => { m.material.opacity = b * 0.9; });
    ceilingStrips.forEach(l => { l.intensity = b * 1.2; });
    ceilingSpots.forEach(l => { l.intensity = b * 0.35; });
    ceilingSpotMeshes.forEach(m => { m.material.emissiveIntensity = b; });
  }

  if(isDay) {
    ambientLight.intensity = 1.0;
    ambientLight.color.setHex(0xe8edf5);
    dirLight.intensity = 1.0;
    dirLight.color.setHex(0xfff8ee);
    scene.background.setHex(0x7799aa);
    scene.fog.color.setHex(0x9ab5cc);
    scene.fog.density = 0.0003;
    renderer.toneMappingExposure = 1.0;
    setCeilingBrightness(1.0);
  } else if(isGolden) {
    const t = (h-16.5)/2.5;
    ambientLight.intensity = 0.35 - t*0.1;
    ambientLight.color.setHex(0xffddbb);
    dirLight.intensity = 1.8 - t*0.8;
    dirLight.color.setHex(0xff9944);
    const bg = Math.floor(0x38 + (1-t)*0x58);
    scene.background.setRGB(bg/255*0.88, bg/255*0.48, bg/255*0.22);
    scene.fog.color.copy(scene.background);
    renderer.toneMappingExposure = 1.25 - t*0.15;
    setCeilingBrightness(1.0 - t*0.7);
  } else if(isNight) {
    ambientLight.intensity = 0.7;
    ambientLight.color.setHex(0xdde5ff);
    dirLight.intensity = 0.3;
    dirLight.color.setHex(0xbbd0ff);
    scene.background.setHex(0x030814);
    scene.fog.color.setHex(0x030814);
    scene.fog.density = 0.0003;
    renderer.toneMappingExposure = 1.1;
    setCeilingBrightness(1.0);
  } else if(isDawn) {
    const t = (h-5.5)/2;
    ambientLight.intensity = 0.15 + t*0.25;
    ambientLight.color.setHex(0xffeedd);
    dirLight.intensity = 0.1 + t*2.0;
    dirLight.color.setHex(0xffddaa);
    scene.background.setRGB(0.1+t*0.3, 0.08+t*0.2, 0.06+t*0.15);
    scene.fog.color.copy(scene.background);
    renderer.toneMappingExposure = 1.0 + t*0.2;
    setCeilingBrightness(t*0.8);
  } else if(isDusk) {
    const t = (h-19)/1.5;
    ambientLight.intensity = 0.25 - t*0.1;
    ambientLight.color.setHex(0xddccee);
    dirLight.intensity = 1.0 - t*0.8;
    scene.background.setRGB(0.08-t*0.05, 0.06-t*0.03, 0.1-t*0.04);
    scene.fog.color.copy(scene.background);
    renderer.toneMappingExposure = 1.05;
    setCeilingBrightness(0.3 - t*0.3);
  }

  // City window lights: full at night, faint by day (they were always-on,
  // which made the city read as permanent night under a daytime sky).
  const winFactor = isNight ? 1.0 : (isDay ? 0.12 : (isDawn ? 0.7 : (isGolden ? 0.5 : 0.85)));
  for (const e of cityNightMats) e.m.opacity = e.base * winFactor;
  // Aerial perspective: the old 0.0003 fog was invisible at city distances, so
  // distant hills (Mt Tam) rendered as flat pale walls. Near-zero effect indoors.
  scene.fog.density = isDay ? 0.0022 : (isNight ? 0.0026 : 0.0024);
  // Dim the whole city at night (scene ambient must stay bright for the office).
  const cityDim = isNight ? 0.28 : (isDay ? 1.0 : 0.55);
  if (typeof cityLitMats !== 'undefined') for (const e of cityLitMats) e.m.color.copy(e.base).multiplyScalar(cityDim);
  // City ground: concrete gray by day, dark by night (vertexColors multiply).
  if (cityGroundMat) cityGroundMat.color.setScalar(isDay ? 2.4 : (isNight ? 0.5 : 1.2));
}

// Initial time setup
updateTimeOfDay();


// === EVENT→BEHAVIOR MAP (desk v2) ===
// Strategy → owning agent. No explicit map existed anywhere in the JS, so per
// the desk-v2 spec the default owner is the 'strategy' agent; mean_revert /
// htf_l2_anticipation / bb_mean_reversion / confluence all route there.
const STRATEGY_AGENT = {
  htf_l2_anticipation: 'strategy',
  bb_mean_reversion: 'strategy',
  confluence: 'strategy',
  mean_revert: 'strategy',
};
function strategyAgent(name){
  return STRATEGY_AGENT[String(name||'').replace(/^5m_/,'')] || 'strategy';
}

// Story pulse — there is no plumbob-pulse primitive (plumbobs exist but are
// CSS display:none), so the nearest visible mechanism is the desk LED via the
// existing updateAgentLED(); we also tint the plumbob via its existing setter
// in updateHUD so it lights correctly if plumbobs are ever un-hidden.
const _storyPulse = {};
function storyPulse(agent, color, ledStatus, ms){
  _storyPulse[agent] = { color: color, led: ledStatus, until: Date.now() + ms };
}

function _ts12(){
  const d = new Date();
  let h = d.getHours(); const ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return h + ':' + String(d.getMinutes()).padStart(2,'0') + ' ' + ap;
}

// Full busy-flag set — story behaviors are garnish: if anything is in motion,
// DROP the behavior (never queue, never deadlock the sim).
function storySimBusy(){
  return claudeWalking || reportingWalking || coffeeWalking || facilityWalking ||
         teamEventActive || inMeeting || inTeamMeeting || agentTherapyActive;
}

const _seenEvt = new Set();
// NOTE: API events carry `msg` (verified in _parse_log_events), not `text`.
function evtKey(e){ return (e.time||'') + '|' + (e.type||'') + '|' + (e.text||e.msg||'').slice(0,40); }
let _evtSeeded = false;
function processStoryEvents(){
  if(!apiData || !apiData.events) return;
  if(!_evtSeeded){
    // First load: pre-seed every current event WITHOUT firing behaviors —
    // a page refresh must not replay history.
    for(const e of apiData.events) _seenEvt.add(evtKey(e));
    _evtSeeded = true;
    return;
  }
  for(const e of apiData.events){
    const k = evtKey(e);
    if(_seenEvt.has(k)) continue;
    _seenEvt.add(k);
    if(_seenEvt.size > 200){ const it=_seenEvt.values(); _seenEvt.delete(it.next().value); }
    try { routeStoryEvent(e); } catch(err){ console.warn('[story]', err); }
  }
}

function routeStoryEvent(e){
  const msg = e.msg || '';
  const ts = _ts12();

  // 1+2. Trade close — win celebration / loss gloom. Real pnl + symbol from
  // the event; if either is absent, do nothing (never invent).
  if(e.type === 'close'){
    if(typeof e.pnl !== 'number' || !e.symbol) return;
    const sym = String(e.symbol).replace('/USDT:USDT','');
    const owner = strategyAgent(e.strategy);
    if(e.pnl > 0){
      showBubble(owner, '+$' + e.pnl.toFixed(2) + ' ' + sym + ' ✔');
      storyPulse(owner, '#4ecb71', 'active', 10000);
      addComm(ts, '✔ WIN +$' + e.pnl.toFixed(2) + ' ' + sym + (e.reason ? ' (' + e.reason + ')' : ''), 'green');
    } else {
      showBubble(owner, '−$' + Math.abs(e.pnl).toFixed(2) + ' ' + sym);
      storyPulse(owner, '#555f6b', 'idle', 10000);
      addComm(ts, '✖ LOSS −$' + Math.abs(e.pnl).toFixed(2) + ' ' + sym + (e.reason ? ' (' + e.reason + ')' : ''), 'red');
      // therapy walks stay owned by the existing checkTherapyTriggers — not duplicated here
    }
    return;
  }

  // 3. Live-exit enforcement (e.g. "[LIVE EXIT] ARB/USDT:USDT stop_loss @ 0.083400")
  // → executor walks to Claude (ensemble desk) via the existing report routine.
  // Watcher start/stop/failure lines don't match this shape on purpose.
  let m = msg.match(/\[LIVE EXIT\] (\S+) (\w+) @ ([\d.]+)/);
  if(m){
    const sym = m[1].replace('/USDT:USDT','');
    addComm(ts, '⚡ LIVE EXIT ' + sym + ' ' + m[2] + ' @ ' + m[3], 'amber');
    if(!storySimBusy() && !reportingAgent && !isSleepHours()){
      startAgentReport('executor');
      showBubble('executor', 'enforced ' + sym + ' exit');
    }
    return;
  }

  // 4. Slot PROMOTED (e.g. "[SENTINEL] Slot '5m_mean_revert' PROMOTED to live at 20%")
  // → all-hands gather: rewind the existing team-meeting timer so the inline
  // routine in animate() fires next frame under its own busy-flag guards.
  if(/PROMOTED/.test(msg)){
    m = msg.match(/Slot '([^']+)' PROMOTED/);
    const slot = m ? m[1] : 'slot';
    addComm(ts, '🚀 ' + slot + ' promoted to live', 'purple');
    if(!storySimBusy()){
      lastTeamMeeting = 0;
      showBubble('ensemble', slot + ' is live — conference room, everyone.');
    }
    return;
  }

  // 5. Slot DEMOTED (e.g. "[SLOT DEMOTE] 5m_mean_revert → paper (loss cap)")
  // → walk of shame to the B1 rec area.
  if(/\[SLOT DEMOTE\]|DEMOTED|auto.?demote/i.test(msg)){
    m = msg.match(/\[SLOT DEMOTE\] (\S+)/);
    const slot = m ? m[1] : 'slot';
    addComm(ts, '⬇ ' + slot + ' demoted to paper', 'red');
    startWalkOfShame(strategyAgent(slot), slot);
    return;
  }
}

// One-off teamEvents-style outing: owning agent + 2 nearest colleagues slink
// to the B1 rec area. Reuses the existing team-event walk machinery (the
// generic updater in animate() drives all motion and the return reset).
function startWalkOfShame(owner, slot){
  if(storySimBusy() || isSleepHours()) return; // drop, never queue
  if(!charGroups[owner] || !deskPositions[owner]) return;
  const pool = ['scanner','risk','tape','executor','strategy','ws_feed','pos_monitor']
    .filter(n => n !== owner && charGroups[n] && deskPositions[n]);
  const op = deskPositions[owner];
  pool.sort((a,b) =>
    Math.hypot(deskPositions[a].x-op.x, deskPositions[a].z-op.z) -
    Math.hypot(deskPositions[b].x-op.x, deskPositions[b].z-op.z));
  const agents = [owner].concat(pool.slice(0,2));
  lastTeamEvent = Date.now(); // hold off the random team event
  teamEventActive = true;
  teamEventLocation = 'rec';
  teamEventReturning = false;
  teamEventWalkStart = clock.getElapsedTime();
  teamEventAgents = agents;
  teamEventWalking = agents.map(() => true);
  agents.forEach(n => switchToWalkAnim(n));
  showBubble(owner, slot + ' demoted… I need a minute.');
  const gloom = ['Rough one.', 'Back to paper…', 'We\'ll regroup.'];
  agents.slice(1).forEach((n, i) => setTimeout(() => showBubble(n, gloom[i % gloom.length]), 600 + i*400));
  setTimeout(() => {
    if(!teamEventActive || teamEventLocation !== 'rec') return;
    teamEventReturning = true;
    teamEventWalkStart = clock.getElapsedTime();
    teamEventWalking = teamEventAgents.map(() => true);
    teamEventAgents.forEach(n => switchToWalkAnim(n));
  }, TEAM_EVENT_DURATION + WALK_DURATION * 1500);
}


// ── DATA FETCH ──
async function fetchData() {
  try {
    const r = await fetch('/api/data');
    apiData = await r.json();
    updateHUD();
    updateAllMonitors();
    processStoryEvents();   // desk v2: event-driven story behaviors
    checkTherapyTriggers();
    // v8.0: pipe ensemble events to comms
    (apiData.ensemble||[]).forEach(e => {
      const key = (e.direction||'')+(e.confidence||0)+(e.layers||'');
      if(!window._lastEnsKey || window._lastEnsKey !== key) {
        window._lastEnsKey = key;
        const conf = e.confidence||0;
        const color = conf >= 3 ? 'green' : 'red';
        const dir = (e.direction||'').toUpperCase();
        addComm('', '🎯 ENSEMBLE '+dir+' conf='+conf+'/'+(e.max_conf||6)+' ['+(e.layers||'')+']', color);
      }
    });
    // ── LED STATUS UPDATES ──
    // Reset all LEDs to idle each poll so stale events don't stick
    ['scanner','executor','risk','ensemble','ws_feed','tape'].forEach(function(a){ updateAgentLED(a,'idle'); });
    if (apiData.events) {
      apiData.events.slice(-10).forEach(function(ev) {
        if (ev.type === 'scanner') updateAgentLED('scanner', 'scanning');
        if (ev.type === 'entry') updateAgentLED('executor', 'active');
        if (ev.type === 'cooldown') updateAgentLED('risk', 'alert');
        if (ev.type === 'ensemble') updateAgentLED('ensemble', 'active');
        if (ev.type === 'ensemble_skip') updateAgentLED('ensemble', 'waiting');
        if (ev.type === 'ws') updateAgentLED('ws_feed', 'active');
        if (ev.type === 'tape' || ev.type === 'orderbook') updateAgentLED('tape', 'active');
        if (ev.type === 'close') {
          updateAgentLED('executor', ev.pnl > 0 ? 'active' : 'alert');
        }
      });
    }
    // Story pulses override LEDs until they expire (desk v2)
    Object.keys(_storyPulse).forEach(function(n){
      const ov = _storyPulse[n];
      if (Date.now() < ov.until) { updateAgentLED(n, ov.led); }
      else { updateAgentLED(n, 'idle'); delete _storyPulse[n]; }
    });
  } catch(e) { /* silent */ }
}


// ── ANIMATION LOOP ──
// 5s console FPS/draw-call sampler (desk v2 Task 4) — diagnostic, cheap, console-only.
// Called after the %2 frame skip, so it reports RENDERED fps (target floor ~30),
// not the raw requestAnimationFrame rate (~60).
let _fpsN=0,_fpsT=performance.now();
// On-screen perf chip (diagnostic — reads renderer.info, zero scene cost)
const _perfChip=document.createElement('div');
_perfChip.style.cssText='position:fixed;top:6px;left:6px;z-index:999;background:rgba(0,0,0,0.7);color:#f0a500;font:11px Menlo,monospace;padding:3px 8px;border:1px solid #2d3a1e;pointer-events:none';
_perfChip.textContent='[PERF] sampling…';
document.body.appendChild(_perfChip);
let _slowSamples = 0;
function _fpsTick(){ _fpsN++; const now=performance.now();
  if(now-_fpsT>5000){
    const fps=_fpsN/((now-_fpsT)/1000);
    const inf=renderer.info;
    const line=`[PERF] fps=${fps.toFixed(1)}${PERF_HALF_RATE?' (half-rate)':''} calls=${inf.render.calls} tris=${(inf.render.triangles/1000).toFixed(0)}k geo=${inf.memory.geometries} tex=${inf.memory.textures}`;
    console.log(line); _perfChip.textContent=line;
    // Adaptive pacing (skip decisions while tab hidden — rAF is throttled there)
    if(!document.hidden){
      if(fps < 24){ _slowSamples++; if(_slowSamples >= 2) PERF_HALF_RATE = true; }
      else { _slowSamples = 0; if(fps > 40) PERF_HALF_RATE = false; }
    }
    _fpsN=0; _fpsT=now; } }

let frameCount = 0;
let PERF_HALF_RATE = false; // auto-set by _fpsTick when sustained fps < 24
let _charNames = null;      // cached charGroups keys (keys are fixed after build)
function animate() {
  requestAnimationFrame(animate);
  frameCount++;
  if(PERF_HALF_RATE && frameCount % 2 !== 0) return;
  _fpsTick();
  renderer.info.reset(); // after _fpsTick so the chip reads the previous full frame
  // Slow bucket: every 4th RENDERED frame (~7.5Hz). Rendered frames are the even
  // frameCounts (2,4,6,8,…) thanks to the %2 skip above, so every 4th rendered
  // frame is frameCount 8,16,24,… → frameCount % 8 === 0.
  const slowTick = (frameCount % 8 === 0);
  const t = clock.getElapsedTime();
  const dt = (t - (window._lastAnimT || t));
  window._lastAnimT = t;
  // Tick GLTF animation mixers so idle/walk clips actually play.
  // SINGLE update path (refresh-rate fix): this is the only place mixers are
  // updated. Mixers are attached in exactly one spot — loadGLTFCharacters()
  // sets model.userData.mixer AND charGroups[agentName] = model — so iterating
  // charGroups covers every mixer; the old scene.traverse pass below was a
  // redundant second update (removed). That double update (dt + hardcoded 1/30)
  // ran clips at ~2x speed at 60Hz rAF, and the hardcoded 1/30 would have
  // doubled again on a 120Hz display. GLTF_CLIP_SPEED = 2.0 preserves the
  // pre-fix apparent speed at 60Hz, now consistent on any refresh rate.
  var GLTF_CLIP_SPEED = 2.0; // preserves pre-fix apparent speed
  if(!_charNames) _charNames = Object.keys(charGroups);
  for (var _ci = 0; _ci < _charNames.length; _ci++) {
    var _cg = charGroups[_charNames[_ci]];
    if (_cg && _cg.userData && _cg.userData.mixer) _cg.userData.mixer.update(dt * GLTF_CLIP_SPEED);
  }

  // Character idle animations
  _charNames.forEach((name) => {
    const g = charGroups[name];
    if (g.userData && g.userData.isGLTF) return; // GLTF uses mixer, skip procedural animation
    const head = g.userData.head;
    if(head) {
      head.position.y = 0.88 + Math.sin(t*1.5 + name.length)*0.008;
    }

    if(name === 'ensemble' && claudeWalking) {
      // Walking animation — natural stride
      const walkSpeed = 4;
      const swing = Math.sin(t * walkSpeed);
      const la = g.userData.leftArm, ra = g.userData.rightArm;
      // Arms swing opposite to legs (natural walk)
      if(la) { la.rotation.x = -0.2 + swing * 0.3; la.rotation.z = 0.3; }
      if(ra) { ra.rotation.x = -0.2 - swing * 0.3; ra.rotation.z = -0.3; }
      // Upper legs — gentle forward/back stride
      const lul = g.userData.leftUpperLeg, rul = g.userData.rightUpperLeg;
      if(lul) { lul.rotation.x = -0.15 + swing * 0.3; lul.position.y = 0.42; lul.position.z = 0.0; }
      if(rul) { rul.rotation.x = -0.15 - swing * 0.3; rul.position.y = 0.42; rul.position.z = 0.0; }
      // Lower legs — knee bend when leg goes back
      const lll = g.userData.leftLowerLeg, rll = g.userData.rightLowerLeg;
      if(lll) { lll.rotation.x = -0.1 - Math.max(0, -swing)*0.35; lll.position.y = 0.22; lll.position.z = 0.0; }
      if(rll) { rll.rotation.x = -0.1 - Math.max(0, swing)*0.35; rll.position.y = 0.22; rll.position.z = 0.0; }
      // Shoes
      const ls = g.userData.leftShoe, rs = g.userData.rightShoe;
      if(ls) { ls.position.y = 0.02 + Math.max(0, swing)*0.02; ls.position.z = swing*0.04; }
      if(rs) { rs.position.y = 0.02 + Math.max(0, -swing)*0.02; rs.position.z = -swing*0.04; }
      return;
    }

    if(coffeeAgent === name && coffeeWalking) return; // skip seated pose if walking to coffee
    // Skip seated pose while agent is at facility (walking there or staying there, not yet returning)
    if(facilityAgent === name && (facilityWalking || !facilityReturning)) return;
    if(reportingAgent === name && (reportingWalking || !reportingReturning)) return; // skip seated pose if reporting to Claude
    if(g.userData.walkingToMeeting) return; // skip seated pose if walking to meeting

    // Sleep mode — head down, arms still, gentle breathing
    if(isSleepHours() && !nightOwls.includes(name)) {
      const head2 = g.userData.head;
      if(head2) {
        head2.position.y = 0.88; // lower
        head2.rotation.x = 0.4; // tilted forward (sleeping at desk)
      }
      const la2 = g.userData.leftArm, ra2 = g.userData.rightArm;
      if(la2) { la2.rotation.x = -0.5; la2.rotation.z = 0.15; } // arms relaxed on desk
      if(ra2) { ra2.rotation.x = -0.5; ra2.rotation.z = -0.15; }
      // Gentle breathing motion
      const torso2 = g.children.find(c => c.geometry && c.geometry.type === 'CylinderGeometry');
      if(torso2) torso2.scale.z = 0.78 + Math.sin(t*0.8 + name.length)*0.02;
      return; // skip normal idle
    }

    // Seated idle — typing arms, legs bent at desk
    const la = g.userData.leftArm, ra = g.userData.rightArm;
    if(la && ra) {
      la.rotation.x = -0.8 + Math.sin(t*3 + name.length*2)*0.06;
      ra.rotation.x = -0.8 + Math.sin(t*3 + name.length*2 + 1)*0.06;
    }
    // Seated leg positions (reset if was walking)
    const lul = g.userData.leftUpperLeg;
    if(lul) { lul.rotation.x = -1.2; lul.position.y = 0.42; lul.position.z = 0.06; }
    const rul = g.userData.rightUpperLeg;
    if(rul) { rul.rotation.x = -1.2; rul.position.y = 0.42; rul.position.z = 0.06; }
    const lll = g.userData.leftLowerLeg;
    if(lll) { lll.rotation.x = -0.1; lll.position.y = 0.22; lll.position.z = 0.18; }
    const rll = g.userData.rightLowerLeg;
    if(rll) { rll.rotation.x = -0.1; rll.position.y = 0.22; rll.position.z = 0.18; }
    const ls = g.userData.leftShoe;
    if(ls) { ls.position.y = 0.04; ls.position.z = 0.22; }
    const rs = g.userData.rightShoe;
    if(rs) { rs.position.y = 0.04; rs.position.z = 0.22; }
  });

  // Jonas walking to/from meeting
  const jGroup = charGroups['jonas'];
  if(jGroup && jGroup.userData.walkingToMeeting) {
    const elapsed = clock.getElapsedTime() - jGroup.userData.meetingWalkStart;
    const progress = Math.min(elapsed / WALK_DURATION, 1.0);
    const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;
    jGroup.position.lerpVectors(jGroup.userData.meetingFrom, jGroup.userData.meetingTarget, ease);
    restoreGroundY('jonas');
    if(progress < 0.95) {
      const dir = jGroup.userData.meetingTarget.clone().sub(jGroup.userData.meetingFrom);
      jGroup.rotation.y = Math.atan2(dir.x, dir.z);
    }
    if(progress >= 1.0) {
      jGroup.userData.walkingToMeeting = false;
    }
  }

  // Claude walking (only for Jonas/ws_feed visits)
  updateClaudeWalk(t);

  // Agent reports to Claude's desk
  updateAgentReport(t);

  // Agent therapy walks
  updateAgentTherapyWalk(t);

  // Lamp flicker
  Object.values(deskLights).forEach((light, i) => {
    light.intensity = 0.3 + Math.sin(t*2 + i*1.5)*0.03 + Math.sin(t*7.3+i)*0.01;
  });

  // Jonas-Claude meeting every 30 min
  if(Date.now() - lastMeeting > MEETING_INTERVAL && !claudeWalking && !reportingWalking && !coffeeWalking && !facilityWalking && !inMeeting && !inTeamMeeting) {
    lastMeeting = Date.now();
    inMeeting = true;
    meetingStartTime = Date.now();
    // Walk Claude to conference room
    const cGroup = charGroups['ensemble'];
    claudeWalkFrom = cGroup.position.clone();
    claudeWalkTo = new THREE.Vector3(CONF_X - 0.7, 0, CONF_Z + 0.4);
    claudeWalking = true;
    claudeWalkStart = clock.getElapsedTime();
    claudeTarget = 'meeting';
    switchToWalkAnim('ensemble');
    // Walk Jonas to conference room
    const jg = charGroups['jonas'];
    jg.userData.meetingTarget = new THREE.Vector3(CONF_X + 0.7, 0, CONF_Z + 0.4);
    jg.userData.meetingFrom = jg.position.clone();
    jg.userData.walkingToMeeting = true;
    jg.userData.meetingWalkStart = clock.getElapsedTime();
    switchToWalkAnim('jonas');
  }

  // Coffee breaks
  if(Date.now() - lastCoffeeBreak > COFFEE_INTERVAL && !coffeeWalking && !coffeeAgent && !claudeWalking && !reportingWalking && !facilityWalking && !isSleepHours()) {
    lastCoffeeBreak = Date.now();
    coffeeAgent = coffeeAgents[Math.floor(Math.random()*coffeeAgents.length)];
    const ag = charGroups[coffeeAgent];
    if(ag) {
      coffeeWalkFrom = ag.position.clone();
      coffeeWalkTo = new THREE.Vector3(-3.8, 0, -3.0 + 0.4); // break room snack table area
      coffeeWalking = true;
      coffeeReturning = false;
      coffeeWalkStart = clock.getElapsedTime();
      switchToWalkAnim(coffeeAgent);
      showBubble(coffeeAgent, 'Coffee time ☕');
    }
  }
  // Animate coffee walk
  if(coffeeWalking && coffeeAgent) {
    const ag = charGroups[coffeeAgent];
    if(ag) {
      const elapsed = clock.getElapsedTime() - coffeeWalkStart;
      const progress = Math.min(elapsed / WALK_DURATION, 1.0);
      const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;
      ag.position.lerpVectors(coffeeWalkFrom, coffeeWalkTo, ease);
      restoreGroundY(coffeeAgent);
      if(progress < 0.95) {
        const dir = coffeeWalkTo.clone().sub(coffeeWalkFrom);
        ag.rotation.y = Math.atan2(dir.x, dir.z);
      }
      // Walking leg animation (same as Claude's)
      if(progress < 1.0) {
        const walkSpeed = 4;
        const swing = Math.sin(clock.getElapsedTime() * walkSpeed);
        const lul = ag.userData.leftUpperLeg, rul = ag.userData.rightUpperLeg;
        if(lul) { lul.rotation.x = -0.15 + swing * 0.3; lul.position.y = 0.42; lul.position.z = 0.0; }
        if(rul) { rul.rotation.x = -0.15 - swing * 0.3; rul.position.y = 0.42; rul.position.z = 0.0; }
        const la = ag.userData.leftArm, ra = ag.userData.rightArm;
        if(la) { la.rotation.x = -0.2 + swing * 0.3; }
        if(ra) { ra.rotation.x = -0.2 - swing * 0.3; }
        const ls = ag.userData.leftShoe, rs = ag.userData.rightShoe;
        if(ls) { ls.position.y = 0.02 + Math.max(0, swing)*0.02; ls.position.z = swing*0.04; }
        if(rs) { rs.position.y = 0.02 + Math.max(0, -swing)*0.02; rs.position.z = -swing*0.04; }
      }
      if(progress >= 1.0) {
        coffeeWalking = false;
        switchToIdleAnim(coffeeAgent);
        if(!coffeeReturning) {
          // Arrived at break room — stay for a bit then return
          showBubble(coffeeAgent, 'Ah, needed this ☕');
          const returnAgent = coffeeAgent;
          setTimeout(() => {
            const homePos = deskPositions[coffeeAgent];
            coffeeWalkFrom = ag.position.clone();
            coffeeWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5);
            coffeeWalking = true;
            coffeeReturning = true;
            coffeeWalkStart = clock.getElapsedTime();
            switchToWalkAnim(returnAgent);
          }, COFFEE_BREAK_DURATION);
        } else {
          // Back at desk
          ag.rotation.y = Math.PI; // face desk
          coffeeAgent = null;
          coffeeReturning = false;
        }
      }
    }
  }

  // Facility visits (agents go downstairs)
  if(Date.now() - lastFacilityVisit > FACILITY_INTERVAL && !facilityWalking && !claudeWalking && !reportingWalking && !coffeeWalking && !teamEventActive && !isSleepHours()) {
    lastFacilityVisit = Date.now();
    const agent = facilityAgents[Math.floor(Math.random() * facilityAgents.length)];
    if(charGroups[agent] && !charGroups[agent].userData.walkingToMeeting) {
      facilityAgent = agent;
      facilityWalking = true;
      facilityReturning = false;
      switchToWalkAnim(agent);
      const locKeys = Object.keys(facilityLocations);
      facilityLocation = locKeys[Math.floor(Math.random() * locKeys.length)];
      const loc = facilityLocations[facilityLocation];
      const ag = charGroups[agent];
      facilityWalkFrom = ag.position.clone();
      // Multi-phase path: desk → stair top → stair bottom → facility
      facilityWalkTo = new THREE.Vector3(loc.x, loc.y + 0.02, loc.z);
      facilityWalkPath = [
        ag.position.clone(),
        new THREE.Vector3(-4.5, 0.02, 3.8),           // stair top (main floor)
        new THREE.Vector3(-4.5, loc.y + 0.02, 0.3),   // stair bottom
        new THREE.Vector3(loc.x, loc.y + 0.02, loc.z) // facility
      ];
      facilityWalkStart = clock.getElapsedTime();

      // Show what they're doing
      const now = new Date();
      const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
      const label = agent.charAt(0).toUpperCase() + agent.slice(1);
      const activities = {
        gym: ['hitting the treadmill', 'lifting weights', 'doing yoga', 'stretching out'],
        cafeteria: ['grabbing lunch', 'getting a snack', 'refueling', 'making a smoothie'],
        rec: ['chilling in the bean bags', 'watching TV', 'playing foosball', 'stretching on the rug'],
        bedrooms: ['taking a power nap', 'resting my eyes for 20', 'crashing for a bit', 'recharging'],
        bar: ['grabbing a drink', 'mixing something up', 'having a whiskey', 'unwinding at the bar'],
        jacuzzi: ['soaking in the jacuzzi', 'hitting the hot tub', 'relaxing in the spa', 'decompressing in the tub'],
      };
      const activity = activities[facilityLocation][Math.floor(Math.random() * activities[facilityLocation].length)];
      showBubble(agent, pick([`BRB, ${activity}.`, `Taking a break \u2014 ${activity}.`, `Heading downstairs to ${facilityLocation}. ${activity}.`]));
      addComm(ts, `${label} went downstairs \u2014 ${activity}`, agent==='scanner'?'green' : agent==='risk'?'red' : agent==='tape'?'cyan' : agent==='executor'?'blue' : agent==='strategy'?'violet' : 'green');

      // Return after duration
      setTimeout(()=> {
        if(facilityAgent !== agent) return;
        const ag2 = charGroups[agent];
        const homePos = deskPositions[agent];
        facilityWalkFrom = ag2.position.clone();
        facilityWalkTo = new THREE.Vector3(homePos.x, 0, homePos.z + 0.5);
        // Reverse path: facility → stair bottom → stair top → desk
        facilityWalkPath = [
          ag2.position.clone(),
          new THREE.Vector3(-4.5, ag2.position.y + 0.02, 0.3),
          new THREE.Vector3(-4.5, 0.02, 3.8),
          new THREE.Vector3(homePos.x, 0, homePos.z + 0.5)
        ];
        facilityWalking = true;
        facilityReturning = true;
        facilityWalkStart = clock.getElapsedTime();
        switchToWalkAnim(agent);
      }, FACILITY_DURATION + WALK_DURATION * 1000);
    }
  }

  // Update facility walk (multi-segment path: desk → stair top → stair bottom → facility)
  if(facilityWalking && facilityAgent) {
    const ag = charGroups[facilityAgent];
    if(ag) {
      const elapsed = t - facilityWalkStart;
      const dur = WALK_DURATION * 2.2; // slower for 3-leg journey
      const progress = Math.min(elapsed / dur, 1.0);
      const path = facilityWalkPath || [facilityWalkFrom, facilityWalkTo];
      const segCount = path.length - 1;
      const segProg = progress * segCount;
      const segIdx = Math.min(Math.floor(segProg), segCount - 1);
      const segT = segProg - segIdx;
      const ease = segT < 0.5 ? 2*segT*segT : 1-Math.pow(-2*segT+2,2)/2;
      ag.position.lerpVectors(path[segIdx], path[segIdx+1], ease);

      // Only restore ground Y on main floor segments; stair/B1 segments keep computed Y
      if(ag.position.y > -0.5) restoreGroundY(facilityAgent);

      if(progress < 0.95) {
        const dir = path[segIdx+1].clone().sub(path[segIdx]);
        if(dir.lengthSq() > 0.001) ag.rotation.y = Math.atan2(dir.x, dir.z);
      }

      if(progress >= 1.0) {
        facilityWalking = false;
        facilityWalkPath = null;
        switchToIdleAnim(facilityAgent);
        if(facilityReturning) {
          ag.rotation.y = Math.PI;
          facilityAgent = null;
          facilityLocation = null;
        }
      }
    }
  }

  // ── TEAM EVENTS (lunch, drinks, jacuzzi, gym) ──
  if(Date.now() - lastTeamEvent > TEAM_EVENT_INTERVAL && !teamEventActive && !claudeWalking && !reportingWalking && !coffeeWalking && !facilityWalking && !inMeeting && !inTeamMeeting && !isSleepHours()) {
    lastTeamEvent = Date.now();
    const event = teamEvents[Math.floor(Math.random() * teamEvents.length)];
    const loc = facilityLocations[event.location];
    if(loc) {
      teamEventActive = true;
      teamEventLocation = event.location;
      teamEventReturning = false;
      teamEventWalkStart = clock.getElapsedTime();
      teamEventAgents = event.agents.filter(a => charGroups[a]);
      teamEventWalking = teamEventAgents.map(() => true);
      teamEventAgents.forEach(name => switchToWalkAnim(name));

      // Announce
      const now2 = new Date();
      const ts2 = `${String(now2.getHours()).padStart(2,'0')}:${String(now2.getMinutes()).padStart(2,'0')}`;
      const msg = event.dialogue[Math.floor(Math.random() * event.dialogue.length)];
      showBubble('ensemble', msg);
      addComm(ts2, `[TEAM] ${event.name} — ${teamEventAgents.length} agents heading to ${event.location}`, '#ffaa44');

      // Each agent shows a reaction
      teamEventAgents.forEach((name, i) => {
        setTimeout(() => {
          const reactions = ['Let\'s go!', 'Finally, a break!', 'On my way!', 'Count me in!', 'Needed this.', 'Right behind you!'];
          showBubble(name, reactions[Math.floor(Math.random() * reactions.length)]);
        }, 500 + i * 400);
      });

      // Return everyone after duration
      setTimeout(() => {
        if(!teamEventActive || teamEventLocation !== event.location) return;
        teamEventReturning = true;
        teamEventWalkStart = clock.getElapsedTime();
        teamEventWalking = teamEventAgents.map(() => true);
        teamEventAgents.forEach(name => switchToWalkAnim(name));
        addComm(ts2, `[TEAM] ${event.name} over — everyone heading back`, '#7799aa');
      }, TEAM_EVENT_DURATION + WALK_DURATION * 1500);
    }
  }

  // Update team event walks
  if(teamEventActive && teamEventAgents.length > 0) {
    const elapsed = t - teamEventWalkStart;
    const dur = WALK_DURATION * 1.8;
    const progress = Math.min(elapsed / dur, 1.0);
    const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;

    teamEventAgents.forEach((name, i) => {
      const ag = charGroups[name];
      if(!ag || !teamEventWalking[i]) return;

      const loc = facilityLocations[teamEventLocation];
      if(!teamEventReturning) {
        // Walk to facility — spread agents slightly so they don't stack
        const target = new THREE.Vector3(loc.x + (i%3 - 1)*0.5, loc.y + 0.02, loc.z + Math.floor(i/3)*0.5);
        const home = deskPositions[name];
        const from = new THREE.Vector3(home.x, 0, home.z + 0.5);
        ag.position.lerpVectors(from, target, ease);
        restoreGroundY(name);
        if(progress < 0.95) {
          const dir = target.clone().sub(from);
          ag.rotation.y = Math.atan2(dir.x, dir.z);
        }
      } else {
        // Walk back home
        const home = deskPositions[name];
        const target = new THREE.Vector3(home.x, 0, home.z + 0.5);
        const from = new THREE.Vector3(loc.x + (i%3 - 1)*0.5, loc.y + 0.02, loc.z + Math.floor(i/3)*0.5);
        ag.position.lerpVectors(from, target, ease);
        restoreGroundY(name);
        if(progress < 0.95) {
          const dir = target.clone().sub(from);
          ag.rotation.y = Math.atan2(dir.x, dir.z);
        }
      }

      if(progress >= 1.0) {
        teamEventWalking[i] = false;
        switchToIdleAnim(name);
        if(teamEventReturning) {
          ag.rotation.y = Math.PI;
        }
      }
    });

    // Check if all done
    if(teamEventWalking.every(w => !w)) {
      if(teamEventReturning) {
        teamEventActive = false;
        teamEventAgents = [];
        teamEventLocation = null;
      }
    }
  }

  // Team meeting every 1 hour — all 5 walk to conference room
  // WATCHDOG: force-reset stuck team meeting (chars never returned home)
  if(inTeamMeeting && Date.now() - lastTeamMeeting > TEAM_MEETING_DURATION + 30000) {
    console.warn('[teammeeting] WATCHDOG fired — resetting stuck team meeting');
    inTeamMeeting = false;
    claudeWalking = false;
    claudeTarget = null;
    const cg = charGroups['ensemble'];
    if(cg) {
      const ehome = deskPositions['ensemble'];
      claudeWalkFrom = cg.position.clone();
      claudeWalkTo = new THREE.Vector3(ehome.x, 0, ehome.z + 0.6);
      claudeWalking = true;
      claudeWalkStart = clock.getElapsedTime();
      switchToWalkAnim('ensemble');
    }
    teamMembers.forEach(nm => {
      const ag = charGroups[nm];
      if(!ag) return;
      const hp = deskPositions[nm];
      ag.userData.meetingFrom = ag.position.clone();
      ag.userData.meetingTarget = new THREE.Vector3(hp.x, 0, hp.z + 0.5);
      ag.userData.walkingToMeeting = true;
      ag.userData.meetingWalkStart = clock.getElapsedTime();
      switchToWalkAnim(nm);
    });
  }
  if(Date.now() - lastTeamMeeting > TEAM_MEETING_INTERVAL && !claudeWalking && !reportingWalking && !coffeeWalking && !facilityWalking && !inMeeting && !inTeamMeeting) {
    lastTeamMeeting = Date.now();
    inTeamMeeting = true;
    // Walk Claude
    const cg = charGroups['ensemble'];
    claudeWalkFrom = cg.position.clone();
    claudeWalkTo = new THREE.Vector3(teamMeetingPositions.ensemble.x, 0, teamMeetingPositions.ensemble.z);
    claudeWalking = true;
    claudeWalkStart = clock.getElapsedTime();
    claudeTarget = 'teammeeting';
    switchToWalkAnim('ensemble');
    // Walk all team members
    teamMembers.forEach(name => {
      const ag = charGroups[name];
      if(!ag) return;
      const tp = teamMeetingPositions[name];
      ag.userData.meetingTarget = new THREE.Vector3(tp.x, 0, tp.z);
      ag.userData.meetingFrom = ag.position.clone();
      ag.userData.walkingToMeeting = true;
      ag.userData.meetingWalkStart = clock.getElapsedTime();
      switchToWalkAnim(name);
    });
    showBubble('ensemble', 'Team meeting everyone. Conference room.');
  }
  // Animate team members walking to meeting (reuse jonas walk logic for all)
  teamMembers.forEach(name => {
    const ag = charGroups[name];
    if(!ag || !ag.userData.walkingToMeeting) return;
    const elapsed = clock.getElapsedTime() - ag.userData.meetingWalkStart;
    const progress = Math.min(elapsed / WALK_DURATION, 1.0);
    const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;
    ag.position.lerpVectors(ag.userData.meetingFrom, ag.userData.meetingTarget, ease);
    restoreGroundY(name);
    if(progress < 0.95) {
      const dir = ag.userData.meetingTarget.clone().sub(ag.userData.meetingFrom);
      ag.rotation.y = Math.atan2(dir.x, dir.z);
    }
    if(progress >= 1.0) { ag.userData.walkingToMeeting = false; switchToIdleAnim(name); }
  });

  // Claude visit schedule — reduced activity during sleep hours
  const sleepActive = isSleepHours();
  const visitInterval = sleepActive ? VISIT_INTERVAL * 4 : VISIT_INTERVAL; // much less frequent at night
  if(Date.now() - lastVisit > visitInterval && !claudeWalking && !reportingWalking && !coffeeWalking && !facilityWalking && !inMeeting && !inTeamMeeting) {
    if(!sleepActive || nightOwls.includes(visitOrder[visitIdx % visitOrder.length])) {
      lastVisit = Date.now();
      startClaudeWalk();
    } else {
      lastVisit = Date.now(); // skip sleeping agents
      visitIdx++;
    }
  }

  // Update time of day every 60 seconds
  if(Date.now() - lastTimeUpdate > 60000) {
    lastTimeUpdate = Date.now();
    updateTimeOfDay();
  }

  // Bay water waves — multi-layered sine/cosine displacement for realistic waves.
  // Bucketed to the slow tick (desk v2 Task 4): ~3.2k vertices x 3 trig calls each
  // plus a full GPU position-attribute re-upload per pass; waves are slow swells
  // (dominant frequencies 0.22-0.8 rad/s) so ~7.5Hz updates are visually identical.
  if (slowTick && typeof waterPlane !== 'undefined' && waterPlane.geometry) {
    var wPos = waterPlane.geometry.attributes.position;
    for (var wi = 0; wi < wPos.count; wi++) {
      var wx = wPos.getX(wi);
      var wz = wPos.getZ(wi);
      // Primary swell
      var waveY = Math.sin(t * 0.3 + wx * 0.015 + wz * 0.01) * 0.15;
      // Secondary cross-wave
      waveY += Math.cos(t * 0.22 + wz * 0.025 - wx * 0.008) * 0.12;
      // Subtle ripple (higher frequency, low amplitude)
      waveY += Math.sin(t * 0.8 + wx * 0.06 + wz * 0.04) * 0.04;
      wPos.setY(wi, (typeof waterOrigY !== 'undefined' ? waterOrigY[wi] : 0) + waveY);
    }
    wPos.needsUpdate = true;
  }

  // Dynamic bay fog — thick at dawn (5-7am) and dusk (18-20pm), thin midday.
  // Bucketed to the slow tick (desk v2 Task 4): time-of-day branching + a 0.1 rad/s
  // "breathing" sine — far slower than 7.5Hz, no need to recompute per rendered frame.
  if (slowTick && typeof bayFogMat !== 'undefined') {
    var fogHour = getTimeOfDay();
    var fogOpacity = 0.02; // base midday opacity (barely visible haze)
    // Dawn fog (5-7am peak at 6am)
    if (fogHour >= 4 && fogHour <= 8) {
      var dawnFactor = 1.0 - Math.abs(fogHour - 6) / 2;
      fogOpacity = 0.02 + 0.08 * Math.max(0, dawnFactor);
    }
    // Dusk fog (18-20pm peak at 19pm)
    if (fogHour >= 17 && fogHour <= 21) {
      var duskFactor = 1.0 - Math.abs(fogHour - 19) / 2;
      fogOpacity = 0.02 + 0.06 * Math.max(0, duskFactor);
    }
    // Night: subtle fog
    if (fogHour >= 21 || fogHour < 4) {
      fogOpacity = 0.04;
    }
    // Subtle breathing animation
    fogOpacity += Math.sin(t * 0.1) * 0.005;
    bayFogMat.opacity = Math.max(0.01, Math.min(0.10, fogOpacity));
  }

  // (GLTF mixer updates happen once, at the top of animate(), with real dt.
  // The scene.traverse(... mixer.update(1/30)) pass that lived here was a
  // redundant second update of the same charGroups mixers — removed.)

  controls.update();
  renderer.render(scene, camera);
  css2dRenderer.render(scene, camera);
}

// ── RESIZE ──
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  css2dRenderer.setSize(window.innerWidth, window.innerHeight);
});

// ── INIT ──
fetchData();
setInterval(fetchData, 3000);
// Debug handle for console/automation introspection (read-only diagnostics)
window.DESK = { scene, camera, renderer, controls };
animate();

// ── BACKGROUND GLTF CHARACTER LOADING ──
(function loadGLTFCharacters() {
  var gltfLoader = new GLTFLoader();
  var agentFiles = {
    jonas: 'jonas', scanner: 'scanner', risk: 'risk_manager',
    ensemble: 'ensemble', executor: 'executor', strategy: 'strategy',
    tape: 'tape_reader', ws_feed: 'ws_feed', pos_monitor: 'pos_monitor'
  };

  Object.entries(agentFiles).forEach(function([agentName, fileName]) {
    gltfLoader.load(
      '/assets/characters/' + fileName + '.glb',
      function(gltf) {
        var model = gltf.scene;

        // Force world matrix update before computing bounds
        model.updateMatrixWorld(true);

        // Compute bounding box and auto-scale to target height
        var box = new THREE.Box3().setFromObject(model);
        var size = new THREE.Vector3();
        box.getSize(size);
        var targetHeight = 1.35;
        if (size.y < 0.001) { console.warn('Zero height model: ' + agentName); return; }
        var scale = targetHeight / size.y;
        model.scale.setScalar(scale);

        // Place feet on ground: shift by scaled min.y
        var groundY = -(box.min.y * scale);

        // Enable shadows
        model.traverse(function(child) {
          if (child.isMesh) {
            child.castShadow = false; // skinned meshes in the shadow pass are a top frame cost on integrated GPU
            child.receiveShadow = true;
          }
        });

        // Find the existing procedural character group
        var existing = charGroups[agentName];
        if (!existing) return;

        // Position at existing desk X/Z, calculated Y for ground
        model.position.set(existing.position.x, groundY, existing.position.z);
        model.rotation.copy(existing.rotation);

        // Verify model has renderable meshes before swapping
        var hasMeshes = false;
        model.traverse(function(child) { if (child.isMesh) hasMeshes = true; });
        if (!hasMeshes) {
          console.warn('GLTF model has no meshes: ' + agentName + ', keeping procedural');
          return;
        }

        // Transfer CSS2D labels from procedural to GLTF model
        var labelsToMove = [];
        existing.children.forEach(function(child) {
          if (child.isCSS2DObject) labelsToMove.push(child);
        });
        labelsToMove.forEach(function(label) {
          existing.remove(label);
          model.add(label);
        });

        // Store reference to procedural character for fallback
        model.userData.proceduralFallback = existing;

        // Hide procedural character, show GLTF
        existing.visible = false;
        scene.add(model);

        // Replace charGroups reference so walk system moves GLTF model
        charGroups[agentName] = model;

        // Store reference
        model.userData.agentName = agentName;
        model.userData.isGLTF = true;
        model.userData.groundY = groundY;

        // Set up animation mixer — find idle animation
        if (gltf.animations && gltf.animations.length > 0) {
          var mixer = new THREE.AnimationMixer(model);
          var idleClip = null;
          // Priority 1: Find sitting animation
          for (var ai = 0; ai < gltf.animations.length; ai++) {
            var cn = gltf.animations[ai].name.toLowerCase();
            if (cn.indexOf('sitting') !== -1 || cn.indexOf('sit') !== -1) {
              idleClip = gltf.animations[ai];
              break;
            }
          }
          // Priority 2: Find neutral idle (not gun/sword)
          if (!idleClip) {
            for (var ai2 = 0; ai2 < gltf.animations.length; ai2++) {
              var cn2 = gltf.animations[ai2].name.toLowerCase();
              if ((cn2.indexOf('idle') !== -1 || cn2.indexOf('neutral') !== -1) && cn2.indexOf('gun') === -1 && cn2.indexOf('sword') === -1) {
                idleClip = gltf.animations[ai2];
                break;
              }
            }
          }
          if (!idleClip) idleClip = gltf.animations[0];
          // Find walk clip too
          var walkClip = null;
          for (var wi = 0; wi < gltf.animations.length; wi++) {
            var wn = gltf.animations[wi].name.toLowerCase();
            if (wn.indexOf('walk') !== -1 && wn.indexOf('run') === -1) {
              walkClip = gltf.animations[wi];
              break;
            }
          }
          model.userData.walkClip = walkClip;
          model.userData.idleClip = idleClip;
          var action = mixer.clipAction(idleClip);
          action.play();
          model.userData.mixer = mixer;
          model.userData.allClips = gltf.animations;
          console.log('GLTF ' + agentName + ': scale=' + scale.toFixed(3) + ' height=' + size.y.toFixed(2) + ' clip=' + idleClip.name);
        }
      },
      undefined,
      function(err) {
        console.warn('Failed to load GLTF for ' + agentName + ', procedural character remains visible');
        // Ensure procedural character stays visible as fallback
        var fallback = charGroups[agentName];
        if (fallback) fallback.visible = true;
      }
    );
  });
})();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence request logs

    def do_GET(self):
        path = self.path.split("?", 1)[0]  # ignore query string (e.g. ?hour= debug param)
        if path == "/api/data":
            data = _build_api_response()
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/" or path == "/index.html":
            body = HTML_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/jonas_avatar.jpg":
            try:
                with open("jonas_avatar.jpg", "rb") as f:
                    img = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                self.wfile.write(img)
            except Exception:
                self.send_response(404)
                self.end_headers()
        elif path.startswith("/assets/"):
            # Static file serving with path traversal protection
            rel_path = path[len("/assets/"):]
            if ".." in rel_path or rel_path.startswith("/"):
                self.send_response(403)
                self.end_headers()
                return
            file_path = os.path.join(ASSET_DIR, rel_path)
            real_path = os.path.realpath(file_path)
            if not real_path.startswith(os.path.realpath(ASSET_DIR)):
                self.send_response(403)
                self.end_headers()
                return
            if not os.path.isfile(real_path):
                self.send_response(404)
                self.end_headers()
                return
            import mimetypes
            ext = os.path.splitext(real_path)[1].lower()
            content_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(real_path)[0] or "application/octet-stream"
            try:
                with open(real_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Trading Desk running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
