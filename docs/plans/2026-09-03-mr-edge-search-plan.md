# 5m_mean_revert edge search — pre-registered research program

## Context

Jonas asked for a strong edge for the 5m_mean_revert slot, the only real-money book ($15 @ 10x). The slot is +$4.62 net over 31 live trades (fees are 35% of gross); since the 7/31 peak it is 2-for-12 (−$10.78), short-side TP hits collapsed from 9/19 to 1/12, and no code change caused it (9/3 deep dive, `reference_mr_deep_dive_2026-09-03.md`).

The prior record is unforgiving and binds this plan (META-RULE #7):
- ~30 MR levers already DEAD/NULL/FORBIDDEN (taker fills, signal loosening, rest/requote levers, universe scan, trend fuse, timeout filter, streaks, weekday, small caps, capital, symbol discriminator, V17 RSI-65). None may be re-proposed.
- The only prior full replay (`reports/mr_replay_90d.json`, 6/30, n=309 signals) put the maker-fill-all expectancy at **+$0.025/trade with a CI straddling zero**. The raw signal has no proven edge at fill-all; the live +EV came from the ~27% of signals that fill.
- House rule: replays can only REJECT; forward testing on real money is the only adjudicator (`reference_edge_hunt_exhaustion.md`).

What has **never** been tested for this slot specifically, and is therefore the legitimate search space:
1. MR-specific exit geometry (the +16%/−12% ROI, 4h time-exit geometry was inherited; wider-SL/partial-TP tests were on the main-bot rig only).
2. A 1h-ADX cap on entries (deep dive: the worst post-peak short went in at the highest htf_adx on file).
3. Short-side conditioning on tape buy_ratio (0/3 since the 7/12 exemption vs 2/2 before, n too small).
4. Funding-rate context (never used as an MR entry filter; `fetchFundingRateHistory` is available).
5. Sub-population screen (hour/session, BB width, RSI extremity, volume multiple) — `mean_revert_filters.py` implements it with FDR/DSR guards but was never run to a verdict.
6. Registered pending: OB-imbalance gate counterfactual at n≥10 episodes — currently **data-blocked** (bot.log rotation keeps ~10 days; only 2 episodes survive).

**Honest expectation:** given the baseline, the most likely outcome is NULL across all families, reported with receipts. "Strong" is defined numerically below so the answer is unambiguous either way.

## Definition of "strong edge" (frozen before any read)

At $15 margin, on the HOLDOUT window only, a family's kept cohort (or geometry cell) must show:
- net expectancy ≥ **+$0.50/trade** (≈ +3.3% ROI/trade; live history is +$0.15), AND
- one-sample bootstrap CI excluding 0, AND
- (H1) diff-vs-live-geometry CI > 0 via independent-resample `bootstrap_diff_ci`, AND
- 3-fold chronological walk-forward sign 3/3 on the full window, AND
- survives deflated Sharpe (n_trials = all cells) and Benjamini-Hochberg FDR (α=0.10) pooled across families.

"Weak/keep" = CI excl 0 but < $0.50 → recorded, one pre-registered re-read after 30 more days, no ship. "Null" = anything else → family closed.

Only a survivor goes to a **forward verdict line** on real money (owner rule: no shadow deploys), n=20 live trades, kill at net ≤ $0 at n=20 or ≤ −$6 at any n. At ~0.4 trades/day that is ~7 weeks per survivor.

## Phase A — Data refill (read-only vs the bot, ~75 min wall)

New `scripts/slot_lab/mr_edge_fetch.py`: fixed-window paginator (own `ccxt.phemex` client, `enableRateLimit`, 0.6 s spacing, `nice -n 19`, per-symbol checkpoint files, resumable). Copies the `FETCH_LIMIT=1000` + retry pattern from `backtest.fetch_ohlcv_full` (backtest.py:277) but with absolute `since`/`until`.
- Window: 2026-06-01 → 2026-09-03 UTC (train + holdout; overlaps the June cache for a parity check).
- Universe (frozen in prereg, no curation): union of the 22 `backtest_data_june/` symbols, current 12 scanner pairs, and every symbol with ≥5 distinct days in `logs/flow_capture.jsonl` in-window (~34 symbols).
- Timeframes: 5m (signals), 1m (exit path, required by `mean_revert_replay._build_path`), 1h (ADX cap). Plus `fetchFundingRateHistory` per symbol (8h cadence).
- Output: `reports/cache/mr_edge_20260601_20260903/{SYM}_{tf}.pkl` + `funding_{SYM}.json` (~220 MB). ~5,800 calls total.

## Phase B — Prereg doc, frozen BEFORE any read

`docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md`, same skeleton as `2026-08-01-mr-universe-ranginess-scan-prereg.md`: thesis per family, frozen universe, window, split (train 6/1→8/3, holdout 8/4→9/3, 8 h embargo), fees ($15 @10x, maker 0.01% / taker 0.06%, trail arm 8%), exact grids, trial count, FDR/DSR/min-n, mechanical selection rule, holdout pass conditions, dead-lever exclusion list, parity caveats, anti-fishing clause (one holdout read per family, no retuning). SHA of the prereg is recorded by the screen script; it refuses to run holdout without it.

## Phase C — Signal table (one artifact, all families read from it)

New `scripts/slot_lab/mr_edge_signal_table.py`, importing `mean_revert_replay` helpers (`_build_path`, `_net`, fee constants; override MARGIN=15, NOTIONAL=150, `backtest.TRAIL_ARM_ROI=8.0` as `gate_block_counterfactual.py:86` does).
- Regenerate signals bar-by-bar with `strategies.bb_mean_reversion_strategy` + `indicators.add_all_indicators`, **adding the live long RSI floor (22.0, bot.py:3193)** which the old regen omitted.
- Per signal: symbol, ts, side, entry px, rsi, rsi_fast, vol_ratio, bb_width, adx5m, **adx1h built the live way** (5m→1h resample incl. the forming bar, trailing 100 bars, bot.py:901-916), hour PT, session; nearest `flow_capture` record ≤ ts within 120 s (parsed with `st2_lab.dataset._normalize`) giving buy_ratio/imbalance/trade_count; `scanner_active` flag (flow row within ±10 min) so results can be reported live-faithful; last settled funding rate ≤ ts.
- Outcomes on the same 1m path via `st2_lab.exit_replay._simulate`: the LIVE cell (SL 1.2% / TP 1.6% / trail 8% / 4h with the +50% extension rule from risk_manager.py:260-277) and every H1 cell: TP {1.0,1.6,2.0,2.4,3.0} × SL {0.8,1.2,1.6,2.0} × time {2h,4h,6h,8h} → `net_by_cell` per signal.
- **Fidelity gate before any read:** the 45 real MR rows in `logs/entry_snapshots.jsonl` must be reproduced (same side, same 5m bar, ≥90%; rsi_fast/htf_adx/vol_ratio within tolerance) or the script aborts (mirrors `mr_variant_grid.py`'s V0 gate).
- Caveats printed verbatim: fill-all at close (real maker fill ~27%, no adverse selection modeled) → every dollar is an upper bound; only relative comparisons are decision metrics. Funding: live uses the predicted rate, replay uses settled — recorded as a parity gap.

## Phase D — Screen: train read, then ONE holdout read per family

New `scripts/slot_lab/mr_edge_screen.py --phase train|holdout`.
- Trials: H1 79 non-live cells + H2 3 (adx1h cap 35/40/50) + H3 3 (skip shorts when buy_ratio ≥ 0.80/0.90/0.95, only when trade_count > 20) + H4 3 (skip shorts when funding ≤ −X, longs when ≥ +X; X = 0.01/0.03/0.05% per 8h) + H5 23 buckets (reuse `mean_revert_filters._buckets`) = **111 trials**.
- Stats: `st2_lab.stats.deflated_sharpe_ratio(n_trials=111)`, one pooled `benjamini_hochberg(alpha=0.10)`, `bootstrap_diff_ci` (independent resample), `walkforward.walk_forward_splits` 3-fold. Min-n: kept ≥40 train / ≥20 holdout, removed ≥15, H5 buckets ≥25.
- Train selection is mechanical, ≤1 winner per family. Holdout read only for train winners. Verdict per the definition above.
- H0 (OB gate): cannot be read now. Ship `scripts/slot_lab/mr_gate_block_archiver.py` (launchd every 6 h, framework Python binary, logs to ~/Library/Logs/Phmex-S) that appends dedup'd `[OB GATE]/[TAPE GATE] 5m_mean_revert` lines to `logs/mr_gate_blocks.jsonl` so the registered n≥10 bar becomes reachable. No verdict from this program.

## Phase E — Survivors only: forward line + live ship (needs a second "go")

- Register `mr_edge_<family>` in `scripts/lab_adjudicator/adjudicate.py` EXPERIMENTS (registered_ts, verdict_n=20 live trades opened after deploy, mode=="live", excluding min_margin_skip; kill net ≤ $0 @ n=20 or ≤ −$6 any n; sentinel `.revert_5m_mean_revert_<family>` checked by bot.py at runtime to disable the gate without restart). Grader = de-sided copy of `grade_side_line` (adjudicate.py:780).
- Change surface per family: H2 one gate after bot.py:3206 using the existing `_slot_htf_adx` (zero new API calls); H3 a short cap inside `_tape_gate_blocks_buy_ratio` (bot.py:340); H5 a feature gate next to H2; H4 uses existing `_fetch_funding_rate` (bot.py:980, 4 h cache) — a REST call in the live loop, fail-open, flagged; H1 `exact_geometry=True` + sl/tp on the slot (bot.py:640) — time-exit change needs a per-slot field plumbed to `risk_manager.should_time_exit`, and the exact-geometry live-order path has never run live (SR_BOUNCE v2 was paper) → extra audit.
- Every new blocked counter propagates to notifier.py, scripts/daily_report.py, web_dashboard.py (CLAUDE.md rule). TDD + /pre-restart-audit + Jonas "go" before restart.

## Files

Create: `scripts/slot_lab/mr_edge_fetch.py`, `mr_edge_signal_table.py`, `mr_edge_screen.py`, `mr_gate_block_archiver.py` (+ launchd plist), `docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md`, `reports/mr_edge_2026/` artifacts, tests for the fetch paginator, fidelity gate, and screen selection rule.
Modify (Phase E only, after survivors): `bot.py`, `config.py`, `.env`, `scripts/lab_adjudicator/adjudicate.py`, reporting surfaces.
Reuse: `backtest.fetch_ohlcv_full` (pattern), `mean_revert_replay` helpers, `exit_replay._simulate`, `st2_lab.stats`, `st2_lab.walkforward`, `mean_revert_filters` buckets/guards, `dataset._normalize`, `gate_block_counterfactual.attach_snapshots` pattern.
Isolation: research scripts never import bot.py/exchange.py/config.py/risk_manager.py; own ccxt client; `nice -n 19`; the live bot (PID 78531) is not touched.

## Verification

- Fetch: row counts vs expected bars per window per symbol; June overlap matches `backtest_data_june/` bar-for-bar.
- Signal table: fidelity gate vs the 45 real MR entries; live cell reproduces `mean_revert_replay` results on overlapping symbols/dates.
- Screen: unit tests on the selection rule with synthetic data (a planted edge is found; a null set yields no winner); prereg SHA check; `py_compile`; isolation grep.
- Every reported number cites the artifact file; verification agent re-derives train and holdout tables independently before anything is presented (META-RULE #2).

## Estimate

Engineering ~1.5 days of agent work (parallel: fetch script + prereg + signal-table + screen tests), ~75 min fetch, ~20 min compute. Result: a train/holdout verdict table for 5 families. Then, per survivor, ~7 weeks of real-money forward adjudication before it can be called an edge.

---
## Execution status (as of 9/3 10:12 PM PT)
- Approved 9:51 PM PT. Prereg frozen 9:55 PM: `docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md` (sha a0bb7fd1…f45e7d).
- Universe frozen (35 symbols): `reports/mr_edge_2026/universe.json`.
- Phase A script done (21 tests); fetch running since 9:57 PM (PID 92534, nice 19), ETA ~11:50 PM PT.
- Phase D screen done (23 tests; 110 trials: 79 geometry cells + 3 ADX + 3 tape + 3 funding + 22 buckets).
- H0 sink deployed: `scripts/slot_lab/mr_gate_block_archiver.py` + launchd `com.phmex.mr-gate-archiver` (6 h); 13 blocks archived.
- Phase C signal-table builder in progress. Then: fidelity gate → train read → one holdout read per family → independent verification → report.
- Live checklist: `TASKS.md` (section "5m_mean_revert edge search").
- 10:17 PM: fidelity gate FAILED on closed-bar regen (2/5). Cause: live fires on the FORMING candle. Prereg AMENDMENT v2 (10:20 PM, before any read): forming-bar regen + family H6 entry-timing (113 trials) + real-money confirmed-vs-forming read. Memory: reference_mr_forming_bar_signals_2026-09-03.md.
- 9/4 2:14 AM: full forming-bar run — fidelity 28/30 PASS, 840 signals. 2:17 AM TRAIN read: baseline −$0.024/trade (n=608), 113 trials, 0 winners in every family → no holdout read. 2:23 AM independent verification: 0 discrepancies. RESULT: NULL. Memory: reference_mr_edge_search_2026-09-04.md.
