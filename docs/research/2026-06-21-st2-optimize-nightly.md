# ST2.0 Execution Research — Nightly (2026-06-21)

**Scope:** New execution material only. Prior synthesis is 2026-06-20-st2-execution-research-synthesis.md —
read that first. Tonight focuses on gaps not yet covered: pre-entry quote-stability gating, trade-OFI vs
LOB-OFI distinction, post-entry cancellation mechanics, and a cross-asset adverse-selection corroboration.

---

## What Prior Reports Already Cover (skip to avoid duplication)

- Adverse selection by construction: fills cluster at imbalance extremes (arxiv 2502.18625, 1610.00261)
- Binance BTC perp imbalance-maker without cancellation: −0.47 bp mean over 8,851 trades
- Queue position: front −0.058 bp vs back −0.775 bp
- Speed requirement for cancel/reinsert cycles; Phemex latency is not competitive
- Rebate trap: Phemex rebate = 0, so δ = half-spread only, frequently beaten by adverse-selection β
- OFI-flip concept: wait for buy pressure to roll over before posting
- Post-offset / deeper-in-spread placement variants
- Fill predictability AUC: 0.72 @1min → 0.66 @10min

---

## What Is NEW Tonight

### 1. Pre-Entry "Crumbling Bid" Gate (CQI Principle)

**Verified source:** IEX SEC Release 34-89686 (2020, D-Limit order approval); updated mechanics in
IEX "Updating the Signal for Today's Markets" (iex.io/article/updating-the-signal-for-todays-markets).

