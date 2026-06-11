# Calibrated Backtester — Research Path Sub-Project 1

**Date:** 2026-05-07 (spec) → 2026-05-08 (Steps 1+2 implemented)
**Status:** Steps 1+2 IMPLEMENTED + smoke-tested. Steps 3-5 pending.
**Owner:** Jonas + Claude
**Context:** Session 2026-05-02 paused live trading and queued a 3-sub-project research path. This spec covers sub-project 1 only.

## Implementation log

- **2026-05-08 06:02 UTC**: Steps 1+2 landed (bundled because Step 1 alone produces no signals — l2_anticipation requires flow that cannot be replayed). Smoke test on ETH/USDT 14 days `--calibration`: 195 trades, 14.4% WR, -$43.13 PnL, 89.2% time_exit. Engine produces signals; calibration comparison vs live PnL still needed (Step 4).
- Audit findings during implementation:
  - **Minimum window = 14 days for HTF runs** (not 7 as originally written). 1h `add_all_indicators` requires ≥200 candles for EMA-200 warmup; 7 days = ~168 candles, gets emptied.
  - **Strategy name shows "unknown" in per-strategy breakdown**. Trade record's strategy field isn't populated by the backtester. Cosmetic now, blocks Step 4 (calibration compare) until fixed.
  - Lookahead semantics for 1h slice match live bot exactly (`searchsorted side="right" - 1` reads current forming 1h candle, same as live). Not a bug.
  - `--calibration false` (default): now passes `htf_window` to `confluence_strategy` instead of `None`. Behavior unchanged in practice (l2_anticipation still HOLDs without flow), just structurally cleaner.

- **2026-05-11 (Steps 3-5 wrap)**:
  - **Step 3 (AE in `check_exits`)** — already implemented at `backtest.py:382-389` during the 05-08 work. No additional code; matches live `risk_manager.py:200-209` order-of-checks. ✅
  - **Strategy field already populated** at `backtest.py:643,852` via `_extract_strategy_name(signal.reason)` → `pos.strategy`. The 05-08 "unknown" was a smoke-test display artifact, not missing data. ✅
  - **`backtest.py` extensions:** added `--starting-balance` flag and `--output-json PATH` flag + `_dump_summary_json` helper. Additive, reversible.
  - **`scripts/calibrate_compare.py`** was already present; verified correct (imports `run_backtest` directly, filters live by symbol+strategy+date, prints PASS/FAIL against ±15% PnL / ±30% count tolerances).
  - **Calibration run executed:** ETH/USDT:USDT × `htf_confluence_pullback` × 2026-03-18 → 2026-05-02 (45d, n=34 live).
    | | Live | Sim | Delta |
    |---|---|---|---|
    | Trades | 34 | 342 | **+906%** |
    | Net PnL | -$0.99 | -$63.84 | **-6364%** |
    | Win rate | 47.1% | 23.4% | -23.7pp |
  - **Verdict: FAIL** — far outside ±15% PnL and ±30% count bands. The spec predicted 20-40% overfire from missing tape/ensemble gates; actual is ~10x. Additional gates absent in backtester beyond tape/ensemble: **daily-symbol-cap, per-pair-loss-cooldown, profitable-hours filter**. WR drop from 47% → 23% indicates the missing gates aren't random — they reject directionally-bad signals.
  - **Correction factor logged in `backtest.py` LIMITATIONS banner**: divide sim trade count by ~10 to approximate live rate. Not a true calibration — the engine is structurally correct but cannot be used for strategy validation until missing gates are simulated.
  - **Next move:** the validated path is **build the missing gates in `backtest.py`**, not the random-rejection shortcut. WR collapse confirms the gates carry directional information. Separate spec needed; this one is **closed with caveat**.

## Goal

Build a backtester whose output PnL on a held-out window of historical data is within **±15%** of the live bot's actual PnL on that same window for at least one strategy × symbol × 30-day slice. Without that calibration, no strategy candidate can be validated before live deployment.

## Why this matters

