# ST2.0 Execution Optimization — Night 64
**Date:** 2026-09-05 | **Focus:** Maker execution quality, passive fill adverse selection
**Prior coverage:** N1–N63 (63 nights); all arXiv q-fin.* through August 2026 screened; SSRN universally 403-blocked

---

## What's New vs. Prior 63 Nights

N63 (2026-09-04) specifically flagged tonight as the estimated earliest meaningful September 2026 arXiv sweep ("~September 5–7"). All four categories fetched. Simultaneously: 2 additional new-to-corpus sources screened via web search and 1 practitioner blog evaluated.

### Sources Evaluated Tonight

| Source | Type | Status |
|--------|------|--------|
| arXiv q-fin.TR September 2026 | Academic listing | VERIFIED — 0 submissions |
| arXiv q-fin.ST September 2026 | Academic listing | VERIFIED — 0 submissions |
| arXiv q-fin.PR September 2026 | Academic listing | VERIFIED — 1 paper (arXiv:2609.01323, already screened N62, NOT APPLICABLE) |
| arXiv q-fin.CP September 2026 | Academic listing | VERIFIED — 6 papers, all options pricing / implied-vol / portfolio math — NOT APPLICABLE |
| arXiv:2608.04373 (Barone et al.) | Peer-reviewed | NEW TO CORPUS — NOT APPLICABLE |
| Frontiers fbloc.2026.1811716 | Peer-reviewed | NEW TO CORPUS — NOT APPLICABLE |
| aligrithm.com "Adverse Selection Is Adverse Selection" | Practitioner blog | NEW TO CORPUS — UNVERIFIED METHODOLOGY |
| Multicoin Capital "Adverse Selection Rules Everything" | Practitioner blog | NEW TO CORPUS — NOT APPLICABLE |

---

## Sources Detail

### arXiv q-fin.CP September 2026 — 6 papers, NOT APPLICABLE
**Verified from:** https://arxiv.org/list/q-fin.CP/2026-09  
Papers: arXiv:2609.00332, 2609.00438, 2609.01323, 2609.02014, 2609.04087, 2609.03552.  
All are numerical methods for options pricing, rough volatility, hedging, or portfolio replication. Zero microstructure or execution content. NOT APPLICABLE.

---

### arXiv:2608.04373 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Public Trader Identity: Adverse Selection and Return Predictability"  
**Source URL:** https://arxiv.org/abs/2608.04373  
**Status: VERIFIED** — abstract fetched directly.

**Key finding:** On a DEX with public wallet identities, "adding the live activity of the highest-ranked wallets to a standard anonymous benchmark raises the out-of-sample R² for one-second returns to 12.31%, a 13.2% gain." Wallet informativeness is a "persistent attribute" with 0.52 rank correlation across ten-day windows. 17.1 billion messages, 14.3 million aggressive orders, 147,113 wallets, $84.3B taker notional.

**Why NOT applicable:** Study is exclusively on a DEX with on-chain wallet address transparency — the mechanism (ranking wallets by historical informativeness and tracking their live orders) requires public counterparty identity. Phemex CEX provides no such data. No passive maker fill content. NOT APPLICABLE.

---

### Frontiers fbloc.2026.1811716 — NEW TO CORPUS, NOT APPLICABLE
**Title:** "Microstructure alpha: hierarchical learning and cross-asset transfer in cryptocurrency markets"  
**Source URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full  
**Data:** Binance spot + perpetual futures, 6 cryptocurrencies (BTC, ETH, SOL, AVAX, LINK, DOT), 3.4M+ minute-level obs, August 2025–February 2026.  
**Status: VERIFIED** — full page fetched.

**Key verified findings:**
- "The Corwin-Schultz spread proxy emerges as the most statistically significant predictor" of short-term returns, with **negative** predictive power (wider spread → lower next-minute return). Outperforms VPIN.
- VPIN (order flow toxicity): "modest predictive content...relatively weak...information asymmetries differ in crypto versus traditional markets."
- After Binance VIP-0 fees (10 bps spot, 4–10 bps perp): "All net Sharpe ratios are deeply negative" (−52 to −10 range); 124–204× daily turnover destroys edge.
- Cross-asset transfer: "Models do not transfer between cryptocurrencies but transfer well between spot/futures of the same asset."

