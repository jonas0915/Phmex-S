# 5m_mean_revert long/short side split — 8/1/2026

**Question:** does 5m_MR's edge live on one side? (Prompted by the 7/12 drift-gate finding: blocked MR longs lose, shorts got the buy_ratio exemption.)

**Verdict: asymmetry SUPPORTED at this n — the edge is on the short side.** Live-era diff CI (95%) excludes zero, and the pre-promotion paper era independently shows the same sign with its own CI excluding zero. Longs are net-negative in both eras; every dollar of the slot's profit has come from shorts. Caveat: n=7 live longs is tiny, and the live CI upper bound (−$0.03) barely clears zero — this is ~95% evidence, not proof.

## Data & conventions

- Source: `trading_state_5m_mean_revert.json` — 39 closed trades, 0 open, `trade_results` empty.
- Era split: `mode == "live"` (19 trades, 6/18–7/31 closes) vs no `mode` key (20 trades, 3/28–6/12) = pre-promotion paper. Promotion timestamp 1781269364 (≈6/12) confirmed in `trading_state_5m_mean_revert_mode.json`.
- Net convention (verified read-only in `risk_manager.py` `close_position`, ~lines 700–764): `net_pnl = gross − fees − funding` in both modes; paper additionally folds sim fees into `pnl_usdt` (line 731) so paper `pnl_usdt == net_pnl`. Rule used: `net = net_pnl` where present, else `pnl_usdt` (only the 3 oldest paper trades, which predate fee sim). This sidesteps the known dashboard fee double-subtract bug entirely.
- Artifacts: `scripts/research/mr-side-split-2026-08-01/` — `side_split.py` (script), `results.json` (full per-trade output), `tape_gate_lines.txt` (gate telemetry).

## LIVE era (primary, since 6/12 promotion) — n=19, net +$15.40

| | LONG | SHORT |
|---|---|---|
| n | 7 | 12 |
| WR | 28.6% (2W) | 83.3% (10W) |
| Net total | **−$1.17** | **+$16.57** |
| Net/trade | −$0.167 | +$1.381 |
| Avg win / avg loss | +$2.00 / −$1.04 | +$2.00 / −$1.70 |
| Worst | −$1.86 (INJ 7/18) | −$1.93 (XRP 7/22) |
| Exit mix | 4 exchange_close, 2 hard_time_exit, 1 min_margin_skip | 9 exchange_close, 3 hard_time_exit |

Notes: winners on both sides average ~+$2.00 — the asymmetry is win RATE, not payoff. Live long wins: WLD 6/18, XLM 7/10; everything after 7/10 on the long side lost (5 straight, incl. the 7/26 XRP `min_margin_skip` fee-only −$0.105 anomaly). Live shorts' only losses: XLM 6/24, XRP 7/22.

**Bootstrap diff (long − short net/trade), house rule (independent per-side resample, then diff; 20k reps, seed 42):**
- Live era: point −$1.548, **95% CI [−2.99, −0.03]**, 90% CI [−2.77, −0.27], P(diff<0) = 97.7%

## Paper pre-promotion era (secondary, 3/28–6/12) — n=20, net +$2.50

| | LONG | SHORT |
|---|---|---|
| n | 11 | 9 |
| WR | 36.4% (4W) | 66.7% (6W) |
| Net total | **−$5.48** | **+$7.98** |
| Net/trade | −$0.498 | +$0.887 |
| Avg win / avg loss | +$0.76 / −$1.22 | +$1.60 / −$0.54 |
| Worst | −$3.10 (WLD 5/23) | −$0.65 (AAVE 4/26) |
| Exit mix | 4 stop_loss, 3 hard_time_exit, 2 adverse_exit, 2 take_profit | 6 take_profit, 2 adverse_exit, 1 hard_time_exit |

- Paper era diff: point −$1.385, **95% CI [−2.46, −0.31]**, P(diff<0) = 99.5%. All 4 stop_loss exits in this era were longs; 6 of 6 paper short TPs hit.
- Combined all 39 (secondary): long −$6.65 over 18, short +$24.55 over 21; diff 95% CI [−2.45, −0.61].

The paper era predates the 7/12 drift-gate observation, so it functions as quasi-independent confirmation of the same sign — this is not one lucky month.

## Gate telemetry cross-check (bot.log, coverage 7/11 → 8/1)

20 unique `[TAPE GATE] 5m_mean_revert ... blocked` lines across `bot.log`..`bot.log.5` (lines carry the `[PAPER]` tag — gate evaluated in the signal path; the slot itself is live):

- LONG blocks: 8 — 7 of them `buy_ratio` (9%–45%), 1 bearish divergence.
- SHORT blocks: 12 — 6 bullish divergence, 4 large-trade-bias, 2 `buy_ratio` (both 7/11–7/12, i.e. **before** the 7/12 short exemption; zero since, as designed).

So in raw counts shorts are blocked slightly more, but the *buy_ratio* gate now fires almost exclusively on longs (7 long blocks in 3 weeks vs 0 eligible short blocks) — consistent with the 7/12 finding that longs need protection and shorts don't. Bounded check only; logs before 7/11 are rotated away.

## Honest caveats

1. n=7 live longs. The live-era CI upper bound is −$0.03 — a hair inside significance. One good long trade would reopen the question.
2. Hypothesis was suggested by the 7/12 drift-gate work (same regime); the paper era mitigates but doesn't eliminate look-elsewhere concerns.
3. Short profits are concentrated in ~+$2.4 exchange_close TP wins in a market that kept mean-reverting downward moves; regime dependence untested.
4. This ledger reflects trades that PASSED the existing gates — the long-side numbers are already post-protection (drift gate, buy_ratio). Unprotected longs would presumably look worse (per 7/12: blocked longs lose).

## Smallest reversible intervention (if acted on — NOT an immediate live change)

Pre-registered forward test, adjudicator-graded, per house practice:

- **Register a verdict line on live MR longs as-is**: over the next 8 live 5m_MR longs, KILL the long side if long net ≤ 0 (block via a new `MR_LONG_DISABLED` env flag or `.block_mr_longs` sentinel), PASS if net > 0. Zero code-behavior change today; pure counter + pre-commitment. At ~7 longs/6 weeks this resolves in ~6–7 weeks.
- Rollback if ever armed: delete the sentinel / flip the flag — no restart-coupled logic.
- Do NOT silently tighten long gates now: that would contaminate the test and repeat the pattern the 7/20 VWAP-filter rejection warned about (post-hoc filters on a small ledger).

Owner go required before registering anything.
