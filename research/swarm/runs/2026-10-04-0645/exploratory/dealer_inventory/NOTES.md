# dealer_inventory lens — run 2026-10-04-0645 — EXPLORATORY NOTES (not evidence)

Result: 0 theses submitted.

## Web sourcing log (8 WebSearch calls; 6 WebFetch attempts, 3 returned readable content)
Searches: (1) perp MM inventory end-of-day unwind; (2) perp basis premium spike mean reversion; (3) IBIT options dealer gamma US session;
(4) MM weekend liquidity withdrawal Kaiko; (5) BTC ETF AP hedging 4pm NAV fix; (6) arXiv crypto intraday reversal inventory risk;
(7) Kim & Hansen quarter-hour effect; (8) MMs flatten Friday / CME open weekend.
Fetches:
- OPENED https://cryptoslate.com/the-invisible-opening-bell-inside-cryptos-endless-trading-day/ — reports Kim & Hansen (UNC, Aug 2026), Binance futures 6 contracts 2021-01-01..2024-10-31: first 10s of each quarter-hour has 26% more trades, 32% more dollar volume, 26% larger absolute returns; direction 56.6% correct, 0.51 bps gross per trade before fees; opening order imbalance correlated with returns over the next 4-12 hours. Mechanism is scheduled algorithmic flow (informed_flow lens), needs signed trade data the long_1h/mr_edge OHLCV caches lack; 0.51 bps is fee-trapped vs c=11.5.
- OPENED https://flashalpha.com/articles/ibit-options-gamma-exposure-bitcoin-etf-dealer-positioning — a single snapshot: IBIT net GEX +$3.98M, gamma flip 35.90 vs spot 35.93 (+0.06%), call wall 36.5 strike +$9.74M; CME BTC=F -$0.85M net gamma. No time series, no return effect measured; no historical GEX data is available to the bot, so a gamma-sign signal is not computable.
- OPENED https://blog.bitfinex.com/bitfinex-alpha/etf-timing-gap-btc-range-bound/ — qualitative AP mechanics only (AP shorts ETF at premium, hedges with futures, delays spot buy); only hypothetical numbers ($100 NAV, $101 premium). No measurable effect.
- UNREADABLE https://ftp.aeaweb.org/conference/2026/program/paper/ByyFEfr4 (PDF binary, fetch tool could not parse) — not cited.
- UNREADABLE https://arxiv.org/pdf/2607.09426 (PDF binary) — not cited beyond the cryptoslate summary above.
- 403 https://www.preprints.org/manuscript/202604.0256/v1 — not cited.
Search-snippet-only (not opened, not cited as evidence): CME crypto futures 24/7 from 2026-05-29 (multiple news results) -> any CME-weekend-gap dealer thesis is structurally ended after the long_1h train era (and is DEAD_LIST row 7 anyway).

## Probes (long_1h, era=train only, 18 symbols ex-GIGGLE; no mr_edge data, no holdout)
- probe_session_reversal.py / .out.txt: weekday US-cash-session (14:00->21:00 UTC) return faded over 48h looked strong POOLED (k=2: n=373 obs, gross fade mean 157.70 bps, naive ci [88.96, 228.37]) while Asia/EU sessions CONTINUED. Pooled obs are 18 cross-correlated symbols per day with overlapping 48h windows, so the naive CI is invalid.
- probe_session_reversal_by_day.py / .out.txt: collapsed to one observation per day the US fade is a coin flip: k=1.5 days=110, day_mean 85.9, ci95_day [-45.1, 212.0], day_hit 0.509; k=2.0 day_hit 0.487, ci [-58.3, 214.0]. Month means alternate sign (k=1.5: 2025-10 +513.4, 2025-11 -293.1, 2026-01 -115.3, 2026-02 +362.2); BTC alone negative (k=1.5 n=41 mean -54.3). Long-side (down-session) carries it: 200.1 vs short-side 22.0 -> a few crash-rebound days, i.e. the multi-day MR of DEAD_LIST row 76 and the time-of-day null of rows 7/67.

## Why no thesis
1. US-session dealer-intermediated move fade: event-level coin flip (above); relabel of rows 76 / 7 / 67 with no source measuring a crypto session-reversal magnitude.
2. Basis (premium) mean reversion: no premium-index series in either dataset; funding as proxy is barred (STANDARDS #14; rows 4, 20, 83).
3. Options-dealer gamma (IBIT/Deribit): no historical GEX/OI series; expiry-unwind/flush already spent (prior-run dealer_inventory_expiry_unwind, dealer_inventory_gamma_flush; rows 104, 105).
4. Weekend inventory: already probed to a coin flip in run 2026-09-27-0300 (exploratory/dealer_inventory/NOTES.md) and CME 24/7 since 2026-05-29 removes the Sunday re-hedge.
5. Quarter-hour algorithmic flow: wrong lens, needs signed tape, gross 0.51 bps is fee-trapped.
