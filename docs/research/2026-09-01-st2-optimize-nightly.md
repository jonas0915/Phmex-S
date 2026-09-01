# ST2.0 Execution Optimization — Night 60
**Date:** 2026-09-01 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 59 Nights

N59 (2026-08-31) delivered the primary deliverable: Tweak 44 (L2 3-metric regime check,
arXiv:2607.09230 Jeon) fully specified. The recommendation to suspend nightly search and
deploy priority tweaks has stood for 14 consecutive nights. Tonight's scope:

1. **arXiv September 2026 listings** — all four q-fin categories (window expected to open ~now)
2. **arXiv:2602.00776** — new hit in search results, Binance Futures perp, 1-second frequency
3. **arXiv:2602.07018** — new hit, "Extremity Premium," adverse selection and sentiment regimes
4. **HFT Advisory practitioner piece** — "Six Market Microstructure Signals Before the Print"
5. **arXiv:2603.24137** — "Bridging the Reality Gap in LOB Simulation"
6. Targeted search on spread-regime gating and passive maker adverse selection

**Net result:** arXiv September 2026 still empty. 1 new-to-corpus paper found and verified
(arXiv:2602.00776, Binance Futures perp). It provides cross-asset confirmation of the spread
regime → adverse selection link — supporting Tweak 44's spread component and surfacing a
simpler standalone spread gate (Candidate Tweak 45). 1 paper screened and NOT APPLICABLE
(arXiv:2602.07018 — daily data). 2 papers NOT APPLICABLE (simulation + practitioner
unverified). **Tweak queue: 44 confirmed + Candidate Tweak 45.**

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

September 2026 arXiv submission window has not opened as of 2026-09-01 (day 1 of month).
Expected to open mid-first-week. Sweep again in 2–3 days.

---

### arXiv:2602.00776 — NEW TO CORPUS ✓ PARTIALLY APPLICABLE
**Title:** "Explainable Patterns in Cryptocurrency Microstructure"
**Authors:** (multiple, Binance Futures perp research group)
**Submitted:** January 31, 2026
**Data:** Binance Futures perpetual contracts — BTC, LTC, ETC, ENJ, ROSE; 1-second
observations; January 1, 2022 – October 12, 2025
**Source URL:** https://arxiv.org/abs/2602.00776
**Status: VERIFIED** — abstract + HTML fetched directly.

**Key verified findings (direct quotes from fetched HTML):**

1. **Cross-asset stability:** "feature rankings and partial effects are stable across assets
   despite heterogeneous liquidity and volatility." Order flow imbalance, spread, and adverse
   selection patterns hold across a one-order-of-magnitude market-cap range.

2. **Wider spreads = attenuated signal quality:** "wider spreads correlate with attenuated
   predictive effects and lower-confidence signals" — passive orders in elevated-spread regimes
   operate in a lower-signal environment.

3. **Maker adverse selection validated empirically:** "A market maker who fails to widen their
   spread in response is essentially offering a subsidy to informed traders, leading to
   near-certain losses." During the Oct 10, 2025 flash crash (Binance Futures perp), the maker
   strategy "suffered catastrophic losses" while taker execution profited — the exact one-sided
   adverse fill pattern.

4. **Empirical validation of microstructure theory:** "the divergent performance of our taker
   and maker strategies empirically validates classic microstructure theories of adverse
   selection."

**What this adds to the corpus:**
- Prior corpus had the spread component as 1/3 of Tweak 44's L2 regime check (arXiv:2607.09230
  Jeon). This paper provides **direct, cross-asset, Binance Futures perp empirical confirmation**
  that elevated spreads degrade maker signal quality — using 1-second frequency data across 5
  assets over 3+ years. The cross-asset stability is the new element: it isn't just a BTC/ETH
  result, it holds across thin-market assets too.
- Supports treating spread-width elevation as an independent adverse-selection gate (not just
  part of a composite regime check).

**Limitation:** No specific percentage thresholds are provided for what constitutes an
"elevated" spread. The paper's maker simulation uses constant-spread logic and the authors
acknowledge "maker strategies are notoriously difficult to simulate accurately" due to latency
and queue dynamics.

---

