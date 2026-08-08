# ST2.0 Execution Optimization — Night 39
**Date:** 2026-08-08 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 38 Nights

N38 closed with: no new actionable tweak. Two papers verified (arXiv:2608.04373 — Hyperliquid DEX, not applicable; Frontiers Blockchain 2026 — VPIN weak for crypto, corroborative). Literature declared "substantially saturated" at N33 after exhaustive coverage of: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, and taker buy/sell variance.

Tonight searched four angles:
1. SSRN 6693260 (Lawrence Chang) — sixth access attempt via alternate URL (ssrn.com/abstract=6693260)
2. arXiv:2507.22712 — "Order Book Filtration and Directional Signal Extraction at High Frequency" (new paper in search results)
3. arXiv:2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure" (Binance Futures perp, SHAP, maker backtest)
4. Practitioner angle: IEX D-Limit / venue-level adverse selection reduction mechanisms (bacidore.com)
5. arXiv:2510.27334 — "When AI Trading Agents Compete" (cited in practitioner article re: meta-order flow)

**Net result tonight: Two verified papers partially new (arXiv:2602.00776 and bacidore.com practitioner piece). Neither yields a new forward-testable tweak — both are corroborative. Two other candidates not applicable (arXiv:2507.22712 — Indian stock futures; arXiv:2510.27334 — pure simulation). SSRN 6693260 — HTTP 403, sixth consecutive failure. No new actionable tweak tonight.**

---

## Papers Evaluated Tonight

### arXiv:2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure"
**Authors:** Not confirmed from fetch (arXiv preprint)
**Published:** February 2026. arXiv preprint.
**URL:** https://arxiv.org/html/2602.00776v1
**Dataset:** Binance Futures perpetual contracts. Five assets: BTC, LTC, ETC, ENJ, ROSE (market cap ranks 1, 20, 40, 60, 100 as of January 2022). Date range: January 1, 2022 – October 12, 2025. Frequency: 1-second. Features: order flow imbalance, bid-ask spreads, VWAP-to-mid deviations.

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Methodology:** CatBoost gradient-boosted decision trees with walk-forward time-series cross-validation. SHAP values for feature attribution. Optimizes both squared error (R²) and Generalized Mean-Absolute Directional Loss (GMADL). Includes both taker and maker strategy backtests.

**Key findings (from fetch):**

1. **OFI concavity at extremes (verbatim from fetch):**
> "Order flow imbalance shows 'predominantly monotone' effects with 'concavity at extremes.'"
Interpretation: at very high OFI values, the predictive return does not continue to scale linearly — it saturates or reverses. This is the empirical shape of OFI's predictive relationship.

2. **Maker adverse selection during flash crash (verbatim from fetch):**
> "A market maker who fails to widen their spread in response is essentially offering a subsidy to informed traders, leading to near-certain losses."
The maker backtest "accumulated unprofitable long positions through repeated bid-side fills during unidirectional price collapse" on October 10, 2025, validating adverse selection theory in a concrete live dataset.

3. **Cross-asset feature consistency (verbatim from fetch):**
> "The same engineered order book and trade features exhibit remarkably similar predictive importance and SHAP dependence shapes across assets"
Features transfer across BTC, LTC, ETC, ENJ, ROSE — stable microstructure patterns despite different market cap tiers.

4. **Taker dominance:**
> "Taker strategies outperformed makers during normal and extreme conditions."
This is the paper's overall practical conclusion on maker vs. taker strategies, consistent with prior literature.

5. **Wider spreads attenuate OFI signal:**
> "Wider spreads 'associate with attenuated predictive effects,' consistent with adverse selection costs."

**What this means for ST2.0:**

