"""EXPLORATORY — NOT the screen, numbers are not evidence.
Probe B: weekend-inventory unwind. Weekend = CME Globex crypto closed window,
Fri 17:00 NY -> Sun 18:00 NY. Signal on the closed 1h bar ending Sun 18:00 NY: fade the
weekend move if |move| >= thr; enter at the next open (CME reopen). Control: the same
rule applied to a 49h mid-week window (Tue 17:00 NY -> Thu 18:00 NY) fired at Thu 18:00 NY.
Dataset long_1h, era=train only (no mr_edge data touched). Lens: dealer_inventory.
"""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/dealer_inventory/probe_b_weekend_unwind.out.json"
SYMS = ld.list_symbols("long_1h")


def make_sig(df, thr_bps, fire_wd, fire_hour, lookback_h):
    """fire on bars whose NY-local end time is (weekday fire_wd, hour fire_hour); the
    move is close[t] / close[t - lookback_h bars]. Closed bars only."""
    idx = df.index
    ny = idx.tz_convert("America/New_York")
    c = df["close"]
    # bar timestamps are bar OPEN times; the bar ending at fire_hour opens at fire_hour-1
    fire = (ny.weekday == fire_wd) & (ny.hour == fire_hour - 1)
    prev_c = c.shift(lookback_h)
    mv = (c / prev_c - 1.0) * 1e4
    sig = pd.Series(0, index=idx, dtype=int)
    sig[fire & (mv <= -thr_bps)] = 1
    sig[fire & (mv >= thr_bps)] = -1
    return sig


def cell(syms, thr, fire_wd, fire_hour, lookback_h, tp, sl, hold):
    trades = []
    for s in syms:
        df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        tr = sc.simulate(df, make_sig(df, thr, fire_wd, fire_hour, lookback_h), tp, sl, hold)
        tr["sym"] = s
        trades.append(tr)
    t = pd.concat(trades)
    if len(t) == 0:
        return {"n": 0}
    lo, hi = bc.mean_ci(t["net_bps"])
    return {"n": int(len(t)), "net_mean": float(t["net_bps"].mean()), "gross_mean": float(t["gross_bps"].mean()),
            "ci95": [float(lo), float(hi)], "wr_net": float((t["net_bps"] > 0).mean()), "p_star": fm.p_star(tp),
            "exit_mix": t["exit_reason"].value_counts().to_dict(),
            "n_long": int((t["side"] == 1).sum()), "net_long": float(t.loc[t.side == 1, "net_bps"].mean()) if (t.side == 1).any() else None,
            "net_short": float(t.loc[t.side == -1, "net_bps"].mean()) if (t.side == -1).any() else None,
            "per_sym": {k: round(float(v), 1) for k, v in t.groupby("sym")["net_bps"].mean().items()}}


res = {}
# weekend: fire Sunday (weekday 6) bar ending 18:00 NY, lookback 49 bars (Fri 17:00 NY close)
# midweek control: fire Thursday (3) bar ending 18:00 NY, lookback 49 bars (Tue 17:00 NY close)
for label, wd in [("weekend", 6), ("midweek", 3)]:
    for thr in [100, 200, 300, 500]:
        for tp, sl, hold in [(150, 150, 24), (200, 200, 24), (200, 200, 48), (300, 300, 48)]:
            key = f"{label}|thr{thr}|tp{tp}|sl{sl}|hold{hold}"
            res[key] = cell(SYMS, thr, wd, 18, 49, tp, sl, hold)
            print(key, json.dumps({k: v for k, v in res[key].items() if k != "per_sym"})[:260], flush=True)
json.dump(res, open(OUT, "w"), indent=1)
