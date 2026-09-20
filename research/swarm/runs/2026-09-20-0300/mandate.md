# Desk Mandate — run 2026-09-20-0300

Clock: now = 2026-09-20T10:00:08Z (UTC) / 2026-09-20 03:00 AM PT. Today = 2026-09-20.

## 1. Purpose

The owner's goal of growing a small account is the desk's PURPOSE, stated as such — it is NOT a screening threshold applied to any individual thesis. The owner's ULTIMATE aspiration (recorded 2026-09-17, owner's own words: "keep it in mind, don't set it yet") is **+10% account ROI per day**. That aspiration is an aim the desk works toward over time by compounding real, verified edges. It is:

- **Never** a bar any thesis is judged against in this or any run.
- **Never** a licence for leverage or aggression substituting for edge.
- **Not** written anywhere in this run as a daily-ROI target, gate, or KPI.

The pass bar for every thesis screened this run is, and stays, exactly CONSTRAINTS.md's "viable" definition (items 1-5): per-trade net expectancy > 0 after cost `c`, with the 95% bootstrap CI of net bps excluding zero, at n ≥ 30 in the train era, observed WR ≥ p* for the spec's target, time-to-verdict (n=50) ≤ 26 weeks at expected frequency, every symbol in the universe passing `lot_check` at $200 notional, and the signal computable on closed bars from data the bot actually has.

## 2. Capital and sizing

- Design basis: **$200**.
- Position sizing: `fee_math.position_notional(capital_usd=200.0, risk_frac=0.10, leverage=10)` = **$200.0 notional** per position (10% margin at 10x leverage). Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums (USD notional per lot), verbatim from `fee_math.LOT_MIN_USD` — do not round: BTC **77.74**, ETH **24.9738**, SOL **1.0143**, XRP **1.0044**, DOGE **1.0010**. `minOrderValueRv` = 1 USDT (`fee_math.MIN_ORDER_VALUE_USD`). Every symbol in a thesis's universe must be checked with `fee_math.lot_check(symbol, notional_usd)` before the thesis is treated as viable (CONSTRAINTS "viable" item 4). At $200 notional, all five listed symbols clear (BTC 2 lots, ETH 8 lots, SOL/XRP/DOGE well over 1 lot) — but any symbol outside this list must still be run through `lot_check` individually; do not assume it clears.

## 3. Minimum net edge in bps after cost, and the p* ladder

Costs, from `fee_math` (never re-derived by hand): `FEES_RT_BPS = 7.0` (maker entry / taker exit blend) + `ADVERSE_BPS = 4.5` (measured post-fill adverse selection) = `C_BPS = 11.5` bps total round-trip cost. A thesis is only worth screening if its expected gross edge clears 11.5 bps by a real, cited margin — sub-0.1% (10 bps) moves cannot pay in this cost structure.

Computed via `fee_math.p_star`, run as instructed:

```
python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
```

