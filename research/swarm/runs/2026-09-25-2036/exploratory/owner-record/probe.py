"""EXPLORATORY PROBE (owner-record lens, run 2026-09-25-2036) -- not a screen, not evidence.
Reads research/swarm/kb/owner_trades/api_closed_pnl.json (+ deposit/withdraw lists if present).
Timestamps in openedTimeNs/updatedTimeNs are milliseconds despite the field name (1648275092166 -> 2022-03-26).
USD = *Ev / 1e4 (SOURCES.md s.2b)."""
import json, statistics as st, collections, datetime as dt
from pathlib import Path
import numpy as np
import sys
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))
from research.swarm.lib import bootstrap_ci

KB = ROOT / "research/swarm/kb/owner_trades"
OUT = ROOT / "research/swarm/runs/2026-09-25-2036/theses/owner_record_probe.json"
rows = json.load(open(KB / "api_closed_pnl.json"))
def ts(r, k): return dt.datetime.fromtimestamp(int(r[k]) / 1e3, dt.timezone.utc)
T = []
for r in rows:
    T.append(dict(sym=r["symbol"], side=r["side"], size=float(r["closedSize"]), lev=r["leverage"],
                  pnl=int(r["realizedPnlEv"]) / 1e4, gross=int(r["closedPnlEv"]) / 1e4,
                  fee=int(r["exchangeFeeEv"]) / 1e4, fund=int(r["fundingFeeEv"]) / 1e4,
                  op=ts(r, "openedTimeNs"), cl=ts(r, "updatedTimeNs"),
                  openp=int(r["openPriceEp"]), closep=int(r["closePriceEp"])))
T.sort(key=lambda t: t["op"])
F = "api_closed_pnl.json"
def summ(ts_):
    p = [t["pnl"] for t in ts_]
    w = [x for x in p if x > 0]; l = [x for x in p if x < 0]
    out = dict(n=len(p), sum_usd=round(sum(p), 2), n_wins=len(w), n_losses=len(l),
               win_rate=round(len(w) / len(p), 4) if p else None,
               avg_win=round(st.mean(w), 2) if w else None, avg_loss=round(st.mean(l), 2) if l else None,
               payoff_ratio=round(st.mean(w) / -st.mean(l), 3) if w and l else None,
               field=f"realizedPnlEv/1e4 ({F})")
    if len(p) >= 2:
        lo, hi = bootstrap_ci.mean_ci(p); out["mean_usd_ci95_bootstrap_ci.mean_ci"] = [round(lo, 3), round(hi, 3)]
    return out
res = {"_label": "EXPLORATORY PROBE -- not a screen, not evidence for any thesis verdict",
       "script": "research/swarm/runs/2026-09-25-2036/exploratory/owner-record/probe.py",
       "source_file": f"research/swarm/kb/owner_trades/{F}", "n_rows": len(T),
       "date_range_utc": [T[0]["op"].isoformat(), T[-1]["cl"].isoformat()],
       "timestamp_note": "openedTimeNs/updatedTimeNs are ms-epoch values despite the Ns suffix"}
# equity path
dep = KB / "api_deposit_list_full.json"; wd = KB / "api_withdraw_list_full.json"
res["deposit_file_present"] = dep.exists(); res["withdraw_file_present"] = wd.exists()
if dep.exists() and wd.exists():
    D = json.load(open(dep)); W = json.load(open(wd))
    t0, t1 = T[0]["op"].timestamp() * 1e3 - 86400e3, T[-1]["cl"].timestamp() * 1e3
    inwin = lambda x: t0 <= int(x.get("createdAt") or x.get("submittedAt")) <= t1
    res["cash_flows_in_window"] = {
        "deposits_by_currency_count": dict(collections.Counter(x["currency"] for x in D if inwin(x))),
        "withdrawals_by_currency_count": dict(collections.Counter(x["currency"] for x in W if inwin(x) and x.get("status") == "Succeed")),
        "note": "flows are coin-denominated (XRP/ADA/MATIC/USDT...), no USD value field and no historical price source in the research stage; a true USD equity path cannot be built without fabricating conversion rates -> fallback to cumulative realized PnL (task fallback)."}
cum = np.cumsum([t["pnl"] for t in T])
res["equity_path_method"] = "cumulative_realized_pnl (realizedPnlEv/1e4)"
res["cum_realized_pnl_final_usd"] = round(float(cum[-1]), 2)
res["cum_realized_pnl_min_usd"] = [round(float(cum.min()), 2), T[int(cum.argmin())]["cl"].isoformat()]
res["cum_realized_pnl_max_usd"] = [round(float(cum.max()), 2), T[int(cum.argmax())]["cl"].isoformat()]
res["cum_path_every_100th"] = [[T[i]["cl"].isoformat(), round(float(cum[i]), 2)] for i in range(0, len(T), 100)] + [[T[-1]["cl"].isoformat(), round(float(cum[-1]), 2)]]
# concentration
pos = sorted([t for t in T if t["pnl"] > 0], key=lambda t: -t["pnl"]); tp = sum(t["pnl"] for t in pos)
res["concentration"] = {"total_positive_pnl_usd": round(tp, 2),
    "largest_trade": {"usd": pos[0]["pnl"], "sym": pos[0]["sym"], "opened": pos[0]["op"].isoformat(), "share": round(pos[0]["pnl"] / tp, 4)},
    "top5_usd": round(sum(t["pnl"] for t in pos[:5]), 2), "top5_share": round(sum(t["pnl"] for t in pos[:5]) / tp, 4),
    "top5_symbols": [t["sym"] for t in pos[:5]], "field": f"realizedPnlEv/1e4 ({F})"}
