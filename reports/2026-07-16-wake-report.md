# Wake Report — Thursday 2026-07-16 (compiled ~6:30 AM PT)
**STATUS: SKELETON — overnight sections fill in at compile time.**

## 1. Bot right now
⏳ (status, balance, open positions, uptime at compile)

## 2. Overnight 7/15→16 (~8 PM → 6:30 AM PT)
⏳ (monitor events, MR signals/fills, TSM eval, errors)

## 3. Interim recap 7/14–7/15 (verified from state files)
- Main bot: **0 trades since the 7/13 9:14 PM halt** — halt integrity confirmed (~2 days).
- 5m_mean_revert: 1 trade — XLM long hard_time_exit **−$0.87** (7/14 10:11 PM PT);
  1 PostOnly miss (ARB short 7/15, RSI 74.6); 1 tape-gate block (BTC long). Normal cadence.
- ETH-TSM (paper): holding ETH long, round trip #2 in progress; 7/15 eval: ret28 +9.5%
  vs thr +5.6% — signal firmly ON.
- Errors 48h: 3 transient (1 watchdog cycle-timeout, 2 Phemex API blips) — self-recovered.

## 4. Standing decisions
- **PT fee toggle — still open, your action.** 10% off maker+taker (officially confirmed);
  PT must sit in the FUTURES wallet, then flip in Account Overview → Fee Level.
- **V17 (MR_SHORT_RSI_MIN): DORMANT at 70 per your 7/15 call.** Knob staged, kill criteria on
  file; arm later = one .env line + audited restart. No pressure — replay says ~$1-2/mo.
- **Min-margin $20: HELD.** If wanted: change TRADE_AMOUNT_USDT=20 + MIN_TRADE_MARGIN=20 +
  weekend cap literal (bot.py:1830 `min(margin*1.3, 15.0)`), then audit + restart.
  MIN_TRADE_MARGIN alone only tightens the crumb guard (fires MORE min_margin_skips).
- **Main scalper: stays halted** (resume = `rm .halt_main_entries`, no restart needed).

## 5. Watch calendar (nothing due today)
- **OB-imbalance gate re-adjudication:** re-run scripts/slot_lab/gate_block_counterfactual.py
  when imbalance blocks reach n≥10 (~late Aug at current rate). Bar: mixed-sign CI or ≥9/10.
- **H3 candle-turn re-check:** at 60-80 real MR closed trades (currently 26).
- **~7/21 adjudicator digest will flash a false 1-day ETH-TSM "REVERT"** — entry-day artifact,
  ignore. ETH-TSM promotion needs ≥1 full round trip + adjudicator grading.
- **Drift-gate grading: FROZEN while main is halted** — the 2-week grading plan (from 7/12)
  assumed htf_l2 kept trading; with main entries halted no new gate data accrues. If main
  stays halted, the bench-htf_l2 decision is effectively made by the halt itself.
- ETH-TSM kill criteria: adjudicator-tracked (net ≤ −$10, 2 disaster stops, tracking err).

## 6. Where the program stands (one paragraph)
The 7/13-14 overnight program closed every cheap lever on 5m_mean_revert with receipts
(reports/overnight-2026-07-14-morning-report.md), staged the one defensible knob (you chose
dormant), and left the bot in capital-preservation posture: main scalper halted, MR slot live
at its natural ~2.6-signals/day cadence, ETH-TSM paper probe running. The honest path to
meaningful P&L remains structural (memory/project_main_scalper_halt_2026-07-13.md), and the
highest-EV click available today is still the PT fee toggle.
