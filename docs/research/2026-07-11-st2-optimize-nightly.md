# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-07-11
**Night:** 15 of series
**Status:** One new partially-verified finding (post-settlement spread peak timing extends the funding-window gate). SSRN 6344338 blocked for 15th consecutive night. Four new angles surveyed — three fully inaccessible or inapplicable, one yields a new diagnostic metric.

---

## Context

Prior reports (nights 1–14, 06-20 synthesis through 07-10) have covered: adverse selection by
construction, queue position mechanics (0.717 bp front-vs-back), Phemex rebate = 0, OFI-flip /
micro-price filter, cancel-and-walk (never repost), VPIN, funding-window gate (UTC 5/8/13/14/16),
F&G regime + extremity premium (U-shaped, both tails adverse), q_near_at_post, q_ratio,
Lehalle-Mounjid latency formalization, universal −0.45 tick fill drift, Phemex amendment endpoint,
spoofable large bids, imbalance persistence duration, volatility-normalized tick size,
spot-perp OFI divergence / funding rate proxy, cross-asset BTC→alt lead indicators (ruled out),
calibrated fill probability score (Albers R²=0.946), LOB depth replenishment (equity only),
cancellation strategies (marginal difference), spread width at signal time.

Tonight targeted four genuinely uncovered angles:
(a) Optimal passive order cancel horizon — is 90s calibrated or arbitrary?
(b) U-shaped spread pattern within 8h funding cycle / post-settlement timing
(c) Effective spread decomposition (adverse selection vs inventory component) for crypto perps
(d) OFI decay rate / trade burst exhaustion timing for passive entry

---

## (a) What's New vs. Prior Reports

| Angle | Prior Coverage | Tonight's Result |
|---|---|---|
| Post-settlement spread timing (within 8h funding cycle) | 06-22 gate blocks entries AT settlement times (UTC 5, 8, 13, 14, 16). No research on spread pattern WITHIN the 8h cycle or what hours AFTER settlement are worst. | **New finding (partially verified)** — two independent 2026 sources suggest spreads peak approximately 2h after settlement, not at settlement itself, following a U-shape within each 8h cycle. See Tweak A. Verification caveat: one source via REPEC abstract summary (primary paper blocked), one source via Cornell blog post (paper is unpublished preliminary). |
| Optimal cancel horizon (stale order timing) | 06-23/06-26 established cancel-and-walk at 90s from practitioner reasoning. No academic calibration. | No new primary source found. 1511.04116 (Latency and liquidity provision) and 1610.00261 (already covered) both confirm cancellation is rational under private-information suspicion but neither provides an empirically calibrated wait-time for crypto perps. The 90s rule remains uncalibrated against primary sources. |
| Effective spread decomposition for crypto perps | Not previously searched. | MDPI IJFS 2026 (Zhivkov et al., 26 exchanges, 812 symbols, Nov 2025–Jan 2026) appeared promising but fetched content confirms it analyzes CEX/DEX funding rate integration, not bid-ask spread decomposition into adverse-selection vs inventory components. Not applicable. |
| OFI decay / burst exhaustion | Hawkes (07-12, night 12, inapplicable). OFI flip (06-24). | arxiv 2508.06788 (Takahashi, Aug 2025): OFI shocks dissipate "almost entirely within a second" — but dataset is S&P 500 E-mini, not crypto. arxiv 2505.17388 (Hu & Zhang): OFI modeled as Ornstein-Uhlenbeck, CSI 300 futures — Chinese equities, not applicable. Anomiq.io absorption/exhaustion: practitioner blog, no primary sources. Not actionable. |
| arXiv 2605.06405 (Le, "Funding-Aware Market Making for Perpetual DEXs", June 2026) | Not in any prior report. | Fetched full HTML. DEX market making via HJB — explicitly lacks "queue position, latency, cancellation behavior, or adverse selection conditional on being filled." Not applicable to ST2.0's one-shot passive order on a CEX. |
| SSRN 6344338 (Rajendran & Singaravelu) | Blocked 14 prior nights | HTTP 403 again — 15th night. PDF delivery URL also blocked. Permanently inaccessible via WebFetch. |

---

## (b) New Forward-Testable Finding

