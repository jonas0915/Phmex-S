#!/usr/bin/env python3
"""Finish the fee ground-truth analysis from cached raw_fills.json.

READ-ONLY: no API calls. Works purely from raw_fills.json + trading_state.json.

Maker/taker classification: the ccxt takerOrMaker flag is null for Phemex,
but each fill carries the exchange's own per-fill fee rate (fee_rate /
info_feeRateRr). Classification rule:
    rate <= 0.0002  -> maker   (maker tier is 0.0001 = 0.01%)
    rate >= 0.0005  -> taker   (taker tier is 0.0006 = 0.06%)
    in between      -> flagged
Cross-checked against Phemex execStatus (6=MakerFill, 7=TakerFill) and
ordType (2=Limit, 3=Stop/market-on-trigger).
"""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
RAW = json.loads((HERE / "raw_fills.json").read_text())
STATE = json.loads((ROOT / "trading_state.json").read_text())

MATCH_WINDOW_SEC = 60          # role matching (same as fee_truth.py)
XCHECK_WINDOW_SEC = 300        # cross-check matching per task spec (±5 min)
fmt = lambda s: time.strftime("%Y-%m-%d %I:%M %p", time.localtime(s))

fills = [f for fl in RAW.values() for f in fl]
fills.sort(key=lambda f: f["timestamp"])
closed = STATE["closed_trades"]


def fee(f):
    return abs(float(f.get("fee_cost") or f.get("info_execFeeRv") or 0))


def rate(f):
    r = f.get("fee_rate")
    if r is None and f.get("info_feeRateRr") is not None:
        r = float(f["info_feeRateRr"])
    return float(r) if r is not None else None


def mt(f):
    r = rate(f)
    if r is None:
        return "unknown"
    if r <= 0.0002:
        return "maker"
    if r >= 0.0005:
        return "taker"
    return "flagged"


# ---- 1. field availability + classification ------------------------------
print("=" * 76)
print("1. PER-FILL FEE-RATE FIELDS")
print("=" * 76)
n_rate = sum(1 for f in fills if rate(f) is not None)
n_tom = sum(1 for f in fills if f.get("takerOrMaker"))
print(f"fills total={len(fills)}  with takerOrMaker={n_tom}  with fee_rate/feeRateRr={n_rate}")
print("distinct fee_rate values:", dict(Counter(rate(f) for f in fills)))
print("distinct execStatus:", dict(Counter(f.get("info_execStatus") for f in fills)))
print("distinct ordType:", dict(Counter(f.get("info_ordType") for f in fills)))
# corroborate rate-class vs execStatus
xt = Counter((mt(f), f.get("info_execStatus")) for f in fills)
print("rate-class x execStatus:", dict(xt))
xo = Counter((mt(f), f.get("info_ordType")) for f in fills)
print("rate-class x ordType:", dict(xo))

# ---- role matching (entry/exit) same rule as fee_truth.py ----------------
by_sym = defaultdict(list)
for t in closed:
    if t.get("symbol"):
        by_sym[t["symbol"]].append(t)

for f in fills:
    f["role"], f["trade_key"], f["dist"] = "unmatched", None, None
    ts = f["timestamp"] / 1000
    best = None
    for t in by_sym.get(f["symbol"], []):
        for role, anchor in (("entry", t.get("opened_at")), ("exit", t.get("closed_at"))):
            if not anchor:
                continue
            d = abs(ts - anchor)
            if best is None or d < best[0]:
                if d <= MATCH_WINDOW_SEC:
                    best = (d, role, (t["opened_at"], t["symbol"], t["closed_at"]))
    if best:
        f["dist"], f["role"], f["trade_key"] = best


def split(sub, label):
    tot_n = sum(f["cost"] for f in sub)
    tot_f = sum(fee(f) for f in sub)
    print(f"\n[{label}] fills={len(sub)} notional=${tot_n:.2f} fees=${tot_f:.4f} "
          f"rate={100*tot_f/tot_n:.4f}%" if tot_n else f"\n[{label}] empty")
    for cls in ("maker", "taker", "flagged", "unknown"):
        s = [f for f in sub if mt(f) == cls]
        if not s:
            continue
        n = sum(f["cost"] for f in s)
        ff = sum(fee(f) for f in s)
        print(f"  {cls:<8} fills={len(s):>3} ({100*len(s)/len(sub):.1f}% by count, "
              f"{100*n/tot_n:.1f}% by notional)  notional=${n:.2f}  fees=${ff:.4f}  "
              f"rate={100*ff/n:.4f}%")


print()
print("=" * 76)
print("2. MAKER/TAKER SPLIT (classified by exchange-reported per-fill fee rate)")
print("=" * 76)
split(fills, "ALL")
for role in ("entry", "exit", "unmatched"):
    split([f for f in fills if f["role"] == role], role.upper())

# ---- 3. cross-check vs trading_state fees_usdt (±5 min) ------------------
print()
print("=" * 76)
print("3. CROSS-CHECK vs trading_state.json fees_usdt (match ±5 min)")
print("=" * 76)
fill_used = set()
rows = []
for t in closed:
    if t.get("fees_usdt") is None:
        continue
    o, c = t.get("opened_at"), t.get("closed_at")
    mine = []
    for i, f in enumerate(fills):
        if f["symbol"] != t["symbol"] or i in fill_used:
            continue
        ts = f["timestamp"] / 1000
        if (o and abs(ts - o) <= XCHECK_WINDOW_SEC) or (c and abs(ts - c) <= XCHECK_WINDOW_SEC):
            mine.append(i)
    if mine:
        for i in mine:
            fill_used.add(i)
        ph = sum(fee(fills[i]) for i in mine)
        rows.append((t, ph, len(mine)))

