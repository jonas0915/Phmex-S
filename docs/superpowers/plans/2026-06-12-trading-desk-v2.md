# Trading Desk v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 3D trading desk truthful (real data on every screen), alive (behaviors keyed to real events), and smooth (~30fps floor), per the approved spec.

**Architecture:** trading_desk.py stays a single file (Python server lines 1–338, `HTML_PAGE` JS blob 339–9153, handler 9156+). Python gains guarded data fields on `/api/data`; JS gains a change-detecting monitor redraw layer and an event→behavior map over existing primitives. Performance work gates the fidelity work.

**Tech Stack:** Python 3.14 stdlib, Three.js 0.160 (already vendored/imported as-is), pytest.
Test cmd: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest tests/ -q` (current baseline: 83 passed).

**Spec (authoritative):** `docs/superpowers/specs/2026-06-12-trading-desk-v2-design.md`.
**Hard rules:** read-only files (state + logs), zero exchange calls, 127.0.0.1, honesty rule (real value or absent — never invented), 12-hr PT display, log clock is EASTERN. Bot is NEVER touched; only the desk process restarts (Task 6).

**Verified anchors (re-verify before editing):** `_parse_log_events` :39 · `_build_api_response` :181 · `monitorCanvases` :514 · speech-bubble creation :6309 · scanner monitor Math.random vol bar ~:6793 · `updateAllMonitors` :7302 · `fetchData` :8426 (3s setInterval; calls updateHUD/updateAllMonitors/checkTherapyTriggers) · team-event machinery :578-585 + :8773.

---

### Task 1: Python `/api/data` truth fields (TDD)

**Files:**
- Modify: `trading_desk.py` (Python section only, lines 1–338)
- Create: `tests/test_trading_desk_v2.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_trading_desk_v2.py
import sys, json, time
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import trading_desk as td

SAMPLE = """
2026-06-12 09:52:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.3)
2026-06-12 09:53:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.9)
2026-06-12 09:52:09 [DEBUG] [HOLD] INJ/USDT:USDT — No confluence signal (1h ADX=23.2)
""".strip().splitlines()

def test_parse_pair_adx_newest_wins():
    adx = td.parse_pair_adx(SAMPLE)
    assert adx["ZEC/USDT:USDT"] == 15.9
    assert "DOGE/USDT:USDT" not in adx          # absent stays absent

def test_slot_truth_shape():
    slots = td.build_slot_truth()
    assert isinstance(slots, list)
    for s in slots:
        assert {"id", "live", "trades", "wr", "net_pnl"} <= set(s.keys())
        if s["live"]:
            assert {"live_net", "headroom", "live_trades"} <= set(s.keys())

def test_api_response_has_truth_fields():
    r = td._build_api_response()
    assert "slots" in r and "watcher" in r and "pair_adx" in r and "top_gates" in r
    assert isinstance(r["watcher"], bool)
```

- [ ] **Step 2: Run → fails** (AttributeError: parse_pair_adx).

- [ ] **Step 3: Implement in the Python section** — port these from web_dashboard.py
(read its current versions and copy with a `# ported from web_dashboard.py — keep
in sync` comment; do NOT import web_dashboard, the processes stay decoupled):
`parse_pair_adx(lines)` (regex + newest-wins), `_watcher_enabled()` with its 30s
cache + seek-tail + full-file grep fallback, `_gate_stats`-equivalent with Eastern
(`ZoneInfo("America/New_York")`) timestamps + 30s cache (name it `gate_counts_24h()`
returning the counts dict). New `build_slot_truth()`:

```python
def build_slot_truth() -> list:
    """Per-slot truth for desk monitors. Net basis; live slots add guardrail fields."""
    out = []
    import glob as _g
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
        def _net(t):
            v = t.get("net_pnl")
            return float(v) if v is not None else float(t.get("pnl_usdt", 0))
        wins = sum(1 for t in trades if _net(t) > 0)
        rec = {"id": slot_id,
               "trades": len(trades),
               "wr": round(wins / len(trades) * 100, 1) if trades else 0,
               "net_pnl": round(sum(_net(t) for t in trades), 2),
               "live": False}
        try:
            with open(os.path.join(BASE_DIR, f"trading_state_{slot_id}_mode.json")) as f:
                rec["live"] = not json.load(f).get("paper_mode", True)
        except (OSError, json.JSONDecodeError):
            pass
        if rec["live"]:
            live = [t for t in trades if t.get("mode") == "live"]
            live_net = round(sum(_net(t) for t in live), 2)
            rec.update({"live_net": live_net,
                        "headroom": round(5.0 + live_net, 2),
                        "live_trades": len(live)})
        out.append(rec)
    return out
