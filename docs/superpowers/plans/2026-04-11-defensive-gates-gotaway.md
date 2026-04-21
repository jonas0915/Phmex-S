# Defensive Gates + gotAway Log + Limit-Only Entries — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix divergence gate bypass, add QUIET regime gate, create gotAway bypass log, add htf_adx to entry snapshots, and switch entries to limit-only (no market fallback) to eliminate taker fees.

**Architecture:** All gate changes are in `bot.py` — additive `continue` blocks in the existing entry gate flow. Order execution changes are in `exchange.py` — entry method removes market fallback, exit method extends limit wait. Both files are independent changes.

**Tech Stack:** Python 3.14, ccxt, Phemex API

---

### Task 1: Add `_log_gotaway()` Method

**Files:**
- Modify: `bot.py:1409` (insert new method before `_log_entry_snapshot`)

This must be implemented first since Tasks 2 and 3 call it.

- [ ] **Step 1: Add the `_log_gotaway` method to the `TradingBot` class**

Insert this method before `_log_entry_snapshot` (line 1409):

```python
    def _log_gotaway(self, reason: str, symbol: str, direction: str, strategy: str,
                     strength: float, confidence: int, price: float,
                     ob: dict | None, flow: dict | None, df=None):
        """Log a trade that was blocked by defensive gates for later analysis."""
        import json as _json
        entry = {
            "ts": int(time.time()),
            "reason": reason,
            "symbol": symbol,
            "direction": direction,
            "strategy": strategy,
            "strength": round(strength, 3),
            "confidence": confidence,
            "price": round(price, 6),
            "ob": {
                "imbalance": round(ob.get("imbalance", 0), 3),
                "spread_pct": round(ob.get("spread_pct", 0), 4),
            } if ob else None,
            "flow": {
                "buy_ratio": round(flow.get("buy_ratio", 0), 3),
                "cvd_slope": round(flow.get("cvd_slope", 0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
                "trade_count": flow.get("trade_count", 0),
            } if flow else None,
            "regime": self._classify_regime(df.iloc[-1], df) if df is not None and len(df) > 0 else None,
        }
        try:
            with open("logs/gotAway.jsonl", "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception:
            pass
```

- [ ] **Step 2: Syntax check**

Run: `python3 -c "import bot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: add _log_gotaway method for tracking blocked trades"
```

---

### Task 2: Fix Divergence Gate Bypass

**Files:**
- Modify: `bot.py:1053-1055` (insert standalone divergence check after tape gate block)

The existing tape gate block (lines 1014-1053) is inside `if flow and flow.get("trade_count", 0) > 20:`. Divergence is valid at any volume, so we add a standalone check that runs regardless.

- [ ] **Step 1: Add standalone divergence check after the tape gate block**

Find this exact code at line 1053-1055:
```python
                    if direction == "short" and lt_bias > 0.3:
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — large trade bias {lt_bias:.2f} (whales buying)")
                        continue

                # Apply funding rate strength modifier
```

Insert between the tape gate block closing and the funding rate modifier:

```python
                    if direction == "short" and lt_bias > 0.3:
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — large trade bias {lt_bias:.2f} (whales buying)")
                        continue

                # Standalone divergence check — always active, even when tape gates skipped
                # Divergence = price direction vs CVD direction; valid at any volume
                # When trade_count > 20, the check inside the tape gate block (above) fires first.
                # This is the safety net for low-volume conditions where tape gates are skipped.
                if flow and flow.get("divergence"):
                    _div = flow["divergence"]
                    if direction == "long" and _div == "bearish":
                        self._log_gotaway("divergence_bearish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} LONG blocked — bearish divergence (always-on)")
                        continue
                    if direction == "short" and _div == "bullish":
                        self._log_gotaway("divergence_bullish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} SHORT blocked — bullish divergence (always-on)")
                        continue

                # Apply funding rate strength modifier
```

- [ ] **Step 2: Syntax check**

Run: `python3 -c "import bot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "fix: divergence gate now fires regardless of trade_count (was bypassed when < 20)"
```

---

### Task 3: Add QUIET Regime Gate

**Files:**
- Modify: `bot.py:1131-1135` (insert regime gate after OB gate, before order placement)

- [ ] **Step 1: Add QUIET regime gate after OB gate block**

Find this exact code at lines 1131-1135:
```python
                    if ob_spread > 0.15:
                        logger.info(f"[OB GATE] {symbol} blocked — wide spread {ob_spread:.3f}%")
                        continue

                order = self.exchange.open_long(symbol, margin, price) if direction == "long" else self.exchange.open_short(symbol, margin, price)
```

