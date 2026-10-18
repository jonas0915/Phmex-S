# Desk mandate — run 2026-10-18-0300

Run id: 2026-10-18-0300. Clock: 2026-10-18T10:00:07Z (3:00 AM PT, Sunday 2026-10-18).
Governing documents: `research/swarm/kb/CONSTRAINTS.md`, `research/swarm/kb/STANDARDS.md`, `research/swarm/kb/DATA.md`, `research/swarm/kb/DEAD_LIST.md` (canonical if anything below differs).
kb_check status: **KB OK** (verbatim output at the bottom of this file).

## 1. Purpose

The desk exists to grow a small account. That is the desk's PURPOSE. It is not a screening threshold.

The owner's long-term aspiration, recorded 2026-09-17 in the owner's words ("keep it in mind, don't set it yet"), is +10% account ROI per day. The desk works toward it only by compounding real, verified edges. It is never a bar that a thesis is judged against. It never permits leverage or aggression as a substitute for edge.

The pass bar is unchanged: per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero, plus CONSTRAINTS "viable" items 1-5:
1. Train-era screen: n >= 30 and the bootstrap CI95 of net bps excludes 0 after `c`.
2. Observed WR >= p* for the spec's TP.
3. Time-to-verdict (n=50) <= 26 weeks at the expected frequency (`fee_math.time_to_verdict_weeks`).
4. Every symbol in the universe passes `lot_check` at $200 notional.
5. The signal can be computed on closed bars from data the bot actually has.

No daily-ROI target applies to any thesis in this run.

## 2. Capital and sizing

- Design basis: $200. Screen position size = `fee_math.position_notional()`. Output: `200.0` (command below). That is 10% margin at 10x.
- Two paper slots max at this size. No cross-sectional baskets.
- Lot minimums (USD per lot), verbatim from `fee_math.LOT_MIN_USD`: BTC 77.74, ETH 24.9738, SOL 1.0143, XRP 1.0044, DOGE 1.001.
- `lot_check` at $200 notional, run this session. Command: `python3 -c "from research.swarm.lib import fee_math as f; n=f.position_notional(); print(n, {s: f.lot_check(s, n) for s in f.LOT_MIN_USD})"`. Output:
  ```
  200.0 {'BTC': {'ok': True, 'lots': 2, 'lot_usd': 77.74}, 'ETH': {'ok': True, 'lots': 8, 'lot_usd': 24.9738}, 'SOL': {'ok': True, 'lots': 197, 'lot_usd': 1.0143}, 'XRP': {'ok': True, 'lots': 199, 'lot_usd': 1.0044}, 'DOGE': {'ok': True, 'lots': 199, 'lot_usd': 1.001}}
  ```
  Each thesis must run `lot_check` on every symbol in its own universe. The five above are only the symbols that `LOT_MIN_USD` lists.
