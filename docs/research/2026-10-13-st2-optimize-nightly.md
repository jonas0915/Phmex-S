# ST2.0 Execution Optimization — Night 87 (2026-10-13)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–77 across Nights 1–86. Night 86 (2026-10-12): Tweak 77 (σ-adaptive cancel threshold, arXiv 2607.11888 Prop. 3.7). Night 85: Tweak 76 (realized-vol pre-entry gate). Night 84: Tweak 75 (OBI upper-bound gate). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Papers re-surfaced and confirmed already in corpus (not repeated):**
- arXiv 2407.16527 (DeLise, "Negative Drift of a Limit Order Fill") — in corpus since Night 29; confirmed inapplicable (US Treasury futures, no new mitigation playbook). Rejected again tonight.
- arXiv 2512.05734 (KANFormer, Zhong et al.) — in corpus since Night 53 (Sept 4); rejected (CAC 40 equity futures, ML-only, no new actionable output beyond "queue position matters").
- arXiv 2609.18019 (Maciejewski, "Model-Free Passive Execution via Order-Level Shadowing") — in corpus since Night 77 (Sept 21); used as basis for Tweak 69 (queue-depletion cancel proxy).
- VPIN-based pre-entry gate concept — in corpus since Night 3; declared "no primary-source threshold verified for crypto perps" in Night 33.

**What is genuinely NEW tonight:**

**Hackernoon practitioner article — "Designing a Market Maker Circuit Breaker for Toxic Order Flow"**

**URL:** https://hackernoon.com/designing-a-market-maker-circuit-breaker-for-toxic-order-flow

**Verification:** Full article fetched tonight. Author proposes a reactive microstructure-based circuit breaker for crypto maker quoting. The article is a practitioner blog post, NOT peer-reviewed. No primary academic citations for specific threshold values. Included as a practitioner example of a design pattern, not as a primary source.

**Direct quotes from the fetched article:**

> "The practical defence isn't forecasting the move. It's pulling or widening quotes within milliseconds of order flow turning toxic, then restoring them once conditions normalise."

> "Hysteresis. Without it, a reading oscillating near the trip level would cancel and re-post quotes on every tick."

> "PCTL_TRIP / PCTL_REARM: 0.90 / 0.80"

The **hysteresis band pattern** — a separate "trip" threshold (activates the gate) and "rearm" threshold (deactivates the gate) — is the structural concept that is new to this series. A grep across all 87 prior nightly reports confirms the word "hysteresis" has never appeared in the stack (zero matches). The prior 77 tweaks, including all gate-based tweaks (OBI, vol, tape, OBI upper-bound), use single-threshold logic: condition > X → block; condition < X → allow. This creates a binary flip around the threshold value, which can cause rapid entry/block oscillation when conditions hover near the threshold.

This is a standard **control-theory engineering pattern** (Schmitt trigger / dead-band logic) applied to maker gate management. The concept does not require an academic primary source — it is a well-established feedback control technique. The Hackernoon article demonstrates its application to crypto maker quoting.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 78 — Gate Hysteresis: Add Trip/Rearm Dead-Band to Volatility Gate (Tweak 76) and OBI Upper-Bound Gate (Tweak 75)

**Source:** Hackernoon practitioner article ("Designing a Market Maker Circuit Breaker for Toxic Order Flow"). URL: https://hackernoon.com/designing-a-market-maker-circuit-breaker-for-toxic-order-flow. Fetched tonight — direct quotes obtained. PRACTITIONER SOURCE — specific threshold values (PCTL_TRIP=0.90, PCTL_REARM=0.80) are not backed by primary academic research.

**Underlying engineering concept:** Hysteresis / Schmitt trigger / dead-band logic (standard control theory, not requiring a citation).

**Why this is structurally new vs. existing tweaks:**

All 77 prior tweaks that involve a gate use single-threshold logic:
- Tweak 75 (OBI upper-bound): block if |OBI| > 0.70, allow if |OBI| ≤ 0.70 → flip at exactly 0.70
- Tweak 76 (vol gate): block if σ_pct > 85th, allow if σ_pct ≤ 85th → flip at exactly the 85th percentile
- Tweak 72 (funding-window): block/allow at a specific funding proximity threshold → binary flip
- Existing OBI lower-bound gate: enter if |OBI| ≥ 0.25, skip if |OBI| < 0.25 → binary flip at 0.25

