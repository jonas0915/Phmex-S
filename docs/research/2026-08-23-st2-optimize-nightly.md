# ST2.0 Execution Optimization — Night 53
**Date:** 2026-08-23 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 52 Nights

N52 declared the arXiv q-fin.TR August 2026 listing complete (17/17), the practitioner search
saturated for the 19th consecutive night, and made its final recommendation to suspend nightly
literature search. Tonight expanded into two unexplored arXiv categories (q-fin.PR and q-fin.ST,
never before fetched as full listings) plus a newly surfaced Quantitative Finance journal paper
(Albers et al. 2025) not in any prior night's corpus.

**Sources evaluated tonight (all new by paper ID):**

| Source | Verdict |
|--------|---------|
| arXiv q-fin.PR August 2026 — 12 papers | 0 applicable |
| arXiv q-fin.ST August 2026 — 28 papers | 0 applicable (2608.10852 fetched + screened) |
| arXiv 2403.02572v2 (Lokin & Yu, FX fill probabilities) | NOT APPLICABLE (FX spot only) |
| arXiv 2409.12721 (Lalor & Swishchuk, CME futures simulation) | NOT APPLICABLE (CME only) |
| Albers et al. 2025, *Quantitative Finance* 25(6):919–947 | **NEW — partially relevant, taker-focused** |

**Net result:** 1 new paper identified and verified at abstract level. **0 new maker execution
tweaks. 20th consecutive night without a new verified actionable tweak. Tweak queue
unchanged at 42.**

---

## Sources Evaluated Tonight

### arXiv q-fin.PR August 2026 — Full Listing (12 papers)
**Verification status: VERIFIED** — listing fetched and screened.

All 12 papers assessed: options pricing models (Black-Scholes extensions, SOFR derivatives,
variance gamma, barrier options, multi-asset COS method), credit risk, volatility risk premium
decompositions, and asset-sale optimal stopping.

