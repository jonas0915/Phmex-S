#!/usr/bin/env python3
"""Daily backup of data GitHub does NOT cover, to iCloud Drive
(launchd: com.phmex.icloud-backup, 5:13 AM daily).

Time Machine destination failed to mount as of 2026-06-11 — this is currently
the ONLY off-machine copy of these paths. .env is deliberately EXCLUDED
(secrets belong in the password manager, not cloud-synced plaintext).

Python port of icloud_backup.sh (2026-06-12): launchd-spawned /bin/zsh is
TCC-blocked from reading ~/Desktop; the framework Python binary holds the
disk-access grant, so the job runs as Python now (rsync inherits it as a
child process).
"""
import socket
import subprocess
from datetime import datetime
from pathlib import Path

HOME = Path.home()
HOST = socket.gethostname().split(".")[0]
DEST = HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Backups" / HOST
LOG = HOME / "Library" / "Logs" / "Phmex-S" / "icloud_backup.log"

EXCLUDES = ["venv", ".venv", "node_modules", "__pycache__", ".git", ".DS_Store", "l2_ticks"]


def log(msg: str) -> None:
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def run_rsync(src: Path, subdir: str, excludes: bool = True) -> None:
    cmd = ["/usr/bin/rsync", "-a"]
    if excludes:
        for e in EXCLUDES:
            cmd += ["--exclude", e]
    cmd += [str(src), f"{DEST / subdir}/"]
    with open(LOG, "a") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=f).returncode
    log(f"{'OK  ' if rc == 0 else 'FAIL'} {src}")


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    log(f"=== backup run {datetime.now().strftime('%c')} ===")

    run_rsync(HOME / "Desktop" / "Phmex-S" / "logs", "phmex-s")
    run_rsync(HOME / "Desktop" / ".remember", "desktop")
    run_rsync(HOME / ".claude" / "projects", "claude-memory")
    run_rsync(HOME / "Desktop" / "ClaudeBot", "claudebot")
    # launchd job definitions (tiny, plain xml) — note trailing-slash semantics
    # of the original (`LaunchAgents/` copies contents, not the dir itself)
    run_rsync(Path(str(HOME / "Library" / "LaunchAgents") + "/"), "launchagents", excludes=False)

    log(f"=== done {datetime.now().strftime('%c')} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
