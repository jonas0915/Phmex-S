"""EXPLORATORY ONLY (cross_asset lens, run 2026-09-25-2036). NOT the screen; numbers are not evidence.
long_1h TRAIN only. Per-symbol and per-half breakdown of NY-15:00 bar continuation (k=1.5)."""
import pandas as pd, numpy as np
from research.swarm.lib import load_data as ld
syms = ["BTC","ETH","SOL","XRP","DOGE","LINK","ADA","BNB","LTC","AAVE","SUI","UNI","XLM","NEAR","TAO","ONDO","1000PEPE","1000SHIB"]
allr = []
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    c, o = df["close"], df["open"]; r = np.log(c/o)
    ny = df.index.tz_convert("America/New_York")
    rr = r[(ny.hour == 15) & (ny.dayofweek < 5)]
    z = rr / rr.rolling(40, min_periods=20).std().shift(1)
    ev = z[z.abs() > 1.5].index
    for h in (3, 6):
        cont = (np.sign(z.reindex(ev)) * np.log(c.shift(-h)/c).reindex(ev) * 1e4).dropna()
        allr.append(pd.DataFrame({"sym": s, "h": h, "ts": cont.index, "cont": cont.values}))
t = pd.concat(allr)
print(t.groupby(["h","sym"]).cont.agg(["count","mean"]).round(1).unstack(0).to_string())
t["half"] = np.where(t.ts < pd.Timestamp("2025-12-10", tz="UTC"), "H1", "H2")
print(t.groupby(["h","half"]).cont.agg(["count","mean"]).round(1).to_string())
t["mon"] = t.ts.dt.strftime("%Y-%m")
print(t[t.h==3].groupby("mon").cont.agg(["count","mean"]).round(1).to_string())
