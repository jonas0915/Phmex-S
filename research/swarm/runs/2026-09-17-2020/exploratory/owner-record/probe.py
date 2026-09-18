"""EXPLORATORY probe — owner's 2022 inverse-contract trade record.
NOT a screen. Numbers here are descriptive only, not evidence for any pass bar.
Source: research/swarm/kb/owner_trades/api_closed_pnl.json (819 rows, read-only, local file).
Deposit/withdraw files (api_deposit_list_full.json / api_withdraw_list_full.json) ARE present
(per SOURCES.md) so a true equity path is attempted using them.
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone

BASE = "research/swarm/kb/owner_trades"

with open(f"{BASE}/api_closed_pnl.json") as f:
    trades = json.load(f)

# Phemex Ev fields for this old inverse product use a 1e4 scale (verified in SOURCES.md
# by two independent recomputes: ADAUSD notional match, uBTCUSD price match).
def usd(ev_str):
    return float(ev_str) / 1e4

for r in trades:
    r["_realized_usd"] = usd(r["realizedPnlEv"])
    r["_pnl_usd"] = usd(r["closedPnlEv"])
    r["_fee_usd"] = usd(r["exchangeFeeEv"])
    r["_funding_usd"] = usd(r["fundingFeeEv"])
    r["_opened_ns"] = int(r["openedTimeNs"])
    r["_updated_ns"] = int(r["updatedTimeNs"])
    # openedTimeNs / updatedTimeNs are actually millisecond epoch values despite the field
    # name (verified: 1648275092166 ms = 2022-03-26, matching SOURCES.md's earliest-row date).
    r["_opened_dt"] = datetime.fromtimestamp(r["_opened_ns"] / 1000, tz=timezone.utc)
    r["_updated_dt"] = datetime.fromtimestamp(r["_updated_ns"] / 1000, tz=timezone.utc)
    r["_hold_s"] = (r["_updated_ns"] - r["_opened_ns"]) / 1000.0

trades_sorted = sorted(trades, key=lambda r: r["_updated_ns"])

# ---- 1. Equity path ----
try:
    with open(f"{BASE}/api_deposit_list_full.json") as f:
        deposits = json.load(f)
    with open(f"{BASE}/api_withdraw_list_full.json") as f:
        withdrawals = json.load(f)
    have_flows = True
except FileNotFoundError:
    deposits, withdrawals = [], []
    have_flows = False

equity_path_available = have_flows
equity_note = None
if have_flows:
    # Deposit/withdraw amounts are multi-currency (XRP, ADA, USDT, ETH, etc.) at raw
    # on-chain/exchange units -- there is no USD-at-time-of-flow conversion available
    # locally, so a clean USD equity(t) = start + deposits - withdrawals + realized_pnl
    # curve CANNOT be built from these files alone (confirmed: SOURCES.md section 2c/2d
    # explicitly flags this — deposits/withdrawals are non-USD units, not USD amounts).
    equity_path_available = False
    equity_note = ("deposit/withdraw files present but denominated in native asset units "
                    "(XRP/ADA/USDT/ETH/...), not USD-at-time -- no USD conversion source "
                    "available locally, so true USD equity(t) cannot be computed; falling "
                    "back to cumulative realized PnL only, per SOURCES.md sec 2c/2d")

cum = 0.0
cum_path = []
for r in trades_sorted:
    cum += r["_realized_usd"]
    cum_path.append((r["_updated_dt"].isoformat(), round(cum, 2)))

cum_final = round(cum, 2)
cum_min = min(c for _, c in cum_path)
cum_max = max(c for _, c in cum_path)

# ---- 2. Concentration ----
positive_trades = [r for r in trades if r["_realized_usd"] > 0]
total_positive_pnl = sum(r["_realized_usd"] for r in positive_trades)
positive_sorted = sorted(positive_trades, key=lambda r: r["_realized_usd"], reverse=True)
largest_trade_pnl = positive_sorted[0]["_realized_usd"] if positive_sorted else 0.0
top5_pnl = sum(r["_realized_usd"] for r in positive_sorted[:5])
share_largest = largest_trade_pnl / total_positive_pnl if total_positive_pnl else None
share_top5 = top5_pnl / total_positive_pnl if total_positive_pnl else None

# ---- 3. Win rate / payoff ----
n = len(trades)
wins = [r for r in trades if r["_realized_usd"] > 0]
losses = [r for r in trades if r["_realized_usd"] < 0]
flats = [r for r in trades if r["_realized_usd"] == 0]
win_rate = len(wins) / n
avg_win = statistics.mean(r["_realized_usd"] for r in wins) if wins else None
avg_loss = statistics.mean(r["_realized_usd"] for r in losses) if losses else None
payoff_ratio = (avg_win / abs(avg_loss)) if (avg_win and avg_loss) else None

# ---- 4. Median hold ----
holds_s = sorted(r["_hold_s"] for r in trades)
median_hold_s = statistics.median(holds_s)
median_hold_hr = median_hold_s / 3600.0

# ---- 5. Symbols ----
symbol_counts = defaultdict(int)
symbol_pnl = defaultdict(float)
for r in trades:
    symbol_counts[r["symbol"]] += 1
    symbol_pnl[r["symbol"]] += r["_realized_usd"]
symbols_by_count = sorted(symbol_counts.items(), key=lambda kv: -kv[1])
symbols_by_pnl = sorted(symbol_pnl.items(), key=lambda kv: -kv[1])

# ---- 6. Side split ----
# side: "1" = Buy (per SOURCES.md leverage/side field convention on this endpoint), "2" = Sell
side_counts = defaultdict(int)
side_pnl = defaultdict(float)
for r in trades:
    side_counts[r["side"]] += 1
    side_pnl[r["side"]] += r["_realized_usd"]

# ---- 7. Time of day (UTC, of open) ----
hour_counts = defaultdict(int)
hour_pnl = defaultdict(float)
for r in trades:
    h = r["_opened_dt"].hour
    hour_counts[h] += 1
    hour_pnl[h] += r["_realized_usd"]
hour_summary = {h: {"n": hour_counts[h], "pnl": round(hour_pnl[h], 2)} for h in sorted(hour_counts)}

# ---- 8. Behaviour after a loss ----
trades_chrono = trades_sorted  # sorted by updatedTimeNs (close time) = trade sequence
after_loss_sizes = []
after_loss_holds = []
after_loss_sides = defaultdict(int)
baseline_sizes = []
baseline_holds = []
baseline_sides = defaultdict(int)
for i in range(1, len(trades_chrono)):
    prev = trades_chrono[i - 1]
    cur = trades_chrono[i]
    size = abs(float(cur["cumEntryValueEv"]) / 1e4) if cur["cumEntryValueEv"] not in (None, "0") else None
    if prev["_realized_usd"] < 0:
        if size is not None:
            after_loss_sizes.append(size)
        after_loss_holds.append(cur["_hold_s"])
        after_loss_sides[cur["side"]] += 1
    else:
        if size is not None:
            baseline_sizes.append(size)
        baseline_holds.append(cur["_hold_s"])
        baseline_sides[cur["side"]] += 1

after_loss_summary = {
    "n_trades_after_a_loss": len(after_loss_holds),
    "median_size_usd_after_loss": statistics.median(after_loss_sizes) if after_loss_sizes else None,
    "median_size_usd_baseline": statistics.median(baseline_sizes) if baseline_sizes else None,
    "median_hold_s_after_loss": statistics.median(after_loss_holds),
    "median_hold_s_baseline": statistics.median(baseline_holds) if baseline_holds else None,
    "side_counts_after_loss": dict(after_loss_sides),
    "side_counts_baseline": dict(baseline_sides),
}

result = {
    "source_file": f"{BASE}/api_closed_pnl.json",
    "n_trades": n,
    "date_range_utc": [trades_sorted[0]["_opened_dt"].isoformat(), trades_sorted[-1]["_updated_dt"].isoformat()],
    "equity_path": {
        "true_usd_equity_available": equity_path_available,
        "note": equity_note,
        "fallback": "cumulative realized PnL (sum of realizedPnlEv/1e4, chronological by updatedTimeNs)",
        "cum_realized_pnl_final_usd": cum_final,
        "cum_realized_pnl_min_usd": round(cum_min, 2),
        "cum_realized_pnl_max_usd": round(cum_max, 2),
        "n_points": len(cum_path),
        "field": "realizedPnlEv/1e4 per row, api_closed_pnl.json",
    },
    "concentration": {
        "total_positive_pnl_usd": round(total_positive_pnl, 2),
        "n_positive_trades": len(positive_trades),
        "largest_single_trade_pnl_usd": round(largest_trade_pnl, 2),
        "share_of_positive_pnl_from_largest_trade": round(share_largest, 4) if share_largest is not None else None,
        "top5_trades_pnl_usd": round(top5_pnl, 2),
        "share_of_positive_pnl_from_top5_trades": round(share_top5, 4) if share_top5 is not None else None,
        "field": "realizedPnlEv/1e4, positive rows only, api_closed_pnl.json",
    },
    "win_rate": {
        "value": round(win_rate, 4),
        "n_wins": len(wins), "n_losses": len(losses), "n_flat": len(flats), "n_total": n,
        "field": "sign of realizedPnlEv, api_closed_pnl.json",
    },
    "payoff_ratio": {
        "avg_win_usd": round(avg_win, 2) if avg_win else None,
        "avg_loss_usd": round(avg_loss, 2) if avg_loss else None,
        "ratio": round(payoff_ratio, 3) if payoff_ratio else None,
        "field": "mean(realizedPnlEv/1e4) split by sign, api_closed_pnl.json",
    },
    "median_hold": {
        "seconds": round(median_hold_s, 1),
        "hours": round(median_hold_hr, 3),
        "field": "(updatedTimeNs - openedTimeNs)/1000, api_closed_pnl.json",
    },
    "symbols": {
        "n_distinct": len(symbol_counts),
        "top10_by_count": symbols_by_count[:10],
        "top10_by_pnl": [(s, round(p, 2)) for s, p in symbols_by_pnl[:10]],
        "bottom5_by_pnl": [(s, round(p, 2)) for s, p in symbols_by_pnl[-5:]],
        "field": "symbol column grouped, api_closed_pnl.json",
    },
    "side_split": {
        "counts": dict(side_counts),
        "pnl": {k: round(v, 2) for k, v in side_pnl.items()},
        "note": "side '1'/'2' raw codes from api_closed_pnl.json (ccxt/Phemex Buy/Sell convention unconfirmed at row level -- reporting raw codes only)",
        "field": "side column, api_closed_pnl.json",
    },
    "time_of_day_utc_of_open": hour_summary,
    "behaviour_after_a_loss": after_loss_summary,
}

out_path = "research/swarm/runs/2026-09-17-2020/theses/owner_record_probe.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2, default=str)

print(json.dumps(result, indent=2, default=str))
print(f"\nWROTE {out_path}")
