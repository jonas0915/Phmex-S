"""EXPLORATORY PROBE #2 — NOT THE SCREEN. Symmetric variant: fade the 07:00-08:00 UTC
bar's move on expiry days (dealer hedge unwind works in either direction if they were
short gamma). long_1h TRAIN only. Universe = Deribit-option coins BTC ETH SOL XRP."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, fee_math as fm, bootstrap_ci as bc, screen as sc

SYMS = ["BTC", "ETH", "SOL", "XRP"]
OUT = "research/swarm/runs/2026-09-17-0701/exploratory/dealer_inventory/probe_expiry_symmetric.out.json"


def last_friday(ts):
    m_end = (ts + pd.offsets.MonthEnd(0)).normalize()
    return m_end - pd.Timedelta(days=(m_end.weekday() - 4) % 7)


def make_signal(df, mode, thr_bps):
    idx = df.index
    ret_bps = (df["close"] / df["open"] - 1.0).to_numpy() * 1e4
    is_pre = (idx.hour == 7)
    fri = (idx.weekday == 4)
    if mode == "friday":
        day_ok = fri
    elif mode == "monthly":
        day_ok = fri & np.array([ts.normalize() == last_friday(ts) for ts in idx])
    elif mode == "nonmonthly_friday":
        day_ok = fri & ~np.array([ts.normalize() == last_friday(ts) for ts in idx])
    sig = pd.Series(0, index=idx, dtype=int)
    sig[is_pre & day_ok & (ret_bps <= -thr_bps)] = 1
    sig[is_pre & day_ok & (ret_bps >= thr_bps)] = -1
    return sig


res = {}
for mode in ("friday", "monthly", "nonmonthly_friday"):
    for thr in (10.0, 25.0, 40.0):
        for hold, tp, sl in ((1, 100, 100), (2, 100, 100), (3, 100, 100)):
            rows = []
            for s in SYMS:
                df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
                tr = sc.simulate(df, make_signal(df, mode, thr), tp, sl, hold)
                tr["symbol"] = s
                rows.append(tr)
            tr = pd.concat(rows, ignore_index=True)
            n = len(tr)
            key = f"{mode}|thr{thr:g}|hold{hold}|tp{tp}"
            if n >= 2:
                res[key] = {"n": n, "net_mean": float(tr.net_bps.mean()), "gross_mean": float(tr.gross_bps.mean()),
                            "ci95": bc.mean_ci(tr.net_bps.to_numpy()), "wr_net": float((tr.net_bps > 0).mean()),
                            "p_star": fm.p_star(tp), "exit_mix": tr.exit_reason.value_counts().to_dict(),
                            "by_side": tr.groupby("side").net_bps.agg(["count", "mean"]).round(1).to_dict(),
                            "per_sym": tr.groupby("symbol").net_bps.mean().round(1).to_dict()}
            else:
                res[key] = {"n": n}
            print(key, json.dumps(res[key], default=str))
json.dump(res, open(OUT, "w"), indent=1, default=str)
print("wrote", OUT)
