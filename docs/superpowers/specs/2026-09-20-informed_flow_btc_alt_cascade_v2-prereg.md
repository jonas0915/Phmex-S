# PRE-REGISTRATION — informed_flow_btc_alt_cascade_v2 paper slot

**Registered**: 2026-09-20T19:50:35Z UTC (2026-09-20 12:50 PM PT), run 2026-09-19-1451, Gate A (owner "go")
passed before this script was invoked. Written BEFORE the single holdout read; this document contains no holdout
numbers and the seat that wrote it holds no holdout token.

**Thesis** (verbatim from the `thesis` object in
`research/swarm/runs/2026-09-19-1451/specs/informed_flow_btc_alt_cascade_v2.frozen.json`):

- **mechanism**: BTC carries the deepest book and the most informed leveraged order flow; a sharp BTC pump (trailing 3h
  return > 150 bps) is driven by short-covering / leveraged futures buying concentrated in BTC's own book first. When a
  given alt has captured less than half of that same-direction move over the same 3h window, the lag is not a catch-up
  waiting to happen -- external lead-lag literature (see source_urls) shows genuine cross-market information propagation
  from a dominant, deeply-liquid venue/asset to thinner books happens on a scale of minutes to tens of minutes, not
  hours; an alt still lagging BTC's move after 3 hours signals the pump lacked broad, genuine demand for that specific
  alt. The desk shorts the unconfirmed laggard, betting informed desks and market makers fade it back down over the
  following hours, squeezing out late alt longs who bought the naive 'BTC pumped, alts will follow' narrative -- those
  late longs are the counterparty forced to sell into the fade (stopped out or exiting on the reversal).
- **counterparty**: Retail/momentum alt-perp longs who chase an alt after seeing BTC pump, on the mistaken assumption
  the alt will mechanically catch up; they are forced to pay (via stop-loss or liquidation) when the unconfirmed pump
  fades and the alt reverts toward its pre-pump level.
- **prediction**: On the long_1h dataset, alts whose trailing 3h return captures <50% of a concurrent BTC trailing-3h
  pump >150 bps will show a negative mean net return (after the 11.5 bps cost c) over the following <=7 hourly bars,
  i.e. shorting the laggard alt at that bar's next open clears cost with a bootstrap CI95 of net bps excluding zero and
  observed WR >= p*(250 bps) = 52.3%.
- **source_urls** (same thesis object):
  - https://zenodo.org/records/17084252
  - https://arxiv.org/abs/2506.08718
  - https://link.springer.com/article/10.1007/s10690-026-09589-z
- **evidence_grade**: `research/swarm/runs/2026-09-19-1451/gate_kept.json` carries NO entry for id
  `informed_flow_btc_alt_cascade_v2` (its five kept entries are the original run ids). The kept entry for
  `informed_flow_btc_alt_cascade` — which v2 re-registers byte-identically apart from the BTC reference-load line
  (`research/swarm/kb/LESSONS.md` line 25, 2026-09-19 row; committee carry-over ruling 2026-09-20 12:52 PM PT in
  `research/swarm/runs/2026-09-19-1451/committee/economics.json` and `statistics.json`) — has `evidence_grade: "A"`
  (`research/swarm/runs/2026-09-19-1451/gate_kept.json`, entry id `informed_flow_btc_alt_cascade`). Recorded as-is;
  no grade is assigned to v2 by this seat.

## Frozen data
All from `research/swarm/runs/2026-09-19-1451/specs/informed_flow_btc_alt_cascade_v2.frozen.json` unless stated.
- dataset: `long_1h`
- universe (16): DOGE, ADA, XRP, LTC, LINK, UNI, NEAR, SUI, ONDO, AAVE, TAO, XLM, 1000PEPE, 1000SHIB, GIGGLE, BNB
- timeframe: `1h`
- tp_bps: 250
- sl_bps: 150
- max_hold_bars: 7
- expected_trades_per_week: 5.72
- doa_line: "Kill if the frozen train-era screen's bootstrap CI95 (bootstrap_ci.mean_ci) of net_bps includes 0, OR
  observed WR < fee_math.p_star(250)=0.523, OR n<30 trades accumulate within the first 12 weeks of any paper-slot
  deployment."
