# ST2.0 Execution Optimization — Night 19
**Date:** 2026-07-15 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 18 Nights

Prior nights 1–18 covered: crumbling-bid gate (N1), funding-cycle U-shape (N2), OFI half-life / VPIN concept (N3), micro-price filter (N4), Boltzmann β / MLOFI (N5), cancel worsens performance / Phemex RPI (N6), Fear & Greed regime (N7), fill-probability regression coefficients (N8), Phemex amendment endpoint / bid spoofing (N9), imbalance persistence / tick-size hostility (N10), spot-perp OFI divergence / funding magnitude (N11), queue-position magnitude 0.717 bp / composite q_fill_score (N12), spread_at_signal_bps (N13), post-settlement spread peak / cycle_phase (N14/N15), vol_norm_tick (N15), fill asymmetry inversion / tape direction noise / VPIN sustained-flow threshold (N16), large-taker arrival as cancel trigger / Albers v2 cancel comparison (N17), altcoin maker p>0.05 / LOB composite state calm/mixed/stressed (N18).

**Three persistent unresolved gaps** carried from prior nights (6+ nights of search each):
- Optimal cancel horizon (TTL): no primary-source calibration
- LOB depth replenishment speed after market orders on crypto perps: no applicable primary source
- Optimal passive sell placement depth inside spread: no applicable primary source

Tonight's searches targeted: (a) entry-timing delay post-signal to reduce adverse selection (new angle), (b) small-size altcoin passive fill quality (new angle), (c) maker-taker switch economics (new angle), (d) temporal intraday dynamics for crypto perp microstructure (new angle). Four searches run; five fetches attempted (two blocked — SSRN 6344338 still HTTP 403 for the 19th consecutive night; MDPI full text HTTP 403).

**One genuinely new paper** (not cited in any prior night) with a conceptual finding applicable to ST2.0. One corroboration of an existing finding (MDPI, limited access).

---

## Verified Sources (New Tonight)

### A — Avery & Ward 2026 — "Is Trend Still Your Friend? A Microstructural Account of the Demise of Short-Term Trend-Following"

- **Source:** Avery & Ward. "Is Trend Still Your Friend? A Microstructural Account of the Demise of Short-Term Trend-Following." arXiv:2607.01550 (July 2026 — published this month; not in any citation database yet).
- **URL:** https://arxiv.org/html/2607.01550 (full HTML, readable)
- **Dataset:** ~100 liquid futures contracts across commodities (CMD), equity indices (IDX), currencies (FXR), and government bonds/yields (YLD). CME Globex intraday bar data, 1995–2025.
- **Access status:** FULLY READABLE (HTML).

**Verified quotes from paper (fetched directly):**

> "The dominant cost of passive execution for a trend follower is therefore not adverse selection in the usual sense (being filled by better-informed counterparties before the price moves against them); it is the opposite – the missed-opportunity cost of failing to be filled while the price runs away in the direction of the signal."

> "The trend follower's passive bid will be filled preferentially in the bad states of the world (when the price drops through it) and missed in the good ones (when the price runs away upward)."

> "Limit-order execution is favoured in mean-reverting environments, and detrimental in trend following environments."

**What this establishes for ST2.0:**

The paper defines two structurally distinct execution regimes for passive limit orders:
- **Mean-reverting environment:** passive limit orders are *favored* — price touches the order and reverts, producing profitable fills with naturally low adverse selection
- **Trending environment:** passive limit orders are *detrimental* — the "good" fills (price reverting) never happen because price runs away; only the "bad" fills (price continuing through the order against the position) occur

ST2.0 is designed as a **short-reversion strategy** (expects price to revert after absorption). In a genuine reversion setup, Avery & Ward's framework predicts passive execution should be *favorable*. The fact that ~57% of ST2.0's fills are adversely selected (established in N18/synthesis) implies that a substantial fraction of signal triggers are occurring in trending regimes disguised as reversion setups at entry time.

**The execution reframing this produces:** Prior nights framed the adverse fill problem as an execution mechanics failure (wrong cancel timing, poor queue position, etc.). This paper reframes it: the adverse fills are not execution failures — they are **regime misclassification events**. When the book is genuinely in a mean-reverting state, passive sells are theoretically favored and should produce better fills. When the book is in a trending state (price will continue up), passive sells fill on every order no matter how well-positioned — and always lose. The implication: **improving regime discrimination at entry time** may reduce adverse selection more than any execution mechanic.

**Why this is NEW vs prior nights:** Prior nights established adverse selection as a structural problem (N18: altcoin maker p>0.05; N1-N12: queue, spread, tape mechanics). Tonight's finding provides a different causal explanation: adverse fills ≠ execution mechanics failure; they = regime misclassification. No prior report has framed the problem this way.

