"""EXPLORATORY ONLY. Same variant-A signal (own cascade bar, short next open) restricted to
majors whose own 1h cascade is market-wide by construction. Day-clustered CI reported.
long_1h TRAIN only; no mr_edge data."""
import json, pandas as pd, numpy as np
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc
OUT = "research/swarm/runs/2026-09-17-0732/exploratory/forced_flows"
def sigA(df, k=3.0, vmult=2.0):
    r = df["close"].pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
    cas = (r <= -k * sd) & (df["volume"] >= vmult * vm)
    return pd.Series(np.where(cas.fillna(False), -1, 0), index=df.index).astype(int)
sets = {"btc_eth": ["BTC", "ETH"], "top4": ["BTC", "ETH", "SOL", "XRP"], "top7": ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB"]}
res = {}
for name, syms in sets.items():
    frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in syms}
    span = max(df.index.max() for df in frames.values()) - min(df.index.min() for df in frames.values()); weeks = span.total_seconds()/(7*86400)
    for tp, hold in [(300, 24), (300, 36), (200, 24)]:
        trades = []
        for s, df in frames.items():
            t = sc.simulate(df, sigA(df), tp, tp, hold); t.insert(0, "symbol", s); trades.append(t)
        T = pd.concat(trades, ignore_index=True); x = T["net_bps"].to_numpy(); n = len(T)
        T["day"] = pd.to_datetime(T["entry_ts"]).dt.date; dm = T.groupby("day")["net_bps"].mean().to_numpy()
        key = f"{name}_tp{tp}_hold{hold}"
        res[key] = {"n": n, "net_mean": float(x.mean()), "ci95": list(bc.mean_ci(x)), "wr": float((x>0).mean()), "p_star": fm.p_star(tp),
                    "trades_per_week": n/weeks, "ttv_weeks": fm.time_to_verdict_weeks(n/weeks), "distinct_days": int(len(dm)),
                    "day_clustered_mean": float(dm.mean()), "day_clustered_ci95": list(bc.mean_ci(dm)),
                    "exit_mix": T["exit_reason"].value_counts().to_dict(),
                    "by_month": T.groupby(pd.to_datetime(T["entry_ts"]).dt.strftime("%Y-%m"))["net_bps"].mean().round(1).to_dict(),
                    "by_symbol_mean": T.groupby("symbol")["net_bps"].mean().round(1).to_dict(), "by_symbol_n": T.groupby("symbol").size().to_dict()}
        T.to_csv(f"{OUT}/probe5_trades_{key}.csv", index=False)
        print(key, json.dumps(res[key], default=str))
json.dump(res, open(f"{OUT}/probe5_summary.json", "w"), indent=2, default=str)
