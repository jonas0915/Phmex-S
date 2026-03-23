#!/usr/bin/env python3
"""
Backtester for Phmex-S strategies.
Replays historical candles through strategy functions and simulates trading.

Usage:
    python backtester.py                          # Run with defaults
    python backtester.py --strategy confluence     # Specific strategy
    python backtester.py --pair BTC/USDT:USDT     # Specific pair
    python backtester.py --days 14                 # Last 14 days
    python backtester.py --wfo                     # Walk-forward optimization
"""
import argparse
import json
import os
import sys
import pandas as pd
import numpy as np
from collections import defaultdict
from dataclasses import dataclass, field
from indicators import add_all_indicators
from strategies import STRATEGIES, Signal, TradeSignal
from config import Config

@dataclass
class BacktestPosition:
    symbol: str
    side: str
    entry_price: float
    amount: float
    margin: float
    stop_loss: float
    take_profit: float
    entry_bar: int
    strategy: str
    peak_price: float = 0.0
    trailing_stop: float = 0.0

    def pnl_pct(self, price):
        if self.side == "long":
            return (price - self.entry_price) / self.entry_price * 100 * Config.LEVERAGE
        else:
            return (self.entry_price - price) / self.entry_price * 100 * Config.LEVERAGE

    def pnl_usdt(self, price):
        return self.pnl_pct(price) / 100 * self.margin


@dataclass
class BacktestResult:
    trades: list = field(default_factory=list)

    def summary(self):
        if not self.trades:
            return {"trades": 0, "wr": 0, "pnl": 0, "kelly": 0}
        wins = [t for t in self.trades if t["pnl_usdt"] > 0]
        losses = [t for t in self.trades if t["pnl_usdt"] <= 0]
        pnl = sum(t["pnl_usdt"] for t in self.trades)
        wr = len(wins) / len(self.trades) * 100

        # Kelly
        if wins and losses:
            avg_win = sum(t["pnl_usdt"] for t in wins) / len(wins)
            avg_loss = abs(sum(t["pnl_usdt"] for t in losses) / len(losses))
            kelly = (wr/100 * avg_win - (1-wr/100) * avg_loss) / avg_win if avg_win > 0 else 0
        else:
            kelly = 0
            avg_win = 0
            avg_loss = 0

        # Exit breakdown
        reasons = defaultdict(lambda: {"count": 0, "pnl": 0})
        for t in self.trades:
            reasons[t["reason"]]["count"] += 1
            reasons[t["reason"]]["pnl"] += t["pnl_usdt"]

        return {
            "trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "wr": round(wr, 1),
            "pnl": round(pnl, 2),
            "avg_win": round(avg_win, 2) if wins else 0,
            "avg_loss": round(avg_loss, 2) if losses else 0,
            "kelly": round(kelly, 3),
            "exits": {k: dict(v) for k, v in sorted(reasons.items(), key=lambda x: x[1]["pnl"])},
        }


def load_data(pair, timeframe, days=None):
    """Load historical data from CSV."""
    safe_name = pair.replace("/", "_").replace(":", "_")
    path = f"backtest_data/{safe_name}_{timeframe}.csv"
    if not os.path.exists(path):
        print(f"No data file: {path}. Run fetch_history.py first.")
        sys.exit(1)
    df = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
    if days:
        cutoff = df.index.max() - pd.Timedelta(days=days)
        df = df[df.index >= cutoff]
    df = df.reset_index()
    df.index = pd.to_datetime(df["timestamp"])
    return df