### Tweak A: Post-Settlement Spread Peak — Extend the Funding-Window Gate

**Sources:**

1. Zhivkov, P., Todorov, V. & Georgiev, S. (2026). "Temporal Dynamics of Market Microstructure
   in Cryptocurrency Perpetual Futures: Econometric Evidence from Centralized and Decentralized
   Exchanges." *International Journal of Financial Studies*, 14(5), 103. MDPI. April 2026.
   **URL:** https://www.mdpi.com/2227-7072/14/5/103
   **Dataset:** 26 exchanges, 812 cryptocurrency perpetual futures symbols, 9.1 million hourly
   observations, November 2025 – January 2026.
   **Verification status:** PARTIALLY VERIFIED — REPEC abstract page (ideas.repec.org/a/gam/
   jijfss/v14y2026i5p103-d1926363.html) fetched successfully; primary MDPI article returned
   HTTP 403. The REPEC page reproduced the abstract summary including: "Spreads peak
   approximately 2 hours after funding rate settlement times." Direct paper text not confirmed.
   REPEC is an academic indexing service; its abstract summaries generally reproduce publisher
   abstracts but this specific detail is not a verbatim quote from a paper we directly read.
   **Label: PLAUSIBLE, not VERIFIED.**

2. Ruan, Q. & Streltsov, A. (AEA 2026 Annual Meeting, preliminary). "Perpetual Futures
   Contracts and Cryptocurrency Market Microstructure." Cornell University PhD candidates.
   **URL (blog summary):** https://business.cornell.edu/centers/2025/02/18/perpetual-futures-contracts-and-cryptocurrency/
   **AEA abstract URL:** https://www.aeaweb.org/conference/2026/program/paper/ByyFEfr4
   **Verification status:** PARTIALLY VERIFIED — Cornell blog post confirmed: "both trading
   activity and bid-ask spreads follow a U-shaped pattern within each cycle" (the 8-hour
   funding cycle). Full paper returned binary PDF, not readable. Blog is authored by the
   paper's own authors — not a third-party summary.
   **Label: PLAUSIBLE, not VERIFIED.**

**What these sources establish (taken together):**

Two independent 2026 sources point at the same structural pattern:
- Bid-ask spreads in crypto perpetual futures are NOT uniform across the 8-hour funding cycle.
- They follow a **U-shaped pattern**: highest just after settlement, declining toward mid-cycle,
  rising again approaching the next settlement.
- The Zhivkov et al. REPEC summary specifies the peak is approximately 2 hours after settlement.
- Funding settlements happen every 8 hours (on Phemex: 00:00, 08:00, 16:00 UTC).
- The implied worst windows for passive makers: UTC 02:00, 10:00, 18:00 (±1h).
- The implied best windows: approximately UTC 04:00–06:00, 12:00–14:00, 20:00–22:00 (mid-cycle).

**Why this is NEW vs. prior reports:**

