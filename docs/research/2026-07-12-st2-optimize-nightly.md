# ST2.0 Execution Optimization — Night 16
**Date:** 2026-07-12 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 15 Nights

Prior nights covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps metric / confirmed literature gaps (N13), post-settlement spread peak cycle_phase metric (N14), volatility-normalized tick size (N15).

Tonight: **three new verified findings** — one structural (fill asymmetry inversion), one methodological (tape direction noise), one practitioner (VPIN sustained-flow threshold). The two highest-priority SSRN papers remain blocked (Night 16). LOB replenishment speed, optimal cancel horizon, and optimal placement depth remain unverified gaps — no primary source found despite fresh search framing.

---

## Verified Sources

### A — Albers et al. 2025 (PARTIALLY NEW — abstract unlocked tonight for first time)

- **Source:** Albers, Cucuringu, Howison & Shestopaloff. "The good, the bad, and latency: exploratory trading on Bybit and Binance." *Quantitative Finance*, Vol. 25, No. 6, pp. 919–947 (2025).
- **URLs:** https://ora.ox.ac.uk/objects/uuid:cdab1de2-7576-42e2-abae-ab12371eba76 (abstract, readable) | https://ideas.repec.org/a/taf/quantf/v25y2025i6p919-947.html (metadata, readable) | https://www.tandfonline.com/doi/full/10.1080/14697688.2025.2515933 (full text, paywalled)
- **Access status:** Abstract and metadata verified from two mirrors. Full paper paywalled — body NOT read.

**Verified quotes (from abstract):**

> "Profitable orders (as measured by short-term future PnL returns) tend to achieve worse-than-expected outcomes, while unprofitable orders typically achieve their expected (adverse) outcomes."

> "In the case of market orders, this translates to a worsening of fill prices, while marketable limit orders suffer from a substantial probability of failing-to-fill-immediately."

> "Quantitative researchers who fail to take these effects into account face the familiar litany of underperforming in a live trading environment relative to stellar backtests."

**What this means:** The fill-adversity pattern is inverted. When a maker order is directionally correct (would be profitable), execution is systematically *worse* than the backtest price — the fill either misses, or arrives at a degraded price. When the order is wrong, it fills perfectly. This is distinct from simple adverse selection after the fill — it documents the pre-fill degradation for the correct-signal orders. The mechanism is HFT counterparties recognizing the same predictive signals and outcompeting passive makers on fill quality precisely when the signal is most valuable.

**Caveat:** Abstract only. The quantitative magnitudes, asset coverage, and exact experimental design are unverified — do not cite specific numbers from this paper.

---

### B — Dubach 2026 (NEW — not cited in any prior report)

- **Source:** Dubach, Philipp D. "The Anatomy of a Decentralized Prediction Market: Microstructure Evidence from the Polymarket Order Book." arXiv:2604.24366v2 (May 14, 2026).
- **URL:** https://arxiv.org/html/2604.24366v2 (readable)
- **Access status:** Fully readable HTML.

**Verified quotes (fetched directly):**

> "Trade direction inference from the public feed shows only ~59% agreement with on-chain ground truth (volume-weighted: 0.592; bootstrap 95% CI [0.542, 0.659])."

> "Effective half-spread changes sign on 67% of markets in a first 7-day window" and "Kyle's λ changes sign on 60%."

> "The median adverse-selection component (is) 0.0" — the Glosten-Harris adverse-selection estimate collapses to zero for most markets due to direction misclassification.

**What this means:** When trade aggressor side is *inferred* rather than reported (which is the standard on most public order book feeds), Glosten-Harris and Kyle's λ decompositions are dominated by sign-noise, not information content. ws_feed.py classifies trades as buys or sells based on price movement relative to mid — a standard heuristic. At 59% accuracy, the buy_ratio signal used in ST2.0's tape gate is carrying ~41% classification noise. This does not invalidate the gate (the residual 59% true-positive rate is still better than random), but it means the gate attenuates far less informed flow than assumed, and raising the threshold does not proportionally improve quality — it mostly reduces fill rate.

**Caveat:** Polymarket is a decentralized prediction market, not a CEX perpetual futures venue. The 41% noise figure may differ on Phemex where Phemex reports aggressor-side flags in the trade stream. The structural warning stands, but the magnitude is venue-specific and unverified for Phemex.

---

### C — Silahian 2026 (MARGINALLY NEW — VPIN concept prior, this threshold is new; PRACTITIONER only)

