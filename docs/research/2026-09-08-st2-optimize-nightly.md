# ST2.0 Maker Execution — Nightly Research (Night 67)
**Date:** 2026-09-08
**Researcher:** Claude (automated nightly sweep)

---

## Status: 3 NEW FINDINGS — First Night of Sep 8-12 Window

Prior 20 consecutive nights had 0 new confirmed findings. Tonight the Sep arXiv sweep and a broader
practitioner/journal search surfaced 3 applicable peer-reviewed sources not previously in the corpus.

---

## What's New vs Prior Reports

| # | Source | Status |
|---|--------|--------|
| arXiv:2602.00776 (Albers et al., Jan 2026) | **NEW — CONFIRMED** |
| arXiv:2608.21888 (Kitron & Wengrowicz, Aug 2026) | **NEW — CONFIRMED** |
| Albers et al. QF 25(6), Jun 2025 (SSRN:4677989) | **NEW — CONFIRMED** (different paper from arXiv:2502.18625) |
| arXiv:2605.06405 (Le, May 2026) | NEW — background only |
| arXiv:2608.04373 (Zhai, Aug 2026) | NEW — NOT APPLICABLE (DEX/wallet) |
| Sep 2026 arXiv q-fin (35 papers) | 0 new applicable papers |

---

## New Sources — Verified Findings

### 1. arXiv:2602.00776 — "Explainable Patterns in Cryptocurrency Microstructure"
Albers, Cucuringu, Howison, Shestopaloff. Submitted Jan 31, 2026.
Source: https://arxiv.org/html/2602.00776v1
Data: Binance Futures perpetual order books and trades, 1-second frequency, Jan 1, 2022–Oct 12, 2025.

**Verified quotes:**

> "all p-values exceed 0.05, so the null hypothesis of zero mean returns cannot be rejected"
(Section 7.3 — on passive maker strategy returns across full dataset)

> "wider spreads associate with attenuated predictive effects and lower-confidence signals,
in line with elevated adverse selection risk" (Section 6)

> During the Oct 10, 2025 flash crash, the maker strategy "was repeatedly filled on its
bid-side quotes" while "there was no corresponding fill on the ask side" (Section 8.4) —
one-sided fill is the canonical adverse selection signature.

**ST2.0 relevance:** The wide-spread → adverse selection finding is direct empirical grounding for
Candidate Tweak 45 (spread_pct gate). One-sided fill is measurable from ST2.0's existing logs
(all ST2.0 fills are ask-side sells; a session with fills but no reversions = one-sided adverse
selection window). The p > 0.05 maker returns across the full 3-year dataset is consistent with
the synthesis finding of -$0.12/trade.

---

### 2. arXiv:2608.21888 — "Short-horizon mean reversion in cryptocurrency markets: a matched cross-market measurement"
Nadav A. Kitron, Jonathan M. Wengrowicz. Submitted Aug 22, 2026.
Source: https://arxiv.org/abs/2608.21888
Data: 183 Binance pairs vs 187 US stocks/ETFs at 15-minute horizons.

**Verified quotes:**

> "90% of 183 Binance pairs carry significant directional reversal against 2.7% of 187
US stocks and ETFs."

> "The reversal concentrates after moves driven by aggressive taker flow and grows with
flow intensity, while the order-book depth a move consumes conditions nothing."

> "The gross edge peaks near 1.3 bp per trade against a 5 bp round-trip cost."

**ST2.0 relevance (important nuance):** The second quote directly bears on the OB imbalance gate vs
tape gate priority:

- "The order-book depth a move consumes conditions nothing" — the imbalance of *resting depth*
  in the book does NOT predict the 15-min reversal.
- "The reversal concentrates after moves driven by aggressive taker flow" — the *sign and intensity
  of taker aggression* (buy_ratio, CVD) is the predictive variable.

