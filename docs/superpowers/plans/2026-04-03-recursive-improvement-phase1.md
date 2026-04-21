# Recursive Improvement Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bot auto-kills, auto-promotes, auto-rollbacks paper/live slots, accepts phone commands via Telegram, and logs entry snapshots — Jonas goes hands-off.

**Architecture:** Filesystem-based IPC via sentinel files. Three new scripts (auto_lifecycle, telegram_commander, entry snapshot logging in bot.py). Bot.py checks for sentinel files at the top of each cycle. Monitor daemon handles `.restart_bot` sentinel. All scheduled via launchd.

**Tech Stack:** Python 3.14, ccxt, python-telegram-bot, launchd, existing recalibration.py + strategy_factory.py infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-02-recursive-improvement-phase1-design.md`

**Deploy After:** 2026-04-07 (Sentinel 5-day A/B eval ends Apr 6)

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `scripts/auto_lifecycle.py` | Kill/promote/decay/rollback scanner (runs every 4 hrs via launchd) |
| `scripts/telegram_commander.py` | Telegram bot polling for /status, /kill, /pause, /resume, /slots, /balance |
| `~/Library/LaunchAgents/com.phmex.auto-lifecycle.plist` | launchd job for auto_lifecycle |
| `~/Library/LaunchAgents/com.phmex.telegram-commander.plist` | launchd job for telegram_commander |

### Modified Files
| File | Changes |
|------|---------|
| `bot.py:389-392` | Add sentinel file check at top of `_run_cycle()` (~15 lines) |
| `bot.py:952-953` | Add entry snapshot logging after live order fill (~10 lines) |
| `bot.py:1132-1136` | Add entry snapshot logging after paper slot entry (~10 lines) |
| `scripts/monitor_daemon.py:127-130` | Add `.restart_bot` sentinel check at top of `run_monitor()` (~10 lines) |

---

### Task 1: Entry Snapshot Logging

**Files:**
- Modify: `bot.py:952-953` (after live entry log)
- Modify: `bot.py:1132-1136` (after paper entry log)

This is the simplest component and has zero dependencies. It appends one JSON line per entry to `logs/entry_snapshots.jsonl`.

- [ ] **Step 1: Add snapshot helper function to bot.py**

Add this function to `Phmex2Bot` class, after the `_extract_fill_amount` method (around line 970). Find the line `def _set_cooldown_if_loss` and add before it:

```python
    def _log_entry_snapshot(self, symbol: str, direction: str, slot_id: str,
                            strategy: str, strength: float, price: float,
                            confidence: int, ob: dict | None, flow: dict | None):
        """Append entry conditions snapshot to JSONL for post-hoc analysis."""
        import json as _json
        snapshot = {
            "ts": int(time.time()),
            "symbol": symbol,
            "direction": direction,
            "slot": slot_id,
            "strategy": strategy,
            "strength": round(strength, 3),
            "confidence": confidence,
            "price": round(price, 6),
            "ob": {
                "imbalance": round(ob.get("imbalance", 0), 3),
                "bid_walls": len(ob.get("bid_walls", [])),
                "ask_walls": len(ob.get("ask_walls", [])),
                "spread_pct": round(ob.get("spread_pct", 0), 4),
            } if ob else None,
            "flow": {
                "buy_ratio": round(flow.get("buy_ratio", 0), 3),
                "cvd_slope": round(flow.get("cvd_slope", 0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
                "trade_count": flow.get("trade_count", 0),
            } if flow else None,
        }
        try:
            with open("logs/entry_snapshots.jsonl", "a") as f:
                f.write(_json.dumps(snapshot) + "\n")
        except Exception as e:
            logger.debug(f"[SNAPSHOT] Failed to write: {e}")
```

- [ ] **Step 2: Call snapshot after live entry fill**

In bot.py, find the line (around line 952):
```python
                    logger.info(f"[ENTRY] {direction.upper()} {symbol} | Fill: {fill_price:.4f} | Margin: ${margin:.2f} | Conf: {confidence}/6 | {signal.reason} | Strength: {signal.strength:.2f}")
```

Add immediately after it:
```python
                    self._log_entry_snapshot(symbol, direction, "5m_scalp", strat_name, signal.strength, fill_price, confidence, ob, flow)
```

Note: `ob` and `flow` are already in scope from the gate checks earlier in the same method. `strat_name` is set around line 860.

- [ ] **Step 3: Call snapshot after paper slot entry**

In bot.py, find the paper entry log (around line 1133-1136):
```python
                logger.info(
                    f"[PAPER] {slot.slot_id} ENTRY {direction.upper()} {symbol} | "
                    f"Price: {price:.4f} | Strength: {signal.strength:.2f} | {signal.reason}"
                )
```

Add immediately after it:
```python
                self._log_entry_snapshot(symbol, direction, slot.slot_id, slot.strategy_name, signal.strength, price, 0, None, None)
```

Note: Paper slots don't have OB/flow data or confidence scores, so we pass `0, None, None`.

- [ ] **Step 4: Verify syntax**

Run: `python3 -m py_compile bot.py`
Expected: No errors.

- [ ] **Step 5: Manual test**

Run: `python3 -c "import bot; b = bot.Phmex2Bot(); b._log_entry_snapshot('BTC/USDT:USDT', 'long', 'test', 'confluence', 0.85, 68400.0, 4, {'imbalance': 0.1, 'bid_walls': [], 'ask_walls': [], 'spread_pct': 0.02}, {'buy_ratio': 0.52, 'cvd_slope': 0.1, 'divergence': None, 'large_trade_bias': 0.05, 'trade_count': 45}); print(open('logs/entry_snapshots.jsonl').read())"`

Expected: One JSON line with all fields populated. Then delete the test file: `rm logs/entry_snapshots.jsonl`

- [ ] **Step 6: Commit**

```bash
git add bot.py
git commit -m "feat: entry snapshot logging to logs/entry_snapshots.jsonl"
```

---

### Task 2: Sentinel File Protocol in bot.py

**Files:**
- Modify: `bot.py:389-392` (top of `_run_cycle()`, after ban mode check)

Bot.py must check for sentinel files at the start of each cycle and act on them. Sentinels are one-shot: read, act, delete.

- [ ] **Step 1: Add sentinel processing method to Phmex2Bot**

First, verify `os` and `json` are imported at the top of bot.py. If not, add them. The sentinel method uses `os.path.exists()`, `os.path.getmtime()`, `os.remove()`, and the promote handler uses `json.load()`. Both must be available at module level.

Add this method to the `Phmex2Bot` class, before `_run_cycle()` (around line 388):

```python
    def _process_sentinels(self):
        """Check for sentinel files and act on them. One-shot: read, act, delete."""
        import glob as _glob

        # Global pause
        if os.path.exists(".pause_trading"):
            if not hasattr(self, '_pause_logged') or not self._pause_logged:
                logger.info("[SENTINEL] .pause_trading active — skipping all entries (exits still processed)")
                self._pause_logged = True
            self._trading_paused = True
        else:
            self._trading_paused = False
            self._pause_logged = False

        # Per-slot kills
        for path in _glob.glob(".kill_*"):
            slot_id = path.replace(".kill_", "")
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.enabled = False
                    # Close any open positions for this slot
                    for sym in list(slot.risk.positions.keys()):
                        pos = slot.risk.positions[sym]
                        if pos.side == "long":
                            self.exchange.close_long(sym, pos.amount)
                        else:
                            self.exchange.close_short(sym, pos.amount)
                        self.exchange.cancel_open_orders(sym)
                        logger.info(f"[SENTINEL] Closing {sym} for killed slot {slot_id}")
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' KILLED")
                    notifier.send(f"🔪 Slot <b>{slot_id}</b> killed via sentinel")
                    break
            os.remove(path)

        # Per-slot pauses (auto-expire after 24 hrs)
        for path in _glob.glob(".pause_*"):
            if path == ".pause_trading":
                continue
            slot_id = path.replace(".pause_", "")
            mtime = os.path.getmtime(path)
            if time.time() - mtime > 86400:
                os.remove(path)
                logger.info(f"[SENTINEL] Pause expired for slot '{slot_id}' (24 hrs)")
                continue
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.enabled = False  # re-enabled when pause file removed/expires

        # Promote: paper → live
        for path in _glob.glob(".promote_*"):
            slot_id = path.replace(".promote_", "")
            try:
                with open(path) as f:
                    data = json.load(f)
                capital_pct = data.get("capital_pct", 0.10)
            except Exception:
                capital_pct = 0.10
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.paper_mode = False
                    slot.capital_pct = capital_pct
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' PROMOTED to live at {capital_pct*100:.0f}%")
                    notifier.send(f"🚀 Slot <b>{slot_id}</b> promoted to live ({capital_pct*100:.0f}% capital)")
                    break
            os.remove(path)

        # Demote: live → paper
        for path in _glob.glob(".demote_*"):
            slot_id = path.replace(".demote_", "")
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.paper_mode = True
                    slot.capital_pct = 0.0
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' DEMOTED to paper")
                    notifier.send(f"⬇️ Slot <b>{slot_id}</b> demoted to paper")
                    break
            os.remove(path)

        return None
```

- [ ] **Step 2: Call sentinel processing at top of _run_cycle()**

In bot.py `_run_cycle()`, find the line after the ban mode block ends (around line 422, after `notifier.notify_ban_lifted()`). There should be a blank line, then:
```python
        self.cycle_count += 1
```

Add sentinel check BEFORE the cycle count increment:
```python
        self._process_sentinels()

```

Then, add a pause guard before the entry loop (around line 695 where `for symbol in self.active_pairs:` begins). This lets the normal exit processing run but skips all entries:
```python
        if getattr(self, '_trading_paused', False):
            return  # exits already processed above, skip entries
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -m py_compile bot.py`
Expected: No errors.

- [ ] **Step 4: Manual test**

```bash
# Create a test pause sentinel
touch .pause_trading
python3 -c "
import bot
b = bot.Phmex2Bot()
b._process_sentinels()
print(f'Paused: {b._trading_paused}')  # Should print: Paused: True
"
rm .pause_trading
```

- [ ] **Step 5: Commit**

```bash
git add bot.py
git commit -m "feat: sentinel file protocol — pause/kill/promote/demote slots via filesystem"
```

---

### Task 3: Monitor Daemon — .restart_bot Sentinel

**Files:**
- Modify: `scripts/monitor_daemon.py:127-130` (top of `run_monitor()`)

- [ ] **Step 1: Add restart sentinel check at top of run_monitor()**

In `scripts/monitor_daemon.py`, find `def run_monitor():` (line 127). After `alerts = []` (line 129), add:

```python
    # Check for restart sentinel (from auto_lifecycle rollback)
    restart_sentinel = os.path.join(BOT_DIR, ".restart_bot")
    if os.path.exists(restart_sentinel):
        import subprocess
        tg_send("🔄 <b>Restarting bot</b> — auto-rollback triggered restart")
        # Kill current bot
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "Python main.py" in line and "grep" not in line:
                pid = int(line.split()[1])
                subprocess.run(["kill", "-9", str(pid)], check=False)
        import time as _time
        _time.sleep(3)
        # Restart bot
        subprocess.Popen(
            ["/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python", "main.py"],
            cwd=BOT_DIR,
            stdout=open(os.path.join(BOT_DIR, "logs", "bot.log"), "a"),
            stderr=subprocess.STDOUT,
        )
        os.remove(restart_sentinel)
        tg_send("✅ <b>Bot restarted</b> successfully")
        print(f"[{now.strftime('%H:%M')}] Restart sentinel processed — bot restarted")
        return  # Skip normal monitoring this cycle
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile scripts/monitor_daemon.py`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/monitor_daemon.py
git commit -m "feat: monitor daemon handles .restart_bot sentinel for auto-rollback"
```

---

### Task 4: Telegram Commander

**Files:**
- Create: `scripts/telegram_commander.py`

- [ ] **Step 1: Install python-telegram-bot**

```bash
pip3 install python-telegram-bot
```

Expected: Successfully installed python-telegram-bot-X.X.X

- [ ] **Step 2: Create telegram_commander.py**

Create `scripts/telegram_commander.py`:

```python
#!/usr/bin/env python3
"""
Telegram Commander — phone-based control for Phmex-S.
Separate daemon, polls for commands, acts via sentinel files.

Usage: python scripts/telegram_commander.py
"""
import json
import os
import sys
import logging
from datetime import datetime

# Setup paths
BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)
os.chdir(BOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BOT_DIR, ".env"))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    filename=os.path.join(BOT_DIR, "logs", "telegram_commander.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# PID file to prevent duplicate instances
PID_FILE = os.path.join(BOT_DIR, ".telegram_commander.pid")


def check_auth(update: Update) -> bool:
    """Only respond to authorized chat."""
    return str(update.effective_chat.id) == CHAT_ID


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    try:
        with open(os.path.join(BOT_DIR, "trading_state.json")) as f:
            state = json.load(f)
        positions = state.get("positions", {})
        trades_today = [
            t for t in state.get("closed_trades", [])
            if t.get("closed_at", 0) > datetime.utcnow().replace(hour=0, minute=0, second=0).timestamp()
        ]
        pnl_today = sum(t.get("pnl_usdt", 0) for t in trades_today)
        wins = sum(1 for t in trades_today if t.get("pnl_usdt", 0) > 0)

        pos_str = ""
        if positions:
            for sym, p in positions.items():
                pos_str += f"\n  {p.get('side','?').upper()} {sym} @ {p.get('entry_price',0):.4f}"
        else:
            pos_str = "\n  None"

        msg = (
            f"📊 <b>Status</b>\n"
            f"Open positions:{pos_str}\n"
            f"Today: {len(trades_today)} trades ({wins}W/{len(trades_today)-wins}L)\n"
            f"PnL: ${pnl_today:+.2f}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    try:
        with open(os.path.join(BOT_DIR, "trading_state.json")) as f:
            state = json.load(f)
        peak = state.get("peak_balance", 0)
        # Parse balance from most recent STATS line in bot log
        balance = 0
        log_path = os.path.join(BOT_DIR, "logs", "bot.log")
        if os.path.exists(log_path):
            import re
            with open(log_path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 50000))  # read last 50KB
                lines = f.read().decode("utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                m = re.search(r'Balance: ([\d.]+) USDT', line)
                if m:
                    balance = float(m.group(1))
                    break
        dd = ((peak - balance) / peak * 100) if peak > 0 and balance > 0 else 0
        msg = f"💰 Balance: ${balance:.2f} | Peak: ${peak:.2f} | DD: {dd:.1f}%"
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    try:
        import glob
        msg = "📋 <b>Slots</b>\n"
        for path in sorted(glob.glob(os.path.join(BOT_DIR, "trading_state_*.json"))):
            slot_name = os.path.basename(path).replace("trading_state_", "").replace(".json", "")
            try:
                with open(path) as f:
                    state = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                msg += f"\n{slot_name}: ERROR ({e})"
                continue
            trades = state.get("closed_trades", [])
            if not trades:
                msg += f"\n{slot_name}: 0 trades"
                continue
            wins = sum(1 for t in trades if t.get("pnl_usdt", 0) > 0)
            pnl = sum(t.get("pnl_usdt", 0) for t in trades)
            wr = wins / len(trades) * 100
            msg += f"\n{slot_name}: {len(trades)} trades | {wr:.0f}% WR | ${pnl:+.2f}"
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /kill <slot_id>")
        return
    slot_id = context.args[0]
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', slot_id):
        await update.message.reply_text("Invalid slot ID. Use alphanumeric and underscores only.")
        return
    sentinel = os.path.join(BOT_DIR, f".kill_{slot_id}")
    with open(sentinel, "w") as f:
        f.write(json.dumps({"killed_by": "telegram", "ts": int(datetime.utcnow().timestamp())}))
    await update.message.reply_text(f"🔪 Kill sentinel written for <b>{slot_id}</b>. Will stop next cycle.", parse_mode="HTML")
    logger.info(f"Kill command for slot: {slot_id}")


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    sentinel = os.path.join(BOT_DIR, ".pause_trading")
    with open(sentinel, "w") as f:
        f.write(json.dumps({"paused_by": "telegram", "ts": int(datetime.utcnow().timestamp())}))
    await update.message.reply_text("⏸ All trading paused. Exits still processed.", parse_mode="HTML")
    logger.info("Pause command received")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    sentinel = os.path.join(BOT_DIR, ".pause_trading")
    if os.path.exists(sentinel):
        os.remove(sentinel)
        await update.message.reply_text("▶️ Trading resumed.", parse_mode="HTML")
    else:
        await update.message.reply_text("Not paused.", parse_mode="HTML")
    logger.info("Resume command received")


def main():
    if not TOKEN or not CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        sys.exit(1)

    # PID file check
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            os.kill(old_pid, 0)  # Check if process exists
            print(f"Commander already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # Stale PID file

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    import signal as _signal
    import atexit

    def _cleanup():
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

    atexit.register(_cleanup)
    _signal.signal(_signal.SIGTERM, lambda sig, frame: sys.exit(0))

    try:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("balance", cmd_balance))
        app.add_handler(CommandHandler("slots", cmd_slots))
        app.add_handler(CommandHandler("kill", cmd_kill))
        app.add_handler(CommandHandler("pause", cmd_pause))
        app.add_handler(CommandHandler("resume", cmd_resume))

        logger.info("Telegram Commander started")
        print("Telegram Commander started. Polling...")
        app.run_polling(drop_pending_updates=True)
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -m py_compile scripts/telegram_commander.py`
Expected: No errors.

- [ ] **Step 4: Manual test (quick start/stop)**

```bash
python3 -c "
import subprocess, time, signal
p = subprocess.Popen(['python3', 'scripts/telegram_commander.py'])
time.sleep(5)
p.send_signal(signal.SIGINT)
p.wait(timeout=5)
print('Commander started and stopped cleanly')
"
tail -3 logs/telegram_commander.log
```

Expected: "Telegram Commander started" in log. Process exits cleanly after SIGINT.

- [ ] **Step 5: Commit**

```bash
git add scripts/telegram_commander.py
git commit -m "feat: Telegram commander — /status /balance /slots /kill /pause /resume"
```

---

### Task 5: Auto-Lifecycle Scanner

**Files:**
- Create: `scripts/auto_lifecycle.py`

This is the most complex component. It imports from `recalibration.py` and `strategy_factory.py`, reads all trading_state_*.json files, and writes sentinel files.

- [ ] **Step 1: Create auto_lifecycle.py**

Create `scripts/auto_lifecycle.py`:

```python
#!/usr/bin/env python3
"""
Auto-Lifecycle Scanner — kill, promote, decay, rollback.
Runs every 4 hours via launchd.

Reads: trading_state_*.json, strategy_factory_state.json, parameter_changelog.json
Writes: sentinel files (.kill_, .pause_, .promote_, .demote_, .restart_bot)
"""
import json
import os
import sys
import time
import glob
import logging
from datetime import datetime

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)
os.chdir(BOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BOT_DIR, ".env"))

from recalibration import compute_metrics, kill_switch_check, edge_decay_check

logging.basicConfig(
    filename=os.path.join(BOT_DIR, "logs", "auto_lifecycle.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Telegram notification (reuse pattern from monitor_daemon)
import requests
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FACTORY_FILE = os.path.join(BOT_DIR, "strategy_factory_state.json")
CHANGELOG_FILE = os.path.join(BOT_DIR, "parameter_changelog.json")
MAX_LIVE_SLOTS = 2


def tg_send(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def load_factory_state():
    if os.path.exists(FACTORY_FILE):
        with open(FACTORY_FILE) as f:
            return json.load(f)
    return {"strategies": {}}


def save_factory_state(state):
    with open(FACTORY_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_slot_trades(slot_id):
    """Load closed trades for a slot from its trading_state file."""
    path = os.path.join(BOT_DIR, f"trading_state_{slot_id}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        state = json.load(f)
    return state.get("closed_trades", [])


def get_live_slot_count(factory_state):
    """Count how many slots are currently in 'live' stage."""
    return sum(1 for s in factory_state.get("strategies", {}).values() if s.get("stage") == "live")


def scan_kills(factory_state):
    """Kill scan: negative Kelly after 50+ trades, or WR < 30% after 25+ trades."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") in ("killed", "retired"):
            continue
        slot_id = info.get("slot_id", name)
        trades = load_slot_trades(slot_id)
        if not trades:
            continue
        metrics = compute_metrics(trades)
        issues = kill_switch_check(metrics)
        if issues:
            sentinel_path = os.path.join(BOT_DIR, f".kill_{slot_id}")
            with open(sentinel_path, "w") as f:
                json.dump({"reason": issues[0], "ts": int(time.time())}, f)
            info["stage"] = "killed"
            info["killed_at"] = int(time.time())
            msg = f"🔪 <b>AUTO-KILL</b>: {slot_id} — {issues[0]}"
            tg_send(msg)
            logger.warning(msg)
            actions.append(f"KILL: {slot_id}")
    return actions


def scan_edge_decay(factory_state):
    """Edge decay scan: 7d WR vs historical, >30% drop → pause 24 hrs."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") in ("killed", "retired"):
            continue
        slot_id = info.get("slot_id", name)
        trades = load_slot_trades(slot_id)
        if not trades:
            continue
        alerts = edge_decay_check(trades)
        if alerts:
            sentinel_path = os.path.join(BOT_DIR, f".pause_{slot_id}")
            if not os.path.exists(sentinel_path):  # Don't overwrite existing pause
                with open(sentinel_path, "w") as f:
                    json.dump({"reason": alerts[0], "ts": int(time.time())}, f)
                msg = f"📉 <b>EDGE DECAY</b>: {slot_id} — {alerts[0]}. Paused 24 hrs."
                tg_send(msg)
                logger.warning(msg)
                actions.append(f"DECAY PAUSE: {slot_id}")
    return actions


def scan_promotions(factory_state):
    """Promote scan: paper slots meeting all criteria → promote to live."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") != "paper":
            continue
        slot_id = info.get("slot_id", name)
        trades = load_slot_trades(slot_id)
        if not trades:
            continue
        metrics = compute_metrics(trades)

        # Check all promotion criteria
        if metrics["trades"] < 50:
            continue
        if metrics["wr"] < 40.0:
            continue
        if metrics["kelly"] <= 0:
            continue
        if metrics["profit_factor"] < 1.1:
            continue
        # max_dd from compute_metrics is absolute dollars — convert to percentage
        total_pnl = metrics["pnl"]
        peak_pnl = total_pnl + metrics["max_dd"]  # peak = current + drawdown from peak
        max_dd_pct = (metrics["max_dd"] / peak_pnl * 100) if peak_pnl > 0 else 0
        if max_dd_pct > 15.0:
            continue

        live_count = get_live_slot_count(factory_state)
        if live_count >= MAX_LIVE_SLOTS:
            # Compare against weakest live slot
            weakest_id, weakest_kelly = None, float("inf")
            for sname, sinfo in factory_state.get("strategies", {}).items():
                if sinfo.get("stage") != "live":
                    continue
                s_slot_id = sinfo.get("slot_id", sname)
                s_trades = load_slot_trades(s_slot_id)
                if s_trades:
                    s_metrics = compute_metrics(s_trades)
                    if s_metrics["kelly"] < weakest_kelly:
                        weakest_kelly = s_metrics["kelly"]
                        weakest_id = s_slot_id
            if weakest_id and metrics["kelly"] > weakest_kelly:
                # Demote weakest
                demote_path = os.path.join(BOT_DIR, f".demote_{weakest_id}")
                with open(demote_path, "w") as f:
                    json.dump({"reason": "replaced by stronger candidate", "ts": int(time.time())}, f)
                for sname, sinfo in factory_state.get("strategies", {}).items():
                    if sinfo.get("slot_id", sname) == weakest_id:
                        sinfo["stage"] = "paper"
                        break
                msg = f"⬇️ <b>AUTO-DEMOTE</b>: {weakest_id} (Kelly {weakest_kelly:.3f}) — replaced by {slot_id}"
                tg_send(msg)
                logger.info(msg)
                actions.append(f"DEMOTE: {weakest_id}")
            else:
                continue  # Can't promote — at cap and candidate isn't better

        # Promote
        promote_path = os.path.join(BOT_DIR, f".promote_{slot_id}")
        with open(promote_path, "w") as f:
            json.dump({"capital_pct": 0.10, "ts": int(time.time())}, f)
        info["stage"] = "live"
        info["promoted_at"] = int(time.time())
        msg = (
            f"🚀 <b>AUTO-PROMOTE</b>: {slot_id} to live at 10%\n"
            f"{metrics['trades']} trades | {metrics['wr']}% WR | "
            f"Kelly {metrics['kelly']:.3f} | PF {metrics['profit_factor']:.2f}"
        )
        tg_send(msg)
        logger.info(msg)
        actions.append(f"PROMOTE: {slot_id}")
        break  # Only promote one slot per scan to avoid exceeding MAX_LIVE_SLOTS

    return actions


def scan_ramps(factory_state):
    """Ramp scan: increase capital for proven live slots."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") != "live":
            continue
        slot_id = info.get("slot_id", name)
        promoted_at = info.get("promoted_at", 0)
        current_pct = info.get("capital_pct", 0.10)

        # Count trades since promotion
        trades = load_slot_trades(slot_id)
        live_trades = [t for t in trades if t.get("closed_at", 0) >= promoted_at]
        profitable = [t for t in live_trades if t.get("pnl_usdt", 0) > 0]

        # Auto-demote FIRST if Kelly turns negative after 25 live trades
        if len(live_trades) >= 25:
            live_metrics = compute_metrics(live_trades)
            if live_metrics["kelly"] < 0:
                demote_path = os.path.join(BOT_DIR, f".demote_{slot_id}")
                with open(demote_path, "w") as f:
                    json.dump({"reason": f"negative Kelly ({live_metrics['kelly']:.3f}) after {len(live_trades)} live trades", "ts": int(time.time())}, f)
                info["stage"] = "paper"
                msg = f"⬇️ <b>AUTO-DEMOTE</b>: {slot_id} — negative Kelly ({live_metrics['kelly']:.3f}) after {len(live_trades)} live trades"
                tg_send(msg)
                actions.append(f"DEMOTE: {slot_id}")
                continue  # Skip ramp — slot is being demoted

        # Ramp up if still healthy
        if len(profitable) >= 50 and current_pct < 0.30:
            info["capital_pct"] = 0.30
            promote_path = os.path.join(BOT_DIR, f".promote_{slot_id}")
            with open(promote_path, "w") as f:
                json.dump({"capital_pct": 0.30, "ts": int(time.time())}, f)
            msg = f"📈 <b>RAMP</b>: {slot_id} → 30% capital ({len(profitable)} profitable trades)"
            tg_send(msg)
            actions.append(f"RAMP 30%: {slot_id}")
        elif len(profitable) >= 25 and current_pct < 0.20:
            info["capital_pct"] = 0.20
            promote_path = os.path.join(BOT_DIR, f".promote_{slot_id}")
            with open(promote_path, "w") as f:
                json.dump({"capital_pct": 0.20, "ts": int(time.time())}, f)
            msg = f"📈 <b>RAMP</b>: {slot_id} → 20% capital ({len(profitable)} profitable trades)"
            tg_send(msg)
            actions.append(f"RAMP 20%: {slot_id}")

    return actions


def scan_rollbacks():
    """Rollback scan: revert parameter changes that caused WR drop."""
    if not os.path.exists(CHANGELOG_FILE):
        return []

    actions = []
    with open(CHANGELOG_FILE) as f:
        changelog = json.load(f)

    now = time.time()
    for entry in changelog:
        changed_at = entry.get("changed_at", 0)
        if now - changed_at > 48 * 3600:
            continue  # Only check changes in last 48 hrs

        pre = entry.get("pre_change_metrics", {})
        param = entry.get("param", "unknown")
        param_source = entry.get("param_source")

        if not param_source:
            msg = f"⚠️ <b>ROLLBACK SKIPPED</b>: {param} — missing param_source"
            tg_send(msg)
            logger.warning(msg)
            continue

        # Load current metrics (last 20 trades from main state)
        trades = []
        try:
            with open(os.path.join(BOT_DIR, "trading_state.json")) as f:
                state = json.load(f)
            trades = state.get("closed_trades", [])[-20:]
        except Exception:
            continue

        if len(trades) < 10:
            continue

        post_metrics = compute_metrics(trades)
        pre_wr = pre.get("wr", 0)

        if pre_wr > 0 and post_metrics["wr"] < pre_wr * 0.85:
            # 15%+ WR drop — rollback
            old_value = entry.get("old_value")
            new_value = entry.get("new_value")
            source_key = entry.get("param_source_key", param)

            if param_source == "env":
                if not _rollback_env(source_key, old_value):
                    tg_send(f"⚠️ <b>ROLLBACK FAILED</b>: {param} — key {source_key} not found in .env")
                    continue
            elif param_source in ("bot_py", "strategies_py"):
                msg = f"⚠️ <b>ROLLBACK NEEDED</b>: {param} {new_value}→{old_value} in {param_source} — manual intervention required"
                tg_send(msg)
                logger.warning(msg)
                actions.append(f"ROLLBACK FLAGGED: {param}")
                continue

            # Write restart sentinel
            restart_path = os.path.join(BOT_DIR, ".restart_bot")
            with open(restart_path, "w") as f:
                json.dump({"reason": f"rollback {param}", "ts": int(time.time())}, f)

            msg = (
                f"🔙 <b>AUTO-ROLLBACK</b>: {param} {new_value}→{old_value}\n"
                f"WR dropped {pre_wr:.0f}% → {post_metrics['wr']:.0f}% in {(now - changed_at)/3600:.0f} hrs"
            )
            tg_send(msg)
            logger.warning(msg)
            actions.append(f"ROLLBACK: {param}")

    return actions


def _rollback_env(key, value):
    """Update a value in the .env file."""
    env_path = os.path.join(BOT_DIR, ".env")
    if not os.path.exists(env_path):
        return False
    lines = open(env_path).readlines()
    found = False
    with open(env_path + ".tmp", "w") as f:
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                found = True
            else:
                f.write(line)
    if found:
        os.replace(env_path + ".tmp", env_path)
        logger.info(f"Rolled back {key} to {value} in .env")
    else:
        os.remove(env_path + ".tmp")
        logger.warning(f"Rollback failed: {key} not found in .env")
    return found


def main():
    logger.info("=== Auto-Lifecycle scan started ===")
    factory_state = load_factory_state()

    all_actions = []
    all_actions.extend(scan_kills(factory_state))
    all_actions.extend(scan_edge_decay(factory_state))
    all_actions.extend(scan_promotions(factory_state))
    all_actions.extend(scan_ramps(factory_state))
    all_actions.extend(scan_rollbacks())

    if all_actions:
        save_factory_state(factory_state)
        logger.info(f"Actions taken: {', '.join(all_actions)}")
    else:
        logger.info("No actions needed")

    print(f"[{datetime.now().strftime('%H:%M')}] Lifecycle scan complete. {len(all_actions)} actions.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile scripts/auto_lifecycle.py`
Expected: No errors.

- [ ] **Step 3: Verify imports work**

Run: `cd ~/Desktop/Phmex-S && python3 -c "from scripts.auto_lifecycle import load_factory_state, scan_kills; print('OK')"`

If this fails with import issues, run instead: `cd ~/Desktop/Phmex-S && python3 scripts/auto_lifecycle.py`
Expected: "Lifecycle scan complete. 0 actions." (no slots need action yet)

- [ ] **Step 4: Create empty parameter_changelog.json**

The rollback scanner reads `parameter_changelog.json`. For Phase 1, changelog entries are appended manually when parameters change (Phase 2 automates this via Optuna/WFO). Create the empty file so the scanner doesn't skip:

```bash
echo "[]" > parameter_changelog.json
```

**Note on rollback scope:** Auto-rollback of `.env` parameters is fully automated. Rollback of `bot.py` / `strategies.py` parameters only sends a Telegram alert for manual intervention — auto-editing live Python source files is too risky.

- [ ] **Step 5: Commit**

```bash
git add scripts/auto_lifecycle.py parameter_changelog.json
git commit -m "feat: auto-lifecycle scanner — kill/promote/decay/rollback"
```

---

### Task 6: launchd Plist Files

**Files:**
- Create: `~/Library/LaunchAgents/com.phmex.auto-lifecycle.plist`
- Create: `~/Library/LaunchAgents/com.phmex.telegram-commander.plist`

- [ ] **Step 1: Create auto-lifecycle plist**

Create `~/Library/LaunchAgents/com.phmex.auto-lifecycle.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.phmex.auto-lifecycle</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python</string>
        <string>/Users/jonaspenaso/Desktop/Phmex-S/scripts/auto_lifecycle.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S</string>
    <key>StartInterval</key>
    <integer>14400</integer>
    <key>StandardOutPath</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S/logs/auto_lifecycle.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S/logs/auto_lifecycle_error.log</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 2: Create telegram-commander plist**

Create `~/Library/LaunchAgents/com.phmex.telegram-commander.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.phmex.telegram-commander</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python</string>
        <string>/Users/jonaspenaso/Desktop/Phmex-S/scripts/telegram_commander.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S</string>
    <key>StandardOutPath</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S/logs/telegram_commander.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S/logs/telegram_commander_error.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 3: Load plists (DO NOT do this until April 7 deploy date)**

These commands are for deploy day only:
```bash
launchctl load ~/Library/LaunchAgents/com.phmex.auto-lifecycle.plist
launchctl load ~/Library/LaunchAgents/com.phmex.telegram-commander.plist
```

- [ ] **Step 4: Commit plist files**

Note: plists are in ~/Library/LaunchAgents, outside the repo. No git commit needed — just verify they exist.

```bash
ls -la ~/Library/LaunchAgents/com.phmex.*.plist
```

Expected: 4 files (daily-report, monitor, auto-lifecycle, telegram-commander).

---

### Task 7: Integration Verification

- [ ] **Step 1: Full syntax check all modified files**

```bash
cd ~/Desktop/Phmex-S
python3 -m py_compile bot.py && echo "bot.py OK"
python3 -m py_compile notifier.py && echo "notifier.py OK"
python3 -m py_compile scripts/auto_lifecycle.py && echo "auto_lifecycle OK"
python3 -m py_compile scripts/telegram_commander.py && echo "telegram_commander OK"
python3 -m py_compile scripts/monitor_daemon.py && echo "monitor_daemon OK"
```

Expected: All OK.

- [ ] **Step 2: Verify auto_lifecycle dry run**

```bash
cd ~/Desktop/Phmex-S && python3 scripts/auto_lifecycle.py
```

Expected: "Lifecycle scan complete. 0 actions." (no slots currently need kill/promote/decay)

- [ ] **Step 3: Verify sentinel protocol end-to-end**

```bash
cd ~/Desktop/Phmex-S
# Create test sentinel
echo '{"capital_pct": 0.10}' > .promote_test_slot
python3 -c "
import bot
b = bot.Phmex2Bot()
b._process_sentinels()
# Should log: Slot 'test_slot' not found (no matching slot)
print('Sentinel processed and deleted:', not __import__('os').path.exists('.promote_test_slot'))
"
```

Expected: Sentinel file deleted, "True" printed.

- [ ] **Step 4: Verify no trading logic changed**

```bash
git diff HEAD -- bot.py | grep -E "^\+.*(place_order|open_long|open_short|close_position)" | grep -v sentinel | grep -v SENTINEL | head -10
```

Expected: Only the sentinel `close_position` call (for killed slots). No other trading logic changes.

- [ ] **Step 5: Final commit**

```bash
git add bot.py scripts/monitor_daemon.py
git commit -m "feat: recursive improvement Phase 1 — sentinel protocol, entry snapshots, lifecycle, commander"
```
