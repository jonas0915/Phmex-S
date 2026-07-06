# R1 — Lab Adjudicator Build (2026-07-05, overnight)

Repurposes the st2-lab machinery into a live-experiment ADJUDICATOR + execution-quality
WATCHDOG. New code only, in `scripts/lab_adjudicator/`; **zero live-bot files touched**
(bot.py, risk_manager.py, exchange.py, config.py, .env all clean per `git status`).
The com.phmex.st2-lab launchd job is untouched and still running as-is; both new
scripts are standalone-runnable — launchd wiring is the follow-up after Jonas reviews.

## What was built

### 1. `scripts/lab_adjudicator/adjudicate.py` — nightly grader for LIVE forward tests
- Registry (`EXPERIMENTS` module constant) with deploy timestamps **verified against
  bot.log restarts**: trail_arm_8 = 7/05 9:01 PM PT (bot.log:53105), sizing_15 =
  7/04 10:48 AM PT (bot.log:15650), mr_bundle = 7/03 7:48 PM PT (memory, PID 61576).
- **trail_arm_8**: avg win of trailing_stop+early_exit exits vs $0.46 baseline;
  givebacks = peak ROI ≥ +5% (bot-tracked `peak_price`, risk_manager.py:175-178
  semantics — 60s-sampled, conservative proxy for candle-MFE) then closed at full SL
  (stop_loss/exchange_close, net<0). REVERT-TRIPPED: ≥3 givebacks in first 20
  trail-relevant trades, or avg win < baseline once ≥10 wins exist (below 10 wins the
  avg-win criterion is deliberately not adjudicated — tiny-n honesty).
- **sizing_15**: realized margin/trade post vs last-50 pre (bootstrap diff CI) +
  daily-halt frequency ("DAILY LOSS HALT" lines, deduped per PT date). Report-only —
  no revert criterion was defined for sizing.
- **mr_bundle**: fills/misses/re-quotes for 5m_mean_revert since deploy from
  bot.log (+bot.log.1 — see gotchas), sidecar counters, live-slot record; fill rate
  vs 15% baseline with bootstrap CI; PASS needs ≥20 attempts AND CI lower bound > 0.
- Stats reuse `scripts/st2_lab/stats.py::bootstrap_diff_ci` (independent resampling,
  sort-the-diffs — house lesson). One-sample-vs-constant CI expressed as
  `bootstrap_diff_ci(sample, [constant])`, seeded → deterministic.
- Telegram via `st2_lab.notify.telegram_alert` (stdlib, .env-reading, best-effort —
  the existing lab pattern), behind `--telegram`. Not sent tonight.

### 2. `scripts/lab_adjudicator/drift_watchdog.py` — adverse-selection monitor
- Imports `scripts/l2x_lab/postentry_drift.py` by path (importlib) and reuses its
  verified machinery (load_trades w/ phantom exclusion, cached window fetch,
  signed_bps, iid + day-cluster bootstrap CIs).
- Rolling 14-day mean 1m post-entry drift on real htf_l2 fills. ALERT if
  mean < −6.0 bps (floor) or < baseline(−4.5) − 2.0 = −6.5 bps. n<3 → NO-DATA,
  no alert. `classify()` is pure and unit-tested. Flags: `--no-fetch`,
  `--window-days`, `--telegram`.

### 3. Logging
Both write to `~/Library/Logs/Phmex-S/lab_adjudicator.log` /
`~/Library/Logs/Phmex-S/drift_watchdog.log` (never ~/Desktop paths — tonight's
launchd/TCC lesson) and print a compact digest to stdout.