Insert the regime gate between the OB gate and the order placement:

```python
                    if ob_spread > 0.15:
                        logger.info(f"[OB GATE] {symbol} blocked — wide spread {ob_spread:.3f}%")
                        continue

                # QUIET regime gate — block low-momentum entries
                # QUIET = 5m ADX 20-25, no EMA stack alignment (0% WR in 48hr audit)
                # Allow through if flow CVD strongly confirms the trade direction
                _regime_snap = self._classify_regime(df.iloc[-1], df)
                if _regime_snap.get("label") == "QUIET":
                    _flow_confirms = False
                    if flow and flow.get("trade_count", 0) > 5:
                        if direction == "long" and flow.get("cvd_slope", 0) > 0.2:
                            _flow_confirms = True
                        if direction == "short" and flow.get("cvd_slope", 0) < -0.2:
                            _flow_confirms = True
                    if not _flow_confirms:
                        self._log_gotaway("quiet_regime", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[REGIME GATE] {symbol} {direction.upper()} blocked — QUIET regime "
                                    f"(5m ADX={_regime_snap.get('adx', '?')}) with no flow confirmation")
                        continue

                order = self.exchange.open_long(symbol, margin, price) if direction == "long" else self.exchange.open_short(symbol, margin, price)
```

- [ ] **Step 2: Syntax check**

Run: `python3 -c "import bot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: add QUIET regime gate — blocks 5m ADX 20-25 entries without flow confirmation"
```

---

### Task 4: Add htf_adx to Entry Snapshot

**Files:**
- Modify: `bot.py:1409-1445` (`_log_entry_snapshot` method signature + snapshot dict)
- Modify: `bot.py:1157` (caller — pass htf_adx value)

- [ ] **Step 1: Update `_log_entry_snapshot` to accept and record htf_adx**

Find the method signature at line 1409-1412:
```python
    def _log_entry_snapshot(self, symbol: str, direction: str, slot_id: str,
                            strategy: str, strength: float, price: float,
                            confidence: int, ob: dict | None, flow: dict | None,
                            ohlcv_last=None, ohlcv_df=None) -> dict:
```

Replace with:
```python
    def _log_entry_snapshot(self, symbol: str, direction: str, slot_id: str,
                            strategy: str, strength: float, price: float,
                            confidence: int, ob: dict | None, flow: dict | None,
                            ohlcv_last=None, ohlcv_df=None, htf_adx: float = None) -> dict:
```

Then find the snapshot dict closing at line 1438:
```python
            "regime": self._classify_regime(ohlcv_last, ohlcv_df) if ohlcv_last is not None else None,
        }
```

Replace with:
```python
            "regime": self._classify_regime(ohlcv_last, ohlcv_df) if ohlcv_last is not None else None,
            "htf_adx": round(htf_adx, 1) if htf_adx is not None else None,
        }
```

- [ ] **Step 2: Pass htf_adx from the entry flow to the snapshot**

Find the snapshot call at line 1157:
```python
                    pos.entry_snapshot = self._log_entry_snapshot(symbol, direction, "5m_scalp", strat_name, signal.strength, fill_price, confidence, ob, flow, ohlcv_last=df.iloc[-1], ohlcv_df=df)
```

Replace with (htf_df is available from line 935):
```python
                    _htf_adx_val = float(htf_df.iloc[-1].get("adx", 0)) if htf_df is not None and len(htf_df) > 0 else None
                    pos.entry_snapshot = self._log_entry_snapshot(symbol, direction, "5m_scalp", strat_name, signal.strength, fill_price, confidence, ob, flow, ohlcv_last=df.iloc[-1], ohlcv_df=df, htf_adx=_htf_adx_val)
```

- [ ] **Step 3: Syntax check**

Run: `python3 -c "import bot; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: add htf_adx to entry_snapshot for post-hoc audit of 1h ADX gate"
```

---

### Task 5: Limit-Only Entries (No Market Fallback)

**Files:**
- Modify: `exchange.py:306-401` (replace `_try_limit_then_market` with `_try_limit_entry`)
- Modify: `exchange.py:419` (update caller in `open_long`)
- Modify: `exchange.py:462` (update caller in `open_short`)

- [ ] **Step 1: Replace `_try_limit_then_market` with `_try_limit_entry`**

Find the entire `_try_limit_then_market` method (lines 306-401). Replace it with:

