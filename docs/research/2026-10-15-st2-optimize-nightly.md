# ST2.0 Execution Optimization — Night 89 (2026-10-15)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–79 across Nights 1–88. Night 88 (2026-10-14): Tweak 79 (tape intensity gate, Kitron & Wengrowicz arXiv 2608.21888 dose-response). Night 87: Tweak 78 (gate hysteresis / trip-rearm dead-band). Night 86: Tweak 77 (σ-adaptive cancel threshold). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Papers re-surfaced and confirmed already in corpus (not repeated):**
- arXiv 2502.18625 (Binance BTC perp maker, "Market Maker's Dilemma") — in corpus since synthesis. Re-surfaced in repricing/chasing search. Rejected again.
- arXiv 2602.00776 (Guo et al., "Explainable Patterns in Cryptocurrency Microstructure") — in corpus since synthesis/Tweak 57. Re-surfaced. Rejected.
- arXiv 2609.18019 (Maciejewski, "Model-Free Passive Execution via Order-Level Shadowing") — in corpus since Night 77. Re-surfaced in session-effects search. Rejected.
- arXiv 2607.11888 (Zeng & Liu, "Optimal Adaptive Market Making") — in corpus since Night 85. Re-surfaced in equation-30 search. Proposition 3.7 / Section 8.7 confirm the θ* interior optimum and Figure 8 (PnL rate vs θ) are documented; equation 30 exact form still not captured. Not re-attempted tonight.
- arXiv 2606.15715 (Barone/Lillo, Hyperliquid adverse selection) — in corpus since Night 82. Re-surfaced. Rejected.
- arXiv 2605.06405 (Le, funding-aware optimal MM for DEXs) — in corpus since Night 86. Re-surfaced. Rejected.
- arXiv 2510.27334 (RL market maker vs. MFT meta-order simulation, Hawkes LOB): Fetched tonight. RL market making in synthetic simulation; no crypto data, no maker fill quality or adverse selection results. Not applicable. Excluded.
- Multicoin Capital "Adverse Selection Rules Everything Around Me" (Feb 2026): Fetched tonight. Primarily covers DeFi/DEX venues. CEX perpetual content limited to practitioner commentary. One noteworthy item: Binance has implemented a maker order type (analogous to Retail Price Improvement) that "hides limit orders from API access" to reduce adverse selection from API-driven informed flow. However, no Phemex-equivalent feature exists based on Phemex's own documentation (post-only help pages confirm standard post-only only; no API-hidden variant). Not actionable for Phemex CEX. Excluded from tweak stack.

**What is genuinely NEW tonight:**

**arXiv 2607.09426 (Kim & Hansen, "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures")**

This paper is NOT in the prior corpus. Nights 86–88 confirmed no prior fetch; search history confirms no prior mention. Submitted to q-fin.TR, July 2026. HTML version fetched tonight.

**Verification:** HTML page fetched at https://arxiv.org/html/2607.09426v2. Direct quotes extracted from abstract and quantitative results tables.

**Direct quotes (fetched tonight):**

Abstract:
> "Opening returns are predictable out of sample."

> "Opening order imbalance predicts returns over roughly four to twelve hours, with much weaker effects at finer clock-time frequencies."

From the quantitative analysis (section on the CFE / short-horizon results):
> "The CFE is negative over the first half hour, consistent with a short-run reversal following boundary imbalance."

> "consistent with the adverse selection that algorithmic order flow can impose on liquidity suppliers in equilibrium"

> "liquidity providers may adjust quotes and inventory ahead of quarter-hour openings"

**Quantitative results (verified from paper):**

Quarter-hour opening windows (first 10 seconds vs. ordinary minutes):
- **+26% more trades**, **+32% higher dollar volume**, **+26% larger absolute returns** (all significant at 1%)
- Out-of-sample AUC for return direction: **0.6011** (lag + timing indicator) vs. 0.5908 (lag only)
- Out-of-sample continuous-return R²: **3.367%** (lag + TI28) vs. 2.464% (lag only)
- ETH specifically: R² = 4.772% (highest among the six contracts; BTC 3.822%)
- **Short-run (first 30 min): CFE negative** — boundary imbalance is followed by reversal
- Medium-run (4–12 hours): same-direction persistence
- Economic magnitude: **~0.5 bp per boundary** (gross forecast target, before fees)
- Excluding funding-settlement quarter-hours (00:00, 08:00, 16:00 UTC): pattern unchanged

**Scope limitations of the paper:**
The paper's data "do not include order-book updates." It measures RETURNS and ORDER FLOW, not maker fill quality or adverse selection on individual resting orders. The adverse-selection inference ("liquidity suppliers may adjust quotes") is a conceptual interpretation, not a measured fill-quality result. The paper does NOT directly test whether maker orders placed at quarter-hour marks underperform.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 80 — Quarter-Hour Activity Gate: Shadow-Log Entry Proximity to UTC Quarter-Hour Marks

