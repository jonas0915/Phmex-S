# Real-Time Order Flow Integration — Design Spec

**Author:** Claude + Jonas
**Date:** March 22, 2026
**Status:** Approved
**Goal:** Add real-time trade streaming via WebSocket to replace REST-based CVD, add order flow as ensemble layer 7 with extreme-condition veto, and improve entry quality across all v10 strategy slots.

---

## Context

### The Problem
- 93.8% of time_exit trades were wrong-direction entries
- Current CVD uses REST `fetch_trades(200)` — stale data, rate limit risk
- Order book snapshots are weak predictors at 5m timeframe
- No real-time visibility into who is actually buying vs selling
- WS feed already runs but only subscribes to OHLCV candles — trade data is available but unused

### The Solution
Add `watch_trades()` to the existing WS connection. Buffer trades per candle. Compute real-time order flow stats. Use as ensemble layer 7 + extreme veto.

### Research Backing
- Order flow imbalance explains ~65% of concurrent price moves (Cont, Kukanov, Stoikov)
- Predictive at seconds-to-minutes horizon — aligns with our 5m timeframe
- Executed trades cannot be faked (unlike order book which can be spoofed)
- Our WS connection already supports `watch_trades()` — no new API needed

---

## Architecture

### Data Flow

```
WS connection (ccxtpro.phemex — existing, shared)
  ├── watch_ohlcv(symbol, "5m")  → candle cache (existing)
  └── watch_trades(symbol)        → trade buffer (NEW)
                                       ↓
                            Per-candle aggregation
                            (resets every 5m candle)
                                       ↓
                            OrderFlowStats dataclass
                                       ↓
                    ┌──────────────────┴──────────────────┐
                    │                                      │
            Ensemble layer 7                        CVD replacement
            (confidence vote                    (replaces REST get_cvd)
             + extreme veto)
```

### Files Modified

| File | Change | Purpose |
|------|--------|---------|
| `ws_feed.py` | Add `watch_trades()` watcher, trade buffer, aggregation | Core data collection |
| `bot.py` | Read order flow stats from WS, add to ensemble, add veto check, remove REST CVD call | Integration |
| `exchange.py` | No changes needed | `get_cvd()` remains as fallback if WS trades unavailable |

### New File: None
All changes fit within existing files. OrderFlowStats can be a dataclass inside ws_feed.py.

---

## ws_feed.py Changes

### Trade Buffer Structure

```python
# Per-symbol trade buffer, resets each candle
self._trade_buffer: dict[str, list] = {}  # symbol → [trades since candle open]

# Per-symbol aggregated stats (updated with running tallies, not re-computed)
self._order_flow: dict[str, dict] = {}    # symbol → OrderFlowStats

# Per-symbol candle tracking for reset detection
self._current_candle_start: dict[str, int] = {}  # symbol → candle start epoch ms

# Per-symbol historical candle deltas for CVD slope
self._candle_deltas: dict[str, collections.deque] = {}  # symbol → deque(maxlen=10)

# Per-symbol running CVD total (survives candle resets, cleared on reconnect)
self._cvd_total: dict[str, float] = {}  # symbol → cumulative delta
```

### OrderFlowStats (computed per candle)

```python
{
    "buy_volume": float,       # Total USDT bought by aggressors
    "sell_volume": float,      # Total USDT sold by aggressors
    "buy_ratio": float,        # buy_vol / total_vol (0.0 to 1.0, 0.5 when no data)
    "delta": float,            # buy_vol - sell_vol (net pressure)
    "cvd": float,              # Running cumulative delta across candles
    "cvd_slope": float,        # CVD direction over last 5 candles (from _candle_deltas deque)
    "divergence": str | None,  # "bullish" / "bearish" / None — price vs CVD divergence
    "large_trade_count": int,  # Trades > 5x median size
    "large_trade_bias": float, # Large trade buy ratio (for logging/future use)
    "trade_count": int,        # Total trades this candle
    "updated_at": float,       # Epoch timestamp
}
```

### New Watcher

A second async task alongside `_watch_symbol()`. Uses incremental running tallies (not re-aggregation from buffer) to avoid holding the lock during expensive computation.

