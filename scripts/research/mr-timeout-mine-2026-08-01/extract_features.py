#!/usr/bin/env python3
"""Extract entry-time features for all closed 5m_mean_revert trades.

Read-only: reads trading_state_5m_mean_revert.json, writes trades_features.json
into this research dir. Eras labeled separately (paper = mode None, pre 6/12
promotion; live = mode 'live').
"""
import json, datetime, os
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
STATE = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state_5m_mean_revert.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades_features.json")

d = json.load(open(STATE))
ct = d["closed_trades"]

rows = []
for i, t in enumerate(ct):
    era = "live" if t.get("mode") == "live" else "paper"
    er = t["exit_reason"]
    if er == "min_margin_skip":
        group = "excluded"   # zero-duration non-trade
    elif er == "hard_time_exit":
        group = "timeout"
    elif er in ("take_profit", "stop_loss", "exchange_close"):
        group = "priced"
    elif er == "adverse_exit":
        group = "adverse"    # early cut, neither TP/SL nor timeout
    else:
        group = "other"

    snap = t.get("entry_snapshot") or {}
    ob = snap.get("ob") or {}
    flow = snap.get("flow") or {}
    reg = snap.get("regime") or {}
    side = t["side"]
    sgn = 1 if side == "long" else -1

    def aligned(v, center=0.0):
        # signed feature aligned with trade side: + = supports the trade direction
        if v is None:
            return None
        return sgn * (v - center)

    opened = datetime.datetime.fromtimestamp(t["opened_at"], PT)
    row = {
        "idx": i,
        "era": era,
        "group": group,
        "exit_reason": er,
        "symbol": t["symbol"].split("/")[0],
        "side": side,
        "opened_pt": opened.strftime("%Y-%m-%d %I:%M %p"),
        "hour_pt": opened.hour,
        "duration_h": t["duration_s"] / 3600.0,
        "pnl_usdt": t["pnl_usdt"],
        "net_pnl": t.get("net_pnl"),
        "margin": t["margin"],
        "entry_strength": t.get("entry_strength"),
        "has_snapshot": bool(snap),
        # raw snapshot features
        "ob_imbalance": ob.get("imbalance"),
        "ob_imbalance_aligned": aligned(ob.get("imbalance")),
        "bid_walls": ob.get("bid_walls"),
        "ask_walls": ob.get("ask_walls"),
        "spread_pct": ob.get("spread_pct"),
        "buy_ratio": flow.get("buy_ratio"),
        "buy_ratio_aligned": aligned(flow.get("buy_ratio"), 0.5),
        "cvd_slope": flow.get("cvd_slope"),
        "cvd_slope_aligned": aligned(flow.get("cvd_slope")),
        "large_trade_bias": flow.get("large_trade_bias"),
        "large_trade_bias_aligned": aligned(flow.get("large_trade_bias"), 0.5),
        "trade_count": flow.get("trade_count"),
        "divergence": flow.get("divergence"),
        "regime_label": reg.get("label"),
        "adx": reg.get("adx"),
        "atr_pct": reg.get("atr_pct"),
        "vol_ratio": reg.get("vol_ratio"),
        "above_ema200": reg.get("above_ema200"),
        "ema_stack_bull": reg.get("ema_stack_bull"),
        "ema_stack_bear": reg.get("ema_stack_bear"),
        "htf_adx": snap.get("htf_adx"),
        # F7 telemetry (live era, added ~7/17 — sparse)
        "rsi": snap.get("rsi"),
        "rsi_fast": snap.get("rsi_fast"),
        "ema21_dist_pct": snap.get("ema21_dist_pct"),
        "ema50_dist_pct": snap.get("ema50_dist_pct"),
        "vwap_dist_pct": snap.get("vwap_dist_pct"),
        "gate_tags": t.get("gate_tags"),
    }
    rows.append(row)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"wrote {len(rows)} rows -> {OUT}")
from collections import Counter
print("era x group:", Counter((r["era"], r["group"]) for r in rows))
print("no-snapshot idx:", [r["idx"] for r in rows if not r["has_snapshot"]])
