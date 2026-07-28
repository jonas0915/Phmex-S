# ST2.0 Execution Optimization — Night 31
**Date:** 2026-07-28 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 30 Nights

N30 closed with: arXiv:2307.04863 Fabre & Ragel (confirmed ST2.0 best-ask placement already optimal), arXiv:2607.09426 Hansen et al. (quarter-hour burst effect, Tweak 32). Tonight searched four angles not previously covered: (1) VPIN/flow toxicity thresholds for passive order gating in crypto perp futures, (2) composite L2 state vs individual order-flow features as adverse selection predictors, (3) funding payment window (00:00/08:00/16:00 UTC) microstructure effects on spread and fill quality, (4) cross-asset order flow spillover (BTC leading altcoin perp timing).

**Summary of new material tonight:**

- arXiv:2607.09230 (Jeon, July 2026, "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures") — VERIFIED via HTML fetch. Binance USDT perpetual futures (BTCUSDT, ETHUSDT), January 2023 through mid-2026. Core finding: **the pre-event L2 composite state is the primary predictive object** for post-event liquidity transitions; order flow adds value only as an overlay on top of the L2 state, not independently. Critical asymmetry: for ETH, order flow increments are present in all regimes and amplify in stressed states (+0.030 to +0.038 in stressed vs +0.004 in calm); for BTC, order flow adds near-zero incremental value. State operationalized as tercile-based composite score (0–3) from spread, depth, and imbalance. New to this series.

**Confirmed near-misses tonight:**
- VPIN academic papers (arXiv search): Kitvanitphasu et al. 2026 paywalled (seen in N29); VisualHFT practitioner thresholds (VPIN > 0.7 / 8 bars) lack quantified performance impact — already classified as unverifiable in N29. No new primary source found on VPIN with quantified adverse-selection reduction for crypto perps.
- Funding window microstructure (MDPI 2227-7072/14/5/103 and 2227-7390/14/2/346) — both returned HTTP 403 Forbidden; primary source content not accessible. Search snippets mention "spreads peaking approximately two hours after standard settlement times" — **UNVERIFIED, cannot cite as fact.**
- Cross-asset lead-lag (OFR working paper, arXiv:2511.00390 DeltaLag) — search snippets found, primary sources not fetched. No verifiable quantitative claim available for altcoin perp maker timing.
- arXiv:2606.08573 (funding rate design) — fetched directly; purely theoretical BSDE mathematics paper, no empirical content on order flow patterns. Dead end.

---

## Finding A — arXiv:2607.09230 VERIFIED: Composite L2 State Dominates Order Flow for Crypto Futures; ETH-Specific Stress Amplification

**Source:** Joohyoung Jeon. "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures." arXiv:2607.09230v1. Submitted July 10, 2026.
**URL:** https://arxiv.org/html/2607.09230v1
**Dataset:** Binance USDT-margined perpetual futures. Assets: BTCUSDT, ETHUSDT. Date range: January 2023 through mid-2026. Data: top-20 L2 order book sampled once per minute + aggregate trade-flow + calendar of scheduled macroeconomic announcements. Sample: "47,513 windows per horizon, 18,631 of them event windows (BTC 9,330, ETH 9,301) against 28,882 matched non-event windows, from 9,773 unique scheduled events across 40 monthly folds."
**Access:** HTML version directly fetched. arXiv preprint (not peer-reviewed). Solo author, no stated institutional affiliation on abstract page.

**Verified quotes (directly fetched from HTML):**

> "The pre-event L2 liquidity state is the primary predictive object"

> "Order flow provides further incremental value only when layered on top of the L2 state model, not as a replacement."

> "A contract-minute is then assigned to a level by an equal-weight count of how many of the three oriented descriptors fall in their top tercile."

> "calm, mixed, and stressed in shares of about 0.21, 0.54, and 0.25"

> "For ETH the order-flow value is present in every regime and grows with liquidity stress" [calm: +0.004, mixed: +0.015 to +0.020, stressed: +0.030 to +0.038 improvement]

> "For BTC the regime decomposition does not establish an order-flow increment."

> "Only one of the six BTC cells clears its null, the five-minute calm regime"

> "This is a prediction study of liquidity-state transitions at a one-minute cadence, not a trading or execution study, and reports no policy, profit, or simulator result."

