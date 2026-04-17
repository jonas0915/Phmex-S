# htf_l2_anticipation — Design Spec
**Date:** 2026-04-17
**Status:** Approved
**Scope:** New parallel strategy that replaces closed-candle confirmation with L2/tape confirmation, enabling earlier entries on pullback setups

---

## Problem Statement

The existing `htf_confluence_pullback` strategy waits for a closed green candle (`bouncing = close > prev_close`) before entering a long. By the time this confirmation lands, the pullback has already reversed and the best part of the move is often over. Rich L2 and tape data (order book walls, bid/ask depth, CVD slope, buy_ratio, large_trade_bias) is fetched on every entry cycle but never read by the strategy itself — it's only used as veto gates in `bot.py`.

This spec introduces a parallel strategy that fires earlier using L2/tape signals as the confirmation layer, while keeping all other gates intact. It runs alongside the existing strategy (not replacing it), enabling A/B comparison on live trades with identical risk controls.

---

## Scope Decision: Parallel, Not Replacement

The existing `htf_confluence_pullback` has 132 trades of history (43.9% WR, -$10.63 net PnL). Modifying it directly would lose the baseline. The new strategy (`htf_l2_anticipation`) runs as a separate signal path. Both fire independently; whichever triggers first gets the entry. After 50 trades on the new strategy, compare side-by-side WR and PnL.

---

## Strategy Specification

### Pre-checks (identical to `htf_confluence_pullback`)

```
if htf_df is None or len(htf_df) < 30: HOLD
if len(df) < 50: HOLD
if htf_adx < 25: HOLD
if volume < vol_avg * 0.6: HOLD    # prev candle (iloc[-2])
if vwap <= 0 or isna(vwap): HOLD
if ema_21 == 0 or ema_50 == 0: HOLD
```

### Setup detection (identical to `htf_confluence_pullback`)

**LONG setup:**
```
htf_long        = htf_ema21 > htf_ema50 AND htf_close > htf_ema50 AND htf_adx >= 20
vwap_long       = close > vwap
pullback_to_ema = (abs(close - ema_21) / ema_21 < 0.005) OR (abs(close - ema_50) / ema_50 < 0.005)
rsi_long        = 35 <= rsi <= 60
```

**SHORT setup:** mirror of LONG.

### Entry trigger (REPLACES `bouncing` + momentum confirmation)

All three required L2/tape signals must pass for entry:

**For LONG entries:**
```python
req1 = flow.get("buy_ratio", 0.5) > 0.55
req2 = flow.get("cvd_slope", 0.0) > 0
req3 = ob["bid_depth_usdt"] > ob["ask_depth_usdt"]
```

**For SHORT entries:** flip all three (buy_ratio < 0.45, cvd_slope < 0, ask_depth > bid_depth).

If `flow` is None or `trade_count < 5`: HOLD (insufficient tape data to anticipate).

### Strength calculation

```
base = 0.82  # same as bouncing-confirmed baseline

# Booster 1: whale accumulation
if direction == "long" and flow.get("large_trade_bias", 0) > 0.2:
    base += 0.03
if direction == "short" and flow.get("large_trade_bias", 0) < -0.2:
    base += 0.03

# Booster 2: bid wall (long) / ask wall (short) within 1% of price — support forming
if direction == "long" and bid_walls:
    nearest_bid_wall_pct = min((price - w[0]) / price * 100 for w in bid_walls if w[0] < price)
    if 0 < nearest_bid_wall_pct < 1.0:
        base += 0.02
if direction == "short" and ask_walls:
    nearest_ask_wall_pct = min((w[0] - price) / price * 100 for w in ask_walls if w[0] > price)
    if 0 < nearest_ask_wall_pct < 1.0:
        base += 0.02

# Booster 3: no adverse wall within 0.5% — path clear
if direction == "long":
    has_near_ask = any(0 < (w[0] - price) / price * 100 < 0.5 for w in ask_walls)
    if not has_near_ask:
        base += 0.02
if direction == "short":
    has_near_bid = any(0 < (price - w[0]) / price * 100 < 0.5 for w in bid_walls)
    if not has_near_bid:
        base += 0.02

strength = min(base, 0.92)  # cap same as original
```

Max strength with all 3 boosters aligned: 0.89. Well above `SCALP_MIN_STRENGTH = 0.75`.

### OB imbalance gate (identical to original)

```
if illiquid: HOLD
if direction == "long" and imbalance < -0.3: HOLD
if direction == "short" and imbalance > 0.3: HOLD
if (long and imbalance > 0.15) or (short and imbalance < -0.15):
    strength += 0.02
```

---

## Integration

### Strategy registration

1. Add `htf_l2_anticipation_strategy` function to `strategies.py`
2. Register in the `STRATEGIES` dict
3. Add to the ensemble router / strategy iteration in `bot.py` so both strategies evaluate every symbol on each cycle

### Tracking

- `strategy_name` in `trading_state.json` trade records: `"htf_l2_anticipation"`
- Log prefix for debug output: `[STRAT L2]`
- Exit reason tagging unchanged (adverse_exit, early_exit, etc.)

### Gates that still apply (no changes)

All pre-entry gates in `bot.py` continue to fire on L2 strategy signals:
- Global cooldown (2 min)
- Per-pair cooldown (10 min after loss)
- Divergence cooldown (new, from Apr 16 session)
- Tape gate + soft tape gate
- Standalone divergence gate
- OB imbalance / walls / spread
- QUIET regime gate
- Time blocks (12-2 AM PT, 10 AM-1 PM PT, 5-7 PM PT)
- Kelly sizing
- HTF cluster throttle (1 htf entry / 30 min) — applies to both strategies combined

### Exits (unchanged)

All universal exits apply identically:
- `adverse_exit` at -3% ROI
- `early_exit` (4 signals: divergence, peak drawdown, RSI cross, CVD flip)
- Take profit at 1.6% price (16% ROI)
- Stop loss at 1.2% price (12% ROI)
- Trailing stop
- Hard time exit at 4 hours

### Margin sizing

Same as existing: $10 Kelly floor, `TRADE_AMOUNT_USDT` base, negative-edge warning but still enters.

---

## Reporting Changes

1. `notifier.py` — trade entry/exit Telegram messages tag strategy as `htf_l2_anticipation`
2. `scripts/daily_report.py` — adds `htf_l2_anticipation` to the "by Strategy" breakdown
3. `web_dashboard.py` — strategy filter dropdown includes new option

---

## Success Criteria (after 50 trades on new strategy)

| Metric | Target | Reason |
|---|---|---|
| Win rate | ≥ 43.9% | Match existing baseline |
| Net PnL per trade | > -$0.08 | Match existing baseline |
| Fire timing | Earlier than `htf_confluence_pullback` on same setups | Validate the "earlier entry" premise |
| Adverse exit rate | ≤ existing rate (5.5% of trades) | Verify we're not entering worse setups |

If all 4 met → evaluate promotion to primary strategy.
If WR below baseline but fire timing earlier → iterate in v2 (relax or tighten L2 requirements).
If adverse exit rate higher → entries are premature; retry with stricter signals.

---

## Out of Scope (for v1)

- Custom exits for L2 entries (e.g., tighter SL for earlier entries)
- Different position sizing for L2 strategy
- L2 signals for other strategies (bb_mean_reversion, momentum_continuation)
- Modifications to the existing `htf_confluence_pullback`
- Backtesting (paper slot) — going live to get realistic fills/slippage
- Adding `buy_ratio > 0.55` and `cvd_slope > 0` thresholds to config (use hardcoded for v1, promote to config after tuning)
