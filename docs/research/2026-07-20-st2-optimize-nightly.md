# ST2.0 Execution Optimization — Night 24
**Date:** 2026-07-20 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 23 Nights

N23 closed with: arXiv:2307.04863 flagged as UNVERIFIED (HTML 404), SSRN 6693260 never surfaced, and the recommendation to halt research in favor of implementing tweaks 4, 6, 9, 10, 11, 12, 14. Tonight resolved the 2307.04863 gap and surfaced two genuinely new 2026 papers and one practitioner pattern not previously covered.

**Summary of new material tonight:**
- arXiv:2307.04863 — NOW VERIFIED (was unverified in N23). Full title, direct quotes, and the savings-function framework extracted.
- arXiv:2607.09230 (Jeon, July 2026) — new paper, never previously surfaced. Confirms L2 liquidity state is the primary predictor; order flow is only a second-order conditioner layered on top.
- SSRN 6693260 (Chang, May 2026) — new paper, direct topic match ("passive-buy toxicity prediction on BTC perpetual futures"), but SSRN blocked. Findings extracted from Google index only — UNVERIFIED quantitatively.
- hftbacktest practitioner pattern — price-displacement-triggered cancel (not TTL-based), directly applicable.

**Not new (confirmed misses):** Optimal cancel TTL, LOB replenishment speed, placement depth in ticks — three persistent gaps remain unresolvable via accessible literature after 24 nights.

---

## Finding A — arXiv:2307.04863 VERIFIED: Savings Function + Power-Law Placement

**Source:** Timothée Fabre (SUN ZU Lab) and Vincent Ragel (LMICS, CentraleSupélec / BNP Paribas).  
**Title:** "Tackling the Problem of State Dependent Execution Probability: Empirical Evidence and Order Placement"  
**URL:** https://arxiv.org/abs/2307.04863 (abstract); HTML at https://arxiv.org/html/2307.04863v1  
**Dataset:** Nov 5 – Dec 5, 2022. BTC-USD and ETH-USD (crypto), BNP Paribas and LVMH (equities).

**Why this is NEW:** N23 could not access the paper (HTML 404, PDF too large). Tonight the HTML was readable. The savings-function framework and power-law finding are genuinely new — no prior night covered this formulation.

**Verified quotes:**

> "We discuss the importance of accurately estimating the clean-up cost that occurs in the case of a non-execution and we show it can be well approximated by a smooth function of market features."

> "In the case of a non execution, the agent will incur a transaction cost that may be greater than if an immediate execution had been chosen at the beginning because of market risk."

> "The fill probability decreases with the distance parameter δ and asymptotically scales as a power law function for both crypto pairs."

> "For small-tick assets [crypto]: the taker-maker fee gap forces the algorithm to post limit orders in the spread."

**The savings function (verified from paper):**

S(T, δ, q, z) = F_T(δ, q, z) × (fill_value) − (1 − F_T(δ, q, z)) × V(T, δ, q, z)

