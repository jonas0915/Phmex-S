"""2e: 2D joint forward-return structure (imbalance x tape feature).
Shows RAW forward return (signed, bps) so we can see directionality, plus the
reversion-alpha view. Also splits long vs short side to expose asymmetry."""
import flowcap_lib as L

rbs = L.load()
samples = L.build_samples(rbs)
H = 900

def qedges(vals, nb):
    v=sorted(vals); return [v[int(i*len(v)/nb)] for i in range(nb)]+[v[-1]]

def bucket(x, edges):
    for i in range(len(edges)-1):
        if x<=edges[i+1]: return i
    return len(edges)-2

print("="*70)
print(f"2D JOINT: raw forward return (bps), rows=imbalance quintile, cols=buy_ratio quintile  H={H}")
print("="*70)
data=[(s["imb"], s["buy_ratio"], s[f"fwd_{H}"]) for s in samples
      if s.get("buy_ratio") is not None and s.get(f"fwd_{H}") is not None]
imb_e=qedges([d[0] for d in data],5)
br_e =qedges([d[1] for d in data],5)
print("imbalance quintile edges:", [round(x,3) for x in imb_e])
print("buy_ratio quintile edges:", [round(x,3) for x in br_e])
grid=[[[] for _ in range(5)] for _ in range(5)]
for imb,br,fr in data:
    grid[bucket(imb,imb_e)][bucket(br,br_e)].append(fr)
hdr="imb\\br  " + "".join(f"   BR{c}   " for c in range(5))
print(hdr)
for ri in range(4,-1,-1):  # high imbalance at top
    cells=[]
    for c in range(5):
        g=grid[ri][c]
        cells.append(f"{1e4*L.mean(g):+7.2f}" if g else "   --  ")
    print(f"  IMB{ri}  "+ "".join(f" {c} " for c in cells))
print("  (reversion = high IMB row should be NEGATIVE; reading raw fwd return)")

# Same with n counts
print("\n  cell counts:")
for ri in range(4,-1,-1):
    print(f"  IMB{ri}  "+"".join(f"{len(grid[ri][c]):>8}" for c in range(5)))

# ---- Long vs short asymmetry on the reversion ----
print("\n" + "="*70)
print("LONG vs SHORT asymmetry (reversion alpha, bps, gross)")
print("="*70)
for side,cond,desc in [("SHORT", lambda s: s["imb"]>0, "imb>0 -> short"),
                        ("LONG",  lambda s: s["imb"]<0, "imb<0 -> long")]:
    for thr in (0.0,0.3,0.5):
        vals=[]
        for s in samples:
            fr=s.get(f"fwd_{H}")
            if fr is None or not cond(s) or abs(s["imb"])<thr: continue
            vals.append((-1 if s["imb"]>0 else 1)*fr)
        m,sd,n=L.stats(vals); se=sd/(n**0.5) if n>1 else 0
        print(f"  {side:5} {desc:14} |imb|>={thr}:  n={n:6d}  {1e4*m:+7.3f} bps  t={m/se if se else 0:+5.2f}")
