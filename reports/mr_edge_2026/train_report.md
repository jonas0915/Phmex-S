# MR edge screen — TRAIN read
- signals: `/Users/jonaspenaso/Desktop/Phmex-S/reports/mr_edge_2026/signals.json`
- prereg: `/Users/jonaspenaso/Desktop/Phmex-S/docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md` sha256 `c68e9ea0fdd71491eb3144baecb442968ea75566700e08f293a874fc95653925`
- generated: 2026-09-04T09:17:40+00:00
- train 2026-06-01 00:00 UTC → 2026-08-03 23:59 UTC (n=608); holdout 2026-08-04 08:00 UTC → 2026-09-03 00:00 UTC excl. (8 h embargo, n=227); dropped 5
- baseline (live cell, all train signals): n=608 mean $-0.024 CI [-0.138, +0.087] sharpe -0.017
- trials: 113 total (H1 79 cells, live twin `tp1.6_sl1.2_t4h` excluded; H2 3; H3 3; H4 3; H5 22 buckets; H6 3 entry-timing, prereg amendment v2)
- guards: pooled BH α=0.1 over all 113 p-values; DSR n_trials=113 (var of trial Sharpes 0.09985); WF 3-fold; min-n kept≥40 (H5 ≥25), removed≥15; bootstrap 2000 reps seed 0

## Caveats
- bootstrap_diff_ci resamples the two sides INDEPENDENTLY (house rule). For H1 the cell and live series come from the SAME rows (paired) and for filters kept is a subset of all-signal; independent resampling ignores that positive dependence, so every diff CI here is CONSERVATIVE (wider than a paired CI). A diff CI that excludes 0 under this treatment is the stronger claim.
- Fill-all at the signal bar close (real maker fill ~27%, adverse selection not modeled): every dollar is an UPPER BOUND. Only relative comparisons (cell vs live, kept vs removed/all) are decision metrics.
- OB/tape gates are not replayed (no historical L2) except where flow_capture supplies H3 inputs.
- fill-all is OPTIMISTIC — real maker fill rate is ~27%. Maker-fill-all is an
    UPPER BOUND on the signal's edge, not a live expectation.
- no adverse selection modeled -> every dollar is an upper bound; only RELATIVE comparisons between cells/cohorts are decision metrics
- funding parity gap: live uses the PREDICTED next rate, replay joins the last SETTLED rate <= signal ts
- flow join = nearest flow_capture row <= ts within 120 s; live OB/tape gates NOT re-applied; scanner_active = any flow row within +/-600 s
- time exits charged the MAKER exit fee (rig `_net` convention); live time exit is a market close (taker): +$0.075 optimistic per time exit at $150 notional
- per-symbol cooldown not applied to rows; cooldown_ok reproduces the rig's one-signal-per-4h-per-symbol set (screens default to cooldown_ok == true)
- fidelity gate tolerates +/-1 bar and reports feature drift vs the entry snapshot
- live 4h extension modeled with the adverse 1m extreme at the 4h mark (pessimistic)
- global max_positions occupancy not modeled -> affects count, not per-trade EV
- replay can only REJECT; survivors go to a real-money forward verdict line
- eval_mode=forming: partial candle rebuilt from cached 1m bars at minute m=1..5 and evaluated on a 300-bar frame (ws_feed cache cap); first firing minute = the signal
- timing parity gap: evaluation on a 60 s grid (1m closes) vs the live ~90 s cycle at arbitrary seconds into the bar -> the live bot can fire between grid points
- volume parity gap: ws-feed candle-builder volume != exchange 1m volume
- frame parity gap: REST fallback (ws stale) evaluates a 500-bar frame; ws path = 300

## Winners (mechanical, ≤1 per family)
- H1: none
- H2: none
- H3: none
- H4: none
- H5: none
- H6: none

## H1 — 79 trials, 0 passing

