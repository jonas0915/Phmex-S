# TASKS — Funding + fee capture (owner pick 9/7 8:14 PM PT)

Owner chose backlog item "Funding + fee capture (Recommended)" from `project_bot_backlog_2026-09-07.md`.
Preflight done 9/7 8:16–8:40 PM PT (3 research agents + 2 read-only Phemex probes).
Plan: `docs/superpowers/plans/2026-09-07-funding-fee-capture.md` (spec + diagnosis receipts inside).
Baseline: bot PID 78531 (since 9/3 9:31 PM PT), HEAD 4d4bcf7 (auto-backup 9/7 6:17 PM PT).

## Diagnosis (verified)
- funding_usdt = 0 on all 51 keyed 5m_MR rows; 12 live rows straddled a settlement. Main book: last nonzero funding 4/7 (one-shot CSV backfill).
- Phemex sign: funding amount positive = PAID, negative = RECEIVED (ETH short 9/4 5:00 PM PT, +rate → −0.00175251). Matches writer net = gross − fees − funding.
- fetch_my_trades interleaves funding rows (info.tradeType "4", action "13") with fills → must be filtered.
- `_save_state` dumps in-memory rows → reconciler patches reverted on next close; only re-applied inside 7-day window.
- Reconciler is main-book only; slot ledgers never reconciled; exchange_close sums last fill only; crumb closes charge the 0.07% estimate.

## Build
- [x] T0 Snapshot all trading_state*.json → reports/backup/2026-09-07-prefund/ (25 files, 8:33 PM PT); pre-PID commit for audit diff = b3d88ad (9/3 9:17 PM); baseline suite 484✓ then 1 pre-existing fail (test_mr_edge_screen::test_isolation_never_imports_live_bot_modules — passes alone, fails only in full-suite order because earlier tests import bot modules; order flake, unrelated)
- [x] T1+T2 Reconciler (helpers + ledger discovery + funding fetch + atomic per-file apply + `--lookback-days`) — commit 48a243d, 17 tests; LIVE under launchd from the 9:00 PM PT run; 100d dry-run receipts in reports/reconcile_backfill_dryrun_2026-09-07.txt (331 real rows / 5 ledgers; MR: 12 fee patches, 17 funding stamps (6 nonzero), 17 pre-7/25 rows unmatched — cause under audit)
- [x] Full suite after all four commits: 969 passed, 1 failed (same pre-existing order flake) — 8:51 PM PT
- [x] T3 RiskManager `_merge_reconciled` on save + tests — commit 36dceb8 8:35 PM PT; 4 new tests, 41✓ on adjacent set. Plan error caught: open_position never calls _save_state (only set_initial_balance/sync/close do); test triggers merge via a 2nd close instead.
- [x] T4 bot.py `_close_fills_summary` (all reduce fills, skip funding rows, VWAP) + crumb-close real fee + tests — commit 8d5db08 8:37 PM PT; 4 new tests, 40✓ adjacent; zero deviation
- [x] T5 daily_report funding line (Telegram + markdown) — commit 6f2e211; live at next scheduled run (display-only)
- [x] First LIVE launchd run of new reconciler 8:59 PM PT: 4 MR rows / 1 ledger, 2 fee patches (ETH 9/1 0.058→0.1015, XRP 9/4 0.088→0.1030), funding stamped ×4 (ETH 9/1 +0.002404, ETH 9/4 −0.001753), exit 0. Values match independent probe. NOTE: old bot code (PID 78531) reverts patches on its next MR save → job re-patches every 15 min + Telegram drift alert until restart (expected).
- [x] Audits (3 parallel, 8:49–9:00 PM PT):
  - Independent re-derivation: 11 sampled rows (fees + funding) match raw Phemex to printed precision; DOGE 8/8 "0.0009" is a real 19-DOGE crumb; Phemex fetch_my_trades history floor ≈ 40 days (earliest fill 7/29) → rows before ~7/29 can NEVER be backfilled from the API (kept as estimates, never patched).
  - Reconciler review: BLOCKER per-ledger claim sets (cross-ledger double count) + should-fix reversal fill theft + should-fix apply window clobbering `positions` → FIX AGENT DISPATCHED 8:57 PM. "partial" bucket = correct improvement (never patches a one-leg fee).
  - RiskManager/bot review: BLOCKER unlocked in-place dict mutation vs json.dump on the 2-thread main book → FIXED c1faefe (`_state_lock` RLock around merge+dump, spy test; 42✓). Crumb-close fee = one bounded extra API call on rare path, accepted + documented.
- [x] Reconciler audit fixes — commit 5279b8a 9:05 PM PT: global claim-once across ledgers (`reconcile_ledgers`), qty-capped side matching (`QTY_COVERED_FRAC` 0.999), stat-signature apply guard (inode+mtime_ns+size); 22 reconciler tests; v2 dry-run values identical to v1 (4 rows already applied by the 8:59 launchd run). Live under launchd from 9:05 PM.
- [x] Final full suite 9:10 PM PT: 975 passed, 1 failed (same pre-existing order flake)
- [x] T6 /pre-restart-audit 9:08–9:13 PM PT: steps 1-3 PASS (no numeric params changed in bot-loaded files; reconciler constants no lessons conflict; 4 files compile; Good-bot not running); step 4 review RESTART-SAFE (estimator floor, mark-price fallback, cancel_open_orders, cooldown, notify_exit, auto-demote, lock order, paper/live separation all intact). Restart diff vs PID 78531 code (b3d88ad): bot.py +118/−, risk_manager.py +78. → WAITING FOR OWNER "go"
- [ ] T7 (post-restart) 100-day `--apply` backfill + MR ledger verification + memory update
- [ ] T7 (post-restart) 100-day `--apply` backfill + MR ledger verification + memory update

- [ ] T7 (post-restart) 100-day `--apply` backfill — NOT RUN: bot never restarted; owner wound the system down 9/9 instead (see below).

## Review
Funding/fee capture: 5 commits (36dceb8, 8d5db08, 6f2e211, 48a243d, c1faefe, 5279b8a), 975✓ suite, 3 audits + 1 independent re-derivation, pre-restart audit RESTART-SAFE 9/7 9:13 PM PT. Reconciler went LIVE under launchd 9/7 8:59 PM PT and patched 4 MR rows with exchange-exact fees + funding. The bot-side commits were never loaded: owner did not say "go", and on 9/9 ordered the wind-down.

## Wind-down (owner order 9/9/2026 7:48 PM PT) — see docs/2026-09-09-winddown.md
- [x] GitHub snapshot tag `pre-winddown-2026-09-08` + branch (9/8 7:58 PM PT)
- [x] 5m_mean_revert demoted to paper (9/8 6:28 PM PT) — no live book
- [x] Market data archived: ~/Desktop/Phmex-S-archive/phmex-s-market-data-2026-09-09.tar.gz 1.97 GB, 470 entries, sha256 recorded (originals kept)
- [x] 22 launchd jobs booted out, plists → ~/Library/LaunchAgents/disabled/phmex-winddown-2026-09-09/ (no crontab / system daemons)
- [x] Bot PID 78531 stopped 7:50:28 PM PT after 0 positions / 0 open orders confirmed on Phemex; $87.12 idle
- [x] Nothing deleted; restore ≈10 min per the winddown doc
- [ ] Owner: copy the archive + repo to the external drive; decide on the $87
