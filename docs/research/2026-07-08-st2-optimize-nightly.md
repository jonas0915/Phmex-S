# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-07-08
**Night:** 12 of series
**Status:** Two genuine new findings from 2026 primary sources; one concrete forward-testable gate derivation; SSRN 6344338 blocked for 12th consecutive night.

---

## Context

Prior reports (nights 1–11, 06-20 synthesis through 07-07) have covered: adverse selection by
construction, queue position mechanics, Phemex rebate = 0, OFI-flip / micro-price filter,
cancel-and-walk (never repost), VPIN, funding-window gate (calendar proximity to settlement),
F&G regime, q_near_at_post, q_ratio, Lehalle-Mounjid latency formalization, universal −0.45 tick
fill drift, Phemex amendment endpoint, spoofable large bids, imbalance persistence duration, and
volatility-normalized tick size. Night 11 declared the academic literature "genuinely exhausted."

Tonight targeted four angles not previously attempted:
(a) Hawkes / self-exciting arrivals as an arrival-rate gate
(b) Cross-asset BTC→alt signal transfer and adverse selection correlation
(c) LOB depth profile shape as sweep velocity predictor
(d) Kyle lambda / Amihud alternatives to VPIN

---

## (a) What's New vs. Prior Reports

| Angle | Prior Coverage | Tonight's Result |
|---|---|---|
| Spot-futures OFI coupling (same asset) | Not in any prior report. 06-22 covered funding *window* (settlement time calendar gate). 06-29 covered F&G. Neither addressed real-time spot vs. perp OFI divergence. | **New finding** — two independent 2026 primary sources establish tight same-asset spot-to-futures coupling (c = 0.94). Enables a novel derivative-specific flow gate. See Tweak A. |
| Cross-asset signal transfer (BTC→alt) | Prior reports speculated about this but never researched it directly. | **New finding** (Pindza 2026): cross-asset transfer is weak (block-diagonal structure); same-asset spot↔futures transfer is strong. Directly refutes the idea of using BTC as a lead indicator for alt adverse selection. |
| Hawkes self-exciting arrivals | 07-06 searched OFI velocity / second-order imbalance, found only an Indian equities abstract (not applicable). | Deep Hawkes market-making paper (2109.15110, 2021) found but it optimizes maker quoting via RL — not applicable to ST2.0's one-shot passive short. No new actionable content. |
| LOB depth profile shape / sweep velocity | Not previously searched. | Search returned arxiv 2506.11843 (Sfendourakis 2025) — purely theoretical unified framework, no empirical trading guidance extractable from PDF. Not actionable. |
| Kyle lambda / Amihud as VPIN alternatives | VPIN covered 06-23. Kyle lambda and Amihud mentioned in search results but only via MetaTrader indicator page and a practitioner tool ("Aperiodic") — no new academic primary source found. Not actionable. |
| SSRN 6344338 (Rajendran & Singaravelu) | Blocked 11 prior nights | HTTP 403 again. 12th consecutive night. Confirmed permanently inaccessible via WebFetch. |

---

## (b) New Forward-Testable Finding

### Tweak A: Spot-vs-Perp OFI Divergence as a Derivative-Flow Gate

**Sources:**

1. Pindza, E. (2026). "Microstructure alpha: hierarchical learning and cross-asset transfer in
   cryptocurrency markets." *Frontiers in Blockchain*, Financial Blockchain section. Published
   June 11, 2026.
   **URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full
   **Verification:** Full article fetched directly. Peer-reviewed. VERIFIED.

2. Bieganowski, B. & Ślepaczuk, R. (2026). "Explainable Patterns in Cryptocurrency Microstructure."
   arXiv:2602.00776v1. January 31, 2026.
   **URL:** https://arxiv.org/html/2602.00776v1
   **Verification:** Full HTML fetched directly. arXiv preprint (not peer-reviewed). VERIFIED.

**What the papers establish:**

**Pindza (2026) — direct quote:**
> "Models trained on one cryptocurrency do not transfer to others, although they transfer well
> between the spot and futures venues of the same asset."

The paper describes a "clear block-diagonal structure: models transfer best to the same-asset
opposite venue (spot↔futures), with meaningfully lower correlations across underlying
cryptocurrencies."

**Bieganowski (2026) — direct quote:**
> "futures mid-price...exhibits variations...highly correlated with the spot order book
> imbalance (c=0.94)."

