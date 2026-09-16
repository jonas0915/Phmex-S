"""Screen: post-12:30 UTC (8:30 ET) print continuation on Phemex 1m data 6/1->9/2/2026.
Event detection is data-driven (no hand-typed calendar): a weekday whose 12:30 UTC 1m bar
has |ret| >= K x the median abs 1m return of the previous 60 bars AND volume >= K x median vol.
Trade: taker entry at 12:31 close in the direction of the 12:30 bar; taker exit at close of
12:31+H. Costs: 0.12% RT (taker/taker) of notional. Reported per-trade net % of notional.
"""
import pandas as pd, numpy as np, sys
CACHE='/Users/jonaspenaso/Desktop/Phmex-S/reports/cache/mr_edge_20260601_20260903/'
rng=np.random.default_rng(0)
def boot_ci(x, n=5000):
    x=np.asarray(x); 
    if len(x)<3: return (np.nan,np.nan)
    m=[rng.choice(x,len(x),replace=True).mean() for _ in range(n)]
    return (np.percentile(m,2.5), np.percentile(m,97.5))
out=[]
for sym in ['BTC','ETH','SOL','XRP','DOGE']:
    df=pd.read_pickle(f'{CACHE}{sym}_USDT_USDT_1m.pkl')
    df['ret']=df['close'].pct_change()
    for hour,minute,label in [(12,30,'0830ET'),(14,0,'1000ET'),(18,0,'1400ET_FOMC')]:
        for K in [3,5]:
            for H in [15,30,60]:
                res=[]; ctrl=[]
                for ts in df.index[(df.index.hour==hour)&(df.index.minute==minute)&(df.index.dayofweek<5)]:
                    i=df.index.get_loc(ts)
                    if i<61 or i+1+H>=len(df): continue
                    prev=df.iloc[i-60:i]
                    bar=df.iloc[i]
                    med_ret=prev['ret'].abs().median(); med_vol=prev['volume'].median()
                    if med_ret==0 or med_vol==0: continue
                    r0=(bar['close']-bar['open'])/bar['open']
                    big = abs(r0)>=K*med_ret and bar['volume']>=K*med_vol
                    entry=df.iloc[i+1]['close']; exit_=df.iloc[i+1+H]['close']
                    sgn=np.sign(r0)
                    net=sgn*(exit_-entry)/entry*100-0.12
                    (res if big else ctrl).append(net)
                lo,hi=boot_ci(res)
                out.append(dict(sym=sym,slot=label,K=K,H=H,n=len(res),mean=np.mean(res) if res else np.nan,lo=lo,hi=hi,ctrl_n=len(ctrl),ctrl_mean=np.mean(ctrl) if ctrl else np.nan))
o=pd.DataFrame(out)
pd.set_option('display.width',200); pd.set_option('display.max_rows',500)
print(o.round(4).to_string())
o.to_csv('macro_screen_out.csv',index=False)
