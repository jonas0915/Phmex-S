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
        narrow_path = os.path.join(BOT_DIR, "trading_state_5m_narrow.json")
        for path in sorted(glob.glob(os.path.join(BOT_DIR, "trading_state_*.json"))):
            slot_name = os.path.basename(path).replace("trading_state_", "").replace(".json", "")
            is_narrow = (path == narrow_path)
            try:
                with open(path) as f:
                    state = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                msg += f"\n{slot_name}: ERROR ({e})"
                continue
            trades = state.get("closed_trades", [])
            if is_narrow:
                try:
                    with open(os.path.join(BOT_DIR, "trading_state_5m_narrow_blocked.json")) as bf:
                        bc = json.load(bf) or {}
                except (FileNotFoundError, json.JSONDecodeError):
                    bc = {"blocked_symbol": 0, "blocked_hour": 0, "blocked_ensemble": 0}
                b_sym = bc.get("blocked_symbol", 0)
                b_hr = bc.get("blocked_hour", 0)
                b_ens = bc.get("blocked_ensemble", 0)
                if not trades:
                    msg += (
                        f"\n🧪 NARROW (paper) | 0 trades | "
                        f"blocked: sym={b_sym} hr={b_hr} ens={b_ens}"
                    )
                    continue
                wins = sum(1 for t in trades if t.get("pnl_usdt", 0) > 0)
                pnl = sum(t.get("pnl_usdt", 0) for t in trades)
                wr = wins / len(trades) * 100
                msg += (
                    f"\n🧪 NARROW (paper) | {len(trades)} trades | "
                    f"WR: {wr:.0f}% | PnL: ${pnl:+.2f} | "
                    f"blocked: sym={b_sym} hr={b_hr} ens={b_ens}"
                )
                continue
            if not trades:
                msg += f"\n{slot_name}: 0 trades"
                continue
            wins = sum(1 for t in trades if t.get("pnl_usdt", 0) > 0)
            pnl = sum(t.get("pnl_usdt", 0) for t in trades)
            wr = wins / len(trades) * 100
            msg += f"\n{slot_name}: {len(trades)} trades | {wr:.0f}% WR | ${pnl:+.2f}"
        # If narrow file doesn't exist yet, still surface a zeroed line.
        if not os.path.exists(narrow_path):
            msg += "\n🧪 NARROW (paper) | 0 trades | blocked: sym=0 hr=0 ens=0 (no state file yet)"
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_narrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed NARROW paper slot view — 7/14/30d stats, blocked counts, today's trades."""
    if not check_auth(update):
        return
    from datetime import datetime, timezone, timedelta
    path = os.path.join(BOT_DIR, "trading_state_5m_narrow.json")
    if not os.path.exists(path):
        await update.message.reply_text(
            "🧪 <b>NARROW (paper)</b>\nNo state file yet — slot has not run.\n"
            "blocked: sym=0 hr=0 ens=0",
            parse_mode="HTML",
        )
        return
    try:
        with open(path) as f:
            state = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        await update.message.reply_text(f"Error reading NARROW state: {e}")
        return

    trades = state.get("closed_trades", []) or []
    try:
        with open(os.path.join(BOT_DIR, "trading_state_5m_narrow_blocked.json")) as bf:
            bc = json.load(bf) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        bc = {"blocked_symbol": 0, "blocked_hour": 0, "blocked_ensemble": 0}
    b_sym = bc.get("blocked_symbol", 0)
    b_hr = bc.get("blocked_hour", 0)
    b_ens = bc.get("blocked_ensemble", 0)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _window(days):
        cutoff = (now - timedelta(days=days)).timestamp()
        sel = [t for t in trades if t.get("closed_at", 0) >= cutoff]
        n = len(sel)
        if n == 0:
            return (0, 0.0, 0.0)
        wins = sum(1 for t in sel if t.get("pnl_usdt", 0) > 0)
        pnl = sum(t.get("pnl_usdt", 0) for t in sel)
        wr = wins / n * 100
        return (n, wr, pnl)

    n7, wr7, pnl7 = _window(7)
    n14, wr14, pnl14 = _window(14)
    n30, wr30, pnl30 = _window(30)

    today_trades = [t for t in trades if t.get("closed_at", 0) >= today_start]
    today_pnl = sum(t.get("pnl_usdt", 0) for t in today_trades)
    today_wins = sum(1 for t in today_trades if t.get("pnl_usdt", 0) > 0)

    lines = [
        "🧪 <b>NARROW (paper) — Detailed</b>",
        f"7d:  {n7} trades | WR {wr7:.0f}% | ${pnl7:+.2f}",
        f"14d: {n14} trades | WR {wr14:.0f}% | ${pnl14:+.2f}",
        f"30d: {n30} trades | WR {wr30:.0f}% | ${pnl30:+.2f}",
        "",
        f"<b>Blocked counts</b>: symbol={b_sym} hour={b_hr} ensemble={b_ens}",
        "",
        f"<b>Today</b>: {len(today_trades)} trades "
        f"({today_wins}W/{len(today_trades)-today_wins}L) | ${today_pnl:+.2f}",
    ]
    for t in today_trades[-5:]:
        sym = t.get("symbol", "?")
        side = (t.get("side", "?") or "?").upper()
        pnl = t.get("pnl_usdt", 0)
        reason = t.get("exit_reason") or t.get("reason") or "?"
        lines.append(f"  {side} {sym} | ${pnl:+.2f} | {reason}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


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


async def cmd_gates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top gate rejection reasons from last 24h."""
    if not check_auth(update):
        return
    import re as _re
    from datetime import datetime, timedelta, timezone
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
        await update.message.reply_text("bot\u00b7log not found")
        return
    if not counts:
        await update.message.reply_text("No gate rejections in last 24h")
        return
    total = sum(counts.values())
    lines_out = [f"\U0001f6ab Gate Blocks (24h) \u2014 {total:,} total\n"]
    for label, cnt in sorted(counts.items(), key=lambda x: -x[1])[:8]:
        pct = cnt / total * 100
        lines_out.append(f"  {label}: {cnt:,} ({pct:.0f}%)")
    await update.message.reply_text("\n".join(lines_out))


async def cmd_fees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fee total today + reconcile CLEAN streak."""
    if not check_auth(update):
        return
    from datetime import datetime, timezone
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
    rec_log = os.path.expanduser("~/Library/Logs/Phmex-S/reconcile.log")
    streak = 0
    try:
        with open(rec_log, "r", errors="replace") as fh:
            lines_r = fh.readlines()
        for line in reversed(lines_r):
            if "Total discrepancies: 0" in line or "CLEAN" in line:
                streak += 1
            else:
                break
    except FileNotFoundError:
        streak = -1
    streak_str = f"{streak} CLEAN" if streak >= 0 else "log not found"
    await update.message.reply_text(f"\U0001f4b8 Fees\nToday: ${fee_today:.4f}\nReconcile streak: {streak_str}")


async def cmd_drift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Last reconcile run result + drift alerts."""
    if not check_auth(update):
        return
    import re as _re
    from datetime import datetime, timedelta, timezone
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
        await update.message.reply_text("reconcile\u00b7log not found")
        return
    if not results:
        await update.message.reply_text("No reconcile runs in last 24h")
        return
    msg = "\U0001f50d Reconcile (24h)\n" + "\n".join(r[:100] for r in results[-5:])
    await update.message.reply_text(msg)


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
        app.add_handler(CommandHandler("narrow", cmd_narrow))
        app.add_handler(CommandHandler("kill", cmd_kill))
        app.add_handler(CommandHandler("pause", cmd_pause))
        app.add_handler(CommandHandler("resume", cmd_resume))
        app.add_handler(CommandHandler("overwatch", cmd_overwatch))
        app.add_handler(CommandHandler("gates", cmd_gates))
        app.add_handler(CommandHandler("fees", cmd_fees))
        app.add_handler(CommandHandler("drift", cmd_drift))

        logger.info("Telegram Commander started")
        print("Telegram Commander started. Polling...")
        app.run_polling(drop_pending_updates=True)
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


if __name__ == "__main__":
    main()
