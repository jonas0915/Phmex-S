#!/usr/bin/env python3
"""Screening-grade order-flow screen on recorded Phemex L2 ticks (read-only).
Per symbol-day: 1s mid/depth series, OFI (Cont-Kukanov-Stoikov top-of-book), trade signed volume.
Event A (sweep+rebuild reversal), Event B (tape-imbalance + thin-ask continuation), plus data quality.
Outputs JSON to the same folder. No bot code imported."""
import gzip, json, sys, math, statistics as st
from pathlib import Path
from collections import defaultdict
REPO = Path('/Users/jonaspenaso/Desktop/Phmex-S/logs/l2_ticks')
OUT = Path(__file__).resolve().parent

def opener(p):
    return gzip.open(p,'rt') if str(p).endswith('.gz') else open(p,'rt')

def load_day(sym, day):
    d = REPO/f'{sym}_USDT_USDT'
    bf = None
    for ext in ('.jsonl.gz','.jsonl'):
        if (d/f'{day}{ext}').exists(): bf = d/f'{day}{ext}'
    tf = None
    for ext in ('.jsonl.gz','.jsonl'):
        if (d/f'trades-{day}{ext}').exists(): tf = d/f'trades-{day}{ext}'
    if bf is None or tf is None: return None
    # per-second aggregation
    sec = {}  # s -> dict
    prev = None; nrows=0; gaps=[]; lat=[]; last_et=None
    ofi_sec = defaultdict(float)
    with opener(bf) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            if not r.get('b') or not r.get('a'): continue
            nrows += 1
            et = r['et']; s = et//1000
            if last_et is not None: gaps.append(et-last_et)
            last_et = et
            if nrows % 50 == 0: lat.append(r['ts']-et)
            pb,qb = r['b'][0]; pa,qa = r['a'][0]
            if prev is not None:
                ppb,pqb,ppa,pqa = prev
                e = (qb if pb>=ppb else 0) - (pqb if pb<=ppb else 0) - (qa if pa<=ppa else 0) + (pqa if pa>=ppa else 0)
                ofi_sec[s] += e
            prev = (pb,qb,pa,qa)
            bd = sum(p*q for p,q in r['b']); ad = sum(p*q for p,q in r['a'])
            sec[s] = ((pb+pa)/2, pb, pa, bd, ad)
    trades = defaultdict(lambda:[0.0,0.0])  # s -> [buy_usd, sell_usd]
    ntr=0
    with opener(tf) as fh:
        for line in fh:
            try: r=json.loads(line)
            except Exception: continue
            ntr+=1; s=r['et']//1000; v=r['px']*r['sz']
            trades[s][0 if r['side']=='buy' else 1] += v
    return dict(sec=sec, ofi=ofi_sec, trades=trades, nrows=nrows, ntr=ntr, gaps=gaps, lat=lat)

def fwd(sec, s, h):
    # forward mid at s+h (nearest available within +5s)
    for k in range(h, h+6):
        v = sec.get(s+k)
        if v: return v[0]
    return None

