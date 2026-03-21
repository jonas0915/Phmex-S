"""
Phmex-S AI War Room — animated multi-agent trading floor dashboard.
Standalone process — reads trading_state.json + logs/bot.log only.
Zero bot imports, zero API calls. Port 8061.
"""
import json
import os
import re
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

LOG_FILE  = "logs/bot.log"
STATE_FILE = "trading_state.json"
AVATAR_FILE = "jonas_avatar.jpg"
HOST, PORT = "127.0.0.1", 8061


def _tail(path, n=200):
    try:
        with open(path, "r") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


def _strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _parse_log_events(lines):
    events = []
    for raw in lines:
        line = _strip_ansi(raw).strip()
        if not line:
            continue
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)', line)
        if not ts_match:
            continue
        timestamp, level, msg = ts_match.groups()
        event = {"time": timestamp, "level": level, "msg": msg}

        if "[HOLD]" in msg:
            m = re.search(r'\[HOLD\] (\S+)[— -]+(.+)', msg)
            if m:
                event["type"] = "hold"
                event["symbol"] = m.group(1)
                event["detail"] = m.group(2)
            else:
                event["type"] = "hold"
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
        elif "[REGIME]" in msg:
            event["type"] = "regime"
        elif "[DRAWDOWN]" in msg:
            event["type"] = "drawdown"
        else:
            event["type"] = "info"

        events.append(event)
    return events


def _get_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"peak_balance": 0, "closed_trades": []}


def _build_api_response():
    lines = _tail(LOG_FILE, 300)
    deduped = []
    prev = None
    for line in lines:
        stripped = _strip_ansi(line).strip()
        if stripped != prev:
            deduped.append(line)
            prev = stripped

    events = _parse_log_events(deduped)
    state = _get_state()

    stats_events = [e for e in events if e.get("type") == "stats"]
    latest_stats = stats_events[-1] if stats_events else None

    cycle_events = [e for e in events if e.get("type") == "cycle"]
    latest_cycle = cycle_events[-1] if cycle_events else None

    recent_trades = state.get("closed_trades", [])[-10:]
    recent_events = events[-50:]

    return {
        "stats": latest_stats,
        "cycle": latest_cycle,
        "peak_balance": state.get("peak_balance", 0),
        "total_trades": len(state.get("closed_trades", [])),
        "recent_trades": recent_trades,
        "events": recent_events,
        "timestamp": time.time(),
    }


# ── HTML Page ───────────────────────────────────────────────────────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI War Room — Phmex-S</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323:wght@400&display=swap" rel="stylesheet">
<style>
/* ── RESET & BASE ── */
*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }

:root {
  --green:  #00ff88;
  --red:    #ff4466;
  --cyan:   #00d4ff;
  --purple: #a855f7;
  --amber:  #ffaa00;
  --dark:   #050810;
  --navy:   #080c18;
  --panel:  #0c1428;
  --border: #1a2a44;
}

html, body {
  width:100vw; height:100vh;
  overflow:hidden;
  background: var(--dark);
  color: #e0e0e0;
  font-family: 'VT323', monospace;
}

/* ── SCANLINES OVERLAY ── */
body::after {
  content:'';
  position:fixed; inset:0; z-index:9999;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.08) 2px,
    rgba(0,0,0,0.08) 4px
  );
  pointer-events:none;
}

/* ── LAYOUT ── */
#app {
  display:grid;
  grid-template-rows: 90px 1fr 220px;
  width:100vw; height:100vh;
}

/* ── HUD TOP BAR ── */
#hud {
  background: rgba(8,12,24,0.95);
  border-bottom: 2px solid var(--cyan);
  display:grid;
  grid-template-columns: 280px 1fr 360px;
  align-items:center;
  padding:0 20px;
  position:relative;
  z-index:100;
  box-shadow: 0 0 30px rgba(0,212,255,0.15);
}

.hud-left {
  display:flex; flex-direction:column; gap:2px;
}
.hud-label {
  font-family:'Press Start 2P', monospace;
  font-size:7px;
  color: var(--cyan);
  opacity:0.7;
  letter-spacing:2px;
}
.hud-balance {
  font-family:'Press Start 2P', monospace;
  font-size:20px;
  color: var(--green);
  text-shadow: 0 0 20px var(--green), 0 0 40px rgba(0,255,136,0.3);
}
.hud-pnl {
  font-size:18px;
  margin-top:2px;
}
.hud-pnl.pos { color: var(--green); }
.hud-pnl.neg { color: var(--red); }

/* sparkline */
#sparkline { height:24px; width:180px; margin-top:4px; }

/* Radar */
.hud-center {
  display:flex; flex-direction:column; align-items:center; gap:4px;
}
.radar-wrap {
  position:relative;
  width:70px; height:70px;
}
.radar-ring {
  position:absolute; inset:0;
  border:2px solid var(--cyan);
  border-radius:50%;
  opacity:0.4;
  animation: radar-pulse 2s ease-in-out infinite;
}
.radar-ring:nth-child(2) { animation-delay:0.7s; inset:10px; opacity:0.25; }
.radar-ring:nth-child(3) { animation-delay:1.4s; inset:20px; opacity:0.15; }
.radar-sweep {
  position:absolute; inset:0;
  border-radius:50%;
  background: conic-gradient(
    from 0deg,
    transparent 270deg,
    rgba(0,212,255,0.5) 360deg
  );
  animation: radar-spin 3s linear infinite;
}
.radar-dot {
  position:absolute;
  width:6px; height:6px;
  background: var(--green);
  border-radius:50%;
  box-shadow: 0 0 8px var(--green);
  top:50%; left:50%;
  transform:translate(-50%,-50%);
}
.radar-blip {
  position:absolute;
  width:8px; height:8px;
  background: var(--amber);
  border-radius:50%;
  box-shadow: 0 0 12px var(--amber);
  animation: blip-fade 2s ease-out forwards;
  pointer-events:none;
}
@keyframes radar-pulse { 0%,100%{opacity:0.4} 50%{opacity:0.8} }
@keyframes radar-spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
@keyframes blip-fade { 0%{opacity:1;transform:scale(1)} 100%{opacity:0;transform:scale(2)} }

.hud-cycle {
  font-family:'Press Start 2P', monospace;
  font-size:7px;
  color: var(--amber);
  letter-spacing:1px;
}

/* HUD right metrics */
.hud-right {
  display:grid;
  grid-template-columns: repeat(4,1fr);
  gap:8px;
}
.hud-metric {
  background: rgba(255,255,255,0.03);
  border:1px solid var(--border);
  border-radius:4px;
  padding:6px 8px;
  text-align:center;
}
.hud-metric .m-label {
  font-size:9px;
  color: var(--cyan);
  opacity:0.7;
  display:block;
  margin-bottom:3px;
}
.hud-metric .m-value {
  font-family:'Press Start 2P', monospace;
  font-size:10px;
  color: var(--amber);
}
.hud-metric .m-value.good { color: var(--green); }
.hud-metric .m-value.bad  { color: var(--red);   }

/* ── OFFICE SCENE ── */
#office {
  position:relative;
  background:
    linear-gradient(180deg, #040608 0%, #080c18 40%, #0d1525 100%);
  overflow:hidden;
}

/* city skyline */
.skyline {
  position:absolute;
  bottom:0; left:0; right:0;
  height:100%;
  pointer-events:none;
}

/* window wall */
.window-wall {
  position:absolute;
  top:0; left:0; right:0;
  height:60%;
  display:flex;
  gap:4px;
  padding:8px 12px;
  pointer-events:none;
}
.window-pane {
  flex:1;
  border:2px solid rgba(100,150,255,0.25);
  border-bottom:none;
  background: rgba(5,10,25,0.7);
  position:relative;
  overflow:hidden;
}
.window-glow {
  position:absolute; inset:0;
  background: radial-gradient(ellipse at 50% 120%, rgba(30,80,180,0.15) 0%, transparent 70%);
}

