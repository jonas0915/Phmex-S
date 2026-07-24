# ST2.0 Execution Optimization — Night 28
**Date:** 2026-07-24 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 27 Nights

N27 closed with: Frontiers/Pindza (VPIN comparable across altcoins; altcoin higher fill rate is a liquidity artifact, not lower adverse selection), Tweak 29 (arrival-rate z-score as TWAP-splitting institutional flow detector). Tonight searched four new angles not yet covered in the series: (1) optimal limit order cancellation timing relative to LOB state — the 27-night open gap, (2) cancel-side OFI as orthogonal signal to trade-tape imbalance, (3) conditional OFI decomposition (Lu/Cucuringu line of work), (4) cross-asset informed trading spillover BTC→altcoin perps. Two findings are new material. SSRN 6693260 remains blocked (night 28).

**Summary of new material tonight:**
- arXiv:1707.01167 (Gonzalez & Schervish, "Instantaneous order impact and high-frequency strategy optimization in limit order books") — ABSTRACT DIRECTLY FETCHED. First theoretical support in the series for **conditional pre-fill cancellation**: the optimal policy cancels a resting limit order when "non-execution or adverse selection probability is high." Closes the 27-night TTL gap with a theoretical framework. No crypto-perp calibration; full paper not readable (PDF binary).
- Cancel-side OFI (Cont, Kukanov & Stoikov 2014 JFE; Lu, Reinert & Cucuringu 2024 Quantitative Finance; Sitaru, Calinescu & Cucuringu 2023 ACM ICAIF) — PARTIALLY VERIFIED via two independent practitioner sources that cite these papers specifically. Primary papers themselves were not directly fetched (two paywalled, one not tried). Key claim chain: adding cancel events to OFI raises 10-second R² from 0.32–0.35 (trade-only) to 0.65 (all events including cancels) on 50 NYSE stocks; cancel-OFI ranks second in predictive importance behind add-OFI, ahead of trade-OFI; conditional OFI with cancel decomposition achieves Sharpe 1.79 vs negative Sharpe for undifferentiated OFI. All equity markets — not crypto perp validated.

**Confirmed misses tonight:**
- SSRN 6693260 ("Do Order-Book States Predict Passive-Buy Toxicity?" Lawrence Chang) — HTTP 403, blocked again. 28th consecutive night. No new access route.
- arXiv:2507.22712 (Order-Book Filtration, Directional Signal Extraction) — Fetched and read. NSE BANKNIFTY equity futures, 3 trading days (Jan 2023). The "ephemeral order" filtration concept is interesting, but requires raw order-ID lifecycle data (order IDs, modification history) that Phemex's L2 WebSocket does not provide in that form. Not actionable.
- Cross-asset BTC→altcoin informed flow spillover — No new literature found. The Frontiers/Pindza paper (N27) is the most recent data on cross-asset microstructure and it found that microstructure models "do not transfer across cryptocurrencies" (same asset spot↔perp transfer works; BTC→altcoin transfer does not). No complementary spillover paper found tonight.
- arXiv:2605.06405 (Funding-Aware MM for Perpetual DEXs) — Fetched. Purely theoretical Avellaneda-Stoikov extension for DEX market making with stochastic funding (Hyperliquid calibration). Addresses market maker inventory + funding coupling; does not address passive directional order adverse selection. Not applicable to ST2.0.

---

## Finding A — arXiv:1707.01167 ABSTRACT-ONLY: Optimal LOB-Conditional Cancellation of Resting Limit Orders

**Source:** Federico Gonzalez, Mark Schervish. "Instantaneous order impact and high-frequency strategy optimization in limit order books." arXiv:1707.01167.
**URL:** https://arxiv.org/abs/1707.01167
**Dataset:** Not specified in abstract. Markov decision process framework; empirical validation implied but not calibrated to a specific exchange or asset class in the abstract.
**Access:** Abstract fetched directly. Full paper is a binary PDF — body content not readable via WebFetch.

**Verified quotes (from abstract, directly fetched):**

> "Limit orders are placed under favorable LOB conditions and canceled when non-execution or adverse selection probability is high."

> "Market orders are used aggressively when the mid-price is expected to move adversely."

> "The optimal policy employs all three order types strategically."

**What this paper is about:**

