# Phmex-S v10.0 "Pipeline" — Multi-Strategy Architecture Design

**Author:** Claude + Jonas
**Date:** March 21, 2026
**Status:** Approved
**Goal:** Evolve Phmex-S from a single-strategy scalping bot into a multi-strategy pipeline to reach top 1% of automated crypto traders.

---

## Context

### Where We Are
- 9 versions in 9 days, $51 → $20.61 (-60%)
- Win rate 35.9% — below 36.6% breakeven threshold
- Only profitable mechanism: early_exit (18 trades, 100% WR, +$16.68)
- #1 loss source: time_exit (105 trades, -$37.88)
- Kelly criterion: negative (-0.21)
- Account will be funded to $100-200 for multi-strategy operation

### What Research Tells Us
- 5m timeframe: overwhelmingly negative Sharpes in walk-forward studies
- 60m+: the only consistently positive Sharpe timeframe (WFO studies)
- Top 1% run 50+ strategies simultaneously (Kevin Davey), treat each as disposable
- Weekend effect: +85-148% crypto returns (p < 0.001, 1,672 trading days)
- Candle boundary: +0.58bps at min 0/15/30/45 (t-stat > 9, 7 exchanges)
- Tight time exits destroy performance (567K backtests, KJ Trading Systems)
- Mean reversion works at 5m ONLY in ranging conditions (ADX<25, Hurst<0.50)
- Monthly walk-forward recalibration is mandatory (fixed params cost -1.07 Sharpe)
- Adverse exit at -0.3% price is noise for ETH/SOL — need -0.5% minimum

### Approach
Evolve Phmex-S (Approach 1). Keep battle-tested infrastructure (exchange, WS, connectivity, dashboard), replace strategy layer with independent slots. Ship incrementally — Phase 1 fixes tonight, new slots added one at a time.

---

## Section 1: Strategy Slots Architecture

The bot evolves from "one strategy picks a signal" to "multiple independent strategies run in parallel, each with its own positions and P&L."

### Current Flow
```
Loop → All pairs → One strategy (confluence) → Signal → Enter/Exit
```

### New Flow
```
Loop → For each Strategy Slot:
         → Slot's pairs → Slot's strategy → Slot's signal → Slot's positions
         → Independent P&L tracking per slot
```

### Slot Definition

