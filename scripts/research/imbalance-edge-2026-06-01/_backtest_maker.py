"""
Maker-fee decisive test for the Dislocation Reversion + Depth-Imbalance Gate signal.

Reuses the EXACT data, train/test chronological split, parameter grid, trigger logic,
refractory rule, and train-only percentile thresholds from _backtest.py.

What is NEW vs _backtest.py:
  - Fees are applied per-scenario, not a flat 0.0012 round-trip taker.
  - Scenario A "optimistic maker, perfect fills": round-trip 0.0002 (0.0001/side),
    every trigger fills at intended price. Upper bound.
  - Scenario B "realistic maker fill model":
      * ENTRY = post-only maker FADING the spike:
          long-fade-a-drop  -> passive limit BUY at the trigger price (current px[i]).
                               Fills only if price later trades AT/BELOW that limit
                               within a fill-wait window (FW seconds). Else NO TRADE.
          short-fade-a-pop -> passive limit SELL at the trigger price (current px[i]).
                               Fills only if price later trades AT/ABOVE that limit
                               within FW. Else NO TRADE.
        Entry fee = 0.0001 maker. Entry price = the limit price (= trigger px[i]).
        The hold clock (max-hold M) starts at the FILL time, not the trigger time.
      * EXIT = post-only maker at TP first; if TP not reached by max-hold M, exit at
        market (taker 0.0006). SL hits are taker (0.0006).
        So per-trade exit fee:
            TP hit (maker)        -> 0.0001
            SL hit (taker)        -> 0.0006
            time-stop (taker mkt) -> 0.0006
        Round-trip fee = entry_fee + exit_fee, blended per trade.

Reported on HELD-OUT TEST for best-on-TRAIN config (selected by net exp/trade under
each scenario's own fee model), plus breakeven fee, gate value, and fill rate.
"""
import json, bisect, itertools, sys, time, statistics
from collections import defaultdict

def log(*a):
    print(*a); sys.stdout.flush()
_t0 = time.time()

PATH = "/Users/jonaspenaso/Desktop/Phmex-S/logs/flow_capture.jsonl"

# Per-scenario fee constants
A_RT_FEE   = 0.0002    # scenario A round-trip (0.0001/side maker)
B_ENTRY    = 0.0001    # scenario B entry maker fee
B_EXIT_TP  = 0.0001    # scenario B exit fee if TP filled as maker
B_EXIT_TKR = 0.0006    # scenario B exit fee if SL or time-stop (taker market)
FILL_WAITS = [30, 60]  # scenario B fill-wait windows (seconds)

# ---------- Load (identical to _backtest.py) ----------
series = defaultdict(lambda: {"ts": [], "px": [], "imb": []})
bad = 0; total = 0
with open(PATH) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            r = json.loads(line)
            sym = r["symbol"]; ts = float(r["ts"]); px = float(r["price"])
            imb = r["ob"]["imbalance"]
            if imb is None or px <= 0:
                bad += 1; continue
            series[sym]["ts"].append(ts)
            series[sym]["px"].append(px)
            series[sym]["imb"].append(float(imb))
        except Exception:
            bad += 1

log(f"RECORDS total={total} bad/skipped={bad} symbols={len(series)}")

for sym, d in series.items():
    order = sorted(range(len(d["ts"])), key=lambda i: d["ts"][i])
    d["ts"] = [d["ts"][i] for i in order]
    d["px"] = [d["px"][i] for i in order]
    d["imb"] = [d["imb"][i] for i in order]

all_ts = []
for d in series.values():
    all_ts.extend(d["ts"])
