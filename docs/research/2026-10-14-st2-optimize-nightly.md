# ST2.0 Execution Optimization — Night 88 (2026-10-14)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–78 across Nights 1–87. Night 87 (2026-10-13): Tweak 78 (gate hysteresis / trip-rearm dead-band). Night 86: Tweak 77 (σ-adaptive cancel threshold). Night 85: Tweak 76 (realized-vol pre-entry gate). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Papers surfaced and confirmed already in corpus (rejected):**
- arXiv 2502.18625 (Binance BTC perp maker, "Market Maker's Dilemma") — in corpus since synthesis (2026-06-20). Re-surfaced in multiple searches tonight. The "Reversals" strategy finding (contrarian maker at the touch) and the negative fill-rate/return correlation are confirmed in corpus. Not repeated.
- arXiv 2602.00776 (Guo et al., "Explainable Patterns in Cryptocurrency Microstructure") — in corpus since synthesis / Tweak 57 onwards.
- arXiv 2407.16527 (DeLise, "Negative Drift of a Limit Order Fill") — in corpus since Night 29.

**Searched and confirmed NOT actionable:**
- arXiv 2607.09230 (Jeon, "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures," July 2026): Fetched tonight. Key finding: "Order flow adds further value only when layered on top of the L2 state model, not as a replacement." The OFI value is inconsistent across symbols (ETH: present in calm/mixed/stressed regimes; BTC: "only isolated five-minute passes"). This paper models discrete L2 state transitions and explicitly does NOT address price-direction prediction, maker entry timing, fill quality, or adverse selection. No specific thresholds for a "stressed" L2 state are provided. No actionable execution tweak derivable without significant additional calibration. **Not added to tweak stack.** Included as a note that L2 regime context modulates OFI predictability — consistent with existing Tweaks 75/76 (regime-avoidance gates) but without adding a specific new gate.

**What is genuinely NEW tonight:**

**arXiv 2608.21888 (Kitron & Wengrowicz, "Short-horizon mean reversion in cryptocurrency markets: a matched cross-market measurement," August 2026)**

This paper is NOT in the prior corpus (N85/N86/N87 prior coverage lists confirm it has not appeared; search history confirms no prior fetch). It was submitted to q-fin.TR on 22 August 2026.

**Verification:** HTML page fetched at https://arxiv.org/html/2608.21888. Direct quotes extracted from abstract and sections 1, 5.1, 5.2, and Figure 7 caption.

**Direct quotes (fetched tonight):**

Abstract:
> "the reversal concentrates after moves driven by aggressive taker flow and grows with flow intensity"

Section 5.1:
> "Flow conditions the reversal but does not replace it"

Figure 7 caption:
> "Reversal concentrates after flow-driven moves and grows with the flow."

Section 1:
> "the flow conditioning is consistent with compensated liquidity provision but cannot exclude informational alternatives"
> "the signature of liquidity provision compensating overreaction in a book that re-forms within the bar"

Section 5.2:
> "compensation for supplying immediacy, competed down to roughly the cost of competing for it"
> "not one of the 183 crypto pairs clears even the 5 bp maker band at any threshold"

**Quantitative results (verified from paper):**
- 90% of 183 Binance spot pairs show significant directional reversal at 15-minute horizon (vs. ~3% of 187 US stocks/ETFs)
- Gross edge peaks near 1.3 bp/trade
- Flip-rate difference between flow-driven and flow-opposed bars: **+0.021** (95% CI: 0.015 to 0.026)
- OOS walk-forward AUC: **0.540 after flow-driven bars** vs. **0.519 after flow-opposed bars**
- Quintile analysis (Figure 7a): dose-response pattern — higher absolute taker imbalance quintile → higher flip probability (specific quintile boundaries not reported in fetched content)
- "within fifteen minutes the book has re-formed, whatever the move did to it"
- Signal decays: "monotonically and is gone by four hours"
- No exploitable cross-venue lead at 1–10 minute lag (IBIT/Binance BTC r = 0.982 contemporaneous, but lagged correlation ≤ 0.013)

**Why this is new vs. the prior 78 tweaks:**

The existing ST2.0 tape gate uses a binary buy_ratio threshold (≥ 0.55 for longs blocked, shorts allowed entry only when buying is present). This is a **directional condition** — is taker buying happening?

The Kitron & Wengrowicz dose-response finding introduces a separate dimension: **intensity conditioning**. Within the set of "buying is happening" events, the paper shows a monotone dose-response: higher absolute taker imbalance quintile → systematically higher reversal probability. The 0.540 vs 0.519 AUC split between flow-driven and flow-opposed bars quantifies the marginal execution benefit of selecting only the higher-intensity subset.

For ST2.0 adverse selection specifically: a resting passive short that fills DURING strong taker buying faces the question "will price continue up post-fill?" The Kitron paper says: the stronger the taker flow, the stronger the expected reversion — meaning the post-fill continuation probability is LOWER when flow intensity is higher, and HIGHER when flow intensity is weaker. This directly maps to adverse selection probability: strong-intensity events are better execution environments than weak-intensity events that just barely pass the 0.55 threshold.

