# Phase 3 Cohort-Gate Simulation — Results (2026-06-11)

Method 1: exact both-sides accounting over ACTUALLY TAKEN trades. For an entry
filter, blocking historical trades is the complete counterfactual — no new
trades appear. Script: `scripts/research/gate-sims-2026-06-11/gate_sim.py`
(read-only; reads `trading_state.json` and prints). Every number below is from
that script's output this session.

## Universe

- 91 `htf_l2_anticipation` trades with `entry_snapshot`, of 107 htf_l2 records
  total. The 16 dropped records are the snapshot-less min_margin_skip-era
  artifacts (verified: 0 of the book's 25 `min_margin_skip` records carry a
  snapshot). Other snapshot-bearing records exist but are out of scope here:
  75 htf_confluence_pullback, 10 synced, 5 momentum_continuation (181 total).
- Span 4/18 – 6/9 UTC, 7.5 weeks, 12.2 trades/wk. Total net_pnl **−$12.68**
  (matches the audit doc §2).
- Half-split (overfit guard G1) at 5/14, 7:16 AM PT: H1 = 45 trades, −$4.53;
  H2 = 46 trades, −$8.15.

**Alignment formula** (matches strategies.py:600-606 semantics):
`aligned_lt_bias = flow.large_trade_bias` for longs, `−flow.large_trade_bias`
for shorts — positive means whales agree with the trade's direction. The audit
agent's tercile cut reproduces exactly under this formula (see Reproduction).

**Accounting**: blocked set B per gate; losers saved = Σ(−net) over B where
net<0; winners clipped = −Σ(net) over B where net>0; NET = saved + clipped
(positive = gate would have helped), all on `net_pnl` (fees+funding included).

**Pass bar**: NET > 0 overall AND same sign in both halves AND n_blocked ≥ 8
AND survives leave-one-out of the single biggest saved loser.

**Extra guard added** (not in the original bar): random-block permutation
baseline. On a net-negative book, blocking *k random trades* has positive
expected NET (≈ k × $0.139 here) — so "net-positive" alone is nearly
meaningless. `rand$` = expected NET of a random gate of the same size; `pRnd` =
P(random same-size block ≥ observed NET), 20,000 draws, fixed seeds.

## Full sweep (91-trade set)

| Gate | nBlk | saved$ | clip$ | NET$ | H1$(n) | H2$(n) | LOO$ | rand$ | pRnd | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| A: aligned_lt_bias ≥ 0.25 | 41 | +18.85 | −8.26 | **+10.59** | +3.61 (22) | +6.98 (19) | +9.13 | +5.71 | 0.075 | PASS |
| A: aligned_lt_bias ≥ 0.30 | 35 | +15.97 | −5.91 | **+10.05** | +3.80 (20) | +6.26 (15) | +8.59 | +4.88 | 0.062 | PASS |
| A: aligned_lt_bias ≥ 0.35 | 32 | +15.22 | −4.88 | **+10.34** | +3.41 (18) | +6.92 (14) | +8.87 | +4.46 | 0.036 | PASS |
| A: aligned_lt_bias ≥ 0.40 | 26 | +13.21 | −3.37 | **+9.84** | +3.09 (15) | +6.75 (11) | +8.38 | +3.62 | 0.024 | PASS |
| A: aligned_lt_bias ≥ 0.45 | 20 | +12.50 | −2.65 | **+9.84** | +3.52 (12) | +6.32 (8) | +8.38 | +2.79 | 0.007 | PASS |
| B: 5m ADX ≥ 23 | 37 | +15.11 | −5.62 | +9.49 | +5.50 (20) | +3.99 (17) | +8.13 | +5.16 | 0.100 | PASS* |
| B: 5m ADX ≥ 24 | 33 | +11.17 | −5.50 | +5.67 | +5.50 (20) | +0.17 (13) | +4.33 | +4.60 | 0.369 | PASS* |
| B: 5m ADX ≥ 25 | 30 | +10.40 | −5.38 | +5.02 | +4.85 (17) | +0.17 (13) | +3.68 | +4.18 | 0.397 | PASS* |
| B: 5m ADX ≥ 26 | 26 | +10.01 | −4.34 | +5.67 | +4.71 (15) | +0.97 (11) | +4.33 | +3.62 | 0.253 | PASS* |
| B: 5m ADX ≥ 27 | 21 | +7.57 | −3.82 | +3.75 | +2.62 (11) | +1.13 (10) | +2.41 | +2.93 | 0.388 | PASS* |
| C: conf floor ≥5 (block conf=4) | 11 | +5.89 | −1.15 | +4.73 | +2.78 (6) | +1.96 (5) | +3.35 | +1.53 | 0.078 | PASS |
| D: block UTC 21 | 9 | +4.53 | −1.42 | +3.11 | +0.50 (4) | +2.61 (5) | +1.74 | +1.25 | 0.184 | PASS* |
| D: block UTC 21,22 | 17 | +8.81 | −2.54 | +6.26 | +1.70 (8) | +4.56 (9) | +4.87 | +2.37 | 0.073 | PASS |
| D: block UTC 21,22,23 | 22 | +11.88 | −2.54 | **+9.34** | +2.09 (10) | +7.25 (12) | +7.95 | +3.07 | 0.018 | PASS |
| D: block UTC 14 | 11 | +6.74 | −1.55 | +5.18 | +1.10 (5) | +4.08 (6) | +3.72 | +1.53 | 0.055 | PASS |
| D: block UTC 14,21,22,23 | 33 | +18.62 | −4.10 | **+14.52** | +3.19 (15) | +11.33 (18) | +13.06 | +4.60 | 0.002 | PASS |
| E: union(A≥.25, ADX≥23, conf<5, UTC 14/21-23) | 72 | +30.96 | −13.40 | **+17.56** | +7.51 (35) | +10.05 (37) | +16.10 | +10.04 | 0.003 | PASS |
| E2: A≥.40 ∪ conf<5 ∪ UTC 21-23 | 49 | +22.39 | −7.07 | **+15.32** | +4.53 (25) | +10.79 (24) | +13.86 | +6.83 | 0.006 | PASS |

