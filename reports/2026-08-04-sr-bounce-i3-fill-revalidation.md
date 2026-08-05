# SR_BOUNCE v2 — I3 fill-price revalidation (pre-live gate)

**Run**: 2026-08-04, read-only. Live bot (PID 57484) untouched; all market data
from PUBLIC unauthenticated endpoints (ccxt.phemex public klines — same prior
art as `scripts/fetch_flow_window.py` / `fetch_history.fetch_ohlcv`; no keys
loaded, zero authenticated calls). No state file was written or modified.

## 1. What the spec actually defines (and doesn't)

- The v2 prereg (`docs/superpowers/specs/2026-07-30-sr-bounce-v2-fixed-geometry-prereg.md:54`)
  makes "I3 fill_price revalidation" a **mandatory pre-live gate** on any
  PASS-ELIGIBLE outcome, but defines no method or numeric pass line.
- A repo + memory-wide search found **no written I3 methodology anywhere**
  (`grep -rw I3` over docs/, reports/, memory/, scripts/: only the prereg line
  and two memory references). The lever-lab memory
  (`reference_sr_bounce_lever_lab_2026-07-29.md:35-39`) records what I3 exists
  to catch: era-1 live-path entry drift — 14/22 day-1 fills landed >0.10% past
  the zone, inverting planned R:R; paper fills at the polled signal price hide
  this.
- The closest spec-defined fill proxy is the 7/28 design's fill-realism rule
  (`2026-07-28-sr-bounce-design.md:53`): *"a limit fills only if a LATER
  candle trades through the limit price."* Touch ≠ fill, per the 2026-07-03
  fill-rate research (fill-rate/adverse-selection is structural).
- Slot mechanics (verified in code): live entries are **PostOnly limit,
  45s entry patience** (`bot.py:749` `entry_patience_s=45.0`;
  `strategy_slot.py:63-68`). Paper mode fills instantly at the polled signal
  price (`bot.py:3442` `entry_px = price if slot.paper_mode else fill_price`,
  where `price = prices.get(symbol)` is the per-cycle cached price dict —
  it can be minutes stale by entry time; receipts in §4).

**Method used (conservative default, stated explicitly because the spec is
silent):** a live PostOnly limit at the paper entry price P counts as FILLED
only if price trades strictly THROUGH the limit (long: 1m low < P; short:
1m high > P) within the 45s patience window, on Phemex 1m candles.

- **Method A (primary, spec-adapted "later candle")**: only 1m candles that
  *start after* `opened_at` and start within [t, t+45s] count. With 45s
  patience that is at most the single next 1m candle, and only when the signal
  fired at second ≥ 15 of its minute.
- **Method B (loose sensitivity)**: any 1m candle *overlapping* [t, t+45s]
  counts — includes the signal candle, whose high/low is contaminated by
  pre-signal prints, so B **overstates** fills.

Known proxy limits (honesty): A counts the whole next candle although the
window covers only part of it (over-credits), cannot see post-signal
trade-through inside the signal candle (under-credits), and structurally
cannot register a fill when the signal fired at second < 15 of its minute —
this artifact affects exactly the two 1000SHIB take_profit winners (fired at
sec 12.9 and 4.8). Their case is called out separately below. Filled trades
keep their recorded fee-inclusive `net_pnl` unchanged (a limit fills at the
limit price = the paper entry price; exits identical). Exit-side fill realism
(the TP is also a maker fill) was NOT re-simulated — the surviving-book
numbers below are therefore still an upper bound on live-attainable PnL.

## 2. Per-trade results

Data: 14 closed trades + 1 open position from `trading_state_SR_BOUNCE.json`
(entries cross-checked against `logs/bot.log*` "SR_BOUNCE ENTRY" lines —
every open matched a log line to the second). Candle receipts: c0 = 1m candle
containing the open; c1 = next 1m candle. Phemex candles re-fetched twice
(identical) and spot-checked against OKX perp candles on LTC, BTC, TAO, SHIB
(independent venue — all consistent; §4).

