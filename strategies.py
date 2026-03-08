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


def is_overextended(df: pd.DataFrame) -> bool:
    """
    Returns True if price is too extended and likely to reverse.
    Blocks entries that are chasing the move.
    """
    last = df.iloc[-1]

    # Early exit: if price is AT or near VWAP (within 1%), it's a retest — always allow
    vwap_dist = abs(last["close"] - last["vwap"]) / last["vwap"]
    if vwap_dist <= 0.01:
        return False

    # 1. Price too far from VWAP
    # Allow up to 5% from VWAP. In a strong trend (RSI 55-75, OB bullish) allow up to 8%
    if vwap_dist > 0.08:
        return True
    elif vwap_dist > 0.05:
        # Only block if RSI is extreme or candle is a blowoff
        if last["rsi"] > 75 or last["rsi"] < 25:
            return True

    # 2. RSI overbought/oversold — don't chase extremes
    if last["rsi"] > 72 or last["rsi"] < 28:
        return True

    # 3. Current candle body is too large (>1.5x ATR) — extended candle, don't chase
    candle_body = abs(last["close"] - last["open"])
    if candle_body > last["atr"] * 1.5:
        return True

    # 4. Price significantly outside Bollinger Bands (>2% beyond the band)
    if last["close"] > last["bb_upper"] * 1.02 or last["close"] < last["bb_lower"] * 0.98:
        return True

    return False


def momentum_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Momentum strategy using EMA crossovers + RSI + MACD.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if is_overextended(df):
        return TradeSignal(Signal.HOLD, "Price overextended, waiting for pullback", 0.0)

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
    if 52 < last["rsi"] < 70:
        buy_score += weight
        reasons.append(f"RSI bullish ({last['rsi']:.1f})")
    elif 30 < last["rsi"] < 48:
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
        if last["macd_hist"] < prev["macd_hist"]:  # still falling, don't catch knife
            return TradeSignal(Signal.HOLD, "Oversold but momentum still falling", 0.0)
        reasons.append(f"Oversold: BB={bb_position:.2f}, RSI={last['rsi']:.1f}, Stoch={last['stoch_k']:.1f}")
        return TradeSignal(Signal.BUY, " | ".join(reasons), 0.75)

    if (last["close"] >= last["bb_upper"] * 0.99 and
            last["rsi"] > 65 and
            last["stoch_k"] > 75 and
            last["stoch_k"] < last["stoch_d"]):
        if last["macd_hist"] > prev["macd_hist"]:  # still rising, don't short strength
            return TradeSignal(Signal.HOLD, "Overbought but momentum still rising", 0.0)
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
        if is_overextended(df):
            return TradeSignal(Signal.HOLD, "Breakout overextended", 0.0)
        reason = f"Breakout above {recent_high:.4f} with {last['volume_ratio']:.1f}x volume"
        return TradeSignal(Signal.BUY, reason, 0.8)

    # Breakdown below recent low with volume
    if (last["close"] < recent_low and
            last["volume_ratio"] > 1.5 and
            last["atr"] > df["atr"].iloc[-lookback:].mean()):
        if is_overextended(df):
            return TradeSignal(Signal.HOLD, "Breakout overextended", 0.0)
        reason = f"Breakdown below {recent_low:.4f} with {last['volume_ratio']:.1f}x volume"
        return TradeSignal(Signal.SELL, reason, 0.8)

    return TradeSignal(Signal.HOLD, "No breakout detected", 0.0)