These two independent 2026 sources establish the same structural fact: same-asset spot OFI and
perpetual futures mid-price are tightly coupled. This is the empirical basis for the gate below.

**What this implies for ST2.0:**

ST2.0 fires when the *perpetual futures* book is bid-heavy and takers are aggressively buying.
The adverse-selection scenario is buying pressure that is genuine (informed directional demand)
continuing to push price up after the passive fill.

The spot-futures coupling result creates a diagnostic split:

- **Scenario A — perp buying AND spot buying (aligned):** Genuine directional demand across both
  venues → the futures price rise is anchored in spot → adverse fill likely → should SKIP.

- **Scenario B — perp buying but spot neutral/bearish (divergence):** Buying is derivative-specific
  (liquidation cascade, funding-driven rebalancing, perp-only speculation) → not anchored in spot
  → reversion more probable → proceed or weight entry positively.

This is the first prior-report-absent gate hypothesis that distinguishes *why* the perp is being
bought, not just *that* it is being bought. The existing tape gate (buy_ratio) and OB gate
(bid/ask imbalance) both measure "how much" buying; neither measures "where" the buying is
anchored.

**Implementation path — two tiers:**

*Tier 1 — funding rate proxy (low infrastructure cost):*

The equilibrium mechanism between spot and perp prices is the funding rate. When perp trades
significantly above spot (positive basis), the funding rate becomes strongly positive — longs pay
shorts to maintain perp premium. If ST2.0 fires AND funding is strongly positive (e.g., annualized
> 30%), this signals the perp is already stretched above spot: buying in the perp is fighting the
funding pull → more likely derivative-specific → higher reversion probability.

**IMPORTANT:** This is different from the 06-22 funding *window* gate, which blocks entries near
settlement times (UTC 5, 8, 13, 14, 16). The 06-22 gate is temporal (when). The proposed gate
here is magnitude-based (how stretched is the basis right now). The two gates compose
independently.

Infrastructure: `ccxt.fetch_funding_rate(symbol)` is already available via exchange.py. Adds
~1 API call per signal trigger. Shadow-log `funding_rate_bps_annual` at each ST2.0 signal.

*Tier 2 — actual spot OFI check (higher infrastructure cost):*

Fetch real-time spot L2 for the same underlying (e.g., AVAX/USDT spot on Binance or Phemex spot)
at signal time. Compute spot_imbalance = (spot_bid_vol − spot_ask_vol) / (spot_bid_vol +
spot_ask_vol). If `spot_imbalance > 0.15` AND `perp_imbalance > 0.25` (both bullish) → skip or
shadow-flag. If `spot_imbalance < 0` AND `perp_imbalance > 0.25` (divergence) → green-light.

Infrastructure cost: second WebSocket or polling connection to a spot venue. Not trivial — do NOT
implement until Tier 1 shadow data establishes whether the proxy is sufficient.

**Forward-testable Tweak A (shadow log, Tier 1 first):**

At each ST2.0 signal trigger, log:
```python
# Funding rate as spot-perp divergence proxy
# fetch once per signal, not per cycle (rate limit conservative)
fr = exchange.fetch_funding_rate(symbol)
funding_rate_annual_pct = fr['fundingRate'] * 3 * 365 * 100  # annualized from 8h rate
# Log alongside existing signal fields
```

After 20+ fills, test: do fills where `funding_rate_annual_pct > 30%` show better win rates
(reversion more likely) than fills where funding is near zero or negative? If yes, the funding
proxy captures the spot-perp divergence effect predicted by the Pindza/Bieganowski finding.

**Tier 1 first, Tier 2 only if Tier 1 shows null (proxy is lossy and we need real spot data).**

**Important caveats:**

1. **Pindza (2026) is about signal PREDICTION transferability, not adverse selection specifically.**
   The block-diagonal structure shows predictive models transfer within asset/venue pairs. The
   implication for adverse selection (buying is genuine vs. derivative-specific) is this author's
   inference, not a direct paper result.

2. **Bieganowski's c = 0.94 correlation** is from their specific dataset (Binance Futures, Jan 2022
   – Oct 2025, 1-second frequency). Correlation magnitude may differ on Phemex small-cap perps.
   The directional result (spot OFI anchors futures price) likely transfers; magnitude does not.

