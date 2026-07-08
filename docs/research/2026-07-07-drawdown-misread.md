# Drawdown misread root cause (2026-07-07 "32.1% — SEVERE" incident)

**Symptom:** 7/7 7:20:40 AM PT — `[DRAWDOWN] 32.1% — SEVERE. Halting entries for 1.5 hours.`
True drawdown at that moment: 8.0% (peak $62.27, exchange equity ~$57.30). The 1.5h pause
(7:20–8:51 AM) covered the 8 AM bounce — a real trading-hours cost.

**Root cause (verified against code + logs):** `bot.py` computed
`real_balance = free_balance + main-bot margin_in_use`. `self.risk.positions` only tracks
MAIN-BOT positions — live **slot** trades (5m_mean_revert's real orders) hold real margin
that free balance excludes but `margin_in_use` never adds back. With the $15 XRP slot short
open (entered 5:21 AM), the first fresh balance read after the dark-wake outage returned
free ≈ $42.30; (62.27 − 42.30)/62.27 = **32.07%** — arithmetically correct math on the
wrong balance concept. The network outage only *delayed* the bad read past the 8/20/25%
tiers straight to SEVERE; the bug would have fired ~28-32% at 5:22 AM regardless.

**All 9 [DRAWDOWN] pauses June 23 – July 7 were the same bug family** — each "drawdown"
equals an open position's margin ÷ peak to the decimal (e.g. 6/23 15.4% = 10/64.80;
6/24 17.8% = 10.07/56.59; 7/2 15.0% = 9.99/66.61; the 8.1-8.6% cluster = ~$5 half-margin
after partial-TP). A second flavor ratchets `peak_balance` UP ~$10 falsely when a closed-
on-exchange position is still in `risk.positions` (7/2's peak 66.61 = 56.62 + 9.99).
None were network-corrupted reads. Zero legitimate drawdown pauses in the period.

**Fix (deployed 2026-07-08, PID follows restart):** `_equity_for_drawdown()` in bot.py —
drawdown/peak/daily-halt tracking now uses `exchange.get_equity()` (the exchange's own
`total` from the same fetch_balance call — free + ALL used margin regardless of which
subsystem placed the order; immune to internal-tracking desync by construction), falling
back to the old sum only when the equity cache is unset (0.0 before first successful
fetch). Trade sizing still uses free balance — correct for that purpose. 4 new tests in
tests/test_equity_for_drawdown.py incl. the incident-numbers regression.

**Known residuals (accepted, not fixed now):**
- `get_balance` silently returns stale cache on fetch failure (exchange.py:58-72) — with
  equity-based math a stale read yields a stale-but-sane drawdown, no false spike; a
  staleness flag remains a possible hardening follow-up.
- `peak_balance` in trading_state.json was re-baselined downward by the 9 misfires (each
  pause-expiry resets peak to current). The stored peak is a misfire artifact; it rebuilds
  from true equity on the next cycles. No state surgery performed.
