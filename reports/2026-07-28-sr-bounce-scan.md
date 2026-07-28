# SR_BOUNCE kill-gate scan — 2026-07-28

**TRAIN (diagnostics only)**: 8703 trades | WR 24.9% | net $-634.17 | per-trade $-0.0729 | avg risk 0.20% / reward 0.46%

**HOLDOUT (the verdict)**: 5084 trades | WR 25.1% | net $-358.42 | per-trade $-0.0705 | avg risk 0.19% / reward 0.39%

## VERDICT vs pre-registered DOA line: **DO-NOT-BUILD**
- line: holdout net-per-trade <= $0 fee-incl OR holdout n < 20

## Per-pair (all trades)
- 1000PEPE/USDT:USDT: 1519 trades, net $-113.63
- 1000SHIB/USDT:USDT: 1626 trades, net $-114.39
- ADA/USDT:USDT: 1126 trades, net $-90.60
- BTC/USDT:USDT: 1431 trades, net $-93.83
- DOGE/USDT:USDT: 1432 trades, net $-100.41
- ENA/USDT:USDT: 1250 trades, net $-117.99
- ETH/USDT:USDT: 1433 trades, net $-89.88
- LTC/USDT:USDT: 1475 trades, net $-106.27
- SOL/USDT:USDT: 1265 trades, net $-86.32
- XRP/USDT:USDT: 1230 trades, net $-79.28

## Bonus: real-trade zone-proximity diagnostic (report-only)
- winners n=55 median dist 0.51 ATR | losers n=38 median 0.48 ATR | p=0.3443 | excluded 663

## Receipts (appended post-review 2026-07-28)
- Data window: ~2026-04-29 → 2026-07-28 (~90d/pair; ~25,920 5m + ~2,160 1h candles/pair, 10 pairs, single fetch run)
- Simulation: $50 notional/trade ($5 margin × 10x), fee 0.12% of notional round-trip, PostOnly-style strict-through next-candle fills, both-barriers-touched → stop_loss, no-lookahead 1h context
- Frozen parameters (spec 2026-07-28, never tuned): k=3 pivots, 0.25×ATR(1h) zone cluster, ≥2 touches (gap ≥3), ADX<30 regime gate, SL = zone edge + 0.25×ATR(5m), TP = next opposing zone capped 3× risk, skip if room < 1× risk
- Test suite: 19/19 green before the run; scan executed once, 1:19–2:38 PM, 2026-07-28
- Caveats: the per-pair table above is ALL trades (train+holdout pooled per pair); the pre-registered verdict line is pooled-holdout and is what governs. Long/short split and maker fill rate were not logged — the verdict covers the confirmed-rejection bounce WITH PostOnly pullback entry; the unfilled-signal population is unmeasured.
- Derived gross (fee-free) check: holdout −$0.0705/trade + $0.06 fee = −$0.0105/trade gross — negative before any fee on the pooled holdout, and per-pair (net/trade + $0.06) is negative on all 10 pairs over all trades.
- Bonus-diagnostic note: "excluded 663" = older trade records with no opened_at field (pre-schema-change), non-scan symbols, trades outside the 90d cache window, and no-opposing-zone cases — excluded rather than mis-analyzed.
