import pickle, statistics
results=pickle.load(open("scripts/research/execution-2026-06-13/results.pkl","rb"))
SYMS=["BTC_USDT_USDT","ETH_USDT_USDT","INJ_USDT_USDT","ARB_USDT_USDT"]
HOR=[10,30,60,300]
def short(s): return s.split("_")[0]

def pct(x): return f"{100*x:5.1f}%"

print("="*78)
print("FILL RATE vs HORIZON  --  placement='at' the touch (what the bot does)")
print("avg of long+short. CONS=trade-through (strict), OPT=at-or-through")
print("="*78)
hdr="Sym   bound |" + "".join(f"  {h}s ".rjust(8) for h in HOR)
print(hdr)
for s in SYMS:
    for bound in ("cons","opt"):
        rl=results[s][("long","at",bound)]["rates"]
        rs=results[s][("short","at",bound)]["rates"]
        avg={h:(rl[h]+rs[h])/2 for h in HOR}
        print(f"{short(s):4} {bound:5} |" + "".join(pct(avg[h]).rjust(8) for h in HOR))
    print("-"*78)

print()
print("="*78)
print("PLACEMENT COMPARISON  --  fill rate @ 60s, OPTIMISTIC bound (avg long+short)")
print("inside = 1 tick toward mid | at = touch | deep = 1 level behind touch")
print("="*78)
print("Sym  |  inside |    at   |   deep")
for s in SYMS:
    row=[]
    for place in ("inside","at","deep"):
        rl=results[s][("long",place,"opt")]["rates"][60]
        rs=results[s][("short",place,"opt")]["rates"][60]
        row.append((rl+rs)/2)
    print(f"{short(s):4} |" + "".join(pct(x).rjust(9) for x in row))

print()
print("="*78)
print("PLACEMENT COMPARISON  --  fill rate @ 60s, CONSERVATIVE bound (avg long+short)")
print("="*78)
print("Sym  |  inside |    at   |   deep")
for s in SYMS:
    row=[]
    for place in ("inside","at","deep"):
        rl=results[s][("long",place,"cons")]["rates"][60]
        rs=results[s][("short",place,"cons")]["rates"][60]
        row.append((rl+rs)/2)
    print(f"{short(s):4} |" + "".join(pct(x).rjust(9) for x in row))

print()
print("="*78)
print("TIME-TO-FILL (seconds) for orders that DID fill within 300s")
print("placement='at', OPTIMISTIC bound, long+short pooled")
print("="*78)
print("Sym  |  n_filled | median |   p90  |  mean")
for s in SYMS:
    pool=[]
    for side in ("long","short"):
        pool+=results[s][(side,"at","opt")]["ttf"][300]
    if not pool:
        print(f"{short(s):4} | no fills"); continue
    pool_s=sorted(x/1000 for x in pool)
    med=statistics.median(pool_s)
    p90=pool_s[int(0.9*(len(pool_s)-1))]
    mean=statistics.mean(pool_s)
    print(f"{short(s):4} | {len(pool_s):8} | {med:6.1f} | {p90:6.1f} | {mean:6.1f}")

print()
print("="*78)
print("TIME-TO-FILL (seconds), CONSERVATIVE bound, placement='at'")
print("="*78)
print("Sym  |  n_filled | median |   p90  |  mean")
for s in SYMS:
    pool=[]
    for side in ("long","short"):
        pool+=results[s][(side,"at","cons")]["ttf"][300]
    if not pool:
        print(f"{short(s):4} | no fills"); continue
    pool_s=sorted(x/1000 for x in pool)
    med=statistics.median(pool_s)
    p90=pool_s[int(0.9*(len(pool_s)-1))]
    mean=statistics.mean(pool_s)
    print(f"{short(s):4} | {len(pool_s):8} | {med:6.1f} | {p90:6.1f} | {mean:6.1f}")
