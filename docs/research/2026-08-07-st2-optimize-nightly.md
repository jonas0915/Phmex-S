# ST2.0 Execution Optimization — Night 38
**Date:** 2026-08-07 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 37 Nights

N37 closed with: arXiv:2607.27070 (taker buy/sell ratio variance compression before crypto-perp liquidation cascades, Binance BTC, 7 macro events — Tweak 38: log `tape_buy_ratio_variance_30m`). Literature was declared "substantially saturated" at N33 after exhaustive coverage of: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, and taker buy/sell variance.

Tonight searched four new angles:
1. Informed-trading detection / tick-level adverse selection for passive limit order placement in crypto perp
2. Post-only repricing / cancel-replace adverse selection literature
3. Queue-priority effects on adverse selection (building on N37's ScienceDirect 403 result)
4. Short-term price reversal microstructure regime detection for passive maker fill timing

**Net result tonight: Two new papers verified (arXiv:2608.04373, Frontiers Blockchain 2026). Both applicable to adverse selection broadly, but neither yields a new forward-testable tweak for ST2.0. First paper is DEX-specific (mechanism does not transfer to Phemex CEX). Second is mildly corroborative of an existing finding. SSRN 6693260 (Lawrence Chang) still HTTP 403 — fifth attempt. Theoretical paper arXiv:2605.24242 verified but not applicable. No new actionable tweak tonight.**

---

## Papers Evaluated Tonight

### arXiv:2608.04373 — "Public Trader Identity: Adverse Selection and Return Predictability"
**Published:** August 2026. arXiv preprint.  
**URL:** https://arxiv.org/html/2608.04373  
**Dataset:** Hyperliquid (fully on-chain DEX). 10 perpetual contracts including BTC, ETH, SOL. 17.1 billion Level-4 messages. 14.3 million aggressive orders from 147,113 wallets. $84.3 billion notional traded. Primary window: July 2026. Replication: December 2025.

**Verification status: VERIFIED** — full HTML fetched and analyzed.

**Key finding (verbatim from fetch):**

> "Wallets ranked by the price movement following their aggressive orders retain that ordering across adjacent ten-day windows, with a rank correlation of 0.52."

Quantified results (from fetch):
- Toxic wallet features raise 1-second R² from 10.88% to 12.31% (13.2% relative gain, t=9.2)
- Markouts flat through the 15th ventile, rising to **3.11 basis points** in the top ventile
- Top-decile markout: 2.20 basis points in validation period
- Incremental R² at actual trade arrivals: 2.47 percentage points

**Core mechanism:** On Hyperliquid, all wallet addresses are public on-chain, enabling real-time identification of which wallets have historically generated the most adverse post-fill price movement. Persistent "toxic wallets" can be flagged and used to widen spreads or reduce depth at quote time.

**Why NOT applicable to ST2.0:**

Phemex is a centralized exchange where order flow is pseudonymous. Individual aggressor identities are not exposed in the L2 order book feed or trade stream. ST2.0's pipeline (ws_feed.py tape, exchange.py L2 snapshot) cannot identify which wallet is initiating the buying pressure that triggers the signal. The mechanism requires public wallet identity — a DEX-exclusive property.

**Indirect corroboration:** The 0.52 rank correlation in toxic-wallet persistence is consistent with the N37 finding (arXiv:2607.27070): informed/toxic buying tends to be monotone and persistent (low buy_ratio variance) rather than random and fluctuating. Both papers support the hypothesis that Tweak 38 (variance compression log) may separate informed-flow entries from routine absorption entries — even without wallet-level identification. However, this connection is inferential, not directly measured.

**Assessment: VERIFIED, not applicable (DEX-specific mechanism).**

---

### Frontiers in Blockchain — "Microstructure alpha: hierarchical learning and cross-asset transfer in cryptocurrency markets"
**Published:** 2026. Frontiers in Blockchain, doi: 10.3389/fbloc.2026.1811716  
**URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full  
**Dataset:** Binance. 6 cryptocurrencies: BTC, ETH, SOL, AVAX, LINK, DOT. Spot and perpetual futures. August 2025 – February 2026. Minute-level bars (~3.4 million total observations). Nine classical microstructure measures.

**Verification status: VERIFIED** — full HTML fetched and analyzed.

**Key findings (from fetch):**

1. **VPIN showed weak individual significance** in algorithmic crypto markets. Quote from analysis: "VPIN (order-flow toxicity) showed weak individual significance, suggesting order-flow imbalances carry limited information in algorithmic crypto markets."

2. **Corwin-Schultz spread proxy:** The only measure with statistically significant negative coefficient (−0.0182), interpreted as "wider minute-level ranges are followed by lower returns, consistent with spread-induced drag." This is about return prediction, not passive fill quality.

3. **Cross-asset transfer failure:** "Models trained on one cryptocurrency fail to generalize to others." However, "models transfer best to the same-asset opposite venue (spot ↔ futures)," suggesting spot LOB features could in principle inform perp entries on the same asset.

4. **No strategy survives realistic costs:** At Binance VIP-0 fees (10 bps spot, 2–5 bps perp) plus slippage, "all net Sharpe ratios are deeply negative" at 5-minute rebalancing frequencies.

5. **Regime dependency (from fetch):** "Microstructure signals vanish in high-volatility regimes — precisely when passive orders face adverse selection."

**What this means for ST2.0:**

The VPIN weakness finding is the most notable. Across 3.4 million minute-level observations on 6 crypto assets including AVAX (which is in ST2.0's universe), VPIN showed "weak individual significance" as a return predictor. This corroborates the prior-night conclusion (present since N1 synthesis) that "VPIN remains unverified as a maker gate for crypto perp." The paper does not study passive fill quality directly — it studies forward return prediction from microstructure features. But the weakness of VPIN in this context is consistent with N1–N38's running finding.

The spot→futures transfer finding: in principle, checking whether aggressive buying in BTC spot is preceding or contemporaneous with the buying detected in the perp tape could add cross-venue signal context. This angle is already partially captured by existing "cross-asset transfer" work covered in prior nights (no new primary source here).

**No new forward-testable tweak from this paper.** The VPIN finding is corroborative, not additive.

**Assessment: VERIFIED, mildly corroborative, no new tweak.**

---

### arXiv:2605.24242 — "Explicit Signal-Adaptive Sequential Optimal Execution Quotes"
**Published:** May 2026. arXiv.  
**URL:** https://arxiv.org/abs/2605.24242  
**Dataset:** None — theoretical paper.

**Verification status: VERIFIED (abstract and structure confirmed).**

**Summary:** Develops HJB-based closed-form solutions for dynamic limit order quoting with signal-dependent drift, price impact, inventory risk, and execution risk. No empirical data, no crypto content, no passive fill quality analysis.

**Assessment: VERIFIED, not applicable (pure theory, no adverse selection or crypto perp content).**

---

### SSRN 6693260 — Lawrence Chang (attempt #5)
**Status:** HTTP 403 Forbidden — fifth consecutive failed access attempt. Still unverified.

**Recommendation:** Try accessing via ResearchGate, Google Scholar author profile, or direct email to the author's institutional page (if identifiable). The paper's claimed finding (flow-adjusted bid-absorption proxy) remains the most likely new primary source — access is the only blocker.

---

### Papers Searched But Not Fetched (Already Covered or Not Applicable)

- **arXiv:1610.00261 — "Limit Order Strategic Placement with Adverse Selection Risk"**: 2016 paper (traditional equities). Already in scope of prior nights' literature sweep.
- **arXiv:1511.04116 — "Latency and liquidity provision in a limit order book"**: 2015 paper, HFT latency focus. Not applicable to ST2.0 (no speed edge).
- **USPTO 11676205 — "Dynamic peg orders"**: Patent document, not academic primary source.
- **PSU Honors Thesis**: Not a primary academic source.

---

## New Forward-Testable Tweak Tonight

**None.** No new verified, applicable paper tonight. The literature space for ST2.0's execution problem appears genuinely exhausted at this search depth.

The following indirect corroboration was found but does not merit a new tweak number:

- arXiv:2608.04373's finding (rank correlation 0.52 in toxic-wallet persistence on Hyperliquid) is consistent with the N37 hypothesis that monotone, low-variance buying pressure is an adverse selection marker — not because wallets are identifiable on Phemex, but because the underlying mechanism (informed buyers sustaining directional pressure) should produce the same tape signature (low buy_ratio variance) regardless of venue type. This reinforces Tweak 38 (log `tape_buy_ratio_variance_30m`) but does not introduce a new angle.

---

## Honest Caveats

1. **Literature is saturated.** 38 consecutive search nights have now covered all major angles in the micro-price, adverse selection, order flow, and maker fill quality literatures for crypto perpetual futures. Search results are consistently returning papers already evaluated in N1–N37.

2. **arXiv:2608.04373 is DEX-specific.** Despite a large, recent dataset and strong findings on toxic-flow persistence, the public wallet identity mechanism is exclusive to on-chain CLOBs. No transferable execution rule exists for Phemex CEX.

3. **Frontiers VPIN finding is corroborative, not additive.** VPIN weakness in crypto perp has been the consensus finding since N1. The Frontiers paper adds evidence (3.4M observations, Aug 2025–Feb 2026, including AVAX) but no new insight.

4. **SSRN 6693260 is the remaining open item.** If accessible, it could produce a new tweak (flow-adjusted ask-absorption ratio log, Tweak 37 — already conditional). Fifth 403 in a row. Try ResearchGate or author page.

5. **42 tweaks queued, 0 deployed across 38 nights.** Tweak accumulation has no value without fill labeling. Priority tweaks 4, 6, 9, 10, 11, 12, 14 are the deployment target. Tweaks 36–38 (log-only, 1–5 lines each) can be added in the same session.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N37): **4 [elevated], 6, 9, 10, 11, 12, 14**  
No new tweak added tonight.  
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer depth check).

