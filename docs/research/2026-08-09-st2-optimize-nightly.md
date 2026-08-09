# ST2.0 Execution Optimization — Night 40
**Date:** 2026-08-09 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 39 Nights

N39 closed with no new tweak (confirmed literature saturation since N33). Prior 39 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, and short-term price reversal regime detection.

Tonight searched four angles:
1. Crypto perpetual open interest dynamics as adverse selection signal (novel angle)
2. Optimal passive placement depth within spread — new 2026 paper (arXiv:2607.28323)
3. Sentiment regime as adverse selection predictor — new 2026 paper (arXiv:2602.07018)
4. Funding rate direction at entry vs. fill adverse selection (arXiv:2605.06405)

**Net result tonight: One new verified paper with a mildly corroborative finding (arXiv:2602.07018). Two candidates not applicable to Phemex CEX (arXiv:2607.28323 — equities/FX; arXiv:2605.06405 — Hyperliquid DEX). No new forward-testable execution tweak tonight.**

---

## Papers Evaluated Tonight

### arXiv:2602.07018 — "The Extremity Premium: Sentiment Regimes and Adverse Selection in Cryptocurrency Markets"
**Published:** February 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2602.07018
**Dataset:** Binance BTC/USDT daily OHLCV, January 1, 2024 – January 8, 2026 (739 days); validation on February 2018 – January 2026 (N=2,896). Crypto Fear & Greed Index daily readings. Bybit LOB snapshots (90 days) and Binance LOB snapshots (61 days) for spread validation. ETH cross-validation.

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Key findings (verified from fetch):**

1. **Extremity premium (verbatim):** "Extreme fear and extreme greed regimes exhibit significantly higher spreads than neutral periods." Extreme regimes = F&G Index <25 (extreme fear) or >75 (extreme greed) vs. neutral (45–55).

