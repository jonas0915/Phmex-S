# ST2.0 Edge Research — Synthesis (real data + literature)

**Date:** 2026-06-20. Two-track research, user-approved. Track A = empirical (our real
trades); Track B = deep web research on maker execution (24 adversarially-verified claims,
19 primary sources). The workflow's own synthesis step failed on a session limit; this file
is the hand synthesis. **Framing (META-RULE #7):** the SIGNAL is already the documented one
survivor of an exhaustive hunt ([[edge-hunt-exhaustion]]); the open question is execution.
Nothing here is a deploy recommendation — outputs are forward-confirm hypotheses.

## Bottom line

The literature **mechanistically explains ST2.0's real losses**, and the explanation is
structural, not a tuning problem: **a passive short-into-absorption fill is adversely
selected by construction.** You post a sell into a bid-heavy book being aggressively bought;
the fills you actually get are disproportionately the ones where buying continues and price
ticks up — against the short — before any reversion. As a slow, small, no-rebate trader you
have **none of the three compensations** the literature says you need (speed, queue position,
rebate). The single most on-point external study (Binance BTC perp, order-book-imbalance
*maker* strategy) **lost money**. This corroborates "execution is the binding constraint" and
points toward ST2.0 being **execution-trapped at this scale** — possibly not winnable as-is.

## Track A — how ST2.0 actually takes trades (our real data)

Source: `docs/research/2026-06-20-st2-how-it-trades.md`. Every number cited there.
- **Real maker fill rate 41.5%** (27 fills / 38 misses / 65 attempts, deduped rotated logs) —
  matches the documented ~43%.
- **Wildly uneven by symbol:** ETH ~59%, INJ ~67% fill; BTC ~30%, ENA ~20%; HYPE/DOGE/ARB
  0-for-window (n≤17/symbol — "never" not yet established).
- **29 filled live trades:** 41.4% WR, **−$0.12/trade, −$3.50 net.** The killer is **loss
  asymmetry** (avg loss −$0.35 ≈ 2× avg win +$0.18), not hit rate. Bleed concentrates in the
  `exchange_close` exit (n=6, 17% WR); the intended `st2_hold` maker exit (n=22, 50% WR) is
  ~breakeven.
- **Two honest blockers:** (a) miss log lines carry only symbol+timestamp — **fill-vs-miss
  conditions are unmeasurable today**; (b) `ob.imbalance` is null on all 29 closed trades (the
  bug fixed 2026-06-19/20; only new trades populate). → the core execution question is
  currently **unanswerable from our data**.
- Weak directional hints (all n≤12, none significant): losers entered busier tape
  (trade_count 132 vs 52) and held longer; winners had higher large_trade_bias (0.43 vs 0.07);
  US daytime 0% WR (n=7); **symbols that fill (ETH/INJ) ≠ symbols that win.**

## Track B — what the microstructure literature says (verified)

**1. The fills you get are the adverse ones — direct, on-point evidence.**
- Binance BTC perpetuals: "Orders with negative subsequent five-second returns are highly
  likely to fill, whereas those with positive returns are much less likely to fill."
  (arxiv 2502.18625, 3-0). For a SHORT, "fill then price up" = adverse — exactly ST2.0.
- Queue imbalance predicts BOTH fill probability AND the direction of the next move: a passive
  near-side order fills faster precisely when price is about to move toward it (i.e., against a
  resting order on the far side). Fills **cluster at extreme imbalance**, not uniformly
  (deep-lob-2021, 3-0 / 2-1).
- "If the price has chances to go down the probability to be filled is high but it is better to
  wait" — high fill probability *is* the adverse-selection signal (arxiv 1610.00261;
  worldscientific S2382626617500095, 3-0).

**2. The closest analog to ST2.0 lost money.**
- Binance BTC perp, **imbalance-conditioned maker strategy without cancellation: −0.4705 bp
  mean over 8,851 trades**; "all imbalance-based strategies perform poorly, negative across the
  board." (arxiv 2502.18625, 3-0). This is ST2.0's exact shape — and it's net-negative.

