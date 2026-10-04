"""EXPLORATORY ONLY (not the screen, numbers are not evidence).
long_1h TRAIN era only (ends ~2026-04-24); no mr_edge data touched.
Descriptive: at 20:00 UTC on the 3rd-to-last calendar day of each month, month-to-date
return vs forward 120h return, per symbol. Counts how many month-end events exist in train."""
import pandas as pd
from research.swarm.lib import load_data as ld

for sym in ["BTC", "ETH", "SOL", "XRP"]:
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    print(sym, "train", df.index[0], "->", df.index[-1], "bars", len(df))
    rows = []
    for per, g in df.groupby(df.index.to_period("M")):
        dim = per.days_in_month
        t = pd.Timestamp(year=per.year, month=per.month, day=dim - 2, hour=20, tz="UTC")
        if t not in df.index or g.index[0].day != 1:
            continue
        mtd = df.loc[t, "close"] / g["open"].iloc[0] - 1
        fwd_end = t + pd.Timedelta(hours=120)
        if fwd_end not in df.index:
            continue
        fwd = df.loc[fwd_end, "close"] / df.loc[t, "close"] - 1
        rows.append((str(per), round(mtd * 1e4), round(fwd * 1e4)))
    for r in rows:
        print("  ", r)
    print("  n_events", len(rows))
