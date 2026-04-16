---
name: Always verify PID lock before assuming bot is dead
description: Phmex-S has a PID lockfile guard at startup — a stale .bot.pid OR a still-alive process will block restarts; always check ps + .bot.pid before declaring "bot is dead"
type: feedback
---

When debugging a "broken" Phmex-S bot, do not trust a single `ps aux` snapshot. The bot has a PID lockfile (`.bot.pid`) that prevents double-starts at startup with the message "Another bot instance is already running (PID X). Exiting."

**Why:** On 2026-04-06 I ran `ps aux | grep "python.*main.py"` and saw nothing, concluded the bot was "dead", and presented a restart proposal. In reality the bot was alive (PID 12694) — the grep had race-condition-missed it. When I attempted restart, the new process aborted on PID lock and the OLD buggy process kept running. The verification agent caught this only on the post-restart check, after I had already presented two false summaries.

**How to apply (always do these THREE checks together):**
1. `ps aux | grep -i "python.*main\.py" | grep -v grep` — process check
2. `cat .bot.pid` — what does the lockfile claim
3. `tail -5 logs/bot.log` — is anything still being logged?

If ANY of the three shows life, the bot is alive. Don't restart with the lockfile in place — kill the existing PID first, remove `.bot.pid`, then start fresh:
```bash
kill <pid> && sleep 2 && rm .bot.pid && nohup ... main.py >> logs/bot.log 2>&1 &
```

Also: when running smoke-test agents post-restart, have them check the new PID matches what `ps aux` reports — not the PID we *think* we started. The agent caught this exact mistake.
