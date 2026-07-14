#!/usr/bin/env python3
"""5m_mean_revert GATE-BLOCKED signal counterfactual — SCREENING-GRADE.

Question (overnight research 2026-07-13): are the OB gate (imbalance / unmatched
wall / wide spread) and the tape-divergence gate PROTECTING the 5m_mean_revert
slot or STRANGLING it? The buy_ratio legs were already adjudicated 2026-07-12
(shorts exempted, +$6.19 CI excl 0; blocked longs LOSE — gate stays) and are
reported here ONLY as sanity cross-checks, not for re-litigation.

Inventory source: [PAPER] [OB GATE] / [PAPER] [TAPE GATE] 5m_mean_revert lines
in logs/bot.log{,.1..5}. Log timestamps verified Pacific for the whole window
(183/195 quiet_regime gotAway epochs match bot.log [REGIME GATE] lines exactly
when parsed as America/Los_Angeles; 0/195 match as America/New_York — see
session receipts). gotAway.jsonl itself has ZERO 5m_mean_revert records (it is
main-loop only), so prices come from logs/flow_capture.jsonl — the per-scan
snapshot (_log_flow_snapshot, bot.py) written in the SAME cycle the gate fired
(match tolerance ±150s, same symbol).

Counterfactual engine — REUSED, not reinvented (lessons.md META-RULE #4):
  * scripts/slot_lab/mean_revert_replay.py  _build_path/_net/_boot_mean_ci,
      PARAMS (flat 1.2% SL / 1.6% TP / 4h hold — the algebraic collapse of the
      live ATR-adaptive exits under current config, see that file's header)
  * scripts/st2_lab/exit_replay.py          _simulate (validated SL/TP/trail
      price-path walker, pessimistic intrabar: adverse extreme first)
  * backtest.py                             _live_update_trailing etc.
      TRAIL_ARM_ROI overridden to 8.0 = live value since 2026-07-05
      (backtest.py module default is 5.0).
Entry = maker fill at the flow_capture snapshot price of the blocking scan
(fallback: 1m candle close of the block minute). Maker entry fee 0.01%; exit
taker 0.06% on stop/trail, maker on TP/4h-hold. $10 margin x 10 lev = $100
notional (prior-study convention; live size moved $10->$15 on 7/5 — scale,
not sign, changes).

Gate ORDER matters (bot.py slot loop: OB gate FIRST, tape gate second): every
tape-blocked line already passed the OB gate that scan, but an OB-blocked
signal might ALSO have been tape-blocked had the OB gate not fired. Each
OB-blocked row is therefore tagged `tape_would_block_now` using the SAME-scan
flow snapshot under TODAY'S tape rules (MR shorts buy_ratio-exempt since 7/12,
trade_count>20 activation, soft thin-tape gate 5..20, divergence always-on)
and the aggregate is reported both raw and tape-surviving.

HONESTY CAVEATS (printed at runtime too):
  * n is SMALL in every category — screening-grade. CIs given, but forward
    shadow-tagging beats gate surgery on n<15.
  * WIDE-SPREAD TRAP: ob_spread blocks fired precisely when the spread was
    >0.15%. A maker fill at the snapshot mid/last price inside such a spread
    is OPTIMISTIC — a real resting limit may never fill, or fills exactly when
    it's adversely selected. Any "gate COSTS money" read on ob_spread is
    inflated by construction.
  * fill-all is optimistic (live maker fill rate ~27% on this slot).
  * Backtest can only REJECT, never confirm (edge-hunt-exhaustion 6/13);
    positive reads are forward-test candidates, not deploys.

Read-only w.r.t. live: touches no bot state, no restart, writes only the
--dump-json path (default: scratchpad).

Run from repo root:
    python scripts/slot_lab/gate_block_counterfactual.py
    python scripts/slot_lab/gate_block_counterfactual.py --dump-json /tmp/out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts", "slot_lab"))

import ccxt  # noqa: E402
import backtest  # noqa: E402
import mean_revert_replay as MR  # noqa: E402  (validated _build_path/_net/_boot_mean_ci/PARAMS)
from st2_lab.exit_replay import _simulate  # noqa: E402
from indicators import add_all_indicators  # noqa: E402
from strategies import bb_mean_reversion_strategy, Signal  # noqa: E402

# Live trail arm (env TRAIL_ARM_ROI=8.0 since 2026-07-05); backtest.py default is 5.0
backtest.TRAIL_ARM_ROI = 8.0

LA = ZoneInfo("America/Los_Angeles")
LOGS = [os.path.join(_BOT_DIR, "logs", f) for f in
        ("bot.log.5", "bot.log.4", "bot.log.3", "bot.log.2", "bot.log.1", "bot.log")]
FLOWCAP = os.path.join(_BOT_DIR, "logs", "flow_capture.jsonl")
SNAP_TOL_S = 150          # max |snapshot.ts - block.ts| for a price match
DEDUP_GAP_S = 900         # same (sym, side, category) within 15 min = one episode
# MR-short buy_ratio exemption deploy: 2026-07-12 7:43 PM PT (PID 20653)
EXEMPT_EPOCH = datetime(2026, 7, 12, 19, 43, tzinfo=LA).timestamp()

LINE_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[DEBUG\] \[PAPER\] \[(OB|TAPE) GATE\] "
    r"5m_mean_revert (\S+)(?: (LONG|SHORT))? blocked — (.+)$")


def categorize(gate: str, detail: str, side: str | None, ts: float) -> str:
    d = detail.lower()
    if gate == "OB":
        if "imbalance" in d:
            return "ob_imbalance"
        if "wall" in d:
            return "ob_wall"
        if "wide spread" in d:
            return "ob_spread"
        return "ob_other"
    if "buy_ratio" in d:
        if side == "LONG":
            return "tape_buy_ratio_LONG"
        return ("tape_buy_ratio_SHORT_pre712" if ts < EXEMPT_EPOCH
                else "tape_buy_ratio_SHORT_POST712_UNEXPECTED")
    if "divergence" in d:
        return "tape_divergence"
    return "tape_other"


def parse_blocks() -> list[dict]:
    rows, seen = [], set()
    for path in LOGS:
        if not os.path.exists(path):
            continue
        with open(path, errors="replace") as fh:
            for line in fh:
                m = LINE_RE.match(line.strip())
                if not m:
                    continue
                local, gate, sym, side, detail = m.groups()
                key = (local, sym, detail)
                if key in seen:      # identical line duplicated across rotations
                    continue
                seen.add(key)
                ts = datetime.strptime(local, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LA).timestamp()
                rows.append({
                    "ts": int(ts), "local_pt": local, "symbol": sym,
                    "side": side.lower() if side else None, "gate": gate,
                    "detail": detail.strip(), "src": os.path.basename(path),
                    "category": categorize(gate, detail, side, ts),
                })
    rows.sort(key=lambda r: r["ts"])
    return rows


def dedup(rows: list[dict]) -> list[dict]:
    """First block of an episode wins; later same-(sym,side,cat) blocks within
    DEDUP_GAP_S of the last kept/absorbed one are absorbed into it."""
    episodes = []
    last: dict[tuple, dict] = {}
    for r in rows:
        k = (r["symbol"], r["side"], r["category"])
        prev = last.get(k)
        if prev is not None and r["ts"] - prev["_last_ts"] <= DEDUP_GAP_S:
            prev["dup_count"] += 1
            prev["_last_ts"] = r["ts"]
            continue
        r = dict(r)
        r["dup_count"] = 0
        r["_last_ts"] = r["ts"]
        episodes.append(r)
        last[k] = r
    for e in episodes:
        e.pop("_last_ts")
    return episodes


def attach_snapshots(episodes: list[dict]) -> None:
    """Nearest flow_capture record (same symbol, |dt|<=SNAP_TOL_S) -> price/ob/flow."""
    want: dict[str, list[dict]] = {}
    for e in episodes:
        want.setdefault(e["symbol"], []).append(e)
    syms = set(want)
    best: dict[int, tuple] = {}   # id(episode) -> (abs_dt, rec)
    with open(FLOWCAP, errors="replace") as fh:
        for line in fh:
            # cheap prefilter before json parse
            if not any(s in line for s in syms):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = rec.get("symbol")
            if sym not in want:
                continue
            for e in want[sym]:
                dt = abs(rec["ts"] - e["ts"])
                if dt <= SNAP_TOL_S:
                    cur = best.get(id(e))
                    if cur is None or dt < cur[0]:
                        best[id(e)] = (dt, rec)
    for e in episodes:
        hit = best.get(id(e))
        if hit:
            dt, rec = hit
            e["snap_dt_s"] = rec["ts"] - e["ts"]
            e["snap_price"] = rec.get("price")
            e["snap_ob"] = rec.get("ob")
            e["snap_flow"] = rec.get("flow")
        else:
            e["snap_dt_s"] = None
            e["snap_price"] = None
            e["snap_ob"] = None
            e["snap_flow"] = None


def tape_would_block_now(e: dict) -> str:
    """Would TODAY'S slot tape gate (post-7/12 rules) block this signal, judged on
    the same-scan flow snapshot? Returns 'yes:<reason>' / 'no' / 'unknown'."""
    fl = e.get("snap_flow")
    side = e.get("side")
    if fl is None or side is None:
        return "unknown"
    tc = fl.get("trade_count", 0) or 0
    br = fl.get("buy_ratio", 0.5)
    div = fl.get("divergence")
    ltb = fl.get("large_trade_bias", 0.0) or 0.0
    if tc > 20:
        # buy_ratio: MR shorts exempt (2026-07-12 carve-out); longs keep the gate
        if side == "long" and br < 0.45:
            return f"yes:buy_ratio {br:.2f}<0.45"
        if side == "long" and div == "bearish":
            return "yes:bearish divergence"
        if side == "short" and div == "bullish":
            return "yes:bullish divergence"
        if side == "long" and ltb < -0.3:
            return f"yes:lt_bias {ltb:.2f}"
        if side == "short" and ltb > 0.3:
            return f"yes:lt_bias {ltb:.2f}"
        return "no"
    # thin tape: soft gate only (main-loop parity; slot loop skips gates at tc<=20)
    return "no"


_EX = None
def _exchange():
    global _EX
    if _EX is None:
        _EX = ccxt.phemex({"enableRateLimit": True})
    return _EX


def _fetch_window(sym: str, timeframe: str, since_s: int, limit: int = 500):
    """One whitelisted-limit kline call (Phemex limit whitelist {5,10,50,100,500,1000})."""
    import pandas as pd
    ex = _exchange()
    for attempt in range(4):
        try:
            batch = ex.fetch_ohlcv(sym, timeframe, since=since_s * 1000, limit=limit)
            break
        except (ccxt.RateLimitExceeded, ccxt.NetworkError) as err:
            print(f"    fetch retry {sym} {timeframe}: {err}")
            time.sleep(5 * (attempt + 1))
    else:
        return None
    if not batch:
        return None
    df = pd.DataFrame(batch, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df["ts"], unit="ms")
    return df.drop(columns=["ts"])


def recover_spread_direction(e: dict) -> None:
    """ob_spread lines log no direction. Regenerate the bb_mean_reversion signal on
    the 5m bar the scan was evaluating (completed bar preceding block ts), with a
    200-bar warmup, exactly like mean_revert_replay._regen_signals windows."""
    since = e["ts"] - (MR.WARMUP + 25) * 300
    df5 = _fetch_window(e["symbol"], "5m", since, limit=500)
    if df5 is None or len(df5) < MR.WARMUP:
        e["side_source"] = "regen_failed:no_data"
        return
    df5 = add_all_indicators(df5)
    idx_epoch = df5.index.view("int64") // 1_000_000_000
    # live evaluates the FORMING bar; the last bar fully known at block time is the
    # one whose open <= ts. Try the forming bar first (its final OHLC approximates
    # what live saw mid-bar), then the previous completed bar.
    candidates = [i for i in range(len(df5)) if idx_epoch[i] <= e["ts"]]
    if not candidates:
        e["side_source"] = "regen_failed:no_bar"
        return
    for i in (candidates[-1], candidates[-1] - 1):
        if i < MR.WARMUP:
            continue
        window = df5.iloc[i - 21:i + 1]
        ts_sig = bb_mean_reversion_strategy(window, orderbook=None)
        if ts_sig.signal != Signal.HOLD:
            e["side"] = "long" if ts_sig.signal == Signal.BUY else "short"
            e["side_source"] = f"regen@bar_open_{int(idx_epoch[i])}"
            e["regen_reason"] = ts_sig.reason
            return
    e["side_source"] = "regen_failed:HOLD_on_both_bars"


def simulate(e: dict) -> None:
    """Counterfactual maker entry at block price -> validated exit engine."""
    if e.get("side") is None:
        e["sim"] = None
        e["sim_skip"] = "no_direction"
        return
    entry_ts = e["ts"]
    df1m = _fetch_window(e["symbol"], "1m", entry_ts - 120, limit=500)  # 500m > 4h hold+slack
    if df1m is None or df1m.empty:
        e["sim"] = None
        e["sim_skip"] = "no_1m_data"
        return
    entry_px = e.get("snap_price")
    px_src = "flow_capture_snapshot"
    if entry_px is None:
        # fallback: close of the 1m bar containing the block ts
        idx_epoch = df1m.index.view("int64") // 1_000_000_000
        prior = [i for i in range(len(df1m)) if idx_epoch[i] <= entry_ts]
        if not prior:
            e["sim"] = None
            e["sim_skip"] = "no_entry_bar"
            return
        entry_px = float(df1m.iloc[prior[-1]]["close"])
        px_src = "1m_close_fallback"
    path = MR._build_path(df1m, entry_ts, MR.PARAMS["hold_secs"], e["side"])
    if not path:
        e["sim"] = None
        e["sim_skip"] = "no_forward_path"
        return
    exit_px, reason, held = _simulate(e["symbol"], e["side"], entry_px,
                                      entry_ts, path, MR.PARAMS, variant=True)
    net = MR._net(entry_px, exit_px, e["side"], reason, MR.NOTIONAL, MR.MAKER_FEE)
    e["sim"] = {
        "entry_px": entry_px, "entry_px_source": px_src,
        "exit_px": exit_px, "exit_reason": reason, "held_s": held,
        "net_usd": round(net, 4),
        "path_end_ts": path[-1]["ts"],
        "path_secs": path[-1]["ts"] - entry_ts,
    }


def summarize(episodes: list[dict], cat: str, note: str = "") -> dict:
    rows = [e for e in episodes if e["category"] == cat and e.get("sim")]
    nets = [e["sim"]["net_usd"] for e in rows]
    n = len(nets)
    out = {"category": cat, "n": n, "note": note}
    if n:
        tot = sum(nets)
        lo, hi = MR._boot_mean_ci(nets, n_boot=10000, seed=42)
        out.update({
            "net_total": round(tot, 3), "expectancy": round(tot / n, 4),
            "ci95_mean": [round(lo, 4), round(hi, 4)],
            "wins": sum(1 for x in nets if x > 0),
            "min": min(nets), "max": max(nets),
            "exit_mix": dict(Counter(e["sim"]["exit_reason"] for e in rows)),
        })
        if out["expectancy"] < 0 and hi < 0:
            out["verdict"] = "GATE SAVES MONEY (blocked cohort loses, CI excl 0)"
        elif out["expectancy"] > 0 and lo > 0:
            out["verdict"] = "GATE COSTS MONEY (blocked cohort wins, CI excl 0) — screening-grade"
        else:
            out["verdict"] = "NULL (CI straddles 0)"
    else:
        out["verdict"] = "no simulated rows"
    return out


def main():
    ap = argparse.ArgumentParser()
    default_dump = os.environ.get(
        "GATE_CF_DUMP",
        "/private/tmp/claude-501/-Users-jonaspenaso-Desktop/da6fc410-ba35-4824-9ccd-5be560c204ac/"
        "scratchpad/gate_block_counterfactual.json")
    ap.add_argument("--dump-json", default=default_dump)
    args = ap.parse_args()

    print("5m_mean_revert GATE-BLOCK counterfactual — SCREENING-GRADE")
    print(f"  exit geometry: {MR.PARAMS} | trail arm ROI {backtest.TRAIL_ARM_ROI} (live)")
    print(f"  fees: maker {MR.MAKER_FEE}%/side, taker {MR.TAKER_FEE}% on stop/trail | notional ${MR.NOTIONAL:.0f}")
    print("  CAVEATS: small-n screening; wide-spread fills OPTIMISTIC; fill-all optimistic;")
    print("  replay can only REJECT, never confirm.")

    raw = parse_blocks()
    print(f"\nraw gate lines parsed: {len(raw)}")
    episodes = dedup(raw)
    print(f"distinct episodes:     {len(episodes)}")
    print("category counts:", dict(Counter(e["category"] for e in episodes)))

    print("\nattaching flow_capture snapshots (price at block time)...")
    attach_snapshots(episodes)
    matched = sum(1 for e in episodes if e["snap_price"] is not None)
    print(f"  snapshot price matched: {matched}/{len(episodes)} (tol ±{SNAP_TOL_S}s)")

    for e in episodes:
        if e["category"] == "ob_spread" and e["side"] is None:
            print(f"  recovering direction for spread block {e['symbol']} @ {e['local_pt']} PT...")
            recover_spread_direction(e)
            print(f"    -> side={e.get('side')} ({e.get('side_source')})")

    for e in episodes:
        if e["category"].startswith("ob_"):
            e["tape_would_block_now"] = tape_would_block_now(e)

    print("\nsimulating counterfactual trades...")
    for e in episodes:
        simulate(e)
        s = e.get("sim")
        tag = (f"net ${s['net_usd']:+.3f} ({s['exit_reason']}, {s['held_s']}s, "
               f"entry {s['entry_px_source']})" if s else f"SKIP: {e.get('sim_skip')}")
        print(f"  {e['local_pt']} PT  {e['symbol']:<18} {str(e['side']).upper():<6} "
              f"{e['category']:<28} {tag}")

    cats = [
        ("ob_imbalance", "OPEN question"),
        ("ob_wall", "OPEN question"),
        ("ob_spread", "OPEN question — WIDE-SPREAD TRAP: maker fill optimistic"),
        ("tape_divergence", "OPEN question"),
        ("tape_buy_ratio_LONG", "ADJUDICATED 7/12 (blocked longs LOSE) — sanity only"),
        ("tape_buy_ratio_SHORT_pre712", "ADJUDICATED 7/12 (+$6.19, exempted) — sanity only"),
    ]
    summaries = []
    print(f"\n{'='*70}\nPER-CATEGORY COUNTERFACTUAL")
    for cat, note in cats:
        s = summarize(episodes, cat, note)
        summaries.append(s)
        print(f"\n[{cat}]  n={s['n']}   ({note})")
        if s["n"]:
            print(f"  net total ${s['net_total']:+.3f} | expectancy ${s['expectancy']:+.4f}/trade "
                  f"| CI95 [{s['ci95_mean'][0]:+.4f}, {s['ci95_mean'][1]:+.4f}]")
            print(f"  wins {s['wins']}/{s['n']} | min {s['min']:+.3f} max {s['max']:+.3f} "
                  f"| exits {s['exit_mix']}")
        print(f"  VERDICT: {s['verdict']}")

    # OB gate aggregate: raw and tape-surviving (today's rules)
    ob_all = [e for e in episodes if e["category"].startswith("ob_") and e.get("sim")]
    ob_surv = [e for e in ob_all if e.get("tape_would_block_now") == "no"]
    for label, rows in (("OB GATE AGGREGATE (all)", ob_all),
                        ("OB GATE AGGREGATE (would ALSO pass today's tape gate)", ob_surv)):
        nets = [e["sim"]["net_usd"] for e in rows]
        if nets:
            lo, hi = MR._boot_mean_ci(nets, n_boot=10000, seed=42)
            print(f"\n{label}: n={len(nets)} net ${sum(nets):+.3f} "
                  f"exp ${sum(nets)/len(nets):+.4f} CI95 [{lo:+.4f}, {hi:+.4f}]")

    dump = {
        "generated_at_pt": datetime.now(LA).strftime("%Y-%m-%d %I:%M:%S %p PT"),
        "params": {**MR.PARAMS, "trail_arm_roi": backtest.TRAIL_ARM_ROI,
                   "maker_fee": MR.MAKER_FEE, "taker_fee": MR.TAKER_FEE,
                   "notional": MR.NOTIONAL, "dedup_gap_s": DEDUP_GAP_S,
                   "snap_tol_s": SNAP_TOL_S},
        "raw_line_count": len(raw),
        "episodes": episodes,
        "summaries": summaries,
    }
    os.makedirs(os.path.dirname(args.dump_json), exist_ok=True)
    with open(args.dump_json, "w") as fh:
        json.dump(dump, fh, indent=1, default=str)
    print(f"\ndump: {args.dump_json}")


if __name__ == "__main__":
    main()
