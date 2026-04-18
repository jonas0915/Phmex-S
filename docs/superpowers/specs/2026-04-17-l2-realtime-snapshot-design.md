# L2 Realtime Snapshot — Design Spec
**Date:** 2026-04-17
**Status:** Approved
**Scope:** Convert the L2 snapshot writer from a once-per-cycle (60s) mechanism to a background thread that updates every 5 seconds, making the L2 Anticipation Monitor panel effectively real-time

---

## Problem Statement

The current `l2_snapshot.json` is written once per main bot cycle (~60s). The L2 Anticipation Monitor panel on the dashboard therefore shows data that can be up to 60s stale, plus 20s of client-polling delay. Signals like `buy_ratio`, `cvd_slope`, and `large_trade_bias` move quickly during active markets. The panel looks frozen when the market is moving.

The underlying data is already real-time — `ws_feed` streams trades continuously and updates its internal `_order_flow` dict tick-by-tick. The snapshot just needs to read from that cache more often.

---

## Architecture

Add a daemon thread to the bot that wakes every 5 seconds, reads the current `ws_feed` flow data for each active pair, merges it with the last-known orderbook depth from the main cycle, and writes `l2_snapshot.json`. The dashboard continues reading the same file (no change) but polls faster.

---

## Changes

### Change 1: Add `_l2_live_writer_thread` to bot.py

A daemon thread that runs for the lifetime of the bot. Each tick (every 5s):

```
1. Snapshot self.active_pairs (copy — may change across scans)
2. For each symbol in the pairs:
   a. Read flow = self._ws_feed.get_order_flow(symbol)  (no API call — in-memory)
   b. Read last-known depth from a new self._ob_depth_cache (filled by main loop)
   c. Build per-symbol entry with all 8 fields
3. Write l2_snapshot.json atomically (.tmp + os.replace)
4. Sleep 5 seconds
```

The thread is started from `Phmex2Bot.run()` just like the background scanner thread. Runs as `daemon=True` so it dies with the main process.

### Change 2: Main loop populates `self._ob_depth_cache`

The main loop already fetches `ob = self.exchange.get_order_book(symbol)` per symbol per cycle. Add one line after that fetch:

```python
if ob:
    self._ob_depth_cache[symbol] = {
        "bid_depth_usdt": ob.get("bid_depth_usdt"),
        "ask_depth_usdt": ob.get("ask_depth_usdt"),
        "bid_walls": ob.get("bid_walls", []),
        "ask_walls": ob.get("ask_walls", []),
        "imbalance": ob.get("imbalance", 0),
        "updated_at": time.time(),
    }
```

Initialize `self._ob_depth_cache: dict[str, dict] = {}` in `__init__`. The live writer thread reads from this cache — no new API calls.

### Change 3: Remove the snapshot write from main loop

The current `_write_l2_snapshot(_l2_snapshot_accum)` call at the end of the main symbol loop is now redundant. The live writer does this every 5s. Delete the call + the accumulation (`_l2_snapshot_accum` dict + per-symbol entries).

The helper function `_write_l2_snapshot()` stays — the live thread uses it.

### Change 4: Dashboard polls faster

In `web_dashboard.py`, find the client-side auto-refresh interval (currently 20 seconds) and change it to **3 seconds** for `/api/content` polls. Keep chart refresh at 30s (charts don't need fast updates).

---

## Data Flow

```
WS feed (live trades stream)
      ↓
ws_feed._order_flow[symbol] (in-memory, updates continuously)
      ↓
_l2_live_writer_thread (every 5s)
      ↓
l2_snapshot.json (atomic write)
      ↓
dashboard /api/content handler
      ↓
browser (polls every 3s)
```

Depth data flows separately:
```
Main bot cycle (every 60s)
      ↓
exchange.get_order_book() (API call, already happens)
      ↓
self._ob_depth_cache[symbol] (in-memory)
      ↓
_l2_live_writer_thread reads this cache (no API)
```

---

## Affected Files

| File | Change |
|---|---|
| `bot.py` | Add `_l2_live_writer_thread` method + daemon thread start in `run()`. Init `_ob_depth_cache` dict. Populate cache in main loop. Remove now-redundant snapshot write at end of main loop. ~50 lines. |
| `web_dashboard.py` | Change client-side `setInterval(refresh, 20000)` to `setInterval(refresh, 3000)`. One line. |

---

## Failure Modes & Handling

| Scenario | Behavior |
|---|---|
| `_ws_feed` is None | Thread skips (flow data unavailable); snapshot written with null flow fields. Dashboard shows ⚫ "no feed" for all symbols. |
| `self.active_pairs` empty | Thread writes empty `{}` symbols dict. Panel shows "No symbols in snapshot." |
| Depth cache stale (>120s) | Snapshot still written with stale depth. Acceptable — dashboard shows the age. |
| Thread crashes | daemon=True ensures bot continues. Log the error. Restart on next bot restart (don't auto-restart the thread — crashes indicate bugs to investigate). |
| Atomic write fails (disk full) | `_write_l2_snapshot()` already handles this silently with debug log. |
| Dashboard polls faster than snapshot updates | No problem — dashboard just re-reads the same snapshot. Bandwidth is ~few KB per request, local loopback. |

---

## Performance / Cost

| Metric | Current | After change |
|---|---|---|
| Snapshot writes | 60/hour (1/min) | 720/hour (1/5s) |
| File size | ~2 KB | ~2 KB (unchanged) |
| CPU per snapshot | ~0.1 ms | ~0.1 ms |
| Phemex API calls | 0 extra | 0 extra (reads cached depth) |
| Dashboard bandwidth | 1 req/20s = 3/min | 1 req/3s = 20/min (local, ~10 KB each = 200 KB/min) |
| Disk wear | negligible | negligible (same file overwritten) |

Net impact: effectively zero cost.

---

## Success Criteria

- After restart, `l2_snapshot.json`'s `updated_at` field updates every ~5 seconds (watch with `watch -n 1 "stat -f %m l2_snapshot.json"`)
- Dashboard L2 panel values visibly change every few seconds during active markets
- No new errors in `bot.log` after restart
- Bot main cycle still runs at 60s cadence (thread doesn't interfere with trading logic)
- Phemex API call rate unchanged (confirmed via logs)

---

## Out of Scope

- Making orderbook depth real-time (would require per-symbol L2 WS subscription — big change)
- WebSocket push to dashboard (HTTP polling at 3s is sufficient for this use case)
- Historical L2 signal chart / trend lines (v1 is current-snapshot only)
- Per-symbol alerts when all 3 L2 signals align (separate feature)
