# Recursive Improvement Phase 2 — Closed-Loop Self-Improvement

**Status:** DRAFT (awaiting approval) — 2026-04-14
**Supersedes / Extends:** `2026-04-02-recursive-improvement-phase1-design.md`
**Target deploy window:** 1-2 sessions after spec approval

## Vision

Phase 1 built a **detect + propose** loop:
- Overwatch runs 12 health checks every 4h and writes LLM-authored fix proposals to `docs/fix-proposals/`
- Weekly forensics surfaces WR-deviation patterns and writes `reports/forensics_*.md`
- Daily reports surface trade-level alerts
- Auto-lifecycle scans kill/pause/promote/demote slots on rule-based thresholds
- Kelly sizing, drawdown pauses, per-pair blacklists, daily caps — all live

**What does not exist: a component that reads those artifacts and mutates code/config.** Every pipeline stops at `.md` / `.log`. This spec closes that loop with asymmetric autonomy — the bot makes de-risking decisions on its own, and escalates risk-expanding ones to the user.

## Guiding principles (from academic + regulatory research)

**Asymmetric autonomy.** Every peer-reviewed framework (SR 11-7, MiFID II RTS 6, López de Prado WFO/purged-CV, Knight Capital post-mortem, NeurIPS 2025 "Losing Winner") converges on the same split:

| Bot can do autonomously | Must route through human |
|---|---|
| Reduce position size | Raise leverage or per-trade size |
| Tighten gates | Loosen gates |
| Pause symbol / strategy / slot | Enable new symbol or strategy |
| Rollback on degradation | Initial deploy of a new strategy |
| Blocklist losing pairs | Raise risk limits or kill-switch thresholds |

**Hard invariants the optimizer cannot cross** (enforced in code, not config):

| Invariant | Value | Rationale |
|---|---|---|
| Max leverage | 10x | Anything higher needs explicit approval + re-spec |
| Max per-trade margin | $15 | Protects account from sizing bugs |
| Min per-trade margin | $3 | Prevents Kelly micro-lot noise (see 2026-04-14 finding) |
| Max daily loss | 3% of balance | Daily halt, existing behavior preserved |
| Max drawdown halt | 30% | Auto-pause threshold, existing behavior preserved |
| Max parameter change per week | ±25% | Prevents compounding degradation |
| Min shadow sample | 30 trades | Before any param variant promotes from paper to live |

Any change that attempts to cross an invariant is rejected at the applier stage with a Telegram alert.

**Shadow mode before live.** Every proposed parameter change runs for N ≥ 30 trades as a paper-slot variant before promotion. This validates improvement against live data, not just backtests.

**Auto-rollback safety net.** Any autonomous change emits to `parameter_changelog.json`. The existing `auto_lifecycle.scan_rollbacks` monitors for a 15% WR drop within 48 hours and auto-reverts.

## What's already built (do not rebuild)

| Capability | Owner | Status |
|---|---|---|
| 12-check health monitor | `overwatch.py` | Live every 4h |
| LLM fix-spec generation | `overwatch.generate_fix_specs` | Live (Claude Sonnet) |
| Weekly pattern detection | `weekly_forensics.py` | Live Sundays |
| Auto-kill slot on neg Kelly / low WR | `auto_lifecycle.scan_kills` | Live |
| Edge decay 24h pause | `auto_lifecycle.scan_edge_decay` | Live |
| Auto-promote paper→live | `auto_lifecycle.scan_promotions` | Live |
| Auto-ramp 10→20→30% capital | `auto_lifecycle.scan_ramps` | Live |
| Auto-rollback on WR drop | `auto_lifecycle.scan_rollbacks` | **Wired but dead (changelog empty)** |
| Kelly bet sizing | `risk_manager.compute_kelly_margin` | Live |
| Drawdown pauses 8/20/25/30% | `risk_manager` | Live |
| Consecutive-loss halt (5 in row) | `bot.py` | Live |
| Per-pair blacklist (3 losses → 4h) | `bot.py` | Live |
| Daily symbol cap | `bot.py` | Live |
| Telegram /status /kill /pause /resume /slots /balance | `telegram_commander.py` | Live |
| Sentinel file IPC | `bot._process_sentinels` | Live |
| Orphan-position 3-layer defense | `exchange.py`, `bot.py` | Live (2026-04-13) |
| Entry snapshot logging | `bot._log_entry_snapshot` | Live |
| Phemex reconciliation every 15min | `reconcile_phemex.py` | Live |

