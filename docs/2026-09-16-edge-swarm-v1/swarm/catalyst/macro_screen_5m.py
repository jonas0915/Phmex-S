"""5m-framed screen of the 8:30 AM ET print-continuation mechanism, Phemex 5m data 6/1->9/2/2026.
Event (data-driven, no hand calendar): weekday 12:30 UTC 5m bar with |close-open|/open >= K x median
abs 5m return of the prior 12 bars AND volume >= K x median volume of the prior 12 bars.
Bot cadence: bar closes 12:35 UTC, taker entry at the 12:35 close in the bar's direction.
Exit modes: (a) time exit at H bars (taker); (b) TP/SL geometry using 1m path (TP/SL % of price),
timeout T minutes, taker both legs. Costs 0.12% RT of notional. One bet per event: pooled by
date across syms, but also per-symbol. Bootstrap CI on per-trade net %.
"""
import pandas as pd, numpy as np
CACHE='/Users/jonaspenaso/Desktop/Phmex-S/reports/cache/mr_edge_20260601_20260903/'
rng=np.random.default_rng(1)
def boot(x,n=5000):
    x=np.asarray(x,float)
    if len(x)<3: return (np.nan,np.nan)
    m=[rng.choice(x,len(x),replace=True).mean() for _ in range(n)]
    return (np.percentile(m,2.5),np.percentile(m,97.5))
SYMS=['ETH','SOL','XRP','DOGE','LINK','ADA','SUI','1000PEPE','BTC']
events={}  # (sym,date)->dict
for sym in SYMS:
    try:
        d5=pd.read_pickle(f'{CACHE}{sym}_USDT_USDT_5m.pkl'); d1=pd.read_pickle(f'{CACHE}{sym}_USDT_USDT_1m.pkl')
    except FileNotFoundError: print('missing',sym); continue
    d5['r']=(d5['close']-d5['open'])/d5['open']
    for ts in d5.index[(d5.index.hour==12)&(d5.index.minute==30)&(d5.index.dayofweek<5)]:
        i=d5.index.get_loc(ts)
        if i<13 or i+25>=len(d5): continue
        prev=d5.iloc[i-12:i]; bar=d5.iloc[i]
        mr=prev['r'].abs().median(); mv=prev['volume'].median()
        if mr==0 or mv==0: continue
        events[(sym,ts.date())]=dict(sym=sym,ts=ts,r0=bar['r'],kr=abs(bar['r'])/mr,kv=bar['volume']/mv,entry=bar['close'],i5=i,d5=d5,d1=d1)
def run(K,H_bars=None,tp=None,sl=None,T_min=None):
    rows=[]
    for (sym,date),e in events.items():
        if not (e['kr']>=K and e['kv']>=K): continue
        sgn=np.sign(e['r0']); entry=e['entry']; d5=e['d5']; d1=e['d1']
        if H_bars is not None:
            ex=d5.iloc[e['i5']+H_bars]['close']; net=sgn*(ex-entry)/entry*100-0.12; hit='time'
        else:
            t0=e['ts']+pd.Timedelta(minutes=5)   # 12:35 entry
            path=d1.loc[t0+pd.Timedelta(minutes=1):t0+pd.Timedelta(minutes=T_min)]
            hit='timeout'; ex=path['close'].iloc[-1] if len(path) else entry
            for _,b in path.iterrows():
                if sgn>0:
                    if b['low']<=entry*(1-sl/100): ex=entry*(1-sl/100); hit='sl'; break
                    if b['high']>=entry*(1+tp/100): ex=entry*(1+tp/100); hit='tp'; break
                else:
                    if b['high']>=entry*(1+sl/100): ex=entry*(1+sl/100); hit='sl'; break
                    if b['low']<=entry*(1-tp/100): ex=entry*(1-tp/100); hit='tp'; break
            net=sgn*(ex-entry)/entry*100-0.12
        rows.append(dict(sym=sym,date=date,net=net,hit=hit,r0=e['r0']*100))
    return pd.DataFrame(rows)
print('events detected (K=3) per sym:', {s:int(sum(1 for (sym,_),e in events.items() if sym==s and e['kr']>=3 and e['kv']>=3)) for s in SYMS})
print('distinct event DATES K=3 (any sym):', len({d for (s,d),e in events.items() if e['kr']>=3 and e['kv']>=3}), '| K=4:', len({d for (s,d),e in events.items() if e['kr']>=4 and e['kv']>=4}))
print('weeks in sample:', round((max(e['ts'] for e in events.values())-min(e['ts'] for e in events.values())).days/7,1))
out=[]
for K in [3,4]:
    for H in [6,12,24]:
        df=run(K,H_bars=H)
        if len(df)==0: continue
        lo,hi=boot(df['net']); out.append(dict(K=K,exit=f'time{H*5}m',n=len(df),n_dates=df['date'].nunique(),mean=df['net'].mean(),lo=lo,hi=hi,wr=(df['net']>0).mean()))
        # one bet per date: pick ETH if present else first
        one=df.sort_values('sym',key=lambda s: s!='ETH').groupby('date').first()
        lo,hi=boot(one['net']); out.append(dict(K=K,exit=f'time{H*5}m_1perdate',n=len(one),n_dates=len(one),mean=one['net'].mean(),lo=lo,hi=hi,wr=(one['net']>0).mean()))
    for tp,sl,T in [(0.5,0.5,120),(0.8,0.5,120),(1.0,0.6,180),(1.5,0.75,240),(0.6,0.3,90)]:
        df=run(K,tp=tp,sl=sl,T_min=T)
        if len(df)==0: continue
        lo,hi=boot(df['net']); hits=df['hit'].value_counts().to_dict()
        out.append(dict(K=K,exit=f'tp{tp}/sl{sl}/T{T}',n=len(df),n_dates=df['date'].nunique(),mean=df['net'].mean(),lo=lo,hi=hi,wr=(df['net']>0).mean(),tp_hit=hits.get('tp',0)/len(df),sl_hit=hits.get('sl',0)/len(df),timeout=hits.get('timeout',0)/len(df)))
o=pd.DataFrame(out); pd.set_option('display.width',220)
print(o.round(3).to_string())
o.to_csv('macro_screen_5m_out.csv',index=False)
df=run(3,tp=0.8,sl=0.5,T_min=120); df.to_csv('macro_events_K3_tp08_sl05.csv',index=False)
print(df.groupby('sym')['net'].agg(['count','mean']).round(3))
print('event dates K=3:', sorted({str(d) for d in df['date']}))