| cell | n | mean | CI | diff vs live | diff CI | sharpe | p | BH | DSR | WF | min-n | exits | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tp1.0_sl0.8_t2h | 608 | -0.096 | [-0.182, -0.008] | -0.072 | [-0.211, +0.073] | -0.089 | 0.834 | n | 0.000 | --- | Y | stop_loss:217,take_profit:122,time_exit:197,trailing_stop:72 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl0.8_t4h | 608 | -0.070 | [-0.162, +0.022] | -0.046 | [-0.195, +0.102] | -0.060 | 0.722 | n | 0.000 | --- | Y | stop_loss:256,take_profit:153,time_exit:98,trailing_stop:101 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl0.8_t6h | 608 | -0.068 | [-0.166, +0.030] | -0.044 | [-0.194, +0.106] | -0.056 | 0.704 | n | 0.000 | -+- | Y | stop_loss:276,take_profit:166,time_exit:58,trailing_stop:108 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl0.8_t8h | 608 | -0.068 | [-0.168, +0.032] | -0.044 | [-0.195, +0.107] | -0.056 | 0.710 | n | 0.000 | --- | Y | stop_loss:281,take_profit:168,time_exit:44,trailing_stop:115 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.2_t2h | 608 | -0.097 | [-0.194, +0.000] | -0.073 | [-0.223, +0.081] | -0.079 | 0.837 | n | 0.000 | --- | Y | stop_loss:133,take_profit:135,time_exit:264,trailing_stop:76 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.2_t4h | 608 | -0.056 | [-0.168, +0.051] | -0.032 | [-0.190, +0.123] | -0.041 | 0.656 | n | 0.000 | --- | Y | stop_loss:171,take_profit:172,time_exit:153,trailing_stop:112 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.2_t6h | 608 | -0.052 | [-0.171, +0.063] | -0.028 | [-0.192, +0.130] | -0.036 | 0.632 | n | 0.000 | --- | Y | stop_loss:197,take_profit:190,time_exit:98,trailing_stop:123 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.2_t8h | 608 | -0.058 | [-0.179, +0.061] | -0.034 | [-0.199, +0.127] | -0.040 | 0.660 | n | 0.000 | --- | Y | stop_loss:213,take_profit:198,time_exit:62,trailing_stop:135 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.6_t2h | 608 | -0.104 | [-0.207, +0.003] | -0.080 | [-0.239, +0.080] | -0.079 | 0.842 | n | 0.000 | --- | Y | stop_loss:84,take_profit:140,time_exit:306,trailing_stop:78 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.6_t4h | 608 | -0.063 | [-0.184, +0.056] | -0.039 | [-0.209, +0.125] | -0.042 | 0.671 | n | 0.000 | +-- | Y | stop_loss:122,take_profit:181,time_exit:189,trailing_stop:116 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.6_t6h | 608 | -0.073 | [-0.206, +0.052] | -0.049 | [-0.230, +0.117] | -0.046 | 0.707 | n | 0.000 | +-- | Y | stop_loss:151,take_profit:203,time_exit:126,trailing_stop:128 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl1.6_t8h | 608 | -0.087 | [-0.221, +0.045] | -0.063 | [-0.242, +0.108] | -0.053 | 0.752 | n | 0.000 | +-- | Y | stop_loss:168,take_profit:214,time_exit:85,trailing_stop:141 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl2.0_t2h | 608 | -0.114 | [-0.224, -0.001] | -0.090 | [-0.254, +0.075] | -0.082 | 0.871 | n | 0.000 | --- | Y | stop_loss:57,take_profit:143,time_exit:330,trailing_stop:78 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl2.0_t4h | 608 | -0.091 | [-0.218, +0.034] | -0.066 | [-0.244, +0.104] | -0.057 | 0.772 | n | 0.000 | +-- | Y | stop_loss:96,take_profit:185,time_exit:209,trailing_stop:118 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl2.0_t6h | 608 | -0.097 | [-0.239, +0.036] | -0.073 | [-0.259, +0.104] | -0.056 | 0.774 | n | 0.000 | --- | Y | stop_loss:116,take_profit:210,time_exit:152,trailing_stop:130 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.0_sl2.0_t8h | 608 | -0.097 | [-0.243, +0.046] | -0.073 | [-0.259, +0.113] | -0.054 | 0.776 | n | 0.000 | +-- | Y | stop_loss:130,take_profit:222,time_exit:113,trailing_stop:143 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl0.8_t2h | 608 | -0.073 | [-0.164, +0.018] | -0.049 | [-0.191, +0.099] | -0.064 | 0.745 | n | 0.000 | --- | Y | stop_loss:217,take_profit:41,time_exit:206,trailing_stop:144 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl0.8_t4h | 608 | -0.041 | [-0.139, +0.057] | -0.017 | [-0.169, +0.133] | -0.033 | 0.582 | n | 0.000 | -+- | Y | stop_loss:256,take_profit:53,time_exit:105,trailing_stop:194 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl0.8_t6h | 608 | -0.036 | [-0.138, +0.066] | -0.012 | [-0.165, +0.145] | -0.028 | 0.564 | n | 0.000 | -+- | Y | stop_loss:276,take_profit:57,time_exit:62,trailing_stop:213 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl0.8_t8h | 608 | -0.037 | [-0.142, +0.066] | -0.012 | [-0.165, +0.143] | -0.028 | 0.565 | n | 0.000 | -+- | Y | stop_loss:281,take_profit:59,time_exit:45,trailing_stop:223 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.2_t2h | 608 | -0.072 | [-0.174, +0.029] | -0.048 | [-0.205, +0.109] | -0.056 | 0.731 | n | 0.000 | --- | Y | stop_loss:133,take_profit:44,time_exit:274,trailing_stop:157 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.2_t6h | 608 | -0.021 | [-0.148, +0.096] | +0.003 | [-0.166, +0.167] | -0.014 | 0.480 | n | 0.000 | -+- | Y | stop_loss:197,take_profit:62,time_exit:103,trailing_stop:246 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.2_t8h | 608 | -0.028 | [-0.156, +0.099] | -0.004 | [-0.172, +0.163] | -0.018 | 0.518 | n | 0.000 | +-- | Y | stop_loss:213,take_profit:66,time_exit:63,trailing_stop:266 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.6_t2h | 608 | -0.079 | [-0.189, +0.027] | -0.055 | [-0.216, +0.108] | -0.058 | 0.751 | n | 0.000 | --- | Y | stop_loss:84,take_profit:46,time_exit:316,trailing_stop:162 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.6_t4h | 608 | -0.033 | [-0.160, +0.086] | -0.009 | [-0.182, +0.158] | -0.022 | 0.536 | n | 0.000 | +-- | Y | stop_loss:122,take_profit:60,time_exit:196,trailing_stop:230 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.6_t6h | 608 | -0.045 | [-0.180, +0.087] | -0.021 | [-0.200, +0.152] | -0.027 | 0.590 | n | 0.000 | +-- | Y | stop_loss:151,take_profit:65,time_exit:132,trailing_stop:260 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl1.6_t8h | 608 | -0.059 | [-0.195, +0.082] | -0.035 | [-0.217, +0.143] | -0.034 | 0.651 | n | 0.000 | +-- | Y | stop_loss:168,take_profit:69,time_exit:87,trailing_stop:284 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl2.0_t2h | 608 | -0.087 | [-0.200, +0.029] | -0.063 | [-0.229, +0.109] | -0.060 | 0.775 | n | 0.000 | --- | Y | stop_loss:57,take_profit:48,time_exit:340,trailing_stop:163 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl2.0_t4h | 608 | -0.057 | [-0.193, +0.071] | -0.033 | [-0.214, +0.148] | -0.034 | 0.646 | n | 0.000 | +-- | Y | stop_loss:96,take_profit:63,time_exit:216,trailing_stop:233 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl2.0_t6h | 608 | -0.067 | [-0.212, +0.075] | -0.042 | [-0.233, +0.142] | -0.037 | 0.671 | n | 0.000 | --- | Y | stop_loss:116,take_profit:68,time_exit:158,trailing_stop:266 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp1.6_sl2.0_t8h | 608 | -0.068 | [-0.219, +0.079] | -0.044 | [-0.232, +0.147] | -0.037 | 0.677 | n | 0.000 | +-- | Y | stop_loss:130,take_profit:72,time_exit:115,trailing_stop:291 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl0.8_t2h | 608 | -0.057 | [-0.151, +0.038] | -0.033 | [-0.178, +0.117] | -0.048 | 0.669 | n | 0.000 | --- | Y | stop_loss:217,take_profit:25,time_exit:207,trailing_stop:159 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl0.8_t4h | 608 | -0.025 | [-0.125, +0.075] | -0.001 | [-0.155, +0.152] | -0.020 | 0.505 | n | 0.000 | -+- | Y | stop_loss:256,take_profit:30,time_exit:105,trailing_stop:217 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl0.8_t6h | 608 | -0.018 | [-0.124, +0.090] | +0.007 | [-0.147, +0.165] | -0.013 | 0.467 | n | 0.000 | -+- | Y | stop_loss:276,take_profit:33,time_exit:62,trailing_stop:237 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl0.8_t8h | 608 | -0.018 | [-0.126, +0.089] | +0.006 | [-0.147, +0.163] | -0.014 | 0.477 | n | 0.000 | -+- | Y | stop_loss:281,take_profit:34,time_exit:45,trailing_stop:248 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.2_t2h | 608 | -0.056 | [-0.162, +0.047] | -0.032 | [-0.191, +0.126] | -0.043 | 0.660 | n | 0.000 | --- | Y | stop_loss:133,take_profit:26,time_exit:276,trailing_stop:173 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.2_t4h | 608 | -0.009 | [-0.127, +0.105] | +0.015 | [-0.149, +0.176] | -0.006 | 0.421 | n | 0.000 | +++ | Y | stop_loss:171,take_profit:33,time_exit:160,trailing_stop:244 | fail: bh,dsr,diff_vs_live_ci |
| tp2.0_sl1.2_t6h | 608 | -0.000 | [-0.129, +0.119] | +0.024 | [-0.146, +0.186] | -0.000 | 0.389 | n | 0.000 | ++- | Y | stop_loss:197,take_profit:36,time_exit:103,trailing_stop:272 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.2_t8h | 608 | -0.007 | [-0.140, +0.122] | +0.017 | [-0.156, +0.186] | -0.005 | 0.422 | n | 0.000 | ++- | Y | stop_loss:213,take_profit:38,time_exit:63,trailing_stop:294 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.6_t2h | 608 | -0.062 | [-0.174, +0.051] | -0.038 | [-0.202, +0.128] | -0.044 | 0.681 | n | 0.000 | --- | Y | stop_loss:84,take_profit:28,time_exit:318,trailing_stop:178 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.6_t4h | 608 | -0.014 | [-0.143, +0.109] | +0.010 | [-0.169, +0.181] | -0.009 | 0.450 | n | 0.000 | +-- | Y | stop_loss:122,take_profit:35,time_exit:196,trailing_stop:255 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.6_t6h | 608 | -0.024 | [-0.161, +0.110] | +0.001 | [-0.184, +0.176] | -0.014 | 0.495 | n | 0.000 | +-- | Y | stop_loss:151,take_profit:38,time_exit:132,trailing_stop:287 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl1.6_t8h | 608 | -0.037 | [-0.176, +0.105] | -0.013 | [-0.203, +0.168] | -0.021 | 0.546 | n | 0.000 | +-- | Y | stop_loss:168,take_profit:40,time_exit:87,trailing_stop:313 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl2.0_t2h | 608 | -0.070 | [-0.186, +0.049] | -0.046 | [-0.214, +0.124] | -0.047 | 0.704 | n | 0.000 | --- | Y | stop_loss:57,take_profit:28,time_exit:342,trailing_stop:181 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl2.0_t4h | 608 | -0.038 | [-0.176, +0.094] | -0.014 | [-0.202, +0.166] | -0.022 | 0.558 | n | 0.000 | +-- | Y | stop_loss:96,take_profit:36,time_exit:216,trailing_stop:260 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl2.0_t6h | 608 | -0.045 | [-0.195, +0.101] | -0.021 | [-0.216, +0.165] | -0.025 | 0.590 | n | 0.000 | +-- | Y | stop_loss:116,take_profit:39,time_exit:158,trailing_stop:295 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.0_sl2.0_t8h | 608 | -0.046 | [-0.202, +0.104] | -0.022 | [-0.215, +0.169] | -0.025 | 0.591 | n | 0.000 | +-- | Y | stop_loss:130,take_profit:41,time_exit:115,trailing_stop:322 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl0.8_t2h | 608 | -0.063 | [-0.156, +0.029] | -0.039 | [-0.182, +0.111] | -0.054 | 0.705 | n | 0.000 | --- | Y | stop_loss:217,take_profit:8,time_exit:208,trailing_stop:175 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl0.8_t4h | 608 | -0.032 | [-0.132, +0.067] | -0.008 | [-0.163, +0.144] | -0.025 | 0.538 | n | 0.000 | -+- | Y | stop_loss:256,take_profit:10,time_exit:105,trailing_stop:237 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl0.8_t6h | 608 | -0.024 | [-0.128, +0.083] | +0.000 | [-0.152, +0.158] | -0.018 | 0.502 | n | 0.000 | -+- | Y | stop_loss:276,take_profit:12,time_exit:62,trailing_stop:258 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl0.8_t8h | 608 | -0.023 | [-0.130, +0.084] | +0.001 | [-0.155, +0.155] | -0.017 | 0.498 | n | 0.000 | -+- | Y | stop_loss:281,take_profit:13,time_exit:45,trailing_stop:269 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.2_t2h | 608 | -0.062 | [-0.167, +0.042] | -0.038 | [-0.195, +0.122] | -0.047 | 0.682 | n | 0.000 | --- | Y | stop_loss:133,take_profit:9,time_exit:277,trailing_stop:189 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.2_t4h | 608 | -0.014 | [-0.131, +0.098] | +0.010 | [-0.156, +0.168] | -0.010 | 0.453 | n | 0.000 | +-+ | Y | stop_loss:171,take_profit:12,time_exit:160,trailing_stop:265 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.2_t6h | 608 | -0.005 | [-0.133, +0.116] | +0.019 | [-0.151, +0.183] | -0.003 | 0.406 | n | 0.000 | ++- | Y | stop_loss:197,take_profit:14,time_exit:103,trailing_stop:294 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.2_t8h | 608 | -0.010 | [-0.143, +0.118] | +0.014 | [-0.157, +0.184] | -0.006 | 0.431 | n | 0.000 | +-- | Y | stop_loss:213,take_profit:16,time_exit:63,trailing_stop:316 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.6_t2h | 608 | -0.065 | [-0.177, +0.047] | -0.041 | [-0.206, +0.125] | -0.046 | 0.691 | n | 0.000 | --- | Y | stop_loss:84,take_profit:11,time_exit:319,trailing_stop:194 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.6_t4h | 608 | -0.018 | [-0.146, +0.105] | +0.006 | [-0.173, +0.177] | -0.011 | 0.466 | n | 0.000 | +-- | Y | stop_loss:122,take_profit:14,time_exit:196,trailing_stop:276 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.6_t6h | 608 | -0.026 | [-0.166, +0.109] | -0.002 | [-0.187, +0.174] | -0.015 | 0.501 | n | 0.000 | +-- | Y | stop_loss:151,take_profit:16,time_exit:132,trailing_stop:309 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl1.6_t8h | 608 | -0.038 | [-0.181, +0.103] | -0.014 | [-0.203, +0.167] | -0.022 | 0.552 | n | 0.000 | +-- | Y | stop_loss:168,take_profit:18,time_exit:87,trailing_stop:335 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl2.0_t2h | 608 | -0.073 | [-0.190, +0.044] | -0.049 | [-0.216, +0.122] | -0.049 | 0.720 | n | 0.000 | --- | Y | stop_loss:57,take_profit:11,time_exit:343,trailing_stop:197 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl2.0_t4h | 608 | -0.040 | [-0.179, +0.094] | -0.016 | [-0.203, +0.165] | -0.024 | 0.571 | n | 0.000 | +-- | Y | stop_loss:96,take_profit:15,time_exit:216,trailing_stop:281 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl2.0_t6h | 608 | -0.047 | [-0.196, +0.099] | -0.023 | [-0.220, +0.163] | -0.026 | 0.602 | n | 0.000 | +-- | Y | stop_loss:116,take_profit:17,time_exit:158,trailing_stop:317 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp2.4_sl2.0_t8h | 608 | -0.046 | [-0.200, +0.104] | -0.022 | [-0.212, +0.169] | -0.024 | 0.586 | n | 0.000 | +-- | Y | stop_loss:130,take_profit:19,time_exit:115,trailing_stop:344 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl0.8_t2h | 608 | -0.060 | [-0.152, +0.033] | -0.036 | [-0.181, +0.116] | -0.050 | 0.686 | n | 0.000 | --- | Y | stop_loss:217,take_profit:4,time_exit:208,trailing_stop:179 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl0.8_t4h | 608 | -0.029 | [-0.128, +0.071] | -0.005 | [-0.161, +0.148] | -0.022 | 0.519 | n | 0.000 | -+- | Y | stop_loss:256,take_profit:5,time_exit:105,trailing_stop:242 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl0.8_t6h | 608 | -0.020 | [-0.125, +0.086] | +0.004 | [-0.150, +0.162] | -0.015 | 0.477 | n | 0.000 | -+- | Y | stop_loss:276,take_profit:5,time_exit:62,trailing_stop:265 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl0.8_t8h | 608 | -0.019 | [-0.126, +0.087] | +0.006 | [-0.149, +0.160] | -0.014 | 0.477 | n | 0.000 | -+- | Y | stop_loss:281,take_profit:6,time_exit:45,trailing_stop:276 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.2_t2h | 608 | -0.059 | [-0.164, +0.047] | -0.035 | [-0.193, +0.124] | -0.045 | 0.671 | n | 0.000 | --- | Y | stop_loss:133,take_profit:4,time_exit:277,trailing_stop:194 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.2_t4h | 608 | -0.010 | [-0.129, +0.102] | +0.014 | [-0.154, +0.173] | -0.007 | 0.430 | n | 0.000 | --+ | Y | stop_loss:171,take_profit:6,time_exit:160,trailing_stop:271 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.2_t6h | 608 | -0.001 | [-0.130, +0.121] | +0.023 | [-0.147, +0.187] | -0.001 | 0.394 | n | 0.000 | -+- | Y | stop_loss:197,take_profit:6,time_exit:103,trailing_stop:302 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.2_t8h | 608 | -0.003 | [-0.138, +0.129] | +0.021 | [-0.151, +0.192] | -0.002 | 0.398 | n | 0.000 | ++- | Y | stop_loss:213,take_profit:8,time_exit:63,trailing_stop:324 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.6_t2h | 608 | -0.062 | [-0.176, +0.052] | -0.038 | [-0.202, +0.130] | -0.044 | 0.681 | n | 0.000 | --- | Y | stop_loss:84,take_profit:5,time_exit:319,trailing_stop:200 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.6_t4h | 608 | -0.013 | [-0.141, +0.114] | +0.011 | [-0.169, +0.184] | -0.008 | 0.451 | n | 0.000 | +-- | Y | stop_loss:122,take_profit:7,time_exit:196,trailing_stop:283 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.6_t6h | 608 | -0.022 | [-0.161, +0.116] | +0.002 | [-0.183, +0.180] | -0.013 | 0.482 | n | 0.000 | +-- | Y | stop_loss:151,take_profit:7,time_exit:132,trailing_stop:318 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl1.6_t8h | 608 | -0.031 | [-0.175, +0.113] | -0.007 | [-0.194, +0.173] | -0.017 | 0.524 | n | 0.000 | +-- | Y | stop_loss:168,take_profit:9,time_exit:87,trailing_stop:344 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl2.0_t2h | 608 | -0.071 | [-0.187, +0.048] | -0.047 | [-0.214, +0.126] | -0.047 | 0.708 | n | 0.000 | --- | Y | stop_loss:57,take_profit:5,time_exit:343,trailing_stop:203 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl2.0_t4h | 608 | -0.035 | [-0.173, +0.102] | -0.011 | [-0.196, +0.173] | -0.020 | 0.545 | n | 0.000 | +-- | Y | stop_loss:96,take_profit:8,time_exit:216,trailing_stop:288 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl2.0_t6h | 608 | -0.041 | [-0.191, +0.106] | -0.017 | [-0.210, +0.170] | -0.022 | 0.578 | n | 0.000 | +-- | Y | stop_loss:116,take_profit:8,time_exit:158,trailing_stop:326 | fail: bh,dsr,wf,diff_vs_live_ci |
| tp3.0_sl2.0_t8h | 608 | -0.037 | [-0.190, +0.116] | -0.013 | [-0.203, +0.181] | -0.020 | 0.549 | n | 0.000 | +-- | Y | stop_loss:130,take_profit:10,time_exit:115,trailing_stop:353 | fail: bh,dsr,wf,diff_vs_live_ci |

