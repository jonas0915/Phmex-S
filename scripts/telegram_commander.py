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
from datetime import datetime, timezone

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
            if t.get("closed_at", 0) > datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).timestamp()
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
        balance = 0
        log_path = os.path.join(BOT_DIR, "logs", "bot.log")
        if os.path.exists(log_path):
            import re
            with open(log_path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 50000))
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
        f.write(json.dumps({"killed_by": "telegram", "ts": int(datetime.now(timezone.utc).timestamp())}))
    await update.message.reply_text(f"🔪 Kill sentinel written for <b>{slot_id}</b>. Will stop next cycle.", parse_mode="HTML")
    logger.info(f"Kill command for slot: {slot_id}")


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    sentinel = os.path.join(BOT_DIR, ".pause_trading")
    with open(sentinel, "w") as f:
        f.write(json.dumps({"paused_by": "telegram", "ts": int(datetime.now(timezone.utc).timestamp())}))
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


async def cmd_overwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    await update.message.reply_text("🔍 Running Overwatch health check...", parse_mode="HTML")
    logger.info("Overwatch command received")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(BOT_DIR, "scripts", "overwatch.py")],
            capture_output=True, text=True, timeout=120, cwd=BOT_DIR,
        )
        if result.returncode == 0:
            await update.message.reply_text("✅ Overwatch complete — check Telegram for alerts (or silence = all clear).", parse_mode="HTML")
        else:
            await update.message.reply_text(f"⚠️ Overwatch exited with error:\n<pre>{result.stderr[:500]}</pre>", parse_mode="HTML")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⚠️ Overwatch timed out after 2 minutes.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Overwatch failed: {e}", parse_mode="HTML")


def main():
    if not TOKEN or not CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        sys.exit(1)

    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            os.kill(old_pid, 0)
            print(f"Commander already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass

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
        app.add_handler(CommandHandler("overwatch", cmd_overwatch))

        logger.info("Telegram Commander started")
        print("Telegram Commander started. Polling...")
        app.run_polling(drop_pending_updates=True)
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


if __name__ == "__main__":
    main()
