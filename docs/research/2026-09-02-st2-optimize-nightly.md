# ST2.0 Execution Optimization — Night 61
**Date:** 2026-09-02 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 60 Nights

N60 (2026-09-01) confirmed Candidate Tweak 45 (standalone spread gate, arXiv:2602.00776)
and reiterated the 14-night-standing recommendation to suspend search and deploy. Tonight's scope:

1. **arXiv September 2026 listings** — all four q-fin categories (day 2 of month)
2. **arXiv:2507.22712** — new ID surfaced in search, "Order-Flow Filtration" paper
3. **arXiv:2506.05764** — new ID surfaced in search, crypto LOB microstructure paper
4. **arXiv:2603.28898** — new ID surfaced in search, MPC trade execution paper
5. **arXiv:2607.28323** — new ID surfaced in search, "Optimal Execution with Passive Market Impact"

**Net result:** September 2026 arXiv still empty (day 2). 4 new-to-corpus papers screened —
all NOT APPLICABLE. No new actionable tweaks. Tweak queue unchanged: 44 confirmed +
Candidate Tweak 45.

---

## Sources Evaluated Tonight

### arXiv September 2026 — All Four Categories
**Status: VERIFIED** — all four listings fetched directly.

| Category | URL Fetched | Result |
|----------|-------------|--------|
| q-fin.TR | arxiv.org/list/q-fin.TR/2026-09 | "No updates for this time period." |
| q-fin.ST | arxiv.org/list/q-fin.ST/2026-09 | "No updates for this time period." |
| q-fin.PR | arxiv.org/list/q-fin.PR/2026-09 | "No updates for this time period." |
| q-fin.CP | arxiv.org/list/q-fin.CP/2026-09 | "No updates for this time period." |

September 2026 submission window not yet open as of 2026-09-02 (day 2). All four
categories confirmed empty. Earliest meaningful sweep: September 3–5, 2026.

---

### arXiv:2507.22712 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Order-Flow Filtration and Directional Association with Short-Horizon Returns"
**Authors:** Aditya Nittur Anantha, Shashi Jain, Prithwish Maiti
**Source URL:** https://arxiv.org/abs/2507.22712
**Status: VERIFIED** — abstract fetched directly.

**Data:** National Stock Exchange of India (NSE), BankNifty index futures, tick-by-tick.

**Key finding:** "Electronic markets generate dense order flow with many transient orders,
which degrade directional signals derived from the limit order book (LOB)." Filtering on
parent orders of executed trades yields "systematically stronger directional association"
with short-horizon returns vs. unfiltered OFI.

**Why NOT applicable:** Indian equity futures, not crypto CEX perpetual. No maker fill
adverse selection content. No actionable threshold or mechanism transferable to ST2.0.
Directional finding (transient cancel noise degrades OFI signal) is already directionally
covered by the core corpus. NOT APPLICABLE.

---

### arXiv:2506.05764 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books:
Better Inputs Matter More Than Stacking Another Hidden Layer"
**Author:** Haochuan Wang
**Source URL:** https://arxiv.org/abs/2506.05764
**Status: VERIFIED** — abstract fetched directly.

**Data:** Bybit exchange, BTC/USDT limit order book snapshots, 100ms–multi-second intervals.

**Key finding:** "With data preprocessing and hyperparameter tuning, simpler models can match
and even exceed the performance of more complex networks." Focuses on model architecture
benchmark (logistic regression, XGBoost, DeepLOB, Conv1D+LSTM) for price direction
forecasting. No maker fill adverse selection, no placement timing, no execution content.

**Why NOT applicable:** Price prediction benchmark paper; no actionable content for passive
maker execution or adverse selection mitigation. NOT APPLICABLE.

---

### arXiv:2603.28898 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Model Predictive Control For Trade Execution"
**Authors:** McAuliffe, Liew, Li, Ushenin, Wang, Tasos, Pearce, Tasoulis, Bertsekas, Tsagaris
**Source URL:** https://arxiv.org/abs/2603.28898
**Status: VERIFIED** — abstract fetched directly.

**Data:** NASDAQ level 3 data.

**Key finding:** "We address the problem of executing large client orders in continuous
double-auction markets under time and liquidity constraints." MPC framework balancing
market impact, opportunity cost, and completion rate for institutional-size orders.

**Why NOT applicable:** Large-order institutional execution (TWAP/VWAP optimization domain),
not passive maker placement at small size. NASDAQ equities, not crypto CEX perp. No maker
adverse selection content. NOT APPLICABLE.

---

### arXiv:2607.28323 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Optimal Execution with Passive Market Impact"
**Authors:** Alexander Barzykin, Robert Boyce, Eyal Neuman, Sturmius Tuschmann
**Source URL:** https://arxiv.org/abs/2607.28323
**Status: VERIFIED** — abstract fetched directly.

**Data:** NASDAQ equities and public FX markets.

**Key finding:** Model "describes passive execution at a tactical level, where fills arise
from a sequence of quote adjustments that balance execution probability, adverse selection,
and opportunity cost." Incorporates "short-term linear response of price changes to order
flow imbalance." Trades off "higher fill intensity and larger accumulated impact...and lower
impact but greater non-execution risk."

