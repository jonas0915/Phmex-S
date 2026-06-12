# Dashboard v2 "Terminal Pro" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild web_dashboard.py's UI as the Jonas-approved amber-on-black "Terminal Pro" command grid with interactive equity chart, blotter drill-down, why-no-trades diagnostics, and mobile mode.

**Architecture:** Server architecture unchanged (stdlib ThreadingHTTPServer, read-only file reads, 3s `/api/content` innerHTML polling). The page shell is restructured so the uPlot chart lives OUTSIDE the swapped `#content` node. Matplotlib is removed entirely; equity ships as JSON via `/api/equity` rendered client-side by a vendored uPlot.

**Tech Stack:** Python 3.14 stdlib, uPlot 1.6.x (vendored, no CDN at runtime), pytest.
Test cmd: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest tests/ -q`

**Visual reference (authoritative):** the approved mockup at
`.superpowers/brainstorm/39778-1781273729/content/final-design.html` — match its
palette, density, and panel structure. Spec: `docs/superpowers/specs/2026-06-12-dashboard-terminal-pro-design.md`.

**Hard rules:** dashboard stays read-only (state files + logs only, ZERO exchange calls), binds 127.0.0.1, no-cache headers on HTML, all times 12-hour PT, PnL displays NET by default and labels basis. The BOT IS NOT TOUCHED — only the dashboard process restarts at the end.

**Current code anchors (verify before each task — file is 2,713 lines):**
`CHART_INTERVAL`/`_chart_cache` ~46-50 · matplotlib imports 32-35 · `refresh_charts` ~1259 ·
`chart_thread_loop` ~1280 · `build_content()` 1513 · footer ~1765 · `build_html()` 1769
(CSS ~1780-2355, JS ~2362-2409) · `build_trades_page()` 2414 · `do_GET` 2639 ·
chart thread start ~2698. Helpers already present: `_live_slot_ids()` ~982,
`read_all_slot_states()` ~267, `_build_observability_panel`, `_build_l2_monitor_panel`,
`_build_reconcile_card`, `read_state()` ~171.

---

### Task 1: Design tokens + page shell (ticker / grid / static chart node / feed)

**Files:**
- Modify: `web_dashboard.py` — `build_html()` (CSS + shell), `build_content()` (grid skeleton)
- Test: `tests/test_dashboard_v2.py` (create)

- [ ] **Step 1: Failing test**

```python
# tests/test_dashboard_v2.py
import re, sys, types
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")

def test_shell_structure():
    import web_dashboard as wd
    html = wd.build_html()
    # chart node must live OUTSIDE the swapped #content div
    content_pos = html.index('id="content"')
    equity_pos = html.index('id="equity-root"')
    assert equity_pos > html.index("<body")
    content_div = re.search(r'<div id="content".*?</div>\s*<!-- /content -->', html, re.S)
    assert content_div is not None
    assert 'id="equity-root"' not in content_div.group(0)
    # terminal palette present, old palette gone
    assert "#000204" in html and "#f0a500" in html
    assert "fonts.googleapis.com" not in html

def test_ticker_present():
    import web_dashboard as wd
    c = wd.build_content()
    assert 'class="ticker"' in c or 'id="ticker"' in wd.build_html()
```

- [ ] **Step 2: Run — fails** (`'equity-root'` not found).

- [ ] **Step 3: Implement.**
In `build_html()`: replace the entire `:root` CSS variable block and theme with:

```css
:root {
  --bg:#000204; --panel:#0a0e08; --border:#2d3a1e; --txt:#9eb89e;
  --amber:#f0a500; --pos:#4af626; --neg:#ff5555; --dim:#5a6b5a;
}
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--txt);
  font:11px/1.5 'SF Mono', Menlo, 'JetBrains Mono', monospace; }
#ticker { position:sticky; top:0; z-index:10; background:var(--panel);
  color:var(--amber); border-bottom:1px solid var(--border);
  padding:5px 10px; white-space:nowrap; overflow:hidden; font-size:12px; }
#grid { display:grid; grid-template-columns:repeat(3,1fr); gap:3px; padding:3px; }
.panel { background:var(--panel); border:1px solid var(--border); padding:6px;
  min-height:120px; overflow-y:auto; max-height:46vh; }
.panel .ptitle { color:var(--amber); letter-spacing:1.5px; font-size:9px;
  text-transform:uppercase; border-bottom:1px solid #1a2412;
  padding-bottom:3px; margin-bottom:5px; }