| # | Opened (PT) | Symbol | Side | Paper entry | Net PnL | Exit | Fill A | Fill B | Evidence (Phemex 1m) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 7/30 10:01 PM | SOL | long | 73.79 | −0.2158 | time | **NO** | NO | c0 L73.88, c1 L73.90 — never ≤ 73.79 (stale entry px; mkt 73.88+) |
| 2 | 7/31 4:20 AM | XLM | long | 0.16975 | +0.5438 | time | **NO** | yes | c1 L0.16980 > P; only c0 L0.16971 < P (contaminated) |
| 3 | 7/31 1:35 PM | 1000SHIB | short | 0.00472 | −0.9710 | SL | **YES** | yes | c1 H0.004722 > P (and c0 H0.004721 > P) |
| 4 | 7/31 5:55 PM | 1000SHIB | long | 0.004907 | +1.2341 | **TP** | **NO*** | marginal | sec 12.9 → no later candle in window; c0 L0.004904 < P by 3 ticks only |
| 5 | 7/31 9:09 PM | 1000PEPE | short | 0.002787 | +0.5697 | time | **YES** | yes | c1 H0.0027884 > P (c0 H0.0027891 > P) |
| 6 | 8/1 5:45 AM | XLM | long | 0.17137 | −0.5618 | time | **NO** | NO | c0 L0.17139, c1 L0.17139 — never ≤ P |
| 7 | 8/1 11:32 AM | BTC | long | 62263.3 | +0.8193 | time | **NO** | NO | c0 L62266.2, c1 L62288.1 — P never traded after open (stale px from 18:31 UTC dip, L62250) |
| 8 | 8/1 8:50 PM | TAO | short | 194.12 | +1.2588 | **TP** | **YES** | yes | c1 H194.21 > P (c0 H194.26 > P) |
| 9 | 8/3 12:10 AM | 1000SHIB | long | 0.004832 | +1.2955 | **TP** | **NO*** | marginal | sec 4.8 → no later candle in window; c0 L0.00483 < P by 2 ticks only |
| 10 | 8/3 9:52 AM | SOL | long | 73.37 | −0.0123 | time | **YES** | yes | c1 L73.33 < P |
| 11 | 8/3 4:26 PM | SOL | long | 73.44 | +0.1306 | time | **NO** | yes | c1 L73.44 = touch only; c0 L73.43 < P (contaminated) |
| 12 | 8/3 11:01 PM | LTC | short | 44.47 | +0.0299 | time | **NO** | NO | c0 H44.47 and c1 H44.47 = touch, never through |
| 13 | 8/4 5:39 AM | ONDO | long | 0.3731 | −0.8105 | SL | **NO** | yes | c1 L0.3731 = touch; c0 L0.3730 < P (contaminated, sig at sec 54) |
| 14 | 8/4 7:05 AM | LTC | long | 44.15 | +0.9140 | time | **NO** | NO | c0 (14:05 UTC) L44.21, c1 L44.22 — P is 0.15% below the entire window; 44.15 last traded ~14:03 UTC (stale px) |
| open | 8/4 4:23 PM | SOL | short | 74.10 | (open) | — | **NO** | NO | c0 flat 74.10 = touch; c1 H74.06 — price fell away immediately |

\* structural artifact of Method A (signal fired < 15s into the minute — no
later 1m candle starts inside the 45s window, so A can never say yes). The
honest reading for #4 and #9: **unknowable at 1m resolution, and the evidence
for a fill is weak** — penetration past the limit is 2–3 ticks on a candle
whose low may predate the signal. OKX cross-check on #4 gives the same
marginal picture (SHIB low ×1000 = 0.004903 vs limit 0.004907).

## 3. Portfolio arithmetic

