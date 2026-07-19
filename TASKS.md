# TASK: htf_l2 PAPER slot + exit-geometry redesign (2026-07-18, Jonas: "paper slot it… make it 68% WR, winners > losers") — IN PROGRESS

Owner override noted: exit-geometry levers were closed for LIVE (7/6); this re-opens them for a
PAPER variant only. Target (68% WR AND avg win > avg loss) is a hypothesis to test in replay —
pre-register whatever the data actually supports. Main stays HALTED; real money untouched.

- [x] Agent A: implementation spec for HTF_L2_PAPER slot — DONE, all anchors verified. Key:
      slot needs explicit flow-passing branch (ST2.0 trap); per-slot SL/TP override must be
      built (minimal ext to StrategySlot + open_position, None=inherit); F5 gate reusable
      strategy-keyed; halt verified NOT to gate slots; snapshot conf=0 + missing htf_adx
      parity bugs to fix; 15 tests specced
- [ ] Agent B: MAE/MFE replay geometry sweep (full ledger + residual book ex thin∧ADX),
      Pareto set where avg win $ > avg loss $, explicit verdict on 68% target — RUNNING
- [x] Agent C (Jonas 7/18: "stop entering non-winning trades"): mine reconstructable
      indicator features (RSI/EMA/VWAP/ATR stretch — the F7 family, never historically
      recorded) vs winner/loser on the 215-trade ledger + residual book; placebo-guarded,
      multiple-testing-discounted; survivors → flag-controlled pre-registered slot filter
      spec. Known-null families excluded (L2 conf, tape, gates, time — receipts). DONE:
      NO deployable filter — all splits fail family-wise placebo (residual best p=0.617,
      conjunction p=0.127); one real finding (losers ~1 ATR more stretched past VWAP,
      Bonferroni-surviving) → pre-registered WATCH-ONLY on F7 telemetry at n≥30; entry-axis
      now fully exhausted. Orchestrator-verified vs artifacts. Memory:
      reference_htf_l2_entry_features_2026-07-18.md
- [ ] Synthesize: pick pre-registered geometry + kill criteria at fixed n; present to Jonas
- [x] Implement via TDD — DONE: slot registration (env-gated builder), flow-passing branch,
      ACTIVE thin∧ADX gate (gotAway reason thin_adx_paper_slot), ensemble conf<4 hard-block
      + counter, snapshot parity fix (real conf + htf_adx, ALL slots), F6 cell tags, per-slot
      sl_percent/tp_percent (None=inherit, regression-pinned), adjudicator REPORT-ONLY grader
      (kill lines OWNER-SET pending), dashboard box. Suite 530 passed / 0 failed, py_compile
      clean. Deviations logged in agent report.
- [x] Audit agent on diff — GO. Independent suite re-run 530/0; paper purity proven (static
      trace + tests whose exchange stub would AttributeError on any real order); live-path
      regression byte-identical (all pre-existing open_position callers keyword-only);
      F5 gate semantics parity confirmed; results[4] pinned by test; reporting propagation
      consistent w/ convention. 1 informational: .promote_HTF_L2_PAPER has no code-level
      refusal (matches existing promotable-slot architecture; promotion not authorized is
      comment-level) — surface at go-gate.
- [ ] Pre-restart audit → Jonas "go" → ONE restart → verify slot entries, telemetry, F7 fields
- [ ] Memory: new project file + MEMORY.md line; grade in lessons.md

---

# TASK: htf_l2 debug fix program (2026-07-17, Jonas: "fix those issues") — IN PROGRESS

Scope confirmed by owner: fix the issues found in the 3-round debug. Strategy fixes are
INERT while .halt_main_entries stands; un-halt remains Jonas's call. Full evidence:
reports/2026-07-17-htf-l2-action-plan.md + memory reference_htf_l2_diagnosis_2026-07-16.md.

Order (safety first, then strategy defects, one TDD cycle each, batch audited fixes → ONE restart):
- [x] F1 (LIVE MONEY): pause branch services slots before return + `_slot_entries_blocked()`
      helper on BOTH slot entry branches (paper gap closed) — 4 tests
- [x] F2: `cancel_entry_orders` (reduceOnly-safe) + one-shot pause-edge sweep, flag
      CANCEL_ENTRIES_ON_PAUSE=true, Telegram alert — 6 tests
- [x] F3: `_pending_cancel_sweep` registry + `sweep_pending_cancels()` per cycle beside
      reconcile; 24h TTL → Telegram; sweep never adopts — 8 tests
- [x] F4: Position.adopted/adopted_at set by sync_positions + orphan-adopt, wired through
      save/load + both closed-trade sites — 7 tests
