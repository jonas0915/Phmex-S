"""EXPLORATORY ONLY (not the screen, numbers are not evidence).
Probe: does the 04:00->08:00 UTC move into the Deribit 08:00 UTC expiry reverse over the
next 6h? long_1h dataset, era='train' only (ends ~2026-04-24; no mr_edge data used)."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld

rows = []
for sym in ["BTC", "ETH", "SOL", "XRP"]:
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    c, o = df["close"], df["open"]
    print(sym, df.index.min(), df.index.max(), len(df))
    for ts in df.index:
        if ts.hour != 7:
            continue
        i = df.index.get_loc(ts)
        if i < 3 or i + 6 >= len(df):
            continue
        pre = (c.iloc[i] / o.iloc[i - 3] - 1) * 1e4           # 04:00 open -> 08:00 close-of-07:00 bar
        post = (c.iloc[i + 6] / o.iloc[i + 1] - 1) * 1e4       # 08:00 open -> 14:00 close
        rows.append(dict(sym=sym, ts=ts, fri=ts.dayofweek == 4, lastfri=(ts.dayofweek == 4 and (ts + pd.Timedelta(days=7)).month != ts.month), pre=pre, post=post))
r = pd.DataFrame(rows)
for name, g in [("all_days", r), ("fridays", r[r.fri]), ("last_fridays", r[r.lastfri]), ("non_fri", r[~r.fri])]:
    for thr in (0, 50, 100):
        gg = g[g.pre.abs() > thr]
        fade = -np.sign(gg.pre) * gg.post
        print(f"{name:13s} |pre|>{thr:3d}: n={len(gg):4d} corr={gg[['pre','post']].corr().iloc[0,1]:+.3f} mean_fade_post_bps={fade.mean():+.1f} fade_win={(fade>0).mean():.3f}")
