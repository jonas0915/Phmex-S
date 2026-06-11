#!/usr/bin/env python3
"""Balance-floor watcher (added 2026-05-30 for the radical-selectivity live experiment).

Reads USDT balance from Phemex (read-only). If balance <= BALANCE_FLOOR (.env, default
50.0), writes .pause_trading in the exact format the live bot reads
(bot.py:476-477 -> "epoch_int\\nreason\\n") so the bot stops opening NEW entries
(exits still process), and sends a Telegram alert.

The reason line starts with "MANUAL" so the existing halt_watcher.py treats it as a
manual halt and LEAVES IT ALONE (no timed auto-clear). A floor breach needs human review.

Reads .env directly (no bot imports), same pattern as scripts/overwatch.py.
Run every 5 min via launchd (com.phmex.floor-watcher).

Usage:
    python scripts/floor_watcher.py            # live: may write pause file
    python scripts/floor_watcher.py --dry-run  # print balance + decision, write nothing
"""
import os
import sys
import time
import logging

import ccxt
import requests
from dotenv import load_dotenv

BOT_DIR = "/Users/jonaspenaso/Desktop/Phmex-S"
PAUSE_FILE = os.path.join(BOT_DIR, ".pause_trading")
LOG_FILE = os.path.join(BOT_DIR, "logs/floor_watcher.log")

load_dotenv(os.path.join(BOT_DIR, ".env"))

API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BALANCE_FLOOR = float(os.getenv("BALANCE_FLOOR", "50.0"))

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [FLOOR-WATCHER] %(message)s",
)


def tg_send(message: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        logging.warning("Telegram creds missing — alert skipped")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        logging.warning(f"tg_send failed: {e}")
        return False


def get_balance():
    """Total USDT balance (read-only). Returns None on API failure so we NEVER
    pause on a transient error — only on a real, observed low balance."""
    try:
        client = ccxt.phemex({
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "swap"},
        })
        bal = client.fetch_balance()
        usdt = bal.get("USDT", {})
        total = usdt.get("total")
        if total is None:
            total = usdt.get("free")
        return float(total) if total is not None else None
    except Exception as e:
        logging.warning(f"get_balance failed (NOT pausing on transient error): {e}")
        return None


def main(dry_run: bool = False) -> int:
    bal = get_balance()
    if bal is None:
        logging.info("Balance unavailable (API error) — no action, retry next run.")
        print("balance: UNAVAILABLE (API error) — no action")
        return 0

    state = "BREACH" if bal <= BALANCE_FLOOR else "OK"
    print(f"balance: ${bal:.2f} | floor: ${BALANCE_FLOOR:.2f} | {state}")

    if bal > BALANCE_FLOOR:
        logging.info(f"Balance ${bal:.2f} > floor ${BALANCE_FLOOR:.2f} — OK.")
        return 0

    if os.path.exists(PAUSE_FILE):
        logging.info(f"Balance ${bal:.2f} <= floor ${BALANCE_FLOOR:.2f}; "
                     f".pause_trading already present — no-op.")
        print("  breach but pause file already present — no-op")
        return 0

    reason = (f"MANUAL BALANCE FLOOR HALT — balance ${bal:.2f} <= floor "
              f"${BALANCE_FLOOR:.2f} (radical-selectivity experiment). Human review required.")

    if dry_run:
        print(f"  [DRY-RUN] would write .pause_trading: {reason}")
        logging.info(f"[DRY-RUN] would pause: {reason}")
        return 0

    try:
        # Match bot.py:477 format exactly: "epoch_int\nreason\n"
        with open(PAUSE_FILE, "w") as f:
            f.write(f"{int(time.time())}\n{reason}\n")
        logging.warning(f"PAUSED trading — {reason}")
        print("  WROTE .pause_trading — bot will stop new entries")
    except Exception as e:
        logging.error(f"Failed to write pause file: {e}")
        return 1

    tg_send(
        f"\U0001f6d1 <b>BALANCE FLOOR HIT</b>\n"
        f"Balance ${bal:.2f} ≤ floor ${BALANCE_FLOOR:.2f}\n"
        f"Trading paused (new entries stopped; exits still run).\n"
        f"Radical-selectivity experiment. Manual review required."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