.panel table { width:100%; border-collapse:collapse; font-size:10px; }
.panel td, .panel th { padding:1px 5px 1px 0; text-align:left; }
.pos { color:var(--pos); } .neg { color:var(--neg); } .dim { color:var(--dim); }
#feed { margin:0 3px 3px; }
```

Drop the Google Fonts `<link>`. Restructure the `<body>` to:

```html
<body>
  <div id="ticker"></div>
  <div id="content"><!-- grid panels, swapped every 3s --></div><!-- /content -->
  <div class="panel" id="equity-root" style="margin:0 3px;">
    <div class="ptitle">EQUITY — loading…</div><div id="equity-chart"></div>
  </div>
  <div id="feed" class="panel"></div>
  <script> /* existing 3s poller, now also updates #ticker and #feed from
     data-* payloads; see Step 3b */ </script>
</body>
```

`build_content()` returns ONLY the `#grid` inner panels (placeholders for now:
six `.panel` divs titled POSITIONS / SLOTS+GUARDRAILS / BLOTTER / WHY NO TRADES? /
GATES+WATCHLIST / (sixth reserved — EQUITY sits outside). Ticker + feed content:
add two new builders used by `/api/content` consumers:

```python
def build_ticker() -> str:
    state = read_state()
    bal = state.get("balance") or 0.0
    today = _today_net_pnl(state)          # helper: sum _net of trades closed today PT
    arrow = "▲" if today >= 0 else "▼"
    cls = "pos" if today >= 0 else "neg"
    hdrm = _mr_headroom()                  # 5.0 + live net pnl of 5m_mean_revert, None if not live
    watcher = "ON" if _watcher_enabled() else "OFF"
    now = datetime.now(PT_TZ).strftime("%-I:%M:%S %p PT")
    parts = [f"PHMEX-S", f"BAL ${bal:.2f} <span class='{cls}'>{arrow}{abs(today):.2f}</span>"]
    if hdrm is not None:
        parts.append(f"MR-LIVE HDRM ${hdrm:.2f}")
    parts += [f"DD {_drawdown_pct(state):.1f}%", f"POS {_open_pos_count()}",
              f"WATCHER <span class='{'pos' if watcher=='ON' else 'neg'}'>{watcher}</span>",
              f"CYC {_latest_cycle()}", now]
    return " ▮ ".join(parts)
```

Implement the small helpers (`_today_net_pnl`, `_mr_headroom` reading
`trading_state_5m_mean_revert{,_mode}.json`, `_watcher_enabled()` = "[LIVE EXIT] watcher enabled"
appears after the last "Volume scanner ON" line in the log tail, `_latest_cycle()` regex
on log tail, `_open_pos_count()` = main + live-slot positions). Every file read
try/excepted to safe defaults. Reuse the existing PT timezone object the file already
has (grep `ZoneInfo\|PT` first; if none, `PT_TZ = ZoneInfo("America/Los_Angeles")`).
Wire `/api/content` to return `build_ticker() + "\x00" + build_content() + "\x00" + build_feed()`
— NO: keep it simple and robust instead: change `/api/content` to return JSON
`{"ticker": ..., "content": ..., "feed": ...}` and update the poller JS:

```javascript
async function poll(){
  try{
    const r = await fetch('/api/content'); const j = await r.json();
    document.getElementById('ticker').innerHTML = j.ticker;
    document.getElementById('content').innerHTML = j.content;
    document.getElementById('feed').innerHTML = j.feed;
  }catch(e){}
}
setInterval(poll, 3000); poll();
```

`build_feed()` = the existing activity-feed builder's content (move/rename the
current feed panel builder; keep its event parsing + colors, restyle classes).

- [ ] **Step 4: Run tests** — new tests pass; full suite green (80 + new).
- [ ] **Step 5: Commit** `git commit -am "feat(dashboard): terminal-pro shell — tokens, ticker, grid, JSON content API"`

---

### Task 2: Vendor uPlot + `/api/equity` + client chart

**Files:**
- Create: `static/uplot.iife.min.js`, `static/uplot.min.css` (vendored)
- Modify: `web_dashboard.py` — remove matplotlib stack; add equity endpoint + static route + chart JS
- Test: `tests/test_dashboard_v2.py`

- [ ] **Step 1: Vendor uPlot (build-time download only):**
```bash
mkdir -p static
curl -sL https://unpkg.com/uplot@1.6.30/dist/uPlot.iife.min.js -o static/uplot.iife.min.js
curl -sL https://unpkg.com/uplot@1.6.30/dist/uPlot.min.css -o static/uplot.min.css
head -c 100 static/uplot.iife.min.js   # sanity: starts with banner/var uPlot
```

- [ ] **Step 2: Failing test**

