# MANDATE — run 2026-09-27-0300

kb_check status: **KB OK** (full output under "kb_check" below).
Clock: now = 2026-09-27T10:00:07Z (3:00 AM PT, 2026-09-27). Run args: `research/swarm/runs/2026-09-27-0300/launch_args.json` (max_analysts 8, max_screens 5, dry_run false).
Governing documents: `research/swarm/kb/CONSTRAINTS.md`, `research/swarm/kb/STANDARDS.md`, `research/swarm/kb/DATA.md` (canonical if anything here differs).

## 1. Purpose

The desk's PURPOSE is the owner's goal of growing a small account. That purpose is a direction, NOT a screening threshold.

The owner's ULTIMATE aspiration, recorded 2026-09-17 in the owner's words "keep it in mind, don't set it yet", is a large daily account return. The desk works toward it only by compounding real, verified edges. It is never a bar any thesis is judged against, and it never licenses leverage or aggression in place of edge. No daily-ROI target is applied to any thesis in this run, and none may be written into any thesis, spec, audit or report.

**The pass bar is, and stays**, CONSTRAINTS "What viable means" 1-5:
1. Train-era screen: n >= 30, and the 95% bootstrap CI of per-trade net bps (after c) excludes 0 (`bootstrap_ci.mean_ci`). The expectancy must be > 0.
2. Observed WR >= p* for the spec's TP (`fee_math.p_star`).
3. Time-to-verdict (n=50) <= 26 weeks at expected frequency (`fee_math.time_to_verdict_weeks`).
4. Every symbol in the universe passes `fee_math.lot_check` at $200 notional.
5. The signal is computable on closed bars from data the bot actually has.

## 2. Capital and sizing

