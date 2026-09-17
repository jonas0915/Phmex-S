# DESK MANDATE — run 2026-09-17-0732

Clock: now = 2026-09-17T14:32:45Z (7:32 AM PT), today = 2026-09-17. Run dir: `research/swarm/runs/2026-09-17-0732/`. Knowledge base: `research/swarm/kb/` (canonical if anything below differs from the embedded copies).

kb_check status: **KB OK** (`python3 -m research.swarm.lib.kb_check`, exit 0, output pasted verbatim at the bottom of this document).

## 1. Purpose

The owner's goal of growing a small account is the desk's PURPOSE. It is stated here as purpose only — it is NOT a screening threshold and no thesis in this run is judged against it.

The owner's ULTIMATE aspiration, recorded 2026-09-17 (owner's words: "keep it in mind, don't set it yet"), is +10% account ROI per day. It is an aim the desk works toward by compounding real, verified edges. It is never a bar any thesis is judged against, and never a licence for leverage or aggression in place of edge.

The pass bar is, and stays: **per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero** — CONSTRAINTS "What viable means" 1-5 in full:

1. Train-era screen: n >= 30 and bootstrap CI95 of net bps excludes 0 (after `c`).
2. Observed WR >= p* for the spec's TP.
3. Time-to-verdict (n=50) <= 26 weeks at expected frequency.
4. Every symbol in the universe passes `lot_check` at $200 notional.
5. Signal is computable on closed bars from data the bot actually has.

No daily-ROI target is applied to any thesis in this run, and nobody writes one anywhere in this run's artifacts.

## 2. Capital and sizing

- Design basis **$200** (CONSTRAINTS "Capital and sizing").
- Screen sizing: `fee_math.position_notional()` → `200.0` (output of `python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"`, run by this seat) = $200 notional (10% margin at 10x).
- Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums, USD notional per lot, verbatim from `fee_math.LOT_MIN_USD` (printed this run): `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`. `minOrderValueRv` 1 USDT. Every universe symbol must pass `fee_math.lot_check` at $200 notional — do not round, do not re-derive.

## 3. Minimum net edge after c

Cost constants come from `research/swarm/lib/fee_math.py`, printed this run: `FEES_RT_BPS 7.0`, `ADVERSE_BPS 4.5`, `C_BPS 11.5`. So `c = 11.5 bps` = 7.0 bps round-trip fees (maker entry / taker exit, VIP-0 maker 0.01% / taker 0.06%) + 4.5 bps measured adverse selection after fill (CONSTRAINTS "Costs").

Required win rate for symmetric TP/SL `x` is `p* = (x + c) / 2x`, computed only via `fee_math.p_star`. Command run by this seat, output verbatim:

