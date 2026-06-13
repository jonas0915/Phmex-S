#!/usr/bin/env python3
"""PART 1 — Independent re-derivation of book x tape absorption edge on flow_capture.jsonl.
Re-derived from scratch. No look-ahead. Read-only.

Claim: imbalance >= 0.3 AND buy_ratio >= 0.6 -> SHORT (revert down).
Sign convention confirmed: positive imbalance = bid-heavy.
"""
import json, math, random
from collections import defaultdict

PATH = 'logs/flow_capture.jsonl'
HORIZONS = [300, 900, 1800]  # seconds
random.seed(42)

# ---- Load: per-symbol time-ordered series of (ts, price, imbalance, buy_ratio) ----
series = defaultdict(list)
for line in open(PATH):
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

print(f"Loaded {sum(len(v) for v in series.values())} usable rows across {len(series)} symbols")

# ---- Build forward-return samples (no look-ahead): for each row, find price >= ts+H ----
# Each sample: dict with symbol, ts, imbalance, buy_ratio, and fwd_ret[H] (signed % move of price)
def build_samples(series, exclude_inj=False):
    samples = []
    for sym, rows in series.items():
        if exclude_inj and sym.startswith('INJ'):
            continue
        ts = [r[0] for r in rows]
        px = [r[1] for r in rows]
        n = len(rows)
        # pointer per horizon
        for i in range(n):
            t0 = ts[i]; p0 = px[i]
            rec = {'symbol': sym, 'ts': t0, 'imb': rows[i][2], 'br': rows[i][3]}
            ok = True
            for H in HORIZONS:
                target = t0 + H
                # find first j>i with ts[j] >= target, within a tolerance window (<= H*2)
                j = i + 1
                # linear scan forward; cadence ~75s so cheap enough but use bisect-ish
                while j < n and ts[j] < target:
                    j += 1
                if j < n and ts[j] <= target + H:  # require a real future point not too far
                    rec[f'fwd{H}'] = (px[j] - p0) / p0  # signed return in fraction
                else:
                    rec[f'fwd{H}'] = None
            samples.append(rec)
    return samples

samples = build_samples(series)
print(f"Built {len(samples)} samples")

def pearson(xs, ys):
    n = len(xs)
    if n < 3: return float('nan')
    mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs); syy = sum((y-my)**2 for y in ys)
    sxy = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    if sxx<=0 or syy<=0: return float('nan')
    return sxy/math.sqrt(sxx*syy)

# ============================================================
# 1. IMBALANCE-ALONE REVERSION BASELINE
# ============================================================
print("\n" + "="*70)
print("1. IMBALANCE-ALONE REVERSION BASELINE (corr of imbalance vs forward return)")
print("   Reversion => NEGATIVE corr (high bid imbalance -> price falls)")
print("="*70)
for H in HORIZONS:
    pairs = [(s['imb'], s[f'fwd{H}']) for s in samples if s[f'fwd{H}'] is not None]
    xs=[p[0] for p in pairs]; ys=[p[1]*10000 for p in pairs]  # ys in bps
    c = pearson(xs, ys)
    print(f"  H={H:5d}s  n={len(pairs):6d}  corr(imbalance, fwd_ret)={c:+.4f}")

# imbalance-alone signal: imb>=0.3 -> short. forward return of a SHORT = -fwd_ret
print("\n  Imbalance-alone SHORT signal (imb>=0.3 -> short). short_return = -fwd_ret (bps):")
for H in HORIZONS:
    sig = [s for s in samples if s['imb']>=0.3 and s[f'fwd{H}'] is not None]
    if not sig: continue
    short_rets = [-s[f'fwd{H}']*10000 for s in sig]
    mean = sum(short_rets)/len(short_rets)
    wr = sum(1 for r in short_rets if r>0)/len(short_rets)
    print(f"  H={H:5d}s  n={len(sig):6d}  mean_short_ret={mean:+.2f}bps  WR(short profitable)={wr*100:.1f}%")

# ============================================================
# 2. ABSORPTION RULE: imb>=0.3 & buy_ratio>=0.6 -> SHORT
# ============================================================
print("\n" + "="*70)
print("2. ABSORPTION RULE: imb>=0.3 AND buy_ratio>=0.6 -> SHORT")
print("   gross short return = -fwd_ret. (bps)")
print("="*70)

FEE_MAKER = 0.0002*2*10000  # 0.02% per side RT? spec says maker 0.02% / taker 0.12% RT
# Spec: "net at maker 0.02% and taker 0.12% RT" -> interpret as round-trip cost in those magnitudes
COST_MAKER_BPS = 2.0   # 0.02% RT = 2 bps
COST_TAKER_BPS = 12.0  # 0.12% RT = 12 bps

def stats_for(sel, H):
    rets = [-s[f'fwd{H}']*10000 for s in sel if s[f'fwd{H}'] is not None]
    if not rets: return None
    n=len(rets); mean=sum(rets)/n
    wr=sum(1 for r in rets if r>0)/n
    sd=math.sqrt(sum((r-mean)**2 for r in rets)/n) if n>1 else 0
    return n,mean,wr,sd,rets

