# Microstructure / Calendar Edge Search — VERDICT (2026-06-13)

Data: binanceus 1h spot OHLCV, 2021-01-01 .. 2026-06-13 (~47.7k bars/sym for full-history
symbols) for BTC ETH SOL BNB XRP DOGE ADA LINK AVAX LTC. Phemex funding-rate history +
timestamps (~195 days, Dec 2025 - Jun 2026) for the perp set.
Methods: block-bootstrap CI (block=24h/7d/3h), walk-forward 5 contiguous folds, per-year
regime split, BH-FDR + Bonferroni multiple-testing correction. Fees: taker 0.132% RT,
maker 0.024% RT.

## RANKED SURVIVORS

| Rank | Effect | Stat strength | WF | Net-fee tradeable? | Verdict |
|------|--------|---------------|-----|--------------------|---------|
| 1 | Funding pre-stamp dip (00:00 UTC, +funding) | p<1e-4, placebo-clean | 4/5 (decaying) | Maker-only, thin | REAL but mostly regime drift; NOT deployable |
| 2 | Saturday strength (alts) | p=0.007 (survives BH+Bonf) | 4/5 (2026 flipped) | +0.20% taker / +0.31% maker | DECAYING; BTC=0, alt-only, dying |
| - | Time-of-day (24 hr) | NONE survive BH-FDR | - | - | NULL after correction |
| - | Thursday weakness (prior claim) | not significant | 2/5 | - | KILLED |
| - | CME weekend-gap FILL (BTC) | sign is BACKWARDS | - | - | KILLED (gaps continue, don't fill) |

## DETAIL

### TEST 1 — Funding-settlement microstructure  (the structurally-motivated one)
- On POSITIVE-funding stamps, the 2h drift INTO the stamp is significantly negative:
  pooled -0.077% (p<0.0001). Placebo (mid-interval 2h drift, same days) = -0.006% (p=0.58).
  => the dip is STAMP-SPECIFIC, not general drift. The structural hypothesis (longs sell
  into settlement when they'd pay) is genuinely supported in-sample.
- BUT there is NO post-stamp bounce: POST drift also negative -0.045% (p=0.0095); POST-PRE
  spread insignificant (p=0.21). Price drifts down through the stamp, no reversal.
- Tradeable play = SHORT into stamp, cover at T (2h hold):
    gross +0.077% | net taker -0.055% | net maker +0.053%.  Maker-only, marginal.
  Concentrated at 00:00 UTC stamp: +0.186% gross / +0.162% net-maker / 54.9% WR.
  08:00 stamp dead (-0.007%), 16:00 weak (+0.055%).
- DISENTANGLING KILLS MOST OF IT: the 22:00->00:00 drift over the full 5.5yr (all days) is
  -0.007% (flat). In the recent 195-day window it is -0.104% (p<1e-4) on ALL days, and
  -0.186% on positive-funding days. So ~half the "edge" is a recent-regime late-day
  weakness, not a funding law; funding adds only ~0.08% incremental, maker-only, on 195d.
- Walk-forward 4/5 but the two most recent folds are ~flat -> decaying.
- CONCLUSION: structurally real (the stamp-specific dip is the cleanest finding here), but
  not a fee-survivable, regime-robust, deployable edge. Sample only 195 days.

### TEST 2 — Time-of-day (24 UTC hours)
- NOTHING survives BH-FDR (critical threshold collapsed to 0). Raw best = 22:00 UTC
  (+0.041%, p=0.008, 5/5 WF, positive 5/6 yrs) but well below maker fees; pure noise-mining
  territory once you account for testing 24 hours. NULL.

### TEST 3 — Day-of-week
- Saturday is the only day surviving BH-FDR (p=0.007) AND Bonferroni: +0.336% mean daily.
  WF 4/5 but 2026 YTD flipped NEGATIVE (-0.31%). BTC Saturday ~0% (-0.0018%); effect is
  alt/high-beta only (DOGE +0.81%, SOL +0.55%). Classic decaying "weekend alt pump".
  Net long Fri-close->Sat-close: +0.20% taker / +0.31% maker historically, but dying.
- Thursday weakness (prior agent's claim): KILLED. Full mean -0.024% (insignificant), WF 2/5,
  per-year all over the place. Not real.

### TEST 4 — CME weekend-gap fill (BTC)
- BACKWARDS from hypothesis. corr(gap, fwd_ret) is POSITIVE (+0.09 to +0.15) => gaps
  CONTINUE, not fill. "Reversion return" negative across all horizons, 5/5 WF folds negative.
  The documented "CME gap fill" is NOT a reversion edge in this data. And 2025-2026 flipped
  (weak reversion now). Not tradeable either direction net of fees. KILLED.

## HONEST BOTTOM LINE
Two of four hypotheses are dead (Thursday, CME-gap-fill). Time-of-day is a pure
multiple-comparison null. The funding pre-stamp dip is the one genuinely interesting,
structurally-motivated, placebo-clean finding — but it is maker-only, largely a
recent-regime artifact, decaying in walk-forward, and backed by only 195 days of funding
data. Saturday alt-strength is real historically but decaying and already reversed in 2026.
NOTHING here clears the bar for a deployable, fee-robust, regime-stable calendar edge.
The classic calendar traps (24-hour mining, "Thursday") behaved exactly as the
multiple-testing correction predicted: noise.