```
python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

Target ladder for this run: **100-300 bps moves**, where p* is roughly 52-56% (100 bps → 55.75%, 150 bps → 53.83%, 200 bps → 52.88%, 300 bps → 51.92%, from the output above). Minimum net edge: the screen's `net_bps_mean` after `c = 11.5 bps` must be > 0 with the CI95 excluding zero (`bootstrap_ci.mean_ci`). CONSTRAINTS is explicit that scalping is fee-trapped — sub-0.1% moves cannot pay (25 bps needs 73.0%, 50 bps needs 61.5%) — so no thesis with a registered `tp_bps` below 100 is in scope.

All statistics — WR, p*, net bps, CI, time-to-verdict — come from `research.swarm.lib` (`fee_math.p_star / net_bps / time_to_verdict_weeks / lot_check / position_notional`, `bootstrap_ci.mean_ci / diff_ci`). Hand arithmetic in prose is a defect (STANDARDS #8).

## 4. Horizons in scope

- **Intraday-to-multi-day.** Explicitly NOT scalping (see section 3: sub-100 bps targets cannot clear c).
- **Event-driven is explicitly IN scope** (listings, unlocks, macro prints, exchange/on-chain events), subject to STANDARDS #2 sourcing, the 5-min poller reality in section 5, and the time-to-verdict bar (viable #3).
- **At least two analyst lenses must target holds > 8h.** Funding settles every 8h (BTC ≈ +0.01%/8h; meme perps often negative — CONSTRAINTS "Costs"); any hold > 8h must account for funding at every settlement crossed, using `load_data.load_funding(symbol, era, token)` on the train era only.
- Slow horizons (hours-days) tolerate the Mac sleeping; 5-min horizons do not (CONSTRAINTS "Execution reality").

## 5. The bot's execution reality (from CONSTRAINTS)

- **5-min poller** — no sub-minute reaction. Any thesis needing 1-minute entry precision is not executable (cf. DEAD_LIST row 84).
- **Entries are maker limit orders** — real maker fill ≈ 27%, and misses are adversely selected. **Exits are taker.** Simulated fills are screening-grade upper bounds (STANDARDS #10); forward test is the only adjudicator.
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. No streaming book.
- The Mac may sleep — slow horizons tolerate that, 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`.
- Signals must be computable on **closed bars** from data the bot actually has; forming-bar signals reproduce only ~40% of closed-bar replays (STANDARDS #4). `screen.causality_check` kills any signal that changes when future bars are removed.

## 6. Datasets and train/holdout boundaries (from `research/swarm/kb/DATA.md`)

Load only via `research.swarm.lib.load_data`; never read caches by hand.

| dataset key | path | symbols | timeframes | coverage | train ends | holdout |
|---|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols | 1m, 5m, 1h | 2026-06-01 → 2026-09-02 23:55 UTC | ≈ 2026-08-10 | after ≈ 2026-08-10 (final 25%) |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols: 1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP | 1h (5m partial) | 2025-06-27 → 2026-08-01 | ≈ 2026-04-24 | ≈ 2026-04-23 → 2026-08-01 (final 25%) |

- `mr_edge` funding: `funding_<SYM>_USDT_USDT.json` rows `{ts ms, rate}`, loaded via `load_funding(symbol, era, token)` — holdout-gated exactly like price data, same era boundary.
- **Use `long_1h` for multi-day / event-driven theses** (DATA.md).
- **Cross-dataset holdout caveat (DATA.md / STANDARDS #6):** `long_1h` holdout ≈ 2026-04-23 → 08-01 overlaps `mr_edge` train (2026-06-01 → ~08-10) and 18 of the 19 `long_1h` symbols also exist in `mr_edge`. A thesis on `long_1h` may not use `mr_edge` data dated on or after 2026-04-23 in any exploratory probe or signal; the gatekeeper rejects a `long_1h` thesis whose probes did.
- **Holdout is never read in this run.** No seat passes `era="holdout"` or `era="all"`, touches the committee token, or reads cache files directly. `load_data.fetch_ohlcv_ccxt` is committee-token gated and outside the research stage — no analyst or screen calls it.
- Non-train screen outputs are era-suffixed (`out.holdout.json`, `trades.holdout.csv`) and never overwrite train-era `out.json` / `trades.csv` (STANDARDS #7) — irrelevant to this run since holdout is not read, stated for completeness.
- Exploratory-only, not loadable via `load_data`: `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (depth-5 book + tape, BTC/ETH/INJ/ARB, 2026-07-13 → 09-10), `logs/flow_capture.jsonl` (2026-05-11 → 09-09), `logs/entry_snapshots.jsonl` (1,374 live entry contexts 2026-04-07 → 09-14).

## 7. Gatekeeper watch list — 15 DEAD_LIST rows most likely to be relabeled this run

Source: `research/swarm/kb/DEAD_LIST.md`. These are a FILTER for rejecting relabels, NOT ideas (STANDARDS #2, #13). Given this run's scope (intraday-to-multi-day, event-driven in, holds > 8h with funding), these rows are the nearest analogs:

| row | 5-word gist |
|---|---|
| 3 | 1h vol-expansion fade, selection bias |
| 4 | Naked funding harvest, price drift |
| 6 | Liquidation-cascade reversion, vol continues |
| 7 | Time-of-day, CME gap, calendar noise |
| 13 | BTC time-series momentum, deflated Sharpe |
| 19 | Token-unlock short, catastrophic drawdown |
| 20 | Funding-spike carry, armed not deployed |
| 23 | VWAP/SMA cross, edge is selection |
| 25 | S/R bounce pivot zones, killed |
| 33 | BTC/ETH Donchian trend, owner declined |
| 76 | Multi-day mean reversion, overnight window |
| 77 | Prior-day value-area breakout, untested |
| 78 | 1h Bollinger-squeeze breakout, refuted |
| 83 | Funding z-score contrarian, no signal |
| 84 | FOMC/CPI first-candle momentum, unexecutable |

Also on the owner-directive blocklist (STANDARDS #14, not row-cited): re-proposing demoted books (main live, ST2.0, 5m_MR live, Donchian live), the BTC blacklist, gate loosening, universe swaps without a new mechanism, and the funding/XS/OI hunt (rows 4, 5, 10, 16, 34, 83). Every thesis must list its nearest dead rows by number and state why the mechanism differs.

## 8. kb_check

Command run exactly: `python3 -m research.swarm.lib.kb_check` (exit code 0). Output verbatim:

```
KB OK
```
