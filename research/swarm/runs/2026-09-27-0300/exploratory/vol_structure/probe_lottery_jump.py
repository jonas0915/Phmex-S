"""EXPLORATORY probe (not the screen, not evidence). long_1h TRAIN era only.
Time-series lottery (MAX / positive-jump) fade: short an alt perp one day after an
extreme upside 24h move. Compares vs unconditional 00UTC short baseline."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen, fee_math as fm, bootstrap_ci as bc

SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]

def sig_jump(df, k=3.0, floor=0.08, look=60):
    c = df["close"]
    r24 = np.log(c / c.shift(24))
    daily = r24[df.index.hour == 0]
    sd = daily.rolling(look, min_periods=30).std().shift(1)
    jump = (daily >= k * sd) & (daily >= floor)
    fire = jump.shift(1, fill_value=False)  # skip one day
    out = pd.Series(0, index=df.index)
    out.loc[fire[fire].index] = -1
    return out

def sig_base(df):
    out = pd.Series(0, index=df.index)
    out[df.index.hour == 0] = -1
    return out

def run(fn, tp, sl, hold, label):
    allt = []
    for s in SYMS:
        df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        t = screen.simulate(df, fn(df), tp, sl, hold)
        t["sym"] = s
        allt.append(t)
    t = pd.concat(allt)
    if len(t) < 2:
        print(label, "n", len(t)); return t
    lo, hi = bc.mean_ci(t.net_bps.values)
    wr = (t.net_bps > 0).mean()
    print(f"{label}: n={len(t)} mean_net={t.net_bps.mean():.2f} ci=[{lo:.2f},{hi:.2f}] WR={wr:.3f} p*={fm.p_star(tp):.4f} span={t.entry_ts.min()}..{t.entry_ts.max()}")
    return t

if __name__ == "__main__":
    df = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
    print("BTC train span", df.index.min(), df.index.max(), len(df))
    for k, fl in [(3.0, 0.08), (2.5, 0.06), (2.0, 0.05)]:
        t = run(lambda d: sig_jump(d, k, fl), 300, 300, 168, f"jump k={k} floor={fl} tp300/sl300/h168")
        if len(t): print(t.groupby("sym").size().to_dict()); print(t.exit_reason.value_counts().to_dict())
    run(sig_base, 300, 300, 168, "BASELINE unconditional 00UTC short tp300/sl300/h168")
