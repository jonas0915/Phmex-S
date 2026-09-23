# ST2.0 Maker Execution — Nightly Optimization Research
**Night 71 | 2026-09-23 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–70)

Prior nights (last covered: N70, 2026-09-22) documented Tweaks 1–58 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth logging, queue rank logging, early posting
in absorption window, quarter-hour boundary blackout (Tweak 51), funding-state gate (Tweak 52),
seconds-to-quarter-hour logging (Tweak 53), OB imbalance regime audit (Tweak 54), 1-second
adverse-selection baseline (Tweak 55), aggressor-ratio gate (Tweak 56), OFI saturation gate
(Tweak 57), and spread-normality gate (Tweak 58).

Tonight's sweep covered four angles:
1. Conditional limit order repricing / chasing the ask when the offer lifts
2. Multi-level OFI (MLOFI) — imbalance measured across depth levels vs. best-bid/ask only
3. Fill probability prediction via survival analysis (KANFormer, Dec 2025)
4. Sentiment-regime effects on maker adverse selection in crypto

**What is genuinely NEW tonight:** Angle 2 yields one confirmed primary-source finding —
the MLOFI paper (arXiv:1907.06230) — that is verifiably absent from Nights 1–70 and
mechanistically applicable to ST2.0's single-level `ob.imbalance` gate. Angles 1, 3, and 4
produced papers already in the corpus or not actionable at ST2.0's scale.

**Honest caveat upfront:** Tonight's single new finding comes from a 2019 equities paper
(NASDAQ), not a crypto-perp-specific paper. Calibration on Phemex data is required before
any gate change. This is a leaner night than N69–N70 (two crypto-specific papers each).

---

## (b) Confirmed New Finding

### Finding A — Multi-Level OFI Improves Price-Prediction vs. Best-Level-Only OFI
**Source:** arXiv:1907.06230 — "Multi-Level Order-Flow Imbalance in a Limit Order Book,"
Ke Xu, Martin D. Gould, Sam D. Howison (2019, SSRN/arXiv).
**URL:** https://arxiv.org/abs/1907.06230
**Data:** 6 liquid NASDAQ stocks (AMZN, TSLA, NFLX, ORCL, CSCO, MU). Tick-by-tick LOB data.
**Status:** FETCHED AND VERIFIED (HTML, abstract + key results) this session.

**Verified claims (from WebFetch of arXiv HTML):**

> "When M=1, MLOFI and OFI are identical; when M≥2, MLOFI becomes a more general measure."

> "For all 6 stocks that we study, we find that the out-of-sample goodness-of-fit of the
> relationship improves with each additional price level that we include in the MLOFI vector."

> "The rate of increase is largest when M is small, and is relatively small when M is large."

**Quantitative improvement (from fetched results):**
- Small-tick stocks (AMZN, TSLA, NFLX): R² improves from ~0.35–0.60 (M=1) to ~0.55–0.80 (M=5)
- Large-tick stocks (ORCL, CSCO, MU): R² improves from ~0.65–0.80 (M=1) to 0.95+ (M=5)
- Improvement plateaus beyond 5–7 levels for most instruments
- Including 10 levels vs. 1: "approximately 65–75% improvement for large-tick stocks and
  15–30% for small-tick stocks" in out-of-sample goodness-of-fit

**What this means for ST2.0:**

The current `ob.imbalance` gate uses single-level (best bid / best ask) depth. MLOFI shows
that the imbalance *across multiple depth levels* is a materially stronger predictor of
short-horizon price direction. Two actionable implications:

(1) **Depth-consistency check**: A bid-heavy imbalance that is strong at level 1 but fades
quickly at levels 2–5 ("surface imbalance") signals that the buying pressure is thin and
potentially near exhaustion — the exact condition ST2.0 wants to enter. A bid-heavy imbalance
that is equally strong at all 5 levels ("deep imbalance") indicates more persistent buying
pressure and a riskier entry. Computing an "OFI depth concentration ratio" — best-level OFI
as a fraction of 5-level total OFI — could discriminate between these regimes.

(2) **Gate calibration accuracy**: If the current `ob.imbalance ≥ 0.25` gate uses only the
best-bid/ask ratio, two trades passing this gate can be in completely different adverse-
selection regimes depending on whether that imbalance is surface-only or deep. Logging MLOFI
alongside the existing gate would enable retrospective calibration of the 0.25 threshold.

**Not in any prior night:** The prior corpus extensively covers single-level OFI and the
ob.imbalance gate (arXiv:2502.18625, arXiv:2602.00776, June 2026 synthesis, Tweaks 54/57),
but none reference multi-level OFI depth-structure as an independent discriminator.

**Caveat:** This paper uses NASDAQ equities, not crypto perps. The improvement magnitude
(65–75% for large-tick, 15–30% for small-tick) may not transfer to crypto. Phemex perp order
books are generally thinner; the "depth" available at 5 levels may be less informative than
on NASDAQ. Treat as a hypothesis-generating finding requiring Phemex-specific calibration,
not a confirmed effect size.

---

## (c) Forward-Testable Execution Tweak

### Tweak 59 — Multi-Level OFI Depth Concentration Logging
**Source:** arXiv:1907.06230 (verified, NASDAQ equities)
**Mechanism:** The current gate passes entries where best-bid/ask imbalance ≥ 0.25.
This conflates "surface-imbalanced" books (buy wall only at level 1) with "deep-imbalanced"
books (consistent buy pressure across levels 1–5). Deep imbalance = more persistent adverse
flow; surface imbalance = potentially near-exhaustion and thus a better mean-reversion entry.

