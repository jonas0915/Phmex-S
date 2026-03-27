# v10 Trades: SMA(9) + SMA(15) + VWAP Filter Backtest

**Date**: 2026-03-25 05:07 UTC

**Scope**: v10 trades only (#247-266, Mar 22 onward)

**Trades analyzed**: 20 (skipped 0)

## Filter Logic

- **LONG**: close > SMA(9), SMA(9) > SMA(15), close > VWAP
- **SHORT**: close < SMA(9), SMA(9) < SMA(15), close < VWAP
- **ADX gate**: 5m ADX > 20

## Results Summary

| Scenario | Trades | Wins | Losses | WR% | Total PnL | Avg PnL |
|----------|--------|------|--------|-----|-----------|----------|
| A: Current v10 | 20 | 8 | 12 | 40.0% | $-1.66 | $-0.0829 |
| B: SMA+VWAP only | 3 | 1 | 2 | 33.3% | $-0.55 | $-0.1848 |
| C: ADX + SMA+VWAP | 2 | 1 | 1 | 50.0% | $-0.10 | $-0.0505 |

## Filter Impact

### Scenario B (SMA+VWAP only)

- Trades removed: 17
- Winners removed: 7 | Losers removed: 10
- PnL of removed trades: $-1.10
- **Net improvement**: $+1.10

### Scenario C (ADX + SMA+VWAP)

- Trades removed: 18
- Winners removed: 7 | Losers removed: 11
- PnL of removed trades: $-1.56
- **Net improvement**: $+1.56

## Trade-by-Trade Detail

| # | Symbol | Side | Strategy | PnL | Passed B? | Passed C? |
|---|--------|------|----------|-----|-----------|----------|
| 247 | XRP/USDT:USDT | short | synced | $-0.15 | no | no |
| 248 | SOL/USDT:USDT | short | htf_confluence_pullback | $+0.93 | no | no |
| 249 | ETH/USDT:USDT | short | htf_confluence_pullback | $+0.32 | no | no |
| 250 | SOL/USDT:USDT | short | htf_confluence_pullback | $+0.79 | no | no |
| 251 | XRP/USDT:USDT | long | momentum_continuation | $+0.49 | YES | YES |
| 252 | BTC/USDT:USDT | long | htf_confluence_pullback | $-0.61 | no | no |
| 253 | SOL/USDT:USDT | long | htf_confluence_pullback | $-0.71 | no | no |
| 254 | BTC/USDT:USDT | long | htf_confluence_pullback | $+0.59 | no | no |
| 255 | SOL/USDT:USDT | long | htf_confluence_pullback | $+1.39 | no | no |
| 256 | SOL/USDT:USDT | long | htf_confluence_pullback | $-0.59 | YES | YES |
| 257 | BNB/USDT:USDT | long | htf_confluence_pullback | $-0.25 | no | no |
| 258 | ETH/USDT:USDT | long | htf_confluence_pullback | $-0.52 | no | no |
| 259 | ETH/USDT:USDT | long | synced | $-0.47 | no | no |
| 260 | BTC/USDT:USDT | long | htf_confluence_pullback | $-0.45 | YES | no |
| 261 | ETH/USDT:USDT | long | htf_confluence_pullback | $+0.66 | no | no |
| 262 | ETH/USDT:USDT | long | htf_confluence_pullback | $+0.45 | no | no |
| 263 | BTC/USDT:USDT | long | htf_confluence_pullback | $-0.55 | no | no |
| 264 | SOL/USDT:USDT | long | htf_confluence_pullback | $-1.70 | no | no |
| 265 | XRP/USDT:USDT | short | htf_confluence_pullback | $-0.73 | no | no |
| 266 | BNB/USDT:USDT | short | htf_confluence_vwap | $-0.54 | no | no |

## Per-Side Breakdown

| Scenario | Trades | WR% | PnL | Avg PnL |
|----------|--------|-----|-----|----------|
| A: LONG | 14 | 35.7% | $-2.29 | $-0.1637 |
| B: LONG (SMA+VWAP) | 3 | 33.3% | $-0.55 | $-0.1848 |
| C: LONG (ADX+SMA+VWAP) | 2 | 50.0% | $-0.10 | $-0.0505 |
| A: SHORT | 6 | 50.0% | $+0.63 | $+0.1058 |
| B: SHORT (SMA+VWAP) | 0 | 0.0% | $+0.00 | $+0.0000 |
| C: SHORT (ADX+SMA+VWAP) | 0 | 0.0% | $+0.00 | $+0.0000 |

## Verdict

**Scenario B (SMA+VWAP) improves PnL by $+1.10** while reducing trade count from 20 to 3.

**Scenario C (ADX+SMA+VWAP) improves PnL by $+1.56** with 2 trades.
