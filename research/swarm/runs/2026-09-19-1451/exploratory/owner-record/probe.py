"""EXPLORATORY probe — owner-record lens (analyst #8), run 2026-09-19-1451.
NOT a screen. Reads local owner_trades files only (api_closed_pnl.json,
api_deposit_list_full.json, api_withdraw_list_full.json). No holdout data,
no bot trading files, no load_data calls (this is not a mr_edge/long_1h
signal probe -- it is a probe over the owner's own 2022-2023 inverse-contract
trade history, which is not one of the screenable datasets at all).

Writes: research/swarm/runs/2026-09-19-1451/theses/owner_record_probe.json
"""
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

KB = "research/swarm/kb/owner_trades"

closed = json.load(open(f"{KB}/api_closed_pnl.json"))
deposits = json.load(open(f"{KB}/api_deposit_list_full.json"))
withdrawals = json.load(open(f"{KB}/api_withdraw_list_full.json"))

# realizedPnlEv is a string of raw Ev units; /1e4 = USD (per SOURCES.md decode).
def pnl_usd(row):
    return int(row["realizedPnlEv"]) / 1e4

# NOTE: despite the field name "...Ns" (nanoseconds), empirically these values are
# MILLISECONDS since epoch -- e.g. row[0]["openedTimeNs"]="1648275092166" / 1e3 =
# 2022-03-26 06:11:32 UTC, matching SOURCES.md's independently-stated earliest date.
# Dividing by 1e9 (treating as true nanoseconds) yields 1970 dates -- verified wrong.
def opened_dt(row):
    return datetime.fromtimestamp(int(row["openedTimeNs"]) / 1e3, tz=timezone.utc)

rows = sorted(closed, key=lambda r: int(r["openedTimeNs"]))
n = len(rows)
pnls = [pnl_usd(r) for r in rows]

# 1. Cumulative realized PnL path (no deposit/withdrawal $-value conversion attempted --
#    deposit/withdrawal rows here are in raw asset units per currency, not USD, so a true
#    USD equity curve cannot be built from these two files without price-at-time lookups
#    for XRP/ADA/etc, which SOURCES.md explicitly says was not attempted). We therefore
#    report cumulative realized PnL only, and separately report deposit/withdrawal ROW
#    COUNTS/currencies (not a USD equity curve) so this is not conflated with equity.
cum = []
running = 0.0
for p in pnls:
    running += p
    cum.append(running)

peak_cum = max(cum)
peak_idx = cum.index(peak_cum)
final_cum = cum[-1]
trough_cum = min(cum[: peak_idx + 1]) if peak_idx > 0 else cum[0]

# 2. Concentration: share of total positive PnL from single largest trade and top-5.
pos_pnls = [p for p in pnls if p > 0]
total_pos = sum(pos_pnls)
sorted_pos = sorted(pos_pnls, reverse=True)
largest_share = sorted_pos[0] / total_pos if total_pos else None
top5_share = sum(sorted_pos[:5]) / total_pos if total_pos else None

# 3. Win rate, payoff ratio.
wins = [p for p in pnls if p > 0]
losses = [p for p in pnls if p < 0]
flats = [p for p in pnls if p == 0]
win_rate = len(wins) / n
avg_win = statistics.mean(wins) if wins else None
avg_loss = statistics.mean(losses) if losses else None
payoff_ratio = (avg_win / abs(avg_loss)) if (avg_win and avg_loss) else None

# 4. Median hold time (updatedTimeNs - openedTimeNs, in this dataset "updatedTimeNs" is the
#    last update to the closed position record, used here as a proxy for close time; both are
#    fields directly present on every row -- see api_closed_pnl.json schema in SOURCES.md).
holds_sec = [(int(r["updatedTimeNs"]) - int(r["openedTimeNs"])) / 1e3 for r in rows]
holds_sec = [h for h in holds_sec if h >= 0]
median_hold_sec = statistics.median(holds_sec) if holds_sec else None

# 5. Symbols.
symbol_counts = Counter(r["symbol"] for r in rows)

# 6. Side split. side: "1"=Buy(long), "2"=Sell(short) per Phemex API convention.
side_counts = Counter(r["side"] for r in rows)

# 7. Time-of-day (UTC hour) of trade open.
hour_counts = Counter(opened_dt(r).hour for r in rows)

# 8. Behavior after a loss: size (cumEntryValueEv proxy / closedSize), side, hold of the
#    NEXT trade (by opened_time order) following a losing trade.
next_after_loss_sizes = []
next_after_loss_holds = []
next_after_loss_same_side = 0
next_after_loss_pairs = 0
for i in range(n - 1):
    if pnls[i] < 0:
        next_after_loss_pairs += 1
        cur = rows[i]
        nxt = rows[i + 1]
        next_after_loss_sizes.append(float(nxt["closedSize"]))
        next_after_loss_holds.append(holds_sec[i + 1] if i + 1 < len(holds_sec) else None)
        if nxt["side"] == cur["side"]:
            next_after_loss_same_side += 1

