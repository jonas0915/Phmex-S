# ST2.0 Execution Research — Nightly (2026-06-23)

**Scope:** New execution material only — no repetition of prior reports.
Prior covered: CQI pre-entry filter, trade-OFI vs LOB-OFI, post-entry cancellation (unverified
hypothesis), cross-asset adverse selection corroboration, queue position, speed, rebate trap,
OFI-flip timing, deeper-in-spread placement, fill predictability AUC decay, funding-cycle adverse
selection gate, negative drift of limit order fill (arxiv 2407.16527), post-fill adverse drift
diagnostic for confirm.py.

---

## What Prior Reports Already Cover (skip to avoid duplication)

- Adverse selection by construction: fills cluster at extreme imbalance (arxiv 2502.18625, 1610.00261)
- Binance BTC perp imbalance-maker without cancellation: −0.47 bp mean over 8,851 trades
- Queue position: front −0.058 bp vs back −0.775 bp; speed requirement for cancel/reinsert
- Phemex rebate = 0; δ = half-spread only, frequently beaten by adverse-selection β
- OFI-flip concept; post-offset / deeper-in-spread variants
- CQI / Crumbling Bid pre-entry gate (IEX SEC Release 34-89686)
- Trade-OFI outperforms LOB-OFI for entry timing (arxiv 2507.22712)
- Post-entry cancellation on persistent informed flow (unverified hypothesis, paywalled primary)
- Fill predictability AUC: 0.72 @1min → 0.66 @10min (deep-lob-2021)
- Cross-asset adverse selection stability (arxiv 2602.00776)
- Funding-window gate: U-shaped adverse selection around 00:00/08:00/16:00 UTC (SSRN 4218907)
- Negative drift of limit order fill: 100% fill rate on adverse moves (arxiv 2407.16527)

---

## What Is NEW Tonight

### 1. OFI Signal Half-Life in Crypto Perps: ~120 Seconds

**Source:** "Meta-Order Flow in Crypto Perps: Catching Big Whale," Lucas Astorian /
Tigro Blanc, Coinmonks/Medium (fetched directly). **SECONDARY SOURCE — blog post, not
peer-reviewed.** The author presents data from testing OFI-based signals on crypto perpetuals
(BTC, SOL, others). No primary paper DOI identified.

**Fetched findings (verbatim from content):**
- Information coefficient at 10 seconds: **IC = 0.127, t-stat = 6.86**
- By 60+ seconds: "fast decay; by 120s, signal edge is near zero"
- Best observed reading: **SOL at 120 seconds, 1.66 bps gross** (BTC 30s: **0.42 bps gross**)
- Assuming 4 bps round-trip taker cost: "all tested configurations are negative net"
- Even under maker rebate of 0.2 bps, "realistic adverse selection costs of approximately
  0.56 bps per side eliminate profitability in most cases"
- Conclusion quoted: "useful as an execution and microstructure signal, not as a standalone
  taker alpha strategy"

**The ST2.0 implication — NEW, not stated in prior reports:**
Prior reports established AUC decay (0.72 @1min → 0.66 @10min), but only as a general fill
predictability measure. Tonight's finding provides a *causal* decay estimate for the OFI signal
itself: the absorption pattern ST2.0 reads at entry time T has **near-zero predictive power by
T + 120 seconds.** ST2.0 then holds the posted limit order for up to 15 minutes — 13+ minutes
of holding on a dead signal.

This provides the first **quantified basis** for the previously-unverified post-entry
cancellation hypothesis from prior reports. Rather than "cancel on persistent buying" (which
requires a new threshold), the simpler version is: **cancel the limit order if not filled within
~90 seconds of posting.** At T+90s the original OFI basis of the entry is statistically
exhausted. If the fill hasn't happened, the setup no longer exists — and holding converts the
trade into a naked position with no edge.

**Caveat (IMPORTANT):** This is a blog post, not a peer-reviewed paper. The IC numbers are
asserted without showing the underlying dataset, methodology, or whether tests survive multiple
comparisons. The directional claim (fast OFI decay in crypto) is consistent with the previously
verified deep-lob-2021 AUC curve, which gives this confidence. The specific number (120s to
zero) should be treated as a plausible order-of-magnitude estimate, not a calibrated threshold.
The 90s cancellation trigger requires forward-testing on our paper slot — do not deploy to live
trading without that test.

