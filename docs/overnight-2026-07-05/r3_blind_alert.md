# R3 — "Bot is blind" alert (built 2026-07-06, NOT yet live — needs restart)

## Why
Two silent network outages on 7/6 (bot.log gaps verified: largest 6:29 AM–7:28 AM PT,
58.7 min; afternoon 3:10 PM–3:34 PM PT) — WS feeds stale, cycles stalled, bot recovered
silently, zero alerts. Same failure family as the June host-sleep loss (−$1.42 XLM).

## Investigation: why overwatch missed it (requirement #1)
- Overwatch = `scripts/overwatch.py`, launchd `com.phmex.overwatch`, schedule in
  `~/Library/LaunchAgents/com.phmex.overwatch.plist`: **every 4 hours**
  (12 AM / 4 AM / 8 AM / 12 PM / 4 PM / 8 PM local) + RunAtLoad. NOT hourly despite its
  docstring.
- It ran on schedule all day 7/6 (logs/overwatch.log: runs at 12 AM, 4 AM, 8 AM, 12 PM,
  4 PM — all completed). Both outages fell entirely between ticks and had recovered
  before the next run (8 AM run saw a log that resumed at 7:35 AM; 4 PM run saw one
  that resumed at 3:34 PM).
- Even if a run had landed mid-outage, **no check would have fired**:
  - `check_process_alive` (overwatch.py:171) — process existed the whole time.
  - `check_log_errors` (:212) — outage lines were WARNING level, not ERROR.
  - `check_ws_freshness` (:283 post-edit) — counts stale/reconnect EVENTS in the last
    60 min of bot.log; a stalled bot writes **nothing**, so the count is low/zero.
  - No check measured "how old is the last log write" → requirement #3 applied
    (log-freshness check added, see below). No existing check was mis-thresholded;
    the capability was genuinely missing, so this is not a duplicate.
- Residual gap (by design, per constraints): overwatch's 4-hour cadence means the
  external check only catches a stall that is STILL in progress at a tick. The in-bot
  detectors below cover the between-ticks window; no new launchd job was added.

## Changes

### bot.py (in-bot, Telegram-only, zero trading-logic changes)
- **bot.py:256–345** — new `BlindMonitor` class (header comment :256, class :268;
  pure state machine, `notify` injected for tests):
  - `check_cycle_gap` (bot.py:294) — stall-recovery notice: gap between cycle starts
    > 300s → one retroactive `[BLIND-RECOVERED] bot was stalled/blind X min
    (<from>–<to> PT), now resumed` (covers host sleep / process freeze; renders
    dates when the gap crosses a PT midnight).
  - `check_ws_blind` (bot.py:315) — WS-blind detection: ALL subscribed symbols stale
    (`ws_feed.is_stale`, 120s default) for > 300s continuous →
    `[BLIND] all WS feeds stale since <time PT> — entries effectively paused,
    exchange SL still armed`; re-alert cooldown 3600s (spans flapping episodes);
    `[BLIND-CLEARED]` once on recovery (only if an alert was sent).
  - All times 12-hour PT via `zoneinfo` America/Los_Angeles (`_fmt_pt`, bot.py:280).
  - Sends via existing `notifier.send`; notify exceptions swallowed (bot.py:288).
- **bot.py:363** — `self._blind = BlindMonitor()` in `Phmex2Bot.__init__`.
- **bot.py:848–858** — wiring at top of `_run_cycle`, BEFORE the ban-mode
  early-return so outage cycles are still covered; whole block wrapped in
  try/except so the monitor can never break a cycle. All-stale is evaluated over
  `self.active_pairs`.

### scripts/overwatch.py (external, covers the process-frozen case)
- **overwatch.py:54** — threshold `BOT_LOG_FRESH_MAX_MIN = 10`.
- **overwatch.py:255–303** — new `check_bot_log_freshness`: bot.log mtime older than
  10 min while the bot process exists → CRITICAL Telegram ("Bot BLIND/FROZEN —
  process alive but bot.log silent for X min (last write <time PT>)"). Stale log +
  no process → OK (defers to `check_process_alive`, which auto-restarts). Missing
  log or failed process check → WARNING.
- **overwatch.py:793** — registered in `run_all_checks` right after
  `check_process_alive` (an auto-restart freshens the log before this check reads
  it); docstring count 12 → 13 (:791).
- Overwatch is a script (no import from live bot) — the new check is live at its
  **next 4-hour tick, no restart/reload needed**.

### tests/test_blind_alert.py (new, 16 tests, fixture-based, no network)
- WS-blind state machine: silent under 5 min; alert exactly once with required
  copy + PT time; re-alert after 60-min cooldown; recovery message once + state
  reset; short blip → zero messages; flapping inside cooldown → no spam (episodes
  an hour apart DO both alert); raising notify never propagates.
- Stall notice: first-call/normal-gap silence; 59-min gap (today's real
  6:29→7:28 AM stall) → one notice with "59 min" + both PT endpoints; baseline
  resets after a notice; cross-midnight gap renders dates.
- Overwatch check: fresh→OK (process not even probed); stale+process→CRITICAL with
  minutes, PT time, PID in diagnostics; stale+no-process→OK deferring to
  process_alive; missing log→WARNING; registration in `run_all_checks` asserted.

## Verification
- `python3 -m py_compile bot.py scripts/overwatch.py tests/test_blind_alert.py` — clean.
- Full suite: **354 passed** (baseline before change: 338 passed) — 16 new, 0 broken.
- Nothing restarted. bot.py changes are staged for the next restart
  (pre-restart-audit required per project rules); the overwatch check goes live on
  its next scheduled run automatically.

## Rollback
- In-bot: remove the `_run_cycle` block (bot.py:848–858), the `__init__` line
  (bot.py:363), and the `BlindMonitor` class (bot.py:256–345).
- External: remove `check_bot_log_freshness` from the `run_all_checks` list
  (overwatch.py:793) — the function itself is then inert.
