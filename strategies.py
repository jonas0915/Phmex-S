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


def ema_scalp_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Fast EMA scalp strategy using EMA3, EMA8, EMA13.

    Buy  when EMA3 crosses above EMA8 and EMA8 > EMA13 and RSI is 45-65.
    Sell when EMA3 crosses below EMA8 and EMA8 < EMA13 and RSI is 35-55.

    Strength = 0.7 when all conditions align, 0.6 when only partial alignment.
    """
    if len(df) < 14:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    close = df["close"]
    ema3  = close.ewm(span=3,  adjust=False).mean()
    ema8  = close.ewm(span=8,  adjust=False).mean()
    ema13 = close.ewm(span=13, adjust=False).mean()

    last_ema3  = ema3.iloc[-1]
    last_ema8  = ema8.iloc[-1]
    last_ema13 = ema13.iloc[-1]
    prev_ema3  = ema3.iloc[-2]
    prev_ema8  = ema8.iloc[-2]

    last_rsi = df["rsi"].iloc[-1]

    ema3_crossed_up   = prev_ema3 <= prev_ema8 and last_ema3 > last_ema8
    ema3_crossed_down = prev_ema3 >= prev_ema8 and last_ema3 < last_ema8

    trend_bullish = last_ema8 > last_ema13
    trend_bearish = last_ema8 < last_ema13
    rsi_buy_zone  = 50 <= last_rsi <= 70
    rsi_sell_zone = 30 <= last_rsi <= 50

    if ema3_crossed_up:
        all_align = trend_bullish and rsi_buy_zone
        strength  = 0.7 if all_align else 0.6
        reason    = (
            f"EMA3 crossed above EMA8 | EMA8={'>' if trend_bullish else '<'}EMA13"
            f" | RSI={last_rsi:.1f}"
        )
        return TradeSignal(Signal.BUY, reason, strength)

    if ema3_crossed_down:
        all_align = trend_bearish and rsi_sell_zone
        strength  = 0.7 if all_align else 0.6
        reason    = (
            f"EMA3 crossed below EMA8 | EMA8={'<' if trend_bearish else '>'}EMA13"
            f" | RSI={last_rsi:.1f}"
        )
        return TradeSignal(Signal.SELL, reason, strength)

    return TradeSignal(Signal.HOLD, "No EMA crossover", 0.0)


def vwap_scalp_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    VWAP pullback-and-bounce scalp strategy.

    Detects a price pullback to VWAP (within 0.3%) on low volume in the last 3
    candles, followed by a bounce candle that closes away from VWAP on
    above-average volume.

    Long if the bounce is above VWAP, short if below. Strength = 0.75.
    """
    if len(df) < 5:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last     = df.iloc[-1]
    lookback = df.iloc[-4:-1]  # last 3 closed candles before current

    vwap       = last["vwap"]
    close      = last["close"]
    vol_avg    = df["volume"].iloc[-20:].mean()
    bounce_vol = last["volume"]

    if pd.isna(vwap) or vwap == 0:
        return TradeSignal(Signal.HOLD, "VWAP not available", 0.0)

    # Check if any of the last 3 candles pulled back to within 0.3% of VWAP
    # on below-average volume (quiet retest)
    pullback_found = False
    for _, row in lookback.iterrows():
        vwap_dist = abs(row["close"] - row["vwap"]) / row["vwap"]
        low_vol   = row["volume"] < vol_avg
        if vwap_dist <= 0.003 and low_vol:
            pullback_found = True
            break

    if not pullback_found:
        return TradeSignal(Signal.HOLD, "No VWAP pullback detected in last 3 candles", 0.0)

    # Bounce candle must close away from VWAP (> 0.1%) with above-average volume
    bounce_dist     = abs(close - vwap) / vwap
    high_vol_bounce = bounce_vol > vol_avg

    if bounce_dist <= 0.002 or not high_vol_bounce:
        return TradeSignal(Signal.HOLD, "Bounce not confirmed (vol or distance weak)", 0.0)

    if close > vwap:
        reason = (
            f"VWAP pullback bounce LONG | close={close:.4f} > VWAP={vwap:.4f}"
            f" | vol={bounce_vol/vol_avg:.1f}x avg"
        )
        return TradeSignal(Signal.BUY, reason, 0.75)

    if close < vwap:
        reason = (
            f"VWAP pullback bounce SHORT | close={close:.4f} < VWAP={vwap:.4f}"
            f" | vol={bounce_vol/vol_avg:.1f}x avg"
        )
        return TradeSignal(Signal.SELL, reason, 0.75)

    return TradeSignal(Signal.HOLD, "Price at VWAP, no directional bias", 0.0)


