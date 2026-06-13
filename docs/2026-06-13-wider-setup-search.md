# Wider-Setup Edge Search — 2026-06-13

Goal: find a wider entry setup with positive edge (the live strategy fires only
~2-4×/day; bottleneck is "no confluence signal", not the gates — see funnel
analysis below). 4 parallel OOS searches on `logs/flow_capture.jsonl` (163k
snapshots, 38 symbols, 2026-05-11→06-13, ~75s cadence — NO survivorship).

Discipline (all four): chronological 50/50 train/test, params chosen on TRAIN
and reported on TEST only, net of MEASURED fee 0.0663% RT (and 0.12% taker),
no look-ahead (at-or-before lookup), random-entry baseline + (where relevant)
direction-shuffle control. Scratch: `scripts/research/wider-setup-2026-06-13/`.

## Results

| Hypothesis | Verdict | Key numbers (TEST) |
|---|---|---|
| Pure price reversion/momentum | **NO EDGE** | revert gross +0.011%/t, random p=0.47; momentum p=0.95. Fee-negative. |
| Liquidity / spread / depth | **NO EDGE** | depth_ratio faint contrarian 2-4bps (ρ≈−0.035), sub-fee; no TP/SL config net-positive OOS; spread/walls/illiquid = nothing |
| Divergence flag as predictor | **NO EDGE** | sub-bps, mostly wrong sign, random p≥0.30 all horizons. Only useful as a gate, never a signal. |
| **Cross-symbol (alt-vs-ETH) reversion** | **WEAK LEAD (maker-only)** | gross +0.093%/t, **beats random p=0.000 + shuffle p=0.000**, WR 59.5%, ~15/day. net: taker −0.027%, **maker +0.028%**. TRAIN was NEGATIVE. BTC-anchor = null (p=0.50). |
| **High-vol reversion** (fade extremes in high vol) | **WEAK LEAD (maker-only)** | gross +0.079%/t, beats random p=0.000, ~399/day. net: taker −0.041%, **maker +0.013%**. WR 42%. |

## The meta-finding

Two independent agents (cross-symbol, vol-regime) converged on the SAME thing:
**short-horizon mean reversion genuinely works gross and beats random + shuffle
controls** — but dies at taker fee, survives only marginally at maker. This is
the THIRD independent confirmation of the same pattern (imbalance study 2026-06-01,
maker-fee ground truth 2026-06-11, now this). **The exploitable edge here is an
EXECUTION (maker-fill) edge, not a signal edge.**

