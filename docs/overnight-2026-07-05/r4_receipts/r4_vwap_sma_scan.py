#!/usr/bin/env python3
"""
R4 SCOPING SCAN (SCREENING-GRADE ONLY — not a deploy justification).

Owner's manual strategy: 5m, LONG-only.
  CROSS variant: 9SMA crosses above 15SMA at bar close AND close > session VWAP
                 -> enter at that bar's close.
  RETEST variant: after a qualifying cross, within N=6 bars (30 min) a bar's LOW
                 touches (<=) the 9SMA or the VWAP, and that bar CLOSES back above
                 BOTH the 9SMA and the VWAP -> enter at that bar's close.
                 One retest entry max per cross.

Definitional choices (degrees of freedom, first-reasonable, NO tuning):
  1. Cross confirmation: strict cross (sma9[t-1] <= sma15[t-1] and sma9[t] > sma15[t]),
     evaluated on closed bars only.
  2. VWAP convention: indicators.vwap() as-is — session VWAP resets at UTC midnight
     (indicators.py:68 index.normalize()); typical price (H+L+C)/3.
  3. "Price above VWAP" = signal bar CLOSE > VWAP at that bar.
  4. Retest window N = 6 bars (30 min) after the cross bar.
  5. Retest touch = low <= sma9 OR low <= vwap of the retest bar.
  6. Retest confirmation = retest bar close > sma9 AND close > vwap.
  7. Bracket: SL 1.2% / TP 1.6% off entry close (same numbers as live), intrabar
     both-touched -> counted as SL (conservative). No exit by end of data -> exit
     at last close ("open" outcome, included at mark).
  8. Fees: 0.12% round-trip subtracted from every gross return (naive taker-ish fill
     at bar close — NOT maker/PostOnly reality).
  9. Warmup: first 15 bars of the series skipped (SMA window); VWAP valid from first
     bar of each UTC day per the helper.
Total stated degrees of freedom: 9. One config per variant. No parameter search.
"""
import sys, glob, os, json
from collections import defaultdict
import pandas as pd
import numpy as np

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from indicators import sma, vwap

DATA_DIR = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_data_june"
FEE_RT = 0.0012          # 0.12% round trip
SL_PCT = 0.012
TP_PCT = 0.016
RETEST_N = 6             # bars
HORIZONS = {"+15m": 3, "+1h": 12, "+4h": 48}
MAJORS = {"BTC", "ETH"}

def load(fp):
    df = pd.read_csv(fp, parse_dates=["timestamp"], index_col="timestamp")
    df = df.sort_index()
    return df

def find_signals(df):
    s9 = sma(df["close"], 9)
    s15 = sma(df["close"], 15)
    vw = vwap(df["high"], df["low"], df["close"], df["volume"])
    cross = (s9 > s15) & (s9.shift(1) <= s15.shift(1)) & (df["close"] > vw)
    cross.iloc[:15] = False
    cross = cross.fillna(False)
    cross_idx = list(np.flatnonzero(cross.values))

    retest_idx = []
    for ci in cross_idx:
        for j in range(ci + 1, min(ci + 1 + RETEST_N, len(df))):
            lo = df["low"].iloc[j]
            cl = df["close"].iloc[j]
            if np.isnan(s9.iloc[j]) or np.isnan(vw.iloc[j]):
                continue
            touched = (lo <= s9.iloc[j]) or (lo <= vw.iloc[j])
            confirmed = (cl > s9.iloc[j]) and (cl > vw.iloc[j])
            if touched and confirmed:
                retest_idx.append(j)
                break  # one retest per cross
    return cross_idx, retest_idx

