#!/usr/bin/env python3
"""Ground-truth per-symbol PnL audit of the main Phmex-S bot.
Source: trading_state.json -> closed_trades. No fabrication; everything computed."""
import json, random, datetime, statistics
from collections import defaultdict

random.seed(42)
STATE = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state.json"
# Static scanner blacklist (already-disabled symbols) read from config/.env
BLACKLIST = {"TRUMP/USDT:USDT","FET/USDT:USDT","TIA/USDT:USDT","NEAR/USDT:USDT",
             "OP/USDT:USDT","BNB/USDT:USDT","SOL/USDT:USDT","SUI/USDT:USDT","LINK/USDT:USDT"}

d = json.load(open(STATE))
ct = d["closed_trades"]
print(f"Raw closed_trades: {len(ct)}")

# Best-effort PnL: net_pnl (fee-inclusive) when present, else gross pnl_usdt.
def pnl(t):
    return t["net_pnl"] if "net_pnl" in t else t.get("pnl_usdt", 0.0)

# Exclude non-executed skips (min_margin_skip / shadow_skip => 0 notional, 0 pnl)
def is_real(t):
    r = t.get("reason") or t.get("exit_reason") or ""
    if r in ("min_margin_skip",): return False
    if t.get("shadow_skip"): return False
    return True

real = [t for t in ct if is_real(t)]
skipped = len(ct) - len(real)
print(f"Excluded non-executed (min_margin_skip/shadow): {skipped}")
print(f"Real executed trades: {len(real)}")
print(f"TOTAL NET PnL (all real): {sum(pnl(t) for t in real):.2f}")
print(f"  (net_pnl present: {sum(1 for t in real if 'net_pnl' in t)}, gross-only: {sum(1 for t in real if 'net_pnl' not in t)})")
print(f"  sum gross pnl_usdt all real: {sum(t.get('pnl_usdt',0) for t in real):.2f}")
print()

def boot_ci(vals, n=10000):
    if len(vals) < 2: return (float('nan'), float('nan'))
    means = []
    k = len(vals)
    for _ in range(n):
        s = sum(vals[random.randrange(k)] for _ in range(k))
        means.append(s / k)
    means.sort()
    return means[int(0.025*n)], means[int(0.975*n)]

by = defaultdict(list)
for t in real:
    by[t["symbol"]].append(t)

rows = []
for sym, ts in by.items():
    pnls = [pnl(t) for t in ts]
    net = sum(pnls)
    n = len(ts)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    wr = len(wins)/n*100
    avg_w = statistics.mean(wins) if wins else 0.0
    avg_l = statistics.mean(losses) if losses else 0.0
    payoff = (avg_w/abs(avg_l)) if avg_l != 0 else float('inf')
    exp = net/n
    lo, hi = boot_ci(pnls)
    tss = [t["closed_at"] for t in ts if "closed_at" in t]
    first = datetime.datetime.fromtimestamp(min(tss)) if tss else None
    last  = datetime.datetime.fromtimestamp(max(tss)) if tss else None
    rows.append(dict(sym=sym, n=n, net=net, wr=wr, avg_w=avg_w, avg_l=avg_l,
                     payoff=payoff, exp=exp, lo=lo, hi=hi, first=first, last=last,
                     blacklisted=sym in BLACKLIST))

rows.sort(key=lambda r: r["net"])  # most negative first

def sname(s): return s.replace("/USDT:USDT","")
def dt(x): return x.strftime("%m-%d") if x else "?"

print(f"{'SYMBOL':<8}{'N':>4}{'NET$':>9}{'WR%':>6}{'avgW':>7}{'avgL':>7}{'pay':>6}{'exp$':>8}{'CI95 (exp/trade)':>22}{'  span':>12}  TRADED?")
print("-"*100)
for r in rows:
    traded = "DISABLED" if r["blacklisted"] else "YES"
    ci = f"[{r['lo']:+.3f},{r['hi']:+.3f}]"
    pay = f"{r['payoff']:.2f}" if r['payoff']!=float('inf') else "inf"
    print(f"{sname(r['sym']):<8}{r['n']:>4}{r['net']:>9.2f}{r['wr']:>6.0f}{r['avg_w']:>7.3f}{r['avg_l']:>7.3f}{pay:>6}{r['exp']:>8.3f}{ci:>22}{dt(r['first'])+'->'+dt(r['last']):>12}  {traded}")

# Concentration
print()
tot = sum(r["net"] for r in rows)
negs = sorted([r for r in rows if r["net"]<0], key=lambda r:r["net"])
print(f"Net across all symbols: {tot:.2f}")
print(f"Negative symbols: {len(negs)}  | Positive: {sum(1 for r in rows if r['net']>0)}")
cum=0
print("\nConcentration of losses (worst-first), share of total negative pool:")
totneg = sum(r['net'] for r in negs)
for r in negs[:10]:
    cum+=r['net']
    print(f"  {sname(r['sym']):<8} net {r['net']:>8.2f}  cum {cum:>8.2f}  ({cum/totneg*100:>4.0f}% of neg pool)  {'DISABLED' if r['blacklisted'] else 'TRADED'}")

# Actionable: currently-traded (non-blacklisted) losers, CI upper bound < 0 = statistically bleeding
print("\nActionable currently-traded bleeders (CI95 upper < 0 = stat-sig negative expectancy):")
for r in negs:
    if not r["blacklisted"] and r["hi"] < 0:
        print(f"  {sname(r['sym']):<8} n={r['n']:<3} net {r['net']:>7.2f} exp {r['exp']:+.3f} CI[{r['lo']:+.3f},{r['hi']:+.3f}] span {dt(r['first'])}->{dt(r['last'])}")
print("\nCurrently-traded losers NOT stat-sig (wide CI / low-n, net<0 but CI crosses 0):")
for r in negs:
    if not r["blacklisted"] and r["hi"] >= 0:
        print(f"  {sname(r['sym']):<8} n={r['n']:<3} net {r['net']:>7.2f} exp {r['exp']:+.3f} CI[{r['lo']:+.3f},{r['hi']:+.3f}] span {dt(r['first'])}->{dt(r['last'])}")
print("\nReliably positive currently-traded (CI95 lower > 0):")
for r in sorted(rows,key=lambda r:-r['net']):
    if not r["blacklisted"] and r["lo"] > 0:
        print(f"  {sname(r['sym']):<8} n={r['n']:<3} net {r['net']:>7.2f} exp {r['exp']:+.3f} CI[{r['lo']:+.3f},{r['hi']:+.3f}] span {dt(r['first'])}->{dt(r['last'])}")
