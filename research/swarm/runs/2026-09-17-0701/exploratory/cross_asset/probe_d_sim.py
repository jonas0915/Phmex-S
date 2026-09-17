"""EXPLORATORY sim of the draft signal with screen.simulate on mr_edge 1h TRAIN. Not the screen."""
import sys, numpy as np, pandas as pd
from pathlib import Path
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm, screen as sc
sig_fn = sc.load_signal_fn(Path("research/swarm/runs/2026-09-17-0701/exploratory/cross_asset/signal_draft.py"))
btc_tr_max = ld.load_ohlcv("BTC","1h",era="train",dataset="mr_edge").index.max()
uni=[]; trades=[]
for s in ld.list_symbols("mr_edge"):
    if s in ("BTC","ETH"): continue
    df = ld.load_ohlcv(s,"1h",era="train",dataset="mr_edge")
    if df.index.max()!=btc_tr_max or df.index.min()!=pd.Timestamp("2026-06-01",tz="UTC"):
        print("EXCLUDE (train span differs from BTC):", s, df.index.min(), df.index.max()); continue
    uni.append(s)
    sc.causality_check(sig_fn, df, symbol=s)
    tr = sc.simulate(df, sig_fn(df), 150, 150, 8); tr.insert(0,"symbol",s); trades.append(tr)
T = pd.concat(trades); x=T.net_bps.to_numpy()
weeks=(btc_tr_max-pd.Timestamp("2026-06-01",tz="UTC")).total_seconds()/(7*86400)
print("universe", len(uni), uni)
print(f"n={len(x)} net_mean={x.mean():.1f} ci95={bc.mean_ci(x)} wr={(x>0).mean():.3f} p_star={fm.p_star(150):.4f} tpw={len(x)/weeks:.1f} ttv_weeks={fm.time_to_verdict_weeks(len(x)/weeks):.1f}")
print(T.exit_reason.value_counts())
print(T.assign(m=T.entry_ts.dt.month).groupby("m").net_bps.agg(["count","mean"]))
print({s: fm.lot_check(s, fm.position_notional())["ok"] for s in uni})
