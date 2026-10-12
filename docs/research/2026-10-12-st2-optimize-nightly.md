# ST2.0 Execution Optimization — Night 86 (2026-10-12)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–76 across Nights 1–85. Night 85 (2026-10-09) produced Tweak 76 (realized-vol gate) from arXiv 2607.11888 Corollary 4.4. Night 84: Tweak 75 (OBI upper-bound gate). Night 83: Tweak 74 (stale-gate per-cycle re-validation). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Prior coverage confirmed (not repeated):**
- Queue position/rank proxy + time-to-fill logging (Tweaks 47/65 — #1 priority)
- OFI/OBI binary/band gates and continuous placement offset (Tweaks 57, 59, 64, 67, 75)
- Exponential-decay optimal posting depth (Tweak 68)
- Cancel-on-price-deviation / fixed threshold (Tweak 60), queue-depletion cancel (Tweak 69)
- Cancel-side asymmetry (Tweak 70), transient-order OBI filter (Tweak 71)
- Funding-window gate (Tweak 72), rolling OBI percentile logging (Tweak 73)
- Stale-gate per-cycle re-validation (Tweak 74)
- Realized-vol pre-entry gate (Tweak 76) — from arXiv 2607.11888 Corollary 4.4 + Theorem 3.6
- arXiv 2606.15715 (Hyperliquid, Barone/Lillo) — reviewed N82
- arXiv 2608.04373 (Hyperliquid public-wallet) — reviewed N80, rejected as CEX-inapplicable
- LIPIcs AFT 2026.36 (Jia, Moallemi, Wang, Zeng — Hyperliquid wealth distribution) — reviewed tonight, DEX-only, not applicable to Phemex CEX passive execution

**What is genuinely NEW tonight:**

**arXiv 2607.11888 (Zeng & Liu) — Proposition 3.7 "Optimal Cancel Latency" (Section 3.4)**
Night 85 extracted Corollary 4.4 (optimal spread formula ∝ σ²) and Theorem 3.6 (adverse selection decomposition) from this paper. The paper also contains **Proposition 3.7**, which was NOT extracted on Night 85. It provides a closed-form cancel-threshold formula that is structurally distinct from all prior cancel-related tweaks (60, 69, 70, 74).

**Verification:** HTML page re-fetched tonight at https://arxiv.org/html/2607.11888. Proposition 3.7 confirmed in Section 3.4 "Adverse Selection Decomposition: Latency vs. Informed."

**Direct quotes from the paper (from tonight's fetch):**

From Proposition 3.7 header and body:
> "Δt_eff(θ) = θ²/σ²"

> "The optimal threshold θ* maximizes the PnL rate"

> "λ(θ) = Λ₀(1−e^(−ρθ))"

Where:
- θ = cancel threshold (price displacement that triggers cancellation)
- σ = local realized volatility
- Δt_eff = effective latency implied by the cancel threshold
- λ(θ) = fill rate as a function of cancel threshold
- Λ₀ = baseline fill intensity, ρ = order book depth decay parameter

The paper also includes the first-order optimality condition (equation 30) for θ* but its exact form was at page offset > 100,000 characters and was not captured in the fetched excerpt. The structural result — Δt_eff = θ²/σ², θ* maximizes PnL rate — is confirmed from the fetched content.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 77 — Volatility-Scaled Cancel Threshold: Replace Fixed Price-Deviation Cancel with σ-Adaptive Threshold

**Source:** Zeng, M. & Liu, Y. "Optimal Adaptive Market Making: A Theoretical Framework for High-Yield Liquidity Provision in Perpetual Futures Markets." arXiv 2607.11888. August 2026. Section 3.4, Proposition 3.7.
**Source URL:** https://arxiv.org/html/2607.11888
**Verification:** HTML page fetched twice (Night 85 for Corollary 4.4, tonight for Proposition 3.7). Direct quotes obtained from both fetches.

**Why this is structurally new vs. existing tweaks:**

- **Tweak 60 (cancel-on-price-deviation):** Cancels if price moves adversely by a fixed bps threshold. The threshold does NOT adapt to current volatility.
- **Tweak 74 (stale-gate cancel):** Cancels when OBI/tape conditions no longer hold. Condition-based, not price-movement-based.
- **Tweak 76 (realized-vol pre-entry gate):** Blocks entries when σ > 85th percentile. Pre-entry filter, not a cancel-while-resting mechanism.
- **Tweak 77:** Adapts the MAGNITUDE of the cancel threshold dynamically based on current σ. When σ is high, a wider threshold avoids over-cancellation (which kills fill rate); when σ is low, a tighter threshold protects against staleness. Neither price-based nor condition-based in isolation — it calibrates the price-movement trigger to realized volatility.

**Structural insight from Proposition 3.7:**

The formula Δt_eff = θ²/σ² links cancel threshold and volatility via effective latency. For ST2.0 with a ~60s bot cycle (Δt_eff ≈ 60s), the implied minimum cancel threshold is:

```
θ* ≥ σ × √(Δt_eff) = σ × √60 ≈ σ × 7.7
```

Current Tweak 60 (fixed threshold): suppose ST2.0 cancels if price moves 5 bps. That is effectively θ = 0.0005.

In a low-vol regime (σ per 60s ≈ 0.0003): θ_current = 0.0005 >> σ√60 = 0.0023 — threshold is tight enough, potentially over-protective.
In a high-vol regime (σ per 60s ≈ 0.001): θ_current = 0.0005 << σ√60 = 0.0077 — threshold is too tight, cancels prematurely, kills fill rate while the fill would still have been within the normal volatility band.

This means a fixed cancel threshold that's calibrated for average volatility simultaneously:
- Cancels too aggressively in high-vol periods (reducing fill rate, not necessarily reducing adverse selection)
- Under-cancels in low-vol periods (allowing stale resting orders that shouldn't remain)

**Proposed Tweak 77:** Replace fixed cancel threshold in ST2.0's resting-order management with a σ-scaled threshold:

```python
import numpy as np

# Current Tweak 60 (fixed):
CANCEL_ADVERSE_THRESHOLD_BPS = 5.0  # cancel if price moves 5 bps against the short

# Proposed Tweak 77 (σ-adaptive):
CANCEL_BASE_LATENCY_SECONDS = 60.0  # bot cycle time (Δt_eff)
CANCEL_THRESHOLD_SCALING_FACTOR = 1.0  # tune: 1.0 = tight (θ = σ√Δt), 1.5 = loose

def _st2_adaptive_cancel_threshold(self, symbol: str) -> float:
    """Returns the optimal cancel threshold θ* for the current volatility regime.
    Based on Proposition 3.7 of arXiv 2607.11888: Δt_eff = θ²/σ² → θ = σ√(Δt_eff).
    """
    sigma = self._realized_vol(symbol)  # from Tweak 76's implementation
    if sigma is None:
        return CANCEL_ADVERSE_THRESHOLD_BPS / 10000.0  # fallback to fixed
    theta_star = sigma * np.sqrt(CANCEL_BASE_LATENCY_SECONDS) * CANCEL_THRESHOLD_SCALING_FACTOR
    # Clamp to reasonable range: never cancel on < 2 bps OR > 20 bps moves
    return max(0.0002, min(0.0020, theta_star))

# In resting-order per-cycle check (replaces Tweak 60's fixed threshold):
# threshold = self._st2_adaptive_cancel_threshold(symbol)
# if mid_price > entry_ask * (1 + threshold):  # price moved up against short
#     cancel, log reason="adaptive_cancel", threshold_bps=threshold*10000, sigma=sigma
```

**Why it matters specifically for ST2.0:**

ST2.0 has exactly the pathological latency case: a ~60s cycle means that in high-vol periods, a fixed cancel threshold fires constantly (killing fills) while in genuinely "stale" low-vol conditions the threshold may not fire at all. The Proposition 3.7 formula gives a principled way to calibrate the threshold to the bot's fixed latency structure.

**Forward-test design:**

- Log `adaptive_threshold_bps`, `sigma_at_cancel`, and `resting_seconds_at_cancel` for every cancel event.
- Compare fill rate and post-fill adverse selection bps between:
  - Low-vol periods (σ below 50th percentile): fixed vs. adaptive threshold cancel count
  - High-vol periods (σ above 75th percentile): same comparison
- Primary hypothesis: σ-adaptive threshold improves fill rate in high-vol without worsening adverse selection bps.
- Secondary hypothesis: in low-vol periods, adaptive threshold catches stale resting orders faster than fixed threshold (tighter bound).

**Implementation complexity:** Low — builds directly on Tweak 76's `_realized_vol()` helper (same data source). Replace one comparison operator in the existing cancel check.

**Implementation dependency:** Shares the rolling trade-price buffer with Tweak 76. If Tweak 76 is deployed first, Tweak 77 reuses its data entirely.

**Priority:** Medium. This is an upgrade to an existing mechanism (Tweak 60) rather than a wholly new gate. Its value depends on how volatile the vol-regime distribution is across ST2.0's symbols. Deployable in shadow mode (log adaptive threshold vs. what the fixed threshold would have done, without actually changing behavior).

**Caveats:**

1. **arXiv 2607.11888 is a theoretical paper.** The constants ρ (order book depth decay) and Λ₀ (baseline fill intensity) in λ(θ) = Λ₀(1−e^(−ρθ)) are not calibrated for Phemex. The formula Δt_eff = θ²/σ² provides the structural relationship; the practical scaling factor (CANCEL_THRESHOLD_SCALING_FACTOR = 1.0 above) is a hypothesis requiring empirical calibration from ST2.0's own fills.

2. **The equation-30 first-order condition for θ*** was not captured (page offset exceeded). The formula given (θ* implied by Δt_eff = θ²/σ²) is the structural relationship — the exact optimizer depends on equation 30, which may impose additional terms. The threshold formula above is therefore a structural starting point, not a fully derived optimum.

3. **σ computation frequency matters.** The bot runs at 60s cycles. If σ is computed from ws_feed.py tape data (sub-second), the vol estimate leads the cancel check by up to 60s. In rapidly changing vol regimes, the σ used for threshold computation may not match the σ at the time the price moves. This is the same caveat as Tweak 76.

4. **Tweak 60 (fixed threshold) and Tweak 77 (adaptive) are mutually exclusive.** If Tweak 77 is deployed, Tweak 60 becomes redundant. The adaptive version subsumes the fixed version when σ is within the clamp range.

---

## (c) Caveats and Unverified Items

1. **LIPIcs AFT 2026.36 (Jia, Moallemi, Wang, Zeng — "Who Loses and Why? Market Microstructure of Perpetual Futures"):** Verified via entity page. Covers Hyperliquid DEX wealth distribution ($1.11B retail losses, $208M MM gains). No actionable CEX maker execution insight — it is a descriptive study of trader-class P&L, not a prescriptive execution paper. Excluded from tweak stack.

2. **arXiv 2605.06405 (Le — "Funding-Aware Optimal Market Making for Perpetual DEXs"):** Verified via abstract. Addresses two-sided DEX market making with stochastic funding rates (HJB approach). Explicitly does not model "queue position, latency, maker priority, cancellation behavior, or adverse selection conditional on being filled" — the exact dimensions relevant to ST2.0. No actionable tweak for Phemex CEX one-sided posting. Excluded.

3. **arXiv 2607.11888, equation 30 (full θ* first-order condition): NOT fully fetched.** Page content truncated at character 100,000. The structural formula from Proposition 3.7 header is verified; the complete optimizer form is not. Tweak 77's implementation uses the structural relationship (Δt_eff = θ²/σ²) as its basis. An additional fetch session could capture equation 30 to refine the formula.

4. **SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): Still UNVERIFIED.** HTTP 403 in prior sessions. Not re-attempted tonight. Excluded.

5. **Microstructure Lab Substack (post-sweep delayed entry): Still PAYWALLED.** Not re-attempted. Still a candidate if access is obtained.

6. **q-fin.TR October 2026 arXiv:** No genuinely new papers emerged from tonight's searches beyond those already in the prior stack (N81–N83 confirmed empty for 3 months; tonight's searches confirm no new papers beyond those already indexed through N85).

---

## Summary

| Tweak | Description | Priority | Source | Status |
|-------|-------------|----------|--------|--------|
| 77 | σ-adaptive cancel threshold: replace fixed price-deviation cancel (Tweak 60) with θ* = σ√(Δt_eff), calibrated to bot's 60s cycle latency | Medium | arXiv 2607.11888 Prop. 3.7 (same paper as Tweak 76; different section) | NEW — VERIFIED |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry timing (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer) | TBD | Academic | PARTIALLY FETCHED |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite for bps analysis)
2. Tweak 75 — OBI upper-bound gate (band filter, independently deployable)
3. Tweak 76 — Realized-vol pre-entry gate (high-σ regime avoidance)
4. Tweak 77 — σ-adaptive cancel threshold (upgrade to Tweak 60; shares vol buffer with Tweak 76) ← NEW
5. Tweak 74 — stale-gate per-cycle re-validation
6. Tweak 72 — funding-window gate
7. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging

**Note on Tweaks 76 + 77 co-deployment:** Both use the same realized-vol buffer (`_realized_vol()` / `_recent_trade_prices[]`). If deployed together, the vol computation runs once per cycle and feeds both: the pre-entry gate (Tweak 76) and the resting-order cancel threshold (Tweak 77). Implementation complexity for the combined deploy is barely more than either alone.

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate, ξ potentially ≥ 1 at small size) remains unaddressed. Tweak 77 is an execution-precision measure — it tunes the cancel trigger to the bot's actual latency structure rather than using an arbitrary fixed threshold — but does not compensate for the structural adverse-selection deficit.
