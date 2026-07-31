# ST2.0 Execution Optimization — Night 33
**Date:** 2026-07-31 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 32 Nights

N32 closed with: Pindza Frontiers 2026 (cross-crypto microstructure transfer fails — anti-BTC-lead-lag gate, Tweak 34), Barone & Lillo arXiv:2606.15715 (buy absorption attracts competing sellers → ask depth growth rate log, Tweak 34a), arXiv:2607.27070 (cascade EWS not viable).

Tonight searched six angles not previously covered:
1. Micro-price / weighted-mid placement and timing (Stoikov-style)
2. Cancel-and-reprice / dynamic order management for maker fills in crypto
3. VPIN / flow toxicity with specific thresholds for passive maker gating
4. Post-fill short-term alpha decay and holding period studies
5. Optimal quoting under adverse selection and price reading (arXiv:2508.20225)
6. LOB observation value and miss-feedback as signal (arXiv:2605.19584)

**Net result tonight: No new empirically-verified actionable tweak.** The literature for ST2.0's specific problem (passive CEX perp maker short at retail size, no rebate) is now substantially saturated after 32 prior nights. Details below.

---

## Papers Fetched and Evaluated Tonight

### arXiv:2508.20225 — "Optimal Quoting under Adverse Selection and Price Reading"
**Authors:** Alexander Barzykin (HSBC), Philippe Bergault (Université Paris Dauphine-PSL), Olivier Guéant (Université Paris Cité), Malo Lemmel (CNRS). June 2026, arXiv:2508.20225v5.
**Type:** Theoretical. No external market dataset — numerical examples use synthetic RFQ flows.
**URL:** https://arxiv.org/abs/2508.20225

**Core concept — price reading / skew sniffers:**

> "when the inventory is nonzero, the first component encourages stronger skewing to reduce time spent in unbalanced positions, while the second component pushes opposite"

> "the market maker's own quotes indirectly reveal information about their inventory" to "skew sniffers"

The paper establishes that a market maker whose quotes persistently reveal directional inventory faces increased adverse selection from HFTs ("skew sniffers") who trade against the implied inventory direction before the maker can rebalance.

**Theoretical applicability to ST2.0:** ST2.0 always posts a passive sell (never a bid), creating a persistent, one-directional pattern in the LOB. In principle, an HFT that learns this pattern could front-run the passive sell: buy ahead of the expected ask-side fill, then sell into the fill, making the fill adversely selected.

**Why this is not actionable for ST2.0:**
1. Paper models RFQ/dealer markets with discrete client tiers — fundamentally different from a continuous LOB crypto perp
2. At ST2.0's $30 margin / retail trade size, the pattern is below the noise floor for any HFT detection
3. Mitigation proposed (randomize quote timing, occasionally post two-sided) requires architectural changes inconsistent with ST2.0's one-direction signal structure
4. No empirical data: all results are from synthetic RFQ simulation

**Verdict: Interesting theoretical principle, not applicable at ST2.0's scale and market structure. Cannot be cited as an actionable finding.**

---

### arXiv:2605.19584 — "Online Market Making and the Value of Observing the Order Book"
**Authors:** Davide Maran, Marcello Restelli. May 2026. Accepted at COLT 2026 (Conference on Learning Theory).
**Type:** Theoretical (online learning / bandit theory). No empirical data.
**URL:** https://arxiv.org/abs/2605.19584

**Core finding:**

> "when a trade occurs, the trader's valuation remains hidden, whereas when no trade occurs, informative feedback about supply and demand is revealed"

The paper establishes that order book "no-trade" observations carry directional information about buyer valuations, and that an algorithm using this miss-feedback achieves O(√T) regret — substantially better than standard bandit approaches.

**Theoretical applicability to ST2.0:** Every PostOnly miss reveals that buyers were not aggressive enough to lift the ask at signal time. A sequence of misses implies absorption has ended; a sequence of fills implies it continues (and fills are therefore adversely selected). This is formally consistent with the DeLise Bernoulli model (N29): fills cluster when price is rising (adverse).

**Why this is not actionable for ST2.0:**
1. Paper's learning framework assumes adaptive spread choice across multiple price levels — ST2.0 posts at fixed best-ask (distance=0, confirmed optimal by Fabre & Ragel, N30)
2. The instrumentation gap identified in the synthesis is the binding constraint: ST2.0 does not currently log the conditions at misses, so the miss-feedback signal cannot be extracted
3. Closing the instrumentation gap (logging ob/flow conditions at each PostOnly miss) was already identified as the highest-value next action in the N1 synthesis — this paper provides theoretical support for that recommendation but does not add a new tweak beyond what was already recommended

**Verdict: Theoretical support for the instrumentation-gap recommendation (log conditions at misses). Does not yield a new independent tweak.**

---

### arXiv:2605.06405 — "Funding-Aware Optimal Market Making for Perpetual DEXs"
**Authors:** Nam Anh Le (National Economics University, Vietnam). May 2026. Hyperliquid data.
**Type:** Theoretical HJB control with empirical calibration (Hyperliquid DEX — NOT Phemex CEX).
**URL:** https://arxiv.org/abs/2605.06405

**Calibrated funding half-lives:** ETH 5.56 hours, BTC 4.07 hours, SOL 2.31 hours on Hyperliquid. Funding mean-reverts on multi-hour timescales.

**Why not actionable for ST2.0:** Funding sign is stable over a 15-minute hold (half-life 2-6 hours >> 15 minutes), but the dollar impact at ST2.0's scale is negligible: 15 min / 480 min (funding interval) × 0.01% typical funding × $30 margin ≈ $0.000009 per trade. Below measurement error. DEX-only calibration; Phemex CEX funding dynamics may differ. Not actionable.

---

