# R5 — Slow-Horizon Strategy Research: Multi-Hour to Multi-Day Families with Verified Post-2022 Evidence

**Date:** 2026-07-05 (overnight research)
**Question:** For this account (~$57, Phemex USDT perps, 1bp maker / 6bp taker, can hold days, 5m scalper already running), which multi-hour-to-multi-day strategy families have the strongest VERIFIED post-2022 evidence of positive expectancy net of realistic costs — and what is the pre-registered forward-test spec at $10-15/position?

**Method:** 5 parallel search agents (TSM/trend, breakout, vol-managed, retail anomalies, Phemex specs + reality check), every cited number fetched this session and quoted from source text. The single most load-bearing source (Han/Kang/Ryu) was verified three independent times, including direct PDF text extraction of the results tables. Anything that could not be fetched is listed in §8 as UNVERIFIED and was NOT used to form the conclusion.

---

## 1. Executive summary

**One family clears the bar: slow, long-only trend / time-series momentum on BTC-ETH at daily horizon.** It has (a) an academic study with realistic costs (15bps/trade), liquidation modeling, and a sample through Aug 2023 showing net Sharpe 1.51 vs market 0.85; (b) an independent true out-of-sample re-test (Feb 2022–Aug 2024) showing the trend entry (new N-day highs) "remains very effective" while its mirror (multi-day dip-buying) died; (c) a 2025 Swiss Finance Institute paper showing a Donchian-ensemble variant net-of-fees Sharpe >1.5 through ~2025; and (d) a live BTC-futures momentum fund that returned 144% net in 2024. The same verified literature kills the short leg, kills multi-day mean reversion post-2022, kills calendar/weekend seasonality post-2022, and says vol-scaling is a drawdown tool, not a rescue for dead signals.

