# TASKS — 5m_mean_revert improvement: taker-vs-maker fill replay (2026-06-29)

Goal: improve `5m_mean_revert`. First study: does the maker-only (PostOnly) entry
cost the slot real edge? Build a screening-grade OHLCV replay that regenerates 90d
of signals and compares maker-fill vs taker-fill net edge.

Context (verified this session):
- Slot is LIVE/ACTIVE, identical maker-only entry path as main bot
  (bot.py:2007 -> exchange.open_long/open_short -> _try_limit_entry, PostOnly, no taker fallback).
- Only 2 live trades ever (+$0.17 net); 5 PostOnly misses since Jun 24.
- Botwide maker fill rate ~27% (48 fills / 176 attempts, 7d) -> 0-for-5 is normal variance.
- ST2.0 taker-fallback verdict does NOT transfer (different signal shape); but edge-hunt
  lessons say taker fees kill thin edges -> must quantify in NET PnL.
- ATR-adaptive SL/TP collapses to flat 1.2%/1.6% under live config (risk_manager.py:519-528).

## Plan
- [ ] Build `scripts/slot_lab/mean_revert_replay.py` reusing:
  - [ ] `backtest.fetch_ohlcv_full` (90d 5m signals + 1m exit path)
  - [ ] `add_all_indicators` + `strategies.bb_mean_reversion_strategy` (bar-by-bar signal regen)
  - [ ] `st2_lab.exit_replay._simulate` (exit engine, params sl_pct=1.2/tp_pct=1.6/hold_secs=14400)
  - [ ] own `_net` with per-leg fee (maker 0.01% vs taker 0.06% entry; slippage 0.05% on taker)
  - [ ] `st2_lab.stats.bootstrap_diff_ci` for CI; walk-forward split
- [ ] Decision matrix output (maker net x taker net)
- [ ] Runtime honesty caveats printed
- [ ] Verify: smoke run (2 pairs / short window) + cross-check regenerated signals vs real logged misses

## Verification
- [x] Compiles + imports clean (py_compile; bootstrap_diff_ci confirmed = bug-fixed independent-resample version)
- [x] Smoke run 2 pairs/14d — full pipeline OK (regen -> path -> simulate -> CI -> walk-forward -> verdict)
- [x] Faithfulness cross-check vs real logged misses (by RSI fingerprint):
      EXACT matches — ADA short RSI 72.0/vol 1.3x; XLM short RSI 73.8 vs live 73.6. Logs confirmed PT (UTC-7).
      CAVEAT: ~half of checkable live signals reproduced; misses due to backtest-vs-live gap
      (live evaluates the FORMING 5m candle intrabar; replay uses closed-bar values). Screening-grade
      on the signal DISTRIBUTION, not a per-trade audit — as scoped.
- [ ] Full 90d/15-pair run (PID 74890 -> reports/mr_replay_90d.json) — IN PROGRESS

## Review
(pending)
