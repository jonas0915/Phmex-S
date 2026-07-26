# ST2.0 Execution Optimization — Night 29
**Date:** 2026-07-26 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 28 Nights

N28 closed with: arXiv:1707.01167 (Gonzalez & Schervish, ABSTRACT ONLY — optimal LOB-conditional cancellation, Tweak 30), cancel-side OFI from Cont/Lu/Sitaru (PARTIALLY VERIFIED via practitioner sources — Tweak 30a). Tonight searched four angles not previously covered: (1) microprice vs midprice placement for passive crypto perp makers, (2) explicit quantification of the Bernoulli fill probability model for resting sell orders, (3) LOB resilience / ask-side refill speed as an entry-timing signal distinct from depth snapshot, (4) real-time VPIN as an intraday gate for passive order placement.

**Summary of new material tonight:**
- arXiv:2407.16527 (DeLise, 2024, "The Negative Drift of a Limit Order Fill") — VERIFIED (HTML fetched directly). First paper in this series to give an explicit Bernoulli fill-probability model: P(fill | adverse move) ≈ 1.0, P(fill | non-adverse move) ≈ 0.018. Average post-fill drift for a resting sell order: approximately +0.45 ticks (upward, adverse). Confirms that ~98% of fills are in adversely-selected states. Treasury futures data — not crypto perps. New to this series.
- arXiv:1602.00731 (Xu et al., 2016, "Limit-order book resiliency after effective market orders") — ABSTRACT ONLY (PDF binary; abstract directly fetched). LOB resilience threshold: "spread and depth can return to sample average within 20 best limit updates" after a market order hit. Key asymmetry: "price resiliency behavior is dominant after aggressive market orders, while price continuation behavior is dominant after less-aggressive market orders." Chinese stocks. The "ask-side refill speed" concept is distinct from Tweak 24's ask_depth_fragility (static depth level) — this is a dynamic rate-of-recovery signal. New to this series.

**Confirmed near-misses tonight:**
- Microprice placement in crypto perps (arXiv:2307.04863 Fabre & Ragel) — HTML 404. Abstract confirmed it covers "optimal distance of placement" with crypto CEX data but specific quantitative findings were not extractable. Not actionable tonight.
- Real-time VPIN gate (VisualHFT practitioner post) — Directly fetched. Claimed threshold: "sustained VPIN above 0.7 for 8 or more consecutive volume bars." BUT: no quantified performance impact (bps saved), no crypto perp applicability stated. Practitioner-only, no academic support. Cannot forward-test without a performance claim to calibrate against.
- Bitcoin VPIN + price jumps (Kitvanitphasu et al., Research in International Business and Finance, Vol. 81C, 2026) — Abstract fetched. Confirms "VPIN significantly predicts future price jumps, with positive serial correlation observed in both VPIN and jump size." BUT: no specific threshold stated in available abstract; no passive order timing recommendations. Verification incomplete — supplementary data not accessible.
- arXiv:2607.01550 "Is Trend Still Your Friend?" (Kurth, Eisler, Rej, Bouchaud) — PDF binary; body content not extractable. Cannot verify quantitative claims. Blocked.
- SSRN 6344338 — 26th consecutive night blocked.
- SSRN 6693260 — 29th consecutive night blocked.

---

## Finding A — arXiv:2407.16527 VERIFIED: Bernoulli Fill Model — ~98% of Fills are Adversely Selected

**Source:** Timothy DeLise. "The Negative Drift of a Limit Order Fill." arXiv:2407.16527. Department of Mathematics and Statistics, Université de Montréal.
**URL:** https://arxiv.org/html/2407.16527v1
**Dataset:** 10-Year US Treasury Bond Futures (ticker TY), CBOT via Trading Technologies. Primary study: November 21, 2023, 6:00 AM–1:00 PM EST (1,683 orders). Backtesting: November 30, 2023, 8:00 AM–5:00 PM EST (576,670 events).

**Verified quotes (directly fetched from HTML):**

> "Buy order fills are accompanied by downward mid price movements and sell orders are accompanied by upward movements, on average."

> "The average drift in each case, which comes out to approximately −0.0065." [in price units; in tick terms: "𝐄̂ₜ[dₜ|f] = −0.45 ticks" (empirical), "𝐄ₜ[dₜ|f] = −0.48 ticks" (theoretical)]

