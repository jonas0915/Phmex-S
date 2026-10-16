# ST2.0 Execution Optimization — Night 90 (2026-10-16)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–80 across Nights 1–89. Night 89 (2026-10-15): Tweak 80 (quarter-hour activity gate, arXiv 2607.09426). Night 88: Tweak 79 (tape intensity dose-response gate, arXiv 2608.21888). Night 87: Tweak 78 (gate hysteresis / trip-rearm dead-band). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Papers fetched and confirmed NOT actionable tonight:**

- **arXiv 2606.05882 (Ochędzan & Antulov-Fantulin, "Market Informedness and Market-Maker Profitability"):** Fetched tonight from https://arxiv.org/abs/2606.05882. Agent-based simulation only — no real exchange data, no crypto-specific asset. The main claim ("informed market order flow is particularly harmful when aggregate market informedness is low") is theoretical, not calibrated. No bps numbers, no AUC, no thresholds. **Not actionable for ST2.0.** Excluded.

- **arXiv 2602.07018 (Farzulla, "Does Crypto Sentiment Extremity Widen Estimated Spreads?"):** Fetched tonight from https://arxiv.org/abs/2602.07018. BTC/USDT daily data using high-low spread proxy (not quoted/executed spread). The paper's own conclusion: "The results therefore show only a descriptive, specification-dependent association. We conclude that they do not establish a stable or causal liquidity premium." After full controls, the sentiment–spread effect is 11.81 bps (p = .101, not significant). **Not actionable.** Excluded.

- **AFT 2026 LIPIcs paper (drops.dagstuhl.de PDF):** Fetched as compressed PDF; body unreadable. Topic unknown. **Excluded.**

- **Microstructure Lab Substack "Order Book Resilience: How Fast Does the Book Recover After a Sweep?"** — Still paywalled. Preview confirms: Binance/GateIO/OKX data, 180,590 sweep events Oct 2025–Feb 2026, 100ms resolution, 30-second recovery paths. Calibrating Obizhaeva-Wang κ. **Numbers not accessible — UNVERIFIED.** Not re-attempted.

- **SSRN 6693260** — Search confirms still not indexed. HTTP 403 persists on direct fetch. **UNVERIFIED.** Not re-attempted.

**arXiv q-fin.TR sweep for new 2026 papers:** All results returned are confirmed prior-corpus papers (2502.18625, 2602.00776, 2609.18019, 2607.11888, 2605.06405). No new uncovered q-fin.TR paper found tonight.

---

**What is genuinely NEW tonight:**

**Robust Volume Z-Score as a Burst Detector (Median/MAD, Practitioner Pattern)**

Source: dev.to practitioner article, "Detecting Orderbook Toxicity & Polymarket Divergence: Building a Microstructure Circuit Breaker."

**URL:** https://dev.to/followsm/detecting-orderbook-toxicity-polymarket-divergence-building-a-microstructure-circuit-breaker-ef9

**Verification:** Full article fetched tonight. Direct quotes extracted. **Practitioner blog post — NOT peer-reviewed. No academic primary source for the specific implementation.** The conceptual foundation (anomalous trade volume as an adverse-selection signal) has a structural grounding in informed-volume microstructure theory (Kyle 1985, Admati-Pfleiderer 1988), but those papers are foundational theory, not crypto perp execution research.

**Direct quotes from the fetched article:**

> "The practical defence isn't forecasting the move. It's pulling or widening quotes within milliseconds of order flow turning toxic, then restoring them once conditions normalise."

On the burst detector specifically:
> "Robust volume Z-score: 0.6745 × (Vt − median) / MAD"

On the VPIN caveats:
> "VPIN did not predict the 22 August sweep. Its percentile was at the 4th percentile before the move."
> "The fast-VPIN relationship inverted."

On the fastest available toxic-flow signal:
> "taker-side imbalance moved first in the case study"

**Why this is new vs. the prior 80 tweaks:**

ST2.0 currently has three volume/flow-related gates:
1. Existing tape gate (buy_ratio ≥ 0.55): directional condition — *is* buying happening?
2. Tweak 79 (tape intensity gate, arXiv 2608.21888): percentile rank of buy_ratio — *how strong* is the buying relative to history?
3. Tweak 76 (realized-vol gate): price-returns σ percentile — *how volatile* has recent price movement been?

None of the three measures **total trade volume magnitude** as an independent dimension. The robust volume Z-score measures: *is the current bar's total trade count / volume anomalously high relative to this symbol's own history?*

The structural motivation from classical informed-volume literature (Kyle 1985): informed traders concentrate their order flow in high-volume periods to camouflage information. Anomalously high total volume is a signal that the flow is more likely to be information-driven. For ST2.0's passive short-into-absorption: a volume burst event (Z-score > 2σ) during buying absorption means the absorption is more likely driven by informed buyers who expect price to continue up, rather than noise traders who will revert.

The median/MAD formulation is specifically chosen over mean/σ for its robustness to volume spikes: a large outlier event won't permanently inflate the baseline, so the burst detector stays calibrated.

