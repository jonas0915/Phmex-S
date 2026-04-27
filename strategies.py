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

    if htf_adx < 25:
        return TradeSignal(Signal.HOLD, f"confluence_pullback: 1h ADX {htf_adx:.1f} < 25", 0.0)

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
    if vol_avg <= 0 or volume < vol_avg * 0.5:
        return TradeSignal(Signal.HOLD, f"confluence_vwap: vol {volume/max(vol_avg,1e-10):.2f}x < 0.5x", 0.0)

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


def htf_l2_anticipation(
    df: pd.DataFrame,
    orderbook: dict = None,
    htf_df: pd.DataFrame = None,
    flow: dict = None,
) -> TradeSignal:
    """
    Pullback strategy that confirms entries via L2/tape signals instead of closed candle.
    Shares setup detection with htf_confluence_pullback — differs only in entry trigger.
    Requires flow dict from ws_feed. Returns HOLD if flow is None or trade_count < 5.
    """
    # Pre-checks (same as htf_confluence_pullback)
    if htf_df is None or len(htf_df) < 30:
        return TradeSignal(Signal.HOLD, "l2_anticipation: no HTF data", 0.0)
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "l2_anticipation: not enough 5m data", 0.0)
    if flow is None or flow.get("trade_count", 0) < 5:
        return TradeSignal(Signal.HOLD, "l2_anticipation: insufficient tape (flow absent or <5 trades)", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    htf = htf_df.iloc[-1]

    close = last["close"]
    rsi = last.get("rsi", 50)
    volume = prev["volume"]
    vol_avg = df["volume"].iloc[-21:-1].mean()
    vwap = last.get("vwap", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)

    htf_adx = htf.get("adx", 0)
    htf_ema21 = htf.get("ema_21", 0)
    htf_ema50 = htf.get("ema_50", 0)
    htf_close = htf.get("close", 0)

    if htf_adx < 25:
        return TradeSignal(Signal.HOLD, f"l2_anticipation: 1h ADX {htf_adx:.1f} < 25", 0.0)
    if vol_avg <= 0 or volume < vol_avg * 0.6:
        return TradeSignal(Signal.HOLD, f"l2_anticipation: vol {volume/max(vol_avg,1e-10):.2f}x < 0.6x", 0.0)
    if vwap <= 0 or pd.isna(vwap):
        return TradeSignal(Signal.HOLD, "l2_anticipation: no VWAP", 0.0)
    if ema_21 == 0 or ema_50 == 0:
        return TradeSignal(Signal.HOLD, "l2_anticipation: EMAs warming up", 0.0)

    direction = None

    # Setup detection (identical to htf_confluence_pullback minus bouncing/momentum)
    htf_long = htf_ema21 > htf_ema50 and htf_close > htf_ema50 and htf_adx >= 20
    vwap_long = close > vwap
    pullback_to_ema = (abs(close - ema_21) / ema_21 < 0.005) or (abs(close - ema_50) / ema_50 < 0.005)
    rsi_long = 35 <= rsi <= 60

    htf_short = htf_ema21 < htf_ema50 and htf_close < htf_ema50 and htf_adx >= 20
    vwap_short = close < vwap
    rsi_short = 40 <= rsi <= 65

    long_setup = htf_long and vwap_long and pullback_to_ema and rsi_long
    short_setup = htf_short and vwap_short and pullback_to_ema and rsi_short

    if not (long_setup or short_setup):
        if not (htf_long or htf_short):
            detail = "1h no trend"
        elif not (vwap_long or vwap_short):
            detail = f"VWAP mismatch (close={close:.4f} vwap={vwap:.4f})"
        elif not pullback_to_ema:
            dist21 = abs(close - ema_21) / ema_21 * 100
            dist50 = abs(close - ema_50) / ema_50 * 100
            detail = f"no pullback (EMA21 dist={dist21:.2f}% EMA50 dist={dist50:.2f}%)"
        else:
            detail = f"RSI {rsi:.1f} out of range"
        return TradeSignal(Signal.HOLD, f"l2_anticipation: {detail}", 0.0)

    # L2/tape confirmation (REPLACES bouncing + momentum confirmation)
    buy_ratio = flow.get("buy_ratio", 0.5)
    cvd_slope = flow.get("cvd_slope", 0.0)
    bid_depth = orderbook.get("bid_depth_usdt", 0) if orderbook else 0
    ask_depth = orderbook.get("ask_depth_usdt", 0) if orderbook else 0

    if long_setup:
        req1 = buy_ratio > 0.55
        req2 = cvd_slope > 0
        req3 = bid_depth > ask_depth
        if not (req1 and req2 and req3):
            reasons = []
            if not req1: reasons.append(f"buy_ratio {buy_ratio:.2f}<0.55")
            if not req2: reasons.append(f"cvd_slope {cvd_slope:.2f}<=0")
            if not req3: reasons.append(f"bid_depth {bid_depth:.0f}<=ask_depth {ask_depth:.0f}")
            return TradeSignal(Signal.HOLD, f"l2_anticipation: long L2 fail ({', '.join(reasons)})", 0.0)
        direction = Signal.BUY
    else:
        req1 = buy_ratio < 0.45
        req2 = cvd_slope < 0
        req3 = ask_depth > bid_depth
        if not (req1 and req2 and req3):
            reasons = []
            if not req1: reasons.append(f"buy_ratio {buy_ratio:.2f}>=0.45")
            if not req2: reasons.append(f"cvd_slope {cvd_slope:.2f}>=0")
            if not req3: reasons.append(f"ask_depth {ask_depth:.0f}<=bid_depth {bid_depth:.0f}")
            return TradeSignal(Signal.HOLD, f"l2_anticipation: short L2 fail ({', '.join(reasons)})", 0.0)
        direction = Signal.SELL

    # Strength calculation
    strength = 0.82

    # Booster 1: whale accumulation
    lt_bias = flow.get("large_trade_bias", 0.0)
    if direction == Signal.BUY and lt_bias > 0.2:
        strength += 0.03
    elif direction == Signal.SELL and lt_bias < -0.2:
        strength += 0.03

    # Booster 2: support/resistance wall within 1%
    price = close
    if orderbook:
        bid_walls = orderbook.get("bid_walls", []) or []
        ask_walls = orderbook.get("ask_walls", []) or []

        if direction == Signal.BUY and bid_walls:
            bid_dists = [(price - w[0]) / price * 100 for w in bid_walls if w[0] < price]
            if bid_dists:
                nearest = min(bid_dists)
                if 0 < nearest < 1.0:
                    strength += 0.02
        elif direction == Signal.SELL and ask_walls:
            ask_dists = [(w[0] - price) / price * 100 for w in ask_walls if w[0] > price]
            if ask_dists:
                nearest = min(ask_dists)
                if 0 < nearest < 1.0:
                    strength += 0.02

        # Booster 3: no adverse wall within 0.5%
        if direction == Signal.BUY:
            has_near_ask = any(0 < (w[0] - price) / price * 100 < 0.5 for w in ask_walls)
            if not has_near_ask:
                strength += 0.02
        else:
            has_near_bid = any(0 < (price - w[0]) / price * 100 < 0.5 for w in bid_walls)
            if not has_near_bid:
                strength += 0.02

        # OB imbalance gate (identical to htf_confluence_pullback)
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, "l2_anticipation: illiquid", 0.0)
        imb = orderbook.get("imbalance", 0)
        if direction == Signal.BUY and imb < -0.3:
            return TradeSignal(Signal.HOLD, f"l2_anticipation: OB blocks long ({imb:.2f})", 0.0)
        if direction == Signal.SELL and imb > 0.3:
            return TradeSignal(Signal.HOLD, f"l2_anticipation: OB blocks short ({imb:.2f})", 0.0)
        if (direction == Signal.BUY and imb > 0.15) or (direction == Signal.SELL and imb < -0.15):
            strength += 0.02

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    reason = (
        f"L2 ANTICIPATION {dir_str} | 1h ADX={htf_adx:.1f} | buy_ratio={buy_ratio:.2f}"
        f" | cvd_slope={cvd_slope:.2f} | bid/ask depth={bid_depth:.0f}/{ask_depth:.0f}"
        f" | RSI={rsi:.1f}"
    )
    return TradeSignal(direction, reason, min(strength, 0.92))


