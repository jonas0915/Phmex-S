# ST2.0 Execution Optimization — Night 36
**Date:** 2026-08-05 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 35 Nights

N35 closed with: MDPI 2227-7072/14/5/103 partially verified via IDEAS/RePec abstract (funding-window spread peaks, Tweak 36 — log `entry_utc_hour`). Literature was declared "substantially saturated" at N33 after exhaustive coverage of micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset microstructure transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, and passive market impact.

Tonight searched four angles not previously covered:
1. Fill-time / time-to-execution distribution as an adverse selection predictor
2. "Flow-adjusted absorption" — aggressive flow normalized by near-touch depth, vs raw OFI alone
3. State-dependent order flow predictiveness across liquidity regimes (crypto futures)
4. Altcoin perp price discovery speed / mean reversion timeline literature

**Net result tonight: One candidate new paper found (SSRN, 403 blocked — UNVERIFIED); one partially-verified new finding from arXiv. One forward-testable log tweak proposed, conditional on SSRN access. arXiv:2607.09230 partially verified but limited applicability.**

---

## Papers Evaluated Tonight

### SSRN 6693260 — "Do Order-Book States Predict Passive-Buy Toxicity? Evidence from BTC Perpetual Futures"
**Author:** Lawrence Chang  
**Published:** May 2, 2026. SSRN working paper.  
**URL:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6693260  
**Dataset:** Binance Level 2 order-book snapshots merged with aggregate trade records. BTC perpetual futures. Specific date range not confirmed.

**Verification status: UNVERIFIED — SSRN returns HTTP 403 Forbidden on two separate access attempts (main page, PDF direct link). All information below is extracted from search engine snippet summaries, which are likely AI paraphrases of the abstract, not verbatim quotes from the paper. Do not act on specific claims as if peer-reviewed.**

**What the search snippets claim (paraphrase, not quoted from paper):**

Per search engine summaries: the paper studies "whether economically interpretable local order-book conditions predict short-horizon future returns and passive-buy adverse-selection risk" in BTC perp. The framework summarizes local conditions via "recent directional order flow, near-touch bid-side absorption capacity, and liquidity-state fragility." The stated key finding: "a flow-adjusted bid-absorption proxy is substantially more informative than raw directional flow alone."

A second summary snippet: "higher recent sell pressure relative to best-bid depth predicts lower short-horizon future returns and higher passive-buy adverse-selection risk. The results suggest that passive-buy toxicity in crypto futures is best understood as a local imbalance between aggressive pressure and near-touch absorption capacity under fragile liquidity states."

**Why potentially relevant for ST2.0 (if verified):**

