# R4 Web Research: VWAP + 9/15 SMA Cross (5-min, long-only) — Verified Evidence Review

Date: 2026-07-06 (overnight batch dated 2026-07-05)
Question: does any verified published evidence support positive expectancy for the mechanical rule
"5-min chart, long when price > session VWAP and 9-SMA crosses above 15-SMA (or on retest of the cross)"
net of OUR costs (crypto perps, $10-15/trade, 6bp taker / 1bp maker, 60s decision cycle, maker-only entries,
measured -4 to -5bp adverse selection on fills)?

## Verification protocol and fabrications caught

Every statistic below was read from a primary source fetched this session (PDF full text extracted locally, or
publisher abstract page). Search-engine summary claims that could not be confirmed on the cited page were EXCLUDED.
Two fabrications were caught in the search layer itself during this research — the exact failure pattern this
project has flagged before:

1. FABRICATED: "A 2019 study in the Journal of Financial Markets found VWAP 14% more accurate than 20-SMA for
   support/resistance." Attributed to tradervue.com/blog/vwap-indicator. Fetched the page: it contains no such
   study, no such number, no academic citation at all. Excluded.
2. FABRICATED: "2022 QuantConnect backtest on 100 liquid NASDAQ stocks: 63% win rate shorting the 2-sigma VWAP
   band." Attributed to crosstrade.io/learn/trading-strategies/vwap-reversion. Fetched the page: no QuantConnect
   study, no 63% figure, no citation. Excluded.

Also unverifiable and excluded from conclusions: the widely-repeated "Greenwich Associates 2022: 72% of
institutional equity traders use VWAP as primary benchmark" — it appears only in blogs; the primary report was
not reachable.

Local receipts (extracted full texts): scratchpad tool-results hu.txt (Hudson-Urquhart), orb.txt (Zarattini et
al.), mnq.txt (Mesfin), madhavan.txt (Madhavan 2002), vwappop.txt (Warrior Trading VWAP Pop deck).

---

## 1. Provenance: where this strategy is taught

VERIFIED — this is a retail day-trading curriculum staple, taught discretionarily, with zero published
performance evidence in any source found.

- Warrior Trading "VWAP Pop" (primary PDF, media.warriortrading.com/2017/03/VWAP-Pop.pdf, full text extracted).
  Tools: "A Stock in play!! / VWAP / 9 EMA / 20 EMA". Setup, quoted: "A stock IN PLAY must clear through the
  VWAP, 9, and 20 EMA's / Allow a pullback to take place / Pullback should at least retest the VWAP, if not both
  9, 20 EMA's... Begin to establish a long position as the price action clears the high of the pivot candle."
  Its causal story, quoted: "Firms/Traders with large orders to fill are penalized if they execute an order above
  VWAP... This price action represents real and natural buying around VWAP." The deck contains NO backtest, NO
  win rate, NO statistics of any kind — chart examples only.
- howtotrade.com "The 9 EMA" (fetched): teaches both a 9/15 EMA crossover ("when the 9 EMA crosses above the
  15 EMA, this implies a bullish trend", entry after a confirming candlestick) and a 9 EMA x VWAP cross strategy.
  Fetch verdict, quoted from the page analysis: "None provided... zero backtest statistics, win rates, or
  performance metrics."
- The owner's exact rule (9/15 SMA cross + price>VWAP filter) is a minor variant of these. NO rigorous published
  test of this specific combination — academic or serious practitioner — was found anywhere. Not one.

Key nuance: the canonical taught version (VWAP Pop) is (a) a PULLBACK-RETEST entry, (b) on a hand-picked
"stock in play" (news/volume catalyst), (c) with discretionary pivot-candle confirmation. The mechanical
crossover version the bot would run strips out exactly the components that section 2 suggests carry the edge.

## 2. Simple MA crossover / mechanical intraday signals, net of costs

- Schulmeister (2009), Review of Financial Economics 18(4) 190-201, abstract verified via EconPapers, quoted:
  "the profitability of 2580 technical models has steadily declined since 1960, and has been unprofitable since
  the early 1990s. However, when based on 30-minutes-data the same models produce an average gross return of 7.2%
  per year between 1983 and 2007... Between 2001 and 2007 the 2580 models perform worse than over the 1980s and
  1990s." Note: 7.2% is GROSS, pre-2008, S&P futures, 30-min bars. The one classic pro-intraday-TA citation is
  gross-of-costs and its own abstract reports decay in the final subperiod.
- Mesfin (2026), "Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification
  Study" (arXiv 2605.04004, full text extracted; independent researcher, NOT peer-reviewed, but transparent
  walk-forward methodology). 947 RTH days of 5-minute MNQ bars, 2021-2025, 14 signal families, fixed 2-point
  round-trip friction, acceptance = T>=2.0 out-of-sample + >=30 trades + positive net + multi-year stability.
  Abstract, quoted: "No tested signal survives these combined criteria simultaneously. The gross edge available
  to next-bar-open systematic execution is structurally constrained to approximately 0.07 to 1.50 points across
  all signal families — a ceiling that is insufficient to clear two-point round-trip transaction costs."
  Conclusion, quoted: "Strategies that rely on next-bar-open execution following a bar-close signal face a
  structural handicap... Strategies that have appeared to work in retail literature may have benefited from:
  (1) use of bid-mid or unrealistic fill prices, (2) failure to account for full round-trip costs, (3)
  optimization on in-sample data... (4) reporting only positive results." The only variants that cleared friction
  held 12-15 bars (60-75 min) rather than 1-6 bars.
