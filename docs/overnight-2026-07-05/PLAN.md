# Overnight Research Program — 2026-07-05 → 07-06

**Directive (Jonas, ~9:30 PM PT 7/5):** all-night research on the main bot's issues —
fills, entries, entering A+ setups, hitting TPs. Test findings, narrow to the best
solution. Report due 5:00 AM PT. Also: repurpose st2-lab (adjudicator + execution
watchdog + queue study) — approved "go for it."

**Hard constraints from memory (violations = wasted night):**
- Exit-geometry dead-end inventory is COMPLETE — do not re-test SL floors, trail bands,
  AE thresholds, time-ratchets, deep-red cuts (reference_sl_loss_levers_2026-07-02).
- Only sanctioned untested exit levers: wider SL replay (1.5/2.0), partial-TP variants
  (+6/+12 vs +10). Rig does NOT model partial-TP — needs extension first.
- Entry features 8/9 NULL loser-vs-winner; gate-quantify NULL; no tilt; hour/day NULL.
  Signal mining from this data = artifacts (edge-hunt-exhaustion). Any "A+ setup" claim
  needs holdout + deflated stats + labeled screening-grade.
- Fills: re-quote on MAIN bot = NULL (do NOT port). Sanctioned lever = queue-state
  conditioning (fill_rate_research 7/3: front-of-queue 13x less toxic).
- Never post inside spread. Never fabricate citations (verify every external claim).
- calibrate_exits.py runs MUST pass --trail-arm-roi 8 (live parity since tonight).
- Live bot: NO code/config changes tonight. Research + replay only. PID 17846.

**Current bot state:** $15 sizing + trail-arm 8% live tonight; halt-paused until
midnight PT; MR bundle live on slot; nightly-research resumes ~midnight (fixed).

## Round log
- R1 dispatched ~9:35 PM PT: queue-state fill study; partial-TP rig extension + head-to-head;
  wider SL replay; DOA-loser early-warning study; verified web research; lab-repurpose build.
- R1 results: (pending)

## Findings accumulator
(append verified findings here each round; mark VERIFIED / REFUTED / UNTESTED)

**[R1, ~10:15 PM] WIDER SL: REFUTED — KEEP 1.2%.** June replay (86 entries, arm8 parity):
SL1.5 −41% net, SL2.0 −57%, monotonic, worse in 4/4 half-cells. WR flat, avg loss balloons.
15/21 stops ride through even 2.0% (71%-DOA reconfirmed independently). Operational
kill-shot: one wider stop ($2.25/$3.00) > daily halt ($1.76) → every stop = halted day.
Deltas outside rig ±25% band, direction-consistent. Receipts: r1_wider_sl.md +
reports/widesl_june_*.json. Exit-side lever inventory now FULLY CLOSED (was last untested).
Memory follow-up: mark reference_sl_loss_levers COMPLETE at session end.

**[R1, ~10:20 PM] WEB RESEARCH: 10 sources VERIFIED (1 excluded 403/unverified).**
Receipts: r1_web_research.md. Transferables:
1. Queue-config gating spec (arXiv 2502.18625v2 detail): fill prob ≈ fully determined by
   near/opposite queue sizes (R²=0.946); only clean markout cell = large-near+small-opposite
   (−0.058bp vs −1.157bp worst); profitable fills are "reversals" predictable from
   placement-time features we already snapshot. → ROUND-2: replicate regression + 3×2
   bucketing on our 148 fills + 100 misses (merge with queue-study agent output).
2. Scale-out fraction: 75% (not 50%) at first TP won all top-5 of 8,960 configs
   (arXiv 2604.27150, weak evidence) → ROUND-2: add fraction variant to partial-TP rig runs.
3. Taker switching = verified DEAD at Phemex fees (needs ~1bp edge, fees 6bp/leg). Closed.
4. Use ≥5-level book imbalance not L1 (0.715 vs 0.580 acc); per-symbol max-spread filter
   idea; VPIN dead (AUC 0.55).

