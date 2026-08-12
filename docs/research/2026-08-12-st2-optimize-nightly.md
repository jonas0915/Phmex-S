# ST2.0 Execution Optimization — Night 43
**Date:** 2026-08-12 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 42 Nights

N42 closed with no new tweak (10th consecutive night, literature declared saturated since N33). Prior 42 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, short-term price reversal regime detection, sentiment regimes, ETH/BTC order flow asymmetry, sunshine trading / TWAP transparency (Hyperliquid), OFI shock dissipation speed (E-mini baseline).

Tonight searched four angles:
1. arXiv:2602.00776 (Bieganowski & Ślepaczuk — "Explainable Patterns in Cryptocurrency Microstructure", Binance perp, 2022–2025, 1-second) — not previously named in any night's covered list; potentially covered under "OFI diminishing returns" topic but dataset/paper not yet cited.
2. SSRN 6693260 (Lawrence Chang) — 8th access attempt via papers.ssrn.com direct URL.
3. arXiv:2603.09164 (Sepper — "Slippage-at-Risk") — appeared in search results, not previously evaluated.
4. Practitioner OFI decay data for crypto perps (Tigro Blanc / Coinmonks, OKX perp, Jan 2026) — partially addresses the open literature gap from N42.

**Net result tonight: One verified paper not previously cited by name (arXiv:2602.00776) with a corroborative finding. One unverified practitioner piece with OFI decay estimates for crypto perps. SSRN 6693260 remains blocked (attempt 8). No new forward-testable execution tweak.**

---

## Papers Evaluated Tonight

### arXiv:2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure"
**Authors:** Bartosz Bieganowski, Robert Ślepaczuk
**Published:** February 2026. arXiv preprint.
**URL:** https://arxiv.org/html/2602.00776v1
**Dataset:** Binance Futures perpetual contracts. BTC, LTC, ETC, ENJ, ROSE (market cap positions 1, 20, 40, 60, 100 as of Jan 1, 2022). 1-second frequency. January 1, 2022 – October 12, 2025.

**Verification status: VERIFIED** — HTML fetched and analyzed (two fetch passes).

**Key findings (verbatim from fetch):**

1. **OFI concavity at extremes:**
> "order flow imbalance has a largely monotone effect with concavity at extremes"
> "diminishing incremental impact as pressure accumulates"
> "the dependence curves exhibit consistent shapes across assets: the effect of order flow imbalance on returns is predominantly monotone with concavity at extremes"

2. **VWAP-to-mid asymmetric reversion:**
> VWAP-to-mid deviations "display asymmetric effects coherent with short-lived pressure and microstructure reversion"

3. **Flash crash maker adverse selection:**
> "the model was repeatedly filled on its bid-side quotes, forcing it to accumulate a growing, and increasingly unprofitable, long position"
> During extreme OFI events: "the model's prediction values reached extreme levels, far outside their normal stationary range, indicating that the magnitude of the order book imbalance was unprecedented"

4. **Adverse selection theory grounding (verbatim):**
> "bid-ask spread is not just a source of profit...but compensation for risk of trading against informed participants"

**What this means for ST2.0:**

The OFI concavity finding has a concrete implication for ST2.0: the strategy triggers at extreme absorption (high OFI tail), precisely the zone where the OFI-to-price predictive relationship saturates. At these extremes, diminishing marginal OFI impact means the expected directional signal is weaker per unit of additional imbalance — the buying pressure has accumulated but is generating less and less incremental return momentum. For a passive SHORT on reversion, this could cut either way:
- *Bearish for the strategy:* the fills that occur at extreme OFI (confirmed as adversely selected — N1 synthesis, arXiv:2502.18625) now also coincide with the weakest signal zone, compounding the problem.
- *Ambiguous for reversion quality:* the concavity could also mean the extreme OFI has exhausted buying pressure (saturation → reversal more likely). The paper does not distinguish.

The flash crash analog is the clearest data point: during the October 10, 2025 flash crash, the maker strategy was repeatedly filled at extreme OFI and suffered catastrophic losses — the opposite of what a passive short would have needed. This is the "exactly wrong" scenario for ST2.0 at extreme absorption.

The VWAP-to-mid finding (asymmetric, short-lived pressure → microstructure reversion) corroborates Tweak candidates in the existing queue (VWAP-to-mid gate).