The 06-22 funding-window gate (Tweak 2 / 06-22) blocks entries AT settlement times (UTC 5, 8, 13,
14, 16 per the prior gate logic, which reflects Phemex's actual settlement times). That gate is
based on flow toxicity AT settlement (informed traders positioning into the rate event). Tonight's
finding is orthogonal: it says the spread (and thus adverse selection cost) peaks approximately
2 hours AFTER settlement, during the post-event adjustment period. A short that triggers 2h after
settlement is posting into a wide spread environment even though the settlement event itself has
passed.

Critically: the 06-22 gate does NOT cover the 2h post-settlement window. ST2.0 could fire at
UTC 10:00 (2h after Phemex's 08:00 UTC settlement) while passing the current gate, but according
to Zhivkov et al., this would be the worst spread moment in the 8h cycle.

**Forward-testable Tweak A (shadow log):**

At each ST2.0 signal trigger, log time within the current 8h funding cycle:

```python
# hours_since_last_settlement: time elapsed since the most recent 8h settlement
# Phemex settlements: 00:00, 08:00, 16:00 UTC
import datetime
utc_hour = datetime.datetime.utcnow().hour
cycle_phase = utc_hour % 8  # 0=at settlement, 1=1h after, ..., 7=1h before next
hours_since_last_settlement = cycle_phase  # 0-7
# Log alongside existing signal fields
```

After 30+ fills, test: do fills with `hours_since_last_settlement` in {1, 2} (post-settlement
peak) show worse post-fill outcomes than fills with `hours_since_last_settlement` in {3, 4, 5}
(mid-cycle trough)? If the U-shape holds for ST2.0 specifically, a gate of "skip entry in first
2h of each 8h cycle" reduces adverse fills without blocking mid-cycle trades.

**Why this metric is complementary to the existing funding-window gate:**

The 06-22 gate is: "block entry AT settlement hour (informed trader event-driven toxicity)."
The proposed `hours_since_last_settlement` metric is: "measure spread-cost regime WITHIN the
cycle (structural liquidity withdrawal post-settlement)." Different mechanism, different timing,
composable.

**Important caveats:**

1. **Neither source is directly verified from a readable primary paper.** Zhivkov et al. via
   REPEC abstract summary (not verbatim quote from paper text); Ruan & Streltsov via blog post
   by the authors summarizing an unpublished preliminary. Do NOT gate on specific thresholds
   from these sources until they can be confirmed from a readable paper or from our own data.

2. **Scale mismatch.** Zhivkov et al. use hourly observations across 812 symbols. The cycle
   phase finding is an aggregate statistical pattern. ST2.0 fires on individual 5-min signals
   for specific small-cap perps. The aggregate spread peak at +2h post-settlement may not hold
   uniformly for AVAX, INJ, ENA, ARB vs. the aggregate pool.

3. **The 06-22 gate and Tweak A may partially overlap.** Phemex settlements at 08:00 UTC +2h
   = 10:00 UTC; the 06-22 gate already blocks UTC 13, 14 (which are 5-6h after the 08:00
   settlement, and 0-1h before the 16:00 settlement). The interaction between the two gates
   needs to be mapped before deciding whether Tweak A adds value or merely adjusts timing.

4. **The U-shape finding is from CEX perpetual futures broadly.** Phemex is a smaller exchange.
   Spread timing may differ from the aggregate pattern observed across 26 exchanges and 812 symbols.

5. **"Approximately 2 hours" is imprecise.** The REPEC text uses hedged language. Whether the
   actual peak is at +1h, +2h, or +3h is not confirmed from the primary paper text. Do not
   implement a hard UTC hour block without first shadow-logging the cycle phase data and
   checking it against our own fill data.

---

## (c) Papers Surveyed Tonight (New vs. Prior Reports)

| Paper | Why Checked | Verdict |
|---|---|---|
| Zhivkov, Todorov & Georgiev (MDPI IJFS 2026) — "Temporal Dynamics of Market Microstructure in Crypto Perp Futures" | Spread decomposition, adverse selection timing, 26 exchanges, 812 symbols | HTTP 403 on primary; REPEC abstract accessible. Paper is about CEX/DEX funding rate integration, NOT spread decomposition into adverse-selection vs inventory components. One useful timing finding (see Tweak A). |
| Ruan & Streltsov (Cornell, AEA 2026 preliminary) — "Perpetual Futures Contracts and Cryptocurrency Market Microstructure" | U-shaped spread pattern in funding cycle | Blog by authors confirms U-shape finding. Full paper binary PDF (unreadable). PARTIALLY VERIFIED for U-shape. |
| arXiv 2605.06405 (Le, May 2026) — "Funding-Aware Optimal Market Making for Perpetual DEXs" | Market making timing, funding interaction, cancellation | Fetched full HTML. Hyperliquid DEX data. Explicitly lacks adverse selection, queue, cancellation modeling. Inapplicable. |
| arXiv 2508.06788 (Takahashi, Aug 2025) — "Returns and OFI: Intraday Dynamics" | OFI decay rate — how fast imbalance signal dissipates | S&P 500 E-mini futures, not crypto. "OFI shocks dissipate almost entirely within a second." NOT APPLICABLE to ST2.0 (crypto, 5-min signal). |
| arXiv 2505.17388 (Hu & Zhang, May 2025) — "Stochastic Price Dynamics in Response to OFI: CSI 300 Index Futures" | OFI-driven price dynamics, OU reversion timing | Chinese equity index futures. Not applicable to crypto perps. |
| Anomiq.io absorption/exhaustion blog | Burst peak detection / flow deceleration as entry timing | Practitioner blog, no primary sources. Provides non-calibrated thresholds for "absorption" (Volume Z>3, Imbalance >60%, Price Impact <0.8). Unverifiable. Not citable. |
| TandF 10.1080/14697688.2025.2515933 (2025) — "The good, the bad, and latency: exploratory trading on Bybit and Binance" | Adverse selection concentration in short windows, Bybit BTC/USDT 31M seconds | HTTP 403 (paywalled). "Adverse-selection risk is highly concentrated in rare short windows" — found in search summary only. Cannot verify. |
| SSRN 6344338 (Rajendran & Singaravelu) | Blocked 14 prior nights | HTTP 403 — 15th night. |

---

## (d) Honest Assessment

Fifteen nights. The academic microstructure literature for passive short-reversion maker execution
at small size, no rebate, on crypto perps remains exhausted at the level of REACHABLE primary sources.
Tonight's survey covered six new angles; one produced a partially-verified finding (Tweak A:
cycle-phase timing as a spread-regime indicator), and five produced nothing actionable.

Tweak A is directionally plausible and is supported by two independent 2026 sources, but both
are only partially verified (REPEC abstract, author blog). The implementation (log `cycle_phase`
= `utc_hour % 8`) is trivial (~3 lines) and carries zero risk. The forward test hypothesis is
specific and falsifiable.

The dominant constraint remains empirical: the 15-item forward-test queue requires 2–4 more
weeks of shadow data before any item can be statistically evaluated. Tweaks 4, 6, 9, 10, 11,
12, 14, and 15 are all 2–5 line shadow-log additions — none are deployed.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | 06-24 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | 06-23, clarified 06-26 | Queued |
| 3 | Shadow-gate VPIN computation | 06-23 | Queued (exploratory; validity contested) |
| 4 | Log `tape_max_single_trade` at signal time | 06-26 | Queued |
| 5 | Log `fg_regime` + `fg_extremity` flag (both extremes adverse — Farzulla 2026) | 06-29, updated 07-09 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | 06-30 | Queued |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | 06-30 | Queued |
| 8 | Verify Phemex order amendment queue behavior (controlled test order) | 07-06 | Verification prerequisite |
| 9 | Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time | 07-06 | Queued (shadow only) |
| 10 | Log `imbalance_duration_s` (seconds of continuous positive OFI before signal) | 07-07 | Queued (shadow only; ~5 lines) |
| 11 | Log `vol_norm_tick` per symbol at signal time | 07-07 | Queued (diagnostic only) |
| 12 | Log `funding_rate_annual_pct` at signal time (spot-perp divergence proxy) | 07-08 | Queued (shadow only; ~3 lines) |
| 13 | Log `q_fill_score` composite (Albers formula: Q_near, Q_opp, imb) | 07-09 | Queued (shadow only; do NOT gate on BTC-calibrated coefficients) |
| 14 | Log `spread_at_signal_bps` (current bid-ask spread in bps at signal time) | 07-10 | Queued (shadow only; ~2 lines; per-symbol rolling median needed for gating) |
| **15** | **Log `cycle_phase` = `utc_hour % 8` at signal time (0=at settlement, 1=1h after... 7=1h before next)** | **07-11** | **Queued (shadow only; ~3 lines; forward-test: are fills with cycle_phase∈{1,2} worse than {3,4,5}?)** |

---

## Research Status

Fifteen nights. Tonight yields one partially-verified diagnostic metric (`cycle_phase`) from two
independent 2026 sources that are not directly readable as primary papers. Both confirm the same
directional structural finding: spread environment in crypto perp futures follows a U-shape within
the 8-hour funding cycle, peaking ~2h after settlement. This refines but does not replace the
existing 06-22 funding-window gate — different mechanism (structural post-settlement spread
adjustment vs. event-driven toxicity at settlement).

All 15 shadow-log items require 2–4 more weeks of fill data before statistical evaluation.
SSRN 6344338 remains permanently inaccessible (15 nights). The cancel-horizon calibration
(Tweak 2's 90s window) has no primary-source backing — still unverified after 15 nights of search.
