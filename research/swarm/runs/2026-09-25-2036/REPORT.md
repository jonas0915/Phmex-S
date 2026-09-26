# REPORT — desk run 2026-09-25-2036

The run started 2026-09-25 at 8:36 PM PT, with dry_run false (`research/swarm/runs/2026-09-25-2036/launch_args.json`).

## Verdict

This run produced 2 theses. The gate rejected 1 as not screenable and kept 1, which was screened. The committee passed none, so nothing moves forward.

The screened thesis was `cross_asset_brrny_window_continuation`. It failed on the train era:
- Its mean net result was negative.
- Its CI95 straddles zero.
- Its win rate was below p*.

The audit reproduced these numbers exactly.

Six of the eight analyst lenses returned no thesis, each with a sourced reason (see "What was not done").

Note: this seat's write of `research/swarm/runs/2026-09-25-2036/REPORT.md` was blocked by the harness, which returns report content as text instead. The orchestrator must save it.

## Theses

**owner_record_delist_peg_dislocation_fade — gate-rejected as not screenable (dead row: none).**
- The universe is one inverse TRYB-pegged perp inside a delisting window. It is in neither `mr_edge` nor `long_1h`.
- The bot has no inverse path, no delisting feed and no anchor-price input.
- At its own 0.707 trades/week, time_to_verdict_weeks is 70.73. That is above the 26-week limit.
- Sources: `research/swarm/runs/2026-09-25-2036/gate_rejections.json` and `research/swarm/runs/2026-09-25-2036/theses/owner_record_delist_peg_dislocation_fade.json` (spec.expected_trades_per_week, prediction).
- Supporting probe, from `research/swarm/runs/2026-09-25-2036/theses/owner_record_probe.json`:
  - The owner record without the TRYB contract has a bootstrap mean CI95 of [-5.878, -2.531] USD/trade.
  - The TRYB contract alone summed to +8128.01 USD.

**cross_asset_brrny_window_continuation — screened, failed.**

The idea: US spot bitcoin ETFs are valued at the CME CF BRRNY rate, fixed over the 3:00 to 4:00 PM ET window. The thesis bets that an outsized NY-3 PM 1h bar keeps moving the same way for the next 6 bars.
- Spec: symmetric TP/SL of 150 bps, 18 symbols, dataset `long_1h` (`research/swarm/runs/2026-09-25-2036/specs/cross_asset_brrny_window_continuation.frozen.json`).
- Gate: evidence grade B (`research/swarm/runs/2026-09-25-2036/gate_kept.json`). It was not graded A because the tradeable link (the move continuing after 4 PM) is the thesis's own inference, with no external source.
- Universe check: all 18 symbols are tradeable and none were dropped (`research/swarm/runs/2026-09-25-2036/register/cross_asset_brrny_window_continuation/universe_check.json`).

Train screen results, all from `research/swarm/runs/2026-09-25-2036/screens/cross_asset_brrny_window_continuation/out.json`:
- n = 167 admitted under max_concurrent 3, out of 393 unconstrained; 226 were dropped.
- net_bps_mean = -16.141136404264746.
- CI95 = [-37.551384049781916, 3.9963538916703234].
- WR = 0.4550898203592814, against p* = 0.5383333333333333.
- trades_per_week = 3.8977493748263408.
- time_to_verdict_weeks = 12.827915597376675.
- Causality check: PASS.

Audit, from `research/swarm/runs/2026-09-25-2036/screens/cross_asset_brrny_window_continuation/audit.json`:
- Verdict CONFIRMED, ci_excludes_zero false, p_boot 1.0.
- The re-run reproduced out.json exactly, and trades.csv was byte-identical.
- All 167 entries matched the signal, with 0 mismatches.
- net_bps == gross_bps - 11.5 on every row.
- It fails CONSTRAINTS viable criteria 1 and 2.
- Informational: 13 of 18 symbols show lot_usd null because they are not in `fee_math.LOT_MIN_USD`. Their lot minimums are unverified, not confirmed.

Committee: **not run**. There is no `research/swarm/runs/2026-09-25-2036/committee/` directory, and the orchestrator context shows committee_passed as empty.
- Economics vote: not run.
- Statistics vote: not run.
- BH table: not run. The only input would have been audit p_boot 1.0.
- tp±20% robustness read: **not run**. There is no `out.robust_*.json` in `screens/cross_asset_brrny_window_continuation/`.
- The primary screen already fails the frozen DOA line (the CI includes 0 and WR < p*), so none of these would change the outcome.

## What was not done

**Lenses that returned no thesis:**

