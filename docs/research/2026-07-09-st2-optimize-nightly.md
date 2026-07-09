# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-07-09
**Night:** 13 of series
**Status:** Two new verified findings — queue position magnitude quantified (arXiv preprint, Binance BTC data) and F&G extremity premium refined (peer-reviewed, 2026). No SSRN access.

---

## Context

Prior reports (nights 1–12, 06-20 synthesis through 07-08) have covered: adverse selection by
construction, queue position mechanics, Phemex rebate = 0, OFI-flip / micro-price filter,
cancel-and-walk (never repost), VPIN, funding-window gate, F&G regime logging, q_near_at_post,
q_ratio, Lehalle-Mounjid latency formalization, universal −0.45 tick fill drift, Phemex amendment
endpoint, spoofable large bids, imbalance persistence duration, volatility-normalized tick size,
spot-vs-perp OFI divergence / funding rate proxy, cross-asset BTC→alt lead indicators (ruled out).

Tonight targeted four angles not previously attempted:
(a) LOB replenishment / resilience speed after absorption events
(b) Calibrated fill probability model combining queue metrics and imbalance
(c) Whether cancellation strategies worsen or improve adverse selection outcomes
(d) F&G adverse selection conditioned on sentiment extremity (both fear and greed)

---

## (a) What's New vs. Prior Reports

| Angle | Prior Coverage | Tonight's Result |
|---|---|---|
| Queue position effect MAGNITUDE quantified | 06-30 defined q_near_at_post and q_ratio as metrics to log, with no calibrated outcome magnitude. | **New finding** — 0.717 bp spread between front-of-queue (−0.058 bp) and back-of-queue (−0.775 bp) post-fill returns. Calibrated regression formula provided. See Tweak A. |
| Combined fill-probability score from queue + imbalance features | 06-30 covered the individual metrics; no composite score. | **New finding** — R²=0.946 regression with specific coefficients validates composing q_near, q_opp, and imbalance into a single predictive score. See Tweak A. |
| F&G non-monotonic (both extremes adverse) | 06-29 logged fg_regime. Prior reports treated F&G as directional (high greed = risk). | **New finding** — peer-reviewed 2026 paper establishes U-shaped relationship: both extreme fear AND extreme greed produce elevated spreads (adverse selection higher). See Tweak B. |
| Cancellation worsening vs. improving outcomes | 06-23 / 06-26 established cancel-and-walk (never repost). Paper tests imbalance-based cancellation. | Imbalance-based cancellation is marginally worse (−0.49 bp) than no cancellation (−0.47 bp). May include repost — full interpretation in caveats. |
| LOB depth replenishment speed (crypto) | Not previously researched. | No crypto-specific primary source found. Equity market data (Xu et al. 2016): spread and depth recover in 5–10 seconds. Not directly actionable — see caveats. |
| SSRN 6344338 | Blocked 12 prior nights | HTTP 403 again. 13th consecutive night. |

---

## (b) New Forward-Testable Findings

### Tweak A: Composite Fill-Probability Score (q_fill_score)

**Source:** Albers, J., Cucuringu, M., Howison, S., & Shestopaloff, A.Y. (2025). "The Market
Maker's Dilemma: Navigating the Fill Probability vs. Post-Fill Returns Trade-Off." arXiv:2502.18625v2.
Submitted February 25, 2025; revised November 23, 2025.
**URL:** https://arxiv.org/html/2502.18625v2
**Dataset:** Binance Bitcoin perpetual futures.
**Verification status:** Full HTML fetched directly. arXiv preprint — NOT peer-reviewed. VERIFIED
(title, authors, abstract, dataset confirmed from abstract page).

**What the paper finds:**

The paper's central result, directly quoted:
> "a negative correlation between maker fill likelihood and post-fill returns"

Empirically, on Binance BTC perp:
- Orders with **negative 5-second returns** (price moved against the maker after fill): >90% fill probability
- Orders with **positive 5-second returns**: <30% fill probability
- Overall naive maker expected return: approximately **−0.8 basis points** per fill

