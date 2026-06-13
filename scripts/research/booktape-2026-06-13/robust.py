#!/usr/bin/env python3
"""
Robustness: walk-forward folds + per-symbol + shuffle control for the two
promising interaction signals (Sa absorption, Sd_active) vs S0 imb-alone.
Net at maker 2bps. Honest about tiny window.
"""
import pandas as pd, numpy as np

OUT = "scripts/research/booktape-2026-06-13/out"
SYMS = ["BTC", "ETH", "INJ", "ARB"]
MAKER = 0.0002
HZ = "fwd60"


def load(s):
    df = pd.read_csv(f"{OUT}/{s}_features.csv")
    df["sv_sign"] = np.sign(df.tape_sv)
    return df


def signals(df, thr):
    imb = df.imb1.values
    base = np.where(np.abs(imb) > thr, np.sign(imb), 0)
    sv = df.sv_sign.values
    cnt = df.tape_cnt.values
    q66 = np.quantile(cnt, 0.66)
    return {
        "S0": base,
        "Sa_absorb": np.where(sv != np.sign(imb), base, 0),
        "Sd_active": np.where(cnt > q66, base, 0),
    }


def netbps(direction, ret, fee=MAKER):
    m = direction != 0
    if m.sum() == 0:
        return 0.0, 0
    pnl = direction[m]*ret[m] - fee
    return pnl.mean()*1e4, int(m.sum())


def walkforward(df, nfolds=5, thr=0.6):
    """Expanding-window walk forward: train picks nothing (fixed thr), just OOS folds."""
    n = len(df)
    bounds = np.linspace(int(n*0.4), n, nfolds+1).astype(int)
    res = {"S0": [], "Sa_absorb": [], "Sd_active": []}
    for i in range(nfolds):
        lo, hi = bounds[i], bounds[i+1]
        seg = df.iloc[lo:hi]
        sg = signals(seg, thr)
        for k in res:
            b, ntr = netbps(sg[k], seg[HZ].values)
            res[k].append((b, ntr))
    return res


def main():
    print("="*78)
    print("WALK-FORWARD (5 OOS folds over last 60% of each symbol), thr=0.6, maker 2bps")
    print("net bps/trade per fold; positive = profitable after fees")
    print("="*78)
    pooled = {"S0": [], "Sa_absorb": [], "Sd_active": []}
    for s in SYMS:
        df = load(s)
        res = walkforward(df)
        print(f"\n[{s}]")
        for k in ["S0", "Sa_absorb", "Sd_active"]:
            vals = [r[0] for r in res[k]]
            ntr = [r[1] for r in res[k]]
            pos = sum(1 for v in vals if v > 0)
            print(f"  {k:10s} folds={['%+.2f'%v for v in vals]}  "
                  f"({pos}/{len(vals)} folds +)  trades/fold={ntr}")
            pooled[k].extend(vals)
    print("\n--- POOLED across all symbols & folds ---")
    for k in ["S0", "Sa_absorb", "Sd_active"]:
        v = np.array(pooled[k])
        pos = (v > 0).mean()
        # t-test mean>0
        from scipy import stats
        t, p = stats.ttest_1samp(v, 0) if len(v) > 1 else (0, 1)
        print(f"  {k:10s} mean={v.mean():+.3f} bps/trade  median={np.median(v):+.3f}  "
              f"%folds+={pos:.0%}  t={t:+.2f} p={p:.3f}  (n_folds={len(v)})")

    # Shuffle control: shuffle the gate (tape) relative to book, keep marginals.
    print("\n" + "="*78)
    print("SHUFFLE CONTROL: randomize tape gate vs book (1000x), is Sa/Sd_active real?")
    print("Compares true net-bps to null where tape labels are permuted.")
    print("="*78)
    rng = np.random.default_rng(42)
    for s in SYMS:
        df = load(s)
        thr = 0.6
        imb = df.imb1.values
        base = np.where(np.abs(imb) > thr, np.sign(imb), 0)
        ret = df[HZ].values
        sv = df.sv_sign.values
        cnt = df.tape_cnt.values
        q66 = np.quantile(cnt, 0.66)
        # true
        true_a = netbps(np.where(sv != np.sign(imb), base, 0), ret)[0]
        true_d = netbps(np.where(cnt > q66, base, 0), ret)[0]
        null_a = []; null_d = []
        for _ in range(1000):
            svp = rng.permutation(sv)
            cntp = rng.permutation(cnt)
            null_a.append(netbps(np.where(svp != np.sign(imb), base, 0), ret)[0])
            q = np.quantile(cntp, 0.66)
            null_d.append(netbps(np.where(cntp > q, base, 0), ret)[0])
        null_a = np.array(null_a); null_d = np.array(null_d)
        pa = (null_a >= true_a).mean()
        pd_ = (null_d >= true_d).mean()
        print(f"[{s}] Sa true={true_a:+.3f} null mean={null_a.mean():+.3f} p={pa:.3f} | "
              f"Sd_active true={true_d:+.3f} null mean={null_d.mean():+.3f} p={pd_:.3f}")


if __name__ == "__main__":
    main()