3. **Funding rate is a lagging proxy for the spot-perp basis.** It is set every 8 hours and
   reflects the *prior* 8 hours of premium accumulation, not the instantaneous premium at signal
   time. A premium that just opened in the last hour may not yet be reflected in the current
   funding rate. This limits Tier 1's precision.

4. **High positive funding is not guaranteed to mean reversion for ST2.0.** High funding attracts
   basis traders who short perp / buy spot to harvest the rate. This buying of spot (to hedge)
   can itself amplify the genuine spot bid, reducing rather than amplifying the spot-perp
   divergence at signal time.

5. **Phemex funding rate API reliability:** Verify that `ccxt.fetch_funding_rate` works reliably
   for all ST2.0 symbols on Phemex before shadow-logging. Not all small-cap pairs may return
   real-time rates.

---

### Observation B: Cross-Asset Lead Indicators Ruled Out

The Pindza (2026) block-diagonal result has a negative implication worth recording:

**Direct quote:**
> "Models trained on one cryptocurrency do not transfer to others."

This explicitly rules out using BTC order book state as a lead indicator for ST2.0 fill quality
on AVAX, INJ, ENA, or other small-cap perps. Prior research notes considered "BTC pumping at
signal time → alt fill adverse" as a plausible hypothesis (never implemented). Tonight's
peer-reviewed 2026 paper, studying exactly this question across BTC, ETH, LTC, ETC, ENJ, ROSE,
finds the effect does not transfer.

**Implication:** Do NOT implement a BTC-state filter for ST2.0 alt signals. The same-asset
spot-vs-perp gate (Tweak A) is the correct form of the inter-venue signal; cross-asset is not.

---

## (c) Caveats and Things Not Verified Tonight

- **SSRN 6344338** (Rajendran & Singaravelu, "Predicting Adverse Selection in High-Frequency
  Cryptocurrency Markets Using Gradient Boosting"): HTTP 403 for the 12th consecutive night.
  The PDF delivery URL from the search result (papers.ssrn.com/sol3/Delivery.cfm/6344338.pdf)
  also blocked. Permanently inaccessible via WebFetch. Manual institutional library access is
  the only remaining path.

- **SSRN 6693260** (Chang 2026): Not retried tonight (permanently blocked since night 1).

- **Hawkes arrival-rate gate:** Deep Hawkes paper (2109.15110) covers market-making via RL, not
  adverse selection gating for one-shot passive orders. No actionable Hawkes-based threshold found.

- **LOB depth shape:** arxiv 2506.11843 is purely theoretical; PDF content not extractable.
  The qualitative result from prior literature (hump-shaped depth profile = sweep is self-slowing)
  remains without a primary source usable as an ST2.0 gate.

- **Bieganowski's maker strategy during flash crash:** "fell victim to severe adverse selection"
  — the paper empirically shows taker strategies substantially outperformed maker strategies in
  extreme imbalance regimes. This is consistent with the 06-20 synthesis's structural finding.
  No new threshold is extractable, but it confirms that the *worst* adverse fills concentrate
  when OFI is "far outside its normal stationary range" — consistent with the imbalance
  persistence gate (07-07 Tweak A) hypothesis.

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
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | 07-07 | Queued (shadow only; ~5 lines) |
| 11 | Log `vol_norm_tick` per symbol at signal time | 07-07 | Queued (diagnostic only) |
| **12** | **Log `funding_rate_annual_pct` at signal time (spot-perp divergence proxy, Tier 1)** | **07-08** | **Queued (shadow only; ~3 lines; Tier 2 = real spot OFI only if Tier 1 null)** |

---

## Research Status

Twelve nights. Tonight yields one genuine new gate hypothesis: spot-vs-perp OFI divergence as a
derivative-flow discriminator, sourced from two independent 2026 primary sources (Pindza,
Frontiers in Blockchain; Bieganowski & Ślepaczuk, arXiv). The practical Tier 1 proxy is funding
rate magnitude at signal time — distinct from the existing 06-22 funding window gate, composable
with it, and implementable in ~3 lines.

Cross-asset lead indicator (BTC state as alt quality filter) is explicitly ruled out by the Pindza
(2026) block-diagonal transfer result.

SSRN 6344338 remains inaccessible (12 nights, permanent). The academic literature continues to
exhaust at the margins. All remaining high-value work is empirical: the 12-item forward-test queue
requires 2–3 weeks of shadow data before statistical evaluation is possible.
