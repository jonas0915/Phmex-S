# TASKS — 2026-09-21 evening: harden the desk after the cascade_v2 paper kill

Owner: "proceed" on item 1 (7:50 PM PT). No bot trading code, no restart. bot.py / .env / trading_state* / sentinels untouched.

## Why
informed_flow_btc_alt_cascade_v2 was killed 9/21 6:00 AM PT on the −$10 any-n cap after ONE BTC-pump event fired 5
concurrent $200 shorts. (a) No concurrency cap existed anywhere in the spec → screen → prereg → slot chain.
(b) GIGGLE was delisted 8/7 (cache ends 8/1) and nothing checked market status. (c) The maint job never announced
the kill (detect_events skips slots already killed) and the kb rows waited for the next Sunday desk run — I wrote
DEAD_LIST 112 / SURVIVORS / LESSONS by hand.

## Tasks (A ∥ B ∥ C, then integration + review)
- [ ] **A. Portfolio concurrency cap** — fee_math.max_concurrent(); registrar fills spec.max_concurrent at freeze;
      screen.run_screen admits trades under the cap (old specs without the key: unchanged, audits still reproduce);
      build.js prereg states + freezes the cap, IMPLEMENT recipe enforces it in the slot; STANDARDS #17; README; tests.
- [ ] **B. Universe tradeability check** — lib/universe_check.py (pure check over a ccxt markets dict + fetch + CLI);
      desk.js registrar drops inactive symbols before freeze and records them; reconciler writes a LESSONS line for
      drops; tests. (build.js precondition + STANDARDS #18 + README + DATA.md note = integration step, after A lands.)
- [ ] **C. Maint reconciles paper verdicts same day** — detect_events fires on None→killed (bug); for swarm-registered
      slots (SURVIVORS row) maint deterministically appends the DEAD_LIST row, updates the SURVIVORS status cell,
      writes the LESSONS line, runs kb_check, commits; PASS grade → SURVIVORS status "PAPER PASS — awaiting owner";
      idempotent against today's hand-written row 112; tests in tests/test_swarm_desk_runner.py.
- [ ] Integration: B's build.js Step-0 precondition, STANDARDS #18, README, DATA.md GIGGLE note.
- [ ] Review agents on all changed files; full pytest; commit per task; push.
- [ ] Memory + TASKS review section.

## Review
(filled at the end)
