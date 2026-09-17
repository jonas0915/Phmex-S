"""EXPLORATORY — NOT THE SCREEN. Draft simulate() pass on mr_edge 1h train for two
candidate signals, using lib.screen.simulate (one position per symbol, SL-first ties).
Numbers shape the spec only; the registered screen is the evidence.
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, screen as sc, fee_math as fm

LAG, THR, CAP = 4, 100.0, 0.5
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")["close"]
b_ret = np.log(btc / btc.shift(LAG)) * 1e4
syms = [s for s in ld.list_symbols("mr_edge") if s not in ("BTC",)]

def sig_rally_lag(df):
    b = b_ret.reindex(df.index); a = np.log(df["close"] / df["close"].shift(LAG)) * 1e4
    f = (b > THR) & (a < CAP * b)
    out = pd.Series(0, index=df.index, dtype=int); out[f.fillna(False)] = -1; return out

def sig_crash_overshoot(df):
    b = b_ret.reindex(df.index); a = np.log(df["close"] / df["close"].shift(LAG)) * 1e4
    f = (b < -THR) & (a < 1.5 * b)
    out = pd.Series(0, index=df.index, dtype=int); out[f.fillna(False)] = 1; return out

def run(name, fn, tp, sl, hold, universe):
    trades = []
    for s in universe:
        df = ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
        tr = sc.simulate(df, fn(df), tp, sl, hold); tr.insert(0, "symbol", s); trades.append(tr)
    T = pd.concat(trades, ignore_index=True)
    n = len(T); x = T["net_bps"].to_numpy()
    weeks = (df.index.max() - df.index.min()).total_seconds() / (7 * 86400)
    lo, hi = bc.mean_ci(x)
    print(f"{name} tp={tp} sl={sl} hold={hold}: n={n} net_mean {x.mean():.1f} CI ({lo:.1f},{hi:.1f}) "
          f"WR {(x>0).mean():.3f} p* {fm.p_star(tp):.4f} tr/wk {n/weeks:.1f} ttv_wk {fm.time_to_verdict_weeks(n/weeks):.1f}")
    print("   exits:", T.exit_reason.value_counts().to_dict(),
          "TIME gross mean:", round(T.loc[T.exit_reason=='TIME','gross_bps'].mean(),1) if (T.exit_reason=='TIME').any() else None)
    T["m"] = pd.to_datetime(T.entry_ts).dt.month
    print("   by month:", T.groupby("m")["net_bps"].agg(["count", "mean"]).round(1).to_dict())
    return T

T1 = run("RALLY_LAG short", sig_rally_lag, 150, 150, 8, syms)
T1.to_csv("research/swarm/runs/2026-09-17-0732/exploratory/cross_asset/probe_3_rally_lag_trades.csv", index=False)
T2 = run("CRASH_OVERSHOOT long", sig_crash_overshoot, 150, 150, 8, syms)
T2.to_csv("research/swarm/runs/2026-09-17-0732/exploratory/cross_asset/probe_3_crash_overshoot_trades.csv", index=False)
# per-symbol net for T1 (which names carry it)
print("RALLY_LAG per-symbol net mean:", T1.groupby("symbol")["net_bps"].agg(["count", "mean"]).round(0).to_dict())
