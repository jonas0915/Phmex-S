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
- [x] A5 HIGH fixes DONE 8/26 8:22 PM PT: mcp_server 4 tools real-only + paper_* fields (shapes back-compat);
      monitor_daemon dual-layer paper exclusion (log marker + state-row match) + real-margin drawdown sum;
      bot.py _close_paper_main logs "[PAPER] Position closed:" via _log_prefix swap (slot mechanism reused).
      21 new tests; full suite 793 passed 0 failed (=772 + exactly the 21 new).
- [x] A6 MEDIUM fixes DONE 8/26 8:21 PM PT: 8 files (recalibration loader-level fix — auto_lifecycle feeds it
      slot files only, contamination path was CLI/COMBINED; scanner dead is_paper→mode; chart/dashboard/
      trading_desk/war_room/daily_review; code_health real-vs-paper entry recency). 26 new tests; full suite
      841 passed 0 failed. BONUS LIVE BUG FIXED: daily_review counted paper-SLOT [PAPER] log lines as real
      trades (today showed 8, truth 5) — pre-existing, now filtered.
- [x] A7 test hardening DONE 8/26 8:21 PM PT: 22 behavioral tests (paper never reaches exchange + live mirrors
      non-vacuous; holistic no-sentinel regression w/ sentinel-consult spy at 0; resize15 mode-homogeneity —
      leaked mixed group drops entirely, conservative). No production bugs found.
- [x] Full suite after A5-A7: 841 passed, 0 failed
- [x] /pre-restart-audit PASSED 8/26 8:35 PM PT (review found 1 race in _log_prefix swap → fixed via per-call
      log_prefix param, suite 841 green) → Jonas "go" 8:42 PM → `.paper_main` touched 8:42 → restart: old 1181
      killed, NEW PID 99187, cycle #21171 8:44 PM, halt honored, no errors → `.halt_main_entries` REMOVED 8:46 PM.
      MAIN BOOK NOW PAPER (shorts-only via .block_longs_main). Last real main trade: 1000PEPE short closed
      8:19 PM trailing_stop +$0.64 (pre-restart, book flat at cutover).
- [ ] memory-sync: record demotion + new sentinel in MEMORY.md / lessons (in progress)

## Notes / surfaced per META-RULE
- Main book was RUNNING WELL at demotion: this week 18 trades +$5.28, 83.3% WR (phmex_pnl 8/26); owner's call.
- Owner directive "no shadow, live deploy" (feedback_no_shadow_live_deploy.md) superseded for main book by this order.
- "Sum all state files" PnL convention: main paper rows now live in trading_state.json tagged mode="paper" —
  lifetime real-PnL sums must exclude them (A3 checks consumers).

# TASKS — Regime-pause slot freeze fix (owner order 9/3 9:22 PM PT)
- [x] Bug verified (4-agent deep dive + adversarial check): regime `return` skipped _evaluate_all_slots; fed by paper main since 8/26
- [x] TDD: tests/test_regime_pause_slot_service.py RED → bot.py regime branch calls _evaluate_all_slots(prices) → GREEN; suite 843✓
- [x] /pre-restart-audit: compile OK, no params changed, review PASS, Good-bot off
- [x] Jonas "go" 9:30 PM → PID 1444 killed, NEW PID 78531 9:31 PM PT, 0 open positions at cutover
## Review
One-line production change mirroring two existing branches. Behavior: slots (entries + exits + ratchet) run during a
main-book regime pause; main entries still pause. Paper main closes still feed the main regime window (affects paper only).

# TASKS — 5m_mean_revert edge search (owner order 9/3 9:37 PM PT; plan approved 9:51 PM PT)
Plan: ~/.claude/plans/hidden-conjuring-kazoo.md. Prereg: docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md (frozen 9:55 PM).
- [x] Preflight: research ledger (30 dead levers) + data/tooling inventory (2 agents)
- [x] Universe frozen: 35 symbols → reports/mr_edge_2026/universe.json
- [x] Prereg doc written BEFORE any read
- [x] A: scripts/slot_lab/mr_edge_fetch.py DONE (21 tests; 1000PEPE June parity 100%)
- [ ] A-run: fetch PID 92534 9:57 PM → DIED 10:58 PM at symbol 21/35 (parent agent killed by usage limit); 20 syms cached, June parity 14/14 = 100%, 0 gaps>2; early-END series (delist/thin): ALLO 8/11, BICO 6/30, DEXE 7/31, EIGEN 8/7, GIGGLE 8/7, INJ 8/18. RESUMED 1:02 AM 9/4 PID 9875 detached (nohup, nice 19) for remaining 15
- [x] C: scripts/slot_lab/mr_edge_signal_table.py DONE 10:15 PM (31 tests; parity with validated rig to 1e-16)
- [ ] C2: FIDELITY FAILED 2/5 on closed bars — live fires on the FORMING candle. Prereg AMENDMENT v2 10:20 PM: forming-bar regen (fire_minute, confirmed_at_close) + family H6 entry-timing (+3 trials → 113) + real-money confirmed-vs-forming read. screen H6 DONE 10:24 PM (26 tests, 113 trials); signal-table forming-bar regen in progress
- [x] D: scripts/slot_lab/mr_edge_screen.py DONE 10:05 PM (23 tests; 110 trials = 79+3+3+3+22; holdout guard: train_results + prereg sha + per-family lock)
- [x] H0 sink: scripts/slot_lab/mr_gate_block_archiver.py (5 tests) + launchd com.phmex.mr-gate-archiver (6h, nice 19) DEPLOYED 10:02 PM; 13 blocks archived (4 OB)
- [ ] Train read → holdout read (one per family) → verification agent re-derives → report
- [ ] E (only if survivor): adjudicator line + live ship via TDD + /pre-restart-audit + go