- [x] F5: `_thin_adx_blocked()` conjunction gate (HTF_BLOCK_ADX_MIN=35, HTF_BLOCK_TAPE_MAX=20,
      HTF_THIN_ADX_BLOCK_ENABLED=true), gotAway reason "thin_adx", inert while halted — 6 tests
- [x] F6: ensemble blocks → gotAway("ensemble_confidence"); main-path pos.gate_tags written
      (sg_htf_adx_hi / sg_thin_tape / shadow axes; "none" when clean) — 3 tests
- [x] Full suite 505 passed, py_compile clean, __pycache__ cleared; all RED phases watched fail
- [x] Audit agent on total diff: clean on all 6 fixes + 3 findings (gate_tags not persisted,
      THIN-ADX invisible on dashboard label_map, TSM/Donchian paper paths pause-blind) —
      ALL 3 FIXED + tested (tests/test_audit_findings_0717.py, 4 tests; Donchian guard blocks
      only exposure INCREASES so de-risking still runs; helper hardened for early-startup)
- [x] Suite: 509 passed. py_compile clean. __pycache__ cleared.
- [x] Jonas "go" → restarted 7/17 5:18 PM PT PID 19587 → verified (sentinel honored, slots
      serviced, no errors); re-restarted 7/18 4:52 PM PT PID 5315 after reboot incident —
      F7 snapshot extension now live
NOT in scope (standing directives): exit-geometry changes, existing-gate removals (quiet_regime
stays), throttle redesign (deliberate cluster-risk design, PnL impact unquantified), un-halt.

---

# TASK: STATS line halt-proof fix (2026-07-16 evening) — COMPLETE ✅

Bug (confirmed by 4-agent debug): the every-10-cycles `=== STATS ===` log line
(risk_manager.py:900) is emitted at the END of `_run_cycle` (bot.py:2086), after
three early returns — regime pause (~1496), `_trading_paused` (~1511), and
`.halt_main_entries` (~1530). Since the 7/13 main-entries halt, zero STATS lines
printed → web_dashboard `_latest_balance` (:1143), trading_desk stats parser (:98),
scripts/daily_report.py (:144), and monitor_daemon all read balance $0 /
drawdown 0% or 100%.

Fix: extract the STATS block into `_maybe_print_stats()` and call it once, right
after `update_peak_balance(real_balance)` (~bot.py:1488), BEFORE all early
returns. Remove the old inline block at 2086-2097. Content is identical:
print_stats reads only closed_trades (finalized before the balance fetch) and the
passed-in real_balance. The 2026-04-26 API-failure guard (skip when available==0
with margin in use) is preserved verbatim.

## Plan
- [x] Preflight (lessons.md META-RULES, MEMORY.md) — done at session start
- [x] Root cause verified with file:line evidence (dashboard-debug agent)
- [x] RED: tests/test_stats_halt_visibility.py — 4 tests, all watched fail (AttributeError + ordering assert)
- [x] GREEN: `_maybe_print_stats` added (bot.py:2104), call moved to bot.py:1494, old block deleted
- [x] Full suite 467 passed (463 + 4 new) + py_compile clean + __pycache__ cleared
- [x] Review agent: PASS, zero findings ≥80; guard semantics, single call site, cadence all confirmed
- [x] Lessons crosscheck: no numeric params changed; no STATS/print_stats conflicts in memory
- [x] Restart on Jonas "go" — 9:00 PM PT, PID 83245, boot clean (3 paper positions
      restored, balance 41.90, sentinel honored)
- [x] FOLLOW-UP FIX (Jonas "fix it" 9:05 PM): web_dashboard `_latest_balance` regex
      only matched STATS `Balance:` — blind for <=10 cycles after every restart.
      Widened to `[Bb]alance:` so the boot line `Starting balance: X USDT`
      (bot.py:751) also counts; most-recent-wins. TDD: 2 red -> green, 15 dashboard
      tests pass. Dashboard-only restart (PID 86987, 9:06 PM PT); stdout now logs to
      ~/Library/Logs/Phmex-S/web_dashboard.log (was /dev/null). VERIFIED live:
      ticker BAL $41.90 / DD 9.6% at 9:07 PM PT.
- [x] Confirmed: first post-restart STATS line 9:13 PM PT WITH halt sentinel active
      (`=== STATS === ... Balance: 41.90 USDT | Drawdown: 9.6%`) — fix proven live;
      dashboard ticker matches ($41.90 / 9.6%)