def confluence_strategy(df: pd.DataFrame, orderbook: dict = None, htf_df: pd.DataFrame = None, flow: dict = None) -> TradeSignal:
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
        signals.append(htf_l2_anticipation(df, orderbook, htf_df, flow))
    # CULLED 2026-04-26 (Option A): momentum_continuation -$0.40/trade net, n=11/30d
    # if htf_adx >= 25:
    #     mom_signal = momentum_continuation_strategy(df, orderbook)
    #     if mom_signal.signal != Signal.HOLD:
    #         htf_ema21 = htf_df.iloc[-1].get("ema_21", 0)
    #         htf_ema50 = htf_df.iloc[-1].get("ema_50", 0)
    #         htf_close = htf_df.iloc[-1].get("close", 0)
    #         htf_agrees = (
    #             (mom_signal.signal == Signal.BUY and htf_close > htf_ema50) or
    #             (mom_signal.signal == Signal.SELL and htf_close < htf_ema50)
    #         )
    #         if htf_agrees and htf_ema21 != 0 and htf_ema50 != 0:
    #             signals.append(mom_signal)
    #             _log.debug(f"[CONFLUENCE] momentum_cont passed HTF guard (1h ADX={htf_adx:.1f})")
    #         else:
    #             _log.debug(f"[CONFLUENCE] momentum_cont blocked by HTF guard (1h EMA21={'>' if htf_ema21>htf_ema50 else '<'}EMA50)")
    # CULLED 2026-04-26 (Option A): htf_confluence_vwap -$0.10/trade net, n=5/30d
    # if htf_adx < 25:
    #     signals.append(htf_confluence_vwap(df, orderbook, htf_df))

    # Log rejection reasons
    for s in signals:
        if s.signal == Signal.HOLD:
            _log.debug(f"[STRAT] {s.reason}")

    # CULLED 2026-04-26 (Option A): bb_mean_reversion 0 trades 30d (effectively dead)
    # Lessons.md note: "entered longs during downtrends (falling knives), 6 consecutive
    # losing longs -$3.73" — disabling here reinforces that lesson
    # if htf_adx < 25:
    #     hurst_val = df.iloc[-1].get("hurst", 0.5) if "hurst" in df.columns else 0.5
    #     if hurst_val < 0.50:
    #         bb_signal = bb_mean_reversion_strategy(df, orderbook)
    #         if bb_signal.signal != Signal.HOLD:
    #             signals.append(bb_signal)

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


STRATEGIES = {
    "bb_mean_reversion":        bb_mean_reversion_strategy,
    "momentum_continuation":    momentum_continuation_strategy,
    "confluence":               confluence_strategy,
    "htf_momentum":             htf_momentum_strategy,
    "liq_cascade":              liquidation_cascade_strategy,
    "htf_l2_anticipation":      htf_l2_anticipation,
}
