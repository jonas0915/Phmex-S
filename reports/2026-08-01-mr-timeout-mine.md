# 5m_MR hard_time_exit entry-signature mine — 2026-08-01

**Question:** do the 5m_mean_revert timeout trades (hard_time_exit) share a predictable entry signature that separates them from trades that resolved at TP/SL?

**Answer: no separable signature at this n.** 0 of 36 tests reached even nominal p<0.05 (Bonferroni bar was 0.0014). Timeouts also aren't a loss problem — live-era timeouts sum to **+$0.20 net** — they're a capacity drag: 39% of the slot's in-position hours for ~1% of its net PnL.

Artifacts: `scripts/research/mr-timeout-mine-2026-08-01/` (extract_features.py, stats.py, trades_features.json, stats_output.txt). Read-only analysis; no bot files touched.

## Data and eras (never merged silently)

`trading_state_5m_mean_revert.json`, 39 closed trades. Two eras, split verified against `trading_state_5m_mean_revert_mode.json` `promoted_at` = June 12, 2026:

- **Paper era** (mode absent, idx 0–19, 3/28–6/11): 8 take_profit, 4 stop_loss, 4 adverse_exit, 4 hard_time_exit (idx 1, 7, 15, 16)
- **Live era** (mode="live", idx 20–38, 6/18–7/31): 13 exchange_close (TP/SL fire exchange-side), 5 hard_time_exit (idx 25, 27, 29, 31, 37), 1 min_margin_skip (idx 35, 0-second non-trade, excluded)

So the prompt's "9 of 39 live" is actually 4 paper + 5 live timeouts. The 4 paper adverse_exits are neither TP/SL nor timeout — excluded from both groups, reported separately. `_blocked.json` holds gate-shadow counters (requote/rsi-floor), not another trade era.

**Features recorded at entry** (entry_snapshot): OB imbalance/walls/spread, flow (buy_ratio, cvd_slope, large_trade_bias, trade_count, divergence), regime (label, ADX, ATR%, vol_ratio, EMA200/stack), htf_adx, plus side/symbol/hour-PT/margin. **Missing/degraded:** no snapshot at all on idx 0, 1, 2 (incl. 1 paper timeout); paper-era `ob` is null in every snapshot (OB features testable in live era only); `htf_adx` non-null on just 6 trades (skipped); `confidence` is 0 everywhere and `entry_strength` is 0.85 on all live trades but one (no variance — uninformative); F7 fields (rsi, rsi_fast, ema21/50_dist, vwap_dist) exist only on 7 trades from 7/19 on (2 timeout vs 5 priced — too few to test, listed for the record: the two timeout RSIs were 37.0 and 60.5, spanning the priced range).

## Tests

Two-sided permutation tests (20k shuffles, seeded) on means for 13 numeric features + Fisher exact on 6 binaries, run twice: **primary = live era only** (timeout n=5 vs priced n=13) and secondary = pooled eras. 36 tests total → Bonferroni α = 0.0014. Full table in `stats_output.txt`.

- **Nothing hit p<0.05, nominally or corrected.**
- Closest: `spread_pct` (live), timeout mean 0.0241 vs priced 0.0123, d≈+1.0, **p=0.083**. Distributions overlap (timeout idx 29 = 0.005, priced idx 28 = 0.036). With 36 tests, an 0.08 is noise-grade. Hypothesis only: timeouts may enter on wider spreads (less liquid moments).
- Directional curiosities that did NOT test out: side-aligned cvd_slope higher in timeouts (p=0.13), side/hour/regime/ADX/walls all flat (p≥0.34).

At n=5 vs 13 the minimum detectable effect is enormous; this whole exercise is hypothesis-generating, not confirmatory.

## Capacity cost (live era)

- Timeouts: idx 25 (XLM L, −$0.87), 27 (1000PEPE S, +$0.17), 29 (TAO S, +$0.38), 31 (SOL L, −$0.53), 37 (LTC S, +$1.06) → **24.8 hours held, net +$0.20** ($0.008/hr; 459 margin-hours).
- Priced trades: 38.8 hours, **net +$15.30** ($0.395/hr; 556 margin-hours). Timeouts consumed **39% of in-position time for 1.3% of the net**, though only 2.4% of the era's calendar span.
- **Blocked-signal check: structurally infeasible from bot.log.** The slot has `max_positions=1` (bot.py:552) and `can_enter` is checked *before* strategy evaluation (bot.py:2810) — while a timeout ride is on, signals for every symbol are skipped un-computed and un-logged. Ledger proxy instead: mean gap from a timeout close to the next entry was 27.9h (vs 68.0h after priced closes) — no sign of a signal queue waiting behind the timeouts; the sample of realized entries suggests the true blocked-opportunity count is low, but it is unobserved.

## Recommendation

**No separable signature at this n — do not build an entry filter.** No pre-registered forward test is warranted: nothing survives, and the trades a filter would remove are net-positive (+$0.20 live), so any filter with false positives on the priced group loses money. If the timeout count doubles (~10 live timeouts), re-run `stats.py` with spread_pct as the single pre-registered hypothesis (one test, no discount needed). The 4h hard limit (risk_manager.py:243, `hard_limit=240` cycles, 1.5× extension when ROI ≥5%) is doing its job as a cheap safety net.

Incidental find while grepping logs (not this task): `bot.log.1` 7/29 12:56 PM shows repeated `[PAPER] 5m_mean_revert ... bb_mean_reversion raised TypeError on strategy_fn(df, ob, htf_df=...) — falling back` warnings across many symbols — same wrapper-signature family as the SR_BOUNCE 7/29 bug. The fallback path works (trades kept flowing), but htf_df may be silently dropped for MR paper evals. Worth a look.
