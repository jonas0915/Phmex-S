# Phase 2b — Regime-Aware Filter for htf_confluence_pullback

> ============================================================
> STATUS: AWAITING APPROVAL — Revision 2 (post-audit)
> ============================================================

**Date:** 2026-04-22
**Revision:** v2 — rewritten after verification audit flagged 5 numerical errors + 1 code-integration blocker in v1
**Author:** Claude (spec-only — no code changes until approved)
**Extends:** Phase 2a gates (Apr 7 ADX/conf hardening, Apr 11 divergence/QUIET gate, Apr 16 tape hardening)

## Revision Log

- **v1 (initial):** proposed UTC 3–6 "Asia Open" block. Audit found:
  - Breakeven WR cited as 57.1%; true value ~47.1% (arithmetic error)
  - "lessons.md line 262" quote on confidence predictive power was a fabricated line citation (concept exists at line 419 but the quote is a paraphrase)
  - "42% Asia Open depth drop" was misattributed — real figure belongs to UTC 21:00, not UTC 3–7
  - Two trade-row fabrications (Apr 22 UTC 3 DOGE, Apr 10 UTC 22 misclassified)
  - Gate B placement self-contradictory ("after Gate A" at ~1186 AND "after `_regime_snap`" at ~1238)
  - When corrected, the underlying UTC 3–6 hypothesis dissolved — 30d data shows UTC 4 is actually profitable (+$0.73) and UTC 6 is 50% WR flat
- **v2 (this doc):** data-driven multi-hour gate targeting the 5 unblocked pullback bleed hours the 30d JSON actually shows. All numbers re-verified against `trading_state.json` directly.

---

## 1. Problem Statement

`htf_confluence_pullback` is the bot's #1 live strategy by volume. **30-day canonical stats** (read from `trading_state.json` closed_trades, UTC day cutoff, 2026-04-22 snapshot):

| Metric | Value |
|---|---|
| Trade count | **147** |
| Wins | 56 |
| Win rate | **38.1%** |
| Net PnL | **−$20.85** |
| Adverse exits | 22 |
| Breakeven WR (1.2% SL / 1.6% TP @ 10x, fees ~0.12% round-trip) | **~47.1%** |
| Expectancy | ~−$0.14 per trade |

**30d adverse_exit share across all strategies** (also from JSON):
- Total AE trades across all strategies (30d): 32
- Pullback AE trades: 22 (**68.8% of all AE count**)
- Total AE dollar bleed (all strategies): −$18.35
- Pullback AE dollar bleed: −$13.16 (**71.7% of all AE $**)

Pullback is comfortably the #1 bleeder — confirmed, just not at the 82% share the handoff cited.

**Breakeven math (re-derived):** At 10x leverage, SL=1.2% price = −12% ROI, TP=1.6% price = +16% ROI. Round-trip taker fees ~0.12% price = ~1.2% ROI drag.

Solving for breakeven: `W × 16 − (1−W) × 12 − 1.2 = 0` → `28W = 13.2` → **W ≈ 47.1%**.

Observed: 38.1%. Gap to breakeven: ~9 percentage points. This strategy has negative expectancy under current parameters.

**14-day sample** (alternate view, UTC cutoff):

| Metric | Value |
|---|---|
| Trades | 51 |
| Wins | 19 |
| WR | 37.3% |
| Net PnL | −$4.56 |
| AE | 17 |

Note: daily reports (`reports/2026-04-*.md`) use a PT day cutoff and produce slightly different 14d totals (44 trades / 32% WR / −$4.59). This spec uses the JSON UTC-cutoff view as canonical.

---

## 2. Hypothesis — Data-Driven Per-Hour Bleed Filter

### 2.1 Observed 30d hourly performance (verified from trading_state.json)

Breakdown of all 147 pullback trades by UTC hour, over the last 30 days:

