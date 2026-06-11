# Solidify the Breakeven Stop-Loss — Design Spec

- **Date:** 2026-06-08
- **Status:** DRAFT — awaiting user approval
- **Author:** Claude (with Jonas)
- **Scope:** Risk engine — breakeven stop-loss reliability (Part A) + earlier engagement (Part B)
- **Touches real money:** YES. Requires `/pre-restart-audit` + a no-open-position window before deploy.

---

## 1. Problem

Two independent failures let profitable trades come back as full −12% losers:

1. **The breakeven SL move has a naked-position window.** When the stop is raised, the bot
   cancels the existing exchange SL+TP *first*, then tries to place the new pair
   (`bot.py:835-838`). There is no `try/except`, no rollback, and no verification. If the
   re-place fails for any reason that is not a rate-limit, `place_sl_tp` does not retry and
   does not raise — it returns null ids (`exchange.py:735-740`) and the position silently
   downgrades to a software-only SL with **no order resting on the exchange**
   (`bot.py:849`). This is the documented mechanism behind the SUI −12% DNS freeze
   (`lessons.md:285-291`) and the XLM cancel-race (`docs/fix-proposals/2026-04-28-08-...`).

2. **Breakeven almost never fires.** It triggers at +1R, which at the default 1.2% stop ×
   10x leverage = **+12% ROI** (`risk_manager.py:241-256`). Earlier exits — `early_exit`
   (+3%), `trailing_stop` (+5%), the +8% peak-drawdown cut — almost always fire first, so
   breakeven is effectively dead code (`bot.py:662-851`).

Verified loss data (this session, `trading_state.json`, strategy `htf_l2_anticipation`,
105 records): `exchange_close` = −$17.76 (32 trades), the single largest loss bucket; these
are positions ridden to the −12% exchange stop.

---

## 2. Goals / Non-Goals

**Goals**
- A1. An SL order is **always** resting on the exchange when the stop moves — no naked window.
- A2. If the durable SL can ever not be guaranteed, the bot **alerts loudly** (Telegram) and
      does not silently pretend it is protected.
- B1. Breakeven engages **earlier** so trades that go modestly green get a guaranteed
      above-entry (or small-loss-capped) stop on the exchange.

**Non-Goals**
- Not changing entry logic, strategy selection, leverage, or position sizing.
- Not re-enabling adverse exit (tracked separately).
- Not removing the existing trailing-stop tiers (Part B coordinates with them, see §4.3).

---

## 3. Part A — Make the breakeven SL move bulletproof (risk-only-down)

### 3.1 Current (broken) sequence — `bot.py:833-851`
```
old_sl = pos.stop_loss
pos.check_breakeven(price)              # may raise pos.stop_loss in memory
pos.update_trailing_stop(price)
if pos.stop_loss != old_sl and pos.sl_order_id and pos.sl_order_id != "software":
    self.exchange.cancel_open_orders(symbol)        # ← kills SL + TP FIRST
    sl_tp = self.exchange.place_sl_tp(...)          # ← then places; no retry/verify/rollback
    pos.sl_order_id = sl_tp.get("sl_order_id") or "software"   # ← silent downgrade on fail
```

### 3.2 New sequence — atomic amend (primary), verified cancel-by-id (fallback)

The capability check (§ Appendix A) found a strictly-better option than the original
"place-before-cancel": Phemex via ccxt supports `edit_order` with a new `triggerPrice`, which
**moves the resting SL server-side with zero window where no stop exists.** This is the
primary mechanism.

**Primary — atomic amend (no gap, no duplicate-order risk):**
1. Call `move_stop_loss(symbol, side, amount, new_sl)` (new helper in `exchange.py`) which
   issues `client.edit_order(pos.sl_order_id, symbol, "market", order_side, amount, None,
   params={"triggerPrice": new_sl, "triggerDirection": sl_trigger_dir})`. The resting stop is
   amended in place; it never disappears.
2. **Verify** via `verify_sl_order` (`exchange.py:772-781`) that the SL now sits at the new
   trigger price.
3. **If amend or verify fails:** the original SL is still resting (amend is non-destructive on
   failure). Log `[BREAKEVEN-FAIL]`, fire a Telegram alert, fall through to the fallback.

> One-time validation required: `edit_order` for trigger orders has never been exercised in
> this bot. Before relying on it live, validate the exact param shape (whether
> `triggerDirection`/`reduceOnly` must be re-sent on amend) with a single controlled live
> amend in a no-position-critical window. (Q3.)

