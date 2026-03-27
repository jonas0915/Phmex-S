from dataclasses import dataclass
from enum import Enum
import logging
import pandas as pd

_log = logging.getLogger("DegenCryt")


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    signal: Signal
    reason: str
    strength: float  # 0.0 to 1.0


def trend_scalp_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Trend-filtered momentum scalp on 1m candles with order book confirmation.

    Trend filter : close vs EMA-200
    Entry trigger: EMA-9 crossed EMA-21 within the last 6 candles (not just current)
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
        return TradeSignal(Signal.HOLD, f"Volume weak ({volume/max(vol_avg, 1e-10):.2f}x avg, need 1.2x)", 0.0)

    # Crossover detection — check last 3 candles for a cross
    crossover_up = False
    crossover_down = False
    cross_age = 0  # 0 = current candle, 1 = one back, 2 = two back
    for i in range(1, min(7, len(df))):
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
        f" | vol={volume/max(vol_avg, 1e-10):.1f}x | MACD={macd_hist:.5f} | RSI={rsi:.1f}"
        f" | ATR={atr_val:.4f}{ob_info}"
    )
    return TradeSignal(direction, reason, min(strength, 0.90))


def bb_mean_reversion_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Bollinger Band mean reversion scalp.

    Entry: Price touches/penetrates outer BB with RSI(7) confirmation,
    then closes back inside the band. Targets BB middle (mean).
    """
    if len(df) < 20:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = last["close"]
    bb_upper = last["bb_upper"]
    bb_lower = last["bb_lower"]
    bb_mid = last["bb_mid"]
    rsi_fast = last.get("rsi_fast", last.get("rsi", 50))
    adx_val = last.get("adx", 25)
    volume = last["volume"]
    vol_avg = df["volume"].iloc[-20:].mean()

    # Only use mean reversion in ranging/low-trend markets (ADX < 30)
    if adx_val > 30:
        return TradeSignal(Signal.HOLD, f"ADX too high for mean reversion ({adx_val:.1f})", 0.0)

    # --- Trend direction filter ---
    # Mean reversion MUST NOT fight a structural trend.
    ema_9 = last.get("ema_9", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)
    ema_200 = last.get("ema_200", 0)
    plus_di = last.get("plus_di", 0)
    minus_di = last.get("minus_di", 0)

    ema_bearish = ema_9 < ema_21 < ema_50
    ema_bullish = ema_9 > ema_21 > ema_50
    below_ema200 = close < ema_200 if ema_200 > 0 else False
    above_ema200 = close > ema_200 if ema_200 > 0 else False
    di_bearish = adx_val > 20 and minus_di > plus_di * 1.3
    di_bullish = adx_val > 20 and plus_di > minus_di * 1.3

    # Trend filter: require 2 of 3 bearish/bullish signals to block (was OR — too aggressive)
    downtrend = sum([ema_bearish, below_ema200, di_bearish]) >= 2
    uptrend = sum([ema_bullish, above_ema200, di_bullish]) >= 2

    # Volume confirmation: rejection should have above-avg volume
    vol_ok = volume > vol_avg * 1.3

    # BB width filter: skip tight consolidation where mean reversion target is too close
    atr_val = last.get("atr", 0)
    bb_width_pct = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0
    atr_pct = atr_val / close if close > 0 else 0
    if atr_pct > 0 and bb_width_pct < 1.5 * atr_pct:
        return TradeSignal(Signal.HOLD, f"BB too tight for mean reversion (width={bb_width_pct:.4f})", 0.0)

    # LONG: Price penetrated lower BB (close or meaningful wick), now closing back inside + RSI oversold
    prev_close_below = prev["close"] <= prev.get("bb_lower", prev["close"])
    prev_wick_below = prev["low"] < prev.get("bb_lower", prev["low"]) * 0.998  # 0.2% penetration
    if (prev_close_below or prev_wick_below) and close > bb_lower:
        if downtrend:
            return TradeSignal(Signal.HOLD,
                f"BB reversion LONG blocked — downtrend (EMA={ema_bearish}, <200={below_ema200}, DI={di_bearish})",
                0.0)
        if rsi_fast < 30 and vol_ok:
            strength = 0.85
            if rsi_fast < 15:
                strength += 0.05
            if orderbook and orderbook.get("imbalance", 0) > 0.1:
                strength += 0.05
            if orderbook and orderbook.get("illiquid", False):
                return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
            return TradeSignal(Signal.BUY,
                f"BB mean reversion LONG | lower BB bounce | RSI(7)={rsi_fast:.1f} | vol={volume/max(vol_avg, 1e-10):.1f}x",
                min(strength, 0.95))

    # SHORT: Price penetrated upper BB (close or meaningful wick), now closing back inside + RSI overbought
    prev_close_above = prev["close"] >= prev.get("bb_upper", prev["close"])
    prev_wick_above = prev["high"] > prev.get("bb_upper", prev["high"]) * 1.002  # 0.2% penetration
    if (prev_close_above or prev_wick_above) and close < bb_upper:
        if uptrend:
            return TradeSignal(Signal.HOLD,
                f"BB reversion SHORT blocked — uptrend (EMA={ema_bullish}, >200={above_ema200}, DI={di_bullish})",
                0.0)
        if rsi_fast > 70 and vol_ok:
            strength = 0.85
            if rsi_fast > 85:
                strength += 0.05
            if orderbook and orderbook.get("imbalance", 0) < -0.1:
                strength += 0.05
            if orderbook and orderbook.get("illiquid", False):
                return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
            return TradeSignal(Signal.SELL,
                f"BB mean reversion SHORT | upper BB rejection | RSI(7)={rsi_fast:.1f} | vol={volume/max(vol_avg, 1e-10):.1f}x",
                min(strength, 0.95))

    return TradeSignal(Signal.HOLD, "No BB mean reversion setup", 0.0)


def trend_pullback_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Trend continuation on pullback to EMA-21.
    Enters when price pulls back to EMA-21 in a strong trend (ADX > 30).
    This is the bread-and-butter scalp entry for trending markets.
    """
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    adx_val = last.get("adx", 0)
    rsi = last.get("rsi", 50)
    volume = last["volume"]
    vol_avg = df["volume"].iloc[-20:].mean()
    close = last["close"]

    # Need strong trend
    if adx_val < 30:
        return TradeSignal(Signal.HOLD, "Trend not strong enough for pullback", 0.0)

    # Volume hard gate — low-volume pullbacks are noise
    if volume < vol_avg * 1.0:
        return TradeSignal(Signal.HOLD, f"Trend pullback blocked — low volume ({volume/max(vol_avg, 1e-10):.1f}x)", 0.0)

    # Use pre-computed EMAs
    last_ema21 = last.get("ema_21", 0)
    last_ema50 = last.get("ema_50", 0)
    if last_ema21 == 0 or last_ema50 == 0:
        return TradeSignal(Signal.HOLD, "Missing EMA data", 0.0)
    prev_close = prev["close"]

    # LONG: uptrend (EMA21 > EMA50), price touched/crossed EMA21 from above, now bouncing
    if last_ema21 > last_ema50:
        touched_ema = abs(prev_close - last_ema21) / last_ema21 < 0.008  # within 0.8% of EMA21
        bouncing = close > last_ema21
        rsi_ok = 40 <= rsi <= 65

        if touched_ema and bouncing and rsi_ok:
            if len(df) > 50:
                recent_high = df["high"].iloc[-50:-1].max()
                dist_to_resistance = (recent_high - close) / close
                if 0 < dist_to_resistance < 0.003:
                    return TradeSignal(Signal.HOLD,
                        f"Trend pullback LONG blocked — too close to resistance ({dist_to_resistance:.4f})", 0.0)
            strength = 0.80
            if volume > vol_avg * 1.5:
                strength += 0.03
            if adx_val > 40:
                strength += 0.03
            if orderbook and orderbook.get("imbalance", 0) > 0.1:
                strength += 0.02
            if orderbook and orderbook.get("illiquid", False):
                return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
            return TradeSignal(Signal.BUY,
                f"Trend pullback LONG | EMA21 bounce | ADX={adx_val:.1f} | RSI={rsi:.1f} | vol={volume/max(vol_avg, 1e-10):.1f}x",
                min(strength, 0.92))

    # SHORT: downtrend (EMA21 < EMA50), price touched/crossed EMA21 from below, now dropping
    if last_ema21 < last_ema50:
        touched_ema = abs(prev_close - last_ema21) / last_ema21 < 0.008  # within 0.8% of EMA21
        dropping = close < last_ema21
        rsi_ok = 35 <= rsi <= 60

        if touched_ema and dropping and rsi_ok:
            if len(df) > 50:
                recent_low = df["low"].iloc[-50:-1].min()
                dist_to_support = (close - recent_low) / close
                if 0 < dist_to_support < 0.003:
                    return TradeSignal(Signal.HOLD,
                        f"Trend pullback SHORT blocked — too close to support ({dist_to_support:.4f})", 0.0)
            strength = 0.80
            if volume > vol_avg * 1.5:
                strength += 0.03
            if adx_val > 40:
                strength += 0.03
            if orderbook and orderbook.get("imbalance", 0) < -0.1:
                strength += 0.02
            if orderbook and orderbook.get("illiquid", False):
                return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
            return TradeSignal(Signal.SELL,
                f"Trend pullback SHORT | EMA21 rejection | ADX={adx_val:.1f} | RSI={rsi:.1f} | vol={volume/max(vol_avg, 1e-10):.1f}x",
                min(strength, 0.92))

    # Diagnostic fallthrough
    if last_ema21 > last_ema50:
        touched = abs(prev_close - last_ema21) / last_ema21 < 0.008
        bouncing = close > last_ema21
        rsi_ok = 40 <= rsi <= 65
        return TradeSignal(Signal.HOLD,
            f"trend_pullback LONG: touch={touched} bounce={bouncing} rsi_ok={rsi_ok}({rsi:.1f})", 0.0)
    elif last_ema21 < last_ema50:
        touched = abs(prev_close - last_ema21) / last_ema21 < 0.008
        dropping = close < last_ema21
        rsi_ok = 35 <= rsi <= 60
        return TradeSignal(Signal.HOLD,
            f"trend_pullback SHORT: touch={touched} drop={dropping} rsi_ok={rsi_ok}({rsi:.1f})", 0.0)
    return TradeSignal(Signal.HOLD, "trend_pullback: EMA21≈EMA50 (no trend direction)", 0.0)