**Key difference from Tweak 79:**
- Tweak 79: buy_ratio percentile rank → directional intensity of taker BUYING
- Tweak 81 (proposed): trade volume Z-score → magnitude of TOTAL TRADE VOLUME regardless of direction

These measure orthogonal dimensions. A burst event (high total volume) can occur with a moderate buy_ratio (active two-sided trading), meaning Tweak 79 might pass while Tweak 81 flags. Conversely, strong directional buying (high buy_ratio percentile) can occur at normal volume levels, meaning Tweak 79 flags while Tweak 81 doesn't.

**Direction ambiguity (same structural uncertainty as Tweak 80):**

The Kitron & Wengrowicz dose-response (Tweak 79's source) suggests stronger taker flow → stronger expected reversion. If volume bursts accompany the strongest taker-flow events, burst events might actually be BETTER for ST2.0 (more reliable reversion). This is the same ambiguity as Tweak 80's quarter-hour gate. The shadow log resolves it empirically.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 81 — Robust Volume Z-Score: Shadow-Log Anomalous Trade-Volume Bursts on Every ST2.0 Entry

**Source:** Practitioner blog post: "Detecting Orderbook Toxicity & Polymarket Divergence: Building a Microstructure Circuit Breaker." URL: https://dev.to/followsm/detecting-orderbook-toxicity-polymarket-divergence-building-a-microstructure-circuit-breaker-ef9. **Practitioner source — not peer-reviewed.** Conceptual motivation: Kyle (1985) informed-trading model and Admati-Pfleiderer (1988) trading concentration theory (standard microstructure, not crypto-specific). Specific thresholds are hypothesis-only.

**Proposed Tweak 81 implementation (shadow mode only):**

```python
import numpy as np

VOLUME_ZSCORE_LOOKBACK_CYCLES = 120  # 2-hour rolling window at 60s cycles
VOLUME_ZSCORE_MIN_HISTORY = 20       # minimum cycles before the score is meaningful

def _robust_volume_zscore(self, symbol: str, current_volume: float) -> float | None:
    """
    Computes a robust Z-score for the current candle's trade volume relative to this
    symbol's recent history, using median/MAD to resist contamination by outlier bursts.
    
    Formula: 0.6745 × (V_t - median(V)) / MAD(V)
    The 0.6745 scale factor makes the score equivalent to a Gaussian Z-score at the median.
    
    Returns None if insufficient history.
    Based on practitioner pattern from dev.to circuit-breaker article (not peer-reviewed).
    """
    history = self._volume_history[symbol][-VOLUME_ZSCORE_LOOKBACK_CYCLES:]
    if len(history) < VOLUME_ZSCORE_MIN_HISTORY:
        return None
    arr = np.array(history, dtype=float)
    med = np.median(arr)
    mad = np.median(np.abs(arr - med))
    if mad == 0:
        return 0.0
    return 0.6745 * (current_volume - med) / mad

# In ST2.0 entry logic — shadow mode only:
# vol_z = self._robust_volume_zscore(symbol, current_candle_volume)
# burst_flag = (vol_z is not None and vol_z > 2.0)
# self._log(f"vol_burst symbol={symbol} vol_z={vol_z:.2f if vol_z is not None else 'N/A'} burst={burst_flag}")
# For now: log only; do NOT gate entry.
```

**Forward-test design (shadow only):**

Log `vol_z` (robust volume Z-score) and `vol_burst` (True if vol_z > 2.0) on every ST2.0 entry attempt and every fill.

- **Primary hypothesis:** Entries where `vol_burst=True` (anomalous total volume) show materially worse win rate and/or higher post-fill adverse selection bps than entries where `vol_burst=False`.
- **Secondary hypothesis (reverse):** Burst events might show *better* win rates, consistent with the Kitron dose-response finding that stronger absorption → stronger reversion (Tweak 79). This would suggest burst events are GOOD entry windows, not bad.
- **If primary hypothesis confirmed** (WR burst=True < WR burst=False by ≥10pp across n≥30): promote to a hard gate blocking ST2.0 entries when vol_z > 2.0. Estimated gate frequency: by construction (Z-score > 2.0 ≈ top ~2–5% of normal distribution), this would block a relatively small fraction of entries, perhaps 5–10%.
- **If secondary hypothesis confirmed** (WR burst=True > WR burst=False): burst events are a positive selection criterion. Consider combining with Tweak 79 as a compound "high intensity + high volume = entry" gate.
- **If neither** (WR indifferent to vol_z): volume magnitude does not differentiate ST2.0 adverse selection. Do not promote to a gate.

**Why median/MAD, not mean/σ:**

A single large burst event inflates mean and σ, making subsequent Z-scores smaller (the distribution adapts to the outlier). Median and MAD are insensitive to outliers: a single 10× volume spike does not change the median or MAD significantly when the lookback has 120 data points. The baseline remains calibrated to typical volume levels, so the next burst fires correctly.

**Implementation complexity:** Minimal. Requires a rolling buffer of recent trade volumes per symbol. This buffer almost certainly exists already (exchange.py or bot.py maintains candle data). The Z-score computation is 5 lines using numpy. No new data feeds.

**Implementation dependency:** Independent of all prior tweaks. Can be shadow-deployed immediately. Does NOT require Tweak 47/65 as a prerequisite (the Z-score is computed at entry time, not post-fill).

**Interaction with existing gates:**
- Orthogonal to Tweak 79 (buy_ratio percentile) and Tweak 76 (price-returns vol percentile). Measures total volume, not directional ratio or price volatility.
- Orthogonal to Tweak 80 (quarter-hour proximity). A burst can occur at any time, not just near quarter-hour marks.
- If vol_z and buy_ratio_pct_rank are both logged, they can be correlated: does a high vol_z tend to co-occur with high buy_ratio_pct_rank (burst = directional burst)? Or are they independent (burst = two-sided volume, not necessarily directional)?

**Priority:** Low-medium. Shadow-log-only with zero execution risk and minimal implementation cost. The key question it answers is whether total trade volume magnitude is a new adverse-selection dimension orthogonal to the directional and price-vol gates already in the stack.

---

## (c) Caveats and Unverified Items

1. **Source is a practitioner blog post, NOT peer-reviewed.** The dev.to article is written by a market-maker for Polymarket short-dated prediction contracts — a very different venue from Phemex crypto perpetuals. The VPIN component of the same article explicitly failed to predict a major sweep event ("VPIN did not predict the 22 August sweep... at the 4th percentile before the move"). The median/MAD burst detector is proposed without backtested results in the article. Apply with skepticism; the shadow log is the only validation path.

2. **Direction ambiguity is the key uncertainty.** The burst detector is equally consistent with two opposing hypotheses: (a) volume bursts = informed flow = adverse selection risk for ST2.0, or (b) volume bursts = strong absorption = better reversion = better outcome for ST2.0. The shadow log resolves this; no a priori claim is being made about the expected direction.

3. **Article's VPIN caveat is a warning.** The same article's VPIN application failed on a live event. Classical adverse-selection indicators can fail precisely when the event is most severe. The robust vol Z-score shares this structural risk.

4. **Z-score threshold (2.0) is a starting hypothesis.** The top 2–5% threshold is an engineering starting point, not derived from any empirical calibration on Phemex data. The actual distribution of vol_z values for ST2.0's entry events will determine the appropriate threshold.

5. **"Volume" is ambiguous without precise definition.** The proposal above uses "current candle's trade volume" (number of trades or trade dollar volume within the analysis window). The specific measure should match what `ws_feed.py` already collects (likely tape trade count or cumulative taker volume over the last N seconds). This needs to be confirmed against the actual implementation before deployment.

6. **Persistent unverified leads (unchanged from Night 89):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403 persists.
   - Microstructure Lab Substack (post-sweep delayed entry / LOB resilience): Still paywalled.
   - arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77): Still not fully captured.

