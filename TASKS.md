# TASKS — ST2.1pc paper-confirm variant (2026-06-16)

User APPROVED the paper-confirm proposal (st2-lab-paper-confirm-8df1250186dd) as a
PAPER variant (no real money). Forward-confirm config:
  hold_secs 1200 (20 cycles) + filters: cvd_slope<=-0.374, spread_pct>=0.039,
  buy_ratio<=0.85, trade_count>=24  (on top of base ST2.0 gate imb>=0.35/br>=0.60).

## Design (verified against code)
- New slot `ST2.1pc`, **strategy_name="ST2.0"** (inherits st2_absorption signal +
  flow-passing + OB/tape gate BYPASS, all keyed on strategy_name=="ST2.0"),
  paper_mode=True (bot.py:1871 gate → never places real orders), capital_pct=0.0,
  trade_amount_usdt=5.0 (mirror ST2.0 sizing for sim).
- Hold is a GLOBAL const (ST2_HOLD_CYCLES=15, bot.py:18) keyed on strategy_name.
  Add ST2_HOLD_CYCLES_BY_SLOT={"ST2.1pc":20}; hold branch uses per-slot lookup.
- No generic per-slot filter hook exists → add a hardcoded `if slot.slot_id=="ST2.1pc"`
  block after `direction` is computed (mirror the 5m_narrow precedent ~bot.py:1742),
  reading ob.spread_pct + flow.cvd_slope/buy_ratio/trade_count; bump_blocked+continue
  on fail. Plain Python (keep st2_lab isolated — don't import safe_exec).

## Steps
- [ ] bot.py: ST2_HOLD_CYCLES_BY_SLOT const + per-slot hold lookup in exit branch
- [ ] bot.py: append ST2.1pc StrategySlot to self.slots (paper)
- [ ] bot.py: ST2.1pc entry-filter block (cvd/spread/br/tc) near the slot entry path
- [ ] web_dashboard.py: add ST2.1pc to _SIGNAL_BOXES (propagation rule)
- [ ] /pre-restart-audit (MANDATORY before restart)
- [ ] restart via audited path; verify ST2.1pc shows PAPER + logs [PAPER] entries
- [ ] forward-confirm >= 30 real(paper) trades, watch spread_pct filter for artifact

## Guardrails
- paper_mode only — ZERO real-money risk. Do NOT create a _mode sidecar for it
  (would risk flipping live). Live ST2.0 slot UNCHANGED. Other slots UNCHANGED.
- spread_pct>=0.039 is artifact-suspect (wide spread → worse real fills); watch it.
