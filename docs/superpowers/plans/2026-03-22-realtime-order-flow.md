# Real-Time Order Flow Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time trade streaming to the WS feed, replacing REST-based CVD with live order flow data, and integrate as ensemble layer 7 with extreme-condition veto.

**Architecture:** Add `watch_trades()` alongside existing `watch_ohlcv()` on the same ccxtpro connection. Buffer trades per 5m candle, compute buy/sell ratios and CVD. Bot reads stats via `get_order_flow()` method. Two files modified: ws_feed.py and bot.py.

**Tech Stack:** Python 3.14, ccxtpro (async WebSocket), Phemex perpetual futures

---

## Codebase API Reference

| Pattern | Correct |
|---------|---------|
| WS feed class | `WSDataFeed` in ws_feed.py |
| WS exchange instance | `self._exchange` (ccxtpro.phemex) |
| Thread lock | `self._lock` (threading.Lock) |
| Candle cache | `self._cache: dict[str, list]` — symbol → list of `[ts, o, h, l, c, v]` |
| Watch all symbols | `_watch_all()` creates asyncio tasks per symbol |
| Subscribe new symbols | `subscribe()` uses `asyncio.run_coroutine_threadsafe()` |
| Bot reads WS | `self._ws_feed.get_ohlcv(symbol)` — returns DataFrame |
| Bot CVD call | `self.exchange.get_cvd(symbol)` — REST, returns `{cvd, cvd_slope, divergence}` |
| Ensemble confidence | `_compute_confidence()` in bot.py — returns `(count, layers_list)` |
| Python path | `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python` |

---

## Task 1: Add Trade Streaming to ws_feed.py

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/ws_feed.py`

- [ ] **Step 1: Add imports and new instance variables**

Read ws_feed.py. Find `__init__`. Add `import collections` at the top (if not present) and add these instance variables after existing ones:

```python
import collections  # at top of file

# In __init__, after self._cache:
self._trade_buffer: dict[str, list] = {}
self._order_flow: dict[str, dict] = {}
self._current_candle_start: dict[str, int] = {}
self._candle_deltas: dict[str, collections.deque] = {}
self._cvd_total: dict[str, float] = {}
```

- [ ] **Step 2: Add `_archive_candle` method**

Add this method to WSDataFeed class:

```python
def _archive_candle(self, symbol: str):
    """Archive current candle's delta to CVD running total, reset for new candle."""
    flow = self._order_flow.get(symbol, {})
    delta = flow.get("delta", 0)
    self._cvd_total[symbol] = self._cvd_total.get(symbol, 0) + delta
    self._candle_deltas.setdefault(
        symbol, collections.deque(maxlen=10)
    ).append(delta)
    self._order_flow[symbol] = {
        "buy_volume": 0, "sell_volume": 0, "buy_ratio": 0.5,
        "delta": 0, "cvd": self._cvd_total[symbol],
        "cvd_slope": 0, "divergence": None,
        "large_trade_count": 0, "large_trade_bias": 0.5,
        "trade_count": 0, "updated_at": 0,
    }
    self._trade_buffer[symbol] = []
