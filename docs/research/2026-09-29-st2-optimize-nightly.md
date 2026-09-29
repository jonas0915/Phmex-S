# ST2.0 Maker Execution — Nightly Optimization Research
**Night 76 | 2026-09-29 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–75)

Prior nights (last covered: N75, 2026-09-28) documented Tweaks 1–65 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth/rank logging, early posting in absorption
window, quarter-hour blackout (Tweak 51), funding gate (Tweak 52), seconds-to-qh (Tweak 53),
OB imbalance regime audit (Tweak 54), 1s adverse-selection baseline (Tweak 55), aggressor-ratio
gate (Tweak 56), OFI saturation gate (Tweak 57), spread-normality gate (Tweak 58), multi-level
OFI depth concentration (Tweak 59), price-deviation cancel-and-repost trigger (Tweak 60), VPIN
suppression gate (Tweak 61), cycle-offset logging (Tweak 62), symbol-specific OFI reliability /
BTC vs ETH asymmetry (Tweak 63), flow intensity over LOB depth (Tweak 64), and queue rank
promoted to #1 priority instrumentation (Tweak 65).

Tonight's sweep searched four angles not previously covered at this depth:
1. Mid-order LOB state monitoring — detecting absorption-ending regime transitions while the
   order is resting (distinct from entry-time gating covered by Tweaks 55–65)
2. CEX perp passive-maker post-fill markout methodology (open gap from N1)
3. September 2026 q-fin.TR new submissions (arXiv listing direct crawl)
4. Stale limit order detection / cancel trigger frameworks

**What is genuinely NEW tonight:**

Angle 1 yields the single new candidate: arXiv:2604.20949 (Hiremath & Hiremath, April 22,
2026) — "Early Detection of Latent Microstructure Regimes in Limit Order Books." The paper's
core contribution is that LOBs transition from stable to stressed through a **latent build-up
phase** that is detectable in advance of observable stress. On simulated data, the method
achieves +18.6 ± 3.2 timestep lead time over classical reactive baselines.

The key conceptual contribution for ST2.0 is its **focus on the transition moment**, not just
the static regime state. All prior ST2.0 entry gates (Tweaks 51–65) condition on the LOB state
AT ENTRY. None captures the LOB state AT CANCEL — the moment when ST2.0 removes an order that
didn't fill. If absorption is ending (transitioning from absorption → neutral), the cancel event
is the moment the bot implicitly "detects" the regime has shifted. Logging the LOB state at
cancel time is the minimum instrument to test whether detectable features precede that transition.

**Important caveat:** The paper is primarily simulation-based (200 simulations). Real data
coverage is "one week of BTC/USDT LOB" — preliminary only. The paper does not publish
Phemex-calibrated thresholds, nor does it study passive maker fill quality directly. It
establishes the conceptual framework; Tweak 66 below is the instrumentation step to test
whether the concept applies to ST2.0's cancel events on Phemex.

Angles 2, 3, and 4 returned no new applicable papers:
- Angle 2 (CEX perp passive markout): no new paper found; the open gap from N1 remains.
  The closest found is arXiv:2407.16527 (DeLise, July 2024) — "The Negative Drift of a Limit
  Order Fill" — but it uses US Treasury futures data, not crypto CEX, and no bps measurements
  were extractable from the abstract. Concept is already established in the N1 synthesis corpus
  via arXiv:2502.18625.
- Angle 3 (Sep 2026 q-fin.TR direct crawl): full listing fetched. 9 papers submitted Sep 23–29
  — none address passive maker execution in crypto perps. Most relevant paper is arXiv:2609.32848
  (Maciejewski, CME HFT queue design), which covers sub-microsecond latency optimization — not
  applicable to ST2.0's timescale.
- Angle 4 (stale order detection): no crypto-perp-native empirical paper found. Papers returned
  were equity (NASDAQ LOBSTER data, 2020) or order cancellation time distributions (not passive
  maker specific).

---

## (b) Confirmed New Finding

