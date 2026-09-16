# Edge candidates NOT on the dead list — literature scan, 9/14/2026

Scope: mechanisms a ~$87 USDT-margined perp account on Phemex, polled every 5 minutes from a home Mac, could still try. Everything on the owner's dead list (5m MR and all variants, L2/OB signals, S/R bounce, VWAP/SMA, liquidation cascades, narrow range, HTF L2, BTC/ETH TSM, Donchian ensemble, small caps, exit tweaks, calendar effects on own trades, funding harvesting, cross-sectional momentum, OI, basis/carry, inverse-linear spread, pairs, entry gates, venue migration) is excluded or explicitly labeled as a re-label.

Evidence standard: each claim cites a URL. Tags: **[FOUND]** = read on the cited page this session; **[SECONDARY]** = primary was blocked (HTTP 403), figure taken from a secondary page that quotes it; **[INFERRED]** = my arithmetic or reasoning, not a published number. I did not verify any number against the bot's own logs — those figures (0.07% RT, −4.5 bps adverse selection, ~$78 BTC lot, $87 balance, 0% maker exit fills) are taken from the task brief as given.

---

## 0. Structural inputs verified this session

| Input | Value | Source |
|---|---|---|
| Phemex USDT-perp default maker / taker | 0.01% / 0.06% | [FOUND] https://phemex.com/help-center/Phemex-Future-fee-structure-and-calculation |
| Implied RT with maker entry + taker exit | 0.07% | [INFERRED] 0.01 + 0.06 — matches the brief's 0.07% |
| BTCUSDT qtyStepSize / minOrderValueRv | 0.001 BTC / 1 USDT | [FOUND] live `GET https://api.phemex.com/public/products`, `perpProductsV2` node, queried 9/14/2026 |
| ETHUSDT qtyStepSize | 0.01 ETH | [FOUND] same API call |
| SOLUSDT qtyStepSize | 0.01 SOL | [FOUND] same API call |
| Phemex USDT Flexible Savings | 5% APY, no lock, cap 500,000 USDT (announced 4/8/2025) | [FOUND] https://phemex.com/announcements/phemex-has-launched-usdt-flexible-savings-earn-up-to-5-apy — a review site says the 5% applies only to the first 20,000 USDT then 2% (https://forklog.com/en/phemex-exchange-review-2026-fees-security-trading-bots-and-earn-products/); either way irrelevant at $87 |

Note on the BTC lot: 0.001 BTC ≈ $78 implies BTC ≈ $78,000. I did not fetch a live BTC price; the $78 figure is the brief's.

---

## 1. Retail base rates (why the prior should be pessimistic)

- **Chague, De-Losso, Giovannetti (2020), "Day Trading for a Living?"** — all individuals who began day-trading Brazilian equity futures 2013-2015 and persisted ≥300 days: "97% of them lost money", "only 0.4% earned more than a bank teller (US$54 per day)", top earner US$310/day with SD US$2,560, "no evidence of learning by day trading." [FOUND] https://ideas.repec.org/p/spa/wpaper/2019wpecon47.html (SSRN mirror: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101, blocked this session)
- **Hyperliquid on-chain samples (2025)** — a Medium analysis of 10,000 wallets reports 73.8% losing; a TechFlow analysis of 43,618 addresses found 1,681 (~3.9%) meeting its profitability screen. [SECONDARY, non-peer-reviewed, methodology not audited] https://medium.com/@envyprotocol/i-analyzed-10-000-hyperliquid-traders-the-results-are-brutal-a29adcca8c2a ; https://www.techflowpost.com/en-US/article/33650
- These are populations, not mechanisms, but they set the prior: the owner's 5-month, ~40-family kill record is the *typical* outcome, not an anomaly.

---

## 2. Mechanisms with documented evidence — full scan

### 2.1 Token-unlock short (event-driven, multi-day) — NOT on the dead list

**Mechanism.** Scheduled vesting unlocks add supply; prices drift down into and through the event. Short the perp ~T-1 to T-30, cover days-to-weeks later.

