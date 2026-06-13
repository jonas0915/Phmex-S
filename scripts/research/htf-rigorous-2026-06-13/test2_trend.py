#!/usr/bin/env python3
"""Family 2: Trend-following. MA crossovers (10/30, 20/50, 50/200) and
Donchian breakout (20, 55). Position held while trend persists; trade = each
completed in->out leg. Long and short. Pooled across symbols."""
import numpy as np, pandas as pd
from engine import load, SYMBOLS, evaluate, print_res, verdict, btc_regime

def legs_from_signal(df, sig):
    """sig: Series of +1/-1/0 desired position (already shifted to be tradable
    next bar). Returns list of trade dicts (entry->exit at each position change)."""
    reg = btc_regime("1d")
    c = df["close"].values
    s = sig.values
    dts = df.index
    trades = []
    pos = 0; entry_i = None
    for i in range(len(s)):
        if s[i] != pos:
            # close existing
            if pos != 0 and entry_i is not None:
                ret = pos * (c[i]/c[entry_i] - 1.0)
                edt = dts[entry_i]
                p = reg.index.get_indexer([edt], method="ffill")[0]
                rg = reg.iloc[p] if p>=0 else "na"
                trades.append({"ret": ret, "entry_dt": edt, "regime": rg})
            pos = s[i]; entry_i = i if pos != 0 else None
    return trades

def ma_cross(fast, slow, symbols, allow_short=True):
    trades = []
    for sym in symbols:
        df = load(sym, "1d")
        f = df.close.rolling(fast).mean()
        sl = df.close.rolling(slow).mean()
        raw = np.where(f > sl, 1, np.where(f < sl, -1, 0))
        raw = pd.Series(raw, index=df.index).shift(1).fillna(0)  # tradable next bar
        if not allow_short:
            raw = raw.clip(lower=0)
        trades += legs_from_signal(df, raw)
    return trades

def donchian(n, symbols, allow_short=True):
    trades = []
    for sym in symbols:
        df = load(sym, "1d")
        hh = df.high.rolling(n).max()
        ll = df.low.rolling(n).min()
        # breakout long when close > prior hh; short when < prior ll; hold until opposite
        pos = np.zeros(len(df))
        c = df.close.values; H = hh.shift(1).values; L = ll.shift(1).values
        cur = 0
        for i in range(len(df)):
            if not np.isnan(H[i]) and c[i] > H[i]: cur = 1
            elif not np.isnan(L[i]) and c[i] < L[i]: cur = -1
            pos[i] = cur
        sig = pd.Series(pos, index=df.index).shift(1).fillna(0)
        if not allow_short: sig = sig.clip(lower=0)
        trades += legs_from_signal(df, sig)
    return trades

def main():
    results = []
    for f,s in [(10,30),(20,50),(50,200)]:
        results.append(evaluate(ma_cross(f,s,SYMBOLS,True), f"MAx {f}/{s} L/S"))
        results.append(evaluate(ma_cross(f,s,SYMBOLS,False), f"MAx {f}/{s} long-only"))
    for n in [20,55]:
        results.append(evaluate(donchian(n,SYMBOLS,True), f"Donchian {n} L/S"))
        results.append(evaluate(donchian(n,SYMBOLS,False), f"Donchian {n} long-only"))
    for r in results: r["_sv"] = verdict(r)[0]
    results.sort(key=lambda r:(r.get("_sv",False), r["mean_base_bps"]), reverse=True)
    print("\n########## TREND-FOLLOW (ranked) ##########")
    for r in results:
        ci=r["ci_base_bps"]; flag="SURV" if r.get("_sv") else "    "
        print(f"[{flag}] {r['label']:22} n={r['n']:5} net@base {r['mean_base_bps']:7.1f}bps "
              f"CI[{ci[0]:7.1f},{ci[1]:7.1f}] stress {r['mean_stress_bps']:7.1f} WR {r['win_rate']*100:4.1f}% "
              f"wf {r['wf']['n_pos'] if r['wf'] else '-'}/{r['wf']['n_folds'] if r['wf'] else '-'}")
    print("\n########## DETAIL top 4 ##########")
    for r in results[:4]: print_res(r)

if __name__ == "__main__":
    main()
