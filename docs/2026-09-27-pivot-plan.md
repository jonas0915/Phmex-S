# Phmex-S Pivot Plan: Slow Trend Follower (FINAL, Sun 9/27/2026)

## Bottom line (for Jonas)

- You asked tonight for a pivot plan. It is to stop short-term trading for good and turn the bot into a slow, long-or-flat trend follower on BTC and ETH only (the Donchian book that has been on paper since 7/16).
- Nothing changes before the 10/14 review. There is no live build, no live offer and no restart. The live sections below are prepared only, so they are ready if you want them on 10/14.
- On paper both books are up: BTC +$6.51 and ETH +$6.83 after modelled fees. Take out the 9/9–9/20 shutdown days, when the paper books sat frozen at a stale size, and it is about +$5.84 and +$5.72.
- The honest caveat: over these 73 days, just holding the same average amount of BTC or ETH would have made more than the rule's own replica. It has only seen a bull run. The review can show the rule was run correctly, but it cannot yet prove the rule has an edge.
- The 10/14 test is the one we agreed on 9/21: both books positive and fidelity clean → I offer the ETH-only one-lot live build. The extra tests in this plan are shown to you as evidence. Adding any of them to that test needs your approval.
- ETH has already missed the fidelity rule by the letter, with six bad days, most of them caused by the shutdown. The fix is a written stop procedure, not a hardware change.
- Tonight, separately: the Mac was on battery (24%, down to 19%). It was plugged back into AC at about 6:12 PM PT (confirmed by pmset). Keep it on AC with the lid open. Nothing outside the Mac would warn you if it went down.

---

Path shorthand: P = `/Users/jonaspenaso/Desktop/Phmex-S/`, MEM = `/Users/jonaspenaso/.claude/projects/-Users-jonaspenaso-Desktop/memory/`. "MEM/donchian-live" means MEM/project_mr_paper_donchian_live_2026-09-08.md, and "spec" means P/docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md.

How numbers are labelled:
- A plain citation means the file it names.
- "Recompute" means the figure was re-run on 9/27 from `P/donchian_signal_{BTC,ETH}.json` (key `days`, 74 daily closes from 7/16 to 9/27) or `P/trading_state_DONCHIAN_*.json`.
- "Judgment" means a threshold with no source behind it. Every judgment threshold was set on 9/27, with 73 of the 89 daily steps in the review window (7/16 close to 10/13 close) already visible and 16 still to come. They are disclosed as such.
- **Fee basis.** The replica and the hold benchmarks are fee-free (`run_history` has no fee term). Every book-against-replica comparison below is made **before fees**, and fees are shown as their own line. The book's net figures are after the paper fee model, which is about 0.12% of notional per round trip (fees_usdt ÷ notional on the ledger rows).

