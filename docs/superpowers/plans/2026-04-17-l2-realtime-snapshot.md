# L2 Realtime Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the L2 snapshot writer from once-per-60s-cycle to a 5-second daemon thread, so the L2 Anticipation Monitor panel updates effectively in real-time.

**Architecture:** Add a daemon thread in `bot.py` that wakes every 5s, reads current ws_feed data (in-memory, no API calls) and last-known orderbook depth from a new `_ob_depth_cache`, then writes `l2_snapshot.json` atomically. Main loop populates the depth cache but no longer writes the snapshot itself. Dashboard poll interval drops from 20s to 3s.

**Tech Stack:** Python 3.14 stdlib (`threading`, `time`), existing `ws_feed` WebSocket cache

**Spec:** `docs/superpowers/specs/2026-04-17-l2-realtime-snapshot-design.md`

---

### Task 1: Add `_ob_depth_cache` + live writer thread + remove old snapshot write

**Files:**
- Modify: `bot.py` — add `import threading`, init `_ob_depth_cache` in `__init__`, populate cache in main loop, add live writer method, start thread in `start()`, remove old accumulator + write call

- [ ] **Step 1: Add `import threading` to bot.py**

Check current imports:
```bash
head -20 /Users/jonaspenaso/Desktop/Phmex-S/bot.py | grep -E "^import|^from"
```

If `import threading` is not present, add it. Line 1 currently reads `import signal`. Add `import threading` right after existing imports, before line 7's `from collections import deque`. The final top block should look like:
```python
import signal
import time
import datetime
import subprocess
import os
import json
import threading
from collections import deque
```

- [ ] **Step 2: Initialize `_ob_depth_cache` in `__init__`**

Find this area in `bot.py` (~line 184 — near other dict inits):
```bash
grep -n "self\._funding_cache\|self\._divergence_cooldown" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Right after the `self._divergence_cooldown` declaration, add:
```python
        self._ob_depth_cache: dict[str, dict] = {}  # symbol -> depth data, populated by main loop, read by live writer thread
```

- [ ] **Step 3: Populate `_ob_depth_cache` in main loop after orderbook fetch**

Find where `ob = self.exchange.get_order_book(symbol)` is called in the main loop:
```bash
grep -n "ob = self.exchange.get_order_book" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

There should be one match in the main loop (~line 936). Right after that line (keep existing logic unchanged), add:
```python
            # Cache depth for live L2 writer thread (no API cost — data is already fetched)
            if ob:
                self._ob_depth_cache[symbol] = {
                    "bid_depth_usdt": ob.get("bid_depth_usdt"),
                    "ask_depth_usdt": ob.get("ask_depth_usdt"),
                    "imbalance":      ob.get("imbalance", 0),
                    "updated_at":     time.time(),
                }
```

Match the indentation of the surrounding code in the main loop (typically 12 spaces for inside-a-for-loop inside-a-method).

- [ ] **Step 4: Remove old snapshot accumulator initialization**

Find the existing accumulator init:
```bash
grep -n "_l2_snapshot_accum" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Expected: 3 matches (init, populate, write call). 

Delete the init line (~line 903):
```python
        _l2_snapshot_accum: dict[str, dict] = {}
```

Also delete the comment above it if present:
```python
        # Accumulate L2/tape signals for dashboard snapshot (written at end of cycle)
```

- [ ] **Step 5: Remove per-symbol snapshot accumulation**

Find the per-symbol snapshot capture (~line 961):
```bash
sed -n '955,975p' /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Delete the entire block that populates `_l2_snapshot_accum[symbol] = {...}` including its comment. The block looks like:
```python
            # Record L2 snapshot for dashboard (overwritten each cycle)
            _price = float(df.iloc[-1]["close"]) if len(df) > 0 else 0.0
            _l2_snapshot_accum[symbol] = {
                "buy_ratio":         (flow or {}).get("buy_ratio"),
                "cvd_slope":         (flow or {}).get("cvd_slope"),
                "bid_depth_usdt":    (ob or {}).get("bid_depth_usdt"),
                "ask_depth_usdt":    (ob or {}).get("ask_depth_usdt"),
                "large_trade_bias":  (flow or {}).get("large_trade_bias"),
                "trade_count":       (flow or {}).get("trade_count", 0),
                "last_price":        _price,
                "updated_at":        time.time(),
            }
```

Remove those 12 lines entirely. The depth cache from Step 3 replaces the orderbook part; the flow data now comes from the thread reading ws_feed directly.

- [ ] **Step 6: Remove the per-cycle snapshot write call**

Find the write call at end of main loop:
```bash
grep -n "_write_l2_snapshot" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Expected: 2 matches after the Step 4-5 deletions — one in the helper function definition, one call.

Delete the CALL (not the helper function definition). The call looks like (~line 1344):
```python
        # Write L2 snapshot for dashboard (silent on failure)
        _write_l2_snapshot(_l2_snapshot_accum)