**Implementation sketch:**
```python
# At ST2.0 entry check, alongside existing ob.imbalance gate:
# ob.bids/asks should already be a list of [price, size] from L2 snapshot

def compute_mlofi_depth_ratio(bids, asks, levels=5):
    """OFI at level 1 vs. average OFI across levels 1–N. > 1 = surface-concentrated."""
    if len(bids) < levels or len(asks) < levels:
        return None
    total_bid = sum(b[1] for b in bids[:levels])
    total_ask = sum(a[1] for a in asks[:levels])
    best_bid = bids[0][1]
    best_ask = asks[0][1]
    best_imbal = (best_bid - best_ask) / (best_bid + best_ask + 1e-9)
    multi_imbal = (total_bid - total_ask) / (total_bid + total_ask + 1e-9)
    # Ratio > 1: best-level more imbalanced than deep → surface imbalance
    # Ratio ≈ 1: consistent depth → deep imbalance
    return best_imbal / (multi_imbal + 1e-9) if abs(multi_imbal) > 1e-6 else None

depth_ratio = compute_mlofi_depth_ratio(ob.bids, ob.asks, levels=5)
if depth_ratio is not None:
    log(f"st2_ofi_depth_ratio={depth_ratio:.3f}")
```

**What to instrument first:** Verify that `exchange.py` or `bot.py` passes the full L2 bids/asks
list (not just best bid/ask) to the ST2.0 entry check. Grep for `ob.bids` and `ob.asks` in
`bot.py` and `exchange.py` — if L2 is captured for the OB imbalance gate, it almost certainly
has 5+ levels already.

**What to measure after logging:** At every ST2.0 signal, log `st2_ofi_depth_ratio`. Stratify
outcomes by depth-ratio quintile. Hypothesis:
- `depth_ratio > 2.0` (surface-concentrated imbalance): best mean-reversion setup — buying
  pressure thinnest at depth, most likely near exhaustion
- `depth_ratio ≈ 1.0` (deep consistent imbalance): riskiest entry — adverse flow has depth
  to run through the posted ask

**Caveat:** Do NOT deploy as a hard gate before 30+ logged attempts show clear stratification
by outcome. The ratio may behave differently on small-cap alt perps (thin books) vs. BTC/ETH.
Instrument-first rule applies. This is a logging tweak only until data confirms the effect.

**Priority:** Medium — mechanistically sound, builds on existing L2 data (likely already
available), and fills a genuine gap in the current gate stack (which is blind to whether
imbalance is surface or deep). Not crypto-specific; calibrate before hardening.

---

## (d) What Was NOT Found (Honest Gaps)

1. **Conditional repricing / chasing the ask (Angle 1):** Searches returned arXiv:2607.28323
   (Optimal Execution with Passive Market Impact, July 2026), arXiv:2609.18019 (Model-Free
   Passive Execution), and arXiv:1409.1442 (sell-side tactics) — all already in the prior
   corpus. No new primary-source paper on conditional repricing for crypto perps was found.

2. **KANFormer fill probability prediction (arXiv:2512.05734):** French equity futures
   (Euronext CAC 40 contracts, 2016–2017). The survival-analysis approach is methodologically
   interesting but the data is equity-only and from 2016. No crypto-perp relevance confirmed.
   Not included as a tweak candidate.

3. **Sentiment-regime adverse selection (arXiv:2602.07018):** This paper tests whether Crypto
   Fear & Greed Index extremes correlate with wider spreads. Conclusion is "specification-
   dependent" with no stable causal finding. Not actionable for a passive maker entry gate.

4. **Market Informedness / agent-based model (arXiv:2606.05882):** Computational agent-based
   model, no empirical market data. Not actionable.

5. **Multi-level OFI on crypto perps specifically:** The only MLOFI primary source found is the
   2019 NASDAQ equities paper. No 2025–2026 paper testing MLOFI on crypto perpetuals was found
   tonight. The hypothesis remains equity-derived; Phemex calibration is the necessary next step.

---

## Priority Ordering (Undeployed Actions, Full Stack)

Unchanged high-priority instrumentation from prior nights (5 lines each, zero risk):
1. `time_to_fill` logging (N64) — 5 lines Python, unblocks all fill-quality analysis
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `queue_rank_at_fill` logging (Tweak 47) — 2–3 lines
5. `seconds_to_qh` logging (Tweak 53) — 1 line
6. `aggressor_ratio_at_attempt` logging (Tweak 56 prerequisite)
7. `ofi_percentile_at_attempt` logging (Tweak 57 prerequisite)
8. `spread_ratio_at_attempt` logging (Tweak 58 prerequisite)

New tonight:
9. `st2_ofi_depth_ratio` logging (Tweak 59 prerequisite) — verify L2 bids/asks available in
   entry context first

Then deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| Candidates tonight | 1 (Tweak 59) |
| Total candidates | 15 (45–59) |
| Conditional | 1 |

---

*Sources fetched and verified this session: arXiv:1907.06230 (MLOFI, HTML+abstract verified).
Rejected as not-new or not-actionable: arXiv:2512.05734 (French equity futures), arXiv:2602.07018
(specification-dependent spread study), arXiv:2606.05882 (agent-based model, no data), and
multiple prior-corpus papers (arXiv:2607.28323, arXiv:2609.18019, arXiv:2602.00776).
All claims from arXiv:1907.06230 are marked as equity-derived (NASDAQ) and require
Phemex-specific calibration before deployment.*
