"""EXPLORATORY (not the screen, not evidence). long_1h TRAIN only via load_data.
Round-number crossing (1-significant-figure grid (major figure: BTC 100k, ETH 1000s, SOL 100s)) vs placebo grid shifted by 0.37 step.
Forward signed return (in cross direction) at h=1,3,6,12 bars from next open.
Variants tried (all listed): grid offset 0.0 (round) and 0.37 (placebo). Nothing else."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]
H = [1,3,6,12]
def events(df, off):
    c = df.close.to_numpy(); o = df.open.to_numpy()
    prev = np.r_[np.nan, c[:-1]]
    step = 10.0 ** (np.floor(np.log10(prev)) - 0)
    lvl_up = (np.floor(prev/step - off) + 1 + off) * step   # first grid level above prev close
    lvl_dn = (np.ceil(prev/step - off) - 1 + off) * step    # first grid level below prev close
    up = (c >= lvl_up); dn = (c <= lvl_dn)
    side = np.where(up & ~dn, 1, np.where(dn & ~up, -1, 0))
    out = []
    for i in np.nonzero(side)[0]:
        if i+1+max(H) >= len(c): continue
        e = o[i+1]
        out.append([side[i]] + [side[i]*(c[i+h]/e-1)*1e4 for h in H])
    return pd.DataFrame(out, columns=["side"]+[f"h{h}" for h in H])
res = {}
for off in (0.0, 0.37):
    frames = []
    for s in SYMS:
        df = load_data.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        ev = events(df, off); ev["sym"] = s; frames.append(ev)
        if off == 0.0: print(s, "train", df.index.min(), df.index.max(), "events", len(ev))
    a = pd.concat(frames)
    res[off] = a
    print(f"offset={off} n={len(a)} up={int((a.side==1).sum())} dn={int((a.side==-1).sum())}")
    print("  mean signed fwd bps:", {h: round(a[f'h{h}'].mean(),2) for h in H})
    print("  up-only:", {h: round(a[a.side==1][f'h{h}'].mean(),2) for h in H}, " dn-only:", {h: round(a[a.side==-1][f'h{h}'].mean(),2) for h in H})
    print("  median:", {h: round(a[f'h{h}'].median(),2) for h in H})
