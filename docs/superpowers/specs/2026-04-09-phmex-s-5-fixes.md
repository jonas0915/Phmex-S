# Phmex-S Recovery — 6 Verified Fixes

**Date:** 2026-04-09
**Author:** Session 2026-04-08
**Status:** Awaiting approval
**Scope:** Move bot from bleeding to break-even/positive in 2 weeks. No agents. No new subsystems. Surgical fixes on verified problems. **Every fix has a live-confirmation validation gate — no silent failures.**

---

## Context (verified tonight)

- Balance: $84.20 (peak $90.50, DD 6.9%)
- 27 Sentinel-era trades, net −$8.86 after fees
- **Fees = 62% of total losses** (Phemex CSV truth)
- **21 of 27 Sentinel adverse exits come from `htf_confluence_pullback`** — one strategy owns the bleed
- 4 data-layer bugs fixed tonight (stop_loss mistag, entry/exit prices, entry_snapshot persistence, cosmetic conf display)
- Truth reconcile pipeline live (every 15 min, atomic apply)

---

## The #1 discovery: Maker fill rate is 0%

Agent audit of `logs/bot.log` + `exchange.py:280` `_try_limit_then_market`:

- 22 entry attempts in last 7 days
- **0 filled as maker**
- All 22 rejected by Phemex with error `39999 "Error in place order"` before the 3s timeout
- All 22 silently fell back to taker market order
- Root cause: `exchange.py:288` uses `params={"timeInForce": "GTC", "postOnly": True}` but Phemex ccxt expects `params={"timeInForce": "PostOnly"}`

**Impact:** Fixing this one line (1-character change in JSON key) could cut fees from $0.107/trade → $0.02-0.05/trade. On 100 trades over 2 weeks: $5-8 saved. At current loss rate, **this alone may be the difference between losing and break-even.**

---

## The 5 Fixes

### Fix 1: `htf_confluence_pullback` trend-flip exit rule
**Problem:** 21/27 Sentinel AEs from this one strategy, summing −$14.48 gross. Current adverse_exit rule (−5% ROI after 10 cycles) is lagging — trades are deep red before it fires.

**Verified feasibility:**
- 1h EMA21/50 cache already exists at `bot.py:133` with 5-min TTL (`_htf_cache`)
- `htf_confluence_pullback` entry gate at `strategies.py:724-780` uses `htf_ema21 > htf_ema50 and htf_close > htf_ema50 and htf_adx >= 20`
- No collision: zero existing trend-flip exit logic (greped `trend_flip`, `htf_exit`)
- `pos.strategy` field already used for branching at `bot.py:689`, `risk_manager.py:602`, `backtest.py:391`

**Fix:** In `bot.py:629` (live) and `bot.py:1119` (paper) exit loops, for positions where `pos.strategy == "htf_confluence_pullback"`:
- Fetch 1h EMA21/50 from `self._htf_cache`
- If longs: if `ema21 < ema50` OR if current 5m candle closes >0.5% below entry → close with `reason="htf_trend_flip_exit"` or `"momentum_exit"`
- Mirror for shorts
- Whichever fires first; normal SL/TP/AE still apply as fallback

**Expected impact:** Kills 21 AEs worth −$14.48 → book flips from −$3.40 to ~+$11 gross on same trade flow
**Effort:** ~15-20 lines in `bot.py` + optional Position helper
**Risk:** Low. Only affects one strategy. Fallback to old AE rule preserved.

---

### Fix 2: Post-only param format bug fix
**Problem:** Maker path rejected by Phemex since deploy. 0% maker fill rate. All fees paid at full taker rate.

**Verified root cause:** `exchange.py:288` uses `"postOnly": True` which Phemex ccxt doesn't recognize. Correct format is `"timeInForce": "PostOnly"` or `"execInst": "PostOnly"`.

**Fix:** Single-line edit at `exchange.py:288`:
```python
# BEFORE:
params={"timeInForce": "GTC", "postOnly": True}
# AFTER:
params={"timeInForce": "PostOnly"}
```

