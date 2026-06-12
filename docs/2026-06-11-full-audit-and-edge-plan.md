# Full Bot Audit + Edge-Improvement Plan — 2026-06-11

Three parallel audit agents (trade inventory, gate/pattern analysis, paper-slot A/B) +
prior-R&D synthesis + arithmetic verification. Every number below was computed from
trading_state.json / code / state files this session. Bot healthy at audit time:
PID 10869, 0 open positions, balance $56.16 (reports/2026-06-11.md), peak $58.26.

## 1. Ground truth (verified)

| Metric | Value | Source |
|---|---|---|
| All-time trades | 603 | trading_state.json closed_trades |
| Gross PnL | −$43.79 | sum pnl_usdt |
| Known fees | $16.74 (287 records) | sum fees_usdt |
| **True net** | **≈ −$60.52 or worse** | gross − known fees; 316 old records have unrecorded fees |
| Win rate | 40.8% gross (vs ~48.9% breakeven) | |
| Expectancy | −$0.073/trade gross | |
| Kelly (last 50, bot's own formula) | **f\* = −0.18** → negative edge; bot still sizes $10 by design (risk_manager.py:447) | |
| Last 30 days | 61 trades, net −$8.26 | all htf_l2_anticipation |
| Last 7 days | 8 trades, net +$0.63 | tiny n; bot near-idle since 6/9 |

Discrepancy resolved: memory's "−$60.51" = gross − fees (−$60.52 reproduces it);
the "592 trades" figure was the whole book at sprint close, mislabeled as
htf_l2-only (htf_l2 itself = 107 records, real set 91 after artifacts).

## 2. Where the bleed lives (htf_l2, 91 real trades, 60d, net −$12.68)

Overlapping cohorts ranked by impact:
1. **Aligned large_trade_bias ≥ 0.36 tercile: −$9.97** (35.5% WR vs 63.3% in the low
   tercile). INVERTED SIGNAL: strategies.py:601-606 currently *boosts* strength when
   whales are already aligned — it's rewarding the worst cohort. Biggest separator found.
2. **30–60 min holds: −$7.16** (36.8% WR; 56% of net loss in 21% of trades) — drift
   into exchange_close/adverse. The just-deployed durable trail addresses part of this.
3. **QUIET-regime flow-confirmation exemption: −$5.45** (18 entries, 44.4% WR) — the
   carve-out at bot.py:1294-1298 admits exactly what the gate was built to block.
4. **conf=4 floor cohort: −$4.73** (n=11, 27.3% WR) — directionally consistent with
   raising the ensemble floor to 5, but n is small.
5. **5m ADX ≥ 25 at entry: 38.7% WR** vs 53-63% below — un-gated, measurable.
6. Hours: only 4/24 PT-hours gross-positive all-time. 2–4 PM PT and 7 AM PT sit
   OUTSIDE the current block. [CORRECTED by gate-sim cross-check 6/11 PM: the
   original n/$ here were htf_l2-only mislabeled as whole-book. Actual whole-book:
   UTC 21-23 n=53/−$14.90; UTC 14 n=20/−$7.68. Direction unchanged, magnitudes larger.]

What's already working: cluster throttle, per-pair cooldowns, time blocks (zero leaks
in 91 entries), early_exit (+$11.03, 100% WR) and trailing_stop (+$2.42) exits.

## 3. Bugs / config lies found

- **Daily symbol cap doesn't exist.** CLAUDE.md + .env claim DAILY_SYMBOL_CAP=3;
  Config.DAILY_SYMBOL_CAP is referenced nowhere — bot.py:966-972 logs only.
- **5m_scalp slot is dead config** — paper_mode=False slots are skipped by the
  evaluator AND the live loop never writes to slot.risk; 0 trades forever.
- **Frozen DOGE paper position** in 5m_narrow since 4/24 — killed slots never run
  exits (bot.py:1480), so the position is stuck permanently.
- HTF throttle timestamp only arms on FULL fills — min_margin_skip partials bypass it
  (cosmetic; ETH 3 entries in 11 min on 5/23 at ~$0 cost).
- durable_sl: 0 records (expected — deployed today, no armed trail yet).

## 4. Paper slots verdict

