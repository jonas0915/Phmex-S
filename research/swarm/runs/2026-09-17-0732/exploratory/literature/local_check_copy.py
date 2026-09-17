import pandas as pd, numpy as np, glob, os
SRC="/Users/jonaspenaso/Desktop/Phmex-S/backtest_data_june"
files=sorted(glob.glob(SRC+"/*_5m.csv"))
d={}
for f in files:
    s=os.path.basename(f).split("_USDT")[0]
    df=pd.read_csv(f,parse_dates=["timestamp"]).set_index("timestamp")
    df.index=pd.to_datetime(df.index,utc=True)
    d[s]=df
print("symbols",list(d), "BTC range",d["BTC"].index.min(),d["BTC"].index.max(),len(d["BTC"]))
close=pd.DataFrame({s:df["close"] for s,df in d.items()}).sort_index()
opn=pd.DataFrame({s:df["open"] for s,df in d.items()}).sort_index()
ret=np.log(close).diff()  # bar close-to-close log return
# --- Test 1: BTC 5m return -> next-bar alt open-to-close return (fill at next bar open)
oc=np.log(close/opn)  # open-to-close of same bar
btc=ret["BTC"]
rows=[]
for s in close.columns:
    if s=="BTC": continue
    nxt=oc[s].shift(-1)  # next bar open->close: enter at next open after BTC bar closes
    m=pd.concat([btc,nxt],axis=1).dropna(); m.columns=["b","a"]
    c=m.corr().iloc[0,1]
    thr=m.b.abs().quantile(0.9)
    big=m[m.b.abs()>=thr]
    sgn=(np.sign(big.b)*big.a)*1e4
    rows.append((s,round(c,4),len(big),round(sgn.mean(),2),round(sgn.std()/np.sqrt(len(sgn)),2)))
t1=pd.DataFrame(rows,columns=["alt","corr(BTC_t,alt_oc_t+1)","n_big(top10%|BTCret|)","mean_signed_next_oc_bps","se_bps"])
print("\nTEST1 BTC 5m return -> alt NEXT-bar open-to-close (bps), top-decile |BTC ret| threshold ~",round(thr*1e4,1),"bps")
print(t1.to_string(index=False))
allsgn=[]
for s in close.columns:
    if s=="BTC": continue
    m=pd.concat([btc,oc[s].shift(-1)],axis=1).dropna(); m.columns=["b","a"]
    big=m[m.b.abs()>=thr]; allsgn.append((np.sign(big.b)*big.a)*1e4)
allsgn=pd.concat(allsgn)
print("pooled signed next-bar alt OC: mean %.2f bps, se %.2f, n %d, hit-rate %.3f"%(allsgn.mean(),allsgn.std()/np.sqrt(len(allsgn)),len(allsgn),(allsgn>0).mean()))
# --- Test 2: funding-stamp bars: mean log return by 5m bar offset relative to 00/08/16 UTC
mins=(ret.index.hour%8)*60+ret.index.minute  # minutes since last funding stamp, 0..479
pooled=ret.drop(columns=["BTC"]).stack()
lab=pd.Series(mins,index=ret.index).reindex(pooled.index.get_level_values(0)).values
g=pd.DataFrame({"r":pooled.values*1e4,"m":lab}).groupby("m")["r"].agg(["mean","count",lambda x: x.std()/np.sqrt(len(x))])
g.columns=["mean_bps","n","se"]
print("\nTEST2 pooled alt 5m log-return by minutes-since-funding-stamp (bar START time; bar 475 = last bar before stamp, bar 0 = first bar after)")
print(g.loc[[455,460,465,470,475,0,5,10,15,20,25]].round(2).to_string())
print("all-bar mean %.2f bps"%pooled.mean()*1e4 if False else "all-bar mean %.3f bps, se %.3f"%(pooled.mean()*1e4,pooled.std()*1e4/np.sqrt(len(pooled))))
gb=pd.DataFrame({"r":ret["BTC"].values*1e4,"m":mins}).dropna().groupby("m")["r"].agg(["mean","count"])
print("BTC only:"); print(gb.loc[[465,470,475,0,5,10]].round(2).to_string())
# --- Test 3: quarter-hour bars (:00,:15,:30,:45 start) vs other 5m bars
q=pd.Series(ret.index.minute%15==0,index=ret.index)
labq=q.reindex(pooled.index.get_level_values(0)).values
gq=pd.DataFrame({"r":pooled.values*1e4,"q":labq}).groupby("q")["r"].agg(["mean","count",lambda x: x.std()/np.sqrt(len(x))])
gq.columns=["mean_bps","n","se"]
print("\nTEST3 pooled alt 5m return: bars starting at :00/:15/:30/:45 (True) vs other (False)")
print(gq.round(3).to_string())
byoff=pd.DataFrame({"r":pooled.values*1e4,"o":pd.Series(ret.index.minute%15,index=ret.index).reindex(pooled.index.get_level_values(0)).values}).groupby("o")["r"].agg(["mean","count"])
print(byoff.round(3).to_string())
