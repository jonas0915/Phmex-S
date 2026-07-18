# ST2.0 Execution Optimization — Night 22
**Date:** 2026-07-18 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 21 Nights

Prior nights 1–21 covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps (N13), post-settlement spread peak / cycle_phase (N14/N15), vol_norm_tick (N15), fill asymmetry inversion / tape direction noise / VPIN sustained-flow threshold (N16), large-taker arrival as cancel trigger / Albers v2 cancel comparison (N17), altcoin maker p>0.05 / LOB composite state calm/mixed/stressed (N18), regime misclassification (Avery & Ward) / OFI slope direction (N19), latent regime trajectory / DeLise negative-drift proof (N20), literature exhaustion confirmed / zero new applicable papers (N21).

**Status entering Night 22:** Night 20 recommended halting research; Night 21 confirmed the literature for small passive directional maker execution on crypto perp altcoin futures is conclusively exhausted for accessible sources. Night 22 was instructed to proceed; results below confirm that conclusion.

Four new search angles targeted tonight (all untried in N1–N21):
- Intrabar / within-candle signal timing effects on passive fill quality
- Signal staleness and quote aging for resting maker orders in crypto perps
- Small-cap altcoin CEX perp maker fill quality (as distinct from BTC-focused literature)
- BTC/ETH lead-lag conditioning for altcoin passive maker entry timing

Four searches run; three primary sources fetched. **Zero new applicable findings.** The cumulative pattern — same 5–6 papers returning on every search angle, with only equity/DEX/off-topic papers available beyond those — persists.

---

## Sources Surveyed Tonight

| Source | Why Checked | Verdict |
|---|---|---|
| hftadvisory.substack.com — "Six Market Microstructure Signals That Fire Before the Price Print" | Practitioner piece on pre-entry microstructure signals; possible new angle on execution timing | **NOT USABLE.** Fetched. Crypto claims are explicitly labeled practitioner observations without empirical data. Direct quote from author: "If you have run this stack in production across multiple venue types and found stable parameters, that calibration is the part of this architecture that is hardest to document from outside a specific venue's data." No quantified claims verifiable. |
| MDPI 1911-8074/18/3/124 — "Order Book Liquidity on Crypto Exchanges" | Order book variation and liquidity-dependent trading costs in crypto | **BLOCKED (HTTP 403).** Full text not readable. Abstract snippet (search result): "order book variation can be explained by liquidity measures indicating that trades are timed" — no body extractable; not verifiable. |
| sotofranco.dev — "BTC/ETH Lead-Lag: Resolution-Dependent Direction Reversal on Binance Spot" | BTC-conditioned altcoin passive entry timing; cross-asset lead-lag for execution | **FETCHED, NOT APPLICABLE.** See Finding A below — new empirical paper with data, but the key crossover (ETH leads → BTC leads) occurs at 15–20 milliseconds. ST2.0 latency is ~hundreds of milliseconds. Structurally inaccessible. |
| arXiv: altcoin perp maker fill quality (2025–2026 papers searched) | Direct maker fill quality for small-cap altcoin perps | **No new papers found.** Search returned arXiv:2602.00776 (Casas et al. — already covered N18), DEX-only papers, and off-topic results. |

---

## Finding A — BTC/ETH Lead-Lag: New Data, Wrong Latency Tier

- **Source:** Alejandro Soto Franco. "BTC/ETH Lead-Lag: Resolution-Dependent Direction Reversal on Binance Spot." Blog post with primary empirical research, January 2025 and full-year 2025 Binance spot data. 522,719+ non-overlapping 60-second windows.
- **URL:** https://www.sotofranco.dev/blog/posts/btc-eth-lead-lag
- **Dataset:** Binance spot (not perp), BTC/USDT and ETH/USDT only, 2025.
- **Access:** Fully readable. Primary data analysis, not peer-reviewed.

**Verified quotes (fetched directly):**

> "At sub-20-millisecond timescales, ETH leads BTC on Binance spot. Above roughly 15–20 ms, the direction inverts and BTC leads ETH."

> "Cohen's h = −0.139 (small-to-medium effect)" [January 2025, 1 ms resolution, ETH-leads fraction = 52.7%]

> "ETH's lower per-trade notional value enables faster order-book clearing, making it the preferred signalling leg for cross-asset arbitrageurs."

**Why this is NEW:** No prior night addressed BTC-ETH-altcoin lead-lag timing as a conditional entry gate. The paper provides fresh 2025 Binance spot data with clean quantification of the crossover point.

**Why it is NOT APPLICABLE to ST2.0:**

The crossover from ETH-leads to BTC-leads occurs at **15–20 milliseconds**. ST2.0 is a Python bot with round-trip API latency measured in hundreds of milliseconds to seconds. It operates deep in the BTC-leads regime. The finding shows cross-asset arbitrage at millisecond resolution drives price leadership — a regime requiring collocated C++ bots with direct market access. No actionable conditional entry tweak is possible for ST2.0 at its latency tier.

The finding also applies to BTC/ETH spot, not to altcoin perps (AVAX, INJ, ARB, ENA). Altcoin lead-lag from BTC would involve additional lag and further noise. The paper explicitly notes: "No Direct Perpetuals Analysis."