- Design basis **$200**. Screen sizing = `fee_math.position_notional()`. Run output: `200.0` (10% margin at 10x). At most two paper slots at this size, and no cross-sectional baskets.
- Lot minimums come from `fee_math.LOT_MIN_USD` (run output, verbatim): `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`. `minOrderValueRv` is 1 USDT.
- `fee_math.lot_check(sym, fee_math.position_notional())` run output: `{'BTC': {'ok': True, 'lots': 2, 'lot_usd': 77.74}, 'ETH': {'ok': True, 'lots': 8, 'lot_usd': 24.9738}, 'SOL': {'ok': True, 'lots': 197, 'lot_usd': 1.0143}, 'XRP': {'ok': True, 'lots': 199, 'lot_usd': 1.0044}, 'DOGE': {'ok': True, 'lots': 199, 'lot_usd': 1.001}}`. Every other universe symbol must be checked by the thesis author with `lot_check`.
- Every spec carries `max_concurrent = fee_math.max_concurrent(sl_bps)`, filled by `registrar.freeze` (STANDARDS #17).
- Every universe symbol must be an active Phemex market (`research.swarm.lib.universe_check`, STANDARDS #18).

## 3. Minimum net edge after c

- Cost constants come from `fee_math` (run output): `FEES_RT_BPS = 7.0` (maker entry / taker exit), `ADVERSE_BPS = 4.5`, `C_BPS = 11.5`. A thesis needs positive per-trade net bps after this 11.5 bps and a CI95 that excludes 0. No extra margin above that is imposed.
- CONSTRAINTS justification: scalping is fee-trapped. The CONSTRAINTS ladder gives 25 bps -> 73.0% and 50 bps -> 61.5%, so sub-0.1% moves cannot pay. The desk therefore targets **100-300 bps moves**.
- p* ladder. Command: `python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"`. Output, verbatim:

```
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

  Across the 100-300 bps ladder, p* runs from roughly 56% down to 52%. Every thesis quotes its own `fee_math.p_star(tp_bps)`. Do not re-derive it by hand.

## 4. Horizons in scope

- **In scope:** intraday to multi-day holds, with targets of 100-300 bps moves.
- **Explicitly NOT in scope:** scalping (sub-0.1% targets, sub-hour reaction), because it is fee-trapped per §3.
- **Explicitly IN scope:** event-driven theses (scheduled or observable forced-flow events). A thesis still needs a mechanism: a named counterparty and why they are forced to pay (STANDARDS #1). It also needs frequency enough for time-to-verdict <= 26 weeks, as row 84 died on exactly this.
- **At least two analyst lenses must target holds > 8h.** On such holds, funding at every 8h settlement must be accounted for. BTC funding is about +0.01%/8h and meme perps are often negative (CONSTRAINTS). Load funding via `load_data.load_funding` or `load_reference_funding`. Funding is holdout-gated like price data.

## 5. Execution reality of the Phmex-S bot (CONSTRAINTS)

- The bot is a **5-min poller** with no sub-minute reaction.
- Entries are **maker limit orders**. Real maker fill is about **27%**, and misses are adversely selected. Exits are **taker**.
- Order-book snapshots arrive every 60s at depth 5, for BTC/ETH/INJ/ARB only. There is no streaming book.
- **The Mac may sleep.** Slow horizons (hours to days) tolerate this; 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel. They are graded daily at 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py` and killed via `touch .kill_<slot>`.
- Simulated fills are screening-grade upper bounds. The forward test is the only adjudicator (STANDARDS #10). Signals must use closed bars only. Forming-bar signals reproduce only about 40% of closed-bar replays (STANDARDS #4).

## 6. Datasets and train/holdout boundaries (research/swarm/kb/DATA.md)

| dataset | path | symbols | timeframes | coverage | train ends |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols | 1m, 5m, 1h (+ funding json) | 2026-06-01 -> 2026-09-02 23:55 UTC | ≈ 2026-08-10; holdout after |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 in the cache: 1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP | 1h (5m partial) | 2025-06-27 -> 2026-08-01 | ≈ 2026-04-24 (holdout ≈ 2026-04-23 -> 08-01) |

- **Use `long_1h` for multi-day and event-driven theses.** GIGGLE is DELISTED (2026-08-07). The screenable `long_1h` universe is the 18 active symbols (DATA.md 2026-09-21 note), and `universe_check` must be run.
- **Cross-dataset rule:** a `long_1h` thesis may not use `mr_edge` data dated on or after 2026-04-23 in any probe or signal (STANDARDS #6).
- **Loading:** all loads go through `research.swarm.lib.load_data`. Reference symbols must use `load_reference` / `load_reference_funding` only (STANDARDS #16). Never read cache files by hand.
- **Holdout is NEVER read in this run.** That rules out era="holdout" and era="all", the committee token, and direct cache reads. `load_data.fetch_ohlcv_ccxt` is committee-token gated, sits outside the research stage, and must not be called.
- Other bot-collected data (`logs/l2_ticks/`, `logs/flow_capture.jsonl`, `logs/entry_snapshots.jsonl`) is exploratory only and cannot be loaded via `load_data`. A screened signal cannot depend on it.

## 7. Gatekeeper watch list: 15 DEAD_LIST rows most likely to be relabeled

These rows come from `research/swarm/kb/DEAD_LIST.md`. They are a relabel FILTER, NOT ideas (STANDARDS #2, #13). Every thesis must cite its nearest rows by number and state how its mechanism differs.

| row | gist (5 words) |
|---|---|
| 3 | 1h vol-expansion fade, selection-biased |
| 4 | Naked funding short = price drift |
| 6 | Liquidation cascades continue, never revert |
| 7 | Calendar/time-of-day effects NULL after FDR |
| 13 | BTC time-series momentum fails deflation |
| 19 | Token-unlock short, catastrophic drawdown |
| 76 | Multi-day mean reversion dead post-2022 |
| 84 | FOMC/CPI candle momentum, too rare |
| 106 | BTC-shock alt lag, negative |
| 107 | ETH/BTC regime rotation fully negative |
| 109 | Daily re-lever flow fully negative |
| 110 | Liq-cascade continuation fully negative too |
| 111 | Vol-scaled continuation straddles zero |
| 112 | BTC-alt cascade paper-killed, dollar-cap |
| 113 | BRRNY window continuation straddles zero |

Owner directives also stand (STANDARDS #14). Never re-propose the demoted books (main live, ST2.0, 5m_MR live, Donchian live), the BTC blacklist, gate loosening, universe swaps without a new mechanism, or the funding/XS/OI hunt (rows 10, 20, 83).

## kb_check

Command: `python3 -m research.swarm.lib.kb_check` (exit 0). Output, verbatim:

```
KB OK
```
