# ST2.0 Execution Optimization — Night 55
**Date:** 2026-08-25 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 54 Nights

N54 completed the arXiv preprint search for Albers et al. "The good, the bad, and latency"
(confirmed no arXiv version; SSRN:4677989 blocked). Tonight's scope:

1. **SSRN:4677989 direct fetch** — Albers et al. preprint (final outstanding action from N54)
2. **arXiv q-fin.TR September 2026 listing** — checked for any new submissions
3. **Broad practitioner sweep** — 4 targeted search angles not run in recent nights
4. **Follow-up on two newly surfaced candidates:** SSRN:7162966 and SSRN:6772279

**Net result:** 1 new paper identified (new to 55-night corpus). **0 new verified actionable
tweaks. 22nd consecutive night without a new verified actionable tweak. Tweak queue
unchanged at 42.**

---

## Sources Evaluated Tonight

### SSRN:4677989 — Albers, Cucuringu, Howison & Shestopaloff preprint
**Status: UNVERIFIED — HTTP 403 Forbidden.**
SSRN is blocking all unauthenticated automated fetches. No content retrievable. Content
confirmed from Oxford University Research Archive (CC BY-NC-ND 4.0) — abstract identical to
what N53 had. No new content possible from this path without authenticated SSRN session.

---

### arXiv q-fin.TR September 2026 Listing
**URL:** https://arxiv.org/list/q-fin.TR/2026-09
**Status: VERIFIED — page fetched successfully. Zero papers listed.**
"No updates for this time period." The September 2026 submission window has not yet opened
as of August 25. No new arXiv q-fin.TR papers to screen.

---

### Practitioner Sweep — 4 Search Angles

**Searches run:**
1. "post-only limit order adverse selection crypto perpetual 2026"
2. "maker fill quality OFI order flow imbalance flip timing cryptocurrency 2026"
3. "passive limit order queue position crypto CEX maker 2026"
4. "crypto perp maker execution optimization passive fill 2026 site:arxiv.org"

**Results:**

| Hit | Status |
|-----|--------|
| arXiv:2602.00776 (Bieganowski, crypto microstructure) | Already in corpus — screened N50 |
| arXiv:2607.28323 ("Optimal Execution with Passive Market Impact") | Already in corpus — screened N52 |
| SSRN:6688399 (Tapiero, OFI additive/multiplicative, Apr 2026) | Pre-June; screened in prior sweeps |
| arXiv:2502.18625 (Albers et al., "Market Maker's Dilemma") | Core paper — in corpus since synthesis |
| Educational explainers, regulatory posts, non-primary sources | Discarded |

**Assessment: All hits are already-screened or non-applicable. Practitioner search
saturated (23rd consecutive night).**

---

### SSRN:7162966 — "The 'Neutrinos' of the Order Book" (Albers, Cucuringu, Howison, Shestopaloff, 2026)
**URL:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7162966
**Status: UNVERIFIED — HTTP 403 Forbidden. SSRN blocked all fetch attempts.**

**Verification path:** SSRN abstract ID 7162966 confirmed via M. Cucuringu's faculty homepage
(https://www.math.ucla.edu/~mihai/fin.htm, verified in prior nights for a different paper on
that same page). Paper appears in the publications list.

**What is known (from web search result snippets — NOT from fetched abstract):**
- Dataset: approximately 4.5 billion messages over one month from Hyperliquid's Bitcoin
  perpetual contract, sourced directly from the blockchain.
- Core finding (paraphrase from snippet — UNVERIFIED): approximately 67% of all messages are
  post-only limit orders that are mechanically rejected because they would cross the spread;
  liquidity replenishment after a spread widening is overwhelmingly "anticipatory" — orders
  that close the spread are already in flight before the widening event occurs.

**Why NOT a new verified maker execution tweak:**

1. **Content is UNVERIFIED.** The 67% / anticipatory-replenishment claims come from web
   search result snippets, not the fetched paper. SSRN returned HTTP 403 on all attempts.
   No abstract, no authors section, no quoted text from the actual paper was retrieved.

2. **Platform mismatch.** The dataset is Hyperliquid — an on-chain, fully transparent
   perpetual DEX where the full order book, including message-level rejection events, is
   directly readable from the blockchain. Phemex is an opaque CEX where post-only rejection
   mechanics and queue state are not publicly observable. The finding that 67% of messages
   are mechanically rejected would require CEX-specific confirmation to apply.

