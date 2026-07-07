# R3 — Paper-Simulation Fee Model Fix (2026-07-05 overnight)

**Status: SHIPPED to repo. NO restart — takes effect on next bot restart.**

## Problem (from r2_fee_research.md)

Paper slots charged `(TAKER_FEE_PERCENT + SLIPPAGE_PERCENT) x 2 = 0.22%` round-trip,
but the live bot's measured cost is ~0.066% RT because entries are ~99% PostOnly maker
(0.01% fee, no slippage possible on a resting order). Every paper strategy was
over-penalized ~$0.23/trade, distorting paper-vs-live comparisons.

## Fix (structural, not curve-fit)

New paper RT fee = **maker entry leg + taker+slippage exit leg = 0.01 + (0.06 + 0.05) = 0.12%**
of notional. Deliberately conservative vs the ~0.066% measured (assumes taker exit,
true for 81% of live exits) — paper should never flatter.

## Changes

| File:line | Change |
|---|---|
| `config.py:92-98` | Added `MAKER_FEE_PERCENT` (env-driven, default `0.01` — Phemex verified base maker rate), comment cites r2_fee_research.md |
| `risk_manager.py:638-650` | `close_position` paper branch: `fee_pct = (MAKER + TAKER + SLIPPAGE) / 100` (was `(TAKER + SLIPPAGE) * 2 / 100`), full rationale comment |
| `risk_manager.py:777-782` | `partial_close_position` paper branch: same model on half notional |
| `tests/test_paper_fee_model.py` | NEW — 4 tests (see below) |

These are the ONLY two paper-fee simulation sites in the codebase (repo-wide grep for
`TAKER_FEE_PERCENT|SLIPPAGE_PERCENT`).

## Live trades verified COMPLETELY unaffected

- The simulation runs only when `fees_usdt is None` AND `self.is_paper` (risk_manager.py:637-638, 768-769).
- Every live close call passes a float `fees_usdt` from the exchange:
  main bot `bot.py:887,934,962,989,1015,1077,1155,2471` via `extract_order_fee`
  (`exchange.py:710` — returns `0.0` if unresolvable, never `None`);
  live-slot closes `bot.py:2855,2962` likewise; sync closes `bot.py:2771,2798`
  pass `sync_fee` (float, initialized 0.0). A live 0-fee close is tagged
  `fees_pending` for reconciler backfill — never simulated.
- Paper-slot closes (`bot.py:2932`, no `fees_usdt` arg) are the only callers that hit the sim.

## NOT changed (deliberate)

- `backtest.py:962` — replay rig default `fee_rt_pct = (TAKER_FEE_PCT + SLIPPAGE_PCT) * 2`
  = **0.22% RT, now DIFFERS from the 0.12% paper model**. Left alone per plan (rig fee
  model validated separately; it already has a `--fee-rt` CLI override documented with
  the measured 0.0663 at backtest.py:1919-1924).
- `scripts/slot_lab/mean_revert_replay.py:74` — own `TAKER_FEE = 0.06` constant (rig).
- `risk_manager.py:267` — breakeven-SL 0.25% buffer comment mentions the old 0.22% RT;
  that buffer applies to live too and stays conservative — not a paper fee deduction.

## Tests

`tests/test_paper_fee_model.py` (fee constants pinned via monkeypatch):
1. Paper close charges exactly 0.12% of notional, netted into pnl_usdt; regression guard vs old 0.22%.
2. Paper partial close charges 0.12% on half notional.
3. Live close with exchange fee: pnl_usdt stays GROSS, fee passed through, no sim.
4. Live close with unknown fee: fees_usdt stays 0.0 + `fees_pending` tag, no sim.

**Full suite: 338 passed (334 prior + 4 new).** `py_compile` clean on config.py,
risk_manager.py, tests/test_paper_fee_model.py.

## Effect on existing data

Historical paper records are NOT rewritten — closed_trades keep the fees they were
charged at close time. Only new paper closes after the next restart use 0.12%.
Paper-vs-live comparisons spanning the change date must account for the model switch.