Single-threshold gates cause **oscillation** when the measured value (OBI, σ percentile, etc.) is hovering near the threshold. In a 60-second cycle bot:
- Cycle N: σ_pct = 84.9% → gate open → signal evaluated
- Cycle N+1: σ_pct = 85.1% → gate closed → signal blocked
- Cycle N+2: σ_pct = 84.7% → gate open → signal evaluated again

This wastes signal evaluations and can produce inconsistent behavior at the threshold boundary. Hysteresis adds a dead-band:

```
TRIP threshold (opens/activates the gate block): e.g., σ_pct > 87th → GATE BLOCKED
REARM threshold (closes/deactivates the gate block): σ_pct < 80th → GATE OPEN

STATE MACHINE:
  GATE_OPEN:
    - if σ_pct > TRIP → transition to GATE_BLOCKED, log reason="vol_gate_trip"
    - otherwise → remain GATE_OPEN
  
  GATE_BLOCKED:
    - if σ_pct < REARM → transition to GATE_OPEN, log reason="vol_gate_rearm"
    - otherwise → remain GATE_BLOCKED
```

The 7-percentile dead-band (87th → 80th) means conditions must improve meaningfully before re-entry is allowed, not just tick back below the original threshold.

**Proposed Tweak 78 implementation:**

```python
# Hysteresis state per symbol (persistent across cycles)
_vol_gate_state: dict[str, str] = {}  # "open" or "blocked", per symbol

# Thresholds (starting hypotheses; require empirical calibration)
VOL_GATE_TRIP_PERCENTILE = 87       # block entries when vol exceeds this
VOL_GATE_REARM_PERCENTILE = 78      # allow entries again once vol drops below this
OBI_UPPER_TRIP = 0.72               # block entries when OBI exceeds this (upgrade to Tweak 75)
OBI_UPPER_REARM = 0.62              # allow entries once OBI drops below this

def _st2_vol_gate_hysteresis(self, symbol: str) -> bool:
    """
    Returns True (gate open → allow entry) or False (gate blocked → skip entry).
    Uses trip/rearm hysteresis to prevent oscillation near the threshold.
    Replaces the single-threshold Tweak 76 gate.
    """
    state = self._vol_gate_state.get(symbol, "open")
    vol_pct = self._vol_percentile_rank(symbol)
    if vol_pct is None:
        return True  # insufficient data → allow; log as vol_gate_unknown

    if state == "open" and vol_pct > VOL_GATE_TRIP_PERCENTILE:
        self._vol_gate_state[symbol] = "blocked"
        self._log(f"vol_gate_trip symbol={symbol} vol_pct={vol_pct:.1f}")
        return False
    elif state == "blocked" and vol_pct < VOL_GATE_REARM_PERCENTILE:
        self._vol_gate_state[symbol] = "open"
        self._log(f"vol_gate_rearm symbol={symbol} vol_pct={vol_pct:.1f}")
        return True
    
    # No state transition — return current state
    return state == "open"

# Apply analogously to OBI upper-bound gate (Tweak 75 upgrade):
def _st2_obi_upper_gate_hysteresis(self, obi: float, symbol: str) -> bool:
    """Returns True (allow entry) if OBI is below the upper cap with hysteresis."""
    state = self._obi_upper_gate_state.get(symbol, "open")
    abs_obi = abs(obi)
    if state == "open" and abs_obi > OBI_UPPER_TRIP:
        self._obi_upper_gate_state[symbol] = "blocked"
        return False
    elif state == "blocked" and abs_obi < OBI_UPPER_REARM:
        self._obi_upper_gate_state[symbol] = "open"
        return True
    return state == "open"
```

**Why this matters specifically for ST2.0:**

