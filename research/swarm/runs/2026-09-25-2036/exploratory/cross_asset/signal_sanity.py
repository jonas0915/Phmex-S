"""EXPLORATORY sanity: signal values + a prefix-causality spot check on long_1h TRAIN (no PnL)."""
import importlib.util, numpy as np, pandas as pd
from research.swarm.lib import load_data as ld
spec = importlib.util.spec_from_file_location("s", "research/swarm/runs/2026-09-25-2036/exploratory/cross_asset/signal_draft.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for s in ["BTC","ETH","1000PEPE"]:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    sig = m.signals(df)
    assert set(sig.unique()) <= {-1,0,1}
    bad = 0
    fires = sig[sig != 0].index
    for t in list(fires) + list(df.index[::500]):
        p = df.loc[:t]
        if m.signals(p).iloc[-1] != sig.loc[t]: bad += 1
    print(s, "values", sorted(sig.unique()), "fires", (sig!=0).sum(), "prefix mismatches", bad)
