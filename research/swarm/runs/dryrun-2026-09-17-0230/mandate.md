# MANDATE — run dryrun-2026-09-17-0230 (DRY RUN — plumbing test)

Clock: 2026-09-17T09:30:28Z (2:30 AM PT). Run dir: `research/swarm/runs/dryrun-2026-09-17-0230/`.
Governing documents: `research/swarm/kb/CONSTRAINTS.md`, `research/swarm/kb/STANDARDS.md`, `research/swarm/kb/DATA.md`, `research/swarm/kb/DEAD_LIST.md` (canonical if anything here differs).
kb_check status: **KB OK** (verbatim output in section 8).

## 1. Purpose vs. pass bar

The owner's goal — growing a small account — is the desk's PURPOSE. It is stated here as purpose and nothing else. It is NOT a screening threshold and must not be converted into one.

The pass bar is, and stays (CONSTRAINTS "viable" 1-5):
1. Train-era screen: n >= 30 and the 95% bootstrap CI of net bps (after `c`) excludes 0 — from `research.swarm.lib.bootstrap_ci.mean_ci`.
2. Observed WR >= p* for the spec's TP — from `research.swarm.lib.fee_math.p_star`.
3. Time-to-verdict (n=50) <= 26 weeks at expected frequency — from `fee_math.time_to_verdict_weeks`.
4. Every symbol in the universe passes `fee_math.lot_check` at $200 notional.
5. Signal computable on closed bars from data the bot actually has.

In one line: per-trade net expectancy > 0 after `c`, with the 95% bootstrap CI excluding zero. No daily-ROI target exists anywhere in this run; any seat that writes one has produced a defect.

## 2. Capital and sizing

- Design basis **$200** (CONSTRAINTS "Capital and sizing").
- Screen sizing: `fee_math.position_notional()` = **200.0** USD notional (10% margin at 10x). Verified this run: `python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"` -> `200.0`.
- Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums, verbatim from `fee_math.LOT_MIN_USD` (do not round), printed this run: `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`. `minOrderValueRv` 1 USDT. Every universe symbol must be checked with `fee_math.lot_check` at $200 notional.

## 3. Minimum net edge after c

Cost stack, printed this run from `research/swarm/lib/fee_math.py` constants: `FEES_RT_BPS 7.0` (maker entry / taker exit), `ADVERSE_BPS 4.5` (measured post-fill adverse selection), `C_BPS 11.5`. All hold-period funding is on top of this for holds crossing an 8h settlement.

Required win rate for symmetric TP/SL `x`: `p* = (x + c) / 2x` (`fee_math.p_star`). Target ladder computed this run:

```
$ python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

Justification from CONSTRAINTS: at 25 bps p* is 73.0% and at 50 bps 61.5% — "scalping is fee-trapped: sub-0.1% moves cannot pay." At 100-300 bps the ladder above puts p* at roughly 52-56%, which is the range a real mechanism can plausibly clear. Therefore theses in this run target **100-300 bps moves**. The minimum net edge is simply: `net_bps_mean > 0` after `c = 11.5 bps` with CI95 excluding 0 (section 1); a thesis whose TP sits below 100 bps needs an explicit written reason and still faces the same bar.

Every WR / p* / CI / time-to-verdict number any seat reports must come from `research.swarm.lib` (`fee_math`, `bootstrap_ci`) with the file path cited. Hand arithmetic in prose is a defect (STANDARDS #8).

## 4. Horizons in scope

- **In scope:** intraday-to-multi-day holds. **Event-driven theses are explicitly IN scope** (scheduled macro prints, listings/unlocks, settlement windows, etc. — mechanism first, counterparty named, external source cited per STANDARDS #1-2).
- **Explicitly NOT scalping.** No sub-100-bps targets, no 5-minute-horizon mechanisms, no forming-bar signals (STANDARDS #4).
- **At least two analyst lenses must target holds > 8h.** Any hold > 8h crosses a funding settlement; funding at every 8h settlement must be accounted for in the screen (BTC ≈ +0.01%/8h; meme perps often negative — CONSTRAINTS "Costs"). Funding is loaded via `load_data.load_funding(symbol, era, token)`, train era only.
- Slow horizons (hours-days) tolerate the Mac sleeping; 5-minute horizons do not (CONSTRAINTS "Execution reality").

## 5. The bot's execution reality (from CONSTRAINTS)

- **5-min poller** — no sub-minute reaction.
- Entries are **maker limit orders**; real maker fill ≈ **27%**, and misses are adversely selected. Exits are **taker**. Simulated fills are screening-grade upper bounds (STANDARDS #10).
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. No streaming book.
- **The Mac may sleep.**
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`.
- Forward test is the only adjudicator.

