#!/usr/bin/env python3
"""MR-tuned universe (ranginess scanner) scan — pre-reg 2026-08-01.

Contract: docs/superpowers/specs/2026-08-01-mr-universe-ranginess-scan-prereg.md
Read-only wrt the live bot. Reuses the existing replay engine
(scripts/slot_lab/mean_revert_replay.py: signal regen + price-path simulate)
and applies the pre-registered fee model (0.12% RT of notional, $30 @ 10x).

Outputs (this dir): results.json, lists.json, trades_all.csv, scan.log (stdout).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reuse the existing engine (do not modify the original file).
from slot_lab.mean_revert_replay import (  # noqa: E402
    _regen_signals, _build_path, PARAMS, WARMUP,
)
from st2_lab.exit_replay import _simulate  # noqa: E402
from indicators import add_all_indicators, adx as adx_fn, bollinger_bands  # noqa: E402
# ---- pre-registered constants (frozen) ----
MARGIN = 30.0
LEVERAGE = 10
NOTIONAL = MARGIN * LEVERAGE          # $300
FEE_RT_PCT = 0.12                     # % of notional, round trip (pre-reg)
FEE_RT = NOTIONAL * FEE_RT_PCT / 100  # $0.36 per trade
TOP_N = 8
REBAL_DAYS = 7
SCORE_LOOKBACK_D = 30
ADX_CUTOFF = 25.0
BB_RETURN_BARS = 12
TRAIN_FRAC = 0.70

DAYS = 400
CACHE = os.path.join(HERE, "cache")
D = 86400


def log(msg):
    print(msg, flush=True)


def _load(sym, tf):
    key = sym.replace("/", "_").replace(":", "_")
    path = os.path.join(CACHE, f"{key}_{tf}_{DAYS}d.parquet")
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


# ------------------------------------------------------------------- scoring
def prep_scoring(df1h):
    """Per-pair 1h arrays for ranginess scoring."""
    c, h, l = df1h["close"], df1h["high"], df1h["low"]
    adx_v, _, _ = adx_fn(h, l, c, period=14)
    up, mid, lo = bollinger_bands(c, period=20, std_dev=2.0)
    ts = np.asarray(df1h.index.view("int64")) // 1_000_000_000
    close = c.to_numpy(float)
    high = h.to_numpy(float)
    low = l.to_numpy(float)
    adx_a = adx_v.to_numpy(float)
    up_a, mid_a, lo_a = up.to_numpy(float), mid.to_numpy(float), lo.to_numpy(float)

    n = len(ts)
    out_dir = np.zeros(n, dtype=int)  # +1 close>upper, -1 close<lower
    with np.errstate(invalid="ignore"):
        out_dir[close > up_a] = 1     # NaN comparisons are False (warmup bars)
        out_dir[close < lo_a] = -1
    resolved = np.zeros(n, dtype=bool)
    for i in np.nonzero(out_dir)[0]:
        hi_k = min(n, i + 1 + BB_RETURN_BARS)
        if out_dir[i] > 0:   # above upper: return = price reaches down to SMA20
            resolved[i] = bool(np.any(low[i + 1:hi_k] <= mid_a[i + 1:hi_k]))
        else:                # below lower: return = price reaches up to SMA20
            resolved[i] = bool(np.any(high[i + 1:hi_k] >= mid_a[i + 1:hi_k]))
    return {"ts": ts, "close": close, "adx": adx_a, "out": out_dir,
            "resolved": resolved}


def score_at(S, reb_ts):
    """Ranginess score on trailing 30d of 1h bars, no lookahead past reb_ts.
    Returns (score, r1, r2) or None if <30d of history."""
    ts = S["ts"]
    lo_ts, hi_ts = reb_ts - SCORE_LOOKBACK_D * D, reb_ts
    if len(ts) == 0 or ts[0] > lo_ts:
        return None
    w = (ts >= lo_ts) & (ts < hi_ts)
    adx_w = S["adx"][w]
    adx_w = adx_w[~np.isnan(adx_w)]
    if len(adx_w) == 0:
        return None
    r1 = float(np.mean(adx_w < ADX_CUTOFF))
    # R2 events: outside-closes whose 12-bar forward window resolves before
    # reb_ts (event bar open <= reb - 13h) — avoids lookahead at decision time.
    ev = w & (S["out"] != 0) & (ts <= reb_ts - (BB_RETURN_BARS + 1) * 3600)
    n_ev = int(np.sum(ev))
    r2 = float(np.sum(S["resolved"][ev]) / n_ev) if n_ev else 0.0
    return (r1 * r2, r1, r2, n_ev)


def control_at(S, reb_ts):
    """Trailing-24h |return| at reb_ts (last close before reb vs close ~24h prior)."""
    ts, close = S["ts"], S["close"]
    i_now = np.searchsorted(ts, reb_ts) - 1
    if i_now < 0:
        return None
    i_prev = np.searchsorted(ts, ts[i_now] - 24 * 3600, side="right") - 1
    if i_prev < 0 or i_prev == i_now:
        return None
    if close[i_prev] == 0:
        return None
    return abs(close[i_now] / close[i_prev] - 1.0)


# --------------------------------------------------------------------- replay
def replay_pair(sym):
    df5 = _load(sym, "5m")
    if df5 is None or len(df5) < WARMUP + 22:
        return []
    df5i = add_all_indicators(df5)
    sigs = _regen_signals(df5i, sym)  # pure engine fn, reused as-is
    trades = []
    for s in sigs:
        path = _build_path(df5, s["entry_ts"], PARAMS["hold_secs"], s["side"])
        if not path:
            continue
        entry = s["close"]
        exit_px, reason, held = _simulate(sym, s["side"], entry, s["entry_ts"],
                                          path, PARAMS, variant=True)
        if s["side"] == "short":
            gross = (entry - exit_px) / entry * NOTIONAL
        else:
            gross = (exit_px - entry) / entry * NOTIONAL
        trades.append({"symbol": sym, "side": s["side"], "entry_ts": s["entry_ts"],
                       "net": gross - FEE_RT, "gross": gross, "reason": reason,
                       "held_s": held, "rsi": s["rsi"]})
    return trades


# -------------------------------------------------------------------- metrics
def seg_metrics(trades, days):
    n = len(trades)
    nets = [t["net"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    return {
        "n": n,
        "days": round(days, 2),
        "trades_per_day": round(n / days, 4) if days > 0 else 0.0,
        "net_total": round(sum(nets), 4),
        "net_per_trade": round(sum(nets) / n, 4) if n else 0.0,
        "win_rate": round(len(wins) / n, 4) if n else 0.0,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0.0,
    }


def per_pair(trades):
    out = {}
    for t in trades:
        d = out.setdefault(t["symbol"], {"n": 0, "net": 0.0, "wins": 0})
        d["n"] += 1
        d["net"] += t["net"]
        d["wins"] += 1 if t["net"] > 0 else 0
    return {s: {"n": d["n"], "net": round(d["net"], 4),
                "wr": round(d["wins"] / d["n"], 3)} for s, d in sorted(out.items())}


# ----------------------------------------------------------------------- main
def main():
    universe = json.load(open(os.path.join(HERE, "universe.json")))
    pairs = [r["symbol"] for r in universe["pairs"]]
    log(f"universe: {len(pairs)} pairs (>= $3M 24h turnover at snapshot)")

    # scoring prep (1h)
    S = {}
    for sym in pairs:
        df1h = _load(sym, "1h")
        if df1h is None or len(df1h) < 25:
            log(f"  {sym}: no/short 1h data — excluded from scoring")
            continue
        S[sym] = prep_scoring(df1h)

    # replay span = intersection-ish: rebalances start 30d after the EARLIEST
    # 1h data (pairs without 30d history at a rebalance are simply ineligible
    # for that rebalance), end at the latest 5m bar.
    start_1h = min(S[s]["ts"][0] for s in S)
    end_5m = 0
    for sym in pairs:
        df5 = _load(sym, "5m")
        if df5 is not None and len(df5):
            end_5m = max(end_5m, int(df5.index.view("int64")[-1] // 1_000_000_000))
    span_start = int(start_1h) + SCORE_LOOKBACK_D * D  # int() — np.int64 breaks json.dump
    span_end = end_5m
    reb_ts_list = list(range(span_start, span_end, REBAL_DAYS * D))
    log(f"span: {datetime.fromtimestamp(span_start, tz=timezone.utc)} -> "
        f"{datetime.fromtimestamp(span_end, tz=timezone.utc)} "
        f"({(span_end - span_start) / D:.1f}d), {len(reb_ts_list)} rebalances")

    # rotating lists
    lists = []
    for R in reb_ts_list:
        scored, ctrl = [], []
        for sym in S:
            sc = score_at(S[sym], R)
            if sc is not None:
                scored.append((sym, sc[0], sc[1], sc[2], sc[3]))
            cv = control_at(S[sym], R)
            if cv is not None and S[sym]["ts"][0] <= R - SCORE_LOOKBACK_D * D:
                # control list drawn from the same eligible universe
                ctrl.append((sym, cv))
        scored.sort(key=lambda x: (-x[1], x[0]))
        ctrl.sort(key=lambda x: (-x[1], x[0]))
        lists.append({
            "rebalance_ts": R,
            "rebalance_utc": datetime.fromtimestamp(R, tz=timezone.utc).isoformat(),
            "test_top8": [x[0] for x in scored[:TOP_N]],
            "test_scores": {x[0]: {"score": round(x[1], 4), "r1": round(x[2], 3),
                                   "r2": round(x[3], 3), "n_events": x[4]}
                            for x in scored},
            "control_top8": [x[0] for x in ctrl[:TOP_N]],
            "control_ranks": {x[0]: round(x[1], 5) for x in ctrl},
        })
    with open(os.path.join(HERE, "lists.json"), "w") as fh:
        json.dump(lists, fh, indent=1)

    # replay all pairs once; filter by membership per list
    trades_csv = os.path.join(HERE, "trades_all.csv")
    if os.path.exists(trades_csv):
        # fast path after the 2026-08-01 json-serialization crash: the replay
        # already ran to completion; reuse its on-disk output (deterministic).
        all_trades = pd.read_csv(trades_csv).to_dict("records")
        log(f"  loaded {len(all_trades)} trades from existing trades_all.csv")
    else:
        all_trades = []
        for sym in pairs:
            tr = replay_pair(sym)
            log(f"  replay {sym}: {len(tr)} trades (full span, pre-membership)")
            all_trades.extend(tr)
        pd.DataFrame(all_trades).to_csv(trades_csv, index=False)

    def in_list(kind, t):
        R_idx = (t["entry_ts"] - span_start) // (REBAL_DAYS * D)
        if R_idx < 0 or R_idx >= len(lists):
            return False
        return t["symbol"] in lists[int(R_idx)][kind]

    test_tr = [t for t in all_trades if in_list("test_top8", t)]
    ctrl_tr = [t for t in all_trades if in_list("control_top8", t)]
    for name, trs in (("test", test_tr), ("control", ctrl_tr)):
        pd.DataFrame(trs).to_csv(os.path.join(HERE, f"trades_{name}.csv"), index=False)

    # 70/30 time split
    t_split = span_start + int(TRAIN_FRAC * (span_end - span_start))
    train_days = (t_split - span_start) / D
    hold_days = (span_end - t_split) / D

    def split(trs):
        return ([t for t in trs if t["entry_ts"] < t_split],
                [t for t in trs if t["entry_ts"] >= t_split])

    test_train, test_hold = split(test_tr)
    ctrl_train, ctrl_hold = split(ctrl_tr)

    res = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "prereg": "docs/superpowers/specs/2026-08-01-mr-universe-ranginess-scan-prereg.md",
        "fee_model": {"rt_pct_of_notional": FEE_RT_PCT, "margin": MARGIN,
                      "leverage": LEVERAGE, "notional": NOTIONAL,
                      "fee_per_trade_usd": FEE_RT},
        "span": {"start_ts": span_start, "end_ts": span_end,
                 "split_ts": t_split,
                 "start_utc": datetime.fromtimestamp(span_start, tz=timezone.utc).isoformat(),
                 "split_utc": datetime.fromtimestamp(t_split, tz=timezone.utc).isoformat(),
                 "end_utc": datetime.fromtimestamp(span_end, tz=timezone.utc).isoformat(),
                 "train_days": round(train_days, 2), "holdout_days": round(hold_days, 2),
                 "n_rebalances": len(reb_ts_list)},
        "train": {
            "test": seg_metrics(test_train, train_days),
            "control": seg_metrics(ctrl_train, train_days),
            "test_per_pair": per_pair(test_train),
            "control_per_pair": per_pair(ctrl_train),
        },
    }

    tt, tc = res["train"]["test"], res["train"]["control"]
    elig = {
        "cond1_net_per_trade_pos": tt["net_per_trade"] > 0,
        "cond2_net_ge_control": tt["net_per_trade"] >= tc["net_per_trade"],
        "cond3_freq_ge_1p5x_control": tt["trades_per_day"] >= 1.5 * tc["trades_per_day"],
    }
    eligible = all(elig.values())
    res["train_eligibility"] = {**elig, "eligible": eligible}
    log(f"\nTRAIN test: n={tt['n']} net/tr=${tt['net_per_trade']} t/d={tt['trades_per_day']}")
    log(f"TRAIN ctrl: n={tc['n']} net/tr=${tc['net_per_trade']} t/d={tc['trades_per_day']}")
    log(f"eligibility: {elig} -> eligible={eligible}")

    # Holdout is computed for reporting (pre-reg: freq+net reported for both
    # lists regardless of verdict), but the VERDICT consumes it only if eligible.
    res["holdout"] = {
        "test": seg_metrics(test_hold, hold_days),
        "control": seg_metrics(ctrl_hold, hold_days),
        "test_per_pair": per_pair(test_hold),
        "control_per_pair": per_pair(ctrl_hold),
    }
    ht, hc = res["holdout"]["test"], res["holdout"]["control"]
    if eligible:
        passed = ht["net_per_trade"] > 0 and ht["net_per_trade"] >= hc["net_per_trade"]
        res["verdict"] = "PASS" if passed else "DO-NOT-BUILD"
        res["verdict_basis"] = {"holdout_net_per_trade_pos": ht["net_per_trade"] > 0,
                                "holdout_net_ge_control": ht["net_per_trade"] >= hc["net_per_trade"]}
    else:
        res["verdict"] = "DO-NOT-BUILD"
        res["verdict_basis"] = {"train_eligibility_failed": True, **elig}
    log(f"HOLDOUT test: n={ht['n']} net/tr=${ht['net_per_trade']} t/d={ht['trades_per_day']}")
    log(f"HOLDOUT ctrl: n={hc['n']} net/tr=${hc['net_per_trade']} t/d={hc['trades_per_day']}")
    log(f"\nVERDICT: {res['verdict']}")

    with open(os.path.join(HERE, "results.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    log("results.json written")


if __name__ == "__main__":
    main()
