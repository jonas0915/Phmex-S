"""Shared utils for higher-TF research. Net fee = 0.066% round-trip."""
import os, glob
import numpy as np
import pandas as pd

DATA = os.path.dirname(os.path.abspath(__file__)) + "/data"
FEE_RT = 0.00066  # 0.066% round trip (taker both sides)
SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC"]

def load(symbol, tf):
    df = pd.read_csv(f"{DATA}/{symbol}_{tf}.csv", parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

def load_all(tf):
    out = {}
    for s in SYMBOLS:
        out[s] = load(s, tf)
    return out

def split_idx(df, frac=0.5):
    """Chronological split point index."""
    return int(len(df) * frac)

def perf_stats(rets, bars_per_year, label=""):
    """rets = per-trade net returns (decimal). Returns dict of stats."""
    rets = np.asarray(rets, dtype=float)
    n = len(rets)
    if n == 0:
        return dict(n=0, mean=0, wr=0, sharpe=0, total=0, ann=0)
    mean = rets.mean()
    wr = (rets > 0).mean()
    sd = rets.std(ddof=1) if n > 1 else 0.0
    sharpe = (mean / sd * np.sqrt(bars_per_year)) if sd > 0 else 0.0
    total = np.prod(1 + rets) - 1
    return dict(n=n, mean=mean, wr=wr, sharpe=sharpe, total=total, sd=sd)

def fmt(d):
    return (f"n={d['n']:>4} mean={d['mean']*100:+.3f}% wr={d['wr']*100:4.1f}% "
            f"sharpe={d['sharpe']:+.2f} total={d['total']*100:+.1f}%")
