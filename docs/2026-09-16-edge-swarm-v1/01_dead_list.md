# Phmex-S dead list — ground truth from the research record (compiled 9/14/2026, read-only)

Path shorthand: MEM = /Users/jonaspenaso/.claude/projects/-Users-jonaspenaso-Desktop/memory/ ; PROJ = /Users/jonaspenaso/Desktop/Phmex-S/
Sources read in full: every MEM/reference_*.md (43 files), every MEM/feedback_*.md (23 files), PROJ/memory/lessons.md (658 lines), PROJ/docs/2026-09-09-winddown.md, PROJ/TASKS.md.
Note: PROJ/TASKS.md is the 9/7 funding/fee-capture log + wind-down checklist; the "keep-or-cut" deep-dive receipts it references live only in the artifact "Phmex-S Keep or Cut" (winddown.md:3-4) — no local doc found (grep of docs/, reports/, TASKS.md). Every number below is copied from the cited file; nothing is computed here.

## A. KILLED / NULL / DO-NOT-BUILD

### A1. Strategy families (signals / books)
| # | Name | Date | Verdict | One-line reason | Source |
|---|---|---|---|---|---|
| 1 | OB-imbalance reversion (imbalance-alone) | 6/1, 6/13 | DEAD at size | Real signal (p≈1e-94) but gross ≈ +0.04%/trade vs breakeven RT fee 0.040%; taker 0/324 configs net-positive; realistic maker fills 0% | PROJ/memory/lessons.md:30; MEM/reference_edge_hunt_exhaustion.md:13 |
| 2 | Short-horizon reversion (alt-vs-ETH, high-vol) | 6/13 | DEAD | Gross-real but net regime-luck, walk-forward ~0/negative | MEM/reference_edge_hunt_exhaustion.md:14 |
| 3 | 1h vol-expansion fade | 6/13 | DEAD | OOS +0.26% on ONE split; full-sample −0.187%/t, Sharpe −2.45 (selection bias) | MEM/reference_edge_hunt_exhaustion.md:15 |
| 4 | Funding harvest (naked directional perp short) | 6/13, 6/29 | DEAD | "+0.65%/trade" was 91% price drift / 9% funding; price risk 8x funding; carry needs a spot hedge | MEM/reference_edge_hunt_exhaustion.md:16; MEM/reference_new_strategy_feasibility_2026-06-29.md:16 |
| 5 | Market-neutral cross-sectional momentum | 6/13, 6/29 | DEAD | Survivorship; short leg dead (t=−0.34); needs ~100-470-name book, collapses at 1-3 positions | MEM/reference_edge_hunt_exhaustion.md:17; MEM/reference_new_strategy_feasibility_2026-06-29.md:17 |
| 6 | Liquidation-cascade reversion | 6/13 | DEAD | Vol-fade with extra steps; high-vol bars CONTINUE, don't revert | MEM/reference_edge_hunt_exhaustion.md:23 |
| 7 | Calendar/microstructure (time-of-day, CME gap fill, funding pre-stamp dip, Saturday alt strength) | 6/13, 7/5, 7/6 | mostly NULL / decaying | Time-of-day noise after FDR; CME-gap backwards; Saturday edge decaying, 2026 YTD negative; weekend boost stat STALE | MEM/reference_edge_hunt_exhaustion.md:23; MEM/reference_weekday_pnl_2026-07-05.md:21-34; MEM/reference_r5_edge_search_2026-07-06.md:38-39 |
| 8 | Pairs / cointegration | 6/13 (#7) | DEAD | "Selection works" split-point-dependent; 96% of live-window Sharpe = ONE coin (SAND); honest Sharpe ~0.1-0.3 | MEM/reference_edge_hunt_exhaustion.md:28 |
| 9 | Book×tape absorption short = ST2.0 | 6/13→6/29 | DEAD / execution-trapped | Real signal, MAKER-ONLY; live 35 trades −$4.71 recorded / −$5.94 true, breakeven WR ~70.8% vs 43%; passive short-into-absorption adversely selected BY CONSTRUCTION; demoted to paper 6/29 | MEM/reference_st2_execution_research.md:12-16; MEM/reference_new_strategy_feasibility_2026-06-29.md:13 |
| 10 | Open-interest strategies | 6/29 | eliminated | No peer-reviewed single-instrument net-of-cost OI edge; NO historical OI data, ccxt can't backfill | MEM/reference_new_strategy_feasibility_2026-06-29.md:18 |
| 11 | Spot-perp basis / carry (delta-neutral) | 7/14 | DEAD at size | Spot fee flat 0.1%/side; best case $0.16/month ($1.88/yr) at $46 | MEM/reference_basis_carry_screen_2026-07-14.md:10-26 |
| 12 | 12-coin basket TSM (28d tercile) | 7/13 | DEAD | Deflated Sharpe 0.63 FAIL (dilution) | MEM/reference_btc_tsm_kill_test_2026-07-15.md:22; MEM/reference_nobarriers_search_2026-07-16.md:29-30 |
| 13 | BTC-TSM (28,5) | 7/15 | DO NOT BUILD | Deflated Sharpe 0.635 FAIL vs 0.95 bar; doesn't beat B&H; 2026 YTD −17% | MEM/reference_btc_tsm_kill_test_2026-07-15.md:12-26 |
| 14 | ETH-TSM-28 daily long-only | 7/6 built paper → killed 7/27 | KILLED (pre-registered line) | Scaling-rights probe (~$0.50-1.50/mo); killed by drift line | MEM/reference_r5_edge_search_2026-07-06.md:22-36; PROJ/memory/lessons.md:628 |
| 15 | Options / VRP income | 7/16 | OUT | Naive harvest −0.1%/yr; Deribit excludes US; revisit ~$25k+ via IBIT only | MEM/reference_nobarriers_search_2026-07-16.md:37-40 |
| 16 | Cross-venue funding arb | 7/16 | OUT at ≤$5k | Cheap venues geoblock US; 8/20 sim portfolios profitable net; no retail track record | MEM/reference_nobarriers_search_2026-07-16.md:41-45 |
| 17 | Market-making with rebates | 7/16 | OUT | No rebates below ~$100M/30d anywhere; passive fills lose pre-fee | MEM/reference_nobarriers_search_2026-07-16.md:46-47 |
| 18 | On-chain / intraday signals, ETF-flow timing, triangular arb, DEX-CEX arb, seasonality/halving/weekend | 7/16 | OUT | adj-R² ≤0.002; +73% gross → −64% net at 0.1% costs; triangular 0/4879 profitable | MEM/reference_nobarriers_search_2026-07-16.md:48-50 |
| 19 | Token-unlock short | 7/16 | LOW-MED, not a base strategy | Real drift but −86.6% max DD in only cost-inclusive replication | MEM/reference_nobarriers_search_2026-07-16.md:51-53 |
| 20 | Funding-spike carry playbook | 7/16 | ARM DON'T DEPLOY | Funding pays 4-11%/yr now (< T-bills); trigger = sustained >15-20% ann. | MEM/reference_nobarriers_search_2026-07-16.md:54-55 |
| 21 | Grid / DCA | 7/15 | DEAD w/ receipts | arXiv 2506.11921: E=0 before fees, negative after | MEM/reference_scale_research_2026-07-15.md:33 |
| 22 | Vol-selling on Phemex | 7/15 | DEAD | Phemex has ZERO options/dated futures | MEM/reference_scale_research_2026-07-15.md:34 |
| 23 | VWAP + 9/15 SMA cross (owner's manual setup) | 7/6 | CLOSED | Scan −0.263%/trade @37.7% WR, no gross drift; published edge = catalyst SELECTION not pattern | MEM/reference_vwap_sma_cross_2026-07-06.md:16-41 |
| 24 | Small-cap perps (<$10M vol) | 7/7 | NO-GO | Own history worst tier (−$0.090/t n=258); spread 0.25-2.3x the RT fee; depth $0-17K; keep $3M scanner floor | MEM/reference_smallcap_viability_2026-07-07.md:12-18 |
| 25 | S/R bounce (2-touch 1h pivot zones, 5m rejection) | 7/28 scan; live paper killed 7/30 | DO-NOT-BUILD / KILLED | Holdout 5,084 trades −$0.0705/t, gross NEGATIVE before fees (TP-hit ~29% vs 32.8% driftless breakeven); live n=50 −$0.79 KILL; 4h/15m, 4h/1h, 1d/1h all negative | MEM/reference_sr_bounce_scan_2026-07-28.md:20-32; MEM/reference_sr_bounce_lever_lab_2026-07-29.md:50-79 |
| 26 | htf_l2_anticipation (main scalper) | halted 7/13; main book → paper 8/26 | DEAD / demoted | 235 trades −$26.81; residual book with every known filter = breakeven (CI incl 0); "no evidenced path to positive expectancy"; main real −$70 lifetime | MEM/reference_htf_l2_diagnosis_2026-07-16.md:10,45; MEM/feedback_never_offer_dead_strategies.md:13 |
| 27 | htf_confluence_pullback | culled 5/2 | CULLED | n=18 WR 22.2% −$0.236/t; cluster entries = −$14.10 of −$14.47 | PROJ/memory/lessons.md:33,307-314 |
| 28 | momentum_continuation, htf_confluence_vwap, bb_mean_reversion (main router) | 4/26 | CULLED | −$0.40/t (n=11), −$0.10/t (n=5), 0 trades + "falling knives" incident | PROJ/memory/lessons.md:35,365 |
| 29 | 5m_narrow, 5m_liq_cascade slots | by 6/13 | KILLED | Listed as KILLED slots; both negative-drift walks (5m_narrow peak @#4) | PROJ/memory/lessons.md:29; MEM/reference_strategy_decay_analysis_2026-09-03.md:24-25 |
| 30 | 5m_mean_revert (live slot) | 9/4 NULL; demoted paper 9/8 | signal zero-EV | Pre-registered replay 6/1→9/3, 35 syms, 608 train: −$0.024/trade fill-all, 6 families/113 trials NULL; live +$4.62 came from maker-fill selection + hot July | MEM/reference_mr_edge_search_2026-09-04.md:20-42; PROJ/docs/2026-09-09-winddown.md:15 |
| 31 | MR-tuned universe (ranginess scanner) | 8/1 | DO-NOT-BUILD | Frequency 0.97x control (needed 1.5x); holdout quality reversed | MEM/reference_mr_universe_scan_2026-08-01.md:10-12 |
| 32 | VWAP_CROSS owner slot (paper) | 7/20 built | paper, negative-drift walk | Peak @#5, "never had a hot start worth the name"; no formal kill verdict in files read | MEM/reference_strategy_decay_analysis_2026-09-03.md:24-25 |
| 33 | BTC/ETH Donchian-ensemble trend (paper) | 7/16 | SURVIVOR on paper; owner DECLINED live 9/8 | Only OOS survivor (sidestepped bear); paper positions still in ledger at wind-down; MEMORY.md: "owner declined Donchian live — never re-offer" | MEM/reference_nobarriers_search_2026-07-16.md:14-34; PROJ/docs/2026-09-09-winddown.md:17 |
| 34 | Linear-vs-inverse funding spread | 7/15 | REAL — PARKED until ~$2K | +3.19%/yr BTC, +4.26%/yr ETH, 100% of 90d windows one-signed; $5.31-7.10/mo only at $2,000; direction = long linear + SHORT inverse (opposite BitMEX) | MEM/reference_funding_spread_phemex_2026-07-15.md:12-24 |

### A2. Levers / mechanisms on existing books
| # | Lever | Date | Verdict | Reason | Source |
|---|---|---|---|---|---|
| 35 | Entry-gate surgery (QUIET, TIME, OB-wall, whale) | 6/13 | NULL — leave alone | No gate separates W/L, every CI spans 0; owner: leave gate stack alone | MEM/reference_gate_quantify_2026-06-13.md:10-15 |
| 36 | ST2.0 trailing stop / active exit | 6/15, 6/22 | INERT | Trail never engages (max live ROI +1.8%); "problem is the SIGNAL" | MEM/reference_st2_exit_replay.md:16-27 |
| 37 | ST2.0 entry re-mine (342 cuts) | 6/29 | NULL | Family-wise permutation p=0.77 | MEM/reference_new_strategy_feasibility_2026-06-29.md:13 |
| 38 | Exit-geometry inventory: SL floor 0.9/0.8%, trail-to-BE@+3%, tight trail band 0.4%, AE threshold sweep −2..−6%, deep-red 2h cut, EARLY_EXIT_MIN_ROI 3→6, loss-cut sweep, hold-vs-cut, time-ratchet SL | ≤7/2 | ALL DEAD | Each rescues less than it clips; "inventory 100% COMPLETE" | MEM/reference_sl_loss_levers_2026-07-02.md:20-28; PROJ/memory/lessons.md:467-473 |
| 39 | Wider SL 1.5/2.0% | 7/6 | REFUTED | −41/−57% net June replay; one wider stop > daily halt at $15 | MEM/reference_overnight_sweep_2026-07-06.md:19-20 |
| 40 | Partial-TP thresholds (6/10/12) and fractions (75/25) | 7/6 | NULL | All inside rig error | MEM/reference_overnight_sweep_2026-07-06.md:21-23 |
| 41 | Restricted adverse-exit (by symbol/regime/trend+vol) | 7/6 | DEAD in all 4 forms | "EXIT-SIDE INVENTORY IS NOW UNCONDITIONALLY EXHAUSTED" | MEM/reference_r2_research_2026-07-06.md:13-17 |
| 42 | Lower trail arm (+3%/+4%) | 7/2 | wash | Rescues ≈ clips | MEM/reference_sl_loss_levers_2026-07-02.md:17 |
| 43 | Trail arm 5%→8% | 7/3 replay +, 7/5 live forward test | only positive exit lever, inside model error | +$2.45 net but net minus top-2 = −$0.49 | MEM/reference_sl_loss_levers_2026-07-02.md:32-33 |
| 44 | A+ entry mining (~40 hypotheses, main) | 7/6 | NULL | Holdout + deflation; RSI floor on main structural null (0/87 longs) | MEM/reference_overnight_sweep_2026-07-06.md:24-25 |
| 45 | Queue-conditioned posting gate | 7/3, 7/6 | NULL on our data | Queue size predicts FILL PROBABILITY not toxicity; 20s cancel already an implicit queue filter | MEM/reference_fill_rate_research_2026-07-03.md:35-36; MEM/reference_overnight_sweep_2026-07-06.md:26-30 |
| 46 | Pre-fill toxicity cancel rule | 7/2 | NULL / undetectable | Tape dead before fills; "best" rule cancels 10/12 of ALL fills | MEM/reference_main_missed_fills_2026-07-02.md:21 |
| 47 | Main-bot maker re-quote port | 7/2 | NOT justified | 100 misses ≈ breakeven raw, −$4.04 bias-corrected | MEM/reference_main_missed_fills_2026-07-02.md:10-18 |
| 48 | Maker exits (fee lever) | 7/6 | DEAD | Patient maker exits live since 6/12: 0/13 fills; early_exit patience = negative EV | MEM/reference_r5_edge_search_2026-07-06.md:12-20 |
| 49 | Taker entries for MR / taker switching | 7/6, 7/14 | DEAD | MR maker +$7.83 vs taker −$24.22 (n=309); needs ~1bp, Phemex 6bp/leg | MEM/reference_mr_overnight_program_2026-07-14.md:17-18; MEM/reference_overnight_sweep_2026-07-06.md:31 |
| 50 | MR signal loosening (ADX 30→35, AND→OR, looser long RSI) | 7/14 | DEAD | ADX adds trades at −$0.265/t CI excl 0 | MEM/reference_mr_overnight_program_2026-07-14.md:19-21 |
| 51 | MR rest extension 60-300s + 2nd requote | 7/14 | CLOSED | Marginal-fill expectancy decays; misses convert zero; prior "misses were winners" partly placement artifact | MEM/reference_mr_overnight_program_2026-07-14.md:22-26 |
| 52 | MR OB-imbalance gate removal | 7/14 | REFUTED — gate STAYS | Vacuous CI, p=0.0625; H0 re-run at n≥10 pending, never executed | MEM/reference_mr_overnight_program_2026-07-14.md:27-31; MEM/reference_mr_deep_dive_2026-09-03.md:25 |
| 53 | MR H1 anchor-requote-at-band | 7/14 | refuted | Anchoring = resting longer = converts ~zero | MEM/reference_mr_overnight_program_2026-07-14.md:32-33 |
| 54 | MR H3 turn-of-15m-candle | 7/14 | NULL (recheck at 60-80 trades) | Replay null, real-money n=6 | MEM/reference_mr_overnight_program_2026-07-14.md:34-35 |
| 55 | V17 MR_SHORT_RSI_MIN 70→65 | 7/15 | DO NOT ARM (owner) | Diff-CI straddles 0, double selection bias, loosens shorts | MEM/reference_overnight_mr_program_2026-07-14.md:23-37 |
| 56 | MR symbol curation / blacklist | 7/14 | data only, no proposal | Selection-biased; BTC do-not-blacklist directive | MEM/reference_mr_overnight_program_2026-07-14.md:38-41 |
| 57 | MR trend-day fuse | 8/1 | NULL, closed | Prevents 0 trades / $0.00 | MEM/reference_mr_ledger_trio_2026-08-01.md:10 |
| 58 | MR timeout entry filter | 8/1 | NULL at this n | 36 tests, zero survive; timeouts are +$0.20 net | MEM/reference_mr_ledger_trio_2026-08-01.md:11 |
| 59 | MR H1 geometry (79 cells), H2 1h-ADX cap, H3 buy_ratio short skip, H4 funding, H5 22 buckets, H6 entry timing / closed-bar confirmation | 9/4 | ALL NULL | BH over 113 p-values min p 0.15; ADX-cap removes POSITIVE cohorts | MEM/reference_mr_edge_search_2026-09-04.md:23-32 |
| 60 | htf_l2 L2-confirmation strength tuning (13 tests) | 7/17 | noise, zero survivors | "Do NOT tune L2 thresholds — nothing to tune" | MEM/reference_htf_l2_signal_rnd_2026-07-17.md:12 |
| 61 | htf_l2 anticipation → confirmation-close timing | 7/17 | don't ship | Timing is a 3-6 bps drag, no change clears its CI | MEM/reference_htf_l2_signal_rnd_2026-07-17.md:14 |
| 62 | htf_l2 entry-feature mining (RSI/EMA/VWAP/ATR stretch, 144 tests) | 7/18 | NO deployable filter | All fail family-wise placebo (p=0.495) | MEM/reference_htf_l2_entry_features_2026-07-18.md:10-15 |
| 63 | VWAP(5m+15m) + 9/15 SMA filter on htf_l2 | 7/20 | REJECTED | VWAP legs no-op; alignment HARMS residual book CI-excluding | MEM/reference_htf_l2_vwap_sma_filter_2026-07-20.md:12-18 |
| 64 | htf_l2 geometry redesign (240-config sweep) | 7/18-27 | 0/240 reach WR≥68 | trade-off measured | PROJ/memory/lessons.md:628 |
| 65 | Ensemble 4/7 confidence gate | 7/17 | DEAD WEIGHT | Structurally cannot fire; confidence score zero predictive power | MEM/reference_htf_l2_diagnosis_2026-07-16.md:49; PROJ/memory/lessons.md:314 |
| 66 | 1h EMA direction gate | 4/9 | useless | 98% of entries already align; AEs happen WITHIN trend | PROJ/memory/lessons.md:313 |
| 67 | Hour-of-day / pullback hour-bleed gate / day-of-week / tilt / same-symbol re-entry | 5/2, 7/2, 7/5 | NULL / stale | Bleed-hour set inverted on current data; worst hour Bonferroni p=0.48; no tilt | PROJ/memory/lessons.md:483-487; MEM/reference_losing_trades_audit_2026-07-02.md:17 |
| 68 | Streak-halting logic | 7/5 | NULL | Payoff asymmetry + chance, big losses ANTI-cluster | MEM/reference_streak_analysis_2026-07-05.md:16-35 |
| 69 | SR_BOUNCE levers L1-L5 (zone cooldown, risk floor, touch count, loss-day blacklist) + L2 snapshot mining (10 features) + I3 fill revalidation | 7/29, 7/30, 8/4, 8/24 | NONE positive / ALL NULL / FAIL x2 | Best combo −$0.064/t; I3 strict fills flip +$2.62 → −$1.49 (edge inverts) | MEM/reference_sr_bounce_lever_lab_2026-07-29.md:14-26,70-76; MEM/reference_sr_bounce_i3_fill_reval_2026-08-04.md:55-73 |
| 70 | Venue migration | 7/6 | DEAD | Phemex already cheapest maker of 6; Hyperliquid −10.8% RT vs 30% bar | MEM/reference_r2_research_2026-07-06.md:22-23 |
| 71 | Fee tiers / referral fee-back | 7/6, 7/15 | unreachable | VIP1 ≥$8M 30d volume; referral impossible on existing account | MEM/reference_r2_research_2026-07-06.md:20-26; MEM/reference_scale_research_2026-07-15.md:36-37 |
| 72 | Faster OB polling / streaming order book | 7/6 | owner declined | Book state measured null for outcomes twice | MEM/reference_r2_research_2026-07-06.md:49-53 |
| 73 | Phemex order-replace queue-position probe | 7/6 | owner declined, UNTESTED | Only beneficiary is slot re-quote leg | MEM/reference_overnight_sweep_2026-07-06.md:44-48 |
| 74 | "Strategies start strong then decay" hypothesis | 9/3 | NOT supported | Artifact = size-up at curve peaks + negative-drift walks peaking early | MEM/reference_strategy_decay_analysis_2026-09-03.md:16-32 |
| 75 | Agent layers (fund manager / trader agent) | 4/8 | rejected as premature | "governance without edge is theater" | PROJ/memory/lessons.md:245-250 |
| 76 | Multi-day mean reversion, 21-23 UTC overnight window, vol-scaling-as-rescue | 7/6 | dead post-2022 | verified by web sweep | MEM/reference_r5_edge_search_2026-07-06.md:38-39 |

## B. STRUCTURAL CONSTRAINTS (from the record)

Fees
- Phemex perp maker 0.01% / taker 0.06% confirmed; real round-trip = maker entry 0.01% + taker exit 0.06% (ETH 9/4 example); bot's in-memory estimate ~0.066% RT within $0.01 at $15 margin. MEM/reference_r2_research_2026-07-06.md:20; MEM/reference_phemex_fees_funding_api_2026-09-07.md:17.
- "Scalping is fee-trapped (0.066% RT kills sub-0.1% moves)"; Phemex has NO retail maker rebate (best maker→0% at $380M vol). MEM/reference_edge_hunt_exhaustion.md:19.
- 12 bps RT taker was the "new edge" screening cost. MEM/reference_new_strategy_feasibility_2026-06-29.md:15.
- Spot fee flat 0.1% maker AND taker (kills spot legs). MEM/reference_basis_carry_screen_2026-07-14.md:17-19.
- No fee tier reachable ($50K assets / $8M volume; VIP1 ≥$8M 30d). MEM/reference_r2_research_2026-07-06.md:20-21; MEM/reference_scale_research_2026-07-15.md:36.
- Only fee lever: PT-token toggle −10% (owner manual action, still open at 7/15). MEM/reference_r2_research_2026-07-06.md:24-25; MEM/reference_scale_research_2026-07-15.md:37.
- Paper sims charge 0.12% RT, deliberately ~2x live. MEM/reference_htf_l2_diagnosis_2026-07-16.md:53.
- Early-era: fees were 63% of total loss (Mar 31→Apr 7). PROJ/memory/lessons.md:232.
- Fees = 35% of live MR gross ($2.50 on $7.12). MEM/reference_mr_deep_dive_2026-09-03.md:26.

Maker fills / execution
- Main-bot PostOnly entry fill rate 25.4% (138 attempts Jun 18–Jul 2). MEM/reference_main_missed_fills_2026-07-02.md:12.
- ST2.0 real maker fill 41.5%; symbol-uneven (ETH ~59%, BTC ~30%, ENA ~20%). MEM/reference_st2_execution_research.md:12.
- MR order-stage fill ~36% (first attempt 4/9, re-quote 2/8); MR structural ceiling "~2.6 signals/day × 72% gate block × ~8% maker conversion". MEM/reference_mr_deep_dive_2026-09-03.md:31; MEM/reference_overnight_mr_program_2026-07-14.md:20-21.
- Exit maker fills: 0/13 since 6/20 (every attempt → market fallback); 81% of exits taker. MEM/reference_r5_edge_search_2026-07-06.md:14-15; MEM/reference_r2_research_2026-07-06.md:31.
- Bot already does 98.9% maker entries. MEM/reference_edge_hunt_exhaustion.md:31.
- "The main bot's PostOnly-20s design is empirically near-optimal at this scale." MEM/reference_fill_rate_research_2026-07-03.md:35.
- Fill-rate vs adverse selection is STRUCTURAL: "our −4.5bps is a property of passive orders, 'not a fixable execution bug.'" MEM/reference_fill_rate_research_2026-07-03.md:13.
- Never post inside the spread. MEM/reference_fill_rate_research_2026-07-03.md:23,30.
- Simulated fills are "very poor proxies" for real executions — every fill replay is screening-grade. MEM/reference_mr_overnight_program_2026-07-14.md:57-58.

Entry drift / adverse selection
- htf_l2: −4.50 bps 1m post-fill drift on 148 fills, CIs exclude 0. MEM/reference_htf_l2_diagnosis_2026-07-16.md:27.
- ST2.0: mean +3.23 bps ADVERSE 30s post-fill; losers +6.03 vs winners +1.97. MEM/reference_st2_postfill_drift.md:15-16.
- Drift watchdog 14d reading −5.33 bps@1m vs −4.5 baseline. MEM/reference_overnight_sweep_2026-07-06.md:43.
- SR_BOUNCE paper: missed trades avg +$0.338 vs fills +$0.211 — "same pattern that killed ST2.0". MEM/reference_sr_bounce_i3_fill_reval_2026-08-04.md:24-25.

Halt math / sizing
- Full SL at $15 margin = −$2.00 mean (n=12); empirical full stop −13.66% of margin (n=21) → −$2.05 @$15 vs halt budget $1.72. MEM/reference_scale_research_2026-07-15.md:44; MEM/reference_r2_research_2026-07-06.md:39.
- Balance thresholds to survive stops under the 3% halt: 1 stop clears @$68, 2 @$137, 3 @$205; 3% overtakes the $5 floor at $166.67. MEM/reference_r2_research_2026-07-06.md:40; MEM/reference_scale_research_2026-07-15.md:43.
- "Halt math breaks proportional scaling": halt-consistent (2 SLs) sizes ~$28 @$250, ~$56 @$500. MEM/reference_scale_research_2026-07-15.md:41-43.
- At $15-reaching sizing ~32% of days would trip the halt. MEM/reference_r2_research_2026-07-06.md:35.
- Each SL ≈ −$1.98 at $15; 2 overlapping SLs ≈ −$4. MEM/reference_streak_analysis_2026-07-05.md:33-34.
- Never size up at a high-water mark (5m_MR $15→$30 at #38, one trade before all-time peak). MEM/reference_strategy_decay_analysis_2026-09-03.md:20-22,34.

Lot minimums / instrument fit
- ETH 0.01 ≈ $17.71 notional fits the halt math; BTC 0.001 step risks $5 = 3x halt — "NEVER at this balance". MEM/reference_r5_edge_search_2026-07-06.md:27-30.
- Winddown reopen condition: "Account ≈ $500+ → exchange minimums stop distorting sizing." PROJ/docs/2026-09-09-winddown.md:44.
- Fill realism at scale: at $561/order resting order exceeds thin-side top-of-book on 8/15 MR symbols; honest ceiling ~$300-600/order on thin names, deep majors only. MEM/reference_scale_research_2026-07-15.md:45-48.
- Only 19 Phemex USDT perps clear the $3M volume floor. MEM/reference_mr_universe_scan_2026-08-01.md:10.

Balance thresholds in the record
- ~$170 unblocks BTC-TSM halt math (signal still dead). MEM/reference_scale_research_2026-07-15.md:17-18.
- ~$2K+ for linear-vs-inverse funding spread. MEM/reference_funding_spread_phemex_2026-07-15.md:12,24.
- "At $41 nothing is reachable; credible strategies start ~$500-5k." MEM/reference_nobarriers_search_2026-07-16.md:60-61.
- Options ~$25k+; cross-venue arb NOT at ≤$5k. MEM/reference_nobarriers_search_2026-07-16.md:39,45.
- "capital buys NO new edge — every class that died at $46 died on edge/structure, not size." MEM/reference_scale_research_2026-07-15.md:13.

Backtest-artifact warnings
- "backtesting this data ... reliably produces ARTIFACTS ... The only reliable adjudicator left is FORWARD testing." MEM/reference_edge_hunt_exhaustion.md:21.
- Backtester pessimistic without gates (2.7x trades, 6.6x worse PnL) — "relative comparisons only". PROJ/memory/lessons.md:316-321.
- Live MR fires on the FORMING 5m candle; closed-bar replays reproduce only ~40% of real entries — ALL prior MR replays population-mismatched; any slot reading df.iloc[-1] must model the forming bar. MEM/reference_mr_forming_bar_signals_2026-09-03.md:11-30.
- Paper slots opened at stale cached prices until 8/5 fix; pre-8/5 paper rows flattered. MEM/reference_sr_bounce_i3_fill_reval_2026-08-04.md:29-43.
- MFE "never reached +1%" was a 30-min checkpoint mislabel; two DOA studies wrong in opposite directions. MEM/reference_sl_loss_levers_2026-07-02.md:12; MEM/reference_htf_l2_diagnosis_2026-07-16.md:41.
- Agent impact estimates without bar-by-bar replay are "vibes"; exit sims must capture both saved AND clipped. PROJ/memory/lessons.md:392-398.
- Shadow/paper data "repeatedly failed to predict live at this scale." MEM/feedback_no_shadow_live_deploy.md:12.

Data / API
- Phemex fill history floor ≈ 40 days; older rows can never be fee/funding-reconciled from the API. MEM/reference_phemex_fees_funding_api_2026-09-07.md:16.
- Funding sign: amount positive = PAID; funding rows interleaved in fetch_my_trades (tradeType "4"). MEM/reference_phemex_fees_funding_api_2026-09-07.md:13-15.
- L2 ticks recorded ONLY for BTC/ETH/INJ/ARB. MEM/reference_st2_postfill_drift.md:12.
- Bot-collected flow_capture only since 5/11/2026; multi-year OHLCV is downloaded public data, not Phemex. MEM/feedback_sum_all_state_files.md:17.
- No historical OI; ccxt phemex can't backfill it. MEM/reference_new_strategy_feasibility_2026-06-29.md:18.
- 1.97 GB market-data archive (l2_ticks, flow_capture, entry_snapshots, gotAway, shadow_adverse) kept at wind-down. PROJ/docs/2026-09-09-winddown.md:22.
- macOS sleep suspends the whole bot; only exchange-resting SL/TP survive. MEM/feedback_host_sleep_suspends_bot.md:10-18.

Account state at wind-down
- Lifetime recorded −$82.94 on 882 trades, 48.3% WR (316 early rows fee-blind; de-dup estimate ≈ −$107); last 90d −$22.41; balance $87.12; no live books. PROJ/docs/2026-09-09-winddown.md:11-15.
- Base rates: ~14-18% of perp traders profitable; audited HLP 10-25% APR = hurdle rate. MEM/reference_nobarriers_search_2026-07-16.md:58-60.

## C. OWNER DIRECTIVES THAT CONSTRAIN PROPOSALS
- Do NOT blacklist/cut BTC from the scanner (settled 6/30). MEM/feedback_do_not_blacklist_btc.md.
- No shadow logs / paper-confirm as validation; every change = small, flag-gated, reversible LIVE deploy judged on real closed PnL (6/30). MEM/feedback_no_shadow_live_deploy.md.
- Never list re-arming a demoted/killed book (main live, ST2.0, BTC blacklist, gate loosening, anything under "don't re-propose") as an option, even hedged — say nothing can be done and stop (9/3). MEM/feedback_never_offer_dead_strategies.md; PROJ/memory/lessons.md:643-648.
- Once Jonas orders, execute; only the pre-restart-audit "say go" gate remains. MEM/feedback_dont_overask_after_decision.md.
- Plain English, verdict first, no fluff/tables/headers unless comparing data. MEM/feedback_plain_english.md. Stop diagnosing once root cause is clear. MEM/feedback_diagnostic_brevity.md.
- Never fabricate; verify every number/citation in the first pass; verify behavioral claims against current state; sum ALL trading_state*.json; correct bootstrap diff-CI. MEM/feedback_never_fabricate.md; MEM/feedback_verify_everything.md; MEM/feedback_verify_behavioral_claims.md; MEM/feedback_sum_all_state_files.md; MEM/feedback_bootstrap_diff_ci.md.
- V17 (MR short RSI 65): "DO NOT ARM. Leave everything as is." (7/15). MEM/reference_overnight_mr_program_2026-07-14.md:36-37.
- Leave the main-bot gate stack alone (6/13). MEM/reference_gate_quantify_2026-06-13.md:15.
- Keep OB snapshot at 60s; NO streaming order book (7/6). MEM/reference_r2_research_2026-07-06.md:49-53.
- Order-replace queue probe declined (7/6). MEM/reference_overnight_sweep_2026-07-06.md:44-48.
- Keep $3M scanner floor; no small-cap slot. MEM/reference_smallcap_viability_2026-07-07.md:18.
- No universe swaps for 5m_MR without a new mechanism. MEM/reference_mr_universe_scan_2026-08-01.md:12.
- SR_BOUNCE: no live promotion before a fresh honest-era I3 pass (8/6). MEM/reference_sr_bounce_i3_fill_reval_2026-08-04.md:49-53.
- Owner pivot 6/29: "make the EXISTING bot profitable" over building new strategies; do NOT re-run funding/XS/OI hunt. MEM/reference_new_strategy_feasibility_2026-06-29.md:20.
- 8/12: main longs BLOCKED (shorts-only); 8/26 main → paper; 9/8 5m_MR → paper; 9/9 wind-down; Donchian live declined — never re-offer. PROJ/docs/2026-09-09-winddown.md:15; MEMORY.md index (Phmex-S wound down entry).
- Reopen conditions are the owner's stated bar: an owner idea NOT on the dead list → pre-registered paper slot; ≈$500+ for sizing; ≈$2,000+ for funding spread. PROJ/docs/2026-09-09-winddown.md:41-45.
- Host must stay on AC (sleep suspends the bot). MEM/feedback_host_sleep_suspends_bot.md:17.
- Don't re-propose Tailscale. MEM/reference_tailscale_dashboard.md:15.
- Historical (pre-6/30, superseded by no-shadow rule): "don't redeploy live without simulated positive edge over 90 days OHLCV" (5/1). PROJ/memory/lessons.md:451.

## D. WHAT WAS NEVER TESTED (strict: searched, no verdict found)

Untested mechanisms (no verdict in any file read):
- S/R rejection with TAKER/market entry at the rejection close — explicitly "NOT tested ... the unfilled-signal population is unmeasured". MEM/reference_sr_bounce_scan_2026-07-28.md:47-49.
- Volume-profile levels, prior-session levels, breakout mode (S/R family), wider touch requirements — explicitly untested; any retry needs its own prereg + DOA line. MEM/reference_sr_bounce_scan_2026-07-28.md:49-51; lever lab says the family "requires a genuinely NEW mechanism (volume-profile levels, breakout mode)". MEM/reference_sr_bounce_lever_lab_2026-07-29.md:61-63.
- SR_BOUNCE shorts-only slice and 5m trend-direction gate — untested, judged "not worth it without new mechanism". MEM/reference_sr_bounce_lever_lab_2026-07-29.md:45-47.
- MR H2 "post deeper than band" — parked, live-only A/B, not built. LimitIfTouched (PostOnly-on-trigger) entries — downgraded, not tested. MEM/reference_mr_overnight_program_2026-07-14.md:59-60.
- Catalyst / "stocks in play"-style event selection as the entry mechanism — the record says the published VWAP-pattern edge lives in selection, not the pattern, but no catalyst-selection mechanism was ever built or scanned. MEM/reference_vwap_sma_cross_2026-07-06.md:26-29.
- ST2.0 forward-confirm entry gates: wait-for-OFI-rollover, crumbling-bid, post-entry-cancel — HELD/parked, never calibrated; trade_count<=80 and large_trade_bias>=0.10 were wired to accrue forward-only, no verdict recorded before the 6/29 demotion. MEM/reference_st2_postfill_drift.md:21,23; MEM/reference_st2_execution_research.md:18.
- Toxicity gating (LightGBM-style predicted-toxic seconds) — "needs training data we don't have at n≈50 fills"; bucket model (time-of-day × queue-imbalance) and imbalance-conditioned stay/cancel — UNVERIFIED leads, verification votes limit-killed. MEM/reference_fill_rate_research_2026-07-03.md:20-25.
- Phemex order-replace preserving queue position — UNTESTED (owner declined the probe). MEM/reference_overnight_sweep_2026-07-06.md:44-48. Phemex amend-preserves-queue: "officially undocumented, assume NO." MEM/reference_mr_overnight_program_2026-07-14.md:36-37.
- Spot-trade permission of the API key — never tested with a live order. MEM/reference_basis_carry_screen_2026-07-14.md:33-34.
- Token-unlock short as a tiny fixed-size experiment — not built. MEM/reference_nobarriers_search_2026-07-16.md:51-53.
- Halt formula max(3%×balance, $2.25) — recommended, NOT implemented. MEM/reference_r2_research_2026-07-06.md:43-44. Size-up rule gated on n-since-last-size-change — proposal only, owner not asked. MEM/reference_strategy_decay_analysis_2026-09-03.md:34-35.
- Forming-bar behavior of SR_BOUNCE / VWAP_CROSS / ST2.0 replays — "likely share the pattern — unverified". MEM/reference_mr_forming_bar_signals_2026-09-03.md:29-30.
- Per-pair AE trigger type (trend-flip for alts, ROI for BTC) — flagged 4/9 as "promising research direction", never run; note the AE feature itself is dead at every threshold and in all 4 restricted forms, so this is a variant of a dead family. PROJ/memory/lessons.md:326-327; MEM/reference_r2_research_2026-07-06.md:13-17.
- Any ML/learned model on our own fills — nothing in the record beyond the data-starved LightGBM note above.
- Inverse (coin-margined) perps as a traded instrument — only analysed for the funding spread; never traded. MEM/reference_funding_spread_phemex_2026-07-15.md.

Tested and PARKED pending a threshold or more data (do not confuse with untested):
- Linear-vs-inverse funding spread → ~$2K+. MEM/reference_funding_spread_phemex_2026-07-15.md:12.
- Spot-perp carry → "materially larger balance". MEM/reference_basis_carry_screen_2026-07-14.md:32-33.
- Options/VRP → ~$25k+ via IBIT; cross-venue arb → >$5k + non-US venue access. MEM/reference_nobarriers_search_2026-07-16.md:39,45.
- Funding-spike carry → trigger sustained >15-20% ann. funding. MEM/reference_nobarriers_search_2026-07-16.md:54-55.
- MR OB-imbalance gate counterfactual (H0) → n≥10 imbalance episodes via archiver (never executed). MEM/reference_mr_edge_search_2026-09-04.md:44; MEM/reference_mr_deep_dive_2026-09-03.md:25.
- MR H3 candle-turn → 60-80 real closed trades. MEM/reference_mr_overnight_program_2026-07-14.md:34-35.
- MR timeout filter → ~10 live timeouts, spread_pct only. MEM/reference_mr_ledger_trio_2026-08-01.md:11.
- mr_long_side KILL line (next 8 live longs) → unresolved, 1 long in 24 days. MEM/reference_mr_deep_dive_2026-09-03.md:28.
- htf_l2 VWAP>4ATR watch hypothesis → n≥30 paper trades (n=14 not supported). MEM/reference_htf_l2_entry_features_2026-07-18.md:14; MEM/reference_htf_l2_loss_audit_2026-07-23.md:23.
- SR_BOUNCE I3 re-run → after tick-recorder extension + ~15-20 more trades. MEM/reference_sr_bounce_i3_fill_reval_2026-08-04.md:73-75.
- Prefill-toxicity study → rerun in ~a month for power (frozen at n=12 while halted). MEM/reference_main_missed_fills_2026-07-02.md:21; MEM/reference_htf_l2_diagnosis_2026-07-16.md:53.
- 5m_MR holdout 8/4→9/3 (n=227) UNREAD — reserved for ONE future pre-registered family. MEM/reference_mr_edge_search_2026-09-04.md:32,44.
- Donchian BTC/ETH paper slot: kill lines registered (paper net ≤ −$15, 90d review); paper verdict not recorded in the files read; owner declined live. MEM/reference_nobarriers_search_2026-07-16.md:30-33.
- Trail-arm 8% live forward test (review @~20 trail trades) — no verdict in files read. MEM/reference_sl_loss_levers_2026-07-02.md:33.

Covered (do NOT treat as untested): higher timeframes (daily TSM, 4h/1h/1d S/R, Donchian, multi-day MR), time-of-day/day-of-week, tape/OB confirmation, queue-state gating, rest duration, taker vs maker, exit geometry (100% inventory), universe swaps, small caps, other venues, funding/XS/OI, pairs, grid/DCA, options.

## E. WHY THINGS DIE AT THIS SIZE — the record's own words
- Execution, not signal: "The edge question has collapsed to ONE execution question: can the bot get passive (maker) fills on a short-into-absorption entry?" MEM/reference_edge_hunt_exhaustion.md:31. "passive execution of a short-reversion signal, small size, slow, no rebate is structurally adverse with no available compensation at this scale." MEM/reference_st2_execution_research.md:16.
- Missing structure: "At this account scale every real edge needs something structural we don't have (spot hedge / broad book / speed-queue). Backtesting our data produces artifacts; the lab/loop FILTERS edge, doesn't CREATE it." MEM/reference_new_strategy_feasibility_2026-06-29.md:20.
- Adverse selection is inherent: fill-rate vs toxicity "is STRUCTURAL"; "Raising fill rate naively = buying more toxicity"; fills happen "into QUIETER tape than misses — the adverse selection is the PATIENT kind." MEM/reference_fill_rate_research_2026-07-03.md:13; MEM/reference_main_missed_fills_2026-07-02.md:21. "At this scale the fill issue has no further code-level solution." MEM/reference_main_missed_fills_2026-07-02.md:22.
- Winners are the misses: "Missed trades avg +$0.338 vs +$0.211 for fills — same pattern that killed ST2.0." MEM/reference_sr_bounce_i3_fill_reval_2026-08-04.md:24-25. MR's live gain "came from the ~27% maker-fill selection (structural, documented) plus a hot July, not from a signal edge." MEM/reference_mr_edge_search_2026-09-04.md:41-42.
- Fee trap: "Scalping is fee-trapped (0.066% RT kills sub-0.1% moves)." MEM/reference_edge_hunt_exhaustion.md:19. But not always the binder: "fees were never the binding constraint, the signal is." MEM/reference_sr_bounce_lever_lab_2026-07-29.md:60-61.
- Losses are the receipt for entries: "the SL bucket is the receipt for entry adverse selection." MEM/reference_sl_loss_levers_2026-07-02.md:10. "Death by hundreds of small fee-inclusive losses = the documented adverse-selection+fees story." MEM/reference_losing_trades_audit_2026-07-02.md:16. "no gate separates winners/losers at available power." MEM/reference_htf_l2_diagnosis_2026-07-16.md:27.
- Payoff asymmetry + size: "avg win $0.46 vs avg loss −$0.85; median loss erases 3.46 median wins ... ~6-8 wins build $2.50-3.50; 2 SLs erase it." MEM/reference_streak_analysis_2026-07-05.md:17-20. ST2.0 "breakeven WR ~70.8% ... loss asymmetry is the killer." MEM/reference_new_strategy_feasibility_2026-06-29.md:13.
- Halt math caps sizing: "ONE full SL (−$10.89) > the $7.50 halt → day over on first stop." MEM/reference_scale_research_2026-07-15.md:41-42. "one full SL at $15 (~$1.98) now trips the 3% daily halt (~$1.87 at $62 balance)." PROJ/memory/lessons.md:609.
- Backtests lie here: "The better a backtest headline looks, the more suspicious it should make you." MEM/reference_edge_hunt_exhaustion.md:21. Live MR "fires on the FORMING 5m candle" so every replay tested a different population. MEM/reference_mr_forming_bar_signals_2026-09-03.md:11-26. Paper "does not perform well when it goes live." MEM/feedback_no_shadow_live_deploy.md:10.
- Hot starts are artifacts: "Promotion / size-up timing IS the artifact" and "Negative-drift random walks peak early." MEM/reference_strategy_decay_analysis_2026-09-03.md:20-25.
- Toxic entry profile for the scalper: "extended 1h trend on a dead tape" (thin-tape ∧ ADX≥35 = 99% of July loss). MEM/reference_htf_l2_diagnosis_2026-07-16.md:47. Earlier: "All-shorts-in-up-market ... gates can't fix wrong direction"; correlated cluster entries "all symbols lose together." PROJ/memory/lessons.md:174-178,307-310.
- Capital doesn't rescue it: "capital buys NO new edge — every class that died at $46 died on edge/structure, not size." MEM/reference_scale_research_2026-07-15.md:13. "At $41 nothing is reachable; credible strategies start ~$500-5k." MEM/reference_nobarriers_search_2026-07-16.md:60.
- Operational leaks: cross-book balance contention on ~$34 shared margin ("entry-timing lottery"); macOS sleep round-tripped a +7% winner to −$1.42; regime pause froze the live slot on PAPER losses. MEM/reference_htf_l2_loss_audit_2026-07-23.md:17; MEM/feedback_host_sleep_suspends_bot.md:12; PROJ/memory/lessons.md:650-655.
- The wind-down summary: "nothing at this size survived: ~40 killed families, fee trap 0.07% RT, exit maker fill 0%, entry drift −4.5 bps by construction, halt math caps sizing, backtests produce artifacts." PROJ/docs/2026-09-09-winddown.md:47.