**3. The three compensations ST2.0 lacks.**
- **Speed:** "There is thus a rational for market makers to be as fast as possible as a
  protection to adverse selection"; latency erodes imbalance-timing value — can't cancel/
  reinsert fast enough to capture it (1610.00261, 3-0). ST2.0 has no latency edge.
- **Queue position:** front-of-queue fills suffer far less adverse selection than back
  (Binance: **−0.058 bp front vs −0.775 bp back**; 2502.18625, 3-0). Front-vs-back is worth up
  to a whole spread and is **symbol-dependent** (queue-value-2016, 3-0) — mirroring our ETH-vs-
  BTC fill spread. ST2.0 posts-and-waits ~20s → likely back-of-queue.
- **Rebate:** limit-order value decomposes as **V = α·(δ − β)** — fill prob × (edge δ minus
  adverse-selection cost β), where **δ = half-spread + rebate** (queue-value-2016 / Moallemi,
  2-1/3-0). With **Phemex rebate = 0**, δ is just the half-spread, and β frequently *exceeds*
  it → negative order value for some names (the paper shows PBR going negative). This is the
  fee-trap, quantified — and consistent with [[edge-hunt-exhaustion]] ("scalping is
  fee-trapped; no retail maker rebate").

**4. You can't predict your way out at a 15-min horizon.**
- Fill predictability with a deep RNN: **AUC 0.72 @1min, decaying to 0.66 @10min**
  (deep-lob-2021, 3-0). Conditioning a ~15-min entry on book state buys "real but limited"
  edge — not enough to flip the adverse-selection sign.

## The combined insight

Track A says ST2.0 bleeds via loss asymmetry and we can't yet measure why; Track B says the
*why* is structural adverse selection on passive fills, and that our exact strategy shape is
documented to lose on crypto perps without speed/queue/rebate. The two converge:
**"losers entered busier tape" (A) = "fills cluster at extreme imbalance / heavy buying" (B).**
The fill itself is the adverse event.

## What to actually do (honest, ranked — none are "deploy")

1. **Close the instrumentation gap (do this; cheap, no trading risk, unblocks everything).**
   The literature's whole answer is about fill-vs-miss and post-fill adverse selection — and we
   can't measure either on our money yet. Two changes: (a) log the ob/flow conditions present at
   every PostOnly **miss** (today only symbol+time are logged); (b) compute **post-fill
   adverse-selection** per trade (5s / 1min / hold-horizon mark vs fill price) now that `ob` is
   captured. Turns "execution is the bottleneck" from belief into a measured bp number, and
   feeds the confirm lab. **Highest-value next action.**
2. **Forward-test placement variants in the lab (hypotheses, low base-rate expectation):**
   (a) wait for buy-pressure to roll over (OFI flip) before posting, instead of posting at the
   imbalance extreme; (b) post-offset / deeper-in-spread variants; (c) per-symbol gating by
   *measured* adverse selection (not fill rate — fills ≠ wins). Set expectations low: the
   analogous Binance maker strategy lost money.
3. **Strategic decision for Jonas:** literature + our data both say passive execution of a
   short-reversion signal at small size, slow, no rebate is structurally adverse with no
   compensation available at this scale. Options: keep forward-testing execution refinements
   (low base rate), or accept ST2.0 as a measured non-edge and redirect. The forward-confirm
   loop (confirm.py, shipped today) is what adjudicates either way — and on 29 real trades it
   already reads `truth: accruing` (−0.12/trade), i.e. honestly not confirming.

## Sources (all primary unless noted; full quotes in the workflow output)
Moallemi/Maglaras queue-value (2016 + 2014 Paris MM); arxiv 2502.18625 (Binance BTC perp maker,
the on-point one); deep-lob-2021 (Columbia); arxiv 1610.00261 & worldscientific
S2382626617500095 (imbalance/latency/adverse selection); arxiv 1106.5040 (execution vs adverse
selection risk); arxiv 1210.1625 (optimal limit/market split); arxiv 1312.0514 (Lipton quote
imbalance). 24/25 claims confirmed; 1 killed (a too-strong "Theorem 2 monotonicity" claim,
0-3 — the real papers show the tradeoff empirically, not as the claimed theorem).