**Evidence.**
- Keyrock, "From Locked to Liquidity: What 16,000+ Token Unlocks Teach Us" — 16,000 unlock events; ~90% associated with negative price pressure; impact begins ~30 days before the event; team unlocks average ~−25%; larger unlocks ~2.4× sharper drops; "ecosystem" unlocks slightly positive (+1.18%). Primary page returned 403; figures from secondary coverage. [SECONDARY] https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/ via https://beincrypto.com/keyrock-research-token-unlocks/ and https://www.chaincatcher.com/en/article/2155623
- Tigro Blanc (Apr 2026), Binance USDT perps, unlocks with Forward Dilution Rate >5%: beta-adjusted CAR[−30,+30] = −15.05%, 95% bootstrap CI [−24.82%, −5.54%]; event-driven short sim 22 trades, 77.3% win rate, +8.88% avg net PnL/trade, profit factor 2.12, **max drawdown −86.6% from one squeeze**, ~16.9 events/yr; author's verdict: "not tradeable as a standalone short strategy... useful as a risk filter or timing overlay." Primary Medium page 403; figures from search summary. [SECONDARY] https://medium.com/coinmonks/i-backtested-shorting-token-unlocks-heres-why-i-m-not-trading-it-yet-42e237d40d9a
- Keyrock also notes investor unlocks now show "controlled" price behaviour because recipients hedge in advance — i.e. the easy part of this edge is already being arbitraged by the recipients themselves. [SECONDARY] same coverage.

**Holding period.** Days to weeks. **Needs:** an unlock calendar (free: tokenomist.ai), the token listed as a Phemex USDT perp, tolerance for squeeze tails. Does not need speed or L2 data.

**Verdict.** Genuinely new relative to the dead list. Weak on frequency (~17 events/yr, so a forward test to n≈30 takes ~2 years) and on tail (one −86.6% DD event in a 22-trade sim). Funding cost for crowded shorts before a known event is the unmeasured killer — I found no published measurement of pre-unlock funding rates [INFERRED gap].

### 2.2 Post-listing fade (short new major-exchange listings after the day-1 pop) — NOT on the dead list

**Mechanism.** Listing hype produces a positive abnormal return around the event, followed by sustained underperformance.

**Evidence.**
- Ante (2019) and Benedetti & Nikbakht (2021, J. Corp. Finance) document positive abnormal returns in the days around exchange listings, turning negative post-event. [SECONDARY, peer-reviewed papers referenced via search summary] https://www.researchgate.net/publication/336049306_Market_Reaction_to_Exchange_Listings_of_Cryptocurrencies
- Empirica, 500+ Binance listings 2017-2024, returns vs first-day close: Day 1 +2.78%, Week 1 +0.40%, Month 1 −1.76%, Month 3 −22.66%, Month 6 −37.64%; six-month distribution: 191 tokens lost >50%, 122 lost 0-50%, 62 gained ≤50%, 88 gained >50%; 2024 cohort: only 5.5% positive at 6 months; aggregate 6-month performance trails ETH by −39.46%; 2024 cohort −31.20% vs market. [FOUND] https://empirica.io/blog/the-binance-effect-a-7-year-analysis-for-token-founders/
- BeInCrypto (2025): 89% of 2025 Binance listings negative (page 403; headline only). [SECONDARY] https://beincrypto.com/binance-listed-tokens-negative-return/
- Counter-evidence: Klein Labs 2024 report finds positive 30-day averages for some exchanges/months (e.g. Binance May +87.8%, Sept +94.9%, with top/bottom 10% trimmed). [FOUND] https://www.chaincatcher.com/en/article/2175717 — so the 30-day window is noisy; the effect in Empirica's data is at 3-6 months.

**Holding period.** 1-6 months. **Needs:** Phemex to list a perp on the token; a listing feed (free); ability to sit through +50% squeezes (88/500 did that). No speed, no L2.

**Verdict.** Genuinely new. Better frequency than unlocks (44 Binance listings in 2024 per Empirica). The Empirica numbers are market-adjusted and still deeply negative, which is more than most crypto anomalies can say. Same unmeasured killer: funding on freshly listed perps is often extremely negative for shorts [INFERRED — widely asserted in trading commentary, I found no measured study]. Also there is an obvious selection issue: Empirica's population is Binance listings, not Phemex-perp-available tokens.

### 2.3 Pre-FOMC drift in BTC — NOT on the dead list, but tiny