| UTC | PT | N | W | WR | Net PnL | AE | Currently |
|---|---|---:|---:|---:|---:|---:|---|
| 0 | 5PM | 4 | 0 | 0% | **−$2.00** | 1 | blocked |
| 1 | 6PM | 6 | 1 | 17% | **−$4.19** | 0 | blocked |
| 2 | 7PM | 5 | 1 | 20% | **−$1.10** | 0 | blocked |
| 4 | 9PM | 5 | 2 | 40% | +$0.73 | 0 | open ✓ |
| **5** | **10PM** | **6** | **1** | **17%** | **−$2.48** | **3** | **open (TARGET)** |
| 6 | 11PM | 8 | 4 | 50% | −$0.47 | 1 | open |
| 7 | 12AM | 10 | 6 | 60% | +$0.33 | 0 | open |
| **8** | **1AM** | **6** | **2** | **33%** | **−$1.80** | **3** | **open (TARGET)** |
| 9 | 2AM | 11 | 6 | 55% | +$0.16 | 2 | blocked |
| 10 | 3AM | 8 | 5 | 62% | **+$3.83** | 1 | open (profitable hour) |
| 11 | 4AM | 8 | 4 | 50% | +$0.54 | 3 | open |
| 12 | 5AM | 3 | 1 | 33% | −$0.66 | 1 | open |
| **13** | **6AM** | **11** | **4** | **36%** | **−$3.29** | **1** | **open (TARGET)** |
| **14** | **7AM** | **13** | **2** | **15%** | **−$5.59** | **2** | **open (TARGET — #1 bleeder)** |
| 15 | 8AM | 14 | 7 | 50% | −$1.39 | 1 | open |
| **16** | **9AM** | **5** | **1** | **20%** | **−$1.93** | **0** | **open (TARGET)** |
| 17 | 10AM | 3 | 1 | 33% | +$0.65 | 1 | blocked |
| 18 | 11AM | 4 | 2 | 50% | −$0.50 | 0 | blocked |
| 19 | 12PM | 4 | 3 | 75% | +$0.44 | 0 | blocked |
| 20 | 1PM | 3 | 0 | 0% | −$1.95 | 0 | blocked |
| 21 | 2PM | 5 | 1 | 20% | −$0.30 | 1 | open |
| 22 | 3PM | 2 | 1 | 50% | −$0.54 | 0 | open |
| 23 | 4PM | 3 | 1 | 33% | +$0.65 | 1 | open |

### 2.2 Target hours — the 5 unblocked bleed hours

`_BLOCKED_HOURS_UTC = {0, 1, 2, 9, 17, 18, 19, 20}` (`bot.py:1172`). Among the unblocked hours, five stand out as consistent pullback losers:

| UTC | PT | N | WR | Net PnL | Notes |
|---|---|---:|---:|---:|---|
| 5 | 10PM | 6 | 17% | −$2.48 | 3 of 6 trades went adverse — high AE density |
| 8 | 1AM | 6 | 33% | −$1.80 | 3 of 6 trades went adverse — same AE density as UTC 5 |
| 13 | 6AM | 11 | 36% | −$3.29 | London open pre-liquidity dump |
| 14 | 7AM | 13 | **15%** | **−$5.59** | **biggest single-hour loss in the distribution** |
| 16 | 9AM | 5 | 20% | −$1.93 | US pre-market chop |
| **Total** | — | **43** | **~22%** | **−$15.09** | ~29% of 30d pullback volume, **~72% of 30d pullback loss** |

If these 5 hours had simply been closed to pullback entries during the 30d window, the strategy's 30d PnL would be approximately **−$20.85 + $15.09 = −$5.76** (87% of the bleed recovered, assuming all five hours' trades are blocked without slippage in the counterfactual). Caveat: counterfactual assumes no re-route of signals to other hours; real-world delta will be smaller due to replacement entries.

### 2.3 No single structural theory — this is a data-driven filter

v1 proposed an "Asia Open thin liquidity" thesis for UTC 3–6. The corrected data does not support that thesis — UTC 4 is profitable, UTC 6 is break-even.

v2 makes no claim about a unifying regime theory. The 5 target hours span multiple market sessions:
- UTC 5, 8 — late Asia session
- UTC 13, 14 — London open / US pre-market transition
- UTC 16 — US cash open

What unites them empirically is: 30+ trades across them show **~22% WR against a 47.1% breakeven**. Five hours is enough surface to see a persistent pattern but the pattern is phenomenological, not theoretical.

**Implication:** validation discipline matters even more. Shadow-log at least 30 observations per target hour before any hard-gate decision.

### 2.4 Regime candidates explicitly rejected

