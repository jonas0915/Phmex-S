import gzip, json, sys, bisect

def load(path):
    op = gzip.open if path.endswith('.gz') else open
    rows=[]
    with op(path,'rt') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
    return rows

path=sys.argv[1]
rows=load(path)
print("n", len(rows))
times=[r['ts'] for r in rows]
bid_depth=[sum(p*s for p,s in r['b']) for r in rows]  # top5 bid depth in quote terms
ask_depth=[sum(p*s for p,s in r['a']) for r in rows]

def crumble_events(depth, times, lookback_ms=10000, frac=0.6):
    n=len(depth)
    j=0
    events=0
    last_event_t=-1e18
    for i in range(n):
        t=times[i]
        while times[j] < t-lookback_ms:
            j+=1
        past = depth[j]
        if past<=0: continue
        if depth[i] < frac*past and (t-last_event_t)>lookback_ms:
            events+=1
            last_event_t=t
    return events

for frac in (0.6,0.5,0.4):
    be = crumble_events(bid_depth, times, 10000, frac)
    ae = crumble_events(ask_depth, times, 10000, frac)
    print(f"frac<{frac} 10s window: bid_crumble_events={be} ask_crumble_events={ae}")
