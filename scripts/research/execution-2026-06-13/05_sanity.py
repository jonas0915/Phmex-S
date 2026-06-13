import pickle, json
results=pickle.load(open("scripts/research/execution-2026-06-13/results.pkl","rb"))
# long vs short split at 60s OPT, placement 'at'
print("Long vs Short fill @60s OPT, placement='at':")
for s in results:
    rl=results[s][("long","at","opt")]["rates"][60]
    rs=results[s][("short","at","opt")]["rates"][60]
    print(f"  {s.split('_')[0]:4} long={100*rl:.1f}%  short={100*rs:.1f}%")

# ARB: check spread distribution (is spread usually > 1 tick? then 'at' bid rarely sees through-trade)
print("\nARB spread (in ticks) distribution from book (first 8000 snaps):")
tick=0.0001
from collections import Counter
c=Counter(); n=0
with open("logs/l2_ticks/ARB_USDT_USDT/2026-06-13.jsonl") as f:
    for line in f:
        r=json.loads(line)
        b=r.get("b");a=r.get("a")
        if not b or not a: continue
        sp=round((a[0][0]-b[0][0])/tick)
        c[sp]+=1; n+=1
        if n>=8000: break
for k in sorted(c)[:8]:
    print(f"  spread={k} ticks: {100*c[k]/n:.1f}%")

# BTC spread for comparison
print("\nBTC spread (in ticks):")
tick=0.1; c=Counter(); n=0
with open("logs/l2_ticks/BTC_USDT_USDT/2026-06-13.jsonl") as f:
    for line in f:
        r=json.loads(line); b=r.get("b");a=r.get("a")
        if not b or not a: continue
        sp=round((a[0][0]-b[0][0])/tick)
        c[sp]+=1;n+=1
        if n>=8000: break
for k in sorted(c)[:8]:
    print(f"  spread={k} ticks: {100*c[k]/n:.1f}%")
