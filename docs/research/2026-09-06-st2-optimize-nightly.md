# ST2.0 Execution Optimization — Night 65
**Date:** 2026-09-06 | **Focus:** Passive maker fill quality / adverse selection mitigation
**Prior coverage:** N1–N64 (64 nights); arXiv q-fin.* through August 2026 fully swept; SSRN universally 403-blocked

---

## What's New vs. Prior 64 Nights

### arXiv September 2026 — All Four Categories (Re-confirmed Day 6)

| Category | Status as of Sep 6 |
|----------|-------------------|
| q-fin.TR | VERIFIED EMPTY (0 submissions) |
| q-fin.ST | VERIFIED EMPTY (0 submissions) |
| q-fin.PR | 1 paper — arXiv:2609.01323 (equity-linked contracts pricing — NOT APPLICABLE, already screened N62) |
| q-fin.CP | 6 papers (arXiv:2609.00332, 00438, 01323, 02014, 03552, 04087) — all pricing/vol math, NOT APPLICABLE, unchanged from N64 |

No new submissions in execution-relevant categories. September 2026 arXiv is still in its early-month sparse window.

---

### arXiv:2307.04863 — NEW TO CORPUS, PARTIALLY APPLICABLE

**Title:** "Interpretable ML for High-Frequency Execution" (Jusselin, Mastrolia, Rosenbaum, et al.)
**Source URL:** https://arxiv.org/abs/2307.04863
**Data:** Coinbase (BTC-USD, ETH-USD), November 5 – December 5, 2022, microsecond-precision L3 feed (SUN ZU Lab proprietary); also Euronext Paris equities (BNPP, LVMH) Jan–Dec 2017
**Status: VERIFIED** — abstract + HTML fetched directly.

This paper appeared in a web search result alongside the in-corpus sources. Screened against N1–N64 reports: **not previously evaluated.** The paper's crypto CEX scope makes it potentially relevant; evaluated below.

#### Key Verified Findings

The paper develops ML models for fill probability prediction and limit/market order placement decisions. Its central results are:

1. **Priority volume (V_prior) dominates fill probability in small-tick crypto books.**
   From paper: *"While the distance is a reasonable proxy for the price priority of an order in a large tick book, it can be misleading for small tick books."* For small-tick CEX pairs (Coinbase BTC-USD, ETH-USD), fill probability scales as V_prior^{−α} where α ∈ {0.4, 1, 2} across model variants. This means: **the volume of resting orders ahead of you at your price level is the primary fill-probability driver**, not raw price distance from mid.

2. **Limit order flow imbalance** (new feature not in prior corpus): The paper claims this is the first study of this variable on fill probability. For crypto: "symmetric monotonicity" — more limit order flow imbalance in your favor predicts higher fill probability. Fails to generalize to equities. This corroborates OFI gating but specifically for fill probability prediction, not adverse selection filtering.

3. **Feature importance diverges between crypto and equities.** For passive crypto orders, V_prior dominates. For equities, order flow imbalance and volatility rank higher. **Implication: equity-sourced fill probability rules do not transfer cleanly to CEX crypto perps.** This partially explains why academic results from non-crypto venues have limited applicability.

4. **No standalone numerical threshold actionable without ML.** The aggressiveness index (ω) finding (monotonically higher fill prob for more aggressive quotes) confirms expected behavior but requires fitted parameters. F-score for Model III on BTC-USD: **0.51** — better than equity benchmark (0.30) but requiring real-time inference.

#### Why Partially Applicable

The **V_prior insight** is extractable as a heuristic WITHOUT an ML pipeline:

