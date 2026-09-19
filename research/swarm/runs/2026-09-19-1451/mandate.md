# Desk Mandate — run 2026-09-19-1451

kb_check: **KB OK** (see full output at bottom).

## 1. Purpose

The owner's goal of growing a small account is the desk's **PURPOSE**, not a screening threshold. The owner's ULTIMATE aspiration, recorded 2026-09-17 in the owner's own words — *"keep it in mind, don't set it yet"* — is +10% account ROI per day. That number is an aim the desk works toward by compounding **real, verified edges**. It is never a bar any thesis is judged against, and it is never a licence for leverage or aggression in place of edge.

The pass bar for every thesis in this run is, and stays, exactly what CONSTRAINTS.md "viable" items 1-5 say:
1. Train-era screen: n ≥ 30 and bootstrap CI95 of net bps excludes 0 (after cost `c`).
2. Observed win rate ≥ p* for the spec's TP.
3. Time-to-verdict (n=50) ≤ 26 weeks at expected frequency.
4. Every symbol in the universe passes `fee_math.lot_check` at $200 notional.
5. Signal is computable on closed bars from data the bot actually has.

**No daily-ROI target is applied to any thesis in this run.** Do not write a daily-ROI figure anywhere in this run's artifacts.

## 2. Capital and sizing

- Design basis: **$200**.
- Position sizing for screens: `fee_math.position_notional()` → $200 notional (10% margin at 10x leverage). Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums (USD notional per lot, `fee_math.LOT_MIN_USD`, do not round): BTC **77.74**, ETH **24.9738**, SOL **1.0143**, XRP **1.0044**, DOGE **1.0010**. `minOrderValueRv` = 1 USDT. Every symbol in a thesis's universe must clear `fee_math.lot_check` at $200 notional (CONSTRAINTS viability item 4).

## 3. Minimum net edge after costs

Costs, from `fee_math` (never hand-derived):
- Fees VIP-0, bot's real maker-entry/taker-exit mix: **7.0 bps round trip** (`fee_math.FEES_RT_BPS`).
- Measured adverse selection after fill: **4.5 bps** (`fee_math.ADVERSE_BPS`).
- Total cost `c` = **11.5 bps** (`fee_math.C_BPS`).

Required win rate for symmetric TP/SL `x`, `p* = (x + c) / 2x` (`fee_math.p_star`), computed live for this run:

```
python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

So at the target ladder: 100 bps → p*=55.75%, 150 bps → p*=53.83%, 200 bps → p*=52.875%, 300 bps → p*=51.92%. This matches CONSTRAINTS' own ladder (25 bps 73.0%, 50 bps 61.5%, 100 bps 55.8%, 300 bps 51.9%, 1000 bps 50.6%) — scalping (sub-100 bps) is fee-trapped; this run's targets of 100-300 bps moves sit in the **~52-56% p*** band, which is where a real mechanism has room to clear cost without needing a coin-flip-adjacent win rate.

Minimum net edge bar: for any screened thesis, bootstrap CI95 (`bootstrap_ci.mean_ci`) on net bps (gross bps minus the 11.5 bps `c`) must exclude zero, and observed WR must meet or beat the p* for that spec's registered TP.

## 4. Horizons in scope

**Intraday-to-multi-day. Explicitly NOT scalping.** Event-driven is explicitly IN scope. At least two analyst lenses this run must target holds > 8 hours; any such hold must account for funding settling every 8h (BTC ≈ +0.01%/8h; meme perps often negative) using `load_data.load_funding` (train era only) and cite the resulting bps drag/gain in the pre-reg.

## 5. Bot execution reality (from CONSTRAINTS.md)

- **5-minute poller** — no sub-minute reaction; a thesis that needs 1-minute precision cannot be executed by this bot.
- Entries are **maker limit orders** — real maker fill ≈ 27%, and misses are adversely selected. Exits are **taker**.
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only — no streaming book, and no L2 signal is available outside those 4 symbols.
- The Mac may sleep — slow horizons (hours-days) tolerate that; 5-minute horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel, graded daily 6 AM PT by `scripts/lab_adjudicator/adjudicate.py`; killed via `touch .kill_<slot>`.
- Simulated fills are screening-grade upper bounds only (STANDARDS #10); forward test is the only real adjudicator.

## 6. Datasets in scope (from research/swarm/kb/DATA.md)

| dataset key | path | coverage | timeframes | train ends | notes |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | ≈ 2026-08-10 | pkl DataFrames (open/high/low/close/volume, UTC index); funding via `funding_<SYM>_USDT_USDT.json`, holdout-gated on the same era boundary. |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE, 1000SHIB, AAVE, ADA, BNB, BTC, DOGE, ETH, GIGGLE, LINK, LTC, NEAR, ONDO, SOL, SUI, TAO, UNI, XLM, XRP), 2025-06-27 → 2026-08-01 | 1h (5m partial) | ≈ 2026-04-24 | parquet; **use for multi-day / event-driven theses**. |

Holdout = final 25% of each dataset's date range; it is **never read in this run** — no `era="holdout"`/`"all"`, no committee token, no `load_data.fetch_ohlcv_ccxt` (committee-token gated, outside research stage).

**Cross-dataset holdout caveat (binding this run):** `long_1h` holdout ≈ 2026-04-23 → 08-01; `mr_edge` train (2026-06-01 → ~08-10) falls inside that window, and 18 of `long_1h`'s 19 symbols also exist in `mr_edge`. **Rule: a `long_1h` thesis may not use `mr_edge` data dated on/after 2026-04-23 in any exploratory probe or signal** — the gatekeeper rejects a `long_1h` thesis whose probes did.

Other bot-collected exploratory-only data (not via `load_data`): `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (depth-5 book+tape, BTC/ETH/INJ/ARB, 2026-07-13→09-10), `logs/flow_capture.jsonl` (2026-05-11→09-09), `logs/entry_snapshots.jsonl` (2026-04-07→09-14).

## 7. DEAD_LIST watch list — 15 rows most likely to be relabeled this run

These are the gatekeeper's watch list, cited from `research/swarm/kb/DEAD_LIST.md`, **not ideas** — given this run's intraday-to-multi-day/event-driven/funding-aware scope, any thesis resembling these mechanisms gets extra scrutiny for a relabel:

| row | 5-word gist |
|---|---|
| 4 | Funding harvest naked directional dies |
| 5 | Cross-sectional momentum needs huge book |
| 7 | Calendar/time-of-day mostly decayed noise |
| 8 | Pairs/cointegration = one-coin luck |
| 12 | 12-coin basket TSM dilution fails |
| 13 | BTC-TSM deflated Sharpe fails bar |
| 14 | ETH-TSM-28 daily killed by drift |
| 19 | Token-unlock short, huge drawdown risk |
| 20 | Funding-spike carry: arm, don't deploy |
| 33 | Donchian trend: owner declined, never reoffer |
| 34 | Funding spread real but sub-scale |
| 76 | Multi-day MR / overnight window dead |
| 82 | Funding-vol regime gate relabels dead levers |
| 83 | Funding z-score contrarian: R²≈0, no signal |
| 84 | Event first-candle momentum, needs 1-min precision |

## 8. kb_check output

```
$ python3 -m research.swarm.lib.kb_check
KB OK
```
