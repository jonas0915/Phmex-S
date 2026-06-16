# ST2.0 maker-first active exit — 2026-06-15

Goal: add an active exit to ST2.0 (today: fixed ~15-min maker hold + passive
resting SL/TP, no trail/early-exit). MUST stay maker-first (+4.3bps maker /
−5.7bps taker). Approved: maker-first + both-sided replay BEFORE any live change.

## Step 1 — sandbox both-sided replay  ✅ DONE
- [x] Built `scripts/st2_lab/exit_replay.py` — reuses backtest.py's validated
      price-only trail fns (`_live_update_trailing`/`_live_check_breakeven`/
      `_effective_stop`) over the flow_capture price path. Maker/taker fee model.
      Both-sided: $saved-on-losers vs $clipped-off-winners (lessons.md:366).
- [x] Ran on REAL live ST2.0 (n=15, grew from 11 this session) + SIM (n=1016).

### Result (REAL set, n=15 — the truth set)
- Standard trail (arm @+5% ROI, also @+2%): **NET DELTA $0.000 — never engages.**
  No live ST2.0 trade reached even +2% ROI (live ROI min/median/max = −13.1 / −2.5
  / **+1.8%**). The trail is irrelevant to this trade population.
- Only an aggressive early-lock (arm @+1% ROI = +0.1% price @10x) engages: 7 trades
  armed → −$0.225 → −$0.155/trade, WR 33%→47%, both-sided +$1.05 (saved $0.87 on
  losers, +$0.17 on winners, no clipping). DIRECTIONAL on n=15, and at +0.1% price
  it's at the edge of the ~76-95s flow sampling resolution → fragile.
- SIM set (n=1016, fill-all, rosy baseline +$37): trail mildly +$5.08 (+0.005/trade),
  saved $14.2 > clipped $9.1. Sign agrees but baseline unrepresentative.

### Verdict
Do NOT deploy the standard trail — inert on real data. The real ST2.0 problem is
the SIGNAL (trades barely move favorably, max +1.8% ROI), not winners giving back
gains. No exit rule manufactures edge. The marginal early-lock variant is too thin
(n=15) + too fragile (sub-sample-resolution) to arm live now.

## Step 2/3 — HOLD (gated)
- [ ] Re-run when ST2.0 has ~30 real trades (st2-watch tracks it). If the early-lock
      both-sided edge holds on a healthier sample → audit → arm maker-only on approval.
- [ ] Bigger lever is entry signal, not exit — feed st2_lab, not exit tuning.

---

# Edge Construction Plan — 2026-06-12 deep dive

(Previous v7.0 Confluence plan superseded; in git history at 57f4051.)

Source: 4-agent deep dive (exits, execution, signals, data assets). All findings
verified against trading_state.json, bot.log, and the gate-sim/replay docs.

## The thesis

The book's #1 measured problem (avg loss 1.8x avg win → breakeven WR ~65-73%)
is **self-inflicted, not market structure**: it began exactly when adverse_exit
was disabled on 5/7 (.env AE_THRESHOLD=-999). Since then 61.5% of losers ride
the full fixed 1.2% SL (−$1.30 avg, 89% of loss dollars) while the bot's own
trail/early-exit machinery banks winners at +$0.21–0.49 (TP 1.6% hit 6x in 607
trades — unreachable). Realized R:R on a SL ride = 0.37. Fixing the exit
geometry + arming the two cross-validated entry gates is the highest-probability
path to positive expectancy with the system as built.

## Phase 1 — Offline validation (replay A/Bs; no live changes)
- [ ] Plumb backtest.py constants to CLI: SL_FLOOR_PCT (:77), TP_CAP_PCT (:78),
      EARLY_EXIT_MIN_ROI (:585), trail tiers (:593-599), time-ratchet hook in
      check_exits_live step 6 (:802-804)
- [ ] A/B 1: SL floor 1.2% → 0.9% / 0.8% (structural R:R 1:1.78 / 1:2.0)
- [ ] A/B 2: time-ratcheted SL (1.2% → 0.8% @60 cycles → 0.6% @120)
- [ ] A/B 3: deep-red 2h cut (ROI < −6% @120 cycles)
- [ ] A/B 4: EARLY_EXIT_MIN_ROI 3% → 6% (score saves AND caps per lessons.md:354)
- [ ] A/B 5: trail tier-1 lock removal / arm at +8%
- [ ] Run each via scripts/calibrate_exits.py (45-entry rig) + full flow-replay;
      bar: delta positive outside the ±25% exit-model error band, both halves
- Prior negatives respected: NO AE-threshold sweep {−2..−6}, NO trail-to-BE+3%

## Phase 2 — Execution fixes (code, needs pre-restart-audit + Jonas approval)
- [ ] Urgency-gated maker exits: close_long/short(urgent=) → _try_limit_exit
      patience. Patient (20-30s): flat_exit, time_exit, cycle TP. Urgent (taker,
      skip the doomed 4s limit): SL, trailing, adverse, early_exit, trend_flip,
      watcher, emergencies. Machinery exists (MAKER_EXIT_ENABLED) — never armed.
      Prize $14-24/yr (25-40% of account); also stops watcher SLs burning 4s.
- [ ] TP race fix: watcher skips take_profit enforcement when exchange TP rests
      at same level; treat Phemex 11011 as "closing elsewhere", not failure.

## Phase 3 — Signal hygiene (shadow-validated, needs Jonas approval to arm)
- [ ] Gate A: block aligned lt_bias ≥ 0.40 — strongest measured gate (+$9.84
      NET, pRnd 0.024/0.007, both methods agree; reproduced independently on
      185-trade join: 32% WR cohort). Shadow-armed since 6/11 (sg_ltbias040),
      forward n=3. Arm at June 23 checkpoint if forward agrees.
- [ ] Gate D: block UTC 21-23 (sg_utc2123, pRnd 0.018) — same checkpoint.
      Caveat: replay says magnitude shrinks dynamically (+$1.53); hour edges decay.
- [ ] Remove whale boost (strategies.py:596-601) — inverted, monotonic, both
      sides (boost cohort 37.5% WR vs 52.6% without). Hygiene; subsumed by A.
- [ ] Close QUIET exemption (bot.py:1337-1351) — measured leak −$5.45/18; its
      criterion (cvd_slope >0.2) selects the worst cvd bucket (−$0.197/trade).
- [ ] Short penalty −0.04 (bot.py:1077-1079): penalizes the better side
      (shorts −$0.069 vs longs −$0.116/trade, n=607). Needs gate-sim
      counterfactual on 0.80-boundary trades BEFORE touching.

## Phase 4 — Data unlocks (cheap now, pays in 2 weeks)
- [ ] Raise l2_tick_recorder RETENTION_DAYS 14 → 60 (one constant; without it
      the dataset self-caps at exactly 14 days rolling — silently destroys the
      "weeks of data" precondition)
- [ ] Add watch_trades (tape prints) channel to recorder — needed for real
      fill/adverse-selection model; book-only top-5 can't measure queue position
- [ ] ~June 26 (2 weeks coverage): validate exit-replay fills against L2 ground
      truth (BTC/ETH/INJ/ARB); re-run imbalance Scenario B w/ trade-through fill model

## Standing experiments (untouched by this plan)
- 5m_mean_revert live 50-trade Kelly test (auto-demote −$5 net / neg Kelly @10)
- Durable-trail GO/NO-GO ~June 23
- Shadow gates A/D forward accumulation → June 23 checkpoint

## Review
(to be filled after each phase per workflow)
