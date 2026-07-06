# Overnight Research Report — Main Bot: Fills, Entries, A+ Setups, TPs
**For Jonas — compiled 8:15 AM PT 7/6** (due 5 AM; delivery late — an API session limit
suspended the session ~11:55 PM–8:05 AM; all round-1 work completed before the cutoff,
two follow-up agents resumed this morning, results below marked PENDING where affected.)

## The one-line answer (CORRECTED 8:40 AM — see revision note)
**Every proposed mechanism was tested tonight and came back null — including, in the
final result, queue-conditioned posting (the toxicity link failed on our own 101 fills).
The honest conclusion: the best solution for the bot was already deployed last night —
trail-arm 8% (the only lever that ever tested positive twice) at $15 size — and the
right move now is disciplined data accrual under the new adjudicator, not another
mechanism. Tonight completed the proof that no further edge is extractable from the
data the bot currently records.**

*Revision note: the 8:15 AM version of this report recommended queue-state
instrumentation → conditioned posting, based on verified external evidence and two
agents flagging the instrumentation gap. The final agent then finished the direct test
on OUR fills (101 fills + 100 misses, exact queue rebuilt for 29 anchors): queue size
predicts fill probability (CI [+0.18,+3.14], replicates 7/03) but NOT fill toxicity
(null in every cut; the published clean-cell pattern: +0.03 [−0.29,+0.34] at our
granularity). Measured reality on our data beats the external transfer — the
queue-conditioning thread is closed, the gate should not be built.*

## What was tested tonight (receipts in docs/overnight-2026-07-05/ + reports/*.json)

**1. Exit side — now 100% CLOSED, with final receipts:**
- Wider SL (1.5/2.0%): REFUTED. June replay (86 entries, arm-8 parity): −41%/−57% net,
  worse in 4/4 half-cells; 15/21 stops ride through even 2.0% (71%-DOA reconfirmed);
  at $15 one wider stop ($2.25–3.00) > daily halt ($1.76) → every stop ends the day.
- Partial-TP thresholds (+6/+10/+12): NULL. Rig extended (faithful port, 0/86 regression
  diffs); deltas ~10x inside rig error; WR identical everywhere. Keep 10.
- 75/25 scale-out fraction (verified external finding): NULL (completed 8:20 AM).
  Best cell f75×t6 +5.5% but ~4x inside rig error, fails both-halves bar, WR flip rests
  on 4 trades. No deploy. If a partial-TP forward test is ever wanted, that's the cell.
- These were the last two untested exit levers ever proposed. Every exit-geometry lever
  in the bot's history now has a tested verdict: the exit stack is optimal as-is.

**2. Entry side ("A+ setups") — NULL again, honestly:**
- ~40 hypotheses on 101 June+ fills with holdout + selection deflation: early-drift
  gating of concurrent entries NULL; all 10 feature×regime interactions NULL; RSI-floor
  transfer to main bot structurally NULL (0/87 longs would ever trigger it).
- One parked hypothesis (losers enter at higher HTF ADX, ~40 vs 36) — fails deflation
  today; pre-registered for re-test at 2x sample. NOT an action.
- Conclusion: A+ setups are not findable in the features we currently record.

**3. Fill side — the live lever, and the gap:**
- Verified external evidence (10 sources fetched + quoted, 1 excluded unverifiable):
  fill probability is almost fully determined by near/opposite queue sizes (R²=0.946,
  233k-order Binance perp study); the ONLY near-clean markout cell is posting into a
  LARGE same-side queue against a SMALL opposite queue (−0.06bp vs −1.16bp worst);
  profitable maker fills are predictable "reversals" from placement-time features.
- FINAL RESULT (8:35 AM): the direct test on OUR data came back NULL. Queue size
  predicts fill probability (significant, replicates 7/03) but NOT toxicity: exact
  loss-vs-win rel-queue wrong-signed (n=9/9), depth proxies null, the published
  near×opposite clean-cell null at our granularity. Misses occupy the same book states
  as fills and skipped-miss sims were ~breakeven ("misses aren't missed winners"
  reconfirmed). The in-sample depth rule that looked good is a post-hoc sweep pick —
  not deployable. VERDICT: close the queue-conditioning thread; do not build the gate.
  Instrumentation extension (entry_snapshot depth/touch fields, zero API calls) is
  cheap but LOW expected value — do opportunistically at a future audited restart only.
- Taker-switching: verified DEAD (needs ~1bp edge; Phemex fees 6bp/leg). Branch closed.
- Parked screening leads (fail deflation today, auto-retest on fresh data via the lab):
  htf_adx main effect; wide-spread signal states (1-of-8 tests, artifact-suspect).
- NEW (from the resurrected 3 AM nightly-research run): Phemex exposes an order-replace
  endpoint (ccxt edit_order) that MAY preserve queue position on price amendment —
  undocumented; needs one controlled test order. If true, re-quoting without losing
  queue standing changes the fill economics materially.

**4. Execution-quality baseline (new watchdog, first real run):**
- Rolling 14-day entry adverse-selection: −5.33bps@1m (n=60, CI [−11.0,−1.3]) vs the
  −4.5bps historical baseline — slightly worse, inside alert thresholds. This is the
  number queue-conditioning must move.

## Recommendation (one primary — corrected)
**PRIMARY — Run the deployed experiments to verdict; no new mechanism ships.**
The only lever that ever tested positive on two independent windows (trail-arm 8%) went
live last night at $15 size, and tonight's sweep proved every other proposed mechanism
null on our data. The constructive program is now: (1) wire the adjudicator + drift
watchdog into the nightly launchd slot so trail-arm-8, $15 sizing, and the MR bundle
get graded automatically with preset revert criteria; (2) let the two parked screening
leads re-test themselves on fresh data as it accrues; (3) the drift watchdog guards the
downside (alerts if adverse selection worsens past −6bps).

**Runner-up (only genuinely new, cheap probe):** one controlled Phemex order-replace
test to learn whether price amendment preserves queue position (from the 3 AM nightly
research). If yes, it improves the SLOT's re-quote leg (where misses ARE missed
winners) — not the main bot. Manual, reversible, ~$15 at risk.

**Optional housekeeping:** add depth/touch fields to entry_snapshot (exchange.py already
computes them; zero API calls) at the NEXT audited restart — not as its own deploy —
so the parked hypotheses become properly testable in 2–3 months.

## What NOT to do (tonight's receipts say so)
Wider SL, different partial-TP thresholds/fractions, early exits of any kind, taker
entries, RSI floor on main bot, feature/regime entry filters, streak-halting logic,
queue-conditioned posting gates on the main bot.