def run_backtest(pair, strategy_name="confluence", timeframe="5m", days=None,
                 margin_per_trade=8.0, sl_pct=1.2, tp_pct=2.1, adverse_threshold=-5.0,
                 adverse_cycles=10):
    """Run backtest on historical data."""
    df_raw = load_data(pair, timeframe, days)
    if len(df_raw) < 100:
        print(f"Not enough data for {pair} ({len(df_raw)} candles)")
        return BacktestResult()

    df = add_all_indicators(df_raw)
    if df is None or len(df) < 50:
        print(f"Not enough data after indicators for {pair}")
        return BacktestResult()

    strategy_fn = STRATEGIES.get(strategy_name, STRATEGIES["confluence"])
    result = BacktestResult()
    position = None
    leverage = Config.LEVERAGE

    # Also load 1h data for HTF if available
    htf_df = None
    try:
        htf_raw = load_data(pair, "1h", days)
        htf_df = add_all_indicators(htf_raw)
    except:
        pass

    for i in range(50, len(df)):  # start after indicator warmup
        bar = df.iloc[i]
        price = bar["close"]
        high = bar["high"]
        low = bar["low"]

        # ── EXIT CHECKS ──
        if position is not None:
            bars_held = i - position.entry_bar
            roi = position.pnl_pct(price)

            # SL hit (check against low/high of candle)
            if position.side == "long" and low <= position.stop_loss:
                exit_price = position.stop_loss
                result.trades.append({
                    "symbol": pair, "side": position.side,
                    "entry": position.entry_price, "exit": exit_price,
                    "margin": position.margin,
                    "pnl_usdt": position.pnl_usdt(exit_price),
                    "pnl_pct": position.pnl_pct(exit_price),
                    "reason": "stop_loss", "strategy": position.strategy,
                    "bars_held": bars_held,
                })
                position = None
                continue
            elif position.side == "short" and high >= position.stop_loss:
                exit_price = position.stop_loss
                result.trades.append({
                    "symbol": pair, "side": position.side,
                    "entry": position.entry_price, "exit": exit_price,
                    "margin": position.margin,
                    "pnl_usdt": position.pnl_usdt(exit_price),
                    "pnl_pct": position.pnl_pct(exit_price),
                    "reason": "stop_loss", "strategy": position.strategy,
                    "bars_held": bars_held,
                })
                position = None
                continue

            # TP hit
            if position.side == "long" and high >= position.take_profit:
                exit_price = position.take_profit
                result.trades.append({
                    "symbol": pair, "side": position.side,
                    "entry": position.entry_price, "exit": exit_price,
                    "margin": position.margin,
                    "pnl_usdt": position.pnl_usdt(exit_price),
                    "pnl_pct": position.pnl_pct(exit_price),
                    "reason": "take_profit", "strategy": position.strategy,
                    "bars_held": bars_held,
                })
                position = None
                continue
            elif position.side == "short" and low <= position.take_profit:
                exit_price = position.take_profit
                result.trades.append({
                    "symbol": pair, "side": position.side,
                    "entry": position.entry_price, "exit": exit_price,
                    "margin": position.margin,
                    "pnl_usdt": position.pnl_usdt(exit_price),
                    "pnl_pct": position.pnl_pct(exit_price),
                    "reason": "take_profit", "strategy": position.strategy,
                    "bars_held": bars_held,
                })
                position = None
                continue

            # Adverse exit: wrong direction after N bars
            if bars_held >= adverse_cycles and roi <= adverse_threshold:
                result.trades.append({
                    "symbol": pair, "side": position.side,
                    "entry": position.entry_price, "exit": price,
                    "margin": position.margin,
                    "pnl_usdt": position.pnl_usdt(price),
                    "pnl_pct": roi,
                    "reason": "adverse_exit", "strategy": position.strategy,
                    "bars_held": bars_held,
                })
                position = None
                continue

            # Tiered trailing stop check
            if roi >= 5.0:
                tiers = [(20,15,5),(15,10,5),(10,6,4),(8,4,4),(5,2,3)]
                lock_pct, trail_pct = 2.0, 3.0
                for threshold, lock, trail in tiers:
                    if roi >= threshold:
                        lock_pct, trail_pct = lock, trail
                        break

                if position.side == "long":
                    if price > position.peak_price:
                        position.peak_price = price
                    trail_price = position.peak_price * (1 - trail_pct / 100 / leverage)
                    lock_price = position.entry_price * (1 + lock_pct / 100 / leverage)
                    stop = max(trail_price, lock_price)
                    if low <= stop:
                        result.trades.append({
                            "symbol": pair, "side": position.side,
                            "entry": position.entry_price, "exit": stop,
                            "margin": position.margin,
                            "pnl_usdt": position.pnl_usdt(stop),
                            "pnl_pct": position.pnl_pct(stop),
                            "reason": "trailing_stop", "strategy": position.strategy,
                            "bars_held": bars_held,
                        })
                        position = None
                        continue
                else:  # short
                    if price < position.peak_price or position.peak_price == 0:
                        position.peak_price = price
                    trail_price = position.peak_price * (1 + trail_pct / 100 / leverage)
                    lock_price = position.entry_price * (1 - lock_pct / 100 / leverage)
                    stop = min(trail_price, lock_price)
                    if high >= stop:
                        result.trades.append({
                            "symbol": pair, "side": position.side,
                            "entry": position.entry_price, "exit": stop,
                            "margin": position.margin,
                            "pnl_usdt": position.pnl_usdt(stop),
                            "pnl_pct": position.pnl_pct(stop),
                            "reason": "trailing_stop", "strategy": position.strategy,
                            "bars_held": bars_held,
                        })
                        position = None
                        continue

            # Hard time exit: 240 bars (4h for 5m, 10 days for 1h)
            hard_limit = 240 if timeframe == "5m" else 24  # 24h for 1h
            if bars_held >= hard_limit:
                if roi >= 5.0 and bars_held < int(hard_limit * 1.5):
                    pass  # extend
                else:
                    result.trades.append({
                        "symbol": pair, "side": position.side,
                        "entry": position.entry_price, "exit": price,
                        "margin": position.margin,
                        "pnl_usdt": position.pnl_usdt(price),
                        "pnl_pct": roi,
                        "reason": "hard_time_exit", "strategy": position.strategy,
                        "bars_held": bars_held,
                    })
                    position = None
                    continue

        # ── ENTRY CHECKS ──
        if position is not None:
            continue  # already in a trade

        # Need enough lookback for strategy
        window = df.iloc[max(0, i-50):i+1]
        if len(window) < 50:
            continue

        # Get HTF context
        htf_window = None
        if htf_df is not None and len(htf_df) > 0:
            # Find matching 1h bar
            bar_time = bar["timestamp"] if "timestamp" in df.columns else bar.name
            if hasattr(bar_time, 'timestamp'):
                pass
            htf_window = htf_df  # pass full HTF — strategy will use last row

        # Call strategy
        try:
            signal = strategy_fn(window, None, htf_df=htf_window)
        except TypeError:
            try:
                signal = strategy_fn(window, None)
            except:
                continue
        except:
            continue

        if signal.signal == Signal.HOLD:
            continue
        if signal.strength < 0.75:  # min strength
            continue

        # Calculate SL/TP
        direction = "long" if signal.signal == Signal.BUY else "short"
        entry_price = price

        if direction == "long":
            sl = entry_price * (1 - sl_pct / 100)
            tp = entry_price * (1 + tp_pct / 100)
        else:
            sl = entry_price * (1 + sl_pct / 100)
            tp = entry_price * (1 - tp_pct / 100)

        position = BacktestPosition(
            symbol=pair,
            side=direction,
            entry_price=entry_price,
            amount=margin_per_trade * leverage / entry_price,
            margin=margin_per_trade,
            stop_loss=sl,
            take_profit=tp,
            entry_bar=i,
            strategy=strategy_name,
            peak_price=entry_price,
        )

    # Close any remaining position at last price
    if position is not None:
        price = df.iloc[-1]["close"]
        result.trades.append({
            "symbol": pair, "side": position.side,
            "entry": position.entry_price, "exit": price,
            "margin": position.margin,
            "pnl_usdt": position.pnl_usdt(price),
            "pnl_pct": position.pnl_pct(price),
            "reason": "end_of_data", "strategy": position.strategy,
            "bars_held": len(df) - 1 - position.entry_bar,
        })

    return result


