# MR-tuned universe (ranginess scanner) scan — 2026-08-01

Pre-registration (contract): `docs/superpowers/specs/2026-08-01-mr-universe-ranginess-scan-prereg.md`
All artifacts: `scripts/research/mr-universe-scan-2026-08-01/`

## VERDICT: DO-NOT-BUILD

Train eligibility failed on 2 of 3 pre-registered conditions, so the universe
thesis is answered negative per the frozen verdict rules. No re-scoring, no
second score definition.

| Train condition (TEST universe) | Required | Actual | Result |
|---|---|---|---|
| (1) net/trade fee-inclusive | > $0 | **−$0.020** | FAIL |
| (2) net/trade ≥ control | ≥ −$0.104 | −$0.020 | pass |
| (3) trades/day ≥ 1.5× control | ≥ 2.418 (1.5 × 1.612) | **1.569** | FAIL |

The core frequency thesis did not show at all: the ranginess list traded
*slightly less* often than the gainer-proxy control (0.97×), not 1.5× more.
Net/trade was better than control on train but still negative. Because
eligibility failed, the holdout was not consumed by the verdict; per the
pre-reg's reporting clause ("frequency and net are reported for both lists
regardless of verdict") the holdout tables are included below — and they
reinforce the negative: on holdout the ordering reverses (test −$0.099/trade
vs control −$0.011/trade). Both lists are net losers over both segments.

## Headline numbers

Fee model (pre-registered): 0.12% RT of notional, $30 margin @ 10x → $300
notional, **$0.36 flat fee per round trip**. All nets below are fee-inclusive.

| Segment | List | n | trades/day | net/trade | net total | WR | avg win | avg loss |
|---|---|---|---|---|---|---|---|---|
| TRAIN (259.3d) | TEST (ranginess) | 407 | 1.569 | −$0.020 | −$8.15 | 69.0% | +$1.222 | −$2.790 |
| TRAIN (259.3d) | CONTROL (24h \|ret\|) | 418 | 1.612 | −$0.104 | −$43.48 | 68.9% | +$1.262 | −$3.131 |
| HOLDOUT (111.1d) | TEST (ranginess) | 203 | 1.827 | −$0.099 | −$20.02 | 67.0% | +$1.271 | −$2.878 |
| HOLDOUT (111.1d) | CONTROL (24h \|ret\|) | 207 | 1.863 | −$0.011 | −$2.28 | 68.6% | +$1.313 | −$2.905 |

Source: `results.json` (verified independently by recomputation from
`trades_test.csv` / `trades_control.csv` — identical to 4 decimals).

Exit mix (all trades, test list): trailing_stop 365, stop_loss 110,
st2_hold (4h time exit) 107, take_profit 28. Control list: 377 / 126 / 90 / 32.
Same shape as prior MR replays — the loss engine is stops (avg loss ≈ 2.3× avg
win), the win engine is trail exits.

## Data span actuals

- **Universe deviation (recorded, not fixed):** pre-reg says "top 30 USDT perps,
  all ≥ $3M 24h turnover." At snapshot (8/1 ~1:15 AM PT) only **19** Phemex
  USDT linear perps cleared $3M, so the universe is those 19
  (`universe.json`, turnovers recorded per pair). The $3M constraint binds
  before the top-30 count does. Survivorship caveat from the pre-reg applies
  (current snapshot, not historical listings).
- History requested: 400 days, 5m + 1h, via ccxt phemex (paginated,
  `backtest.fetch_ohlcv_full`, rate-limited). **18 of 19 pairs delivered the
  full 400d** (5m: 115,199 bars; 1h: 9,599 bars each). GIGGLE listed
  2026-01-13, so it has ~200d — its history starts at listing and it becomes
  list-eligible once it has 30d of 1h data. Per-pair actual spans:
  `data_manifest.json`.
- Replay/rotation span: first rebalance 2025-07-27 (30d of 1h scoring history
  after data start) → 2026-08-01, **370.5 days, 53 weekly rebalances**.
- 70/30 split: TRAIN 2025-07-27 → 2026-04-12 6:56 AM PT (259.3d),
  HOLDOUT 2026-04-12 → 2026-08-01 (111.1d). Split by entry timestamp.
- Minor tail artifact: GIGGLE was fetched ~12h after the other pairs, so the
  final ~12h of the span has data only for GIGGLE. Affects both lists equally;
  ≤0.15% of the span.

## Fee-bug status (pre-reg checked item)

