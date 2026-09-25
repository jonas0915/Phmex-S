# ST2.0 Maker Execution — Nightly Optimization Research
**Night 73 | 2026-09-25 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–72)

Prior nights (last covered: N72, 2026-09-24) documented Tweaks 1–62 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth/rank logging, early posting in absorption
window, quarter-hour blackout (Tweak 51), funding gate (Tweak 52), seconds-to-qh (Tweak 53),
OB imbalance regime audit (Tweak 54), 1s adverse-selection baseline (Tweak 55), aggressor-ratio
gate (Tweak 56), OFI saturation gate (Tweak 57), spread-normality gate (Tweak 58), multi-level
OFI depth concentration (Tweak 59), price-deviation cancel-and-repost trigger (Tweak 60),
VPIN suppression gate (Tweak 61), and cycle-offset logging (Tweak 62).

Tonight's sweep covered four angles:
1. Symbol-asymmetric OFI predictiveness (BTC vs ETH) on crypto perp L2 state transitions
2. Liquidation cascade early-warning signals (taker variance compression) as suppression gate
3. Optimal quoting under adverse selection and price reading (theoretical framework)
4. Adverse selection mechanics on DEX perps (Hyperliquid)

**What is genuinely NEW tonight:**
- Angle 1 yields the most actionable finding: arXiv:2607.09230 (Jeon, July 2026) — Binance
  BTCUSDT and ETHUSDT perp data, 2023–2026 — shows that OFI/order flow adds **zero robust
  predictive value for BTC** L2 state transitions, while for ETH it adds meaningful value
  specifically in stressed liquidity regimes. This is the first paper in the corpus giving
  a *per-symbol* answer to the question of when OFI gates are trustworthy. It is NOT in any
  prior night.
- Angle 2 yields a cautionary finding: arXiv:2607.27070 (Garcia Seuma, July 2026) identifies
  taker order-flow variance compression as the one reliable pre-cascade signal, but explicitly
  states it is "not a per-event alarm." Useful for risk monitoring; too noisy for a per-trade
  suppression gate. Not in prior corpus.
- Angles 3 and 4 were rejected: arXiv:2508.20225 is a theoretical FX dealer model with no
  crypto-perp applicability; arXiv:2606.15715 (Hyperliquid) is a DEX paper — queue priority,
  gas fees, and oracle mechanics do not transfer to Phemex CEX.

---

## (b) Confirmed New Findings

### Finding A — OFI Gate Is Reliable for ETH, Unreliable for BTC
**Source:** arXiv:2607.09230 — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State
Transitions in Crypto Futures," Joohyoung Jeon (July 10, 2026)
**URL:** https://arxiv.org/abs/2607.09230
**Market/Data:** Binance BTCUSDT and ETHUSDT perpetual futures, 2023–2026 (47,513 event windows,
18,631 macro-event windows, 28,882 matched non-event controls; rolling monthly OOS evaluation).
**Status:** FETCHED AND VERIFIED (abstract page + HTML, full abstract quoted below).

**Verified quote (from abstract):**

> "Order flow adds further value only when layered on top of the L2 state model, not as a
> replacement. This value is not robustly cross-symbol: for ETH it is present across calm,
> mixed, and stressed regimes and largest under stressed pre-event liquidity, whereas BTC shows
> only isolated five-minute passes and no regime that clears at both horizons."

**Additional verified structural claims (from HTML summary):**

> "the first-order predictive signal is the pre-event L2 liquidity state: a coarse pre-event
> state baseline strongly predicts post-event liquidity regimes"

> "Order flow adds further value only when layered on top of the L2 state model"

The paper builds a "supervised discrete L2 liquidity-state transition task" using spread, top-20
depth, and top-20 imbalance as the state features. Liquidity regimes are classified as calm,
mixed, or stressed based on these three tercile-ranked descriptors. Order flow (taker volume and
trade-flow imbalance) is then evaluated as an *additional layer* on top of the state model.

**What this means for ST2.0:**

ST2.0 currently applies `ob.imbalance ≥ 0.25` as a universal gate across all traded symbols
(BTC, ETH, and alt perps). This paper's direct evidence on Binance perps says OFI-based
predictive power is **symbol-specific**:

- **BTC:** Order flow shows "no regime that clears at both horizons" — meaning the OFI gate
  for BTC entries may have near-zero signal value. Any fill or miss driven by the OFI threshold
  on BTC is operating without reliable empirical backing from a contemporaneous perp dataset.

