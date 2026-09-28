# Donchian trend strategy at 5x leverage: test and verification report (Sun 9/27/2026)

Owner request, 9/27: "run an extensive testing, backtesting and verification of the donchian on 5x leverage."
No bot code, state, `.env` or order was touched. This was research only.

## Bottom line

- **5x does not break the strategy.** Across 10 years of history it was never liquidated, and a code audit found no look-ahead and no bug.
- **5x does not improve the strategy either.** Risk-adjusted return (Sharpe) is identical at every leverage level: BTC 1.15, ETH 0.89. Leverage only makes the same bet bigger.
- **The big long-run numbers come from 2016–2021.** Since the strategy was published in 2025, 5x BTC has lost money and trailed simply holding the same average exposure. ETH's recent record is mixed.
- **Expect to lose two-thirds to three-quarters of the account at some point.** 5x drawdowns are 75% (BTC) and 64% (ETH). There is about a 1-in-5 chance of falling below half your starting capital. Right now the 5x BTC book would be 56% below its 12/17/2024 peak (v2).
- **Recommendation:** treat leverage as a pure risk dial, not a return booster. At the 10/14 review, choose the worst drawdown you can live with (BTC / ETH):
  - 1x: about 21% / 17%
  - 2x: about 39% / 31%
  - 3x: about 54% / 44%
  - 5x: about 75% / 64%

  Five times the leverage does not bring five times the edge.

## Corrected results, full history

Rule: the bot's own `donchian_slot.run_history`. Script: `research/backtests/donchian_leverage_v2_2026_09_27.py`. Output: `research/backtests/donchian_leverage_v2_2026_09_27.json`.

**BTC** (10/12/2016 → 9/27/2026). Growth is annual (CAGR); drawdown is the worst peak-to-trough drop.

| Leverage | Yearly growth | Worst drawdown | Sharpe | Liquidated |
|---|---|---|---|---|
| 1x | 19.4% | 21.0% | 1.15 | no |
| 2x | 37.6% | 38.5% | 1.16 | no |
| 3x | 53.9% | 53.5% | 1.16 | no |
| 5x | 78.4% | 75.3% (75.5% at intraday lows) | 1.15 | no |
| 7x | 88.7% | 88.1% | 1.13 | no |
| 8x | wiped out | 100% | — | yes, 1/5/2017 |

**ETH** (8/13/2017 → 9/27/2026)

| Leverage | Yearly growth | Worst drawdown | Sharpe | Liquidated |
|---|---|---|---|---|
| 1x | 12.1% | 16.8% | 0.89 | no |
| 2x | 23.0% | 31.3% | 0.89 | no |
| 3x | 32.3% | 43.6% | 0.89 | no |
| 5x | 45.1% | 63.6% | 0.89 | no |
| 6x | 48.0% | 71.8% | 0.88 | no |
| 7x | 48.4% | 79.0% | 0.88 | no |
| 8x | 46.1% | 85.6% | 0.88 | no |

**5x by calendar year**
- **BTC:**
  - Good years: 2016 +103%, 2017 +676%, 2019 +159%, 2020 +490%, 2021 +7%, 2023 +140%, 2024 +133%.
  - Losing years: 2018 −33%, 2022 −42%, 2025 −45%.
  - 2026 to date: +5%.
- **ETH:**
  - Good years: 2017 +62%, 2018 +14%, 2019 +26%, 2020 +273%, 2021 +196%, 2023 +6%, 2024 +22%.
  - Losing year: 2022 −13%.
  - Flat: 2025 0%. 2026 to date: +3%.

## Recent periods: 5x against the alternatives

Total return over each window.

- **Hold** = buy and hold at 1x.
- **Matched hold** = holding the strategy's average 5x exposure (BTC 1.00x, ETH 0.60x) constantly, with the same costs.
- The drawdown in brackets belongs to the 5x rule.

| Window | BTC hold | BTC 1x rule | BTC 5x rule | BTC matched hold | ETH hold | ETH 5x rule | ETH matched hold |
|---|---|---|---|---|---|---|---|
| Phemex era, 11/4/2022 → now | +300% | +44% | +181% (DD 67%) | +199% | +64% | +16% (DD 63%) | +36% |
| After publication, 4/1/2025 → now | −1% | −1% | **−18%** (DD 61%) | −8% | +41% | +33% | +43% |
| Bear, 8/1/2025 → 7/15/2026 | −43% | −11% | **−49%** | −48% | −45% | −26% | −24% |
| Last 12 months | −23% | −4% | −24% (DD 57%) | −29% | −33% | −21% | −15% |

- At 1x, the rule's real value shows in bear markets: over the bear window BTC lost −11% against −43% for holding.
- At 5x, BTC's protection is multiplied away: the 5x rule lost −49%, more than holding BTC (−43%). ETH at 5x still lost less than holding ETH (−26% vs −45%), but no less than the matched hold (−24%).

