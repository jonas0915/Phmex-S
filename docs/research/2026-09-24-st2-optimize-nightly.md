# ST2.0 Maker Execution — Nightly Optimization Research
**Night 72 | 2026-09-24 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–71)

Prior nights (last covered: N71, 2026-09-23) documented Tweaks 1–59 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth/rank logging, early posting in absorption
window, quarter-hour boundary blackout (Tweak 51), funding-state gate (Tweak 52),
seconds-to-quarter-hour logging (Tweak 53), OB imbalance regime audit (Tweak 54), 1-second
adverse-selection baseline (Tweak 55), aggressor-ratio gate (Tweak 56), OFI saturation gate
(Tweak 57), spread-normality gate (Tweak 58), and multi-level OFI depth concentration logging
(Tweak 59).

Tonight's sweep covered four angles:
1. VPIN / order-flow toxicity as a pre-entry passive maker suppression gate (crypto data)
2. Optimal cancel-and-repost MECHANICS for passive limits on perp futures (price-deviation trigger
   vs. the time-based cancel-and-wait in prior corpus)
3. Intraday microstructure patterns beyond the quarter-hour on crypto perps (Binance, 2021–2024)
4. Post-absorption ask-side queue recovery timing (LOB resiliency empirics)

**What is genuinely NEW tonight:**
- Angle 2 yields the most concrete finding: arXiv:2607.11888 (April 2026) directly addresses
  cancel-and-repost mechanics for perpetual futures and gives a price-deviation trigger framework
  not present in any prior night. Prior corpus covers cancel-and-wait conceptually but not the
  *when-to-cancel* mechanism in quantitative terms.
- Angle 1 yields a VPIN-as-suppression-gate hypothesis with a verified (abstract-level) crypto
  primary source. Prior corpus has not treated VPIN/toxicity as an entry-filter angle.
- Angle 4 adds LOB resiliency quantification (arXiv:1602.00731) — different paper from the N69
  Bechler & Scholtes 2017 entry (arXiv:1708.02715); corroborates but with a different data source
  and a specific entry-timing implication.
- Angle 3 is a useful **negative finding**: confirms the existing quarter-hour gate is sufficient;
  no additional intraday blackout is warranted.

---

## (b) Confirmed New Findings

### Finding A — Cancel-and-Repost Should Be Price-Deviation Triggered, Not Time-Based
**Source:** arXiv:2607.11888 — "Optimal Adaptive Market Making: A Theoretical Framework for
High-Yield Liquidity Provision in Perpetual Futures Markets," Minmin Zeng & Yi Liu (April 2026)
**URL:** https://arxiv.org/html/2607.11888
**Market:** Perpetual futures (theoretical framework, CEX-referenced pricing)
**Status:** FETCHED AND VERIFIED (HTML) by research sub-agent.

**Verified conceptual claims extracted from fetched HTML:**

1. The paper's core cancel trigger is price-deviation based: **cancel when the reference mid moves
   by θ price units in the adverse direction**, then repost at the updated level. This is NOT a
   time trigger — it is a market-state trigger.

2. The adverse selection cost from cancel latency scales as **σ√Δt** — convex in reaction time.
   Doubling your cancel-reaction time increases adverse selection by ~√2, not linearly. Faster
   cancel infrastructure has convex returns (each halving of reaction time cuts the latency cost
   more than the previous halving).

3. Setting a wider threshold θ is equivalent to tolerating a longer effective latency window. The
   paper expresses this as **Δt_eff(θ) ≈ θ²/σ²** — adverse-selection cost grows quadratically in
   θ and inversely with volatility. At higher volatility, tighter thresholds are required to hold
   the same adverse-selection budget.

4. Adverse selection decomposes into two components: the **informed-flow fraction π** (a
   Glosten-Milgrom-style toxicity term analogous to what VPIN measures) and a **cancel-latency
   cost** term. The optimal cancel threshold θ* jointly minimizes both. Treating π as a
   session-level gate and θ as the per-quote execution parameter is the natural two-layer
   implementation.

**Note on formula verbatim accuracy:** The HTML was processed by the fetch agent; the conceptual
structure (cancel-on-price-move, latency-cost convexity, θ²/σ² effective latency, informed-flow
decomposition) is consistent with standard microstructure theory. Treat specific formula notation
as extracted from the HTML rather than character-for-character verbatim from the typeset paper.

