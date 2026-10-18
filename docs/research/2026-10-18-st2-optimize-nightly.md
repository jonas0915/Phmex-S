# ST2.0 Execution Optimization — Night 92 (2026-10-18)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–82 across Nights 1–91. Night 91 (2026-10-17): Tweak 82 (FIFO time-to-fill queue classification, arXiv 2609.13597). Night 90: Tweak 81 (robust volume Z-score burst detector). Night 89: Tweak 80 (quarter-hour proximity gate, arXiv 2607.09426). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Papers re-surfaced and confirmed already in corpus (rejected):**
- arXiv 2609.18019 (Model-Free Passive Execution via Order-Level Shadowing) — in corpus since Night 77.
- arXiv 2607.28323 (Optimal Execution with Passive Market Impact, Barzykin et al.) — in corpus since Night 91.
- arXiv 2609.13597 (Same Book, Different Fills, Danait/NVIDIA) — in corpus since Night 91.
- arXiv 2502.18625 (Market Maker's Dilemma, Binance BTC perp) — in corpus since synthesis.
- arXiv 2605.06405 (Funding-Aware Optimal Market Making for Perpetual DEXs) — in corpus since Night 86.
- arXiv 2603.24137 (Bridging the Reality Gap in LOB Simulation) — fetched tonight; S&P 500 equities, simulation-only, no passive fill adverse selection quantification. **Not actionable.** Excluded.

---

**What is genuinely NEW tonight:**

**arXiv 2608.04373 (Liu, Parlour, Spatt — "Public Trader Identity: Adverse Selection and Return Predictability," Hyperliquid, July–August 2026)**

This paper is NOT in the prior corpus. Search history and prior night coverage lists (Nights 89–91) confirm no prior fetch. Fetched tonight from https://arxiv.org/html/2608.04373.

**Data:** Hyperliquid (decentralized perpetuals exchange), July 1–27, 2026. Ten most active perpetual markets; primary analysis on BTC, ETH, SOL. 17.1B Level-4 messages, 14.3M aggressive orders, 147,113 wallets, $84.3B taker notional. Independent replication on December 2025 data (26.3B messages).

**What the paper does:** Hyperliquid publishes counterparty wallet IDs on all fills — a data asset unavailable on centralized exchanges. The paper ranks wallets by short-horizon markout (10s) and tests whether tracking top-ranked wallets improves return forecasts for passive market makers.

**Direct quotes from fetched HTML (abstract and results section):**

> "A decentralized exchange now publishes the counterparty."
> "Wallets retain that ordering across adjacent ten-day windows, with a rank correlation of 0.52."
> "Public wallet histories therefore carry short-horizon price information that anonymous order-book data leave unmeasured."

**Key quantitative results (verified from fetched page):**

| Cohort | 10-second markout | Rank correlation (adjacent 10-day windows) |
|--------|-------------------|--------------------------------------------|
| Top decile | 2.11 bp | 0.52 |
| Top ventile | 3.11 bp | — |
| Fifteenth ventile and below | ~flat (near zero) | — |

- Adding top-decile wallet identity block raises out-of-sample R² from 10.88% to 12.31% at one second (+13.2% relative gain, t = 9.2).
- The increment is larger at arrivals (fills), rising from 1.43 to 2.47 pp of one-second R².
- Markout gain decays to ~3% relative at 30 seconds under ridge regression.
- **Adverse selection is structurally concentrated:** markouts are flat through the 15th ventile — the cost sits in a narrow top-5–10% tail.

**Why NOT directly actionable for Phemex ST2.0:**

The finding depends on public wallet-level order attribution, which is unique to Hyperliquid's on-chain architecture. On Phemex (CEX), taker identities are anonymous — the wallet-identity mechanism does not transfer. The paper itself states: "Turning the forecasting gain into profits would require a dynamic execution and market-making model, which it does not build."

**What the paper adds structurally (cross-venue inference):**

The paper is the strongest crypto-native empirical confirmation to date that adverse selection on perpetual futures passive fills is **structurally concentrated in a narrow informed-taker tail**. On Hyperliquid, that tail is the top 5–10% of wallets by markout. On Phemex (anonymous), the same tail exists but is unobservable by wallet. The question for ST2.0 is: *what observable market-state features correlate with the presence of top-decile informed takers at the time of fill?*

The prior corpus already addresses this indirectly:
- arXiv 2502.18625 (Binance BTC perp): front-of-queue fills = −0.058 bp adverse selection; back-of-queue = −0.775 bp → the informed-tail fills cluster in back-of-queue events.
- arXiv 2609.13597 (Night 91): queue position uncertainty bounds ≈ 7–8 pp completion.
- arXiv 2608.21888 (Tweak 79): taker-flow intensity percentile correlates with post-fill direction.

arXiv 2608.04373 does not provide a new gate for Phemex, but it confirms the structural direction: **adverse selection concentrates in events where an informed agent decides to fill a resting passive order.** Those events tend to coincide with the tail of book-absorption intensity — exactly what Tweaks 79/80/81/82 are designed to measure.

**Classification:** New paper, verified, NOT actionable for Phemex CEX. Structurally corroborating — adds empirical weight to existing corpus direction without producing a new executable tweak.

---

## (b) Concrete Forward-Testable Execution Tweak

**No new tweak this night.**

arXiv 2608.04373 does not produce an executable tweak for Phemex ST2.0. The wallet-identity mechanism is unavailable on CEX. No other new paper surfaced tonight that clears the verification bar and has an actionable translation to ST2.0's execution context.

The undeployed priority stack from Night 91 is unchanged. The highest-priority undeployed items remain:

1. **Tweaks 47/65** — queue rank proxy at entry time + time-to-fill logging at close. These address the #1 structural weakness (no queue position) and are prerequisites for bps analysis. Zero execution risk.
2. **Tweak 75/76/77/78** — OBI upper-bound gate, realized-vol gate, σ-adaptive cancel threshold, gate hysteresis. Deployable as a bundle.
3. **Tweak 79** — tape intensity gate (shadow-deployable independently).
4. **Tweaks 80/81/82** — quarter-hour proximity, robust volume Z-score, FIFO time-to-fill classification. All shadow-log-only, zero execution risk.

The research series has now covered 82 tweaks across 92 nights. As noted in Night 90, the academic literature available to this problem is becoming saturated. Future nights should prioritize finding the SSRN 6693260 (BTC perp flow-adjusted bid-absorption) open-access pathway or other practitioner sources that might yield Phemex-specific calibration data.

---

## (c) Caveats and Unverified Items

1. **arXiv 2608.04373 uses Hyperliquid DEX data, NOT Phemex CEX.** Hyperliquid's on-chain wallet attribution is not available on any CEX. The quantitative results (2.11 bp markout, 13.2% R² gain) are Hyperliquid-specific and cannot be assumed to hold on Phemex in magnitude. The structural direction (concentration in informed tail) is cross-venue by theory.

2. **"Queuing and inventories in limit order markets" (ScienceDirect 2025, pii/S1386418125000229):** Returned in search as potentially new material on cancellation timing. HTTP 403 on full-text fetch; content unverified. Not acted upon. Could be re-attempted via alternative access.

3. **Persistent unverified leads (unchanged from Night 91):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403 persists.
   - Microstructure Lab Substack (post-sweep delayed entry / LOB resilience, 180,590 sweep events, Binance/GateIO/OKX): Still paywalled.
   - arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77): Still partially fetched.