### Finding A — LOB Regime Transitions Have a Detectable Latent Build-Up Phase
**Source:** arXiv:2604.20949 — "Early Detection of Latent Microstructure Regimes in Limit
Order Books," Prakul Sunil Hiremath & Vruksha Arun Hiremath (April 22, 2026)
**URL:** https://arxiv.org/abs/2604.20949
**Market/Data:** Primary: 200 Monte Carlo simulations. Real data: BTC/USDT LOB, one week
(preliminary validation only).
**Status:** FETCHED AND VERIFIED (abstract page) this session.

**Verified quote (from abstract):**

> "Limit order books can transition rapidly from stable to stressed conditions, yet standard
> early-warning signals...are inherently reactive."

> "Mean lead-time of +18.6 ± 3.2 timesteps with perfect precision and moderate coverage
> across simulations, outperforming classical baselines."

**What this means for ST2.0:**

Prior nights focused on what the LOB looks like AT THE MOMENT ST2.0 decides to enter. This
paper's contribution is that the transition itself — from a favorable (absorption) regime to an
unfavorable (reversal onset or neutral) regime — has a latent pre-transition window.

For ST2.0, the relevant question is: can the LOB state at cancel time be compared to the LOB
state at entry time to detect regime shift? If absorption is ending:
- Spread may be widening (unfavorable for passive fill)
- Ask depth at posting price may be thinning
- Tape buy_ratio may be falling
- OFI may be compressing

None of these are currently logged at cancel time. Tweak 60 logs `adverse_move_bps_at_cancel`
and `cancel_reason` — but not the full LOB state (spread, depth, OFI, buy_ratio) at cancel.

**Important limitations:**
1. The paper's 18.6-timestep lead time is from simulated data; the "timestep" unit is not
   calibrated to real Phemex exchange time. This number cannot be used as a threshold.
2. The one-week BTC/USDT real-data validation is too short to be a primary source for
   parameter decisions.
3. The authors are not established microstructure researchers in the corpus. The methodology
   (trigger-based detector, MAX aggregation, adaptive thresholding) is not independently
   replicated in any other paper found tonight.

This finding motivates instrumentation only, not a gate change.

---

## (c) Forward-Testable Execution Tweak

### Tweak 66 — Log Full LOB State Snapshot at Cancel Events (Regime-Transition Instrumentation)
**Source:** arXiv:2604.20949 (verified, BTC/USDT simulation + 1-week real data, April 2026)
**Mechanism:** ST2.0 currently logs LOB state at entry (spread, OFI, buy_ratio) but logs only
`adverse_move_bps_at_cancel` + `cancel_reason` at cancel time (Tweak 60). Adding a full LOB
snapshot at cancel time creates a paired dataset: (entry-state, cancel-state) → regime shift
delta. After 30+ cancels, test: do cancels in strongly-adverse-selecting conditions show
detectable LOB drift from entry-state to cancel-state?

**Instrument (zero risk, zero trading change):**

```python
# At every ST2.0 cancel event (after Tweak 60 cancel logging):
cancel_spread_pct = (ob.asks[0][0] - ob.bids[0][0]) / ob.asks[0][0]
cancel_buy_ratio  = tape.buy_ratio  # current tape state at cancel
cancel_ob_imbal   = ob.imbalance    # current OFI state at cancel
cancel_ask_depth  = ob.asks[0][1]   # size at best ask at cancel

log(f"st2_cancel_state: symbol={symbol} "
    f"spread_pct={cancel_spread_pct:.4f} buy_ratio={cancel_buy_ratio:.3f} "
    f"ob_imbal={cancel_ob_imbal:.3f} ask_depth={cancel_ask_depth:.0f} "
    f"time_resting_sec={time_resting:.1f}")
```

**What to test after 30+ cancels:**
- Does `cancel_buy_ratio` drop relative to `entry_buy_ratio`? (absorption fading)
- Does `cancel_spread_pct` widen relative to `entry_spread_pct`? (regime transition)
- Do cancelled orders that precede wins (where a later entry succeeds) show different
  cancel-state profiles than orders cancelled ahead of losers?

