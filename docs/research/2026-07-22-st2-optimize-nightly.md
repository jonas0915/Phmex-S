# ST2.0 Execution Optimization — Night 26
**Date:** 2026-07-22 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 25 Nights

N25 closed with: arXiv:2606.15715 (Barone & Lillo, Hyperliquid — visible sustained flow raises adverse selection for hidden passive fills) confirming Tweak 4 priority, SSRN 6344338/6551572 still blocked at 23 consecutive nights. Tonight searched four new angles: (1) intraday time-of-day adverse selection patterns in crypto perpetual futures, (2) altcoin-specific microstructure vs BTC/ETH maker fill quality, (3) ask-side LOB depth thinning as a predictive signal, (4) optimal passive maker TTL/cancellation timing. Two findings are new material; two angles were near-complete misses.

**Summary of new material tonight:**
- arXiv:2602.07018 (Levi, "The Extremity Premium: Sentiment Regimes and Adverse Selection in Cryptocurrency Markets," 2026) — VERIFIED (abstract and full paper fetched). Extreme sentiment regimes correlate with statistically higher spreads, interpreted as elevated adverse selection risk. Daily signal only; fragile to model specification.
- Ruan & Streltsov (SSRN 4218907, "Perpetual Futures Contracts and Cryptocurrency Market Quality") — PARTIALLY VERIFIED. SSRN PDF blocked; key findings confirmed from two independent Cornell Business/hub pages. U-shaped adverse selection pattern within 8-hour funding cycles: worst conditions near funding settlements (00:00, 08:00, 16:00 UTC), best in mid-cycle.

**Confirmed misses or repeats tonight:**
- Altcoin vs BTC maker fill quality — Frontiers paper (2026) covers altcoin microstructure at 1-min frequency but is diagnostic only; no maker-strategy execution findings by asset tier.
- Ask-side depth thinning / LOB fragility — arXiv:2506.05764 studies mid-price prediction, not execution or directional depth asymmetry. No new actionable material beyond Tweak 24 (ask_depth_fragility, queued N24).
- Optimal TTL / cancellation timing — no new literature found. Gap remains unresolved (first noted N6, still open at N26).
- SSRN 6344338 — 24th consecutive night blocked.

---

## Finding A — arXiv:2602.07018 VERIFIED: Extreme Sentiment Regimes Associate with Higher Adverse Selection Risk

**Source:** Elad Levi. "The Extremity Premium: Sentiment Regimes and Adverse Selection in Cryptocurrency Markets." arXiv, February 2026.
**URL:** https://arxiv.org/abs/2602.07018 (HTML: https://arxiv.org/html/2602.07018v1)
**Dataset:** Bitcoin daily OHLCV + Crypto Fear & Greed Index, 2018–2026 (N = 2,896 daily observations). Validation on Ethereum and 6-of-7 historical market cycles.

**Verified quotes (from abstract, directly fetched):**

> "Extreme fear and extreme greed regimes exhibit significantly higher spreads than neutral periods — the 'extremity premium.'"

> "within-volatility-quintile comparisons show a premium (p < 0.001, pooled volatility-demeaned Cohen's d = 0.21 — a post-hoc, exploratory test, as the pre-specified within-quintile endpoint does not survive multiple-testing correction; raw pooled extreme-vs-neutral d = 0.40)"

> "Granger causality runs from uncertainty to spreads (primary-sample F = 12.79)"

> "The effect replicates on Ethereum and across 6 of 7 market cycles."

> "the premium is sensitive to functional form: regression controls absorb regime effects, while nonparametric stratification preserves them"

**What the five sentiment regimes are:**
- Extreme Fear: F&G < 25
- Fear: 25–44
- Neutral: 45–55
- Greed: 56–75
- Extreme Greed: > 75

**Core mechanism:** The paper interprets extreme sentiment periods (either direction) as associated with higher informed-trader activity. When the crowd commits strongly to a directional view, the probability of informed trading increases, and market makers respond by widening spreads as adverse-selection compensation.

**Quantified premium:** Cohen's d = 0.40 (raw, extreme vs neutral); d = 0.21 (within-volatility-quintile). For the Extreme Greed regime specifically, the paper reports ~15% wider implied spreads relative to neutral.

**What this means for ST2.0:**

ST2.0 shorts into buy absorption — a short precisely during what looks like a greed/buying episode. If the Extreme Greed regime (F&G > 75) co-occurs with the signal, the spread is ~15% wider and informed buying is statistically more present. This means:
1. The passive sell posted into heavy buying is statistically more likely to be against informed flow in an Extreme Greed regime.
2. The Extreme Fear regime is also elevated (d = 0.40), which is surprising — but the mechanism differs (forced seller flow adversely selects resting buys, not shorts).
3. For ST2.0 specifically, the risk concentrates in **Extreme Greed** where the buy-absorption signal is most likely driven by informed/momentum flow that continues rather than reverts.

