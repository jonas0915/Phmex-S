# ST2.0 Deep Research — Is There Any Recoverable Edge?

**Date:** 2026-06-29
**Trigger:** Jonas — "do a deep research for ST2.0 using the loop and the lab; ignore my restrictions for this run."
**Method:** 5 parallel empirical/literature research agents + a forced 40-iteration loop run + 2 adversarial verification agents. Restrictions (no-re-mine / META-RULE #7) lifted for this run. All numbers cross-checked against raw `trading_state_ST2.0.json`, `logs/`, and the lab's own diagnostics.

---

## Verdict (one line)

**ST2.0 has no recoverable edge.** It is not merely "execution-trapped" (the prior verdict) — the entry **signal itself carries no separable edge and is probably pointed the wrong way**, and the killer is **loss asymmetry**: a 0.41 payoff ratio needs a ~71% win rate to break even, and ST2.0 wins 43%. No lever in the lab's reach — entry filter, exit geometry, or maker→taker — closes a −$0.13 to −$0.17/trade hole. **Keep it demoted (done 2026-06-29). Do not re-arm. Stop tuning execution.**

---

## Canonical numbers (VERIFIED from raw data, 2 independent recomputes + the loop's own diagnostics agree)

| Metric | Value | Note |
|---|---|---|
| Live trades | 35 (15W / 19L / 1 flat) | `mode=="live"` in closed_trades |
| Win rate | 42.9% | |
| Recorded net | −$4.71 | sum of net_pnl |
| **True net (honest fees)** | **−$5.94** | 19/35 trades logged `fees_usdt:0`; real fees ≈$1.41 vs recorded $0.18 |
| Expectancy | −$0.1346/trade | bootstrap 95% CI **[−0.243, −0.028]**, entirely < 0 |
| Avg win / avg loss | +$0.151 / −$0.367 | **payoff ratio 0.41** |
| **Breakeven WR** | **70.8% (78.5% with fees)** | **prior research's 48.9% is REFUTED** — it assumed symmetric payoff |
| Maker fill rate | ~32–36% | down from prior 43% (older log era) |
| Post-fill 30s drift | +2.77 bps adverse | winners +1.33 vs losers +6.03; direction robust, magnitude soft (join noise 6.8 bps) |
| `exchange_close` cohort | 7 trades, −$2.39 (≈half the loss) | avg 58-min hold; `adverse_exit` disabled globally |

---

## Findings by angle

### 1. Entry signal — no separable edge (decisive)
Re-mined **342 cuts** (single + 2-feature) on the 35 real trades, restrictions off. Best cut reaches +0.015/trade expectancy — but a **family-wise permutation test (1,000 label shuffles) gives p = 0.77**: random label-shuffling beats the best filter 77% of the time, and the observed best is *below the median* of the null. Every candidate's expectancy CI straddles zero. The lab's own `diagnostics.py` returns 0 candidates at n=35. **The signal carries no edge any in-sample filter can recover.** Independently reproduces the prior `gate_quantify` NULL with stronger statistics.

### 2. External literature — the signal is likely wrong-signed (new insight)
Peer-reviewed microstructure (Cartea/Donnelly/Jaimungal 2018; Gould/Bonart 2016; Lipton et al. 2013) is near-unanimous: **order-book imbalance predicts CONTINUATION, not reversion.** ST2.0 shorts into a bid-heavy book expecting reversion *down* — the opposite of the documented effect. "Absorption reversion" has only practitioner/blog support, no robust academic backing. Additional structural problems:
- **Wrong horizon:** imbalance alpha decays in ~3–10 seconds; ST2.0 holds ~15–23 minutes — far past it.
- **Adverse selection is structural** for slow makers, compensated only by rebates/queue/speed — none of which a Phemex retail account has.
- **The exact live analog lost money:** Albers, Cucuringu, Howison & Shestopaloff (2025), arXiv:2502.18625 — a live Binance BTC-perp imbalance maker lost **−0.4705 bps/trade over 8,851 trades** (this is the actual source of the internal "−0.47 bp" note). "All imbalance-based strategies — maker or taker — perform poorly."
- The only positive evidence (hftbacktest tutorial, +0.86 bps) **depends on Binance's top-tier maker rebate + a queue/latency simulator** — inapplicable to retail Phemex.

*Sourcing caveat:* a few secondary figures (Huang-Stoll 9.6%, Cont et al. 65% R²) were flagged not-primary-verified and are not load-bearing. The verdict rests on the qualitative findings (continuation sign, seconds-scale decay, structural adverse selection, the live −0.47 bps result), all well-supported.

### 3. Execution (maker→taker) — won't help; "maker protective" claim REFUTED
- Maker→taker entry reconstruction: taker is ~7 bps **worse** (spread + 12 bps round-trip taker fee). **HIGH confidence maker→taker does not create edge.**
- The session's initial finding that "the maker is *protective* because missed signals were worse shorts (−75.5 bps)" was **adversarially refuted**: that number rests on only ~2 usable ETH miss-points (one win, one loss) plus a non-reproducible INJ −237 bps outlier across an L2 recorder gap. Mechanically the maker likely **misses favorable reversals**, not disasters — so "protective" is probably itself wrong-signed. Do not rely on it.
- Post-fill adverse drift (+2.77 bps) is real in *direction* but its magnitude is soft (join noise 6.8 bps > signal) and it conflates execution with a simply-wrong signal.
- **Reason maker→taker can't help: BOTH execution adverse selection AND signal weakness — dominated by the signal/loss-asymmetry.**

### 4. Exit geometry — only loss-cutting has any value, and not enough
- Profit-side exits (trailing stop, breakeven ratchet, partial scale-out, wider TP) are **INERT at n=35** — only 1/35 trades ever reached the +16% TP; 0/29 reconstructed paths hit +10% ROI. Confirms the prior n=15 finding.
- Loss-cutting (tighter stop / taker-backstopped time-stop) is worth roughly **+$0.5 to +$1.5 over 35 trades**, but fidelity-capped (80s path reconstruction understates excursions).
- Most defensible fix: a real **taker-backstopped time-stop (~5–10 min)** — the "15-min hold" actually runs a median 22.9 min with a 5-hour hang tail; the `exchange_close` cohort (avg 58 min) is half the loss.
- **Even best-case, exit fixes take ST2.0 from −$4.71 to ≈ −$3.2 — still net-negative.** Exit can only slow the bleed.

### 5. The loop — a working truth-gate pointed at a dead space
- **Forced 40-iteration run: `run_count` 113→153, 0 accepted of 500 history entries.** Every iteration identical: *"neighborhood exhausted (155 already tried)... no out-of-sample improvement — champion unchanged."* Pushing it 8× harder finds nothing — empirical proof it's exhausted on current data.
- **Structural limit:** the genome only mutates entry thresholds, entry-veto filters, and static SL/TP/hold (`config.py:91-98`). The real bottleneck is execution/fill quality, which the loop **cannot mutate and cannot faithfully model** — its adverse-fill model is a flat hardcoded haircut applied uniformly. It can't tell a better-filling config from a worse one. So its only response to adverse fills is "be stricter," which shrinks trade count below the rankability/walk-forward/DSR bars → 0 accepted.
- The honest gates (walk-forward + deflated-Sharpe ≥0.90 + bootstrap-CI) are working correctly — they're refusing to crown noise. The loop isn't broken; it's correctly reporting there's no edge reachable from its knobs.

### 6. Measurement gap — queue position is a dead end; adverse selection is measurable but won't change the answer
- Queue position is **fundamentally unobservable** for retail (Phemex returns aggregated depth, never market-by-order). `fills.py`'s claim is right on that narrow point.
- BUT adverse selection — the actual edge-killer — is **measurable cheaply at high N from the tape**, decoupled from trade count. A live L2 tick recorder (~23ms) has run since Jun 13, and a complete adverse-selection study (`scripts/research/execution-2026-06-13/`) already exists but was never wired into the loop.
- Cheap instrumentation wins (P0: read the maker/taker flag + real fee already in ccxt responses; P1: add ST2.0's symbols — WIF/ENA/etc — to the tick recorder, currently only BTC/ETH/INJ/ARB so only 22/35 trades are L2-covered).
- **But this only makes the conclusion rigorous — it won't remove the bottleneck.** Better measurement would let the loop test whether any placement/symbol/regime subset escapes adverse selection; every prior signal says it won't.

---

## Recommendations

1. **Keep ST2.0 demoted (done 2026-06-29). Do not re-arm.** The case is now over-determined: signal has no edge (perm p=0.77), is likely wrong-signed (literature), loss asymmetry needs 71% WR vs actual 43%, true net −$5.94, CI entirely negative, the exact live analog in the literature lost money, and the loop is exhausted (0/500 accepted).
2. **Stop tuning ST2.0 execution.** Maker→taker, offset, fill-window — all settled negative or null. HIGH confidence.
3. **The loop is good machinery aimed at a dead space.** Either pause it on ST2.0 or repurpose it to a strategy whose edge lives in signal selection (where its search space is competent) and whose execution is taker (so the fill-modeling gap doesn't bite) — e.g. `5m_mean_revert`. (NOT pursued this session per Jonas.)
4. **Fix the broken fee ledger (bug, separate from ST2.0).** 19/35 ST2.0 trades logged `fees_usdt:0`; `extract_order_fee` returns 0 when ccxt doesn't populate, and `takerOrMaker`/`fee.rate` are never read. This understates losses bot-wide, not just ST2.0. Worth fixing regardless.
5. **If a future taker strategy needs it,** the cheap P0+P1 instrumentation (read maker/taker flag + real fee; add traded symbols to the tick recorder) is worth doing — but only then.

---

## Cross-references
- [[reference_st2_execution_research]] — prior "execution-trapped" verdict (now refined: signal-trapped too)
- [[reference_st2_postfill_drift]] — prior +3.23 bps drift (now +2.77, magnitude soft)
- [[reference_st2_exit_replay]] — prior "trail inert" at n=15 (confirmed at n=35)
- [[reference_edge_hunt_exhaustion]] — backtesting this data produces artifacts; forward-test is the only adjudicator
- [[project_phmex_st2]] — demote record

## Reproducibility
- Loop: `cd scripts && python -m st2_lab.loop --iterations N` (lab-only, never touches live)
- Exit grid: `scripts/st2_lab/exit_grid.py` (new), `exit_replay.py`
- Drift: `scripts/st2_lab/drift.py`; fills: `fills.py`; entry filters: `entry_filter_sim.py`
- Prior execution study: `scripts/research/execution-2026-06-13/{02_fillmodel,adverse_selection}.py`
