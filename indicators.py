import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = sma(series, period)
    std = series.rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 14, d_period: int = 3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = sma(k, d_period)
    return k, d


def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    return sma(volume, period)


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Session-anchored VWAP — resets at midnight UTC each day."""
    typical_price = (high + low + close) / 3
    df_temp = pd.DataFrame({
        "tp": typical_price,
        "vol": volume,
        "date": typical_price.index.normalize()  # midnight UTC date for each candle
    })
    tpv = df_temp["tp"] * df_temp["vol"]
    # Cumulative sum within each day group
    cum_tpv = tpv.groupby(df_temp["date"]).cumsum()
    cum_vol = df_temp["vol"].groupby(df_temp["date"]).cumsum()
    return cum_tpv / cum_vol.replace(0, float("nan"))


def adx(high, low, close, period=14):
    plus_dm_raw = high.diff().clip(lower=0)
    minus_dm_raw = (-low.diff()).clip(lower=0)
    # Compare originals before zeroing to avoid sequential modification bug
    plus_dm = plus_dm_raw.copy()
    minus_dm = minus_dm_raw.copy()
    plus_dm[plus_dm_raw <= minus_dm_raw] = 0
    minus_dm[minus_dm_raw <= plus_dm_raw] = 0
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr_smooth = tr.ewm(com=period-1, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(com=period-1, adjust=False).mean() / atr_smooth
    minus_di = 100 * minus_dm.ewm(com=period-1, adjust=False).mean() / atr_smooth
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(com=period-1, adjust=False).mean()
    return adx_val, plus_di, minus_di


def choppiness_index(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr_sum = tr.rolling(period).sum()
    high_max = high.rolling(period).max()
    low_min = low.rolling(period).min()
    hl_range = (high_max - low_min).replace(0, np.nan)
    chop = 100 * np.log10(atr_sum / hl_range) / np.log10(period)
    return chop


def efficiency_ratio(close, period=10):
    """Kaufman Efficiency Ratio: 0=choppy, 1=trending."""
    direction = (close - close.shift(period)).abs()
    volatility = close.diff().abs().rolling(period).sum()
    return direction / volatility.replace(0, np.nan)


def atr_fast(high, low, close, period=7):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period-1, min_periods=period, adjust=False).mean()


def obv(close, volume):
    direction = np.sign(close.diff())
    return (direction * volume).cumsum()


def keltner_channels(close, high, low, atr_series, ema_period=21, atr_mult=1.5):
    ema_line = close.ewm(span=ema_period, adjust=False).mean()
    upper = ema_line + atr_mult * atr_series
    lower = ema_line - atr_mult * atr_series
    return upper, lower


def bb_squeeze(bb_upper, bb_lower, kc_upper, kc_lower):
    return (bb_upper < kc_upper) & (bb_lower > kc_lower)


def atr_percentile(atr_series, lookback=100):
    return atr_series.rolling(lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    )


def hurst_exponent(close, window=100):
    """Hurst exponent via R/S method (pure numpy for performance).
    H > 0.55 = trending, H < 0.45 = mean-reverting, 0.45-0.55 = random walk."""
    arr = close.values.astype(float)
    result = np.full(len(arr), np.nan)

    for idx in range(window - 1, len(arr)):
        x = arr[idx - window + 1:idx + 1]
        x = x[~np.isnan(x)]
        n = len(x)
        if n < 20:
            continue
        rs_list, ns_list = [], []
        for div in [2, 4, 8, 16]:
            sub_len = n // div
            if sub_len < 8:
                continue
            rs_vals = []
            for i in range(div):
                sub = x[i * sub_len:(i + 1) * sub_len]
                mean = sub.mean()
                cumdev = np.cumsum(sub - mean)
                R = cumdev.max() - cumdev.min()
                S = sub.std(ddof=1)
                if S > 0 and R > 0:
                    rs_vals.append(R / S)
            if rs_vals:
                rs_list.append(np.log(np.mean(rs_vals)))
                ns_list.append(np.log(sub_len))
        if len(rs_list) >= 2:
            coeffs = np.polyfit(ns_list, rs_list, 1)
            result[idx] = coeffs[0]

    return pd.Series(result, index=close.index)


def compute_sr_levels(df, pivot_bars=10, lookback=150):
    """Return nearest resistance above and support below current price.
    Uses rolling swing pivots + VWAP as dynamic S/R."""
    recent = df.iloc[-lookback:] if len(df) >= lookback else df
    highs, lows = [], []
    for i in range(pivot_bars, len(recent) - pivot_bars):
        window = recent.iloc[i - pivot_bars:i + pivot_bars + 1]
        if recent.iloc[i]["high"] == window["high"].max():
            highs.append(float(recent.iloc[i]["high"]))
        if recent.iloc[i]["low"] == window["low"].min():
            lows.append(float(recent.iloc[i]["low"]))
    close = float(df.iloc[-1]["close"])
    vwap_val = float(df.iloc[-1].get("vwap", 0))
    if vwap_val > 0:
        if vwap_val > close:
            highs.append(vwap_val)
        else:
            lows.append(vwap_val)
    resistance = min((h for h in highs if h > close), default=None)
    support = max((l for l in lows if l < close), default=None)
    return resistance, support


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Trend EMAs
    df["ema_9"] = ema(close, 9)
    df["ema_21"] = ema(close, 21)
    df["ema_50"] = ema(close, 50)
    df["ema_200"] = ema(close, 200)

    # SMAs for test & retest strategy
    df["sma_9"] = sma(close, 9)
    df["sma_15"] = sma(close, 15)

    # VWAP (session-anchored, resets daily at midnight UTC)
    df["vwap"] = vwap(high, low, close, volume)

    # Momentum
    df["rsi"] = rsi(close, 14)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(close)

    # Volatility
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(close)
    df["atr"] = atr(high, low, close)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # Stochastic
    df["stoch_k"], df["stoch_d"] = stochastic(high, low, close)

    # Volume
    df["volume_sma"] = volume_sma(volume)
    df["volume_ratio"] = volume / df["volume_sma"]

    # Fast indicators for scalping
    df["atr_fast"] = atr_fast(high, low, close)
    df["rsi_fast"] = rsi(close, period=7)

    # ADX for trend strength
    df["adx"], df["plus_di"], df["minus_di"] = adx(high, low, close)

    # Choppiness Index
    df["chop"] = choppiness_index(high, low, close)

    # Kaufman Efficiency Ratio (logging only — not used for gating)
    df["er"] = efficiency_ratio(close)

    # OBV
    df["obv"] = obv(close, volume)

    # Keltner Channels
    kc_upper, kc_lower = keltner_channels(close, high, low, df["atr"])
    df["kc_upper"] = kc_upper
    df["kc_lower"] = kc_lower

    # BB Squeeze
    df["squeeze"] = bb_squeeze(df["bb_upper"], df["bb_lower"], df["kc_upper"], df["kc_lower"])

    # Volatility regime
    df["atr_pct"] = atr_percentile(df["atr"])

    # Hurst exponent for regime detection
    df["hurst"] = hurst_exponent(close)

    # Only drop rows where core signal indicators are NaN (not all 30+ columns).
    # EMA-200 is the slowest warmup; once it's valid, everything else is too.
    # This preserves ~300 rows instead of blanket dropna() losing 60-100 rows.
    core_cols = ["ema_200", "rsi", "macd", "atr", "adx"]
    existing = [c for c in core_cols if c in df.columns]
    return df.dropna(subset=existing)