```python
async def _watch_trades(self, symbol: str):
    """Stream individual trades, aggregate into per-candle order flow stats."""
    while self._running:
        trades = await self._exchange.watch_trades(symbol)
        # Compute incremental updates OUTSIDE lock
        batch_buy = 0.0
        batch_sell = 0.0
        for trade in trades:
            cost = trade.get("cost", 0) or (trade.get("amount", 0) * trade.get("price", 0))
            ts = trade.get("timestamp", 0)

            # Candle reset detection: floor timestamp to nearest 5m boundary
            candle_start = (ts // 300_000) * 300_000
            current = self._current_candle_start.get(symbol, 0)
            if candle_start != current and current != 0:
                # New candle — archive and reset
                self._archive_candle(symbol)
            self._current_candle_start[symbol] = candle_start

            if trade.get("side") == "buy":
                batch_buy += cost
            else:
                batch_sell += cost

        # Apply incremental update under lock (fast)
        with self._lock:
            flow = self._order_flow.setdefault(symbol, {
                "buy_volume": 0, "sell_volume": 0, "trade_count": 0})
            flow["buy_volume"] += batch_buy
            flow["sell_volume"] += batch_sell
            flow["trade_count"] += len(trades)
            total = flow["buy_volume"] + flow["sell_volume"]
            flow["buy_ratio"] = flow["buy_volume"] / total if total > 0 else 0.5
            flow["delta"] = flow["buy_volume"] - flow["sell_volume"]
            flow["cvd"] = self._cvd_total.get(symbol, 0) + flow["delta"]
            flow["updated_at"] = time.time()

            # CVD slope from historical candle deltas
            deltas = self._candle_deltas.get(symbol, collections.deque(maxlen=10))
            if len(deltas) >= 2:
                first_half = sum(list(deltas)[:len(deltas)//2])
                second_half = sum(list(deltas)[len(deltas)//2:])
                flow["cvd_slope"] = second_half - first_half
            else:
                flow["cvd_slope"] = flow["delta"]  # current candle only

            # Divergence detection: price direction vs CVD direction
            # Uses OHLCV cache for price comparison
            candles = self._cache.get(symbol, [])
            if len(candles) >= 2:
                price_dir = candles[-1][4] - candles[-2][4]  # close[-1] - close[-2]
                cvd_dir = flow["cvd_slope"]
                if price_dir < 0 and cvd_dir > 0:
                    flow["divergence"] = "bullish"
                elif price_dir > 0 and cvd_dir < 0:
                    flow["divergence"] = "bearish"
                else:
                    flow["divergence"] = None
            else:
                flow["divergence"] = None

    # Cap buffer at 10K trades per symbol
    buf = self._trade_buffer.get(symbol, [])
    if len(buf) > 10_000:
        self._trade_buffer[symbol] = buf[-10_000:]
```

### _archive_candle helper

```python
def _archive_candle(self, symbol: str):
    """Archive current candle's delta to CVD running total, reset for new candle."""
    flow = self._order_flow.get(symbol, {})
    delta = flow.get("delta", 0)

    # Add to CVD running total
    self._cvd_total[symbol] = self._cvd_total.get(symbol, 0) + delta

    # Store in candle deltas history (for slope calculation)
    self._candle_deltas.setdefault(symbol, collections.deque(maxlen=10)).append(delta)

    # Reset current candle stats
    self._order_flow[symbol] = {
        "buy_volume": 0, "sell_volume": 0, "buy_ratio": 0.5,
        "delta": 0, "cvd": self._cvd_total[symbol],
        "cvd_slope": 0, "divergence": None,
        "large_trade_count": 0, "large_trade_bias": 0.5,
        "trade_count": 0, "updated_at": time.time(),
    }
    self._trade_buffer[symbol] = []
```

### Launching Trade Watchers

**In `_watch_all()` (line 165):**
```python
tasks = []
for sym in self.symbols:
    tasks.append(self._watch_symbol(sym))
    tasks.append(self._watch_trades(sym))  # NEW
await asyncio.gather(*tasks)
```

**In `subscribe()` (line 104) — for dynamically added symbols:**
```python
asyncio.run_coroutine_threadsafe(self._watch_trades(sym), self._loop)  # NEW
```

### Reconnection Handling

On WS reconnection (existing backoff logic in `_watch_trades`):
- Current candle buffer is cleared (partial data is unreliable)
- Historical CVD (`_cvd_total`) is preserved (completed candles are valid)
- `_candle_deltas` deque is preserved (slope history intact)
- `_current_candle_start` is reset to 0 (forces fresh candle detection)

### Public API

```python
def get_order_flow(self, symbol: str) -> dict | None:
    """Get current candle's order flow stats for a symbol."""
    with self._lock:
        return self._order_flow.get(symbol)
```

---

## bot.py Changes

### 1. Replace REST CVD with WS Order Flow

Current (around line 687):
```python
cvd_data = self.exchange.get_cvd(symbol)  # REST call
```

