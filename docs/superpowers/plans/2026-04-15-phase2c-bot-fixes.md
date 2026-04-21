# Phase 2c + Bot Fixes (C2/C3/I9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three live-bot bugs (C2/C3/I9), lock down the dashboard to localhost, and ship Phase 2c observability panels to web_dashboard.py + telegram_commander.py.

**Architecture:** Bot fixes are isolated line changes in bot.py/exchange.py — one change per file, no cross-file ripple. Dashboard and Telegram changes are additive read-only panels; they share a single helper function that parses bot.log so the two surfaces stay in sync. Bot restart required only for C2/C3/I9; dashboard and telegram_commander reload independently.

**Tech Stack:** Python 3.14, ccxt, python-telegram-bot, stdlib http.server (dashboard), bot.log parsing via regex

---

## File Map

| File | Change |
|---|---|
| `web_dashboard.py:42` | HOST `0.0.0.0` → `127.0.0.1` |
| `bot.py:1419-1424` | C2: wrap CVD slope gate in strategy carve-out |
| `exchange.py:225` | I9: normalize cvd_slope by total volume |
| `bot.py:1676-1693` | C3: filter fetch_my_trades to post-entry timestamps |
| `web_dashboard.py` | Add `_gate_stats()` helper + Gates panel + Reconcile panel |
| `scripts/telegram_commander.py` | Add `/gates`, `/fees`, `/drift` command handlers |

---

## Task 1: Dashboard Lockdown

**Files:**
- Modify: `web_dashboard.py:42`

- [ ] **Step 1: Apply the 1-line fix**

Change line 42 from:
```python
HOST = "0.0.0.0"
```
to:
```python
HOST = "127.0.0.1"
```

- [ ] **Step 2: Verify the docstring already says 127.0.0.1**

Check line 7 reads:
```
Open:   http://127.0.0.1:8050
```
It does. No docstring change needed.

- [ ] **Step 3: Commit**

```bash
cd ~/Desktop/Phmex-S
git add web_dashboard.py
git commit -m "fix: lock dashboard to 127.0.0.1 (Phase 2c prereq)"
```

---

## Task 2: C2 — Paper Slot CVD Slope Carve-out

**Files:**
- Modify: `bot.py:1419-1424`

**Context:** Live bot at line 1037 exempts `htf_confluence_pullback` and `bb_mean_reversion` from the CVD slope gate because pullbacks have negative CVD by definition. The paper slot at lines 1419-1424 applies CVD slope to ALL strategies — no carve-out. Paper slots running bb_mean_reversion are incorrectly blocked.

- [ ] **Step 1: Extract strategy name before the CVD slope check**

Replace lines 1419-1424:
```python
                    if direction == "long" and cvd_slope < -0.3:
                        logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — CVD slope {cvd_slope:.2f}")
                        continue
                    if direction == "short" and cvd_slope > 0.3:
                        logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — CVD slope {cvd_slope:.2f}")
                        continue
```

With:
```python
                    # CVD slope gate — carve-out for pullback/reversion (matches live bot line 1037)
                    _paper_strat = self._extract_strategy_name(signal.reason)
                    if _paper_strat not in ("htf_confluence_pullback", "bb_mean_reversion"):
                        if direction == "long" and cvd_slope < -0.3:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — CVD slope {cvd_slope:.2f}")
                            continue
                        if direction == "short" and cvd_slope > 0.3:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — CVD slope {cvd_slope:.2f}")
                            continue
```

- [ ] **Step 2: Verify `_extract_strategy_name` is accessible here**

It's a method on `self` (Bot class). Grep to confirm:
```bash
grep -n "_extract_strategy_name" bot.py | head -5
```
Expected: at least one `def _extract_strategy_name` and usages elsewhere on `self`.

- [ ] **Step 3: Syntax check**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

---

## Task 3: I9 — Normalize REST CVD Slope

**Files:**
- Modify: `exchange.py:225`

**Context:** `get_cvd()` computes `cvd_slope = second_half_avg - first_half_avg` in raw USD values (e.g. ±$50,000 for BTC). The gate threshold is ±0.3. Without normalization, the REST CVD slope is 9 orders of magnitude larger than the WS normalized value — the gate fires constantly on REST data. Fix: divide by total traded volume to get a [-1, +1] normalized slope.

- [ ] **Step 1: Apply normalization**

