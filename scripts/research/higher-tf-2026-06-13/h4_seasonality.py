"""H4: Time-of-day / day-of-week seasonality at hourly & daily level.
Uses 1h data. Computes mean forward 1h and forward-to-daily-close returns by
hour-of-day (UTC) and day-of-week. Also tests a 'weekend effect' long/short.
All net-of-nothing for the descriptive part (these are holding-period returns, fee
applied only when we simulate a tradable rule). Chronological split for the rule."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS

def main():
    data=load_all("1h")
    # pool log/simple returns with hour & dow
    rows=[]
    for s in SYMBOLS:
        df=data[s].copy()
        df["ret"]=df["close"].pct_change()
        df["hour"]=df["timestamp"].dt.hour
        df["dow"]=df["timestamp"].dt.dayofweek  # 0=Mon
        df["sym"]=s
        rows.append(df.dropna(subset=["ret"]))
    alld=pd.concat(rows)
    print("===== H4 HOUR-OF-DAY (UTC) mean 1h return, all symbols pooled =====")
    g=alld.groupby("hour")["ret"].agg(["mean","std","count"])
    g["t"]=g["mean"]/(g["std"]/np.sqrt(g["count"]))
    for h,r in g.iterrows():
        print(f"  {h:02d}:00 UTC  mean={r['mean']*100:+.4f}%  t={r['t']:+.2f}  n={int(r['count'])}")
    print("\n===== H4 DAY-OF-WEEK mean 1h return (UTC) =====")
    days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    g2=alld.groupby("dow")["ret"].agg(["mean","std","count"])
    g2["t"]=g2["mean"]/(g2["std"]/np.sqrt(g2["count"]))
    g2["daily_equiv"]=(1+g2["mean"])**24-1
    for d,r in g2.iterrows():
        print(f"  {days[d]}  mean1h={r['mean']*100:+.4f}%  t={r['t']:+.2f}  ~daily={r['daily_equiv']*100:+.3f}%  n={int(r['count'])}")

    # Weekend effect rule: build daily bars, test buy-Friday-close sell-Monday-open style.
    print("\n===== H4 WEEKEND EFFECT (daily resample, BTC+ETH+pooled) =====")
    for s in SYMBOLS:
        df=data[s].set_index("timestamp")
        daily=df["close"].resample("1D").last().dropna()
        op=df["open"].resample("1D").first().dropna()
        dd=pd.DataFrame({"open":op,"close":daily})
        dd["dow"]=dd.index.dayofweek
        dd["fwd"]=dd["close"].shift(-1)/dd["open"]-1  # open->next? use close-to-close
        dd["cc"]=dd["close"].pct_change().shift(-1)    # today close -> tomorrow close
    # pooled day-of-week on daily close-to-close
    pooled=[]
    for s in SYMBOLS:
        df=data[s].set_index("timestamp")
        daily=df["close"].resample("1D").last().dropna()
        r=daily.pct_change().dropna()
        tmp=pd.DataFrame({"ret":r}); tmp["dow"]=tmp.index.dayofweek; tmp["sym"]=s
        pooled.append(tmp)
    pd_all=pd.concat(pooled)
    g3=pd_all.groupby("dow")["ret"].agg(["mean","std","count"])
    g3["t"]=g3["mean"]/(g3["std"]/np.sqrt(g3["count"]))
    print("  Daily close-to-close return by day-of-week (the bar's own day):")
    for d,r in g3.iterrows():
        print(f"  {days[d]}  mean={r['mean']*100:+.3f}%  t={r['t']:+.2f}  n={int(r['count'])}")

    # Tradable: best hour long rule, OOS split
    print("\n===== H4 TRADABLE: long single best-hour, hold 1h, net fee, OOS =====")
    alld_sorted=alld.sort_values("timestamp")
    sp_time=alld_sorted["timestamp"].quantile(0.5)
    tr=alld_sorted[alld_sorted["timestamp"]<sp_time]
    # pick best hour in train
    best=tr.groupby("hour")["ret"].mean().idxmax()
    te=alld_sorted[alld_sorted["timestamp"]>=sp_time]
    tr_h=tr[tr["hour"]==best]["ret"].values - FEE_RT
    te_h=te[te["hour"]==best]["ret"].values - FEE_RT
    bpy=365  # ~1 trade/day
    print(f"  best train hour={best:02d}:00 UTC")
    print(f"  TRAIN {fmt(perf_stats(tr_h,bpy))}")
    print(f"  TEST  {fmt(perf_stats(te_h,bpy))}")

if __name__=="__main__":
    main()