def run_wfo(pair, strategy_name="confluence", timeframe="5m", train_days=21, test_days=7):
    """Walk-forward optimization: train on train_days, test on test_days."""
    print(f"\n{'='*60}")
    print(f"Walk-Forward: {pair} | {strategy_name} | {timeframe}")
    print(f"Train: {train_days} days | Test: {test_days} days")
    print(f"{'='*60}")

    # Run on train period
    train_result = run_backtest(pair, strategy_name, timeframe, days=train_days+test_days)
    if not train_result.trades:
        print("No trades in train period")
        return

    # Split results (rough: by trade index proportional to time)
    split = int(len(train_result.trades) * train_days / (train_days + test_days))
    train_trades = train_result.trades[:split]
    test_trades = train_result.trades[split:]

    train_r = BacktestResult(trades=train_trades)
    test_r = BacktestResult(trades=test_trades)

    print(f"\nTrain ({len(train_trades)} trades):")
    print_summary(train_r.summary())
    print(f"\nTest ({len(test_trades)} trades):")
    print_summary(test_r.summary())

    train_s = train_r.summary()
    test_s = test_r.summary()
    if train_s["kelly"] > 0 and test_s["kelly"] > 0:
        print(f"\n  PASS — Kelly positive in both train ({train_s['kelly']:.3f}) and test ({test_s['kelly']:.3f})")
    else:
        print(f"\n  FAIL — Kelly train={train_s['kelly']:.3f}, test={test_s['kelly']:.3f}")


