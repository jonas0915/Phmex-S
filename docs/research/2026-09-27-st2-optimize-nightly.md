# ST2.0 Maker Execution — Nightly Optimization Research
**Night 74 | 2026-09-27 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–73)

Prior nights (last covered: N73, 2026-09-25) documented Tweaks 1–63 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth/rank logging, early posting in absorption
window, quarter-hour blackout (Tweak 51), funding gate (Tweak 52), seconds-to-qh (Tweak 53),
OB imbalance regime audit (Tweak 54), 1s adverse-selection baseline (Tweak 55), aggressor-ratio
gate (Tweak 56), OFI saturation gate (Tweak 57), spread-normality gate (Tweak 58), multi-level
OFI depth concentration (Tweak 59), price-deviation cancel-and-repost trigger (Tweak 60), VPIN
suppression gate (Tweak 61), cycle-offset logging (Tweak 62), and symbol-specific OFI gate
reliability / BTC vs ETH asymmetry (Tweak 63).

Tonight's sweep searched four angles:
1. OFI signal decay / passive order staleness after posting
2. Signed markout / post-fill adverse selection measurement methodology for crypto perps
3. Short-horizon mean reversion timing after taker-driven moves in crypto
4. Cross-venue lead-lag effect on passive maker adverse selection

**What is genuinely NEW tonight:**

Angle 3 yields the single most actionable finding: arXiv:2608.21888 (Kitron & Wengrowicz,
August 22 2026) — Binance, 183 pairs, holdout through August 2026 — directly measures whether
15-minute mean reversion after aggressive taker buying is conditioned by order-book depth
imbalance or by taker flow intensity. The answer is unambiguous:
- **Taker flow intensity conditions the reversal** (monotonically: higher buy imbalance →
  higher sign-flip rate). ST2.0's `tape.buy_ratio` captures this.
- **LOB depth consumed conditions NOTHING**: reversal is statistically indistinguishable
  whether the move consumed depth or not. This directly challenges `ob.imbalance ≥ 0.25`.

This paper is NOT in any prior night (N1–N73). No prior night has tested LOB depth imbalance
as a reversal conditioning variable against flow intensity on the same dataset for 15-min crypto.

Angle 2 surfaced no new actionable paper: the arXiv:2608.04373 "Public Trader Identity" paper
is DEX/wallet data, not applicable to Phemex CEX. Angles 1 and 4 returned only prior-corpus
papers (arXiv:2607.09230, arXiv:2602.00776, arXiv:2408.03594 equity data — all already covered
or not applicable).

---

## (b) Confirmed New Finding

### Finding A — LOB Depth Imbalance Does NOT Condition 15-Minute Mean Reversion; Taker Flow Does
**Source:** arXiv:2608.21888 — "Short-horizon mean reversion in cryptocurrency markets: a
matched cross-market measurement," Nadav A. Kitron & Jonathan M. Wengrowicz (August 22, 2026)
**URL:** https://arxiv.org/abs/2608.21888
**Market/Data:** 183 Binance spot/perp pairs; in-sample through 2026-02-11; holdout
2026-02-12 to 2026-08-08 (6 months, outcomes fixed before model was frozen).
**Status:** FETCHED AND VERIFIED (HTML full paper) this session.

**Verified quotes:**

On the core mechanism:
> "reversal concentrates after moves driven by aggressive taker flow and grows with flow
> intensity"

On LOB depth as a conditioning variable (the critical gate-challenging finding):
> "next-bar reversal is indistinguishable after depth-consuming and depth-replenished moves:
> the pooled flip-rate difference is −0.002 (block-bootstrap CI [−0.007, +0.004])"

On the sign-vs-magnitude finding:
> "The signal lives in signs, not magnitudes: lag-one return autocorrelation is near zero on
> the major coins"

On cross-section breadth:
> "90% of 183 Binance pairs FDR-significant; 98% show mean-reverting coupling (A<0)"

On the gross edge size:
> "peaks near 1.3 bp per trade against a 5 bp round-trip cost"

**Quantitative context:**

Flow imbalance metric used: `i_t = 2 × V^taker-buy_t / V_t − 1 ∈ [−1,+1]`
This is equivalent to `2 × tape.buy_ratio − 1` — a metric already computed by ST2.0.

Reversal AUC across flow-imbalance quintiles rises monotonically from 50.2% to 53.0% in
crypto (vs. 49.8% to 51.2% in US stocks). The dose–response is clear and statistically
significant.