**Caveats:**
1. **Traditional futures only (CME; equities, FX, bonds).** Not tested on crypto perps or altcoins. The "favored in mean-reverting environments" claim is established on liquid, large-notional CME contracts — very different microstructure from AVAX/INJ/ARB/ENA on Phemex.
2. **No quantified thresholds provided.** The paper identifies the structural pattern qualitatively but does not provide calibrated bp-level estimates or entry-filter thresholds.
3. **ST2.0 is already trying to identify the reversion regime.** The finding doesn't say regime identification is *possible* at ST2.0's resolution — only that execution is favorable *when the regime is correctly identified*.
4. **"Favored" is relative.** Even in mean-reverting regimes, passive fills carry some adverse selection. The claim is directional, not that adverse selection vanishes.

---

### B — MDPI 2026 — "Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures"

- **Source:** (Authors TBD). "Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures: Econometric Evidence from Centralized and Decentralized Exchanges." *IJFS* Vol. 14, No. 5 (2026) — MDPI.
- **URL:** https://www.mdpi.com/2227-7072/14/5/103 (full text HTTP 403, not readable); https://ideas.repec.org/a/gam/jijfss/v14y2026i5p103-d1926363.html (metadata readable)
- **Dataset:** 26 exchanges, 812 symbols, 9.1 million hourly data points, 53 overlapping 7-day rolling windows, November 2025 – January 2026.
- **Access status:** Metadata and abstract readable via repec mirror. Full paper HTTP 403 — body NOT read.

**Verified quotes from accessible abstract/metadata:**

> "Intraday spread patterns are statistically significant and linked to funding rate settlement mechanics, with spreads peaking approximately two hours after standard settlement times."

> "mid-tier exchanges lead the largest venue (Binance) more frequently than the reverse"

> "near-integrated (IGARCH) volatility behavior...appears in only 24.5% of windows"

**What this establishes for ST2.0:**

The "spreads peaking approximately two hours after standard settlement times" finding corroborates the existing Tweak 15 (cycle_phase = utc_hour % 8) from Night 15 (post-settlement spread cycle). The new value of tonight's citation: the N15 finding was derived from a practitioner source and one paper. This MDPI result provides empirical backing across **812 symbols on 26 exchanges** with rolling-window statistical tests (GARCH, Bai-Perron, CUSUM), covering Nov 2025–Jan 2026 — a broader and more recent dataset.

The specific timing implication: Phemex funding settles at UTC 0:00, 8:00, 16:00. "Two hours after" = UTC 2:00, 10:00, 18:00. In 12-hour PT: **6:00 PM PT / 10:00 PM PT / 2:00 AM PT** are the widest-spread windows. These are the hours when passive maker half-spread capture is theoretically highest — but also where volatility conditions are most elevated.

**Why this is not fully new:** N14/N15 already established cycle_phase and post-settlement spread timing. The MDPI paper corroborates rather than extends this finding. No new execution tweak arises from it directly.

**Caveats:** Abstract-only access. The "approximately two hours" is quoted from the search result summary, not a direct sentence from the full paper. Do not treat the 2-hour timing as precisely verified without reading the full paper.

---

## Papers Surveyed Tonight

| Paper | Why Checked | Verdict |
|---|---|---|
| arXiv:2607.01550 (Avery & Ward, July 2026) — "Is Trend Still Your Friend? Microstructural Account of Trend-Following" | New July 2026 paper on passive execution costs vs missed-opportunity costs for directional strategies | VERIFIED (HTML). Yields regime-discrimination reframing (Finding A). CME futures only, not crypto perps. No quantified thresholds. |
| MDPI 2227-7072/14/5/103 (2026) — "Temporal Dynamics of Crypto Perp Microstructure" | Intraday timing for passive maker execution; spread cycles across 812 symbols | PARTIAL. Abstract only (full text HTTP 403). Corroborates N15 cycle_phase finding across 812 symbols / 26 exchanges. No new execution tweak. |
| arXiv:2409.12721v2 — "Market Simulation under Adverse Selection" | Cancel-or-hold decision thresholds; LOB replenishment after market orders | NOT APPLICABLE. CME equity/bond futures only. No cancel horizon calibration. No crypto content. |
| SSRN 6344338 (Rajendran & Singaravelu) — "Predicting Adverse Selection...Gradient Boosting" | Best available ML adverse selection model for crypto HFT | BLOCKED (HTTP 403, Night 19 — 19 consecutive nights). No claims verifiable. |

---

## New Forward-Testable Tweak

### Tweak 21 — OFI Slope Direction at Signal Time: Trend vs. Reversion Discriminator (Shadow Log)
**Based on:** arXiv:2607.01550 (Avery & Ward, July 2026), verified above

**Mechanism:**
The Avery & Ward finding establishes that passive fill quality is structurally favorable in mean-reverting environments and detrimental in trending ones. For ST2.0, the signal fires when OFI is elevated (aggressive bid absorption). The discriminating question is: is the OFI *peaking and rolling over* (genuine reversal setup) or *still accelerating* (trend continuation)?