**Source:** Kim, J. & Hansen, P. "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures." arXiv:2607.09426v2. July 2026.
**Source URL:** https://arxiv.org/html/2607.09426v2
**Verification:** HTML page fetched tonight. Direct quotes extracted from abstract and quantitative results. Paper uses Binance USDT-margined perp data; NOT Phemex. Results are on ETH and BTC among six contracts. Paper is an arXiv preprint (q-fin.TR), NOT peer-reviewed yet.

**Structural motivation:**

ST2.0 posts a passive SELL into buy-heavy order books. The quarter-hour effect paper documents that at UTC :00, :15, :30, and :45 marks, algorithmic trading activity is significantly elevated: 26–32% more volume, larger absolute returns, and the paper concludes "consistent with the adverse selection that algorithmic order flow can impose on liquidity suppliers in equilibrium." The paper further notes "liquidity providers may adjust quotes and inventory ahead of quarter-hour openings."

For ST2.0 specifically, the quarter-hour opening creates two countervailing forces:

1. **Higher fill probability**: Volume is 32% higher, so a resting passive SELL at the ask is more likely to be hit.
2. **Higher adverse selection probability**: Algorithmic activity is elevated, meaning the flow hitting the resting order is more likely to be information-driven (not reversal-prone retail flow). The paper's CFE shows a SHORT-RUN REVERSAL in the first 30 minutes after boundary imbalance — meaning price does tend to reverse after quarter-hour buying. But: the post-fill continuation risk is amplified by algorithmic presence. More of the fill events will come from algorithmic takers who correctly anticipate near-term direction.

The synthesis (2026-06-20) established: "fills cluster at extreme imbalance — you fill precisely when buying continues." The quarter-hour window concentrates the most algorithmically-driven buying of the cycle. A resting passive short filled during a quarter-hour burst is filled by the most aggressive and potentially most informed buyers of that cycle.

This is a different dimension from Tweak 72 (funding-window gate, which blocks the 3 daily funding-settlement quarter-hours: 00:00, 08:00, 16:00 UTC). The Kim & Hansen paper shows the pattern is **unchanged when excluding funding-settlement marks** — meaning the other 93 daily quarter-hour marks also show elevated activity. Tweak 80 would gate on ALL 96 daily quarter-hour marks, not just the 3 funding ones.

**Proposed Tweak 80 — implementation (shadow mode only):**

```python
from datetime import datetime, timezone

QUARTER_HOUR_PROXIMITY_SECONDS = 120  # ±2 minutes of UTC :00/:15/:30/:45

def _is_near_quarter_hour(self) -> bool:
    """
    Returns True if the current UTC time is within QUARTER_HOUR_PROXIMITY_SECONDS
    of a quarter-hour mark (UTC :00, :15, :30, or :45).
    Based on arXiv 2607.09426: elevated algorithmic activity at these boundaries
    may increase adverse selection for resting passive orders.
    """
    now = datetime.now(timezone.utc)
    seconds_into_hour = now.minute * 60 + now.second
    nearest_quarter = round(seconds_into_hour / 900) * 900  # 900s = 15 min
    distance = abs(seconds_into_hour - nearest_quarter)
    # Handle wrap-around (e.g., 59:50 is 10s from :00)
    distance = min(distance, 3600 - distance)
    return distance <= QUARTER_HOUR_PROXIMITY_SECONDS

# In ST2.0 entry logic — shadow mode only:
# near_qh = self._is_near_quarter_hour()
# self._log(f"quarter_hour_proximity near={near_qh} timestamp={datetime.now(timezone.utc).isoformat()}")
# For now: log only; do NOT gate entry. Compare win_rate[near=True] vs win_rate[near=False].
```

**Forward-test design (shadow only):**

Log `near_quarter_hour` (True/False) on every ST2.0 entry attempt and every fill.

- **Primary hypothesis:** Entries where `near_quarter_hour=True` show lower win rate and/or higher post-fill adverse selection bps than entries where `near_quarter_hour=False`.
- **Secondary hypothesis:** Fill rate during `near_quarter_hour=True` is higher (consistent with 32% volume increase), but the wins-per-fill ratio is worse.
- **If primary hypothesis confirmed (WR near=True < WR near=False by ≥10pp across n≥30 fills):** Promote to a hard gate blocking ST2.0 entries within ±2 minutes of quarter-hour marks. Estimated gate frequency: with n=96 quarter-hour marks per day × 4 minutes blocked per mark = 384 minutes blocked / 1440 minutes total = ~27% of trading time blocked.
- **If primary hypothesis rejected:** The elevated algorithmic activity does not meaningfully differentiate ST2.0 adverse selection. Do not promote to a gate.

