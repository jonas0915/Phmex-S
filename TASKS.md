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