If the paper's latent-phase concept scales, orders cancelled in mid-absorption-fade should show
buy_ratio compression and spread expansion vs. entry state. Orders cancelled mid-continuation
(price moving against ST2.0 without fade) should show the reverse.

**Priority:** Low-medium. The paper is primarily simulation-based with weak real-data validation.
However, the implementation cost is 4 log lines — zero trading impact — and pairs directly with
Tweak 60's cancel logging that may already be instrumented. The combined (entry-state,
cancel-state) dataset is uniquely useful: no prior night has proposed capturing the delta between
entry conditions and cancel conditions to measure regime drift.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:2604.20949 (Hiremath & Hiremath, April 2026):** Primarily simulation-based. Real
   data is one week of BTC/USDT, not Phemex, not alt perps, not independently replicated.
   The +18.6 timestep lead time is a simulation metric; it cannot be used as a Phemex threshold.
   Treat as weak-evidence motivation for instrumentation, not a validated empirical finding.

2. **Persistent open gaps (N1–N76, unresolved):**
   - A Phemex-calibrated adverse-selection measure — no primary source found at any night
   - A crypto-perp-native study of OFI signal decay over the order-resting window — no paper
   - A passive-maker-specific markout paper on CEX perpetuals — no paper (closest: arXiv:2407.16527
     on US Treasury futures; arXiv:2502.18625 on Binance BTC perp taker-side)

3. **Literature saturation signal:** Tonight's crawl of the full September 2026 q-fin.TR
   listing (9 papers) plus targeted searches across 4 angles returned only one new candidate,
   and that candidate is primarily simulation-based. The literature on passive CEX perp maker
   execution appears to be approaching saturation for the current search methodology. The most
   productive next research direction is likely ST2.0's own live data (via the undeployed
   instrumentation stack) rather than further literature sweeps on the same angles.

---

## Priority Ordering (Undeployed Actions, Full Stack)

**No change to priority 1 from N75:**
1. `queue_rank_proxy` at posting + `time_to_fill` at fill (Tweaks 47/65) — #1 priority,
   edge-budget constraint basis (arXiv:2609.13597 + arXiv:2608.21888 combined inference)
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
13. `flow_imbal = 2*tape.buy_ratio-1` + `ob_imbalance` at every entry (Tweak 64)
14. Full LOB state snapshot at cancel events (Tweak 66) — new tonight, low-medium priority

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 46 (Tweaks 4–65 + Tweak 66) |
| New candidates tonight | 1 (Tweak 66: cancel-state LOB snapshot) |
| Total candidates | 22 (45–66) |
| Negative findings | +0 new tonight |
| Conditional | 1 |

---

*Sources fetched and verified this session:*
- *arXiv:2604.20949 (Hiremath & Hiremath, April 2026, BTC/USDT simulation + 1-week real data,
  abstract verified via fetch)*
- *arXiv:2609.32848 (Maciejewski, Sep 2026, CME NQ HFT queue design — rejected: HFT latency,
  not passive maker)*
- *arXiv:2609.11614 (Moret & Lillo, Sep 2026, regime-switching RL market making — rejected:
  simulated environment)*
- *arXiv:2604.21993 (Xu et al., April 2026, quote deterioration detection — rejected: ABIDES
  simulation only)*
- *arXiv:2603.09164 (Sepper, March 2026, Slippage-at-Risk — rejected: taker slippage on
  Hyperliquid DEX)*
- *arXiv:2407.16527 (DeLise, July 2024, negative drift of limit order fill — rejected: US
  Treasury futures, not crypto CEX)*
- *Sep 2026 q-fin.TR listing (9 papers, Sep 23–29 2026): none applicable*
- *Rejected as prior corpus: arXiv:2609.18019, arXiv:2608.21888, arXiv:2607.09230,
  arXiv:2609.13597, arXiv:2602.00776, arXiv:2502.18625, arXiv:2607.28323*