The paper models optimal order execution as a Markov decision process, incorporating "recent order impact and LOB shape" as state variables. The optimal policy is dynamic — it does not post a limit order and then passively wait for the TTL to expire. Instead, it actively monitors LOB state and cancels when:
1. Non-execution probability rises too high (order won't fill in time)
2. Adverse selection probability rises (price will move against the resting order after it fills)

When neither condition is met (LOB "favorable"), the policy holds the limit order. When adverse selection risk is high, the policy also supports switching to market orders to guarantee execution at cost of crossing the spread.

**Why this is new relative to the prior 27 nights:**

The "optimal TTL/cancellation timing" gap was noted at Night 6 and has remained open through Night 27 — the single longest-running unanswered gap in the research series. This paper provides the closest theoretical framing found in the series: it names "adverse selection probability" as the explicit trigger for cancellation and frames the decision as a LOB-state-conditional policy, not a fixed-time TTL rule. No prior night's literature addressed this directly.

**What this means for ST2.0:**

ST2.0 currently posts a passive sell and waits a fixed TTL for fill. If the LOB state worsens during the TTL (arrival z-score spikes, OFI flips strongly bid-side, ask depth collapses), the Gonzalez & Schervish framework says the optimal action is **cancellation**, not passive waiting. The adverse selection probability has risen since order placement. The current fixed-TTL policy implicitly treats the LOB as stationary for the duration of the resting order — but the LOB is not stationary.

**Forward-testable implication → Tweak 30 (shadow log, 3–5 lines):**

Monitor LOB state DURING the TTL window (e.g., every 5 seconds). At each check, compute `arrival_rate_zscore` (Tweak 29) and `ob_imbalance`. Log whether these signals *worsened* post-placement vs the signal-time values. After 30+ filled trades: do fills preceded by "worsened LOB during TTL" have systematically higher adverse selection (worse post-fill 30s returns)?

If yes: implement conditional cancellation rule — cancel resting sell if `arrival_rate_zscore > 1.5 AND ob_imbalance remains bid-heavy throughout TTL` after N seconds with no fill. This converts the fixed TTL into a conditional TTL: the order lives until filled, TTL expires, OR adverse-selection proxy exceeds threshold.

**Critical limitations:**
1. **Abstract only — full paper content not read.** The actual LOB thresholds and state variables that trigger cancellation in the model are not visible. Cannot implement specific thresholds from this paper.
2. Not calibrated to crypto perps. The asset class and exchange are not specified in the abstract.
3. The "adverse selection probability" trigger is defined relative to a Markov model — it would need to be approximated with observable proxies (arrival z-score, OFI) rather than computed from the paper's model.
4. The model addresses an agent with a single order and a time deadline. ST2.0's context (3-second scan cycles, 60-second main loop) may not match the paper's time granularity.

---

## Finding B — Cancel-Side OFI (PARTIALLY VERIFIED via practitioner sources): Cancel Events Carry Orthogonal Adverse Selection Signal

**Sources (practitioner, both directly fetched; underlying papers not directly fetched):**
- HFT Advisory: "The Cancel-Stream Gap: Why Your Signal Stack Is Building on 35% of the Order Book" — https://hftadvisory.substack.com/p/the-cancel-stream-gap-why-your-signal
- Electronic Trading Hub: "Why Your Trade-Tape OFI Caps at 35% R-Squared: The Cancel Stream Your Signal Pipeline Is Ignoring" — https://electronictradinghub.com/why-your-trade-tape-ofi-caps-at-35-r-squared-the-cancel-stream-your-signal-pipeline-is-ignoring/

**Underlying academic citations (not directly fetched — UNVERIFIED at primary source):**
- Cont, Kukanov & Stoikov (2014). "The Price Impact of Order Book Events." *Journal of Financial Econometrics*. [50 NYSE stocks, 10s windows]
- Lu, Reinert & Cucuringu (2024). "Trade co-occurrence, trade flow decomposition and conditional order imbalance in equity markets." *Quantitative Finance*. DOI: 10.1080/14697688.2024.2358963 [457 stocks, 4 years, daily data — HTTP 403]
- Sitaru, Calinescu & Cucuringu (2023). ACM ICAIF. [100 stocks, 3 years of L3 data]

**Verified quotes (directly from fetched practitioner sources):**

From HFT Advisory:
> "Most HFT signal stacks consume the trade tape and discard the cancel stream — modeling 35% of order book events."

> "97% of limit orders cancel before executing"

> "unified order flow imbalance at the best bid and ask" achieved R-squared of 0.65, while "trade-only OFI" produced only "0.32 to 0.35 range"

From Electronic Trading Hub (reporting Lu et al. and Sitaru et al.):
> "report R-squared in the 84 to 86% range with Sharpe ratios of 1.79 on strategies built from the conditional decomposition, versus negative Sharpe on undifferentiated OFI"

> "add-OFI ranks first in predictive importance, cancel-OFI ranks second, and trade-OFI ranks last"

**What cancel-OFI is:**

Standard OFI uses only executed trades (bid lifts and ask hits). Cancel-OFI additionally captures the rate at which resting limit orders are *withdrawn* from each side of the book. When the ask side is rapidly cancelling (sellers pulling their resting orders faster than they're being hit), the book is thinning on the sell side for a reason: those passive sellers have updated their belief that price will move up. This is adverse for ST2.0's passive short — the market maker co-locating alongside us on the ask is fleeing, not for fundamental reasons, but because they see the same buy flow we do and expect it to continue.

The asymmetry of cancel-OFI: **bid cancellations** (buyers pulling bids below) vs **ask cancellations** (sellers pulling offers above):
- Heavy ask-side cancels at signal time → passive sellers fleeing → implies higher probability the buy absorption continues (adverse for ST2.0's short)
- Heavy bid-side cancels at signal time → buyers fleeing their bids → implies buy pressure may exhaust (favorable for ST2.0's short)

**Why this is new relative to the prior 27 nights:**

None of the prior 27 nights addressed the cancel stream as a distinct signal. Tweak 4 (`tape_max_single_trade`), Tweak 29 (`arrival_rate_zscore`), and the LOB imbalance gate all use executed trades and/or resting depth snapshots. Cancel events are the third distinct order book event type and — per the academic literature — orthogonal to the other two in predictive content.

**Feasibility on Phemex:**

Phemex's L2 WebSocket sends depth update diffs (price level → quantity). An implicit cancel can be inferred when a bid level's quantity decreases without a corresponding trade print at that price. The ws_feed.py already collects the tape (trades) and LOB (depth). Cross-referencing the two gives an estimated cancel rate per side:
```python
# Inferred bid cancel at level price_level:
# depth[price_level] decreased AND no trade at price_level in last cycle
# → implied bid cancellation count
bid_cancel_inferred += depth_before[price_level] - depth_after[price_level]
```
This is noisier than a proper L3 cancel event stream but is computable from existing infrastructure.

**Forward-testable tweak → Tweak 30a (shadow log, ~5 lines):**
At signal time, compute from the most recent LOB delta cycle:
```python
ask_cancel_inferred = sum(max(0, depth_before[p] - depth_after[p])
                          for p in ask_levels if no_trade_at(p))
bid_cancel_inferred = sum(max(0, depth_before[p] - depth_after[p])
                          for p in bid_levels if no_trade_at(p))
cancel_side_ratio = ask_cancel_inferred / max(bid_cancel_inferred, 1)
```
Log `cancel_side_ratio` alongside fill/miss/adverse outcome. After 30+ fills: do adverse fills cluster at high `cancel_side_ratio` (ask side cancelling faster than bid → sellers fleeing)? If yes, add as a pre-entry gate.

**Critical limitations:**
1. **All underlying academic papers are equity markets** (NYSE, NSE). R² and Sharpe claims may not transfer to Phemex altcoin perp micro-structure. Crypto perps have lower resting order counts, thinner books, and a different participant mix. The "97% cancel rate" is NYSE data.
2. **Primary papers not directly fetched.** Lu et al. 2024 (Quantitative Finance) was HTTP 403. Sitaru et al. 2023 was not tried. The specific statistics (R² 84-86%, Sharpe 1.79) are reported by two independent practitioner sources citing these papers but are not verified from the paper text itself. Label as PARTIALLY VERIFIED.
3. **Inferred cancel rate ≠ actual cancel stream.** The Phemex L2 WS does not expose individual order cancel events. The inferred approach from depth diffs is a rough proxy. True cancel-OFI (as in Lu et al.) requires L3 order-level data.
4. The Cont et al. (2014) claim of R² 0.65 is for 10-second price prediction on large-cap US equities. Crypto perp altcoins have much thinner books and different tick-to-spread ratios. The predictive lift from cancel events may be smaller, larger, or noise-level at Phemex's liquidity tier.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 30 | **Conditional TTL cancellation log.** Monitor `arrival_rate_zscore` and `ob_imbalance` every 5s DURING the TTL window. Log whether these worsened post-placement vs. signal-time values. After 30+ fills: do fills where LOB worsened during TTL have higher adverse selection? If yes: add LOB-conditional cancel rule (cancel if z > 1.5 AND ob still bid-heavy after Ns with no fill). Addresses the 27-night TTL gap. | arXiv:1707.01167 abstract (Gonzalez & Schervish — ABSTRACT ONLY, no crypto calibration) | Queued — log only | 3–5 lines |
| 30a | **Cancel-side ratio log.** Compute `ask_cancel_inferred / bid_cancel_inferred` per LOB delta cycle. Log at signal time. After 30+ fills: do adverse fills have elevated ask-side cancel rates? Gate if confirmed. | Cont/Lu/Sitaru (equity markets, PARTIALLY VERIFIED via practitioner sources — NOT from primary paper text) | Queued — log only | 5 lines |

Note: Tweak numbering continues from Tweak 29 (N27). Tweaks 30 and 30a are distinct signals that could be logged in the same session. Whether to combine into a single implementation pass is an implementation decision, not a research decision.

---

## Honest Caveats

1. **Finding A (arXiv:1707.01167):** Abstract fetched directly; full paper not readable. The specific LOB state variables that define "favorable" vs "adverse" in the paper's MDP model are not available from the abstract alone. Tweak 30 operationalizes the finding using Tweak 29's arrival_rate_zscore as the adverse-selection proxy — which is itself from a practitioner-unverified source (N27). Two layers of inference.

2. **Finding B (cancel-OFI):** Two independent practitioner sources cite the same academic papers consistently. The claim chain is plausible and the academic papers (Cont et al. 2014, Lu et al. 2024) are peer-reviewed in well-regarded journals. BUT: the underlying papers were not directly fetched — one was paywalled (HTTP 403). R² and Sharpe claims are PARTIALLY VERIFIED, not confirmed. Equity markets only. The inferred cancel rate from Phemex L2 depth diffs is a rough proxy for the L3 cancel-OFI used in the academic papers.

3. **Cross-asset spillover gap remains open.** No literature found that specifically addresses whether heavy BTC perp buying predicts imminent altcoin passive short adverse selection. This remains an unresolved angle.

4. **29 tweaks already queued, 0 deployed across 27 nights.** Adding Tweaks 30 and 30a brings the queue to 31. The recommendation from N20–N27 is unchanged: implement priority tweaks first — 4, 6, 9, 10, 11, 12, 14. Tweaks 30 and 30a are each 3–5 lines and could be added in the same pass. But continued research before collecting 30+ tagged fills per diagnostic variable has zero ROI. Tonight marks the same pattern.

5. **SSRN 6344338** still blocked (25 consecutive nights). **SSRN 6693260** still blocked (28th night). Both remain the most directly applicable blocked sources in the series.

---

## Cumulative Forward-Test Queue (31 Tweaks)

Priority tweaks (unchanged from N20–N27): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweaks 30, 30a added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), above (Tweaks 30, 30a).

---

## Night 28 Bottom Line

Two findings. Finding A (arXiv:1707.01167, Gonzalez & Schervish, ABSTRACT ONLY): closes the 27-night open gap on optimal cancellation timing — the theoretical answer is "cancel when adverse selection probability is high," implemented as a LOB-conditional policy rather than a fixed TTL. Forward-testable as Tweak 30 (monitor LOB state during TTL, log degradation, then gate). Limitation: abstract-only, no crypto calibration. Finding B (Cont et al. 2014 / Lu et al. 2024 / Sitaru et al. 2023, EQUITY MARKETS, PARTIALLY VERIFIED): cancel-side OFI is the second most important predictive signal in order book microstructure, orthogonal to the trade tape and resting depth — "add-OFI ranks first, cancel-OFI ranks second, trade-OFI ranks last." Forward-testable as Tweak 30a (infer ask vs bid cancel rate from Phemex L2 depth diffs; log at signal time). Critical limitation: all equity markets, primary papers not directly fetched, inferred cancel rate is a noisy proxy.

**Recommendation unchanged from N20–N27:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweaks 29, 30, 30a are each 3–5 lines and can be added in the same session. Night 28: 31 tweaks queued, 0 deployed.
