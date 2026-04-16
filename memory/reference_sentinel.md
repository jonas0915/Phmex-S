---
name: Sentinel Deployment
description: v11 (Sentinel) deployed 2026-04-01 23:01 PT — 3-layer entry gates, evaluate after 5 days against Pipeline baseline
type: project
---

## Deployed
2026-04-01 23:01 PT | PID 31456 | Trade #342+

## What Changed (from Pipeline)
- **Layer 1 (Rate):** cooldown 2→10 min, blacklist 2→4 hr, global cooldown 30s→2 min, regime 4/6→3/5 + 15→30 min, daily cap 3/symbol
- **Layer 2 (OB):** imbalance ±0.3→±0.25, wall veto, spread >0.15% veto
- **Layer 3 (Tape):** buy_ratio 0.30→0.45, CVD slope <-0.3, bearish divergence, large trade bias <-0.3
- **Slots:** removed ATR Gate, V10 Control, SMA+VWAP, 8H Funding. Added legacy_control (ungated Pipeline replica)
- **Dashboard:** Sentinel label in teal (#00d4aa)

## First Night Results (2026-04-02)
- 626 gate blocks overnight (gates firing correctly)
- Daily cap working: ETH, SOL, SUI hitting 3-trade limit by 07:35 UTC
- Legacy_control trading ungated as expected
- Trade size updated $5→$10
- Balance at restart: $82.71

## Evaluation Plan
- Run 5 days (through 2026-04-06)
- Compare live vs legacy_control: trade count, WR, AE rate, PnL
- Compare against Pipeline baseline week (memory/reference_performance_baseline.md)
- Target: AE rate <30% (was ~50%), WR ~45-55% (was ~35%)
- If legacy_control outperforms → gates too tight, loosen

## April 7 Parameter Changes (2026-04-07)
Applied after 5-day Sentinel eval (Apr 2–6). 3 changes, all from april-7-review.md:

1. **SOL blacklisted** — Added SOL/USDT:USDT to SCANNER_BLACKLIST in .env. Reason: 0W/6L over 2 days, removing it eliminates 3 of 7 AEs from Apr 6.
2. **CONFIDENCE_THRESHOLDS raised 3→4** — All strategies now require 4/7 ensemble signals (was 3). liq_cascade added explicitly. Location: bot.py:803-812. Eliminates 2 of remaining 4 AEs.
3. **_PROFITABLE_HOURS_UTC trimmed** — From {6,7,8,9,10,13,16} to {10,16,21,3} (PT 3,9,14,20 only). Location: bot.py:881. Cuts off consistently losing morning hours.

Post-change: 5 of 7 Apr 6 AEs are eliminated by these fixes. 2 remaining are high-confidence legitimate losses — AE threshold unchanged (correct call).

## April 7 Post-Mortem (2026-04-07 session 2) — ORIGINAL APR 2 EVAL WAS CORRUPTED
The Apr 2 "Sentinel is winning / 0% AE rate" narrative was built on corrupted data. Forensics found:

1. **AE rate was NOT 0%** — it was **50.8%** (worse than the ~41% pre-Sentinel baseline). Root cause: risk_manager writes `reason` field but analytics read `exit_reason` — silent tagging bug.
2. **Reports under-reported losses by $6.30 (58%)** — `pnl_usdt` is gross, fees were never subtracted for live trades, and dashboards labeled gross as "PnL".
3. **"+$8.27 Sentinel outperformance" was apples-to-oranges** — Sentinel gross vs V10 Control net. Invalid comparison.
4. **Three of four flagship Sentinel tape gates were broken since deploy:**
   - `cvd_slope`: spec ±0.3 vs raw ±100..±3,000,000 — 9 orders of magnitude off, fired randomly
   - `large_trade_bias`: hardcoded to 0.5 forever, never updated
   - Tape gates silently bypass when `trade_count <= 20` with no log
   - Entry snapshot dict literal existed but was never attached to Position (dead code)

### Phemex ground truth (FIFO-reconciled from CSV, 8 days Mar 31 -> Apr 7 UTC)
- 69 trades, **-$10.84 net**
- Gross closed PnL: -$3.95
- Fees: -$6.86 (**63% of total loss — fees are the dominant bleed**)
- Sentinel per-trade economics are **WORSE** than the pre-Sentinel baseline
- AE trades = 51% of all Sentinel trades and concentrate 100% of the bleed
- Killing AE = +$12.57 gross (non-AE buckets all profitable)

### Fixes deployed 2026-04-07 session 2
- cvd_slope normalized to -1..+1 ratio; large_trade_bias actually computed (>=5x median, requires >=8 large trades)
- Entry snapshots wired to Position -> closed_trades
- Real fee capture via `exchange.extract_order_fee()`; fees_usdt / funding_usdt / net_pnl on every trade
- 69 historical trades FIFO-backfilled from Phemex CSV ($0.00 diff)
- Reports + dashboard switched to net_pnl with safe fallback
- Dashboard: ~370 lines dead code removed, reconciliation panel added
- launchd `com.phmex.reconcile` every 4h with Telegram alerts
- Race condition closed (large-trade tracking inside self._lock)
- spread_pct midpoint formula fix, tape gate skip logging
- Option 1: cvd_slope carve-out for pullback strategies (but see C1/C2 in lessons.md — carve-out broken for bb_reversion and paper slot)

### Known issues logged but NOT fixed this session
See lessons.md ("Known issues logged but NOT fixed 2026-04-07 session 2"). User restricted bot code edits.

See also: `reference_sentinel_gate_forensics.md` for the detailed breakdown of the three broken gates.

## Spec
docs/superpowers/specs/2026-04-01-entry-quality-gates-design.md
