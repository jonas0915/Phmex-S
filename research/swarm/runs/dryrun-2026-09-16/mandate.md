# DESK MANDATE — run dryrun-2026-09-16 (DRY RUN / plumbing test)

Clock: now = 2026-09-17T05:18:08Z (UTC); today = 2026-09-16 (9/16 10:18 PM PT).
Run dir: research/swarm/runs/dryrun-2026-09-16/. Knowledge base: research/swarm/kb/ (canonical if anything here differs).
kb_check status: **KB OK** (see section 8 for the verbatim output).

## 1. Purpose vs. pass bar

The owner's goal — growing a small account — is the desk's PURPOSE. It is stated here as purpose only. It is NOT a screening threshold and no seat may turn it into one.

The pass bar is, and stays, CONSTRAINTS.md "viable" 1-5:
1. Train-era screen: n >= 30 and bootstrap CI95 of net bps (after c) excludes 0 — `bootstrap_ci.mean_ci`.
2. Observed WR >= p* for the spec's TP — `fee_math.p_star`.
3. Time-to-verdict (n=50) <= 26 weeks at expected frequency — `fee_math.time_to_verdict_weeks`.
4. Every symbol in the universe passes `fee_math.lot_check` at $200 notional.
5. Signal computable on closed bars from data the bot actually has.

In one line: per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero. There is no daily-ROI target anywhere in this run, and none may be written.

## 2. Capital and sizing

- Design basis **$200** (CONSTRAINTS "Capital and sizing").
- Position sizing for screens: `fee_math.position_notional()` → **200.0** USD notional (10% margin at 10x). Source: research/swarm/lib/fee_math.py, printed this run.
- Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums (USD notional per lot), verbatim from `fee_math.LOT_MIN_USD` as printed this run: BTC 77.74, ETH 24.9738, SOL 1.0143, XRP 1.0044, DOGE 1.001. `minOrderValueRv` 1 USDT. Every universe symbol is checked with `fee_math.lot_check`; do not round.

## 3. Minimum net edge after c

Costs (from research/swarm/lib/fee_math.py, printed this run): `FEES_RT_BPS` = 7.0 (maker entry / taker exit), `ADVERSE_BPS` = 4.5, `C_BPS` = **11.5 bps** round trip. CONSTRAINTS: "Scalping is fee-trapped: sub-0.1% moves cannot pay."

Required win rate for a symmetric TP/SL of x bps is `fee_math.p_star(x)` = (x + c) / 2x. Computed this run with
`python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"`, output verbatim:

```
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

Target ladder for this run: **100-300 bps moves**, where p* is roughly 52-56% (100 bps → 55.75%, 150 bps → 53.83%, 200 bps → 52.88%, 300 bps → 51.92%, all from the output above). Minimum net edge: the train-era `net_bps_mean` after c = 11.5 bps must be > 0 with the CI95 excluding 0 (section 1); a thesis whose TP is below 100 bps sits in the fee trap and is out of mandate. All stats come from `research.swarm.lib` — hand arithmetic in prose is a defect (STANDARDS #8).

## 4. Horizons in scope

- **In scope:** intraday-to-multi-day holds. **Event-driven theses are explicitly IN scope** (scheduled macro prints, exchange/on-chain events, unlocks, listings — subject to the DEAD_LIST filter in section 7).
- **Explicitly NOT scalping.** No sub-0.1% targets, no sub-5-minute reaction requirements (CONSTRAINTS: 5-min poller).
- **At least two analyst lenses must target holds > 8h.** Any hold > 8h crosses a funding settlement (every 8h; BTC ≈ +0.01%/8h; meme perps often negative) and the thesis must account for funding at every settlement crossed, using `load_data.load_funding(symbol, era, token)` on train era only (see section 6).
- Live slots that read the forming bar reproduce only ~40% of closed-bar replays — build only on closed bars (STANDARDS #4).

## 5. Execution reality of the Phmex-S bot (CONSTRAINTS)

- **5-min poller** — no sub-minute reaction.
- Entries are **maker limit orders**; real maker fill ≈ **27%**, and misses are adversely selected. Exits are **taker**. Simulated fills are screening-grade upper bounds (STANDARDS #10).
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. No streaming book.
- **The Mac may sleep**: slow horizons (hours-days) tolerate that; 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`.
- Never modify bot trading code (bot.py, strategies.py, risk_manager.py, exchange.py, config.py, .env, any slot file).

## 6. Datasets and train/holdout boundaries (research/swarm/kb/DATA.md)

Load only via `research.swarm.lib.load_data`; never read caches by hand in a screen.

| key | path | coverage | timeframes | train ends |
|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | ≈ 2026-08-10; holdout after. Funding per symbol in `funding_<SYM>_USDT_USDT.json` via `load_funding(symbol, era, token)` — holdout-gated on the same era boundary. |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP), 1h 2025-06-27 → 2026-08-01 | 1h (5m partial) | ≈ 2026-04-24. **Use this for multi-day / event-driven theses.** |

- Longer daily history: `load_data.fetch_ohlcv_ccxt("BTC", "1d", since_ms, until_ms)` (up to ~2 years of 5m/15m/1h/1d public Phemex bars). Any pull must be recorded in the frozen spec's dataset field and saved under `screens/<id>/data_*.pkl` (gitignored).
- Exploratory-only, not loadable via `load_data`: `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (BTC/ETH/INJ/ARB, 2026-07-13 → 09-10), `logs/flow_capture.jsonl` (2026-05-11 → 09-09), `logs/entry_snapshots.jsonl` (2026-04-07 → 09-14).
- **Holdout rule for this run: holdout is never read.** No seat passes era="holdout" or era="all", touches the committee token, or opens cache files directly. Holdout = final 25% of each dataset's range and `load_ohlcv` / `load_funding` refuse it without the token (STANDARDS #6). Non-train outputs would be era-suffixed (`out.holdout.json`) — none are expected in this run.

## 7. Gatekeeper watch list — 15 DEAD_LIST rows most likely to be relabeled this run

Source: research/swarm/kb/DEAD_LIST.md (rows cited by `n`). These are a FILTER, not ideas (STANDARDS #2, #13). Chosen for overlap with this run's scope (100-300 bps, >8h holds, event-driven, multi-day).

| row | 5-word gist |
|---|---|
| 3 | 1h vol-expansion fade, split-luck |
| 4 | Naked funding-harvest short is drift |
| 6 | Liquidation cascades continue, don't revert |
| 7 | Time-of-day / calendar noise |
| 13 | BTC-TSM(28,5) fails deflated Sharpe |
| 19 | Token-unlock short, −86.6% DD |
| 20 | Funding-spike carry: arm, don't deploy |
| 25 | S/R bounce zones gross-negative |
| 33 | Donchian trend: owner declined, never re-offer |
| 76 | Multi-day MR / overnight window dead |
| 77 | Prior-day value-area breakout, no DOA |
| 78 | 1h Bollinger-squeeze breakout, no slippage |
| 82 | Funding-settlement vol breakout gate relabel |
| 83 | Funding z-score contrarian, R² ~0.003 |
| 84 | FOMC/CPI first-candle needs 1-min precision |

Also standing owner directives (STANDARDS #14): never re-propose demoted books (main live, ST2.0, 5m_MR live, Donchian live), the BTC blacklist, gate loosening, universe swaps without a new mechanism, or the funding/XS/OI hunt. Section D of DEAD_LIST.md ("Explicitly UNTESTED mechanisms") carries no row numbers and must not be cited as a row.

## 8. kb_check

Command run: `python3 -m research.swarm.lib.kb_check` (exit 0). Output verbatim:

```
KB OK
```
