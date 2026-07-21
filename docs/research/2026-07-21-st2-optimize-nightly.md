# ST2.0 Execution Optimization — Night 25
**Date:** 2026-07-21 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 24 Nights

N24 closed with: arXiv:2307.04863 (savings function) fully verified, arXiv:2607.09230 (L2 hierarchy) new, hftbacktest price-displacement cancel pattern, and SSRN 6693260 (ask depth fragility) still blocked. Tonight ran 4 new search angles: iceberg/hidden liquidity detection, ML adverse selection classifiers for crypto, conditional cancel triggers from aggressive tape flow, and new 2026 perp execution papers.

**Summary of new material tonight:**
- arXiv:2606.15715 (Barone & Lillo, June 2026) — new Hyperliquid paper, directly readable, VERIFIED. Adverse selection costs for passive (hidden) orders are quantifiably higher when visible sustained directional flow is present on the same side. Indirect but directionally applicable to ST2.0.
- SSRN 6344338 (Rajendran & Singaravelu) — confirmed this is the same paper previously blocked 22 consecutive nights (also indexed as SSRN 6551572). STILL blocked (HTTP 403 on both SSRN PDF and ResearchGate). Detailed claims from search result summaries cannot be verified from primary source.
- Iceberg detection (ClearEdge, practitioner piece) — not academic, no verifiable statistics, not applicable to ST2.0.
- arXiv:2505.12465 (RL market making with latency) — RL paper for high-frequency market making at 30-100ms latency; does not address passive directional order placement at ST2.0's timescale.

**Confirmed repeats from prior nights:**
- arXiv:2602.00776 (Casas et al., covered N18), arXiv:2409.12721 (CME adverse fills, N23), arXiv:2307.04863 (covered N24)

---

## Finding A — arXiv:2606.15715 VERIFIED: Visible Sustained Flow → Higher Adverse Selection for Hidden Passive Fills

**Source:** Davide Barone, Fabrizio Lillo (Scuola Normale Superiore, Pisa). "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid." arXiv, June 2026.
**URL:** https://arxiv.org/abs/2606.15715 (HTML: https://arxiv.org/html/2606.15715v1)
**Dataset:** 201 Hyperliquid perpetual futures markets, July 28, 2025 – March 23, 2026. 641 million fills (~365 million market orders, $1.93 trillion traded volume). 4.3 million reconstructed statistical metaorders and 465,000 visible TWAP executions with address-level attribution.

**Verified quotes:**

> "visible TWAP programs elicit liquidity provision: while active, displayed depth rises and the book tilts toward the absorbing side" (Abstract)

> "visible TWAPs face lower execution costs than comparable hidden metaorders and leave a smaller permanent price impact" (Abstract)

> "hidden metaorders executed alongside already-visible same-direction TWAP flow incur higher permanent costs" (Abstract)

> "a 10 percentage point increase in already-visible same-side TWAP dominance" associates with approximately 0.84–0.92 basis points higher permanent cost for hidden orders (Section 4.3, Table 3)

**What this is about:**
The paper compares two execution modes for LARGE institutional orders on Hyperliquid: (a) disclosed TWAP programs (publicly broadcast order schedules, visible to the whole market), and (b) hidden metaorders (reconstructed statistically from fills). The disclosed orders attracted liquidity provision — the book deepened toward the absorbing side — while hidden orders in the presence of competing visible same-direction flow paid more in adverse selection costs.

**What this means for ST2.0 (indirect, requires careful translation):**

The direct mechanism — disclosure attracting protective depth — does not apply to ST2.0, which is a small passive limit order, not a large TWAP program. However, the finding encodes a directional insight about tape composition:

When the tape is dominated by visible, sustained, large-notional buying (the signature of a disclosed institutional TWAP or equivalent programmatic execution), the dominant buyers have attracted protective liquidity provision on their side. This means:
1. The bid side fills are MORE competitive (depth is deeper, quote updates are faster in response to the visible flow)
2. Passive shorts resting into this bid are MORE likely to be adversely selected — they are being filled by the same large buyers who are permanently moving price

**Operationally for ST2.0:** This is a directional confirmation of what Tweak 4 (`tape_max_single_trade`) was designed to detect. If the tape around signal time shows a **sustained sequence of large, uniformly-spaced buy prints** (as opposed to sporadic absorption), this is the adverse regime — the buying is programmatic/institutional, not a squeeze that will revert. The Tweak 4 log (`tape_max_single_trade` at signal time) is the right first-order proxy for this. Larger max single trade → more likely to be institutional, programmatic, and permanent rather than speculative and reverting.

**Critical limitations:**
- The paper studies large institutional orders on Hyperliquid, not small passive maker fills on Phemex. The mechanism (disclosure attracting protective depth) is specific to large orders with disclosed schedules — inapplicable to ST2.0's scale.
- Hyperliquid is fully on-chain (public address-level attribution), which is unique and not directly comparable to Phemex's opaque order flow.
- The paper does not study passive fill-level adverse selection for small resting orders — it studies execution costs for large metaorders. The translation to ST2.0 is one inference step removed.
- Quantified impact (0.84–0.92 bps per 10pp TWAP dominance increase) cannot be imported as a Phemex calibration — different venue, scale, and mechanism.

