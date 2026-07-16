# TASK: Donchian Ensemble Slot build (2026-07-16) — IN PROGRESS
Owner go: Jonas "build it". Spec: docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md
Evidence: reports/2026-07-16-wake-report.md §0.4 (OOS SIDESTEPPED verdict).

- [ ] 1. `donchian_slot.py` module (frozen constants, pure signal math, atomic state, replica sidecars)
- [ ] 2. bot.py wiring: 2 paper slots (DONCHIAN_BTC/ETH) + `_evaluate_donchian(prices)` called
      from `_evaluate_all_slots` (after `_evaluate_eth_tsm`), TSM-pattern rails opt-out
- [ ] 3. Unit tests (signal math golden cases from the validated replay; state roundtrip;
      day-roll trigger; whitelist-legal fetch)
- [ ] 4. Reporting propagation verified: [SLOT] lines, daily_report, notifier, dashboard
- [ ] 5. Full suite green + independent code review + /pre-restart-audit
- [ ] 6. Jonas "go" → restart → verify first daily eval, replica agreement, dashboards
- [ ] Rollback: `.kill_DONCHIAN_*` / revert (paper-only, zero market risk)

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