New:
```python
# Get order flow from WS (real-time, no REST call)
flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None

# Build cvd_data from order flow (backward compatible with ensemble layer 3)
cvd_data = None
if flow:
    cvd_data = {
        "cvd": flow.get("cvd", 0),
        "cvd_slope": flow.get("cvd_slope", 0),
        "divergence": flow.get("divergence"),  # Preserves divergence detection (bullish/bearish)
    }
elif self._ws_feed is None or not self._ws_feed.is_connected:
    # Fallback to REST CVD when WS unavailable
    cvd_data = self.exchange.get_cvd(symbol)
```

**Note:** CVD divergence is now computed in ws_feed.py `_watch_trades()` by comparing price direction vs CVD direction. Ensemble layer 3 continues to work exactly as before — same dict keys, same divergence values.

### 2. Add Order Flow as Ensemble Layer 7

In `_compute_confidence()`, add after layer 6 (OB imbalance):

```python
# 7. Order flow — real-time buy/sell aggressor ratio
if flow:
    buy_ratio = flow.get("buy_ratio", 0.5)
    if (is_long and buy_ratio > 0.55) or (not is_long and buy_ratio < 0.45):
        confirmed.append("order_flow")
```

Update log to show `/7` instead of `/6`.

**Ensemble threshold stays at 3.** Now 3/7 instead of 3/6. This intentionally makes entries slightly easier (more chances to accumulate confirmations), which counteracts the veto that blocks the worst entries. Net effect: more trades enter, but only quality ones survive the veto. The CONFIDENCE_THRESHOLDS dict in bot.py already supports per-strategy values — can tighten individually later if needed.

### 3. Add Extreme Order Flow Veto

After ensemble confidence check, before entry:

```python
# Order flow extreme veto — block entry if real money strongly disagrees
if flow:
    buy_ratio = flow.get("buy_ratio", 0.5)
    if direction == "long" and buy_ratio < 0.30:
        logger.info(f"[FLOW VETO] {symbol} LONG blocked — buy_ratio {buy_ratio:.0%} (sellers dominating)")
        continue
    if direction == "short" and buy_ratio > 0.70:
        logger.info(f"[FLOW VETO] {symbol} SHORT blocked — buy_ratio {buy_ratio:.0%} (buyers dominating)")
        continue
```

### 4. Graceful Degradation

If WS trade data is unavailable (feed not connected, symbol not streaming):
- Fall back to REST `get_cvd()` (existing behavior)
- Order flow layer 7 simply doesn't confirm (no penalty)
- Veto doesn't fire (no data = no block)
- Bot works exactly as before — zero regression risk

---

## Integration with v10 Slots

Order flow is computed at the WS feed level (shared across all slots). Each slot benefits:

| Slot | How Order Flow Helps |
|------|---------------------|
| 5m scalp | Confirms entry direction with real buying/selling pressure |
| 1h momentum | Verifies buyers stepping in at pullback levels |
| Mean reversion | Confirms selling exhaustion before fading oversold |
| Liquidation cascade | Distinguishes forced liquidations (one-sided flow) from organic volume |
| Funding contrarian | Confirms the funding unwind is actually happening |

No per-slot configuration needed — the flow data is available to any strategy that reads it.

---

## Veto Thresholds

| Buy Ratio | Long Entry | Short Entry |
|-----------|-----------|-------------|
| > 0.70 | +1 confidence (strong agree) | **VETO** (buyers dominating, don't short) |
| 0.55 - 0.70 | +1 confidence | Neutral |
| 0.45 - 0.55 | Neutral | Neutral |
| 0.30 - 0.45 | Neutral | +1 confidence |
| < 0.30 | **VETO** (sellers dominating, don't buy) | +1 confidence (strong agree) |

---

## Expected Results

| Metric | Before | After | Basis |
|--------|--------|-------|-------|
| Wrong-direction entries | ~50% | ~30-35% | Veto blocks worst entries |
| Win rate | 35.9% | 40-45% | Better entry quality |
| Time_exit % | 46% of exits | 25-30% | Fewer aimless trades |
| REST API calls | 1 per signal per pair | 0 (WS replaces CVD) | Fewer rate limit issues |
| Entry data freshness | Seconds stale (REST) | Real-time (WS) | Faster reaction |

---

## Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| WS trade stream adds latency | Separate async task, doesn't block OHLCV |
| Trade buffer memory growth | Reset every candle, cap buffer at 10K trades |
| Phemex WS disconnection | Graceful fallback to REST CVD |
| Veto too aggressive (blocks good trades) | 30/70 thresholds are extreme — only blocks truly one-sided flow |
| More complexity | Single file change (ws_feed.py), clean dataclass API |

---

## Implementation Estimate

- `ws_feed.py`: ~80 lines (trade watcher + buffer + aggregation + public API)
- `bot.py`: ~20 lines (replace REST CVD, add layer 7, add veto)
- Total: ~100 lines of code
- No new files, no new dependencies, no new API connections
