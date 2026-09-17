# MANDATE — desk run 2026-09-17-1152

Written by the DESK BRIEF seat. Clock: now = 2026-09-17T18:52:14Z (UTC), today = 2026-09-17.
Run dir: `research/swarm/runs/2026-09-17-1152/`. Knowledge base: `research/swarm/kb/` (canonical if anything here differs).
kb_check status: **KB OK** (see section 8; output pasted verbatim).

Governing documents, obeyed in full: `research/swarm/kb/CONSTRAINTS.md`, `research/swarm/kb/STANDARDS.md`, `research/swarm/kb/DATA.md`, `research/swarm/kb/DEAD_LIST.md`.
Run parameters from `research/swarm/runs/2026-09-17-1152/launch_args.json`: max_analysts 8, max_screens 5, dry_run false.

---

## 1. Purpose (not a threshold)

The owner's goal of growing a small account is the desk's **PURPOSE**. It is stated here as purpose and nothing else — it is **NOT a screening threshold**.

The owner's **ULTIMATE aspiration**, recorded 2026-09-17 in the owner's words — "keep it in mind, don't set it yet" — is +10% account ROI per day. It is an **aim** the desk works toward by compounding real, verified edges. It is:
- **never** a bar any thesis is judged against;
- **never** a licence for leverage, sizing, or aggression in place of edge.

The pass bar is, and stays: **per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero** — i.e. CONSTRAINTS "viable" 1-5, reproduced here so no seat has to re-derive them:
1. Train-era screen: n >= 30 and bootstrap CI95 of net bps excludes 0 (after `c`).
2. Observed WR >= p* for the spec's TP.
3. Time-to-verdict (n=50) <= 26 weeks at expected frequency.
4. Every symbol in the universe passes `lot_check` at $200 notional.
5. Signal is computable on closed bars from data the bot actually has.

**No daily-ROI target is applied to any thesis in this run.** No seat writes one anywhere.

---

## 2. Capital and sizing

- Design basis **$200** (CONSTRAINTS, Capital and sizing).
- Position sizing for every screen: `fee_math.position_notional()` -> **200.0** USD notional (10% margin at 10x). Verified this run:
  `python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"` -> `200.0`.