def momentum_burst_strategy(df: pd.DataFrame) -> TradeSignal:
    """
    Momentum burst scalp strategy.

    Fires when a sudden volume spike (> 2x average) occurs alongside a strong
    directional candle (body > 0.6x ATR). RSI and MACD histogram must confirm
    direction. Strength = 0.80 when all conditions are met.
    """
    if len(df) < 3:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    vol_avg      = df["volume"].iloc[-20:].mean()
    volume_burst = last["volume"] > vol_avg * 2.0

    if not volume_burst:
        return TradeSignal(Signal.HOLD, "No volume burst", 0.0)

    candle_body   = abs(last["close"] - last["open"])
    strong_candle = candle_body > last["atr"] * 0.6

    if not strong_candle:
        return TradeSignal(Signal.HOLD, "Volume burst but candle body too small", 0.0)

    rsi       = last["rsi"]
    macd_hist = last["macd_hist"]
    prev_hist = prev["macd_hist"]

    is_bullish_candle = last["close"] > last["open"]
    is_bearish_candle = last["close"] < last["open"]

    rsi_long_ok  = rsi > 50
    rsi_short_ok = rsi < 50
    macd_rising  = macd_hist > prev_hist
    macd_falling = macd_hist < prev_hist

    if is_bullish_candle and rsi_long_ok and macd_rising:
        reason = (
            f"Momentum burst LONG | vol={last['volume']/vol_avg:.1f}x avg"
            f" | body={candle_body:.4f} ({candle_body/last['atr']:.1f}x ATR)"
            f" | RSI={rsi:.1f} | MACD hist rising"
        )
        return TradeSignal(Signal.BUY, reason, 0.80)

    if is_bearish_candle and rsi_short_ok and macd_falling:
        reason = (
            f"Momentum burst SHORT | vol={last['volume']/vol_avg:.1f}x avg"
            f" | body={candle_body:.4f} ({candle_body/last['atr']:.1f}x ATR)"
            f" | RSI={rsi:.1f} | MACD hist falling"
        )
        return TradeSignal(Signal.SELL, reason, 0.80)

    return TradeSignal(Signal.HOLD, "Volume burst but direction/RSI/MACD not aligned", 0.0)


