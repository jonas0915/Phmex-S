# R1 — Partial-TP Threshold Head-to-Head (+6 / +10 / +12 ROI)

**Date:** 2026-07-05 (overnight run) · **Verdict: NULL — no variant clears the rig's ±25% exit-model error. Keep PARTIAL_TP_ROI=10.**

Sanctioned lever per `memory/reference_sl_loss_levers_2026-07-02.md` ("REMAINING UNTESTED #2:
Partial-TP threshold variants — never head-to-head"). This is the last untested TP-side knob.

## What was built

The replay rig (`scripts/calibrate_exits.py` + `backtest.py check_exits_live`) previously did NOT
model partial-TP (documented limitation). Extended it with a faithful port of the live logic:

- **Live source ported:** `bot.py:859-905` (scale-out half at +PARTIAL_TP_ROI margin-ROI at a 60s
  cycle price, before early_exit in the cycle) + `risk_manager.py:748-829` (halve amount/margin,
  leave SL/trail/peak untouched, lift `take_profit` to +PARTIAL_RUNNER_TP_ROI, cancel the stale
  resting exchange TP → runner TP becomes software-enforced).
- **Rig changes (research code only — no live bot files touched):**
  - `backtest.py`: `BTPosition` gains `scaled_out` / `partial_exit_price` / `partial_exit_epoch` /
    `tp_is_software` (all default-off); module knobs `PARTIAL_TP_ROI` / `PARTIAL_RUNNER_TP_ROI`
    (default `None` = off); step **0b** in `check_exits_live` (fires at cycle price after the
    intra-bar resting-order check, before early_exit — live ordering); `_resting_order_hit` skips
    `tp_price` once `tp_is_software` (live cancels the resting TP on scale-out, bot.py:897-900).
  - `scripts/calibrate_exits.py`: `--partial-tp-roi` / `--runner-tp-roi` CLI knobs (wired through
    `apply_exit_overrides`); PnL accounting = half banked at `partial_exit_price` + half at final
    sim exit; dump rows gain `sim_scaled_out` / `sim_partial_px`.
  - `py_compile` clean on both files.
- **Live scaled-out entries replay correctly by construction:** live partial-TP trades appear in
  `trading_state.json` as two half-size rows sharing one entry; PnL is linear in size, so applying
  sim partial-TP to each half aggregates exactly like one full position.

## Regression check (knob off ⇒ rig unchanged)

Pre-change baseline run (June window, `--trail-arm-roi 8`) dumped before any edit, re-run after:
**86/86 rows identical on every pre-existing field, totals identical, 0 diffs** (only additive
fields `sim_scaled_out`/`sim_partial_px` appear, all false/null). PASS.

## Run setup

`python3 scripts/calibrate_exits.py --window-start 2026-06-01 --window-end 2026-07-04
--data-dir backtest_data_june --trail-arm-roi 8 [--partial-tp-roi N --runner-tp-roi 25]`

- `--trail-arm-roi 8` on ALL runs (live parity since tonight — mandatory).
- 86 live htf_l2_anticipation entries replayed; intra-bar path ~77% bar-close fallback
  (June flow coverage is thin — adds to model error).
- Dumps: `reports/ptp_june_off.json`, `ptp_june_6.json`, `ptp_june_10.json`, `ptp_june_12.json`.
- Live actual for the window: net **+$12.47** (sim baseline +$14.57, +16.8% — inside the rig's
  known error band).

## Results (sim net, net of actual live fees, n=86)

| variant | sim net | Δ vs off | WR | avg win | avg loss | H1 (→6/17) | H2 | Δ H1 | Δ H2 | scale-outs |
|---|---|---|---|---|---|---|---|---|---|---|
| **off** | **+$14.57** | — | 68.6% | +$0.721 | −$1.036 | +$3.94 | +$10.64 | — | — | 0 |
| ptp 6 / runner 25 | +$15.12 | **+$0.55 (+3.8%)** | 68.6% | +$0.675 | −$0.915 | +$3.52 | +$11.60 | −$0.41 | +$0.96 | 52 |
| ptp 10 / runner 25 (live) | +$14.38 | −$0.19 (−1.3%) | 68.6% | +$0.718 | −$1.036 | +$3.90 | +$10.48 | −$0.03 | −$0.16 | 26 |
| ptp 12 / runner 25 | +$14.29 | −$0.28 (−1.9%) | 68.6% | +$0.716 | −$1.036 | +$3.33 | +$10.96 | −$0.60 | +$0.33 | 14 |

Half-split boundary = 2026-06-17 12:00 UTC (5:00 AM PT). All variants are positive in both
halves in absolute terms — but so is the baseline, so the meaningful bar is the **improvement**
per half, and **no variant's delta is positive in both halves** (ptp6: −/+; ptp10: −/−; ptp12: −/+).

## Which trades change and why

- **WR never changes (59/86 in all four runs)** — partial-TP never flips a trade's sign here; it
  only reshapes magnitudes.
- **ptp 6 (52 scale-outs, 29 helped / 23 hurt):** gains come from losers that peaked ≥+6% ROI then
  reversed — banking half shrinks the round-trip (TAO short +$0.98, ADA long +$0.96, ETH
  hard_time +$0.70, HYPE +$0.63 — avg loss improves −$1.036 → −$0.915). Losses come from capping
  half of every big winner at +6% while the runner (resting TP cancelled, target lifted to +25%)
  early-exits below the old +16%-ROI exchange TP (INJ −$0.68, XLM −$0.58, AAVE −$0.56, WLD −$0.50,
  −$0.48…). Net ≈ wash: +$0.55.
- **ptp 10 (26 scale-outs, 18 helped / 8 hurt):** the "hurt" trades are exactly the exchange-TP
  winners whose runner half loses the resting +1.6% TP (exchange_close → early_exit lower); the
  banked-half gains on the rest almost exactly cancel. Net −$0.19 — the live setting is
  PnL-neutral in this window per the rig.
- **ptp 12 (14 scale-outs):** too few triggers to matter; same TP-cancellation drag on the same
  big winners. Net −$0.28.
- The recurring single largest hurt (INJ long 6/14, −$0.68 in all three variants) is a full
  +16%-ROI resting-TP winner whose runner half gives back to +9% before early_exit.

## Does anything clear the ±25% exit-model error?

No. The rig's documented exit-model error is ±25% of window net (~±$3.6 on a +$14.57 base;
sim-vs-live delta this window is itself +16.8%). The best variant delta is **+$0.55 (3.8%)** —
an order of magnitude inside the noise floor. Deltas this size are unmeasurable with this
instrument, and none passes the both-halves improvement bar either.

## Verdict

**NULL.** Partial-TP threshold is not a lever: 6/10/12 all land within ±4% of baseline, WR
untouched, no variant improves both halves, nothing clears model error. The current live
setting (PARTIAL_TP_ROI=10, RUNNER=25) is as good as any — **no change recommended, no restart
needed.** This closes the last untested TP-side item in the exit-geometry inventory
(`reference_sl_loss_levers_2026-07-02.md`); exit side remains COMPLETE — fix entries, not exits.

## Artifacts

- Rig extension: `backtest.py` (BTPosition fields, PARTIAL_TP knobs, check_exits_live step 0b,
  `_resting_order_hit` software-TP skip), `scripts/calibrate_exits.py` (CLI + accounting).
- Per-trade dumps: `reports/ptp_june_{off,6,10,12}.json` (knobs recorded in each).
- Regression proof: pre-change baseline in scratchpad diffed 0/86 vs `ptp_june_off.json`.
