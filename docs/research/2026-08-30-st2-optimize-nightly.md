# ST2.0 Execution Optimization — Night 58
**Date:** 2026-08-30 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 57 Nights

N57 confirmed all four August 2026 arXiv q-fin categories fully screened, September 2026
window not yet open, and the recommendation to suspend nightly search had been standing for
11 consecutive nights. Tonight's scope:

1. **arXiv September 2026 listings** — all four categories re-checked (q-fin.TR/ST/PR/CP)
2. **Four targeted practitioner/academic searches** — new angle combinations
3. **SSRN:7162966 ("Neutrinos")** — alternative access paths (Cucuringu homepage, Scholar)

**Net result:** 2 new-to-corpus papers found (arXiv:2607.09230 and arXiv:2606.05882). 1 new
SSRN companion paper series identified (Albers et al. 2026, 3-paper set). **1 partially
applicable finding from arXiv:2607.09230** — "L2 state first" principle from real Binance
BTC/ETH perpetual data. No fully verified actionable tweak at the level of prior corpus
papers. Tweak queue updated to **43 (pending further review)** pending Jonas decision on
whether the L2 state finding clears the forward-test bar.

---

## Sources Evaluated Tonight

### arXiv September 2026 — All Four Categories
**Status: VERIFIED** — all four listings fetched directly.

| Category | URL Fetched | Result |
|----------|-------------|--------|
| q-fin.TR | arxiv.org/list/q-fin.TR/2026-09 | "No updates for this time period." |
| q-fin.ST | arxiv.org/list/q-fin.ST/2026-09 | "No updates for this time period." |
| q-fin.PR | arxiv.org/list/q-fin.PR/2026-09 | "No updates for this time period." |
| q-fin.CP | arxiv.org/list/q-fin.CP/2026-09 | "No updates for this time period." |

September 2026 arXiv submission window has not opened as of 2026-08-30. No new papers
available. All four categories will be swept when September submissions appear.

---

### arXiv:2607.09230 — NEW TO CORPUS
**Title:** "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in
Crypto Futures"
**Author:** Joohyoung Jeon
**Submitted:** July 10, 2026
**Source URL:** https://arxiv.org/abs/2607.09230
**Status: VERIFIED — abstract fetched directly.**

**Data:** Binance BTCUSDT and ETHUSDT perpetual futures, 2023–2026. (CEX data ✓)

**Key finding (direct paraphrase from abstract as fetched):** "The first-order predictive
signal is the pre-event L2 liquidity state." Order flow (OFI) "demonstrates predictive
value only when incorporated atop L2 state models, and shows asymmetric performance across
assets — proving robust for ETH across various market conditions but yielding minimal gains
for BTC."

**The proposed principle (author's framing):** "state-first design principle for market
microstructure models" — L2 book state should be verified before order flow features are
used as the primary signal.

**Relevance to ST2.0:**

The paper studies Binance BTC/ETH perps (same asset class, CEX — analogous to Phemex).
ST2.0 currently gates on top-of-book OB imbalance (a single-level OFI metric). The Jeon
finding says:

1. **L2 state is the first-order signal, not OFI alone.** If the pre-placement L2 depth
   state is not in a confirming regime, OFI-based entries are weaker predictors. ST2.0 is
   posting a passive SELL based on OFI absorption — but the paper says OFI only matters
   *when* L2 state already confirms it.

2. **ETH robust, BTC minimal.** This maps directly to ST2.0's empirical fill split (synthesis:
   ETH ~59% fill rate, BTC ~30%). The same asset-level asymmetry in OFI predictive power
   appears in real Binance data.

**Honest limitation:** The paper studies *liquidity-state transition prediction* (a supervised
classification task), not maker fill adverse selection directly. The connection to ST2.0's
execution problem is inferential: "if L2 state is unfavorable, the OFI signal that triggered
the entry is less reliable → the fill you get at that moment is more adversely selected."
This is plausible and consistent with the core corpus (arXiv:2502.18625's back-of-queue
adverse selection) but not a direct measurement of passive fill quality.

**Potential Tweak 44 (CANDIDATE — not yet elevated):**
> Before posting the passive maker SELL, check a multi-level L2 depth condition (not just
> current top-of-book imbalance). If L2 state is not in a confirming regime (e.g., depth
> at levels 2–5 is eroding vs. reinforcing the bid-side pressure), skip the entry or wait
> one cycle. Expected effect: filter the subset of OFI-triggered entries that are placing
> into an unfavorable book state — which the paper implies are the lower-quality signals
> (especially on BTC). Forward-test metric: fill rate and post-fill adverse selection
> by L2-state-confirmed vs. not.
>
> Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp, 2023–2026 real data, abstract
> verified).
>
> **Caveat:** "confirmed" means the abstract was fetched. The full methodology — which
> L2 levels, which state definition, what time granularity — requires reading the full
> paper before this tweak can be specified numerically.

