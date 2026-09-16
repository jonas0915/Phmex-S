import pandas as pd, numpy as np, os
DATA_DIR = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_data"
for sym in ["BTC","ETH"]:
    df = pd.read_csv(os.path.join(DATA_DIR, f"{sym}_USDT_USDT_5m.csv"), parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    n_bars = len(df)
    span_days = (df["timestamp"].iloc[-1]-df["timestamp"].iloc[0]).total_seconds()/86400.0
    weeks = span_days/7.0
    high=df["high"]; low=df["low"]; close=df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high-low729:=high-low),(high-prev_close).abs(),(low-prev_close).abs()],axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    atr_p20 = atr14.rolling(500,min_periods=200).apply(lambda x: np.nanpercentile(x,20),raw=False)
    contraction_bar = atr14 <= atr_p20
    persist = contraction_bar.rolling(6).sum() >= 6
    range_high = high.rolling(24).max(); range_low = low.rolling(24).min()
    highs=high.values; lows=low.values; closes=close.values
    rh=range_high.values; rl=range_low.values
    idx = np.where(persist.fillna(False).values)[0]
    count=0; last=-100
    for i in idx:
        if i-last<=24: continue
        if i+9>=n_bars: continue
        brk_up = closes[i+1:i+4] > rh[i]
        brk_dn = closes[i+1:i+4] < rl[i]
        up_hits = np.where(brk_up)[0]; dn_hits = np.where(brk_dn)[0]
        broke=None
        if len(up_hits)>0: broke=("up", i+1+up_hits[0])
        elif len(dn_hits)>0: broke=("dn", i+1+dn_hits[0])
        if broke is None: continue
        direction,bidx = broke
        retest_end = min(bidx+6,n_bars)
        if direction=="up":
            level=rh[i]
            retest = (lows[bidx+1:retest_end] <= level*1.002) if bidx+1<retest_end else np.array([])
            hold = (closes[bidx+1:retest_end] > level) if bidx+1<retest_end else np.array([])
        else:
            level=rl[i]
            retest = (highs[bidx+1:retest_end] >= level*0.998) if bidx+1<retest_end else np.array([])
            hold = (closes[bidx+1:retest_end] < level) if bidx+1<retest_end else np.array([])
        if len(retest)>0 and retest.any() and hold.any():
            count+=1; last=bidx
    print(sym, "tightened sig3 (persist>=6) count:", count, "per_week:", round(count/weeks,3))