- Both live strategies (`htf_l2_anticipation`, `htf_confluence_pullback`) have CI brackets bracketing zero — no statistical evidence of edge.
- Account is bleeding live (~$1–2/active day at current $5/trade size).
- Without a validated backtester, every new idea has to be tested with real money. That's the bug, not any specific strategy choice.
- Once calibrated, the backtester becomes the gate for sub-project 3 (deployment policy: no strategy goes live without positive simulated edge after fees+slippage).

## Current state (verified 2026-05-07)

Two backtester files exist:

**`backtest.py`** (1145 lines) — production target:
- Live OHLCV fetch via ccxt (1m + needs 1h)
- Regime-adaptive ATR SL/TP, floor 1.2%, cap 1.6%
- Fees: 0.06% taker × 2 + 0.05% slippage × 2
- Gates: cooldowns + regime pause + DD halt + max open + half-size choppy
- **Blocker at line 682**: calls `confluence_strategy(df_window, None)` with no `htf_df` and no `flow` → strategy returns HOLD immediately → zero signals fire for current live strategy
- **Missing**: ensemble confidence gate (bot.py:1036-1061), tape veto gate (bot.py:1078-1125), divergence cooldown (bot.py:1063-1076), daily symbol cap, AE logic
- Hardcoded starting balance $74.38 (line 37), never read from `trading_state.json`

**`backtester.py`** (478 lines) — older research tool, CSV-based, no gates, fixed SL/TP. Not the calibration path; reference only.

## Calibration target

**Minimum viable calibration:** 1 strategy × 1 symbol × 30 days, output PnL within ±15% of live PnL on the same slice, AND trade count within ±30% (rules out coincidental PnL match from opposing errors).

**Strategy choice:** `htf_confluence_pullback` (revived only inside backtester, not live). Rationale: it's the only OHLCV-only strategy in the codebase. `htf_l2_anticipation` requires live L2/tape signals that can't be replayed from OHLCV (no historical snapshots stored).

**Symbol choice:** ETH/USDT:USDT — deepest liquidity, most stable spread, minimizes slippage model error.

**Window choice:** 30-day window from `trading_state.json` covering pre-cull (5/2 backwards). Actual ETH pullback trade count in that window is the live ground truth.

**Sample size note:** 30 days at current frequency yields roughly 20-40 backtest trades on ETH alone. Below the 50-trade threshold for tight CI, but enough to confirm the backtester isn't off by 2-5x. Extend to 2 symbols or 45 days if count too low.

## Implementation sequence (5 steps, each independently testable + reversible)

### Step 1 — Fix HTF data missing (blocker)

In `backtest.py`, fetch a 1h OHLCV dataframe per pair alongside the 1m data. Pass it as `htf_df` to `confluence_strategy` at line 682. Change `confluence_strategy(df_window, None)` to `confluence_strategy(df_window, None, htf_df=htf_window)` where `htf_window` is the 1h slice up to current sim time.

- **Files:** `backtest.py` lines 477-500 (data-fetch loop) and line 682 (strategy call)
- **Reversible:** yes, additive
- **Test:** `python backtest.py --pairs ETH/USDT:USDT --days 7` should produce non-zero trade count

### Step 2 — Re-enable `htf_confluence_pullback` for calibration only

`htf_l2_anticipation` cannot fire without live flow. Add a `--calibration` flag that calls `htf_confluence_pullback` directly instead of routing through `confluence_strategy` (which is currently culled at strategies.py:670-675). Live strategy routing untouched.

- **Files:** `backtest.py` entry loop near line 682, argparse near line 1049
- **Reversible:** flag is additive
- **Test:** confirm trade reasons in output show `htf_confluence_pullback`

### Step 3 — Add adverse exit to `check_exits()`

Match live config exactly: roi <= -3% AND cycles_held >= 10. Insert before time-exit block.

- **Files:** `backtest.py` `check_exits()` near line 392
- **Reversible:** can be flag-gated
- **Test:** run with and without AE; AE should reduce avg holding time on losers

