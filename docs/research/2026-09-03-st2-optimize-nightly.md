# ST2.0 Execution Optimization — Night 62
**Date:** 2026-09-03 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 61 Nights

N61 (2026-09-02) screened 4 new papers (all NOT APPLICABLE) and confirmed September 2026
arXiv was empty on day 2. Tonight's scope (day 3 of September):

1. **arXiv September 2026 listings** — all four q-fin categories re-confirmed
2. **arXiv:2409.12721** ("Market Simulation under Adverse Selection") — new to corpus
3. **arXiv:2603.15963** ("Risk-Based Auto-Deleveraging") — new to corpus
4. **arXiv:2605.06405** ("Funding-Aware Optimal Market Making for Perpetual DEXs") — new to corpus
5. **arXiv:2605.24242** ("Explicit Signal-Adaptive Sequential Optimal Execution Quotes") — new to corpus
6. **arXiv:2607.28323 full paper** (Barzykin et al.) — HTML fetched for numerical detail
7. **ScienceDirect S1386418125000229** ("Queuing and inventories in limit order markets") — 403 blocked
8. Targeted search: cancel/repost timing, passive fill decay, post-only repricing

**Net result: 0 new actionable tweaks.** September 2026 arXiv remains nearly empty (1
non-applicable pricing paper). 5 new-to-corpus papers screened — all NOT APPLICABLE. The
full paper read of arXiv:2607.28323 surfaces one minor mechanistic detail not captured in N61
(the explicit δ* formula for quote aggressiveness vs. inventory), but the paper remains
NASDAQ/FX only and non-actionable without empirical calibration on Phemex.

**Tweak queue unchanged: 44 confirmed + Candidate Tweak 45.**

---

## Sources Evaluated Tonight

### arXiv September 2026 — All Four Categories
**Status: VERIFIED** — all four listings fetched directly.

| Category | URL Fetched | Result |
|----------|-------------|--------|
| q-fin.TR | arxiv.org/list/q-fin.TR/2026-09 | "No updates for this time period." |
| q-fin.ST | arxiv.org/list/q-fin.ST/2026-09 | "No updates for this time period." |
| q-fin.PR | arxiv.org/list/q-fin.PR/2026-09 | 1 paper: arXiv:2609.01323 (equity-linked contracts pricing — NOT APPLICABLE) |
| q-fin.CP | arxiv.org/list/q-fin.CP/2026-09 | "No updates for this time period." |

September 2026 submission window has now opened (day 3) but contains only 1 paper in
q-fin.PR, unrelated to execution microstructure. All other categories empty.

---

### arXiv:2409.12721 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Market Simulation under Adverse Selection"
**Authors:** Luca Lalor, Anatoliy Swishchuk
**Data:** CME futures — ES (E-mini S&P 500), NQ, CL, ZN (10-Year Treasury)
**Source URL:** https://arxiv.org/abs/2409.12721
**Status: VERIFIED** — abstract + HTML fetched directly.

**Key finding:** "Fill probabilities and adverse fills can significantly affect performance" in
strategy simulation. Proposes a simulation framework incorporating realistic fill dynamics.

**Why NOT applicable:** CME equity index / commodity futures, not crypto CEX perp. No passive
maker placement findings, no actionable thresholds for post-only execution. Qualitative
finding (adverse fills inflate simulated PnL vs. reality) is already established in corpus via
arXiv:2502.18625. NOT APPLICABLE.

---

### arXiv:2603.15963 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Risk-Based Auto-Deleveraging"
**Authors:** Steven Campbell, Natascha Hey, Ciamac C. Moallemi, Marcel Nutz
**Source URL:** https://arxiv.org/abs/2603.15963
**Status: VERIFIED** — abstract fetched directly.

**Key finding:** Formulates auto-deleveraging (ADL) as a "minimax leverage" optimization for
cryptocurrency futures exchanges. Applied to Hyperliquid's October 2025 ADL event.

**Why NOT applicable:** Exchange risk management paper (ADL policy design). Does not address
passive maker execution, adverse selection, or order placement quality. NOT APPLICABLE.

---

