---
name: Phase 2 v2 Audit Findings
description: Audit of Phase 2 recursive-improvement spec — v1 issues, v2 corrections, open prereqs. Read before resuming Phase 2 work.
type: reference
---

# Phase 2 Recursive Improvement — Audit + v2 Summary

**Date:** 2026-04-14
**Spec v1:** `docs/superpowers/specs/2026-04-14-recursive-improvement-phase2-design.md` (REVISE verdict)
**Spec v2:** `docs/superpowers/specs/2026-04-14-recursive-improvement-phase2-design-v2.md` (ship-ready draft)

## V1 audit verdict: REVISE (yellow-red)

Four parallel audits found v1 was directionally correct but had four blocking issues.

### Blocking issues fixed in v2

1. **Schema break.** V1's `parameter_changelog.json` schema used ISO timestamp + `wr_7d/net_pnl_7d` keys. Existing consumer `auto_lifecycle.scan_rollbacks` (scripts/auto_lifecycle.py:267-294) reads Unix int + `wr/pnl/ae_rate/trades`. V1 would have crashed the rollback watcher. V2 matches Phase 1 schema exactly.

2. **Restart-discipline violation.** V1's applier auto-committed and triggered `.restart_bot` with no `/pre-restart-audit`. CLAUDE.md mandates the audit. V2 routes every autonomous mutation through `/pre-restart-audit`.

3. **Dashboard propagation missing.** V1 only surfaced changelog + pending actions on Telegram. CLAUDE.md rule: EVERY bot update must propagate to Telegram AND dashboard. V2 requires both.

4. **Ignored revised Phase 2 ordering.** `reference_recursive_improvement.md:41-72` mandates fee reduction → regime gating → observability → Optuna/WFO. V1 silently replaced all of this with applier/backtester. V2 reorders: fees (2a) → regime (2b) → observability (2c) → changelog (2d) → backtester (2e) → applier (2f) → approval (2g).

### Factual corrections in v2

- `compute_kelly_margin` → **`calculate_kelly_margin`** (risk_manager.py:392)
- Entry snapshots started **2026-04-06** (not 04-07 as v1 claimed)
- Orphan defense is **3 layers** (commit 2c89ad8), not 7
- **Phase 2e removed.** V1's "MIN_TRADE_MARGIN $3 floor from XRP finding" was not supported. Today's XRP was a scratch trade with a log-format-bug-only $0.00 margin display — Kelly actually hit the $10 fallback path, not a micro-lot. If a $3 floor is wanted later, it needs a separate case.
- MIN_TRADE_MARGIN in code today = $2 default (risk_manager.py:403)
- MAX_TRADE_MARGIN in code today = $10 default; v2's $15 cap is a new invariant

### Tightened SAFE classification (vs v1)

| Action | v1 | v2 |
|---|---|---|
| `tighten_gate_threshold` | SAFE | **RISKY unless gate has unit tests** (cvd_slope-class bugs) |
| `shorten_time_exit 60→30min` | SAFE | **RISKY** (interacts with Signal #4 peak-drawdown) |
| `pause_symbol` | SAFE | SAFE only if ≥30 trades + <30% WR |

### Rate cap tightened

- V1: 1/4h + 3/7d ≈ 12/month
- V2: 1/day + 2/7d ≈ 8/month (matches Jonas's actual deliberate cadence)

---

## Prereq status (2026-04-14)

### Q1 — Bot fixes C1/C2/C3/I9/I18

C1 and C2 landed. C3 and I9 NOT landed. I18 defanged (1h_momentum slot removed in 67a8aa3 but code path still bugged).

| ID | Status | Location |
|---|---|---|
| C1 | ✅ LANDED (commit 2c89ad8) | bot.py:1113 strategy-name fix |
| C2 | ✅ LANDED (verified 2026-04-20) | bot.py:1623-1625 paper-path carve-out exempts same tuple as live |
| C3 | ❌ NOT LANDED | bot.py:1678 `_sync_exchange_closes` fee-match race |
| I9 | ❌ NOT LANDED | exchange.py:225 REST-fallback CVD not normalized (9-OOM bug) |
| I18 | ⚠️ OBVIATED | bot.py:1355-1358 code still bugged; slot removed in 67a8aa3 |

**Implication:** Phase 2a (fee reduction) formally blocked per `reference_recursive_improvement.md:52` until C3/I9 land (was C2/C3/I9 — C2 now closed).

### Q2 — Reconcile CLEAN streak

**5 runs clean** as of 8:17 PM PT 2026-04-14. Phase 2a precondition satisfied (≥4 CLEAN).

Log: `~/Library/Logs/Phmex-S/reconcile.log`. CLEAN = `Total discrepancies: 0` per reconcile_phemex.py:231-236.

One brief drift at 7:16 PM (SUI fee $0.06 off) auto-patched. One 11:48 AM batch of 41 unmatched = Phemex API/CDN outage, recovered.

### Q4 — Dashboard security

**Bound 0.0.0.0 with zero auth.** [web_dashboard.py:42](../web_dashboard.py#L42) — any LAN device can read bot balance, trades, etc. No HTTPS. ngrok installed but not running.

**Blocks Phase 2c as drafted.** Must either flip to `127.0.0.1` (1-line, local-view only) or add Basic-Auth before adding changelog/pending-actions/balance panels.

---

## Recommended next action

Ship **Phase 2c observability + dashboard lockdown first** (low risk, unblocks everything) in parallel with a small bot-fix PR for C2/C3/I9. Then resume Phase 2a (fees) → 2b (regime) → 2d (changelog) → 2e (backtester) → 2f (applier) → 2g (approval).

Phase 2e (XRP min-margin floor) is removed from scope pending new evidence.