Output (verbatim):
```
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

So for symmetric TP/SL targets: 100 bps → p* **55.75%**, 150 bps → p* **53.83%**, 200 bps → p* **52.875%**, 300 bps → p* **51.92%**. This run's target ladder is **100-300 bps moves**, where required win rate is roughly **52-56%** — consistent with CONSTRAINTS.md's quoted p* ladder (25 bps 73.0%, 50 bps 61.5%, 100 bps 55.8%, 300 bps 51.9%, 1000 bps 50.6%): the smaller the target move, the higher the win rate a thesis must clear, because the fixed 11.5 bps cost is a larger fraction of a smaller target. This is why the desk is explicitly out of scalping territory (sub-50 bps targets) this run.

## 4. Horizons in scope

**Intraday-to-multi-day.** Explicitly **NOT scalping** (no sub-50-bps-target, single-bar-hold theses). Event-driven theses (funding settlements, scheduled macro prints, listing/unlock-type catalysts, etc.) are explicitly **IN scope**, subject to STANDARDS #1 (mechanism first — name the counterparty forced to pay) and STANDARDS #2 (cited external source with the actual number).

At least **two analyst lenses must target holds > 8 hours**. Any thesis holding past an 8h funding settlement must account for funding cost/carry explicitly (BTC funding ≈ +0.01%/8h per CONSTRAINTS; alt/meme perp funding is often negative) — this is not optional bookkeeping, it changes net expectancy on multi-day holds.

## 5. Execution reality of the Phmex-S bot (from CONSTRAINTS.md)

- **5-minute poller** — no sub-minute reaction; a thesis that needs 1-minute precision cannot be executed by this bot.
- Entries are **maker limit orders** — real maker fill rate ≈ **27%**, and misses are adversely selected (this is where the 4.5 bps `ADVERSE_BPS` term comes from). Exits are **taker**.
- Order book snapshots every 60s, depth 5, **BTC/ETH/INJ/ARB only** — no streaming book, and no L2 features available outside those four symbols.
- The Mac running the bot **may sleep** — slow horizons (hours-to-days) tolerate that; 5-minute-scale horizons do not.
- Paper slots run on the live feed behind a `.paper` sentinel, graded daily 6 AM PT by `scripts/lab_adjudicator/adjudicate.py`; killed via `touch .kill_<slot>`.

## 6. Datasets and train/holdout boundaries

Per `research/swarm/kb/DATA.md`, loaded only via `research.swarm.lib.load_data` (never raw caches by hand):

| dataset key | path | coverage | timeframes | train ends | notes |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | ≈ 2026-08-10 (holdout after) | pkl DataFrames, cols open/high/low/close/volume, UTC index; funding via `funding_<SYM>_USDT_USDT.json`, holdout-gated identically to price, `load_funding(symbol, era, token)` |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP), 2025-06-27 → 2026-08-01 | 1h (5m partial) | ≈ 2026-04-24 (holdout after) | parquet; **use this for multi-day / event-driven theses** |

**Holdout is never read in this run.** Holdout = final 25% of each dataset's range; `load_data.load_ohlcv` / `load_data.load_funding` refuse holdout rows without the committee token, and `load_data.fetch_ohlcv_ccxt` is committee-token gated and outside the research stage entirely — this run does not call it.

**Cross-dataset holdout caveat (binding on this run):** `long_1h` holdout ≈ 2026-04-23 → 08-01; `mr_edge` train (2026-06-01 → ≈08-10) falls inside that window, and 18 of the 19 `long_1h` symbols also exist in `mr_edge`. Rule: a thesis built on the `long_1h` dataset may **not** use any `mr_edge` data dated on or after **2026-04-23** in any exploratory probe or signal — the gatekeeper rejects a `long_1h` thesis whose probes did.

Other bot-collected data (not loadable via `load_data`; exploratory only, not for signal construction unless a thesis specifically justifies it): `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (depth-5 book+tape, BTC/ETH/INJ/ARB, 2026-07-13→09-10), `logs/flow_capture.jsonl` (OB+flow, 2026-05-11→09-09), `logs/entry_snapshots.jsonl` (1,374 live entry contexts, 2026-04-07→09-14).

## 7. DEAD_LIST watch list — 15 rows most likely to be relabeled this run

These are the gatekeeper's watch list for this run's horizon (intraday-to-multi-day, event-driven, non-scalping), **not** a source of ideas (STANDARDS #2). Any thesis resembling these must cite the row and explain the mechanism difference.

| row | family | gist (5 words) |
|---|---|---|
| 3 | 1h vol-expansion fade | single-split selection bias, refuted |
| 5 | Cross-sectional momentum (market-neutral) | needs 100+ names, dead |
| 7 | Calendar/microstructure (time-of-day, CME gap, weekend) | mostly null, decaying, stale |
| 12 | 12-coin basket TSM (28d tercile) | deflated Sharpe fails, dilution |
| 13 | BTC-TSM (28,5) | doesn't beat buy-and-hold |
| 14 | ETH-TSM-28 daily long-only | scaling-rights only, killed |
| 19 | Token-unlock short | real drift, catastrophic drawdown |
| 20 | Funding-spike carry playbook | armed not deployed, threshold gated |
| 31 | MR-tuned universe (ranginess scanner) | frequency below control, reversed |
| 33 | BTC/ETH Donchian-ensemble trend (paper) | owner declined live, never reoffer |
| 34 | Linear-vs-inverse funding spread | real but parked, sub-scale |
| 76 | Multi-day MR / overnight window / vol-scaling | dead post-2022, web-verified |
| 77 | Prior-Day Value-Area Breakout (vae_bo) | untested variant, no backtest |
| 78 | 1h Bollinger-Squeeze Breakout | same bias as row 3 |
| 84 | FOMC/CPI first-candle momentum (ETH) | needs 1-min precision, unavailable |

## 8. kb_check

Ran exactly: `python3 -m research.swarm.lib.kb_check`

```
KB OK
```
