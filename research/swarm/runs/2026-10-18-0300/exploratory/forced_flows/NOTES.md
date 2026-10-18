# forced_flows lens notes — run 2026-10-18-0300 (EXPLORATORY; not evidence)

Outcome: ZERO theses registered. No train-data probes were run; no load_data calls were made (so no holdout or cross-dataset exposure).

## Web log
WebSearch calls: 8 (none refused; budget NOT exhausted).
WebFetch attempts (4):
1. https://arxiv.org/abs/2608.21888 — OK. Kitron & Wengrowicz, "Short-horizon mean reversion in cryptocurrency markets" (submitted 22 Aug 2026): 15-minute reversal on 90% of 183 Binance pairs; gross edge peaks near 1.3 bp per trade vs a 5 bp round trip — net negative.
2. https://quantpedia.com/cryptocurrency-market-dynamics-around-bitcoin-futures-expiration-events/ — OK (first 100k chars). Daily BTC around CME/BITO expirations 2017-12-29 to 2024-02-28; no numeric return figures in text (charts only); pattern reversed after BITO launch.
3. https://www.theblock.co/post/372115/whats-next-after-cryptos-fourth-largest-long-liquidation-event-of-2025 — OK. K33 (2025-09-24): BTC returned 0.78% avg (median -1.1%) over 30 days after top-5% annual liquidation events vs typical 5.9%; ~a quarter of spikes coincided with local bottoms.
4. https://www.bitmex.com/blog/2025q1-derivatives-report — HTTP 404, not read, not cited.

## Candidates considered and why each was dropped
- Flow-driven bar reversal (arXiv 2608.21888): 15-min horizon, 1.3 bp gross — far below the 100-300 bps ladder; adjacent to DEAD rows 2, 3, 6.
- Futures/options expiry flows (Quantpedia/Blasco et al.; Deribit expiry news): monthly events, ~10 per long_1h train window on BTC — cannot reach n>=30 / 26-week verdict; no source gives a return number; options-expiry unclamp is DEAD row 105, calendar row 7/84.
- Post-liquidation-spike drift (K33 via The Block): BTC-level, ~top 5% of days, 30-day horizon — too few events and a 30-day hold; liquidation data not in the caches; same family as DEAD rows 6, 110, 76.
- Perp new-listing short (StockSharp 2023 informal blog, BitMEX report 404): listing events are not in either dataset's universe; source gives no return numbers.
- Perp delisting forced closures (Binance Jan 2026 news): event-calendar data not in datasets; news only, outcomes mixed; n far below 30.
- Funding-settlement flows: owner ban on funding hunt (STANDARDS #14); DEAD rows 4, 7, 82, 83.
- Prior runs of this lens (2026-09-27, 2026-10-04 NOTES) already dropped round-number, stop-sweep (row 114), LETF window (rows 109, 113), ADL (row 108), and quarter-hour imbalance candidates.
