# R1 — DOA / Entry-Quality Study (June+ htf_l2, main bot)

**Date:** 2026-07-05 (overnight run) · **Status:** SCREENING-GRADE, read-only vs the bot
**Data:** `trading_state.json` closed_trades, strategy `htf_l2_anticipation`, `min_margin_skip` phantoms excluded, opened_at ≥ 2026-06-01 UTC → **n=101 real fills** (87 long / 14 short, all 10x leverage, 74W/27L, net **+$7.46**). Entry range 6/2 11:27 AM UTC → 7/5 12:56 PM UTC.
**Candles:** fresh Phemex public OHLCV via ccxt — 1m windows entry→exit for all 101/101 trades, 5m pre-entry windows 101/101 (cached in session scratchpad `r1/c1m`, `r1/c5m`; `reports/cache_l2x_drift/` untouched). Timing precision ±60s (candle granularity).
**Scripts:** scratchpad `r1/fetch_data.py`, `r1/analyze.py`, results in `r1/results.json` (scratchpad is session-temporary; scripts reproducible from this doc's definitions).
**Hypotheses tested this study: ~40** (12 single-feature screens + 10 interactions + 6 early-drift features + 8 threshold scans + 3 overlap cells + 2 RSI variants). At α=0.05 expect ~2 nominal hits by chance. Bootstrap CIs: 10k resamples, groups resampled independently then diffs taken (per bootstrap-diff-CI lesson), seed 42.

Respects the NULL inventory: no re-mining of single entry features at t=0 as standalone gates (2026-07-02 audit: 8/9 null, spread_pct hit died under de-confounding; gate-quantify null; hours null; tilt null).

---

## Part A — Early post-entry signals: winners vs DOA losers

**DOA definition:** loser (net_pnl ≤ 0) whose maximum favorable excursion, measured from 1m candle extremes **strictly after the entry candle** through exit, never reached **+10 bps** price move = +1% ROI at 10x. → **13 of 27 losers are DOA** (11/27 if the entry candle's extremes are included). DOA losers account for **−$13.65** of the −$27.67 June+ loss dollars (49%).

*Reconciliation note:* the 2026-07-02 audit said "71% of June SL losers DOA." On this window/method: 24 SL-bracket losers (`exchange_close`+`stop_loss`), 13 DOA = **54%**. Different window (their study ran through 7/2; June has since accreted trades to 7/5), likely different MFE source (this study: post-entry-candle 1m extremes; conservative — entry-candle extremes can pre-date the fill). Directionally consistent (roughly half-plus of SL losers never see +1% ROI); exact 71% not reproduced — flag, not resolved.

### A.1 Early-drift features (signed bps, + = with the trade), Winners (n=74) vs DOA (n=13, **n<20**)

| feature | W mean / med | DOA mean / med | diff (W−DOA) | 95% CI on diff |
|---|---|---|---|---|
| drift @1m (open) | −3.2 / −3.4 | −25.1 / −3.6 | +21.9 | [+1.0, +49.4] |
| drift @2m | +0.2 / −4.6 | −27.2 / −16.4 | +27.3 | [+9.6, +47.6] |
| drift @5m | +4.4 / +1.7 | −41.6 / −46.5 | **+46.0** | **[+26.0, +66.5]** |
| entry-candle close vs fill | −3.9 / −2.4 | −23.2 / −3.5 | +19.3 | [−0.7, +45.6] |
| early MFE (1–5m) | +16.1 / +6.2 | −11.2 / −3.0 | +27.3 | [+14.3, +42.6] |
| early MAE (1–5m) | −16.2 / −15.8 | −52.8 / −47.3 | +36.6 | [+11.8, +63.2] |

**⚠ Circularity caveat (load-bearing):** DOA is *defined* by never going favorable, so early adverse drift is partly baked into the label. These CIs describe separation, not a tradeable edge. The non-circular tests are A.2 and A.3.

### A.2 Could an early-adverse flag discriminate at decision time? (winner false-positive cost)

| flag threshold | flags DOA | flags winners |
|---|---|---|
| drift@5m ≤ −10 bps | 10/13 | 22/74 (30%) |
| drift@5m ≤ −20 bps | 8/13 | 14/74 (19%) |
| drift@5m ≤ −30 bps | 7/13 | 10/74 (14%) |
| earlyMAE ≤ −30 bps | 7/13 | 13/74 (18%) |

Best in-sample point (~−30 bps @5m): catches ~54% of DOA at ~14% winner contamination. In-sample threshold scan (8 hypotheses), no holdout — **screening-grade only**. Consistent with the L2X finding (losers mildly CONTINUE); per L2X 9/9 HOLD-beats-cut, this must NOT become an early exit.

### A.3 The actionable use — gate the 2nd/3rd concurrent entry: **NULL**

For each entry opened while another June+ htf_l2 position was open (n=26), measured the open position's live signed drift at the new entry's timestamp (1m candle opens):

| condition at new entry | n | sum $ | mean $ | WR |
|---|---|---|---|---|
| prior position underwater (drift < 0) | 11 ⚠n<20 | −0.35 | −0.032 | 64% |
| prior underwater ≥10 bps | 9 ⚠n<20 | +0.49 | +0.054 | 67% |
| prior position green | 15 ⚠n<20 | +1.15 | +0.077 | 80% |
| no overlap | 75 | +6.66 | +0.089 | 73% |

95% CI (underwater − green mean pnl): **[−0.73, +0.51]** — straddles zero; the ≥10bps cell is even *positive*. Direction of the any-underwater cell agrees with the hypothesis but the sample cannot support a gate. **Verdict: NULL / underpowered — do not build the gate; re-look at n≈60 overlap entries.**

Correlated-exposure sanity check: overlapping trade pairs agree in pnl sign 28/36 (78%) vs 61% expected under independence at WR 73% — mild same-move correlation exists (consistent with tonight's streak analysis), it just doesn't cash out as a prior-drift entry gate at this n.

---

## Part B — Feature × regime interactions (SCREENING-GRADE)

Single-feature screen (in-sample, n=100 with snapshots, winner-vs-loser standardized diff): top two |d| = **htf_adx (d=−0.408; losers enter at HIGHER HTF ADX, 40.2 vs 36.0)** and **cvd_al (d=+0.349; winners have more side-aligned CVD slope)**. Note spread_pct reappears at d=+0.34 (winners at wider spread) — same artifact the 7/2 audit killed via majors de-confounding; not pursued.

10 interaction hypotheses (top-2 features × {session, spread_hi, vol_hi, choppy, imb_pos}), split-half boundary 2026-06-28 06:12 UTC (≈50/50):

- Sign-persisting in both halves: `cvd_al×spread_hi` (+0.149; halves +0.387/+0.104), `cvd_al×choppy` (+0.250; +0.169/+0.217), `htf_adx×choppy` (−0.280; −0.122/−0.730), `htf_adx×vol_hi` (+0.322; +0.544/+0.051 — H2 ≈ 0).
- **Bootstrap 95% CIs on the interaction stat all straddle zero:** cvd×spread [−0.44, +0.83]; cvd×choppy [−0.52, +0.88]; htf_adx×choppy [−0.95, +0.51]. **Verdict: interactions NULL.**

**One residual candidate — htf_adx MAIN effect** (not an interaction): median-split mean-pnl diff −$0.316/trade, 95% CI [−0.626, −0.004]; same sign in both halves (H1 −0.426, H2 −0.177) but each half individually straddles zero. It was selected as best-of-12 in-sample, so the nominal CI does **not** survive selection deflation (12 screens → needs far tighter). Coherent story exists (entering when HTF trend is already ADX-40+ = late), but by this project's own rules this is **a hypothesis to pre-register and re-check at larger n, not an action**. Cross-check against lessons.md before anything ships.

---

## Part C — Does the slot's RSI floor transfer to the main bot? **Structural NULL**

Replayed the live slot rule (bot.py:1998–2005: block LONGS with RSI(7) < 22; receipt = `reports/mr_replay_90d.json`, slot maker fills: RSI<22 n=21 −$4.08 vs band 22–30 n=132 +$12.05) against all 87 June+ main-bot longs. RSI(7) computed with the bot's own `indicators.rsi` (ewm com=6, adjust=False) on 5m closes; both completed-bar and forming-bar(entry-price-as-close) variants; 87/87 agreement on the block decision.

- **Trades the floor would have blocked: 0 of 87.** Minimum RSI(7)-5m at entry = 28.1 (completed-bar) / 25.7 (forming-bar). Median ≈ 50–53.
- Even the 22–30 caution band contains only 1–2 trades (both winners, +$0.34/+$1.11 — n<20, anecdote).

The main bot's htf_l2 signal simply never fires into deep-oversold longs — the falling-knife cohort the slot floor removes **does not exist on the main bot**. The slot's RSI receipt neither transfers nor needs to. The other half of the "A+ definition" (fresh/small queue at post) is **unmeasurable retroactively**: main-bot entry snapshots record ob/flow/regime but no queue state — that's the known instrumentation gap (queue-size study already queued per fill-rate research).

---

## Verdict

1. **Part A separation is real but ~half mechanical**; the deployable version (early-drift gate on concurrent entries) is **NULL at n=26**.
2. **Part B interactions NULL**; htf_adx-high-→-worse is the lone screening-grade survivor and does not survive selection deflation. Park it; re-test pre-registered at ~2x n.
3. **Part C definitive NULL by construction** — do not port the RSI floor to the main bot; there is nothing for it to block.
4. Everything here is HYPOTHESIS-grade per CLAUDE.md — cross-check lessons.md before any action.