**Fallback — cancel-just-the-SL-by-id, then place + verify + retry:**
If amend is unavailable/unreliable, do NOT use the blunt `cancel_open_orders` (it nukes the TP
too). Instead:
1. Place the new SL, verify it landed.
2. Then `client.cancel_order(pos.sl_order_id, symbol)` — cancels ONLY the old SL by id, leaves
   the TP untouched (this single-id cancel is already used elsewhere, `bot.py:845`; §3.4).
3. If the new SL fails to place/verify, leave the OLD SL in place, log `[BREAKEVEN-FAIL]`,
   alert. Never cancel the old SL until the new one is confirmed live. No naked window.

### 3.3 Retry on ALL failures, not just rate-limits
`place_sl_tp` currently retries only on `_is_rate_limit_error` (`exchange.py:736`). The new
`move_stop_loss` helper retries on **any** transient exchange error (timeout, network, DNS,
5xx) with bounded backoff (e.g. 3 attempts). Per `lessons.md:290`, order-path calls must
"complete or raise" and are deliberately excluded from the `_call_with_timeout` wrapper —
this helper follows that rule (it raises on exhaustion; the caller in §3.2 step 4 handles it).

### 3.4 Preserve the TP
`cancel_open_orders` cancels SL **and** TP (`exchange.py:783-796`) — never use it on the
breakeven path. The amend path (§3.2 primary) never touches the TP. The fallback path cancels
**only** the SL by id via `client.cancel_order(pos.sl_order_id, symbol)` — this single-id
cancel is **already proven in the codebase** (`bot.py:845` cancels just the TP by id in
partial-close mode), and SL/TP ids are tracked separately on the `Position`
(`risk_manager.py:27-28`). Any cancel-by-id must skip ids equal to the `"software"` sentinel.
(Q4 — RESOLVED feasible.)

### 3.5 Verification loop already exists — wire breakeven into it
The per-cycle `[SL CHECK]` loop (`bot.py:778-792`) re-verifies non-software SL ids each cycle
and re-places if missing. After Part A, a breakeven-moved SL that ever drops to `"software"`
must (a) raise an alert and (b) be picked up by this loop for re-placement. Confirm the loop
preserves the breakeven-adjusted price (it claims to at `bot.py:789-790`) and does not reset
to the Config % stop.

### 3.6 Must-not (regression guard)
Do **not** alter the exit-reason classification in `check_positions`
(`risk_manager.py:668-679`). Breakeven ratcheting the SL above entry is what previously caused
profitable breakeven/trail exits to be mistagged as `stop_loss` (`lessons.md:228-232,
306-312`). The branch on `trailing_stop_price` + PnL sign must stay intact.

---

## 4. Part B — Engage breakeven earlier

### 4.1 Parameters (confirmed with Jonas)
- **Trigger:** position reaches **+6% ROI** (= +0.6% price move at 10x).
- **Lock:** move SL to **+3% ROI** above entry (= +0.3% price above entry).

### 4.2 Fee math for the chosen +3% lock
At 10x, +3% ROI = +0.3% above entry. Taker round-trip cost ≈ **0.22% price**
(`risk_manager.py:246`: 0.06% taker ×2 + 0.05% slippage ×2). So a stop resting at +3% ROI
that fills nets ≈ +0.3% − 0.22% = **+0.08% price = +0.8% ROI net — a genuine small locked
profit.** (Jonas's initial +1% would have netted ≈ −1.2% after fees; bumped to +3% to clear
the fee floor and stay green.)

| Lock level (ROI) | Price above entry | Net after ~0.22% fees | Meaning |
|---|---|---|---|
| +1% (initial idea) | +0.10% | ≈ −1.2% ROI | tiny-loss cap |
| +2.5% (current code) | +0.25% | ≈ +0.3% ROI | true breakeven |
| **+3% (CHOSEN)** | **+0.30%** | **≈ +0.8% ROI** | **small locked profit** |

### 4.3 Interaction with the existing trailing stop
The trailing stop arms at **+5% ROI** and locks a **+2% ROI** floor at its first tier
(`risk_manager.py:53-63`). Today that floor is **software-only**. With Part A, the breakeven
move puts a **durable exchange order** at the locked level. To avoid the exchange SL (+1%)
being *looser* than the software trailing floor (+2%), the breakeven lock should be
**coordinated with — and not below — the trailing floor at the same ROI**. Cleanest design:
the +6% breakeven simply ensures the exchange SL is moved to the locked level, using
`max(breakeven_lock, current_trailing_floor)` so the resting order is never looser than the
software intent. (Q2.)

