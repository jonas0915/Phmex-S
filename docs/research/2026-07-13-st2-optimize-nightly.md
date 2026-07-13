# ST2.0 Execution Optimization — Night 17
**Date:** 2026-07-13 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 16 Nights

Prior nights 1–16 covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps / confirmed literature gaps (N13), post-settlement spread peak cycle_phase metric (N14/N15), vol_norm_tick (N15), fill asymmetry inversion / tape direction noise / VPIN sustained-flow threshold (N16).

**Three persistent unresolved gaps** carried from prior nights (still open after tonight):
- Optimal cancel horizon (TTL): the 90s rule has no primary-source calibration
- LOB depth replenishment speed after market orders on crypto perps: no applicable primary source
- Optimal passive sell placement depth (mid vs inside spread vs best ask): no applicable primary source

Tonight's search strategy: targeted the three open gaps plus any new 2026 papers. Six papers/sources checked; five were inapplicable or already covered. **One new finding** — a quantified cancellation comparison from the v2 update of Albers et al. (2502.18625), which was not in v1 and has not appeared in any prior night's report.

---

## Verified Source (New Tonight)

### A — Albers et al. 2025 v2 (NEW in v2 — not in v1, not cited in any prior report)

- **Source:** Albers, Cucuringu, Howison & Shestopaloff. "The Market Maker's Dilemma: Navigating the Fill Probability vs. Post-Fill Returns Trade-Off." arXiv:2502.18625v2 (revised 2025).
- **URL:** https://arxiv.org/html/2502.18625v2 (full HTML, readable)
- **Dataset:** Live trading experiments on Binance Bitcoin perpetual market.
- **Access status:** FULLY READABLE (v2 HTML).

**Verified quotes from v2 (fetched directly):**

> "If the top bid price moved up or the top ask price moved down without the respective orders filling, we canceled and reposted them at the updated top price."

This describes their price-triggered cancellation protocol used in the continuous quoting mode. The periodic quoting mode version: "If the top bid or ask price changed, leaving the respective order posted deeper in the book, we canceled it."

The v2 paper compares the imbalance-based maker strategy with and without a cancellation rule (cancel when imbalance shifts adversely):

> "Imbalance-based maker strategy (without cancellation): −0.4705 bp mean return"
> "Imbalance-based maker strategy with cancellation: −0.4921 bp mean return"

And — critically — the diagnosis of why the cancel rule makes things slightly worse:

> "only mitigates a subset of those adverse cases, namely the ones where imbalance slowly changes adversely, rather than sudden adverse price moves caused by, e.g., large taker orders"

**What this establishes:**

1. **Adding an imbalance-shift cancel rule worsens outcome by 0.02 bp** (−0.47 → −0.49 bp), not improves it. The marginal overhead of cancellation (losing queue position, re-posting cost, timing gap) outweighs the benefit.

2. **The diagnostic is specific:** imbalance-triggered cancel ONLY helps when the book deteriorates slowly. It specifically fails for the case most relevant to ST2.0 — sudden large taker orders buying through the ask — because by the time the cancellation fires (imbalance has slowly shifted), the damage is already done.

3. This extends Night 6 ("cancel worsens performance") with a quantified magnitude and a mechanistic explanation on crypto perp data.

**Why this is NEW vs Night 6:** Night 6 established the directional finding (cancel can worsen) from practitioner reasoning and Phemex RPI context. Tonight's finding gives the quantified result on Binance BTC perp live trading data, and — more importantly — identifies the SPECIFIC failure mode: imbalance-triggered cancel misses sudden large taker arrivals entirely.

**Caveat:** The comparison is on a symmetric market-making strategy (posting both bid and ask) on BTC perpetual, not on ST2.0's one-directional passive short. The magnitude difference (−0.02 bp) may not transfer directly. The structural diagnosis (slow-imbalance vs sudden-large-taker failure mode) is the more transferable finding.

---

## New Forward-Testable Tweak

### Tweak 19 — Large-Taker Arrival as Cancel Trigger (Shadow Log First)
**Based on:** Albers et al. v2 (2502.18625v2), verified above

**Mechanism:**
The Albers finding establishes that imbalance-shift cancel fails specifically for "sudden adverse price moves caused by large taker orders." For ST2.0, the absorbing-bid scenario involves sustained aggressive buying. If a single large taker order exceeds a threshold (e.g., > X% of the ask-side queue depth at the order's price level), this is the case Albers identifies as causing the adversely-selected fill — and it's exactly the case the imbalance-triggered cancel misses.

The proposed log: when ST2.0's passive limit sell is resting, track whether a large taker arrives on the bid side (single-trade size > Y% of ask-side queue at the order's level) before the fill. If such an event precedes the fill, tag the trade as `large_taker_prefill=True`.

**Forward test hypothesis:** Do trades tagged `large_taker_prefill=True` show systematically worse post-fill outcomes (price continues up after fill) vs. trades where the fill came from accumulated smaller orders? If confirmed, this justifies a cancel-on-large-taker-arrival rule. If NOT confirmed (large takers precede good fills), no gate is warranted.

**Implementation:** ws_feed.py already streams trade sizes. At each incoming trade while the passive order is resting, check `trade_size > threshold` and log the flag. (~5 lines in the order-monitoring loop.)

**Why this differs from a fixed imbalance cancel:** The existing buy_ratio gate is a snapshot at entry. This tracks single-trade bursts while resting — the precise event class Albers identifies as uncancellable by a slow imbalance shift.

**Caveat:** Threshold calibration (Y% of ask queue) requires shadow data. Albers' dataset is BTC perp at much larger size than ST2.0's $150 notional — the threshold that constitutes "large" on BTC may be structurally different from small-cap alts (INJ, ARB, ENA, AVAX). Do NOT gate on this live without first shadow-logging the distribution of pre-fill trade sizes on at least 30 fills.

