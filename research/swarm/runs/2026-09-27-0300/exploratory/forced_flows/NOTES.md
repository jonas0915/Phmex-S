# forced_flows lens notes — run 2026-09-27-0300 (EXPLORATORY; not evidence)
Web: 9 WebSearch calls, 9 WebFetch attempts (3 returned HTTP 403: two ScienceDirect, one SSRN; 1 paywalled: tradingresearchub; roguequant preview had no usable stats). Budget not exhausted.
Opened and cited: NY Fed SR150 (Osler) PDF; ideas.repec Han 2024 JBEF abstract; Glassnode liquidation-heatmaps page; arxiv 2607.27070 opened (no post-cascade price stats; not cited).
Probes (all on long_1h TRAIN via load_data, every variant listed in each script docstring):
- probe_round_cross.py / probe_round_cross_1sf.py: round-number crossing continuation -> NULL vs placebo grid; round-number idea dropped.
- probe_sweep_reclaim.py: sweep-fade N in {24,72} + breakout-hold control.
- probe_sweep_breakdown.py: per-symbol / per-month / de-overlapped; ALSO read load_funding(era='train') which is mr_edge-anchored (2026-06..08) -> thesis registered on mr_edge, not long_1h (STANDARDS #6).
- probe_sweep_frequency.py: trade counts, causality_check, lot_check, p_star at the registered spec (PnL not printed).
Thesis: theses/forced_flows_stop_sweep_exhaustion_fade.json. Second slot unused (round-number continuation refuted by own probe; no other forced-flow mechanism with a real source and data the bot has).
