# Entry Gate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the entry gate system against bad overnight trades by adding a 2 AM PT time block, a soft tape gate for thin-volume windows, and a divergence cooldown that prevents re-entry immediately after a block.

**Architecture:** All three changes are in `bot.py` only. No new files. Changes are additive — they add blocking logic, they do not modify existing gate thresholds. The divergence cooldown adds one new instance variable to `__init__`.

**Tech Stack:** Python 3.14, bot.py entry loop (~lines 850–1200)

**Spec:** `docs/superpowers/specs/2026-04-16-entry-gate-hardening-design.md`

---

### Task 1: Add 2 AM PT to Time Blocks

**Files:**
- Modify: `bot.py:1086–1097`

- [ ] **Step 1: Edit the time block set and comment**

In `bot.py`, replace lines 1086–1097 with:

```python
                # Time-of-day filter: block entries during toxic PT hours (PDT = UTC-7)
                # Blocked PT hours → UTC (verified Apr 10–16, 417-trade analysis):
                #   2 AM PT   (26% WR/-$4.22 all-time)    → UTC 9
                #   10 AM-1 PM PT (28% WR/-$12.17)        → UTC 17,18,19,20
                #   5-7 PM PT (26% WR/-$16.11)            → UTC 0,1,2
                # Open: 12-2 AM, 3-10 AM, 2-5 PM, 8 PM-12 AM PT
                _BLOCKED_HOURS_UTC = {0, 1, 2, 9, 17, 18, 19, 20}
                _utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
                _pt_hour = (_utc_hour - 7) % 24
                if _utc_hour in _BLOCKED_HOURS_UTC:
                    _pt_label = f"{_pt_hour % 12 or 12}:00 {'AM' if _pt_hour < 12 else 'PM'}"
                    logger.info(f"[TIME BLOCK] {symbol} {direction} skipped — {_pt_label} PT is blocked")
                    continue
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 3: Verify the change is correct**

```bash
grep -n "BLOCKED_HOURS_UTC" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```
Expected: one line containing `{0, 1, 2, 9, 17, 18, 19, 20}`

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: block 2 AM PT (UTC 9) — 26% WR, -\$4.22 all-time"
```

---

### Task 2: Soft Tape Gate for Thin Volume (5–20 trades)

**Files:**
- Modify: `bot.py:1016–1017`

- [ ] **Step 1: Add soft gate inside the tape-skip block**

In `bot.py`, replace lines 1016–1017 with:

```python
                if not (flow and flow.get("trade_count", 0) > 20):
                    logger.info(f"[TAPE GATE SKIP] {symbol} {direction} — low volume (trade_count={flow.get('trade_count', 0) if flow else 'no_flow'}) — tape gates inactive")
                    # Soft gate: even at low volume, block on extreme seller/buyer dominance
                    if flow and 5 <= flow.get("trade_count", 0) <= 20:
                        _soft_ratio = flow.get("buy_ratio", 0.5)
                        if direction == "long" and _soft_ratio < 0.40:
                            logger.info(
                                f"[TAPE GATE SOFT] {symbol} LONG blocked — buy_ratio {_soft_ratio:.0%} "
                                f"(thin tape, {flow.get('trade_count')} trades, sellers overwhelming)")
                            continue
                        if direction == "short" and _soft_ratio > 0.60:
                            logger.info(
                                f"[TAPE GATE SOFT] {symbol} SHORT blocked — buy_ratio {_soft_ratio:.0%} "
                                f"(thin tape, {flow.get('trade_count')} trades, buyers overwhelming)")
                            continue
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 3: Verify the change looks right in context**

```bash
sed -n '1013,1025p' /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```
Expected: shows `if not (flow and ...)` block containing the `TAPE GATE SOFT` logic nested inside.

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: soft tape gate — block buy_ratio <40%/>60% when trade_count 5-20"
```

---

### Task 3: Divergence Gate Cooldown

**Files:**
- Modify: `bot.py:184` (add `__init__` variable)
- Modify: `bot.py:1014` (insert cooldown check before tape gate)
- Modify: `bot.py:1044–1046` (set cooldown in tape gate divergence block)
- Modify: `bot.py:1063–1067` (set cooldown in standalone divergence gate)

- [ ] **Step 1: Add `_divergence_cooldown` to `__init__`**