res["all_trades"] = summ(T)
hold = [(t["cl"] - t["op"]).total_seconds() for t in T]
res["median_hold_seconds"] = st.median(hold); res["hold_field"] = "updatedTimeNs - openedTimeNs"
# symbols
bs = collections.defaultdict(list)
for t in T: bs[t["sym"]].append(t)
res["by_symbol"] = {s: {"n": len(v), "sum_usd": round(sum(x["pnl"] for x in v), 2)} for s, v in sorted(bs.items(), key=lambda kv: -len(kv[1]))}
res["by_side"] = {("1_buy_long" if s == "1" else "2_sell_short"): summ([t for t in T if t["side"] == s]) for s in ("1", "2")}
# TRYB decomposition
tr = [t for t in T if t["sym"] == "u100TRYBUSD"]; ex = [t for t in T if t["sym"] != "u100TRYBUSD"]
res["u100TRYBUSD_episode"] = summ(tr) | {
    "first_open": tr[0]["op"].isoformat(), "last_close": tr[-1]["cl"].isoformat(),
    "open_price_Ep_range": [min(t["openp"] for t in tr), max(t["openp"] for t in tr)],
    "long_entries_open_price_Ep_median": st.median([t["openp"] for t in tr if t["side"] == "1"]),
    "short_entries_open_price_Ep_median": st.median([t["openp"] for t in tr if t["side"] == "2"]),
    "note": "Ep prices ~53,500 = 0.0535 USD per TRY (priceScale 1e6 inferred from pnl recompute not performed; relative levels only). Longs opened near/below ~0.050-0.054, shorts opened near ~0.069-0.087 -> buy low / sell high oscillation around a fiat-anchored level"}
res["ex_TRYB"] = summ(ex)
res["ex_TRYB_by_side"] = {("1_buy_long" if s == "1" else "2_sell_short"): summ([t for t in ex if t["side"] == s]) for s in ("1", "2")}
res["ex_TRYB_median_hold_seconds"] = st.median([(t["cl"] - t["op"]).total_seconds() for t in ex])
hb = {"<5m": (0, 300), "5m-1h": (300, 3600), "1h-8h": (3600, 28800), "8h-3d": (28800, 259200), ">3d": (259200, 1e12)}
res["ex_TRYB_by_hold"] = {k: summ([t for t in ex if a <= (t["cl"] - t["op"]).total_seconds() < b]) for k, (a, b) in hb.items()}
res["ex_TRYB_fees_usd"] = round(sum(t["fee"] for t in ex), 2); res["ex_TRYB_gross_closedPnl_usd"] = round(sum(t["gross"] for t in ex), 2)
res["ex_TRYB_funding_usd"] = round(sum(t["fund"] for t in ex), 2)
res["fee_field"] = "exchangeFeeEv/1e4, closedPnlEv/1e4, fundingFeeEv/1e4"
# time of day (UTC hour of open), ex-TRYB
hod = collections.defaultdict(list)
for t in ex: hod[t["op"].hour].append(t["pnl"])
res["ex_TRYB_by_open_hour_utc"] = {h: {"n": len(v), "sum_usd": round(sum(v), 2)} for h, v in sorted(hod.items())}
# behaviour after a loss (consecutive trades by open time, all symbols)
after = collections.Counter(); sz = {"after_loss": [], "after_win": []}; hl = {"after_loss": [], "after_win": []}; np_ = {"after_loss": [], "after_win": []}
for a, b in zip(T, T[1:]):
    k = "after_loss" if a["pnl"] < 0 else "after_win"
    after[(k, "same_side" if a["side"] == b["side"] else "flip_side")] += 1
    after[(k, "same_symbol" if a["sym"] == b["sym"] else "other_symbol")] += 1
    if a["sym"] == b["sym"] and a["size"] > 0: sz[k].append(b["size"] / a["size"])
    hl[k].append((b["cl"] - b["op"]).total_seconds()); np_[k].append(b["pnl"])
res["behaviour_after_loss_vs_win"] = {
    "counts": {f"{k[0]}|{k[1]}": v for k, v in sorted(after.items())},
    "next_size_ratio_same_symbol_median": {k: (round(st.median(v), 3) if v else None) for k, v in sz.items()},
    "next_hold_median_seconds": {k: st.median(v) for k, v in hl.items()},
    "next_trade_pnl": {k: summ([{"pnl": x} for x in v]) for k, v in np_.items()},
    "gap_to_next_open_median_seconds": {k: st.median([(b["op"] - a["cl"]).total_seconds() for a, b in zip(T, T[1:]) if (a["pnl"] < 0) == (k == "after_loss")]) for k in ("after_loss", "after_win")},
    "field": "consecutive rows by openedTimeNs; size=closedSize; pnl=realizedPnlEv/1e4"}
json.dump(res, open(OUT, "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