Replace line 225:
```python
            cvd_slope = second_half_avg - first_half_avg
```

With:
```python
            total_volume = sum(
                abs(t.get("amount", 0) * t.get("price", 0)) for t in trades
            )
            cvd_slope = (second_half_avg - first_half_avg) / total_volume if total_volume > 0 else 0.0
```

- [ ] **Step 2: Syntax check**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile exchange.py && echo "OK"
```
Expected: `OK`

---

## Task 4: C3 — Fix _sync_exchange_closes Fee-Match Race

**Files:**
- Modify: `bot.py:1676-1693`

**Context:** When a position disappears from exchange (SL/TP fired), the bot calls `fetch_my_trades(symbol, limit=10)` and takes `recent[-1]`. Race: if the SL/TP just fired, `recent[-1]` may still be the ENTRY trade, not the exit trade. This gives the wrong exit price AND charges the wrong fee. Fix: filter trades to those timestamped after `pos.opened_at`.

- [ ] **Step 1: Apply timestamp filter**

Replace lines 1676-1693 (the try block inside `_sync_exchange_closes`):
```python
                    try:
                        recent = self.exchange.client.fetch_my_trades(symbol, limit=10)
                        if recent:
                            last_trade = recent[-1]
                            fill = float(last_trade.get("price", 0))
                            if fill > 0:
                                exit_price = fill
                                logger.info(f"[SYNC] {symbol} real exit fill: {exit_price}")
                            # Sum fees from the most recent reduce-only fill(s)
                            try:
                                fee = last_trade.get("fee") or {}
                                if fee.get("cost") is not None:
                                    sync_fee = abs(float(fee.get("cost") or 0))
                                else:
                                    for f in last_trade.get("fees") or []:
                                        if f.get("cost") is not None:
                                            sync_fee += abs(float(f.get("cost") or 0))
                            except Exception:
                                pass
                    except Exception:
                        pass
```

With:
```python
                    try:
                        recent = self.exchange.client.fetch_my_trades(symbol, limit=10)
                        if recent:
                            # Filter to trades after position entry to avoid picking up the entry fill
                            entry_ts_ms = int(pos.opened_at * 1000)
                            close_trades = [tr for tr in recent if (tr.get("timestamp") or 0) > entry_ts_ms]
                            last_trade = close_trades[-1] if close_trades else None
                            if last_trade:
                                fill = float(last_trade.get("price", 0))
                                if fill > 0:
                                    exit_price = fill
                                    logger.info(f"[SYNC] {symbol} real exit fill: {exit_price}")
                                # Sum fees from the confirmed close trade
                                try:
                                    fee = last_trade.get("fee") or {}
                                    if fee.get("cost") is not None:
                                        sync_fee = abs(float(fee.get("cost") or 0))
                                    else:
                                        for f in last_trade.get("fees") or []:
                                            if f.get("cost") is not None:
                                                sync_fee += abs(float(f.get("cost") or 0))
                                except Exception:
                                    pass
                            else:
                                logger.debug(f"[SYNC] {symbol} no post-entry close trade found yet — using mark price")
                    except Exception:
                        pass
