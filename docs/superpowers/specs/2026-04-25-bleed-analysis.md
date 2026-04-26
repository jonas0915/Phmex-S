---
title: 14-day Bleed Analysis (REWRITTEN AFTER VERIFICATION)
status: NO ACTION RECOMMENDED — every quantitative recommendation refuted by independent replay
created: 2026-04-25
revised: 2026-04-25 (post-verification)
author: 3 investigation agents + 3 verification agents (independent)
---

# Bleed Analysis 2026-04-25 — VERIFIED

## Why this spec was rewritten

The first version proposed "trail-to-breakeven at peak ROI ≥ +3%" as the highest-impact fix, claiming +$4.50 to +$6.00 over 14 days. **Independent OHLCV-replay simulation showed the actual delta is -$0.20** — a small NET LOSS. The mechanism rescues 11 losing trades (+$4.23) but equally caps 10 genuine winners (-$4.43). Net ~zero across triggers from 2% to 5%.

This rewrite reports only verified numbers and withdraws every quantitative recommendation that didn't survive replay.

---

## What was VERIFIED

| Claim | Verified value | Method |
|---|---|---|
| Hours filter location & contents | bot.py:1172 `_BLOCKED_HOURS_UTC = {0,1,2,9,17,18,19,20}` (verbatim match) | Direct read |
| Today's 1 trade | ASTER short adverse_exit, net -$0.4405 | trading_state.json |
| Yesterday's 6 trades | 2W/3L/1skip, net -$0.4260 | trading_state.json |
| Peak balance | $74.78 | trading_state.json |
| All AEs in window are losses | 0 of 22 had net_pnl ≥ 0 | trading_state.json |
| AE counterfactual DIRECTION | Looser AE = bigger loss; tighter cycles ≈ neutral | 1m OHLCV replay vs Phemex |
| AE rule is doing its job | Confirmed by counterfactual | Replay |

## What was REFUTED

| Spec claim | Actual | Severity |
|---|---|---|
| 81 trades, -$3.40 net (14d) | 75 trades, -$3.71 (or 71/-$2.33 strict 14d) | Minor |
| 27 AEs, -$14.58, 33.3% rate | **22 AEs, -$11.77, 29.3% rate (BELOW the 30% line)** | Material |
| Evening pullback: 9 trades, -$1.11 | **11 trades, 18.2% WR, -$2.11** | Material — bleed is worse than first claimed |
| 88.9% of AEs had peak > 0 anytime | 77.8% (21/27) | Overstated |
| Trail-to-breakeven at +3% captures +$4.50 to +$6.00 | **-$0.20 net (loss)** | **Headline recommendation collapses** |
| PT 18 is the only statistically significant hour, Z=-2.12 | **PT 18 Z=-0.98 — NOT significant** | PT-18 block recommendation collapses |
| PT 18 sample: 0/6, -$4.80 | n=7, wins=1, net=-$4.16 | Numbers wrong |
| Phmex-S has zero unit tests | **4 test files / 12 test functions in `tests/`** | Memory-system error — affects Phase 2 v2 audit risk classification |

## What was STRONGER than the spec claimed

- **63% of AEs (not 51.9%) had peak ROI > 0 after the cycle-10 AE-eligibility window.** The "trades go briefly profitable then bleed back" pattern is real and stronger than first reported. **However, the proposed fix (trail-to-breakeven) does not capture this profit because it equally caps the genuine winners.** The pattern is a real phenomenon without a known good lever.
- **PT 20 is statistically significant as a WINNING cluster:** 12 trades, 9 wins (75%), net +$2.36, Z=+3.24. Currently NOT in the blocklist (allowed). No action needed; just noting that real signal exists in the data.

---

## Verified status of the entry / exit pipeline

### AE rule
- **Working as designed.** -3% / 10 cycles is the correct severity. Loosening to -4% costs $2.52 / 14d more; -5% costs $5.05 more. Tighter cycles produce a marginal benefit too small to discriminate.
- **AE is a symptom, not the disease.** It's correctly cleaning up bad entries.

### Hours filter
- Live blocklist `{0,1,2,9,17,18,19,20}` UTC at bot.py:1172. No hour reaches |Z|≥1.96 as a LOSING cluster on 30d data. Only PT 20 hits significance — as a winner, already allowed. **No data-driven case for changing the filter.**

### Evening pullback (PT 17-23) on htf_confluence_pullback
- 11 trades, 18.2% WR, -$2.11 net over 14d. Worse than initially reported.
- **But:** sample is small (n=11), no |Z|≥1.96 hour inside it, and the evening losses share characteristics (low trade_count tape skip, high ATR%, illiquid alts) that are addressable but not via a global hour gate.
- A shadow-only strategy-aware gate (`htf_confluence_pullback` blocked when ATR% > 0.4% AND PT ∈ {20,21,22,23}) is the only directionally-supported intervention — but at the current sample size, it's a hypothesis, not a recommendation.

---

## Withdrawn recommendations (reasons)

| # | Original recommendation | Withdrawal reason |
|---|---|---|
| 1 | Trail-to-breakeven at peak_roi ≥ +3% | Replay shows -$0.20 (loss), not +$4.50 to +$6.00 (claimed). Saves losers but caps winners 1-for-1. |
| 2 | Block conf=4 entries when tape gate skipped | Premise depended on the evening-bleed magnitude, which itself is small (n=11, -$2.11). Could be valid but needs more data + own simulation pass before recommending. |
| 3 | Block PT 18 (UTC 1) | Z=-0.98, not -2.12. Sample 7/1/-$4.16, not 6/0/-$4.80. Not statistically significant. |
| 4 | Shadow ATR ceiling for evening pullback | Still directionally defensible but no longer urgent — evening bleed is small in absolute terms. Defer until more data. |
| 5 | "Memory hygiene" fix for hours filter | Still valid — hours filter IS at bot.py:1172, not bot.py:881. Update lessons.md / MEMORY.md. |

---

## What the data actually supports

**No high-confidence action is available right now.**

- AE rule is verified-correct.
- Hours filter has no data-driven adjustment to make.
- Trail-to-breakeven is verified-net-zero.
- Evening pullback bleed is real but small (-$2.11 / 14d) and the only credible fix is shadow-only.
- 14-day sample is too thin to support tighten/loosen calls on most parameters.

**The right move is: wait for more data + fix the verified factual errors in memory + ensure agent recommendations include actual simulation, not estimates.**

---

## Lessons captured (separate commit to memory/lessons.md)

1. **Repo is NOT zero-tests** — `tests/` has `test_ae_exit_rule.py`, `test_kill_switches.py`, `test_postonly_param.py`, `test_weekly_forensics.py`. The Phase 2 v2 audit's "RISKY without unit tests" classification was based on a wrong premise; some areas DO have coverage.
2. **Agent impact estimates require actual simulation, not vibes.** The first agent estimated +$4.50 to +$6.00 for trail-to-breakeven; OHLCV replay showed -$0.20. Never trust an impact number an agent didn't actually compute against bar-by-bar data.
3. **Cross-verify counts before building a thesis.** Trade counts in the first pass were off by 6+ trades and PnL by ~$3. Always have a second agent independently re-derive headline numbers from raw data before any recommendation is built on them.

---

## Files referenced
- trading_state.json (closed_trades, n=486)
- bot.py:1172 (verified live filter)
- risk_manager.py:200-209 (AE rule)
- tests/ (4 test files — memory was wrong about this)
- /tmp/be_sim.py, /tmp/be_sim_results.json, /tmp/verify_bleed.py, /tmp/verify_hours.py (verification artifacts)