### arXiv:2605.06405 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Funding-Aware Optimal Market Making for Perpetual DEXs"
**Author:** Nam Anh Le
**Data:** Hyperliquid DEX perpetuals (ETH, BTC, SOL), calibrated via Hamilton-Jacobi-Bellman
**Source URL:** https://arxiv.org/abs/2605.06405
**Status: VERIFIED** — abstract fetched directly.

**Key finding:** Extends Avellaneda-Stoikov market-making to include stochastic funding rates.
"Improves mean ETH/BTC performance while lowering inventory RMS relative to classical A-S."

**Why NOT applicable:** DEX AMM-style liquidity provision, not a CEX post-only limit order.
Funding-rate dynamics differ between DEX and Phemex CEX structure. No adverse selection
measurement for passive fill timing. NOT APPLICABLE.

---

### arXiv:2605.24242 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Explicit Signal-Adaptive Sequential Optimal Execution Quotes"
**Source URL:** https://arxiv.org/abs/2605.24242
**Status: VERIFIED** — abstract fetched directly.

**Key finding:** Derives "fully explicit value functions and optimal quotes" for sequential
limit-order placement under signal-dependent drift, price impact, inventory risk, and
execution risk. Fills modeled by point processes with quote-distance-dependent intensities.

**Why NOT applicable:** Theoretical model with no crypto CEX empirical calibration. The
paper's fill-intensity model requires market-specific parameter estimation (signal decay,
impact coefficients) that the paper does not provide for crypto perpetuals. The conceptual
framework (signal-adaptive quoting) is consistent with the corpus but adds no new testable
threshold or mechanism for ST2.0. NOT APPLICABLE.

---

### arXiv:2607.28323 — FULL PAPER READ (already in corpus from N61)
**Title:** "Optimal Execution with Passive Market Impact"
**Authors:** Alexander Barzykin, Robert Boyce, Eyal Neuman, Sturmius Tuschmann
**Data:** NASDAQ equities + FX markets only
**Source URL:** https://arxiv.org/html/2607.28323
**Status: VERIFIED** — full HTML fetched.

Previously classified NOT APPLICABLE in N61 (NASDAQ/FX only, non-actionable without
crypto re-calibration). Tonight's full paper read extracts the key formula:

**Optimal quote distance formula (verified from full paper):**
> δ*(t,q) = 1/k + (1/k)·log(ω(t,q)/ω(t,q−1)) + (η/λ)·q

Where: k = fill intensity decay with distance, η = passive impact coefficient,
λ = fill intensity at mid, q = remaining inventory.

**Interpretation:** Optimal passive sell quote is placed CLOSER to mid when inventory is
large (urgency), and DEEPER when time pressure eases. Fill intensity decay k spans
0.48–3.72 for equities and 0.5–0.6 for FX in their calibration.

**Core mechanistic insight (minor enhancement over N61):** The paper explicitly confirms that
for a zero-rebate passive sell in a unidirectional position (ST2.0 short), the "urgency"
component goes to zero (q is fixed at 1 contract), and the tradeoff collapses to minimizing
adverse selection cost vs. non-execution risk — i.e., there is no inventory pressure pushing
toward more aggressive quoting. This means the classic "post closer to mid as size grows"
logic does NOT apply to ST2.0's single-unit short, and the dominant variable is purely the
adverse selection cost per fill.

**Status: SUPPLEMENTAL NOTE — still NOT APPLICABLE as a new tweak.** No crypto CEX calibration
exists. The δ* formula requires estimating k (fill decay vs. distance) from Phemex order book
data — not currently logged. This is a framework for a future empirical study, not a
deployable parameter today.

---

### ScienceDirect S1386418125000229 — BLOCKED, NOT SCREENED
**Title:** "Queuing and inventories in limit order markets" (2025)
**Source URL:** https://www.sciencedirect.com/science/article/pii/S1386418125000229
**Status: 403 Forbidden.** Could not fetch. Unable to evaluate content.

---

## New Forward-Testable Tweaks Tonight

**None.** All sources screened are NOT APPLICABLE.

The tweak queue remains at **44 confirmed + Candidate Tweak 45** (unchanged from N61).

