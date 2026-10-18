# vol_structure lens — run 2026-10-18-0300 — EXPLORATORY NOTES (not evidence)

Outcome: 0 theses registered. No data probes run (no load_data calls, no holdout, no mr_edge, no fetch_ohlcv_ccxt).
WebSearch budget not exhausted (9 searches, all returned results).

## Search log (WebSearch)
1. bitcoin realized volatility shock subsequent returns time series predictability 2025 paper daily
2. cryptocurrency perpetual futures volatility-of-volatility predicts returns 2025 arxiv
3. crypto dual investment structured products market maker gamma hedging pinning price 2025
4. cryptocurrency jumps predict future returns negative jump reversal paper 2024 2025 high-frequency
5. volatility-managed portfolios cryptocurrency bitcoin realized variance timing 2024 2025 study results
6. bitcoin returns after extreme daily moves overreaction momentum next day 2024 2025 study
7. Kaiko OR Glassnode report bitcoin realized volatility record low compression followed by expansion 2025
8. realized skewness cryptocurrency predicts next week returns time-series 2024 2025 Journal
9. bitcoin volatility regime switch trend following performance high vs low volatility regimes 2025
10. "volatility of volatility" bitcoin returns predict 2025 OR 2026 vol-of-vol risk premium crypto

## Fetch log (WebFetch, 3 pages, all opened)
- https://panoptic.xyz/research/crypto-gamma-traps — seven short-gamma "traps" (Deribit coin-margined collateral, LP hedging, DOV auctions, negative GEX, sticky delta, vanna, convenience yield). Numbers on page: since Jan 2023 ~71% of BTC / 65% of ETH 30-day windows had positive spot-vol correlation vs 42%/43% earlier; BTC MM GEX "predominantly negative" in 2023. Every measure needs options data (GEX, IV, Greeks) the bot lacks -> fails CONSTRAINTS viable #5. No OHLCV-computable signal, no backtest.
- https://ar5iv.labs.arxiv.org/html/2110.09429 (Saef, Nagy, Sizov, Hardle; Digital Finance 2024) — intraday jumps do NOT predict next-day returns: lagged jump dummy coef 0.001 (SE 0.003), R2 0.000, 2,040 obs, BTC/BCH/ETC/ETH/LTC/XRP, 2019-04-12 -> 2021-02-08. Same-day effect only (-0.017, SE 0.006). This is evidence AGAINST a post-shock daily drift thesis.
- https://www.anserpress.org/journal/fel/5/2/53 (Tripathi, Financial Economics Letters 5(2):53, 2026-06-18) — BTC vol-targeted EMA trend performance statistically invariant across volatility regimes (fail to reject, p = 0.195); traditional assets regime-sensitive (p < 0.001). Evidence AGAINST conditioning BTC direction on realized-vol regime.

## Why no thesis
- Forced short-gamma counterparties with a documented number (dealer GEX, vanna/charm, DOV auctions, Deribit coin-M collateral) all need options data -> viable #5 fails.
- Realized-vol-only mechanisms found are relabels of dead/rejected rows in this lens: compression->expansion (rows 3, 78; 2026-09-17 shock_compression_drift), vol-targeter de-lever / vol-scaled continuation (row 111; 2026-09-17 termspread_delever), expiry unclamp (row 105), MM withdrawal (row 104), positive-jump/lottery fade (Lee & Wang JFQA 2025 — the 2026-09-27 lottery_jump_fade, gate-rejected vs row 76), liquidation-shock continuation/reversion (rows 6, 110).
- Post-shock daily drift: the one 2024 primary source opened (Saef et al.) reports no next-day effect.
- Glassnode/Kaiko compression coverage (search 7) is secondary press with no forward-return statistic; a Glassnode researcher is quoted saying compression bands have no predictive value. Not usable under STANDARDS #2.