4. **Literature saturation assessment:** The standard search angles (q-fin.TR arXiv, practitioner microstructure blogs, SSRN crypto perp execution) are producing diminishing returns. New 2026 papers on passive maker execution for crypto perpetuals are returning the same prior-corpus papers or are equity/DEX venue-mismatched. The open research frontier for this series has shifted from literature discovery to empirical deployment (deploying Tweaks 47/65 to generate ST2.0-specific fill data).

---

## Summary

| Item | Description | Status |
|------|-------------|--------|
| arXiv 2608.04373 (Liu/Parlour/Spatt) | New to corpus: Hyperliquid wallet-level adverse selection confirmation. Adverse selection concentrates in top-5–10% informed-taker tail (2.11 bp markout at 10s, R² gain +13.2%). NOT actionable for Phemex (CEX, anonymous takers). Structurally corroborates existing corpus direction. | NEW — VERIFIED (HTML fetched, direct quotes + quantitative table extracted); NOT actionable for Phemex |
| Tweak 83 | None proposed this night. | N/A |

**No new forward-testable execution tweak tonight.**

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry + LOB recovery timing (Microstructure Lab Substack) | TBD | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | PARTIALLY FETCHED |

**Undeployed priority stack (unchanged from Night 91):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold
5. Tweak 78 — Gate hysteresis
6. Tweak 79 — Tape intensity gate
7. Tweak 74 — stale-gate per-cycle re-validation
8. Tweak 72 — funding-window gate
9. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
10. Tweak 71 — transient-order OBI filter
11. Tweak 80 — Quarter-hour proximity shadow log
12. Tweak 81 — Robust volume Z-score shadow log
13. Tweak 82 — FIFO time-to-fill queue classification

**Research series status:** 82 tweaks, 92 nights. Literature saturation increasing. Empirical deployment of Tweaks 47/65 is the highest-leverage next step — without ST2.0's own fill data broken out by queue proxy and time-to-fill, the research series cannot advance from "proposed" to "confirmed" on its most important hypotheses.
