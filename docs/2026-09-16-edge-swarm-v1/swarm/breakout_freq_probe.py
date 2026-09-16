import pandas as pd
import numpy as np
import glob, os

DATA_DIR = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_data"
symbols = ["BTC", "ETH", "SOL", "XRP", "BNB"]

def load(sym):
    path = os.path.join(DATA_DIR, f"{sym}_USDT_USDT_5m.csv")
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

results = {}

for sym in symbols:
    df = load(sym)
    n_bars = len(df)
    span_days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds() / 86400.0
    weeks = span_days / 7.0

    # --- Idea 1: Bollinger squeeze -> breakout continuation ---
    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    bw = (upper - lower) / sma20
    bw_pct = bw.rolling(500, min_periods=200).apply(lambda x: (x.iloc[-1] <= np.nanpercentile(x, 10)), raw=False)
    vol_avg20 = df["volume"].rolling(20).mean()
    squeeze = bw_pct.fillna(0).astype(bool)
    breakout_up = (df["close"] > upper) & (df["volume"] > 1.5 * vol_avg20)
    breakout_dn = (df["close"] < lower) & (df["volume"] > 1.5 * vol_avg20)
    breakout_any = breakout_up | breakout_dn

    # signal = squeeze bar followed within next 3 bars by a breakout bar
    sig1_idx = []
    squeeze_idx = np.where(squeeze.values)[0]
    breakout_arr = breakout_any.values
    last_signal_bar = -100
    for i in squeeze_idx:
        window_end = min(i + 4, n_bars)
        hit = np.where(breakout_arr[i:window_end])[0]
        if len(hit) > 0:
            bar = i + hit[0]
            if bar - last_signal_bar > 12:  # de-dupe within 1h
                sig1_idx.append(bar)
                last_signal_bar = bar
    sig1_count = len(sig1_idx)

    # --- Idea 2: funding-anchor opening range breakout (00:00/08:00/16:00 UTC) ---
    ts = df["timestamp"]
    hour = ts.dt.hour
    minute = ts.dt.minute
    anchor_mask = hour.isin([0, 8, 16]) & (minute == 0)
    anchor_idx = np.where(anchor_mask.values)[0]
    sig2_count = 0
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    for i in anchor_idx:
        if i + 15 >= n_bars:
            continue
        or_high = highs[i:i+3].max()
        or_low = lows[i:i+3].min()
        or_height = or_high - or_low
        if or_height <= 0:
            continue
        window = closes[i+3:i+15]
        broke_up = np.where(window > or_high)[0]
        broke_dn = np.where(window < or_low)[0]
        if len(broke_up) > 0 or len(broke_dn) > 0:
            sig2_count += 1

    # --- Idea 3: ATR contraction + N-bar range breakout + retest confirm ---
    high = df["high"]; low = df["low"]; close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    atr_pct = atr14.rolling(500, min_periods=200).apply(lambda x: (x.iloc[-1] <= np.nanpercentile(x, 20)), raw=False).fillna(0).astype(bool)
    range_high = high.rolling(24).max()
    range_low = low.rolling(24).min()

    sig3_count = 0
    last_sig3 = -100
    contraction_idx = np.where(atr_pct.values)[0]
    rh = range_high.values; rl = range_low.values
    for i in contraction_idx:
        if i - last_sig3 <= 24:
            continue
        if i + 9 >= n_bars:
            continue
        brk_up = closes[i+1:i+4] > rh[i]
        brk_dn = closes[i+1:i+4] < rl[i]
        up_hits = np.where(brk_up)[0]
        dn_hits = np.where(brk_dn)[0]
        broke = None
        if len(up_hits) > 0:
            broke = ("up", i + 1 + up_hits[0])
        elif len(dn_hits) > 0:
            broke = ("dn", i + 1 + dn_hits[0])
        if broke is None:
            continue
        direction, bidx = broke
        retest_end = min(bidx + 6, n_bars)
        if direction == "up":
            level = rh[i]
            retest = (lows[bidx+1:retest_end] <= level * 1.002) if bidx+1 < retest_end else np.array([])
            hold = (closes[bidx+1:retest_end] > level) if bidx+1 < retest_end else np.array([])
        else:
            level = rl[i]
            retest = (highs[bidx+1:retest_end] >= level * 0.998) if bidx+1 < retest_end else np.array([])
            hold = (closes[bidx+1:retest_end] < level) if bidx+1 < retest_end else np.array([])
        if len(retest) > 0 and retest.any() and hold.any():
            sig3_count += 1
            last_sig3 = bidx

    results[sym] = dict(
        n_bars=n_bars, span_days=round(span_days, 1), weeks=round(weeks, 2),
        sig1_squeeze_breakout=sig1_count, sig1_per_week=round(sig1_count / weeks, 3),
        sig2_or_breakout=sig2_count, sig2_per_week=round(sig2_count / weeks, 3),
        sig3_contraction_retest=sig3_count, sig3_per_week=round(sig3_count / weeks, 3),
    )

for sym, r in results.items():
    print(sym, r)
