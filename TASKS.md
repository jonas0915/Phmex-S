# v7.0 "Confluence" — Strategy Rebuild

## Why
245 trades, -$23.47, 36% WR, profit factor 0.688. Every version has gotten worse. The bot overtrades on single-indicator signals without higher-timeframe context. Internet research + 245-trade data analysis both point to the same fix: multi-timeframe confluence entries.

## What Works (KEEP)
- early_exit: 100% WR, +$16.68 — the profit engine. Don't touch.
- VWAP reversion: 57% WR — only positive strategy. Evolve it.
- Connectivity fixes (P4): WS staleness, REST timeout. Keep.
- Dynamic volume scanner: top 7 by volume. Keep.
- Blacklist: TRUMP/FET/TIA/NEAR/OP. Keep.

## What's Broken (REPLACE)
- momentum_continuation: 9.1% WR, -$1.92 — KILL
- trend_pullback: 39% WR but -$6.30 — KILL
- keltner_squeeze: 29% WR, -$0.90 — KILL
- trend_scalp: already removed
- adaptive router: routes to broken strategies — REPLACE

## The New Architecture

### Add 1h Higher Timeframe Data
- REST-based 1h candle cache in bot.py (cached 5 min, same pattern as Good-bot)
- Run `add_all_indicators()` on 1h data
- Pass `htf_df` to strategy function

### Strategy 1: `htf_confluence_pullback` (Trending: 1h ADX ≥ 20)
ALL 5 required:
1. **1h trend** — EMA-21 > EMA-50, close > EMA-50, ADX ≥ 20 (long) / mirror for short
2. **VWAP gate** — 5m close > VWAP (long only) / < VWAP (short only)
3. **5m pullback** — price within 0.5% of EMA-21 or EMA-50, bouncing (close > open)
4. **RSI zone** — 35-60 for longs, 40-65 for shorts
5. **Volume** — ≥ 1.3x 20-period average

Strength: 0.80 base, +0.03 (1h ADX>30), +0.03 (stoch confirm), +0.03 (vol 2x+), +0.02 (OB), cap 0.92

### Strategy 2: `htf_confluence_vwap` (Ranging: 1h ADX < 20)
ALL 4 required:
1. **1h ranging** — ADX < 20, BB width > ATR (room to revert)
2. **VWAP deviation** — price ≥ 0.4% from VWAP + RSI(7) < 30 (long) or > 70 (short)
3. **Candle reversal** — close > prev close (long) / close < prev close (short)
4. **Volume** — ≥ 1.0x average

Strength: 0.82 base, +0.03 (VWAP dev>0.7%), +0.03 (extreme RSI), +0.02 (vol 1.5x+), +0.02 (OB), cap 0.90

### Master Router: `confluence_strategy`
- Requires htf_df (no HTF = no trade)
- CHOP > 65 → HOLD
- 1h ADX ≥ 20 → `htf_confluence_pullback`
- 1h ADX < 20 → `htf_confluence_vwap`

## Config Changes (.env)
- `STRATEGY=confluence` (new, easy rollback to `adaptive`)
- `SCALP_MIN_STRENGTH=0.80`
- `MAX_OPEN_TRADES=2` (capital preservation at $20 balance)
- `TRADE_AMOUNT_USDT=8.0` (reduce from 10)
- `SCANNER_TOP_N=5` (fewer pairs, more focus)

## Time Exits (risk_manager.py)
- `htf_confluence_pullback`: soft=25, hard=75
- `htf_confluence_vwap`: soft=15, hard=45

## Files to Modify
1. `strategies.py` — 2 new strategies + confluence router (keep old strategies for rollback)
2. `bot.py` — Add HTF cache, pass htf_df to strategy, remove half-size band-aid
3. `risk_manager.py` — Add time exit thresholds for new strategies
4. `.env` — Config changes
5. `config.py` — No changes needed (existing env var loading works)

## Implementation Order
- [ ] 1. Add `_htf_cache` + `_fetch_htf_data()` to bot.py
- [ ] 2. Write `htf_confluence_pullback` in strategies.py
- [ ] 3. Write `htf_confluence_vwap` in strategies.py
- [ ] 4. Write `confluence_strategy` router in strategies.py
- [ ] 5. Update STRATEGIES dict + bot.py strategy call to pass htf_df
- [ ] 6. Update STRATEGY_TIME_EXITS in risk_manager.py
- [ ] 7. Update .env config
- [ ] 8. Compile check all files
- [ ] 9. Deploy audit agents on all modified files
- [ ] 10. Restart with cleared cache, verify logs

## Expected Outcome
- 3-5 trades/day (down from 24)
- 45-55% WR (up from 36%)
- time_exits drop dramatically (HTF-confirmed entries are directionally aligned)
- early_exit continues capturing momentum runs
- Rollback: change .env STRATEGY=adaptive
