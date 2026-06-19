# Partial Take-Profit Scale-Out — 2026-06-19

## Problem (Jonas's report, verified)
"When the bot wins 15%, it loses 15% almost right away." Trade audit of the last
100 closed trades (May 9 – Jun 19) confirmed the *feeling* but located a different
*mechanism*:

- Median **win +4.4%** ROI vs median **loss −12.8%** ROI.
- **65% of losses** land at −10% or worse (full ~1.2%-price stop × 10x).
- Only **13% of wins** reach +10%; take-profit (+16% ROI) fired **once in 100 trades**.
- Genuine same-symbol whipsaw: only **3/100** — NOT the dominant pattern.
- Reconstructed from logs (n=19): winners **peak at +6–10% ROI but trail out at
  ~+2.9%** — giving back ~4 points every time.

So the asymmetry is **winners trimmed small while losers ride the full stop**, and
specifically winners *surrender gains they already had* to the trail.

## Why not the obvious knobs
- **Tighten SL (Jonas's first idea):** attacks loss *size* (the wrong side), and
  tight stops get wicked out (durable-trail lesson, 2026-06-11). Likely lowers WR.
- **Adverse-exit / early loss-cut:** swept −2% to −6% on 5/2; **every threshold lost
  money** (winner-caps > loser-rescues). On the do-not-retry list.

Both proven-negative. The only lever not in a rejected family is **stop strangling
the winners.**

## The change (conservative ship)
When an open **main-bot** position reaches **+`PARTIAL_TP_ROI`% margin-ROI**
(deployed at **10%** — Jonas's call: scale out only on genuine runners, leave
modest +6-9% winners to run untouched; bump to 12 for more selectivity), close
**half** at market and let the **runner half** continue under the *existing*
trail / TP / durable-SL machinery — no nulling of stops, no breakeven surgery, no
order cancel/replace.

Why +10% and not +6%: winners peak +6-10% ROI; in the reconstructed sample ~1 in 5
peaked ≥10% and only ~1 in 10 reached ≥12%. +10% catches the runner cohort that
clearly broke out without firing on the modest-winner crowd (which Jonas wanted left
alone), and without being so rare it's inert.

- Resting exchange SL/TP are `reduceOnly`, so they auto-cap to the remaining half.
- Effect: **lock +6% on half** (gains the trail currently gives back); the runner
  still rides. Helps small/medium winners (the bulk); slightly caps the rare big
  runner. Net-positive on the observed distribution.
- Fully reversible: `PARTIAL_TP_ROI=0` disables.

## Files
- `config.py` — `PARTIAL_TP_ROI` (default 0.0).
- `.env` — `PARTIAL_TP_ROI=6.0`.
- `risk_manager.py` — `Position.scaled_out` (+ persistence); rewrote
  `partial_close_position` to record a `partial_tp` closed_trades entry, shrink
  amount/margin, set `scaled_out`, return `(pnl, pnl_pct)`. Added `peak_price` to
  every `close_position` record (MFE instrumentation — closes the audit data gap).
- `bot.py` — partial-TP scale-out loop before the early-exit block, guarded by
  `_pos_lock` / `_closing` (no double-close with the live exit watcher), no
  `cancel_open_orders`, fires `notify_partial_tp`.
- `tests/test_partial_tp.py` — 6 tests (halving, runner untouched, trade record,
  short side, fire-once flag, paper fee netting). Full suite 162 passed.

## Propagation (CLAUDE.md rule)
- Telegram: `notifier.notify_partial_tp` + `notify_exit` already handle `partial_tp`.
- Daily report (`scripts/daily_report.py`) and `web_dashboard.py` group by
  `exit_reason` dynamically → `partial_tp` row appears automatically.

## Expectation (honest)
Modest, not transformational: roughly +2 ROI points per winning trade plus a small
loss-side benefit. The reason every fix lands "modest" is the bot's real edge is
thin. The win here is it's positive-EV, bounded-downside, reversible, and — via the
new `peak_price` field — finally *measurable*. Decision point: re-audit after
~30–50 trades with the new MFE data.