## The gap — four specific connections missing

1. **Fix-spec applier.** Overwatch writes `.md` proposals; nothing reads and applies them.
2. **Changelog writer.** Every autonomous config/code change must emit to `parameter_changelog.json` so the existing rollback watcher has targets.
3. **Forensics → hypothesis bridge.** Weekly forensics finds patterns like "SUI shorts at 3PM PT lose 80% over 14 trades" but doesn't translate to a config change.
4. **Snapshot-driven backtester.** `logs/entry_snapshots.jsonl` has been collecting since 2026-04-07; nothing consumes it to test alternative gate thresholds against historical entries.

## Components

### Component 1: `scripts/auto_improver.py` (~250 lines)

**Purpose:** Read proposals from `docs/fix-proposals/` and `reports/forensics_*.md`, classify risk, apply SAFE ones, escalate RISKY ones.

**Trigger:** launchd `com.phmex.auto-improver.plist` every 4h, starts 30 min after overwatch so it reads fresh proposals.

**Classification rule set:**

```python
SAFE_ACTIONS = {
    # De-risking only
    "add_symbol_to_blocklist",
    "add_hour_to_block",
    "tighten_gate_threshold",    # OB ±0.25 → ±0.30
    "reduce_daily_symbol_cap",   # 3 → 2
    "reduce_max_open_trades",    # 3 → 2
    "shorten_time_exit",         # 60min → 30min
    "tighten_adverse_exit",      # -5% → -4%
    "pause_strategy",
    "pause_symbol",
    "shrink_position_size",      # respecting min $3 floor
}

RISKY_ACTIONS = {
    # Risk-expanding — require Telegram /approve
    "remove_symbol_from_blocklist",
    "remove_hour_from_block",
    "loosen_gate_threshold",
    "raise_daily_symbol_cap",
    "raise_max_open_trades",
    "lengthen_time_exit",
    "loosen_adverse_exit",
    "enable_new_strategy",
    "enable_new_symbol",
    "raise_position_size",
}

FORBIDDEN_ACTIONS = {
    # Hard-coded, never mutated by optimizer
    "raise_leverage",
    "raise_max_trade_size_above_15",
    "lower_drawdown_halt",
    "raise_daily_loss_halt",
    "disable_kill_switch",
}
```

**Flow:**
```
for proposal in new_proposals:
    parsed = parse_proposal(proposal)       # extract action + params
    risk = classify(parsed.action)
    if risk == FORBIDDEN: log + alert + skip
    elif risk == SAFE:
        if backtester_supports(parsed):
            delta = snapshot_backtest(parsed)
            if delta > THRESHOLD: apply + log + telegram_info
        else:
            apply_directly + log + telegram_info
    elif risk == RISKY:
        write_pending_approval(parsed)
        telegram_alert(parsed, action_id)
        # await /approve action_id or /reject action_id
```

**Applier sub-agent:** calls a subprocess Claude Sonnet invocation with the proposal + targeted `Edit` tool on one file at a time. Commits the change with `[auto] <action>` prefix. Writes changelog entry. Triggers `.restart_bot` sentinel.

**Hard guardrails:**
- Rate limit: max 1 autonomous change per 4h cycle
- Weekly cap: max 3 autonomous changes per 7d
- Invariant check: rejects any change that would cross a hard invariant
- Snapshot-backtest gate: if backtester says new config is >10% worse, refuse

### Component 2: `scripts/param_changelog_writer.py` (~100 lines)

**Purpose:** Central function every autonomous change path calls. Guarantees changelog is populated.

