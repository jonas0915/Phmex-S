import json, bisect, statistics, random

SYMS = ["BTC_USDT_USDT","ETH_USDT_USDT","INJ_USDT_USDT","ARB_USDT_USDT"]
TICK = {"BTC_USDT_USDT":0.1,"ETH_USDT_USDT":0.01,"INJ_USDT_USDT":0.001,"ARB_USDT_USDT":0.0001}
HORIZONS = [10,30,60,300]  # seconds
# Placement offsets in ticks relative to touch. For a BUY (long):
#   inside  = best_bid + 1 tick (more aggressive, closer to mid)
#   at      = best_bid (the touch)  -- what the bot does
#   deep    = best_bid - 1 tick (1 level behind touch)
PLACEMENTS = ["inside","at","deep"]

random.seed(42)
N_SAMPLES = 4000   # entry samples per symbol per side

def load_trades(path):
    # returns (ets[], pxs[], sides[]) sorted by et
    rows=[]
    with open(path) as f:
        for line in f:
            try: r=json.loads(line)
            except: continue
            et=r.get("et"); px=r.get("px"); side=r.get("side")
            if et is None or px is None or side is None: continue
            rows.append((et,px,side))
    rows.sort(key=lambda x:x[0])
    return [r[0] for r in rows],[r[1] for r in rows],[r[2] for r in rows]

def load_book(path):
    # returns ets[], bestbid[], bestask[] sorted by et
    rows=[]
    with open(path) as f:
        for line in f:
            try: r=json.loads(line)
            except: continue
            et=r.get("et"); b=r.get("b"); a=r.get("a")
            if et is None or not b or not a: continue
            bb=b[0][0]; ba=a[0][0]
            if bb is None or ba is None or bb<=0 or ba<=0: continue
            if ba<=bb: continue  # crossed/locked snapshot, skip
            rows.append((et,bb,ba))
    rows.sort(key=lambda x:x[0])
    return [r[0] for r in rows],[r[1] for r in rows],[r[2] for r in rows]

def fill_check(side, P, t0, horizon_ms, t_ets, t_pxs, t_sides, bound):
    """Return time-to-fill in ms if filled within horizon, else None.
    side='long' -> resting BUY at P, fills when a SELL aggressor prints <= P (opt) or < P (cons).
    side='short'-> resting SELL at P, fills when a BUY aggressor prints >= P (opt) or > P (cons).
    """
    end = t0 + horizon_ms
    i = bisect.bisect_left(t_ets, t0)
    n=len(t_ets)
    eps = 0.0
    while i < n:
        et=t_ets[i]
        if et > end: break
        px=t_pxs[i]; tside=t_sides[i]
        if side=="long":
            if tside=="sell":
                hit = (px < P) if bound=="cons" else (px <= P)
                if hit: return et - t0
        else:
            if tside=="buy":
                hit = (px > P) if bound=="cons" else (px >= P)
                if hit: return et - t0
        i+=1
    return None

results={}
for s in SYMS:
    tick=TICK[s]
    t_ets,t_pxs,t_sides = load_trades(f"logs/l2_ticks/{s}/trades-{'2026-06-13'}.jsonl")
    b_ets,b_bb,b_ba = load_book(f"logs/l2_ticks/{s}/2026-06-13.jsonl")
    if not b_ets or not t_ets:
        continue
    # valid sampling window: need room for max horizon AND trades to exist after
    lo = max(b_ets[0], t_ets[0])
    hi = min(b_ets[-1], t_ets[-1]) - max(HORIZONS)*1000
    if hi<=lo: 
        print(f"{s}: window too short"); continue
    samples=[random.uniform(lo,hi) for _ in range(N_SAMPLES)]
    # for each sample: pick a book snapshot at-or-before t0
    sym_res={}
    for side in ("long","short"):
        for place in PLACEMENTS:
            for bound in ("cons","opt"):
                key=(side,place,bound)
                fills={h:0 for h in HORIZONS}
                ttf={h:[] for h in HORIZONS}
                total=0
                for t0 in samples:
                    t0=int(t0)
                    bi=bisect.bisect_right(b_ets,t0)-1
                    if bi<0: continue
                    bb=b_bb[bi]; ba=b_ba[bi]
                    if side=="long":
                        base=bb
                        if place=="inside": P=base+tick
                        elif place=="at": P=base
                        else: P=base-tick
                        # don't post above the ask (would be taker / invalid maker)
                        if P>=ba: P=ba-tick
                    else:
                        base=ba
                        if place=="inside": P=base-tick
                        elif place=="at": P=base
                        else: P=base+tick
                        if P<=bb: P=bb+tick
                    P=round(P,8)
                    total+=1
                    # check largest horizon once, derive smaller via ttf
                    ttf_full=fill_check(side,P,t0,max(HORIZONS)*1000,t_ets,t_pxs,t_sides,bound)
                    if ttf_full is not None:
                        for h in HORIZONS:
                            if ttf_full <= h*1000:
                                fills[h]+=1
                                ttf[h].append(ttf_full)
                rates={h: (fills[h]/total if total else 0) for h in HORIZONS}
                sym_res[key]={"total":total,"rates":rates,"ttf":ttf}
    results[s]=sym_res
    print(f"done {s}: trades={len(t_ets)} book={len(b_ets)} samples_valid~{total}")

import pickle
with open("scripts/research/execution-2026-06-13/results.pkl","wb") as f:
    pickle.dump(results,f)
print("SAVED")