- **Source:** Silahian, Ariel. "VPIN and Real-Time Order Toxicity: What Your Execution Stack Cannot See Before the Fill." ElectronicTradingHub.com (March 1, 2026).
- **URL:** https://electronictradinghub.com/vpin-and-real-time-order-toxicity-what-your-execution-stack-cannot-see-before-the-fill/ (readable)
- **Access status:** Fully readable practitioner article. NOT peer-reviewed.

**Verified quotes (fetched directly):**

> "by segmenting volume into buy-initiated and sell-initiated buckets on a volume clock rather than a time clock, you get a real-time, updating measure of the proportion of informed order flow"

> "at sustained elevated informed flow concentration, execution into that order flow carries structural adverse selection cost"

> "The LOB was not showing depth that reflected genuine liquidity intention...the composition of the book...was deteriorating over a multi-hour window"

> "When informed participants are concentrating their activity — when they know something the market makers do not — VPIN rises. Market makers facing that composition widen spreads or pull depth entirely."

**Author-calibrated threshold (NOT peer-reviewed):** "sustained VPIN above 0.7 for 8 or more consecutive volume bars" flagged as elevated adverse selection environment.

**What this means (if applied to ST2.0):** The article articulates a specific sustained-flow variant of the VPIN gate that differs from the snapshot buy_ratio gate already in ST2.0. The current OB gate samples buy_ratio at signal time. Silahian's angle is about *sustained* imbalance over multiple volume periods — a rising VPIN over 8 bars rather than a single-bar reading. A situation where buy_ratio has been elevated for 8 consecutive bars (say, 8 × ~30s = ~4 minutes of sustained absorption buying) may signal a genuine breakout rather than a reversion setup, even if the current-bar reading is within the 0.55 threshold.

**Caveat:** Author-calibrated threshold, no peer-reviewed backing. Volume bar definition unspecified. The VPIN concept's accuracy on crypto was already benchmarked at AUC 0.55 (Astorian 2021, BTC spot). Apply at low weight.

---

### D — Still Blocked (SSRN wall, Night 16)

| Paper | SSRN ID | Nights blocked |
|-------|---------|----------------|
| Chang 2026, "Do Order-Book States Predict Passive-Buy Toxicity?" | 6693260 | 16 |
| Rajendran & Singaravelu 2026, "Predicting Adverse Selection...Gradient Boosting" | 6344338 / 6551572 | 16 |

Both return HTTP 403 across all access routes. No claims from either paper can be verified.

---

### E — Confirmed Gaps (Active Search, No Source Found)

After fresh search framing tonight, these remain unverified across all accessible literature:

| Gap | Fresh Search Angles Tried Tonight | Result |
|-----|-----------------------------------|--------|
| Optimal cancel horizon (TTL) for passive crypto perp order | "limit order lifetime validity duration crypto maker stale order" | No primary source found |
| LOB depth replenishment speed after market order in crypto perps | "orderbook recovery speed crypto perpetual depth replenishment after market order" | No primary source found |
| Optimal passive sell placement (mid vs inside spread vs best ask) | "optimal limit order price placement inside spread best ask crypto perpetual maker" | No primary source found |

---

## Execution Tweaks for ST2.0 (Forward-Testable)

These are additions to the existing forward-test queue (Tweaks 1–15). Each is tied to a verified source with an explicit caveat.

### Tweak 16 — Sustained Buy-Ratio Imbalance Gate (Shadow Log First)
**Based on:** Silahian 2026 (practitioner, unverified thresholds) + existing ws_feed.py rolling buy_ratio

**Mechanism:** Before posting the passive limit short, check whether the last N consecutive ~30s samples from ws_feed have each shown buy_ratio > 0.60 (a sustained absorption condition). If all N bars are elevated, the interpretation shifts from "absorption reversion" to "breakout in progress" — skip entry this cycle.

**Why this differs from the existing tape gate:** The existing gate uses a single-bar buy_ratio snapshot. This tweak detects *persistence* of elevated buying across consecutive samples, targeting the scenario Silahian describes: "multi-hour LOB composition deterioration" before the adverse fill. An 8-bar × 30s = 4-minute window is a practical starting point.

**Forward test:** Shadow-log `buy_ratio_consecutive_bars_above_0.60` on every ST2.0 signal. Compare adverse selection rate (post-fill return) when this counter ≥ 4 vs < 4 before gating anything live.

**Caveat:** Author-calibrated threshold. N and the 0.60 cutoff require empirical calibration on ST2.0's actual signals. Do NOT apply as a live gate without shadow data.

---

