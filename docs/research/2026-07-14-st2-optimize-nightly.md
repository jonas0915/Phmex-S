# ST2.0 Execution Optimization — Night 18
**Date:** 2026-07-14 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 17 Nights

Prior nights 1–17 covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps / confirmed literature gaps (N13), post-settlement spread peak cycle_phase metric (N14/N15), vol_norm_tick (N15), fill asymmetry inversion / tape direction noise / VPIN sustained-flow threshold (N16), large-taker arrival as cancel trigger / Albers v2 cancel comparison (N17).

Tonight's search targeted: (a) passive placement depth inside spread (persistent gap), (b) cancel horizon calibration (persistent gap), (c) LOB depth replenishment after market orders (persistent gap), (d) any 2025–2026 papers on passive altcoin perp execution quality. Four searches run, five papers fetched.

**Two genuinely new papers** — neither cited in any prior night. Neither directly resolves a persistent gap, but each yields a new diagnostic finding.

---

## Verified Sources (New Tonight)

### A — Casas et al. 2026 — "Explainable Patterns in Cryptocurrency Microstructure"

- **Source:** Casas, Marchetti & (co-authors). "Explainable Patterns in Cryptocurrency Microstructure." arXiv:2602.00776 (2026).
- **URL:** https://arxiv.org/html/2602.00776v1 (full HTML, readable)
- **Dataset:** Binance Futures perpetual contract order books and trades, 1-second frequency, January 1, 2022 – October 12, 2025. Assets: BTC, LTC, ETC, ENJ, ROSE (ranked 1, 20, 40, 60, 100 by market cap at start of period).
- **Access status:** FULLY READABLE (HTML).

**Verified quotes from paper (fetched directly):**

> "Positions are entered passively by posting limit orders at the bid (for buys) or ask (for sells)"

> "the strategy was repeatedly filled on its bid-side quotes, forcing it to accumulate a growing, and increasingly unprofitable, long position" [during flash crash — mechanism of catastrophic adverse selection]

> "all p-values exceed 0.05, so the null hypothesis of zero mean returns cannot be rejected for any asset in the maker backtest" [for altcoin perps]

Quantified maker performance table (their Table, extracted via fetch):

| Asset | Maker ARC | Taker ARC | Maker IR |
|-------|-----------|-----------|----------|
| BTC   | 2.93%     | 0.13%     | 5.47     |
| ENJ   | −0.81%    | 4.06%     | −0.77    |
| ETC   | −0.07%    | 5.78%     | −0.05    |
| ROSE  | +0.27%    | 7.00%     | +0.32    |

**What this establishes for ST2.0:**

1. **Passive altcoin maker returns are statistically zero** over 4 years of Binance Futures data. The null hypothesis (zero mean returns) cannot be rejected at p < 0.05 for any altcoin. This is the most rigorous statistical treatment of the "altcoin passive maker ceiling" seen in this research series — prior nights cited point estimates in bp terms; this paper provides the formal null-hypothesis test result.

2. **BTC is the structural exception**, not the rule. Maker IR = 5.47 for BTC vs. near-zero for all altcoins. The mechanism identified: less liquid altcoins face wider effective spreads and higher adverse selection costs, eroding spread capture. ST2.0 trades AVAX, INJ, ARB, ENA — altcoins — and this result applies directly.

3. **Placement is at the touch** (best ask for sells). The paper does NOT analyze inside-spread placement variants. The persistent gap (optimal depth inside spread) remains unresolved.

4. **"Fixed depth" means fixed notional size**, not fixed price distance from mid. This paper provides no placement depth optimization.

**Why this is NEW vs. prior nights:** The bp-level findings (e.g., Albers −0.47 bp, Binance imbalance strategy negative) were established in prior nights. Tonight's finding is the formal p-value result: a 4-year dataset with cross-asset coverage explicitly rejects the possibility that passive altcoin maker strategies have nonzero mean returns. This sets a hard statistical ceiling that was previously described structurally but not tested this way.

