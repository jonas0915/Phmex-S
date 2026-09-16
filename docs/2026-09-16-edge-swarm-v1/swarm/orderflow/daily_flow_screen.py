#!/usr/bin/env python3
"""Daily aggressor-flow persistence screen on logs/flow_capture.jsonl (read-only).
Per symbol per UTC day: trade_count-weighted buy_ratio, mean large_trade_bias, mean cvd_slope, mean ob.imbalance, last price.
Feature z-score vs trailing 20 days (excl. today); forward 1/3/5-day log return from daily last price.
Pooled quintile table + Q5-Q1 spread with naive SE (symbol-days treated independent; 3d/5d overlap inflates significance)."""
import json, math, statistics as st, sys
from collections import defaultdict
SRC='/Users/jonaspenaso/Desktop/Phmex-S/logs/flow_capture.jsonl'
OUT='/private/tmp/claude-501/-Users-jonaspenaso-Desktop/cada294f-0cc3-4fac-8342-724c46c4fb06/scratchpad/swarm/orderflow/daily_flow_screen.json'
agg=defaultdict(lambda: defaultdict(lambda: dict(n=0,tc=0.0,br=0.0,ltb=0.0,cvd=0.0,imb=0.0,last=None,last_ts=0)))
nrows=0; bad=0
with open(SRC) as fh:
    for line in fh:
        try: r=json.loads(line)
        except Exception: bad+=1; continue
        nrows+=1
        f=r.get('flow') or {}; ob=r.get('ob') or {}
        if not f or r.get('price') in (None,0): continue
        day=r['ts']//86400
        a=agg[r['symbol']][day]
        tc=f.get('trade_count') or 0
        a['n']+=1; a['tc']+=tc; a['br']+=(f.get('buy_ratio') or 0.5)*tc
        a['ltb']+=f.get('large_trade_bias') or 0.0; a['cvd']+=f.get('cvd_slope') or 0.0; a['imb']+=ob.get('imbalance') or 0.0
        if r['ts']>=a['last_ts']: a['last']=r['price']; a['last_ts']=r['ts']
print('rows',nrows,'bad',bad,'symbols',len(agg))
MIN_SNAPS=200
feats=['br','ltb','cvd','imb']
rows=[]
for sym,days in agg.items():
    ds=sorted(d for d,a in days.items() if a['n']>=MIN_SNAPS and a['tc']>0)
    if len(ds)<40: continue
    ser={}
    for d in ds:
        a=days[d]
        ser[d]=dict(br=a['br']/a['tc'], ltb=a['ltb']/a['n'], cvd=a['cvd']/a['n'], imb=a['imb']/a['n'], px=a['last'])
    for i,d in enumerate(ds):
        if i<20: continue
        hist=[ser[ds[j]] for j in range(i-20,i)]
        # require contiguous-ish history: last 20 rows span <= 30 days
        if d-ds[i-20]>30: continue
        row=dict(sym=sym, day=d)
        ok=True
        for f in feats:
            xs=[h[f] for h in hist]; mu=sum(xs)/20; sd=st.pstdev(xs)
            if sd==0: ok=False; break
            row['z_'+f]=(ser[d][f]-mu)/sd
        if not ok: continue
        for h in (1,3,5):
            if d+h in ser: row[f'r{h}']=math.log(ser[d+h]['px']/ser[d]['px'])*1e4
        rows.append(row)
print('symbol-days',len(rows),'symbols',len(set(r['sym'] for r in rows)))
def qtable(rows, zf, h):
    xs=[(r[zf], r[f'r{h}']) for r in rows if f'r{h}' in r]
    if len(xs)<50: return None
    xs.sort(); n=len(xs); q=n//5
    out=[]
    for k in range(5):
        seg=[y for _,y in xs[k*q:(k+1)*q if k<4 else n]]
        out.append(dict(n=len(seg), mean_bps=round(sum(seg)/len(seg),1), median_bps=round(sorted(seg)[len(seg)//2],1)))
    q1=[y for _,y in xs[:q]]; q5=[y for _,y in xs[4*q:]]
    m1=sum(q1)/len(q1); m5=sum(q5)/len(q5)
    se=math.sqrt(st.pvariance(q1)/len(q1)+st.pvariance(q5)/len(q5))
    return dict(n=n, quintiles=out, q5_minus_q1_bps=round(m5-m1,1), se_bps=round(se,1), t=round((m5-m1)/se,2))
res={}
TRADABLE={'ETH/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT','DOGE/USDT:USDT','1000PEPE/USDT:USDT','1000SHIB/USDT:USDT','SUI/USDT:USDT','LINK/USDT:USDT','ADA/USDT:USDT','ARB/USDT:USDT'}
for scope,rs in (('all',rows),('tradable10',[r for r in rows if r['sym'] in TRADABLE])):
    res[scope]={}
    for f in feats:
        for h in (1,3,5):
            res[scope][f'z_{f}_r{h}']=qtable(rs,'z_'+f,h)
json.dump(dict(nrows=nrows, symbol_days=len(rows), symbols=sorted(set(r['sym'] for r in rows)), results=res), open(OUT,'w'), indent=1)
for scope in res:
    print('==',scope, 'n symbol-days', len(rows) if scope=='all' else len([r for r in rows if r['sym'] in TRADABLE]))
    for k,v in res[scope].items():
        if v: print(k, 'n',v['n'], 'Q1..Q5 mean bps', [q['mean_bps'] for q in v['quintiles']], 'Q5-Q1', v['q5_minus_q1_bps'], 'se', v['se_bps'], 't', v['t'])