**What this paper establishes for ST2.0:**

The paper's composite L2 state (score 0–3, counting how many of three descriptors — spread, depth-negated, imbalance — fall in their top tercile simultaneously) is the primary predictor of post-event liquidity regime. Individual flow features only add value conditioned on this state.

Three implications for ST2.0:

**1. State-first design principle.** ST2.0 already uses individual components of the L2 state: ob.imbalance gate (±0.25) and tape buy_ratio gate (0.45/0.55). But these are individual thresholds applied independently. The paper's finding is that the *composite count* (how many simultaneously stressed?) predicts post-signal regime more strongly than any single component. An absorption signal firing when ALL THREE L2 descriptors are simultaneously in stressed territory is a qualitatively different regime from one where only one is. This composite hasn't been tracked or logged in ST2.0.

**2. ETH-like altcoins: stressed state amplifies order flow signal, but at cost.** For ETH (most similar participant structure to major altcoin perps), order flow is most predictive in the stressed regime (all/most L2 descriptors stressed). ST2.0 fires on buy absorption — which IS concentrated order flow. This means ST2.0's signal fires most reliably in EXACTLY the conditions the paper identifies as highest order-flow predictiveness. But this is double-edged: stressed L2 state means thin depth, wide spread, and high imbalance — precisely the conditions where, per DeLise (N29), an adverse move is most likely to run through the resting sell order. The paper does not resolve this trade-off because it studies prediction, not execution outcomes.

**3. BTC: order flow near-worthless on top of L2 state.** For BTC signals in ST2.0, the book shape is essentially the entire signal; the tape/flow overlay adds negligible incremental predictive value per this paper's framework. If ST2.0 fires on BTC, the order flow component (buy_ratio, cvd) is doing less work than believed.

**What this does NOT address:**

The paper is explicitly a prediction study of liquidity-state transitions, not a passive fill adverse selection study. It shows that composite L2 state predicts post-event liquidity regime (spread/depth/imbalance outcomes), not the adverse selection cost of a resting maker fill. The connection to ST2.0 adverse selection is inferred, not measured.

**Forward-testable implication → Tweak 33 (shadow log, 4–6 lines):**

At signal time, compute and log the composite L2 stress score:

```python
# At signal time — using already-available ob snapshot
spread_pct = (ob["best_ask"] - ob["best_bid"]) / ob["mid_price"]
# Use rolling 1000-bar estimates for tercile thresholds (or hardcode from data)
stress_score = 0
if spread_pct > SPREAD_P67:      # spread in top tercile
    stress_score += 1
if ob_total_bid_depth < DEPTH_P33:  # depth in bottom tercile (negated)
    stress_score += 1
if abs(ob["imbalance"]) > IMBALANCE_P67:  # imbalance magnitude in top tercile
    stress_score += 1
# stress_score: 0 = calm, 1 = mixed, 2–3 = stressed
```

Log `l2_stress_score` (0–3) alongside fill/miss/adverse outcome. After 30+ fills:
- Do adverse fills cluster at `l2_stress_score` ≥ 2?
- Do missed entries (PostOnly cancelled) cluster at any specific score?
- Cross-reference with Tweak 32 (QH burst) and Tweak 24 (ask_depth_fragility): does composite score add information beyond individual components?

If adverse fills cluster at score ≥ 2: candidate gate (block entry when all three L2 descriptors are simultaneously stressed). If adverse fills do NOT cluster by stress score: confirms individual components are sufficient.

Tercile thresholds: can be estimated offline from existing `trading_state.json` entry snapshots (ob fields are stored) or set conservatively from order-of-magnitude expectations (e.g., spread_p67 ≈ 2× typical bid-ask, imbalance_p67 ≈ 0.35).

**Critical limitations:**
1. Paper is a preprint (July 10, 2026), solo author, not peer-reviewed. Not yet independently replicated.
2. Dataset is BTCUSDT and ETHUSDT Binance perp — neither is ST2.0's primary altcoin universe (INJ, AVAX, ARB, etc.). The composite state thresholds (tercile breaks) would need to be re-estimated per symbol on Phemex.
3. Paper does not measure passive fill adverse selection — connection to ST2.0 adverse selection cost is inferred, not measured.
4. "Order flow matters more in stressed states" could cut either way for ST2.0: signal is stronger, but so is adverse selection. The paper cannot tell us which effect dominates for a passive short.
5. Top-20 LOB sampled once per minute — ST2.0 evaluates per 60s cycle, which matches, but intrabar dynamics (sub-minute) are not captured.

