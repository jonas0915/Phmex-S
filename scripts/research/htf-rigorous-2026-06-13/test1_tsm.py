#!/usr/bin/env python3
"""Family 1: Time-series momentum. Trailing N-day return sign predicts next
M-day return. Long if trailing>0, short if trailing<0. Non-overlapping holds
(step by M days) to keep trades independent. Pooled across symbols.

Sweep N in {1,2,3,5,7,14}, M in {1,2,3,5,7}. Evaluate each honestly."""
import numpy as np, pandas as pd
from engine import load, SYMBOLS, evaluate, print_res, verdict, tag_regime, btc_regime

def tsm_trades(N, M, symbols):
    trades = []
    reg = btc_regime("1d")
    for sym in symbols:
        df = load(sym, "1d")
        c = df["close"].values
        dts = df.index
        # require contiguous-ish: skip if big gaps handled by index step
        i = N
        while i + M < len(c):
            trail = c[i] / c[i-N] - 1.0
            if trail == 0:
                i += M; continue
            direction = 1 if trail > 0 else -1
            fwd = c[i+M] / c[i] - 1.0
            ret = direction * fwd
            edt = dts[i]
            # regime tag
            pos = reg.index.get_indexer([edt], method="ffill")[0]
            rg = reg.iloc[pos] if pos >= 0 else "na"
            trades.append({"ret": ret, "entry_dt": edt, "regime": rg, "symbol": sym})
            i += M  # non-overlapping
    return trades

def main():
    Ns = [1,2,3,5,7,14]; Ms = [1,2,3,5,7]
    results = []
    for N in Ns:
        for M in Ms:
            tr = tsm_trades(N, M, SYMBOLS)
            res = evaluate(tr, f"TSM N={N} M={M}")
            sv, _ = verdict(res)
            res["_sv"] = sv
            results.append(res)
    # rank by full-sample net base bps among those with n>=30
    results.sort(key=lambda r: (r.get("_sv",False), r["mean_base_bps"]), reverse=True)
    print("\n########## TSM SWEEP (ranked) ##########")
    for r in results:
        ci = r["ci_base_bps"]
        flag = "SURV" if r.get("_sv") else "    "
        print(f"[{flag}] {r['label']:14} n={r['n']:5} net@base {r['mean_base_bps']:6.1f}bps "
              f"CI[{ci[0]:6.1f},{ci[1]:6.1f}] stress {r['mean_stress_bps']:6.1f}bps "
              f"WR {r['win_rate']*100:4.1f}% wf {r['wf']['n_pos'] if r['wf'] else '-'}/{r['wf']['n_folds'] if r['wf'] else '-'}")
    print("\n########## DETAIL: top 4 by net ##########")
    for r in results[:4]:
        print_res(r)

if __name__ == "__main__":
    main()
