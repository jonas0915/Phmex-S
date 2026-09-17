# EXPLORATORY — vol_structure lens, run 2026-09-17-0701 (NOT the screen; numbers here are not evidence)

All probes: dataset `long_1h`, era `train` only (2025-06-27 06:00 -> 2026-04-23 04:00 UTC per BTC frame). No `mr_edge` data was loaded by any file in this directory (STANDARDS #6 cross-dataset caveat respected). No holdout, no committee token, no `fetch_ohlcv_ccxt`.

| file | what |
|---|---|
| `signal_expiry_release.py` + `probe_expiry_release.py` | Post-Friday-08:00-UTC-expiry compressed-range breakout, 19 symbols. `probe_expiry_release_out_200_200_72.json`: n=151, net_bps_mean -9.51, CI95 [-41.96, 21.61], WR 0.503 (< p* 0.52875). NOT submitted as a thesis (probe net negative; option-dealer counterparty only exists on BTC/ETH where the fire count is 5 and 8). |
| `signal_shock_drift.py` + `probe_shock_drift.py` | Shock-out-of-compression continuation, 19 symbols. `probe_shock_drift_out_200_200_48.json`: n=262, net +9.75, CI95 [-14.62, 33.39], WR 0.5534, 6.12 trades/wk. `probe_shock_drift_out_300_300_72.json`: n=262, net +8.10, CI95 [-27.17, 42.71], WR 0.5229. Submitted as thesis `vol_structure_shock_compression_drift` WITH the probe result disclosed in the thesis JSON. |
| `lib_numbers.txt` | `fee_math.position_notional`, `p_star(160/200/240)`, `lot_check` for all 19 symbols at $200, `time_to_verdict_weeks`. |

Two geometries were probed for shock_drift (200/48 and 300/72); no further sweep was run.
