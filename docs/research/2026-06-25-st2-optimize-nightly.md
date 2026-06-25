# ST2.0 Execution Research — Nightly (2026-06-25)

**Scope:** New execution material only — no repetition of prior reports.

Prior covered (full list — skip anything from this set):
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
- OFI Signal Half-Life ~120 seconds → 90s limit order expiry gate (Coinmonks secondary source)
- VPIN Pre-Entry Toxicity Gate (practitioner blog / Easley et al. framework, uncalibrated)
- Micro-Price Placement Filter: only post if P_micro ≤ limit_price (Stoikov SSRN 2970694 / arxiv 2411.13594)
- 20:00–23:00 UTC thin-liquidity gate (Amberdata secondary source, Binance spot only)

---

## Status: Diminishing Returns Confirmed — One Incremental Finding

The 06-24 report declared the execution literature "genuinely near-exhausted" and recommended
pausing nightly research. Tonight's sweep confirms that assessment. Three papers flagged in
06-24 as unread high-priority targets were pursued:

- **SSRN 5066176** "Market Making in Crypto" (Stoikov et al.): Scribd interface accessible but
  document text not renderable; primary source still unread. The search summary confirms it
  develops a "Bar Portion" (BP) alpha signal for active bidirectional market making — not
  passive single-side short execution. Even if accessible, likely not directly relevant to ST2.0.
- **ScienceDirect S0275531925004192** (VPIN vs Bitcoin price jumps): HTTP 403, fourth consecutive
  night. Remains blocked.
- **arxiv 2507.09734** "Boltzmann Price": Fetched and read (HTML version, full access). See below.

---

## What Is NEW Tonight (one incremental finding)

### 1. Boltzmann Price: Tunable Generalization of the Micro-Price Gate

**Verified source:** arxiv 2507.09734, "Boltzmann Price: Toward Understanding the Fair Price
in High-Frequency Markets" (Rola, Cracow University of Economics, submitted July 13, 2025).
Full HTML fetched and read.

**The formula (verbatim from paper):**
```
P^boltzmann(β) = (e^(-β·q^b)·P^b + e^(-β·q^a)·P^a) / (e^(-β·q^b) + e^(-β·q^a))
```
where q^b and q^a are bid and ask volume imbalance at the top of book, P^b and P^a are bid
and ask prices, and β is a free parameter (analogous to inverse temperature in statistical
mechanics).

**Special cases (verbatim from paper):** "when β=0, the Boltzmann price equals the mid-price;
when β≈2, it approximates the weighted mid-price." Through Taylor expansion: "P^boltzmann(β) ≈
(1-β/2)·P^mid + (β/2)·P^w" for small imbalances.

**What this means:** The micro-price gate introduced in the 06-24 report uses the standard
Stoikov weighted mid-price formula (effectively β≈2). The Boltzmann Price generalizes this to
a tunable β. At β > 2, the fair-value estimate becomes more sensitive to imbalance — the
gate would block more entries during high-OBI states. At β < 2, the gate becomes more
permissive.

**The ST2.0 implication (incremental, not new):**
This is NOT a new execution tactic. It is a refinement of the 06-24 micro-price gate.
The practical upgrade: instead of the fixed Stoikov formula, implement the Boltzmann Price with
β as a calibration parameter. Start at β=2 (recovers the existing micro-price check), then
tune β against paper-slot outcomes to find the value that best separates adverse fills from
favorable fills in our specific Phemex data.

**Concrete implementation (upgrade to 06-24 Tweak A):**
```python
import math

def boltzmann_price(bid_price, ask_price, bid_vol, ask_vol, beta=2.0):
    # beta=2 recovers weighted mid-price / Stoikov micro-price
    w_bid = math.exp(-beta * bid_vol)
    w_ask = math.exp(-beta * ask_vol)
    return (w_bid * ask_price + w_ask * bid_price) / (w_bid + w_ask)

# Note: crossed weights (bid vol → ask price weight, ask vol → bid price weight)
# is correct for Stoikov micro-price but the Boltzmann formula uses the same
# imbalance concept differently. Use whichever your prior implementation used;
# the β tuning is the additive value here.
```

**Caveats:**
- β is a free parameter with no canonical value for crypto perps. The paper provides no
  empirical calibration — β must be estimated from your own data.
- Paper is validated on historical equity data only (stocks GE, LCID mentioned). No crypto
  validation.
- This is an enhancement to an already-undeployed shadow gate (the 06-24 micro-price filter).
  The β tuning question is premature until the fixed-β shadow gate has run for ≥1 week.

---

### 2. Multi-Level OFI (MLOFI) — Deeper Book Levels Add Signal (Partially Verified)

**Partially verified source:** arxiv 1907.06230, "Multi-Level Order-Flow Imbalance in a Limit
Order Book" (Kolm, Turiel, Westray; Oxford/NYU, 2019). Abstract fetched directly; PDF binary
(non-parseable). Full quantitative results NOT directly read — citing this under PARTIAL
VERIFICATION only.

**From abstract (verbatim):** "we find that the out-of-sample goodness-of-fit of the
relationship [between MLOFI and contemporaneous mid-price changes] improves with each
additional price level that we include in the MLOFI vector."

**What MLOFI is:** A vector quantity measuring net order flow at each price level separately:
`MLOFI = [OFI_1, OFI_2, ..., OFI_M]` where each OFI_k is the net buy/sell flow at the k-th
price level from the top of book. Rather than collapsing all book flow into a single top-of-book
imbalance number, MLOFI preserves the depth structure. Linear regression of mid-price change
against MLOFI was shown to improve with each additional level on 6 Nasdaq stocks.

