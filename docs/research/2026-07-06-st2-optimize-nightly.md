# ST2.0 Execution Research — Nightly Optimization Report
**Date:** 2026-07-06
**Night:** 10 of series
**Status:** Two new verified findings — one platform-structural (Phemex amendment endpoint), one market-microstructure (spoofable large bids in crypto LOBs)

---

## Context

Prior reports (06-20 synthesis through 06-30, nights 1–9) have covered: adverse selection by
construction, queue position mechanics, Phemex rebate = 0 / RPI access = 0, OFI-flip / micro-price
filter, CQI gate, trade-OFI timing, cancel-and-walk rule (never repost), VPIN, funding-window gate,
F&G regime logging, near-side ask queue thinness (q_near_at_post), queue size ratio (q_ratio),
and the universal −0.45 tick fill drift. The 06-30 report declared the academic literature
"genuinely exhausted." Tonight's sweep checks two angles prior reports did not investigate:
(a) whether Phemex's REST API supports in-place order amendment without cancel + reinsert,
and (b) whether the spoofability of large bids in crypto LOBs creates a new skip-gate hypothesis.

---

## (a) What's New vs. Prior Reports

| Angle | Prior Coverage | Tonight's Result |
|---|---|---|
| Phemex order amendment endpoint | Not checked in any prior report; the 06-26 report closed order-type selection as exhausted but did not check amendment. | **New finding** — endpoint exists and is supported by CCXT |
| Spoofability of large LOB bids | Not in any prior report | **New finding** — 31% of large near-best bids are spoofable; indirect adverse-selection implication |
| OFI velocity / second-order imbalance | Not covered | No usable primary source found (arxiv 2408.03594 covers Indian equities, abstract only, not applicable) |
| SSRN 6693260 (Chang 2026) | Blocked 9 prior nights | HTTP 403 again. Permanently inaccessible via WebFetch. |

---

## (b) New Forward-Testable Findings

### Tweak A: Phemex In-Place Order Amendment — Queue Position Unknown, Worth Verifying

**Sources:**
- Phemex official API reference: https://phemex-docs.github.io/ (verified — official Phemex documentation, fetched directly)
- CCXT issue #20910: https://github.com/ccxt/ccxt/issues/20910 (verified — GitHub, direct fetch)

**What was found:**

Phemex provides `PUT /orders/replace` — an "Amend Order by OrderId" endpoint that modifies a
resting order's price and/or quantity in-place, without a separate cancel + re-create cycle.

From the official Phemex API reference (directly fetched):
> "Amend order by order ID: PUT /orders/replace?symbol=<symbol>&orderID=<orderID>&price=<price>&orderQty=<orderQty>"

Amendable fields confirmed: price, quantity, stop price, take profit, stop loss, trailing offset.
Immutable fields confirmed: symbol, orderID.

**CCXT support:** CCXT's `phemex.edit_order()` wraps this endpoint. Per issue #20910, price
amendment (`priceRp` parameter) works correctly. Quantity amendment has a bug (wrong parameter
name `baseQtyEV` vs correct `orderQtyRq`) but price-only amendment is functional.

**Critical unknown — queue position:** The Phemex API documentation does NOT state whether a
price amendment preserves or resets queue priority. This is the pivotal question. The general
principle in FIFO exchange matching engines (CME, Nasdaq) is:

- Quantity decrease → queue position preserved
- Price change → queue position reset (order treated as new at the amended price level)

If Phemex follows FIFO convention, price amendment resets priority — equivalent to cancel +
reinsert but with one fewer API round-trip and no gap between cancel and reinsert. That is
still marginally useful (eliminates the reinsert latency gap during which the level may move).

If Phemex does NOT reset priority on price amendment (unusual), ST2.0 could reprice to chase
an adverse move while keeping queue rank — this would be a material execution advantage not
previously documented in any prior report.

