# CRITIC: completeness review of REPORT.md, run 2026-09-27-0300

**Verdict:** The report's headline is correct. One thesis was screened, it failed, and nothing moves forward; every out.json and audit.json number I re-checked matches the files. The problems are about completeness and citations: the report never cites most of the forced_flows and cross_asset exploratory work, it cites one source ID that no artifact supports, it reads fetch failures from "run-context notes" that are not on disk, and it misses one gate-vs-probe contradiction about touching the screen dataset before freeze. I found no holdout access, and the sha checks pass.

Method: I listed the run dir with `find research/swarm/runs/2026-09-27-0300 -type f | sort` (69 files before this one). I re-opened gate_kept.json, gate_rejections.json, theses/*.json, register/*/*.json, specs/*.frozen.json, screens/*/out.json, audit.json, trades.csv, and every exploratory NOTES/dispositions file. I ran the grep for (e) and registrar.verify for (f) as specified.

## (a) Artifacts not cited in the report

1. `screens/forced_flows_stop_sweep_exhaustion_fade/trades.csv` and `screens/forced_flows_stop_sweep_exhaustion_fade/signal.py` are named in prose ("trades.csv was byte-identical", "signal.py is byte-identical") but never given as paths. The exit mix 84/78/20 comes from trades.csv `exit_reason`, which I re-counted: TP 84, SL 78, TIME 20. Entry months are 2026-06 74, 2026-07 88, 2026-08 20. The month spread is not reported.
2. `screens/forced_flows_stop_sweep_exhaustion_fade/__pycache__/signal.cpython-314.pyc` is an orphaned build artifact in a screen folder.
3. `register/forced_flows_stop_sweep_exhaustion_fade/thesis.json` is not cited. It is the `pruned_path` in universe_check.json, and I checked that it is identical (json diff) to `theses/forced_flows_stop_sweep_exhaustion_fade.json`.
4. `theses/vol_structure_lottery_jump_fade.json`, `theses/cross_asset_weekend_etf_catchup.json` and `theses/forced_flows_stop_sweep_exhaustion_fade.json` are not cited by path. The report describes all three theses only through gate_*.json and the frozen spec.
5. `mandate.md` is not cited.
6. The whole of `exploratory/forced_flows/` is uncited: `NOTES.md`, `probe_round_cross.py/.out.txt`, `probe_round_cross_1sf.py/.out.txt`, `probe_sweep_breakdown.py/.out.txt`, `probe_sweep_frequency.py/.out.txt`, `probe_sweep_reclaim.py/.out.txt`, `sweep_signal_draft.py`, and `__pycache__/{probe_round_cross,sweep_signal_draft}.cpython-314.pyc`. The report's "Dataset disclosure (from the run context's forced_flows notes)" and "second thesis slot unused" both come from `exploratory/forced_flows/NOTES.md:7` and `:9`, which are not cited.
7. The whole of `exploratory/cross_asset/` is uncited: `NOTES.md`, `causality_sanity.out.txt`, `fee_math_outputs.txt`, `probe_frequency_capped.py/.out.txt`, `probe_weekend_etf_catchup.py/.out.txt`, `probe_weekend_etf_catchup_final.out.txt`, `signal_draft.py`, `signal_final.py`, and `__pycache__/{signal_draft,signal_final}.cpython-314.pyc`. The report's cross_asset fetch-failure list comes from `exploratory/cross_asset/NOTES.md:2`, which is not cited.
8. In `exploratory/vol_structure/`, only `probe_idio_h168.out.txt` is cited. Uncited: `probe_idio_h168.py`, `probe_idio_jump.py/.out.txt`, `probe_lottery_jump.py/.out.txt`, `probe_lottery_jump_admit.py/.out.txt`, `signal_draft_vol_structure_lottery_jump_fade.py`, and `__pycache__/{probe_lottery_jump,signal_draft_vol_structure_lottery_jump_fade}.cpython-314.pyc`. The rejected thesis ran 4 probe variants, and the report mentions only one.
9. In `exploratory/dealer_inventory/`, uncited: `probe_weekend_and_lowvol.py/.out.txt` (pooled Monday fade n=320, mean +54.29 bps per `NOTES.md:14`), `probe_weekend_lowvol_by_week.py/.out.txt` (15/29 weekends positive per `NOTES.md:16`), and `probe_weekend_by_week.py`.
10. Uncited probe scripts: `exploratory/informed_flow/probe_idio_volume.py`, `exploratory/session_calendar/probe_weekend_freq.py`, and `exploratory/literature/local_check_copy.py`.
11. `committee/` does not exist (`ls` returned "No such file or directory"), and `screens/<id>/` has no `out.robust_*.json`. This matches the report's "not run".

