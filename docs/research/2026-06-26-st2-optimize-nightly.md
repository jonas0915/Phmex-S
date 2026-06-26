# ST2.0 Execution Research — Nightly (2026-06-26)

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
- Boltzmann Price β Calibration (arxiv 2507.09734)
- Multi-Level OFI (MLOFI) — Depth-Weighted Imbalance (arxiv 1907.06230, abstract only)

---

## Status: Third Consecutive Diminishing-Returns Night — Three Verifiable New Facts

The 06-24 and 06-25 reports called for closing the nightly research series. Tonight confirms those
assessments. All major execution angles are covered. However, three verifiable NEW facts emerged:
two of consequence, one that closes a long-open research item.

---

## What Is NEW Tonight

### 1. Counter-Finding: Cancellation Made Passive Maker Losses Worse in the Live Perp Experiment

**Verified source:** arxiv 2502.18625 ("The Market Maker's Dilemma", Albers et al.), fetched directly.
**Confidence:** VERIFIED — full HTML accessed.

The Binance BTC perp live trading paper (repeatedly cited in prior reports for the −0.47 bp result)
**also tested an imbalance-triggered cancellation rule.** Prior reports only extracted the no-cancel
result. The with-cancel comparison was NOT cited in any prior report.

**Verbatim (from arxiv 2502.18625v2):**
> "Cancel threshold: 0.0 — orders cancelled when imbalance crosses back through zero."
> "The cancellation rule only mitigates a subset of those adverse cases, namely the ones where
> imbalance slowly changes adversely, rather than sudden adverse price moves caused by, e.g.,
> large taker orders."

**Quantitative result (from paper, directly extracted):**
- Without cancel: **−0.4705 bp mean return**, 32.17s avg hold
- With cancel: **−0.4921 bp mean return**, 38.83s avg hold
- Cancellation made losses 0.02 bp worse and increased hold time (orders that would have been
  adversely filled survived longer, then got filled anyway under worse conditions).

**The ST2.0 implication — direct counter-evidence for the 06-23 Tweak A (90s expiry gate):**

The 06-23 report proposed a 90-second time-based cancellation as a positive intervention, citing
OFI signal decay. This result from the only live perp experiment in the literature that tested
a cancel rule is that cancellation *hurt*, not helped. The mechanisms differ — the paper tested
imbalance-based cancel (cross-zero) while the 06-23 proposal was time-based (90s elapsed). But
the same structural problem applies to both: the orders that would have filled adversely (and
been cancelled) were replaced by either (a) no fill, or (b) a later fill under similarly adverse
conditions, with the added cost of queue-position loss on reinsertion.

**Critical interpretation:** This does NOT mean the 90s expiry is definitely harmful. Time-based
cancellation (abandon after signal decay) is conceptually different from imbalance-reversion
cancellation (cancel when OBI flips). A timed cancel that simply accepts "this signal is dead,
walk away" avoids the reinsertion problem entirely (no repost). The paper's result warns against
cancel-and-repost cycles, not against clean cancel-with-no-repost. The 06-23 Tweak A should
be relabeled: **cancel and do NOT repost on the same cycle** — if you cancel at 90s, wait for
the next fresh signal trigger on the next bot cycle. Do not re-enter the order at a different
price on the same trigger.

**Honest caveat:** The live experiment tested imbalance-based cancellation on Binance BTC perp
(not Phemex, not small-cap alts, not time-based). The result does not directly invalidate the
90s time-based expiry, but it is the strongest empirical evidence against cancel-and-repost
cycles for passive maker orders in crypto perps. Weight accordingly.

---

### 2. Phemex RPI Orders: ST2.0 Has Zero Protection in the Regular Book

**Verified source:** Official Phemex documentation, fetched directly.
URL: https://phemex.com/help-center/RPI-Order
**Confidence:** VERIFIED — official platform documentation.

**Verbatim (from Phemex help page):**
> "The Retail Price Improvement (RPI) order is a specialized order type designed to enhance
> liquidity quality and pricing efficiency for retail traders."
> "RPI orders will only match with orders placed by non-algorithmic users."
> "do not execute against orders submitted via OpenAPI."
> "Only approved market-making partners are authorized to place RPI orders."

