# DESK MANDATE — run 2026-09-17-0701

Clock: now = 2026-09-17T14:01:15Z (7:01 AM PT), today = 2026-09-17. Run dir: `research/swarm/runs/2026-09-17-0701/`. Knowledge base: `research/swarm/kb/` (canonical if anything below differs).

kb_check status: **KB OK** (run at the bottom of this document, output pasted verbatim).

## 1. Purpose

The owner's goal of growing a small account is the desk's PURPOSE. It is stated here as purpose only — it is NOT a screening threshold and no thesis in this run is judged against it.

The owner's ULTIMATE aspiration, recorded 2026-09-17 (owner's words: "keep it in mind, don't set it yet"), is +10% account ROI per day. It is an aim the desk works toward by compounding real, verified edges. It is never a bar any thesis is judged against, and never a licence for leverage or aggression in place of edge.

The pass bar is, and stays: **per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero** — CONSTRAINTS "viable" 1-5 in full:

1. Train-era screen: n >= 30 and bootstrap CI95 of net bps excludes 0 (after `c`).
2. Observed WR >= p* for the spec's TP.
3. Time-to-verdict (n=50) <= 26 weeks at expected frequency.
4. Every symbol in the universe passes `lot_check` at $200 notional.
5. Signal is computable on closed bars from data the bot actually has.

No daily-ROI target is applied to any thesis in this run. Nobody writes one anywhere in this run's artifacts.

## 2. Capital and sizing

- Design basis **$200** (CONSTRAINTS "Capital and sizing").
- Screen sizing: `fee_math.position_notional()` → `200.0` (output of `python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"`, this run) = $200 notional (10% margin at 10x).
- Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums, USD notional per lot, verbatim from `fee_math.LOT_MIN_USD` (printed this run): `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`. `minOrderValueRv` 1 USDT. Every universe symbol must pass `fee_math.lot_check` at $200 notional — do not round, do not re-derive.

## 3. Minimum net edge after c

Costs come from `research/swarm/lib/fee_math.py` constants, printed this run: `C_BPS 11.5`, `FEES_RT_BPS 7.0`, `ADVERSE_BPS 4.5`. So `c = 11.5 bps` = 7.0 bps round-trip fees (maker entry / taker exit, VIP-0) + 4.5 bps measured adverse selection after fill (CONSTRAINTS "Costs").

Required win rate for symmetric TP/SL `x` is `p* = (x + c) / 2x` — computed only via `fee_math.p_star`. Command run this desk-brief seat:

```
python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

Target ladder for this run: **100-300 bps moves**, where p* is roughly 52-56% (100 bps → 55.75%, 150 bps → 53.83%, 200 bps → 52.88%, 300 bps → 51.92%, all from the output above). CONSTRAINTS is explicit that scalping is fee-trapped ("sub-0.1% moves cannot pay"; its own ladder reads 25 bps → 73.0%, 50 bps → 61.5%). Any thesis whose TP is below 100 bps must show why its observed WR clears the `fee_math.p_star` value for that TP; the desk's default is the 100-300 bps band.

Minimum net edge: the mean net bps per trade after `c` must be > 0 with the `bootstrap_ci.mean_ci` CI95 excluding 0 (viable #1). There is no separate hand-set bps floor — the CI is the floor.

## 4. Horizons in scope

- **Intraday-to-multi-day.** Explicitly NOT scalping (see §3; sub-100 bps targets are fee-trapped per CONSTRAINTS).
- **Event-driven is explicitly IN scope** (scheduled macro prints, listings/unlocks, funding settlements as events, etc.) — subject to STANDARDS #1 (name the counterparty and why they are forced to pay) and #2 (external source with its actual number).
- **At least two analyst lenses must target holds > 8h.** Funding settles every 8h (BTC ≈ +0.01%/8h; meme perps often negative — CONSTRAINTS "Costs"); any hold > 8h must account for funding at every settlement crossed. Funding data is loaded only via `load_data.load_funding(symbol, era, token)` and is holdout-gated exactly like price (STANDARDS #6).
- Slow horizons tolerate the Mac sleeping; 5-min horizons do not (CONSTRAINTS "Execution reality").

## 5. The bot's execution reality (from CONSTRAINTS)

- **5-min poller** — no sub-minute reaction. Anything needing 1-minute precision cannot be executed (cf. DEAD_LIST row 84).
- Entries are **maker limit orders**; real maker fill ≈ **27%**, and misses are adversely selected. Exits are **taker**.
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. No streaming book.
- The Mac may sleep; slow horizons (hours-days) tolerate that, 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`.
- Simulated fills are screening-grade upper bounds (STANDARDS #10). Forward test is the only adjudicator.

## 6. Datasets and train/holdout boundaries (from research/swarm/kb/DATA.md)

Load only via `research.swarm.lib.load_data`; never read caches by hand in a screen.

| dataset key | path | coverage | timeframes | train ends | notes |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | ≈ 2026-08-10 (holdout after) | pkl DataFrames, cols open/high/low/close/volume, UTC index. Funding: `funding_<SYM>_USDT_USDT.json` rows `{ts ms, rate}` via `load_funding(symbol, era, token)`, holdout-gated on the same era boundary. |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP), 1h 2025-06-27 → 2026-08-01 | 1h (5m partial) | ≈ 2026-04-24 | parquet. **Use this for multi-day / event-driven theses.** |

