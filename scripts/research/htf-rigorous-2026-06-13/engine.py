#!/usr/bin/env python3
"""Shared backtest engine + rigorous evaluation harness.

Methodology (non-negotiable):
- Net of fees: base 0.066% RT; stress 0.12% fee + 0.03% slippage = 0.30% RT.
- Full-sample mean net/trade + bootstrap 95% CI (must be clearly >0).
- Walk-forward: >=5 expanding folds, count positive folds, mean fold OOS.
- Regime split (BTC bull/bear/chop) attached to each trade by entry date.
- A candidate positive on one split but negative full-sample = ARTIFACT.

All returns are simple per-trade log-equivalent arithmetic on close-to-close
(or signal exit). Long AND short allowed (perp). Per-trade return is direction*
(exit/entry - 1) minus round-trip cost.
"""
import os, numpy as np, pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
SYMBOLS = ["BTC","ETH","SOL","BNB","DOGE","ADA","AVAX","LINK","LTC","DOT","ATOM","UNI","BCH"]
# XRP excluded by default (912d delisting gap corrupts returns); MATIC ends 2025-01.
ALL_SYMBOLS = SYMBOLS + ["XRP","MATIC"]

FEE_BASE = 0.00066   # 0.066% round-trip
FEE_STRESS = 0.00120 + 0.00030  # 0.12% fee + 0.03% slippage RT

_cache = {}
def load(sym, tf="1d"):
    k = (sym, tf)
    if k in _cache: return _cache[k]
    df = pd.read_csv(os.path.join(DATA, f"{sym}_{tf}.csv"), parse_dates=["dt"])
    df = df.set_index("dt").sort_index()
    _cache[k] = df
    return df

def btc_regime(tf="1d"):
    """Return a Series mapping date->regime using BTC 200/50 SMA structure."""
    k = ("__regime__", tf)
    if k in _cache: return _cache[k]
    btc = load("BTC", tf).copy()
    btc["sma200"] = btc.close.rolling(200).mean()
    btc["sma50"] = btc.close.rolling(50).mean()
    def reg(r):
        if np.isnan(r.sma200): return "na"
        if r.close > r.sma200 and r.sma50 > r.sma200: return "bull"
        if r.close < r.sma200 and r.sma50 < r.sma200: return "bear"
        return "chop"
    s = btc.apply(reg, axis=1)
    _cache[k] = s
    return s

def tag_regime(entry_dt, tf="1d"):
    s = btc_regime(tf)
    idx = s.index.asof(entry_dt) if hasattr(s.index, "asof") else None
    try:
        pos = s.index.get_indexer([entry_dt], method="ffill")[0]
        if pos < 0: return "na"
        return s.iloc[pos]
    except Exception:
        return "na"

# ---------- evaluation ----------
def bootstrap_ci(x, n=5000, seed=42):
    x = np.asarray(x, float)
    if len(x) < 5: return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(n, len(x)))].mean(axis=1)
    return (np.percentile(means, 2.5), np.percentile(means, 97.5))

def walk_forward(trades_df, folds=6):
    """Expanding-window walk-forward: split chronologically into `folds`
    equal OOS chunks; for each, report OOS mean net (base fee). Reports the
    mean across folds and how many are >0. No parameter fitting per fold here
    (these are parameter-free rules) -> this is a stability check, the honest
    minimum: does the edge persist in every sub-period?"""
    if len(trades_df) < folds * 5:
        return None
    df = trades_df.sort_values("entry_dt").reset_index(drop=True)
    chunks = np.array_split(df, folds)
    rows = []
    for i, c in enumerate(chunks):
        m = c["net_base"].mean()
        rows.append((i+1, len(c), m, str(c["entry_dt"].iloc[0].date()), str(c["entry_dt"].iloc[-1].date())))
    means = [r[2] for r in rows]
    npos = sum(1 for m in means if m > 0)
    return {"folds": rows, "n_pos": npos, "n_folds": len(rows), "mean_fold": float(np.mean(means))}