def run(sym, days, sweep_bps, win=3, rebuild_s=10):
    resA=[]; resB=[]; resC=[]; dq=[]
    for day in days:
        D = load_day(sym, day)
        if D is None: print('missing',sym,day); continue
        sec=D['sec']; ofi=D['ofi']; tr=D['trades']
        keys=sorted(sec)
        g=D['gaps']; lat=D['lat']
        dq.append(dict(day=day, book_rows=D['nrows'], trade_rows=D['ntr'], secs_with_book=len(keys),
                       max_gap_s=max(g)/1000 if g else None, gaps_gt5s=sum(1 for x in g if x>5000),
                       lat_ms_median=st.median(lat) if lat else None))
        # realized 15-min range dist (bps) for geometry sanity
        rng=[]
        for s in keys[::900]:
            m0=sec[s][0]; hi=lo=m0
            for k in range(s, s+900):
                v=sec.get(k)
                if v: hi=max(hi,v[0]); lo=min(lo,v[0])
            rng.append((hi-lo)/m0*1e4)
        resC.append(dict(day=day, range15m_bps_median=st.median(rng) if rng else None,
                         range15m_bps_p75=sorted(rng)[int(len(rng)*0.75)] if rng else None))
        # rolling 1h median depth per side for thinness
        # Event A: mid moves >= sweep_bps within `win` s on trade burst, then rebuild within rebuild_s
        last_evt=-10**9
        for s in keys:
            v0=sec.get(s-win); v1=sec.get(s)
            if not v0 or not v1: continue
            mv=(v1[0]-v0[0])/v0[0]*1e4
            if abs(mv) < sweep_bps or s-last_evt < 60: continue
            side = 1 if mv>0 else -1  # +1 = up-sweep (asks eaten)
            # swept side depth before vs after
            dep_before = v0[4] if side>0 else v0[3]
            dep_after = v1[4] if side>0 else v1[3]
            tv = sum(tr[k][0]-tr[k][1] for k in range(s-win, s+1))
            # rebuild: within rebuild_s, swept side depth back to >=80% of before AND OFI sign against sweep
            reb=False; ofi_after=0.0
            for k in range(s+1, s+rebuild_s+1):
                vk=sec.get(k); ofi_after += ofi.get(k,0.0)
                if vk and ((vk[4] if side>0 else vk[3]) >= 0.8*dep_before): reb=True
            ofi_against = (ofi_after*side) < 0
            row=dict(day=day, s=s, side=side, move_bps=mv, dep_before=dep_before, dep_after=dep_after,
                     tape_signed_usd=tv, rebuild=reb, ofi_against=ofi_against)
            for h in (60,300,900):
                f=fwd(sec, s+rebuild_s, h); base=fwd(sec, s+rebuild_s, 0)
                row[f'r{h}_bps'] = None if (f is None or base is None) else (f-base)/base*1e4*(-side)  # + = reversal profit
            resA.append(row); last_evt=s
        # Event B: 60s signed tape imbalance extreme + mid at 30-min high/low + thin far side
        # compute 60s rolling signed tape and 30-min high/low
        tape60={}; acc=0.0
        for s in keys:
            acc = sum(tr[k][0]-tr[k][1] for k in range(s-59,s+1))
            tape60[s]=acc
        vals=sorted(abs(x) for x in tape60.values() if x)
        if not vals: continue
        thr=vals[int(len(vals)*0.95)]
        last_evt=-10**9
        for s in keys:
            t=tape60[s]
            if abs(t)<thr or s-last_evt<300: continue
            side=1 if t>0 else -1
            m=sec[s][0]
            hi=max((sec[k][0] for k in range(s-1800,s) if k in sec), default=None)
            lo=min((sec[k][0] for k in range(s-1800,s) if k in sec), default=None)
            if hi is None: continue
            at_ext = (side>0 and m>=hi) or (side<0 and m<=lo)
            if not at_ext: continue
            # far-side thinness vs trailing 1h median
            far = [sec[k][4 if side>0 else 3] for k in range(s-3600,s,10) if k in sec]
            far_now = sec[s][4 if side>0 else 3]
            thin = far and far_now < 0.5*st.median(far)
            row=dict(day=day,s=s,side=side,tape=t,thin=bool(thin))
            for h in (300,900,1800):
                f=fwd(sec,s,h); row[f'r{h}_bps']=None if f is None else (f-m)/m*1e4*side  # + = continuation profit
            resB.append(row); last_evt=s
        print(sym, day, 'A',sum(1 for r in resA if r['day']==day),'B',sum(1 for r in resB if r['day']==day), flush=True)
    def summ(rows, key, cond=None):
        xs=[r[key] for r in rows if r.get(key) is not None and (cond is None or cond(r))]
        if not xs: return None
        xs.sort(); n=len(xs); m=sum(xs)/n; sd=st.pstdev(xs) if n>1 else 0
        return dict(n=n, mean=round(m,2), median=round(xs[n//2],2), se=round(sd/math.sqrt(n),2) if n>1 else None,
                    hit_gt_cost=round(sum(1 for x in xs if x>12)/n,3))
    out=dict(symbol=sym, days=days, sweep_bps=sweep_bps, dq=dq, range=resC,
             A_all={h:summ(resA,f'r{h}_bps') for h in (60,300,900)},
             A_rebuild_ofi={h:summ(resA,f'r{h}_bps',lambda r:r['rebuild'] and r['ofi_against']) for h in (60,300,900)},
             A_norebuild={h:summ(resA,f'r{h}_bps',lambda r:not r['rebuild']) for h in (60,300,900)},
             B_all={h:summ(resB,f'r{h}_bps') for h in (300,900,1800)},
             B_thin={h:summ(resB,f'r{h}_bps',lambda r:r['thin']) for h in (300,900,1800)},
             B_notthin={h:summ(resB,f'r{h}_bps',lambda r:not r['thin']) for h in (300,900,1800)},
             nA=len(resA), nB=len(resB))
    (OUT/f'screen_{sym}.json').write_text(json.dumps(out,indent=1))
    print(json.dumps({k:v for k,v in out.items() if k not in ('dq','range')}, indent=1))
    print('DQ', json.dumps(dq)); print('RANGE', json.dumps(resC))

if __name__=='__main__':
    sym=sys.argv[1]; days=sys.argv[2].split(','); bps=float(sys.argv[3])
    run(sym, days, bps)
