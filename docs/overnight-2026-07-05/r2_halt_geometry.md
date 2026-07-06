# R2 — Daily-Loss Halt x $15 Sizing: Geometry, June+ Cost, Options

**Date:** 2026-07-06 (overnight run) · **Scope:** read-only analysis, no config changes.
**Question:** the 3% daily-loss halt is now binding at $15 sizing (one full stop ≈ trips it). What does that cost, and what are the clean levers?

**Data sources (all primary):** `bot.py` (halt implementation), `trading_state.json` (115 June+ main-bot closed trades, 6/2–7/5), `logs/halt_watcher.log` (halt trip/clear ledger since 5/18), `logs/gotAway.jsonl` (gate-blocked signals), `logs/bot.log*` (6/20+ only). Analysis script: scratchpad `halt_geometry.py` (session-temp).

---

## 1. Ground truth: how the halt works

- **Trigger** — `_should_halt_daily_loss` (bot.py:94-97): halts when `today_net <= -(balance * 3%)`. `threshold_pct=3.0` is a default argument; the call site (bot.py:1195) does not override it.
- **today_net** — `_compute_today_net_pnl` (bot.py:74-91): sum of `net_pnl` of **main-bot** trades closed today on the **America/Los_Angeles day boundary**. Live-slot trades are NOT counted toward today_net.
- **balance** — free + margin in use (real equity), re-read every 60 s cycle (bot.py:1165-1167).
- **On trip** — writes `.pause_trading` with reason `DAILY LOSS HALT: ...` (bot.py:1208-1215). Entries blocked (main bot at bot.py:1190, live slots at bot.py:2126); exits still processed.
- **Reset** — the sentinel does NOT self-expire in bot.py. The external `halt_watcher` (scripts/halt_watcher.py, running since 5/18) clears a daily-loss sentinel at the next PT midnight (verified: cleared 7/5's halt at 12:00 AM PT 7/6, halt_watcher.log). So one trip = no entries for the rest of that PT day.
- **Override** — `.daily_loss_override` containing today's PT date neutralizes only a daily-loss pause for that one day (bot.py:104-122, 641-656).

**Sanity note (item 5):** `.daily_loss_override` currently EXISTS on disk but contains `2026-06-30` → **expired/inactive** (date-scoped; today's PT date doesn't match). `.pause_trading` is absent. Halt protection is fully armed.

## 2. Halt history, June+ (actual ~$10 sizing)

Ground truth from halt_watcher.log (it logs every active halt every 5 min, so no trip lasting >5 min can be missed while the watcher runs; its log is continuous through June):

| Day | Trip (PT) | Halt line | Cleared by | Rest-of-day blocked |
|---|---|---|---|---|
| 6/14 | ~9:20 AM (sentinel; loss threshold crossed 8:04 AM) | −$1.55 vs 3% of $46.58 | watcher at PT midnight | ~15 h |
| 6/30 | 12:19 AM | −$1.75 vs 3% of $56.51 | **operator override 8:34 AM** | 8.3 h |
| 7/5 | 6:07 AM | −$2.16 vs 3% of $57.40 | watcher at PT midnight | 17.9 h |

**3 halt days in 25 June+ trading days (12%).** My per-day replay of `trading_state.json` at actual sizing reproduces exactly these 3 days and no others (balances interpolated between the exact anchors logged in the halt lines themselves; no borderline days within ±$0.15 of threshold).

Reconciliation receipts: the 6/14 halt figure −$1.55 = gross cum after the 3rd close (−0.7498 −0.3195 −0.4798 = −1.549; DOGE's $0.06 fee was appended to the record after the halt computed). The 7/5 −$2.16 vs file cum −2.27 is the same fee-timing effect (~$0.11). Immaterial to any trip decision.

### What happened AFTER each trip (post-halt counterfactual at $10)

- **6/14** — not reconstructible: while paused the cycle returns before signal evaluation (bot.py:1190), so no signals are logged; gotAway.jsonl has 0 entries post-trip. **Anomaly (flagged, unresolved):** one BTC entry at 2:03 PM PT executed *while the sentinel was active* (net −$0.84, stop_loss). The watcher's age counter shows the sentinel was continuously present from ~12:20 PM local (Mac was on ET that day — the 6/15 3:00 AM local clear = PT midnight proves it), and the git revision current on 6/14 (0370fe8) already had the `_trading_paused` enforcement. Mechanism for the leak not determined from available logs. It is the only such case found.
- **6/30** — partially OBSERVED thanks to the override: after trading resumed 8:34 AM, exactly 1 trade was taken (BTC, opened 9:27 AM, net **−$0.15**) plus 1 signal blocked by a normal gate (quiet_regime, 9:47 PM). Had the halt stayed on, it would have saved $0.15 that day.
- **7/5** — not reconstructible: 0 post-trip signals logged, 0 gotAway entries, live slots also blocked (bot.py:2126).

**Honest bottom line for #1:** the true cost of the 3 actual halts is mostly unobservable. The only two observable post-trip trades (the 6/14 leak and the 6/30 post-override trade) were both losers (−$0.84, −$0.15) — a tiny, biased sample (n=2, not evidence).

## 3. June+ replay at $15 sizing

**Critical caveat first:** the $15 raise has so far NOT changed realized sizing — post-7/4 margins are min $6.26 / median $9.99 / max $10.05 (n=12). Kelly/ATR sizing (risk_manager.py:407-417) produces ~$10 and the cap only binds above that. The 7/5 halt was tripped by ~2 stacked ~$10 losers, not one $15 stop. So this replay models the *hypothetical where sizing actually reaches the cap*. Two scenarios:

- **A (as prescribed):** scale every trade's net_pnl by 15/margin. Overstates for Kelly-shrunk trades (34 of 115 trades had margin <$9; one 7/3 trade had margin $0.0002 → phantom scaling; scaled-out partials also double-inflate).
- **B (sizing-faithful):** only cap-bound trades (margin ≥ 9.5) scale ×1.5; others unchanged — matches how `calculate_margin` responds to a cap raise (cap applied at risk_manager.py:414).

Both scenarios trip on the **same 8 of 25 days (32%)** — vs 3 actual — blocking an average **19.5 h/day** (156 h total) of trading:

| Day | Trip at (PT) | Trades cut | Cut PnL — A | Cut PnL — B | Note |
|---|---|---|---|---|---|
| 6/12 | trade #2, 8:57 AM | 2 | +0.34 | +0.34 | |
| 6/14 | trade #2, 12:21 AM | 2 | −3.07 | −1.32 | CENSORED (real halt hid rest of day; incl. the leaked −$0.84 loser) |
| 6/22 | trade #1, 8:48 AM | 1 | +0.35 | +0.35 | |
| 6/29 | trade #1, 6:30 AM | 1 | +0.00 | +0.00 | |
| 6/30 | trade #1, 12:19 AM | 1 | −0.39 | −0.15 | CENSORED (cut trade exists only because of the override) |
| 7/1 | trade #1, 3:12 AM | 5 | +1.96 | +1.40 | |
| 7/4 | trade #1, 1:58 AM | 7 | +0.46 | +1.40 | |
| 7/5 | trade #3, 6:07 AM | 0 | 0.00 | 0.00 | CENSORED (nothing traded post-trip) |
| **Total** | | **19** | **−0.35** | **+2.01** | positive = halt removes net wins |

- **Scenario A:** halt removes −$0.35 net (≈ wash, slight save). Bootstrap 95% CI on the total (resample the 8 trip-days, 10k draws): **[−$8.42, +$6.13]**. n=8 < 20 — **not significant**.
- **Scenario B:** halt removes **+$2.01 net of winners** (a cost). 95% CI **[−$2.53, +$6.46]**. n=8 < 20 — **not significant**.
- Cut-trade split (19 trades): 11 winners / 8 losers (A: +9.54 vs −9.90; B: +7.69 vs −5.68). The halt cuts winners slightly MORE often than losers in this sample.
- **Censoring cuts both ways and is the biggest honesty caveat:** on the 5 trip-days with full uncensored history, the cut PnL was ≥ 0 all 5 times (+$3.11 A / +$3.49 B) — post-trip trades were net winners. The only negative contributions come from censored days where post-trip history barely exists. But on 6/14 and 7/5 we cannot see what a $15 bot would have traded after its (earlier) trip — the measured totals are estimates on a truncated sample, not the full counterfactual.
- Multi-day compounding (balance path changing under $15 PnL) ignored; threshold sensitivity is small (±$3 balance error moves the threshold ±$0.09).

**Context:** June+ at actual sizing netted **+$6.94 over 25 days (+$0.28/day mean, 13/25 positive days)**. A rule that removes ~30% of trading days from a net-positive period has positive expected cost even though this sample's direct measurement straddles zero.

## 4. Geometry: balance → stops the halt absorbs at $15

Empirical full-stop cost (June+ SL/exchange_close losers with loss >9% of margin, n=21): mean **−13.66% of margin** → **−$2.05 per full $15 stop** (−$1.37 at $10). Slightly worse than the −$1.98 back-of-envelope.

| Balance | 3% budget | Full $15 stops survived | Halts on |
|---|---|---|---|
| $50.00 | $1.50 | 0 | 1st stop |
| **$58.80 (now)** | **$1.76** | **0** | **1st stop** |
| $66.00 | $1.98 | 0 | 1st stop (breakeven is $68, not $66, at the empirical $2.05 stop) |
| $80.00 | $2.40 | 1 | 2nd stop |
| $100.00 | $3.00 | 1 | 2nd stop |
| $137.00 | $4.10 | 2 | 3rd stop |
| $205.00 | $6.15 | 3 | 4th stop |

**Breakeven balances at $15 sizing: 1 stop = $68, 2 stops = $137, 3 stops = $205.** At the June+ earn rate (+$0.28/day) the ~$11 gap from $57.40 to $68 is ~40 trading days — and every halt day removes ~19.5 h of earning time, so the binding halt slows the very growth that would unbind it. At today's *actual* ~$10 sizing the halt absorbs 1 full stop ($1.37 < $1.76) and trips on the 2nd — the "day ends on one stop" regime only fully materializes if/when sizing truly reaches $15 (see the open $15-ineffective investigation).

## 5. Clean options (Jonas decides — none recommended here)

| Option | One-line effect | Exact number it changes | Where |
|---|---|---|---|
| Raise halt % (e.g. 3→5%) | Budget $1.72 → $2.87/day at $57.40; absorbs 1 full $15 stop instead of 0 | `threshold_pct: float = 3.0` | bot.py:94 (call site bot.py:1195 uses the default) |
| Floor the halt in $ (e.g. max(3%, $4.10)) | Guarantees 2 full $15 stops/day regardless of balance; % takes over above $137 | condition `today_net <= -(balance*3/100)` → `-max(balance*0.03, FLOOR)` | bot.py:97 |
| Scale size to the halt (size = k×balance semantics) | Keeps stops-per-day constant as balance grows; 1 stop/day ⇒ cap ≈ 22% of balance ($12.60 today), 2 stops ⇒ 11% ($6.30) | `TRADE_AMOUNT_USDT` | .env; cap applied risk_manager.py:414 |
| Accept as-is | At actual ~$10 realized sizing: 1 stop absorbed, halts on 2 stacked losers (the 7/5 pattern); if sizing reaches $15, every first stop ends the day until $68 | nothing | — |
| (existing ad-hoc lever) per-day override | Re-arms trading for one PT day after a trip; used 6/30 | `.daily_loss_override` = today's PT date | bot.py:104-122, 641-656 |

## Verification notes

- Halt-day ledger cross-verified two ways: halt_watcher.log lines vs independent replay of trading_state.json — exact match (3/3 days, no extras).
- Halt-line dollar figures reconciled to trade records to the cent (fee-timing explains the small deltas).
- All CIs: day-level bootstrap, independent resampling, 10k draws; every bucket here is n<20 and labeled as such.
- Open anomaly worth a follow-up: the 6/14 mid-halt BTC entry (leak through an active `.pause_trading`).
