# Ban Recovery Improvement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ban mode recovery smarter — diagnose failures, re-rotate VPN, alert after 60 min stuck.

**Architecture:** Three additions to the existing recovery loop in `bot.py:354-370`. One new notification function in `notifier.py`. No new files. No changes to trading logic.

**Tech Stack:** Python stdlib (`subprocess`, `time`), existing `notifier.py` Telegram helpers.

**Spec:** `docs/superpowers/specs/2026-04-03-ban-recovery-improvement-design.md`

---

### Task 1: Make `_rotate_vpn()` return success/failure

**Files:**
- Modify: `bot.py:58-72`

- [ ] **Step 1: Update `_rotate_vpn()` to return a bool**

Replace the current function at `bot.py:58-72` with:

```python
def _rotate_vpn() -> bool:
    """Disconnect and reconnect ExpressVPN to a new server. Returns True if connected."""
    global _vpn_index
    server = _VPN_SERVERS[_vpn_index % len(_VPN_SERVERS)]
    _vpn_index += 1
    logger.info(f"[VPN] Rotating to {server}...")
    try:
        subprocess.run(["expressvpnctl", "disconnect"], timeout=15, check=False)
        time.sleep(3)
        subprocess.run(["expressvpnctl", "connect", server], timeout=30, check=False)
        time.sleep(5)
        result = subprocess.run(["expressvpnctl", "status"], capture_output=True, text=True, timeout=10)
        status_line = result.stdout.splitlines()[0] if result.stdout else "status unknown"
        logger.info(f"[VPN] {status_line}")
        connected = "Connected" in status_line or "connected" in status_line
        if not connected:
            logger.warning(f"[VPN] Rotation to {server} may have failed — status: {status_line}")
        return connected
    except Exception as e:
        logger.warning(f"[VPN] Rotation failed: {e}")
        return False
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import bot"` from the project root.
Expected: No errors (clean import).

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: _rotate_vpn returns bool to indicate success"
```

---

### Task 2: Add `ban_extensions` counter and diagnostics helper

**Files:**
- Modify: `bot.py:85-89` (init)
- Modify: `bot.py` (add helper function after `_rotate_vpn`)

- [ ] **Step 1: Add `ban_extensions` to `__init__`**

In `bot.py`, after line 87 (`self.ban_mode_until = 0`), add:

```python
        self.ban_extensions = 0
```

- [ ] **Step 2: Add `_diagnose_connectivity()` helper**

Add this function after `_rotate_vpn()` (after line 72), before `class Phmex2Bot`:

```python
def _diagnose_connectivity() -> dict:
    """Quick connectivity diagnosis: network reachable? VPN connected?"""
    diag = {"network": "unknown", "vpn": "unknown"}
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, timeout=5
        )
        diag["network"] = "ok" if result.returncode == 0 else "down"
    except Exception:
        diag["network"] = "down"
    try:
        result = subprocess.run(
            ["expressvpnctl", "status"],
            capture_output=True, text=True, timeout=5
        )
        status = result.stdout.strip() if result.stdout else ""
        if "Connected" in status or "connected" in status:
            diag["vpn"] = "connected"
        elif "Not connected" in status or "not connected" in status:
            diag["vpn"] = "disconnected"
        else:
            diag["vpn"] = status[:50] if status else "unknown"
    except Exception:
        diag["vpn"] = "unknown"
    return diag
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import bot"`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: add ban_extensions counter and connectivity diagnostics"
```

---

### Task 3: Add `notify_ban_stuck()` to notifier

**Files:**
- Modify: `notifier.py:93` (after `notify_ban_lifted`)

- [ ] **Step 1: Add the new notification function**

In `notifier.py`, after `notify_ban_lifted()` (after line 93), add:

```python
def notify_ban_stuck(minutes: int, diag: dict | None = None):
    diag_str = ""
    if diag:
        diag_str = f"\nNetwork: {diag.get('network', '?')} | VPN: {diag.get('vpn', '?')}"
    send(
        f"\u26a0\ufe0f <b>BAN MODE STUCK</b>  [{BOT_NAME}]\n"
        f"Bot stuck in ban mode for {minutes}+ minutes.{diag_str}\n"
        f"Manual check recommended."
    )
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import notifier"`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add notifier.py
git commit -m "feat: add notify_ban_stuck Telegram alert"
```

---

### Task 4: Upgrade the recovery loop

**Files:**
- Modify: `bot.py:354-371` (recovery check in `_run_cycle`)
- Modify: `bot.py:340-345` (5-error ban entry — reset counter)
- Modify: `bot.py:420-427` (OHLCV ban entry — reset counter)

- [ ] **Step 1: Replace the recovery block**

Replace `bot.py` lines 354-371 (the `if self.ban_mode:` block inside `_run_cycle`) with:

```python
        if self.ban_mode:
            if _time_module.time() < self.ban_mode_until:
                return
            # Use WS connectivity check instead of REST endpoint test
            if self._ws_feed and self._ws_feed.is_connected:
                test = True
            else:
                sym = self.active_pairs[0] if self.active_pairs else None
                test = self.exchange.get_ohlcv(sym, Config.TIMEFRAME, limit=5) if sym else None
            if not test or (hasattr(test, '__len__') and len(test) == 0):
                # Diagnose why recovery failed
                diag = _diagnose_connectivity()
                self.ban_extensions += 1
                logger.warning(
                    f"[BAN MODE] Still blocked (extension #{self.ban_extensions}) — "
                    f"network={diag['network']} vpn={diag['vpn']}"
                )
                # Re-rotate VPN every 2 failed recoveries
                if self.ban_extensions % 2 == 0:
                    logger.info(f"[BAN MODE] Re-rotating VPN after {self.ban_extensions} failed recoveries")
                    _rotate_vpn()
                # Telegram escalation after 60 min (6 extensions)
                if self.ban_extensions == 6:
                    notifier.notify_ban_stuck(self.ban_extensions * 10, diag)
                self.ban_mode_until = _time_module.time() + 600
                return
            else:
                self.ban_mode = False
                self.consecutive_errors = 0
                self.ban_extensions = 0
                logger.info("[BAN MODE] Connection restored, resuming trading")
                notifier.notify_ban_lifted()