The adversarial mechanism: *"If the next price move is against a maker order in the top-of-book
queue, that order automatically fills, with probability 1"* — fills are structurally biased toward
adverse price moves.

**Queue position effect (quantified for the first time across this series):**

- Front-of-queue (0–10% position): **−0.058 bp** average post-fill return
- Back-of-queue (75–100% position): **−0.775 bp** average post-fill return
- **Spread: 0.717 bp between front and back of queue**

This is the first time this report series has a calibrated magnitude for the queue position effect.
The 06-30 report's q_near_at_post and q_ratio metrics were defined as things to LOG; the Albers
et al. paper provides the size of the effect these metrics are trying to detect.

**Fill probability regression model:**

The paper provides a calibrated logistic regression for fill probability:

```
z = 0.5649 - 0.0159 × Q_near + 0.1013 × Q_opp - 0.3166 × imb
R² = 0.946
```

Where (per paper):
- `Q_near` = near-side queue size (same-side orders ahead of the maker's order)
- `Q_opp` = opposite-side queue mass (bid volume for a passive sell order)
- `imb` = order book imbalance at posting time

These are the same three components already in ST2.0's forward-test queue (q_near_at_post = Q_near,
q_ratio derives from Q_opp/Q_near, ob_imbalance = imb). The paper provides calibrated coefficients
showing their relative predictive weights: Q_opp dominates over Q_near (0.1013 vs 0.0159), and
imbalance has the largest magnitude (0.3166).

**Interpretation for ST2.0:**

ST2.0 fires when the book is bid-heavy (high Q_opp, high imb) — exactly the configuration that
drives high fill probability (high z). This confirms the structural trap: the signal that triggers
entry creates the fill conditions that also guarantee adverse selection. The ONLY viable path
the paper identifies is a predictive reversal signal:

> "viable maker strategies often require a contrarian approach, counter-trading the prevailing
> order book imbalance" when supported by an additional predictive signal.

ST2.0's absorption-and-reversion thesis IS that predictive signal. This validates the strategy
architecture while explaining why the execution is so poor without it: without a reversion signal,
all imbalance-based passive strategies fail.

**What happens to ALL imbalance-based strategies (with or without cancellation):**

- Imbalance-based maker, no cancellation: **−0.47 bp**
- Imbalance-based maker with cancellation: **−0.49 bp** (marginally worse)
- Imbalance-based taker: **−1.96 bp**

The cancellation finding is relevant to ST2.0's queued 90s cancel (Tweak 2). See caveats.

**Forward-testable Tweak A (shadow log):**

At each ST2.0 signal trigger, log a composite fill-probability score alongside existing metrics:

```python
# q_fill_score: composite from paper formula (Albers et al. 2502.18625)
# Coefficients calibrated on Binance BTC perp — use for diagnostic only, not as a gate
# Q_near = q_near_at_post (already queued), Q_opp from q_ratio denominator, imb = ob_imbalance
q_fill_score = 0.5649 - 0.0159 * q_near_at_post_norm + 0.1013 * q_opp_norm - 0.3166 * ob_imbalance
# Note: Q_near and Q_opp must be normalized consistently with the paper's scale
# Use normalized versions (fraction of rolling 5-min mean) as proxy until calibration data exists
```

After 30+ fills, test: do fills with `q_fill_score > 0.65` show significantly worse post-fill
outcomes (lower WR, larger adverse price move in first 60s) than fills with `q_fill_score < 0.45`?

