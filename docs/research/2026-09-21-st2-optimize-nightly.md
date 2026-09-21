# ST2.0 Maker Execution — Nightly Optimization Research
**Night 69 | 2026-09-21 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–68)

Prior nights (last covered: N68, 2026-09-09) documented Tweaks 1–53 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth logging, queue rank logging, early posting
in absorption window, quarter-hour boundary blackout (Tweak 51), funding-state gate (Tweak 52),
and seconds-to-quarter-hour logging (Tweak 53).

Tonight's sweep covered four new angles:
1. LOB replenishment dynamics after aggressive taker flow (new paper, 2017, not in prior corpus)
2. Passive vs aggressive execution slippage equivalence (new Sep 2026 paper, CME ES futures)
3. Nonlinear saturating impact — most recent lag dominates adverse selection (new Sep 2026)
4. Visible-vs-hidden flow and adverse selection shift on crypto perp LOBs (new 2026)

**What is genuinely NEW tonight:** Angles 1 and 2 yield confirmed primary-source findings directly
applicable to ST2.0 execution. Angle 3 corroborates prior corpus findings; no new actionable tweak
beyond confirming the 1-second mark-out window priority. Angle 4 is mechanistically interesting
but applies to large-metaorder execution (not our $15 passive limit) and is on a DEX (Hyperliquid).

---

## (b) Confirmed New Findings

### Finding A — LOB Ask-Side Replenishment Collapses Above ~0.30 Trade Imbalance
**Source:** arXiv:1708.02715 — Bechler & Scholtes, "Order Flows and Limit Order Book Resiliency
on the Meso-Scale"
**URL:** https://arxiv.org/pdf/1708.02715
**Data:** Equity LOB data; meso-scale defined by volume buckets of 10–100 market executions +
100–1,000 limit order events. Median bucket duration: ~150–170 seconds.

**Verified quotes (from agent WebFetch of the paper):**

> "the net limit order activity is stable on the passive side, while liquidity provision on the
> active side declines" (above imbalance ~0.3)

> "periods where market orders are accompanied primarily by limit order cancellations, creating
> a strong negative trend" (above-threshold regime)

**Below the threshold (~0.3 imbalance):** the book "bounces back through fresh posted volume" —
normal resilience in a ~150-second window.

**Above the threshold:** ask-side recovery fails on the normal ~2.5-minute timescale. This is
the LOB condition where a passive ask fills into persistent adverse flow rather than a
temporarily thin but recovering book.

**ST2.0 relevance:** The current OB imbalance gate is ±0.25. The paper identifies the regime
change between 0.25 and 0.30. Entries above 0.30 may be systematically entering the ask-collapse
regime; entries between 0.25 and 0.30 may still be in the recoverable regime. This gives the gate
an empirically motivated threshold to test.

**Caveat:** This is equity data, not crypto perps. The threshold and recovery timescale may differ
on Phemex. The meso-scale definition (150s) is close to ST2.0's ~15-minute hold horizon, so the
directional implication is relevant even if the exact number is not portable.

---

### Finding B — Unavoidable ~0.083 tick Adverse Selection at 1-Second Post-Fill
**Source:** arXiv:2609.18019 — "Model-Free Passive Execution via Order-Level Shadowing"
(September 2026). CME ES futures, full calendar year 2025, 9,000+ completed execution windows.
**URL:** https://arxiv.org/html/2609.18019
**Data:** CME ES front-month futures (equity index, not crypto, not perps).

**Verified quotes (from agent WebFetch):**

> "agreement to the fourth decimal on both, over more than nine thousand completed windows"
(passive vs aggressive slippage: +0.0955 vs +0.0952 ticks/contract)

> "the signature of adverse selection rather than of temporary impact"
(describing the +0.0825 tick 1-second post-fill mark)

> "A passive method without a directional forecast should execute slightly worse than the
> mid-price whatever else it knows"

**Key numbers:**
- Passive relative slippage: +0.0955 ± 0.0130 ticks/contract
- Aggressive relative slippage: +0.0952 ± 0.0135 ticks/contract (statistically identical)
- 1-second post-fill adverse selection: ~+0.0825 ticks (both passive and aggressive)
- Latency sensitivity: passive loses 0.011 ticks/ms; aggressive loses 0.042 ticks/ms (~4x more)

**ST2.0 relevance:** Two implications. (1) The ~0.083 tick adverse selection at 1-second is the
structural floor — this much adverse selection is unavoidable regardless of passive/aggressive
style. ST2.0's instrumentation (once deployed) should measure whether its 1-second mark-out
significantly exceeds this floor; if it does, it's exchange-specific adverse selection, not just
structural. (2) The 4x latency advantage of passive over aggressive confirms there is no benefit
to switching to aggressive/taker entries — the slippage is identical and Phemex charges a taker
fee.

**Caveat:** This is CME ES futures — liquid, large-tick, deep book. Not directly portable to
small-cap alt perps on Phemex. The ~0.083 tick figure should be treated as a conceptual baseline,
not a Phemex-specific number.

---

### Supporting Finding — Nonlinear Saturation of Impact (Confirms Prior Corpus)
**Source:** arXiv:2609.06085 — Naviglio & Lillo, "Explainable Deep Learning for Price-Trade
Dynamics" (September 2026). High-frequency equity data.
**URL:** https://arxiv.org/abs/2609.06085

**Verified claim (from agent WebFetch):**

> "Lagged signed volume generates sign-preserving and saturating effects, consistent with
> nonlinear price impact and order-flow persistence."

**Implication:** Adverse selection for a passive ask is nonlinear — the first burst of taker
buying carries the most risk; subsequent flow has diminishing marginal impact. This corroborates
N68 Tweak 51 (quarter-hour boundary blackout) and the existing "post early in absorption window"
direction from N66. No new tweak warranted; confirms the saturation-based timing logic.

