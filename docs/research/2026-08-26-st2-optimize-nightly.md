# ST2.0 Execution Optimization — Night 56
**Date:** 2026-08-26 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 55 Nights

N55 flagged SSRN:7162966 ("Neutrinos of the Order Book", Albers et al. 2026) as a new-to-corpus
DEX paper (Hyperliquid data), blocked by 403. Tonight's scope:

1. **arXiv q-fin.CP August 2026 full listing** — this category was never fully screened in N1–N55
2. **arXiv:2510.27334** — new paper ID surfaced in a search snippet, not in prior corpus
3. **Practitioner sweep (4 new search angles):** post-only repricing/chasing, OFI flip maker
   timing, maker fill quality short-reversion, and general August 2026 crypto execution
4. **HFT Advisory Substack — "Six Market Microstructure Signals"** — practitioner piece surfaced
   in OFI search, not previously screened

**Net result:** q-fin.CP August 2026 (31 papers) now fully screened — 0 applicable. arXiv:2510.27334
screened — NOT APPLICABLE. HFT Advisory piece screened — NOT APPLICABLE. All web searches returned
only already-in-corpus papers. **0 new verified actionable tweaks. 23rd consecutive night without a
new verified actionable tweak. Tweak queue unchanged at 42.**

---

## Sources Evaluated Tonight

### arXiv q-fin.CP August 2026 — Full Listing (31 Papers)
**Verification status: VERIFIED** — listing fetched directly from arxiv.org/list/q-fin.CP/2026-08.

All 31 papers screened by title and description. Categories covered: implied volatility surface
generation (flow matching), battery storage optimization, AI interest rate forecasting, transport
geometry for variance surfaces, diffusion models in finance survey, synthetic LOB evaluation
(LOB-ID), COS-tensor-train options pricing, Itô signature dynamic hedging, CAT bond KAN pricing,
market microstructure dynamics generative model (M3), McKean–Vlasov financial time series,
arbitrage detection, inelastic market calibration, hedging realism, volatility risk premium
learning-to-rank, and various cross-listed papers on DeFi, exchange rates, token economies,
options pricing, RL stock trading, portfolio choice, concentrated liquidity, DEX routing, and
Ethereum validator economics.

**LOB-adjacent papers screened (not applicable):**
- *LOB-ID* (synthetic market data evaluation via inception distance) — about generative model
  quality, not maker fill adverse selection. No actionable tweak.
- *M3: State-Event Generative Foundation Model for Market Microstructure Dynamics* — generative
  model for synthetic LOB sequences; no maker execution measurement or adverse selection content.
- *FlowLOB: Efficient and Controllable Limit Order Book Generation* — flow-matching LOB generator;
  no adverse selection measurement. Cross-listed.

**Assessment: 31/31 screened, 0 applicable. arXiv q-fin.CP August 2026 now fully screened.**
All four relevant August 2026 arXiv categories (q-fin.TR, q-fin.PR, q-fin.ST, q-fin.CP) are now
complete. No new papers expected until September 2026 submissions open.

---

### arXiv:2510.27334 — RL Market Making and Adverse Selection via Hawkes LOB
**Status: VERIFIED — abstract fetched from arxiv.org.**

Title appears to be an RL-based study of how market making agents exploit adverse selection from
medium-frequency traders. The methodology uses a **Hawkes Limit Order Book simulation model**
(not real exchange data). Direct quote from fetched content: *"we use reinforcement learning (RL)
within a Hawkes Limit Order Book (LOB) model in order to replicate the behaviours of high-frequency
market makers."*

**Why NOT applicable:** Simulation-only; no real crypto exchange data. The paper's adverse
selection angle is from the market maker *extracting* from a medium-frequency trader, not a slow
directional trader posting passively into a CEX perp book. No mechanism, threshold, or tweak
transferable to ST2.0.

**Assessment: VERIFIED (abstract). NOT APPLICABLE — Hawkes simulation, no CEX crypto data.**

---

### Practitioner Sweep — 4 Search Angles
**Searches run (all verified via web search tool):**
1. "passive limit order adverse selection post-only maker fill crypto perpetual 2026 arxiv"
2. "order flow imbalance OFI flip maker timing queue position crypto CEX perpetual execution 2026"
3. "post-only repricing limit order chasing adverse selection crypto futures maker 2026"
4. "maker fill quality passive execution optimization short-reversion crypto perp 2026 site:arxiv.org"

**Results:**

