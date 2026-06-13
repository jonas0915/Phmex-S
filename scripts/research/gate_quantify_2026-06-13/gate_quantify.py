#!/usr/bin/env python3
"""
Quantify-before-cutting: model-free forward-return test for the main-bot entry gates.

Question per gate: does it block LOSERS (earn its keep), WINNERS (cost money),
or NOTHING (cruft)?

Method (NO exit model — sidesteps the broken backtester exit engine):
  For every signal a gate BLOCKED we know (epoch_ts, symbol, side). We read the
  CONTINUOUS 5m kline series (cached by fetch_klines.py) and compute the forward
  price return at 5/15/30/60 min after the block, SIGNED by intended direction:
    signed_ret = side_sign * (close(t0+H) / close(t0) - 1),  +1 long / -1 short
  Entry reference = the 5m close of the bar containing t0 (uniform across every
  population, so log-derived signals with no recorded price work too).

  Verdict per gate, judged against the BASE RATE (entered trades' forward return):
    blocked mean << base, CI<0   -> KEEP   (blocks losers)
    blocked mean  > base          -> COSTS MONEY (blocks better-than-average)
    blocked mean ~= base          -> CRUFT (no separation; blocks signals as good
                                            as the ones it passes)
  Bootstrap 95% CIs on each mean + on the (blocked - base) difference.

Sources (all real, cited at runtime):
  - ENTERED (base rate): trading_state.json closed_trades, htf_l2_anticipation,
    entry_snapshot.ob present. Also carries realized net_pnl -> proxy validation.
  - QUIET-blocked: logs/gotAway.jsonl, htf_l2 (all reason=quiet_regime). Clean, tagged.
  - TIME / OB-wall / WHALE-blocked: parsed from logs/bot.log* (strategy-AMBIGUOUS,
    log retention May 21+). Timestamps America/New_York (EDT) -> epoch.

Kline timestamps are UTC-naive (pd.to_datetime unit='ms').
NO FABRICATION: every printed number is computed from a file read at runtime.
"""
import os, re, sys, csv, json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bisect import bisect_right

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.chdir(ROOT)
KDIR = os.path.join(ROOT, "scripts/research/gate_quantify_2026-06-13/klines5m")

EDT = ZoneInfo("America/New_York")
UTC = timezone.utc
HORIZONS = [5, 15, 30, 60]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
BAR_S = 300
MATCH_TOL_S = 360  # nearest 5m bar must be within this of the target time


# ---------------------------------------------------------------- kline prices
class Klines:
    def __init__(self, kdir):
        self.ts = {}    # full symbol -> sorted epoch list (UTC, bar open)
        self.close = {} # parallel closes
        for fn in os.listdir(kdir):
            if not fn.endswith(".csv"):
                continue
            sym = fn[:-4].replace("_USDT_USDT", "/USDT:USDT")
            ts, cl = [], []
            with open(os.path.join(kdir, fn)) as f:
                for row in csv.DictReader(f):
                    t = int(datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=UTC).timestamp())
                    ts.append(t); cl.append(float(row["close"]))
            self.ts[sym] = ts; self.close[sym] = cl

    def close_at(self, symbol, t):
        """Close of the 5m bar at-or-before t (within MATCH_TOL_S), else None."""
        ts = self.ts.get(symbol)
        if not ts:
            return None
        i = bisect_right(ts, t) - 1
        if i < 0:
            return None
        if t - ts[i] > MATCH_TOL_S + BAR_S:
            return None
        return self.close[symbol][i]

    def signed_fwd(self, symbol, t0, side, horizon_min):
        c0 = self.close_at(symbol, t0)
        cH = self.close_at(symbol, t0 + horizon_min * 60)
        if c0 is None or cH is None or c0 == 0:
            return None
        sign = 1.0 if side == "long" else -1.0
        return sign * (cH / c0 - 1.0)


# ---------------------------------------------------------------- stats
def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")

def _boot_means(xs, iters, seed):
    """Bootstrap resample means in DRAW ORDER (NOT sorted). Each element is one
    independent resample's mean. Caller sorts only when taking quantiles of a
    single distribution — never sort before differencing two of these."""
    n = len(xs); means = []; state = seed
    for _ in range(iters):
        s = 0.0
        for _ in range(n):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            s += xs[state % n]
        means.append(s / n)
    return means

def bootstrap_ci(xs, iters=3000, seed=987654321):
    if not xs:
        return (float("nan"), float("nan"))
    m = sorted(_boot_means(xs, iters, seed))
    return (m[int(0.025 * iters)], m[int(0.975 * iters)])

