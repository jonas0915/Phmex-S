#!/usr/bin/env python3
"""
Trade simulator: compare imbalance-alone vs book x tape interaction signals.
Net fees: maker 0.02% RT (2 bps), taker 0.12% RT (12 bps).
Chronological train/test (first 60% train to pick threshold, last 40% test).
We trade at fixed horizon (fwd60) — directional sim using realized fwd return as
the exit (no path TP/SL since we only sampled mid at horizons; this is the
honest 'expected move' sim, conservative & look-ahead-free for the decision).

Signals (all map to a direction +1 long / -1 short / 0 flat):
  S0  imb1 momentum          : sign(imb1) when |imb1|>thr
  Sa  absorption-gated       : imb1 momentum only when tape OPPOSES book
  Sb  confirmation-gated     : imb1 momentum only when tape AGREES w/ direction
  Sc  imb1 + ofi combo       : trade only when sign(imb1)==sign(ofi)
  Sd_lo regime: imb1 only when tape QUIET ; Sd_hi only when tape ACTIVE
  Scvd imb1 + tape signed-vol confirm (sign(imb1)==sign(tape_sv))
"""
import pandas as pd, numpy as np

OUT = "scripts/research/booktape-2026-06-13/out"
SYMS = ["BTC", "ETH", "INJ", "ARB"]
MAKER_RT = 0.0002   # 2 bps round trip
TAKER_RT = 0.0012   # 12 bps round trip
HZ = "fwd60"


def load():
    dfs = []
    for s in SYMS:
        df = pd.read_csv(f"{OUT}/{s}_features.csv")
        df["sym"] = s
        df["sv_sign"] = np.sign(df.tape_sv)
        df["ofi_sign"] = np.sign(df.ofi_w)
        df["cnt_med"] = df.tape_cnt.median()
        dfs.append(df)
    return dfs


def sim(direction, ret, fee):
    """direction: array of -1/0/+1. ret: forward return. fee: RT cost.
    returns (n_trades, mean_net_bps, total_net_bps, winrate, sharpe)"""
    mask = direction != 0
    if mask.sum() == 0:
        return (0, 0, 0, 0, 0)
    pnl = direction[mask] * ret[mask] - fee
    return (int(mask.sum()), pnl.mean()*1e4, pnl.sum()*1e4,
            float((pnl > 0).mean()), float(pnl.mean()/(pnl.std()+1e-12)))


def build_signals(df, thr):
    imb = df.imb1.values
    sv = df.sv_sign.values
    ofi = df.ofi_sign.values
    cnt = df.tape_cnt.values
    cnt_q33, cnt_q66 = np.quantile(cnt, [0.33, 0.66])
    base_dir = np.where(np.abs(imb) > thr, np.sign(imb), 0)  # momentum
    sigs = {}
    sigs["S0_imb_alone"] = base_dir.copy()
    # absorption: tape opposes book (sign(sv) != sign(imb))
    opp = sv != np.sign(imb)
    sigs["Sa_absorption"] = np.where(opp, base_dir, 0)
    # confirmation: tape agrees with traded direction (sign(sv)==sign(imb))
    agr = sv == np.sign(imb)
    sigs["Sb_confirm_tape"] = np.where(agr, base_dir, 0)
    # OFI combo: only when ofi sign agrees with imb sign
    sigs["Sc_imb_AND_ofi"] = np.where(ofi == np.sign(imb), base_dir, 0)
    # regime
    sigs["Sd_quiet"] = np.where(cnt <= cnt_q33, base_dir, 0)
    sigs["Sd_active"] = np.where(cnt > cnt_q66, base_dir, 0)
    return sigs


def run():
    dfs = load()
    allp = pd.concat(dfs, ignore_index=True)
    print("="*78)
    print(f"TRADE SIM @ {HZ}  | maker RT={MAKER_RT*1e4:.0f}bps  taker RT={TAKER_RT*1e4:.0f}bps")
    print("Direction = trade WITH book imbalance (momentum, the sign that works here).")
    print("="*78)

    # Pick threshold on TRAIN per symbol (chronological), evaluate on TEST.
    THRS = [0.0, 0.2, 0.4, 0.6]
    for fee, fname in [(MAKER_RT, "MAKER 2bps"), (TAKER_RT, "TAKER 12bps")]:
        print(f"\n########## FEE = {fname} ##########")
        # pooled, but threshold chosen per-symbol on train then applied test, summed.
        agg = {}
        for s in SYMS:
            df = dfs[s_i(s)].reset_index(drop=True)
            n = len(df); cut = int(n*0.6)
            tr, te = df.iloc[:cut], df.iloc[cut:]
            # choose best threshold for S0 on train (by net mean bps)
            best_thr, best_v = 0.0, -1e9
            for t in THRS:
                d = build_signals(tr, t)["S0_imb_alone"]
                v = sim(d, tr[HZ].values, fee)[1]
                if v > best_v: best_v, best_thr = v, t
            sigs_te = build_signals(te, best_thr)
            for name, d in sigs_te.items():
                r = sim(d, te[HZ].values, fee)
                agg.setdefault(name, []).append((s, best_thr, r))
        # print per signal: pooled net bps/trade (trade-weighted) + total
        print(f"{'signal':18s} {'n_trades':>9s} {'net_bps/trade':>14s} {'total_bps':>11s} {'winrate':>8s}")
        for name in ["S0_imb_alone","Sa_absorption","Sb_confirm_tape","Sc_imb_AND_ofi","Sd_quiet","Sd_active"]:
            rows = agg[name]
            N = sum(r[2][0] for r in rows)
            tot = sum(r[2][2] for r in rows)
            wr = np.average([r[2][3] for r in rows if r[2][0]>0],
                            weights=[r[2][0] for r in rows if r[2][0]>0]) if N>0 else 0
            mean = tot / N if N>0 else 0
            flag = "  <== beats fees & beats S0" if False else ""
            print(f"{name:18s} {N:9d} {mean:14.3f} {tot:11.1f} {wr:8.3f}")
        thrs_used = {r[0]: r[1] for r in agg['S0_imb_alone']}
        print("  thresholds chosen (per sym, on train):", thrs_used)


def s_i(s):
    return SYMS.index(s)


if __name__ == "__main__":
    run()