**Why NOT a new standalone tweak:**
- The "OFI concavity at extremes" finding mechanistically supports the N1 synthesis hypothesis (a): "wait for buy-pressure to roll over (OFI flip) before posting." This hypothesis is already in the tweak queue. The paper provides a primary source backing for it, not a new direction.
- The concavity does not disambiguate between "extreme OFI = exhausted buying = good reversion signal" vs. "extreme OFI = unreliable predictor + worst fill zone." Resolving this requires labeled fill data (i.e., deploying Tweaks 4, 6, 9, 10, 11, 12, 14).
- Dataset spans altcoins (LTC, ETC, ENJ, ROSE) alongside BTC — the cross-asset portability is confirmed, but the 1-second resolution doesn't translate directly to ST2.0's 60-second cycle.

**Assessment: VERIFIED. Corroborative — provides a multi-year Binance Futures primary source for OFI concavity at extremes, directly supporting the existing OFI-flip hypothesis in the queue. Strengthens confidence in existing priority tweaks; no new tweak warranted.**

---

### SSRN 6693260 — Lawrence Chang (attempt #8)
**Status:** HTTP 403 Forbidden — eighth consecutive failed access. URL tried: `papers.ssrn.com/sol3/papers.cfm?abstract_id=6693260`.

**Still unverified.** Claimed content from search snippet (DO NOT cite as fact):
- Claimed title: "Do Order-Book States Predict Passive-Buy Toxicity? Evidence from BTC Perpetual Futures"
- Claimed finding: "flow-adjusted bid-absorption proxy is substantially more informative than raw directional flow alone, with higher recent sell pressure relative to best-bid depth predicting lower short-horizon future returns and higher passive-buy adverse-selection risk"
- Claimed three predictors: (1) recent directional order flow, (2) near-touch bid-side absorption capacity, (3) liquidity-state fragility

All above is from search engine index snippet only. Primary source inaccessible. Eight consecutive 403 errors. Next viable route: ResearchGate author profile search (searching "Lawrence Chang" + "BTC perpetual" + "toxicity"), or NCCU repository direct search. Tweak 37 remains conditional on this paper's verification.

---

### arXiv:2603.09164 — "Slippage-at-Risk (SaR): A Forward-Looking Liquidity Risk Framework for Perpetual Futures Exchanges"
**Author:** Otar Sepper
**Dataset:** Hyperliquid order book data, including October 10, 2025 liquidation cascade.
**URL:** https://arxiv.org/abs/2603.09164

**Verification status: VERIFIED** — abstract and key claims confirmed via fetch.

**Key finding (verbatim from fetch):**
> "SaR provides a forward-looking assessment of liquidation execution risk derived from current order book microstructure."

**Assessment: VERIFIED, NOT APPLICABLE.** Hyperliquid DEX liquidity risk framework. Focuses on exchange-level slippage-at-risk measurement, not passive maker fill quality or adverse selection for a directional short. No content applicable to Phemex CEX passive order execution.

---

### Practitioner: "Meta-Order Flow in Crypto Perps: Catching Big Whale" (Medium/Coinmonks)
**Author:** Tigro Blanc (pseudonymous)
**URL:** https://medium.com/coinmonks/meta-order-flow-in-crypto-perps-catching-big-whale-6a127e2f70e8
**Dataset claimed:** OKX perpetual contracts, January 18–31, 2026 (14-day proprietary)

**Verification status: UNVERIFIED — practitioner blog, not peer-reviewed, proprietary unpublished data.**

**Claimed findings (from fetch — not citable as fact):**
- OFI Information Coefficient (IC) by horizon on crypto perps: "10s horizon: IC 0.127, t-stat 6.86"; "30s horizon: IC 0.086, alpha 0.42 bps (BTC)"; "by 120s, signal edge is near zero"
- "Q5-Q1 spread of 0.25 bps at 30s" — imbalance quintile spread persists but decays
- Fill-rate uncertainty acknowledged: "Fill-rate uncertainty under passive execution" listed as a constraint; no empirical data on passive fill adverse selection provided

