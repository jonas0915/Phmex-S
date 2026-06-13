import json
from collections import Counter
for s in ["BTC_USDT_USDT","ETH_USDT_USDT","INJ_USDT_USDT","ARB_USDT_USDT"]:
    diffs=Counter(); n=0
    with open(f"logs/l2_ticks/{s}/2026-06-13.jsonl") as f:
        for line in f:
            try: r=json.loads(line)
            except: continue
            # gap between adjacent ask levels & bid levels
            for arr in (r.get("a",[]), r.get("b",[])):
                px=[lvl[0] for lvl in arr]
                for i in range(len(px)-1):
                    d=round(abs(px[i+1]-px[i]),8)
                    if d>0: diffs[d]+=1
            n+=1
            if n>=5000: break
    common=diffs.most_common(5)
    print(f"{s}: most common level gaps -> {common}")
