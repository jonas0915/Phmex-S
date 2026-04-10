# Backtester Audit — 2026-04-09

## backtester.py (435L)
- CLI: `--strategy --pair --timeframe --days --margin --sl --tp --wfo`
- Strategy dispatch: STRATEGIES dict from strategies.py, `--strategy` flag isolates one
- Exit models: SL (fixed %), TP (fixed %), adverse_exit (ROI-based: -5% after 10 bars), trailing (5-tier), hard time exit (240 bars)
- Fee model: **Missing entirely** — PnL is gross only
- Data source: CSV files in backtest_data/ (pre-fetched via fetch_history.py)
- Single strategy isolation: yes
- HTF data: loads 1h CSVs, passes as htf_df to strategies (not used in exit logic yet)
- **Note**: `htf_confluence_pullback` is NOT in STRATEGIES dict — silently falls back to `confluence`

## backtest.py (1143L)
- CLI: `--pairs --days --timeframe --no-gates`
- Strategy dispatch: hardcoded `adaptive_strategy()` ensemble — no single-strategy isolation
- Exit models: SL (ATR-based), TP (ATR-based R:R), trailing (R-based), breakeven, early_exit, flat_exit, time exits — **no adverse_exit at all**
- Fee model: **Present** — 0.06%/side taker + 0.05% slippage
- Data source: live ccxt fetch (no CSV cache)

## Gaps vs Fix 5 needs
- Need: AE rule comparison (old ROI-based vs new trend-flip) over 90 days
- Need: fees + AE in same tool
- Plan: extend backtester.py — it has AE logic + HTF data + strategy isolation, just needs fees added
- CSV data is stale (ends Mar 23) — need to re-fetch via fetch_history.py for 90 days

## OB/tape caveat
Neither backtester replays L2 orderbook or tape buy_ratio gates. Both skip them entirely. Results will have higher trade count and lower quality than live (optimistic by ~5-10%).

## HTF data for trend-flip AE
backtester.py already loads 1h CSVs with indicators. EMA21/EMA50 available — just need to reference them in exit loop (currently only passed to entry strategy).

---

## Calibration: Backtester vs Live Sentinel (Apr 1-9, 2026)

### Live Sentinel (5 comparable pairs)
- Trades: 58, Net PnL: -$7.44, WR: 41.4%

### Backtester (confluence, --days 9, --ae-rule roi)
| Pair | Trades | WR | Net |
|------|--------|----|-----|
| BTC | 39 | 41.0% | -$11.28 |
| ETH | 36 | 58.3% | -$5.88 |
| SOL | 32 | 40.6% | -$13.93 |
| BNB | 23 | 39.1% | -$5.73 |
| XRP | 26 | 30.8% | -$12.13 |
| **Total** | **156** | **42.3%** | **-$48.95** |

### Discrepancy
- Trade count: backtest 156 vs live 58 (2.7x more — no OB/tape/cooldown gates)
- PnL: backtest -$48.95 vs live -$7.44 (6.6x worse)
- WR: ~42% both (aligned)
- **Verdict: PESSIMISTIC** — backtester over-trades without gates, generating low-quality entries the live bot correctly filters. Directional signal valid, absolute PnL not usable.
