# CRITIC — desk run 2026-09-25-2036

Verdict first: **research/swarm/runs/2026-09-25-2036/REPORT.md does not exist**, so the synthesis seat's output is missing. I checked for it twice (`ls` at 2026-09-26 03:58 UTC, which is 8:58 PM PT on 2026-09-25). Items (a), (b) and (g) are judged against a report that is absent. Items (c)-(f) were checked from the raw files. Holdout grep: no process failure (the one hit is the mandate's own prohibition text). Frozen sha: verifies True. The only screened thesis, `cross_asset_brrny_window_continuation`, failed its pre-registered DOA line on out.json: CI straddles zero and WR is below p*.

## (a) Artifacts not cited in the report

1. **REPORT.md missing.** Because there is no report, every artifact in the run dir is uncited. desk.js `closeOut` runs synthesis before the critic, so the synthesis seat either returned null or did not write its file. This is a process failure and needs a LESSONS line.
2. Uncited screen artifacts: `screens/cross_asset_brrny_window_continuation/out.json`, `audit.json`, `trades.csv`, `signal.py`, plus a stray `__pycache__/signal.cpython-314.pyc`.
3. Uncited exploratory artifacts: 26 files (every file under `exploratory/`), including `cross_asset/*` (5 probes + outputs, `signal_draft.py`), `dealer_inventory/*`, `informed_flow/notes.md`, `literature/*`, `owner-record/*`, `session_calendar/sourcing_log.md` and `vol_structure/*`. Five lenses returned 0 theses: informed_flow, session_calendar, dealer_inventory, vol_structure and literature. Per desk.js they belong in the report's "What was not done" section, which does not exist.
4. `exploratory/vol_structure/probe_letf_close_fade_specparams.out.txt` has no matching script. `probe_letf_close_fade.py` has an mtime of 20:43, but the output was written at 20:47 with different params (tp 200, k 1.0) than the sibling `.out.txt`. The command that produced it is not recorded, so its provenance is unrecorded.
5. `exploratory/vol_structure/probe_letf_close_fade.py:29-33` and `probe_lv_upside_break.py:38-41` run `screen.simulate` + `admit_trades` + `bootstrap_ci.mean_ci` on train. They sweep direction (±1), universe (2 vs 4 symbols), tp/k and up/down (`probe_letf_close_fade.out.txt` has 4 variants, `probe_lv_upside_break.out.txt` has 2). These are unregistered shadow screens. No thesis came out of them, so multiplicity was not charged to any spec, but the search is not recorded anywhere a report would cite.
6. Not a finding: `committee/` and `screens/<id>/out.robust_*.json` are absent **by design**. desk.js:304 makes the committee eligible only when audit CONFIRMED **and** `ci_excludes_zero` is true, and `audit.json` has `ci_excludes_zero: false`.
7. Reconciliation is not yet visible. `research/swarm/kb/DEAD_LIST.md` has no row for `cross_asset_brrny_window_continuation` (grep: 0 hits). This is expected only if the reconciler seat runs after this critic (desk.js `closeOut` order). Verify after close.

## (b) Numbers in the report without a file path

1. Not assessable, because REPORT.md is missing. No report numbers exist to check.
2. Unsourced numbers in the thesis files themselves:
   - `theses/owner_record_delist_peg_dislocation_fade.json:6` (prediction) gives "33 trades in 46.68 weeks = 0.707/week". Neither 46.68 nor 0.707 has a path. `owner_record_probe.json` has only `date_range_utc`, so 0.707 is hand arithmetic, which is an STANDARDS #8 defect.
   - `gate_rejections.json` repeats "0.707/week" and "70.73" with no path.

## (c) Contradictions between files (re-opened, report not trusted)

1. **Unverified lot minimums.**
   - Thesis `theses/cross_asset_brrny_window_continuation.json:39` (evidence) and gate_kept.json state "every universe symbol passes lot_check at position_notional()=200".
   - But `screens/cross_asset_brrny_window_continuation/out.json:44,49,...` shows `lot_usd: null` (lots 200) for 13 of 18 symbols: LINK LTC ADA BNB AAVE UNI SUI NEAR XLM TAO ONDO 1000PEPE 1000SHIB. `audit.json:12` confirms they are not in `fee_math.LOT_MIN_USD`, so their lot minimums are unverified, not passed. The same null pattern appears in `exploratory/cross_asset/probe_frequency.out.txt:5`.
   - This bears on CONSTRAINTS viable item 4.
2. **Selective placebo citation.**
   - Thesis evidence (`theses/cross_asset_brrny_window_continuation.json:39`) says `probe_fix_hour.out.txt` "shows NY-15:00 outlier bars continued while placebo NY hours 13/14/17 reverted".
   - The same file's `NY hour 10:` block (`exploratory/cross_asset/probe_fix_hour.out.txt:16-24`) also shows continuation (negative fade: k=1.5 h=3 −19.9, h=6 −23.3; k=2.0 h=3 −33.9, h=6 −56.1). The thesis omits that placebo hour.
   - The hour-13 block is also mixed (k=1.5 h=12 is −5.0, `probe_fix_hour.out.txt:26-34`).
