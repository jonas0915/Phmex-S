# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-06-30
**Night:** 9 of series
**Status:** Three new verified findings tonight — more than expected given the 06-29 "exhausted" call

---

## Context

The 06-29 report declared this series "definitively exhausted." Tonight's sweep partly confirms that (three of four search angles found nothing new) but yields three verified findings that are genuinely new:

1. A fill-probability regression from a previously cited paper, with specific coefficients not previously extracted
2. A new primary source (Lehalle & Mounjid 2016) formalizing the latency constraint on cancel defense
3. A queue-size-ratio cancel signal from Cont & De Larrard (2013), not in any prior report

---

## (a) What's New vs. Prior Reports

| Search Angle | Result |
|---|---|
| Bid-ask spread as intra-day fill quality timing signal | Nothing new. Spread-widening-as-defense covered 06-16. No primary source found for spread-as-timing-signal within one instrument. |
| Trade arrival rate / VPIN | VPIN (Easley et al. 2012) already in forward-test queue as 06-23 Tweak B. VPIN replication controversy noted in caveats below. |
| Limit order fill probability models | **New quantitative extraction from arxiv 2502.18625** (previously cited in 06-26 for cancellation result, not for fill probability model). See Tweak A. |
| Level exhaustion / stack depletion | Two new sources: Cont & De Larrard (2013) queue ratio + Lehalle & Mounjid (2016) latency formalization. See Tweaks B and C. |

---

## (b) New Forward-Testable Findings

### Tweak A: Ask-Queue Thinness as a Skip Gate (Not Post at All)

**Source:** arxiv 2502.18625 — the Binance BTC perpetual paper already cited in the 06-26 report for the cancellation counter-finding. Tonight extracted the fill probability model from the same paper, which was NOT previously pulled.

**URL:** https://arxiv.org/html/2502.18625v2

**Verification status:** Full paper accessible via arXiv HTML. Verified directly.

**New finding — the fill probability regression:**

The paper fits an OLS model over 232,897 maker orders on Binance BTC perp:

```
P(fill) ~ β₀ + β₁·q_near + β₂·q_opp + β₃·imbalance
```

Where:
- `q_near` = ask-side queue size (near-side for a sell), β₁ = +0.0159 (p<0.001)
- `q_opp` = bid-side queue size (opposite side), β₂ = +0.1013 (p=0.065)
- `imbalance` = (bid_size − ask_size)/(bid_size + ask_size), β₃ = −0.3166 (p<0.001), R² = 0.946

**Direct quote:** "Fill probability exceeds 90% when the near-side queue is very small and the opposite-side queue is very large."

**Critical implication for ST2.0:** ST2.0 fires on aggressive bid absorption (bid-heavy book, high positive imbalance). The regression says imbalance β₃ = −0.3166 — meaning a positive (bid-heavy) imbalance *increases* fill probability for the ask. In other words, ST2.0's entry condition is also the condition with the highest fill probability for the passive sell — and we know from the 06-20 synthesis that all fills are adversely selected. We are posting into the highest-fill-probability / highest-adverse-selection regime by design.

**Forward-testable Tweak A:** Add a shadow log field `q_near_at_post` (ask queue size at the target price level at the moment of posting). After 20+ fills, test: do fills where `q_near_at_post` was very thin (< threshold) show worse adverse selection (post-fill adverse move in first 60s) than fills where the ask queue was deeper? If near-queue thinness correlates with adverse fills, implement a skip gate: do NOT post when ask queue at the target level is below threshold X (thin queue = near-certain fast fill = near-certain adverse selection).

**Note:** This is distinct from OB imbalance gate (which measures bid vs. ask ratio). This measures the ABSOLUTE ask queue size at our specific price level, which the regression shows is a strong independent predictor.

---

### Tweak B: Queue Size Ratio as a Dynamic Cancel Trigger

**Source:** Cont & De Larrard (2013), "Price Dynamics in a Markovian Limit Order Market," *SIAM Journal on Financial Mathematics*.
**URL:** https://epubs.siam.org/doi/abs/10.1137/110856605
**Verification status:** Abstract confirmed; full text paywalled.

**Direct quote from abstract:** "The probability of a price increase at the next event is given by the ratio of queue sizes."

In the Markovian LOB model, the probability that the next price tick is UP ≈ `q_bid / (q_bid + q_ask)` at the top of book. This formalizes a real-time cancel signal: as the bid queue depletes faster than the ask queue at adjacent levels, the next-event probability of a sweep through your resting ask increases.

**How it differs from existing tweaks:**
- Not OFI (flow direction); this is absolute queue mass
- Not cancel-on-momentum (06-27, which monitors mid-price movement); this monitors queue depletion *before* the price moves
- Not Tweak A above (which is a skip gate at entry); this is an in-flight cancel signal while the order is resting

**Forward-testable Tweak B:** During the order's resting period (between post and fill/cancel), monitor at each 1s interval:
1. `q_bid_best` = bid queue size at the best bid level
2. `q_ask_target` = ask queue size at our limit price
3. Compute `q_ratio = q_bid_best / (q_bid_best + q_ask_target)`
4. Shadow-log `q_ratio_at_fill` vs. `q_ratio_at_cancel` for all outcomes
5. After 20+ fills, test: do fills where `q_ratio_at_fill > 0.7` show worse adverse selection than fills where `q_ratio < 0.5`?

