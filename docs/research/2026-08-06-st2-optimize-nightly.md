# ST2.0 Execution Optimization — Night 37
**Date:** 2026-08-06 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 36 Nights

N36 closed with: SSRN 6693260 (Lawrence Chang, flow-adjusted ask-absorption ratio — UNVERIFIED/403, Tweak 37 conditional); arXiv:2607.09230 (Jeon, order flow predictiveness highest under stressed liquidity — corroborates Tweak 33). Literature was declared "substantially saturated" at N33 after exhaustive coverage of micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, and state-dependent order flow.

Tonight searched four angles not previously covered:
1. Order book resilience / replenishment speed after aggressive buy waves
2. Hawkes process / self-exciting order flow burst decay as entry timing signal
3. Liquidation cascade early-warning signals in crypto perpetual futures
4. Taker order-flow burstiness / variance as a conditional adverse selection filter

**Net result tonight: One genuinely new verified paper (arXiv:2607.27070, HTML accessed). One new forward-testable diagnostic tweak derived from it. One non-applicable verified paper (arXiv:2606.15715, Hyperliquid DEX). Two additional candidates blocked (TechRxiv 403, ScienceDirect 403). All other search results returned papers already covered in N1–N36.**

---

## Papers Evaluated Tonight

### arXiv:2607.27070 — "Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades"
**Author(s):** Not confirmed from fetch (arXiv preprint)  
**Published:** July 2026. arXiv preprint.  
**URL:** https://arxiv.org/html/2607.27070v1  
**Dataset:** Binance BTCUSDT USD-margined perpetual futures. Seven liquidation cascade events spanning May 2022 – October 2025 (including a record $19B event on October 10, 2025). 1-minute price data; 5-minute leverage/order-flow metrics. Approximately 17,600 rows per window for leverage metrics; ~88,000 bars per event window for price.

**Verification status: VERIFIED** — abstract and methodology sections accessed via arXiv HTML. Key claims below are extracted from the HTML fetch; some phrasing may be paraphrased rather than verbatim.

**Key findings (from HTML fetch):**

Abstract finding (verbatim from fetch):
> "The one regularity surviving all events with data is a compression of taker order-flow variance"

This compression "passes a 300-onset placebo test (Fisher-combined p≈5×10⁻⁶)" but represents "a population-level precursor, not a per-event alarm."

**What "taker order-flow variance compression" means:**

Definition (from paper): The *variance* of the taker buy/sell ratio falls before cascades — the opposite of what naive early-warning intuition would predict (which expects rising variance before crashes). During the build-up to an endogenous squeeze, buying pressure becomes more *monotone* (consistent, low-variance directional flow) rather than noisy.

Measurement specifics (verified from HTML):
- Rolling window: 0.5–4 hours
- Detrending window: 2–16 hours
- Trend quantified via Kendall rank correlation τ, significance threshold p < 0.05
- Metric: lag-1 autocorrelation and variance on rolling windows

**Two-type cascade structure (verified):**

> "Anticipated or endogenous-buildup cascades carry a price signature; pure exogenous shocks carry none (February 2025 shows no precursor in any variable) or relocate it to leverage/flow (October 2025)."

The mechanism: variance compression can only build over time in events that develop over hours to days. Abrupt exogenous shocks (repriced within minutes of unscheduled announcements) leave no window for this signal to form.

