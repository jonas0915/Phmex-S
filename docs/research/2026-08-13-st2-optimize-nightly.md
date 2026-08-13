# ST2.0 Execution Optimization — Night 44
**Date:** 2026-08-13 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 43 Nights

N43 closed with no new tweak (11th consecutive night, literature declared saturated since N33). Prior 43 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, short-term price reversal regime detection, sentiment regimes, ETH/BTC order flow asymmetry, sunshine trading / TWAP transparency (Hyperliquid), OFI shock dissipation speed (E-mini baseline), OFI concavity at extremes (Binance Futures 2022–2025).

Tonight searched four angles:
1. arXiv:2607.28323 (Optimal Execution with Passive Market Impact, July 2026) — not previously checked
2. SSRN 6693260 (Lawrence Chang, passive-buy toxicity) — 9th access attempt; ResearchGate + NCCU repository routes exhausted
3. "Bitcoin wild moves: Evidence from order flow toxicity and price jumps" (Kitvanitphasu et al., Research in International Business and Finance, 2026) — new paper in VPIN space
4. SSRN 6525818 (Ching-Lin Chang, "Synchronized Toxicity", March 2026) — new paper, appeared in search

**Net result tonight: Zero new applicable papers. arXiv:2607.28323 is equity/FX only. The Bitcoin toxicity paper is VPIN on Bitcoin spot (likely), unverifiable in full text. SSRN 6525818 is US equities only. SSRN 6693260 attempt #9 blocked. No new forward-testable execution tweak. Tweak queue unchanged at 42. This is the 12th consecutive night without a new actionable finding.**

---

## Papers Evaluated Tonight

### arXiv:2607.28323 — "Optimal Execution with Passive Market Impact"
**URL:** https://arxiv.org/html/2607.28323v1
**Published:** July 2026. arXiv preprint.
**Dataset:** NASDAQ equities (AMZN, TSLA, NFLX, ORCL, CSCO, MU, 2016) and LSEG FX spot (GBPUSD, AUDUSD, USDMXN, 2026).

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Key finding (verbatim from fetch):**
> "Fill intensity decays exponentially with distance from the midprice, and the short-term linear response of price changes to order flow imbalance" combine to produce passive impact rates that "decay exponentially with quote distance."

The paper derives a model for optimal passive execution where the trader chooses δ (distance from midprice) to balance fill probability against passive market impact accumulation. The key mechanism: resting limit orders themselves move the mesoscopic price against the poster. The optimal quote distance balances fill rate (decaying exponentially in δ) against this self-inflicted passive impact.

**Why NOT applicable to ST2.0:**
- Equity and FX datasets only. No crypto content anywhere.
- The framework assumes symmetric quote-distance optimization by market makers. ST2.0 posts a single directional passive short at signal inception — no iterative reposting or distance optimization.
- The "passive market impact" mechanism (own order moving price against poster) is a function of order size relative to book depth. At ST2.0's $15–$30 scale vs. crypto perp depth, this effect is likely negligible.
- The exponential fill-rate decay with distance is a useful stylized fact (confirms: posts closer to mid fill faster, posts away fill rarely), but this is already captured in ST2.0's post-only-at-spread design.

**Assessment: VERIFIED, NOT APPLICABLE.** Equity/FX only. No new execution tweak for ST2.0.

---

### SSRN 6693260 — Lawrence Chang (attempt #9)
**Status:** HTTP 403 Forbidden — ninth consecutive failed access.

**Routes tried tonight:** Direct SSRN URL; NCCU repository search (National Chengchi University — authorship confirmed from SSRN index snippet but no institutional preprint repository page found); ResearchGate author search ("Lawrence Chang" + crypto) → zero profile match.

