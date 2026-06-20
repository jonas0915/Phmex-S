# Phase 0 — Fix `ob:null` on Slot Entry Snapshots

**Date:** 2026-06-19
**Status:** Design — pending review
**Scope:** Single-bug instrumentation fix. Prerequisite for the ST2.0 AI-lab
(Approach A, see the lab design that follows). Small, ship independently.

## Problem

Every real ST2.0 trade records `entry_snapshot.ob = null`. Verified: all 28
`mode=live` records in `trading_state_ST2.0.json` have `ob: null` (only the `flow`
block is populated). The orderbook half of the feature vector — `imbalance`,
`spread_pct`, wall counts — is missing on every live trade.

This blindfolds the lab two ways:
1. The lab's real-trade ingestion (`scripts/st2_lab/real_trades.py`) can only label
   real outcomes on `flow` features — exactly the half that shows almost no
   separation (gate-quantify NULL). Three of the four current champion filters key
   off orderbook data (`spread_pct`, plus the `imbalance` the signal needs), so the
   lab cannot learn from, or even audit, what those conditions did on real fills.
2. Any future model "trained on reality" is trained on feature-crippled rows.

No honest ST2.0 lab work is possible until live entries record `ob`.

## Root cause

`bot.py:_log_entry_snapshot` (≈line 2333) builds the snapshot's ob block as:

```python
"ob": {
    "imbalance": round(ob.get("imbalance", 0), 3),
    "bid_walls": len(ob.get("bid_walls", [])),
    "ask_walls": len(ob.get("ask_walls", [])),
    "spread_pct": round(ob.get("spread_pct", 0), 4),
} if ob else None,
```

So when the `ob` argument is `None`, the block serializes to `null`.

- **Main-bot entry** (`bot.py:1527`) passes the real `ob` → block populated. Correct.
- **Slot shared-tail entry** (`bot.py:2038`) passes a hardcoded `None`:

```python
snap = self._log_entry_snapshot(symbol, direction, slot.slot_id,
        _entry_strategy_name, signal.strength, entry_px, 0,
        None,   # <-- ob hardcoded None; flow passed correctly
        flow, ohlcv_last=..., ohlcv_df=...)
```

ST2.0 runs as a slot, so it always hits line 2038 → `ob:null`. The `flow` arg is
passed correctly, which is why `flow` survives and `ob` does not.

A valid `ob` is already in scope at this point: it is fetched once per symbol at
`bot.py:1735` (`ob = self.exchange.get_order_book(symbol)`) and already consumed in
the same slot loop by the OB gate (`ob.get("imbalance", ...)`) and by
`_compute_confidence(direction, df, ob, ...)` at `bot.py:1925`. The fix is to pass
the `ob` that already exists, not to fetch anything new.

## The fix

Change the slot snapshot call at `bot.py:2038` to pass `ob` instead of `None`:

```python
snap = self._log_entry_snapshot(symbol, direction, slot.slot_id,
        _entry_strategy_name, signal.strength, entry_px, 0,
        ob,     # was None — record the orderbook block on slot entries
        flow, ohlcv_last=..., ohlcv_df=...)
```

That is the entire functional change. `_log_entry_snapshot` already handles `ob`
being `None` gracefully (`} if ob else None`), so on a genuine `get_order_book`
failure the snapshot still records `ob:null` rather than crashing — strictly better
than today.

## Scope / non-goals

- **Single edit** at `bot.py:2038`. No change to `_log_entry_snapshot`, the signal,
  the gates, or any exit logic.
- **Not backfillable**: the 28 historical live trades stay `ob:null` (the data was
  never captured). The fix only improves trades from restart forward. The real
  labeled set starts accumulating complete rows immediately after deploy.
- **Main-bot path unchanged** (already correct).
- This is instrumentation only — it does not change what ST2.0 trades or how it
  exits. Zero behavioral change to live trading; only the recorded snapshot changes.

## Edge cases

- `get_order_book` returns `None` (API hiccup): snapshot records `ob:null` for that
  one trade (current behavior for all trades — no regression).
- Paper vs live: line 2038 is the shared tail for both, so paper slots also start
  recording `ob`. Desired — the lab's sandbox/paper data gets the same completeness.
- `ob` present but missing a sub-field: `.get(key, 0)` defaults already guard this.

## Testing

1. **Regression unit test** (`tests/test_entry_snapshot_ob.py`): call
   `_log_entry_snapshot` with a populated `ob` dict and assert the returned
   snapshot's `ob` block is non-null with the expected `imbalance`/`spread_pct`;
   call with `ob=None` and assert `ob` is `None` (graceful path preserved).
2. **Static guard**: assert (grep test or comment) that the slot entry call passes
   `ob`, to prevent a future regression back to `None`.
3. **Live verification after deploy**: after the next slot entry, confirm the new
   `trading_state_<slot>.json` record and `logs/entry_snapshots.jsonl` line have a
   populated `ob` block.

## Propagation (CLAUDE.md rule)

- `logs/entry_snapshots.jsonl` and `trading_state_<slot>.json` records gain a real
  `ob` block — downstream consumers (`real_trades.py`, dashboards) already read
  `entry_snapshot.ob` and tolerate `null`, so no consumer breaks; they simply start
  receiving real data.
- No Telegram/dashboard metric is added or renamed, so no notifier/report changes
  are required. (Confirm during audit.)

## Deploy

Through `/pre-restart-audit` (live-money bot). Bot currently flat — clean window.
After restart, watch for the first slot entry and verify the `ob` block is present.

## Why this is Phase 0

Cheap, isolated, zero behavioral risk, and it unblocks every later phase: the
discovery engine, the real-fill labeling, and the model graduation path all depend
on real trades carrying their full feature vector.
