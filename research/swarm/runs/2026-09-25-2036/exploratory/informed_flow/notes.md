# informed_flow lens — run 2026-09-25-2036 — EXPLORATORY NOTES (not evidence)

Outcome: 0 theses. No data probes were run (no load_data calls, no holdout, no mr_edge reads).

Web work: 11 WebSearch calls, 7 WebFetch attempts. 2 fetches returned readable content; 1 more was a PDF extracted locally. Budget was NOT exhausted.
- OK   https://arxiv.org/html/2607.09426v2 (Quarter-Hour Effect, Binance USDT perps BTC/ETH/XRP/SOL/DOGE/ADA, 2021-01-01..2024-10-31):
       order imbalance in the first 10 seconds after a quarter-hour boundary predicts returns 4-12h ahead, but the paper says
       "E[sign(Y_hat)Y] averages about 0.5 bp per boundary ... one twentieth of a round trip", and that order flow cannot be
       proxied from OHLCV (it needs aggressor-flagged trades). This is fee-trapped against c=11.5 bps and cannot be screened. Rejected.
- OK   https://www.cerge-ei.cz/pdf/wp/Wp730.pdf (Bianchi/Babiak/Dickerson, 2017-03..2022-03, daily): the reversal premium is
       concentrated in low-volume pairs, 0.65%/day vs -0.19% for high-volume pairs (value-weighted). This is a pre-2024 daily
       cross-sectional reversal. It is close to DEAD rows 2/5/76 (cross-sectional, multi-day MR) and needs a basket. Rejected.
- 403  sciencedirect S0275531925004192 (Bitcoin wild moves, VPIN): the search snippet says VPIN predicts jump SIZE, not
       direction, so there is no directional perp trade. Not cited, because the page was not opened.
- 403  sciencedirect S0378426625000317, peerj cs-3810; Springer s10690-026-09589-z needs a login redirect. Not cited.
- EFMA Order-Flow paper PDF: TLS certificate error. Not cited.

Why the lens is dry for this desk:
1. Cross-venue (Binance/Bybit/Coinbase -> Phemex) and spot->perp lead-lag both need non-Phemex or spot data. Neither
   screenable dataset (mr_edge, long_1h) has it. The only in-dataset proxy for spot->perp is funding, and the funding
   hunt is banned (STANDARDS #14; rows 83, 88).
2. Large-cap -> alt propagation at hourly+ horizons is already dead on this account: row 106 (cross_asset_btc_shock_lag, CI
   fully negative) and row 112 (informed_flow_btc_alt_cascade_v2, paper kill). Row 107 covers ETH/BTC. In the 2026-09-20-0300
   gate_rejections.json, literature_btc_alt_drift was rejected as a duplicate of the BTC->alt lag. Search snippets put
   BTC->alt transmission lead times at seconds (PeerJ TAM, "16 to 118 seconds" in a search snippet; the page itself was
   403, so this is not cited as evidence). That is consistent with the lag being arbitraged well below the bot's 5-min
   poller, so any hourly re-attempt would be a relabel.
3. Aggressor-side order-flow imbalance (the only 2024-2026 evidence of informed flow predicting returns) needs trade-level
   data. The bot's L2/tape logs are exploratory-only and not loadable via load_data. A BVC proxy from OHLCV is unsupported:
   a search snippet reported near-random classification accuracy (Polymarket context, not opened).
4. The signal function does not receive the symbol, so a per-alt residual-vs-BTC idea can only use a fixed reference. The
   idiosyncratic-flow continuation idea found no fetched source with a number, so it was not proposed.
