# Overnight Program — Morning Report (2026-07-14)
**Status: DRAFT — agents still running; sections marked ⏳ update as results land.**

Goal (Jonas, 7/13 ~10 PM PT): improve 5m_mean_revert's trading + bot consistent profitability.
Method: 7 research agents (4 data replays on own 90d history, 2 live-web, 1 follow-up test),
adversarial verification on anything shippable, build what survives, pre-restart audit, stage.
**Honest framing up front: no lever found tonight manufactures a strong edge. What follows is
what the evidence actually supports, ranked, with receipts.**

---

## Bot state (unchanged tonight)
- PID 7730 since 7/13 9:14 PM PT. Main scalper HALTED (`.halt_main_entries`). 5m_mean_revert LIVE,
  ETH-TSM paper. 0 open positions at report time (verify at morning read).
- Restart gate: NOTHING deployed overnight; all changes staged for your "go."

## Item #1 — free money, your action: PT fee toggle (CONFIRMED at official source)
10% off BOTH maker and taker on USDT perps. Needs PT in the **futures wallet** + toggle flipped
(Account Overview / Fee Level). Source: phemex.com/help-center/how-to-use-pt-to-cover-trading-fees.
No rebate tiers reachable at our size (MM program needs >0.08% of exchange maker volume).

## Settled tonight (do not revisit)
- **Taker entries for MR: DEAD.** Own 90d replay: maker +$7.83 vs taker −$24.22 (n=309), all 3
  walk-forward folds negative, per-trade drag −$0.104. Mean reversion's edge IS the entry price.
- **Loosening confluence/ADX to trade more: DEAD.** Variant grid (19 variants, V0 reproduced
  baseline exactly): ADX 30→35 added trades at −$0.265/trade (CI excludes 0); RSI-AND-vol → OR
  flips expectancy negative. The confluence is load-bearing.
- **Strength gate 0.80 is INERT** — strategy only emits ≥0.85 (strategies.py:88,108). Frequency
  lives in internal thresholds, not the gate.
- **Amend-preserves-queue on Phemex: assume NO.** No documented keep-priority feature (official
  API docs + ccxt source checked). Requote redesign around queue priority is parked.
- **Signal scarcity is by design:** ~2.6 qualified signals/day → gates 72% → maker misses 71%
  → ~8% conversion. A few trades/week is the structural ceiling of THIS signal.

## Candidate #1 (WEAK, forward-test proposal): V17 — MR short RSI 70→65, longs untouched
- 90d replay: 1.47x signals, all 3 folds beat baseline, added 151 trades at +$0.090/trade,
  69.5% win, 15 symbols, not outlier-driven. Rhymes with the validated 7/12 "MR shorts carry
  the edge" finding. BUT diff-CI vs baseline [−0.083,+0.127] straddles zero; picked after
  peeking at side-splits; grade WEAK. ⏳ pending adversarial verification pass.
- If you want it: bounded live forward test under no-shadow directive, with kill criteria
  (proposal staged in TASKS.md after verification). Rollback = one .env/param revert.

## Web-research hypotheses (literature, URL-cited, fabrication-guarded)
- H1 (MED): requote should reprice to the BAND/mean anchor, not chase last price (2 papers).
- H2 (MED): posting DEEPER than the band lowers fill rate but raises per-fill expectancy.
- H3 (turn-of-15m-candle) — TESTED: replay NULL (diff CI [−0.195,+0.150]); real-money
  UNDERPOWERED (n=6 turn cohort, point estimate +$1.31/trade hypothesis-consistent, all 5
  just-before-turn fills winners — but 6 trades is not evidence). NO ACTION; passive re-check
  at ~60-80 real closed trades. Replay can't test true entry minute (bar-close timestamps).
- Methodological cap (Lo/MacKinlay/Zhang JFE 2002): simulated fills are "very poor proxies" —
  every fill-related replay tonight is screening-grade; live fills are the only adjudicator.
- New mechanism lead: Phemex `LimitIfTouched` + PostOnly-on-trigger — park the entry server-side
  at the band instead of cycle-timed posting. Candidate only; depends on fill-capture results. ⏳

## Fill-capture study — DEFERRED LEVER CLOSED (WEAK, do not ship)
- Rest extension 45→60/90/120/300s: marginal-fill expectancy decays MONOTONICALLY with rest
  (+$0.089 → −$0.082, every CI straddles 0, n=6-10). Late returns are the toxic cohort, exactly
  as reference_fill_rate_research predicted. Requote-era misses: 60/90s converts ZERO.
- 2nd requote: marginal fills were losers (−$1.80, n=2). The one real requote win was the FIRST
  requote (XRP 7/7 +$2.34) — already shipped. Keep 45s + 1 requote as-is.
- Deploy blocker regardless: 180s cycle watchdog can't fit 90-120s rest + requote.
- CORRECTION to prior record: 2 of the "misses were winners" trades ($2.13 of +$3.55) never
  returned through the limit — priced at placement (simulated-fill trap). The prior study
  overstated the miss-capture prize.
- Knock-on: `LimitIfTouched` lead DOWNGRADED — server-side parking doesn't fix rare/toxic returns.
- Receipts: scripts/slot_lab/mr_rest_extension_study.py, reports/mr_rest_extension.json.
  Forward-test to confirm would need 3-5 months for a CI centered near zero — not justified.

## ⏳ Pending sections (agents running)
- Gate counterfactuals (OB gate 26% of MR kills — protecting or strangling?).
- Symbol edge map + expansion candidates (waiting on its 90d replay of new symbols).
- Phase 2 adversarial verification of all SHIP/forward-test candidates.
- Phase 3 build + tests + pre-restart audit (only for what survives).

## The honest bottom line (will be finalized at morning)
The bot's consistent profitability does not hinge on any single overnight lever — the MR slot is
a low-frequency, marginal-expectancy strategy (+$0.025/trade upper bound, CI straddles 0). The
levers above can incrementally raise trade count and fill quality; none of them turn it into a
strong edge. Structural options (scale, strategy class) were adjudicated earlier tonight — see
memory/project_main_scalper_halt_2026-07-13.md.