## Review
- Diff: bot.py only (+ this file + new test file). reports/2026-07-16.md diff is the
  bot's own 8:22 PM report regeneration, not part of this change.
- Reviewer's minor note (~55 conf, immaterial): rare `min_margin_skip` close at
  bot.py:2001 now lands after the STATS print instead of before — consumers parse
  only the Balance field, so no impact on the fix target.

---

# TASK: Donchian Ensemble Slot build (2026-07-16) — DEPLOYED (paper) ✅
Restart 7/16 7:39 PM PT (PID 47206, Jonas go). Halt honored; 0 errors. DAY-ONE FIDELITY
PERFECT: paper book == pure-rule replica to 1e-8 (BTC w=0.2336 = $23.36 @ 1x, SL 0/no TP;
ETH w=0.2350). Both = legitimate 3-4/9 fast-lookback probes, vol-scaled. Known cosmetic:
generic entry log prints 10x/SL/TP pre-overwrite — final state verified correct.
Owner go: Jonas "build it". Spec: docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md
Evidence: reports/2026-07-16-wake-report.md §0.4 (OOS SIDESTEPPED verdict).

- [x] 1. `donchian_slot.py` (321 lines): frozen constants, pure math, atomic state, replica
      sidecars. GOLDEN FIDELITY: max |w_prod − w_replay| = 2.9e-15 over 518 days; incremental
      advance bit-exact vs batch fold.
- [x] 2. bot.py wiring: DONCHIAN_BTC/ETH paper slots + `_evaluate_donchian` in
      `_evaluate_all_slots` after TSM; per-coin isolation; live-order path REFUSES even if
      promoted (paper-only invariant in code).
- [x] 3. Tests: 30 new (golden micro-cases, rebalance rules, state roundtrip/idempotency/
      reseed, CSV regression anchors, wiring) — tests/test_donchian_slot.py.
- [x] 4. Reporting: dashboard + daily_report glob trading_state_* generically (verified
      static); sidecars deliberately non-trading_state-named (no phantom slots). Live-surface
      check after restart.
- [x] 5. Adversarial review: 9/9 PASS, zero issues ≥80. BONUS FINDING FIXED: pre-existing
      `.kill_*` handler sent real exchange orders for PAPER slots (could reduce a real
      overlapping position); now routes paper slots through _close_slot_position (paper book,
      WS-price/entry fallback) — +3 targeted tests (tests/test_kill_paper_slot.py).
      FULL SUITE: 463 passed. py_compile clean.
- [ ] 6. Jonas "go" → restart (rm -rf __pycache__) → verify first daily eval, replica
      agreement, [SLOT] lines, dashboards
- [x] Rollback: `.kill_DONCHIAN_*` now genuinely zero-market-risk (fix above) / revert commit

---

# TASK: Overnight research program (2026-07-13 10 PM → 7-14 ~1:30 AM PT) — COMPLETE

Goal: improve 5m_mean_revert trading + consistency. 11 agents (6 research, 2 web, 2 adversarial
verify, 1 review) + 1 follow-up test. Full results: reports/overnight-2026-07-14-morning-report.md