```python
    def _try_limit_entry(self, symbol: str, side: str, amount: float, limit_price: float) -> Optional[dict]:
        """Place limit-only entry order. No market fallback — if unfilled, skip the trade.
        Maker fee = 0.01% vs taker 0.06%. Missing a fill is better than overpaying 6x fees."""
        limit_price = self._round_price(symbol, limit_price)
        order_side = "buy" if side == "long" else "sell"

        try:
            order = self.client.create_order(symbol, "limit", order_side, amount, limit_price, params={"timeInForce": "PostOnly"})
            order_id = order.get("id")
            logger.info(f"[MAKER] Limit {order_side} {amount} {symbol} @ {limit_price} (id={order_id})")

            # Wait up to 5s for fill (10 polls × 0.5s)
            for _ in range(10):
                time.sleep(0.5)
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    status = fetched.get("status", "")
                    if status == "closed":
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER @ {fetched.get('average', limit_price)}")
                        return fetched
                    if status in ("canceled", "cancelled"):
                        # PostOnly rejected (would have crossed spread)
                        logger.info(f"[FILL MISS] {symbol} — PostOnly rejected, skipping entry")
                        return None
                except Exception:
                    pass

            # Not filled — cancel and skip (no market fallback)
            try:
                self.client.cancel_order(order_id, symbol)
                # Check for race: filled between our last poll and cancel
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER @ {fetched.get('average', limit_price)} (raced cancel)")
                        return fetched
                    filled_amount = float(fetched.get("filled", 0) or 0)
                    if filled_amount > 0:
                        # Partial fill — keep it, don't chase remainder with market
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER partial {filled_amount}/{amount}")
                        return fetched
                except Exception:
                    pass
            except Exception:
                # Cancel failed — check if filled
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        return fetched
                except Exception:
                    pass

            logger.info(f"[FILL MISS] {symbol} {order_side} — limit not filled in 5s, skipping entry")
            return None

        except Exception as e:
            logger.warning(f"[FILL MISS] {symbol} — limit order failed: {e}, skipping entry")
            return None
```

- [ ] **Step 2: Update `open_long` caller**

Find at line 419:
```python
        return self._try_limit_then_market(symbol, "long", amount, limit_price)
```

Replace with:
```python
        return self._try_limit_entry(symbol, "long", amount, limit_price)
```

- [ ] **Step 3: Update `open_short` caller**

Find at line 462:
```python
        return self._try_limit_then_market(symbol, "short", amount, limit_price)
```

Replace with:
```python
        return self._try_limit_entry(symbol, "short", amount, limit_price)
```

- [ ] **Step 4: Syntax check**

Run: `python3 -c "import exchange; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add exchange.py
git commit -m "feat: limit-only entries, no market fallback — eliminates taker fees on entries"
```

---

### Task 6: Extend Exit Limit Wait

**Files:**
- Modify: `exchange.py:487-520` (`_try_limit_exit` method)

- [ ] **Step 1: Extend limit exit wait from 2s to 4s**

Find the poll loop at line 496:
```python
            for _ in range(4):  # 2s total
```

Replace with:
```python
            for _ in range(8):  # 4s total — more time for maker fill on exits
```

- [ ] **Step 2: Syntax check**

Run: `python3 -c "import exchange; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add exchange.py
git commit -m "feat: extend exit limit wait 2s→4s for better maker fill rate"
```

---

### Task 7: Pre-Restart Audit + Deploy

**Files:** None (verification only)

- [ ] **Step 1: Full syntax check**

Run: `python3 -c "import bot; import exchange; print('ALL OK')"`
Expected: `ALL OK`

- [ ] **Step 2: Clear pycache**

Run: `rm -rf __pycache__`

- [ ] **Step 3: Run `/pre-restart-audit`**

This deploys review agents to check all changes for issues before restart.

- [ ] **Step 4: Verify no open positions before restart**

Run: `python3 -c "import json; s=json.load(open('trading_state.json')); print('Open positions:', len(s.get('positions', [])))"`
Expected: `Open positions: 0`

- [ ] **Step 5: Stop the bot**

Run: `kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null`

- [ ] **Step 6: Restart with new code**

Run:
```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
```

- [ ] **Step 7: Verify bot started and new gates active**

Run: `tail -20 logs/bot.log`
Expected: Bot startup messages, no errors.

Run: `sleep 120 && grep -c "DIVERGENCE GATE\|REGIME GATE\|FILL MISS\|FILL.*MAKER" logs/bot.log`
Expected: Non-zero counts after a few cycles (gates logging blocked trades or maker fills).