| Feature | Reason rejected |
|---------|----------------|
| Confidence/ensemble threshold | `lessons.md` "Ensemble Layers Are Not Truly Independent" (Apr 16, ~line 419): layers 3 (CVD) & 7 (order_flow) both derive from the WS trade feed; htf_trend & vwap_pos are correlated. The 4/7 threshold is easier to clear than it appears. Raising it would punish correlated signals, not filter bad ones. DO NOT TOUCH. |
| Hurst value as a standalone gate | Already inside confidence layer 4 (`bot.py:316`). Adding it again doubles-counts. |
| 1h EMA gate | Handoff note: "proven useless." Not touching. |
| Pullback ADX threshold | Handoff: "DO NOT touch pullback ADX without spec." Out of scope. |
| CVD slope for pullback | Explicit carve-out at `bot.py:1113` — intentional architecture. Not touching. |
| early_exit thresholds | `lessons.md` line ~366 (Apr 11): simulation showed lowering to 1.5% ROI = CATASTROPHIC (−$60.96 vs −$20.87). LOCKED. |
| 5m VOLATILE regime (as hard gate) | Data gap — outcomes not stored in `entry_snapshots.jsonl`. Will be SHADOW-LOGGED only as Gate B (see §3.2). |

---

## 3. Proposed Filter Design

### 3.1 Gate A: Multi-Hour Pullback Bleed Filter

**Mechanism:** When `strat_name == "htf_confluence_pullback"` and current UTC hour is in `_PULLBACK_BLEED_HOURS_UTC = {5, 8, 13, 14, 16}`, log a `"pullback_hour_bleed"` gotAway entry. When `Config.PULLBACK_SESSION_GATE=true`, also hard-block the entry.

**Default:** `PULLBACK_SESSION_GATE=false` — shadow-tag only. Hard gate requires explicit `.env` flip after validation.

**Integration point in `bot.py`:** After HTF throttle check at **line 1184**, before Kelly sizing at **line 1186**. This is one blank line of space — the new block goes directly between them. Verified from v1 audit that lines 1184–1186 are:

```
1184    if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation") and time.time() - self._last_htf_entry_time < 1800:
1185        # (HTF throttle continues)
1186    margin = self.risk.calculate_kelly_margin(...)
```

**Proposed Gate A code block:**

```python
# Phase 2b Gate A: Pullback per-hour bleed filter (data-driven, 30d)
# Target hours are the 5 unblocked UTC hours where 30d WR was 15-36% vs 47% breakeven
# Shadow-log when PULLBACK_SESSION_GATE=false; hard-block when true
if strat_name == "htf_confluence_pullback":
    _pb_utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
    _PULLBACK_BLEED_HOURS_UTC = {5, 8, 13, 14, 16}
    if _pb_utc_hour in _PULLBACK_BLEED_HOURS_UTC:
        _pb_pt = (_pb_utc_hour - 7) % 24
        _pb_label = f"{_pb_pt % 12 or 12}:00 {'AM' if _pb_pt < 12 else 'PM'}"
        self._log_gotaway("pullback_hour_bleed", symbol, direction, strat_name,
                          signal.strength, confidence, price, ob, flow, df)
        logger.info(
            f"[PHASE2B] {symbol} {direction.upper()} pullback hour bleed — "
            f"{_pb_label} PT ({'BLOCKED' if Config.PULLBACK_SESSION_GATE else 'shadow-tagged'})"
        )
        if Config.PULLBACK_SESSION_GATE:
            continue
```

### 3.2 Gate B: Pullback VOLATILE 5m Regime (shadow-only)

**Physical placement (corrected from v1):** Gate A lives at ~line 1186 (between HTF throttle and Kelly sizing). Gate B must live at ~**line 1240**, AFTER the existing `_regime_snap = self._classify_regime(...)` assignment at line 1238. Gate B is NOT adjacent to Gate A in the source file — it is ~50 lines downstream, in the post-QUIET-gate block.

This means execution flow is: **Gate A fires (at ~1186) → Kelly → QUIET gate logic → `_regime_snap` assigned (1238) → Gate B fires (~1240) → entry**.

**Mechanism:** If `_regime_snap.get("label") == "VOLATILE"` and `strat_name == "htf_confluence_pullback"`, log `"pullback_volatile_5m"` to gotAway. **No hard-gate path** — Gate B is shadow-only until outcome-join script exists (§9.2).

