# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-07-07
**Night:** 11 of series
**Status:** Two new findings — one peer-reviewed (tangential), one practitioner (unverified thresholds). Literature confirmed thin at this depth.

---

## Context

Prior reports (06-20 synthesis through 07-06, nights 1–10) declared the academic literature
"genuinely exhausted" after night 9 and confirmed again after night 10. Tonight's sweep targeted
four angles not yet covered in any prior report: (a) imbalance persistence / meta-order duration
as an adverse-selection amplifier, (b) intraday realized volatility as a real-time entry gate,
(c) volatility-normalized tick size as a per-symbol passive execution diagnostic, (d) AI/RL
market maker adverse selection of institutional flow.

---

## (a) What's New vs. Prior Reports

| Angle | Prior Coverage | Tonight's Result |
|---|---|---|
| Imbalance persistence duration (how long has OFI been one-sided before signal) | Not in any prior report. OFI-flip (06-22) measures direction change; q_ratio (06-30) measures queue mass; tape gate measures buy_ratio — none measure the continuous duration of the current imbalance spell. | **New practitioner finding** — named explicitly as a meta-order signal; thresholds unverified from primary source. |
| Intraday realized volatility as real-time maker gate | F&G (daily) covered 06-29; funding-window (calendar) covered 06-22; VPIN (flow toxicity proxy) covered 06-23. Short-window RV as a real-time entry gate not covered. | No primary source found — search returned no relevant academic papers. |
| Volatility-normalized tick size per symbol | Not in any prior report. | **New finding** from peer-reviewed paper (Bouchaud et al., July 2026) — tangential applicability to reversion; useful as a symbol-ranking diagnostic. |
| RL agent detection of meta-order flow | Not in any prior report. | Tangential result only — RL agents profited by providing liquidity efficiently, not by adversely selecting TWAP. Not actionable for ST2.0. |
| SSRN 6344338 (gradient boosting for adverse selection prediction, Rajendran & Singaravelu) | Not in any prior report. | **HTTP 403** — inaccessible via WebFetch. Blocked twice tonight. |

---

## (b) New Forward-Testable Findings

### Tweak A: Imbalance Persistence Duration as a Meta-Order Proxy

**Source:** Coinmonks practitioner article, "Meta-Order Flow in Crypto Perps: Catching Big Whale,"
by Tigro Blanc.
**URL:** https://medium.com/coinmonks/meta-order-flow-in-crypto-perps-catching-big-whale-6a127e2f70e8
**Verification status:** Full article fetched directly. Practitioner blog — NOT peer-reviewed. Thresholds
labeled UNVERIFIED below. The underlying concept (sustained imbalance = institutional meta-order)
is grounded in standard meta-order flow theory (Almgren-Chriss, Gatheral square-root law) but the
specific numbers are this author's estimates, not from a primary study.

**What the article describes:**

Three features computed from L2 data to detect institutional meta-orders in crypto perps:
1. Volume imbalance: `(bid_vol − ask_vol) / (bid_vol + ask_vol)`
2. Arrival-rate z-score: current order intensity vs. rolling 5-minute baseline
3. Imbalance persistence: whether imbalance remains one-sided over a short window

The article states the detection trigger fires when BOTH conditions hold (thresholds UNVERIFIED):
- "Arrival-rate z-score > 1.5"
- "Absolute volume imbalance > 0.2"

**Key finding for passive makers (direct quote):**
> "passive orders do not fill uniformly; many fills occur in worse local states"