---

### 2. VPIN Pre-Entry Toxicity Gate (Compute from Existing ws_feed)

**Source:** buildix.trade, "What Is VPIN? Flow Toxicity Detection for Crypto Traders" (fetched
directly). **SECONDARY SOURCE — practitioner blog, not peer-reviewed.** References the original
Easley, López de Prado, O'Hara VPIN framework (primary: "Flow Toxicity and Liquidity in a
High Frequency World," NYU Stern, available at stern.nyu.edu/sites/default/files/assets/
documents/con_035928.pdf — not fetched tonight, see caveat below).

**VPIN definition and computation (fetched, verbatim):**
VPIN = Volume-Synchronized Probability of Informed Trading. Computed by:
1. Group trades into **fixed-volume buckets** (not time buckets)
2. Classify each trade as buyer-initiated or seller-initiated via the **tick rule**
3. Compute **moving average of absolute order imbalance** across the last N buckets:
   `VPIN_t = (1/N) × Σ|V_buy - V_sell| / V_total` per bucket

**Fetched thresholds (practitioner-calibrated, not canonical):**
- **VPIN > 0.7**: "a disproportionate amount of volume is coming from one side — directional
  move may be imminent"
- **VPIN > 0.8**: combined with low OBI, indicates potential liquidation cascade

**The ST2.0 implication — NEW:**
Prior reports established trade-OFI and buy_ratio as entry signals, and CQI-style bid-depth
velocity as a pre-entry filter. VPIN adds a complementary pre-entry toxicity check that is:
(a) **volume-synchronized** (not time-gated, so robust to variable-speed markets);
(b) computed directly from our existing ws_feed trade tape (ws_feed already collects trade-by-trade
data with direction classification);
(c) interpretable as a toxicity level rather than a directional signal.

The gate: if VPIN > 0.7 when the bot is about to post a limit sell, the order flow is dominated
by aggressive directional volume. An ST2.0 short in this environment is posting into a runaway
bid — not an absorption setup. Skip this cycle.

**Why VPIN > buy_ratio alone:** buy_ratio is a snapshot over a rolling time window. VPIN is
volume-normalized across fixed-sized buckets, which means a single large aggressive trade
doesn't distort it the way it can distort a time-windowed buy_ratio. VPIN measures *sustained
directional composition*, not just instantaneous flow.

**Compute from ws_feed:** The ws_feed already maintains per-trade records with size and direction.
Computing VPIN requires accumulating a rolling sum of `|buy_vol - sell_vol| / total_vol` per
fixed-volume bucket, then averaging across the last N buckets. This is a ~20-line addition to
the existing tape/flow infrastructure — no new data feed.

**Caveat:** The buildix.trade thresholds (>0.7, >0.8) are practitioner rules of thumb for
unnamed crypto venues. The primary Easley et al. paper was not fetched tonight (NYU Stern PDF;
the seminal paper studies E-Mini S&P 500 futures, not crypto perps). The crypto-venue calibration
of these thresholds requires testing against our own ws_feed data. The original VPIN framework
has also been criticized for sensitivity to bucket size N and tick-rule misclassification; these
issues compound in fast crypto markets. Treat as a candidate filter requiring paper-slot
calibration before live deployment.

---

## What Could Not Be Verified Tonight

- **Kwan (2025) RL paper on dynamic limit order submission** (Stern SMC 2025): HTTP 404 on the
  direct PDF link. Could not access. Potentially relevant for optimal repricing/cancellation
  timing — worth a future fetch attempt via a direct search for Amy Kwan's name.
- **Primary VPIN paper (Easley et al., NYU Stern):** Not fetched tonight. The PDF URL
  (stern.nyu.edu) was confirmed in search results but not read. The core VPIN framework is
  well-established in academic literature, but the specific calibration for crypto perps is
  absent from the primary source.
- **ScienceDirect 2025 Bitcoin wild moves / VPIN paper (S0275531925004192):** Paywalled; not
  fetched. Abstract indicates it directly studies VPIN vs. Bitcoin price jumps — likely the best
  primary source for crypto VPIN calibration. Priority for tomorrow night if continuing this line.
