# SR_BOUNCE counterfactual lever lab — 2026-07-29

Scratch replay (`lever_lab.py`), TRAIN window only (signal_ts < cut, cut mirrors run_scan.py's split logic). Frozen originals (`sr_levels.py`, `sr_signal.py`, `engine.py`, `fetch_data.py`) untouched.

TRAIN cutoff: signal_ts < 1782671100000 (2026-06-28T18:25:00+00:00 UTC)

Regenerated baseline TRAIN (this harness, full 90d replay): **n=8706, WR 24.9%, net $-634.44, net/trade $-0.0729**
Frozen scan's reported baseline TRAIN (reference): n=8703, net/trade $-0.0729

Cross-check vs frozen scan: trade-count diff +3 (+0.0%), net/trade diff $+0.0000. All lever deltas below are computed against **this harness's own regenerated baseline** (same code, same data, same split) for an apples-to-apples comparison; the frozen scan's number is shown above for reference only.

## Per-lever TRAIN results

| Lever | Description | Trades | WR | Net | Net/trade | Δ vs baseline | % removed |
|---|---|---|---|---|---|---|---|
| baseline | Frozen engine logic (this harness) | 8706 | 24.9% | $-634.44 | $-0.0729 | $+0.0000 | 0.0% |
| L1 | Zone cooldown (12x 5m candles / 1h, any exit) | 6375 | 25.6% | $-448.62 | $-0.0704 | $+0.0025 | 26.8% |
| L2 | Risk floor (skip risk_pct < 0.25%) | 2202 | 29.7% | $-183.50 | $-0.0833 | $-0.0105 | 74.7% |
| L3 | Touch band (keep touches 2-5, skip 6+) | 863 | 24.3% | $-60.84 | $-0.0705 | $+0.0024 | 90.1% |
| L4 | Loss-side day blacklist (stop_loss zones, same UTC day) | 3784 | 25.7% | $-272.54 | $-0.0720 | $+0.0009 | 56.5% |
| L5 | Combo: L1 + L3 (composed from above, no fresh replay needed) | 616 | 24.7% | $-39.60 | $-0.0643 | $+0.0086 | 92.9% |

## Methodology notes / limitations

- L1 (zone cooldown) and L4 (loss-day blacklist) are proper re-replays: the lever logic is wired into the entry-scan loop itself, so a blocked signal genuinely never fires and the position slot may go to a different signal — sequencing is exact.
- L2 (risk floor) and L3 (touch band) are POST-FILTERS on the baseline trade list. This is NOT exact: in a true re-replay, removing a filtered-out trade would free that symbol's one-position-per-symbol slot for a different signal the baseline never took. Post-filter numbers are an UPPER BOUND on what a true re-replay of L2/L3 alone would show.
- L1/L4 re-replays use TRAIN-window-only data (feed truncated to cut_ts + 10d buffer) to avoid the ~80min/10-pair full-replay cost; the buffer exists only so trades opened near the TRAIN boundary have candles to resolve against, not to peek at holdout outcomes. No statistic from beyond the TRAIN cutoff informed any lever decision.
- Replays parallelized 10-way across available CPU cores; trade-selection logic is otherwise byte-for-byte identical to the frozen `engine.replay()` (verified against the existing unit-test fixtures before this run).

## L5 selection

Best two individual levers by TRAIN net/trade: **L1** and **L3**.

## Holdout (honesty-gated)

Overall best performer on TRAIN: **L5** (net/trade $-0.0643). This is NOT positive — below the honesty-rule bar of net/trade > 0. **No holdout run performed.**