## Gotchas found while building (real, verified)
1. **`[MAKER] Limit` lines carry no slot tag** (bot.log 2026-07-04 12:19:30), so the
   mr_watch-style "attempts" counter (filter on `5m_mean_revert` then match
   `[MAKER] Limit`) can never fire — it structurally counts 0. The adjudicator infers
   signal-level attempts as fills + final-miss lines instead (one terminal line per
   signal; a re-quoted miss still ends in a single miss line — verified in the 7/04
   12:19-12:21 LTC trace). NOTE: scripts/mr_watch.py has this same dead counter; not
   fixed here (out of scope — no existing files modified), worth a follow-up.
2. **bot.log rotates ~every 3 days** (bot.log.1 = 7/01-7/04); a since-deploy window
   routinely spans the boundary, so the adjudicator reads bot.log.1 + bot.log.

## Test results
- `python3 -m py_compile` clean on both scripts + test file.
- New: `tests/test_lab_adjudicator.py` — **24 tests, all passing** (fixture-based:
  fake state files via tmp_path, fake log text; covers giveback counter incl.
  short-side peak ROI and the net<0 requirement, revert-trip logic (2 vs 3 givebacks,
  window cutoff at 20, avg-win min-n gate), n=0 no-verdict, CI computation
  (coverage, determinism, n<3 → None), sizing grader from a fake state file w/
  halt-date filtering, MR log parsing w/ since-filter, drift classify thresholds
  incl. boundary).
- Full suite: **334 passed** (310 pre-existing + 24 new), 0 failures —
  `python3 -m pytest tests/ -q` → `334 passed in 56.50s`.

## Real output (actual runs, 2026-07-05 ~10:05 PM PT)
```
LAB ADJUDICATOR — live forward tests (Jul 5 10:04 PM PT)
[trail_arm_8]  WATCH — n=0 — no verdict | n=0 post-deploy, 0 trail-relevant, 0 givebacks | avg win n/a (0 wins) vs $0.46 base
[sizing_15]    WATCH — cap NOT binding — Kelly still sizing below $15 (known: risk_manager.py:399-415); 1 daily-halt day(s) since deploy | margin $9.27/trade post (n=8) vs $8.27 pre (n=50), diff +1.00 CI[-0.10,+2.01] | halts 1 day(s) (0.68/day)
[mr_bundle]    WATCH — 1/20 attempts — no verdict yet | 1 attempts · 0 fills · 1 misses · 1 re-quotes | fill 0% vs 15% base CI n/a (n<3) | live 0 trades 0W $+0.00 | counters: requote_miss=1

DRIFT WATCHDOG (Jul 5 10:05 PM PT) — OK: -5.33 bps @1m vs -4.5 baseline (floor -6.0) | rolling 14d htf_l2 fills n=60 (of 60 recent, 0 uncovered) iidCI[-11.0,-1.3] dayCI[-13.5,-1.4]
```
Cross-checks: trail deployed 1h before run → n=0 is correct. MR "1 attempt / 1 miss /
1 re-quote" matches the sidecar (`requote_miss: 1`) and the single 7/04 LTC trace.
Sizing margins post-deploy ($9.27 avg, n=8) confirm the Kelly-caps-below-$15 finding.
Drift −5.33 bps @1m (n=60) is mildly worse than the −4.5 baseline but inside both
alert thresholds → OK; worth watching.

## Side effects
Only `reports/cache_l2x_drift/` gained/refreshed 1m-candle cache files (the shared
l2x cache, by design — one previously-truncated ETH window was refetched).

## Left to wire (follow-up, after Jonas reviews)
1. launchd job (or fold into the existing nightly): run both scripts nightly with
   `--telegram`; stdout/stderr to `~/Library/Logs/Phmex-S/` paths (NOT ~/Desktop).
2. Decide sizing_15 disposition — the adjudicator confirms the cap isn't binding;
   the open investigation (project_trade_size_15) owns the verdict.
3. Optional: fix the dead `[MAKER] Limit` attempts counter in scripts/mr_watch.py
   (same structural miss found here).
4. As trail_arm_8 data arrives, sanity-check the bot-peak vs candle-MFE proxy on the
   first few givebacks/wins.
