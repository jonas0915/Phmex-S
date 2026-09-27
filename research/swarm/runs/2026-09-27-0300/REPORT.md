# REPORT: desk run 2026-09-27-0300

The run started 2026-09-27 at 3:00 AM PT, with dry_run false, max_analysts 8 and max_screens 5 (`research/swarm/runs/2026-09-27-0300/launch_args.json`).

## Verdict

The desk produced 3 theses and screened 1. None passed committee, so nothing moves forward.
- The gate rejected 2 theses as relabels of dead rows (`research/swarm/runs/2026-09-27-0300/gate_rejections.json`).
- The gate kept 1 thesis, `forced_flows_stop_sweep_exhaustion_fade`, which was screened on the train era. It failed: its mean net result was negative and its CI95 straddles zero. The audit reproduced the numbers exactly.
- Five of the eight analyst lenses returned no thesis. Each gave a sourced reason (see "What was not done").

## Theses

**vol_structure_lottery_jump_fade: gate-rejected, dead row 76.**
It shorts a coin after a large BTC-relative up-day and holds up to 7 days. The gate judged that to be conditional multi-day reversal (row 76, with row 2 also relevant), and its sources are cross-sectional sorts only. Its own train probe of the exact registered spec was already null: admitted n=84, mean -2.0 bps, CI [-44.8, 40.9], WR 0.524 against p*(200) 0.52875 (`research/swarm/runs/2026-09-27-0300/gate_rejections.json`, quoting `research/swarm/runs/2026-09-27-0300/exploratory/vol_structure/probe_idio_h168.out.txt`). It was not frozen or screened.

**cross_asset_weekend_etf_catchup: gate-rejected, dead row 7 (row 18 also applies).**
Row 7's source, `scripts/research/microstructure-2026-06-13/VERDICT.md` TEST 4, already tested weekend-gap continuation into the TradFi reopen and found it not tradeable in either direction net of fees. Moving the anchor to the ETF Monday open, adding vol-scaling and widening to 5 symbols are parameter or universe changes (`research/swarm/runs/2026-09-27-0300/gate_rejections.json`). It was not frozen or screened.

**forced_flows_stop_sweep_exhaustion_fade: screened, failed.**

The idea: fade a closed 1h bar that pierces the prior 72-bar high or low but closes back inside it. The named counterparty is the stop-loss and liquidation flow that rested just beyond that level.

Setup:
- **Spec** (`research/swarm/runs/2026-09-27-0300/specs/forced_flows_stop_sweep_exhaustion_fade.frozen.json`): dataset `mr_edge`, 1h bars, symmetric TP/SL of 150 bps, max hold 24 bars, max_concurrent 3.
  - Universe: BTC, ETH, SOL, XRP, DOGE.
  - Frozen 2026-09-27 at 3:00 AM PT, spec sha 3124d390….
