#!/usr/bin/env python3
"""Build the htf_l2_anticipation position ledger for geometry replay.

- Source: trading_state.json (v8 duplicate EXCLUDED by construction — we only read trading_state.json)
- Excludes exit_reason == min_margin_skip (partial-fill ghosts, pnl 0, n=20) -> 215 trade records
- Merges each partial_tp half-record into its runner record -> positions
- Tags toxic cell: entry_snapshot.flow.trade_count <= 20 AND entry_snapshot.htf_adx >= 35
  (cell definition from reference_htf_l2_diagnosis_2026-07-16.md item R3-2)
Outputs positions.json
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

d = json.load(open(os.path.join(ROOT, "trading_state.json")))
h = [t for t in d["closed_trades"] if t.get("strategy") == "htf_l2_anticipation"]
assert len(h) == 235, len(h)
h = [t for t in h if t.get("exit_reason") != "min_margin_skip"]
assert len(h) == 215, len(h)

partials = [t for t in h if t.get("exit_reason") == "partial_tp"]
others = [t for t in h if t.get("exit_reason") != "partial_tp"]

positions = []
used = set()
for t in others:
    pos = {
        "symbol": t["symbol"], "side": t["side"], "entry": t["entry"],
        "amount": t["amount"], "margin": t["margin"],
        "opened_at": t["opened_at"], "closed_at": t["closed_at"],
        "exit_price": t.get("exit_price", t["exit"]),
        "exit_reason": t.get("exit_reason", t.get("reason")),
        "actual_pnl_usdt": t["pnl_usdt"],
        "actual_fees": t.get("fees_usdt"),
        "actual_net": t.get("net_pnl", t["pnl_usdt"] - (t.get("fees_usdt") or 0)),
        "partial": None,
    }
    if t.get("scaled_out"):
        # find its partial half
        m = [p for i, p in enumerate(partials)
             if i not in used and p["symbol"] == t["symbol"]
             and abs(p["opened_at"] - t["opened_at"]) < 5
             and abs(p["entry"] - t["entry"]) / t["entry"] < 1e-6]
        assert len(m) == 1, (t["symbol"], len(m))
        p = m[0]
        used.add(partials.index(p))
        pos["amount"] = t["amount"] + p["amount"]
        pos["margin"] = t["margin"] + p["margin"]
        pos["actual_pnl_usdt"] += p["pnl_usdt"]
        pos["actual_fees"] = (pos["actual_fees"] or 0) + (p.get("fees_usdt") or 0)
        pos["actual_net"] += p.get("net_pnl", p["pnl_usdt"] - (p.get("fees_usdt") or 0))
        pos["partial"] = {"exit_price": p.get("exit_price", p["exit"]), "closed_at": p["closed_at"]}
    snap = t.get("entry_snapshot") or {}
    tc = (snap.get("flow") or {}).get("trade_count")
    adx = snap.get("htf_adx")
    pos["trade_count"] = tc
    pos["htf_adx"] = adx
    pos["toxic"] = (tc is not None and adx is not None and tc <= 20 and adx >= 35)
    positions.append(pos)

assert len(used) == len(partials) == 10, (len(used), len(partials))
print("positions:", len(positions))
print("toxic positions:", sum(1 for p in positions if p["toxic"]))
print("sum actual_net (should be close to -26.81 minus nothing):",
      round(sum(p["actual_net"] for p in positions), 2))
json.dump(positions, open(os.path.join(HERE, "positions.json"), "w"), indent=1)