## H2 — 3 trials, 0 passing

| trial | n kept | n removed | n null | kept mean | kept CI | removed mean | removed CI | kept−all | diff CI | sharpe | p | BH | DSR | WF | min-n | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| adx1h<=35 | 475 | 133 | 0 | -0.092 | [-0.219, +0.032] | +0.220 | [-0.020, +0.456] | -0.068 | [-0.240, +0.107] | -0.066 | 0.922 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| adx1h<=40 | 531 | 77 | 0 | -0.076 | [-0.192, +0.042] | +0.332 | [+0.002, +0.654] | -0.052 | [-0.211, +0.110] | -0.054 | 0.898 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| adx1h<=50 | 585 | 23 | 0 | -0.031 | [-0.150, +0.083] | +0.155 | [-0.451, +0.769] | -0.007 | [-0.167, +0.152] | -0.022 | 0.696 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |

## H3 — 3 trials, 0 passing

| trial | n kept | n removed | n null | kept mean | kept CI | removed mean | removed CI | kept−all | diff CI | sharpe | p | BH | DSR | WF | min-n | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| short_skip_buy_ratio>=0.80 | 598 | 10 | 0 | -0.034 | [-0.145, +0.076] | +0.575 | [-0.141, +1.210] | -0.010 | [-0.173, +0.150] | -0.024 | 0.711 | n | 0.000 | -+- | n | fail: min_n,bh,dsr,wf,removed_ci,kept_vs_all |
| short_skip_buy_ratio>=0.90 | 599 | 9 | 0 | -0.030 | [-0.142, +0.080] | +0.376 | [-0.302, +0.915] | -0.006 | [-0.168, +0.148] | -0.021 | 0.710 | n | 0.000 | -+- | n | fail: min_n,bh,dsr,wf,removed_ci,kept_vs_all |
| short_skip_buy_ratio>=0.95 | 602 | 6 | 0 | -0.030 | [-0.141, +0.081] | +0.614 | [+0.107, +1.023] | -0.006 | [-0.167, +0.156] | -0.021 | 0.702 | n | 0.000 | -+- | n | fail: min_n,bh,dsr,wf,removed_ci,kept_vs_all |