def sma_vwap_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    9 SMA & 15 SMA + VWAP test & retest strategy with volume & L2 confirmation.

    Entry requires ALL of:
      1. Trend  : 9 SMA > 15 SMA (long) or < (short)
      2. Bias   : Price above/below VWAP
      3. Retest : Price recently tested 9 SMA or VWAP within 0.5%
      4. Bounce : Current candle closed back above/below the level
      5. Volume : Pullback candle had LOW volume (<0.9x avg) — healthy retest
                  Bounce candle has HIGH volume (>1.1x avg) — buyers/sellers in
      6. L2     : Order book imbalance confirms direction (>+0.1 for long, <-0.1 for short)
                  No large wall blocking within 1% of price
    """
    if len(df) < 20:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last  = df.iloc[-1]
    close = last["close"]
    sma9  = last["sma_9"]
    sma15 = last["sma_15"]
    vwap  = last["vwap"]

    if pd.isna(sma9) or pd.isna(sma15) or pd.isna(vwap):
        return TradeSignal(Signal.HOLD, "Indicators not ready", 0.0)

    tolerance = 0.005   # 0.5% proximity for "test"
    lookback  = df.iloc[-6:-1]  # last 5 closed candles

    # Volume analysis
    vol_avg        = df["volume"].iloc[-20:].mean()
    bounce_vol     = last["volume"]
    pullback_vols  = lookback["volume"].values
    low_vol_retest = any(v < vol_avg * 0.9 for v in pullback_vols)
    high_vol_bounce = bounce_vol > vol_avg * 1.1

    # L2 order book
    ob_imbalance  = orderbook["imbalance"]  if orderbook else 0.0
    ask_walls     = orderbook["ask_walls"]  if orderbook else []
    bid_walls     = orderbook["bid_walls"]  if orderbook else []
    best_ask      = orderbook["best_ask"]   if orderbook else close * 1.99
    best_bid      = orderbook["best_bid"]   if orderbook else 0

    # Wall proximity check (within 1% of close)
    ask_wall_nearby = any(w[0] <= close * 1.01 for w in ask_walls)
    bid_wall_nearby = any(w[0] >= close * 0.99 for w in bid_walls)

    # ── LONG setup ───────────────────────────────────────────────────────────
    if sma9 > sma15 and close > vwap and close > sma9:
        tested_sma9  = any(abs(row["low"] - row["sma_9"]) / row["sma_9"] <= tolerance for _, row in lookback.iterrows())
        tested_vwap  = any(abs(row["low"] - row["vwap"])  / row["vwap"]  <= tolerance for _, row in lookback.iterrows())
        # LONG: at least one candle tested the level (low touched) AND closed above it (bullish rejection)
        crossed_back = any(
            row["low"] <= row["sma_9"] * 1.005 and row["close"] > row["sma_9"]
            for _, row in lookback.iterrows()
        )

        if (tested_sma9 or tested_vwap) and crossed_back:
            if orderbook and ob_imbalance < -0.05:
                return TradeSignal(Signal.HOLD, f"LONG contradicted by bearish OB imbalance ({ob_imbalance:+.2f})", 0.0)

            level = "9SMA" if tested_sma9 else "VWAP"
            vol_ok = low_vol_retest and high_vol_bounce
            ob_ok  = ob_imbalance > 0.1 and not ask_wall_nearby

            reasons = [f"Retest {level}", f"9SMA>{sma9:.4f}>15SMA={sma15:.4f}", f"VWAP={vwap:.4f}"]
            if vol_ok:
                reasons.append(f"Vol confirmed (bounce={bounce_vol/vol_avg:.1f}x)")
            if orderbook:
                reasons.append(f"OB imbalance={ob_imbalance:+.2f}")

            # Score: base 0.6, +0.15 for volume, +0.15 for OB
            strength = 0.6 + (0.15 if vol_ok else 0) + (0.15 if ob_ok else 0)

            if not vol_ok:
                reasons.append("weak vol")
            if orderbook and not ob_ok:
                reasons.append("OB bearish or ask wall nearby")

            return TradeSignal(Signal.BUY, " | ".join(reasons), strength)

    # ── SHORT setup ──────────────────────────────────────────────────────────
    if sma9 < sma15 and close < vwap and close < sma9:
        tested_sma9  = any(abs(row["high"] - row["sma_9"]) / row["sma_9"] <= tolerance for _, row in lookback.iterrows())
        tested_vwap  = any(abs(row["high"] - row["vwap"])  / row["vwap"]  <= tolerance for _, row in lookback.iterrows())
        # SHORT: at least one candle tested the level (high touched) AND closed below it (bearish rejection)
        crossed_back = any(
            row["high"] >= row["sma_9"] * 0.995 and row["close"] < row["sma_9"]
            for _, row in lookback.iterrows()
        )

        if (tested_sma9 or tested_vwap) and crossed_back:
            if orderbook and ob_imbalance > 0.05:
                return TradeSignal(Signal.HOLD, f"SHORT contradicted by bullish OB imbalance ({ob_imbalance:+.2f})", 0.0)

            level = "9SMA" if tested_sma9 else "VWAP"
            vol_ok = low_vol_retest and high_vol_bounce
            ob_ok  = ob_imbalance < -0.1 and not bid_wall_nearby

            reasons = [f"Retest {level}", f"9SMA<{sma9:.4f}<15SMA={sma15:.4f}", f"VWAP={vwap:.4f}"]
            if vol_ok:
                reasons.append(f"Vol confirmed (bounce={bounce_vol/vol_avg:.1f}x)")
            if orderbook:
                reasons.append(f"OB imbalance={ob_imbalance:+.2f}")

            strength = 0.6 + (0.15 if vol_ok else 0) + (0.15 if ob_ok else 0)

            if not vol_ok:
                reasons.append("weak vol")
            if orderbook and not ob_ok:
                reasons.append("OB bullish or bid wall nearby")

            return TradeSignal(Signal.SELL, " | ".join(reasons), strength)

    return TradeSignal(Signal.HOLD, "No test & retest setup", 0.0)


def combined_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Combine all strategies. SMA/VWAP is mandatory — must fire BUY or SELL.
    Requires SMA/VWAP + at least 2 of the other 3 strategies to agree (3/4 total).
    """
    signals = [
        momentum_strategy(df),
        mean_reversion_strategy(df),
        breakout_strategy(df),
        sma_vwap_strategy(df, orderbook),
    ]

    # SMA/VWAP is mandatory — if it doesn't fire, no trade
    sma_vwap_sig = signals[3]
    if sma_vwap_sig.signal == Signal.HOLD:
        return TradeSignal(Signal.HOLD, "SMA/VWAP no setup", 0.0)

    direction = sma_vwap_sig.signal  # BUY or SELL

    # Count how many others agree
    others = signals[:3]
    agreeing = [s for s in others if s.signal == direction]

    if len(agreeing) < 2:
        return TradeSignal(Signal.HOLD, f"SMA/VWAP fired but only {len(agreeing)}/3 others agree", 0.0)

    # 3/4 confirmed with SMA/VWAP mandatory
    all_agreeing = agreeing + [sma_vwap_sig]
    avg_strength = sum(s.strength for s in all_agreeing) / len(all_agreeing)

    if avg_strength < 0.65:
        return TradeSignal(Signal.HOLD, "Signal strength too low", 0.0)

    reasons = [s.reason for s in all_agreeing]
    return TradeSignal(direction, f"[3/4 + SMA/VWAP confirmed] " + " | ".join(reasons), avg_strength)


STRATEGIES = {
    "momentum": momentum_strategy,
    "mean_reversion": mean_reversion_strategy,
    "breakout": breakout_strategy,
    "sma_vwap": sma_vwap_strategy,
    "combined": combined_strategy,
}
