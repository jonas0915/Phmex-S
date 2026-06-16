#!/usr/bin/env python3
"""ST2.0 maker-first exit replay — BOTH-SIDED.

Compares the CURRENT ST2.0 exit (fixed ~15-min maker hold + resting SL/TP)
against a MAKER-FIRST ACTIVE exit (adds the live tiered trailing stop +
breakeven ratchet; taker fee charged only on stop exits as the catastrophe
backstop) over the SAME ST2.0 entries and the SAME recorded price paths
(logs/flow_capture.jsonl). Reuses backtest.py's validated price-only trail
functions — no reinvention (lessons.md META-RULE #4).

Reports the BOTH-SIDED diff lessons.md:366 demands: dollars SAVED on baseline
losers AND dollars CLIPPED off baseline winners — not just a net number. A trail
that "rescues losers" is worthless if it equally clips winners.

Entry sets:
  --real : real LIVE ST2.0 trades (trading_state_ST2.0.json, mode==live).
           Honest but THIN (~11). The truth set.
  --sim  : ST2.0 signals reconstructed from flow_capture (champion gate:
           imbalance>=imb_min & buy_ratio>=br_min & trade_count>=min_trades).
           Larger DIRECTIONAL surface, but fills ALL signals (artifact-prone).

HONESTY CAVEATS (also printed at runtime):
  * flow_capture samples each symbol ~76-95s apart → the trail is modeled at the
    live DECISION cadence (which is what the live software trail actually used),
    NOT tick-accurate fills. Relative A/B ranking, not an absolute fill forecast.
  * The robust output is the per-trade DELTA (variant - baseline); both legs use
    the identical simulator + paths, so the delta isolates the exit-rule effect
    even where absolute PnL fidelity is imperfect.

Run from repo root:
    python scripts/st2_lab/exit_replay.py            # real + sim
    python scripts/st2_lab/exit_replay.py --real     # real only
    python scripts/st2_lab/exit_replay.py --trail-arm-roi 8 --trail-tier1-lock 2
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sys

# repo root on path (backtest.py + this package live under it)
_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))

import backtest  # noqa: E402
from backtest import (  # noqa: E402
    BTPosition, _live_update_trailing, _live_check_breakeven, _effective_stop,
)

# package-relative imports work whether run as module or script
try:
    from . import config as C
    from . import dataset as DS
except ImportError:  # run directly as a file
    from st2_lab import config as C  # type: ignore
    from st2_lab import dataset as DS  # type: ignore

LEVERAGE = 10
DEFAULT_MARGIN = C.MARGIN_USDT  # 10.0; sim notional = MARGIN * LEVERAGE
PARAMS = dict(C.DEFAULT_CHAMPION["params"])  # imb_min/br_min/min_trades/hold_secs/sl_pct/tp_pct
PATH_LOOKAHEAD = 60  # records to scan after entry (~60*80s ≈ 80min >> 15min hold)
SIM_COOLDOWN_S = 900  # one ST2.0 entry per symbol per hold window (no overlap)


def _net(entry_price, exit_price, side, reason, notional, maker_fee, taker_fee):
    """Net PnL: gross minus maker entry fee minus exit fee (taker on stops, maker
    on profit/hold exits — the maker-first economics)."""
    if side == "short":
        gross = (entry_price - exit_price) / entry_price * notional
    else:
        gross = (exit_price - entry_price) / entry_price * notional
    entry_fee = notional * maker_fee / 100.0  # ST2.0 enters PostOnly (maker)
    is_taker_exit = reason in ("stop_loss", "catastrophe")
    exit_fee = notional * (taker_fee if is_taker_exit else maker_fee) / 100.0
    return gross - entry_fee - exit_fee


def _simulate(sym, side, entry_price, entry_ts, path, params, variant):
    """Walk the forward price path; return (exit_price, reason, held_s).
    baseline: resting SL/TP + fixed hold. variant: + tiered trail + breakeven."""
    sl = entry_price * (1 + params["sl_pct"] / 100) if side == "short" else entry_price * (1 - params["sl_pct"] / 100)
    tp = entry_price * (1 - params["tp_pct"] / 100) if side == "short" else entry_price * (1 + params["tp_pct"] / 100)
    pos = BTPosition(
        pair=sym, direction=side, entry_price=entry_price, entry_candle=0,
        size_usd=0.0, margin=DEFAULT_MARGIN, sl_price=sl, tp_price=tp,
        strategy="ST2.0", peak_price=entry_price, entry_epoch=entry_ts,
    )
    hold = params["hold_secs"]
    for rec in path:
        ts, price = rec["ts"], rec["price"]
        held = ts - entry_ts
        if variant:
            _live_update_trailing(pos, price)   # arms trail at ROI>=5%, ratchets
            _live_check_breakeven(pos, price)   # 1R -> entry +/-0.25% lock
        eff_sl = _effective_stop(pos) if variant else pos.sl_price
        if side == "short":
            sl_hit, tp_hit = price >= eff_sl, price <= pos.tp_price
        else:
            sl_hit, tp_hit = price <= eff_sl, price >= pos.tp_price
        if sl_hit:  # pessimistic: stop wins if both inside one sampled point
            armed = variant and pos.trailing_stop_price is not None
            return eff_sl, ("trailing_stop" if armed else "stop_loss"), held
        if tp_hit:
            return pos.tp_price, "take_profit", held
        if held >= hold:
            return price, "st2_hold", held
    if path:  # ran out of recorded path before the hold elapsed
        return path[-1]["price"], "end_of_path", path[-1]["ts"] - entry_ts
    return entry_price, "no_path", 0


def _forward_path(recs, ts_list, entry_ts):
    """Records strictly after entry_ts, capped to PATH_LOOKAHEAD."""
    i = bisect.bisect_right(ts_list, entry_ts)
    return recs[i:i + PATH_LOOKAHEAD]


def _real_entries(by_symbol):
    """Real LIVE ST2.0 trades projected to entries with a flow_capture path."""
    state_file = os.path.join(C.BOT_DIR, "trading_state_ST2.0.json")
    if not os.path.exists(state_file):
        return [], 0
    try:
        ct = json.load(open(state_file)).get("closed_trades", [])
    except (json.JSONDecodeError, OSError):
        return [], 0
    out, no_path = [], 0
    ts_index = {s: [r["ts"] for r in recs] for s, recs in by_symbol.items()}
    for t in ct:
        if t.get("mode") != "live":
            continue
        sym = t.get("symbol")
        recs = by_symbol.get(sym)
        if not recs:
            no_path += 1
            continue
        entry_price = t.get("entry_price") or t.get("entry")
        entry_ts = int(t.get("opened_at") or 0)
        side = t.get("side", "short")
        amount = float(t.get("amount", 0) or 0)
        notional = (amount * entry_price) if amount else DEFAULT_MARGIN * LEVERAGE
        path = _forward_path(recs, ts_index[sym], entry_ts)
        if not path:
            no_path += 1
            continue
        out.append({"symbol": sym, "side": side, "entry_price": entry_price,
                    "entry_ts": entry_ts, "notional": notional, "path": path})
    return out, no_path


def _sim_entries(by_symbol, params, max_n=None):
    """Reconstruct ST2.0 short signals from flow_capture (champion base gate)."""
    out = []
    for sym, recs in by_symbol.items():
        ts_list = [r["ts"] for r in recs]
        last = -10 ** 18
        for r in recs:
            if r["ts"] - last < SIM_COOLDOWN_S:
                continue
            if (r["imbalance"] >= params["imb_min"]
                    and r["buy_ratio"] >= params["br_min"]
                    and r["trade_count"] >= params["min_trades"]):
                path = _forward_path(recs, ts_list, r["ts"])
                if not path:
                    continue
                out.append({"symbol": sym, "side": "short", "entry_price": r["price"],
                            "entry_ts": r["ts"], "notional": DEFAULT_MARGIN * LEVERAGE,
                            "path": path})
                last = r["ts"]
    out.sort(key=lambda e: e["entry_ts"])
    if max_n:
        out = out[:max_n]
    return out


def _run(entries, params, maker_fee, taker_fee, label):
    """Simulate baseline vs variant over entries; return both-sided summary."""
    rows = []
    for e in entries:
        b_px, b_rsn, _ = _simulate(e["symbol"], e["side"], e["entry_price"],
                                   e["entry_ts"], e["path"], params, variant=False)
        v_px, v_rsn, _ = _simulate(e["symbol"], e["side"], e["entry_price"],
                                   e["entry_ts"], e["path"], params, variant=True)
        b_net = _net(e["entry_price"], b_px, e["side"], b_rsn, e["notional"], maker_fee, taker_fee)
        v_net = _net(e["entry_price"], v_px, e["side"], v_rsn, e["notional"], maker_fee, taker_fee)
        rows.append({"sym": e["symbol"].split("/")[0], "b_net": b_net, "v_net": v_net,
                     "delta": v_net - b_net, "b_reason": b_rsn, "v_reason": v_rsn})
    n = len(rows)
    if n == 0:
        print(f"\n=== {label}: 0 entries (no data) ===")
        return None
    b_tot = sum(r["b_net"] for r in rows)
    v_tot = sum(r["v_net"] for r in rows)
    saved = sum(r["delta"] for r in rows if r["b_net"] <= 0)   # on baseline losers
    clipped = sum(r["delta"] for r in rows if r["b_net"] > 0)  # on baseline winners
    b_wins = sum(1 for r in rows if r["b_net"] > 0)
    v_wins = sum(1 for r in rows if r["v_net"] > 0)
    print(f"\n=== {label} (n={n}) ===")
    print(f"  baseline net  ${b_tot:+.3f}  | WR {b_wins}/{n} ({b_wins/n*100:.0f}%) | exp ${b_tot/n:+.4f}/trade")
    print(f"  variant  net  ${v_tot:+.3f}  | WR {v_wins}/{n} ({v_wins/n*100:.0f}%) | exp ${v_tot/n:+.4f}/trade")
    print(f"  NET DELTA     ${v_tot - b_tot:+.3f}  ({(v_tot-b_tot)/n:+.4f}/trade)")
    print(f"  both-sided:   saved on losers ${saved:+.3f}  |  clipped off winners ${clipped:+.3f}")
    # reason mix shift
    from collections import Counter
    bc, vc = Counter(r["b_reason"] for r in rows), Counter(r["v_reason"] for r in rows)
    keys = sorted(set(bc) | set(vc))
    print("  exit-reason mix (baseline -> variant):")
    for k in keys:
        print(f"    {k:<14} {bc.get(k,0):>4} -> {vc.get(k,0):<4}")
    return {"label": label, "n": n, "b_net": b_tot, "v_net": v_tot,
            "saved": saved, "clipped": clipped, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description="ST2.0 maker-first exit replay (both-sided)")
    ap.add_argument("--real", action="store_true", help="real live ST2.0 trades only")
    ap.add_argument("--sim", action="store_true", help="simulated ST2.0 entries only")
    ap.add_argument("--trail-arm-roi", type=float, default=None, help="trail arm ROI %% (live 5.0)")
    ap.add_argument("--trail-tier1-lock", type=float, default=None, help="tier-1 lock-in %% (live 2.0)")
    ap.add_argument("--hold-secs", type=int, default=None, help="fixed hold backstop (live 900)")
    ap.add_argument("--maker-fee", type=float, default=0.02, help="maker fee %% per side (default 0.02)")
    ap.add_argument("--taker-fee", type=float, default=0.06, help="taker fee %% per side (default 0.06)")
    ap.add_argument("--max-sim", type=int, default=None, help="cap simulated entries")
    ap.add_argument("--dump-json", type=str, default=None, help="write per-trade rows to PATH")
    args = ap.parse_args()

    # trail-knob overrides into backtest's module globals (used by _live_update_trailing)
    if args.trail_arm_roi is not None:
        backtest.TRAIL_ARM_ROI = args.trail_arm_roi
    if args.trail_tier1_lock is not None:
        backtest.TRAIL_TIER1_LOCK = args.trail_tier1_lock
    params = dict(PARAMS)
    if args.hold_secs is not None:
        params["hold_secs"] = args.hold_secs

    run_real = args.real or not args.sim
    run_sim = args.sim or not args.real

    print("ST2.0 maker-first exit replay — BOTH-SIDED")
    print(f"  params: {params}")
    print(f"  trail: arm ROI {getattr(backtest,'TRAIL_ARM_ROI',5.0)}%, tier1 lock "
          f"{getattr(backtest,'TRAIL_TIER1_LOCK',2.0)}% | fees maker {args.maker_fee}% / taker {args.taker_fee}%")
    print("  CAVEAT: flow cadence ~76-95s → trail modeled at decision cadence, NOT tick fills.")

    print("  loading flow_capture ...", flush=True)
    by_symbol = DS.load_dataset()
    print(f"  {DS.dataset_summary(by_symbol)}")

    summaries = []
    if run_real:
        ents, no_path = _real_entries(by_symbol)
        if no_path:
            print(f"  [real] {no_path} live trade(s) skipped — no flow_capture path for symbol/time")
        s = _run(ents, params, args.maker_fee, args.taker_fee, "REAL live ST2.0 (truth set, THIN)")
        if s:
            summaries.append(s)
    if run_sim:
        ents = _sim_entries(by_symbol, params, max_n=args.max_sim)
        s = _run(ents, params, args.maker_fee, args.taker_fee,
                 "SIMULATED ST2.0 (fill-all, DIRECTIONAL — artifact-prone)")
        if s:
            summaries.append(s)

    print("\n--- verdict guidance ---")
    print("  Adopt the trail ONLY if NET DELTA > 0 AND 'saved on losers' clearly")
    print("  exceeds |clipped off winners| on the REAL set, and the SIM set agrees in sign.")
    print("  With n~11 real trades this is DIRECTIONAL — confirm on a healthier sample")
    print("  (st2-watch tracks ST2.0 toward 30 live trades) before arming live.")

    if args.dump_json:
        with open(args.dump_json, "w") as fh:
            json.dump(summaries, fh, indent=1)
        print(f"\n  per-trade dump: {args.dump_json}")


if __name__ == "__main__":
    main()