**What is confirmed from search engine indexing only (NOT a primary source, DO NOT cite as fact):**
- Author: Lawrence Chang, NCCU affiliation
- Paper posted May 2, 2026 on SSRN
- Claimed dataset: Binance L2 order-book snapshots merged with aggregate trade records, BTC perpetual futures
- Claimed framework: three predictors of passive-buy adverse-selection risk — (1) recent directional order flow, (2) near-touch bid-side absorption capacity, (3) liquidity-state fragility
- Claimed main result: "flow-adjusted bid-absorption proxy is substantially more informative than raw directional flow alone"

**All above is search-engine-indexed snippet only.** Nine consecutive 403 errors across all access routes. No institutional repository copy found. Tweak 37 remains conditional on verification.

**Remaining access path:** Contact author directly via NCCU institutional email (if listed on NCCU department page). This is the only untried route after 9 attempts.

---

### "Bitcoin Wild Moves: Evidence from Order Flow Toxicity and Price Jumps"
**Authors:** Kitvanitphasu, Kyaw, Likitapiwat, Treepongkaruna
**Published:** Research in International Business and Finance, 2026
**URL:** https://ideas.repec.org/a/eee/riibaf/v81y2026ics0275531925004192.html
**Dataset:** Not confirmed (full text inaccessible). Likely Bitcoin spot/exchange data (abstract uses "Bitcoin" not "perpetual"; VPIN construction typically requires tick-level spot data).

**Verification status: PARTIALLY VERIFIED** — Abstract confirmed via UWA repository public metadata; full text behind paywall on ScienceDirect (403). The following is from the abstract/metadata only:

> "VPIN significantly predicts future price jumps, with positive serial correlation observed in both VPIN and jump size, suggesting persistent asymmetric information and momentum effects."

> "time-zone and day-of-week effects in VPIN, highlighting the role of global trading patterns"

**Why NOT new ground for ST2.0:**
1. VPIN topic was covered in prior nights as a general entry in the covered list. The specific finding here — VPIN predicts Bitcoin jump probability — is a directional result, not a passive maker execution result.
2. The paper studies Bitcoin spot (most likely). ST2.0 operates on Phemex crypto perp CEX. VPIN-to-jumps dynamics in spot may or may not transfer to perp.
3. No findings on passive maker adverse selection timing, fill rates, or OFI reversal. The paper is about jump forecasting using VPIN, not about how to time a passive short entry to reduce adverse selection.
4. "Persistent serial correlation in VPIN" is a useful context reminder (elevated toxicity begets elevated toxicity — a VPIN gate on entry could potentially be chained across consecutive signals), but this mechanism is already within the scope of Tweak 36 (log-only VPIN gate, queued N35).

**Assessment: PARTIALLY VERIFIED (abstract only). No new execution tweak. VPIN topic covered in prior nights; this paper adds a jump-forecasting angle not relevant to passive maker fill quality.**

---

### SSRN 6525818 — "Synchronized Toxicity: A High-Performance Framework for Latency-Adjusted Volume-Informed Trading"
**Author:** Ching-Lin Chang (distinct from Lawrence Chang)
**Published:** March 31, 2026 on SSRN
**URL:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6525818 (403; summary from search index only — NOT primary source)

**What is known from search indexing only (UNVERIFIED):**
- Introduces "VPIN_LAD" — a Latency-Adjusted, Depth-Weighted VPIN that uses deterministic OrderID matching via TotalView-ITCH message flows instead of Lee-Ready heuristic classification
- Identified problem: during high-velocity volatility shocks, standard VPIN saturates at 1.0 (maximum toxicity) due to misclassification lag — "phantom toxicity" caused by physical latency
- Fix: VPIN_LAD "safely collapses to standard theoretical bounds during stable markets and successfully preserves the true gradient of risk during severe liquidity crises"
- Dataset implied: US equities (TotalView-ITCH = NASDAQ proprietary feed; "SIP data" and "Lee-Ready algorithm" are US equity concepts)