**Assessment: NEW TO CORPUS. PARTIALLY APPLICABLE. Full paper read needed for
parameter specification.**

---

### arXiv:2606.05882 — NEW TO CORPUS
**Title:** "Market Informedness and Market-Maker Profitability: The Trade-Off Between
Adverse Selection and Price Discovery"
**Authors:** Konrad Ochędzan, Nino Antulov-Fantulin
**Submitted:** June 4, 2026 (v1); June 17, 2026 (v2)
**Source URL:** https://arxiv.org/abs/2606.05882
**Status: VERIFIED — abstract fetched directly.**

**Method:** Agent-based model with heterogeneous learning agents; prices emerge endogenously.
**NOT real crypto exchange data.**

**Key finding:** "Informed market order flow is particularly harmful when aggregate market
informedness is low, exposing market makers to severe adverse-selection risk." Profitability
generally improves as informedness increases: "the price-discovery benefits of informed
trading can offset its adverse-selection costs."

**Why NOT a new actionable tweak:**
- Agent-based simulation, no real CEX perpetual data. The parameters (heterogeneous agent
  learning rates, inventory risk preferences) have no direct mapping to Phemex mechanics.
- The finding is directionally consistent with the existing corpus (adverse selection from
  informed flow) but adds no new threshold or mechanism beyond what arXiv:2502.18625 already
  established from real Binance data.

**Assessment: NEW TO CORPUS. NOT APPLICABLE — simulation only, no actionable parameter.**

---

### SSRN:7162966 ("Neutrinos") + Companion Papers — Status Update
**SSRN:7162966 ("Neutrinos of the Order Book"):** HTTP 403 again. UNVERIFIED. No change
from N55.

**NEW: Two companion papers identified from Cucuringu homepage (https://www.math.ucla.edu/~mihai/fin.htm):**

1. **"An Open Book: Level 4 Order Book Data from the Hyperliquid Exchange"** — Albers,
   Cucuringu, Howison, Shestopaloff, 2026. SSRN. NOT APPLICABLE (DEX data). NEW TO CORPUS.

2. **"The Price Impact of Nothing: Rejected Orders as Predictors of Future Returns"** —
   Albers, Cucuringu, Howison, Shestopaloff, 2026. SSRN. NEW TO CORPUS. Potentially
   relevant — rejected post-only orders predicting future returns — but UNVERIFIED (403) and
   dataset is Hyperliquid (on-chain DEX, where rejected messages are visible on-chain).
   On Phemex (opaque CEX), a trader can observe their own post-only rejections but not other
   participants' rejections. Mechanism transfer requires CEX-specific confirmation.
   CONDITIONAL on SSRN access.

**No PDF links publicly available for any of the three "Neutrinos" series papers.**

---

### Practitioner Sweep — 4 Search Angles
**Searches run (all verified via web search tool):**
1. `passive limit order fill adverse selection OFI timing crypto perpetual CEX 2026 maker execution`
2. `post-only maker order placement timing book imbalance flip reversion crypto perpetual 2026 arxiv`
3. `arxiv 2026 september q-fin limit order adverse selection maker fill optimization`
4. `"post-only" "queue position" maker adverse selection crypto perpetual execution tweak 2026`

All results were either: already in the 57-night corpus, excluded as DEX-only, excluded as
non-primary (educational/blog), or one of the two new papers reported above.
Practitioner search is saturated.

---

## New Forward-Testable Tweak Tonight

**Candidate Tweak 44 (PENDING):** L2 depth regime check before posting passive maker SELL.
See arXiv:2607.09230 section above for full specification and caveats.

**Not yet elevated to the full queue until full paper is read.**

**Tweak queue: 42 confirmed + 1 candidate (Tweak 44) = 43 pending Jonas review.**

---

## Honest Caveats

1. **arXiv:2607.09230** (Jeon, Binance BTC/ETH perp, 2023–2026) is the one genuinely
   new-to-corpus, partially applicable find tonight. The abstract is verified; the full
   paper methodology is not yet read. The L2-state-first principle is real but its
   operational translation to ST2.0 requires reading the full paper to determine which L2
   levels and what state definition the author uses.

2. **SSRN remains universally blocked** (403 on all IDs: 4677989, 5323703, 6344338,
   6693260, 6772279, 7162966). Author contact is the only remaining path.

3. **A third companion paper in the Albers/Cucuringu series** ("The Price Impact of
   Nothing") was found tonight and is NEW TO CORPUS. It is blocked (SSRN 403). If
   accessible, its claim that mechanically rejected post-only orders predict future returns
   is directly relevant to ST2.0's entry timing (a flood of rejected post-only orders before
   entry = a signal of quote-stuffing or anticipatory positioning that worsens queue state).

4. **The empirical gap remains the binding constraint.** No paper in 58 nights has measured
   OFI-flip decay speed at 60-second granularity in a crypto CEX perpetual. Still requires
   internal fill-log measurement from the bot's own data.

5. **September 2026 arXiv window not yet open.** Next viable arXiv sweep: first week of
   September.

---

## Cumulative Forward-Test Queue (42 confirmed, 1 candidate)

**Priority tweaks (unchanged from N20–N57): 4 [elevated], 6, 9, 10, 11, 12, 14**
**Cascade-blocking tweak class: RETIRED** (arXiv:2607.27070 N46 + arXiv:2608.03616 N47).
**Candidate Tweak 44:** Multi-level L2 depth regime check as pre-placement gate
(arXiv:2607.09230, Jeon, Binance BTC/ETH perp — full paper read required).
**Conditional Tweak 43:** Composite LightGBM toxicity gate (SSRN:6344338, blocked).
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks
27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a),
N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37),
N37 (Tweak 38).

