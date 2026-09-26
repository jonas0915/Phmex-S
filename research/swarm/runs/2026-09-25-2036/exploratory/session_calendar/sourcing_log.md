# session_calendar sourcing log — run 2026-09-25-2036 (EXPLORATORY, not evidence)

Outcome: 0 theses. No data probes run (no train data read). 10 WebSearch, 7 WebFetch (1 x 403).

Fetched (opened):
- https://www.quantseeker.com/p/turn-of-the-month-strategies-do-they — TOM: "Assets outside of equities show no evidence of the TOM effect, except for high-yield bonds (HYG) and possibly Bitcoin." No BTC numbers.
- https://paperswithbacktest.com/strategies/is-the-turn-of-the-month-an-anomaly-on-which-an-investment-strategy-could-be-based-evidence-from-bitcoin-and-ethereum — Vasileiou (2022) TOM BTC/ETH; page reports combined portfolio annual return 7.84%, Sharpe 0.53, MDD -29.68%.
- https://valuelytica.substack.com/p/end-of-month-effect-in-bitcoin — BTCE.DE 2021-2024; last 5 trading days strongest; EOM Sharpe 1.08, EOM Trend Sharpe 2.06; no t-stats; no mechanism.
- https://river.com/content/best-time-and-day-to-dca-bitcoin — since 2010; last 3 days of month 3.11%/6.83%/6.21% higher chance of monthly high than low; authors: "not statistically significant enough".
- https://river.com/content/dca-research-2026 — 2023-01..2025-10 weekly timing best/worst gap 0.77%; no day-of-month data.
- https://www.nber.org/system/files/working_papers/w33554/w33554.pdf — Harvey/Mazzoleni/Melone (rev. Jan 2026): equity overweight -> -17 bps next day; month-end concentrated; equities/bonds only, no crypto.
- https://paperswithbacktest.com/blog/bitcoin-never-sleeps-exploiting-seasonality — Padysak & Vojtko 2022: 21-23 UTC intraday effect (intraday = dead lens, row 76).
- 403: https://www.sciencedirect.com/science/article/pii/S1062940825000816 (not cited).

Why no thesis:
1. Month-end / TOM family: only descriptive seasonality sources, no crypto source naming a forced counterparty (window dressing / NAV marking search returned nothing crypto-specific). Mechanism-less seasonality = relabel of DEAD row 18 ("seasonality/halving/weekend all null", MEM/reference_nobarriers_search_2026-07-16.md:48-50) and row 7. Also ~10 independent month-ends in long_1h train -> events too few for an honest CI (cross-symbol trades are one clustered event).
2. Macro-release multi-day drift: Block Scholes / search summary says CPI response concentrated at 1-hour horizon; Nazaruk 2025 (prior run 2026-09-19-1451) found volatility not returns -> rows 84 + prior fomc_drift_short.
3. Rebalancing (Harvey et al.): equities/bonds only; transferring to crypto would be an unsourced key claim.
4. Weekend/Monday: rows 7, 18, 67; prior unscreened session_calendar_weekend_thinbook_fade (runs/2026-09-17-0732) already covers the weekend-thin-book angle.
5. Expiry: prior cme_expiry_drift (frequency-starved) and deribit_gamma_fade (source contradicted) already tried.