- **forced_flows** — dry for our costs. No probes were run.
  - Osler's round-number stop flow is under 1 bp and gone within minutes.
  - Funding-settlement flows are dead (rows 7/82) and banned (STANDARDS #14).
  - Cascades and ADL are dead rows 6/108/110/112. Leveraged-token rebalance is row 109.
  - Listings cannot be screened.
- **informed_flow** — dry.
  - Cross-venue and spot-to-perp lead-lag need data we do not have.
  - The quarter-hour imbalance effect needs aggressor-flagged trades and is fee-trapped.
  - BTC-to-alt propagation is dead (rows 106/107/112).
  - Notes: `research/swarm/runs/2026-09-25-2036/exploratory/informed_flow/notes.md`.
- **dealer_inventory** — dry.
  - The Deribit expiry reversal was probed on train and did not reverse (`research/swarm/runs/2026-09-25-2036/exploratory/dealer_inventory/probe_expiry_reversal.out.txt`).
  - Drift-burst reversion is fee-trapped and belongs to the row 6/80/110 family.
  - Weekend inventory is row 7.
  - Log: `research/swarm/runs/2026-09-25-2036/exploratory/dealer_inventory/sources_log.txt`.
- **session_calendar** — dry. No probes were run.
  - Turn-of-month has no forced counterparty, so it would relabel rows 18/7.
  - Macro-print drift is row 84.
  - Log: `research/swarm/runs/2026-09-25-2036/exploratory/session_calendar/sourcing_log.md`.
- **vol_structure** — two exploratory train probes, not evidence:
  - Low-vol upside break, long: n 44, mean -14.537266777505335 net bps, CI [-85.22444142537081, 62.502831301901885], WR 0.38636363636363635 against p* 0.5191666666666667 (`research/swarm/runs/2026-09-25-2036/exploratory/vol_structure/probe_lv_upside_break.out.txt`).
  - Leveraged-ETF close fade at k=1.0: n 170, mean -3.144127222920105, CI [-31.355684511018687, 24.23336408653946], WR 0.5176470588235295 against p* 0.52875 (`research/swarm/runs/2026-09-25-2036/exploratory/vol_structure/probe_letf_close_fade_specparams.out.txt`).
  - The seat declined to register a threshold picked on train data.
- **literature** — dry.
  - None of the five pre-fetched papers is usable.
  - The quarter-hour and 15-minute reversal effects are fee-trapped.
  - Dispositions: `research/swarm/runs/2026-09-25-2036/exploratory/literature/dispositions.txt`.
  - The local_check output (`research/swarm/runs/2026-09-25-2036/exploratory/literature/local_check_output.txt`) falls in the row 106 family.

**Web budget.** No lens has web_budget_exhausted = true in the run context. All stopped on their own.

**Errors.** None were recorded: register status FROZEN, no dropped symbols, screen_error null, audit CONFIRMED.

**Sources that could not be fetched** (as reported by the lens seats; none are cited):
- ScienceDirect S1544612322001179, S1544612326008688, S0275531925004192, S0378426625000317 and S1062940825000816 (HTTP 403).
- Springer s10690-026-09589-z (auth redirect).
- PeerJ cs-3810 (403).
- EFMA order-flow PDF (TLS error).
- SSRN 6592830 and 6889877 (403).
- Medium/Coinmonks (403).
- cfbenchmarks.com (blocked).
- etfdb (403).
- cmegroup FAQ and nasdaq.com (timeouts).
- AEA/ASSA PDF (could not be parsed).
- arXiv 2601.18991 body (not extracted; cited for framing only).
- `exploratory/literature` academic/ssrn_6932998.html (Cloudflare block page).

**Reconcile (STANDARDS #15) — not done yet.** `cross_asset_brrny_window_continuation` needs a row in `research/swarm/kb/DEAD_LIST.md`. Searching DEAD_LIST.md and SURVIVORS.md for "brrny" returns nothing.

## Next run should

- Run the committee seats — economics, statistics with BH, and the registered tp±20% read — on every screened thesis, even one that clearly fails. Then there are no "not run" gaps in `committee/*.json` or `out.robust_*.json`.
- Add the 13 universe symbols missing from `fee_math.LOT_MIN_USD`, taken from the live Phemex market list: LINK, LTC, ADA, BNB, AAVE, UNI, SUI, NEAR, XLM, TAO, ONDO, 1000PEPE, 1000SHIB. Until then, `lot_check` does not verify viable item 4 for most of `long_1h`.
- Give lens seats a data-availability checklist up front (aggressor flow, spot, options OI, event feeds) so they stop re-sourcing mechanisms our datasets cannot test. Also have the gate stop, before screening, any thesis whose tradeable link is the analyst's own inference and whose train probe already shows decay in the second half of train.