- Crypto, daily: Hudson & Urquhart, "Technical trading and cryptocurrencies", Annals of Operations Research 297
  (2021), full text extracted. DAILY data (Bitcoin from 7/18/2010 CoinDesk / 12/1/2012 Bitstamp; Litecoin 4/28/2013,
  Ripple 8/4/2013, Ethereum 8/7/2015; through 12/31/2017), ~15,000 rules. Best rules 13.42% (CoinDesk) to 22.15%
  (Ethereum) annualized; breakeven transaction costs quoted: "The breakeven transaction costs range 7.88 basis
  points for the support-resistance rule in Ripple... as high as 66.41 and 57.51 basis points" (CoinDesk,
  Bitstamp) — versus ~50bp actual BTC costs at the time. And critically: "does not offer any positive returns in
  the out-of-sample period" for Bitcoin. So even the flagship pro-TA crypto paper: daily frequency, breakeven
  costs that would NOT survive being spread across 5-min-frequency trade counts, and Bitcoin predictability dead
  out-of-sample.
- Crypto, intraday: Svogun & Bazan-Palomino, "Technical analysis in cryptocurrency markets: Do transaction costs
  and bubbles matter?", J. Int. Financial Markets, Institutions & Money 79 (2022), abstract verified via RePEc,
  quoted: "We study the daily and 1-minute returns of 69 technical trade rules in the form of moving average and
  breakout strategies... For the most profitable trade rules, we find that bubble periods increase the likelihood
  that Ethereum, Ripple and Litecoin beat buy-and-hold, but not Bitcoin and Bitcoin Cash. Transaction costs
  decrease this likelihood for Ripple and Litecoin, but increase it for Bitcoin and Ethereum." Translation:
  MA-rule profitability at 1-min is conditional, coin-specific, and bubble-regime-dependent — not a stable edge.
  (Full text paywalled; only abstract-level claims used.)
- The equities counter-example that proves the real lesson: Zarattini, Barbon & Aziz, "A Profitable Day Trading
  Strategy For The U.S. Equity Market" (SSRN 4729284, full text extracted). 5-min opening range breakout,
  2016-2023, 7,000+ stocks, $25,000 account, commission $0.0035/share (IB Pro tier), stop at the opposite side of
  the 5-min range. ORB applied to ALL stocks: "a Sharpe Ratio of 0.48, which was significantly lower than the
  0.78 Sharpe ratio for the S&P 500" — the raw 5-min price pattern UNDERPERFORMS passive. Only after filtering to
  "Stocks in Play" (relative volume >100%, price>$5, avg volume >1M, ATR>$0.50) does it produce "a total net
  performance of over 1,600%, with a Sharpe ratio of 2.81, and an annualized alpha of 36%". The edge lives in the
  catalyst/universe selection, not in the bar-pattern entry. A mechanical crossover bot has no equivalent of the
  stock-in-play filter on a fixed perp universe.

## 3. VWAP: measurable institutional behavior vs folklore