```

- [ ] **Step 3: Add `_watch_trades` async method**

Add this method to WSDataFeed class:

```python
async def _watch_trades(self, symbol: str):
    """Stream individual trades, aggregate into per-candle order flow stats."""
    import time as _time
    backoff = 2
    while self._running:
        try:
            trades = await self._exchange.watch_trades(symbol)
            batch_buy = 0.0
            batch_sell = 0.0
            batch_count = 0

            for trade in trades:
                cost = trade.get("cost", 0) or (
                    trade.get("amount", 0) * trade.get("price", 0))
                ts = trade.get("timestamp", 0)

                # Candle reset: floor to nearest 5m boundary
                candle_start = (ts // 300_000) * 300_000
                current = self._current_candle_start.get(symbol, 0)
                if candle_start != current and current != 0:
                    self._archive_candle(symbol)
                self._current_candle_start[symbol] = candle_start

                if trade.get("side") == "buy":
                    batch_buy += cost
                else:
                    batch_sell += cost
                batch_count += 1

            # Apply under lock (fast — no computation)
            with self._lock:
                flow = self._order_flow.setdefault(symbol, {
                    "buy_volume": 0, "sell_volume": 0, "buy_ratio": 0.5,
                    "delta": 0, "cvd": 0, "cvd_slope": 0, "divergence": None,
                    "large_trade_count": 0, "large_trade_bias": 0.5,
                    "trade_count": 0, "updated_at": 0,
                })
                flow["buy_volume"] += batch_buy
                flow["sell_volume"] += batch_sell
                flow["trade_count"] += batch_count
                total = flow["buy_volume"] + flow["sell_volume"]
                flow["buy_ratio"] = flow["buy_volume"] / total if total > 0 else 0.5
                flow["delta"] = flow["buy_volume"] - flow["sell_volume"]
                flow["cvd"] = self._cvd_total.get(symbol, 0) + flow["delta"]
                flow["updated_at"] = _time.time()

                # CVD slope from candle history
                deltas = self._candle_deltas.get(symbol, collections.deque(maxlen=10))
                if len(deltas) >= 2:
                    half = len(deltas) // 2
                    d_list = list(deltas)
                    flow["cvd_slope"] = sum(d_list[half:]) - sum(d_list[:half])
                else:
                    flow["cvd_slope"] = flow["delta"]

                # Divergence: price direction vs CVD direction
                candles = self._cache.get(symbol, [])
                if len(candles) >= 2:
                    price_dir = candles[-1][4] - candles[-2][4]
                    cvd_dir = flow["cvd_slope"]
                    if price_dir < 0 and cvd_dir > 0:
                        flow["divergence"] = "bullish"
                    elif price_dir > 0 and cvd_dir < 0:
                        flow["divergence"] = "bearish"
                    else:
                        flow["divergence"] = None
                else:
                    flow["divergence"] = None

            backoff = 2
        except Exception as e:
            logger.warning(f"[WS] Trade stream error for {symbol}: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
```

- [ ] **Step 4: Add `get_order_flow` public method**

```python
def get_order_flow(self, symbol: str) -> dict | None:
    """Get current candle's order flow stats for a symbol."""
    with self._lock:
        flow = self._order_flow.get(symbol)
        return dict(flow) if flow else None
```

- [ ] **Step 5: Wire `_watch_trades` into `_watch_all` and `subscribe`**

Find `_watch_all()` — currently creates tasks only for `_watch_symbol`. Add `_watch_trades` tasks:

```python
# In _watch_all, change task creation to include trades:
tasks = []
for sym in self.symbols:
    tasks.append(self._watch_symbol(sym))
    tasks.append(self._watch_trades(sym))
await asyncio.gather(*tasks)
```

Find `subscribe()` — where it launches `_watch_symbol` for new symbols via `run_coroutine_threadsafe`. Add `_watch_trades` launch alongside it:

```python
# After the existing run_coroutine_threadsafe for _watch_symbol:
asyncio.run_coroutine_threadsafe(self._watch_trades(sym), self._loop)
```

- [ ] **Step 6: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile ws_feed.py && echo "OK"
```

- [ ] **Step 7: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add ws_feed.py
git commit -m "feat: add real-time trade streaming to WS feed — order flow stats per candle"
```

---

## Task 2: Integrate Order Flow into bot.py

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/bot.py`

- [ ] **Step 1: Replace REST CVD call with WS order flow**

Read bot.py. Find where `self.exchange.get_cvd(symbol)` is called (around line 687 area). Replace with:

```python
# Get order flow from WS (real-time, no REST call)
flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None

# Build cvd_data from order flow (backward compatible with ensemble layer 3)
cvd_data = None
if flow and flow.get("trade_count", 0) > 0:
    cvd_data = {
        "cvd": flow.get("cvd", 0),
        "cvd_slope": flow.get("cvd_slope", 0),
        "divergence": flow.get("divergence"),
    }
else:
    # Fallback to REST CVD when WS trades unavailable
    cvd_data = self.exchange.get_cvd(symbol)
```

- [ ] **Step 2: Add order flow as ensemble layer 7**

Find `_compute_confidence()`. After layer 6 (OB imbalance), add layer 7. The method needs to receive `flow` as a parameter.

Add `flow: dict | None = None` to the method signature.

Add after the OB imbalance block:

```python
    # 7. Order flow — real-time buy/sell aggressor ratio
    if flow and flow.get("trade_count", 0) > 10:  # need meaningful sample
        buy_ratio = flow.get("buy_ratio", 0.5)
        if (is_long and buy_ratio > 0.55) or (not is_long and buy_ratio < 0.45):
            confirmed.append("order_flow")
```

Update the log line from `/6` to `/7`.

- [ ] **Step 3: Pass `flow` to `_compute_confidence`**

Find where `_compute_confidence` is called (around line 652). Add `flow=flow` to the call:

```python
confidence, layers = self._compute_confidence(
    direction, df, ob, htf_df=htf_df,
    cvd_data=cvd_data, hurst_val=hurst_val, funding_data=funding_data,
    strategy=strat_name, flow=flow  # NEW
)
```

- [ ] **Step 4: Add extreme order flow veto**

After the ensemble confidence check (the `if confidence < min_confidence: continue` block), add:

```python
# Order flow extreme veto — block entry if real money strongly disagrees
if flow and flow.get("trade_count", 0) > 20:  # need significant sample
    buy_ratio = flow.get("buy_ratio", 0.5)
    if direction == "long" and buy_ratio < 0.30:
        logger.info(
            f"[FLOW VETO] {symbol} LONG blocked — buy_ratio {buy_ratio:.0%} "
            f"({flow.get('trade_count', 0)} trades, sellers dominating)")
        continue
    if direction == "short" and buy_ratio > 0.70:
        logger.info(
            f"[FLOW VETO] {symbol} SHORT blocked — buy_ratio {buy_ratio:.0%} "
            f"({flow.get('trade_count', 0)} trades, buyers dominating)")
        continue
```

- [ ] **Step 5: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```

- [ ] **Step 6: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add bot.py
git commit -m "feat: integrate WS order flow — ensemble layer 7 + extreme veto, replaces REST CVD"
```

---

## Task 3: Audit & Deploy

- [ ] **Step 1: Deploy audit agents on both files**

Parallel audit ws_feed.py and bot.py for thread safety, async correctness, graceful degradation.

- [ ] **Step 2: Full compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile ws_feed.py
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile strategies.py
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile risk_manager.py
echo "All OK"
```

- [ ] **Step 3: Restart bot**

```bash
cd ~/Desktop/Phmex-S
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
```

- [ ] **Step 4: Verify trade streaming in logs**

```bash
sleep 30 && grep -E "FLOW|order_flow|watch_trades|Trade stream" ~/Desktop/Phmex-S/logs/bot.log | tail -10
```

Expect: trade stream connected, order flow stats appearing, no errors.

- [ ] **Step 5: Verify ensemble shows /7 in logs**

```bash
grep "ENSEMBLE" ~/Desktop/Phmex-S/logs/bot.log | tail -5
```

Expect: `confidence=X/7` with `order_flow` appearing in layers when buy_ratio aligns.
