"""Stress-test the H4 day-of-week edge. Is it real or a few outlier Thursdays?
1. Per-day-of-week daily open->close, TRAIN vs TEST separately (does Mon+/Thu- persist?)
2. Median (not mean) and trimmed mean -> outlier robustness.
3. Month-by-month Thursday & Monday mean -> temporal stability.
4. Long-Mon vs Short-Thu legs separately OOS.
5. Bootstrap p-value on the test-half rule mean."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS

days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

def daily_panel():
    data=load_all("1h"); frames=[]
    for s in SYMBOLS:
        df=data[s].set_index("timestamp")
        d=pd.DataFrame({"open":df["open"].resample("1D").first(),
                        "close":df["close"].resample("1D").last()}).dropna()
        d["oc"]=d["close"]/d["open"]-1
        d["dow"]=d.index.dayofweek; d["sym"]=s; d["month"]=d.index.to_period("M")
        frames.append(d)
    return pd.concat(frames)

def main():
    p=daily_panel()
    n=len(p);
    # chronological split by date
    cutoff=p.index.sort_values()[int(len(p.index.unique())*0.5)] if False else p.index.unique().sort_values()[len(p.index.unique())//2]
    tr=p[p.index<cutoff]; te=p[p.index>=cutoff]
    print(f"split date ~ {cutoff.date()}  train days={tr.index.nunique()} test days={te.index.nunique()}")
    print("\n=== open->close mean by DOW: TRAIN | TEST (raw, not fee-adjusted) ===")
    for d in range(7):
        a=tr[tr.dow==d]["oc"]; b=te[te.dow==d]["oc"]
        ta=a.mean()/(a.std()/np.sqrt(len(a))) if len(a)>1 else 0
        tb=b.mean()/(b.std()/np.sqrt(len(b))) if len(b)>1 else 0
        print(f"  {days[d]} TRAIN {a.mean()*100:+.3f}% (t={ta:+.1f},n={len(a)}) | TEST {b.mean()*100:+.3f}% (t={tb:+.1f},n={len(b)})")

    print("\n=== Outlier robustness: Thursday open->close (all data) ===")
    thu=p[p.dow==3]["oc"]
    print(f"  mean={thu.mean()*100:+.3f}%  median={thu.median()*100:+.3f}%  trim10={thu.clip(thu.quantile(.05),thu.quantile(.95)).mean()*100:+.3f}%  n={len(thu)}")
    mon=p[p.dow==0]["oc"]
    print(f"  Mon mean={mon.mean()*100:+.3f}% median={mon.median()*100:+.3f}% trim10={mon.clip(mon.quantile(.05),mon.quantile(.95)).mean()*100:+.3f}% n={len(mon)}")

    print("\n=== Month-by-month: Monday & Thursday mean open->close (pooled syms) ===")
    for m,grp in p.groupby("month"):
        mo=grp[grp.dow==0]["oc"].mean(); th=grp[grp.dow==3]["oc"].mean()
        print(f"  {m}  Mon={mo*100:+.3f}%  Thu={th*100:+.3f}%")

    print("\n=== Legs separately, fee-adjusted, OOS (test half) ===")
    for name,d,dirn in [("LongMon",0,1),("ShortThu",3,-1)]:
        b=te[te.dow==d]["oc"].values
        net=dirn*b-FEE_RT
        print(f"  {name} TEST {fmt(perf_stats(net,365))}")

    print("\n=== Bootstrap: test-half rule (LongMon+ShortThu) mean vs shuffled-sign null ===")
    rng=np.random.default_rng(42)
    rule=[]
    for d,dirn in [(0,1),(3,-1)]:
        rule+= list(dirn*te[te.dow==d]["oc"].values - FEE_RT)
    rule=np.array(rule); obs=rule.mean()
    # null: random +/- sign on the same magnitude pool
    mags=np.abs(np.concatenate([te[te.dow==0]["oc"].values, te[te.dow==3]["oc"].values]))
    boot=[]
    for _ in range(20000):
        signs=rng.choice([-1,1],size=len(mags))
        boot.append((signs*mags - FEE_RT).mean())
    boot=np.array(boot); pval=(boot>=obs).mean()
    print(f"  observed test mean={obs*100:+.3f}%/trade  one-sided p(random>=obs)={pval:.4f}  n={len(rule)}")

if __name__=="__main__":
    main()
