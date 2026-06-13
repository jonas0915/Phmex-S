#!/usr/bin/env python3
"""
INDEPENDENT re-derivation of the '1h Volatility-Expansion FADE' edge.
Built from scratch. No reuse of prior agent code.

Signal: on bar i, range = high-low. ATR = Wilder ATR(period) computed up to bar i (no lookahead).
If range[i] > k * ATR[i-1]  (use prior-bar ATR to avoid the trigger bar contaminating its own ATR):
   direction of bar = sign(close[i]-open[i]).
   FADE: if bar up -> SHORT; if bar down -> LONG.
   Enter at open[i+1]. Hold H bars. Exit at open[i+1+H] (time exit).
Return per trade computed on raw price move, sign-adjusted, minus costs.
"""
import os, json, math
import numpy as np
import pandas as pd

DIR = os.path.dirname(os.path.abspath(__file__))
SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC","TRX","DOT","NEAR","ATOM"]

def load(sym):
    df = pd.read_csv(os.path.join(DIR, f"ohlcv_{sym}.csv"))
    df["dt"] = pd.to_datetime(df.ts, unit="ms")
    return df

def wilder_atr(df, period=14):
    h, l, c = df.high.values, df.low.values, df.close.values
    pc = np.empty(len(c)); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum.reduce([h-l, np.abs(h-pc), np.abs(l-pc)])
    atr = np.full(len(tr), np.nan)
    if len(tr) <= period: return atr
    atr[period] = tr[1:period+1].mean()
    for i in range(period+1, len(tr)):
        atr[i] = (atr[i-1]*(period-1) + tr[i]) / period
    return atr

def gen_signals(df, k, atr_period=14):
    """Return list of trades (dicts) with no cost applied yet."""
    df = df.reset_index(drop=True)
    atr = wilder_atr(df, atr_period)
    o, h, l, c = df.open.values, df.high.values, df.low.values, df.close.values
    rng = h - l
    trades = []
    n = len(df)
    for i in range(atr_period+1, n):
        a = atr[i-1]  # prior-bar ATR, no lookahead
        if not np.isfinite(a) or a <= 0: continue
        if rng[i] > k * a:
            bar_dir = np.sign(c[i] - o[i])
            if bar_dir == 0: continue
            side = -bar_dir  # fade
            trades.append({
                "trig_idx": i,
                "entry_idx": i+1,
                "dt": df.dt.iloc[i],
                "side": int(side),         # +1 long, -1 short
                "bar_dir": int(bar_dir),   # +1 up bar, -1 down bar
                "atr": a, "range": rng[i],
                "ratio": rng[i]/a,
            })
    return trades, df

def realize(trades, df, hold, fee_oneway=0.00066, slip=0.0, stop=None, tp=None):
    """Apply time exit (+ optional intrabar stop/tp) and costs. Returns DataFrame of trade pnl."""
    o, h, l, c = df.open.values, df.high.values, df.low.values, df.close.values
    n = len(df)
    rows = []
    for t in trades:
        ei = t["entry_idx"]
        xi = ei + hold
        if xi >= n: continue
        entry = o[ei]
        side = t["side"]
        exit_px = o[xi]
        exit_reason = "time"
        # intrabar stop/tp scan over hold window (bars ei..xi-1), conservative: stop checked before tp
        if stop is not None or tp is not None:
            for j in range(ei, xi):
                hi, lo = h[j], l[j]
                if side == 1:  # long
                    if stop is not None and lo <= entry*(1-stop):
                        exit_px = entry*(1-stop); exit_reason="stop"; break
                    if tp is not None and hi >= entry*(1+tp):
                        exit_px = entry*(1+tp); exit_reason="tp"; break
                else:  # short
                    if stop is not None and hi >= entry*(1+stop):
                        exit_px = entry*(1+stop); exit_reason="stop"; break
                    if tp is not None and lo <= entry*(1-tp):
                        exit_px = entry*(1-tp); exit_reason="tp"; break
        gross = side * (exit_px - entry) / entry
        cost = 2*fee_oneway + 2*slip
        net = gross - cost
        rows.append({**t, "gross":gross, "net":net, "exit_reason":exit_reason,
                     "month": pd.Timestamp(t["dt"]).strftime("%Y-%m")})
    return pd.DataFrame(rows)

def stats(pnl, col="net"):
    if len(pnl)==0: return {"n":0}
    x = pnl[col].values
    n=len(x); mean=x.mean(); sd=x.std(ddof=1) if n>1 else 0
    sharpe = mean/sd*math.sqrt(n) if sd>0 else 0  # per-trade-aggregate sharpe (sqrt N)
    wr = (x>0).mean()
    return {"n":n, "mean_pct":mean*100, "total_pct":x.sum()*100, "wr":wr*100,
            "sharpe":sharpe, "median_pct":np.median(x)*100}

if __name__=="__main__":
    print("loaded engine")
