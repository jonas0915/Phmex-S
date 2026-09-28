# ST2.0 Maker Execution — Nightly Optimization Research
**Night 75 | 2026-09-28 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–74)

Prior nights (last covered: N74, 2026-09-27) documented Tweaks 1–64 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth/rank logging, early posting in absorption
window, quarter-hour blackout (Tweak 51), funding gate (Tweak 52), seconds-to-qh (Tweak 53),
OB imbalance regime audit (Tweak 54), 1s adverse-selection baseline (Tweak 55), aggressor-ratio
gate (Tweak 56), OFI saturation gate (Tweak 57), spread-normality gate (Tweak 58), multi-level
OFI depth concentration (Tweak 59), price-deviation cancel-and-repost trigger (Tweak 60), VPIN
suppression gate (Tweak 61), cycle-offset logging (Tweak 62), symbol-specific OFI reliability /
BTC vs ETH asymmetry (Tweak 63), and flow intensity over LOB depth (Tweak 64).

Tonight's sweep searched four angles not previously covered:
1. Post-fill markout methodology for passive makers on crypto perps (cited gap from N74)
2. OFI signal decay over the order-resting period (cited gap from N74)
3. Cross-venue lead-lag effect on passive maker adverse selection
4. Queue-position ignorance cost — quantifying how much not knowing queue rank costs

**What is genuinely NEW tonight:**

Angle 4 yields the single actionable finding: arXiv:2609.13597 (Danait, Zamora & Boier,
September 11–17, 2026) — "Same Book, Different Fills: Partial Identification of FIFO Execution
from Aggregate Order Books" — directly quantifies how much passive fill completion and
implementation shortfall differ depending on unobserved queue rank. This paper is NOT in any
prior night (N1–N74). It provides the first quantitative calibration in the corpus for the cost
of not knowing queue position.

**Cross-connection to N74:** The N74 finding (arXiv:2608.21888, Kitron & Wengrowicz) documented
the gross reversal edge at ~1.3 bps. This paper documents the implementation shortfall penalty
from queue position ignorance at ~0.4–1.0 bps (see below). Together, these two papers constrain
the economics: if queue position uncertainty costs ~1 bps and gross edge is ~1.3 bps, queue rank
is not a marginal concern — it consumes most of the gross edge.

Angles 1, 2, and 3 returned only prior-corpus papers or non-applicable sources (see section d).

---

## (b) Confirmed New Finding

### Finding A — Queue Position Ignorance Costs ~0.4–1.0 bps and ~8pp Fill Completion
**Source:** arXiv:2609.13597 — "Same Book, Different Fills: Partial Identification of FIFO
Execution from Aggregate Order Books," Riya Danait, Yuliana Zamora & Ioana Boier
(submitted September 11, 2026; revised September 17, 2026)
**URL:** https://arxiv.org/abs/2609.13597
**Market/Data:** Tokyo Stock Exchange (TSE) 2025 data; two equity instruments (RIC 1301.T and
RIC 7911.T); seven months of synchronized L2 order book snapshots + L1 trade data; 1,080
matched five-minute execution episodes per instrument across 18 held-out trading days.
**Status:** FETCHED AND VERIFIED (arXiv abstract page) this session.

**Verified quotes (from fetched abstract):**

On the core finding:
> "Observationally equivalent aggregate-book paths can imply economically different
> passive-execution outcomes."

> "Passive-execution backtests can therefore depend on an unobserved cancellation-allocation
> rule even when observed prices, quantities, and trades are held fixed."

**Verified quantitative claims (from fetched abstract):**

For instrument 1301.T: front cancellation vs back cancellation = **8.01 percentage points**
higher pre-terminal completion and **1.010 bps** lower implementation shortfall.

For instrument 7911.T: **7.39 percentage points** and **0.384 bps** respectively.

**What this means for ST2.0:**

