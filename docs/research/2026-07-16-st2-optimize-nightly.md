# ST2.0 Execution Optimization — Night 20
**Date:** 2026-07-16 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 19 Nights

Prior nights 1–19 covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps (N13), post-settlement spread peak / cycle_phase (N14/N15), vol_norm_tick (N15), fill asymmetry inversion / tape direction noise / VPIN sustained-flow threshold (N16), large-taker arrival as cancel trigger / Albers v2 cancel comparison (N17), altcoin maker p>0.05 / LOB composite state calm/mixed/stressed (N18), regime misclassification (Avery & Ward) / OFI slope direction (N19).

**Three persistent unresolved gaps** carried from prior nights (unresolved after Night 20):
- Optimal cancel horizon (TTL): no primary-source calibration
- LOB depth replenishment speed after market orders on crypto perps: no applicable primary source
- Optimal passive sell placement depth inside spread: no applicable primary source

Tonight's searches targeted four uncovered angles: order arrival intensity / Hawkes processes for passive fill quality; 2026 crypto perp adverse selection measures; informed trading toxicity beyond VPIN; information decay / signal staleness for resting orders. Four searches run; four papers fetched. **Two new papers** (not cited in any prior night). One yields a new conceptual finding applicable as a shadow-log tweak; the other provides mathematical formalization of the adverse selection mechanism (corroboration only, no new tweak).

---

## Verified Sources (New Tonight)

### A — Hiremath & Hiremath 2026 — "Early Detection of Latent Microstructure Regimes in Limit Order Books"

- **Source:** Prakul Sunil Hiremath and Vruksha Arun Hiremath. "Early Detection of Latent Microstructure Regimes in Limit Order Books." arXiv:2604.20949 (April 2026).
- **URL:** https://arxiv.org/abs/2604.20949 (abstract); https://arxiv.org/html/2604.20949 (HTML, readable)
- **Dataset:** Primary results from 200 synthetic simulation runs. Real-data application: Binance BTC/USDT **spot** market (not perp), 1 Hz sampling, 1 week, n=5 stress events.
- **Access status:** Abstract and full HTML readable.

**Verified quotes (fetched from HTML):**

> "Gradual depth erosion, mild spread widening, slightly elevated imbalance—changes that remain below standard detection thresholds individually"

> "Across 200 simulation runs, the method achieves mean lead-time +18.6±3.2 timesteps (95% CI)."

> "A_t > 3×Ã_t^(10) sustained for ≥30 consecutive seconds" [stress state definition: spread > 3× 10-min rolling median for ≥30 s]

> "We do not claim the method is production-ready."

Real BTC/USDT result (extracted from paper): +38 ± 21 seconds lead-time, precision 1.00, coverage 0.80, **n=5 events**.

**The 4-channel composite the paper proposes:**
1. HMM entropy (regime uncertainty from a hidden Markov model fit once per day)
2. Depth erosion (sustained decline in near-side LOB depth)
3. Spread drift (normalized bid-ask widening)
4. Order flow momentum (persistent imbalance direction)

Combined via MAX aggregation (the highest-firing channel triggers the detector). The paper finds "HMM entropy and depth erosion account for >99% of first-trigger events."

**What this establishes for ST2.0:**

Prior nights established CONTEMPORANEOUS state at signal time (Tweak 20: calm/mixed/stressed LOB composite; Tweak 21: OFI slope direction). This paper introduces a TRAJECTORY framing: the book passes through a "latent deterioration phase" — measurable but individually sub-threshold depth erosion + spread widening + OFI momentum — before observable stress arrives. The detector's four channels can identify this latent phase ~38 seconds before observable stress in the real BTC data.

For ST2.0's absorption signal: if the book has already been in a "latent deterioration" trend for the 60 seconds before signal trigger, that is the period where depth is eroding and OFI is already building — the signal fires at or near peak stress. If the latent channels are still ACCELERATING at signal time (depth still eroding, OFI still rising, spread still widening), the regime has not peaked. If they are PLATEAUING or DECELERATING, the peak may be near or past.

