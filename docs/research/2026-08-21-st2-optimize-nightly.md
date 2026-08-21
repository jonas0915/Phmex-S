# ST2.0 Execution Optimization — Night 51
**Date:** 2026-08-21 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 50 Nights

N50 screened the complete August 2026 q-fin.TR listing (16 papers), August 2026 q-fin.CP (17 papers), and several search-surfaced candidates — declaring the literature saturated for the 17th consecutive night. Tonight's scope:

1. **Updated August 2026 q-fin.TR listing re-fetch** — found 1 paper (2608.19389) not in N50's 16-paper count
2. **New practitioner source** — aligrithm.com, July 2, 2026 (Ali H. Askar): "Adverse Selection is Adverse Selection: Porting Fast-Fills-Are-Bad-Fills to FX and Futures" — new by URL, fetched and verified
3. **New Frontiers 2026 paper** — fbloc.2026.1811716 (Pindza 2026), "Microstructure Alpha: Hierarchical Learning and Cross-Asset Transfer" — Binance spot + perp, Aug 2025–Feb 2026
4. **SSRN 5323703 retry** — Ruan & Streltsov, "Perpetual Futures Contracts and Cryptocurrency Market Quality" — HTTP 403 Forbidden; not accessible

**Net result:** 3 new sources evaluated, 0 applicable. **18th consecutive night without a new verified actionable tweak. Tweak queue unchanged at 42.**

---

## Sources Evaluated Tonight

### arXiv:2608.19389 — "Concentrated Liquidity Provision: a Reinforcement Learning Perspective"
**Published:** August 2026 (new paper ID; N50 listed 16 papers, this is the 17th).
**URL:** https://arxiv.org/abs/2608.19389
**Verification status: VERIFIED** — abstract fetched.

Formulates dynamic liquidity provision on constant-product AMMs (Uniswap V3 style) as a stochastic impulse control problem, solved via RL.

**Why NOT applicable:** This is exclusively about AMM/DEX concentrated liquidity (DeFi), not CEX order books or crypto perpetual futures maker execution. No fill quality, adverse selection, or passive placement findings.

**Assessment: VERIFIED, NOT APPLICABLE. DeFi AMM paper; zero relevance to CEX passive maker execution.**

---

### aligrithm.com — "Adverse Selection is Adverse Selection: Porting Fast-Fills-Are-Bad-Fills to FX and Futures"
**Published:** July 2, 2026 | **Author:** Ali H. Askar
**URL:** https://aligrithm.com/adverse-selection-is-adverse-selection-porting-fast-fills-are-bad-fills-to-fx-and-futures/
**Verification status: VERIFIED** — page fetched successfully.

**Core thesis** (direct quote from fetch): "adverse selection is a property of who chooses to trade against you, not of what the contract pays at the end." The piece argues fill quality degrades universally with fill speed, across prediction markets (Polymarket CLOB), spot FX (EURUSD), and traditional futures (bunds).

**Fill-quality data table presented (exact as fetched):**

| Order Type | Average Fill Quality |
|---|---|
| Market orders | −0.72 |
| Limit orders < 1 minute | −0.31 |
| Limit orders > 10 minutes | +0.43 |

**Why NOT a verified new tweak:**
- The quantitative data (−0.72/−0.31/+0.43) is **UNVERIFIED** — the second fetch confirmed the data is "illustrative rather than formally sourced research": no market specified for the table, no sample size, no data period, no methodology for "fill quality" metric, no order direction specified (buy vs sell). Numbers are not citable as a primary source.
- **No crypto perpetual futures data.** The article tests prediction markets, EURUSD, and bund futures only.
- **Conceptual claim is covered territory.** The principle — fast fills are adversely selected, slow fills represent liquidity-provision fills — is established in the prior 50-night corpus from a stronger primary source: arXiv:2502.18625 (Binance BTC perp, verified, 3-0) showed fills cluster at extreme imbalance exactly when price continues moving against the passive short. That paper provides the on-point crypto-perp empirical backing; this practitioner piece adds no verified data beyond what already exists.

**Assessment: VERIFIED content, UNVERIFIED data, NOT APPLICABLE as a new tweak. Concept already in corpus via arXiv:2502.18625.**

---

### Frontiers in Blockchain fbloc.2026.1811716 — "Microstructure Alpha: Hierarchical Learning and Cross-Asset Transfer in Cryptocurrency Markets" (Pindza, 2026)
**URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full
**Verification status: VERIFIED** — full article fetched.

**Dataset:** Binance spot + perpetual futures; BTC, ETH, SOL, AVAX, LINK, DOT; August 2025 – February 2026; 1-minute bars, ~3.4M observations.

**Key findings (directly from fetch):**
- Microstructure signals carry "genuine but weak information content" — not exploitable at standard retail fee levels.
- Spot Sharpe ratios: −31 to −52 (annualized). Futures Sharpe ratios: −10 to −18.
- "Spread proxy (range-based) emerges as most statistically significant predictor."
- VPIN: "higher values in spot markets, suggesting greater informed trading activity."
- Cross-asset transfer: gradient boosting overfits under proper temporal controls — "known hazard in financial ML."
- To overcome fees would require: "(i) lower fee tier (market-maker rebates, VIP-9), (ii) longer holding horizon, (iii) portfolio netting."

