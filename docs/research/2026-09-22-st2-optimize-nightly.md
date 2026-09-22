# ST2.0 Maker Execution — Nightly Optimization Research
**Night 70 | 2026-09-22 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–69)

Prior nights (last covered: N69, 2026-09-21) documented Tweaks 1–55 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth logging, queue rank logging, early posting
in absorption window, quarter-hour boundary blackout (Tweak 51), funding-state gate (Tweak 52),
seconds-to-quarter-hour logging (Tweak 53), OB imbalance regime audit (Tweak 54), and 1-second
adverse-selection baseline measurement (Tweak 55).

Tonight's sweep covered four new angles:
1. OFI reversal timing — when within a taker-driven buy episode to post the passive ask
2. OFI saturation / diminishing marginal impact at extremes as an entry-quality signal
3. Spread normality as a proxy for adverse-selection risk at entry
4. Tick-distance-from-mid vs fill probability tradeoff (exponential decay framework)

**What is genuinely NEW tonight:** Angles 1 and 2 yield confirmed primary-source findings from a
direct crypto-market paper (183 Binance pairs, 15-minute horizon) — closer to ST2.0's exact shape
than most prior corpus entries. Angle 3 is new as a formalized gate (crypto data). Angle 4
provides the theoretical framework for tick placement but no new gate beyond prior work.

---

## (b) Confirmed New Findings

### Finding A — Reversion Concentrates Only After Taker-Driven Up-Moves
**Source:** arXiv:2608.21888 — "Short-horizon mean reversion in cryptocurrency markets:
a matched cross-market measurement" (August 2026). 183 Binance pairs, 15-minute horizon.
**URL:** https://arxiv.org/abs/2608.21888
**Status:** FETCHED AND VERIFIED (HTML, August 2026) by sub-agent WebFetch.

**Verified quotes:**

> "reversal concentrates after moves driven by aggressive taker flow and grows with flow intensity"

> "A dose–response after flow-driven bars, a coin-flip after flow-opposed ones."

> "Next-bar reversal is indistinguishable after depth-consuming and depth-replenished moves:
> the pooled flip-rate difference is −0.002"

> "What conditions the reversal is the aggressive flow, not any hole it leaves in the book"

> "the signal decays monotonically and is gone by four hours: the profile of a microstructure
> effect with finite memory"

**Two implications for ST2.0:**

(1) The reversal edge exists only when the prior up-move was *taker-driven* (aggressive market
orders). If the up-move was passive/limit-flow-driven, the expected next-bar return is a coin-flip
with no edge. ST2.0 currently conditions on ob.imbalance (book state) and tape buy_ratio (flow
direction) but does not require confirmation that the observed pressure was executed aggressively
(i.e., a high aggressor_ratio / large-trade-dominated flow). Adding an **aggressor-ratio gate**
before posting would filter out the coin-flip subset.

(2) The depth consumed during the up-move — whether the ask side was thinned out or fully
replenished — has a pooled flip-rate difference of −0.002 with the reversion outcome. This is
effectively zero. Monitoring or gating on ask-side book depth recovery as a pre-entry condition
is not supported by this data and can be dropped as a candidate research direction.

**Caveat:** 183 Binance pairs, 15-minute candle horizon, backtest not restricted to maker entries
or passive fills. The aggressor ratio metric (% of volume from aggressive market orders) may not
be directly available in ST2.0's existing tape data; verify against ws_feed.py field availability.
The 5 bp gross edge number in the paper is for a directional taker strategy, not a passive maker —
maker capture of the reversion remains subject to the adverse-selection problem documented in the
June 2026 synthesis.

---

### Finding B — OFI Concavity at Extremes and Spread-State Adverse Selection
**Source:** arXiv:2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure"
(February 2026). Crypto exchange data.
**URL:** https://arxiv.org/abs/2602.00776
**Status:** FETCHED AND VERIFIED (HTML, February 2026) by sub-agent WebFetch.

**Verified quotes:**

> "order flow imbalance has a largely monotone effect with concavity at extremes (diminishing
> incremental impact as pressure accumulates)"

> "wider spreads associate with attenuated predictive effects and lower-confidence signals,
> in line with elevated adverse selection risk"

> "the strategy was repeatedly filled on its bid-side quotes, forcing it to accumulate a growing,
> and increasingly unprofitable, long position" [during flash crash — adverse fill example]

**Two implications for ST2.0:**

(1) OFI concavity at extremes means that when buy-side OFI is in the extreme saturating region,
the marginal new unit of buy flow has *decreasing* impact. This is precisely when the mean-reversion
thesis is most compelling — the buying force is exhausting itself. Posting the passive short-side
maker after OFI has reached an extreme (rather than on first-onset of buy pressure) means entering
when incremental adverse pressure per unit flow is lowest. Combined with Finding A (aggressor
ratio), the ideal entry window is: aggressor-dominated up-move that has produced extreme OFI.