---

## Unverified Claims (Cannot Cite as Fact)

**Funding window spread peaks:** Multiple search snippets claim "spreads peak approximately two hours after standard settlement times" (00:00/08:00/16:00 UTC → peaks near 02:00/10:00/18:00 UTC) for crypto perp futures. **Primary sources (MDPI papers 2227-7072/14/5/103 and 2227-7390/14/2/346) returned HTTP 403 Forbidden — content not accessible.** This claim cannot be cited. If true, it would be a new timing gate for ST2.0 (avoid entries 1–2 hours post-funding settlement). Marked for retry on a future night.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 33 | **Composite L2 stress score log.** At signal time, compute the tercile-based count of simultaneously stressed L2 descriptors (spread, depth, imbalance). Log `l2_stress_score` (0–3) alongside fill/miss/adverse outcome. After 30+ fills: do adverse fills cluster at score ≥ 2? If yes: candidate gate. Cross-reference with Tweaks 24, 32. | arXiv:2607.09230 Jeon July 2026 (Binance perp BTC+ETH, Jan 2023–mid-2026 — NOT Phemex altcoin; preprint, not peer-reviewed; paper studies liquidity-state predictions, not passive fill adverse selection directly) | Queued — log only | 4–6 lines |

---

## Honest Caveats

1. **Single verified finding tonight.** VPIN, funding window, and cross-asset lead-lag angles all produced either paywalled papers, 403 blocks, or practitioner claims without academic support. Night 31 yields one new tweak (33) from one verified primary source. This is lean but honest — one solid, verified finding beats five unverifiable claims.

2. **arXiv:2607.09230 is brand new (July 10, 2026) and not peer-reviewed.** The state-first design principle is well-motivated theoretically, but the specific quantitative improvements (+0.030–0.038 in stressed ETH regime) are unpublished results from a solo-authored preprint. Cross-asset extrapolation from BTCUSDT+ETHUSDT Binance perp to Phemex altcoin perp universe requires per-symbol recalibration.

3. **Funding window claim is UNVERIFIED.** Do not act on it. Mark MDPI papers (2227-7072/14/5/103, 2227-7390/14/2/346) for retry on a future night via a different access route.

4. **The composite state framing is new, but the individual components are not.** Imbalance (±0.25 gate) and buy_ratio (0.45/0.55 gate) are already in ST2.0's entry logic. Tweak 33 adds the composite stress count — which measures simultaneous extremity across all three — not a replacement for existing gates.

5. **37 tweaks queued, 0 deployed across 31 nights.** Recommendation unchanged from N20–N30: implement priority tweaks 4, 6, 9, 10, 11, 12, 14 first. Tweak 33 is a log-only diagnostic, 4–6 lines, can be added in the same session as priority tweaks.

6. **SSRN 6344338 blocked** (28 consecutive nights). **SSRN 6693260 blocked** (31 consecutive nights). No new access route.

---

## Cumulative Forward-Test Queue (37 Tweaks)

Priority tweaks (unchanged from N20–N30): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweak 33 added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), above (Tweak 33).

---

## Night 31 Bottom Line

One verified finding. arXiv:2607.09230 (Jeon, July 10 2026, Binance USDT perp, BTC+ETH, Jan 2023–mid-2026, VERIFIED via HTML): the composite L2 state (tercile-based count of simultaneously stressed spread/depth/imbalance descriptors) is the primary predictive object for post-signal liquidity transitions — more informative than individual order-flow features alone. For ETH-like assets, order flow amplifies predictiveness in stressed states (+0.030–0.038 vs +0.004 in calm); for BTC, order flow adds near-zero value on top of L2 state. Forward-testable as Tweak 33 (log composite L2 stress score 0–3 at signal time; check if adverse fills cluster at score ≥ 2). Critical limitations: preprint, solo author, Binance BTC+ETH only, paper explicitly studies prediction not execution. Funding window spread-peak claim (MDPI sources): UNVERIFIED — primary sources returned 403.

**Recommendation unchanged from N20–N30:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweak 33 is 4–6 lines (log only). Night 31: 37 tweaks queued, 0 deployed.