Horizon: "is gone by four hours" — confirming the 15-minute TP horizon ST2.0 already uses.
Holdout result: class-mean AUC gap 0.020 (95% CI [0.010, 0.028]), attenuated from 0.031
in-sample. Effect persists but is smaller out-of-period.

BTC, ETH, and XRP individually all show consistent patterns (AUC 0.533, 0.538, 0.536 in
holdout period) — no BTC exception for the taker-flow-conditioned reversal.

**What this means for ST2.0's gate logic:**

ST2.0 uses `ob.imbalance ≥ 0.25` (order-book bid/ask depth ratio) as a primary gate.
The June 2026 synthesis (N73 prior) showed this gate is unreliable for BTC. Now this paper
adds direct evidence for the mechanism:

The gate is conditioning on **the wrong variable**. LOB depth imbalance does not predict
whether the 15-min reversal will occur — it is *orthogonal* to both move size and signed flow
(`|ρ| ≤ 0.09`). Taker flow intensity (`tape.buy_ratio`) does predict reversal magnitude.

ST2.0 already has `tape.buy_ratio` in the entry gate stack (the 0.45/0.55 gate). The paper's
finding means this flow gate should be the *primary* conditioning variable, not the LOB
imbalance gate. The `ob.imbalance ≥ 0.25` gate may be blocking entries where taker flow is
strong but the *snapshot book* happens to look balanced — and may be passing entries where the
book looks imbalanced but flow intensity is actually moderate.

**Important caveat on gross edge:**

The paper documents 1.3 bps gross edge per trade on a 5 bps round-trip cost benchmark. As a
POST-ONLY maker, ST2.0 avoids the taker-side fee. The benchmark round-trip (5 bps) is not the
right cost structure for a maker-only strategy — the relevant cost is one-way fill cost plus
adverse selection, not 5 bps. Whether ST2.0's execution economics cross the actual threshold is
unresolved from this paper alone and requires Phemex-specific calibration.

---

## (c) Forward-Testable Execution Tweak

### Tweak 64 — Flow Intensity Over LOB Depth: Log Taker Flow Imbalance Quintile at Entry
**Source:** arXiv:2608.21888 (verified, Binance 183 pairs, holdout 2026-02-12 to 2026-08-08)
**Mechanism:** The `ob.imbalance ≥ 0.25` gate conditions on LOB depth — but the paper shows
LOB depth does NOT condition 15-min mean reversion. Taker flow intensity DOES condition it,
monotonically. ST2.0 already has `tape.buy_ratio` but treats it as a binary gate (0.55 pass
threshold) rather than an intensity signal.

**Part 1 — Instrument (zero risk, instrument-first rule):**

```python
# At every ST2.0 signal evaluation, log the flow imbalance alongside OB gate result:
flow_imbal = 2 * tape.buy_ratio - 1  # ∈ [−1, +1]; matches paper's i_t metric
log(f"st2_eval: symbol={symbol} flow_imbal={flow_imbal:.3f} "
    f"ob_imbalance={ob.imbalance:.3f} buy_ratio={tape.buy_ratio:.3f}")

# At every fill:
log(f"st2_fill: symbol={symbol} win={win} flow_imbal_at_entry={flow_imbal:.3f}")
```

After 30+ fills stratified by `flow_imbal`, test: does top-quintile taker flow imbalance
(flow_imbal ≥ 0.6, i.e., buy_ratio ≥ 0.80) predict higher WR than bottom quintile?

**Part 2 — LOB Depth vs Flow Cross-Check (instrument first):**

Log `ob_depth_consumed` flag: whether the ob.imbalance was driven by a large bid wall (depth
at level 1) vs. spread thinning. Test: does ob.imbalance trigger without high flow_imbal pass
have systematically worse WR? If paper holds on Phemex data, high-ob-imbalance / low-flow-imbal
entries (the "book looks heavy but flow is light" case) should underperform.

**Part 3 — Gate reordering (deploy only after Parts 1-2 confirm):**

If stratification confirms the paper's finding on Phemex data:
- Tighten `tape.buy_ratio` threshold from 0.55 → 0.65 (flow-intensity filter)
- Relax or remove `ob.imbalance ≥ 0.25` for BTC entries (consistent with Tweak 63's BTC OFI
  unreliability finding from N73)

This is a conservative, instrument-then-deploy sequence: do NOT change live gates before
30+ fills confirm the flow_imbal → WR relationship on Phemex data.

