#!/usr/bin/env python3
"""Catch-up wrapper for daily_report.py.

Runs every 30min via launchd. Re-runs the report if today's file
is missing or older than 2 hours.
"""
import os
import time
from datetime import datetime

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(BOT_DIR, "reports")
MAX_AGE = 7200  # 2 hours in seconds


def needs_report():
    today = datetime.now().strftime("%Y-%m-%d")
    report_file = os.path.join(REPORT_DIR, f"{today}.md")

    if not os.path.exists(report_file):
        return True

    age = time.time() - os.path.getmtime(report_file)
    return age >= MAX_AGE


if __name__ == "__main__":
    if needs_report():
        print(f"[{datetime.now()}] Report stale or missing — running daily_report.py")
        # Import and run directly (same process, no subprocess needed)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "daily_report",
            os.path.join(BOT_DIR, "scripts", "daily_report.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.generate_report()
    else:
        print(f"[{datetime.now()}] Report is fresh — skipping")
