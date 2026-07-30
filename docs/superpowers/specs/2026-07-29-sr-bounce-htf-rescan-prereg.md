# PRE-REGISTRATION — SR_BOUNCE higher-timeframe re-scan

**Registered**: 2026-07-29 ~9:20 PM ET, owner order: timeframe is the suspected
constraint; owner requires **2-3 trades/day** across the pair universe.
**Motivation** (receipts): 5m/1h version killed by scan (−$0.0705/t holdout) and
confirmed by day-1 live (−$0.047/t); zones averaged 0.19% risk width = noise-scale;
fees 30-60% of wins. At 4h/1d zone scale, structural stops run 1-3% and the 0.12%
RT fee falls to a 4-12% tax. This scan tests whether the SAME mechanism (frozen
pivot/cluster/touch/rejection/geometry rules) is viable at structure scale.

## Grid (EXACTLY three configs — frozen before any run)
| Config | Zone TF | Entry TF | Expected freq (prior, from measured 25/day at 1h/5m) |
|---|---|---|---|
| A | 4h | 15m | ~4-8/day |
| B | 4h | 1h  | ~1-3/day |
| C | 1d | 1h  | ~0.5-2/day |

All other signal parameters IDENTICAL to the frozen spec (k=3 pivots, 0.25×ATR(zone-TF)
cluster, ≥2 touches gap ≥3, ADX(zone-TF) < 30 regime gate, confirmed rejection on the
entry TF, SL = zone edge ∓ 0.25×ATR(entry TF), TP = nearest opposing zone capped 3×,
skip room < 1× risk). NO parameter tuning within configs.

## Data & costs
- ~400 days per pair, same 10-pair universe, fresh ccxt fetch (cached).
- Fees: 0.12% RT of notional (unchanged).
- **Funding (NEW, required at these hold times)**: charge 0.01% of notional per 8h
  of hold time, always as a cost (conservative — real funding is signed, but
  unmeasured; the bot's own funding capture is a known gap). Stated now so the
  scan can't lie optimistically about multi-hour holds.
- Fill realism, both-touched→SL, no-lookahead: unchanged from the reviewed engine.

## Split & selection (multiplicity handled)
- Per config: TRAIN = first ~70%, HOLDOUT = last ~30% by time. Frozen before run.
- Selection happens on TRAIN ONLY. A config is ELIGIBLE iff TRAIN shows:
  (1) net/trade > $0 fee-and-funding-inclusive, AND (2) pooled frequency ≥ 1.5
  trades/day (floor under the owner's 2-3 target), AND (3) ≥150 train trades
  (below that, no verdict — insufficient sample).
- If ≥1 config eligible: the SINGLE best (train net/trade) gets ONE holdout run.
  HOLDOUT PASS bar: net/trade > $0. Others' holdouts stay unread forever.
- If none eligible: DO-NOT-BUILD at higher TF; the timeframe thesis is answered
  negative for this mechanism; no third scan without a new mechanism.

## Pre-committed actions
- Holdout PASS → spec a paper slot at that config (new slot, new registration;
  SR_BOUNCE 5m slot's n=50 verdict is independent and unaffected).
- Holdout FAIL or none eligible → written to memory as final; the S/R bounce
  mechanism is closed at ALL tested timeframes without a new mechanism.
- Frequency numbers from the scan are reported per config regardless, so the
  owner sees the real trades/day menu even on a kill.

## Anti-fishing clause
Three configs, one selection rule, one holdout read — final as of this
registration. No added configs, no threshold changes, no re-slicing after results.
