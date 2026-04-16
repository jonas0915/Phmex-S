---
name: Recursive Improvement Plan
description: Phase 1 spec + revised Phase 2 ordering after 2026-04-07 audit
type: project
---

## Status: Phase 1 FULLY DEPLOYED 2026-04-07
**Spec:** docs/superpowers/specs/2026-04-02-recursive-improvement-phase1-design.md

> NOTE: Phase 1 was originally claimed deployed on 2026-04-02, but entry snapshots
> were dead code until 2026-04-07 — the snapshot dict was built but never attached
> to Position. Fix landed in session 2 of 2026-04-07. Phase 1 is NOW truly live.

## Key Decisions (2026-04-02)
- Full auto autonomy — bot acts within guardrails, notifies via Telegram
- Moderate guardrails: ±25% param change/week, 30+ shadow trades, auto-rollback on 15%+ WR drop
- Auto-promote at 10% capital, ramp 10→20→30% after proving out
- Max 2 live slots (margin safety at $73 balance)
- Additive slot model with cap — promotion bumps weakest live slot if at cap
- Sentinel file-based IPC (no sockets, no shared memory)
- Two-way Telegram: python-telegram-bot library (~100 lines, separate daemon)

## Deployed Components
1. `scripts/auto_lifecycle.py` — kill/promote/decay/rollback scanner, every 4 hrs via launchd (com.phmex.auto-lifecycle.plist)
2. `scripts/telegram_commander.py` — Telegram polling daemon: /status /balance /slots /kill /pause /resume. launchd: com.phmex.telegram-commander.plist
3. `logs/entry_snapshots.jsonl` — OB/tape data appended on every live + paper entry via _log_entry_snapshot() (NOW actually wired as of 2026-04-07)
4. `parameter_changelog.json` — created (empty []), tracks param changes for auto-rollback
5. `_log_entry_snapshot()` in bot.py — appends JSONL on every entry
6. `_process_sentinels()` in bot.py — handles .pause_trading, .kill_*, .pause_*, .promote_*, .demote_* each cycle
7. monitor_daemon.py — handles .restart_bot sentinel for auto-rollback
8. launchd logs: ~/Library/Logs/Phmex-S/ (TCC-safe, not ~/Desktop)

## Verified Infrastructure
- recalibration.py: --json, kill (lines 121-136), edge decay (lines 139-158), importable
- strategy_factory.py: promotion criteria (40-47), kill criteria (49-55), but bot.py does NOT read factory state
- notifier.py: send-only, generic send(), same token works for polling
- launchd: 3 jobs active, plist templates established, Python 3.14 path confirmed

---

## Phase 2 — Revised Order (post-2026-04-07 audit)

The 2026-04-07 audit (3/4 tape gates broken silently, 58% of fees dropped from
reports, exit_reason tagging buggy, original Apr 7 review built on corrupt data)
forced a reprioritization. Original order (Optuna, shadow infra, regime, capital,
hypothesis-gen) is OBSOLETE. New order:

### 1. Fee reduction (post-only maker limits, maker rebates) — TOP PRIORITY
- Fees = 63% of losses ($6.86 of $10.84 over 8 days)
- Highest dollar/hr lever available
- Was NOT in original Phase 2; promoted to #1 by audit findings
- Requires C1/C2/C3/I9/I18 bot fixes to land first (small but prerequisite)

### 2. Regime-aware slot gating
- 82% of adverse exits are longs — "all shorts in up market / all longs in down
  market" failure mode needs a regime filter
- Was item 3 in original list; promoted by directional-skew evidence

### 3. Observability panels
- Gates firing rate, fee-pending flags, drift alerts
- Enables every other Phase 2 decision; you can't manage what you can't see
- New entry, not in original list

### 4. Optuna / WFO on cleaned data
- Was original #1; demoted because you cannot optimize on broken telemetry
- Gate: requires 2 weeks of clean post-audit telemetry before kickoff

### Deferred indefinitely
- Shadow parameter infra — basic version already exists in paper slots
- Capital reallocation — meaningless until at least one slot is proven profitable
- Automated strategy hypothesis generation — LLM toy, lowest priority

---

## Blockers

- **48-hour watch window**: No Phase 2 work until 2026-04-09 07:00 PM PT.
  Bot must run on the post-audit fixes for 48h to confirm telemetry is honest.
- **Bot fixes prerequisite**: Fee reduction work blocked until C1/C2/C3/I9/I18
  land in bot code.
- **Honest accounting invariant**: Any Phase 2 work assumes the reconcile job
  shows CLEAN on every run. If reconcile drifts, STOP Phase 2 and re-audit.

---

## Lessons from 2026-04-07 audit

See `memory/reference_sentinel_gate_forensics.md` for the full forensic writeup
of the gate failures, fee accounting drift, and exit_reason bugs. Key takeaway:
**"deployed" without telemetry verification is not deployed.** Phase 1's entry
snapshots sat dead for 5 days because nothing checked the file was being
written. Phase 2 work must include a "prove the telemetry is live" step in
every deploy checklist.