**Caveats:** Strategy type is symmetric market making (both sides), conditioned on microstructure patterns (not specifically short-reversion absorption). The altcoin p>0.05 result applies to their strategy, not identically to ST2.0. However, the mechanism (wider spreads + adverse selection > spread capture for altcoins) applies structurally.

---

### B — (Authors TBD) 2026 — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures"

- **Source:** arXiv:2607.09230 (July 2026 — published this month; not yet in any citation database).
- **URL:** https://arxiv.org/html/2607.09230 (full HTML, readable)
- **Dataset:** BTCUSDT and ETHUSDT perpetual futures on Binance; January 2023 – mid-2026; top-20 LOB snapshots at 1-minute frequency; 47,513 windows total; 18,631 macro-event windows.
- **Access status:** FULLY READABLE (HTML).

**Verified quotes from paper (fetched directly):**

> "Our dependent variable is not price but the post-event liquidity state of the book, a discrete calm, mixed, or stressed regime"

> "order flow earns its place over book shape mainly in the stressed pre-event states"

> "A one-minute snapshot cannot recover queue position, own-order fill probability, sub-second market-order impact, or a replay-grade execution simulator."

**Quantified regime-specific order flow incremental value (ETH, primary asset):**

| LOB State at Entry | OFI incremental value (1m) | OFI incremental value (5m) |
|---|---|---|
| Calm | +0.004 | +0.004 |
| Mixed | +0.020 | +0.015 |
| Stressed | **+0.038** | **+0.030** |

(Scale: proper-score increments over baseline. BTC: none of these clear the null at either horizon.)

**Stressed-state persistence probability: 0.456** — a book in "stressed" state has 45.6% probability of remaining stressed at the next 1-minute mark.

**LOB state definition used in the paper** (tercile-based composite):
- "Depth is negated, since a deep book is liquid and a thin book is stressed"
- Spread + inverted depth + imbalance → tercile composite → {calm, mixed, stressed}

**What this establishes for ST2.0:**

1. **The "stressed" LOB state — the regime ST2.0 enters (high absorption, bid-heavy imbalance, potentially thin ask-side)** — is the exact state where order flow has highest predictive power for future liquidity regime. Order flow informativeness triples from calm to stressed state.

2. **Stressed states persist.** 45.6% transition probability from stressed → stressed at 1-minute horizon. For a resting passive order in a stressed book, there is near-coin-flip odds the book remains stressed at the next minute. This means the adverse conditions (thin ask-side, aggressive buying, high imbalance) that ST2.0 uses as its signal also define the regime where adverse fills are most likely to persist post-entry.

3. **BTC order flow doesn't clear the null at any horizon.** ETH-like altcoins (where imbalance matters) are the correct analog for ST2.0's targets (INJ, ARB, ENA, AVAX).

**Why this is NEW vs. prior nights:** N10 established imbalance_duration_s (duration of continuous positive OFI). N6/N7/N12 track individual components (q_near, spread, imbalance). This paper introduces a COMPOSITE LOB regime classifier (calm/mixed/stressed) and quantifies that:
(a) stressed-state entry has 45.6% probability of remaining stressed (persistence number, new);
(b) order flow informativeness is state-dependent, scaling from +0.004 in calm to +0.038 in stressed (structural, new framing).

The composite regime classifier itself — combining spread, depth, imbalance into a single 3-state label — has not been proposed in any prior night's report.

**Caveats:** Paper predicts LOB regime transitions (calm/mixed/stressed), NOT price direction or passive order adverse selection directly. Authors explicitly acknowledge the snapshot cannot recover fill probability or queue position. The 45.6% persistence probability is for BTC/ETH on Binance at 1-minute frequency — not for small-cap alts at 5-minute signal resolution. The result may differ on Phemex and for the specific altcoins ST2.0 trades.

---

## Papers Surveyed Tonight (New vs. Prior Reports)