**Schema (matches Phase 1 design):**
```json
{
  "changed_at": "2026-04-14T04:30:00Z",
  "param": "OB_IMBALANCE_THRESHOLD",
  "old_value": 0.25,
  "new_value": 0.30,
  "param_source": "env",
  "param_source_key": "OB_IMBALANCE_THRESHOLD",
  "change_action": "tighten_gate_threshold",
  "proposal_source": "docs/fix-proposals/2026-04-14-08-ob-imbalance.md",
  "actor": "auto_improver",
  "pre_change_metrics": {
    "wr_7d": 0.42,
    "net_pnl_7d": -8.31,
    "trade_count_7d": 24,
    "avg_pnl_7d": -0.346
  },
  "rollback_watch_until": "2026-04-16T04:30:00Z"
}
```

**Usage pattern (to be inserted in all autonomous mutation paths):**
```python
from scripts.param_changelog_writer import log_param_change
log_param_change(
    param="OB_IMBALANCE_THRESHOLD",
    old=0.25, new=0.30,
    source="env", action="tighten_gate_threshold",
    proposal="docs/fix-proposals/...",
)
```

**Watch enforcement:** Once written, `auto_lifecycle.scan_rollbacks` already picks it up on its 4h cycle.

### Component 3: `scripts/snapshot_backtester.py` (~200 lines)

**Purpose:** Replay `logs/entry_snapshots.jsonl` against alternative gate thresholds. Answers: "what would happen if OB imbalance were 0.30 instead of 0.25?"

**Not a full backtester** — it does not simulate price paths. It replays historical ENTRIES (which we know the outcome of) and answers "would this gate have passed under the alternative?"

**Inputs:**
- `logs/entry_snapshots.jsonl` (all entries since 2026-04-07, has OB, flow, ADX, RSI, vol, regime)
- Proposed parameter change
- Matching closed_trades from `trading_state.json`

**Outputs (table):**
- How many historical entries the new gate would have blocked
- Of those blocked, what was their realized PnL (saved or missed)
- Counterfactual net PnL if change had been live
- Confidence interval (bootstrapped over 1000 resamples)

**Critical caveat:** entries that DIDN'T fire historically due to other gates can't be recovered. Only measures what existing entries would have been filtered. So it's an **upper bound on the benefit of tightening** and useful for answering "is this tightening safe" but useless for answering "what should we loosen".

### Component 4: extend `telegram_commander.py` (~50 lines)

**New commands:**
- `/pending` — list RISKY actions awaiting approval
- `/approve <action_id>` — approve a pending action, applier runs it
- `/reject <action_id>` — reject a pending action, no state change
- `/improver` — force-run auto_improver now
- `/changelog` — show last 10 changelog entries
- `/invariants` — show current hard invariants

**Storage:** `logs/pending_actions.jsonl` — one row per pending action with full proposal + expiry (24h default, auto-expires if not approved).

## Closed-loop flow

```
┌──────────────────────┐
│ Bot trades           │───► closed_trades, entry_snapshots
└──────────────────────┘
         │
         ▼
┌──────────────────────┐
│ overwatch.py         │───► docs/fix-proposals/*.md (every 4h)
│ weekly_forensics.py  │───► reports/forensics_*.md (Sundays)
│ daily_report.py      │───► reports/YYYY-MM-DD.md (daily)
└──────────────────────┘
         │
         ▼
┌──────────────────────┐
│ [NEW] auto_improver  │
│  - parse proposal    │
│  - classify risk     │
│  - if SAFE:          │───► snapshot_backtester validates
│    └─ apply          │───► param_changelog_writer logs
│                      │───► git commit + .restart_bot
│  - if RISKY:         │
│    └─ telegram alert │───► await /approve or /reject
└──────────────────────┘
         │
         ▼ (after 48h)
┌──────────────────────┐
│ auto_lifecycle       │
│  .scan_rollbacks     │───► if WR drops 15%, revert + restart
└──────────────────────┘
```

## Implementation phases

### Phase 2a — Foundation (shippable in 1 session, low risk)
- Component 2: `param_changelog_writer.py`
- Retrofit into existing autonomous mutation paths: drawdown pause, slot kill, per-pair blacklist (these currently don't log, so rollback can't protect them either)
- Add `/changelog` Telegram command

### Phase 2b — Safe-action applier (1 session)
- Component 1: `auto_improver.py` with SAFE actions only (RISKY path returns "stubbed — not implemented")
- Component 4 — `/pending`, `/approve`, `/reject` Telegram commands (stubbed)
- launchd plist + RunAtLoad first manual run

