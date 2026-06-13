"""STEP 3: Liquidity as a FILTER on a baseline short-horizon reversion entry.
Baseline entry: price moved down >X% over last ~300s -> LONG (reversion), or up >X% -> SHORT.
Then condition (filter) on liquidity state: tight spread / deep book / not illiquid.
Compare net of filtered vs unfiltered on TEST. Thresholds from TRAIN.
Exit: tp/sl best from prior step (tp=0.006, sl=0.005 symmetric-ish) + a 0.4% tp variant.
Fees 0.0663%.
"""
import sys
sys.path.insert(0, 'scripts/research/wider-setup-2026-06-13')
import numpy as np
from liquidity_load import load, COL
from liquidity_backtest import simulate_trade, FEES

LOOKBACK = 300

def past_return(arr, i, lb=LOOKBACK, tol=120):
    ts=arr[i,0]; p0=arr[i,1]; target=ts-lb
    tcol=arr[:,0]
    j=np.searchsorted(tcol, target, side='left')
    # j is first >= target; pick closest among j-1,j that is <= i
    cands=[c for c in (j-1,j) if 0<=c<i]
    if not cands: return np.nan
    best=min(cands, key=lambda c: abs(tcol[c]-target))
    if abs(tcol[best]-target)>tol: return np.nan
    pp=arr[best,1]
    if pp<=0: return np.nan
    return (p0-pp)/pp

def collect(arr, move_thr, filt, spread_thr, deep_thr):
    """filt in {'none','tight','deep','notilliquid','tight_deep'}"""
    trigs=[]
    for i in range(1,len(arr)-1):
        pr=past_return(arr,i)
        if np.isnan(pr): continue
        # reversion: big down move -> long, big up move -> short
        if pr <= -move_thr: side='long'
        elif pr >= move_thr: side='short'
        else: continue
        # apply filter
        sp=arr[i,COL['spread']]; dr=arr[i,COL['dratio']]
        bd=arr[i,COL['bd']]; ad=arr[i,COL['ad']]; il=arr[i,COL['illiquid']]
        depth=(bd+ad) if (not np.isnan(bd) and not np.isnan(ad)) else np.nan
        if filt=='tight' and not (not np.isnan(sp) and sp<=spread_thr): continue
        if filt=='deep' and not (not np.isnan(depth) and depth>=deep_thr): continue
        if filt=='notilliquid' and il==1: continue
        if filt=='tight_deep' and not (not np.isnan(sp) and sp<=spread_thr and not np.isnan(depth) and depth>=deep_thr): continue
        trigs.append((i,side))
    return trigs

def run(d, split, move_thr, filt, spread_thr, deep_thr, tp, sl):
    res=[]
    for sym,arr in d.items():
        half=len(arr)//2
        sub=arr[:half] if split=='train' else arr[half:]
        if len(sub)<50: continue
        for i,side in collect(sub,move_thr,filt,spread_thr,deep_thr):
            r=simulate_trade(sub,i,side,tp,sl)
            if r is not None: res.append(r)
    return np.array(res)

def main():
    d=load()
    # TRAIN-derived thresholds
    sp_all=[]; depth_all=[]
    for sym,arr in d.items():
        half=len(arr)//2; sub=arr[:half]
        s=sub[:,COL['spread']]; sp_all.append(s[np.isfinite(s)])
        bd=sub[:,COL['bd']]; ad=sub[:,COL['ad']]
        dp=bd+ad; depth_all.append(dp[np.isfinite(dp)])
    sp_all=np.concatenate(sp_all); depth_all=np.concatenate(depth_all)
    spread_thr=np.quantile(sp_all,0.5)   # tighter than median
    deep_thr=np.quantile(depth_all,0.5)  # deeper than median
    print(f'TRAIN spread median(thr)={spread_thr:.4f}  depth median(thr)={deep_thr:.0f} USDT')

    for move_thr in [0.004, 0.008]:
        for (tp,sl) in [(0.006,0.005),(0.004,0.005),(0.010,0.005)]:
            print(f'\n--- move_thr={move_thr*100:.1f}% reversion, tp={tp} sl={sl} ---')
            for filt in ['none','tight','deep','notilliquid','tight_deep']:
                res=run(d,'test',move_thr,filt,spread_thr,deep_thr,tp,sl)
                if len(res)==0:
                    print(f'  TEST {filt:12s} n=0'); continue
                net=res-FEES['low']
                print(f'  TEST {filt:12s} n={len(res):>5} wr={np.mean(res>0):.3f} '
                      f'avg_net={net.mean()*1e4:+.2f}bps total={net.sum()*100:+.1f}%')

if __name__=='__main__':
    main()
