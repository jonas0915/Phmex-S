"""EXPLORATORY PROBE (owner-record lens, run 2026-09-27-0300). NOT a screen, NOT evidence.
Reads only research/swarm/kb/owner_trades/*.json (owner's 2022-23 inverse-contract record).
Writes research/swarm/runs/2026-09-27-0300/theses/owner_record_probe.json."""
import json, collections
from pathlib import Path
import numpy as np, pandas as pd
from research.swarm.lib import bootstrap_ci, fee_math

ROOT = Path("/Users/jonaspenaso/Desktop/Phmex-S")
KB = ROOT / "research/swarm/kb/owner_trades"
SRC = "research/swarm/kb/owner_trades/api_closed_pnl.json"
OUT = ROOT / "research/swarm/runs/2026-09-27-0300/theses/owner_record_probe.json"

rows = json.load(open(KB / "api_closed_pnl.json"))
df = pd.DataFrame(rows)
for c in ["closedSize", "cumEntryValueEv", "closedPnlEv", "exchangeFeeEv", "fundingFeeEv", "realizedPnlEv",
          "openedTimeNs", "updatedTimeNs", "openPriceEp", "closePriceEp", "leverage", "side"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
# openedTimeNs / updatedTimeNs are in ms despite the name (1648275092166 -> 2022-03-26)
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
out = {"_label": "EXPLORATORY PROBE - not a screen, not evidence for any thesis verdict",
       "source_file": SRC, "n_rows": int(len(df)),
       "time_field_note": "openedTimeNs/updatedTimeNs are millisecond epochs (value 1648275092166 -> 2022-03-26)",
       "date_range_utc": [str(df.opened.min()), str(df.closed.max())]}

# equity path
dep = json.load(open(KB / "api_deposit_list_full.json")) if (KB / "api_deposit_list_full.json").exists() else None
wd = json.load(open(KB / "api_withdraw_list_full.json")) if (KB / "api_withdraw_list_full.json").exists() else None
df["cum_realized"] = df.pnl.cumsum()
out["equity_path"] = {
    "method": "cumulative realized PnL (realizedPnlEv/1e4); deposit/withdraw files present but mixed-currency with no USD value field and no in-stage 2022 price source, so a USD equity line cannot be built without inventing rates",
    "deposit_file_rows": len(dep) if dep else None, "withdraw_file_rows": len(wd) if wd else None,
    "deposit_currencies_counts": dict(collections.Counter(d["currency"] for d in dep)) if dep else None,
    "withdraw_currencies_counts": dict(collections.Counter(w["currency"] for w in wd)) if wd else None,
    "final_cum_realized_usd": round(float(df.cum_realized.iloc[-1]), 2),
    "min_cum_realized_usd": round(float(df.cum_realized.min()), 2),
    "min_at": str(df.closed.iloc[int(df.cum_realized.idxmin())]),
    "max_cum_realized_usd": round(float(df.cum_realized.max()), 2),
    "max_at": str(df.closed.iloc[int(df.cum_realized.idxmax())]),
    "monthly_realized_usd": {str(k): round(float(v), 2) for k, v in df.groupby(df.closed.dt.strftime("%Y-%m")).pnl.sum().items()},
    "field": "realizedPnlEv/1e4, updatedTimeNs",
}
if dep:
    # 2022-23 window flows by currency (raw amountEv/1e8), no USD conversion
    lo, hi = df.opened.min().value // 10**6, df.closed.max().value // 10**6
    def win(lst, key):
        c = collections.defaultdict(float)
        for r in lst:
            t = int(r.get(key) or 0)
            if lo - 86400000 * 7 <= t <= hi and r.get("status") in ("Success", "Succeed"):
                c[r["currency"]] += int(r["amountEv"]) / 1e8
        return {k: round(v, 4) for k, v in c.items()}
    out["equity_path"]["flows_in_window_native_units_amountEv_div_1e8"] = {
        "deposits": win(dep, "createdAt"), "withdrawals": win(wd, "submittedAt"),
        "note": "native coin units, NOT USD; window = first open minus 7d .. last close"}

pos = df.pnl[df.pnl > 0].sort_values(ascending=False)
out["concentration"] = {"total_positive_pnl_usd": round(float(pos.sum()), 2),
    "largest_trade_usd": round(float(pos.iloc[0]), 2),
    "largest_trade_symbol": df.loc[pos.index[0], "symbol"], "largest_trade_opened": str(df.loc[pos.index[0], "opened"]),
    "share_largest": round(float(pos.iloc[0] / pos.sum()), 4),
    "top5_usd": round(float(pos.iloc[:5].sum()), 2), "share_top5": round(float(pos.iloc[:5].sum() / pos.sum()), 4),
    "top5_symbols": [df.loc[i, "symbol"] for i in pos.index[:5]], "field": "realizedPnlEv/1e4"}
w, l = df.pnl[df.pnl > 0], df.pnl[df.pnl < 0]
out["win_rate"] = {"value": round(len(w) / len(df), 4), "n_wins": int(len(w)), "n_losses": int(len(l)), "field": "realizedPnlEv>0"}
out["payoff_ratio"] = {"value": round(float(w.mean() / -l.mean()), 4), "avg_win_usd": round(float(w.mean()), 2),
                       "avg_loss_usd": round(float(l.mean()), 2), "field": "realizedPnlEv/1e4"}
out["median_hold_seconds"] = float(df.hold_s.median())
out["fees_total_usd"] = round(float(df.fee.sum()), 2)
out["funding_total_usd"] = round(float(df.fund.sum()), 2)
out["gross_total_usd"] = round(float(df.gross.sum()), 2)
sym = df.groupby("symbol").agg(n=("pnl", "size"), pnl=("pnl", "sum"), wr=("pnl", lambda s: (s > 0).mean())).sort_values("n", ascending=False)
out["symbols"] = {k: {"n": int(r.n), "pnl_usd": round(float(r.pnl), 2), "wr": round(float(r.wr), 4)} for k, r in sym.iterrows()}
out["side_split"] = {str(int(k)): {"n": int(len(g)), "pnl_usd": round(float(g.pnl.sum()), 2), "wr": round(float((g.pnl > 0).mean()), 4)}
                     for k, g in df.groupby("side")}
out["side_code_note"] = "Phemex side 1=Buy(long) 2=Sell(short)"
out["time_of_day_utc"] = {int(h): {"n": int(len(g)), "pnl_usd": round(float(g.pnl.sum()), 2)} for h, g in df.groupby(df.opened.dt.hour)}

# behaviour after loss
nxt = df.shift(-1)
after = {}
for lab, m in (("after_loss", df.pnl < 0), ("after_win", df.pnl > 0)):
    m = m & nxt.pnl.notna()
    after[lab] = {"n": int(m.sum()), "next_closedSize_mean": round(float(nxt.closedSize[m].mean()), 3),
                  "next_hold_s_median": float(nxt.hold_s[m].median()),
                  "next_same_side_share": round(float((nxt.side[m] == df.side[m]).mean()), 4),
                  "next_same_symbol_share": round(float((nxt.symbol[m] == df.symbol[m]).mean()), 4),
                  "next_pnl_mean_usd": round(float(nxt.pnl[m].mean()), 3),
                  "next_wr": round(float((nxt.pnl[m] > 0).mean()), 4),
                  "gap_to_next_open_s_median": float(((nxt.openedTimeNs[m] - df.updatedTimeNs[m]) / 1e3).median())}
out["behaviour_after_loss"] = after
out["behaviour_field"] = "chronologically next row by updatedTimeNs: closedSize, side, symbol, hold, realizedPnlEv"

# decomposition: TRYB episode vs rest
tr = df.symbol == "u100TRYBUSD"
ex = df[~tr]
ci = bootstrap_ci.mean_ci(ex.pnl.values)
out["tryb_vs_rest"] = {"tryb_n": int(tr.sum()), "tryb_pnl_usd": round(float(df.pnl[tr].sum()), 2),
    "tryb_first_open": str(df.opened[tr].min()), "tryb_last_close": str(df.closed[tr].max()),
    "ex_tryb_n": int(len(ex)), "ex_tryb_pnl_usd": round(float(ex.pnl.sum()), 2),
    "ex_tryb_mean_usd_ci95_bootstrap": [round(ci[0], 3), round(ci[1], 3)],
    "ex_tryb_wr": round(float((ex.pnl > 0).mean()), 4),
    "ex_tryb_gross_usd": round(float(ex.gross.sum()), 2), "ex_tryb_fee_usd": round(float(ex.fee.sum()), 2),
    "ex_tryb_funding_usd": round(float(ex.fund.sum()), 2),
    "ci_source": "research.swarm.lib.bootstrap_ci.mean_ci on realizedPnlEv/1e4 per trade"}

# ex-TRYB: where did the positive slices live? (per-trade directional price move in bps, fee-free)
def slice_stats(g):
    x = g.dir_move_bps.dropna().values
    d = {"n": int(len(g)), "pnl_usd": round(float(g.pnl.sum()), 2), "wr_pnl": round(float((g.pnl > 0).mean()), 4) if len(g) else None,
         "dir_move_bps_mean": round(float(np.mean(x)), 2) if len(x) else None}
    if len(x) >= 10:
        c = bootstrap_ci.mean_ci(x); d["dir_move_bps_ci95"] = [round(c[0], 2), round(c[1], 2)]
    return d
bins = [0, 600, 3600, 4 * 3600, 24 * 3600, 1e12]
labs = ["<10m", "10m-1h", "1-4h", "4-24h", ">24h"]
ex = ex.assign(hold_bucket=pd.cut(ex.hold_s, bins, labels=labs, right=False))
out["ex_tryb_by_hold"] = {str(k): slice_stats(g) for k, g in ex.groupby("hold_bucket", observed=True)}
out["ex_tryb_by_side"] = {str(int(k)): slice_stats(g) for k, g in ex.groupby("side")}
out["ex_tryb_by_leverage"] = {str(k): slice_stats(g) for k, g in ex.groupby(pd.cut(ex.leverage, [-1, 0.5, 10, 25, 50, 1000], labels=["0(cross)", "1-10", "11-25", "26-50", ">50"]), observed=True)}
out["ex_tryb_by_month"] = {k: slice_stats(g) for k, g in ex.groupby(ex.opened.dt.strftime("%Y-%m"))}
# market-stress windows (dates from public record: LUNA collapse 2022-05-07..05-13, 3AC/Celsius 2022-06-12..06-19, FTX 2022-11-06..11-14)
stress = {"luna_2022-05-07_05-13": ("2022-05-07", "2022-05-14"), "celsius_3ac_2022-06-12_06-19": ("2022-06-12", "2022-06-20"),
          "ftx_2022-11-06_11-14": ("2022-11-06", "2022-11-15")}
sm = pd.Series(False, index=ex.index)
out["ex_tryb_stress_windows"] = {}
for k, (a, b) in stress.items():
    m = (ex.opened >= pd.Timestamp(a, tz="UTC")) & (ex.opened < pd.Timestamp(b, tz="UTC"))
    sm |= m
    out["ex_tryb_stress_windows"][k] = slice_stats(ex[m])
out["ex_tryb_stress_windows"]["all_other_days"] = slice_stats(ex[~sm])
for k, sub in (("stress_long", ex[sm & (ex.side == 1)]), ("stress_short", ex[sm & (ex.side == 2)])):
    out["ex_tryb_stress_windows"][k] = slice_stats(sub)
top = ex.sort_values("pnl", ascending=False).head(15)
out["ex_tryb_top15_winners"] = [{"symbol": r.symbol, "side": int(r.side), "opened": str(r.opened), "hold_h": round(r.hold_s / 3600, 2),
                                 "pnl_usd": round(r.pnl, 2), "dir_move_bps": round(r.dir_move_bps, 1), "leverage": float(r.leverage)} for r in top.itertuples()]
out["ex_tryb_top15_share_of_ex_tryb_positive"] = round(float(top.pnl.sum() / ex.pnl[ex.pnl > 0].sum()), 4)
out["fee_math_ref"] = {"C_BPS": fee_math.C_BPS, "p_star_200": fee_math.p_star(200)}
json.dump(out, open(OUT, "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
