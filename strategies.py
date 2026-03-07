from dataclasses import dataclass
from enum import Enum
import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    signal: Signal
    reason: str
    strength: float  # 0.0 to 1.0


def momentum_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Momentum strategy using EMA crossovers + RSI + MACD.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    reasons = []
    buy_score = 0
    sell_score = 0
    total_weight = 0

    # EMA crossover (weight: 3)
    weight = 3
    total_weight += weight
    if last["ema_9"] > last["ema_21"] and prev["ema_9"] <= prev["ema_21"]:
        buy_score += weight
        reasons.append("EMA9 crossed above EMA21")
    elif last["ema_9"] < last["ema_21"] and prev["ema_9"] >= prev["ema_21"]:
        sell_score += weight
        reasons.append("EMA9 crossed below EMA21")

    # Trend filter (weight: 2)
    weight = 2
    total_weight += weight
    if last["ema_21"] > last["ema_50"]:
        buy_score += weight
    elif last["ema_21"] < last["ema_50"]:
        sell_score += weight

    # RSI (weight: 2)
    weight = 2
    total_weight += weight
    if 45 < last["rsi"] < 70:
        buy_score += weight
        reasons.append(f"RSI bullish ({last['rsi']:.1f})")
    elif 30 < last["rsi"] < 55:
        sell_score += weight
        reasons.append(f"RSI bearish ({last['rsi']:.1f})")

    # MACD histogram rising (weight: 2)
    weight = 2
    total_weight += weight
    if last["macd_hist"] > 0 and last["macd_hist"] > prev["macd_hist"]:
        buy_score += weight
        reasons.append("MACD bullish momentum")
    elif last["macd_hist"] < 0 and last["macd_hist"] < prev["macd_hist"]:
        sell_score += weight
        reasons.append("MACD bearish momentum")

    # Volume confirmation (weight: 1)
    weight = 1
    total_weight += weight
    if last["volume_ratio"] > 1.5:
        if buy_score > sell_score:
            buy_score += weight
        else:
            sell_score += weight
        reasons.append(f"High volume ({last['volume_ratio']:.1f}x)")

    buy_pct = buy_score / total_weight
    sell_pct = sell_score / total_weight
    threshold = 0.5

    if buy_pct >= threshold:
        return TradeSignal(Signal.BUY, " | ".join(reasons), buy_pct)
    elif sell_pct >= threshold:
        return TradeSignal(Signal.SELL, " | ".join(reasons), sell_pct)
    return TradeSignal(Signal.HOLD, "No clear signal", 0.0)


def mean_reversion_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Mean reversion using Bollinger Bands + RSI + Stochastic.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    reasons = []

    # Price near lower BB + RSI oversold
    bb_position = (last["close"] - last["bb_lower"]) / (last["bb_upper"] - last["bb_lower"])

    if (last["close"] <= last["bb_lower"] * 1.01 and
            last["rsi"] < 35 and
            last["stoch_k"] < 25 and
            last["stoch_k"] > last["stoch_d"]):
        reasons.append(f"Oversold: BB={bb_position:.2f}, RSI={last['rsi']:.1f}, Stoch={last['stoch_k']:.1f}")
        return TradeSignal(Signal.BUY, " | ".join(reasons), 0.75)

    if (last["close"] >= last["bb_upper"] * 0.99 and
            last["rsi"] > 65 and
            last["stoch_k"] > 75 and
            last["stoch_k"] < last["stoch_d"]):
        reasons.append(f"Overbought: BB={bb_position:.2f}, RSI={last['rsi']:.1f}, Stoch={last['stoch_k']:.1f}")
        return TradeSignal(Signal.SELL, " | ".join(reasons), 0.75)

    return TradeSignal(Signal.HOLD, "Price within normal range", 0.0)


def breakout_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Breakout strategy using recent high/low + volume + ATR.
    """
    lookback = 20
    last = df.iloc[-1]
    window = df.iloc[-lookback - 1:-1]

    recent_high = window["high"].max()
    recent_low = window["low"].min()

    # Breakout above recent high with volume
    if (last["close"] > recent_high and
            last["volume_ratio"] > 1.5 and
            last["atr"] > df["atr"].iloc[-lookback:].mean()):
        reason = f"Breakout above {recent_high:.4f} with {last['volume_ratio']:.1f}x volume"
        return TradeSignal(Signal.BUY, reason, 0.8)

    # Breakdown below recent low with volume
    if (last["close"] < recent_low and
            last["volume_ratio"] > 1.5 and
            last["atr"] > df["atr"].iloc[-lookback:].mean()):
        reason = f"Breakdown below {recent_low:.4f} with {last['volume_ratio']:.1f}x volume"
        return TradeSignal(Signal.SELL, reason, 0.8)

    return TradeSignal(Signal.HOLD, "No breakout detected", 0.0)


def combined_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Combine all strategies with voting. Requires 2 out of 3 to agree.
    """
    signals = [
        momentum_strategy(df),
        mean_reversion_strategy(df),
        breakout_strategy(df),
    ]

    buy_votes = sum(1 for s in signals if s.signal == Signal.BUY)
    sell_votes = sum(1 for s in signals if s.signal == Signal.SELL)

    buy_reasons = [s.reason for s in signals if s.signal == Signal.BUY]
    sell_reasons = [s.reason for s in signals if s.signal == Signal.SELL]

    if buy_votes >= 2:
        avg_strength = sum(s.strength for s in signals if s.signal == Signal.BUY) / buy_votes
        return TradeSignal(Signal.BUY, f"[{buy_votes}/3 strategies] " + " | ".join(buy_reasons), avg_strength)

    if sell_votes >= 2:
        avg_strength = sum(s.strength for s in signals if s.signal == Signal.SELL) / sell_votes
        return TradeSignal(Signal.SELL, f"[{sell_votes}/3 strategies] " + " | ".join(sell_reasons), avg_strength)

    return TradeSignal(Signal.HOLD, "No consensus between strategies", 0.0)


STRATEGIES = {
    "momentum": momentum_strategy,
    "mean_reversion": mean_reversion_strategy,
    "breakout": breakout_strategy,
    "combined": combined_strategy,
}
