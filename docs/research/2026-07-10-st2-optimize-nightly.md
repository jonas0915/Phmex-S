# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-07-10
**Night:** 14 of series
**Status:** One new verified finding (spread width at signal time, from a previously partially-mined paper). Literature remains exhausted. Four new primary sources surveyed — two inaccessible, two not applicable to one-shot passive limit orders.

---

## Context

Prior reports (nights 1–13, 06-20 synthesis through 07-09) have covered: adverse selection by
construction, queue position mechanics (quantified at 0.717 bp front-vs-back), Phemex rebate = 0,
OFI-flip / micro-price filter, cancel-and-walk (never repost), VPIN, funding-window gate, F&G
regime + extremity premium (U-shaped), q_near_at_post, q_ratio, Lehalle-Mounjid latency
formalization, universal −0.45 tick fill drift, Phemex amendment endpoint, spoofable large bids,
imbalance persistence duration, volatility-normalized tick size, spot-perp OFI divergence / funding
rate proxy, cross-asset BTC→alt lead indicators (ruled out), calibrated fill probability score
(Albers formula), LOB depth replenishment (equity-only), cancellation strategies (marginal
difference).

Tonight targeted four genuinely uncovered angles:
(a) Iceberg / hidden order detection — does the dominant bid being an iceberg change adverseselection risk for a resting passive short?
(b) Passive sell placement depth — optimal posting price (mid vs. best-ask vs. inside spread)
(c) Fill timing as an adverse selection predictor — do faster fills predict worse outcomes?
(d) Session / time-of-day adverse selection conditioned on maker performance in crypto perps

---

## (a) What's New vs. Prior Reports

| Angle | Prior Coverage | Tonight's Result |
|---|---|---|
| Spread width at signal time | Not in any prior report or forward-test queue. Vol-norm-tick (night 11) addresses relative tick size, not instantaneous spread. | **New finding** — Bieganowski (2026, Binance Futures, already-verified source) explicitly links wider-than-normal spread at signal time to elevated adverse selection and attenuated predictive signal. Log `spread_at_signal_bps`. See Tweak A. |
| Iceberg / hidden order detection | Not in any prior report. Spoofable large bids (night 10) addressed visible bids; icebergs are hidden volume. | **Inaccessible** — Wiley paper (Lajbcygier 2025) paywalled (HTTP 402). arxiv 1909.09495 (CME iceberg detection) is equity futures, 2019 — not transferable to crypto perps. No crypto-specific primary source found. |
| Passive sell placement depth (mid vs ask vs inside) | Cont & Kukanov (1210.1625, optimal limit/market split) cited in synthesis night 1. Prior reports note "post-offset variants" as a hypothesis but no placement-depth research was done. | **No new primary source.** The search returned Cont & Kukanov (already covered) and the Albers 2502.18625 formula (night 13). Neither addresses the choice between posting at mid, inside spread, or best-ask. The "3-6× higher fill rate inside spread" result found in passing cites Cont & Kukanov — already known. |
| Fill timing as adverse selection predictor | DeLise (arxiv 2407.16527, July 2024): "The Negative Drift of a Limit Order Fill." | Fetched abstract — confirms fills coincide with adverse price movements. Dataset is 10-Year US Treasury Bond futures; no quantitative fill-speed metrics in the abstract. This is the same structural phenomenon already documented in night 1 (Albers 2502.18625, Binance BTC perp). No new actionable content. |
| Session-based adverse selection for crypto perp passive makers | 06-22 funding-window gate covers settlement timing. Track A noted 0% WR for US daytime (n=7, not significant). | No academic primary source on crypto perp maker adverse selection stratified by trading session. Practitioner sources (Coinmonks March 2026, Amberdata) document session volatility patterns but do not measure adverse selection cost for makers per session. Not actionable. |
| Hyperliquid sunshine trading (June 2026) | Not in any prior report. | Barone & Lillo, arXiv:2606.15715, June 14, 2026. VERIFIED — full HTML fetched. **Not applicable** to ST2.0: paper studies large-scale TWAP metaorders (4.3M statistical metaorders, $1.93T volume) on Hyperliquid. The 55 bp / 99 bp adverse selection findings are for institutional multi-child executions spanning minutes, not one-shot $150 passive limit orders. |
| SSRN 6344338 (Rajendran & Singaravelu) | Blocked 13 consecutive nights | HTTP 403 again — 14th night. Permanently inaccessible via WebFetch. |