loc = sum(float(t["fees_usdt"]) for t, _, _ in rows)
ph = sum(p for _, p, _ in rows)
print(f"closed_trades with fees_usdt: {sum(1 for t in closed if t.get('fees_usdt') is not None)}")
print(f"matched to fills here (±5min): {len(rows)} trades covering "
      f"{sum(k for _, _, k in rows)} fills")
print(f"sum local fees_usdt = ${loc:.4f}   sum Phemex fill fees = ${ph:.4f}   "
      f"delta = ${ph-loc:+.4f} ({100*(ph-loc)/loc:+.2f}%)")
bad = [(t, p) for t, p, _ in rows if abs(p - float(t["fees_usdt"])) > 0.005]
print(f"trades with |delta| > $0.005: {len(bad)}")
for t, p in sorted(bad, key=lambda x: -abs(x[1] - float(x[0]['fees_usdt'])))[:12]:
    print(f"  {fmt(t['closed_at'])} {t['symbol']:<18} local={float(t['fees_usdt']):.4f} "
          f"phemex={p:.4f} d={p-float(t['fees_usdt']):+.4f} reason={t.get('exit_reason')}")

# ---- 4. the 28 unmatched fills -------------------------------------------
print()
print("=" * 76)
print("4. UNMATCHED FILLS — what are they?")
print("=" * 76)
unm = [f for f in fills if f["role"] == "unmatched"]
print(f"count={len(unm)}")
for f in unm:
    ts = f["timestamp"] / 1000
    # nearest closed-trade anchor on same symbol
    nd, nrole = None, None
    for t in by_sym.get(f["symbol"], []):
        for role, anchor in (("open", t.get("opened_at")), ("close", t.get("closed_at"))):
            if anchor:
                d = ts - anchor
                if nd is None or abs(d) < abs(nd):
                    nd, nrole = d, role
    print(f"  {fmt(ts)} {f['symbol']:<18} {f['side']:<4} {mt(f):<6} "
          f"rate={rate(f)} cost=${f['cost']:.2f} fee=${fee(f):.4f} "
          f"ordType={f['info_ordType']} nearest={nrole} {nd:+.0f}s")

# how many fall within ±5min of a trade (i.e. only missed the 60s window)?
near = sum(1 for f in unm if any(
    (t.get("opened_at") and abs(f["timestamp"]/1000 - t["opened_at"]) <= XCHECK_WINDOW_SEC) or
    (t.get("closed_at") and abs(f["timestamp"]/1000 - t["closed_at"]) <= XCHECK_WINDOW_SEC)
    for t in by_sym.get(f["symbol"], [])))
print(f"\nunmatched fills that ARE within ±5 min of a closed trade: {near}/{len(unm)}")

# ---- 5. decision math ------------------------------------------------------
print()
print("=" * 76)
print("5. DECISION MATH")
print("=" * 76)
last50 = sorted([t for t in closed if t.get("closed_at")], key=lambda t: t["closed_at"])[-50:]
for label, key in (("gross pnl_usdt", "pnl_usdt"), ("net_pnl", "net_pnl")):
    vals = [float(t.get(key)) for t in last50 if t.get(key) is not None]
    w = [v for v in vals if v > 0]
    l = [-v for v in vals if v < 0]
    if w and l:
        print(f"last-50 by {label}: n={len(vals)} wins={len(w)} avgW=${sum(w)/len(w):.4f} "
              f"losses={len(l)} avgL=${sum(l)/len(l):.4f} WR={100*len(w)/len(vals):.1f}%")

# audit numbers given: W=0.485, L=0.660 on $100 notional
W, L, N = 0.485, 0.660, 100.0
print(f"\nUsing audit last-50 numbers: avg win=+${W} avg loss=-${L} notional=${N}/trade")
print("breakeven WR = (L + F) / (W + L)   where F = RT fee rate x notional")
scens = [("(a) measured 0.0663% RT", 0.000663),
         ("(b) canonical taker 0.12% RT", 0.0012),
         ("(c1) full-maker 0.02% RT", 0.0002),
         ("(c2) full-maker upper 0.04% RT", 0.0004)]
res = {}
for name, r in scens:
    F = r * N
    be = (L + F) / (W + L)
    res[name] = be
    print(f"  {name:<32} F=${F:.4f}/trade  breakeven WR = {100*be:.2f}%")
print(f"  headroom (a)->(c1): {100*(res[scens[0][0]] - res[scens[2][0]]):.2f} WR pts")
print(f"  headroom (b)->(a):  {100*(res[scens[1][0]] - res[scens[0][0]]):.2f} WR pts")

# Kelly under (c): shift each last-50 net pnl by the per-trade fee savings
print("\nKelly f* = p - (1-p)/b,  b = avgW/avgL  (last-50, net_pnl)")
vals = [float(t["net_pnl"]) for t in last50 if t.get("net_pnl") is not None]
for name, save in (("as-is (measured fees)", 0.0),
                   ("full-maker exits 0.02% RT (save $0.0463/trade)", (0.000663 - 0.0002) * N),
                   ("full-maker exits 0.04% RT (save $0.0263/trade)", (0.000663 - 0.0004) * N)):
    adj = [v + save for v in vals]
    w = [v for v in adj if v > 0]
    l = [-v for v in adj if v < 0]
    p = len(w) / len(adj)
    b = (sum(w) / len(w)) / (sum(l) / len(l))
    f_star = p - (1 - p) / b
    print(f"  {name:<48} p={100*p:.1f}% b={b:.3f} f*={f_star:+.4f} "
          f"{'POSITIVE' if f_star > 0 else 'negative'}")
