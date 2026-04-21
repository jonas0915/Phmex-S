# Defensive Gates + gotAway Log + Maker Fill Improvement — Design Spec

**Date:** 2026-04-11
**Status:** Approved
**Context:** 48-hour audit found -$4.86 net PnL, 26.7% WR. Divergence gate bypassed in low-volume conditions. QUIET regime entries at 0% WR. No mechanism to track blocked trades. Taker fees eating $1.20 on 15 trades (~$0.08/trade avg vs $0.02 if all maker).

## Problem Statement

1. **Divergence gate bypass** — `bot.py:1014-1016`: when `trade_count <= 20`, the entire tape gate block is skipped, including divergence. Divergence (price-vs-CVD direction) is valid regardless of trade volume. Trades with bearish divergence entered long and lost.
2. **QUIET regime unguarded** — `_classify_regime()` produces QUIET label (5m ADX 20-25, no EMA alignment) but it's only logged in `entry_snapshot`, never used as a gate. 0% WR across 5 trades with QUIET regime.
3. **No gotAway tracking** — when gates block trades, there's no record of what was blocked. Can't validate if gates are helping or hurting.
4. **Missing htf_adx in entry_snapshot** — the 1h ADX value used by the actual gate is not recorded, making post-hoc audits impossible without raw logs (which rotate).
5. **Low maker fill rate on entries and exits** — `_try_limit_then_market` waits only 3s before falling to market (taker 0.06%). `_try_limit_exit` waits only 2s. Log data shows ~50% market fallback rate. On $100 notional, each taker fill costs $0.05 more than maker. Over 414 trades, estimated $33+ in avoidable fees.

## Changes

### Change 1: Fix Divergence Gate Bypass

**File:** `bot.py`
**Location:** After the existing tape gate block (line ~1053), before funding rate modifier (line ~1055)

Add a standalone divergence check that runs **regardless of trade_count**. The existing tape gate block stays as-is (buy_ratio, CVD slope, large_trade_bias still require `trade_count > 20` since they need volume to be meaningful).

```python
# Standalone divergence check — always active, even when tape gates skipped
# Divergence = price direction vs CVD direction; valid at any volume
if flow and flow.get("divergence"):
    _div = flow["divergence"]
    if direction == "long" and _div == "bearish":
        self._log_gotaway("divergence_bearish", symbol, direction, strat_name,
                          signal.strength, confidence, price, ob, flow, df)
        logger.info(f"[DIVERGENCE GATE] {symbol} LONG blocked — bearish divergence (always-on)")
        continue
    if direction == "short" and _div == "bullish":
        self._log_gotaway("divergence_bullish", symbol, direction, strat_name,
                          signal.strength, confidence, price, ob, flow, df)
        logger.info(f"[DIVERGENCE GATE] {symbol} SHORT blocked — bullish divergence (always-on)")
        continue
```

**Note:** When `trade_count > 20`, the existing divergence check inside the tape gate block fires first (lines 1042-1047). The standalone check is a safety net for low-volume conditions. Both paths log and continue, so there's no double-execution risk.

### Change 2: QUIET Regime Gate

**File:** `bot.py`
**Location:** After OB gate block (line ~1133), before order placement (line ~1135)

Compute 5m regime and block QUIET entries unless flow strongly confirms the direction. This accounts for the fact that pullbacks naturally have weak 5m momentum — we only block when there's truly no momentum anywhere.

```python
# QUIET regime gate — block low-momentum entries
# QUIET = 5m ADX 20-25 with no EMA stack alignment (0% WR in audit data)
# Allow through if flow CVD strongly confirms the trade direction
_regime_snap = self._classify_regime(df.iloc[-1], df)
if _regime_snap.get("label") == "QUIET":
    _flow_confirms = False
    if flow and flow.get("trade_count", 0) > 5:
        if direction == "long" and flow.get("cvd_slope", 0) > 0.2:
            _flow_confirms = True
        if direction == "short" and flow.get("cvd_slope", 0) < -0.2:
            _flow_confirms = True
    if not _flow_confirms:
        self._log_gotaway("quiet_regime", symbol, direction, strat_name,
                          signal.strength, confidence, price, ob, flow, df)
        logger.info(f"[REGIME GATE] {symbol} {direction.upper()} blocked — QUIET regime "
                    f"(5m ADX={_regime_snap.get('adx', '?')}) with no flow confirmation")
        continue
```

### Change 3: gotAway JSONL Log

**File:** `bot.py`
**New method:** `_log_gotaway()`

Writes blocked-trade snapshots to `logs/gotAway.jsonl` for post-hoc validation. Reuses the existing `_classify_regime()` and snapshot pattern.