Holdout = final 25% of each dataset's range (STANDARDS #6).

**Holdout is never read in this run.** No seat passes era="holdout" or era="all", no seat uses the committee token, no seat opens the cache files directly. `load_data.fetch_ohlcv_ccxt` is committee-token gated and outside the research stage — no analyst or screen calls it.

**Cross-dataset holdout caveat (DATA.md / STANDARDS #6):** `long_1h` holdout ≈ 2026-04-23 → 08-01; `mr_edge` train (2026-06-01 → ~08-10) falls inside that window, and 18 of the 19 `long_1h` symbols also exist in `mr_edge`. Rule: a thesis on the `long_1h` dataset may not use `mr_edge` data dated on or after 2026-04-23 in any exploratory probe or signal; the gatekeeper rejects a `long_1h` thesis whose probes did.

Artifact naming: train-era screens write `out.json` / `trades.csv`; any other era writes era-suffixed files (`out.holdout.json`, `trades.holdout.csv`) and never overwrites train artifacts (STANDARDS #7).

Other bot-collected data (exploratory only, not loadable via `load_data`): `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (depth-5 book + tape, BTC/ETH/INJ/ARB, 2026-07-13 → 09-10); `logs/flow_capture.jsonl` (OB + flow snapshots 2026-05-11 → 09-09); `logs/entry_snapshots.jsonl` (1,374 live entry contexts 2026-04-07 → 09-14).

## 7. Gatekeeper watch list — 15 DEAD_LIST rows most likely to be relabeled this run

These are a FILTER, not ideas (STANDARDS #2). Read from `research/swarm/kb/DEAD_LIST.md`; every thesis must cite its nearest rows by number and say how its mechanism differs (STANDARDS #13).

| row | 5-word gist |
|---|---|
| 3 | 1h vol-expansion fade, split-selection bias |
| 4 | Naked funding harvest, price drift |
| 6 | Liquidation-cascade reversion; high-vol continues |
| 7 | Time-of-day / calendar effects null |
| 13 | BTC time-series momentum fails deflation |
| 19 | Token-unlock short, catastrophic drawdown |
| 20 | Funding-spike carry, armed not deployed |
| 25 | S/R bounce zones, gross negative |
| 33 | Donchian trend paper; owner declined |
| 76 | Multi-day mean reversion dead post-2022 |
| 77 | Prior-day value-area breakout, untested |
| 78 | 1h Bollinger-squeeze breakout, refuted |
| 82 | Funding-settlement vol-regime breakout gate |
| 83 | Funding z-score contrarian, R² ~0.003 |
| 84 | FOMC/CPI first-candle momentum, unexecutable |

Also standing owner directives (STANDARDS #14): never re-propose demoted books (main live, ST2.0, 5m_MR live, Donchian live), the BTC blacklist, gate loosening, universe swaps without a new mechanism, or the funding/XS/OI hunt (rows 10, 34, 56, 83 are the nearest rows for that hunt).

## 8. Hard rules for every seat this run

- Never modify bot trading code (`bot.py`, `strategies.py`, `risk_manager.py`, `exchange.py`, `config.py`, `.env`, any slot file).
- Never read holdout; never call `load_data.fetch_ohlcv_ccxt`.
- A frozen spec (`research/swarm/runs/2026-09-17-0701/specs/*.frozen.json`) and its `screens/<id>/signal.py` are never edited — a new idea is a new thesis.
- Every statistic comes from `research.swarm.lib` (`fee_math.p_star / net_bps / time_to_verdict_weeks / lot_check / position_notional`, `bootstrap_ci.mean_ci / diff_ci`). Hand arithmetic in prose is a defect.
- Cite a file path for every number. "Not run" is valid; a made-up number is not.
- Every thesis cites at least one external source URL with the actual number that source reports (STANDARDS #2).
- Do not write any daily-ROI target anywhere.

## kb_check

Command run: `python3 -m research.swarm.lib.kb_check` (from repo root, this seat, 2026-09-17). Output verbatim:

```
KB OK
```
