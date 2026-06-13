"""H2: Cross-sectional momentum. Each rebalance, rank universe by trailing return,
long top-k, short bottom-k, hold until next rebalance. Net of fee (entry+exit each leg).
Tested on 1h grid aligned to daily rebalance. Chronological split."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS, split_idx

def run(tf, lookback_bars, rebal_bars, k, dollar_neutral=True):
    data = load_all(tf)
    # build aligned close matrix on common timestamps
    idx = None
    for s in SYMBOLS:
        ts = data[s].set_index("timestamp")
        idx = ts.index if idx is None else idx.intersection(ts.index)
    idx = idx.sort_values()
    closes = pd.DataFrame({s: data[s].set_index("timestamp").reindex(idx)["close"] for s in SYMBOLS})
    opens  = pd.DataFrame({s: data[s].set_index("timestamp").reindex(idx)["open"]  for s in SYMBOLS})
    n = len(idx)
    sp = int(n*0.5)
    train_r, test_r = [], []
    i = lookback_bars
    while i + 1 + rebal_bars < n:
        trail = closes.iloc[i] / closes.iloc[i-lookback_bars] - 1
        trail = trail.dropna()
        if len(trail) < 2*k:
            i += rebal_bars; continue
        ranked = trail.sort_values()
        shorts = ranked.index[:k]
        longs = ranked.index[-k:]
        entry_o = opens.iloc[i+1]
        exit_o  = opens.iloc[i+1+rebal_bars]
        rets = []
        for s in longs:
            rets.append((exit_o[s]/entry_o[s]-1) - FEE_RT)
        for s in shorts:
            rets.append(-(exit_o[s]/entry_o[s]-1) - FEE_RT)
        port = np.mean(rets)
        if i+1 < sp: train_r.append(port)
        else: test_r.append(port)
        i += rebal_bars
    return train_r, test_r

def main():
    print("===== H2 CROSS-SECTIONAL MOMENTUM (long top-k / short bottom-k) =====")
    print("tf  lookback rebal  k | TRAIN | TEST")
    for tf in ["1h","4h"]:
        bpy = (365*24) if tf=="1h" else (365*6)
        if tf=="1h":
            grid = [(24,24,3),(48,24,3),(72,24,3),(168,24,3),(168,168,3),(24,12,2),(48,48,3),(168,168,2)]
        else:
            grid = [(6,6,3),(12,6,3),(18,6,3),(42,6,3),(42,42,3),(6,3,2),(12,12,3),(42,42,2)]
        for lb,rb,k in grid:
            tr,te = run(tf,lb,rb,k)
            st_tr = perf_stats(tr, bpy/rb); st_te = perf_stats(te, bpy/rb)
            print(f"{tf:>3} {lb:>5} {rb:>5} {k:>3} | {fmt(st_tr)} | {fmt(st_te)}")

if __name__=="__main__":
    main()