**Why NOT applicable as new tweak:** Confirms fee-trap (already well-established in corpus from arXiv:2502.18625 and synthesis N0). No passive maker placement findings. No adverse selection mitigation content. The VPIN weakness corroborates why OFI-based entry gating is limited, consistent with prior reports. NOT APPLICABLE as a new execution tweak.

---

### aligrithm.com — "Adverse Selection Is Adverse Selection" — PRACTITIONER BLOG, UNVERIFIED
**Source URL:** https://aligrithm.com/adverse-selection-is-adverse-selection-porting-fast-fills-are-bad-fills-to-fx-and-futures/  
**Data claimed:** Polymarket (prediction market CLOB), EURUSD FX, Bund futures.  
**Status: PRACTITIONER BLOG — methodology NOT verified; no sample size, no peer review.**

**Core claim** (blog author's words, approximately):  
"The faster the fill, the worse the adverse selection, in every order book."

**Reported fill quality by time-to-fill bucket (unverified, non-crypto data):**

| Fill Speed | Reported Fill Quality |
|---|---|
| Market orders (immediate) | −0.72 |
| Limit orders, filled < 1 min | −0.31 |
| Limit orders, filled > 10 min | +0.43 |

Units not defined by the blog. No statistical methodology disclosed.

**Relevance assessment:** The general direction — fast passive fills are adversely selected — is already established in the peer-reviewed corpus for crypto CEX perp via arXiv:2502.18625 ("orders with negative subsequent five-second returns are highly likely to fill"). The blog adds an operationalized **time-to-fill bucket framing** not seen in prior nightly reports. However:
1. Source is not peer-reviewed.
2. Data is Polymarket/EURUSD/Bund — not crypto CEX perp.
3. The specific thresholds (<1 min = bad, >10 min = good) are UNVERIFIED for Phemex.
4. "Fill quality" values are undefined in units.

**Verdict: UNVERIFIED — consistent with corpus direction, adds framing only.**  
The operationalized implication for ST2.0 is zero-cost: **log time_to_fill on every ST2.0 fill** (ms from post timestamp to exchange fill confirmation). Once 30+ fills accumulate, bucket by fill speed and compute post-fill 5-min markout per bucket. This would verify or refute the fast-fill = adverse-selection claim on actual Phemex data. Zero trading risk.

---

### Multicoin Capital "Adverse Selection Rules Everything Around Me" — NOT APPLICABLE
**Source URL:** https://multicoin.capital/2026/02/17/adverse-selection-rules-everything-around-me/  
**Status: VERIFIED** — page fetched directly.

**Key finding:** DEX/blockchain-specific piece. Focuses on mempool transparency, sandwich attacks, and AMM adverse selection. Proposed mitigations (maker cancellation windows, JIT liquidity, retail price improvement APIs) all require exchange-level implementation, not accessible to a passive maker on Phemex CEX. NOT APPLICABLE.

---

## New Forward-Testable Tweaks Tonight

**Zero new confirmed tweaks from peer-reviewed sources.**

**One UNVERIFIED instrumentation suggestion (not a tweak, a measurement change):**

> **Log `time_to_fill` on every ST2.0 fill** — record the elapsed seconds between the post-only order submission timestamp and the fill confirmation from the exchange. Bucket by speed (<60s, 60–300s, >300s) and compute post-fill 5-min markout per bucket. This makes the "fast fills are bad fills" hypothesis testable on Phemex data. Zero trading risk. Marginal log line.

This is NOT a new confirmed tweak — it is a data-collection step that could validate or invalidate an existing corpus assumption. Cost: ~5 lines of Python. No parameter changes.

---

## Honest Caveats

1. **September 2026 arXiv remains very sparse (day 5 of month).** q-fin.CP has 6 papers (all pricing math). q-fin.TR, q-fin.ST still empty. q-fin.PR: 1 non-applicable paper. Expected submission accumulation: September 8–12 after the September 1 blackout period ends.

2. **0 new peer-reviewed findings.** 2 new academic papers screened (arXiv:2608.04373, Frontiers 2026) — both NOT APPLICABLE. 2 practitioner blogs screened — one NOT APPLICABLE (Multicoin/DEX), one consistent with corpus direction but methodology UNVERIFIED (aligrithm.com).

3. **The aligrithm.com time-to-fill framing** adds practical operationalizability to an academic finding already in the corpus (arXiv:2502.18625). It does not constitute a new verified source. If "time_to_fill" is already logged somewhere in the ST2.0 codebase, this is moot — check before adding.

4. **SSRN still universally blocked.** 6 IDs remain unscreened (4677989, 5323703, 6344338, 6693260, 6772279, 7162966).

5. **ScienceDirect S1386418125000229** ("Queuing and inventories in limit order markets") still 403-blocked.

6. **The empirical gap is unchanged.** No paper in 64 nights has measured OFI-flip decay or passive fill adverse selection at 60-second granularity on a crypto CEX perp. Internal bot data remains the only path.

---

## Standing Recommendation (Night 18 of suspension advisory — unchanged)

**Suspend nightly literature sweeps.** Resume ~September 8–12 when September 2026 arXiv submissions accumulate in earnest.

**Immediate action (zero trading risk):** Deploy Tweak 45 (spread gate logging — `spread_pct` at every entry attempt) and add `time_to_fill` logging on fills. Both are pure instrumentation — no parameter changes, no trading risk, and they unblock threshold calibration for Tweaks 44 and 45 plus the fast-fill hypothesis.

**Then deploy:** Priority tweaks 4, 6, 9, 10, 11, 12, 14 from the existing queue.

---

## Cumulative Forward-Test Queue (44 confirmed + 1 candidate — unchanged)

**Priority tweaks (unchanged N20–N64): 4 [elevated], 6, 9, 10, 11, 12, 14**  
**Tweak 44 (confirmed N59):** L2 3-metric regime check — top-20 levels, spread/depth/imbalance, tercile-based calm/mixed/stressed. BTC: skip calm. ETH: log tier, no hard skip. Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp, 2023–2026).  
**Candidate Tweak 45:** Standalone spread gate — skip entry when bid-ask spread ≥ 75th pct rolling per-symbol. Source: arXiv:2602.00776 (Binance Futures perp, 2022–2025).  
**Conditional Tweak 43:** Composite LightGBM toxicity gate (SSRN:6344338, blocked).  
Full queue archived: N22 (Tweaks 1–22), N23 (23), N24 (24–26), N26 (27–28), N27 (29), N28 (30, 30a), N29 (31, 31a), N30 (32, 32a), N31 (33), N32 (34, 34a), N34 (35, 35a), N35 (36), N36 (37), N37 (38), N59 (44).

