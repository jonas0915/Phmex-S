#!/usr/bin/env python3
"""PART 2 — Run the absorption signal on OUR ACTUAL REALIZED TRADES.
Fully independent dataset (real money). Read-only.

Join: closed_trades[].entry_snapshot.ob.imbalance + .flow.buy_ratio + side + realized PnL.
Also try to expand coverage via entry_snapshots.jsonl matched on ts.
"""
import json
from collections import defaultdict

d = json.load(open('trading_state.json'))
ct = d['closed_trades']
print(f"closed_trades total: {len(ct)}")

# ---- Build trade records that have entry signal + realized PnL ----
# Prefer net_pnl; fall back note count.
def pnl_of(t):
    # return (net_or_gross_pnl, is_net)
    if t.get('net_pnl') is not None:
        return t['net_pnl'], True
    return t.get('pnl_usdt'), False

trades = []
n_have_sig = 0; n_net = 0; n_gross_only = 0
for t in ct:
    es = t.get('entry_snapshot')
    if not (es and isinstance(es, dict)):
        continue
    ob = es.get('ob') or {}
    fl = es.get('flow') or {}
    im = ob.get('imbalance'); br = fl.get('buy_ratio')
    if im is None or br is None:
        continue
    n_have_sig += 1
    pnl, is_net = pnl_of(t)
    if pnl is None:
        continue
    if is_net: n_net += 1
    else: n_gross_only += 1
    trades.append({
        'symbol': t['symbol'], 'side': t['side'], 'imb': im, 'br': br,
        'pnl': pnl, 'is_net': is_net,
        'pnl_pct': t.get('pnl_pct'), 'strategy': t.get('strategy'),
    })

print(f"trades with entry signal (imb+br): {n_have_sig}")
print(f"  with usable PnL: {len(trades)}  (net_pnl: {n_net}, gross-only fallback: {n_gross_only})")

# Side breakdown
from collections import Counter
sc = Counter(t['side'] for t in trades)
print(f"  sides: {dict(sc)}")

def summarize(label, sel):
    n = len(sel)
    if n == 0:
        print(f"  {label:48s} n=0")
        return
    wins = sum(1 for t in sel if t['pnl'] > 0)
    tot = sum(t['pnl'] for t in sel)
    avg = tot/n
    wr = wins/n*100
    flag = "  <-- SMALL N" if n < 15 else ""
    print(f"  {label:48s} n={n:3d}  WR={wr:5.1f}%  avg_net=${avg:+.4f}  total=${tot:+.3f}{flag}")

ABS = lambda t: t['imb'] >= 0.3 and t['br'] >= 0.6

# ============================================================
# (a) SHORT trades: absorption-aligned vs other shorts
# ============================================================
print("\n" + "="*70)
print("(a) SHORT trades — absorption-aligned (imb>=.3 & br>=.6) vs other shorts")
print("    Absorption predicts shorts WIN. So aligned shorts should do BETTER.")
print("="*70)
shorts = [t for t in trades if t['side'] == 'short']
summarize("ALL shorts", shorts)
summarize("Shorts WITH absorption (imb>=.3 & br>=.6)", [t for t in shorts if ABS(t)])
summarize("Shorts WITHOUT absorption", [t for t in shorts if not ABS(t)])

# ============================================================
# (b) 2D bucket: imbalance x buy_ratio, realized WR/avg net (all trades & shorts)
# ============================================================
print("\n" + "="*70)
print("(b) 2D BUCKETS imbalance x buy_ratio — realized WR / avg net")
print("="*70)
imb_bins = [(-1.01,-0.3),(-0.3,0.0),(0.0,0.3),(0.3,1.01)]
br_bins = [(-0.01,0.4),(0.4,0.6),(0.6,1.01)]
imb_lbl = ['imb<-.3','-.3..0','0..0.3','imb>=.3']
br_lbl = ['br<0.4','0.4-0.6','br>=0.6']

def bucket2d(pool, title):
    print(f"\n  --- {title} (n={len(pool)}) ---")
    print(f"  {'':10s}" + "".join(f"{b:>20s}" for b in br_lbl))
    for (ilo,ihi),il in zip(imb_bins,imb_lbl):
        cells=[]
        for (blo,bhi) in br_bins:
            sel=[t for t in pool if ilo<t['imb']<=ihi and blo<t['br']<=bhi]
            if sel:
                wr=sum(1 for t in sel if t['pnl']>0)/len(sel)*100
                avg=sum(t['pnl'] for t in sel)/len(sel)
                cells.append(f"n{len(sel)} {wr:.0f}% ${avg:+.3f}")
            else:
                cells.append("-")
        print(f"  {il:10s}" + "".join(f"{c:>20s}" for c in cells))

bucket2d(trades, "ALL trades")
bucket2d(shorts, "SHORTS only")
bucket2d([t for t in trades if t['side']=='long'], "LONGS only")

# ============================================================
# (c) Absorption as an ENTRY FILTER: filtered vs actual book
# ============================================================
print("\n" + "="*70)
print("(c) ABSORPTION AS ENTRY FILTER — filtered book vs actual book")
print("    Rule: only take SHORTS when imb>=.3 & br>=.6; AVOID LONGS into absorption.")
print("="*70)
actual_total = sum(t['pnl'] for t in trades)
actual_n = len(trades)
print(f"  ACTUAL realized book (signal-tagged trades): n={actual_n}  total=${actual_total:+.3f}")

# Filter variants:
# F1: keep only absorption-aligned shorts (drop everything else)
f1 = [t for t in trades if t['side']=='short' and ABS(t)]
summarize("F1: ONLY absorption-aligned shorts", f1)

# F2: drop longs that entered into absorption (imb>=.3 & br>=.6), keep rest
f2 = [t for t in trades if not (t['side']=='long' and ABS(t))]
summarize("F2: drop longs-into-absorption, keep rest", f2)
print(f"      vs actual ${actual_total:+.3f} -> delta from dropping those longs: "
      f"${sum(t['pnl'] for t in f2)-actual_total:+.3f}")

# F3: combine: drop longs-into-absorption AND require shorts to be absorption-aligned
f3 = [t for t in trades if (t['side']=='short' and ABS(t)) or (t['side']=='long' and not ABS(t))]
summarize("F3: abs-shorts + non-abs-longs", f3)

# What did the dropped longs-into-absorption do?
dropped_longs = [t for t in trades if t['side']=='long' and ABS(t)]
summarize("(longs that entered INTO absorption - dropped)", dropped_longs)

# ============================================================
# Marginal: imbalance-alone and buy_ratio-alone effect on realized PnL
# ============================================================
print("\n" + "="*70)
print("Marginal checks (realized): does each leg show up alone?")
print("="*70)
summarize("Shorts with imb>=.3 (any br)", [t for t in shorts if t['imb']>=0.3])
summarize("Shorts with br>=.6 (any imb)", [t for t in shorts if t['br']>=0.6])
summarize("Shorts imb<.3 & br<.6", [t for t in shorts if t['imb']<0.3 and t['br']<0.6])

# INJ presence in our trades
print("\n  Symbol breakdown of absorption-aligned shorts:")
for sym,c in Counter(t['symbol'] for t in shorts if ABS(t)).most_common():
    sel=[t for t in shorts if ABS(t) and t['symbol']==sym]
    tot=sum(x['pnl'] for x in sel)
    print(f"    {sym:22s} n={c:2d} total=${tot:+.3f}")