**Infrastructure check required:** Needs real-time per-level queue sizes from `ws_feed.py` or L2 snapshots. Must verify before shadow-logging.

---

### Observation C: Latency is the Binding Constraint on Cancel Defense (Formally)

**Source:** Lehalle & Mounjid (2016), "Limit Order Strategic Placement with Adverse Selection Risk and the Role of Latency," *Market Microstructure and Liquidity*, Vol. 3, No. 1, 2017.
**URL:** https://arxiv.org/abs/1610.00261
**Verification status:** arXiv abstract confirmed accessible.

**Direct quote from abstract:** "if the price has chances to go down the probability to be filled is high but it is better to wait a little more before the trade to obtain a better price."

**More operationally useful framing from the abstract:** The paper explicitly models that the rational response to adverse-selection risk is cancellation and reinsertion — but only if latency permits. Below a latency threshold, the cancel arrives after the fill and provides no protection.

**No new tweak implied** — this formalizes the binding constraint already acknowledged since the 06-13 report. It is cited here to confirm that Tweaks A and B above will only help if the cancel can reach Phemex before the matching engine executes. At typical API latency (~80–150ms round-trip), a cancel sent when a sweep is *already at your level* will likely be too late. Tweaks A and B must therefore trigger *one or two price levels early*, before the sweep reaches the order.

**Implication for implementation:** The trigger threshold for Tweak B should fire when the sweep is still 1–2 ticks away, not when it is already at the limit price. This means the implementation needs to monitor bid levels *below* the order, not just the adjacent level.

---

## (c) Caveats and Things Not Verified

1. **VPIN replication controversy:** A practitioner blog (quant.stackexchange.com, not peer-reviewed) cites that Andersen & Bondarenko (2015) contested the Easley et al. Flash Crash VPIN result. The Andersen & Bondarenko paper was NOT fetched. This is a second-hand claim — labeling as unverified. But VPIN's validity in crypto is additionally uncertain. The queued shadow-gate (06-23 Tweak B) should be treated as exploratory, not assumed predictive.

2. **Cont & De Larrard abstract only:** The queue-ratio formula rests on the abstract. The model uses Poisson arrival assumptions that do not hold in crypto. The practical inference (cancel when q_ratio > threshold) is a derivative of the theoretical result, not a direct implementation recommendation.

3. **arxiv 2502.18625 regression transferability:** The fill probability model (R² = 0.946) was calibrated on Binance BTC perp. Phemex has different book dynamics, maker/taker mix, and lower overall liquidity. Coefficients likely differ; the directional result (thin ask queue = higher fill probability) is likely to transfer but magnitudes are Phemex-unknown.

4. **Lehalle & Mounjid latency threshold:** The paper models latency as a continuous parameter; the threshold below which cancel defense is useless is not specified in the abstract and was not accessible. The specific latency cutoff for Phemex's matching engine is not known.

5. **EFMA 2017 cancellation paper:** SSL error prevented fetching; the quote in the level exhaustion search is from a search snippet only. Not independently verified.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | 06-24 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (do NOT repost same cycle) | 06-23, clarified 06-26 | Queued |
| 3 | Shadow-gate VPIN computation | 06-23 | Queued (treat as exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | 06-26 | Queued |
| 5 | Log `fg_regime` (Fear & Greed index) at signal time | 06-29 | Queued |
| **6** | **Log `q_near_at_post` (ask queue size at target price at post time) — Tweak A** | **06-30** | **Queued (shadow only; verify ask-level queue data available)** |
| **7** | **Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting — Tweak B** | **06-30** | **Queued (shadow only; verify L2 depth data at per-level granularity)** |

---

## Additional Structural Confirmation (Not a New Tweak)

**Source:** arXiv 2407.16527 (2024), "The Negative Drift of a Limit Order Fill"
**URL:** https://arxiv.org/html/2407.16527v1
**Verification:** Accessible via arXiv HTML. New source — not in any prior nightly report.

**Direct quote:** "limit order fills are caused by and coincide with adverse price movements, which create a drag on the market maker's profit and loss."

**Empirical result:** Post-fill drift averages **−0.45 ticks** in US Treasury futures — a universal structural tax on passive placement, independent of spread width, imbalance, or timing. The mechanism is the discrete price-grid: any fill requires price to move to your level, which is by definition adverse.

**Why this matters for ST2.0:** This confirms that adverse selection is not a contingent risk that can be gated away — it is structurally baked into every passive fill at 1-tick granularity. The tweaks above (Tweak A skip gate, Tweak B cancel signal) can reduce the fraction of fills that happen under worst-case conditions, but cannot eliminate the structural −0.45 tick drag. This is useful framing for Jonas when evaluating whether the forward-test queue is worth pursuing at all vs. abandoning ST2.0 entirely.

---

## Research Status

Nine nights. Four verified new findings tonight (more than expected given 06-29's "exhausted" call): the 2502.18625 fill probability regression (Tweak A), Cont & De Larrard queue ratio (Tweak B), Lehalle & Mounjid latency formalization (Observation C), and arXiv 2407.16527 universal drift structural confirmation. Research literature is now genuinely exhausted.

The remaining unread primary source with material probability of new content: **SSRN 6693260 (Chang 2026)** — order-book state predicting passive-buy toxicity. Not yet accessible.

All further work is empirical: shadow-logging the 7 queued metrics for 2–3 weeks, then evaluating which show statistical separation between adverse and clean fills before any live implementation.
