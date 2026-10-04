# REPORT — swarm run 2026-10-04-0645 (6:45 AM PT, Sunday 2026-10-04)

**Verdict: this run produced 0 theses, screened 0 and passed 0 through committee. All 8 analyst lenses returned no thesis, so the gate, register, screen, audit and committee stages had nothing to process.**

Sources for the verdict:
- The orchestrator run context: `gate_kept: []`, `gate_rejected: []`, `screened: []`, `committee_passed: []`.
- The run directory. `research/swarm/runs/2026-10-04-0645/` holds only `exploratory/`, `theses/`, `mandate.md` and `launch_args.json`. There is no `gate_rejections.json`, no `specs/`, no `screens/` and no `committee/`.

## Theses in this run

None.
- **Gate rejections:** none. `research/swarm/runs/2026-10-04-0645/gate_rejections.json` does not exist, so this was not run.
- **Screens:** none. There is no `out.json`, `audit.json`, `committee/*.json` or `out.robust_*.json` under `research/swarm/runs/2026-10-04-0645/`, so this was not run.
- **Statistics not computed:** n, net bps, CI95, WR vs p*, evidence grade, audit verdict, committee votes, the BH table and the tp±20% read.

The file `research/swarm/runs/2026-10-04-0645/theses/owner_record_probe.json` is a probe output, not a thesis. It is byte-identical to `exploratory/owner-record/owner_record_probe.json` (checked with `cmp`).

## What was not done

### Lenses that returned no thesis

None of the 8 lenses produced a thesis. The web budget was **not** exhausted for any of them (`web_budget_exhausted: false` for all 8 in the run context), so none had its sourcing cut short.

**forced_flows** (notes: `research/swarm/runs/2026-10-04-0645/exploratory/forced_flows/NOTES.md`)
- The best candidate was quarter-hour opening order imbalance (Kim & Hansen, arXiv 2607.09426).
- The paper's public component is under 1 bp at 4h, and 9.8 and 16.9 bp at 8h and 12h (`exploratory/forced_flows/kim_hansen_2607.09426.txt` line 970, confirmed this turn).
  - That is below c, the 11.5 bps total round-trip cost (CONSTRAINTS).
  - The signal needs 10-second signed flow, which neither dataset has.
- The other candidates were already probed null or relabel dead rows 6, 19, 77, 108, 109, 110, 113 and 114, or are funding ideas (rows 4, 7, 82, 83) that the owner has banned.
- No data probes were run.

**informed_flow** (notes: `.../exploratory/informed_flow/NOTES.md`)
- This is the lens's third straight zero-thesis run (2026-09-25-2036, 2026-09-27-0300 and this one).
- Cross-venue and spot-to-perp lead-lag need non-Phemex data.
- BTC-to-alt propagation is dead (rows 106, 107, 112).
- Garfinkel, Hsiao and Hu (2025) report a -0.491% daily high-minus-low effect (t = -7.21) that disappears where margin or shorting exists. Every Phemex perp can be shorted.
- Bianchi-Dickerson is gross-only and covers 2017-2018, which falls under row 76.
- No data probes were run.

**dealer_inventory** (notes: `.../exploratory/dealer_inventory/NOTES.md`)
- The probe faded the US cash session over 48h. Pooled, it looked strong: n=373, 157.70 bps gross, naive CI [88.96, 228.37] (`exploratory/dealer_inventory/probe_session_reversal.out.txt` line 24).
- With one observation per day it is a coin flip. At k=1.5: 110 days, day hit rate 0.509, ci95_day [-45.1, 212.0]. BTC alone: n=41, mean -54.3 (`exploratory/dealer_inventory/probe_session_reversal_by_day.out.txt`).
- It is a relabel of rows 76, 7 and 67.
- Basis, gamma and weekend-inventory routes are dead or not computable.
- The probes used long_1h train only.

**session_calendar** (notes: `.../exploratory/session_calendar/NOTES.md`)
- The best candidate was month-end rebalancing, which has a genuine mandate-bound counterparty. It fails viability item 3 by construction.
- `time_to_verdict_weeks` (in `exploratory/session_calendar/probe_frequency_ceiling.out.txt`) is above 26 weeks at every stop size:

| sl_bps | max_concurrent | time_to_verdict_weeks |
|---|---|---|
| 100 | 4 | 54.17 |
| 150 | 3 | 72.22 |
| 200 | 2 | 108.33 |

- long_1h train has only 9 month-end events per symbol (`exploratory/session_calendar/probe_month_end_rebalance.out.txt`).
- Macro-day, turn-of-month and DCA timing were dropped as row 84, row 7/67 and row 7 relabels, or for having no effect.

**vol_structure** (notes: `.../exploratory/vol_structure/NOTES.md`)
- Every forced short-gamma mechanism needs options data (GEX, vanna/charm) that the bot does not have, so it fails viable #5.
- Every realized-vol-only variant relabels rows 3, 78, 104, 105, 111, 113 or 76, or ideas rejected in earlier runs.
- None of the 3 opened sources gives a number for the key claim.
- No data probes were run.
- Minor discrepancy: the NOTES header says "9 queries" but lists 10 searches. The run context says 10.

