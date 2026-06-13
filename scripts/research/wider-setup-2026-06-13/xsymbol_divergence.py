#!/usr/bin/env python3
"""
Cross-symbol divergence / lead-lag OOS edge search.

Hypothesis: When an alt diverges from an anchor (BTC or ETH) over a short window W,
does the alt revert toward / catch up to the anchor?

divergence = alt_ret(W) - beta * anchor_ret(W)
  negative divergence => alt UNDERperformed anchor => reversion bet = LONG alt (catch-up)
  positive divergence => alt OVERperformed anchor => reversion bet = SHORT alt

Strict no-look-ahead:
 - anchor price aligned at-or-before each timestamp (never future)
 - returns over trailing window W (price now vs price at-or-before now-W)
 - forward exit walks forward only
 - chronological 50/50 split, params chosen on TRAIN, reported on TEST
 - refractory = W per symbol
 - random baseline: 1000 random-entry draws -> p-value

Usage: python3 xsymbol_divergence.py <anchor_symbol_short>   (e.g. ETH or BTC)
"""
import json, sys, bisect, random, statistics
from collections import defaultdict

DATA = "logs/flow_capture.jsonl"
ANCHOR = sys.argv[1] if len(sys.argv) > 1 else "ETH"
ANCHOR_SYM = f"{ANCHOR}/USDT:USDT"

# fee scenarios (round-trip), as fraction of notional
FEES = {"gross": 0.0, "maker_0.0663pct": 0.000663, "taker_0.12pct": 0.0012}

ALIGN_TOL = 150          # seconds tolerance for at-or-before alignment
WINDOWS = [300, 600, 900]
MAX_HOLDS = [300, 900, 1800]
TPS = [0.004, 0.006, 0.010]
SLS = [0.005, 0.008]
PCTS = [90, 95]
MIN_TRIGGERS_TEST = 20   # need at least this many TEST triggers to trust a config

random.seed(42)

# ---------- load ----------
series = defaultdict(list)   # symbol -> list of (ts, price), will sort
with open(DATA) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        p = d.get("price")
        if p is None or p <= 0:
            continue
        series[d["symbol"]].append((d["ts"], p))

for s in series:
    series[s].sort(key=lambda x: x[0])

if ANCHOR_SYM not in series:
    print("anchor not found"); sys.exit(1)

anchor_ts = [t for t, _ in series[ANCHOR_SYM]]
anchor_px = [p for _, p in series[ANCHOR_SYM]]


def at_or_before(ts_list, px_list, target, tol):
    """Return price at-or-before target within tol seconds, else None. NEVER future."""
    i = bisect.bisect_right(ts_list, target) - 1
    if i < 0:
        return None
    if target - ts_list[i] > tol:
        return None
    return px_list[i]


def anchor_ret(t_now, W):
    """Anchor return over [t_now - W, t_now] using at-or-before alignment for BOTH ends."""
    p_now = at_or_before(anchor_ts, anchor_px, t_now, ALIGN_TOL)
    p_past = at_or_before(anchor_ts, anchor_px, t_now - W, ALIGN_TOL)
    if p_now is None or p_past is None:
        return None
    return p_now / p_past - 1.0


# determine global chronological split point (median ts across all alt rows we consider)
all_alt_ts = []
ALTS = [s for s in series if s not in (ANCHOR_SYM,) and len(series[s]) >= 200]
for s in ALTS:
    all_alt_ts.extend(t for t, _ in series[s])
