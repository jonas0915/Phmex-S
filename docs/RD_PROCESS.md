# Phmex-S — Continuous R&D Process

## The Pipeline

Every strategy goes through these stages:

```
HYPOTHESIS → BACKTEST → PAPER → VALIDATE → LIVE → MONITOR → KILL/EVOLVE
```

## Weekly Cadence

### Monday: Performance Review
1. Run recalibration report: `python recalibration.py`
2. Check each slot's Kelly, WR, PnL
3. Flag any slot approaching kill thresholds
4. Review edge decay (compare last 7d vs all-time)

### Wednesday: Strategy Pipeline Check
1. Run factory report: `python strategy_factory.py report`
2. Are there strategies in paper mode? Check their progress
3. Any paper strategies ready for validation? `python strategy_factory.py validate <name>`
4. Is the idea pipeline dry? Brainstorm new hypotheses

### Friday: R&D Session
1. Research new edges (deploy research agents)
2. Register new hypotheses: `python strategy_factory.py register <name> <hypothesis>`
3. Backtest promising ideas: `python backtester.py --strategy <name>`
4. Review killed strategies — is the kill reason still valid?

### Monthly: Recalibration
1. Full recalibration: `python recalibration.py`
2. Walk-forward optimization on all live strategies
3. Update parameters if OOS Sharpe > IS Sharpe × 0.7
4. Kill any strategy with negative Kelly after 50+ trades
5. Promote any paper strategy that passes validation
6. Save findings to memory

## How to Generate New Strategy Ideas

### Sources of Edge (Research-Backed)
1. **Weekend effect** — already implemented (1.3x weekend boost)
2. **Candle boundary** — already implemented (skip last 2 min)
3. **Liquidation cascades** — Slot 4 in paper mode
4. **Funding rate extremes** — Slot 5 in paper mode
5. **Time-of-day volatility** — trade only during EU/US overlap (14:00-21:00 UTC)
6. **VPIN regime filter** — detect informed flow, stand aside
7. **Cross-timeframe momentum** — 4h trend + 5m entry
8. **Correlation breakdowns** — BTC/ETH correlation divergence
9. **Volume profile anomalies** — unusual volume at specific price levels
10. **On-chain signals** — whale movements, exchange flows

### How to Test a New Idea
1. Register: `python strategy_factory.py register <name> "<hypothesis>"`
2. Write the strategy function in strategies.py (follow existing pattern)
3. Backtest: `python backtester.py --strategy <name> --days 30`
4. If Kelly > 0 and WR > 40%: add as paper slot in bot.py
5. Collect 50+ paper trades
6. Validate: `python strategy_factory.py validate <name>`
7. If passes: `python strategy_factory.py promote <name>`

### Kill Criteria
- Negative Kelly after 50+ trades → auto-kill
- WR < 30% after 25+ trades → auto-kill
- WR declining 3 consecutive months → flag for review
- Edge decay > 30% (recent WR vs historical) → investigate

## Key Commands

```bash
# Performance
python recalibration.py                    # Full performance report
python recalibration.py --days 7           # Last 7 days only
python recalibration.py --slot <name>      # Specific slot

# Factory
python strategy_factory.py list            # All strategies by stage
python strategy_factory.py report          # Pipeline health check
python strategy_factory.py register <name> <hypothesis>
python strategy_factory.py test <name>     # Start backtest
python strategy_factory.py validate <name> # Check promotion criteria
python strategy_factory.py promote <name>  # Move to live
python strategy_factory.py kill <name> <reason>

# Backtesting
python fetch_history.py 30                 # Fetch 30 days of data
python backtester.py --strategy <name>     # Run backtest
python backtester.py --wfo                 # Walk-forward optimization

# Bot
python tracker_update.py status            # Project tracker
```

## Top 1% Benchmarks

| Metric | Target | Current |
|--------|--------|---------|
| Portfolio Sharpe | > 1.0 | TBD |
| Kelly (2+ slots) | Positive | TBD |
| Monthly recalibration | Running | Built |
| Paper strategies testing | 1+ always | 4 in paper |
| Live strategies | 3-5 | 1 live |
| Monthly return | 3-5% | TBD |
| Max drawdown | < 15% | TBD |
| Win rate (combined) | > 45% | 35.9% (v8 baseline) |

## Research Memory Files
- `memory/reference_deep_research_mar21.md` — Full R&D findings
- `memory/reference_trading_research.md` — Hedge fund benchmarks
- `memory/project_v10_pipeline.md` — Build progress
