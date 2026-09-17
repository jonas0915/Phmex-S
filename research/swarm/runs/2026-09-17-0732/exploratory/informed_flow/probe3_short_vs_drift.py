"""EXPLORATORY probe 3 (NOT the screen). Is the conditional short (ETH 4h z>=+2 rally, alt captured <0.5x)
better than an UNCONDITIONAL alt short with identical geometry (TP=SL=150, hold 8, one position per symbol,
re-enter immediately)? diff_ci (independent resampling) of conditional minus baseline, on mr_edge train
and on long_1h train separately. Also the signal draft for thesis 1 exactly as it will be registered."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm, screen as sc

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/informed_flow/probe3_out.json"

def draft_signals(df, leader):
    K, THR, CAP = 4, 2.0, 0.5
    L = np.log(leader["close"]); lk = L.diff(K)
    vol = L.diff().rolling(24 * 14).std() * np.sqrt(K)
    z = (lk / vol).reindex(df.index); lkr = lk.reindex(df.index)
    a = np.log(df["close"]).diff(K)
    cond = (z >= THR) & (a < CAP * lkr)
    sig = pd.Series(0, index=df.index, dtype=int); sig[cond.fillna(False)] = -1
    return sig

res = {}
for ds, excl in (("mr_edge", {"ALLO","BICO","DEXE","EIGEN","GIGGLE","INJ","WIF","WLD","ZAMA"}), ("long_1h", {"GIGGLE"})):
    eth = ld.load_ohlcv("ETH", "1h", era="train", dataset=ds)
    cond_rows, base_rows = [], []
    for s in ld.list_symbols(ds):
        if s in ("ETH", "BTC") or s in excl: continue
        df = ld.load_ohlcv(s, "1h", era="train", dataset=ds)
        tr = sc.simulate(df, draft_signals(df, eth), 150, 150, 8); tr.insert(0, "symbol", s); cond_rows.append(tr)
        bs = sc.simulate(df, pd.Series(-1, index=df.index), 150, 150, 8); bs.insert(0, "symbol", s); base_rows.append(bs)
    C = pd.concat(cond_rows, ignore_index=True); B = pd.concat(base_rows, ignore_index=True)
    weeks = (eth.index.max() - eth.index.min()).total_seconds() / (7 * 86400)
    c, b = C.net_bps.to_numpy(), B.net_bps.to_numpy()
    r = {"cond_n": int(len(c)), "cond_net_mean": float(c.mean()), "cond_ci95": list(bc.mean_ci(c)), "cond_wr": float((c > 0).mean()),
         "cond_tpw": len(c) / weeks, "cond_ttv_weeks": fm.time_to_verdict_weeks(len(c) / weeks), "p_star": fm.p_star(150),
         "base_n": int(len(b)), "base_net_mean": float(b.mean()), "base_ci95": list(bc.mean_ci(b)), "base_wr": float((b > 0).mean()),
         "diff_ci95_cond_minus_base": list(bc.diff_ci(c, b)),
         "cond_exit": C.exit_reason.value_counts().to_dict(),
         "cond_by_month": {k: [int(v["count"]), float(v["mean"])] for k, v in C.assign(m=C.entry_ts.dt.strftime("%Y-%m")).groupby("m").net_bps.agg(["count", "mean"]).iterrows()},
         "cond_by_symbol": {k: [int(v["count"]), float(v["mean"])] for k, v in C.groupby("symbol").net_bps.agg(["count", "mean"]).iterrows()}}
    res[ds] = r; print(ds, json.dumps(r, default=str))
json.dump(res, open(OUT, "w"), indent=1, default=str)
