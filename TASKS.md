# TASKS — 2026-09-21 evening: harden the desk after the cascade_v2 paper kill

Owner: "proceed" on item 1 (7:50 PM PT). No bot trading code, no restart. bot.py / .env / trading_state* / sentinels untouched.

## Why
informed_flow_btc_alt_cascade_v2 was killed 9/21 6:00 AM PT on the −$10 any-n cap after ONE BTC-pump event fired 5
concurrent $200 shorts. (a) No concurrency cap existed anywhere in the spec → screen → prereg → slot chain.
(b) GIGGLE was delisted 8/7 (cache ends 8/1) and nothing checked market status. (c) The maint job never announced
the kill (detect_events skips slots already killed) and the kb rows waited for the next Sunday desk run — I wrote
DEAD_LIST 112 / SURVIVORS / LESSONS by hand.

## Tasks (A ∥ B ∥ C, then integration + review)
- [x] **A. Portfolio concurrency cap** — fee_math.max_concurrent(); registrar fills spec.max_concurrent at freeze;
      screen.run_screen admits trades under the cap (old specs without the key: unchanged, audits still reproduce);
      build.js prereg states + freezes the cap, IMPLEMENT recipe enforces it in the slot; STANDARDS #17; README; tests.
- [x] **B. Universe tradeability check** — lib/universe_check.py (pure check over a ccxt markets dict + fetch + CLI);
      desk.js registrar drops inactive symbols before freeze and records them; reconciler writes a LESSONS line for
      drops; tests. (build.js precondition + STANDARDS #18 + README + DATA.md note = integration step, after A lands.)
- [x] **C. Maint reconciles paper verdicts same day** — detect_events fires on None→killed (bug); for swarm-registered
      slots (SURVIVORS row) maint deterministically appends the DEAD_LIST row, updates the SURVIVORS status cell,
      writes the LESSONS line, runs kb_check, commits; PASS grade → SURVIVORS status "PAPER PASS — awaiting owner";
      idempotent against today's hand-written row 112; tests in tests/test_swarm_desk_runner.py.
- [x] Integration: B's build.js Step-0 precondition, STANDARDS #18, README, DATA.md GIGGLE note.
- [x] Review agents on all changed files; full pytest; commit per task; push.
- [x] Memory + TASKS review section.

## Review (2026-09-21 8:20 PM PT)
**All work landed in commit 5a40936** — the hourly auto-backup (8:17 PM) swept the working tree into one `chore(auto-backup)` commit and pushed it before the per-task commits ran; not rewritten (already on origin). Contents of 5a40936 (19 files, +1259/−97):
- A: research/swarm/lib/{fee_math,registrar,screen}.py + tests. `fee_math.max_concurrent(150)` = 3. Legacy specs byte-identical (md5 proof by the implementer). 92 tests in the 4 lib files (was 70).
- B: research/swarm/lib/universe_check.py (new) + tests/test_swarm_universe_check.py (15) + kb/DATA.md note; desk.js register seat prunes inactive symbols before freeze, reconciler LESSONS line, critic clause. Live check: GIGGLE DELISTED, BTC/ETH active.
- C: scripts/swarm_desk.py maint — None→killed event (the 9/21 6:01 kill was never announced), same-day DEAD_LIST/SURVIVORS reconciliation, state schema 2, idempotent vs row 112; tests 59→69.
- Integration: build.js Step-0 c2 (SPEC_MISSING_MAX_CONCURRENT) + c3 (UNIVERSE_UNTRADEABLE), prereg sections, IMPLEMENT MAX_CONCURRENT guard; STANDARDS #17 + #18; README.
- **Two extra defects found while chasing the 7:31 AM second kill event:** (1) tests/test_lab_adjudicator.py `build_digest()` graded the REAL v2 book and wrote the LIVE `.kill_informed_flow_btc_alt_cascade_v2` during the 7:30 AM code-health pytest → autouse fixture redirects BOT_DIR to tmp_path (proven: sentinel lands in tmp, repo clean). (2) scripts/code_health.py compileall now excludes research/swarm/runs/ + docs/ (records, not code) — was CRITICAL every morning since the 9/20 desk run.
- Verification: full suite `1 failed, 1222 passed` (the 1 = known ordering-only `test_isolation_never_imports_live_bot_modules`, passes alone); `node --check` both workflows OK; kb_check `[]`; compile check OK; no live sentinels written by the suite. Two independent review agents: APPROVE / APPROVE.
- Not touched: bot.py, .env, state files, sentinels, launchd. No restart needed; maint/adjudicator/code-health are launchd jobs that read fresh code at their next run (6:00 / 6:30 / 7:30 AM PT).
- Lesson: the auto-backup job commits+pushes the whole tree at :17 every hour — commit per task BEFORE :17 or expect a sweep.
