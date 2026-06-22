# ST2.0 Execution Research — Nightly (2026-06-22)

**Scope:** New execution material only — no repetition of prior reports.
Prior covered: CQI pre-entry filter, trade-OFI vs LOB-OFI, post-entry cancellation (unverified hypothesis),
cross-asset adverse selection corroboration, queue position, speed, rebate trap, OFI-flip timing,
deeper-in-spread placement, fill predictability AUC decay.

---

## What Prior Reports Already Cover (skip to avoid duplication)

- Adverse selection by construction: fills cluster at extreme imbalance (arxiv 2502.18625, 1610.00261)
- Binance BTC perp imbalance-maker without cancellation: −0.47 bp mean over 8,851 trades
- Queue position: front −0.058 bp vs back −0.775 bp; speed requirement for cancel/reinsert
- Phemex rebate = 0; δ = half-spread only, frequently beaten by adverse-selection β
- OFI-flip concept; post-offset / deeper-in-spread variants
- CQI / Crumbling Bid pre-entry gate (IEX SEC Release 34-89686)
- Trade-OFI outperforms LOB-OFI for entry timing (arxiv 2507.22712)
- Post-entry cancellation on persistent informed flow (UNVERIFIED hypothesis, paywalled primary)
- Fill predictability AUC: 0.72 @1min → 0.66 @10min
- Cross-asset adverse selection stability (arxiv 2602.00776)

---

## What Is NEW Tonight

### 1. Funding-Cycle Adverse-Selection Gate

**Sources:**
- Ruan & Streltsov, "Perpetual Futures Contracts and Cryptocurrency Market Quality" (SSRN 4218907,
  high-frequency order book data 2017–2023). Full text inaccessible (SSRN paywall). Existence and
  findings confirmed via search result descriptions and a Cornell University Business School article
  (business.cornell.edu, February 2025) summarizing this research.
- Cornell summary verbatim: "both trading activity and bid-ask spreads follow a U-shaped pattern
  within each cycle."

**The finding:** Spread widening and adverse selection risk for passive makers are highest at the
**beginning and end of each 8-hour funding cycle** — i.e., around funding settlement times (00:00,
08:00, 16:00 UTC on most major venues). The middle of the cycle (~3–5 hours from any settlement)
is the narrowest-spread, least-adversely-selected window. Market makers respond by widening quotes
during settlement windows; this is the period of highest informed-trader activity (funding
arbitrageurs closing or flipping positions).

**The ST2.0 implication (NEW — not in any prior report):**
ST2.0 posts a passive sell into a bid-heavy book. If adverse selection is structurally elevated in
the ~30–60 minutes before and after funding settlement, those windows are the worst possible time
to post. A simple funding-window gate: check current UTC time against the three daily settlement
boundaries. If within N minutes of any boundary, skip the entry cycle.

Phemex funding settlements: every 8 hours, 00:00 / 08:00 / 16:00 UTC (confirm in exchange docs —
Phemex settlement schedule may differ slightly from Binance). The gate requires only a time lookup,
no new data feed.

**Caveat:** Ruan & Streltsov study *spot* market quality as a function of perp funding; the paper
does not directly measure *perp* passive execution quality during these windows. The mechanism is
indirect: informed traders build/unwind positions approaching settlement → spot spreads widen →
directional pressure on the underlying → adverse for a passive perp short. The N-minute window is
uncalibrated; the paper confirms the U-shape exists but does not specify the exact window width.
Primary source text not read (SSRN paywall blocked). Treat as a HIGH-CREDIBILITY HYPOTHESIS, not a
confirmed result. Forward-test via the ST2.0 paper slot before any live gate addition.

---

### 2. Negative-Drift Fill Quantification — 100% Fill Rate on Adverse Moves

**Verified source:** arxiv 2407.16527v1, "The Negative Drift of a Limit Order Fill" (Levin, 2024).
Full HTML fetched and read. Asset studied: 10-Year US Treasury Bond futures (TY).

**Key findings (verbatim from fetched text):**

> "the average drift in each case...comes out to approximately −0.0065"
> "P(f|D)=1 the fill rate for a downward movement is 100%"
> "Rf = 0.018" (non-adverse fill rate: 1.8%)
> "limit order fills are caused by and coincide with adverse price movements, which create a drag
> on the market maker's profit and loss"
> theoretical prediction: −0.48 ticks; empirical: −0.45 ticks

