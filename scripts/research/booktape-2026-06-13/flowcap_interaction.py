"""Book x Tape interaction tests (2a-2e). All gross bps unless stated.

Reversion convention: signal direction = -sign(imb). reversion alpha =
mean( -sign(imb) * fwd_ret ). Positive => reversion edge.
"""
import flowcap_lib as L

rbs = L.load()
samples = L.build_samples(rbs)
H = 900  # primary horizon (also report 300)

def rev(s, H):
    fr=s.get(f"fwd_{H}")
    if fr is None or s["imb"]==0: return None
    return (-1 if s["imb"]>0 else 1)*fr

def report(name, vals):
    m,sd,n = L.stats(vals)
    se = sd/(n**0.5) if n>1 else float('nan')
    t = m/se if se and se==se and se!=0 else float('nan')
    print(f"  {name:<42} n={n:6d}  {1e4*m:+7.3f} bps  t={t:+5.2f}")

print("="*70)
print(f"INTERACTION TESTS  (reversion alpha in bps, gross, H={H}s)")
print("="*70)

# ---- 2a CONFIRMATION: tape agrees with reversion direction ----
# Reversion of positive imbalance -> short -> we want price to FALL.
# Tape "agrees" with the DOWN move if sellers dominate: buy_ratio<0.5 / cvd_slope<0.
# For negative imbalance -> long -> want price UP -> tape agrees if buy_ratio>0.5.
print("\n[2a] CONFIRMATION: tape agrees with reversion direction")
print("     (signal=short when imb>0; agree = tape points DOWN i.e. buy_ratio<0.5)")
for tape_key, agree_fn, label in [
    ("buy_ratio", lambda s: (s["buy_ratio"]<0.5) if s["imb"]>0 else (s["buy_ratio"]>0.5), "buy_ratio"),
    ("cvd_slope", lambda s: (s["cvd_slope"]<0) if s["imb"]>0 else (s["cvd_slope"]>0), "cvd_slope"),
]:
    agree=[]; disagree=[]
    for s in samples:
        v=rev(s,H)
        if v is None or s.get(tape_key) is None: continue
        if agree_fn(s): agree.append(v)
        else: disagree.append(v)
    print(f"   {label}:")
    report(f"     AGREE (book+tape aligned)", agree)
    report(f"     DISAGREE", disagree)

# Same but restricted to strong imbalance
print("\n[2a-strong] CONFIRMATION restricted to |imb|>=0.3")
for tape_key, agree_fn, label in [
    ("buy_ratio", lambda s: (s["buy_ratio"]<0.5) if s["imb"]>0 else (s["buy_ratio"]>0.5), "buy_ratio"),
    ("cvd_slope", lambda s: (s["cvd_slope"]<0) if s["imb"]>0 else (s["cvd_slope"]>0), "cvd_slope"),
]:
    agree=[]; disagree=[]
    for s in samples:
        if abs(s["imb"])<0.3: continue
        v=rev(s,H)
        if v is None or s.get(tape_key) is None: continue
        if agree_fn(s): agree.append(v)
        else: disagree.append(v)
    print(f"   {label}:")
    report(f"     AGREE", agree)
    report(f"     DISAGREE", disagree)

# ---- 2b ABSORPTION: large imbalance + OPPOSING flow ----
# Bid-heavy book (imb>0) but heavy SELLING (buy_ratio<0.5) = absorption of sells
#   into bids -> classic the wall holds, but reversion says price falls anyway.
# The prompt's absorption proxy: large imbalance + opposing flow. Opposing =
# flow pushing AGAINST the book imbalance (buy_ratio<0.5 while imb>0).
# Note: for imb>0, "opposing flow" (selling) == "agrees with reversion(short)".
# So 2b w/ opposing is identical to 2a-agree. Define absorption distinctly:
# flow SAME direction as book (buy_ratio>0.5 & imb>0): buyers AND bid wall -> does
# reversion still happen (price falls despite buying)? vs opposing.
print("\n[2b] ABSORPTION: strong imbalance, flow SAME dir as book vs OPPOSING")
print("     SAME = buyers hitting a bid-heavy book (imb>0 & buy_ratio>0.5)")
same=[]; opp=[]
for s in samples:
    if abs(s["imb"])<0.3 or s.get("buy_ratio") is None: continue
    v=rev(s,H)
    if v is None: continue
    book_up = s["imb"]>0
    flow_up = s["buy_ratio"]>0.5
    if book_up==flow_up: same.append(v)
    else: opp.append(v)
report("SAME (flow w/ book, vs reversion)", same)
report("OPPOSING (flow vs book = w/ reversion)", opp)

# ---- 2c divergence flag x imbalance ----
print("\n[2c] divergence flag x imbalance")
for dv in (None,"bullish","bearish"):
    vals=[rev(s,H) for s in samples if s["divergence"]==dv and rev(s,H) is not None]
    report(f"divergence={dv}", vals)
print("   strong imb |imb|>=0.3, by divergence:")
for dv in (None,"bullish","bearish"):
    vals=[rev(s,H) for s in samples if s["divergence"]==dv and abs(s["imb"])>=0.3 and rev(s,H) is not None]
    report(f"   div={dv} & |imb|>=0.3", vals)

# ---- 2d trade_count regime ----
print("\n[2d] trade_count regime (does reversion need high/low activity?)")
tcs=sorted(s["trade_count"] for s in samples if s.get("trade_count") is not None)
q33=tcs[len(tcs)//3]; q66=tcs[2*len(tcs)//3]
print(f"     tertiles: low<={q33}, mid<={q66}, high>")
for lab,lo,hi in [("LOW",-1,q33),("MID",q33,q66),("HIGH",q66,10**9)]:
    vals=[rev(s,H) for s in samples if s.get("trade_count") is not None and lo<s["trade_count"]<=hi and rev(s,H) is not None]
    report(f"{lab} activity", vals)
print("   strong imb |imb|>=0.3 by activity:")
for lab,lo,hi in [("LOW",-1,q33),("MID",q33,q66),("HIGH",q66,10**9)]:
    vals=[rev(s,H) for s in samples if s.get("trade_count") is not None and lo<s["trade_count"]<=hi and abs(s["imb"])>=0.3 and rev(s,H) is not None]
    report(f"   {lab} & |imb|>=0.3", vals)