**Why this matters for the cancel-and-walk rule (06-26):**
The 06-26 report established "cancel-and-walk, never cancel-and-repost" based on live perp
evidence that cancel + reinsert made losses worse (queue position loss on reinsert). The
amendment endpoint is a distinct mechanism — if it preserves queue position, the adverse
finding from 06-26 does NOT apply (there is no queue position loss to worry about).

**Forward-testable Tweak A:** Verify queue behavior empirically before any implementation:
1. Post a small test limit order on a low-activity pair (not ST2.0's active pairs) at a price
   far from market.
2. Wait until another order is posted at the same price level (visible in L2).
3. Call `edit_order()` with a trivial price change (e.g., ±1 tick) to amend.
4. Check L2 snapshot: is the amended order at the front or back of the new price level's queue?

If queue is reset (order moves to back): amendment is equivalent to cancel + reinsert. Still
useful as a single-call latency optimization but does NOT change the cancel-and-walk analysis.

If queue is preserved (unusual): this opens a new branch of implementation that bypasses the
06-26 restriction entirely.

**Implementation note:** The CCXT wrapper is `phemex.edit_order(order_id, symbol, type, side, amount, price)`. Price-only amendment: pass `amount=None` or the existing amount. Shadow verification required before any ST2.0 change.

**Caveat:** No literature or practitioner source verified Phemex-specific queue behavior on
amendment. The queue position outcome is empirically unknown. This is a verification task,
not a ready tweak.

---

### Tweak B: Spoofable Large Bids — New Skip-Gate Hypothesis

**Source:** arxiv 2504.15908, "Learning the Spoofability of Limit Order Books With Interpretable
Probabilistic Neural Networks," Challet et al., April 2025.
**URL:** https://arxiv.org/html/2504.15908v1
**Verification status:** VERIFIED — full HTML fetched directly.

**Direct quote from paper:**
> "Running this algorithm on all submitted limit orders in the period 2024-12-04 to 2024-12-07,
> we find that **31% of large orders could spoof the market.**"

**Key spoofability profile (from paper):**
> "orders of size Q≥50,000 USD and posting distance δ smaller than several basis points generate
> maximum impact."

The paper models a "spoofable" large bid as one that (a) is large relative to normal book depth,
(b) is posted within a few basis points of the current best bid, and (c) generates statistically
significant upward price pressure that is subsequently reversed on cancellation.

**Indirect ST2.0 implication:**

ST2.0 fires on bid-heavy books being aggressively absorbed (takers buying into the bid wall).
Genuine absorption (real buyers) → no reversion → adverse fill. But a significant fraction of
large bids near best price are spoofed: they create artificial imbalance, attract takers, then
are pulled. The post-cancellation snap-back is exactly what ST2.0 is trying to short.

However, the adverse-selection scenario arises when the spoofer's large bid is canceled while
ST2.0's passive sell is resting above: the bid wall disappears, the apparent buying pressure
that attracted aggressive takers evaporates, and if residual buyers continue pushing price up
through ST2.0's limit, the fill is adverse.

The new skip gate hypothesis: at signal time, if the dominant bid exhibits the spoofability
profile (size ≥ large relative to book, posting distance < threshold from best bid), skip or
shadow-flag the entry. Rationale: a spoof-driven imbalance signal is noisier than a genuine
absorption signal — it reflects artificial book pressure, not informed directional flow.

**Forward-testable Tweak B (shadow log only):**
At each ST2.0 signal trigger, log two fields:
1. `dominant_bid_size_ratio` = size of the largest resting bid within 3 bps of best bid /
   median bid size in the same range (measures "anomalously large" bid presence)
2. `dominant_bid_dist_bps` = posting distance of that largest bid from best bid in bps

After 20+ fills, test: do entries where `dominant_bid_size_ratio > threshold AND
dominant_bid_dist_bps < 3` show worse fill outcomes (lower WR or larger adverse post-fill
move in first 60 seconds)?

**Infrastructure:** ws_feed.py already tracks L2 book depth. Adding a function to snapshot
the top-5 bid levels at signal time and compute max size + distance is ~5 lines.

**Important caveats:**

1. **ST2.0 fires on absorption, not on posting.** Spoofed orders are canceled, not absorbed.
   If ST2.0's signal fires on actual taker buys hitting the bid, the dominant bid being
   absorbed is likely GENUINE (spoofers don't want to be filled). The spoofability angle
   applies to bids that exist in the book at signal time but may be canceled during the
   order's resting period — a more indirect path to adverse selection than it first appears.

2. **Size threshold mismatch.** The paper's spoofability threshold is ≥$50K USD. ST2.0 trades
   $150 notional on pairs like INJ, ARB, ENA. The book depth on these small-cap perps differs
   substantially from BTC perp on Binance. The $50K threshold does not transfer directly;
   a pair-specific "anomalously large" definition is needed.

3. **December 2024 crypto data on an unspecified exchange.** Likely Binance spot or large
   perp. Transfer to Phemex small-cap perps is an assumption.

4. **The paper measures spoofability of orders, not adverse selection suffered by passive
   sellers.** The adverse-selection implication for ST2.0 is this author's inference, not
   a direct result from the paper.

---

## (c) Caveats and Things Not Verified

- **SSRN 6693260 (Chang 2026):** HTTP 403 for the tenth consecutive night. This paper
  ("Do Order-Book States Predict Passive-Buy Toxicity?") remains the most directly
  on-point unread source in the series. Permanently inaccessible via WebFetch. Manual
  access or institutional library access is the only remaining path.

- **Phemex queue position on amendment:** Empirically unknown. Must be verified via a
  controlled test order before any implementation. Do NOT implement price-amendment-based
  repricing on live ST2.0 orders until queue behavior is confirmed.

- **arxiv 2504.15908 quantitative spoofability coefficients:** The 31% figure and the
  $50K / several-bps thresholds were extracted from the HTML. The classification model's
  precision, recall, and AUC for live detection were NOT in the fetched content — the paper
  describes a training-time algorithm, not a real-time classifier. Real-time spoofability
  detection is not directly actionable from this paper alone.

---

## Forward-Test Queue (Cumulative — All Nights)

| # | Tweak | Source Night | Status |
|---|---|---|---|
| 1 | Shadow-gate micro-price check (Boltzmann β=2) | 06-24 | Queued |
| 2 | Shadow-gate 90s cancel + `miss_expired` log (cancel-and-walk, never repost) | 06-23, clarified 06-26 | Queued |
| 3 | Shadow-gate VPIN computation | 06-23 | Queued (validity contested; exploratory) |
| 4 | Log `tape_max_single_trade` at signal time | 06-26 | Queued |
| 5 | Log `fg_regime` (Fear & Greed index) at signal time | 06-29 | Queued |
| 6 | Log `q_near_at_post` (ask queue size at target price at post time) | 06-30 | Queued |
| 7 | Log `q_ratio` (bid/ask queue mass ratio) at 1s intervals while resting | 06-30 | Queued |
| **8** | **Verify Phemex order amendment queue behavior (controlled test order)** | **07-06** | **Verification prerequisite — do before any implementation** |
| **9** | **Log `dominant_bid_size_ratio` + `dominant_bid_dist_bps` at signal time** | **07-06** | **Queued (shadow only; ~5 lines)** |

---

## Research Status

Ten nights. Tonight adds two findings not in any prior report: the Phemex amendment endpoint
(a platform capability that was simply never checked), and the spoofability profile of large
near-best bids (a new angle on what drives the imbalance signal ST2.0 uses). Both are at
the "shadow-log or verify" stage — neither is ready for live implementation.

The academic literature is genuinely exhausted. All remaining work is empirical: forward-testing
the 9-item queue above against real fill outcomes. SSRN 6693260 remains the only unread
high-probability primary source; check access periodically.