Each slot has:
- Its own strategy function
- Its own timeframe (5m, 1h, 4h)
- Its own pair list (can overlap — different timeframes won't conflict)
- Its own max positions (e.g., 1-2 per slot)
- Its own capital allocation (e.g., $50 per slot)
- Its own exit rules (SL, TP, adverse exit thresholds)
- Its own P&L in trading_state.json (separate closed_trades per slot)
- A kill switch: if negative Kelly after N trades, auto-disable

### Global Constraints (Shared)
- Total max positions across all slots (e.g., 4)
- Total max margin usage (e.g., 80% of balance)
- Minimum 30% capital reserve (always uninvested)
- Drawdown halt applies globally
- Single exchange connection (shared ccxt client for main loop, dedicated for background tasks)
- **All slots execute sequentially within the main loop — never threaded.** This avoids ccxt concurrency issues (ccxt is NOT thread-safe).

### Position Conflict Rules
Phemex has ONE position per symbol per account (not per strategy). Two slots CANNOT hold opposing positions on the same symbol. Rules:
- **Position lock per symbol:** Before entering, check if ANY other slot holds a position on the same symbol. If yes, skip entry.
- **Same-direction allowed:** Two slots CAN hold the same direction on the same symbol (they combine on exchange but are tracked separately internally).
- **Opposing direction blocked:** If Slot 1 is long SOL and Slot 2 wants to short SOL, Slot 2 waits. No cross-slot position flipping.

### Planned Slots (Incremental Rollout)

| Slot | Strategy | Timeframe | Research Basis | Phase |
|------|----------|-----------|----------------|-------|
| 1 | Fixed 5m scalp (research-corrected) | 5m | Existing + proven edge fixes | Phase 1 |
| 2 | 1h momentum | 1h | WFO: only consistently positive Sharpe TF | Phase 2 |
| 3 | Mean reversion (BB + VWAP, ranging only) | 5m | Works at 2-30 min with regime gate | Phase 3 |
| 4 | Liquidation cascade | 5m/1h | Structural edge, CoinGlass data | Phase 4 |
| 5 | Funding rate contrarian | 8h | 19.26% annualized, proven mechanism | Phase 4 |

---

## Section 2: Phase 1 — Fix Current Bot

Before building new slots, fix what research proved wrong in v9.0.

### Changes

| Change | Current | New | Research Source |
|--------|---------|-----|----------------|
| Adverse exit threshold | -3% ROI | -5% ROI | -0.3% price is noise for ETH/SOL; pros use 0.5-0.8% price |
| Soft time exits | 10-30 cycles | Remove entirely | 567K study: tight time exits destroy performance |
| Weekend sizing | None | 1.3x Kelly multiplier Sat/Sun (capped at $10) | +85-92% return differential per asset, p < 0.001 |
| Candle-boundary bias | None | Prefer entries at candle opens | +0.58bps at boundaries, t-stat > 9 |
| bb_mean_reversion | Disabled | Re-enable with ADX<25 + Hurst<0.50 | Mean reversion strongest at 2-30 min in ranging |
| Tiered trailing stop | Fixed 0.7R trail | Progressive tightening by ROI tier | FMZ Quant tiered system, AdaptiveTrend study |

### Exit System After Changes

**Priority order (checked in this sequence each cycle):**

| Priority | Exit | Trigger | Purpose |
|----------|------|---------|---------|
| 1 | Early exit | 3%+ ROI + momentum reversal | Primary profit engine |
| 2 | Tiered trailing stop | Lock-in floor breached | Protect winners |
| 3 | Breakeven stop | Price below entry + 0.25% after 1R reached | Lock in zero-loss |
| 4 | Adverse exit | -5% ROI after 10 min | Cut wrong-direction trades |
| 5 | Flat exit | 4h, [-4%, +4%) ROI | Catch stagnant positions |
| 6 | Hard time exit | 4h, ROI outside flat range (>= +4% or < -4%) | Emergency backstop for outliers flat exit missed |
| 7 | SL | 1.2% price (-12% ROI) hit on exchange | Hard downside cap (exchange-side conditional order) |
| 8 | TP | 2.1% price (+21% ROI) hit on exchange | Backstop for runners (exchange-side conditional order) |

**Exit overlap clarification:**
- Flat exit (priority 5) catches trades at 4h with ROI in [-4%, +4%). These are the stagnant/weak trades.
- Hard time exit (priority 6) catches trades at 4h with ROI >= +4% or < -4%. These are the outliers where adverse exit didn't fire (e.g., trade was at -4.5% but only after 10 min mark, or trade drifted slowly to -4.5%).
- SL/TP (7-8) are exchange-side orders — they fire independently of the bot's polling loop. They are the catastrophic backstop.

**Adverse exit interaction with SL:**
- Adverse exit fires at -5% ROI after 10 min (catches wrong-direction trades early)
- SL fires at -12% ROI (1.2% price × 10x) — exchange-side, fires on flash crashes or gap moves
- The zone between -5% and -12% for trades older than 10 min: adverse exit already fired, so nothing should be in this zone unless the close order failed. The hard time exit at 4h catches any survivors.

**Note on tiered trailing stop vs 567K study:**
The 567K study found trailing stops produced 22% less profit than fixed TP for day trading. However, the AdaptiveTrend study (Sharpe 2.41) found removing their dynamic trailing stop dropped Sharpe by 0.73. Our tiered trailing is a hybrid (fixed floor + trail). Success metric: compare trades closed by tiered trailing vs those closed by early_exit after 50 trades. If tiered trailing produces lower avg profit than early_exit, simplify to early_exit only.

### Tiered Trailing Stop (Profit Protection)

| ROI Reached | Minimum Lock-In | Trail from Peak |
|-------------|----------------|-----------------|
| +5% | +2% | 3% from peak |
| +8% | +4% | 4% from peak |
| +10% | +6% | 4% from peak |
| +15% | +10% | 5% from peak |
| +20% | +15% | 5% from peak |

Lock-in is a hard floor that only ratchets up. Once +15% ROI hit, cannot close below +10%. The principle: never give back more than 1/3 of peak profit.

### What Stays Unchanged
- SL 1.2%, TP 2.1% (research-validated)
- Early exit logic (only profitable mechanism)
- Ensemble confidence gate (research supports ensembles)
- PostOnly maker orders (biggest structural edge: 0.01% vs 0.06%)
- Breakeven stop at 1R (ranked 3rd in 567K study)

---

## Section 3: Phase 2 — 1h Momentum Strategy (Slot 2)

### Entry Conditions (4 core, keeping it simple to avoid over-fitting)
1. **ADX > 25 on 1h** (confirmed trend — filters chop)
2. **EMA-21 > EMA-50** for longs (< for shorts) — trend direction
3. **MACD histogram expanding** — momentum accelerating
4. **Pullback to EMA-21** — entry on dip, not chase

Optional boosters (increase confidence/size, but not required for entry):
- Volume > 1.2x average → +0.05 strength
- Ensemble confidence 3+/6 → full size (2 or fewer → half size)

**Expected signal frequency:** ~2-5 signals per week across 5 pairs. 1h trends are less frequent than 5m signals. Kill switch at 50 trades will take ~3-6 weeks to evaluate. This is acceptable — 1h strategies trade less but win bigger.

### Exit Rules (Independent from 5m Slot)
- SL: 2.0% price (-20% ROI at 10x)
- TP: 4.0% price (+40% ROI at 10x)
- Adverse exit: -8% ROI after 3 candles (3h)
- Tiered trailing stop: same structure as Phase 1
- Early exit: momentum reversal at +5% ROI
- Hard time exit: 24h
- No soft time exits

### Position Sizing
- Separate capital allocation from 5m slot
- Kelly-based within its own allocation
- $2 floor, cap based on allocation

### Pairs
Same dynamic scanner (top 5 by volume). Different timeframe means different signals — a pair can have a 5m scalp AND a 1h momentum trade simultaneously.

### Research Basis
- AdaptiveTrend study: 1h momentum + dynamic trailing = Sharpe 2.41
- Feature importance: NATR, momentum, MACD consistently top-8 predictors
- Rob Carver: momentum dominates at 1h+ horizons
- WFO studies: 60m was ONLY consistently positive Sharpe timeframe

---

## Section 4: Phase 3-4 — Recalibration & Strategy Pipeline

### Monthly Recalibration Process

Every 30 days (or 100 trades, whichever first):

1. **Per-slot performance report** — WR, PnL, Kelly, Sharpe, max DD per slot. Flag negative Kelly slots.
2. **Parameter walk-forward** — Re-optimize SL/TP/adverse using last 30 days. Only update if out-of-sample Sharpe > in-sample × 0.7.
3. **Kill switch evaluation** — Negative Kelly after 50+ trades → auto-disable. WR declining 3 months → flag.
4. **Edge decay check** — Compare signal hit rate vs first month. >30% drop → investigate or kill.

### Strategy Factory (Ongoing)

Process for generating new strategy candidates:

1. **Hypothesis** — e.g., "Liquidation clusters predict 1h moves"
2. **Backtest** — Run on historical data
3. **Paper trade** — Run in a slot with $0 real capital
4. **Validate** — Positive Kelly after 50+ paper trades → promote
5. **Deploy** — Assign capital, set kill switch
6. **Monitor** — Monthly recalibration catches decay

### New Files
- `recalibration.py` — monthly report + walk-forward + kill switch
- `paper_mode` flag per strategy slot
- `strategy_factory/` directory — templates for new candidates
- Dashboard: per-slot P&L cards, kill switch status, recalibration countdown

---

## Section 5: Implementation Timeline

| Phase | What | When | Success Gate |
|-------|------|------|-------------|
| 1 | Fix v9.0 (6 changes + tiered trailing) | Tonight/Tomorrow | Compiles, bot running |
| 2a | Refactor for strategy slots | Days 2-3 | Slot framework working |
| 2b | Build backtester + WFO framework | Days 3-5 | Can backtest any slot's strategy on historical data |
| 2c | 1h momentum (Slot 2) | Days 5-7 | Backtested first, then live |
| 2d | Proven edges (weekend, candle-boundary) | Day 7 | Integrated all slots |
| 3a | bb_mean_reversion (Slot 3) | Week 2 | Paper mode, then live |
| 3b | recalibration.py (uses backtester from 2b) | Week 2 | Monthly reports generating, WFO working |
| 4 | Liquidation + Funding rate (Slots 4-5) | Week 3-4 | Paper mode, validate |
| 5 | Strategy factory pipeline | Week 4+ | Ongoing |

### Account Funding
- Fund to $100-200 before Phase 2c goes live
- $50 per slot for first 2 slots, minimum 30% reserve (uninvested)
- Positive Kelly after 50 trades → increase allocation

### Rollback Plan
Before each phase:
1. **Git tag** the current working state (e.g., `git tag v9.0-pre-phase1`)
2. **Archive trading_state.json** (e.g., `trading_state_pre_phase1.json`)
3. **Revert criteria:** If WR drops below 30% at 25 trades after any phase change, revert to the previous tag
4. **How to revert:** `git checkout <tag>`, restore archived state file, restart bot. New slot framework code lives on a feature branch until validated — revert doesn't lose it.

### Milestones

| Milestone | Metric | Target | Kill Trigger |
|-----------|--------|--------|-------------|
| 25 trades (Slot 1) | WR, adverse exit rate | WR > 40% | WR < 30% |
| 25 trades (Slot 2) | WR, avg win | WR > 45%, win > 2x loss | WR < 35% |
| 50 trades (combined) | Kelly per slot | 1+ slot positive | Both negative |
| 100 trades (combined) | Portfolio Sharpe | > 0.5 | < 0 |
| 200 trades (combined) | Consistency | 60%+ green days | < 40% |

### Top 1% Target
- Portfolio Sharpe > 1.0
- Kelly positive on 2+ slots
- Monthly recalibration running
- 1+ new strategy candidate in paper testing always
- WR > 45% combined
- 3-5% monthly return, <15% max drawdown
- ~36-60% annualized

---

## Research References

All findings sourced from deep R&D sessions (Mar 20-21, 2026):
- `memory/reference_trading_research.md` — Hedge fund benchmarks, microstructure
- `memory/reference_deep_research_mar21.md` — MAE, time exits, mean reversion, top 1% traits, proven edges, position sizing
- 567K backtests study (KJ Trading Systems)
- Taiwan day trading study (Barber/Odean, 450K traders)
- AdaptiveTrend (Sharpe 2.41, arxiv)
- Weekend effect (1,672 trading days, p < 0.001)
- Candle boundary effect (t-stat > 9, 7 exchanges)
- Walk-forward optimization studies (81 configurations)
