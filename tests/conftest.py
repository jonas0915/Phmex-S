import os

# Route ALL test logging away from the live bot.log. Mocked order lines
# ("[SL-MOVE] amend BTC @ 99.0 ... rejected") landing in bot.log read exactly
# like live order activity and nearly caused a false live-incident diagnosis
# on 2026-06-11. Must be set before any project module imports setup_logger().
os.environ.setdefault("PHMEX_LOG_FILE", "logs/test_run.log")

# Blank Telegram credentials for the WHOLE suite. notifier.send() reads env at
# call time and no-ops on empty token/chat — without this, tests that exercise
# alert paths (e.g. slot durable-SL amend failure with the fake XLM@$101.20
# position) send REAL pushes on every suite run, including the daily 7:30 AM
# code-health job (spammed Jonas until 2026-07-06). load_dotenv() does not
# override pre-existing env keys, so these empty strings win over .env.
os.environ["TELEGRAM_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
