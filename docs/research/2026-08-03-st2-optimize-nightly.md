# ST2.0 Execution Optimization — Night 35
**Date:** 2026-08-03 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 34 Nights

N34 closed with: arXiv:2602.00776 (Bieganowski & Ślepaczuk, Binance Futures 5 assets, VWAP-to-mid diagnostic Tweak 35, OFI extremity Tweak 35a). The MDPI paper on temporal dynamics of crypto perp microstructure (MDPI 2227-7072/14/5/103) had been blocked HTTP 403 for **four consecutive nights** — labeled "UNVERIFIED, do not act."

Tonight's search covered four new angles:
1. Intraday time-of-day adverse selection patterns for crypto perp maker fills
2. Volatility-regime-conditional passive fill quality in crypto perp
3. LOB depth profile / shape beyond best-N as adverse selection predictor
4. Post-fill realized spread decomposition in crypto perp context

**Net result tonight: One meaningful status upgrade (MDPI paper partially verified via IDEAS/RePec abstract), yielding one new forward-testable diagnostic tweak. All other candidates are non-applicable or previously covered.**

---

## Papers Fetched and Evaluated Tonight

### MDPI 2227-7072/14/5/103 — PARTIALLY VERIFIED via IDEAS/RePec Abstract
**Full title:** "Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures: Econometric Evidence from Centralized and Decentralized Exchanges"  
**Authors:** Petar Zhivkov, Venelin Todorov, Slavi Georgiev  
**Institution:** Bulgarian Academy of Sciences (Institute of Information and Communication Technologies; Institute of Mathematics and Informatics); Angel Kanchev University of Ruse  
**Published:** MDPI International Journal of Financial Studies, 2026, vol. 14, issue 5, article 103  
**Dataset:** 26 cryptocurrency exchanges (centralized + decentralized), 812 perpetual futures symbols. Period: November 2025 through January 2026. 9.1 million hourly observations. 53 overlapping seven-day rolling windows.  
**Primary source access:** MDPI page still returns HTTP 403 Forbidden (5th consecutive night). Abstract metadata accessed via IDEAS/RePec index page (ideas.repec.org/a/gam/jijfss/v14y2026i5p103-d1926363.html).

**Verification status: PARTIAL.** The claim below appears in the IDEAS/RePec abstract metadata. The extraction model may have paraphrased rather than quoted verbatim from the IDEAS/RePec page. Full paper methods and tables remain inaccessible. This is a status upgrade from four nights of "UNVERIFIED" (could not access any content at all), not full verification.

**Key finding extracted from abstract metadata:**

> "Intraday spread patterns are statistically significant and linked to funding rate settlement mechanics, with spreads peaking approximately two hours after standard settlement times."

**What this means for ST2.0:**

Phemex standard funding settles at 00:00, 08:00, 16:00 UTC (8-hour intervals, standard for crypto perp CEX). If the finding holds, spreads peak approximately:
- ~02:00 UTC (= 7:00 PM PT)
- ~10:00 UTC (= 3:00 AM PT)
- ~18:00 UTC (= 11:00 AM PT)

For ST2.0, which posts a passive SELL at the best ask: a wider spread at entry time means the passive sell is physically further from the mid-price. Two competing effects:

1. **Lower fill probability** — the passive ask is further from the bid, fewer market buys reach it
2. **Potentially more adverse selection if filled** — spread widening is driven by informed/directional post-funding flow; a fill during this window means a buyer committed to executing even at a worse price, which is a signal of informed buying pressure (adverse for a passive short)

The N1 synthesis noted "US daytime 0% WR" (7 trades, too small to be significant). The funding-settlement spread-peak windows partially overlap with US daytime (10:00 UTC = early morning PT, 18:00 UTC = late morning PT). If the spread-peak effect is real, it provides a structural mechanism for the US-daytime weakness observed in our small sample.

**Additional findings from the abstract metadata:**
- Two-tiered market structure: centralized exchanges tightly integrated; decentralized exchanges fragmented.
- Integration gaps ranging from −0.041 to 0.222 across exchanges.
- Structural break testing: no discrete regime shifts, only gradual evolution.
- Near-integrated volatility in only 24.5% of windows.
- Mid-tier exchanges show stronger price discovery leadership than size-based hierarchy predicts.

These additional findings are directionally consistent with existing knowledge but don't yield new execution tweaks beyond the intraday timing point.

