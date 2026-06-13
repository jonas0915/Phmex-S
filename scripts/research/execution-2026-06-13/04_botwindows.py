import pickle
results=pickle.load(open("scripts/research/execution-2026-06-13/results.pkl","rb"))
SYMS=["BTC_USDT_USDT","ETH_USDT_USDT","INJ_USDT_USDT","ARB_USDT_USDT"]
def short(s): return s.split("_")[0]
def pct(x): return f"{100*x:5.1f}%"

# Re-measure exactly at 20s and 25s by reusing ttf pools (placement='at', long+short)
for win,label in [(20,"ENTRY 20s window"),(25,"PATIENT-EXIT 25s window")]:
    print("="*70)
    print(f"{label}  (placement='at' the touch, avg long+short)")
    print("="*70)
    print("Sym  |  CONS  |  OPT")
    for s in SYMS:
        # count fills <= win seconds from the 300s ttf pool / total samples
        for bound in ("cons","opt"):
            pass
        out=[]
        for bound in ("cons","opt"):
            filled=0; total=0
            for side in ("long","short"):
                d=results[s][(side,"at",bound)]
                total+=d["total"]
                filled+=sum(1 for t in d["ttf"][300] if t<=win*1000)
            out.append(filled/total if total else 0)
        print(f"{short(s):4} |{pct(out[0]).rjust(7)} |{pct(out[1]).rjust(7)}")
    print()