**Why the 15-min reversion window matters here:**

ST2.0 holds for ~15 minutes. The Kim & Hansen paper shows SHORT-RUN REVERSION in the first 30 minutes after a boundary imbalance event. This is structurally aligned with ST2.0's expected PnL if the fill happens during a genuine absorption event. However, the algorithmic-flow contribution to fills may produce a subset of fills that continue against the short (the 0.5 bp gross signal, before fees, is insufficient to overcome adverse selection + SL costs without high fill quality). Shadow-logging quarter-hour proximity gives ST2.0's own data a chance to disambiguate.

**Implementation complexity:** Minimal. One time-based function, one log line per entry attempt. No new data feeds. No change to execution behavior in shadow mode.

**Implementation dependency:** Independent of all prior tweaks. Can be shadow-deployed immediately.

**Interaction with existing gates:**
- Tweak 72 (funding-window gate) blocks entries near the 3 funding-settlement quarter-hours (00:00, 08:00, 16:00 UTC). Tweak 80 would separately flag entries near the remaining 93 quarter-hour marks. The two are complementary, not redundant.
- Tweak 76 (vol gate) and Tweak 75 (OBI upper-bound) may correlate with quarter-hour proximity since volume and OBI spikes occur at these marks. If the vol/OBI gates are deployed, they may already capture some quarter-hour adverse events — this overlap would reduce the incremental value of Tweak 80. Worth measuring.

**Priority:** Low-to-medium. Start as a pure shadow observation (zero execution risk, zero implementation risk). Promote to a gate only if the data confirms the hypothesis. Given the synthesis conclusion that ST2.0 is "execution-trapped," understanding whether quarter-hour algorithmic bursts concentrate the adverse fills is a diagnostically useful measurement even if it doesn't change execution.

**Caveat on direction:** The paper says the short-run (30-min) return following boundary imbalance is a REVERSAL (CFE negative). This is actually the CORRECT direction for ST2.0. It's possible that quarter-hour windows are BETTER entry points for the short-reversion signal, not worse. The shadow log will resolve this ambiguity.

---

## (c) Caveats and Unverified Items

1. **arXiv 2607.09426 is on Binance USDT-margined perp data, not Phemex.** The six contracts are BTC, ETH, XRP, SOL, DOGE, ADA. Phemex's microstructure (liquidity, taker composition, maker depth) differs. The quarter-hour effect magnitude (26–32% activity increase) may differ on Phemex. Used as structural motivation, not as directly calibrated Phemex data.

2. **The paper does not measure maker fill quality or adverse selection on individual orders.** The adverse-selection inference is conceptual ("consistent with ... adverse selection that algorithmic order flow can impose on liquidity suppliers"). The paper explicitly states its data do not include order-book updates. The forward-test design above directly tests what the paper can only infer.

3. **Direction ambiguity.** The short-run (30-min) CFE is NEGATIVE — boundary imbalance is followed by price reversal. This could mean quarter-hour entries are BETTER for ST2.0 (more reliable reversion signal), not worse. The shadow log resolves this.

4. **27% of trading time blocked if gate is confirmed.** A gate blocking ±2 min of all 96 daily quarter-hours blocks approximately 384/1440 ≈ 27% of cycles. This would substantially reduce ST2.0's entry frequency. Calibrate proximity window carefully if promoted to a gate.

5. **Persistent unverified leads (unchanged from Night 88):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403 persists. Not re-attempted tonight.
   - Microstructure Lab Substack (post-sweep delayed entry): Still paywalled.
   - arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77): Still not fully captured.

6. **Binance "API-hidden maker order" (RPI-analog):** Confirmed not available on Phemex by documentation check. Not actionable.

---

## Summary

| Tweak | Description | Priority | Source | Status |
|-------|-------------|----------|--------|--------|
| 80 | Quarter-hour activity gate: shadow-log `near_quarter_hour` flag on every ST2.0 entry; compare win rate and adverse selection bps near vs. far from UTC :00/:15/:30/:45 marks | Low-medium (shadow only until data confirms) | arXiv 2607.09426 (Kim & Hansen, July 2026, Binance perp data, q-fin.TR preprint) | NEW — VERIFIED (paper fetched, quotes extracted); hypothesis direction ambiguous — shadow log required to resolve |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry timing (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |
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
11. **Tweak 80 — Quarter-hour proximity shadow log** ← NEW (observe-only until hypothesis confirmed)

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed. Tweak 80 adds a shadow-logging observation that may reveal whether quarter-hour algorithmic bursts disproportionately produce ST2.0's adverse fills — at zero execution risk and minimal implementation cost.
