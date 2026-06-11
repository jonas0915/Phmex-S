# Part B — Trailing-Stop Profit Protection: Plan of Action

- **Date written:** 2026-06-08 (Sun)
- **Target:** buildable work done + deployed **2026-06-09 (Mon)**
- **Owner:** Claude (build/audit) · Jonas (restart OK + GO/NO-GO calls)
- **Goal:** stop winners from round-tripping to the −12% exchange stop, via an
  exchange-durable trailing stop — shipped only on evidence, not a guess.

---

## The core problem this resolves
The trailing stop ratchets a profit floor in **software**, checked once per 60s against the
5m candle close (`risk_manager.py:37-91`, `should_stop_loss` 93-102). It never moves a resting
order on the exchange (only `check_breakeven` does, `bot.py:833-851`). So a fast reversal
between cycles blows past the locked profit down to the −12% stop → the `exchange_close`
bleed (−$17.76 / 32 trades, this session's data).

## The hard constraint (why "decide tomorrow" isn't possible, but "deploy tomorrow" is)
Making the trail exchange-resting is **outcome-changing**: a resting order fires on intra-
minute **wicks** the 60s software loop never sees (trail bands are just 0.3–0.5% of price at
10x). We have **only 5m OHLC on disk — no tick/sub-minute data** — so the wick effect
**cannot be backtested** (verified 2026-06-08). The only honest evidence is **forward
shadow-logging**. Therefore: build + deploy the logger tomorrow; decide GO/NO-GO once it has
data.

---

## TIMELINE

### TODAY (2026-06-08, tonight) — Claude, no live risk
- [ ] Finalize this plan + update the design spec to the approved shape.
- [ ] Write the **shadow-logger** (read-only instrumentation, no order changes):
  - On every cycle, for each open position with the trail **armed** (peak ROI ≥ +5%),
    record: timestamp, symbol, entry, current `trailing_stop_price`, the mid-cycle ticker
    `last` price (already fetched at `bot.py:405-407`), the 5m candle high/low, and the
    actual software exit when it happens.
  - Append to `logs/shadow_trail.jsonl`. Pure logging — touches no orders, no SL/TP.
- [ ] Self-review + syntax check. Confirm zero changes to any order/exit path.

### TOMORROW (2026-06-09, Mon)

**Morning (Claude):**
- [ ] `/pre-restart-audit` on the shadow-logger diff (must also grep cross-project sprint
  memory per `lessons.md:458-463`).
- [ ] Confirm it's logging-only: no diff in `risk_manager.py` exit logic, no `place_sl_tp`,
  no `edit_order`, no `cancel_*` on the live path.

**Deploy window (needs Jonas):**
- [ ] When the bot is **flat (0 open positions)** — it was flat as of last check — get Jonas's
  explicit restart OK and deploy the shadow-logger. Data starts accruing immediately.
- [ ] Verify first armed-trail event lands in `shadow_trail.jsonl`.

**By Mon EOD — what "resolved" means:**
- Shadow-logger **live and collecting**.
- Part A (un-missable breakeven SL) audited and deploy-ready (see its own spec).
- A dated GO/NO-GO gate on the calendar (below). Nothing about durable trailing ships blind.

### DECISION GATE — ~2026-06-23 to 06-29 (data-dependent)
The bot takes ~2 trades/day; armed-trail events are a subset. Need ~15–20 armed events for a
read. Estimated **~2–3 weeks**. When enough events accrue, Claude analyzes
`shadow_trail.jsonl`:
- How often would an exchange-resting trail have fired on a **wick** that the software loop
  survived (premature exit)?
- For those, did the trade **recover** (wick-out cost) or keep falling (durable would've
  saved it)?
- Net $ effect on actual fills: **losers saved − winners wicked out**.
- **GO** if clearly net-positive → build durable trailing (atomic `edit_order` amend +
  ≥0.1% throttle, per design spec) → `/pre-restart-audit` → deploy in a flat window.
- **NO-GO** if net-negative/ambiguous → keep software trailing; Part A already covers the
  breakeven level. Document and close.

---

## FAST-TRACK ALTERNATIVE (if you want protection LIVE tomorrow, not in ~3 weeks)
If waiting for data is unacceptable, we ship durable trailing **tomorrow** accepting the
wick-out risk blind. To de-risk going in without data, ship a **conservative variant**:
- Use a **wider trail band** (e.g. trail 1.0–1.5% from peak instead of 0.3–0.5%) so the
  resting stop is far enough from price to rarely catch noise wicks, trading a bit of
  give-back for far fewer false stop-outs.
- Atomic `edit_order` amend + ≥0.1% throttle; `/pre-restart-audit`; deploy in a flat window
  with explicit OK.
- **Claude's flag:** this is shipping an un-backtested outcome change on live $56. The
  shadow-logger should run **alongside** it regardless, so we still learn the real wick rate.

**My recommendation: evidence-first (the timeline above).** Take the fast-track only if you
explicitly accept the blind-deploy risk.

---

## Guardrails (apply to both paths)
- Atomic `edit_order` amend only — never blunt `cancel_open_orders` (it nukes the TP,
  `exchange.py:783-796`). One-time live validation of `edit_order` param shape first.
- New order helper must "complete or raise" — not timeout-wrapped (`lessons.md:290`).
- Do NOT break the `trailing_stop` / `stop_loss` / `take_profit` classification
  (`risk_manager.py:668-679`) — documented mistag regression.
- Propagate any new tag/metric to `notifier.py` + `scripts/daily_report.py` +
  `web_dashboard.py` (`CLAUDE.md:14-18`).
- Mandatory `/pre-restart-audit` + no-open-position window + explicit restart OK before any
  live deploy.

## What I need from you
1. Confirm **"Part B" = this trailing-protection workstream** (vs. something else you meant).
2. **Evidence-first or fast-track?** (I recommend evidence-first.)
3. Restart OK tomorrow when the bot is flat, to deploy the shadow-logger.

---

## DECISIONS — 2026-06-11 (Jonas)
1. **Part B = this workstream** — confirmed.
2. **FAST-TRACK chosen.** Durable exchange-resting trailing ships with the conservative
   wide band (1.0–1.5% from peak), accepting the blind-deploy wick risk explicitly.
   Shadow-logger runs alongside regardless, so the real wick rate still gets measured.
3. **Restart approved + executed 2026-06-11 ~9:56 AM PT** (flat window, 0 open positions
   verified two ways; /pre-restart-audit passed). Shadow-logger is LIVE.
4. **Design-spec Q2 resolved: YES** — use `max(breakeven_lock, current_trailing_floor)`
   so the exchange SL is never looser than the software trailing intent.

### Build status
- [x] Shadow-logger written (`bot.py` `_log_shadow_trail`, call site after all exit paths)
- [x] Self-review + syntax check + independent audit agent (PASS; REST ticker call
      removed per audit — executor-teardown tail latency, see method comment)
- [x] /pre-restart-audit passed; deployed in flat window
- [ ] First armed-trail event lands in `logs/shadow_trail.jsonl` (arms at peak ROI ≥ +5%)
- [x] FAST-TRACK build DEPLOYED 2026-06-11 ~10:28 AM PT (PID 10869, flat window,
      /pre-restart-audit PASS, 15/15 tests green). `move_stop_loss` atomic amend +
      1.2% wide-band durable trail + `durable_sl` exit tag + dashboard/Telegram
      propagation. One-time live `edit_order` param validation = first live amend
      (verbose-logged, fallback is the safety net) — STILL PENDING until a trail arms.
- [ ] Follow-up (pre-existing, audit-flagged): `[SL CHECK]` re-place path still
      cancels-before-places (bot.py ~785) — route through move_stop_loss later.

---

## FAST-TRACK BUILD ADDENDUM — 2026-06-11

Architecture decision: the durable exchange trail is a **wide backstop**, not a
replacement for the software trail. The software tiers (0.3–0.5% price from peak)
keep firing first via the 60s loop; the resting exchange order ratchets at a wide
band below peak so a fast reversal between cycles hits the durable order long before
the −12% static stop — while sitting far enough from price that noise wicks rarely
catch it.

### 1. `exchange.move_stop_loss(symbol, side, amount, new_sl, sl_order_id) -> str`
- **Primary:** `client.edit_order(sl_order_id, symbol, "market", order_side, amount,
  None, params={triggerPrice, triggerDirection, reduceOnly:True})` — amend in place,
  zero naked window. Retry 3× on ANY transient error (1s/2s backoff). Complete-or-raise
  (no `_call_with_timeout`, per lessons.md:290).
- **Fallback (amend exhausted):** place new SL (same param shape as `place_sl_tp`,
  3 attempts, raise on exhaustion) → `verify_sl_order(new_id)` → only then
  `client.cancel_order(old_id, symbol)` best-effort (warn on failure; orphan
  reduce-only is cleaned by `cancel_open_orders` at close). Old SL is NEVER cancelled
  before the new one is confirmed.
- Returns the resting SL order id. Skips ids equal to `"software"` sentinel (raises
  ValueError — caller must not route software-SL positions here).
- First live amend = the one-time `edit_order` param validation: request/response
  logged at INFO with full params; the fallback path is the safety net if Phemex
  rejects the amend shape.

### 2. bot.py breakeven/trailing block (replaces 823-851 logic)
- `target = max(breakeven-ratcheted pos.stop_loss, durable_floor)` for longs
  (min for shorts), where `durable_floor = peak_price * (1 ∓ DURABLE_TRAIL_BAND_PCT/100)`,
  armed only when `pos.trailing_stop_price is not None` (peak ROI ≥ +5%). This
  satisfies Q2: the resting order is never looser than the breakeven lock; it is
  intentionally looser than the tight software trail (backstop role).
- **Ratchet-only:** never moves the exchange SL away from price.
- **Throttle:** amend only when `|target − pos.exchange_sl_price| / price ≥ 0.1%`.
- **Failure:** old order still rests (amend non-destructive) → log `[SL-MOVE-FAIL]`,
  Telegram alert, leave `pos.sl_order_id` unchanged. NO silent `"software"` downgrade.
- Software-SL positions (`sl_order_id == "software"`) keep current behavior.

### 3. New config / state
- `.env: DURABLE_TRAIL_BAND_PCT` (price %, default **1.2**, spec range 1.0–1.5).
- `Position.exchange_sl_price: Optional[float]` — the price the resting exchange SL
  actually sits at. Persisted in state; missing key on load defaults to None
  (backward compatible). Re-derived on startup sync.

### 4. Propagation (CLAUDE.md rule)
- `notifier.py`: `[SL-MOVE-FAIL]` alert + durable-SL level in position lines.
- `scripts/daily_report.py`: count of durable-SL saves vs software exits.
- `web_dashboard.py`: show `exchange_sl_price` per open position (no stale lie where
  the dashboard shows `stop_loss` but the resting order sits elsewhere).

### 5. Tests (before audit)
- `move_stop_loss`: amend-success / amend-fail→fallback-success / fallback-place-fail
  keeps OLD SL + raises / cancel-old-fail warns but succeeds. Mocked ccxt client.
- Target computation: Q2 max(), short-side min(), ratchet-only, throttle boundary.
- Regression: exit-reason classification (risk_manager.py:668-679) byte-identical.
