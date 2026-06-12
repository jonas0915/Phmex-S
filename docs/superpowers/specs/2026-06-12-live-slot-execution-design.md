# Live Slot Execution — Guarded Promotion of 5m_mean_revert

**Date:** 2026-06-12
**Status:** Approved by Jonas ("ship it", ~1 AM PT 2026-06-12)
**Decision context:** Jonas chose "Promote now, guarded" over waiting for the 50-trade
paper bar. Claude's recommendation to wait was overridden — recorded per process.

## Why

5m_mean_revert is the only positive slot on the board: 19 paper trades, 52.6% WR,
+$3.95 (bot.log slot summary, 2026-06-11 11:52 PM PT). Sample is statistically
unverified (95% CI on WR roughly 29–76%); Jonas accepts that risk in exchange for
hard guardrails. All trend slots are negative or killed; live strategy has no edge
(592 trades, −$60.51 lifetime).

## Discovery that forced this build

The `.promote_<slot>` sentinel (bot.py:547-565) only flips `slot.paper_mode = False`.
The paper evaluator skips non-paper slots (bot.py:1533) and the only real-order call
is the main loop's (bot.py:1370). Promoting today would take the slot DARK: no live
orders, no paper data. Live slot execution does not exist and must be built.

## Decisions (Jonas, 2026-06-12)

1. **Mirror the paper path** — live entries use exactly the slot evaluation path the
   19-trade record came from: signal → strength ≥ 0.80 → slot capacity/conflict →
   OB gate → tape gate (incl. bb_mean_reversion CVD carve-out, bot.py:1761).
   NO main-pipeline ensemble/time-block/global-cooldown gates.
2. **PostOnly limit entries, skip on miss** — maker fees, no chasing. Accepted
   trade-off: live will slightly under-trade paper.
3. **Guardrails:** $10 margin (Config.TRADE_AMOUNT_USDT), max_positions=1 (existing
   slot config), auto-demote on live net PnL ≤ −$5.00 OR live-only Kelly < 0 after
   ≥ 10 live trades.

## Architecture (Approach A — mode-aware slot evaluator)

Rejected alternatives: (B) route bb_mean_reversion into main pipeline — main gates
would apply, contradicts decision 1, results incomparable with paper record;
(C) separate process — shared API key conflict history, zombie risk.

### Components

**1. Promotion (existing, small additions)**
- Sentinel `.promote_5m_mean_revert` already flips paper_mode at runtime (no restart).
- ADD: `slot.promoted_at` timestamp persisted to the slot state file; live-only
  accounting anchors here. Telegram notification exists.

**2. Live entry execution** — in the slot evaluator (rename `_evaluate_paper_slots`
→ `_evaluate_slots`; paper branch unchanged):
- Same path through signal/strength/can_enter/conflict/OB gate/tape gate.
- Live branch replaces `slot.risk.open_position(signal_price)` with:
  a. `exchange._try_limit_entry(symbol, side, amount, price)` — PostOnly, skip on
     miss (existing FILL MISS semantics, filled>0-on-canceled fix applies).
  b. Real entry price from `fetch_positions()` (never order response — lessons.md).
  c. Place exchange SL/TP (same RiskManager math as paper used: Config SL/TP + ATR).
  d. `slot.risk.open_position(real_fill, ...)` + entry snapshot + gate shadow-tags.
  e. Trade record tagged `mode: "live"` at close time.
- Account drawdown halt and `.pause_trading` apply to slot live entries.

**3. Live exit execution**
- Exchange-resting SL/TP = hard backstop (protection present even if bot dies).
- SL/TP enforcement = the exchange-resting orders; their fills are detected and
  recorded by reconcile Path A (component 4). The cycle does NOT software-close on
  SL/TP touch (would race the exchange order → double-close).
- Per-cycle (60s): adverse_exit and time_exit only — executed as REAL closes via
  `exchange.close_long/close_short`, then cancel the resting SL/TP; real fill price
  + fees recorded. NO trailing/breakeven in v1 (paper record had none).
- Live-exit watcher (1s) stays main-bot-only in v1. Follow-up after it is proven.

**4. Reconcile ownership (critical fix)**
- Sync Path A (close detection) and Path B (orphan adoption) currently see only
  `self.risk.positions` (bot.py:2203-2259). Path B would mis-adopt a live slot
  position into main tracking → double management.
- Fix: tracked set = main positions ∪ live-slot positions. Path A close-detection
  runs per owner (slot closes recorded into slot.risk with real fill + fees, tagged
  `exchange_close`). Path B adopts only symbols in neither tracker.
- Highest-risk integration point — gets dedicated tests.

**5. Guardrails / auto-demote**
- Live-only accounting: `live_pnl` = Σ net pnl of `mode=="live"` trades closed since
  `promoted_at`. Paper history never counts.
- After EVERY live close, check: live_pnl ≤ −$5.00 → demote; live trade count ≥ 10
  AND live-only Kelly < 0 → demote.
- Demote (auto or `.demote_` sentinel): close open slot position at market, cancel
  its orders, `paper_mode = True`, Telegram alert. Never freeze a position
  (killed-slot DOGE freeze lesson, audit 2026-06-11).

**6. Reporting (CLAUDE.md propagation rule)**
- web_dashboard.py `_LIVE_SLOTS` (currently hardcoded `{"5m_scalp"}`,
  web_dashboard.py:980) becomes dynamic from slot.paper_mode.
- Slot live trades use real notify_entry/notify_exit (not notify_paper_*), labeled
  with slot_id.
- scripts/daily_report.py gains a live-slot section (trades/WR/PnL since promotion).

## Testing

- Unit: demote trigger math (−$5 cap, Kelly-after-10, paper history excluded),
  reconcile ownership (slot position NOT adopted; slot exchange-close recorded to
  slot.risk), mode tagging, entry-path parity (live branch hits same gates as paper).
- py_compile all touched files; full test suite green.
- `/pre-restart-audit` before deploy. Deploy on next flat window AFTER the live-exit
  watcher (deployed 2026-06-11 11:55 PM PT) has handled ≥ 2 real exits — one live
  change at a time.

## Rollback

`touch .demote_5m_mean_revert` — runtime, no restart, closes position, back to paper.
Code rollback: feature is additive to the slot evaluator; revert commit restores
paper-only behavior.

## Success / failure criteria

- Success: live slot reaches 50 combined trades with live-only Kelly > 0 → promotion
  confirmed, consider capital_pct increase.
- Failure: either auto-demote fires → back to paper, count it as the forward test
  answering honestly.
