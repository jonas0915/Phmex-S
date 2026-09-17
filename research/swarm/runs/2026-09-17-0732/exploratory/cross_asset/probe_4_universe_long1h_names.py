"""EXPLORATORY — NOT THE SCREEN. Same RALLY_LAG short draft as probe_3 but on the
pre-existing long_1h major-name list intersected with mr_edge (excludes BTC as the
conditioner; NEAR absent from mr_edge). Universe chosen by a pre-existing list, not by
probe_3 per-symbol results. Train era only."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, screen as sc, fee_math as fm
LAG, THR, CAP = 4, 100.0, 0.5
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")["close"]
b_ret = np.log(btc / btc.shift(LAG)) * 1e4
uni = [s for s in ld.list_symbols("long_1h") if s in ld.list_symbols("mr_edge") and s != "BTC"]
print("universe", len(uni), uni)
def sig(df):
    b = b_ret.reindex(df.index); a = np.log(df["close"] / df["close"].shift(LAG)) * 1e4
    f = (b > THR) & (a < CAP * b)
    out = pd.Series(0, index=df.index, dtype=int); out[f.fillna(False)] = -1; return out
trades = []
for s in uni:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
    tr = sc.simulate(df, sig(df), 150, 150, 8); tr.insert(0, "symbol", s); trades.append(tr)
T = pd.concat(trades, ignore_index=True); x = T.net_bps.to_numpy(); n = len(T)
weeks = (df.index.max() - df.index.min()).total_seconds() / (7 * 86400)
lo, hi = bc.mean_ci(x)
print(f"n={n} net_mean {x.mean():.1f} CI ({lo:.1f},{hi:.1f}) WR {(x>0).mean():.3f} p* {fm.p_star(150):.4f} tr/wk {n/weeks:.1f} ttv_wk {fm.time_to_verdict_weeks(n/weeks):.2f}")
print("exits:", T.exit_reason.value_counts().to_dict(), "TIME gross mean:", round(T.loc[T.exit_reason=='TIME','gross_bps'].mean(),1))
T["m"] = pd.to_datetime(T.entry_ts).dt.month
print("by month:", T.groupby("m")["net_bps"].agg(["count","mean"]).round(1).to_dict())
print("lot_check:", {s: fm.lot_check(s, fm.position_notional())["ok"] for s in uni})
T.to_csv("research/swarm/runs/2026-09-17-0732/exploratory/cross_asset/probe_4_trades.csv", index=False)