## Staged (inert until your go — nothing deployed)
- [x] V17 knob: strategies.py SHORT RSI threshold parameterized as MR_SHORT_RSI_MIN (default 70
      = today's behavior). Compile OK, 430/430 tests, review agent clean, verified CONFIRMED-
      WITH-CAVEATS (adversarial). TO ARM: add `MR_SHORT_RSI_MIN=65` to .env → /pre-restart-audit
      → restart. Expected ~$1-2/mo at current size (scaling-rights test, NOT a needle-mover).
      KILL CRITERIA: cohort = live MR shorts w/ entry RSI(7) in (65,70] (RSI is in signal reason);
      hard kill at cohort net ≤ −$5 or 3 consecutive cohort SL losers; review at 30 cohort fills
      (~2 mo, net<0 → revert); adjudicator CI at 60. REVERT: set 70 / remove line + restart.

## Adjudicated tonight — do NOT revisit (receipts in morning report)
- [x] Taker fills for MR: DEAD (maker +$7.83 vs taker −$24.22, 3/3 folds negative)
- [x] Loosening confluence/ADX/longs: DEAD; strength gate 0.80 INERT (emits ≥0.85)
- [x] Rest extension 60-300s + 2nd requote: DEAD (late fills toxic, monotonic decay; watchdog
      blocker; prior "misses were winners" partly a placement-price artifact — corrected)
- [x] OB-imbalance gate removal: REFUTED by verification (4/4-wins CI vacuous, p=0.0625,
      double-count in cohorts) — GATE STAYS; re-run gate_block_counterfactual.py at n≥10 (~6-8 wk)
- [x] H1 chase-vs-anchor requote: refuted on own data; H3 candle-turn: NULL/underpowered
      (passive re-check at 60-80 real trades); H2 depth + LimitIfTouched: parked (live-only A/B)
- [x] Amend-preserves-queue on Phemex: undocumented, assume NO
- [x] Symbol map: 1000PEPE only CI+ symbol; curated book fails most-recent fold — data only

## Jonas actions (morning)
- [ ] PT fee toggle (10% off maker+taker, confirmed official) — PT into futures wallet + flip
- [x] Decide: arm MR_SHORT_RSI_MIN=65 forward test? → **JONAS 7/15: DO NOT ARM, leave as is.**
      (2nd independent adversarial verify concurred: diff-CI straddles 0, double selection bias,
      most-recent fold breakeven, kill-gate ~4 mo away at ~8% live fills. Knob stays dormant @70.)
- [ ] Held from last night: min-margin $20 (needs TRADE_AMOUNT_USDT too + weekend cap literal
      bot.py:1830; MIN_TRADE_MARGIN alone only tightens crumb guard — see forensics in chat)

---

# TASK: Halt main-bot entries, keep 5m_mean_revert + ETH-TSM (2026-07-13)

## Why
Session audit (5 agents, cross-verified against state files): main bot is gross-negative
(gross WR 53.9% < 58.8% break-even) and never had a profitable month (lifetime ≈ −$110).
Owner directive: halt everything except the 5m_mean_revert live slot and the ETH-TSM paper
probe. Runtime check confirmed the ONLY real-money exposure is (a) the main bot scalper
(Config.STRATEGY=confluence → confluence_strategy wrapper → htf_l2_anticipation signals) and
(b) 5m_mean_revert (live). Everything else already paper (ST2.0/liq_cascade/narrow/ETH-TSM).

## Mechanism
`.pause_trading` is WRONG: its `return` at bot.py:1452 fires BEFORE the slot evaluators
(_evaluate_slots @2022, _evaluate_eth_tsm @2030), freezing slot software-exits. Instead add a
`.halt_main_entries` sentinel that skips only the main entry loop but still services slots +
their exits. Reversible: delete the file (no restart needed to toggle).

## Changes (bot.py)
- [ ] 1. Add helper `_evaluate_all_slots(self, prices)` wrapping the two existing slot-eval
      try/except blocks verbatim (same exception handling / log levels).
- [ ] 2. Replace the inline slot-eval block (~2020-2032) with `self._evaluate_all_slots(prices)`.
- [ ] 3. At the entry gate (after the `_trading_paused` return, ~1454), add:
      if `.halt_main_entries` exists → log once (+Telegram once), run `_evaluate_all_slots(prices)`,
      then `return`. Reset the one-shot log flag when the file is absent.

## Known tradeoff
While halted, the `[STATS]` log line (bot.py:2007) is skipped — identical to existing
regime-pause / daily-halt early-return windows, just longer. Dashboard reads trading_state.json
directly for balance, so this is cosmetic. Documented, accepted.

## Rollout
- [ ] py_compile check
- [ ] /pre-restart-audit (deploy review agent — real money)
- [ ] Create `.halt_main_entries`, then restart (rm -rf __pycache__)
- [ ] Verify in log: main/htf_l2 entries halted; 5m_mean_revert + ETH-TSM still evaluating; exits fire
- [ ] Update MEMORY.md

## Review — DONE 2026-07-13 9:15 PM PT
- Change made (3 edits): `.halt_main_entries` gate @entry (~1461), `_evaluate_all_slots` helper (~2079),
  inline slot block replaced with helper call (~2044). py_compile PASS.
- Pre-restart audit: independent code-reviewer, all 7 checks PASS, 0 issues ≥80% conf; confirmed all
  safety-critical reconcile/SL/orphan logic runs ABOVE the gate; `.pause_trading` slot-freeze defect avoided.
- Restart: sentinel created, __pycache__ cleared, PID 20653 killed, PID 7730 launched 9:14 PM.
  Halt logged active 9:15:49 PM. 0 open positions (WLD short stopped out −$2.17 at 9:11 PM pre-restart via
  its resting exchange SL). Slots serviced under halt CONFIRMED (Kelly-disable logs fire from inside
  `_evaluate_slots`). 5m_mean_revert LIVE/ACTIVE (not disabled); ETH-TSM PAPER/ACTIVE. No errors.
- Resume: `rm .halt_main_entries`. Memory: project_main_scalper_halt_2026-07-13.md + MEMORY.md updated.
