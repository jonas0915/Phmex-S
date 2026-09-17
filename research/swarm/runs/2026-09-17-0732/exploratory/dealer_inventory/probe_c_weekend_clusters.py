"""EXPLORATORY — NOT the screen. Cluster diagnostics for the weekend-unwind cell
(thr 200 bps, tp/sl 300, hold 48, long side only): per-weekend aggregation, weekend-level
bootstrap CI via bootstrap_ci.mean_ci on per-weekend means, month spread, and the
same for the short side. long_1h train only."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc
import importlib.util, sys
spec = importlib.util.spec_from_file_location("pb", "research/swarm/runs/2026-09-17-0732/exploratory/dealer_inventory/probe_b_weekend_unwind.py")
# reuse make_sig without re-running the sweep: copy of the function
def make_sig(df, thr_bps, fire_wd, fire_hour, lookback_h):
    idx = df.index; ny = idx.tz_convert("America/New_York"); c = df["close"]
    fire = (ny.weekday == fire_wd) & (ny.hour == fire_hour - 1)
    mv = (c / c.shift(lookback_h) - 1.0) * 1e4
    sig = pd.Series(0, index=idx, dtype=int)
    sig[fire & (mv <= -thr_bps)] = 1
    sig[fire & (mv >= thr_bps)] = -1
    return sig

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/dealer_inventory/probe_c_weekend_clusters.out.json"
res = {}
for thr in [200, 300]:
    trades = []
    for s in ld.list_symbols("long_1h"):
        df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        tr = sc.simulate(df, make_sig(df, thr, 6, 18, 49), 300, 300, 48); tr["sym"] = s; trades.append(tr)
    t = pd.concat(trades)
    t["weekend"] = pd.to_datetime(t["entry_ts"]).dt.tz_convert("America/New_York").dt.date.astype(str)
    for side, name in [(1, "long"), (-1, "short")]:
        u = t[t.side == side]
        pw = u.groupby("weekend")["net_bps"].agg(["mean", "count"])
        lo, hi = bc.mean_ci(pw["mean"])
        tlo, thi = bc.mean_ci(u["net_bps"])
        months = pd.to_datetime(u["entry_ts"]).dt.strftime("%Y-%m")
        res[f"thr{thr}|{name}"] = {
            "n_trades": int(len(u)), "n_weekends": int(len(pw)), "trade_net_mean": float(u["net_bps"].mean()),
            "trade_ci95": [float(tlo), float(thi)], "weekend_mean_of_means": float(pw["mean"].mean()),
            "weekend_ci95": [float(lo), float(hi)], "weekends_positive_frac": float((pw["mean"] > 0).mean()),
            "wr_trades": float((u["net_bps"] > 0).mean()), "p_star_300": fm.p_star(300),
            "per_weekend": {k: [round(float(v["mean"]), 1), int(v["count"])] for k, v in pw.iterrows()},
            "month_net_mean": {k: round(float(v), 1) for k, v in u.groupby(months)["net_bps"].mean().items()},
            "month_n": {k: int(v) for k, v in months.value_counts().sort_index().items()},
            "trades_per_week": float(len(u) / 43.0),
            "ttv_weeks_n50": fm.time_to_verdict_weeks(len(u) / 43.0),
        }
        print(json.dumps({k: v for k, v in res[f"thr{thr}|{name}"].items() if k != "per_weekend"}))
        print("  per_weekend:", res[f"thr{thr}|{name}"]["per_weekend"])
json.dump(res, open(OUT, "w"), indent=1)