---

## Papers Surveyed Tonight (New vs Prior Reports)

| Paper | Why Checked | Verdict |
|---|---|---|
| arXiv:2506.05764 (Wang, June 2025) — "Exploring Microstructural Dynamics in Crypto LOBs: Better Inputs..." | New June 2025 paper on crypto LOB dynamics | Dataset: BTC/USDT LOB snapshots at Bybit. Paper is about ML feature selection for LOB price forecasting — not about placement depth, cancel timing, or adverse selection for passive orders. NOT APPLICABLE. |
| arXiv:2603.09164 (Sepper, March 2026) — "Slippage-at-Risk: A Forward-Looking Liquidity Risk Framework..." | LOB depth recovery / replenishment speed | Hyperliquid data. Framework covers forward-looking slippage risk metrics (SaR, ESaR, TSaR), not depth replenishment dynamics post-market-order. NOT APPLICABLE to LOB replenishment gap. |
| arXiv:2502.18625v2 (Albers et al., v2 update) — "The Market Maker's Dilemma" | v2 new content on cancel protocol and placement depth | VERIFIED. Yields Tweak 19 (see above). Price-triggered cancel protocol and quantified imbalance-cancel comparison extracted. |
| arXiv:2606.05882 (Ochędzan & Antulov-Fantulin, June 2026) — "Market Informedness and Market-Maker Profitability..." | New angle: adverse selection as function of aggregate market informedness | Agent-based simulation, no empirical data. Finding: "informed market order flow is particularly harmful when aggregate market informedness is low." Not directly calibratable to ST2.0. NOT ACTIONABLE. |
| arXiv:2511.20606 (Wu, November 2025) — "LOB Dynamics in Matching Markets: Microstructure, Spread, and Execution Slippage" | Placement depth and spread/slippage for passive makers | Theoretical paper on non-financial matching markets (labor markets analogy). Not about crypto or traditional financial LOBs. NOT APPLICABLE. |

---

## Honest Caveats

1. **The three persistent literature gaps remain unresolved after Night 17.** Optimal cancel TTL (uncalibrated beyond 90s practitioner heuristic), LOB replenishment speed (no crypto perp primary source), and optimal placement depth (mid vs inside vs best ask — no applicable primary source) have now been searched for six or more nights each with no primary source found. These gaps may not have accessible literature solutions.

2. **Tweak 19 (large-taker cancel trigger) is diagnostic only.** The finding from Albers v2 diagnoses the failure mode but provides no calibrated threshold. The relevant event on small-cap alts (INJ, ARB, ENA) may look structurally different from BTC perp large-taker events.

3. **The quantified comparison (−0.47 vs −0.49 bp) is on BTC perp symmetric market-making.** ST2.0 is directional, short-only, small-cap alts. The magnitude difference may not transfer; the mechanistic diagnosis is more transferable than the number.

4. **Night 17 total forward-test queue: Tweaks 1–19, all undeployed.** The empirical bottleneck remains the binding constraint. Shadow-log tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines and remain unimplemented — these should take priority over any new research angles.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | N4 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | N3/N6 | Queued |
| 3 | Shadow-gate VPIN computation | N3 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | N6 | Queued |
| 5 | Log `fg_regime` + `fg_extremity` flag (both extremes adverse) | N7/N9 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | N10 | Queued |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | N10 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | N6 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | N6 | Queued (shadow only) |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | N7 | Queued (shadow only; ~5 lines) |
| 11 | Log `vol_norm_tick` per symbol at signal time | N11 | Queued (diagnostic only) |
| 12 | Log `funding_rate_annual_pct` at signal time (spot-perp divergence proxy) | N12 | Queued (shadow only; ~3 lines) |
| 13 | Log `q_fill_score` composite (Albers formula: Q_near, Q_opp, imb) | N13 | Queued (do NOT gate on BTC-calibrated coefficients) |
| 14 | Log `spread_at_signal_bps` (current bid-ask spread in bps at signal time) | N14 | Queued (shadow only; ~2 lines) |
| 15 | Log `cycle_phase` = `utc_hour % 8` at signal time | N15 | Queued (shadow only; ~3 lines) |
| 16 | Sustained buy-ratio imbalance gate (shadow log first, 8-bar × 30s window) | N16 | Queued |
| 17 | Buy_ratio noise audit (check if Phemex WS reports aggressor-side flag) | N16 | Queued (diagnostic) |
| 18 | Signal magnitude shadow-log (ensemble_confidence vs post-fill return) | N16 | Queued (diagnostic) |
| **19** | **Log `large_taker_prefill` flag (single trade > Y% of ask queue while resting) — shadow only; compare post-fill outcomes tagged vs untagged** | **N17** | **Queued (shadow only; ~5 lines in ws monitoring loop)** |

---

## Research Series Status

| Category | Status |
|---|---|
| Pre-entry gates | 8 tweaks (N1, N2, N3, N7, N11, N15, N16, N17) |
| At-entry placement | 4 tweaks (N4, N5, N8, N12) |
| Post-entry management / cancel | 4 tweaks (N6, N8, N9, N19 tonight) |
| Diagnostics only | 3 tweaks (N13, N14, N17, N18) |
| Confirmed unresolvable via literature | Optimal TTL, LOB replenishment speed, placement depth inside spread |
| Blocked SSRN | 2 papers (SSRN 6693260 + 6344338 — Night 17 consecutive, effectively permanent) |

**Priority note:** 19 tweaks queued, 0 deployed. The most implementable items (Tweaks 4, 6, 9, 10, 11, 12, 14 — each 2–5 lines, shadow-log only) have been ready for weeks. Research is no longer the bottleneck.