**Expected impact:** Fees drop 50-80% depending on actual maker fill rate post-fix. At 50% maker rate: ~$4/week saved. At 70%: ~$6/week. Verified via `[MAKER] Limit filled` vs `[MAKER] ... failed` log tags after deploy.

**Effort:** 1 line + add a counter metric to `exchange.py` for maker-fill rate visibility
**Risk:** Low if tested properly. Potential risk: if Phemex timeInForce enum rejects the new value on some symbol, limit will fail and fallback to market — same as current behavior. Worst case = no change.

**Post-deploy verification:** After 10 trades, grep `logs/bot.log` for `[MAKER] Limit filled` count. If still 0 → diagnose further. If >0 → Telegram alert confirming fix.

---

### Fix 3: Extend existing kill switches (don't duplicate)
**Problem:** No daily loss halt, no global consecutive-loss halt, existing DD tiers start at 20% which is too loose for $84 account.

**Verified existing infrastructure:**
- `risk_manager.py:229-329` — tiered DD halts at 20/25/30% (30min/1hr/1.5hr pause)
- `bot.py:127` — `self._loss_streak` tracked but not wired to a halt
- `bot.py:1291-1300` — per-pair 3-loss blacklist (4hr)
- `telegram_commander.py:148-167` — `/pause` and `/resume` via `.pause_trading` sentinel file, `bot.py:396-429` reads sentinel

**Fix:** Extend, don't duplicate:
1. **Daily loss halt** in `bot.py` entry cycle: compute `today_net = sum(net_pnl for t in closed_trades if today)`. If `today_net < -0.03 * balance` → touch `.pause_trading` sentinel, write reason, Telegram alert. Auto-clears at 00:00 PT.
2. **Global consecutive-loss halt**: wire `self._loss_streak >= 5` to 4h entry halt, reuse `.pause_trading` sentinel, Telegram alert
3. **Tighter DD tier**: add 8% soft halt at `risk_manager.py` (15-min pause, opt-out via `/resume`), placed before existing 20% tier

**Expected impact:** Prevents runaway losing days. On worst 2 days of history, would have saved ~$3-5 each day = $6-10/2 weeks.
**Effort:** ~40 lines in `bot.py` + `risk_manager.py`
**Risk:** Low. Telegram /pause and /resume already work. Adding trigger conditions doesn't change the enforcement path.

---

### Fix 4: Dead paper slot + shadow filter cleanup
**Problem:** 5 dead/broken paper slots + unused shadow filter = cognitive tax, state bloat, dashboard noise.