all_ts.sort()
t_min, t_max = all_ts[0], all_ts[-1]
split_ts = all_ts[len(all_ts)//2]
span_hr = (t_max - t_min)/3600.0
log(f"TIME span {span_hr:.1f}h split_ts={split_ts} ({(split_ts-t_min)/3600:.1f}h into data)")

# ---------- Grid (identical) ----------
Ws   = [180, 300, 600]
PCTS = [90, 95]
THRS = [0.0, 0.1, 0.2]
TPS  = [0.004, 0.006, 0.010]
SLS  = [0.005, 0.008]
MS   = [300, 900, 1800]

def build_retprior(d, W):
    ts = d["ts"]; px = d["px"]; out = []
    for i in range(len(ts)):
        target = ts[i] - W
        j = bisect.bisect_right(ts, target) - 1
        if j < 0:
            out.append(None); continue
        if ts[i] - ts[j] > 2*W:
            out.append(None); continue
        out.append(px[i]/px[j] - 1.0)
    return out

retprior = {}
for sym, d in series.items():
    for W in Ws:
        retprior[(sym, W)] = build_retprior(d, W)

def percentile(sv, p):
    if not sv: return None
    k = (len(sv)-1)*(p/100.0); lo = int(k); hi = min(lo+1, len(sv)-1); frac = k-lo
    return sv[lo]*(1-frac) + sv[hi]*frac

# ---------- Forward simulation returning the OUTCOME TYPE, not just gross ----------
# outcome: 'tp' | 'sl' | 'time'  with gross return (signed, before fees)
def simulate_exit(d, from_idx, entry_px, side, tp, sl, max_hold_s):
    ts = d["ts"]; px = d["px"]
    ts0 = ts[from_idx]
    deadline = ts0 + max_hold_s
    last_px = entry_px
    n = len(ts); j = from_idx + 1
    while j < n and ts[j] <= deadline:
        p = px[j]; last_px = p
        if side == "long":
            ret = p/entry_px - 1.0
            if ret >= tp:  return "tp", tp
            if ret <= -sl: return "sl", -sl
        else:
            ret = entry_px/p - 1.0
            if ret >= tp:  return "tp", tp
            if ret <= -sl: return "sl", -sl
        j += 1
    if side == "long":
        return "time", last_px/entry_px - 1.0
    else:
        return "time", entry_px/last_px - 1.0

# ---------- Scenario A: perfect fills, flat round-trip fee ----------
def run_config_A(W, pct, thr, tp, sl, M, region):
    trades = []  # (sym, side, net, gross)
    per_sym = defaultdict(lambda: [0, 0.0, 0])
    for sym, d in series.items():
        ts = d["ts"]; px = d["px"]; imb = d["imb"]; rp = retprior[(sym, W)]
        train_vals = sorted(v for k, v in enumerate(rp) if v is not None and ts[k] < split_ts)
        if len(train_vals) < 50:
            continue
        hi_thr = percentile(train_vals, pct)
        lo_thr = percentile(train_vals, 100-pct)
        last_trig = -1e18
        for i in range(len(ts)):
            t = ts[i]
            in_region = (t < split_ts) if region == "train" else (t >= split_ts)
            if not in_region: continue
            v = rp[i]
            if v is None: continue
            side = None
            if v >= hi_thr:
                if imb[i] <= -thr: side = "short"
            elif v <= lo_thr:
                if imb[i] >= thr: side = "long"
            if side is None: continue
            if t - last_trig < W: continue
            last_trig = t
            entry_px = px[i]
            _, gross = simulate_exit(d, i, entry_px, side, tp, sl, M)
            net = gross - A_RT_FEE
            trades.append((sym, side, net, gross))
            s = per_sym[sym]; s[0]+=1; s[1]+=net; s[2]+= (1 if net>0 else 0)
    return trades, per_sym

# ---------- Scenario B: realistic maker entry-fill + blended exit fee ----------
# Returns trades with extra fields: filled flag aggregated separately.
# For B we count: triggers, fills, and per-filled-trade net + fee breakdown.
def run_config_B(W, pct, thr, tp, sl, M, region, fill_wait):
    trades = []  # (sym, side, net, gross, rt_fee, exit_type)
    triggers = 0
    fills = 0
    per_sym = defaultdict(lambda: [0, 0.0, 0])
    for sym, d in series.items():
        ts = d["ts"]; px = d["px"]; imb = d["imb"]; rp = retprior[(sym, W)]
        train_vals = sorted(v for k, v in enumerate(rp) if v is not None and ts[k] < split_ts)
        if len(train_vals) < 50:
            continue
        hi_thr = percentile(train_vals, pct)
        lo_thr = percentile(train_vals, 100-pct)
        last_trig = -1e18
        n = len(ts)
        for i in range(n):
            t = ts[i]
            in_region = (t < split_ts) if region == "train" else (t >= split_ts)
            if not in_region: continue
            v = rp[i]
            if v is None: continue
            side = None
            if v >= hi_thr:
                if imb[i] <= -thr: side = "short"
            elif v <= lo_thr:
                if imb[i] >= thr: side = "long"
            if side is None: continue
            if t - last_trig < W: continue
            last_trig = t   # refractory keyed to TRIGGER time (same as taker baseline)
            triggers += 1
            limit_px = px[i]   # passive limit at the trigger price
            # ---- post-only maker entry: must trade through limit within fill_wait ----
            deadline = t + fill_wait
            fill_idx = None
            j = i + 1
            while j < n and ts[j] <= deadline:
                p = px[j]
                if side == "long":
                    # buy limit at limit_px fills if price trades at/below it
                    if p <= limit_px:
                        fill_idx = j; break
                else:
                    # sell limit at limit_px fills if price trades at/above it
                    if p >= limit_px:
                        fill_idx = j; break
                j += 1
            if fill_idx is None:
                continue  # NO TRADE — cost of passivity
            fills += 1
            entry_px = limit_px            # filled at our passive price
            # hold clock starts at FILL time
            exit_type, gross = simulate_exit(d, fill_idx, entry_px, side, tp, sl, M)
            entry_fee = B_ENTRY
            if exit_type == "tp":
                exit_fee = B_EXIT_TP       # TP reached -> maker exit
            else:
                exit_fee = B_EXIT_TKR      # SL or time-stop -> taker market exit
            rt_fee = entry_fee + exit_fee
            net = gross - rt_fee
            trades.append((sym, side, net, gross, rt_fee, exit_type))
            s = per_sym[sym]; s[0]+=1; s[1]+=net; s[2]+= (1 if net>0 else 0)
    return trades, per_sym, triggers, fills

# ---------- Aggregate helpers ----------
def agg(trades):
    n = len(trades)
    if n == 0:
        return dict(n=0, exp=0.0, gross=0.0, wr=0.0, total=0.0)
    exp   = sum(x[2] for x in trades)/n
    gross = sum(x[3] for x in trades)/n
    wr    = sum(1 for x in trades if x[2] > 0)/n
    total = sum(x[2] for x in trades)
    return dict(n=n, exp=exp, gross=gross, wr=wr, total=total)

grid = list(itertools.product(Ws, PCTS, THRS, TPS, SLS, MS))
log(f"\nGRID size = {len(grid)} configs")

# =====================================================================
# SCENARIO A
# =====================================================================
log("\n" + "="*70)
log("SCENARIO A — optimistic maker, perfect fills (round-trip 0.02%)")
log("="*70)

A_train = []
for cfg in grid:
    tr, _ = run_config_A(*cfg, "train")
    a = agg(tr); a["cfg"] = cfg; A_train.append(a)

A_elig = [r for r in A_train if r["n"] >= 50]
A_pos  = [r for r in A_elig if r["exp"] > 0]
log(f"TRAIN eligible (n>=50): {len(A_elig)}/{len(grid)}  net-positive on TRAIN: {len(A_pos)}")
A_best = max(A_elig, key=lambda r: r["exp"])
W,pct,thr,tp,sl,M = A_best["cfg"]
log(f"BEST TRAIN cfg: W={W}s pct={pct} thr={thr} TP={tp*100:.2f}% SL={sl*100:.2f}% M={M}s")
log(f"  TRAIN: n={A_best['n']} wr={A_best['wr']*100:.1f}% gross/trade={A_best['gross']*100:.4f}% net/trade={A_best['exp']*100:.4f}%")

A_test_tr, A_test_ps = run_config_A(W,pct,thr,tp,sl,M, "test")
At = agg(A_test_tr)
log(f"\n  HELD-OUT TEST (best cfg):")
log(f"    n={At['n']} wr={At['wr']*100:.1f}% gross/trade={At['gross']*100:.4f}% "
    f"net/trade={At['exp']*100:.4f}% total_net={At['total']*100:.2f}%")
# Breakeven fee for scenario A best on TEST = gross expectancy (fee that zeros it)
A_breakeven = At["gross"]
log(f"    BREAKEVEN round-trip fee (TEST gross exp): {A_breakeven*100:.4f}%  "
    f"(maker=0.02% taker=0.12%)")

# Gate value (TEST) under scenario A: avg test net/trade by thr bucket over eligible
log(f"\n  GATE VALUE (Scenario A, TEST, eligible configs):")
A_gate = defaultdict(list)
for r in A_elig:
    cW,cpct,cthr,ctp,csl,cM = r["cfg"]
    tt,_ = run_config_A(cW,cpct,cthr,ctp,csl,cM, "test")
    a = agg(tt)
    if a["n"] == 0: continue
    A_gate[cthr].append((a["exp"], a["n"]))
for thr_v in sorted(A_gate):
    rows = A_gate[thr_v]
    avg = sum(e for e,_ in rows)/len(rows)
    tot = sum(nn for _,nn in rows)
    pos = sum(1 for e,_ in rows if e>0)
    log(f"    thr={thr_v}: configs={len(rows):3d} avg_test_net/trade={avg*100:8.4f}% "
        f"test_trades={tot:5d} pct_pos={pos/len(rows)*100:.0f}%")

# =====================================================================
# SCENARIO B  (run for each fill-wait window)
# =====================================================================
for FW in FILL_WAITS:
    log("\n" + "="*70)
    log(f"SCENARIO B — realistic maker fill model, fill-wait = {FW}s")
    log("  entry 0.01% maker (post-only, must fill); exit TP=0.01% maker else 0.06% taker")
    log("="*70)

    B_train = []
    for cfg in grid:
        tr, _, trig, fil = run_config_B(*cfg, "train", FW)
        a = agg(tr); a["cfg"] = cfg; a["trig"] = trig; a["fills"] = fil
        B_train.append(a)

    B_elig = [r for r in B_train if r["n"] >= 50]
    B_pos  = [r for r in B_elig if r["exp"] > 0]
    log(f"TRAIN eligible (filled n>=50): {len(B_elig)}/{len(grid)}  net-positive on TRAIN: {len(B_pos)}")
    if not B_elig:
        log("  No eligible config (too few fills on train). Skipping.")
        continue
    B_best = max(B_elig, key=lambda r: r["exp"])
    W,pct,thr,tp,sl,M = B_best["cfg"]
    log(f"BEST TRAIN cfg: W={W}s pct={pct} thr={thr} TP={tp*100:.2f}% SL={sl*100:.2f}% M={M}s")
    fr_tr = B_best["fills"]/B_best["trig"]*100 if B_best["trig"] else 0
    log(f"  TRAIN: triggers={B_best['trig']} fills={B_best['fills']} ({fr_tr:.1f}%) "
        f"n={B_best['n']} wr={B_best['wr']*100:.1f}% gross/trade={B_best['gross']*100:.4f}% "
        f"net/trade={B_best['exp']*100:.4f}%")

    B_tr, B_ps, B_trig, B_fil = run_config_B(W,pct,thr,tp,sl,M, "test", FW)
    Bt = agg(B_tr)
    fr = B_fil/B_trig*100 if B_trig else 0
    blended = sum(x[4] for x in B_tr)/len(B_tr) if B_tr else 0.0
    tp_cnt = sum(1 for x in B_tr if x[5]=="tp")
    sl_cnt = sum(1 for x in B_tr if x[5]=="sl")
    tm_cnt = sum(1 for x in B_tr if x[5]=="time")
    log(f"\n  HELD-OUT TEST (best cfg, fill-wait {FW}s):")
    log(f"    triggers={B_trig} fills={B_fil} fill_rate={fr:.1f}%")
    log(f"    n={Bt['n']} wr={Bt['wr']*100:.1f}% gross/trade={Bt['gross']*100:.4f}% "
        f"net/trade={Bt['exp']*100:.4f}% total_net={Bt['total']*100:.2f}%")
    log(f"    exit mix: TP(maker)={tp_cnt} SL(taker)={sl_cnt} time(taker)={tm_cnt}")
    log(f"    BLENDED avg round-trip fee actually paid = {blended*100:.4f}%")
    B_breakeven = Bt["gross"]
    log(f"    BREAKEVEN round-trip fee (TEST gross exp) = {B_breakeven*100:.4f}%  "
        f"(blended paid={blended*100:.4f}% maker=0.02% taker=0.12%)")

    # Gate value (TEST) scenario B
    log(f"\n  GATE VALUE (Scenario B FW={FW}s, TEST, eligible configs):")
    B_gate = defaultdict(list)
    for r in B_elig:
        cW,cpct,cthr,ctp,csl,cM = r["cfg"]
        tt,_,_,_ = run_config_B(cW,cpct,cthr,ctp,csl,cM, "test", FW)
        a = agg(tt)
        if a["n"] == 0: continue
        B_gate[cthr].append((a["exp"], a["n"]))
    for thr_v in sorted(B_gate):
        rows = B_gate[thr_v]
        avg = sum(e for e,_ in rows)/len(rows)
        tot = sum(nn for _,nn in rows)
        pos = sum(1 for e,_ in rows if e>0)
        log(f"    thr={thr_v}: configs={len(rows):3d} avg_test_net/trade={avg*100:8.4f}% "
            f"test_trades={tot:5d} pct_pos={pos/len(rows)*100:.0f}%")

log(f"\nDONE in {time.time()-_t0:.1f}s")