## Hard caveats (why this is a lead, not a deployable edge)
1. Gross +0.09% < one taker RT fee (0.12%). Maker-only, razor-thin (+0.013–0.028%/t net).
2. TRAIN-negative / TEST-positive on the cross-symbol config → regime-luck risk; needs a 2nd OOS window.
3. **Maker fills UNPROVEN** — 75s flow cadence can't validate passive-limit fills (the exact wall from 2026-06-01). Needs `logs/l2_ticks/` sub-second data (accumulating since 6/12, ~1-2 wks to usable, only BTC/ETH/INJ/ARB).
4. Ruled-out (don't retest): OB imbalance (both dirs), buy_ratio/cvd_slope/large_trade_bias (zero-signal negative controls), hour-of-day, confidence floor.

## EXECUTION DEEP-DIVE (2026-06-13, L2 tick data — the make-or-break test)

Used logs/l2_ticks/ (book + trade prints, BTC/ETH/INJ/ARB). CAVEAT: trade prints
only exist for 2026-06-13 (~16h, one session) — directional first-pass, not
bankable to a decimal. Scratch: scripts/research/execution-2026-06-13/.

**Fill rate (passive limit at touch, 20-25s window):** BTC/ETH ~35%, INJ ~20-30%,
ARB 5-30%. Infinite-patience cap ~50-57%. The unfilled half is adversely selected.

**Adverse selection splits by spread width (THE finding):**
- BTC/ETH: 1-tick spreads (~0.016 bps) → no half-spread to capture; maker fee
  (0.02% RT) alone exceeds it; reversion fills eat ~1.4 bps more. Net −2.3 to
  −3.8 bps. STRUCTURALLY DEAD.
- INJ/ARB: wide spreads (7-12 bps) → capture > adverse+fees IN ISOLATION
  (+4 to +8.5 bps) BUT fill rate is 5-30% and Agent B's number doesn't model
  fill rate; the wide spread that makes it profitable is why you can't get filled.
- The triangle that can't be squared: where there's spread to capture you can't
  fill; where you can fill there's no spread. Classic MM problem, lost at $56.

**Reversion re-validation (walk-forward, K=4/6 folds):** gross signal TIME-STABLE
and direction-real (shuffle-significant most folds), but net-of-fee NOT viable —
Family A (alt-vs-ETH) mean OOS −0.001 to −0.008%/t at maker_RT; Family B (high-vol)
−0.036 to −0.039%, negative 9/10 folds. Original lead was regime-luck at NET level.
Only positive cells are fragile grid corners on rare big TP hits, sub-50% WR.

**Current bot execution (PID 69117):** entries 98.9% maker (post-once-20s-skip, no
chase, no taker fallback). Maker exits shipped today NOT yet exercised live (n=2,
exchange resting TP/SL wins the race every time → reduceOnly-abort, handled
correctly). GAP: open_long/open_short hard-code the touch price (exchange.py:485,537)
— a maker-reversion entry can't post at a caller-supplied deeper price; _try_limit_entry
accepts limit_price but the public wrappers don't pass it. Minor: live-exit watcher
(bot.py:2100/2102) passes no urgent arg → even watcher TP goes taker.

**META-VERDICT:** the maker-fill wall is real and now quantified. Not a plumbing
fix — a structural spread/fill/adverse triangle a $56 account can't win vs MMs.
4th independent confirmation of "no capturable edge at this size" (cf June 1
recommendation to halt real-money). The ONLY thread not fully killed: passive
spread-capture on wide-spread alts (INJ/ARB) with a JOINT fill+adverse+directional
model over more L2 data (needs ~1-2 wks). Expected value of further digging: low.

## 1h VOL-EXPANSION FADE — found then KILLED by independent verification (2026-06-13)

A higher-TF search agent reported a "1h vol-expansion fade" (fade bars with range
>3×ATR14, hold 12h) at OOS +0.26%/t, Sharpe 3.4, 7/8 months. INDEPENDENT
re-derivation from scratch (full year, walk-forward) KILLED it: full-sample
−0.187%/t, Sharpe −2.45, bootstrap CI [−0.333,−0.040] (significantly NEGATIVE);
honest train→test loses; legs flip sign by regime (noise); walk-forward 1/5 folds
positive. It was selection bias on one 50/50 split. DO NOT DEPLOY. Lesson: the
better a backtest headline looks on this single-regime data, the more it needs
independent re-derivation — every backtest edge this session died under scrutiny.

USEFUL BYPRODUCT: the longer-hold slot architecture is now fully mapped (how to add
a 12h-hold slot without breaking the scalper's 4h time-exit) — reusable for any
FORWARD-tested candidate. Plan in agent output / this session.

Funding harvest: RULED OUT (disguised directional bet, single-venue). Phemex has
NO retail maker rebate (best case maker→0% at $380M vol). Scalping fee-trap confirmed.

## Recommended next steps (NOT done — pending Jonas)
1. Do NOT deploy. Marginal, maker-dependent, fill-unproven, possible regime luck.
2. Re-validate cross-symbol reversion on a fresh OOS window once more flow data accrues (kill/confirm regime-luck).
3. When L2 data matures (~late June): test whether maker fills are REAL for a reversion entry — the actual make-or-break question, finally testable. Today's maker-exit infra (urgency-gated exits) is the execution prerequisite, now in place.
4. Optional: a paper slot for cross-sym/high-vol reversion w/ maker-only execution to accumulate forward evidence (cf. 5m_mean_revert — consistent: reversion is the least-bad live strategy).
