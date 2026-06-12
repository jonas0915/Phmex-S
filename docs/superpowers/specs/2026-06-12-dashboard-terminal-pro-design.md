# Dashboard v2 — "Terminal Pro" Redesign (web_dashboard.py)

**Date:** 2026-06-12
**Status:** Approved by Jonas via visual companion ("this is approved", ~10 AM PT).
Design chosen through 3 mockup rounds: skin **B (Terminal Pro, amber-on-black dense)**,
layout **B (command grid)**, all 4 capability options selected.
**Scope:** web_dashboard.py ONLY. trading_desk.py is phase 2 (separate spec).

## Hard constraints (project rules — non-negotiable)
- Dashboard is read-only and bot-independent: reads ONLY trading_state*.json,
  logs/bot.log, logs/*.jsonl. ZERO exchange/API calls. Localhost bind (127.0.0.1)
  stays. Restarting the dashboard never touches the bot (no pre-restart-audit needed).
- All times 12-hour PT.
- No-cache headers stay (lessons.md: browser cache bites).
- Net-vs-gross honesty: every PnL number labels its basis; defaults to NET.

## Visual system
- Palette: bg `#000204`, panel bg `#0a0e08`, borders `#2d3a1e`, primary text `#9eb89e`,
  accent/headers `#f0a500` (amber), positive `#4af626`, negative `#ff5555`,
  muted `#5a6b5a`.
- Single monospace stack: `'SF Mono', Menlo, 'JetBrains Mono', monospace` (drop the
  Google Fonts Inter import — terminal aesthetic + no external font dependency).
- Density: minimal padding, uppercase letter-spaced panel titles, table rows ~16px.

## Layout (command grid)
Top ticker strip (sticky): `PHMEX-S ▮ BAL $X ▲/▼today ▮ MR-LIVE HDRM $X ▮ DD X% ▮
POS n ▮ WATCHER ON/OFF ▮ CYC n ▮ h:mm:ss AM/PM PT`. Watcher state = whether the
[LIVE EXIT] watcher-enabled line appears after the latest startup marker in bot.log.

3×2 grid + full-width feed:
1. **POSITIONS** — main + live-slot positions merged with owner tag; sym, side,
   entry, SL/TP, age, strategy. uPnL shown ONLY when a current price is already
   available from existing dashboard data sources (no new API calls); otherwise
   omit the column value ("—"). Flat state shows last close.
2. **SLOTS + GUARDRAILS** — per slot: status dot (LIVE green / paper amber /
   killed ✝ grey), trades, WR, net PnL. For LIVE slots: demote-headroom depletion
   bar ($5 + live_net_pnl, gradient green→amber), negative-Kelly arm state
   ("@10 live trades — n so far"). Data from mode sidecars + slot state files.
3. **EQUITY (interactive)** — uPlot (vendored local copy under a new `static/`
   route, NOT a CDN link, so the dashboard works offline; ~40KB). New
   `/api/equity?era=sentinel|all` endpoint returns JSON series of cumulative NET
   PnL by close time + per-point trade metadata. Win/loss colored markers; hover
   tooltip = time, sym, strat, net PnL, reason; drag-zoom. Era toggle buttons.
   Matplotlib, the 30s chart thread, `_chart_cache`, and `/chart/<name>` are REMOVED.
4. **BLOTTER** — all trades newest-first, main + slots merged, columns: time (PT),
   sym, side, strat, net PnL, reason, mode/owner badge. Click row → expands inline
   drill-down: confidence + layers, entry snapshot fields (buy_ratio, cvd_slope,
   lt_bias, ob imbalance), shadow/gate tags, fees + basis, entry/exit prices.
   Snapshot data from the trade record's stored entry_snapshot/gate_tags fields;
   graceful "no snapshot recorded" for old trades. Served via `/api/trade?id=...`
   (lazy-load on expand). Absorbs and replaces the separate `/trades` page (route
   301s to `/`).
5. **WHY NO TRADES?** — per scanned pair: latest 1h ADX parsed from the newest
   `[HOLD] <sym> — No confluence signal (1h ADX=X)` / `[STRAT]` lines per symbol in
   the log tail, rendered as bar-vs-threshold (25); time since last non-HOLD signal;
   top gate rejecters 24h (existing observability data); mean_revert band-touch
   note when parseable. If a pair has no recent HOLD line, show "—" (never guess).
6. **GATES + WATCHLIST** — 24h gate rejection counts (existing `_build_observability_panel`
   data) + compact watchlist: sym, 24h vol, spread, readiness dot (existing logic).

Full-width **FEED** — last ~20 log events, color-coded, 12-hr PT timestamps.

Panels removed/merged from v1: Sessions card DROPPED (session-of-day adds no
decision value at this density), L2 monitor panel and
reconcile card become compact rows inside GATES+WATCHLIST and POSITIONS respectively
(reconcile mismatch shows as a red ticker chip when non-OK — surfacing only on
problem, per density principle). Live-vs-cascade comparison and NARROW panels drop
(both slots killed; data still in /api if needed later).

## Mobile
CSS media query (≤700px): single column, order = ticker (wrapped), SLOTS+GUARDRAILS,
POSITIONS, EQUITY, BLOTTER (top 10 + "more"), others collapsed behind <details>.
Same URL, no separate page.

## Architecture (unchanged on purpose)
stdlib ThreadingHTTPServer + DashboardHandler; `build_content()` f-strings;
3s `/api/content` innerHTML polling. New endpoints: `/api/equity`, `/api/trade`,
`/static/uplot.*`. uPlot re-renders client-side on its own fetch cycle (30s or on
era toggle) — the innerHTML swap must NOT destroy the chart: chart lives in a
dedicated DOM node OUTSIDE the swapped `#content` container (restructure index shell
accordingly).

## Error handling
Every file read in new code paths wrapped (JSONDecodeError/IOError → empty default).
Malformed snapshot → "snapshot unavailable". Missing uPlot files → panel shows
"chart assets missing" instead of JS error.

## Testing / verification
- `tests/test_dashboard_v2.py`: equity endpoint JSON shape, trade drill-down endpoint
  (snapshot present + absent), why-no-trades log parser (sample HOLD lines incl.
  missing-pair case), live-slot guardrail math surfaced in content.
- py_compile; full suite green; manual browser check at :8050 desktop + narrow
  window; verify ticker watcher state correct against live log.
- Dashboard process restart only (`pkill -f web_dashboard` + relaunch) — bot untouched.

## Rollback
Single file + new static assets; `git revert` restores v1 (matplotlib path returns
with it). No bot interaction either way.