---

## arXiv Coverage as of Night 64

- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.TR September 2026: EMPTY (0 submissions as of Sep 5)
- q-fin.ST September 2026: EMPTY (0 submissions as of Sep 5)
- q-fin.PR September 2026: 1 paper (arXiv:2609.01323 — not applicable)
- q-fin.CP September 2026: 6 papers (arXiv:2609.00332, 00438, 01323, 02014, 03552, 04087 — all pricing math, not applicable)

---

## Night 64 Bottom Line

**0 new actionable findings from verified sources.** 8 sources evaluated:

- **arXiv q-fin.TR/ST September 2026:** VERIFIED EMPTY.
- **arXiv q-fin.PR September 2026:** 1 paper (already screened N62), NOT APPLICABLE.
- **arXiv q-fin.CP September 2026:** 6 papers, VERIFIED, all NOT APPLICABLE (pricing math only).
- **arXiv:2608.04373** (DEX wallet identity): NEW TO CORPUS. NOT APPLICABLE.
- **Frontiers fbloc.2026.1811716** (Binance perp micro alpha, Aug 25–Feb 26): NEW TO CORPUS. NOT APPLICABLE as new tweak; confirms fee-trap and spread predictor dominance.
- **aligrithm.com practitioner blog** (fast fills are bad fills): NEW TO CORPUS. UNVERIFIED methodology, non-crypto data. Consistent with corpus; suggests logging `time_to_fill` on fills as zero-cost instrumentation.
- **Multicoin Capital blog** (DeFi adverse selection): NEW TO CORPUS. NOT APPLICABLE.

**Recommendation (18th consecutive night):** Stop searching until September 8–12. Add `time_to_fill` logging (5 lines of Python). Deploy Tweak 45 spread logging immediately.