**What the CQI does (verbatim from IEX's published description):**
IEX's Crumbling Quote Indicator fires when it detects:
- "Disappearing quotes on geographically significant venues"
- "Quote-size update bursts"
- "Locked or crossed markets"
- "Rapid-correlated quote changes"

When triggered, D-Limit orders automatically reprice ("get out of the way") and remain restricted
"for up to 2 milliseconds." V6 of the signal covers 54% of NBBO changes (up from 33% in prior versions)
while maintaining its true-positive rate. The signal processes top-of-book data from 11 venues.

**The ST2.0 analog (adaptation, not a direct port — CQI is US equities with multi-venue NBBO):**
Before posting the limit sell, measure bid-side stability in the prior 3–5 seconds of L2 updates:
- Has top-bid depth shrunk by ≥20% without a corresponding price uptick?
- Has the best bid ticked down ≥1 level since the signal fired?
If either condition holds, the bid-side is "crumbling" — the absorption pattern that ST2.0 shorts may
already be completing. Skip this posting attempt; re-evaluate next cycle.

**Caveat:** CQI uses 11-venue NBBO cross-correlation. Phemex is single-venue, so this is an approximation
using bid-depth velocity alone. Any threshold (20%, 1 tick) is uncalibrated — would need tuning on
Phemex L2 snapshots. The underlying logic (detect bid instability before posting a passive sell) is
sound and directly addresses ST2.0's known problem: posting into the moment of maximum adverse selection.

---

### 2. Trade-OFI Outperforms LOB-OFI for Entry Timing

**Verified source:** arxiv 2507.22712v1 — "Order Book Filtration and Directional Signal Extraction at
High Frequency" (Anantha, Jain, Maiti; July 2025, NSE India BankNifty futures).

**Key finding (verbatim from abstract):** "when filters are applied on the parent orders of executed
trades, the resulting OBI series exhibits systematically stronger directional association" and "OBI
computed using trade events exhibits stronger causal alignment with future price movements" compared to
LOB-derived OBI.

**The ST2.0 implication:** ST2.0 currently uses `ob.imbalance` (LOB-side snapshot) as its primary entry
gate. Buy_ratio and CVD (trade-flow based) may be more directionally predictive for timing. When the
two diverge — `ob.imbalance` is high-bid but buy_ratio / CVD are already rolling over — trust the
trade-flow signal. More concretely: require BOTH `ob.imbalance` above threshold AND `buy_ratio` starting
to decline (not just peak) before posting, rather than treating the imbalance snapshot alone as the
entry trigger.

**Caveat:** This paper studies NSE India equity futures, not crypto perps on Phemex. Structural
differences exist (auction vs. continuous, different participant mix). This is a directional hypothesis
for the forward-confirm lab, not a proven result. Practically, ST2.0 already tracks buy_ratio — this
is a filter weight change, not new instrumentation.

---

### 3. Post-Entry Cancellation on Persistent Informed Flow

**Partial source (UNVERIFIED from primary):** ScienceDirect "High Frequency Market Making: The Role of
Speed" (surfaced in search results, paywall-blocked — could not fetch full paper). Search result summary
states: "Liquidity providers and high-frequency traders may cancel orders due to increased fear of
adverse selection when observing market order arrivals, as they may fear the market order owner has
private information, with stronger signals from larger orders suggesting stronger fear of being picked off."

**The ST2.0 implication (labeled HYPOTHESIS — primary source unread):** Currently ST2.0 posts the
limit sell and holds until fill, timeout, or SL. An alternative: after posting, monitor ongoing taker
activity. If large_trade_bias stays > 0.4 AND buy_ratio stays > 0.6 for N consecutive seconds after
posting, the "absorption is real" thesis is failing in real time — cancel the order before it fills
under adverse conditions. This targets the documented asymmetry: losing fills happen when buying
continues (the signal is wrong); winning fills happen when buying pauses (the reversion starts).

**Caveat:** UNVERIFIED — primary source not read. Do not act on this without finding and reading the
actual paper. The logic is consistent with the prior synthesis, but the specific cancellation-trigger
implementation is untested.

---

### 4. Cross-Asset Adverse Selection Corroboration (Confirmatory)

**Verified source:** arxiv 2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure"
(Bieganowski & Ślepaczuk; submitted January 31, 2026, Binance Futures BTC/LTC/ETC/ENJ/ROSE,
Jan 2022–Oct 2025).

**Key finding (verbatim from abstract):** "the divergent performance of our taker and maker strategies
empirically validates classic microstructure theories of adverse selection and highlights the systemic
risks of algorithmic trading."

**What this adds:** The prior synthesis relied primarily on BTC perp data (arxiv 2502.18625). This 2026
paper extends the adverse-selection maker-loss result across 5 assets including smaller/less liquid names
(ENJ, ROSE). Maker strategies underperform takers even during normal markets; the divergence is
**cross-asset and stable** over a 3+ year period. This strengthens the prior conclusion that ST2.0's
adverse selection problem is not BTC-specific or a market-condition artifact.

**Caveat:** Full paper not fetched (abstract only). Specific strategy parameters and exact loss
magnitudes not verified. Adds cross-asset corroboration, not new tactics.

---

## Summary: 2 Concrete Forward-Testable Tweaks

These two are grounded in verified sources and adaptable to ST2.0 without new infrastructure:

**Tweak A — Crumbling Bid Pre-Entry Filter**
Implementation: In the ST2.0 entry check, compare top-bid depth and best-bid price in the last snapshot
vs 3 seconds prior (using ws_feed L2 data). If bid depth fell ≥ X% OR best bid dropped ≥ 1 tick in
the window, reject this entry cycle. Test on paper slot before any live change.
Source: IEX SEC Release 34-89686 + iex.io signal docs (verified). Threshold X = uncalibrated.

**Tweak B — Require Trade-OFI Confirmation on LOB Signal**
Implementation: Do not post when `ob.imbalance` is high-bid but `buy_ratio` is ≥0.6 AND NOT declining
over the last 2 cycles. Wait for buy_ratio to show a downward tick before treating the imbalance as
an absorption signal. Rationale: the trade-flow signal is more causally aligned with future direction;
a still-rising buy_ratio into a high imbalance may mean the absorption isn't complete yet.
Source: arxiv 2507.22712 (verified with caveat: Indian equity futures, not crypto perps).

---

## What Could Not Be Verified Tonight

- Post-entry cancellation mechanics (Tweak 3 above): primary source paywalled. Hypothesis only.
- Full text of Bieganowski & Ślepaczuk (2602.00776): abstract only — specific numbers unavailable.
- The Deribit "Toxic Flow" article was fetched but contained no actionable passive-maker tactics
  (focused on AMM/LP context rather than passive limit-order placement on perps).
- Quote-churn threshold for the CQI adaptation: the IEX model uses ML + 11-venue data; the
  single-venue approximation for Phemex requires calibration against real L2 feed data.

---

## Honest Assessment

The prior synthesis conclusion stands: **adverse selection on a passive short-reversion fill at small
size, slow, no rebate is structurally negative.** Tonight's material does not change that. What it adds:

- A mechanistically sound pre-entry filter (Crumbling Bid / CQI principle) that addresses the specific
  moment of maximum adverse selection — the instant of posting into a still-buying book.
- A signal-priority clarification (trade-OFI > LOB-OFI for timing) consistent with empirical finding
  across multiple markets.
- Multi-asset confirmation that maker adverse selection is stable and cross-asset, not a single-coin
  anomaly.

Low base-rate expectation: the Binance BTC maker strategy lost money *with* imbalance conditioning.
These tweaks narrow the entry timing; they do not eliminate structural adverse selection. Forward-test
via ST2.0 paper slot before any live configuration change.