**Slots to delete** (verified from this session's audit):
- `trading_state_5m_atr_gate.json` — last trade 04-01, 0 Sentinel-era trades
- `trading_state_5m_sma_vwap.json` — last trade 04-01, 0 Sentinel-era trades
- `trading_state_5m_v10_control.json` — last trade 04-01, 0 Sentinel-era trades
- `trading_state_5m_legacy_control.json` — 50 Sentinel-era trades, −$15.28 (worst performer, no A/B value)
- `trading_state_1h_momentum.json` — 21 trades −$5.47 + I18 data bug (reads 5m WS data, invalid)

**Keep:** `liq_cascade` (+$2.59 / 4 trades), `mean_revert` (+$2.00 / 1 trade)

**Shadow filter:** Remove `shadow_skip`/`shadow_hour_pt` write paths in `bot.py`, `risk_manager.py`, and display in `web_dashboard.py`, `scripts/daily_report.py`, `notifier.py`. Lessons.md confirms Z=0.055, not significant.

**Fix:** Delete state files; remove init code in `bot.py` paper slot section; grep and remove references in `web_dashboard.py`, `scripts/daily_report.py`, `notifier.py`.

**Expected impact:** No direct $ impact. Reduces surface area for future bugs. Legibility.
**Effort:** ~100 lines deleted across 4-5 files
**Risk:** Medium. Prior slot removals broke dashboard A/B card (lessons.md). `/pre-restart-audit` MUST grep for stale references.

---

### Fix 5: Audit & extend existing backtester
**Problem:** Need to validate Fix 1 (new AE exit rule) against historical data before trusting it. Every parameter decision so far has been based on <30 live trades — not enough for statistical power.

**Verified existing infrastructure:**
- `backtester.py` (435 lines) — CSV-driven replay, models SL/TP/adverse_exit/trailing. **Missing: fees, slippage, funding.** Supports CLI: `--strategy --pair --timeframe --days --wfo`
- `backtest.py` (1143 lines) — Live ccxt fetch, `adaptive_strategy` ensemble, models fees (0.06%/side) + slippage (0.05%). **Missing: adverse_exit, single-strategy isolation.**
- Neither has been validated against live trade records
- Both stub out L2 orderbook + tape/flow gates (cannot replay from history — documented at `backtest.py:1026-1030`)

**Fix:** Read-only audit + surgical extension:
1. **Day 2** (read-only): run both backtesters on current `htf_confluence_pullback`, document output format, identify gaps
2. **Day 3**: add fees + slippage to `backtester.py` (copy math from `backtest.py:33-34`); add `--ae-rule` flag to parametrize the AE logic at `backtester.py:201-212` (~30 min)
3. **Day 4**: calibration — replay last 27 Sentinel live trades through backtester, compare PnL/WR. Document mismatch. If >20% off, investigate before trusting outputs.
4. **Day 5-7**: sweep new AE rule (Fix 1) vs old AE rule on 90 days × 6 pairs. Report: does the new rule actually improve historical P&L?

**Critical caveat:** Backtester output will be **optimistic vs live** because OB/tape gates pass-through. Any backtest finding needs a live-confirmation period before trusted.

**Expected impact:** Indirect but enormous. Unlocks evidence-based tuning for everything after Day 7.
**Effort:** Day 2-3 audit + ~50 lines added; Day 4 validation; Day 5-7 sweeps
**Risk:** Low. Read-only + additive. Does not touch live bot.

---

### Fix 6: Weekly forensic-learn loop (scheduled /trade-audit)
**Problem:** Manual `/trade-audit` is on-demand only. Patterns in weekly data don't get surfaced unless a session happens to look. Memory updates drift behind reality.

**Verified existing infrastructure:**
- `/trade-audit` skill already exists (`.claude/skills/trade-audit/`)
- `telegram_commander.py` already wired for send-only messages
- `launchd` jobs already running (reconcile, daily-report, monitor)
- `memory/lessons.md` is the curated pattern store

**Fix:** Add a single launchd job that runs every Sunday 8 PM PT:
1. Runs `scripts/weekly_forensics.py` (new, ~80 lines)
2. Script loads last 7 days of closed_trades from `trading_state.json`
3. Computes deterministic pattern buckets (symbol × hour × side × exit_reason × confidence)
4. For each bucket with `n >= 10 and abs(win_rate - 0.5) > 0.2`, flags as "significant"
5. Drops Telegram summary: "Week X forensics: found N significant patterns, top 3 listed"
6. Writes full report to `reports/forensics_YYYY-MM-DD.md`
7. Does NOT auto-edit `memory/lessons.md` — user reviews the report and approves or rejects

**Why this is NOT an LLM loop:** Deterministic pattern detection (`pandas.groupby` + binomial test). No agent in the loop. No confidence theater. Just measurement on a schedule.

**Expected impact:** Prevents pattern drift between manual sessions. At 50 trades/week, after 4 weeks you have 200 trades → first statistically meaningful patterns emerge → first evidence-based rule proposal.
**Effort:** ~80 lines `scripts/weekly_forensics.py` + ~20 lines `com.phmex.forensics.plist` launchd job
**Risk:** Very low. Read-only + Telegram notification + markdown file write. No live-bot touching.

**Validation gates (CRITICAL — applies to ALL 6 fixes):**
Every fix must pass 3 verification checkpoints before being declared "done":
1. **Syntax check**: `python3 -m py_compile <file>` → must pass
2. **Smoke test**: run the new code path with mock data or dry-run → must produce expected output
3. **Live confirmation**: after deploy, tail `logs/bot.log` for 10 min and grep for the new log tag → must fire at least once

If ANY of the 3 fails → fix is NOT done, no "partially working" shipping. This is the direct lesson from 2026-04-07: `cvd_slope` was spec'd at ±0.3 but raw values were ±3M; `large_trade_bias` was hardcoded to 0.5; tape gates silently bypassed when trade_count ≤ 20. All three had passed syntax checks. None had passed live confirmation. The damage was 8 days of trading on broken gates.

**Validation command for Fix 2 specifically**: after deploy, wait for 5 live entries, then:
```
grep "\[MAKER\] Limit filled" logs/bot.log | wc -l
```
If >= 1 → bug is fixed. If 0 → the fix did not work, do not declare success.

---

## Sequencing

| Day | Actions | Restart? |
|---|---|---|
| **1** (tomorrow 2026-04-09) | Fix 1 + Fix 2 + Fix 3 + Fix 4 bundled. `/pre-restart-audit` → restart. Begin Fix 5 audit (read-only). | ✅ |
| **2** | Fix 5: run both backtesters, document. Monitor Day 1 fix effectiveness via Telegram. | ❌ |
| **3** | Fix 5: add fees to `backtester.py`, add `--ae-rule` flag, calibrate against live. | ❌ |
| **4** | Fix 5: calibration pass. If match within tolerance → trust. | ❌ |
| **5-7** | Fix 5: sweep new AE rule on 90 days × 6 pairs. Decision: is Fix 1 actually better in backtest? | ❌ |
| **8-14** | If backtest confirms Fix 1: monitor live. If not: iterate AE rule parameters, re-sweep, re-deploy. | Maybe 1 tuning restart |

---

## Success criteria

**End of Day 1** (2026-04-09):
- Bot restarted clean with 4 fixes
- Maker fill rate >20% in first 10 trades post-restart (measured via `[MAKER] Limit filled` count)
- No new bugs introduced (verified by logs + Telegram)

**End of Week 1** (2026-04-15):
- Fees reduced by ≥40% measured via reconcile vs pre-fix baseline
- At most 1 adverse_exit per day average (was ~3/day)
- Daily net PnL ≥ −$0.30 average (was −$1-2)
- Backtester validated against live + first sweep complete

**End of Week 2** (2026-04-22):
- Daily net PnL ≥ $0 average (break-even reached)
- OR: backtester definitively shows strategy has no edge at any parameter → pivot decision
- Either outcome is a win (no more guessing)

---

## What this plan is NOT

- ❌ Building a fund manager agent (premature, you don't need governance until you have something worth governing)
- ❌ Building a trader LLM agent (no edge to protect, $5/day API cost on $84 account is absurd)
- ❌ Timeframe migration 5m → 1h (verified: every real 1h sample is a loser, and the 1h paper slot has data bug I18)
- ❌ Replacing `htf_confluence_pullback` (it IS a 1h EMA21/50 pullback strategy — the proposed replacement)
- ❌ Raising the confidence floor (all 5 conf buckets are net-negative; nothing to raise to)
- ❌ Rebuilding backtester (two already exist totaling 1,578 lines)
- ❌ Rebuilding post-only order path (already exists at `exchange.py:280`, just has a 1-line param bug)

## What survived verification

Every fix in this spec has been verified against actual code + logs + lessons.md. Three of my original five proposals were caught as "rediscover existing infrastructure" violations of META-RULE #4:
- Post-only orders → exists, has bug
- Kill switches → partially exists, extend it
- Backtester → exists twice, needs extension

The remaining real work is much smaller than my initial pitch: ~80-100 lines new code, ~100 lines deleted, 1 critical 1-line bug fix, and audits of existing tools.

---

## Approval gate

User must approve this spec before `/superpowers:writing-plans` creates the implementation plan.

If approved: proceed to plan. If not: iterate here.
