# PRE-REGISTRATION — 5m_mean_revert edge search (5 families, one holdout read each)

**Registered**: 2026-09-03 ~9:55 PM PT, owner order ("find a strong edge for 5m_mean_revert"), plan approved 9:51 PM PT.
**Thesis**: the slot's live geometry, HTF-trend exposure, short-side tape context, funding context and sub-populations
were inherited or never tested for THIS slot. Each is tested once, mechanically, against frozen criteria. Everything in
the closed ledger (`reference_mr_overnight_program_2026-07-14`, `reference_mr_ledger_trio_2026-08-01`,
`reference_mr_universe_scan_2026-08-01`, `reference_mr_deep_dive_2026-09-03`) is EXCLUDED: taker fills, signal
loosening, rest/requote/patience levers, universe/symbol curation, BTC blacklist, V17 RSI-65, trend-day fuse, timeout
filter, streaks, weekday, small caps, capital scale, ATR%/band-boundness/ADX symbol discriminator.

## Frozen data
- Window 2026-06-01 00:00 UTC → 2026-09-03 00:00 UTC. TRAIN = 6/1 → 8/3 23:59:59 UTC. HOLDOUT = 8/4 00:00 + 8 h embargo → 9/3.
- Universe (35, frozen 9/3 9:52 PM PT in `reports/mr_edge_2026/universe.json`): union of the 22 June-cache symbols, the
  14 pairs in the current scanner rotation, and every symbol with ≥5 distinct days in `logs/flow_capture.jsonl` in-window.
  No curation, no re-scoring.
- Bars: 5m (signals), 1m (exit path), 1h (ADX cap). Funding: Phemex `fetchFundingRateHistory`, last SETTLED rate ≤ signal ts
  (parity gap recorded: live uses the predicted rate).
- Signal engine: `strategies.bb_mean_reversion_strategy` bar-by-bar on `indicators.add_all_indicators`, PLUS the live long
  RSI floor (rsi_fast < 22 blocks longs). `MR_SHORT_RSI_MIN` = 70 (default). OB/tape gates are NOT replayed (no historical
  L2) except where flow_capture supplies buy_ratio for H3 — recorded limitation.
- Economics: $15 margin @10x ($150 notional), maker 0.01% / taker 0.06% per side, trail arm 8% ROI, breakeven ratchet on.
- Live cell: SL 1.2% / TP 1.6% price, trail 8%, 4 h hard time exit with +50% extension when unrealized ROI ≥ 5% at 4 h.
- Fill model: fill-all at the signal bar close. Real maker fill ≈ 27%, adverse selection not modeled → every dollar is an
  UPPER BOUND. Only relative comparisons (cell vs live, kept vs removed) are decision metrics.

## Families and grids (111 trials nominal; the screen script reports the true count)
- **H1 exit geometry**: TP {1.0,1.6,2.0,2.4,3.0}% × SL {0.8,1.2,1.6,2.0}% × time {2,4,6,8} h, minus the live twin
  (tp1.6_sl1.2_t4h) = 79 cells, each vs the live cell.
- **H2 1h-ADX cap**: keep entries only when adx1h ≤ {35, 40, 50} (adx1h built the live way: 5m→1h incl. forming bar,
  trailing 100 bars). Null adx1h excluded from both cohorts.
- **H3 short tape context**: skip SHORTS when buy_ratio ≥ {0.80, 0.90, 0.95} and trade_count > 20 (nearest flow_capture
  row ≤ ts within 120 s). Null flow → kept. Longs untouched.
- **H4 funding context**: skip shorts when funding ≤ −X, skip longs when funding ≥ +X, X ∈ {0.0001, 0.0003, 0.0005}
  (0.01/0.03/0.05% per 8 h). Null funding → kept.
- **H5 sub-populations**: the single-dimension buckets in `scripts/slot_lab/mean_revert_filters._buckets` (side, RSI
  extremity, volume multiple, 5m ADX regime, PT hour block, BB-width tercile, long&ADX<15). Kept = in bucket.
- **H0 (registered 7/14, still pending)**: OB-imbalance gate counterfactual at n≥10 episodes. NOT readable in this
  program (bot.log rotation keeps ~10 days). A gate-block archiver is added so the bar becomes reachable. No verdict here.

## Statistics (frozen)
- One-sample bootstrap mean CI, 2000 reps, fixed seed. Diff CIs via `st2_lab.stats.bootstrap_diff_ci` — independent
  resample, then sort the DIFFS (house rule; conservative for paired H1 comparisons — accepted).
- `deflated_sharpe_ratio` with n_trials = total trials. Pooled `benjamini_hochberg` α = 0.10 across all trial p-values.
- 3-fold chronological walk-forward sign check (`st2_lab.walkforward.walk_forward_splits`).
- Min-n: kept ≥ 40 train / ≥ 20 holdout; removed ≥ 15; H5 buckets ≥ 25.

## Selection and verdict (frozen)
- TRAIN selection is mechanical, ≤1 winner per family. Filters (H2-H5): removed mean < 0 with CI excl 0 AND kept mean >
  all-signal mean AND BH pass AND DSR > 0.95 AND WF 3/3 AND min-n. H1: diff-vs-live CI > 0 AND BH AND DSR > 0.95 AND
  WF 3/3 AND min-n. Tie-break: highest DSR.
- HOLDOUT: ONE read per family, train winners only, lock file per family. The screen refuses holdout unless
  sha256(this file) equals `meta.prereg_sha` in `signals.json`.
  - **STRONG** = kept/cell mean ≥ +$0.50/trade AND one-sample CI excl 0 AND (H1) diff-vs-live CI > 0 AND full-window WF 3/3.
  - **WEAK** = CI excl 0 but mean < $0.50 → recorded, one pre-registered re-read after 30 more days, no ship.
  - **NULL** = anything else → family closed; no re-grid, no threshold retuning.
- A STRONG survivor is NOT an edge yet. It goes to a real-money forward verdict line (`mr_edge_<family>` in the lab
  adjudicator: n = 20 live trades opened after deploy, kill at net ≤ $0 at n=20 or ≤ −$6 at any n, runtime revert
  sentinel), shipped only after TDD + /pre-restart-audit + owner "go".

## Anti-fishing clause
One grid per family, one holdout read per family, thresholds fixed above. Any deviation discovered during execution
(data gaps, fidelity-gate misses, bucket-count differences) is REPORTED as a finding, not fixed and re-run.
The fidelity gate (≥ 90% of the 45 real MR entries reproduced at the same bar and side) must pass before any train read.
