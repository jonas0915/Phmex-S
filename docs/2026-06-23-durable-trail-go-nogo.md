# Durable-Trail GO/NO-GO — 2026-06-23

**Run:** manually, ~5:50 AM PT on 2026-06-23 (ahead of the 8:43 AM PT launchd schedule,
at owner request). Read-only analysis. Gate window per the Part B plan was June 23–29.

---

## VERDICT: **GO — KEEP the durable trail at the 1.2% band.**

Three findings, all data-backed:
1. **The 1.2% band is justified.** A tight 0.3–0.5% trail would have been wicked out of
   **53% of armed episodes (10/19)**; the wide 1.2% band only **11% (2/19)**. 8 episodes
   are cases where the wide band survived but a tight trail would have stopped early.
2. **The mechanism works.** The exchange-SL amend (`edit_order`) succeeded **65 times**
   vs **6 failures (all one Jun 11 BTC deploy-day burst, self-resolved)**.
3. **A tight-band durable trail is DEAD** (the original Part B question): it would clip
   over half the winners. Don't TIGHTEN. No evidence to WIDEN either (the 2 wide-band
   wicks both still exited net-positive).

**Net effect of the armed trail:** all **19 armed episodes exited net-positive**; the
software trailing-stop bucket alone is **+$4.08 over 15 trades** since Jun 11.

---

## Data sources
- `logs/shadow_trail.jsonl` — 19 armed-trail episodes (peak ROI ≥ +5%), Jun 13–19 PT.
- `trading_state.json` — closed_trades since 2026-06-11, exit-reason economics.
- `logs/bot.log*` — `[SL-MOVE]` amend success/failure ledger.

## 1. Armed-trail sample — SUFFICIENT
**19 distinct armed episodes** (grouped by symbol+entry), 97 ticks, 19 exits, spanning
2026-06-13 4:46 AM PT → 2026-06-19 5:17 PM PT. The plan estimated ~15–20 needed for a
read; 19 clears it. (No new armed episodes Jun 20–22 — quiet/chop, near-zero main-bot
trades.)

## 2. Wick test — the core question
For each armed episode, tracked the running peak and tested whether a candle low ever
pierced a tight 0.4% trail vs the wide 1.2% band:

| Trail | Episodes wicked | % |
|-------|-----------------|---|
| Tight 0.4% (software band) | 10 / 19 | 53% |
| **Wide 1.2% (durable band)** | **2 / 19** | **11%** |

- **8 episodes** would have been wicked by the tight trail but survived under the wide
  band — i.e. the wide band directly prevented premature stop-outs.
- The 2 episodes that pierced even the wide band (both XLM) still exited net-positive
  (+$1.59 `exchange_close`, +$0.22 `trailing_stop`).
- **All 19 armed episodes exited profitable.** A tight resting trail would have
  truncated the 8 wicked winners at the wick instead of letting them ride to exit.

**Conclusion:** the wide 1.2% band is the correct geometry. A tight exchange-resting
trail is not viable on this bot's noise profile.

## 3. Amend mechanism health
| `[SL-MOVE]` outcome | count |
|---------------------|-------|
| `amended` (success) | **65** |
| amend attempt failed | 6 (all 2026-06-11, BTC) |
| successes since Jun 15 | 64 / 64 |

The `edit_order` endpoint is validated and reliable. The lone failure cluster was the
first-ever attempt on deploy day (BTC, 8:05 PM PT Jun 11); every amend since has
succeeded (Jun 15: 22, Jun 16: 20, Jun 17: 12, Jun 19: 10). Failure-path logging was
upgraded 2026-06-23 to capture the ccxt error class + repr if it ever recurs.

**`durable_sl` exits: 0** across all state files — NOT a fault. The ratcheted resting
SL is the backstop; faster layers (software `trailing_stop` / `take_profit` / 1s live
watcher) fire first, so the durable SL has never needed to be the trigger.

## 4. Exit-reason economics since 2026-06-11 (main bot, 38 trades, net +$0.07)
| exit_reason | trades | net |
|-------------|--------|-----|
| trailing_stop | 15 | **+$4.08** |
| take_profit | 1 | +$1.44 |
| early_exit | 1 | +$0.77 |
| exchange_close | 17 | −$4.25 |
| hard_time_exit | 2 | −$1.13 |
| stop_loss | 1 | −$0.84 |
| min_margin_skip | 1 | $0.00 |

The trail/TP/early buckets (the profit engine) are **+$6.29**; the losses sit in
`exchange_close`/`time`/`stop_loss` (entry-side / SL outcomes, not a trail problem).
The book is roughly breakeven overall — separate from the trail's job, which is to
protect armed winners, and at that it is working.

## 5. Recommendations
- **KEEP** `DURABLE_TRAIL_BAND_PCT = 1.2%`. Justified by the 53%-vs-11% wick test.
- **Do NOT tighten** — a tight band clips >half the winners.
- **Do NOT widen** — only 2/19 pierced the wide band, both still profitable.
- **Tight-band durable trail = closed/dead** (original Part B hypothesis answered NO).
- Re-check opportunistically if the bot's volatility regime shifts materially.

*All figures verified against the raw files cited above (no-fabrication rule).
This run fulfills the scheduled `com.phmex.gonogo-durable-trail` job; that one-shot
launchd job is being removed so it does not re-fire.*