- Pyo & Lee (2020, Finance Research Letters): FOMC announcements significantly affect BTC; secondary summary reports ≈+0.96% the day before, ≈−1% on announcement day. Primary 403; the 0.96% figure came from a search-engine summary and I could not confirm it on the abstract page. [SECONDARY, weak provenance] https://www.sciencedirect.com/science/article/abs/pii/S154461231930159X
- Karau (2023, J. Int. Money & Finance) "Monetary policy shocks and Bitcoin prices": 1 bp surprise tightening in 2-yr yield → ≈−0.25% BTC on the day, with a "large drift" over following days. [SECONDARY] https://www.sciencedirect.com/science/article/abs/pii/S027553192200099X
- A 2026 FRL paper on scheduled FOMC statements and intraday risk exists (403). https://www.sciencedirect.com/science/article/abs/pii/S1544612326006021

**Feasibility.** 8 events/yr; ~1% move × $78 BTC lot = ~$0.78 gross per event before 0.07% fees ($0.05) and adverse selection ($0.035). ~$5.50/yr if it works perfectly. Not forward-testable to any n in a human timeframe. [INFERRED]

### 2.4 BTC hourly / overnight / weekend seasonality — adjacent to dead "time-of-day" but structurally different; evidence is mixed and cost-blind

Owner's null was on his own 5m-MR trades by hour/weekday, not on a standalone long-BTC seasonal hold, so this is not literally dead. But:
- Quantpedia, Gemini hourly BTC 10/9/2015–6/30/2023: buy 21:00 UTC, sell 23:00 UTC; 40.64%/yr, Calmar 1.79, MDD −22.7%; "rough period in 2022 and 2023"; costs not mentioned; ~365 round trips/yr. [FOUND] https://quantpedia.com/the-seasonality-of-bitcoin/ ; strategy page (2015-2021 sample): 33%/yr, vol 20.93%, Sharpe 1.58, MDD −34.04%, costs not mentioned. [FOUND] https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin
- Quantpedia (2024): MAX(10)-high strategy held only overnight/weekend; out-of-sample 10/2021–10/2024 ~35%/yr, MDD −12% for the close-to-close variant; "most returns... generated during the overnight trading session"; **transaction costs not included**; authors call the in/out-of-sample split "very arbitrary." [FOUND] https://quantpedia.com/how-to-profitably-trade-bitcoins-overnight-sessions/
- Contrary: Bitcoin weekend effect 9/19/2014–1/21/2024, HAC-robust OLS with month FE: "no detectable weekend–weekday gap in average returns"; weekends are quieter, not premia. [FOUND] https://ojs.bbwpublisher.com/index.php/PBES/article/view/11691
- Contrary: hourly analysis shows the "Monday effect" collapses to a single Sunday 23:00–00:00 UTC hour (US retail logging back in); authors call it non-tradeable and advise discarding any seasonal signal that disappears under hourly scrutiny. [FOUND] https://mlquants.substack.com/p/are-day-of-the-week-effects-in-cryptocurrencies

**Feasibility arithmetic.** The 21:00-23:00 UTC trade needs ~365 RT/yr. At the owner's realised cost (0.07% fees + 4.5 bps adverse selection ≈ 11.5 bps per RT) that is ≈ 42% of notional per year in costs, against a *gross* 33-41%/yr. Dead after costs at retail. Weekend-only (52 RT/yr ≈ 6%/yr cost) is arithmetically survivable but the return evidence is contradicted by the 2014-2024 paper. [INFERRED arithmetic; sources above]

### 2.5 Daily/weekly trend-following with vol targeting — RE-LABEL of the paper Donchian slot (mostly)

- Hudson & Urquhart (2021, Annals of OR), ~15,000 rules, 5 markets: breakeven transaction costs "substantially higher than those typically found in cryptocurrency markets" **but "no predictability for Bitcoin in the out-of-sample period."** [FOUND] https://research.birmingham.ac.uk/en/publications/technical-trading-and-cryptocurrencies/
- Le & Ruthbah (Monash/SSRN 2023-24): shorter-lookback trend rules give high Sharpe; "the effect of transaction costs is very substantial." PDF 403. [SECONDARY] https://www.monash.edu/business/mcfs/our-research/all-projects/investment-strategy/trend-following-strategies-for-crypto-investors
- Concretum: Donchian ensemble over top-20 liquid coins with vol-based sizing, Sharpe >1.5, 10.8%/yr alpha vs BTC — backtest, period/OOS not stated on page. [FOUND] https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/
- arXiv 2602.11708 (2026): 150+ pairs, 2022-2024, Sharpe 2.41, MDD −12.7% — backtest with "transaction cost modeling" but no separate net figures in abstract. [FOUND] https://arxiv.org/abs/2602.11708 — treat as unverified.
- arXiv 2009.12155: "255% walkforward annualised returns" 2010-2020 — costs not stated in abstract. [FOUND] https://arxiv.org/abs/2009.12155 — treat as unverified.