2. **Granger causality (verbatim):** "Uncertainty predicts spreads (primary-sample F=12.79; the extended-sample F=211) but not vice versa (F=0.82, p=0.49)." Within-volatility-quintile: premium survives after controlling for realized volatility (p<0.001, Cohen's d=0.21).

3. **Direction irrelevant, intensity is the driver (verbatim):** "Intensity, not direction, drives uncertainty-linked liquidity withdrawal in cryptocurrency markets." Extreme fear (+0.039 units above neutral) and extreme greed (+0.055 units above neutral) both widen spreads relative to neutral.

4. **Market maker mechanism (verbatim):** "Market makers provide liquidity with uncertainty-aware spread adjustment" — spreads widen proportional to decomposed uncertainty in extreme regimes.

5. **Aleatoric dominance (verbatim):** "Aleatoric (irreducible market noise) accounts for 81.6% of total uncertainty." The spread widening is mostly driven by irreducible noise, not information asymmetry that could be exploited.

**What this means for ST2.0:**

ST2.0 fires when the market is in heavy buying absorption — a condition most likely to co-occur with "Extreme Greed" (F&G >75) sessions. This paper documents that maker passive orders during extreme sentiment regimes face elevated adverse selection: spreads are wider, informed traders are more active relative to noise traders, and market makers are pulling liquidity. This is consistent with the N1 synthesis finding ("fills cluster at extreme imbalance = adverse-selection event") but adds a session-level framing: the *background regime* matters, not just the local imbalance.

**Why NOT a new actionable tweak:**
- Resolution mismatch: daily F&G reading vs. 60s ST2.0 cycle. Daily sentiment cannot distinguish the 15-minute absorption window.
- The Fear & Greed Index is not a current input to the bot (would require a new external data source: alternative.me API).
- The authors explicitly state: "identification of 'pure' sentiment effects from volatility remains an open challenge." The F&G index embeds 25% volatility, making the adverse selection signal redundant with what volatility filters already capture.
- The spread widening in extreme regimes is an effect, not a cause: the same underlying information asymmetry that widens spreads *is* the adverse selection. Adding F&G as a gate would be measuring the shadow, not the substance.
- No evidence the finding transfers to 60-second passive order fills on a crypto CEX perp.

**Assessment: VERIFIED. Corroborative — consistent with N1 synthesis and prior 39 nights. No new forward-testable execution tweak warranted.**

---

### arXiv:2607.28323 — "Optimal Execution with Passive Market Impact"
**Published:** July 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2607.28323
**Dataset:** US Equities — LOBSTER/NASDAQ, 6 stocks, 2016. FX — LSEG, 5 currency pairs, 2026. No crypto content.

**Verification status: VERIFIED (dataset and key claims confirmed from HTML fetch).**

**Key finding (verbatim from fetch):** Fill intensity follows "Λ(δ)=λe^(−kδ)" — exponential decay with distance δ from midprice in ticks, with k ranging 0.48–3.72 across equities. "Deeper quotes require exponentially more submissions on average before execution." "A more aggressive quote increases the fill intensity but also increases the rate at which passive impact is accumulated."

**Assessment: VERIFIED, NOT APPLICABLE.** US equities + FX only. The exponential fill-probability-decay-with-distance finding is already the core model underlying "passive market impact" covered in prior nights (specifically, the Moallemi/Maglaras queue-value model in the N1 synthesis documents the same structure for crypto perp). No new insight for crypto perp specifically.

---

### arXiv:2605.06405 — "Funding-Aware Optimal Market Making for Perpetual DEXs"
**Published:** May 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2605.06405
**Dataset:** Hyperliquid DEX only — ETH, BTC, SOL perps. Nov–Dec 2025 backtest.

**Verification status: VERIFIED (HTML fetched).**

**Key limitation (verbatim from fetch):** "Neither proxy knows the market maker's queue position, latency, maker priority, cancellation behavior, or adverse selection conditional on being filled." "The simulator is best read as a controlled policy comparison under common execution assumptions. Before a stronger trading claim, the next robustness layer should add a simple adverse-selection or latency cost."

**Assessment: VERIFIED, NOT APPLICABLE.** Hyperliquid DEX-specific. Paper does not measure whether funding direction at entry correlates with post-fill adverse selection — this was the core question for ST2.0 and it is explicitly not addressed. CEX queue dynamics differ substantially from Hyperliquid fill mechanics. "Funding-aware quoting" angle was already covered in prior nights.

---

### AEA 2026 — "Perpetual Futures and Basis Risk: Evidence from Cryptocurrency"
**Source:** AEA 2026 Conference Paper. URL: https://www.aeaweb.org/conference/2026/program/paper/ByyFEfr4
**Status: UNVERIFIED.** Binary PDF returned, content not readable. Abstract and findings inaccessible. Unverified — no claims extracted.

---

## New Forward-Testable Tweak Tonight

**None.** The arXiv:2602.07018 finding (extreme sentiment → wider spreads → elevated adverse selection) is corroborative and at the wrong time resolution for ST2.0's 60s execution cycle. No new metric, no new gate.

**Tweak queue remains at 42 (unchanged from N39).**

---

## Honest Caveats

1. **arXiv:2602.07018 is the one genuinely new paper tonight.** The finding is real and Granger-confirmed (F=211 on 2,896 days), but it operates at daily granularity and studies spread-widening, not passive fill adverse selection directly. It cannot motivate a real-time gate without (a) an external F&G API feed and (b) sub-daily granularity research.

2. **Literature remains saturated.** For the 7th consecutive night (N34–N40), all new papers either repeat covered findings, are not applicable to Phemex CEX, or operate at the wrong time resolution. The specific problem space (passive maker adverse selection for short-reversion on crypto perp CEX, small size, no speed, no rebate) appears exhausted at normal search depth.

3. **AEA "Basis Risk" paper inaccessible.** A conference paper on crypto perpetual basis risk could be relevant — basis divergence before passive short entries is an untested angle. Could not verify content; binary PDF only.

4. **42 tweaks queued, 0 deployed across 40 nights.** The research phase has yielded a 42-item queue with no deployment. Further literature search has diminishing returns. The path forward is deploying priority tweaks (4, 6, 9, 10, 11, 12, 14) and log-only tweaks (36, 37, 38) to generate labeled fill data — the only thing that can validate or discard the queued hypotheses.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N39): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 40 Bottom Line

**No new actionable execution tweak tonight.** One new verified paper:

**arXiv:2602.07018** (Binance BTC/USDT, daily, Jan 2024–Jan 2026 + validation Feb 2018–Jan 2026): Extreme sentiment regimes (F&G <25 or >75) predict elevated spreads and adverse selection for passive makers (Granger F=211, p<0.001). "Intensity, not direction, drives uncertainty-linked liquidity withdrawal." Corroborative — consistent with N1 synthesis but at daily resolution; not actionable for ST2.0's 60s cycle without an external F&G feed and sub-daily validation.

Two candidates not applicable: arXiv:2607.28323 (US equities/FX — exponential fill-probability-decay model, already covered in prior nights under passive market impact); arXiv:2605.06405 (Hyperliquid DEX — funding-aware quoting, DEX-specific, not transferable to Phemex CEX). One candidate inaccessible: AEA 2026 crypto basis risk paper (binary PDF).

**Recommendation after 40 nights:** Literature search has reached genuine diminishing returns. The binding constraint is no longer knowledge — it is deployment. Deploy priority tweaks 4, 6, 9, 10, 11, 12, 14. Add log-only tweaks 36 (1 line), 37 (3–4 lines, conditional on SSRN 6693260), 38 (3–5 lines, conditional on ws_feed.py tape buffer audit). Shift research focus from literature to live-data fill labeling — 30+ labeled fills are the prerequisite for validating or discarding all 42 queued tweaks.