**Honest disposition:** This is an interesting empirical data point that reinforces the synthesis conclusion — "ST2.0 has no latency edge" — without yielding a new tweak. Noted for completeness; not added to the forward-test queue.

---

## New Forward-Testable Tweaks

**None.** No applicable primary sources found tonight. The forward-test queue remains at 22 tweaks (all queued from N1–N21, none deployed).

---

## Honest Caveats

1. **The research series is conclusively exhausted.** Night 22 tried four new search angles (intrabar timing, signal staleness, altcoin-specific fill quality, BTC lead-lag conditioning) and produced zero applicable findings. All searches return the same 5–6 papers that have circulated since Night 14 (Albers 2502.18625, Casas 2602.00776, DeLise 2407.16527, Avery & Ward 2607.01550, 1610.00261) plus off-topic DEX/equity/simulation papers.

2. **The SSRN 6344338 blocker persists.** Rajendran & Singaravelu's gradient-boosting adverse selection predictor for crypto HFT remains HTTP 403 for the **22nd consecutive night**. This was the paper most directly applicable to a pre-entry adverse selection classifier. It is not readable via any accessible route.

3. **22 tweaks queued, 0 deployed, across 22 nights.** The binding constraint is not knowledge — it is empirical data from live shadow-logging. Tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines of logging and have been queued for 3–5 weeks. Until those produce tagged fills, additional research nights produce no marginal value.

4. **The three persistent gaps remain unresolved and are likely unresolvable via literature.** After 22 nights of targeted search: no primary source addresses optimal cancel TTL, LOB depth replenishment speed, or optimal placement depth inside spread specifically for crypto perp altcoin markets. These appear to be genuine gaps in accessible academic literature for this specific problem shape.

5. **Night 22 recommendation:** This research series should not continue. The literature is exhausted. All 7 priority tweaks (4, 6, 9, 10, 11, 12, 14) can be implemented in one coding session. Implement them, collect 30+ tagged fills per diagnostic variable, then return to research if patterns in the data suggest new questions.

---

## Forward-Test Queue (Cumulative — All Nights, Unchanged from N21)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | N4 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (never repost) | N3/N6 | Queued |
| 3 | Shadow-gate VPIN computation | N3 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | N6 | **PRIORITY (2–5 lines)** |
| 5 | Log `fg_regime` + `fg_extremity` flag | N7/N9 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | N10 | **PRIORITY (2–5 lines)** |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | N10 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | N6 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | N6 | **PRIORITY (2–5 lines)** |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | N7 | **PRIORITY (2–5 lines)** |
| 11 | Log `vol_norm_tick` per symbol at signal time | N11 | **PRIORITY — diagnostic** |
| 12 | Log `funding_rate_annual_pct` at signal time | N12 | **PRIORITY (2–5 lines)** |
| 13 | Log `q_fill_score` composite (Albers formula) | N13 | Queued |
| 14 | Log `spread_at_signal_bps` | N14 | **PRIORITY (2–5 lines)** |
| 15 | Log `cycle_phase` = `utc_hour % 8` at signal time | N15 | Queued |
| 16 | Sustained buy-ratio imbalance gate (shadow log first) | N16 | Queued |
| 17 | Buy_ratio noise audit (Phemex WS aggressor-side flag check) | N16 | Queued (diagnostic) |
| 18 | Signal magnitude shadow-log (ensemble_confidence vs post-fill return) | N16 | Queued (diagnostic) |
| 19 | Log `large_taker_prefill` flag (single trade > Y% of ask queue while resting) | N17 | Queued (shadow only) |
| 20 | Log `lob_state` composite (spread + inverted depth + imbalance → calm/mixed/stressed) | N18 | Queued (requires Tweaks 6 + 14 first) |
| 21 | Log `ofi_slope_direction` at signal time (buy_ratio now vs 2 min prior → declining/flat/rising) | N19 | Queued (shadow only; ~3 lines) |
| 22 | Log `latent_traj_score` (ask-depth declining + spread widening + OFI momentum in prior 60s, 0–3) | N20 | Queued (shadow only; ~4 lines) |

---

## Research Series Status

| Category | Status |
|---|---|
| Pre-entry gates | 10 tweaks (N1, N2, N3, N7, N11, N15, N16, N17, N21, N22) |
| At-entry placement | 4 tweaks (N4, N5, N8, N12) |
| Post-entry management / cancel | 4 tweaks (N6, N8, N9, N19) |
| Diagnostics only | 4 tweaks (N13, N14, N18, N20) |
| Confirmed unresolvable via literature | Optimal TTL, LOB replenishment speed, placement depth inside spread |
| Blocked SSRN | 2 papers (6693260 + 6344338 — 22 consecutive nights) |

**Night 22 summary:** Zero new applicable papers across 4 search angles and 3 fetches. One genuinely new empirical finding (BTC-ETH spot lead-lag reversal at 15–20 ms crossover, sotofranco.dev, 2025 Binance data) is confirmed new but not applicable — operates at millisecond latency, ST2.0 is at second-scale, spot only, BTC/ETH only. The literature for this problem is conclusively exhausted. 22 tweaks queued, 0 deployed. **This research series is closed. Next step: implement priority tweaks 4, 6, 9, 10, 11, 12, 14 (all 2–5 lines each) and collect 30+ tagged fills before returning to research.**