```

(Check what the file's project-dir constant is actually called — survey said
`LOG_FILE`/`STATE_FILE` exist; if there's no BASE_DIR, derive
`BASE_DIR = os.path.dirname(os.path.abspath(__file__))` consistent with existing
constants.) Wire all four into `_build_api_response()` (line ~181): `slots`,
`watcher`, `pair_adx` (from the same tail lines the function already reads — reuse
its existing tail, don't add a second read), `top_gates` (top 4 of gate_counts_24h
as `[["adx", 14729], ...]`).

- [ ] **Step 4: Run tests → pass; FULL suite → expect 86 (83 + 3, report actual); py_compile.**
- [ ] **Step 5: Commit** `git add trading_desk.py tests/test_trading_desk_v2.py && git commit -m "feat(desk): truth fields on /api/data — slots, watcher, pair_adx, top_gates"`

---

### Task 2: Truthful monitors + redraw discipline (JS)

**Files:**
- Modify: `trading_desk.py` (HTML_PAGE JS only)

- [ ] **Step 1: ANCHOR-VERIFY.** Read `updateAllMonitors` (:7302 area) and the
per-desk monitor draw functions it calls; find the scanner desk's
`Math.random()` vol bar (~:6793). Map which draw function serves which desk
(scanner, risk, executor, wallwatch, walldash). Report the map in your summary.

- [ ] **Step 2: Redraw discipline.** Add a change-hash gate so each monitor canvas
redraws only when its data slice changed:

```javascript
const _monHash = {};
function monChanged(key, slice){
  const h = JSON.stringify(slice);
  if(_monHash[key] === h) return false;
  _monHash[key] = h; return true;
}
```

In `updateAllMonitors`, wrap each desk's draw call:
`if(monChanged('scanner', [apiData.pair_adx, apiData.watchlist])) drawScannerMonitor(...);`
— adapt key/slice per desk to exactly the fields that desk renders (the slice must
include every field the draw reads, else the monitor goes stale; list your slices
in the summary). Canvas textures must set `texture.needsUpdate = true` only when
redrawn (verify how the existing code flags texture updates and keep that
mechanism).

- [ ] **Step 3: Truthful content.**
- Scanner desk: replace the Math.random vol bar with per-pair ADX bars from
  `apiData.pair_adx`: for each of up to 6 pairs, bar width = min(adx,45)/45 of the
  bar area, green when ≥25 else amber; pairs absent from pair_adx render a dim
  dash. Label "1H ADX vs 25".
- Risk desk: add drawdown (existing field) + mean_revert guardrail: find the slot
  in `apiData.slots` with id "5m_mean_revert"; if live, draw "HDRM $X.XX / $5.00"
  with a depletion bar (width = max(0, headroom/5)*barWidth, green→amber); if not
  live or absent, draw "MR: paper" dim.
- Executor desk: "WATCHER ON/OFF" from `apiData.watcher` (green/red) + the newest
  event of type matching /live.?exit/i from apiData.events when present (one line,
  truncated 28 chars).
- Wallwatch: append a bottom row: "MR-LIVE  net $X.XX  hdrm $X.XX" (or "MR paper").
- Walldash: ensure PnL figures it draws are labeled "net" (check what field it
  reads — if it renders gross today, switch to the net fields now available in
  apiData.slots/state and label accordingly).
NEVER invent a value: absent data renders dim dashes. All strings drawn via
canvas fillText (no innerHTML — no escaping concern in-canvas).

- [ ] **Step 4: Verify.** py_compile + import smoke (`python3 -c "import trading_desk"`
must not raise) + full pytest suite (expect 86). If `which node` finds node, also
extract the JS between `<script type="module">` and `</script>` to a temp file and
run `node --check` on it for a syntax gate; skip silently if node is absent.
Visual verification happens in Task 6.
- [ ] **Step 5: Commit** `git commit -am "feat(desk): truthful monitors + change-gated redraws"`

---

### Task 3: Event→behavior map (JS)

**Files:**
- Modify: `trading_desk.py` (HTML_PAGE JS only)

- [ ] **Step 1: ANCHOR-VERIFY.** Read `fetchData` (:8426), the events array
consumption, speech-bubble helpers (:6309/:7314 area), therapy trigger
(`checkTherapyTriggers`), team-event machinery (:578-585, :8773), and the
strategy→desk/agent mapping (which agent represents which strategy — survey
says desks: scanner/risk/ensemble/tape/jonas/executor/strategy/ws_feed/
pos_monitor). Report the agent-name constants you found.

- [ ] **Step 2: Implement** a marked section `// === EVENT→BEHAVIOR MAP (desk v2) ===`:

