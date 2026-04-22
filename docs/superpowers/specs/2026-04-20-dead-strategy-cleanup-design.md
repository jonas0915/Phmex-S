# Dead Strategy Cleanup — Design Spec

**Date:** 2026-04-20
**Status:** Draft — awaiting approval
**Scope:** Code hygiene only — zero trading behavior changes
**Risk:** LOW
**Blast radius:** Dev experience only

---

## 1. Problem

`strategies.py` defines 14 strategy functions. Only **4 fire in live trading** (verified from 30 days of `trading_state.json` — see §3). The remaining 10 are:

- Orphaned (no caller anywhere in repo)
- Paper-slot-only for slots that have since been deleted
- Historical leftovers from pre-Sentinel (v11) architecture

This creates ongoing cost:

- Debugging requires reading 14 strategy functions to find the 4 that matter
- Reference docs (`memory/reference_*.md`) still cite strategies that never fire
- Future edits risk activating stale/broken code via config typo
- Cognitive overhead on every `grep`, every session handoff
- ~1,500+ lines of dead Python inflating the diff surface

## 2. Goal

Remove all strategies that have produced **zero live trades in the last 30 days**, plus their STRATEGIES-dict entries and any orphan support code — while preserving **100% of current trading behavior**.

## 3. Evidence — strategies by live activity (30d)

Verified from `trading_state.json` closed_trades on 2026-04-20:

| Strategy | 30d trades | Keep? |
|---|---:|---|
| htf_confluence_pullback | 149 | ✅ KEEP |
| htf_confluence_vwap | 9 | ✅ KEEP |
| momentum_continuation | 10 | ✅ KEEP |
| htf_l2_anticipation | 7 | ✅ KEEP |
| trend_scalp | 0 | ❌ DELETE |
| trend_pullback | 0 | ❌ DELETE |
| bb_mean_reversion | 0 | ⚠️ CONDITIONAL (see §5) |
| bb_reversion (alias) | 0 | ❌ DELETE |
| keltner_squeeze | 0 | ❌ DELETE |
| vwap_reversion | 0 | ❌ DELETE |
| adaptive | 0 | ⚠️ CONDITIONAL (meta-wrapper, see §5) |
| confluence | — | ✅ KEEP (base router for htf_confluence_*) |
| confluence_sma_vwap | 0 | ❌ DELETE (orphan — zero callers) |
| htf_momentum | 0 | ❌ DELETE |
| liq_cascade | 0 live | ⚠️ CONDITIONAL (paper slot exists, see §5) |
| funding_contrarian | 0 | ❌ DELETE |
| htf_l2_anticipation | — | already counted above |

## 4. Non-goals