**Why this is NEW vs prior nights:** Tweak 20 (N18) measures composite LOB state at signal time. Tweak 21 (N19) measures OFI slope (rising vs declining at signal time). This paper adds two new channels to the trajectory picture: DEPTH EROSION trend and SPREAD DRIFT trend. Neither of these has been proposed as a pre-signal trajectory metric in N1–N19. The multi-channel approach (all four signals together, not just OFI) is also new.

**Caveats:**
1. **+18.6 ± 3.2 timestep lead time is SIMULATED only.** The real BTC/USDT result (+38 ± 21 seconds, n=5) is explicitly labeled "preliminary illustrative" by the authors and lacks statistical power.
2. **BTC/USDT spot, not crypto perps, not altcoins.** The structural dynamics differ from Phemex AVAX/INJ/ARB/ENA perpetuals.
3. **HMM requires daily re-fitting.** The method requires fitting a hidden Markov model on each day's data — more infrastructure than a rolling indicator.
4. **Non-stationarity concern.** Authors explicitly warn: "The HMM is fitted once per day but BTC/USDT exhibits intra-session regime shifts," making the model stale within the trading day.
5. **Authors state: "We do not claim the method is production-ready."** This is one of the more honest caveats in the research series.

---

### B — DeLise 2024 — "The Negative Drift of a Limit Order Fill"

- **Source:** Timothy DeLise, Université de Montréal. "The Negative Drift of a Limit Order Fill." arXiv:2407.16527 (July 2024).
- **URL:** https://arxiv.org/html/2407.16527 (full HTML, readable)
- **Dataset:** 10-Year US Treasury Bond futures (TY contract). Primary: November 21, 2023 (6 AM–1 PM EST); validation: November 30, 2023. Traditional futures only — not crypto.
- **Access status:** FULLY READABLE (HTML).

**Verified quotes (fetched from HTML):**

> "Limit order fills are caused by and coincide with adverse price movements, which create a drag on the market maker's profit and loss."

> "approximately −0.0065 [ticks]" for direct measurement; theoretical expectation −0.48 ticks, empirical average drift −0.45 ticks (Table 2).

The mathematical proof (Equation 3): E[dt|f] = (Rf·P(U) − P(D)) / P(f), where Rf < 1 is the fill probability on a favorable move, P(U) ≈ P(D) for a symmetric random walk, and P(D) > Rf·P(U) because adverse-direction moves produce near-certain fills while favorable-direction moves produce only probabilistic fills. The numerator is negative → the expected drift conditional on fill is negative.

**What this establishes for ST2.0:**

The DeLise paper provides a mathematical proof of the adverse selection mechanism already described qualitatively in the synthesis (N0) and corroborated empirically in N18 (Casas et al., altcoin maker p>0.05). The key equation formalizes: the reason limit order fills carry negative drift is not randomness or bad luck — it is structural: adverse fills are near-certain (price moves against the position → limit is filled at the worst moment), while favorable fills (price bouncing away) are probabilistic.

The 0.45–0.48 tick magnitude applies to US Treasury Bond futures with a tick size of 1/64 and does not transfer numerically to crypto perps. The structural claim — that the drift is unavoidable for any passive maker without additional information advantage — does transfer.

**Why this is corroboration, not new:** The synthesis (N0) established this structurally using the Albers et al. (2502.18625) evidence: "Orders with negative subsequent five-second returns are highly likely to fill." DeLise's paper formalizes this as a theorem with proof. No new execution tweak arises from it — the mechanism was already known.

**Caveats:**
1. US Treasury Bond futures only — not crypto.
2. The 0.45–0.48 tick magnitude is not transferable.
3. The paper "beyond scope" caveat: they note that short-term alpha signals to preempt adverse moves are possible but out of scope; next-mid-price-direction empirical predictability is only 15–25% correlated.

---

## Papers Surveyed Tonight

