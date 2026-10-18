# EXPLORATORY COPY (run 2026-10-18-0300, literature seat, analyst #7). NOT EVIDENCE.
# Original: docs/2026-09-16-edge-swarm-v1/sweep/leadlag/local_check.py (unedited).
# Changes vs original, and only these:
#  (1) data source: the original reads raw CSVs from backtest_data_june via pd.read_csv, bypassing
#      research.swarm.lib.load_data (forbidden, LESSONS 2026-09-19/2026-09-25). Here every series is
#      load_data.load_ohlcv(sym, "5m", era="train", dataset="mr_edge") -> holdout-guarded, train only.
#  (2) uncertainty: hand-rolled se = std/sqrt(n) replaced by bootstrap_ci.mean_ci (LESSONS 2026-10-04);
#      Test3 groups are too large for the in-memory bootstrap, so only mean and n are printed there.
# Run: PYTHONDONTWRITEBYTECODE=1 python3 local_check_copy.py > local_check_output.txt (from this dir)
import sys; sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as L
from research.swarm.lib.bootstrap_ci import mean_ci
import pandas as pd, numpy as np, glob, os
d={}
for s in L.list_symbols("mr_edge"):
    d[s]=L.load_ohlcv(s,"5m",era="train",dataset="mr_edge")
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
    lo,hi=mean_ci(sgn.values); rows.append((s,round(c,4),len(big),round(sgn.mean(),2),round(lo,2),round(hi,2)))
t1=pd.DataFrame(rows,columns=["alt","corr(BTC_t,alt_oc_t+1)","n_big(top10%|BTCret|)","mean_signed_next_oc_bps","ci95_lo","ci95_hi"])
print("\nTEST1 BTC 5m return -> alt NEXT-bar open-to-close (bps), top-decile |BTC ret| threshold ~",round(thr*1e4,1),"bps")
print(t1.to_string(index=False))
allsgn=[]
for s in close.columns:
    if s=="BTC": continue
    m=pd.concat([btc,oc[s].shift(-1)],axis=1).dropna(); m.columns=["b","a"]
    big=m[m.b.abs()>=thr]; allsgn.append((np.sign(big.b)*big.a)*1e4)
allsgn=pd.concat(allsgn)
plo,phi=mean_ci(allsgn.values,n_boot=500)
print("pooled signed next-bar alt OC: mean %.2f bps, bootstrap ci95 [%.2f, %.2f] (mean_ci n_boot=500), n %d, hit-rate %.3f"%(allsgn.mean(),plo,phi,len(allsgn),(allsgn>0).mean()))
# --- Test 2: funding-stamp bars: mean log return by 5m bar offset relative to 00/08/16 UTC
mins=(ret.index.hour%8)*60+ret.index.minute  # minutes since last funding stamp, 0..479
pooled=ret.drop(columns=["BTC"]).stack()
lab=pd.Series(mins,index=ret.index).reindex(pooled.index.get_level_values(0)).values
g=pd.DataFrame({"r":pooled.values*1e4,"m":lab}).groupby("m")["r"].agg(["mean","count",lambda x: mean_ci(x.values,n_boot=500)[0],lambda x: mean_ci(x.values,n_boot=500)[1]])
g.columns=["mean_bps","n","ci95_lo","ci95_hi"]
print("\nTEST2 pooled alt 5m log-return by minutes-since-funding-stamp (bar START time; bar 475 = last bar before stamp, bar 0 = first bar after)")
print(g.loc[[455,460,465,470,475,0,5,10,15,20,25]].round(2).to_string())
print("all-bar mean %.3f bps (n %d; no CI: too large for in-memory bootstrap)"%(pooled.mean()*1e4,len(pooled)))
gb=pd.DataFrame({"r":ret["BTC"].values*1e4,"m":mins}).dropna().groupby("m")["r"].agg(["mean","count"])
print("BTC only:"); print(gb.loc[[465,470,475,0,5,10]].round(2).to_string())
# --- Test 3: quarter-hour bars (:00,:15,:30,:45 start) vs other 5m bars
q=pd.Series(ret.index.minute%15==0,index=ret.index)
labq=q.reindex(pooled.index.get_level_values(0)).values
gq=pd.DataFrame({"r":pooled.values*1e4,"q":labq}).groupby("q")["r"].agg(["mean","count"])
gq.columns=["mean_bps","n"]
print("\nTEST3 pooled alt 5m return: bars starting at :00/:15/:30/:45 (True) vs other (False)")
print(gq.round(3).to_string())
byoff=pd.DataFrame({"r":pooled.values*1e4,"o":pd.Series(ret.index.minute%15,index=ret.index).reindex(pooled.index.get_level_values(0)).values}).groupby("o")["r"].agg(["mean","count"])
print(byoff.round(3).to_string())
