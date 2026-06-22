#!/usr/bin/env python3
"""ST2.0 entry-filter simulator — BOTH-SIDED, on the REAL live trades.

The trail exit-replay (exit_replay.py) proved the EXIT is inert — ST2.0's bleed is
an ENTRY/fill problem (adversely-selected maker fills; see
reference_st2_execution_research + the 2026-06-22 post-fill drift finding). This
asks the entry-side question on real money: if ST2.0 had SKIPPED entries matching a
veto, what happens to net / win-rate / the big (<=-12% ROI) stop-outs — and HOW MANY
WINNERS does the same veto also kill?

It scores each candidate veto both-sided, like exit_replay: a filter that "removes
losers" is worthless if it removes as many winners. OFFLINE only — reads
trading_state_ST2.0.json; no bot import, no trading.

HONESTY (printed at runtime): n=30 real trades is UNDERPOWERED. The lab's own
diagnostics.analyze_failures requires keep>=20 AND veto>=10 and returns nothing at
this n — consistent with gate_quantify (NULL: no entry gate yet separates W/L with
significance). Treat every result as DIRECTIONAL, in-sample, overfit-prone. A filter
earns live only via forward paper-confirm, never this in-sample table.

Entry features available historically: flow only (buy_ratio, cvd_slope,
large_trade_bias, trade_count, divergence). `imbalance` is ob:null on the closed
trades (the ob fix only populates NEW trades) -> unusable as a backtest veto.

Run from repo root:
    python scripts/st2_lab/entry_filter_sim.py
"""
from __future__ import annotations

import json
import os

try:
    from . import config as C
    from . import real_trades
except ImportError:  # run directly as a file
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from st2_lab import config as C            # type: ignore
    from st2_lab import real_trades            # type: ignore

BIG_LOSS_PCT = -11.5   # ROI threshold for a "big" stop-out loser (full ~-12% SL)


def load_records() -> list[dict]:
    """Real live ST2.0 records: feature projection (from real_trades) + pnl_pct +
    symbol attached from the raw state (1:1 — every closed live trade has a snapshot)."""
    recs = real_trades.load_real_trades()
    state = os.path.join(C.BOT_DIR, "trading_state_ST2.0.json")
    ct = [t for t in json.load(open(state)).get("closed_trades", []) if t.get("mode") == "live"]
    ct = [t for t in ct if isinstance(t.get("entry_snapshot"), dict)]
    for r, t in zip(recs, ct):
        r["pnl_pct"] = float(t.get("pnl_pct") or 0)
        r["symbol"] = (t.get("symbol") or "").split("/")[0]
    return recs


def evaluate(recs: list[dict], keep_pred, label: str) -> dict:
    """Apply keep_pred (True = take the trade). Report both-sided impact."""
    kept = [r for r in recs if keep_pred(r)]
    removed = [r for r in recs if not keep_pred(r)]
    n = len(recs)

    def net(rs):   return sum(r["net"] for r in rs)
    def wins(rs):  return sum(1 for r in rs if r["net"] > 0)
    def big(rs):   return [r for r in rs if r["pnl_pct"] <= BIG_LOSS_PCT]

    rem_winners = [r for r in removed if r["net"] > 0]
    rem_losers = [r for r in removed if r["net"] < 0]
    return {
        "label": label,
        "kept_n": len(kept), "removed_n": len(removed),
        "net_before": round(net(recs), 3), "net_after": round(net(kept), 3),
        "net_delta": round(net(recs) - net(kept), 3) * -1,  # after - before
        "exp_before": round(net(recs) / n, 4) if n else 0,
        "exp_after": round(net(kept) / len(kept), 4) if kept else 0,
        "wr_before": round(wins(recs) / n * 100, 0) if n else 0,
        "wr_after": round(wins(kept) / len(kept) * 100, 0) if kept else 0,
        "big_before": len(big(recs)), "big_after": len(big(kept)),
        "removed_winners": len(rem_winners), "removed_losers": len(rem_losers),
        "saved_on_losers": round(-net(rem_losers), 3),   # $ NOT lost (losers skipped)
        "given_up_winners": round(net(rem_winners), 3),  # $ forgone (winners skipped)
    }


def fmt(r: dict) -> str:
    return (
        f"{r['label']}\n"
        f"  kept {r['kept_n']}/{r['kept_n']+r['removed_n']}  (removed {r['removed_n']}: "
        f"{r['removed_losers']} losers / {r['removed_winners']} winners)\n"
        f"  net   ${r['net_before']:+.3f} -> ${r['net_after']:+.3f}   (delta ${r['net_delta']:+.3f})\n"
        f"  exp   ${r['exp_before']:+.4f} -> ${r['exp_after']:+.4f}/trade   |  "
        f"WR {r['wr_before']:.0f}% -> {r['wr_after']:.0f}%\n"
        f"  big losers (<= {BIG_LOSS_PCT:.0f}% ROI):  {r['big_before']} -> {r['big_after']}\n"
        f"  both-sided:  saved on skipped losers ${r['saved_on_losers']:+.3f}  |  "
        f"given up on skipped winners ${r['given_up_winners']:+.3f}"
    )


# Candidate vetoes — single-feature, research-grounded, NOT tuned to the 4 losers.
# trade_count is the only feature with real W/L separation (winners ~61 vs losers
# ~131) AND it is corroborated by reference_st2_execution_research ("losers entered
# busier tape"). large_trade_bias is a secondary (winners showed higher conviction).
CANDIDATES = [
    ("busy-tape veto: keep trade_count <= 80",  lambda r: r["trade_count"] <= 80),
    ("busy-tape veto: keep trade_count <= 100", lambda r: r["trade_count"] <= 100),
    ("busy-tape veto: keep trade_count <= 120", lambda r: r["trade_count"] <= 120),
    ("low-conviction veto: keep large_trade_bias >= 0.10", lambda r: r["large_trade_bias"] >= 0.10),
    ("combo (overfit-prone): tc<=100 AND ltb>=0.0",
     lambda r: r["trade_count"] <= 100 and r["large_trade_bias"] >= 0.0),
]


def main():
    recs = load_records()
    n = len(recs)
    print("ST2.0 ENTRY-FILTER simulator — BOTH-SIDED (real live trades)")
    print(f"  n={n} real live trades | UNDERPOWERED + in-sample — DIRECTIONAL only.")
    print(f"  imbalance unusable (ob:null historically); flow features only.\n")
    base = evaluate(recs, lambda r: True, "BASELINE (no filter)")
    print(fmt(base))
    for label, pred in CANDIDATES:
        print("\n" + fmt(evaluate(recs, pred, label)))
    print("\n--- verdict guidance ---")
    print("  Prefer a veto where saved-on-losers clearly exceeds given-up-on-winners AND")
    print("  it removes >=1 big loser. Then forward paper-confirm before any live arm —")
    print("  NEVER arm on this in-sample table (gate_quantify NULL; n=30).")


if __name__ == "__main__":
    main()