---

## (b) New Forward-Testable Finding

### Tweak A: Current Spread Width at Signal Time

**Source:** Bieganowski, B. & Ślepaczuk, R. (2026). "Explainable Patterns in Cryptocurrency
Microstructure." arXiv:2602.00776v1. January 31, 2026.
**URL:** https://arxiv.org/html/2602.00776v1
**Dataset:** Binance Futures perpetual contracts, January 1 2022 – October 12 2025 (1-second
frequency, multiple cryptocurrencies).
**Verification status:** VERIFIED — full HTML fetched directly in night 12 (arXiv, accessible).
This is a new extraction from a source confirmed accessible; the spread-width finding was NOT
extracted in night 12's report (which focused on the c=0.94 spot-OFI coupling result).

**What the paper establishes:**

Direct quote extracted from the paper's text:
> "wider spreads associate with attenuated predictive effects and lower-confidence signals, in line
> with elevated adverse selection risk"

This is documented in the context of order book signal quality across different spread regimes.
When the current bid-ask spread is wider than its rolling baseline, two things happen simultaneously:
(a) the predictive signal (order book imbalance, OFI) carries less information about future price
direction, and (b) adverse selection cost for a passive maker is higher because the effective cost
of being adversely selected (price moves through your fill price) is amplified.

**Why this is NEW vs. prior reports:**

Night 11 added `vol_norm_tick` (volatility-normalized tick size) as a per-symbol structural
diagnostic. That measures the long-run book depth hostility for a symbol. `spread_at_signal_bps`
measures the instantaneous spread at the specific moment of each signal trigger — a real-time
adverse selection cost indicator that changes tick-by-tick, not a per-symbol constant.

The forward-test queue has OFI level (ob.imbalance), OFI duration (imbalance_duration_s), queue
mass (q_near_at_post, q_ratio), volatility (vol_norm_tick), macro regime (fg_regime, fg_extremity),
spot-perp basis (funding_rate_annual_pct), and composite fill probability (q_fill_score). None of
these captures the instantaneous bid-ask spread at signal time.

**Implementation (trivial — ~2 lines):**

```python
# spread_at_signal_bps: current bid-ask spread at ST2.0 signal trigger
# ob.bids[0][0] and ob.asks[0][0] are already available in bot.py's OB snapshot
mid_price = (ob.bids[0][0] + ob.asks[0][0]) / 2
spread_at_signal_bps = (ob.asks[0][0] - ob.bids[0][0]) / mid_price * 10_000
# Log alongside existing signal fields
```

**Forward-testable hypothesis:** After 30+ fills, test: do fills where `spread_at_signal_bps` is
above the 30-day rolling median for that symbol show worse post-fill outcomes (lower WR, larger
adverse price move in first 60s) than fills with below-median spread? If confirmed, a spread-width
gate (skip entry when spread > e.g. 1.5× rolling median) reduces adverse fills.

**Why this metric is complementary to the existing queue:**

- `ob.imbalance` measures DIRECTION of book pressure
- `q_fill_score` measures fill PROBABILITY given queue/imbalance conditions
- `spread_at_signal_bps` measures the COST of being adversely selected (wider spread = larger
  post-fill price move needed to profit, and higher adverse selection risk per the Bieganowski
  finding)

Three dimensions: direction, probability, cost. The queue now covers all three.

**Important caveats:**

1. **Directionality of the quote.** "Wider spreads associate with attenuated predictive effects"
   was extracted via WebFetch from the paper's HTML. The exact section and statistical significance
   of this claim were not retrievable from the WebFetch output. Treat as verified directionally,
   not as a calibrated threshold. Do not gate on a specific spread multiple without our own data.

2. **Confounding with volatility.** Spread widens during high volatility. `vol_norm_tick` (Tweak
   11) already partially captures this. Expect correlation between `spread_at_signal_bps` and
   `vol_norm_tick` — both need to be logged to disentangle their independent effects.

3. **Symbol baseline varies.** HYPE, DOGE, and ARB have systematically wider spreads than ETH or
   BTC. The gate must use a per-symbol rolling median, not a cross-symbol absolute threshold.

4. **Spread at signal time vs spread during order resting.** The Bieganowski finding is about the
   spread AT entry. The spread while the order rests could widen further or narrow. Only the
   entry-time snapshot is proposed here.

---