---

## Finding B — SSRN 6344338/6551572 (Rajendran & Singaravelu): STILL BLOCKED — Status Clarification

**Source:** Suresh Rajendran, Divya Singaravelu. "Predicting Adverse Selection in High-Frequency Cryptocurrency Markets Using Gradient Boosting." SSRN, March 2026.
**URLs:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6344338 and https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6551572

**Access:** HTTP 403 on SSRN PDF delivery link (6551572 delivery URL blocked) and HTTP 403 on ResearchGate. **UNVERIFIED — primary source not read on any night.**

**Clarification:** Tonight's search confirmed that SSRN 6344338 and SSRN 6551572 resolve to the **same paper** — the 6551572 index entry that appeared promising in tonight's search results is not a second paper or a newer version. The 22-night block on 6344338 also blocks 6551572. No new route found.

**What the search result SUMMARIES claim (UNVERIFIED — not from primary source):**
- LightGBM model trained on 31,081,463 second-level observations of BTC/USDT perpetual futures on Bybit, February 2025 – February 2026
- Dual-output model: toxicity classifier + quantile regressor → composite "TailScore"
- Toxicity label: seconds where strong directional order flow is followed by sustained price continuation over 5-second horizon (rolling quantile threshold, 1-hour lookback)
- Out-of-sample ROC-AUC: 0.668–0.921 monthly across 360 days
- CVaR99 efficiency at 0.1% gate: 25.85x (ETH/USDT: 27.50x)
- Toxicity rates ranged from 0.081% (September 2025) to 0.795% (February 2025)

These claims are ENTIRELY derived from WebSearch AI summaries, not direct paper access. Do not implement any gate derived from these claims until the full text is read. The paper remains the single most directly applicable blocked source across the entire 25-night research series.

---

## New Forward-Testable Tweaks Tonight

No new tweaks added. Finding A (Barone & Lillo, Hyperliquid) provides directional confirmation that **Tweak 4 is correctly oriented** (`tape_max_single_trade` at signal time). It does not suggest a new logging variable — it reinforces the priority of implementing Tweak 4 before any more complex tape analysis.

**Revised priority framing:**
- Tweak 4 (`tape_max_single_trade`) is the single most actionable pre-entry tape diagnostic given Finding A
- The visible-vs.-programmatic buying distinction can only be empirically assessed once Tweak 4 data is collected: sustained high `tape_max_single_trade` → likely institutional/TWAP-like → permanent impact → more adverse. Sporadic normal sizes → speculative absorption → reversion candidate

---

## Honest Caveats

1. **Night 25 produced one verified new paper (Finding A, Hyperliquid).** Its findings are indirect for ST2.0's problem shape. They confirm existing priority direction (Tweak 4) but do not add new variables to the queue.

2. **The Rajendran ML classifier (SSRN 6344338/6551572) remains the single most directly applicable blocked paper** in the 25-night series. It has now been blocked on 23 consecutive nights with no accessible route found. If this paper becomes accessible (author contact, academia.edu, ResearchGate access change), reading it should be the immediate priority.

3. **Iceberg detection literature does not apply to ST2.0.** The practitioner piece (ClearEdge) identified detection heuristics for hidden bids (repeated fills at same price, instant depth replenishment) but provided no verified data on how iceberg buying correlates with adverse passive short fills. The academic iceberg detection paper (arXiv:1909.09495, CME, 2019) predates crypto perp microstructure and is venue-specific to CME equity futures.

4. **No new cancellation trigger angle found tonight.** The aggressive-tape-flow cancel trigger angle produced no academic or practitioner sources beyond what was covered in N6, N17, and N24 (the hftbacktest price-displacement cancel pattern).

5. **The three persistent literature gaps remain unresolved after 25 nights:** optimal cancel TTL, LOB depth replenishment speed, optimal placement depth inside the spread for crypto perp altcoin markets.

6. **26 tweaks queued, 0 deployed across 25 nights.** The binding constraint is unchanged: empirical data from live shadow-logging, not knowledge. Priority tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines of code and have been queued for 3–7 weeks. Tweak 4 is elevated to highest priority based on Finding A tonight.

---

## Cumulative Forward-Test Queue (26 Tweaks, unchanged)

Priority tweaks (adjusted priority after Finding A): **4 [elevated], 6, 9, 10, 11, 12, 14**
Full queue: see N22 report (Tweaks 1–22) + N23 (Tweak 23) + N24 (Tweaks 24, 25, 26)

---

## Night 25 Bottom Line

One new verified paper found tonight (Barone & Lillo, arXiv:2606.15715, Hyperliquid June 2026). Its direct finding — that adverse selection costs for hidden passive fills are higher when visible sustained same-direction flow is present — is an indirect confirmation that sustained programmatic buying (institutional TWAP-like tape) is the highest-adverse-selection entry context for ST2.0's passive short. Tweak 4 (`tape_max_single_trade` logging) is the correct first-order diagnostic for this regime. No new tweaks added.

**The research series recommendation from N22-N24 remains: implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Do not continue adding nights to the queue before collecting 30+ tagged fills per diagnostic variable.** Night 25 marks 25 nights of research, 26 tweaks queued, 0 deployed.
