# Phmex-S Pivot Plan: Slow Trend Follower (FINAL, reviser seat, Sun 9/27/2026)

Path shorthand: P = `/Users/jonaspenaso/Desktop/Phmex-S/`, MEM = `/Users/jonaspenaso/.claude/projects/-Users-jonaspenaso-Desktop/memory/`.

How numbers are labelled:
- A plain citation means the seat or the file it names.
- "Reviser recompute" means I re-ran it this turn from `P/donchian_signal_{BTC,ETH}.json` (key `days`) or `P/trading_state_DONCHIAN_*.json`.
- "Judgment" means a threshold with no source. I set every judgment threshold on 9/27, with 72 of the 89 review days already visible, and they are disclosed that way.

The Mac clock is on EDT: `/etc/localtime` has pointed to America/New_York since Sep 26, 7:19 AM. All times below are converted to PT.

---

## (0) Do this first: the host is on battery

- `pmset -g batt`, read by the reviser at about 5:55 PM PT: "Battery Power … 24%; discharging; 1:13 remaining".
- MEM/feedback_host_sleep_suspends_bot.md says AC power is non-negotiable.
- The 9/9–9/20 outage is what caused the ETH fidelity breach (section 2, A2).
- **Owner action, tonight:** plug in the Mac with the lid open. This is not a halt or a bot change.
- Every section below depends on uptime (see C4 in section 7).

---

## (1) Verdict

1. **Direction.** Retire short-horizon trading and make the bot a slow, long-or-flat trend follower on BTC and ETH only. It runs the frozen 9-lookback Donchian ensemble, and every other book stays retired. The reason: everything short-horizon is on the dead list, and so is every simpler trend variant (DEAD_LIST rows 5, 12, 13, 14).
2. **What the evidence actually is.** Donchian is not a proven edge. It is the one candidate that has not yet been killed.
   - **Out-of-sample bear replay** (P/reports/2026-07-16-wake-report.md:61-62):
     - BTC −11.5% against buy-and-hold −44.0%.
     - ETH −4.9% against −48.0%.
     - It lost money outright, so it did worse than holding stables.
     - It was compared only with 100% buy-and-hold.
     - A static position at the paper-window average weight (BTC 0.242, reviser recompute) would have lost about 0.242 × 44.0% ≈ 10.6% (arithmetic). For BTC, that cannot be told apart from simply holding less. ETH's static equivalent is about 0.206 × 48.0% ≈ 9.9%, so ETH does look better.
     - UNVERIFIED until the replay's own average weight is known. The scripts were lost (MEM/reference_nobarriers_search_2026-07-16.md:22).
   - **Paper window, 7/16–9/27** (reviser recompute):

     | | Timed replica | Constant-weight hold at same average w | Static buy at 7/16 at average w |
     |---|---|---|---|
     | BTC | $6.45 | $7.16 | $7.81 |
     | ETH | $5.53 | $8.19 | $9.12 |

     In the only live-data window, the timing added nothing over plain beta.
   - **It has never faced the bar that killed its relative.** BTC-TSM died on a deflated Sharpe of 0.635 against a 0.95 bar, with a Sharpe-difference CI against buy-and-hold that included zero (MEM/reference_btc_tsm_kill_test_2026-07-15.md:10-26). No deflated Sharpe or Sharpe CI has ever been computed for Donchian.
   - **It was chosen from a multi-candidate search** (nobarriers:10-14), on the same bear test now cited as its proof (wake-report:58-69).
   - **The only long-sample figure is borrowed:** Concretum/SSRN Sharpe 1.56, 2015–Mar 2025 (spec:5). That window includes 2021, which our own memory calls "the 2021 parabola artifact" for higher-timeframe trend (MEM/reference_edge_hunt_exhaustion.md:19).
3. **At $87 this is not an income decision.**
   - BTC cannot trade. ETH is at most one lot, on or off (section 4).
   - At $87, a 25% APR is about $22 a year (arithmetic).
   - The 10/14 review can prove faithful execution. It cannot prove edge. Reaching n=50 needs 37–40 weeks at the spec's cadence (`fee_math.time_to_verdict_weeks`, verdict seat).
   - Therefore "hold stables and keep Donchian on paper indefinitely" is a first-class outcome of 10/14, not a fallback (section 3, decision map).

---

## (2) Phase 0: now to 10/14/2026

