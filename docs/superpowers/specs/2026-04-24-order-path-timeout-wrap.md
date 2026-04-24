---
title: Wrap exchange.py order-path calls in _call_with_timeout
status: QUEUED — execute at next no-position restart window
created: 2026-04-23
author: session handoff
---

# Order-path timeout wrapping (Item 9 from 2026-04-23 DNS+overwatch fix session)

## Why

The 2026-04-10 loop-freeze fix wrapped 9 REST reads (fetch_balance, fetch_ohlcv,
fetch_order_book, fetch_trades x2, fetch_funding_rate, fetch_ticker,
fetch_positions) in `_call_with_timeout` at [exchange.py:47](exchange.py#L47),
each capped at 15s. It left 20 order-path calls relying solely on
`socket.setdefaulttimeout(10)` ([main.py:60](main.py#L60)) and ccxt's internal
timeout.

During the 2026-04-23 DNS bursts (2,369 errors across 62 minutes, VPN resolver
100.64.100.1 blinking intermittently), order-path calls could stall up to the
10-s socket ceiling with no retry. This affects: SL/TP placement, stop-order
cancellation, order status checks, leverage setting — all real-money flows.

## Which calls

Per the 2026-04-23 DNS investigation agent report, the unwrapped call sites
are at exchange.py lines (approximate — verify with AST before editing):
389, 401, 423, 426, 441, 503, 546, 557, 565, 574, 577, 588, 599, 609, 663,
674, 731, 752, 763, 777, 788, 791, 803.

These cover:
- `create_order` (open_long, close_long, open_short, close_short)
- `cancel_order`, `cancel_all_orders`
- `fetch_order`, `fetch_open_orders`, `fetch_my_trades`
- `set_leverage`
- `place_sl_tp` internal calls

## Proposed approach

1. Keep `_call_with_timeout(fn, timeout=15)` default for reads.
2. Add a higher timeout for orders: `_call_with_timeout(fn, timeout=30)` —
   orders must complete (not silently skip), so the timeout is an upper bound
   on how long we'll block, after which we RAISE (not return None like the
   read path).
3. Add a one-retry helper `_call_with_retry_on_dns(fn, retries=1)` that catches
   `(OSError, ccxt.NetworkError)` whose message matches
   `TRANSIENT_EXCHANGE_HINTS` (mirror the overwatch helper) and retries once
   with 2-s sleep.
4. Wrap each order-path call: `self._call_with_retry_on_dns(lambda: self.client.create_order(...))`.
5. Audit that every raised exception is properly caught at the calling site in
   bot.py / risk_manager.py — orders that fail must register with the orphan
   safety net (2026-04-13 three-layer defense).

## Pre-deploy checklist (MANDATORY)

1. `/pre-restart-audit` on the full diff.
2. Confirm no open positions at restart time (check `trading_state.json`
   positions dict + `fetch_positions` ground truth).
3. Confirm bot has logged at least one clean `[MAKER] Limit filled` in the
   last 24h (verify exchange.py:288 postOnly fix still works).
4. Grep for test coverage of `_call_with_retry_on_dns` — write a smoke test
   if needed.
5. Verify the retry helper doesn't double-submit orders (one retry per
   call-site; exchange-side idempotency via clientOrderId if available).

## Risk

- **Order double-submit on retry:** if the exchange accepts the order but
  the response hangs, the retry submits a duplicate. Mitigation: use
  `clientOrderId` / `newClientOrderId` to make submissions idempotent.
  Alternative: don't retry create_order at all — only retry on reads.
- **Longer perceived latency on DNS bursts:** a 30-s order timeout means
  during a bad DNS window, an entry could block 30s before raising. In
  scalping, that's a meaningful delay — but still better than a hung call.
- **Blast radius:** real-money order flow. Cannot ship without
  /pre-restart-audit and a planned restart window.

## Blocked by

- No open positions at restart time.
- Memory of 2026-04-13 orphan-position incident — any change to order flow
  must preserve the three-layer defense.

## Not blocked by

- DNS local-cache install (Option B chosen in 2026-04-23 session — overwatch
  filter handles symptom; this fix is additional hardening, not a dependency).

## Related

- [lessons.md](../../memory/lessons.md) — "DNS outage froze main loop" (2026-04-10)
- [lessons.md](../../memory/lessons.md) — "Orphan positions — three-layer defense" (2026-04-13)
- scripts/overwatch.py — `TRANSIENT_EXCHANGE_HINTS` (2026-04-23, reusable pattern)
