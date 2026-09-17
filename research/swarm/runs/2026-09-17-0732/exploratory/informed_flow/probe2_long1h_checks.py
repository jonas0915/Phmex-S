"""EXPLORATORY probe 2 (NOT the screen). long_1h dataset, era=train only (2025-06-27 -> ~2026-04-24).
(a) Same ETH-led seesaw rule as probe1 (K=4, thr=2.0, cap 0.5, TP=SL=150, H=8) on a different period,
    as an out-of-period sanity check for thesis 1 (mr_edge). No mr_edge data touched here.
(b) BTC 72h move -> laggard alt catch-up (slow diffusion, in-leader-direction) with TP=SL=300, hold 48,
    as a candidate for a >8h-hold thesis."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm, screen as sc

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/informed_flow/probe2_out.json"
eth = ld.load_ohlcv("ETH", "1h", era="train", dataset="long_1h")
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
t0, t1 = eth.index.min(), eth.index.max()
print("long_1h train span", t0, t1)
frames = {}
for s in ld.list_symbols("long_1h"):
    if s in ("ETH", "BTC"): continue
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    print(s, df.index.min(), df.index.max(), len(df))
    frames[s] = df
weeks = (t1 - t0).total_seconds() / (7 * 86400)

def seesaw_sig(df, leader, K, thr, cap):
    L = np.log(leader["close"]); lk = L.diff(K)
    vol = L.diff().rolling(24 * 14).std() * np.sqrt(K)
    z = (lk / vol).reindex(df.index); lkr = lk.reindex(df.index)
    a = np.log(df["close"]).diff(K); sgn = np.sign(z)
    cond = (z.abs() >= thr) & (a * sgn < cap * lkr.abs())
    sig = pd.Series(0, index=df.index); sig[cond & (sgn > 0)] = -1; sig[cond & (sgn < 0)] = 1
    return sig

def diffusion_sig(df, leader, K, thr, cap):
    L = np.log(leader["close"]); lk = L.diff(K)
    vol = L.diff().rolling(24 * 30).std() * np.sqrt(K)
    z = (lk / vol).reindex(df.index); lkr = lk.reindex(df.index)
    a = np.log(df["close"]).diff(K); sgn = np.sign(z)
    cond = (z.abs() >= thr) & (a * sgn < cap * lkr.abs())
    sig = pd.Series(0, index=df.index); sig[cond & (sgn > 0)] = 1; sig[cond & (sgn < 0)] = -1
    return sig

def summarize(T, tp):
    r = {"n": int(len(T))}
    if len(T) >= 2:
        x = T.net_bps.to_numpy()
        r.update(net_mean=float(x.mean()), ci95=[float(v) for v in bc.mean_ci(x)], wr=float((x > 0).mean()),
                 p_star=fm.p_star(tp), tpw=len(T) / weeks, exit=T.exit_reason.value_counts().to_dict())
        for side in (-1, 1):
            xs = T[T.side == side].net_bps.to_numpy()
            if len(xs) >= 2:
                r[f"side{side}"] = {"n": int(len(xs)), "net_mean": float(xs.mean()), "ci95": [float(v) for v in bc.mean_ci(xs)], "wr": float((xs > 0).mean())}
        m = T.assign(m=T.entry_ts.dt.strftime("%Y-%m")).groupby("m").net_bps.agg(["count", "mean"])
        r["by_month"] = {k: [int(v["count"]), float(v["mean"])] for k, v in m.iterrows()}
    return r

res = {}
for K, thr, tp, H, name, fn, leader in ((4, 2.0, 150, 8, "a_ETH_seesaw_K4_thr2.0_tp150_H8", seesaw_sig, eth),
                                        (4, 2.0, 200, 8, "a_ETH_seesaw_K4_thr2.0_tp200_H8", seesaw_sig, eth),
                                        (4, 2.0, 150, 8, "a_BTC_seesaw_K4_thr2.0_tp150_H8", seesaw_sig, btc),
                                        (72, 1.5, 300, 48, "b_BTC_diffusion_K72_thr1.5_tp300_H48", diffusion_sig, btc),
                                        (72, 2.0, 300, 48, "b_BTC_diffusion_K72_thr2.0_tp300_H48", diffusion_sig, btc),
                                        (24, 1.5, 300, 48, "b_BTC_diffusion_K24_thr1.5_tp300_H48", diffusion_sig, btc)):
    rows = []
    for s, df in frames.items():
        tr = sc.simulate(df, fn(df, leader, K, thr, 0.5), tp, tp, H); tr.insert(0, "symbol", s); rows.append(tr)
    T = pd.concat(rows, ignore_index=True)
    res[name] = summarize(T, tp); print(name, json.dumps(res[name]))
json.dump(res, open(OUT, "w"), indent=1, default=str)
