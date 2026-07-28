"""Bonus diagnostic: were our REAL historical trades' outcomes related to
S/R zone proximity at entry? Report-only; never a verdict input (spec §3)."""
import json
import math
import pandas as pd
from fetch_data import load_candles, _slug
from sr_levels import atr, validated_zones
import os


def mann_whitney_u(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 5 or n2 < 5:
        return float("nan"), 1.0
    allv = sorted((v, 0) for v in a) + sorted((v, 1) for v in b)
    allv.sort(key=lambda x: x[0])
    # midranks with ties
    ranks, i = {}, 0
    vals = [v for v, _ in allv]
    r = [0.0] * len(vals)
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        mid = (i + j) / 2 + 1
        for k2 in range(i, j + 1):
            r[k2] = mid
        i = j + 1
    r1 = sum(r[k] for k in range(len(allv)) if allv[k][1] == 0)
    u = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    # tie-corrected variance
    from collections import Counter
    tie = sum(c**3 - c for c in Counter(vals).values())
    n = n1 + n2
    var = n1 * n2 / 12 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        return u, 1.0
    z = (u - mu) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return u, p


def zone_proximity_report(state_path: str, data_dir: str = "data") -> dict:
    trades = json.load(open(state_path)).get("closed_trades", [])
    win_d, loss_d, excluded = [], [], 0
    for t in trades:
        sym = t.get("symbol")
        f = os.path.join(data_dir, f"{_slug(sym)}_1h.csv") if sym else None
        if not sym or not f or not os.path.exists(f):
            excluded += 1
            continue
        df1h = load_candles(sym, "1h", data_dir=data_dir)
        opened = (t.get("opened_at") or 0) * 1000
        ctx = df1h[df1h["ts"] + 3_600_000 <= opened].tail(500).reset_index(drop=True)
        if len(ctx) < 100:
            excluded += 1
            continue
        zones = validated_zones(ctx)
        entry = t.get("entry_price") or t.get("entry") or 0
        a = float(atr(ctx).iloc[-1])
        side = t.get("side", "long")
        if side == "long":
            opp = [z["lo"] for z in zones if z["side"] == "resistance" and z["lo"] > entry]
            d = (min(opp) - entry) / a if opp and a > 0 else float("inf")
        else:
            opp = [z["hi"] for z in zones if z["side"] == "support" and z["hi"] < entry]
            d = (entry - max(opp)) / a if opp and a > 0 else float("inf")
        if math.isinf(d):
            excluded += 1
            continue
        n = t.get("net_pnl")
        n = n if n is not None else t.get("pnl_usdt", 0) or 0
        (win_d if n > 0 else loss_d).append(d)
    u, p = mann_whitney_u(win_d, loss_d)
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else float("nan")
    return {"n_win": len(win_d), "n_loss": len(loss_d),
            "median_win_dist": med(win_d), "median_loss_dist": med(loss_d),
            "U": u, "p": p, "excluded": excluded}
