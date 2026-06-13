"""STEP 1: Descriptive. Bucket snapshots by microstructure features, compute forward
returns over {300,900,1800}s. Spearman correlation feature vs forward return (with n).
Also illiquid-flag conditional means. No look-ahead."""
import sys
sys.path.insert(0, 'scripts/research/wider-setup-2026-06-13')
import numpy as np
from liquidity_load import load, COL, fwd_return

HORIZONS = [300, 900, 1800]
np.random.seed(0)

def spearman(x, y):
    # rank-based pearson
    def rank(a):
        order = a.argsort()
        r = np.empty(len(a), float)
        r[order] = np.arange(len(a))
        return r
    rx, ry = rank(x), rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return float('nan')
    return float(np.corrcoef(rx, ry)[0, 1])

def main():
    d = load()
    # Build flat arrays: feature values + forward returns per horizon, pooled across symbols.
    feats = {'spread': [], 'dratio': [], 'walldiff': [], 'illiquid': []}
    fwd = {h: [] for h in HORIZONS}
    feat_store = {k: [] for k in feats}
    # we store per-snapshot the features and the 3 fwd returns; only keep rows where all 3 fwd valid
    rows_spread = {h: ([], []) for h in HORIZONS}  # (feat, ret)
    rows_dratio = {h: ([], []) for h in HORIZONS}
    rows_walld = {h: ([], []) for h in HORIZONS}
    illq = {h: ([], []) for h in HORIZONS}  # (flag, ret)

    for sym, arr in d.items():
        n = len(arr)
        for i in range(n):
            sp = arr[i, COL['spread']]
            dr = arr[i, COL['dratio']]
            wd = arr[i, COL['walldiff']]
            il = arr[i, COL['illiquid']]
            for h in HORIZONS:
                r = fwd_return(arr, i, h)
                if np.isnan(r):
                    continue
                if not np.isnan(sp):
                    rows_spread[h][0].append(sp); rows_spread[h][1].append(r)
                if not np.isnan(dr) and np.isfinite(dr):
                    rows_dratio[h][0].append(dr); rows_dratio[h][1].append(r)
                rows_walld[h][0].append(wd); rows_walld[h][1].append(r)
                illq[h][0].append(il); illq[h][1].append(r)

    def report_feature(name, store):
        print(f'\n===== FEATURE: {name} =====')
        for h in HORIZONS:
            x = np.array(store[h][0]); y = np.array(store[h][1])
            if len(x) < 50:
                print(f'  h={h}s  n={len(x)}  too few'); continue
            rho = spearman(x, y)
            # quintile buckets
            qs = np.quantile(x, [0, .2, .4, .6, .8, 1.0])
            print(f'  h={h}s  n={len(x):>7}  spearman_rho={rho:+.4f}')
            line = '    quintile mean_fwd_ret(bps): '
            cells = []
            for b in range(5):
                lo, hi = qs[b], qs[b+1]
                if b < 4:
                    m = (x >= lo) & (x < hi)
                else:
                    m = (x >= lo) & (x <= hi)
                yy = y[m]
                if len(yy):
                    cells.append(f'Q{b+1}={np.mean(yy)*1e4:+.2f}(n{len(yy)})')
            print(line + ' '.join(cells))

    report_feature('spread_pct', rows_spread)
    report_feature('depth_ratio (bid/ask)', rows_dratio)
    report_feature('walldiff (bid_walls-ask_walls)', rows_walld)

    print('\n===== ILLIQUID FLAG =====')
    for h in HORIZONS:
        fl = np.array(illq[h][0]); y = np.array(illq[h][1])
        m0 = fl == 0; m1 = fl == 1
        print(f'  h={h}s  liquid n={m0.sum()} mean={np.mean(y[m0])*1e4:+.3f}bps | illiquid n={m1.sum()} mean={(np.mean(y[m1])*1e4 if m1.sum() else float("nan")):+.3f}bps')

if __name__ == '__main__':
    main()