**The catch for this account is not the edge, it is the arithmetic of the daily-loss halt** (3% of balance ≈ $1.72, realized-PnL-only — verified in bot.py). A trend-appropriate stop is wide (~6-8%), so notional must be ~$18-25, NOT $15 margin at 10x ($150 notional). The only Phemex min-step that fits today is **ETHUSDT at 0.01 ETH ≈ $17.7 notional** (BTC's 0.001 step ≈ $63.2 notional risks ~$4-5 at a trend stop — an instant halt breach).

**Recommendation:** forward-test the Han et al. (28-day lookback, 5-day hold, long-only, top-tercile) rule, expressed as one 0.01-ETH position, exactly as pre-registered in §7. Expected dollar PnL is small (~$1/month scale if history rhymes); the test's purpose is process/cost validation so it can be scaled as the account grows — say that plainly and judge it that way.

---

## 2. Family 1 — Time-series momentum / trend at daily horizon: SURVIVED, long-only

### 2.1 Han, Kang & Ryu (2023) — the anchor source (verified 3×, incl. direct PDF extraction)

Han, Kang & Ryu, "Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions," SSRN 4675565.
PDF: https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf

- **Sample (quoted from PDF):** "our sample starts on this date and ends on August 28, 2023" (starts Dec 2013) — includes the 2022 bear (Terra/FTX).
- **Rule (quoted):** "A strategy that buys the market when its look-back period return falls within the top third of the historical returns outperforms the market across a wide range of look-back and holding periods. The strategy performs best when the look-back period is twenty-eight days and the holding period is five days." Market portfolio is value-weighted; "the average market dominance of these two coins [BTC+ETH] stands at 79.0%" — so this is essentially a BTC/ETH timing overlay.
- **Costs (quoted):** "We assume a transaction cost of 15 basis points (bps) for every trade" — deliberately above Binance's then-current 10bps spot / 4.5bps futures; slippage/tick/liquidation grounded in ~15.7M real trading records.
- **Net results — extracted directly from the paper's results table this session:**
  - (28,5) long-only BEFORE costs: mean 75.37%/yr, std 48.34%, **Sharpe 1.56**, cum 46,787%, MDD 61.0%
  - (28,5) long-only AFTER 15bps costs: mean 72.85%/yr, std 48.34%, **Sharpe 1.51**, cum 36,685.8%, **MDD 61.8%**
  - (28,5) short-only after costs: mean −2.44%, Sharpe −0.05 (dead); long-short after costs: Sharpe 1.07 (worse than long-only)
- **Robustness (quoted):** "Even after accounting for the transaction costs, all long-only portfolios, except for the (7, 7) portfolio, outperform the market." "It has a higher Sharpe ratio than the market in eight of the ten years and a lower standard deviation and MDD in all years." "It holds a position for 48% of the sample period."
- **Honest caveats from the paper itself:** the edge is mostly bear-avoidance, not upside capture ("it underperforms the market when the market goes up"); it "can generate profits in the future only if the market continues to grow"; short-side TSM "almost non-existent when the market is bearish"; cross-sectional momentum among large coins "has diminished."

### 2.2 Quantpedia true out-of-sample re-test (2024) — trend lives, dip-buying died

Beluská, "Revisiting Trend-following and Mean-reversion Strategies in Bitcoin," Quantpedia, Sep 2024. https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/ (also SSRN 4955617). Fetched independently by two agents, matching quotes.

- Original in-sample Nov 2015–Feb 2022; OOS window **Feb 4 2022 – Aug 20 2024**.
- MAX rule (buy BTC at new 10-50-day high): OOS, "the MAX strategy remains very effective"; "Buying the BTC when it reaches a 10-days maximum appears to be less effective than buying at a 20-days maximum, however, is still worthwhile."
- MIN rule (buy at new N-day low): "the MIN strategy is not performing as well as it did in the in-sample analysis... this strategy has suffered due to a decline."
- **Limitation:** gross of costs (turnover is low, but strictly this source is direction-only evidence).

### 2.3 Supporting evidence

- **Bui & Nguyen, arXiv 2602.11708 (2026), 6h bars, OOS Jan 2022–Dec 2024:** their plain **TSMOM-1M benchmark: 18.4%/yr, Sharpe 0.65, MDD −34.8%** net of 4bps+slippage+funding — mediocre but still positive through the bear. Their full adaptive framework claims Sharpe 2.41 net (2.01 at 8bps) — **screening-grade only** (non-peer-reviewed, unknown shop, extraordinary claim).
- **Man AHL, "In Crypto We Trend" (Dec 2024):** https://www.man.com/insights/in-crypto-we-trend — a major systematic manager applying 50/200d MA + breakout trend to crypto with vol scaling; optimal breadth "around 10-15 coins"; explicit honesty flag that measured crypto trend Sharpes are "higher than expected... probably a function of the short history." Qualitative survival evidence, no published Sharpe.
- **Live fund reality check (HedgeNordic, Jan 2025):** https://hedgenordic.com/2025/01/outshining-bitcoins-rally-with-momentum-strategy/ — "Anna Fund emerged as the top performer in the index with a return of 144 percent" (2024) vs BTC "gross return of 121 percent," running "a momentum-driven strategy that exclusively relies on historical price and volume data to trade Bitcoin futures." Single fund, single year, launched mid-2023 — survivorship caveat applies, but it is a real net track record.
- **Borri, Liu, Tsyvinski & Wu, arXiv 2510.14435 (Oct 2025):** crypto momentum (2-week lookback, cross-sectional) significant "in both the full sample and post-2020 period" — adjacent evidence from the Liu-Tsyvinski lineage.

**Verdict: strongest verified family.** Consistent across an academically-costed study, an independent OOS re-test, an institutional practitioner, and one live fund. The surviving shape is specific: **long-only, slow (20-30d lookback), daily-close cadence, exits to flat (never flip short).**

---

## 3. Family 2 — Donchian / channel breakout: viable, as a cousin of Family 1

- **Zarattini, Pagani & Barbon (2025), Swiss Finance Institute RP 25-80** (SSRN 5209907; verified via https://ideas.repec.org/p/chf/rpseri/rp2580.html and https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/): ensemble of "multiple Donchian channel-based trend models, each calibrated with different lookback periods" + "volatility-based position sizing," survivorship-bias-free data since 2015, top-20 liquid coins: "achieved notable net-of-fees returns, with a Sharpe ratio above 1.5 and an annualized alpha of 10.8% versus Bitcoin." Full PDF was 403-blocked: exact fee bps, MDD, and the ensemble lookback list are UNVERIFIED.
- **Quantpedia "Silicon vs. Satoshi"** (https://quantpedia.com/silicon-vs-satoshi-tactical-asset-rotation-between-nasdaq-100-and-bitcoin/, sample 2019–Dec 2025): single-lookback Donchian breakout entries produced Sharpe 1.69 (5-day) / 1.68 (20-day) with MaxDD −19.5%/−17.6% vs buy-and-hold BTC Sharpe 0.894, MDD −76.6% — **but "Transaction costs are not modeled."**
- Nobody in the verified set shows a classic 20/55 turtle on BTC/ETH perps net of fees for 2023-2026 specifically. The one turtle test found (Gate Research via odaily.news) is a modified variant on an exchange token over one bull year — weak external validity.

**Verdict: real but second place.** The net-of-fees evidence (Zarattini) is ensemble+portfolio, not a single retail rule; the single-rule evidence (Quantpedia ×2) is gross of costs. Breakout entries and tercile-TSM entries are cousins — both are "be long when price is strong at the 20-30d scale" — so this family corroborates Family 1 rather than competing with it.

---

## 4. Family 3 — Vol-managed variants: drawdown tool, not a rescue

- **Grobys et al. (2025), FMPM 39:443-476** (https://link.springer.com/article/10.1007/s11408-025-00474-9, full text fetched): Barroso–Santa-Clara scaling on weekly crypto momentum (2016-2023) lifts payoffs from "0.71% per week" plain to "1.86% per week" (8-week vol window), alphas 0.76-1.69%/week — **but no transaction costs**, tail risk unchanged ("it does not change the tail risk behavior"), and in the **Aug 2020–Dec 2023 subsample, plain momentum is negative and insignificant with no separate risk-managed result reported.**
- **Yang (2025), Finance Research Letters 85:107879** (abstract via https://colab.ws/articles/10.1016%2Fj.frl.2025.107879): risk management raises weekly momentum returns "from 3.18% to 3.47% and annualized Sharpe ratios from 1.12 to 1.42." Sample period unverifiable (paywalled).
- **Jones, Matsui & Knottenbelt, arXiv 2603.23480** (2024 backtest, BTC-heavy portfolio, 1bp costs): plain 20%-vol-targeting cut MaxDD from −33.0% to −15.8% **but reduced Sortino from 2.47 to 1.96** vs buy-and-hold; it only won risk-adjusted when an extra predictive signal was added.

**Verdict: do not lead with this.** Vol scaling verifiably halves drawdowns and helps full-sample Sharpe, but no verified source shows it rescuing a post-2022 signal, and at our size it is **unimplementable anyway**: one 0.01-ETH step is the minimum position — there is nothing below it to scale down to. Revisit when the account can hold 5+ steps.

---

## 5. Family 4 — Other retail-scale multi-day anomalies: mostly verified DEAD

- **Day-of-week effects: DEAD.** Scielo 2024 study (https://www.scielo.org.mx/scielo.php?script=sci_arttext&pid=S2683-26902024000100012), BTC/ETH Jul 2020–Dec 2023, GARCH: for Bitcoin "no discernible calendar anomalies, suggesting enhanced market efficiency."
- **Weekend premium: DEAD.** 2014-2024 study (https://ojs.bbwpublisher.com/index.php/PBES/article/view/11691): "no detectable weekend-weekday gap in average returns" across all subsamples; "quieter weekends rather than compensating return premia." (One low-prestige contrary study exists; its raw ~11bp/day gap is about one taker round-trip — not tradable.)
- **The famous 21:00-23:00 UTC overnight window: NO post-2022 evidence.** Quantpedia's sample ends Feb 3, 2022, zero costs; two taker crossings/day would eat it. Do not build on it.
- **Multi-day dip-buying / mean reversion: DEAD post-2022** (Quantpedia MIN result, §2.2) — consistent with this project's own MR struggles.
- **One survivor worth logging, not trading: Monday Asia-open trend concentration.** Concretum (https://concretumgroup.com/seasonality-in-bitcoin-intraday-trend-trading/), 2018-2025, effect "substantially more pronounced" 2020H2-2025: trend ensemble Sharpe ~1.6 vs ~0.8 long-only at same vol target, payoff concentrated Sunday ~7 PM ET through Monday. **Gross-of-fees only** — a candidate to measure in-house someday, not proven.

---

## 6. Phemex practicalities and the sizing math (all inputs verified)

### 6.1 Contract and cost facts

| Fact | Value | Source (fetched this session) |
|---|---|---|
| Fees | 0.01% maker / 0.06% taker | Phemex help center: "Maker fee rate: 0.0001 (0.01%), Taker fee rate: 0.0006 (0.06%)" |
| BTCUSDT min step | 0.001 BTC, min order value 1 USDT, 100x max | api.phemex.com/public/products: `"qtyStepSize": "0.001"` |
| ETHUSDT min step | 0.01 ETH | same API: `"qtyStepSize": "0.01"` |
| Funding | every 8h (00/08/16 UTC), longs pay when positive; only carry cost (no overnight fee) | Phemex help center + products API `"fundingInterval": 28800` |
| Live prices (Jul 5-6, 2026, Phemex API) | BTC $63,166; ETH $1,770.51 | api.phemex.com/md/v3/ticker/24hr |
| Live funding | BTC +0.0100%/8h (=3bp/day long cost); ETH +0.00227%/8h (=0.7bp/day) | same ticker: `"fundingRateRr":"0.0001"` / `"0.0000227"` |
| Typical funding regime | ~5.1% annualized avg (May 2024) ≈ 1.4bp/day; goes negative in bearish stretches | The Block/K33: https://www.theblock.co/post/314382/ |
| BTC realized vol now | 30d stdev of daily returns 1.51% (~29%/yr) — near historic lows | https://bitbo.io/volatility/; Fidelity: <50% vol "in just 5% of bitcoin's existence" |
| BTC daily ATR | 3.25% of price (point-in-time) | https://www.coinlore.com/coin/bitcoin/forecast/price-prediction |

So min-step notionals today: **BTC 0.001 = $63.17; ETH 0.01 = $17.71.**

### 6.2 Cost per multi-day trade vs move size

Maker-in / taker-out = **7bp RT** of notional (worst case taker-taker 12bp). A 5-day hold crosses ~15 funding events: at current rates ≈ 3.4bp (ETH) to 15bp (BTC) for a long; in the K33-average regime ≈ 7bp; occasionally negative (you get paid). **Total ≈ 10-22bp per round trip.** A 1-sigma 5-day BTC move at current vol is 1.51%×√5 ≈ 3.4% (340bp). Costs are ~3-6% of the signal's natural move scale — this is the structural reason slow trend survives costs where our intraday edges did not (the same 15bps that Han et al. charge per trade barely dents a 5-day holding-period strategy: Sharpe 1.56 → 1.51).

### 6.3 The daily-loss halt constraint (verified in our code)

- Halt fires on **realized** PnL only: `today_net = _compute_today_net_pnl(self.risk.closed_trades)` (bot.py:1298) vs `_should_halt_daily_loss(today_net, balance, threshold_pct=3.0)` (bot.py:94). Balance ~$57 → threshold ≈ **−$1.72** (matches the halt observed 7/5 per memory).
- Implication 1: an open multi-day position's unrealized adverse excursion **cannot** trip the halt. Good — normal 2-3% wiggles are safe while open.
- Implication 2: the moment a stop closes the position, the full loss lands in one day's budget — **shared with the 5m scalper.** One trend stop-out + a normal scalper losing day can combine to halt everything.
- Sizing: with a trend-appropriate disaster stop of 8%, max notional = $1.72×0.8 (leave scalper headroom) / 0.08 ≈ **$17** → exactly one 0.01-ETH step ($17.7, stop loss ≈ $1.42). BTC's 0.001 step ($63.2) would risk $5.05 at the same stop — **triple the halt threshold; BTC is unusable at this account size with honest trend stops.** "$15 at 10x" ($150 notional) would risk $12 — never do this at multi-day horizon. **Wider stops at longer horizons force smaller notional; leverage setting is just margin efficiency (0.01 ETH at 3x isolated uses ~$5.90 margin).**

### 6.4 What the dollars look like (honest)

At fixed $17.7 notional, ~48% deployment, if the strategy earned anything like Han's net 72.85%/yr it would make ~$13/yr — and history will not repeat that number (their sample includes two mega bull cycles; current vol is near historic lows). Realistic expectation: **single-digit dollars per year, ~$0.50-1.50/month scale.** The forward test is a process/cost/fidelity validation to earn the right to scale with the account — not an income strategy at $57.

---

## 7. Winner + pre-registered forward-test spec ("ETH-TSM-28")

**Winner: long-only daily-horizon time-series momentum (Han et al. 28/5 tercile rule), one 0.01-ETH position on ETHUSDT.**

Pre-registered spec — freeze before first trade, no mid-test parameter edits:

1. **Signal (daily, at 00:00 UTC close):** compute ETH's trailing 28-day return. Signal LONG if it falls in the **top tercile** of the expanding-window history of ETH 28-day returns (use all available daily history, ≥2 years, from exchange OHLCV). Otherwise FLAT. Never short. (Deviation from paper, declared: paper uses the value-weighted market portfolio, ~79% BTC+ETH; we express in ETH because it is the only min-step that fits the halt math. BTC and market-portfolio signals are logged in parallel for later comparison but not traded.)
2. **Entry:** on signal ON, post-only limit at best bid (maker, 1bp); if unfilled after 30 min, take (6bp). One position, LONG only, 0.01 ETH.
3. **Exit:** re-evaluate every day at 00:00 UTC with minimum hold 5 days (per the (28,5) rule); exit to flat when the 28-day return leaves the top tercile. Exit maker-first with 30-min taker fallback.
4. **Disaster stop:** exchange-side SL at −8% from entry (≈ $1.42 loss). This is a backstop, not the exit mechanism; expected exits are signal exits.
5. **Size/leverage:** 0.01 ETH fixed, isolated margin, 3x (≈$5.90 margin). No pyramiding, no vol-scaling (impossible below one step), no adding on drawdown.
6. **Cost budget:** ≤ 12bp fees + funding-as-realized per round trip. Log every funding payment.
7. **Duration & cadence:** 6 months. Expected ~1-3 entries/month (derived from "holds a position 48% of the sample period" with 5-day holding — estimate, not a verified paper statistic), so ~10-20 round trips.
8. **What must be true to believe it (pre-registered, in order of what the test can actually prove):**
   - (a) **Execution fidelity:** live fills within 15bp of the signal-day close on ≥80% of transitions; realized costs within budget. This is the primary testable claim at this sample size.
   - (b) **Behavioral fidelity:** long during ETH up-moves, flat during down-moves — live daily-return correlation with the paper-signal replica ≥0.9; any divergence investigated same week.
   - (c) **PnL sanity:** live net PnL within fees+slippage of the same-period paper signal. (With 10-20 trades, a t-test on expectancy is impossible — the strategy is believed on the published evidence, the test validates OUR implementation of it. Do not claim more.)
9. **Kill criteria (any one):** cumulative net ≤ **−$10**; OR two disaster-stop hits (means the stop is doing the exiting, which is not this strategy); OR signal-replica tracking error >0.1%/day for 2 consecutive weeks; OR the daily halt is tripped by a trend stop-out combining with scalper losses twice (means budget-sharing is broken — pause trend leg, fix budgeting first).
10. **Rollback:** flat the position, disable the slot; nothing else in the bot changes.

**Interactions with existing systems to settle before go:** (i) trend stop-out shares the $1.72 daily budget with the scalper — consider reserving $1.40 of the budget on days a trend position exists; (ii) exclude the trend slot from Kelly sizing and from the −$5 auto-demote logic (10-20 trades of a 48%-deployment strategy will look like noise to those rails); (iii) the 00:00 UTC daily cadence must survive Mac sleep — this is exactly the strategy shape least hurt by the known host-sleep issue (exchange SL + one decision/day), a genuine architectural fit.

---

## 8. UNVERIFIED / excluded (fetched-failed — do not rely on; flagged for manual download)

- **Rosen & Wang, SSRN 5732803 (Nov 2025)** — the strongest DECAY claim found: search snippets say BTC TSMOM predictors "have lost explanatory power" in recent years (weekly data 2011-2024). SSRN 403'd; **every number unverified.** This is the main open threat to the conclusion — worth a manual download before scaling beyond the forward test.
- Huang, Sangiorgi & Urquhart, SSRN 4825389 (volume-weighted TSMOM, snippet Sharpe 2.17) — 403, unverified.
- Grayscale "The Trend is Your Friend" (snippet: 50d-MA BTC Sharpe 1.9 vs 1.3) — 403, unverified.
- Le & Ruthbah, SSRN 4551518; Habeli et al., SSRN 5090097; Karassavidis et al., SSRN 5821842 — all 403, unverified.
- Zarattini full-paper details (fee bps, MDD, lookback list 5-360d) — abstract verified, details not.
- SG CTA/Trend index annual 2024/2025 figures — snippets only (the fetched BarclayHedge page gave only "YTD: 8.79%" as of Jul 6, 2026, traditional CTAs not crypto).

## 9. Source list (fetched & verified this session)

1. Han, Kang & Ryu (2023), SSRN 4675565 — PDF: acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/... [verified 3×, tables extracted]
2. Quantpedia, "Revisiting Trend-following and Mean-reversion Strategies in Bitcoin" (Sep 2024) [fetched 2×]
3. Zarattini, Pagani & Barbon (2025), SFI RP 25-80 — via ideas.repec.org/p/chf/rpseri/rp2580.html + concretumgroup.com [abstract verified 2×]
4. Bui & Nguyen (2026), arXiv 2602.11708 [fetched 2×; quality-flagged]
5. Man AHL, "In Crypto We Trend" (Dec 2024), man.com/insights/in-crypto-we-trend [fetched 2×]
6. Grobys et al. (2025), FMPM 39:443-476, link.springer.com/article/10.1007/s11408-025-00474-9 [full text fetched]
7. Yang (2025), FRL 85:107879 via colab.ws mirror [abstract only]
8. Jones, Matsui & Knottenbelt, arXiv 2603.23480 [full HTML fetched]
9. Borri, Liu, Tsyvinski & Wu, arXiv 2510.14435 [fetched]
10. Concretum, "Seasonality in Bitcoin Intraday Trend Trading" [fetched]
11. Scielo 2024 calendar-anomaly study; 12. BBW weekend-effect study 2014-2024 [both fetched]
13. Phemex help center (fees, funding) + api.phemex.com/public/products + /md/v3/ticker/24hr [fetched live]
14. The Block/K33 funding-rate article; 15. Fidelity Digital Assets vol note; 16. bitbo.io/volatility; 17. coinlore.com BTC ATR; 18. HedgeNordic Anna Fund; 19. BarclayHedge SG CTA index page; 20. Quantpedia "Silicon vs. Satoshi"; 21. odaily.news Gate turtle study; 22. Quantpedia overnight-anomaly page (pre-2022 only) [all fetched]

Internal code facts: bot.py:94 (`_should_halt_daily_loss`, 3% threshold), bot.py:1298 (realized-only `today_net`), read this session.