(Note: even with AE disabled live as of this session, calibration target compares against historical period when AE was active. The backtester needs AE for that historical comparison.)

### Step 4 — Calibration comparison script

New standalone script `scripts/calibrate_compare.py`. Reads `trading_state.json`, filters `closed_trades` by date range and symbol, sums `net_pnl`. Prints live baseline alongside backtest total + delta percentage.

- **Files:** new script, read-only on `trading_state.json`
- **Reversible:** read-only
- **Test:** output shows both numbers and delta in one run

### Step 5 — Reconcile and document residual gap

After steps 1-4, run comparison. Document gap (expected: 20-40% overfiring from missing tape/ensemble gates). If within ±15%, calibration achieved. If not, measure fire-rate ratio and apply rejection-rate correction factor as a documented constant.

- **Files:** update `backtest.py` LIMITATIONS banner near line 1025
- **Test:** documented correction factor; replicable on second run

## Out of scope (deferred to later sub-projects)

- L2/tape simulation. `htf_l2_anticipation` cannot be backtested without historical L2 snapshots. Either build a snapshot recorder now and wait 30+ days, or proxy with volume-derived signals (separate spec).
- Multi-strategy testing CLI (sub-project 2 of research path).
- Deployment gate policy (sub-project 3).
- Walk-forward optimization. The current target is calibration accuracy, not strategy optimization.

## Acceptance criteria

- [x] Step 1+2 land: backtester produces non-zero trade count with `--calibration` (195 ETH trades on 14-day run, 2026-05-08)
- [x] Strategy name populated in trade record (was always populated; "unknown" was a smoke-test display artifact)
- [x] Step 3 lands: AE check fires correctly in backtest (already at `backtest.py:382-389` from 05-08)
- [x] Step 4 lands: calibration comparison script outputs delta in one command (`scripts/calibrate_compare.py`)
- [ ] Step 5 lands: backtest PnL on 30-day ETH pullback window within ±15% of live PnL on same window AND trade count within ±30% — **FAILED 2026-05-11 by 10x margin; engine works but missing live gates. Spec closed with caveat.**
- [x] LIMITATIONS banner updated with measured correction factor (2026-05-11)

## Risks

1. **30 days × 1 symbol may not yield enough trades** for meaningful CI. Mitigation: extend window or add a second symbol if count < 25.
2. **OHLCV fetch granularity at 1m vs 5m candle close** — backtester uses 1m for fill simulation, live runs on 5m. Differences in within-bar SL/TP fill order are real but small. Mitigation: document the convention; live-vs-backtest delta on this dimension is bounded.
3. **Live strategy uses culled `htf_l2_anticipation`, calibration uses revived `htf_confluence_pullback`** — calibrating one strategy doesn't prove the other works. This is acknowledged. Calibration validates the *engine*, not the live strategy. Once engine is calibrated, separate work is needed to backtest l2_anticipation (needs L2 snapshot infrastructure first).
4. **Hardcoded starting balance $74.38** at backtest.py:37 — does not match current $63 account. Update or override via flag in Step 4 to read from `trading_state.json`.

## Estimated effort

- Step 1: 1-2 hours (data-fetch loop + signature change)
- Step 2: 30 min (flag + routing)
- Step 3: 30 min (AE check insertion)
- Step 4: 1 hour (comparison script)
- Step 5: 1-2 hours (run, measure, document)

**Total: 4-6 hours of focused work, spread across one or two sessions.**

## Workflow rules for implementation

- Pre-restart-audit not required — backtester is offline, doesn't touch live bot.
- Every code change reviewed by parallel verification agent before merge.
- Live bot remains in current state (PID 27948, $5/trade, AE disabled) throughout.
- Bot's `.pause_trading` may be re-enabled at any time if balance hits halt threshold.

## What this does NOT do

- Does not produce a live-deployable strategy.
- Does not validate `htf_l2_anticipation` (needs separate L2-snapshot work).
- Does not change live trading behavior.
- Does not stop the live bot from bleeding while calibration is being built.
