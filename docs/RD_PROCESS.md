# Phmex-S — Continuous R&D Process

## The Pipeline

Every strategy goes through these stages:

```
HYPOTHESIS → BACKTEST → PAPER → VALIDATE → LIVE → MONITOR → KILL/EVOLVE
```

## Current State (Sentinel v11 — 2026-04-02)

| Stage | Strategies |
|-------|-----------|
| **Live** | confluence (htf_confluence_pullback) — Sentinel gates |
| **Paper (gated)** | liq_cascade, bb_reversion (mean revert), htf_momentum |
| **Paper (control)** | legacy_control (ungated Pipeline replica for A/B) |
| **Killed** | ATR Gate, V10 Control, SMA+VWAP, 8H Funding |

## Weekly Cadence

### Monday: Performance Review
1. Run daily report: `python scripts/daily_report.py`
2. Compare live vs legacy_control (Sentinel A/B)
3. Check each paper slot's WR, PnL, AE rate
4. Flag any slot approaching kill thresholds
5. Review edge decay (compare last 7d vs all-time)

### Wednesday: Strategy Pipeline Check
1. Are paper strategies collecting enough trades? (need 50+ for validation)
2. Any paper strategy ready for promotion?
3. Is the idea pipeline dry? Brainstorm new hypotheses
4. Check gate effectiveness — are [TAPE GATE]/[OB GATE]/[RATE GATE] logs showing expected blocks?

### Friday: R&D Session
1. Research new edges (deploy research agents)
2. Review killed strategies — is the kill reason still valid?
3. Backtest promising ideas if tools available
4. Save findings to memory/reference_*.md

### Monthly: Recalibration
1. Walk-forward optimization on live strategy parameters
2. Kill any strategy with negative Kelly after 50+ trades
3. Promote any paper strategy that passes validation
4. Review and tighten/loosen gate thresholds based on data
5. Update memory files with findings

## How to Test a New Idea
1. Write the strategy function in strategies.py (follow existing pattern)
2. Add as paper slot in bot.py (StrategySlot with paper_mode=True)
3. Collect 50+ paper trades
4. Compare against live and legacy_control
5. If Kelly > 0 and WR > 40%: promote to live
6. Save research to memory/reference_*.md

## Kill Criteria
- Negative Kelly after 50+ trades → auto-kill
- WR < 30% after 25+ trades → auto-kill
- WR declining 3 consecutive months → flag for review
- Edge decay > 30% (recent WR vs historical) → investigate

## Top 1% Benchmarks

| Metric | Target | Current (Pipeline baseline) |
|--------|--------|-----------------------------|
| AE rate | < 30% | ~50% (Sentinel targeting <30%) |
| Win rate (live) | > 45% | 35-64% (varies by day) |
| Monthly return | 3-5% | Negative (drawdown recovery) |
| Max drawdown | < 15% | 14.6% (at limit) |
| Paper strategies | 1+ always | 3 gated + 1 control |
| Live strategies | 1-3 | 1 live |

## Sources of Edge (Research-Backed)
1. **Weekend effect** — implemented (weekend boost)
2. **Candle boundary** — implemented (skip last 2 min)
3. **Liquidation cascades** — paper slot active (liq_cascade)
4. **Time-of-day filtering** — implemented (blocked hours)
5. **L2 orderbook gating** — implemented (Sentinel)
6. **Tape/flow gating** — implemented (Sentinel)
7. **VPIN regime filter** — unexplored
8. **Cross-timeframe momentum** — paper slot active (1h_momentum)
9. **Correlation breakdowns** — unexplored (BTC/ETH divergence)
10. **Volume profile anomalies** — unexplored
11. **Mean reversion** — paper slot active (bb_reversion)

## Key Commands

```bash
# Bot
python main.py >> logs/bot.log 2>&1 &     # Start bot
python scripts/daily_report.py             # Generate daily report

# Dashboard
python web_dashboard.py                    # Web dashboard (localhost:8050)
python war_room.py                         # Terminal dashboard

# Analysis
python recalibration.py                    # Performance report
python recalibration.py --days 7           # Last 7 days only

# Data
python fetch_history.py 30                 # Fetch 30 days of OHLCV data
```

## Memory References
- `memory/reference_bot_architecture.md` — Current bot structure (Sentinel)
- `memory/reference_existing_infrastructure.md` — L2/tape systems and gate status
- `memory/reference_performance_baseline.md` — Pipeline week baseline for comparison
- `memory/reference_sentinel.md` — Sentinel deployment details and evaluation plan
- `memory/lessons.md` — META-RULES and operational lessons