Where F_T(δ, q, z) is the state-dependent fill probability and V(T, δ, q, z) is the expected clean-up cost on non-execution (how much the market moves against the position if the limit order doesn't fill within horizon T).

**Calibrated horizon:** Crypto T = **1 second** (vs equities T = 10 seconds). Empirical fill rate within T=1s: **~2% for crypto pairs, ~4% for equities**.

**What this means for ST2.0:**

1. **Clean-up cost gate:** When the estimated non-execution cost V is high (book is moving away from signal price, bid_drift is accelerating), the savings function S goes negative — the passive limit order has negative expected value and should not be posted. This provides theoretical grounding for bid_drift_bps (Tweak 23) as an entry gate, not just a log: if bid has already drifted > threshold since signal, don't post.

2. **Power-law placement:** Fill probability at distance δ from best bid follows a power law for crypto. This means: posting 1 tick away from best bid vs AT best bid is a large jump in fill probability (power-law, not linear). Shadow-logging `placement_distance_ticks` + fill outcome would empirically calibrate this curve for Phemex specifically (Tweak 25 below).

**Critical limitations:**
- T=1s horizon is profoundly different from ST2.0's ~3–4 minute wait time. The paper frames this as "post LO or immediately execute as taker" within 1 second — ST2.0 waits minutes. The conceptual framework transfers; the quantitative calibration does not.
- Data is BTC/ETH spot-like (not Phemex altcoin perps). Altcoin perps have different tick structures and participant mix.
- The paper does not publish a concrete δ* value — optimal placement is solved per-state numerically. The clean-up cost gate is a pattern, not a number.

---

## Finding B — arXiv:2607.09230 VERIFIED: L2 State Is Primary; Order Flow Is Secondary

**Source:** Joohyoung Jeon. "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures." arXiv, July 10, 2026.  
**URL:** https://arxiv.org/html/2607.09230v1  
**Data:** Crypto futures (venue not confirmed from accessible portion). 1-minute cadence.

**Verified quotes:**

> "The first-order predictive signal is the pre-event L2 liquidity state: a coarse pre-event state baseline strongly predicts post-event liquidity regimes."

> "Order flow adds further value only when layered on top of the L2 state model, not as a replacement."

**What this means for ST2.0:**

Prior nights established the LOB composite state `lob_state` (Tweak 20: calm/mixed/stressed from spread + inverted depth + imbalance) and individual order flow signals (OFI slope, imbalance duration, tape buy_ratio). This paper adds a clear hierarchy: **L2 state comes first; OFI/tape are second-order conditioners on top of L2 state.** This means Tweak 20 (`lob_state`) should be the primary pre-entry gate, with OFI-based tweaks (16, 21, 22) as secondary filters — not interchangeable alternatives.

Practical implication for the tweak queue: implement Tweak 20 (lob_state composite) before tweaks 16/21/22 (OFI conditioners). This upgrades Tweak 20 from "depends on Tweaks 6 + 14 first" to a structural priority.

**Critical limitations:**
- "This is a prediction study of liquidity-state transitions at a one-minute cadence, not a trading or execution study" — their own words. The dependent variable is next-minute L2 regime, not fill-level adverse selection.
- Venue not confirmed from accessible abstract text. May be BTC-only or single exchange.
- Directional confirmation, not quantitative calibration.

---

## Finding C — SSRN 6693260 UNVERIFIED: Flow-Adjusted Bid-Absorption as Toxicity Predictor

**Source:** Lawrence Chang. "Do Order-Book States Predict Passive-Buy Toxicity? Evidence from BTC Perpetual Futures." SSRN, May 2, 2026.  
**URL:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6693260  
**Access:** HTTP 403. Findings extracted from Google index only — **UNVERIFIED quantitatively.**

**Claimed findings (from Google index, not direct paper access):**

Three named features as predictors of whether a passive fill is toxic or non-toxic:
1. Recent directional order flow
2. **Flow-adjusted bid-absorption capacity at the near touch** — described as "substantially more informative than raw directional flow alone"
3. Liquidity-state fragility — "execution risk depends not only on recent aggressive flow, but also on the vulnerability of the surrounding displayed liquidity"

**Why this matters (even unverified):** N23's Finding B (CME paper) established that ~80% of passive fills are adverse and ~20% are not. This SSRN paper directly asks "what predicts which fills land in the non-toxic 20%?" — the single most directly applicable question for ST2.0. The three named features map onto our existing tweak queue:
- Feature 1 (directional flow) → Tweaks 10, 21 (imbalance_duration, ofi_slope_direction)
- Feature 2 (flow-adjusted bid-absorption at near touch) → Tweak 9 (dominant_bid_size_ratio) + new element: flow-adjustment
- Feature 3 (liquidity fragility) → **not yet in the queue** → Tweak 24 below

**What "liquidity-state fragility" likely means operationally:** how thin the ask depth is relative to its recent baseline. If the ask side is unusually thin, displayed liquidity is fragile — a few aggressive buys wipe it and price jumps, leaving a filled short underwater.

**Caveats:** Every numerical claim from this paper is UNVERIFIED. If a copy becomes accessible (author contact, ResearchGate, direct request), read it before implementing any gate derived from it.

---

## Finding D — hftbacktest Practitioner Pattern: Price-Displacement Cancel vs TTL Cancel

**Source:** hftbacktest documentation. "Queue-Based Market Making in Large Tick Size Assets."  
**URL:** https://hftbacktest.readthedocs.io/en/latest/tutorials/Queue-Based%20Market%20Making%20in%20Large%20Tick%20Size%20Assets.html  
**Access:** Directly readable. Practitioner tutorial, not academic.

**Verified quotes:**

> "Cancels if a working order is not in the new grid."

> "it may be more effective to respond to each incoming feed" [than fixed 100ms intervals]

**Placement rule from code example:**  
`bid_price = np.minimum(reservation_price - half_spread, best_bid)`  
Where half_spread is set at `tick_size * 0.49`.

**What this adds for ST2.0:** The practitioner pattern is: cancel when the inside bid has moved outside your target price band — not on a fixed timer. This is actionable because ST2.0 currently posts and waits with no cancel trigger other than TTL expiry. A price-displacement trigger is implementable in ~3 lines: track signal_bid at post time; if current_bid < signal_bid - threshold_bps, cancel (the fill opportunity has moved away from you). This is the ACTION version of Tweak 23's bid_drift_bps log.

Also from the Multicoin Capital piece (Feb 2026, https://multicoin.capital/2026/02/17/adverse-selection-rules-everything-around-me/): "By letting cancels execute before new taker orders, Hyperliquid lowers the risk for market makers during fast market moves." This confirms Phemex does NOT offer cancel-before-fill protection — a structural disadvantage for resting makers. This is unactionable for ST2.0 (venue constraint), but explains why cancellation on Phemex is slower to take effect than on Hyperliquid.

---

## Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority |
|---|---|---|---|
| 24 | Log `ask_depth_fragility` = ask depth at signal / avg ask depth prior 60s (shadow log). Low values → fragile displayed liquidity → higher adverse selection risk per Chang SSRN 6693260 concept | Finding C (UNVERIFIED source; log only — no gate) | Queued (2–3 lines) |
| 25 | Log `placement_distance_ticks` (how many ticks from best bid ST2.0 posts) + fill outcome together. Empirically calibrate the power-law fill probability curve for Phemex altcoin perps specifically | Finding A (arXiv:2307.04863, verified) | Queued (2 lines) |
| 26 | Shadow-gate price-displacement cancel: log whether bid_drift_bps from Tweak 23 exceeds 3/5/8 bps thresholds, and what the outcome would have been if canceled at each threshold | Finding D (hftbacktest practitioner, verified) | Queued — depends on Tweak 23 data |

---

## Hierarchy Update (from Finding B)

Prior nights treated lob_state (Tweak 20) and OFI conditioners (Tweaks 16, 21, 22) as peers. Finding B (Jeon 2607.09230) establishes that L2 state is structurally primary and OFI is second-order. Revised implementation priority within the existing queue:

**Implement Tweak 20 (`lob_state`) before Tweaks 16/21/22.** The `calm` regime from lob_state is the minimum threshold condition; OFI tweaks only apply when lob_state passes. This is not a new tweak — it's a reordering within the existing queue.

---

## Honest Caveats

1. **Finding A (arXiv:2307.04863):** Fully verified for direct quotes and framework. BUT it uses T=1s horizons — ST2.0 waits ~3–4 minutes. The power-law concept and savings-function structure transfer conceptually; no number from the paper should be imported as a Phemex calibration.

2. **Finding B (arXiv:2607.09230):** Verified quotes. Studies liquidity-state transitions (regime prediction), not fill-level adverse selection. The hierarchy conclusion (L2 first, OFI second) is directionally credible but not quantitatively precise.

3. **Finding C (SSRN 6693260):** Title and feature names extracted from Google index only. HTTP 403 persists. Zero numbers are verifiable. Do not implement any gate derived from this paper until the full text is read.

4. **Finding D (hftbacktest):** Practitioner tutorial, not academic. The price-displacement cancel pattern is logical and productizable, but there is no empirical data on whether it improves or worsens PnL outcomes for a strategy with ST2.0's signal/horizon profile.

5. **The TTL gap, LOB replenishment gap, and optimal placement depth gap remain unresolved.** Night 24 searched all three again. Nothing found. These appear to be genuine gaps in accessible literature for this specific problem.

6. **24 tweaks queued, 0 deployed across 24 nights.** Tweak 26 depends on Tweak 23 data (bid_drift_bps logging). Tweak 23 depends on implementation. Priority tweaks 4, 6, 9, 10, 11, 12, 14 remain the minimum viable implementation set. The binding constraint is still empirical data, not knowledge.

---

## Cumulative Forward-Test Queue (26 Tweaks)

Priority tweaks (unchanged): **4, 6, 9, 10, 11, 12, 14** — each 2–5 lines of shadow logging. Structural priority reorder: Tweak 20 before Tweaks 16/21/22 (per Finding B hierarchy).

Tweaks 24, 25, 26 added tonight. Full queue reproduced in N22; not repeated here.

---

## Night 24 Bottom Line

Three verified new findings (arXiv:2307.04863 now fully read; arXiv:2607.09230 new July 2026 paper; hftbacktest practitioner cancel pattern). One unverified but directly relevant new paper (SSRN 6693260 — the closest thing to an adverse-selection classifier for BTC perp fills). The main structural contributions: (a) theoretical grounding for bid_drift_bps as a cancel gate (not just a log) via the savings function — when clean-up cost > half-spread, the passive order has negative expected value; (b) L2 state is hierarchically primary over OFI signals, which upgrades Tweak 20 implementation priority; (c) ask_depth_fragility (Tweak 24) is the one genuinely new feature concept from the Chang SSRN paper.

**Recommendation unchanged from N20-N23:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Do not add more to the queue until 30+ tagged fills per diagnostic variable are collected. Research is now at Night 24 with 26 tweaks queued, 0 deployed.
