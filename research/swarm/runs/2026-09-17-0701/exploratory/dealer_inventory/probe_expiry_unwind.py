"""EXPLORATORY PROBE — NOT THE SCREEN. Numbers here are not evidence.
Lens: dealer_inventory. Mechanism: Deribit option market-maker delta-hedge unwind
around the 08:00 UTC expiry (FRL study: fall in the hour before, reversal in the two
hours after, on top-decile ATM-OI days). Proxy for high-OI days = Friday expiries
(weekly + monthly + quarterly), since the bot has no options OI feed.
Dataset: long_1h TRAIN only (2025-06-27 -> 2026-04-23). No mr_edge data used
(cross-dataset caveat). Universe = coins with Deribit options: BTC ETH SOL XRP.
"""
import sys, json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, fee_math as fm, bootstrap_ci as bc, screen as sc

SYMS = ["BTC", "ETH", "SOL", "XRP"]
OUT = "research/swarm/runs/2026-09-17-0701/exploratory/dealer_inventory/probe_expiry_unwind.out.json"


def last_friday(ts):
    # last Friday of the month for a timestamp
    m_end = (ts + pd.offsets.MonthEnd(0)).normalize()
    return m_end - pd.Timedelta(days=(m_end.weekday() - 4) % 7)


def make_signal(df, mode, thr_bps):
    idx = df.index
    ret = df["close"] / df["open"] - 1.0
    is_pre = (idx.hour == 7)
    fri = (idx.weekday == 4)
    if mode == "friday":
        day_ok = fri
    elif mode == "monthly":
        day_ok = fri & np.array([ts.normalize() == last_friday(ts) for ts in idx])
    elif mode == "everyday":
        day_ok = np.ones(len(idx), bool)
    drop = ret.to_numpy() * 1e4 <= -thr_bps
    sig = pd.Series(0, index=idx, dtype=int)
    sig[is_pre & day_ok & drop] = 1
    return sig


res = {}
for mode in ("friday", "monthly", "everyday"):
    for thr in (0.0, 10.0, 25.0):
        for hold, tp, sl in ((2, 100, 100), (3, 100, 100), (6, 150, 150)):
            rows = []
            for s in SYMS:
                df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
                sig = make_signal(df, mode, thr)
                tr = sc.simulate(df, sig, tp, sl, hold)
                tr["symbol"] = s
                rows.append(tr)
            tr = pd.concat(rows, ignore_index=True)
            n = len(tr)
            key = f"{mode}|thr{thr:g}|hold{hold}|tp{tp}"
            if n >= 2:
                ci = bc.mean_ci(tr["net_bps"].to_numpy())
                res[key] = {"n": n, "net_mean": float(tr.net_bps.mean()), "gross_mean": float(tr.gross_bps.mean()),
                            "ci95": ci, "wr_net": float((tr.net_bps > 0).mean()), "p_star": fm.p_star(tp),
                            "exit_mix": tr.exit_reason.value_counts().to_dict(),
                            "per_sym": tr.groupby("symbol").net_bps.mean().round(1).to_dict()}
            else:
                res[key] = {"n": n}
            print(key, json.dumps(res[key], default=str))

# control: same-time long on non-Friday days with drop (time-of-day only)
json.dump(res, open(OUT, "w"), indent=1, default=str)
print("wrote", OUT)