## (b) Numbers or claims without a file path next to them

1. The Verdict says "3 theses", "screened 1" and "Five of the eight analyst lenses". No path is given. These are supportable from the `theses/` listing and the `exploratory/*` lens dirs.
2. The vol_structure summary says "holds up to 7 days" with no path. The source is `theses/vol_structure_lottery_jump_fade.json` spec.max_hold_bars=168.
3. The "Dataset disclosure" bullet cites "the run context's forced_flows notes" and no file. The on-disk sources are `exploratory/forced_flows/NOTES.md:7`, `exploratory/forced_flows/probe_sweep_breakdown.py:29`, and the frozen spec's `evidence` field.
4. "tp 120 and 180" has no path in its bullet. The source is the frozen spec's `spec.doa_line`.
5. The "Web budget: no lens has web_budget_exhausted true in the run context" line has no file. On disk, only `exploratory/forced_flows/NOTES.md:2` says "Budget not exhausted"; no other lens file records budget state.
6. "register_status is FROZEN, screen_error is null" and "committee_passed is empty" are sourced to the "orchestrator context", which is not an artifact in the run dir.
7. The whole "Sources that could not be fetched" block cites "each lens's run-context notes" and no file paths. The on-disk sources are `exploratory/forced_flows/NOTES.md:2`, `exploratory/informed_flow/NOTES.md:5`, `exploratory/dealer_inventory/NOTES.md:11`, `exploratory/session_calendar/NOTES.txt:12`, `exploratory/cross_asset/NOTES.md:2` and `exploratory/literature/dispositions.txt:8,16,17`.
8. **"SSRN 3331198 (403)"** (forced_flows) does not appear in any file in the run dir (`grep -rn 3331198` gave 0 hits). `exploratory/forced_flows/NOTES.md:2` says only "one SSRN". The ID is unsupported.
9. **The vol_structure fetch failures, "SSRN and ScienceDirect pages (403)", have no on-disk source.** `exploratory/vol_structure/` has no NOTES file, and neither `theses/vol_structure_lottery_jump_fade.json` nor `gate_rejections.json` records a failed fetch.
10. "informed_flow: 5 of 9 fetches failed" comes from `exploratory/informed_flow/NOTES.md:5`, which is internally inconsistent. It says 9 attempts and 4 readable, but lists 6 failures: sciencedirect S1386418126000029, SSRN 5020002, SSRN 6938742, sciencedirect S0378426625000317, springer, and the EFMA certificate error. The report inherits "5" (9 minus 4) without flagging the mismatch.

## (c) Contradictions between artifacts and the report

1. **gate_kept.json reason vs the forced_flows probes.** gate_kept.json says "the probes used long_1h train before 2026-04-24, which does not overlap mr_edge". Two probes did touch mr_edge train before freeze:
   - `exploratory/forced_flows/probe_sweep_frequency.py:24` calls `load_data.load_ohlcv(s, "1h", era="train", dataset="mr_edge")`. Its output, `probe_sweep_frequency.out.txt`, prints mr_edge train bounds and 1692 bars per symbol.
   - `exploratory/forced_flows/probe_sweep_breakdown.py:29` calls `load_funding(s, era="train")`, which is mr_edge-anchored, and prints mr_edge-train funding means.

   mr_edge train is the exact dataset and era the screen then ran on. The thesis discloses both reads ("only its index bounds were read" plus the funding means). The gate's statement is still factually wrong, and the report does not surface it. STANDARDS #3 requires pre-registration before any data is read; the gate accepted a thesis whose author had opened the screen-era data, and the report should say so.