\* = passes the formal 4-part bar but is NOT distinguishable from a random
same-size block (pRnd > 0.10). The 4-part bar alone is too weak on a
net-negative book — see caveats.

## Reading the table honestly

**All 17 gates "pass" the formal bar.** That is the predictable artifact of a
−$12.68 book: blocking anything looks good. The permutation column is what
separates signal from arithmetic:

1. **Gate A (aligned whale bias) is the real one.** NET is stable +$9.8–10.6
   across all five thresholds, positive in both halves at every threshold,
   survives LOO, and pRnd improves monotonically as the threshold rises
   (0.075 → 0.007). Tighter cuts keep almost all the savings while clipping
   fewer winners — exactly what a genuine inverted signal looks like.
   **A ≥ 0.40–0.45 is the strongest single gate in the sweep** (pRnd
   0.024/0.007, clips only $2.65–3.37 of winners).
2. **Gate B (5m ADX) is mostly noise.** Only ADX ≥ 23 is even marginal
   (pRnd 0.100); 24–27 are at pRnd 0.25–0.40 — indistinguishable from blocking
   random trades — and H2 NET nearly vanishes (+$0.17 at 24/25). The audit's
   "ADX ≥ 24.9 → 38.7% WR" cohort reproduces, but a low WR cohort on a
   negative book is not evidence of a usable filter. **Do not ship B.**
3. **Gate C (conf floor 5)** is positive in both halves and pRnd 0.078, but
   n=11 sits just above the floor and prior April research already read
   confidence-as-filter as dead. Weak-yes at best; cheap to ship since it only
   changes one threshold; expect little.
4. **Gate D (hours)** — UTC 21-23 (2–4 PM PT) is solid: pRnd 0.018, both
   halves positive, survives LOO; the whole-book cross-check (n=287 with
   net_pnl) agrees: n=53, NET +$14.90. UTC 14 alone is marginal (pRnd 0.055,
   n=11). **The combined {14,21,22,23} pRnd 0.002 is inflated by selection** —
   those hours were picked by scanning all 24 hours on this same data, so the
   permutation test overstates it. Treat UTC 21-23 as the defensible piece.