**What this means for ST2.0:**

The prior corpus (and prior cancel-and-wait tweaks) discusses *whether* to cancel but not *when*
to trigger the cancel. This paper gives the answer: watch the reference mid (Phemex mid or
cross-exchange mid), and cancel when it moves by θ ticks adverse to the posted ask. The threshold
θ should be tightened automatically in high-σ sessions (tighten during volatile sessions, loosen
during quiet tape) rather than being a fixed absolute value.

At ST2.0's $15 margin size and 1.2% SL, the adverse-budget before the position loses money is
~120 bps. The cancel trigger θ should be well inside that — a reasonable starting hypothesis is
θ = 10–20 bps adverse move from posting price triggers a cancel-and-repost.

**Not in prior corpus:** Prior nights cover the concept of canceling an unfilled order, but no
prior night has identified a *price-deviation trigger* derived from a crypto-perp-native
theoretical paper. This is the missing mechanistic piece for the cancel-and-repost research line.

---

### Finding B — VPIN Elevated Before Bitcoin Price Jumps (Suppression Gate Hypothesis)
**Source:** Kitvanitphasu, Kyaw, Likitapiwat & Treepongkaruna — "Bitcoin wild moves: Evidence
from order flow toxicity and price jumps," *Research in International Business and Finance*,
Vol. 81, 2026.
**DOI:** https://doi.org/10.1016/j.ribaf.2025.103163
**Market/Data:** High-frequency Bitcoin spot data. VAR modeling framework.
**Status:** VERIFIED from IDEAS/RePEC abstract page and ScienceDirect abstract.

**Verified quotes (from fetched abstract):**

> "VPIN significantly predicts future price jumps, with positive serial correlation observed in
> both VPIN and jump size, suggesting persistent asymmetric information and momentum effects."

> "Price jumps occasionally affect VPIN" — the relationship is bidirectional but asymmetric
> (VPIN predicts jumps more reliably than jumps predict VPIN).

The paper also identifies time-zone and day-of-week effects in VPIN.

**What this means for ST2.0:**

ST2.0 enters a bid-heavy book being aggressively bought, expecting the buying to exhaust and
revert. The precondition for the trade working is that the buying is *uninformed* flow (no
persistent adverse information driving price up). If VPIN is elevated at signal time, the
aggressive buying is more likely to be informed (directional information) and less likely to
revert — the premise of the signal inverts. This motivates using VPIN as a **suppression gate**
(skip entry when VPIN > regime threshold), not as a confirmation signal.

**Important caveat:** This is Bitcoin spot data, not perpetual futures. The funding-rate mechanics,
liquidation-cascade flow, and basis-arbitrage dynamics that are structural to perps are absent from
this dataset. VPIN computed on spot Bitcoin may not transfer directly to Phemex alt perps. Also,
the paywall blocked the specific VPIN thresholds and lead times from the main body of the paper —
the abstract confirms the predictive relationship but does not provide actionable threshold values.
This finding motivates instrumenting VPIN as a logging field first; the threshold must be
calibrated from Phemex data.

---

### Finding C — LOB Ask-Side Recovers in ~20 Order Updates (~5–10 sec) Post-Buy Sweep
**Source:** Xu, Chen, Xiong, Zhang, Zhou & Stanley — "Limit-order book resiliency after effective
market orders: Spread, depth and intensity" (2016)
**arXiv:** https://arxiv.org/abs/1602.00731
**Market/Data:** Chinese equity order book data.
**Status:** FETCHED AND VERIFIED (HTML) by research sub-agent.

**Verified quotes (from fetched HTML):**

> "the spread and depth can return to the sample average within 20 best limit updates"

> "The spread narrows gradually and relaxes to its normal level after about 20 incoming orders"

At spreads ≥ 2 ticks (more typical of crypto perps than equity 1-tick books):
> "the effective market orders produce symmetrical stimulus to limit orders"
> "the intensity curves of buy limit orders and sell limit orders basically overlap"

**What this means for ST2.0:**

