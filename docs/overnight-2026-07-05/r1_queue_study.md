# R1 — Queue-State Conditioning Study (main-bot PostOnly fills)

**Date:** overnight 7/5 → 7/6/2026 (analysis completed ~8:10 AM PT 7/6)
**Question:** can we condition the main bot's PostOnly maker posts on order-book queue
state to get less-toxic fills? (Sanctioned next step from reference_fill_rate_research_2026-07-03:
front-of-queue fills ~13x less toxic → queue-size study on OUR OWN fills.)
**Verdict: NULL — no actionable conditioning rule on any observable we have.**
One significant mechanical finding (queue size predicts fill *probability*, not fill
*toxicity*) plus a defined instrumentation gap. All results screening-grade.
READ-ONLY study — no bot files touched.

Receipts: scripts + raw outputs archived in
`docs/overnight-2026-07-05/r1_queue_study_receipts/` (queue_study_fast.py, exact_stream.py,
near_opp_2x2.py; fast_out.txt, exact_out.txt, *_out.json).
Bootstrap CIs: 10k resamples, groups resampled independently, diff per iteration
(per lessons.md bootstrap-diff rule), fixed seeds.

---

## A. Instrumentation inventory — what we actually observe at post time

| Source | Queue-state observables | Coverage (June+ htf_l2) |
|---|---|---|
| `trading_state.json` entry_snapshot.ob | `imbalance` (20-level volume imbalance, exchange.py:105), `spread_pct`, `bid_walls`/`ask_walls` counts. **No depth USD, no touch sizes.** Captured at signal time (placement follows in the same cycle). | 100 of 101 fills |
| `logs/flow_capture.jsonl` | 20-level `bid_depth_usdt`/`ask_depth_usdt` + imbalance + spread per scan cycle. Joined by symbol within 90 s (median gap 36 s, max 47 s). | 100/100 fills, 100/100 misses |
| `logs/l2_ticks/` (com.phmex.l2-recorder) | Exact top-5 book snapshots — **only ARB, BTC, ETH, INJ**, June 12+ | 26 fills + 11 misses on tick symbols; 29/37 reconstructed (4 anchors pre-recorder, 4 no snapshot within 30 s) |
| `reports/main_missed_fills.json` | 100 PostOnly misses (June 18 – July 3 UTC) with replayed sim outcomes | joined 100/100 |
| `reports/l2x_postentry_drift.json` | post-entry drift (bps) per real fill, study window ends July 1 | 66 of 101 fills |
| `logs/gotAway.jsonl` | **Not misses** — gate-blocked signals (bot.py `_log_gotaway`). Not used. | — |

**Hard gaps (honest):**
1. **Placement timestamp is not persisted** anywhere in state — placement had to be
   estimated as anchor − 20 s (the pre-7/3 maker wait) for exact-queue reconstruction.
2. **Our queue POSITION (volume ahead of us at our price) is unobservable** from every
   source we have. The literature's 13x effect is about *position*; we can only ever see
   *total resting size at the level*. This cannot be fixed retroactively.
3. Touch-level sizes exist for only 4 of ~25 scanner symbols (l2-recorder scope).
4. entry_snapshot records imbalance/walls but **not** depth_usdt or touch sizes, even
   though the bot has the full book in hand at that moment (exchange.py:118-130 computes it).

## B. Fills split by queue proxies (June+ htf_l2, n=101 non-phantom, net +$7.46, 73.3% WR)

Median splits; "d15" = mean post-entry drift at 15 min (bps, + = with the trade), n_d = drift-joined subset.

| Proxy (median split) | Low bucket | High bucket | hi−lo avg net$ [95% CI] | hi−lo d15 bps [95% CI] |
|---|---|---|---|---|
| Near-side 20L depth pctile (0.619) | n=50, 76% WR, +$8.29, d15 +12.5 | n=50, 70% WR, −$1.05, d15 −13.2 | −0.19 [−0.50, +0.13] | −25.7 [−64.9, +14.5] |
| Side-relative imbalance (0.073) | n=50, 74% WR, +$2.32 | n=50, 74% WR, +$5.16 | +0.06 [−0.26, +0.38] | −6.5 [−48.4, +37.2] |
| spread_pct (0.0405) | n=50, 62% WR, −$5.63, d15 −27.6 | n=50, 86% WR, +$13.11, d15 +20.1 | **+0.37 [+0.07, +0.69]** | **+47.7 [+8.4, +93.5]** |
| Near-side walls (0) | n=52, 69% WR, −$2.71 | n=48, 79% WR, +$10.19 | +0.26 [−0.04, +0.58] | −11.7 [−47.5, +25.4] |

Depth-pctile quintiles: 0–20% n=7 (+$0.38, n<20), 20–40% n=14 (+$0.68, n<20),
40–60% n=27 (+$5.86), 60–80% n=26 (+$3.66), 80–100% n=26 (**−$3.34**, 73% WR).

- **Near-side depth (the queue proxy): directionally supports the hypothesis**
  (thin-book fills better on PnL and drift; only the deepest quintile is net-negative)
  **but both CIs include 0.** Not significant at n=100.
