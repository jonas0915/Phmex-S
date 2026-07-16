# Donchian Ensemble Slot (BTC + ETH) — Design Spec
2026-07-16. Owner go: Jonas ("build it"). Paper-first, promote-by-sentinel.

## Why (evidence)
Concretum/SSRN 5209907 (net-of-10bps BTC CAGR 30%, Sharpe 1.56, MDD 19%; ETH 27%/1.51/15%,
2015–2025.03) + our own OOS replay through the bear the paper never saw (Aug 2025→Jul 2026):
BTC −11.5% vs −44.0% B&H (MDD −15.1 vs −53), ETH −4.9% vs −48.0% (MDD −13.9 vs −67.6);
9/9 long at Oct top, flat Nov 13-14, robust ±1 lookback step and 20bps. Receipts:
reports/2026-07-16-wake-report.md §0.4; replay scripts preserved (scratchpad donchian_ensemble.py).
Distinct from killed family members: NOT the 28d single-tercile rule (BTC kill test 7/15),
NOT the 12-coin basket TSM (7/13 kill) — 9-lookback ensemble + ratcheting stops + vol target,
BTC/ETH only (our own data: the trend signal lives in the majors; dilution is what failed).

## Strategy rules (FROZEN — fidelity to the validated replay; no tuning without new replay)
Per coin (BTC/USDT:USDT, ETH/USDT:USDT), daily bars (UTC close), close-only:
- 9 sub-models, Donchian lookbacks N ∈ {5,10,20,30,60,90,150,250,360} on CLOSES.
- Sub-model entry: today's close == max(close, last N) → long.
- Sub-model exit: close <= trailing stop; stop = Donchian midline (mean of N-day
  close-high and N-day close-low) at entry, ratcheted daily to max(prev stop, midline) —
  never down.
- Combo weight w = mean(9 sub-model positions ∈ {0,1}) × vol_scalar;
  vol_scalar = min(0.25 / σ_90d, 2.0), σ = annualized (√365) std of last 90 daily simple returns.
- Rebalance: on any sub-model flip immediately; on vol-only drift when |Δw| > 0.20·w.
- Long/flat only. No shorts. No leverage in paper (notional = base × w).

## Architecture (mirrors tsm_slot.py / _evaluate_eth_tsm — proven pattern)
- New module `donchian_slot.py`: frozen constants, signal math (pure functions), per-coin
  state (sub-model stops, entry flags, w) persisted atomically to
  `donchian_slot_state.json`; pure-rule replica series for fidelity tracking
  (`donchian_signal_{BTC,ETH}.json`, like eth_tsm_28_signal.json).
- Two StrategySlots: `DONCHIAN_BTC`, `DONCHIAN_ETH`; paper_mode=True;
  strategy_name NOT in STRATEGIES (same trick as ETH-TSM: _evaluate_slots skips entirely;
  all logic in a dedicated `_evaluate_donchian(prices)` called from _evaluate_all_slots).
  Rails opt-out identical to TSM (loss_cap −999, kelly_min_trades 10**9, no durable trail —
  the ratcheting Donchian stop IS the exit; close-only, software-evaluated in paper).
- Data: daily OHLCV via existing fetch path, limit=500 (whitelist-legal; need 360+90=450).
  Completed candles only; evaluate once per UTC day roll (same trigger as TSM).
- Paper sizing: base notional $100/coin × w (paper — no halt-math interaction). Fees via
  existing paper fee model (MAKER_FEE_PERCENT path); record positions/trades through the
  slot RiskManager like other paper slots (persist open positions — Mar 26 lesson).
- Promote path: `.promote_DONCHIAN_BTC` / `.promote_DONCHIAN_ETH` sentinels (existing
  mechanism). Live sizing decided AT promotion (needs funding; not in this build).

## Kill criteria (pre-registered, adjudicator-graded)
- Fidelity: daily |bot w − replica w| > 0.10 on >3 days in 14d → BUG, fix or kill.
- Paper net ≤ −$15 on $100-base (≈ −15% = beyond replay MDD) → kill.
- 90-day review: tracking error, trade count vs replay cadence (~65-70 adj/yr), net vs
  same-period pure-rule replica.

## Reporting (CLAUDE.md propagation rule — mandatory)
- [SLOT] status lines (existing loop) pick the new slots up automatically; verify.
- daily_report.py + notifier: slots appear in the Live Slot/paper sections; verify or extend.
- web_dashboard: slot rows render for new slot ids; verify or extend.

## Non-goals (v1)
No live orders, no shorting, no other coins, no parameter tuning, no intraday stops.

## Rollout
Implement → tests (green suite) → independent code review → pre-restart audit →
Jonas "go" → restart → verify first daily eval + [SLOT] lines + dashboards.
Rollback: `.kill_DONCHIAN_*` sentinels or revert commit (paper-only, zero market risk).
