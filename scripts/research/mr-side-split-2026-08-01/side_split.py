#!/usr/bin/env python3
"""5m_mean_revert long-vs-short side split. READ-ONLY analysis.

Net convention (verified in risk_manager.py close_position, lines ~700-764):
  - net_pnl = gross_pnl - fees_usdt - funding_usdt in BOTH modes.
  - Paper additionally folds sim fees into pnl_usdt (line 731), so paper
    pnl_usdt == net_pnl. Live pnl_usdt is gross.
  - 3 oldest paper trades (Mar/early-Apr) predate fee sim: no fees_usdt or
    net_pnl key -> net taken as pnl_usdt (no fee was ever modeled).
Rule used here: net = t['net_pnl'] if present else t['pnl_usdt'].

Era split: mode == 'live' (post 6/12 promotion, promoted_at=1781269364 in
trading_state_5m_mean_revert_mode.json) vs no mode key = pre-promotion paper.

Bootstrap: house rule — resample each side independently, compute the diff
per replicate, then take percentiles of the DIFF distribution. Never sort
sides first.
"""
import json, random, datetime, statistics as st

STATE = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state_5m_mean_revert.json"
OUT   = "/Users/jonaspenaso/Desktop/Phmex-S/scripts/research/mr-side-split-2026-08-01/results.json"

d = json.load(open(STATE))
trades = d["closed_trades"]

def net(t):
    return t["net_pnl"] if "net_pnl" in t else t["pnl_usdt"]

def era(t):
    return "live" if t.get("mode") == "live" else "paper_pre_promotion"

def side_stats(rows):
    if not rows:
        return {"n": 0}
    nets = [net(t) for t in rows]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    reasons = {}
    for t in rows:
        r = t.get("exit_reason") or t.get("reason")
        reasons[r] = reasons.get(r, 0) + 1
    return {
        "n": len(rows),
        "wins": len(wins),
        "wr_pct": round(100 * len(wins) / len(rows), 1),
        "net_total": round(sum(nets), 4),
        "net_per_trade": round(sum(nets) / len(rows), 4),
        "avg_win": round(st.mean(wins), 4) if wins else None,
        "avg_loss": round(st.mean(losses), 4) if losses else None,
        "worst": round(min(nets), 4),
        "best": round(max(nets), 4),
        "exit_reasons": reasons,
        "trades": [
            {
                "closed": datetime.datetime.fromtimestamp(t["closed_at"]).strftime("%Y-%m-%d %H:%M"),
                "symbol": t["symbol"].split("/")[0],
                "reason": t.get("exit_reason") or t.get("reason"),
                "net": round(net(t), 4),
            }
            for t in sorted(rows, key=lambda x: x["closed_at"])
        ],
    }

def bootstrap_diff_ci(longs, shorts, n_boot=20000, seed=42):
    """Resample each side independently per replicate; diff = mean(long)-mean(short);
    CI from percentiles of the diff distribution (house bootstrap-diff-CI rule)."""
    rng = random.Random(seed)
    ln = [net(t) for t in longs]
    sn = [net(t) for t in shorts]
    diffs = []
    for _ in range(n_boot):
        lb = [rng.choice(ln) for _ in ln]
        sb = [rng.choice(sn) for _ in sn]
        diffs.append(sum(lb) / len(lb) - sum(sb) / len(sb))
    diffs.sort()
    def pct(p):
        return diffs[min(len(diffs) - 1, max(0, int(p * len(diffs))))]
    return {
        "point_diff_long_minus_short": round(sum(ln) / len(ln) - sum(sn) / len(sn), 4),
        "ci95": [round(pct(0.025), 4), round(pct(0.975), 4)],
        "ci90": [round(pct(0.05), 4), round(pct(0.95), 4)],
        "frac_diff_below_zero": round(sum(1 for x in diffs if x < 0) / len(diffs), 4),
        "n_boot": n_boot,
        "seed": seed,
    }

results = {"state_file": STATE, "n_closed_total": len(trades), "eras": {}}
for e in ("live", "paper_pre_promotion"):
    rows = [t for t in trades if era(t) == e]
    longs = [t for t in rows if t["side"] == "long"]
    shorts = [t for t in rows if t["side"] == "short"]
    block = {
        "n": len(rows),
        "net_total": round(sum(net(t) for t in rows), 4),
        "long": side_stats(longs),
        "short": side_stats(shorts),
    }
    if longs and shorts:
        block["bootstrap_diff"] = bootstrap_diff_ci(longs, shorts)
    results["eras"][e] = block

# combined (secondary)
longs = [t for t in trades if t["side"] == "long"]
shorts = [t for t in trades if t["side"] == "short"]
results["combined_all_eras"] = {
    "long": side_stats(longs), "short": side_stats(shorts),
    "bootstrap_diff": bootstrap_diff_ci(longs, shorts),
}
# drop per-trade lists from combined to keep file small
for s in ("long", "short"):
    results["combined_all_eras"][s].pop("trades", None)

json.dump(results, open(OUT, "w"), indent=1)
print(json.dumps(results, indent=1, default=str))
