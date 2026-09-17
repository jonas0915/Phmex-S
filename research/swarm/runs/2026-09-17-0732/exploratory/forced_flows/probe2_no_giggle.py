"""EXPLORATORY ONLY — not the screen. Variant A (single cascade bar, short next open),
long_1h TRAIN, 18 symbols (GIGGLE excluded: its per-symbol train span 2026-01-13 -> 2026-06-12
overlaps the long_1h holdout window by date). Adds a day-clustered CI (mean of per-entry-day
means, bootstrap_ci.mean_ci over days) as a cluster-robustness read. No mr_edge data used."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc
OUT = "research/swarm/runs/2026-09-17-0732/exploratory/forced_flows"
syms = [s for s in ld.list_symbols("long_1h") if s != "GIGGLE"]
def sigA(df, k=3.0, vmult=2.0):
    r = df["close"].pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
    cas = (r <= -k * sd) & (df["volume"] >= vmult * vm)
    return pd.Series(np.where(cas.fillna(False), -1, 0), index=df.index).astype(int)
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in syms}
span = max(df.index.max() for df in frames.values()) - min(df.index.min() for df in frames.values())
weeks = span.total_seconds() / (7 * 86400)
res = {"symbols": syms, "weeks": weeks, "train_span": [str(min(df.index.min() for df in frames.values())), str(max(df.index.max() for df in frames.values()))]}
sig_counts = {s: int((sigA(df) != 0).sum()) for s, df in frames.items()}
res["signal_bars_per_symbol"] = sig_counts
for tp, hold in [(300, 24), (300, 36), (240, 24), (360, 24)]:
    trades = []
    for s, df in frames.items():
        t = sc.simulate(df, sigA(df), tp, tp, hold); t.insert(0, "symbol", s); trades.append(t)
    T = pd.concat(trades, ignore_index=True)
    x = T["net_bps"].to_numpy(); n = len(T)
    T["day"] = pd.to_datetime(T["entry_ts"]).dt.date
    top = T["day"].value_counts()
    ex = T[T["day"] != top.index[0]]["net_bps"].to_numpy()
    daymeans = T.groupby("day")["net_bps"].mean().to_numpy()
    key = f"A_tp{tp}_hold{hold}"
    res[key] = {"n": n, "net_mean": float(x.mean()), "ci95": list(bc.mean_ci(x)), "wr": float((x > 0).mean()),
                "p_star": fm.p_star(tp), "trades_per_week": n / weeks, "ttv_weeks": fm.time_to_verdict_weeks(n / weeks),
                "distinct_days": int(len(daymeans)), "top_day": str(top.index[0]), "top_day_n": int(top.iloc[0]),
                "ex_top_day_n": int(len(ex)), "ex_top_day_mean": float(ex.mean()), "ex_top_day_ci95": list(bc.mean_ci(ex)),
                "day_clustered_mean": float(daymeans.mean()), "day_clustered_ci95": list(bc.mean_ci(daymeans)),
                "exit_mix": T["exit_reason"].value_counts().to_dict(),
                "by_month": T.groupby(pd.to_datetime(T["entry_ts"]).dt.strftime("%Y-%m"))["net_bps"].mean().round(1).to_dict(),
                "by_symbol_n": T.groupby("symbol")["net_bps"].size().to_dict(),
                "by_symbol_mean": T.groupby("symbol")["net_bps"].mean().round(1).to_dict()}
    T.to_csv(f"{OUT}/probe2_trades_{key}.csv", index=False)
    print(key, json.dumps({k: v for k, v in res[key].items() if k not in ("by_symbol_n", "by_symbol_mean")}, default=str))
json.dump(res, open(f"{OUT}/probe2_summary.json", "w"), indent=2, default=str)
print("lot_check", {s: fm.lot_check(s, fm.position_notional()) for s in syms})