for H in HORIZONS:
    absn = [s for s in samples if s['imb']>=0.3 and s['br']>=0.6]
    imbn = [s for s in samples if s['imb']>=0.3]
    a = stats_for(absn, H); b = stats_for(imbn, H)
    if not a: continue
    an,am,awr,asd,arets=a; bn,bm,bwr,bsd,brets=b
    se = asd/math.sqrt(an) if an>0 else float('nan')
    print(f"\n  H={H}s")
    print(f"    ABSORPTION (imb>=.3 & br>=.6): n={an:5d} gross_mean={am:+.2f}bps  WR={awr*100:.1f}%  SE={se:.2f}")
    print(f"    IMBALANCE-ALONE (imb>=.3)    : n={bn:5d} gross_mean={bm:+.2f}bps  WR={bwr*100:.1f}%")
    print(f"    UPLIFT (absorption - imb-alone) = {am-bm:+.2f}bps")
    print(f"    net @ maker(-{COST_MAKER_BPS}bps) = {am-COST_MAKER_BPS:+.2f}bps   net @ taker(-{COST_TAKER_BPS}bps) = {am-COST_TAKER_BPS:+.2f}bps")

# ============================================================
# 3. BOOTSTRAP CI on absorption gross mean (focus H=900)
# ============================================================
print("\n" + "="*70)
print("3. BOOTSTRAP 95% CI on absorption gross mean short return")
print("="*70)
for H in HORIZONS:
    sel = [-s[f'fwd{H}']*10000 for s in samples if s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
    if len(sel)<30:
        print(f"  H={H}s n={len(sel)} too few"); continue
    n=len(sel); B=2000
    means=[]
    for _ in range(B):
        m=sum(sel[random.randrange(n)] for _ in range(n))/n
        means.append(m)
    means.sort()
    lo=means[int(0.025*B)]; hi=means[int(0.975*B)]
    print(f"  H={H}s n={n}  mean={sum(sel)/n:+.2f}bps  95%CI=[{lo:+.2f}, {hi:+.2f}]bps  excludes_0={'YES' if lo>0 else 'no'}")

# ============================================================
# 4. CHRONOLOGICAL TRAIN/TEST SPLIT (OOS)
# ============================================================
print("\n" + "="*70)
print("4. CHRONOLOGICAL TRAIN/TEST (50/50 by ts) — OOS check")
print("="*70)
all_ts = sorted(s['ts'] for s in samples)
cut = all_ts[len(all_ts)//2]
for H in HORIZONS:
    tr = [-s[f'fwd{H}']*10000 for s in samples if s['ts']<cut and s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
    te = [-s[f'fwd{H}']*10000 for s in samples if s['ts']>=cut and s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
    tm = sum(tr)/len(tr) if tr else float('nan')
    em = sum(te)/len(te) if te else float('nan')
    print(f"  H={H}s  TRAIN n={len(tr):4d} mean={tm:+.2f}bps  |  TEST n={len(te):4d} mean={em:+.2f}bps  net_taker_test={em-COST_TAKER_BPS:+.2f}")

# ============================================================
# 5. BEATS-RANDOM: vs random subsets of same size
# ============================================================
print("\n" + "="*70)
print("5. BEATS-RANDOM (absorption mean vs distribution of random equal-n subsets)")
print("="*70)
for H in HORIZONS:
    universe = [-s[f'fwd{H}']*10000 for s in samples if s[f'fwd{H}'] is not None]
    sel = [-s[f'fwd{H}']*10000 for s in samples if s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
    if len(sel)<30: continue
    k=len(sel); obs=sum(sel)/k
    U=len(universe)
    rand_means=[]
    for _ in range(2000):
        m=sum(universe[random.randrange(U)] for _ in range(k))/k
        rand_means.append(m)
    pct = sum(1 for m in rand_means if m>=obs)/len(rand_means)
    base = sum(universe)/U
    print(f"  H={H}s  absorption_mean={obs:+.2f}  universe_mean={base:+.2f}  p(random>=obs)={pct:.4f}")

# ============================================================
# 6. INJ-CONCENTRATION CAVEAT: exclude INJ, re-run
# ============================================================
print("\n" + "="*70)
print("6. INJ CONCENTRATION — share of absorption signals from INJ, and excl-INJ re-run")
print("="*70)
H=900
sel_all = [s for s in samples if s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
from collections import Counter
symc = Counter(s['symbol'] for s in sel_all)
print(f"  Absorption signals (H={H}) by symbol (top 10):")
for sym,c in symc.most_common(10):
    print(f"    {sym:22s} {c:5d}  ({100*c/len(sel_all):.1f}%)")

samples_noinj = build_samples(series, exclude_inj=True)
for H in HORIZONS:
    sel = [-s[f'fwd{H}']*10000 for s in samples_noinj if s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
    imb = [-s[f'fwd{H}']*10000 for s in samples_noinj if s['imb']>=0.3 and s[f'fwd{H}'] is not None]
    if not sel: continue
    am=sum(sel)/len(sel); bm=sum(imb)/len(imb)
    wr=sum(1 for r in sel if r>0)/len(sel)
    print(f"  [EXCL INJ] H={H}s  abs n={len(sel):5d} mean={am:+.2f}bps WR={wr*100:.1f}%  imb-alone={bm:+.2f}  uplift={am-bm:+.2f}  net_taker={am-COST_TAKER_BPS:+.2f}")

# Also: INJ-only
print("\n  INJ-ONLY absorption:")
for H in HORIZONS:
    sel=[-s[f'fwd{H}']*10000 for s in samples if s['symbol'].startswith('INJ') and s['imb']>=0.3 and s['br']>=0.6 and s[f'fwd{H}'] is not None]
    if not sel: continue
    print(f"    H={H}s n={len(sel):5d} mean={sum(sel)/len(sel):+.2f}bps")
