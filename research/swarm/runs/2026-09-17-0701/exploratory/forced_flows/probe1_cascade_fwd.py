"""EXPLORATORY ONLY — not the screen, numbers are not evidence.
Probe: forward returns after a 'cascade bar' on long_1h TRAIN data (19 symbols).
Cascade bar = 1h close-to-close return <= -k * rolling(168) std of 1h returns, AND
volume >= v * rolling(168) median volume. Forward returns from next bar's open.
Also the mirror (up-cascade). Uses only long_1h era='train' — no mr_edge data touched."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","GIGGLE","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]
H = [6, 12, 24, 48, 72]
out = {}
for k in (3.0, 4.0, 5.0):
    for v in (2.0, 3.0):
        rows = []
        for s in SYMS:
            df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
            r = df.close.pct_change()
            sd = r.rolling(168, min_periods=100).std().shift(1)
            vm = df.volume.rolling(168, min_periods=100).median().shift(1)
            down = (r <= -k * sd) & (df.volume >= v * vm)
            up = (r >= k * sd) & (df.volume >= v * vm)
            o = df.open.to_numpy(); c = df.close.to_numpy(); n = len(df)
            for side, mask in ((-1, down), (1, up)):
                idx = np.flatnonzero(mask.to_numpy())
                last = -10**9
                for i in idx:
                    if i + 1 >= n or i - last < 24:  # de-cluster: one event per 24h
                        continue
                    last = i
                    e = o[i + 1]
                    row = {"sym": s, "side": side, "ts": str(df.index[i]), "k": k, "v": v}
                    for h in H:
                        j = min(i + 1 + h, n - 1)
                        row[f"fwd{h}"] = side * (c[j] / e - 1) * 1e4  # bps in direction of continuation
                    rows.append(row)
        t = pd.DataFrame(rows)
        for side in (-1, 1):
            tt = t[t.side == side]
            key = f"k{k}_v{v}_side{side}"
            out[key] = {"n": int(len(tt)), **{f"mean_fwd{h}_bps": float(tt[f"fwd{h}"].mean()) for h in H},
                        **{f"pos_frac_fwd{h}": float((tt[f"fwd{h}"] > 0).mean()) for h in H}}
        t.to_csv(f"/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/probe1_events_k{k}_v{v}.csv", index=False)
json.dump(out, open("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/probe1_summary.json", "w"), indent=2)
for kk, vv in out.items():
    print(kk, json.dumps({a: round(b, 3) if isinstance(b, float) else b for a, b in vv.items()}))
