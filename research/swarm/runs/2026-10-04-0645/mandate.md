# Desk mandate — run 2026-10-04-0645

Clock: now = 2026-10-04T13:45:39Z (6:45 AM PT, Sunday 2026-10-04). kb_check status: **KB OK** (verbatim output at the bottom).

Governing documents: `research/swarm/kb/CONSTRAINTS.md`, `research/swarm/kb/STANDARDS.md`, `research/swarm/kb/DATA.md`. Where this mandate and those files disagree, the kb files win.

## 1. Purpose

The desk exists to **grow a small account**. That goal is the desk's purpose. It is **not** a screening threshold.

The owner's long-term aim, recorded 2026-09-17 in his words ("keep it in mind, don't set it yet"), is +10% account ROI per day. The desk works toward that aim only by compounding real, verified edges. It is never a bar for judging any thesis. It also never justifies using leverage, size or aggression in place of an edge.

**The pass bar does not change:** per-trade net expectancy must be > 0 after `c`, and the 95% bootstrap CI must exclude zero. That means all five CONSTRAINTS "viable" criteria:
1. Train-era screen: n >= 30, and the bootstrap CI95 of net bps after `c` excludes 0 (`bootstrap_ci.mean_ci`).
2. Observed WR >= `fee_math.p_star` for the spec's TP.
3. Time-to-verdict at n=50 is <= 26 weeks at the expected frequency (`fee_math.time_to_verdict_weeks`).
4. Every symbol in the universe passes `fee_math.lot_check` at $200 notional.
5. The signal can be computed on closed bars from data the bot actually has.

No daily-ROI target is applied to any thesis in this run.

## 2. Capital and sizing

- Design basis: **$200** of capital.
- Screen position size: `fee_math.position_notional()` returns `200.0` USD notional, which is 10% margin at 10x. Read this from the tool, not by hand.
- No more than two paper slots at this size. No cross-sectional baskets.
- Lot minimums are verbatim from `fee_math.LOT_MIN_USD`: `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`. `minOrderValueRv` is 1 USDT.
- `fee_math.lot_check(symbol, fee_math.position_notional())` run this session:
  - BTC `{'ok': True, 'lots': 2, 'lot_usd': 77.74}`
  - ETH `{'ok': True, 'lots': 8, 'lot_usd': 24.9738}`
  - SOL `{'ok': True, 'lots': 197, 'lot_usd': 1.0143}`
  - XRP `{'ok': True, 'lots': 199, 'lot_usd': 1.0044}`
  - DOGE `{'ok': True, 'lots': 199, 'lot_usd': 1.001}`