- **No trading behavior change.** Same 4 strategies, same gates, same params.
- **No backtester changes.** `backtest.py` / `backtester.py` consolidation is out of scope — separate spec.
- **No removal of gates, cooldowns, or scoring.** This is strictly module-level dead code.
- **No removal of pullback carve-out strings** at [bot.py:1113](bot.py#L1113) / [bot.py:1625](bot.py#L1625). The tuple `("htf_confluence_pullback", "bb_mean_reversion")` stays intact even if the `bb_mean_reversion_strategy` function is deleted, because historical trades in `trading_state.json` still carry that `strategy` tag and the string match protects them during replays.

## 5. Conditional deletions — need verification first

Each of these requires a pre-deletion audit:

### 5a. `bb_mean_reversion_strategy`
- Check if any paper slot (liq_cascade, mean_revert, narrow) invokes it
- Check if the `confluence` router falls back to it under any branch
- If both checks pass → delete. Otherwise keep.

### 5b. `adaptive_strategy`
- Meta-wrapper that dispatches to other strategies
- Verify with `grep -rn "adaptive_strategy\|'adaptive'" --include="*.py"`
- Likely still referenced by scanner/factory — **assume keep** unless proven unused.

### 5c. `liquidation_cascade_strategy`
- Paper slot `trading_state_5m_liq_cascade.json` exists (22 lifetime trades, still active)
- If paper slot still receives signals in logs → **KEEP**
- If paper slot is stale (no entries in 7d) → deletion candidate, separate follow-up

## 6. Files to change

### Modify
- `strategies.py` — delete function bodies + STRATEGIES dict entries

### Verify, don't modify
- `bot.py` — pullback carve-out tuple stays
- `strategy_factory.py` — confirm it doesn't invoke deleted names
- `risk_manager.py` — confirm exit tagging doesn't reference deleted names
- `web_dashboard.py` / `scripts/daily_report.py` — confirm `.get(name, "unknown")` tolerance on historical trades

### Delete (if applicable)
- Orphan `.bak` files for deleted slots (already untracked, ignore)

## 7. Implementation steps

1. **Pre-audit** — run the verification from §5 for each CONDITIONAL entry. Downgrade to KEEP if any live caller found.
2. **Grep sweep** — for each DELETE entry:
   ```bash
   grep -rn "<function_name>\|'<strategy_key>'\|\"<strategy_key>\"" --include="*.py" --include="*.json"
   ```
   Must return zero hits outside strategies.py itself.
3. **Delete function bodies** from strategies.py.
4. **Delete STRATEGIES dict entries** for the deleted names + legacy aliases.
5. **Syntax check**: `python3 -m py_compile strategies.py bot.py strategy_factory.py`.
6. **Run `/pre-restart-audit`** — confirm no regressions.
7. **Commit** — single atomic commit: `chore: remove N dead strategies (zero 30d live activity)`.
8. **No bot restart required** — `strategies.py` loads at startup; running bot continues with its already-loaded functions. Next natural restart picks up the cleanup.

## 8. Validation

### Pre-merge
- Syntax checks pass
- Grep sweep clean
- Pre-restart audit clean

### 24h post-deploy (at next restart)
- Trade cadence unchanged: live trades/day ± 10% of 7d baseline
- Strategy mix unchanged: same 4 strategies producing entries
- No new `ImportError` / `KeyError` / `AttributeError` in logs
- Dashboard + daily report render without missing-key errors

### Rollback
`git revert <cleanup-commit>` — no state migration, no exchange-side impact. Fully reversible within seconds.

## 9. Risk matrix

| Risk | Severity | Mitigation |
|---|---|---|
| Deleted function called via string lookup not caught by grep | Medium | §7.2 grep sweep covers .py + .json; run twice with different patterns |
| Historical trades in trading_state.json reference deleted strategy name → dashboard breaks | Low | Display code already uses `.get()` defaults; verify in §6 |
| Cleanup lands during live trading and introduces syntax error | Low | Pre-restart audit + py_compile catch this before any restart |
| Meta-wrapper (`adaptive`) assumed dead but still hot in factory | Medium | §5b explicitly defers this until verified |
| Obsidian vault / external docs reference deleted strategies | Low | Docs can be updated lazily; won't break runtime |

## 10. Expected outcomes

| Dimension | Change |
|---|---|
| Live trading behavior | None |
| Win rate | Unchanged |
| PnL | Unchanged |
| Fill quality | Unchanged |
| `strategies.py` LOC | −1,200 to −1,500 (estimate) |
| STRATEGIES dict size | 14 → 5 entries |
| Grep noise | Drops ~60% for strategy-related searches |
| Onboarding/debugging time | Materially faster |

## 11. Decision gate

**Proceed when:** Jonas approves + bot is in a low-activity window (weekend morning or post-restart window for another reason).

**Defer if:** active incident, open position, upcoming feature deploy that touches `strategies.py`.

## 12. Follow-ups (out of scope, queued)

- `backtest.py` vs `backtester.py` consolidation (Phase 2 blocker)
- Remove stale `.bak` files + `trading_state_*.json` for deleted paper slots
- Add `.gitignore` entries for runtime artifacts (`.bot.pid`, `trading_state.json`, etc.)
- Zero-test repo → add minimal smoke tests for the 4 live strategies
- Reference doc cleanup — memory/reference_*.md still cites deleted strategies

---

**Approver:** Jonas
**Implementer:** Claude (subagent-driven, after approval)
**Estimated execution time:** 30–45 minutes including verification, restart window excluded
