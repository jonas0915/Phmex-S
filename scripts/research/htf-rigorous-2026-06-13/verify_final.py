#!/usr/bin/env python3
"""MAKE-OR-BREAK verification of market-neutral cross-sectional momentum.

Addresses 4 concerns:
  1. Survivorship + leg decomposition (+ crashed-coin universe + wider universe)
  2. Parameter plateau (full L x k x H grid, t-stats)
  3. Recent decay (per-year t-stat + Sharpe)
  4. Realistic turnover costs (6-leg weekly rebal)

KEY METHODOLOGY FIXES vs prior test5:
  - Portfolio return per rebalance = mean of leg returns over the HOLD horizon,
    but we report it as a held-position return, and annualize using the
    REBALANCE cadence (weekly) -> overlapping H>7 holds mean capital is reused;
    we model NON-OVERLAPPING books by default (rebal == hold) for the honest
    Sharpe, and separately show the overlapping version for comparison.
  - Turnover: at each rebalance, names rotate; we compute actual fraction of
    book turned over and charge cost on it.
  - LUNA ticker reuse on gateio: old-LUNA spliced with LUNA2.0 on 2022-05-28.
    We TRUNCATE XLUNA at its death (first close < 0.5% of trailing ATH) so the
    fake +5,000,000% relaunch spike can't poison the SHORT leg. A short that
    rode it to zero is closed at the death price (realistic: delisting fill).
"""
import os, numpy as np, pandas as pd
from engine import load, SYMBOLS, ALL_SYMBOLS, bootstrap_ci

FEE_MAKER = 0.0002   # 0.02% per side
FEE_TAKER = 0.0012   # 0.12% per side

# ---- universes ----
CORE13 = SYMBOLS  # BTC ETH SOL BNB DOGE ADA AVAX LINK LTC DOT ATOM UNI BCH
WIDER_EXTRA = ["SUSHI","YFI","COMP","MKR","AAVE","SNX","CRV","1INCH","GRT","SAND",
               "MANA","APE","GALA","CHZ","ENJ","BAT","ZRX","EOS","XLM","TRX","ETC",
               "FIL","ICP","NEAR","ALGO","VET","THETA","FTM","XTZ","EGLD","FLOW","KSM"]
CRASHED = ["XLUNA","FTT","CEL","RAY","WAVES","LUNC"]

def _exists(sym):
    return os.path.exists(os.path.join(os.path.dirname(__file__),"data",f"{sym}_1d.csv"))

def load_close(sym):
    return load(sym,"1d")["close"]

def truncate_dead(close, ath_frac=0.005):
    """For a crashed coin: once close falls below ath_frac of its trailing ATH,
    treat as delisted -> keep the death candle, drop everything after (prevents
    ticker-reuse relaunch spikes from leaking in)."""
    ath = close.cummax()
    dead = close < ath*ath_frac
    if dead.any():
        first_dead = dead.idxmax()
        # keep through first_dead (the fill where short closes), drop the rest
        return close.loc[:first_dead]
    return close

def build_panel(symbols, truncate_crashed=False):
    cols={}
    for s in symbols:
        if not _exists(s):
            continue
        c = load_close(s)
        if truncate_crashed and s in CRASHED:
            c = truncate_dead(c)
        cols[s]=c
    panel=pd.DataFrame(cols).sort_index()
    return panel

