"""Funding-settlement extreme-rate screen, Phemex 35 syms 6/1->9/2/2026.
Event: settlement at 00/08/16 UTC where the rate paid is in the cross-sectional/time top or bottom
q% (crowded side pays). Trade: at the settlement 5m bar close (taker), take the side that RECEIVED
funding (contrarian to crowding): rate>0 -> short; rate<0 -> long. Hold H hours (taker exit) or
TP/SL on 5m path. Costs 0.12% RT; funding received over the hold is ADDED (rate x hours/8).
Compares vs. all settlements (control) and same-direction momentum variant.
"""
import pandas as pd, numpy as np, json, glob, os
CACHE='/Users/jonaspenaso/Desktop/Phmex-S/reports/cache/mr_edge_20260601_20260903/'
rng=np.random.default_rng(2)
def boot(x,n=4000):
    x=np.asarray(x,float)
    if len(x)<3: return (np.nan,np.nan)
    m=[rng.choice(x,len(x),replace=True).mean() for _ in range(n)]
    return (np.percentile(m,2.5),np.percentile(m,97.5))
rows=[]
for f in sorted(glob.glob(CACHE+'funding_*.json')):
    sym=os.path.basename(f)[8:-5]
    p5=f'{CACHE}{sym}_5m.pkl'
    if not os.path.exists(p5): continue
    d5=pd.read_pickle(p5); fr=json.load(open(f))
    for r in fr:
        ts=pd.Timestamp(r['ts'],unit='ms',tz='UTC'); rate=r['rate']
        if ts not in d5.index: continue
        i=d5.index.get_loc(ts)
        if i<1 or i+289>=len(d5): continue
        entry=d5.iloc[i]['close']   # close of the bar that opens at settlement (bot sees at :05)
        rec={'sym':sym,'ts':ts,'rate':rate,'entry':entry}
        for H in [1,4,8,24]:
            ex=d5.iloc[i+H*12]['close']; rec[f'ret{H}']=(ex-entry)/entry*100
        rows.append(rec)
df=pd.DataFrame(rows); print('settlement obs',len(df),'syms',df['sym'].nunique())
print('rate pct (8h, %):', (df['rate']*100).quantile([.01,.05,.1,.5,.9,.95,.99]).round(4).to_dict())
out=[]
for q in [0.05,0.10]:
    lo_thr=df['rate'].quantile(q); hi_thr=df['rate'].quantile(1-q)
    for H in [1,4,8,24]:
        for variant in ['contrarian','momentum']:
            sel=df[(df['rate']>=hi_thr)|(df['rate']<=lo_thr)].copy()
            sgn=-np.sign(sel['rate']) if variant=='contrarian' else np.sign(sel['rate'])
            # funding over hold: contrarian side receives |rate| each settlement crossed (H/8 settlements), momentum pays
            fund=(np.abs(sel['rate'])*100)*(H/8)*(1 if variant=='contrarian' else -1)
            net=sgn*sel[f'ret{H}']-0.12+fund
            l,h=boot(net); out.append(dict(q=q,H=H,variant=variant,n=len(net),mean=net.mean(),lo=l,hi=h,wr=(net>0).mean(),n_pos_rate=int((sel['rate']>0).sum())))
    # control: all settlements, contrarian
    for H in [4,8]:
        sgn=-np.sign(df['rate']); net=sgn*df[f'ret{H}']-0.12+np.abs(df['rate'])*100*(H/8)
        l,h=boot(net); out.append(dict(q='all',H=H,variant='contrarian',n=len(net),mean=net.mean(),lo=l,hi=h,wr=(net>0).mean(),n_pos_rate=int((df['rate']>0).sum())))
o=pd.DataFrame(out); pd.set_option('display.width',200); print(o.round(4).to_string()); o.to_csv('funding_screen_out.csv',index=False)
# extreme events per week
q=0.05; sel=df[(df['rate']>=df['rate'].quantile(1-q))|(df['rate']<=df['rate'].quantile(q))]
print('extreme (5% tails) events:',len(sel),'over weeks',round((df['ts'].max()-df['ts'].min()).days/7,1),'-> per week',round(len(sel)/((df['ts'].max()-df['ts'].min()).days/7),1))
print('by sym top:', sel['sym'].value_counts().head(8).to_dict())
