"""(a) Does volatility regime change whether REVERSION or MOMENTUM works?

For each snapshot compute:
  - realized vol (trailing 900s stdev of snapshot returns) -> tercile bucket
    (thresholds set on TRAIN only, applied to TEST)
  - ret_prior (trailing 900s return) -> trigger when |ret_prior| in top 5%
    (95th pctile of |ret_prior| set on TRAIN only)

Two strategies on triggered snapshots:
  REVERSION: fade the move. If ret_prior>0 -> SHORT; if <0 -> LONG.
  MOMENTUM:  follow the move. If ret_prior>0 -> LONG; if <0 -> SHORT.

Exit via TP/SL over forward path (max_horizon=1800s).
Grid: TP in {0.4,0.6,1.0}%, SL in {0.5,0.8}%.

Report mean GROSS net/trade and NET after fees (0.0663% and 0.12% RT) per
vol regime x strategy, TRAIN vs TEST, with n. Random baseline on the best
TEST config.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))
from volregime_lib import (load_by_symbol, realized_vol, ret_prior,
                           fwd_path, simulate_exit, FEE_LOW, FEE_HIGH)

random.seed(42)
VOL_WINDOW = 900
PRIOR_WINDOW = 900
MAX_HORIZON = 1800
TPS = [0.004, 0.006, 0.010]
SLS = [0.005, 0.008]


def build():
    by = load_by_symbol()
    all_ts = []
    for rows in by.values():
        all_ts.extend(r["ts"] for r in rows)
    all_ts.sort()
    split_ts = all_ts[len(all_ts) // 2]

    # First pass: collect candidate snapshots with vol + ret_prior + fwd path.
    cands = []  # dict per triggerable snapshot
    for sym, rows in by.items():
        ts_list = [r["ts"] for r in rows]
        for i in range(len(rows)):
            rv = realized_vol(rows, ts_list, i, VOL_WINDOW)
            rp = ret_prior(rows, ts_list, i, PRIOR_WINDOW)
            if rv is None or rp is None:
                continue
            path = fwd_path(rows, ts_list, i, MAX_HORIZON)
            if not path:
                continue
            cands.append({
                "split": "train" if rows[i]["ts"] <= split_ts else "test",
                "rv": rv,
                "rp": rp,
                "ep": rows[i]["price"],
                "path": path,
            })
    return cands, split_ts


def quantiles(vals, qs):
    s = sorted(vals)
    out = []
    for q in qs:
        idx = min(len(s) - 1, int(q * len(s)))
        out.append(s[idx])
    return out


def main():
    cands, split_ts = build()
    train = [c for c in cands if c["split"] == "train"]
    test = [c for c in cands if c["split"] == "test"]
    print(f"candidates: total={len(cands)} train={len(train)} test={len(test)} split_ts={split_ts}")

    # TRAIN-only thresholds
    rv_t1, rv_t2 = quantiles([c["rv"] for c in train], [1/3, 2/3])
    abs_rp_95 = quantiles([abs(c["rp"]) for c in train], [0.95])[0]
    print(f"TRAIN vol terciles: low<{rv_t1:.5f}<=med<{rv_t2:.5f}<=high")
    print(f"TRAIN |ret_prior| 95th pctile trigger: {abs_rp_95*100:.4f}%")
    print()

    def regime(rv):
        if rv < rv_t1:
            return "low"
        if rv < rv_t2:
            return "med"
        return "high"

    def trade_ret(c, strat, tp, sl):
        rp = c["rp"]
        if rp > 0:
            direction = -1 if strat == "rev" else +1
        else:
            direction = +1 if strat == "rev" else -1
        return simulate_exit(c["ep"], c["path"], direction, tp, sl)

    # Pick best config per (regime, strat) on TRAIN by net@FEE_HIGH, then report TEST.
    print("=== VOL-REGIME x DIRECTION EDGE TABLE ===")
    print("(net/trade in %, after FEE_HIGH 0.12% RT; trigger=|ret_prior|>=95th)")
    header = f"{'regime':6} {'strat':4} {'tp/sl':9} {'split':5} {'n':>6} {'gross%':>9} {'net_lo%':>9} {'net_hi%':>9} {'WR':>7}"
    print(header)

    best = {}
    for reg in ("low", "med", "high"):
        for strat in ("rev", "mom"):
            tr = [c for c in train if abs(c["rp"]) >= abs_rp_95 and regime(c["rv"]) == reg]
            if not tr:
                continue
            # grid search on train
            best_cfg = None
            for tp in TPS:
                for sl in SLS:
                    rets = [trade_ret(c, strat, tp, sl) for c in tr]
                    net = sum(r - FEE_HIGH for r in rets) / len(rets)
                    if best_cfg is None or net > best_cfg[0]:
                        best_cfg = (net, tp, sl)
            best[(reg, strat)] = best_cfg[1:]

    for reg in ("low", "med", "high"):
        for strat in ("rev", "mom"):
            if (reg, strat) not in best:
                continue
            tp, sl = best[(reg, strat)]
            for split, data in (("train", train), ("test", test)):
                sub = [c for c in data if abs(c["rp"]) >= abs_rp_95 and regime(c["rv"]) == reg]
                if not sub:
                    print(f"{reg:6} {strat:4} {tp*100:.1f}/{sl*100:.1f}    {split:5} {0:>6}")
                    continue
                rets = [trade_ret(c, strat, tp, sl) for c in sub]
                n = len(rets)
                gross = sum(rets) / n
                net_lo = sum(r - FEE_LOW for r in rets) / n
                net_hi = sum(r - FEE_HIGH for r in rets) / n
                wr = sum(1 for r in rets if r > 0) / n
                cfg = f"{tp*100:.1f}/{sl*100:.1f}"
                print(f"{reg:6} {strat:4} {cfg:9} {split:5} {n:>6} {gross*100:>8.4f}% {net_lo*100:>8.4f}% {net_hi*100:>8.4f}% {wr*100:>6.2f}%")
        print()

    # Random baseline: for the best TEST net_hi config, shuffle direction 1000x.
    print("=== RANDOM BASELINE on best-TEST config (shuffle long/short direction) ===")
    # find best test config by net_hi
    best_test = None
    for reg in ("low", "med", "high"):
        for strat in ("rev", "mom"):
            if (reg, strat) not in best:
                continue
            tp, sl = best[(reg, strat)]
            sub = [c for c in test if abs(c["rp"]) >= abs_rp_95 and regime(c["rv"]) == reg]
            if not sub:
                continue
            rets = [trade_ret(c, strat, tp, sl) for c in sub]
            net = sum(r - FEE_HIGH for r in rets) / len(rets)
            if best_test is None or net > best_test[0]:
                best_test = (net, reg, strat, tp, sl, sub)
    if best_test:
        net, reg, strat, tp, sl, sub = best_test
        span_days = 33.5
        n = len(sub)
        # triggers/day across full test span (~16.8 days = half of 33.5)
        test_days = span_days / 2
        print(f"best TEST config: regime={reg} strat={strat} tp/sl={tp*100:.1f}/{sl*100:.1f}")
        print(f"  TEST n={n}  net_hi/trade={net*100:.4f}%  triggers/day~={n/test_days:.1f}")
        wr = sum(1 for c in sub if trade_ret(c, strat, tp, sl) > 0) / n
        print(f"  WR={wr*100:.2f}%")
        real_net = net
        beats = 0
        for _ in range(1000):
            tot = 0.0
            for c in sub:
                d = random.choice([+1, -1])
                tot += simulate_exit(c["ep"], c["path"], d, tp, sl) - FEE_HIGH
            if tot / n >= real_net:
                beats += 1
        p = beats / 1000.0
        verdict = "PASS(<0.05)" if p < 0.05 and real_net > 0 else "NO EDGE"
        print(f"  random p-value={p:.3f}  net>0? {real_net>0}  => {verdict}")


if __name__ == "__main__":
    main()