This suggests the existing tape buy_ratio gate (0.45/0.55) is more informationally targeted than the
OB imbalance gate (±0.25). It also means a ST2.0 fill that happens during aggressive taker buying
(high buy_ratio) is being adversely selected into that taker momentum — the signal is real, but
the fill itself arrives at the worst point in the 15-minute window.

At 1.3 bp gross edge vs 5 bp round-trip: confirms the edge exists but is below execution costs
at current fill rates — consistent with synthesis.

---

### 3. Albers, Cucuringu, Howison, Shestopaloff — "The good, the bad and latency: exploratory trading on Bybit and Binance"
Quantitative Finance, Vol. 25, No. 6, pp. 919-947. Published Jun 24, 2025.
Source: https://ora.ox.ac.uk/objects/uuid:cdab1de2-7576-42e2-abae-ab12371eba76
SSRN: https://ssrn.com/abstract=4677989 (blocked; ORA page verified)
Data: Millions of market orders and marketable limit orders on Bybit and Binance.

**Verified quotes (from Oxford ORA page):**

> "a large-scale live trading experiment involving the placement of millions of market orders
sent at a high frequency on two cryptocurrency exchanges"

> "a consistent disadvantage to the trader, pointing to an adverse selection effect for taker
orders: profitable orders tend to achieve worse-than-expected outcomes"

> For marketable limit orders: "a substantial probability of failing-to-fill-immediately"

> "Discrepancies between the actual and expected outcomes are...strongly correlated with market
factors such as volatility, latency, and LOB liquidity."

**ST2.0 relevance (re-peg vs cancel question):** When a post-only order fails (would cross) and is
repriced to become a marketable limit order, this paper's finding that marketable limit orders carry
"a substantial probability of failing-to-fill-immediately" — and that adverse selection spikes with
volatility — is the best available empirical evidence on the re-peg question. Repricing a failed
post-only into aggressive territory during volatile/low-liquidity conditions is likely to fail
anyway, making cancel-and-wait the defensible default. No dedicated re-peg vs cancel study exists.

---

## 2-4 Concrete, Forward-Testable Execution Tweaks

### Tweak 48 — Spread-spike cancellation gate (elevates Candidate 45)
**What:** When the current bid-ask spread_pct exceeds the rolling 90th percentile (per symbol), do
not submit the ST2.0 entry. If already submitted and spread spikes before fill, cancel and reset.

**Rationale:** arXiv:2602.00776 (verified): "wider spreads associate with attenuated predictive
effects and lower-confidence signals, in line with elevated adverse selection risk." The flash-crash
one-sided fill (all fills, no corresponding reversions) was a wide-spread event. This gate blocks
entry during the regime most likely to produce adverse fills.

**Forward test:** Log spread_pct at every attempt (already identified as Candidate Tweak 45);
after 30+ attempts, compute WR and post-fill markout stratified by spread_pct decile. Gate at
90th pct if adverse selection is concentrated there.

**Risk:** Zero — pure instrumentation step (log spread_pct) before any gating is deployed.
Gating decision made post-calibration.

---

### Tweak 49 — Tape buy_ratio gate tightening (informed by 2608.21888)
**What:** ST2.0 requires buy_ratio > 0.55 to confirm absorption (tape confirms aggressive buying
before the short entry). arXiv:2608.21888 shows the reversal "grows with flow intensity" — higher
buy_ratio = stronger eventual reversal, but also higher adverse selection risk at fill time
(you are filling into peak momentum). The currently fixed threshold (0.55) is not calibrated.

**Rationale:** The paper separates two effects: (a) higher taker intensity → larger eventual
reversal (good for the signal), but (b) the fill happens at the worst point in the reversal
window (adverse selection). The optimal gate may be higher than 0.55 to wait for taker flow to
exhaust, or it may require a time-delay filter (post-peak, not peak).