---

## Summary

| Tweak | Description | Priority | Source | Status |
|-------|-------------|----------|--------|--------|
| 81 | Robust volume Z-score: shadow-log `vol_z = 0.6745 × (V_t − median) / MAD` per symbol on every ST2.0 entry; compare adverse selection outcomes vs. burst flag (vol_z > 2.0). New orthogonal dimension vs. Tweaks 76 (price-vol) and 79 (directional intensity) | Low-medium (shadow only until data confirms direction) | Practitioner pattern: dev.to circuit-breaker article (fetched, direct quotes); conceptual basis: Kyle (1985), Admati-Pfleiderer (1988) informed-volume theory | NEW — VERIFIED (concept + direct quotes; practitioner source only, not peer-reviewed); direction ambiguous |

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | Academic | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry + LOB recovery timing (Microstructure Lab Substack) | TBD | Practitioner | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | Academic | PARTIALLY FETCHED |

**Undeployed priority stack (updated):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging (gating prerequisite for bps analysis)
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold (shares vol buffer with Tweak 76)
5. Tweak 78 — Gate hysteresis (ship as part of same changeset as Tweaks 75+76)
6. Tweak 79 — Tape intensity gate (independently deployable in shadow mode)
7. Tweak 74 — stale-gate per-cycle re-validation
8. Tweak 72 — funding-window gate
9. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
10. Tweak 71 — transient-order OBI filter
11. Tweak 80 — Quarter-hour proximity shadow log
12. **Tweak 81 — Robust volume Z-score shadow log** ← NEW (observe-only until direction confirmed)

**Structural situation unchanged:** The binding constraint (no speed, no queue position, no rebate) remains unaddressed. Tweak 81 adds a shadow-logging observation for a new orthogonal dimension (total trade volume magnitude) that may or may not correlate with adverse selection outcomes for ST2.0. Implementation cost is minimal; the shadow log answers whether volume bursts concentrate the adverse fills or whether they are neutral/beneficial. Tonight's academic sweep found no new uncovered peer-reviewed papers in the execution space — the literature available to this series is becoming saturated.