Only cross-listed paper: **2608.04373** ("Public Trader Identity: Adverse Selection and Return
Predictability") — already screened in N39 and N48. NOT APPLICABLE.

**Assessment: 12/12 screened, 0 applicable. q-fin.PR August 2026 now fully screened.**

---

### arXiv q-fin.ST August 2026 — Screening of Unscreened Papers

q-fin.ST (Statistical Finance) August 2026 had 28 total papers. Most cross-listed into q-fin.TR
or q-fin.CP and were already screened in N47–N52. Unscreened paper found and fetched:

**arXiv:2608.10852 — "Universality and Heterogeneity of Stylized Facts in Cryptocurrency and
Equity Markets"**
Authors: Jaesung Kim, Changhee Cho, Jae Woo Lee.
Fetched: abstract verified.

**Abstract (verbatim excerpt):** "We analyze high-frequency data (2020–2025) using the
Complexity–Entropy Causality Plane (CECP) and directed horizontal visibility graphs (directed
HVG) to uncover complex temporal patterns and time-directed structures in the return series...
cryptocurrencies appear more locally random than the equity benchmark during ordinary periods,
yet exhibit significantly stronger directional time-irreversibility around high-visibility return
events."

**Why NOT applicable:** Return-series information-theoretic analysis (CECP, directed HVG).
No order book, no order flow, no maker/taker dynamics, no adverse selection measurement,
no fill quality content.

**Assessment: VERIFIED, NOT APPLICABLE. Statistical stylized-facts paper; zero execution content.**

---

### arXiv:2403.02572v2 — "Fill Probabilities in a Limit Order Book with State-Dependent Stochastic Order Flows"
Authors: Felix Lokin, Fenghui Yu.
Submitted March 2024, revised February 2026. Fetched: abstract verified.

**Abstract (verbatim excerpt):** "We model the limit order book within a general state-dependent
stochastic framework... We validate the proposed model through extensive numerical experiments
using real foreign exchange spot market data."

**Why NOT applicable:** FX spot market only. No mention of cryptocurrency, CEX, adverse selection,
maker fill rates, OFI, or post-only orders. The fill probability framework is theoretically
interesting but validated exclusively on FX spot data and is not calibrated to crypto perp
CEX dynamics. The exponential fill-probability decay with distance-from-mid is already in
the prior corpus (deep-lob-2021, synthesis file).

**Assessment: VERIFIED, NOT APPLICABLE. FX spot framework only, no crypto content.**

---

### arXiv:2409.12721 — "Market Simulation under Adverse Selection"
Authors: Luca Lalor, Anatoliy Swishchuk.
Fetched: abstract verified.

**Abstract (verbatim excerpt):** "We study the effects of fill probabilities and adverse fills
on the trading strategy simulation process. We specifically focus on a stochastic optimal
control market-making problem and test the strategy on ES (E-mini S&P 500), NQ (E-mini
Nasdaq 100), CL (Crude Oil) and ZN (10-Year Treasury Note)... Many previous works aim to
measure different types of adverse selection in the limit order book (LOB), however, they often
simulate price processes and market orders independently. This has the ability to largely inflate
the performance of a short-term style trading strategy."

**Why NOT applicable:** CME traditional futures (ES, NQ, CL, ZN) only. No cryptocurrency,
no perpetual futures, no CEX content. The simulation-inflation finding (adverse selection inflates
backtest performance) is covered territory from the synthesis. Market-making context is bilateral
(bid + ask simultaneously), not directional passive short entry.

**Assessment: VERIFIED, NOT APPLICABLE. CME futures only; no crypto or CEX content.**

---

### Albers, Cucuringu, Howison & Shestopaloff (2025) — "The good, the bad, and latency: exploratory trading on Bybit and Binance"
**Journal:** *Quantitative Finance*, Taylor & Francis, vol. 25(6), pages 919–947, June 2025.
**DOI:** 10.1080/14697688.2025.2515933
**URL:** https://ideas.repec.org/a/taf/quantf/v25y2025i6p919-947.html
**Verification status: VERIFIED at abstract level** — full text not accessed (paywalled).

**Abstract (verbatim, from IDEAS/RepEC):**
"We present the findings of a large-scale live trading experiment involving the placement of
millions of market orders sent at a high frequency on two cryptocurrency exchanges, Bybit and
Binance. We analyze the execution outcomes of these orders in comparison to the expected outcome
based on the most recent snapshot of the Limit Order Book (LOB) at the time of order submission
for two execution modes: one using market orders and the second using marketable limit orders
aiming at the best price. Discrepancies between the actual and expected outcomes are due to
intermittent LOB updates during a time span resulting from delays on the exchange, delays on
the trader's end, or communication delays between the trader and the exchange. We show these
discrepancies are strongly correlated with market factors such as volatility, latency, and LOB
liquidity. Notably, we find a consistent disadvantage to the trader, pointing to an adverse
selection effect for taker orders: profitable orders (as measured by short-term future PnL
returns) tend to achieve worse-than-expected outcomes, while unprofitable orders typically
achieve their expected (adverse) outcomes. In the case of market orders, this translates to a
worsening of fill prices, while marketable limit orders suffer from a substantial probability
of failing-to-fill-immediately."

**Why NOT a new verified maker execution tweak:**

The paper studies **TAKER execution** (market orders and marketable limit orders), not passive
post-only maker orders. ST2.0 posts on the MAKER side — the other side of the trades this paper
studies. The adverse selection finding ("profitable taker orders get worse fill prices") is the
mirror image of what arXiv:2502.18625 shows from the maker side ("fills cluster when price
continues moving against the passive order") — conceptually convergent but not additive.

The finding that "discrepancies are correlated with volatility, latency, and LOB liquidity" is
potentially relevant: in low-liquidity LOB states, even large taker orders fail to match
immediately — but from the MAKER side this would mean passive limit orders in thin books have
higher fill probability AND higher adverse price movement risk. This is the core adverse-selection
tradeoff documented in the June-20 synthesis. No new threshold or mechanism quantified from the
abstract alone.

**What IS new:** This is the **first large-scale live-exchange crypto CEX taker execution study**
in the 53-night corpus. The scale (millions of orders, Bybit + Binance, real execution) is
beyond anything in prior nights. The paper may contain LOB liquidity thresholds or volatility
regime breakpoints that are actionable from the maker perspective — but only readable from the
full text.

**Assessment: VERIFIED (abstract). PARTIALLY RELEVANT — large-scale crypto CEX execution study,
taker-focused. Full text needed for any maker-applicable findings. NOT a new actionable tweak
without full paper access.**

---

## New Forward-Testable Tweak Tonight

**None verified.**

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **Albers et al. (2025) full text is paywalled** (Taylor & Francis / Quantitative Finance).
   The abstract confirms crypto CEX content (Bybit + Binance, live trading, LOB dynamics) but
   the primary focus is taker execution. A free preprint may exist on arXiv — the authors
   (Cucuringu, Howison, Shestopaloff) are Oxford/Toronto affiliated and frequently post
   preprints. Recommended action: search arXiv for author names + "latency Bybit Binance" to
   locate preprint version. This is now the most promising unread candidate in the corpus.

2. **q-fin.PR and q-fin.ST August 2026 listings now fully screened.** Combined with q-fin.TR
   (17/17, N51): all three relevant August 2026 arXiv categories are complete. No new papers
   expected until September 2026 listings appear.

3. **SSRN 5323703 and 6344338 remain blocked (403).** Unchanged from N52.

4. **20th consecutive night without a new verified actionable tweak.** The recommendation to
   suspend nightly literature search and deploy priority tweaks has now been made for 6
   consecutive nights without action.

5. **Empirical gap remains the binding constraint.** No paper in 53 nights has measured
   OFI-flip decay speed in crypto CEX perpetual futures at 60-second granularity. This is
   not findable in the literature — it requires internal measurement from ST2.0's own fill log.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N53): **4 [elevated], 6, 9, 10, 11, 12, 14**
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

## Night 53 Bottom Line

**No new actionable execution tweak tonight.** 7 sources evaluated:

- **arXiv q-fin.PR August 2026** (12 papers): VERIFIED, 0 applicable. Category now fully screened.
- **arXiv q-fin.ST August 2026** (28 papers): VERIFIED, 0 applicable. 2608.10852 screened; category now fully screened.
- **arXiv:2403.02572v2** (Lokin & Yu, FX fill probability): VERIFIED, NOT APPLICABLE. FX spot only.
- **arXiv:2409.12721** (Lalor & Swishchuk, CME simulation): VERIFIED, NOT APPLICABLE. CME only.
- **Albers et al. 2025** (*Quantitative Finance* 25(6), Bybit+Binance live taker experiment):
  **VERIFIED (abstract). NEW TO CORPUS. PARTIALLY RELEVANT — taker-focused, full text needed.**
- **arXiv:2608.10852** (Kim, Cho, Lee, stylized facts): VERIFIED, NOT APPLICABLE. Return-series stats.

**All three August 2026 arXiv q-fin categories (TR/PR/ST) now fully screened.**

**New recommended action (added tonight):** (d) Search arXiv for Albers, Cucuringu, Howison,
Shestopaloff preprint of "The good, the bad, and latency" — may contain LOB liquidity thresholds
and volatility breakpoints actionable from the maker perspective.

**Final recommendation (unchanged from N47–N52, now 6 nights overdue on execution):**
Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
Remaining optional actions:
(a) SSRN 5323703 author contact (Ruan & Streltsov — perpetual futures market quality);
(b) SSRN 6344338 author contact (Rajendran/Singaravelu via ResearchGate);
(c) NCCU Finance → Lawrence Chang institutional email → one attempt for SSRN 6693260;
**(d) [NEW] arXiv preprint search for Albers et al. 2025 "The good, the bad, and latency".**
