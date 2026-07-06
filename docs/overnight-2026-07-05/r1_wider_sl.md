# R1 — Wider SL replay (1.5% / 2.0%) — the last untested exit lever

**Date:** 2026-07-05 (overnight run) | **Verdict: KEEP 1.2 — wider SL is decisively worse**

Closes the last open item in `memory/reference_sl_loss_levers_2026-07-02.md` ("REMAINING UNTESTED #1: WIDER SL"). The exit-side inventory is now fully complete: every direction has been replayed and every one loses to the live config.

## Rig setup

`scripts/calibrate_exits.py` — exit-model isolation rig replaying the 86 real live entries (main-bot strategy) from the June window, exits re-simulated per variant. All runs with **`--trail-arm-roi 8`** (live parity since tonight's restart), `--window-start 2026-06-01 --window-end 2026-07-04 --data-dir backtest_data_june`.

- Per-trade dumps: `reports/widesl_june_baseline12.json`, `reports/widesl_june_sl15.json`, `reports/widesl_june_sl20.json`
- Rig fidelity this window: baseline sim $+14.57 vs live $+12.47 (delta **+16.8%**, inside the documented ±25% error band). Intra-bar price: ~75–78% bar-close fallback (flow coverage thin), so per-trade fills are approximate but variant-vs-baseline diffs share the same price path.
- Trades replayed were June live trades at **$10 margin**; scale dollar figures ×1.5 for today's $15 sizing.

## Headline results (86 trades, sim net incl. fees)

| Variant | Sim net | vs baseline | WR | Avg win | Avg loss | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|
| **SL 1.2 (live)** | **$+14.57** | — | 68.6% (59/86) | $+0.72 | $−1.04 | $+3.94 | $+10.64 |
| SL 1.5 | $+8.58 | **−$5.99 (−41%)** | 68.6% (59/86) | $+0.72 | $−1.26 | $+0.88 | $+7.71 |
| SL 2.0 | $+6.34 | **−$8.24 (−57%)** | 69.8% (60/86) | $+0.72 | $−1.41 | $−0.84 | $+7.18 |

Both halves worse under both variants (4/4 half-cells negative). Monotonic: the wider the SL, the worse. Win rate barely moves — wider SL doesn't create winners, it just makes losers bigger. SL 2.0 turns the first half of June **negative**.

## Per-trade decomposition (vs baseline; 59/86 trades unchanged in both variants)

Baseline had **21 SL-side stops** in the window, netting $−25.62.

**SL 1.5:**
- SL losers → winners: **0**
- SL losers → smaller losers: **2** (+$0.39 — ADA, TAO; both just shrink via hard_time_exit)
- Trades that got worse (rode to the deeper stop): **19** (−$6.38); worst EIGEN −$1.33 → −$2.68
- Net: **−$5.99**

**SL 2.0:**
- SL losers → winners: **1** (+$1.75 — INJ short, exchange_close −$1.26 → early_exit +$0.49)
- SL losers → smaller losers: **5** (+$2.10 — ARB/BTC flat_exit, 2×ADA/TAO time exits)
- Trades that got worse: **15** (−$12.08); worst AAVE −$1.24 → −$2.62
- Net: **−$8.24**

Even paying 67% more room per stop, only **1 of 21** SL losers ever becomes a winner. The "saves" are mostly loss-shrinks into time/flat exits, worth +$3.85 total against −$12.08 of deeper stops.

## 71%-DOA sanity read — depth before recovery on saved trades

For each trade the wider SL "saves", max adverse excursion measured from the first breach of the baseline 1.2% line until price recovered to the variant's exit level (5m candles, $10 June margins):

| Trade | Saved by | Delta | Max depth (price) | Max ROI drawdown | Recovery after breach |
|---|---|---|---|---|---|
| INJ short | 2.0 only | +$1.75 | 1.53% | −15% (−$1.53 open) | 0.8 h |
| ARB long | 2.0 only | +$0.84 | 1.89% | −19% (−$1.89 open) | 0.2 h |
| BTC long | 2.0 only | +$0.57 | 1.60% | −16% (−$0.97 open, $6 margin) | 2.4 h |
| ADA long | 2.0 only | +$0.30 | 1.86% | −19% (−$1.86 open) | 1.8 h |
| ADA long | 1.5 & 2.0 | +$0.20 | 1.28% | −13% | 0.2 h |
| TAO short | 1.5 & 2.0 | +$0.19 | 1.25% | −12% | 0.1 h |

Consistent with the 71%-DOA finding — and independently reconfirms it: **15 of 21 stops (71.4%) ride straight through even a 2.0% stop.** The recoverable minority hovers just past 1.2% (two barely graze 1.25–1.28% and snap back within ~10 min); the four extra 2.0%-saves go 1.5–1.9% deep — at $15 margin those troughs are $2.25–$2.84 of open loss to harvest saves averaging +$0.86 (at $10 scale). The asymmetry is exactly what DOA predicts.

## Operational overlay (the part sim PnL doesn't show)

At 10x leverage and today's **$15 margin**:
- Full SL 1.5% stop = **−$2.25** (~−$2.40 with fees); SL 2.0% = **−$3.00** (~−$3.15)
- Daily halt threshold ≈ **−$1.76** (3% of ~$59 balance; tripped 7/5 at −$2.16 vs −$1.72 limit)
- **A single wider-SL full stop guarantees a halted day.** June window: 21 stops in ~33 days ≈ 0.64 stops/day. SL 1.5/2.0 converts 19/15 of those into instant-halt events respectively — each one also ends the rest of that day's trading, an opportunity cost the sim doesn't even price in. The sim numbers above are therefore an **upper bound** on wider-SL performance.
- Even the baseline 1.2% stop at $15 is ≈ −$1.80 + fees, already at the halt line — wider SL makes an existing operational fragility strictly worse.

## Honest verdict vs the ±25% rig error band

The variant deltas (−41%, −57%) are well outside the band, monotonic with SL width, negative in both halves under both variants, and mechanically explained by the per-trade decomposition (71% of stops are DOA — more room = bigger loss, same destination). No plausible rig error flips this. The operational halt math independently kills wider SL even if sim PnL had been a wash.

**KEEP SL 1.2%.** Exit-geometry inventory is now COMPLETE — all levers tested, all dead: tighter trail arm (wash), time-ratchet (−$1.88), deep-red cut (dead), and now wider SL (−$6.0 to −$8.2). The fix remains on the entry side, not exits.

---
*Runs: 3× `calibrate_exits.py` per config above; decomposition/depth scripts in session scratchpad (`widesl_decomp.py`, `widesl_depth.py`). All numbers read from tool output this session; per-trade rows preserved in the three JSON dumps.*