def eval_signal(df, i):
    """Return dict of fwd returns (net of fees) and bracket outcome."""
    entry = df["close"].iloc[i]
    out = {"ts": df.index[i], "entry": entry}
    for name, h in HORIZONS.items():
        j = i + h
        if j < len(df):
            out[name] = (df["close"].iloc[j] / entry - 1) - FEE_RT
        else:
            out[name] = None
    sl = entry * (1 - SL_PCT)
    tp = entry * (1 + TP_PCT)
    res, ret = "open", None
    for j in range(i + 1, len(df)):
        lo, hi = df["low"].iloc[j], df["high"].iloc[j]
        hit_sl = lo <= sl
        hit_tp = hi >= tp
        if hit_sl:                      # conservative: SL wins ties
            res, ret = "SL", -SL_PCT - FEE_RT
            break
        if hit_tp:
            res, ret = "TP", TP_PCT - FEE_RT
            break
    if res == "open":
        ret = (df["close"].iloc[-1] / entry - 1) - FEE_RT
    out["bracket_res"] = res
    out["bracket_ret"] = ret
    return out

def agg(rows, key="bracket_ret"):
    rets = [r[key] for r in rows if r[key] is not None]
    if not rets:
        return dict(n=0)
    wins = sum(1 for x in rets if x > 0)
    return dict(n=len(rets), wr=wins / len(rets), avg=float(np.mean(rets)),
                med=float(np.median(rets)), total=float(np.sum(rets)))

def agg_h(rows, name):
    rets = [r[name] for r in rows if r.get(name) is not None]
    if not rets:
        return dict(n=0)
    return dict(n=len(rets), avg=float(np.mean(rets)),
                pos=float(np.mean([x > 0 for x in rets])))

def main():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_5m.csv")))
    all_sigs = {"cross": [], "retest": []}
    per_sym = {}
    tmin, tmax = None, None
    for fp in files:
        sym = os.path.basename(fp).split("_")[0]
        df = load(fp)
        tmin = df.index[0] if tmin is None else min(tmin, df.index[0])
        tmax = df.index[-1] if tmax is None else max(tmax, df.index[-1])
        ci, ri = find_signals(df)
        per_sym[sym] = {"cross": len(ci), "retest": len(ri),
                        "days": (df.index[-1] - df.index[0]).total_seconds() / 86400}
        for i in ci:
            r = eval_signal(df, i); r["sym"] = sym; all_sigs["cross"].append(r)
        for i in ri:
            r = eval_signal(df, i); r["sym"] = sym; all_sigs["retest"].append(r)

    span_days = (tmax - tmin).total_seconds() / 86400
    mid = tmin + (tmax - tmin) / 2

    report = {"span_days": span_days, "tmin": str(tmin), "tmax": str(tmax),
              "mid": str(mid), "n_symbols": len(files), "per_sym": per_sym}

    for var in ("cross", "retest"):
        rows = all_sigs[var]
        r = {"total_signals": len(rows),
             "per_day_all": len(rows) / span_days,
             "per_day_per_sym": len(rows) / span_days / len(files),
             "bracket": agg(rows)}
        for hname in HORIZONS:
            r[f"fwd{hname}"] = agg_h(rows, hname)
        maj = [x for x in rows if x["sym"] in MAJORS]
        alt = [x for x in rows if x["sym"] not in MAJORS]
        r["bracket_majors"] = agg(maj)
        r["bracket_alts"] = agg(alt)
        h1 = [x for x in rows if x["ts"] < mid]
        h2 = [x for x in rows if x["ts"] >= mid]
        r["bracket_half1"] = agg(h1)
        r["bracket_half2"] = agg(h2)
        r["fwd+1h_half1"] = agg_h(h1, "+1h")
        r["fwd+1h_half2"] = agg_h(h2, "+1h")
        r["fwd+1h_majors"] = agg_h(maj, "+1h")
        r["fwd+1h_alts"] = agg_h(alt, "+1h")
        res_counts = defaultdict(int)
        for x in rows:
            res_counts[x["bracket_res"]] += 1
        r["bracket_outcomes"] = dict(res_counts)
        report[var] = r

    # same-5m-bar cross-symbol collisions (2-min global cooldown proxy)
    for var in ("cross", "retest"):
        ts_count = defaultdict(int)
        for x in all_sigs[var]:
            ts_count[x["ts"]] += 1
        collide = sum(c - 1 for c in ts_count.values() if c > 1)
        report[var]["same_bar_collisions"] = collide

    print(json.dumps(report, indent=1, default=str))

if __name__ == "__main__":
    main()