```

- [ ] **Step 2: Reset `ban_extensions` at the 5-error ban entry**

At `bot.py:340-345`, after `self.ban_mode = True` and before `notifier.notify_ban_mode(10)`, add the reset. The block should become:

```python
                if self.consecutive_errors >= 5:
                    self.ban_mode = True
                    self.ban_mode_until = time.time() + 600
                    self.ban_extensions = 0
                    logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                    self.consecutive_errors = 0
                    notifier.notify_ban_mode(10)
```

- [ ] **Step 3: Reset `ban_extensions` at the OHLCV ban entry**

At `bot.py:420-427`, after `self.ban_mode = True`, add the reset. The block should become:

```python
            if self._empty_price_cycles >= 3:
                self.ban_mode = True
                self.ban_mode_until = time.time() + 600
                self._empty_price_cycles = 0
                self.ban_extensions = 0
                logger.warning("[BAN MODE] All OHLCV fetches failed 3 cycles — CDN ban detected, rotating VPN and pausing 10 min")
                _rotate_vpn()
                notifier.notify_ban_mode(10)
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import bot"`
Expected: No errors.

- [ ] **Step 5: Verify log output format**

Run: `grep -n "BAN MODE" bot.py | head -20`
Expected: All BAN MODE log lines present with correct formatting — no typos, no broken f-strings.

- [ ] **Step 6: Commit**

```bash
git add bot.py
git commit -m "feat: smart ban recovery — diagnostics, VPN re-rotation, Telegram escalation"
```

---

### Task 5: Final verification

- [ ] **Step 1: Full syntax check**

Run: `python3 -c "import bot; import notifier; print('OK')"` 
Expected: Prints `OK`, no errors.

- [ ] **Step 2: Verify no trading logic changed**

Run: `git diff HEAD~4 -- bot.py | grep -E "^\+.*place_order|^\+.*entry|^\+.*signal|^\+.*risk\." | head -10`
Expected: Empty output — no trading-path lines were added.

- [ ] **Step 3: Review the diff end-to-end**

Run: `git diff HEAD~4 -- bot.py notifier.py`
Manually confirm:
- Recovery loop changes are inside `if self.ban_mode:` only
- `_rotate_vpn()` signature changed to return bool
- `_diagnose_connectivity()` added between `_rotate_vpn` and `class Phmex2Bot`
- `notify_ban_stuck()` added after `notify_ban_lifted()` in notifier.py
- `ban_extensions` reset at all 3 locations (init, 5-error entry, OHLCV entry, ban lifted)