def diff_ci(a, b, iters=3000, seed=192837465):
    """Proper bootstrap 95% CI of mean(a) - mean(b): resample a and b
    INDEPENDENTLY each iteration, take the difference of the two draw-order
    means, THEN sort the differences. (The earlier version sorted each array
    first and subtracted order-statistic by order-statistic — a comonotonic
    coupling that cancels variance and made the CI ~2.4x too narrow.)"""
    if not a or not b:
        return (float("nan"), float("nan"))
    ma = _boot_means(a, iters, seed)
    mb = _boot_means(b, iters, seed ^ 0x5DEECE66)
    d = sorted(ma[i] - mb[i] for i in range(iters))
    return (d[int(0.025 * iters)], d[int(0.975 * iters)])


# ---------------------------------------------------------------- populations
def load_entered():
    d = json.load(open("trading_state.json"))
    out = []
    for t in d.get("closed_trades", []) or []:
        if t.get("strategy") != "htf_l2_anticipation":
            continue
        es = t.get("entry_snapshot") or {}
        if not es.get("ob"):
            continue
        out.append({"ts": int(es["ts"]), "symbol": es["symbol"],
                    "side": es["direction"], "net_pnl": t.get("net_pnl")})
    return out

def load_quiet_blocked():
    out = []
    for line in open("logs/gotAway.jsonl"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("strategy") == "htf_l2_anticipation" and d.get("reason") == "quiet_regime":
            out.append({"ts": int(d["ts"]), "symbol": d["symbol"], "side": d["direction"]})
    return out

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_TIME_RE = re.compile(r"\[TIME BLOCK\] (\S+/USDT:USDT) (long|short) ")
_OBWALL_RE = re.compile(r"\[OB GATE\] (\S+/USDT:USDT) (LONG|SHORT) blocked — unmatched")
_WHALE_RE = re.compile(r"\[TAPE GATE\] (\S+/USDT:USDT) (LONG|SHORT) blocked — large trade bias")

def load_log_blocked():
    gates = {"TIME": [], "OB_wall": [], "WHALE": []}
    seen = set()
    for fn in sorted(f for f in os.listdir("logs") if f.startswith("bot.log")):
        for raw in open(os.path.join("logs", fn), errors="ignore"):
            line = ANSI.sub("", raw)
            m = _TS_RE.match(line)
            if not m:
                continue
            ts = int(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                     .replace(tzinfo=EDT).timestamp())
            for gate, rx in (("TIME", _TIME_RE), ("OB_wall", _OBWALL_RE), ("WHALE", _WHALE_RE)):
                g = rx.search(line)
                if g:
                    key = (gate, ts, g.group(1), g.group(2).lower())
                    if key not in seen:
                        seen.add(key)
                        gates[gate].append({"ts": ts, "symbol": g.group(1),
                                            "side": g.group(2).lower()})
                    break
    return gates


def collapse(rows, window_s=900):
    """Pseudo-replication fix: the same blocked setup re-fires every ~72s cycle
    throughout a blocked window. Keep only the FIRST signal per (symbol, side)
    within any `window_s` span so near-identical forward windows aren't counted
    as independent observations."""
    out = []
    last = {}  # (symbol, side) -> ts of last kept
    for r in sorted(rows, key=lambda x: x["ts"]):
        k = (r["symbol"], r["side"])
        if k in last and r["ts"] - last[k] < window_s:
            continue
        last[k] = r["ts"]
        out.append(r)
    return out


# ---------------------------------------------------------------- driver
def fwd_series(kl, rows, horizon):
    out = []
    for r in rows:
        sr = kl.signed_fwd(r["symbol"], r["ts"], r["side"], horizon)
        if sr is not None:
            out.append(sr)
    return out

def bp(x):
    return f"{x*1e4:+7.1f}" if x == x else "    n/a"

def main():
    if not os.path.isdir(KDIR) or not os.listdir(KDIR):
        sys.exit(f"no klines in {KDIR} — run fetch_klines.py first")
    kl = Klines(KDIR)
    print(f"klines: {len(kl.ts)} symbols loaded", file=sys.stderr)

    entered = load_entered()  # real distinct trades — NOT collapsed
    quiet_raw = load_quiet_blocked()
    logb = load_log_blocked()
    # collapse pseudo-replicated blocked signals (same sym/side within 15 min)
    quiet = collapse(quiet_raw)
    time_b = collapse(logb["TIME"])
    ob_b = collapse(logb["OB_wall"])
    whale_b = collapse(logb["WHALE"])
    print(f"collapse (15min, same sym/side): QUIET {len(quiet_raw)}->{len(quiet)}  "
          f"TIME {len(logb['TIME'])}->{len(time_b)}  OB {len(logb['OB_wall'])}->{len(ob_b)}  "
          f"WHALE {len(logb['WHALE'])}->{len(whale_b)}", file=sys.stderr)
    pops = [
        ("ENTERED (base rate)", entered),
        ("QUIET-blocked (htf_l2*)", quiet),
        ("TIME-blocked (all-strat)", time_b),
        ("OB-wall-blocked (all-strat)", ob_b),
        ("WHALE-blocked (all-strat)", whale_b),
    ]

    print("\n" + "=" * 104)
    print("GATE QUANTIFY — model-free SIGNED forward returns, bps (negative = blocked a LOSER = good)")
    print("=" * 104)
    hdr = f"{'population':<30} {'n':>4} | " + " | ".join(f"{h:>2}min mean(cov)" for h in HORIZONS)
    print(hdr); print("-" * 104)
    series = {}
    for name, rows in pops:
        line = f"{name:<30} {len(rows):>4} | "
        s = {}
        for h in HORIZONS:
            xs = fwd_series(kl, rows, h); s[h] = xs
            line += f"{bp(_mean(xs))}({len(xs):>3}) | "
        series[name] = s
        print(line)

    FEE_RT_BPS = 12.0  # taker round-trip floor (config.py:59 0.06%x2); maker entries
                       # cut entry side, but exits are often taker. 12bps is the LOW end;
                       # risk_manager.py:253 budgets 22bps. A gross move below this is
                       # not tradeable either way.
    base = series["ENTERED (base rate)"]
    print("\n" + "=" * 104)
    print("VERDICT @30min — blocked vs base rate, bootstrap 95% CIs (bps). "
          f"Fee floor ~{FEE_RT_BPS:.0f}-22bps round-trip.")
    print("=" * 104)
    base30 = base[30]; base30_m = _mean(base30)
    print(f"BASE RATE (entered trades, 30min): mean={bp(base30_m)}bps  n={len(base30)}  "
          f"CI{tuple(round(x*1e4,1) for x in bootstrap_ci(base30))}")
    print("* only QUIET is a clean htf_l2-vs-htf_l2 comparison; TIME/OB/WHALE blocked")
    print("  pops are ALL-STRATEGY (logs untagged) vs an htf_l2-only base -> confounded.")
    print("-" * 104)
    for name, rows in pops:
        if name == "ENTERED (base rate)":
            continue
        xs = series[name][30]
        if not xs:
            print(f"{name:<30} no coverage"); continue
        m = _mean(xs); ci = bootstrap_ci(xs); dci = diff_ci(xs, base30)
        # significance first (CI excludes 0), THEN whether the magnitude even
        # clears the fee floor. Sub-fee separation is not actionable.
        sub_fee = abs(m) * 1e4 < FEE_RT_BPS
        if ci[1] < 0:
            v = "blocks losers" + (" (but sub-fee)" if sub_fee else "")
        elif ci[0] > 0:
            v = "blocks winners" + (" (but sub-fee)" if sub_fee else "")
        elif dci[0] > 0:
            v = "leans blocks-better-than-base (NOT sig)"
        elif dci[1] < 0:
            v = "leans blocks-worse-than-base (NOT sig)"
        else:
            v = "NO separation (CI & diff span 0)"
        print(f"{name:<30} n={len(xs):>3} mean={bp(m)}  CI[{bp(ci[0])},{bp(ci[1])}]  "
              f"diff_vs_base[{bp(dci[0])},{bp(dci[1])}]  -> {v}")

    print("\n" + "=" * 104)
    print("PROXY VALIDATION — entered trades: sign(30min fwd) vs sign(realized net_pnl)")
    print("=" * 104)
    agree = tot = 0
    for r in entered:
        if r.get("net_pnl") is None:
            continue
        sr = kl.signed_fwd(r["symbol"], r["ts"], r["side"], 30)
        if sr is None:
            continue
        tot += 1
        agree += int((sr > 0) == (r["net_pnl"] > 0))
    print(f"agreement: {agree}/{tot} = {100*agree/tot:.0f}%" if tot else "no coverage")
    print("(high agreement => the model-free forward-return proxy tracks real outcomes)")

if __name__ == "__main__":
    main()