Finding 1 (OFI concavity at extremes) is the most directly relevant. ST2.0 fires on HIGH OFI (bid-heavy book being aggressively bought). If OFI's predictive relationship is concave at extreme values, then the most extreme OFI entries — the entries that "look most like absorption" on a raw metric — may actually be the point where the expected short-term return is lower or even negative (adverse selection: the largest, most committed buyers pushing to extreme OFI are the ones who continue). This is the mechanistic explanation for why Tweak 4 (fill-time elevation flag) and Tweak 6 (post-fill alpha decay log) remain the highest-priority diagnostics: the OFI concavity means "more OFI is not always better" and extreme-OFI fills are precisely the adversely selected ones.

**Assessment: VERIFIED. Corroborative only.** All three relevant findings — OFI concavity, maker adverse selection under flash conditions, and cross-asset feature consistency — are consistent with and corroborative of the prior 38 nights' coverage. The OFI concavity finding was implicit in "OFI diminishing returns" (in the covered list since N1) and is now supported by a Binance Futures perp-specific SHAP analysis across 5 assets and 3.75 years of 1-second data. No new metric, no new gate, no new tweak.

---

### Practitioner Piece — "Three Innovative Ways to Reduce Adverse Selection"
**Source:** Bacidore & Associates. Jeff Bacidore (former head of trading research at Goldman Sachs, NYSE, and IEX).
**URL:** https://www.bacidore.com/post/iex-d-limit-intelligentcross-and-m-elo-three-innovative-ways-to-reduce-adverse-selection
**Status: VERIFIED** — full content fetched and analyzed.

**Summary of mechanisms reviewed:**

Three venue-level adverse selection reduction mechanisms, all confirmed non-applicable to Phemex CEX:

1. **IEX D-Limit** — Uses a Crumbling Quote Indicator (CQI) to detect imminent adverse price movement and automatically reprice passive limit orders with a 350-microsecond speed bump advantage. Requires: exchange-level CQI computation, latency speed bump, IEX venue.

2. **IntelligentCross** — Periodic batch matching (millisecond delay) to prevent stale-price exploitation. Requires: venue's matching engine to be modified.

3. **Nasdaq M-ELO** — Both sides commit to a mandatory 10-millisecond rest period before execution at the then-prevailing midpoint. Requires: counterparty consent and venue infrastructure.

**Key confirmed conclusion (verbatim from fetch):**
> "None of these mechanisms are viable without exchange infrastructure support. All three depend on venue-level controls (speed bumps, matching engines, or mandatory delays) that individual traders cannot replicate."

**Relevance for ST2.0:** This confirms the structural constraint that has been implicit since the N1 synthesis: without exchange cooperation, speed edge, or rebate structure, the only levers available to ST2.0 for reducing adverse selection are **entry timing** (choosing WHEN to place based on observable pre-fill signals) and **price offset** (where within the spread to post). Cancel/reprice requires either speed (not available) or exchange CQI support (not on Phemex). This is not a new finding but is now confirmed by a practitioner primary source with named authorship.

**Assessment: VERIFIED, confirms known structural constraint. Not a new tweak.**

---

### arXiv:2507.22712 — "Order Book Filtration and Directional Signal Extraction at High Frequency"
**URL:** https://arxiv.org/html/2507.22712v1
**Dataset:** National Stock Exchange of India (NSE). BANKNIFTY index futures. Three trading dates in January 2021. Tick-by-tick data, millisecond precision.

**Verification status: VERIFIED** — HTML fetched.

**Assessment: NOT APPLICABLE.** Indian stock index futures, not crypto perpetual futures. No fill quality or adverse selection content. No forward-testable rule for a crypto maker.

---

### arXiv:2510.27334 — "When AI Trading Agents Compete: Adverse Selection of Meta-Orders by RL-Based Market Making"
**Authors:** Ali Raza Jafree, Konark Jain, Nick Firoozye.
**URL:** https://arxiv.org/abs/2510.27334
**Dataset:** None — pure simulation using a Hawkes Limit Order Book model. No real exchange data.

**Verification status: VERIFIED** (abstract confirmed).

**Key verbatim claim:**
> "medium-frequency traders are increasingly subject to adverse selection by high-frequency trading agents" and "slippage costs incurred by medium-frequency traders are likely to increase over time."

