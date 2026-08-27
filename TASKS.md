# TASKS — Main book → PAPER (owner order 8/26 7:26 PM PT)

Owner order: "put the main book on paper" + "make sure this reflects on the dashboard".
Preflight done (lessons.md + MEMORY.md + code map, 2 agents, 8/26 7:31 PM PT). Finding: no existing
main-paper mechanism — main is live-by-filename (risk_manager.py:304), dashboard hardcodes main LIVE
(web_dashboard.py:548). Build required.

## Interim safety (DONE)
- [x] `touch .halt_main_entries` 8/26 7:32 PM PT — main entries blocked instantly, no restart, 0 open positions at cut.

## Conventions (all agents follow these)
- Sentinel: `.paper_main` in repo root, checked fresh via `_main_paper()` helper next to `_longs_blocked` (bot.py:75).
- Paper positions tagged `"paper": true` in the position dict at open; exits/reconciler/trail branch on the
  POSITION's tag, not the live sentinel (no mixed-state if sentinel toggles mid-position).
- Closed rows tagged `mode="paper"`. Main's RiskManager `is_paper` stays False (no gross→net ledger flip mid-file,
  risk_manager.py:745). Historical main rows have NO mode field = real money; new paper rows have mode="paper".
- Paper fills use `_fresh_paper_entry_price` (as slots do, bot.py:3275). Simulated SL/TP mirror bot.py:4832-4844.

## Build (parallel agents)
- [x] A1 bot.py DONE 8/26 7:55 PM PT: _main_paper() + paper entry branch (all gates identical, zero exchange
      calls); all 7 exit sites + watcher + trail + SL-verify + startup place_sl_tp + partial-TP branch on
      POSITION tag; sim SL/TP rides existing software-exit loop (sim trailing free); reconciler excludes tagged
      positions (phantom-close tested); daily-loss halt + Kelly + STATS exclude mode=="paper".
      DEVIATION (justified): risk_manager.py edited — Position.paper persisted across restart (else restart
      strips tag → real SL/TP placed for phantom), partial_close mode=, Kelly/STATS filters. 25 new tests.
      FULL SUITE: 798 passed, 0 failed.
- [x] A2 web_dashboard.py DONE 8/26 7:45 PM PT: _main_paper() + _split_main_rows() (split by row's OWN mode,
      never sentinel); PAPER badge both main cards (coexists w/ HALTED + SHORTS-ONLY); no-mode rows never pass
      honest filter (8/12 leak class regression-tested both sentinel states); paper stats on separate "paper (sim)"
      row; equity/ticker/blotter/positions paper-aware. 17 new tests; 100 passed 0 failed across dashboard modules.
      Note: blotter strategy-chip WRs already blend live+paper by design (pre-existing) — flag to owner.
- [x] A3 adjudicator + reports DONE 8/26 7:44 PM PT: _real_rows() filter on all registered lines incl. side lines
      + trail_arm + sizing; tripwire unreachable from sims (tested to sim −$12); digest PAPER banner; daily_report
      real/paper split + Telegram paper line. 77 passed on owned modules (15 new) + 17 adjacent. Full suite deferred
      to post-build gate.
- [x] A4 mode-blind consumers DONE 8/26 7:51 PM PT: 10 scripts fixed w/ uniform `mode != "paper"` predicate —
      overwatch (4 checks + position-desync phantom-alarm the sweep missed), telegram /status "+n paper sim",
      reconcile_phemex/backfill_fees structurally can't touch sim rows, strategy_tracker (old-vs-new identical
      −$126.10/14 files), weekly_forensics, auto_lifecycle, symbol_pnl_audit, postentry_drift, sprint_checkpoint.
      16 new tests; 36 passed 0 failed. Zero mode="paper" rows exist today → all filters verified no-op.
      DEPENDENCY: overwatch desync check needs open paper positions tagged "paper": true (A1 convention).
- [ ] NOTE: real 1000PEPE short opened 7:32:24 PM PT (same minute as halt, boundary trade) — last real main trade;
      untagged → follows real close path by design; main flat once it closes.
- [ ] A1 addendum (sent 7:45 PM PT): bot-side daily-loss halt / era loss cap / DD / Kelly sums must exclude
      mode=="paper" rows; paper rows well-formed for reconcile matching.

## After build
- [x] Cross-audit DONE 8/26 8:11 PM PT: PASS-WITH-NOTES. No real-order leaks (all ~58 exchange call sites traced,
      2 independent traces); 1000PEPE untagged → real path proven incl. restart round-trip; authoritative full
      suite 772 passed 0 failed (A1's 798 was mid-build snapshot). Restart safe with halt armed; halt REMOVAL
      gated on HIGH fixes below.
- [ ] A5 HIGH fixes (dispatched 8:12 PM PT): mcp_server.py 4 tools mode-blind (status/pnl/recent_trades/
      open_positions blend paper into real answers); monitor_daemon.py paper-blind (log marker missing on paper
      main closes — bot.py _close_paper_main gets [PAPER] log line — + state-read hardening).
- [ ] A6 MEDIUM fixes (dispatched 8:12 PM PT): recalibration.py (feeds kill_switch_check!), scanner.py dead
      is_paper filter, chart/dashboard/trading_desk/war_room/daily_review, code_health entry-health paper-aware.
- [ ] A7 test hardening (dispatched 8:12 PM PT): behavioral mock tests for 8 textually-verified guards; holistic
      no-sentinel regression; mode-homogeneous partial-TP group test in adjudicator.
- [ ] Full suite green after A5-A7
- [ ] /pre-restart-audit → present checklist → **Jonas says "go"** → restart → verify new PID + paper entry in log
- [ ] `touch .paper_main` before restart (sentinel present at boot); `.halt_main_entries` stays until paper mode
      verified live, then rm (ask Jonas to run rm if permission classifier blocks)
- [ ] memory-sync: record demotion + new sentinel in MEMORY.md / lessons

## Notes / surfaced per META-RULE
- Main book was RUNNING WELL at demotion: this week 18 trades +$5.28, 83.3% WR (phmex_pnl 8/26); owner's call.
- Owner directive "no shadow, live deploy" (feedback_no_shadow_live_deploy.md) superseded for main book by this order.
- "Sum all state files" PnL convention: main paper rows now live in trading_state.json tagged mode="paper" —
  lifetime real-PnL sums must exclude them (A3 checks consumers).
