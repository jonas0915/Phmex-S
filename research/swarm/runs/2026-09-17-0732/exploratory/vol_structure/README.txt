EXPLORATORY — vol_structure lens, run 2026-09-17-0732. These are probes, NOT screens; their numbers are not evidence.
Result: NO THESIS SUBMITTED (lens dry at the daily horizon under the desk's constraints).

Files
- 00_symbols_span.txt      long_1h symbol list + train spans (GIGGLE train era runs to 2026-06-12 because load_data splits per-symbol; excluded from probes)
- 01_probe_shock_continuation.py   post-shock continuation (daily range >= SHOCK x 20-day mean, 24h volume >= 2x, directional day), long_1h 1h train, TP=SL, hold 48 bars
- 01_out_c0.75_s2.0_tp200_h48.json  n=12 (too few)
- 01_out_c1.0_s2.0_tp200_h48.json   n=26 net -73.0 bps CI [-150.0, 3.9] WR 0.346 (17 SL / 9 TP)
- 01_out_c1.0_s1.75_tp200_h48.json  n=28 net -54.4 bps CI [-125.8, 17.1] WR 0.393
- 01_out_c0.9_s1.75_tp150_h48.json  n=23 net -57.2 bps CI [-109.3, 8.1] WR 0.348
- 02_variants_summary.txt   the three lines above
- 03_probe_mr_edge.py / 03_out_mr_edge_c1.0_s2.0_tp200_h48.json / 03_summary.txt   same probe on mr_edge 1h train: n=8, net -11.5, CI [-161.5, 138.5]
- 04_ttv.txt   fee_math.time_to_verdict_weeks at 0.607 trades/week = 82.4 weeks (fails viable #3 <= 26 weeks)

Why no thesis: the pre-registrable direction (continuation after a daily-horizon vol shock, counterparty = liquidation engine + vol-target deleveraging) is negative on every train probe and fires ~0.6/week across 18 symbols. The opposite sign (fade) is DEAD_LIST rows 3/6/76 family and would be a post-hoc flip. Options-expiry reversal (FRL 2026 paper, n=1,059 expiry days) is ~0.16-0.21% per leg per cryptoslate's 2026-09-11 replication — below the 100 bps floor and needs ATM-OI/gamma data the bot lacks.
Holdout never touched. mr_edge probe (03_*) used mr_edge train data dated >= 2026-04-23 — so if any future long_1h thesis is built from this lens, it must not cite 03_*.