| Paper | Why Checked | Verdict |
|---|---|---|
| arXiv:2604.20949 (Hiremath & Hiremath, April 2026) — "Early Detection of Latent Microstructure Regimes in LOBs" | New 2026 paper; 4-channel leading indicator of stress regime onset; BTC spot data | VERIFIED (HTML). Lead-time +38 ± 21 s (n=5 real events; +18.6 ± 3.2 is simulated). Depth erosion + HMM entropy the dominant channels. Authors: not production-ready. Yields Tweak 22 (shadow-log only). |
| arXiv:2407.16527 (DeLise, July 2024) — "The Negative Drift of a Limit Order Fill" | Quantified adverse drift after limit order fills; possible new angle on fill cost | VERIFIED (HTML). Provides mathematical proof + ~0.45–0.48 tick quantification for US Treasury futures. Corroborates synthesis finding. No new tweak. Not crypto. |
| arXiv:2403.02572 (Lokin & Yu, 2024) — "Fill Probabilities in a LOB with State-Dependent Stochastic Order Flows" | State-dependent fill probabilities; placement at different depths | NOT APPLICABLE. FX spot markets only. "Fill probabilities typically negligible for deeper levels." No crypto applicability. Persistent gap (placement depth) remains unresolved. |
| arXiv:2312.16190 (2023) — "Hawkes-based cryptocurrency forecasting via LOB data" | Hawkes process / order arrival intensity for passive fill quality | NOT APPLICABLE. Price direction forecasting, not adverse selection or fill quality for passive makers. Older paper (2023), not about execution quality. |

---

## New Forward-Testable Tweak

### Tweak 22 — Pre-Signal Latent Regime Trajectory Score (Shadow Log)
**Based on:** arXiv:2604.20949 (Hiremath & Hiremath, April 2026), verified above

**Mechanism:**
The paper establishes that book stress transitions follow a "latent build-up" phase with three observable (but individually sub-threshold) channels: depth erosion, spread widening, and OFI momentum. At signal time, these three channels are already readable from existing ws_feed.py / exchange.py data.

At each ST2.0 signal trigger, log whether these three channels are ACCELERATING (still building) or DECELERATING (at or past peak) over the 60-second window before signal:
- `depth_erosion_trend`: is ask-side near-queue depth declining in the 60s before signal? (`ask_depth_now < ask_depth_60s_ago`)
- `spread_drift_trend`: is spread widening in the 60s before signal? (`spread_now > spread_60s_ago`)
- `ofi_momentum_trend`: this overlaps with Tweak 21's ofi_slope_direction (already queued)

Combine into a `latent_traj_score` = count of channels still accelerating at signal time (0, 1, 2, or 3).

**Forward test hypothesis:** Do fills with high `latent_traj_score` (2–3 channels still accelerating) show worse post-fill outcomes than fills with low score (0–1 channels accelerating)? A high score means ST2.0 entered mid-deterioration (regime not yet peaked); a low score means the deterioration has flattened, which may coincide with the reversion setup.

**Implementation:** ~4 lines. Ask-side depth and spread are already available at signal time (exchange.py, ws_feed.py). Log 60s-prior snapshot vs current for both channels. The OFI component is covered by Tweak 21.

**Note on scope:** Tweak 21 (OFI slope direction) covers the OFI momentum channel from this paper. Tweak 22 adds the two non-OFI channels (depth erosion trajectory and spread drift trajectory). The composite `latent_traj_score` bundles all three.

**Caveat:** The paper's empirical basis is n=5 stress events on BTC/USDT spot. The 60-second window is inferred from the paper's ~38s real-data lead time, not a calibrated recommendation. The HMM entropy channel (the dominant one in the paper) is not proposed here because it requires daily model re-fitting — prohibitive complexity for a shadow log diagnostic. Do NOT gate live trades without 30+ fills per score category.

---

## Honest Caveats

1. **The three persistent literature gaps remain unresolved after Night 20.** Optimal cancel TTL, LOB replenishment speed, and placement depth inside spread have been searched for 7+ consecutive nights each with no primary source found on crypto perp data.

2. **Finding A (2604.20949) has very weak empirical grounding.** The headline +18.6 ± 3.2 timestep result is purely simulated. The real BTC/USDT application has n=5 events, no statistical power, and is labeled "illustrative" by the authors.

3. **Finding B (DeLise 2407.16527) is corroboration only.** The mathematical proof confirms what the synthesis established empirically. The 0.45–0.48 tick magnitude is US Treasury specific and does not transfer.