The 7/6 "paper-sim fee over-penalty" bug (`docs/overnight-2026-07-05/r3_paper_fee.md`):
paper slots in `risk_manager.py` used to charge (taker+slippage)×2 = 0.22% RT;
fixed 7/5 to 0.12% RT. **This scan does not touch that code path at all.**
The reused replay engine (`scripts/slot_lab/mean_revert_replay.py:97-109`) has
its own fee constants (maker 0.01% / taker 0.06% per side) and was never
affected by the paper-sim bug; `backtest.py`'s separate 0.22% rig default
(r3 doc, "NOT changed") is also not on this scan's code path. For this scan the
engine's `_net` was **not** used — per the pre-reg, PnL is gross price move on
$300 notional minus a flat $0.36 (0.12% RT), applied identically to every trade
regardless of exit type (`scan.py::replay_pair`). Note this is slightly
conservative for maker-heavy exits and slightly generous for taker exits vs
the engine's split model; it is the registered model, applied uniformly to
both lists, so the A/B comparison is unaffected.

## Engine-vs-live divergences (reported, engine used as-is per instructions)

1. **RSI floor not modeled.** Live blocks 5m_mean_revert LONGS with RSI(7) < 22
   (`.env:95 MEAN_REVERT_LONG_RSI_MIN=22.0`, gate at `bot.py:2990-2997` — it
   lives in bot.py, not in `strategies.bb_mean_reversion_strategy`, which is
   what the replay engine calls). The replay therefore includes deep-oversold
   longs that live would block. Affects both lists identically.
2. **Trail arm ROI 5% vs live 8%.** The engine's simulator uses
   `backtest.py:596 TRAIL_ARM_ROI = 5.0` (module constant); live runs
   `.env:31 TRAIL_ARM_ROI=8.0`. Replay trails arm earlier than live would.
3. **Short RSI threshold matches live** (`MR_SHORT_RSI_MIN` unset in .env →
   default 70, the un-armed V17 state).
4. **Tape/OB gates cannot be replayed** (no historical L2) — pre-recorded
   limitation; this measures signal-on-OHLCV, not fill selection.
5. **Fill-all at signal close** (maker-style). Real maker fill rate ~27%; this
   is an upper bound on trade count, same as every prior scan with this engine.
