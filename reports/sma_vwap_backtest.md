# SMA(9) + SMA(15) + VWAP Filter Backtest

**Date**: 2026-03-25 04:59 UTC

**Trades analyzed**: 247 (skipped 0, 19 without timestamps)

## Filter Logic

- **LONG**: close > SMA(9), SMA(9) > SMA(15), close > VWAP
- **SHORT**: close < SMA(9), SMA(9) < SMA(15), close < VWAP
- **ADX gate**: 5m ADX > 20

## Results Summary

| Scenario | Trades | Wins | Losses | WR% | Total PnL | Avg PnL |
|----------|--------|------|--------|-----|-----------|----------|
| A: Current v10 (all trades) | 247 | 83 | 164 | 33.6% | $-32.64 | $-0.1321 |
| B: SMA+VWAP filter | 109 | 37 | 72 | 33.9% | $-12.33 | $-0.1131 |
| C: ADX + SMA+VWAP | 88 | 35 | 53 | 39.8% | $-6.43 | $-0.0731 |

## Filter Impact

### Scenario B (SMA+VWAP only)

- Trades removed: 138
- Winners removed: 46 | Losers removed: 92
- PnL of removed trades: $-20.31
- **Net improvement**: $+20.31

### Scenario C (ADX + SMA+VWAP)

- Trades removed: 159
- Winners removed: 48 | Losers removed: 111
- PnL of removed trades: $-26.21
- **Net improvement**: $+26.21

## Per-Side Breakdown

| Scenario | Trades | WR% | PnL | Avg PnL |
|----------|--------|-----|-----|----------|
| A: LONG | 164 | 34.8% | $-22.39 | $-0.1365 |
| B: LONG (SMA+VWAP) | 73 | 38.4% | $-8.17 | $-0.1119 |
| C: LONG (ADX+SMA+VWAP) | 58 | 44.8% | $-4.55 | $-0.0785 |
| A: SHORT | 83 | 31.3% | $-10.25 | $-0.1235 |
| B: SHORT (SMA+VWAP) | 36 | 25.0% | $-4.16 | $-0.1156 |
| C: SHORT (ADX+SMA+VWAP) | 30 | 30.0% | $-1.88 | $-0.0626 |

## Biggest Losers Filtered by B (Saved Money)

| Date | Symbol | Side | PnL | ADX | Strategy |
|------|--------|------|-----|-----|----------|
| 03/13 17:29 | TRUMP/USDT:USDT | long | $-3.55 | 19 | unknown |
| 03/15 00:46 | OP/USDT:USDT | short | $-2.06 | 55 | unknown |
| 03/15 03:36 | NEAR/USDT:USDT | long | $-1.76 | 54 | unknown |
| 03/24 11:57 | SOL/USDT:USDT | long | $-1.70 | 16 | htf_confluence_pullback |
| 03/14 04:38 | WIF/USDT:USDT | long | $-1.69 | 13 | unknown |
| 03/15 03:27 | RENDER/USDT:USDT | long | $-1.32 | 37 | unknown |
| 03/13 12:02 | SOL/USDT:USDT | short | $-1.29 | 36 | unknown |
| 03/18 04:02 | FET/USDT:USDT | long | $-1.27 | 10 | bb_mean_reversion |
| 03/13 12:02 | XRP/USDT:USDT | short | $-1.25 | 23 | unknown |
| 03/14 05:25 | SOL/USDT:USDT | long | $-1.24 | 21 | unknown |
| 03/14 05:25 | XRP/USDT:USDT | long | $-1.21 | 20 | unknown |
| 03/13 05:03 | LINK/USDT:USDT | long | $-1.21 | 12 | unknown |
| 03/17 15:13 | ETH/USDT:USDT | long | $-1.19 | 19 | bb_mean_reversion |
| 03/17 05:18 | FET/USDT:USDT | long | $-1.06 | 27 | trend_pullback |
| 03/17 05:30 | WIF/USDT:USDT | long | $-1.04 | 27 | synced |

## Biggest Winners Filtered by B (Missed Gains)

| Date | Symbol | Side | PnL | ADX | Strategy |
|------|--------|------|-----|-----|----------|
| 03/14 14:02 | WIF/USDT:USDT | long | $+3.28 | 14 | unknown |
| 03/13 15:27 | SOL/USDT:USDT | short | $+1.72 | 34 | unknown |
| 03/17 03:26 | DOGE/USDT:USDT | short | $+1.52 | 22 | trend_pullback |
| 03/15 21:01 | SUI/USDT:USDT | long | $+1.46 | 24 | bb_mean_reversion |
| 03/14 21:10 | WIF/USDT:USDT | long | $+1.46 | 17 | unknown |
| 03/16 03:08 | DOGE/USDT:USDT | long | $+1.43 | 17 | trend_pullback |
| 03/15 00:09 | WIF/USDT:USDT | long | $+1.43 | 43 | unknown |
| 03/14 21:26 | RENDER/USDT:USDT | long | $+1.41 | 17 | unknown |
| 03/15 01:32 | ETH/USDT:USDT | long | $+1.41 | 29 | unknown |
| 03/23 16:46 | SOL/USDT:USDT | long | $+1.39 | 26 | htf_confluence_pullback |
| 03/17 17:42 | FET/USDT:USDT | long | $+0.99 | 17 | trend_pullback |
| 03/18 02:01 | RENDER/USDT:USDT | long | $+0.98 | 19 | trend_pullback |
| 03/13 05:03 | XRP/USDT:USDT | long | $+0.95 | 18 | unknown |
| 03/23 06:15 | SOL/USDT:USDT | short | $+0.93 | 23 | htf_confluence_pullback |
| 03/15 01:08 | LINK/USDT:USDT | long | $+0.92 | 35 | unknown |

## Verdict

**Scenario B (SMA+VWAP) improves PnL by $+20.31** while reducing trade count from 247 to 109.

**Scenario C (ADX+SMA+VWAP) improves PnL by $+26.21** with 88 trades.