```

- [ ] **Step 2: Confirm `pos.opened_at` exists on Position objects**

```bash
grep -n "opened_at" risk_manager.py | head -10
```
Expected: `opened_at` assigned in `open_position`.

- [ ] **Step 3: Syntax check**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

---

## Task 5: Pre-Restart Audit + Bot Restart

**Files:** None (process management)

- [ ] **Step 1: Run pre-restart audit**

```
/pre-restart-audit
```

All changed files must pass. Do not proceed if audit fails.

- [ ] **Step 2: Clear pycache and restart bot**

```bash
cd ~/Desktop/Phmex-S
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 3
tail -20 logs/bot.log
```

Expected: bot cycles starting, no `SyntaxError` or `ImportError`.

- [ ] **Step 3: Commit bot fixes**

```bash
git add bot.py exchange.py
git commit -m "fix: C2/C3/I9 bot fixes — paper CVD carve-out, sync race, REST CVD normalize"
```

---

## Task 6: Phase 2c — Observability Panels (Dashboard)

**Files:**
- Modify: `web_dashboard.py`

Add two panels to the existing dashboard:
1. **Gates panel** — top rejection reasons from today's bot.log
2. **Reconcile panel** — CLEAN streak + last drift alert

- [ ] **Step 1: Add `_gate_stats()` helper function**

Add this function near the top of web_dashboard.py (after the constants, before the route handlers). Find a suitable insertion point (after the `strip_ansi` function around line 53):

```python
def _gate_stats(log_file: str, max_age_hours: int = 24) -> dict:
    """Parse bot.log for gate rejection counts over the last max_age_hours."""
    import re as _re
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    counts = {}
    gate_pattern = _re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?'
        r'(?:\[TAPE GATE\]|\[OB GATE\]|ENSEMBLE SKIP|time_block|ADX.*?too low|'
        r'low vol|No confluence|Choppy|cooldown|QUIET regime|divergence)',
        _re.IGNORECASE
    )
    label_map = [
        ("TAPE GATE",      "[TAPE GATE]"),
        ("OB GATE",        "[OB GATE]"),
        ("Ensemble <4/7",  "ENSEMBLE SKIP"),
        ("Time block",     "time_block"),
        ("ADX too low",    "ADX"),
        ("Low volume",     "low vol"),
        ("No confluence",  "No confluence"),
        ("Choppy market",  "Choppy"),
        ("Cooldown",       "cooldown"),
        ("QUIET regime",   "QUIET regime"),
        ("Divergence",     "divergence"),
    ]
    try:
        with open(log_file, "r", errors="replace") as fh:
            for line in fh:
                # Fast pre-filter before regex
                if not any(kw.lower() in line.lower() for _, kw in label_map):
                    continue
                # Extract timestamp
                ts_match = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if ts < cutoff:
                            continue
                    except ValueError:
                        pass
                for label, keyword in label_map:
                    if keyword.lower() in line.lower():
                        counts[label] = counts.get(label, 0) + 1
                        break
    except (FileNotFoundError, PermissionError):
        pass
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _reconcile_status(reconcile_log: str, max_age_hours: int = 24) -> dict:
    """Parse reconcile.log for CLEAN streak and last drift message."""
    import re as _re
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    results = []
    try:
        with open(reconcile_log, "r", errors="replace") as fh:
            for line in fh:
                if "Total discrepancies:" not in line and "CLEAN" not in line and "DRIFT" not in line:
                    continue
                ts_match = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if ts >= cutoff:
                            results.append(line.strip())
                    except ValueError:
                        pass
    except (FileNotFoundError, PermissionError):
        return {"streak": 0, "last": "reconcile.log not found", "drifts": []}

    clean_streak = 0
    drifts = []
    for line in reversed(results):
        if "Total discrepancies: 0" in line or "CLEAN" in line:
            clean_streak += 1
        else:
            if drifts or "DRIFT" in line or "discrepanc" in line.lower():
                drifts.append(line)
            break

    last = results[-1] if results else "No reconcile runs in last 24h"
    return {"streak": clean_streak, "last": last, "drifts": drifts[:3]}
```

- [ ] **Step 2: Build `_build_observability_panel()` HTML function**

Add after the helpers:

```python
RECONCILE_LOG = os.path.expanduser("~/Library/Logs/Phmex-S/reconcile.log")

def _build_observability_panel() -> str:
    """Build Phase 2c observability HTML panel."""
    # --- Gates ---
    stats = _gate_stats(LOG_FILE)
    if stats:
        total_blocks = sum(stats.values())
        gate_rows = ""
        for label, count in list(stats.items())[:8]:
            pct = count / total_blocks * 100 if total_blocks else 0
            bar_w = int(pct)
            gate_rows += f"""<tr>
                <td style="padding:4px 8px;font-size:13px">{escape(label)}</td>
                <td style="padding:4px 8px;text-align:right;font-family:monospace">{count:,}</td>
                <td style="padding:4px 8px;text-align:right;color:#888;font-size:12px">{pct:.0f}%</td>
            </tr>"""
        gates_html = f"""
        <div style="margin-bottom:8px;color:#888;font-size:12px">{total_blocks:,} total blocks (last 24h)</div>
        <div class="table-wrap"><table><thead><tr>
            <th>Gate</th><th style="text-align:right">Blocks</th><th style="text-align:right">%</th>
        </tr></thead><tbody>{gate_rows}</tbody></table></div>"""
    else:
        gates_html = '<div style="color:#888;font-size:13px">No gate rejections found in log</div>'

    # --- Reconcile ---
    rec = _reconcile_status(RECONCILE_LOG)
    streak_color = "#4caf50" if rec["streak"] >= 4 else "#ff9800" if rec["streak"] >= 1 else "#f44336"
    streak_label = f'<span style="color:{streak_color};font-weight:700">{rec["streak"]} CLEAN</span>'
    drift_html = ""
    if rec["drifts"]:
        drift_html = "<br>".join(f'<div style="color:#ff9800;font-size:12px">{escape(d)}</div>' for d in rec["drifts"])
    else:
        drift_html = '<div style="color:#4caf50;font-size:12px">No drift in last 24h</div>'

    last_run_html = f'<div style="color:#888;font-size:12px;margin-top:4px">{escape(rec["last"][:120])}</div>'

    return f"""
    <div class="audit-section">
        <h3>Gate Rejection Breakdown (24h)</h3>
        {gates_html}
    </div>
    <div class="audit-section" style="margin-top:12px">
        <h3>Reconcile Status</h3>
        <div style="margin-bottom:8px">Streak: {streak_label}</div>
        {drift_html}
        {last_run_html}
    </div>"""