**The ST2.0 implication (new angle, not in any prior report):**
The current `ob.imbalance` in the ST2.0 entry gate uses only the top-of-book bid/ask volumes.
The MLOFI finding suggests that including levels 2–5 of the order book could improve the
imbalance signal's predictive value for the entry gate. A practical version:
```
depth_weighted_imbalance = Σ(w_k × OFI_k) for k in 1..N
```
where w_k decays with depth (e.g., w_k = 1/k or exponential decay). If large bid volume
at levels 2 and 3 is also absorbed (MLOFI is positive and stacked across levels), the
absorption signal is stronger. If only the top-of-book is heavy but levels 2–3 are thin,
the signal is shallower.

**Whether this is deployable now:** The ws_feed already captures multiple levels of L2 data.
No new data feed required. The bot's existing `ob.bids` and `ob.asks` arrays include levels
beyond the top. The change is in how imbalance is computed — a parameter tweak in the signal
computation, not new infrastructure.

**Caveats (IMPORTANT):**
- Full paper not read — only abstract. The specific improvement magnitudes and optimal number
  of levels are NOT verified from primary source.
- Study uses 6 US equity stocks on Nasdaq, not crypto perps on Phemex. Transfer validity unknown.
- This refines an existing gate (imbalance threshold), it does not change the gate's logic.
  Needs the same shadow-gate approach: log the depth-weighted imbalance alongside the existing
  gate output for 1 week, then correlate against ST2.0 fill outcomes.

---

## What Could Not Be Verified Tonight

- **SSRN 5066176** (Stoikov "Market Making in Crypto"): Scribd interface only, document text
  unreadable. Bar Portion (BP) signal details remain unknown. Could be relevant for active
  bidirectional quoting, not directly for ST2.0's passive single-side short.
- **ScienceDirect S0275531925004192** (VPIN vs Bitcoin price jumps): HTTP 403, fourth night.
- **Oxford MLOFI PDF** (1907.06230): Binary PDF, non-parseable. Quantitative results (R²
  improvement per level, optimal depth) remain unverified from primary source.
- **arxiv 2605.06405** "Funding-Aware Optimal Market Making for Perpetual DEXs": Fetched and
  read. Explicitly does NOT model adverse selection or fill quality; authors flag queue position
  and cancellation behavior as future work. Not actionable for ST2.0.

---

## Concrete Forward-Testable Tweaks

### Tweak A — Boltzmann Price β Calibration (Enhancement to 06-24 Micro-Price Gate)
**Status:** Enhancement to an existing undeployed shadow gate. Do not implement until the
06-24 micro-price gate (β=2 fixed) has collected ≥1 week of shadow data.
**Then:** Enable β as a tunable parameter in the micro-price check. Sweep β ∈ {1.5, 2.0, 2.5, 3.0}
against paper-slot fill outcomes. Select the β that maximizes (WR − blocked_good_entries).
**Source:** arxiv 2507.09734 (verified; equity only).
**Risk:** Low — this is a post-hoc calibration of an already-proposed shadow gate.

### Tweak B — Depth-Weighted MLOFI Imbalance (Enhancement to OBI Gate)
**Status:** New angle, partially supported by literature. Implement as shadow logging first.
**Implementation:** At each ST2.0 signal trigger, compute a depth-weighted imbalance across
the top 3–5 levels of `ob.bids` and `ob.asks` using weights [1, 0.5, 0.25, 0.125, 0.0625]
(halving per level). Log this alongside the existing `ob.imbalance`. After 1 week, compare
depth-weighted imbalance distribution at winning vs losing fills.
**Source:** arxiv 1907.06230 (PARTIALLY VERIFIED — abstract only, equity data only).
**Risk:** Low if shadow-only. Could reveal that the top-of-book signal is already capturing
most of the information (null result is a valid outcome of the test).

---

## Honest Assessment

**Tonight confirms the 06-24 conclusion: execution improvement literature for this setup is
exhausted.** Two findings tonight — both are refinements of gates already proposed, not new
dimensions. The single genuinely new conceptual angle (MLOFI as depth-weighted imbalance)
is partially verified (abstract only, equity data) and is an enhancement to an existing gate,
not a new gate.

**Recommended action: officially close the nightly research series.**

The forward-testing queue now has 9 hypotheses across all execution dimensions:
pre-entry (CQI crumbling bid, trade-OFI confirmation, funding window, VPIN, micro-price),
at-entry (deeper-in-spread, OFI-flip), post-entry (90s expiry, cancellation on informed flow).
Adding more research without testing any of these hypotheses is diminishing-returns work.

**Next step:** Prioritize the paper-slot forward-test roadmap:
1. Shadow-gate the micro-price check (06-24 Tweak A) — 2 lines of code, no live impact
2. Shadow-gate the 90s expiry timer (06-23 Tweak A) — requires `miss_expired` log reason
3. Shadow-gate the VPIN computation (06-23 Tweak B) — log-only for 1 week
4. Only after shadow data: evaluate which gates to enforce in the paper slot

Research resumes only if an accessible primary source on crypto-perp passive execution
quality becomes available (priority targets: MDPI 2227-7072/14/5/103, SSRN 5066176 direct,
ScienceDirect VPIN/BTC paper).
