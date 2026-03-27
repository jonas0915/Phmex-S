"""
Phmex-S Animated Trading Desk — Sims-style isometric trading floor with live bot data.
Standalone process — reads trading_state.json + bot.log only.
Zero bot imports, zero API calls.
"""
import json
import os
import re
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from html import escape

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MIME_OVERRIDES = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".hdr": "application/octet-stream",
}

LOG_FILE = "logs/bot.log"
STATE_FILE = "trading_state.json"
HOST, PORT = "127.0.0.1", 8060


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
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_trades = [t for t in all_trades if t.get("closed_at", 0) >= today_start]
    today_pnl = sum(t.get("pnl_usdt", 0) for t in today_trades)
    today_count = len(today_trades)
    today_wins = sum(1 for t in today_trades if t.get("pnl_usdt", 0) > 0)
    today_wr = (today_wins / today_count * 100) if today_count > 0 else 0

    # Per-pair PnL (top 5 by absolute PnL)
    pair_pnl = {}
    for t in all_trades:
        sym = t.get("symbol", "?").replace("/USDT:USDT", "")
        pair_pnl[sym] = pair_pnl.get(sym, 0) + t.get("pnl_usdt", 0)
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
    wins = [t.get("pnl_usdt", 0) for t in all_trades if t.get("pnl_usdt", 0) > 0]
    losses = [t.get("pnl_usdt", 0) for t in all_trades if t.get("pnl_usdt", 0) < 0]
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
        if t.get("pnl_usdt", 0) > 0:
            strat_stats[s]["wins"] += 1
        strat_stats[s]["pnl"] += t.get("pnl_usdt", 0)
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
        exit_reasons[r]["pnl"] += t.get("pnl_usdt", 0)
    for r in exit_reasons:
        exit_reasons[r]["pnl"] = round(exit_reasons[r]["pnl"], 2)

    # Paper slot data
    paper_state_file = os.path.join(os.path.dirname(__file__), "trading_state_5m_sma_vwap.json")
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
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { SMAAPass } from 'three/addons/postprocessing/SMAAPass.js';
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
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
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

// ── POST-PROCESSING (HDR BLOOM) ──
const composer = new EffectComposer(renderer);
// RenderPass added after scene/camera init (below)

// ── TIME OF DAY ──
let currentHour = new Date().getHours() + new Date().getMinutes()/60;
let lastTimeUpdate = 0;
const panPlaneMeshes = {}; // store references for texture updates

function getTimeOfDay() {
  const d = new Date();
  return d.getHours() + d.getMinutes()/60;
}

// ── SCENE ──
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x88bbdd);
scene.fog = new THREE.FogExp2(0x9ab5cc, 0.0003);

// ── CAMERA ──
const camera = new THREE.PerspectiveCamera(50, window.innerWidth/window.innerHeight, 0.5, 2000);
camera.position.set(2, 6, 9);
camera.lookAt(0, 0.5, 0);

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
controls.target.set(0, 0, 0);
controls.zoomSpeed = 1.2;