ST2.0 has a 60-second cycle. At typical crypto perp volatility levels, σ percentile can oscillate several percentage points per cycle. With single-threshold gating (Tweak 76's 85th percentile), the gate activates/deactivates repeatedly during borderline high-vol periods, creating inconsistent protection. With a 78th–87th hysteresis band, the gate becomes sticky: once triggered by genuinely high vol, it stays blocked until conditions clearly normalize, giving the vol gate its intended protective effect.

The same logic applies to the OBI upper-bound gate (Tweak 75): OBI of 0.68–0.72 can oscillate in active books, causing the gate to flicker at the 0.70 boundary. The hysteresis band (trip=0.72, rearm=0.62) prevents this.

**Forward-test design:**

Shadow mode (no execution change): log `vol_gate_state`, `vol_pct_at_entry`, and `gate_transitions` per cycle.
- Compare single-threshold behavior (N gate transitions) vs. hysteresis behavior (expected significantly fewer transitions)
- Primary hypothesis: hysteresis reduces gate transitions by ≥60% during volatile sessions without meaningfully reducing total entry opportunities
- Secondary hypothesis: entries immediately following a vol_gate_rearm event (first cycle back after blocked period) have better adverse-selection bps than single-threshold entries that slipped through at the 84–86th percentile range

**Implementation complexity:** Low. The state machine is 8 lines of logic. State is per-symbol (dict), persists within a session but resets to "open" on restart (conservative default). No new data feeds — reuses Tweak 76's `_vol_percentile_rank()` output.

**Implementation dependency:** Requires Tweak 76 to be deployed first (provides the `_vol_percentile_rank()` helper). Tweak 78 is an upgrade to Tweak 76's single-threshold logic. For Tweak 75 (OBI upper-bound), the OBI hysteresis is independently deployable.

**Priority:** Low-to-medium. This is an engineering refinement to existing gates (Tweaks 75 and 76), not a new gate concept. Its value materializes only once Tweaks 75 and 76 are deployed and observable oscillation at the threshold is confirmed. Deploy as part of the same changeset as Tweaks 75 and 76 to avoid shipping single-threshold gates that then need immediate follow-up.

---

## (c) Caveats and Unverified Items

1. **Hackernoon article (circuit breaker for toxic order flow): PRACTITIONER SOURCE, NOT PEER-REVIEWED.** The specific trip/rearm values in the article (PCTL_TRIP=0.90, PCTL_REARM=0.80) are practitioner-asserted with no primary academic backing. The Tweak 78 thresholds above (87/78 for vol, 0.72/0.62 for OBI) are independent starting hypotheses calibrated to the existing gate values — they are NOT taken directly from the article. The article serves as a practitioner illustration of the hysteresis pattern, not as the empirical source for the specific numbers.

2. **Hysteresis concept itself (control theory):** The trip/rearm dead-band is standard feedback control engineering (Schmitt trigger). It requires no academic citation but also no quantification is provided for the optimal dead-band width in a 60-second crypto perp bot. The 9-percentile vol dead-band and 0.10 OBI dead-band proposed above are starting hypotheses requiring empirical calibration.

3. **State reset on bot restart:** The `_vol_gate_state` resets to "open" on restart. If the bot restarts during a blocked period (high vol), the first cycle post-restart will evaluate the entry condition as if state were "open," potentially allowing an entry the gate was protecting against. Mitigation: log vol_pct at startup to detect if immediate trip should be re-applied. This is a minor edge case but worth noting for implementation.

4. **Interaction with per-pair cooldown (10 min):** The existing cooldown already provides some temporal protection against rapid re-entry after a loss. The vol gate hysteresis adds protection against high-vol entry oscillation independent of loss outcome. The two mechanisms are complementary, not redundant.

5. **Academic literature saturation confirmed tonight:** arXiv q-fin.TR October 2026 sweep yielded no new papers. Papers returned in all searches (arXiv 2407.16527, 2512.05734, 2609.18019) are confirmed prior corpus. No new primary-source academic papers found tonight.

6. **SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): Still UNVERIFIED.** HTTP 403 persists. Not re-attempted tonight.

7. **Microstructure Lab Substack (post-sweep delayed entry): Still PAYWALLED.** Not re-attempted.

8. **arXiv 2607.11888 equation 30 (full θ* optimizer): Still PARTIALLY FETCHED.** The structural result (Tweak 77) is verified; the exact θ* expression depends on equation 30, which remains uncaptured.

---

## Summary

| Tweak | Description | Priority | Source | Status |
|-------|-------------|----------|--------|--------|
| 78 | Gate hysteresis: replace single-threshold vol gate (Tweak 76) and OBI upper-bound gate (Tweak 75) with trip/rearm dead-band state machines, preventing oscillation at threshold boundaries | Low-medium | Practitioner pattern (Hackernoon circuit-breaker article, fetched tonight) + standard control theory | NEW — VERIFIED (concept); thresholds are hypothesis-only |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry timing (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | Academic | PARTIALLY FETCHED |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite for bps analysis)
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold (shares vol buffer with Tweak 76)
5. Tweak 78 — Gate hysteresis upgrade (ship as part of same changeset as Tweaks 75+76) ← NEW
6. Tweak 74 — stale-gate per-cycle re-validation
7. Tweak 72 — funding-window gate
8. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging

**Structural situation unchanged:** Binding constraint (no speed, no queue position, no rebate) remains unaddressed. Tweak 78 is an engineering quality-of-life improvement to existing gates — it prevents threshold oscillation but does not change the fundamental adverse-selection economics.
