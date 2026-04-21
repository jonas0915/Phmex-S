# Lessons

## META-RULES

1. **Preflight is step zero.** Read lessons.md + MEMORY.md + all reference_*.md BEFORE any work. No exceptions. Don't wait for hooks to remind you.
2. **Verify numbers before presenting.** Deploy verification agents alongside analysis agents in the FIRST pass. Never present unverified PnL sums, trade counts, or calculations to the user.
3. **Save memory incrementally.** Don't wait until session end. When you learn something reusable, save it immediately.
4. **Check existing infrastructure before proposing new.** Grep for features before suggesting to build them. The fix is often "tighten existing gates" not "build new system."
5. **Deploy parallel agents by default.** If a task has 2+ independent parts, parallelize. Don't work sequentially unless there are dependencies.
6. **Proactive verification, not reactive.** Don't wait for the user to say "verify this." Build verification into every analysis pass.
7. **Read all reference_*.md before proposing changes.** The current setup was built on prior R&D. Don't rediscover what is already documented.
8. **Always verify dashboard/report numbers against exchange truth before making decisions.** Fabricated or mislabeled data has caused real-money losses. Gross vs net, `reason` vs `exit_reason`, labels vs math — assume nothing, reconcile against Phemex CSV / raw API before presenting.

## Session Grades
- 2026-04-14 (session 1): A — Phase 2 v2 spec drafted + audited (4 parallel audit agents on v1 found schema break + restart-discipline + dashboard-propagation + ordering issues; v2 rewrite addresses all). 5 open-question research dispatched in parallel: confirmed only C1 landed, C2/C3/I9 still block Phase 2a fee work; reconcile CLEAN streak = 5 runs; dashboard bound 0.0.0.0 zero-auth (must lock). Migrated overwatch LLM `claude-sonnet-4-20250514` → `claude-sonnet-4-6` (deprecation 2026-07-14). Tightened TP 2.1→1.6 (16% ROI) and adverse -5.0→-3.0 after counterfactual analysis (16% TP would have rescued only $1.70/13d but adverse-tighten estimated +$9.42/13d). Discovered trailing stop NOT broken — fires were silently mis-tagged as `take_profit`/`stop_loss` because the string "trailing_stop" never existed in live exit-tag path. Extended risk_manager.py BUG-A fix (lessons.md:219-222) to emit `trailing_stop` and added 🎯 label in notifier.py per CLAUDE.md propagation rule. Pre-restart-audit: code review GREEN, syntax PASS, parameter crosscheck PASS. Bot restarted clean PID 24017. 3 commits. **Self-correction:** flagged TRADE_AMOUNT_USDT 5→10 in .env diff as a concern; Jonas pointed out CLAUDE.md project doc already documented $10 as the canonical value — should have cross-referenced project CLAUDE.md before raising. Lesson saved.
- 2026-04-13 (session 1): A — Orphan-position incident: BTC short ran to -45% unrealized (-$6.44) while bot showed `Positions: 0`. Root cause: commit ab51309 ("limit-only, no market fallback") created a race where late fills after "signal lost" became orphans. Bot had NO per-cycle scan for unknown exchange positions. Overwatch detected it correctly via Check 4 (`position_desync`) but (a) only ran 1× today due to broken plist scheduler (exit code 78), (b) Anthropic API key was invalid so fix specs failed, (c) `tg_send` silently no-op'd if creds missing. Deployed 7-layer fix: (L1) `_position_ground_truth` with pre-snapshot delta check — prevents mis-adopting user's manual positions; (L2) bot entry-failure safety net w/ ORPHAN ADOPTED telegram alert; (L3) per-cycle bidirectional sync — runs even when bot tracks 0 positions; (L4) overwatch tg_send now logs success/failure, main() isolates alert from fix-spec; (L5) new Check #12 `check_unrealized_drawdown` — flags -30% WARN / -50% CRITICAL ROI-on-margin; (L6) plist rewritten with StartCalendarInterval (24 hourly) + RunAtLoad + ~/Library/Logs/ path — exit code 78→0; rotated ANTHROPIC_API_KEY. Pre-restart audit caught C1 critical (ground-truth mis-match on pre-existing positions), fixed before deploy. Bot restarted PID 77271, cycle #1 clean.
- 2026-04-10 (session 2): A — Major reliability deploy: loop freeze fix (thread-wrapped REST + watchdog over sleep) + early exit signal #4 (peak drawdown). Found SUI trade Apr 9 hit +10% unrealized then reversed to -12% — two root causes: (1) DNS outage froze main loop 35 min (watchdog didn't cover time.sleep), (2) early_exit signals are lagging at profit peaks (RSI/MACD/EMA all read "bullish" at +10%). Also made DAILY_SYMBOL_CAP configurable (.env). T3 analysis: 31% WR on 13 samples — directionally interesting but n too small (audit flagged 5 logic issues). Multiple audit rounds caught critical "gap scenario" in signal #4 design. No corrections from Jonas. 5 commits deployed.
- 2026-04-10 (session 1): A — Deployed cluster throttle (max 1 htf entry per 30 min). Quick session — clear task from prior audit, clean execution, no corrections.
- 2026-04-09 (session 2): A — Completed all 15 tasks from 6-fix plan + backtester extension + regime shadow logger + full bot audit. Tasks 7-8 (live validation), 13-14 (forensics script + launchd), 15 (verification sweep), 9-12 (backtester audit + extension + calibration + 90-day sweep). Parallel agents throughout. Key finding: backtester is pessimistic (2.7x overtrade without gates), AE rule sweep inconclusive (trend-flip wins 4/5 pairs but BTC churns). No corrections from Jonas. Clean session.
- 2026-04-08 (session 2): A+ — Continued from session 1. Built full 2-week recovery plan after 5 rounds of agent verification caught 3 of 5 proposed "fixes" as META-RULE #4 violations (rediscovering existing infra). KEY DISCOVERY: maker fill rate is 0% since deploy — all 22 entry attempts rejected with Phemex error 39999 because exchange.py:288 uses `postOnly: True` but Phemex ccxt expects `timeInForce: "PostOnly"`. Single-line bug fix = ~50-80% fee reduction, potentially the difference between break-even and losing. Other verified existing infra: backtester.py (435L) + backtest.py (1143L), DD halt tiers 20/25/30%, Telegram /pause sentinel, _try_limit_then_market at exchange.py:280, 1h EMA cache at bot.py:133. Spec written: docs/superpowers/specs/2026-04-09-phmex-s-5-fixes.md. Agent layer proposals (fund manager, trader agent) rejected as premature — no edge to govern yet. Session rule: verify EVERY fix premise against existing code before proposing.
- 2026-04-08 (session 1): A — Fee lies returning. Pulled Phemex truth live: today's report was −$0.78/57% WR but truth was −$1.65/42.9% WR (fees $0.87 silently dropped to 0). Deployed continuous truth pipeline: reconcile_phemex.py gained `--apply` mode (atomic temp+rename, concurrent-safe, idempotent), launchd job cut from 4h print-only → 15min with --apply, daily_report.py reconciles before every run. Parallel Sentinel forensic agent + independent verification — agent was directionally right but quantitatively wrong (used gross instead of net; all conf buckets are negative net, not just conf-4). Verified findings: AE = 26/54 (48%) = −$17.41 net, htf_confluence_pullback owns 92% of bleed (21 AEs, −$14.48), hours 3 & 9 PT are 0% WR, hour 20 PT is 75% WR (don't scrap whitelist, surgically drop 3 & 9). Dispatched 3 parallel fix agents: (A) stop_loss mistag — `check_positions` now classifies SL-line hit by PnL sign (ratcheted SL above entry → take_profit); also added entry_price/exit_price aliases to trade dict. (B) entry_snapshot attach — live+paper now `_save_state()` immediately after snapshot assign, sync_positions preserves snapshot across restart. (C) conf=3 "leakage" was a false alarm — 04-04/05/06 are BEFORE 04-07 raise; only cosmetic `/6` → `/7` display fix. /pre-restart-audit passed, restarted, bot PID 21214, both live positions synced with SL/TP mirrored on exchange. Balance $84.20 ($68.32 free + $15.88 locked).
- 2026-04-07 (session 2): A+ — Massive forensics session. Found daily reports understating losses by $6.30/58% (gross PnL, fees never subtracted). Apr 7 review "+$8.27 Sentinel outperformance" was apples-to-oranges (gross vs net) — invalid. Sentinel AE rate was NOT 0%, it was 50.8% — exit_reason tagging bug (`reason` field written, `exit_reason` field read). Three of four Sentinel tape gates broken since deploy: cvd_slope 9 orders of magnitude off (±0.3 vs raw ±3M), large_trade_bias hardcoded to 0.5 forever, tape gates silently skip when trade_count≤20. Entry snapshots were dead code. Reconcile script computing fake $200 drift via signed notional. Deployed 17 fixes: normalized cvd_slope, real large_trade_bias compute, real fee capture via ccxt extract_order_fee, 69 historical trades FIFO-backfilled from Phemex CSV ($0.00 diff), dashboard net_pnl migration, reconciliation panel, 370 lines dead dashboard code removed, launchd reconcile every 4h with Telegram alerts. Phemex ground truth Mar 31–Apr 7: 69 trades, -$10.84 net, fees -$6.86 (63% of total loss). Sentinel per-trade economics WORSE than pre-Sentinel baseline. AE = 51% of trades, 100% of the bleed.
- 2026-04-07 (session 1): A — April 7 review deployed: SOL blacklisted (0W/6L), confidence gate raised 3→4, profitable hours trimmed to 4 windows (PT 3,9,14,20). Recursive Improvement Phase 1 fully deployed: sentinel file protocol, entry snapshot logging, Telegram commander (/status /balance /slots /kill /pause /resume), auto-lifecycle scanner (4hr launchd). 2 code review bugs caught pre-deploy (unguarded os.remove, unclosed Popen file handle). AE analysis: 5 of 7 today's AEs eliminated by deployed fixes. CVD gate finding: code already existed at bot.py:845-847 — failures were due to trade_count<20 guard bypassing gate.
- 2026-04-05 (session 2): A — Full trade audit of 12-trade losing day (-$2.94, 8 AE, 67% AE rate ending Sentinel's 0% streak). Built April 7 review queue with 5 ranked fixes (stale profitable hours, min conf gate, ADX threshold, hard-block PT 18:00, exit_reason tagging). Fixed 3 broken launchd jobs (monitor, daily-report, report-catchup) — silently failing 5 days due to macOS TCC blocking writes to ~/Desktop. Root cause: launchd can't write StdOut/StdErr to protected folders. Fix: moved logs to ~/Library/Logs/Phmex-S/. Lesson saved to feedback_launchd_tcc.md. Also set up 4 session-based cron agents for health/reports/audit/memory-cleanup.
- 2026-04-05 (session 1): A- — Deep trade audit of 7-trade losing day (-$3.06, all shorts in up market). Verified gate values at each entry — no gate failures, all trades legitimately passed. Verified shadow time filter data — NOT statistically significant yet (Z=0.055). Correctly decided NOT to harden time blocks (Jonas agreed). Created /trade-audit and /verify-work skills. Key finding: 6AM PT is in profitable set but actually negative — needs monitoring.
- 2026-04-04 (session 1): A — Fixed inflated balance reporting (requested vs actual margin), sync_positions disk persistence bug, analyzed trade frequency collapse (market regime, not gates). Full bot audit with parallel agents. Audited Recursive Improvement Phase 1 plan with 3 parallel review agents — found 9 critical + 6 important bugs in the plan code. Fixed all in the plan file. Plan is audit-clean for April 7 execution.
- 2026-04-03 (session 1): B+ — Fixed ban mode recovery loop (diagnostics, VPN re-rotation, Telegram escalation). Code review caught 2 criticals, audit caught a 3rd. Wrote Recursive Improvement Phase 1 implementation plan (7 tasks). Correctly held off execution until April 7 deploy date after Jonas flagged it.
- 2026-04-02 (session 3): B — Added Fees + Real PnL rows to A/B test dashboard card. Simple task but required 3 rounds of edits due to not clarifying ambiguous request upfront.
- 2026-04-02 (session 2): B+ — Massive dashboard overhaul (Bloomberg 3-column layout, Slot Lifecycle card, A/B Test card, /tracker route, dead V10 cleanup). Spec audit patched 6 gaps. Failed to verify Sentinel deploy timestamp before presenting stats — Jonas caught 28 vs 11 trade miscount. Good recovery.
- 2026-04-02 (session 1): A — Verified Sentinel overnight (626 gate blocks, all gates firing). Designed recursive improvement Phase 1 spec with full agent verification of all infrastructure claims (recalibration.py, strategy_factory.py, notifier.py, launchd). Spec written: auto-lifecycle + telegram commander + entry snapshot logging.
- 2026-04-01 (session 2): A — Deep bot performance analysis, root cause diagnosis, discovered existing L2/tape infrastructure, designed + implemented + deployed Sentinel (v11). 3-layer entry gates, paper slot cleanup, legacy_control A/B slot. Pre-restart audit passed. Deployed at 23:01 PT.
- 2026-04-01 (session 1): B — Handled Samsung Remote ops (restart, IP change), bot diagnostics. No code bugs to fix. Efficient network scan found TV IP change.

## Operational Lessons

### Samsung Remote: TV IP can change via DHCP
- The TV (Samsung UN65NU6900) gets its IP via DHCP and it changed from .84 to .100
- Diagnosis: ping sweep + ARP table scan, match MAC `00:7C:2D:E8:99:82` to find new IP
- Fix: update TV_IP in server.py. Recommend Jonas set a static DHCP reservation in router.

### Always run SamsungRemote with caffeinate
- Server dies if Mac sleeps. Launch with: `caffeinate -i python3 server.py`
- The server doesn't daemonize itself, so caffeinate keeps the system awake.

### Phmex-S Bot: Verify numbers before presenting
- When computing PnL sums from JSON trade data, verify the math before presenting to the user
- Deploy verification agents in the FIRST analysis pass, not as a follow-up
- Lesson learned: ATR Gate PnL was reported as -$5.44, actually -$6.24. V10 Control trades reported as 11, actually 9.
- Lesson learned (session 2): Used midnight Apr 1 as Sentinel deploy time, but bot actually restarted at 11:01 PM. Reported 28 Sentinel trades when only 11 were real. Always cross-check trade timestamps against bot.log startup lines before presenting A/B comparisons.

### Phmex-S Bot: Check existing infrastructure before proposing new
- The bot already has L2 orderbook (exchange.py:77-118) and tape/flow (ws_feed.py) infrastructure
- Always grep for existing features before proposing to build them
- The fix is often "tighten existing gates" not "build new system"

### Phmex-S Bot: Adverse exit is the #1 PnL drag
- Week of 3/26-4/01: 24 adverse exits cost -$10.43, all other exits made +$12.69
- Root cause: rapid re-entry (2-min cooldown too short) + HTF trend lag + underused tape/OB gates
- Good days have <30% AE rate, bad days have >50% AE rate

### Phmex-S Bot: Paper slots bypass live gates
- Paper slots (bot.py:952-1018) do NOT use ensemble confidence, flow veto, or time filters
- This means adding gates to the live path doesn't automatically apply to paper slots — must add separately
- legacy_control slot intentionally stays ungated as A/B control
- When removing paper slots, check for stale references in web_dashboard.py and daily_report.py

### Phmex-S Bot: Version names are trade-index based
- Dashboard version labels (web_dashboard.py:300-315) use trade count boundaries, not config
- When deploying a new version, set the boundary to current closed trade count
- Current: Pipeline = trades 247-341, Sentinel = trades 342+

### Phmex-S Bot: Pre-restart audit catches real bugs
- Code review agent found stale state file references (v10_control, sma_vwap) in dashboard + report after slot removal
- Without the audit, legacy_control A/B comparison would have been invisible on the dashboard
- Never skip the pre-restart audit — it pays for itself

### Phmex-S Bot: Telegram is send-only — no two-way yet
- notifier.py uses raw requests.post, not python-telegram-bot library
- No polling, no webhook, no command handlers exist
- Same TELEGRAM_TOKEN supports both send and receive (standard Bot API)
- python-telegram-bot not installed but all deps present — single pip install
- Phase 1 recursive improvement adds telegram_commander.py as separate daemon

### Phmex-S Bot: Projections are not verified findings
- When presenting analysis, clearly separate verified data from projections/estimates
- "AE rate will drop to <30%" is a target, not a verified claim
- The only way to verify projections is to run the experiment and measure
- Legacy_control A/B slot exists specifically to verify Sentinel's improvement claim

### Don't assume scope on display changes — ask to clarify
- When the user says "add X" to a display, they may want X alone, or X plus derived values (e.g., "add fees" might mean fees AND fee-adjusted PnL).
- If there's any ambiguity about scope, ask upfront: "Do you want just the fee amount, or also the real PnL after fees?"
- Listen carefully to corrections: "just add the fees" means literally only fees. But a follow-up like "I want both" clarifies the full intent.
- The cost of one clarifying question is much less than 3 rounds of edits.

### Phmex-S Bot: Don't execute plans before their deploy date
- Recursive Improvement Phase 1 has a deploy date of April 7 (5-day Sentinel eval)
- I almost started executing the plan on April 3 — Jonas correctly stopped me
- Always check spec deploy dates before executing implementation plans
- Building early risks the live bot; the plan can wait

### Phmex-S Bot: Balance reporting was inflated by ~$3
- Bot stored REQUESTED margin ($10) instead of ACTUAL exchange margin ($6.76)
- Fix: recalculate pos.margin from fill_amount * fill_price / LEVERAGE after fill
- Also fix: available -= pos.margin (actual), not margin (requested)
- Deployed 2026-04-04

### Phmex-S Bot: sync_positions must save state to disk
- sync_positions() loaded exchange positions into memory but never called _save_state()
- This meant trading_state.json on disk showed 0 positions after restart even though bot tracked them in memory
- Fix: added self._save_state() at end of sync_positions() if positions were synced
- Deployed 2026-04-04

### Phmex-S Bot: Shadow time filter is NOT statistically significant yet
- 27 shadow trades vs 31 profitable-window trades over 7 days
- WR nearly identical: 44.4% vs 45.2% (Z-score 0.055, need >1.96)
- Some shadow hours are profitable (8-10 PM PT: +$3.11)
- Do NOT blanket-block all shadow hours — kills evening wins
- Jonas explicitly rejected blocking 7/8 AM PT despite losses there
- Wait for more data before hardening any time blocks

### Phmex-S Bot: All-shorts-in-up-market is the real risk
- Apr 5: 7 trades, ALL shorts, market ground up. -$3.06 PnL
- Strategy had no mechanism to detect directional regime mismatch
- 1h trend said "short" but 5m price refused to follow through
- This is a strategy limitation, not a gate problem — gates can't fix wrong direction

### Phmex-S Bot: Low trade frequency is market regime, not gates
- Apr 1-4: trades dropped 18→10→2→1 — looked like Sentinel gates were too tight
- Investigation: 79% of ADX readings <20, 97% of volume readings <0.5x average
- Strategy-level filters (ADX, volume) blocked 1,277+ candidates before any Sentinel gate fired
- Sentinel gates only blocked 48 candidates on Apr 4 — they're NOT the bottleneck
- The market is in a low-ADX, low-volume chop regime — correct behavior is to stay out

### Phmex-S Bot: Ban mode recovery was blind and infinite
- Deployed fix 2026-04-03: diagnostics (ping + VPN status), VPN re-rotation every 2 failures, Telegram alert every 60 min
- Pre-existing bug: recovery loop retried the same thing forever with no escalation
- Code review caught 2 critical bugs (missing function, missing return) — always run review agents
- Audit caught a 3rd reset point (startup ban entry) — pre-restart audit pays for itself

### Phmex-S Bot: Sentinel first night — gates are firing
- 626 gate blocks overnight (2026-04-02 05:03–07:40)
- Daily cap working: ETH, SOL, SUI all hitting 3-trade cap by 07:35
- Legacy_control trading ungated as expected (took XRP short while live was capped)
- Trade size updated to $10/trade (was $5)

### Phmex-S Bot: Accounting bugs compound silently
- Gross pnl_usdt + missing fees + wrong exit_reason tagging = $6.30 hidden loss over 8 days (58% under-report)
- Daily reports read `pnl_usdt` (gross) and labeled it "PnL". Fees were never subtracted for live trades.
- Exit reason analytics read `exit_reason` but risk_manager wrote `reason` -> Sentinel AE rate falsely reported as 0% when it was actually 50.8%
- Fix: fees_usdt/funding_usdt/net_pnl fields on every trade, all dashboards/reports switched to net_pnl, 69 trades FIFO-backfilled from Phemex CSV

### Phmex-S Bot: Never trust labels — verify the math
- April 7 review claimed "Sentinel +$8.27 outperformance" — it was comparing Sentinel gross vs V10 Control net. Apples-to-oranges.
- Any comparison must use the same accounting basis on both sides. Verify what each column actually contains before drawing conclusions.
- The phrase "Sentinel is winning" drove real parameter decisions that were based on a corrupted baseline.

### Phmex-S Bot: Dimensional mismatches in gate thresholds are silent killers
- Sentinel `cvd_slope` threshold was spec'd at ±0.3 but raw values ranged ±100 to ±3,000,000 — 9 orders of magnitude off. Gate fired randomly.
- `large_trade_bias` was hardcoded to 0.5 and never updated by any code path — flagship gate was a constant.
- Tape gates silently bypassed when `trade_count <= 20` with no log line — impossible to detect from logs alone.
- Always unit-test gate thresholds against real raw distributions before deploying. Log every skip/bypass with a reason.

### Phmex-S Bot: Dead code lookalikes — "deployed features that do nothing"
- Entry snapshot dict literal existed in bot.py but was never attached to Position -> `closed_trades` always had empty snapshot fields.
- If you grep and find the feature "exists," also verify it's wired end-to-end (read -> compute -> write -> consumer).
- "Feature deployed" is not proven by code presence — only by a value landing in the destination.

### Phmex-S Bot: Backfill from exchange export is gold
- 69/69 trades matched exactly ($0.00 diff) when backfilled via FIFO pairing against the Phemex CSV
- Exchange CSV is the single source of truth — any internal number that disagrees with it is the bug, not the CSV
- Always keep a reconcile script that can replay the full history from exchange data

### Phmex-S Bot: Sync fee capture from ccxt info dict, use FIFO for pairing
- Phemex does NOT expose `closedPnlRv` in fill records returned by ccxt — you cannot compute per-trade PnL from a single fill
- Fee IS present in ccxt order response via `exchange.extract_order_fee()` — capture at fill time
- For historical reconciliation, pair entry/exit fills FIFO per symbol — signed net notional gives false drift ($200+ phantom)

### Phmex-S Bot: Fees are the dominant bleed, not bad entries
- 8-day Phemex truth (Mar 31 -> Apr 7): Gross -$3.95, Fees -$6.86 (63% of total loss), Net -$10.84
- AE trades = 51% of all Sentinel trades and concentrate 100% of the net bleed. Killing AE trades = +$12.57 gross alone.
- Sentinel per-trade economics are WORSE than the pre-Sentinel baseline — the Apr 2 "Sentinel is winning" narrative was built on corrupted exit_reason data.

### Phmex-S Bot: Maker fill rate is 0% — postOnly param format bug (2026-04-08)
- `exchange.py:288` uses `params={"timeInForce": "GTC", "postOnly": True}` — Phemex ccxt rejects this with error 39999
- Correct format: `params={"timeInForce": "PostOnly"}`
- Evidence: 22 entry attempts in 7 days, 0 `[MAKER] Limit filled` log lines, 22 `[MAKER] ... failed ... using market` warnings
- Silent failure — bot falls back to taker market order, pays full 0.06%/side instead of ~0% maker
- This is why fees are 62% of losses despite _try_limit_then_market being wired correctly
- **Fix is a 1-character JSON key change** — single highest-value session discovery
- Before trusting ANY maker path: grep logs for `[MAKER] Limit filled` count. If 0, the param format is wrong.

### Phmex-S Bot: Agent layers are premature — governance without edge is theater
- Rejected fund manager + trader agent proposals this session
- Rationale: no edge to govern, 4 agents on $84 account = infrastructure theater
- Replace "fund manager" with 3 hardcoded kill switches in bot.py (daily loss, DD tier, consecutive loss)
- Replace "trader agent" with scheduled /trade-audit skill once a day
- Rule: don't build management layers until you have something worth managing

### Phmex-S Bot: META-RULE #4 violation rate is high — always verify before proposing
- Session 2026-04-08-2: 3 of 5 proposed "fixes" were rediscover-existing-infra violations
  - Post-only orders → exists (exchange.py:280)
  - Kill switches → exists (DD tiers, Telegram pause, per-pair halt)
  - Backtester → exists twice (435+1143 lines)
- Dispatching 3 parallel verification agents caught all of them before code was written
- Rule: for ANY non-trivial fix proposal, run at least one agent pass specifically for META-RULE #4 ("does this already exist?") before writing anything

### Phmex-S Bot: Subagent forensics drifts on gross-vs-net and trade counts
- First Sentinel forensics agent claimed 54 trades, actual was 27 (2x overcount)
- Same agent used gross PnL in buckets where fees matter — conclusions were directionally right but numerically wrong (e.g., "conf 5 is positive +$0.32" — actually −$1.38 net)
- Rule: independently re-verify any critical number from a subagent before presenting it. The forensics subagent is fast but imprecise.

### Phmex-S Bot: Fee lies regress silently — always pull exchange truth
- Daily report on 2026-04-08 showed "Fees: $0.00" for 7 trades when Phemex charged $0.87 — known I7 bug regressed on 04-07/08 trades after the 04-07 fix
- Fix deployed: `reconcile_phemex.py --apply` patches trading_state.json fees_usdt/net_pnl from Phemex fills, atomic temp+rename, concurrent-safe
- launchd `com.phmex.reconcile` runs every 15 min with --apply (was 4h print-only)
- `daily_report.py` runs reconcile --apply before every report
- Rule: any report showing fees=$0 is lying until proven by exchange CSV. Never trust local fee fields without a recent reconcile.

### Phmex-S Bot: stop_loss mistag — check_positions must classify by PnL sign
- 14 Sentinel-era "stop_loss" trades were 12/14 wins totaling +$4.80 — impossible
- Root cause: `check_positions` tagged every `should_stop_loss(price)` hit as "stop_loss", even when `check_breakeven`/`update_trailing_stop`/`partial_close_position` had ratcheted SL above entry
- Fix (risk_manager.py:~640): if `pos.pnl_usdt(price) > 0` at SL trigger, classify as "take_profit" instead
- Also fix: trade dict now persists `entry_price`/`exit_price` aliases (not just legacy `entry`/`exit`)

### Phmex-S Bot: entry_snapshot loss across restarts
- Only 3/26 Sentinel AE trades carried entry_snapshot — sync_positions() on restart rebuilt fresh Position objects clobbering disk-restored snapshots
- Fix: sync_positions() now reads existing Position before rebuild, preserves entry_snapshot/shadow_skip/shadow_hour_pt
- Fix: bot.py calls `self.risk._save_state()` immediately after `pos.entry_snapshot = ...` assignment (live + paper slot paths)
- Lesson: any in-memory attribute that matters forensically MUST be saved to disk immediately, not deferred to next save

### Phmex-S Bot: Trust but verify subagent forensics
- 2026-04-08 Sentinel forensics agent claimed "conf=5 is the only positive bucket (+$0.32)" — independent re-run showed conf=5 is actually −$1.38 net. ALL conf buckets are negative net after fees.
- Agent was computing on gross PnL while fees now properly dominate (post fee-reconcile deploy)
- Agent also fabricated "4 conf=3 trades opened AFTER 04-07 raise" — 04-04/05/06 are chronologically BEFORE 04-07
- Rule: always re-run critical numbers independently before acting on subagent findings. Agents drift on timeline/gross-vs-net.

### Phmex-S Bot: Don't tune on corrupted data — fix data layer first
- 3 of 5 Sentinel forensic findings this session pointed at data-layer bugs (stop_loss mistag, entry_snapshot gap, fee reconcile lag)
- Retuning strategy on those numbers would repeat the 04-07 "+$8.27 Sentinel outperformance" mistake
- Sequence: data bugs → 24h clean data → then strategy retune. Never skip the data step.

### Phmex-S Bot: Known issues logged but NOT fixed 2026-04-07 session 2 (user restricted bot code edits)
- C1: pullback carve-out uses "bb_reversion" but _extract_strategy_name returns "bb_mean_reversion" — carve-out broken for BB reversion [LANDED 2c89ad8, verified 2026-04-20 bot.py:1113]
- C2: paper slot has no cvd_slope carve-out at all [LANDED, verified 2026-04-20 bot.py:1623-1625 — paper path exempts same tuple as live]
- C3: _sync_exchange_closes fee matching uses `recent[-1]` (race window)
- I9: REST fallback CVD not normalized in exchange.get_cvd
- I18: 1h_momentum paper slot reads 5m WS data (invalidates results)
- I1: entry log says "Conf: X/6" but there are 7 ensemble layers
- I7: Missing fees silently become 0 in net_pnl (no fees_pending flag)
- I8: sync_positions overwrites ATR-based SL/TP with fixed-% on restart
- I15: Regime pause reuses notify_ban_mode(30) sending misleading CDN message
- Zero tests in the entire repo

### Phmex-S Bot: htf_confluence_pullback cluster entries are the #1 loss source (2026-04-09)
- 27/57 htf_confluence_pullback trades entered in clusters (2+ within 30 min on different symbols)
- Clusters account for -$14.10 of -$14.47 total strategy loss. Non-cluster trades are -$0.37 (breakeven).
- Every cluster of 3+ trades went 0 wins. When the 1h regime read is wrong, all symbols lose together.
- The strategy itself is sound for solo entries. The problem is correlated multi-symbol entries.
- Fix: throttle htf_confluence_pullback to 1 entry per 30-min window.
- The 1h EMA direction gate was simulated and found useless — 98% of entries already align with 1h trend. AEs happen WITHIN the prevailing trend, not against it.
- Confidence score (3-6/7) has zero predictive power — all cluster at 30-36% WR.

### Phmex-S Bot: Backtester is pessimistic without gates (2026-04-09)
- Calibrated backtester.py against 9 days of live Sentinel trades: 156 backtest trades vs 58 live (2.7x), -$48.95 vs -$7.44 (6.6x worse)
- Root cause: backtester has no OB imbalance gate, tape gate, per-pair cooldown, daily symbol cap, or global cooldown. It takes every raw signal.
- Win rate is aligned (~42% both) — the confluence signal's base hit rate is accurately modeled
- **Use backtester for relative comparisons only** (A vs B rule), not absolute PnL forecasting
- The live gates ARE the edge — they filter out 63% of signals and those signals are mostly losers

### Phmex-S Bot: Trend-flip AE churns BTC but helps altcoins (2026-04-09)
- 90-day sweep: trend_flip wins 4/5 pairs (ETH/SOL/BNB/XRP) but generates 1351 BTC trades vs 463 ROI
- 1h EMA21/50 crosses too frequently on BTC — creates churn, total net worse (-$566 vs -$534)
- Per-pair AE gating (trend-flip for alts, ROI for BTC) is a promising research direction
- Keep ROI as universal default until per-pair gating is tested

### Phmex-S Bot: DNS outage froze main loop for 35 min — positions unmonitored (2026-04-10)
- SUI LONG on Apr 9 hit +10% unrealized ROI then reversed to -12% loss. Early exit never ran.
- Root cause 1: All 5 WS feeds dropped at 8:28 AM PT (DNS: "Cannot connect to ws.phemex.com"). REST fallback also hung on DNS. ccxt `timeout:10000` only covers HTTP read/write, NOT DNS resolution.
- Root cause 2: `time.sleep(Config.LOOP_INTERVAL)` at bot.py:419 was OUTSIDE the try/except — watchdog alarm didn't cover it.
- Fix deployed: (A) `socket.setdefaulttimeout(10)` at startup, (B) `_call_with_timeout()` thread wrapper on all REST reads (15s), (C) sleep moved inside watchdog scope (alarm 120→180s).
- Rule: ALL ccxt REST calls must go through `_call_with_timeout`. Order placement (close_long, close_short, place_sl_tp) is excluded — must complete or raise.

### Phmex-S Bot: Early exit signals are lagging at profit peaks (2026-04-10)
- `should_exit_early()` uses 3 reversal signals (RSI<45, MACD crossover, price<EMA-9). At +10% ROI peak, all 3 read "bullish" — they confirm reversals AFTER they happen.
- At 8%+ ROI only 1-of-3 needed, but 0-of-3 fire at the peak. 100% miss rate at profit tops.
- Fix: Signal #4 (peak drawdown) — if peak_roi >= 8% and drawdown from peak >= 3%, `return True` immediately (bypasses signal count). For peak 5-8% + 2% drawdown, counts as 1 signal.
- CRITICAL DESIGN LESSON: The "gap scenario" — tiering drawdown threshold by current pnl_pct (not peak_roi) creates a dead zone. At 10% peak dropping to 7%, the 3% threshold applies while at 8%+ pnl, but once pnl drops below 8%, it switches to 2% threshold needing 2-of-4. Fix: use peak_roi for the immediate-exit tier, not current pnl.
- peak_price must be updated BEFORE should_exit_early runs (trailing stop updates at bot.py:782, after early exit at bot.py:622). Inline update added.
- Rule: When designing tiered thresholds, always walk through the transition scenarios. Edge cases at tier boundaries are where bugs hide.

### Phmex-S Bot: DAILY_SYMBOL_CAP made configurable (2026-04-10)
- Was hardcoded to 3 at bot.py:887. Now reads from Config.DAILY_SYMBOL_CAP (.env, default 3).
- T3 (3rd trade per symbol per day) has 31% WR on 13 symbol-days — directionally bad but n=13 is too small.
- Audit flagged: selection bias (cap-hit days are high-activity days), correlation≠causation, 95% CI spans 11-59% at n=13.
- Decision: keep at 3, revisit after 30+ symbol-days (~6-10 weeks). Don't change parameters on thin data.

### Phmex-S Bot: Trailing-stop mistag — extends BUG-A fix (2026-04-14)
- Symptom: Jonas observed "trailing stop stopped working." Verified across 426 closed trades — **zero** had `exit_reason=="trailing_stop"`. Believed broken.
- Root cause: trail was firing fine — code path is intact (`update_trailing_stop` called every cycle at bot.py:792, `should_stop_loss` short-circuits to trail check at risk_manager.py:93-102). But `check_positions` at risk_manager.py:668-677 had only two branches after `should_stop_loss` returned True: `take_profit` (PnL>0) and `stop_loss` (PnL<0). The string "trailing_stop" did not exist in the live exit-tag path — only in backtester.
- Smoking-gun evidence: 5 Sentinel-era trades tagged `stop_loss` had POSITIVE PnL (+2.76%, +1.34%, +2.93%, +6.92%, +3.09% ROI) — these landed exactly on tier-1 (+2%) and tier-3 (+6%) lock-in floors. Trail fires in disguise. Even after BUG-A fix retagged them to `take_profit`, the trail/TP distinction was lost.
- Fix (risk_manager.py:668-679): branch on `pos.trailing_stop_price is not None` first. If trail-armed AND PnL>0 → `trailing_stop`. Else PnL>0 → `take_profit`. Else `stop_loss`.
- Propagation per CLAUDE.md rule: notifier.py:53-55 emits 🎯 TRAILING STOP. daily_report.py + web_dashboard.py already use generic exit_reason bucketing — auto-display new bucket.
- **Rule:** before debugging bot logic that "stopped working," verify the data layer first. Reports may be lying via mis-tagging — symptom presents identically to actual failure. Especially: when an exit_reason is missing entirely from history, suspect the tag pipeline before the trigger logic.

### Phmex-S Bot: Cross-check CLAUDE.md before flagging .env drift (2026-04-14)
- Pre-restart-audit flagged `TRADE_AMOUNT_USDT 5.0 → 10.0` as a concerning unintended change because the diff was bigger than my staged edits. Jonas corrected: $10 was the documented canonical value all along (project CLAUDE.md). The .env at 5.0 was the drift; the bump to 10.0 was a restoration.
- **Rule:** when the audit-diff includes pre-existing changes you didn't make, cross-reference the project-level CLAUDE.md and any session-handoff notes BEFORE flagging them as concerns. The canonical state may be in docs, not in code/config. Flagging a non-issue as risky wastes a confirmation cycle.
- **Rule (general):** project-level CLAUDE.md is authoritative on parameter values when they conflict with .env. Treat divergence as a drift bug to flag, not as evidence the .env is the source of truth.

### Phmex-S Bot: Orphan positions — the three-layer defense (2026-04-13)
- Incident: BTC short at $70,915 orphaned (user closed manually at -45% / -$6.44). Bot had `Positions: 0` — had no idea position existed. `adverse_exit` never fired because it only evaluates tracked positions.
- Root cause: commit ab51309 made entries limit-only (no market fallback). On "signal lost", bot logged and moved on without confirming the exchange. Late fills could slip through the cancel-race and become orphans.
- **Three-layer defense (deployed 2026-04-13):**
  - L1 `exchange._position_ground_truth(symbol, side, pre_amount)` — snapshot positions BEFORE create_order, only trust delta growth. Prevents mis-adopting the user's manual pre-existing position.
  - L2 bot.py entry-failure safety net — on "signal lost" in live mode, check ground truth with the stored pre_amount; if delta detected, adopt + SL/TP + Telegram "⚠️ ORPHAN ADOPTED".
  - L3 bot.py `_sync_exchange_closes` now bidirectional — detects (A) closed-on-exchange and (B) untracked orphans. Runs every cycle, EVEN when `self.risk.positions` is empty (dropped that guard — orphans are defined by that state).
- **Also deployed:**
  - Overwatch Check #12 `check_unrealized_drawdown` — flags any exchange position at -30% (WARN) / -50% (CRITICAL) ROI-on-margin
  - Overwatch `tg_send` now logs success/failure at INFO/WARN (was silent no-op if creds missing)
  - Overwatch `main()` isolates send_alert from generate_fix_specs (Anthropic outage must not silence Telegram)
  - Launchd plist: StartCalendarInterval (24 hourly entries) + RunAtLoad + ~/Library/Logs/ paths — exit code went 78 → 0. The old `StartInterval=3600` was firing only ~1×/30h due to Mac sleep.
- **Rule:** any exit path in order placement that returns "no fill" MUST check exchange ground truth. Never trust order-tracking alone. Real money sits on the other side of every race.
- **Rule:** any per-cycle exchange reconciliation must run even when the bot tracks 0 positions — that's exactly when orphans are possible.
