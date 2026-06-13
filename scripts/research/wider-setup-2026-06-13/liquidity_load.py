"""Shared loader for liquidity microstructure analysis.
Builds per-symbol sorted arrays of (ts, price, features) for no-look-ahead forward returns.
"""
import json
import numpy as np
from collections import defaultdict

FLOW = 'logs/flow_capture.jsonl'

def load():
    per = defaultdict(list)
    with open(FLOW) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            ob = r.get('ob')
            if ob is None:
                continue
            price = r.get('price')
            if price is None or price <= 0:
                continue
            sym = r['symbol']
            spread = ob.get('spread_pct')
            bd = ob.get('bid_depth_usdt')
            ad = ob.get('ask_depth_usdt')
            bw = ob.get('bid_walls')
            aw = ob.get('ask_walls')
            illq = ob.get('illiquid')
            # depth ratio bid/ask
            if bd is None or ad is None or ad <= 0:
                dratio = np.nan
            else:
                dratio = bd / ad
            walldiff = (bw if bw is not None else 0) - (aw if aw is not None else 0)
            per[sym].append((
                r['ts'], price,
                spread if spread is not None else np.nan,
                bd if bd is not None else np.nan,
                ad if ad is not None else np.nan,
                dratio,
                walldiff,
                1 if illq else 0,
            ))
    # sort each by ts, dedupe ts keeping first
    out = {}
    for sym, rows in per.items():
        rows.sort(key=lambda x: x[0])
        arr = np.array(rows, dtype=float)
        out[sym] = arr  # cols: ts,price,spread,bd,ad,dratio,walldiff,illiquid
    return out

COL = {'ts':0,'price':1,'spread':2,'bd':3,'ad':4,'dratio':5,'walldiff':6,'illiquid':7}

def fwd_return(arr, i, horizon, tol=120):
    """Forward return from row i over `horizon` seconds.
    Lookup: nearest snapshot to ts+horizon (no look-ahead beyond i). The matched
    snapshot ts must be within `tol` seconds of target, else returns nan (spans a data hole)."""
    ts = arr[i,0]; p0 = arr[i,1]
    target = ts + horizon
    tcol = arr[:,0]
    # candidate just before-or-at target
    j = np.searchsorted(tcol, target, side='right') - 1
    if j <= i:
        # nothing at/after target within array beyond i
        # try the first snapshot after i if it lands near target
        k = i + 1
        if k < len(tcol) and abs(tcol[k] - target) <= tol:
            j = k
        else:
            return np.nan
    # pick whichever of j and j+1 is closest to target (j+1 may overshoot but be closer)
    best = j
    if j + 1 < len(tcol) and abs(tcol[j+1] - target) < abs(tcol[j] - target):
        best = j + 1
    if best <= i:
        return np.nan
    if abs(tcol[best] - target) > tol:
        return np.nan
    p1 = arr[best,1]
    if p0 <= 0:
        return np.nan
    return (p1 - p0) / p0

if __name__ == '__main__':
    d = load()
    print('symbols', len(d), 'total rows', sum(len(v) for v in d.values()))