def keltner_squeeze_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Keltner Channel squeeze breakout. Fires when BB exits Keltner after compression.
    """
    if len(df) < 30:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    squeeze_now = last.get("squeeze", False)
    squeeze_prev = prev.get("squeeze", False)

    # Squeeze just released (was in squeeze, now not)
    if squeeze_prev and not squeeze_now:
        close = last["close"]
        kc_upper = last.get("kc_upper", 0)
        kc_lower = last.get("kc_lower", 0)
        macd_hist = last.get("macd_hist", 0)
        volume = last["volume"]
        vol_avg = df["volume"].iloc[-20:].mean()
        adx_val = last.get("adx", 25)

        # Need volume confirmation (1.5x avg — squeeze itself is the confirmation)
        if volume < vol_avg * 1.5:
            return TradeSignal(Signal.HOLD, "Squeeze release but low volume", 0.0)

        strength = 0.83  # bumped from 0.82 so shorts can clear 0.80 gate (0.83-0.08+0.05=0.80)
        if adx_val > 25:
            strength += 0.05

        if close > kc_upper and macd_hist > 0:
            if orderbook and orderbook.get("illiquid", False):
                return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
            return TradeSignal(Signal.BUY,
                f"KC squeeze breakout LONG | vol={volume/max(vol_avg, 1e-10):.1f}x | ADX={adx_val:.1f}",
                min(strength, 0.90))

        if close < kc_lower and macd_hist < 0:
            if orderbook and orderbook.get("illiquid", False):
                return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
            return TradeSignal(Signal.SELL,
                f"KC squeeze breakout SHORT | vol={volume/max(vol_avg, 1e-10):.1f}x | ADX={adx_val:.1f}",
                min(strength, 0.90))

        # Squeeze released but no directional break
        return TradeSignal(Signal.HOLD,
            f"keltner: squeeze released, no break (close={close:.2f} KC={kc_lower:.2f}-{kc_upper:.2f} MACD={macd_hist:.5f})", 0.0)

    return TradeSignal(Signal.HOLD,
        f"keltner: no squeeze release (sq_prev={squeeze_prev} sq_now={squeeze_now})", 0.0)


def momentum_continuation_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Momentum continuation for established trends (ADX > 25).
    Fills the gap when trend is running but no crossover/pullback exists.
    Enters when price is trending with expanding MACD histogram.

    Strength: 0.72 base, max ~0.88.
    """
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    adx_val = last.get("adx", 0)
    rsi = last.get("rsi", 50)
    close = last["close"]
    # Use last COMPLETED candle for volume (iloc[-1] is still forming, has partial volume)
    volume = prev["volume"]
    vol_avg = df["volume"].iloc[-21:-1].mean()
    macd_hist = last.get("macd_hist", 0)
    prev_hist = prev.get("macd_hist", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)

    if pd.isna(ema_21) or pd.isna(ema_50) or ema_21 == 0 or ema_50 == 0:
        return TradeSignal(Signal.HOLD, "EMA values warming up", 0.0)

    # Gate: need some trend direction (lowered from 25 to fire more often)
    if adx_val < 20:
        return TradeSignal(Signal.HOLD, f"ADX too low for momentum cont ({adx_val:.1f})", 0.0)

    # Gate: volume at least average (using completed candle)
    if vol_avg <= 0 or volume < vol_avg * 1.0:
        return TradeSignal(Signal.HOLD, f"Volume below average ({volume/max(vol_avg, 1e-10):.2f}x)", 0.0)

    # Determine direction from EMA structure
    trend_long = ema_21 > ema_50
    trend_short = ema_21 < ema_50

    # Gate: price must be on the right side of EMA-21 (in the trend)
    price_long = close > ema_21
    price_short = close < ema_21

    # Gate: price within 3% of EMA-21 — no chasing (widened from 2% for more entries)
    ema_distance_pct = abs(close - ema_21) / ema_21 * 100
    if ema_distance_pct > 3.0:
        return TradeSignal(Signal.HOLD, f"Price too far from EMA-21 ({ema_distance_pct:.1f}%)", 0.0)

    # Gate: MACD histogram must be expanding in trend direction
    hist_expanding_long = macd_hist > 0 and macd_hist > prev_hist
    hist_expanding_short = macd_hist < 0 and macd_hist < prev_hist

    direction = None
    if trend_long and price_long and hist_expanding_long:
        # RSI guard: 40-70 for longs (not overextended)
        if 40 <= rsi <= 70:
            direction = Signal.BUY
    elif trend_short and price_short and hist_expanding_short:
        # RSI guard: 30-60 for shorts
        if 30 <= rsi <= 60:
            direction = Signal.SELL

    if direction is None:
        # Diagnostic: which condition blocked?
        if not (trend_long or trend_short):
            detail = f"no EMA trend (EMA21={ema_21:.2f} EMA50={ema_50:.2f})"
        elif trend_long and not price_long:
            detail = f"price {close:.2f} < EMA21 {ema_21:.2f}"
        elif trend_short and not price_short:
            detail = f"price {close:.2f} > EMA21 {ema_21:.2f}"
        elif trend_long and not hist_expanding_long:
            detail = f"MACD not expanding (hist={macd_hist:.5f} prev={prev_hist:.5f})"
        elif trend_short and not hist_expanding_short:
            detail = f"MACD not expanding (hist={macd_hist:.5f} prev={prev_hist:.5f})"
        elif trend_long and not (40 <= rsi <= 70):
            detail = f"RSI {rsi:.1f} outside 40-70"
        elif trend_short and not (30 <= rsi <= 60):
            detail = f"RSI {rsi:.1f} outside 30-60"
        else:
            detail = f"EMA21={'>' if trend_long else '<'}EMA50 hist={macd_hist:.5f} RSI={rsi:.1f}"
        return TradeSignal(Signal.HOLD, f"momentum_cont: {detail}", 0.0)

    # Calculate strength: 0.72 base
    strength = 0.72

    # Bonus: Stochastic confirmation
    stoch_k = last.get("stoch_k", 50)
    if direction == Signal.BUY and 20 < stoch_k < 80:
        strength += 0.04
    elif direction == Signal.SELL and 20 < stoch_k < 80:
        strength += 0.04

    # Bonus: VWAP confirmation
    vwap = last.get("vwap", 0)
    if vwap > 0:
        if direction == Signal.BUY and close > vwap:
            strength += 0.04
        elif direction == Signal.SELL and close < vwap:
            strength += 0.04

    # Bonus: strong ADX
    if adx_val > 35:
        strength += 0.03

    # Bonus: volume spike
    if volume > vol_avg * 1.5:
        strength += 0.03

    # Order book confirmation
    ob_info = ""
    if orderbook is not None:
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, f"Illiquid market (spread {orderbook.get('spread_pct', 0):.2f}%)", 0.0)

        imbalance = orderbook.get("imbalance", 0.0)

        # Block entry if OB strongly contradicts
        if direction == Signal.BUY and imbalance < -0.3:
            return TradeSignal(Signal.HOLD, f"OB blocks long — heavy ask imbalance ({imbalance:.2f})", 0.0)
        if direction == Signal.SELL and imbalance > 0.3:
            return TradeSignal(Signal.HOLD, f"OB blocks short — heavy bid imbalance ({imbalance:.2f})", 0.0)

        # OB strength bonus
        if direction == Signal.BUY and imbalance > 0.15:
            strength += 0.02
        elif direction == Signal.SELL and imbalance < -0.15:
            strength += 0.02

        ob_info = f" | OB_imb={imbalance:+.2f}"

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    reason = (
        f"MOMENTUM CONT {dir_str} | EMA21{'>' if trend_long else '<'}EMA50"
        f" | price {'>' if price_long else '<'} EMA21 ({ema_distance_pct:.1f}% away)"
        f" | MACD expanding | ADX={adx_val:.1f} | RSI={rsi:.1f}"
        f" | vol={volume/max(vol_avg, 1e-10):.1f}x{ob_info}"
    )
    return TradeSignal(direction, reason, min(strength, 0.88))