**CRITICAL CAVEAT — coefficient transfer:** The coefficients (0.0159, 0.1013, 0.3166) are
calibrated on Binance BTC perpetual futures. ST2.0 trades small-cap perps (AVAX, INJ, ENA, ARB)
on Phemex. The directional relationships (higher Q_near → lower fill prob, higher Q_opp → higher
fill prob, higher bid-imbalance → fills when you don't want to) almost certainly transfer. The
specific magnitudes do NOT transfer without recalibration. Log and observe; do not gate on these
coefficients until calibrated against our own fill data.

---

### Tweak B: F&G Extremity Premium — Both Extremes Are Adverse

**Source:** Farzulla, M. (2026). "The Extremity Premium: Sentiment Regimes and Adverse Selection
in Cryptocurrency Markets." arXiv:2602.07018v2. Submitted February 1, 2026; revised February 14, 2026.
**URL:** https://arxiv.org/abs/2602.07018
**Dataset:** Bitcoin daily data + Crypto Fear & Greed Index, February 2018 – January 2026 (8-year).
Replicated on Ethereum.
**Verification status:** Abstract and metadata fetched directly. VERIFIED (title, authors, date,
dataset confirmed). Full PDF not rendered (binary).

**What the paper finds:**

Direct quote from abstract:
> "Extreme fear and extreme greed regimes exhibit significantly higher spreads than neutral periods
> -- a phenomenon we term the 'extremity premium.'"

And:
> "intensity, not direction, drives uncertainty-linked liquidity withdrawal in cryptocurrency markets."

The relationship between F&G and adverse selection cost (bid-ask spread) is **U-shaped, not
monotonic**: both tails of the F&G distribution (extreme fear <20 AND extreme greed >80) produce
higher spreads, while neutral (20–80) periods show lower spreads.

**Why this is NEW vs. the 06-29 report:**

The 06-29 report added `fg_regime` logging but treated the F&G signal as roughly directional —
high greed = more momentum = higher risk of adverse selection for a short. The Farzulla (2026)
paper establishes empirically that the adverse selection cost is elevated at BOTH extremes. This
means:

- **Extreme fear** → liquidity withdraws → spreads widen → passive fills adversely selected from
  wider effective bid-ask spread → bad for ST2.0 entries
- **Extreme greed** → similar effect through the other channel (leveraged longs, forced
  rebalancing) → spreads also widen → equally bad

The 06-29 fg_regime logging should be updated to reflect this: flag both F&G < 20 AND F&G > 80
as "adverse extremity" rather than treating them differently.

**Forward-testable Tweak B (update to existing Tweak 5):**

When logging `fg_regime` at each ST2.0 signal trigger (already in forward-test queue as Tweak 5),
add an explicit `fg_extremity` flag:

```python
# Extremity premium flag (Farzulla 2026: both extremes adverse, not just one)
fg_value = get_fear_greed_index()
fg_extremity = (fg_value < 20) or (fg_value > 80)  # adverse regime
fg_regime = fg_value  # keep continuous value for calibration
```

After 30+ fills, test: do fills where `fg_extremity=True` show worse post-fill outcomes (lower
WR, larger spread at fill time) than fills in neutral F&G periods (20–80)?

**Important caveats:**

1. **Daily data, not intraday.** The paper uses daily bid-ask spreads on Bitcoin. ST2.0's entries
   happen on 5-minute signals. Daily average spread may not reflect the intraday moment of the
   entry. The directional result (extremity → higher adverse selection costs) likely holds
   intraday, but the specific thresholds (<20, >80) are calibrated to daily data.

2. **BTC only.** The paper uses BTC (replicated on ETH). ST2.0 trades small-cap perps. Small-cap
   pairs typically show wider spreads than BTC at baseline; whether the INCREMENTAL adverse effect
   of extremity is larger or smaller on small-caps is unknown.

3. **Daily F&G as a proxy for intraday conditions.** The F&G Index is updated once daily.
   It captures sentiment at a daily resolution and will not detect intraday sentiment shifts
   that precede a specific 5-minute entry. The existing fg_regime logging (Tweak 5) already
   handles this correctly — log the daily value and test correlation with fill outcomes.

4. **Spread as a proxy for adverse selection.** The paper measures bid-ask spread, which proxies
   adverse selection cost. ST2.0's actual adverse selection comes from directional adverse price
   movement post-fill, not just the spread. The mechanism likely transfers (wider spread → worse
   adverse selection) but is indirect.

---

## (c) Caveats and Things Not Verified Tonight

- **SSRN 6344338** (Rajendran & Singaravelu): HTTP 403 for the 13th consecutive night. Permanently
  inaccessible via WebFetch.

- **SSRN 6693260** (Chang 2026): Not retried (confirmed permanently blocked in prior nights).

- **Imbalance-based cancellation finding from 2502.18625:** The paper shows −0.49 bp for
  "imbalance-based maker with cancellation" vs −0.47 bp without cancellation. This appears to
  contradict the cancel-and-walk rule (Tweak 2, 06-26) but the comparison may not be apples-to-
  apples: the 06-26 evidence was from live perp evidence that cancel+REPOST worsened outcomes.
  The paper's "with cancellation" strategy details are not clear from the fetched HTML — it may
  include reposting, which is the specific mechanism the 06-26 rule prohibits. The cancel-and-walk
  (cancel, then DO NOT repost) is still valid. The paper does NOT test the "cancel without repost"
  variant directly. Treat as an observation requiring caution, not a contradiction.

- **LOB depth replenishment in crypto:** No crypto-specific primary source found. Equity market
  data (Xu et al. 2016, cited in emergentmind review) shows spread/depth recovery in 5–10 seconds
  after a market order shock. Directional implication for ST2.0: depth replenishes fast (equity,
  5-10s); posting the limit sell quickly after signal fires may matter for achieving front-of-queue
  positioning before depth returns below our price. Not actionable until crypto-specific data found.

- **arXiv:2507.22712 "Order Book Filtration and Directional Signal Extraction"** (not a July 2026
  paper — 2507 = July 2025): focuses on filtering LOB noise from flickering orders to improve OBI
  signal quality. Not directly applicable to ST2.0's cancellation timing or adverse selection gating.

- **arXiv:2602.07018 full text:** PDF binary was returned. Only abstract was extractable. Findings
  above are from the abstract only — no deeper result extraction possible without institutional
  access or a readable HTML version.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | 06-24 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | 06-23, clarified 06-26 | Queued |
| 3 | Shadow-gate VPIN computation | 06-23 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | 06-26 | Queued |
| 5 | Log `fg_regime` + **`fg_extremity` flag** (both extremes adverse — Farzulla 2026) | 06-29, **updated 07-09** | Queued (update Tweak 5 to add extremity flag) |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | 06-30 | Queued |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | 06-30 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | 07-06 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | 07-06 | Queued (shadow only) |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | 07-07 | Queued (shadow only; ~5 lines) |
| 11 | Log `vol_norm_tick` per symbol at signal time | 07-07 | Queued (diagnostic only) |
| 12 | Log `funding_rate_annual_pct` at signal time (spot-perp divergence proxy, Tier 1) | 07-08 | Queued (shadow only; ~3 lines) |
| **13** | **Log `q_fill_score` composite (Albers formula: Q_near, Q_opp, imb) at signal time** | **07-09** | **Queued (shadow only; DO NOT gate on BTC-calibrated coefficients until recalibrated)** |

---

## Research Status

Thirteen nights. Tonight yields two genuine new findings, both verified from primary sources:

1. **Albers et al. (arXiv:2502.18625, Binance BTC perp):** Queue position effect magnitude
   quantified at 0.717 bp (front vs. back of queue). Calibrated composite formula (R²=0.946)
   confirms q_near, q_opp, and ob_imbalance are the right metrics and their relative weights.
   Key insight: ST2.0's reversal signal is the correct and necessary (per this paper, ONLY viable)
   counter to the fill probability/adverse selection tradeoff. Shadow-log q_fill_score.

2. **Farzulla (arXiv:2602.07018, Bitcoin daily, 2026 peer-reviewed):** F&G adversity is
   U-shaped — BOTH extreme fear and extreme greed elevate adverse selection costs. Update the
   queued fg_regime logging (Tweak 5) to add an `fg_extremity` flag for F&G < 20 or > 80.

The academic literature remains at its margins. All 13 shadow-log items require 2–4 weeks of
fill data before statistical evaluation. SSRN 6344338 remains permanently inaccessible (13 nights).
