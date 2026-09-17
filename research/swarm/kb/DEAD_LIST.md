# DEAD_LIST — killed / null / do-not-build (append-only, cite by row)

Row format (machine-checked by `kb_check.dead_rows`): `| n | family | one-line why dead | source | date |`.
Row numbers are unique and strictly ascending. A thesis's pre-reg must cite its nearest row(s) by number.
This file is a FILTER for rejecting relabels of things this account already killed — it is never a source of ideas (STANDARDS.md #2).

Rows 1-76 transcribe `docs/2026-09-16-edge-swarm-v1/01_dead_list.md` A1 (strategy families) + A2 (levers on existing books) verbatim, in original order.
Rows 77-84 are the 8 v1 swarm-session candidates (5 internal backtests + 3 internet-sourced ideas) that were vetted and refuted before this desk existed.
Rows 85-103 are killed sub-mechanisms documented in the 20 `reference_*.md` memory files that were not already captured as their own row 1-76 (several v1 rows compress multiple distinct sub-tests into one line; each compressed sub-test gets its own row here so a later agent can cite it precisely).

| n | family | why dead (one line) | source | date |
|---|---|---|---|---|
| 1 | OB-imbalance reversion (imbalance-alone) | DEAD at size — Real signal (p≈1e-94) but gross ≈ +0.04%/trade vs breakeven RT fee 0.040%; taker 0/324 configs net-positive; realistic maker fills 0% | 01_dead_list.md:12 | 2026-06-01 |
| 2 | Short-horizon reversion (alt-vs-ETH, high-vol) | DEAD — Gross-real but net regime-luck, walk-forward ~0/negative | 01_dead_list.md:13 | 2026-06-13 |
| 3 | 1h vol-expansion fade | DEAD — OOS +0.26% on ONE split; full-sample −0.187%/t, Sharpe −2.45 (selection bias) | 01_dead_list.md:14 | 2026-06-13 |
| 4 | Funding harvest (naked directional perp short) | DEAD — "+0.65%/trade" was 91% price drift / 9% funding; price risk 8x funding; carry needs a spot hedge | 01_dead_list.md:15 | 2026-06-13 |
| 5 | Market-neutral cross-sectional momentum | DEAD — Survivorship; short leg dead (t=−0.34); needs ~100-470-name book, collapses at 1-3 positions | 01_dead_list.md:16 | 2026-06-13 |
| 6 | Liquidation-cascade reversion | DEAD — Vol-fade with extra steps; high-vol bars CONTINUE, don't revert | 01_dead_list.md:17 | 2026-06-13 |
| 7 | Calendar/microstructure (time-of-day, CME gap fill, funding pre-stamp dip, Saturday alt strength) | mostly NULL / decaying — Time-of-day noise after FDR; CME-gap backwards; Saturday edge decaying, 2026 YTD negative; weekend boost stat STALE | 01_dead_list.md:18 | 2026-06-13 |
| 8 | Pairs / cointegration | DEAD — "Selection works" split-point-dependent; 96% of live-window Sharpe = ONE coin (SAND); honest Sharpe ~0.1-0.3 | 01_dead_list.md:19 | 2026-06-13 |
| 9 | Book×tape absorption short = ST2.0 | DEAD / execution-trapped — Real signal, MAKER-ONLY; live 35 trades −$4.71 recorded / −$5.94 true, breakeven WR ~70.8% vs 43%; passive short-into-absorption adversely selected BY CONSTRUCTION; demoted to paper 6/29 | 01_dead_list.md:20 | 2026-06-13 |
| 10 | Open-interest strategies | eliminated — No peer-reviewed single-instrument net-of-cost OI edge; NO historical OI data, ccxt can't backfill | 01_dead_list.md:21 | 2026-06-29 |
| 11 | Spot-perp basis / carry (delta-neutral) | DEAD at size — Spot fee flat 0.1%/side; best case $0.16/month ($1.88/yr) at $46 | 01_dead_list.md:22 | 2026-07-14 |
| 12 | 12-coin basket TSM (28d tercile) | DEAD — Deflated Sharpe 0.63 FAIL (dilution) | 01_dead_list.md:23 | 2026-07-13 |
| 13 | BTC-TSM (28,5) | DO NOT BUILD — Deflated Sharpe 0.635 FAIL vs 0.95 bar; doesn't beat B&H; 2026 YTD −17% | 01_dead_list.md:24 | 2026-07-15 |
| 14 | ETH-TSM-28 daily long-only | KILLED (pre-registered line) — Scaling-rights probe (~$0.50-1.50/mo); killed by drift line | 01_dead_list.md:25 | 2026-07-06 |
| 15 | Options / VRP income | OUT — Naive harvest −0.1%/yr; Deribit excludes US; revisit ~$25k+ via IBIT only | 01_dead_list.md:26 | 2026-07-16 |
| 16 | Cross-venue funding arb | OUT at ≤$5k — Cheap venues geoblock US; 8/20 sim portfolios profitable net; no retail track record | 01_dead_list.md:27 | 2026-07-16 |
| 17 | Market-making with rebates | OUT — No rebates below ~$100M/30d anywhere; passive fills lose pre-fee | 01_dead_list.md:28 | 2026-07-16 |
| 18 | On-chain / intraday signals, ETF-flow timing, triangular arb, DEX-CEX arb, seasonality/halving/weekend | OUT — adj-R² ≤0.002; +73% gross → −64% net at 0.1% costs; triangular 0/4879 profitable | 01_dead_list.md:29 | 2026-07-16 |
| 19 | Token-unlock short | LOW-MED, not a base strategy — Real drift but −86.6% max DD in only cost-inclusive replication | 01_dead_list.md:30 | 2026-07-16 |
| 20 | Funding-spike carry playbook | ARM DON'T DEPLOY — Funding pays 4-11%/yr now (< T-bills); trigger = sustained >15-20% ann. | 01_dead_list.md:31 | 2026-07-16 |
| 21 | Grid / DCA | DEAD w/ receipts — arXiv 2506.11921: E=0 before fees, negative after | 01_dead_list.md:32 | 2026-07-15 |
| 22 | Vol-selling on Phemex | DEAD — Phemex has ZERO options/dated futures | 01_dead_list.md:33 | 2026-07-15 |
| 23 | VWAP + 9/15 SMA cross (owner's manual setup) | CLOSED — Scan −0.263%/trade @37.7% WR, no gross drift; published edge = catalyst SELECTION not pattern | 01_dead_list.md:34 | 2026-07-06 |
| 24 | Small-cap perps (<$10M vol) | NO-GO — Own history worst tier (−$0.090/t n=258); spread 0.25-2.3x the RT fee; depth $0-17K; keep $3M scanner floor | 01_dead_list.md:35 | 2026-07-07 |
| 25 | S/R bounce (2-touch 1h pivot zones, 5m rejection) | DO-NOT-BUILD / KILLED — Holdout 5,084 trades −$0.0705/t, gross NEGATIVE before fees (TP-hit ~29% vs 32.8% driftless breakeven); live n=50 −$0.79 KILL; 4h/15m, 4h/1h, 1d/1h all negative | 01_dead_list.md:36 | 2026-07-28 |
| 26 | htf_l2_anticipation (main scalper) | DEAD / demoted — 235 trades −$26.81; residual book with every known filter = breakeven (CI incl 0); "no evidenced path to positive expectancy"; main real −$70 lifetime | 01_dead_list.md:37 | 2026-07-13 |
| 27 | htf_confluence_pullback | CULLED — n=18 WR 22.2% −$0.236/t; cluster entries = −$14.10 of −$14.47 | 01_dead_list.md:38 | 2026-05-02 |
| 28 | momentum_continuation, htf_confluence_vwap, bb_mean_reversion (main router) | CULLED — −$0.40/t (n=11), −$0.10/t (n=5), 0 trades + "falling knives" incident | 01_dead_list.md:39 | 2026-04-26 |
| 29 | 5m_narrow, 5m_liq_cascade slots | KILLED — Listed as KILLED slots; both negative-drift walks (5m_narrow peak @#4) | 01_dead_list.md:40 | 2026-06-13 |
| 30 | 5m_mean_revert (live slot) | signal zero-EV — Pre-registered replay 6/1→9/3, 35 syms, 608 train: −$0.024/trade fill-all, 6 families/113 trials NULL; live +$4.62 came from maker-fill selection + hot July | 01_dead_list.md:41 | 2026-09-04 |
| 31 | MR-tuned universe (ranginess scanner) | DO-NOT-BUILD — Frequency 0.97x control (needed 1.5x); holdout quality reversed | 01_dead_list.md:42 | 2026-08-01 |
| 32 | VWAP_CROSS owner slot (paper) | paper, negative-drift walk — Peak @#5, "never had a hot start worth the name"; no formal kill verdict in files read | 01_dead_list.md:43 | 2026-07-20 |
| 33 | BTC/ETH Donchian-ensemble trend (paper) | SURVIVOR on paper; owner DECLINED live 9/8 — Only OOS survivor (sidestepped bear); paper positions still in ledger at wind-down; MEMORY.md: "owner declined Donchian live — never re-offer" | 01_dead_list.md:44 | 2026-07-16 |
| 34 | Linear-vs-inverse funding spread | REAL — PARKED until ~$2K — +3.19%/yr BTC, +4.26%/yr ETH, 100% of 90d windows one-signed; $5.31-7.10/mo only at $2,000; direction = long linear + SHORT inverse (opposite BitMEX) | 01_dead_list.md:45 | 2026-07-15 |
| 35 | Entry-gate surgery (QUIET, TIME, OB-wall, whale) | NULL — leave alone — No gate separates W/L, every CI spans 0; owner: leave gate stack alone | 01_dead_list.md:50 | 2026-06-13 |
| 36 | ST2.0 trailing stop / active exit | INERT — Trail never engages (max live ROI +1.8%); "problem is the SIGNAL" | 01_dead_list.md:51 | 2026-06-15 |
| 37 | ST2.0 entry re-mine (342 cuts) | NULL — Family-wise permutation p=0.77 | 01_dead_list.md:52 | 2026-06-29 |
| 38 | Exit-geometry inventory: SL floor 0.9/0.8%, trail-to-BE@+3%, tight trail band 0.4%, AE threshold sweep −2..−6%, deep-red 2h cut, EARLY_EXIT_MIN_ROI 3→6, loss-cut sweep, hold-vs-cut, time-ratchet SL | ALL DEAD — Each rescues less than it clips; "inventory 100% COMPLETE" | 01_dead_list.md:53 | 2026-07-02 |
| 39 | Wider SL 1.5/2.0% | REFUTED — −41/−57% net June replay; one wider stop > daily halt at $15 | 01_dead_list.md:54 | 2026-07-06 |
| 40 | Partial-TP thresholds (6/10/12) and fractions (75/25) | NULL — All inside rig error | 01_dead_list.md:55 | 2026-07-06 |
| 41 | Restricted adverse-exit (by symbol/regime/trend+vol) | DEAD in all 4 forms — "EXIT-SIDE INVENTORY IS NOW UNCONDITIONALLY EXHAUSTED" | 01_dead_list.md:56 | 2026-07-06 |
| 42 | Lower trail arm (+3%/+4%) | wash — Rescues ≈ clips | 01_dead_list.md:57 | 2026-07-02 |
| 43 | Trail arm 5%→8% | only positive exit lever, inside model error — +$2.45 net but net minus top-2 = −$0.49 | 01_dead_list.md:58 | 2026-07-03 |
| 44 | A+ entry mining (~40 hypotheses, main) | NULL — Holdout + deflation; RSI floor on main structural null (0/87 longs) | 01_dead_list.md:59 | 2026-07-06 |
| 45 | Queue-conditioned posting gate | NULL on our data — Queue size predicts FILL PROBABILITY not toxicity; 20s cancel already an implicit queue filter | 01_dead_list.md:60 | 2026-07-03 |
| 46 | Pre-fill toxicity cancel rule | NULL / undetectable — Tape dead before fills; "best" rule cancels 10/12 of ALL fills | 01_dead_list.md:61 | 2026-07-02 |
| 47 | Main-bot maker re-quote port | NOT justified — 100 misses ≈ breakeven raw, −$4.04 bias-corrected | 01_dead_list.md:62 | 2026-07-02 |
| 48 | Maker exits (fee lever) | DEAD — Patient maker exits live since 6/12: 0/13 fills; early_exit patience = negative EV | 01_dead_list.md:63 | 2026-07-06 |
| 49 | Taker entries for MR / taker switching | DEAD — MR maker +$7.83 vs taker −$24.22 (n=309); needs ~1bp, Phemex 6bp/leg | 01_dead_list.md:64 | 2026-07-06 |
| 50 | MR signal loosening (ADX 30→35, AND→OR, looser long RSI) | DEAD — ADX adds trades at −$0.265/t CI excl 0 | 01_dead_list.md:65 | 2026-07-14 |
| 51 | MR rest extension 60-300s + 2nd requote | CLOSED — Marginal-fill expectancy decays; misses convert zero; prior "misses were winners" partly placement artifact | 01_dead_list.md:66 | 2026-07-14 |
| 52 | MR OB-imbalance gate removal | REFUTED — gate STAYS — Vacuous CI, p=0.0625; H0 re-run at n≥10 pending, never executed | 01_dead_list.md:67 | 2026-07-14 |
| 53 | MR H1 anchor-requote-at-band | refuted — Anchoring = resting longer = converts ~zero | 01_dead_list.md:68 | 2026-07-14 |
| 54 | MR H3 turn-of-15m-candle | NULL (recheck at 60-80 trades) — Replay null, real-money n=6 | 01_dead_list.md:69 | 2026-07-14 |
| 55 | V17 MR_SHORT_RSI_MIN 70→65 | DO NOT ARM (owner) — Diff-CI straddles 0, double selection bias, loosens shorts | 01_dead_list.md:70 | 2026-07-15 |
| 56 | MR symbol curation / blacklist | data only, no proposal — Selection-biased; BTC do-not-blacklist directive | 01_dead_list.md:71 | 2026-07-14 |
| 57 | MR trend-day fuse | NULL, closed — Prevents 0 trades / $0.00 | 01_dead_list.md:72 | 2026-08-01 |
| 58 | MR timeout entry filter | NULL at this n — 36 tests, zero survive; timeouts are +$0.20 net | 01_dead_list.md:73 | 2026-08-01 |
| 59 | MR H1 geometry (79 cells), H2 1h-ADX cap, H3 buy_ratio short skip, H4 funding, H5 22 buckets, H6 entry timing / closed-bar confirmation | ALL NULL — BH over 113 p-values min p 0.15; ADX-cap removes POSITIVE cohorts | 01_dead_list.md:74 | 2026-09-04 |
| 60 | htf_l2 L2-confirmation strength tuning (13 tests) | noise, zero survivors — "Do NOT tune L2 thresholds — nothing to tune" | 01_dead_list.md:75 | 2026-07-17 |
| 61 | htf_l2 anticipation → confirmation-close timing | don't ship — Timing is a 3-6 bps drag, no change clears its CI | 01_dead_list.md:76 | 2026-07-17 |
| 62 | htf_l2 entry-feature mining (RSI/EMA/VWAP/ATR stretch, 144 tests) | NO deployable filter — All fail family-wise placebo (p=0.495) | 01_dead_list.md:77 | 2026-07-18 |
| 63 | VWAP(5m+15m) + 9/15 SMA filter on htf_l2 | REJECTED — VWAP legs no-op; alignment HARMS residual book CI-excluding | 01_dead_list.md:78 | 2026-07-20 |
| 64 | htf_l2 geometry redesign (240-config sweep) | 0/240 reach WR≥68 — trade-off measured | 01_dead_list.md:79 | 2026-07-18 |
| 65 | Ensemble 4/7 confidence gate | DEAD WEIGHT — Structurally cannot fire; confidence score zero predictive power | 01_dead_list.md:80 | 2026-07-17 |
| 66 | 1h EMA direction gate | useless — 98% of entries already align; AEs happen WITHIN trend | 01_dead_list.md:81 | 2026-04-09 |
| 67 | Hour-of-day / pullback hour-bleed gate / day-of-week / tilt / same-symbol re-entry | NULL / stale — Bleed-hour set inverted on current data; worst hour Bonferroni p=0.48; no tilt | 01_dead_list.md:82 | 2026-05-02 |
| 68 | Streak-halting logic | NULL — Payoff asymmetry + chance, big losses ANTI-cluster | 01_dead_list.md:83 | 2026-07-05 |
| 69 | SR_BOUNCE levers L1-L5 (zone cooldown, risk floor, touch count, loss-day blacklist) + L2 snapshot mining (10 features) + I3 fill revalidation | NONE positive / ALL NULL / FAIL x2 — Best combo −$0.064/t; I3 strict fills flip +$2.62 → −$1.49 (edge inverts) | 01_dead_list.md:84 | 2026-07-29 |
| 70 | Venue migration | DEAD — Phemex already cheapest maker of 6; Hyperliquid −10.8% RT vs 30% bar | 01_dead_list.md:85 | 2026-07-06 |
| 71 | Fee tiers / referral fee-back | unreachable — VIP1 ≥$8M 30d volume; referral impossible on existing account | 01_dead_list.md:86 | 2026-07-06 |
| 72 | Faster OB polling / streaming order book | owner declined — Book state measured null for outcomes twice | 01_dead_list.md:87 | 2026-07-06 |
| 73 | Phemex order-replace queue-position probe | owner declined, UNTESTED — Only beneficiary is slot re-quote leg | 01_dead_list.md:88 | 2026-07-06 |
| 74 | "Strategies start strong then decay" hypothesis | NOT supported — Artifact = size-up at curve peaks + negative-drift walks peaking early | 01_dead_list.md:89 | 2026-09-03 |
| 75 | Agent layers (fund manager / trader agent) | rejected as premature — "governance without edge is theater" | 01_dead_list.md:90 | 2026-04-08 |
| 76 | Multi-day mean reversion, 21-23 UTC overnight window, vol-scaling-as-rescue | dead post-2022 — verified by web sweep | 01_dead_list.md:91 | 2026-07-06 |
| 77 | Prior-Day Value-Area Edge Breakout (vae_bo) | refuted — untested S/R-family variant shipped with no backtest and no pre-registered DOA line, the precondition the dead list requires for this family; at its own 5-8 trades/week would take roughly a year-plus to reach the CI pass bar | swarm/REPORT.md | 2026-09-16 |
| 78 | 1h Bollinger-Squeeze Breakout (bb_squeeze_breakout) | refuted — nearest analog (1h vol-expansion fade, row 3) already died from single-split selection bias; backtest-only, no slippage/drift modeled, partial-TP structure inflates visible TP-hit rate rather than net expectancy | swarm/REPORT.md | 2026-09-16 |
| 79 | S/R Rejection Reversion — Taker-Chase Entry (sr_rejection_taker) | refuted — reuses the exact zone-construction method of the killed S/R-bounce family (row 25); taker-chase entry adds ~12bps cost and forces every signal into the trade population SR_BOUNCE's own I3 fill-revalidation showed underperforms | swarm/REPORT.md | 2026-09-16 |
| 80 | Large-Print Tape Snap-Back (tape_snapback) | refuted — economically the same bet as the killed liquidation-cascade-reversion family (row 6, high-vol bars CONTINUE not revert); own fee math misapplies the maker-blend rate to a taker entry, understating true round-trip cost by roughly half | swarm/REPORT.md | 2026-09-16 |
| 81 | OFI-Rollover Reversion Entry (ofi_rollover) | refuted — wait-for-OFI-rollover is the exact entry gate the record already parked on ST2.0 and never calibrated before demotion; raw sign-flip trigger fires 75x/day and is noise-dominated per its own frequency probe | swarm/REPORT.md | 2026-09-16 |
| 82 | S1 — Funding-settlement volatility-regime breakout gate (alts) | refuted 2/2 — relabels two already-dead levers (time-of-day gate row 7, taker entries row 49); fee+drift math needs a 56.5% win rate from a mechanism that is a magnitude finding, not a direction finding | sweep/REPORT.md | 2026-09-16 |
| 83 | S2 — Funding-rate z-score contrarian reversal | refuted 2/2 — the bot's own 195-day funding study already measured this exact relationship at R-squared ~0.003 (no signal); owner directive says don't re-run the funding/XS/OI hunt; ~0.4-0.6 trades/week would take ~7-20 years for a CI verdict | sweep/REPORT.md | 2026-09-16 |
| 84 | S3 — FOMC/CPI first-candle momentum continuation (ETH) | refuted 1/2, net FAIL — cost-adjusted breakeven win rate (56.5%) asserted with zero pulled data; confirmed frequency (~20/yr) would take 10+ years for a CI verdict; entry needs 1-minute precision the bot's 5-minute poller can't execute | sweep/REPORT.md | 2026-09-16 |
| 85 | MR edge-search H1 geometry (79 cells) | NULL — every cell within +/-$0.03 of live; best diff +$0.024, CI straddles 0 | MEM/reference_mr_edge_search_2026-09-04.md:23 | 2026-09-04 |
| 86 | MR edge-search H2 1h-ADX cap | NULL, direction opposite hypothesis — removed cohorts were POSITIVE (<=35 mean +$0.22, <=40 mean +$0.33); the cap would cut the better trades | MEM/reference_mr_edge_search_2026-09-04.md:24 | 2026-09-04 |
| 87 | MR edge-search H3 buy_ratio short skip | NULL — removed n=9/10/6 (flow coverage only 140/608), removed-cohort means +$0.38 to +$0.61, no actionable signal | MEM/reference_mr_edge_search_2026-09-04.md:26 | 2026-09-04 |
| 88 | MR edge-search H4 funding effect | NULL — no effect, X=0.0001 removed n=112 mean +$0.002 | MEM/reference_mr_edge_search_2026-09-04.md:27 | 2026-09-04 |
| 89 | MR edge-search H5 22 buckets | NULL — all kept means within [-0.11, +0.12], every CI straddles 0 | MEM/reference_mr_edge_search_2026-09-04.md:28 | 2026-09-04 |
| 90 | MR edge-search H6 entry timing / closed-bar confirmation | NULL — confirmed_at_close +$0.004 (n=401) vs unconfirmed -$0.078 (n=207), CI straddles; not supported by replay | MEM/reference_mr_edge_search_2026-09-04.md:29 | 2026-09-04 |
| 91 | htf_l2 exit lever: SL floor 0.9/0.8% | DEAD — failed 6/12 validation bar | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 92 | htf_l2 exit lever: trail-to-BE@+3% | REFUTED — -$0.20 actual on 4/25 replay | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 93 | htf_l2 exit lever: tight trail band 0.4% | DEAD — wicks 53% of winners; 6/23 GO/NO-GO kept 1.2% | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 94 | htf_l2 exit lever: AE threshold sweep -2%..-6% | DEAD — caps more than it rescues everywhere, do-not-retry | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 95 | htf_l2 exit lever: deep-red 2h cut | DEAD — failed | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 96 | htf_l2 exit lever: EARLY_EXIT_MIN_ROI 3 to 6 | DEAD — failed | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 97 | htf_l2 exit lever: loss-cut sweep | DEAD — do-not-retry | MEM/reference_sl_loss_levers_2026-07-02.md:20 | 2026-07-02 |
| 98 | htf_l2 time-ratchet SL (60:0.8,120:0.6) | DEAD — re-run on current era: -$1.88 vs baseline, WR 68.6% to 62.9%, fails both-halves bar; dips-recover kills tightened stops in every form | MEM/reference_sl_loss_levers_2026-07-02.md:22 | 2026-07-02 |
| 99 | SR_BOUNCE L2 snapshot mining (10 features) | ALL 10 FEATURES NULL — zero PASS at p<0.005, zero suggestive at p<0.05; closest trend_alignment p=0.064 and directionally backward | MEM/reference_sr_bounce_lever_lab_2026-07-29.md:70 | 2026-07-29 |
| 100 | htf_l2 bull-chasing / broken-long-logic hypothesis | REFUTED — June longs +$4.69 in a -10% month; long-side gap is toxic-cell exposure (thin AND ADX>=35), not broken long logic | MEM/reference_htf_l2_signal_rnd_2026-07-17.md:16 | 2026-07-17 |
| 101 | htf_l2 L2-confirm trade_count>=5 floor fix | REJECTED — raising the floor to fix the degenerate buy_ratio pocket not justified; thin-only cohort is +$6.86 lifetime, already covered by the F5 thin-AND-ADX gate | MEM/reference_htf_l2_signal_rnd_2026-07-17.md:18 | 2026-07-17 |
| 102 | Main-bot htf_adx main-effect toxicity lever | PARKED, fails deflation today — losers enter at ADX 40 vs 36, CI [-0.63,-0.004] but best-of-12 selection | MEM/reference_overnight_sweep_2026-07-06.md:37 | 2026-07-06 |
| 103 | Main-bot wide-spread signal-state lever | PARKED, fails deflation today — 1-of-8 states, artifact-suspect per ST2.0 spread precedent | MEM/reference_overnight_sweep_2026-07-06.md:38 | 2026-07-06 |

## Explicitly UNTESTED mechanisms

Copied from `docs/2026-09-16-edge-swarm-v1/01_dead_list.md` lines 187-204 (section D). These are NOT dead — no verdict exists in any file read. They are not rows above and carry no row number; do not cite a row for them. Path shorthand: MEM = `/Users/jonaspenaso/.claude/projects/-Users-jonaspenaso-Desktop/memory/`; PROJ = `/Users/jonaspenaso/Desktop/Phmex-S/`.

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