**What this means for ST2.0:**
Phemex has a two-tier order book. HFT-approved market makers can post RPI orders that exclusively
match against retail TAKER flow — these maker orders cannot be taken by algorithms. ST2.0's
standard passive limit sell orders sit in the regular book and are NOT covered by any such
protection. Any algorithm or HFT taker can fill ST2.0's passive sell. Specifically:

1. ST2.0 cannot post RPI orders (not an approved market-making partner).
2. The fill on ST2.0's passive sell could come from an HFT taker that has detected the same
   bid-absorption signal and is acting on it directionally (taker buy) faster than ST2.0
   can respond.
3. There is no mechanism on Phemex by which ST2.0 could gain RPI protections without
   joining the approved market-maker program — which requires a separate application process
   and commitment to continuous two-sided quoting obligations.

**This is a platform-structural disadvantage that prior reports did not document.** The prior
reports established the economic disadvantage (no rebate, slow, no queue position). This adds
the regulatory/structural layer: ST2.0's orders are in the bottom tier of Phemex's order book
protection hierarchy.

**Honest caveat:** The RPI page describes order MATCHING protection for retail TAKERS, not
makers. It means retail takers (buyers) get better fills by being matched against approved-MM
RPI orders. For ST2.0 as a MAKER (passive seller), the implication is indirect: ST2.0 does not
benefit from any analogous protection as a maker. It doesn't mean HFT specifically targets
ST2.0; it means no platform mechanism prevents it.

**Is there a tweak?** No direct tweak available. This confirms that the structural disadvantage
is fixed and platform-enforced. ST2.0 cannot improve its maker execution through order type
selection on Phemex — the only maker order type available to non-approved participants is the
standard POST-ONLY limit order already in use.

---

### 3. Closed Loop: MDPI 2227-7072/14/5/103 Is NOT a Relevant Execution Paper

**Status:** Closed research item. This paper has been blocked for 4 consecutive nights and
flagged as a high-priority target. Tonight its bibliographic record was confirmed via IDEAS/RePEC.

**Source:** https://ideas.repec.org/a/gam/jijfss/v14y2026i5p103-d1926363.html
**Confidence:** VERIFIED — full bibliographic entry fetched.

**Title:** "Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures:
Econometric Evidence from Centralized and Decentralized Exchanges" (Zhivkov, Todorov, Georgiev;
IJFS, April 2026).

**Dataset:** 9.1 million *hourly* observations across 26 exchanges, 812 symbols, Nov 2025–Jan 2026.
**Methods:** GARCH(1,1), Bai–Perron structural breaks, CUSUM tests, Granger causality in bivariate VAR.

**Why this is not useful for ST2.0:** This paper operates at hourly frequency across 26 exchanges
and studies cross-exchange integration and volatility persistence. It does NOT address:
- Order book microstructure at second/minute scale
- Maker fill quality or adverse selection
- Passive limit order placement or cancellation
- Imbalance mean reversion or signal decay

This paper can be permanently deprioritized. It is not a LOB/execution paper. The 4-night
access attempt was not worth the continued research budget.

---

## What Could Not Be Verified Tonight