- VERIFIED as an institutional EXECUTION BENCHMARK: Madhavan (2002), "VWAP Strategies", Journal of Trading
  Spring 2002 pp. 32-39 (full text extracted), quoted: "It is common to evaluate the performance of traders by
  their ability to execute orders at prices better than the volume-weighted average price (VWAP) over the trading
  horizon. Berkowitz, Logue, and Noser [1988] regard the VWAP benchmark as a good approximation of the price for
  a passive trader." Also: "The uncritical use of VWAP as a benchmark can promote trading behavior that actually
  increases costs and risk." So: institutions really do anchor EXECUTION QUALITY MEASUREMENT to VWAP, and a whole
  algorithmic literature exists on tracking it (e.g., Bialkowski/Darolles/Le Fol "Decomposing volume for VWAP
  strategies").
- NOT VERIFIED anywhere: that this produces exploitable intraday support/resistance or that price>VWAP is a
  profitable trend filter. Madhavan says nothing about VWAP as support/resistance. No academic paper testing
  "VWAP as S/R" or "price-above-VWAP filter profitability" was found. The two blog statistics that claimed such
  evidence were both fabricated (see protocol section). The VWAP Pop deck's mechanism story (benchmark-penalized
  institutions passively buying near VWAP) is a plausible narrative FOR US EQUITIES with agency-execution flow —
  and even there it is untested folklore at the strategy level.
- Transfer to crypto perps: the causal mechanism itself is undocumented for our market. No verified source
  establishes that crypto perp flow is benchmark-executed against session VWAP the way institutional equity flow
  is (crypto has no market close, so "session VWAP" is an arbitrary anchor; the taught strategies all assume the
  9:30-4:00 equity session structure — opening auction, stock-in-play catalyst, high-of-day magnet). The VWAP
  filter's justification is therefore weakest precisely in our market.

## 4. Retest entry vs breakout entry

- The ONLY verified quantitative head-to-head found: Mesfin (2026), Table 3 (5-min MNQ, after 2-pt friction):
  immediate ORB long at bar+15 horizon: +2.82 net points, T=1.50, 55.5% win rate (still FAIL vs T>=2);
  pullback/retest entry variant: quoted — "produces a catastrophic 80.7% stop-out rate at a 20-point stop,
  yielding -4.44 net and T = -1.27" (19.3% win rate, 83 trades). His reading, quoted: "In MNQ, a high proportion
  of apparent breakouts simply fail and reverse, making pullback entries systematically wrong." One market, one
  parameterization, not peer-reviewed — but it is actual data, and it points AGAINST the retest variant.
- Everything else on "break and retest is superior" (acy.com, liquidityfinder, fxopen, capital.com, etc.) is
  assertion without any backtest. No verified evidence that retest entries beat breakout entries exists in what
  was found; the one measured comparison says the opposite. Verdict: retest superiority is UNVERIFIED folklore.

## 5. Transfer to our context, per finding

Our frictions: 1bp maker / 6bp taker per side; maker-only entries with MEASURED -4 to -5bp adverse selection at
fill (internal, 148 htf_l2 fills, cluster-robust); 60s decision cycle = bar-close signal + delayed execution;
$10-15 notional. Effective round trip (maker in / mixed out + adverse selection) is roughly 7-15bp+ — on a 5-min
crypto bar whose typical range is a few bp to a few dozen bp.

- Schulmeister: gross-only, 30-min bars, pre-2008 index futures, decaying in its own final window. Transfer:
  none as support; historical curiosity.
- Mesfin: closest structural analog to our bot (5-min bars, bar-close signal, next-bar execution, honest
  friction). His finding — gross OHLCV edge 0.07-1.50 pts vs 2 pts friction — maps directly onto our measured
  reality (main bot htf_l2: gross-positive +$3.47/159 trades, fees flip it negative; 2026-06-29 audit). Strong
  negative transfer. Caveat: not peer-reviewed, single instrument.
- Hudson & Urquhart: DAILY crypto, best breakevens 8-66bp per round trip, Bitcoin dead OOS. At 5-min frequency
  the per-trade edge shrinks while our ~7-15bp friction stays fixed; nothing in this paper supports a 5-min
  version. Negative-to-neutral transfer.
- Svogun & Bazan-Palomino: only intraday (1-min) crypto MA test found; profitability conditional on bubble
  regimes and coin, not stable. Does not support a standing mechanical rule. Neutral-to-negative transfer.
