# Ban Mode Recovery Improvement — Design Spec

**Date:** 2026-04-03
**Status:** Draft
**Scope:** bot.py ban mode recovery loop (lines 354-370) + `_rotate_vpn()` (lines 58-72)

## Problem

When the bot enters ban mode (CDN block or connectivity loss), the recovery loop is blind and static:
- Tries one OHLCV fetch every 10 minutes
- Never checks *why* it's failing (network down? VPN disconnected? Phemex-specific?)
- Only rotates VPN once on ban entry, never again during recovery
- `_rotate_vpn()` doesn't verify the VPN actually connected (`check=False`)
- No Telegram alert on repeated failures — bot can be stuck for hours silently
- No max retry count or escalation

**Evidence:** On 2026-04-03 00:01–01:12 UTC, the bot looped in ban mode for 70+ minutes. The VPN rotated once on entry, the new connection kept failing with Phemex error 30000, and the bot re-extended the 10-min pause 7+ times with no intervention.

## Design

Three changes, all scoped to the recovery path. Zero changes to entry logic, signal generation, or trading paths.

### 1. Diagnose Before Extending

Before extending the ban pause, run lightweight diagnostics to classify the failure:

```
On recovery check failure:
  1. Ping 8.8.8.8 (timeout 3s) → network_ok: bool
  2. expressvpnctl status → vpn_connected: bool
  3. Log diagnosis: "[BAN DIAG] network={ok/down} vpn={connected/disconnected/unknown}"
```

This is pure logging — it doesn't change behavior. It tells us (and the logs) *why* recovery is failing, which informs fix #2.

### 2. Re-rotate VPN on Repeated Failures

Add a `ban_extensions` counter. Every 2 consecutive failed recovery checks, rotate VPN to a fresh server.

```
On recovery check failure:
  self.ban_extensions += 1
  if self.ban_extensions % 2 == 0:
      _rotate_vpn()
      # Also verify VPN connected
  extend pause 10 min
```

On ban entry, reset: `self.ban_extensions = 0`
On ban lifted, reset: `self.ban_extensions = 0`

Also fix `_rotate_vpn()` to return success/failure:
- After `expressvpnctl connect`, check `expressvpnctl status` output for "Connected"
- Return `True` if connected, `False` otherwise
- Log the result either way

### 3. Telegram Escalation After 60 Minutes

After 6 ban extensions (60 min stuck), send a one-time Telegram alert:

```
On recovery check failure:
  if self.ban_extensions == 6:
      notifier.notify_ban_stuck(60)
```

Message format:
```
⚠️ BAN MODE STUCK [Phmex-S]
Bot has been in ban mode for 60+ minutes.
Last diagnosis: network={ok/down} vpn={connected/disconnected}
Manual check recommended.
```

Only fires once per ban episode (the `== 6` check, not `>= 6`). The existing `notify_ban_lifted()` already covers the recovery notification.

## Modified Code Sections

| File | Lines | Change |
|------|-------|--------|
| bot.py | 58-72 | `_rotate_vpn()` returns bool, verifies connection |
| bot.py | 85-87 | Add `self.ban_extensions = 0` init |
| bot.py | 354-370 | Add diagnostics, re-rotation, escalation to recovery path |
| bot.py | 420-427 | Reset `ban_extensions = 0` on ban entry |
| notifier.py | ~84-93 | Add `notify_ban_stuck(minutes)` function |

## What Does NOT Change

- Ban entry trigger logic (3 empty OHLCV cycles)
- Ban entry from 5 consecutive errors
- 10-minute pause duration
- OHLCV/WS recovery test
- Any trading path, signal, or position management code
- Ban lifted notification

## Risk Assessment

**Risk: None.** All changes are inside the already-broken recovery loop. The bot can't trade while in ban mode, so nothing is disrupted. Worst case: diagnostics add ~3s per recovery check, same outcome as today.

## Testing

- Syntax check: `python3 -c "import bot"`
- Log verification: trigger ban mode manually (disconnect VPN), confirm diagnostics appear in logs
- Telegram verification: confirm `notify_ban_stuck` message arrives after simulated 6 extensions