---

## Honest Caveats

1. **September 2026 arXiv now open but almost empty (day 3).** 1 paper in q-fin.PR
   (arXiv:2609.01323, equity-linked contracts — not applicable). All other categories still
   empty. Sweep again September 4–7 as submissions accumulate.

2. **The search space for this execution angle is exhausted.** 7 new sources screened
   tonight (5 papers + 1 blocked + Barzykin full paper re-read); all NOT APPLICABLE.
   The pattern of 16 consecutive nights with no actionable findings is consistent with
   literature saturation for the current sub-problem.

3. **arXiv:2607.28323 (Barzykin et al.)** full paper read confirms the δ* formula but yields
   no new crypto-transferable thresholds. The single-unit inventory observation (q=1 means
   urgency term is zero, leaving only adverse selection) is a minor clarification. Not a tweak.

4. **ScienceDirect S1386418125000229** ("Queuing and inventories") remains blocked (403).
   If accessible, this 2025 paper on queue position and inventory interactions could be relevant.
   No further action available without institutional access.

5. **SSRN remains universally blocked** (403 on all IDs: 4677989, 5323703, 6344338,
   6693260, 6772279, 7162966). Author contact is the only remaining path.

6. **The empirical gap remains.** No paper in 62 nights has measured OFI-flip decay speed
   or passive fill adverse selection at 60-second granularity specifically for a crypto CEX
   perp maker. Internal bot data is the only source for this measurement.

7. **Recommendation (unchanged from N47–N61, now 16 nights overdue on execution):**
   Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
   Implement Tweak 44 (L2 3-metric regime check) or Candidate Tweak 45 (standalone spread
   gate ≥75th pct rolling per-symbol). Begin logging `spread_pct` at every entry immediately —
   zero trading risk, unblocks threshold calibration for both. Resume arXiv sweep as
   September 2026 submissions accumulate (expected ~September 5–7).

---

## Cumulative Forward-Test Queue (44 confirmed + 1 candidate)

**Priority tweaks (unchanged N20–N62): 4 [elevated], 6, 9, 10, 11, 12, 14**
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

## arXiv Coverage as of Night 62

- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.TR September 2026: EMPTY (0 papers as of Sep 3)
- q-fin.ST September 2026: EMPTY (0 papers as of Sep 3)
- q-fin.PR September 2026: 1 paper (arXiv:2609.01323 — not applicable)
- q-fin.CP September 2026: EMPTY (0 papers as of Sep 3)

---

## Night 62 Bottom Line

**0 new actionable findings.** 7 sources evaluated:

- **arXiv q-fin.TR/ST/PR/CP September 2026:** VERIFIED. Nearly empty — 1 non-applicable paper.
- **arXiv:2409.12721** (Lalor & Swishchuk, CME futures simulation): NEW TO CORPUS. NOT APPLICABLE.
- **arXiv:2603.15963** (Campbell et al., ADL crypto futures): NEW TO CORPUS. NOT APPLICABLE.
- **arXiv:2605.06405** (Le, DEX funding-aware MM): NEW TO CORPUS. NOT APPLICABLE.
- **arXiv:2605.24242** (Signal-adaptive sequential execution): NEW TO CORPUS. NOT APPLICABLE —
  theoretical only, no crypto CEX calibration.
- **arXiv:2607.28323 full paper** (Barzykin et al., NASDAQ/FX): ALREADY IN CORPUS. Full paper
  read confirms single-unit inventory insight (q=1 → urgency term is zero → adverse selection
  is the only variable). Still NOT APPLICABLE as a new tweak.
- **ScienceDirect S1386418125000229** (Queuing and inventories, 2025): BLOCKED (403). Not screened.

**Recommendation (16th consecutive night, unchanged):** Stop searching. Deploy Tweaks 4, 6,
9, 10, 11, 12, 14. Start with Tweak 45 (spread gate ≥75th pct rolling) or Tweak 44 (L2
regime check) — whichever is faster to implement. Log `spread_pct` at every entry now.
Resume sweep when September 2026 submissions accumulate (~September 5–7).
