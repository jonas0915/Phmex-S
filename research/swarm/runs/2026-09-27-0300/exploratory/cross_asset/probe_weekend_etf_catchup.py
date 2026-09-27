"""EXPLORATORY (not the screen, numbers are not evidence). long_1h TRAIN era only.
Counts Monday weekend-gap events for the one registered config and the signed forward
close-to-close return at the registered horizon (30 bars). No mr_edge data is read."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sig", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tot = 0
for sym in ["BTC", "ETH", "SOL", "XRP", "DOGE"]:
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    s = m.signals(df).reindex(df.index).fillna(0).astype(int)
    ev = s[s != 0]
    fwd = []
    for ts, side in ev.items():
        i = df.index.get_loc(ts)
        if i + 31 < len(df):
            fwd.append(side * (df["close"].iloc[i + 31] / df["open"].iloc[i + 1] - 1) * 1e4)
    tot += len(ev)
    print(sym, "span", df.index.min(), df.index.max(), "events", len(ev), "long", int((ev > 0).sum()), "short", int((ev < 0).sum()),
          "mean_signed_fwd30_bps(descriptive)", round(float(np.mean(fwd)), 2) if fwd else None)
weeks = (df.index.max() - df.index.min()).total_seconds() / (7 * 86400)
print("total_events", tot, "train_weeks", round(weeks, 2))
