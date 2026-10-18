# informed_flow lens -- run 2026-10-18-0300 -- EXPLORATORY NOTES (not evidence)

Outcome: 0 theses. No data probes were run (no load_data calls, no holdout, no mr_edge reads, no fetch_ohlcv_ccxt).

## Web log (7 WebSearch calls, 3 WebFetch attempts; budget NOT exhausted)
Searches:
1. arXiv 2025 informed trading crypto perpetual futures volume price impact hourly return predictability
2. Bitcoin lead-lag altcoins intraday 2025 minutes hours propagation Binance perpetual
3. crypto intraday momentum volume-weighted signal net of transaction costs 2025 Bitcoin hourly
4. bulk volume classification OHLCV order flow proxy crypto return predictability 2024 2025
5. Kurihara Matsumoto 2026 Asia-Pacific Financial Markets BTC->altcoin lagged price transmission
6. stealth trading / volume-return informed traders crypto continuation hourly 2025
7. Upbit Binance Coinbase price discovery lead perpetual smaller exchanges lag 2025

Fetches (every attempt listed):
1. 403   https://t2r2.star.titech.ac.jp/rrws/file/CTT100941776/ATD100000413/ (Kurihara & Matsumoto 2026, BTC->altcoin lag). Not cited.
2. OK    https://arxiv.org/abs/2506.08718v1 (Plazuelo Pascual et al., "Price Discovery in Cryptocurrency Markets", 2025):
         abstract only -- CEX leads ETH price discovery; BTC futures lead overall, "mixed" in high volatility. No lag lengths, no information-share numbers on the page.
3. OK    https://business.cornell.edu/article/2025/02/perpetual-futures-contracts-and-cryptocurrency (Ruan & Streltsov):
         perps = 93% of crypto derivatives volume; volume/spreads U-shaped within the 8h funding cycle; no hour-by-hour magnitudes on the page.

## Why no thesis (same structural blockers as runs 2026-09-25-2036, 2026-09-27-0300, 2026-10-04-0645 NOTES)
1. Cross-venue (Binance/Coinbase/Upbit -> Phemex) and spot->perp lead-lag need non-Phemex data; neither screenable dataset has it.
2. Large-cap -> alt propagation is the only in-dataset informed-flow channel and is dead: DEAD_LIST rows 106, 112 (and 107). The one new 2026 source on it (Kurihara & Matsumoto, DOI 10.1007/s10690-026-09589-z) was 403 -- and would be a relabel anyway.
3. Funding-cycle informed trading (Cornell piece) is a funding-settlement-hour timing effect: relabel of rows 7/82 and inside the STANDARDS #14 funding-hunt ban; the page gives no magnitudes.
4. Volume-as-informed-flow (Bianchi-Dickerson volume x return) was already probed on long_1h train in run 2026-09-27-0300 (exploratory/informed_flow/probe_idio_volume.out.txt): no volume separation; residual pattern is a row 2/76 relabel. Not re-probed (data-snooping).
5. No fetched 2024-2026 source reported a net-of-cost number for a mechanism computable from Phemex OHLCV at hourly+ horizons.