### Phase 2c — Snapshot backtester (1 session)
- Component 3: `snapshot_backtester.py`
- Wire into auto_improver's gate-tightening validation

### Phase 2d — RISKY approval loop (0.5 session)
- Activate RISKY path in auto_improver
- `/approve` / `/reject` become functional
- Pending actions expire after 24h

### Phase 2e — Min-margin floor (from 2026-04-14 XRP finding)
- Add `MIN_TRADE_MARGIN_USDT=3.0` floor in `risk_manager.compute_kelly_margin`
- Kelly can shrink, but not below $3 (prevents micro-lot noise)

## Success metrics

At 2 weeks post-deploy, measure:

| Metric | Target | Measured via |
|---|---|---|
| Autonomous changes applied | ≥3 | changelog entries |
| Autonomous rollbacks | ≤1 | changelog + auto_lifecycle logs |
| False positives (changes user would have rejected) | 0 | Reviewed weekly |
| Time from proposal to apply | <8h median | timestamps |
| Bot WR trend | ≥2pp improvement | closed_trades 14d vs prior 14d |
| Human approvals needed | <5/week | /pending log |

## Human-gated decisions (never automated)

Per academic + regulatory consensus:

1. **Raise leverage above 10x** — structural account risk
2. **Raise per-trade margin above $15** — protects against sizing bugs
3. **Deploy a brand-new strategy live** — must first accumulate 30 shadow trades
4. **Loosen the drawdown-halt thresholds** (8%/20%/25%/30%) — account protection
5. **Disable any kill switch** — circuit breakers
6. **Raise daily-loss halt above 3%** — account protection
7. **Remove hard invariant caps** — spec-level change requires re-design

## Open questions for review

1. **SL/TP changes — SAFE or RISKY?** My read: tightening SL is SAFE, loosening SL is RISKY, widening TP is RISKY (less likely to hit), tightening TP is SAFE (take profit earlier). Confirm.
2. **Should auto_improver only act during certain hours** (e.g., not during active trading window)? Could gate changes to market-close calm hours.
3. **Rollback window 48h — too short / too long?** Shorter = faster corrections but more rollback churn. Spec-design default is 48h; keep or tune.
4. **Anthropic cost budget** — each auto_improver tick calls Sonnet. At 4h cadence = 6 calls/day. At ~$0.05/call = $9/month. Acceptable?
5. **Integration with MIN_TRADE_MARGIN floor** — the XRP bug shows Kelly can shrink to noise. Phase 2e adds a $3 floor. Confirm acceptable vs strict Kelly math.

## Known risks

- **Over-automation creep.** Classification rules must be reviewed quarterly. Any action that becomes routine SAFE should stay SAFE; any edge-case behavior that surprised the user should be escalated to RISKY.
- **Proposal quality.** Overwatch's LLM-written proposals are the input. Bad proposal → bad action. Snapshot backtester is the defense; if a proposal can't be validated against historical snapshots, stay in RISKY path.
- **Regime shift.** Parameter changes tuned on one regime may hurt in another. The 15% WR rollback watcher is the safety net. Test that it actually fires.
- **Applier bugs.** An auto-edit that breaks syntax crashes the bot at next restart. Mitigation: run `py_compile` before committing; reject on failure.

## Success criteria to proceed with full build

Phase 2a must show:
- Zero false changelog entries (schema rejections or corrupt writes) after 48h
- All existing autonomous mutations now write to changelog
- `auto_lifecycle.scan_rollbacks` successfully tests against a synthetic "bad change" and reverts it

If Phase 2a meets criteria, proceed with 2b. If it doesn't, stop and revise before expanding surface area.

## Appendix — what this spec does NOT cover

- Reinforcement learning or online learning on signals (deferred — complexity outweighs benefit at current scale)
- Automated strategy synthesis (deferred — explicit "never automate new-strategy deployment")
- Market-microstructure research ingestion via WebFetch (deferred — would need citation review gate, not worth building yet)
- Multi-model committee for proposals (deferred — single LLM with invariant caps is sufficient for current scale)
- Optuna / Bayesian optimization of gate thresholds (deferred — sample size still thin, would overfit)

These are all candidates for Phase 3+ once Phase 2 is stable.
