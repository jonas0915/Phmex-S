# Desk Mandate — run 2026-09-17-2020

## 1. Purpose

The owner's goal of growing a small account is the desk's **PURPOSE**, not a screening threshold. The owner's ULTIMATE aspiration, recorded 2026-09-17 in the owner's own words — "keep it in mind, don't set it yet" — is +10% account ROI per day. That number is an aim the desk works toward by compounding real, verified edges over time. It is **never a bar any thesis is judged against**, and it is **never a licence for leverage or aggression in place of edge**.

The pass bar for this run is, and stays, exactly what CONSTRAINTS.md's "viable" section (items 1-5) says: per-trade net expectancy > 0 after cost `c`, with the 95% bootstrap CI excluding zero. No daily-ROI target — 10%/day or any other figure — is applied to any thesis, screen, or verdict produced in this run.

## 2. Capital and sizing

- Design basis: **$200**.
- Position sizing for every screen: `research.swarm.lib.fee_math.position_notional()` → $200 notional (10% margin at 10x leverage).
- Two paper slots maximum at this size; no cross-sectional baskets.
- Every symbol in a thesis's universe must pass `fee_math.lot_check` at $200 notional before the thesis can register (lot minimums from CONSTRAINTS.md: BTC $77.74, ETH $24.9738, SOL $1.0143, XRP $1.0044, DOGE $1.0010; `minOrderValueRv` 1 USDT).

## 3. Minimum net edge after costs

Cost basis from CONSTRAINTS.md: fees round-trip (maker entry / taker exit) = **7.0 bps** (`fee_math.FEES_RT_BPS`), measured adverse selection = **4.5 bps** (`fee_math.ADVERSE_BPS`), total **c = 11.5 bps** (`fee_math.C_BPS`).

Command run:
```
python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
```
Output (verbatim):
```
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

So for the target ladder of 100-300 bps moves: p* ≈ 55.75% at 100 bps, 53.83% at 150 bps, 52.875% at 200 bps, 51.92% at 300 bps — i.e., roughly **52-56%** required win rate across the target range, consistent with the mandate's target band. Any thesis in scope this run must clear its move size's own p* from this table (or from a fresh `fee_math.p_star` call at its registered TP), not a hand-computed number.

## 4. Horizons in scope

- **In scope:** intraday-to-multi-day holds. Event-driven theses are explicitly IN scope.
- **Explicitly NOT in scope:** scalping. CONSTRAINTS.md is blunt on this: "Scalping is fee-trapped: sub-0.1% moves cannot pay" — sub-100-bps target moves are out of bounds for this run's target ladder (100-300 bps).
- At least two analyst lenses this run must target holds **> 8 hours**. Any such hold must account for funding, which settles every 8h (BTC ≈ +0.01%/8h per funding period; meme perps often negative) — a multi-day hold accrues funding cost/credit across multiple settlements and that accrual must be priced into the thesis's net-bps math, not ignored.

## 5. Bot execution reality (from CONSTRAINTS.md)

- **5-minute poller** — no sub-minute reaction; any signal must be computable and actionable on a 5-min-or-slower cadence.
- Entries are **maker limit orders**; real maker fill rate ≈ **27%**, and misses are adversely selected.
- **Exits are taker.**
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only — no streaming book, no L2 depth for other symbols.
- The Mac running the bot **may sleep**. Slow horizons (hours-to-days) tolerate that; 5-minute-scale horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6 AM PT by `scripts/lab_adjudicator/adjudicate.py`; killed via `touch .kill_<slot>`.
- Simulated fills are screening-grade upper bounds only (STANDARDS.md #10); forward test is the only real adjudicator.

## 6. Datasets in scope (from `research/swarm/kb/DATA.md`)

| dataset key | path | coverage | timeframes | train-end |
|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | train ends ≈ 2026-08-10; holdout after |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE, 1000SHIB, AAVE, ADA, BNB, BTC, DOGE, ETH, GIGGLE, LINK, LTC, NEAR, ONDO, SOL, SUI, TAO, UNI, XLM, XRP), 1h (5m partial), 2025-06-27 → 2026-08-01 | 1h primary | train ends ≈ 2026-04-24; **use this dataset for multi-day / event-driven theses** |

Both are loaded only via `research.swarm.lib.load_data` (`load_ohlcv`, `load_funding(symbol, era, token)`); never read the cache files or `mr_edge`/`long_1h` pkl/parquet directly. `load_data.fetch_ohlcv_ccxt` is committee-token gated and out of scope for this run — analysts and screens do not call it.

**Holdout is never read in this run.** `load_ohlcv`/`load_funding` refuse holdout rows (era="holdout"/"all") without the committee token, which this run does not hold. Funding is holdout-gated exactly like price, anchored to the same era boundary.

**Cross-dataset holdout caveat (binding on this run):** `long_1h` holdout (final 25% of 2025-06-27→2026-08-01) ≈ 2026-04-23 → 08-01. `mr_edge` train (2026-06-01 → ~08-10) falls inside that window, and 18 of the 19 `long_1h` symbols also exist in `mr_edge`. Rule: a thesis built on `long_1h` may not use `mr_edge` data dated on or after **2026-04-23** in any exploratory probe or signal. Given item 4 above (event-driven, holds > 8h, multi-day) will likely route analysts toward `long_1h`, this boundary applies directly — watch it.

## 7. DEAD_LIST rows most likely to be relabeled this run

These are the gatekeeper's watch list for this run's intraday/multi-day/event-driven scope — NOT ideas to build from (`research/swarm/kb/DEAD_LIST.md`, STANDARDS.md #2 and #13).

| row | gist (5 words) |
|---|---|
| 3 | 1h vol-expansion fade selection-biased |
| 4 | Funding harvest = disguised price drift |
| 5 | Cross-sectional momentum needs 100+ names |
| 7 | Calendar/microstructure mostly null after FDR |
| 8 | Pairs/cointegration one-coin Sharpe illusion |
| 12 | 12-coin basket TSM deflated-Sharpe fail |
| 13 | BTC-TSM(28,5) fails deflated-Sharpe bar |
| 19 | Token-unlock short, huge drawdown risk |
| 20 | Funding-spike carry armed, not deployed |
| 25 | S/R bounce killed, gross negative |
| 33 | Donchian trend survivor, owner declined live |
| 34 | Funding spread real but sub-$2K-parked |
| 76 | Multi-day mean reversion dead post-2022 |
| 82 | Funding-settlement vol-regime gate relabels dead gates |
| 84 | FOMC/CPI momentum needs 1-min precision |

## 8. kb_check

Command run: `python3 -m research.swarm.lib.kb_check`

```
KB OK
```