### VPIN Electronic Trading Hub (practitioner article, not primary research)
**URL:** https://electronictradinghub.com/vpin-and-real-time-order-toxicity-what-your-execution-stack-cannot-see-before-the-fill/

**Claimed threshold:** "sustained VPIN above 0.7 for 8 or more consecutive volume bars." **Explicit caveat in the article itself:** these are "practitioner-calibrated parameters" — not from academic studies. No original backtesting data provided. Author is a practitioner (Ariel Silahian), not an academic.

**Verdict: Unverifiable as a primary source. Cannot cite the 0.7 / 8-bar thresholds.** Consistent with N29 conclusion: no primary source with quantified VPIN adverse-selection reduction for crypto perps has been found across 33 nights.

---

### arXiv:2607.04221 — "A Limit Order Market with Uncertain Informed Trading Participation"
**Authors:** Umut Çetin, Mingwei Lin (London School of Economics). July 2026. Theoretical.
**Core finding:** "the distribution of informed trading participation affects the asymptotic shape of the limit order book. In particular, the effect is not summarized by the expected number of informed traders alone." Equilibrium price impact follows a power law whose exponent depends on the full distribution of informed trader count, not the mean.

**Verdict:** Pure theory, no data. No actionable implication for ST2.0 beyond the existing synthesis: fills cluster in high-information regimes (which is the adverse-selection problem already identified).

---

### arXiv:2606.05882 — "Market Informedness and Market-Maker Profitability"
**Authors:** Konrad Ochedzan, Nino Antulov-Fantulin (ETH Zurich / Aisot Technologies). June 2026. Agent-based simulation.
**Core finding:** "informed market order flow is particularly harmful when aggregate market informedness is low" (simulation result). But: "positive relationship between informedness and profitability" for *adaptive* market makers (using RL).

**Verdict:** Simulation only. Applies to learning, adaptive two-sided market makers — not to ST2.0's fixed-spread, single-direction passive sell with no rebate.

---

## What the Cancel-and-Reprice and Micro-Price Angles Yielded

**Cancel-and-reprice (dynamic order management):** No new academic paper found. The closest prior work remains the IEX D-Limit / CQI mechanism (covered in N30) which validates the Tweak 30 conditional-cancellation concept. The specific question of "when to cancel and repost at a new price level" is not studied for fixed-best-ask passive makers because reposting below best-ask would cross the spread and become a taker order. No new paper on this angle.

**Micro-price placement timing:** No new paper specific to crypto perps. The Stoikov micro-price (weighted mid using queue imbalance) has been implicit in prior nights' OFI/imbalance discussion. The practical question (use micro-price rather than best-ask as the placement reference) is moot for ST2.0: the paper by Fabre & Ragel (N30) confirmed best-ask placement is already fee-optimal at Phemex's 0% maker / taker fee schedule.

---

## New Forward-Testable Tweaks Tonight

**None.** No new empirically-verified tweak is added to the queue tonight. The two theoretical findings (arXiv:2508.20225 price-reading and arXiv:2605.19584 miss-feedback) provide theoretical support for:
- The existing instrumentation-gap recommendation (log ob/flow at every miss), originally from the N1 synthesis
- The randomize-timing principle, which is theoretically sound but not actionable at ST2.0's retail scale

These do not constitute new tweaks — they reinforce existing recommendations.

---

## Honest Caveats

1. **Literature saturation.** After 33 nights covering the major microstructure literature, the searches are converging. Papers surfaced tonight are predominantly: (a) theoretical with no crypto perp data, (b) for DEX or RFQ market structures not mapping to Phemex CEX, (c) already covered in prior nights. This is the expected outcome for a narrow, specific problem after exhaustive search.

2. **Cancel-and-reprice: genuinely not studied.** No academic paper on optimal cancel-and-reprice for fixed-spread passive makers in crypto perps was found in 33 nights. This is not a search failure — the reason is structural: once you post at best-ask (distance=0), there's no repricing that improves your position without crossing to taker. The only reprice option is to post further away (larger distance), which reduces fill probability and is suboptimal per Fabre & Ragel.

3. **VPIN remains unverified.** After 33 nights, no primary source with quantified VPIN threshold for adverse-selection reduction in crypto perp passive maker fills has been found. The practitioner "0.7 / 8 bars" threshold is explicitly stated as non-academic. Do not act on it.

4. **The binding constraint is still execution, not signal.** Nothing found tonight changes the synthesis bottom line: the passive short-reversion fill is structurally adverse-selected, and the path forward is (a) deploy priority tweaks 4, 6, 9, 10, 11, 12, 14 to collect tagged fills, and (b) close the instrumentation gap on misses. No amount of theoretical literature changes what the data will say once logged.

---

## Cumulative Forward-Test Queue (39 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N32): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweaks added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a).

---

## Night 33 Bottom Line

Exhaustive search across six untried angles (micro-price placement, cancel-reprice dynamics, VPIN thresholds, post-fill alpha decay, price-reading / skew-sniffing, miss-feedback value) yielded no new empirically-verified actionable tweak. Five papers fetched and evaluated — all theoretical, DEX-specific, or RFQ-specific; none provide new quantified findings for Phemex CEX passive maker execution at retail scale. The two closest to new: arXiv:2508.20225 (Barzykin et al., Paris Dauphine/HSBC, price-reading / skew-sniffing — RFQ theory only, below ST2.0's detection threshold) and arXiv:2605.19584 (Maran & Restelli, COLT 2026, miss-feedback signal — theoretically supports instrumentation-gap priority but yields no new independent tweak). VPIN threshold remains unverified after 33 nights. Literature for this specific problem appears substantially saturated.

**Recommendation unchanged:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Close instrumentation gap (log ob/flow conditions at every PostOnly miss). Night 33: 39 tweaks queued, 0 deployed.
