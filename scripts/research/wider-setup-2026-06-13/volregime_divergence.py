"""(b) Is the divergence flag a standalone forward-return predictor on the
wide 38-symbol universe?

For divergence=='bullish' we expect price UP; 'bearish' expect price DOWN.
We compute mean SIGNED forward return where sign = +1 for bullish, -1 for
bearish (so a predictive flag => positive mean). null = baseline (sign by
nothing; we report raw mean fwd return as drift reference).

Chronological 50/50 split. Horizons {300,900,1800}s. We report n per flag,
mean signed fwd return (gross), WR (directionally correct), and a random
baseline: shuffle the flag->sign assignment 1000x and see what fraction of
shuffles beat the real mean.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(__file__))
from volregime_lib import load_by_symbol, fwd_price
import bisect

HORIZONS = [300, 900, 1800]
random.seed(42)


def build_events(by):
    """Flatten all snapshots with a usable fwd price per horizon, tagged with
    split (train/test by global chronological median ts)."""
    # global median ts for split
    all_ts = []
    for rows in by.values():
        all_ts.extend(r["ts"] for r in rows)
    all_ts.sort()
    split_ts = all_ts[len(all_ts) // 2]

    events = []  # (split, div, {h: signed_fwd_ret, raw_fwd_ret})
    for sym, rows in by.items():
        ts_list = [r["ts"] for r in rows]
        for i in range(len(rows)):
            div = rows[i]["div"]
            ep = rows[i]["price"]
            fwd = {}
            ok = False
            for h in HORIZONS:
                fp = fwd_price(rows, ts_list, i, h)
                if fp is None:
                    fwd[h] = None
                else:
                    fwd[h] = (fp - ep) / ep
                    ok = True
            if not ok:
                continue
            split = "train" if rows[i]["ts"] <= split_ts else "test"
            events.append((split, div, fwd))
    return events, split_ts


def signed(div, raw):
    if div == "bullish":
        return raw
    if div == "bearish":
        return -raw
    return raw  # null: raw drift reference


def summarize(events, split, h):
    rows = {"bullish": [], "bearish": [], None: []}
    for sp, div, fwd in events:
        if sp != split:
            continue
        raw = fwd.get(h)
        if raw is None:
            continue
        rows.setdefault(div, []).append(signed(div, raw))
    out = {}
    for k, v in rows.items():
        if not v:
            out[k] = (0, None, None)
            continue
        n = len(v)
        mean = sum(v) / n
        wr = sum(1 for x in v if x > 0) / n
        out[k] = (n, mean, wr)
    return out


def random_pvalue(events, split, h, flag, n_shuffles=1000):
    """For the given flag (bullish/bearish), test whether its signed mean fwd
    return beats random. We pool ALL raw fwd returns in this split and draw
    random samples of the same n, applying the flag's sign. Fraction of random
    draws whose mean >= real mean = p-value."""
    pool = []
    real = []
    sign = 1 if flag == "bullish" else -1
    for sp, div, fwd in events:
        if sp != split:
            continue
        raw = fwd.get(h)
        if raw is None:
            continue
        pool.append(raw)
        if div == flag:
            real.append(sign * raw)
    if not real or len(pool) < len(real):
        return None, None
    real_mean = sum(real) / len(real)
    k = len(real)
    beats = 0
    for _ in range(1000):
        samp = random.sample(pool, k)
        rm = sum(sign * x for x in samp) / k
        if rm >= real_mean:
            beats += 1
    return real_mean, beats / 1000.0


def main():
    by = load_by_symbol()
    events, split_ts = build_events(by)
    n_train = sum(1 for e in events if e[0] == "train")
    n_test = sum(1 for e in events if e[0] == "test")
    print(f"events: total={len(events)} train={n_train} test={n_test} split_ts={split_ts}")
    print()
    print("=== DIVERGENCE FORWARD-RETURN TABLE (signed: +bullish, -bearish, null=raw drift) ===")
    print(f"{'split':6} {'h(s)':5} {'flag':9} {'n':>7} {'mean_signed_ret':>16} {'WR':>7}")
    for split in ("train", "test"):
        for h in HORIZONS:
            s = summarize(events, split, h)
            for flag in ("bullish", "bearish", None):
                n, mean, wr = s.get(flag, (0, None, None))
                fl = "null" if flag is None else flag
                if mean is None:
                    print(f"{split:6} {h:<5} {fl:9} {n:>7} {'--':>16} {'--':>7}")
                else:
                    print(f"{split:6} {h:<5} {fl:9} {n:>7} {mean*100:>15.4f}% {wr*100:>6.2f}%")
        print()

    print("=== RANDOM BASELINE (TEST split): p = frac of 1000 random draws beating real signed mean ===")
    print(f"{'h(s)':5} {'flag':9} {'real_mean':>12} {'p_value':>9}  verdict")
    for h in HORIZONS:
        for flag in ("bullish", "bearish"):
            rm, p = random_pvalue(events, "test", h, flag)
            if rm is None:
                print(f"{h:<5} {flag:9} {'--':>12} {'--':>9}")
                continue
            verdict = "PASS(<0.05)" if p < 0.05 else "NO EDGE"
            print(f"{h:<5} {flag:9} {rm*100:>11.4f}% {p:>9.3f}  {verdict}")


if __name__ == "__main__":
    main()