**Verdict.** The literature's trend result is the same thing the owner already has in paper (Donchian ensemble). The one non-dead element is *cross-asset rotation + vol sizing across many alts*, and that is blocked at $87 by lot floors on BTC (and by the number of simultaneous positions a $87 book can carry). Nothing here is new evidence; it's a re-label. The owner's rule (backtest ≠ evidence) applies with force to the two arXiv papers.

### 2.6 Grid / market-neutral / stat-arb — dead or infeasible

- Chen, Chen & Jang (arXiv 2506.11921): plain grid "produces near-zero expected return before fees." [SECONDARY] via search summary; dynamic grid with trend detection is again trend-following.
- Yang & Malik (arXiv 2405.15461): multivariate pair trading, 15.49%/yr 2020-2022 — pairs is on the dead list. https://arxiv.org/abs/2405.15461
- Cross-exchange lead-lag: price discovery is sub-second on Binance; low-volume venues lag high-volume ones. Requires colocated speed the owner does not have; 5-minute polling is 4-5 orders of magnitude too slow. [FOUND abstract] https://arxiv.org/abs/2506.08718 ; https://www.sciencedirect.com/science/article/abs/pii/S016517652600220X

### 2.7 CME gap fill — mechanism removed by the market

CME BTC futures moved to 24/7 trading from late May 2026; the weekend gap "has effectively disappeared." [FOUND via search] https://www.coindesk.com/markets/2026/05/28/bitcoin-s-famous-cme-gaps-are-about-to-disappear-though-three-remain-unresolved

### 2.8 Turn-of-month / month-of-year — no robust Bitcoin effect

Turn-of-month: only Stacks significant; Bitcoin shows no statistically significant calendar anomalies when tested properly. [SECONDARY] https://www.researchgate.net/publication/359327404_Turn-of-the-month_effect_in_cryptocurrencies ; https://harbourfrontquant.substack.com/p/calendar-anomalies-in-digital-assets

### 2.9 Non-trading yield — Phemex USDT Flexible Savings

5% APY, no lock (see §0). On $87 that is ≈ $4.35/yr. Counterparty (exchange) risk, zero fee drag, zero adverse selection. [FOUND + INFERRED arithmetic]

---

## 3. Which candidates are genuinely NOT re-labels

| Candidate | New vs dead list? | Why |
|---|---|---|
| Token-unlock short | Yes | Event-driven supply shock, multi-day hold; nothing in the dead list is event-driven |
| Post-listing fade | Yes | Same reason |
| Pre-FOMC drift | Yes | Macro-calendar event; not tested |
| BTC overnight/weekend seasonal long | Partly | Different object (standalone BTC hold) from the owner's own-trade hour/weekday null, but evidence is contradicted and cost-blind |
| Trend + vol sizing + rotation | No | Re-label of the paper Donchian slot |
| Grid / pairs / lead-lag | No / infeasible | Pairs dead; grid ≈ 0 EV pre-fee; lead-lag needs sub-second speed |
| CME gap | No longer exists | Market change 5/2026 |

---

## 4. Fee-and-size feasibility at $87 / 0.07% RT / $78 BTC lot / 5-min polling

All figures below are [INFERRED] arithmetic from the verified inputs in §0 and the brief.

### 4.1 Cost per round trip

- Fees: 0.07% × notional. On a $15 slot = $0.0105; on the $78 BTC lot = $0.055; on the full $87 = $0.061.
- Adverse selection on maker entry (brief): 4.5 bps → $0.007 / $0.035 / $0.039 respectively.
- Realised all-in cost per RT ≈ 11.5 bps of notional, before funding.
- Funding: 8-hourly; sign and size unknown per trade; ignored below (it only makes the numbers worse for crowded-side positions).