**Explicit limitation (authors' own words, from fetch):**
> "Seven events, a single venue, and moderate effect sizes throughout."

And: "Single-event critical-slowing-down claims in crypto derivatives are therefore fragile by construction." This means the variance compression finding is a statistical pattern across a small population of events, not a reliable gate for any individual entry.

---

**What this means for ST2.0:**

ST2.0 fires on aggressive BUYING into a passive ask-side limit — book×tape absorption. If that buying is the build-up phase of an *endogenous* short squeeze / liquidation cascade, the passive short would be entering directly into the beginning of a squeeze — one of the worst possible adverse selection scenarios.

The paper's finding suggests that during endogenous squeeze build-ups, taker buy/sell ratio variance is **compressed** (monotone, consistent buying). This is structurally distinct from the "noisy absorption" pattern ST2.0 is designed to exploit (fluctuating buying pressure that peaks and reverts within ~15 minutes).

**The contrast:**
- ST2.0's target regime: high OFI, elevated tape buy_ratio, but *fluctuating* — absorption that peaks and stalls
- Endogenous squeeze build-up: high OFI, elevated tape buy_ratio, *monotone and persistent* — variance of the buy/sell ratio compressed over 0.5–4h

If these two regimes are distinguishable from the tape data available in ST2.0's pipeline, monitoring medium-term buy_ratio variance at signal time could help separate "routine absorption with reversion potential" from "building squeeze with continuation risk."

**Scale mismatch — critical caveat:**

The paper uses 0.5–4h rolling windows on 5-minute Binance data. ST2.0 operates at 60s cycle. ST2.0's tape buffer (ws_feed.py) captures recent trade flow, likely 60–300 seconds deep. A meaningful "variance over 30-minute window" would require the tape buffer to retain 30 minutes of per-minute flow data. Whether this is currently implemented, or whether the buffer is deep enough, is an engineering question — not resolved here. At ST2.0's current tape depth, a "30-minute variance" computation may not be feasible without a buffer extension.

**Additional limitation:** The paper is about 7 macro BTC squeeze events over 3 years — extremely rare compared to ST2.0's routine absorption micro-entries. Whether the variance compression pattern at the macro cascade scale maps to micro-scale absorption entries is a hypothesis, not an established finding. The paper itself does not study passive maker fill quality or routine absorption entries.

---

### arXiv:2606.15715 — "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid"
**URL:** https://arxiv.org/html/2606.15715v1  
**Dataset:** Hyperliquid (on-chain DEX CLOB). 201 cryptocurrency perpetual futures markets. July 28, 2025 – March 23, 2026. ~$1.93 trillion volume across 641 million fills. 4.3 million hidden metaorders vs. 465,000 visible TWAP executions.

**Verification status: VERIFIED** — HTML fetched successfully.

**Key finding (verbatim from fetch):**
> Visible TWAPs face approximately "99 basis points lower temporary impact" than comparable hidden metaorders. Announced flow leaves "roughly 55 basis points less post-execution price displacement."

The paper demonstrates that **"sunshine" trading** (pre-disclosing order direction and parameters, as Hyperliquid's TWAP module does on-chain) reduces adverse selection because counterparties can identify the flow as likely uninformed liquidity rather than informed directional trading.

**Why not applicable to ST2.0:**

Hyperliquid is an on-chain CLOB where TWAP parameters are publicly visible in the smart contract state during execution. Phemex is a centralized exchange where post-only limit orders are not pre-announced. The "sunshine" mechanism depends on the ability of market makers to observe and interpret disclosed execution schedules in real time — a DEX-specific property that does not transfer to Phemex CEX. No passive fill quality metric or gate applicable to ST2.0's use case was extracted. **Not applicable.**

---

### Other Candidates Evaluated Tonight (Non-Applicable or Blocked)

**TechRxiv "Optimal Execution Under Self-Exciting..." (November 2025):**  
HTTP 403 Forbidden on direct PDF fetch. Could not access content. Hawkes-based optimal execution — topic is relevant in principle, but Hawkes process work for passive fill quality in crypto perp has been searched for 37 nights without a primary source emerging that is both verified and crypto-perp-specific. Remains unverified.

**ScienceDirect "Queuing and inventories in limit order markets" (2025):**  
HTTP 403 Forbidden. Queue position within a tick level and adverse selection — an interesting angle (prior nights found no primary source on this for crypto perp), but content inaccessible. Unverified.

**arXiv:2607.01550 — "Is Trend Still Your Friend?":**  
Verified via HTML. ~100 liquid futures across 1995–2025. Finding: HFT-dominated small-tick markets suppress short-term trend following. No crypto perp content, no passive maker fill content, no adverse selection metric. Not applicable.

**arXiv:2607.09230 (Jeon) and arXiv:2602.00776 (Bieganowski):**  
Both appeared in search results — already covered in N36 and N34 respectively. Not re-evaluated.

---

## New Forward-Testable Tweak Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 38 | **Medium-term taker buy_ratio variance log.** At signal fire time, compute and log `tape_buy_ratio_variance_30m` = variance of per-minute tape buy_ratio values over the prior 30 minutes (if tape buffer supports this depth; else use available window). Hypothesis: ST2.0 entries where this variance is *anomalously low* (compressed, monotone buying pressure over ≥30 min) may be entering into an endogenous-buildup squeeze rather than routine absorption — and are therefore more adversely selected. Entries where buy_ratio fluctuates (variance higher) are more consistent with the absorption-then-reversion regime ST2.0 is designed for. After 30+ fills: does `tape_buy_ratio_variance_30m` cluster at low values for adverse outcomes and high values for clean fills? **Engineering prerequisite: confirm tape buffer (ws_feed.py) retains ≥30 minutes of per-minute buy_ratio data. If not, buffer extension needed before this metric is computable.** | arXiv:2607.27070, "Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades," arXiv July 2026. Binance BTCUSDT, 7 macro cascade events 2022–2025. VERIFIED via arXiv HTML. Caveats: 7-event population, macro cascades not routine micro-entries, 0.5–4h window vs ST2.0's 60s cycle, BTC only, explicitly "population-level not per-event alarm." | Queued — log only (pending tape buffer check) | 3–5 lines + possible buffer extension |

---

## Honest Caveats

1. **Seven events, not a general rule.** The paper's authors explicitly say their variance compression finding is "a population-level precursor, not a per-event alarm" and that "single-event critical-slowing-down claims in crypto derivatives are therefore fragile by construction." Tweak 38 is motivated by this finding but cannot be implemented as a gate without independent validation on ST2.0's own fills.

2. **Scale mismatch.** The paper uses 0.5–4h rolling windows on 5-min Binance data. ST2.0 operates at 60s. The tape buffer in ws_feed.py likely holds far less than 30 minutes of granular per-minute buy_ratio. Tweak 38 requires a tape buffer audit before implementation. A compressed variance signal over 5 minutes may have no relationship to the 0.5–4h compression measured in the paper.

3. **BTC macro cascades ≠ altcoin routine absorption.** The paper studies squeeze events at the level of billions of dollars in liquidations on BTC. ST2.0's entries are on altcoin perps (INJ/AVAX/ARB) at $5 margin in routine micro-absorption events. Whether the variance compression mechanism applies at this scale and asset class is an untested hypothesis.

4. **Sunshine trading (arXiv:2606.15715) not applicable.** Confirmed non-applicable despite interesting dataset (641M fills, 201 crypto perps). DEX-specific mechanism does not transfer to Phemex CEX.

5. **42 tweaks queued, 0 deployed across 37 nights.** The binding constraint remains unchanged. Tweak 38 is log-only (after tape buffer check) and can be added alongside any priority-tweak deployment session.

6. **SSRN 6693260 (Chang, N36 Tweak 37)** — still HTTP 403 blocked. Should retry via Google Scholar, ResearchGate, or author institutional page before next nightly session.

---

## Cumulative Forward-Test Queue (42 Tweaks)

Priority tweaks (unchanged from N20–N36): **4 [elevated], 6, 9, 10, 11, 12, 14**  
Tweak 38 added tonight — **conditional on tape buffer depth check.**  
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), above (Tweak 38 — conditional on tape buffer check).

---

## Night 37 Bottom Line

One genuinely new verified paper: **arXiv:2607.27070** (Binance BTCUSDT, 7 macro squeeze events 2022–2025). Core finding: the *variance* of the taker buy/sell ratio is compressed before endogenous-buildup liquidation cascades — monotone, persistent buying rather than fluctuating flow. This is a population-level precursor (p≈5×10⁻⁶ on 300-onset placebo), not a per-event alarm.

**ST2.0 angle:** The absorption pattern ST2.0 is designed to exploit (buy pressure peaks and reverts) has *different* variance structure from a building squeeze (buy pressure monotone and persistent). If medium-term tape buy_ratio variance can be computed (requires tape buffer ≥30 minutes deep), entries during low-variance windows may be entering into squeeze build-ups rather than routine absorption spikes — a novel adverse selection filter hypothesis.

**Tweak 38:** Log `tape_buy_ratio_variance_30m` at signal time. Engineering prerequisite: audit ws_feed.py tape buffer depth. After 30+ labeled fills, test whether low-variance entries cluster with adverse outcomes.

One non-applicable verified paper: arXiv:2606.15715 (Hyperliquid DEX, 201 crypto perps, 641M fills) — "sunshine" trading reduces adverse selection on on-chain CLOBs, but the mechanism is DEX-specific and does not transfer to Phemex CEX.

**Recommendation unchanged:** Deploy priority tweaks 4, 6, 9, 10, 11, 12, 14. Add Tweak 38 log after confirming tape buffer depth (check ws_feed.py). Attempt SSRN 6693260 access via ResearchGate or Google Scholar before N38. Night 37: 42 tweaks queued (2 conditional), 0 deployed.