def evaluate(trades, label):
    """trades: list of dicts with keys ret (gross directional), entry_dt, regime, symbol."""
    if not trades:
        return {"label": label, "n": 0, "verdict": "NO TRADES"}
    df = pd.DataFrame(trades)
    df["net_base"] = df["ret"] - FEE_BASE
    df["net_stress"] = df["ret"] - FEE_STRESS
    n = len(df)
    mean_gross = df["ret"].mean()
    mean_base = df["net_base"].mean()
    mean_stress = df["net_stress"].mean()
    ci_base = bootstrap_ci(df["net_base"].values)
    ci_stress = bootstrap_ci(df["net_stress"].values)
    wf = walk_forward(df)
    # regime breakdown
    reg = {}
    for r, g in df.groupby("regime"):
        reg[r] = {"n": len(g), "mean_base": float(g["net_base"].mean())}
    # win rate, total
    wr = float((df["net_base"] > 0).mean())
    res = {
        "label": label, "n": n,
        "mean_gross_bps": mean_gross*1e4,
        "mean_base_bps": mean_base*1e4, "ci_base_bps": (ci_base[0]*1e4, ci_base[1]*1e4),
        "mean_stress_bps": mean_stress*1e4, "ci_stress_bps": (ci_stress[0]*1e4, ci_stress[1]*1e4),
        "win_rate": wr,
        "total_net_base": float(df["net_base"].sum()),
        "regime": reg, "wf": wf,
        "first": str(df["entry_dt"].min().date()), "last": str(df["entry_dt"].max().date()),
    }
    return res

def verdict(res):
    """Apply the 3 hard tests. Returns (survives_bool, reason)."""
    if res.get("n", 0) < 30:
        return False, "too few trades (<30)"
    ci_lo = res["ci_base_bps"][0]
    full_ok = res["mean_base_bps"] > 0 and ci_lo > 0
    wf = res["wf"]
    wf_ok = wf is not None and wf["n_pos"] > wf["n_folds"]/2
    regs = {r: v for r, v in res["regime"].items() if r in ("bull","bear","chop") and v["n"] >= 15}
    pos_regs = sum(1 for v in regs.values() if v["mean_base"] > 0)
    multi_ok = len(regs) >= 2 and pos_regs >= 2
    survives = full_ok and wf_ok and multi_ok
    reasons = []
    reasons.append(f"full-sample CI>0: {'PASS' if full_ok else 'FAIL'} (mean {res['mean_base_bps']:.1f}bps, CI lo {ci_lo:.1f})")
    if wf:
        reasons.append(f"walk-fwd majority+: {'PASS' if wf_ok else 'FAIL'} ({wf['n_pos']}/{wf['n_folds']} folds, mean fold {wf['mean_fold']*1e4:.1f}bps)")
    else:
        reasons.append("walk-fwd: N/A (too few)")
    reasons.append(f"multi-regime: {'PASS' if multi_ok else 'FAIL'} ({pos_regs}/{len(regs)} regimes +)")
    return survives, " | ".join(reasons)

def print_res(res):
    print(f"\n=== {res['label']} ===")
    if res.get("n",0)==0:
        print("  NO TRADES"); return
    print(f"  n={res['n']}  span {res['first']}..{res['last']}  WR {res['win_rate']*100:.1f}%")
    print(f"  gross {res['mean_gross_bps']:.1f}bps | net@0.066% {res['mean_base_bps']:.1f}bps "
          f"CI[{res['ci_base_bps'][0]:.1f},{res['ci_base_bps'][1]:.1f}] | "
          f"net@stress {res['mean_stress_bps']:.1f}bps CI[{res['ci_stress_bps'][0]:.1f},{res['ci_stress_bps'][1]:.1f}]")
    print(f"  total net (base, sum of per-trade): {res['total_net_base']*100:.1f}% units")
    rs = " ".join(f"{r}:{v['n']}@{v['mean_base']*1e4:.0f}bps" for r,v in sorted(res['regime'].items()))
    print(f"  regime: {rs}")
    if res['wf']:
        fs = " ".join(f"f{r[0]}:{r[2]*1e4:.0f}" for r in res['wf']['folds'])
        print(f"  walk-fwd ({res['wf']['n_pos']}/{res['wf']['n_folds']}+): {fs}")
    sv, why = verdict(res)
    print(f"  VERDICT: {'*** SURVIVES ***' if sv else 'reject/artifact'} -- {why}")
    return sv