```javascript
const _seenEvt = new Set();
function evtKey(e){ return (e.time||'') + '|' + (e.type||'') + '|' + (e.text||'').slice(0,40); }
function processStoryEvents(){
  if(!apiData || !apiData.events) return;
  for(const e of apiData.events){
    const k = evtKey(e);
    if(_seenEvt.has(k)) continue;
    _seenEvt.add(k);
    if(_seenEvt.size > 200){ const it=_seenEvt.values(); _seenEvt.delete(it.next().value); }
    routeStoryEvent(e);
  }
}
```

`routeStoryEvent(e)` cases (reuse ONLY existing primitives — speech via the
existing bubble helper, plumbob color setters, walk routines, comms feed append):
- `close` with positive pnl → owning agent (map strategy name → agent; default
  "strategy") speech "+$X.XX <sym> ✔", plumbob green pulse 10s, comms line.
- `close` negative → speech "−$X.XX <sym>", plumbob grey 10s; let the EXISTING
  therapy trigger handle walks (do not duplicate it — just don't block it).
- event text matching /\[LIVE EXIT\]/ → executor walks to ensemble desk using the
  existing report-to-Claude walk routine if one exists (survey says "agents report
  to Claude (ensemble desk) after certain events" — reuse that function), speech
  "enforced <sym> exit".
- /PROMOTED/ → trigger the existing team-meeting gather at the conference table
  (reuse the full-team-meeting routine guarded by its existing busy flags), comms
  "🚀 <slot> promoted to live".
- /DEMOTED|auto-demote/ → walk of shame: owning agent + 2 nearest walk to the B1
  rec area via the existing team-event location for rec area (reuse teamEvents
  machinery with a one-off event object), gloom bubbles, comms "⬇ <slot> demoted".
- Guard EVERYTHING: if a routine's busy-flags (claudeWalking, teamEventActive,
  inMeeting, …) are set, SKIP the behavior (drop, don't queue) — story events are
  garnish, never deadlock the sim.
Call `processStoryEvents()` from `fetchData` after `updateAllMonitors()`.
**On first load, pre-seed `_seenEvt` with all current events WITHOUT firing
behaviors** (a page refresh must not replay history).

- [ ] **Step 3: Verify** py_compile + import + suite (86). Step 4: Commit
`git commit -am "feat(desk): event-driven story behaviors keyed to real events"`

---

### Task 4: Performance floor

**Files:**
- Modify: `trading_desk.py` (JS only)

- [ ] **Step 1: Instrument.** Add a 5s console FPS/draw-call sampler:

```javascript
let _fpsN=0,_fpsT=performance.now();
function _fpsTick(){ _fpsN++; const now=performance.now();
  if(now-_fpsT>5000){ console.log(`[PERF] fps=${(_fpsN/((now-_fpsT)/1000)).toFixed(1)} calls=${renderer.info.render.calls}`);
    _fpsN=0; _fpsT=now; } }
```
Call from `animate()`. (Keep it — it's diagnostic, cheap, console-only.)

- [ ] **Step 2: animate() audit.** Read the animate loop. Move per-frame work that
doesn't need 30fps to a frame-modulo bucket: bay-fog opacity, water-wave vertex
math, label distance/visibility checks → every 4th rendered frame
(`if(frameCount % 8 === 0)` given the existing %2 frame skip — verify the existing
skip and compose correctly). Do NOT touch AnimationMixer updates or camera controls
(those need every rendered frame).

- [ ] **Step 3: Texture redraw audit.** Confirm Task 2's monChanged gates cover ALL
canvas-texture redraws including wall screens and conference TV; any remaining
unconditional canvas redraws in the data path get the same gate. updateTimeOfDay's
panorama regeneration: verify it runs on its slow clock only (survey says
real-clock schedule) — if any call path triggers it per-poll, gate it to
change-of-period only.

- [ ] **Step 4: Verify** py_compile + import + suite. Record in your report the
[PERF] lines you'd expect (actual numbers come from Jonas's browser in Task 6 —
do NOT fabricate fps numbers; you cannot run a browser).
- [ ] **Step 5: Commit** `git commit -am "perf(desk): frame-modulo bucketing, gated texture redraws, fps sampler"`

---

### Task 5: Fidelity within budget

**Files:**
- Modify: `trading_desk.py` (JS only)

- [ ] **Step 1:** Window glass: locate the penthouse glass material; if it's
`MeshPhysicalMaterial`/`MeshStandardMaterial`, set a pre-baked environment via
`THREE.CubeTextureLoader` ONLY if cube assets exist under assets/ — they don't, so
instead use the cheap option: `scene.environment = pmremGenerator.fromScene(skyDomeScene)`
is too heavy per time-of-day regen; therefore: bump glass material props only
(`metalness 0.1, roughness 0.05, opacity/transmission per existing style`) +
a static `envMapIntensity` if an env map already exists. If no env map exists,
limit to material-prop polish. (Honesty: do what's cheap; report what you did.)
- [ ] **Step 2:** Warmer sunset/night palettes: in updateTimeOfDay's palette
constants, warm the sunset oranges and deepen night blues (small literal tweaks,
keep regen on its existing schedule).
- [ ] **Step 3:** Lamp glow: one shared radial-gradient canvas texture → `THREE.Sprite`
(AdditiveBlending, depthWrite false) added at each desk-lamp position, scale ~0.6.
Desks already have lamp objects — find their positions from the desk-building code.
- [ ] **Step 4:** Each item individually revertible (separate small commits OK).
py_compile + import + suite. Commit(s) `git commit -am "feat(desk): glass/palette/lamp-glow polish within fps budget"`

---

### Task 6: Verify live + desk-only restart

- [ ] **Step 1:** Full suite (expect 86) + py_compile.
- [ ] **Step 2:** Restart ONLY the desk:
```bash
pkill -f "Python.*trading_desk" 2>/dev/null; sleep 1
cd /Users/jonaspenaso/Desktop/Phmex-S
nohup /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python trading_desk.py >> logs/trading_desk.log 2>&1 &
sleep 3; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8060/      # 200
curl -s http://127.0.0.1:8060/api/data | python3 -c "import json,sys; d=json.load(sys.stdin); print('slots' in d, d.get('watcher'), len(d.get('pair_adx',{})))"
ps -p $(cat .bot.pid) -o pid,etime | tail -1   # bot untouched
```
- [ ] **Step 3:** Cross-check /api/data truth against ground truth (slot net vs
trading_state_5m_mean_revert.json; watcher vs log) — numbers must match exactly.
- [ ] **Step 4:** Tell Jonas to open http://127.0.0.1:8060 and confirm: scanner ADX
bars match the dashboard's why-no-trades panel, risk desk shows the headroom bar,
[PERF] console lines hold ≥~30fps. His eyes are the final gate for visuals.