> **Before posting, read the L2 order book depth at your target ask price. If a large quantity of sell volume is already resting at that exact price level, your resting order joins the back of that queue — fill probability is low AND adverse selection is elevated (same fills as arXiv:2502.18625's back-of-queue finding: −0.775 bp vs front-of-queue −0.058 bp).**

This is directly implementable on Phemex using the existing L2 feed already fetched for OB imbalance gating. No ML inference required.

**Caveats for this paper:**
- Data is Coinbase, Nov-Dec 2022 — not Phemex, not 2026
- α ∈ {0.4, 1, 2} values are Coinbase-specific; Phemex calibration required
- Does not address adverse selection directly (fill probability ≠ post-fill PnL)
- Likely overlaps thematically with Tweaks 4–14 in the existing queue (their specific content is archived in N1–N22 and not re-read tonight — verify before deploying as a new tweak)

---

### Other Sources Evaluated Tonight

| Source | Verdict |
|--------|---------|
| arXiv:2607.11888 "Optimal Adaptive Market Making for Perp Futures" | NOT APPLICABLE — theoretical HJB framework, no empirical crypto data, no passive-fill content |
| supa.is "Hyperliquid vs OKX CEX execution checklist 2026" | NOT APPLICABLE — no maker fill data; recommends own empirical testing only |
| Web search: "maker order repricing cancel-and-repost adverse selection crypto perp 2026" | No new papers; surface arXiv:2607.11888 and arXiv:2603.15963 (both already screened/classified NOT APPLICABLE) |
| Web search: "passive limit order time-to-fill adverse selection crypto CEX 2026" | Returns arXiv:2307.04863 (now screened above) and arXiv:2407.16527 (DeLise, Treasury futures, already in corpus from N63) |

---

## New Forward-Testable Tweak Tonight

### Candidate Tweak 46: V_prior queue depth check at target price level

**Source:** arXiv:2307.04863 (Jusselin et al., Coinbase BTC/ETH-USD, Nov–Dec 2022)  
**Verified claim:** Fill probability on small-tick crypto CEX pairs scales as V_prior^{−α} — the resting sell volume at your target price level is the primary fill-probability determinant, more informative than price distance from mid.

**Operationalization for ST2.0:**
- At entry signal time, read the L2 ask side at the intended post price (best_ask).
- Compute `v_prior_sell` = total ask quantity already resting at that price tier.
- **Log first:** record `v_prior_sell` at every ST2.0 entry attempt (fills and misses) for 2–3 weeks.
- **Gate later (after calibration):** if `v_prior_sell` exceeds the Xth percentile per-symbol, skip entry. The α range in the paper (0.4–2) suggests the relationship is convex — very large V_prior is sharply worse.

**Cost:** 1–2 lines of Python reading existing L2 data already fetched. No new exchange calls.  
**Interaction with existing system:** Complements Tweak 45 (spread gate) and Tweak 44 (regime check). Specifically targets queue position rather than spread or regime — a distinct mechanism.

**Caveat — check Tweaks 4–14 first:** The specific content of the priority tweak queue (4, 6, 9, 10, 11, 12, 14) is archived in N1–N22 reports not re-read tonight. Tweak 46 may overlap conceptually with one of these. Verify before treating as novel.

---

## Honest Caveats

1. **arXiv September 2026 is still sparse (day 6).** q-fin.TR/ST remain empty. The expected accumulation window (Sep 8–12 after August blackout) is still ahead.

2. **arXiv:2307.04863 is 2023 data from Coinbase**, not Phemex, and not a perpetual futures venue. The V_prior result is for spot CEX LOB — transfer to Phemex perp LOB is unverified.

3. **The V_prior heuristic does not address adverse selection directly** — it predicts *whether* you fill, not *what happens after*. It is a fill probability tool, not an adverse-selection filter. The adverse-selection mechanism remains arXiv:2502.18625 (front-vs-back-queue fills on Binance BTC perp).

4. **SSRN (6 IDs) and ScienceDirect S1386418125000229 remain blocked.** No alternative access found tonight.

5. **Standing gap from N64:** `time_to_fill` is still not logged. The instrumentation from N64 (log fill speed → bucket → markout per bucket) remains undeployed and is still the single highest-leverage zero-risk action.

6. **Literature saturation continues.** This is the 19th consecutive night with 0 new tweaks from peer-reviewed sources. The existing queue (Tweaks 4, 6, 9, 10, 11, 12, 14, 44, 45) remains undeployed.

---

## Standing Recommendation (Night 19 of suspension advisory — unchanged)

**Suspend nightly sweeps.** Resume September 8–12 when q-fin.TR/ST submissions accumulate.

**Highest-priority immediate actions (zero trading risk):**
1. Log `time_to_fill` on every ST2.0 fill (5 lines of Python — from N64, still undeployed)
2. Log `spread_pct` at every entry attempt (Tweak 45 — from N60, still undeployed)
3. Log `v_prior_sell` at every entry attempt (Candidate Tweak 46 — tonight)

**Then deploy** priority Tweaks 4, 6, 9, 10, 11, 12, 14 from the existing queue.

---

## Cumulative Forward-Test Queue (44 confirmed + 2 candidates — +1 tonight)

**Priority tweaks (unchanged N20–N65): 4 [elevated], 6, 9, 10, 11, 12, 14**  
**Tweak 44 (confirmed N59):** L2 3-metric regime check (top-20 levels, spread/depth/imbalance terciles). Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp 2023–2026).  
**Candidate Tweak 45 (N60):** Standalone spread gate ≥75th pct rolling per-symbol. Source: arXiv:2602.00776 (Binance Futures perp 2022–2025).  
**Candidate Tweak 46 (N65):** V_prior queue depth check at target ask price before posting. Source: arXiv:2307.04863 (Jusselin et al., Coinbase BTC/ETH-USD 2022). Verify against Tweaks 4–14 before treating as novel.  
**Conditional Tweak 43:** Composite LightGBM toxicity gate (SSRN:6344338, blocked).  
Full queue archived: N22 (Tweaks 1–22), N23 (23), N24 (24–26), N26 (27–28), N27 (29), N28 (30, 30a), N29 (31, 31a), N30 (32, 32a), N31 (33), N32 (34, 34a), N34 (35, 35a), N35 (36), N36 (37), N37 (38), N59 (44).

---

## arXiv Coverage as of Night 65

- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.TR September 2026: EMPTY (0 submissions as of Sep 6)
- q-fin.ST September 2026: EMPTY (0 submissions as of Sep 6)
- q-fin.PR September 2026: 1 paper (arXiv:2609.01323 — not applicable)
- q-fin.CP September 2026: 6 papers (arXiv:2609.00332, 00438, 01323, 02014, 03552, 04087 — all pricing math, not applicable)

---

## Night 65 Bottom Line

**1 new candidate tweak from a newly-screened source (arXiv:2307.04863).** All other sources: NOT APPLICABLE or NOT NEW.

Summary of sources evaluated:
- **arXiv q-fin.TR/ST September 2026:** VERIFIED EMPTY.
- **arXiv q-fin.PR/CP September 2026:** UNCHANGED from N64 (1 + 6 papers, all not applicable).
- **arXiv:2307.04863** (Jusselin et al., Coinbase CEX fill probability): NEW TO CORPUS. PARTIALLY APPLICABLE — V_prior queue depth heuristic extractable without ML. Yields Candidate Tweak 46.
- **arXiv:2607.11888** (Adaptive MM theory): NOT APPLICABLE.
- **supa.is CEX execution checklist:** NOT APPLICABLE (no empirical data).

**Recommendation (19th consecutive night):** Stop searching until September 8–12. Deploy `time_to_fill` and `spread_pct` logging immediately. Candidate Tweak 46 (`v_prior_sell` logging) is an easy add at the same time.
