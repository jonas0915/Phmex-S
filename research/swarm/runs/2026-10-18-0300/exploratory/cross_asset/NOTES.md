# cross_asset lens notes (run 2026-10-18-0300) — EXPLORATORY, not evidence. Result: 0 theses.

Web log: 9 WebSearch calls (none refused), 2 WebFetch calls (both opened):
- https://arxiv.org/abs/2602.23762 and https://arxiv.org/html/2602.23762v1 (Ma, Bao, Wen, "One Rising Ship Sinks Other Ships", Feb 2026): half-day returns 2022-04-28 to 2025-03-31, on-chain chain-level portfolios; reports CONTEMPORANEOUS negative cross-chain coefficients (e.g. Ethereum on Arbitrum beta = -0.140, per the fetched page) and only an own-lag reversal term; no lagged cross-chain predictive term. Not tradeable as a lead-lag; own-lag half-day reversal is row 2 / row 76 territory. Not cited in any thesis.
- Searches on SPX/NDX-futures -> BTC hourly lead-lag, Treasury-yield shocks -> BTC hourly drift, equity-hours vs off-hours persistence, alt downside-beta underreaction, residual/idiosyncratic alt momentum, large->small coin daily diffusion: no 2024-2026 source with a lagged, tradeable number. Search summaries only (not opened, not cited): Guo/Sang/Tu/Wang JEDC 2024 cross-crypto predictability is minute-scale (~10 min) and a long-short XS portfolio (row 5 + owner XS directive); Quantpedia BTC overnight/intraday split and Bespoke 2022 US-open drop are calendar effects (rows 7, 113, weekend ETF catch-up gate-rejected 2026-09-27).

Why no thesis:
1. Neither screenable dataset (mr_edge 35 crypto perps, long_1h 19 crypto perps) carries SPX/NDX/DXY/rates series, and the bot has no such feed, so CONSTRAINTS viable item 5 fails for any direct equity/rates spillover signal.
2. Every crypto-only proxy for the lens relabels a dead row: BTC->alt lag/shock (rows 106, 112), ETH/BTC regime -> alt beta (row 107), US-session / ETF-window / weekend timing (rows 7, 113), session -> overnight reversal (rows 7, 76), cross-coin XS spillover (row 5), alt-vs-major short-horizon reversion (row 2), pairs (row 8).
3. The one new 2026 source found (2602.23762) is contemporaneous-only; building a lagged signal from it would mean citing a statistic the paper does not report.

No probes run, no data loaded this run (no train or holdout reads). Second thesis slot left unused deliberately.
