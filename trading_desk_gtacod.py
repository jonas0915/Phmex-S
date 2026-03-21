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
        "timestamp": time.time(),
    }



# ── HTML Page (GTA×COD Apex Command Center) ─────────────────────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>APEX COMMAND CENTER</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{--cyan:#00f0ff;--magenta:#ff0055;--amber:#ffb800;--green:#00ff88;--red:#ff3344;--bg:#0a0e1a;--bg2:#111827;--border:rgba(0,240,255,0.15);--glow:0 0 8px rgba(0,240,255,0.3)}
html,body{height:100%;overflow:hidden;background:var(--bg);color:#c8d0e0;font-family:'Rajdhani',sans-serif}
body{background-image:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,240,255,0.012) 2px,rgba(0,240,255,0.012) 4px)}
.mono{font-family:'Fira Code',monospace;font-variant-numeric:tabular-nums}
.lbl{font-size:10px;text-transform:uppercase;letter-spacing:2px;color:rgba(200,208,224,0.45);font-weight:600}
.panel{background:rgba(17,24,39,0.85);border:1px solid var(--border);border-radius:4px;box-shadow:var(--glow);overflow:hidden}
.panel-head{padding:6px 12px;border-bottom:1px solid var(--border);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:var(--cyan)}

/* LAYOUT */
.app{display:grid;height:100vh;grid-template-rows:52px 1fr 42px;grid-template-columns:1fr;gap:4px;padding:4px}
.main{display:grid;grid-template-columns:25% 40% 35%;gap:4px;min-height:0}

/* TOP BAR */
.top-bar{display:flex;align-items:center;gap:0;padding:0 8px;background:linear-gradient(90deg,rgba(17,24,39,0.95),rgba(10,14,26,0.95));border-bottom:1px solid var(--border);box-shadow:0 2px 12px rgba(0,0,0,0.5)}
.stat-box{flex:1;text-align:center;padding:4px 6px;border-right:1px solid rgba(0,240,255,0.08)}
.stat-box:last-child{border-right:none}
.stat-val{font-family:'Fira Code',monospace;font-size:16px;font-weight:500;font-variant-numeric:tabular-nums;line-height:1.2}
.stat-val.cyan{color:var(--cyan);text-shadow:0 0 10px rgba(0,240,255,0.5)}
.stat-val.green{color:var(--green)}.stat-val.red{color:var(--red)}.stat-val.amber{color:var(--amber)}