Nothing here places an order, restarts the bot or touches `.env`. Any step that changes code, launchd, a sentinel or a KB file is marked **OWNER GO**. Any restart also needs `/pre-restart-audit`. Nothing in Phase 0 asks the owner to decide anything about live Donchian (I7). Live-related work is drafted and held for 10/14.

### A. Fix the record (week of 9/28)

- **A1. OWNER GO: append the existing 9/21 ruling to the KB.** This records a decision already made; it is not a new proposal.
  - Stale entries: DEAD_LIST row 33 (P/research/swarm/kb/DEAD_LIST.md:45, "owner DECLINED live 9/8 … never re-offer"), STANDARDS #14 (P/research/swarm/kb/STANDARDS.md:16, which lists "Donchian live" among never-re-propose items), and the wind-down line in MEM/MEMORY.md.
  - The newer ruling is MEM/project_mr_paper_donchian_live_2026-09-08.md:21: "Owner's own ask lifts the 9/8 'never re-offer' for that date only; do not raise it before 10/14."
  - The KB is append-only, so the fix is an appended ruling row.
- **A2. Log the ETH fidelity breach as a BUG, by the letter of the spec. No waiver** (fixes I1).
  - Spec:45 says "daily |bot w − replica w| > 0.10 on >3 days in 14d → BUG, fix or kill."
  - Book against replica breached on six ETH days: 7/26, 7/27, 9/10, 9/15, 9/16, 9/17. The donchian seat and the critic confirmed this independently. BTC had none.
  - Four of those days (9/10, 9/15–9/17) fall inside one 14-day window.
  - The verdict seat's "0 breaches" compared `w` with `w_target` inside the signal file. That is the replica against itself (max gap BTC 0.012, ETH 0.009, reviser recompute), not the spec's test.
  - Cause of the September days: the bot was down from after the 5:01 PM PT eval on 9/9 until 9:04 PM PT on 9/20, and the paper book held a stale size (donchian seat, `logs/bot.log.4` / `bot.log.3`).
  - Cause of the 7/26–7/27 days: UNVERIFIED, because those logs have rotated out.
  - **Pre-registered consequence**, set now before the remaining 17 days are seen: ETH counts as fidelity-clean at 10/14 only if all three hold:
    - (a) the root cause is fixed (uptime, section 0 and B9);
    - (b) no breach day falls in the 14 days before the cutoff (9/30–10/13);
    - (c) ETH is graded on its **ex-outage net**.
  - **Outage P&L to strip from ETH:** $1.11. That is the excess weight (book 0.3048 against replica w) × daily return × $100, summed over the 9/9–9/19 closes (reviser recompute; the critic got the same). 9/17 alone contributes +$0.69.
  - This explains $1.11 of the $1.30 gap between ETH book and replica. The planner's earlier $0.89 estimate is withdrawn.
- **A3. Record that the kill lines are not actually graded.** The spec calls them "adjudicator-graded" (spec:44), but Donchian is absent from P/scripts/lab_adjudicator/adjudicate.py (grepped by three seats). Also record that the paper position objects carry `"paper": false` (e.g. the open ETH position in P/trading_state_DONCHIAN_ETH.json; default at risk_manager.py:447, per the critic). Check this before any promotion (M1).

### B. Build the measurement (research scripts only, no bot restart)