```

- [ ] **Step 3: Inject panel into the dashboard page**

Find where the dashboard page HTML is assembled (search for `audit-section` or the section that renders the trade breakdown tables). Add a call to `_build_observability_panel()` in that section:

```bash
grep -n "audit-section\|def.*page\|def.*html\|def.*render" web_dashboard.py | head -20
```

Insert `_build_observability_panel()` output into the HTML response at an appropriate location (after the paper slot section or before the trade log). The exact insertion point depends on the page structure found above.

- [ ] **Step 4: Syntax check**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile web_dashboard.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 5: Restart dashboard and verify panels load**

```bash
pkill -f "web_dashboard" 2>/dev/null; sleep 1
cd ~/Desktop/Phmex-S
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python web_dashboard.py &
sleep 2
curl -s http://127.0.0.1:8050 | grep -c "Gate Rejection"
```
Expected: `1` (panel heading found)

- [ ] **Step 6: Commit**

```bash
git add web_dashboard.py
git commit -m "feat(2c): add gate rejection + reconcile panels to dashboard"
```

---

## Task 7: Phase 2c — Telegram Commands /gates /fees /drift

**Files:**
- Modify: `scripts/telegram_commander.py`

- [ ] **Step 1: Add shared helper imports at top of telegram_commander.py**

After the existing imports, add:
```python
import re as _re
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 2: Add `/gates` command handler**

Add after the existing command handlers (e.g., after `cmd_overwatch`):

```python
async def cmd_gates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top gate rejection reasons from last 24h."""
    if not check_auth(update):
        return
    log_file = os.path.join(BOT_DIR, "logs", "bot.log")
    label_map = [
        ("Tape gate",      "[TAPE GATE]"),
        ("OB gate",        "[OB GATE]"),
        ("Ensemble <4/7",  "ENSEMBLE SKIP"),
        ("Time block",     "time_block"),
        ("ADX too low",    "ADX"),
        ("Low volume",     "low vol"),
        ("No confluence",  "No confluence"),
        ("Choppy",         "Choppy"),
        ("Cooldown",       "cooldown"),
    ]
    counts = {}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        with open(log_file, "r", errors="replace") as fh:
            for line in fh:
                if not any(kw.lower() in line.lower() for _, kw in label_map):
                    continue
                ts_m = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_m:
                    try:
                        ts = datetime.strptime(ts_m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if ts < cutoff:
                            continue
                    except ValueError:
                        pass
                for label, kw in label_map:
                    if kw.lower() in line.lower():
                        counts[label] = counts.get(label, 0) + 1
                        break
    except FileNotFoundError:
        await update.message.reply_text("bot·log not found")
        return
    if not counts:
        await update.message.reply_text("No gate rejections in last 24h")
        return
    total = sum(counts.values())
    lines = [f"🚫 Gate Blocks (24h) — {total:,} total\n"]
    for label, cnt in sorted(counts.items(), key=lambda x: -x[1])[:8]:
        pct = cnt / total * 100
        lines.append(f"  {label}: {cnt:,} ({pct:.0f}%)")
    await update.message.reply_text("\n".join(lines))
```

- [ ] **Step 3: Add `/fees` command handler**