At each ST2.0 signal trigger, log the **OFI slope direction** over the prior N samples from ws_feed:
- `ofi_slope = "declining"`: the buy_ratio / OFI was higher N bars ago and is now lower — potential peak reversal (mean-reverting candidate)
- `ofi_slope = "flat"`: OFI stable at elevated level
- `ofi_slope = "rising"`: OFI still accelerating at signal time — trend continuation candidate

**Forward test hypothesis:** Do fills tagged `ofi_slope="declining"` (entry after OFI peak, into a reversion) show better post-fill outcomes than fills tagged `ofi_slope="rising"` (entry while buying pressure is still accelerating)? If Avery & Ward's "mean-reverting environments favor passive execution" transfers to crypto perps, declining-OFI entries should have lower adverse selection rates.

**Implementation:** ws_feed.py already tracks rolling buy_ratio. Compare buy_ratio at signal time vs buy_ratio N bars ago (e.g., N=4 × 30s = 2 minutes prior). If current < prior by threshold t, tag as "declining." (~3 lines.)

**Why this is not duplicated by existing tweaks:** Tweak 10 logs `imbalance_duration_s` (how long OFI has been elevated). Tweak 21 logs `ofi_slope_direction` (whether OFI is still rising or has started falling at entry). The two are complementary: a long-duration but declining OFI is a different condition from a short-duration still-rising OFI.

**Caveat:** Avery & Ward's finding is on CME traditional futures at daily/hourly resolution. ST2.0 signals on 5-minute candles for small-cap crypto alts. The regime concept (mean-reverting vs trending) may not transfer cleanly. The 2-minute lookback window (4 × 30s bars) is a starting assumption — threshold requires calibration on actual ST2.0 fills. Do NOT gate live trades on this without 30+ fill data points per slope category.

---

## Honest Caveats

1. **The three persistent gaps remain unresolved after Night 19.** Optimal cancel TTL, LOB depth replenishment speed, and optimal placement depth inside spread have each been searched for 7+ nights with no primary source found on crypto perp data. These gaps appear to be genuinely absent from accessible literature.

2. **Finding A (Avery & Ward) is on CME traditional futures.** The conceptual insight (regime misclassification as the driver of adverse fills) is new and relevant, but the paper does not test on crypto, does not provide calibrated thresholds, and does not show that OFI slope direction is the correct discriminator for regime type.

3. **Finding B (MDPI) is abstract-only.** The "2 hours after settlement" timing is a search-result summary quote, not a directly-read paper sentence. Treat as plausible corroboration of N15, not a new calibrated finding.

4. **The forward-test queue now stands at Tweaks 1–21, 0 deployed after 19 nights.** The binding constraint remains empirical, not theoretical. Tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines of shadow-logging and have been queued for multiple weeks. No further research nights are warranted until at least 30 tagged fills are available.

5. **SSRN 6344338 (Rajendran & Singaravelu, gradient boosting adverse selection predictor) is permanently inaccessible.** 19 consecutive nights of 403. The paper that would most directly calibrate a pre-entry adverse selection classifier for crypto HFT remains unreadable.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | N4 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (never repost) | N3/N6 | Queued |
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
| 20 | Log `lob_state` composite (spread + depth + imbalance → calm/mixed/stressed) | N18 | Queued (requires Tweaks 6 + 14 first) |
| **21** | **Log `ofi_slope_direction` at signal time (buy_ratio now vs 2 min prior → declining/flat/rising). Compare post-fill adverse selection by slope category.** | **N19** | **Queued (shadow only; ~3 lines)** |

---

## Research Series Status

| Category | Status |
|---|---|
| Pre-entry gates | 9 tweaks (N1, N2, N3, N7, N11, N15, N16, N17, N21 tonight) |
| At-entry placement | 4 tweaks (N4, N5, N8, N12) |
| Post-entry management / cancel | 4 tweaks (N6, N8, N9, N19) |
| Diagnostics only | 5 tweaks (N13, N14, N17, N18, N20) |
| Confirmed unresolvable via literature | Optimal TTL, LOB replenishment speed, placement depth inside spread |
| Blocked SSRN | 2 papers (6693260 + 6344338 — 19 consecutive nights) |

**Night 19 summary:** One new paper (Avery & Ward, July 2026 on CME futures) provides a regime-discrimination reframing: adverse fills are regime misclassification events, not execution mechanics failures. Limit-order execution is theoretically favored in mean-reverting environments. This grounds Tweak 21 (OFI slope direction at signal time as regime proxy). The MDPI temporal dynamics paper corroborates the existing cycle_phase finding across 812 symbols but is abstract-only. The literature is thinning — 19 nights, 21 queued tweaks, 0 deployed. No further research nights are warranted until shadow data exists.
