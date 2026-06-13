"""H1: Time-series momentum. If trailing N-bar return > 0 (long) / < 0 (short),
enter at next bar open, hold M bars, exit at open. Net of fee. Pooled across symbols.
Non-overlapping trades (step = M) to keep samples independent."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS, split_idx

def run_combo(data, lookback, hold, tf, long_short=True):
    """Returns (train_rets, test_rets) lists of net per-trade returns."""
    train_r, test_r = [], []
    bars_per_year = (365*24) if tf=="1h" else (365*6)
    for s in SYMBOLS:
        df = data[s]
        o = df["open"].values
        c = df["close"].values
        n = len(df)
        sp = split_idx(df, 0.5)
        # signal at bar i uses close[i-lookback..i]; enter at open[i+1]; exit at open[i+1+hold]
        i = lookback
        while i + 1 + hold < n:
            trail = c[i] / c[i-lookback] - 1
            if trail == 0:
                i += hold; continue
            direction = 1 if trail > 0 else (-1 if long_short else 0)
            if direction == 0:
                i += hold; continue
            entry = o[i+1]
            exit_ = o[i+1+hold]
            gross = direction * (exit_/entry - 1)
            net = gross - FEE_RT
            # classify by entry bar position
            if i+1 < sp:
                train_r.append(net)
            else:
                test_r.append(net)
            i += hold  # non-overlapping
    return train_r, test_r

def main():
    for tf in ["1h","4h"]:
        data = load_all(tf)
        bpy = (365*24) if tf=="1h" else (365*6)
        print(f"\n===== {tf} TIME-SERIES MOMENTUM (long/short, non-overlapping) =====")
        print(f"{'LB':>4}{'HOLD':>5} | TRAIN {'':22} | TEST")
        results = []
        if tf=="1h":
            lbs = [6,12,24,48,72,168]   # 6h..7d
            holds = [6,12,24,48]
        else:
            lbs = [3,6,12,24,42]        # 12h..7d
            holds = [3,6,12,24]
        for lb in lbs:
            for hd in holds:
                tr, te = run_combo(data, lb, hd, tf)
                st_tr = perf_stats(tr, bpy/hd)
                st_te = perf_stats(te, bpy/hd)
                results.append((lb,hd,st_tr,st_te))
                print(f"{lb:>4}{hd:>5} | {fmt(st_tr)} | {fmt(st_te)}")
        # best by test mean among those with train mean>0
        valid = [r for r in results if r[2]['mean']>0 and r[2]['n']>=30]
        valid.sort(key=lambda r: r[3]['mean'], reverse=True)
        print(f"  Top by TEST mean (train-positive): ", end="")
        if valid:
            lb,hd,st,te = valid[0]
            print(f"lb={lb} hold={hd}: test {fmt(te)}")
        else:
            print("none train-positive")

if __name__=="__main__":
    main()