# ---- core backtest: returns per-rebalance leg detail ----
def run(L, k, H, symbols, long_short=True, rebal=None, truncate_crashed=False):
    """Returns DataFrame rows = (entry_dt, symbol, side, ret_gross, turnover_flag).
    rebal = days between rebalances (default = H for non-overlapping book)."""
    if rebal is None: rebal = H
    panel = build_panel(symbols, truncate_crashed)
    idx = panel.index
    rows=[]
    prev_holdings=set()
    i=L
    while i + 1 < len(idx):
        row_now=panel.iloc[i]; row_past=panel.iloc[i-L]
        trail=(row_now/row_past-1.0).dropna()
        if len(trail) < 2*k+1:
            i+=rebal; continue
        ranked=trail.sort_values(ascending=False)
        longs=list(ranked.index[:k]); shorts=list(ranked.index[-k:]) if long_short else []
        # forward return over H days; if a coin's series ends before i+H (delist),
        # use its LAST available price (realistic exit at delisting).
        j=min(i+H, len(idx)-1)
        edt=idx[i]
        cur=set()
        for s in longs:
            entry=panel.iloc[i].get(s,np.nan)
            exitp=panel.iloc[j].get(s,np.nan)
            if np.isnan(entry): continue
            if np.isnan(exitp):
                # find last non-nan before j for this symbol
                ser=panel[s].iloc[i:j+1].dropna()
                if len(ser)<2: continue
                exitp=ser.iloc[-1]
            rows.append({"entry_dt":edt,"symbol":s,"side":"L","ret":exitp/entry-1.0})
            cur.add(("L",s))
        for s in shorts:
            entry=panel.iloc[i].get(s,np.nan)
            exitp=panel.iloc[j].get(s,np.nan)
            if np.isnan(entry): continue
            if np.isnan(exitp):
                ser=panel[s].iloc[i:j+1].dropna()
                if len(ser)<2: continue
                exitp=ser.iloc[-1]
            rows.append({"entry_dt":edt,"symbol":s,"side":"S","ret":-(exitp/entry-1.0)})
            cur.add(("S",s))
        prev_holdings=cur
        i+=rebal
    return pd.DataFrame(rows)

def tstat(x):
    x=np.asarray(x,float)
    if len(x)<3 or x.std(ddof=1)==0: return np.nan
    return x.mean()/(x.std(ddof=1)/np.sqrt(len(x)))

def book_series(trades, leg_filter=None):
    """Aggregate to per-rebalance portfolio return (equal-weight legs).
    leg_filter: None|'L'|'S'."""
    if trades.empty: return pd.Series(dtype=float)
    df=trades
    if leg_filter: df=df[df["side"]==leg_filter]
    if df.empty: return pd.Series(dtype=float)
    return df.groupby("entry_dt")["ret"].mean().sort_index()

def ann_factor(rebal_days):
    return 365.25/rebal_days

def summ(series, rebal_days, fee_rt_per_leg=0.0, k=3, long_short=True, turnover=2.0):
    """series = per-rebalance GROSS book return. Apply turnover cost.
    turnover = fraction of book replaced per rebalance (worst case 2.0 = full
    long+short rotation; we measure real turnover separately)."""
    if len(series)==0: return None
    # cost per rebalance = turnover * fee_rt_per_leg  (fee_rt_per_leg already RT)
    cost = turnover*fee_rt_per_leg
    net = series - cost
    af=ann_factor(rebal_days)
    sharpe = net.mean()/net.std(ddof=1)*np.sqrt(af) if net.std(ddof=1)>0 else np.nan
    return {"n":len(net),"mean_bps":net.mean()*1e4,"gross_bps":series.mean()*1e4,
            "t":tstat(net.values),"sharpe":sharpe,
            "ci":bootstrap_ci(net.values)}

def measure_turnover(trades):
    """Actual fraction of (side,symbol) holdings that change each rebalance."""
    if trades.empty: return np.nan
    by=trades.groupby("entry_dt")
    holds=[set(zip(g["side"],g["symbol"])) for _,g in by]
    if len(holds)<2: return np.nan
    turns=[]
    for a,b in zip(holds[:-1],holds[1:]):
        if not a: continue
        changed=len(a.symmetric_difference(b))  # entries+exits
        turns.append(changed/(2*len(a)))  # normalize: full rotation -> 1.0 of book each side...
    return float(np.mean(turns)) if turns else np.nan

# =====================================================================
def section(t): print("\n"+"="*70+f"\n{t}\n"+"="*70)

