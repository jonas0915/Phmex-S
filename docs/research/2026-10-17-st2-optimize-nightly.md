# ST2.0 Execution Optimization — Night 91 (2026-10-17)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–81 across Nights 1–90. Night 90 (2026-10-16): Tweak 81 (robust volume Z-score, median/MAD burst detector). Night 89: Tweak 80 (quarter-hour proximity gate, arXiv 2607.09426). Night 88: Tweak 79 (tape intensity gate, arXiv 2608.21888). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Papers surfaced and confirmed already in corpus (rejected):**
- arXiv 2502.18625 (Market Maker's Dilemma, Binance BTC perp) — in corpus since synthesis. Re-surfaced.
- arXiv 2602.00776 (Explainable Patterns in Crypto Microstructure) — in corpus since synthesis. Re-surfaced.
- arXiv 2607.11888 (Optimal Adaptive Market Making) — in corpus since Night 85. Re-surfaced.
- arXiv 2606.15715 (Hyperliquid adverse selection, sunshine trading) — in corpus since Night 82. Re-surfaced.
- arXiv 2609.18019 (Model-Free Passive Execution via Order-Level Shadowing) — in corpus since Night 77. Re-surfaced.
- arXiv 1610.00261 (Limit Order Strategic Placement, latency/adverse selection) — in corpus since synthesis. Re-surfaced.
- arXiv 2510.27334 (RL market maker vs MFT simulation) — excluded Night 89. Re-surfaced.

**New paper fetched, NOT actionable:**

**arXiv 2607.28323 (Barzykin, Boyce, Neuman, Tuschmann — "Optimal Execution with Passive Market Impact," July 2026, HSBC/Imperial College London):** Fetched tonight from https://arxiv.org/html/2607.28323v1. The paper models passive limit orders with two empirical inputs: fill probabilities that decay exponentially with distance from midprice (λe^(−kδ), k ranges 0.48–3.72 by equity ticker), and short-term price moves that respond linearly to OFI. Data is NASDAQ (six equities) and LSEG FX (five pairs). NOT crypto-specific. The fill probability finding confirms existing corpus knowledge (synthesis already cites exponential decay from Avellaneda–Stoikov). The OFI impact component does not add new execution thresholds. **Not actionable for ST2.0 beyond confirming current placement at touch is fill-probability optimal.** Excluded from tweak stack.

---

**What is genuinely NEW tonight:**

**arXiv 2609.13597 (Danait, Zamora, Boier [NVIDIA] — "Same Book, Different Fills: Partial Identification of FIFO Execution from Aggregate Order Books," September 2026)**

This paper is NOT in the prior corpus. Search history and prior night coverage lists confirm no prior fetch. Submitted to q-fin.CP (computational), September 2026. Fetched tonight from https://arxiv.org/html/2609.13597v1.

**What the paper does:** L2 order book data (price-level snapshots) shows total quantity per level but not individual order IDs or queue order. When a cancellation occurs, L2 cannot reveal whether the cancelled quantity was ahead of or behind a resting passive order. The authors hold the observed aggregate path fixed and vary only the cancellation-allocation rule — front, quantity-weighted random, or back — then measure how passive fill outcomes and strategy rankings change.

**Data:** Tokyo Stock Exchange (TSE) equities, two instruments (RIC 1301.T and RIC 7911.T), LSEG Tick History, Jan–Jul 2025, 10-level L2 snapshots. 1,080 five-minute episodes per instrument on 18 held-out July dates.

**Direct quotes from abstract (fetched tonight):**
> "passive-execution backtests based on L2 can depend on an unobserved cancellation-allocation rule"
> "Execution policies evaluated from aggregate data should be accompanied by FIFO sensitivity analysis"
> "observationally equivalent aggregate-book paths can imply economically different passive-execution outcomes"

**Quantitative results (from the fetched page):**

Front-allocation vs. back-allocation (everything else equal):

| Metric | 1301.T | 7911.T |
|--------|--------|--------|
| Passive pre-terminal completion | +8.01 pp | +7.39 pp |
| Passive implementation shortfall | −1.010 bp [−1.253, −0.788] | −0.384 bp [−0.493, −0.284] |

- Policy choice changed (preferred policy reversed) in 3.63–14.26% of cross-rule comparisons for 7911.T and 0.83–4.49% for 1301.T when the queue assumption changed.
- When policy choice changed, the added cost was 2.4–17.4 bp per instance depending on instrument.

**Why this is new vs. the prior 81 tweaks:**

The corpus already has evidence that queue position matters: arXiv 2502.18625 (synthesis) quantified −0.058 bp (front) vs −0.775 bp (back) post-fill adverse selection on Binance BTC perp. The queue-value-2016 (Moallemi) synthesis entry shows front-vs-back is worth "up to a whole spread" and is symbol-dependent.

What arXiv 2609.13597 adds is structurally new:

1. **A bounding methodology, not just a point estimate.** Danait et al. show that even without observing individual queue positions, you can bound the queue uncertainty by replaying the same aggregate path under front, random, and back cancellation. The spread between front and back outcomes is a *measurable bound* on how much queue position actually matters for a given instrument. For ST2.0, this suggests: run the same ST2.0 fill history under front/random/back cancellation assumptions to bound the queue-position sensitivity of the current strategy.

2. **A concrete classification criterion for time-to-fill as a queue-rank proxy.** Front-of-queue fills happen faster (smaller queue ahead, hit sooner at current price). Back-of-queue fills require price to move all the way through the queue before hitting — precisely the adverse move. The paper's front/back boundary is a queue-position assumption, but in live execution with known order placement timestamps, *time-to-fill* is a direct (noisy) proxy for queue depth ahead of the order: slow fills (many seconds to minutes) are disproportionately back-of-queue; fast fills (seconds) are front-of-queue. This is the exact inference Tweak 65 (time-to-fill logging) is designed to enable — and the 7–8 pp completion and ~1 bp IS bounding from Danait et al. provides the theoretical *motivation* for why this measurement is worth doing.

3. **"Policy reversal" as an adversarial threshold.** The authors find policy preference reverses in 3.6–14.3% of comparisons when the queue assumption changes. For ST2.0, the analogous question is: does the decision to enter (vs. skip) depend on whether we assume we're front or back of queue? If we're always back-of-queue (as suggested by the synthesis: "posts-and-waits ~20s → likely back-of-queue"), then the observed win rate may be the WORST CASE of the front/back range. The front-of-queue upper bound could be ~7–8 pp better.

**Scope limitations:**
- Tokyo Stock Exchange equity data, NOT crypto perps. FIFO matching is generally assumed for limit orders on most venues, but Phemex's actual queue mechanics under post-only may differ from TSE. Direction of the finding is structural (queue position → fill timing → adverse selection), but magnitudes are equity-specific.
- The authors treat front/back as bounding conventions, not as precise estimates of any real trader's position. For ST2.0's live fill history, time-to-fill is the best available (noisy) proxy.

---

## (b) Concrete Forward-Testable Execution Tweak

### Tweak 82 — FIFO Queue Sensitivity Analysis: Classify ST2.0 Fills by Time-to-Fill as Front/Back Queue Proxy; Measure Adverse Selection Gap

**Source:** Danait, R., Zamora, Y. & Boier, I. "Same Book, Different Fills: Partial Identification of FIFO Execution from Aggregate Order Books." arXiv:2609.13597v1. September 2026.
**Source URL:** https://arxiv.org/html/2609.13597v1
**Verification:** HTML page fetched tonight. Direct quotes and quantitative table extracted from abstract and main results. Paper is q-fin.CP (not peer-reviewed; NVIDIA authors). NOT crypto data (TSE equities). Direction of inference is structural and applies to any FIFO LOB.

**Structural motivation:**

The synthesis (2026-06-20) established that ST2.0's fills are adversely selected — you fill precisely when buying continues — and that back-of-queue fills are documented to suffer far worse adverse selection than front-of-queue fills (synthesis: "−0.058 bp front vs −0.775 bp back," arXiv 2502.18625). The synthesis also noted ST2.0 "posts-and-waits ~20s → likely back-of-queue."

Danait et al. add a new measurement framework: hold the aggregate book path fixed, vary cancellation allocation, and measure how fill outcomes bound. Their front/back spread (7–8 pp completion, ~1 bp IS) on TSE instruments is a reference magnitude for what queue uncertainty costs in practice.

For ST2.0, Tweak 65 (time-to-fill logging) is already proposed but undeployed. arXiv 2609.13597 provides the formal motivation for WHY time-to-fill is the right measurement:

- **Fast fill (< threshold seconds):** order was near front of queue; price moved to it quickly with little intervening queue. Less adverse.
- **Slow fill (> threshold seconds):** order was further back; required price to move through substantial queue depth. More adverse — the fill arrived precisely because price moved in the wrong direction (against the short).

**Proposed Tweak 82 — implementation (log-only, shadow mode):**

```python
# At ST2.0 order placement:
# _slot_order_placed_ts[symbol] = time.monotonic()

# At ST2.0 fill detection (in _sync_exchange_closes or equivalent):
# fill_ts = time.monotonic()
# ttf_seconds = fill_ts - _slot_order_placed_ts.get(symbol, fill_ts)
# queue_class = "fast" if ttf_seconds < 30 else ("medium" if ttf_seconds < 90 else "slow")
# self._log(f"st2_fill_queue symbol={symbol} ttf={ttf_seconds:.1f}s class={queue_class}")
#
# For misses (order cancelled/expired without fill):
# miss_ts = time.monotonic()
# time_held = miss_ts - _slot_order_placed_ts.get(symbol, miss_ts)
# self._log(f"st2_miss_queue symbol={symbol} held={time_held:.1f}s")
```

**Forward-test design (shadow log only):**

Log `ttf_seconds` and `queue_class` on every ST2.0 fill. After accumulating n≥30 fills across the three classes:

- **Primary hypothesis:** Slow fills (queue_class=slow) show materially worse win rate and/or post-fill adverse selection (bps marked against fill price at 5s / 1min / hold horizon) than fast fills (queue_class=fast). Expected from synthesis: Δ adverse selection ≈ 0.7 bp (the −0.058 vs −0.775 bp Binance gap, arXiv 2502.18625).
- **Secondary measurement:** Distribution of ttf_seconds in ST2.0 fills — does it confirm the "back-of-queue" hypothesis? If median ttf > 60s, the synthesis assumption is validated.
- **If primary hypothesis confirmed** (WR fast > WR slow by ≥10pp across n≥30): consider a time-to-fill-based GATE — cancel-and-repost if order has been resting > T seconds with no fill (the resting period itself becomes an adverse selection indicator). This would convert Tweak 65 from a measurement to an execution filter.
- **If distribution shows bimodal pattern** (fast cluster + slow cluster): the two clusters likely represent different market states. Fast = book swept the resting order. Slow = price drifted up through the queue (against the short). The bimodal split is itself a diagnostic for adverse selection.

**Threshold calibration:**
- 30s (fast/medium boundary): approximately the 20s wait already cited in synthesis, with buffer.
- 90s (medium/slow boundary): about 1.5 candle cycles. Orders resting > 90s are likely back-of-queue in a thin absorption scenario.
- These are starting hypotheses — the actual ttf distribution from ST2.0's own fills will calibrate the thresholds.

**Why this is higher priority than Tweaks 80–81 (quarter-hour, volume Z-score):**

Tweaks 80–81 address external market conditions at entry time (time-of-day, volume regime). Tweak 82 addresses the internal state of ST2.0's specific resting order — how long it has been in the queue — which the synthesis identified as the #2 structural weakness (no queue position). The Danait et al. paper provides a bound: if queue position uncertainty costs 7–8 pp completion on TSE, and arXiv 2502.18625 shows 0.7 bp adverse-selection gap on Binance, ST2.0's slow fills may carry the bulk of its adverse selection load. Tweak 82 is the measurement that confirms or rejects this.

**Implementation dependency:**
- Requires order placement timestamp logging (trivially available at the time of order submission in bot.py / strategy_slot.py).
- Independent of all prior tweaks.
- Can be shadow-deployed as a pure logging addition with zero execution risk.
- If Tweak 47 (queue rank proxy from book volume) is implemented first, it provides an ORDER-PLACEMENT-TIME estimate of queue position; Tweak 82 provides an ORDER-CLOSE-TIME measurement. Together they bracket the queue experience from both ends.

**Priority:** Medium-high. Shadow log only, zero execution risk, minimal implementation cost. Closes the most significant instrumentation gap the synthesis identified (queue position), now with a second independent empirical anchor from a new paper.

---

## (c) Caveats and Unverified Items

1. **arXiv 2609.13597 is Tokyo Stock Exchange equity data, NOT crypto perps.** TSE uses a fully deterministic FIFO matching engine with known tick size and queue dynamics. Phemex's post-only queue mechanics may differ. The 7–8 pp completion bound is an equity reference magnitude, not a Phemex calibration. The directional claim (queue position → fill timing → adverse selection) is structural and applies broadly.

2. **Time-to-fill is a noisy proxy for queue position.** A fast fill can occur because the market moved quickly (not necessarily because ST2.0 was front-of-queue) — e.g., a large sweep that clears the entire bid stack. A slow fill can reflect a thin market, not back-of-queue position. The proxy is useful directionally but not an exact queue-rank measure.

3. **The 30s/90s thresholds are hypothesis-only.** No calibration against ST2.0's actual fill distribution has been performed. The actual distribution of ttf in ST2.0 fills (currently unknown from available data) will determine the appropriate boundaries.

4. **arXiv 2607.28323 (Optimal Execution with Passive Market Impact) — new but not actionable.** Fetched tonight. Equities/FX only. Fill probability decays exponentially with distance from midprice (confirming existing corpus knowledge). The OFI component (passive impact) doesn't add a new gate threshold. Excluded from tweak stack.

5. **Persistent unverified leads (unchanged from Night 90):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403 persists. Not re-attempted tonight.
   - Microstructure Lab Substack (post-sweep delayed entry / LOB resilience): Still paywalled.
   - arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77): Still not fully captured.

