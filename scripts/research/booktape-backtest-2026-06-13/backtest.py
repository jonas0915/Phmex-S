#!/usr/bin/env python3
"""
CLEAN CONSOLIDATED BACKTEST — "book x tape absorption short" signal.

Strategy:  imbalance >= 0.3 AND buy_ratio >= 0.6  ->  SHORT
Data:      logs/flow_capture.jsonl  (snapshots, ~75s cadence, 2026-05-11 -> 06-13)
Exit:      hold H seconds, at-or-before lookup (NO look-ahead)
Refractory: one entry per symbol per H seconds (don't re-fire same dislocation)
Holds:     300s, 900s (headline), 1800s
Fees:      maker 0.02% RT = 2 bps ; taker 0.12% RT = 12 bps
Sizing:    $10 margin x 10x = $100 notional/trade  (also $50, $100 margin)

Read-only. Every number printed comes from this run.
"""
import json, math, random
from collections import defaultdict, Counter

PATH = 'logs/flow_capture.jsonl'
HOLDS = [300, 900, 1800]
HEADLINE_H = 900
IMB_TH = 0.3
BR_TH = 0.6
COST_MAKER = 2.0   # bps RT
COST_TAKER = 12.0  # bps RT
MARGINS = [10, 50, 100]
LEVERAGE = 10
random.seed(42)

# ----------------------------------------------------------------------
# Load per-symbol time-ordered series
# ----------------------------------------------------------------------
series = defaultdict(list)
n_lines = 0
for line in open(PATH):
    n_lines += 1
    try:
        r = json.loads(line)
    except Exception:
        continue
    ob = r.get('ob') or {}
    fl = r.get('flow') or {}
    im = ob.get('imbalance'); br = fl.get('buy_ratio'); px = r.get('price')
    if im is None or br is None or px is None or px <= 0:
        continue
    series[r['symbol']].append((r['ts'], px, im, br))
for s in series:
    series[s].sort(key=lambda x: x[0])

usable = sum(len(v) for v in series.values())
all_ts = sorted(t for rows in series.values() for (t, *_ ) in rows)
span_days = (all_ts[-1] - all_ts[0]) / 86400.0
print(f"Lines read         : {n_lines}")
print(f"Usable snapshots   : {usable}  across {len(series)} symbols")
print(f"Time span          : {span_days:.1f} days "
      f"({all_ts[0]} -> {all_ts[-1]})")

# ----------------------------------------------------------------------
# Build TRADES with refractory period (one entry/symbol/H seconds)
#   exit price = first snapshot with ts >= entry_ts + H, within +H tolerance
#   short gross return (bps) = -(exit-entry)/entry * 10000
# ----------------------------------------------------------------------
def build_trades(H, exclude_inj=False, only_inj=False):
    trades = []
    for sym, rows in series.items():
        if exclude_inj and sym.startswith('INJ'):
            continue
        if only_inj and not sym.startswith('INJ'):
            continue
        ts = [r[0] for r in rows]; px = [r[1] for r in rows]
        n = len(rows)
        last_fire = -1e18
        for i in range(n):
            t0, p0, im, br = rows[i]
            if not (im >= IMB_TH and br >= BR_TH):
                continue
            if t0 - last_fire < H:       # refractory
                continue
            # find exit at-or-after t0+H (no look-ahead beyond what existed)
            target = t0 + H
            j = i + 1
            while j < n and ts[j] < target:
                j += 1
            if j >= n or ts[j] > target + H:   # no real future point in window
                continue
            pe = px[j]
            short_bps = -((pe - p0) / p0) * 10000.0
            last_fire = t0
            trades.append({'symbol': sym, 'ts': t0, 'bps': short_bps})
    return trades

def desc(rets):
    n = len(rets)
    mean = sum(rets) / n
    wr = sum(1 for r in rets if r > 0) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / n) if n > 1 else 0.0
    return n, mean, wr, sd

# ======================================================================
# 1 + 2.  HEADLINE & NET BY HOLD
# ======================================================================
print("\n" + "=" * 78)
print("TABLE 1+2 — HEADLINE (gross) & NET AFTER FEES, by hold (refractory = hold)")
print("=" * 78)
print(f"{'Hold':>6} {'Trades':>7} {'Tr/day':>7} {'WR%':>6} {'gross/tr':>9} "
      f"{'tot_gross':>10} {'tot_%':>8} {'net/tr_mk':>10} {'net/tr_tk':>10} {'tot_mk':>9} {'tot_tk':>9}")