**Forward test:** Log `buy_ratio_at_entry` for every fill. After 30+ fills, plot post-fill 5-min
markout vs buy_ratio_at_entry decile. If WR improves at buy_ratio > 0.65 or > 0.70 (taker
exhaust level), tighten the gate. If WR is flat, keep current threshold.

**Risk:** Zero — log buy_ratio_at_entry first (already partially available from tape logging);
no threshold change until calibration data exists.

---

### Tweak 50 — Cancel-and-wait over re-peg for failed post-only orders
**What:** When ST2.0's post-only sell order fails (venue rejects because it would immediately
cross the bid), CANCEL and enforce a 30-second wait before resubmitting at the updated ask,
rather than repricing aggressively.

**Rationale:** Albers et al. QF 25(6) (verified): marketable limit orders (what a repriced
post-only becomes) carry "a substantial probability of failing-to-fill-immediately" with
adverse selection that correlates with volatility. A failed post-only means the book moved
toward you — volatile moment — which is exactly the regime where repriced marketable limits
fail. Cancel-and-wait costs a missed fill but avoids a fill at a worse price with no maker
protection and no rebate.

**Forward test:** Tag every entry attempt that fails post-only validation; log outcome (did bot
cancel, did it reprice, what was the eventual fill/no-fill result). After 20+ events, compare
outcomes. Note: this is observable in existing logs if post-only failures are logged.

**Risk:** Minimal — if cancel-and-wait is already the default behavior, this is a verification
step only. If bot currently reprices, the change is a single conditional in bot.py.

---

## Caveats and Unverified Claims

1. **arXiv:2602.00776 full paper:** Maker strategy return p-values and flash-crash case study are
   from the HTML version; Section numbers may differ in final published version. Claims cited
   verbatim from the arxiv.org HTML. CONFIRMED.

2. **arXiv:2608.21888 full paper:** The "1.3 bp vs 5 bp" edge figure and "OB depth conditions
   nothing" quote are from the abstract only; full paper not fetched. The 1.3 bp figure may
   be specific to a subset of pairs or conditions. Marked CONFIRMED but with caveat that
   abstract-only access limits depth of interpretation.

3. **Albers et al. QF 25(6) full paper:** SSRN:4677989 is blocked (consistent with Night 64
   note). ORA page confirms publication, journal volume/issue, and abstract quotes. Full
   empirical tables (fill rates, adverse selection magnitude) not accessible. Marked CONFIRMED
   for existence and abstract claims only.

4. **Re-peg vs cancel empirical data:** No peer-reviewed study exists on this specific question
   as of Sep 8, 2026. Tweak 50 recommendation is based on indirect inference from Albers
   et al., not a direct measurement. Forward-test is the only way to verify.

5. **September 2026 arXiv:** Fully sparse as of Sep 8 (35 papers reviewed, 0 applicable).
   The Sep 8-12 window may yet yield papers; nightly sweeps should continue.

---

## Cumulative Queue Status

- Confirmed tweaks: 44 (prior) + 0 net new confirmed = **44 confirmed**
- Candidates: 45, 46, 47 (prior) + 48, 49, 50 (tonight) = **6 candidates**
- Conditional: 43 (SSRN blocked) = 1 conditional
- Tonight's additions elevate Candidate 45 (spread_pct gate) with direct empirical backing from
  arXiv:2602.00776; Tweaks 48-50 are candidates pending instrumentation.

## Undeployed Priority Actions (unchanged from Night 66)

1. `time_to_fill` logging (N64) — 5 lines Python
2. `spread_pct` logging at every attempt (Candidate Tweak 45 / Tweak 48) — 2 lines Python
3. `v_prior_sell` logging (Candidate Tweak 46) — 2 lines Python
4. `queue_rank_at_fill` logging (Candidate Tweak 47) — 2 lines Python
5. Deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14

**Standing recommendation:** Resume sweeps — Sep 8-12 window is now active. Three new confirmed
sources tonight after 20-night drought. Continue nightly until Sep 12, then reassess.
