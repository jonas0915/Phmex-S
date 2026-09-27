# informed_flow lens -- exploratory notes (run 2026-09-27-0300) -- EXPLORATORY, not evidence

Outcome: zero theses returned.

Web: 8 WebSearch queries, 9 WebFetch attempts (4 readable: arxiv 2608.21888, arxiv 2607.09426, ideas.repec JEDC 2024 Guo et al abstract, CERGE-EI WP730 PDF via local text extract; 403/redirect: sciencedirect S1386418126000029, SSRN 5020002, SSRN 6938742, sciencedirect S0378426625000317, springer 10.1007/s10690-026-09589-z; EFMA PDF cert error).

Findings per source (read on page):
- arxiv.org/html/2608.21888v1: 15m reversal in 183 Binance spot pairs, peak gross edge ~1.3 bps, "not one of the 183 crypto pairs clears even the 5 bp maker band"; 81% of sign reversal idiosyncratic; gone by 4h. -> fee-trapped.
- arxiv.org/html/2607.09426v2: quarter-hour opening order imbalance (Binance USDT-M, signed trades) predicts 4-12h returns, 5-17 bps; sign-weighted realized target ~0.5 bps. -> needs signed flow we cannot load via load_data; magnitude fee-trapped.
- ideas.repec.org JEDC v163 2024 (Guo, Sang, Tu, Wang): cross-crypto lagged-return predictability, long-short portfolio -> the BTC/large-cap->alt lag family already dead here (rows 106, 112) and XS baskets are out (row 5, CONSTRAINTS).
- CERGE-EI WP730 (Bianchi, Babiak, Dickerson, 2022): daily XS reversal concentrated in low-volume pairs (1.22%/day low vs 0.54%/day high, text lines ~470-472). -> cross-sectional, 2017-2022 sample, pre-dates the post-2022 MR death (row 76).

Probe: probe_idio_volume.py / probe_idio_volume.out.txt (long_1h train only, 2025-06-27 -> 2026-04-23). Tested whether idiosyncratic (alt minus BTC) 24h moves continue on high relative volume (informed, Llorente et al.) and revert on low volume (uninformed). Result: no volume separation -- high-volume idio moves also revert at 48h; low-volume cells n=5-71. The only visible pattern is unconditional 48h reversal of big idio moves, which is a relabel of dead rows 2 and 76 with no informed-flow mechanism. Not proposed.

Why no thesis: every externally sourced informed-flow mechanism either (a) needs signed trade flow / cross-venue / spot data not loadable through load_data, (b) is fee-trapped (<20 bps), (c) is the BTC->alt propagation family already killed (rows 106, 112; plus prior desk theses informed_flow_btc_lead_alt / btc_alt_lag), or (d) is cross-sectional.