**Why NOT applicable:** NASDAQ/FX markets only; no crypto CEX perpetual data; no
zero-rebate environment. The quote-adjustment / repricing mechanism is relevant in concept
(the exact cancel-and-reinsert problem ST2.0 faces) but the model parameters are calibrated
to traditional equities and FX — no transferable thresholds without crypto CEX re-calibration.
Qualitatively consistent with the fill-probability vs. adverse-selection tradeoff already
established in the core corpus (arXiv:2502.18625). NOT APPLICABLE as a new actionable tweak.

**Partial interest note:** This is the only paper tonight that directly models "quote
adjustments that balance execution probability, adverse selection, and opportunity cost" —
the exact tactical decision ST2.0 faces on each 60-second cycle. The paper is NASDAQ/FX
and not a tweak source, but if ST2.0 were to model repricing intervals explicitly (e.g.,
how many cycles to wait before cancelling and reposting at a different level), this
paper's framework could provide a theoretical scaffold. No actionable parameter tonight.

---

## New Forward-Testable Tweaks Tonight

**None.** All four papers screened are NOT APPLICABLE.

The tweak queue remains at **44 confirmed + Candidate Tweak 45** (unchanged from N60).

---

## Honest Caveats

1. **September 2026 arXiv still empty (day 2 of month).** Earliest meaningful sweep:
   September 3–5, 2026. All four categories confirmed empty tonight.

2. **Search space for this execution angle is saturated.** 4 new papers screened tonight;
   all NOT APPLICABLE. The pattern of the last 15 nights — only non-applicable papers
   surfacing — is consistent with the search being exhausted for the current sub-problem.

3. **arXiv:2607.28323 (Barzykin et al.)** is the closest conceptual neighbor to ST2.0's
   repricing problem among tonight's papers, but NASDAQ/FX calibration makes it
   non-actionable without significant re-derivation. Flagged for awareness only.

4. **SSRN remains universally blocked** (403 on all IDs: 4677989, 5323703, 6344338,
   6693260, 6772279, 7162966). Author contact is the only remaining path.

5. **The empirical gap remains.** No paper in 61 nights has directly measured OFI-flip
   decay speed or passive fill adverse selection at 60-second granularity on a crypto CEX
   perp. Internal bot data is the only source for this measurement.

6. **Recommendation (unchanged from N47–N60, now 15 nights overdue on execution):**
   Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
   Implement Tweak 44 (L2 3-metric regime check) or the simpler Candidate Tweak 45
   (standalone spread gate, ≥75th pct rolling per-symbol). Begin logging `spread_pct` at
   every entry immediately — zero trading risk, unblocks threshold calibration for both.
   Resume arXiv sweep when September 2026 submissions open (expected September 3–5).

---

## Cumulative Forward-Test Queue (44 confirmed + 1 candidate)

**Priority tweaks (unchanged N20–N61): 4 [elevated], 6, 9, 10, 11, 12, 14**
**Tweak 44 (confirmed N59):** L2 3-metric regime check — top-20 levels, spread/depth/
imbalance, tercile-based calm/mixed/stressed. BTC: skip calm. ETH: log tier, no hard skip.
Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp, 2023–2026, full paper verified N59).
**Candidate Tweak 45:** Standalone spread gate — skip entry when bid-ask spread ≥ 75th pct
rolling per-symbol. Source: arXiv:2602.00776 (Binance Futures perp, 2022–2025, verified N60).
**Conditional Tweak 43:** Composite LightGBM toxicity gate (SSRN:6344338, blocked).
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks
27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a),
N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37),
N37 (Tweak 38), N59 (Tweak 44).

---

## arXiv Coverage as of Night 61

- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.* September 2026: EMPTY — submission window not yet open (day 2 of month)

---

## Night 61 Bottom Line

**0 new actionable findings.** 5 sources evaluated:

- **arXiv q-fin.TR/ST/PR/CP September 2026** (all four): VERIFIED EMPTY (day 2).
- **arXiv:2507.22712** (OFI filtration, NSE India): NEW TO CORPUS. NOT APPLICABLE.
- **arXiv:2506.05764** (Bybit LOB model benchmark, Wang): NEW TO CORPUS. NOT APPLICABLE.
- **arXiv:2603.28898** (MPC large-order execution, NASDAQ): NEW TO CORPUS. NOT APPLICABLE.
- **arXiv:2607.28323** (Passive market impact, NASDAQ/FX): NEW TO CORPUS. NOT APPLICABLE.
  Closest conceptual neighbor to ST2.0's repricing problem tonight; non-actionable without
  crypto CEX re-calibration.

**Recommendation (15th consecutive night, unchanged):** Stop searching. Deploy Tweaks 4, 6,
9, 10, 11, 12, 14. Implement Tweak 44 or Candidate Tweak 45 as the faster first step.
Log `spread_pct` at every entry starting now — zero cost, unblocks both calibrations.
