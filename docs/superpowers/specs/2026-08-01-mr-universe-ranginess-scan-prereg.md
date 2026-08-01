# PRE-REGISTRATION — MR-tuned universe (ranginess scanner) scan

**Registered**: 2026-08-01 ~10:15 PM PT (7/31), owner order ("execute on #1").
**Thesis**: 5m_mean_revert's pair universe comes from a gainer-ranked scanner —
optimized for momentum, adversarial for mean reversion. A ranginess-ranked
universe should raise MR trade frequency and reduce trend-ambush losses
WITHOUT touching the proven gate stack. This scan tests universe selection
ONLY; strategy and gates are frozen as-is.

## Design
Replay the existing 5m_mean_revert signal engine
(scripts/slot_lab/mean_revert_replay.py — reuse, do not rewrite) over two
rotating top-8 pair lists drawn from the same universe:
- **TEST list**: ranked by frozen ranginess score (below)
- **CONTROL list**: ranked by trailing-24h |return| descending (gainer proxy —
  mirrors the live scanner's ranking basis)

## Frozen parameters (no tuning — deviations are findings to REPORT, not fix)
- Universe: top 30 Phemex USDT perps by current 24h volume, all ≥ $3M
  (survivorship caveat recorded: current snapshot, not historical listings).
- History: ~400 days, 5m OHLCV for replay + 1h for scoring (ccxt, cached).
- Ranginess score per pair, computed on trailing 30d of 1h bars:
  R1 = fraction of bars with ADX(14) < 25   (mirrors the slot's regime gate)
  R2 = of closes outside BB(20,2), fraction returning to the 20-SMA within
       12 bars   (band-revert rate — the mechanism MR feeds on)
  score = R1 × R2. Rebalance both lists every 7 days.
- Fees: 0.12% RT of notional. $30 margin @10x per trade (current live size).
  Replay agent MUST inspect the replay engine's fee handling first — the 7/6
  open bug (paper-sim fee over-penalty) must be checked and its status
  reported before results are read.
- Same entry/exit mechanics as the live slot per the replay engine; tape/OB
  gates CANNOT be replayed (no historical L2) — recorded limitation, same as
  every prior scan: this measures signal-on-OHLCV, not fill selection.

## Split & verdict (frozen)
- TRAIN = first ~70% by time, HOLDOUT = last ~30%. Selection on TRAIN only.
- TRAIN eligibility for the TEST universe, ALL required:
  (1) net/trade > $0 fee-inclusive,
  (2) net/trade ≥ CONTROL's net/trade (universe must not degrade quality),
  (3) trades/day ≥ 1.5× CONTROL's (the frequency thesis must actually show).
- Eligible → ONE holdout read: PASS iff holdout net/trade > $0 AND ≥ control
  holdout net/trade. Not eligible or holdout fail → DO-NOT-BUILD; the
  universe thesis is answered negative; no re-scoring, no second score
  definition without a new mechanism.
- PASS → next step is a spec for a paper-slot A/B (MR slot fed by ranginess
  list, live slot untouched) — separate registration, owner-gated.

## Anti-fishing clause
One score definition (R1×R2), one control, one holdout read — final as of
this registration. Frequency and net are reported for both lists regardless
of verdict.