No prior tweak conditions on flow INTENSITY within the buy_ratio domain. Tweak 64 (OFI continuous placement offset) adjusts posting depth based on OFI magnitude but does not gate entries. The existing buy_ratio gate is binary (above/below 0.55). Tweak 79 proposes conditioning on whether the current flow event is high-intensity (top quintile) vs. low-intensity (barely above threshold).

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 79 — Tape Intensity Gate: Require High-Intensity Taker Absorption (Top Quintile) for ST2.0 Entry

**Source:** Kitron, N.A. & Wengrowicz, J.M. "Short-horizon mean reversion in cryptocurrency markets: a matched cross-market measurement." arXiv:2608.21888. August 2026.
**Source URL:** https://arxiv.org/html/2608.21888
**Verification:** HTML page fetched tonight. Direct quotes extracted from abstract, Section 1, 5.1, 5.2, and Figure 7 caption. Paper is a q-fin.TR empirical measurement study, NOT peer-reviewed yet (arXiv preprint).

**Structural motivation:**

ST2.0 is a short-reversion strategy that posts a passive SELL into bid-heavy buying. The synthesis established that the fills you actually get are adversely selected: you fill precisely when buying continues (not reverses). The Kitron paper quantifies this directly on the execution side: **the probability of reversal (good for the short) grows monotonically with taker flow intensity.** Selecting only high-intensity events reduces adverse selection because the mean-reversion force is stronger — the post-fill continuation probability is lower.

The existing binary gate (buy_ratio ≥ 0.55) selects ALL buying events above a minimal threshold. A high-intensity gate would select only events where buying is strong enough that the dose-response relationship meaningfully improves the reversion probability.

**Proposed Tweak 79:**

Add a rolling percentile rank of the current buy_ratio (or taker imbalance magnitude) against its recent distribution, and require the current reading to be in the top N% (starting hypothesis: top 30% = 70th percentile, requiring buy_ratio to be genuinely elevated, not just marginally above 0.55).

```python
TAPE_INTENSITY_GATE_PERCENTILE = 70   # require buy_ratio in top 30% of recent distribution
TAPE_INTENSITY_LOOKBACK_CYCLES = 120  # 2-hour rolling window at 60s cycles

def _st2_tape_intensity_gate(self, symbol: str, buy_ratio: float) -> bool:
    """
    Returns True (allow entry) only when the current buy_ratio is in the top N% of
    recent readings for this symbol. Reduces adverse selection by selecting high-intensity
    absorption events where mean-reversion probability is highest.

    Source: Kitron & Wengrowicz arXiv 2608.21888 dose-response finding:
    "reversal concentrates after moves driven by aggressive taker flow and grows with flow intensity"
    """
    history = self._buy_ratio_history[symbol][-TAPE_INTENSITY_LOOKBACK_CYCLES:]
    if len(history) < 20:
        return True  # insufficient history → allow; log as tape_intensity_unknown
    pct_rank = sum(1 for h in history if h <= buy_ratio) / len(history) * 100
    passes = pct_rank >= TAPE_INTENSITY_GATE_PERCENTILE
    self._log(f"tape_intensity symbol={symbol} buy_ratio={buy_ratio:.3f} pct_rank={pct_rank:.1f} gate={'PASS' if passes else 'BLOCK'}")
    return passes

# In ST2.0 entry check (after existing buy_ratio ≥ 0.55 gate):
# if not self._st2_tape_intensity_gate(symbol, buy_ratio):
#     skip, log reason="tape_intensity_block"
```

**Why intensity, not just the existing threshold:**

The existing gate is: buy_ratio ≥ 0.55. But if the symbol's typical buy_ratio during absorption events is 0.70–0.85, a reading of 0.57 barely passes the current gate and is in the bottom half of the symbol's absorption distribution. Per the Kitron dose-response, this is a lower-confidence reversion scenario with higher adverse selection risk. The intensity gate catches this by requiring not just directional presence of buying but quantitative strength relative to the symbol's own history.

**Forward-test design:**

Shadow mode: log `buy_ratio_pct_rank` on every ST2.0 entry attempt.