```

Delete those two lines. Leave `_write_l2_snapshot()` function intact — the new thread uses it.

- [ ] **Step 7: Add the live writer method to the Phmex2Bot class**

Find a good location inside the class — after `_run_cycle()` ends is natural. Search for the end of `_run_cycle`:
```bash
grep -n "^    def _run_cycle\|^    def " /Users/jonaspenaso/Desktop/Phmex-S/bot.py | head -20
```

Insert this method AFTER `_run_cycle()` ends but BEFORE the next `def` that follows:

```python
    def _l2_live_writer_loop(self, interval_sec: float = 5.0) -> None:
        """Daemon thread: writes l2_snapshot.json every `interval_sec` from in-memory caches.
        No API calls — reads ws_feed (live) and _ob_depth_cache (populated by main loop)."""
        while self.running:
            try:
                pairs = list(self.active_pairs)
                accum: dict[str, dict] = {}
                for symbol in pairs:
                    flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
                    depth = self._ob_depth_cache.get(symbol, {})
                    accum[symbol] = {
                        "buy_ratio":         (flow or {}).get("buy_ratio"),
                        "cvd_slope":         (flow or {}).get("cvd_slope"),
                        "bid_depth_usdt":    depth.get("bid_depth_usdt"),
                        "ask_depth_usdt":    depth.get("ask_depth_usdt"),
                        "large_trade_bias":  (flow or {}).get("large_trade_bias"),
                        "trade_count":       (flow or {}).get("trade_count", 0),
                        "last_price":        None,  # price not needed for panel, omit
                        "updated_at":        time.time(),
                    }
                _write_l2_snapshot(accum)
            except Exception as e:
                logger.debug(f"[L2_LIVE] writer tick failed: {e}")
            time.sleep(interval_sec)
```

Match indentation of other methods in the class (typically 4 spaces for method def).

- [ ] **Step 8: Start the live writer thread in `start()`**

Find the main loop setup in `start()`:
```bash
grep -n "self.running = True" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Right BEFORE the line `self.running = True` (~line 421), add:

```python
        # Start L2 snapshot live writer thread (updates every 5s for real-time dashboard)
        threading.Thread(
            target=self._l2_live_writer_loop,
            daemon=True,
            name="l2-live-writer",
        ).start()
        logger.info("[L2_LIVE] Snapshot writer thread started (5s interval)")
```

Match indentation of surrounding code in `start()` (typically 8 spaces).

- [ ] **Step 9: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 10: Verify all snapshot mechanics are in the right place**

```bash
grep -n "_l2_snapshot_accum\|_ob_depth_cache\|_l2_live_writer_loop\|_write_l2_snapshot\|l2-live-writer" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Expected matches:
- 0 matches for `_l2_snapshot_accum` (removed)
- 2+ matches for `_ob_depth_cache` (init + main loop populate)
- 2 matches for `_l2_live_writer_loop` (def + thread start)
- 2 matches for `_write_l2_snapshot` (def + call inside the new loop)
- 1 match for `l2-live-writer` (thread name)

- [ ] **Step 11: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: L2 snapshot writer moved to 5s daemon thread (real-time)"
```

---

### Task 2: Dashboard polls every 3 seconds

**Files:**
- Modify: `web_dashboard.py` — change `setInterval` from 20000 to 3000, update footer text

- [ ] **Step 1: Update client-side refresh interval**

Find the current value:
```bash
grep -n "setInterval(refresh" /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py
```

Expected: one match at ~line 2039 with value `20000`.

Replace that line:
```python
  setInterval(refresh, 20000);
```

with:
```python
  setInterval(refresh, 3000);
```

- [ ] **Step 2: Update footer text**

Find the footer:
```bash
grep -n "Auto-refresh 20s" /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py
```

Expected: one match at ~line 1418.

Replace:
```python
    Auto-refresh 20s &middot; Charts {CHART_INTERVAL}s &middot; Read-only &middot; Zero API calls
```

with:
```python
    Auto-refresh 3s &middot; Charts {CHART_INTERVAL}s &middot; Read-only &middot; Zero API calls
```

- [ ] **Step 3: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile web_dashboard.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add web_dashboard.py && git commit -m "feat(dashboard): poll every 3s for real-time L2 panel updates"
```

---

### Task 3: Restart Bot + Dashboard, Verify Real-Time Updates

- [ ] **Step 1: Run `/pre-restart-audit` skill**

Invoke the `pre-restart-audit` skill. Do not proceed until all checks pass.

- [ ] **Step 2: Restart bot**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
kill $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 10
cat .bot.pid
```
Expected: new PID printed.

- [ ] **Step 3: Restart dashboard**

```bash
kill $(ps aux | grep "web_dashboard" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
nohup /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py > /Users/jonaspenaso/Desktop/Phmex-S/logs/dashboard.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8050/
```
Expected: `HTTP 200`

- [ ] **Step 4: Verify live writer thread is running**

```bash
grep "L2_LIVE.*started\|L2_LIVE.*writer" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -5
```
Expected: at least one line `[L2_LIVE] Snapshot writer thread started (5s interval)`.

- [ ] **Step 5: Verify snapshot file updates frequently**

```bash
for i in 1 2 3 4; do
  echo "Check $i: $(date)"
  stat -f "%Sm %z bytes" /Users/jonaspenaso/Desktop/Phmex-S/l2_snapshot.json 2>/dev/null || ls -la /Users/jonaspenaso/Desktop/Phmex-S/l2_snapshot.json
  sleep 6
done
```
Expected: mtime changes every 6s — confirms the 5s writer is running. File size should stay small (~2 KB).

- [ ] **Step 6: Verify no errors in bot.log**

```bash
grep -i "error\|traceback\|exception\|L2_LIVE.*failed" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: no new errors after restart timestamp. `[L2_LIVE]` lines should only appear on failures, not normal operation.

- [ ] **Step 7: Verify dashboard renders fresh data**

Open http://127.0.0.1:8050/ in a browser. Watch for:
- L2 panel values changing every few seconds during active market
- "updated Xs ago" header showing single-digit seconds
- Footer reads "Auto-refresh 3s"
