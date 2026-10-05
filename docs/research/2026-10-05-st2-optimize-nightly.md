# ST2.0 Execution Optimization — Night 82 (2026-10-05)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–71 across Nights 1–81. Academic literature (arXiv q-fin.TR) declared saturated Night 77; confirmed N78–81 (three consecutive months zero new submissions). Night 81 added Tweaks 70 (cancel-side asymmetry gate) and 71 (transient-order OBI filter, low priority). Undeployed #1 priority remains Tweaks 47/65 (queue rank + time-to-fill logging).

---

## (a) What's New vs. Prior Reports

**Prior coverage confirmed (not repeated):**
- Queue position effects (Tweaks 47/65 — #1 priority)
- OFI/OBI binary gates and continuous placement offset (Tweaks 57, 59, 64, 67)
- Spread gates, cancel-and-wait (Tweaks 60, 69), cancel-side asymmetry (70), transient-order filter (71)
- Hyperliquid DEX public-wallet adverse-selection paper (arXiv 2608.04373) — rejected N80 as CEX-inapplicable

**What is genuinely NEW tonight:**

1. **Ruan & Streltsov — perpetual funding cycle creates a U-shaped adverse-selection pattern** (new angle, not covered in any prior report). Prior reports covered queue position, OFI, OBI, and spread gates. The 8-hour funding cycle as a *timing gate* for passive entries has not appeared in Tweaks 1–71 or in the 2026-06-20 synthesis.

2. **arXiv 2606.15715 (Barone & Lillo, June 2026)** — Hyperliquid perp paper not in any prior report. Structural finding about adverse selection being amplified for passive sellers alongside large visible buyers. Limited Phemex applicability (DEX mechanism), but provides fresh framing for the extreme-OBI scenario.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 72 — Funding-Window Adverse-Selection Gate

**Source:** Ruan, Q. & Streltsov, A. (Cornell University, PhD candidates). "Perpetual Futures Contracts and Cryptocurrency Market Microstructure." Working paper summarized at Cornell SC Johnson College of Business, February 2025.
**Source URL:** https://business.cornell.edu/article/2025/02/perpetual-futures-contracts-and-cryptocurrency/
**Verification:** Cornell blog page directly fetched. Direct quote obtained.

**Verified claim (direct quote from Cornell summary):**
> "both trading activity and bid-ask spreads follow a U-shaped pattern within each cycle"

Context from multiple search results corroborating the paper's finding (not independently verified, labeled UNVERIFIED):
> "market makers respond to heightened adverse selection risk by widening quoted spreads... particularly during funding settlement hours" — search-result synthesis of the paper, UNVERIFIED (full paper not fetched)

**Mechanism:** In perpetual futures markets with 8-hour funding cycles (settlement at UTC 00:00, 08:00, 16:00), trading activity and spreads are lowest at mid-cycle and peak near settlement windows. Market makers widen spreads in anticipation of adverse selection risk around funding time — reflecting that informed traders position ahead of funding payments.

**Application to ST2.0:**
ST2.0 posts a passive sell expecting reversion. If adverse selection is structurally elevated near funding windows (as spreads/activity peak implies), ST2.0 entries placed within ~30–45 minutes of a settlement window are in a higher-adverse-selection regime regardless of instantaneous OBI or tape conditions.

**Proposed Tweak 72:** Pre-entry timing filter:
```python
import datetime

FUNDING_SETTLEMENT_UTC_HOURS = {0, 8, 16}  # Phemex standard 8-hour funding
FUNDING_BLOCK_WINDOW_MINUTES = 45           # configurable

def _is_near_funding_window(self) -> bool:
    now_utc = datetime.datetime.utcnow()
    mins_in_cycle = (now_utc.hour % 8) * 60 + now_utc.minute
    mins_to_settlement = (480 - mins_in_cycle) % 480  # minutes until next window
    return mins_to_settlement <= FUNDING_BLOCK_WINDOW_MINUTES

# In entry check: if self._is_near_funding_window(): skip entry, log reason="funding_window_block"
```

**Forward-test design:**
- Shadow mode: log `mins_to_funding_window` on every ST2.0 attempt (fill and miss).
- Analysis: compare post-fill adverse-selection bps by `mins_to_funding_window` bucket (0–30, 30–90, 90–180, 180–240). If adverse selection is measurably higher in the 0–45-min bucket, deploy as a hard gate.
- The 45-minute window is a starting hypothesis — calibrate from data.

**Priority:** Medium. Implementation is low-complexity (pure time arithmetic, no new LOB data required). Risk is reduced fill rate. The underlying finding is about SPOT market spreads (not perp maker fills directly) — see Caveats.

---

### Tweak 73 — Hyperliquid Structural Insight: Sustained Extreme OBI as Adverse-Selection Amplifier

**Source:** Barone, D. & Lillo, F. "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid." arXiv 2606.15715, June 2026.
**Source URL:** https://arxiv.org/abs/2606.15715
**Verification:** arXiv abstract page fetched (Night 82). Not in any prior report's rejected list.

**Verified claims (direct quotes from abstract):**
> "Hidden metaorders executed alongside already-visible same-direction TWAP flow incur higher permanent costs: adverse-selection costs shift toward non-announcers."
> "while active, displayed depth rises and the book tilts toward the absorbing side, the more so the larger the announced order."

**Structural insight for ST2.0:** When a large visible directional buyer is actively sweeping the book, passive sellers who are NOT the announced order are the "non-announcers" and bear disproportionate adverse selection. On Phemex (CEX), there is no public TWAP announcement mechanism — the Hyperliquid DEX mechanism does not translate directly. However, the structural analog exists: if the OBI reading that fires ST2.0 is sustained at extreme levels (e.g., top 10% of the rolling distribution, not just above the ±0.25 gate), it may reflect a large aggressive buyer still actively in the book — exactly the scenario where non-announcing passive sellers face amplified costs.

**Proposed Tweak 73:** Log rolling OBI percentile rank at entry attempt (in addition to the raw imbalance snapshot):
```python
# Compute percentile rank of current ob.imbalance vs rolling 2h window
obi_pct = percentile_rank(ob.imbalance, self._obi_rolling_2h_buffer)
# Log: obi_pct alongside existing ob.imbalance
# Analysis question: do fills at obi_pct > 90th show worse post-fill adverse-selection than fills at obi_pct 50–75?
```

**Priority:** Low. This is a shadow-logging step only — no gate change until data exists. It builds on the existing OBI infrastructure and does not require deploying Tweak 47/65 first (though Tweak 47/65 data would enrich the analysis). Applicability to Phemex CEX is indirect — the Hyperliquid mechanism (public TWAP visibility) has no Phemex equivalent.

---

## (c) Caveats and Unverified Items

1. **Ruan & Streltsov full paper not fetched.** The primary finding (U-shaped pattern) was accessed via a Cornell Business blog summary, not the paper directly. The paper title, journal, dataset (which exchanges, which assets, what time period), and quantitative magnitude of the adverse-selection effect are NOT verified. The claim that the U-shaped pattern applies specifically to perpetual maker fills (vs. spot spreads) is an inference, not a verified direct quote. The blog explicitly says the authors study SPOT market microstructure effects of perp funding — not perp market maker adverse selection directly. The transfer to ST2.0's perp passive execution requires an additional assumption.

2. **Funding window block values are unverified hypotheses.** The 45-minute pre-settlement window and the {0, 8, 16} UTC settlement hours are consistent with Phemex's standard 8-hour funding schedule, but must be confirmed against Phemex's current funding schedule documentation. The block window size requires calibration from ST2.0's own data.

3. **arXiv 2606.15715 (Hyperliquid) full text not read.** Abstract fetched. The DEX-specific mechanism (public wallet addresses, visible TWAP programs) has no direct Phemex equivalent. The structural principle is portable; the magnitude and threshold numbers are not.

4. **Toxic Flow Segmentation (Microstructure Lab, Jan–Feb 2026):** paywalled — cannot verify claims about VPIN thresholds. Excluded from this report.

5. **LLMQuant "Why Your Perfect Limit Order Never Gets Filled" (Apr 2026):** paywalled — core claims not verifiable. Excluded.

6. **Academic literature saturation confirmed:** arXiv q-fin.TR October 2026 — not re-fetched tonight (confirmed empty Night 81). No new academic preprints added to the queue.

---

## Summary

| Tweak | Description | Priority | Source Type | Status |
|-------|-------------|----------|-------------|--------|
| 72 | Funding-window pre-entry gate (block 30–45 min before UTC 00/08/16) | Medium | Academic (Cornell blog, paper not fetched) | NEW |
| 73 | Rolling OBI percentile logging at entry attempt | Low | Academic (Hyperliquid DEX, indirect) | NEW |

**Undeployed priority stack:**
Tweaks 47/65 (queue rank proxy + time-to-fill logging) remain #1 — no change. Tonight's Tweak 72 is notable because it requires zero new LOB data and is independently testable in shadow mode without waiting for Tweak 47/65 deployment. It is the first timing-based gate in the stack.

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed by the literature. Tweak 72 is an adverse-selection *avoidance* measure (skip the high-risk time window), not a compensation for the structural deficit.
