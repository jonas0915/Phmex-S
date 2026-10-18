# session_calendar lens — run 2026-10-18-0300 — EXPLORATORY, zero theses registered

Not evidence. No train or holdout market data was read by this lens. The only probe is a fee_math frequency ceiling (probe_holiday_ttv.py -> probe_holiday_ttv.out.txt) built on an ASSUMED CEILING input (labelled as such per LESSONS 2026-10-04), not a measured frequency.

Web: 9 WebSearch, 4 WebFetch attempts (2 readable; beincrypto.com returned HTTP 403, napier.ac.uk redirected to a holding page). Unopened pages are not cited.

Readable sources and what they report:
- https://parafi.com/signals/bitcoin-biggest-moves-market-hours (TwelveData hourly BTC/USD, 2021-01-11 to 2026-08-24): Asia "owned 51 of the 85 weeks" with a >=10% one-way move; US market hours' share of variance 24% before the Jan 2024 spot-ETF listings, 33% after. The page reports NO direction/return statistics and NO continuation-vs-reversal finding across sessions/days. => a magnitude/attribution finding, not a direction finding; nothing to trade.
- https://iris.unical.it/handle/20.500.11770/385042 (Algieri, Lawuobahsumo, Leccadito, Zahid 2025, doi 10.1016/j.najef.2025.102441): day-of-week, month, quarter, US-holiday and weekend dummies across 8 coins; abstract says only that anomalies exist in mean/variance/skewness/kurtosis. No coefficients, signs or days on the page. => no tradeable number; row 7/18/67 family.

Search-summary-only (pages NOT opened, therefore NOT cited as evidence): a CoinGecko holiday study reported via beincrypto (403 on fetch); Yaya 2024 and Tan & Chia 2024 day-of-week reviews (non-significant / mixed returns effects); Weiss et al. FRL 2026 Deribit expiry reversals (intraday, daily expiries — already dropped in run 2026-09-27-0300 NOTES.txt); Benigno & Rosa NY Fed SR1052 (BTC orthogonal to macro news); Babaoglu & Pfeifer Volmex 2024 (macro days raise vol, not direction).

Candidates considered and why none was registered:
1. US-federal-holiday drift (TradFi closed, crypto open): the only number is from a page I could not open (403), so it cannot be cited (STANDARDS #2). Independently, frequency fails CONSTRAINTS item 3 by construction: probe_holiday_ttv.out.txt with an ASSUMED CEILING of 11 holidays/yr x max_concurrent(sl) admitted names gives time_to_verdict_weeks(n=50) = 59.09 (sl 100), 78.79 (sl 150), 118.18 (sl 200), 236.36 (sl 300), all > 26. Also near rows 7/18 (seasonality).
2. Session attribution (Asia vs US hours, Parafi): variance shares only, no direction; any session-to-session continuation/reversal is intraday (rows 7/67, 113 brrny window continuation) and outside this lens's >=8h scope.
3. Day-of-week / Monday / weekend: 2024-2025 literature is mixed or non-significant on returns (Algieri 2025 gives no numbers on the page); weekend-move->Monday continuation already rejected as row 7 relabel (runs/2026-09-27-0300/gate_rejections.json, cross_asset_weekend_etf_catchup); weekend thin-book fade already proposed 2026-09-17-0732. Rows 7, 18, 67.
4. Weekend leverage build-up -> Monday liquidation: only anecdotes (Fundstrat 2023 Sunday cascade, The Block 2021 Monday); no systematic source, and the bet is liquidation-cascade continuation/reversion (rows 6, 110). Also OI data is unavailable (row 10).
5. Macro-release multi-day drift: sources describe same-window/1h reactions or volatility, not multi-day direction; rows 84 and prior session_calendar_fomc_drift_short.
6. Monthly/quarterly expiry, turn-of-month, month-end rebalancing: frequency-starved (runs/2026-10-04-0645/exploratory/session_calendar/probe_frequency_ceiling.out.txt; runs/2026-09-20-0300 cme_expiry_drift) — not re-proposed.

Structural finding (unchanged from runs 2026-09-25, 09-27, 10-04): under STANDARDS #17 max_concurrent (4/3/2/1 at sl 100/150/200/300 per fee_math.max_concurrent), calendar events rarer than weekly cannot meet item 3, and weekly/daily calendar triggers collapse into the already-dead unconditional weekend/day-of-week/time-of-day families (rows 7, 18, 67, 76). This lens has now returned zero theses in four consecutive runs; recommend the orchestrator retire or merge it.
