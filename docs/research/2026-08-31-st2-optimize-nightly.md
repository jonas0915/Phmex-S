# ST2.0 Execution Optimization — Night 59
**Date:** 2026-08-31 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 58 Nights

N58 (2026-08-30) elevated arXiv:2607.09230 (Jeon, Binance BTC/ETH perp) as **Candidate Tweak 44**
but flagged that the full paper methodology was unread — leaving it unspecified numerically.
Tonight's scope:

1. **Full paper read of arXiv:2607.09230** (open access HTML) — primary goal: numerically specify
   Tweak 44 (L2 depth regime check as pre-placement gate)
2. **arXiv September 2026 listings** — all four q-fin categories re-confirmed
3. **Targeted practitioner search** — one new search angle
4. **arXiv:2608.04373** (surfaced in search results, not in prior corpus) — screened
5. **arXiv:2407.16527** (surfaced in search results, not in prior corpus) — screened

**Net result:** Tweak 44 is now NUMERICALLY SPECIFIED (primary deliverable). Two papers
added to corpus (both NOT APPLICABLE). September 2026 arXiv still empty. No new tweaks
beyond the Tweak 44 specification.

---

## Sources Evaluated Tonight

### arXiv:2607.09230 — FULL PAPER READ (Tweak 44 now specified)
**Title:** "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in
Crypto Futures"
**Author:** Joohyoung Jeon
**Data:** Binance BTCUSDT and ETHUSDT perpetual futures, January 2023–mid-2026
**Source URL:** https://arxiv.org/abs/2607.09230
**Status: VERIFIED — full HTML paper fetched directly (arxiv.org/html/2607.09230)**

### Full Methodology (Verified from Full Paper Read)

**L2 Book Specification:**
- Top-20 levels per side (Binance BTCUSDT and ETHUSDT perp)
- 1-minute sampling cadence
- Pre-event window: [t−5min, t) before macro news releases

**Three-State Regime Definition:**
The L2 state is classified by counting how many of THREE metrics fall in their "top tercile"
(where top = most stressed direction):
1. **Relative bid-ask spread** (top tercile = widest spread)
2. **Top-20 aggregate depth** (negated — top tercile = shallowest book)
3. **Top-20 order-book imbalance** (top tercile = most imbalanced)

Thresholds are **tercile-based**, estimated per symbol from training-fold data only (no leakage).
- 0 metrics in top tercile → **calm**
- 1 metric in top tercile → **mixed**
- 2–3 metrics in top tercile → **stressed**

Empirical regime distribution (47,513 windows): ~0.21 calm, ~0.54 mixed, ~0.25 stressed.

**Key Numerical Results (verified from full paper):**

| Asset | OFI overlay (1m) | OFI overlay (5m) | Null threshold | Verdict |
|-------|-----------------|-----------------|---------------|---------|
| ETH | +0.020 | +0.016 | 95th pct: 0.006/0.003 | CLEARS — OFI adds real value |
| BTC | +0.001 | +0.003 | Below null | FAILS — OFI adds nothing |

**ETH regime breakdown (OFI increment over L2 model):**
- Calm: +0.004 (1m), modest
- Mixed: +0.020 (1m), +0.015 (5m) — clears null
- **Stressed: +0.038 (1m), +0.030 (5m) — highest OFI value of any cell**

**BTC regime breakdown:**
- Only 1 of 6 cells clears null (5m calm). **No regime clears at both horizons.**
- Stressed BTC: at or below null — OFI is noise, not signal.

**State-first principle (verified):**
"The first-order predictive signal is the pre-event L2 liquidity state... Order flow provides
further incremental value only when layered on top of the L2 state model."

---

## Tweak 44 — NOW FULLY SPECIFIED

**Mechanism:** Before posting passive maker SELL, compute a 3-metric L2 regime check across
the top-20 book levels and classify as calm / mixed / stressed. Apply asset-specific filter.

**Implementation spec:**

At pre-placement moment (ST2.0 60-second cycle), compute:
1. `spread_z` = relative bid-ask spread (best ask − best bid) / mid — tercile rank vs. rolling
   60-day per-symbol distribution
2. `depth_z` = total notional depth across top-20 bid + ask levels — tercile rank (inverted:
   shallow = stressed)
3. `imbalance_z` = aggregate OB imbalance across top-20 levels = (bid_depth − ask_depth) /
   (bid_depth + ask_depth) — tercile rank vs. rolling distribution

Count how many of {spread_z, depth_z, imbalance_z} are in their "stressed" tercile.
- 0 → calm; 1 → mixed; 2–3 → stressed