- **Gate** (`research/swarm/runs/2026-09-27-0300/gate_kept.json`): evidence grade B. It was not graded A because no source supports the fade payoff itself, and Osler's cascades point toward continuation.
- **Universe check** (`research/swarm/runs/2026-09-27-0300/register/forced_flows_stop_sweep_exhaustion_fade/universe_check.json`): all 5 symbols are listed and active; dropped_symbols is empty.
- **Dataset disclosure** (from the run context's forced_flows notes): the thesis moved to `mr_edge` because an exploratory probe called `load_data.load_funding(era='train')` without a dataset, which read `mr_edge` funding from inside the `long_1h` holdout window (STANDARDS #6).

Train-screen results, all from `research/swarm/runs/2026-09-27-0300/screens/forced_flows_stop_sweep_exhaustion_fade/out.json`:
- n = 182 admitted, out of 208 unconstrained; 26 were dropped by the max_concurrent 3 cap.
- net_bps_mean = -3.843812932804567.
- CI95 = [-24.86903305201303, 16.207261398979114].
- WR = 0.5439560439560439, against p* = 0.5383333333333333.
- trades_per_week = 18.081608515671203.
- time_to_verdict_weeks = 2.7652407116692825.
- Causality: PASS. lot_check: all 5 symbols ok.
- Train span: 2026-06-01 to 2026-08-10 11:00 UTC.

Audit, from `research/swarm/runs/2026-09-27-0300/screens/forced_flows_stop_sweep_exhaustion_fade/audit.json`:
- Verdict CONFIRMED, ci_excludes_zero false, p_boot 1.0.
- Frozen spec verified. signal.py is byte-identical to the frozen signal_py.
- The rerun reproduced out.json exactly, and trades.csv was byte-identical.
- All 182 trade rows matched the signal, with 0 mismatches. net_bps == gross_bps - 11.5 on every row.
- The auditor recomputed p_star(150), time_to_verdict_weeks and max_concurrent(150)=3, and all matched.
- The screen fails CONSTRAINTS viable item 1 and the spec's DOA line. WR clears p*, but the TP/SL/TIME exit mix of 84/78/20 still nets negative after c.
- Informational findings:
  - 2 trades were cut short by the end of the train data.
  - 20 of 182 trades hit TP or SL inside the entry bar, so their intrabar ordering is screening-grade.
  - The spec expected 23.7 trades/week; the screen realized 18.08.

Committee: **not run**. There is no `research/swarm/runs/2026-09-27-0300/committee/` directory, and committee_passed is empty in the orchestrator context.
- Economics vote: not run.
- Statistics vote: not run.
- BH table: not run. The only input would have been audit p_boot 1.0 (`research/swarm/runs/2026-09-27-0300/screens/forced_flows_stop_sweep_exhaustion_fade/audit.json`).
- tp±20% robustness read (tp 120 and 180): **not run**. There is no `out.robust_*.json` in `screens/forced_flows_stop_sweep_exhaustion_fade/`.
- The primary screen already fails the frozen DOA line (the CI includes 0 and the mean is ≤ 0), so none of these would change the outcome.

Per STANDARDS #15, this thesis must get a DEAD_LIST row.

## What was not done

**Lenses that returned no thesis:**
- **informed_flow** (`research/swarm/runs/2026-09-27-0300/exploratory/informed_flow/NOTES.md`). Sourced mechanisms were fee-trapped (arXiv 2608.21888, 2607.09426), already dead (rows 106 and 112 for BTC-to-alt lead-lag), or cross-sectional (row 5). Its probe (`exploratory/informed_flow/probe_idio_volume.out.txt`) found that volume did not separate informed from uninformed moves. The only pattern left was a relabel of rows 2 and 76.
- **dealer_inventory** (`research/swarm/runs/2026-09-27-0300/exploratory/dealer_inventory/NOTES.md`).
  - Weekend-inventory fade: only 19 of 41 weekends had a positive mean fade (`exploratory/dealer_inventory/probe_weekend_by_week.out.txt`). A Binance Research source contradicts it, and it is economically the same bet as row 7.
  - Volume-conditioned reversal would relabel rows 5 and 76.
  - Basis reversion falls under the owner's funding ban.
  - Expiry unwind was already tried in prior runs.
- **session_calendar** (`research/swarm/runs/2026-09-27-0300/exploratory/session_calendar/NOTES.txt`).
  - Monthly and quarterly events are too rare to meet the 26-week time-to-verdict under the concurrency cap.
  - The Deribit expiry effect is intraday and sits near row 105.
  - A weekend-dump long clears item 3 only at its loosest setting (`exploratory/session_calendar/probe_weekend_freq.out.txt`).
  - Unconditional weekend or day-of-week trades would relabel rows 7, 18 and 67.
- **literature** (`research/swarm/runs/2026-09-27-0300/exploratory/literature/dispositions.txt`). No source gave a counterparty, an OHLCV-observable signal, enough size and no dead-row overlap together. The local check (`exploratory/literature/local_check_output.txt`) was fee-trapped and belongs to the row 106 family.
- **owner-record** (no NOTES file; the probe is `research/swarm/runs/2026-09-27-0300/exploratory/owner-record/probe.py`, output `research/swarm/runs/2026-09-27-0300/theses/owner_record_probe.json`). The only profitable subset is the u100TRYBUSD delisting episode. That was already filed and rejected as not screenable in `research/swarm/runs/2026-09-25-2036/gate_rejections.json`. The rest of the book has a per-trade CI95 entirely below zero (`theses/owner_record_probe.json`).

**Web budget:** no lens has web_budget_exhausted true in the run context.

**Registrar, screen and audit errors:** none. register_status is FROZEN, screen_error is null and the audit is CONFIRMED (orchestrator context; `screens/forced_flows_stop_sweep_exhaustion_fade/audit.json`).

**Other stages not run:**
- The two gate-rejected theses were never frozen or screened.
- The forced_flows lens left its second thesis slot unused.
- The committee and the tp±20% robustness read were not run (see above).

**Sources that could not be fetched (none are cited), per each lens's run-context notes:**
- forced_flows: two ScienceDirect pages (403), SSRN 3331198 (403), tradingresearchub (paywall), roguequant (preview had no stats).
- informed_flow: 5 of 9 fetches failed (403, redirect or certificate error). URLs are in its NOTES.md.
- dealer_inventory: ScienceDirect (403), Kaiko (redirect), TradingView (404).
- session_calendar: SSRN 6592830, ScienceDirect S1062940825000816, a ResearchGate weekend PDF and the CME 24/7 article (403 or timeout).
- vol_structure: SSRN and ScienceDirect pages (403).
- cross_asset: ScienceDirect, BeInCrypto and bitcoinethereumnews (403), and both cmegroup pages (timeout).
- literature: the FRL 2026 Deribit-expiry page (403), a Bitcoin intraday momentum PDF (blocked), and `academic/ssrn_6932998.html` (Elsevier "Content Blocked").

## Next run should

- **Require a dataset on every exploratory load before the first probe.** A `load_funding(era='train')` call with no dataset silently read `mr_edge` rows from inside the `long_1h` holdout window and forced forced_flows onto a different dataset mid-run. The analyst harness should reject exploratory loads that do not name a dataset.
- **Share claimed mechanisms across lenses and pre-screen them against the watch-list rows (7, 18, 76) before web budget is spent.** Three lenses (dealer_inventory, session_calendar, cross_asset) independently probed the weekend family, and both submitted theses were rejected as relabels of rows 7 and 76. One of them was submitted even though its own probe of the exact registered spec was null.
- **Write a committee record even when the primary screen fails.** It should state "skipped: primary DOA failed", every lens should write a NOTES file (owner-record did not), and the synthesis seat should not have to infer "not run" from missing directories.