## H4 — 3 trials, 0 passing

| trial | n kept | n removed | n null | kept mean | kept CI | removed mean | removed CI | kept−all | diff CI | sharpe | p | BH | DSR | WF | min-n | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| funding_skip_X=0.0001 | 496 | 112 | 0 | -0.030 | [-0.154, +0.097] | +0.002 | [-0.254, +0.243] | -0.006 | [-0.172, +0.164] | -0.021 | 0.687 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| funding_skip_X=0.0003 | 598 | 10 | 0 | -0.022 | [-0.137, +0.085] | -0.161 | [-0.906, +0.562] | +0.002 | [-0.157, +0.162] | -0.015 | 0.640 | n | 0.000 | -+- | n | fail: min_n,bh,dsr,wf,removed_ci |
| funding_skip_X=0.0005 | 607 | 1 | 0 | -0.026 | [-0.137, +0.085] | +1.125 | n/a | -0.002 | [-0.167, +0.159] | -0.018 | 0.682 | n | 0.000 | -+- | n | fail: min_n,bh,dsr,wf,removed_ci,kept_vs_all |

## H5 — 22 trials, 0 passing

| trial | n kept | n removed | n null | kept mean | kept CI | removed mean | removed CI | kept−all | diff CI | sharpe | p | BH | DSR | WF | min-n | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| side=long | 260 | 348 | 0 | -0.005 | [-0.175, +0.173] | -0.038 | [-0.186, +0.107] | +0.019 | [-0.186, +0.221] | -0.004 | 0.529 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci |
| side=short | 348 | 260 | 0 | -0.038 | [-0.186, +0.107] | -0.005 | [-0.175, +0.173] | -0.014 | [-0.194, +0.170] | -0.027 | 0.688 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| long RSI<15 | 0 | 608 | 0 | n/a | n/a | -0.024 | [-0.138, +0.087] | n/a | n/a | +0.000 | 1.000 | n | 0.500 | n/a | n | fail: min_n,bh,dsr,wf,removed_ci,kept_vs_all |
| long RSI 15-22 | 2 | 606 | 0 | -1.570 | [-1.905, -1.234] | -0.019 | [-0.131, +0.088] | -1.546 | [-1.953, -1.131] | -3.310 | 1.000 | n | 0.053 | n/a | n | fail: min_n,bh,dsr,wf,removed_ci,kept_vs_all |
| long RSI 22-30 | 258 | 350 | 0 | +0.007 | [-0.162, +0.185] | -0.047 | [-0.195, +0.103] | +0.031 | [-0.183, +0.239] | +0.005 | 0.477 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci |
| short RSI 70-78 | 301 | 307 | 0 | -0.066 | [-0.231, +0.103] | +0.017 | [-0.140, +0.184] | -0.042 | [-0.242, +0.162] | -0.046 | 0.788 | n | 0.000 | -++ | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| short RSI 78-85 | 44 | 564 | 0 | +0.090 | [-0.320, +0.489] | -0.033 | [-0.148, +0.087] | +0.114 | [-0.309, +0.531] | +0.064 | 0.335 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci |
| short RSI>85 | 3 | 605 | 0 | +0.866 | [-0.609, +2.370] | -0.028 | [-0.139, +0.084] | +0.890 | [-0.549, +2.387] | +0.581 | 0.151 | n | 0.381 | n/a | n | fail: min_n,bh,dsr,wf,removed_ci |
| vol 1.3-1.7x | 398 | 210 | 0 | -0.069 | [-0.213, +0.078] | +0.062 | [-0.117, +0.242] | -0.045 | [-0.224, +0.132] | -0.047 | 0.820 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| vol 1.7-2.5x | 136 | 472 | 0 | +0.036 | [-0.207, +0.264] | -0.042 | [-0.174, +0.089] | +0.061 | [-0.201, +0.332] | +0.027 | 0.383 | n | 0.000 | +++ | Y | fail: bh,dsr,removed_ci |
| vol>2.5x | 74 | 534 | 0 | +0.108 | [-0.181, +0.386] | -0.042 | [-0.161, +0.078] | +0.132 | [-0.176, +0.418] | +0.086 | 0.235 | n | 0.000 | +++ | Y | fail: bh,dsr,removed_ci |
| ADX<15 | 57 | 551 | 0 | +0.070 | [-0.250, +0.368] | -0.034 | [-0.152, +0.089] | +0.094 | [-0.223, +0.409] | +0.059 | 0.312 | n | 0.000 | ++- | Y | fail: bh,dsr,wf,removed_ci |
| ADX 15-22 | 343 | 265 | 0 | +0.014 | [-0.149, +0.167] | -0.073 | [-0.231, +0.108] | +0.038 | [-0.146, +0.231] | +0.010 | 0.426 | n | 0.000 | -++ | Y | fail: bh,dsr,wf,removed_ci |
| ADX 22-30 | 208 | 400 | 0 | -0.112 | [-0.310, +0.077] | +0.022 | [-0.114, +0.161] | -0.088 | [-0.304, +0.142] | -0.079 | 0.887 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| hour 0-6 PT | 172 | 436 | 0 | -0.029 | [-0.237, +0.187] | -0.022 | [-0.156, +0.110] | -0.005 | [-0.246, +0.249] | -0.021 | 0.617 | n | 0.000 | ++- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| hour 6-12 PT | 119 | 489 | 0 | -0.047 | [-0.297, +0.216] | -0.018 | [-0.151, +0.099] | -0.023 | [-0.295, +0.264] | -0.033 | 0.651 | n | 0.000 | --+ | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| hour 12-18 PT | 185 | 423 | 0 | -0.012 | [-0.209, +0.200] | -0.029 | [-0.165, +0.101] | +0.012 | [-0.216, +0.263] | -0.008 | 0.551 | n | 0.000 | ++- | Y | fail: bh,dsr,wf,removed_ci |
| hour 18-24 PT | 132 | 476 | 0 | -0.014 | [-0.257, +0.233] | -0.027 | [-0.151, +0.097] | +0.011 | [-0.247, +0.267] | -0.010 | 0.541 | n | 0.000 | -++ | Y | fail: bh,dsr,wf,removed_ci |
| long & ADX<15 | 32 | 576 | 0 | -0.025 | [-0.425, +0.361] | -0.024 | [-0.141, +0.088] | -0.001 | [-0.434, +0.437] | -0.021 | 0.553 | n | 0.000 | ++- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |
| bbwidth low | 203 | 405 | 0 | -0.001 | [-0.164, +0.177] | -0.036 | [-0.185, +0.110] | +0.024 | [-0.179, +0.233] | -0.000 | 0.497 | n | 0.000 | -++ | Y | fail: bh,dsr,wf,removed_ci |
| bbwidth mid | 203 | 405 | 0 | -0.005 | [-0.197, +0.187] | -0.034 | [-0.170, +0.109] | +0.019 | [-0.210, +0.260] | -0.004 | 0.522 | n | 0.000 | --+ | Y | fail: bh,dsr,wf,removed_ci |
| bbwidth high | 202 | 406 | 0 | -0.067 | [-0.284, +0.143] | -0.003 | [-0.126, +0.123] | -0.043 | [-0.285, +0.203] | -0.042 | 0.736 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |

