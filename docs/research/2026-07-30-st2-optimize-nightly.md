# ST2.0 Execution Optimization — Night 32
**Date:** 2026-07-30 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 31 Nights

N31 closed with: arXiv:2607.09230 Jeon (composite L2 stress score, Tweak 33). Tonight searched four angles not previously covered: (1) arXiv:2511.00390 DeltaLag — BTC→altcoin lead-lag for perp entry timing; (2) cross-asset microstructure transfer at minute frequency (Frontiers 2026); (3) sunshine trading / visible-buy-flow effects on passive ask-side competition (arXiv:2606.15715 Hyperliquid); (4) cascade EWS as an adverse-selection gate (arXiv:2607.27070).

**Summary of new material tonight:**

- **Frontiers 2026 (Pindza, Binance 6-crypto spot+perp, Aug 2025–Feb 2026) — VERIFIED via HTML fetch.** Core finding: microstructure features do NOT transfer cross-cryptocurrency at minute frequency ("block-diagonal structure" — same-asset opposite venue transfers, cross-asset does not). "No strategy survives realistic exchange fees." Directly contradicts any proposed BTC lead-lag gate for altcoin ST2.0 entries. New to this series.

- **arXiv:2606.15715 (Barone & Lillo, Hyperliquid DEX perp, Jul 2025–Mar 2026) — VERIFIED via abstract + HTML fetch.** Core finding: visible buy TWAP programs "elicit liquidity provision: while active, displayed depth rises and the book tilts toward the absorbing side." Hidden passive sells facing a visible buyer see more competing sellers pile in at the ask — queue position degrades during the exact buy-absorption episode that triggers ST2.0's signal. Also: "hidden metaorders executed alongside already-visible same-direction TWAP flow incur higher permanent costs: adverse-selection costs shift toward non-announcers." New to this series.

- **arXiv:2607.27070 (Binance BTCUSDT, 7 cascade events, 2022–2025) — VERIFIED via HTML fetch.** No reliable per-event cascade early-warning signal. "Single-venue, single-variable early-warning claims in crypto perpetual markets are fragile by construction." Argues AGAINST adding a cascade-detection gate to ST2.0. New to this series.

**Dead ends tonight:**
- arXiv:2511.00390 DeltaLag: US equities daily returns only; no crypto perp content. Not applicable.
- MDPI 2227-7072/14/5/103 (funding window): 403 Forbidden — 3rd consecutive blocked night.
- Tiniç & Sensoy (spread decomposition): 403 Forbidden.
- SSRN 6344338: 32nd consecutive night blocked.
- SSRN 6693260: 32nd consecutive night blocked.

---

## Finding A — Frontiers 2026 VERIFIED: Cross-Crypto Microstructure Transfer Fails; No Strategy Survives Fees

**Source:** Edson Pindza. "Microstructure alpha: hierarchical learning and cross-asset transfer in cryptocurrency markets." *Frontiers in Blockchain*, 10.3389/fbloc.2026.1811716. University of South Africa, Pretoria.
**URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full
**Dataset:** Binance spot and perpetual futures, six cryptocurrencies (Bitcoin, Ethereum, Solana, Avalanche, Chainlink, Polkadot). Date range: August 2025 through February 2026. Approximately 3.4 million minute-level observations (285,000 bars per asset–venue pair).
**Access:** Full HTML fetched directly. Peer-reviewed (Frontiers in Blockchain).

**Verified quotes (directly fetched from HTML):**

> "Models trained on one cryptocurrency do not transfer to others, although they transfer well between the spot and futures venues of the same asset."

> "The heatmap displays a clear block-diagonal structure: models transfer best to the same-asset opposite venue (spot futures), with meaningfully lower correlations across underlying cryptocurrencies."

> "All net Sharpe ratios are deeply negative"

> "no strategy survives realistic exchange fees"

> "gradient-boosted models overfit severely under proper leakage controls"

**What this paper establishes for ST2.0:**

