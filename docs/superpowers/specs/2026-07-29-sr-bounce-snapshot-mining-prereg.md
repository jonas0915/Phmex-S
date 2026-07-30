# PRE-REGISTRATION — SR_BOUNCE entry-snapshot mining (L2/OB confirmation hypothesis)

**Registered**: 2026-07-29, ~9:05 PM ET, owner order ("yes pre-register it"), BEFORE
the n=50 verdict resolves and before anyone has looked at feature-vs-outcome splits.
**Trigger**: runs as part of the SR_BOUNCE n=50 wrap-up (whatever the verdict), on
the full closed-trade ledger at that moment (~50 trades, 100% snapshot coverage —
verified 25/25 at registration).

## Hypothesis (owner's, 2026-07-29)
Order-book / L2 state at entry can confirm or veto SR_BOUNCE entries — i.e., at
least one book/flow feature separates winning from losing entries.

## Prior (recorded so the outcome is read honestly)
Heavily against: htf_l2 L2-confirmation R&D 13 tests / 0 survivors (7/17);
imbalance-as-gate added no OOS value even at p≈1e-94 signal strength (6/1);
gate-quantify found no separating entry feature (6/13). This mining is the cheap,
honest test of the owner's idea on this strategy's own data — not a rerun of those.

## Features tested (EXACTLY these 10; all exist in every snapshot — verified)
Book: ob.imbalance, ob.spread_pct, bid/ask depth ratio (bid_depth_usdt/ask_depth_usdt),
walls net (bid_walls − ask_walls).
Flow: flow.buy_ratio, flow.cvd_slope, flow.large_trade_bias, flow.trade_count.
Context controls (not L2, included to rank the book against them): regime.adx,
directional alignment (long ∧ ema_stack_bull) − (long ∧ ema_stack_bear), mirrored
for shorts — this is the day-1 "longs vs trend" hypothesis getting its shot on the
same terms.

Directional features (imbalance, buy_ratio, cvd_slope, large_trade_bias, walls net,
depth ratio) are SIGNED BY TRADE SIDE before testing (favorable = agrees with the
trade direction), so longs and shorts pool.

## Method (frozen)
- Outcome: win = net_pnl > 0 (paper net is already fee-inclusive — 7/28 lesson).
- Test: Mann-Whitney U (the existing overlap.py implementation, reused verbatim),
  two-sided, winners vs losers per feature.
- Multiplicity: 10 features → Bonferroni. PASS bar: p < 0.005 (0.05/10).
  SUGGESTIVE band: p < 0.05 uncorrected — reported as "not evidence, direction
  for the next pre-registration only".
- Power honesty: at n≈50 (~25W/25L expected), only large effects can clear 0.005.
  A null result therefore reads "no large effect", NOT "no effect". This is stated
  now so nobody (including Claude) inflates a null into "L2 is useless" or a
  suggestive p into "L2 works".

## Pre-committed actions
- Any feature p < 0.005 → owner is shown the split; IF the strategy also survived
  its n=50 line, that feature becomes a spec'd gate candidate with its own
  forward-test registration. If the strategy died, the finding transfers as a
  candidate for OTHER books' F7-style mining, not a reason to revive SR_BOUNCE.
- Only suggestive results → recorded in the autopsy memory file; NO gate built,
  NO threshold tuned, NO second look at the same data with new features (that
  would be fishing — a new hypothesis needs NEW data).
- All null → the L2-confirmation idea is closed for SR_BOUNCE with receipts,
  joining the 7/17 and 6/1 findings.

## Anti-fishing clause
The feature list, signing convention, test, and bar above are final as of this
registration. Adding features, changing the bar, or re-slicing (by symbol, by
hour, by touch count...) after seeing results is prohibited — any such idea goes
into a NEW pre-registration against data accrued AFTER it.