4. **The forward-test queue now stands at Tweaks 1–22, 0 deployed after 20 nights.** The binding constraint is empirical, not theoretical. Tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines of shadow-logging and have been queued for 3–5 weeks without implementation. Research has definitively outpaced implementation.

5. **The literature is genuinely exhausted for this problem domain.** Multiple nights have now returned the same papers (Albers 2502.18625, Casas 2602.00776, 2607.09230) even on new search angles. The marginal value of additional research nights is declining below the value of any shadow-log implementation.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | N4 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | N3/N6 | Queued |
| 3 | Shadow-gate VPIN computation | N3 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | N6 | **PRIORITY (2–5 lines)** |
| 5 | Log `fg_regime` + `fg_extremity` flag | N7/N9 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | N10 | **PRIORITY (2–5 lines)** |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | N10 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | N6 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | N6 | **PRIORITY (2–5 lines)** |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | N7 | **PRIORITY (2–5 lines)** |
| 11 | Log `vol_norm_tick` per symbol at signal time | N11 | **PRIORITY — diagnostic** |
| 12 | Log `funding_rate_annual_pct` at signal time | N12 | **PRIORITY (2–5 lines)** |
| 13 | Log `q_fill_score` composite (Albers formula) | N13 | Queued |
| 14 | Log `spread_at_signal_bps` | N14 | **PRIORITY (2–5 lines)** |
| 15 | Log `cycle_phase` = `utc_hour % 8` at signal time | N15 | Queued |
| 16 | Sustained buy-ratio imbalance gate (shadow log first) | N16 | Queued |
| 17 | Buy_ratio noise audit (Phemex WS aggressor-side flag check) | N16 | Queued (diagnostic) |
| 18 | Signal magnitude shadow-log (ensemble_confidence vs post-fill return) | N16 | Queued (diagnostic) |
| 19 | Log `large_taker_prefill` flag (single trade > Y% of ask queue while resting) | N17 | Queued (shadow only) |
| 20 | Log `lob_state` composite (spread + inverted depth + imbalance → calm/mixed/stressed) | N18 | Queued (requires Tweaks 6 + 14 first) |
| 21 | Log `ofi_slope_direction` at signal time (buy_ratio now vs 2 min prior → declining/flat/rising) | N19 | Queued (shadow only; ~3 lines) |
| **22** | **Log `latent_traj_score` = count of channels still accelerating at signal time: (a) ask-depth declining in prior 60s, (b) spread widening in prior 60s, (c) OFI momentum (= Tweak 21). Score 0–3. Compare post-fill outcomes by score.** | **N20** | **Queued (shadow only; ~4 lines; do not gate live without 30+ fills per category)** |

---

## Research Series Status

| Category | Status |
|---|---|
| Pre-entry gates | 10 tweaks (N1, N2, N3, N7, N11, N15, N16, N17, N21, N22 tonight) |
| At-entry placement | 4 tweaks (N4, N5, N8, N12) |
| Post-entry management / cancel | 4 tweaks (N6, N8, N9, N19) |
| Diagnostics only | 5 tweaks (N13, N14, N17, N18, N20) |
| Confirmed unresolvable via literature | Optimal TTL, LOB replenishment speed, placement depth inside spread |
| Blocked SSRN | 2 papers (6693260 + 6344338 — 20 consecutive nights) |

**Night 20 summary:** Two new papers. Finding A (Hiremath & Hiremath, April 2026) introduces a 4-channel latent regime trajectory concept — depth erosion + spread drift + OFI momentum + HMM entropy — with a real-data BTC/USDT lead time of +38 ± 21 s (n=5; weak). Grounds Tweak 22 (depth erosion and spread drift trajectory, 4 lines, shadow only). Finding B (DeLise 2024) provides mathematical proof of the negative-drift mechanism — corroborates synthesis; no new tweak; US Treasury only. The literature is exhausted for this problem. 22 tweaks queued, 0 deployed. **Recommendation: halt research series; implement Tweaks 4, 6, 9, 10, 11, 12, 14 (each 2–5 lines, highest priority) before any additional research nights.**