```python
def test_equity_endpoint_shape(tmp_path, monkeypatch):
    import web_dashboard as wd
    data = wd.build_equity_series("all")
    assert set(data.keys()) == {"t", "v", "meta"}
    assert len(data["t"]) == len(data["v"]) == len(data["meta"])
    if data["meta"]:
        m = data["meta"][0]
        assert {"sym", "strat", "pnl", "reason", "win"} <= set(m.keys())

def test_equity_sentinel_era_subset():
    import web_dashboard as wd
    a = wd.build_equity_series("all"); s = wd.build_equity_series("sentinel")
    assert len(s["t"]) <= len(a["t"])
```

- [ ] **Step 3: Implement `build_equity_series(era)`** — pure function over
`read_state()["closed_trades"]` (+ live-slot closed trades merged, mode-tagged):
cumulative NET pnl (`_net`-equivalent: prefer `net_pnl`, fallback `pnl_usdt`),
x = close timestamps, era="sentinel" filters trades after the Sentinel deploy
timestamp already used by the old sentinel chart (find the constant/logic in
`_make_cumulative_pnl_sentinel` ~line 1259 region and reuse the same cutoff).
`meta[i] = {"sym","strat","pnl","reason","win","time_pt"}` (12-hr PT string).

Routes in `do_GET`: `GET /api/equity?era=...` → JSON; `GET /static/<name>` →
serve the two vendored files from `os.path.join(PROJECT_DIR,"static")` with
correct content-type, 404 anything else (no path traversal: `name = os.path.basename(...)`).

Client: in `build_html()` head, `<link href="/static/uplot.min.css">` +
`<script src="/static/uplot.iife.min.js">`; chart JS:

```javascript
let plot=null, era='sentinel';
async function loadEquity(){
  try{
    const r=await fetch('/api/equity?era='+era); const d=await r.json();
    const opts={width:document.getElementById('equity-chart').clientWidth||800,
      height:180, scales:{x:{time:true}},
      series:[{}, {label:'NET PnL', stroke:'#f0a500', width:1.5,
        points:{show:true, size:5,
          fill:(u,si,i)=> d.meta[i] && d.meta[i].win ? '#4af626' : '#ff5555'}}],
      axes:[{stroke:'#5a6b5a',grid:{stroke:'#1a2412'}},{stroke:'#5a6b5a',grid:{stroke:'#1a2412'}}],
      cursor:{}, legend:{show:false}};
    const node=document.getElementById('equity-chart'); node.innerHTML='';
    plot=new uPlot(opts,[d.t,d.v],node);
    // tooltip: on cursor move show meta of nearest idx in a small absolute div
    /* implement: div#eqtip absolutely positioned; plot.over.addEventListener('mousemove', ...) reading plot.cursor.idx, fill from d.meta[idx] (time_pt, sym, strat, pnl, reason) */
  }catch(e){ document.getElementById('equity-root').querySelector('.ptitle').textContent='EQUITY — chart assets missing'; }
}
function setEra(e){ era=e; loadEquity(); }
loadEquity(); setInterval(loadEquity, 30000);
```

Era toggle: two buttons `[SENTINEL] [ALL]` in the equity panel title bar calling `setEra`.

**Remove the matplotlib stack:** imports (lines 32-35), `CHART_INTERVAL`,
`_chart_cache`, `_chart_lock`, `_chart_version`, `refresh_charts`,
`_make_cumulative_pnl*`, `_make_pnl_by_reason`, `chart_thread_loop`, the thread
start at ~2698, the `/chart/` route, and the `has_charts` blocks in `build_content`.
Grep `matplotlib\|_chart_\|plt\.` afterward — zero hits allowed.

- [ ] **Step 4: Tests + full suite green.**
- [ ] **Step 5: Commit** `git commit -am "feat(dashboard): interactive uPlot equity + /api/equity; matplotlib removed"`

---

### Task 3: Blotter (merged, mode-tagged) + drill-down endpoint

**Files:**
- Modify: `web_dashboard.py`
- Test: `tests/test_dashboard_v2.py`

- [ ] **Step 1: Failing tests**

```python
def test_merged_blotter_rows():
    import web_dashboard as wd
    rows = wd.collect_blotter_rows(limit=500)
    assert isinstance(rows, list)
    if rows:
        r = rows[0]
        assert {"id", "time_pt", "sym", "side", "strat", "net", "reason", "owner"} <= set(r.keys())
        ts = [x["ts"] for x in rows]
        assert ts == sorted(ts, reverse=True)  # newest first

def test_trade_detail_endpoint():
    import web_dashboard as wd
    rows = wd.collect_blotter_rows(limit=5)
    if rows:
        d = wd.build_trade_detail(rows[0]["id"])
        assert "snapshot" in d  # dict or the string "no snapshot recorded"
```