- Two paper slots max at this size; **no cross-sectional baskets** (CONSTRAINTS).
- Lot minimums (USD notional per lot), verbatim from `fee_math.LOT_MIN_USD`, printed this run — do not round:
  `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`
  `minOrderValueRv` 1 USDT. Every symbol in a thesis universe must pass `fee_math.lot_check` at $200 notional (viable #4). Any symbol outside `LOT_MIN_USD` must be checked with `lot_check`, not assumed.

---

## 3. Minimum net edge after c = 11.5 bps

Cost stack, from `fee_math` (printed this run, never re-derived by hand):
- `fee_math.FEES_RT_BPS` = **7.0** bps (maker entry 0.01% / taker exit 0.06%, the bot's real mix)
- `fee_math.ADVERSE_BPS` = **4.5** bps (measured adverse selection after fill)
- `fee_math.C_BPS` = **11.5** bps (total `c`)

Required win rate for symmetric TP/SL of `x` bps is `p* = (x + c) / 2x` (`fee_math.p_star`). Target ladder, command run exactly as specified:

```
$ python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

Justification from CONSTRAINTS: scalping is fee-trapped — sub-0.1% moves cannot pay (25 bps needs 73.0% WR, 50 bps needs 61.5%). The desk therefore targets **100-300 bps moves**, where p* is roughly **52-56%** (55.75% at 100 bps down to 51.92% at 300 bps per the output above). The minimum acceptable net edge is not a fixed bps number chosen by hand: it is whatever the screen's `net_bps_mean` is, after `c`, with `bootstrap_ci.mean_ci` CI95 excluding 0 (viable #1) and observed WR >= p* for the spec's `tp_bps` (viable #2). Any thesis whose TP is below 100 bps must show why it is not fee-trapped against this ladder.

Robustness (STANDARDS #9): exactly one registered read per thesis — `tp_bps` perturbed +20% and -20%; `net_bps_mean` must keep sign in both. No further grid.

---

## 4. Horizons in scope

- **In scope: intraday-to-multi-day.** Holds from a few hours to several days.
- **Explicitly NOT scalping.** Sub-0.1% targets and sub-hour reaction windows are out (fee-trapped per section 3; 5-min poller per section 5).
- **Event-driven is explicitly IN scope** (scheduled macro prints, exchange/protocol events, listings, unlock-adjacent flows, settlement-time mechanics) — subject to STANDARDS #1 (name the counterparty and why they are forced to pay) and #2 (external source with its actual number).
- **At least two analyst lenses must target holds > 8h.** For any hold > 8h, funding at every 8h settlement crossed must be accounted for in the thesis and the screen (CONSTRAINTS: BTC ≈ +0.01%/8h; meme perps often negative). Funding data is loaded only via `load_data.load_funding(symbol, era, token)` on the train era — it is holdout-gated exactly like price.
- The long-horizon dataset for multi-day / event-driven theses is `long_1h` (section 6).

---

## 5. The bot's execution reality (from CONSTRAINTS)

- **5-min poller** — no sub-minute reaction. Signals must be computable on closed bars.
- **Entries are maker limit orders**; real maker fill ≈ **27%**, and the misses are adversely selected. Simulated fills are screening-grade upper bounds (STANDARDS #10).
- **Exits are taker.**
- Order book snapshots every 60s, depth 5, **BTC/ETH/INJ/ARB only**. No streaming book.
- **The Mac may sleep**; slow horizons (hours-days) tolerate that, 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6:00 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`. Forward test is the only adjudicator.
- Live slots that read the forming bar reproduce only ~40% of closed-bar replays — do not build on forming-bar signals (STANDARDS #4).

---

## 6. Datasets and train/holdout boundaries (from `research/swarm/kb/DATA.md`)

Load only through `research.swarm.lib.load_data`; never read caches by hand in a screen.

| dataset key | path | symbols | coverage | timeframes | train ends |
|---|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols | 2026-06-01 -> 2026-09-02 23:55 UTC | 1m, 5m, 1h | ≈ **2026-08-10**; holdout after |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols: 1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP | 1h 2025-06-27 -> 2026-08-01 | 1h (5m partial) | ≈ **2026-04-24**; holdout ≈ 2026-04-23 -> 08-01 |

- `mr_edge` funding: `funding_<SYM>_USDT_USDT.json` rows `{ts ms, rate}`, loaded via `load_funding(symbol, era, token)` — holdout-gated at the same era boundary as price.
- **Use `long_1h` for multi-day / event-driven theses** (DATA.md).
- **Cross-dataset holdout caveat (DATA.md / STANDARDS #6):** `mr_edge` train (2026-06-01 -> ~08-10) sits inside the `long_1h` holdout window, and 18 of 19 `long_1h` symbols also exist in `mr_edge`. A thesis on `long_1h` may not use `mr_edge` data dated on or after 2026-04-23 in any exploratory probe or signal; the gatekeeper rejects a `long_1h` thesis whose probes did.
- **Holdout is never read in this run.** No seat passes `era="holdout"` or `era="all"`, touches the committee token, or reads cache files directly. `load_data.fetch_ohlcv_ccxt` is committee-token gated and outside the research stage — no analyst or screen calls it.
- Artifact naming (STANDARDS #7): train-era screens write `out.json` / `trades.csv` under `screens/<id>/`; nothing else is produced this run.
- Exploratory-only bot data (not loadable via `load_data`): `logs/l2_ticks/<SYM>/<date>.jsonl.gz` (BTC/ETH/INJ/ARB, 2026-07-13 -> 09-10), `logs/flow_capture.jsonl` (2026-05-11 -> 09-09), `logs/entry_snapshots.jsonl` (1,374 live entry contexts 2026-04-07 -> 09-14).

---

## 7. Gatekeeper watch list — 15 DEAD_LIST rows most likely to be relabeled this run

Source: `research/swarm/kb/DEAD_LIST.md` (139 lines, rows 1-103). These are the gatekeeper's relabel FILTER, **not ideas** (STANDARDS #2, #13). Every thesis cites its nearest rows and states why its mechanism differs. Selected for this run's intraday-to-multi-day, event-driven, >8h-hold emphasis:

| row | 5-word gist |
|---|---|
| 3 | 1h vol-expansion fade, split-selected |
| 4 | Naked funding harvest = price drift |
| 6 | Liquidation cascade reversion: continues instead |
| 7 | Time-of-day / calendar edges null |
| 13 | BTC time-series momentum fails deflation |
| 18 | On-chain, ETF-flow, seasonality all out |
| 19 | Token-unlock short: real but 86% DD |
| 20 | Funding-spike carry: armed, not deployed |
| 25 | S/R bounce zones gross-negative |
| 33 | Donchian trend paper — owner declined |
| 34 | Linear-vs-inverse funding spread parked |
| 76 | Multi-day MR / overnight window dead |
| 78 | 1h Bollinger-squeeze breakout refuted |
| 83 | Funding z-score contrarian: R² 0.003 |
| 84 | FOMC/CPI first-candle momentum, unexecutable |

Adjacent rows to keep in view when a thesis is event- or funding-flavored: 5 (cross-sectional momentum), 10 (open-interest, no data), 12 (basket TSM dilution), 16 (cross-venue funding arb), 77 (value-area breakout), 82 (funding-settlement vol breakout gate). Owner directives (STANDARDS #14) apply on top of the rows: no re-proposing demoted books (main live, ST2.0, 5m_MR live, Donchian live), no BTC blacklist, no gate loosening, no universe swaps without a new mechanism, no funding/XS/OI hunt.

---

## 8. kb_check

Command run exactly: `python3 -m research.swarm.lib.kb_check` (cwd = repo root). Output verbatim:

```
KB OK
```

Exit code 0. The kb was not modified by this seat.
