# session_calendar lens — run 2026-10-04-0645 — EXPLORATORY, zero theses registered

Web: 8 searches, 6 fetch attempts (5 readable; macrohive.com turn-of-month page returned HTTP 403, not cited).

Readable sources and what they report:
- https://www.blockscholes.com/institutional-research/is-bitcoin-showing-greater-sensitivity-to-us-cpi-releases-again (2026-09-14): BTC CPI-surprise 1h R2 nearly 80% on a 12-release window, but the sensitivity is "specific to the immediate, one-hour horizon; and not the longer 4-to-24-hour periods"; NFP sensitivity "faded to near zero in 2026". => no multi-day macro-day drift; the 1h piece is row 84 (and intraday).
- https://quantpedia.com/the-seasonality-of-bitcoin/ : hour-of-day (21:00-23:00 UTC) and day-of-week results; no turn-of-month analysis. Intraday => rows 7/67.
- https://ideas.repec.org/a/ahs/journl/v9y2024i1p43-60.html (Ergun 2024, 2019-2023): turn-of-month significant only for Stacks; Bitcoin shows no TOM anomaly.
- https://valuelytica.substack.com/p/end-of-month-effect-in-bitcoin (2025-12-27): BTCE.DE 2021-2024, last five trading days of the month carry much of the return; EOM Sharpe 1.08 vs B&H 0.55.
- https://www.fxstreet.com/cryptocurrencies/news/bitcoin-weekly-forecast-quarter-end-rebalancing-might-fuel-btc-next-bullish-move-202607031130 (2026-07-03, citing K33 Research): 9 of 18 months showed month-end-window ETF flows diverging from the month trend; months where BTC underperformed the S&P 500 were followed by stronger month-end inflows; K33: "not a persistent driver".
- https://river.com/content/dca-research-2026 (2026-01-06, 2023-01 to 2025-10): weekly best-vs-worst recurring-buy time advantage 0.77%; daily 0.08%; called "real yet modest".

Candidate considered and dropped: month-end rebalancing (multi-asset holders with fixed BTC weights forced to buy after a down month / sell after an up month, 3 days pre to 3 days post month-end).
- Counterparty is genuine (mandate-bound rebalancer), but frequency is one event per month. probe_frequency_ceiling.out.txt: admitted-trade ceiling under fee_math.max_concurrent gives time_to_verdict_weeks 54.17 (sl 100), 72.22 (sl 150), 108.33 (sl 200) — all > 26 => fails CONSTRAINTS viability item 3 by construction (same reason gate rejected session_calendar_cme_expiry_drift, runs/2026-09-20-0300/gate_rejections.json).
- long_1h train holds only 9 month-end events per symbol (probe_month_end_rebalance.out.txt), so n>=30 independent observations is unreachable; trades within one event are one correlated cluster (STANDARDS #17).
- K33 itself says the effect is non-persistent (9/18 months); also near DEAD_LIST row 18 (seasonality, ETF-flow timing).
Weekly DCA timing (River): 0.77% is a best-minus-worst in-sample pick over all weekday/hour pairs (selection-inflated) and the Fri->Wed hold spans the weekend => relabel of row 7.
