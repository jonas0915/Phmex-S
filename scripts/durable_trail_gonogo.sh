#!/bin/zsh
# One-time durable-trail GO/NO-GO analysis runner (launchd: com.phmex.gonogo-durable-trail)
# Scheduled 2026-06-11 for 2026-06-23 11:43 AM ET (8:43 AM PT). Safe to re-run manually.
set -u
cd /Users/jonaspenaso/Desktop/Phmex-S || exit 1
PROMPT_FILE=scripts/durable_trail_gonogo_prompt.md
LOG=/Users/jonaspenaso/Library/Logs/Phmex-S/gonogo_durable_trail.log
echo "=== GO/NO-GO run $(date) ===" >> "$LOG"
# Deliberately NO python/shell-exec in the allowlist: this runs unsupervised on the
# machine hosting the live bot. jq covers all JSON counting/grouping/summing read-only.
/Users/jonaspenaso/.local/bin/claude -p "$(cat $PROMPT_FILE)" \
  --allowedTools "Read,Glob,Grep,Write,Bash(jq *),Bash(grep *),Bash(tail *),Bash(head *),Bash(wc *),Bash(ls *)" \
  >> "$LOG" 2>&1
echo "=== exit $? at $(date) ===" >> "$LOG"

# Self-cleanup: one-shot job — drop the LaunchAgent so it never re-fires next June 23.
# bootout terminates this script's process; it MUST be the last line.
rm -f /Users/jonaspenaso/Library/LaunchAgents/com.phmex.gonogo-durable-trail.plist
echo "=== plist removed, booting out label $(date) ===" >> "$LOG"
launchctl bootout "gui/$(id -u)/com.phmex.gonogo-durable-trail"