5. **Combination.** The full union (E) leaves **19 trades in 7.5 weeks
   (2.5/wk)** — the bot becomes effectively idle, and the residual +$4.87 at
   84% WR over 19 trades is itself an overfit-looking remnant. The moderate
   E2 (A ≥ 0.40 ∪ conf<5 ∪ UTC 21-23, dropping the noise gates B and UTC 14)
   keeps NET +$15.32 (87% of E's benefit), pRnd 0.006, both halves positive,
   and leaves **42 trades (5.6/wk), residual net +$2.63, 69% WR** — a much
   saner residual book. **E2 is the recommendation shape if Phase 3 ships.**

## Whale-boost removal (strategies.py:601-606), separate accounting

The +0.03 boost fires when aligned lt_bias > 0.2. **46 of 91 taken trades got
the boost; that cohort's net is −$9.79** — confirming the audit's "inverted
signal" read (the boost rewards the worst cohort).

But removing the boost only *blocks* a trade if it then fails the 0.80
SCALP_MIN_STRENGTH bar (bot.py:1052), i.e. gate-time strength < 0.83.
Gate-time strength is not stored: `entry_snapshot.strength` is recorded after
the funding strength_mod (±0.03, bot.py:1202-1203) which is applied AFTER the
0.80 gate. So:

- Point estimate (recorded < 0.83): **5 trades blocked, saved +$1.84, clipped
  −$0.96, NET +$0.88** — all 5 were shorts (base 0.82 + 0.03 boost − 0.04
  short penalty ≈ 0.81–0.83): ENA, ETH×2, ARB (losers, −$0.30 to −$0.75
  each) and XLM (winner, +$0.96).
- Hard bounds: 0 trades (if every funding mod was +0.03) to 22 trades
  (NET +$1.07) at the other extreme.

As a blocking change, whale-boost removal **FAILS the bar** (n=5 < 8; halves
+1.84/−0.96). It is a ~$1 nothing on its own. The real money in the whale
signal is gate A — an explicit aligned-lt_bias block — not the boost removal.
Removing the boost is still justified as code hygiene (it points the wrong
way), and is strictly subsumed by gate A at any threshold ≤ 0.45 for shorts /
all thresholds for the cohort it boosts.

## Reproduction of audit-doc §2 cohorts (sanity)

- Top aligned_lt tercile: n=31, cut 0.360, net −$9.97, WR 35.5% ✓ (matches
  audit exactly).
- 5m ADX ≥ 24.9: n=31, WR 38.7%, net −$5.54 ✓.
- conf=4: n=11, net −$4.73 ✓.
- **Discrepancy found:** the audit labeled the hour cohorts "whole book". They
  are not — UTC 21-23 n=22/−$9.34 and UTC 14 n=11/−$5.18 reproduce exactly on
  the **91-trade htf_l2 set**. The actual whole-book numbers (287 records with
  net_pnl) are UTC 21-23: n=53, −$14.90, and UTC 14: n=20, −$7.68. Direction
  agrees in both views, so the conclusion stands, but the audit's n/label was
  wrong.

## Caveats (read before shipping anything)

1. **Everything here is in-sample.** Every threshold was chosen after looking
   at this same 91-trade window (the audit found the cohorts; this sweep
   formalized them). The half-split guard helps but both halves were visible
   during cohort discovery. The pRnd column corrects for "blocking anything
   helps" but NOT for threshold selection — the hour-set pRnd values are the
   most inflated (24-hour scan), gate A's monotone threshold profile is the
   least worrying.
2. **n is small.** 91 trades, $-scale ±$15. A handful of trades flips any row.
   LOO is reported, but two-out would dent several gates.
3. **Mean-shift counterfactual only.** Method 1 assumes blocking an entry has
   zero effect on other entries. True for pure entry filters with this bot's
   architecture (per-pair cooldowns/cluster throttle could in principle let a
   blocked trade *unblock* a different later entry — not modeled, believed
   second-order at 12 trades/wk).
4. **The residual book is not "profitable", it's leftovers.** E2's residual
   +$2.63/42 trades (+$0.35/wk) is statistically nothing and partly selected
   by construction. The honest claim is "the gates remove measurably-bad
   cohorts", not "the gated bot has positive expectancy". [CORRECTED 6/11 PM:
   Phase 2's fee ground-truth (docs/2026-06-11-fee-ground-truth.md) found
   entries already 98.9% maker — fees are NOT the remaining expectancy lever;
   the loss-asymmetry work (durable trail) and these gates are what's left.]
5. **Whale-boost counterfactual is bounded, not exact** (funding mod not
   recorded at gate time). Bounds: 0–22 trades, NET +$0.00 to +$1.07.
6. Hour gates judged on the htf_l2 set; a live time-block is bot-wide. The
   whole-book check agrees directionally for UTC 21-23, so this caveat is
   informational.

## Bottom line

- **Ship-candidates (in order): A (aligned lt_bias ≥ 0.40), D (UTC 21-23
  block).** Both pass the bar AND beat random blocking with stable
  both-halves behavior.
- **C (conf ≥ 5)**: cheap, weakly supported, fine to include.
- **B (ADX)**: fails the random-block test at every audit-suggested
  threshold. Drop it.
- **UTC 14**: marginal, selection-tainted; park it, re-check on forward data.
- **Whale-boost removal**: do it as hygiene; expect ~$1, not a fix.
- **Preferred package = E2** (A ≥ 0.40 ∪ conf<5 ∪ UTC 21-23): in-sample NET
  +$15.32 of the −$12.68 book, residual 5.6 trades/wk (not idle, vs 2.5/wk
  for the full union).
- Per Phase-3 rules this should still go through the calibrated flow-replay
  entry model or a paper/shadow window before live — this document is the
  taken-trades accounting, not forward validation.