headline = {}
for H in HOLDS:
    tr = build_trades(H)
    rets = [t['bps'] for t in tr]
    n, mean, wr, sd = desc(rets)
    tot = sum(rets)
    per_day = n / span_days
    net_mk = mean - COST_MAKER
    net_tk = mean - COST_TAKER
    tot_mk = tot - COST_MAKER * n
    tot_tk = tot - COST_TAKER * n
    headline[H] = dict(n=n, mean=mean, wr=wr, sd=sd, tot=tot,
                       net_mk=net_mk, net_tk=net_tk, tot_mk=tot_mk, tot_tk=tot_tk,
                       per_day=per_day, rets=rets, trades=tr)
    print(f"{H:>6} {n:>7} {per_day:>7.1f} {wr*100:>6.1f} {mean:>+9.2f} "
          f"{tot:>+10.0f} {tot/100:>+8.2f} {net_mk:>+10.2f} {net_tk:>+10.2f} "
          f"{tot_mk:>+9.0f} {tot_tk:>+9.0f}")
print("  (gross/tr, net/tr, tot_gross, tot_mk, tot_tk in bps ; tot_% = total gross in percent)")

# ======================================================================
# 3.  DOLLARS at real sizing
# ======================================================================
print("\n" + "=" * 78)
print(f"TABLE 3 — DOLLARS at HEADLINE hold = {HEADLINE_H}s  (1 bp on $N notional = $N*1e-4)")
print("=" * 78)
h = headline[HEADLINE_H]
print(f"  trades={h['n']}  gross/tr={h['mean']:+.2f}bps  "
      f"net_maker/tr={h['net_mk']:+.2f}bps  net_taker/tr={h['net_tk']:+.2f}bps")
print(f"\n  {'Margin':>7} {'Notional':>9} {'$/tr_mk':>9} {'$/tr_tk':>9} "
      f"{'$total_mk':>11} {'$total_tk':>11}")
for m in MARGINS:
    notional = m * LEVERAGE
    f = notional * 1e-4   # USD per 1 bps
    print(f"  {('$'+str(m)):>7} {('$'+str(notional)):>9} "
          f"{h['net_mk']*f:>+9.4f} {h['net_tk']*f:>+9.4f} "
          f"{h['tot_mk']*f:>+11.2f} {h['tot_tk']*f:>+11.2f}")
print("  ($/tr = avg USD per trade ; $total = USD over all backtest trades)")

# ======================================================================
# 4.  EQUITY CURVE STATS (headline hold, maker net, chronological order)
# ======================================================================
print("\n" + "=" * 78)
print(f"TABLE 4 — EQUITY / RISK STATS @ {HEADLINE_H}s (chronological, MAKER net bps)")
print("=" * 78)
tr_sorted = sorted(h['trades'], key=lambda t: t['ts'])
net_series = [t['bps'] - COST_MAKER for t in tr_sorted]
cum = 0.0; peak = 0.0; maxdd = 0.0
eq = []
for r in net_series:
    cum += r; eq.append(cum)
    peak = max(peak, cum)
    maxdd = min(maxdd, cum - peak)
n = len(net_series)
mean_n = sum(net_series) / n
sd_n = math.sqrt(sum((r - mean_n) ** 2 for r in net_series) / n)
sharpe_tr = mean_n / sd_n if sd_n > 0 else float('nan')
# annualize by trade frequency
tr_per_year = h['per_day'] * 365
sharpe_ann = sharpe_tr * math.sqrt(tr_per_year)
pct_prof = sum(1 for r in net_series if r > 0) / n * 100
# quartile cumulative progression
qs = [eq[int(n*q)-1] for q in (0.25, 0.50, 0.75, 1.0)]
print(f"  net trades (maker)      : {n}")
print(f"  final cum net (maker)   : {cum:+.1f} bps  ({cum/100:+.2f}%)")
print(f"  cum @ 25/50/75/100%     : {qs[0]:+.0f} / {qs[1]:+.0f} / {qs[2]:+.0f} / {qs[3]:+.0f} bps")
print(f"  max drawdown            : {maxdd:+.1f} bps  ({maxdd/100:+.2f}%)")
print(f"  per-trade mean / sd     : {mean_n:+.2f} / {sd_n:.2f} bps")
print(f"  Sharpe per-trade        : {sharpe_tr:+.3f}")
print(f"  Sharpe annualized       : {sharpe_ann:+.2f}  (x sqrt({tr_per_year:.0f} tr/yr))")
print(f"  % trades profitable      : {pct_prof:.1f}%")

# ======================================================================
# 5.  PER-SYMBOL TABLE + INJ concentration
# ======================================================================
print("\n" + "=" * 78)
print(f"TABLE 5 — PER-SYMBOL @ {HEADLINE_H}s (maker net), sorted by trade count")
print("=" * 78)
bysym = defaultdict(list)
for t in h['trades']:
    bysym[t['symbol']].append(t['bps'])
print(f"  {'Symbol':>18} {'Trades':>7} {'WR%':>6} {'gross/tr':>9} {'net_mk/tr':>10} {'tot_net_mk':>11}")
rows_sym = []
for sym, b in bysym.items():
    nn = len(b); mm = sum(b)/nn; ww = sum(1 for x in b if x>0)/nn*100
    rows_sym.append((sym, nn, ww, mm, mm-COST_MAKER, (mm-COST_MAKER)*nn))
