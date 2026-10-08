# ST2.0 Execution Optimization — Night 84 (2026-10-08)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–74 across Nights 1–83. Academic literature (arXiv q-fin.TR) confirmed saturated Nights 77–83 (three consecutive months, zero new submissions). Last four nights added Tweaks 70–74 (cancel-side asymmetry, transient-order OBI filter, funding-window gate, rolling OBI percentile logging, stale-gate per-cycle re-validation). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Prior coverage confirmed (not repeated):**
- Queue position/rank proxy + time-to-fill logging (Tweaks 47/65 — #1 priority)
- OFI/OBI binary gates and continuous placement offset (Tweaks 57, 59, 64, 67)
- Exponential-decay optimal posting depth (Tweak 68)
- Price-deviation cancel/repost (Tweak 60), queue-depletion cancel (Tweak 69)
- Cancel-side asymmetry gate (Tweak 70), transient-order OBI filter (Tweak 71)
- Funding-window gate (Tweak 72), rolling OBI percentile logging (Tweak 73)
- Stale-gate per-cycle re-validation (Tweak 74)
- arXiv 2608.04373 (Hyperliquid public-wallet) — reviewed N80, rejected as CEX-inapplicable
- arXiv 2606.15715 (Hyperliquid Barone/Lillo) — reviewed N82

**What is genuinely NEW tonight:**

1. **arXiv 2602.00776 (Guo et al., February 2026)** — "Explainable Patterns in Cryptocurrency Microstructure." VERIFIED — HTML page fetched at https://arxiv.org/html/2602.00776v1. NOT present in any prior report (paper pre-dates the nightly series start, but wasn't identified in earlier sweeps; not in q-fin.TR — category is cs.LG or cs.AI, which explains the gap). Key finding: OFI has a **monotone effect with concavity at extremes**. At very high OBI/OFI readings, the marginal predictive value of additional imbalance for short-horizon returns diminishes. Also verified: during a flash crash event, the maker strategy suffered severe adverse selection. This provides a formal basis for an **OBI upper-bound gate** not present anywhere in Tweaks 1–74.

2. **The Microstructure Lab Substack — "Order Book Resilience: How Fast Does the Book Recover After a Sweep?"** — PAYWALLED. Summary visible: 180,590 sweep events, 100ms resolution, 30-second observation window, multiple exchanges. Core findings (from publicly visible text only): spread and depth revert within 5–10 seconds; limit order intensity takes ~30 minutes to recover. Label UNVERIFIED — full article not accessible. Included only as a lead.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 75 — OBI Upper-Bound Gate: Block Entries at Extreme Imbalance

**Source:** Guo et al. "Explainable Patterns in Cryptocurrency Microstructure." arXiv 2602.00776. February 2026.
**Source URL:** https://arxiv.org/html/2602.00776v1
**Verification:** HTML page fetched. Direct quotes obtained.

**Verified claims (direct quotes):**
> "order flow imbalance has a largely monotone effect with concavity at extremes"

> "conservative sizing at extremes and caution when extrapolating beyond the observed domain"

The paper applies SHAP (Shapley Additive Explanations) across BTC, ETH, and altcoins on crypto markets to identify which features drive short-horizon return predictions. OFI is confirmed as a primary predictor, but the SHAP dependence plot shows a concave shape: additional imbalance signal beyond the high-imbalance region adds diminishing marginal predictive value for returns. The paper also documents that during a flash-crash event, the passive maker strategy "fell victim to severe adverse selection" — repeatedly filling on bids while prices collapsed.

**New structural insight for ST2.0:**
ST2.0's current OBI gate is a *lower bound* only (|OBI| ≥ 0.25 — enter when imbalance is strong enough). No upper bound exists. The concavity finding from 2602.00776 provides a second rationale for adding one, layered with the existing adverse-selection evidence:

1. From arXiv 2502.18625 (synthesis): fills cluster at extreme imbalance — highest adverse-selection fills occur at the highest OBI values. This is the adverse-selection side.
2. From arXiv 2602.00776 (new tonight): OFI concavity at extremes — the expected reversion signal (ST2.0's entire reason to post) also weakens at extreme OBI. This is the signal-quality side.

At very high OBI readings (e.g., > 0.7), both problems converge: fill adverse selection is highest AND the reversion signal is weakest. The entry is simultaneously most dangerous and least expected to pay off.

**Proposed Tweak 75:** Add an OBI upper-bound to the ST2.0 entry gate:

```python
# Current gate (lower bound only):
OB_IMBALANCE_GATE = 0.25  # |OBI| >= 0.25 to enter
# (bot.py:1433, 1883)

# Proposed addition (upper bound):
OB_IMBALANCE_UPPER_CAP = 0.70  # configurable; start at 0.70, tune from data

# In ST2.0 entry check:
def _st2_obi_gate(self, obi: float) -> bool:
    """Pass if OBI is in the 'sweet spot': strong enough to signal absorption,
    but not so extreme that adverse selection dominates and signal concavity kicks in."""
    return OB_IMBALANCE_GATE <= abs(obi) <= OB_IMBALANCE_UPPER_CAP

# Log: obi_at_entry for every entry attempt (fill and miss)
# Analysis: segment post-fill adverse selection bps by OBI bucket
#   (0.25–0.40, 0.40–0.55, 0.55–0.70, >0.70)
# Hypothesis: >0.70 bucket shows worst post-fill adverse selection
```

**Why this is new vs. existing tweaks:**
- Tweaks 57, 59, 64, 67: all OBI as a *lower bound* / binary enable gate
- Tweak 73: logs rolling OBI percentile (shadow-only, no gate change)
- **Tweak 75:** Adds an UPPER BOUND to the OBI gate — a structurally distinct change. The existing stack has never blocked entries at *too-high* OBI. This tweak makes the gate a band filter, not a threshold.

**Forward-test design:**
- Shadow mode: log `obi_at_entry` and `obi_category` (in-band vs. upper-cap-blocked) for every ST2.0 attempt.
- Primary analysis: do post-fill adverse-selection bps differ by OBI bucket? If the >0.70 bucket shows reliably worse bps than 0.25–0.55, the upper cap is justified.
- The 0.70 threshold is a starting hypothesis — requires calibration from ST2.0 data once Tweak 47/65 instrumentation (time-to-fill logging) is deployed. With Tweak 47/65, the adverse-selection bps calculation becomes tractable.
- Secondary analysis (no Tweak 47/65 needed): compare win rates by OBI bucket. If >0.70 OBI entries have materially worse WR than 0.25–0.55 entries, that's sufficient to pilot the gate.

**Implementation complexity:** Very low. Adds one comparison to the existing OBI gate check. No new data feeds required — uses the current `ob.imbalance` value already captured at entry time.

**Priority:** Medium. This is the first tweak to propose constraining the *upper* end of the OBI signal distribution, which is a structurally distinct entry-filter shape from everything prior. It is independently deployable in shadow mode (no dependency on Tweak 47/65 to collect the entry-bucket data, though Tweak 47/65 data enriches the calibration analysis). It should sit behind Tweaks 47/65 in the deployment queue but ahead of Tweaks 70–74 in terms of analytical novelty.

**Caveats:**
- arXiv 2602.00776 studies OFI as a DIRECTIONAL signal for a taker strategy. The "concavity at extremes" finding is about the return-prediction power of OFI for taker trades — not about passive fill adverse selection directly. The application to ST2.0 (a maker strategy) requires combining this with the adverse-selection evidence from arXiv 2502.18625 (fills cluster at extreme imbalance). The two papers together support the tweak; neither alone proves it.
- The 0.70 upper cap is arbitrary — a forward-calibration hypothesis. The right threshold depends on Phemex's OBI distribution for the traded symbols (BTC, ETH), which varies by volatility regime. Starting at 0.70 is a conservative starting point; empirically it might need adjustment to 0.65 or 0.80.
- "Concavity at extremes" is a feature-importance finding from SHAP plots, not a formal theorem about adverse selection magnitude. The inference is structurally plausible, not mathematically proven.

---

## (c) Caveats and Unverified Items

1. **The Microstructure Lab Substack resilience article: PAYWALLED.** The article "Order Book Resilience: How Fast Does the Book Recover After a Sweep?" (themicrostructurelab.substack.com) analyzed 180,590 sweep events with 100ms resolution. From publicly visible text: spread/depth reverts within 5–10 seconds, limit-order intensity takes ~30 minutes to recover. If verified, these timing numbers would provide a quantitative basis for a "delayed entry after OBI peak" tweak (enter 10–30 seconds AFTER the imbalance peak, not at the peak). Not available — cannot verify. Noted as a lead for future sessions if access is obtained.

2. **arXiv 2602.00776 exchange/timeframe not confirmed.** The paper studies crypto markets but the specific exchanges and observation periods are not stated in the fetched HTML summary. The OFI concavity finding may not transfer identically to Phemex's order book microstructure, though cross-asset stability is one of the paper's explicit claims.

3. **arXiv q-fin.TR October 2026:** Not re-fetched tonight (confirmed empty Nights 81–83; three consecutive months). No change expected two days after last confirmation.

4. **SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption):** Remains UNVERIFIED (HTTP 403 confirmed Night 83). If accessible, this would provide direct crypto-perp evidence for a combined OFI+depth gate upgrade. Excluded until accessible.

---

## Summary

| Tweak | Description | Priority | Source Type | Status |
|-------|-------------|----------|-------------|--------|
| 75 | OBI upper-bound gate (band filter ≥0.25 and ≤0.70 instead of threshold-only ≥0.25) | Medium | Academic (crypto, SHAP/OFI study — taker context, maker inference) | NEW — VERIFIED |

**Unverified lead:**
| — | Post-sweep delayed entry gate (wait 10–30s after OBI peak for depth recovery) | TBD | Practitioner (Microstructure Lab Substack, paywalled) | UNVERIFIED |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite)
2. Tweak 75 — OBI upper-bound gate (independently deployable in shadow mode, no Tweak 47/65 dependency)
3. Tweak 74 — stale-gate per-cycle re-validation (medium-high)
4. Tweak 72 — funding-window gate (medium, timing-only, no new data)
5. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging (medium/low)
6. Tweak 71 — transient-order OBI filter (low)

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed. Tweak 75 is an adverse-selection *avoidance* measure at the extreme end of the OBI distribution — it trims the worst-risk entries without compensating for the underlying structural deficit.