// ── Right-click drag to move orbit target freely ──
// Middle-click or Ctrl+left-click pans (default OrbitControls)
// Double-click to reset view
renderer.domElement.addEventListener('dblclick', () => {
  controls.target.set(0, 0, 0);
  camera.position.set(2, 6, 9);
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

// ── SF PANORAMA TEXTURE — time-synced, photorealistic 2K resolution ──
function createSFPanorama(facing, hour) {
  if(hour === undefined) hour = getTimeOfDay();
  const c = document.createElement('canvas');
  c.width = 2048; c.height = 768;
  const W = 2048, H = 768;
  const ctx = c.getContext('2d');

  // Lerp hex colors helper
  function lc(a, b, t) {
    const pa = [parseInt(a.slice(1,3),16),parseInt(a.slice(3,5),16),parseInt(a.slice(5,7),16)];
    const pb = [parseInt(b.slice(1,3),16),parseInt(b.slice(3,5),16),parseInt(b.slice(5,7),16)];
    const r = Math.round(pa[0]+(pb[0]-pa[0])*t);
    const g2 = Math.round(pa[1]+(pb[1]-pa[1])*t);
    const b2 = Math.round(pa[2]+(pb[2]-pa[2])*t);
    return `#${r.toString(16).padStart(2,'0')}${g2.toString(16).padStart(2,'0')}${b2.toString(16).padStart(2,'0')}`;
  }

  // Parse hex to [r,g,b]
  function parseHex(hex) {
    return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
  }

  // Draw a photorealistic building with glass curtain wall, setbacks, rooftop
  function drawBuilding(bx, by, bw, bh, opts) {
    const depth = opts.depth || 0; // 0=near, 1=mid, 2=far
    const hazeAlpha = depth === 2 ? 0.35 : depth === 1 ? 0.15 : 0;
    const detailLevel = depth === 2 ? 0 : depth === 1 ? 1 : 2;

    // Base building color — glass/steel/concrete tones, atmospheric fade for distance
    const baseColors = isDaytime
      ? ['#7088aa','#6880a0','#8098bb','#5a7898','#90a8c5','#7590b0','#6078a0','#506888','#6a88aa','#7898b8',
         '#5e78a0','#88a0c0','#4a6888','#a0b0cc','#6888a8','#506888','#8aa0c0',
         '#7898b0','#6888a5','#90a8c0','#5878a0','#8098b0','#7090a8','#5a7898','#88a0b8',
         '#6080a0','#a8b8d0','#507090','#98b0c8','#6888a0','#b0c0d8','#5878a0']
      : ['#1a2535','#1e2840','#222d3d','#162030','#253545','#1d2838','#152535','#0e1a28','#1b2230','#202a3a',
         '#18222e','#252e3e','#0c1520','#1f2938','#2a3040',
         '#141e2c','#1c2638','#20283a','#0f1825','#222a38','#182234','#121c2a','#262e40'];
    const baseColor = baseColors[Math.floor(Math.random()*baseColors.length)];
    const [br,bg,bb] = parseHex(baseColor);

    // Atmospheric perspective — blend toward sky color at distance
    const [sr,sg2,sb] = isDaytime ? [136,153,180] : [20,30,50];
    const ar = Math.round(br + (sr-br)*hazeAlpha);
    const ag = Math.round(bg + (sg2-bg)*hazeAlpha);
    const ab = Math.round(bb + (sb-bb)*hazeAlpha);

    // Glass tint variation — some buildings have green, bronze, or warm blue tints
    const tintRoll = Math.random();
    var tintR=0, tintG=0, tintB=0;
    if(isDaytime && depth < 2) {
      if(tintRoll < 0.12) { tintR=-6; tintG=4; tintB=8; } // cool blue glass
      else if(tintRoll < 0.22) { tintR=-10; tintG=-2; tintB=15; } // deep blue glass
      else if(tintRoll < 0.30) { tintR=-4; tintG=6; tintB=12; } // sky blue glass
      else if(tintRoll < 0.36) { tintR=5; tintG=3; tintB=-4; } // subtle bronze
      else if(tintRoll < 0.42) { tintR=-8; tintG=8; tintB=2; } // green tint
    }

    // Building body with vertical gradient (lighter at top = sky reflection)
    const bG = ctx.createLinearGradient(bx, by-bh, bx, by);
    const topTint = isDaytime ? 25 : 8;
    bG.addColorStop(0, `rgb(${Math.min(255,ar+topTint+tintR)},${Math.min(255,ag+topTint+tintG)},${Math.min(255,ab+topTint+tintB)})`);
    bG.addColorStop(0.3, `rgb(${ar+tintR},${ag+tintG},${ab+tintB})`);
    bG.addColorStop(0.7, `rgb(${ar},${ag},${ab})`);
    bG.addColorStop(1, `rgb(${Math.max(0,ar-12)},${Math.max(0,ag-12)},${Math.max(0,ab-12)})`);
    ctx.fillStyle = bG;
    ctx.fillRect(bx, by-bh, bw, bh);

    // Glass curtain wall reflection bands (vertical light streaks)
    if(detailLevel >= 1 && bw > 8) {
      const bandCount = Math.floor(bw / 5) + 1;
      for(let i = 0; i < bandCount; i++) {
        const bandX = bx + bw * 0.1 + (bw * 0.8 * i / Math.max(bandCount-1,1));
        const bandW = 2 + Math.random() * 4;
        const reflAlpha = isDaytime ? 0.10 + Math.random()*0.08 : 0.04 + Math.random()*0.04;
        const reflG = ctx.createLinearGradient(bandX, by-bh, bandX, by);
        reflG.addColorStop(0, `rgba(${isDaytime?'160,200,245':'90,120,170'},${reflAlpha})`);
        reflG.addColorStop(0.25, `rgba(${isDaytime?'140,185,240':'70,100,150'},${reflAlpha*0.5})`);
        reflG.addColorStop(0.5, `rgba(${isDaytime?'180,215,250':'85,110,160'},${reflAlpha*0.8})`);
        reflG.addColorStop(0.75, `rgba(${isDaytime?'200,225,255':'95,115,165'},${reflAlpha*0.3})`);
        reflG.addColorStop(1, `rgba(${isDaytime?'120,170,220':'50,75,120'},0)`);
        ctx.fillStyle = reflG;
        ctx.fillRect(bandX-bandW/2, by-bh, bandW, bh);
      }
      // Cyan sky reflection patch on glass buildings (daytime)
      if(isDaytime && Math.random() > 0.4) {
        const patchY = by - bh*0.3 - Math.random()*bh*0.4;
        ctx.fillStyle = `rgba(120,200,240,${0.05+Math.random()*0.06})`;
        ctx.fillRect(bx+bw*0.1, patchY, bw*0.8, bh*0.12);
      }
    }

    // Horizontal floor lines (glass panels)
    if(detailLevel >= 1 && bh > 12) {
      const floorSpacing = isDaytime ? 3 + Math.random() : 4 + Math.random()*2;
      ctx.strokeStyle = isDaytime ? `rgba(60,70,80,0.15)` : `rgba(10,15,25,0.25)`;
      ctx.lineWidth = 0.5;
      for(let fy = by - bh + floorSpacing; fy < by - 2; fy += floorSpacing) {
        ctx.beginPath(); ctx.moveTo(bx, fy); ctx.lineTo(bx+bw, fy); ctx.stroke();
      }
    }

    // Windows — varied patterns (grid, bands, or scattered)
    if(detailLevel >= 1) {
      const winPattern = Math.random(); // 0-0.4: grid, 0.4-0.7: horizontal bands, 0.7-1: mixed
      const wSpacingX = detailLevel >= 2 ? (2.5 + Math.random()*1.5) : (4 + Math.random()*2);
      const wSpacingY = detailLevel >= 2 ? (3 + Math.random()*1.5) : (4.5 + Math.random()*1.5);
      const wW = detailLevel >= 2 ? (1.5 + Math.random()*1) : (1.2 + Math.random()*0.8);
      const wH = detailLevel >= 2 ? (1.8 + Math.random()*0.8) : (1.5 + Math.random()*0.7);
      const skipRate = depth === 1 ? 0.45 : 0.25;
      for(let wy = by-bh+3; wy < by-2; wy += wSpacingY) {
        const rowLit = winPattern > 0.4 && winPattern < 0.7 && Math.random() > 0.6; // entire floor lit
        for(let wx = bx+2; wx < bx+bw-2; wx += wSpacingX) {
          if(Math.random() < skipRate) continue;
          const isLit = rowLit || Math.random() > (isDaytime ? 0.60 : 0.18);
          if(isLit) {
            const warmth = Math.random();
            const coolWin = !isDaytime && Math.random() > 0.85;
            const blueWin = isDaytime && Math.random() > 0.92; // reflected sky
            const wr = coolWin ? 180+Math.floor(Math.random()*40) : blueWin ? 140+Math.floor(Math.random()*30) : 255;
            const wg = coolWin ? 200+Math.floor(Math.random()*40) : blueWin ? 180+Math.floor(Math.random()*40) : Math.floor(200 + warmth*55);
            const wbl = coolWin ? 235+Math.floor(Math.random()*20) : blueWin ? 230+Math.floor(Math.random()*25) : Math.floor(60 + warmth*100 + (isDaytime ? 80 : 0));
            const wa = isDaytime ? 0.15+Math.random()*0.20 : 0.4+Math.random()*0.55;
            ctx.fillStyle = `rgba(${wr},${wg},${wbl},${wa})`;
          } else {
            ctx.fillStyle = isDaytime
              ? `rgba(${120+Math.random()*40},${145+Math.random()*40},${185+Math.random()*40},0.12)`
              : `rgba(15,25,45,0.20)`;
          }
          ctx.fillRect(wx, wy, wW, wH);
        }
      }
    }

    // Setback (stepped top) for tall buildings
    if(opts.setback && bh > 40) {
      const setH = bh * 0.15;
      const setW = bw * 0.7;
      const setX = bx + (bw - setW)/2;
      ctx.fillStyle = `rgb(${Math.min(255,ar+15)},${Math.min(255,ag+15)},${Math.min(255,ab+15)})`;
      ctx.fillRect(setX, by-bh-setH, setW, setH);
    }

    // Rooftop equipment (AC units, water towers, antennas, mechanical penthouses)
    if(detailLevel >= 2 && bh > 20 && Math.random() > 0.30) {
      const roofType = Math.random();
      ctx.fillStyle = isDaytime ? '#667788' : '#2a3545';
      if(roofType < 0.35) {
        // AC units cluster
        const acCount = 2 + Math.floor(Math.random()*3);
        for(let ac = 0; ac < acCount; ac++) {
          const acx = bx + bw*0.12 + Math.random()*bw*0.65;
          const acw = 3+Math.random()*4;
          const ach = 2+Math.random()*2;
          ctx.fillRect(acx, by-bh-2-Math.random()*2, acw, ach);
          if(detailLevel >= 2) {
            ctx.fillStyle = isDaytime ? '#778899' : '#354050';
            ctx.fillRect(acx+1, by-bh-2.5-Math.random()*2, acw-2, 0.8);
            ctx.fillStyle = isDaytime ? '#667788' : '#2a3545';
          }
        }
      } else if(roofType < 0.55) {
        // Water tower (cylindrical body + conical roof)
        const wtx = bx + bw*0.25 + Math.random()*bw*0.3;
        const wtw = 4 + Math.random()*3;
        const wth = 5 + Math.random()*4;
        ctx.strokeStyle = isDaytime ? '#778899' : '#3a4555';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(wtx+1, by-bh); ctx.lineTo(wtx+2, by-bh-wth+1); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(wtx+wtw-1, by-bh); ctx.lineTo(wtx+wtw-2, by-bh-wth+1); ctx.stroke();
        ctx.fillStyle = isDaytime ? '#6a7a8a' : '#2a3540';
        ctx.fillRect(wtx, by-bh-wth, wtw, wth*0.7);
        ctx.fillStyle = isDaytime ? '#5a6a7a' : '#1a2530';
        ctx.beginPath();
        ctx.moveTo(wtx-1, by-bh-wth);
        ctx.lineTo(wtx+wtw/2, by-bh-wth-3);
        ctx.lineTo(wtx+wtw+1, by-bh-wth);
        ctx.closePath(); ctx.fill();
      } else if(roofType < 0.7 && bw > 12) {
        // Mechanical penthouse (enclosed box)
        const phw = bw * 0.4;
        const phh = 3 + Math.random()*2;
        const phx = bx + (bw-phw)/2;
        ctx.fillStyle = isDaytime ? '#5a6878' : '#222c38';
        ctx.fillRect(phx, by-bh-phh, phw, phh);
        ctx.fillStyle = isDaytime ? '#4a5868' : '#1a222e';
        ctx.fillRect(phx, by-bh-phh, phw, 1);
      }
      // Antenna (on any rooftop type for tall buildings)
      if(bh > 35 && Math.random() > 0.35) {
        ctx.strokeStyle = isDaytime ? '#8899aa' : '#556677';
        ctx.lineWidth = 1;
        const antX = bx + bw*0.3 + Math.random()*bw*0.4;
        const antH = 8+Math.random()*12;
        ctx.beginPath(); ctx.moveTo(antX, by-bh); ctx.lineTo(antX, by-bh-antH); ctx.stroke();
        if(Math.random() > 0.5) {
          const armY = by-bh-antH*0.6;
          ctx.beginPath(); ctx.moveTo(antX-2, armY); ctx.lineTo(antX+2, armY); ctx.stroke();
        }
        ctx.fillStyle = '#ff3333';
        ctx.beginPath(); ctx.arc(antX, by-bh-antH-1, 1.5, 0, Math.PI*2); ctx.fill();
        if(!isDaytime) {
          ctx.fillStyle = 'rgba(255,50,50,0.18)';
          ctx.beginPath(); ctx.arc(antX, by-bh-antH-1, 6, 0, Math.PI*2); ctx.fill();
        }
      }
    }

    // Edge highlight (sun-facing side)
    if(detailLevel >= 1 && isDaytime) {
      ctx.fillStyle = 'rgba(200,215,235,0.15)';
      ctx.fillRect(bx, by-bh, 2, bh);
    }
    // Opposite edge shadow for depth
    if(detailLevel >= 1) {
      ctx.fillStyle = isDaytime ? 'rgba(30,40,60,0.08)' : 'rgba(0,0,0,0.12)';
      ctx.fillRect(bx+bw-2, by-bh, 2, bh);
    }
  }

  // ── Time-based color palette ──
  // 0-5: night, 5-7: dawn, 7-10: morning, 10-16: day, 16-18.5: golden hour, 18.5-20: dusk, 20-24: night
  let skyTop, skyMid, skyLow, skyHorizon, horizonGlow, starAlpha, windowBright, waterTop, waterBot;
  const h = ((hour % 24) + 24) % 24;

  if(h >= 21 || h < 5) {
    // Deep night
    skyTop='#050810'; skyMid='#0a1428'; skyLow='#101c38'; skyHorizon='#1a2545';
    horizonGlow='rgba(40,60,120,0.15)'; starAlpha=1.0; windowBright=0.85;
    waterTop='#0a1530'; waterBot='#060e20';
  } else if(h >= 5 && h < 6.5) {
    // Dawn — deep blue to pink/orange
    const t = (h-5)/1.5;
    skyTop=lc('#050810','#1a1535',t); skyMid=lc('#0a1428','#2a2050',t);
    skyLow=lc('#101c38','#6a4060',t); skyHorizon=lc('#1a2545','#ee8855',t);
    horizonGlow=`rgba(255,${Math.floor(100+t*80)},${Math.floor(40+t*40)},${0.1+t*0.3})`;
    starAlpha=1.0-t*0.8; windowBright=0.7-t*0.3;
    waterTop=lc('#0a1530','#2a3050',t); waterBot=lc('#060e20','#1a2540',t);
  } else if(h >= 6.5 && h < 8) {
    // Sunrise — warm golden
    const t = (h-6.5)/1.5;
    skyTop=lc('#1a1535','#3a5580',t); skyMid=lc('#2a2050','#5580aa',t);
    skyLow=lc('#6a4060','#88aabb',t); skyHorizon=lc('#ee8855','#ffcc88',t);
    horizonGlow=`rgba(255,${Math.floor(180-t*60)},${Math.floor(80+t*40)},${0.4-t*0.2})`;
    starAlpha=0.2-t*0.2; windowBright=0.35-t*0.1;
    waterTop=lc('#2a3050','#4a6888',t); waterBot=lc('#1a2540','#3a5570',t);
  } else if(h >= 8 && h < 11) {
    // Morning — clear blue
    const t = (h-8)/3;
    skyTop=lc('#3a5580','#2266bb',t); skyMid=lc('#5580aa','#55aadd',t);
    skyLow=lc('#88aabb','#88ccee',t); skyHorizon=lc('#ffcc88','#aaddee',t);
    horizonGlow='rgba(200,220,255,0.1)'; starAlpha=0; windowBright=0.15;
    waterTop=lc('#4a6888','#4488bb',t); waterBot=lc('#3a5570','#3a7099',t);
  } else if(h >= 11 && h < 16) {
    // Midday — bright blue
    skyTop='#1155aa'; skyMid='#3399dd'; skyLow='#66bbee'; skyHorizon='#99ddff';
    horizonGlow='rgba(200,230,255,0.08)'; starAlpha=0; windowBright=0.1;
    waterTop='#3388bb'; waterBot='#2a6699';
  } else if(h >= 16 && h < 18.5) {
    // Golden hour — warm
    const t = (h-16)/2.5;
    skyTop=lc('#1155aa','#1a2550',t); skyMid=lc('#3399dd','#4a5580',t);
    skyLow=lc('#66bbee','#886655',t); skyHorizon=lc('#99ddff','#ee8844',t);
    horizonGlow=`rgba(255,${Math.floor(150+t*60)},${Math.floor(50+t*30)},${0.08+t*0.3})`;
    starAlpha=t*0.3; windowBright=0.15+t*0.5;
    waterTop=lc('#3388bb','#3a4555',t); waterBot=lc('#2a6699','#2a3548',t);
  } else if(h >= 18.5 && h < 21) {
    // Dusk — purple/blue transition
    const t = (h-18.5)/2.5;
    skyTop=lc('#1a2550','#0c1528',t); skyMid=lc('#4a5580','#152040',t);
    skyLow=lc('#886655','#253050',t); skyHorizon=lc('#ee8844','#2a3555',t);
    horizonGlow=`rgba(200,${Math.floor(120-t*80)},${Math.floor(80-t*40)},${0.35-t*0.25})`;
    starAlpha=0.3+t*0.7; windowBright=0.65+t*0.2;
    waterTop=lc('#3a4555','#0a1530',t); waterBot=lc('#2a3548','#060e20',t);
  }

  // Sky gradient — extra stops for smoother atmospheric transition
  const skyG = ctx.createLinearGradient(0,0,0,H*0.73);
  skyG.addColorStop(0, skyTop);
  skyG.addColorStop(0.15, lc(skyTop, skyMid, 0.4));
  skyG.addColorStop(0.35, skyMid);
  skyG.addColorStop(0.55, lc(skyMid, skyLow, 0.5));
  skyG.addColorStop(0.72, skyLow);
  skyG.addColorStop(0.88, lc(skyLow, skyHorizon, 0.6));
  skyG.addColorStop(1.0, skyHorizon);
  ctx.fillStyle = skyG;
  ctx.fillRect(0,0,W,H);

  // Horizon glow
  const glowG = ctx.createRadialGradient(W/2, H*0.73, 50, W/2, H*0.73, W*0.5);
  glowG.addColorStop(0, horizonGlow);
  glowG.addColorStop(0.6, horizonGlow.replace(/[\d.]+\)$/, '0)'));
  glowG.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = glowG;
  ctx.fillRect(0,0,W,H);

  // Sun/moon
  if(h >= 6 && h < 18.5) {
    // Sun position based on time
    const sunProgress = (h-6)/12.5; // 0=sunrise east, 0.5=noon, 1=sunset west
    const sunX = W * (0.1 + sunProgress*0.8);
    const sunY = H*0.73 - Math.sin(sunProgress*Math.PI)*H*0.5;
    const sunSize = h>7&&h<17 ? 20 : 25;
    const sunColor = h<8||h>16.5 ? '#ffaa44' : '#ffffcc';
    ctx.fillStyle = sunColor;
    ctx.beginPath(); ctx.arc(sunX, sunY, sunSize, 0, Math.PI*2); ctx.fill();
    // Sun glow
    const sg = ctx.createRadialGradient(sunX,sunY,sunSize,sunX,sunY,sunSize*4);
    sg.addColorStop(0, h<8||h>16.5 ? 'rgba(255,180,80,0.3)' : 'rgba(255,255,200,0.15)');
    sg.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = sg; ctx.fillRect(0,0,W,H);
  } else if(starAlpha > 0.3) {
    // Moon
    const moonX = W*0.75; const moonY = H*0.15;
    ctx.fillStyle = `rgba(220,225,240,${starAlpha*0.9})`;
    ctx.beginPath(); ctx.arc(moonX, moonY, 12, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = `rgba(200,210,230,${starAlpha*0.1})`;
    ctx.beginPath(); ctx.arc(moonX, moonY, 30, 0, Math.PI*2); ctx.fill();
  }

  // Stars
  if(starAlpha > 0.05) {
    for(let i=0;i<150;i++){
      const sy = Math.random()*H*0.4;
      const a = (0.3+Math.random()*0.7) * starAlpha;
      ctx.fillStyle = `rgba(255,255,${220+Math.random()*35},${a})`;
      const s = Math.random()>0.92 ? 3 : Math.random()>0.7 ? 2 : 1;
      ctx.fillRect(Math.random()*W, sy, s, s);
    }
  }

  // Clouds (subtle, time-tinted)
  if(h >= 6 && h < 20) {
    const cloudAlpha = 0.06 + (h>16 ? 0.08 : 0);
    for(let i=0;i<8;i++){
      const cx = Math.random()*W;
      const cy = H*0.15 + Math.random()*H*0.25;
      const cw = 60+Math.random()*120;
      const cloudColor = h>16.5 ? `rgba(255,180,120,${cloudAlpha})` : `rgba(255,255,255,${cloudAlpha})`;
      ctx.fillStyle = cloudColor;
      ctx.beginPath();
      ctx.ellipse(cx, cy, cw, 8+Math.random()*12, 0, 0, Math.PI*2);
      ctx.fill();
    }
  }

  // Bay water
  const waterY = Math.floor(H*0.73);
  const waterG2 = ctx.createLinearGradient(0,waterY,0,H);
  waterG2.addColorStop(0, waterTop);
  waterG2.addColorStop(1, waterBot);
  ctx.fillStyle = waterG2;
  ctx.fillRect(0, waterY, W, H-waterY);

  // Water reflections — color depends on sky
  const isGolden = h >= 16 && h < 20;
  const isDaytime = h >= 7 && h < 17;
  for(let i=0;i<200;i++){
    const rx = Math.random()*W;
    const ry = waterY+4+Math.random()*(H-waterY-8);
    const rw = 4+Math.random()*40;
    if(isGolden) {
      ctx.fillStyle = `rgba(255,${150+Math.random()*80},${40+Math.random()*60},${0.06+Math.random()*0.15})`;
    } else if(isDaytime) {
      ctx.fillStyle = `rgba(${120+Math.random()*60},${180+Math.random()*60},${220+Math.random()*35},${0.05+Math.random()*0.1})`;
    } else {
      ctx.fillStyle = `rgba(${60+Math.random()*60},${80+Math.random()*60},${140+Math.random()*60},${0.04+Math.random()*0.1})`;
    }
    ctx.fillRect(rx, ry, rw, 1);
  }
  // Shimmer streaks
  for(let i=0;i<40;i++){
    const shimColor = isGolden ? `rgba(255,${200+Math.random()*55},${120+Math.random()*80},${0.1+Math.random()*0.2})`
      : isDaytime ? `rgba(200,230,255,${0.08+Math.random()*0.12})`
      : `rgba(${150+Math.random()*60},${170+Math.random()*50},${200+Math.random()*55},${0.06+Math.random()*0.12})`;
    ctx.fillStyle = shimColor;
    ctx.fillRect(W*0.2+Math.random()*W*0.6, waterY+10+Math.random()*(H-waterY-30), 3+Math.random()*12, 1);
  }

  // Window brightness for buildings
  const wb = windowBright;

  // Scale factor for coordinates
  const S = 2;
  const landY = waterY; // where land meets water

  if(facing === 'north') {
    // ── NORTH — SF Bay, Coit Tower, Alcatraz, Angel Island, Marin hills, piers ──

    // Marin headlands — multi-ridge (far left, strong haze)
    ctx.fillStyle = isDaytime ? '#6a8a60' : '#1a2820';
    ctx.globalAlpha = isDaytime ? 0.45 : 0.6;
    ctx.beginPath(); ctx.moveTo(0, landY);
    ctx.quadraticCurveTo(80*S, landY-38*S, 180*S, landY-20*S);
    ctx.quadraticCurveTo(220*S, landY-30*S, 280*S, landY-8*S);
    ctx.lineTo(280*S, landY); ctx.fill();
    ctx.globalAlpha = 1;
    // Second Marin ridge (fainter, behind)
    ctx.fillStyle = isDaytime ? 'rgba(100,140,95,0.3)' : 'rgba(12,22,18,0.4)';
    ctx.beginPath(); ctx.moveTo(0, landY-5*S);
    ctx.quadraticCurveTo(60*S, landY-45*S, 150*S, landY-28*S);
    ctx.quadraticCurveTo(200*S, landY-35*S, 300*S, landY-10*S);
    ctx.lineTo(300*S, landY); ctx.lineTo(0, landY); ctx.fill();

    // Golden Gate Bridge (visible far left, behind headlands — international orange)
    {
      const ggO = isDaytime ? '#c04030' : '#8a2a1e';
      // Distant towers (small due to distance)
      ctx.fillStyle = ggO;
      ctx.fillRect(55*S, landY-38*S, 4*S, 28*S);
      ctx.fillRect(115*S, landY-35*S, 4*S, 25*S);
      // Deck
      ctx.fillRect(35*S, landY-12*S, 100*S, 2.5*S);
      // Main cable catenary
      ctx.strokeStyle = ggO; ctx.lineWidth = 1.5*S;
      ctx.beginPath();
      const ggNmid = 87*S;
      for(let x=57*S; x<=117*S; x+=2*S) {
        const sag = Math.pow((x-ggNmid)/(30*S),2)*12*S;
        ctx.lineTo(x, landY-30*S+sag);
      }
      ctx.stroke();
      // Suspender cables
      ctx.lineWidth = S*0.3;
      for(let x=62*S; x<115*S; x+=5*S) {
        const sag = Math.pow((x-ggNmid)/(30*S),2)*12*S;
        ctx.beginPath(); ctx.moveTo(x, landY-30*S+sag); ctx.lineTo(x, landY-12*S); ctx.stroke();
      }
      // Aviation lights
      ctx.fillStyle = '#ff3333';
      ctx.beginPath(); ctx.arc(57*S, landY-39*S, 1.5*S, 0, Math.PI*2); ctx.fill();
      ctx.beginPath(); ctx.arc(117*S, landY-36*S, 1.5*S, 0, Math.PI*2); ctx.fill();
    }

    // Tiburon Peninsula (behind Angel Island, green hills)
    ctx.fillStyle = isDaytime ? 'rgba(90,120,80,0.4)' : 'rgba(15,25,20,0.55)';
    ctx.beginPath(); ctx.moveTo(400*S, landY-1*S); ctx.quadraticCurveTo(520*S, landY-28*S, 700*S, landY-1*S); ctx.fill();

    // Angel Island (solid with atmospheric fade)
    ctx.fillStyle = isDaytime ? '#7a9a78' : '#152025';
    ctx.globalAlpha = isDaytime ? 0.6 : 0.75;
    ctx.beginPath(); ctx.moveTo(520*S, landY-2*S); ctx.quadraticCurveTo(640*S, landY-40*S, 780*S, landY-2*S); ctx.fill();
    ctx.globalAlpha = 1;
    if(isDaytime) {
      ctx.fillStyle = 'rgba(160,185,210,0.2)';
      ctx.beginPath(); ctx.moveTo(520*S, landY-2*S); ctx.quadraticCurveTo(640*S, landY-40*S, 780*S, landY-2*S); ctx.fill();
    }

    // Telegraph Hill with Coit Tower (left-center)
    ctx.fillStyle = isDaytime ? '#5a7a50' : '#1a2a20';
    ctx.beginPath();
    ctx.moveTo(250*S, landY); ctx.quadraticCurveTo(330*S, landY-55*S, 420*S, landY); ctx.fill();
    // Hill texture — trees
    if(isDaytime) {
      for(let tx=260*S; tx<410*S; tx+=4+Math.random()*6) {
        const hillY = landY - 55*S * (1 - Math.pow((tx-335*S)/(85*S), 2));
        if(hillY < landY) {
          ctx.fillStyle = `rgb(${60+Math.random()*30},${90+Math.random()*30},${50+Math.random()*20})`;
          ctx.beginPath(); ctx.arc(tx, hillY+Math.random()*10, 2+Math.random()*3, 0, Math.PI*2); ctx.fill();
        }
      }
    }
    // Coit Tower (white cylindrical tower)
    ctx.fillStyle = isDaytime ? '#e0ddd5' : '#7a7a80';
    ctx.fillRect(325*S, landY-65*S, 10*S, 25*S);
    ctx.beginPath(); ctx.arc(330*S, landY-65*S, 5*S, Math.PI, 0); ctx.fill();
    // Coit Tower observation columns
    if(isDaytime) {
      ctx.fillStyle = '#d5d0c8';
      for(let cx=326*S; cx<335*S; cx+=2.5*S) {
        ctx.fillRect(cx, landY-63*S, S*0.8, 18*S);
      }
    }

    // Embarcadero mid-ground buildings (depth 1, fill gaps)
    for(let x=0; x<W; x+=12*S+Math.random()*10*S) {
      drawBuilding(x, landY, (6+Math.random()*8)*S, (8+Math.random()*15)*S, {depth:1});
    }
    // Low waterfront buildings (Fisherman's Wharf) — foreground layer
    for(let x=0; x<W; x+=15*S+Math.random()*12*S) {
      drawBuilding(x, landY, (8+Math.random()*14)*S, (4+Math.random()*10)*S, {depth:0});
    }
    // Pier structures (more piers)
    for(let i=0;i<8;i++){
      const px = (50+i*110+Math.random()*25)*S;
      ctx.fillStyle = isDaytime ? '#9a9888' : '#2a2a30';
      ctx.fillRect(px, landY-5*S, 28*S, 5*S);
      ctx.fillStyle = isDaytime ? '#8a8878' : '#252530';
      ctx.fillRect(px+3*S, landY-10*S, 22*S, 5*S);
      // Pier number sign
      if(isDaytime) { ctx.fillStyle = '#bb4422'; ctx.fillRect(px+10*S, landY-12*S, 4*S, 2*S); }
    }

    // Alcatraz Island (more prominent silhouette)
    ctx.fillStyle = isDaytime ? '#6a7a60' : '#1a2530';
    ctx.beginPath(); ctx.moveTo(560*S, landY-3*S); ctx.quadraticCurveTo(630*S, landY-25*S, 720*S, landY-3*S); ctx.fill();
    // Rocky shoreline detail
    ctx.fillStyle = isDaytime ? '#8a9080' : '#2a3530';
    ctx.beginPath(); ctx.moveTo(565*S, landY-2*S); ctx.quadraticCurveTo(585*S, landY-6*S, 600*S, landY-3*S); ctx.fill();
    // Alcatraz main cellhouse
    ctx.fillStyle = isDaytime ? '#7a7580' : '#2a3540';
    ctx.fillRect(600*S, landY-18*S, 30*S, 15*S);
    // Warden house
    ctx.fillRect(615*S, landY-23*S, 10*S, 5*S);
    // Water tower
    ctx.fillStyle = isDaytime ? '#8a8580' : '#3a4550';
    ctx.fillRect(645*S, landY-15*S, 15*S, 12*S);
    ctx.fillRect(650*S, landY-20*S, 5*S, 5*S);
    // Alcatraz lighthouse
    ctx.fillStyle = '#ccccaa'; ctx.fillRect(632*S, landY-30*S, 3*S, 12*S);
    ctx.fillStyle = '#ffee88'; ctx.beginPath(); ctx.arc(633*S, landY-31*S, 4*S, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = 'rgba(255,238,120,0.2)'; ctx.beginPath(); ctx.arc(633*S, landY-31*S, 12*S, 0, Math.PI*2); ctx.fill();

    // Sailboats on the bay (triangular sails)
    for(let i=0; i<6; i++) {
      const bx = 100*S + Math.random()*(W-200*S);
      const byy = landY + 8*S + Math.random()*55*S;
      ctx.fillStyle = isDaytime ? '#ffffff' : '#aaaaaa';
      ctx.fillRect(bx, byy-1.5*S, 4*S, 1.5*S);
      // Sail (triangle, daytime only)
      if(isDaytime) {
        ctx.fillStyle = `rgba(255,255,255,${0.6+Math.random()*0.3})`;
        ctx.beginPath(); ctx.moveTo(bx+2*S, byy-1.5*S); ctx.lineTo(bx+2*S, byy-6*S); ctx.lineTo(bx+4*S, byy-1.5*S); ctx.fill();
      }
      ctx.fillStyle = isDaytime ? 'rgba(200,220,240,0.3)' : 'rgba(100,120,150,0.15)';
      ctx.fillRect(bx-3*S, byy, 10*S, S*0.5);
    }
    // Larger ferries
    for(let i=0; i<3; i++) {
      const bx = 200*S + Math.random()*(W-400*S);
      const byy = landY + 15*S + Math.random()*40*S;
      ctx.fillStyle = isDaytime ? '#eeeeee' : '#888888';
      ctx.fillRect(bx, byy-3*S, 8*S, 3*S);
      ctx.fillStyle = isDaytime ? '#dddddd' : '#777777';
      ctx.fillRect(bx+1*S, byy-5*S, 6*S, 2*S);
      ctx.fillStyle = isDaytime ? 'rgba(200,220,240,0.25)' : 'rgba(100,120,150,0.12)';
      ctx.fillRect(bx-5*S, byy, 16*S, S*0.5);
    }

    // Bay Bridge visible on far right (western span towers + deck + cables)
    const bbColor = isDaytime ? '#b0b8c0' : '#8899aa';
    const bbDark = isDaytime ? '#8a9298' : '#667788';
    // Towers
    ctx.fillStyle = bbColor;
    ctx.fillRect(820*S, landY-48*S, 6*S, 48*S);
    ctx.fillRect(900*S, landY-44*S, 6*S, 44*S);
    // Tower cross-beams
    ctx.fillStyle = bbDark;
    ctx.fillRect(820*S, landY-30*S, 6*S, 3*S);
    ctx.fillRect(900*S, landY-28*S, 6*S, 3*S);
    // Deck
    ctx.fillStyle = bbDark;
    ctx.fillRect(800*S, landY-8*S, 220*S, 5*S);
    ctx.fillStyle = isDaytime ? '#99aabb' : '#778899';
    ctx.fillRect(800*S, landY-8*S, 220*S, 2*S);
    // Main cable catenary between towers
    ctx.strokeStyle = bbColor; ctx.lineWidth = 1.5*S;
    ctx.beginPath();
    for(let x=823*S; x<=903*S; x+=2*S) {
      const mid = 863*S;
      const sag = Math.pow((x-mid)/(40*S),2)*18*S;
      ctx.lineTo(x, landY-38*S+sag);
    }
    ctx.stroke();
    // Vertical suspender cables
    ctx.lineWidth = S*0.4;
    for(let x=828*S; x<900*S; x+=8*S) {
      const mid = 863*S;
      const sag = Math.pow((x-mid)/(40*S),2)*18*S;
      ctx.beginPath(); ctx.moveTo(x, landY-38*S+sag); ctx.lineTo(x, landY-8*S); ctx.stroke();
    }
    // Aviation lights on towers
    ctx.fillStyle = '#ff3333';
    ctx.beginPath(); ctx.arc(823*S, landY-49*S, 2*S, 0, Math.PI*2); ctx.fill();
    ctx.beginPath(); ctx.arc(903*S, landY-45*S, 2*S, 0, Math.PI*2); ctx.fill();
    if(!isDaytime) {
      ctx.fillStyle = 'rgba(255,50,50,0.2)';
      ctx.beginPath(); ctx.arc(823*S, landY-49*S, 6*S, 0, Math.PI*2); ctx.fill();
      ctx.beginPath(); ctx.arc(903*S, landY-45*S, 6*S, 0, Math.PI*2); ctx.fill();
    }
    // Bridge deck lights
    for(let x=805*S; x<1015*S; x+=8*S) {
      ctx.fillStyle = '#ffeeaa'; ctx.fillRect(x, landY-10*S, 1.5*S, 1.5*S);
    }

    // Transamerica Pyramid visible behind waterfront (iconic pointed shape)
    {
      const tpX = 160*S;
      const tpTop = landY - 60*S;
      const tpBase = 8*S;
      const tpG = ctx.createLinearGradient(tpX-tpBase, landY, tpX+tpBase, tpTop);
      if(isDaytime) { tpG.addColorStop(0,'#8898a8'); tpG.addColorStop(1,'#a0b0c0'); }
      else { tpG.addColorStop(0,'#2a3545'); tpG.addColorStop(1,'#3a4a60'); }
      ctx.fillStyle = tpG;
      ctx.beginPath(); ctx.moveTo(tpX-tpBase, landY-10*S); ctx.lineTo(tpX, tpTop); ctx.lineTo(tpX+tpBase, landY-10*S); ctx.fill();
      // Glass reflection streak
      ctx.fillStyle = isDaytime ? 'rgba(200,220,240,0.2)' : 'rgba(100,140,200,0.1)';
      ctx.beginPath(); ctx.moveTo(tpX-1.5*S, landY-10*S); ctx.lineTo(tpX, tpTop); ctx.lineTo(tpX+1.5*S, landY-10*S); ctx.fill();
      // Spire
      ctx.fillStyle = isDaytime ? '#99aabb' : '#667788';
      ctx.fillRect(tpX-S*0.5, tpTop-6*S, S, 6*S);
      ctx.fillStyle = '#ff3333'; ctx.beginPath(); ctx.arc(tpX, tpTop-7*S, 1.5*S, 0, Math.PI*2); ctx.fill();
    }
  }
  else if(facing === 'south') {
    // ── SOUTH — SoMa/Mission neighborhoods, Twin Peaks in background ──

    // Twin Peaks hills (far background with atmospheric fade)
    ctx.fillStyle = isDaytime ? '#8a7a50' : '#3a3528';
    ctx.beginPath();
    ctx.moveTo(250*S, landY-10*S); ctx.quadraticCurveTo(400*S, landY-90*S, 530*S, landY-20*S); ctx.fill();
    ctx.fillStyle = isDaytime ? '#887850' : '#383225';
    ctx.beginPath();
    ctx.moveTo(420*S, landY-15*S); ctx.quadraticCurveTo(540*S, landY-80*S, 680*S, landY-18*S); ctx.fill();
    // Hill texture — California golden grass
    if(isDaytime) {
      for(let tx=280*S; tx<650*S; tx+=3+Math.random()*4) {
        const peakX = tx < 500*S ? 400*S : 540*S;
        const peakH = tx < 500*S ? 90*S : 80*S;
        const dist = Math.abs(tx - peakX) / (130*S);
        if(dist < 1) {
          const hillY = landY - peakH * (1 - dist*dist) + Math.random()*5;
          ctx.fillStyle = `rgb(${120+Math.random()*30},${105+Math.random()*25},${55+Math.random()*20})`;
          ctx.fillRect(tx, hillY, 2, 2);
        }
      }
    }
    // Atmospheric haze over hills
    if(isDaytime) {
      const hazeG = ctx.createLinearGradient(0, landY-90*S, 0, landY-40*S);
      hazeG.addColorStop(0, 'rgba(160,180,210,0.35)');
      hazeG.addColorStop(1, 'rgba(160,180,210,0)');
      ctx.fillStyle = hazeG;
      ctx.fillRect(200*S, landY-90*S, 500*S, 50*S);
    }

    // Sutro Tower (distinctive red/white radio tower)
    ctx.strokeStyle = isDaytime ? '#cc4422' : '#aa3318';
    ctx.lineWidth = 3*S;
    ctx.beginPath(); ctx.moveTo(480*S, landY-70*S); ctx.lineTo(480*S, landY-110*S); ctx.stroke();
    ctx.lineWidth = 2*S;
    // Three sets of crossbars
    ctx.beginPath(); ctx.moveTo(470*S, landY-78*S); ctx.lineTo(480*S, landY-88*S); ctx.lineTo(490*S, landY-78*S); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(472*S, landY-86*S); ctx.lineTo(480*S, landY-95*S); ctx.lineTo(488*S, landY-86*S); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(474*S, landY-93*S); ctx.lineTo(480*S, landY-102*S); ctx.lineTo(486*S, landY-93*S); ctx.stroke();
    // Aviation light
    ctx.fillStyle = '#ff3333'; ctx.beginPath(); ctx.arc(480*S, landY-111*S, 2*S, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = 'rgba(255,50,50,0.2)'; ctx.beginPath(); ctx.arc(480*S, landY-111*S, 6*S, 0, Math.PI*2); ctx.fill();

    // Potrero Hill (right side)
    ctx.fillStyle = isDaytime ? '#7a7a48' : '#2a2a20';
    ctx.beginPath(); ctx.moveTo(750*S, landY-5*S); ctx.quadraticCurveTo(850*S, landY-40*S, 970*S, landY-5*S); ctx.fill();

    // Bernal Heights (rounded hill with bare grassy top)
    ctx.fillStyle = isDaytime ? '#8a8050' : '#2a2820';
    ctx.beginPath(); ctx.moveTo(100*S, landY-5*S); ctx.quadraticCurveTo(180*S, landY-35*S, 270*S, landY-5*S); ctx.fill();
    // Mount Davidson (highest point in SF, has large cross)
    ctx.fillStyle = isDaytime ? '#4a6a40' : '#1a2a18';
    ctx.beginPath(); ctx.moveTo(700*S, landY-10*S); ctx.quadraticCurveTo(780*S, landY-50*S, 860*S, landY-10*S); ctx.fill();
    // Cross on Mount Davidson
    if(isDaytime) {
      ctx.fillStyle = '#ddddcc';
      ctx.fillRect(778*S, landY-60*S, 2*S, 12*S);
      ctx.fillRect(774*S, landY-55*S, 10*S, 2*S);
    }

    // SoMa/Mission far buildings (depth 2 — atmospheric fade, fill skyline)
    for(let x=0; x<W; x+=14*S+Math.random()*8*S) {
      drawBuilding(x, landY, (6+Math.random()*10)*S, (10+Math.random()*18)*S, {depth:2});
    }

    // SoMa mid buildings (depth 1 — denser)
    for(let x=0; x<W; x+=12*S+Math.random()*8*S) {
      drawBuilding(x, landY, (8+Math.random()*12)*S, (15+Math.random()*25)*S, {depth:1});
    }

    // 280 freeway overpass (concrete highway in foreground-right)
    ctx.fillStyle = isDaytime ? '#8a8880' : '#2a2a28';
    ctx.fillRect(750*S, landY-8*S, 200*S, 4*S);
    // Highway support pillars
    for(let px=760*S; px<940*S; px+=25*S) {
      ctx.fillStyle = isDaytime ? '#9a9890' : '#3a3a38';
      ctx.fillRect(px, landY-8*S, 3*S, 8*S);
    }
    // Highway lane markings
    if(isDaytime) {
      ctx.fillStyle = 'rgba(255,255,200,0.3)';
      for(let lx=755*S; lx<940*S; lx+=8*S) { ctx.fillRect(lx, landY-6*S, 4*S, S*0.5); }
    }

    // SoMa foreground buildings (near layer — full detail, more buildings)
    const somaFG = [
      {x:30,w:28,h:55},{x:75,w:16,h:38},{x:110,w:22,h:48},{x:155,w:18,h:35},{x:190,w:24,h:42},
      {x:240,w:20,h:55},{x:285,w:14,h:30},{x:320,w:26,h:46},{x:370,w:18,h:38},{x:410,w:22,h:35},
      {x:455,w:28,h:52},{x:505,w:16,h:32},{x:545,w:20,h:44},{x:590,w:24,h:58,setback:true},
      {x:640,w:18,h:35},{x:680,w:22,h:42},{x:730,w:20,h:38},{x:780,w:26,h:48},{x:840,w:18,h:32},
      {x:880,w:22,h:45},{x:920,w:16,h:28},{x:955,w:24,h:38},
    ];
    somaFG.forEach(b => {
      drawBuilding(b.x*S, landY, b.w*S, b.h*S, {depth:0, setback:b.setback||false});
    });

    // Neon signs on some buildings (night only)
    if(!isDaytime) {
      const signColors = ['rgba(0,180,255,0.6)','rgba(255,50,100,0.5)','rgba(0,255,120,0.5)','rgba(255,200,0,0.5)'];
      for(let i=0; i<5; i++) {
        const sx = (100+Math.random()*800)*S;
        const sy = landY - (20+Math.random()*25)*S;
        ctx.fillStyle = signColors[Math.floor(Math.random()*signColors.length)];
        ctx.fillRect(sx, sy, (6+Math.random()*10)*S, 2*S);
        // Glow
        ctx.fillStyle = signColors[Math.floor(Math.random()*signColors.length)].replace(/[\d.]+\)$/, '0.1)');
        ctx.fillRect(sx-2*S, sy-2*S, (10+Math.random()*14)*S, 6*S);
      }
    }

    // Street-level trees (foreground)
    if(isDaytime) {
      for(let tx=10*S; tx<W; tx+=30*S+Math.random()*18*S) {
        ctx.fillStyle = '#5a4a30';
        ctx.fillRect(tx, landY-6*S, 2*S, 6*S);
        ctx.fillStyle = `rgb(${50+Math.random()*30},${80+Math.random()*30},${40+Math.random()*20})`;
        ctx.beginPath(); ctx.arc(tx+S, landY-8*S, 4*S+Math.random()*2*S, 0, Math.PI*2); ctx.fill();
      }
    }
  }
  else if(facing === 'east') {
    // ── EAST — Bay Bridge (main feature), Oakland skyline, port cranes ──

    // Oakland Hills (ridgeline — far background with atmospheric perspective)
    ctx.fillStyle = isDaytime ? '#5a7a58' : '#1a2a25';
    ctx.globalAlpha = isDaytime ? 0.6 : 0.8;
    ctx.beginPath(); ctx.moveTo(0,landY+10*S);
    for(let x=0; x<=W; x+=6) ctx.lineTo(x, landY-8*S+Math.sin(x*0.003)*14*S+Math.sin(x*0.01)*7*S+Math.sin(x*0.025)*3*S);
    ctx.lineTo(W,landY+10*S); ctx.fill();
    ctx.globalAlpha = 1;
    // Atmospheric haze over hills
    if(isDaytime) {
      const hG = ctx.createLinearGradient(0, landY-20*S, 0, landY);
      hG.addColorStop(0, 'rgba(150,175,200,0.4)');
      hG.addColorStop(1, 'rgba(150,175,200,0)');
      ctx.fillStyle = hG;
      ctx.fillRect(0, landY-20*S, W, 20*S);
    }

    // Oakland far buildings (depth 2 — atmospheric fade, packed skyline)
    const oakFar = [
      {x:380,w:12,h:30},{x:410,w:16,h:38},{x:445,w:10,h:25},{x:470,w:14,h:32},{x:500,w:18,h:35},
      {x:535,w:12,h:28},{x:560,w:16,h:30},{x:590,w:10,h:22},{x:615,w:14,h:28},{x:645,w:18,h:32},
      {x:680,w:12,h:25},{x:710,w:16,h:35},{x:745,w:10,h:22},{x:770,w:14,h:30},{x:800,w:16,h:28},
      {x:835,w:12,h:25},{x:860,w:18,h:32},{x:900,w:14,h:28},
    ];
    oakFar.forEach(b => {
      drawBuilding(b.x*S, landY, b.w*S, b.h*S, {depth:2});
    });

    // Oakland mid buildings (more buildings, denser)
    const oakMid = [
      {x:340,w:20,h:55},{x:390,w:16,h:42},{x:430,w:26,h:78},{x:480,w:14,h:38},{x:510,w:18,h:52},
      {x:550,w:22,h:65},{x:595,w:16,h:42},{x:630,w:22,h:58},{x:670,w:18,h:45},{x:710,w:26,h:55},
      {x:755,w:14,h:38},{x:790,w:20,h:48},{x:830,w:24,h:62},{x:870,w:16,h:35},{x:910,w:18,h:42},
    ];
    oakMid.forEach(b => {
      drawBuilding(b.x*S, landY, b.w*S, b.h*S, {depth:1, setback:b.h>50});
    });

    // Container ships at port (before cranes so cranes draw over them)
    for(let i=0; i<3; i++) {
      const sx = (420+i*150+Math.random()*40)*S;
      const sy = landY + 2*S;
      // Hull
      ctx.fillStyle = isDaytime ? '#445566' : '#1a2530';
      ctx.fillRect(sx, sy-4*S, 35*S, 4*S);
      // Containers (colored stacks)
      const containerColors = isDaytime
        ? ['#cc4422','#2266aa','#22aa44','#ddaa22','#8844aa','#dd6622']
        : ['#551a0e','#0e2a55','#0e550e','#554a0e','#3a1a55','#552a0e'];
      for(let cx=sx+2*S; cx<sx+32*S; cx+=5*S) {
        const stackH = 2+Math.floor(Math.random()*3);
        for(let row=0; row<stackH; row++) {
          ctx.fillStyle = containerColors[Math.floor(Math.random()*containerColors.length)];
          ctx.fillRect(cx, sy-4*S-(row+1)*2*S, 4*S, 2*S);
        }
      }
    }

    // Port cranes (iconic orange gantry cranes — Oakland port, more visible)
    for(let i=0; i<7; i++) {
      const cx = (380+i*80+Math.random()*20)*S;
      ctx.strokeStyle = isDaytime ? '#dd6633' : '#993311';
      ctx.lineWidth = 4*S;
      ctx.beginPath(); ctx.moveTo(cx-5*S, landY); ctx.lineTo(cx, landY-57*S); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx+5*S, landY); ctx.lineTo(cx, landY-57*S); ctx.stroke();
      ctx.lineWidth = 3*S;
      ctx.beginPath(); ctx.moveTo(cx, landY-52*S); ctx.lineTo(cx+45*S, landY-42*S); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx, landY-52*S); ctx.lineTo(cx-25*S, landY-44*S); ctx.stroke();
      ctx.fillStyle = isDaytime ? '#ee7744' : '#884422';
      ctx.fillRect(cx-4*S, landY-60*S, 8*S, 6*S);
      // Aviation light (brighter)
      ctx.fillStyle = '#ff5522'; ctx.beginPath(); ctx.arc(cx, landY-62*S, 2*S, 0, Math.PI*2); ctx.fill();
      if(!isDaytime) {
        ctx.fillStyle = 'rgba(255,85,34,0.15)'; ctx.beginPath(); ctx.arc(cx, landY-62*S, 6*S, 0, Math.PI*2); ctx.fill();
      }
    }

    // Yerba Buena Island
    ctx.fillStyle = isDaytime ? '#3a5a40' : '#162030';
    ctx.beginPath(); ctx.moveTo(200*S, landY); ctx.quadraticCurveTo(290*S, landY-50*S, 400*S, landY); ctx.fill();
    // Trees on YBI
    if(isDaytime) {
      for(let tx=220*S; tx<380*S; tx+=5+Math.random()*4) {
        const dist = Math.abs(tx-300*S)/(100*S);
        if(dist < 1) {
          const ybiH = 50*S * (1-dist*dist);
          ctx.fillStyle = `rgb(${40+Math.random()*25},${60+Math.random()*30},${35+Math.random()*15})`;
          ctx.beginPath(); ctx.arc(tx, landY-ybiH*0.6+Math.random()*10, 3+Math.random()*3, 0, Math.PI*2); ctx.fill();
        }
      }
    }

    // Bay Bridge — western suspension span (silver/gray steel)
    const bbSilver = isDaytime ? '#b0b8c4' : '#8899aa';
    const bbGray = isDaytime ? '#8a9298' : '#667788';
    const bbLight = isDaytime ? '#c8d0d8' : '#aabbcc';

    // Western span tower 1
    ctx.fillStyle = bbSilver;
    ctx.fillRect(140*S, 168*S, 10*S, landY-168*S-10*S);
    // Tower cross-beams
    ctx.fillStyle = bbGray;
    ctx.fillRect(138*S, 200*S, 14*S, 3*S);
    ctx.fillRect(138*S, 235*S, 14*S, 3*S);
    // Tower cap
    ctx.fillStyle = bbLight;
    ctx.fillRect(141*S, 165*S, 8*S, 3*S);

    // Western span tower 2
    ctx.fillStyle = bbSilver;
    ctx.fillRect(290*S, 173*S, 10*S, landY-173*S-10*S);
    ctx.fillStyle = bbGray;
    ctx.fillRect(288*S, 205*S, 14*S, 3*S);
    ctx.fillRect(288*S, 238*S, 14*S, 3*S);
    ctx.fillStyle = bbLight;
    ctx.fillRect(291*S, 170*S, 8*S, 3*S);

    // Eastern self-anchored span single tower (white/silver, modern design)
    ctx.fillStyle = isDaytime ? '#dde0e4' : '#aaaaaa';
    ctx.fillRect(465*S, 178*S, 8*S, landY-178*S-10*S);
    // X-brace detail
    ctx.strokeStyle = isDaytime ? '#c0c4c8' : '#888888';
    ctx.lineWidth = 1.5*S;
    ctx.beginPath(); ctx.moveTo(465*S, 200*S); ctx.lineTo(473*S, 230*S); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(473*S, 200*S); ctx.lineTo(465*S, 230*S); ctx.stroke();

    // Aviation lights
    [[145*S,166*S],[295*S,171*S],[469*S,176*S]].forEach(([tx,ty])=>{
      ctx.fillStyle='#ff3333'; ctx.beginPath(); ctx.arc(tx,ty,3*S,0,Math.PI*2); ctx.fill();
      ctx.fillStyle='rgba(255,50,50,0.25)'; ctx.beginPath(); ctx.arc(tx,ty,8*S,0,Math.PI*2); ctx.fill();
    });

    // Bridge deck — full span
    ctx.fillStyle = bbGray;
    ctx.fillRect(80*S, landY-10*S, 470*S, 7*S);
    ctx.fillStyle = isDaytime ? '#99aabb' : '#778899';
    ctx.fillRect(80*S, landY-10*S, 470*S, 3*S);

    // Suspension cables — span 1 (between tower 1 and tower 2)
    ctx.strokeStyle = bbLight; ctx.lineWidth = 2*S;
    const span1Mid = 215*S;
    const span1Half = 75*S;
    ctx.beginPath();
    for(let x=145*S; x<=295*S; x+=2*S) {
      const sag = Math.pow((x-span1Mid)/span1Half, 2) * 30*S;
      ctx.lineTo(x, 195*S-30*S+sag);
    }
    ctx.stroke();
    // Span 1 vertical suspenders
    ctx.lineWidth = S*0.5;
    for(let x=152*S; x<290*S; x+=8*S) {
      const sag = Math.pow((x-span1Mid)/span1Half, 2) * 30*S;
      ctx.beginPath(); ctx.moveTo(x, 195*S-30*S+sag); ctx.lineTo(x, landY-10*S); ctx.stroke();
    }

    // Suspension cables — span 2 (tower 2 to approach)
    ctx.lineWidth = 2*S;
    ctx.beginPath();
    for(let x=80*S; x<=145*S; x+=2*S) {
      const t = (x-80*S)/(65*S);
      const y = landY-10*S + (168*S - landY+10*S)*t - Math.sin(t*Math.PI)*8*S;
      ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Eastern SAS cables (fan-shaped from single tower)
    ctx.strokeStyle = isDaytime ? '#ccd0d4' : '#999999'; ctx.lineWidth = S*0.8;
    for(let x=400*S; x<530*S; x+=10*S) {
      ctx.beginPath(); ctx.moveTo(469*S, 185*S); ctx.lineTo(x, landY-10*S); ctx.stroke();
    }

    // Bridge lights
    for(let x=85*S; x<550*S; x+=8*S) {
      ctx.fillStyle = '#ffeeaa'; ctx.fillRect(x, landY-12*S, 2*S, 2*S);
      if(!isDaytime) {
        ctx.fillStyle = 'rgba(255,238,170,0.1)'; ctx.beginPath(); ctx.arc(x+S, landY-11*S, 6*S, 0, Math.PI*2); ctx.fill();
      }
    }
    // Car headlights on bridge (both directions)
    for(let x=90*S; x<545*S; x+=12*S+Math.random()*10*S) {
      ctx.fillStyle = Math.random()>0.5 ? 'rgba(255,255,240,0.7)' : 'rgba(255,60,30,0.5)';
      ctx.fillRect(x, landY-7*S, 4*S, S);
    }

    // Boats in the bay (east facing = more water visible)
    for(let i=0; i<8; i++) {
      const bx = 50*S + Math.random()*(W-100*S);
      const byy = landY+15*S+Math.random()*50*S;
      ctx.fillStyle = isDaytime ? '#ffffff' : '#aaaaaa';
      ctx.fillRect(bx, byy-2*S, 3*S, 1.5*S);
      ctx.fillStyle = isDaytime ? 'rgba(200,220,240,0.25)' : 'rgba(80,100,130,0.12)';
      ctx.fillRect(bx-2*S, byy, 7*S, S*0.4);
    }
    // Distant container ships on horizon
    for(let i=0; i<2; i++) {
      const sx = (500+i*250+Math.random()*100)*S;
      const sy = landY + 5*S + Math.random()*8*S;
      ctx.fillStyle = isDaytime ? '#667788' : '#334455';
      ctx.fillRect(sx, sy-3*S, 20*S, 3*S);
      // Stacked containers (tiny colored blocks)
      const cols = isDaytime ? ['#aa3322','#2255aa','#228844'] : ['#441a0e','#0e2244','#0e3a1e'];
      for(let cx=sx+2*S; cx<sx+18*S; cx+=4*S) {
        ctx.fillStyle = cols[Math.floor(Math.random()*cols.length)];
        ctx.fillRect(cx, sy-5*S, 3*S, 2*S);
      }
    }
  }
  else { // west — DOWNTOWN FiDi, Transamerica Pyramid, hills, Golden Gate in distance
    // Background hills (Nob Hill, Russian Hill — atmospheric fade)
    ctx.fillStyle = isDaytime ? '#6a8a58' : '#1a2a20';
    ctx.globalAlpha = isDaytime ? 0.5 : 0.7;
    ctx.beginPath(); ctx.moveTo(0,landY);
    ctx.quadraticCurveTo(150*S, landY-45*S, 300*S, landY-20*S);
    ctx.quadraticCurveTo(500*S, landY-35*S, 700*S, landY-15*S);
    ctx.quadraticCurveTo(850*S, landY-25*S, W, landY-10*S);
    ctx.lineTo(W,landY); ctx.fill();
    ctx.globalAlpha = 1;
    // Hill texture
    if(isDaytime) {
      const hG = ctx.createLinearGradient(0, landY-45*S, 0, landY);
      hG.addColorStop(0, 'rgba(140,165,190,0.3)');
      hG.addColorStop(1, 'rgba(140,165,190,0)');
      ctx.fillStyle = hG;
      ctx.fillRect(0, landY-45*S, W, 45*S);
    }

    // Marin Headlands (far background, NW)
    ctx.fillStyle = isDaytime ? '#4a6a48' : '#1a2820';
    ctx.globalAlpha = isDaytime ? 0.4 : 0.6;
    ctx.beginPath(); ctx.moveTo(650*S,landY-10*S);
    ctx.quadraticCurveTo(750*S, landY-50*S, 900*S, landY-15*S);
    ctx.lineTo(900*S, landY-10*S); ctx.fill();
    ctx.globalAlpha = 1;

    // Dense downtown FiDi — 3 depth layers (PACKED skyline)

    // Far layer (depth 2 — atmospheric fade, denser)
    for(let x=0; x<W; x+=10*S+Math.random()*8*S) {
      drawBuilding(x, landY, (5+Math.random()*10)*S, (12+Math.random()*35)*S, {depth:2});
    }

    // Mid layer (depth 1 — denser, varied widths)
    for(let x=0; x<W; x+=10*S+Math.random()*7*S) {
      drawBuilding(x, landY, (6+Math.random()*12)*S, (18+Math.random()*40)*S, {depth:1});
    }

    // Foreground major towers (more towers, taller, varied widths)
    const towers = [
      {x:30,w:18,h:120},{x:60,w:32,h:175,setback:true},{x:105,w:14,h:85},{x:135,w:24,h:140},
      {x:175,w:18,h:95},{x:210,w:22,h:115,setback:true},{x:260,w:16,h:78},
      {x:300,w:26,h:100},{x:345,w:14,h:65},{x:380,w:20,h:150},{x:420,w:18,h:88},
      {x:460,w:30,h:95},{x:510,w:16,h:72},{x:550,w:24,h:108,setback:true},
      {x:600,w:18,h:82},{x:640,w:22,h:95},{x:690,w:14,h:60},{x:720,w:28,h:98},
      {x:770,w:16,h:75},{x:810,w:20,h:118},{x:860,w:24,h:88},{x:910,w:18,h:70},{x:950,w:26,h:82},
    ];
    towers.forEach(b => {
      drawBuilding(b.x*S, landY, b.w*S, b.h*S, {depth:0, setback:b.setback||false});
    });

    // 555 California (distinctive dark granite tower)
    {
      const bG = ctx.createLinearGradient(230*S, landY-140*S, 258*S, landY);
      if(isDaytime) { bG.addColorStop(0,'#7a4a35'); bG.addColorStop(1,'#6a3a28'); }
      else { bG.addColorStop(0,'#1a1a28'); bG.addColorStop(1,'#151520'); }
      ctx.fillStyle = bG;
      ctx.fillRect(230*S, landY-140*S, 28*S, 140*S);
      // Dark granite texture — horizontal bands
      for(let fy=landY-138*S; fy<landY; fy+=3*S) {
        ctx.fillStyle = isDaytime ? 'rgba(80,80,85,0.08)' : 'rgba(10,10,15,0.1)';
        ctx.fillRect(230*S, fy, 28*S, S);
      }
      // 555 windows
      for(let wy=landY-135*S; wy<landY-3*S; wy+=4*S) {
        for(let wx=232*S; wx<256*S; wx+=3.5*S) {
          if(Math.random()>0.35) {
            ctx.fillStyle = isDaytime ? `rgba(180,190,200,0.12)` : `rgba(255,${210+Math.random()*40},${100+Math.random()*60},${wb*(0.4+Math.random()*0.5)})`;
            ctx.fillRect(wx, wy, 2*S, 2.5*S);
          }
        }
      }
    }

    // Transamerica Pyramid (iconic pointed silhouette)
    {
      const pyrX = 555*S;
      const pyrTop = landY - 155*S;
      const pyrBase = 14*S;
      // Main body
      const pyrG = ctx.createLinearGradient(pyrX-pyrBase, landY, pyrX+pyrBase, pyrTop);
      if(isDaytime) { pyrG.addColorStop(0,'#7a8a9a'); pyrG.addColorStop(0.3,'#8898a8'); pyrG.addColorStop(1,'#9aabb8'); }
      else { pyrG.addColorStop(0,'#2a3545'); pyrG.addColorStop(1,'#354560'); }
      ctx.fillStyle = pyrG;
      ctx.beginPath(); ctx.moveTo(pyrX-pyrBase, landY); ctx.lineTo(pyrX, pyrTop); ctx.lineTo(pyrX+pyrBase, landY); ctx.fill();
      // Glass reflection streak
      ctx.fillStyle = isDaytime ? 'rgba(200,220,240,0.15)' : 'rgba(100,140,200,0.08)';
      ctx.beginPath(); ctx.moveTo(pyrX-2*S, landY); ctx.lineTo(pyrX, pyrTop); ctx.lineTo(pyrX+2*S, landY); ctx.fill();
      // Windows
      for(let wy=landY-145*S; wy<landY-2*S; wy+=4*S) {
        const pw = ((wy-landY+155*S)/(155*S))*pyrBase;
        for(let wx=-pw; wx<pw; wx+=3*S) {
          if(Math.random()>0.35) {
            ctx.fillStyle = isDaytime ? `rgba(180,200,230,0.12)` : `rgba(255,${210+Math.random()*45},${90+Math.random()*70},${wb*(0.5+Math.random()*0.5)})`;
            ctx.fillRect(pyrX+wx, wy, S, 2*S);
          }
        }
      }
      // Antenna spire
      ctx.fillStyle = isDaytime ? '#99aabb' : '#667788';
      ctx.fillRect(pyrX-S, pyrTop-12*S, 2*S, 12*S);
      ctx.fillStyle = '#ff3333'; ctx.beginPath(); ctx.arc(pyrX, pyrTop-13*S, 2*S, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = 'rgba(255,50,50,0.15)'; ctx.beginPath(); ctx.arc(pyrX, pyrTop-13*S, 6*S, 0, Math.PI*2); ctx.fill();
      // Wing protrusions (elevator/stairwell shafts)
      ctx.fillStyle = isDaytime ? '#6a7a8a' : '#253040';
      ctx.fillRect(pyrX-pyrBase-3*S, landY-40*S, 3*S, 40*S);
      ctx.fillRect(pyrX+pyrBase, landY-40*S, 3*S, 40*S);
    }

    // Golden Gate Bridge (northwest, international orange #c04030)
    const ggOrange = isDaytime ? '#c04030' : '#8a2a1e';
    const ggDark = isDaytime ? '#a03525' : '#6a2015';
    // Tower 1 (south tower, closer = larger)
    const ggT1x = 700*S, ggT1top = landY-72*S;
    ctx.fillStyle = ggOrange;
    ctx.fillRect(ggT1x-4*S, ggT1top, 8*S, 72*S-10*S);
    // Tower 1 cross-beams (two levels like real GG)
    ctx.fillStyle = ggDark;
    ctx.fillRect(ggT1x-5*S, landY-48*S, 10*S, 3*S);
    ctx.fillRect(ggT1x-5*S, landY-28*S, 10*S, 3*S);
    // Tower 1 top detail (stepped cap)
    ctx.fillStyle = ggOrange;
    ctx.fillRect(ggT1x-3*S, ggT1top-3*S, 6*S, 3*S);

    // Tower 2 (north tower, farther = slightly smaller, atmospheric perspective)
    const ggT2x = 820*S, ggT2top = landY-65*S;
    ctx.fillStyle = isDaytime ? '#b8483a' : '#7a2518';
    ctx.fillRect(ggT2x-3.5*S, ggT2top, 7*S, 65*S-10*S);
    ctx.fillStyle = isDaytime ? '#a03a2c' : '#6a1c12';
    ctx.fillRect(ggT2x-4.5*S, landY-44*S, 9*S, 3*S);
    ctx.fillRect(ggT2x-4.5*S, landY-26*S, 9*S, 3*S);
    ctx.fillStyle = isDaytime ? '#b8483a' : '#7a2518';
    ctx.fillRect(ggT2x-2.5*S, ggT2top-2.5*S, 5*S, 2.5*S);

    // Bridge deck (spans full width between towers and beyond)
    ctx.fillStyle = ggDark;
    ctx.fillRect(660*S, landY-13*S, 210*S, 4*S);
    // Deck rail highlights
    ctx.fillStyle = ggOrange;
    ctx.fillRect(660*S, landY-14*S, 210*S, 1.5*S);

    // Main cables — catenary between towers
    ctx.strokeStyle = ggOrange; ctx.lineWidth = 2.5*S;
    ctx.beginPath();
    const ggMid = (ggT1x + ggT2x)/2;
    const ggSpan = (ggT2x - ggT1x)/2;
    for(let x=ggT1x; x<=ggT2x; x+=2*S) {
      const sag = Math.pow((x-ggMid)/ggSpan,2)*22*S;
      ctx.lineTo(x, landY-58*S+sag);
    }
    ctx.stroke();

    // Left side cable (south approach)
    ctx.lineWidth = 2*S;
    ctx.beginPath();
    for(let x=660*S; x<=ggT1x; x+=2*S) {
      const t = (x-660*S)/(ggT1x-660*S);
      const y = landY-13*S + (ggT1top - landY+13*S)*t - Math.sin(t*Math.PI)*5*S;
      ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Right side cable (north approach)
    ctx.beginPath();
    for(let x=ggT2x; x<=870*S; x+=2*S) {
      const t = (x-ggT2x)/(870*S-ggT2x);
      const y = ggT2top + (landY-13*S - ggT2top)*t - Math.sin((1-t)*Math.PI)*4*S;
      ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Vertical suspender cables (between towers)
    ctx.strokeStyle = ggOrange; ctx.lineWidth = S*0.5;
    for(let x=ggT1x+6*S; x<ggT2x-4*S; x+=6*S) {
      const sag = Math.pow((x-ggMid)/ggSpan,2)*22*S;
      const cableY = landY-58*S+sag;
      ctx.beginPath(); ctx.moveTo(x, cableY); ctx.lineTo(x, landY-13*S); ctx.stroke();
    }

    // Aviation lights on tower tops
    ctx.fillStyle = '#ff3333';
    ctx.beginPath(); ctx.arc(ggT1x, ggT1top-4*S, 2.5*S, 0, Math.PI*2); ctx.fill();
    ctx.beginPath(); ctx.arc(ggT2x, ggT2top-3.5*S, 2*S, 0, Math.PI*2); ctx.fill();
    if(!isDaytime) {
      ctx.fillStyle = 'rgba(255,50,50,0.25)';
      ctx.beginPath(); ctx.arc(ggT1x, ggT1top-4*S, 8*S, 0, Math.PI*2); ctx.fill();
      ctx.beginPath(); ctx.arc(ggT2x, ggT2top-3.5*S, 6*S, 0, Math.PI*2); ctx.fill();
    }

    // Street-level trees (denser)
    if(isDaytime) {
      for(let tx=15*S; tx<W; tx+=28*S+Math.random()*18*S) {
        ctx.fillStyle = '#5a4a30';
        ctx.fillRect(tx, landY-5*S, 1.5*S, 5*S);
        ctx.fillStyle = `rgb(${45+Math.random()*25},${75+Math.random()*30},${35+Math.random()*15})`;
        ctx.beginPath(); ctx.arc(tx+S, landY-7*S, 3.5*S+Math.random()*2*S, 0, Math.PI*2); ctx.fill();
      }
    }

    // Foreground small details — street lights, fire hydrants
    for(let sx=30*S; sx<W; sx+=50*S+Math.random()*40*S) {
      // Street light pole
      ctx.fillStyle = isDaytime ? '#888888' : '#555555';
      ctx.fillRect(sx, landY-4*S, S*0.5, 4*S);
      if(!isDaytime) {
        // Light glow
        ctx.fillStyle = 'rgba(255,230,150,0.4)';
        ctx.beginPath(); ctx.arc(sx, landY-4*S, 3*S, 0, Math.PI*2); ctx.fill();
      }
    }
  }

  // ── PHOTO POST-PROCESS — grain + desaturation in one pass ──
  {
    const imgData = ctx.getImageData(0, 0, W, H);
    const d = imgData.data;
    for(let i = 0; i < d.length; i += 4) {
      // Desaturate 12% toward luminance
      const gray = d[i]*0.299 + d[i+1]*0.587 + d[i+2]*0.114;
      d[i] = d[i]*0.88 + gray*0.12;
      d[i+1] = d[i+1]*0.88 + gray*0.12;
      d[i+2] = d[i+2]*0.88 + gray*0.12;
      // Add subtle grain (every 3rd pixel for perf)
      if(i % 12 === 0) {
        const noise = (Math.random() - 0.5) * 10;
        d[i] = Math.max(0, Math.min(255, d[i] + noise));
        d[i+1] = Math.max(0, Math.min(255, d[i+1] + noise));
        d[i+2] = Math.max(0, Math.min(255, d[i+2] + noise));
      }
    }
    ctx.putImageData(imgData, 0, 0);
  }

  // ── ATMOSPHERIC HAZE BAND at horizon ──
  {
    const hazeG = ctx.createLinearGradient(0, landY-15*S, 0, landY+5*S);
    hazeG.addColorStop(0, 'rgba(0,0,0,0)');
    hazeG.addColorStop(0.4, isDaytime ? 'rgba(170,190,215,0.12)' : 'rgba(20,30,50,0.08)');
    hazeG.addColorStop(0.8, isDaytime ? 'rgba(160,180,210,0.08)' : 'rgba(15,25,40,0.05)');
    hazeG.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = hazeG;
    ctx.fillRect(0, landY-15*S, W, 20*S);
  }

  // ── ATMOSPHERIC HAZE AT HORIZON ──
  {
    var hazeGrad = ctx.createLinearGradient(0, landY - 30*S, 0, landY + 10*S);
    hazeGrad.addColorStop(0, 'rgba(180,200,220,0)');
    hazeGrad.addColorStop(1, 'rgba(180,200,220,0.35)');
    ctx.fillStyle = hazeGrad;
    ctx.fillRect(0, landY - 30*S, W, 40*S);
  }

  // ── VIGNETTE — subtle dark edges for photographic look ──
  {
    const vigG = ctx.createRadialGradient(W/2, H/2, W*0.25, W/2, H/2, W*0.7);
    vigG.addColorStop(0, 'rgba(0,0,0,0)');
    vigG.addColorStop(0.7, 'rgba(0,0,0,0)');
    vigG.addColorStop(1, 'rgba(0,0,0,0.15)');
    ctx.fillStyle = vigG;
    ctx.fillRect(0, 0, W, H);
  }

  return new THREE.CanvasTexture(c);
}

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
  // Note: stairwell hole removed — stairs are outside cylinder radius
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
  color:0x88aacc, transparent:true, opacity:0.04,
  roughness:0.05, metalness:0.1, side:THREE.DoubleSide,
});
const frameMat = new THREE.MeshStandardMaterial({color:0x334450, metalness:0.7, roughness:0.3});

// Create panorama for each wall direction (time-synced)
const panTex = {
  north: createSFPanorama('north', currentHour),
  south: createSFPanorama('south', currentHour),
  east:  createSFPanorama('east', currentHour),
  west:  createSFPanorama('west', currentHour),
};

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

  // Panorama behind glass — curved cylinder segment
  const panGeo = new THREE.CylinderGeometry(
    PENTHOUSE_RAD - 0.02, PENTHOUSE_RAD - 0.02, ROOM_H, arcSegs, 1, true, wq.startAngle, arcAngle
  );
  const panMat = new THREE.MeshBasicMaterial({map: panTex[wq.facing], side: THREE.BackSide});
  const panMesh = new THREE.Mesh(panGeo, panMat);
  panMesh.position.set(0, ROOM_H / 2, 0);
  panMesh.userData.isPanorama = true;
  scene.add(panMesh);
  panPlaneMeshes[wq.facing] = panMesh;

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

// ── PHOTO PANORAMA OVERRIDE ──
// ── PHOTO PANORAMA — replace procedural wall textures with real SF photo ──
(function loadPhotoPanorama() {
  var texLoader = new THREE.TextureLoader();
  texLoader.load('/assets/environment/sf_panorama.jpg', function(texture) {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.wrapS = THREE.ClampToEdgeWrapping;
    texture.wrapT = THREE.ClampToEdgeWrapping;

    // The photo is a ~227-degree panorama. Split it into 4 wall segments.
    // Each wall gets a UV-offset slice of the full panorama.
    var facingToUV = {
      north: { offsetX: 0.0,  scaleX: 0.25 },
      east:  { offsetX: 0.25, scaleX: 0.25 },
      south: { offsetX: 0.5,  scaleX: 0.25 },
      west:  { offsetX: 0.75, scaleX: 0.25 },
    };

    Object.entries(panPlaneMeshes).forEach(function([facing, mesh]) {
      var uv = facingToUV[facing];
      if (!uv) return;
      // Clone texture with different UV offset for each wall
      var wallTex = texture.clone();
      wallTex.needsUpdate = true;
      wallTex.offset.set(uv.offsetX, 0);
      wallTex.repeat.set(uv.scaleX, 1);
      mesh.material.map = wallTex;
      mesh.material.needsUpdate = true;
    });

    console.log('Photo panorama applied to wall planes');
  }, undefined, function(err) {
    console.warn('Photo panorama failed, keeping procedural');
  });
})();

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
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.rotation.x = -Math.PI/2;
  ground.position.set(0, GROUND_Y, 0);
  ground.receiveShadow = true;
  scene.add(ground);

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
  scene.add(gridPlane);

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
  scene.add(waterPlane);

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
  scene.add(twinPeaks);

  const twinPeaks2 = new THREE.Mesh(
    new THREE.SphereGeometry(27, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x4d7d3d, roughness: 0.82})
  );
  twinPeaks2.position.set(10, GROUND_Y, 75);
  twinPeaks2.scale.y = 0.45;
  scene.add(twinPeaks2);

  // Marin Headlands (northwest, across the bay and Golden Gate) — distant blue-gray haze
  const marinHill = new THREE.Mesh(
    new THREE.SphereGeometry(45, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x6a8899, roughness: 0.85})
  );
  marinHill.position.set(-100, GROUND_Y, -160);
  marinHill.scale.y = 0.45;
  scene.add(marinHill);

  const marinHill2 = new THREE.Mesh(
    new THREE.SphereGeometry(40, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x6d8b9c, roughness: 0.85})
  );
  marinHill2.position.set(-70, GROUND_Y, -180);
  marinHill2.scale.y = 0.4;
  scene.add(marinHill2);

  // Mt Tamalpais (far north-northwest) — farthest, most blue-gray haze
  const tamalpais = new THREE.Mesh(
    new THREE.SphereGeometry(55, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({color: 0x7788aa, roughness: 0.85})
  );
  tamalpais.position.set(-120, GROUND_Y, -230);
  tamalpais.scale.y = 0.45;
  scene.add(tamalpais);

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
    scene.add(oh);
  }

  // ── EARLY MATERIAL DECLARATIONS (needed by landmarks below) ──
  const winMat = new THREE.MeshBasicMaterial({color:0xfff0cc, transparent:true, opacity:0.9, side:THREE.DoubleSide});
  const avLightMat = new THREE.MeshBasicMaterial({color:0xff2200, emissive:0xff2200});

  // ── SF HILLS (the city's famous 7 hills + more) ──
  const hillMat = new THREE.MeshStandardMaterial({color: 0x4a8a42, roughness: 0.8});
  const hillMatDry = new THREE.MeshStandardMaterial({color: 0x6a8a48, roughness: 0.82});

  // Nob Hill (west-northwest, behind FiDi) — gentle rise under buildings
  const nobHill = new THREE.Mesh(new THREE.SphereGeometry(12, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  nobHill.position.set(-35, GROUND_Y, -10);
  nobHill.scale.set(1, 0.35, 1);
  scene.add(nobHill);

  // Russian Hill (northwest) — gentle rise
  const russianHill = new THREE.Mesh(new THREE.SphereGeometry(14, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  russianHill.position.set(-30, GROUND_Y, -25);
  russianHill.scale.set(1, 0.4, 1);
  scene.add(russianHill);

  // Telegraph Hill + Coit Tower (north-northwest) — moderate rise
  const telegraphHill = new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  telegraphHill.position.set(-12, GROUND_Y, -22);
  telegraphHill.scale.set(1, 0.5, 1);
  scene.add(telegraphHill);
  // Coit Tower on top
  const coitTower = new THREE.Mesh(
    new THREE.CylinderGeometry(0.4, 0.5, 4, 8),
    new THREE.MeshStandardMaterial({color: 0xe0ddd5, roughness: 0.5})
  );
  coitTower.position.set(-12, GROUND_Y + 5, -22);
  scene.add(coitTower);

  // Potrero Hill (south-southeast) — subtle
  const potreroHill = new THREE.Mesh(new THREE.SphereGeometry(12, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMatDry);
  potreroHill.position.set(20, GROUND_Y, 55);
  potreroHill.scale.set(1, 0.25, 1);
  scene.add(potreroHill);

  // Bernal Heights (south) — subtle
  const bernalHill = new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMatDry);
  bernalHill.position.set(5, GROUND_Y, 90);
  bernalHill.scale.set(1, 0.3, 1);
  scene.add(bernalHill);

  // Mount Davidson (far southwest) — tallest in-city hill
  const mtDavidson = new THREE.Mesh(new THREE.SphereGeometry(14, 32, 16, 0, Math.PI*2, 0, Math.PI/4), hillMat);
  mtDavidson.position.set(-50, GROUND_Y, 100);
  mtDavidson.scale.set(1, 0.4, 1);
  scene.add(mtDavidson);

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
    scene.add(fbGroup);
  }

  // Oracle Park / AT&T Park (south of Embarcadero)
  {
    const parkMat = new THREE.MeshStandardMaterial({color: 0x4a5a6a, roughness: 0.5, metalness: 0.3});
    const park = new THREE.Mesh(new THREE.BoxGeometry(8, 5, 10), parkMat);
    park.position.set(28, GROUND_Y + 2.5, 20);
    scene.add(park);
    // Green field
    const field = new THREE.Mesh(
      new THREE.PlaneGeometry(5, 7),
      new THREE.MeshStandardMaterial({color: 0x3a8a3a, roughness: 0.9})
    );
    field.rotation.x = -Math.PI/2;
    field.position.set(28, GROUND_Y + 5.1, 20);
    scene.add(field);
  }

  // Sutro Tower (on Twin Peaks — red/white radio tower)
  {
    const sutroMat = new THREE.MeshStandardMaterial({color: 0xcc4422, roughness: 0.4});
    // Main mast
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.2, 15, 6), sutroMat);
    mast.position.set(2, GROUND_Y + 18 + 7.5, 78);
    scene.add(mast);
    // Cross arms (3 levels)
    for(let ay = 0; ay < 3; ay++) {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(4-ay, 0.15, 0.15), sutroMat);
      arm.position.set(2, GROUND_Y + 20 + ay*4, 78);
      scene.add(arm);
    }
    // Aviation light
    const sutroLight = new THREE.Mesh(new THREE.SphereGeometry(0.2, 4, 4), avLightMat);
    sutroLight.position.set(2, GROUND_Y + 33.5, 78);
    scene.add(sutroLight);
  }

  // ── EMBARCADERO CURVE (waterfront promenade) ──
  const embarcMat = new THREE.MeshStandardMaterial({color: 0x9a9a90, roughness: 0.8});
  for(let a = -0.3; a <= 1.2; a += 0.08) {
    const ex = 20 + Math.cos(a) * 22;
    const ez = -18 + Math.sin(a) * 30;
    if(isWater(ex, ez)) continue;
    const seg = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.15, 2.5), embarcMat);
    seg.position.set(ex, GROUND_Y + 0.15, ez);
    scene.add(seg);
  }

  // ── ALCATRAZ ISLAND (in the bay, north) ──
  {
    const alcMat = new THREE.MeshStandardMaterial({color: 0x6a7a60, roughness: 0.85});
    const alcIsland = new THREE.Mesh(new THREE.ConeGeometry(5, 3, 32, 4), alcMat);
    alcIsland.position.set(-15, GROUND_Y + 1.5, -80);
    scene.add(alcIsland);
    // Main building
    const alcBld = new THREE.Mesh(
      new THREE.BoxGeometry(4, 2, 2),
      new THREE.MeshStandardMaterial({color: 0x8a8580, roughness: 0.7})
    );
    alcBld.position.set(-15, GROUND_Y + 4, -80);
    scene.add(alcBld);
    // Lighthouse
    const alcLight = new THREE.Mesh(
      new THREE.CylinderGeometry(0.2, 0.2, 3, 6),
      new THREE.MeshStandardMaterial({color: 0xeeeeee, roughness: 0.5})
    );
    alcLight.position.set(-14, GROUND_Y + 5.5, -80);
    scene.add(alcLight);
  }

  // ── ANGEL ISLAND (larger, behind Alcatraz) ──
  {
    const aiMat = new THREE.MeshStandardMaterial({color: 0x4a6a48, roughness: 0.85});
    const aiHill = new THREE.Mesh(new THREE.ConeGeometry(12, 8, 32, 4), aiMat);
    aiHill.position.set(10, GROUND_Y + 4, -120);
    scene.add(aiHill);
    const aiHill2 = new THREE.Mesh(new THREE.ConeGeometry(8, 5, 32, 4), aiMat);
    aiHill2.position.set(18, GROUND_Y + 2.5, -115);
    scene.add(aiHill2);
  }

  // Street grid — dark asphalt strips covering the whole city
  const streetPaveMat = new THREE.MeshStandardMaterial({color:0x4a4a50, roughness:0.88, metalness:0.02});
  const streetW = 1.5; // street width
  for(let i = -80; i <= 80; i += 6) {
    // N-S streets
    const ns = new THREE.Mesh(new THREE.PlaneGeometry(streetW, 250), streetPaveMat);
    ns.rotation.x = -Math.PI/2;
    ns.position.set(i, GROUND_Y + 0.05, 20);
    scene.add(ns);
    // E-W streets
    if(i >= -40) {
      const ew = new THREE.Mesh(new THREE.PlaneGeometry(200, streetW), streetPaveMat);
      ew.rotation.x = -Math.PI/2;
      ew.position.set(0, GROUND_Y + 0.05, i);
      scene.add(ew);
    }
  }
  // Yellow center lines on major streets (every 18 units)
  const lineMat = new THREE.MeshBasicMaterial({color:0xcccc44});
  for(let i = -78; i <= 78; i += 18) {
    const ln = new THREE.Mesh(new THREE.PlaneGeometry(0.1, 250), lineMat);
    ln.rotation.x = -Math.PI/2;
    ln.position.set(i, GROUND_Y + 0.06, 20);
    scene.add(ln);
    if(i >= -40) {
      const ln2 = new THREE.Mesh(new THREE.PlaneGeometry(200, 0.1), lineMat);
      ln2.rotation.x = -Math.PI/2;
      ln2.position.set(0, GROUND_Y + 0.06, i);
      scene.add(ln2);
    }
  }

  // Market Street — diagonal cut through the grid
  const marketMat = new THREE.MeshStandardMaterial({color:0x333338, roughness:0.9});
  const marketSt = new THREE.Mesh(new THREE.PlaneGeometry(2.5, 90), marketMat);
  marketSt.rotation.x = -Math.PI/2;
  marketSt.rotation.z = Math.PI * 0.22; // ~40 degree diagonal
  marketSt.position.set(-15, GROUND_Y + 0.07, 15);
  scene.add(marketSt);

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
      scene.add(im);
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
      scene.add(sim);
    }

    // Emissive window rectangles on tall modern buildings (bright spots on faces)
    const winEmGeo = new THREE.PlaneGeometry(1, 1);
    const winWarmMat = new THREE.MeshBasicMaterial({color:0xffe8b0, transparent:true, opacity:0.7, side:THREE.DoubleSide});
    const winCoolMat2 = new THREE.MeshBasicMaterial({color:0xb0d0ff, transparent:true, opacity:0.5, side:THREE.DoubleSide});
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
        scene.add(wn);
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
      scene.add(spire);
      const avl = new THREE.Mesh(new THREE.SphereGeometry(0.12, 4, 4), antLightMat2);
      avl.position.set(b.x, GROUND_Y + b.h + spireH + 0.2, b.z);
      scene.add(avl);
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
      scene.add(im);
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
      scene.add(im);
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
          if(Math.random() < 0.6) continue;
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

    g.position.set(x, GROUND_Y, z);
    scene.add(g);
  }

  // 181 Fremont (immediately south of Salesforce Tower — tall dark neighbor)
  cityBuilding(2, 12, 3.5, 3.5, 42, true);

  // Millennium Tower (slightly northwest)
  cityBuilding(-8, -4, 3, 3, 38, true);

  // One Rincon Hill (south, near Bay Bridge approach)
  cityBuilding(12, 22, 3, 3, 36, true);

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
    return Math.abs(x) < 8 && Math.abs(z) < 7;
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
  scene.add(oaklandGround);
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
  scene.add(tiGround);
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
    scene.add(b);
    const avl = new THREE.Mesh(new THREE.SphereGeometry(0.2, 4, 4), avLightMat);
    avl.position.set(-20, GROUND_Y+35.5, 2);
    scene.add(avl);
  }

  // Embarcadero Center (4 white brutalist towers, NNW of Salesforce)
  for(let i = 0; i < 4; i++) {
    const ecMat = new THREE.MeshStandardMaterial({color:0x7a90a8, roughness:0.3, metalness:0.35});
    const ec = new THREE.Mesh(new THREE.BoxGeometry(3.5, 17+i*1.5, 3), ecMat);
    ec.position.set(-10 + i*4.5, GROUND_Y + (17+i*1.5)/2, -8);
    scene.add(ec);
  }

  // 101 California — cylindrical glass tower
  const cal101 = new THREE.Mesh(
    new THREE.CylinderGeometry(2, 2, 18, 12),
    new THREE.MeshPhysicalMaterial({color:0x7a8a9a, roughness:0.1, metalness:0.5, transparent:true, opacity:0.85})
  );
  cal101.position.set(-14, GROUND_Y + 9, -3);
  scene.add(cal101);

  // SF City Hall — Beaux-Arts with dome (WSW)
  {
    const chBase = new THREE.Mesh(
      new THREE.BoxGeometry(8, 5, 6),
      new THREE.MeshStandardMaterial({color:0x7a8a9a, roughness:0.4, metalness:0.3})
    );
    chBase.position.set(-55, GROUND_Y + 2.5, 15);
    scene.add(chBase);
    const chDome = new THREE.Mesh(
      new THREE.SphereGeometry(2.5, 12, 8, 0, Math.PI*2, 0, Math.PI/2),
      new THREE.MeshStandardMaterial({color:0xc8b050, roughness:0.3, metalness:0.7})
    );
    chDome.position.set(-55, GROUND_Y + 5, 15);
    scene.add(chDome);
    const chLantern = new THREE.Mesh(
      new THREE.CylinderGeometry(0.4, 0.5, 2, 8),
      new THREE.MeshStandardMaterial({color:0xd4b840, roughness:0.2, metalness:0.8})
    );
    chLantern.position.set(-55, GROUND_Y + 8, 15);
    scene.add(chLantern);
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
    scene.add(pyrGroup);
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
    scene.add(ggGroup);
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
      scene.add(road);
      // Road side barriers
      for(let side = -1; side <= 1; side += 2) {
        const barrier = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.6, len+3), ggRoadSideMat);
        const offsetX = Math.cos(ang + Math.PI/2) * 3 * side;
        const offsetZ = Math.sin(ang + Math.PI/2) * 3 * side;
        barrier.position.set((x1+x2)/2 + offsetX, GROUND_Y + 1.3, (z1+z2)/2 + offsetZ);
        barrier.rotation.y = ang;
        scene.add(barrier);
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
    scene.add(westSpan);

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
    scene.add(eastSpan);
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
      scene.add(road);
      // Support columns under elevated sections
      if(frac > 0.2) {
        const colH = y - GROUND_Y;
        const col = new THREE.Mesh(new THREE.BoxGeometry(0.6, colH, 0.6), bbRoadMat);
        col.position.set((x1+x2)/2, GROUND_Y + colH/2, (z1+z2)/2);
        scene.add(col);
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
    scene.add(presidioGround);

    // Presidio hills / terrain bumps
    const pHill1 = new THREE.Mesh(new THREE.ConeGeometry(15, 12, 32, 4), presidioMat);
    pHill1.position.set(-55, GROUND_Y + 6, -50);
    scene.add(pHill1);
    const pHill2 = new THREE.Mesh(new THREE.ConeGeometry(12, 8, 32, 4), presidioMat);
    pHill2.position.set(-70, GROUND_Y + 4, -70);
    scene.add(pHill2);
    const pHill3 = new THREE.Mesh(new THREE.ConeGeometry(10, 7, 32, 4), presidioMat);
    pHill3.position.set(-45, GROUND_Y + 3.5, -80);
    scene.add(pHill3);

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
      scene.add(tree);
      const trunk = new THREE.Mesh(trunkGeo, trunkMat);
      trunk.position.set(tx, GROUND_Y + 1, tz);
      scene.add(trunk);
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
    scene.add(fortPoint);
    // Fort Point parapet
    const fortWall = new THREE.Mesh(
      new THREE.BoxGeometry(7, 1, 0.5),
      new THREE.MeshStandardMaterial({color: 0x7a5a40, roughness: 0.8})
    );
    fortWall.position.set(-85, GROUND_Y + 3.5, -87.5);
    scene.add(fortWall);
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
    scene.add(marinGround);

    // Additional hill connecting to bridge north anchor
    const marinConnect = new THREE.Mesh(
      new THREE.ConeGeometry(25, 18, 32, 4),
      new THREE.MeshStandardMaterial({color: 0x6a7048, roughness: 0.9})
    );
    marinConnect.position.set(-90, GROUND_Y + 9, -135);
    scene.add(marinConnect);

    // Ridge between the two main Marin hills
    const marinRidge = new THREE.Mesh(
      new THREE.ConeGeometry(20, 14, 32, 4),
      new THREE.MeshStandardMaterial({color: 0x7a7048, roughness: 0.9})
    );
    marinRidge.position.set(-85, GROUND_Y + 7, -170);
    scene.add(marinRidge);
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
      scene.add(seg);
    }
    // Northern SF shoreline: along the bay from Presidio to Ferry Building
    for(let sx = -80; sx <= 18; sx += 3) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.2, 2), shoreMat);
      seg.position.set(sx, GROUND_Y + 0.12, -18);
      scene.add(seg);
    }
    // Curved shoreline around NE corner (North Beach to Embarcadero)
    for(let a = -0.3; a <= 0.5; a += 0.06) {
      const sx = 28 + Math.cos(a) * 8;
      const sz = -18 + Math.sin(a) * 8;
      const seg = new THREE.Mesh(new THREE.BoxGeometry(2, 0.2, 2), shoreMat);
      seg.position.set(sx, GROUND_Y + 0.12, sz);
      scene.add(seg);
    }
    // Presidio / GG waterfront shoreline
    for(let sx = -90; sx <= -30; sx += 4) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(4.5, 0.2, 2), shoreMat);
      seg.position.set(sx, GROUND_Y + 0.12, -95);
      scene.add(seg);
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
    scene.add(ybiHill);
    // Secondary bump
    const ybiHill2 = new THREE.Mesh(new THREE.SphereGeometry(7, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), ybiMat);
    ybiHill2.position.set(50, GROUND_Y, -50);
    ybiHill2.scale.y = 0.5;
    scene.add(ybiHill2);
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
    scene.add(oakExtGround);

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
    scene.add(fogPlane);
    bayFogPlanes.push(fogPlane);
  }
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
    // Scanner monitors: pair status
    ctx.fillStyle = '#00ff88';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('SCANNER', 6, 4);
    const holdEvts = events.filter(e=>e.type==='hold').slice(-8);
    const scanEvts = events.filter(e=>e.type==='scanner').slice(-3);
    ctx.font = '9px monospace';
    let y = 20;
    holdEvts.forEach(e => {
      const sym = (e.symbol||'').replace('/USDT:USDT','');
      ctx.fillStyle = '#556677';
      ctx.fillText('HOLD', 6, y);
      ctx.fillStyle = '#8899aa';
      ctx.fillText(sym, 42, y);
      // vol bar
      ctx.fillStyle = '#1a3322';
      ctx.fillRect(120, y+1, 80, 7);
      ctx.fillStyle = '#2d7a35';
      ctx.fillRect(120, y+1, 20+Math.random()*50, 7);
      y += 12;
    });
    if(name.endsWith('2')) {
      ctx.fillStyle = '#ffb830';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('LIVE SCAN', 6, 4);
      ctx.font = '9px monospace';
      y = 20;
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
    }
  }
  else if(name.startsWith('risk')) {
    ctx.fillStyle = '#ff4444';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('RISK MANAGER', 6, 4);
    // Drawdown bar
    const dd = s.drawdown || 0;
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    ctx.fillText('Drawdown', 6, 22);
    ctx.fillStyle = '#1a1a2a';
    ctx.fillRect(6, 34, 180, 12);
    ctx.fillStyle = dd > 15 ? '#ff3333' : dd > 10 ? '#ffaa33' : '#33aa55';
    ctx.fillRect(6, 34, Math.min(dd/20*180, 180), 12);
    ctx.fillStyle = '#fff';
    ctx.fillText(dd.toFixed(1)+'%', 80, 35);
    // Positions
    ctx.fillStyle = '#aab';
    ctx.fillText('Positions: '+(cy.positions||0), 6, 54);
    // Last trades
    ctx.fillText('Last Trades:', 6, 70);
    let y = 82;
    trades.slice(-5).forEach(t => {
      const pnl = t.pnl_usdt || 0;
      ctx.fillStyle = pnl >= 0 ? '#4ecb71' : '#e05252';
      const sym = (t.symbol||'').replace('/USDT:USDT','');
      ctx.fillText(`${sym} ${pnl>=0?'+':''}${pnl.toFixed(2)}`, 6, y);
      y += 11;
    });
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
    // Aggressor ratio bar
    const ratio = 0.3 + Math.random()*0.4;
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    ctx.fillText('Aggressor Ratio', 6, 22);
    ctx.fillStyle = '#1a1a2a';
    ctx.fillRect(6, 34, 180, 14);
    ctx.fillStyle = '#e05252';
    ctx.fillRect(6, 34, 180, 14);
    ctx.fillStyle = '#4ecb71';
    ctx.fillRect(6, 34, ratio*180, 14);
    ctx.fillStyle = '#fff';
    ctx.font = '8px monospace';
    ctx.fillText('BUY', 10, 37);
    ctx.fillText('SELL', 160, 37);
    // Depth bars
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    ctx.fillText('Bid/Ask Depth', 6, 58);
    for(let i=0;i<8;i++){
      const bw = 20+Math.random()*60;
      const aw = 20+Math.random()*60;
      ctx.fillStyle = '#1a4a2a';
      ctx.fillRect(90-bw, 72+i*10, bw, 7);
      ctx.fillStyle = '#4a1a1a';
      ctx.fillRect(94, 72+i*10, aw, 7);
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
    // Executor agent monitors — Keltner Squeeze, Momentum Burst, Trend Scalp
    ctx.fillStyle = '#60a5fa';
    ctx.font = 'bold 11px monospace';
    ctx.fillText('TREND ENGINE', 6, 4);
    ctx.fillStyle = '#889';
    ctx.font = '9px monospace';
    // ADX meter
    ctx.fillText('ADX Strength', 6, 22);
    ctx.fillStyle = '#1a1a2a';
    ctx.fillRect(6, 34, 180, 12);
    const holdEvts = events.filter(e=>e.type==='hold');
    const lastH = holdEvts.length ? holdEvts[holdEvts.length-1] : null;
    const adxMatch = lastH ? (lastH.detail||'').match(/ADX=([\d.]+)/) : null;
    const adx = adxMatch ? parseFloat(adxMatch[1]) : 15+Math.random()*25;
    ctx.fillStyle = adx > 25 ? '#60a5fa' : adx > 20 ? '#fbbf24' : '#555';
    ctx.fillRect(6, 34, Math.min(adx/50*180, 180), 12);
    ctx.fillStyle = '#fff';
    ctx.fillText(adx.toFixed(1), 80, 35);
    // Strategy status
    ctx.fillStyle = '#8899aa';
    ctx.fillText('Keltner Squeeze', 6, 54);
    ctx.fillStyle = adx > 25 ? '#4ecb71' : '#555';
    ctx.fillText(adx > 25 ? 'ACTIVE' : 'STANDBY', 130, 54);
    ctx.fillStyle = '#8899aa';
    ctx.fillText('Momentum Burst', 6, 68);
    ctx.fillStyle = adx > 25 ? '#4ecb71' : '#555';
    ctx.fillText(adx > 25 ? 'ACTIVE' : 'STANDBY', 130, 68);
    ctx.fillStyle = '#8899aa';
    ctx.fillText('Trend Scalp', 6, 82);
    ctx.fillStyle = adx > 25 ? '#4ecb71' : '#555';
    ctx.fillText(adx > 25 ? 'ACTIVE' : 'STANDBY', 130, 82);
    if(name.endsWith('2')){
      // MACD-style mini chart
      ctx.fillStyle = '#3366aa';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('MOMENTUM', 6, 4);
      let cx2 = 6;
      for(let i=0;i<24;i++){
        const v = (Math.random()-0.5)*30;
        ctx.fillStyle = v > 0 ? '#60a5fa' : '#334466';
        ctx.fillRect(cx2, 50-Math.max(v,0), 5, Math.abs(v));
        cx2 += 7;
      }
      ctx.fillStyle = '#8899aa';
      ctx.font = '8px monospace';
      ctx.fillText('MACD Histogram', 6, 90);
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
    const chop = chopMatch ? parseFloat(chopMatch[1]) : 40+Math.random()*30;
    ctx.fillStyle = chop > 61.8 ? '#e05252' : chop > 50 ? '#fbbf24' : '#a78bfa';
    ctx.fillRect(6, 34, Math.min(chop/100*180, 180), 12);
    ctx.fillStyle = '#fff';
    ctx.fillText(chop.toFixed(1), 80, 35);
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
      // Bollinger Band mini visualization
      ctx.fillStyle = '#6644aa';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('BB BANDS', 6, 4);
      // Draw bands
      ctx.strokeStyle = '#8866cc';
      ctx.lineWidth = 1;
      let lastMid=50, lastUp=65, lastLow=35;
      for(let i=0;i<30;i++){
        const mid = 50 + (Math.random()-0.5)*10;
        const spread = 12+Math.random()*8;
        const up = mid+spread, low = mid-spread;
        if(i>0){
          ctx.strokeStyle='#6644aa44'; ctx.beginPath(); ctx.moveTo(4+(i-1)*6,lastUp+10); ctx.lineTo(4+i*6,up+10); ctx.stroke();
          ctx.strokeStyle='#6644aa44'; ctx.beginPath(); ctx.moveTo(4+(i-1)*6,lastLow+10); ctx.lineTo(4+i*6,low+10); ctx.stroke();
          ctx.strokeStyle='#a78bfa'; ctx.beginPath(); ctx.moveTo(4+(i-1)*6,lastMid+10); ctx.lineTo(4+i*6,mid+10); ctx.stroke();
        }
        lastMid=mid; lastUp=up; lastLow=low;
      }
      // Price dot
      ctx.fillStyle='#fff';
      ctx.beginPath(); ctx.arc(4+29*6, lastMid+10, 2, 0, Math.PI*2); ctx.fill();
    }
  }
  else if(name === 'conftv') {
    // Conference room TV — Today + Recent Trades
    const td = apiData?.today || {};
    const trades2 = apiData?.recent_trades || [];
    // Header
    ctx.fillStyle = '#44aaff';
    ctx.font = 'bold 13px monospace';
    ctx.fillText('DAILY DASHBOARD', 8, 12);
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
    ctx.fillText('SIDE  PAIR       PNL      ROI    REASON', 8, 66);
    ctx.font = '8px monospace';
    let ty = 78;
    trades2.slice(-8).reverse().forEach(t => {
      const p = t.pnl_usdt||0;
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
    ctx.fillText('CUMULATIVE P&L', 8, 182);
    if(trades2.length > 1) {
      let cum = 0;
      const pts = trades2.map(t => { cum += (t.pnl_usdt||0); return cum; });
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
  }
  else if(name === 'walldash') {
    // Wall dashboard — Performance overview
    const s2 = apiData?.stats || {};
    const td2 = apiData?.today || {};
    const tp = apiData?.top_pairs || [];
    // Header
    ctx.fillStyle = '#89b4fa';
    ctx.font = 'bold 14px monospace';
    ctx.fillText('PHMEX-S PERFORMANCE', 10, 16);
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
    ctx.fillText('PnL: '+(pnl2>=0?'+':'')+pnl2.toFixed(2), 170, 60);
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
    ctx.fillText('TOP PAIRS', 10, 114);
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
    // Sparkline
    const sparkY = 96;
    ctx.strokeStyle = '#4ecb71';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for(let i=0;i<30;i++){
      const v = sparkY + (Math.sin(i*0.5+Date.now()*0.001)*8) + (Math.random()*4-2);
      if(i===0) ctx.moveTo(6+i*6, v); else ctx.lineTo(6+i*6, v);
    }
    ctx.stroke();
    if(name.endsWith('2')){
      ctx.fillStyle = '#ddaa22';
      ctx.font = 'bold 10px monospace';
      ctx.fillText('TRADE LOG', 6, 4);
      ctx.font = '8px monospace';
      let y = 20;
      trades.slice(-8).forEach(t=>{
        const p = t.pnl_usdt||0;
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

function updateAllMonitors() {
  Object.keys(monitorCanvases).forEach(name => {
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

function startAgentReport() {
  const target = visitOrder[visitIdx % visitOrder.length];
  visitIdx++;

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
      generateDialogue('meeting');
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
      generateDialogue('teammeeting');
      setTimeout(()=>{
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
  feed.innerHTML = evts.map(e => {
    const t = e.type||'info';
    const time = (e.time||'').split(' ')[1]||'';
    const msg = (e.msg||'').substring(0,60);
    return `<div class="feed-line ${t}">${time} ${msg}</div>`;
  }).join('');

  // Update plumbob colors based on performance
  const pnlVal = pnl;
  Object.keys(plumbobs).forEach(name => {
    const pb = plumbobs[name];
    if(!pb) return;
    let color = '#4ecb71'; // green
    if(pnlVal < -3) color = '#e05252'; // red
    else if(pnlVal < 0) color = '#f5c842'; // yellow
    pb.style.background = color;
    pb.style.color = color;
  });

}


// ── POST-PROCESSING SETUP (post scene/camera init) ──
composer.addPass(new RenderPass(scene, camera));

// SSAO disabled — too heavy on integrated GPU
var ssaoPass = null;

const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  0.12,  // strength — very subtle for realism
  0.4,   // radius
  0.85   // threshold — only brightest surfaces bloom
);
composer.addPass(bloomPass);

// Color grading removed — extra render pass too heavy for integrated GPU

composer.addPass(new OutputPass());

// ── TIME OF DAY UPDATE ──
function updateTimeOfDay() {
  currentHour = getTimeOfDay();
  // Regenerate panoramas
  ['north','south','east','west'].forEach(facing => {
    const newTex = createSFPanorama(facing, currentHour);
    const mesh = panPlaneMeshes[facing];
    if(mesh) {
      mesh.material.map.dispose();
      mesh.material.map = newTex;
      mesh.material.needsUpdate = true;
    }
  });
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
    bloomPass.strength = 0.12;
    setCeilingBrightness(1.0);
  } else if(isGolden) {
    const t = (h-16.5)/2.5;
    ambientLight.intensity = 0.35 - t*0.1;
    ambientLight.color.setHex(0xffe8cc);
    dirLight.intensity = 1.8 - t*0.8;
    dirLight.color.setHex(0xffaa66);
    const bg = Math.floor(0x30 + (1-t)*0x50);
    scene.background.setRGB(bg/255*0.8, bg/255*0.5, bg/255*0.3);
    scene.fog.color.copy(scene.background);
    renderer.toneMappingExposure = 1.2 - t*0.15;
    bloomPass.strength = 0.15 + t*0.1;
    setCeilingBrightness(1.0 - t*0.7);
  } else if(isNight) {
    ambientLight.intensity = 0.7;
    ambientLight.color.setHex(0xeeeeff);
    dirLight.intensity = 0.3;
    dirLight.color.setHex(0xccddff);
    scene.background.setHex(0x050810);
    scene.fog.color.setHex(0x050810);
    scene.fog.density = 0.0003;
    renderer.toneMappingExposure = 1.1;
    bloomPass.strength = 0.15;
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
    bloomPass.strength = 0.2 - t*0.08;
    setCeilingBrightness(t*0.8);
  } else if(isDusk) {
    const t = (h-19)/1.5;
    ambientLight.intensity = 0.25 - t*0.1;
    ambientLight.color.setHex(0xddccee);
    dirLight.intensity = 1.0 - t*0.8;
    scene.background.setRGB(0.08-t*0.05, 0.06-t*0.03, 0.1-t*0.04);
    scene.fog.color.copy(scene.background);
    renderer.toneMappingExposure = 1.05;
    bloomPass.strength = 0.15 + t*0.05;
    setCeilingBrightness(0.3 - t*0.3);
  }
}

// Initial time setup
updateTimeOfDay();


// ── DATA FETCH ──
async function fetchData() {
  try {
    const r = await fetch('/api/data');
    apiData = await r.json();
    updateHUD();
    updateAllMonitors();
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
  } catch(e) { /* silent */ }
}


// ── ANIMATION LOOP ──
let frameCount = 0;
function animate() {
  requestAnimationFrame(animate);
  frameCount++;
  if(frameCount % 2 !== 0) return; // ~30fps instead of 60fps
  const t = clock.getElapsedTime();

  // Character idle animations
  Object.entries(charGroups).forEach(([name, g]) => {
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
      // First walk to stair top, then descend
      facilityWalkTo = new THREE.Vector3(loc.x, loc.y + 0.02, loc.z);
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
        facilityWalking = true;
        facilityReturning = true;
        facilityWalkStart = clock.getElapsedTime();
        switchToWalkAnim(agent);
      }, FACILITY_DURATION + WALK_DURATION * 1000);
    }
  }

  // Update facility walk
  if(facilityWalking && facilityAgent) {
    const ag = charGroups[facilityAgent];
    if(ag) {
      const elapsed = t - facilityWalkStart;
      const dur = WALK_DURATION * 1.5; // slower walk (going down stairs)
      const progress = Math.min(elapsed / dur, 1.0);
      const ease = progress < 0.5 ? 2*progress*progress : 1-Math.pow(-2*progress+2,2)/2;
      ag.position.lerpVectors(facilityWalkFrom, facilityWalkTo, ease);
      restoreGroundY(facilityAgent);

      if(progress < 0.95) {
        const dir = facilityWalkTo.clone().sub(facilityWalkFrom);
        ag.rotation.y = Math.atan2(dir.x, dir.z);
      }

      if(progress >= 1.0) {
        facilityWalking = false;
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

  // Bay water waves — multi-layered sine/cosine displacement for realistic waves
  if (typeof waterPlane !== 'undefined' && waterPlane.geometry) {
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

  // Dynamic bay fog — thick at dawn (5-7am) and dusk (18-20pm), thin midday
  if (typeof bayFogMat !== 'undefined') {
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

  // Update GLTF animation mixers
  scene.traverse(function(obj) {
    if (obj.userData && obj.userData.mixer) {
      obj.userData.mixer.update(1/30);
    }
  });

  controls.update();
  composer.render();
  css2dRenderer.render(scene, camera);
}

// ── RESIZE ──
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
  if (ssaoPass) ssaoPass.setSize(window.innerWidth, window.innerHeight);
  css2dRenderer.setSize(window.innerWidth, window.innerHeight);
});

// ── INIT ──
fetchData();
setInterval(fetchData, 3000);
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
            child.castShadow = true;
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
        if self.path == "/api/data":
            data = _build_api_response()
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/" or self.path == "/index.html":
            body = HTML_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/jonas_avatar.jpg":
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
        elif self.path.startswith("/assets/"):
            # Static file serving with path traversal protection
            rel_path = self.path[len("/assets/"):]
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
