import os

# Route ALL test logging away from the live bot.log. Mocked order lines
# ("[SL-MOVE] amend BTC @ 99.0 ... rejected") landing in bot.log read exactly
# like live order activity and nearly caused a false live-incident diagnosis
# on 2026-06-11. Must be set before any project module imports setup_logger().
os.environ.setdefault("PHMEX_LOG_FILE", "logs/test_run.log")
