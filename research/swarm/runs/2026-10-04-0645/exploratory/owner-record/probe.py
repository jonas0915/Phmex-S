"""EXPLORATORY PROBE (owner-record lens, run 2026-10-04-0645). NOT a screen, NOT evidence.
Reads only research/swarm/kb/owner_trades/*.json (owner's 2022-23 inverse-contract record).
No price/time-series market data is read. Writes:
  research/swarm/runs/2026-10-04-0645/exploratory/owner-record/owner_record_probe.json  (canonical, LESSONS 2026-09-27)
  research/swarm/runs/2026-10-04-0645/theses/owner_record_probe.json                   (copy; task-mandated path)
Command: cd /Users/jonaspenaso/Desktop/Phmex-S && PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 research/swarm/runs/2026-10-04-0645/exploratory/owner-record/probe.py
"""
import json, collections
from pathlib import Path
import numpy as np, pandas as pd
from research.swarm.lib import bootstrap_ci

ROOT = Path("/Users/jonaspenaso/Desktop/Phmex-S")
KB = ROOT / "research/swarm/kb/owner_trades"
RUN = ROOT / "research/swarm/runs/2026-10-04-0645"
SRC = "research/swarm/kb/owner_trades/api_closed_pnl.json"

df = pd.DataFrame(json.load(open(KB / "api_closed_pnl.json")))
num = ["closedSize", "cumEntryValueEv", "closedPnlEv", "exchangeFeeEv", "fundingFeeEv", "realizedPnlEv",
       "openedTimeNs", "updatedTimeNs", "openPriceEp", "closePriceEp", "leverage", "side"]
for c in num:
    df[c] = pd.to_numeric(df[c], errors="coerce")
# openedTimeNs/updatedTimeNs hold ms epochs despite the name (1648275092166 -> 2022-03-26)
df["opened"] = pd.to_datetime(df.openedTimeNs, unit="ms", utc=True)
df["closed"] = pd.to_datetime(df.updatedTimeNs, unit="ms", utc=True)
df["pnl"] = df.realizedPnlEv / 1e4
df["gross"] = df.closedPnlEv / 1e4
df["fee"] = df.exchangeFeeEv / 1e4
df["fund"] = df.fundingFeeEv / 1e4
df["hold_s"] = (df.updatedTimeNs - df.openedTimeNs) / 1e3
df["px_move_bps"] = (df.closePriceEp / df.openPriceEp - 1) * 1e4
df["dir_move_bps"] = np.where(df.side == 1, df.px_move_bps, -df.px_move_bps)
df = df.sort_values("closed").reset_index(drop=True)
r2 = lambda x: round(float(x), 4)

out = {"_label": "EXPLORATORY PROBE - not a screen, not a thesis, not evidence for any verdict",
       "source_file": SRC, "n_rows": int(len(df)),
       "fields_used": "realizedPnlEv, closedPnlEv, exchangeFeeEv, fundingFeeEv (/1e4 = USD); openedTimeNs, updatedTimeNs (ms epochs); side (1=Buy/long, 2=Sell/short); closedSize; leverage; openPriceEp, closePriceEp; symbol",
       "date_range_utc": [str(df.opened.min()), str(df.closed.max())]}

# --- equity path ---
dep_p, wd_p = KB / "api_deposit_list_full.json", KB / "api_withdraw_list_full.json"
dep = json.load(open(dep_p)) if dep_p.exists() else None
wd = json.load(open(wd_p)) if wd_p.exists() else None
df["cum_realized"] = df.pnl.cumsum()
eq = {"method": "cumulative realized PnL (sum realizedPnlEv/1e4 by updatedTimeNs). Deposit/withdraw files ARE present but are mixed-currency "
                "(amountEv/1e8 native coin units, no USD value field) and no 2022 price source is in-stage, so a USD equity line is not built "
                "(would require inventing FX rates). Native-unit flows inside the trading window are reported instead.",
      "final_cum_realized_usd": r2(df.cum_realized.iloc[-1]),
      "min_cum_realized_usd": r2(df.cum_realized.min()), "min_at": str(df.closed.iloc[int(df.cum_realized.idxmin())]),
      "max_cum_realized_usd": r2(df.cum_realized.max()), "max_at": str(df.closed.iloc[int(df.cum_realized.idxmax())]),
      "monthly_realized_usd": {k: r2(v) for k, v in df.groupby(df.closed.dt.strftime("%Y-%m")).pnl.sum().items()},
      "field": "realizedPnlEv/1e4, updatedTimeNs"}