(2) Wider spreads at entry correlate with higher adverse selection. A spread-normality gate —
suppress ST2.0 entry when the current spread is more than N× its rolling median — would filter
entries during stressed, high-adverse-selection regimes. The spread at entry is cheap to compute
from the L2 snapshot already captured in ST2.0.

**Caveat:** Paper is crypto-market but the specific exchange, pairs, and time window are not
quoted in the fetched excerpt. "Extreme OFI" threshold is not quantified in the fetched passages;
calibration against ST2.0's own OFI distribution would be needed. The flash crash result confirms
the structural adverse selection risk (documented in June 2026 synthesis) but does not add a new
actionable gate on its own.

---

### Supporting Finding — Exponential Fill Probability Decay with Tick Distance
**Source:** arXiv:2607.28323 — "Optimal Execution with Passive Market Impact" (July 2026).
NASDAQ equities and public FX.
**URL:** https://arxiv.org/abs/2607.28323
**Status:** FETCHED, abstract verified by sub-agent.

**Verified quotes:**

> "approximately exponential decay of limit-order fill probabilities with distance from the
> midprice"

> "fills arise from a sequence of quote adjustments that balance execution probability, adverse
> selection, and opportunity cost"

> "This generates a trade-off between higher fill intensity and larger accumulated impact on the
> one hand, and lower impact but greater non-execution risk on the other."

**Implication for ST2.0:** The exponential shape means the fill-rate/adverse-selection tradeoff
for tick placement is not linear — moving 1 tick behind best ask reduces fill probability much
more on the far side of the inflection point than at the inflection itself. This framework supports
the existing hypothesis (never deploy blind tick-distance changes without measuring the decay
constant on Phemex). It also frames cancel-repost as the *expected* optimal behavior, not noise:
the paper's optimal policy is continuous quote adjustment, not set-and-forget.

**Caveat:** Equity and FX data, not crypto perps. The decay constant is market-specific and
would need calibration from Phemex fill logs. No new deployment gate — this is theoretical
support for the existing tick-placement and cancel-repost research directions.

---

## (c) Forward-Testable Execution Tweaks

### Tweak 56 — Aggressor-Ratio Gate: Post Only After Taker-Driven Up-Moves
**Source:** arXiv:2608.21888 (verified, crypto data)
**Mechanism:** ST2.0 currently gates on ob.imbalance and tape.buy_ratio. These measure *that*
buying pressure exists but not *how* it was executed. Adding a threshold on the aggressor ratio
(fraction of prior-N-minutes volume from aggressive market orders) filters out the "coin-flip"
subset where the up-move was passive-flow-driven with no reversion edge.

**Implementation sketch:**
```python
# In ST2.0 signal evaluation, after existing tape gate:
aggressor_ratio = tape.large_trade_count / max(tape.total_trade_count, 1)
# or: fraction of prior-window volume tagged as taker/aggressive
if aggressor_ratio < AGGRESSOR_RATIO_MIN:  # e.g., 0.55
    log("st2_blocked: low aggressor ratio")
    return
```
**What to instrument first:** Log `aggressor_ratio_at_attempt` at every ST2.0 signal evaluation.
Check if `ws_feed.py` or `exchange.py` already tracks taker vs maker volume proportion. If not,
the buy_ratio field may be a partial proxy (high buy_ratio + high large_trade_bias may approximate
a taker-dominated up-move).

**What to measure after logging:** Post-fill outcome (win/loss) grouped by `aggressor_ratio_at_attempt`
quintile. Hypothesis: fills where aggressor_ratio < 0.50 should have near-50% WR; above 0.65 should
show measurable WR improvement.

**Caveat:** The aggressor-ratio field may not exist in current ws_feed.py; confirm before adding
gate logic. Do NOT deploy as a hard gate before 30+ logged attempts show the stratification.
Large_trade_bias may be a viable proxy in the interim.

