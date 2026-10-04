# informed_flow lens -- run 2026-10-04-0645 -- EXPLORATORY NOTES (not evidence)

Outcome: 0 theses. No data probes were run this run (no load_data calls, no holdout, no mr_edge reads, no fetch_ohlcv_ccxt).

## Web log (9 WebSearch calls, 6 WebFetch attempts; budget NOT exhausted)
Searches: abnormal volume/informed trading hourly; Upbit-Binance lead-lag; informed trading before Binance listings;
Bianchi-Dickerson 12h volume; Coinbase premium; arxiv 2025 hourly lead-lag altcoins; low-vs-high-volume reversal/continuation;
abnormal volume 2024-2026; Garfinkel-Hsiao-Hu disagreement.

Fetches (every attempt listed):
1. OK   https://www.cxoadvisory.com/technical-trading/predicting-crypto-asset-returns-with-past-returns-volume/
        Bianchi & Dickerson "Trading Volume in Cryptocurrency Markets" (Aug 2018 draft, SSRN 3239670): sample 2017-01-01..2018-05-10,
        26 assets; abnormal volume = log deviation from trend over rolling 21 intervals; low-volume reversal (RevL) at 12h,
        "gross annualized Sharpe ratios as high as 2.96"; costs not specified (gross).
2. EMPTY https://qmro.qmul.ac.uk/xmlui/handle/123456789/83862?show=full (no content returned). Not cited.
3. 403  https://www.mdpi.com/1911-8074/19/9/692 (BTC->altcoin Granger lag strategy per search snippet). Not cited.
4. OK   https://www.emerald.com/sef/article/38/4/693/343866/Directional-predictability-between-returns-and
        Fousekis & Grigoriadis (2021), daily BTC/ETH/XRP/LTC: "Low levels of trading activity have in general no information content
        about future returns; high levels, however, tend to precede extreme positive returns."
5. PAYWALL https://www.cxoadvisory.com/currency-trading/eth-btc-lead-lag-relationship (results behind paywall). Not cited.
6. OK (PDF, extracted locally with pypdf) https://biz.uiowa.edu/faculty/jgarfinkel/pubs/crypto_divop.pdf
        Garfinkel, Hsiao, Hu, Financial Management 54(3) 2025: sample July 1 2018 - Dec 31 2021; high-minus-low DISAGREE (abnormal
        volume) quintile daily return differential -0.491% (t = -7.21); "the crypto-day observations where margin trading is allowed
        do not exhibit this relation."

## Why no thesis
1. Cross-venue (Binance/Bybit/Coinbase/Upbit -> Phemex) and spot->perp (Coinbase premium) lead-lag need non-Phemex data that
   neither screenable dataset (mr_edge, long_1h) contains. Funding as a spot-perp proxy is banned (STANDARDS #14; rows 83, 88).
2. Large-cap -> alt propagation at hourly+ is already killed: rows 106 (cross_asset_btc_shock_lag, CI fully negative) and
   112 (informed_flow_btc_alt_cascade_v2, paper kill); row 107 (ETH/BTC). The only new 2025-26 lead-lag source (MDPI JRFM 19/9/692)
   returned 403 and is the same BTC->alt family anyway.
3. Volume-as-informed-flow: the abnormal-volume disagreement effect (Garfinkel et al. 2025) vanishes where shorting is available --
   every Phemex perp is shortable, so there is no forced counterparty on this venue. The Bianchi-Dickerson low-volume 12h
   reversal is a 2017-2018 gross-only result (pre-2022; row 76 says multi-day MR died post-2022), and the prior desk probe
   research/swarm/runs/2026-09-27-0300/exploratory/informed_flow/probe_idio_volume.out.txt already found low-relative-volume
   cells too sparse (n=5-71) and no volume separation on long_1h train -- re-probing the same train data with a new cut would
   be data-snooping a relabel of rows 2/76.
4. Listing-announcement informed trading (pre-announcement drift per search snippet, page not opened) needs an event calendar
   that is not loadable through load_data. Not cited.