- [ ] **Step 2: Implement.**
`collect_blotter_rows(limit)`: main `read_state()["closed_trades"]` (owner "main")
+ each slot state's closed_trades (owner = slot_id, include `mode` field), build
stable `id` = `f"{owner}:{index_in_that_file}"`, sort by close timestamp desc.
`build_trade_detail(id)`: re-read the owning file, pull the trade dict, return
`{"trade": {display fields}, "snapshot": trade.get("entry_snapshot") or "no snapshot recorded",
"gate_tags": trade.get("gate_tags"), "fees": ..., "basis": "net"}` — everything
try/excepted; unknown id → `{"error": "not found"}`.
Route `GET /api/trade?id=<id>` → JSON.
Blotter panel HTML: table rows with `onclick="drill(this,'<id>')"`; JS `drill()`
fetches `/api/trade`, inserts/toggles an expansion `<tr>` styled like the mockup
(amber left border, dim snapshot line: conf/layers, buy_ratio, cvd_slope, lt_bias,
ob imbalance, tags, fees). Because `#content` is swapped every 3s, expanded state
is lost on refresh — acceptable v1; note in code comment.
`/trades` route → `301 Location: /`; delete `build_trades_page()` (grep for other
callers first — the `_mode.json` skip added there moves into `collect_blotter_rows`'s
glob if that glob is reused; verify nothing else calls it).

- [ ] **Step 3: Tests + suite green. Step 4: Commit** `git commit -am "feat(dashboard): merged blotter + trade drill-down API"`

---

### Task 4: WHY NO TRADES? panel (TDD on the log parser)

**Files:**
- Modify: `web_dashboard.py`
- Test: `tests/test_dashboard_v2.py`

- [ ] **Step 1: Failing test**

```python
SAMPLE_LOG = """
2026-06-12 09:52:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.3)
2026-06-12 09:52:09 [DEBUG] [STRAT] l2_anticipation: 1h ADX 23.2 < 25
2026-06-12 09:52:09 [DEBUG] [HOLD] INJ/USDT:USDT — No confluence signal (1h ADX=23.2)
2026-06-12 09:53:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.9)
"""

def test_parse_pair_adx():
    import web_dashboard as wd
    adx = wd.parse_pair_adx(SAMPLE_LOG.strip().splitlines())
    assert adx["ZEC/USDT:USDT"] == 15.9     # newest wins
    assert adx["INJ/USDT:USDT"] == 23.2
    assert "DOGE/USDT:USDT" not in adx      # absent pair stays absent — never guess
```

- [ ] **Step 2: Implement** `parse_pair_adx(lines)` with regex
`\[HOLD\] (\S+) — No confluence signal \(1h ADX=([\d.]+)\)` iterating forward so
later lines overwrite. Panel builder `_build_why_no_trades()`:
- per scanned pair (the watchlist pairs already known to the dashboard): ADX value
  + a 9-block bar `▓`/`░` scaled 0–45 with the 25 threshold (≥25 renders green ✓,
  missing pair renders "—"),
- "last signal": newest non-HOLD `[ENTRY]`/`[SLOT LIVE] ... ENTRY`/`Position opened`
  line timestamp in the tail, as 12-hr PT + "ago",
- "top gate 24h": reuse the existing observability counts (grep
  `_build_observability_panel` for its data helper and call the same source).
Wire into the grid (panel 5).

- [ ] **Step 3: Tests + suite. Step 4: Commit** `git commit -am "feat(dashboard): why-no-trades diagnostics panel"`

---

### Task 5: POSITIONS + SLOTS/GUARDRAILS panels

**Files:**
- Modify: `web_dashboard.py`
- Test: `tests/test_dashboard_v2.py`

- [ ] **Step 1: Failing test**

```python
def test_guardrail_panel_math(tmp_path, monkeypatch):
    import web_dashboard as wd
    html = wd._build_slots_guardrails()
    assert "SLOTS" in html.upper()
    # if 5m_mean_revert is live, headroom string present
    import json, os
    mode = os.path.join(wd.PROJECT_DIR, "trading_state_5m_mean_revert_mode.json")
    if os.path.exists(mode) and not json.load(open(mode)).get("paper_mode", True):
        assert "headroom" in html.lower() or "HDRM" in html
```