**Priority:** High — this is the most directly motivated execution gate from a crypto-specific
paper (183 pairs, 15-min horizon = closest match to ST2.0's exact shape in the corpus).

---

### Tweak 57 — OFI Saturation Gate: Suppress Entry at Low/Moderate OFI, Accept Only at Extreme
**Source:** arXiv:2602.00776 (verified, crypto data)
**Mechanism:** The reversal edge grows with flow intensity (Finding A) and OFI concavity means
marginal pressure is lowest at OFI extremes (Finding B). Entries in the moderate-OFI regime are
lower-quality than entries at extreme OFI. A rolling-percentile OFI gate — only accept ST2.0
signal when OFI_current >= 80th percentile of its rolling 20-entry distribution — concentrates
entries in the highest-edge regime.

**Implementation sketch:**
```python
# Maintain rolling buffer of recent OFI readings
OFI_BUFFER.append(current_ofi)
if len(OFI_BUFFER) >= 20:
    ofi_pct = percentileofscore(OFI_BUFFER[-20:], current_ofi)
    log(f"st2_ofi_pct={ofi_pct:.1f}")
    if ofi_pct < OFI_PERCENTILE_MIN:  # e.g., 75
        log("st2_blocked: moderate OFI regime")
        return
```
**What to measure first:** Log `ofi_percentile_at_attempt` at every evaluation. Confirm current
OFI calculation and what buffer/field it reads from in bot.py / ws_feed.py. Stratify outcomes by
`ofi_percentile_at_attempt` quintile.

**Caveat:** OFI threshold (75th vs 80th vs 85th percentile) must be calibrated from Phemex data.
A too-strict gate (e.g., 90th percentile) may reduce trade frequency below statistical usefulness.
Instrument before deploying as a hard gate.

**Priority:** Medium — logically consistent with Finding A, supported by crypto data, but
threshold requires calibration.

---

### Tweak 58 — Spread-Normality Gate: Suppress Entry When Spread Is Elevated
**Source:** arXiv:2602.00776 (verified, crypto data)
**Mechanism:** Wider spreads at entry correlate with elevated adverse selection. When the bid-ask
spread is significantly above its rolling median (e.g., > 2× the 20-candle rolling median spread),
the adverse selection environment is degraded. Add a spread-normality gate alongside the existing
ob.imbalance gate.

**Implementation sketch:**
```python
# At ST2.0 entry check:
current_spread_pct = (ask - bid) / mid
rolling_median_spread = np.median(SPREAD_BUFFER[-20:])
SPREAD_BUFFER.append(current_spread_pct)
spread_ratio = current_spread_pct / rolling_median_spread
log(f"st2_spread_ratio={spread_ratio:.2f}")
if spread_ratio > SPREAD_RATIO_MAX:  # e.g., 2.0
    log("st2_blocked: elevated spread")
    return
```
**What to measure first:** `spread_pct_at_attempt` is already flagged in the undeployed
instrumentation stack (Tweak 45/48 from prior nights). Ensure this is being logged. Stratify
outcomes by `spread_pct_at_attempt` vs rolling median ratio.

**Caveat:** Spread normality threshold is pair-specific (BTC spread vs. small-cap alt spread
differ substantially). Use relative (ratio to rolling median) not absolute. Instrument-first rule
applies.

**Priority:** Medium — consistent with prior spread gate candidates (Tweaks 45, 48), now with
direct crypto-data support from arXiv:2602.00776. Reuses instrumentation already flagged.

---

## Priority Ordering (Undeployed Actions, Full Stack)

Unchanged high-priority instrumentation from prior nights (5 lines each, zero risk):
1. `time_to_fill` logging (N64) — 5 lines Python, unblocks all fill-quality analysis
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `queue_rank_at_fill` logging (Tweak 47) — 2–3 lines
5. `seconds_to_qh` logging (Tweak 53) — 1 line

New tonight — add to instrumentation batch:
6. `aggressor_ratio_at_attempt` logging (Tweak 56 prerequisite) — check ws_feed.py for existing field
7. `ofi_percentile_at_attempt` logging (Tweak 57 prerequisite)
8. `spread_ratio_at_attempt` logging (Tweak 58 prerequisite, partially overlaps item 2)

Then deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:2608.21888** — 183 Binance pairs, 15-minute horizon. The finding that depth consumed
   is not predictive of reversion (−0.002 flip-rate difference) is a single dataset. Binance
   linear perps ≠ Phemex. The aggressor ratio metric may require tape-level data not in current
   ST2.0 logs; verify in ws_feed.py before adding gate logic.

2. **arXiv:2602.00776** — "Explainable Patterns in Cryptocurrency Microstructure." The exchange
   and specific pairs are not quoted in the fetched passages. OFI threshold for "extreme/saturating
   region" is not numerically specified; requires Phemex-specific calibration. The spread-adversity
   finding is correlational, not causal — elevated spreads may proxy for regime (e.g., low-liquidity
   session) rather than being a direct causal input.

3. **arXiv:2607.28323** — Equity/FX data. The exponential fill probability decay shape is likely
   qualitatively correct for crypto perps but the decay constant is market-specific. No Phemex-
   specific calibration is possible without fill logs.

4. **arXiv:2408.03594** (OFI forecasting via Hawkes process) — NSE equity data, not crypto.
   Confirms bid-offer cross-dependence with a lag but provides no direct ST2.0 entry-timing
   guidance. Not included as a tweak candidate.

5. **Aggressor ratio availability:** Before deploying Tweak 56, grep ws_feed.py and bot.py for
   "taker", "aggressor", "large_trade", "buy_ratio" to confirm what fields are captured. The
   existing `large_trade_bias` field may function as a partial proxy.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| Candidates tonight | 3 (Tweaks 56, 57, 58) |
| Total candidates | 14 (45–58) |
| Conditional | 1 |

---

*Sources fetched and verified this session (via sub-agent WebFetch):
arXiv:2608.21888, arXiv:2602.00776, arXiv:2607.28323, arXiv:2408.03594.
All claims marked "verified" were read from fetched source text by the research sub-agent.
Claims from non-crypto or non-perp markets are labelled with their origin and treated as
conceptual reference only. No new tweaks are deploy-ready — instrument first.*