6. **Exit path on 5m bars, not 1m.** The pre-reg freezes data to "5m for
   replay + 1h for scoring," so the exit simulator walks 5m bars (engine
   originally used 1m). Each bar is expanded adverse-extreme-first, so intrabar
   SL-vs-TP ties resolve pessimistically (engine's own rule); the engine's
   strictly-after-entry bar filter means the first ~5 minutes post-entry are
   unobserved (was ~1 minute on 1m).
7. Global occupancy (max_positions) and cross-book contention not modeled —
   affects totals, not per-trade expectancy; identical for both lists.

## Frozen scoring implementation (literal readings recorded)

Score per pair at each rebalance R, on trailing 30d of 1h bars (`scan.py`):
- R1 = fraction of bars with ADX(14) < 25 — `indicators.adx` (the live bot's
  own ADX), bars with open ts in [R−30d, R).
- R2 = of closes outside BB(20,2) (`indicators.bollinger_bands`, live
  defaults), fraction where price *touches* the 20-SMA within the next 12 bars
  (long side: subsequent bar low ≤ that bar's SMA20; short side: high ≥ SMA20).
  "Returning to the 20-SMA" read as intrabar touch.
- **No-lookahead restriction (judgment call):** R2 events are only counted if
  their 12-bar resolution window closes before R (event bar open ≤ R−13h);
  otherwise scoring at R would peek past the rebalance decision time.
- R2 = 0 (hence score 0) if a pair had zero outside-band events in the window.
- Ties broken by symbol name (deterministic); both lists rebalance on the same
  7-day boundaries; membership window = [R, R+7d).
- Pairs need 30d of 1h history to be scored; the CONTROL list is drawn from the
  same 30d-eligible pool (judgment call — keeps the two lists sampling the
  identical universe at every rebalance). Control rank = |close_now /
  close_24h_ago − 1| on 1h closes as of R, descending.
- Mean TEST∩CONTROL overlap: 3.7 of 8 names per week (range 1-7) — the two
  rankings are genuinely different, the null result is not overlap-driven.
- Signals are regenerated per pair over the full span with the engine's own
  per-symbol 4h cooldown, then filtered by list membership at entry time
  (cooldown is pair-global, so a signal suppressed by a pre-membership signal's
  cooldown stays suppressed — boundary-week effect only, identical treatment
  for both lists).

## Per-pair breakdown

TRAIN — TEST list (n=407, −$8.15):

| Pair | n | net | WR | | Pair | n | net | WR |
|---|---|---|---|---|---|---|---|---|
| ADA | 20 | +$21.93 | 90% | | LTC | 44 | −$8.49 | 64% |
| AAVE | 19 | +$18.66 | 89% | | SUI | 10 | −$13.38 | 50% |
| 1000SHIB | 38 | +$15.79 | 79% | | TAO | 44 | −$14.28 | 66% |
| XRP | 22 | +$10.13 | 82% | | XLM | 27 | −$16.14 | 59% |
| LINK | 23 | +$9.34 | 74% | | UNI | 15 | −$12.38 | 60% |
| NEAR | 26 | +$4.28 | 77% | | ETH | 6 | −$7.02 | 33% |
| ONDO | 27 | +$1.92 | 70% | | SOL | 11 | −$6.83 | 64% |
| GIGGLE | 8 | +$1.40 | 88% | | BNB | 18 | −$4.60 | 50% |
| | | | | | DOGE | 6 | −$3.98 | 50% |
| | | | | | BTC | 17 | −$2.76 | 47% |
| | | | | | 1000PEPE | 26 | −$1.72 | 73% |

TRAIN — CONTROL list (n=418, −$43.48): winners NEAR +$21.43, ADA +$19.04,
ONDO +$12.51, XRP +$12.33, 1000SHIB +$11.22; losers SUI −$27.03, TAO −$26.74,
LTC −$22.94, UNI −$13.72, XLM −$13.54, DOGE −$12.66, SOL −$10.06, LINK −$9.26.

HOLDOUT — TEST (n=203, −$20.02): GIGGLE +$22.84, TAO +$12.61, 1000PEPE +$10.41
vs ONDO −$19.42, AAVE −$13.85, UNI −$11.74, SUI −$11.07, DOGE −$7.03.
HOLDOUT — CONTROL (n=207, −$2.28): TAO +$17.39, SOL +$9.03, 1000PEPE +$7.42 vs
UNI −$14.01, ADA −$13.50, DOGE −$9.59, XLM −$5.37.

Full tables: `results.json` (`train`/`holdout` → `*_per_pair`); raw trades with
timestamps, sides, exit reasons: `trades_test.csv`, `trades_control.csv`,
`trades_all.csv`; weekly lists with full scores: `lists.json`.

## Judgment calls & incidents (complete list)

1. Universe = 19 pairs, not 30 ($3M floor binds — see Data span).
2. GIGGLE re-fetched at its actual listing depth (~200d) rather than dropped;
   cached under the same key, actual span recorded in `data_manifest.json`.
3. Exit path on 5m bars (pre-reg data spec) — see divergence #6.
4. Flat $0.36 RT fee for every trade regardless of exit type (pre-reg model
   applied literally; replaces the engine's maker/taker-split `_net`).
5. R2 no-lookahead event cutoff at R−13h; R2=0 when no events (see scoring).
6. Control list restricted to the same 30d-eligible pool as the test list.
7. Cooldown pair-global, membership filtered post-hoc (see scoring).
8. Trades/day denominators = full segment lengths (259.33d / 111.14d), not
   "days with data" — GIGGLE's late start slightly deflates both lists' rates
   equally.
9. Incident: first scan run crashed at the final `json.dump` (numpy int64 in
   a span timestamp) *after* writing `lists.json` and all trade CSVs. Fix:
   int cast + a fast path that reloads `trades_all.csv` instead of re-replaying.
   The re-run's metrics matched the crashed run's logged metrics exactly
   (n=407/418/203/207, same net/trade and trades/day — `scan.log` vs
   `results.json`), confirming determinism; no numbers changed.
10. Holdout metrics were computed in the same deterministic run for the
    pre-reg's "report both lists regardless of verdict" clause, but the verdict
    logic consumed train eligibility first and, having failed, never used them
    (`scan.py` verdict block; `results.json:verdict_basis`).

## What this answers

The ranginess-ranked universe does **not** raise MR trade frequency (0.97× the
gainer-proxy control on train, 0.98× on holdout — the live scanner's ranking
basis is not what's throttling MR frequency), and neither universe makes the
frozen 5m_mean_revert signal net-positive at $30/10x under the registered fee
model over 370 days. Train's apparent quality edge for the test list
(−$0.02 vs −$0.10) did not survive the holdout (−$0.10 vs −$0.01) — consistent
with noise, not universe selection. Per the anti-fishing clause this closes the
one registered read: DO-NOT-BUILD; no re-scoring or alternative score without a
new mechanism.

## Artifacts

- `scripts/research/mr-universe-scan-2026-08-01/universe.json` — universe snapshot + turnovers
- `scripts/research/mr-universe-scan-2026-08-01/data_manifest.json` — per-pair actual spans
- `scripts/research/mr-universe-scan-2026-08-01/cache/*.parquet` — 5m + 1h OHLCV (38 files)
- `scripts/research/mr-universe-scan-2026-08-01/lists.json` — 53 weekly top-8 lists, both rankings, full scores
- `scripts/research/mr-universe-scan-2026-08-01/trades_all.csv` / `trades_test.csv` / `trades_control.csv`
- `scripts/research/mr-universe-scan-2026-08-01/results.json` — all metrics + eligibility + verdict
- `scripts/research/mr-universe-scan-2026-08-01/scan.py`, `fetch_data.py`, `probe.py`, `scan.log`, `fetch.log`