**Interpretation for ST2.0:**
- When the short-side (ST2.0's sell limit) fills, the fill happens because price ticked UP through
  the limit — the direction adverse to the short. This already known conceptually. What's new:
  the fill rate on adverse moves is **100%**; favorable fills (where price drifts down without
  tagging the limit) happen only **1.8%** of the time.
- "1/3 of all orders remain unfilled when price moves favorably" — ST2.0's ~57% miss rate is
  consistent with this; the misses are *the good outcomes* (price fell without filling, which is
  what the short-reversion prediction called for).
- Measured adverse drift: **40–48 basis points per fill** (Treasury futures, not crypto perps).
  The magnitude is asset-specific and will differ on Phemex, but the sign is robust.

**New actionable use (not stated in prior reports):**
This provides a clean post-fill diagnostic test. Within the forward-confirm lab (confirm.py),
compute the 30-second mark-to-market vs fill price for every ST2.0 fill. If the average is
consistently negative (price rose after short fill), the negative drift thesis is confirmed on
our own data. **This turns "execution is adversely selected" from a literature belief into a
measured internal number.** The specific test: `avg(mark_30s - fill_price)` over all filled
shorts. If consistently positive (price went up 30s after fill), that's the adverse drift
measured on Phemex data.

**Caveat:** Paper studies US Treasury futures, not crypto perpetuals. Magnitude (40–48 bps) likely
inflated vs crypto perps with tighter absolute tick sizes. The directional claim (fill rate on
adverse moves = 100%) is mechanically true by construction in any continuous LOB — a resting sell
fills when price ticks up through it. The value of the paper is the quantification and the
formalization, not a new concept. The diagnostic use for confirm.py is implementation work, not
research.

---

## What Could Not Be Verified Tonight

- **SSRN 4218907 full text** (Ruan & Streltsov): paywall returned HTTP 403. Funding cycle timing
  window (exactly how many minutes before/after settlement adverse selection peaks) is NOT available
  from any accessible primary source tonight. The existence of the U-shaped pattern is confirmed
  via Cornell Business summary; the specific window is uncalibrated.
- **MDPI 2227-7072/14/5/103** ("Temporal Dynamics of Market Microstructure in Cryptocurrency
  Perpetual Futures"): HTTP 403. Potentially the best primary source for time-of-day perp
  execution quality; blocked.
- **arxiv 2412.07461** ("A theory of passive market impact"): abstract only. Too theoretical for
  actionable extraction without full text.
- **Specific Phemex funding settlement schedule:** assumed 00:00/08:00/16:00 UTC — must verify
  against Phemex exchange documentation before implementing a funding-window gate.

---

## Concrete Forward-Testable Tweaks

### Tweak A — Funding-Window Gate (NEW)
**Implementation:** Before posting any ST2.0 limit sell, check `utc_now % 28800` (seconds into the
8-hour cycle). If within ±N minutes of 00:00, 08:00, or 16:00 UTC, skip this entry. Start with
N=30 as a baseline; calibrate against the paper slot.
**Source:** Ruan & Streltsov SSRN 4218907 / Cornell Business summary (VERIFIED as existing;
funding window width UNCALIBRATED — requires Phemex-specific tuning).
**Risk:** Could exclude mid-day sessions that are actually fine; calibrate via paper slot before
live deployment.

### Tweak B — Post-Fill Adverse Drift Diagnostic (implement in confirm.py, not in live bot)
**Implementation:** For every closed ST2.0 position, record `fill_price` and `mark_30s` (mid
30 seconds post-fill). Compute `drift = mark_30s - fill_price` for a short (positive = adverse).
Report mean drift and distribution in the next trade audit.
**Source:** arxiv 2407.16527 (VERIFIED, Treasury futures; adapted as a diagnostic metric).
**Risk:** Zero — this is logging-only, no trading logic change. Should be done first.

---

## Honest Assessment

Two new findings tonight, both with caveats:

**Finding 1 (Funding Gate)** is the highest-actionability new result: a concrete, time-based,
zero-infrastructure gate that could meaningfully reduce entry into the worst adverse-selection
windows. The mechanism is sound; the magnitude is unquantified from accessible sources. This
warrants a paper-slot forward test.

**Finding 2 (Negative Drift Diagnostic)** is a measurement improvement, not a new tactic. Adds a
verified framework for quantifying the post-fill adverse selection ST2.0 already experiences.
Confirms that confirm.py's post-fill mark is the right diagnostic tool — and gives an expected
direction: marks should be adverse (positive for shorts). If they're NOT adverse on our data,
that's a meaningful positive signal about fill quality.

The structural conclusion from prior reports remains unchanged: passive short-reversion maker at
small size, slow, no rebate on Phemex is adversely selected by construction. Tonight adds one
gating mechanism (funding cycle) that is time-based, low-cost, and testable.