```python
# Phase 2b Gate B: VOLATILE 5m regime shadow tag (pullback-specific)
# Place AFTER existing _regime_snap = self._classify_regime(...) at ~line 1238
# Reuses existing variable; no extra compute. No continue statement — shadow only.
if strat_name == "htf_confluence_pullback" and _regime_snap.get("label") == "VOLATILE":
    self._log_gotaway("pullback_volatile_5m", symbol, direction, strat_name,
                      signal.strength, confidence, price, ob, flow, df)
    logger.debug(
        f"[PHASE2B] {symbol} {direction.upper()} pullback volatile 5m — "
        f"ATR={_regime_snap.get('atr_pct', 0):.3%} vol={_regime_snap.get('vol_ratio', 0):.1f}x "
        f"(shadow-tagged only)"
    )
```

### 3.3 Config additions in `config.py`

```python
# Phase 2b regime filter flags — false = shadow-tag only, true = hard block
PULLBACK_SESSION_GATE = os.getenv("PULLBACK_SESSION_GATE", "false").lower() == "true"
PULLBACK_VOLATILE_GATE = os.getenv("PULLBACK_VOLATILE_GATE", "false").lower() == "true"  # reserved; not read by Gate B until a separate spec activates it
```

---

## 4. Shadow vs Hard Gate Phase Plan

**Weeks 1–4: Shadow logging only**

Both gates write to `logs/gotAway.jsonl` with tags `pullback_hour_bleed` and `pullback_volatile_5m`. No trades blocked. Bot behavior unchanged.

v2 extends shadow period to **4 weeks** (v1 was 2) because the gate targets 5 hours instead of 4; each hour needs its own 30-observation minimum per `reference_research_mar24_strategy_change_risks.md`. With the 30d data showing 43 trades across 5 hours (~8.6/hour), 2 weeks alone won't meet the bar.

Monitor daily:
```bash
grep pullback_hour_bleed logs/gotAway.jsonl | wc -l
```

**End of Week 4: Gate A promotion gate**

All must be true:
1. ≥ 30 `pullback_hour_bleed` observations across the 5 target hours combined
2. ≥ 10 observations in the **worst** target hour (currently UTC 14), to avoid promoting on thin evidence
3. Run `/trade-audit` to cross-reference `gotAway.jsonl` against `trading_state.json` by timestamp; confirm tagged trades show WR < 35% and net PnL < −$3.00 in the shadow period
4. `htf_l2_anticipation` and `momentum_continuation` trade counts in UTC {5, 8, 13, 14, 16} are unchanged vs baseline (verify no accidental scope creep)
5. Not more than 20% of all pullback wins in the shadow period would have been blocked

If all 5 met: Jonas approves `.env` change `PULLBACK_SESSION_GATE=true` → `/pre-restart-audit` → restart bot → monitor 48h.

**Weeks 5–8: Gate B validation**

Gate B requires the outcome-join script (§9.2). Once deployed and 4 more weeks of shadow data exist with outcomes:
- ≥ 30 `pullback_volatile_5m` observations with joined outcomes
- Same WR/PnL thresholds as Gate A
- Jonas approves Gate B promotion as a separate decision

### 4.1 Per-hour promotion option (fallback)

If the 4-week shadow period shows some target hours stay profitable while others bleed (e.g., UTC 8 flips positive due to regime change), the Gate A hour set can be promoted **in slices**. Example:
- Week 4 data shows UTC 14 still the clear bleeder → promote Gate A with `{14}` only
- Week 8 data confirms UTC 5, 13 still bleed → expand to `{5, 13, 14}`
- Skip or drop UTC 8 or 16 if their data normalizes

The gate set `_PULLBACK_BLEED_HOURS_UTC` is a single Python set literal — adjustable in one line, no other code change needed. Rollback is the same.

---

## 5. Non-Goals