### arXiv:2602.07018 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "The Extremity Premium: Sentiment Regimes and Adverse Selection in Cryptocurrency
Markets"
**Author:** Murad Farzulla
**Data:** Crypto Fear & Greed Index + Bitcoin/Ethereum **daily** price data, 2018–2026
(N=2,896 days)
**Source URL:** https://arxiv.org/abs/2602.07018
**Status: VERIFIED** — abstract fetched directly.

**Key finding:** "Extreme fear and extreme greed regimes exhibit significantly higher spreads
than neutral periods — the 'extremity premium.'" Cohen's d = 0.21 within-volatility quintiles
(p < 0.001). The effect is direction-agnostic (both extremes = elevated spread, V-shape).

**Why NOT applicable to ST2.0:** Daily data only; no intraday thresholds; effect is absorbed
by parametric regression controls (parametric volatility controls eliminate regime effects, only
nonparametric methods preserve them); no guidance on entry timing for 60-second-cycle perp
maker. The qualitative finding (extreme sentiment = wider spreads = higher adverse selection)
is already in the core corpus directionally. NOT APPLICABLE.

---

### HFT Advisory Substack — PRACTITIONER PIECE, UNVERIFIED
**Title:** "Six Market Microstructure Signals That Fire Before the Price Print"
**URL:** https://hftadvisory.substack.com/p/six-market-microstructure-signals
**Status:** Fetched directly. Practitioner claims ONLY. **Not a primary source.**

Signals described: (1) cancel-side asymmetry, (2) refresh-latency widening, (3) VPIN
elevation, (4) multi-level LOB imbalance, (5) spread widening, (6) print and queue position.

Practitioner thresholds cited (UNVERIFIED — explicitly labeled non-academic by author):
- Cancel asymmetry: "3–5× imbalance on one side in the 100ms before a fill is consistent
  with informed repositioning"
- VPIN: "above 0.7 sustained across 8 buckets indicates elevated informed-flow probability"

Academic citations are Easley et al. (VPIN), Cont et al., Foucault et al. — all in prior
corpus. The specific numerical thresholds (0.7, 8 buckets, 3-5×, 100ms) are the author's
practitioner heuristics with no published verification. UNVERIFIED. NOT adding to tweak queue.

---

### arXiv:2603.24137 — NOT APPLICABLE
**Title:** "Bridging the Reality Gap in Limit Order Book Simulation"
**Status: VERIFIED** — abstract fetched. LOB simulation methodology paper. No empirical
findings about maker fill adverse selection or placement timing thresholds. NOT APPLICABLE.

---

## Candidate Tweak 45 — Standalone Spread Gate

