import json
def span(path, key):
    lo=hi=None; n=0
    with open(path) as f:
        for line in f:
            try: r=json.loads(line)
            except: continue
            v=r.get(key)
            if v is None: continue
            n+=1
            if lo is None or v<lo: lo=v
            if hi is None or v>hi: hi=v
    return lo,hi,n

import datetime
def fmt(ms):
    if ms is None: return "None"
    return datetime.datetime.utcfromtimestamp(ms/1000).strftime("%Y-%m-%d %H:%M:%S UTC")

for s in ["BTC_USDT_USDT","ETH_USDT_USDT","INJ_USDT_USDT","ARB_USDT_USDT"]:
    bp=f"logs/l2_ticks/{s}/2026-06-13.jsonl"
    tp=f"logs/l2_ticks/{s}/trades-2026-06-13.jsonl"
    print(f"\n=== {s} ===")
    for label,p,k in [("book ts",bp,"ts"),("book et",bp,"et"),("trade ts",tp,"ts"),("trade et",tp,"et")]:
        lo,hi,n=span(p,k)
        dur=(hi-lo)/1000/3600 if lo else 0
        print(f"  {label}: {fmt(lo)} -> {fmt(hi)}  ({dur:.2f}h, n={n})")
