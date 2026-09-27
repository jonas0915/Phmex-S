# dealer_inventory lens — run 2026-09-27-0300 — EXPLORATORY NOTES (not evidence)

Result: 0 theses submitted.

## Web sourcing (6 WebSearch calls; 7 WebFetch attempts, 4 returned content)
Opened:
- https://arxiv.org/html/2608.21888v1 — Binance 15m, 2025-01-01..2026-02-11, 183 pairs: reversal after aggressive taker flow; gross edge peaks near 1.3 bp/trade vs 5 bp round trip; signal "gone by four hours". Implies the inventory-reversal premium sits far below this desk's 100-300 bps targets. Fee-trapped.
- https://www.cerge-ei.cz/pdf/wp/Wp730.pdf (Bianchi, Babiak, Dickerson, CERGE-EI WP 730, June 2022) — low-volume-conditioned reversal, EW daily 1.26% (p 0.001) vs 0.54% high-volume; sample 2017-03..2022-03, cross-sectional. It is pre-2022 and cross-sectional, so it runs into DEAD_LIST rows 5 and 76.
- https://www.theblock.co/post/302705/... (Kaiko) — weekend share of BTC volume 28% (2019) to 16% (2024); market makers "less inclined to provide liquidity in a low-volume environment".
- https://finance.yahoo.com/markets/crypto/articles/weekend-chain-prices-monday-don-183331035.html — Binance Research: weekend on-chain (tokenized) prices price in a median 92% of Monday's gap (through 2026-07-28), and accuracy rises with move size (1-3% moves: 97%). This is contrary evidence: weekend moves are informative, not transient impact.
Failed: sciencedirect S0378426625000317 (403), research.kaiko.com (redirect to app login), tradingview weekend-fade script (404).

## Probes (long_1h, era=train only; no mr_edge data)
- probe_weekend_and_lowvol.py / .out.txt: A1 pooled weekend |move|>300 bps Monday fade n=320, mean +54.29 bps; A2 low-vol n=140 +106.13; B1 volume-conditioned 24h-move fade, all n=754 mean -18.95 bps; vr<1 -37.02.
- probe_weekend_by_week.py / .out.txt: per-weekend, 19 of 41 weekends have a positive mean fade, and the median weekend mean is -96.8 bps. The pooled mean is carried by a few clustered weekends; at the event level it is a coin flip.
- probe_weekend_lowvol_by_week.py / .out.txt: low-vol subset 15/29 weekends positive, median 9.0; vr<0.6 8/15, median 0.5.

## Why no thesis
1. Weekend-inventory Monday fade: at the event level (the unit a concurrency-capped slot trades) the probe is a coin flip. External evidence (Binance Research, above) says weekend prices are informative. Economically it is the same bet as DEAD_LIST row 7 (CME-gap fill, found backwards). This would be a relabel with no supporting source.
2. Volume-conditioned (Grossman-Miller / Campbell-Grossman-Wang) reversal: the only numeric source is pre-2022 and cross-sectional (rows 5, 76). The 2026 source shows the effect is 1.3 bp and dies by 4h. The train probe B1 is negative.
3. Basis mean reversion: this data has no premium-index series, and funding as a proxy is covered by the owner's funding-hunt ban (rows 4, 20, 83). Deribit-expiry dealer unwind was already covered by prior-run theses dealer_inventory_expiry_unwind / dealer_inventory_gamma_flush and vol_structure rows 104-105.
