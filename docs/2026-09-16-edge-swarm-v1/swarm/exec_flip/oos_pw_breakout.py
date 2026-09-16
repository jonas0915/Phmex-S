"""SCREENING-GRADE, READ-ONLY. Out-of-sample re-run of the prior swarm's C1/C2 prior-week breakout cells
(rule copied verbatim from ae940530/.../swarm/htf_levels/probe_c_orb.py) on the mr_edge Phemex 5m cache
(reports/cache/mr_edge_20260601_20260903), data TRUNCATED at 2026-08-03 23:55 UTC so the 8/4->9/3 holdout
stays unread (same discipline as the prior breakout lens). Plus ONE pre-specified new cell F (failed
acceptance -> taker reversal to weekly midpoint). Costs: taker 0.12% RT + 0.06% RT slippage + funding
0.01%/8h charged regardless of side; both-touched-in-bar -> SL; $75 notional ($7.50 margin x 10x).
Slices: OVERLAP = entries 6/1..7/5 (partly seen by the jun set for 18 symbols), OOS = entries 7/6..8/3 (never screened)."""
import glob, os, json
import numpy as np, pandas as pd
CACHE='/Users/jonaspenaso/Desktop/Phmex-S/reports/cache/mr_edge_20260601_20260903'
OUT=os.path.dirname(os.path.abspath(__file__))
END=pd.Timestamp('2026-08-03 23:55:00+00:00')
FEE=0.0012; SLIP=0.0006; FUND_8H=0.0001; NOTIONAL=75.0
OOS_START=pd.Timestamp('2026-07-06 00:00:00+00:00')
JUN_SYMS={'1000PEPE','AAVE','ADA','ALLO','ARB','AVAX','BCH','BNB','BTC','DOGE','EIGEN','ETH','HYPE','INJ','ONDO','SOL','TAO','WIF','WLD','XLM','XRP','ZEC'}
TRADABLE9=['ETH','SOL','XRP','DOGE','1000PEPE','1000SHIB','SUI','LINK','ADA']
rng=np.random.default_rng(23)

