# Imbalance-Reversion Edge — Findings & Verdict (2026-06-01)

**TL;DR:** There IS a real directional signal in the order book — imbalance predicts
short-horizon mean-reversion — but its gross magnitude (~0.04%/trade) is about half the
0.12% taker round-trip fee. It only clears costs at maker fees (0.02%), and only in the
perfect-fill idealization. Realistic maker fills are **unverifiable** with current data
(75s capture cadence). **Verdict: real but uncapturable at $56 / current execution. Not
promotable. Edge hunt closed.**

This extends, not replaces, the documented open thread: maker-only execution was already
flagged as the sole edge lead on 2026-04-26 and 2026-05-07 (see lessons.md). This doc
quantifies it.

## What was tested
Three rigorous backtests (chronological train/test splits, params selected on train only,
reported on held-out test). Data: `logs/flow_capture.jsonl` (108,297 real L2 snapshots,
35 symbols, ~20-day span, May 10 → May 30 2026) + `backtest_data_may/` OHLCV.
Reproducible scripts: `scripts/research/imbalance-edge-2026-06-01/`.

## Finding 1 — The signal is real, and it's REVERSION (not momentum)
- `corr(ob.imbalance, forward_return)` is **negative at every horizon**, monotonic across
  quintiles, strongest at 60s (r = −0.0641, p ≈ 1e-94). Positive imbalance (book leans bid)
  → price reverts **down**.
- `depth_ratio` ≈ `imbalance` (same construct). These are the top features by a wide margin.
- Flow features (`cvd_slope`, `buy_ratio`, `large_trade_bias`) separate **nothing** (|r| < 0.022).
  Acts as a clean negative control — strengthens confidence the imbalance effect is real.
- Effect **decays with horizon** and is noisy per-symbol (sign consistent, magnitude swings).

## Finding 2 — The signal is ~half the taker fee
- Best gross expectancy anywhere ≈ **+0.04%/trade**. Breakeven round-trip fee = **0.040%**.
- Dislocation-reversion strategy (fade sharp moves + imbalance gate), 324-config grid:
  **0 of 324 configs net-positive on the train half** at taker fees. There was nothing to
  overfit to. Held-out test: n=1538, WR 39.9%, gross +0.0401%/trade, **net −0.0799%/trade**.
- The imbalance **gate adds no out-of-sample value** (slightly hurts, cuts ~65% of trades).
  Note: the live bot already gates imbalance at ±0.25 (`strategies.py:139`).

## Finding 3 — Maker fees rescue it, but only on paper
Same strategy, same split, maker fees:
| Execution | Round-trip cost | Held-out TEST result |
|---|---|---|
| Taker | 0.12% | −0.0799%/trade (dies — 3× the breakeven fee) |
| Maker, perfect fills (Scenario A) | 0.02% | **+0.0201%/trade, +30.84% total, WR 45.4%** |
| Maker, realistic fills (Scenario B, 30–60s passive wait) | — | **0% of orders fill — untestable** |

- Breakeven fee = 0.0401% → sits *just above* maker (0.02%), far below taker (0.12%).
  That ~2bp of headroom is razor-thin: one bp of slippage/adverse selection erases it.
- Scenario B returns nothing because `flow_capture.jsonl` samples each symbol only every
  **~75 seconds**. A passive limit at the trigger price gets 0% confirmed fills at 30/60s
  windows; fills only appear at 120s+ (~50%). You can't validate sub-second passive fill
  realism with 75s snapshots.

## The missing data (the only remaining unknown)
**Sub-second tick / L1 order-book data.** Everything else is answered. Without it, the
realistic maker-fill question (Scenario B) is unanswerable, and the signal belongs to the
market makers we'd be trying to passively fill against (adverse selection).

## Why we stopped here (the call)
A ~2bp edge needs scale and high-quality maker fills to matter. At $56 the dollar payoff is
pennies even in the dream case, and the realistic outcome — after building tick capture and
fixing the 0%-fill maker-exit bug (`exchange.py:553-616`) — is that adverse selection eats
the 2bp. This matches the external research conclusion: a $56 account cannot overcome
execution costs vs. market makers. The signal is real; it is structurally not ours to take
at this size.

## If ever revisited (preconditions, in order)
1. Collect sub-second tick/L1 data for the target symbols (weeks of it).
2. Fix maker-exit fills (the 4s-timeout 0%-fill bug).
3. Re-run Scenario B against tick data with a real fill+adverse-selection model.
4. Only consider deployment if it survives realistic maker fills with margin to spare —
   and at materially larger capital, where 2bp is worth the operational risk.