2. **The "Next run should" bullet 2 misattributes lenses.** It says "Three lenses (dealer_inventory, session_calendar, cross_asset) ... both submitted theses were rejected as relabels of rows 7 and 76". The row-76 rejection is `vol_structure_lottery_jump_fade`. Its lens is `vol_structure` (`theses/vol_structure_lottery_jump_fade.json` "lens"), and it is a BTC-relative jump fade, not a weekend thesis. Only cross_asset (row 7) belongs to the weekend family.
3. **The report says only forced_flows left its second thesis slot unused.** `exploratory/cross_asset/NOTES.md:3` also records that the lens "produced one thesis ... and no second". This is an omission in "Other stages not run".
4. **SSRN 3331198** is in the report but not in `exploratory/forced_flows/NOTES.md:2` (see b8).
5. **vol_structure fetch failures** are in the report with no backing artifact (see b9).
6. **No contradictions among the numeric artifacts:**
   - out.json and audit.json `numbers` and `rerun` agree exactly on n, net_bps_mean, ci95, wr, p_star and time_to_verdict_weeks.
   - audit.json's 84/78/20 and "20 of 182 entry_ts==exit_ts" match trades.csv, which I recounted.
   - The largest |net_bps - (gross_bps - 11.5)| is 7.1e-15, i.e. floating-point noise.
   - The frozen spec universe [BTC, ETH, SOL, XRP, DOGE] equals the thesis universe and `register/.../universe_check.json` tradeable, and dropped_symbols is [].
   - gate_rejections dead_row 76 and 7 match the report.
   - The vol_structure probe numbers match `exploratory/vol_structure/probe_idio_h168.out.txt:1-2`, which uses mc=2, and `fee_math.max_concurrent(200)` returns 2.
   - `fee_math.max_concurrent(150)` returns 3, matching the spec.
7. The frozen spec's `frozen_at` is `2026-09-27T10:00:07Z`. That is identical to `launch_args.json` "now", so it records the run clock, not the wall-clock freeze moment, and cannot show that the freeze came after the probes. The report's "Frozen ... at 3:00 AM PT" repeats this value without that caveat.

## (d) Thesis-file quality (nearest_dead_rows, why_different, evidence numbers)

1. No thesis has an empty nearest_dead_rows:
   - vol_structure has 6 rows (76, 3, 6, 110, 111, 19).
   - cross_asset has 6 rows (7, 18, 113, 106, 110, 76).
   - forced_flows has 7 rows (25, 6, 110, 3, 76, 33, 77).
   - Every evidence field contains numbers.
2. `theses/vol_structure_lottery_jump_fade.json` nearest_dead_rows leaves out row 2 (short-horizon alt reversion, `research/swarm/kb/DEAD_LIST.md:14`). `gate_rejections.json` says row 2 also applies.
3. `theses/cross_asset_weekend_etf_catchup.json` has a specific but factually wrong why_different for row 7. It says row 7 was a fade only and that continuation is new. `scripts/research/microstructure-2026-06-13/VERDICT.md` TEST 4 (about lines 54-58) shows continuation was measured ("gaps CONTINUE ... Not tradeable either direction").
4. `theses/owner_record_probe.json` sits in `theses/` but is labeled "EXPLORATORY PROBE - not a screen". It has no nearest_dead_rows, mechanism or spec. It belongs under `exploratory/owner-record/`, and the owner-record lens wrote no NOTES file (the report already notes this).

## (e) Holdout access

1. The grep returned one hit: `mandate.md:66`. That line is the mandate's prohibition text ("That rules out era=\"holdout\" and era=\"all\""), not an access, so there is no process failure.
2. Every exploratory probe that loads price data uses `era="train"`. audit.json step2 records the rerun with `--era train`. The only other mr_edge reads are the ones in c1 (train era).

## (f) Frozen spec / signal.py sha verification

1. `registrar.verify` output: `{'research/swarm/runs/2026-09-27-0300/specs/forced_flows_stop_sweep_exhaustion_fade.frozen.json': True}`.
2. The sha256 of `screens/forced_flows_stop_sweep_exhaustion_fade/signal.py` is 5cac80afcc7c0ddf8add3f20f67143b3a84e0d72af3e90122e3cca1c173fdd25. That equals the sha256 of the frozen `thesis.signal_py` and the out.json `signal_sha256`, and the file is byte-identical to the frozen signal_py (Python equality check True).
3. Nothing failed to verify.

## (g) Daily-ROI target or hand-computed statistic in the report

1. Daily-ROI target: none.
2. Hand-computed statistics: none. Every mean, CI, WR, p*, trades/week and time-to-verdict is quoted at full precision from `out.json` or `audit.json`. "26 dropped" is out.json `portfolio.n_dropped`. "5 of 9" is a count from lens notes, not a statistic (see b10).
3. Style note only: the report uses 24-hour times, "2026-08-10 11:00 UTC" (train span) and "11:00 UTC". Under the owner's 12-hour rule these should read 11:00 AM UTC / 4:00 AM PT.