## 6. Datasets and train/holdout boundaries (from `research/swarm/kb/DATA.md`)

Load only via `research.swarm.lib.load_data`; never read caches by hand.

| dataset key | path | symbols | timeframes | coverage | train ends |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols | 1m, 5m, 1h | 2026-06-01 -> 2026-09-02 23:55 UTC (pkl; funding as `funding_<SYM>_USDT_USDT.json`) | ≈ 2026-08-10; holdout after |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols: 1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP | 1h (5m partial) | 2025-06-27 -> 2026-08-01 (parquet) | ≈ 2026-04-24; holdout ≈ 2026-04-23 -> 08-01 |

- `long_1h` is the dataset for multi-day / event-driven theses (DATA.md).
- **Holdout is never read in this run.** Holdout = final 25% of each dataset's range; `load_ohlcv` and `load_funding` refuse holdout rows without the committee token; no seat in this run holds or uses the token, and era `"holdout"` / `"all"` are forbidden. Nobody reads the cache files directly.
- `load_data.fetch_ohlcv_ccxt` is committee-token gated, build-stage only — analysts and screens do not call it.
- **Cross-dataset holdout caveat (DATA.md / STANDARDS #6):** `mr_edge` train (2026-06-01 -> ~08-10) overlaps the `long_1h` holdout window (≈ 2026-04-23 -> 08-01), and 18 of 19 `long_1h` symbols exist in `mr_edge`. A thesis on `long_1h` may not use `mr_edge` data dated on or after 2026-04-23 in any probe or signal; the gatekeeper rejects any `long_1h` thesis whose probes did.
- Other bot-collected data (exploratory only, not loadable via `load_data`): `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (BTC/ETH/INJ/ARB, 2026-07-13 -> 09-10), `logs/flow_capture.jsonl` (2026-05-11 -> 09-09), `logs/entry_snapshots.jsonl` (1,374 live entry contexts 2026-04-07 -> 09-14).
- Artifact naming: train era writes `out.json` / `trades.csv`; any other era writes era-suffixed files (STANDARDS #7).

## 7. Gatekeeper watch list — 15 DEAD_LIST rows most likely to be relabeled this run

Source: `research/swarm/kb/DEAD_LIST.md` (cite by row number). This is a FILTER, not a source of ideas (STANDARDS #2, #13). Selected for the intraday-to-multi-day, event-driven, >8h-hold mandate:

| row | 5-word gist |
|---|---|
| 3 | 1h vol-expansion fade, split-selected |
| 4 | Naked funding harvest = price drift |
| 5 | Cross-sectional momentum needs 100+ names |
| 6 | Liquidation cascade: high-vol continues |
| 7 | Time-of-day / calendar effects null |
| 13 | BTC time-series momentum fails deflation |
| 19 | Token-unlock short −86.6% max DD |
| 20 | Funding-spike carry: armed, not deployed |
| 25 | S/R bounce gross negative, killed |
| 34 | Linear-vs-inverse funding spread parked |
| 76 | Multi-day mean reversion dead post-2022 |
| 78 | 1h Bollinger squeeze breakout refuted |
| 82 | Funding-settlement vol breakout gate refuted |
| 83 | Funding z-score contrarian: no signal |
| 84 | FOMC/CPI first-candle needs 1-min |

Also in force (STANDARDS #14, owner directives): never re-propose demoted books (main live, ST2.0, 5m_MR live, Donchian live — rows 9, 26, 30, 33), the BTC blacklist (row 56), gate loosening (rows 35, 50, 52), universe swaps without a new mechanism (row 31), or the funding/XS/OI hunt (rows 4, 5, 10, 83). Every thesis must cite its nearest dead rows and state why the mechanism differs.

## 8. kb_check

Command run: `python3 -m research.swarm.lib.kb_check` (exit code 0). Output verbatim:

```
KB OK
```
