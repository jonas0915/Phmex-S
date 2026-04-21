# Momentum Router + Volume Gate Fix

**Date:** 2026-03-23
**Problem:** Bot missed a 7% ETH move because the confluence router has no momentum/breakout path. When ADX is high and price runs away from EMAs, only `htf_confluence_pullback` runs — and it HOLDs because there's no pullback to enter on. Additionally, the 0.8x volume gate blocks nearly all candles (readings of 0.03x-0.79x consistently).

**Solution:** Wire existing `momentum_continuation_strategy` into the confluence router with an HTF confirmation guard, and lower the pullback volume gate.

---

## Changes

### 1. Confluence Router (strategies.py, `confluence_strategy`, lines 968-993)

**Current routing:**
```
ADX >= 20 → htf_confluence_pullback
ADX < 25  → htf_confluence_vwap
ADX < 25 + Hurst < 0.5 → bb_mean_reversion
```

**New routing:**
```
ADX >= 20 → htf_confluence_pullback       (unchanged)
ADX >= 25 → momentum_continuation + HTF guard (NEW)
ADX < 25  → htf_confluence_vwap           (unchanged)
ADX < 25 + Hurst < 0.5 → bb_mean_reversion (unchanged)
```

When ADX >= 25, `momentum_continuation_strategy` is called. Before appending its signal, apply an **HTF direction guard**:
- LONG only if 1h EMA-21 > 1h EMA-50
- SHORT only if 1h EMA-21 < 1h EMA-50
- If HTF disagrees, discard the signal (HOLD)

This prevents counter-trend momentum entries that would lack higher-timeframe confirmation.

**Implementation pseudocode** (insert after line 970, before the VWAP block):
```python
    if htf_adx >= 25:
        mom_signal = momentum_continuation_strategy(df, orderbook)
        if mom_signal.signal != Signal.HOLD:
            htf_ema21 = htf_df.iloc[-1].get("ema_21", 0)
            htf_ema50 = htf_df.iloc[-1].get("ema_50", 0)
            htf_agrees = (
                (mom_signal.signal == Signal.BUY and htf_ema21 > htf_ema50) or
                (mom_signal.signal == Signal.SELL and htf_ema21 < htf_ema50)
            )
            if htf_agrees and htf_ema21 != 0 and htf_ema50 != 0:
                signals.append(mom_signal)
                _log.debug(f"[CONFLUENCE] momentum_cont passed HTF guard (1h ADX={htf_adx:.1f})")
            else:
                _log.debug(f"[CONFLUENCE] momentum_cont blocked by HTF guard (1h EMA21={'>' if htf_ema21>htf_ema50 else '<'}EMA50)")
```

The existing `max(active, key=lambda s: s.strength)` selector picks the strongest non-HOLD signal. Pullback (0.84 base) wins over momentum (0.72 base) when both fire, which is correct — pullback is higher conviction. Momentum only wins when pullback HOLDs.

**SHORT strength gate interaction:** momentum base is 0.72. After the -0.04 short penalty (bot.py:680), shorts start at 0.68. The SCALP_MIN_STRENGTH gate is 0.80, so shorts need 3 of 4 bonuses (stoch +0.04, VWAP +0.04, ADX>35 +0.03, volume spike +0.03) to pass. This means momentum shorts will be rare but not impossible. Longs need only 2 of 4 bonuses — more achievable.

**Note:** `momentum_continuation_strategy` is also referenced in `adaptive_strategy` (lines 685, 691) without HTF guard. This is irrelevant while running `confluence` strategy but should be noted if switching strategies in the future.

### 2. Volume Gate (strategies.py, `htf_confluence_pullback`, line 755)

**Current:** `volume < vol_avg * 0.8` (blocks if below 80% of 20-period SMA)
**New:** `volume < vol_avg * 0.5` (blocks if below 50% of 20-period SMA)

Rationale: Logs show readings of 0.03x-0.79x consistently. The 0.8x gate vetoes nearly every candle, preventing the other 4 pullback conditions from being evaluated. Lowering to 0.5x still filters dead candles while letting reasonable volume through.

### 3. No changes to momentum_continuation_strategy itself

The function at strategies.py:410-548 is used as-is. Its existing guards:
- ADX > 20 (confirmed trend)
- EMA-21/EMA-50 alignment (direction)
- MACD histogram expanding in trend direction
- Price within 3% of EMA-21 (no chasing)
- Volume >= 1.0x average
- RSI range (40-70 long, 30-60 short)
- OB confirmation (blocks contradicting imbalance)

---

## Impact Analysis

| Strategy | Impact |
|----------|--------|
| htf_confluence_pullback | Volume gate loosened — more candles evaluated. All other gates unchanged. |
| htf_confluence_vwap | Zero impact — routing and code unchanged. |
| bb_mean_reversion | Zero impact — routing and code unchanged. |
| momentum_continuation | Now called from confluence router when ADX >= 25, with HTF guard. |

## Conflict Resolution

When ADX is 25+, both pullback and momentum may fire:
- Pullback base strength: 0.84
- Momentum base strength: 0.72
- Pullback wins when both fire (correct — higher conviction)
- Momentum fills in when pullback HOLDs (the gap we're fixing)

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Momentum enters at top of move, reversal follows | Medium | SL 1.2%, adverse_exit at -3% ROI/10min, max loss ~$1.20/trade |
| Lower volume gate lets weak pullback signals through | Low | 4 other gates still filter (HTF trend, VWAP, RSI, momentum confirmation) |
| More trades = more fee exposure | Low | PostOnly maker fees $0.02/round-trip on $100 notional |
| Counter-trend momentum entry | Low | HTF EMA guard eliminates this |

## Historical Precedent

momentum_continuation ran live in v6-v8. Log entries from Mar 20 show it produced entries on SOL, SUI, BNB. It was not removed for poor performance — it was not wired into the v7+ confluence router.

## Files Modified

- `strategies.py` — confluence_strategy router (~5 lines added), volume gate threshold (1 line changed)