Paper book (14 closed): **+$4.2243** (sums exactly from state-file `net_pnl`).
The 3 take_profit winners (#4, #8, #9) = **+$3.7884** — 90% of the book.

| | Fills | Fill rate | Surviving net | vs paper |
|---|---|---|---|---|
| **Method A (conservative)** | 4/14 closed (open miss → 4/15) | **28.6%** | **+$0.85** (−0.9710 +0.5697 +1.2588 −0.0123) | **−80% of paper net** |
| Method B (loose ceiling) | 9/14 (open miss → 9/15) | 64.3% | +$3.24 | −23% |

**Adverse-selection signature — PRESENT (highlighted per gate purpose):**
- Under Method A, missed trades average **+$0.338/trade** vs filled trades
  +$0.211/trade — the misses are the richer cohort.
- Of the 3 take_profit winners (+$3.79, the book's earnings engine), only
  **TAO (+$1.26) clearly survives**; the two 1000SHIB TPs (+$2.53 combined)
  are Method-A misses and only 2–3-tick marginal fills under the loose method.
- The two biggest hard_time_exit winners — BTC +$0.82 (#7) and LTC +$0.91
  (#14) — are unambiguous NO-FILLS under BOTH methods, and both carry **stale
  paper entry prices**: the paper book "bought" at prices that had stopped
  trading 1–3 minutes before the open (receipts §4). Those two are phantom
  gains a live order could not have captured.
- Meanwhile the single worst trade (SHIB short SL, −$0.97) fills under both
  methods, and 3 of the 4 conservative fills are shorts filled by price
  rising through the sell limit — fills happen when the market comes through
  you. This is exactly the structural pattern the 2026-07-03 fill-rate
  research predicts.

## 4. Receipts

- **State**: `/Users/jonaspenaso/Desktop/Phmex-S/trading_state_SR_BOUNCE.json`
  — 14 `closed_trades` (sum net +4.2243), 1 open position (SOL short 74.10,
  opened 8/4 4:23:53 PM PT).
- **Entry log lines**: `logs/bot.log` + `.1` — every trade's open matches a
  `SR_BOUNCE ENTRY` line to the second (log local tz shifts EDT→PDT mid-week;
  matched via epoch, per the Mac-timezone-travels rule).
- **Stale-price receipts** (Phemex 1m, re-fetched twice identical; OKX
  independent):
  - LTC #14 (open 8/4 14:05:44 UTC, paper entry 44.15): Phemex 14:03 C44.19,
    14:04 O44.18 H44.22, 14:05 O44.21 H44.26 **L44.21**, 14:06 L44.22. OKX
    LTC-USDT-SWAP: 14:03 L44.15, 14:05 O44.21 H44.25 L44.21. 44.15 last
    printed ≈14:03; a PostOnly buy at 44.15 rests ~0.15% below market, no fill.
  - BTC #7 (open 8/1 18:32:22 UTC, entry 62263.3): Phemex 18:31 L62250 (P
    traded here), 18:32 **L62266.2**, 18:33 L62288.1. OKX identical lows
    (62227/62266.2/62277.4). Price never returned to the limit in the window.
  - Root cause receipt: `bot.py` slot loop takes `price = prices.get(symbol)`
    from the per-cycle price dict; with a 60s cycle plus loop latency the
    paper entry price can be minutes old — the very "drift between signal
    close and polled fill" defect the lever-lab memory says I3 exists to
    catch, here manifesting as *favorable* phantom entries.
- **Scripts** (scratchpad, not committed):
  `i3_fill_revalidation.py` / `i3_results.json` under the session scratchpad
  dir; method exactly as §1.

## 5. Verdict

**I3 gate: FAIL — do not promote SR_BOUNCE v2 to live on the current paper
evidence.** (Spec's own frame: the prereg makes I3 mandatory before any live
promotion and sets no numeric line; conservative default applied and stated.)

- Under the conservative fill model the paper +$4.22 collapses to **+$0.85**
  (fill rate 28.6%), and that residue rests on a 4-trade sample dominated by
  one TAO win — not evidence of a live-attainable edge.
- The adverse-selection signature is present: the book's earnings concentrate
  in entries a live PostOnly order would have missed (2 of 3 TP winners
  marginal-at-best, both large time-exit winners phantom-priced), while the
  worst loser fills cleanly.
- Independent of fill modeling, two entries (#7 BTC, #14 LTC, +$1.73 combined
  = 41% of the book) used stale prices that were not obtainable at open time
  under any execution model.
- Note the verdict line itself is untouched: v2 is at n=14 of the registered
  n=50, so no PASS/KILL read is due yet and nothing here changes the frozen
  `sr_bounce_v2` grader. This gate says only: **the paper ledger overstates
  live-attainable PnL, and any future n≥50 net>0 result must clear a fresh
  I3 run before going live** — with the stale-price entry path fixed or at
  minimum re-measured first.

Open follow-ups suggested (no action taken, live bot untouched):
1. The stale `prices` dict at the slot paper-entry site affects every paper
   slot's entry price honesty, not just SR_BOUNCE — worth a one-line
   timestamp audit in a future session.
2. If v2 reaches n=50 net>0, rerun I3 on the full ledger (the method here is
   reproducible from the scratchpad script) and consider tick-level l2 data
   (`l2_tick_recorder.py`) for the marginal-fill cases the 1m proxy cannot
   resolve.