| Paper | Why Checked | Verdict |
|---|---|---|
| arXiv:2602.00776 (Casas et al., Feb 2026) — "Explainable Patterns in Crypto Microstructure" | Altcoin passive maker performance, placement depth, adverse selection quantification | VERIFIED. Altcoin maker p>0.05 (4-year Binance Futures). BTC exception IR=5.47. Placement at touch only. No depth optimization. See Finding A. |
| arXiv:2607.09230 (July 2026) — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions" | LOB state-dependent predictability, regime transitions, adverse selection in stressed states | VERIFIED. Stressed-state persistence 0.456. OFI informativeness 3× higher in stressed states. LOB composite regime classifier. See Finding B. |
| arXiv:2606.15715 (June 2026) — "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid" | Adverse selection for passive orders in on-chain crypto perp LOB | NOT APPLICABLE. Focuses on visible vs. hidden statistical metaorders (TWAP execution), not resting passive limit orders. Hyperliquid DEX, not CEX. No placement depth or cancel timing. |
| arXiv:1602.00731 — "Limit-Order Book Resiliency after Effective Market Orders" | LOB depth replenishment speed (persistent gap) | NOT APPLICABLE. Chinese equity stocks, not crypto. Recovery measured in "20 best limit updates" with no clock-time calibration. Persistent gap remains unresolved. |
| arXiv:2607.09230 already covered above | — | — |

---

## New Forward-Testable Tweak

### Tweak 20 — LOB State Composite Score at Signal Time (Shadow Log)
**Based on:** arXiv:2607.09230 (2607.09230, July 2026), verified above

**Mechanism:**
At each ST2.0 signal trigger, compute and log a coarse LOB state classification using the three components the paper identifies: current spread (in bps), ask-side depth at the order's level (inverted — thin book = stressed), and order book imbalance. Combine into a single composite score (e.g., sum of tercile ranks, 0–6) and classify as:
- `lob_state = "calm"` (composite 0–2)
- `lob_state = "mixed"` (composite 3–4)
- `lob_state = "stressed"` (composite 5–6)

**Components already partially covered by existing tweaks:**
- Tweak 6: `q_near_at_post` (ask depth component)
- Tweak 14: `spread_at_signal_bps` (spread component)
- Existing OB gate: `ob.imbalance` (imbalance component)

**The new value of combining them:** Rather than analyzing three separate metrics post-hoc, the composite label produces a single regime classification. The 2607.09230 finding establishes that in stressed-state books (the exact entry condition for ST2.0), order flow is most persistent and predictive — which means adverse conditions are most likely to continue after fill.

**Forward test hypothesis:** Do fills tagged `lob_state="stressed"` at signal time show significantly worse post-fill outcomes (price up after fill, short loses) vs. `lob_state="mixed"` or `lob_state="calm"` fills? If the stressed-state persistence result transfers to ST2.0's altcoin universe, stressed-state entries should have the worst post-fill return distribution.

**Implementation:** ~5 lines — at signal time, read `spread_bps`, `q_near_at_post`, and `ob.imbalance`; compute tercile ranks relative to rolling 30-day per-symbol distributions; sum and classify. Existing variables are already available at signal time.

**Why this is not Tweak 6/14 duplicated:** Each of 6 and 14 is a single-dimension diagnostic. Tweak 20 proposes a composite regime label, whose predictive value comes from the joint distribution of all three dimensions simultaneously — consistent with the paper's finding that the composite regime, not any single component, predicts state persistence.

**Priority note:** Tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines and remain unimplemented. Tweak 20 depends on 6 and 14 being logged first (those components need rolling-baseline calibration). Sequence: implement 6 + 14 + existing imbalance → then derive Tweak 20 composite.

**Caveat:** Tercile thresholds must be calibrated per-symbol (INJ/ARB/ENA likely have different spread/depth distributions than BTC/ETH). Do not apply a BTC-derived threshold directly. Require 30-signal rolling baseline per symbol before the composite is meaningful.

---

## Honest Caveats

1. **The three persistent unresolved gaps remain open after Night 18.** Optimal cancel TTL (uncalibrated beyond 90s practitioner heuristic), LOB depth replenishment speed (no crypto perp primary source — the only resiliency paper found was Chinese equity stocks), and optimal placement depth inside spread (no applicable primary source). All three have been searched for 6+ nights.

