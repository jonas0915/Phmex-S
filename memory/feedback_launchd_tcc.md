---
name: launchd jobs cannot write to ~/Desktop (TCC)
description: macOS TCC blocks launchd background jobs from accessing ~/Desktop, ~/Documents, ~/Downloads — use ~/Library/Logs/ instead
type: feedback
---

macOS TCC (Transparency, Consent, and Control) blocks launchd background daemons from accessing protected user folders: ~/Desktop, ~/Documents, ~/Downloads, ~/Pictures, ~/Movies. Scripts work fine when run interactively (terminal inherits user TCC) but fail under launchd with exit code 78 (EX_CONFIG) and silent stderr.

**Why:** TCC permissions are per-process. Launchd background jobs run in a separate context that doesn't inherit Terminal's permissions. The bot's launchd jobs (monitor, daily-report, report-catchup) silently failed for 5 days starting around 2026-03-31 because their stdout/stderr paths were under ~/Desktop/Phmex-S/logs/. Diagnosis was tricky because stderr was empty (TCC blocks writes silently).

**How to apply:**
- Never put launchd StandardOutPath/StandardErrorPath under ~/Desktop, ~/Documents, ~/Downloads
- Use ~/Library/Logs/<AppName>/ instead — no TCC restriction, standard macOS convention
- The script itself can still read/write files in ~/Desktop because the *script's* file operations happen in the inherited user context, but launchd's own file redirections do not
- If a launchd job mysteriously exits 78 with no stderr, suspect TCC first
- Alternative fix: grant Full Disk Access to the Python binary in System Settings → Privacy & Security → Full Disk Access (more invasive, harder to track)

Fixed 2026-04-05: moved monitor.log, daily-report.log, report-catchup.log to ~/Library/Logs/Phmex-S/. All 3 jobs now run with exit 0.
