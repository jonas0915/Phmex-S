# cross_asset lens notes (run 2026-10-04-0645) — EXPLORATORY, not evidence. Result: 0 theses.

Web log: 10 WebSearch calls (none refused); 4 WebFetch attempts:
- https://arxiv.org/pdf/2606.00071 — opened, PDF text not extractable by the fetcher (only cite key guo2024cross visible). Not cited.
- https://www.mdpi.com/1911-8074/19/9/692 (JRFM 2026 19(9) 692, 12h-session reversal, Kraken 2016-2025) — HTTP 403. Not cited; claims seen only in search snippets.
- https://arxiv.org/abs/2607.09426 (Kim & Hansen, Quarter-Hour Effect) — opened; crypto-only, quarter-hour order-imbalance, no cross-asset content, sub-hour trigger. Not used.
- https://ideas.repec.org/a/bla/finrev/v60y2025i2p453-479.html (Leong & Kwok 2025, Financial Review) — opened; abstract reports spillovers FROM Bitcoin TO equities/defensive assets (crypto leads), no lag numbers. Direction is not tradeable on our perps.

Why no thesis:
1. Neither dataset (mr_edge, long_1h) carries SPX/NDX/DXY/rates series, so equity/rates -> crypto spillover cannot be signalled directly.
2. Every crypto-only proxy for this lens found relabels a dead row: BTC->alt lag/shock (rows 106, 112; Guo et al. 2024 cross-crypto spillover is a long-short XS portfolio -> row 5 + owner XS directive), ETH/BTC regime -> alt beta (row 107), US-session/ETF-window effects (rows 7, 113, weekend ETF catch-up gate-rejected 2026-09-27 on row 7), US-session -> overnight reversal (rows 7, 76; prior probe research/swarm/runs/2026-09-25-2036/exploratory/cross_asset/probe_session_split.out.txt shows corr -0.03..-0.21 on n=212/symbol, mostly inside noise), US-holiday effect (~9-10 events/yr -> fails 26-week time-to-verdict; row 18 seasonality).
3. Search snippets on the ETF-era "power hour" reversal report it as not profitable after costs; Krüger's analysis (finviz/yahoo snippets) found no consistent 10 AM ET drop.
No probes run, no data loaded this run (no train or holdout reads).