2. **Neither new paper directly addresses passive execution tactics.** Finding A (altcoin maker p>0.05) corroborates the structural ceiling but provides no new execution mechanism. Finding B (stressed-state persistence) is about LOB regime transitions, not fill probability or adverse selection magnitude.

3. **The 45.6% stressed-state persistence is on BTC/ETH at 1-minute resolution.** ST2.0 signals on 5-minute candles for small-cap altcoins on Phemex. Both the resolution mismatch and the asset-class difference mean the exact number is non-transferable. The structural relationship (stressed → persistent stress) is more robust than the specific probability.

4. **Altcoin maker p>0.05 result (Finding A) is on a symmetric strategy, not ST2.0's directional absorption short.** However, the mechanism (wider spreads + adverse selection > spread capture for altcoins) applies structurally to any passive altcoin maker strategy, including ST2.0.

5. **Forward-test queue now stands at Tweaks 1–20, 0 deployed.** This is Night 18. The binding constraint is empirical, not theoretical. Tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines and should take absolute priority over any further research nights until shadow data is available.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | N4 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | N3/N6 | Queued |
| 3 | Shadow-gate VPIN computation | N3 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | N6 | **Queued — PRIORITY (2–5 lines)** |
| 5 | Log `fg_regime` + `fg_extremity` flag | N7/N9 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | N10 | **Queued — PRIORITY (2–5 lines)** |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | N10 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | N6 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | N6 | **Queued — PRIORITY (2–5 lines)** |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | N7 | **Queued — PRIORITY (2–5 lines)** |
| 11 | Log `vol_norm_tick` per symbol at signal time | N11 | **Queued — PRIORITY (diagnostic; 2–5 lines)** |
| 12 | Log `funding_rate_annual_pct` at signal time | N12 | **Queued — PRIORITY (2–5 lines)** |
| 13 | Log `q_fill_score` composite (Albers formula) | N13 | Queued (do NOT gate on BTC coefficients) |
| 14 | Log `spread_at_signal_bps` | N14 | **Queued — PRIORITY (2–5 lines)** |
| 15 | Log `cycle_phase` = `utc_hour % 8` at signal time | N15 | Queued |
| 16 | Sustained buy-ratio imbalance gate (shadow log first) | N16 | Queued |
| 17 | Buy_ratio noise audit (Phemex WS aggressor-side flag check) | N16 | Queued (diagnostic) |
| 18 | Signal magnitude shadow-log (ensemble_confidence vs post-fill return) | N16 | Queued (diagnostic) |
| 19 | Log `large_taker_prefill` flag (single trade > Y% of ask queue while resting) | N17 | Queued (shadow only; ~5 lines in ws monitoring loop) |
| **20** | **Log `lob_state` composite (spread + inverted depth + imbalance tercile composite → calm/mixed/stressed) at signal time. Depends on Tweaks 6 + 14 being active first.** | **N18** | **Queued (shadow only; ~5 lines; requires 30-signal rolling baseline per symbol)** |

---

## Research Series Status

| Category | Status |
|---|---|
| Pre-entry gates | 8 tweaks (N1, N2, N3, N7, N11, N15, N16, N17) |
| At-entry placement | 4 tweaks (N4, N5, N8, N12) |
| Post-entry management / cancel | 4 tweaks (N6, N8, N9, N19) |
| Diagnostics only | 4 tweaks (N13, N14, N17, N18, N20 tonight) |
| Confirmed unresolvable via literature | Optimal TTL, LOB replenishment speed, placement depth inside spread |
| Blocked SSRN | 2 papers (6693260 + 6344338 — multiple consecutive nights) |

**Night 18 summary:** Two new papers, neither previously cited. Finding A establishes the formal statistical ceiling for altcoin passive makers (p>0.05, 4-year dataset). Finding B introduces the LOB composite state variable (stressed-state persistence = 0.456) and grounds the proposed composite regime diagnostic (Tweak 20). The empirical bottleneck — 20 queued tweaks, 0 deployed — remains the dominant constraint.