In `bot.py`, after line 184 (`self._funding_cache = ...`), add:

```python
        self._divergence_cooldown: dict[str, dict] = {}  # symbol -> {"blocked_at": float, "clean_cycles": int}
```

- [ ] **Step 2: Add cooldown check before the tape gate (after line 1013 — the blank line after ensemble skip)**

After the blank line at 1014 (right before the `# Order flow / tape veto` comment), insert:

```python
                # Divergence cooldown — require 3 clean cycles OR 10 min after a divergence block
                if symbol in self._divergence_cooldown:
                    _dc = self._divergence_cooldown[symbol]
                    _dc_elapsed = time.time() - _dc["blocked_at"]
                    if _dc_elapsed >= 600 or _dc["clean_cycles"] >= 3:
                        del self._divergence_cooldown[symbol]  # cooldown expired, allow through
                    else:
                        # Count clean cycles (cycles where divergence is absent for this symbol)
                        if not (flow and flow.get("divergence")):
                            self._divergence_cooldown[symbol]["clean_cycles"] += 1
                        logger.info(
                            f"[DIVERGENCE COOLDOWN] {symbol} {direction} blocked — "
                            f"{_dc['clean_cycles']}/3 clean cycles, {_dc_elapsed:.0f}s elapsed")
                        continue

```

- [ ] **Step 3: Set cooldown in the tape gate divergence block (inside `trade_count > 20`)**

Find the tape gate bearish divergence block. Current lines ~1044–1046:
```python
                    if direction == "long" and divergence == "bearish":
                        logger.info(f"[TAPE GATE] {symbol} LONG blocked — bearish divergence (price up, sellers gaining)")
                        continue
```

Replace with:
```python
                    if direction == "long" and divergence == "bearish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        logger.info(f"[TAPE GATE] {symbol} LONG blocked — bearish divergence (price up, sellers gaining)")
                        continue
```

Find the tape gate bullish divergence block. Current lines ~1047–1049:
```python
                    if direction == "short" and divergence == "bullish":
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — bullish divergence (price down, buyers gaining)")
                        continue
```

Replace with:
```python
                    if direction == "short" and divergence == "bullish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — bullish divergence (price down, buyers gaining)")
                        continue
```

- [ ] **Step 4: Set cooldown in the standalone divergence gate (~lines 1063–1072, now shifted by ~16 lines due to previous insertions)**

Find the standalone divergence gate block (search for `[DIVERGENCE GATE]`). Current code:
```python
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
```

Replace with:
```python
                    if direction == "long" and _div == "bearish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        self._log_gotaway("divergence_bearish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} LONG blocked — bearish divergence (always-on)")
                        continue
                    if direction == "short" and _div == "bullish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        self._log_gotaway("divergence_bullish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} SHORT blocked — bullish divergence (always-on)")
                        continue
```

- [ ] **Step 5: Verify syntax**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 6: Verify all divergence cooldown pieces are present**

```bash
grep -n "divergence_cooldown\|DIVERGENCE COOLDOWN" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```
Expected: 6+ lines — one in `__init__`, one cooldown check block, two `_divergence_cooldown[symbol] =` in tape gate, two `_divergence_cooldown[symbol] =` in standalone gate, and the `[DIVERGENCE COOLDOWN]` log line.

- [ ] **Step 7: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: divergence gate cooldown — 3 clean cycles or 10 min before re-entry"
```

---

### Task 4: Pre-Restart Audit + Restart

- [ ] **Step 1: Run `/pre-restart-audit`**

Invoke the `pre-restart-audit` skill. Do not restart until audit passes.

- [ ] **Step 2: Clear pycache and restart bot**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
kill $(cat .bot.pid) 2>/dev/null; sleep 2
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 3 && cat .bot.pid
```
Expected: new PID printed.

- [ ] **Step 3: Verify all three features active in logs**

```bash
sleep 10 && tail -50 /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | grep -E "TIME BLOCK|TAPE GATE SOFT|DIVERGENCE COOLDOWN|started|cycle"
```
Expected: bot started message + cycle lines. TIME BLOCK, TAPE GATE SOFT, DIVERGENCE COOLDOWN lines will appear when conditions trigger (may not appear in first 10 seconds).

- [ ] **Step 4: Verify no Python errors in first cycle**

```bash
grep -i "error\|traceback\|exception" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: no new errors after restart timestamp.
