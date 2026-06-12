# Live Exit Watcher (Tier 2) — Design Spec

- **Date:** 2026-06-11 (evening) · **Requested by:** Jonas ("I wanted the 60-second
  snapshot to be live")
- **Touches real money: YES** — new thread that can close live positions.
  /pre-restart-audit + flat window required.

## 1. Problem
All software exits (trailing stop, software SL/TP, early/flat/adverse/time) are
evaluated once per 60s cycle. Price can blow through a level seconds after a check
and the bot reacts up to ~59s late. The measured damage lives on the loss side
($0.92 avg loss vs $0.49 avg win; 30-60min holds bleed −$7.16/60d). The durable
exchange trail (deployed 6/11 AM) covers the disaster tail; this covers everything
between normal exit and disaster.

## 2. Design — enforcement goes live, dynamics stay identical
A daemon thread (`_live_exit_watcher_loop`, ~1s interval) checks each open live
position's CURRENT exit levels against the live WS price and closes the moment a
level breaks.

**Critical semantic decision:** the watcher only ENFORCES levels — it does NOT
ratchet them. `check_breakeven` / `update_trailing_stop` / durable-SL moves stay on
the 60s cycle. Rationale: ratcheting the trail at 1Hz would tighten effective trail
dynamics (more wick sensitivity) — exactly the outcome-changing behavior the Part B
evidence-first plan said needs shadow data first. Same levels as today, faster
trigger. The shadow-logger keeps measuring the tightening question separately.

## 3. Mechanics
- `ws_feed.last_price(symbol) -> (price, age_s)` — new O(1) accessor reading the
  forming-candle close under the existing lock.
- Watcher loop per open position:
  1. Skip if WS price age > 10s (stale feed → cycle remains the authority; never
     exit on stale data).
  2. Claim the symbol in a `_closing` set under `_pos_lock` (skip if already
     claimed or gone) — the 60s cycle's exit blocks check the same set, so a
     position can only be closed by one path. Claims released in `finally`.
  3. Classification reuse: call `risk.check_positions({sym: price})` for the one
     symbol — identical exit reasons (trailing_stop/stop_loss/take_profit) by
     construction, zero new classification code (regression guard lessons.md:306).
  4. Close via the same sequence as the cycle (close order → fill extract →
     cooldown → close_position → cancel_open_orders → notify), logged `[LIVE EXIT]`.
- Cycle changes: exit blocks + durable-SL block honor the `_closing` claim set
  (skip claimed symbols). No other cycle behavior changes.
- Indicator/time-based exits (early_exit, flat, time, trend-flip) STAY on the 60s
  cycle — they need DataFrames/cycle counts, and they are not price-level breaches.
- Adverse exit is price-based but currently disabled live (−999); the watcher
  honors the same config so it is a no-op until that changes.

## 4. Config / rollback
- `LIVE_EXIT_WATCHER` (.env, default **true** per Jonas's explicit request) —
  false reverts to pure 60s behavior without code rollback.
- Watcher never opens positions, never places/moves SL/TP, never touches paper
  slots. Close orders only, reduceOnly via existing close_long/close_short.

## 5. Failure modes addressed
- Double-close: `_closing` claims + reduceOnly + positions-dict check under lock.
- Stale WS: 10s age guard; cycle remains backstop authority.
- Watcher crash: wrapped loop; logs `[LIVE EXIT] watcher died` + Telegram alert,
  cycle exits continue unaffected (watcher is additive only).
- Exchange call latency inside the watcher: claims released on completion; cycle
  skips claimed symbols instead of blocking.

## 6. Tests (mocked, no network)
breach→close fires once; cycle skips claimed symbol; stale price → no action;
trailing/SL/TP reasons classify identically to cycle path; watcher disabled flag
→ zero effect; close failure → claim released, position intact, alert logged.

## 7. Propagation
No new exit reasons (reuses check_positions classification) → notifier/report/
dashboard flow unchanged. New log tag `[LIVE EXIT]` only.
