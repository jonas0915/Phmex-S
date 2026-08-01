# ST2.0 Execution Optimization — Night 34
**Date:** 2026-08-01 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 33 Nights

N33 closed with: literature declared "substantially saturated" after exhaustive coverage of micro-price, cancel-reprice, VPIN thresholds, post-fill alpha decay, price-reading/skew-sniffers, miss-feedback signal — zero new tweaks, 39 queued.

Tonight searched four angles not previously covered:
1. Fleeting/spoofing order filtration and passive maker fill quality
2. VWAP-to-mid deviation as a pre-trade adverse selection indicator in crypto perp
3. Optimal passive execution with passive market impact (NASDAQ/FX calibration)
4. Cross-asset maker vs taker performance on altcoin perpetual futures (extended coverage)

**Net result tonight: One new verified paper (arXiv:2602.00776) with two forward-testable diagnostic tweaks. MDPI funding-window paper blocked for the 4th consecutive night. Other candidates all used non-crypto or non-perp data.**

---

## Papers Fetched and Evaluated Tonight

### arXiv:2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure"
**Authors:** Bartosz Bieganowski, Robert Ślepaczuk (University of Warsaw, Faculty of Economic Sciences).
**Submitted:** January 31, 2026. arXiv preprint.
**URL:** https://arxiv.org/html/2602.00776v1
**Dataset:** Binance Futures perpetual contracts. Five assets: BTC, LTC, ETC, ENJ, ROSE (selected to span market-cap ranks 1, 20, 40, 60, 100 as of 2022-01-01). 1-second frequency. Date range: 2022-01-01 through 2025-10-12.
**Access:** HTML fetched directly. arXiv preprint (not peer-reviewed at time of fetch).

**Abstract (verbatim):**
> "We document stable cross-asset patterns in cryptocurrency limit-order-book microstructure: the same engineered order book and trade features exhibit remarkably similar predictive importance and SHAP dependence shapes across assets spanning an order of magnitude in market capitalization."

**Verified findings (HTML fetch):**

**Finding 1 — VWAP-to-mid shows microstructure reversion effects:**
> "VWAP-to-mid deviations show asymmetric effects coherent with short-lived pressure and microstructure reversion."

This means: temporary deviations of recent volume-weighted trade prices from the current midprice are mean-reverting in the data. For ST2.0, which signals on buy absorption (buying pressure temporarily drives recent trade prices above the mid), the reversion dynamic is directly what the strategy expects. The SHAP evidence here is empirical confirmation (on Binance Futures perp data) that VWAP-to-mid deviations carry reversal signal.

**Finding 2 — OFI has diminishing marginal effects at extremes:**
> "positive imbalance predicts positive returns, but with diminishing marginal effects at extremes (diminishing incremental impact as pressure accumulates)"

For ST2.0: the entry gate fires on elevated positive OFI (bid-heavy book). The paper finds that at very extreme OFI values, the incremental predictive power is concave — more extreme doesn't add linearly more signal. This suggests that entries triggered at very extreme imbalance may offer no better directional backing than moderate-imbalance entries, while likely carrying more adverse selection risk (more committed buying).

**Finding 3 — Maker underperformance on mid-cap altcoin perps (verified with numbers):**
| Asset | Strategy | ARC | IR |
|-------|----------|-----|----|
| ETC | Taker | 5.78% | 8.97 |
| ETC | Maker | −0.07% | −0.05 |
| ENJ | Taker | 4.06% | 6.58 |
| ENJ | Maker | −0.81% | −0.77 |
| ROSE | Taker | 7.00% | 5.28 |
| ROSE | Maker | 0.27% | 0.32 |

> "In stark contrast to the taker strategy's success, the market-making strategy suffered catastrophic losses during the flash crash."

> "A market maker who fails to widen their spread in response is essentially offering a subsidy to informed traders, leading to near-certain losses."

