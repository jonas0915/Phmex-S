#!/usr/bin/env python3
"""Family 3: Cross-sectional momentum. Each rebalance (weekly), rank universe
by trailing L-day return; long top-k, short bottom-k; hold H days. Each
symbol-leg is a trade. Market-neutral-ish (equal long/short)."""
import numpy as np, pandas as pd
from engine import load, SYMBOLS, evaluate, print_res, verdict, btc_regime

def build_panel(symbols, tf="1d"):
    cols = {}
    for s in symbols:
        cols[s] = load(s, tf)["close"]
    panel = pd.DataFrame(cols).sort_index()
    return panel

def xsec(L, k, H, symbols, long_short=True):
    panel = build_panel(symbols)
    reg = btc_regime("1d")
    idx = panel.index
    trades = []
    i = L
    while i + H < len(idx):
        row_now = panel.iloc[i]
        row_past = panel.iloc[i-L]
        trail = (row_now / row_past - 1.0).dropna()
        # need enough names
        valid = trail.dropna()
        if len(valid) < 2*k + 1:
            i += 7; continue
        ranked = valid.sort_values(ascending=False)
        longs = ranked.index[:k]
        shorts = ranked.index[-k:] if long_short else []
        fut = panel.iloc[i+H] / panel.iloc[i] - 1.0
        edt = idx[i]
        p = reg.index.get_indexer([edt], method="ffill")[0]
        rg = reg.iloc[p] if p>=0 else "na"
        for s in longs:
            if not np.isnan(fut.get(s, np.nan)):
                trades.append({"ret": fut[s], "entry_dt": edt, "regime": rg, "symbol": s})
        for s in shorts:
            if not np.isnan(fut.get(s, np.nan)):
                trades.append({"ret": -fut[s], "entry_dt": edt, "regime": rg, "symbol": s})
        i += 7  # weekly rebalance
    return trades

def main():
    results = []
    for L in [7,14,30]:
        for k in [2,3]:
            for H in [7,14]:
                results.append(evaluate(xsec(L,k,H,SYMBOLS,True), f"XS L{L} k{k} H{H} L/S"))
                results.append(evaluate(xsec(L,k,H,SYMBOLS,False), f"XS L{L} k{k} H{H} long"))
    for r in results: r["_sv"]=verdict(r)[0]
    results.sort(key=lambda r:(r.get("_sv",False), r["mean_base_bps"]), reverse=True)
    print("\n########## CROSS-SECTIONAL MOM (ranked) ##########")
    for r in results:
        ci=r["ci_base_bps"]; flag="SURV" if r.get("_sv") else "    "
        print(f"[{flag}] {r['label']:18} n={r['n']:5} net@base {r['mean_base_bps']:7.1f}bps "
              f"CI[{ci[0]:7.1f},{ci[1]:7.1f}] stress {r['mean_stress_bps']:7.1f} WR {r['win_rate']*100:4.1f}% "
              f"wf {r['wf']['n_pos'] if r['wf'] else '-'}/{r['wf']['n_folds'] if r['wf'] else '-'}")
    print("\n########## DETAIL top 4 ##########")
    for r in results[:4]: print_res(r)

if __name__ == "__main__":
    main()