- [ ] **Step 2: Implement.**
`_build_positions_panel()`: merge `read_state()["positions"]` + live slots'
positions (owner tag); columns sym/side/entry/SL/TP/age/strat/owner; uPnL "—"
unless a price for that symbol exists in already-read data; flat state → "flat —
no open positions" + last close line. Reconcile status from the existing
`_build_reconcile_card` data source — render ONLY when non-OK, as a red row.
`_build_slots_guardrails()`: per slot from `read_all_slot_states()` + mode sidecars:
status dot (LIVE `.pos`, paper amber, killed ✝ `.dim` — killed = negative Kelly at
≥50 trades, same rule as strategy_slot.is_killed, computed from the state file),
trades/WR/net PnL (net basis). For live slots: depletion bar
`width = max(0, (5.0 + live_net) / 5.0 * 100)%` with green→amber gradient,
caption `${5+live_net:.2f} of $5.00 · neg-Kelly @10 live trades ({n} so far)`.
Replace the old `_build_slots_overview` + sessions card usage in `build_content`
(sessions card DROPPED per spec). Old L2 monitor panel: render its readiness
summary as 1-2 compact rows inside GATES+WATCHLIST (next task) and delete the
big panel.

- [ ] **Step 3: Tests + suite. Step 4: Commit** `git commit -am "feat(dashboard): positions + slot guardrail panels"`

---

### Task 6: GATES+WATCHLIST panel, panel pruning, footer

**Files:**
- Modify: `web_dashboard.py`

- [ ] **Step 1:** `_build_gates_watchlist()`: top = 24h gate counts line (existing
observability data, one dim line: `ens 169 · hour 42 · sym 9 · …`); middle =
watchlist table (sym, vol, spread, readiness dot — reuse existing watchlist data
builder, restyle); bottom = L2 readiness compact rows (from old L2 panel's data).
Delete panels per spec: sessions, big L2 panel, reconcile card (now conditional row
in POSITIONS), live-vs-cascade comparison, NARROW panel — and their builder calls
in `build_content` (leave builder functions only if other code calls them; else delete).
Footer: `Auto-refresh 3s · Equity 30s · Read-only · Zero API calls · NET basis`.

- [ ] **Step 2:** Full suite + `py_compile`. Grep: `_build_session_card\|_build_paper_comparison\|NARROW` → no remaining call sites in build_content.
- [ ] **Step 3: Commit** `git commit -am "feat(dashboard): gates+watchlist panel, prune dead panels"`

---

### Task 7: Mobile mode

**Files:**
- Modify: `web_dashboard.py` (CSS only)

- [ ] **Step 1:** Append media query to the CSS block:

```css
@media (max-width:700px){
  #grid { grid-template-columns:1fr; }
  .panel { max-height:none; }
  #ticker { white-space:normal; font-size:11px; }
  /* order: slots/guardrails first, then positions, equity, blotter */
  #p-slots{order:1} #p-positions{order:2} #p-why{order:5}
  #p-gates{order:6} #p-blotter{order:4}
  #p-blotter tr:nth-child(n+12){display:none}
}
```
Give the six grid panels stable ids (`p-positions`, `p-slots`, `p-blotter`,
`p-why`, `p-gates` + reserved) in their builders. `#equity-root` sits between
content and feed already — order handled by document flow on mobile.
Add `<meta name="viewport" content="width=device-width, initial-scale=1">` to head.

- [ ] **Step 2:** `py_compile`; manual narrow-window check happens in Task 8. Commit `git commit -am "feat(dashboard): mobile stacked mode"`

---

### Task 8: Verification + dashboard restart (BOT UNTOUCHED)

- [ ] **Step 1:** Full suite green; `py_compile web_dashboard.py`.
- [ ] **Step 2:** Grep zero-hits: `matplotlib`, `_chart_cache`, `build_trades_page`, `fonts.googleapis`.
- [ ] **Step 3:** Restart ONLY the dashboard process:
```bash
pkill -f "Python.*web_dashboard" 2>/dev/null; sleep 1
cd /Users/jonaspenaso/Desktop/Phmex-S
nohup /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python web_dashboard.py >> logs/dashboard.log 2>&1 &
sleep 3; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8050/        # expect 200
curl -s http://127.0.0.1:8050/api/equity?era=all | head -c 200                  # expect JSON
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8050/static/uplot.iife.min.js  # 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8050/trades           # 301
```
Verify the bot is untouched: `ps -p $(cat .bot.pid) -o pid,etime` unchanged.
- [ ] **Step 4:** Screenshot-level check: confirm ticker values match `phmex_status`
ground truth (balance, cycle, watcher ON) — numbers must be real, never fabricated.
- [ ] **Step 5:** Commit anything outstanding; report done with the URL.
