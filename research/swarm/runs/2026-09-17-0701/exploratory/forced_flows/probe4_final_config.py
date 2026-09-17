"""EXPLORATORY ONLY — candidate config on the 18-symbol universe (GIGGLE dropped: its
long_1h cache spans 2026-01-13 -> beyond, so its per-symbol 'train' slice runs to 2026-06-12,
inside the other symbols' holdout window). tp=sl=300, hold 36 bars; plus the +/-20% tp
variants the committee will read. long_1h TRAIN only."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen as sc, bootstrap_ci as bc, fee_math as fm
SIG = open("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/candidate_signal.py").read()
ns = {}; exec(SIG, ns); signals = ns["signals"]
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in SYMS}
t0 = min(d.index.min() for d in frames.values()); t1 = max(d.index.max() for d in frames.values())
weeks = (t1 - t0).total_seconds() / (7 * 86400)
res = {"train_span": [str(t0), str(t1)], "weeks": weeks}
for tp in (300, 240, 360):
    trs = []
    for s, df in frames.items():
        t = sc.simulate(df, signals(df), tp, 300, 36); t.insert(0, "symbol", s); trs.append(t)
    T = pd.concat(trs, ignore_index=True); x = T.net_bps.to_numpy()
    days = pd.to_datetime(T.entry_ts).dt.floor("D"); top = days.value_counts()
    xe = T[days != top.index[0]].net_bps.to_numpy()
    res[f"tp{tp}"] = {"n": int(len(T)), "net_mean": float(x.mean()), "ci95": list(bc.mean_ci(x)), "wr": float((x > 0).mean()),
                      "p_star": fm.p_star(tp), "trades_per_week": len(T) / weeks, "ttv_weeks": fm.time_to_verdict_weeks(len(T) / weeks),
                      "distinct_days": int(days.nunique()), "top_day": str(top.index[0].date()), "top_day_n": int(top.iloc[0]),
                      "ex_top_day_n": int(len(xe)), "ex_top_day_net_mean": float(xe.mean()), "ex_top_day_ci95": list(bc.mean_ci(xe)),
                      "exit_mix": T.exit_reason.value_counts().to_dict(),
                      "by_month_net_mean": {str(k): float(v) for k, v in T.groupby(pd.to_datetime(T.entry_ts).dt.to_period("M")).net_bps.mean().items()}}
    if tp == 300:
        T.to_csv("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/probe4_trades_tp300.csv", index=False)
json.dump(res, open("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/probe4_summary.json", "w"), indent=2, default=str)
print(json.dumps(res, indent=1, default=str))
