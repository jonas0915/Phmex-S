# Sentinel-Era Cumulative PnL Chart — Design

**Date:** 2026-04-27
**Status:** Spec — pending implementation plan
**Author:** Jonas + Claude
**Scope:** Dashboard-only. No bot logic, no Telegram, no schema changes.

## Goal

Add a single chart to the dashboard that visualizes net cumulative PnL across the Sentinel-era trade slice (deployed 2026-04-01 23:01 PT, trade #342+). Mirror the visual shape of the existing all-time `cumulative_pnl` chart so the eye reads them consistently. Overlay a vertical marker at the 2026-04-26 strategy cull commit so the cull's effect is visible at a glance.

The chart answers exactly one question: **does the post-Sentinel curve bend flat or upward to the right of the cull marker?**

## Why

- The Sentinel-era audit card currently shows a table only. The 146-trade slice has the answer to "is the bot actually profitable in its current configuration" but it's buried in row-by-row math.
- The verified per-trade net expectancy is -$0.10/trade with 95% CI entirely below zero (`memory/lessons.md` 2026-04-26 cull entry). The all-time chart hides this trend in older noise.
- The cull on 2026-04-26 (commit `479f879`, 19:22:55 PT) is the most recent intervention. A visible marker turns the chart into a controlled before/after view.
- Reuses the existing chart cache, route handler, and refresh thread — minimal incremental complexity.

## Out of scope

- Daily-bars chart (D from the brainstorm options) — explicitly deferred. Add later if cumulative-only proves insufficient.
- Per-strategy breakdown — duplicates info already in the audit table.
- Telegram propagation — this is a dashboard-only visualization, not a metric/gate/exit-reason change. Per `CLAUDE.md` propagation rule, only the chart cache + route + render path need updating; reports remain unchanged.

## Architecture

### New components

1. **Chart generator** — `_make_cumulative_pnl_sentinel(trades)` in `web_dashboard.py`. Mirrors `_make_cumulative_pnl` but:
   - Filters trades to those with `opened_at >= SENTINEL_DEPLOY_TS` (reuses the existing constant computation in `render` at line 1366).
   - Renumbers x-axis as 1..N within the Sentinel slice (NOT global trade index — keeps the chart self-contained and matches the audit card's "146 trades" framing).
   - Adds a vertical dashed line at the trade index of the first post-cull trade.
   - Title: `"Cumulative PnL — Sentinel Era"`.

2. **Cache key** — `cumulative_pnl_sentinel`. Added to `refresh_charts()` alongside the existing two. The `/chart/<name>` route at `web_dashboard.py:2219` is already generic; no route change needed.

3. **Render placement** — embedded inside the existing Sentinel audit card (`data-id="audit-sentinel"`), directly above the `perf-summary` stats div. Visually pairs the chart with its data slice. The all-time chart pair stays in the existing `charts-grid` at top of center column.

### Data flow

```
trading_state.json
  └─ closed_trades[]
       │
       ▼
  refresh_charts()        ← runs every 30s in chart_thread_loop
       │
       ├── _make_cumulative_pnl()                    (existing, all-time)
       ├── _make_pnl_by_reason()                     (existing, all-time)
       └── _make_cumulative_pnl_sentinel()           (NEW, trade #342+ only)
       │
       ▼
  _chart_cache["cumulative_pnl_sentinel"] = PNG bytes
       │
       ▼
  GET /chart/cumulative_pnl_sentinel?v=<chart_version>
       │
       ▼
  <img> inside Sentinel audit card
```

## Cull marker — exact placement

- Cull commit `479f879` landed at **2026-04-26 19:22:55 PT** = **2026-04-27 02:22:55 UTC**.
- Constant: `SENTINEL_CULL_TS = datetime(2026, 4, 27, 2, 22, 55, tzinfo=timezone.utc).timestamp()`.
- Marker x-position: index of the first Sentinel-era trade where `opened_at >= SENTINEL_CULL_TS`. If no such trade exists yet (none entered post-cull), skip the marker — chart still renders.
- Visual: vertical dashed line, color `#f9e2af` (Catppuccin yellow — distinct from the green/red fill bands), `linewidth=1`, `alpha=0.6`. Small label `"cull"` near the top of the line, `fontsize=8`, `color=#a6adc8`.

## Visual style

Match `_make_cumulative_pnl()` exactly:
- Figure size `(9, 4)`, facecolor `#1e1e2e`.
- Line `#89b4fa`, linewidth 2, marker `o` size 3.
- Green fill above zero `#a6e3a1` alpha 0.15, red fill below `#f38ba8` alpha 0.15.
- Zero line: `#585b70` dashed alpha 0.5.
- Tick / spine / grid colors as existing.

The only style additions are the cull marker line and label.

## Edge cases

- **Empty Sentinel slice:** If `sentinel_trades` is empty (shouldn't happen — there are 146 by spec), `_make_cumulative_pnl_sentinel` returns `b""` and the cache key is omitted. Render path checks for the cache key the same way it already checks `has_charts`.
- **No post-cull trades:** Skip the marker entirely. Chart still renders the pre-cull curve.
- **Single trade post-cull:** Marker renders; line continues for one point. Acceptable; user understands the cull is recent.
- **Trade timestamp missing/zero:** Already handled by the existing filter at `web_dashboard.py:1369` (`t.get("opened_at") or t.get("closed_at") or 0`). New chart uses identical filter logic.

## Testing

Manual verification only — consistent with existing chart code (no chart unit tests in `tests/`). Steps:

1. Start dashboard, open `localhost:8050`.
2. Verify chart appears inside the Sentinel audit card, above the perf-summary.
3. Verify trade count on x-axis matches the audit card subtitle (`146 trades` as of 2026-04-26).
4. Verify cull marker position aligns with the first post-2026-04-27 02:22 UTC trade.
5. Refresh — chart version bumps, browser cache busts, no flicker (existing immutable cache headers handle this).
6. Confirm no regression in the existing two charts.

## Reversibility

Single-file, additive change. Revert is a clean delete of:
- The new `_make_cumulative_pnl_sentinel` function.
- The new `SENTINEL_CULL_TS` constant.
- The new entry in `refresh_charts()`.
- The new `<img>` tag inside the Sentinel audit card.

No state migration, no schema change, no log format change.

## Risk

Low. Read-only on `trading_state.json`. Uses the same lock and cache mechanism as existing charts. Worst case: matplotlib raises on bad data → `chart_thread_loop` logs `[CHART] Error refreshing charts` and continues; existing charts unaffected.

## Open questions

None.

## Build sequence

1. Add `SENTINEL_DEPLOY_TS` and `SENTINEL_CULL_TS` as module-level constants near the top of `web_dashboard.py` (currently `SENTINEL_DEPLOY_TS` is computed inside `render` — promoting it makes it reusable from `refresh_charts`).
2. Implement `_make_cumulative_pnl_sentinel(trades)`.
3. Wire it into `refresh_charts()`.
4. Insert `<img src="/chart/cumulative_pnl_sentinel?v={_v}">` inside the Sentinel audit card, above the perf-summary div.
5. Manual verification per above.