ST2.0's Tweak 47 (queue_rank_at_fill logging — undeployed) was proposed as a nice-to-have
diagnostic. This paper reframes it as a core economics question:

The gross reversal edge documented in arXiv:2608.21888 (N74, Binance 183 pairs) peaks near
**1.3 bps** per trade. The TSE equity finding puts queue-position uncertainty at **0.4–1.0 bps**
implementation shortfall. If the equity finding scales to crypto alt perps (caveat below), the
queue rank penalty consumes **30–75% of the available gross edge**.

ST2.0 currently has no queue rank signal. Tweak 47 logs `queue_rank_at_fill` — knowing where in
the price level the fill occurred. The paper provides a quantitative reason to treat Tweak 47 as
a higher priority than other undeployed instrumentation: it is the instrumentation most directly
connected to the realized edge gap.

**Important caveats (see section d):** Japanese equity data, not crypto perps. FIFO priority
rules differ across exchanges; Phemex uses strict FIFO but with cancel-replace patterns that
differ from TSE. The ~1 bps figure is not directly transferable; it establishes order of
magnitude and motivates measurement, not a deployable threshold.

---

## (c) Forward-Testable Execution Tweak

### Tweak 65 — Prioritize Queue Rank Instrumentation; Frame as Edge-Budget Constraint
**Source:** arXiv:2609.13597 (verified, TSE 2026, FIFO passive execution) + arXiv:2608.21888
(verified, Binance perps 2026, gross reversal edge)
**Mechanism:** Not a new gate — a reprioritization of the existing instrumentation queue.
Prior reports treated `queue_rank_at_fill` (Tweak 47) as one of thirteen equal-priority
undeployed logging items. This paper provides a quantitative rationale to promote Tweak 47
to the **first** instrumentation deploy, before spread logging, OFI percentiles, or VPIN.

**Why:** If queue position ignorance costs ~0.4–1.0 bps (TSE data) and the gross edge is ~1.3 bps
(Binance data), logging queue rank at fill is the measurement most likely to reveal whether
ST2.0 has a viable edge at all — or whether the edge is entirely consumed by queue position.

**Deployment sketch (from prior Tweak 47 spec):**

```python
# At ST2.0 fill event: estimate queue rank from level-2 snapshot
# queue_rank ≈ total bid volume posted ahead of our order at fill price
# (not perfectly observable without order ID; proxy: volume at best ask at posting time)
queue_rank_proxy = ob.asks[0][1]  # total size at best ask when order was placed
log(f"st2_fill: symbol={symbol} win={win} queue_rank_proxy={queue_rank_proxy:.0f} "
    f"time_to_fill_sec={time_to_fill:.1f}")
```

After 30+ fills stratified by `queue_rank_proxy`, test: do fills with low queue rank (smaller
ask volume ahead) show higher WR than fills with high queue rank (large ask volume at posting)?
If the TSE finding scales, the answer should be yes, with ~8pp WR difference at the extremes.

