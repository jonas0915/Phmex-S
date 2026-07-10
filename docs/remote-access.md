# Remote Access — Working on Phmex-S from Another Machine

Set up 2026-07-09 so the bot can be operated from a second Mac (e.g. work laptop)
while it keeps running on the always-on home Mac.

## The model: one bot, remote windows
- Phmex-S runs on **exactly one machine — the home Mac (`MacBook-Air-3`), 24/7.**
- The second Mac does **not** run a copy. It opens a **VS Code remote tunnel** into the
  home Mac and operates it as if sitting at it (edit files, terminal, restart, Claude Code).
- Tunnel name: **`phmex-home`** (persistent launchd service `com.visualstudio.code.tunnel`).
  - Browser: `https://vscode.dev/tunnel/phmex-home/Users/jonaspenaso/Desktop/Phmex-S`
  - Or VS Code desktop → `Remote-Tunnels: Connect to Tunnel` → GitHub → `phmex-home`.
  - Access is locked to the owner's GitHub account.

## ⚠️ RULE: editing a file ≠ the bot using it
The tunnel edits the **actual files on the home Mac in real time** — there is no copy and
no sync step. Save a file and it changes on disk **instantly**.

BUT the **running bot loaded its code and `.env` into memory at startup.** It keeps running
the OLD code until it is **restarted**. So:

> **Save a strategy / param / `.env` change → it is on the home Mac immediately, but the live
> bot will NOT act on it until an audited restart.**

Editing while the bot runs is safe (you are only changing disk files). The **restart** is the
gated moment — see below.

## ⚠️ RULE: restart is gated, from ANY machine
Restarting from the tunnel is fine — the command runs on the home Mac — but the standard gate
still applies, no exceptions:
- **Run `/pre-restart-audit` first.** Real money is at stake. (See root `CLAUDE.md`.)
- Only after the audit passes: stop the running bot and start it again on the home Mac.
- **NEVER start a second instance on the work Mac.** Two bots on one account = duplicate
  orders. The tunnel is a window, not a second host.

## Git is separate
Editing files changes the home Mac's working tree, not GitHub. To version/back up a change,
`git commit` + `git push` (the `com.phmex.auto-backup` job also pushes periodically). Git
history and the running bot are independent concerns.

## Keep-alive
launchd + the tunnel only work while the home Mac is **awake and unlocked** (host sleep
suspends the bot AND the tunnel). Keep it on AC with the lid open (the `com.jonas.caffeinate`
agent helps). If the home Mac sleeps, the work Mac loses access until it wakes.