**What this extends for ST2.0:** arXiv:2502.18625 (N1 synthesis) established maker underperformance on Binance BTC perp specifically. arXiv:2602.00776 extends this to smaller-cap altcoin perps (ETC, ENJ, ROSE — comparable market-cap tier to ST2.0's INJ/AVAX/ARB universe). Taker IR is 5–9× while maker IR is flat-to-negative for these assets. ETC, ENJ, ROSE are lower-liquidity assets where adverse selection of passive orders is most severe — the same structural property as ST2.0's altcoin targets.

**What the cross-asset SHAP stability means for ST2.0 gates:**
> "The same families of features dominate the SHAP summaries across large-cap and mid/long-tail cryptoassets."

Order flow imbalance, spread, and VWAP-to-mid rank similarly across all five instruments. This supports applying ST2.0's existing imbalance gate and tape gate (calibrated on whatever fills exist) to new altcoin symbols without per-symbol retuning — the feature importance structure is stable across market-cap tiers.

**Critical limitations:**
1. arXiv preprint — not peer-reviewed at time of search. University of Warsaw, not a top-tier microstructure venue.
2. Dataset is Binance Futures, not Phemex. Participant mix, tick size, and fee structure differ.
3. The "maker" and "taker" strategies in the paper are tested in the SAME direction as the predictive signal (OFI positive → enter long as taker or post bid as maker). ST2.0 is COUNTER-TREND (buy absorption → post passive SHORT). The maker-vs-taker performance comparison maps directionally only if you believe the signal can be exploited in either direction.
4. VWAP-to-mid finding: the paper uses SHAP on a predictive ML model; the VWAP-to-mid feature's specific directionality (positive vs negative deviation) in the context of a passive short on absorption is inferred, not directly measured.
5. Five assets only; ETC/ENJ/ROSE are not INJ/AVAX/ARB. Market microstructure may differ.
6. **Risk: this paper is from January 2026 and predates the research series by ~6 months. Tweaks 1–22 (archived in N22) are not in the reports I reviewed. Verify arXiv:2602.00776 is not already documented there before assigning a new tweak number.**

---

### arXiv:2507.22712 — "Order Book Filtration and Directional Signal Extraction at High Frequency"
**URL:** https://arxiv.org/html/2507.22712v1
**Dataset:** National Stock Exchange of India (NSE), BANKNIFTY index futures. January 2–13, 2021 and January 24, 2021. NOT crypto.

**Core finding:** Three structural filters targeting fleeting orders (lifetime < threshold, modification count > threshold, update timing < threshold) improve OBI directional signal quality. Unfiltered OBI "conflates genuine imbalance with short-lived manipulation, weakening its directional informativeness."

**Why not actionable for ST2.0:** NSE equity index futures with tick-by-tick millisecond data. ST2.0 operates on Phemex CEX perp futures at 60-second cycle granularity. Fleeting-order contamination of OBI is primarily a millisecond HFT problem; at ST2.0's 60s evaluation cycle, short-lived spoof orders have already resolved. No quantitative results on adverse selection reduction were extractable from the fetch. Cannot transfer finding to Phemex crypto perp at retail cycle speed.

---

### arXiv:2607.28323 — "Optimal Execution with Passive Market Impact"
**URL:** https://arxiv.org/abs/2607.28323
**Dataset:** NASDAQ equities and public FX data. NOT crypto perp.

**Core model:** Exponential decay of fill probabilities with distance from midprice; linear price response to OFI. Optimal strategy balances fill intensity vs accumulated passive impact and non-execution risk.

**Why not actionable for ST2.0:** NASDAQ/FX data only; no crypto calibration. The model's optimal solution yields no universal prescription ("the optimal strategy depends on controlling quote aggressiveness"). The exponential fill-probability decay with price distance was already established for crypto perp by Fabre & Ragel (N30). Not new for ST2.0's use case.

---

### MDPI 2227-7072/14/5/103 — "Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures"
HTTP 403 Forbidden — 4th consecutive blocked night. Claim about funding-window spread peaks remains **UNVERIFIED**. Cannot act on it.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 35 | **VWAP-to-mid deviation log at signal time.** At signal time, compute and log `vwap_to_mid` = (60s tape VWAP − current mid) / mid from the existing tape buffer. For a passive SHORT on buy absorption: hypothesis is that fills where mid > VWAP (recent trades below current mid = price rose away from trade cluster, absorption peak passed) show better reversion outcomes than fills where mid < VWAP (ongoing lift, price still rising). After 30+ fills: does `vwap_to_mid` cluster at any sign/magnitude for adverse vs clean fills? Cross-reference with Tweak 24 (static depth) and Tweak 34a (ask depth growth rate). **Verify this isn't already in the N22 archived queue (Tweaks 1–22) before assigning this number.** | arXiv:2602.00776, Bieganowski & Ślepaczuk Jan 2026 (Binance Futures perp, 5 assets, Jan 2022–Oct 2025 — NOT Phemex; SHAP model study of return prediction, not direct adverse selection measurement; pre-series paper, check for prior coverage) | Queued — log only | 2–3 lines |
| 35a | **OFI extremity diagnostic.** At signal time, bin the absolute OFI value into 3 buckets: moderate (0.25–0.40), high (0.40–0.55), extreme (>0.55). Log which bucket alongside fill/adverse outcome. Hypothesis: extreme OFI entries (>0.55) may show worse outcomes than moderate OFI entries (0.25–0.40) because the paper finds diminishing predictive returns at extremes while adverse selection risk presumably rises. **This is the opposite of what a simple "more extreme = stronger signal" intuition would suggest.** If confirmed: candidate gate to block entries when OFI is too extreme. Cross-reference with existing ±0.25 gate logic. **Same caveat as Tweak 35 — verify not already in N1–22 queue.** | arXiv:2602.00776, same source (Binance Futures perp — NOT Phemex; paper measures return prediction via ML, not direct adverse selection; counter-trend application is inferred) | Queued — log only | 3–4 lines |

---

## Honest Caveats

1. **arXiv:2602.00776 predates this research series.** The paper is from January 2026; the nightly series started in June 2026. It is plausible this paper was found and archived in N1–N22 (Tweaks 1–22, archived in N22). The reports reviewed tonight (N28, N30–N33) do not reference it, and neither does the N1 synthesis. But N1–N27 were not reviewed. Before acting on Tweaks 35/35a, verify against the N22 archived list.

2. **VWAP-to-mid directionality requires care.** The paper's SHAP finding is: VWAP-to-mid predicts short-term returns with reversion. The sign interpretation for ST2.0 (passive SHORT on absorption) requires careful thought about which direction of VWAP-to-mid deviation predicts better or worse outcomes for a counter-trend entry, and is not directly resolved by the paper. Log first, interpret from data.

3. **OFI diminishing-returns finding applies to trend-following use of OFI.** The paper uses OFI as a return predictor in the same direction (high positive OFI → long). For ST2.0's counter-trend short, the diminishing-returns finding may not transfer cleanly. Treat Tweak 35a as a diagnostic hypothesis, not a derived result.

4. **Maker underperformance on altcoin perps** is now supported by two independent papers (arXiv:2502.18625 for BTC, arXiv:2602.00776 extending to ETC/ENJ/ROSE). The implication (passive maker short at small size with no rebate is structurally adverse-selected) is corroborated — but these papers test maker-in-signal-direction, not counter-trend maker. This is an important structural caveat.

5. **39 → 41 tweaks queued (if 35/35a not already archived), 0 deployed across 34 nights.** The binding constraint remains deploying priority tweaks 4, 6, 9, 10, 11, 12, 14 to collect 30+ tagged fills. Logging tweaks 35 and 35a are each 2–3 lines and can be added alongside any priority-tweak deploy session.

---

## Cumulative Forward-Test Queue (39–41 Tweaks)

Priority tweaks (unchanged from N20–N33): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweaks 35, 35a potentially added tonight — **verify against N22 archive first**.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a).

