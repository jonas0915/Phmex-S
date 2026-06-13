#!/usr/bin/env python3
"""Hourly auto-commit + push of tracked changes (launchd: com.phmex.auto-backup).

GitHub is the off-machine backup for code/state; .env and logs/ stay local
by design (.gitignore) — never force-add them here.

Python port of auto_backup.sh (2026-06-12): launchd-spawned /bin/zsh is
TCC-blocked from reading ~/Desktop, so the shell version exited 127 every
run. The framework Python binary holds the disk-access grant (same reason
com.phmex.reconcile and daily-report work), so the job runs as Python now.
"""
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "Desktop" / "Phmex-S"
LOG = Path.home() / "Library" / "Logs" / "Phmex-S" / "auto_backup.log"
GIT = "/usr/bin/git"


def log(msg: str) -> None:
    with open(LOG, "a") as f:
        f.write(f"{datetime.now().strftime('%a %b %d %I:%M:%S %p %Z %Y').strip()} {msg}\n")


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run([GIT, *args], cwd=REPO, capture_output=True, text=True, check=check)


def main() -> int:
    os.chdir(REPO)

    # Stale-lock guard: skip this run if another git process is genuinely active;
    # remove the lock only if it is older than 10 minutes (known crashed-git issue).
    lock = REPO / ".git" / "index.lock"
    if lock.exists():
        if time.time() - lock.stat().st_mtime > 600:
            lock.unlink(missing_ok=True)
            log("removed stale index.lock")
        else:
            log("index.lock fresh — skipping run")
            return 0

    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return 0  # nothing to back up

    stamp = datetime.now().strftime("%Y-%m-%d %I:%M %p %Z").strip()
    commit = git("commit", "-q", "-m", f"chore(auto-backup): {stamp}")
    if commit.returncode != 0:
        log(f"commit FAILED (will retry next hour): {commit.stderr.strip()[:200]}")
        return 1

    push = git("push", "-q", "origin", "main")
    if push.returncode != 0:
        log(f"push FAILED (will retry next hour): {push.stderr.strip()[:200]}")
        return 1

    log("pushed OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
