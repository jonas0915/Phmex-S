"""EXPLORATORY probe (not the screen; numbers are not evidence).
mr_edge 1h TRAIN only. Does the lagged BTC (or ETH/BTC ratio) 1h/4h move predict alt returns
over the next k hours beyond the alt's own lagged return? Cross-sectional pooled regression + conditional means."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm
btc = ld.load_ohlcv("BTC","1h",era="train",dataset="mr_edge")["close"]
eth = ld.load_ohlcv("ETH","1h",era="train",dataset="mr_edge")["close"]
print("train span", btc.index.min(), btc.index.max())
alts = [s for s in ld.list_symbols("mr_edge") if s not in ("BTC","ETH")]
rows=[]
for s in alts:
    c = ld.load_ohlcv(s,"1h",era="train",dataset="mr_edge")["close"]
    d = pd.DataFrame({"c":c}).join(btc.rename("b"), how="inner").join(eth.rename("e"), how="inner")
    for L in (1,4,24):
        d[f"b{L}"] = np.log(d.b/d.b.shift(L))*1e4
        d[f"a{L}"] = np.log(d.c/d.c.shift(L))*1e4
        d[f"r{L}"] = np.log((d.e/d.b)/(d.e/d.b).shift(L))*1e4
    for K in (1,4,8,24):
        d[f"f{K}"] = np.log(d.c.shift(-K)/d.c)*1e4   # forward return (probe only)
    d["sym"]=s; rows.append(d.dropna())
D = pd.concat(rows)
print("pooled rows", len(D))
for L in (1,4,24):
    for K in (1,4,8,24):
        x = D[[f"b{L}", f"a{L}"]].to_numpy(); y = D[f"f{K}"].to_numpy()
        X = np.c_[np.ones(len(x)), x]
        beta = np.linalg.lstsq(X,y,rcond=None)[0]
        resid = y - X@beta; s2 = resid@resid/(len(y)-3); cov = s2*np.linalg.inv(X.T@X)
        t = beta/np.sqrt(np.diag(cov))
        print(f"lagBTC L={L}h -> alt fwd K={K}h: beta_btc={beta[1]:.4f} t={t[1]:.2f} | beta_own={beta[2]:.4f} t={t[2]:.2f}")
# Conditional: BTC big up/down move over L, alt lagged less than half of it (alt 'late') -> next K
for L,K in ((1,4),(4,8),(4,24),(24,24)):
    thr = D[f"b{L}"].abs().quantile(0.9)
    up = D[(D[f"b{L}"]>thr)&(D[f"a{L}"]<0.5*D[f"b{L}"])][f"f{K}"].to_numpy()
    dn = D[(D[f"b{L}"]<-thr)&(D[f"a{L}"]>0.5*D[f"b{L}"])][f"f{K}"].to_numpy()
    print(f"L={L} K={K} thr={thr:.0f}bps  late-up n={len(up)} mean={up.mean():.1f} ci={bc.mean_ci(up)}  late-dn n={len(dn)} mean={dn.mean():.1f} ci={bc.mean_ci(dn)}")
# ETH/BTC ratio regime
for L,K in ((24,8),(24,24)):
    thr = D[f"r{L}"].abs().quantile(0.8)
    up = D[D[f"r{L}"]>thr][f"f{K}"].to_numpy(); dn = D[D[f"r{L}"]<-thr][f"f{K}"].to_numpy()
    print(f"ETHBTC L={L} K={K} thr={thr:.0f}bps ratio-up n={len(up)} mean={up.mean():.1f} ci={bc.mean_ci(up)} ratio-dn n={len(dn)} mean={dn.mean():.1f} ci={bc.mean_ci(dn)}")