### 4.4 Simulation gate — DO NOT ship Part B blind
Prior R&D (`docs/superpowers/specs/2026-04-25-bleed-analysis.md`) ran exactly this lever and
found it **net −$0.20**: rescued ~11 losers (+$4.23) but clipped ~10 winners (−$4.43). Hard
rule (`lessons.md:354`): an exit-logic change must be simulated **both sides** — trades saved
AND trades clipped — before shipping.

**Plan:** build/refresh a bar-by-bar OHLCV replay over the actual taken `htf_l2_anticipation`
trades, sweep trigger/lock = {**+6%/+3% (chosen)**, +6%/+2.5%, +5%/+3%, +4%/+3%}, and report
for each: losers rescued, winners clipped, **net $**. Ship the +6%/+3% config ONLY if it is
net-positive under current params. This is a read-only analysis; it does not touch the bot.

> Caveat (`MEMORY.md:45`, `lessons.md`): the entry simulator failed its ±15% calibration. This
> replay is exit-only over *already-taken* trades (no entry simulation), which is materially
> safer, but results are still directional — we treat a clearly-positive result as the bar.

---

## 5. Propagation (mandatory — `CLAUDE.md:14-18`)
Any new exit tag, fallback event, or breakeven metric MUST be reflected in:
- `notifier.py` + `scripts/daily_report.py` (Telegram) — incl. the new `[BREAKEVEN-FAIL]`
  alert and any "SL moved to breakeven" notification.
- `web_dashboard.py` — so the dashboard does not show a stale/false protection state.
A silent change here is a reporting lie.

---

## 6. Testing & validation
1. **Unit-level (paper/dry):** simulate `move_stop_loss` success, place-fail, verify-fail,
   and DNS-timeout paths; assert the position is never left without a resting SL and that the
   failure path keeps the OLD SL + alerts.
2. **Classification regression:** assert breakeven/trailing/TP exits still tag correctly
   (`risk_manager.py:668-679`) — no `stop_loss` mistags.
3. **Part B simulation (§4.4):** both-sides net-$ table before any trigger change ships.
4. **Live smoke (no-position window):** deploy Part A during a flat window, open one small
   live probe, confirm a breakeven move places-before-cancels and the `[SL CHECK]` loop sees
   the new id.

---

## 7. Rollout
1. Approve this spec.
2. Implement Part A. Run Part B simulation in parallel (read-only).
3. `/pre-restart-audit` (must also grep cross-project sprint memory per `lessons.md:458-463`).
4. Deploy Part A in a **no-open-position window**, with explicit restart OK from Jonas.
5. Decide Part B trigger/lock from the simulation numbers; if green, ship + re-audit.

---

## 8. Open questions
- **Q1 (lock level):** ✅ RESOLVED — **+3% ROI** (Jonas, 2026-06-08). Nets ≈ +0.8% after fees.
- **Q2 (coordination):** use `max(breakeven_lock, trailing_floor)` so the exchange SL is never
  looser than the software trailing intent? Recommendation: yes. **← still needs your nod.**
- **Q3 (no-gap placement):** ✅ RESOLVED — atomic `edit_order` amend moves the stop server-side
  with zero gap (best option); cancel-by-id+place is the fallback. One-time live param
  validation of `edit_order` for trigger orders required before relying on it.
- **Q4 (single-order cancel):** ✅ RESOLVED — feasible today; `client.cancel_order(id, symbol)`
  already used at `bot.py:845`; SL/TP ids tracked separately (`risk_manager.py:27-28`).

## Appendix A — Exchange capability findings (2026-06-08)
- **Account is one-way / Merged mode** (no `posSide`/hedge set anywhere; ccxt defaults to
  `Merged`). SL = reduce-only conditional market trigger order (`exchange.py:723-731`).
- **Atomic amend FEASIBLE:** ccxt `phemex.has['editOrder'] == True`; `edit_order` maps
  `triggerPrice`→`stopPxRp`/`stopPxEp` to Phemex's amend-by-orderID endpoint. Unused in this
  bot today → validate param shape with one live amend.
- **Place-before-cancel (two resting SLs):** UNKNOWN — reduce-only duplicate acceptance in
  Merged mode is undetermined from code; would need a live test. Superseded by amend, so not
  needed.
- **Single-id cancel FEASIBLE today:** `client.cancel_order` already used by id at
  `exchange.py:423,574,791` and `bot.py:845`. Must skip `"software"` sentinel ids.