def print_summary(s):
    print(f"  Trades: {s['trades']} | WR: {s['wr']}% | PnL: ${s['pnl']}")
    print(f"  Avg Win: ${s['avg_win']} | Avg Loss: ${s['avg_loss']} | Kelly: {s['kelly']}")
    if s.get("exits"):
        print(f"  Exits:")
        for reason, data in s["exits"].items():
            print(f"    {reason:20s}: {data['count']:3d} trades | ${data['pnl']:+.2f}")


def main():
    parser = argparse.ArgumentParser(description="Phmex-S Backtester")
    parser.add_argument("--strategy", default="confluence", help="Strategy name")
    parser.add_argument("--pair", default=None, help="Trading pair (default: all)")
    parser.add_argument("--timeframe", default="5m", help="Timeframe")
    parser.add_argument("--days", type=int, default=30, help="Days of data")
    parser.add_argument("--margin", type=float, default=8.0, help="Margin per trade")
    parser.add_argument("--sl", type=float, default=1.2, help="Stop loss pct")
    parser.add_argument("--tp", type=float, default=2.1, help="Take profit pct")
    parser.add_argument("--wfo", action="store_true", help="Run walk-forward optimization")
    args = parser.parse_args()

    pairs = [args.pair] if args.pair else [
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT"
    ]

    if args.wfo:
        for pair in pairs:
            run_wfo(pair, args.strategy, args.timeframe)
        return

    all_trades = []
    for pair in pairs:
        result = run_backtest(pair, args.strategy, args.timeframe, args.days,
                             args.margin, args.sl, args.tp)
        if result.trades:
            s = result.summary()
            print(f"\n{pair}: {s['trades']} trades | WR: {s['wr']}% | PnL: ${s['pnl']} | Kelly: {s['kelly']}")
            all_trades.extend(result.trades)

    if all_trades:
        combined = BacktestResult(trades=all_trades)
        s = combined.summary()
        print(f"\n{'='*60}")
        print(f"COMBINED: {s['trades']} trades across {len(pairs)} pairs")
        print(f"{'='*60}")
        print_summary(s)


if __name__ == "__main__":
    main()