**Assessment: VERIFIED but NOT APPLICABLE.** Simulation only, no real crypto exchange data, no fill quality analysis, no forward-testable execution rule. The finding about MFT adverse selection increasing over time is a theoretical concern but not actionable without empirical grounding in crypto perp specifically.

---

### SSRN 6693260 — Lawrence Chang (attempt #6)
**Status:** HTTP 403 Forbidden — sixth consecutive failed access attempt. Still unverified.

The alternative URL format (ssrn.com/abstract=6693260 vs papers.ssrn.com/sol3/papers.cfm?abstract_id=6693260) produced the same result. All details remain unverified search-snippet paraphrases only.

**Recommendation:** The author (Lawrence Chang) is at National Chengchi University (NCCU), Taiwan. Search for their NCCU institutional page or Google Scholar profile to find a non-SSRN hosted copy. If the paper has been submitted to a journal since May 2026, it may also be accessible via journal preprint server.

---

## New Forward-Testable Tweak Tonight

**None.** All verified papers tonight are either not applicable or corroborative of existing coverage. Tweak queue remains at 42 (unchanged).

The arXiv:2602.00776 OFI concavity finding (Binance Futures perp, 1s data, 2022–2025) adds empirical SHAP-grounded confirmation to the existing "OFI diminishing returns" finding, specifically confirming the concave shape at the high end — but this is already the mechanism that Tweaks 4, 6, and 9 are designed to measure. No new tweak is warranted.

---

## Honest Caveats

1. **Night 39, literature saturation confirmed.** All search queries are returning papers from the same N1–N38 pool plus non-applicable new papers. The specific problem domain (passive maker adverse selection for short-reversion on crypto perp CEX, small size, no speed, no rebate) is now exhaustively covered at this search depth.

2. **arXiv:2602.00776 OFI concavity finding:** The specific SHAP analysis across 5 Binance perp assets over 3.75 years is the strongest empirical grounding for "OFI diminishing returns" found in 39 nights. But it does not add a new metric — it validates the mechanism behind tweaks already in the queue.

3. **bacidore.com confirms structural constraint:** The only levers for ST2.0 (no speed, no exchange cooperation) are pre-fill entry timing and price offset. This was the N1 synthesis conclusion; it is now practitioner-confirmed.

4. **SSRN 6693260 remains open.** This is the sixth consecutive 403. NCCU institutional repository or Google Scholar author page is the recommended next access attempt.

5. **42 tweaks queued, 0 deployed across 39 nights.** No new tweak tonight. The research loop has reached genuinely diminishing returns. Deployment of priority tweaks (4, 6, 9, 10, 11, 12, 14) + log tweaks (36, 37 conditional, 38 conditional) is the live-data path forward — not more literature search.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N38): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 39 Bottom Line

**No new actionable execution tweak tonight.** Papers verified:

1. **arXiv:2602.00776** (Binance Futures perp, 5 assets, 1s data, Jan 2022 – Oct 2025): OFI concavity at extremes confirmed via SHAP analysis — corroborates existing "OFI diminishing returns" coverage; maker adverse selection during flash crash directly observed. Taker dominates maker in backtests. No new metric.

2. **bacidore.com practitioner piece** (IEX D-Limit, IntelligentCross, M-ELO): All three adverse selection reduction mechanisms require venue-level controls. Confirmed: the only levers available to ST2.0 are entry timing and price offset. No new tweak.

Not applicable: arXiv:2507.22712 (Indian stock futures), arXiv:2510.27334 (pure simulation).
Still blocked: SSRN 6693260 (Lawrence Chang, attempt #6 — 403).

**Recommendation:** After 39 nights of literature research, deploy priority tweaks 4, 6, 9, 10, 11, 12, 14. Add log-only tweaks 36 (1 line), 37 (3–4 lines, conditional on SSRN access), and 38 (3–5 lines, conditional on ws_feed.py tape buffer check) in the same session. Move the research focus from literature search to live-data fill labeling — 30+ labeled fills are the prerequisite for validating or discarding all 42 queued tweaks.
