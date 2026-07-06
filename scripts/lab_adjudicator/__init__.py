"""Lab adjudicator — nightly grader for LIVE forward tests + execution watchdog.

Read-only vs the bot: consumes trading_state*.json, sidecars and logs/bot.log.
Never imports bot.py / risk_manager.py / exchange.py / config.py.
"""
