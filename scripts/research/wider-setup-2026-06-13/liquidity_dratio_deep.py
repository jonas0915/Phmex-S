"""Deep dive on depth_ratio. Per-symbol spearman, and decile table (extremes) for h=300.
Use per-symbol z-scored depth_ratio to remove cross-symbol scale differences."""
import sys
sys.path.insert(0, 'scripts/research/wider-setup-2026-06-13')
import numpy as np
from liquidity_load import load, COL, fwd_return

H = 300

def spearman(x, y):
    def rank(a):
        o = a.argsort(); r = np.empty(len(a)); r[o] = np.arange(len(a)); return r
    rx, ry = rank(x), rank(y)
    if rx.std()==0 or ry.std()==0: return float('nan')
    return float(np.corrcoef(rx, ry)[0,1])

def main():
    d = load()
    persym = []
    all_x = []; all_y = []
    for sym, arr in d.items():
        xs=[]; ys=[]
        for i in range(len(arr)):
            dr = arr[i, COL['dratio']]
            if np.isnan(dr) or not np.isfinite(dr): continue
            r = fwd_return(arr, i, H)
            if np.isnan(r): continue
            xs.append(dr); ys.append(r)
        if len(xs) < 200: continue
        xs=np.array(xs); ys=np.array(ys)
        rho = spearman(xs, ys)
        persym.append((sym, len(xs), rho))
        all_x.append(xs); all_y.append(ys)
    print('=== PER-SYMBOL spearman(depth_ratio, fwd300) ===')
    for s,n,rho in sorted(persym, key=lambda t:t[2]):
        print(f'  {s:20s} n={n:>6} rho={rho:+.4f}')
    rhos=np.array([t[2] for t in persym])
    print(f'\nmean per-sym rho={rhos.mean():+.4f} median={np.median(rhos):+.4f} '
          f'frac_negative={np.mean(rhos<0):.2f}  ({len(rhos)} symbols)')

    # pooled decile table
    X=np.concatenate(all_x); Y=np.concatenate(all_y)
    print(f'\n=== POOLED DECILE depth_ratio vs fwd300 (n={len(X)}) ===')
    qs=np.quantile(X, np.linspace(0,1,11))
    for b in range(10):
        lo,hi=qs[b],qs[b+1]
        m=(X>=lo)&(X<hi) if b<9 else (X>=lo)&(X<=hi)
        yy=Y[m]
        print(f'  D{b+1:>2} dr[{lo:.3f},{hi:.3f}] n={len(yy):>6} mean={yy.mean()*1e4:+.3f}bps wr_up={np.mean(yy>0):.3f}')

if __name__=='__main__':
    main()