- `max_concurrent = fee_math.max_concurrent(sl_bps)` is filled in by `registrar.freeze` (STANDARDS #17).
- Universe tradeability is checked with `research.swarm.lib.universe_check` before every freeze (STANDARDS #18). GIGGLE is delisted, so the screenable `long_1h` universe is 18 symbols.

## 3. Minimum net edge after c = 11.5 bps

Cost constants from `research.swarm.lib.fee_math`, printed this session: `FEES_RT_BPS` = 7.0 (maker entry / taker exit), `ADVERSE_BPS` = 4.5, `C_BPS` = 11.5. The minimum edge is: net expectancy per trade after subtracting c = 11.5 bps must be > 0, with the CI95 excluding 0. A gross move has to clear 11.5 bps before it counts at all. That is why sub-0.1% scalps are fee-trapped (CONSTRAINTS: p*(25 bps) = 73.0%, p*(50 bps) = 61.5%).

Required win rate for symmetric TP/SL on the target ladder. Command: `python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"`. Output (verbatim):
```
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```
Targets for this run are 100-300 bps moves, where p* runs from about 52% (300 bps) to about 56% (100 bps). A thesis's WR is compared against `fee_math.p_star(tp_bps)` for its own registered TP, never against a number from prose.

## 4. Horizons in scope

- IN scope: intraday through multi-day holds (hours to days) that aim for 100-300 bps moves.
- Explicitly NOT in scope: scalping (sub-0.1% targets, minute-scale holds).
- Explicitly IN scope: event-driven theses (scheduled or detectable events with a named forced counterparty).
- At least two analyst lenses must target holds > 8h. Any hold that crosses an 8h funding settlement must include funding in its net bps. Load it with `load_data.load_funding` (train era only), or with `load_reference_funding` for reference symbols. BTC is about +0.01%/8h. Meme perps are often negative.
- Owner directives still apply (STANDARDS #14). Do not re-propose demoted books (main live, ST2.0, 5m_MR live, Donchian live), the BTC blacklist, gate loosening, universe swaps without a new mechanism, or the funding/XS/OI hunt.

## 5. Execution reality (from CONSTRAINTS)

- The bot polls every 5 min, so nothing can react faster than a minute.
- Entries are maker limit orders. Real maker fill is about 27%, and misses are adversely selected. Exits are taker.
- Order book: snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. There is no streaming book.
- The Mac may sleep. Slow horizons (hours to days) tolerate that; 5-min horizons do not.
- Signals must use closed bars only. Forming-bar live slots reproduce only about 40% of closed-bar replays (STANDARDS #4).
- Paper slots run on the live feed with a `.paper` sentinel. They are graded daily at 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`. Kill a slot with `touch .kill_<slot>`.
- Simulated fills are upper bounds for screening only. The forward test is the only adjudicator (STANDARDS #10).

## 6. Datasets and train/holdout boundaries (from `research/swarm/kb/DATA.md`)

| key | path | symbols | timeframes | coverage | train ends |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 | 1m, 5m, 1h (+ funding json) | 2026-06-01 → 2026-09-02 23:55 UTC | ≈ 2026-08-10 |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 listed (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP); 18 screenable (GIGGLE delisted 2026-08-07) | 1h (5m partial) | 2025-06-27 → 2026-08-01 | ≈ 2026-04-24 |

- Holdout is the final 25% of each dataset's range. `load_data.holdout_start(t0, t1, frac=0.25)` computes the exact boundary.
- Use `long_1h` for multi-day and event-driven theses (DATA.md).
- **Holdout is NEVER read in this run.** Do not use era="holdout" or "all", the committee token, or direct cache reads. Do not call `load_data.fetch_ohlcv_ccxt`, which is committee-token gated and outside the research stage.
- Cross-dataset caveat: the `long_1h` holdout (about 2026-04-23 → 08-01) overlaps the `mr_edge` train window. A `long_1h` thesis may not use `mr_edge` data dated on or after 2026-04-23 in any probe or signal.
- Reference symbols must be loaded with `load_data.load_reference` / `load_reference_funding`, never with `load_ohlcv`/`load_funding` plus an explicit era (STANDARDS #16).
- Bot-collected logs (`logs/l2_ticks/`, `logs/flow_capture.jsonl`, `logs/entry_snapshots.jsonl`) are exploratory only and cannot be loaded through `load_data`.

## 7. Gatekeeper watch list: 15 DEAD_LIST rows most likely to be relabeled

These rows are the rejection filter for this run. They are NOT ideas. Gists are from `research/swarm/kb/DEAD_LIST.md`.

| row | gist (5 words) |
|---|---|
| 3 | 1h vol-expansion fade, selection-biased |
| 4 | Naked funding short = price drift |
| 6 | Liquidation-cascade reversion: high-vol continues |
| 7 | Calendar/time-of-day effects noise/decaying |
| 13 | BTC time-series momentum fails deflation |
| 19 | Token-unlock short: −86.6% drawdown |
| 76 | Multi-day mean reversion dead post-2022 |
| 78 | 1h Bollinger-squeeze breakout, selection bias |
| 83 | Funding z-score contrarian: R²≈0.003 |
| 84 | FOMC/CPI first-candle momentum, too rare |
| 106 | BTC-shock alt lag: negative CI |
| 107 | ETH/BTC regime rotation: negative CI |
| 110 | Liquidation-cascade continuation: negative CI |
| 113 | BRRNY window continuation: CI straddles |
| 114 | Stop-sweep exhaustion fade: CI straddles |

Every thesis must cite its nearest rows by number and explain why its mechanism differs (STANDARDS #13).

## 8. kb_check

Command: `python3 -m research.swarm.lib.kb_check`. Output (verbatim):
```
KB OK
```
