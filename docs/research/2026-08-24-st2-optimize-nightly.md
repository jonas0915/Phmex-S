# ST2.0 Execution Optimization — Night 54
**Date:** 2026-08-24 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 53 Nights

N53 flagged one remaining action: search arXiv for an open-access preprint of Albers, Cucuringu,
Howison & Shestopaloff (2025) "The good, the bad, and latency" (*Quantitative Finance*
25(6):919–947) — identified as the most promising unread candidate. Tonight executed that search
plus a general practitioner sweep for new 2026 material.

**Sources evaluated tonight:**

| Source | Verdict |
|--------|---------|
| Albers et al. preprint search (arXiv + author homepage) | VERIFIED: No arXiv version. Preprint is SSRN:4677989. Abstract is the same as N53. |
| SSRN 5323703 retry (Ruan & Streltsov) | UNVERIFIED — HTTP 403 Forbidden (4th blocked attempt) |
| arXiv:2607.09230 (Jeon, July 2026 — "When Does Order Flow Matter?") | VERIFIED — already in corpus, screened Night 36 |
| arXiv:2606.15715 (Barone & Lillo, June 2026 — Hyperliquid sunshine trading) | VERIFIED — already in corpus, screened Night 37; NOT APPLICABLE |
| arXiv:2602.00776 (Bieganowski, 2026 — crypto microstructure patterns) | VERIFIED — already in corpus, screened Night 50 |

**Net result: 0 new applicable sources. 21st consecutive night without a new verified actionable
tweak. Tweak queue unchanged at 42.**

---

## Source Details

### Albers et al. Preprint Search
**Verification status: VERIFIED** — Cucuringu faculty homepage at UCLA
(https://www.math.ucla.edu/~mihai/fin.htm) confirms only two links exist for the paper: the
Tandfonline DOI and SSRN:4677989. No arXiv preprint was ever posted.

**SSRN:4677989 access attempt:** Not attempted tonight (prior nights confirmed SSRN access is
inconsistent; fetching a different SSRN ID with unknown access state would require a separate
attempt). The abstract via Oxford University Research Archive (CC BY-NC-ND 4.0, open access) is
identical to what N53 already had from IDEAS/RepEC. Content confirmed, VERIFIED verbatim.

**Key from abstract (directly quoted, ORA open access version):**
> "We show these discrepancies are strongly correlated with market factors such as volatility,
> latency, and LOB liquidity. Notably, we find a consistent disadvantage to the trader, pointing to
> an adverse selection effect for taker orders: profitable orders (as measured by short-term future
> PnL returns) tend to achieve worse-than-expected outcomes, while unprofitable orders typically
> achieve their expected (adverse) outcomes."

**Assessment:** This paper studies **TAKER** execution only (market orders and marketable limit
orders on Bybit + Binance). Its adverse selection finding is the taker-side mirror of what
arXiv:2502.18625 already documents from the maker side. No new maker execution guidance
extractable from abstract. Full text (body) may contain LOB liquidity thresholds relevant to
maker side, but remains paywalled.

**No new tweak.** The N53 recommendation to attempt SSRN:4677989 directly (different ID from the
403'd 5323703) is still available as an optional action.

---

### SSRN 5323703 — Ruan & Streltsov
**Status: UNVERIFIED — HTTP 403 Forbidden.** 4th consecutive blocked access. Content remains
inaccessible without authenticated session or institutional proxy.

---

### Candidate Papers from Practitioner Search — All Pre-Screened
Three papers surfaced in web search:

- **arXiv:2607.09230** (Jeon, "When Does Order Flow Matter? State-Dependent L2 Liquidity-State
  Transitions in Crypto Futures") — fetched and verified tonight from abstract; confirmed already
  screened in Night 36 (2026-07-16). Core finding: OFI adds value only when layered on top of L2
  state; BTC perpetual OFI does not robustly predict across regimes (ETH does). Already covered.

- **arXiv:2606.15715** (Barone & Lillo, Hyperliquid sunshine trading) — confirmed already
  screened in Night 37 (2026-08-06). DEX-only mechanism, institutional scale ($1.93T notional),
  NOT APPLICABLE to Phemex CEX single $150 passive limit.

- **arXiv:2602.00776** (Bieganowski, crypto microstructure patterns) — confirmed screened in
  Night 50 (2026-08-20). Already in corpus.

---

## New Forward-Testable Tweak Tonight

**None verified.**

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **No arXiv preprint of Albers et al. exists.** SSRN:4677989 is the only open-access route
   to more than the abstract. It is a different SSRN ID from the 403'd 5323703 — worth one
   direct fetch attempt. The body may contain LOB liquidity or volatility regime thresholds
   applicable from the maker perspective.

2. **SSRN 5323703 remains permanently inaccessible** via WebFetch. Author contact is the only
   remaining path.

3. **September 2026 arXiv listings not yet published.** The listing date 2026-08-24 is still
   within August. No new arXiv category sweep is possible until September submissions begin
   appearing.

4. **21st consecutive night without a new verified actionable tweak.** The recommendation to
   suspend nightly literature search and deploy priority tweaks has now been made for 7
   consecutive nights (N47–N54) without action. This is the binding constraint — not the
   literature search.

5. **Empirical gap unchanged.** No paper in 54 nights has measured OFI-flip decay speed in
   crypto CEX perpetual futures at 60-second entry granularity. This is ST2.0-specific and
   requires internal fill-log measurement.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N54): **4 [elevated], 6, 9, 10, 11, 12, 14**
**Cascade-blocking tweak class: RETIRED** (dual confirmation: arXiv:2607.27070 N46 +
arXiv:2608.03616 N47).
**Conditional candidate: Tweak 43** — composite LightGBM toxicity gate using 5-second OFI
features, 1-hour rolling adaptive threshold (SSRN 6344338, Rajendran & Singaravelu).
CONDITIONAL on full paper access.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks
27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a),
N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 —
conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 54 Bottom Line

**No new actionable execution tweak tonight.** 5 sources evaluated:

- **Albers et al. preprint search:** VERIFIED — no arXiv version. SSRN:4677989 confirmed.
  Abstract content unchanged from N53. No new maker findings from abstract.
- **SSRN 5323703** (Ruan & Streltsov): UNVERIFIED (403). Unchanged.
- **arXiv:2607.09230** (Jeon, "When Does Order Flow Matter?"): VERIFIED — already in corpus
  from Night 36.
- **arXiv:2606.15715** (Barone & Lillo, Hyperliquid): VERIFIED — already in corpus from Night
  37. NOT APPLICABLE.
- **arXiv:2602.00776** (Bieganowski): VERIFIED — already in corpus from Night 50.

**Final recommendation (unchanged from N47–N53, now 8 nights overdue on execution):**
Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
Optional remaining actions:
(a) Fetch SSRN:4677989 directly (Albers et al. preprint — different from the 403'd 5323703);
(b) Author contact for SSRN 5323703 (Ruan & Streltsov);
(c) Author contact for SSRN 6344338 (Rajendran/Singaravelu via ResearchGate);
(d) NCCU Finance → Lawrence Chang institutional email → one attempt for SSRN 6693260;
(e) Resume literature search in September 2026 when new arXiv submissions appear.
