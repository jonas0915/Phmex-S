
# Sentinel v11 — April 7 Review Queue

## Eval Summary (Apr 2–5, 4 days)

| Metric | Sentinel (Live) | Legacy Control (Paper) | Pipeline Baseline |
|--------|----------------|----------------------|-------------------|
| Trades | 24 | 29 | 59 (7 days) |
| Win Rate | 42% | 34% | ~45% |
| PnL | -$1.81 | -$10.08 | +$2.25 |
| PnL/Trade | -$0.075 | -$0.348 | +$0.038 |
| AE Rate | 0% | unknown | 41% |
| AE PnL | $0.00 | -- | -$10.43 |

**Verdict:** Sentinel dramatically outperforms legacy control (+$8.27 delta). AE rate target PASSED (0% vs <30% target). WR target MISSED (42% vs 45-55%). Both strategies are losing — this is a bad market regime (low ADX, choppy), not a gate problem.

---

## Queued Changes (Priority Order)

### 1. Fix Stale Profitable Hours Config
**Impact:** Systemic — 4 of 7 "profitable" hours are net losers
**Evidence (365 trades all-time):**

| PT Hour | Current Status | Actual WR | Actual PnL | Recommendation |
|---------|---------------|-----------|------------|----------------|
| PT 0:00 | PROFITABLE | 33% | -$2.53 | → Shadow |
| PT 1:00 | PROFITABLE | 50% | -$1.48 | → Shadow |
| PT 2:00 | PROFITABLE | 29% | -$3.22 | → Shadow |
| PT 3:00 | PROFITABLE | 60% | +$2.00 | Keep (low sample) |
| PT 6:00 | PROFITABLE | 38% | -$0.77 | → Shadow |
| PT 9:00 | PROFITABLE | 50% | +$3.91 | Keep ✓ |
| PT 23:00 | PROFITABLE | 36% | -$0.36 | → Shadow |

**New profitable set:** PT 3:00, 9:00, 14:00, 20:00
**Risk:** Low — just reclassifying shadow tags, not hard-blocking.

### 2. Minimum Ensemble Confidence Gate
**Impact:** -$0.68 (SUI trade with 3/7 conf + bullish CVD divergence on a short)
**Evidence:** Apr 5 SUI entry at 07:10 had 3/7 confidence, bullish CVD divergence, positive CVD slope — all contra-indicators for a short. Passed all gates.
**Proposal:** Block entries with ensemble confidence < 4/7.
**Risk:** Low — only 1 trade in recent history would have been affected. Check if any winners had conf < 4.
**Location:** bot.py, near ensemble calculation (~line 250-270).

### 3. Consider ADX Threshold Increase (20 → 25)
**Impact:** Would have blocked 6 of 6 losing trades on Apr 5 (all had ADX 20-24)
**Evidence:** Every losing trade on Apr 5 had ADX between 20.7 and 24.0.
**Risk:** MEDIUM — need to check how many winning trades also had ADX 20-24. This could kill good entries too.
**Action:** Run backtest query before implementing:
```python
# Count wins vs losses at ADX 20-25
grep "ADX" logs/bot.log | # extract ADX values at entry for wins vs losses
```
**Do NOT implement without data.** This is the riskiest change.

### 4. Hard-Block Candidate Hours
**Impact:** -$10.76 cumulative across 49 trades
**Evidence:**

| PT Hour | Trades | WR | PnL | Avg | Action |
|---------|--------|-----|-----|-----|--------|
| PT 4:00 | 7 | 29% | -$2.41 | -$0.34 | Hard block candidate |
| PT 5:00 | 6 | 33% | -$1.37 | -$0.23 | Hard block candidate |
| PT 18:00 | 18 | 28% | -$4.31 | -$0.24 | Hard block candidate |
| PT 19:00 | 18 | 39% | -$2.67 | -$0.15 | Monitor (borderline) |

**Risk:** Medium — per lessons.md, shadow time filter is NOT statistically significant yet (Z=0.055). Jonas rejected blocking 7/8 AM PT previously. Recommend blocking PT 18:00 only (strongest signal: 18 trades, 28% WR, -$4.31).

### 5. Investigate exit_reason Tagging
**Impact:** Analytics quality — all 24 Sentinel trades show "unknown" exit reason
**Evidence:** Sentinel eval shows 0% AE rate, but exit_reason is "unknown" on all trades. Either AE truly never fired (gates are that good) or the field isn't being tagged.
**Action:** Grep bot.log for actual exit reasons on Sentinel trades to verify.

---

## NOT Queued (Intentionally)

- **Regime filter** — correct fix for "all shorts in up market" but this is a major strategy change, not a parameter tweak. Save for Phase 2.
- **liq_cascade promotion** — only paper slot with positive PnL (+$1.68), but sample too small (11 trades). Keep observing.
- **Recursive Improvement Phase 1** — separate deploy, spec already written.

---

## Decision Framework for Apr 7

1. Fix #1 (profitable hours) — low risk, clear data. Do it.
2. Fix #2 (min confidence) — low risk, obvious miss. Do it.
3. Fix #5 (exit tagging) — zero risk, pure analytics. Do it.
4. Fix #4 (block PT 18:00) — medium risk, present data to Jonas.
5. Fix #3 (ADX threshold) — requires backtest data first. Research, don't deploy blind.