**Why NOT a new tweak:** Confirms the fee-trap diagnosis from the June-20 synthesis. VPIN and spread-proxy findings are covered territory (multiple prior nights). No new passive maker fill or placement-timing findings. Negative Sharpe results on futures reinforce the synthesis's "execution-trapped at this scale" conclusion without adding actionable guidance.

**Assessment: VERIFIED. No new maker execution tweak. Confirmatory of prior corpus; VPIN topic covered.**

---

### SSRN 5323703 — Ruan & Streltsov, "Perpetual Futures Contracts and Cryptocurrency Market Quality" (2026)
**Retry status:** HTTP 403 Forbidden. Full paper inaccessible.
**Assessment: UNVERIFIED. Cannot evaluate.**

---

## Updated August 2026 q-fin.TR Listing (Complete — 17 Papers)

N50 counted 16 papers. The listing now shows 17 total:

| arXiv ID | Title | Verdict |
|----------|-------|---------|
| 2608.00631–2608.00988 (7 papers) | Various — binary markets, FX, HFT equities, math | NOT APPLICABLE (covered N47/N48) |
| 2608.02917 | AMMs as Verifiable Portfolio Products | NOT APPLICABLE (covered N48) |
| 2608.04373 | Public Trader Identity: Adverse Selection and Return Predictability | NOT APPLICABLE (covered N39/N48) |
| 2608.05373 | Intraday Options Manipulation Detection | NOT APPLICABLE (covered N48) |
| 2608.07690–2608.09188 (4 papers) | OTC OFI/skew, Hawkes-Heston, price-limited markets, cross-venue | NOT APPLICABLE (covered N47/N48) |
| 2608.13096 | FlowLOB | NOT APPLICABLE (covered N48/N49) |
| 2608.15640 | Blockchain censorship critique | NOT APPLICABLE (covered N50) |
| 2608.18195 | Multi-Level Market Making with RL | NOT APPLICABLE (covered N50) |
| **2608.19389** | **Concentrated Liquidity Provision via RL** | **NEW TONIGHT — NOT APPLICABLE (DeFi AMM)** |

**17/17 August 2026 q-fin.TR papers now screened. 0 applicable.**

---

## New Forward-Testable Tweak Tonight

**None verified.**

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **aligrithm.com fill-quality data is illustrative, not rigorous.** The -0.72/-0.31/+0.43 breakdown by fill speed cannot be cited as a primary source — no methodology, no sample size, no market specified. The conceptual claim (fast fills adversely selected) is correct and documented in stronger form in arXiv:2502.18625. Do not use the aligrithm numbers in any backtest or implementation rationale.

2. **arXiv:2608.19389 is the 17th paper in August 2026 q-fin.TR** — N50's count of 16 was incomplete. Evaluated tonight: AMM/DEX paper, not applicable. August 2026 q-fin.TR is now fully screened at 17/17.

3. **SSRN 5323703** (Ruan & Streltsov, perp futures market quality): 403'd. Given the search engine summary mentions "adverse selection risk" and "widening quoted spreads" in response to it, this could be relevant. Suggested path: author contact or institutional proxy.

4. **18th consecutive night without a new verified actionable tweak.** The recommendation from N47–N50 stands without change: suspend nightly literature search; deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14 to generate labeled fill data.

5. **Empirical gap remains the binding constraint.** No paper in 51 nights has measured OFI-flip decay speed in crypto CEX perpetual futures at 60-second granularity. This is not findable in the literature — it requires internal measurement from ST2.0's own fill log.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N51): **4 [elevated], 6, 9, 10, 11, 12, 14**
**Cascade-blocking tweak class: RETIRED** (dual confirmation: arXiv:2607.27070 N46 + arXiv:2608.03616 N47).
**Conditional candidate: Tweak 43** — composite LightGBM toxicity gate using 5-second OFI features, 1-hour rolling adaptive threshold (SSRN 6344338, Rajendran & Singaravelu). CONDITIONAL on full paper access. Do not implement until verified.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 51 Bottom Line

**No new actionable execution tweak tonight.** 3 new sources evaluated:

- **arXiv:2608.19389** (Concentrated Liquidity Provision via RL, August 2026): VERIFIED, NOT APPLICABLE. DeFi AMM paper; no CEX content.
- **aligrithm.com July 2026** (Askar, "Adverse Selection is Adverse Selection"): VERIFIED content, fill-speed data UNVERIFIED (no methodology). Conceptual claim covered by arXiv:2502.18625.
- **Frontiers fbloc.2026.1811716** (Pindza 2026, Binance spot + perp, Aug 2025–Feb 2026): VERIFIED, NOT APPLICABLE. Confirms fee-trap and VPIN coverage; no new maker execution guidance.
- **SSRN 5323703** (Ruan & Streltsov): UNVERIFIED (403).

**August 2026 q-fin.TR listing now complete at 17/17 papers (N50's 16-paper count was missing 2608.19389).**

**Final recommendation (unchanged from N47–N50):** Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14. Remaining optional actions: (a) SSRN 5323703 author contact (Ruan & Streltsov); (b) SSRN 6344338 author contact (Rajendran/Singaravelu via ResearchGate); (c) NCCU Finance → Lawrence Chang's institutional email → one attempt for SSRN 6693260.
