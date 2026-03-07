# DegenCryt - Active Crypto Trading Bot

An active cryptocurrency trading bot with multiple strategies, risk management, and paper/live trading modes.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your settings

# Run in paper mode (safe, simulated)
python main.py --mode paper

# Run in live mode
python main.py --mode live
```

## CLI Options

```
python main.py [--mode paper|live] [--strategy momentum|mean_reversion|breakout|combined]
               [--pairs BTC/USDT,ETH/USDT] [--timeframe 15m]
```

## Strategies

| Strategy | Description |
|---|---|
| `momentum` | EMA crossovers + RSI + MACD |
| `mean_reversion` | Bollinger Bands + Stochastic |
| `breakout` | Price/volume breakouts |
| `combined` | Majority vote across all 3 (recommended) |

## Risk Management

- Per-trade position sizing (% of balance)
- Stop loss & take profit on every trade
- Optional trailing stop
- Max open trades limit
- Max drawdown circuit breaker

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `EXCHANGE` | `binance` | Exchange name (ccxt compatible) |
| `TRADING_PAIRS` | `BTC/USDT,ETH/USDT` | Pairs to trade |
| `TIMEFRAME` | `15m` | Candle timeframe |
| `STRATEGY` | `combined` | Trading strategy |
| `TRADE_AMOUNT_PERCENT` | `2.0` | % of balance per trade |
| `MAX_OPEN_TRADES` | `3` | Max simultaneous positions |
| `STOP_LOSS_PERCENT` | `2.0` | Stop loss % |
| `TAKE_PROFIT_PERCENT` | `4.0` | Take profit % |
| `TRAILING_STOP` | `true` | Enable trailing stop |
| `MODE` | `paper` | `paper` or `live` |

## Disclaimer

This bot is for educational purposes. Crypto trading involves substantial risk. Never trade more than you can afford to lose.