```python
def _log_gotaway(self, reason: str, symbol: str, direction: str, strategy: str,
                 strength: float, confidence: int, price: float,
                 ob: dict | None, flow: dict | None, df=None):
    """Log a trade that was blocked by defensive gates for later analysis."""
    import json as _json
    entry = {
        "ts": int(time.time()),
        "reason": reason,
        "symbol": symbol,
        "direction": direction,
        "strategy": strategy,
        "strength": round(strength, 3),
        "confidence": confidence,
        "price": round(price, 6),
        "ob": {
            "imbalance": round(ob.get("imbalance", 0), 3),
            "spread_pct": round(ob.get("spread_pct", 0), 4),
        } if ob else None,
        "flow": {
            "buy_ratio": round(flow.get("buy_ratio", 0), 3),
            "cvd_slope": round(flow.get("cvd_slope", 0), 4),
            "divergence": flow.get("divergence"),
            "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
            "trade_count": flow.get("trade_count", 0),
        } if flow else None,
        "regime": self._classify_regime(df.iloc[-1], df) if df is not None and len(df) > 0 else None,
    }
    try:
        with open("logs/gotAway.jsonl", "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass
```

### Change 4: Add htf_adx to entry_snapshot

**File:** `bot.py`
**Location:** `_log_entry_snapshot()` method (line ~1409)

Add `htf_adx` parameter and include it in the snapshot dict so the actual gating value is preserved.

1. Update `_log_entry_snapshot()` signature to accept `htf_adx: float = None`
2. Add `"htf_adx": htf_adx` to the snapshot dict
3. Pass `htf_adx` from the entry flow where `htf_df` data is available

### Change 5: Limit-Only Entries (No Market Fallback)

**Files:** `exchange.py`
**Methods:** `_try_limit_then_market()` (entries), `_try_limit_exit()` (software exits)

Current fee structure on Phemex:
- **Maker: 0.01%** (limit orders that add liquidity)
- **Taker: 0.06%** (market orders that take liquidity)
- **SL on exchange: always taker** (can't change — must execute immediately)
- **TP on exchange: limit/maker** (already optimal)

**Problem:** Entry limit orders wait 3s, then cancel and send a market order at 6x the fee. ~50% of entries fall through to taker. On $100 notional, each taker fill costs $0.05 more than maker.

**Fix — Entries become limit-only. No market fallback:**

```
Limit at best_bid (long) / best_ask (short) → wait 5s (10 polls × 0.5s)
  If filled → proceed as normal
  If not filled → cancel → return None → bot skips this entry
```

**Why this is safe:**
- `htf_confluence_pullback` signals are based on 5m candle conditions (1h ADX, EMA pullback, RSI). These persist across multiple candles. If the limit misses, the same signal fires next cycle (60s later).
- A failed limit does NOT trigger the 2-min global cooldown or HTF cluster throttle — only successful entries set those timers. So the bot retries immediately next cycle.
- If price moved so fast our limit missed, chasing with a market order gives a worse fill AND 6x higher fees. Skipping is the correct action.
- The bot runs a 60s cycle on a 5m timeframe. Missing one cycle is 1/5 of a candle — insignificant for pullback setups.

**Rename method:** `_try_limit_then_market()` → `_try_limit_entry()` to reflect the new behavior. Update callers in `open_long()` and `open_short()` to handle `None` return (already handled — bot.py line 1136 checks `if order:`).

**Exits stay as-is (limit-first, market-fallback):**
Exits keep the current approach because being stuck in a losing position is worse than paying taker fees. Extend `_try_limit_exit()` wait from 2s to 4s (8 polls) to give more time for maker fills on non-urgent exits (flat_exit, time_exit). adverse_exit uses same path — 4s delay is acceptable since the -5% ROI threshold already triggered.

**Add maker/taker fill tracking:**
Log `[MAKER]` vs `[TAKER]` tag on every fill so we can measure improvement:
```python
logger.info(f"[FILL] {symbol} {side} — MAKER @ {fill_price}")  # or TAKER
```

**Expected impact:** Every entry becomes maker (0.01% vs 0.06%). On $100 notional, saves $0.05/trade. Some entries will be missed when limits don't fill, but those would have been worse fills at higher fees. Net positive.

## What Does NOT Change

- No parameter changes (SL, TP, confidence threshold, time blocks, cooldowns)
- No strategy logic changes (htf_confluence_pullback, momentum_continuation, etc.)
- No exit logic changes (adverse_exit, flat_exit, time_exit thresholds)
- Existing tape gates (buy_ratio, CVD slope, large_trade_bias) still require `trade_count > 20`
- Paper slot evaluation logic unchanged

## Testing

1. Syntax check: `python3 -c "import bot"`
2. Verify gotAway.jsonl is created on first blocked trade
3. Verify entry_snapshot now includes htf_adx field
4. Monitor logs for `[DIVERGENCE GATE]` and `[REGIME GATE]` messages
5. Run `/pre-restart-audit` before deploying

## Rollback

All changes are additive gates with `continue` — removing any gate just lets more trades through. No state format changes, no config changes. Safe to revert by commenting out individual gate blocks.
