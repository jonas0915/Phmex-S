# ST2.0 Execution Optimization — Night 81 (2026-10-04)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–69 across Nights 1–80. Academic literature declared saturated Night 77, confirmed N79–80.

---

## Literature Status

**arXiv q-fin.TR October 2026: EMPTY.**
Fetched `https://arxiv.org/list/q-fin.TR/2026-10` directly — server returned "No updates for this time period." Third consecutive month with zero new submissions to q-fin.TR. The four confirmed persistent gaps (Phemex-calibrated adverse-selection measure, crypto-perp OFI decay study, CEX-perp passive-maker markout, optimal delayed-posting timing) remain unaddressed in the peer-reviewed literature.

---

## New Findings (Night 81)

### Tweak 70 — Cancel-Side Asymmetry Pre-Entry Filter (NEW)

**Source:** HFT Advisory Substack, "Six Market Microstructure Signals That Fire Before the Price Print: A Practitioner's Execution Quality Architecture." URL: https://hftadvisory.substack.com/p/six-market-microstructure-signals — fetched and verified 2026-10-04.

**Verified claim (direct quote):**
> "one side of the book is draining limit orders faster than the other, while the spread itself has not yet moved"

The signal (called "Cancel-Side Asymmetry" by the author) identifies informed maker repositioning *before* price moves. It operates at T+0 — observable in the same snapshot as the entry decision — and is categorically distinct from OBI (depth snapshot), VPIN (volume toxicity), OFI (trade-side flow), and spread widening (which the author explicitly labels "too late for avoidance strategy").

**Application to ST2.0 (short-reversion setup):**
ST2.0's signal condition is "bid-heavy book being aggressively lifted." In that setup, if the *ask side* is simultaneously draining (limit sells being canceled) faster than the bid side is draining, it means informed sellers are pulling their offers ahead of continued upside — a continuation signal, not absorption. The practitioner threshold cited is ≥3–5× imbalance in cancellation rates.

**Proposed Tweak 70:** At the entry check, compute a real-time cancellation-rate ratio:
```
cancel_ratio = ask_cancel_rate_5s / bid_cancel_rate_5s
```
Block the entry if `cancel_ratio > 3.0` (asks draining faster → sellers retreating → upside continuation risk). A complementary condition: if bids are canceling at >3× ask-cancel rate, this weakens the "bid-heavy" premise and should also block entry.

**Priority:** Medium. This requires tracking per-side order-cancel events in the WS feed, which ST2.0's existing `ws_feed.py` tape stream may partially support. Unlike Tweaks 47/65 (queue rank), this does not require level-3 order IDs — only per-side cancel event counts, available from L2 diff streams.

**Caveat:** Source is practitioner (not peer-reviewed). The 3–5× threshold is from the author's experience, not from a calibrated study. No crypto-perp-specific evidence cited. Must be treated as a hypothesis requiring forward data collection before deploying as a hard gate.

---

### Tweak 71 — Transient-Order Filter for OBI Computation (NEW, marginal)

**Source:** arXiv 2507.22712, "Order Book Filtration and Directional Signal Extraction at High Frequency," Anantha, Jain, Maiti. URL: https://arxiv.org/html/2507.22712v1 — fetched and verified 2026-10-04.

**Verified claims (direct quotes):**
> "removing orders that reflect fleeting, deceptive, or noncommittal intent" through "structurally transient activity" elimination

> "Filtered aggregate order flow showed only modest changes relative to the unfiltered benchmark, but applying filters specifically to parent orders of executed trades revealed systematically stronger directional association"

The authors tested three filtering schemes on tick-by-tick BANKNIFTY index futures data (NSE India, Jan 2021):
- **Lifetime filter (ℱT):** Remove orders surviving <{100, 500, 1000}ms
- **Modification-count filter (ℱM):** Remove orders with >{1, 3, 5} modifications
- **Modification-time filter (ℱMT):** Retain only orders with ≥{50, 100, 200}ms between final two modifications

Quantitative result: Modification-time filtering improved the Pearson correlation between filtered OBI and short-horizon returns by ~11.3% (from 0.01018 to 0.01133). Excitation norms under filtering "rise sharply" in some sessions (e.g., 24.7352 vs 9.6726 unfiltered), but the R² improvement was "relatively flat" (8.37–8.43).

**Application to ST2.0:** The current OB imbalance gate computes depth from a raw Phemex L2 snapshot. If quote-stuffing noise from short-lived orders is contaminating the OBI reading, applying a 500ms lifetime filter to orders feeding the computation could yield a cleaner gate. The 11.3% correlation improvement is modest but not trivial as a noise-reduction step.

**Priority:** Low. The improvement is modest and the data is BANKNIFTY (Indian equity index futures, 2021) — not crypto perps. Authors explicitly decline to assert generalizability: *"Rather than asserting universal market microstructure conclusions, our aim is to demonstrate how a multi-layered diagnostic framework can be applied."* No crypto-specific validation. This tweak is worth logging but should sit behind Tweaks 47/65 and the higher-priority queue data first.

---

## Not Applicable (Investigated, Rejected)

**Multicoin Capital "Adverse Selection Rules Everything Around Me" (Feb 2026):**
Verified quote: *"market makers could quote two different prices, and in the tighter price they would have the option to cancel a trade within 1 second after matching."*
This is the post-fill cancellation mechanism flagged as a hypothesis in Night 1 (then paywalled). It is implemented in DeFi/DEX contexts (DFlow, LFJ Liquidity Book). The article explicitly states that *"perps use inventory management and risk limits instead of the maker-cancellation model."* Phemex CEX does not expose a post-fill cancellation API — not actionable for ST2.0.

**arXiv 2507.22712 / 2507.22712v1:** Covered above. BankNifty data, not crypto-perp. Included as Tweak 71 with low priority.

**ScienceDirect "Order flow and cryptocurrency returns" (2026):** HTTP 403, cannot fetch. Cannot verify — excluded.

---

## Summary

| Tweak | Description | Priority | Source Type | Status |
|-------|-------------|----------|-------------|--------|
| 70 | Cancel-side asymmetry pre-entry gate | Medium | Practitioner (Substack) | NEW |
| 71 | Transient-order lifetime filter for OBI | Low | Academic (BankNifty, not perps) | NEW |

**Undeployed priority stack unchanged:** Tweaks 47/65 (queue rank logging) remain the gating prerequisite for all downstream calibration. Tonight adds two new entries to the undeployed stack; neither displaces 47/65.

**Academic literature posture:** Three consecutive months of zero q-fin.TR submissions. The binding constraint (no queue position, no rebate, back-of-queue fills) remains structurally unaddressed by published research for CEX perp-specific passive execution at small size.