**What this does NOT mean:** The paper is Bitcoin daily data. It cannot be calibrated to Phemex altcoin perp intraday fills. The d = 0.21 within-quintile effect does not survive Bonferroni correction. This is a directional indicator only — not a gate with a known precision.

**Forward-testable tweak → Tweak 27 (shadow log, 1–2 lines):**
Log `fg_regime` at signal time (e.g., "extreme_greed" / "greed" / "neutral" / "fear" / "extreme_fear") using the daily Crypto Fear & Greed Index value available via free API. After collecting 30+ tagged fills, check whether adverse fills cluster in extreme regimes vs neutral. If so, skip entry during Extreme Greed or Extreme Fear as a daily-level pre-filter.

**Critical limitations:**
1. Daily Bitcoin data — not intraday, not altcoins, not perps specifically.
2. The effect is fragile: parametric regression controls absorb it; only nonparametric stratification preserves it.
3. Cohen's d = 0.21 (within-quintile) fails Bonferroni correction — the pre-specified endpoint did not survive multiple-testing adjustment.
4. No mechanism connecting daily F&G regime to individual fill adverse selection within that day.

---

## Finding B — SSRN 4218907 PARTIALLY VERIFIED: U-Shaped Adverse Selection Within Each 8-Hour Funding Cycle

