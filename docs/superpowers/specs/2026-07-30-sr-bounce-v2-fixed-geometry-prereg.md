# PRE-REGISTRATION — SR_BOUNCE v2 (fixed geometry era)

**Registered**: 2026-07-30 ~8:50 PM PT, owner order (remote): "Set 2.5% on 10x
leverage and then 1.5% sl" → clarified "SR_Bounce. 25% roi" — i.e. TP = 2.5%
price move (25% ROI at 10x), SL = 1.5% price move (−15% ROI at 10x).

**Context**: Era 1 (structural zone exits) closed KILL the same evening at its
pre-registered n=50 line: net −$0.79 fee-inclusive, 23W/27L (46.0% WR), last
trade closed 8:20:50 PM PT, auto-killed on negative Kelly (−0.076) at
8:24:54 PM PT (sidecar killed_at). Era-1 autopsy premise:
zones at 5m/1h scale produced noise-scale stops (median ~0.16–0.19% risk
width) with the 0.12% RT fee eating 30–60% of wins. This era tests the owner's
counter-thesis: same entry signal (zone touch + rejection), but exits wide
enough that fees are a ~5% tax on wins and the stop sits outside noise.

## What changes (and what does not)
- ENTRY: unchanged — sr_bounce.evaluate() frozen as-is (k=3 pivots, 0.25×ATR
  cluster, ≥2 touches gap ≥3, ADX<30 regime gate, confirmed rejection). Its
  internal room-vs-opposing-zone skip still shapes the entry set (structural
  levels are still computed; only their USE as exits stops).
- EXIT: fixed TP +2.5% / SL −1.5% of entry price, applied VERBATIM (atr=0 path,
  no ATR clamp/widening). R:R fixed 1.67:1. Fee-inclusive breakeven WR on a $5
  margin / $50 notional trade: win = $5×25% − $0.06 fee = $1.19; loss = $5×15%
  + $0.06 = $0.81; **BE-WR = 0.81/2.00 = 40.5%** (era 1 delivered 46.0% WR —
  above this bar, which is the owner's thesis in one number).
- The era-1 stale-levels entry skip (price drifted past structural levels
  between signal and entry) does NOT apply in v2 — with fixed exits the
  structural levels are informational only. Recorded here as a known,
  intentional entry-set difference vs era 1.
- THIRD EXIT (recorded for honesty, review catch 7/30): the generic slot
  240-cycle (~4h) hard time exit still applies (risk_manager.should_time_exit;
  1.5× extension only at ROI ≥ +5%). Era 1 never tripped it (all 50 exits
  were take_profit/stop_loss — tight structural targets resolved fast), but a
  2.5% target implies multi-hour holds, so some v2 trades WILL close mid-range
  at ~4h. The BE-WR 40.5% is therefore the bar for the SL/TP-resolved subset,
  not every trade; the verdict line is net-only and unaffected. Time-exit
  frequency and PnL will be visible in exit_reason and reported at verdict.
- Slot economics unchanged: PAPER, $5/trade, max 1 position, entry patience
  45s, loss cap −$5.

## Ledger & era hygiene
- Era-1 ledger archived to `trading_state_SR_BOUNCE_era1.json` (still matches
  the `trading_state*.json` lifetime-PnL glob — history preserved).
- Sidecar `killed_at` cleared at deploy; fresh `trading_state_SR_BOUNCE.json`.
- Era-1 KILL verdict is FINAL and keeps printing in the digest (grader pinned
  to the archived file). v2 is a new experiment, not an appeal.

## Verdict line (frozen now)
- Grader: `sr_bounce_v2`, verdict at **n=50 paper trades**, net_pnl AS-IS
  (fee-inclusive — risk_manager deducts sim fees at close; no re-subtraction).
- n≥50 & net ≤ $0 → **KILL** (fixed-geometry thesis refuted at this scale;
  the S/R program returns to closed — no v3 without a new mechanism).
- n≥50 & net > $0 → **PASS-ELIGIBLE** (owner decision required; promotion is
  never automatic; I3 fill_price revalidation is a mandatory pre-live gate).
- WR alone is not a verdict input; the line is net-only, same as era 1.

## Anti-fishing clause
One geometry (2.5/1.5), one verdict read at n=50, registered before the first
v2 trade. No mid-era geometry changes; a geometry change = new era, new line.

## Prior (recorded for honesty)
The 7/28 scan holdout was gross-negative BEFORE fees at structural exits, and
the 7/29 lever lab found no positive exit lever on 8,706 train trades — the
mechanism's prior is against v2 too. The owner knows this and ordered the
forward test; the forward test measures live signal-on-fresh-data, which the
scan cannot. Prior per-trade to beat: −$0.016/t (era-1 realized).

---

## CHANGELOG — 2026-08-12 owner re-registration (honest-era verdict)

**Owner order 2026-08-12 (~8:45 PM PT):** the n=50 verdict line now counts
ONLY honest-era trades — `opened_at >= 1785991620` (the 2026-08-05 9:47 PM PT
fresh-price fix, PID 27868). Rationale: the 19 pre-fix rows carry stale
cached-price phantom entries (+$4.40 of the book's +$6.07 at re-registration);
grading on them would pass the strategy on fills that could not have happened.
The phantom-cushion caveat was flagged and recorded BEFORE the original line
could grade (memory, 8/9-8/10), so this supersession predates any verdict —
it is not a post-hoc goalpost move. State at re-registration: honest era
n=23, net +$1.66, 14W/9L, ZERO take_profit exits (max favorable excursion
2.47% vs the 2.5% target), 21 hard_time_exit / 2 stop_loss.

Unchanged: KILL if net <= $0 at n=50 (honest count); PASS is never automatic;
a fresh I3 strict-fill revalidation gates any live path; timer-units bugs
(240 cycles ≈ 5.7-9.5h real vs the 4h label, silent ROI>=5% 1.5x extension)
remain deferred to the era boundary and the grade carries that caveat.
Implementation: `honest_since` in EXPERIMENTS["sr_bounce_v2"] +
opened_at filter in grade_sr_bounce_v2 (adjudicate.py), tests
test_grade_sr_bounce_v2_honest_* (686 suite green at deploy).