- Zarattini et al.: the pattern-alone arm (all stocks) LOSES to passive even at $0.0035/share; edge appears only
  with catalyst selection. Our bot would run the pattern-alone arm on a fixed perp universe. Negative transfer
  for the mechanical version; mildly supportive if paired with a genuine "coin in play" activity filter (our
  scanner's volume/vol filters are a weak cousin).
- Madhavan/VWAP: benchmark anchoring is real in equities; S/R and trend-filter claims unverified anywhere;
  mechanism undocumented in crypto perps. The VWAP>price condition may still have value purely as a regime/trend
  proxy, but no verified source demonstrates it.
- Retest arm: the only data point says retest entries were the WORST variant tested. Also note our own adjacent
  internal result: main-bot missed-fills study (2026-07-02) found chased/returned entries were not missed winners.
- One more internal collision: the owner's rule is a MOMENTUM entry (buy strength above VWAP), and our measured
  -4 to -5bp adverse selection is on maker fills — posting a bid into upward momentum means we fill mostly when
  price comes back DOWN through us. A maker-only implementation of a momentum-crossover signal is structurally
  fighting itself: either we chase (taker, 6bp) or we get filled predominantly on the failures. This is the same
  fill-rate/adverse-selection tension already documented internally (2026-07-03 fill-rate research).

## Verdict

Does any verified evidence support positive expectancy for the mechanical 5-min "price>VWAP + 9/15 SMA cross"
long rule after our costs? NO. Strictly: the exact rule has never been rigorously tested in anything found
(that part is UNKNOWN — absence of test, not proof of loss), but every adjacent rigorous test points the same
direction — mechanical bar-pattern entries on 5-min data do not clear realistic friction (Mesfin; Zarattini's
all-stocks arm; H&U's daily-only breakevens; Svogun's regime-dependence), the VWAP-filter mechanism is
unverified even in equities and undocumented in crypto perps, and the retest variant has the single worst
verified datapoint. The strategy's teachers publish no performance evidence at all. Prior probability of
positive expectancy at our cost structure: low.

## What the forward test must measure to settle it

Run it as a paper/sim slot first (signal-tagged, no capital) — consistent with existing lab infrastructure:

1. Signal-conditional gross drift: mid-price move at +5/+15/+30/+60 min after each crossover event (price>VWAP,
   9/15 SMA cross on 5-min bars), in bps, with cluster-robust CI. This is THE number: if gross drift at the
   holdable horizon is under ~15bp, the strategy is dead before execution is even discussed.
2. Two entry arms in parallel: (a) enter at crossover bar close, (b) enter only on retest of the crossover
   level within N bars. Count how many retests never come (missed winners) vs how many retest fills are failures
   — this is the Mesfin 80.7%-stop-out question on our data.
3. Execution reality on the maker path: fill rate of a passive bid at signal time, time-to-fill, and adverse
   selection of those fills specifically (expect worse than the -4 to -5bp baseline, because the signal is
   momentum-long). Compare against a taker arm at 6bp to see which net is less bad.
4. Trade frequency and regime split: signals/day per symbol, and results split by trend/chop regime and by
   BTC vs alts — Svogun says regime will dominate.
5. Kill criteria set in advance: e.g., 100+ signals, gross drift CI excluding +15bp at every horizon, or net
   expectancy CI upper bound < 0 → close as null, do not iterate parameters (that is the multiple-comparisons
   trap Mesfin documents).

## Sources (all fetched this session)

- Warrior Trading, "VWAP Pop" deck: https://media.warriortrading.com/2017/03/VWAP-Pop.pdf (full text extracted)
- HowToTrade, "The 9 EMA": https://howtotrade.com/trading-strategies/9-ema/ (fetched; no stats present)
- Schulmeister (2009), Rev. Financial Economics 18(4):190-201, abstract: https://econpapers.repec.org/article/eeerevfin/v_3a18_3ay_3a2009_3ai_3a4_3ap_3a190-201.htm
- Mesfin (2026), arXiv 2605.04004: https://arxiv.org/pdf/2605.04004 (full text extracted)
- Hudson & Urquhart (2021), Annals of Operations Research 297: https://centaur.reading.ac.uk/85715/8/Hudson-Urquhart2019_Article_TechnicalTradingAndCryptocurre.pdf (full text extracted)
- Svogun & Bazan-Palomino (2022), JIFMIM 79, abstract: https://ideas.repec.org/a/eee/intfin/v79y2022ics1042443122000816.html
- Zarattini, Barbon & Aziz (2024), SSRN 4729284: https://www.wealth-lab.com/api/discussion/download/pdf/8007-ssrn-4729284-1-pdf (full text extracted)
- Madhavan (2002), "VWAP Strategies", J. of Trading Spring 2002: https://www.smallake.kr/wp-content/uploads/2016/03/TP_Spring_2002_Madhavan.pdf (full text extracted)
- Fabrication checks (claims NOT found on cited pages): https://www.tradervue.com/blog/vwap-indicator , https://crosstrade.io/learn/trading-strategies/vwap-reversion
