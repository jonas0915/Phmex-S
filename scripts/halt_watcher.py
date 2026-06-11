#!/usr/bin/env python3
"""Halt watcher: auto-clears .pause_trading after the documented cooldown elapses.

Rules:
  DAILY LOSS HALT       → clears at next PT midnight (file mtime PT-date != today PT-date)
  CONSECUTIVE LOSS HALT → clears 4 hours after file mtime
  Anything else         → leave alone (manual halt, requires human action)

Run every 5 minutes via launchd (com.phmex.halt-watcher).
"""
import os
import sys
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

PAUSE_FILE = "/Users/jonaspenaso/Desktop/Phmex-S/.pause_trading"
LOG_FILE = "/Users/jonaspenaso/Desktop/Phmex-S/logs/halt_watcher.log"
PT = ZoneInfo("America/Los_Angeles")
CONSECUTIVE_HALT_SECS = 4 * 3600

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [HALT-WATCHER] %(message)s",
)


def main() -> int:
    if not os.path.exists(PAUSE_FILE):
        return 0

    try:
        with open(PAUSE_FILE) as f:
            content = f.read()
    except Exception as e:
        logging.warning(f"Could not read {PAUSE_FILE}: {e}")
        return 1

    lines = content.strip().splitlines()
    reason = lines[1] if len(lines) > 1 else ""
    mtime = os.path.getmtime(PAUSE_FILE)
    file_pt_date = datetime.fromtimestamp(mtime, tz=PT).strftime("%Y-%m-%d")
    today_pt = datetime.now(tz=PT).strftime("%Y-%m-%d")
    age_secs = time.time() - mtime

    should_clear = False
    cleared_reason = ""

    if reason.startswith("DAILY LOSS HALT"):
        if file_pt_date != today_pt:
            should_clear = True
            cleared_reason = f"daily halt from {file_pt_date}, now {today_pt}"
    elif reason.startswith("CONSECUTIVE LOSS HALT"):
        if age_secs >= CONSECUTIVE_HALT_SECS:
            should_clear = True
            cleared_reason = f"consecutive halt age {age_secs/3600:.1f}h >= 4h"
    else:
        logging.info(f"Manual/unknown halt — leaving alone. Reason: {reason!r}")
        return 0

    if should_clear:
        try:
            os.remove(PAUSE_FILE)
            logging.info(f"Cleared .pause_trading ({cleared_reason}). Original reason: {reason!r}")
            return 0
        except Exception as e:
            logging.error(f"Failed to remove {PAUSE_FILE}: {e}")
            return 1
    else:
        logging.info(f"Halt still active ({reason[:60]!r}, age {age_secs/3600:.1f}h, file day {file_pt_date})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