**Why NOT applicable to ST2.0:**
- US equities infrastructure (TotalView-ITCH, SIP, Lee-Ready) has no equivalent on Phemex CEX.
- Phemex provides aggregate trade flow, not order-level IDs for deterministic classification.
- Even if the VPIN_LAD concept were ported, the paper falls within the already-covered VPIN topic space.

**Assessment: UNVERIFIED (search index only, 403). US equities only per infrastructure references. Not applicable to Phemex CEX. No new tweak.**

---

## New Forward-Testable Tweak Tonight

**None.** Zero new primary sources applicable to Phemex crypto perp passive maker execution.

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **SSRN 6693260 — 9 consecutive 403s; all automated access routes exhausted.** The last untried path is direct author contact (NCCU institutional email). This paper's claimed content — flow-adjusted bid-absorption proxy substantially more informative than raw directional flow, with near-touch bid-side absorption capacity as the key predictor of passive-buy adverse-selection risk — remains the single most directly applicable unverified finding in the 44-night corpus. If the author has a public email on the NCCU Finance/Quantitative Finance department page, one direct contact attempt is reasonable.

2. **SSRN 6525818 ("Synchronized Toxicity") is genuinely new to the covered list by paper ID**, but falls within the VPIN topic and is US equities only. No execution insight for ST2.0.

3. **Bitcoin wild moves paper (Kitvanitphasu et al., 2026)** is new by paper ID and is partially verified (abstract). Its finding — VPIN persistently predicts Bitcoin price jumps with positive serial correlation — is consistent with the already-queued Tweak 36 (log-only VPIN gate). No new standalone tweak.

4. **OFI decay speed in crypto perps remains the single most important unverified hypothesis** in the 44-night corpus. No primary source has been found for how fast OFI informativeness decays in crypto perpetual futures (E-mini: <1 second per arXiv:2508.06788; crypto perp: 5-30 seconds per unverified practitioner data). This gap is now confirmed unanswerable through public literature search — it requires proprietary labeled fill data, which only deploying priority Tweaks 4/6 can generate.

5. **44 nights, 42 tweaks, 0 deployed.** The 12th consecutive night without a new actionable tweak. Every accessible search path in the specific problem space (passive maker adverse selection, crypto perp CEX, small size, no speed, no rebate) has now been exhausted. The literature is genuinely saturated.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N44): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 44 Bottom Line

**No new actionable execution tweak tonight.** Four papers evaluated:

**arXiv:2607.28323** (Optimal Execution with Passive Market Impact, equities/FX, July 2026): VERIFIED, NOT APPLICABLE. Fill intensity decays exponentially with distance from midprice; passive orders themselves generate mesoscopic market impact. Equity/FX only — no crypto content.

**SSRN 6693260** (Lawrence Chang, BTC perp passive-buy toxicity): Attempt #9 = 403. NCCU affiliation confirmed, no repository copy found. Still the highest-value inaccessible paper in the corpus. Last access route: direct author contact via NCCU department page.

**Kitvanitphasu et al. (2026)** ("Bitcoin wild moves", Research in International Business and Finance): Abstract confirmed via UWA — VPIN predicts BTC price jumps with positive serial correlation. VPIN topic covered in prior nights; Bitcoin spot (likely), not perp. Full text behind ScienceDirect paywall. No new ST2.0 tweak.

**SSRN 6525818** (Ching-Lin Chang, "Synchronized Toxicity", March 2026): VPIN_LAD using TotalView-ITCH. US equities only. VPIN topic covered. Not applicable.

**Final recommendation after 44 nights:** Suspend literature search entirely. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14 and log-only Tweaks 36–38. Thirty labeled fills with post-fill alpha decay and OFI-at-fill logged are the only thing that can validate or discard the 42-item tweak queue. The OFI decay speed question — the single most important remaining hypothesis — cannot be answered without live fill data. Optional single action: check NCCU Finance department page for Lawrence Chang's institutional email and make one direct contact attempt for SSRN 6693260.
