#!/usr/bin/env python3
"""
Liquidation-cascade reversion engine. No-lookahead, full-sample-first.

Cascade trigger on bar i (all gates use info available up to bar i):
  range[i]      > k * ATR[i-1]                  (extreme range vs trailing ATR)
  volume[i]     > m * avg_vol[i-1]              (volume spike -> forced-selling signature)
  |c-o|/range[i] > d                            (sharp directional close)
Direction = sign(close-open). DOWN cascade -> LONG (bounce). UP cascade -> SHORT (fade).
Entry at open[i+1]; time exit after H bars at open[i+1+H]; optional intrabar stop/tp.

The whole point: compare conditions
  A) BIGBAR only (k)            == the dead vol-fade
  B) BIGBAR + VOLUME (k,m)      == add forced-selling signature
  C) BIGBAR + VOLUME + DIRCLOSE (k,m,d) == full cascade fingerprint
If B/C don't beat A on full-sample sign + CI, this collapses to the dead vol-fade.
"""
import os, math
import numpy as np
import pandas as pd

DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DIR, "data")

def list_symbols(tf):
    out=[]
    for f in os.listdir(DATA):
        if f.endswith(f"_{tf}.csv"):
            out.append(f[:-(len(tf)+5)])
    return sorted(out)

def load(sym, tf):
    df = pd.read_csv(os.path.join(DATA, f"{sym}_{tf}.csv"))
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df["dt"] = pd.to_datetime(df.ts, unit="ms")
    return df

def wilder_atr(df, period=14):
    h,l,c = df.high.values, df.low.values, df.close.values
    pc = np.empty(len(c)); pc[0]=c[0]; pc[1:]=c[:-1]
    tr = np.maximum.reduce([h-l, np.abs(h-pc), np.abs(l-pc)])
    atr = np.full(len(tr), np.nan)
    if len(tr) <= period: return atr
    atr[period] = tr[1:period+1].mean()
    for i in range(period+1, len(tr)):
        atr[i] = (atr[i-1]*(period-1)+tr[i])/period
    return atr

def gen_signals(df, k, m, d, atr_period=14, vol_period=20):
    """Return trades. m=None disables volume gate, d=None disables dirclose gate.
       Direction-based: down cascade -> long(+1), up cascade -> short(-1)."""
    df = df.reset_index(drop=True)
    atr = wilder_atr(df, atr_period)
    o,h,l,c,v = df.open.values, df.high.values, df.low.values, df.close.values, df.volume.values
    rng = h-l
    # trailing avg volume up to i-1 (no lookahead): rolling mean shifted
    avgv = pd.Series(v).rolling(vol_period).mean().shift(1).values
    n=len(df); trades=[]
    start = max(atr_period+1, vol_period+1)
    for i in range(start, n):
        a = atr[i-1]
        if not np.isfinite(a) or a<=0: continue
        if rng[i] <= k*a: continue
        if m is not None:
            av = avgv[i]
            if not np.isfinite(av) or av<=0 or v[i] <= m*av: continue
        body = c[i]-o[i]
        if rng[i] <= 0: continue
        if d is not None and abs(body)/rng[i] <= d: continue
        bar_dir = np.sign(body)
        if bar_dir == 0: continue
        side = int(bar_dir)  # REVERSION: down bar(-1) -> long(+1)? -> side = -bar_dir
        side = int(-bar_dir)
        vr = v[i]/avgv[i] if (np.isfinite(avgv[i]) and avgv[i]>0) else np.nan
        trades.append({"trig_idx":i,"entry_idx":i+1,"dt":df.dt.iloc[i],
                       "side":side,"bar_dir":int(bar_dir),"ratio":rng[i]/a,
                       "volratio":vr,"bodyfrac":abs(body)/rng[i]})
    return trades, df

def realize(trades, df, hold, fee_oneway=0.00066, slip=0.0, stop=None, tp=None):
    o,h,l,c = df.open.values, df.high.values, df.low.values, df.close.values
    n=len(df); rows=[]
    for t in trades:
        ei=t["entry_idx"]; xi=ei+hold
        if xi>=n: continue
        entry=o[ei]; side=t["side"]; exit_px=o[xi]; reason="time"
        if stop is not None or tp is not None:
            for j in range(ei, xi):
                hi,lo=h[j],l[j]
                if side==1:
                    if stop is not None and lo<=entry*(1-stop): exit_px=entry*(1-stop); reason="stop"; break
                    if tp is not None and hi>=entry*(1+tp): exit_px=entry*(1+tp); reason="tp"; break
                else:
                    if stop is not None and hi>=entry*(1+stop): exit_px=entry*(1+stop); reason="stop"; break
                    if tp is not None and lo<=entry*(1-tp): exit_px=entry*(1-tp); reason="tp"; break
        gross = side*(exit_px-entry)/entry
        net = gross - (2*fee_oneway + 2*slip)
        rows.append({**t,"gross":gross,"net":net,"exit_reason":reason,
                     "month":pd.Timestamp(t["dt"]).strftime("%Y-%m")})
    return pd.DataFrame(rows)

def stats(pnl, col="net"):
    if len(pnl)==0: return {"n":0,"mean_pct":0,"total_pct":0,"wr":0,"sharpe":0,"median_pct":0}
    x=pnl[col].values; n=len(x); mean=x.mean(); sd=x.std(ddof=1) if n>1 else 0
    sharpe = mean/sd*math.sqrt(n) if sd>0 else 0
    return {"n":n,"mean_pct":mean*100,"total_pct":x.sum()*100,"wr":(x>0).mean()*100,
            "sharpe":sharpe,"median_pct":np.median(x)*100}

def bootstrap_ci(x, iters=2000, seed=42):
    if len(x)<5: return (float("nan"),float("nan"))
    rng=np.random.default_rng(seed)
    boot=np.array([rng.choice(x,len(x),replace=True).mean() for _ in range(iters)])*100
    return (np.percentile(boot,2.5), np.percentile(boot,97.5))

def build_all(symbols, tf, k, m, d, hold, fee=0.00066, slip=0.0, stop=None, tp=None,
              atr_period=14, vol_period=20):
    fr=[]
    for s in symbols:
        df=load(s,tf); tr,dff=gen_signals(df,k,m,d,atr_period,vol_period)
        p=realize(tr,dff,hold,fee,slip,stop,tp)
        if len(p): p["sym"]=s; fr.append(p)
    if not fr: return pd.DataFrame()
    return pd.concat(fr,ignore_index=True)

if __name__=="__main__":
    print("symbols 1h:", list_symbols("1h"))
    print("symbols 5m:", list_symbols("5m"))
