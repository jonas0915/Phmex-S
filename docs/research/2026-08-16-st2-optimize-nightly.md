# ST2.0 Execution Optimization — Night 47
**Date:** 2026-08-16 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 46 Nights

N46 closed with no new tweak (14th consecutive night; literature declared saturated since N33). Prior 46 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, short-term price reversal regime detection, sentiment regimes, ETH/BTC order flow asymmetry, sunshine trading / TWAP transparency (Hyperliquid), OFI shock dissipation speed (E-mini baseline), OFI concavity at extremes (Binance Futures 2022–2025).

Tonight searched four angles (all execution-focused):
1. New August 2026 arXiv preprints on crypto perpetual futures maker adverse selection / passive fill quality
2. arXiv:2608.00885 — "Optimal Trading of Microstructure Mean Reversion" (August 2026 — not previously checked)
3. arXiv:2608.03616 — "Measuring the engine of a liquidation cascade: subcritical branching inside a first-order transition" (August 2026 — new paper not in any prior night's citation list; BTC perp Binance + Hyperliquid, May 2022–October 2025)
4. arXiv:2608.05838 / arXiv:2608.07690 / arXiv:2506.05764 — three additional papers surfaced and screened

**Net result tonight: One new VERIFIED paper by paper ID (arXiv:2608.03616) with BTC perp crypto data. Companion paper by the same author as N46's arXiv:2607.27070 (Ramon Marc Garcia Seuma). Key finding: liquidation cascades are subcritical (branching ratio λ ≈ 0.1–0.2), front-loaded (87.8% of forced selling in first 30 minutes), and venue-backstop-dominant (62.6% of forced-sell notional absorbed off-book by Hyperliquid's HLP, not the order book). This is a second quantitative confirmation of N46's retirement of the cascade-blocking tweak class. No new forward-testable execution tweak. This is the 15th consecutive night without a new actionable finding. Tweak queue unchanged at 42.**

---

## Papers Evaluated Tonight