## H6 — 3 trials, 0 passing

| trial | n kept | n removed | n null | kept mean | kept CI | removed mean | removed CI | kept−all | diff CI | sharpe | p | BH | DSR | WF | min-n | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| confirmed_at_close | 401 | 207 | 0 | +0.004 | [-0.143, +0.146] | -0.078 | [-0.265, +0.117] | +0.028 | [-0.151, +0.214] | +0.002 | 0.474 | n | 0.000 | -++ | Y | fail: bh,dsr,wf,removed_ci |
| fire_minute<=2 | 78 | 530 | 0 | +0.124 | [-0.190, +0.427] | -0.046 | [-0.167, +0.070] | +0.148 | [-0.170, +0.471] | +0.091 | 0.214 | n | 0.000 | +++ | Y | fail: bh,dsr,removed_ci |
| fire_minute>=3 | 530 | 78 | 0 | -0.046 | [-0.167, +0.070] | +0.124 | [-0.190, +0.427] | -0.022 | [-0.187, +0.144] | -0.032 | 0.766 | n | 0.000 | -+- | Y | fail: bh,dsr,wf,removed_ci,kept_vs_all |

Selection rule (frozen): filters need removed mean < 0 with CI excl 0 AND kept mean > all-signal mean AND BH AND DSR > 0.95 AND WF 3/3 AND min-n; H1 cells need diff-vs-live CI > 0 AND BH AND DSR > 0.95 AND WF 3/3 AND min-n. Tie-break: highest DSR. p for filters = P(bootstrap kept mean ≤ 0); p for H1 = P(independent-resample diff cell−live ≤ 0). WF sign: filters = kept fold mean > 0; H1 = fold mean of (cell − live) > 0.