/* KILL FEED */
.kill-feed{display:flex;flex-direction:column;min-height:0}
.kill-list{flex:1;overflow-y:auto;padding:4px 8px;scrollbar-width:thin;scrollbar-color:#1a2235 transparent}
.kill-entry{padding:5px 8px;margin-bottom:3px;border-radius:3px;font-size:12px;font-family:'Fira Code',monospace;line-height:1.4;border-left:3px solid transparent;animation:fadeSlide .4s ease-out}
.kill-entry.win{border-left-color:var(--green);background:rgba(0,255,136,0.05);color:var(--green)}
.kill-entry.loss{border-left-color:var(--red);background:rgba(255,51,68,0.05);color:var(--red)}
.kill-entry.entry{border-left-color:var(--cyan);background:rgba(0,240,255,0.05);color:var(--cyan)}
.kill-entry .strat{color:rgba(200,208,224,0.4);font-size:10px;display:block;margin-top:1px}
@keyframes fadeSlide{from{opacity:0;transform:translateX(-12px)}to{opacity:1;transform:translateX(0)}}

/* RADAR */
.radar-wrap{display:flex;flex-direction:column;min-height:0}
.radar-container{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;min-height:0}
.radar-ring{position:relative;width:min(280px,90%);aspect-ratio:1;border-radius:50%;border:1px solid rgba(0,240,255,0.12);background:radial-gradient(circle,rgba(0,240,255,0.03) 0%,transparent 70%)}
.radar-ring::before{content:'';position:absolute;inset:20%;border-radius:50%;border:1px solid rgba(0,240,255,0.08)}
.radar-ring::after{content:'';position:absolute;inset:40%;border-radius:50%;border:1px solid rgba(0,240,255,0.06)}
.radar-center{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column}
.radar-center .title{font-size:14px;font-weight:700;letter-spacing:3px;color:var(--cyan);text-shadow:0 0 12px rgba(0,240,255,0.5)}
.radar-center .sub{font-size:9px;letter-spacing:2px;color:rgba(0,240,255,0.4);text-transform:uppercase}
.scan-line{position:absolute;inset:0;border-radius:50%;overflow:hidden;animation:radarSpin 8s linear infinite}
.scan-line::after{content:'';position:absolute;top:50%;left:50%;width:50%;height:1px;background:linear-gradient(90deg,rgba(0,240,255,0.4),transparent);transform-origin:left center}
@keyframes radarSpin{to{transform:rotate(360deg)}}
.radar-node{position:absolute;text-align:center;transform:translate(-50%,-50%)}
.radar-node .pair-name{font-size:9px;font-weight:700;color:var(--cyan);letter-spacing:1px;margin-bottom:2px}
.conf-meter{display:flex;gap:1px;justify-content:center}
.conf-seg{width:6px;height:3px;background:#1a2235;border-radius:1px}
.conf-seg.lit{background:var(--cyan);box-shadow:0 0 4px rgba(0,240,255,0.5)}
.radar-events{padding:4px 8px;font-size:11px;font-family:'Fira Code',monospace;max-height:60px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#1a2235 transparent;border-top:1px solid var(--border)}
.radar-events .evt{padding:2px 0;color:rgba(200,208,224,0.5)}
.radar-events .evt.active{color:var(--cyan)}

/* INTEL */
.intel-wrap{display:flex;flex-direction:column;min-height:0}
.intel-scroll{flex:1;overflow-y:auto;padding:6px 8px;scrollbar-width:thin;scrollbar-color:#1a2235 transparent}
.intel-section{margin-bottom:8px}
.intel-section .sec-title{font-size:10px;text-transform:uppercase;letter-spacing:2px;color:var(--magenta);font-weight:700;margin-bottom:4px;padding-bottom:2px;border-bottom:1px solid rgba(255,0,85,0.15)}
.intel-row{display:flex;justify-content:space-between;align-items:center;padding:2px 0;font-size:11px;font-family:'Fira Code',monospace}
.intel-row .k{color:rgba(200,208,224,0.55)}.intel-row .v{color:#e0e6f0}
.hurst-bar{width:40px;height:4px;background:#1a2235;border-radius:2px;overflow:hidden;display:inline-block;vertical-align:middle;margin-left:4px}
.hurst-fill{height:100%;border-radius:2px;transition:width .3s}
table.strat-tbl{width:100%;border-collapse:collapse;font-size:10px;font-family:'Fira Code',monospace}
table.strat-tbl th{text-align:left;color:rgba(200,208,224,0.4);font-weight:500;padding:2px 4px;border-bottom:1px solid rgba(0,240,255,0.08)}
table.strat-tbl td{padding:2px 4px;color:#c8d0e0}
.exit-grid{display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:10px;font-family:'Fira Code',monospace}
.exit-item .ename{color:rgba(200,208,224,0.5)}.exit-item .eval{font-weight:500}

/* BOTTOM BAR */
.bot-bar{display:flex;align-items:center;gap:12px;padding:0 12px;background:rgba(17,24,39,0.9);border-top:1px solid var(--border);font-size:11px;font-family:'Fira Code',monospace;overflow:hidden}
.bot-bar .ticker{display:flex;gap:16px;white-space:nowrap;animation:scroll 30s linear infinite;flex-shrink:0}
.bot-bar .sep{color:rgba(0,240,255,0.2)}
.bot-bar .pair-hold{color:rgba(200,208,224,0.45)}.bot-bar .pair-hold b{color:var(--cyan);font-weight:500}
.bot-stats{display:flex;gap:12px;flex-shrink:0;margin-left:auto;color:rgba(200,208,224,0.6)}
.bot-stats span b{color:#e0e6f0}
@keyframes scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}
</style>
</head>
<body>
<div class="app">
  <!-- TOP BAR -->
  <div class="top-bar">
    <div class="stat-box"><div class="lbl">Balance</div><div class="stat-val cyan mono" id="s-bal">--</div></div>
    <div class="stat-box"><div class="lbl">Today PnL</div><div class="stat-val mono" id="s-today">--</div></div>
    <div class="stat-box"><div class="lbl">Total PnL</div><div class="stat-val mono" id="s-pnl">--</div></div>
    <div class="stat-box"><div class="lbl">Win Rate</div><div class="stat-val mono" id="s-wr">--</div></div>
    <div class="stat-box"><div class="lbl">Drawdown</div><div class="stat-val mono" id="s-dd">--</div></div>
    <div class="stat-box"><div class="lbl">Cycle</div><div class="stat-val cyan mono" id="s-cyc">--</div></div>
    <div class="stat-box"><div class="lbl">Peak</div><div class="stat-val amber mono" id="s-peak">--</div></div>
    <div class="stat-box"><div class="lbl">Trades</div><div class="stat-val mono" id="s-trades">--</div></div>
  </div>

  <!-- MAIN 3-COL -->
  <div class="main">
    <!-- KILL FEED -->
    <div class="panel kill-feed">
      <div class="panel-head">Trade Feed</div>
      <div class="kill-list" id="kill-list"></div>
    </div>

    <!-- RADAR -->
    <div class="panel radar-wrap">
      <div class="panel-head">Tactical Radar</div>
      <div class="radar-container">
        <div class="radar-ring">
          <div class="scan-line"></div>
          <div class="radar-center">
            <span class="title">APEX v8.0</span>
            <span class="sub">Command Active</span>
          </div>
          <div id="radar-nodes"></div>
        </div>
      </div>
      <div class="radar-events" id="radar-events"></div>
    </div>

    <!-- INTEL -->
    <div class="panel intel-wrap">
      <div class="panel-head">Intel</div>
      <div class="intel-scroll">
        <!-- Kelly -->
        <div class="intel-section">
          <div class="sec-title">Kelly Criterion</div>
          <div id="intel-kelly">
            <div class="intel-row"><span class="k">f* raw</span><span class="v mono">--</span></div>
            <div class="intel-row"><span class="k">f kelly</span><span class="v mono">--</span></div>
            <div class="intel-row"><span class="k">margin</span><span class="v mono">--</span></div>
            <div class="intel-row"><span class="k">confidence</span><span class="v mono">--</span></div>
          </div>
        </div>
        <!-- CVD -->
        <div class="intel-section">
          <div class="sec-title">CVD Analysis</div>
          <div id="intel-cvd"></div>
        </div>
        <!-- Hurst -->
        <div class="intel-section">
          <div class="sec-title">Hurst Regime</div>
          <div id="intel-hurst"></div>
        </div>
        <!-- Funding -->
        <div class="intel-section">
          <div class="sec-title">Funding Rates</div>
          <div id="intel-funding"></div>
        </div>
        <!-- Strat Stats -->
        <div class="intel-section">
          <div class="sec-title">Strategy Stats</div>
          <table class="strat-tbl" id="intel-strats">
            <thead><tr><th>Strategy</th><th>N</th><th>WR%</th><th>PnL</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <!-- Exit Reasons -->
        <div class="intel-section">
          <div class="sec-title">Exit Reasons</div>
          <div class="exit-grid" id="intel-exits"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- BOTTOM BAR -->
  <div class="bot-bar">
    <div class="ticker" id="bot-ticker"></div>
    <div class="bot-stats" id="bot-stats"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const pnlColor = v => v >= 0 ? 'var(--green)' : 'var(--red)';
const pnlSign = v => v >= 0 ? '+' : '';
const shortSym = s => s ? s.replace('/USDT:USDT','').replace('/USDT','') : '??';
const shortStrat = s => s ? s.replace(/_/g,' ').replace('htf confluence ','') : '';
const wrClass = v => v > 55 ? 'green' : v >= 40 ? 'amber' : 'red';

let knownTradeIds = new Set();
let lastTradeCount = 0;

// Radar node positions around a circle
const nodeAngles = {};
function getNodePos(pairs, idx, total) {
  const angle = (idx / total) * Math.PI * 2 - Math.PI / 2;
  const r = 42; // % from center
  return { x: 50 + r * Math.cos(angle), y: 50 + r * Math.sin(angle) };
}

function buildConfMeter(conf, max) {
  let h = '';
  for (let i = 0; i < max; i++) h += `<div class="conf-seg${i < conf ? ' lit' : ''}"></div>`;
  return h;
}

function updateTopBar(data) {
  const s = data.stats || {};
  const t = data.today || {};
  $('s-bal').textContent = '$' + (s.balance || 0).toFixed(2);
  const todayPnl = t.pnl || 0;
  const el = $('s-today');
  el.textContent = pnlSign(todayPnl) + '$' + todayPnl.toFixed(2);
  el.className = 'stat-val mono ' + (todayPnl >= 0 ? 'green' : 'red');
  const totalPnl = s.total_pnl || 0;
  const ep = $('s-pnl');
  ep.textContent = pnlSign(totalPnl) + '$' + totalPnl.toFixed(2);
  ep.className = 'stat-val mono ' + (totalPnl >= 0 ? 'green' : 'red');
  const wr = s.win_rate || 0;
  const ew = $('s-wr');
  ew.textContent = wr.toFixed(1) + '%';
  ew.className = 'stat-val mono ' + wrClass(wr);
  $('s-dd').textContent = (s.drawdown || 0).toFixed(1) + '%';
  $('s-dd').className = 'stat-val mono ' + ((s.drawdown || 0) > 10 ? 'red' : (s.drawdown || 0) > 5 ? 'amber' : 'green');
  $('s-cyc').textContent = '#' + ((data.cycle || {}).cycle || 0);
  $('s-peak').textContent = '$' + (data.peak_balance || 0).toFixed(2);
  $('s-trades').textContent = data.total_trades || s.trades || 0;
}

function updateKillFeed(data) {
  const trades = data.recent_trades || [];
  const list = $('kill-list');
  const newCount = data.total_trades || (data.stats || {}).trades || 0;
  // Full rebuild if first load or count changed
  if (lastTradeCount !== newCount || list.children.length === 0) {
    lastTradeCount = newCount;
    // Build from newest first (assume array is newest-last or newest-first — handle both)
    const items = trades.slice(-15).reverse();
    const frag = document.createDocumentFragment();
    items.forEach(t => {
      const div = document.createElement('div');
      const sym = shortSym(t.symbol);
      const side = (t.side || 'long').toUpperCase();
      const pnl = t.pnl_usdt;
      const pct = t.pnl_pct;
      const reason = t.reason || '';
      if (pnl == null || pnl === undefined) {
        // Active entry
        div.className = 'kill-entry entry';
        div.innerHTML = `&#9658; ${side} ${sym} @ $${(t.entry_price||0).toFixed(2)} | $${(t.margin||0).toFixed(2)} | Conf ${t.confidence||'?'}/6`;
      } else if (pnl >= 0) {
        div.className = 'kill-entry win';
        div.innerHTML = `&#10022; ${side} ${sym} <b>${pnlSign(pnl)}$${pnl.toFixed(2)}</b> (${pnlSign(pct)}${pct.toFixed(1)}%) [${reason}]`;
      } else {
        div.className = 'kill-entry loss';
        div.innerHTML = `&#10022; ${side} ${sym} <b>-$${Math.abs(pnl).toFixed(2)}</b> (${pct.toFixed(1)}%) [${reason}]`;
      }
      if (t.strategy) div.innerHTML += `<span class="strat">${shortStrat(t.strategy)}</span>`;
      frag.appendChild(div);
    });
    list.innerHTML = '';
    list.appendChild(frag);
  }
}

function updateRadar(data) {
  const container = $('radar-nodes');
  const watchlist = data.watchlist || [];
  const ensemble = data.ensemble || [];
  const pairs = watchlist.map(w => w[0] || w);
  if (pairs.length === 0) { container.innerHTML = ''; return; }

  // Build ensemble confidence map
  const confMap = {};
  ensemble.forEach(e => {
    const sym = shortSym(e.symbol || '');
    if (sym) confMap[sym] = { conf: e.confidence || 0, max: e.max_conf || 6 };
  });

  let html = '';
  pairs.forEach((p, i) => {
    const pos = getNodePos(pairs, i, pairs.length);
    const c = confMap[p] || { conf: 0, max: 6 };
    html += `<div class="radar-node" style="left:${pos.x}%;top:${pos.y}%">
      <div class="pair-name">${p}</div>
      <div class="conf-meter">${buildConfMeter(c.conf, c.max)}</div>
    </div>`;
  });
  container.innerHTML = html;

  // Events
  const evtEl = $('radar-events');
  let evtHtml = '';
  ensemble.slice(0, 5).forEach(e => {
    const dir = (e.direction || '').toUpperCase();
    const conf = e.confidence || 0;
    const max = e.max_conf || 6;
    const layers = e.layers || '';
    const isSkip = e.type === 'skip' || conf < 3;
    evtHtml += `<div class="evt${isSkip ? '' : ' active'}">${dir} conf ${conf}/${max} [${layers}]</div>`;
  });
  evtEl.innerHTML = evtHtml || '<div class="evt">Awaiting signals...</div>';
}

function updateIntel(data) {
  // Kelly
  const k = data.kelly || {};
  $('intel-kelly').innerHTML = `
    <div class="intel-row"><span class="k">f* raw</span><span class="v mono">${(k.kelly_raw||0).toFixed(4)}</span></div>
    <div class="intel-row"><span class="k">f kelly</span><span class="v mono" style="color:var(--cyan)">${(k.f_kelly||0).toFixed(4)}</span></div>
    <div class="intel-row"><span class="k">margin</span><span class="v mono">$${(k.margin||0).toFixed(2)}</span></div>
    <div class="intel-row"><span class="k">confidence</span><span class="v mono">${k.confidence||0}/6</span></div>`;

  // CVD
  const cvd = data.cvd || {};
  let cvdHtml = '';
  Object.entries(cvd).forEach(([sym, d]) => {
    const arrow = (d.slope||0) > 0 ? '&#8593;' : (d.slope||0) < 0 ? '&#8595;' : '&#8594;';
    const arrowColor = (d.slope||0) > 0 ? 'var(--green)' : (d.slope||0) < 0 ? 'var(--red)' : 'var(--amber)';
    const div = d.divergence && d.divergence !== 'none' ? ` <span style="color:var(--magenta);font-size:9px">${d.divergence.toUpperCase()}</span>` : '';
    cvdHtml += `<div class="intel-row"><span class="k">${shortSym(sym)}</span><span class="v mono"><span style="color:${arrowColor}">${arrow}</span> ${(d.slope||0).toFixed(0)}${div}</span></div>`;
  });
  $('intel-cvd').innerHTML = cvdHtml || '<div class="intel-row"><span class="k">--</span><span class="v">No data</span></div>';

  // Hurst
  const hurst = data.hurst || {};
  let hHtml = '';
  Object.entries(hurst).forEach(([sym, d]) => {
    const h = d.hurst || 0.5;
    const label = h > 0.55 ? 'TREND' : h < 0.45 ? 'REVERT' : 'RANDOM';
    const color = h > 0.55 ? 'var(--green)' : h < 0.45 ? 'var(--magenta)' : 'var(--amber)';
    hHtml += `<div class="intel-row"><span class="k">${shortSym(sym)}</span><span class="v mono">${h.toFixed(3)} <span style="color:${color};font-size:9px;font-weight:700">${label}</span><span class="hurst-bar"><span class="hurst-fill" style="width:${h*100}%;background:${color}"></span></span></span></div>`;
  });
  $('intel-hurst').innerHTML = hHtml || '<div class="intel-row"><span class="k">--</span><span class="v">No data</span></div>';

  // Funding
  const fund = data.funding || {};
  let fHtml = '';
  Object.entries(fund).forEach(([sym, d]) => {
    const rate = d.rate || 0;
    const sig = d.signal || 'none';
    const rColor = rate > 0 ? 'var(--green)' : rate < 0 ? 'var(--red)' : '#c8d0e0';
    const sigBadge = sig !== 'none' ? ` <span style="color:var(--amber);font-size:9px">${sig.toUpperCase()}</span>` : '';
    fHtml += `<div class="intel-row"><span class="k">${shortSym(sym)}</span><span class="v mono" style="color:${rColor}">${(rate*100).toFixed(4)}%${sigBadge}</span></div>`;
  });
  $('intel-funding').innerHTML = fHtml || '<div class="intel-row"><span class="k">--</span><span class="v">No data</span></div>';

  // Strat stats
  const strats = data.strat_stats || {};
  const tbody = $('intel-strats').querySelector('tbody');
  let sHtml = '';
  Object.entries(strats).forEach(([name, d]) => {
    const wrC = wrClass(d.wr || 0);
    const pC = (d.pnl||0) >= 0 ? 'var(--green)' : 'var(--red)';
    sHtml += `<tr><td>${shortStrat(name)}</td><td>${d.count||0}</td><td style="color:var(--${wrC})">${(d.wr||0).toFixed(0)}%</td><td style="color:${pC}">${pnlSign(d.pnl||0)}$${(d.pnl||0).toFixed(2)}</td></tr>`;
  });
  tbody.innerHTML = sHtml || '<tr><td colspan="4" style="color:rgba(200,208,224,0.3)">No data</td></tr>';

  // Exit reasons
  const exits = data.exit_reasons || {};
  let eHtml = '';
  Object.entries(exits).forEach(([name, d]) => {
    const pC = (d.pnl||0) >= 0 ? 'var(--green)' : 'var(--red)';
    eHtml += `<div class="exit-item"><span class="ename">${name}</span> <span class="eval" style="color:${pC}">${d.count} / ${pnlSign(d.pnl||0)}$${(d.pnl||0).toFixed(2)}</span></div>`;
  });
  $('intel-exits').innerHTML = eHtml || '<span style="color:rgba(200,208,224,0.3)">No data</span>';
}

function updateBottom(data) {
  const wl = data.watchlist || [];
  const tp = data.top_pairs || [];
  // Ticker: watchlist pairs + hold reasons, doubled for seamless scroll
  let items = '';
  wl.forEach(w => {
    const pair = w[0] || '??';
    const reason = w[1] || '';
    items += `<span class="pair-hold"><b>${pair}</b> ${reason}</span><span class="sep">|</span>`;
  });
  // Double it for infinite scroll effect
  $('bot-ticker').innerHTML = items + items;

  // Stats
  const aw = data.avg_win || 0, al = data.avg_loss || 0, best = data.best_trade || 0, worst = data.worst_trade || 0;
  let statsHtml = `<span>AvgW: <b style="color:var(--green)">${pnlSign(aw)}$${aw.toFixed(2)}</b></span>`;
  statsHtml += `<span>AvgL: <b style="color:var(--red)">$${al.toFixed(2)}</b></span>`;
  statsHtml += `<span>Best: <b style="color:var(--green)">${pnlSign(best)}$${best.toFixed(2)}</b></span>`;
  statsHtml += `<span>Worst: <b style="color:var(--red)">$${worst.toFixed(2)}</b></span>`;
  // Top pairs
  tp.slice(0, 5).forEach(p => {
    const c = (p[1]||0) >= 0 ? 'var(--green)' : 'var(--red)';
    statsHtml += `<span>${p[0]}: <b style="color:${c}">${pnlSign(p[1]||0)}$${(p[1]||0).toFixed(2)}</b></span>`;
  });
  $('bot-stats').innerHTML = statsHtml;
}

function updateUI(data) {
  if (!data) return;
  updateTopBar(data);
  updateKillFeed(data);
  updateRadar(data);
  updateIntel(data);
  updateBottom(data);
}

async function fetchData() {
  try {
    const res = await fetch('/api/data');
    if (!res.ok) return;
    const data = await res.json();
    updateUI(data);
  } catch (e) {
    // Silently retry next cycle
  }
}

// Init
fetchData();
setInterval(fetchData, 5000);
</script>
</body>
</html>
"""



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