- Any other symbol must be run through `lot_check` before freeze.
- Every spec carries `max_concurrent = fee_math.max_concurrent(sl_bps)`, filled in by `registrar.freeze` (STANDARDS #17).
- Every symbol must pass `universe_check` before freeze (STANDARDS #18).

## 3. Minimum net edge after costs

- `c = 11.5 bps` (`fee_math.C_BPS`). It is made of:
  - 7.0 bps round-trip fees: maker entry plus taker exit at VIP-0 (`fee_math.FEES_RT_BPS`).
  - 4.5 bps measured adverse selection after fill (`fee_math.ADVERSE_BPS`).
- Every thesis must show net bps per trade > 0 **after** this `c`, with the CI95 excluding 0.
- Break-even win rate for a symmetric TP/SL of `x` bps is `fee_math.p_star(x)`. Command run this session:
  `python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"`
  Output, verbatim:
  ```
  {100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
  ```
- **Target ladder: moves of 100-300 bps.** In that range p* is about 52-56% (output above). That is a winnable band.
- Smaller targets are fee-trapped. CONSTRAINTS quotes p* = 73.0% at 25 bps and 61.5% at 50 bps, so sub-0.1% moves cannot pay.
- Any non-symmetric geometry must take its break-even from `fee_math` / `screen` output. Never hand-derive it.

## 4. Horizons in scope

- **In scope:** intraday to multi-day holds, roughly 1h bars up to several days.
- **Explicitly NOT in scope:** scalping, meaning sub-hour holds or targets under 100 bps.
- **Explicitly IN scope:** event-driven theses (scheduled or detectable events with a named forced counterparty, STANDARDS #1).
- **At least two analyst lenses must target holds > 8h.**
  - Any such hold crosses an 8h funding settlement. Funding must be accounted for at every settlement the position spans.
  - Load funding with `load_data.load_funding(symbol, "train")`, or `load_reference_funding` for reference symbols.
  - Per CONSTRAINTS, BTC funding is about +0.01% per 8h, and meme perps are often negative.
  - Owner directive (STANDARDS #14): funding / XS / OI is **not** an edge source to hunt. Funding enters only as a cost or carry adjustment.

## 5. Execution reality of the Phmex-S bot (from CONSTRAINTS)

- **5-minute poller.** It cannot react faster than a minute.
- **Entries are maker limit orders.** Real maker fill rate is about 27%, and misses are adversely selected. **Exits are taker.**
- Simulated fills are screening-grade upper bounds. The forward test is the only adjudicator (STANDARDS #10).
- Order-book snapshots: every 60s, depth 5, BTC/ETH/INJ/ARB only. There is no streaming book.
- **The Mac may sleep.** Slow horizons (hours to days) tolerate that; 5-minute horizons do not.
- **Signals must use closed bars only** (STANDARDS #4). A live slot reading the forming bar reproduces only about 40% of closed-bar replays.
- Paper slots:
  - run on the live feed with a `.paper` sentinel;
  - are graded daily at 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`;
  - are killed with `touch .kill_<slot>`.

## 6. Datasets and train/holdout boundaries (from `research/swarm/kb/DATA.md`)

Load data only through `research.swarm.lib.load_data`. Never read the caches by hand.

| dataset key | path | coverage | timeframes | train ends |
|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC; funding `funding_<SYM>_USDT_USDT.json` | 1m, 5m, 1h | ≈ 2026-08-10 (holdout after) |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols: 1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP; 1h 2025-06-27 → 2026-08-01 | 1h (5m partial) | ≈ 2026-04-24 |

- **Use `long_1h` for multi-day or event-driven theses.**
- **GIGGLE is delisted** (DATA.md 2026-09-21 note). The screenable `long_1h` universe is the other 18 symbols. `universe_check` must be run before freeze.
- **Cross-dataset holdout caveat.** The `long_1h` holdout runs from about 2026-04-23 to 2026-08-01, and it overlaps `mr_edge` train data. So a `long_1h` thesis may not use any `mr_edge` data dated on or after 2026-04-23, in any probe or signal.
- **Reference symbols** (for example BTC as a driver) load only through `load_data.load_reference` / `load_reference_funding`. Never use `load_ohlcv`/`load_funding` with an explicit era inside a signal (STANDARDS #16).
- **Holdout is never read in this run.**
  - No `era="holdout"` or `era="all"`.
  - No committee token.
  - No direct cache reads.
  - No `load_data.fetch_ohlcv_ccxt`. It is committee-token gated and belongs to the build stage only.
- Holdout is the final 25% of each dataset's range. It is read once, later, by the build stage.

Other bot-collected data (exploratory only; not loadable by `load_data`):
- `logs/l2_ticks/<SYM>/<date>.jsonl.gz`: BTC/ETH/INJ/ARB, 2026-07-13 → 09-10
- `logs/flow_capture.jsonl`: 2026-05-11 → 09-09
- `logs/entry_snapshots.jsonl`: 2026-04-07 → 09-14

## 7. Gatekeeper watch list — 15 DEAD_LIST rows most likely to be relabeled this run

These rows are a filter, **not ideas** (STANDARDS #2, #13). Every thesis must cite its nearest row(s) by number and explain how its mechanism differs. Source: `research/swarm/kb/DEAD_LIST.md`.

| row | 5-word gist |
|---|---|
| 3 | 1h vol-expansion fade, selection-biased |
| 4 | Naked funding short = price drift |
| 6 | Liquidation-cascade reversion; high-vol continues |
| 7 | Calendar/time-of-day/weekend effects null |
| 13 | BTC time-series momentum fails deflation |
| 19 | Token-unlock short, -86.6% drawdown |
| 76 | Multi-day mean reversion dead post-2022 |
| 83 | Funding z-score contrarian, R² 0.003 |
| 84 | FOMC/CPI first-candle momentum, unverified |
| 106 | BTC shock lag into alts negative |
| 107 | ETH/BTC regime rotation, fully negative |
| 110 | Liquidation-cascade continuation, fully negative |
| 111 | Vol-scaled continuation, CI straddles zero |
| 113 | Window continuation (brrny), CI straddles |
| 114 | Stop-sweep exhaustion fade, CI straddles |

Also in force (STANDARDS #14), no re-proposals of:
- demoted books (main live, ST2.0, 5m_MR live, Donchian live);
- the BTC blacklist;
- gate loosening;
- universe swaps without a new mechanism;
- the funding/XS/OI hunt.

## 8. kb_check

Command: `python3 -m research.swarm.lib.kb_check` (exit code 0)

```
KB OK
```