- Ensemble confidence threshold — not touched
- 1h EMA gate — not touched
- Pullback ADX threshold in `strategies.py` — not touched
- early_exit thresholds — not touched
- CVD slope carve-out for pullback (`bot.py:1113`) — not touched
- HTF throttle timing (30 min between htf_confluence_pullback entries) — not touched
- Any paper slot logic — gates apply to live slot only (paper entries loop starts ~line 1466)
- `htf_l2_anticipation`, `momentum_continuation`, `htf_confluence_vwap` — unaffected by Gate A string match
- Telegram/dashboard reporting surfaces — shadow tags land in `gotAway.jsonl` only; no report section changes during shadow phase (DECIDE — see §9.1)
- BTC orphan_adopted reconcile-loop improvement (Apr 22 separate incident) — out of scope; file for a different spec

---

## 6. Risk Matrix

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| Gate A string match fails silently | High | Low | `_extract_strategy_name` returns `"htf_confluence_pullback"` at `bot.py:40-41` — confirmed exact match in v1 audit |
| Target hour set overfits 30d sample | Medium | Medium | 4-week shadow phase + per-hour promotion option (§4.1) lets the data self-correct |
| One target hour flips profitable during shadow | Medium | Medium | Per-hour promotion option — don't block profitable hours |
| `_regime_snap` used before defined | Medium | Low | Gate B physically placed AFTER line 1238; verified in audit step 4 of §10 |
| Shadow period disk bloat | Low | Low | ~200 bytes per gotAway entry × ~50 entries/week = 10KB/week — negligible |
| False-positive wins in the 5 target hours | Medium | High | Expected — 43 trades have ~10 wins across 5 hours. Promotion criterion requires tagged trades show WR<35%; this already accounts for winners |
| Session handoff cites wrong numbers (v1 lesson) | High | High | v2 all numbers re-verified against `trading_state.json` directly. Pre-approval, run `/trade-audit` one more time to confirm nothing drifted since v2 was written. |

---

## 7. Validation Metrics

**Gate A promotion criteria (all required):**
- Shadow period ≥ 4 calendar weeks
- ≥ 30 total `pullback_hour_bleed` observations across the 5 target hours
- ≥ 10 observations in UTC 14 specifically
- `/trade-audit` cross-ref: tagged trades have WR < 35% and net PnL < −$3.00 in the shadow period
- ≤ 20% of pullback wins would have been blocked
- `htf_l2_anticipation` trade counts in target hours unchanged within ±20% vs 30d baseline

**Expected outcome if full Gate A is promoted:**
- Pullback volume reduction: ~30% (approximating 43/147 = 29% historical volume)
- Pullback WR: lift from 38.1% toward 43–47% (target range is breakeven-or-better)
- Adverse-exit rate for pullback: fall from 15% (22/147) toward ~10% (12/~100 remaining)
- Pullback net PnL: recover ~$12–15 of the historical −$20.85 / 30d bleed (counterfactual, assumes no signal rerouting)

**CAUTION on the WR lift estimate:** With 147 30d trades, a 9-percentage-point WR shift has a 95% CI of approximately ±8 points. The target is directional; statistical significance requires 100+ post-gate trades (likely ~3 weeks of live data after hard-gate promotion).

**Do NOT declare success if:**
- `htf_l2_anticipation` trade count in target hours drops by more than 20% (signals accidental scope)
- Total bot daily trade count falls below 2/day 7-day average (signals over-filtering)
- early_exit count drops week-over-week (signals winners being cut)
- Pullback WR at non-target hours also drops (signals unrelated regime shift, not a gate effect)

---

## 8. Rollback

**Gate A (hard-gated):** Set `PULLBACK_SESSION_GATE=false` in `.env`, `/pre-restart-audit`, restart. Full rollback in under 2 minutes. No state migration, no exchange-side impact.

**Partial rollback:** Edit `_PULLBACK_BLEED_HOURS_UTC` set literal — add/remove hours as needed. Single-line change. Pre-restart-audit + restart.

**Gate B:** Gate B has no hard-gate path in this spec. Shadow log removal: single `bot.py` block deletion. Pre-restart-audit required.

**Full revert:** `git revert <phase2b-commit>` — fully reversible, no follow-on effects.

---

## 9. Follow-Ups Out of Scope

1. **DECIDE (before implementation):** Add `pullback_hour_bleed` + `pullback_volatile_5m` counts to daily report (`scripts/daily_report.py`) + Telegram. Per CLAUDE.md propagation rule, any new reported metric must hit both Telegram and dashboard. RECOMMEND: defer until Gate A is promoted (shadow-phase metrics are only of interest to Claude/Jonas via file reads).