all_alt_ts.sort()
SPLIT_TS = all_alt_ts[len(all_alt_ts) // 2]
import datetime as _dt
def fmt(t): return _dt.datetime.fromtimestamp(t, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
print(f"# anchor={ANCHOR_SYM} alts={len(ALTS)} split={fmt(SPLIT_TS)} "
      f"data_span={fmt(all_alt_ts[0])}..{fmt(all_alt_ts[-1])}")


def build_signals(sym, W, beta):
    """For each alt snapshot, compute divergence vs anchor over W. Returns list of
    (ts, price, divergence). Only where both alt-trailing and anchor-trailing returns exist."""
    s = series[sym]
    ts = [t for t, _ in s]; px = [p for _, p in s]
    out = []
    for i in range(len(s)):
        t_now = ts[i]; p_now = px[i]
        # alt trailing return over W
        p_past = at_or_before(ts, px, t_now - W, ALIGN_TOL)
        if p_past is None:
            continue
        ar = p_now / p_past - 1.0
        br = anchor_ret(t_now, W)
        if br is None:
            continue
        div = ar - beta * br
        out.append((t_now, p_now, div))
    return out


def forward_exit(sym, entry_idx_ts, entry_price, side, max_hold, tp, sl):
    """Walk forward from entry ts. side=+1 long, -1 short. Return realized gross return
    (as signed fraction of price, positive=profit)."""
    s = series[sym]
    ts = [t for t, _ in s]; px = [p for _, p in s]
    i = bisect.bisect_right(ts, entry_idx_ts)  # strictly after entry snapshot
    end = entry_idx_ts + max_hold
    last_p = entry_price
    while i < len(s) and ts[i] <= end:
        p = px[i]; last_p = p
        ret = side * (p / entry_price - 1.0)
        if ret >= tp:
            return tp
        if ret <= -sl:
            return -sl
        i += 1
    # exit at last observed price within window
    return side * (last_p / entry_price - 1.0)


def run_config(sym_signals, W, pct, direction, max_hold, tp, sl, period):
    """direction: 'reversion' or 'momentum'. period: 'train'/'test'/'all'.
    Returns list of gross returns (per trade)."""
    rets = []
    contrib = defaultdict(list)
    for sym, sigs in sym_signals.items():
        # threshold from TRAIN portion only
        train_divs = [abs(d) for (t, p, d) in sigs if t < SPLIT_TS]
        if len(train_divs) < 30:
            continue
        train_divs.sort()
        thr = train_divs[int(len(train_divs) * pct / 100.0)]
        if thr <= 0:
            continue
        last_entry = -1e18
        for (t, p, d) in sigs:
            if period == "train" and t >= SPLIT_TS:
                continue
            if period == "test" and t < SPLIT_TS:
                continue
            if abs(d) < thr:
                continue
            if t - last_entry < W:   # refractory
                continue
            # reversion: bet alt reverts toward anchor.
            # negative div (alt underperformed) -> LONG (side +1). positive -> SHORT (-1)
            if direction == "reversion":
                side = -1 if d > 0 else +1
            else:  # momentum
                side = +1 if d > 0 else -1
            r = forward_exit(sym, t, p, side, max_hold, tp, sl)
            rets.append(r)
            contrib[sym].append(r)
            last_entry = t
    return rets, contrib


def net_stats(rets, fee):
    if not rets:
        return None
    nets = [r - fee for r in rets]
    return {
        "n": len(nets),
        "mean_net": statistics.mean(nets),
        "wr": sum(1 for r in rets if r > 0) / len(rets),
        "sum_net": sum(nets),
    }


def random_baseline(sym_signals, period, max_hold, tp, sl, n_trades, n_draws=1000):
    """For each draw, pick n_trades random (sym, ts, price) entry points in the period,
    random side, run forward_exit, record mean gross return. Return list of draw means."""
    pool = []
    for sym, sigs in sym_signals.items():
        for (t, p, d) in sigs:
            if period == "test" and t < SPLIT_TS: continue
            if period == "train" and t >= SPLIT_TS: continue
            pool.append((sym, t, p))
    if len(pool) < n_trades or n_trades == 0:
        return []
    draws = []
    for _ in range(n_draws):
        picks = random.sample(pool, n_trades)
        rr = []
        for (sym, t, p) in picks:
            side = random.choice([+1, -1])
            rr.append(forward_exit(sym, t, p, side, max_hold, tp, sl))
        draws.append(statistics.mean(rr))
    return draws


# ---------- main search ----------
print(f"# fees RT: {FEES}")
# cache signals per (W, beta=1)
beta = 1.0
best = None
results = []
sigcache = {}

for W in WINDOWS:
    sym_signals = {sym: build_signals(sym, W, beta) for sym in ALTS}
    sigcache[W] = sym_signals
    # report span of days for triggers/day calc
    test_secs = all_alt_ts[-1] - SPLIT_TS
    test_days = test_secs / 86400.0
    train_days = (SPLIT_TS - all_alt_ts[0]) / 86400.0
    for pct in PCTS:
        for direction in ("reversion", "momentum"):
            for max_hold in MAX_HOLDS:
                for tp in TPS:
                    for sl in SLS:
                        tr_rets, _ = run_config(sym_signals, W, pct, direction, max_hold, tp, sl, "train")
                        if len(tr_rets) < 20:
                            continue
                        tr = net_stats(tr_rets, FEES["taker_0.12pct"])
                        results.append({
                            "W": W, "pct": pct, "dir": direction, "mh": max_hold,
                            "tp": tp, "sl": sl,
                            "train_n": tr["n"], "train_mean_net": tr["mean_net"],
                            "train_wr": tr["wr"],
                            "_signals_key": W,
                        })

# pick best TRAIN config by mean_net (taker fee) among those with enough triggers
results.sort(key=lambda r: -r["train_mean_net"])
print("\n# ==== TOP 10 TRAIN configs by mean_net @ taker 0.12% ====")
print(f"{'W':>4}{'pct':>4} {'dir':>9}{'mh':>5}{'tp':>5}{'sl':>5} {'tr_n':>5} {'tr_net%':>9} {'tr_wr':>6}")
for r in results[:10]:
    print(f"{r['W']:>4}{r['pct']:>4} {r['dir']:>9}{r['mh']:>5}{r['tp']*100:>5.1f}{r['sl']*100:>5.1f} "
          f"{r['train_n']:>5} {r['train_mean_net']*100:>8.4f}% {r['train_wr']*100:>5.1f}%")

# now evaluate the top TRAIN config on TEST with full fee breakdown + random baseline
if results:
    bestr = results[0]
    W = bestr["W"]
    sym_signals = sigcache[W]
    test_days = (all_alt_ts[-1] - SPLIT_TS) / 86400.0
    print(f"\n# ==== BEST TRAIN CONFIG -> TEST ====")
    print(f"# {bestr}")
    te_rets, contrib = run_config(sym_signals, W, bestr["pct"], bestr["dir"],
                                  bestr["mh"], bestr["tp"], bestr["sl"], "test")
    print(f"# TEST triggers n={len(te_rets)}  triggers/day={len(te_rets)/test_days:.2f}  test_days={test_days:.1f}")
    for fname, fee in FEES.items():
        st = net_stats(te_rets, fee)
        if st:
            print(f"#   {fname:18s} mean_net={st['mean_net']*100:+.4f}% wr={st['wr']*100:.1f}% sum_net={st['sum_net']*100:+.2f}%")
    # random baseline on TEST, matched n
    if te_rets:
        draws = random_baseline(sym_signals, "test", bestr["mh"], bestr["tp"], bestr["sl"], len(te_rets))
        strat_gross = statistics.mean(te_rets)
        if draws:
            frac_beat = sum(1 for d in draws if d >= strat_gross) / len(draws)
            print(f"#   random baseline (1000 draws, gross): mean={statistics.mean(draws)*100:+.4f}% "
                  f"p10={sorted(draws)[100]*100:+.4f}% p90={sorted(draws)[900]*100:+.4f}%")
            print(f"#   strategy gross mean = {strat_gross*100:+.4f}%  p-value(frac random >= strat) = {frac_beat:.3f}")
    # symbol contribution
    print("#   top contributing symbols (TEST, by sum gross):")
    contrib_sum = sorted(contrib.items(), key=lambda kv: -sum(kv[1]))
    for sym, rr in contrib_sum[:8]:
        print(f"#     {sym:22s} n={len(rr):3d} sum_gross={sum(rr)*100:+.2f}% mean={statistics.mean(rr)*100:+.4f}%")

# Also: evaluate ALL top-5 TRAIN configs on TEST to check robustness
print("\n# ==== TOP-5 TRAIN configs evaluated on TEST (taker 0.12%) ====")
print(f"{'W':>4}{'pct':>4} {'dir':>9}{'mh':>5}{'tp':>5}{'sl':>5} {'te_n':>5} {'te_net%':>9} {'te_wr':>6} {'tr_net%':>9}")
seen_keys=set()
shown=0
for r in results:
    key=(r['W'],r['pct'],r['dir'],r['mh'],r['tp'],r['sl'])
    if key in seen_keys: continue
    seen_keys.add(key)
    W=r['W']
    ss=sigcache[W]
    te,_=run_config(ss,W,r['pct'],r['dir'],r['mh'],r['tp'],r['sl'],"test")
    st=net_stats(te,FEES["taker_0.12pct"])
    if st and st['n']>=MIN_TRIGGERS_TEST:
        print(f"{W:>4}{r['pct']:>4} {r['dir']:>9}{r['mh']:>5}{r['tp']*100:>5.1f}{r['sl']*100:>5.1f} "
              f"{st['n']:>5} {st['mean_net']*100:>8.4f}% {st['wr']*100:>5.1f}% {r['train_mean_net']*100:>8.4f}%")
        shown+=1
    if shown>=5: break
