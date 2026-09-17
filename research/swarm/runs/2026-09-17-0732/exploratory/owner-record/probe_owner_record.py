"""EXPLORATORY probe — owner-record lens, run 2026-09-17-0732.

Reads research/swarm/kb/owner_trades/api_closed_pnl.json (819 closed inverse-contract positions,
2022-03 -> 2023-02) plus the deposit/withdraw lists if present, and writes a descriptive summary to
research/swarm/runs/2026-09-17-0732/theses/owner_record_probe.json.

This is a PROBE, not a thesis and not a screen. Nothing here is evidence for a pass/fail verdict.
Field provenance is recorded next to every number. No stats are hand-rolled: CI numbers come from
research.swarm.lib.bootstrap_ci.mean_ci; everything else is counts / sums / medians of raw fields.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path("/Users/jonaspenaso/Desktop/Phmex-S")
sys.path.insert(0, str(REPO))
from research.swarm.lib.bootstrap_ci import mean_ci  # noqa: E402

KB = REPO / "research/swarm/kb/owner_trades"
OUT = REPO / "research/swarm/runs/2026-09-17-0732/theses/owner_record_probe.json"
PNL_PATH = KB / "api_closed_pnl.json"
DEP_PATH = KB / "api_deposit_list_full.json"
WD_PATH = KB / "api_withdraw_list_full.json"

EV = 1e4          # closed-position *Ev fields -> USD (verified in SOURCES.md section 2b)
EP = 1e4          # *Ep price fields -> price
WALLET_EV = 1e8   # wallet amountEv -> native units (SOURCES.md 2c: 3000000000 raw = 30 XRP)

rows = json.load(open(PNL_PATH))
df = pd.DataFrame(rows)
for c in ["closedSize", "closedPnlEv", "exchangeFeeEv", "fundingFeeEv", "realizedPnlEv",
          "openedTimeNs", "updatedTimeNs", "openPriceEp", "closePriceEp", "roiEr", "leverage", "cumEntryValueEv"]:
    df[c] = pd.to_numeric(df[c])
df["opened"] = pd.to_datetime(df["openedTimeNs"], unit="ms", utc=True)
df["closed"] = pd.to_datetime(df["updatedTimeNs"], unit="ms", utc=True)
df["hold_min"] = (df["closed"] - df["opened"]).dt.total_seconds() / 60.0
df["realized_usd"] = df["realizedPnlEv"] / EV
df["gross_usd"] = df["closedPnlEv"] / EV
df["fee_usd"] = df["exchangeFeeEv"] / EV
df["funding_usd"] = df["fundingFeeEv"] / EV
# side: 1 = long, 2 = short (checked: row 400 uBTCUSD side=2, open 20069.5 -> close 20180.0, closedPnlEv < 0)
df["side_lbl"] = df["side"].map({"1": "long", "2": "short"})
df["open_px"] = df["openPriceEp"] / EP
df["close_px"] = df["closePriceEp"] / EP
df["ret_bps"] = np.where(df["side_lbl"] == "long",
                         (df["close_px"] / df["open_px"] - 1) * 1e4,
                         (df["open_px"] / df["close_px"] - 1) * 1e4)
df = df.sort_values("closed").reset_index(drop=True)
df["cum_realized_usd"] = df["realized_usd"].cumsum()

out: dict = {"label": "EXPLORATORY PROBE — not a thesis, not a screen", "run": "2026-09-17-0732",
             "lens": "owner-record", "source_file": str(PNL_PATH.relative_to(REPO)),
             "scales": {"closed_pnl_Ev_div": EV, "price_Ep_div": EP, "wallet_amountEv_div": WALLET_EV,
                        "note": "Ev/Ep scales per SOURCES.md 2b; wallet 1e8 per SOURCES.md 2c XRP example."}}

# ---- headline ----
out["n_positions"] = int(len(df))
out["window_utc"] = {"first_open": str(df["opened"].min()), "last_close": str(df["closed"].max())}
out["cum_realized_pnl_usd"] = {"field": "sum(realizedPnlEv)/1e4", "total": round(float(df["realized_usd"].sum()), 2),
                                "min_cum": round(float(df["cum_realized_usd"].min()), 2),
                                "min_cum_at": str(df.loc[df["cum_realized_usd"].idxmin(), "closed"]),
                                "max_cum": round(float(df["cum_realized_usd"].max()), 2),
                                "max_cum_at": str(df.loc[df["cum_realized_usd"].idxmax(), "closed"])}
out["gross_pnl_usd_total"] = {"field": "sum(closedPnlEv)/1e4", "value": round(float(df["gross_usd"].sum()), 2)}
out["fees_usd_total"] = {"field": "sum(exchangeFeeEv)/1e4", "value": round(float(df["fee_usd"].sum()), 2)}
out["funding_usd_total"] = {"field": "sum(fundingFeeEv)/1e4", "value": round(float(df["funding_usd"].sum()), 2)}

# ---- monthly cum path (realized only) ----
m = df.set_index("closed")["realized_usd"].resample("MS").sum()
out["monthly_realized_usd"] = {str(k.date()): round(float(v), 2) for k, v in m.items()}
out["monthly_cum_realized_usd"] = {str(k.date()): round(float(v), 2) for k, v in m.cumsum().items()}

# ---- concentration ----
pos = df[df["realized_usd"] > 0].sort_values("realized_usd", ascending=False)
tot_pos = float(pos["realized_usd"].sum())
top1 = pos.iloc[0]
top5 = pos.head(5)
out["concentration"] = {
    "field": "realizedPnlEv/1e4, positive rows only",
    "total_positive_pnl_usd": round(tot_pos, 2),
    "n_positive": int(len(pos)),
    "largest_trade_usd": round(float(top1["realized_usd"]), 2),
    "largest_trade_share_of_positive": round(float(top1["realized_usd"]) / tot_pos, 4),
    "largest_trade": {"symbol": top1["symbol"], "side": top1["side_lbl"], "leverage": int(top1["leverage"]),
                      "opened": str(top1["opened"]), "closed": str(top1["closed"]),
                      "hold_min": round(float(top1["hold_min"]), 1), "ret_bps": round(float(top1["ret_bps"]), 1),
                      "closedSize": int(top1["closedSize"])},
    "top5_usd": round(float(top5["realized_usd"].sum()), 2),
    "top5_share_of_positive": round(float(top5["realized_usd"].sum()) / tot_pos, 4),
    "top5_trades": [{"symbol": r["symbol"], "side": r["side_lbl"], "leverage": int(r["leverage"]),
                     "usd": round(float(r["realized_usd"]), 2), "closed": str(r["closed"]),
                     "hold_min": round(float(r["hold_min"]), 1), "ret_bps": round(float(r["ret_bps"]), 1)}
                    for _, r in top5.iterrows()],
    "total_minus_largest_usd": round(float(df["realized_usd"].sum()) - float(top1["realized_usd"]), 2),
    "total_minus_top5_usd": round(float(df["realized_usd"].sum()) - float(top5["realized_usd"].sum()), 2),
}

# ---- win rate / payoff / hold ----
wins = df[df["realized_usd"] > 0]; losses = df[df["realized_usd"] < 0]
lo, hi = mean_ci(df["realized_usd"].values)
out["win_rate"] = {"field": "realizedPnlEv>0", "wr": round(len(wins) / len(df), 4), "n_win": int(len(wins)),
                   "n_loss": int(len(losses)), "n_zero": int((df["realized_usd"] == 0).sum())}
out["payoff_ratio"] = {"field": "mean(win realized)/|mean(loss realized)|",
                       "avg_win_usd": round(float(wins["realized_usd"].mean()), 3),
                       "avg_loss_usd": round(float(losses["realized_usd"].mean()), 3),
                       "ratio": round(float(wins["realized_usd"].mean() / abs(losses["realized_usd"].mean())), 3),
                       "median_win_usd": round(float(wins["realized_usd"].median()), 3),
                       "median_loss_usd": round(float(losses["realized_usd"].median()), 3)}
out["per_trade_realized_usd"] = {"mean": round(float(df["realized_usd"].mean()), 4),
                                 "ci95_bootstrap_lib": [round(lo, 4), round(hi, 4)],
                                 "median": round(float(df["realized_usd"].median()), 4)}
out["hold_minutes"] = {"field": "(updatedTimeNs-openedTimeNs)/60000", "median": round(float(df["hold_min"].median()), 1),
                       "p25": round(float(df["hold_min"].quantile(.25)), 1), "p75": round(float(df["hold_min"].quantile(.75)), 1),
                       "median_win": round(float(wins["hold_min"].median()), 1),
                       "median_loss": round(float(losses["hold_min"].median()), 1)}
out["ret_bps_price_move"] = {"field": "sign-adjusted (closePriceEp/openPriceEp-1)*1e4",
                             "median_win": round(float(wins["ret_bps"].median()), 1),
                             "median_loss": round(float(losses["ret_bps"].median()), 1),
                             "wr_gross_price_move_gt0": round(float((df["ret_bps"] > 0).mean()), 4)}

# ---- symbols ----
g = df.groupby("symbol").agg(n=("realized_usd", "size"), usd=("realized_usd", "sum"),
                             wr=("realized_usd", lambda s: float((s > 0).mean())),
                             med_hold=("hold_min", "median")).sort_values("usd", ascending=False)
out["symbols"] = {k: {"n": int(v.n), "usd": round(float(v.usd), 2), "wr": round(float(v.wr), 3),
                      "median_hold_min": round(float(v.med_hold), 1)} for k, v in g.iterrows()}

# ---- side ----
gs = df.groupby("side_lbl").agg(n=("realized_usd", "size"), usd=("realized_usd", "sum"),
                                wr=("realized_usd", lambda s: float((s > 0).mean())), med_hold=("hold_min", "median"))
out["side_split"] = {k: {"n": int(v.n), "usd": round(float(v.usd), 2), "wr": round(float(v.wr), 3),
                         "median_hold_min": round(float(v.med_hold), 1)} for k, v in gs.iterrows()}

# ---- leverage ----
gl = df.groupby("leverage").agg(n=("realized_usd", "size"), usd=("realized_usd", "sum"),
                                wr=("realized_usd", lambda s: float((s > 0).mean())))
out["leverage_split"] = {int(k): {"n": int(v.n), "usd": round(float(v.usd), 2), "wr": round(float(v.wr), 3)}
                         for k, v in gl.iterrows()}

# ---- time of day (open time, UTC hour and PT hour) ----
df["hour_utc"] = df["opened"].dt.hour
df["hour_pt"] = df["opened"].dt.tz_convert("America/Los_Angeles").dt.hour
for col in ["hour_utc", "hour_pt"]:
    gh = df.groupby(col).agg(n=("realized_usd", "size"), usd=("realized_usd", "sum"),
                             wr=("realized_usd", lambda s: float((s > 0).mean())))
    out[f"time_of_day_{col}"] = {int(k): {"n": int(v.n), "usd": round(float(v.usd), 2), "wr": round(float(v.wr), 3)}
                                 for k, v in gh.iterrows()}
df["dow_utc"] = df["opened"].dt.dayofweek
gd = df.groupby("dow_utc").agg(n=("realized_usd", "size"), usd=("realized_usd", "sum"),
                               wr=("realized_usd", lambda s: float((s > 0).mean())))
out["day_of_week_utc_0=Mon"] = {int(k): {"n": int(v.n), "usd": round(float(v.usd), 2), "wr": round(float(v.wr), 3)}
                                for k, v in gd.iterrows()}

# ---- behaviour after a loss (next trade in close-time order) ----
nxt = df.shift(-1)
after_loss = df[df["realized_usd"] < 0].index
after_win = df[df["realized_usd"] > 0].index
def nxt_stats(idx):
    n = nxt.loc[idx].dropna(subset=["realized_usd"])
    cur = df.loc[n.index]
    return {"n": int(len(n)),
            "next_size_ratio_median": round(float((n["closedSize"] / cur["closedSize"]).median()), 3),
            "next_size_larger_share": round(float((n["closedSize"] > cur["closedSize"]).mean()), 3),
            "next_same_side_share": round(float((n["side"] == cur["side"]).mean()), 3),
            "next_same_symbol_share": round(float((n["symbol"] == cur["symbol"]).mean()), 3),
            "next_hold_min_median": round(float(n["hold_min"].median()), 1),
            "next_leverage_median": round(float(n["leverage"].median()), 1),
            "next_wr": round(float((n["realized_usd"] > 0).mean()), 3),
            "next_realized_usd_mean": round(float(n["realized_usd"].mean()), 3),
            "gap_to_next_open_min_median": round(float(((n["opened"] - cur["closed"]).dt.total_seconds() / 60).median()), 1)}
out["after_loss_next_trade"] = nxt_stats(after_loss)
out["after_win_next_trade"] = nxt_stats(after_win)

# ---- hold-bucket / horizon view (what horizon did the money come from?) ----
bins = [0, 5, 15, 60, 240, 480, 1440, 1e9]
labels = ["<5m", "5-15m", "15-60m", "1-4h", "4-8h", "8-24h", ">24h"]
df["hold_bucket"] = pd.cut(df["hold_min"], bins=bins, labels=labels, right=False)
gb = df.groupby("hold_bucket", observed=True).agg(n=("realized_usd", "size"), usd=("realized_usd", "sum"),
                                                  wr=("realized_usd", lambda s: float((s > 0).mean())),
                                                  med_ret_bps=("ret_bps", "median"))
out["hold_bucket"] = {str(k): {"n": int(v.n), "usd": round(float(v.usd), 2), "wr": round(float(v.wr), 3),
                               "median_ret_bps": round(float(v.med_ret_bps), 1)} for k, v in gb.iterrows()}

# ---- funding paid vs received by side ----
gf = df.groupby("side_lbl")["funding_usd"].agg(["sum", "count"])
out["funding_by_side_usd"] = {k: {"sum": round(float(v["sum"]), 2), "n": int(v["count"])} for k, v in gf.iterrows()}

# ---- equity path with deposits / withdrawals (stable-coin flows only, native units otherwise) ----
eq: dict = {"note": ("Deposits/withdrawals are mostly non-stable (XRP/ADA/MATIC/TRX/...). Only USDT flows are "
                     "USD-denominated; non-stable flows are listed in NATIVE units unconverted because no "
                     "historical price series for them is in the repo and this probe fabricates nothing. "
                     "Therefore a TRUE equity path cannot be built from these files alone; the stable-only "
                     "path below is a partial reconstruction.")}
if DEP_PATH.exists() and WD_PATH.exists():
    dep = pd.DataFrame(json.load(open(DEP_PATH)))
    wd = pd.DataFrame(json.load(open(WD_PATH)))
    dep["ts"] = pd.to_datetime(pd.to_numeric(dep["createdAt"]), unit="ms", utc=True)
    dep["amt"] = pd.to_numeric(dep["amountEv"]) / WALLET_EV
    wd["ts"] = pd.to_datetime(pd.to_numeric(wd["submittedAt"]), unit="ms", utc=True)
    wd["amt"] = pd.to_numeric(wd["amountEv"]) / WALLET_EV
    wd_ok = wd[wd["status"] == "Succeed"]
    win0, win1 = df["opened"].min() - pd.Timedelta(days=2), df["closed"].max() + pd.Timedelta(days=30)
    dep_w = dep[(dep["ts"] >= win0) & (dep["ts"] <= win1)]
    wd_w = wd_ok[(wd_ok["ts"] >= win0) & (wd_ok["ts"] <= win1)]
    eq["window"] = [str(win0), str(win1)]
    eq["deposits_native_by_currency_in_window"] = {k: round(float(v), 4) for k, v in dep_w.groupby("currency")["amt"].sum().items()}
    eq["deposits_count_in_window"] = int(len(dep_w))
    eq["withdrawals_native_by_currency_in_window"] = {k: round(float(v), 4) for k, v in wd_w.groupby("currency")["amt"].sum().items()}
    eq["withdrawals_count_in_window"] = int(len(wd_w))
    eq["first_deposit"] = {"ts": str(dep["ts"].min()), "currency": dep.loc[dep["ts"].idxmin(), "currency"],
                           "amt_native": float(dep.loc[dep["ts"].idxmin(), "amt"])}
    # stable-only path
    flows = pd.concat([dep_w[dep_w["currency"] == "USDT"][["ts", "amt"]].assign(kind="dep"),
                       wd_w[wd_w["currency"] == "USDT"][["ts", "amt"]].assign(amt=lambda x: -x["amt"], kind="wd"),
                       df[["closed", "realized_usd"]].rename(columns={"closed": "ts", "realized_usd": "amt"}).assign(kind="pnl")])
    flows = flows.sort_values("ts")
    flows["cum"] = flows["amt"].cumsum()
    mm = flows.set_index("ts")["amt"].resample("MS").sum().cumsum()
    eq["stable_only_equity_path_monthly_usd"] = {str(k.date()): round(float(v), 2) for k, v in mm.items()}
    eq["stable_only_usdt_deposits_in_window_usd"] = round(float(dep_w[dep_w["currency"] == "USDT"]["amt"].sum()), 2)
    eq["stable_only_usdt_withdrawals_in_window_usd"] = round(float(wd_w[wd_w["currency"] == "USDT"]["amt"].sum()), 2)
    # withdrawals clustered around the big win
    big_close = top1["closed"]
    near = wd_ok[(wd_ok["ts"] >= big_close - pd.Timedelta(days=3)) & (wd_ok["ts"] <= big_close + pd.Timedelta(days=3))]
    eq["withdrawals_within_3d_of_largest_win_native"] = [{"ts": str(r.ts), "currency": r.currency, "amt_native": round(float(r.amt), 4)}
                                                         for r in near.itertuples()]
else:
    eq["files_present"] = False
out["equity_path"] = eq

OUT.write_text(json.dumps(out, indent=2, default=str))
print(json.dumps({k: out[k] for k in ["n_positions", "cum_realized_pnl_usd", "concentration", "win_rate", "payoff_ratio",
                                      "per_trade_realized_usd", "hold_minutes", "side_split", "hold_bucket",
                                      "after_loss_next_trade", "after_win_next_trade"]}, indent=1, default=str))
print("symbols:", json.dumps(out["symbols"], default=str))
print("lev:", json.dumps(out["leverage_split"], default=str))
print("hour_pt:", json.dumps(out["time_of_day_hour_pt"], default=str))
print("dow:", json.dumps(out["day_of_week_utc_0=Mon"], default=str))
print("funding:", out["funding_by_side_usd"], out["funding_usd_total"])
print("equity:", json.dumps(eq, indent=1, default=str))
print("monthly cum:", out["monthly_cum_realized_usd"])
print("wrote", OUT)
