# ST2.0 Execution Optimization — Night 21
**Date:** 2026-07-17 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 20 Nights

Prior nights 1–20 covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps (N13), post-settlement spread peak / cycle_phase (N14/N15), vol_norm_tick (N15), fill asymmetry inversion / tape direction noise / VPIN sustained-flow threshold (N16), large-taker arrival as cancel trigger / Albers v2 cancel comparison (N17), altcoin maker p>0.05 / LOB composite state calm/mixed/stressed (N18), regime misclassification (Avery & Ward) / OFI slope direction (N19), latent regime trajectory / DeLise negative-drift proof (N20).

**Three persistent unresolved gaps** carried from prior nights (7–10 nights of targeted search each, now conclusively unresolved):
- Optimal cancel horizon (TTL): no primary-source calibration for crypto perps
- LOB depth replenishment speed after market orders on crypto perps: no applicable primary source
- Optimal passive sell placement depth inside spread: no applicable primary source

Tonight's searches targeted four angles across these gaps plus one new angle (stale-quote / pick-off risk mitigation). Four searches run; six papers fetched.

**Zero new applicable papers.** All six fetched papers are either simulation-only, traditional equity markets, or DEX-specific. The searches also returned several papers already covered in prior nights (2602.00776 Casas et al.; 2502.18625 Albers et al.; 1610.00261 Latency/adverse selection).

---

## Papers Surveyed Tonight

| Paper | Why Checked | Verdict |
|---|---|---|
| arXiv:2607.04280 — "Order Splitting and Liquidity Replenishment Are Jointly Necessary for the Square-Root Law of Market Impact" (July 2026) | LOB replenishment speed (persistent gap) | **NOT APPLICABLE.** Simulated data calibrated against Tokyo Stock Exchange equity data. No crypto content. No time-to-recovery measurements. Identifies order splitting + HFT quoting as mechanisms for SRL, not recovery speed. |
| arXiv:2605.24242 — "Explicit Signal-Adaptive Sequential Optimal Execution Quotes" (June 2025) | Signal-adaptive quote placement — potentially new angle | **NOT APPLICABLE.** Pure theory paper. No dataset. Framework addresses active sequential execution, not passive resting maker orders. No crypto content. |
| arXiv:2510.27334 — "When AI Trading Agents Compete: Adverse Selection of Meta-Orders by RL-Based Market Making" (October 2025) | RL-based adverse selection of passive makers — new angle | **NOT APPLICABLE.** Simulated Hawkes LOB environment. No real-world data. No crypto content. Key claim: "Increased profits for the market making RL agent do not necessarily cause significantly increased slippages for the MFT agent" — simulation result, does not transfer. |
| arXiv:2506.05764 — "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books: Better Inputs Matter More Than Stacking Another Hidden Layer" (June 2025) | Crypto LOB dynamics — potential placement or fill quality findings | **NOT APPLICABLE TO EXECUTION.** Bybit BTC/USDT spot (not perp). About price *forecasting* model architecture. Key finding: "simpler models can match and even exceed the performance of more complex networks." No passive maker fill quality, no adverse selection, no placement depth content. |
| arXiv:2507.22712 — "Order Book Filtration and Directional Signal Extraction at High Frequency" (July 2026) | Order flow signal extraction — potential OBI-adverse-selection link | **NOT APPLICABLE.** National Stock Exchange of India, BankNifty index futures. Not crypto. Key finding: "filtration of the aggregate order flow produces only modest changes relative to the unfiltered benchmark" — equity futures only. |
| arXiv:2605.06405 — "Funding-Aware Optimal Market Making for Perpetual DEXs" (May 2026) | Funding rate + market making for perpetual contracts — potential CEX transfer | **NOT APPLICABLE.** Hyperliquid DEX only. Framework: bid-ask spread optimization for bidirectional inventory-managed market making, not directional passive maker. Authors note "heavy-tailed innovations" vs Gaussian OU assumption — model gap acknowledged. No CEX applicability discussed. |

---

## New Forward-Testable Tweaks

**None.** No applicable primary sources found tonight.

---

## Honest Caveats

1. **The three persistent literature gaps are now conclusively unresolved.** After 7–10 targeted searches per gap across 21 nights, no primary source addresses optimal cancel TTL, LOB replenishment speed, or placement depth inside spread for crypto perpetual futures. These gaps appear to reflect genuine limits of accessible academic literature on this specific problem.

2. **The search is returning the same 5–6 papers on every new search angle.** Albers 2502.18625, Casas 2602.00776, and 1610.00261 now appear in virtually every search. This is a reliable signal that the relevant literature is exhausted.

3. **Six new papers fetched tonight — zero applicable.** All six are simulation-only, equity markets (Tokyo, India), DEX-specific (Hyperliquid), or spot price forecasting. The structural constraint — no academic coverage of small passive directional maker execution on crypto perpetual futures for altcoin pairs — persists.

4. **Night 20's recommendation stands and is reinforced by Night 21.** From N20: "Research has definitively outpaced implementation. 22 tweaks queued, 0 deployed. Halt research series; implement Tweaks 4, 6, 9, 10, 11, 12, 14 first." Night 21 confirms: the literature for this specific problem is exhausted. No further research nights are warranted until shadow-log data from implemented tweaks is available.

5. **SSRN 6344338 (Rajendran & Singaravelu, gradient boosting adverse selection predictor for crypto HFT) remains permanently inaccessible.** Night 21 marks 21 consecutive nights of HTTP 403. This paper has been permanently inaccessible throughout the research series.

---

## Forward-Test Queue (Cumulative — All Nights, Unchanged)

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
| Blocked SSRN | 2 papers (6693260 + 6344338 — 21 consecutive nights) |

**Night 21 summary:** Zero new applicable papers. Six papers fetched; all inapplicable (Tokyo equity simulation, pure theory, RL simulation, spot price forecasting, Indian equity futures, Hyperliquid DEX). The literature for this specific problem — small passive directional maker execution on crypto perpetual altcoin futures — is conclusively exhausted for accessible sources. 22 tweaks queued, 0 deployed across 21 nights. **This research series should not continue until shadow-log data from implemented priority tweaks (4, 6, 9, 10, 11, 12, 14) is available to calibrate against.**