---

## Night 58 Bottom Line

**1 new partially applicable finding tonight.** 6 sources evaluated:

- **arXiv q-fin.TR/ST/PR/CP September 2026** (all four): VERIFIED. Empty. Window not open.
- **arXiv:2607.09230** (Jeon, "L2 state first", Binance BTC/ETH perp, real data):
  **NEW TO CORPUS. PARTIALLY APPLICABLE.** L2 depth state is first-order predictive signal;
  OFI only adds value atop it. ETH robust, BTC minimal — matching ST2.0's fill asymmetry.
  Candidate Tweak 44. Full paper read required before numerical specification.
- **arXiv:2606.05882** (Ochędzan & Antulov-Fantulin, market informedness, agent-based):
  **NEW TO CORPUS. NOT APPLICABLE** — simulation, no real crypto CEX data.
- **"The Price Impact of Nothing"** (Albers et al. 2026, Hyperliquid rejected orders):
  **NEW TO CORPUS. UNVERIFIED (403). DEX context.** Potentially relevant mechanism
  (rejected post-only orders predicting returns) but not verifiable and not CEX-applicable
  without further access.
- **"An Open Book"** (Albers et al. 2026, Hyperliquid L4 data): NEW TO CORPUS. NOT
  APPLICABLE (DEX data description paper).
- **Practitioner sweeps (4 angles):** All results already in corpus or non-primary.

**arXiv coverage as of Night 58:**
- q-fin.TR August 2026: COMPLETE (N51, 17 papers)
- q-fin.PR August 2026: COMPLETE (N53, 12 papers)
- q-fin.ST August 2026: COMPLETE (N53, 28 papers)
- q-fin.CP August 2026: COMPLETE (N56, 31 papers)
- q-fin.* September 2026: EMPTY — submission window not yet open

**Updated optional actions:**
(a) SSRN:5323703 author contact (Ruan & Streltsov);
(b) SSRN:6344338 author contact (Rajendran/Singaravelu via ResearchGate);
(c) NCCU Finance → Lawrence Chang institutional email → one attempt for SSRN:6693260;
(d) SSRN:4677989 author contact (Albers et al. "good, bad, latency");
(e) SSRN:7162966 author contact (Albers et al. "Neutrinos");
**(f) [NEW] Full read of arXiv:2607.09230 (Jeon, open access) to specify Tweak 44
    numerically — which L2 levels, what state definition, what granularity.**
**(g) [NEW] SSRN:7162966 companion — "The Price Impact of Nothing" — author contact for
    CEX applicability of the rejected-orders-predict-returns finding.**

**Recommendation (unchanged since N47, now 12 nights overdue on execution):**
Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
Read arXiv:2607.09230 full paper (open access) and specify Tweak 44.
Resume arXiv sweep in September 2026 when new submissions appear.