if dep is not None and wd is not None:
    lo, hi = df.opened.min().value // 10**6 - 86400000 * 7, df.closed.max().value // 10**6
    def flows(lst):
        c = collections.defaultdict(float); n = collections.Counter()
        for r in lst:
            t = int(r.get("createdAt") or r.get("submittedAt") or 0)  # deposits: createdAt; withdrawals: submittedAt
            if lo <= t <= hi and str(r.get("status")) in ("Success", "Succeed"):
                c[r["currency"]] += int(r["amountEv"]) / 1e8; n[r["currency"]] += 1
        return {k: {"amount_native": round(v, 4), "n": n[k]} for k, v in c.items()}
    eq["deposit_file_rows"], eq["withdraw_file_rows"] = len(dep), len(wd)
    eq["flows_in_window_native_units"] = {"deposits": flows(dep), "withdrawals": flows(wd),
                                          "window": "first open minus 7d .. last close", "field": "amountEv/1e8, createdAt (deposits) / submittedAt (withdrawals), status"}
    # withdrawals clustered around the peak
    peak = df.closed.iloc[int(df.cum_realized.idxmax())]
    near = [r for r in wd if abs(int(r.get("submittedAt") or 0) - peak.value // 10**6) <= 3 * 86400000]
    eq["withdrawals_within_3d_of_peak"] = [{"currency": r["currency"], "amount_native": int(r["amountEv"]) / 1e8, "status": r.get("status"),
                                            "submittedAt_utc": str(pd.to_datetime(int(r["submittedAt"]), unit="ms", utc=True))} for r in near]
out["equity_path"] = eq

# --- concentration ---
pos = df[df.pnl > 0].sort_values("pnl", ascending=False)
tp = float(pos.pnl.sum())
out["concentration"] = {"total_positive_pnl_usd": r2(tp),
    "largest_trade_usd": r2(pos.pnl.iloc[0]), "largest_trade_symbol": pos.symbol.iloc[0], "largest_trade_opened": str(pos.opened.iloc[0]),
    "share_largest": r2(pos.pnl.iloc[0] / tp), "top5_usd": r2(pos.pnl.head(5).sum()), "share_top5": r2(pos.pnl.head(5).sum() / tp),
    "top5": [{"symbol": r.symbol, "pnl_usd": r2(r.pnl), "side": int(r.side), "lev": int(r.leverage), "opened": str(r.opened)} for r in pos.head(5).itertuples()],
    "field": "realizedPnlEv/1e4"}

# --- win rate / payoff / hold / fees ---
w, l = df[df.pnl > 0], df[df.pnl <= 0]
out["win_rate"] = {"value": r2(len(w) / len(df)), "n_wins": int(len(w)), "n_losses_or_zero": int(len(l)), "field": "realizedPnlEv>0"}
out["payoff_ratio"] = {"value": r2(w.pnl.mean() / -l.pnl.mean()), "avg_win_usd": r2(w.pnl.mean()), "avg_loss_usd": r2(l.pnl.mean()), "field": "realizedPnlEv/1e4"}
out["median_hold_seconds"] = r2(df.hold_s.median())
out["totals_usd"] = {"realized": r2(df.pnl.sum()), "gross_closedPnl": r2(df.gross.sum()), "fees": r2(df.fee.sum()), "funding": r2(df.fund.sum()),
                     "field": "closedPnlEv, exchangeFeeEv, fundingFeeEv, realizedPnlEv /1e4"}

def grp(g):
    return {"n": int(len(g)), "pnl_usd": r2(g.pnl.sum()), "wr": r2((g.pnl > 0).mean()), "median_hold_s": r2(g.hold_s.median())}
out["symbols"] = {k: grp(g) for k, g in df.groupby("symbol")}
out["side_split"] = {("long" if k == 1 else "short"): grp(g) for k, g in df.groupby("side")}
out["time_of_day_utc_by_open"] = {int(k): {"n": int(len(g)), "pnl_usd": r2(g.pnl.sum())} for k, g in df.groupby(df.opened.dt.hour)}

# --- behaviour after loss / win ---
beh = {}
for lab, mask in (("after_loss", df.pnl <= 0), ("after_win", df.pnl > 0)):
    idx = df.index[mask & (df.index < len(df) - 1)]
    nx = df.loc[idx + 1].reset_index(drop=True); cur = df.loc[idx].reset_index(drop=True)
    beh[lab] = {"n": int(len(idx)), "next_closedSize_mean": r2(nx.closedSize.mean()), "this_closedSize_mean": r2(cur.closedSize.mean()),
                "next_size_up_share_same_symbol": r2(((nx.closedSize > cur.closedSize) & (nx.symbol == cur.symbol)).sum() / max(1, (nx.symbol == cur.symbol).sum())),
                "next_leverage_mean": r2(nx.leverage.mean()), "this_leverage_mean": r2(cur.leverage.mean()),
                "next_hold_s_median": r2(nx.hold_s.median()), "next_same_side_share": r2((nx.side == cur.side).mean()),
                "next_same_symbol_share": r2((nx.symbol == cur.symbol).mean()), "next_pnl_mean_usd": r2(nx.pnl.mean()),
                "next_wr": r2((nx.pnl > 0).mean()),
                "gap_close_to_next_open_s_median": r2(np.median((nx.openedTimeNs.values - cur.updatedTimeNs.values) / 1e3))}
out["behaviour_after_loss"] = beh
out["behaviour_field"] = "chronologically next row by updatedTimeNs (closedSize, leverage, side, symbol, hold, realizedPnlEv)"

# --- the profitable subset: TRYB vs everything else ---
T = df[df.symbol == "u100TRYBUSD"]; X = df[df.symbol != "u100TRYBUSD"]
out["tryb_detail"] = {"n": int(len(T)), "pnl_usd": r2(T.pnl.sum()), "wr": r2((T.pnl > 0).mean()),
    "side_counts": {("long" if k == 1 else "short"): int(v) for k, v in T.side.value_counts().items()},
    "pnl_by_side": {("long" if k == 1 else "short"): r2(v) for k, v in T.groupby("side").pnl.sum().items()},
    "first_open": str(T.opened.min()), "last_close": str(T.closed.max()),
    "open_price_range_Ep": [int(T.openPriceEp.min()), int(T.openPriceEp.max())],
    "close_price_range_Ep": [int(T.closePriceEp.min()), int(T.closePriceEp.max())],
    "dir_move_bps_median": r2(T.dir_move_bps.median()), "hold_s_median": r2(T.hold_s.median()),
    "leverage_values": sorted(set(int(x) for x in T.leverage)),
    "trades": [{"opened": str(r.opened), "closed": str(r.closed), "side": "long" if r.side == 1 else "short", "size": int(r.closedSize),
                "openEp": int(r.openPriceEp), "closeEp": int(r.closePriceEp), "dir_move_bps": r2(r.dir_move_bps), "pnl_usd": r2(r.pnl), "lev": int(r.leverage)}
               for r in T.sort_values("opened").itertuples()],
    "note": "Ep price scale for u100TRYBUSD not decoded here; relative move (dir_move_bps) is scale-free."}
ci = bootstrap_ci.mean_ci(X.pnl.values)
out["ex_tryb"] = {"n": int(len(X)), "pnl_usd": r2(X.pnl.sum()), "wr": r2((X.pnl > 0).mean()), "mean_usd_ci95": ci,
                  "gross_usd": r2(X.gross.sum()), "fees_usd": r2(X.fee.sum()), "ci_source": "research.swarm.lib.bootstrap_ci.mean_ci(realizedPnlEv/1e4)"}
# event windows: LUNA crash 2022-05-07..05-15, FTX collapse 2022-11-06..11-14 (dates are the probe's own window choice)
ev = {"luna_2022-05-07_to_05-15": ("2022-05-07", "2022-05-16"), "ftx_2022-11-06_to_11-14": ("2022-11-06", "2022-11-15")}
evo = {}
for k, (a, b) in ev.items():
    g = X[(X.opened >= a) & (X.opened < b)]
    evo[k] = {"ex_tryb": grp(g) if len(g) else {"n": 0}, "dir_move_bps_mean": r2(g.dir_move_bps.mean()) if len(g) else None}
    gs = df[(df.opened >= a) & (df.opened < b)]
    evo[k]["all"] = grp(gs) if len(gs) else {"n": 0}
out["stress_event_windows"] = evo
# hold buckets ex-TRYB, with directional move CI (bps) via lib
def hb(s):
    return "<1h" if s < 3600 else "1-4h" if s < 14400 else "4-24h" if s < 86400 else ">24h"
out["ex_tryb_by_hold"] = {}
for k, g in X.groupby(X.hold_s.map(hb)):
    out["ex_tryb_by_hold"][k] = {**grp(g), "dir_move_bps_mean": r2(g.dir_move_bps.mean()),
                                 "dir_move_bps_ci95": bootstrap_ci.mean_ci(g.dir_move_bps.values) if len(g) > 1 else None}
# top-20 ex-TRYB winners: when / what
xw = X.sort_values("pnl", ascending=False).head(20)
out["ex_tryb_top20_winners"] = [{"symbol": r.symbol, "opened": str(r.opened), "side": "long" if r.side == 1 else "short",
                                 "hold_h": r2(r.hold_s / 3600), "dir_move_bps": r2(r.dir_move_bps), "pnl_usd": r2(r.pnl), "lev": int(r.leverage)} for r in xw.itertuples()]
out["ex_tryb_top20_share_of_ex_tryb_positive"] = r2(xw.pnl.sum() / X[X.pnl > 0].pnl.sum())

s = json.dumps(out, indent=1, default=str)
(RUN / "exploratory/owner-record/owner_record_probe.json").write_text(s)
(RUN / "theses/owner_record_probe.json").write_text(s)
print(s)