- **B1. OWNER GO: automated fidelity grader.**
  - Book w = open notional ÷ $100, from `trading_state_DONCHIAN_*.json`.
  - Replica w = `w` in `donchian_signal_*.json`.
  - Sampled at 11:00 PM PT, 6 hours after the 5:00 PM PT roll (judgment, matches the donchian seat's method).
  - Output to both the adjudicator digest (Telegram, per owner directive) and `swarm_desk --mode maint` → PAPER_STATUS.md.
- **B2. OWNER GO: review script, frozen before 10/14.**
  - Commit sha recorded before 10/14 (STANDARDS #3).
  - Replica = `donchian_slot.run_history(closes)` (P/donchian_slot.py:192) on closes from 7/16 to 10/13.
  - P&L measured two ways: closed-book, and mark-to-market at the 10/13 5:00 PM PT close.
  - The script also computes every R-rule in section 3.
- **B3. Funding.**
  - Pull Phemex public funding history for BTC and ETH, 7/16 to 10/13, and charge w × notional × rate at each 8-hour settlement.
  - 7/16 to 8/10 from the cache: BTC 0.343%, ETH 0.119% of notional (verdict seat, `load_reference_funding`).
  - 8/10 to 10/13 is UNVERIFIED.
  - `funding_usdt` is 0.0 on all 36 paper rows.
- **B4. Replica-gap reconciliation.**
  - ETH: $5.534 replica against $6.833 book. $1.11 is explained by the outage (A2); the remaining about $0.19 still needs a row-by-row check.
  - BTC: $6.452 against $6.505.
  - Pre-listed mechanical adjustments are the only ones allowed: fees, fill price against close, outage excess weight, and the open position mark. Nothing else can be "explained away" (fixes I2).
- **B5. Stop-deviation replay.**
  - Measure the effect on replay return and drawdown of a resting disaster stop at (i) a fixed −8% and (ii) the lowest active sub-model stop.
  - Test each under two post-stop policies:
    - (a) re-enter to the policy weight at the next daily eval;
    - (b) stay flat until a sub-model flips.
  - This answers the whipsaw question in I6. It has never been measured (evidence seat, open question 7).
- **B6. Lot-rounding replay.** Floor rounding against round-to-nearest, at $87, $260, $500 and $1,000. It answers whether a one-lot ETH book still behaves like the ensemble.
- **B7. Independent re-derivation, feasibility first** (fixes I10, C1, C3).
  - **Step 1:** confirm whether at least about 815 daily bars (about 450 warmup + about 365 test, arithmetic) are obtainable. DATA.md:14 says ccxt reaches "~2 years", and it is committee-token gated. The original used "spliced+verified" data from an undocumented source (wake-report:60).
  - **If the bars are not obtainable:** record "B7 not possible". The out-of-sample result stays single-derivation, and that counts against FUND in R7.
  - **If they are**, rebuild with `run_history` and report:
    - (i) return and max drawdown against buy-and-hold;
    - (ii) the replay's own average w;
    - (iii) an **exposure-matched static-hold benchmark** at that average w;
    - (iv) a deflated Sharpe and a Sharpe-difference bootstrap CI against the exposure-matched benchmark, using the same bar that killed BTC-TSM (DSR ≥ 0.95; resample independently, then sort the differences, per MEM/feedback_bootstrap_diff_ci.md).
  - This is an implementation and benchmark check, not fresh evidence: the bear was the selection test.
- **B8. Hurdle comparison.** Compare replay and paper returns, net of funding, with the audited HLP 10–25% APR (nobarriers:57-61) and with holding stables.
- **B9. Uptime record.**
  - List every period the bot was down since 7/16 from the logs that still exist (bot.log.5 starts 9/5, per the donchian seat), and tag each ledger day as up or down.
  - Owner decision (not presumed): AC-only operation, or a second always-on host. MEM/project_mac_upgrade.md already plans an MBP migration.

### C. Reporting gaps (code, OWNER GO; scripts only, no bot restart)

- **C1.** `scripts/daily_report.py:174 paper_slot_summaries` leaves Donchian out. Add a Donchian Telegram section showing:
  - w, and how many sub-models are long;
  - net, both as booked and ex-outage for ETH;
  - funding-adjusted net;
  - fidelity state;
  - the replica and exposure-matched benchmark P&L.
- **C2.** Register DONCHIAN_BTC and DONCHIAN_ETH in `adjudicate.py` EXPERIMENTS, with the −$15 line and the fidelity line.
- **C3.** Dashboard `web_dashboard.py:838-850`: add the same fields as C1, so Telegram and the dashboard agree.
- **C4.** Fix the stale label at `web_dashboard.py:851`: "5M_MEAN_REVERT — LIVE FORWARD TEST" has been paper since 9/8 (M2, honest-data rule; reviser read the line).

### D. Retire or freeze the scalper machinery (every item OWNER GO, reversible, nothing deleted)

The standing rule is never pause or halt unasked (MEM/feedback_never_pause_bot_unasked.md).

- **D1. Unload dead-book launchd jobs.** `l2-recorder`, `st2-lab`, `nightly-research`, `mr-watch`, `mr-gate-archiver`, `flow-sanity`, `weekly-sweep` and `auto-lifecycle`. `auto-lifecycle` is inert but can write `.promote_`, `.kill_` and `.restart_bot`. The plist files stay on disk.
- **D2. Desk: move `desk-weekly` to monthly, or unload it.**
  - Never use `scripts/.halt_swarm_desk`: it also stops `--mode maint` and with it PAPER_STATUS (codemap coupling 5).
  - **Next run time is ambiguous** (fixes I12). The installed plist fires at Hour=3 local, with the Weekday key at line 29 and Hour at line 31 of `~/Library/LaunchAgents/com.phmex.desk-weekly.plist`.
  - The Mac has been on America/New_York since 9/26, so the next run on Sun 10/4 fires at either 12:00 AM PT (new zone) or 3:00 AM PT (stale registration). MEM/reference_launchd_stale_timezone explains why either is possible. UNVERIFIED which.
  - Check `launchctl print` for every PT-labelled job (daily-report, desk-maint, lab-adjudicator, code-health). Fix with bootout and bootstrap after the owner decides which zone the Mac stays on.
- **D3. Main scalper.** It is already paper via `.paper_main`, dated Aug 26. The owner may choose `.halt_main_entries` or a new Config early-return. There is no urgency.
- **D4. Scanner, WebSocket feed and L2 writer.** Retire only after the dashboard price source moves off `l2_snapshot.json` (coupling 1). Keep the STATS line on every path (coupling 2). The scanner and `TRADING_PAIRS` are `.env` changes, so the owner makes them.
- **D5. Keep every `trading_state_*` ledger.** Lifetime P&L is their sum.

### E. Prepare the live build: drafts only, held for 10/14, not put to the owner before then (fixes I7)

- **E1. Draft Donchian spec v2 on a branch, unmerged.** It must cover:
  - a live open, close and resize that trades only the difference;
  - a lot-rounding policy;
  - a 1x isolated pin per symbol;
  - a resting reduce-only disaster stop as a registered deviation from spec:56, sized from B5;
  - a written post-stop policy, (a) or (b) from B5;
  - the stop trigger price type. `exchange.place_stop_loss` sets no `triggerType` (exchange.py:1126-1146, reviser read), so it uses the venue default, which is UNVERIFIED as mark or last;
  - **why there is no resting take-profit** (I6);
  - a Donchian ownership lock;
  - funding recording;
  - trend-specific halts (see section 4, item 6);
  - a live fidelity line on lots;
  - a `VOL_CAP` of 2.0 against the 1x pin (M3: at w = 2 notional is twice the base; observed max vol_scalar is 0.748 BTC / 0.522 ETH, capital seat).
- **E1 on take-profit, the draft ruling for the owner at 10/14:** MEM/feedback_broker_side_exits_first.md requires a resting take-profit "and stop where the venue allows", and says any omission must be explained. For a trend follower, a fixed TP caps the right tail, which is where the rule's expected value sits (wake-report:69: "its EV lives in trending legs"). The draft therefore rests the stop only and states this reason, and the owner rules on it.
- **E2. Draft (do not present before 10/14) the sizing options.**
  - All $87 into ETH at today's w: a $26.07 target against a $26.87 lot gives **0 lots** under floor rounding (capital seat).
  - The 9/8 default base of $75 × w 0.2992 = $22.44, also 0 lots.
  - Options:
    - (a) round-to-nearest, a registered deviation. One lot is then about 30.9% of the account, and the position goes flat below w ≈ 0.154 (critic arithmetic). Live ETH is effectively an on/off switch, and a lot-fidelity line mostly measures its own rounding.
    - (b) add capital.
    - (c) no live build.

### What the paper test can and cannot show by 10/14

- **It can show:**
  - the rule was run faithfully (subject to A2);
  - book-to-replica gaps are explained only by the pre-listed adjustments;
  - both books are positive after funding and ex-outage.
- **It cannot show edge.** The −$15 kill line also cannot realistically trip at these weights. It would need about a 43% ETH fall with no exits at the observed max w of 0.353 (critic arithmetic), while the replica's mark-to-market drawdown so far is −$2.66 BTC / −$1.94 ETH (reviser recompute). So "risk stayed inside the kill lines" is guaranteed, not tested (I3). It is a catastrophe guard, not evidence.
- **Current state** (reviser read of the ledgers):
  - BTC: 16 rows, +$6.50.
  - ETH: 20 rows, +$6.83 as booked, about +$5.72 ex-outage (arithmetic, 6.83 − 1.11).
  - The top 3 trades in each coin make more than the total.
  - No test leg yet: the worst daily-close drawdown is −6.9% BTC / −5.6% ETH (verdict seat).

---

## (3) The 10/14 review: rules (set 9/27 with 72/89 days visible; disclosed)

Data cutoff: the 10/13 UTC close, 5:00 PM PT 10/13. The script and its sha are frozen before 10/14 (R0).

- **R0. Freeze the measurement.** P&L reported closed-book and mark-to-market; the ETH net is reported both as booked and ex-outage.
- **R1. Kill lines (applied first).**
  - Net ≤ −$15 on the $100 base (spec:46) → RETIRE. This is labelled a catastrophe guard (I3).
  - Fidelity per spec:45, book against replica → BUG. ETH follows A2's pre-registered consequence.
- **R2. Adjustment count against the replica's own cadence** (fixes I5).
  - The spec's "~65-70 adj/yr" (spec:47) does not say whether it is per coin, and this window runs faster: the replica changed w 22 times on BTC and 25 on ETH in 73 steps (reviser recompute), about 110 and 125 a year annualized (arithmetic).
  - Compare book adjustments (closed rows plus the open position) with replica w-changes over the same up-days, excluding B9 downtime.
  - Pass: within ±30% (judgment).
  - The earlier "ETH at 1.45× pace" flag is withdrawn. That was the rule's own behaviour on this window.
- **R3. Drawdown against the replica** (fixes I3).
  - The old absolute −$10 amber is dropped; it could not trip.
  - Amber if the book's mark-to-market drawdown is worse than the replica's mark-to-market drawdown on the same days by more than $1.00 (judgment) → EXTEND.
- **R4. Replica tracking.**
  - Mark-to-market net within ±$1.00 of the replica **after only the B4 pre-listed adjustments** (judgment).
  - The "or explained row by row" escape clause is removed (I2). A gap left after the allowed adjustments fails.
- **R5. Funding.** Both books must be positive after B3 funding. ETH is also judged ex-outage.
- **R6. Test leg, recorded as information and not as a kill** (fixes I4).
  - A test leg is an underlying peak-to-trough of at least 15% on daily closes, or 30 or more days inside a ±5% band (judgment).
  - If one occurs, the book is judged against the **replica on the same path** (R3/R4 tolerances). It is not judged against a buy-and-hold ratio. A correctly working rule cannot be retired for behaving like the rule.
  - The book-to-buy-and-hold ratio is recorded for context only. In one 15% leg, the 150-, 250- and 360-day stops won't fire, so a loss of about w × 15% is expected (critic).
  - If no leg occurs, the next checkpoint is the end of the first test leg or 1/13/2027, whichever comes first (judgment).
- **R7. Evidence bar, new** (fixes C1, C2, C3).
  - (a) Paper replica P&L against the constant-weight exposure-matched hold on the same window. It currently trails: BTC $6.45 against $7.16, ETH $5.53 against $8.19 (reviser recompute).
  - (b) The B7 result against the exposure-matched static benchmark with DSR ≥ 0.95, the same bar as BTC-TSM.
  - (c) The B8 hurdle.
  - R7 cannot be met by 10/14 on paper data alone. It gates FUND, as below.

**How outcomes map to decisions**
- **RETIRE the book:**
  - an R1 loss kill;
  - R4 still failing after the fix window, defined as 30 days from 10/14 (judgment; fixes M4);
  - or B7 completed and failing the exposure-matched DSR bar.
- **EXTEND PAPER to the next checkpoint:**
  - an R1 fidelity bug not yet cleared under A2;
  - R2 outside ±30%;
  - R3 amber;
  - R4 open inside the fix window;
  - a book between −$15 and $0 after funding;
  - R7(b) impossible or not yet run;
  - or no test leg and the owner prefers to wait.
- **HOLD STABLES / PAPER INDEFINITELY:** B8 shows the replay does not beat stables or HLP after costs and funding, or the owner declines to add capital. This is the honest default at $87 (I13).
- **FUND:** offer the ETH-only live build agreed on 9/21 (MEM/project…:21). It requires all of the following:
  - R1 through R5 pass, with ETH fidelity-clean under A2;
  - R7(b) passes;
  - and the owner picks E2 (a) or (b).
  - Caveat: without a test leg, this checks execution; it does not prove edge.
  - BTC stays paper. OWNER GO is required before any build starts.
  - On today's evidence (R7(a) trailing, B7 feasibility unknown), FUND is unlikely at 10/14. EXTEND or HOLD STABLES is the expected outcome.

---

## (4) Phase 1: if funded (not before a 10/14 GO)

### Build scope (about 250–300 lines, per MEM/project…:14)

1. **Order path.** Replace the stub at `bot.py:4938-4949`, which returns "LIVE mode unsupported — book untouched".
   - Live open, close and resize that trades only the difference, with reduceOnly partial closes.
   - Template: `_tsm_try_entry` at bot.py:4659, with taker fallback through `exchange.py:1158 open_long_market`.
2. **Resting broker-side stop from day one.**
   - Place with `exchange.py:1126 place_stop_loss`; move with `:933 move_stop_loss` after each daily eval and resize; heal every cycle through `:1009 verify_sl_order` (TSM pattern bot.py:4516-4527).
   - The level, the trigger type and the post-stop policy come from spec v2 and B5.
   - No resting take-profit, with the reason stated in the spec (E1).
3. **Leverage pin.** 1x isolated per symbol, flag saved first (`exchange.py:1113`, `bot.py:4464`). The exchange is at 10x today (MEM/project…:14).
4. **Ownership.** A Donchian lock like `bot.py:4431 _tsm_locks_symbol`, plus a pre-entry position check. Save ownership before the first reconcile, so `_adopt_orphan_position` (:5297) cannot bracket the position. Flip the `"paper": false` default on Donchian positions to explicit tagging (A3).
5. **Evaluation order.** Run the Donchian eval and the stop-health check **ahead** of the early returns: ban mode at :1653/:1677 and warmup at :1734-1747.
6. **Trend-specific halts** (fixes I9). Every scalper-era block that currently gates Donchian up-sizes must be reviewed:
   - `_slot_entries_blocked` (bot.py:2905-2914, reviser read) blocks on `.pause_trading`, `.max_dd_halt` or the main book's `_drawdown_pause_until`. It is called for Donchian at bot.py:4958-4962, and it produced the 9/20 "up-size deferred — account halt" messages.
   - The daily-loss halt at :1428.
   - Give trend books their own drawdown rule. Keep the manual `.pause_trading` path (owner control).
7. **Funding.** Record it per settlement.
8. **Telegram.** Custom live entry and exit messages like TSM's at bot.py:4803; verify that `daily_report.py:98 live_slot_summaries` picks up the slot.
9. **Dashboard.** A live card with lots, stop level, leverage, funding and fidelity, replacing the hard-coded "(PAPER)" at web_dashboard.py:838-850.
10. **Tests, audit, go.** Update `tests/test_donchian_slot.py` (it pins the stub; line 553 per memory, not re-read), then `/pre-restart-audit`, then the owner's go.

### Capital (capital seat; today's w and prices; lots BTC 0.001 = $84.41, ETH 0.01 = $26.87; per coin)

| Threshold | ETH | BTC |
|---|---|---|
| One lot at today's weight | about $90 | about $172 |
| One lot when fully long | $60 | $134 |
| Five lots | $449 | $859 |
| Full sub-model fidelity | $538 | $1,202 |

- Balance: $87.12 (logs/bot.log STATS 9/27; matches docs/2026-09-16-edge-swarm-v1/03_exchange_economics.md:7).
- Funding on a 30-day long: 0.42%–0.90% of notional, which is 6 to 13 times the 0.07% round-trip fee (capital seat).

### Counterparty and venue (new; fixes I11)

- All capital sits on one exchange. Before any added capital, the owner sets a maximum balance to keep on Phemex and a withdrawal plan (owner decision).
- **UNVERIFIED:** Phemex security incident history, including a reported January 2025 hot-wallet incident that is not in this repo.
- **UNVERIFIED:** whether the owner's jurisdiction is permitted under Phemex's terms. Check Phemex's restricted-jurisdiction list. Other venues were already rejected over US geoblocks (nobarriers:44).

### First-30-day kill lines (pre-register before go-live; judgment items need owner sign-off)

- **Disaster stops:** 2 resting-stop fills → demote to paper. Precedent: the ETH-TSM kill criteria "2 disaster stops" (wake-report:138). This replaces reliance on the −$11 `loss_cap_usdt` (MEM/project…:16), which on one ETH lot needs about five −8% stops at about $2.17 each before it trips (critic, I3). Keep −$11 as a backstop.
- **Unprotected position:** open with no verified resting stop for more than 1 cycle → Telegram CRITICAL; a second occurrence → demote (judgment).
- **Lot fidelity:** held lots ≠ policy lots on more than 3 of 14 days → demote. Days after a disaster-stop fill are excluded if spec v2 chooses post-stop policy (b) (judgment).
- **Scalper interference:** any scalper bracket or orphan adoption on the symbol → demote immediately (judgment).
- **Leverage:** exchange leverage ≠ 1x while open → alert; demote if it does not heal (judgment).
- **Uptime:** more than 24 hours of bot downtime while a live position is open → Telegram CRITICAL (judgment; the resting stop is the protection).
- BTC stays paper under the −$15 line.

---

## (5) Phase 2: second-sleeve research through a redirected desk

The desk cannot screen slow ideas today (verdict seat):
- The schema accepts only `mr_edge` and `long_1h`, at 5m and 1h (desk.js:200-201).
- `long_1h` covers 2025-06-27 to 2026-08-01 (DATA.md:9-10), too short for the 450-bar warmup.
- screen.py:93-94 has no signal exits and no funding charge.
- The viability bar demands at least 1.92 trades a week (CONSTRAINTS.md:20-24, fee_math.py:32).
- Each run costs about 2.5M tokens (README.md:163) (M6).

**Order of work (each step OWNER GO; nothing runs monthly until steps 1–3 land):**
1. A multi-year daily dataset with its own holdout. A source reaching past about 2 years is UNVERIFIED. This is the same blocker as B7.
2. A signal-exit mode and a per-settlement funding charge in screen.py, with tests.
3. Rewrite the CONSTRAINTS.md:4 and :20-24 viability rules for 1x vol-targeted sleeves, using a daily-return bootstrap.
4. Mandate changes:
   - desk.js:65: median hold of at least 3 days, plus a required `corr_to_donchian` (judgment).
   - desk.js:106: the gatekeeper rejects short horizons and |ρ| > 0.5 (judgment).
   - desk.js:64 and :74: signal exit, or targets of at least 1000 bps.
   - Drop the intraday lenses.
   - `max_analysts` 8 → 4 and `max_screens` 5 → 2 (judgment).
5. Cadence: monthly (Day=1) in both plist copies, then bootout and bootstrap. Resolve the timezone first (D2).

**Scope rule:** a second sleeve needs a non-trend mechanism. A second BTC/ETH trend sleeve would relabel rows 5, 12, 13, 14 or 33.

**Removed from Phase 2** (fixes I8):
- Row 34, the linear-vs-inverse funding spread, is "REAL — PARKED until ~$2K" (DEAD_LIST.md:46, reviser read). It stays a capital-triggered parked item, not a candidate at $87.
- Inverse BTCUSD for sub-lot BTC was "not proposed" (MEM/project…:15, reviser read). It is also coin-margined (BTC collateral plus a long gives roughly double BTC exposure, which is unmodelled), so it is dropped from the plan.

---

## (6) What we will NOT do

- **Any short-horizon or scalper book, including re-arming a demoted one:**
  - the main scalper and momentum_continuation (row 28);
  - ST2.0 (MEM/project_st2_status.md);
  - SR_BOUNCE;
  - 5m_MR;
  - cascade_v2.
- **Short-horizon breakout variants:** rows 66, 78, 82 and 84.
- **Relabelled trend variants:**
  - BTC-TSM(28,5), row 13;
  - the 12-coin basket TSM, row 12;
  - ETH-TSM-28, row 14;
  - cross-sectional momentum, row 5;
  - shorts;
  - coins beyond BTC and ETH;
  - tuning the frozen parameters (spec:10-12, 56).
- **VWAP+SMA cross:** row 32.
- **Carry and funding as a hunt:**
  - naked funding harvest, row 4;
  - spot-perp basis, row 11;
  - funding-spike carry, row 20;
  - re-running the funding, cross-sectional or OI hunt;
  - row 34 at $87;
  - the inverse BTCUSD route.
- **Owner-declined items:** small caps, BTC blacklisting, Tailscale, faster order-book polling.
- **Discretionary trading.** Excluding the one TRYB event, the 2022 record lost −$3,270.79 over 786 trades, CI95 about [−5.92, −2.5] per trade (MEM/reference_owner_manual_run_2022.md:16).
- **Live Donchian before 10/14:** nothing raised, presented or merged (MEM/project…:21).

---

## (7) Risks, and what would change the plan

- **C1/C2, beta not timing.** In the paper window the replica trails constant-weight hold by $0.71 on BTC and $2.66 on ETH (arithmetic from the section 1 table). **Would change:** if R7 and B7 show no advantage over the exposure-matched hold → HOLD STABLES / PAPER INDEFINITELY. There would be no reason to run a timed rule live over a smaller static position.
- **C3, double standard.** Until Donchian passes the DSR bar that killed BTC-TSM, it is described as "not yet killed", never as "survivor".
- **C4, single host.** The Mac is on battery, the time zone moved with travel, and the 11-day outage breached fidelity. **Would change:** a repeat outage during paper → the fidelity clock resets under A2. During live → the resting stop protects, and the downtime alert fires.
- **C5, outage P&L.** $1.11 of ETH's net came from stale sizing. ETH is graded ex-outage.
- **Two rallies make all the profit.** 8/17–8/21 gave BTC +$5.41 / ETH +$5.19; 9/18–9/21 gave +$3.11 / +$2.38 (donchian seat). Bear behaviour is untested on paper.
- **Stop deviation (B5)** may worsen the rule. If so, use a wider stop or the sub-model midline. The stop is never dropped (owner directive).
- **Lot rounding (B6)** may destroy vol targeting → FUND requires capital or waits.
- **Funding:** 5–11%/yr for longs in normal markets (capital seat). If it turns a book negative → EXTEND.
- **Operational couplings:**
  - orphan adoption (bot.py:5297);
  - global 10x leverage in one-way mode;
  - the dashboard's dependence on the L2 writer;
  - the STATS line;
  - the `.halt_swarm_desk` blast radius;
  - `_slot_entries_blocked` gating trend up-sizes (bot.py:2905-2914);
  - launchd time-zone ambiguity.
- **Hurdle (B8).** If the rule doesn't beat stables or HLP after costs, hold stables.
- **The `.env` inline-comment concern (MAX_DRAWDOWN_PERCENT) is dropped.** The bot is running as PID 4305 under that `.env`, so it parsed (M5).

---

## (8) Seat disagreements: resolution status

1. **Fidelity: RESOLVED against the verdict seat.** Book against replica breached on six ETH days (donchian seat and critic confirmed). The verdict seat measured w against w_target. Handled in A2 by the letter of the spec, with no waiver.
2. **ETH replica gap $1.30: mostly RESOLVED.** $1.11 comes from the outage (reviser recompute); about $0.19 remains for B4.
3. **ETH lot value.** $24.97 (fee_math.py:12, stale 9/14), $26.87 (9/27 close), $26.76 (live ticker). Use the current price and refresh fee_math.py:12 (OWNER GO).
4. **BTC 15 rows vs 16 rows.** This is timing: PAPER_STATUS was written at 6:30 AM PT and the 16th row closed at 5:00 PM PT. Not a conflict.
5. **How to hold the desk.** Never `.halt_swarm_desk`; change the cadence or unload `desk-weekly`.
6. **Fidelity grader location.** Both: the adjudicator (Telegram) and PAPER_STATUS mirroring it.
7. **Live sizing basis.** Unresolved until the 10/14 E2 choice; drafted, not presented.
8. **Cost basis for daily-bar fills** (the 4.5 bps adverse-selection component of C_BPS 11.5). Measurable only with a live-sized fill.
9. **Retirement scope.** Every D item stays OWNER GO.
10. **Funding and fee-capture commits** (RESTART-SAFE 9/7, "awaiting owner go", MEM/project…:17). Whether they are live now is UNVERIFIED; check with `git log` against the running process's start time.

---

## Critic findings not adopted

- **I1, "accept that the 14-day window containing the breaches ends 9/23 anyway":** rejected. Letting the breach age out quietly is also a waiver. A2 instead pre-registers explicit clearance conditions: root cause fixed, a clean 9/30–10/13 window, and ex-outage grading. The critic's main point on I1 is adopted.
- **I2, "thresholds set after seeing 72/89 days":** adopted as disclosure plus removal of the R4 escape clause. It cannot be fully cured, because the data is already seen. The remedy is disclosure and making R7 (exposure-matched, DSR) the binding gate, since R7 does not depend on thresholds chosen this week.
- **I11, Phemex January 2025 hot-wallet incident:** kept only as UNVERIFIED. Nothing in the repo or memory confirms it, so the plan asserts no incident.

## Deferred minors

- **M6:** monthly desk token cost. It is addressed by gating monthly runs behind Phase 2 steps 1–3; no further action now.
- M1, M2, M3, M4 and M5 were fixed inline (A3/Phase 1 item 4; C4; E1; decision map "fix window = 30 days"; section 7).