**1. Cross-asset gating is not supported.** The most frequently proposed extension of ST2.0 is "gate altcoin entries on BTC order flow direction" — i.e., only post when BTC's microstructure also shows bearish signals. This paper runs exactly that test (cross-cryptocurrency model transfer at minute level) and finds it fails empirically. Models trained on BTC microstructure features have "meaningfully lower correlations" when applied to altcoins vs. same-asset cross-venue transfer. Adding a BTC signal gate to altcoin ST2.0 entries is not supported by this evidence.

**2. Same-asset spot/perp transfer does work.** The block-diagonal structure confirms that the same asset's spot microstructure transfers to its perp (and vice versa). For ST2.0, this means: if AVAX perp shows buy absorption, checking AVAX spot OFI for confirmation would have empirical backing — but cross-asset (BTC's OFI predicting AVAX perp behavior) would not. This requires spot WebSocket feeds not currently in ST2.0's infrastructure.

**3. Fee drag confirmation.** "No strategy survives realistic exchange fees" at minute-level micro signals. Binance VIP-0 = 2 bps maker / 5 bps taker (10–14 bps round-trip). Phemex = 0% maker / ~5 bps taker. The fee drag conclusion from the N1 synthesis (scalping is fee-trapped) is corroborated by independent empirical evidence in a 2026 peer-reviewed paper.

**4. Range-based spread proxy: most robust signal.** "Range-based spread proxies and realised volatility the most robust [microstructure features]." Wide minute-level price range (Corwin-Schultz proxy) is the strongest return predictor — and it's bearish for returns. For a SHORT strategy, this suggests that entering when the recent minute-level range is wide (high volatility) has directional support. But the paper's caveat is explicit: no strategy survives fees even with these signals. The directional content is real but not exploitable at retail fees via minute-level turnover.

**What this does NOT address:**

The paper studies return prediction (alpha), not passive fill adverse selection directly. The cross-asset transfer failure at the return-prediction level is evidence against a BTC lead-lag gate, but does not rule out BTC order flow IMPROVING fill quality (vs return direction) for altcoin ST2.0 entries — this is a different hypothesis. However, the mechanism by which a cross-asset signal would improve fill quality (not return prediction) without improving return prediction is unclear.

**Forward-testable implication → Tweak 34 (anti-recommendation — no code):**

Do NOT add a cross-asset BTC-direction gate to altcoin ST2.0 entries. The empirical evidence (Binance 6-crypto spot+perp, Aug–Feb 2026) shows cross-cryptocurrency microstructure transfer fails at minute frequency. If such a gate is added, it is untested speculation; this paper provides prior evidence against it.

