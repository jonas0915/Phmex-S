---
name: SESSION_HANDOFF — last touched 2026-05-01
description: Read this FIRST in next session. Cull failed at day 5 of 14, bot stopped, research path opened.
type: project
---

# Session Handoff — 2026-05-01

## Bot state right now
- **NOT RUNNING.** Bot stopped sometime after 8:41 PM PT 2026-04-30 (last log line is a routine WS seeding, no error). PID 41730 gone. `.bot.pid` stale at 1648 (also gone). No restart attempted.
- **Balance: $68.51** USDT. Down from ~$74.45 at session start, ~$74.78 at peak.
- **Open positions: 0.**
- 2 live strategies remained from the 2026-04-26 cull (`htf_confluence_pullback` + `htf_l2_anticipation`).

## Headline finding: cull observation FAILED

5 days into the 14-day post-cull observation window (n=26 trades since 2026-04-27 02:22 UTC):

| Metric | Pre-cull (30d) | Post-cull (5d, n=26) | Direction |
|---|---|---|---|
| Win rate | 39.7% | **23.1%** | ▼ |
| Per-trade net | -$0.10 | **-$0.24** | ▼ |
| AE rate | 29.3% | **50%** | ▼ |
| `htf_confluence_pullback` per-trade | -$0.13 | **-$0.24** | ▼ |
| `htf_l2_anticipation` per-trade | +$0.20 (n=13) | **-$0.25** (n=10 post) | ▼ flipped negative |

Both strategies are now negative-edge over their cumulative samples. The +$0.20/trade reading on `htf_l2_anticipation` that justified keeping it was statistical noise; at n=23 cumulative it's now negative.

**Decision (2026-05-01):** no more parameter sweeps. The bot has not produced verified positive edge across 5 rounds of changes (Sentinel deploy, conf 3→4, hours trim, TP/AE tighten, cull). Research path opened.

## What was shipped this session arc (2026-04-27 → 05-01)

**Sentinel-era cumulative PnL chart on dashboard** — 4 commits, full subagent-driven workflow:
1. `78310be` — module constants + `_cull_marker_index` helper + 6 unit tests in `tests/test_sentinel_chart.py`
2. `ce11306` — `_make_cumulative_pnl_sentinel(trades) -> bytes` chart generator (mirrors `_make_cumulative_pnl` style + yellow cull marker)
3. `278648c` — wire into `refresh_charts()` + embed `<img>` inside Sentinel audit card
4. `0846ce8` — cache-eviction fix from code review (handles `*.bak` rollback edge case)

Live verified: chart serves at `localhost:8050/chart/cumulative_pnl_sentinel`, embeds correctly inside the audit card.

Spec: `docs/superpowers/specs/2026-04-27-sentinel-pnl-chart-design.md`
Plan: `docs/superpowers/plans/2026-04-27-sentinel-pnl-chart.md`

## Forensics performed (clean, no bugs)

**AVAX/ARB shorts (2026-04-27 losses):**
- AVAX: real 1h downtrend (ADX 29.2, EMAs aligned), pullback gate fired exactly at the EMA pivot, 5m EMAs crossed back to bullish at +22 min → AE fired correctly. Not a gate failure, market refused the bet.
- ARB: bot saw RSI **63** at entry (verified from bot.log), inside the 40-65 short band. My earlier "RSI=71" claim was a **partial-bar timing artifact** — same bar, measured 3.5 min later after it finalized at a higher close.
- Entry snapshot persistence verified working. Schema is nested (`entry_snapshot.flow.buy_ratio`, `entry_snapshot.ob.imbalance`, `entry_snapshot.regime.adx`), not the flat top-level fields I had been grepping for. 83% population rate across recent trades.

## Open: brainstorming the backtest harness

Jonas's stated R&D plan:
1. Build a backtest harness that produces results matching live trading within ±15%
2. Test new strategy ideas against 90 days OHLCV with realistic fees + slippage
3. Only deploy what shows positive simulated edge

**Existing infra surveyed:**
- `backtester.py` (478L) — CSV-based, no live gates → 2.7x overtrade calibration gap
- `backtest.py` (1143L) — production, has cooldowns + regime + DD halt + strength gate, missing OB/tape
- 90-day OHLCV in `backtest_data/`: 5 pairs (BTC, ETH, SOL, BNB, XRP) × 5m+1h, Jan 10 → Apr 10 2026
- Both backtesters import `confluence_strategy()` directly from live `strategies.py` — no copy
- AE rule lives in `backtester.py` only (`--ae-rule {roi,trend_flip}` flag)

**Decomposed into 3 sub-projects:**
1. **Backtest calibration** — pick one backtester, get it within ±15% of live on PnL+WR
2. **Strategy testing harness** — CLI / workflow for proposing+testing new ideas
3. **Deployment gate** — process policy, "no live deploy without simulated +ve edge"

**Open question** (where brainstorming was paused): how to handle OB/tape gates that aren't in OHLCV?
- **A.** Skip them in backtester, accept ~20-30% trade-count gap, calibrate other gates carefully. Available now, ~3-5 days.
- **B.** Proxy from OHLCV structure (buy_ratio ~ candle close-vs-mid, imbalance ~ wick asymmetry). Lossy. ~1-2 weeks.
- **C.** Capture L2/tape live going forward, build replay corpus. Highest fidelity. 30-60 days lag.

## Next session — pick up at the brainstorm

1. Resume the A/B/C decision on OB/tape simulation
2. Then continue brainstorming sub-project 1 (calibration target — PnL? WR? trade count? all three?)
3. Then writing-plans → implementation
4. Bot stays OFF until simulation says yes (or Jonas overrides for a deliberate paper-only restart)

## Lower-priority pending items

- **Backup folder cleanup**: `~/Desktop/Phmex-S.backup-2026-04-26` is past the 2026-05-03 deadline. Safe to delete (no rollback needed).
- **`bb_mean_reversion` shorts-only spec** — deferred from the 2026-04-26 handoff. Likely irrelevant now if we go research-first.
- **Paper slot decisions** (`5m_liq_cascade`, `5m_mean_revert`) — also deferred. Same reasoning.
- **Order-path timeout wrap** (`docs/superpowers/specs/2026-04-24-order-path-timeout-wrap.md`) — needs no-position window for restart. We have one now if/when we redeploy.

## META-RULE corrections caught this session

1. **ADX threshold** — quoted 20 from memory; actual code is 25 (strategies.py:291,527). See lessons.md "Verify thresholds against strategies.py source."
2. **Partial-bar RSI** — computed RSI on finalized bar instead of partial bar bot evaluated. See lessons.md "Partial-bar RSI replication."
3. **Snapshot schema** — claimed flat fields when schema is nested. See lessons.md "entry_snapshot schema is nested."

Pattern: under time pressure I trust memory + quick pandas-recompute over reading current source. Each time, parallel verification (or Jonas) caught it. Rule now formalized in lessons.md.
