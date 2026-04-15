# Recursive Improvement Phase 2 — Design Spec v2

**Status:** DRAFT v2 (supersedes v1 2026-04-14) — 2026-04-14
**Extends:** `2026-04-02-recursive-improvement-phase1-design.md` (Phase 1, fully deployed 2026-04-07)
**Aligns with:** `memory/reference_recursive_improvement.md` revised ordering (post-2026-04-07 audit)
**Audit record:** v1 of this spec (same dated file, suffixed `-v1.md` if kept) received a REVISE verdict across infrastructure, prior-R&D, lessons-compliance, and empirical-claim audits on 2026-04-14. Issues addressed below.

---

## Why v2

v1 was directionally correct but had four load-bearing problems:

1. **Ordering conflict.** v1 shipped closed-loop tooling first. The post-audit revised ordering in `reference_recursive_improvement.md:41-72` mandates: **fee reduction → regime gating → observability → Optuna/WFO**. v1 silently replaced all of those with applier/backtester/approval tooling. v2 reconciles: fee reduction and regime gating ship first; closed-loop tooling ships last and only after observability is in place.
2. **Schema break.** v1's `parameter_changelog.json` schema (ISO timestamp, `wr_7d/net_pnl_7d` keys) would crash the existing `auto_lifecycle.scan_rollbacks` consumer ([scripts/auto_lifecycle.py:267-294](../../../scripts/auto_lifecycle.py#L267-L294)) which reads Unix int + `wr/pnl/ae_rate/trades`. v2 matches Phase 1 schema exactly.
3. **Restart-discipline violation.** v1's auto-improver auto-committed and triggered `.restart_bot` with no `/pre-restart-audit`. CLAUDE.md mandates: "NEVER restart without running `/pre-restart-audit` first." v2 routes every autonomous mutation through the existing `pre-restart-audit` skill, or refuses the change.
4. **Dashboard propagation missing.** v1 surfaced changelog + pending actions on Telegram only. CLAUDE.md mandates: "EVERY bot update must propagate to Telegram AND the dashboard." v2 propagates every new surface to `web_dashboard.py`.

