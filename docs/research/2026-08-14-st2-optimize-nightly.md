# ST2.0 Execution Optimization — Night 45
**Date:** 2026-08-14 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 44 Nights

N44 closed with no new tweak (12th consecutive night, literature declared saturated since N33). Prior 44 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, short-term price reversal regime detection, sentiment regimes, ETH/BTC order flow asymmetry, sunshine trading / TWAP transparency (Hyperliquid), OFI shock dissipation speed (E-mini baseline), OFI concavity at extremes (Binance Futures 2022–2025).

Tonight searched four angles (all execution-focused):
1. New 2026 arXiv preprints on crypto perpetual futures maker adverse selection / passive fill quality
2. arXiv:2407.16527 — "The Negative Drift of a Limit Order Fill" (appeared in search, not previously cited by ID)
3. arXiv:2403.02572 — "Fill Probabilities in a Limit Order Book with State-Dependent Stochastic Order Flows" (appeared in search, not previously cited by ID)
4. arXiv:2607.09230 — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures" (July 2026 — new paper not in any prior night's citation list; Binance BTCUSDT/ETHUSDT perp, 2023–mid-2026)

Additional papers surfaced but screened out without fetch:
- arXiv:2602.00776 — covered N43
- arXiv:2606.15715 — covered N42
- arXiv:2607.28323 — covered N44
- arXiv:2608.04373 — covered N39
- arXiv:2502.18625 — covered in June-20 synthesis
- SSRN 6693260 — attempt #10 attempted via search; still inaccessible
- Frontiers/Blockchain "Microstructure alpha" (Binance spot+perp, Aug 2025–Feb 2026) — evaluated in brief; returns prediction from spread/momentum features, all Sharpe ratios deeply negative at retail fee rates; within covered topic space (cross-asset transfer, OFI diminishing returns); no new execution tweak

**Net result tonight: One new VERIFIED paper by paper ID (arXiv:2607.09230) with quantified BTC/ETH OFI asymmetry data on Binance perp 2023–2026. Corroborative — within the covered "ETH/BTC order flow asymmetry" and "state-dependent order flow" topics. Not an execution study; no new forward-testable tweak. This is the 13th consecutive night without a new actionable finding. Tweak queue unchanged at 42.**

---

## Papers Evaluated Tonight

### arXiv:2607.09230 — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures"
**Dataset:** Binance perpetual futures. BTCUSDT and ETHUSDT. January 2023 through mid-2026. 1-minute L2 snapshots (top-20 price levels). 47,513 event windows; 18,631 macro event windows, 28,882 non-event controls.
**Published:** July 2026. arXiv preprint.
**URL:** https://arxiv.org/html/2607.09230v1

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Key findings (verbatim from fetch):**

1. **L2 state dominates order flow:**
> "the first-order predictive signal is the pre-event L2 liquidity state: a coarse pre-event state baseline strongly predicts post-event liquidity regimes"

Pre-event L2 state alone improves on the marginal model by +0.045 at 5-minute horizon. Order flow adds only +0.010–0.020 additional improvement for ETH and near-zero for BTC.

2. **ETH OFI informativeness (stressed regime):**
> "The increment rises monotonically from calm to mixed to stressed, reaching 0.004, 0.020, and 0.038 at the one-minute horizon"

For ETH, order flow informativeness is highest under stressed pre-event liquidity and lowest when calm.

3. **BTC OFI informativeness:**
BTC order-flow overlay: +0.001 (1-minute), +0.003 (5-minute) — both below the flow-shuffle null threshold (0.004 at 1-minute). The paper does not establish that OFI adds predictive value for BTC perp at any horizon tested.

**What this means for ST2.0:**

The primary finding — "pre-event L2 liquidity state is the first-order predictor, not order flow" — corroborates the LOB depth profile topic in the covered list (Tweak 9/10/11 class) and is consistent with the blocked SSRN 6693260 snippet ("liquidity fragility matters as a local state variable"). The pre-event L2 state is what matters most for whether the post-event regime will be calm vs. stressed.

The BTC-specific OFI finding is the most novel quantitative data point: across a 3.5-year Binance BTCUSDT perp dataset, OFI adds essentially zero predictive value for post-absorption liquidity transitions. For ETH, OFI adds +0.020 at 1-minute horizon, which is above the null threshold.

**Implication for the existing OFI-flip hypothesis (Tweak 4/6 class):** If the OFI-flip delay (waiting for OFI to roll over before posting) is implemented, the theoretical basis is stronger for ETH entries than BTC entries. On BTC perp, OFI's predictive value for post-event L2 transitions is near-zero; the relevant pre-entry filter is the L2 depth state, not OFI timing.