- **arxiv 2412.07461 (passive market impact theory):** Full text fetched but yielded only theory
  (no closed-form solution, no implementable thresholds). Not actionable in isolation.
- **T-KAN alpha decay paper (arxiv 2601.02310):** Fetched but uses FI-2010 equity data, not
  crypto. No OBI decay rates applicable to Phemex.

---

## Concrete Forward-Testable Tweaks

### Tweak A — 90-Second Limit Order Expiry Gate (NEW)
**Implementation:** After posting the ST2.0 limit sell, start a 90-second timer. If the order
is not filled within 90 seconds of posting, cancel it and mark the attempt as `miss_expired`
(not `miss_no_fill`). Do NOT re-enter on the same signal cycle — wait for the next fresh signal.
**Rationale:** The OFI signal underlying the absorption entry has near-zero predictive power by
T+120s (Coinmonks secondary source, consistent with prior deep-lob-2021 AUC decay). Holding
past 90s is holding on a dead signal with full adverse-selection exposure.
**Source:** Coinmonks/Medium (secondary source, not peer-reviewed; consistent with prior verified
AUC decay data). IC near-zero at 120s → 90s gives a 30s execution buffer.
**Risk:** Could reduce fill rate further. But fills beyond 90s are almost certainly fills on
signals the bot already lost — quantify with the paper slot before any live change.
**Log requirement:** New exit reason `miss_expired` must be logged for the paper slot to measure
whether 90s fills vs. >90s fills have different WR. This is the instrumentation that makes the
forward test measurable.

### Tweak B — VPIN Pre-Entry Toxicity Gate (NEW)
**Implementation:** Add a rolling VPIN calculation to ws_feed (or to the bot's tape-check
function). Compute VPIN using fixed-volume buckets from ws_feed's trade stream. Before posting
any limit sell: if `VPIN > 0.7`, skip this cycle. Log gate rejections as `skip_vpin`.
**Rationale:** High VPIN means the current order flow is disproportionately directional
(aggressive buying continuing). Posting a passive sell into this is likely posting into informed
flow, not absorption.
**Source:** buildix.trade (secondary, practitioner thresholds); VPIN framework from Easley et
al. (not fetched; primary exists). Threshold 0.7 is practitioner-calibrated, not canonical.
**Risk:** Threshold uncalibrated for Phemex. Start by logging VPIN at each signal trigger
(shadow gate) for 1 week before enforcing it. Only block entries after observing the distribution
of VPIN values and their correlation with ST2.0 outcomes.

---

## Honest Assessment

**Tonight's two findings are lower-confidence than prior nights** because both primary sources
are secondary (blog posts, not peer-reviewed papers). That said:

**Tweak A (90s expiry)** is the stronger of the two. The directional logic is grounded:
the synthesis + tonight's data both confirm rapid OFI decay, and the cancellation was already
flagged as a hypothesis from prior reports. Tonight provides the first *number* (90-120s) that
gives it calibration basis. Implementation risk is low (cancellation-only, no new gates). This
should be the next instrumented paper-slot test.

**Tweak B (VPIN gate)** is conceptually sound but practically uncertain. The computation is
implementable from existing ws_feed data. The threshold is not calibrated for Phemex. The correct
next step is a shadow gate (log VPIN values without blocking) for 1 week, then correlate against
ST2.0 outcomes. Do not enforce it blind.

**Cumulative picture:** Five nightly reports have now covered the main dimensions of passive
execution improvement:
- Pre-entry: CQI/crumbling bid, trade-OFI confirmation, funding window, VPIN
- At-entry: deeper-in-spread placement, OFI-flip wait
- Post-entry: 90s expiry, cancellation on persistent flow
- Diagnostic: post-fill adverse drift in confirm.py

The literature is approaching exhaustion on genuinely new angles at this scale (small, slow,
no rebate, Phemex). Diminishing returns are real — nightly reports are now surfacing secondary
sources rather than fresh peer-reviewed findings. The bottleneck has shifted from research to
forward-testing: the paper-slot lab now has enough hypotheses to run for 2-4 weeks.