- 5m_narrow killed (Kelly −0.212, 20% WR/50t), 5m_liq_cascade killed (−0.079, 34%/50t)
  — both Kelly values independently recomputed, exact match.
- 5m_mean_revert (+$3.95/19t, 52.6% WR): **statistical coin flip** — P(≥10W|p=0.5)=0.50;
  edge is all short-side (+$7.98) with longs negative; 11/19 entries would have been
  blocked by live gates; profits rest on touch-price TP fills with 0.05%/side slippage
  assumption. Not promotable evidence. ~1.7 trades/week — near-dormant.

## 5. Prior R&D constraints (what NOT to redo)

Dead (with killing numbers, see memory + docs): all 9+ culled strategies; AE threshold
tuning at every value; trail-to-breakeven +3% (−$0.20); confidence as a filter (April
read); imbalance-reversion at TAKER fees (0/324 configs net-positive, OOS −0.08%/t);
hour-set hardening from shadow data; radical selectivity (inconclusive, reverted).
Alive: imbalance signal itself is REAL (p≈1e-94, monotonic, OOS-persistent) but worth
only ~+0.04%/trade gross — under the 0.12% RT taker cost, above realistic maker cost.
Infrastructure: flow-replay backtester ENTRY-calibrated (53=53), EXIT model broken
(−207% PnL error); flow_capture.jsonl ~150k rows and growing; sweep automation live.

## 6. The edge plan

The honest frame: 5 rounds of param tweaks and 9 strategy culls found no entry edge at
taker fees. The two highest-probability paths to positive expectancy are (A) cutting
the 0.12% RT fee to maker rates — which moves breakeven WR from ~48.9% to ~44-45%,
below the recent live WR — and (B) deleting the measurable negative cohorts above.
New-signal research is third priority, behind both.

**Phase 0 — hygiene (no sim needed, zero trading risk), this week**
- Fix frozen DOGE paper position + make killed slots close their open paper positions.
- Delete or implement the daily symbol cap (stop the doc lie). Remove 5m_scalp dead config.
- Remove the QUIET flow-confirmation exemption (it's a leak, −$5.45/60d) — or demote
  to shadow-tag to keep measuring.

**Phase 1 — fix the backtester exit model (prerequisite for everything)**
- Implement 60s-cadence early_exit + intra-bar adverse_exit in flow_replay per
  docs/2026-05-30-flow-replay-calibration.md:79-81. Acceptance: live-window PnL error
  within ±15% (was −207%). Investigate ZEC 10x overfire while in there.

**Phase 2 — maker-fee hypothesis (the documented #1 lead)**
- Fix the maker-exit 4s-timeout bug (exchange.py:553-616; fill rate currently 0%).
- On the fixed sim: test maker-entry + maker-exit variants OOS. Fee burden is ~$93/yr
  taker vs ~$33 best-case — on a $56 account this is the whole game.
- Ship only if simulated net-positive (lessons.md:407 hard rule).

**Phase 3 — entry-cohort gates (sim-gated, uses the CALIBRATED entry model)**
Replay both sides (saved AND clipped, lessons.md:354) for each, ship only net-positive:
- a. Block aligned large_trade_bias ≥ ~0.35 AND remove the inverted whale boost.
- b. Block 5m ADX ≥ 25 at entry for htf_l2.
- c. Raise ensemble floor 4→5.
- d. Extend time block to UTC 21-23 (2-4 PM PT) and evaluate UTC 14 (7 AM PT).
Note: these cut n hard (maybe 50-70% of entries). At ~2 trades/day that means a
near-idle bot — acceptable only because expectancy is currently negative.

**Phase 4 — re-tests that unlock if Phases 1-3 land**
- Imbalance-reversion under real maker fills (preconditions in the 6/1 doc).
- Durable-trail GO/NO-GO June 23 (already scheduled, self-cleaning launchd job).
- 5m_mean_revert short-side only as a gated paper slot — re-evaluate at n≥50.

**Decision gate:** if after Phases 1-3 no simulated-positive config exists, the data
supports the 6/1 standing recommendation (halt live trading / paper-only) — Jonas's
call, the $50 floor remains the hard backstop either way.