### 4.2 Breakeven win rate for symmetric TP/SL of x bps, cost c = 11.5 bps

p* = (x + c) / (2x)

| Target/stop x | Breakeven win rate |
|---|---|
| 25 bps (5-min scalp) | 73.0% |
| 50 bps | 61.5% |
| 100 bps | 55.8% |
| 300 bps (multi-day) | 51.9% |
| 1,000 bps (weeks) | 50.6% |

This is the whole story of the owner's record: intraday geometries need >60% hit rates that no documented crypto anomaly delivers, while multi-day holds need barely above coin-flip. The literature's surviving effects (unlocks, listings, trend) are all at the bottom of this table.

### 4.3 Dollar ceiling at $87

- Even a strategy that genuinely nets 20%/yr after costs (a strong, institutional-grade result) produces ≈ $17/yr on $87.
- The Quantpedia 21-23 UTC seasonal, gross 40.64%/yr, would lose ≈ 42% of notional/yr to 365 RTs at 11.5 bps — net negative regardless of size.
- Phemex savings at 5% ≈ $4.35/yr with no trading risk. Any trading strategy must clear that plus the risk premium to be rational.
- Minimum-lot constraint: one 0.001 BTC lot is 90% of the account; a 5% adverse move on it (−$3.90) is 4.5% of the balance; there is no sizing granularity on BTC at all. ETH (0.01 ETH step) and SOL (0.01 SOL step) are fine granularity-wise.

### 4.4 Account size needed for a fee structure of 0.07% RT to be "beatable" in a way that matters

The fee structure is beatable in *percentage* terms at any size once holds are multi-day (table 4.2). The binding constraint is dollars:

| Target net income | Required balance at 20%/yr net | at 10%/yr net |
|---|---|---|
| $10 / month | $600 | $1,200 |
| $100 / month | $6,000 | $12,000 |
| Bank-teller equivalent in Chague (US$54/day ≈ $1,100/mo) | $66,000 | $132,000 |

And the 20%/yr net assumption is generous: Hudson & Urquhart found *no* out-of-sample BTC predictability; Le & Ruthbah found costs "very substantial"; the 2014-2024 weekend paper found no return premium. The record's own funding-spread finding (+3-4%/yr, real, but <$2/mo below $2K) is the honest benchmark for what a real but small edge pays at this scale.

### 4.5 Per-candidate feasibility

| Candidate | RTs/yr | Fee drag/yr on $15 slot | Gross evidence | Forward-test time to n=30 | Blockers |
|---|---|---|---|---|---|
| Unlock short | ~17 | ~$0.18 | CAR −15% over 60d (secondary), 77% WR sim with −86.6% DD | ~2 yrs | Phemex must list the perp; funding on crowded shorts unmeasured; tail |
| Post-listing fade | ~20-44 | ~$0.46 | −22.66% at 3 mo, −37.64% at 6 mo vs day-1 close (Empirica) | ~1 yr | Phemex must list the perp; funding on new perps unmeasured; 18% of tokens +50% |
| Pre-FOMC | 8 | ~$0.08 | ≈+1% day-before (weak provenance) | ~4 yrs | n hopeless; BTC lot = 90% of account |
| Weekend BTC hold | 52 | ~$0.06 (BTC lot: $0.28) | contradicted | ~7 months | Evidence conflict; BTC lot floor |

Nothing in this table pays more than single-digit dollars per year at $87 even if it works exactly as the backtests say.

---

## 5. Structural options suggested by the failure modes