---

## Night 38 Bottom Line

**No new actionable execution tweak tonight.** Two new papers verified:

1. **arXiv:2608.04373** (Hyperliquid, Aug 2026): Toxic-wallet flow persists with 0.52 rank correlation across 10-day windows, raising 1-second return R² by 13.2% (t=9.2). DEX-specific mechanism (public wallet identity); not applicable to Phemex CEX. Indirectly corroborates Tweak 38 (low buy_ratio variance as informed-flow marker).

2. **Frontiers Blockchain 2026** (Binance, 6 cryptos including AVAX, Aug 2025–Feb 2026): VPIN shows "weak individual significance" as a return predictor in algorithmic crypto markets. Corroborates existing conclusion that VPIN is an unreliable gate for crypto perp adverse selection. No new tweak.

SSRN 6693260 (Lawrence Chang) — 403 again (attempt #5). This remains the one open unverified source that could produce a genuinely new finding (Tweak 37, flow-adjusted ask-absorption log). Try ResearchGate or author institutional page.

**Recommendation unchanged:** Deploy priority tweaks 4, 6, 9, 10, 11, 12, 14. Add Tweaks 36 (1 line), 37 (conditional, 3–4 lines), 38 (conditional on tape buffer check, 3–5 lines) in the same session. Night 38: 42 tweaks queued, 0 deployed.
