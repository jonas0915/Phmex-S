# Overnight Program — Morning Report (2026-07-14)
**Status: FINAL (~1:30 AM PT). 12 agents run: 6 research + 2 live-web + 2 adversarial
verification + 1 code review + 1 follow-up test. One change STAGED (inert), nothing deployed.**

## TL;DR — your 3 morning decisions
1. **PT fee toggle** (guaranteed +, your manual action): PT into futures wallet, flip toggle.
   10% off maker AND taker, officially confirmed.
2. **Arm the V17 forward test?** Staged & audited: add `MR_SHORT_RSI_MIN=65` to .env →
   /pre-restart-audit → restart. MR shorts fire at RSI>65 (now hardcode-70). Evidence:
   CONFIRMED-WITH-CAVEATS — real replay math, no significance (needs ~334 fills to prove),
   worth ~$1-2/mo at current size. A scaling-rights test with kill criteria (TASKS.md).
3. Everything else tested tonight is CLOSED — 9 levers adjudicated dead/null with receipts
   below. No re-mining.

**The blunt truth about "profitable bot by morning":** no overnight lever manufactures edge.
The MR slot's expectancy upper bound is +$0.025/trade (CI straddles 0) at ~2.6 signals/day.
Tonight hardened the slot's evidence base, closed every cheap lever honestly, and staged the
one defensible knob. Consistency at meaningful scale still runs through the structural
decisions in memory/project_main_scalper_halt_2026-07-13.md.

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

## Candidate #1: V17 — MR short RSI 70→65 — VERIFIED (with caveats) and STAGED
- 90d replay: 1.47x signals, added 151 trades +$0.090/trade, 69.5% win. Adversarial verifier
  re-derived everything from raw rows AND stress-tested the grid against a line-faithful port
  of the live strategy: 455/455 signals exact, no lookahead, no overgeneration. Survives
  outlier trims and best-symbol removal.
- Honest size: fold-1 "win" is $0.003 noise; 2 weeks carry 78% of added dollars; diff-CI
  straddles zero; ~334 fills (≈2 yrs) needed for significance; ~$1-2/mo expected at current
  size. This is a scaling-rights forward test, not a P&L needle-mover.
- STAGED (inert): strategies.py threshold now `MR_SHORT_RSI_MIN` env knob, default 70 =
  bit-identical to today (compile OK, 430/430 tests, independent review clean, default-
  invariance + dotenv chain verified). Blast radius = 5m_mean_revert slot only (confluence
  culled its bb call in April). ARM: `MR_SHORT_RSI_MIN=65` in .env + audited restart.
  KILL CRITERIA in TASKS.md. REVERT: set 70 / delete line + restart.