**Why this matters for the literature gap:** Across 42 prior nights, no peer-reviewed primary source measured OFI signal decay speed specifically in crypto perpetual futures. This practitioner piece, if taken at face value, suggests OFI on OKX crypto perps has an IC half-life of ~10-30 seconds and becomes near-negligible by 120 seconds. This is substantially slower than the E-mini benchmark from N42 (arXiv:2508.06788: OFI shock dissipates within 1 second). The practitioner data tentatively supports the "5-15 second OFI settling window" inference from N42, but cannot close the literature gap. It remains strictly unverified.

**Implication if true (speculative, labeled):** A passive order posted immediately at OFI extreme fires at the peak of the signal, which (per arXiv:2602.00776) is also the concavity zone — diminishing incremental predictive power. A 10-15 second delay before posting would (a) let the OFI signal peak and begin rolling over, moving into the more-linear regime where OFI-to-price is more reliable, and (b) reduce adverse selection by avoiding the fill window where buying is still sustained. This is the OFI-flip hypothesis again — same queue item, additional (unverified) mechanism support.

---

## New Forward-Testable Tweak Tonight

**None.** arXiv:2602.00776 is corroborative of existing queued items (OFI-flip hypothesis, VWAP-to-mid gate). The practitioner OFI decay data is unverified. No new primary source justifies adding to the queue.

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **arXiv:2602.00776 may already have been evaluated** under the "OFI diminishing returns" topic in earlier nights (the night-by-night covered lists archive by topic, not by arXiv ID). If so, tonight adds zero new papers. If not, it's the first Binance Futures primary source to formally quantify OFI concavity at extremes with a multi-year, 1-second dataset — and strengthens the case for OFI-flip timing over immediate-at-extreme posting.

2. **The practitioner OFI decay data (OKX perp, 14-day, Jan 2026) is UNVERIFIED.** IC = 0.127 at 10s, near zero at 120s — these numbers are from a pseudonymous Coinmonks blog post with proprietary data. They cannot be cited, but they are consistent with the inference from N42 (crypto perps likely have OFI decay over 5-30 seconds, not <1 second like E-mini). The literature gap on this question remains open.

3. **SSRN 6693260 — 8 consecutive 403s.** The paper is almost certainly under journal embargo or behind a hard paywall. The claimed content (flow-adjusted bid-absorption proxy as passive-buy toxicity predictor) would be the single most directly applicable primary source in the 43-night corpus if verified.

4. **43 nights, 42 tweaks, 0 deployed.** The 11th consecutive night without a new actionable tweak. The binding constraint is unambiguously deployment. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14 and log-only Tweaks 36–38 to generate labeled fill data.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N42): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 43 Bottom Line

**No new actionable execution tweak tonight.** Key findings:

**arXiv:2602.00776** (Bieganowski & Ślepaczuk, "Explainable Patterns in Cryptocurrency Microstructure", Binance Futures, BTC/LTC/ETC/ENJ/ROSE, 1-second, Jan 2022–Oct 2025): OFI concavity at extremes — "diminishing incremental impact as pressure accumulates." At extreme absorption (ST2.0's trigger zone), OFI-to-price predictive power saturates. Flash crash maker fills: "repeatedly filled on bid-side quotes, forcing it to accumulate a growing, and increasingly unprofitable, long position." VWAP-to-mid: "asymmetric effects coherent with short-lived pressure and microstructure reversion." Corroborative — provides a multi-year Binance Futures primary source for OFI concavity, strengthening the existing OFI-flip hypothesis in the queue. No new tweak.

**Practitioner (UNVERIFIED — Tigro Blanc, OKX perp, 14-day Jan 2026):** OFI IC = 0.127 at 10s, near zero by 120s in crypto perps. Consistent with N42's inference (crypto OFI decays over 5-30 seconds, far slower than E-mini's <1 second). Cannot close literature gap — not peer-reviewed, proprietary data.

**SSRN 6693260 — 8 consecutive 403s.** Still the single highest-value inaccessible paper in the corpus.

**arXiv:2603.09164** (Sepper, Hyperliquid, Oct 2025): Slippage-at-Risk framework — DEX-specific, not applicable.

**Recommendation after 43 nights:** Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14 and log-only Tweaks 36–38. Thirty labeled fills are the minimum to validate or discard the 42-tweak queue — no further literature can substitute for this. One remaining access route for SSRN 6693260: ResearchGate or NCCU repository search for "Lawrence Chang" + "BTC perpetual futures" + "toxicity."