**Priority upgrade:** Move Tweak 47 from position #4 in the instrumentation queue to position #1
(above `time_to_fill`, which is already #1 in the current stack). The rationale: `time_to_fill`
measures the symptom (long fill times = back-of-queue); `queue_rank_proxy` measures the cause
directly. If only one instrumentation change can be deployed in the next cycle, this is it.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:2609.13597 (Danait et al., Sep 2026, TSE equities):** Japanese equity data. TSE uses
   FIFO priority with specific price-time rules; Phemex uses strict FIFO but the cancel-replace
   patterns on crypto perps (high cancel rate, large institutional participants repricing quotes
   continuously) differ from equities. The 0.4–1.0 bps penalty is order-of-magnitude context only.
   It cannot be applied as a precise Phemex calibration without Phemex-specific stratification.

2. **Cross-finding synthesis (arXiv:2609.13597 × arXiv:2608.21888):** Combining a TSE equity
   paper with a Binance crypto paper to get "queue costs consume 30–75% of gross edge" is
   cross-data inference. Both datasets are non-Phemex. The comparison is motivated and internally
   consistent, but the combined claim should be treated as a hypothesis requiring Phemex
   confirmation, not a documented fact.

3. **Angles 1–3 findings (post-fill markout methodology, OFI signal decay, cross-venue lead-lag):**
   - Angle 1 (post-fill markout): arXiv:2608.04373 (DEX wallet data, prior corpus) and
     arXiv:2602.00776 (Binance perps, prior corpus) remain the closest sources. No new
     crypto-perp-native passive-maker markout methodology paper found tonight.
   - Angle 2 (OFI signal decay during resting): arXiv:2507.22712 (BankNifty index futures,
     India equity, not crypto perp); arXiv:2506.05764 (BTC/USDT Bybit, LOB noise filtering,
     not a signal decay study). No crypto-perp-native paper measuring OFI decay timescale found.
   - Angle 3 (cross-venue lead-lag): arXiv:2608.09188 (equity perpetuals on OKX, oracle
     methodology during cash closure — not BTC/alt perp adverse selection). arXiv:2506.08718
     (ETH Binance vs Uniswap, BTC CME futures — Binance leads price discovery, but no passive
     maker implication quantified). Neither paper is actionable for ST2.0.

4. **Remaining open gaps (unresolved across N1–N75):**
   - A Phemex-calibrated adverse-selection measure (no primary source found at any night)
   - A crypto-perp-native empirical study of OFI signal decay over the order-resting window
   - A passive-maker-specific markout paper on CEX perpetuals (not DEX, not spot)

---

## Priority Ordering (Undeployed Actions, Full Stack)

**Upgrade tonight:** Tweak 47 (`queue_rank_proxy` logging) moves from position #4 → #1.

Revised ordering:
1. `queue_rank_proxy` at posting + `time_to_fill` at fill (Tweaks 47/N64) — together ~5 lines,
   now the #1 priority based on the edge-budget constraint finding
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `seconds_to_qh` logging (Tweak 53) — 1 line
5. `aggressor_ratio_at_attempt` logging (Tweak 56)
6. `ofi_percentile_at_attempt` logging (Tweak 57)
7. `spread_ratio_at_attempt` logging (Tweak 58)
8. `st2_ofi_depth_ratio` logging (Tweak 59)
9. `adverse_move_bps_at_cancel` + `cancel_reason` logging (Tweak 60)
10. `vpin_proxy_at_attempt` logging (Tweak 61)
11. `seconds_into_cycle` logging (Tweak 62)
12. `symbol + ob_imbalance + outcome` per-fill logging (Tweak 63)
13. `flow_imbal = 2*tape.buy_ratio-1` + `ob_imbalance` at every entry attempt (Tweak 64)

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 45 (Tweaks 4–64 + reprioritized Tweak 47) |
| New candidates tonight | 1 (Tweak 65: queue rank promoted to #1 priority) |
| Total candidates | 21 (45–65) |
| Negative findings | +0 new tonight |
| Conditional | 1 |

---

*Sources fetched and verified this session:*
- *arXiv:2609.13597 (Danait, Zamora & Boier, Sep 2026, TSE FIFO execution, abstract verified)*
- *Rejected as prior corpus: arXiv:2608.21888, arXiv:2607.09230, arXiv:2602.00776,*
  *arXiv:2502.18625, arXiv:2607.28323, arXiv:2608.04373*
- *Rejected as not applicable: arXiv:2507.22712 (BankNifty equity, not crypto), arXiv:2506.05764*
  *(LOB noise filtering, not signal decay study), arXiv:2608.09188 (equity perp oracles),*
  *arXiv:2506.08718 (ETH/BTC spot vs DEX), arXiv:2409.12721 (CME equity futures),*
  *arXiv:2608.18195 (RL simulated environments), arXiv:2512.05734 (CAC 40 equity futures),*
  *arXiv:2605.24242 (theoretical, no empirical data)*
