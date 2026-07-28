# SR_BOUNCE — Support/Resistance Bounce Strategy (Design)

**Date**: 2026-07-28
**Status**: Approved design, pre-implementation
**Owner decision trail**: bounce style (+ regime-awareness staged later), swing-pivot
levels, confirmed-rejection entry, structural exits — all owner-selected 2026-07-28.
Build path approved: backtest kill-gate first (C), then paper slot (A) only if the
scan survives. Level-engine module (B) deliberately NOT built until earned.

## 1. What it trades

Horizontal support/resistance bounces in ranging markets. Buy confirmed rejections
at validated support zones; short confirmed rejections at validated resistance.
This is the first strategy in the fleet to trade *horizontal* levels — existing
books trade dynamic S/R only (BB bands, EMA zones, Donchian channels).

## 2. Signal definition (frozen before the scan)

Per scanned pair, levels on 1h candles (existing 500-candle fetch), entries on 5m:

1. **Pivots**: 1h swing low = lowest low of k=3 candles either side (mirror for
   swing highs). Full 500-candle lookback (~3 weeks of structure).
2. **Zones**: pivots within 0.25 × ATR(1h) merge into one zone (a price BAND).
   Zone edges = min/max of member pivots.
3. **Validation**: zone tradeable after ≥2 distinct touches (founding pivot + ≥1
   later test that reversed). A "touch" = a 1h candle whose range enters the zone
   and closes back outside it, ≥3 candles after the previous touch.
4. **Trigger** (5m): price enters a validated support zone AND a 5m candle pierces
   the zone and closes back above it (confirmed rejection). Mirror at resistance.
5. **Regime gate**: 1h ADX < 30 (bounces are a ranging-market trade — same
   threshold family as 5m_mean_revert). Standard slot OB/tape gates apply
   (SR_BOUNCE gets NO carve-outs until data argues for them).

**Execution**: resting PostOnly maker at the rejection candle's close, 45s
patience (5m_mean_revert's proven execution profile). No re-quote in v1.

**Exits (structural)**:
- Stop: far edge of the zone + 0.25 × ATR(5m) buffer. Zone broke = thesis dead.
- Target: nearest opposing validated zone, capped at 3 × stop distance.
- Skip rule: if the nearest opposing zone is < 1 × stop distance away, no trade
  (no room to get paid).

## 3. Stage C — backtest kill-gate (build this first)

Standalone read-only script under `scripts/research/sr-bounce-scan/`. No bot
imports beyond pure helpers; never touches live state.

- **Data**: `backtest_data_may/` archive + fresh ccxt fetch of current scanner
  pairs; target ≥90 days/pair of 1h+5m. Chronological split: train = first 60d
  (sanity/diagnostics only), holdout = last 30d (the verdict).
- **No tuning**: all parameters in §2 are frozen now. The scan runs once on
  holdout. If someone wants to tune, that's a new spec.
- **Fill realism**: a limit fills only if a LATER 5m candle trades through the
  limit price. 0.12%-of-notional round-trip fee model (paper-slot parity).
- **PRE-REGISTERED DOA LINE** (agreed 2026-07-28, before any code): do NOT build
  the slot if holdout shows fee-inclusive net-per-trade ≤ $0, OR holdout yields
  < 20 trades across all pairs (too rare to reach a verdict at slot pace).
  Precedent: the 2026-07-06 VWAP+SMA scan (DOA −0.26%/trade, correctly predicted
  the built-anyway slot's death at n=50).
- **Bonus diagnostic** (report-only, not a verdict input): S/R-zone proximity at
  entry for the 754 historical real trades; Mann-Whitney W/L separation test.
  Context: the 2026-06-13 gate-quantify study found NO separating entry feature,
  but zone proximity was not among those tested.
- **Output**: `reports/<run-date>-sr-bounce-scan.md` (dated the day the scan
  runs) with per-pair and pooled results, receipts, and a BUILD / DO-NOT-BUILD
  call against the DOA line.

## 4. Stage A — paper slot (only if the scan survives)

- `sr_bounce()` in strategies.py, registered as a proper `STRATEGIES` key
  (full generic-slot gate parity, like vwap_sma_cross — NOT a bespoke evaluator).
- `StrategySlot("SR_BOUNCE", paper_mode=True, trade_amount_usdt=5.0,
  max_positions=1)`. Structural SL/TP passed per-trade.
- Level state is recomputed per cycle from the existing candle fetch (no
  persisted level sidecar in v1 — that's the deferred Approach B).
- **Pre-registered adjudicator lines**, added to the EXPERIMENTS registry the
  same day the slot ships: KILL at n=50 if fee-adjusted net ≤ $0 or WR < the
  geometry breakeven (computed in the registry comment from realized avg
  stop/target distances — never invented). No early PASS; promotion is a
  separate owner decision with its own audit.
- Reporting: dashboard signal card + blotter chip (free from framework);
  `[sr_bounce]` line in the adjudicator digest.

## 5. Testing

TDD per house rules:
- Pivot detection, zone clustering, touch counting on synthetic 1h candles
  (including: pivot at window edge, overlapping clusters, touch-spacing rule).
- Rejection trigger on synthetic 5m candles (pierce-and-close-back vs
  close-through vs never-entered).
- Geometry: stop/target/skip-rule including the cap and the no-room skip.
- Scan script: fill-realism unit test (limit only fills on later candle cross).
- Slot wiring: STRATEGIES key present, slot board renders, state file created,
  kill sentinel works (test stubs copy attr names from class defs — 7/27 lesson).

## 6. Explicitly out of scope (YAGNI)

- Breakout mode (staged as a possible second slot only after bounce verdict).
- Level-engine module with persisted zone state / dashboard zone overlay (B).
- Multi-timeframe level confluence, volume-profile nodes, round numbers.
- Any carve-outs from slot OB/tape gates.
- Any live promotion path — paper only in this spec.

## 7. Sequencing

1. Scan build + run (~1 day) → report with receipts.
2. DOA → stop; write a dated `memory/reference_sr_bounce_scan_*.md`; done.
3. Alive → slot build (~1 day, TDD) → pre-restart audit → paper accrual →
   adjudicator owns the verdict.
