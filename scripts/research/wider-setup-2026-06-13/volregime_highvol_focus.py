"""Focused test on the one cell that showed a TRAIN-consistent gross edge:
HIGH-VOL REVERSION. Question: is the gross edge real (beats random direction),
and does it survive fees at the maker rate (0.0663% RT)?

Also report triggers/day and run the random baseline ON THIS SPECIFIC cell
(not the n=2 'best' artifact from the grid script).
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))
from volregime_lib import (load_by_symbol, realized_vol, ret_prior,
                           fwd_path, simulate_exit, FEE_LOW, FEE_HIGH)

random.seed(7)
VOL_WINDOW = 900
PRIOR_WINDOW = 900
MAX_HORIZON = 1800
TEST_DAYS = 33.5 / 2


def build():
    by = load_by_symbol()
    all_ts = []
    for rows in by.values():
        all_ts.extend(r["ts"] for r in rows)
    all_ts.sort()
    split_ts = all_ts[len(all_ts) // 2]
    cands = []
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
                "rv": rv, "rp": rp, "ep": rows[i]["price"], "path": path,
            })
    return cands, split_ts


def q(vals, qq):
    s = sorted(vals); return s[min(len(s)-1, int(qq*len(s)))]


def rev_ret(c, tp, sl):
    direction = -1 if c["rp"] > 0 else +1  # fade
    return simulate_exit(c["ep"], c["path"], direction, tp, sl)


def main():
    cands, split_ts = build()
    train = [c for c in cands if c["split"] == "train"]
    test = [c for c in cands if c["split"] == "test"]
    rv_t2 = q([c["rv"] for c in train], 2/3)  # high-vol threshold (train)
    abs_rp_95 = q([abs(c["rp"]) for c in train], 0.95)
    print(f"high-vol thresh (train rv 67th pctile)={rv_t2:.5f}  trigger |rp|>= {abs_rp_95*100:.3f}%")

    # tune tp/sl on TRAIN high-vol reversion by gross (fee-agnostic edge),
    # then report TEST at both fee tiers.
    TPS = [0.004, 0.006, 0.010]; SLS = [0.005, 0.008]
    tr = [c for c in train if c["rv"] >= rv_t2 and abs(c["rp"]) >= abs_rp_95]
    te = [c for c in test if c["rv"] >= rv_t2 and abs(c["rp"]) >= abs_rp_95]
    print(f"high-vol reversion candidates: train={len(tr)} test={len(te)}")
    print()
    print(f"{'tp/sl':9} {'tr_gross%':>10} {'te_gross%':>10} {'te_net_lo%':>11} {'te_net_hi%':>11} {'te_WR':>7} {'te_n':>6} {'rand_p':>7}")

    pool_paths = te  # for random direction shuffle
    for tp in TPS:
        for sl in SLS:
            tg = sum(rev_ret(c, tp, sl) for c in tr)/len(tr)
            te_rets = [rev_ret(c, tp, sl) for c in te]
            n = len(te_rets)
            teg = sum(te_rets)/n
            net_lo = sum(r-FEE_LOW for r in te_rets)/n
            net_hi = sum(r-FEE_HIGH for r in te_rets)/n
            wr = sum(1 for r in te_rets if r>0)/n
            # random p on TEST gross (shuffle direction)
            real = teg
            beats = 0
            for _ in range(1000):
                tot = sum(simulate_exit(c["ep"], c["path"], random.choice([1,-1]), tp, sl) for c in te)
                if tot/n >= real: beats += 1
            p = beats/1000.0
            print(f"{tp*100:.1f}/{sl*100:.1f}    {tg*100:>9.4f}% {teg*100:>9.4f}% {net_lo*100:>10.4f}% {net_hi*100:>10.4f}% {wr*100:>6.2f}% {n:>6} {p:>7.3f}")

    print()
    print(f"triggers/day on TEST (high-vol reversion universe): {len(te)/TEST_DAYS:.1f}")
    print("Note: net_lo = after 0.0663% RT (maker), net_hi = after 0.12% RT (taker).")


if __name__ == "__main__":
    main()