### arXiv:2608.03616 — "Measuring the engine of a liquidation cascade: subcritical branching inside a first-order transition"
**Author:** Ramon Marc Garcia Seuma (same author as N46's arXiv:2607.27070)
**Published:** August 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2608.03616
**Dataset:** Seven BTC perpetual futures liquidation cascades, May 2022–October 2025. Binance (historical) + Hyperliquid on-chain fill log (detailed, begins 2025-05-25). N=22 assets at May 2022, expanding to N=30 by 2024–2025.

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Key quantitative findings (direct from fetch):**

1. **Branching ratio — subcritical throughout:**
> "λ̂ ≈ 0.1–0.2 throughout"

A branching ratio below 1 means forced liquidations do NOT self-amplify. Each forced sell generates only 0.1–0.2 additional forced sells. Cascades are mechanically bounded.

2. **Front-loading — 88% of forced selling in 30 minutes:**
> "87.8% of all post-onset forced selling occurred in the first 30 minutes"

Cascades are exogenous sweeps, not slow chain reactions.

3. **Price impact during cascade onset:**
> "a factor of 1.2–3.5 regressed, 3.2–9.1 quoted directly"

The order parameter (a liquidity/order-flow composite) "jumps by between 1.6 and 4.4 baseline standard deviations into a near-fully-ordered phase."

4. **Off-book absorption dominates — Hyperliquid-specific:**
> "62.6% of post-onset forced-sell notional" was absorbed off-book by the venue backstop (Hyperliquid's HLP mechanism)

This is the paper's most structurally novel finding: the majority of forced selling during cascades does NOT hit the visible order book. The exchange's backstop absorbs it before it reaches the LOB. The paper characterizes cascades as "not a slow chain reaction but an exogenous front-loaded sweep."

**What this means for ST2.0 and the tweak queue:**

This is a companion paper to N46's arXiv:2607.27070. Together they provide two independent quantitative arguments for retiring the cascade-blocking tweak class:
- **N46 (arXiv:2607.27070):** Signal heterogeneity across 7 events — no consistent per-event early warning. Cascade-blocking gates fire on the wrong events.
- **N47 (arXiv:2608.03616):** Subcritical branching (λ ≈ 0.1–0.2) + front-loading (88% in 30 min) — even if a cascade IS correctly detected, 88% of the forced selling is already done within 30 minutes. A gate fired at onset arrives too late to avoid the bulk of the impact.

**On the off-book absorption finding (62.6%):** This is Hyperliquid-specific (HLP = Hyperliquid Liquidity Provider backstop, a DEX mechanism). Phemex is a CEX with a different liquidation engine and insurance fund. The finding does NOT directly transfer to Phemex. However, the conceptual point is worth noting: during high-absorption events, some of the apparent "bid-side absorption" visible in LOB data may be coming from venue backstop mechanisms not reflected on-book, and the true filling price may differ from the visible book. This is not quantified for Phemex and should not be acted on without Phemex-specific data.

**Why NOT a new standalone tweak:**
- The cascade topic is in the covered list (N46), and the cascade-blocking tweak class was already retired/flagged for downgrade in N46.
- arXiv:2608.03616 corroborates that retirement with an additional mechanism (subcritical branching + front-loading) rather than reversing it.
- The off-book absorption finding is Hyperliquid-specific and cannot be applied to Phemex without separate verification.
- No passive maker fill data, no adverse selection measurement, no fill quality findings.

**Assessment: VERIFIED. New by paper ID. Companion to N46 by same author. Confirms cascade-blocking tweak class retirement on two independent grounds: subcritical branching (cascades don't amplify) + front-loading (88% done in 30 min = gate-at-onset too late). Hyperliquid off-book absorption finding is DEX-specific and not transferable to Phemex. No new execution tweak.**

---

### arXiv:2608.00885 — "Optimal Trading of Microstructure Mean Reversion"
**Published:** August 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2608.00885
**Dataset:** None. Purely theoretical/mathematical paper.

**Verification status: VERIFIED** — Abstract and content confirmed.

The paper derives a symmetric band strategy optimal for exploiting microstructure mean reversion, with profit rate formula R* = α·s_G·√(2/π)·e^(−θ*²/2s_G²). Key insight: "all profit is the option value of waiting rather than immediate execution."

**Why NOT applicable:** Theoretical only, no dataset. Requires active bidirectional trading (buy at −θ, sell at +θ), speed advantage (seconds-level reversion), and maker rebates to function. ST2.0 is a directional passive short with no speed or rebate edge. Not applicable.

**Assessment: VERIFIED, NOT APPLICABLE. Theoretical, no crypto data, wrong strategy archetype.**

---

### arXiv:2608.05838 — "Asset-specific limit order microstructure noise"
**Published:** August 2026.
**URL:** https://arxiv.org/abs/2608.05838
**Dataset:** Recent NASDAQ limit order book data. No crypto content.

Models asset-specific noise tail characteristics (Gamma distributions) in high-frequency returns. Finding: "asset-specific noise tail parameters are relevant in practice" for efficient price estimation.

**Assessment: VERIFIED, NOT APPLICABLE. NASDAQ only. Noise estimation for volatility, not execution quality. No crypto content.**

---

### arXiv:2608.07690 — "On a Simple Relationship Between Order Imbalance, Skew and Width in Over-The-Counter Trading"
**Published:** August 7, 2026.
**URL:** https://arxiv.org/abs/2608.07690
**Dataset:** None. Purely theoretical. OTC markets only.

Establishes that OTC market makers should adjust quote skew at first order and width at second order in response to order imbalance. The "constant width, linear skew" heuristic emerges as a special case. No crypto content.

**Assessment: VERIFIED, NOT APPLICABLE. OTC markets only, theoretical. No crypto content.**

---

### arXiv:2506.05764 — "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books: Better Inputs Matter More Than Stacking Another Hidden Layer"
**Published:** May 2026.
**URL:** https://arxiv.org/abs/2506.05764
**Dataset:** BTC/USDT, Bybit exchange. 100ms–multi-second LOB snapshots.

Finds that data filtering (Kalman, Savitzky-Golay) matters more than model complexity for LOB price prediction. Simpler models (XGBoost, logistic regression) can match deep architectures (DeepLOB, Conv1D+LSTM). Focus is price prediction accuracy, not execution quality.

**Assessment: VERIFIED, NOT APPLICABLE. Price prediction study, not execution quality. Topic (crypto LOB microstructure) covered. No adverse selection or fill quality findings.**

---

## New Forward-Testable Tweak Tonight

**None.** arXiv:2608.03616 is verified and new by paper ID but provides a second corroborating argument for the N46 cascade-blocking retirement — not a new direction.

**Tweak queue remains at 42 (unchanged from N33).**

**Cascade-blocking tweak class: RETIREMENT CONFIRMED (dual-paper verification).** N46 (arXiv:2607.27070) established signal heterogeneity; N47 (arXiv:2608.03616) establishes subcritical branching + 30-minute front-loading. Two independent mechanisms both argue against per-event cascade-blocking gates. This class should be formally retired from the queue.

---

## Honest Caveats

1. **arXiv:2608.03616 is genuinely new by paper ID and adds quantitative content** (branching ratio, 30-minute front-loading, off-book absorption percentage) but the practical conclusion is the same as N46: cascade-blocking gates are not viable for ST2.0. The cascade-blocking tweak class is now confirmed for retirement on two independent grounds.

2. **Off-book absorption (62.6%) is Hyperliquid-specific.** Hyperliquid's HLP is a DEX backstop with no equivalent on Phemex. The on-book vs. off-book absorption split cannot be assumed to apply to Phemex's CEX liquidation engine without separate data.

3. **SSRN 6693260 (Lawrence Chang) — unchanged at 10+ consecutive 403s.** The one untried route remains: NCCU Finance department institutional email for Lawrence Chang. This is the single most directly applicable inaccessible paper in the 47-night corpus.

4. **47 nights, 42 tweaks, 0 deployed.** 15th consecutive night without a new actionable tweak. The literature for the specific problem space (passive maker adverse selection, crypto perp CEX, small size, no speed, no rebate) is confirmed exhausted through public search. No further literature review can substitute for 30 labeled fills from deploying priority Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N47): **4 [elevated], 6, 9, 10, 11, 12, 14**
**Cascade-blocking tweak class: RETIRED** (dual confirmation: arXiv:2607.27070 N46 + arXiv:2608.03616 N47).
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 47 Bottom Line

**No new actionable execution tweak tonight.** Five papers evaluated:

**arXiv:2608.03616** ("Measuring the engine of a liquidation cascade", Garcia Seuma, Binance+Hyperliquid BTC perp, May 2022–October 2025, August 2026): VERIFIED. New by paper ID. Companion paper to N46 by same author. Subcritical branching ratio λ ≈ 0.1–0.2; 87.8% of forced selling lands in first 30 minutes; 62.6% absorbed off-book by Hyperliquid's HLP (DEX-specific, not applicable to Phemex). Cascade-blocking tweak class is now confirmed for retirement on two independent grounds. Not an execution study; no new tweak.

**arXiv:2608.00885** ("Optimal Trading of Microstructure Mean Reversion", August 2026): VERIFIED, NOT APPLICABLE. Theoretical only, no dataset, no crypto. Requires speed + bidirectional trading + rebates.

**arXiv:2608.05838** ("Asset-specific limit order microstructure noise", August 2026): VERIFIED, NOT APPLICABLE. NASDAQ only.

**arXiv:2608.07690** ("Order Imbalance, Skew and Width in OTC Trading", August 7, 2026): VERIFIED, NOT APPLICABLE. OTC only, theoretical.

**arXiv:2506.05764** ("Better Inputs Matter More Than Stacking Another Hidden Layer", Bybit BTC/USDT, May 2026): VERIFIED, NOT APPLICABLE. Price prediction study, not execution quality.

**Final recommendation after 47 nights:** Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14. Formally retire the cascade-blocking tweak class. The single optional remaining action: NCCU Finance department page → Lawrence Chang's institutional email → one contact attempt for SSRN 6693260.