**Source:** Qihong Ruan, Artem Streltsov. "Perpetual Futures Contracts and Cryptocurrency Market Quality." SSRN 4218907 (May 2022, updated).
**Primary URL:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4218907 — **HTTP 403, blocked.**
**Secondary source used for verification:** Cornell Business Centers (https://business.cornell.edu/centers/2025/02/18/perpetual-futures-contracts-and-cryptocurrency/) and Cornell SC Johnson hub (https://business.cornell.edu/hub/2024/02/20/the-emerging-market-cryptocurrencies-perpetual-contracts/). Both are university-hosted factual summaries of the paper.
**Dataset:** High-frequency order book data, 2017–2023. Natural experiment: Huobi's perp contract termination in October 2021.

**Verified quotes (from Cornell Business Centers page, secondary source):**

> "both trading activity and bid-ask spreads follow a U-shaped pattern within each cycle"

> "Market makers react by widening bid-ask spreads, increasing trading costs" [around funding settlements]

**Additional confirmed claim from Cornell hub summary:**

> "Spot market quality follows a U-shaped pattern over perpetual contracts' eight-hour funding cycles. Increased informed trading occurs during funding settlement hours and periods of larger funding fee magnitudes."

**What the U-shape means for ST2.0:**

Funding settlements on Phemex (and most perp exchanges) occur at **00:00, 08:00, and 16:00 UTC**. The U-shaped pattern within each 8-hour cycle means:
- **Hours 0–1 after settlement (e.g., 00:00–01:00, 08:00–09:00, 16:00–17:00 UTC):** High activity, widest spreads, highest adverse selection. Informed traders are most active as they position around or immediately following the funding settlement.
- **Mid-cycle (~3–5 hours after settlement, e.g., 03:00–05:00, 11:00–13:00, 19:00–21:00 UTC):** Lower activity, tighter spreads, lowest adverse selection within the cycle.
- **Hours 7–8 before next settlement (cycle end):** Spreads widen again as funding arbitrageurs reposition ahead of the next settlement.

**Internal consistency check:** The project's PULLBACK_SESSION_GATE already blocks UTC hours {5, 8, 13, 14, 16} when enabled. Hours 8 and 16 are **exactly the Phemex perp funding reset times** — the gate was blocking these without explicitly knowing the Ruan & Streltsov mechanism. This is independent corroboration that hours 8 and 16 UTC are structurally worse for passive entries. The gate was right for the wrong reason.

**What this means for ST2.0 specifically:**

Posting a passive sell into buy absorption at 00:01 UTC or 08:01 UTC (immediately after a funding reset) is in the worst window: spreads are widest, informed traders are most active. The buy absorption ST2.0 detects near these hours is more likely to be informed flow (funding arbitrage or momentum following the reset) than the speculative squeeze that reverts.

Mid-cycle (hours 3–5 after reset) is the theoretically better window: quieter informed activity, tighter spreads, more likely a genuine short-term speculative squeeze that reverts.

**Forward-testable tweak → Tweak 28 (shadow log, 2 lines):**
Log `hours_since_funding` = (current UTC hour × 60 + current minute) mod 480, divided by 60 — a fractional measure of position within the 8-hour cycle (0 = just after settlement, 8 = just before next). After 30+ tagged fills, check whether adverse fills cluster at values < 1.5h or > 6.5h (near funding events) vs 2–6h (mid-cycle). If the pattern holds, add a gate: skip entry within 90 minutes of a funding reset hour.

**Critical limitations:**
1. **Primary source not directly read.** Findings confirmed from two independent Cornell-hosted secondary sources (not the full paper text). Quantitative details (exact hours, bps differentials) cannot be verified. Mark as PARTIALLY VERIFIED.
2. The paper studies **spot market quality** as affected by perp contracts — not passive fill adverse selection on the perp market itself. The translation requires one inference step: if informed traders are active on spot near funding settlements, they are likely active on perp as well (funding arbitrage works on both sides simultaneously).
3. 2017–2023 data (Huobi era). Microstructure may differ on current Phemex (different participant mix, lower volumes, different latency regime).
4. No per-asset or per-liquidity-tier breakdown visible in the summary. Whether the pattern is stronger for BTC vs altcoin perps is unknown.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 27 | Log `fg_regime` at signal time using daily Crypto F&G Index value. After 30+ tagged fills: do adverse fills cluster in extreme regimes (< 25 or > 75)? If yes, add daily-level skip gate. | Finding A (arXiv:2602.07018, VERIFIED — but daily BTC data, not intraday perp-specific) | Queued — log only | 1–2 lines |
| 28 | Log `hours_since_funding` = float position within the current 8-hour funding cycle (0 at 00:00/08:00/16:00 UTC, peaks at 8). After 30+ tagged fills: do adverse fills cluster at cycle edges vs mid-cycle? If yes, add 90-minute funding-window exclusion gate. | Finding B (SSRN 4218907, PARTIALLY VERIFIED — secondary source) | Queued — log only | 2 lines |

---

## Honest Caveats

1. **Finding A (arXiv:2602.07018):** Fully fetched and directly quoted. BUT: daily BTC data only; d = 0.21 within-quintile does not survive Bonferroni correction; parametric controls absorb the regime effect. Treat as a directional indicator, not a precise gate. Tweak 27 should remain shadow-log-only until we have tagged fills per regime.

2. **Finding B (SSRN 4218907):** PARTIALLY VERIFIED — university-hosted secondary sources confirm the U-shaped pattern and informed-trading-at-settlement findings, but the full paper is blocked. No quantitative thresholds (exact bps, precise hours) can be cited from primary source. Implement Tweak 28 as a log only; do not add a hard gate until primary source is read or empirical data from Tweak 28 confirms the pattern on Phemex.

3. **Altcoin microstructure angle was a near-complete miss.** The Frontiers 2026 paper confirms altcoins have wider spreads and higher price impact (AVAX, DOT) but is diagnostic only — no maker-execution findings. This gap remains: no literature directly addresses whether altcoin perp passive fill adverse selection rates differ from BTC in a way exploitable by a small maker.

4. **TTL/optimal cancellation gap persists at Night 26.** No literature found on this in any of the 26 nights. This appears to be a genuine underdocumented area for the specific problem shape (small passive directional maker on crypto perp altcoin at minutes-scale hold).

5. **SSRN 6344338 blocked for 24 consecutive nights.** No new access route found.

6. **Internal consistency note on Finding B:** The existing PULLBACK_SESSION_GATE blocks UTC hours 8 and 16 — both are funding reset hours. The gate was built on session performance data, not this paper. The convergence is partial empirical confirmation that the paper's mechanism may operate on Phemex. Hours 5, 13, 14 are also gated (US/EU open overlap) — a different mechanism but possibly correlated with funding arbitrage activity.

7. **28 tweaks queued, 0 deployed across 26 nights.** Tweaks 27 and 28 are each 1–2 lines. The recommendation from N20–N25 remains: implement priority tweaks 4, 6, 9, 10, 11, 12, 14 first. Do not add more to the queue before collecting 30+ tagged fills per diagnostic variable. Research has now run 26 nights with no implementation — the bottleneck is execution, not knowledge.

---

## Cumulative Forward-Test Queue (28 Tweaks)

Priority tweaks (unchanged): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweaks 27 and 28 added tonight.
Full queue archived in N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), and above (Tweaks 27–28).

---

## Night 26 Bottom Line

Two new findings. Finding A (arXiv:2602.07018, VERIFIED): extreme sentiment regimes (F&G > 75 or < 25) associate with ~15% wider spreads and elevated adverse selection in Bitcoin markets — forward-testable as a daily-level log gate (Tweak 27), but daily data and fragile statistics limit confidence. Finding B (SSRN 4218907, PARTIALLY VERIFIED via Cornell secondary sources): bid-ask spreads and informed trading follow a U-shaped pattern within each 8-hour perpetual funding cycle, with worst adverse selection near settlement hours (00:00, 08:00, 16:00 UTC) and best conditions mid-cycle — testable as a 2-line `hours_since_funding` log (Tweak 28). The finding is consistent with the existing PULLBACK_SESSION_GATE blocking hours 8 and 16 UTC from empirical performance data.

**Recommendation unchanged from N20–N25:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweaks 27 and 28 are 1–2 lines each and can be added in the same session. Do not continue adding to the research queue until 30+ tagged fills per variable are collected. Night 26: 28 tweaks queued, 0 deployed.
