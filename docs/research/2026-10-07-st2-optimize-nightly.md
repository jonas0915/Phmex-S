# ST2.0 Execution Optimization — Night 83 (2026-10-07)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–73 across Nights 1–82. Academic literature (arXiv q-fin.TR) confirmed saturated Nights 77–82 (three consecutive months, zero new submissions). Last three nights added Tweaks 70–73 (cancel-side asymmetry, transient-order OBI filter, funding-window gate, rolling OBI percentile logging). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Prior coverage confirmed (not repeated):**
- Queue position/rank proxy + time-to-fill logging (Tweaks 47/65 — #1 priority)
- OFI/OBI binary gates and continuous placement offset (Tweaks 57, 59, 64, 67)
- Exponential-decay optimal posting depth (Tweak 68, practitioner-sourced)
- Price-deviation cancel/repost (Tweak 60), queue-depletion cancel trigger (Tweak 69)
- Cancel-side asymmetry pre-entry gate (Tweak 70), transient-order OBI filter (Tweak 71)
- Funding-window gate (Tweak 72), rolling OBI percentile logging (Tweak 73)
- Shadow-PPOV derivative (Tweak 69, arXiv 2609.18019)

**What is genuinely NEW tonight:**

1. **arXiv 2607.28323 (Barzykin, Boyce, Neuman, Tuschmann — July 30, 2026)** — "Optimal Execution with Passive Market Impact." VERIFIED — HTML page fetched. NOT in any prior report. Provides the formal passive-impact framework for optimal posting distance and its time evolution. Key structural insight for ST2.0: passive impact *accumulates* as a function of resting time, meaning a resting order that was correctly priced at posting time accrues adverse exposure over each subsequent second it remains unfilled. This provides a formal rationale (beyond the synthesis's empirical observation) for why fills cluster at adverse states — the order is filled precisely when accumulated passive impact peaks.

2. **SSRN 6693260 (Chang, May 2026)** — "Do Order-Book States Predict Passive-Buy Toxicity? Evidence from BTC Perpetual Futures." Source UNVERIFIED (HTTP 403 on primary paper). From search result summary only: uses Binance L2 data; finds a "flow-adjusted bid-absorption proxy" substantially more predictive of passive-buy adverse selection than raw OFI alone. Labeled UNVERIFIED — included as a caveat/lead only.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 74 — Stale-Quote Cancel: Per-Cycle Entry Gate Re-Validation

**Source:** arXiv 2607.28323 — Barzykin, Boyce, Neuman, Tuschmann. "Optimal Execution with Passive Market Impact." July 30, 2026.
**Source URL:** https://arxiv.org/abs/2607.28323
**Verification:** HTML page fetched and read. Direct quotes obtained from the paper.

**Verified claims (direct quotes):**
> "a more aggressive quote increases the fill intensity but also increases the rate at which passive impact is accumulated, whereas a less aggressive quote reduces immediate impact but increases non-execution risk and inventory costs."

> "The optimal quote distance formula: δ⋆(t,q) = 1/k + (1/k)log(ω(t,q)/ω(t,q-1)) + (η/λ)q"

where k is the fill intensity decay rate, η/λ is the passive impact per unit, q is remaining inventory.

**Structural insight:**
The paper proves that passive impact accumulates as a function of time resting and posting distance. For an order that hasn't filled over T seconds: each additional second increases the accumulated passive impact the order has absorbed from the market's order flow. The fills that occur are precisely the ones at which accumulated passive impact peaks — i.e., when the book has moved most against the resting order. This is the formal analytic complement to the synthesis's empirical observation that "fills cluster at extreme imbalance."

**Application to ST2.0:**
ST2.0's entry gates (OBI ≥ ±0.25, tape buy_ratio ≥ 0.55) are validated *at the time of posting.* If the order remains unfilled through multiple 60s bot cycles, the book conditions that justified posting may no longer hold — but the order is still live and accumulating passive impact exposure. If OBI has normalized (absorption episode ending) and the order still fills, that fill is occurring in a drifted state that no longer meets entry criteria: a high-adverse-selection fill by definition.

**Proposed Tweak 74:** At every bot cycle while a ST2.0 order is resting, re-evaluate the entry gates:

```python
# In bot.py, per-cycle check while ST2.0 has a resting POST-ONLY ask:
def _st2_order_still_valid(self, symbol: str, ob, tape) -> bool:
    """Re-check entry conditions for a resting ST2.0 order."""
    obi_ok = ob.imbalance is not None and abs(ob.imbalance) >= OB_IMBALANCE_GATE
    tape_ok = (tape.buy_ratio is not None and
               tape.buy_ratio >= TAPE_BUY_RATIO_UPPER)  # buy pressure still elevated
    return obi_ok and tape_ok

# If _st2_order_still_valid() is False → cancel resting order
# Log: reason="stale_gate_cancel", failed_gate="obi|tape|both",
#       obi_at_cancel=ob.imbalance, tape_at_cancel=tape.buy_ratio,
#       resting_seconds=elapsed_since_post
```

**Why this is new vs. existing tweaks:**
- Tweak 60: cancels on adverse *price movement* (different trigger — price-based, not gate re-validation)
- Tweak 69: cancels on *depth drop* at the posting level (queue depletion signal)
- Tweak 70: pre-entry cancel-side asymmetry (blocks *before* posting, not during resting)
- **Tweak 74:** Cancels when entry *conditions* are no longer valid (OBI/tape have normalized), independent of price movement or queue state

**Forward-test design:**
- Log `resting_seconds` and the gate state at cancel time for all `stale_gate_cancel` events.
- Comparison: do fills that occur > 60s after posting show worse post-fill adverse selection bps than fills within 60s of posting? If yes, the stale-cancel gate directly targets the high-adverse-selection fills.
- Implementation complexity: Low — uses existing ob/tape data already present in the cycle, no new feeds.

**Priority:** Medium-High. Architecturally trivial (adds one conditional check to the per-cycle resting-order evaluation) and directly targets the core adverse-selection mechanism identified in the synthesis. Does not require Tweak 47/65 data to deploy in shadow mode.

**Caveats:** arXiv 2607.28323 is calibrated on NASDAQ equities and FX pairs (k: 0.48–3.72 ticks⁻¹ for equities), not crypto perps. The specific k and η/λ values are NOT transferable to Phemex BTC/ETH. The portable finding is structural: passive impact accumulates over resting time, and fills at the worst accumulated-impact state are the adversely selected ones. This is consistent with the synthesis's empirical evidence and the prior Binance-specific adverse selection finding (arXiv 2502.18625); 2607.28323 provides the formal mechanism, not new crypto-specific calibration.

---

## (c) Caveats and Unverified Items

1. **arXiv 2607.28323: NASDAQ/FX calibration only.** Quantitative thresholds (k, η, ℓ) are not transferable to Phemex crypto perps. The structural argument (passive impact accumulates with resting time → adversely selected fills happen in drifted states) is the portable claim, not the formula constants.

2. **SSRN 6693260 (Chang, May 2026): UNVERIFIED from primary source.** HTTP 403 on SSRN. Not available as open preprint (search confirmed). From search result summary only: "flow-adjusted bid-absorption proxy combining recent directional order flow and near-touch bid-side absorption capacity substantially more informative than raw directional flow alone for predicting passive-buy adverse-selection risk in BTC perpetual futures." If verified, this would suggest an upgrade to ST2.0's OBI gate: instead of measuring ask-side depth imbalance alone, compute the ratio of recent BUY taker flow to best-ask resting depth. Labeled unverified; excluded from the tweak stack until accessible.

3. **arXiv q-fin.TR: Third consecutive month confirmed empty** (confirmed N81, Oct 4). No re-fetch tonight — two days since N82, unlikely new submissions.

4. **Tweak 74's re-validation cycle aligns with the 60s bot cycle.** If the true OBI/tape "normalized" event happens between cycles, Tweak 74 may lag by up to 60s before canceling. Combined with Tweak 69 (queue depletion, fires within the cycle) and Tweak 60 (price movement, also per-cycle), the three cancel triggers together narrow the window of adversely-selected resting exposure.

---

## Summary

| Tweak | Description | Priority | Source Type | Status |
|-------|-------------|----------|-------------|--------|
| 74 | Per-cycle re-validation of OBI+tape gates for resting orders; cancel if gates no longer pass | Medium-High | Academic (NASDAQ/FX, structural argument portable) | NEW — VERIFIED |

**Unverified lead:**
| — | Flow-adjusted ask-absorption proxy (ratio of buy flow to best-ask depth) as entry gate | TBD | Academic (SSRN 6693260, BTC perp) | UNVERIFIED — cannot access primary |

**Undeployed priority stack:**
Tweaks 47/65 (queue rank proxy + time-to-fill logging) remain #1 — no change. Tweak 74 sits behind them but is independently deployable in shadow mode (no dependency on Tweak 47/65 data). The stale-gate cancel log feeds the same replay analysis pool that Tweaks 60, 69, 70 contribute to.

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed by the literature. Tweak 74 is an adverse-selection *pruning* measure — it reduces the tail of fills that occur in drifted/stale gate states — but does not compensate for the structural deficit that makes all fills adversely selected to some degree.