The Mac clock is on EDT: `/etc/localtime` has pointed to America/New_York since 9/26 at 4:19 AM PT (7:19 AM EDT; the symlink's mtime, which is only a proxy for when the zone changed). Log timestamps before 9/26 are PT and later ones are EDT. Every time below is converted to PT.

---

## (0) Do this first: the host is on battery (uptime risk, separate from the outage)

- `pmset -g batt` read at about 5:55 PM PT: "Battery Power … 24%; discharging; 1:13 remaining". A verifier's later read showed 20% with 0:49 remaining.
- MEM/feedback_host_sleep_suspends_bot.md:17 calls AC power "non-negotiable for a position-holding bot."
- **Owner action, tonight:** plug in the Mac and keep the lid open. This is not a halt or a bot change.
- **No off-host downtime alert exists today.** The only watchers are launchd jobs on this same Mac (com.phmex.overwatch, halt-watcher and telegram-commander, per a verifier's `launchctl list`). If the Mac sleeps or dies, nothing fires. See B9.
- This battery risk did **not** cause the 9/9–9/20 outage. That outage was the owner-ordered wind-down (A2).

---

## (1) Verdict

1. **Direction.** Retire short-horizon trading and make the bot a slow, long-or-flat trend follower on BTC and ETH only. It runs the frozen 9-lookback Donchian ensemble, and every other book stays retired.
   - The 5m_mean_revert shorts-only paper test is already over. The bot's negative-Kelly kill switch disabled it at n=57 on 9/24 (P/research/swarm/kb/PAPER_STATUS.md:18). Its verdict record is still owed (A4).
   - Why: everything short-horizon is on the dead list, and so are the simpler time-series trend variants: DEAD_LIST rows 12 (basket TSM), 13 (BTC-TSM) and 14 (ETH-TSM-28). Cross-sectional momentum, a different family, is dead at row 5.
2. **What the evidence actually is.** Donchian is not a proven edge. It is the one candidate that has not been killed.
   - **Out-of-sample bear replay** (P/reports/2026-07-16-wake-report.md:62-63):
     - BTC −11.5% against buy-and-hold −44.0%.
     - ETH −4.9% against −48.0%.
     - It lost money outright, so it did worse than holding stables.
     - It was compared only with 100% buy-and-hold.
     - A static position at the paper-window average weight would have lost about 0.242 × 44.0% ≈ 10.6% on BTC and about 0.206 × 48.0% ≈ 9.9% on ETH (average w from the recompute; the rest is arithmetic). For BTC that cannot be told apart from simply holding less. ETH does look better.
     - This stays UNVERIFIED until the replay's own average weight is known. The replay scripts were recorded as kept only in a session scratchpad (MEM/reference_nobarriers_search_2026-07-16.md:22; spec:9 says "preserved (scratchpad donchian_ensemble.py)"). A verifier's filesystem search on 9/27 found no `donchian_ensemble*.py` anywhere, so they are effectively lost.
   - **Paper window, 7/16–9/27, before fees** (recompute; average w is BTC 0.242, ETH 0.206):

     | | Rule replica | Constant-weight hold at the same average w | Static buy at 7/16 at average w |
     |---|---|---|---|
     | BTC | $6.45 | $7.16 | $7.81 |
     | ETH | $5.53 | $8.19 | $9.12 |

     In the only live-data window, the timing added nothing over plain exposure. This is one bull window, so it does not show that timing never adds anything.
   - **It has never faced the bar that killed its relative.** BTC-TSM died on a deflated Sharpe of 0.635 against a 0.95 bar, and its Sharpe-difference CI against buy-and-hold included zero (MEM/reference_btc_tsm_kill_test_2026-07-15.md:10-26). No deflated Sharpe or Sharpe CI has been found for Donchian (repo and memory greps; absence cannot be fully proven).
   - **One test, one regime.** Donchian was ranked #1 from published research and then given a single out-of-sample test on our own data (wake-report:3-5 and 20-27; MEM/reference_nobarriers_search_2026-07-16.md:14, "only one, and it passed a real OOS test"). No other candidate was replayed on the bear. So the caveat is thin evidence (one test, one regime, the paper's parameters), not selection bias.
   - **The only long-sample figure is borrowed:** Concretum/SSRN Sharpe 1.56, 2015 to March 2025 (spec:5). That window includes 2021, which our memory calls "the 2021 parabola artifact" for higher-timeframe trend (MEM/reference_edge_hunt_exhaustion.md:19).
3. **At $87 this is not an income decision.**
   - BTC cannot trade. ETH is at most one lot, on or off (section 4).
   - At $87, a 25% APR is about $22 a year (arithmetic).
   - The 10/14 review can prove faithful execution. It cannot prove edge.
   - Reaching n=50 adjustments per coin takes about 37–40 weeks at the spec's ~65–70 a year (spec:47; research/swarm/lib/fee_math.py:32-35), or about 21–24 weeks at the pace actually observed (22 BTC and 25 ETH w-changes in 73 steps, recompute). Rebalances are not independent trades either, so n=50 is a weak unit for an edge verdict.
   - "Hold stables and keep Donchian on paper indefinitely" is therefore a real option for the owner at 10/14, alongside the agreed outcome (section 3).

---

## (2) Phase 0: now to 10/14/2026

Nothing here places an order, restarts the bot or touches `.env`. Every step that writes code, a research script into the repo, a branch, launchd, a sentinel or a KB file is marked **OWNER GO**. Any restart also needs `/pre-restart-audit`. Nothing in Phase 0 asks the owner to decide anything about live Donchian. Live-related work is drafted and held for 10/14.

### A. Fix the record (week of 9/28)

- **A1. DEFERRED to 10/14: KB ruling append.** At the 10/14 review, and only then, append a row recording the review's outcome. Until then DEAD_LIST row 33 (P/research/swarm/kb/DEAD_LIST.md:45) and STANDARDS #14 (P/research/swarm/kb/STANDARDS.md:16) stand as written. The 9/21 lift applies "for that date only; do not raise it before 10/14" (MEM/donchian-live:21). The desk reads kb/ on every run, so an early row could prompt Donchian-live or trend proposals.
- **A2. OWNER GO: log the ETH fidelity breach as a BUG, by the letter of the spec, with no waiver.**
  - Spec:45 says "daily |bot w − replica w| > 0.10 on >3 days in 14d → BUG, fix or kill."
  - The book breached the replica on six ETH days: 7/26, 7/27, 9/10, 9/15, 9/16 and 9/17 (recompute, book w sampled at 11:00 PM PT). BTC had none; its outage gaps were about 0.074–0.076, under the 0.10 line.
  - Four of those days (9/10 and 9/15–9/17) fall inside one 14-day window.
  - A check of `w` against `w_target` inside the signal file compares the replica with itself (max gap BTC 0.012, ETH 0.009). That is not the spec's test.
  - **Cause of the September days: the owner-ordered wind-down, not a host failure.** The bot was stopped with SIGTERM at 7:50 PM PT on 9/9 by owner order, and the Donchian paper positions were left open in the ledgers (MEM/project_phmex_winddown_2026-09-09.md:11-13 and :20; the last regular log line is 7:50:02 PM PT, P/logs/bot.log.4:89108-89128). The bot restarted at 8:47 PM PT on 9/20 (bot.log.4:89149). The stale size was held until the first Donchian rebalance at 9:04 PM PT; up-sizes were "deferred — account halt" from 8:49 PM (bot.log.4:89214-89215). The current process, PID 4305, has been running since 9:11 PM PT 9/20. All of this is in bot.log.4; bot.log.3 starts at 6:16 AM PT on 9/21.
  - **Cause of the 7/26–7/27 days: open and unexplained.** The ledger shows a one-day lag. The ETH book opened at w 0.1728 on 7/24, which was the replica's 7/23 value. It was not resized at the 7/26 eval, when the replica went to 0.2287, and then opened at 0.2287 on 7/27, when the replica was at 0.1135. Why it lagged needs logs that have rotated out, so it stays UNVERIFIED.
  - **Pre-registered reading of "fidelity clean" for ETH** (set now, before the last 16 closes; the owner confirms or changes this reading at 10/14). ETH counts as fidelity-clean only if all three hold:
    - (a) the stop procedure in A5 is written, so a deliberate stop cannot freeze the paper books again;
    - (b) no breach day falls in the 14 days before the cutoff (9/30–10/13);
    - (c) ETH's result is also reported **ex-outage** and **ex-outage and ex-July-lag** (the figures are in "Current state" below).
  - **Outage P&L, before fees:** ETH +$1.11 and BTC +$0.67. Each is (book w − replica w) × daily return × $100, summed over the 9/9–9/19 closes (recompute). 9/17 alone gives ETH +$0.69 and BTC +$0.44.
- **A3. OWNER GO: record that the kill lines are not actually graded.** The spec calls them "adjudicator-graded" (spec:44), but Donchian does not appear in P/scripts/lab_adjudicator/adjudicate.py (grep for "donch" returns nothing). Also record that the paper position objects carry `"paper": false`; the open ETH and BTC positions in P/trading_state_DONCHIAN_*.json both show it (default at risk_manager.py:447). Check this before any promotion.
- **A4. OWNER GO (owner decision): write the 5m_mean_revert verdict record.** Record it as a KILL / closed record: disabled by the negative-Kelly switch at n=57, net −$0.10, last close 9/24 (PAPER_STATUS.md:18).
- **A5. OWNER GO: deliberate-stop procedure** (this is the fix for A2's September cause). Whenever the bot is stopped on purpose, do one of two things. Either (1) record the Donchian paper books as flat at the stop time and re-enter at the policy weight on restart, or (2) mark the stopped days as excluded from fidelity and P&L grading. Add this to the restore steps in P/docs/2026-09-09-winddown.md.

### B. Build the measurement (research scripts only, no bot restart; each script is OWNER GO before it goes in the repo)

- **B1. OWNER GO: automated fidelity grader.**
  - Book w = open notional ÷ $100, from `trading_state_DONCHIAN_*.json`.
  - Replica w = `w` in `donchian_signal_*.json`.
  - Sampled at 11:00 PM PT, six hours after the 5:00 PM PT roll (judgment).
  - Output to three places: the adjudicator digest (Telegram), `swarm_desk --mode maint` → PAPER_STATUS.md, and the dashboard's Donchian card with the same fields (P/CLAUDE.md propagation rule).
- **B2. OWNER GO: review script, frozen before 10/14.**
  - Commit sha recorded before 10/14 (STANDARDS #3).
  - Replica = `donchian_slot.run_history(closes)` (P/donchian_slot.py:192) run on **at least 450–500 daily closes ending at the 10/13 close**. That is the same 500-bar bootstrap the live replica used (the first signal row reads "bootstrap over 500 bars"; spec:36 needs 360+90 = 450). Score only the 7/16–10/13 slice. On 90 closes alone, `_vol_scalar` returns None and w stays at 0 (donchian_slot.py:108-113, 132-176).
  - Check that the rebuilt series matches the stored `donchian_signal_*.json` (stops and w are path-dependent).
  - P&L measured two ways: closed-book, and mark-to-market at the 10/13 5:00 PM PT close. Both before and after fees.
  - The script also computes every R-rule in section 3.
- **B3. OWNER GO: funding.**
  - Pull Phemex public funding history for BTC and ETH from 7/16 to 10/13. At each 8-hour settlement charge **notional × rate** (that is, w × $100 × rate; notional is already base × w, per spec:24).
  - 7/16 to 8/10, from the cache: BTC 0.343% and ETH 0.119% of notional, about 4.9% and 1.7% a year (`load_reference_funding`, 77 settlements; reproduced by a verifier).
  - 8/26 to 9/28, from a public ccxt read on 9/27: BTC 0.413% per 30 days (5.02% a year), ETH 0.349% per 30 days (4.24% a year), 100 settlements each.
  - 8/10 to 8/26 still needs paging and is UNVERIFIED.
  - `funding_usdt` is 0.0 on all 36 paper rows. That is expected: paper has no exchange funding fills.
- **B4. OWNER GO: replica-gap reconciliation, on one fee basis.** Book gross = closed-row P&L before fees plus the open position marked at the 9/27 close. All figures are recompute.

  | Component (before fees unless stated) | ETH | BTC |
  |---|---|---|
  | Replica (fee-free) | $5.534 | $6.452 |
  | Book gross | $7.358 | $7.030 |
  | **Gross gap** | **+$1.824** | **+$0.578** |
  | Weight deviation, 9/9–9/19 outage | +$1.110 | +$0.668 |
  | Weight deviation, 7/26–7/27 one-day lag (**open, unexplained; not an allowed adjustment**) | +$0.540 (7/26 +0.362, 7/27 +0.178) | — |
  | Weight deviation, all other days | +$0.021 | −$0.302 (7/20 −0.175, 7/23 −0.118) |
  | Fill price against the eval-day close | +$0.285 | +$0.178 |
  | Remainder: the book holds a fixed coin amount while the replica holds a constant daily notional, plus sampling (unattributed) | −$0.133 | +$0.034 |
  | Fees (paper model) | −$0.485 | −$0.536 |
  | **Net book minus replica** | **+$1.299** (6.833 − 5.534) | **+$0.053** (6.505 − 6.452) |

  - BTC's close net match is fees cancelling the outage and fill gains. It is not a clean match.
  - Pre-listed adjustments are the only ones allowed: fees, fill price against close, outage excess weight (or A5-excluded days), and the open-position mark. The July lag is not one of them, so it counts against R4 unless its cause is found and fixed.
- **B5. OWNER GO: stop-deviation replay.**
  - Measure what a resting disaster stop does to replay return and drawdown, at (i) a fixed −8% and (ii) the lowest active sub-model stop.
  - Test each under two post-stop policies:
    - (a) re-enter to the policy weight at the next daily eval;
    - (b) stay flat until a sub-model flips.
  - This answers the whipsaw question, which has never been measured.
- **B6. OWNER GO: lot-rounding replay.** Floor rounding against round-to-nearest, at $87, $260, $500 and $1,000. It answers whether a one-lot ETH book still behaves like the ensemble.
- **B7. OWNER GO: independent re-derivation, feasibility first.**
  - **Step 1:** confirm whether about 815 daily bars are obtainable (about 450 warmup plus about 365 test, arithmetic). DATA.md:14 says ccxt reaches "~2 years" (about 730 bars), and it is gated by the committee token. The original used "spliced+verified" data (wake-report:60), and no source for that data was found.
  - **If the bars are not obtainable:** record "B7 not possible". The out-of-sample result stays single-derivation, and that is reported to the owner.
  - **If they are**, rebuild with `run_history` and report:
    - (i) return and max drawdown against buy-and-hold;
    - (ii) the replay's own average w;
    - (iii) an **exposure-matched static-hold benchmark** at that average w;
    - (iv) a deflated Sharpe and a Sharpe-difference bootstrap CI against the exposure-matched benchmark, on the same bar that killed BTC-TSM (DSR ≥ 0.95; resample each side independently, then sort the differences, per MEM/feedback_bootstrap_diff_ci.md).
  - This re-checks a single out-of-sample test. It is a benchmark check, not a new regime.
- **B8. Hurdle comparison.** Compare replay and paper returns, net of funding, with the audited HLP 10–25% APR (MEM/reference_nobarriers_search_2026-07-16.md:59) and with holding stables.
- **B9. Uptime record and off-host alert.**
  - List every period the bot was down since 7/16 from the logs that still exist, and tag each ledger day as up, down, or deliberate stop (A5).
  - Owner decision (not presumed): AC-only operation, or **migrate the single bot instance** to an always-on host. Only one instance may ever run: stop the Mac copy first (P/CLAUDE.md, "Never start a second instance on another machine"). MEM/project_mac_upgrade.md already plans an MBP migration.
  - Owner decision: add an **off-host dead-man check**, for example a cloud routine that alerts when the daily digest is missing. None exists today.

### C. Reporting gaps (code, OWNER GO; scripts only, no bot restart)

- **C1.** `scripts/daily_report.py:174 paper_slot_summaries` leaves Donchian out. Add a Donchian Telegram section showing:
  - w, and how many sub-models are long;
  - net, both as booked and ex-outage (both coins);
  - funding-adjusted net;
  - fidelity state and the breach count and history (B1);
  - the replica and exposure-matched benchmark P&L, before fees.
- **C2.** Register DONCHIAN_BTC and DONCHIAN_ETH in `adjudicate.py` EXPERIMENTS, with the −$15 line and the fidelity line.
- **C3.** Dashboard `web_dashboard.py:838-850`: add the same fields as C1, so Telegram and the dashboard agree.
- **C4.** Fix the stale label at `web_dashboard.py:851`, "5M_MEAN_REVERT — LIVE FORWARD TEST". The book has been paper since 9/8 and kill-switched since 9/24 (honest-data rule).

### D. Retire or freeze the scalper machinery (every item OWNER GO, reversible, nothing deleted)

The standing rule is never pause or halt unasked (MEM/feedback_never_pause_bot_unasked.md).

- **D1. Unload dead-book launchd jobs:** `l2-recorder`, `st2-lab`, `nightly-research`, `mr-watch`, `mr-gate-archiver`, `flow-sanity`, `weekly-sweep` and `auto-lifecycle`. `auto-lifecycle` is inert (its log shows "0 actions") but can write `.promote_`, `.kill_` and `.restart_bot` (auto_lifecycle.py:7). The plist files stay on disk.
- **D2. Desk: move `desk-weekly` to monthly, or unload it.**
  - This changes the owner's 9/16 requirement that the desk "maintain/improve the bot constantly (recurring cadence + maintenance loop)" (MEM/project_edge_swarm_v2_desk_2026-09-16.md:18). It needs his explicit go.
  - Never use `scripts/.halt_swarm_desk`: it stops every mode, including `--mode maint`, and with it PAPER_STATUS (swarm_desk.py:8 and :1136).
  - **Next run time.** The plist fires at Hour=3 local (`~/Library/LaunchAgents/com.phmex.desk-weekly.plist`, Weekday at line 29, Hour at line 31). The 9/27 run, the first since the zone change, fired at 3:00 AM PT (run id `2026-09-27-0300`, built in PT at swarm_desk.py:83/884; desk-weekly.out.log). So the registration is still on PT. The 10/4 run is expected at 3:00 AM PT unless the Mac reboots or the job is re-bootstrapped (MEM/reference_launchd_stale_timezone.md).
  - Check `launchctl print` for the other PT-labelled jobs (daily-report, desk-maint, lab-adjudicator, code-health). Fix with bootout and bootstrap once the owner decides which zone the Mac stays on.
- **D3. Main scalper.** It is already paper via `.paper_main`, dated 8/26. The owner may choose `.halt_main_entries` or a new Config early-return. There is no urgency.
- **D4. Scanner, WebSocket feed and L2 writer.** Retire them only after the dashboard's price source moves off `l2_snapshot.json` (web_dashboard.py:486-497 reads it; bot.py:446 and :2937 write it). Keep the STATS line on every path (it is parsed at daily_report.py:234 and web_dashboard.py:1596). The scanner and `TRADING_PAIRS` are `.env` changes, so the owner makes them.
- **D5. Keep every `trading_state_*` ledger.** Lifetime P&L is their sum.

### E. Prepare the live build: drafts only, held for 10/14

> **PREPARED ONLY — not offered; no live decision, OWNER GO or build before the 10/14 review.**

- **E1. Draft Donchian spec v2 on a branch, unmerged** (creating the branch is OWNER GO). It must cover:
  - a live open, close and resize that trades only the difference;
  - a lot-rounding policy;
  - a 1x isolated pin per symbol;
  - a resting reduce-only disaster stop, registered as a deviation from spec:56 ("no intraday stops") and sized from B5;
  - a written post-stop policy, (a) or (b) from B5;
  - the stop trigger price type. `exchange.place_stop_loss` sets no `triggerType` (exchange.py:1126-1156), so it uses the venue default, which is UNVERIFIED as mark or last;
  - the take-profit question (below);
  - a Donchian ownership lock;
  - funding recording;
  - the halt policy for trend books, as its own owner decision (section 4, item 6);
  - a live fidelity line on lots;
  - a `VOL_CAP` of 2.0 against the 1x pin (at w = 2 the notional is twice the base; the observed max vol_scalar is 0.748 BTC and 0.522 ETH, capital seat).
- **E1, take-profit: an EXCEPTION REQUEST to an owner directive. The default is compliance.**
  - The directive, quoted: "take-profit (and stop where the venue allows) must be placed as resting orders at the broker/exchange the moment a fill is recorded … if the venue can't rest both (Robinhood options: no OCO), rest the one the data says matters … and say so explicitly" (MEM/feedback_broker_side_exits_first.md:8, :12).
  - Phemex can rest both (exchange.py:867 `place_sl_tp`), so the venue clause does not apply.
  - The case for an exception: on a trend follower a fixed TP caps the right tail, which is where the rule's value sits (wake-report:69, "its EV lives in trending legs").
  - Unless the owner signs the exception **in writing** before spec v2 is frozen, spec v2 rests a TP as well, for example a far TP at a registered level.
- **E2. Draft (not presented before 10/14) the sizing options.**
  - All $87.12 into ETH at today's w of 0.2992 gives a $26.07 target against a $26.87 lot (9/27 5:00 PM PT close), so **0 lots** under floor rounding.
  - The 9/8 proposal default base of $75 × w 0.2992 = $22.44, also 0 lots.
  - Options:
    - (a) round-to-nearest, a registered deviation. One lot is then about 30.8% of the account, and the position goes flat below w ≈ 0.154. Live ETH is effectively an on/off switch, and a lot-fidelity line mostly measures its own rounding.
    - (b) add capital.
    - (c) no live build.

### What the paper test can and cannot show by 10/14

- **It can show:**
  - the rule was run faithfully (subject to A2);
  - book-to-replica gaps are explained only by the pre-listed adjustments (B4);
  - whether both books are positive as booked, ex-outage, and after funding.
- **It cannot show edge.** The −$15 kill line also cannot realistically trip at these weights. With no exits, it would need about a 31% BTC fall at BTC's max w of 0.4915 (about 44% from the current +$6.51), or about a 43% ETH fall at ETH's max w of 0.353 (recompute and arithmetic). The replica's worst mark-to-market drawdown so far is −$2.66 BTC and −$1.94 ETH (recompute). So "risk stayed inside the kill lines" is guaranteed, not tested. The line is a catastrophe guard, not evidence.
- **Current state** (ledgers read 9/27; fees are the paper model):
  - BTC: 16 rows, +$6.51 net (+$7.04 before fees), about +$5.84 ex-outage (6.505 − 0.668).
  - ETH: 20 rows, +$6.83 net (+$7.32 before fees), about +$5.72 ex-outage (6.833 − 1.110), and about +$5.18 when the 7/26–7/27 lag is also removed (6.833 − 1.671, all ETH weight deviation).
  - The top 3 trades in each coin make more than the total.
  - Exits: 33 rebalances and 3 stops (BTC 2, ETH 1).
  - No test leg yet: the worst daily-close drawdown is −6.9% BTC and −5.6% ETH (verdict seat).

---

## (3) The 10/14 review: rules (set 9/27 with 73 of 89 steps visible; disclosed)

Data cutoff: the 10/13 UTC close, which is 5:00 PM PT on 10/13. The script and its sha are frozen before 10/14 (R0). The spec's own review items are tracking error, trade count against the replay's cadence, and net against the pure-rule replica (spec:47). R2–R4 put numbers on those, and those numbers are judgment.

- **R0. Freeze the measurement.** P&L is reported closed-book and mark-to-market, before and after fees. Both coins are reported as booked and ex-outage, and ETH also ex-July-lag.
- **R1. Kill lines (spec, applied first).**
  - Net ≤ −$15 on the $100 base (spec:46) → RETIRE. This is a catastrophe guard.
  - Fidelity per spec:45, book against replica → BUG, fix or kill. ETH follows A2's pre-registered reading.
- **R2. Adjustment count against the replica's own cadence.**
  - The spec's "~65-70 adj/yr" (spec:47) does not say whether it is per coin, and this window runs faster: the replica changed w 22 times on BTC and 25 times on ETH in 73 steps (recompute), about 110 and 125 a year (arithmetic).
  - Compare book adjustments (closed rows plus the open position) with replica w-changes over the same up-days, excluding B9 downtime and A5-excluded days.
  - Pass: within ±30% (judgment).
- **R3. Drawdown against the replica.** Amber if the book's mark-to-market drawdown is worse than the replica's on the same days by more than $1.00 (judgment) → EXTEND.
- **R4. Replica tracking.** Mark-to-market net within ±$1.00 of the replica **after only the B4 pre-listed adjustments** (judgment). A gap left after those adjustments fails. On today's numbers ETH carries an unexplained +$0.54 from the July lag.
- **R5. Funding.** Each book is reported after B3 funding, as booked and ex-outage.
- **R6. Test leg, recorded as information and not as a kill.**
  - A test leg is an underlying peak-to-trough fall of at least 15% on daily closes, or 30 or more days inside a ±5% band (judgment).
  - If one occurs, the book is judged against the **replica on the same path** (R3/R4 tolerances), not against a buy-and-hold ratio. A correctly working rule should not be retired for behaving like the rule.
  - For context: today the 250- and 360-day sub-models are flat on both coins, so they hold no stop. BTC's 150-day stop sits 14.0% below the 9/27 close and ETH's sits 19.2% below (P/donchian_slot_state.json). A 15% leg would cost at most w × 15%, which is $7.37 BTC and $4.49 ETH at today's w. The faster sub-models' stops would cut that earlier.
  - If no leg occurs, the next checkpoint is the end of the first test leg or 1/13/2027, whichever comes first (judgment).
- **R7. Evidence for the owner (not a gate unless he approves the proposed change below).**
  - (a) The paper replica against the constant-weight exposure-matched hold on the same window, before fees. **What it shows today:** the rule made less than just holding the same average amount. BTC $6.45 against $7.16 (−$0.71), ETH $5.53 against $8.19 (−$2.66). In this bull-only window the timing added nothing.
  - (b) The B7 result against the exposure-matched static benchmark, with DSR ≥ 0.95, the bar that killed BTC-TSM. It may not be possible (B7 step 1).
  - (c) The B8 hurdle: stables and HLP.

**How outcomes map to decisions**

- **The agreed FUND gate** (MEM/donchian-live:21, owner-agreed 9/21): "If both books positive + fidelity clean → offer ETH-only one-lot live BUILD." This plan does not change that gate.
- **PROPOSED change to the agreed criteria (needs owner approval, or it stays evidence only):** also require (i) both books positive after B3 funding and ex-outage (R5), (ii) R7(b) passing, or recorded as impossible and knowingly waived by the owner, and (iii) R4 passing. Reason: the agreed gate checks execution. Today R7(a) shows no timing advantage, and the only out-of-sample evidence is one test. Against that, the standing rule is that the forward test is the adjudicator (STANDARDS.md:12, #10). That is why this stays a proposal.
- **RETIRE the book:** an R1 loss kill; an R1 fidelity BUG that is not fixed ("fix or kill", spec:45); or R4 still failing after a 30-day fix window from 10/14 (judgment, proposed).
- **EXTEND PAPER to the next checkpoint:** fidelity not clean at 10/14; a book between −$15 and $0; R2 outside ±30%; R3 amber; R4 open inside the fix window; or no test leg and the owner prefers to wait.
- **HOLD STABLES / PAPER INDEFINITELY:** the owner's option at any outcome, for example if R7 and B8 show no advantage over holding less, or he declines to add capital.
- **FUND.** **PREPARED ONLY — not offered; no live decision, OWNER GO or build before the 10/14 review.** If the agreed gate is met at 10/14 (plus any extra conditions the owner approves), offer the ETH-only one-lot live build and he picks E2 (a), (b) or (c). Without a test leg this checks execution, not edge. BTC stays paper. OWNER GO is required before any build starts. Today both books are positive. Whether ETH is fidelity-clean depends on the 9/30–10/13 window and on the owner accepting A2's reading.

---

## (4) Phase 1: if funded (not before a 10/14 GO)

> **PREPARED ONLY — not offered; no live decision, OWNER GO or build before the 10/14 review.**

### Build scope (about 250–300 lines, per MEM/donchian-live:14)

1. **Order path.** Replace the stub at `bot.py:4940-4949`, which returns "LIVE mode unsupported — book untouched".
   - Live open, close and resize that trades only the difference, with reduceOnly partial closes.
   - Template: `_tsm_try_entry` at bot.py:4659, with taker fallback through `exchange.py:1158 open_long_market`.
2. **Resting broker-side exits from day one.**
   - Place with `exchange.py:1126 place_stop_loss`, and move with `:933 move_stop_loss` after each daily eval and resize.
   - The TSM heal (bot.py:4516-4527) only re-places a stop when `sl_order_id` is None or "software", so it misses a stop cancelled on the exchange. Adding a `:1009 verify_sl_order` check every cycle (the main-book pattern at bot.py:1973) is new work.
   - The level, the trigger type and the post-stop policy come from spec v2 and B5. The TP follows E1: a resting TP unless the owner has signed the exception.
3. **Leverage pin.** 1x isolated per symbol via `exchange.py:1113 set_symbol_leverage`. Save the flag before the flip, as at bot.py:4735-4744; bot.py:4464 `_tsm_restore_leverage` is the restore path. The exchange was 10x isolated on BTC and ETH as of the 9/14 probe (docs/2026-09-16-edge-swarm-v1/03_exchange_economics.md:10). Nobody re-read it on 9/27.
4. **Ownership.** A Donchian lock like `bot.py:4431 _tsm_locks_symbol`, plus a pre-entry position check. Save ownership before the first reconcile, so `_adopt_orphan_position` (bot.py:5297) cannot bracket the position. Switch Donchian positions from the `"paper": false` default to explicit tagging (A3).
5. **Evaluation order.** Run the Donchian eval and the stop-health check **ahead** of the early returns: ban mode at :1653/:1677 and warmup at :1734-1747.
6. **Trend-book halts: a separate OWNER GO line, not part of the general build go.**
   - `_slot_entries_blocked` (bot.py:2905-2914) blocks on `.pause_trading`, `.max_dd_halt` or the main book's `_drawdown_pause_until`. It is called for Donchian at bot.py:4958-4962, and it produced 22 "up-size deferred — account halt" messages on 9/20.
   - The daily-loss halt is at :1428.
   - Default: `.max_dd_halt` and the manual `.pause_trading` keep blocking Donchian up-sizes unless the owner explicitly rules otherwise. Any trend-specific drawdown rule is written into spec v2 as a number and signed off on its own. These halts were deliberate safety fixes (7/23 safety bundle; F1–F6 bundle).
7. **Funding.** Record it per settlement.
8. **Telegram.** Custom live entry and exit messages like TSM's (entry message at bot.py:4812, stop-failure alert at :4800). Confirm that `daily_report.py:98 live_slot_summaries` picks up the slot. It globs `trading_state_*_mode.json`, and no Donchian mode sidecar exists yet, so this is untested.
9. **Dashboard.** A live card with lots, stop level, leverage, funding and fidelity, replacing the hard-coded "(PAPER)" at web_dashboard.py:838-850.
10. **Tests, audit, go.** Update `tests/test_donchian_slot.py`, which pins the stub at line 553 (`assert "LIVE mode unsupported" in note`), then run `/pre-restart-audit`, then get the owner's go.

### Capital

> **PREPARED ONLY — not offered; no live decision, OWNER GO or build before the 10/14 review.**

Capital seat figures, per coin, at today's w. Lots are priced at the 9/27 5:00 PM PT closes: BTC 0.001 = $84.41, ETH 0.01 = $26.87. Live ticker prices a little later reproduce the same thresholds within about $2.

| Threshold | ETH | BTC |
|---|---|---|
| One lot at today's weight | about $90 | about $172 |
| One lot when fully long | $60 | $134 |
| Five lots | $449 | $859 |
| Full sub-model fidelity | $538 | $1,202 |

- Balance: $87.12. The STATS line (a live `fetch_balance`) printed it repeatedly on 9/27 between 5:05 and 5:57 PM PT (P/logs/bot.log). It matches docs/2026-09-16-edge-swarm-v1/03_exchange_economics.md:7.
- **Funding on a 30-day long, measured:** BTC 0.413% and ETH 0.349% of notional over 8/26–9/28 (public history, 9/27 read). That is about 5–6 times the capital seat's 0.07% round-trip fee (the paper books model about 0.12%). ETH was only 0.119% over 25 days in 7/16–8/10. Single 8-hour readings run higher (ETH was at the 0.0001 clamp on 9/27, which works out to 0.90% per 30 days), but that is a spot rate, not a norm.

### Counterparty and venue

- All capital sits on one exchange. Before any added capital, the owner sets a maximum balance to keep on Phemex and a withdrawal plan (owner decision).
- **UNVERIFIED:** Phemex's security incident history, including a reported January 2025 hot-wallet incident. Nothing in the repo or memory mentions it.
- **UNVERIFIED:** whether the owner's jurisdiction is allowed under Phemex's terms. Check Phemex's restricted-jurisdiction list. Other venues were already rejected as prohibited or geoblocked (MEM/reference_nobarriers_search_2026-07-16.md:44).

### First-30-day kill lines (pre-register before go-live; judgment items need owner sign-off)

- **Disaster stops:** 2 resting-stop fills → demote to paper. Precedent: the ETH-TSM kill criteria "2 disaster stops" (wake-report:138).
  - The −$11 era loss cap is not set today. The Donchian slots run `loss_cap_usdt=-999.0` (bot.py:815, :830), and −$11 was only an unconfirmed proposal default (MEM/donchian-live:16).
  - If it is set as a backstop, on one ETH lot it needs about six −8% stops at about $2.17 each before it trips (five come to $10.85; strategy_slot.py:200 trips at pnl ≤ cap).
- **Unprotected position:** open with no verified resting stop for more than 1 cycle → Telegram CRITICAL; a second occurrence → demote (judgment).
- **Lot fidelity:** held lots ≠ policy lots on more than 3 of 14 days → demote. If spec v2 picks post-stop policy (b), days after a disaster-stop fill are excluded (judgment).
- **Scalper interference:** any scalper bracket or orphan adoption on the symbol → demote immediately (judgment).
- **Leverage:** exchange leverage ≠ 1x while a position is open → alert; demote if it does not heal (judgment).
- **Uptime:** this needs the off-host watcher from B9, because nothing on the Mac can alert while the Mac is down. Proposed go-live preconditions: AC power, or the migrated always-on host, plus the off-host check. Then more than 24 hours of downtime with a live position open → Telegram CRITICAL (judgment; the resting stop is the protection meanwhile).
- BTC stays paper under the −$15 line.

---

## (5) Phase 2: second-sleeve research through a redirected desk

The desk cannot screen slow ideas today (verdict seat):
- The schema accepts only `mr_edge` and `long_1h`, at 5m and 1h (desk.js:200-201).
- `long_1h` covers 2025-06-27 to 2026-08-01 (DATA.md:9-10), which is too short for the 450-bar warmup.
- screen.py:93-94 has no signal exits and no funding charge.
- The viability bar demands at least 1.92 trades a week (CONSTRAINTS.md:20-24, fee_math.py:32).
- Each run costs about 2.5M tokens (README.md:163).

**Order of work (each step OWNER GO; nothing runs monthly until steps 1–3 land):**
1. A multi-year daily dataset with its own holdout. A source reaching past about 2 years is UNVERIFIED. This is the same blocker as B7.
2. A signal-exit mode and a per-settlement funding charge in screen.py, with tests.
3. Rewrite the viability rules at CONSTRAINTS.md:4 and :20-24 for 1x vol-targeted sleeves, using a daily-return bootstrap.
4. Mandate changes. These change the owner's 9/16 desk design, so they need his explicit go, and the owner-record lens stays unless he drops it (MEM/project_edge_swarm_v2_desk_2026-09-16.md:12, :18):
   - desk.js:65: median hold of at least 3 days, plus a required `corr_to_donchian` (judgment).
   - desk.js:106: the gatekeeper rejects short horizons and |ρ| > 0.5 (judgment).
   - desk.js:64 and :74: signal exit, or targets of at least 1000 bps.
   - Drop the intraday lenses.
   - `max_analysts` 8 → 4 and `max_screens` 5 → 2 (judgment).
5. Cadence: monthly (Day=1) in both plist copies, then bootout and bootstrap. Resolve the time zone first (D2).

**Scope rule:** a second sleeve needs a non-trend mechanism. The gatekeeper must reject relabels of rows 5, 12, 13, 14 and 33 (trend and momentum), row 76 (multi-day mean reversion and vol-scaling-as-rescue), and rows 4, 11, 20 and 34 (carry and funding).

**Removed from Phase 2:**
- Row 34, the linear-vs-inverse funding spread, is "REAL — PARKED until ~$2K" (DEAD_LIST.md:46). It stays a capital-triggered parked item, not a candidate at $87.
- Inverse BTCUSD for sub-lot BTC was "not proposed" (MEM/donchian-live:15). It is also coin-margined, so BTC collateral plus a long gives roughly double BTC exposure, which is unmodelled. It is dropped from the plan.

---

## (6) What we will NOT do

Everything on DEAD_LIST, and every demoted or owner-declined item, stays closed (kb/DEAD_LIST.md, STANDARDS #14). The rows that matter most for this pivot:

- **Short-horizon and scalper books, including re-arming a demoted one:** the main scalper (row 26), the main router strategies including momentum_continuation (row 28), ST2.0 (MEM/project_st2_status.md), SR_BOUNCE, 5m_MR and cascade_v2.
- **Short-horizon breakout variants:** rows 77, 78, 82 and 84.
- **Relabelled trend variants:** the 12-coin basket TSM (row 12), BTC-TSM(28,5) (row 13), ETH-TSM-28 (row 14), cross-sectional momentum (row 5), shorts, coins beyond BTC and ETH, and tuning the frozen parameters (spec:14-24, 56).
- **VWAP + SMA cross:** rows 23 and 32.
- **Carry and funding as a hunt:** rows 4, 11 and 20, the funding/cross-sectional/OI hunt, row 34 at $87, and the inverse BTCUSD route.
- **Closed, do-not-re-propose items:** small caps (research NO-GO, row 24), the BTC blacklist (owner-rejected), Tailscale (removed) and faster order-book polling (owner declined, row 72).
- **Discretionary trading.** Excluding the one TRYB event, the 2022 record lost −$3,270.79 over 786 trades, CI95 about [−5.92, −2.5] per trade (MEM/reference_owner_manual_run_2022.md:16).
- **Live Donchian before 10/14:** nothing raised, presented or merged (MEM/donchian-live:21). The live sections of this plan are prepared only.

---

## (7) Risks, and what would change the plan

- **Exposure, not timing.** In the paper window the replica trails the constant-weight hold by $0.71 on BTC and $2.66 on ETH, both before fees (section 1 table). **Would change:** if R7 and B7 show no advantage over the exposure-matched hold, the owner may prefer HOLD STABLES / PAPER INDEFINITELY. A timed rule has no clear case to run live over a smaller static position.
- **Double standard.** Until Donchian passes the DSR bar that killed BTC-TSM, it is described as "not yet killed", never as "survivor".
- **Deliberate stops freeze paper books.** The 9/9–9/20 wind-down left the Donchian paper positions open. That produced ETH's September breaches and +$1.11 ETH / +$0.67 BTC of P&L before fees. **Fix:** the A5 procedure. **Would change:** another stop without A5 during paper → the fidelity clock resets under A2.
- **Single host, separate risk.** The Mac is on battery, the time zone moved with travel, and no off-host alert exists. During live, the resting stop protects the position, but nothing would warn anyone until B9's off-host check exists.
- **Unexplained July lag.** ETH lagged the replica by one day on 7/26–7/27 (+$0.54 before fees), cause unknown. If it recurs, that is a live-code bug, not noise.
- **Two rallies make all the profit.** 8/17–8/21 gave BTC +$5.41 and ETH +$5.19. The rows closed 9/20–9/21, which span 9/7–9/21, gave BTC +$3.11 and ETH +$2.38; ETH's row includes the +$1.11 outage effect (about +$1.27 without it). Bear behaviour is untested on paper.
- **Stop deviation (B5)** may worsen the rule. If so, use a wider stop or the sub-model midline. The stop is never dropped (owner directive).
- **Lot rounding (B6)** may destroy vol targeting → FUND needs capital or waits.
- **Funding:** measured at about 4–5% a year for longs over 8/26–9/28 (BTC 5.02%, ETH 4.24%), and 1.7% for ETH in 7/16–8/10. Spot rates run higher. If funding turns a book negative, that is reported to the owner (R5).
- **Operational couplings:**
  - orphan adoption (bot.py:5297);
  - global 10x leverage in one-way mode;
  - the dashboard's dependence on the L2 writer;
  - the STATS line;
  - the `.halt_swarm_desk` blast radius;
  - `_slot_entries_blocked` gating trend up-sizes (bot.py:2905-2914);
  - launchd time zone (D2).
- **Hurdle (B8).** If the rule doesn't beat stables or HLP after costs, holding stables is the owner's natural choice.
- **The `.env` inline-comment concern (MAX_DRAWDOWN_PERCENT) is dropped.** The bot is running as PID 4305 under that `.env` (its mtime is before the 9/20 start, and config.py:26 applies float() at import), so it parsed.

---

## (8) Seat disagreements: resolution status

1. **Fidelity: RESOLVED against the verdict seat.** The book breached the replica on six ETH days (recompute). The verdict seat compared w with w_target. Handled in A2 by the letter of the spec, with no waiver.
2. **ETH replica gap: PARTLY RESOLVED.** On one fee basis the book is +$1.82 ahead of the replica before fees. The outage explains $1.11, fills +$0.29, other days +$0.02, and the unattributed remainder is −$0.13. The **7/26–7/27 lag (+$0.54) is open and unexplained.** Net of −$0.49 fees, the gap is $1.30 (B4 table). BTC: +$0.58 gross, with the outage +$0.67 and fees −$0.54 offsetting.
3. **ETH lot value.** $24.97 (P/research/swarm/lib/fee_math.py:12, stale since the 9/14 probe), $26.87 (9/27 close), about $26.76 (live ticker, point in time). Use the current price and refresh fee_math.py:12 (OWNER GO).
4. **BTC 15 rows vs 16 rows.** This is timing: PAPER_STATUS was written at 6:30 AM PT and the 16th row closed at 5:00 PM PT. Not a conflict.
5. **How to hold the desk.** Never `.halt_swarm_desk`; change the cadence or unload `desk-weekly`, with owner go (D2).
6. **Fidelity grader location.** All three: the adjudicator (Telegram), PAPER_STATUS, and the dashboard.
7. **Live sizing basis.** Unresolved until the 10/14 E2 choice; drafted, not presented.
8. **Cost basis for daily-bar fills** (the 4.5 bps adverse-selection part of C_BPS 11.5, fee_math.py:7-9). Measurable only with a live-sized fill (judgment).
9. **Retirement scope.** Every D item stays OWNER GO.
10. **Funding and fee-capture commits: RESOLVED, live.** All six commits (36dceb8, 8d5db08, 6f2e211, 48a243d, c1faefe, 5279b8a; 9/7 evening PT) are on `main`, which is checked out. The running process, PID 4305, started at 9:11 PM PT on 9/20, after them.

---

## Appendix: Verification log (9/27)

Nine adversarial verifiers checked **334 claims** in the draft and verified **273**. They raised 68 findings. The editor re-derived the changed numbers from the ledgers, signal files, logs, git and one public funding read.

**Applied**
- Row 66 is the 1h EMA gate, not a breakout → breakout rows are now 77, 78, 82 and 84.
- Frozen-parameter cite spec:10-12 → spec:14-24, 56.
- Main scalper is row 26 (row 28 is the router cull).
- Small caps, Tailscale and the BTC blacklist relabelled as closed items (only row 72 and the BTC blacklist are owner declines).
- "MEM/project…" expanded to MEM/project_mr_paper_donchian_live_2026-09-08.md (the "MEM/donchian-live" shorthand).
- R7 and FUND ambiguity resolved by owner ruling R-c (agreed gate, and R7 as evidence plus a proposed change).
- The 15%-leg claim corrected: the 250- and 360-day models are flat; the 150-day stops are −14.0% BTC and −19.2% ETH.
- Days visible 72/89 → 73 of 89 steps, 16 remaining (three verifiers).
- Funding range relabelled and replaced with measured trailing rates (two verifiers; 9/27 public read reproduced BTC 0.413% and ETH 0.349% per 30 days).
- Flag-saved-first cite → bot.py:4735-4744; bot.py:4464 is the restore path.
- −$11 cap: six stops, not five; the cap is −999 today (bot.py:815, :830).
- The TSM heal does not call verify_sl_order; adding it is new work.
- The TSM Telegram cite → bot.py:4812.
- The stub range → bot.py:4940-4949 (two verifiers).
- "10x today" → as of the 9/14 probe.
- Removed the "chosen from a multi-candidate search" selection claim and B7's "the bear was the selection test" (two verifiers).
- "Scripts were lost" citation corrected.
- Wake-report cite → :62-63.
- 7:19 AM → 4:19 AM PT (7:19 AM EDT).
- Row 5 separated from the time-series trend rows.
- n=50 given at both the spec cadence and the observed cadence (two verifiers).
- desk-weekly: the 9/27 run fired at 3:00 AM PT, so the stale PT registration is confirmed and 10/4 is expected at 3:00 AM PT.
- Broker-side exits directive quoted accurately; no-TP is an explicit exception request (ruling R-d; two verifiers).
- The kill line now also covers BTC (about 31% fall).
- 30.9% → 30.8%.
- Replica-gap fee-basis mismatch fixed; the ETH gap is shown as components, and the July lag is marked open (ruling R-f; three verifiers). The files agreed with v8's split (fill +$0.285, remainder −$0.133) and with v7's combined +$0.15.
- The B2 replica must run on ≥450–500 closes.
- The funding formula double-counted w → notional × rate.
- Outage times and log cite corrected. The files show the stop at 7:50 PM PT 9/9 (SIGTERM; the last regular log line is 7:50:02 PM), not the 8:42 PM a verifier inferred from a stray "Markets loaded" line. Restart at 8:47 PM PT 9/20; bot.log.4 only.
- Live-Donchian sections labelled PREPARED ONLY (ruling R-a).
- A1 deferred to 10/14; row 33 and #14 not called stale (ruling R-a).
- Trend-book halt loosening made its own OWNER GO, with `.max_dd_halt` kept by default.
- Row 32 → rows 23 and 32 for VWAP+SMA.
- Scope rule extended with rows 76, 4, 11, 20 and 34.
- OWNER GO tags added to A2, A3, A4, A5, B3–B8 and E1.
- Uptime kill line needs an off-host watcher; AC or an always-on host proposed as a go-live precondition.
- D2 and Phase 2 flagged as changing the owner's 9/16 desk requirement; owner-record lens kept.
- The second host is worded as a migration of one instance.
- B1 now also outputs to the dashboard.
- The outage recast as the deliberate wind-down, with a procedure fix and AC kept as a separate risk (ruling R-e).
- No off-host alert exists; the "downtime alert fires" claim removed (ruling R-e).
- Funding commits marked RESOLVED and live (confirmed on `main`; PID 4305 started 9:11 PM PT 9/20).
- 9/18–9/21 rally figures relabelled as rows closed 9/20–9/21, with ETH ex-outage about $1.27 (two verifiers).
- fee_math.py path completed.
- ETH ex-July-lag net added (about $5.18).
- BTC ex-outage reported (about $5.84; the +$0.67 outage effect).
- Capital-table prices labelled as 9/27 closes.

**Rejected or not applied**
- **5m_MR "active test would be ended" (v6, important): REJECTED per ruling R-b.** The slot was already switched off by the bot's own negative-Kelly kill switch at n=57 on 9/24 (PAPER_STATUS.md:18). A4 instead adds its owed verdict record.
- **Collapse section 6 into one line (v6, minor):** not applied, because it is not a factual fix and the plan structure is kept. Row citations were corrected and the section now opens with the one-line rule.
- **"Hold the whole document until 10/14" (v6, critical, alternative fix):** superseded by ruling R-a. The owner asked for this plan, so the live sections stay in, labelled PREPARED ONLY.
- **No change needed (v8, three notes):** the $84.41/$26.87 lot prices, the $87.12 balance, and a blind-run stop count (the ledgers show 33 rebalances and 3 stops, now stated in the plan).

**Still UNVERIFIED**
- Cause of the 7/26–7/27 ETH lag (logs rotated).
- Funding from 8/10 to 8/26 (not cached; needs paging).
- Whether about 815 daily bars are obtainable for B7.
- The bear replay's own average weight; the replay scripts are not on disk.
- The Phemex venue default trigger type (mark or last).
- Current exchange leverage (last read 9/14).
- The Phemex January 2025 hot-wallet incident and the owner's jurisdiction eligibility.
- Whether `live_slot_summaries` picks up a promoted Donchian slot.
- The battery readings are point-in-time.
- Seat-sourced figures not re-derived: the capital seat's vol_scalar maxima, the verdict seat's −6.9%/−5.6% drawdowns and desk facts, the replica MTM drawdowns (−$2.66/−$1.94), and the 2.5M-token desk cost.
- Absence of any prior Donchian DSR (greps found none).