**cross_asset** (notes: `.../exploratory/cross_asset/NOTES.md`)
- Neither dataset has SPX, NDX, DXY or rates series.
- Every crypto-only proxy relabels rows 5, 7, 18, 76, 106, 107, 112 or 113.
- No data was loaded.

**literature** (notes: `.../exploratory/literature/NOTES.md`)
- The sweep papers name no forced counterparty.
- The lead-lag check, run read-only through a copy on mr_edge 5m train, gave a pooled signed next-bar alt open-to-close of 0.79 bps (se 0.17, n 66496, hit rate 0.459) (`exploratory/literature/local_check_output.txt` line 39). That is fee-trapped and in the dead row 106 family.
- The `__pycache__` cleanup the seat flagged is not needed. This turn's directory listing of `exploratory/literature/` shows only `NOTES.md`, `local_check_copy.py` and `local_check_output.txt`.

**owner-record** (notes: `.../exploratory/owner-record/NOTES.md`)
- All of the owner's profit came from one contract on one morning. u100TRYBUSD made +$8,128.01 on n=33 trades, from 8:47 PM to 12:44 AM PT on 2022-11-09/10 (`exploratory/owner-record/owner_record_probe.json`: tryb_detail).
- Everything else (n=786) made -$3,270.79, with per-trade CI95 [-5.96, -2.49] from `bootstrap_ci.mean_ci` (same file: ex_tryb).
- The episode was already rejected as not screenable. `owner_record_delist_peg_dislocation_fade` failed time-to-verdict at 70.73 weeks against the 26-week limit (`research/swarm/runs/2026-09-25-2036/gate_rejections.json`).
- The only screenable generalization relabels rows 6, 76, 104, 110 and 114.

### Mandate requirement not met

The mandate requires at least two lenses to target holds over 8h (`research/swarm/runs/2026-10-04-0645/mandate.md` §4). Because no lens produced a thesis, no >8h thesis exists this run. forced_flows explicitly reports that its 8h+ quota was left unfilled.

### Registrar, screen and audit errors

None, because none of these stages ran. No `registrar.freeze`, `universe_check --frozen`, `screen.run_screen` or audit was invoked this run.

### Sources that could not be fetched (none of them is cited)

**HTTP 403**
- https://www.sciencedirect.com/science/article/pii/S1544612322001179 (forced_flows)
- https://www.mdpi.com/1911-8074/19/9/692 (informed_flow and cross_asset)
- https://www.preprints.org/manuscript/202604.0256/v1 (dealer_inventory)
- the macrohive.com turn-of-month page (session_calendar; its exact URL is not recorded in NOTES)
- https://eprints.soton.ac.uk/412873 (literature)

**Empty or paywalled**
- https://qmro.qmul.ac.uk/xmlui/handle/123456789/83862?show=full (empty; informed_flow)
- https://www.cxoadvisory.com/currency-trading/eth-btc-lead-lag-relationship (paywall; informed_flow)

**PDF could not be parsed by the fetcher**
- https://ftp.aeaweb.org/conference/2026/program/paper/ByyFEfr4 (dealer_inventory)
- https://arxiv.org/pdf/2607.09426 (dealer_inventory; forced_flows did extract it locally with pypdf)
- https://arxiv.org/pdf/2606.00071 (cross_asset)

**Other**
- https://www.bitmex.com/blog/site-announcement/bitmex-has-removed-ftx-from-the-bitmex-indices: 404 after a 301 redirect (owner-record)
- `docs/2026-09-16-edge-swarm-v1/sweep/academic/ssrn_6932998.html`: a 372-character Elsevier "Content Blocked" page with no paper content (literature)

## Next run should

- **Stop or rotate lenses that keep coming back dry for the same data-gap reason.** informed_flow has now returned zero theses three runs in a row. Across this run's lenses, the same gaps recur: no signed tape, no options gamma/OI history, no cross-venue prices, no event calendars. Before the next launch, either decide whether one of those datasets can be added to `load_data` at research stage, or replace these lenses with ones the existing OHLCV/funding data can actually serve.
- **Compute the frequency ceiling in the mandate, before analysts start.** For each event cadence (monthly, quarterly, a few per year), put `fee_math.time_to_verdict_weeks` under `max_concurrent` into `mandate.md`, so lenses drop low-frequency event ideas without spending web budget. session_calendar computed this itself this run (`exploratory/session_calendar/probe_frequency_ceiling.out.txt`), and the 2026-09-20-0300 and 2026-09-25-2036 gates rejected ideas for the same reason.
- **Share one run-level fetch log across lenses.** arXiv 2607.09426 was fetched or evaluated by four lenses (forced_flows, dealer_inventory, cross_asset, literature), and mdpi JRFM 19/9/692 returned 403 to two. A shared ledger of URL, status and extracted figure, readable by every lens, would stop the same source being re-fetched and re-rejected and would free budget for new sources.