> "P(f|D)=1" [fill probability given adverse move = 100%]

> "P(f|U)=P(f|M)=Rₓ≈0.018" [fill probability given non-adverse move ≈ 1.8%]

> "even good predictions have a correlation with the future mid price movement of only 15–25%"

**What this paper adds — the Bernoulli fill model:**

The paper formalizes what the 2026-06-20 synthesis established qualitatively: fills are adversely selected. DeLise's contribution is a precise Bernoulli fill-probability decomposition:
- When price moves adversely through the resting order: P(fill) = 1. Price runs through and crosses the order.
- When price does NOT move adversely: P(fill) = 0.018. Only 1.8% of non-adverse ticks result in a fill (random "incidental" fills — price touched the limit level for unrelated reasons and there happened to be a counterparty).

This means roughly:
```
Expected adverse fills ≈ 100% × P(adverse move)
Expected non-adverse fills ≈ 1.8% × P(non-adverse move)
```
Given any reasonable mix, ~98%+ of actual fills land in an adversely-selected state. The non-adverse 1.8% exists but is negligible.

**Why this is new relative to prior 28 nights:**

N1 synthesis (arXiv:2502.18625) established qualitatively that "orders with negative subsequent five-minute returns are highly likely to fill." DeLise quantifies this as a Bernoulli model: P(adverse fill) = 1.0, P(incidental fill) = 0.018. No prior night cited this specific paper or its Bernoulli model. The magnitude (0.45 ticks average upward drift for a resting sell) is the first fill-drift number in this series.

**What this means for ST2.0:**

The Bernoulli model has one concrete implication for order timing: the time between placement and fill carries information. An order filled in the first 1–2 cycles after posting (< 120s) is almost certainly an adverse fill — price ran through it quickly. An order that survives N cycles without filling has not been hit on adverse moves; if it eventually fills, it's marginally more likely to be the 1.8% incidental type. But the 1.8% base rate is so low that this "waiting advantage" is weak.