At ≥2-tick spread (the expected state on a crypto alt perp after a buy sweep widens the book),
the ask side replenishes symmetrically and rapidly — approximately 20 incoming orders, which on
an active perp is on the order of 5–10 seconds. This means:

- A passive ask posted immediately after the signal confirms has a brief window (under ~10 seconds)
  to achieve a favorable queue position before the ask side is fully replenished.
- Any artificial delay in posting the passive ask (e.g., waiting for additional confirmation bars,
  processing latency, cycle overhead) means entering at back-of-queue once replenishment is
  complete.
- This motivates tight posting latency: once the signal fires, the order should be placed in the
  same cycle, not deferred.

**Relation to prior corpus:** This is a different paper from N69's arXiv:1708.02715 (Bechler &
Scholtes 2017, equity LOB resiliency). That paper documented ask-side collapse *above* 0.30
imbalance; this paper quantifies the recovery speed (~20 order updates) after a buy sweep. They
are complementary: 1708.02715 shows recovery fails at extreme imbalance; 1602.00731 shows it
is fast (~5–10s) at moderate imbalance. Together: post immediately (within one cycle), and avoid
entries at imbalance >0.30 (N69 Tweak 54).

**Caveat:** Chinese equity data, not crypto perps. The ~20-order recovery timescale is market-
and-instrument-specific. Crypto alt perps typically have thinner books and larger spreads; the
recovery may be faster or slower depending on the pair. Use as a qualitative ordering principle
(post promptly, don't delay), not as a precise second-count.

---

### Negative Finding D — No New Intraday Blackout Warranted Beyond Quarter-Hour Gate
**Source:** arXiv:2607.09426 — "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return
Predictability in Cryptocurrency Futures" (July 2026). Binance USDT-margined perp futures,
Jan 2021–Oct 2024.
**URL:** https://arxiv.org/html/2607.09426v1
**Status:** FETCHED AND VERIFIED by research sub-agent.

**Verified quote:**

> "the pattern is essentially unchanged when we exclude the three quarter-hours each day that
> coincide with funding settlement (00:00, 08:00, and 16:00 UTC)"

The paper documents one-hour and five-minute periodicity (activity peaks at the opening second
of each hour, secondary surge at H+30), but the agent confirmed these carry **no
return-predictive content** — only volume noise.

**Implication:** The existing Tweak 51 (quarter-hour blackout) is the correct and sufficient
time-of-day gate. Funding settlement times (00:00/08:00/16:00 UTC) are fully captured within
the quarter-hour gate. Hour-boundary volume bursts do not add directional adverse selection.
No new session-boundary or hour-boundary blackout is justified by the literature.

A separate MDPI paper (Zhivkov et al. 2026, 26 exchanges, 812 symbols, Nov 2025–Jan 2026)
found spread peaks approximately 2 hours after standard settlement times (02:00, 10:00, 18:00
UTC), but these represent wider bid-ask spreads (potentially favorable for a passive ask quoted
at the current best offer) rather than heightened adverse selection. Not a new blackout candidate.

---

## (c) Forward-Testable Execution Tweaks

### Tweak 60 — Price-Deviation Cancel-and-Repost Trigger
**Source:** arXiv:2607.11888 (verified, perp futures framework)
**Mechanism:** The current cancel logic (if any) is either passive (wait N seconds) or not
explicitly triggered by market-state. Replace or augment it with a price-deviation trigger:
cancel the resting passive ask when the reference mid (Phemex live mid) moves θ bps adverse
(i.e., bids lift further, reference mid rises) from the price at posting time.

**Implementation sketch:**
```python
# At ST2.0 order posting, record the mid at posting time:
st2_post_mid = (best_bid + best_ask) / 2
st2_post_price = ask_price  # the posted passive ask

# Each cycle while order rests unfilled:
current_mid = (best_bid + best_ask) / 2
adverse_move_bps = (current_mid - st2_post_mid) / st2_post_mid * 10000

if adverse_move_bps > ST2_CANCEL_THETA_BPS:  # e.g., 10–20 bps
    cancel_order()
    log(f"st2_cancel_price_deviation: theta={adverse_move_bps:.1f}bps")
    # Then repost at new ask level (or skip if imbalance has dissipated)
```

**Threshold calibration hypothesis:**
- Default starting point: θ = 10–15 bps (roughly 1/10 of the 120 bps SL budget)
- Tighten θ dynamically as realized σ rises: `θ_eff = θ_base / (current_vol_multiplier ** 0.5)`
  — this is the intuition from the σ√Δt scaling in arXiv:2607.11888
- After cancel, do NOT repost blindly: only repost if OFI and tape signals still pass current
  entry criteria. A cancel triggered by rising mid may indicate the absorption trade has failed.

**What to instrument first:** Log `adverse_move_bps_at_cancel` and `cancel_reason` at every
cancel event. Stratify outcome (would-have-filled vs. avoided-loss) vs. cancel threshold.

**Priority:** High — this fills the mechanistic gap in the cancel-and-wait research line. First
new perp-native theoretical framework in the corpus for cancel trigger mechanics.

---

### Tweak 61 — VPIN Suppression Gate: Skip Entry When Toxicity Elevated
**Source:** Kitvanitphasu et al. 2026, DOI:10.1016/j.ribaf.2025.103163 (verified, Bitcoin spot)
**Mechanism:** High VPIN = high probability of informed flow. If the aggressive buying at signal
time is informed (directional information) rather than uninformed (noise/momentum that will
revert), the ST2.0 premise is inverted. A rolling VPIN computed over the past N volume buckets
provides a toxicity pre-screen.

**Implementation sketch:**
```python
# VPIN approximation using signed volume buckets:
# 1. Divide recent trade volume into buckets of V trades each
# 2. For each bucket: buy_vol fraction approximates the CDF of price changes
# 3. VPIN = (1/n) * sum(|buy_fraction_i - 0.5| * 2) for n recent buckets
# Simplified: VPIN ≈ abs(tape.buy_ratio - 0.5) * 2 over a rolling volume window

rolling_vpin = abs(tape.buy_ratio - 0.5) * 2  # simplified proxy
if rolling_vpin > VPIN_THRESHOLD:  # e.g., 0.5
    log(f"st2_blocked: elevated_vpin={rolling_vpin:.3f}")
    return
```

**Note:** The simplified proxy above uses the existing `tape.buy_ratio` field as a VPIN
approximation. True VPIN requires volume-bucketing of the raw trade stream; the simplified proxy
is a starting point for logging. The full implementation would use ws_feed.py trade data.

**What to measure first:** Log `vpin_at_attempt` at every ST2.0 evaluation. Stratify outcomes
(win/loss) by `vpin_at_attempt` quintile. Hypothesis: high VPIN (>0.5) entries should show lower
WR than low VPIN entries.

**Caveat:** The primary source is Bitcoin spot, not perps. The VPIN threshold must be calibrated
from Phemex data. Do NOT deploy as a hard gate before 30+ logged attempts show stratification.
The simplified buy_ratio proxy may be available now and is a zero-cost first logging step.

**Priority:** Medium — logically motivated, new angle not in corpus, but crypto-spot-only source
and no specific thresholds from the paper.

---

### Tweak 62 — Post-Signal Entry Within One Cycle (Prompt Posting)
**Source:** arXiv:1602.00731 (verified, Chinese equities)
**Mechanism:** Ask-side LOB depth recovers within ~20 order updates after a buy sweep (~5–10s on
active instruments). Any delay in placing the passive ask means entering after replenishment is
complete — at back-of-queue. The current bot runs on a 60-second cycle; if the signal fires
mid-cycle, the earliest post happens at the next cycle boundary (up to 60 seconds later).

**Implication:** The ~5–10 second recovery window cannot be exploited on a 60-second cycle. This
is a structural constraint: ST2.0 is already effectively entering at back-of-queue by construction
due to the cycle granularity. The tweak is not "post faster" (cycle time is fixed) but:
- Log `cycle_offset_at_entry` — how far into the cycle did the signal fire? Entries early in a
  60s cycle had more queue priority time than entries at the end of the cycle.
- Hypothesis: fills from early-cycle entries (first 10–15s of the cycle) may have better outcomes
  than late-cycle entries (last 10–15s), because the order was posted earlier in the replenishment
  window.

**What to instrument:** At every ST2.0 entry attempt, log `seconds_into_cycle` (time since last
bot.py loop restart). After 30+ attempts, stratify post-fill WR by `seconds_into_cycle` decile.

**Caveat:** Chinese equity data. The 5–10 second recovery is an approximation for an active
market; thin-book alt perps may be slower. The 60-second cycle constraint cannot be removed
without a broader architecture change. This is a logging-and-stratification tweak, not a
deployment gate.

**Priority:** Low-Medium — the cycle-offset logging is cheap (1–2 lines), but the structural
constraint (60s cycle) means exploiting a 5–10 second window may require re-architecting the
entry loop, which is out of scope.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:2607.11888 (Zeng & Liu 2026, perp futures cancel-and-repost):** The formula notation
   (σ√Δt latency cost, θ²/σ² effective latency) was extracted from the paper HTML by the research
   sub-agent and is consistent with standard microstructure theory, but was not character-for-
   character verified from the typeset paper. Treat conceptual structure as confirmed, specific
   formula notation as potentially paraphrased. The core claim (price-deviation trigger, not
   time-trigger) is directly stated in the fetched HTML.

2. **VPIN paper (Kitvanitphasu et al. 2026):** The paywall blocked the main body of the paper.
   Only the abstract was verified. No specific VPIN thresholds, bucket sizes, or lead times are
   confirmed. The abstract confirms the predictive relationship (VPIN → price jumps) but not the
   quantitative parameters needed to deploy a gate.

3. **arXiv:1602.00731 (Xu et al. 2016, Chinese equities):** 2016 equity data. "~20 order updates"
   is from a specific equity market with specific tick/depth characteristics. On a thin crypto
   alt perp, this number could be smaller (thinner book = faster percentage recovery) or larger
   (fewer orders arriving). Use as directional principle only.

4. **arXiv:2607.09426 (Quarter-hour effect, Binance perps):** This paper may be the source of
   the existing Tweak 51 if it was found in an earlier session (N68 report not available to
   confirm). The negative finding (no new blackout warranted) is independently useful regardless.

5. **Angle 2 negative:** No 2025–2026 paper was found providing specific VPIN thresholds or
   calibrated cancel-and-repost timing for crypto alt perp passive execution. arXiv:2607.11888
   is the closest primary source and is perp-futures-native, but is theoretical rather than
   empirical.

---

## Priority Ordering (Undeployed Actions, Full Stack)

Unchanged high-priority instrumentation (5 lines each, zero risk):
1. `time_to_fill` logging (N64) — 5 lines Python, unblocks all fill-quality analysis
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `queue_rank_at_fill` logging (Tweak 47) — 2–3 lines
5. `seconds_to_qh` logging (Tweak 53) — 1 line
6. `aggressor_ratio_at_attempt` logging (Tweak 56 prerequisite)
7. `ofi_percentile_at_attempt` logging (Tweak 57 prerequisite)
8. `spread_ratio_at_attempt` logging (Tweak 58 prerequisite)
9. `st2_ofi_depth_ratio` logging (Tweak 59 prerequisite)

New tonight:
10. `adverse_move_bps_at_cancel` + `cancel_reason` logging (Tweak 60 prerequisite)
11. `vpin_proxy_at_attempt` logging using existing buy_ratio (Tweak 61 prerequisite, 1 line)
12. `seconds_into_cycle` logging at entry (Tweak 62 prerequisite, 1 line)

Then deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| New candidates tonight | 3 (Tweaks 60, 61, 62) |
| Total candidates | 18 (45–62) |
| Negative findings | +1 (no new intraday blackout) |
| Conditional | 1 |

---

*Sources fetched and verified this session:*
- *arXiv:2607.11888 (Zeng & Liu 2026, perp futures cancel-on-move framework, HTML verified)*
- *DOI:10.1016/j.ribaf.2025.103163 (Kitvanitphasu et al. 2026, VPIN Bitcoin spot, abstract verified)*
- *arXiv:1602.00731 (Xu et al. 2016, LOB resiliency, HTML verified)*
- *arXiv:2607.09426 (Quarter-hour effect, Binance perps 2021–2024, HTML verified)*
- *Rejected/not-new: arXiv:2609.18019, arXiv:2607.28323, arXiv:2602.00776 (all prior corpus)*
- *Formula notation from arXiv:2607.11888 extracted from HTML — treat as conceptual reference,
  not verbatim typeset.*
