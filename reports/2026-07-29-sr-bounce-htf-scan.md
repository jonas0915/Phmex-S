# SR_BOUNCE higher-timeframe re-scan — 2026-07-29

Pre-registration: `docs/superpowers/specs/2026-07-29-sr-bounce-htf-rescan-prereg.md` (frozen grid, split, selection rule, funding model, anti-fishing clause). Engine: `scripts/research/sr-bounce-htf-scan/htf_engine.py` (generalized, byte-faithful copy of the frozen `sr-bounce-scan/engine.py`). Signal math unmodified (`sr_levels.py`, `sr_signal.py` imported directly).

## Per-config TRAIN results (all 3, reported regardless of verdict)

| Config | Zone/Entry TF | Train n | WR | Net | Net/trade | Trades/day | Train days |
|---|---|---|---|---|---|---|---|
| A | 4h zone / 15m entry | 12485 | 27.6% | $-898.33 | $-0.0720 | 44.59 | 280 |
| B | 4h zone / 1h entry | 5384 | 32.5% | $-297.83 | $-0.0553 | 19.23 | 280 |
| C | 1d zone / 1h entry | 1074 | 25.1% | $-132.61 | $-0.1235 | 3.84 | 280 |

## Eligibility checklist (pre-registered bars)

Eligible iff: (1) train net/trade > $0 fee+funding-inclusive, (2) pooled train frequency >= 1.5 trades/day, (3) train n >= 150.

| Config | net/trade > $0 | freq >= 1.5/day | n >= 150 | ELIGIBLE |
|---|---|---|---|---|
| A | FAIL | PASS (44.59/day) | PASS | not eligible |
| B | FAIL | PASS (19.23/day) | PASS | not eligible |
| C | FAIL | PASS (3.84/day) | PASS | not eligible |

## Selection & holdout

**No config eligible on TRAIN.** Per the pre-registered selection rule, no holdout is read for any config. **Verdict: DO-NOT-BUILD at higher TF** -- the timeframe thesis is answered negative for this mechanism; per the prereg, no third scan without a new mechanism.

## Methodology notes

- Fees 0.12% RT of notional (unchanged). Funding: 0.01% of notional per 8h of hold time, always charged as a cost (never a credit), per the prereg. Hold time measured fill-to-exit (see build report for the documented reasoning on this implementation choice).
- TRAIN/HOLDOUT split is a calendar ~70/30 split of each config's own entry-TF data range (not a trade-count split), so it holds regardless of how many trades a config produces.
- Selection happened on TRAIN ONLY, one winner, one holdout read -- per the pre-registration's anti-fishing clause. No added configs, no threshold changes, no re-slicing after results.