- frozen spec path: `research/swarm/runs/2026-09-19-1451/specs/informed_flow_btc_alt_cascade_v2.frozen.json`,
  `sha256` field = `2d51f95509d209b6ebfb42cee3c5ea67b561ac0490dab46ed1d69cac019f6c41`, `frozen_at` 2026-09-20T19:30:00Z;
  `registrar.verify(...)` printed `True` at this registration.
- signal sha256: `c8cf4ee13bd1d8e096966389e426f3294d007ecd32aa22f25394da881efd6d8d`
  (`research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.json`, `signal_sha256`); the
  frozen signal file is `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/signal.py`.
  Signal constants: K = 3 bars, THRESH_BPS = 150.0, LAG_RATIO = 0.5; BTC loaded via
  `load_data.load_reference("BTC", "1h", dataset="long_1h")`; short-only (`-1`), never long.
- train_span: `["2025-06-27 06:00:00+00:00", "2026-06-12 16:00:00+00:00"]`
  (`research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.json`, `train_span`).
- holdout: the final 25% of the dataset's range per `load_data.holdout_start` — stated as the rule; no holdout rows
  were read and no dates are computed from them here.
- Cross-dataset holdout caveat (STANDARDS #6, dataset is `long_1h`): "holdout window overlaps mr_edge train; treat the
  holdout read as a sanity read only".

## Economics
- Basis $200. Notional per trade = 200.0
  (`python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"` → `200.0`).
- c = 11.5 bps (`fee_math.C_BPS` printed → `11.5`; maker-entry/taker-exit 7.0 bps + 4.5 bps adverse selection per
  `research/swarm/kb/CONSTRAINTS.md`).
- p* = 0.523 (`research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.json`, `p_star`;
  `fee_math.p_star(250)` printed → `0.523`).
- lot_check at $200 notional, all 16 symbols `ok: true`
  (`research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.json`, `lot_check` block):
  DOGE ok (199 lots, lot_usd 1.001), ADA ok (200), XRP ok (199 lots, lot_usd 1.0044), LTC ok (200), LINK ok (200),
  UNI ok (200), NEAR ok (200), SUI ok (200), ONDO ok (200), AAVE ok (200), TAO ok (200), XLM ok (200),
  1000PEPE ok (200), 1000SHIB ok (200), GIGGLE ok (200), BNB ok (200). `lot_usd` is null for every symbol other than
  DOGE and XRP in that block (`fee_math.LOT_MIN_USD` printed → `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143,
  'XRP': 1.0044, 'DOGE': 1.001}`, so no other universe symbol has a registered lot floor).
- Funding: max_hold_bars 7 × 1h bar = 7h ≤ 8h, so the CONSTRAINTS "hold > 8h must account for funding" trigger is not
  met. A position can still straddle one 8h funding settlement depending on entry hour; the paper book does not model
  funding and this is recorded as a known, unmodelled cost (funding is not deducted and not claimed either way).
- Paper convention: 1x paper book, margin recorded AS the notional (Donchian convention, `donchian_slot.py` /
  `_donchian_open_paper`), so USD PnL = notional × price move and ROI% = price move %. Sim fees are deducted at close
  by risk_manager; the ledger's `net_pnl` is therefore fee-inclusive at the source (see the verdict line).

## Slot design (paper only)
- slot_id `informed_flow_btc_alt_cascade_v2`; module `informed_flow_btc_alt_cascade_v2_slot.py`; tests
  `tests/test_informed_flow_btc_alt_cascade_v2_slot.py`; state file
  `trading_state_informed_flow_btc_alt_cascade_v2.json` (auto-discovered by `web_dashboard.read_all_slot_states`);
  sidecars `informed_flow_btc_alt_cascade_v2_slot_state.json` + `informed_flow_btc_alt_cascade_v2_signal_<SYM>.json`
  (never prefixed `trading_state_`).
- Signals computed on CLOSED bars only, transcribed from
  `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/signal.py`: at closed 1h bar i, BTC
  trailing-3-bar return `btc_ret = (close_btc[i]/close_btc[i-3] − 1) × 1e4`, alt trailing-3-bar return `alt_ret`
  likewise on the alt's own closes; fire short (−1) when `btc_ret > 150.0` AND `alt_ret < btc_ret × 0.5`; otherwise 0;
  never +1. A signal on closed bar i → paper entry at the first price after bar i closes (≈ open[i+1]). The forming
  bar is never read (STANDARDS #4).
- Exit rule transcribed from `research/swarm/lib/screen.py` `simulate()`: each later closed bar checks SL then TP
  against that bar's low/high (SL wins ties); for a short, SL = entry × (1 + 150/1e4) tested against high, TP =
  entry × (1 − 250/1e4) tested against low; TIME exit at max_hold_bars = 7 at that bar's close. Exit tags
  `stop_loss` / `take_profit` / `time_exit`.
- Slot parameters: `paper_mode` True, `loss_cap_usdt` −999.0, `kelly_min_trades` 10**9, `durable_trail_enabled`
  False (rails opt-out: the verdict line below is the only kill).
- Kill file `.kill_informed_flow_btc_alt_cascade_v2`, touched automatically by the adjudicator on a KILL (see the
  verdict line) or by hand; honoured by the bot's generic `.kill_*` sentinel loop and by the evaluator's
  `slot.enabled` check every cycle.
- Live path NOT implemented: a promoted slot logs an error once per UTC day and places nothing, identical to
  `_donchian_adjust_position`.

## Verdict line (frozen)
VERDICT LINE (frozen; the adjudicator implements it numerically, the prereg doc states it verbatim):
- Ledger: closed_trades of trading_state_informed_flow_btc_alt_cascade_v2.json with closed_at >= registered_ts (the epoch of 2026-09-20T19:50:35Z); net = sum of each row's net_pnl AS-IS (fee-inclusive at the source — risk_manager deducts sim fees at close; never re-subtract), via the adjudicator's existing _net(t).
- verdict_n = 50.
- KILL: n >= 50 and net <= 0.
- KILL: net <= -10.00 USD at ANY n (dollar loss cap).
- PASS: n >= 50 and the lower bound of the bootstrap CI95 of per-trade net USD (research.swarm.lib.bootstrap_ci.mean_ci, defaults: 2000 reps, alpha 0.05, seed 0) > 0.
- INCONCLUSIVE: n >= 50, net > 0, CI95 lower bound <= 0 → keep accruing, re-grade at every n; hard stop at n = 100: PASS if the CI95 lower bound > 0 there, else KILL.
- WATCH: n < 50 and net > -10.00.
- ENFORCEMENT (spec §7 "kill line enforced automatically"): the adjudicator's grade_<id> TOUCHES .kill_informed_flow_btc_alt_cascade_v2 when a KILL clause is hit — the two KILL lines above AND the INCONCLUSIVE hard stop at n = 100 — paper-only, zero market risk: the bot's existing .kill_* sentinel loop closes the paper book and persists the kill. The slot's own rails stay opted out (loss_cap_usdt −999.0, kelly_min_trades 10**9) because this line is the enforcement. PASS is never a promotion: it makes the thesis PASS-ELIGIBLE for an owner decision; the grader never writes .promote_* and promotes nothing.
ANTI-FISHING CLAUSE (frozen): no change to tp_bps, sl_bps, max_hold_bars, universe, timeframe or the signal during the paper era; no second holdout read; any deviation or data problem found during the run is REPORTED as a finding, never fixed-and-re-run; a parameter change is a new thesis through the desk with its own pre-registration. Rollback at any time = touch .kill_informed_flow_btc_alt_cascade_v2 (paper-only, zero market risk).

registered_ts for the ledger filter above: 2026-09-20T19:50:35Z = epoch 1789933835
(`python3 -c "from datetime import datetime,timezone; print(int(datetime(2026,9,20,19,50,35,tzinfo=timezone.utc).timestamp()))"`).

## Prior (train, read before this registration)
Every number is followed by the file it came from. The v2 screen folder
`research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/` contains only `out.json`,
`signal.py`, `trades.csv` — where a v2 file is absent it is recorded as "not run", with the committee's carried-over
v1 citation given separately and labelled as such.

- n = 246 — `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.json`
- net_bps_mean = 34.07147326187418 — same file
- ci95 = [12.271245400252258, 56.30117389045181] — same file (excludes 0)
- wr = 0.524390243902439 vs p_star = 0.523 (WR ≥ p*) — same file
- trades_per_week = 4.914149821640904 — same file (frozen spec's `expected_trades_per_week` is 5.72 —
  `research/swarm/runs/2026-09-19-1451/specs/informed_flow_btc_alt_cascade_v2.frozen.json`; the two differ and both are
  recorded as-is)
- time_to_verdict_weeks = 10.174699961285327 — same file
- causality = "PASS" — same file
- audit.json verdict / numbers.p_boot: **not run** for v2 —
  `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/audit.json` does not exist. The
  committee carried over the v1 audit: verdict `CONFIRMED`, `numbers.p_boot` = 0.0025 —
  `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade/audit.json` (v1 path, cited by the
  carry-over ruling in `research/swarm/runs/2026-09-19-1451/committee/statistics.json`).
- BH row: `research/swarm/runs/2026-09-19-1451/committee/bh.json` has NO row for id `informed_flow_btc_alt_cascade_v2`.
  Its row for `informed_flow_btc_alt_cascade` (v1): p = 0.0025, rank 1, threshold 0.02, significant true, q = 0.1,
  m = 5, k_star = 1 — `research/swarm/runs/2026-09-19-1451/committee/bh.json`.
- Economics vote (`research/swarm/runs/2026-09-19-1451/committee/economics.json`, id
  `informed_flow_btc_alt_cascade_v2`, pass true), reasons: (0) CARRIED OVER by controller ruling 2026-09-20 12:52 PM PT
  — v2 is a byte-identical re-registration of v1 (only the BTC reference load line changed to
  `load_data.load_reference`), train out.json matches v1 on n/net_bps_mean/ci95/wr/p_star/trades_per_week/per_symbol/
  train_span and trades.csv md5 02dd4a06b42c73ce8ed23d9dcfc43862 is identical, verified programmatically; (1) WR ≥ p*:
  wr 0.524390243902439 ≥ p_star 0.523; (2) lot_check ok for all 16 symbols at position_notional 200.0; (3) feasible on
  a 5-min poller — timeframe 1h, closed bars only, causality PASS; (4) max_hold 7 × 1h = 7h ≤ 8h, no funding
  adjustment required or claimed; (5) time_to_verdict_weeks 10.174699961285327 ≤ 26. (Reasons 1–5 cite the v1 out.json
  path.)
- Statistics vote (`research/swarm/runs/2026-09-19-1451/committee/statistics.json`, id
  `informed_flow_btc_alt_cascade_v2`, pass true), reasons: (0) the same CARRIED OVER ruling; (a) n = 246 ≥ 30;
  (b) CI95 [12.271245400252258, 56.30117389045181] excludes 0; (c) BH at q = 0.10, m = 5, k* = 1, this thesis rank 1
  with p = 0.0025 ≤ 0.02 → bh_significant true (table in `research/swarm/runs/2026-09-19-1451/committee/bh.json`);
  (d) month spread from trades.csv: max single calendar month 2026-02 = 68/246 = 27.6% < 50%; (e) per_symbol max
  TAO/NEAR = 25/246 = 10.2% < 60%; (f) robustness tp_bps ±20%: registered 34.07147326187418, plus (tp 300)
  38.988748766962445, minus (tp 200) 22.245729624354507, all positive → pass. (Reasons a–f cite the v1 paths.)
- Robustness for v2: **not run** — neither
  `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.robust_plus.json` nor
  `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.robust_minus.json` exists. The v1
  files the committee cited read: `out.robust_plus.json` net_bps_mean = 38.988748766962445 and
  `out.robust_minus.json` net_bps_mean = 22.245729624354507 —
  `research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade/` (v1 path).
- Prior process failure recorded for honesty: the v1 build's holdout read was void (n = 0) because the frozen v1
  signal loaded BTC with era="train" hard-coded; v2 exists only to fix that plumbing via `load_reference` —
  `research/swarm/kb/LESSONS.md` line 25 (2026-09-19 row). No v2 holdout number exists yet.

## Holdout (read once)
Read once at 2026-09-20T19:50:35Z by the command: python3 -m research.swarm.lib.screen research/swarm/runs/2026-09-19-1451/specs/informed_flow_btc_alt_cascade_v2.frozen.json research/swarm/runs/2026-09-19-1451 --era holdout --token COMMITTEE-HOLDOUT-READ. Out path: research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json (trades in research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/trades.holdout.csv; the train out.json was not touched). Every number below was read from that out.holdout.json by this seat.
- n = 75 — research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json
- net_bps_mean = 59.198399668922356 — research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json
- ci95 = [20.994210390758322, 98.16793798069588] — research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json
- wr = 0.5733333333333334 (p_star in the same file = 0.523) — research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json
- per_symbol = DOGE 3, ADA 4, XRP 2, LTC 6, LINK 2, UNI 2, NEAR 9, SUI 4, ONDO 5, AAVE 5, TAO 7, XLM 8, 1000PEPE 4, 1000SHIB 4, GIGGLE 4, BNB 6 — research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json
- trades_per_week = 5.226047283284944 — research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/out.holdout.json
- Sanity read only (dataset long_1h, STANDARDS #6 overlap caveat above); these numbers change nothing above.

Decision: BUILD — the fixed rule's "otherwise → BUILD" clause applies because ci95 is not null (n = 75 ≥ 2) and its upper bound 98.16793798069588 is not < 0.

## Owner decision (reference feed)
Appended 2026-09-20T20:30:49Z UTC on resume of run 2026-09-19-1451 (args.resume_after_prereg), args.reference_feed = "exchange_ohlcv". The original IMPLEMENT seat stopped because the frozen signal loads its reference series through research.swarm.lib.load_data and the slot framework hands a slot only its own symbol's OHLCV. Owner decision, verbatim (args.owner_decision), copied character-for-character — the text between the fence lines, nothing added, nothing escaped:
```text
Owner decision 2026-09-20 1:16 PM PT (Jonas, in reply to the controller's recommendation): "yes" — the slot MAY fetch BTC 1h closed bars live via self.exchange.get_ohlcv("BTC", "1h", limit=...) as the reference series — one extra request per cycle, closed bars only, intersected on the alt's closed-bar index exactly as the frozen signal does.
```
Transcription: the frozen signal's `ld.load_reference("BTC", "1h", dataset="long_1h")` is transcribed as a live reference fetch — `self.exchange.get_ohlcv("BTC/USDT:USDT", "1h", limit=OHLCV_LIMIT)` → `complete_bars(...)` (closed bars only) → intersected on the alt's closed-bar index exactly as the frozen file does. The pure module exposes `signals(df, ref_df)` (reference frame as an explicit second argument; parity against the frozen file is tested on synthetic frames and on the research cache's train frames of ≥3 universe symbols). The bot fetches the reference ONCE per cycle, after the paper_mode guard, and passes the same closed frame to every symbol. Nothing above this section changes; the verdict line, anti-fishing clause and holdout record stand as committed.


## Verdict (appended 2026-09-21 5:50 PM PT — after the fact; the lines above were frozen 2026-09-20)
**KILL** — registered clause "net <= -10.00 USD at ANY n". Adjudicator run 2026-09-21 06:00:02 PT: n=5, 0W, net $-16.20 → touched `.kill_informed_flow_btc_alt_cascade_v2`; the bot's sentinel loop killed the slot at 6:01:43 AM PT. Final paper book n=6 (1W) net $-11.44 (a NEAR short opened 4:01 AM closed take_profit +$4.76 at 6:00 AM, inside the same minute as the ruling). Trades (PT): NEAR short 2:00→3:01 AM stop -3.24; BNB short 2:00→5:00 AM stop -3.24; LTC short 3:01→4:00 AM stop -3.24; NEAR short 3:01→4:01 AM stop -3.24; ONDO short 3:01→4:01 AM stop -3.24; NEAR short 4:01→6:00 AM TP +4.76. Source: trading_state_informed_flow_btc_alt_cascade_v2.json closed_trades. Every loss came from one BTC-pump event (signal bars 08:00Z and 09:00Z). Findings, not fixes (anti-fishing): no concurrency cap was pre-registered (LESSONS 2026-09-21); GIGGLE was delisted before the test began (LESSONS 2026-09-21). DEAD_LIST row 112. Paper only; $0 real money.