```python
async def cmd_fees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fee total today + reconcile CLEAN streak."""
    if not check_auth(update):
        return
    # Fee total from trading_state.json
    state_file = os.path.join(BOT_DIR, "trading_state.json")
    fee_today = 0.0
    try:
        with open(state_file) as f:
            state = json.load(f)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for t in state.get("closed_trades", []):
            opened = t.get("opened_at", 0)
            if datetime.fromtimestamp(opened, tz=timezone.utc).strftime("%Y-%m-%d") == today_str:
                fee_today += abs(t.get("fees_usdt", 0) or 0)
    except Exception:
        pass
    # Reconcile streak
    rec_log = os.path.expanduser("~/Library/Logs/Phmex-S/reconcile.log")
    streak = 0
    try:
        with open(rec_log, "r", errors="replace") as fh:
            lines = fh.readlines()
        for line in reversed(lines):
            if "Total discrepancies: 0" in line or "CLEAN" in line:
                streak += 1
            else:
                break
    except FileNotFoundError:
        streak = -1
    streak_str = f"{streak} CLEAN" if streak >= 0 else "log not found"
    msg = f"💸 Fees\nToday: ${fee_today:.4f}\nReconcile streak: {streak_str}"
    await update.message.reply_text(msg)
```

- [ ] **Step 4: Add `/drift` command handler**

```python
async def cmd_drift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Last reconcile run result + any drift alerts."""
    if not check_auth(update):
        return
    rec_log = os.path.expanduser("~/Library/Logs/Phmex-S/reconcile.log")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    results = []
    try:
        with open(rec_log, "r", errors="replace") as fh:
            for line in fh:
                if "discrepanc" not in line.lower() and "CLEAN" not in line and "DRIFT" not in line:
                    continue
                ts_m = _re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if ts_m:
                    try:
                        ts = datetime.strptime(ts_m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if ts >= cutoff:
                            results.append(line.strip())
                    except ValueError:
                        pass
    except FileNotFoundError:
        await update.message.reply_text("reconcile·log not found")
        return
    if not results:
        await update.message.reply_text("No reconcile runs in last 24h")
        return
    # Show last 5 results
    msg = "🔍 Reconcile (24h)\n" + "\n".join(r[:100] for r in results[-5:])
    await update.message.reply_text(msg)
```

- [ ] **Step 5: Register handlers in main application setup**

Find where existing handlers are registered (grep for `add_handler`):
```bash
grep -n "add_handler\|CommandHandler" scripts/telegram_commander.py | tail -15
```

Add alongside existing handlers:
```python
app.add_handler(CommandHandler("gates", cmd_gates))
app.add_handler(CommandHandler("fees", cmd_fees))
app.add_handler(CommandHandler("drift", cmd_drift))
```

- [ ] **Step 6: Update `/help` or help text to include new commands**

Find the help text (grep for `/status` or `help`):
```bash
grep -n "status\|help\|Available" scripts/telegram_commander.py | head -10
```

Add the three new commands to the help list.

- [ ] **Step 7: Syntax check**

```bash
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile scripts/telegram_commander.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 8: Restart telegram_commander**

```bash
pkill -f "telegram_commander" 2>/dev/null
sleep 1
cd ~/Desktop/Phmex-S
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python scripts/telegram_commander.py >> logs/telegram_commander.log 2>&1 &
sleep 3
tail -5 logs/telegram_commander.log
```
Expected: `Started polling` or similar startup log line.

- [ ] **Step 9: Commit**

```bash
git add scripts/telegram_commander.py
git commit -m "feat(2c): add /gates /fees /drift commands to Telegram commander"
```

---

## Completion Checklist

- [ ] `web_dashboard.py` bound to `127.0.0.1` — confirmed by `curl http://127.0.0.1:8050` succeeding
- [ ] C2: paper slot no longer blocks `bb_mean_reversion` longs on negative CVD slope
- [ ] C3: `[SYNC]` log shows "no post-entry close trade found yet" when race occurs, instead of using entry price
- [ ] I9: `get_cvd()` returns values in [-1, +1] range — verify with `python3 -c "from exchange import Exchange; ..."`
- [ ] Dashboard gates panel renders with gate counts (or "No gate rejections" if quiet market)
- [ ] Dashboard reconcile panel shows CLEAN streak ≥ 4 (current known streak as of 2026-04-14)
- [ ] `/gates`, `/fees`, `/drift` respond on Telegram
- [ ] All 4 commits landed: dashboard lockdown, bot fixes, dashboard panels, telegram commands