- Compare win rate and post-fill adverse-selection bps (once Tweak 47/65 is deployed) across buy_ratio_pct_rank quintiles.
- Primary hypothesis: entries in buy_ratio_pct_rank > 70 show win rate ≥ 50% (Kitron: AUC ~0.540 after flow-driven bars) vs. entries below 70 showing WR ≤ 40%.
- Secondary hypothesis: the tape_intensity_block gate fires on ~30% of current "pass" signals, reducing entry volume but improving win rate per entry.
- **If primary hypothesis confirmed:** tighten threshold toward top quintile (80th percentile). If rejected (WR doesn't differentiate by intensity), the gate adds no value and should be dropped.

**Implementation complexity:** Low. Requires a rolling buffer of recent buy_ratio readings per symbol — this buffer almost certainly exists already (ws_feed.py maintains tape state). The percentile rank computation is a one-liner. No new data feeds.

**Implementation dependency:** Independent of all prior tweaks. Can be shadow-deployed immediately alongside the existing buy_ratio gate without any prerequisite.

**Interaction with existing gates:**
- This is a STRENGTHENING of the current tape gate, not a replacement. The gate stack becomes: buy_ratio ≥ 0.55 (directional) AND buy_ratio_pct_rank ≥ 70 (intensity). If the intensity gate is deployed, the directional gate can be optionally loosened (e.g., to 0.50), since intensity rank subsumes the directional check.
- Tweak 75 (OBI upper-bound) and Tweak 76 (vol gate) are orthogonal regime-avoidance gates. All three can co-exist.
- No interaction with cancel-related tweaks (60, 69, 74, 77).

**Priority:** Medium. This is the first tweak that operates on the INTENSITY (not direction) of taker flow, grounded in a directly measured dose-response relationship on crypto spot (not perps, but the reversion mechanism is the same). Lower priority than Tweaks 47/65 (instrumentation prerequisite) but independently deployable in shadow mode without them. Once the intensity percentile rank is logged, it becomes an empirical test of the Kitron hypothesis in ST2.0's own data.

---

## (c) Caveats and Unverified Items

1. **arXiv 2608.21888 is a PREPRINT on Binance SPOT pairs, not perps.** The 15-minute reversion finding is measured on 183 Binance *spot* pairs, not perpetual futures. The dose-response finding (reversion grows with taker flow intensity) may differ in magnitude on Phemex perps due to funding-rate mechanics, different trader composition, and different liquidity profile. The directional claim (stronger flow → stronger expected reversion) is structurally plausible for perps, but the specific AUC figures (0.540 vs 0.519) are not calibrated for Phemex. Used as structural motivation with empirical quantification on analogous markets.

2. **"Not one of the 183 crypto pairs clears even the 5 bp maker band" (Section 5.2):** The paper's cost analysis uses a 5 bp round-trip threshold (approximately 2.5 bp per side). Phemex maker fee is 0% with no rebate — the gross edge comparison is different. At zero fees, the 1.3 bp gross edge is potentially viable if adverse selection and SL/TP friction are below 1.3 bp/trade. The paper's cost conclusion applies to standard fee schedules, not Phemex's structure. This is a significant caveat: even with zero fees, 1.3 bp gross edge against observed adverse selection magnitude is razor-thin.

3. **Dose-response quintile boundaries not reported.** The Figure 7a quintile analysis shows a dose-response pattern but the specific quintile boundaries (what absolute taker imbalance level defines "top quintile") are not reported in the fetched content. The 70th percentile starting hypothesis in Tweak 79 is a calibration choice, not derived from the paper's quantiles. Empirical calibration against ST2.0's own buy_ratio distribution is required.

4. **Buy_ratio vs. absolute taker imbalance.** The paper's intensity measure is "absolute taker imbalance" (excess of buy volume over sell volume, normalized). ST2.0's existing tape gate uses buy_ratio = buy_volume / total_volume. These are monotonically related for symmetric distributions but not identical. The percentile rank approach in Tweak 79 uses the symbol's own buy_ratio history as the reference distribution, which implicitly normalizes for any difference.

5. **arXiv 2607.09230 (Jeon, L2 state transitions): Not added to tweak stack.** The finding that OFI value depends on L2 state is interesting but provides no actionable gate threshold. The paper explicitly does not address maker execution or fill quality. Flagged for future consideration if L2 book-depth regime detection is added to ST2.0's instrumentation.

6. **Persistent unverified leads (unchanged):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403 persists. Not re-attempted tonight.
   - Microstructure Lab Substack (post-sweep delayed entry): Still paywalled.
   - arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77): Still partially fetched.

---

## Summary

| Tweak | Description | Priority | Source | Status |
|-------|-------------|----------|--------|--------|
| 79 | Tape intensity gate: require buy_ratio in top N% of rolling distribution (not just > 0.55), grounded in dose-response finding that reversion strength scales with flow intensity | Medium | arXiv 2608.21888 (Kitron & Wengrowicz, Aug 2026, q-fin.TR empirical preprint; Binance spot) | NEW — VERIFIED (concept + direct quotes); thresholds are hypothesis-only |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry timing (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | Academic | PARTIALLY FETCHED |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite for bps analysis)
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold (upgrade to Tweak 60; shares vol buffer with Tweak 76)
5. Tweak 78 — Gate hysteresis (ship as part of same changeset as Tweaks 75+76)
6. Tweak 79 — Tape intensity gate (independently deployable in shadow mode) ← NEW
7. Tweak 74 — stale-gate per-cycle re-validation
8. Tweak 72 — funding-window gate
9. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
10. Tweak 71 — transient-order OBI filter

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed. Tweak 79 reduces adverse selection by selecting only high-intensity flow events where the reversion force is strongest — per the Kitron dose-response finding, this improves the post-fill return distribution without addressing the structural speed/queue deficits. The 1.3 bp gross edge ceiling from Kitron means Tweak 79 is a precision improvement, not a structural fix.