3. **The snippet-derived mechanism is directionally noted for future reference:** If
   anticipatory replenishment is real on CEX perps, it implies that a passive order at the
   touch faces queue-jumping from a flood of late-arriving orders that anticipated the same
   imbalance event — worsening queue position over time. This is consistent with the N1–N20
   corpus finding (arXiv:2502.18625) that back-of-queue fills suffer −0.775 bp vs front
   −0.058 bp. But no new threshold, no new measurement, no testable parameter derives from
   a snippet paraphrase alone.

**Assessment: NEW TO CORPUS (Night 55). UNVERIFIED (403). POTENTIALLY RELEVANT — DEX
context. Full paper access needed before any tweak can be derived.**

---

### SSRN:6772279 — "Order Flow Imbalance and the Decay of Price Impact in CME Ether Future" (Tony Li)
**Status: UNVERIFIED — HTTP 403 Forbidden. No content retrieved.**

Candidate from tonight's search sweep. SSRN is inaccessible without authenticated session.
Abstract ID numbering and data coverage (through April 2026) suggest a 2026 paper. CME ETH
futures, not crypto perp CEX — likely NOT APPLICABLE even if accessible, given the CEX
perpetual vs. regulated futures context mismatch documented across prior nights.

**Assessment: UNVERIFIED (403). Likely NOT APPLICABLE (CME, not CEX perp).**

---

## New Forward-Testable Tweak Tonight

**None verified.**

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **SSRN:7162966 ("Neutrinos") is the one genuinely new-to-corpus find tonight.** It was
   published in 2026 by the same Albers/Cucuringu/Howison team responsible for the core
   corpus paper (arXiv:2502.18625). The content is UNVERIFIED from a fetched source — only
   web snippets are available. The finding about anticipatory replenishment and mechanically
   rejected post-only orders is worth reading if SSRN access becomes available.

2. **SSRN remains universally blocked** via automated WebFetch (403 on all IDs: 4677989,
   5323703, 6344338, 6693260, 6772279, 7162966). The only viable remaining path is author
   contact or institutional proxy for any SSRN paper.

3. **September 2026 arXiv listings have not yet appeared.** The q-fin.TR listing is empty.
   No new academic papers are available until September submissions open.

4. **22nd consecutive night without a new verified actionable tweak.** The recommendation to
   suspend nightly search and deploy priority tweaks has now been made for 9 consecutive
   nights (N47–N55) without action.

5. **The empirical gap remains the binding constraint.** No external paper in 55 nights has
   measured OFI-flip decay speed at 60-second granularity in a crypto CEX perpetual. This
   is ST2.0-specific and requires internal fill-log measurement from the bot's own data.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N55): **4 [elevated], 6, 9, 10, 11, 12, 14**
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

## Night 55 Bottom Line

**No new actionable execution tweak tonight.** 6 sources evaluated:

- **SSRN:4677989** (Albers et al. "good, bad, latency" preprint): UNVERIFIED (403).
  Unchanged from N54.
- **arXiv q-fin.TR September 2026**: VERIFIED — empty. No new papers.
- **Practitioner sweep (4 angles)**: All results already in corpus or non-applicable.
- **SSRN:7162966** ("Neutrinos of the Order Book", Albers et al. 2026): **NEW TO CORPUS.**
  UNVERIFIED (403). DEX context (Hyperliquid). Snippet claims: ~67% of messages are
  mechanically-rejected post-only orders; anticipatory replenishment after spread widening.
  No verified tweak derivable from snippets.
- **SSRN:6772279** (Tony Li, OFI CME ETH): UNVERIFIED (403). Likely NOT APPLICABLE (CME).

**New optional action (added tonight):**
(e) Author contact for SSRN:7162966 (Jakob Albers or Alexander Shestopaloff — both have
research emails via their institutional pages). Cucuringu homepage lists the paper; author
emails may be reachable from the same page.

**Final recommendation (unchanged from N47–N54, now 9 nights overdue on execution):**
Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14.
Remaining optional actions:
(a) SSRN:5323703 author contact (Ruan & Streltsov);
(b) SSRN:6344338 author contact (Rajendran/Singaravelu via ResearchGate);
(c) NCCU Finance → Lawrence Chang institutional email → one attempt for SSRN:6693260;
(d) SSRN:4677989 author contact (Albers et al.) or institutional proxy;
**(e) [NEW] Author contact for SSRN:7162966 (Albers et al. "Neutrinos" — 2026 paper, DEX
context but same team as the core corpus paper).**
