# Trading Desk v2 — Truthful, Alive, Smooth (trading_desk.py)

**Date:** 2026-06-12 · **Status:** Approved by Jonas ("proceed", ~11:30 AM PT).
Scope chosen: all four areas; **smoothness wins** every fidelity conflict (hard
~30fps floor on M3 Air integrated GPU). Phase 2 of the "make it nicer" request
(phase 1 = dashboard v2, shipped).

## Hard constraints
- Read-only: trading_state*.json + logs/bot.log + l2 snapshot only. ZERO exchange
  calls. 127.0.0.1:8060. Restart-independent from the bot (no pre-restart-audit).
- Honesty rule: every rendered number is real or absent — no Math.random()
  cosmetics, no invented values. 12-hr PT for human-readable times; log clock is
  EASTERN (parse with ZoneInfo America/New_York like dashboard's fixed parsers).
- SSAO / color-grading stay removed (GPU). Single-file HTML_PAGE structure stays;
  new JS in clearly-marked sections.

## Workstream 1 — Truthful monitors (priority 1)
Python `_build_api_response` additions (all guarded reads):
- `slots`: per slot {id, live: bool, trades, wr, net_pnl, and for live slots
  live_net, headroom (5.0 + live_net), live_trades} from slot state + mode sidecars
  (net = net_pnl fallback pnl_usdt — same as dashboard).
- `watcher`: bool — "[LIVE EXIT] watcher enabled" after last startup marker
  (port the dashboard's _watcher_enabled incl. 30s cache + full-file fallback).
- `pair_adx`: {sym: adx} from [HOLD] lines (port dashboard parse_pair_adx).
- `top_gates`: top 4 of the 24h gate counts (port _gate_stats Eastern-aware,
  30s cache).
JS monitor changes:
- Scanner desk: real per-pair ADX bars vs the 25 threshold (replace Math.random
  vol bar). Pairs without data render dim dashes.
- Risk desk: drawdown + mean_revert headroom depletion bar (green→amber).
- Executor desk: watcher ON/OFF + last [LIVE EXIT] event line when present.
- Wallwatch: MR-LIVE row (status, live_net, headroom). Walldash: net-basis labels.
- Redraw discipline: each monitor canvas redraws ONLY when its slice of apiData
  changed (JSON-stringify hash or field compare), at most once per poll (3s).

## Workstream 2 — Event-driven life (priority 2)
Event→behavior map consuming the existing typed events in apiData.events +
new fields above. Reuse ONLY existing primitives (walkTo/speech bubbles/plumbob
colors/gather routines). Behaviors:
- `close` win → celebration at the owning strategy desk (green plumbob pulse,
  speech, brief gather of 2 nearest agents).
- `close` loss / stop-out → owning agent gloom (grey plumbob, slump speech,
  therapy-desk walk reuses existing therapy trigger).
- `[LIVE EXIT]` watcher fire → executor agent walks to ensemble (Claude) desk,
  speech "enforced <sym> exit".
- Slot PROMOTED → conference-room team gather + speech. Slot DEMOTED/auto-demote
  → walk of shame: owning agent walks to B1 rec area, 3 agents follow, gloom
  bubbles; comms panel narrates.
- Dedup: each log event keyed by timestamp+type fires its behavior once (Set of
  seen keys, capped 200).

## Workstream 3 — Performance floor (gates workstreams 2/4)
- Monitor texture redraws throttled per workstream 1 (biggest win — today every
  monitor canvas redraws every updateAllMonitors call).
- animate() audit: move per-frame work that doesn't need 30fps (bay fog opacity,
  water waves, label distance checks) to every 4th frame; verify CSS2D label
  count and culling.
- Instancing audit: any remaining per-mesh static city geometry → merged/instanced.
- Measurement: renderer.info.render.calls + a 5s FPS sampler logged to console
  before/after; acceptance = no regression below ~30fps at default camera, draw
  calls reduced or equal.

## Workstream 4 — Fidelity within remaining budget (last)
- Window glass: cheap pre-baked cubemap env reflection on the penthouse glass.
- Warmer sunset/night palettes in updateTimeOfDay (texture regen stays on its
  existing slow clock, NOT per frame).
- Lamp glow sprites (additive billboards, one shared texture).
- Each item individually droppable if the FPS floor breaks; NO SSAO/grading.

## Testing / verification
- Python additions: module-level pure functions with tests (tests/test_trading_desk_v2.py):
  api response shape with promoted + paper + killed slots, watcher/adx/gates
  parsers against sample log lines (reuse dashboard test patterns).
- JS: not unit-testable here — per-task code review + live browser verify in the
  final task (restart desk process only, check monitors show real values matching
  /api/data, trigger-able behaviors observed via comms panel narration).
- Rollback: git revert; desk restart is `pkill -f trading_desk` + relaunch.
