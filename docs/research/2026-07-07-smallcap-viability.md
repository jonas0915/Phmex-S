# Small-Cap Perp Viability — Go/No-Go
**Date:** July 7, 2026 (~9:21 PM PT market snapshot) · **Status:** READ-ONLY research · **Verdict: NO-GO**

Owner thesis under test: more volatility → bigger % moves → the ~1.2%-ROI round-trip fee hurdle matters less.

## 1. Our own history by liquidity tier
Source: `~/Desktop/Phmex-S/trading_state.json` (708 closed trades; net_pnl where present [392 trades], pnl_usdt otherwise).
Tiers assigned by **current** Phemex 24h turnover (`/md/v2/ticker/24hr/all`, fetched this session).

| Tier (24h vol) | n | WR | Net PnL | Avg/trade |
|---|---|---|---|---|
| Major (>$50M): BTC, ETH, SOL | 243 | 42.8% | −$15.05 | −$0.062 |
| Mid ($10–50M): XRP, SUI, BNB, DOGE, ADA, LINK | 200 | 42.5% | −$12.17 | −$0.061 |
| Small (<$10M): 30 symbols | 258 | 46.1% | −$23.14 | −$0.090 |
| Unlisted today (TON, ASTER) | 7 (n<30, inconclusive) | 42.9% | −$2.98 | −$0.426 |

- Small tier is the **worst** avg/trade, not the best. Small ex-blacklist-5 (TRUMP/FET/TIA/NEAR/OP removed): n=211, WR 54.5%, **+$0.14 total (+$0.0006/trade)** — breakeven, not an edge.
- The blacklist-5 alone: 47 trades, **−$23.27** — consistent with the March analysis (cutting them flipped −$20.18 → +$3.09). Small/mid caps were the documented loss engine.
- Caveat: tiering uses today's volume; some names (OP, NEAR, INJ) were larger when traded. Directionally this flatters the small tier, since shrinking books are worse now than when we traded them.

## 2. Spread/depth reality (candidate small caps, $500K–$3M 24h vol, not currently traded)
Source: `/md/v2/orderbook` per symbol, fetched this session. Depth = bid+ask notional within 0.1% of mid.

| Symbol | 24h vol | Spread % | Depth @0.1% |
|---|---|---|---|
| YFI | $2.89M | 0.096% | $2,662 |
| u1000SHIB | $2.12M | 0.047% | $17,153 |
| FARTCOIN | $2.00M | 0.135% | $809 |
| UNI | $1.99M | 0.062% | $6,490 |
| PUMP | $1.76M | 0.065% | $257 |
| PENGU | $1.72M | 0.032% | $5,650 |
| LDO | $1.54M | 0.276% | $0 |
| JUP | $1.38M | 0.044% | $3,435 |
| ORDI | $1.43M | 0.029% | $2,211 |
| ICP | $1.27M | 0.183% | $7,816 |
| **BTC (ref)** | $272M | **0.0002%** | **$2.01M** |
| **ETH (ref)** | $65M | **0.0006%** | **$3.15M** |
| **SOL (ref)** | $56M | **0.0127%** | **$1.18M** |

- Median small-cap spread **0.065%** (range 0.029–0.276%) vs effectively zero on BTC/ETH. Crossing the spread both ways costs 0.03–0.28% of price — **0.25x to 2.3x the entire 0.12% RT fee**, i.e. up to +2.8% ROI at 10x on top of the 1.2% hurdle.
- At $150 notional: a single order is 58% of PUMP's visible 0.1% depth, 19% of FARTCOIN's; LDO has **zero** liquidity within 0.1% of mid. Maker entries in books this thin are exactly the structural adverse-selection trap documented in the fill-rate research (only stale/toxic quotes get filled; thin books worsen it).

## 3. Volatility payoff
Source: `/exchange/public/md/v2/kline/last`, 5m bars, n=500 (~41 hrs), true-range % of close.

| Symbol | Mean 5m ATR% | ATR ÷ spread |
|---|---|---|
| BTC | 0.235% | 1476x |
| ETH | 0.289% | 507x |
| SOL | 0.295% | 23x |
| 10 small caps | 0.33–1.46% (mean 0.60%) | **2x–23x** |

Small caps move ~2.2x more per 5m bar (0.60% vs 0.27% majors) but carry ~20x the spread. The move-per-unit-friction ratio **collapses** from 500–1500x (BTC/ETH) to 2–23x. The extra move does not clear the extra friction — it's the same trade with a worse cost base.

## 4. Verdict: NO-GO
The thesis fails on all three legs:
1. **History:** small tier is our worst avg/trade (−$0.090 vs −$0.062 majors, n=258); even ex-blacklist it's breakeven (+$0.0006/trade, n=211), and the March blacklist finding stands — small caps supplied the losses, not the edge.
2. **Costs:** median 0.065% spread ≈ half-to-double the entire 0.12% RT fee; the thesis only counted the fee hurdle, not the spread hurdle that scales with illiquidity.
3. **Structure:** fill-rate research says the adverse-selection tension is structural and thin books worsen it. Depth of $257–$17K within 0.1% of mid vs our $150 clip means we ARE the book.

Five key numbers: small-tier avg **−$0.090/trade** (n=258) · blacklist-5 **−$23.27** of lifetime −$53.34 · median small-cap spread **0.065%** vs 0.12% RT fee · depth @0.1% **$0–$17K** vs $1.2–3.2M majors · ATR/spread **2–23x** vs 507–1476x on ETH/BTC.

**Conditional note:** the current scanner ($3M min volume, ~12 symbols, blacklist cleared 6/30) already reaches into the small tier (INJ +$3.06/30, DOGE +$3.39/27 — both n<30, inconclusive). Recommendation: keep the $3M volume floor as-is; do **not** lower it into the $500K–$3M band. No paper slot warranted — there is no cost model under which this band clears its own friction at our size.

*All numbers computed this session from the cited files/endpoints. Cross-check against lessons.md before acting.*