Additional corrections baked in:
- Phase 2e ("MIN_TRADE_MARGIN floor from XRP finding") removed — the 2026-04-14 XRP trade was a scratch trade with a log-display bug, not Kelly micro-lot noise. Min-margin investigation parked until a real case arises.
- Factual errors fixed: `compute_kelly_margin` → `calculate_kelly_margin` ([risk_manager.py:392](../../../risk_manager.py#L392)); entry snapshots began 2026-04-06 (not 04-07); orphan defense is 3 layers per commit 2c89ad8.
- v1 rebranded Phase 1 guardrails (asymmetric autonomy, ±25%/week, 30 shadow trades, 15% WR rollback) as novel. v2 cites Phase 1 and only adds genuinely new invariants.

---

## Guiding principles (inherited from Phase 1)

v2 inherits these from [Phase 1 design §Guardrails](../specs/2026-04-02-recursive-improvement-phase1-design.md#guardrails) — not rediscovered:

- Asymmetric autonomy (bot can reduce risk, never increase)
- ±25% max parameter change per week
- ≥30 shadow trades before any parameter variant promotes from paper to live
- Auto-rollback on 15% WR drop in 48h (already wired; dead because changelog empty)
- Max 2 live slots
- Never raise leverage or size autonomously

**New invariants added in v2** (must be enforced in code, not just config):

| Invariant | Value | Rationale |
|---|---|---|
| Max per-trade margin | $15 | Protects account from sizing bugs; current `MAX_TRADE_MARGIN` default = $10, new ceiling is a hard cap |
| Max daily autonomous mutations | 1 | Matches Jonas's actual deliberate cadence (1 change / 3-4 days) |
| Max weekly autonomous mutations | 2 | Down from v1's 3; preserves caution |
| Reconcile-CLEAN precondition | All last 4 runs CLEAN | From `reference_recursive_improvement.md:81-82` |
| Pre-restart audit precondition | Required | From CLAUDE.md |

---

## Hard preconditions (fail-closed)

Before **any** autonomous mutation is applied, all of the following must be true — or the mutation is rejected and an alert is sent:

1. `scripts/reconcile_phemex.py` last 4 runs all reported CLEAN (no drift, no orphans, no reconciliation lag warnings).
2. `logs/entry_snapshots.jsonl` has been written to in the last 24h (telemetry-live check).
3. `parameter_changelog.json` is readable and schema-valid.
4. No drawdown halt currently active.
5. No consecutive-loss halt currently active.
6. No `.pause_trading` sentinel present.
7. Overwatch last run reported no CRITICAL findings (only WARN or INFO).

Any precondition failure → mutation rejected, Telegram WARN sent, no retry for that proposal until next cycle.

---

## What's already built (verified 2026-04-14)

| Capability | Owner | Status |
|---|---|---|
| 12 health checks every 4h | [scripts/overwatch.py](../../../scripts/overwatch.py) | Live (com.phmex.overwatch.plist) |
| LLM fix-spec generation | `overwatch.generate_fix_specs` ([line 748](../../../scripts/overwatch.py#L748)) | Live (claude-sonnet-4-6) |
| Weekly pattern detection | `weekly_forensics.py` | Live Sundays (com.phmex.forensics.plist) |
| Auto-kill / edge-decay / promote / ramp / rollback | [scripts/auto_lifecycle.py](../../../scripts/auto_lifecycle.py) lines 83/108/131/208/257 | All live; rollback **wired but dead (changelog empty)** |
| Kelly bet sizing | `risk_manager.calculate_kelly_margin` ([line 392](../../../risk_manager.py#L392)) | Live |
| Drawdown pauses 8/20/25/30% | [risk_manager.py:355-369](../../../risk_manager.py#L355-L369) | Live |
| Consecutive-loss halt (5 in row) | [bot.py:72](../../../bot.py#L72) | Live |
| Per-pair blacklist (3 losses → 4h) | [bot.py:1617-1622](../../../bot.py#L1617-L1622) | Live |
| Daily symbol cap (=3) | [config.py:25](../../../config.py#L25), [bot.py:898](../../../bot.py#L898) | Live |
| Telegram commands `/status /kill /pause /resume /slots /balance /overwatch` | [scripts/telegram_commander.py](../../../scripts/telegram_commander.py) | Live |
| Sentinel file IPC | `bot._process_sentinels` ([bot.py:441](../../../bot.py#L441)) | Live |
| Orphan-position 3-layer defense | `exchange.py`, `bot.py` (commit 2c89ad8, 2026-04-13) | Live |
| Entry snapshot logging | `bot._log_entry_snapshot` ([bot.py:1573](../../../bot.py#L1573)) | Live since **2026-04-06** (first entry 20:35) |
| Phemex reconciliation every 15 min | `scripts/reconcile_phemex.py` (com.phmex.reconcile.plist) | Live |
| Overwatch uses Claude Sonnet 4.6 | [scripts/overwatch.py:892](../../../scripts/overwatch.py#L892) | Updated 2026-04-14 (deprecation migration) |

---

## The gaps (what Phase 2 actually builds)

From the revised ordering in `reference_recursive_improvement.md:41-72`, plus the four v1-identified connections:

| # | Gap | Phase |
|---|---|---|
| G1 | Fee reduction (post-only maker limits, maker rebates) — **63% of losses, top lever** | 2a |
| G2 | Regime-aware slot gating — 82% of adverse exits are longs | 2b |
| G3 | Observability panels (gates firing rate, fee-pending flags, drift alerts) | 2c |
| G4 | Changelog writer + retrofit into existing mutations (wakes up `scan_rollbacks`) | 2d |
| G5 | Snapshot-driven backtester (consumes `logs/entry_snapshots.jsonl`) | 2e |
| G6 | Fix-spec applier (SAFE-only, with `/pre-restart-audit` hook) | 2f |
| G7 | Approval-loop for RISKY actions (Telegram `/pending /approve /reject`) | 2g |

Each phase is a 0.5-1 session shippable unit. Phases must ship in order; each has a **completion gate** that must pass before moving to the next.

---

## Phase 2a — Fee Reduction (top priority)

**Status goal:** Cut the #1 cost line. Fees = $6.86 of $10.84 losses over 8 days ≈ 63% of losses. Maker rebates turn cost into revenue on post-only fills.

**Prerequisites** (from `reference_recursive_improvement.md:52`):
- C1/C2/C3/I9/I18 bot fixes must be verified landed first. These are small but prerequisite — audit status before 2a kicks off.

**Work:**
1. Verify all live orders route through post-only maker path; no market fallback outside exits. Check [bot.py] entry and exit order placement.
   - Current state: limit-only entries exist (commit ab51309). Verify no remaining market fallbacks in ExchangeWrapper paths.
2. Quantify realized maker/taker ratio over last 14 days using exchange order history export (do NOT trust internal logs — cross-check per CLAUDE.md fabrication rule).
3. If taker ratio > 10%, investigate and remediate.
4. Surface `fee_total_24h`, `maker_ratio_7d`, `taker_ratio_7d` on:
   - Daily Telegram report ([notifier.py], [scripts/daily_report.py])
   - Web dashboard ([web_dashboard.py])

**Completion gate:**
- Real-money fee rate over 48h post-deploy ≤ 50% of pre-deploy rate on equivalent trade count, OR
- Evidence that further reduction requires strategy changes not fee-mechanism changes

---

## Phase 2b — Regime-aware slot gating

**Status goal:** Block longs in confirmed downtrend; block shorts in confirmed uptrend. Target: reduce adverse-exit rate from current ~25% (per latest report) toward ≤15%.

**Work:**
1. Define regime signal — recommendation: 1H SMA(50) slope + 4H ADX. Both must agree for a directional bias; otherwise "neutral" (no filter).
2. Add `regime_gate` to entry flow in [bot.py] — after per-pair cooldown, before ensemble confidence.
3. Enforce: in "up" regime, reject SHORT signals; in "down" regime, reject LONG signals; neutral = no filter.
4. Log gate decisions to `logs/gate_decisions.jsonl` (new file, one line per entry attempt: fired/blocked/reason).
5. Propagate regime state to:
   - Telegram `/status` (show current regime: UP/DOWN/NEUTRAL)
   - Web dashboard (regime badge + gate-firing stats)

**Completion gate:**
- 7-day rolling adverse-exit rate drops at least 5pp, OR
- Evidence that current directional skew has shifted and regime gate is no longer the right fix

---

## Phase 2c — Observability panels

**Status goal:** Every Phase 2 decision beyond this point needs empirical feedback. Ship observability before shipping autonomy.

**Work:**
1. Extend [web_dashboard.py] with:
   - Gates firing-rate table (per-gate: fire_count, block_count, block_reason breakdown over 7d)
   - Fee-pending flag (any trade whose fee has not been reconciled to exchange truth)
   - Drift alerts (reconcile_phemex findings over last 24h)
   - Regime history (regime timeline over last 48h)
   - Changelog preview (empty until 2d, then populated)
2. Add matching `/gates /fees /drift /regime` commands to [scripts/telegram_commander.py].
3. Ensure both surfaces read from the same source of truth (no duplicate computation).

**Completion gate:**
- Dashboard loads all panels without error against live data
- Telegram commands return matching numbers (cross-check rule)

---

## Phase 2d — Changelog writer + retrofit

**Status goal:** Wake up the dead `auto_lifecycle.scan_rollbacks` watcher by populating `parameter_changelog.json`.

**Schema (matches Phase 1 exactly — see [phase1-design.md lines 52-64](../specs/2026-04-02-recursive-improvement-phase1-design.md#L52-L64)):**

```json
{
  "param": "ADVERSE_EXIT_THRESHOLD",
  "old_value": -5.0,
  "new_value": -6.0,
  "changed_at": 1775100000,
  "pre_change_metrics": {"wr": 42.0, "pnl": 1.20, "ae_rate": 28.0, "trades": 20},
  "source": "auto_lifecycle",
  "param_source": "env",
  "param_source_key": "ADVERSE_EXIT_THRESHOLD"
}
```

**Deliverables:**
1. `scripts/param_changelog_writer.py` (~80 lines) — central `log_param_change()` function. Validates inputs, enforces Phase 1 schema, writes atomically.
2. **Retrofit existing autonomous mutations** to call the writer. These paths already mutate state but don't log:
   - Drawdown pauses (risk_manager)
   - Slot kills (auto_lifecycle)
   - Per-pair blacklist activations (bot.py)
   - Edge-decay pauses (auto_lifecycle)
3. Add `/changelog` Telegram command + web dashboard panel (last 10 entries).

**Completion gate (hard — must pass before 2e):**
- Read-back test: after triggering a synthetic drawdown pause in a dry-run, assert the entry appears in `parameter_changelog.json` with Phase 1 schema.
- `auto_lifecycle.scan_rollbacks` successfully identifies a synthetic "bad change" entry and emits a rollback sentinel (test-only, sentinel consumed and discarded).
- 48h with bot running and at least 1 real entry written by a retrofitted path, no schema errors.
- Dashboard panel renders the real entry.

If this gate fails, STOP. Do not proceed to 2e/2f/2g.

---

## Phase 2e — Snapshot-driven backtester

**Status goal:** Answer "what would happen if OB imbalance were 0.30 instead of 0.25?" from historical entry data, not backtests.

**Scope (bounded):**
- Replay only `logs/entry_snapshots.jsonl` entries (currently ~64, will be ~150+ by deploy)
- Only validates **tightening** a gate (filtering out entries we know the outcome of). Useless for loosening — acknowledged in v1 line 209.
- Outputs counterfactual net PnL with bootstrapped 1000-sample CI over realized outcomes
- Refuses to render a verdict if sample size < 30 matching entries

**Caveat (from sample-size audit):**
- Data is <2 weeks at time of writing. Confidence intervals will be wide. The backtester's job is to flag "this change is probably harmful" (downside screen), not "this change is probably good" (upside claim).

**Deliverables:**
1. `scripts/snapshot_backtester.py` (~200 lines)
2. CLI: `python scripts/snapshot_backtester.py --param OB_IMBALANCE_THRESHOLD --from 0.25 --to 0.30`
3. Output: text table + JSON dump for consumption by 2f.

**Completion gate:**
- On a known historical gate change with >30 matching entries, produces a counterfactual that matches hand-computed values within 5%.

---

## Phase 2f — Fix-spec applier (SAFE-only, audit-gated)

**Status goal:** Connect overwatch proposals to code changes — but only de-risking ones, only through `/pre-restart-audit`.

**Flow (per proposal):**

```
Read proposal from docs/fix-proposals/*.md
   │
   ▼
Preconditions (reconcile CLEAN, telemetry live, etc.) — FAIL → skip + telegram INFO
   │
   ▼
Parse action + params
   │
   ▼
Classify risk:
   SAFE (tightened gate, shortened time exit, pause symbol w/ ≥30 trade evidence)
   RISKY (see table below)
   FORBIDDEN (raise leverage, raise size, disable kill switch, lower DD halt) → REJECT + ALERT
   │
   ▼
If SAFE + backtester supports: run snapshot_backtester
   If result shows >10% worse counterfactual → REJECT + telegram INFO
   │
   ▼
Write staged patch to `.staged_changes/YYYY-MM-DD-<action>.diff`
   │
   ▼
Invoke `/pre-restart-audit` skill via subprocess
   If audit passes:
     - Apply patch
     - Run py_compile on all touched files (syntax guard)
     - Write changelog entry
     - git commit with [auto] prefix
     - Emit .restart_bot sentinel → monitor_daemon restarts bot
     - Telegram INFO with action + diff summary
     - Dashboard reflects change
   If audit fails:
     - Discard patch
     - Telegram WARN with audit findings
```

**Revised SAFE classification (tighter than v1):**

| Action | v1 class | v2 class | Reason |
|---|---|---|---|
| `tighten_gate_threshold` | SAFE | **RISKY** unless the gate has unit tests covering the new value | cvd_slope-class bugs (lessons.md:157-161) could silently worsen a broken gate |
| `pause_symbol` | SAFE | SAFE only if ≥30 closed trades on that symbol with <30% WR | prevents blanket bans on thin data (lessons.md:113-119) |
| `shorten_time_exit 60→30min` | SAFE | **RISKY** | interacts with Signal #4 peak-drawdown logic (just deployed) |
| `tighten_adverse_exit` | SAFE | SAFE | de-risking, well understood |
| `add_symbol_to_blocklist` | SAFE | SAFE if ≥5 losses in 7 days | |
| `add_hour_to_block` | SAFE | SAFE if ≥3 losses in that hour over 14 days | |
| `shrink_position_size` (respecting min) | SAFE | SAFE | |
| `reduce_daily_symbol_cap` | SAFE | SAFE | |
| `reduce_max_open_trades` | SAFE | SAFE | |

All others from v1 remain RISKY or FORBIDDEN.

**Rate limits (tightened):**
- Max 1 autonomous change per day (was 1 per 4h)
- Max 2 autonomous changes per 7d (was 3)
- If 2 rollbacks in any 14d window, auto-disable applier and require human re-enable

**Completion gate:**
- Dry-run: applier processes 3 synthetic proposals (1 SAFE, 1 RISKY, 1 FORBIDDEN) correctly — SAFE staged, RISKY routed to pending, FORBIDDEN rejected with alert.
- `/pre-restart-audit` hook confirmed to invoke and block on audit failure (test with a deliberately broken patch).

---

## Phase 2g — Approval loop for RISKY actions

**Status goal:** Every change the bot can't decide alone routes to Telegram for explicit approval.

**Work:**
1. Extend [scripts/telegram_commander.py]:
   - `/pending` — list actions awaiting approval with `action_id` each
   - `/approve <action_id>` — re-enters applier with that action, runs `/pre-restart-audit`
   - `/reject <action_id>` — discards action, logs reason
2. Storage: `logs/pending_actions.jsonl` (one row per pending action + 24h expiry)
3. Dashboard panel: pending-approval queue with countdown to expiry

**Completion gate:**
- End-to-end test: a RISKY proposal reaches `/pending`, Jonas runs `/approve` from phone, applier runs, `/pre-restart-audit` passes, change commits, bot restarts, dashboard reflects.

---

## Success metrics (2 weeks post-full-deploy)

| Metric | Target | Measured via |
|---|---|---|
| 7-day fee-to-gross-PnL ratio | <30% (was 63%) | trading_state.json + exchange export |
| 7-day adverse-exit rate | ≤15% (was ~25%) | closed_trades by exit_reason |
| Autonomous changes applied | ≥2 | parameter_changelog.json |
| Autonomous rollbacks | ≤1 | auto_lifecycle logs |
| Changes user would have rejected | 0 | reviewed weekly |
| Human approvals needed | ≤2/week | pending_actions.jsonl |
| Dashboard surface parity with Telegram | 100% | manual spot-check |
| Reconcile CLEAN streak | ≥95% of runs | reconcile_phemex logs |

---

## Human-gated decisions (never automated — same as v1)

1. Raise leverage above 10x
2. Raise per-trade margin above $15
3. Deploy a brand-new strategy live (requires 30 shadow trades first)
4. Loosen drawdown-halt thresholds (8%/20%/25%/30%)
5. Disable any kill switch
6. Raise daily-loss halt above 3%
7. Remove hard invariant caps (spec-level change → requires re-design)

---

## Known risks + mitigations

| Risk | Mitigation |
|---|---|
| LLM-authored patch introduces semantic bug | `/pre-restart-audit` hook; py_compile guard; 15% WR rollback watcher |
| Proposal quality degrades | Backtester's downside screen; SAFE list re-classifies aggressively |
| Regime shift invalidates tuning | Rollback watcher + reconcile-CLEAN precondition |
| Anthropic API outage mid-applier | Precondition check: applier no-ops if Sonnet unreachable |
| `.bot.pid` race on auto-restart | Use 3-check alive protocol from feedback_pid_lock_check.md |
| launchd TCC log path violation | All plists write to `~/Library/Logs/Phmex-S/` (not `~/Desktop/`) |
| Dashboard and Telegram drift | Phase 2c enforces shared source of truth |

---

## Explicit non-goals (same as v1, updated)

- Reinforcement learning / online learning on signals
- Automated strategy synthesis (human-gated forever)
- Market-microstructure research ingestion via WebFetch
- Multi-model committee for proposals
- Optuna / Bayesian optimization (deferred per `reference_recursive_improvement.md:64-66`; requires 2 weeks clean telemetry)
- **Min-trade-margin floor from "XRP finding"** — removed. Today's XRP was a scratch trade with a log-display bug, not Kelly noise. Investigation parked.

---

## Open questions to resolve before 2a kicks off

1. **C1/C2/C3/I9/I18 bot fixes** — are these landed? Need to confirm before Phase 2a (fee reduction) can start.
2. **Reconcile-CLEAN streak** — what's the current streak length? If <4 consecutive CLEAN runs, preconditions will block all autonomous mutations; may want to ship 2a-2c (which are human-driven) while the streak accumulates.
3. **Jonas approval cadence** — do you want 1-change-per-day or 1-per-3-days as the autonomous cap? Spec proposes 1/day with 2/week; easy to tighten further.
4. **Dashboard port 8050** — is it currently exposed externally, or localhost only? Affects whether new surfaces need auth.
5. **Snapshot backtester sample size** — by deploy date, we'll have ~150 entries. Is the 30-entry floor per-variant too low? Consider 50.

---

## Summary of changes vs v1

| Area | v1 | v2 |
|---|---|---|
| Ordering | Applier first | Fees → Regime → Observability → Changelog → Backtester → Applier → Approval |
| Changelog schema | ISO strings, `wr_7d` keys | Unix int, `wr/pnl/ae_rate/trades` — matches Phase 1 |
| Restart discipline | auto-restart via sentinel | `/pre-restart-audit` hook mandatory |
| Dashboard | Telegram only | Every surface propagates to web_dashboard.py |
| SAFE classification | Generous | Tightened: 3 actions demoted RISKY |
| Rate limits | 1/4h, 3/7d (~12/month) | 1/day, 2/7d (~8/month) |
| Phase 2e XRP finding | MIN_TRADE_MARGIN floor | Removed — not supported by evidence |
| Preconditions | None | 7 fail-closed checks |
| Prior-art citations | None (rebranded Phase 1) | Cites Phase 1 throughout |
| Empirical corrections | - | `calculate_kelly_margin`, snapshot start 04-06, 3-layer orphan |
| Reconcile-CLEAN precondition | Missing | Enforced |
| Telemetry-live check | Missing | Enforced (snapshot write within 24h) |