**Critical limitations:**
1. **MDPI still 403 — methods unverified.** The abstract summary was extracted via IDEAS/RePec, not from the full paper. Internal methodology, statistical tests, and tables for the "2-hour post-settlement spread peak" claim are unconfirmed.
2. **26-exchange average.** The finding is an average across centralized + decentralized venues. Phemex's specific spread dynamics may differ substantially from the cross-exchange average (especially since CEX-DEX integration is stated to be fragmented).
3. **Hourly granularity.** The study uses hourly data. ST2.0 operates on 60-second cycles. Intraday spread peaks at hourly resolution may not translate cleanly to minute-level fill quality patterns.
4. **812 symbols averaged.** Effects on specific low-liquidity altcoin perps (INJ, AVAX, ARB — comparable to ST2.0's universe) may be stronger or weaker than the cross-symbol average. Low-liquidity symbols may show more pronounced post-funding spread peaks.
5. **Directionality of adverse selection effect is inferred.** The paper measures spread widening, not adverse selection on passive fills specifically. That wider spread correlates with adverse selection for passive makers is the standard microstructure inference (Glosten-Milgrom), not directly measured in this paper.

---

### Other Candidates Evaluated Tonight (All Non-Applicable)

**arXiv:2407.16527 — "The Negative Drift of a Limit Order Fill" (DeLise)**  
US Treasury Bond futures only. No crypto perp data. Already covered in N29 as the "DeLise Bernoulli model" (fills cluster when price moves adversely). Not new.

**arXiv:2409.12721 — "Market Simulation under Adverse Selection" (Lalor & Swishchuk)**  
Dataset: Chicago Mercantile Exchange — ES, NQ, CL, ZN futures. No crypto content. Core finding: "fill probabilities and adverse fills can significantly affect performance." Theoretically consistent with ST2.0's known problem but no crypto-specific quantification. Not applicable.

**arXiv:2506.05764 — "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books"**  
Bybit BTC/USDT, 100ms–multi-second snapshots. Studies prediction model architecture (logistic regression vs DeepLOB). Headline finding: "better inputs matter more than stacking another hidden layer." Focused on return prediction model selection, not adverse selection or passive fill quality. Not applicable.

**Multicoin Capital blog (Applebaum & Sengupta, Feb 2026) — "Adverse Selection Rules Everything Around Me"**  
Practitioner opinion piece on DeFi adverse selection (MEV, JIT liquidity, private relays). Six frameworks all DeFi/DEX specific (encrypted mempools, commit-reveal, Flashbots). Not applicable to Phemex CEX perp. No quantified maker fill metrics.

**ScienceDirect — "High-frequency dynamics of Bitcoin futures" (2025)**  
HTTP 403 blocked. Title references Mixture of Distributions Hypothesis and Intraday Trading Invariance — methodology-focused paper, not adverse selection or passive fill quality. Not pursued further.

---

## New Forward-Testable Tweak Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 36 | **Funding-window hour log.** At signal fire time, log `entry_utc_hour` (0–23) alongside fill/adverse outcome. After 30+ fills: do adverse fills cluster in the post-funding-settlement windows (01:00–03:00, 09:00–11:00, 17:00–19:00 UTC)? Cross-reference with the existing N1 "US daytime 0% WR" (7 trades, n too small) to see if the structural mechanism (spread-peak post-funding) explains the timing pattern. If clustering confirmed: candidate time-of-day block gate for those 6 hours/day. Does NOT require any exchange API call — current UTC hour is a 1-line Python add (`import datetime; entry_utc_hour = datetime.datetime.utcnow().hour`). | Zhivkov, Todorov, Georgiev. "Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures." MDPI IJFS 2026, vol. 14(5):103. Dataset: 26 exchanges, 812 symbols, hourly, Nov 2025–Jan 2026. PARTIAL VERIFICATION via IDEAS/RePec abstract — full paper 403 blocked, 5th night. | Queued — log only | 1 line |

---

## Honest Caveats

1. **Partial verification only.** The core claim ("spreads peak ~2 hours after settlement") appears in the IDEAS/RePec abstract metadata, but the full paper methodology and tables remain inaccessible. The WebFetch extraction model may have paraphrased. Treat as "plausible, abstract-supported" not "peer-review-confirmed."

2. **26-exchange average vs Phemex.** Even if the finding is robust on average, Phemex's specific post-funding spread behavior is unknown. The paper's CEX/DEX integration fragmentation finding suggests per-venue variance is significant.

3. **Hourly data → minute execution gap.** A spread peak measured hourly does not guarantee that within the peak hour, every minute is equally adverse. The signal is coarse.

4. **Tweak 36 is 1 line, log-only.** The cost is negligible; the hypothesis is plausible and partially backed. It can be added in any priority-tweak deployment session.

5. **40 tweaks queued, 0 deployed across 35 nights.** The binding constraint remains unchanged: deploy priority tweaks 4, 6, 9, 10, 11, 12, 14 to collect 30+ tagged fills per diagnostic variable. No amount of logged variables helps without fills to label.

6. **MDPI paper should be retried.** Five nights of 403. Try a different access method (Google Scholar PDF link, institutional proxy, ResearchGate) in a future session rather than the MDPI direct URL.

---

## Cumulative Forward-Test Queue (40 Tweaks)

Priority tweaks (unchanged from N20–N34): **4 [elevated], 6, 9, 10, 11, 12, 14**  
Tweak 36 added tonight.  
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), above (Tweak 36).

---

## Night 35 Bottom Line

One meaningful status upgrade: the MDPI Zhivkov et al. (2026) paper — blocked 4 consecutive nights as "UNVERIFIED" — is now **partially verified via IDEAS/RePec abstract**. The claim "intraday spread patterns are statistically significant and linked to funding rate settlement mechanics, with spreads peaking approximately two hours after standard settlement times" appears in the abstract metadata for a paper covering 26 exchanges, 812 symbols, hourly, Nov 2025–Jan 2026. For Phemex (funding at 00:00/08:00/16:00 UTC), the implied adverse windows are ~02:00, 10:00, 18:00 UTC. Tweak 36: log `entry_utc_hour` (1 line, zero cost) to test whether adverse fills cluster in these windows. Full paper 403 still; claim is abstract-level only.

All other candidates tonight: not applicable (CME/Treasury futures, DeFi practitioner, BTC prediction model architecture, 403 blocked). No new verified finding beyond the MDPI abstract upgrade.

**Recommendation unchanged:** Deploy priority tweaks 4, 6, 9, 10, 11, 12, 14. Add Tweak 36 (1 line) in the same session. Night 35: 40 tweaks queued, 0 deployed.
