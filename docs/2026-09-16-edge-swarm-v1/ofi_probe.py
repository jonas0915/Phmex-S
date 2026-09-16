import gzip, json, sys

def load(path):
    op = gzip.open if path.endswith('.gz') else open
    rows=[]
    with op(path, 'rt') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                rows.append(json.loads(line))
            except: pass
    return rows

def ofi_series(rows):
    # L1 OFI a la Cont/Kukanov/Stoikov: compare consecutive snapshots' best bid/ask price+size
    out=[]
    prev=None
    for r in rows:
        if not r.get('b') or not r.get('a'): continue
        bp, bs = r['b'][0]
        ap, aszv = r['a'][0]
        if prev is not None:
            pbp, pbs, pap, pas, pts = prev
            # bid side contribution
            if bp > pbp: e_b = bs
            elif bp == pbp: e_b = bs - pbs
            else: e_b = -pbs
            # ask side contribution
            if ap > pap: e_a = -pas
            elif ap == pap: e_a = aszv - pas
            else: e_a = aszv
            ofi = e_b - e_a
            out.append((r['ts'], ofi))
        prev=(bp,bs,ap,aszv,r['ts'])
    return out

path = sys.argv[1]
rows = load(path)
print("n_snapshots", len(rows))
if rows:
    print("ts_span_sec", (rows[-1]['ts']-rows[0]['ts'])/1000)
series = ofi_series(rows)
print("n_ofi_points", len(series))

# rolling 60s sum of OFI, detect sign-flip "rollover" events:
# sustained negative (rolling sum < -thresh) for >=T ms, then flips to rolling sum > +thresh within window
import statistics
vals=[v for _,v in series]
if vals:
    print("ofi abs mean", sum(abs(v) for v in vals)/len(vals))
    print("ofi stdev", statistics.pstdev(vals))

# rolling window sum via simple loop (time-based 30s window)
window_ms = 30000
thresh = None
if vals:
    thresh = statistics.pstdev(vals) * 3 * (window_ms/1000/2)**0.5  # rough scale guess, will calibrate below instead

# better: compute rolling sum directly
times=[t for t,_ in series]
n=len(series)
roll=[]
import bisect
# build prefix sums with timestamps, O(n) two-pointer since time increasing
s=0.0
j=0
cum=[0.0]*(n+1)
for i,(t,v) in enumerate(series):
    cum[i+1]=cum[i]+v
roll_sum=[]
j=0
for i in range(n):
    t_i = times[i]
    while times[j] < t_i - window_ms:
        j+=1
    roll_sum.append(cum[i+1]-cum[j])

rs_abs_mean = sum(abs(x) for x in roll_sum)/len(roll_sum)
rs_stdev = statistics.pstdev(roll_sum)
print("rolling30s abs mean", rs_abs_mean, "stdev", rs_stdev)

# define rollover event: rolling sum crosses from < -k*stdev to > +k*stdev within 90s, k=1.5
k=1.5
neg_thresh = -k*rs_stdev
pos_thresh = k*rs_stdev
events=0
state='neutral'
last_neg_time=None
for i,(t,v) in enumerate(series):
    rs = roll_sum[i]
    if rs < neg_thresh:
        state='neg'
        last_neg_time=t
    elif rs > pos_thresh and state=='neg' and last_neg_time is not None and (t-last_neg_time) < 90000:
        events+=1
        state='neutral'
        last_neg_time=None
print("rollover_events(neg->pos, k=1.5, 90s)", events)
