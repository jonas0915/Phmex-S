"""EXPLORATORY ONLY — not the screen. Market-wide vs idiosyncratic cascade split.
long_1h TRAIN, 17 alts (GIGGLE, BTC excluded from the traded set). Condition: BTC's own
1h close-to-close return at the SAME closed bar <= -kb * BTC trailing-168h std (lagged).
BTC series is loaded from the same dataset/era and aligned on timestamp (only BTC bars at or
before each bar's own timestamp are used). No mr_edge data used."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc
OUT = "research/swarm/runs/2026-09-17-0732/exploratory/forced_flows"
syms = [s for s in ld.list_symbols("long_1h") if s not in ("GIGGLE", "BTC")]
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
rb = btc["close"].pct_change(); sdb = rb.rolling(168, min_periods=100).std().shift(1)
btc_z = (rb / sdb)
def sig(df, kb, k_alt, vmult, need_alt):
    r = df["close"].pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
    z_b = btc_z.reindex(df.index)
    cond = (z_b <= -kb)
    if need_alt:
        cond = cond & (r <= -k_alt * sd) & (df["volume"] >= vmult * vm)
    else:
        cond = cond & (r < 0)
    return pd.Series(np.where(cond.fillna(False), -1, 0), index=df.index).astype(int)
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in syms}
span = max(df.index.max() for df in frames.values()) - min(df.index.min() for df in frames.values())
weeks = span.total_seconds() / (7 * 86400)
res = {"weeks": weeks}
for kb, need_alt in [(2.5, True), (3.0, True), (3.0, False), (2.5, False), (4.0, False)]:
    for tp, hold in [(300, 24), (300, 36), (200, 24)]:
        trades = []
        for s, df in frames.items():
            t = sc.simulate(df, sig(df, kb, 2.0, 1.5, need_alt), tp, tp, hold); t.insert(0, "symbol", s); trades.append(t)
        T = pd.concat(trades, ignore_index=True)
        n = len(T)
        if n < 5: print(kb, need_alt, tp, hold, "n", n); continue
        x = T["net_bps"].to_numpy()
        T["day"] = pd.to_datetime(T["entry_ts"]).dt.date
        dm = T.groupby("day")["net_bps"].mean().to_numpy()
        top = T["day"].value_counts(); ex = T[T["day"] != top.index[0]]["net_bps"].to_numpy()
        key = f"kb{kb}_alt{need_alt}_tp{tp}_hold{hold}"
        res[key] = {"n": n, "net_mean": float(x.mean()), "ci95": list(bc.mean_ci(x)), "wr": float((x > 0).mean()), "p_star": fm.p_star(tp),
                    "trades_per_week": n / weeks, "ttv_weeks": fm.time_to_verdict_weeks(n / weeks), "distinct_days": int(len(dm)),
                    "day_clustered_mean": float(dm.mean()), "day_clustered_ci95": list(bc.mean_ci(dm)) if len(dm) >= 2 else None,
                    "top_day": str(top.index[0]), "top_day_n": int(top.iloc[0]), "ex_top_day_mean": float(ex.mean()) if len(ex) else None,
                    "ex_top_day_ci95": list(bc.mean_ci(ex)) if len(ex) >= 2 else None,
                    "exit_mix": T["exit_reason"].value_counts().to_dict(),
                    "by_month": T.groupby(pd.to_datetime(T["entry_ts"]).dt.strftime("%Y-%m"))["net_bps"].mean().round(1).to_dict()}
        T.to_csv(f"{OUT}/probe3_trades_{key}.csv", index=False)
        print(key, json.dumps(res[key], default=str))
json.dump(res, open(f"{OUT}/probe3_summary.json", "w"), indent=2, default=str)