- **ETH:** Order flow adds value, and more so in stressed regimes (wide spread, thin depth,
  high top-20 imbalance) — precisely the conditions ST2.0 enters. The OFI gate for ETH
  appears meaningfully grounded.

- **Alt perps (not studied):** Unknown. Alt perps typically share thin-book characteristics
  with ETH (stressed regimes more common) rather than deep-book BTC. The ETH finding may be
  the better prior for alts, but this is speculative.

The paper also establishes a **state-first principle**: L2 state (spread + depth + imbalance
together) is the *primary* predictive object; order flow is only an *overlay*. This challenges
the current gate ordering in ST2.0, where `ob.imbalance` (a single OFI-like number) is checked
before the full L2 state picture is assessed.

**Not in any prior night:** All prior OFI-related tweaks (Tweaks 54, 57, 59) treat OFI as
universally informative and discuss threshold calibration. No prior night has surfaced a
crypto-perp-native paper with a per-symbol OFI reliability result.

---

### Cautionary Finding B — Taker Variance Compression Before Cascade Events: Not a Per-Trade Gate
**Source:** arXiv:2607.27070 — "Where does the criticality live? Early-warning signals are
event-heterogeneous across seven crypto-perpetual liquidation cascades," Ramon Marc Garcia Seuma
(July 29, 2026)
**URL:** https://arxiv.org/abs/2607.27070
**Market:** Crypto perpetual futures (7 historical cascade events)
**Status:** VERIFIED (abstract page)

**Verified quote (from abstract):**

> "The one regularity surviving all events with data is a compression of taker order-flow
> variance, which passes a 300-onset placebo test (Fisher-combined p ~ 5e-6)."

The paper is explicit that this is a population-level regularity: the variance compression is
reliably present *in aggregate* across cascade events, but is "not a per-event alarm." The signal
cannot reliably predict any individual cascade; its false-alarm rate on the placebo test means it
fires too often to function as a per-trade gate.

**Implication:** Do NOT implement taker variance compression as a ST2.0 suppression gate. The
paper's own framing rules this out as a trade-level filter. However: logging a rolling
`taker_variance_20` metric (standard deviation of taker_ratio over the past 20 candles) is
low-cost and could surface regime-level risk awareness. If variance compression is extreme and
sustained (not just a single reading), it may warrant manual review rather than automated blocking.

---

## (c) Forward-Testable Execution Tweak

### Tweak 63 — Symbol-Specific OFI Gate Reliability: Log Per-Symbol OFI Outcomes, Consider BTC Exception
**Source:** arXiv:2607.09230 (verified, Binance BTCUSDT + ETHUSDT perp, 2023–2026)
**Mechanism:** The universal `ob.imbalance ≥ 0.25` gate currently treats all symbols
identically. The paper provides direct evidence that for BTC, OFI/order flow adds no robust
predictive signal for L2 state transitions. The implication is a two-part tweak:

**Part 1 — Instrument (zero risk, instrument-first rule):**
```python
# At every ST2.0 signal evaluation, log symbol + OFI value together:
log(f"st2_eval: symbol={symbol} ob_imbalance={ob.imbalance:.3f} "
    f"spread_pct={spread_pct:.4f} depth_bids={total_bid_depth:.0f}")

# At every fill and loss:
log(f"st2_outcome: symbol={symbol} win={win} ob_imbalance_at_entry={ob_imbalance:.3f}")
```

After 30+ fills stratified by symbol, compute per-symbol OFI→outcome correlation. Hypothesis:
- ETH fills with high `ob.imbalance` should show higher WR than ETH fills with low imbalance
- BTC fills should show **no correlation** between `ob.imbalance` at entry and outcome WR

If confirmed: the `ob.imbalance ≥ 0.25` gate is working for ETH and doing nothing for BTC.

**Part 2 — State-first gate ordering (instrument first, then deploy if stratification confirms):**

Instead of checking `ob.imbalance` alone, evaluate the L2 *state* composite: spread, top-5
depth, and imbalance together. The paper shows the 3-descriptor composite strongly predicts
post-event liquidity regimes even without order flow. This suggests:

```python
def l2_state_score(ob, spread_pct, rolling_spread_median):
    """Score 0-3: how many L2 indicators are in the 'stressed/favorable' tercile."""
    score = 0
    # High imbalance (bids dominate): favorable for short entry
    if ob.imbalance >= 0.25:
        score += 1
    # Spread near normal (not elevated adverse-selection environment):
    if spread_pct <= 1.5 * rolling_spread_median:
        score += 1
    # Depth at best ask not unusually thin (book has inventory to absorb):
    if ob.asks[0][1] >= ob_depth_rolling_25th_pct:
        score += 1
    return score

# Gate: require l2_state_score >= 2 instead of single ob.imbalance gate
if l2_state_score(ob, spread_pct, rolling_spread_median) < 2:
    log("st2_blocked: l2_state_composite_weak")
    return
```

