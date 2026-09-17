"""EXPLORATORY probe (NOT the screen; numbers are not evidence). Lens informed_flow, run 2026-09-17-0732.
Question: when ETH (the leader) makes a >= thr-sigma move over K closed 1h bars and an alt has captured
less than half of it, does the alt move AGAINST ETH's direction over the next H bars (seesaw), on the
mr_edge 1h TRAIN era? Uses screen.simulate (one position per symbol, SL-first tie rule) so the geometry
matches the real screen. Both sides reported separately (ETH-up -> short alt; ETH-down -> long alt)."""
import json, sys
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm, screen as sc

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/informed_flow/probe1_out.json"
eth = ld.load_ohlcv("ETH", "1h", era="train", dataset="mr_edge")
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")
t0, t1 = eth.index.min(), eth.index.max()
syms = [s for s in ld.list_symbols("mr_edge") if s not in ("ETH", "BTC")]
frames = {}
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
    if df.index.min() != t0 or df.index.max() != t1:
        print("EXCLUDE (span differs from ETH):", s, df.index.min(), df.index.max()); continue
    frames[s] = df
print("universe", len(frames), sorted(frames))
print("train span", t0, t1)

def make_sig(df, leader, K, thr, cap, signed=True):
    L = np.log(leader["close"])
    lk = L.diff(K)
    vol = L.diff().rolling(24 * 14).std() * np.sqrt(K)
    z = (lk / vol).reindex(df.index)
    lkr = lk.reindex(df.index)
    a = np.log(df["close"]).diff(K)
    sgn = np.sign(z)
    captured = a * sgn if signed else a.abs()
    cond = (z.abs() >= thr) & (captured < cap * lkr.abs())
    sig = pd.Series(0, index=df.index)
    sig[cond & (sgn > 0)] = -1
    sig[cond & (sgn < 0)] = 1
    return sig

res = {}
weeks = (t1 - t0).total_seconds() / (7 * 86400)
for leader_name, leader in (("ETH", eth), ("BTC", btc)):
    for K in (4, 8):
        for thr in (2.0, 2.5):
            for tp in (150, 200):
                for H in (8, 12):
                    rows = []
                    for s, df in frames.items():
                        sig = make_sig(df, leader, K, thr, 0.5)
                        tr = sc.simulate(df, sig, tp, tp, H)
                        tr.insert(0, "symbol", s); rows.append(tr)
                    T = pd.concat(rows, ignore_index=True)
                    key = f"{leader_name}_K{K}_thr{thr}_tp{tp}_H{H}"
                    r = {"n": int(len(T))}
                    if len(T) >= 2:
                        x = T.net_bps.to_numpy()
                        r.update(net_mean=float(x.mean()), ci95=[float(v) for v in bc.mean_ci(x)],
                                 wr=float((x > 0).mean()), p_star=fm.p_star(tp), tpw=len(T) / weeks,
                                 exit=T.exit_reason.value_counts().to_dict())
                        for side in (-1, 1):
                            xs = T[T.side == side].net_bps.to_numpy()
                            if len(xs) >= 2:
                                r[f"side{side}"] = {"n": int(len(xs)), "net_mean": float(xs.mean()), "ci95": [float(v) for v in bc.mean_ci(xs)], "wr": float((xs > 0).mean())}
                        r["by_month"] = {str(k): [int(v["count"]), float(v["mean"])] for k, v in
                                         T.assign(m=T.entry_ts.dt.to_period("M")).groupby("m").net_bps.agg(["count", "mean"]).iterrows()}
                    res[key] = r
                    print(key, json.dumps(r))
json.dump(res, open(OUT, "w"), indent=1, default=str)
