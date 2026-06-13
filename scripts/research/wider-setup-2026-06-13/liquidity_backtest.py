"""STEP 2/4/5: Trigger backtest with TP/SL, chronological 50/50 train/test, random baseline.
Trigger: depth_ratio extremes (contrarian). dr <= lo_thr => LONG (ask-heavy, fade sellers);
dr >= hi_thr => SHORT (bid-heavy, fade buyers).
Thresholds chosen on TRAIN by symbol-pooled quantiles. Report TEST net.
Exit: first-touch TP or SL scanning forward bars (no look-ahead), conservative SL-first on same bar.
Fees: 0.0663% and 0.12% RT subtracted from gross.
"""
import sys
sys.path.insert(0, 'scripts/research/wider-setup-2026-06-13')
import numpy as np
from liquidity_load import load, COL

np.random.seed(42)
MAX_HOLD = 1800  # seconds max hold
FEES = {'low': 0.000663, 'high': 0.0012}

def simulate_trade(arr, i, side, tp, sl):
    """Scan forward from i until TP or SL or MAX_HOLD. Returns gross signed return or None.
    SL-first within a bar (conservative)."""
    p0 = arr[i, 1]
    ts0 = arr[i, 0]
    n = len(arr)
    for j in range(i+1, n):
        if arr[j,0] - ts0 > MAX_HOLD:
            # close at this bar's price (timeout)
            ret = (arr[j,1]-p0)/p0
            return ret if side=='long' else -ret
        if arr[j,0] - ts0 > MAX_HOLD + 200:
            return None  # data hole, abandon
        chg = (arr[j,1]-p0)/p0
        signed = chg if side=='long' else -chg
        if signed <= -sl:
            return -sl
        if signed >= tp:
            return tp
    return None  # ran out of data

def collect_triggers(arr, lo_thr, hi_thr):
    trigs=[]  # (i, side)
    for i in range(len(arr)-1):
        dr = arr[i, COL['dratio']]
        if np.isnan(dr) or not np.isfinite(dr): continue
        if dr <= lo_thr:
            trigs.append((i,'long'))
        elif dr >= hi_thr:
            trigs.append((i,'short'))
    return trigs

def run(split='test', lo_thr=None, hi_thr=None, tp=0.006, sl=0.008, d=None, lo_pct=0.1, hi_pct=0.9):
    results=[]
    n_trig=0
    for sym, arr in d.items():
        half = len(arr)//2
        if split=='train':
            sub = arr[:half]
        else:
            sub = arr[half:]
        if len(sub) < 50: continue
        trigs = collect_triggers(sub, lo_thr, hi_thr)
        n_trig += len(trigs)
        for i, side in trigs:
            r = simulate_trade(sub, i, side, tp, sl)
            if r is not None:
                results.append(r)
    return np.array(results), n_trig

def main():
    d = load()
    # determine thresholds from TRAIN pooled depth_ratio distribution
    train_dr=[]
    for sym,arr in d.items():
        half=len(arr)//2
        sub=arr[:half]
        dr=sub[:,COL['dratio']]
        dr=dr[np.isfinite(dr)]
        train_dr.append(dr)
    TR=np.concatenate(train_dr)
    print(f'TRAIN depth_ratio n={len(TR)} median={np.median(TR):.3f}')

    grid_tp=[0.004,0.006,0.010]
    grid_sl=[0.005,0.008]
    grid_q=[(0.05,0.95),(0.10,0.90),(0.20,0.80)]

    print('\n=== TRAIN GRID (net @0.0663% RT) ===')
    best=None
    for (lq,hq) in grid_q:
        lo_thr=np.quantile(TR,lq); hi_thr=np.quantile(TR,hq)
        for tp in grid_tp:
            for sl in grid_sl:
                res,ntr=run('train',lo_thr,hi_thr,tp,sl,d)
                if len(res)==0: continue
                net=res - FEES['low']
                tot=net.sum(); avg=net.mean(); wr=np.mean(res>0)
                key=(lq,hq,tp,sl)
                print(f'  q({lq},{hq}) tp={tp} sl={sl} n={len(res):>5} wr={wr:.3f} '
                      f'avg_net={avg*1e4:+.2f}bps total_net={tot*100:+.2f}%')
                if best is None or tot>best[0]:
                    best=(tot,key,lo_thr,hi_thr,tp,sl)
    print(f'\nBEST TRAIN: total_net={best[0]*100:+.2f}% params q={best[1][:2]} tp={best[4]} sl={best[5]}')

    # Apply best to TEST
    _,_,lo_thr,hi_thr,tp,sl=best
    for feekey in ['low','high']:
        res,ntr=run('test',lo_thr,hi_thr,tp,sl,d)
        net=res-FEES[feekey]
        # span days of test for trigs/day
        print(f'\n=== TEST (fees={FEES[feekey]*100:.4f}% RT) ===')
        print(f'  trades={len(res)} triggers={ntr} wr={np.mean(res>0):.3f} '
              f'avg_net={net.mean()*1e4:+.2f}bps total_net={net.sum()*100:+.2f}% gross={res.sum()*100:+.2f}%')

    # random baseline on TEST: same #triggers, random entry rows, random side, same tp/sl
    res_real,ntr=run('test',lo_thr,hi_thr,tp,sl,d)
    n_real=len(res_real)
    real_total=(res_real-FEES['low']).sum()
    # build pool of all test rows
    test_arrs=[arr[len(arr)//2:] for arr in d.values() if len(arr[len(arr)//2:])>=50]
    beat=0; draws=1000
    rng=np.random.default_rng(7)
    rand_totals=[]
    for _ in range(draws):
        tot=0.0; cnt=0
        while cnt<n_real:
            a=test_arrs[rng.integers(len(test_arrs))]
            i=rng.integers(0,len(a)-1)
            side='long' if rng.random()<0.5 else 'short'
            r=simulate_trade(a,i,side,tp,sl)
            if r is not None:
                tot+=(r-FEES['low']); cnt+=1
        rand_totals.append(tot)
        if tot>=real_total: beat+=1
    rand_totals=np.array(rand_totals)
    print(f'\n=== RANDOM BASELINE (TEST, {draws} draws, n={n_real} each, tp={tp} sl={sl}) ===')
    print(f'  strategy total_net={real_total*100:+.2f}%')
    print(f'  random mean={rand_totals.mean()*100:+.2f}% std={rand_totals.std()*100:.2f}% '
          f'p5={np.percentile(rand_totals,5)*100:+.2f}% p95={np.percentile(rand_totals,95)*100:+.2f}%')
    print(f'  fraction of random draws BEATING strategy: {beat/draws:.3f} (p-value)')

if __name__=='__main__':
    main()