def atr1h(df5,n=14):
    h=df5.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
    pc=h['close'].shift(1); tr=pd.concat([h['high']-h['low'],(h['high']-pc).abs(),(h['low']-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean().shift(1).reindex(df5.index,method='ffill')
def simulate(df5,i_entry,side,tp,sl,max_bars):
    px_in=df5['open'].iloc[i_entry]; end=min(i_entry+max_bars,len(df5)-1)
    H=df5['high'].values; L=df5['low'].values
    for j in range(i_entry,end+1):
        h,l=H[j],L[j]
        if (l<=sl if side==1 else h>=sl): return px_in,sl,j-i_entry,'SL'
        if (h>=tp if side==1 else l<=tp): return px_in,tp,j-i_entry,'TP'
    return px_in,df5['close'].iloc[end],end-i_entry,'TIME'
def pnl(pi,po,side,bars):
    g=side*(po-pi)/pi; return g, g-FEE-SLIP-FUND_8H*(bars*5/60/8), g-FEE

def mech_C(df5,sym,tp_mult,tag):
    out=[]; a=atr1h(df5)
    h1=df5.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
    wk=df5.resample('W-MON',label='left',closed='left').agg({'high':'max','low':'min'}).dropna()
    for wstart in wk.index[1:]:
        prevw=wstart-pd.Timedelta(days=7)
        if prevw not in wk.index: continue
        pwh,pwl=wk.loc[prevw,'high'],wk.loc[prevw,'low']; pwr=pwh-pwl
        week=h1[(h1.index>=wstart)&(h1.index<wstart+pd.Timedelta(days=7))]
        if len(week)<48: continue
        for side,lvl in ((1,pwh),(-1,pwl)):
            c=week['close'].values; idx=None
            for k in range(1,len(c)):
                if (c[k]>lvl and c[k-1]>lvl) if side==1 else (c[k]<lvl and c[k-1]<lvl): idx=k; break
            if idx is None or idx+1>=len(week): continue
            t_entry=week.index[idx+1]
            if t_entry not in df5.index: continue
            i_entry=df5.index.get_loc(t_entry); at=a.iloc[i_entry]
            if not np.isfinite(at): continue
            tp=lvl+side*tp_mult*pwr; sl=lvl-side*1.0*at; pi=df5['open'].iloc[i_entry]
            if side*(tp-pi)/pi<0.004 or side*(pi-sl)/pi<=0: continue
            pi,po,bars,why=simulate(df5,i_entry,side,tp,sl,288*5); g,n,nf=pnl(pi,po,side,bars)
            out.append(dict(sym=sym,mech=tag,t=str(t_entry),side=side,gross=g,net=n,net_feeonly=nf,bars=bars,why=why,
                            tp_pct=side*(tp-pi)/pi*100,sl_pct=side*(pi-sl)/pi*100,truncated=(why=='TIME' and i_entry+288*5>len(df5)-1)))
    return out

def mech_F(df5,sym):
    """NEW pre-specified cell: after C1 acceptance (2 consecutive 1h closes beyond PWH/PWL), the FIRST 1h close back
    inside the prior-week range within 48h -> taker entry against the failed breakout at next 1h open.
    TP = prior-week midpoint; SL = extreme since acceptance +/- 0.5*ATR1h; 3-day max. One per side per week."""
    out=[]; a=atr1h(df5)
    h1=df5.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
    wk=df5.resample('W-MON',label='left',closed='left').agg({'high':'max','low':'min'}).dropna()
    for wstart in wk.index[1:]:
        prevw=wstart-pd.Timedelta(days=7)
        if prevw not in wk.index: continue
        pwh,pwl=wk.loc[prevw,'high'],wk.loc[prevw,'low']; mid=(pwh+pwl)/2
        week=h1[(h1.index>=wstart)&(h1.index<wstart+pd.Timedelta(days=7))]
        if len(week)<48: continue
        for bside,lvl in ((1,pwh),(-1,pwl)):
            c=week['close'].values; hh=week['high'].values; ll=week['low'].values; idx=None
            for k in range(1,len(c)):
                if (c[k]>lvl and c[k-1]>lvl) if bside==1 else (c[k]<lvl and c[k-1]<lvl): idx=k; break
            if idx is None: continue
            fail=None
            for k in range(idx+1,min(idx+49,len(c))):
                if (c[k]<lvl) if bside==1 else (c[k]>lvl): fail=k; break
            if fail is None or fail+1>=len(week): continue
            t_entry=week.index[fail+1]
            if t_entry not in df5.index: continue
            i_entry=df5.index.get_loc(t_entry); at=a.iloc[i_entry]
            if not np.isfinite(at): continue
            side=-bside
            ext=hh[idx:fail+1].max() if bside==1 else ll[idx:fail+1].min()
            sl=ext+0.5*at if bside==1 else ext-0.5*at
            tp=mid; pi=df5['open'].iloc[i_entry]
            if side*(tp-pi)/pi<0.004 or side*(pi-sl)/pi<=0: continue
            pi,po,bars,why=simulate(df5,i_entry,side,tp,sl,288*3); g,n,nf=pnl(pi,po,side,bars)
            out.append(dict(sym=sym,mech='F_pw_failed_breakout',t=str(t_entry),side=side,gross=g,net=n,net_feeonly=nf,bars=bars,why=why,
                            tp_pct=side*(tp-pi)/pi*100,sl_pct=side*(pi-sl)/pi*100,truncated=(why=='TIME' and i_entry+288*3>len(df5)-1)))
    return out

rows=[]; syms=[]
for f in sorted(glob.glob(f'{CACHE}/*_5m.pkl')):
    sym=os.path.basename(f).replace('_USDT_USDT_5m.pkl','')
    if sym=='BTC': continue
    df5=pd.read_pickle(f); df5=df5[~df5.index.duplicated()].sort_index(); df5=df5[df5.index<=END]
    if len(df5)<288*14: continue
    syms.append(sym)
    for r in mech_C(df5,sym,0.5,'C1_pw_tp0.5'): rows.append(r)
    for r in mech_C(df5,sym,0.25,'C2_pw_tp0.25'): rows.append(r)
    for r in mech_F(df5,sym): rows.append(r)
R=pd.DataFrame(rows); R['t']=pd.to_datetime(R['t'],utc=True)
R['slice']=np.where(R.t>=OOS_START,'OOS_0706_0803','OVERLAP_0601_0705')
R['seen_sym']=R.sym.isin(JUN_SYMS)
R.to_csv(f'{OUT}/oos_trades.csv',index=False)

def boot_ci(x,B=4000):
    x=np.asarray(x); m=np.array([rng.choice(x,len(x)).mean() for _ in range(B)]); return np.percentile(m,[2.5,97.5])
def summ(g):
    n=len(g); lo,hi=boot_ci(g.net.values) if n>=5 else (np.nan,np.nan)
    return pd.Series(dict(n=n,net_pct=g.net.mean()*100,gross_pct=g.gross.mean()*100,net_feeonly_pct=g.net_feeonly.mean()*100,ci_lo=lo*100,ci_hi=hi*100,
        usd_75N=g.net.mean()*NOTIONAL,total_usd_75N=g.net.sum()*NOTIONAL,tp_rate=(g.why=='TP').mean(),sl_rate=(g.why=='SL').mean(),time_rate=(g.why=='TIME').mean(),
        trunc=(g.truncated).mean(),be_tp=(g.sl_pct/(g.sl_pct+g.tp_pct)).mean(),med_tp=g.tp_pct.median(),med_sl=g.sl_pct.median(),med_hold_h=g.bars.median()*5/60,
        sl_usd_75N=-g.sl_pct.median()/100*NOTIONAL,tp_usd_75N=g.tp_pct.median()/100*NOTIONAL,syms_pos=(g.groupby('sym').net.sum()>0).sum(),syms=g.sym.nunique()))
pd.set_option('display.width',300); pd.set_option('display.max_columns',40)
print('symbols used:',len(syms),syms)
for title,G in [('mech x slice',['mech','slice']),('mech x slice x side',['mech','slice','side']),('mech x slice x seen_sym',['mech','slice','seen_sym'])]:
    print(f'\n=== {title} ==='); print(R.groupby(G).apply(summ,include_groups=False).round(3).to_string())
U=R[R.sym.isin(TRADABLE9)]
print('\n=== tradable-9 universe (ETH SOL XRP DOGE 1000PEPE 1000SHIB SUI LINK ADA) mech x slice ==='); print(U.groupby(['mech','slice']).apply(summ,include_groups=False).round(3).to_string())
print('\n=== ETH only, mech x slice ==='); print(R[R.sym=='ETH'].groupby(['mech','slice']).apply(summ,include_groups=False).round(3).to_string())
c1=R[(R.mech=='C1_pw_tp0.5')&(R.slice=='OOS_0706_0803')].sort_values('net')
if len(c1)>2: print('\n=== C1 OOS excluding top-2 winners ==='); print(summ(c1.iloc[:-2]).round(3).to_string())
print('\n=== C1 OOS per symbol ==='); print(c1.groupby('sym').agg(n=('net','size'),net_pct=('net',lambda x:x.mean()*100),tp_rate=('why',lambda x:(x=='TP').mean())).round(3).to_string())
# signal rate on tradable-9 over full 6/1..8/3 window (9 weeks x 9 syms)
c1all=R[(R.mech=='C1_pw_tp0.5')&(R.sym.isin(TRADABLE9))]
wk_n=len(pd.date_range('2026-06-01','2026-08-03',freq='W-MON'))
print(f'\nC1 tradable-9: {len(c1all)} trades over {wk_n} weeks x {c1all.sym.nunique()} syms -> {len(c1all)/wk_n:.2f} trades/week for the 9-symbol book; per symbol-week {len(c1all)/(wk_n*9):.3f}')
c1w=R[(R.mech=='C1_pw_tp0.5')]
print(f'C1 all-{len(syms)}: {len(c1w)} trades over {wk_n} weeks -> {len(c1w)/wk_n:.2f}/week; per symbol-week {len(c1w)/(wk_n*len(syms)):.3f}')
print('hold hours quantiles (C1 all):', c1w.bars.mul(5/60).quantile([.25,.5,.75,.9]).round(1).to_dict())
json.dump({'symbols':syms,'n_rows':len(R)}, open(f'{OUT}/oos_meta.json','w'))