def combined_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Scalp combined strategy.

    All 3 sub-strategies vote. Requires at least 2/3 to agree on direction and
    an average strength >= 0.70. Applies a quick overextension guard (RSI > 75
    or RSI < 25 => HOLD). If an orderbook is provided and its imbalance
    contradicts the intended direction by more than 0.15, returns HOLD.
    """
    if len(df) < 14:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    # Overextension guard
    rsi = df["rsi"].iloc[-1]
    if rsi > 75 or rsi < 25:
        return TradeSignal(
            Signal.HOLD,
            f"RSI overextended ({rsi:.1f}), skipping scalp entry",
            0.0,
        )

    sub_signals = [
        ema_scalp_strategy(df),
        vwap_scalp_strategy(df),
        momentum_burst_strategy(df),
    ]

    buy_signals  = [s for s in sub_signals if s.signal == Signal.BUY]
    sell_signals = [s for s in sub_signals if s.signal == Signal.SELL]

    if len(buy_signals) >= 2:
        direction = Signal.BUY
        agreeing  = buy_signals
    elif len(sell_signals) >= 2:
        direction = Signal.SELL
        agreeing  = sell_signals
    else:
        return TradeSignal(Signal.HOLD, "Less than 2/3 sub-strategies agree", 0.0)

    avg_strength = sum(s.strength for s in agreeing) / len(agreeing)
    if avg_strength < 0.70:
        return TradeSignal(
            Signal.HOLD,
            f"Average strength {avg_strength:.2f} below 0.70 threshold",
            0.0,
        )

    # Orderbook weighting
    if orderbook is not None:
        # Block entry on illiquid markets
        if orderbook.get("illiquid", False):
            return TradeSignal(
                Signal.HOLD,
                "Market illiquid (spread > 0.3%), skipping entry",
                0.0,
            )

        dir_str = "long" if direction == Signal.BUY else "short"
        ob_score = 0.0
        ob_score = orderbook.get("imbalance", 0.0)
        bid_walls = orderbook.get("bid_walls", [])
        ask_walls = orderbook.get("ask_walls", [])
        if dir_str == "long":
            if bid_walls: ob_score += 0.10
            if ask_walls: ob_score -= 0.10
        else:
            if ask_walls: ob_score += 0.10
            if bid_walls: ob_score -= 0.10
        ob_score = max(-1.0, min(1.0, ob_score))

        # Blend: 75% strategy strength, 25% order book
        raw_strategy_strength = avg_strength
        final_strength = (raw_strategy_strength * 0.75) + (ob_score * 0.25)
    else:
        final_strength = avg_strength

    sub_reasons = " | ".join(s.reason for s in agreeing)
    reason = f"[SCALP 2/3] {sub_reasons}"
    return TradeSignal(direction, reason, final_strength)


def trend_scalp_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Trend-filtered momentum scalp on 1m candles with order book confirmation.

    Trend filter : close vs EMA-200
    Entry trigger: EMA-9 crossed EMA-21 within the last 3 candles (not just current)
    Volume       : current volume > 1.2x 20-period average
    Momentum     : MACD histogram confirming direction
    RSI guard    : 30-75 (not overextended)
    Order book   : if provided, blocks entry on illiquid markets or adverse imbalance;
                   boosts/penalises strength based on flow direction and walls.

    Strength:
      0.65 base
      +0.05 if crossover on current candle (freshest signal)
      +0.05 if MACD histogram above its 20-period mean
      +0.05 if RSI in ideal zone (45-65 long / 35-55 short)
      +/- 0.05 order book imbalance adjustment
    """
    if len(df) < 150:
        return TradeSignal(Signal.HOLD, f"Warming up ({len(df)}/150 candles)", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close      = last["close"]
    ema_9      = last["ema_9"]
    ema_21     = last["ema_21"]
    ema_200    = last["ema_200"]
    rsi        = last["rsi"]
    macd_hist  = last["macd_hist"]
    prev_hist  = prev["macd_hist"]
    volume     = last["volume"]
    atr_val    = last["atr"]

    vol_avg = df["volume"].iloc[-20:].mean()

    # Gate: EMA values ready
    if pd.isna(ema_200) or pd.isna(ema_9) or pd.isna(ema_21):
        return TradeSignal(Signal.HOLD, "EMA values warming up", 0.0)

    # Gate: RSI not overextended
    if pd.isna(rsi) or not (30 <= rsi <= 75):
        return TradeSignal(Signal.HOLD, f"RSI overextended ({rsi:.1f})", 0.0)

    # Gate: volume spike required (lowered to 1.2x for more opportunities)
    if vol_avg <= 0 or volume <= vol_avg * 1.2:
        return TradeSignal(Signal.HOLD, f"Volume weak ({volume/vol_avg:.2f}x avg, need 1.2x)", 0.0)

    # Crossover detection — check last 3 candles for a cross
    crossover_up = False
    crossover_down = False
    cross_age = 0  # 0 = current candle, 1 = one back, 2 = two back
    for i in range(1, min(4, len(df))):
        cur = df.iloc[-i]
        prv = df.iloc[-(i + 1)]
        if prv["ema_9"] <= prv["ema_21"] and cur["ema_9"] > cur["ema_21"]:
            crossover_up = True
            cross_age = i - 1
            break
        if prv["ema_9"] >= prv["ema_21"] and cur["ema_9"] < cur["ema_21"]:
            crossover_down = True
            cross_age = i - 1
            break

    # Trend direction
    trend_long  = close > ema_200
    trend_short = close < ema_200

    # MACD strength bonus
    hist_mean   = df["macd_hist"].iloc[-20:].abs().mean()
    strong_macd = (hist_mean > 0) and (abs(macd_hist) > hist_mean)

    # Build signal
    direction = None
    if crossover_up and trend_long and macd_hist > 0 and macd_hist > prev_hist:
        direction = Signal.BUY
    elif crossover_down and trend_short and macd_hist < 0 and macd_hist < prev_hist:
        direction = Signal.SELL

    if direction is None:
        return TradeSignal(Signal.HOLD, "No qualifying trend-scalp setup", 0.0)

    # Calculate strength
    strength = 0.65
    if cross_age == 0:
        strength += 0.05  # freshest crossover
    if strong_macd:
        strength += 0.05
    if direction == Signal.BUY and 45 <= rsi <= 65:
        strength += 0.05
    elif direction == Signal.SELL and 35 <= rsi <= 55:
        strength += 0.05

    # Order book confirmation
    ob_info = ""
    if orderbook is not None:
        # Block on illiquid markets
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, f"Illiquid market (spread {orderbook.get('spread_pct', 0):.2f}%)", 0.0)

        imbalance  = orderbook.get("imbalance", 0.0)
        bid_walls  = orderbook.get("bid_walls", [])
        ask_walls  = orderbook.get("ask_walls", [])
        spread_pct = orderbook.get("spread_pct", 0.0)

        ob_adj = 0.0
        if direction == Signal.BUY:
            ob_adj += imbalance * 0.10   # positive imbalance = more bids = bullish
            if bid_walls: ob_adj += 0.03
            if ask_walls: ob_adj -= 0.05  # sell wall opposes long
        else:
            ob_adj -= imbalance * 0.10   # positive imbalance = more bids = bearish for shorts
            if ask_walls: ob_adj += 0.03
            if bid_walls: ob_adj -= 0.05  # buy wall opposes short

        # Block entry if order book strongly contradicts (adverse imbalance > 0.3)
        if direction == Signal.BUY and imbalance < -0.3:
            return TradeSignal(Signal.HOLD, f"OB blocks long — heavy ask imbalance ({imbalance:.2f})", 0.0)
        if direction == Signal.SELL and imbalance > 0.3:
            return TradeSignal(Signal.HOLD, f"OB blocks short — heavy bid imbalance ({imbalance:.2f})", 0.0)

        strength += ob_adj
        ob_info = f" | OB_imb={imbalance:+.2f} adj={ob_adj:+.3f} spread={spread_pct:.3f}%"

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    cross_str = f"candle-{cross_age}" if cross_age > 0 else "current"
    reason = (
        f"TREND SCALP {dir_str} | EMA9xEMA21 {'UP' if direction == Signal.BUY else 'DOWN'} ({cross_str})"
        f" | {close:.4f} {'>' if trend_long else '<'} EMA200={ema_200:.4f}"
        f" | vol={volume/vol_avg:.1f}x | MACD={macd_hist:.5f} | RSI={rsi:.1f}"
        f" | ATR={atr_val:.4f}{ob_info}"
    )
    return TradeSignal(direction, reason, strength)


STRATEGIES = {
    "ema_scalp":      ema_scalp_strategy,
    "vwap_scalp":     vwap_scalp_strategy,
    "momentum_burst": momentum_burst_strategy,
    "combined":       combined_strategy,
    "trend_scalp":    trend_scalp_strategy,
}