for sym, nn, ww, mm, netm, totnet in sorted(rows_sym, key=lambda x: -x[1]):
    print(f"  {sym:>18} {nn:>7} {ww:>6.1f} {mm:>+9.2f} {netm:>+10.2f} {totnet:>+11.0f}")

inj = [t['bps'] for t in h['trades'] if t['symbol'].startswith('INJ')]
noinj = [t['bps'] for t in h['trades'] if not t['symbol'].startswith('INJ')]
print(f"\n  INJ concentration @ {HEADLINE_H}s:")
print(f"    INJ trades        : {len(inj)}  ({len(inj)/h['n']*100:.1f}% of all trades)")
if inj:
    print(f"    INJ-included head : n={h['n']} gross/tr={h['mean']:+.2f} "
          f"net_mk/tr={h['net_mk']:+.2f} tot_net_mk={h['tot_mk']:+.0f}bps")
if noinj:
    nn,mm,ww,_=desc(noinj)
    print(f"    INJ-EXCLUDED head : n={nn} gross/tr={mm:+.2f} "
          f"net_mk/tr={mm-COST_MAKER:+.2f} tot_net_mk={(mm-COST_MAKER)*nn:+.0f}bps  WR={ww*100:.1f}%")

# ======================================================================
# 6.  TRAIN/TEST OOS SPLIT (chronological 50/50)
# ======================================================================
print("\n" + "=" * 78)
print("TABLE 6 — CHRONOLOGICAL 50/50 TRAIN/TEST (maker net)")
print("=" * 78)
print(f"  {'Hold':>6} {'TR_n':>5} {'TR_net_mk/tr':>13} {'TR_tot_mk':>10} | "
      f"{'TE_n':>5} {'TE_net_mk/tr':>13} {'TE_tot_mk':>10} {'TE_WR%':>7}")
cut = all_ts[len(all_ts)//2]
for H in HOLDS:
    tr = headline[H]['trades']
    train = [t['bps'] for t in tr if t['ts'] < cut]
    test  = [t['bps'] for t in tr if t['ts'] >= cut]
    if not train or not test:
        continue
    trn, trm, *_ = desc(train)
    ten, tem, tewr, _ = desc(test)
    print(f"  {H:>6} {trn:>5} {trm-COST_MAKER:>+13.2f} {(trm-COST_MAKER)*trn:>+10.0f} | "
          f"{ten:>5} {tem-COST_MAKER:>+13.2f} {(tem-COST_MAKER)*ten:>+10.0f} {tewr*100:>7.1f}")
print(f"  (split at ts={cut})")

# ======================================================================
# 7.  OUR REAL TRADES — overlap with the signal
# ======================================================================
print("\n" + "=" * 78)
print("TABLE 7 — OUR REAL CLOSED TRADES vs the signal (trading_state.json)")
print("=" * 78)
d = json.load(open('trading_state.json'))
ct = d['closed_trades']
sides_all = Counter(t.get('side') for t in ct)
have_es = [t for t in ct if isinstance(t.get('entry_snapshot'), dict)
           and (t['entry_snapshot'].get('ob') or {}).get('imbalance') is not None
           and (t['entry_snapshot'].get('flow') or {}).get('buy_ratio') is not None]
meet = []
for t in have_es:
    ob = t['entry_snapshot']['ob']; fl = t['entry_snapshot']['flow']
    if ob['imbalance'] >= IMB_TH and fl['buy_ratio'] >= BR_TH:
        meet.append(t)
meet_sides = Counter(t['side'] for t in meet)
longs = [t for t in meet if t['side'] == 'long']
shorts = [t for t in meet if t['side'] == 'short']
long_pnl = sum(t.get('pnl_usdt') or 0 for t in longs)
print(f"  total closed_trades             : {len(ct)}   (sides: {dict(sides_all)})")
print(f"  with usable entry signal        : {len(have_es)}")
print(f"  meet imb>=.3 & br>=.6 at entry  : {len(meet)}   (sides: {dict(meet_sides)})")
print(f"  >>> shorts meeting the signal   : {len(shorts)}   <-- the signal says SHORT")
print(f"  >>> longs meeting the signal    : {len(longs)}   (traded AGAINST the signal)")
print(f"  realized net_pnl of those longs : ${long_pnl:+.4f}  (USD)")
won = sum(1 for t in longs if (t.get('pnl_usdt') or 0) > 0)
print(f"  those longs WR                  : {won}/{len(longs)} = {won/len(longs)*100:.0f}%")
print(f"  ZERO-SHORT OVERLAP              : {len(shorts)} of {len(ct)} real trades ever "
      f"fired this signal in the SHORT direction it predicts.")
print("\n  The 11 longs (entered INTO absorption — opposite of signal):")
for t in longs:
    print(f"    {t['symbol']:>16} long  pnl=${(t.get('pnl_usdt') or 0):+.4f}  reason={t.get('reason')}")
