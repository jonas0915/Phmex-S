# Session Handoff — Resume Here

**Last session ended:** 2026-04-17 ~8:00 PM PT
**Session grade:** A — major feature session, 15 commits, all verified live
**Bot PID:** 26384 (restarted 2026-04-17 7:45 PM PT)
**Dashboard PID:** ~active (port 8050)
**Balance at session end:** ~$73.57 USDT (peak $76.24, drawdown 3.5%)

---

## What was deployed this session (3 features, 15 commits)

### Feature 1: `htf_l2_anticipation` strategy — parallel to `htf_confluence_pullback`
Runs alongside the existing confluence pullback strategy. Replaces the `bouncing = close > prev_close` candle confirmation with L2/tape confirmation:
- **3 required signals:** `buy_ratio > 0.55` (longs) / `< 0.45` (shorts), `cvd_slope` directional (>0 long, <0 short), `bid_depth > ask_depth` (longs) / opposite (shorts)
- **3 boosters:** `large_trade_bias > 0.2` (+0.03), bid/ask wall within 1% (+0.02), no adverse wall within 0.5% (+0.02)
- Shares HTF trend, VWAP, pullback-to-EMA, RSI, volume gates with original — only confirmation layer differs
- HTF cluster throttle (30 min) and trend-flip exit extended to cover both strategies

### Feature 2: L2 Anticipation Signal Monitor dashboard panel
New panel on right column of dashboard. Reads `l2_snapshot.json` and renders a live table:
- Columns: Symbol, buy_ratio, cvd_slope, depth bid/ask ratio, whale bias, READY status
- READY column shows **direction**: ✅ LONG 3/3, ✅ SHORT 3/3, ⚠️ MIXED NL/NS, 🟠 N/3, 🔴 0/3
- Dropped duplicate Reconcile Status card in same session

### Feature 3: Real-time L2 snapshot writer thread
Daemon thread writes `l2_snapshot.json` every 5 seconds (was 60s main-loop). Dashboard polls every 3s (was 20s). End-to-end latency: ~4s average, 8s worst case. No API calls — reads from ws_feed in-memory cache and `_ob_depth_cache` populated by main loop.

### Commits (chronological)
```
042bdd8 feat: wire htf_l2_anticipation into confluence router + STRATEGIES dict
ffbcdc0 feat: pass flow dict to strategy_fn + extract htf_l2_anticipation name
f47ec7e feat: include htf_l2_anticipation in trend_strats + HTF cluster throttle
420c029 fix: extend HTF throttle update + trend-flip exit to htf_l2_anticipation
b649d41 docs: L2 signal dashboard panel spec
78874e6 feat: bot writes l2_snapshot.json each cycle for dashboard
75bced6 feat: add L2 Anticipation Signal Monitor dashboard panel
ca554f3 refactor: remove duplicate Reconcile Status card from observability panel
3f619c4 fix(dashboard): L2 panel READY column shows direction (LONG/SHORT/MIXED)
2990f0f docs: L2 realtime snapshot thread spec
6c7dad1 feat: L2 snapshot writer moved to 5s daemon thread (real-time)
3653b52 fix: set self.running=True before L2 writer thread start (race fix)
40bdbdd feat(dashboard): poll every 3s for real-time L2 panel updates
```

---

## What to monitor next 24-48h

1. **htf_l2_anticipation trade count** — should start accumulating. Compare against `htf_confluence_pullback` on same setups.
2. **L2 signal alignment** — does any symbol hit ✅ LONG 3/3 or SHORT 3/3 reliably? If not, thresholds may need tuning.
3. **Thread stability** — `[L2_LIVE]` write failures in bot.log. Should be none.
4. **Dashboard responsiveness** — L2 panel values should visibly change every 5s during active markets.
5. **Snapshot file mtime** — should update every 5s (check with `stat -f %Sm l2_snapshot.json`).

## Success criteria (after 50 htf_l2_anticipation trades)
- WR ≥ 43.9% (htf_confluence_pullback baseline)
- Net PnL per trade > -$0.08
- Fires earlier than pullback strategy on same setups
- Adverse exit rate ≤ existing rate (~5.5%)

---

## Architecture snapshot

### Entry gate flow (unchanged from prior session)
Signal → Global cooldown → Per-pair cooldown → Divergence cooldown → Ensemble conf → Tape gate + soft tape gate → Divergence gate → Funding → Time blocks → HTF cluster throttle → Kelly → OB → QUIET regime → Entry

### New in this session
- **2 confluence strategies** now fire in parallel: `htf_confluence_pullback` (baseline) + `htf_l2_anticipation` (new)
- **`_ob_depth_cache`** in Phmex2Bot: depth data populated by main loop (60s), read by live writer thread (5s)
- **`_l2_live_writer_loop`** daemon thread: writes `l2_snapshot.json` every 5s

### Files touched
- `bot.py` — +200 lines (strategy router, flow passing, threading, L2 cache)
- `strategies.py` — +160 lines (htf_l2_anticipation function, STRATEGIES dict entry)
- `web_dashboard.py` — +130 lines (L2 panel + -18 lines for duplicate Reconcile removal)
- `l2_snapshot.json` — new runtime file, 8 symbols, ~2 KB
- `docs/superpowers/specs/` — 3 new spec docs
- `docs/superpowers/plans/` — 3 new plan docs

---

## Outstanding follow-ups (carried forward)

- **`.env` tracked in git** — `git rm --cached .env` needed (Jonas's call, keys rotated 04-13)
- **backfill_fees.py** — hardcoded paths, not committed
- **Phase 2a (fee reduction)** — still unblocked, not started
- **Scanner vol_rank tuning** — BTC dominates, may need log normalization after more data
- **Fee data in trading_state.json** — `fee_usdt` field is 0 for all trades (pre-existing issue)
- **L2 anticipation tuning** — hardcoded thresholds (0.55/0.45, ±0.1, 1.2x/0.83x). Promote to config after 50 trades.
- **Dashboard Sessions + Charts panels** — flagged as low-value in audit, left for now. Revisit after 2 weeks.

---

## Active monitoring (carried forward)
- `[L2_LIVE]` log lines — new, thread health
- `[RATE WATCH]` log lines — since Apr 16, cap removed
- `[TAPE GATE SOFT]` log lines — since Apr 16
- `[DIVERGENCE COOLDOWN]` log lines — since Apr 16
- `[TIMEOUT]` log entries (DNS wrap from 04-10)
- Maker fill rate (postOnly fix from 04-09)
- Orphan-position 3-layer defense (live since 04-13)
- Overwatch hourly health checks
- Reconcile every 15min