def vwap_reversion_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    VWAP mean reversion for ranging markets (ADX < 25).
    Fades price when stretched from VWAP with RSI confirmation.
    Targets return to VWAP — works in sideways/low-momentum conditions.

    Strength: 0.80 base, max ~0.90.
    """
    if len(df) < 30:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = last["close"]
    rsi = last.get("rsi", 50)
    rsi_fast = last.get("rsi_fast", rsi)
    vwap = last.get("vwap", 0)
    volume = last["volume"]
    vol_avg = df["volume"].iloc[-20:].mean()
    adx_val = last.get("adx", 25)

    if vwap <= 0 or pd.isna(vwap):
        return TradeSignal(Signal.HOLD, "VWAP not available", 0.0)

    # Only in ranging/low-momentum markets
    if adx_val > 25:
        return TradeSignal(Signal.HOLD, f"ADX too high for VWAP reversion ({adx_val:.1f})", 0.0)

    # Distance from VWAP
    vwap_dist_pct = (close - vwap) / vwap * 100

    # Volume confirmation — need above-average volume on the rejection
    vol_ok = volume > vol_avg * 1.0

    direction = None

    # LONG: price significantly below VWAP + RSI oversold + bouncing
    if vwap_dist_pct < -0.3 and rsi_fast < 35 and vol_ok:
        # Confirmation: price bouncing (current close > previous close)
        if close > prev["close"]:
            direction = Signal.BUY

    # SHORT: price significantly above VWAP + RSI overbought + dropping
    if vwap_dist_pct > 0.3 and rsi_fast > 65 and vol_ok:
        # Confirmation: price dropping (current close < previous close)
        if close < prev["close"]:
            direction = Signal.SELL

    if direction is None:
        vol_ok_flag = volume > vol_avg * 1.0
        if abs(vwap_dist_pct) < 0.3:
            detail = f"VWAP dist {vwap_dist_pct:+.2f}% < 0.30%"
        elif not vol_ok_flag:
            detail = f"vol {volume/max(vol_avg, 1e-10):.2f}x < 1.0x"
        elif vwap_dist_pct < 0 and rsi_fast >= 35:
            detail = f"RSI(7) {rsi_fast:.1f} not oversold (<35)"
        elif vwap_dist_pct > 0 and rsi_fast <= 65:
            detail = f"RSI(7) {rsi_fast:.1f} not overbought (>65)"
        else:
            detail = f"no price reversal (dist={vwap_dist_pct:+.2f}% rsi7={rsi_fast:.1f})"
        return TradeSignal(Signal.HOLD, f"vwap_reversion: {detail}", 0.0)

    # Calculate strength (0.87 base so shorts survive -0.08 penalty: 0.87-0.08=0.79 > 0.78 gate)
    strength = 0.87

    # Bonus: extreme distance from VWAP
    if abs(vwap_dist_pct) > 0.6:
        strength += 0.03

    # Bonus: extreme RSI
    if (direction == Signal.BUY and rsi_fast < 25) or (direction == Signal.SELL and rsi_fast > 75):
        strength += 0.03

    # Bonus: volume spike
    if volume > vol_avg * 1.5:
        strength += 0.02

    # Order book confirmation
    ob_info = ""
    if orderbook is not None:
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, "Illiquid market", 0.0)
        imbalance = orderbook.get("imbalance", 0.0)
        if direction == Signal.BUY and imbalance < -0.3:
            return TradeSignal(Signal.HOLD, f"OB blocks long — heavy ask imbalance ({imbalance:.2f})", 0.0)
        if direction == Signal.SELL and imbalance > 0.3:
            return TradeSignal(Signal.HOLD, f"OB blocks short — heavy bid imbalance ({imbalance:.2f})", 0.0)
        if (direction == Signal.BUY and imbalance > 0.15) or (direction == Signal.SELL and imbalance < -0.15):
            strength += 0.02
        ob_info = f" | OB_imb={imbalance:+.2f}"

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    reason = (
        f"VWAP REVERSION {dir_str} | dist={vwap_dist_pct:+.2f}%"
        f" | RSI(7)={rsi_fast:.1f} | ADX={adx_val:.1f}"
        f" | vol={volume/max(vol_avg, 1e-10):.1f}x{ob_info}"
    )
    return TradeSignal(direction, reason, min(strength, 0.90))


def adaptive_strategy(df: pd.DataFrame, orderbook: dict = None) -> TradeSignal:
    """
    Adaptive strategy that selects sub-strategies based on market regime.

    Low ADX (< 25): Mean reversion (BB bounce, VWAP)
    High ADX (>= 25): Momentum/trend (Keltner squeeze, trend scalp, momentum burst)
    Choppiness > 61.8: Skip entries entirely (Fibonacci choppy threshold)
    """
    if len(df) < 30:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    last = df.iloc[-1]
    adx_val = last.get("adx", 25)
    chop_val = last.get("chop", 50)
    rsi = last.get("rsi", 50)

    # Hard filter: choppy market (raised from 61.8 to 65 — crypto is naturally choppier)
    if chop_val > 65.0:
        return TradeSignal(Signal.HOLD, f"Choppy market (CHOP={chop_val:.1f}), sitting out", 0.0)

    # Overextension guard — only block true extremes, not strong trends
    if rsi > 85 or rsi < 15:
        return TradeSignal(Signal.HOLD, f"RSI extreme ({rsi:.1f}), sitting out", 0.0)

    signals = []

    if adx_val < 20:
        # Ranging market — VWAP reversion for mean-reversion setups
        signals.append(vwap_reversion_strategy(df, orderbook))
    elif adx_val <= 30:
        # Overlap zone (ADX 20-30) — only strategies that can fire here
        # trend_pullback gates ADX >= 30 internally, always HOLD here — removed
        # trend_scalp base 0.65, rarely passes 0.80 gate, 37.5% WR — removed
        signals.append(keltner_squeeze_strategy(df, orderbook))
        signals.append(momentum_continuation_strategy(df, orderbook))
    else:
        # Clearly trending market (ADX > 30) — pullback + momentum + squeeze
        # trend_scalp removed: base 0.65 rarely clears 0.80 gate, 37.5% WR
        signals.append(keltner_squeeze_strategy(df, orderbook))
        signals.append(trend_pullback_strategy(df, orderbook))
        signals.append(momentum_continuation_strategy(df, orderbook))

    # Per-strategy rejection logging
    holds = [s for s in signals if s.signal == Signal.HOLD]
    for s in holds:
        _log.debug(f"[STRAT] {s.reason}")

    # Pick the strongest non-HOLD signal
    active = [s for s in signals if s.signal != Signal.HOLD]
    if not active:
        return TradeSignal(Signal.HOLD, f"No signal (ADX={adx_val:.1f}, CHOP={chop_val:.1f})", 0.0)

    # If multiple strong signals agree on direction, boost strength
    buy_signals = [s for s in active if s.signal == Signal.BUY]
    sell_signals = [s for s in active if s.signal == Signal.SELL]
    strong_buys  = [s for s in buy_signals if s.strength >= 0.65]
    strong_sells = [s for s in sell_signals if s.strength >= 0.65]

    if len(strong_buys) >= 2:
        best = max(strong_buys, key=lambda s: s.strength)
        boost = min(0.10, 0.05 * (len(strong_buys) - 1))
        return TradeSignal(Signal.BUY, f"[ADAPTIVE {len(strong_buys)}x] {best.reason}", min(best.strength + boost, 0.95))
    elif len(strong_sells) >= 2:
        best = max(strong_sells, key=lambda s: s.strength)
        boost = min(0.10, 0.05 * (len(strong_sells) - 1))
        return TradeSignal(Signal.SELL, f"[ADAPTIVE {len(strong_sells)}x] {best.reason}", min(best.strength + boost, 0.95))

    # Single signal — use it if strong enough
    best = max(active, key=lambda s: s.strength)
    return best


def htf_confluence_pullback(df: pd.DataFrame, orderbook: dict = None, htf_df: pd.DataFrame = None) -> TradeSignal:
    """
    Trending market pullback with 1h confirmation.
    Requires ALL 5: HTF trend + VWAP gate + 5m pullback + RSI zone + volume.
    """
    if htf_df is None or len(htf_df) < 30:
        return TradeSignal(Signal.HOLD, "confluence_pullback: no HTF data", 0.0)
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "confluence_pullback: not enough 5m data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    htf = htf_df.iloc[-1]

    close = last["close"]
    rsi = last.get("rsi", 50)
    # Use last COMPLETED candle for volume (iloc[-1] is still forming, has partial volume)
    volume = prev["volume"]
    vol_avg = df["volume"].iloc[-21:-1].mean()
    vwap = last.get("vwap", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)

    # HTF indicators
    htf_adx = htf.get("adx", 0)
    htf_ema21 = htf.get("ema_21", 0)
    htf_ema50 = htf.get("ema_50", 0)
    htf_close = htf.get("close", 0)

    if htf_adx < 20:
        return TradeSignal(Signal.HOLD, f"confluence_pullback: 1h ADX {htf_adx:.1f} < 20", 0.0)

    # Volume gate — using completed candle vs 20-period avg of completed candles
    if vol_avg <= 0 or volume < vol_avg * 0.6:
        return TradeSignal(Signal.HOLD, f"confluence_pullback: vol {volume/max(vol_avg,1e-10):.2f}x < 0.6x", 0.0)

    if vwap <= 0 or pd.isna(vwap):
        return TradeSignal(Signal.HOLD, "confluence_pullback: no VWAP", 0.0)
    if ema_21 == 0 or ema_50 == 0:
        return TradeSignal(Signal.HOLD, "confluence_pullback: EMAs warming up", 0.0)

    direction = None

    # LONG setup
    htf_long = htf_ema21 > htf_ema50 and htf_close > htf_ema50 and htf_adx >= 20
    vwap_long = close > vwap
    pullback_to_ema = (abs(close - ema_21) / ema_21 < 0.005) or (abs(close - ema_50) / ema_50 < 0.005)
    bouncing = close > prev["close"]
    rsi_long = 35 <= rsi <= 60

    if htf_long and vwap_long and pullback_to_ema and bouncing and rsi_long:
        direction = Signal.BUY

    # SHORT setup
    htf_short = htf_ema21 < htf_ema50 and htf_close < htf_ema50 and htf_adx >= 20
    vwap_short = close < vwap
    dropping = close < prev["close"]
    rsi_short = 40 <= rsi <= 65

    if direction is None and htf_short and vwap_short and pullback_to_ema and dropping and rsi_short:
        direction = Signal.SELL

    # Momentum confirmation: last candle must show recovery in direction
    if direction is not None:
        last_close = df["close"].iloc[-1]
        last_open = df["open"].iloc[-1]
        prev_rsi = df["rsi"].iloc[-3] if len(df) > 3 else rsi

        if direction == Signal.BUY:
            momentum_ok = (last_close > last_open) or (rsi > prev_rsi)
        else:  # Signal.SELL
            momentum_ok = (last_close < last_open) or (rsi < prev_rsi)

        if not momentum_ok:
            side_str = "long" if direction == Signal.BUY else "short"
            _log.debug(
                f"confluence_pullback: {side_str} rejected — no momentum confirmation "
                f"(candle={'green' if last_close > last_open else 'red'}, "
                f"RSI {prev_rsi:.1f}→{rsi:.1f})"
            )
            direction = None

    if direction is None:
        # Diagnostic
        if not (htf_long or htf_short):
            detail = f"1h no trend (EMA21={'>' if htf_ema21>htf_ema50 else '<'}EMA50, close={'>' if htf_close>htf_ema50 else '<'}EMA50)"
        elif not (vwap_long or vwap_short):
            detail = f"VWAP mismatch (close={close:.2f} vwap={vwap:.2f})"
        elif not pullback_to_ema:
            dist21 = abs(close - ema_21) / ema_21 * 100
            dist50 = abs(close - ema_50) / ema_50 * 100
            detail = f"no pullback (EMA21 dist={dist21:.2f}% EMA50 dist={dist50:.2f}%)"
        elif not (bouncing or dropping):
            detail = "no candle confirmation"
        else:
            detail = f"RSI {rsi:.1f} out of range"
        return TradeSignal(Signal.HOLD, f"confluence_pullback: {detail}", 0.0)

    # Strength (0.84 base so shorts survive -0.04 penalty: 0.84-0.04=0.80 = gate)
    strength = 0.84
    stoch_k = last.get("stoch_k", 50)
    if htf_adx > 30:
        strength += 0.03
    if (direction == Signal.BUY and stoch_k < 30) or (direction == Signal.SELL and stoch_k > 70):
        strength += 0.03
    if volume > vol_avg * 2.0:
        strength += 0.03
    if orderbook:
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, "confluence_pullback: illiquid", 0.0)
        imb = orderbook.get("imbalance", 0)
        if direction == Signal.BUY and imb < -0.3:
            return TradeSignal(Signal.HOLD, f"confluence_pullback: OB blocks long ({imb:.2f})", 0.0)
        if direction == Signal.SELL and imb > 0.3:
            return TradeSignal(Signal.HOLD, f"confluence_pullback: OB blocks short ({imb:.2f})", 0.0)
        if (direction == Signal.BUY and imb > 0.15) or (direction == Signal.SELL and imb < -0.15):
            strength += 0.02

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    reason = (
        f"CONFLUENCE PULLBACK {dir_str} | 1h ADX={htf_adx:.1f} | VWAP={'>' if close>vwap else '<'}"
        f" | pullback to EMA | RSI={rsi:.1f} | vol={volume/max(vol_avg,1e-10):.1f}x"
    )
    return TradeSignal(direction, reason, min(strength, 0.92))


def htf_confluence_vwap(df: pd.DataFrame, orderbook: dict = None, htf_df: pd.DataFrame = None) -> TradeSignal:
    """
    Ranging market VWAP reversion with 1h confirmation.
    Requires ALL 4: HTF ranging + VWAP deviation + RSI extreme + candle reversal.
    """
    if htf_df is None or len(htf_df) < 30:
        return TradeSignal(Signal.HOLD, "confluence_vwap: no HTF data", 0.0)
    if len(df) < 30:
        return TradeSignal(Signal.HOLD, "confluence_vwap: not enough 5m data", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    htf = htf_df.iloc[-1]

    close = last["close"]
    rsi_fast = last.get("rsi_fast", last.get("rsi", 50))
    volume = last["volume"]
    vol_avg = df["volume"].iloc[-20:].mean()
    vwap = last.get("vwap", 0)

    # HTF ranging confirmation
    htf_adx = htf.get("adx", 25)
    if htf_adx >= 25:
        return TradeSignal(Signal.HOLD, f"confluence_vwap: 1h ADX {htf_adx:.1f} >= 25 (trending)", 0.0)

    if vwap <= 0 or pd.isna(vwap):
        return TradeSignal(Signal.HOLD, "confluence_vwap: no VWAP", 0.0)

    vwap_dist_pct = (close - vwap) / vwap * 100

    # Volume gate
    if vol_avg <= 0 or volume < vol_avg * 0.7:
        return TradeSignal(Signal.HOLD, f"confluence_vwap: vol {volume/max(vol_avg,1e-10):.2f}x < 0.7x", 0.0)

    direction = None

    # LONG: price below VWAP, oversold, bouncing
    if vwap_dist_pct < -0.4 and rsi_fast < 30 and close > prev["close"]:
        direction = Signal.BUY

    # SHORT: price above VWAP, overbought, dropping
    if direction is None and vwap_dist_pct > 0.4 and rsi_fast > 70 and close < prev["close"]:
        direction = Signal.SELL

    # Momentum confirmation for mean reversion: candle shows reversal
    if direction is not None:
        last_close = df["close"].iloc[-1]
        last_open = df["open"].iloc[-1]
        prev_rsi = df["rsi_fast"].iloc[-3] if len(df) > 3 else rsi_fast

        if direction == Signal.BUY:
            momentum_ok = (last_close > last_open) or (rsi_fast > prev_rsi)
        else:
            momentum_ok = (last_close < last_open) or (rsi_fast < prev_rsi)

        if not momentum_ok:
            side_str = "long" if direction == Signal.BUY else "short"
            _log.debug(
                f"confluence_vwap: {side_str} rejected — no reversal momentum "
                f"(candle={'green' if last_close > last_open else 'red'}, "
                f"RSI {prev_rsi:.1f}→{rsi_fast:.1f})"
            )
            direction = None

    if direction is None:
        if abs(vwap_dist_pct) < 0.4:
            detail = f"VWAP dist {vwap_dist_pct:+.2f}% < 0.40%"
        elif vwap_dist_pct < 0 and rsi_fast >= 30:
            detail = f"RSI(7) {rsi_fast:.1f} not oversold (<30)"
        elif vwap_dist_pct > 0 and rsi_fast <= 70:
            detail = f"RSI(7) {rsi_fast:.1f} not overbought (>70)"
        else:
            detail = f"no candle reversal (dist={vwap_dist_pct:+.2f}%)"
        return TradeSignal(Signal.HOLD, f"confluence_vwap: {detail}", 0.0)

    # Strength (0.84 base so shorts survive -0.04 penalty: 0.84-0.04=0.80 = gate)
    strength = 0.84
    if abs(vwap_dist_pct) > 0.7:
        strength += 0.03
    if (direction == Signal.BUY and rsi_fast < 20) or (direction == Signal.SELL and rsi_fast > 80):
        strength += 0.03
    if volume > vol_avg * 1.5:
        strength += 0.02
    if orderbook:
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, "confluence_vwap: illiquid", 0.0)
        imb = orderbook.get("imbalance", 0)
        if direction == Signal.BUY and imb < -0.3:
            return TradeSignal(Signal.HOLD, f"confluence_vwap: OB blocks long ({imb:.2f})", 0.0)
        if direction == Signal.SELL and imb > 0.3:
            return TradeSignal(Signal.HOLD, f"confluence_vwap: OB blocks short ({imb:.2f})", 0.0)
        if (direction == Signal.BUY and imb > 0.15) or (direction == Signal.SELL and imb < -0.15):
            strength += 0.02

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    reason = (
        f"CONFLUENCE VWAP {dir_str} | 1h ADX={htf_adx:.1f} (ranging)"
        f" | dist={vwap_dist_pct:+.2f}% | RSI(7)={rsi_fast:.1f}"
        f" | vol={volume/max(vol_avg,1e-10):.1f}x"
    )
    return TradeSignal(direction, reason, min(strength, 0.90))


def confluence_strategy(df: pd.DataFrame, orderbook: dict = None, htf_df: pd.DataFrame = None) -> TradeSignal:
    """
    Master router for v7.0 Confluence. Routes to HTF-confirmed strategies
    based on 1h ADX regime. Requires multi-timeframe data.
    """
    if len(df) < 30:
        return TradeSignal(Signal.HOLD, "Not enough data", 0.0)

    chop_val = df.iloc[-1].get("chop", 50)
    if chop_val > 65:
        return TradeSignal(Signal.HOLD, f"Choppy market (CHOP={chop_val:.1f})", 0.0)

    if htf_df is None or len(htf_df) < 30:
        return TradeSignal(Signal.HOLD, "No 1h HTF data — cannot trade without HTF context", 0.0)

    htf_adx = htf_df.iloc[-1].get("adx", 25)

    signals = []
    if htf_adx >= 20:
        signals.append(htf_confluence_pullback(df, orderbook, htf_df))
    if htf_adx >= 25:
        mom_signal = momentum_continuation_strategy(df, orderbook)
        if mom_signal.signal != Signal.HOLD:
            htf_ema21 = htf_df.iloc[-1].get("ema_21", 0)
            htf_ema50 = htf_df.iloc[-1].get("ema_50", 0)
            htf_close = htf_df.iloc[-1].get("close", 0)
            htf_agrees = (
                (mom_signal.signal == Signal.BUY and htf_close > htf_ema50) or
                (mom_signal.signal == Signal.SELL and htf_close < htf_ema50)
            )
            if htf_agrees and htf_ema21 != 0 and htf_ema50 != 0:
                signals.append(mom_signal)
                _log.debug(f"[CONFLUENCE] momentum_cont passed HTF guard (1h ADX={htf_adx:.1f})")
            else:
                _log.debug(f"[CONFLUENCE] momentum_cont blocked by HTF guard (1h EMA21={'>' if htf_ema21>htf_ema50 else '<'}EMA50)")
    if htf_adx < 25:
        signals.append(htf_confluence_vwap(df, orderbook, htf_df))

    # Log rejection reasons
    for s in signals:
        if s.signal == Signal.HOLD:
            _log.debug(f"[STRAT] {s.reason}")

    # Mean reversion in confirmed ranging conditions
    # Research: works at 2-30 min horizons when ADX < 25 AND Hurst < 0.50
    if htf_adx < 25:
        hurst_val = df.iloc[-1].get("hurst", 0.5) if "hurst" in df.columns else 0.5
        if hurst_val < 0.50:
            bb_signal = bb_mean_reversion_strategy(df, orderbook)
            if bb_signal.signal != Signal.HOLD:
                signals.append(bb_signal)

    # Pick strongest non-HOLD
    active = [s for s in signals if s.signal != Signal.HOLD]
    if not active:
        return TradeSignal(Signal.HOLD, f"No confluence signal (1h ADX={htf_adx:.1f})", 0.0)

    return max(active, key=lambda s: s.strength)


def htf_momentum_strategy(df, ob, htf_df=None):
    """1h momentum strategy — trend-following with pullback entry.
    Research: 1h is the only consistently positive Sharpe timeframe in WFO studies.
    Momentum dominates at 1h+ horizons (Rob Carver, AdaptiveTrend study).

    Entry: 4 core conditions (simple to avoid over-fitting):
    1. ADX > 25 (confirmed trend)
    2. EMA-21 > EMA-50 for longs (< for shorts)
    3. MACD histogram expanding
    4. Pullback to EMA-21 (within 0.5% of EMA-21)

    Optional boosters:
    - Volume > 1.2x → +0.05 strength
    """
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "Insufficient data", 0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Core indicators
    adx = last.get("adx", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)
    macd_hist = last.get("macd_hist", 0)
    prev_macd_hist = prev.get("macd_hist", 0)
    close = last.get("close", 0)
    volume = last.get("volume", 0)

    if not all([adx, ema_21, ema_50, close]):
        return TradeSignal(Signal.HOLD, "Missing indicators", 0)

    # Volume average (20-period)
    vol_avg = df["volume"].iloc[-20:].mean() if len(df) >= 20 else volume
    vol_ratio = volume / vol_avg if vol_avg > 0 else 0

    # Condition 1: ADX > 25 (confirmed trend)
    if adx <= 25:
        _log.debug(f"htf_momentum: ADX {adx:.1f} <= 25 — no trend")
        return TradeSignal(Signal.HOLD, f"htf_momentum: ADX {adx:.1f} too low", 0)

    # Condition 2: EMA alignment determines direction
    direction = None
    if ema_21 > ema_50:
        direction = Signal.BUY
    elif ema_21 < ema_50:
        direction = Signal.SELL
    else:
        return TradeSignal(Signal.HOLD, "htf_momentum: EMAs flat", 0)

    # Condition 3: MACD histogram expanding in direction
    if direction == Signal.BUY:
        macd_expanding = macd_hist > prev_macd_hist and macd_hist > 0
    else:
        macd_expanding = macd_hist < prev_macd_hist and macd_hist < 0

    if not macd_expanding:
        side_str = "long" if direction == Signal.BUY else "short"
        _log.debug(f"htf_momentum: {side_str} MACD not expanding (hist={macd_hist:.4f} prev={prev_macd_hist:.4f})")
        return TradeSignal(Signal.HOLD, "htf_momentum: MACD not expanding", 0)

    # Condition 4: Pullback to EMA-21 (within 0.5% of EMA-21)
    ema_distance_pct = abs(close - ema_21) / ema_21 * 100 if ema_21 > 0 else 999

    if direction == Signal.BUY:
        # Price should be near or slightly below EMA-21 (pullback)
        pullback = close <= ema_21 * 1.005  # within 0.5% above EMA-21
    else:
        # Price should be near or slightly above EMA-21
        pullback = close >= ema_21 * 0.995  # within 0.5% below EMA-21

    if not pullback:
        _log.debug(f"htf_momentum: price {ema_distance_pct:.2f}% from EMA-21 — too far for pullback entry")
        return TradeSignal(Signal.HOLD, f"htf_momentum: no pullback (dist={ema_distance_pct:.1f}%)", 0)

    # All 4 conditions met — calculate strength
    strength = 0.80

    # Volume booster
    if vol_ratio > 1.2:
        strength += 0.05

    # ADX strength bonus
    if adx > 35:
        strength += 0.03
    if adx > 45:
        strength += 0.02

    strength = min(strength, 0.95)

    side_str = "long" if direction == Signal.BUY else "short"
    reason = f"htf_momentum: {side_str} ADX={adx:.0f} MACD expanding vol={vol_ratio:.1f}x"

    return TradeSignal(direction, reason, strength)


def liquidation_cascade_strategy(df, ob, htf_df=None):
    """Liquidation cascade proxy strategy.
    Uses volume spike + strong momentum + extreme RSI as proxies for
    liquidation cascades in progress.

    Research: Liquidation cascades are structural — forced selling/buying
    accelerates price in the cascade direction. Oct 2025: $19B OI erased in 36h.

    Entry: Ride the cascade (momentum), not fade it.
    - Massive volume spike (>2.5x average) = liquidations happening
    - Strong directional candle (body > 70% of range)
    - RSI extreme (>75 or <25) = momentum, not reversal here
    - ADX > 30 = confirmed strong move
    """
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "Insufficient data", 0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = last.get("close", 0)
    open_price = last.get("open", 0)
    high = last.get("high", 0)
    low = last.get("low", 0)
    volume = last.get("volume", 0)
    rsi = last.get("rsi", 50)
    adx = last.get("adx", 0)

    if not all([close, open_price, high, low]):
        return TradeSignal(Signal.HOLD, "Missing data", 0)

    # Volume average (20-period)
    vol_avg = df["volume"].iloc[-20:].mean() if len(df) >= 20 else volume
    vol_ratio = volume / vol_avg if vol_avg > 0 else 0

    # Condition 1: Massive volume spike (liquidations in progress)
    if vol_ratio < 2.5:
        return TradeSignal(Signal.HOLD, f"liq_cascade: vol {vol_ratio:.1f}x < 2.5x", 0)

    # Condition 2: Strong directional candle (body > 70% of range)
    candle_range = high - low
    if candle_range == 0:
        return TradeSignal(Signal.HOLD, "liq_cascade: zero range candle", 0)
    body = abs(close - open_price)
    body_ratio = body / candle_range
    if body_ratio < 0.7:
        return TradeSignal(Signal.HOLD, f"liq_cascade: weak body {body_ratio:.0%}", 0)

    # Condition 3: ADX confirms strong move
    if adx < 30:
        return TradeSignal(Signal.HOLD, f"liq_cascade: ADX {adx:.0f} < 30", 0)

    # Direction: follow the cascade (momentum, not reversal)
    if close > open_price:
        direction = Signal.BUY  # Bullish cascade — shorts getting liquidated
    else:
        direction = Signal.SELL  # Bearish cascade — longs getting liquidated

    # Condition 4: RSI confirms momentum (NOT overbought/oversold reversal)
    if direction == Signal.BUY and rsi < 55:
        return TradeSignal(Signal.HOLD, f"liq_cascade: long but RSI {rsi:.0f} < 55", 0)
    if direction == Signal.SELL and rsi > 45:
        return TradeSignal(Signal.HOLD, f"liq_cascade: short but RSI {rsi:.0f} > 45", 0)

    # Strength based on volume intensity
    strength = 0.82
    if vol_ratio > 3.5:
        strength += 0.05
    if vol_ratio > 5.0:
        strength += 0.05
    if adx > 40:
        strength += 0.03
    strength = min(strength, 0.95)

    side_str = "long" if direction == Signal.BUY else "short"
    reason = f"liq_cascade: {side_str} vol={vol_ratio:.1f}x body={body_ratio:.0%} ADX={adx:.0f} RSI={rsi:.0f}"

    _log.debug(f"[SIGNAL] {reason} | strength={strength:.2f}")
    return TradeSignal(direction, reason, strength)


def funding_rate_contrarian_strategy(df, ob, htf_df=None):
    """Funding rate contrarian strategy.
    When funding is extremely positive → market is overleveraged long → short signal.
    When funding is extremely negative → overleveraged short → long signal.

    Research: Extreme funding preceded BTC Nov 2022 bottom, Mar 2020 crash bottom,
    and Oct 2025 $19B liquidation cascade.

    This strategy uses RSI and price position relative to EMA as confirmation.
    Funding rate data must be passed via the dataframe (added by bot.py).
    """
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "Insufficient data", 0)

    last = df.iloc[-1]

    close = last.get("close", 0)
    rsi = last.get("rsi", 50)
    ema_50 = last.get("ema_50", 0)

    # Funding rate — check if it's in the dataframe
    # Bot adds funding_rate to df via _fetch_funding_rate
    funding_rate = last.get("funding_rate", None)
    if funding_rate is None:
        # Try to get from the last few rows
        for i in range(-1, max(-5, -len(df)), -1):
            fr = df.iloc[i].get("funding_rate", None)
            if fr is not None:
                funding_rate = fr
                break

    if funding_rate is None or funding_rate == 0:
        return TradeSignal(Signal.HOLD, "funding_contrarian: no funding data", 0)

    # Extreme thresholds (per 8h funding period)
    # Normal: 0.01% (0.0001)
    # Elevated: >0.05% (0.0005)
    # Extreme: >0.1% (0.001)
    EXTREME_POSITIVE = 0.0008  # 0.08% — overleveraged longs
    EXTREME_NEGATIVE = -0.0005  # -0.05% — overleveraged shorts (rarer)

    direction = None

    if funding_rate >= EXTREME_POSITIVE:
        # Market overleveraged long → contrarian short
        direction = Signal.SELL
        # Confirmation: price should be extended above EMA (overextended)
        if close < ema_50:
            return TradeSignal(Signal.HOLD,
                f"funding_contrarian: extreme positive ({funding_rate*100:.3f}%) but price below EMA-50", 0)
    elif funding_rate <= EXTREME_NEGATIVE:
        # Market overleveraged short → contrarian long
        direction = Signal.BUY
        # Confirmation: price should be below EMA (oversold)
        if close > ema_50:
            return TradeSignal(Signal.HOLD,
                f"funding_contrarian: extreme negative ({funding_rate*100:.3f}%) but price above EMA-50", 0)
    else:
        return TradeSignal(Signal.HOLD,
            f"funding_contrarian: funding {funding_rate*100:.4f}% not extreme", 0)

    # RSI confirmation — should align with reversal
    if direction == Signal.BUY and rsi > 60:
        return TradeSignal(Signal.HOLD,
            f"funding_contrarian: long but RSI {rsi:.0f} > 60 (not oversold enough)", 0)
    if direction == Signal.SELL and rsi < 40:
        return TradeSignal(Signal.HOLD,
            f"funding_contrarian: short but RSI {rsi:.0f} < 40 (not overbought enough)", 0)

    # Strength based on funding extremity
    strength = 0.80
    if abs(funding_rate) >= 0.001:  # 0.1%
        strength += 0.05
    if abs(funding_rate) >= 0.002:  # 0.2%
        strength += 0.05
    strength = min(strength, 0.95)

    side_str = "long" if direction == Signal.BUY else "short"
    reason = f"funding_contrarian: {side_str} funding={funding_rate*100:.3f}% RSI={rsi:.0f}"

    _log.debug(f"[SIGNAL] {reason} | strength={strength:.2f}")
    return TradeSignal(direction, reason, strength)


def confluence_sma_vwap_strategy(df, orderbook=None, htf_df=None) -> TradeSignal:
    """Confluence strategy + 1H SMA(9)/SMA(15) trend direction gate.
    Uses HTF (1h) SMA structure for bias — allows pullbacks on 5m entry."""
    signal = confluence_strategy(df, orderbook, htf_df)
    if signal.signal == Signal.HOLD:
        return signal

    # Use 1H HTF data for SMA trend direction (not 5m)
    if htf_df is None or len(htf_df) < 20:
        return signal  # no HTF data, pass through

    # Compute 1h SMA9 and SMA15 on HTF candles
    htf_close = htf_df["close"]
    htf_sma9 = htf_close.rolling(9).mean().iloc[-1]
    htf_sma15 = htf_close.rolling(15).mean().iloc[-1]

    if htf_sma9 == 0 or htf_sma15 == 0:
        return signal

    # Trend direction gate: SMA9 vs SMA15 on 1h (no price > SMA9 requirement)
    if signal.signal == Signal.BUY:
        if not (htf_sma9 > htf_sma15):
            return TradeSignal(Signal.HOLD, f"SMA+VWAP gate: 1h SMA9 {htf_sma9:.2f} < SMA15 {htf_sma15:.2f}", 0.0)
    elif signal.signal == Signal.SELL:
        if not (htf_sma9 < htf_sma15):
            return TradeSignal(Signal.HOLD, f"SMA+VWAP gate: 1h SMA9 {htf_sma9:.2f} > SMA15 {htf_sma15:.2f}", 0.0)

    return TradeSignal(signal.signal, signal.reason + " +1hSMA", min(signal.strength + 0.03, 1.0))


STRATEGIES = {
    "trend_scalp":              trend_scalp_strategy,
    "trend_pullback":           trend_pullback_strategy,
    "bb_reversion":             bb_mean_reversion_strategy,
    "keltner_squeeze":          keltner_squeeze_strategy,
    "momentum_continuation":    momentum_continuation_strategy,
    "vwap_reversion":           vwap_reversion_strategy,
    "adaptive":                 adaptive_strategy,
    "confluence":               confluence_strategy,
    "confluence_sma_vwap":      confluence_sma_vwap_strategy,
    "htf_momentum":             htf_momentum_strategy,
    "liq_cascade":              liquidation_cascade_strategy,
    "funding_contrarian":       funding_rate_contrarian_strategy,
}