More precisely: the Bernoulli model implies that **extending the TTL does not rescue the expected adverse selection cost** — the rare non-adverse fills (1.8%) arrive randomly throughout the TTL, not preferentially late. Cancelling early when LOB worsens (Tweak 30's conditional cancellation) therefore does not reduce the rate of non-adverse fills meaningfully — it just reduces total fill count.

The only way to improve expected outcomes under the Bernoulli model is to improve P(adverse move | signal time) — i.e., gate entries on conditions where the probability of an adverse move is lower. This is exactly what the existing tweak queue (4, 6, 9, 10, 11, 12, 14) is testing.

**Forward-testable implication → Tweak 31 (shadow log, 2 lines):**

Log `time_to_fill_cycles` = number of main loop cycles elapsed between order placement and fill confirmation. After 30+ fills:
- Do "fast fills" (1–2 cycles, < 120s) have worse post-fill 30s returns than "slow fills" (3+ cycles)?
- If yes: add a "no fast fill" cancellation rule — if order fills within 1 cycle of posting, treat as an adverse-fill signal and tighten the next-entry cooldown.

This is implementable as a log on fill confirmation (2 lines). No gate until data confirms.

**Critical limitations:**
1. **Treasury futures, not crypto perps.** TY is highly liquid (CBOT), tightly quoted, with different tick structure than Phemex altcoin perps. The P=0.018 parameter is specific to this instrument and period — it may be higher or lower on thin altcoin perps.
2. **1 day of data** (primary study). Very small sample. The Bernoulli parameter estimates have wide confidence intervals.
3. **The model is symmetric** — it treats buy and sell orders equivalently. ST2.0 only places sell orders. The specific adverse-selection asymmetry for a short in a buy-absorbed book may differ from the symmetric model.
4. **No recommendations for reducing adverse selection** are given in the paper. The paper is descriptive, not prescriptive.
5. The paper was not peer-reviewed at time of search (arXiv preprint, July 2024).

---

## Finding B — arXiv:1602.00731 ABSTRACT ONLY: LOB Resilience "20 Updates" Threshold — Ask-Side Refill Speed as Continuation vs Reversion Signal

**Source:** Hai-Chuan Xu, Wei Chen, Xiong Xiong, Wei Zhang, Wei-Xing Zhou, H. Eugene Stanley. "Limit-order book resiliency after effective market orders: Spread, depth and intensity." arXiv:1602.00731.
**URL:** https://arxiv.org/abs/1602.00731
**Dataset:** Chinese stocks (specific stocks, exchange, date range not stated in accessible abstract).
**Access:** Abstract directly fetched. Full paper was binary PDF — body content not readable via WebFetch.

**Verified quotes (from abstract, directly fetched):**

> "the spread and depth can return to the sample average within 20 best limit updates"

> "The price resiliency behavior is dominant after aggressive market orders, while the price continuation behavior is dominant after less-aggressive market orders."

> "effective market orders produce asymmetrical stimulus to limit orders when the initial spreads equal to 1 tick."

**What this paper adds — aggressive vs less-aggressive distinction:**

The paper identifies that market order aggressiveness predicts which regime the book enters post-hit:
- **Aggressive market orders** (large, crosses spread, takes multiple levels) → book shows **resilience** (asks refill quickly → favors a short-reversion maker)
- **Less-aggressive market orders** (small, picks only the best ask, doesn't sweep) → book shows **continuation** (asks refill slowly, price continues → adverse for a short-reversion maker)

This is counterintuitive: it's the LARGE, AGGRESSIVE buys that produce resilience, not the small ones. The mechanism: large buys signal temporarily elevated demand; market makers see the hit and immediately refresh the ask at a higher price, closing the spread. Small buys, by contrast, represent persistent directional pressure in small increments — the continuation signal.

For ST2.0, which fires on buy absorption (sustained buy-side tape pressure), the relevant question is: are the buys triggering the signal large and aggressive (→ expect resilience, short favorable) or small and sustained (→ expect continuation, adverse for short)?

**Distinction from Tweak 24 (ask_depth_fragility):**

Tweak 24 captures the STATIC depth at the ask at signal time — a low-depth ask before entry means it's easier to run through. The LOB resilience signal here is DYNAMIC — it measures the RATE OF RECOVERY after buys deplete ask depth. A book that quickly rebuilds ask depth after each sweep is resilient (favorable); one that stays depleted is fragile/continuation (adverse). These are orthogonal measurements: a thin book (Tweak 24 fires) could still be resilient (ask rebuilds quickly) or not.

**Forward-testable implication → Tweak 31a (shadow log, 3–4 lines):**

At signal time, over the most recent K LOB updates, compute:
```python
# For each LOB update where ask depth at best decreased (a buy hit it):
# how many subsequent updates does it take to return to pre-hit level?
ask_refill_time_avg = mean(updates_to_refill for each depleted ask level)
ask_refill_fast = ask_refill_time_avg < THRESHOLD  # e.g., < 5 updates
```
Log `ask_refill_time_avg` at signal time. After 30+ fills: do adverse fills cluster when `ask_refill_time_avg` is high (slow refill → continuation) vs low (fast refill → resilience)?

If yes: adds orthogonal signal to Tweak 24. If no: collapses into Tweak 24 (static depth sufficient).

Implementation requires ws_feed.py to track LOB update timestamps per level — about 5–8 lines. Data is already available from existing L2 WebSocket feed.

**Critical limitations:**
1. **Abstract only.** "20 best limit updates" is from the abstract; the specific conditions (symbol, spread size, market regime) that determine this threshold are not visible. Cannot calibrate to Phemex tick structure.
2. **Chinese stocks, 2016.** Different participant mix, tick structure, and HFT presence than Phemex altcoin perps 2026.
3. **Full paper not read.** The precise definition of "aggressive" vs "less-aggressive" market order is not available from the abstract. The ST2.0 context (buy absorption = sustained tape, possibly a mix) may not map cleanly to the paper's categories.
4. **Complementarity with Tweak 30a (cancel-side OFI) is not quantified.** Cancel-OFI (N28) measures sellers withdrawing; resilience measures sellers returning. These could be combined but their joint predictive content on crypto perps is unknown.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 31 | **Time-to-fill log.** On fill confirmation, log `time_to_fill_cycles` = cycles elapsed since placement. After 30+ fills: do 1–2 cycle fills have worse post-fill 30s returns than 3+ cycle fills? If yes: tighten next-entry cooldown after fast fills. | arXiv:2407.16527 DeLise 2024 (Treasury futures, abstract + HTML verified — NOT crypto perp; P=0.018 non-adverse fill rate is instrument-specific) | Queued — log only | 2 lines |
| 31a | **Ask-side refill rate log.** Over the K most recent LOB updates, compute mean updates-to-refill per depleted ask level. Log at signal time. After 30+ fills: do adverse fills cluster at high (slow) refill time? If yes: adds signal orthogonal to Tweak 24. | arXiv:1602.00731 Xu et al. 2016 (ABSTRACT ONLY, Chinese stocks — not crypto perp; 20-update threshold not calibrated) | Queued — log only | 5–8 lines |

---

## Honest Caveats

1. **Finding A (arXiv:2407.16527):** HTML fetched, quotes are direct. BUT: 1 day of Treasury futures data, preprint, symmetric model. The P=0.018 parameter cannot be assumed for Phemex altcoin perps. The drift magnitude (+0.45 ticks) translates to different bps depending on spread and tick size per symbol. Do not hardcode these numbers as Phemex calibrations.

2. **Finding B (arXiv:1602.00731):** Abstract fetched directly; full paper not readable (PDF binary). The "20 best limit updates" threshold and the aggressive/less-aggressive distinction are from the abstract only. Full methodology, asset details, and precise definitions are unknown. The counterintuitive direction (aggressive buys → resilience, not continuation) is interesting but requires primary paper access to validate the mechanism.

3. **The Bernoulli model implication is constraining, not liberating.** If P(non-adverse fill) = 0.018 holds on Phemex, it means the rate of "good fills" is so low that execution tweaks which only shift timing (faster/slower orders) cannot materially improve expected adverse selection — only signal-level gating (not posting in the first place when adverse selection probability is high) can help. This reinforces the existing priority queue (Tweaks 4, 6, 9, 10, 11, 12, 14) over timing tweaks (31, 31a).

4. **Microprice placement angle remains uncovered.** Fabre & Ragel (arXiv:2307.04863) returned HTML 404. This paper studied "optimal distance of placement" with crypto CEX data and may have quantitative depth-offset findings. Retry in a future night with alternate URL.

5. **31 tweaks queued, 0 deployed across 28 nights (plus 2 tonight = 33 queued).** Recommendation unchanged since N20: implement priority tweaks 4, 6, 9, 10, 11, 12, 14 first. Each is 2–5 lines. The limiting factor is data collection — none of the queued tweaks can be decided on without 30+ tagged fills per variable. Continuing research before implementation does not close this gap.

6. **SSRN 6344338 blocked** (26 consecutive nights). **SSRN 6693260 blocked** (29 consecutive nights). No new access route.

---

## Cumulative Forward-Test Queue (33 Tweaks)

Priority tweaks (unchanged from N20–N28): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweaks 31, 31a added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), above (Tweaks 31, 31a).

---

## Night 29 Bottom Line

Two findings. Finding A (arXiv:2407.16527, DeLise 2024, VERIFIED via HTML): explicit Bernoulli fill-probability model for resting sell orders — P(fill|adverse move)=1.0, P(fill|non-adverse move)=0.018. Average post-fill drift = +0.45 ticks (upward, adverse for a resting sell). The model implies ~98% of fills are adversely selected. Forward-testable as Tweak 31 (log time-to-fill-cycles at fill confirmation; test whether fast fills have worse post-fill returns). Critical limitation: 1 day of Treasury futures data — P=0.018 is not calibrated to Phemex. Finding B (arXiv:1602.00731, Xu et al. 2016, ABSTRACT ONLY): LOB resilience after market orders returns to baseline within "20 best limit updates"; aggressive buys produce book resilience (ask refills fast → favorable for short) while less-aggressive buys produce continuation (ask stays thin → adverse for short). Forward-testable as Tweak 31a (log ask-side refill rate — distinct from Tweak 24's static depth snapshot). Critical limitation: abstract only, Chinese stocks.

**Recommendation unchanged from N20–N28:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweaks 31 and 31a are each 2–8 lines and can be added in the same session. Night 29: 33 tweaks queued, 0 deployed.