- **Imbalance and walls: NULL.**
- **spread_pct is the only nominally significant split** (wide spread → better fills, both
  metrics). Flags before anyone acts on it: (a) 4 features × 2 metrics = 8 tests, one
  nominal hit is compatible with chance; (b) it is the same direction as the ST2.0
  `spread_pct>=0.039` filter that is on record as **artifact-suspect** (bot.py ST2.0 filter
  comment); (c) prior loser-vs-winner feature audits were NULL. Screening-grade lead only;
  must be cross-checked against lessons.md and forward-tested before any use.

## C. Misses (100 PostOnly misses, June 18 – July 3, sim outcomes from main_missed_fills.json)

- **Misses do NOT sit in different aggregate book states than fills:** near-depth pctile
  misses 0.609 vs fills 0.612, diff −0.003 [−0.071, +0.067]. A rule keyed on 20-level
  depth would skip fills and misses roughly proportionally.
- Miss sim outcomes by the fills' median-depth split: low n=48 +$1.17 (62.5% sim WR) vs
  high n=52 +$4.30 (71.2%); diff +0.06 [−0.26, +0.39] — NULL. The misses a depth rule
  would additionally skip were ~breakeven sims, consistent with the 7/2 finding that main-bot
  misses are NOT missed winners (reference_main_missed_fills).
- Near×opposite depth 2×2 (web-research finding #1 replication attempt, R1 plan):
  all fill cells statistically indistinguishable — "clean cell" (near BIG + opp small,
  n=48) minus other fills +0.03 [−0.29, +0.34]. NULL at our snapshot granularity.
  Misses in near-BIG+opp-BIG were sim-losers (−$3.49, n=19, **n<20**).

## D. Exact touch-queue at placement (tick symbols only; placement = anchor − 20 s ± 20 s)

New June+ reconstruction (26 fills + 11 misses on ARB/BTC/ETH/INJ; 29/37 covered,
11 at the exact price level, rest touch-fallback; rel-queue = resting size at our
price ÷ symbol-day median touch size):

| Group | n | median rel-queue | mean |
|---|---|---|---|
| fill-winners | 9 (**n<20**) | 0.66 | 0.74 |
| fill-losers | 9 (**n<20**) | 0.17 | 0.41 |
| misses | 11 (**n<20**) | 1.07 | 1.95 |

- **miss − fill rel-queue: +1.37, 95% CI [+0.18, +3.14] — significant.** Misses happen
  on ~2–3x larger touch queues. Replicates the 7/3 study independently (23 anchors there:
  miss median 2.06 vs fill 0.59–0.65, reports/queue_at_placement.json).
- **loss − win rel-queue: −0.33, 95% CI [−0.88, +0.31] — NULL, and wrong-signed** for the
  toxicity hypothesis (our losers sat on *smaller* queues). Same null in the 7/3 sample
  (win 0.59 vs loss 0.65, n=5/7).
- Composition caveat: covered tick-symbol fills run 9W/9L (50% WR) vs 73% overall —
  BTC/ETH skew losier; tick-symbol results may not generalize to the full scanner set.

## E. Rule sweep (in-sample, post-hoc — NOT deployable evidence)

"Skip post when near-side depth pctile > X": best X=0.8 keeps 74 fills (+$10.57), cuts 26
fills (−$3.34) and 25 misses (free). But the threshold was picked from a 5-point sweep on
100 trades, the cut bucket is one quintile (n=26, WR still 73% — the loss is avg-loss-driven),
and the underlying hi-vs-lo contrast is not significant (§B). This is exactly the shape of
lead that edge-hunt-exhaustion says becomes an artifact.

## F. Conclusions

1. **No conditioning rule is supported by the data we have.** The only significant queue
   effect is mechanical: big near-queue → you don't get filled. Since our misses are
   demonstrably NOT missed winners, "post only into small queues" buys fill *rate*, not
   fill *quality* — and fill-rate-for-its-own-sake was already adjudicated (do not port
   re-quote; fill-rate↔adverse-selection tension is structural).
2. **Fill toxicity vs queue size: NULL on both the exact (n=18, underpowered) and proxy
   (n=100) measurements**, with the exact measurement wrong-signed.
3. **The literature's lever (queue POSITION) is unobservable in our stack** — that part is
   an instrumentation gap that even perfect logging can only partially close (position
   requires tracking level-size deltas from placement moment; feasible from l2_ticks stream
   for the 4 recorded symbols only).
4. **If we ever want to answer this decision-grade**, the concrete instrumentation is:
   at order placement log (a) exact placement ts + our limit px per order id,
   (b) top-5 both-sides book from the already-fetched ob (extend entry_snapshot with
   depth_usdt + touch sizes — zero extra API calls, exchange.py already computes them),
   (c) resting size at our level. At ~100 attempts/month, ~2–3 months to a powered split.
   Whether that's worth queue depth on the roadmap is an owner call — expected value is
   low given (1)–(2).
5. Incidental screening-grade lead (NOT part of the queue hypothesis): wide-spread signal
   states outperformed on both PnL and drift (§B). One-of-eight-tests caveat + artifact-suspect
   precedent. Park unless it survives a fresh-data check.