1. **Stop intraday entirely; only trade multi-day event or trend holds.** Every survivor in the literature is at the ≥days horizon; every intraday item in the owner's record is dead, consistent with Hudson & Urquhart (no OOS BTC predictability) and the breakeven table in §4.2. Evidence: §2.1, §2.2, §2.5, §4.2.
2. **Do not move to spot.** Phemex spot fee is 0.1% per side (record's basis/carry note), worse than 0.07% RT on perps; spot removes shorting, which is where the only two new candidates live.
3. **Park in Phemex USDT Flexible Savings (5% APY).** ≈$4.35/yr, no fees, no adverse selection, exchange counterparty risk. This is the only positive-expectancy action at $87 with [FOUND] evidence and no forward test required. https://phemex.com/announcements/phemex-has-launched-usdt-flexible-savings-earn-up-to-5-apy
4. **Fund the account to ≥$600-$1,200 before any further strategy work**, because below that no real edge can pay more than the electricity (§4.4). This is not advice to deposit; it is the arithmetic threshold at which "it works but pays nothing" stops being the answer.
5. **Nothing at this size is viable — stop.** This is the option best supported by the evidence: Chague's 97%/0.4% base rates, the Hyperliquid 74%-losing samples, the owner's ~40 killed families, the §4.3 dollar ceiling, and the fact that the two non-dead candidates each carry an unmeasured funding cost and a −86.6% / +50%-squeeze tail that a $15 slot cannot survive many times.

---

## 6. Ranked shortlist (with honesty tags)

1. **Post-listing fade (short 1-3 months after a major-exchange listing pop)** — only candidate with market-adjusted, multi-year, [FOUND] numbers (Empirica) and enough events (~40/yr) to forward-test inside a year. Expected dollars at $15: cents per trade. Unmeasured killer: funding on new perps. Needs an owner "go" for a paper slot, nothing more.
2. **Token-unlock short (T-1 to T+21, FDR >5%)** — [SECONDARY] evidence only, ~17 events/yr, one-squeeze tail; the backtester himself declined to trade it. Paper-only if at all.
3. **Nothing / savings** — arithmetically dominant at $87.

Not shortlisted: pre-FOMC (n hopeless), seasonality (contradicted + cost-blind), trend/vol rotation (re-label of the paper Donchian slot), grid/pairs/lead-lag (dead or infeasible), CME gap (gone).

---

## Sources (all accessed 9/14/2026)

- https://phemex.com/help-center/Phemex-Future-fee-structure-and-calculation
- https://api.phemex.com/public/products
- https://phemex.com/announcements/phemex-has-launched-usdt-flexible-savings-earn-up-to-5-apy
- https://forklog.com/en/phemex-exchange-review-2026-fees-security-trading-bots-and-earn-products/
- https://ideas.repec.org/p/spa/wpaper/2019wpecon47.html
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101
- https://medium.com/@envyprotocol/i-analyzed-10-000-hyperliquid-traders-the-results-are-brutal-a29adcca8c2a
- https://www.techflowpost.com/en-US/article/33650
- https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/
- https://beincrypto.com/keyrock-research-token-unlocks/
- https://www.chaincatcher.com/en/article/2155623
- https://medium.com/coinmonks/i-backtested-shorting-token-unlocks-heres-why-i-m-not-trading-it-yet-42e237d40d9a
- https://www.researchgate.net/publication/336049306_Market_Reaction_to_Exchange_Listings_of_Cryptocurrencies
- https://empirica.io/blog/the-binance-effect-a-7-year-analysis-for-token-founders/
- https://beincrypto.com/binance-listed-tokens-negative-return/
- https://www.chaincatcher.com/en/article/2175717
- https://www.sciencedirect.com/science/article/abs/pii/S154461231930159X
- https://www.sciencedirect.com/science/article/abs/pii/S027553192200099X
- https://www.sciencedirect.com/science/article/abs/pii/S1544612326006021
- https://quantpedia.com/the-seasonality-of-bitcoin/
- https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin
- https://quantpedia.com/how-to-profitably-trade-bitcoins-overnight-sessions/
- https://ojs.bbwpublisher.com/index.php/PBES/article/view/11691
- https://mlquants.substack.com/p/are-day-of-the-week-effects-in-cryptocurrencies
- https://research.birmingham.ac.uk/en/publications/technical-trading-and-cryptocurrencies/
- https://www.monash.edu/business/mcfs/our-research/all-projects/investment-strategy/trend-following-strategies-for-crypto-investors
- https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/
- https://arxiv.org/abs/2602.11708
- https://arxiv.org/abs/2009.12155
- https://arxiv.org/abs/2405.15461
- https://arxiv.org/abs/2506.08718
- https://www.sciencedirect.com/science/article/abs/pii/S016517652600220X
- https://www.coindesk.com/markets/2026/05/28/bitcoin-s-famous-cme-gaps-are-about-to-disappear-though-three-remain-unresolved
- https://www.researchgate.net/publication/359327404_Turn-of-the-month_effect_in_cryptocurrencies
- https://harbourfrontquant.substack.com/p/calendar-anomalies-in-digital-assets