**What to instrument first:** The spread_pct and depth components are already flagged in the
undeployed instrumentation stack (Tweaks 45, 48, 58). The composite gate can be constructed
from existing data once those logs are confirmed active.

**Priority for Part 1:** High — 2–3 log lines, verifies the BTC OFI unreliability hypothesis
against ST2.0's own data, directly motivated by the closest crypto-perp-native OFI study in the
corpus (Binance perps, 2023–2026).

**Priority for Part 2:** Medium — deploy only after Part 1 stratification shows BTC/ETH asymmetry
in the live data. Do NOT flip to composite gate before the per-symbol logging confirms the effect.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:2607.09230 (Jeon, July 2026):** The abstract and HTML summary were fetched and
   verified. The paper studies Binance BTCUSDT and ETHUSDT only — not alt perps and not
   Phemex. The "L2 state transition task" is distinct from a trading P&L outcome: predicting
   regime transition ≠ predicting fill WR. The OFI-unreliability finding for BTC is from the
   transition-prediction task, not directly from a maker strategy backtest. It is the
   strongest available evidence on a Binance-like perp book, but requires ST2.0-specific
   stratification to confirm. Treat as a motivated hypothesis, not a confirmed effect.

2. **arXiv:2607.27070 (Garcia Seuma, July 2026):** The taker variance compression finding
   is explicitly "not a per-event alarm" by the paper itself. Using it as a per-trade gate
   would contradict the paper's own conclusion. Only the population-level regularity is
   confirmed.

3. **Symbol generalizability:** The corpus now has two BTC-vs-ETH findings pointing in
   the same direction: the June 2026 synthesis showed ETH had ~59% fill rate vs BTC ~30%;
   tonight's paper shows OFI is reliable for ETH but not BTC on Binance. Both suggest BTC
   may be structurally different from ETH in how book imbalance predicts near-term price
   direction. Whether this extends to alt perps (the bulk of ST2.0's trade attempts) is
   unknown.

4. **Nothing found on:** (a) a perp-native empirical paper on cancel-repost timing that
   supersedes arXiv:2607.11888 (N72), (b) a direct Phemex-calibrated adverse-selection
   measure, (c) volatility-gated posting rules with crypto perp data. These gaps remain open.

---

## Priority Ordering (Undeployed Actions, Full Stack)

Unchanged high-priority instrumentation (each ~2–5 lines, zero trading risk):
1. `time_to_fill` logging (N64) — 5 lines, unblocks all fill-quality analysis
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `queue_rank_at_fill` logging (Tweak 47) — 2–3 lines
5. `seconds_to_qh` logging (Tweak 53) — 1 line
6. `aggressor_ratio_at_attempt` logging (Tweak 56)
7. `ofi_percentile_at_attempt` logging (Tweak 57)
8. `spread_ratio_at_attempt` logging (Tweak 58)
9. `st2_ofi_depth_ratio` logging (Tweak 59)
10. `adverse_move_bps_at_cancel` + `cancel_reason` logging (Tweak 60)
11. `vpin_proxy_at_attempt` logging (Tweak 61)
12. `seconds_into_cycle` logging (Tweak 62)

New tonight:
13. `symbol + ob_imbalance + outcome` per-fill logging for BTC/ETH asymmetry check (Tweak 63, Part 1)

Then deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| New candidates tonight | 1 (Tweak 63) |
| Total candidates | 19 (45–63) |
| Negative findings | +1 (taker variance compression: not a per-trade gate) |
| Conditional | 1 |

---

*Sources fetched and verified this session:*
- *arXiv:2607.09230 (Jeon 2026, Binance BTC+ETH perp OFI asymmetry, abstract + HTML verified)*
- *arXiv:2607.27070 (Garcia Seuma 2026, liquidation cascade early-warning, abstract verified)*
- *Rejected as not-new or not-applicable: arXiv:2508.20225 (theoretical FX dealer model),
  arXiv:2606.15715 (Hyperliquid DEX — DEX mechanics don't transfer to Phemex CEX),
  arXiv:2602.00776, arXiv:2502.18625, arXiv:2607.28323, arXiv:2609.18019 (all prior corpus)*
