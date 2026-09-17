"""EXPLORATORY PROBE (not a thesis, not a screen). Lens: owner-record.
Reads research/swarm/kb/owner_trades/api_closed_pnl.json (819 closed inverse-contract positions)
and, if present, api_deposit_list_full.json / api_withdraw_list_full.json.
Writes research/swarm/runs/2026-09-17-0701/theses/owner_record_probe.json.
Every number carries the field it came from. Stats via research.swarm.lib.bootstrap_ci only.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np, pandas as pd
ROOT = Path("/Users/jonaspenaso/Desktop/Phmex-S"); sys.path.insert(0, str(ROOT))
from research.swarm.lib import bootstrap_ci as bci

KB = ROOT / "research/swarm/kb/owner_trades"
OUT = ROOT / "research/swarm/runs/2026-09-17-0701/theses/owner_record_probe.json"
EV = 1e4  # *Ev fields / 1e4 = USD (SOURCES.md §2b, verified two ways)
EP = 1e4  # *Ep price scale (openPriceEp 899930 -> 89.993 LUNA)

rows = json.load(open(KB / "api_closed_pnl.json"))
df = pd.DataFrame(rows)
for c in ["closedSize","cumEntryValueEv","closedPnlEv","exchangeFeeEv","fundingFeeEv","realizedPnlEv","openedTimeNs","updatedTimeNs","openPriceEp","closePriceEp","roiEr","leverage"]:
    df[c] = pd.to_numeric(df[c])
df["realized_usd"] = df["realizedPnlEv"] / EV
df["closed_pnl_usd"] = df["closedPnlEv"] / EV
df["fee_usd"] = df["exchangeFeeEv"] / EV
df["funding_usd"] = df["fundingFeeEv"] / EV
df["opened"] = pd.to_datetime(df["openedTimeNs"], unit="ms", utc=True)
df["closed"] = pd.to_datetime(df["updatedTimeNs"], unit="ms", utc=True)
df["hold_min"] = (df["closed"] - df["opened"]).dt.total_seconds() / 60
df["open_px"] = df["openPriceEp"] / EP; df["close_px"] = df["closePriceEp"] / EP
# side decode check: side=1 rows should have sign(closedPnl) == sign(close-open)
df["px_ret"] = df["close_px"] / df["open_px"] - 1
s1 = df[df.side == "1"]; s2 = df[df.side == "2"]
side1_long_consistent = float(((np.sign(s1.closed_pnl_usd) == np.sign(s1.px_ret)) | (s1.closed_pnl_usd == 0)).mean())
side2_short_consistent = float(((np.sign(s2.closed_pnl_usd) == -np.sign(s2.px_ret)) | (s2.closed_pnl_usd == 0)).mean())
df["dir"] = np.where(df.side == "1", "long", "short")
df["gross_ret_bps"] = np.where(df.side == "1", df.px_ret, -df.px_ret) * 1e4  # price move in position direction, bps
df = df.sort_values("closed").reset_index(drop=True)
df["cum_realized_usd"] = df["realized_usd"].cumsum()

res = {"_label": "EXPLORATORY PROBE — not a thesis, not a screen; numbers are descriptive of the owner's 2022-23 inverse-contract record only",
       "source_file": str(KB / "api_closed_pnl.json"), "n_rows": int(len(df)),
       "scale_note": "USD = *Ev/1e4 (SOURCES.md §2b); price = *Ep/1e4; openedTimeNs/updatedTimeNs are epoch ms",
       "side_decode": {"side==1 treated as long, share of rows where sign(closedPnlEv)==sign(closePriceEp-openPriceEp)": side1_long_consistent,
                        "side==2 treated as short, share consistent": side2_short_consistent},
       "window_utc": {"first_open": str(df.opened.min()), "last_close": str(df.closed.max())}}

# --- cumulative realized PnL path (field realizedPnlEv) ---
cum = df.set_index("closed")["cum_realized_usd"]
monthly = cum.resample("ME").last().dropna()
res["cum_realized_pnl_usd"] = {"field": "realizedPnlEv/1e4 cumsum in closed-time order",
    "final": float(cum.iloc[-1]), "min": float(cum.min()), "min_at": str(cum.idxmin()), "max": float(cum.max()), "max_at": str(cum.idxmax()),
    "month_end": {str(k.date()): float(v) for k, v in monthly.items()}}
res["components_usd"] = {"sum_closedPnlEv": float(df.closed_pnl_usd.sum()), "sum_exchangeFeeEv": float(df.fee_usd.sum()),
                          "sum_fundingFeeEv": float(df.funding_usd.sum()), "sum_realizedPnlEv": float(df.realized_usd.sum()),
                          "identity_check_closed_minus_fee_minus_funding_minus_realized": float((df.closed_pnl_usd - df.fee_usd - df.funding_usd - df.realized_usd).abs().max())}

# --- deposits / withdrawals (present) — by currency, raw amountEv/1e8; NO USD conversion (no 2022 price source here) ---
def flows(fn, amt_scale=1e8):
    p = KB / fn
    if not p.exists(): return {"present": False}
    d = json.load(open(p)); out = defaultdict(lambda: {"n": 0, "amount_units": 0.0})
    for r in d:
        if str(r.get("status", "")).lower() not in ("success", "succeed"): continue
        out[r["currency"]]["n"] += 1; out[r["currency"]]["amount_units"] += float(r["amountEv"]) / amt_scale
    ts_key = "createdAt" if "createdAt" in d[0] else "submittedAt"
    ts = pd.to_datetime([int(r[ts_key]) for r in d], unit="ms", utc=True)
    return {"present": True, "file": str(p), "n_rows": len(d), "first": str(ts.min()), "last": str(ts.max()),
            "by_currency_successful": dict(out), "scale_note": "amountEv/1e8 in native coin units (Phemex wallet Ev scale); NOT converted to USD — no historical price source in this probe"}
res["deposits"] = flows("api_deposit_list_full.json"); res["withdrawals"] = flows("api_withdraw_list_full.json")
res["true_equity_path"] = "NOT COMPUTED — deposits/withdrawals are in XRP/ADA/MATIC/AVAX/USDT native units and the inverse contracts settle in coin (currency='USD' label, coin-margined); a USD equity line needs 2022-23 daily prices for each coin, which this probe does not have. Cumulative realized PnL (realizedPnlEv) is reported instead."

# --- concentration ---
pos = df[df.realized_usd > 0].realized_usd.sort_values(ascending=False)
res["concentration"] = {"field": "realizedPnlEv/1e4, positive rows only", "total_positive_usd": float(pos.sum()), "n_positive": int(len(pos)),
    "largest_trade_usd": float(pos.iloc[0]), "largest_share_of_total_positive": float(pos.iloc[0] / pos.sum()),
    "top5_share_of_total_positive": float(pos.iloc[:5].sum() / pos.sum()),
    "top5_rows": df.loc[pos.index[:5], ["symbol","dir","opened","closed","hold_min","closedSize","open_px","close_px","realized_usd"]].astype(str).to_dict("records")}

# --- win rate / payoff / hold ---
w = df[df.realized_usd > 0]; l = df[df.realized_usd < 0]
res["win_rate"] = {"field": "realizedPnlEv>0", "wr": float(len(w) / len(df)), "n_win": int(len(w)), "n_loss": int(len(l)), "n_zero": int((df.realized_usd == 0).sum()),
                   "wr_ci95_bootstrap": list(bci.mean_ci((df.realized_usd > 0).astype(float).to_numpy()))}
res["payoff"] = {"mean_win_usd": float(w.realized_usd.mean()), "mean_loss_usd": float(l.realized_usd.mean()), "payoff_ratio": float(w.realized_usd.mean() / -l.realized_usd.mean()),
                 "median_win_usd": float(w.realized_usd.median()), "median_loss_usd": float(l.realized_usd.median()),
                 "mean_realized_per_trade_usd": float(df.realized_usd.mean()), "mean_realized_ci95_bootstrap": list(bci.mean_ci(df.realized_usd.to_numpy())),
                 "mean_gross_ret_bps_in_position_direction": float(df.gross_ret_bps.mean()), "gross_ret_bps_ci95": list(bci.mean_ci(df.gross_ret_bps.to_numpy()))}
res["hold"] = {"field": "updatedTimeNs-openedTimeNs (ms) in minutes", "median_min": float(df.hold_min.median()), "mean_min": float(df.hold_min.mean()),
               "p25_min": float(df.hold_min.quantile(.25)), "p75_min": float(df.hold_min.quantile(.75)),
               "median_hold_winners_min": float(w.hold_min.median()), "median_hold_losers_min": float(l.hold_min.median())}
# hold buckets
bins = [0, 5, 30, 120, 480, 1440, 1e9]; labels = ["<5m","5-30m","30m-2h","2-8h","8-24h",">24h"]
df["hold_bucket"] = pd.cut(df.hold_min, bins=bins, labels=labels, right=False)
res["by_hold_bucket"] = {str(k): {"n": int(len(g)), "wr": float((g.realized_usd > 0).mean()), "sum_usd": float(g.realized_usd.sum()), "mean_usd": float(g.realized_usd.mean()),
                          "mean_gross_ret_bps": float(g.gross_ret_bps.mean())} for k, g in df.groupby("hold_bucket", observed=True)}

# --- symbols ---
res["by_symbol"] = {k: {"n": int(len(g)), "wr": float((g.realized_usd > 0).mean()), "sum_usd": float(g.realized_usd.sum()), "median_hold_min": float(g.hold_min.median())}
                    for k, g in sorted(df.groupby("symbol"), key=lambda kv: -kv[1].realized_usd.sum())}
# --- side split ---
res["by_side"] = {k: {"n": int(len(g)), "wr": float((g.realized_usd > 0).mean()), "sum_usd": float(g.realized_usd.sum()), "mean_usd": float(g.realized_usd.mean()),
                      "mean_ci95": list(bci.mean_ci(g.realized_usd.to_numpy())), "median_hold_min": float(g.hold_min.median())} for k, g in df.groupby("dir")}
# --- time of day (UTC hour of open) ---
df["hour_utc"] = df.opened.dt.hour
res["by_open_hour_utc"] = {int(k): {"n": int(len(g)), "wr": float((g.realized_usd > 0).mean()), "sum_usd": float(g.realized_usd.sum())} for k, g in df.groupby("hour_utc")}
df["dow"] = df.opened.dt.day_name()
res["by_open_dow_utc"] = {k: {"n": int(len(g)), "wr": float((g.realized_usd > 0).mean()), "sum_usd": float(g.realized_usd.sum())} for k, g in df.groupby("dow")}
# --- behaviour after a loss (next trade in closed-time order) ---
df["prev_realized"] = df.realized_usd.shift(1); df["prev_dir"] = df["dir"].shift(1); df["prev_size"] = df.closedSize.shift(1); df["prev_symbol"] = df.symbol.shift(1)
nxt = df.dropna(subset=["prev_realized"])
after_loss = nxt[nxt.prev_realized < 0]; after_win = nxt[nxt.prev_realized > 0]
def beh(g):
    same_sym = g[g.symbol == g.prev_symbol]
    return {"n": int(len(g)), "wr_next": float((g.realized_usd > 0).mean()), "mean_next_usd": float(g.realized_usd.mean()), "mean_next_ci95": list(bci.mean_ci(g.realized_usd.to_numpy())),
            "median_hold_next_min": float(g.hold_min.median()), "share_next_same_side": float((g["dir"] == g.prev_dir).mean()),
            "share_next_same_symbol": float((g.symbol == g.prev_symbol).mean()),
            "median_size_ratio_next_over_prev_same_symbol": float((same_sym.closedSize / same_sym.prev_size).median()) if len(same_sym) else None,
            "n_same_symbol": int(len(same_sym))}
res["after_loss"] = beh(after_loss); res["after_win"] = beh(after_win)
res["after_loss_minus_after_win_mean_diff_ci95"] = list(bci.diff_ci(after_loss.realized_usd.to_numpy(), after_win.realized_usd.to_numpy()))
# --- profitable subset: what did the big winners look like? ---
res["gross_ret_bps_quantiles"] = {q: float(df.gross_ret_bps.quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}
res["gross_ret_bps_by_side"] = {k: {"median": float(g.gross_ret_bps.median()), "mean": float(g.gross_ret_bps.mean())} for k, g in df.groupby("dir")}
# PnL month by side
df["month"] = df.closed.dt.strftime("%Y-%m")
res["by_month_side_sum_usd"] = {m: {k: float(g.realized_usd.sum()) for k, g in gm.groupby("dir")} for m, gm in df.groupby("month")}
res["by_month_n_wr"] = {m: {"n": int(len(gm)), "wr": float((gm.realized_usd > 0).mean())} for m, gm in df.groupby("month")}
# leverage field
res["leverage_field"] = {"field": "leverage (raw)", "value_counts": {str(k): int(v) for k, v in df.leverage.value_counts().items()}}
res["closedSize_note"] = "closedSize is contracts; cumEntryValueEv is 0 on every row" if (df.cumEntryValueEv == 0).all() else "cumEntryValueEv nonzero on some rows"

OUT.write_text(json.dumps(res, indent=1, default=str))
print(json.dumps({k: res[k] for k in ["n_rows","side_decode","cum_realized_pnl_usd","components_usd","concentration","win_rate","payoff","hold","by_hold_bucket","by_side","after_loss","after_win","after_loss_minus_after_win_mean_diff_ci95","gross_ret_bps_quantiles","leverage_field","closedSize_note","true_equity_path"]}, indent=1, default=str))
print("BY_SYMBOL", json.dumps(res["by_symbol"], indent=0, default=str))
print("BY_HOUR", json.dumps(res["by_open_hour_utc"], default=str))
print("BY_DOW", json.dumps(res["by_open_dow_utc"], default=str))
print("BY_MONTH", json.dumps(res["by_month_side_sum_usd"], default=str)); print(json.dumps(res["by_month_n_wr"], default=str))
print("DEP", json.dumps(res["deposits"], default=str)); print("WD", json.dumps(res["withdrawals"], default=str))