3. **Contrary probe not cited.** `exploratory/cross_asset/probe_session_split.out.txt:1-10` shows corr(us->post) negative for 9 of the 10 symbols (SUI +0.009 is the only positive). That is a US-session → post-session reversal, the opposite of the continuation premise. The thesis evidence does not mention it.
4. **Probe vs screen (observation, not an audit defect).**
   - The probes' uncapped forward returns suggested large continuation: `probe_fix_hour.out.txt:6-14` and `probe_fix_hour_bysym.out.txt` H1/H2 rows.
   - The frozen screen shows `net_bps_mean` −16.141 with ci95 [−37.55, 4.00] and wr 0.4551 < p_star 0.5383 (`out.json:6-11`, `audit.json:17-25`).
   - The probes had no TP/SL, no max_concurrent and a 10-symbol subset, so the exploratory numbers were not predictive of the registered screen.
5. **Small mismatch in time_to_verdict.** The owner_record thesis (`:6`) and `gate_rejections.json` state time_to_verdict_weeks 70.73. `fee_math.time_to_verdict_weeks(0.707)` returns 70.72135785007073 (run this critic). The stated number comes from an unrecorded, unrounded input (see b.2).
6. Consistent (no contradiction):
   - `out.json`, `audit.json` numbers and `audit.json` rerun agree: n 167, net_bps_mean, ci95, wr, p_star, time_to_verdict_weeks 12.8279.
   - `out.json.signal_sha256` 56759c5a…a4b2 equals `shasum -a 256 screens/.../signal.py`.
   - The thesis `signal_py` string is byte-equal to `screens/.../signal.py`.
   - The frozen universe (18 symbols, `specs/...frozen.json`) equals the thesis universe. `register/cross_asset_brrny_window_continuation/universe_check.json` has `dropped_symbols: []` and `all_tradeable: true`.
   - `audit.json` p_boot 1.0 matches the desk.js:133 ladder default (1.0 when no alpha level gives a lower CI bound > 0).
   - `gate_kept.json` and `gate_rejections.json` together cover both theses. `theses/owner_record_probe.json` is an exploratory probe, not a thesis (desk.js:169).
7. **Mandate not met.** `mandate.md` §4 requires "At least two analyst lenses must target holds > 8h". Neither thesis does:
   - The screened spec has `max_hold_bars` 6 on 1h, i.e. 6h (`specs/cross_asset_brrny_window_continuation.frozen.json`).
   - The gate-rejected spec is 12 × 5m (`theses/owner_record_delist_peg_dislocation_fade.json`).

## (d) Thesis quality: nearest_dead_rows, why_different, evidence numbers

1. `cross_asset_brrny_window_continuation`: 6 dead rows (3, 7, 18, 110, 106, 109). Each why_different is row-specific. Evidence carries numbers ($58B, 0.533, 0.027, F=8.4767, p=0.00406, 87,672 obs, 50.6% vs 38.4%). Defect: the evidence cites probes selectively (c.2, c.3).
2. `owner_record_delist_peg_dislocation_fade`: 5 dead rows (2, 76, 6, 110, 19). Each is row-specific. Evidence has numbers with paths to `owner_record_probe.json` (n=33, +$8,128.01, WR 0.8182, CI95 [−5.878, −2.531]). The arxiv 2601.18991 source is cited explicitly with no number, which is disclosed. Defect: see b.2.
3. Otherwise none.

## (e) Holdout access

1. `grep -rn "COMMITTEE-HOLDOUT-READ\|era=\"holdout\"\|era='holdout'\|era=\"all\"\|--era holdout\|--era all" research/swarm/runs/2026-09-25-2036` has one hit: `mandate.md:79`. That hit is the mandate's own prohibition sentence ("no era="holdout"/"all""), not an access. Every exploratory `load_ohlcv` call uses `era="train"`/`'train'`, `dataset="long_1h"`. No `fetch_ohlcv_ccxt` or token usage was found.
2. **Process failure (repeat of LESSONS 2026-09-19, `research/swarm/kb/LESSONS.md:22`).**
   - `exploratory/literature/local_check_copy.py:2,7` reads raw CSVs from `/Users/jonaspenaso/Desktop/Phmex-S/backtest_data_june` via `pd.read_csv`, bypassing `load_data` and its holdout guard.
   - Per `exploratory/literature/local_check_output.txt:2`, the data spans BTC 2026-05-20 → 2026-07-04. That window lies inside the `long_1h` holdout (≈ 2026-04-23 → 08-01, STANDARDS #6).
   - No thesis used it: the family is dead row 106 and the lens produced 0 theses. So no screened spec is contaminated, but the rule in LESSONS:22 was broken again. It needs a new dated LESSONS line.

## (f) Frozen spec / signal sha verification

1. `registrar.verify` → `{'research/swarm/runs/2026-09-25-2036/specs/cross_asset_brrny_window_continuation.frozen.json': True}`. signal.py sha256 56759c5ad10380c280a8408315abacaa16bd89f96596370a54c5cb81a069a4b2 equals `out.json.signal_sha256`. None failed.

## (g) Daily-ROI target or hand-computed statistic in the report

1. Not assessable, because REPORT.md is missing.
2. Outside the report:
   - `mandate.md` §1 mentions the owner's aspiration only as "never a bar" and states "No daily-ROI target is applied". That is not a target.
   - Hand arithmetic appears in thesis prose: "33 trades in 46.68 weeks = 0.707/week" (`theses/owner_record_delist_peg_dislocation_fade.json:6`), see b.2.
   - The probes' CIs came from `bootstrap_ci.mean_ci` (`vol_structure/*.py`, `owner-record/probe.py` output labels). The cross_asset probes report plain means only, with no CI.
