"""EXPLORATORY ONLY — not the screen; numbers here are not evidence.
Probe: post-cascade continuation SHORT on long_1h TRAIN (1h bars). No mr_edge data is
loaded anywhere in this probe (STANDARDS #6 cross-dataset caveat).
Variants:
  A: single cascade bar (ret <= -k*std168, vol >= 2x med168), short next open.
  B: A + 'no-recovery' confirmation: the bar AFTER the cascade bar closes below the
     cascade bar's midpoint (forced flow not exhausted) -> signal on that 2nd bar.
Simulation uses research.swarm.lib.screen.simulate; CI from bootstrap_ci.mean_ci.
"""
import json, sys
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/forced_flows"
syms = [s for s in ld.list_symbols("long_1h")]

def sigA(df, k=3.0, vmult=2.0):
    r = df["close"].pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
    cas = (r <= -k * sd) & (df["volume"] >= vmult * vm)
    return pd.Series(np.where(cas.fillna(False), -1, 0), index=df.index).astype(int)

def sigB(df, k=3.0, vmult=2.0):
    r = df["close"].pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
    cas = (r <= -k * sd) & (df["volume"] >= vmult * vm)
    mid = (df["high"] + df["low"]) / 2
    confirm = cas.shift(1).fillna(False) & (df["close"] < mid.shift(1))
    return pd.Series(np.where(confirm.fillna(False), -1, 0), index=df.index).astype(int)

res = {}
frames = {}
for s in syms:
    try:
        frames[s] = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    except Exception as e:
        print("skip", s, e)
print({s: (str(df.index.min()), str(df.index.max()), len(df)) for s, df in frames.items()})
for name, fn in [("A", sigA), ("B", sigB)]:
    for tp, hold in [(200, 24), (300, 36), (300, 24)]:
        trades = []
        for s, df in frames.items():
            t = sc.simulate(df, fn(df), tp, tp, hold); t.insert(0, "symbol", s); trades.append(t)
        T = pd.concat(trades, ignore_index=True)
        n = len(T)
        if n < 2: continue
        x = T["net_bps"].to_numpy()
        T["day"] = pd.to_datetime(T["entry_ts"]).dt.date
        top = T["day"].value_counts()
        ex = T[T["day"] != top.index[0]]["net_bps"].to_numpy()
        span = max(df.index.max() for df in frames.values()) - min(df.index.min() for df in frames.values())
        weeks = span.total_seconds() / (7 * 86400)
        key = f"{name}_tp{tp}_hold{hold}"
        res[key] = {"n": n, "net_mean": float(x.mean()), "ci95": list(bc.mean_ci(x)), "wr": float((x > 0).mean()),
                    "p_star": fm.p_star(tp), "trades_per_week": n / weeks,
                    "ttv_weeks": fm.time_to_verdict_weeks(n / weeks),
                    "top_day": str(top.index[0]), "top_day_n": int(top.iloc[0]),
                    "ex_top_day_mean": float(ex.mean()), "ex_top_day_ci95": list(bc.mean_ci(ex)),
                    "exit_mix": T["exit_reason"].value_counts().to_dict(),
                    "by_month": T.groupby(pd.to_datetime(T["entry_ts"]).dt.strftime("%Y-%m"))["net_bps"].mean().round(1).to_dict()}
        T.to_csv(f"{OUT}/probe1_trades_{key}.csv", index=False)
        print(key, json.dumps(res[key], default=str))
json.dump(res, open(f"{OUT}/probe1_summary.json", "w"), indent=2, default=str)
