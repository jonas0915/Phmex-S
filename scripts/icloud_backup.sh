#!/bin/zsh
# Daily backup of data GitHub does NOT cover, to iCloud Drive
# (launchd: com.phmex.icloud-backup, 5:13 AM daily).
# Time Machine destination failed to mount as of 2026-06-11 — this is currently
# the ONLY off-machine copy of these paths. .env is deliberately EXCLUDED
# (secrets belong in the password manager, not cloud-synced plaintext).
set -u
DEST="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Backups/$(hostname -s)"
LOG="$HOME/Library/Logs/Phmex-S/icloud_backup.log"
mkdir -p "$DEST"
echo "=== backup run $(date) ===" >> "$LOG"

run_rsync() {  # src dest-subdir
  rsync -a \
    --exclude 'venv' --exclude '.venv' --exclude 'node_modules' \
    --exclude '__pycache__' --exclude '.git' --exclude '.DS_Store' \
    --exclude 'l2_ticks' \
    "$1" "$DEST/$2/" >> "$LOG" 2>&1 \
    && echo "OK   $1" >> "$LOG" || echo "FAIL $1" >> "$LOG"
}

run_rsync "$HOME/Desktop/Phmex-S/logs"        "phmex-s"
run_rsync "$HOME/Desktop/.remember"           "desktop"
run_rsync "$HOME/.claude/projects"            "claude-memory"
run_rsync "$HOME/Desktop/ClaudeBot"           "claudebot"
# launchd job definitions (tiny, plain xml)
rsync -a "$HOME/Library/LaunchAgents/" "$DEST/launchagents/" >> "$LOG" 2>&1 \
  && echo "OK   LaunchAgents" >> "$LOG" || echo "FAIL LaunchAgents" >> "$LOG"

echo "=== done $(date) ===" >> "$LOG"