---

## Summary

| Tweak | Description | Priority | Source | Status |
|-------|-------------|----------|--------|--------|
| 82 | FIFO queue sensitivity: log `ttf_seconds` (time from placement to fill) on every ST2.0 fill; classify fills as fast/medium/slow as a front/back queue proxy; measure whether slow fills (back-of-queue) carry materially worse adverse selection than fast fills. Directly addresses the #2 structural weakness (no queue position) identified in the synthesis. | Medium-high (shadow log only; closes the most important instrumentation gap) | Danait, Zamora, Boier (NVIDIA), arXiv:2609.13597v1, Sep 2026, q-fin.CP. TSE equity data; direction structural. | NEW — VERIFIED (HTML fetched, quotes + quantitative table extracted; equity venue, direction structural) |

**Excluded tonight:**
| — | arXiv 2607.28323 (Optimal Execution with Passive Market Impact, Barzykin et al., HSBC/Imperial, July 2026) | N/A | Equities/FX only; confirms corpus knowledge | Fetched, NOT actionable for ST2.0 |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry + LOB recovery timing (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | Academic | PARTIALLY FETCHED |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite for bps analysis)
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold (shares vol buffer with Tweak 76)
5. Tweak 78 — Gate hysteresis (ship as part of same changeset as Tweaks 75+76)
6. Tweak 79 — Tape intensity gate (independently deployable in shadow mode)
7. Tweak 74 — stale-gate per-cycle re-validation
8. Tweak 72 — funding-window gate
9. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
10. Tweak 71 — transient-order OBI filter
11. Tweak 80 — Quarter-hour proximity shadow log
12. Tweak 81 — Robust volume Z-score shadow log
13. **Tweak 82 — FIFO time-to-fill queue classification** ← NEW (shadow log; strengthens case for deploying Tweaks 47/65)

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed. Tweak 82 gives ST2.0 its first direct measurement of queue-position exposure by classifying fills as fast (likely front-of-queue) vs. slow (likely back-of-queue). The Danait et al. paper adds a second independent empirical anchor — alongside arXiv 2502.18625 — for why this measurement is worth doing: queue uncertainty costs 7–8 pp completion and ~1 bp IS in equity LOBs, and the synthesis already shows −0.717 bp adverse-selection gap (front vs. back) on the closest crypto-perp analog.