## Web-research hypotheses (literature, URL-cited, fabrication-guarded)
- H1 (anchor requote at band, don't chase) — REFUTED ON OWN DATA: the current requote reprices
  to the live touch (bot.py:2508-2530, drift-capped), and that chase produced the only real
  requote fill (XRP 7/7 +$2.34). Anchoring at the band = resting longer at the limit, which the
  fill-capture study showed converts ~zero and skews toxic. Current design stays.
- H2 (MED, untested): posting DEEPER than the band lowers fill rate but raises per-fill
  expectancy. Only testable live (simulated fills are poor proxies). Parked as a possible
  future A/B; not built tonight.
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

## Candidate #2 — VERIFICATION VERDICT: REFUTED as a remove decision. GATE STAYS.
Adversarial verifier reproduced all 9 decisive sims exactly (independent engine, fresh data) —
the arithmetic is right, the INFERENCE is not: (1) "CI excl 0" at 4/4 winners is vacuous (all-
positive bootstrap can't include 0; sign test p=6.25% fails); (2) the "5/5 OB-unique winners"
cohort had a double-counted episode + one cohort assignment resting on a 70s-late snapshot;
(3) the two corroborating findings were 75% the same trades; (4) at real fill rates the removal
is worth ~$1/month upper bound. ACTION: keep gate ON (free — logging already exists), re-run
counterfactual at n≥10 imbalance episodes (~6-8 weeks), bar = mixed-sign CI or ≥9/10 wins.
Original screening finding preserved below for the record:

## [superseded screening finding] remove OB-IMBALANCE gate for MR entries only
- Counterfactual study (38 episodes 6/25-7/13, pipeline self-validated by reproducing both
  adjudicated 7/12 cohorts; 3 fresh-data spot-checks exact):
  · ob_imbalance blocks: n=4, ALL winners, +$0.75/trade, CI [+0.33,+1.30] excl 0.
  · Structural split of all 12 OB blocks: tape-redundant cohort = real losers −$4.73 (already
    caught by tape gate); OB-UNIQUE cohort = 5/5 winners +$4.30 CI [+0.53,+1.24].
  · OB gate = redundant-where-right, costly-where-unique. ob_wall + tape_divergence: KEEP
    (NULL). ob_spread: unadjudicatable (n=1, phantom-win trap).
- HONESTY: n=4 and n=5 cohorts — thinner than anything shipped before (7/12 exemption was
  n=10). 4/4 winners doesn't clear p<0.05 on sign alone. ⏳ adversarial verification running.
- Your call in the morning: ship live-bounded (no-shadow directive) vs shadow-tag to n≥15.
- Receipts: scripts/slot_lab/gate_block_counterfactual.py + scratchpad dump (verified).

## Symbol edge map — DATA ONLY, no proposal
- Only CI-excludes-zero positive: 1000PEPE (+$0.41/trade, 92% WR, n=13). Bleed side: ONDO
  −$6.45, BTC 35% WR −$3.64 (data only — do-not-blacklist-BTC directive respected), AAVE −$4.12.
- Discriminator NULL: MR edge not predictable from ATR%/band-boundness/ADX (all rho≈0).
- Expansion: SUI/BNB modestly positive (CIs straddle), OP reject, blind-add dilutes.
- Curated book (−5 bleeders +SUI/BNB): exp +$0.101 CI [+0.007,+0.195] — but selection-biased
  AND the most recent fold is flat-to-negative. NOT proposed; hypothesis-generation only.
- Receipts: reports/mr_symbol_map.json, reports/mr_expansion_90d.json.

## Verification pass (Phase 2) — both candidates attacked by independent agents
- V17: CONFIRMED-WITH-CAVEATS → staged (see Candidate #1).
- OB-imbalance removal: REFUTED → gate stays (see Candidate #2 section).
- Method note: both verifiers rebuilt the math independently (one wrote its own exit engine
  and matched 9/9 sims to the cent; the other ported the live strategy line-by-line and
  matched 455/455 signals). First-pass agent numbers were arithmetically right both times;
  one INFERENCE survived, one didn't. The verification layer earned its cost.

## Bot state at report close (~1:30 AM PT)
PID 7730, zero errors since 9:14 PM restart, 0 open positions, main entries halted, MR slot +
ETH-TSM active, no MR signals overnight (normal at ~2.6/day). Staged strategies.py change is
INERT until restart — running bot unaffected.

## The honest bottom line
The bot's consistent profitability does not hinge on any overnight lever — the MR slot is a
low-frequency, marginal-expectancy strategy (+$0.025/trade upper bound, CI straddles 0, ~2.6
signals/day). Tonight closed every cheap lever with receipts, corrected one prior finding
(the "misses were winners" study partly priced fills that never happened), staged the one
defensible knob (V17), and queued the one honest re-adjudication (OB-imbalance at n≥10,
~6-8 weeks). None of this turns MR into a strong edge. Consistency at meaningful scale still
runs through the structural decisions in memory/project_main_scalper_halt_2026-07-13.md —
and the single highest-EV action available this morning remains the PT fee toggle.