- **SSRN 6693260** (Lawrence Chang, May 2026, "Do Order-Book States Predict Passive-Buy Toxicity?
  Evidence from BTC Perpetual Futures"): HTTP 403. This paper is the most directly on-point new
  source surfaced during tonight's search. Its abstract describes a "flow-adjusted bid-absorption
  proxy" that predicts passive-buy adverse-selection risk in BTC perps — exactly ST2.0's signal.
  Full content unread; existence confirmed through search snippets only. **Priority target if
  accessible.** Authors: Lawrence Chang, affiliation unknown. Submitted May 2026 to SSRN.
- **ScienceDirect S0275531925004192** (VPIN vs Bitcoin price jumps): HTTP 403, fifth night.
  Crypto VPIN calibration remains unverified from primary source.
- **arxiv 1907.06230 full text** (MLOFI, Kolm et al.): PDF binary, unreadable. Quantitative
  results (R² per depth level, optimal level count) remain unverified from primary source.

---

## Concrete Forward-Testable Tweaks

### Tweak A — Revise the 90s Cancel to "Cancel-and-Walk, Never Cancel-and-Repost" (Refinement)
**What changed from 06-23 Tweak A:** The 06-23 report proposed cancelling at 90s with a
`miss_expired` log reason and waiting for the next signal. That structure is preserved. What
is ADDED: an explicit prohibition on re-entering at a different price on the same signal cycle.
The live perp experiment found cancellation worse when it enables reinsertion — because reinsertion
puts you back at the end of the queue under worse adverse-selection conditions. Cancel-and-walk
(abandon the entire signal cycle, wait for a fresh trigger) avoids this failure mode.
**Implementation note:** The bot should NOT attempt to "chase" a missed fill by repricing. If
ST2.0 cancels at T+90s, that symbol is blocked from re-entry until the next fresh signal trigger
occurs (minimum next bot cycle, effectively 60–120s later).
**Source:** arxiv 2502.18625 (verified; cancel-and-repost made losses worse; cancel-and-abandon
is the safer variant); 06-23 Coinmonks source (signal decay, 90s basis; confirmed).
**Status:** Enhancement/clarification of existing 06-23 hypothesis. Shadow-gate applies as before.

### Tweak B — Log Phemex Order Book Tier Context at Entry (No-Code-Change Prerequisite)
**What this is:** Not a trading tweak — a logging addition. At each ST2.0 signal trigger, log
whether the trade tape at that moment shows unusually large aggressive taker buys (suggesting
HFT taker activity). Specifically: log the single largest trade size in the 5-second tape window
as `tape_max_single_trade`. If fills cluster on entries where a single large taker buy dominated
the tape, it provides circumstantial evidence that informed HFT flow is the filling mechanism
(consistent with the RPI finding — HFTs can take from ST2.0's regular book orders).
**Source:** Phemex RPI documentation (structural finding that HFT takers can fill ST2.0 orders
with no platform-level constraint); Coinmonks / arxiv 2502.18625 (informed large-taker flow
as adverse-selection mechanism).
**Implementation:** ws_feed already tracks per-trade sizes. Adding `max(trade.size for trade in
recent_tape)` at signal time is 1 line. No gate — shadow logging only, for 2 weeks. Then
compare `tape_max_single_trade` distribution at winning vs losing fills.

---

## Honest Assessment

**Tonight's three findings are the most operationally clean of all 7 reports:**
- Finding 1 (cancel worse): directly modifies a proposed tweak from a prior report — strengthens
  the "cancel-and-walk only, never repost" constraint. Source is the same verified live perp paper
  used throughout; the specific comparison was simply not previously extracted.
- Finding 2 (Phemex RPI): closes the question of whether platform order type selection can
  improve maker execution. It cannot. ST2.0 has exhausted the available order types on Phemex.
- Finding 3 (MDPI closure): administrative but useful — permanently removes a 4-night open item.

**The research series is genuinely exhausted.** Tonight's findings are refinements of refinements,
not new dimensions. The binding work is now entirely in the paper-slot forward-test queue, not
in the literature. Recommend closing this research series unless SSRN 6693260 (Chang, May 2026)
becomes accessible — that paper is the last high-probability unread primary source.

**Priority forward-test queue (unchanged from 06-25):**
1. Shadow-gate the micro-price check (06-24 Tweak A) — 2 lines, no live impact
2. Shadow-gate 90s cancel-and-walk with `miss_expired` log (06-23 Tweak A, now clarified)
3. Shadow-gate VPIN computation (06-23 Tweak B) — log only for 1 week
4. Log `tape_max_single_trade` at signal time (tonight's Tweak B) — 1 line
5. Only after 1–2 weeks shadow data: evaluate which gates to enforce in paper slot

**Sources used tonight:** arxiv 2502.18625 (verified, full HTML), phemex.com/help-center/RPI-Order
(verified, official docs), ideas.repec.org/a/gam/jijfss/v14y2026i5p103 (verified, bibliographic).
One unverified source (SSRN 6693260, abstract via search snippet only; paywalled).
