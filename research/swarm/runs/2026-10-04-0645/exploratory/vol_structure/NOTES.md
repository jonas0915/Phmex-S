# vol_structure lens — run 2026-10-04-0645 — EXPLORATORY NOTES (not evidence)

Outcome: 0 theses registered. No data probes run (no load_data calls, no holdout, no mr_edge).

## Search log (WebSearch, 9 queries, all returned results; budget not exhausted)
1. bitcoin dealer gamma positioning negative gamma realized volatility return predictability 2025 paper
2. cryptocurrency volatility breakout strategy intraday range compression daily backtest 2024 2025 paper
3. realized skewness predicts bitcoin returns time series daily 2024 2025
4. volatility of volatility cryptocurrency returns predictability 2025 arxiv
5. intraday momentum cryptocurrency gamma hedging demand last half hour
6. cryptocurrency returns following low realized volatility regime vs high volatility regime
7. crypto options market makers short gamma hedging perpetual futures Deribit net gamma exposure
8. Zarattini noise area intraday momentum bitcoin crypto replication
9. bitcoin vanna charm flows dealers buy back hedges after volatility spike
10. SSRN 2025 bitcoin realized volatility shock predicts future returns time series

## Fetch log (WebFetch, 3 pages, all opened)
- https://ungeracademy.com/blog/trading-bitcoin-95000-in-2025-volatility-breakout — CME BTC futures ATR-channel breakout, 5m + daily; page reports "almost $600,000 from 2018 to present", average trade "over $850"; BACKTEST, no trade count, no win rate. Not a live record; no counterparty named.
- https://research.glassnode.com/gamma-exposure-heatmap/ — directional claims only (negative GEX = "volatility accelerators"); Aug-Nov 2025 negative GEX coincided with 120k -> ~80k; page itself says "limited case study"; NO quantitative statistics. Signal also needs Deribit options data the bot does not have (viability item 5).
- https://hashdex.com/en-US/insights/bitcoin-s-link-between-low-volatility-and-outsized-returns — low vol = annualized 30-day vol below 30%, 1-year forward horizon, 2010-12-01 to 2023-09-08, published 2023-09-18; gives NO numeric return comparison; horizon (1 year) and date (2023) are outside the desk's scope.

## Why no thesis
- Every directional vol-structure mechanism with a named forced counterparty found on the web needs options data (dealer GEX, vanna/charm, IV crush) that the bot does not have -> fails CONSTRAINTS viable #5.
- The realized-vol-only variants are relabels of rows already dead or rejected in this lens:
  compression->expansion continuation (shock_compression_drift 2026-09-17, rows 3/78/111), vol-scaled continuation (row 111),
  vol-targeter de-lever (termspread_delever 2026-09-17), expiry unclamp (row 105), MM withdrawal (row 104),
  positive-jump/lottery fade (gate-rejected 2026-09-27 as row 76), US-close LETF rebalance fade (probed null 2026-09-25,
  runs/2026-09-25-2036/exploratory/vol_structure/probe_letf_close_fade.out.txt), window/intraday momentum (row 113).
- Low-vol-regime long drift (Hashdex) has no quantified source and no forced counterparty; it is long-beta in a train era that fell.
- Sources found carry no number for the key claim, so any thesis would fail STANDARDS #2.