def main():
    HL,HK,HH = 14,3,14  # headline
    REBAL = 7           # weekly rebalance (as specified in the candidate)

    section("0. HEADLINE REPRO (overlapping weekly rebal, H14) core-13")
    tr=run(HL,HK,HH,CORE13,True,rebal=REBAL)
    s=book_series(tr)
    r=summ(s,REBAL,0,turnover=0)
    print(f"  gross: n_rebal={r['n']} mean {r['gross_bps']:.1f}bps t={r['t']:.2f} "
          f"sharpe(weekly-ann, gross)={r['sharpe']:.2f}")
    print(f"  NOTE: weekly rebal + 14d hold = 2x overlapping book (capital reused).")

    section("1A. LEG DECOMPOSITION (core-13, L14 k3 H14, weekly) — per year")
    print("  Which leg drives the edge? gross bps per rebalance.")
    print(f"  {'year':6} {'long_bps':>9} {'short_bps':>10} {'both_bps':>9} {'n':>4}")
    for yr in range(2021,2027):
        sub=tr[pd.to_datetime(tr['entry_dt']).dt.tz_localize(None).dt.year==yr]
        if sub.empty: continue
        l=book_series(sub,'L'); sh=book_series(sub,'S'); bo=book_series(sub)
        print(f"  {yr:6} {l.mean()*1e4:9.1f} {sh.mean()*1e4:10.1f} {bo.mean()*1e4:9.1f} {len(bo):4}")
    lL=book_series(tr,'L'); lS=book_series(tr,'S'); lB=book_series(tr)
    print(f"  {'ALL':6} {lL.mean()*1e4:9.1f} {lS.mean()*1e4:10.1f} {lB.mean()*1e4:9.1f} {len(lB):4}")
    print(f"  long-only t={tstat(lL.values):.2f}  short-only t={tstat(lS.values):.2f}  both t={tstat(lB.values):.2f}")

    section("1B. SURVIVORSHIP — add CRASHED coins (LUNA/FTT/CEL/RAY/WAVES/LUNC)")
    print("  These delisted/died; gateio history truncated at death (no relaunch spike).")
    for cc in CRASHED:
        if _exists(cc):
            c=truncate_dead(load_close(cc))
            print(f"    {cc}: {c.index[0].date()}..{c.index[-1].date()} "
                  f"({len(c)}d) ATH {load_close(cc).max():.4g} -> death {c.iloc[-1]:.4g}")
    uni_crash = CORE13 + CRASHED
    trc=run(HL,HK,HH,uni_crash,True,rebal=REBAL,truncate_crashed=True)
    sc=book_series(trc); scL=book_series(trc,'L'); scS=book_series(trc,'S')
    print(f"\n  core-13      : both {lB.mean()*1e4:7.1f}bps t={tstat(lB.values):.2f} | "
          f"L {lL.mean()*1e4:.1f} S {lS.mean()*1e4:.1f}")
    print(f"  +crashed(19) : both {sc.mean()*1e4:7.1f}bps t={tstat(sc.values):.2f} | "
          f"L {scL.mean()*1e4:.1f} S {scS.mean()*1e4:.1f}")
    print("  -> if short-leg bps RISES with crashed coins, survivorship was UNDERSTATING short.")
    # how often did a crashed coin land in the short basket?
    cs=trc[(trc['side']=='S')&(trc['symbol'].isin(CRASHED))]
    print(f"  crashed coins shorted {len(cs)} leg-trades, avg ret {cs['ret'].mean()*100:.1f}% "
          f"(vs all-short avg {trc[trc.side=='S']['ret'].mean()*100:.1f}%)")

    section("1C. UNIVERSE EXPANSION — wider survivor universe (binanceus)")
    avail_wider=[s for s in WIDER_EXTRA if _exists(s)]
    print(f"  added {len(avail_wider)} coins: {avail_wider}")
    for name,uni,kk in [("core-13",CORE13,3),
                        ("core+wider",CORE13+avail_wider,3),
                        ("core+wider k5",CORE13+avail_wider,5),
                        ("ALL (core+wider+crashed)",CORE13+avail_wider+CRASHED,5)]:
        tc = name.startswith("ALL")
        t2=run(HL,kk,HH,uni,True,rebal=REBAL,truncate_crashed=tc)
        b=book_series(t2)
        r2=summ(b,REBAL,0,turnover=0)
        print(f"  {name:26} N={len([u for u in uni if _exists(u)]):3} k={kk} "
              f"n_rebal={r2['n']:4} both {r2['gross_bps']:7.1f}bps t={r2['t']:5.2f} "
              f"sharpe {r2['sharpe']:5.2f} CI[{r2['ci'][0]*1e4:.0f},{r2['ci'][1]*1e4:.0f}]")

    section("2. PARAMETER PLATEAU (core-13, L/S, weekly rebal) — t-stats")
    print("  cell = gross bps [t]. Contiguous positive region = real plateau.")
    Ls=[7,10,14,21,30]; ks=[2,3,4,5]; Hs=[7,14,21,30]
    for H in Hs:
        print(f"\n  --- H={H} ---")
        hdr="   L\\k  " + "".join(f"{('k'+str(k)):>14}" for k in ks)
        print(hdr)
        for L in Ls:
            cells=[]
            for k in ks:
                t2=run(L,k,H,CORE13,True,rebal=REBAL)
                b=book_series(t2)
                cells.append(f"{b.mean()*1e4:7.0f}[{tstat(b.values):4.1f}]")
            print(f"   {L:2}   "+"".join(f"{c:>14}" for c in cells))

    section("3. RECENT DECAY (core-13 headline, per year, t-stat + ann.Sharpe)")
    print(f"  {'year':6} {'n':>4} {'gross_bps':>10} {'t':>6} {'Sharpe':>8} {'compound%':>10}")
    for yr in range(2021,2027):
        sub=tr[pd.to_datetime(tr['entry_dt']).dt.tz_localize(None).dt.year==yr]
        b=book_series(sub)
        if len(b)<3: continue
        shp=b.mean()/b.std(ddof=1)*np.sqrt(52) if b.std(ddof=1)>0 else np.nan
        comp=((1+b).prod()-1)*100
        print(f"  {yr:6} {len(b):4} {b.mean()*1e4:10.1f} {tstat(b.values):6.2f} {shp:8.2f} {comp:10.1f}")
    # H1 vs H2 of sample
    b_all=book_series(tr).sort_index()
    half=len(b_all)//2
    print(f"  first half t={tstat(b_all.iloc[:half].values):.2f} "
          f"({b_all.iloc[:half].mean()*1e4:.0f}bps) | "
          f"second half t={tstat(b_all.iloc[half:].values):.2f} "
          f"({b_all.iloc[half:].mean()*1e4:.0f}bps)")
    # last 12 months
    cutoff=b_all.index.max()-pd.Timedelta(days=365)
    recent=b_all[b_all.index>=cutoff]
    print(f"  last 12mo: n={len(recent)} mean {recent.mean()*1e4:.1f}bps t={tstat(recent.values):.2f}")

    section("4. REALISTIC TURNOVER COSTS (6-leg weekly rebal)")
    turn=measure_turnover(tr)
    print(f"  measured book turnover/rebalance: {turn*100:.0f}% of legs rotate")
    print(f"  per-rebalance gross (book) = {lB.mean()*1e4:.1f}bps")
    # cost: each rotated leg pays RT. legs=2k=6. cost = 2k * turnover_pct * fee_rt
    nlegs=2*HK
    for label,fee in [("maker 0.02%/side -> 0.04% RT",FEE_MAKER*2),
                      ("taker 0.12%/side -> 0.24% RT",FEE_TAKER*2)]:
        # fraction of legs replaced each rebalance:
        frac=turn  # symmetric_difference/(2*nlegs) already -> approx frac of legs new
        cost_per_rebal = frac*nlegs*fee/nlegs  # = frac*fee... per book unit
        # Simpler & honest: cost on book = (legs replaced) * fee / nlegs
        legs_replaced = frac*2*nlegs  # symmetric diff counts in+out
        cost_book = legs_replaced*fee/nlegs
        net = lB - cost_book
        af=ann_factor(REBAL)
        shp=net.mean()/net.std(ddof=1)*np.sqrt(af) if net.std(ddof=1)>0 else np.nan
        print(f"  {label:30} cost {cost_book*1e4:5.1f}bps/rebal -> net {net.mean()*1e4:6.1f}bps "
              f"t={tstat(net.values):.2f} ann.Sharpe(weekly,overlap){shp:.2f}")

    section("4B. HONEST NON-OVERLAPPING SHARPE (rebal == hold, no capital reuse)")
    print("  Each $ deployed once per H days; true deployable Sharpe.")
    for H in [7,14,21]:
        t2=run(14,3,H,CORE13,True,rebal=H)  # non-overlapping
        b=book_series(t2)
        turn2=measure_turnover(t2)
        for label,fee in [("maker",FEE_MAKER*2),("taker",FEE_TAKER*2)]:
            legs_replaced=turn2*2*6
            cost=legs_replaced*fee/6
            net=b-cost
            af=ann_factor(H)
            shp=net.mean()/net.std(ddof=1)*np.sqrt(af) if net.std(ddof=1)>0 else np.nan
            print(f"  H={H:2} {label:6} n={len(b):3} turn={turn2*100:3.0f}% gross {b.mean()*1e4:6.1f} "
                  f"net {net.mean()*1e4:6.1f}bps t={tstat(net.values):4.2f} ann.Sharpe={shp:5.2f}")

if __name__=="__main__":
    main()