/* floor line */
.floor-line {
  position:absolute;
  bottom: 0; left:0; right:0;
  height:3px;
  background: linear-gradient(90deg, transparent, var(--cyan), var(--purple), var(--cyan), transparent);
  opacity:0.4;
}

/* desk stations */
.station {
  position:absolute;
  bottom:0;
  display:flex;
  flex-direction:column;
  align-items:center;
  width:200px;
  z-index:10;
}

/* character sprite (pixel art via CSS) */
.char-sprite {
  position:relative;
  width:60px; height:84px;
  image-rendering:pixelated;
  animation: char-bob 1.2s ease-in-out infinite;
}
@keyframes char-bob { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }

.char-head {
  position:absolute;
  top:0; left:50%;
  transform:translateX(-50%);
  width:36px; height:30px;
  border-radius:4px 4px 3px 3px;
}
.char-body {
  position:absolute;
  top:32px; left:50%;
  transform:translateX(-50%);
  width:42px; height:30px;
  border-radius:3px;
}
.char-legs {
  position:absolute;
  top:62px; left:50%;
  transform:translateX(-50%);
  width:42px; height:22px;
  border-radius:0 0 3px 3px;
}
.char-glow {
  position:absolute; inset:-10px;
  border-radius:50%;
  animation:glow-pulse 2s ease-in-out infinite;
  pointer-events:none;
}
@keyframes glow-pulse { 0%,100%{opacity:0.3;transform:scale(1)} 50%{opacity:0.7;transform:scale(1.1)} }

/* desk */
.desk {
  width:180px; height:36px;
  border-radius:4px 4px 0 0;
  position:relative;
  display:flex;
  align-items:center;
  justify-content:center;
}
.desk-monitor {
  width:54px; height:42px;
  border:2px solid #445;
  border-radius:4px;
  background:#0a0a14;
  position:absolute;
  top:-40px;
  display:flex;
  align-items:center;
  justify-content:center;
  overflow:hidden;
  box-shadow: 0 0 8px rgba(0,200,255,0.15);
}
.monitor-screen {
  width:100%; height:100%;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  font-size:9px;
  font-family:'VT323',monospace;
  line-height:1.3;
  padding:3px;
}
.desk-monitor:nth-child(2) { left:8px; }
.desk-monitor:nth-child(3) { left:72px; }
.desk-monitor:nth-child(4) { left:136px; }

/* speech bubble */
.bubble {
  position:absolute;
  bottom:100%;
  left:50%;
  transform:translateX(-50%);
  background: rgba(12,20,40,0.95);
  border:1px solid;
  border-radius:6px;
  padding:6px 10px;
  font-size:13px;
  white-space:nowrap;
  max-width:220px;
  white-space:normal;
  text-align:center;
  line-height:1.3;
  margin-bottom:6px;
  pointer-events:none;
  opacity:0;
  transition: opacity 0.4s ease;
  z-index:50;
}
.bubble.visible { opacity:1; }
.bubble::after {
  content:'';
  position:absolute;
  top:100%; left:50%;
  transform:translateX(-50%);
  border:6px solid transparent;
  border-top-color: inherit;
}
.bubble.claude-b  { border-color:var(--purple); color:var(--purple); }
.bubble.claude-b::after { border-top-color: var(--purple); }
.bubble.scanner-b { border-color:var(--green);  color:var(--green);  }
.bubble.scanner-b::after { border-top-color: var(--green); }
.bubble.risk-b    { border-color:var(--red);    color:var(--red);    }
.bubble.risk-b::after { border-top-color: var(--red); }
.bubble.tape-b    { border-color:var(--cyan);   color:var(--cyan);   }
.bubble.tape-b::after { border-top-color: var(--cyan); }
.bubble.jonas-b   { border-color:var(--amber);  color:var(--amber);  }
.bubble.jonas-b::after { border-top-color: var(--amber); }

/* name tag */
.name-tag {
  font-family:'Press Start 2P', monospace;
  font-size:6px;
  letter-spacing:1px;
  margin-top:2px;
  opacity:0.9;
}

/* Jonas avatar face */
.jonas-face {
  width:38px; height:38px;
  border-radius:50%;
  object-fit:cover;
  border:2px solid var(--amber);
  box-shadow:0 0 14px var(--amber);
}

/* walking Claude */
#claude-walker {
  position:absolute;
  bottom:28px;
  width:40px; height:56px;
  transition: left 2s cubic-bezier(0.4,0,0.2,1);
  z-index:20;
}

/* warning lights on risk desk */
.warning-light {
  width:8px; height:8px;
  border-radius:50%;
  display:inline-block;
  margin:0 2px;
}
.wl-red   { background:var(--red);   box-shadow:0 0 6px var(--red);  animation:wl-blink 1s ease-in-out infinite; }
.wl-amber { background:var(--amber); box-shadow:0 0 6px var(--amber); animation:wl-blink 1.3s ease-in-out infinite; }
.wl-green { background:var(--green); box-shadow:0 0 6px var(--green); }
@keyframes wl-blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

/* particles */
#particles { position:absolute; inset:0; pointer-events:none; z-index:30; overflow:hidden; }
.particle {
  position:absolute;
  width:4px; height:4px;
  border-radius:50%;
  pointer-events:none;
  animation: particle-fly 1.5s ease-out forwards;
}
@keyframes particle-fly {
  0%  { opacity:1; transform:translate(0,0) scale(1); }
  100%{ opacity:0; transform:translate(var(--tx),var(--ty)) scale(0); }
}

/* twinkling stars */
.star {
  position:absolute;
  width:2px; height:2px;
  background:#fff;
  border-radius:50%;
  animation:twinkle var(--d) ease-in-out infinite var(--delay);
}
@keyframes twinkle { 0%,100%{opacity:0.2} 50%{opacity:1} }

/* ── TERMINALS BOTTOM ── */
#terminals {
  display:grid;
  grid-template-columns:1fr 1fr 1fr;
  gap:8px;
  padding:8px;
  background: var(--dark);
  border-top:2px solid var(--border);
}

.terminal {
  background: rgba(0,0,0,0.7);
  border:1px solid var(--border);
  border-radius:4px;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.5), 0 0 15px rgba(0,212,255,0.05);
  position:relative;
}
/* CRT glow */
.terminal::before {
  content:'';
  position:absolute; inset:0;
  background: radial-gradient(ellipse at 50% 0%, rgba(0,212,255,0.05) 0%, transparent 70%);
  pointer-events:none;
}

.term-header {
  display:flex;
  align-items:center;
  gap:6px;
  padding:5px 10px;
  background: rgba(26,42,68,0.8);
  border-bottom:1px solid var(--border);
}
.term-dot {
  width:8px; height:8px;
  border-radius:50%;
}
.term-title {
  font-family:'Press Start 2P', monospace;
  font-size:7px;
  letter-spacing:1px;
}

.term-body {
  flex:1;
  overflow:hidden;
  padding:6px 8px;
  font-size:14px;
  line-height:1.5;
  display:flex;
  flex-direction:column;
  gap:2px;
  position:relative;
}