**Effective friction estimate (UNVERIFIED — author's calculation):**
> "effective one-way friction of about 0.56 bps" under realistic execution assumptions for passive
> orders when meta-order flow is active.

**Why this is NEW vs. prior reports:**

The existing queue captures OFI *level* (tape buy_ratio gate, ob.imbalance gate), OFI *direction
change* (OFI-flip concept, 06-22), and queue *mass ratio* (q_ratio, 06-30). None captures the
*temporal duration* of the current imbalance spell before signal time.

Meta-order flow theory predicts a distinction:
- **Transient absorption spike** (new, just started): imbalance high, duration short → may reverse
  quickly → ST2.0 signal premise holds
- **Sustained absorption** (ongoing for >30s): imbalance high AND duration long → likely
  institutional meta-order with many child orders still queued → price continues against the short
  → adverse fill

The hypothesis: longer `imbalance_duration_s` at signal time correlates with worse ST2.0 fill
outcomes. If confirmed, the skip gate would be: do NOT post when `imbalance_duration_s > threshold`
(e.g., >30–45s of continuous positive OFI).

**Forward-testable Tweak A (shadow log only):**

At each ST2.0 signal trigger, compute and log:
```python
# imbalance_duration_s: seconds since OFI was last negative or zero
# Requires tracking OFI sign at each 1s tick in ws_feed.py
imbalance_duration_s = time.time() - last_ofi_negative_ts
```
After 20+ fills, test: do fills with `imbalance_duration_s > 30` show worse adverse selection
(lower WR, larger adverse post-fill move in first 60s) than fills with `imbalance_duration_s < 15`?

**Infrastructure:** `ws_feed.py` already computes OFI per cycle. Add a `last_ofi_negative_ts` field
that resets whenever OFI sign flips to ≤ 0. Compute duration at signal time. ~5 lines.

**Important caveats:**
1. The source is a practitioner blog. The 0.56 bps friction estimate and the z-score / imbalance
   thresholds are the author's calibration, not from a peer-reviewed study. Treat as hypotheses.
2. ST2.0's tape gate (buy_ratio > 0.55) already partially captures "active buying." Imbalance
   duration adds the temporal dimension — but some correlation between them is expected.
3. The concept is for detecting meta-orders to avoid them. The actionable implication for ST2.0
   is the opposite: sustained imbalance → skip entry (or require even stricter confirmation).
4. Threshold calibration (30s? 45s?) must come from our own fill data, not from this article.

---

### Observation B: Volatility-Normalized Tick Size as a Per-Symbol Diagnostic

**Source:** Kurth, Eisler, Rej, Bouchaud (Capital Fund Management), "Is Trend Still Your Friend? A
Microstructural Account of the Demise of Short-Term Trend-Following," arXiv:2607.01550v1.
**URL:** https://arxiv.org/abs/2607.01550
**Date:** July 2, 2026 (3 days ago)
**Verification status:** VERIFIED — abstract and full summary fetched from arXiv.

**What the paper finds:**

The paper studies the collapse of short-term trend strategies post-2008 and identifies
"volatility-normalized tick size as the critical discriminant separating degraded from surviving
strategies."

**Direct quote:**
> "Short-term trend profits completely collapsed on small-tick contracts while remaining intact on
> large-tick ones."

Quantitative result: pre/post-break Sharpe ratios:
- Small-tick (high volatility-normalized): collapsed from ~0.8 to ~0 (~100% degradation)
- Large-tick (low volatility-normalized): remained ~1.0–1.2 (~0–30% degradation)

The structural mechanism: "HFT withdrawal eliminated residual depth [on small-tick books], forcing
trend followers to either walk the book aggressively or retreat entirely." On dense large-tick books,
"sufficient depth remained for continued execution."

**Applicability to ST2.0 (cautious):**

The paper is about trend-following, not reversion. The self-fulfilling trend loop mechanism does NOT
apply to ST2.0's counter-trend passive short.

However, the underlying book-depth finding transfers: symbols with a small volatility-normalized
tick size have thin books that sweep faster. For a passive seller, a faster-sweeping book means:
- The order reaches your limit price sooner after the imbalance event
- The cancel window (before the fill) is narrower
- The Lehalle & Mounjid latency constraint (06-30 report) bites harder

**Concrete per-symbol diagnostic:**

Compute: `vol_norm_tick[s] = tick_size[s] / (price[s] × hourly_realized_vol[s])`

Lower `vol_norm_tick` = smaller tick relative to price movement = faster-sweeping book = shorter
cancel window = more adverse fills expected from latency alone (independent of signal quality).

This provides a principled way to rank ST2.0's active symbols by passive execution hostility:
- If ETH has a higher `vol_norm_tick` than ENA, ETH's book sweeps more slowly relative to price
  moves → fills on ETH are less likely to be terminally adversely selected from pure latency
- This is consistent with our empirical observation (ETH ~59% fill rate, ENA ~20%) — though fill
  rate ≠ win rate, the hostility ranking may apply to both

**Not a gate (yet):** Log `vol_norm_tick` per symbol at signal time; test whether it correlates with
adverse post-fill drift after 30+ fills per symbol. Only then consider a per-symbol blocking rule.

**Important caveats:**
1. The paper's mechanism (trend self-fulfilling loop) does NOT apply to ST2.0. Only the structural
   book-depth implication transfers.
2. The paper studies equity futures. Crypto perps have different tick size conventions and
   microstructure. Direct quantitative transfer is an assumption.
3. "Small-tick" in the paper refers to contracts where the spread is near 1 tick, not small absolute
   tick size. Must verify which category each ST2.0 symbol falls into before using this diagnostic.
4. Computing hourly realized volatility requires ~60 1-min returns — feasible from existing candle
   data but adds a computation step.

---

## (c) Caveats and Things Not Verified Tonight

- **SSRN 6344338** (Rajendran & Singaravelu, "Predicting Adverse Selection in High-Frequency
  Cryptocurrency Markets Using Gradient Boosting"): HTTP 403 twice — abstract page AND delivery URL.
  The abstract description ("identifies rare seconds where passive quoting is most likely to be
  adversely selected") is the most directly actionable unread paper in the series after SSRN 6693260.
  Manual access required.

- **SSRN 6693260** (Chang 2026, "Do Order-Book States Predict Passive-Buy Toxicity?"): 11th
  consecutive night of 403. Permanently inaccessible via WebFetch.

- **Intraday realized volatility as a real-time gate:** Conceptually appealing (higher short-window
  RV = faster book sweep = worse cancel window) but no academic primary source found tonight. The
  VPIN metric already partially captures this (flow toxicity proxy), and the funding-window gate
  captures the calendar-correlated volatility pattern. A direct short-window RV gate would be novel
  but remains without a primary source.

- **Coinmonks article quantitative thresholds:** The z-score > 1.5 and |imbalance| > 0.2 thresholds
  for meta-order detection are the author's calibration estimates, not verified from a peer-reviewed
  study. Treat as starting-point hypotheses, not calibrated parameters.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | 06-24 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | 06-23, clarified 06-26 | Queued |
| 3 | Shadow-gate VPIN computation | 06-23 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | 06-26 | Queued |
| 5 | Log `fg_regime` (Fear & Greed index) at signal time | 06-29 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | 06-30 | Queued |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | 06-30 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | 07-06 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | 07-06 | Queued (shadow only) |
| **10** | **Log `imbalance_duration_s` (seconds of continuous positive OFI before signal)** | **07-07** | **Queued (shadow only; ~5 lines; practitioner-sourced hypothesis)** |
| **11** | **Log `vol_norm_tick` per symbol at signal time** | **07-07** | **Queued (diagnostic only; verify symbol classification before gating)** |

---

## Research Status

Eleven nights. Tonight yields two findings at the margin: (a) imbalance persistence duration
as a temporal meta-order detection signal (practitioner source, unverified thresholds), and
(b) volatility-normalized tick size as a per-symbol passive execution hostility diagnostic
(peer-reviewed, July 2026, tangential mechanism). Both are shadow-log additions, not gating changes.

The academic literature is exhausted. All remaining work is empirical: logging the 11-item queue
above against real fill outcomes over the next 2–3 weeks, then testing which metrics show
statistical separation between adverse and clean fills.

Two primary sources remain permanently inaccessible: SSRN 6344338 and SSRN 6693260. Manual
(institutional library) access is the only remaining path.