## (c) Papers Surveyed Tonight (New vs. Prior Reports)

| Paper | Why Checked | Verdict |
|---|---|---|
| arXiv:2407.16527 (DeLise, July 2024) "The Negative Drift of a Limit Order Fill" | Fill timing / time-to-fill as adverse selection predictor | Dataset = 10-Year US Treasury Bond futures. Confirms structural adverse selection on passive fills — same finding as night 1 but on equity futures. No crypto relevance, no fill-speed metric extracted from abstract. NOT NEW. |
| arXiv:2606.15715 (Barone & Lillo, June 2026) "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid" | New June 2026 paper on crypto perp adverse selection | VERIFIED. Studies TWAP metaorders at institutional scale ($1.93T). Findings (55–99 bp) are not applicable to ST2.0's single $150 passive limit. Sunshine trading mechanism (public intent disclosure) is conceptually interesting but has no implementation path for a one-shot order. NOT APPLICABLE. |
| arXiv:2602.00776v1 (Bieganowski, 2026) — spread-width finding not extracted in night 12 | Partial re-read for session-based and spread-regime findings | **Yields Tweak A.** Spread width at signal time linked to elevated adverse selection. |
| Multicoin Capital "Adverse Selection Rules Everything Around Me" (Feb 2026) | Crypto practitioner, potential concrete insights | Opinion-driven, no systematic data. Mechanisms discussed (DFlow flow tagging, RPI) are DEX/AMM-specific, not applicable to Phemex centralized perp. NOT ACTIONABLE. |
| Wiley — Lajbcygier (2025) "Who Can See the Iceberg's Peak?" | Iceberg detection — new angle | HTTP 402 (paywalled). Inaccessible. |

---

## (d) Honest Assessment

Tonight's sweep is the honest result of a literature that has been genuinely exhausted over 13
prior nights. Four new angles were checked; three yielded nothing actionable (iceberg detection:
no crypto-specific source; placement depth: prior papers only; fill timing: Treasury futures only;
session effects: no academic primary source). One produced a single new diagnostic metric
(spread_at_signal_bps) from a partially-mined paper that was already in the verified source set.

**The forward-test queue is now 14 items.** The binding constraint remains empirical: 2–3 more
weeks of fills are needed before any of items 1–14 can be statistically evaluated. The most
implementable item in the queue is Tweak A (2 lines, no risk) and the overdue Tweak 2
(cancel-and-walk, already designed, deployment-ready).

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | 06-24 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | 06-23, clarified 06-26 | Queued |
| 3 | Shadow-gate VPIN computation | 06-23 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | 06-26 | Queued |
| 5 | Log `fg_regime` + `fg_extremity` flag (both extremes adverse) | 06-29, updated 07-09 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | 06-30 | Queued |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | 06-30 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | 07-06 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | 07-06 | Queued (shadow only) |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | 07-07 | Queued (shadow only; ~5 lines) |
| 11 | Log `vol_norm_tick` per symbol at signal time | 07-07 | Queued (diagnostic only) |
| 12 | Log `funding_rate_annual_pct` at signal time (spot-perp divergence proxy) | 07-08 | Queued (shadow only; ~3 lines) |
| 13 | Log `q_fill_score` composite (Albers formula: Q_near, Q_opp, imb) | 07-09 | Queued (shadow only; do NOT gate on BTC-calibrated coefficients) |
| **14** | **Log `spread_at_signal_bps` (current bid-ask spread in bps at signal time)** | **07-10** | **Queued (shadow only; ~2 lines; per-symbol rolling median needed for gating)** |

---

## Research Status

Fourteen nights. Tonight yields one genuine new diagnostic metric (spread_at_signal_bps) from a
verified source that was not fully mined in its prior appearance (night 12). The iceberg detection,
placement depth, fill timing, and session effects angles — four new directions searched tonight —
produced no applicable primary source beyond what was already in the queue.

All 14 shadow-log items require 2–4 more weeks of fill data before statistical evaluation.
SSRN 6344338 remains permanently inaccessible (14 nights). The academic microstructure literature
for this specific problem — passive short-reversion maker execution at small size, no rebate, on
crypto perps — is exhausted at the level of reachable sources.

The next highest-value action remains empirical: begin implementing the shadow-log items that
are ~2–5 lines each (Tweaks 4, 6, 9, 10, 11, 12, 14 are all trivially small) so the fill data
accumulates before the statistical evaluation can begin.