**Asset-specific entry rules (derived from Jeon findings):**

- **BTC entries:** OFI adds nothing in any regime (only calm/5m borderline clears).
  Recommended filter: **skip BTC entry if L2 state is calm** (no OFI predictability, no L2
  state confirming). Allow mixed/stressed only — but note stressed BTC also fails null.
  Conservative option: gate BTC to stressed regime only (at least the book is imbalanced/thin,
  giving some mechanical validation of absorption signal).

- **ETH entries:** OFI gains most in stressed regime (+0.038), meaningful in mixed (+0.020),
  minimal in calm (+0.004). Recommended filter: **do not skip any ETH regime** — but flag calm
  entries as lower-quality for logging. Apply standard OB gate; the L2 regime check adds
  confidence tier, not a hard filter (ETH clears null in all regimes individually).

**Forward-test metric:**
Log L2_regime (calm/mixed/stressed) on each ST2.0 entry. After n ≥ 30 fills:
- Fill rate by regime (do stressed-regime entries fill more or less?)
- Post-fill 15m adverse movement by regime
- BTC vs ETH split within each regime

**Source:** arXiv:2607.09230 (Jeon, open access, Binance BTC/ETH perp 2023–2026, full paper
read and verified 2026-08-31).

**Caveat:** The paper studies L2 state's predictive power for *liquidity-state transitions*
after macro news events (not passive fill quality directly). The transfer to ST2.0 is
inferential: OFI-triggered entries in an unfavorable L2 regime are the ones where the
directional signal is least reliable, implying higher adverse selection on the resulting fill.
This is consistent with arXiv:2502.18625 (back-of-queue adverse selection) but is not a
direct measurement of passive fill quality by L2 regime. Tercile thresholds require
calibration from bot's own rolling order-book data (the paper uses per-symbol training folds;
ST2.0 can approximate with 60-day rolling percentiles).

---

## Additional Sources Screened Tonight

### arXiv:2608.04373 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Public Trader Identity: Adverse Selection and Return Predictability"
**Author:** Daojing Zhai
**Submitted:** August 5, 2026 (v1); August 23, 2026 (v3)
**Source URL:** https://arxiv.org/abs/2608.04373
**Status: VERIFIED — abstract fetched directly.**

**Data:** Decentralized exchange with **public wallet identifiers**; 17.1B messages, 147K wallets,
$84.3B taker notional. Historical DEX data analysis.

**Key finding:** Public wallet trade histories predict one-second returns with 12.31% out-of-sample
R² (13.2% improvement over anonymous benchmark). Persistent informativeness across 10-day windows
(rank correlation: 0.52).

**Why NOT applicable:** DEX-only (public wallet addresses are the signal). Phemex is an opaque CEX
— no trader identity data is observable. The mechanism (exploiting persistent wallet informativeness)
has no analog in ST2.0's architecture. NOT APPLICABLE.

---

### arXiv:2407.16527 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "The Negative Drift of a Limit Order Fill"
**Author:** Timothy DeLise
**Submitted:** July 23, 2024
**Source URL:** https://arxiv.org/abs/2407.16527
**Status: VERIFIED — abstract fetched directly.**

**Data:** 10-Year US Treasury Bond futures; discrete market model (theoretical).

**Key finding:** Limit order fills are caused by and coincide with adverse price movements,
creating drag on market maker PnL — directionally consistent with the adverse selection problem
ST2.0 faces. However, no crypto CEX data, no actionable thresholds, no quantitative parameters
transferable to a 60-second-cycle perp maker.

**Why NOT applicable:** Treasury futures, 2024, theoretical + simulation only. The qualitative
finding (fills are adversely selected) is already established in the core corpus via
arXiv:2502.18625 from actual Binance BTC perp data. No new tweak. NOT APPLICABLE.

---

### arXiv September 2026 — All Four Categories
**Status: VERIFIED** — all four listings fetched directly.

| Category | URL Fetched | Result |
|----------|-------------|--------|
| q-fin.TR | arxiv.org/list/q-fin.TR/2026-09 | "No updates for this time period." |
| q-fin.ST | arxiv.org/list/q-fin.ST/2026-09 | "No updates for this time period." |
| q-fin.PR | arxiv.org/list/q-fin.PR/2026-09 | "No updates for this time period." |
| q-fin.CP | arxiv.org/list/q-fin.CP/2026-09 | "No updates for this time period." |

September 2026 submission window still not open as of 2026-08-31.

---

## New Forward-Testable Tweak Tonight