ST2.0 is a passive SELL, not a passive BUY. The mirror of passive-buy toxicity:
- Passive-buy toxicity is driven by: high sell pressure / thin bid-depth = fills when sellers are sweeping a fragile bid-side
- Passive-sell toxicity (ST2.0's problem) would be driven by: **high buy pressure / thin ask-depth** = fills when buyers are sweeping a fragile ask-side

The paper's proposed metric — "flow-adjusted absorption proxy" = aggressive directional flow / near-touch depth on the near side — if it works for passive buys, the same logic by symmetry should apply to passive sells. This is DISTINCT from:
- Raw OFI (bid volume − ask volume / total): does not normalize by near-touch depth
- Tape buy_ratio (fraction of last N trades that were buys): does not normalize by depth at all
- OB imbalance gate (±0.25): measures depth imbalance without incorporating trade flow rate

The new metric would be: `aggressive_buy_volume_Ns / ask_depth_top_K_levels` — how much recent aggressive buying has occurred relative to the ask-side's capacity to absorb it. If the ask-side is thin and being swept hard, a fill there is likely adversely selected (buyers committed to price and will push further up). If the ask-side is deep and buy volume is modest, absorption capacity was intact — a fill is more likely at the peak of pressure, consistent with reversion.

**Critical limitations:**
1. **SSRN 403 — UNVERIFIED.** Cannot access abstract, dataset details, methodology, or results table. All findings above are extracted from search engine summaries which may be AI-generated. The paper may not contain any of the quoted language verbatim.
2. **BTC perpetual only.** If verified, transfer to altcoin perps (INJ/AVAX/ARB) requires separate validation. Absorption dynamics on thin altcoin books may differ from BTC.
3. **Passive-buy → passive-sell mirror logic.** The mirroring is theoretically motivated (market microstructure is symmetric in principle) but not empirically validated in any paper found to date.
4. **"Informative" vs "actionable."** Even if the flow-adjusted absorption proxy is more informative than raw OFI, that does not imply using it as a gate improves execution — it may already be captured by the composite of existing tape gate + OB gate.

---

### arXiv:2607.09230 — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures"
**Author:** Joohyoung Jeon  
**Published:** July 2025–2026 preprint. arXiv.  
**URL:** https://arxiv.org/abs/2607.09230  
**Dataset:** Binance BTCUSDT and ETHUSDT futures. 2023–2026 timeframe. Top-20 L2 order book + trade-flow records.

**Verification status: PARTIAL — abstract and methodology sections accessed via arXiv HTML. Full paper numerical tables not deeply reviewed.**

**Verified findings (from arXiv HTML fetch):**

Abstract (paraphrased, not verbatim — page extract):
> "Building event-conditioned market models requires separating macro-event labels from persistent microstructure state. We study this distinction in Binance BTCUSDT and ETHUSDT futures from 2023-2026, combining top-20 L2 order book data, trade-flow records, and macro-event windows."

**Liquidity state definitions (verified):** Three descriptors: (1) relative bid-ask spread, (2) total depth across top-20 levels, (3) order-book imbalance across those levels — bucketed into "calm, mixed, or stressed" tercile-based categories.

**Key asymmetric finding (verified extract):**
> "For ETH it is present across calm, mixed, and stressed regimes and largest under stressed pre-event liquidity, whereas BTC shows only isolated five-minute passes and no regime that clears at both horizons."
> "For ETH the order-flow value is present in every regime and grows with liquidity stress. The increment rises monotonically from calm to mixed to stressed."

**What this means for ST2.0:**

The paper finds that order flow's predictive value is HIGHEST when the book is in a "stressed" liquidity state — defined as wide spread + low total depth + elevated imbalance. For altcoin perps (INJ/AVAX/ARB), which have structurally thinner books than BTC or ETH, the "stressed" state is likely more common and more persistent. If order flow (including buy pressure) is most informative precisely when the book is fragile, then ST2.0's entry gate — which fires on buy absorption in a bid-heavy book — is most likely to be meaningfully adversely selected under stressed liquidity (where fills are rare but meaningful if they occur).

This provides additional support for the **Tweak 33 (book-fragility gate)** already in the queue: block ST2.0 entries when total depth at best levels is below a threshold (indicating stressed liquidity where adverse fills are structurally larger).

**Critical limitations:**
1. **BTC/ETH only.** The paper explicitly notes "a genuine limit" — findings cannot be assumed to transfer to altcoin perps.
2. **Macro-event prediction context.** The paper studies whether order flow predicts liquidity-state transitions around macro events, not whether order flow predicts adverse selection on passive limit orders. Indirect connection to ST2.0's problem.
3. **ETH-vs-BTC asymmetry is "a two-point observation."** The authors' own caveat: "the ETH-versus-BTC asymmetry is a two-point observation rather than a population statement." Cannot extrapolate to altcoins.
4. **Preprint.** Not peer-reviewed at time of fetch.

---

### Other Candidates Evaluated (Non-Applicable)

**Bitcoin wild moves: Evidence from order flow toxicity and price jumps** (Kitvanitphasu et al., Research in International Business and Finance, Vol. 81C, 2026)  
Full abstract accessed via IDEAS/RePec (ideas.repec.org/a/eee/riibaf/v81y2026ics0275531925004192.html). Uses VPIN to predict Bitcoin price jumps via VAR modeling. Key finding: "VPIN significantly predicts future price jumps, with positive serial correlation observed in both VPIN and jump size." Time-zone and day-of-week effects identified. **Not applicable for ST2.0:** VPIN-as-jump-predictor is a different question from VPIN as a passive-maker adverse-selection gate. VPIN thresholds for maker gating have been searched for 33 nights without finding a primary source — this paper does not fill that gap (it studies VPIN → jumps, not VPIN → fill quality). VPIN remains unverified as a maker gate.

**Fill-time distribution papers (search angle #1):** Search for "passive limit order time-to-fill distribution adverse selection crypto perpetual arxiv 2025" returned arXiv:2502.18625 (the Market Maker's Dilemma, already in synthesis) and arXiv:2607.28323 (NASDAQ/FX, already covered N34). The survival-analysis fill-time modeling described in one snippet appears to refer to arXiv:2502.18625 which is the foundational paper in the synthesis. No new paper on fill-time as an adverse selection predictor was found.

**Altcoin price discovery speed (search angle #4):** Search returned market statistics sites (Datawallet, Coinperps) and Wiley Mathematical Finance (perpetual futures pricing theory, not microstructure). No new primary empirical paper on altcoin-specific price discovery speed or mean reversion timelines was found that is not already covered.

---

## New Forward-Testable Tweak Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 37 | **Flow-adjusted ask-absorption ratio log.** At signal time, compute and log `ask_absorption_stress = tape_buy_volume_60s / sum_ask_qty_levels_1_to_5` (total aggressive buy volume in last 60s tape, divided by the sum of ask-side quantity at the best 5 price levels as of signal time). Hypothesis: fills where this ratio is HIGH (aggressive buying against a thin ask-side) are more adversely selected than fills where this ratio is LOW (buying absorbed by a deep ask). If confirmed after 30+ fills: candidate pre-entry filter — block entry when ask_absorption_stress exceeds a threshold (exact threshold to be determined from data, not from the unverified paper). Cross-reference with existing OB gate (imbalance ±0.25) and tape gate (buy_ratio 0.45/0.55) — the hypothesis is that this ratio adds signal beyond what those gates capture. **CONDITIONAL on verifying SSRN 6693260 (Lawrence Chang paper) first.** If the paper is accessible and the core finding does not hold, this tweak loses its only empirical backing. Can be implemented as 3–4 lines of code using `ob.asks[:5]` (already available in the signal pipeline) and the existing tape buffer. | Lawrence Chang, "Do Order-Book States Predict Passive-Buy Toxicity? Evidence from BTC Perpetual Futures." SSRN 6693260, May 2026. SSRN HTTP 403 Forbidden — UNVERIFIED. All claims from search snippet paraphrases only. Treat as hypothesis-motivated, not empirically-backed until paper is accessed. | Conditional / queued | 3–4 lines |

---

## Honest Caveats

1. **Chang paper is UNVERIFIED.** Two SSRN fetch attempts returned HTTP 403. The "flow-adjusted bid-absorption proxy substantially more informative than raw directional flow" claim comes from search engine snippet summaries — likely AI paraphrases of the abstract, not verbatim text. The paper may not use this exact framing. Do not deploy Tweak 37 as a gate until the actual paper is read and the finding is confirmed. Log-only implementation carries zero risk; the gate is the conditional step.

2. **SSRN retry next session.** Try accessing via Google Scholar, ResearchGate, or the author's institutional page if SSRN is still 403.

3. **Tweak 37 may already be partially captured.** The existing OB imbalance gate (±0.25) measures depth imbalance; the tape gate (buy_ratio) measures flow direction. The "flow-adjusted absorption" ratio combines both but in a specific normalization. Whether this ratio adds independent signal beyond the composite of existing gates is an empirical question, not a derivable one.

4. **arXiv:2607.09230 (Jeon) is partially verified** but its primary relevance is as corroboration for Tweak 33 (book-fragility gate, already queued). No new tweak from it.

5. **41 tweaks queued, 0 deployed across 36 nights.** The binding constraint remains unchanged. The new Tweak 37 is log-only and adds 3–4 lines alongside any priority-tweak deployment session.

---

## Cumulative Forward-Test Queue (41 Tweaks — +1 Conditional)

Priority tweaks (unchanged from N20–N35): **4 [elevated], 6, 9, 10, 11, 12, 14**  
Tweak 37 added tonight — **conditional on verifying SSRN 6693260.**  
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), above (Tweak 37 — conditional).

---

## Night 36 Bottom Line

One candidate new paper found — SSRN 6693260 (Lawrence Chang, "Do Order-Book States Predict Passive-Buy Toxicity? Evidence from BTC Perpetual Futures," May 2026) — which proposes that a **flow-adjusted bid-absorption proxy** (aggressive directional flow / near-touch depth) is "substantially more informative than raw directional flow alone" for predicting passive-fill adverse selection. SSRN is HTTP 403 blocked; this finding is UNVERIFIED and comes only from search engine snippet paraphrases. If verified, the mirror for ST2.0 (passive SELL) would be a flow-adjusted ASK-absorption ratio = aggressive buy volume / ask-side depth, which is distinct from the existing OB imbalance gate and tape buy-ratio gate. Tweak 37: log this ratio at signal time (3–4 lines, conditional on paper access).

arXiv:2607.09230 (Jeon, BTC/ETH Binance, 2023–2026, partially verified): order flow predictiveness is highest under stressed liquidity, grows monotonically from calm → mixed → stressed. Corroborates existing Tweak 33 (book-fragility gate) but adds no new tweak; BTC/ETH only, altcoin transfer unvalidated.

**Recommendation unchanged:** Deploy priority tweaks 4, 6, 9, 10, 11, 12, 14. Add Tweak 37 log (3–4 lines) in the same session — after attempting SSRN access. Night 36: 41 tweaks queued (1 conditional), 0 deployed.