## The six independent tests

These ran on the **v1** backtest, before the audit's fixes. v1 re-levered positions daily and assumed early funding, which made it slightly more optimistic. Their conclusions hold, and v2 re-derives the headline figures above. Exact percentages here can differ by a few points from v2.

1. **Rolling windows** (every 1-year and 2-year period)
   - At 5x, about a third of 1-year periods lose money (36% BTC, 35% ETH).
   - About a quarter of years see a drawdown over 50%.
   - About 80–85% of BTC 5x start dates from 2021 onward end behind buy-and-hold (v2: 382 of 2,095 daily start dates end ahead).
   - The BTC 5x book has been under water for 649 days, 56% below its 12/17/2024 peak (v2). The ETH 5x book: 930 days, 50% below its 3/11/2024 peak (v2).
2. **Crash and liquidation stress**
   - Using Phemex's own perpetual wicks (checked to the 1-minute level), nothing is liquidated at 5x.
   - Closest calls:
     - 1/5/2017: 67% of the liquidation cushion used.
     - 10/10/2025: 61% of the cushion used, down 60% at the low, at 3.66x exposure.
   - A one-day BTC drop of about 23% at peak exposure would wipe the account.
   - It survived COVID (3/12/2020) mainly because it happened to be out of the market.
3. **Statistics**
   - The strict deflated-Sharpe bar (0.95, the one that killed BTC-TSM in July), assuming 37 trials, passes on the full history for BTC (0.983) and only just for ETH (0.951). With 100 trials, ETH fails (0.921). It **fails from 2022 on** (BTC 0.483, ETH 0.363).
   - The edge over a matched hold is not proven under the repo's required method: the independent bootstrap's confidence range includes zero. A paired bootstrap comes close to passing (BTC P = 0.048, ETH P = 0.066), so the timing may add a little, but it is not established.
   - At 5x there is about a 1-in-5 chance of falling below half the starting capital (BTC 17.5%, ETH 21.0%) and a 22–28% chance of losing money in any given year.
4. **Sensitivity**
   - The rule's settings don't matter much.
   - The weight cap never binds: max weight is 0.85 BTC and 0.58 ETH, so peak exposure at 5x is 4.3x and 2.9x.
   - Most fragile to **funding**. In v2, doubling funding cuts BTC 5x to 43% a year, and ETH over the Phemex era to −7% a year.
   - Returns show diminishing gains from more leverage, and where they peak depends on the window: between 3x and 7x in v2. Since 11/2022 BTC peaks at about 5.5x and ETH at about 3x. Past the peak, extra leverage adds only drawdown.
5. **Out of sample**
   - Since publication, BTC 5x lost money and trailed a matched hold: −18% against −8% (v2 table above).
   - Across 8 other coins, the frozen rule beat buy-and-hold's risk-adjusted return on 5 of them. That's encouraging for the rule, but no single coin is statistically significant, and leverage added nothing on any of them.
   - This was a test only. It is not a proposal to trade those coins.
6. **Code audit**
   - No look-ahead: perturbing future prices never changes past weights.
   - Filling at the daily close is fair, since the bot trades just after the 00:00 UTC close (median close-to-next-open gap: BTC 0.0002%, ETH 0.003%).
   - The rule matches the spec.
   - It found three problems that made v1 too optimistic, all fixed in v2:
     - Funding before 2022 was assumed at about half its real level.
     - Positions were re-levered daily.
     - Two bad Coinbase lows ($0.06 and $0.10).

## Verification

- **Final check:** a separate agent cross-checked about 150 numbers in this report against the result files and confirmed about 138. Every mismatch it found has been corrected above.

- **Two blind reimplementations:** the v1 backtest was rebuilt blind by a separate agent and matched to the cent. The v2 corrected figures match the audit agent's independent reimplementation: ETH exactly (45.1% / 46.6%), BTC within 0.3 points (v2 78.4% / 83.7% vs the audit's 78.5% / 84.0%).
- **Agreement with the July research:** at 1x over the same bear window, v2 gives BTC −11.3% against the July research's −11.5%, and ETH −4.1% against −4.9%. v1 gave −11.1% and −3.9%.
- **Match to the live bot:** backtest weights match the live bot's signal file within 0.003 (BTC) and 0.048 (ETH) over the 74 paper days.
- **Remaining assumptions:**
  - ETH funding before 4/30/2019 uses BTC's BitMEX rate as a stand-in (625 days).
  - The maintenance margin is 0.5%; Phemex's real figure is 0.33%, so this is conservative.
  - Daily bars are used. The 1-minute check showed daily lows equal the true intraday lows on the 20 worst days since 2022.
  - The strategy's parameters were published on 2015–2025 data, so most of the full-history figures are in-sample.
