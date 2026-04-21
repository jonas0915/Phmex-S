# Entry Quality Gates — Design Spec
**Date:** 2026-04-01
**Status:** Proposed
**Goal:** Reduce adverse exit rate from ~50% to under 30% without killing profitable trading days

## Problem Statement

The bot overtraded on April 1 (17 trades, 9 adverse exits, -$2.20) due to:
1. Rapid re-entry after losses (2-min cooldown too short)
2. HTF trend lag (1H EMAs don't flip fast enough to catch reversals)
3. Existing tape + orderbook data is collected but underused as entry gates

The bot's edge exists — non-AE exits made +$12.69 this week. Adverse exits clawed back -$10.43. The fix is filtering bad entries, not changing the strategy.

## Success Criteria

- Adverse exit rate: <30% of trades (from current ~40-50%)
- Daily trade count: naturally falls to 8-12 as bad entries get filtered
- Best days (like 3/27: 14 trades, 64% WR, +$2.91) remain possible
- No new dependencies or infrastructure — uses existing code

## Design: Three-Layer Entry Filter

All gates apply to the **live slot only**. Paper slots remain ungated (they bypass ensemble, flow veto, and time filters already). This preserves them as controls.

### Layer 1 — Rate Limiting (Prevent Re-Entry Loops)

**Changes to bot.py:**

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| Per-pair cooldown after loss | 120s (2 min) | 600s (10 min) | bot.py:1032 |
| Blacklist after 3 consecutive losses | 7200s (2 hr) | 14400s (4 hr) | bot.py:1028 |
| Global cooldown between entries | 30s | 120s (2 min) | bot.py:667 |
| Regime pause trigger | 4 of 6 losses | 3 of 5 losses | bot.py:1037 |
| Regime pause duration | 900s (15 min) | 1800s (30 min) | bot.py:1038 |

**New: Per-symbol daily trade cap (bot.py, after line ~671):**
- Max 3 trades per symbol per day
- Count open + closed trades where opened_at > day_start_epoch for that symbol
- Resets at midnight UTC

### Layer 2 — L2 Orderbook Gate (Tighten Existing Infrastructure)

**Change existing strategy gate (strategies.py:116-145):**
- Imbalance block threshold: ±0.3 → ±0.25

**New gate at order placement (bot.py, before line ~857):**
Uses the already-fetched `ob` variable from bot.py:707.

```
if direction == "long" and ob.imbalance < -0.25:
    block — "asks dominate book"
if direction == "short" and ob.imbalance > 0.25:
    block — "bids dominate book"
if direction == "long" and ask_walls exist and no bid_walls:
    block — "unmatched sell wall"
if direction == "short" and bid_walls exist and no ask_walls:
    block — "unmatched buy wall"
if ob.spread_pct > 0.15:
    block — "illiquid, spread too wide"
```

Fail-open: if `ob` is None, allow the trade.

### Layer 3 — Tape Gate (Activate Unused Data)

All data already computed by ws_feed.py and available in the `flow` variable.

**Tighten existing veto (bot.py:789):**
- Buy ratio long veto: 0.30 → 0.45
- Buy ratio short veto: 0.70 → 0.55

**New gates (bot.py, near line ~798):**

```
if direction == "long" and cvd_slope < -0.3:
    block — "cumulative selling accelerating"
if direction == "short" and cvd_slope > 0.3:
    block — "cumulative buying accelerating"

if direction == "long" and divergence == "bearish":
    block — "price rising but sellers gaining (trap)"
if direction == "short" and divergence == "bullish":
    block — "price falling but buyers gaining (trap)"

if direction == "long" and large_trade_bias < -0.3:
    block — "whales selling"
if direction == "short" and large_trade_bias > 0.3:
    block — "whales buying"
```

Minimum trade count threshold: 20 trades in current candle for tape gates to activate (existing pattern from bot.py:787). During low-volume hours (<20 trades), tape gates are inactive — this is intentional, as low-volume sessions (like 3/31 night) were profitable.

## Gate Interaction

A trade must pass ALL three layers. Any single layer can block. But each layer uses moderate thresholds — it takes genuine adverse conditions to trigger a block, not noise.

```
Signal fires → Layer 1 (cooldown/cap check)
                 ↓ pass
              Layer 2 (orderbook check)
                 ↓ pass
              Layer 3 (tape check)
                 ↓ pass
              Place order
```

## Paper Slot Changes

### Remove (underperformers / redundant)

| Slot | Reason | Action |
|------|--------|--------|
| 5m_atr_gate | Worst performer: 16 trades, -$6.24, 12.5% WR | **Remove** from self.slots + delete state file |
| 5m_v10_control | Replaced by legacy_control slot | **Remove** from self.slots + delete state file |
| 5m_sma_vwap | Consistently underperforms live: -$0.51 today | **Remove** from self.slots + delete state file |
| 8h_funding | No trades observed in analysis period | **Remove** from self.slots + delete state file |

### Keep (valuable)

| Slot | Reason |
|------|--------|
| 5m_liq_cascade | Best paper performer: +$0.98 today, selective entries |
| 5m_mean_revert | Second best: +$1.00 today, selective entries |
| 1h_momentum | Different timeframe, useful as 1H trend comparison |

### Add: Legacy Control Slot (NEW)

A frozen replica of the current live bot — runs the same strategy with the **old** gate thresholds. Purpose: directly measure whether the new gates improve performance vs. the pre-update version.

```python
StrategySlot(
    slot_id="5m_legacy_control",
    strategy_name="confluence",
    timeframe="5m",
    max_positions=2,
    capital_pct=0.0,
    paper_mode=True,
)
```

**Key behavior:** Paper slots bypass ensemble confidence, flow veto, and time filters (bot.py:952-1018). So the legacy slot naturally runs without the new Layer 2/3 gates. It also doesn't have the live slot's cooldown changes (Layer 1), since paper slots use their own isolated RiskManager. This means the legacy slot automatically replicates pre-update behavior with no extra code.

**State file:** `trading_state_5m_legacy_control.json` (auto-created)

**Comparison metric:** After 5 days, compare live slot vs legacy_control on:
- Trade count, win rate, AE rate, PnL
- If live is better → gates are working
- If legacy is better → gates are too tight, loosen thresholds

## Files Changed

| File | Changes |
|------|---------|
| bot.py:102-166 | Remove 4 paper slots (atr_gate, v10_control, sma_vwap, 8h_funding), add legacy_control |
| bot.py:667 | Global cooldown 30→120 |
| bot.py:~671 (new) | Per-symbol daily trade cap (3, counts open + closed) |
| bot.py:789-798 | Tighten buy_ratio veto, add CVD/divergence/large_trade gates |
| bot.py:~857 (new block) | L2 orderbook gate before order placement |
| bot.py:1028 | Blacklist 7200→14400 |
| bot.py:1032 | Per-pair cooldown 120→600 |
| bot.py:1037-1038 | Regime pause 4/6→3/5, 900→1800 |
| strategies.py:116-145 | Imbalance gate ±0.3→±0.25 |

## Logging

All gate blocks logged with `[RATE GATE]`, `[OB GATE]`, or `[TAPE GATE]` prefix for post-analysis. No silent blocks.

## Tuning Plan

1. **Run for 5 trading days** after deployment
2. Compare live slot vs legacy_control slot on: trade count, win rate, AE rate, PnL
3. Compare against baseline week (3/26-4/01) stored in memory/reference_performance_baseline.md
4. **Adjust if:**
   - AE rate not dropping below 30% → tighten thresholds further
   - Trade count drops below 4/day consistently → loosen tape/OB gates
   - Legacy control outperforms live → gates are too aggressive, roll back specific layers
5. **Generate daily report** comparing live vs legacy_control

## Rollback Plan

All changes are threshold adjustments to existing code or additive gates. Rollback = revert the numbers. No structural changes, no new dependencies. Paper slot changes are independent — can re-add removed slots anytime by re-adding to self.slots list.

## What This Does NOT Change

- Strategy logic (htf_confluence_pullback signal generation)
- Exit logic (adverse_exit, stop_loss, take_profit thresholds)
- Position sizing
- Liq Cascade, Mean Revert, or 1H Momentum paper slots

## Expected Impact (Based on Apr 1 Data)

| Metric | Before | After (estimated) |
|--------|--------|-------------------|
| Trades | 17 | ~8-10 |
| Adverse exits | 9 (53%) | ~2-3 (~25%) |
| PnL | -$2.20 | ~+$0.50 to +$1.50 |
| Win rate | 35% | ~45-55% |
| Paper slots | 7 (4 useless) | 4 (all purposeful) |
