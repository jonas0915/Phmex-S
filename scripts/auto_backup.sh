#!/bin/zsh
# Hourly auto-commit + push of tracked changes (launchd: com.phmex.auto-backup).
# GitHub is the off-machine backup for code/state; .env and logs/ stay local
# by design (.gitignore) — never force-add them here.
set -u
cd /Users/jonaspenaso/Desktop/Phmex-S || exit 1
LOG=/Users/jonaspenaso/Library/Logs/Phmex-S/auto_backup.log

# Stale-lock guard: skip this run if another git process is genuinely active;
# remove the lock only if it is older than 10 minutes (known crashed-git issue).
if [ -f .git/index.lock ]; then
  if [ -n "$(find .git/index.lock -mmin +10 2>/dev/null)" ]; then
    rm -f .git/index.lock
    echo "$(date) removed stale index.lock" >> "$LOG"
  else
    echo "$(date) index.lock fresh — skipping run" >> "$LOG"
    exit 0
  fi
fi

git add -A
if git diff --cached --quiet; then
  exit 0  # nothing to back up
fi
git commit -q -m "chore(auto-backup): $(date '+%Y-%m-%d %I:%M %p %Z')" \
  && git push -q origin main >> "$LOG" 2>&1 \
  && echo "$(date) pushed OK" >> "$LOG" \
  || echo "$(date) commit/push FAILED (will retry next hour)" >> "$LOG"