**Mechanism:** Before posting the passive maker SELL, compare the current bid-ask spread
against a rolling percentile threshold for that symbol. If the spread is elevated
(e.g., above 75th pct of the symbol's 60-day rolling distribution at the same time of day),
defer by one 60-second cycle.

**Basis:** arXiv:2602.00776 (Binance Futures perp, 1-second, 5 assets, 3+ years): "wider
spreads correlate with attenuated predictive effects and lower-confidence signals." Cross-asset
stability holds. Maker adverse selection is demonstrated in elevated-spread regimes.

**Relationship to Tweak 44:** Tweak 44 (arXiv:2607.09230 Jeon) includes spread as 1 of 3
regime metrics — a high spread alone yields "mixed" (not "stressed") and does NOT hard-skip
for ETH, and skips calm-only for BTC. Tweak 45 proposes: **if spread alone is ≥ 75th pct,
skip regardless of other regime metrics.** This is strictly more aggressive on spread-gating
than Tweak 44 and could be implemented as a pre-check before Tweak 44's 3-metric composite.

**Forward-test metric:** Log `spread_pct` (rolling percentile of bid-ask spread) at each ST2.0
entry. After n ≥ 30 fills: fill rate and 15m post-fill adverse move by spread_pct quartile.

**Status: CANDIDATE** — awaiting threshold calibration from bot's own rolling spread data.

**Caveat:** (a) No specific threshold in the paper — 75th pct is a reasonable starting point
but must be calibrated per symbol. (b) Elevated spread at entry partly overlaps with Tweak 44's
spread_z component — implementing both adds redundant filtering; consider Tweak 45 as a
simpler pre-check that replaces the spread_z component in Tweak 44 rather than doubling it.
(c) The flash-crash finding is an extreme event; the paper does not establish the same
adverse-selection elevation during ordinary spread fluctuations (widening from 0.01% to 0.02%
bp is not the same as a market dislocation).

---

## Honest Caveats

1. **September 2026 arXiv still empty (day 1 of month).** Expected to open mid-first-week.
   Earliest meaningful sweep: September 3–5, 2026.

2. **arXiv:2602.00776 strengthens, but does not add beyond, existing corpus.** The spread-
   regime → adverse selection link was already directionally established via arXiv:2502.18625
   and arXiv:1610.00261. The new contribution is cross-asset empirical confirmation on Binance
   Futures perp at 1-second frequency. No new mechanism.

3. **SSRN remains universally blocked** (403 on all IDs: 4677989, 5323703, 6344338, 6693260,
   6772279, 7162966). Author contact is the only path.

4. **The empirical gap remains.** No paper in 60 nights has measured OFI-flip decay speed or
   passive fill adverse selection at 60-second granularity specifically for a crypto CEX perp
   maker. Internal bot data is the only source for this measurement.

5. **Recommendation (unchanged from N47–N59, now 14 nights overdue):**
   Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14, and
   implement + instrument Tweak 44 (L2 3-metric regime check). Evaluate Tweak 45 as a simpler
   pre-check before committing to the full Tweak 44 implementation. Resume arXiv sweep
   September 3–5, 2026.

---

## Cumulative Forward-Test Queue (44 confirmed + 1 candidate)

**Priority tweaks (unchanged N20–N60): 4 [elevated], 6, 9, 10, 11, 12, 14**
**Tweak 44 (confirmed N59):** L2 3-metric regime check — top-20 levels, spread/depth/imbalance,
tercile-based calm/mixed/stressed. BTC: skip calm. ETH: log tier, no hard skip.
Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp, 2023–2026, full paper read).
**Candidate Tweak 45:** Standalone spread gate — skip entry when bid-ask spread ≥ 75th pct
rolling per-symbol. Source: arXiv:2602.00776 (Binance Futures perp, 2022–2025, verified
2026-09-01). Simpler alternative/pre-check to Tweak 44's spread_z component.
**Conditional Tweak 43:** Composite LightGBM toxicity gate (SSRN:6344338, blocked).
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks
27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a),
N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37),
N37 (Tweak 38), N59 (Tweak 44).

---

## arXiv Coverage as of Night 60

- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.* September 2026: EMPTY — window expected mid-first-week

---

## Night 60 Bottom Line

**1 new-to-corpus paper verified; 1 candidate tweak added.** 5 sources evaluated:

- **arXiv q-fin.TR/ST/PR/CP September 2026** (all four): VERIFIED. Still empty (day 1).
- **arXiv:2602.00776** (Binance Futures perp, 5 assets, 1-second, 2022–2025):
  **NEW TO CORPUS. PARTIALLY APPLICABLE.** Cross-asset confirmation: elevated spread at entry
  correlates with attenuated predictive signal and higher maker adverse selection. Strengthens
  Tweak 44's spread component; surfaces Candidate Tweak 45 (standalone spread gate at 75th
  pct rolling per-symbol).
- **arXiv:2602.07018** (Farzulla, "Extremity Premium," daily data): **NEW TO CORPUS.
  NOT APPLICABLE** — daily resolution, effect absorbed by parametric controls, no intraday
  thresholds.
- **HFT Advisory Substack** (practitioner piece): Screened. UNVERIFIED practitioner
  thresholds citing corpus papers already held. Not added to queue.
- **arXiv:2603.24137** (LOB simulation methodology): NOT APPLICABLE.

**Recommendation (14th consecutive night, unchanged):** Stop searching. Deploy Tweaks 4, 6, 9,
10, 11, 12, 14. Implement Tweak 44 (L2 regime check) or the simpler Tweak 45 (spread gate)
as a faster-to-implement first step. Log spread_pct at every entry starting now — this costs
nothing and answers the calibration question for both Tweaks 44 and 45.