### Tweak 17 — Buy_Ratio Noise Audit (Diagnostic, Not a Gate)
**Based on:** Dubach 2026 (arXiv 2604.24366) trade-direction classification accuracy

**Mechanism:** Check whether Phemex's WebSocket trade stream reports aggressor side (taker buy / taker sell) directly in the trade event payload. If it does, ws_feed.py can use ground-truth direction rather than inferred direction, potentially improving buy_ratio accuracy from the ~59% public-feed baseline.

**Why this matters:** If ws_feed.py currently infers aggressor side from price movement (trades at/above ask = buy, at/below bid = sell), the buy_ratio gate may have ~41% noise. Switching to reported aggressor-side flags (if available from Phemex) would eliminate this noise at zero algorithmic cost.

**Forward test:** Check Phemex WebSocket trade message schema for `"side"` or `"takerSide"` field. If present, compare the inferred buy_ratio against the reported buy_ratio on the same ws_feed data for 1 week. If meaningful agreement gap, switch to reported side.

**Caveat:** Dubach's 41% misclassification is from a decentralized prediction market, not Phemex perps. The magnitude may be much lower on Phemex if aggressor-side flags are already reported. This is a diagnostic to run before drawing any conclusions.

---

### Tweak 18 — Signal Magnitude Shadow-Log (Diagnostic, Not a Gate)
**Based on:** Albers et al. 2025 (Quant Finance Vol 25 No 6 — abstract only)

**Mechanism:** The abstract confirms that fill quality for *profitable* orders is systematically worse than backtest, while *unprofitable* orders fill as expected. If ST2.0's signal magnitude (e.g., ensemble confidence score, OFI reading, or ob.imbalance at signal time) correlates with directional correctness, then *higher-confidence signals may paradoxically attract worse fills* — the informed-flow interpretation implies HFT counterparties share the same signal and take liquidity aggressively when the setup is strong.

**Forward test:** Shadow-log `ensemble_confidence`, `ob_imbalance`, and `buy_ratio` at signal time for every ST2.0 fill. Segment by post-fill return (winner vs loser). Check: do higher-confidence signals win LESS often, or win at WORSE fill prices? If yes, this supports a counterintuitive gate: skip signals above a confidence ceiling.

**Caveat:** Abstract only — specific mechanism, magnitudes, and asset coverage from Albers et al. are unverified. This is a diagnostic hypothesis, not a validated finding. Do not implement as a live gate without ST2.0-specific data.

---

## Honest Caveats

1. **Two most directly relevant papers (SSRN 6693260, 6344338) remain blocked after 16 nights.** No claim from either can be stated. The most powerful ML-based adverse selection calibration results in the literature are inaccessible.

2. **The Albers et al. finding (Tweak 18) is abstract-only.** The quantitative magnitudes and experimental details are behind the Tandfonline paywall. The tweak is a hypothesis, not a calibrated rule.

3. **Silahian 2026 is a practitioner blog, not a peer-reviewed source.** The 0.7/8-bar threshold has no academic backing. Use only as inspiration for shadow-logging; do not gate live trades on it.

4. **Dubach 2026's 41% misclassification rate is from Polymarket, not a CEX perp.** Phemex's WebSocket feed may report ground-truth aggressor side, making this noise figure irrelevant. Verify the ws_feed.py schema before drawing conclusions.

5. **LOB replenishment speed, optimal cancel horizon, and optimal placement depth remain unverified gaps** after 16 nights of search. No peer-reviewed primary source with calibrated numbers exists in accessible literature for any of these three topics for crypto perp venues.

6. **The forward-test queue now stands at Tweaks 1–18, all undeployed.** The empirical bottleneck remains the binding constraint, not the research bottleneck.

---

## Research Series Status

| Category | Status |
|----------|--------|
| Pre-entry gates | 7 tweaks (N1, N2, N3, N7, N11, N15, N16 tonight) |
| At-entry placement | 4 tweaks (N4, N5, N8, N12) |
| Post-entry management | 3 tweaks (N6, N8, N9) |
| Diagnostics only | 4 tweaks (N10, N13, N14, N17-18 tonight) |
| Confirmed unresolvable via literature | Optimal TTL, LOB replenishment speed, placement depth inside spread |
| Blocked SSRN | 2 papers (N16 = Night 16 consecutive) |

The research series has covered all searchable literature angles. Priority shifts: deploy shadow-logging on Tweaks 13, 14, 16–18 (diagnostics) to generate ST2.0-specific data. The next binding constraint is empirical, not theoretical.