all_sizes = [float(r["closedSize"]) for r in rows]
avg_size_all = statistics.mean(all_sizes)
avg_size_after_loss = statistics.mean(next_after_loss_sizes) if next_after_loss_sizes else None
avg_hold_after_loss = statistics.mean([h for h in next_after_loss_holds if h is not None]) if next_after_loss_holds else None

out = {
    "note": "PROBE, not a thesis or a screen result. Source files: api_closed_pnl.json (819 rows), "
            "api_deposit_list_full.json, api_withdraw_list_full.json, all under research/swarm/kb/owner_trades/.",
    "n_closed_positions": n,
    "date_range": {
        "earliest": rows[0]["openedTimeNs"] and str(opened_dt(rows[0])),
        "latest": str(opened_dt(rows[-1])),
    },
    "equity_path_caveat": (
        "deposit/withdrawal files exist but are in raw per-currency asset units "
        "(e.g. XRP, ADA units), not USD -- SOURCES.md confirms no USD conversion was "
        "attempted. A true USD equity curve was NOT built. Reporting cumulative REALIZED "
        "PnL only (sum of realizedPnlEv/1e4, field: closed[i]['realizedPnlEv']), which "
        "excludes deposits/withdrawals and unrealized PnL."
    ),
    "cumulative_realized_pnl_usd": {
        "field": "sum(realizedPnlEv)/1e4 across all 819 rows, chronological by openedTimeNs",
        "final": round(final_cum, 2),
        "peak": round(peak_cum, 2),
        "peak_at_row_index_chronological": peak_idx,
        "peak_at_date": str(opened_dt(rows[peak_idx])),
    },
    "concentration": {
        "field": "realizedPnlEv/1e4, positive rows only, n_positive=" + str(len(pos_pnls)),
        "total_positive_pnl_usd": round(total_pos, 2),
        "largest_single_trade_share_of_total_positive": round(largest_share, 4) if largest_share else None,
        "top5_trades_share_of_total_positive": round(top5_share, 4) if top5_share else None,
        "largest_trade_pnl_usd": round(sorted_pos[0], 2) if sorted_pos else None,
    },
    "win_rate": {"field": "count(realizedPnlEv>0)/n", "value": round(win_rate, 4), "n_wins": len(wins), "n_losses": len(losses), "n_flat": len(flats)},
    "payoff_ratio": {
        "field": "mean(realizedPnlEv>0)/abs(mean(realizedPnlEv<0)), both /1e4",
        "avg_win_usd": round(avg_win, 2) if avg_win else None,
        "avg_loss_usd": round(avg_loss, 2) if avg_loss else None,
        "ratio": round(payoff_ratio, 3) if payoff_ratio else None,
    },
    "median_hold": {
        "field": "median(updatedTimeNs - openedTimeNs)/1e9 seconds, both fields on api_closed_pnl.json rows",
        "seconds": round(median_hold_sec, 1) if median_hold_sec else None,
        "hours": round(median_hold_sec / 3600, 2) if median_hold_sec else None,
    },
    "symbols": {"field": "Counter(row['symbol'])", "top10": symbol_counts.most_common(10), "n_unique_symbols": len(symbol_counts)},
    "side_split": {"field": "Counter(row['side']) -- '1'=long/Buy, '2'=short/Sell per Phemex convention", "counts": dict(side_counts)},
    "time_of_day_utc_hour": {"field": "Counter(datetime.fromtimestamp(openedTimeNs/1e9, utc).hour)", "counts": dict(sorted(hour_counts.items()))},
    "behavior_after_loss": {
        "field": "for each losing row i (realizedPnlEv<0), inspect row i+1 (next trade by openedTimeNs order)",
        "n_loss_events_with_next_trade": next_after_loss_pairs,
        "avg_size_all_trades": round(avg_size_all, 4),
        "avg_size_of_trade_immediately_after_a_loss": round(avg_size_after_loss, 4) if avg_size_after_loss else None,
        "avg_hold_seconds_of_trade_immediately_after_a_loss": round(avg_hold_after_loss, 1) if avg_hold_after_loss else None,
        "pct_next_trade_same_side_as_losing_trade": round(next_after_loss_same_side / next_after_loss_pairs, 4) if next_after_loss_pairs else None,
    },
    "deposits_withdrawals_row_counts_not_usd_equity": {
        "field": "len(api_deposit_list_full.json), len(api_withdraw_list_full.json)",
        "n_deposits": len(deposits),
        "n_withdrawals": len(withdrawals),
    },
}

with open("research/swarm/runs/2026-09-19-1451/theses/owner_record_probe.json", "w") as f:
    json.dump(out, f, indent=2, default=str)

print(json.dumps(out, indent=2, default=str))