| Hit | Status |
|-----|--------|
| arXiv:2502.18625 (Market Maker's Dilemma, Binance BTC perp) | Core paper — in corpus since synthesis |
| arXiv:2602.00776 (Bieganowski, crypto microstructure patterns) | Already in corpus — screened N50 |
| arXiv:2607.28323 (Optimal Execution with Passive Market Impact) | Already in corpus — screened N52 |
| arXiv:1610.00261 (Limit Order Strategic Placement, adverse selection + latency) | Core paper — in corpus since synthesis |
| arXiv:2409.12721 (Lalor & Swishchuk, CME simulation) | Screened N53 — NOT APPLICABLE |
| Educational / exchange explainers (BingX, finchtrade, cow.fi) | Discarded — non-primary |
| Quantt, INCRYPTED, emergentmind OFI guides | Discarded — educational, no primary data |

**Assessment: All applicable hits already in corpus. Practitioner search saturated for the
24th consecutive night.**

---

### HFT Advisory Substack — "Six Market Microstructure Signals That Fire Before the Price Print"
**URL:** https://hftadvisory.substack.com/p/six-market-microstructure-signals
**Status: VERIFIED — page fetched.**

The six signals described are: (1) cancel-side asymmetry (T+0), (2) refresh-latency widening
(T+0–10ms), (3) VPIN elevation (T+50ms), (4) multi-level LOB imbalance (T+100ms), (5) top-of-book
spread widening (T+500ms), (6) print and queue position (T+1s).

**Why NOT a new verified tweak:**
- This is a practitioner blog post, not a primary research source. No exchange data, no sample
  sizes, no reproducible methodology cited. The signals described are the same OFI/VPIN/queue
  taxonomy already in the corpus from arxiv:2502.18625 and arXiv:1610.00261.
- Crypto content is explicitly marked as requiring "venue-specific tuning rather than portable
  calibration." No specific claims about maker execution, post-only fills, or passive adverse
  selection in crypto perpetuals.
- Signal timing (T+0 to T+1s) is HFT-grade — irrelevant to a 60-second-cycle bot with no
  latency edge.

**Assessment: NOT APPLICABLE. Practitioner taxonomy piece; no primary data, no new tweak.**

---

## New Forward-Testable Tweak Tonight

**None verified.**

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **All four August 2026 arXiv q-fin categories now fully screened** (TR: N51, PR+ST: N53,
   CP: tonight). No new papers are available until September 2026 submissions open.

2. **SSRN remains universally blocked** (403 on all IDs attempted across N1–N56:
   4677989, 5323703, 6344338, 6693260, 6772279, 7162966). Author contact is the only
   remaining path to these papers.

3. **23rd consecutive night without a new verified actionable tweak.** The recommendation to
   suspend nightly literature search and deploy priority tweaks has now been made for 10
   consecutive nights (N47–N56) without action.

4. **The empirical gap remains the binding constraint.** No paper in 56 nights has measured
   OFI-flip decay speed at 60-second granularity in a crypto CEX perpetual. This is
   ST2.0-specific and requires internal fill-log measurement from the bot's own data — not
   findable in external literature.

5. **arXiv September 2026 listings have not yet opened.** The next viable arXiv sweep is
   when September submissions appear (expected first week of September 2026).

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N56): **4 [elevated], 6, 9, 10, 11, 12, 14**
**Cascade-blocking tweak class: RETIRED** (dual confirmation: arXiv:2607.27070 N46 +
arXiv:2608.03616 N47).
**Conditional candidate: Tweak 43** — composite LightGBM toxicity gate using 5-second OFI
features, 1-hour rolling adaptive threshold (SSRN 6344338, Rajendran & Singaravelu).
CONDITIONAL on full paper access.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks
27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a),
N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 —
conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 56 Bottom Line

**No new actionable execution tweak tonight.** 6 sources evaluated:

- **arXiv q-fin.CP August 2026** (31 papers): VERIFIED. **NEW: category fully screened for
  first time.** 0 applicable. All four August 2026 q-fin categories (TR/PR/ST/CP) now complete.
- **arXiv:2510.27334** (RL + Hawkes LOB market making): VERIFIED (abstract). **NEW TO CORPUS.**
  NOT APPLICABLE — simulation only, no real crypto exchange data.
- **Practitioner sweep (4 angles)**: All results already in corpus or non-primary. Saturated.
- **HFT Advisory Substack "Six Signals"**: VERIFIED (fetched). NOT APPLICABLE — practitioner
  taxonomy, HFT latency regime, no primary data for crypto CEX passive maker.

**arXiv coverage as of Night 56:**
- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers) ← NEW TONIGHT

**Final recommendation (unchanged from N47–N55, now 10 nights overdue on execution):**
Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
Resume arXiv sweep in September 2026 when new submissions appear.
Remaining optional actions:
(a) SSRN:5323703 author contact (Ruan & Streltsov);
(b) SSRN:6344338 author contact (Rajendran/Singaravelu via ResearchGate);
(c) NCCU Finance → Lawrence Chang institutional email → one attempt for SSRN:6693260;
(d) SSRN:4677989 author contact (Albers et al. "good, bad, latency" preprint);
(e) SSRN:7162966 author contact (Albers et al. "Neutrinos" — 2026 DEX paper).
