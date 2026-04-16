---
name: Sentinel Gate Forensics
description: Post-mortem of the three broken Sentinel tape gates discovered 2026-04-07 session 2. Root causes, evidence, and fixes.
type: project
---

# Sentinel Gate Forensics (2026-04-07)

Three of the four flagship Sentinel tape gates were broken from deploy (2026-04-01 23:01 PT) until 2026-04-07 20:58 PT. The Apr 2 "Sentinel is winning / 0% AE rate" narrative was built entirely on corrupted data.

## Gate 1: `cvd_slope` — 9 orders of magnitude off

**Spec:** threshold ±0.3 (intended as a normalized slope ratio).
**Reality:** raw `cvd_slope` values ranged from ±100 to ±3,000,000 depending on symbol volume. The gate comparison `abs(cvd_slope) > 0.3` was therefore true on virtually every tick — the gate "fired" randomly based on which side of the comparison noise landed on.

**Root cause:** the raw CVD delta was computed in quote-asset units and never normalized before comparison. The spec number was copy-pasted from a prototype notebook that used a ratio form.

**Fix (deployed 2026-04-07):** normalize `cvd_slope` to a -1..+1 ratio (delta / rolling absolute sum). Threshold ±0.3 now has real dimensional meaning.

**Side effect:** a pullback strategy carve-out was added as "Option 1" (cvd_slope gate skipped for pullback-style strategies). **Warning — the carve-out is broken:** it checks for strategy name `"bb_reversion"` but `_extract_strategy_name` returns `"bb_mean_reversion"` (C1 in lessons.md). Paper slot has no carve-out at all (C2).

## Gate 2: `large_trade_bias` — hardcoded constant

**Spec:** ratio of large-trade buy volume vs large-trade sell volume over a rolling window. Gate was `large_trade_bias < -0.3` for shorts, `> 0.3` for longs.

**Reality:** `self.large_trade_bias = 0.5` was set once in `__init__` and **never updated by any code path**. The flagship "smart money bias" gate was a constant `0.5` for the entire Sentinel deploy.

**Root cause:** the update function was written but never called from the WS tape handler. No test / log line ever surfaced that the value was stuck.

**Fix (deployed 2026-04-07):** actually compute `large_trade_bias` from rolling large-trade deques. Large = ≥5× rolling median trade size. Requires ≥8 large trades in window before returning a signal (initially ≥5, raised after noise).

**Secondary fix:** the new large-trade tracking deques were being written outside `self._lock` — race condition. Closed by moving writes inside the lock.

## Gate 3: Tape gates silently bypass when `trade_count ≤ 20`

**Behavior:** when WS tape buffer had ≤20 trades in the window, all tape gates (`buy_ratio`, `cvd_slope`, `large_trade_bias`) were **skipped entirely with no log line**. This made it impossible to tell from logs whether a trade passed the gates or just slipped under the trade_count floor.

**Root cause:** defensive early-return intended to prevent small-sample noise, but no skip telemetry.

**Fix (deployed 2026-04-07):** added skip logging — every tape-gate bypass now emits a reason line to bot.log. The ≤20 floor is kept but now visible.

## Gate 4 (honorable mention): `spread_pct` display bug

Not a compute bug — the gate math was correct. But the dashboard/log display format was wrong, showing spread at 100× actual. Fixed to use the midpoint formula `(ask - bid) / ((ask+bid)/2)`.

## Collateral damage to the Apr 2 eval

Because cvd_slope fired randomly and large_trade_bias was a constant:
- Claims that "Sentinel gates are blocking low-quality setups" were false for 3 of 4 gates
- Claims of "AE rate dropped to 0%" were false — real AE rate was **50.8%**, a separate bug (exit_reason tagging: risk_manager wrote `reason`, analytics read `exit_reason`)
- Claims of "+$8.27 Sentinel outperformance vs V10 Control" were apples-to-oranges (gross vs net)

## Lessons for future gate deploys

1. **Log raw distributions before thresholding.** A threshold without a histogram of the raw values it's compared against is a guess.
2. **Unit-test every gate with real production data samples before deploy.** Would have caught cvd_slope in seconds.
3. **Log every skip / bypass with a reason.** A gate that silently opts out is indistinguishable from a gate that passes.
4. **Verify the update path, not just the read path.** `large_trade_bias` was read 1000s of times and "looked fine" — but nothing was ever writing to it.
5. **When a new metric shows "too good to be true" numbers (0% AE rate), it is.** Stop and reconcile against exchange truth before drawing conclusions.

## See also
- `reference_sentinel.md` — deploy metadata + Apr 7 post-mortem section
- `lessons.md` — META-RULE 8 (verify dashboard/report numbers against exchange truth)
- Apr 7 session-2 session grade entry in `lessons.md`