**Why NOT a new standalone tweak:**
- The paper is explicitly a liquidity-state *prediction* study, not an execution study: "a prediction study of liquidity-state transitions at a one-minute cadence, not a trading or execution study, and reports no policy, profit, or simulator result."
- The ETH/BTC OFI asymmetry topic is in the covered list from prior nights (by topic, not by this paper ID).
- The BTC OFI nullity at 1-minute horizon is quantified for the first time by a primary source, but the policy implication (don't rely on OFI-flip timing for BTC entries) is a refinement of an existing queued item, not a new direction.
- The paper does not measure passive maker fill quality, adverse selection, or fill-then-price-move outcomes.

**Assessment: VERIFIED. Corroborative — provides a 2023-2026 Binance BTCUSDT/ETHUSDT perp primary source for BTC/ETH OFI asymmetry. Strengthens the case for L2-state-first filtering (pre-event book depth as the gate, not OFI timing) and adds a BTC-specific caveat to the OFI-flip hypothesis. No new tweak — topic already covered.**

---

### arXiv:2407.16527 — "The Negative Drift of a Limit Order Fill"
**URL:** https://arxiv.org/pdf/2407.16527
**Dataset:** 10-Year US Treasury Bond futures. No crypto content.

**Verification status: VERIFIED (abstract)**

**Key finding (verbatim):**
> "limit order fills are caused by and coincide with adverse price movements, which create a drag on the market maker's profit and loss"

The paper provides theoretical proof and empirical confirmation that "low-cost random fills" is a false model assumption — fills are actually "high-cost non-random" events coinciding with adverse price movements.

**Why NOT applicable:** US Treasury futures only. Conceptually within scope of the N1 synthesis ("fills cluster at extreme imbalance") but no crypto content, no new execution mechanism, no new tweak. The core finding (fills are adverse events, not random) is already the documented foundation of ST2.0's problem statement.

**Assessment: VERIFIED, NOT APPLICABLE. Wrong market. Corroborative of N1 synthesis structural diagnosis.**

---

### arXiv:2403.02572 — "Fill Probabilities in a Limit Order Book with State-Dependent Stochastic Order Flows"
**URL:** https://arxiv.org/abs/2403.02572
**Dataset:** Foreign exchange spot market data. No crypto content.

**Verification status: VERIFIED (abstract)**

Derives mathematical expressions for fill probabilities under state-dependent order flows. Key quote:
> "limit orders are not guaranteed to be executed and inherently involve a trade-off between execution cost and execution risk."

**Why NOT applicable:** FX spot only. Fill probability math under state-dependent flows is within the covered "state-dependent order flow" topic. No crypto perp data, no new tweak.

**Assessment: VERIFIED, NOT APPLICABLE. Wrong market. Topic covered.**

---

### SSRN 6693260 — Lawrence Chang (attempt #10)
**Status:** Search index re-checked. Still inaccessible via any automated route. Ten consecutive 403s across all access paths. The one untried route remains: direct author contact via NCCU Finance department institutional email. This paper's claimed content (flow-adjusted bid-absorption proxy as the primary predictor of passive-buy adverse selection in BTC perp) remains the single most directly applicable inaccessible paper in the 45-night corpus.

---

## New Forward-Testable Tweak Tonight

**None.** arXiv:2607.09230 is corroborative of existing covered topics (ETH/BTC OFI asymmetry; L2 depth profile as primary filter). The BTC-specific OFI nullity finding strengthens a BTC parameterization caveat to the existing OFI-flip hypothesis, but does not justify a new queue entry — this is a sub-variant within Tweak 4/6.

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **arXiv:2607.09230 is genuinely new by paper ID** but falls within the already-covered "state-dependent order flow" and "ETH/BTC order flow asymmetry" topics. Its most useful contribution is quantification: BTC OFI overlay ≈ 0 predictive value at 1-minute horizon (Binance BTCUSDT perp, 3.5-year dataset). This supports the inference that OFI-flip timing (existing queue) should be parameterized differently for BTC vs ETH entries if deployed.

2. **SSRN 6693260 — 10 consecutive 403s.** Still the single most directly applicable inaccessible paper. One access route untried: NCCU Finance department page for Lawrence Chang's institutional email.

3. **OFI decay speed in crypto perps remains the single most important unverified empirical gap** in the 45-night corpus. No primary source has measured how fast OFI informativeness decays in crypto perpetual futures specifically. The arXiv:2607.09230 finding that BTC OFI adds near-zero predictive value at the 1-minute level is adjacent but measures liquidity-state classification, not OFI decay speed.

4. **45 nights, 42 tweaks, 0 deployed.** 13th consecutive night without a new actionable tweak. The literature for the specific problem space (passive maker adverse selection, crypto perp CEX, small size, no speed, no rebate) is demonstrably exhausted through public search. The OFI-flip deployment (priority Tweaks 4, 6) and instrumentation closure (logging fill vs miss conditions) remain the only path forward. No further literature can substitute for 30 labeled fills.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N44): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 45 Bottom Line

**No new actionable execution tweak tonight.** Four papers evaluated:

**arXiv:2607.09230** ("When Does Order Flow Matter?", Binance BTCUSDT/ETHUSDT perp, Jan 2023–mid-2026, July 2026): VERIFIED. New by paper ID. BTC OFI overlay = +0.001 (1m) and +0.003 (5m) — below null threshold; order flow adds essentially zero predictive value for post-absorption liquidity transitions in BTC perp. ETH OFI: +0.020 (1m) under stressed pre-event L2 state. Primary predictor at both horizons is the pre-event L2 liquidity state, not OFI. Corroborative — within covered topics (ETH/BTC OFI asymmetry; LOB depth profile). Not an execution study; no new tweak. Sub-variant implication: if OFI-flip timing is deployed, consider BTC-specific parameterization (shorter delay or state-gated).

**arXiv:2407.16527** ("The Negative Drift of a Limit Order Fill", US Treasury futures): VERIFIED, NOT APPLICABLE. Wrong market. Confirms fills are adverse events, not random — already the N1 synthesis foundation.

**arXiv:2403.02572** ("Fill Probabilities with State-Dependent Order Flows", FX spot): VERIFIED, NOT APPLICABLE. Wrong market. Topic covered.

**SSRN 6693260** (Lawrence Chang): Attempt #10 = 403. Last untried route: NCCU institutional email.

**Final recommendation after 45 nights:** Literature search is confirmed exhausted. Suspend nightly reports until 30+ labeled fills are generated by deploying priority Tweaks 4, 6, 9, 10, 11, 12, 14. The single optional remaining action: check NCCU Finance department page for Lawrence Chang's email and make one direct contact attempt for SSRN 6693260.