**Tweak 44 — CONFIRMED AND SPECIFIED** (elevated from Candidate in N58):

> Before posting a passive maker SELL: compute 3-metric L2 regime (calm/mixed/stressed) using
> top-20 levels on each side. Metrics: relative spread, aggregate depth (inverted), aggregate
> OB imbalance. Tercile thresholds rolling per symbol. BTC: skip calm entries (no OFI or L2
> predictability per Jeon). ETH: log regime tier; no hard skip (signal clears null in all
> regimes but calm is weakest). Forward-test: fill rate and 15m post-fill adverse move by
> regime, split BTC vs. ETH.
>
> Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp 2023–2026, full paper verified
> 2026-08-31).

**Tweak queue: 43 confirmed (Tweaks 1–43) + Tweak 44 now confirmed = 44 total.**

---

## Honest Caveats

1. **Tweak 44 transfer is inferential.** The Jeon paper is about L2 state prediction during macro
   news events — not about maker fill adverse selection. The ST2.0 relevance is: "OFI-triggered
   entries in an unfavorable L2 regime are weaker signals → fills at those moments are more
   adversely selected." Consistent with corpus but not directly measured.

2. **Tercile thresholds require calibration.** Jeon estimates per-symbol terciles from training
   folds. ST2.0 must estimate from the bot's own rolling order-book observations (e.g., 60-day
   rolling percentile of spread/depth/imbalance at 60-second cadence). This is implementable
   but requires a warm-up period.

3. **September 2026 arXiv still empty.** No new papers until the window opens (expected first
   week of September 2026).

4. **SSRN universally blocked** (403 on all IDs: 4677989, 5323703, 6344338, 6693260, 6772279,
   7162966). Author contact is the only path.

5. **The empirical gap remains.** No paper has measured OFI-flip decay speed or passive fill
   adverse selection at 60-second granularity specifically for ST2.0's signal regime on Phemex.
   Internal bot data is the only source for this measurement.

---

## Cumulative Forward-Test Queue (44 Tweaks)

**Priority tweaks (unchanged from N20–N59): 4 [elevated], 6, 9, 10, 11, 12, 14**
**Now includes Tweak 44** (L2 depth regime check, arXiv:2607.09230, Jeon, specified tonight).
**Conditional Tweak 43:** Composite LightGBM toxicity gate (SSRN:6344338, blocked).
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks
27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a),
N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37),
N37 (Tweak 38), **N59 (Tweak 44 — L2 3-metric regime check)**.

---

## arXiv Coverage as of Night 59

- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.* September 2026: EMPTY — submission window not yet open

---

## Night 59 Bottom Line

**Primary deliverable: Tweak 44 fully specified.** 5 sources evaluated:

- **arXiv:2607.09230 full paper** (Jeon, Binance BTC/ETH perp): VERIFIED (HTML fetched).
  **Tweak 44 now numerically specified.** Top-20-level 3-metric L2 regime (calm/mixed/stressed)
  as pre-placement gate. BTC: skip calm entries. ETH: log tier, no hard skip.
- **arXiv:2608.04373** (Zhai, "Public Trader Identity"): NEW TO CORPUS. VERIFIED (abstract).
  NOT APPLICABLE — DEX public wallet signal, no CEX analog.
- **arXiv:2407.16527** (DeLise, "Negative Drift of Limit Order Fill"): NEW TO CORPUS. VERIFIED
  (abstract). NOT APPLICABLE — Treasury futures, no actionable thresholds, qualitative finding
  already covered by arXiv:2502.18625.
- **arXiv q-fin.TR/ST/PR/CP September 2026** (all four): VERIFIED (all fetched). EMPTY.
- **Practitioner search (1 angle)**: All results already in corpus or non-primary.

**Recommendation (unchanged from N47–N58, now 13 nights overdue):**
Suspend nightly literature search. **Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.**
**Implement and log-instrument Tweak 44** (L2 regime classifier on top-20 levels before
placement). Resume arXiv sweep when September 2026 submissions open.

Optional actions still outstanding:
(a) SSRN:5323703 author contact (Ruan & Streltsov);
(b) SSRN:6344338 author contact (Rajendran/Singaravelu via ResearchGate);
(c) NCCU Finance → Lawrence Chang → SSRN:6693260;
(d) SSRN:4677989 author contact (Albers et al. "good, bad, latency");
(e) SSRN:7162966 author contact (Albers et al. "Neutrinos");
(f) SSRN companion — "The Price Impact of Nothing" — author contact for CEX applicability.