---

## Night 34 Bottom Line

One new verified paper; two diagnostic log tweaks conditional on prior-queue check.

arXiv:2602.00776 (Bieganowski & Ślepaczuk, University of Warsaw, Binance Futures perp, 5 assets BTC/LTC/ETC/ENJ/ROSE, Jan 2022–Oct 2025, VERIFIED via HTML):

(1) "VWAP-to-mid deviations show asymmetric effects coherent with short-lived pressure and microstructure reversion" → Tweak 35: log 60s tape VWAP−mid / mid at signal time; hypothesis: mid > VWAP at signal (absorption peaked, prices starting to fall) predicts cleaner fills for a passive short.

(2) OFI has "diminishing marginal effects at extremes" → Tweak 35a: bin OFI extremity; extreme OFI (>0.55) may be no better predictor than moderate OFI (0.25–0.40) while carrying higher adverse selection risk.

(3) Maker strategy performance on mid-cap altcoin perps: ETC maker −0.07%/−0.05 IR, ENJ maker −0.81%/−0.77 IR vs taker 5.78%/8.97 and 4.06%/6.58 IR respectively. Extends N1's BTC-specific maker-underperformance finding to the altcoin tier comparable to ST2.0's universe (INJ/AVAX/ARB).

Critical limitations: preprint, Binance not Phemex, return-prediction SHAP study not direct adverse selection measurement, paper predates series (check N22 archive). Three other candidates evaluated (arXiv:2507.22712 NSE equity futures; arXiv:2607.28323 NASDAQ/FX; arXiv:2510.27334 spot LOB simulation) — none applicable to Phemex crypto perp at ST2.0's scale. MDPI funding-window paper: HTTP 403, 4th night.

**Recommendation unchanged:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Add Tweaks 35/35a (2–3 lines each) in the same session after verifying they're not already in the N22 archive. Night 34: 39–41 tweaks queued, 0 deployed.