/* activity feed */
.log-line {
  display:flex;
  gap:6px;
  animation:log-slide 0.3s ease-out;
}
@keyframes log-slide { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:none} }
.log-time { color:#445; min-width:55px; }
.log-msg  { flex:1; word-break:break-all; }
.log-green  { color: var(--green); }
.log-red    { color: var(--red);   }
.log-cyan   { color: var(--cyan);  }
.log-amber  { color: var(--amber); }
.log-purple { color: var(--purple);}

/* trade blotter */
.blotter-table { width:100%; border-collapse:collapse; font-size:13px; }
.blotter-table th {
  color: var(--cyan);
  font-size:10px;
  text-align:left;
  padding:2px 4px;
  border-bottom:1px solid var(--border);
  font-family:'Press Start 2P',monospace;
}
.blotter-table td {
  padding:3px 4px;
  border-bottom:1px solid rgba(26,42,68,0.4);
}
.blotter-row { transition:background 0.3s; }
.blotter-row.flash-green { animation: flash-green 0.6s ease-out; }
.blotter-row.flash-red   { animation: flash-red   0.6s ease-out; }
@keyframes flash-green { 0%{background:rgba(0,255,136,0.3)} 100%{background:transparent} }
@keyframes flash-red   { 0%{background:rgba(255,68,102,0.3)} 100%{background:transparent} }

/* agent comms */
.comm-line {
  display:flex;
  gap:6px;
  align-items:flex-start;
  animation:log-slide 0.3s ease-out;
}
.comm-time { color:#445; min-width:48px; font-size:12px; }
.comm-text { font-size:13px; line-height:1.4; }

/* cursor blink */
.cursor::after {
  content:'_';
  animation:blink 1s step-end infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

/* scroll fade */
.term-body { mask-image: linear-gradient(to bottom, transparent 0%, black 15%); }
</style>
</head>
<body>
<div id="app">

  <!-- ── HUD TOP BAR ── -->
  <div id="hud">
    <div class="hud-left">
      <span class="hud-label">BALANCE</span>
      <span class="hud-balance" id="hud-balance">$--.--</span>
      <span class="hud-pnl" id="hud-pnl">P&amp;L: --</span>
      <canvas id="sparkline" width="180" height="24"></canvas>
    </div>
    <div class="hud-center">
      <div class="radar-wrap" id="radar">
        <div class="radar-ring"></div>
        <div class="radar-ring"></div>
        <div class="radar-ring"></div>
        <div class="radar-sweep"></div>
        <div class="radar-dot"></div>
      </div>
      <div class="hud-cycle" id="hud-cycle">CYCLE #---</div>
    </div>
    <div class="hud-right">
      <div class="hud-metric">
        <span class="m-label">WIN RATE</span>
        <span class="m-value" id="m-winrate">--%</span>
      </div>
      <div class="hud-metric">
        <span class="m-label">DRAWDOWN</span>
        <span class="m-value" id="m-drawdown">--%</span>
      </div>
      <div class="hud-metric">
        <span class="m-label">POSITIONS</span>
        <span class="m-value" id="m-positions">-</span>
      </div>
      <div class="hud-metric">
        <span class="m-label">TRADES</span>
        <span class="m-value" id="m-trades">-</span>
      </div>
    </div>
  </div>

  <!-- ── OFFICE SCENE ── -->
  <div id="office">
    <!-- stars -->
    <div id="stars"></div>

    <!-- window wall -->
    <div class="window-wall">
      <div class="window-pane"><div class="window-glow"></div></div>
      <div class="window-pane"><div class="window-glow"></div></div>
      <div class="window-pane"><div class="window-glow"></div></div>
      <div class="window-pane"><div class="window-glow"></div></div>
      <div class="window-pane"><div class="window-glow"></div></div>
      <div class="window-pane"><div class="window-glow"></div></div>
    </div>

    <!-- city skyline SVG -->
    <svg class="skyline" viewBox="0 0 1440 400" preserveAspectRatio="none" style="position:absolute;bottom:0;left:0;right:0;pointer-events:none;z-index:1">
      <defs>
        <filter id="city-glow">
          <feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <!-- distant buildings -->
      <rect x="0"   y="220" width="60"  height="180" fill="#0a0f1e" rx="1"/>
      <rect x="65"  y="180" width="45"  height="220" fill="#080c1a" rx="1"/>
      <rect x="115" y="240" width="30"  height="160" fill="#0a0f1e" rx="1"/>
      <rect x="150" y="190" width="55"  height="210" fill="#090d1c" rx="1"/>
      <rect x="210" y="210" width="40"  height="190" fill="#080c1a" rx="1"/>
      <rect x="255" y="160" width="70"  height="240" fill="#0a0f1e" rx="1"/>
      <rect x="330" y="200" width="35"  height="200" fill="#080c1a" rx="1"/>
      <rect x="370" y="230" width="50"  height="170" fill="#0a0f1e" rx="1"/>
      <rect x="425" y="175" width="65"  height="225" fill="#090d1c" rx="1"/>
      <rect x="495" y="220" width="40"  height="180" fill="#080c1a" rx="1"/>
      <rect x="540" y="185" width="55"  height="215" fill="#0a0f1e" rx="1"/>
      <rect x="600" y="200" width="30"  height="200" fill="#090d1c" rx="1"/>
      <rect x="635" y="155" width="75"  height="245" fill="#080c1a" rx="1"/>
      <rect x="715" y="210" width="45"  height="190" fill="#0a0f1e" rx="1"/>
      <rect x="765" y="230" width="35"  height="170" fill="#090d1c" rx="1"/>
      <rect x="805" y="190" width="60"  height="210" fill="#080c1a" rx="1"/>
      <rect x="870" y="175" width="50"  height="225" fill="#0a0f1e" rx="1"/>
      <rect x="925" y="220" width="40"  height="180" fill="#090d1c" rx="1"/>
      <rect x="970" y="165" width="70"  height="235" fill="#080c1a" rx="1"/>
      <rect x="1045" y="200" width="45" height="200" fill="#0a0f1e" rx="1"/>
      <rect x="1095" y="185" width="55" height="215" fill="#090d1c" rx="1"/>
      <rect x="1155" y="230" width="30" height="170" fill="#080c1a" rx="1"/>
      <rect x="1190" y="170" width="65" height="230" fill="#0a0f1e" rx="1"/>
      <rect x="1260" y="210" width="50" height="190" fill="#090d1c" rx="1"/>
      <rect x="1315" y="195" width="45" height="205" fill="#080c1a" rx="1"/>
      <rect x="1365" y="225" width="75" height="175" fill="#0a0f1e" rx="1"/>

      <!-- building windows (lit amber/cyan) -->
      <g fill="rgba(255,170,0,0.4)" filter="url(#city-glow)">
        <rect x="72" y="188" width="5" height="5"/><rect x="80" y="188" width="5" height="5"/>
        <rect x="72" y="198" width="5" height="5"/>
        <rect x="160" y="198" width="5" height="5"/><rect x="168" y="207" width="5" height="5"/>
        <rect x="265" y="170" width="5" height="5"/><rect x="273" y="178" width="5" height="5"/>
        <rect x="265" y="186" width="5" height="5"/>
        <rect x="435" y="183" width="5" height="5"/><rect x="443" y="192" width="5" height="5"/>
        <rect x="645" y="162" width="5" height="5"/><rect x="653" y="171" width="5" height="5"/>
        <rect x="645" y="180" width="5" height="5"/>
        <rect x="812" y="198" width="5" height="5"/><rect x="820" y="207" width="5" height="5"/>
        <rect x="980" y="173" width="5" height="5"/><rect x="988" y="182" width="5" height="5"/>
        <rect x="1200" y="178" width="5" height="5"/><rect x="1208" y="187" width="5" height="5"/>
        <rect x="1200" y="196" width="5" height="5"/>
      </g>
      <g fill="rgba(0,212,255,0.3)" filter="url(#city-glow)">
        <rect x="88" y="207" width="5" height="5"/>
        <rect x="176" y="198" width="5" height="5"/>
        <rect x="281" y="188" width="5" height="5"/>
        <rect x="451" y="183" width="5" height="5"/>
        <rect x="661" y="162" width="5" height="5"/>
        <rect x="828" y="198" width="5" height="5"/>
        <rect x="996" y="173" width="5" height="5"/>
        <rect x="1216" y="178" width="5" height="5"/>
      </g>

      <!-- floor -->
      <rect x="0" y="360" width="1440" height="40" fill="#0c1428"/>
    </svg>

    <!-- floor line -->
    <div class="floor-line"></div>

    <!-- particles -->
    <div id="particles"></div>

    <!-- ── STATION: SCANNER (far left) ── -->
    <div class="station" id="station-scanner" style="left:6%;bottom:0">
      <div class="bubble scanner-b" id="bubble-scanner">Scanning markets...</div>
      <div class="char-sprite" id="char-scanner" style="animation-delay:0.2s">
        <div class="char-head" style="background:#2a8a3a;border:2px solid var(--green)"></div>
        <div class="char-body" style="background:#1a6a2a;border:2px solid #2a8a3a"></div>
        <div class="char-legs" style="background:#145020;border:2px solid #2a8a3a"></div>
        <div class="char-glow" style="background:radial-gradient(circle,rgba(0,255,136,0.35),transparent)"></div>
      </div>
      <div class="desk" style="background:#1a3a1a;border:2px solid #2a6a2a">
        <div class="desk-monitor" style="left:10px"><div class="monitor-screen" id="mon-scan1" style="color:var(--green)">---</div></div>
        <div class="desk-monitor" style="left:60px"><div class="monitor-screen" id="mon-scan2" style="color:var(--green)">---</div></div>
        <div class="desk-monitor" style="left:110px"><div class="monitor-screen" id="mon-scan3" style="color:var(--amber)">---</div></div>
      </div>
      <div class="name-tag" style="color:var(--green)">SCANNER</div>
    </div>

    <!-- ── STATION: RISK MANAGER ── -->
    <div class="station" id="station-risk" style="left:25%;bottom:0">
      <div class="bubble risk-b" id="bubble-risk">Monitoring risk...</div>
      <div class="char-sprite" id="char-risk" style="animation-delay:0.5s">
        <div class="char-head" style="background:#8a2a2a;border:2px solid var(--red)"></div>
        <div class="char-body" style="background:#6a1a1a;border:2px solid #8a2a2a"></div>
        <div class="char-legs" style="background:#501414;border:2px solid #8a2a2a"></div>
        <div class="char-glow" style="background:radial-gradient(circle,rgba(255,68,102,0.35),transparent)"></div>
      </div>
      <div class="desk" style="background:#3a1a1a;border:2px solid #6a2a2a">
        <span class="warning-light wl-red" id="wl-r"></span>
        <span class="warning-light wl-amber" id="wl-a"></span>
        <span class="warning-light wl-green" id="wl-g"></span>
        <div class="desk-monitor" style="left:60px"><div class="monitor-screen" id="mon-risk" style="color:var(--red)">--</div></div>
      </div>
      <div class="name-tag" style="color:var(--red)">RISK MGR</div>
    </div>

    <!-- ── STATION: CLAUDE (center) ── -->
    <div class="station" id="station-claude" style="left:44%;bottom:0">
      <div class="bubble claude-b" id="bubble-claude">Analyzing signals...</div>
      <div class="char-sprite" id="char-claude" style="animation-delay:0.9s">
        <div class="char-head" style="background:#6a3aaa;border:2px solid var(--purple)"></div>
        <div class="char-body" style="background:#4a2a7a;border:2px solid #6a3aaa"></div>
        <div class="char-legs" style="background:#3a1a5a;border:2px solid #6a3aaa"></div>
        <div class="char-glow" style="background:radial-gradient(circle,rgba(168,85,247,0.5),transparent);animation-duration:1.5s"></div>
      </div>
      <div class="desk" style="background:#2a1a4a;border:2px solid #4a2a7a">
        <div class="desk-monitor" style="left:10px"><div class="monitor-screen" id="mon-claude1" style="color:var(--purple)">---</div></div>
        <div class="desk-monitor" style="left:60px"><div class="monitor-screen" id="mon-claude2" style="color:var(--cyan)">---</div></div>
      </div>
      <div class="name-tag" style="color:var(--purple)">CLAUDE AI</div>
    </div>

    <!-- ── STATION: TAPE READER ── -->
    <div class="station" id="station-tape" style="left:63%;bottom:0">
      <div class="bubble tape-b" id="bubble-tape">Reading flow...</div>
      <div class="char-sprite" id="char-tape" style="animation-delay:0.3s">
        <div class="char-head" style="background:#1a6a8a;border:2px solid var(--cyan)"></div>
        <div class="char-body" style="background:#104a6a;border:2px solid #1a6a8a"></div>
        <div class="char-legs" style="background:#0a3a50;border:2px solid #1a6a8a"></div>
        <div class="char-glow" style="background:radial-gradient(circle,rgba(0,212,255,0.35),transparent)"></div>
      </div>
      <div class="desk" style="background:#0a2a3a;border:2px solid #1a5a6a">
        <div class="desk-monitor" style="left:10px"><div class="monitor-screen" id="mon-tape1" style="color:var(--cyan)">---</div></div>
        <div class="desk-monitor" style="left:60px"><div class="monitor-screen" id="mon-tape2" style="color:var(--cyan)">---</div></div>
        <div class="desk-monitor" style="left:110px"><div class="monitor-screen" id="mon-tape3" style="color:var(--amber)">---</div></div>
      </div>
      <div class="name-tag" style="color:var(--cyan)">TAPE READER</div>
    </div>

    <!-- ── STATION: JONAS (corner office right) ── -->
    <div class="station" id="station-jonas" style="right:4%;bottom:0;width:180px">
      <div class="bubble jonas-b" id="bubble-jonas">Watching the numbers...</div>
      <div class="char-sprite" id="char-jonas" style="animation-delay:0.7s">
        <img src="/jonas_avatar.jpg" class="jonas-face" alt="Jonas"
          onerror="this.outerHTML='<div style=\'width:28px;height:28px;border-radius:50%;background:#3a2800;border:2px solid var(--amber);margin:auto\'></div>'"
        >
        <div class="char-body" style="background:#5a4a10;border:2px solid #8a6a20;margin-top:4px"></div>
        <div class="char-legs" style="background:#3a3008;border:2px solid #8a6a20"></div>
        <div class="char-glow" style="background:radial-gradient(circle,rgba(255,170,0,0.35),transparent)"></div>
      </div>
      <div class="desk" style="background:#2a2008;border:2px solid #6a5a1a;width:180px">
        <div class="desk-monitor" style="left:10px"><div class="monitor-screen" id="mon-jonas1" style="color:var(--amber)">---</div></div>
        <div class="desk-monitor" style="left:70px"><div class="monitor-screen" id="mon-jonas2" style="color:var(--green)">---</div></div>
      </div>
      <div class="name-tag" style="color:var(--amber)">THE BOSS</div>
    </div>

    <!-- ── WALKING CLAUDE ── -->
    <div id="claude-walker" style="left:44%;display:none;z-index:15">
      <div class="char-sprite" style="animation-name:char-bob;animation-duration:0.6s">
        <div class="char-head" style="background:#6a3aaa;border:2px solid var(--purple)"></div>
        <div class="char-body" style="background:#4a2a7a;border:2px solid #6a3aaa"></div>
        <div class="char-legs" style="background:#3a1a5a;border:2px solid #6a3aaa"></div>
        <div class="char-glow" style="background:radial-gradient(circle,rgba(168,85,247,0.6),transparent);animation-duration:0.8s"></div>
      </div>
    </div>
  </div>

  <!-- ── TERMINALS BOTTOM ── -->
  <div id="terminals">

    <!-- Activity Feed -->
    <div class="terminal">
      <div class="term-header">
        <div class="term-dot" style="background:#ff5f57"></div>
        <div class="term-dot" style="background:#febc2e"></div>
        <div class="term-dot" style="background:#28c840"></div>
        <span class="term-title" style="color:var(--green)">// ACTIVITY FEED</span>
      </div>
      <div class="term-body" id="feed" style="mask-image:linear-gradient(to bottom, transparent 0%, black 20%)">
        <div class="log-line"><span class="log-time log-cyan">--:--:--</span><span class="log-msg log-amber">Connecting to data feed...</span></div>
      </div>
    </div>

    <!-- Trade Blotter -->
    <div class="terminal">
      <div class="term-header">
        <div class="term-dot" style="background:#ff5f57"></div>
        <div class="term-dot" style="background:#febc2e"></div>
        <div class="term-dot" style="background:#28c840"></div>
        <span class="term-title" style="color:var(--amber)">// TRADE BLOTTER</span>
      </div>
      <div class="term-body" style="padding:0;mask-image:none">
        <table class="blotter-table">
          <thead>
            <tr>
              <th>TIME</th>
              <th>PAIR</th>
              <th>SIDE</th>
              <th>PNL</th>
              <th>REASON</th>
            </tr>
          </thead>
          <tbody id="blotter-body">
            <tr><td colspan="5" style="color:#445;padding:8px;text-align:center">Awaiting trades...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Agent Comms -->
    <div class="terminal">
      <div class="term-header">
        <div class="term-dot" style="background:#ff5f57"></div>
        <div class="term-dot" style="background:#febc2e"></div>
        <div class="term-dot" style="background:#28c840"></div>
        <span class="term-title" style="color:var(--purple)">// AGENT COMMS</span>
      </div>
      <div class="term-body" id="comms" style="mask-image:linear-gradient(to bottom, transparent 0%, black 20%)">
        <div class="comm-line">
          <span class="comm-time log-purple">--:--</span>
          <span class="comm-text log-purple">War Room initializing...</span>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
// ── STATE ──
const state = {
  data: null,
  prevTradeCount: 0,
  sparkData: [],
  claudePos: 'claude',  // scanner | risk | claude | tape | jonas
  claudeStep: 0,
  walkCycle: ['scanner','risk','tape','jonas','claude'],
  commsLog: [],
  lastEventIdx: 0,
};

// ── STARS ──
(function initStars(){
  const el = document.getElementById('stars');
  for(let i=0;i<80;i++){
    const s = document.createElement('div');
    s.className='star';
    s.style.cssText=`
      left:${Math.random()*100}%;
      top:${Math.random()*55}%;
      --d:${2+Math.random()*4}s;
      --delay:-${Math.random()*4}s;
      opacity:${0.1+Math.random()*0.5};
    `;
    el.appendChild(s);
  }
})();

// ── SPARKLINE ──
function drawSparkline(canvas, data, color='#00ff88'){
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(data.length<2) return;
  const min=Math.min(...data), max=Math.max(...data);
  const range=max-min||1;
  const w=canvas.width, h=canvas.height, pad=2;
  ctx.strokeStyle=color;
  ctx.lineWidth=1.5;
  ctx.shadowColor=color;
  ctx.shadowBlur=4;
  ctx.beginPath();
  data.forEach((v,i)=>{
    const x=pad+(i/(data.length-1))*(w-2*pad);
    const y=h-pad-((v-min)/range)*(h-2*pad);
    i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
  });
  ctx.stroke();
}

// ── PARTICLES ──
function spawnParticles(color='#00ff88', count=12){
  const el=document.getElementById('particles');
  for(let i=0;i<count;i++){
    const p=document.createElement('div');
    p.className='particle';
    const angle=Math.random()*Math.PI*2;
    const dist=40+Math.random()*60;
    p.style.cssText=`
      left:${30+Math.random()*70}%;
      bottom:${60+Math.random()*30}px;
      background:${color};
      box-shadow:0 0 6px ${color};
      --tx:${Math.cos(angle)*dist}px;
      --ty:${Math.sin(angle)*dist}px;
    `;
    el.appendChild(p);
    setTimeout(()=>p.remove(),1500);
  }
}

// ── RADAR BLIP ──
function addRadarBlip(){
  const radar=document.getElementById('radar');
  const b=document.createElement('div');
  b.className='radar-blip';
  const angle=Math.random()*Math.PI*2;
  const r=10+Math.random()*20;
  b.style.cssText=`
    left:${50+Math.cos(angle)*r}%;
    top:${50+Math.sin(angle)*r}%;
    transform:translate(-50%,-50%);
  `;
  radar.appendChild(b);
  setTimeout(()=>b.remove(),2000);
}

// ── CLAUDE WALK ──
function updateClaudeWalk(){
  const positions = {
    scanner:  '6%',
    risk:     '25%',
    claude:   '44%',
    tape:     '63%',
    jonas:    'calc(96% - 40px)',
  };
  // desk station offsets for walker overlay
  const desks = ['scanner','risk','tape','jonas','claude'];
  state.claudeStep = (state.claudeStep+1) % state.walkCycle.length;
  const dest = state.walkCycle[state.claudeStep];
  state.claudePos = dest;

  const walker = document.getElementById('claude-walker');
  const stationClaude = document.getElementById('station-claude');

  if(dest === 'claude'){
    walker.style.display='none';
    stationClaude.style.opacity='1';
  } else {
    walker.style.display='block';
    stationClaude.style.opacity='0.3';
    walker.style.left = positions[dest];
  }

  // Natural dialogue — pick from pool based on actual data context
  const d = state.data;
  const dd = d?.stats?.drawdown ?? 0;
  const wr = d?.stats?.win_rate ?? 0;
  const pnl = d?.stats?.total_pnl ?? 0;
  const pos = d?.cycle?.positions ?? 0;
  const bal = d?.stats?.balance ?? 0;
  const cycle = d?.cycle?.cycle ?? 0;
  const evs = d?.events || [];
  const holds = evs.filter(e=>e.type==='hold');
  const tapeEvs = evs.filter(e=>e.type==='tape');
  const riskEvs = evs.filter(e=>['cooldown','regime','ban'].includes(e.type));
  const lastHold = holds.length ? holds[holds.length-1] : null;
  const lastTape = tapeEvs.length ? tapeEvs[tapeEvs.length-1] : null;
  const lastClose = evs.filter(e=>e.type==='close').pop();
  const lastEntry = evs.filter(e=>e.type==='entry').pop();
  const pick = arr => arr[Math.floor(Math.random()*arr.length)];

  // Helper: extract symbol short name
  const short = s => (s||'').replace('/USDT:USDT','').replace('/USDT','');

  // Claude bubble at destination
  const claudeBubbles = {
    scanner: lastHold
      ? `Hey, anything on ${short(lastHold.symbol)}?`
      : pick([`Yo Scanner, what's hot right now?`, `Anything setting up? I'm bored.`, `Talk to me — what are you seeing?`]),
    risk: dd > 15
      ? `We're at ${dd.toFixed(1)}% drawdown... should I slow down?`
      : pos >= 3
      ? `We've got ${pos} open — room for more?`
      : pick([`Risk check — how's our exposure?`, `Am I clear to enter?`, `What's the damage report?`]),
    tape: lastTape
      ? `What's the flow looking like on this one?`
      : pick([`Reading anything interesting?`, `Any big players moving?`, `What's the tape saying?`]),
    jonas: pnl > 0
      ? `We're up $${pnl.toFixed(2)} today, boss.`
      : pnl < -2
      ? `Tough day... down $${Math.abs(pnl).toFixed(2)}. Working on it.`
      : pick([`Quick update for you, Jonas.`, `Here's where we stand.`, `Checking in — anything you need?`]),
    claude: cycle > 0
      ? `Cycle ${cycle}... ${pos} position${pos!==1?'s':''} running.`
      : `Warming up the system...`,
  };
  setBubble('claude', claudeBubbles[dest]);

  // Agent responses — natural, data-specific
  if(dest !== 'claude'){
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

    let claudeMsg, agentMsg;
    if(dest === 'scanner'){
      claudeMsg = claudeBubbles.scanner;
      if(lastHold){
        const sym = short(lastHold.symbol);
        const det = lastHold.detail || '';
        const adxMatch = det.match(/ADX=([\d.]+)/);
        const adx = adxMatch ? parseFloat(adxMatch[1]) : 0;
        agentMsg = adx < 20
          ? `${sym} is dead — ADX at ${adx.toFixed(0)}, no trend at all. I'd skip it.`
          : adx > 30
          ? `${sym} looks interesting, ADX ${adx.toFixed(0)} but the chop filter killed it.`
          : `Nothing clean on ${sym} right now. ${det.slice(0,25)}. Still scanning the others.`;
      } else {
        agentMsg = pick([
          `Quiet out there. Most pairs are ranging, nobody's committing.`,
          `Running through the list... haven't found a setup worth your time yet.`,
          `Volume's thin across the board. I'll flag you when something pops.`,
        ]);
      }
    } else if(dest === 'risk'){
      claudeMsg = claudeBubbles.risk;
      if(riskEvs.length){
        const last = riskEvs[riskEvs.length-1];
        if(last.type==='cooldown') agentMsg = `We just got burned — I put that pair on timeout. Give it a few minutes.`;
        else if(last.type==='regime') agentMsg = `Three losses in a row. I've pulled us out of the market for 15 minutes. Non-negotiable.`;
        else if(last.type==='ban') agentMsg = `API is giving us trouble. I've shut entries until it clears up.`;
        else agentMsg = last.msg.substring(0,60);
      } else if(dd > 15){
        agentMsg = `Drawdown is ${dd.toFixed(1)}% — getting uncomfortable. We've got ${pos} open. I'd be careful adding more.`;
      } else if(dd > 8){
        agentMsg = `${dd.toFixed(1)}% drawdown, ${pos} position${pos!==1?'s':''}. We're fine but keep entries tight.`;
      } else {
        agentMsg = pos > 0
          ? `All good. ${pos} position${pos!==1?'s':''} running, drawdown only ${dd.toFixed(1)}%. You've got room.`
          : `Book is empty, drawdown ${dd.toFixed(1)}%. Green light on entries whenever you see something.`;
      }
    } else if(dest === 'tape'){
      claudeMsg = claudeBubbles.tape;
      if(lastTape){
        const msg = lastTape.msg || '';
        const aggrMatch = msg.match(/aggr=([\d.]+)/);
        const deltaMatch = msg.match(/delta=\$([\-\+\d,]+)/);
        if(aggrMatch){
          const aggr = parseFloat(aggrMatch[1]);
          if(aggr > 0.6) agentMsg = `Buyers in control — aggressor ratio ${aggr.toFixed(2)}. Longs look supported.`;
          else if(aggr < 0.4) agentMsg = `Sellers are heavy. Aggressor at ${aggr.toFixed(2)}, I'd avoid longs right now.`;
          else agentMsg = `Mixed signals — aggressor at ${aggr.toFixed(2)}, nobody's winning. I wouldn't force a trade here.`;
        } else {
          agentMsg = msg.replace(/\[TAPE\]\s*/,'').substring(0,60);
        }
      } else {
        agentMsg = pick([
          `Flow is quiet. No big orders, no sweeps. Just market makers shuffling.`,
          `Nothing notable. Small fish trading with each other.`,
          `Tape's flat. When the whales show up, I'll let you know.`,
        ]);
      }
    } else if(dest === 'jonas'){
      claudeMsg = claudeBubbles.jonas;
      if(pnl > 5) agentMsg = `$${pnl.toFixed(2)} up? Nice work. Keep the risk tight and ride it out.`;
      else if(pnl > 0) agentMsg = `+$${pnl.toFixed(2)}, ${wr.toFixed(0)}% win rate. Solid. Don't get greedy though.`;
      else if(pnl > -2) agentMsg = `Basically flat at $${pnl.toFixed(2)}. Not worried yet. The setups will come.`;
      else if(pnl > -5) agentMsg = `Down $${Math.abs(pnl).toFixed(2)}... I've seen worse. Stick to the plan, don't revenge trade.`;
      else agentMsg = `$${pnl.toFixed(2)} is rough. I trust the system but maybe tighten up entries. ${wr.toFixed(0)}% WR needs work.`;
    }

    setTimeout(()=>addComm(ts, `Claude → ${dest==='jonas'?'Jonas':dest.charAt(0).toUpperCase()+dest.slice(1)}: "${claudeMsg}"`, 'purple'), 0);
    setTimeout(()=>{
      addComm(ts, `${dest==='jonas'?'Jonas':dest.charAt(0).toUpperCase()+dest.slice(1)} → Claude: "${agentMsg}"`, 'cyan');
      // Also set the agent's bubble to their response
      setBubble(dest==='jonas'?'jonas':dest, agentMsg);
    }, 1500);
  }
}

// ── BUBBLES ──
function setBubble(agent, text){
  const el = document.getElementById(`bubble-${agent}`);
  if(!el) return;
  el.textContent = text;
  el.classList.add('visible');
  clearTimeout(el._timer);
  el._timer = setTimeout(()=>el.classList.remove('visible'), 5500);
}

// ── COMMS ──
function addComm(ts, text, color='purple'){
  const el = document.getElementById('comms');
  const div = document.createElement('div');
  div.className='comm-line';
  div.innerHTML=`
    <span class="comm-time log-${color}">${ts}</span>
    <span class="comm-text log-${color}">${text}</span>
  `;
  el.appendChild(div);
  while(el.children.length>12) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

// ── ACTIVITY FEED ──
function addFeedLine(ts, msg, cls){
  const el = document.getElementById('feed');
  const div = document.createElement('div');
  div.className='log-line';
  const hm = ts ? (typeof ts==='number' ? new Date(ts*1000).toTimeString().substring(0,8) : String(ts).substring(11,19)) : '--:--:--';
  div.innerHTML=`<span class="log-time log-cyan">${hm}</span><span class="log-msg ${cls}">${escHtml(msg)}</span>`;
  el.appendChild(div);
  while(el.children.length>18) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

function escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function eventClass(ev){
  if(ev.type==='entry') return 'log-green';
  if(ev.type==='close'){
    if(ev.pnl!=null) return ev.pnl>=0 ? 'log-green' : 'log-red';
    return 'log-amber';
  }
  if(ev.type==='cooldown'||ev.type==='ban'||ev.type==='regime') return 'log-red';
  if(ev.type==='scanner') return 'log-amber';
  if(ev.type==='tape'||ev.type==='orderbook'||ev.type==='depth') return 'log-cyan';
  if(ev.type==='ws'||ev.type==='sync') return 'log-cyan';
  if(ev.type==='fill'||ev.type==='entry_detail') return 'log-green';
  return 'log-amber';
}

function eventSummary(ev){
  if(ev.type==='entry') return `ENTRY ${ev.side||''} ${ev.symbol||''} — ${ev.msg}`;
  if(ev.type==='close'){
    const pnlStr = ev.pnl!=null ? ` | PnL: ${ev.pnl>0?'+':''}${ev.pnl?.toFixed(2)} USDT` : '';
    return `CLOSE ${ev.side||''} ${ev.symbol||''}${pnlStr}`;
  }
  if(ev.type==='hold') return `HOLD ${ev.symbol||''} — ${ev.detail||ev.msg}`;
  if(ev.type==='cycle') return `Cycle #${ev.cycle} | ${ev.positions} positions`;
  if(ev.type==='stats') return `STATS: ${ev.win_rate?.toFixed(0)}% WR | PnL: ${ev.total_pnl?.toFixed(2)} USDT`;
  if(ev.type==='cooldown') return ev.msg;
  if(ev.type==='scanner') return ev.msg.substring(0,70);
  if(ev.type==='tape') return ev.msg.substring(0,70);
  return ev.msg.substring(0,70);
}

// ── BLOTTER ──
let prevTradeIds = new Set();
function updateBlotter(trades){
  const tbody = document.getElementById('blotter-body');
  const last5 = [...trades].reverse().slice(0,5);
  if(!last5.length){
    tbody.innerHTML='<tr><td colspan="5" style="color:#445;padding:8px;text-align:center">No trades yet</td></tr>';
    return;
  }
  tbody.innerHTML = last5.map(t=>{
    const pnl = t.pnl_usdt ?? t.pnl ?? t.realized_pnl ?? 0;
    const pnlCls = pnl>=0 ? 'log-green':'log-red';
    const pnlStr = `${pnl>=0?'+':''}${parseFloat(pnl).toFixed(2)}`;
    const raw = t.closed_at||t.time||'';
    const ts = typeof raw==='number' ? new Date(raw*1000).toTimeString().substring(0,5) : String(raw).substring(11,16) || '--:--';
    const sym = (t.symbol||'??').replace('/USDT:USDT','').replace('/USDT','');
    const side = (t.side||t.direction||'?').toUpperCase();
    const reason = t.reason||t.exit_reason||'-';
    const isNew = !prevTradeIds.has(t.id||String(t.closed_at)||ts);
    const flashCls = isNew ? (pnl>=0?'blotter-row flash-green':'blotter-row flash-red') : 'blotter-row';
    return `<tr class="${flashCls}">
      <td class="log-cyan">${ts}</td>
      <td style="color:#ddd">${sym}</td>
      <td style="color:${side==='LONG'?'var(--green)':'var(--red)'}">${side}</td>
      <td class="${pnlCls}">${pnlStr}</td>
      <td style="color:#778">${reason}</td>
    </tr>`;
  }).join('');
  prevTradeIds = new Set(last5.map(t=>t.id||String(t.closed_at)||''));
}

// ── HUD UPDATE ──
function updateHUD(d){
  // Balance
  const bal = d.stats?.balance;
  const balEl = document.getElementById('hud-balance');
  if(bal!=null){
    balEl.textContent = `$${parseFloat(bal).toFixed(2)}`;
    state.sparkData.push(parseFloat(bal));
    if(state.sparkData.length>40) state.sparkData.shift();
    drawSparkline(document.getElementById('sparkline'), state.sparkData);
  }

  // PnL
  const pnl = d.stats?.total_pnl;
  const pnlEl = document.getElementById('hud-pnl');
  if(pnl!=null){
    pnlEl.textContent = `P&L: ${pnl>=0?'+':''}${parseFloat(pnl).toFixed(2)} USDT`;
    pnlEl.className = `hud-pnl ${pnl>=0?'pos':'neg'}`;
  }

  // Cycle
  if(d.cycle?.cycle){
    document.getElementById('hud-cycle').textContent = `CYCLE #${d.cycle.cycle}`;
  }

  // Metrics
  const wr = d.stats?.win_rate;
  const wrEl = document.getElementById('m-winrate');
  if(wr!=null){
    wrEl.textContent = `${parseFloat(wr).toFixed(0)}%`;
    wrEl.className = `m-value ${wr>=55?'good':wr<40?'bad':''}`;
  }

  const dd = d.stats?.drawdown;
  const ddEl = document.getElementById('m-drawdown');
  if(dd!=null){
    ddEl.textContent = `${parseFloat(dd).toFixed(1)}%`;
    ddEl.className = `m-value ${dd>15?'bad':dd<8?'good':''}`;
  }

  const pos = d.cycle?.positions;
  if(pos!=null) document.getElementById('m-positions').textContent = pos;
  if(d.total_trades!=null) document.getElementById('m-trades').textContent = d.total_trades;
}

// ── MONITOR SCREENS ──
function updateMonitors(d){
  // Scanner monitors
  const scanEvs = (d.events||[]).filter(e=>e.type==='scanner');
  if(scanEvs.length){
    const last = scanEvs[scanEvs.length-1].msg;
    document.getElementById('mon-scan1').textContent = last.substring(0,12);
    document.getElementById('mon-scan2').textContent = 'ACTIVE';
  }
  document.getElementById('mon-scan3').textContent = d.cycle?.cycle ? `C#${d.cycle.cycle}` : '---';

  // Risk monitors
  const dd = d.stats?.drawdown;
  document.getElementById('mon-risk').innerHTML =
    `<span style="font-size:8px">${dd!=null?dd.toFixed(1)+'%':'--'}\nDD</span>`;

  // Claude monitors
  const pos = d.cycle?.positions ?? '--';
  document.getElementById('mon-claude1').textContent = `P:${pos}`;
  const wr = d.stats?.win_rate;
  document.getElementById('mon-claude2').textContent = wr!=null ? `${wr.toFixed(0)}%WR` : '---';

  // Tape monitors
  const tapeEvs = (d.events||[]).filter(e=>e.type==='tape');
  if(tapeEvs.length){
    const t = tapeEvs[tapeEvs.length-1].msg;
    document.getElementById('mon-tape1').textContent = 'FLOW';
    document.getElementById('mon-tape2').textContent = t.substring(0,10);
  }
  document.getElementById('mon-tape3').textContent = d.stats?.trades!=null ? `${d.stats.trades}TR` : '---';

  // Jonas monitors
  const bal = d.stats?.balance;
  document.getElementById('mon-jonas1').textContent = bal!=null ? `$${parseFloat(bal).toFixed(0)}` : '---';
  const pnl = d.stats?.total_pnl;
  document.getElementById('mon-jonas2').textContent = pnl!=null ?
    `${pnl>=0?'+':''}${parseFloat(pnl).toFixed(1)}` : '---';
}

// ── AGENT BUBBLES from data (idle chatter between walks) ──
function updateAgentBubbles(d){
  const evs = d.events||[];
  const pick = arr => arr[Math.floor(Math.random()*arr.length)];
  const short = s => (s||'').replace('/USDT:USDT','').replace('/USDT','');

  // Scanner — idle thoughts about what they're seeing
  const holds = evs.filter(e=>e.type==='hold');
  if(holds.length){
    const recent = holds.slice(-3);
    const syms = [...new Set(recent.map(h=>short(h.symbol)))].join(', ');
    const last = recent[recent.length-1];
    const det = last.detail || '';
    const adxMatch = det.match(/ADX=([\d.]+)/);
    const chopMatch = det.match(/CHOP=([\d.]+)/);
    const adx = adxMatch ? parseFloat(adxMatch[1]) : 0;
    const chop = chopMatch ? parseFloat(chopMatch[1]) : 0;
    const msgs = [];
    if(adx < 15) msgs.push(`${short(last.symbol)} is flatlined. ADX ${adx.toFixed(0)}... nothing to work with.`);
    else if(adx > 30 && chop > 50) msgs.push(`${short(last.symbol)}'s got some movement but it's choppy. Not worth the risk.`);
    else if(adx > 25) msgs.push(`${short(last.symbol)} is building momentum, ADX ${adx.toFixed(0)}. Could set up soon.`);
    else msgs.push(`Checked ${syms} — all quiet. Nobody's trending.`);
    msgs.push(`Still grinding through the list. ${syms} looked at so far this cycle.`);
    setBubble('scanner', pick(msgs));
  }

  // Risk Manager — monitoring stress levels
  const riskEvs = evs.filter(e=>['cooldown','regime','drawdown','ban'].includes(e.type));
  const dd = d.stats?.drawdown ?? 0;
  const wr = d.stats?.win_rate ?? 0;
  const pos = d.cycle?.positions ?? 0;
  if(riskEvs.length){
    const last = riskEvs[riskEvs.length-1];
    if(last.type==='cooldown') setBubble('risk', `Just pulled a pair offline after that loss. Cooling down.`);
    else if(last.type==='regime') setBubble('risk', `Three L's in a row. We're sitting out for 15 minutes.`);
    else setBubble('risk', last.msg.substring(0,60));
  } else if(dd > 15){
    setBubble('risk', pick([
      `${dd.toFixed(1)}% drawdown... I'm watching this closely.`,
      `Getting a bit warm in here. DD at ${dd.toFixed(1)}%.`,
      `${pos} open, ${dd.toFixed(1)}% down from peak. Not great.`,
    ]));
  } else {
    setBubble('risk', pick([
      `Everything's in check. ${pos} open, ${dd.toFixed(1)}% DD.`,
      `Risk is manageable. Win rate sitting at ${wr.toFixed(0)}%.`,
      `${pos} position${pos!==1?'s':''} tracked. Limits look fine.`,
    ]));
  }

  // Tape Reader
  const tapeEvs = evs.filter(e=>['tape','orderbook','depth'].includes(e.type));
  if(tapeEvs.length){
    const last = tapeEvs[tapeEvs.length-1];
    const msg = last.msg || '';
    const aggrMatch = msg.match(/aggr=([\d.]+)/);
    if(aggrMatch){
      const aggr = parseFloat(aggrMatch[1]);
      if(aggr > 0.6) setBubble('tape', pick([`Buyers stepping up. Aggr ratio ${aggr.toFixed(2)}.`, `Buy pressure building — ${aggr.toFixed(2)} aggressor.`]));
      else if(aggr < 0.4) setBubble('tape', pick([`Sellers dominant right now. ${aggr.toFixed(2)} aggr.`, `Heavy selling. Would not go long here.`]));
      else setBubble('tape', `Balanced flow, nobody committing. ${aggr.toFixed(2)} aggr.`);
    } else if(last.type==='depth'){
      setBubble('tape', msg.replace(/\[DEPTH\]\s*/,'').substring(0,55));
    } else {
      setBubble('tape', msg.replace(/\[(TAPE|OB)\]\s*/,'').substring(0,55));
    }
  } else {
    setBubble('tape', pick([`Tape's quiet. Just noise.`, `Nothing on the flow worth flagging.`, `Waiting for volume to pick up.`]));
  }

  // Jonas — the boss reacting to performance
  const pnl = d.stats?.total_pnl ?? 0;
  const bal = d.stats?.balance;
  const trades = d.stats?.trades ?? 0;
  if(bal!=null){
    if(pnl > 5) setBubble('jonas', pick([
      `$${bal.toFixed(0)} and climbing. This is what I like to see.`,
      `+$${pnl.toFixed(2)} today. Good work, team. Stay sharp.`,
    ]));
    else if(pnl > 0) setBubble('jonas', pick([
      `$${bal.toFixed(0)} in the account. ${wr.toFixed(0)}% WR across ${trades} trades. Acceptable.`,
      `Slightly green at +$${pnl.toFixed(2)}. Room for improvement but at least we're not bleeding.`,
    ]));
    else if(pnl > -3) setBubble('jonas', pick([
      `$${pnl.toFixed(2)}... basically flat. The opportunities will come.`,
      `$${bal.toFixed(0)} balance. Small drawdown. I've seen worse days.`,
    ]));
    else setBubble('jonas', pick([
      `Down $${Math.abs(pnl).toFixed(2)}. I'm not happy but the system works long-term.`,
      `${trades} trades, ${wr.toFixed(0)}% WR, $${pnl.toFixed(2)} net. We need better entries, Claude.`,
      `Rough session. $${bal.toFixed(0)} left. Let's not dig the hole deeper.`,
    ]));
  }

  // Claude at own desk — thinking about the current state
  if(state.claudePos==='claude'){
    const lastClose = evs.filter(e=>e.type==='close').pop();
    const lastEntry = evs.filter(e=>e.type==='entry').pop();
    if(lastEntry){
      setBubble('claude', `Got a ${lastEntry.side||''} on ${short(lastEntry.symbol)}. Watching it closely.`);
    } else if(lastClose){
      const cpnl = lastClose.pnl;
      if(cpnl > 0) setBubble('claude', `Nice — ${short(lastClose.symbol)} closed green. +$${cpnl.toFixed(2)}.`);
      else setBubble('claude', `${short(lastClose.symbol)} stopped out. ${cpnl?.toFixed(2)} USDT. Moving on.`);
    } else if(pos > 0){
      setBubble('claude', pick([
        `${pos} running. Monitoring exits and scanning for the next setup.`,
        `Watching my ${pos} position${pos!==1?'s':''}. Breakeven check every cycle.`,
      ]));
    } else {
      setBubble('claude', pick([
        `Book is empty. Running through signals... waiting for something clean.`,
        `Nothing open yet. Scanning ${d?.events?.filter(e=>e.type==='hold').length||0} pairs this cycle.`,
        `Patience. The setups come when the market's ready, not when I am.`,
      ]));
    }
  }
}

// ── NEW EVENTS → FEED ──
function processNewEvents(d){
  const evs = d.events||[];
  const startIdx = Math.max(0, evs.length - 8);
  for(let i=startIdx; i<evs.length; i++){
    const ev = evs[i];
    const key = ev.time + ev.type + ev.msg?.substring(0,20);
    if(!state.seenKeys) state.seenKeys = new Set();
    if(state.seenKeys.has(key)) continue;
    state.seenKeys.add(key);
    if(state.seenKeys.size > 200) {
      const iter = state.seenKeys.values();
      state.seenKeys.delete(iter.next().value);
    }

    addFeedLine(ev.time, eventSummary(ev), eventClass(ev));

    // Trade fired → particles + radar blip
    if(ev.type==='entry'||ev.type==='fill'){
      spawnParticles(ev.side==='SHORT'?'#ff4466':'#00ff88', 10);
      addRadarBlip();
    }
    if(ev.type==='close' && ev.pnl!=null){
      spawnParticles(ev.pnl>=0?'#00ff88':'#ff4466', 8);
    }
  }
}

// ── WARNING LIGHTS ──
function updateWarningLights(d){
  const dd = d.stats?.drawdown ?? 0;
  const hasCooldown = (d.events||[]).some(e=>['cooldown','ban','regime'].includes(e.type));
  // red: drawdown >15 or ban mode
  document.getElementById('wl-r').style.animationPlayState = (dd>15||hasCooldown) ? 'running':'paused';
  document.getElementById('wl-r').style.opacity = (dd>15||hasCooldown) ? '1':'0.2';
  // amber: 8-15%
  document.getElementById('wl-a').style.animationPlayState = (dd>8&&dd<=15) ? 'running':'paused';
  document.getElementById('wl-a').style.opacity = (dd>8&&dd<=15) ? '1':'0.2';
  // green: all good
  document.getElementById('wl-g').style.opacity = dd<=8 ? '1':'0.2';
}

// ── MAIN FETCH LOOP ──
async function fetchData(){
  try{
    const r = await fetch('/api/data');
    const d = await r.json();
    state.data = d;

    updateHUD(d);
    updateMonitors(d);
    updateAgentBubbles(d);
    updateBlotter(d.recent_trades||[]);
    processNewEvents(d);
    updateWarningLights(d);

  } catch(e){
    addFeedLine(null, `Connection error: ${e.message}`, 'log-red');
  }
}

// ── TIMERS ──
fetchData();
setInterval(fetchData, 3000);

// Claude walks every 20s
setInterval(updateClaudeWalk, 20000);

// Initial bubbles after 2s
setTimeout(()=>{
  setBubble('scanner', 'Scanning top 5 movers by volume...');
  setBubble('risk', 'All systems nominal. Drawdown within limits.');
  setBubble('tape', 'Monitoring order flow and depth...');
  setBubble('claude', 'War Room online. Watching all channels.');
  setBubble('jonas', 'Run the system. Trust the edge. Lets go.');
}, 2000);

// Auto-rotate bubbles for idle agents
setInterval(()=>{
  const d = state.data;
  if(!d) return;
  const idle_scanner = [
    'Checking top pair volumes...',
    'ETH and BTC leading the board',
    'Filtering pairs above $10M vol',
    'Spread check: all pairs within limits',
  ];
  const idle_tape = [
    'Monitoring aggressor ratio...',
    'Watching for large block trades',
    'Order book depth looks healthy',
    'Tracking bid/ask imbalance...',
  ];
  const idle_claude = [
    'Signal matrix: all inputs nominal',
    'ADX filters active across 14 pairs',
    'Regime monitor: green',
    'Running technical confluence checks...',
  ];

  if(state.claudePos!=='scanner') setBubble('scanner', idle_scanner[Math.floor(Math.random()*idle_scanner.length)]);
  if(state.claudePos!=='tape')    setBubble('tape',    idle_tape[Math.floor(Math.random()*idle_tape.length)]);
  if(state.claudePos==='claude')  setBubble('claude',  idle_claude[Math.floor(Math.random()*idle_claude.length)]);
}, 7000);
</script>
</body>
</html>"""


# ── HTTP Handler ────────────────────────────────────────────────────────────

class WRHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_GET(self):
        if self.path == "/":
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/data":
            try:
                data = _build_api_response()
                body = json.dumps(data, default=str).encode("utf-8")
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/jonas_avatar.jpg":
            try:
                with open(AVATAR_FILE, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


# ── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), WRHandler)
    print(f"[WAR ROOM] AI War Room running at http://{HOST}:{PORT}")
    print(f"[WAR ROOM] Reading: {LOG_FILE}, {STATE_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[WAR ROOM] Shutting down.")
        server.server_close()