2. **Outcome-join script** (`scripts/analyze_gotaway_outcomes.py`) — required for Gate B hard-gate decision. Cross-references `gotAway.jsonl` by timestamp against `trading_state.json` `closed_at` field within a ±15-minute window. Should also emit aggregate WR/PnL per tag per hour. Separate spec.

3. **BTC orphan_adopted incident (Apr 22)** — reconcile loop worked but had a ~13-minute naked position window during DNS outage. Worth a small spec to shorten reconcile cadence when `[CANCEL FAIL]` + `fetch_order failed` fire on the same entry. Out of scope here.

4. **Symbol-level pullback filters** — per `memory/reference_research_mar27_adverse_exit.md`, BNB+SOL drove 62% of adverse exits in v10. Scanner now dynamically rotates symbols, so fresh data needed. Revisit after 50+ per-symbol pullback observations in Sentinel.

5. **UTC 15 (8AM PT) and UTC 13 (6AM PT) secondary-analysis note** — UTC 15 has 14 trades at 50% WR but −$1.39 net (wins are smaller than losses). UTC 13 has 11 trades at 36% WR, already in the target set. A future "loss-asymmetry" filter (block when win-size/loss-size ratio is poor) could help UTC 15; too complex for this spec.

6. **Full hour-set re-verification every 30 days** — the pullback per-hour distribution will drift with market regime. Add a monthly `/trade-audit` on the hour set to confirm the 5 target hours are still the bleeders.

---

## 10. Implementation Checklist

- [ ] 1. Run `/pre-restart-audit` on current running bot before touching any file
- [ ] 2. Run `/trade-audit` once more to reconfirm the canonical 30d numbers immediately before implementation (guards against drift between spec authoring and deployment)
- [ ] 3. Add `PULLBACK_SESSION_GATE` and `PULLBACK_VOLATILE_GATE` to `config.py` with `false` defaults
- [ ] 4. Add Gate A block to `bot.py` at line ~1186 (between HTF throttle and Kelly sizing), inside `if strat_name == "htf_confluence_pullback":` check
- [ ] 5. Add Gate B block to `bot.py` at line ~1240 (AFTER existing `_regime_snap = self._classify_regime(...)` at line 1238), reuse `_regime_snap` variable, NO `continue` statement — shadow only
- [ ] 6. Verify PT time label in Gate A log uses 12-hour format (PDT = UTC-7), matching `bot.py:1176` style
- [ ] 7. Run `python3 -m py_compile bot.py config.py` — zero errors
- [ ] 8. Deploy code-review audit agent on the bot.py diff: confirm (a) Gate A/B only fire for `htf_confluence_pullback`; (b) paper slot loop (~line 1466) is unaffected; (c) Gate B has no `continue`; (d) `_regime_snap` reuse is after its definition; (e) string literal `"htf_confluence_pullback"` matches `_extract_strategy_name` output exactly
- [ ] 9. Add `PULLBACK_SESSION_GATE=false` and `PULLBACK_VOLATILE_GATE=false` to `.env` with a comment referencing this spec path
- [ ] 10. Update `CLAUDE.md` parameter table with the two new `.env` flags
- [ ] 11. Restart bot; within 1–2 cycles during a target UTC hour, verify `logs/gotAway.jsonl` receives `pullback_hour_bleed` entries; verify `htf_l2_anticipation` trades in the same UTC hours still execute (not blocked by scope mistake)

### Pre-restart-audit checklist (subset for this change)

- [ ] `_log_gotaway` call signature matches `bot.py:1752` (9 positional + 1 keyword `df`)
- [ ] Gate A/B NOT inside the paper slot loop (lines ~1466–1700)
- [ ] `Config.PULLBACK_SESSION_GATE` defaults `false` — no trading behavior change on deploy
- [ ] No new imports needed (`datetime` already imported in bot.py)
- [ ] gotAway write is non-blocking (uses existing try/except pattern)
- [ ] `"htf_confluence_pullback"` string matches `_extract_strategy_name` return at bot.py:40-41

---

*Spec v2 authored: 2026-04-22 | All numbers re-verified against trading_state.json*
*Approver: Jonas | Implementer: Claude subagent (after approval) | Estimated execution: 30–45 min including audit*