**[R1, ~10:35 PM] PARTIAL-TP THRESHOLDS: NULL.** Rig extended (faithful port, regression
check 0/86 diffs), June window arm8 parity: off +$14.57 / ptp6 +$15.12 / ptp10 +$14.38 /
ptp12 +$14.29 — WR identical everywhere, deltas ~10x inside rig error, both-halves FAIL
for all. Live PARTIAL_TP_ROI=10 as good as any; NO change. Receipts: r1_partial_tp.md +
reports/ptp_june_*.json. Exit-geometry inventory FULLY COMPLETE (thresholds were last).
→ ROUND-2 dispatched: 75/25 scale-out FRACTION variant (web finding #2) on same rig.

**[R1, ~10:45 PM] DOA/A+ ENTRY STUDY: NULL across the board (honest, ~40 hypotheses).**
Receipts: r1_doa_study.md. (a) Early-drift gate on 2nd/3rd concurrent entries: NULL
(CI [−0.73,+0.51], n=26 overlap entries; re-look at ~60). Overlap co-movement real (78%
sign agreement) but doesn't cash out. (b) All 10 feature×regime interactions NULL.
htf_adx main effect (losers enter at ADX 40 vs 36) PARKED as pre-registered re-test at
2x n — best-of-12 in-sample, fails selection deflation; NOT an action. (c) RSI-floor
transfer to main bot: STRUCTURAL NULL — 0/87 June+ main longs had RSI<22; cohort doesn't
exist on main; nothing to port. (d) Queue state at post time = INSTRUMENTATION GAP
(2nd independent flag tonight). DOA share 54% this window/method vs 71% in audit —
flagged, window+method differ. No early exit proposed (HOLD-beats-cut respected).

**[R1, ~11:00 PM] LAB REPURPOSE: BUILT.** scripts/lab_adjudicator/ (adjudicate.py +
drift_watchdog.py), zero live files touched, 334 tests pass (310+24 new). Real first
run: trail_arm_8 n=0 no-verdict (honest); sizing_15 pre-fix margins $9.27 (n=8, expected
— fix deployed after); mr_bundle 1/20 attempts. DRIFT WATCHDOG REAL SIGNAL: rolling 14d
entry drift −5.33bps@1m (n=60) vs −4.5 baseline — worse but inside alert thresholds
(−6.0/−6.5). WATCH. Real bug found: mr_watch attempts counter structurally dead ([MAKER]
lines lack slot tag) — follow-up, not modified tonight. Left to wire: launchd + --telegram
after Jonas approves format. Receipts: r1_lab_build.md.

**[~11:55 PM] SESSION LIMIT HIT — resets 1:20 AM PT.** Two agents died mid-work:
(1) queue-state study — died at "23 symbol-days, in-memory too slow, switching to
streaming pass per day file" (resume with that plan via SendMessage/agent resume);
(2) partial-TP fraction round-2 — died at "rig side — CLI knob + fraction-aware
accounting" (resume same way). REVISED SCHEDULE: idle-chain hourly wakeups → at
~1:25 AM resume both agents → collect ~2:30-3:30 → compile REPORT.md by 4:10 AM,
Telegram by 5:00 AM. Everything else already landed (see accumulator above);
even if the two resumes fail, the report can ship on R1 results + the
instrumentation-gap recommendation.

**[8:15 AM 7/6] REPORT SHIPPED** (REPORT.md + Telegram) — 3h late due to the session
suspension; primary rec = queue-state instrumentation → conditioned posting.

**[8:20 AM 7/6] PARTIAL-TP FRACTION (R2): NULL.** f75×t6 +$0.80 (+5.5%) — only variant
that flips 4 losers to winners (WR 68.6→73.3) but ~4x inside rig error, both-halves FAIL.
No deploy. Noted as the nominated cell if a partial-TP forward test is ever wanted.
Rig now has --partial-tp-fraction knob (regression-checked). reports/ptp_june_frac*.json.
Queue-study agent still PENDING.

## Report
Due 5:00 AM PT at docs/overnight-2026-07-05/REPORT.md + Telegram summary.
Must contain ONE primary recommendation (don't flip-flop), runners-up, receipts.
