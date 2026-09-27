"""EXPLORATORY (not the screen, not evidence). long_1h TRAIN only via load_data.
Stop-sweep-and-reclaim: 1h bar pierces the prior N-bar extreme (where stop/liquidation orders cluster
just beyond, Osler SR150) but CLOSES back inside. Fade direction = -1 after an upside sweep, +1 after
downside sweep. Forward signed return from next open at h=1,3,6,12,24. Variants tried (all listed):
N in {24, 72}; plus a breakout-hold control (close beyond extreme) with the same N."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]
H = [1,3,6,12,24]
for N in (24, 72):
    rows = {"sweep_fade": [], "breakout_hold": []}
    for s in SYMS:
        df = load_data.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        ph = df.high.rolling(N).max().shift(1); pl = df.low.rolling(N).min().shift(1)
        o, c = df.open.to_numpy(), df.close.to_numpy()
        up_sweep = (df.high > ph) & (df.close < ph); dn_sweep = (df.low < pl) & (df.close > pl)
        up_bo = df.close > ph; dn_bo = df.close < pl
        for name, sd in (("sweep_fade", np.where(up_sweep, -1, np.where(dn_sweep, 1, 0))),
                         ("breakout_hold", np.where(up_bo, 1, np.where(dn_bo, -1, 0)))):
            for i in np.nonzero(sd)[0]:
                if i + 1 + max(H) >= len(c): continue
                e = o[i+1]
                rows[name].append([s, sd[i]] + [sd[i]*(c[i+h]/e-1)*1e4 for h in H])
    for name, r in rows.items():
        a = pd.DataFrame(r, columns=["sym","side"]+[f"h{h}" for h in H])
        print(f"N={N} {name} n={len(a)} long={int((a.side==1).sum())} short={int((a.side==-1).sum())}")
        print("   mean:", {h: round(a[f'h{h}'].mean(),2) for h in H})
        print("   long:", {h: round(a[a.side==1][f'h{h}'].mean(),2) for h in H}, "short:", {h: round(a[a.side==-1][f'h{h}'].mean(),2) for h in H})
