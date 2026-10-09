# ST2.0 Execution Optimization — Night 85 (2026-10-09)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–75 across Nights 1–84. Tweak 75 (N84): OBI upper-bound gate (arXiv 2602.00776). Tweak 74 (N83): per-cycle stale-gate cancel (arXiv 2607.28323). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Prior coverage confirmed (not repeated):**
- Queue position/rank proxy + time-to-fill logging (Tweaks 47/65 — #1 priority)
- OFI/OBI binary gates and continuous placement offset (Tweaks 57, 59, 64, 67)
- Exponential-decay optimal posting depth (Tweak 68)
- Cancel-on-price-deviation (Tweak 60), queue-depletion cancel (Tweak 69)
- Cancel-side asymmetry (Tweak 70), transient-order OBI filter (Tweak 71)
- Funding-window gate (Tweak 72), rolling OBI percentile logging (Tweak 73)
- Stale-gate per-cycle re-validation (Tweak 74), OBI upper-bound gate (Tweak 75)
- arXiv 2607.28323 (Barzykin et al. — passive market impact, NASDAQ/FX), arXiv 2602.00776 (Guo et al. — OFI SHAP, crypto)

**What is genuinely NEW tonight:**

1. **arXiv 2607.11888 (Zeng & Liu, August 2026)** — "Optimal Adaptive Market Making: A Theoretical Framework for High-Yield Liquidity Provision in Perpetual Futures Markets." VERIFIED — arXiv abstract page fetched; HTML page fetched for direct quote extraction. NOT in any prior report. This is the first paper in the nightly series that is (a) explicitly about perpetual futures, (b) explicitly about the zero-maker-fee regime (directly matching Phemex's structure), and (c) provides a formal decomposition of adverse selection with a closed-form optimal spread that includes a volatility-squared term. The key portable finding for ST2.0: **optimal posted spread grows with σ²** — meaning ST2.0's fixed-offset posting approach is systematically underpriced in high-volatility regimes, guaranteeing adverse selection in those conditions.

2. **arXiv 2508.06788 (Takahashi, October 2025)** — "Returns and Order Flow Imbalances: Intraday Dynamics and Macroeconomic News Effects." VERIFIED abstract and title at arxiv.org. NOT in any prior report. Studies S&P 500 E-mini futures at 1-second frequency. Finding: "structural parameters and volatilities also exhibit pronounced intraday variation tied to liquidity, trading intensity, and spreads." OFI price impact and return impact vary by intraday session window, with "impulse responses indicating shocks dissipate almost entirely within a second." Limited applicability to Phemex crypto perps (different asset class, different microstructure) — included as structural corroboration of intraday OFI seasonality only.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 76 — Realized-Volatility Gate: Skip Entries in High-σ Regimes

**Source:** Zeng, M. & Liu, Y. "Optimal Adaptive Market Making: A Theoretical Framework for High-Yield Liquidity Provision in Perpetual Futures Markets." arXiv 2607.11888. August 2026.
**Source URL:** https://arxiv.org/abs/2607.11888
**Verification:** Abstract fetched. HTML fetched for direct quote extraction. Direct quotes obtained.

**Verified claims (direct quotes from the paper):**

From the abstract:
> "We model the market maker's problem as a stochastic optimal control problem on a filtered probability space, where the controls are adaptive bid-ask spreads and inventory hedging decisions across two exchanges."
> "high-APY Regime Theorems that characterize, in terms of five dimensionless parameters, the precise regions where annualized Sharpe ratios exceed given thresholds"

From Corollary 4.4 (verbatim from HTML):
> "The optimal total spread (bid–ask) is: s∗(t,q) = 2/k + γσ²(T−t) + 2α"

From Definition 3.14 (verbatim from HTML):
> "The MM is profitable per fill when ξ < 1 (ignoring inventory and hedging costs)."

Where ξ = α/δ̄ is the adverse selection intensity ratio (adverse selection α divided by posted half-spread δ̄).

From Theorem 3.6, equation 25 (verbatim):
> "α = π·αinfo + (1−π)·cℓσ√(Δt)"

Where π is the informed-trading fraction and the second term is the latency adverse-selection cost scaling with σ√(Δt).

**Structural insight for ST2.0:**

The optimal spread formula s∗ = 2/k + γσ²(T−t) + 2α is the core finding. It states that optimal posting distance grows with the square of local volatility σ. ST2.0 posts at a fixed depth from mid (a constant offset, not dynamically scaled to σ). In high-σ regimes:

- The paper's s∗ formula says optimal spread is wider — but ST2.0 continues posting at the same fixed offset.
- The latency adverse selection term (1−π)·cℓσ√(Δt) also grows with σ — so even the "uninformed" component of adverse selection worsens.
- Combined: in high-σ regimes, ST2.0 simultaneously (a) posts too tight relative to optimal, and (b) suffers amplified latency-driven adverse selection.

This is a different cause than the OBI upper-bound problem from Tweak 75 (adverse selection from extreme order-book imbalance) — it is a regime-level condition that makes passive posting systematically worse regardless of instantaneous OBI.

**Proposed Tweak 76:** Add a realized-volatility gate as a pre-entry filter:

```python
import numpy as np

VOLATILITY_LOOKBACK_TRADES = 50        # recent ticks to compute realized vol
VOLATILITY_GATE_PERCENTILE = 85        # block if vol > 85th pct of rolling distribution
VOLATILITY_ROLLING_WINDOW = 2 * 60    # 2-hour rolling buffer for percentile computation

def _realized_vol(self, symbol: str) -> float | None:
    """Returns annualized realized vol from recent trade prices."""
    prices = self._recent_trade_prices[symbol][-VOLATILITY_LOOKBACK_TRADES:]
    if len(prices) < 10:
        return None
    log_returns = np.diff(np.log(prices))
    return float(np.std(log_returns) * np.sqrt(len(log_returns)))  # unannualized is fine

def _st2_vol_gate(self, symbol: str) -> bool:
    """Pass if local realized vol is NOT in the high-vol regime (below gate percentile)."""
    vol = self._realized_vol(symbol)
    if vol is None:
        return True  # insufficient data → allow, log as vol_gate_unknown
    pct_rank = percentile_rank(vol, self._vol_rolling_buffer[symbol])
    return pct_rank <= VOLATILITY_GATE_PERCENTILE

# In ST2.0 entry check:
# if not self._st2_vol_gate(symbol): skip, log reason="vol_gate_block", vol=vol, pct_rank=pct_rank
```

**Why this is new vs. existing tweaks:**
- Tweak 68: posting depth as a function of queue rank (not volatility)
- Tweak 60: cancel on adverse price movement (reactive, not pre-entry)
- Tweak 74: cancel when OBI/tape no longer valid (condition-based, not vol-based)
- Tweak 75: OBI upper-bound (imbalance magnitude, not vol regime)
- **Tweak 76:** Pre-entry gate based on LOCAL REALIZED VOLATILITY — the first volatility-regime-conditioned entry filter in the stack. The rationale is grounded in a closed-form theorem (Corollary 4.4): in high-σ regimes, optimal spread widens but ST2.0's fixed offset doesn't, making every fill structurally adversely selected vs. optimal pricing.

**Forward-test design:**
- Shadow mode: log `vol_pct_rank` and `realized_vol_estimate` on every ST2.0 entry attempt.
- Primary analysis: segment post-fill adverse-selection bps by vol percentile bucket (0–50, 50–75, 75–85, 85–95, 95–100). Hypothesis: fills in the 85–100 bucket show materially worse post-fill adverse selection bps.
- Secondary: compare win rate by vol bucket. If entries at vol_pct_rank > 85 have WR < 35% vs. the overall 41.5% fill WR from the synthesis, the gate is justified.
- The 85th percentile threshold is a starting hypothesis derived from the paper's concept of the high-σ regime; requires calibration from ST2.0's own data once Tweak 47/65 (time-to-fill logging) is active.

**Implementation complexity:** Low-to-medium. Requires a rolling buffer of recent trade prices per symbol (likely already partially available via ws_feed.py tape data) and a rolling 2h vol distribution. No new data feeds; uses existing tape price ticks.

**Priority:** Medium. This is the first volatility-regime gate in the entire 75-tweak stack — a structurally distinct entry-filter dimension from all prior tweaks, which filter on OBI magnitude, tape ratio, funding timing, or queue conditions. It is independently deployable in shadow mode (no dependency on Tweak 47/65), though Tweak 47/65 data would allow calibrating the bps cost of high-vol fills directly. Should sit alongside Tweak 75 in the priority queue — both are "adverse-selection avoidance by regime" gates.

**Caveats:**
- arXiv 2607.11888 is a THEORETICAL paper with no empirical crypto perp calibration. The constants k (fill intensity decay), γ (risk aversion), and α (adverse selection per fill) from Corollary 4.4 are not measured for Phemex BTC/ETH. The structural result (s∗ ∝ σ²) is the portable claim; the specific functional form is theory, not measured from our symbols.
- The ξ < 1 profitability condition from Definition 3.14 excludes "inventory and hedging costs" per the paper's own quote — the practical profitability threshold for ST2.0 (which has no cross-exchange hedge) is below ξ < 1.
- The paper is explicitly about market MAKERS who post both sides (bid + ask). ST2.0 posts one-sided (ask only, short-reversion). The paper's framework applies structurally to the ask-side posting; the inventory management framework (cross-exchange hedging) is not relevant to ST2.0.
- The 85th percentile gate threshold is hypothesis-only. The relationship between realized vol percentile and adverse selection bps needs empirical confirmation from ST2.0's own data.

---

## (c) Caveats and Unverified Items

1. **arXiv 2508.06788 (Takahashi, S&P 500 E-mini): Different asset class.** The finding that OFI structural parameters exhibit "pronounced intraday variation" is plausible for crypto perps but not verified on those markets. Tweak 72 (funding-window gate) already covers intraday timing for perps via the funding-cycle mechanism. arXiv 2508.06788 provides no additional actionable tweak beyond what Tweak 72 already captures; included as structural corroboration only, not as a tweak basis.

2. **arXiv 2607.11888 constants not calibrated.** The optimal spread formula requires k (fill intensity decay rate) calibrated to Phemex's order book depth profile. k varies by symbol (BTC vs. ETH vs. altcoins) and volatility regime. The formula is a qualitative guide (s∗ grows with σ²), not a deployment formula.

3. **SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): Still UNVERIFIED.** Searches tonight confirmed no accessible preprint or open-access version. HTTP 403 confirmed in prior sessions. Excluded.

4. **The Microstructure Lab Substack (order-book resilience after sweeps): Still PAYWALLED.** Not re-fetched. The lead (delayed entry 10–30s after OBI peak during book recovery) remains unverified.

5. **arXiv q-fin.TR October 2026:** Not re-fetched tonight (three consecutive months confirmed empty as of N81). No new submissions expected in a 48-hour window.

---

## Summary

| Tweak | Description | Priority | Source Type | Status |
|-------|-------------|----------|-------------|--------|
| 76 | Realized-vol gate: skip ST2.0 entries when short-window σ > 85th rolling percentile | Medium | Academic (perp futures, theoretical; portable structural result) | NEW — VERIFIED |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite for bps analysis)
2. Tweak 75 — OBI upper-bound gate (adverse selection avoidance at extreme imbalance)
3. Tweak 76 — Realized-vol gate (adverse selection avoidance in high-σ regimes) ← NEW
4. Tweak 74 — stale-gate per-cycle re-validation
5. Tweak 72 — funding-window gate
6. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
7. Tweak 71 — transient-order OBI filter

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate, ξ potentially ≥ 1 at small size) remains. Tweak 76 is an adverse-selection avoidance measure that reduces entries in the highest-risk volatility regime, consistent with the arXiv 2607.11888 theorem that profitability requires ξ < 1. Both Tweaks 75 and 76 are regime-avoidance gates that trim the distribution of entries toward lower-adverse-selection conditions; neither compensates for the structural deficit in the conditions that remain.