Conversely, a same-asset spot/perp confirmation gate (e.g., altcoin's own spot market showing matching absorption) has empirical backing but requires infrastructure not currently available (spot WebSocket feeds per altcoin symbol).

**Critical limitations:**
1. Binance spot+perp — not Phemex perp. Participant mix and fee structure differ.
2. 6 major liquid cryptocurrencies. ST2.0 trades mid-cap altcoin perps (INJ, AVAX, ARB) which may have different cross-asset dynamics from BTC/ETH/SOL.
3. Paper studies return prediction; the cross-asset failure applies to return forecasting — not specifically to fill quality or adverse selection conditional on a signal.
4. Solo-authored paper from UNISA; not yet independently replicated to my knowledge.
5. Frontiers in Blockchain is a peer-reviewed open-access journal but of lower impact factor than top-tier journals. Results should be treated as suggestive, not definitive.

---

## Finding B — arXiv:2606.15715 VERIFIED: Buy Absorption Attracts Competing Passive Sellers — Ask-Side Depth Growth Degrades Queue Position

**Source:** Davide Barone, Fabrizio Lillo. "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid." arXiv:2606.15715.
**URL:** https://arxiv.org/abs/2606.15715
**Dataset:** Hyperliquid — fully on-chain limit order book for cryptocurrency perpetual futures. 201 perpetual markets. Date range: July 28, 2025 to March 23, 2026. 641M+ fills, 4.3M hidden metaorders, 465K visible TWAP executions.
**Access:** Abstract fetched directly; HTML also fetched. arXiv preprint.

**Verified quotes (directly from abstract):**

> "visible TWAP programs elicit liquidity provision: while active, displayed depth rises and the book tilts toward the absorbing side, the more so the larger the announced order"

> "Hidden metaorders executed alongside already-visible same-direction TWAP flow incur higher permanent costs: adverse-selection costs shift toward non-announcers"

> "Visible TWAPs face lower execution costs than comparable hidden metaorders and leave a smaller permanent price impact"

> "Sunshine trading theory predicts that publicly disclosing trading intentions can reduce adverse selection and attract liquidity provision, lowering execution costs"

**What this paper establishes for ST2.0:**

The paper's primary mechanism: a visible buy program (TWAP) causes "displayed depth rises and book tilts toward the absorbing side." In the buy-TWAP context, "absorbing side" is the buy/bid side — the TWAP attracts more passive sells (other market makers competing to sell into the visible buyer).

For ST2.0, which fires on buy absorption (elevated buy tape, bid-heavy LOB), the mechanism transfers as follows:
- ST2.0's signal fires BECAUSE large, concentrated buying is happening
- That same concentrated buying attracts OTHER passive sellers to the ask queue
- ST2.0 posts a passive sell into an ask queue that is simultaneously GROWING due to the same buying episode
- Result: ST2.0 is further back in queue at the precise moment it posts than the static ask depth snapshot (Tweak 24) would suggest

This is a NEW angle on the queue-position problem (identified in the N1 synthesis as -0.775 bp back-of-queue vs -0.058 bp front). The synthesis noted that ST2.0 posts-and-waits ~20s → likely back-of-queue. The sunshine paper provides a mechanism for WHY queue position degrades specifically during the signal trigger: buy absorption attracts competing sellers.

**The additional finding** — "adverse-selection costs shift toward non-announcers" — applies to hidden buyers competing with visible TWAP buyers. The direction for ST2.0 is opposite (ST2.0 is a hidden SELL). However, the asymmetry is directionally consistent: when a determined, visible buyer is present, the hidden sell (ST2.0) faces a counterparty who is committed to executing — making fills driven by that buyer adversely selected (price moving up before reversion).

**Forward-testable implication → Tweak 34a (shadow log, 3–4 lines):**

Log `ask_depth_delta_60s` = change in total best-5-level ask-side quoted depth over the 60 seconds before signal fire time:

```python
# Using already-buffered ob snapshots from ws_feed.py
ask_depth_now = sum(ob["asks"][:5][i][1] for i in range(len(ob["asks"][:5])))
ask_depth_60s_ago = sum(ob_snapshot_60s_ago["asks"][:5][i][1] for i in range(len(...)))
ask_depth_delta_60s = ask_depth_now - ask_depth_60s_ago
```

Log `ask_depth_delta_60s` alongside fill/miss/adverse outcome. After 30+ fills:
- Do adverse fills cluster at `ask_depth_delta_60s > 0` (ask depth growing = more sellers competing)?
- Is `ask_depth_delta_60s` correlated with time-to-fill (Tweak 31 variable)?
- Cross-reference with Tweak 24 (`ask_depth_fragility`, static depth): does the growth rate add information beyond the level?

If adverse fills cluster when ask depth is growing (consistent with the sunshine mechanism): candidate gate (block or delay entry when ask depth growth rate exceeds threshold). If no clustering: the static depth snapshot (Tweak 24) is sufficient.

**Distinction from prior tweaks:**
- Tweak 24: static `ask_depth` level at signal time
- Tweak 31a: `ask_refill_rate` — how fast asks recover AFTER being hit
- Tweak 34a: `ask_depth_delta_60s` — how fast asks are GROWING in the period BEFORE signal fire (pre-signal supply buildup)

These are orthogonal. Tweak 24 measures absolute depth; Tweak 31a measures post-hit recovery speed; Tweak 34a measures pre-signal supply accumulation. All three could be true simultaneously and provide complementary information.

**Critical limitations:**
1. **Hyperliquid DEX — not Phemex CEX.** On Hyperliquid, TWAP order intentions are visible on-chain from inception (the "sunshine" mechanism depends on this). Phemex CEX does not expose individual order types publicly. The mechanism transfers at the LOB-dynamics level (buy absorption → competing sellers add depth) but not the visibility mechanism (you can't detect a TWAP specifically on Phemex).
2. **Large institutional metaorders.** The 4.3M statistical metaorders and 465K TWAPs represent institutional-scale execution, not ST2.0's $5–30 margin retail-size passive sell. Queue competition dynamics from institutional TWAP programs may not scale down to retail-size passive orders.
3. **The "adverse-selection cost" finding** applies specifically to hidden orders in the SAME direction as the TWAP. For ST2.0 (sell), the TWAP in question would be a buy — opposite direction. The paper does not directly study what happens to the passive ask-side when a visible buy TWAP is active, beyond "depth rises."
4. arXiv preprint — not peer-reviewed at the time of this search. Authored by Fabrizio Lillo (established researcher, Bologna + SNS Pisa), which increases credibility of the methodology.

---

## Finding C — arXiv:2607.27070 VERIFIED: No Reliable Per-Event Cascade EWS — Don't Add a Cascade Gate

**Source:** "Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades." arXiv:2607.27070.
**URL:** https://arxiv.org/html/2607.27070
**Dataset:** Binance USD-margined perpetual futures, BTCUSDT, seven cascade events (May 2022, Nov 2022, Aug 2024, Dec 2024, Feb 2025, Apr 2025, Oct 2025). 1-min klines, 5-min metrics dumps.
**Access:** HTML fetched directly. arXiv preprint.

**Verified findings (from HTML fetch):**

> "Single-venue, single-variable early-warning claims in crypto perpetual markets are fragile by construction."

> "Price carries the critical-slowing-down signature in five of seven events but is silent in exactly the two sudden-news (tariff) shocks."

> "compression of taker order-flow variance" shows statistical significance across cascades (p ≈ 5×10⁻⁶) "but represents only a population-level precursor, not a per-event alarm."

**What this establishes for ST2.0:**

The proposal to add a "cascade detection gate" (block ST2.0 entries when cascade onset is detected) is empirically not viable: the one replicable pattern ("order-flow variance compression") is a population-level statistical regularity, not a per-event alarm that fires reliably before each cascade. It fires silently before two of seven observed cascades (the news-driven ones).

The practical implication: don't propose or implement a cascade EWS gate for ST2.0. The existing per-pair cooldown (10 min after loss) and daily halt (max(3% × balance, $8)) already serve as post-cascade circuit breakers; trying to predict cascades pre-entry is not supported by this evidence.

**Critical limitations:**
1. BTCUSDT only — altcoin perp cascade dynamics may differ.
2. 7 events — small sample, limited statistical power on individual signals.
3. Paper is BTCUSDT only and studies BTC cascades — ST2.0's altcoin universe may have different cascade signatures.

---

## Unverified Claims (Cannot Cite as Fact)

**Funding window spread peaks:** MDPI 2227-7072/14/5/103 returned HTTP 403 Forbidden for the 3rd consecutive night. Claim that "spreads peak approximately 1–2 hours after standard funding settlement times (00:00/08:00/16:00 UTC)" remains unverified. Do not act on it. Access route unknown — standard WebFetch cannot reach MDPI for this paper.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 34 | **Anti-recommendation: do NOT add BTC lead-lag gate for altcoin entries.** Cross-crypto microstructure transfer fails empirically (Binance 6-crypto, Aug–Feb 2026). Any proposed gate should be treated as unsupported speculation per this paper. If same-asset spot confirmation is desired, that requires infrastructure work (spot WebSocket per altcoin). | Frontiers 2026, Pindza (Binance spot+perp 6 major cryptos, Aug 2025–Feb 2026 — major assets only, Binance not Phemex; peer-reviewed open-access; solo author UNISA) | No-code negative recommendation | 0 lines |
| 34a | **Ask-side depth growth rate log.** At signal time, log `ask_depth_delta_60s` = change in total best-5-level ask-side depth over the 60 seconds before signal fire. After 30+ fills: do adverse fills cluster when ask depth is growing? Cross-reference Tweak 24 (static depth) and Tweak 31 (time-to-fill). If yes: candidate gate on pre-signal ask supply buildup. | arXiv:2606.15715 Barone & Lillo 2025 (Hyperliquid DEX, 201 perp markets — NOT Phemex CEX; institutional TWAP execution, not retail-size; mechanism inferred from buy-side dynamics, not directly measured on ask side; preprint) | Queued — log only | 3–4 lines |

---

## Honest Caveats

1. **Finding A (Frontiers 2026):** Full HTML fetched, direct quotes verified. But: solo-authored, Frontiers in Blockchain (lower-tier venue), Binance spot+perp with major assets only. The cross-asset transfer failure is the headline finding; it's clearly evidenced in the abstract and results. Applies as a negative prior against BTC lead-lag gating, not a definitive proof.

2. **Finding B (arXiv:2606.15715):** Abstract fetched directly, quotes are verbatim from the abstract. The mechanism connecting "TWAP buy → ask depth rises → ST2.0 queue degrades" is an inference from the paper's LOB-dynamics finding — the paper doesn't directly study retail passive sell behavior during buy absorption episodes. Institutional TWAP → visible mechanism doesn't directly translate to Phemex CEX, where TWAP orders are not publicly visible. Tweak 34a is motivated by the mechanism, not directly measured.

3. **Finding C (arXiv:2607.27070):** HTML fetched, key quotes extracted. Strong negative result — no reliable cascade EWS. The constraint is that this studies BTCUSDT only; altcoin cascade dynamics may differ but the general finding ("single-venue, single-variable claims are fragile") is structural advice applicable to any proposed cascade gate.

4. **DeltaLag (arXiv:2511.00390): confirmed dead end.** US equities daily returns only. Not applicable to crypto perp intraday execution. Closes the BTC lead-lag angle from the literature side (Frontiers 2026 closes the empirical cross-crypto angle).

5. **39 tweaks queued, 0 deployed across 32 nights.** Recommendation unchanged from N20–N31: implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweak 34a is 3–4 lines (log only) and can be added in the same session. The bottleneck remains deploying the priority tweaks to collect 30+ tagged fills per diagnostic variable.

6. **SSRN 6344338 blocked** (32 consecutive nights). **SSRN 6693260 blocked** (32 consecutive nights). No access route.

---

## Cumulative Forward-Test Queue (39 Tweaks)

Priority tweaks (unchanged from N20–N31): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweaks 34, 34a added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), above (Tweaks 34, 34a).

---

## Night 32 Bottom Line

Three findings. Finding A (Frontiers 2026, Pindza, Binance 6-crypto spot+perp, Aug 2025–Feb 2026, VERIFIED via full HTML, peer-reviewed): cross-cryptocurrency microstructure transfer fails at minute frequency — "models trained on one cryptocurrency do not transfer to others"; same-asset spot/perp transfer works. "No strategy survives realistic exchange fees." Closes the BTC lead-lag gate hypothesis: don't add it (Tweak 34, anti-recommendation). Finding B (arXiv:2606.15715, Barone & Lillo, Hyperliquid DEX 201 perp markets, Jul 2025–Mar 2026, VERIFIED via abstract): visible buy programs "elicit liquidity provision — displayed depth rises and book tilts toward the absorbing side." Buy absorption (ST2.0's signal trigger) attracts competing passive sellers, degrading queue position precisely at signal fire time. Forward-testable as Tweak 34a (log `ask_depth_delta_60s` — pre-signal ask supply growth rate, distinct from Tweak 24's static depth). Critical: Hyperliquid DEX, institutional TWAP, not directly measured for retail-size Phemex passive sells. Finding C (arXiv:2607.27070, Binance BTCUSDT, 7 cascades 2022–2025, VERIFIED via HTML): no reliable per-event cascade EWS — "single-venue, single-variable early-warning claims are fragile by construction." Argues against adding a cascade detection gate to ST2.0.

**Recommendation unchanged from N20–N31:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweak 34a is 3–4 lines (log only). Night 32: 39 tweaks queued, 0 deployed.