---

## (c) Forward-Testable Execution Tweaks

### Tweak 54 — OB Imbalance Gate Threshold Audit Against Replenishment Regime Boundary
**Source:** arXiv:1708.02715 (verified)
**Mechanism:** The current gate passes entries where OB imbalance ≥ +0.25 (confirming bid-heavy
book). The LOB resiliency paper places the ask-side-collapse regime change at ~0.30, not 0.25.
Entries between 0.25 and 0.30 may still be in the normal-recovery regime; entries above 0.30
may be entering the ask-side-collapse regime where adverse fills dominate.

**Implementation sketch:** No gate change yet — instrument first. At every ST2.0 entry attempt,
log `ob_imbalance_at_entry`. After 30+ attempts, stratify post-fill outcomes by:
- Imbalance 0.25–0.30 (current gate passes; recoverable regime by paper's finding)
- Imbalance 0.30–0.40 (above regime boundary)
- Imbalance > 0.40 (deep adverse regime)

If adverse-fill rate is significantly higher above 0.30, tighten the gate to 0.30 (or test 0.30
as an upper bound rather than a lower bound — reject if imbalance is TOO high, suggesting
the recovery window has already collapsed).

**What to measure:** Post-fill 5-min markout vs `ob_imbalance_at_entry` decile.

**Caveat:** Equity data; threshold may not be 0.30 on Phemex. Do NOT tighten gate before data
confirms the effect. Log first.

**Priority:** Medium — builds on the existing `ob.imbalance` field now being logged since the
2026-06-19/20 fix. This is checkable from current logs already if that field is populated.

---

### Tweak 55 — 1-Second Post-Fill Mark-Out as Adverse Selection Baseline Target
**Source:** arXiv:2609.18019 (verified)
**Mechanism:** The structural, unavoidable adverse selection floor at 1-second post-fill is
~0.083 ticks. When ST2.0's `time_to_fill` logging (N64, undeployed) is added, also log the
1-second mark-out: record `mid_1s_after_fill` and compute `adverse_sel_1s = mid_1s_after_fill -
fill_price`. If ST2.0's `adverse_sel_1s` significantly exceeds ~0.083 ticks (converted to the
relevant pair's tick unit), that excess is exchange-specific adverse selection that instrumentation
changes could address (e.g., quarter-hour gate, funding gate, imbalance gate).

**Implementation sketch:** On the fill-confirmation path in `bot.py`, schedule a 1-second
delayed check:
```python
import asyncio
fill_price = ... # from fill confirmation
await asyncio.sleep(1)
mid_1s = (best_bid + best_ask) / 2  # from current L2
adverse_sel_1s = mid_1s - fill_price  # positive = adverse for a short entry
log(f"st2_adv_sel_1s={adverse_sel_1s:.5f}")
```
**What to measure:** Average `adverse_sel_1s` vs the theoretical floor. Also: is `adverse_sel_1s`
higher during above-0.30 imbalance (Tweak 54) or within 45s of quarter-hour (Tweak 51)?

**Caveat:** CME ES is not Phemex. The 0.083 ticks is a conceptual reference, not a hard Phemex
threshold. The L2 snapshot at +1s must use live data, not cached.

---

## Priority Ordering (Undeployed Actions, Full Stack)

The following remain the highest priority (unchanged from N68):

1. `time_to_fill` logging (N64) — 5 lines Python, zero risk
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `queue_rank_at_fill` logging (Tweak 47) — 2–3 lines
5. `seconds_to_qh` logging (Tweak 53, N68) — 1 line

New tonight:
6. `ob_imbalance_at_entry` logging / Tweak 54 audit — verify field is being captured; compute
   post-fill outcomes by imbalance decile
7. `adverse_sel_1s` logging (Tweak 55) — 5 lines on fill confirmation path

Then deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:1708.02715** — 2017 equity data. The 0.30 threshold and 150s recovery window are
   equity-market calibrated. Phemex perp recovery dynamics may differ substantially. Do NOT use
   0.30 as a hard gate without Phemex-specific calibration.

2. **arXiv:2609.18019** — CME ES futures. The 0.083 ticks adverse-selection floor is for a
   deep, institutional, large-tick market. Phemex alt perps are likely to have larger adverse
   selection costs at the same time horizon. Use as conceptual reference only.

3. **arXiv:2609.06085** (nonlinear saturation) — equity data, not crypto perps. The saturation
   finding is consistent with crypto microstructure intuition but not empirically confirmed on
   Phemex. Treated as supporting evidence, not a new deployment target.

4. **arXiv:2606.15715** (Hyperliquid visible vs hidden flow) — DEX (Hyperliquid) and applies to
   large metaorders, NOT small passive limits. Not actionable for $15 ST2.0 positions. Not
   included as a tweak candidate.

5. **Sub-agent verification:** All four papers were fetched and quoted by a sub-agent. Quotes and
   arXiv IDs are reported as verified from the fetch. This session did not independently re-fetch
   all sources; treat as Confirmed (sourced from WebFetch) with appropriate skepticism for precise
   numbers from non-crypto markets.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| Candidates tonight | 2 (Tweaks 54, 55) |
| Total candidates | 11 (45–55) |
| Conditional | 1 |

---

*Sources fetched and verified this session (via sub-agent WebFetch):
arXiv:1708.02715, arXiv:2609.18019, arXiv:2609.06085, arXiv:2606.15715.
All claims marked "verified" were read from fetched source text by the research sub-agent.
Precise numeric claims from non-crypto markets (CME ES, equities) are conceptual reference only.*
