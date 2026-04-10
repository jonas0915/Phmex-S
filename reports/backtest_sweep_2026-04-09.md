# AE Rule Sweep — 90 Days, 5 Pairs (Jan 10 - Apr 9, 2026)

## Results

| Pair | ROI Trades | ROI WR | ROI Net | TF Trades | TF WR | TF Net | Winner |
|------|-----------|--------|---------|-----------|-------|--------|--------|
| BTC | 463 | 43.0% | -$126.09 | 1351 | 11.4% | -$251.52 | ROI |
| ETH | 359 | 48.7% | -$103.34 | 428 | 32.0% | -$76.94 | TF |
| SOL | 366 | 50.3% | -$113.59 | 436 | 35.3% | -$81.92 | TF |
| BNB | 298 | 46.0% | -$75.28 | 394 | 21.1% | -$70.39 | TF |
| XRP | 361 | 46.3% | -$115.68 | 440 | 27.5% | -$84.74 | TF |
| **TOTAL** | **1847** | **46.5%** | **-$533.98** | **3049** | **24.1%** | **-$565.51** | **ROI** |

## Verdict: INCONCLUSIVE

- Trend-flip wins on **4/5 pairs** (ETH, SOL, BNB, XRP) by net PnL
- BUT **total net is worse** for trend-flip (-$565.51 vs -$533.98) due to BTC blowup
- BTC trend-flip generates 1351 trades (vs 463 ROI) — 1h EMA crosses too frequently on BTC
- On altcoins, trend-flip saves $25-35/pair by cutting losses earlier
- Neither rule is profitable — backtester lacks OB/tape gates, so these numbers overstate losses

## Recommendation

Keep ROI as default. Consider per-pair gating: trend-flip for altcoins, ROI for BTC.
This is a future research item, not actionable now.

## Caveat

Backtester has no OB/tape/cooldown gates — it over-trades 2.7x vs live (see calibration in backtester_audit.md). Use these results for **relative** comparison only, not absolute PnL forecasting.