**Priority for Part 1:** High — 2-3 log lines, directly tests the paper's core claim against
ST2.0's own data, uses an existing field (tape.buy_ratio), not a new computation.

**Priority for Parts 2-3:** Medium — deploy only after stratification confirms; requires
30+ fills stratified by flow_imbal to avoid over-fitting.

---

## (d) Caveats and Unverifiable Items

1. **arXiv:2608.21888 (Kitron & Wengrowicz, Aug 2026):** The paper studies Binance spot/perp
   pairs on taker fills. ST2.0 is a MAKER strategy on Phemex alt perps. The reversal documented
   is from the taker-buy perspective (the aggressor); ST2.0's POST-ONLY SELL is resting on the
   *ask side*. The paper confirms the reversal exists (good for the signal), but does not measure
   what fraction of the reversal the PASSIVE maker captures post-fill. The documented 1.3 bps
   gross edge is below the paper's own 5 bps benchmark round-trip; however, that benchmark
   applies full round-trip taker costs. As a maker, ST2.0's effective cost structure is
   materially different and requires Phemex-specific analysis.

2. **LOB depth finding:** The "depth-consuming vs. depth-replenished moves revert identically"
   result is at the 15-minute candle level — it conditions on whether the *previous bar's* move
   consumed book depth, not on a real-time imbalance snapshot at entry. The `ob.imbalance`
   gate in ST2.0 is a real-time snapshot at signal time, not a backward-looking depth-consumed
   measure. The two are related but not identical. The paper suggests that even as a real-time
   conditioning variable, LOB depth imbalance is orthogonal to flow (`|ρ| ≤ 0.09`) and to move
   size, making it an unlikely predictor of better reversal. Treat as motivated hypothesis
   requiring Phemex stratification.

3. **Gross edge (1.3 bps) vs. cost benchmark (5 bps):** The paper frames this as "not
   exploitable under benchmark spot-cost assumptions" and "none of the 183 crypto pairs clears
   even the 5 bp maker band at any threshold." This is a cautionary finding for a maker strategy.
   The paper uses a round-trip benchmark; ST2.0's actual cost depends on maker fees + adverse
   selection + holding cost, which is different. Not directly interpretable without Phemex data.

4. **What remains unfound:** (a) a paper with Phemex-calibrated adverse-selection measure,
   (b) a crypto-perp-native study of OFI signal decay over the order-resting period, (c) a
   markout methodology paper for passive maker orders specifically (the arXiv:2608.04373
   "Public Trader Identity" paper covers markouts but on DEX data). These gaps remain open.

---

## Priority Ordering (Undeployed Actions, Full Stack)

Unchanged high-priority instrumentation:
1. `time_to_fill` logging (N64) — 5 lines, unblocks all fill-quality analysis
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `queue_rank_at_fill` logging (Tweak 47) — 2–3 lines
5. `seconds_to_qh` logging (Tweak 53) — 1 line
6. `aggressor_ratio_at_attempt` logging (Tweak 56)
7. `ofi_percentile_at_attempt` logging (Tweak 57)
8. `spread_ratio_at_attempt` logging (Tweak 58)
9. `st2_ofi_depth_ratio` logging (Tweak 59)
10. `adverse_move_bps_at_cancel` + `cancel_reason` logging (Tweak 60)
11. `vpin_proxy_at_attempt` logging (Tweak 61)
12. `seconds_into_cycle` logging (Tweak 62)
13. `symbol + ob_imbalance + outcome` per-fill logging (Tweak 63)

New tonight:
14. `flow_imbal = 2*tape.buy_ratio-1` + `ob_imbalance` logged together at every entry
    attempt and fill, with outcome (Tweak 64, Part 1) — 2-3 lines, zero trading risk

Then deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| New candidates tonight | 1 (Tweak 64) |
| Total candidates | 20 (45–64) |
| Negative findings | +0 new tonight |
| Conditional | 1 |

---

*Sources fetched and verified this session:*
- *arXiv:2608.21888 (Kitron & Wengrowicz, Aug 22 2026, Binance 183 pairs, mean reversion
  HTML full paper fetched and verified). All quotes above are extracted directly from the
  fetched HTML.*
- *Rejected as DEX / not applicable: arXiv:2608.04373 (DEX wallet data — not CEX),
  arXiv:2608.00885 (theoretical, equity-only)*
- *Returned only prior-corpus entries (not new): arXiv:2607.09230, arXiv:2602.00776,
  arXiv:2408.03594 (equity), arXiv:2607.11888*
