#!/usr/bin/env python3
"""Ground-truth the maker-fee hypothesis against Phemex's own fill records.

READ-ONLY: only calls fetch_my_trades. Never places/cancels orders.

Phase 1 (fetch): paginate fetch_my_trades per symbol (symbols taken from
trading_state.json closed_trades) from the earliest closed_trade backward
bound, caching raw fills to raw_fills.json. Re-runs reuse the cache unless
--refetch is passed.

Phase 2 (analyze):
  - maker vs taker split (count + notional), per side
  - ENTRY vs EXIT split by matching fills to closed_trades (symbol +
    timestamp within MATCH_WINDOW_SEC of opened_at / closed_at)
  - effective fee rate vs notional per bucket
  - total fees over the fetched window + annualized burn
  - cross-check vs trading_state.json fees_usdt
  - breakeven WR at measured fees vs canonical 0.12% taker RT vs
    full-maker 0.02% RT

Usage:
  python fee_truth.py            # fetch (cached) + analyze
  python fee_truth.py --refetch  # force re-fetch from Phemex
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # scripts/research/fee-truth-2026-06-11 -> Phmex-S
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from exchange import Exchange  # noqa: E402

STATE_FILE = ROOT / "trading_state.json"
RAW_FILE = HERE / "raw_fills.json"
SUMMARY_FILE = HERE / "summary.json"

MATCH_WINDOW_SEC = 60        # same as scripts/reconcile_phemex.py
PAGE_LIMIT = 200
SLEEP_BETWEEN_CALLS = 0.35   # on top of ccxt enableRateLimit
FEE_TOLERANCE_USDT = 0.05    # same as reconcile script

# Fee-rate scenarios (round-trip fraction of notional)
CANONICAL_TAKER_RT = 0.0012  # 0.06% taker per side x 2
FULL_MAKER_RT = 0.0002       # 0.01% maker per side x 2


# ---------------------------------------------------------------- fetch

def fetch_all_fills(symbols: list[str], since_ms: int) -> dict[str, list[dict]]:
    ex = Exchange()
    out: dict[str, list[dict]] = {}
    for i, sym in enumerate(symbols, 1):
        fills: dict[str, dict] = {}  # id -> fill (dedupe)
        cursor = since_ms
        pages = 0
        while True:
            try:
                batch = ex.client.fetch_my_trades(sym, since=cursor, limit=PAGE_LIMIT) or []
            except Exception as e:
                print(f"  [WARN] fetch_my_trades({sym}, since={cursor}) failed: {e}")
                break
            pages += 1
            new = 0
            max_ts = cursor
            for f in batch:
                fid = f.get("id") or f"{f.get('order')}:{f.get('timestamp')}:{f.get('price')}:{f.get('amount')}"
                if fid not in fills:
                    fills[fid] = f
                    new += 1
                ts = f.get("timestamp") or 0
                if ts > max_ts:
                    max_ts = ts
            if len(batch) < PAGE_LIMIT or new == 0:
                break
            cursor = max_ts + 1
            time.sleep(SLEEP_BETWEEN_CALLS)
        out[sym] = sorted(fills.values(), key=lambda f: f.get("timestamp") or 0)
        print(f"  [{i:>2}/{len(symbols)}] {sym:<20} fills={len(out[sym]):>4} pages={pages}")
        time.sleep(SLEEP_BETWEEN_CALLS)
    return out


def slim(f: dict) -> dict:
    """Keep only fields needed for analysis (raw 'info' kept for fee rate audit)."""
    fee = f.get("fee") or {}
    info = f.get("info") or {}
    return {
        "id": f.get("id"),
        "order": f.get("order"),
        "symbol": f.get("symbol"),
        "timestamp": f.get("timestamp"),
        "datetime": f.get("datetime"),
        "side": f.get("side"),
        "takerOrMaker": f.get("takerOrMaker"),
        "price": f.get("price"),
        "amount": f.get("amount"),
        "cost": f.get("cost"),
        "fee_cost": fee.get("cost"),
        "fee_currency": fee.get("currency"),
        "fee_rate": fee.get("rate"),
        "info_execFeeRv": info.get("execFeeRv"),
        "info_feeRateRr": info.get("feeRateRr"),
        "info_execStatus": info.get("execStatus"),
        "info_ordType": info.get("ordType"),
    }


# ---------------------------------------------------------------- analyze

def fill_fee(f: dict) -> float:
    c = f.get("fee_cost")
    if c is not None:
        try:
            return abs(float(c))
        except Exception:
            pass
    try:
        return abs(float(f.get("info_execFeeRv") or 0))
    except Exception:
        return 0.0


def load_closed_trades() -> list[dict]:
    data = json.loads(STATE_FILE.read_text())
    return data.get("closed_trades", []) or []


def classify_fills(all_fills: list[dict], closed_trades: list[dict]) -> None:
    """Tag each fill in-place with role: entry / exit / unmatched, and the trade key."""
    # index trades by symbol
    by_sym: dict[str, list[dict]] = defaultdict(list)
    for t in closed_trades:
        if t.get("symbol"):
            by_sym[t["symbol"]].append(t)
    for f in all_fills:
        f["role"] = "unmatched"
        f["trade_key"] = None
        ts = (f.get("timestamp") or 0) / 1000
        best = None  # (distance, role, key)
        for t in by_sym.get(f.get("symbol") or "", []):
            for role, anchor in (("entry", t.get("opened_at")), ("exit", t.get("closed_at"))):
                if not anchor:
                    continue
                d = abs(ts - anchor)
                if d <= MATCH_WINDOW_SEC and (best is None or d < best[0]):
                    best = (d, role, (t.get("opened_at"), t.get("symbol"), t.get("closed_at")))
        if best:
            f["role"] = best[1]
            f["trade_key"] = best[2]


def bucket_stats(fills: list[dict]) -> dict:
    n = len(fills)
    notional = sum(float(f.get("cost") or 0) for f in fills)
    fees = sum(fill_fee(f) for f in fills)
    return {
        "fills": n,
        "notional": round(notional, 4),
        "fees": round(fees, 6),
        "fee_rate_pct": round(100 * fees / notional, 6) if notional else None,
    }


def pct(a, b):
    return round(100 * a / b, 2) if b else None


def main():
    refetch = "--refetch" in sys.argv

    closed_trades = load_closed_trades()
    symbols = sorted({t.get("symbol") for t in closed_trades if t.get("symbol")})
    earliest_open = min(t.get("opened_at") or 9e12 for t in closed_trades)
    since_ms = int((earliest_open - 86400) * 1000)  # 1 day pad before first trade

    if RAW_FILE.exists() and not refetch:
        print(f"Using cached fills: {RAW_FILE}")
        raw = json.loads(RAW_FILE.read_text())
    else:
        if not Config.is_live():
            print("[ERROR] not live mode — no API keys"); return
        print(f"Fetching fills for {len(symbols)} symbols since "
              f"{time.strftime('%Y-%m-%d %I:%M %p', time.localtime(since_ms/1000))} local ...")
        fills_by_sym = fetch_all_fills(symbols, since_ms)
        raw = {sym: [slim(f) for f in fl] for sym, fl in fills_by_sym.items()}
        RAW_FILE.write_text(json.dumps(raw, indent=1))
        print(f"Saved raw fills -> {RAW_FILE}")

    all_fills = [f for fl in raw.values() for f in fl]
    all_fills.sort(key=lambda f: f.get("timestamp") or 0)
    if not all_fills:
        print("No fills returned."); return

    first_ts = all_fills[0]["timestamp"] / 1000
    last_ts = all_fills[-1]["timestamp"] / 1000
    window_days = (last_ts - first_ts) / 86400
    fmt = lambda s: time.strftime("%Y-%m-%d %I:%M %p", time.localtime(s))

    classify_fills(all_fills, closed_trades)

    print()
    print("=" * 72)
    print("PHEMEX FILL GROUND TRUTH")
    print("=" * 72)
    print(f"Fetched fills: {len(all_fills)} across {sum(1 for s in raw if raw[s])} symbols")
    print(f"Window: {fmt(first_ts)} -> {fmt(last_ts)} local ({window_days:.1f} days)")
    print(f"Requested since: {fmt(since_ms/1000)} (earliest closed_trade minus 1d)")

    # ---- maker/taker split
    makers = [f for f in all_fills if f.get("takerOrMaker") == "maker"]
    takers = [f for f in all_fills if f.get("takerOrMaker") == "taker"]
    other = [f for f in all_fills if f.get("takerOrMaker") not in ("maker", "taker")]
    tot_notional = sum(float(f.get("cost") or 0) for f in all_fills)
    tot_fees = sum(fill_fee(f) for f in all_fills)
    print()
    print("--- Maker vs taker (ALL fills) ---")
    for name, b in (("maker", makers), ("taker", takers), ("unknown", other)):
        if not b and name == "unknown":
            continue
        s = bucket_stats(b)
        print(f"{name:<8} fills={s['fills']:>4} ({pct(s['fills'], len(all_fills))}%)  "
              f"notional=${s['notional']:>10.2f} ({pct(s['notional'], tot_notional)}%)  "
              f"fees=${s['fees']:>8.4f}  rate={s['fee_rate_pct']}%")
    print(f"{'TOTAL':<8} fills={len(all_fills):>4}        notional=${tot_notional:>10.2f}        "
          f"fees=${tot_fees:>8.4f}  rate={round(100*tot_fees/tot_notional, 6)}%")

    # negative fee = maker rebate check
    neg_fee = [f for f in all_fills if (f.get("fee_cost") or 0) and float(f["fee_cost"]) < 0]
    print(f"Fills with negative fee (rebate): {len(neg_fee)}")

    # ---- entry vs exit
    print()
    print("--- ENTRY vs EXIT (matched to closed_trades within "
          f"{MATCH_WINDOW_SEC}s) ---")
    roles = {}
    for role in ("entry", "exit", "unmatched"):
        sub = [f for f in all_fills if f["role"] == role]
        roles[role] = sub
        s = bucket_stats(sub)
        mk = sum(1 for f in sub if f.get("takerOrMaker") == "maker")
        tk = sum(1 for f in sub if f.get("takerOrMaker") == "taker")
        mk_not = sum(float(f.get("cost") or 0) for f in sub if f.get("takerOrMaker") == "maker")
        print(f"{role:<10} fills={s['fills']:>4}  maker={mk} ({pct(mk, len(sub))}%)  "
              f"taker={tk}  maker_notional%={pct(mk_not, s['notional'])}  "
              f"fees=${s['fees']:.4f}  rate={s['fee_rate_pct']}%")

    # round-trip rate from matched entry+exit
    matched = roles["entry"] + roles["exit"]
    m_not = sum(float(f.get("cost") or 0) for f in matched)
    m_fee = sum(fill_fee(f) for f in matched)
    # RT rate = total fee / one-side notional (entry side) since RT spans 2 legs
    e_not = sum(float(f.get("cost") or 0) for f in roles["entry"])
    print()
    if e_not:
        print(f"Round-trip fee rate (matched fees / entry notional): "
              f"{100 * m_fee / e_not:.4f}%")
    print(f"Blended per-side fee rate (matched): {100 * m_fee / m_not:.4f}%" if m_not else "")

    # ---- per-trade aggregation + cross-check vs fees_usdt
    fee_by_trade: dict[tuple, float] = defaultdict(float)
    for f in matched:
        fee_by_trade[f["trade_key"]] += fill_fee(f)

    trades_by_key = {(t.get("opened_at"), t.get("symbol"), t.get("closed_at")): t
                     for t in closed_trades}
    with_fees = [t for t in closed_trades if t.get("fees_usdt") is not None]
    both = []  # (trade, local_fee, phemex_fee)
    for key, pfee in fee_by_trade.items():
        t = trades_by_key.get(key)
        if t is not None and t.get("fees_usdt") is not None:
            both.append((t, float(t["fees_usdt"]), pfee))
    print()
    print("--- Cross-check vs trading_state.json fees_usdt ---")
    print(f"closed_trades with fees_usdt recorded: {len(with_fees)}")
    print(f"of those, matched to Phemex fills here: {len(both)}")
    if both:
        loc = sum(b[1] for b in both)
        ph = sum(b[2] for b in both)
        drift = [b for b in both if abs(b[1] - b[2]) > FEE_TOLERANCE_USDT]
        print(f"sum local fees_usdt = ${loc:.4f} | sum Phemex fees = ${ph:.4f} | "
              f"delta = ${ph - loc:+.4f}")
        print(f"trades with |delta| > ${FEE_TOLERANCE_USDT}: {len(drift)}")
        for t, lf, pf in sorted(drift, key=lambda x: -abs(x[1]-x[2]))[:10]:
            ts = time.strftime("%m-%d %I:%M %p", time.localtime(t.get("closed_at") or 0))
            print(f"  {ts} {t.get('symbol'):<18} local={lf:.4f} phemex={pf:.4f} "
                  f"d={pf-lf:+.4f}")

    # ---- trades fully matched (entry+exit fills found) for per-trade fee stats
    trade_roles: dict[tuple, set] = defaultdict(set)
    for f in matched:
        trade_roles[f["trade_key"]].add(f["role"])
    full_rt_keys = [k for k, r in trade_roles.items() if r == {"entry", "exit"}]
    print()
    print(f"Trades with BOTH entry and exit fills matched: {len(full_rt_keys)}")
    rt_fees, rt_notionals, rt_rates = [], [], []
    rt_entry_maker = rt_exit_maker = 0
    for k in full_rt_keys:
        efs = [f for f in matched if f["trade_key"] == k and f["role"] == "entry"]
        xfs = [f for f in matched if f["trade_key"] == k and f["role"] == "exit"]
        fee = sum(fill_fee(f) for f in efs + xfs)
        ent_not = sum(float(f.get("cost") or 0) for f in efs)
        if ent_not <= 0:
            continue
        rt_fees.append(fee)
        rt_notionals.append(ent_not)
        rt_rates.append(fee / ent_not)
        if all(f.get("takerOrMaker") == "maker" for f in efs):
            rt_entry_maker += 1
        if all(f.get("takerOrMaker") == "maker" for f in xfs):
            rt_exit_maker += 1
    if rt_rates:
        rt_rates_s = sorted(rt_rates)
        med_rt = rt_rates_s[len(rt_rates_s)//2]
        avg_rt = sum(rt_rates) / len(rt_rates)
        print(f"Per-trade RT fee rate: mean={100*avg_rt:.4f}%  median={100*med_rt:.4f}%  "
              f"min={100*rt_rates_s[0]:.4f}%  max={100*rt_rates_s[-1]:.4f}%")
        print(f"All-maker entry leg: {rt_entry_maker}/{len(full_rt_keys)} "
              f"({pct(rt_entry_maker, len(full_rt_keys))}%)  "
              f"All-maker exit leg: {rt_exit_maker}/{len(full_rt_keys)} "
              f"({pct(rt_exit_maker, len(full_rt_keys))}%)")

    # ---- annualized burn
    print()
    print("--- Fee burn ---")
    print(f"Total fees in window ({window_days:.1f}d): ${tot_fees:.4f}")
    ann_window = tot_fees / window_days * 365 if window_days > 0 else 0
    print(f"Annualized at window rate: ${ann_window:.2f}/yr")
    # last-30d trade rate
    now = time.time()
    fills_30 = [f for f in all_fills if (f["timestamp"] or 0)/1000 >= now - 30*86400]
    fees_30 = sum(fill_fee(f) for f in fills_30)
    print(f"Last 30d: fills={len(fills_30)} fees=${fees_30:.4f} -> "
          f"annualized ${fees_30/30*365:.2f}/yr")

    # ---- breakeven WR
    print()
    print("--- Breakeven win rate ---")
    # use closed trades inside the fetched fill window with gross pnl recorded
    win_trades = [t for t in closed_trades
                  if (t.get("closed_at") or 0) >= first_ts and t.get("pnl_usdt") is not None]
    wins = [float(t["pnl_usdt"]) for t in win_trades if float(t["pnl_usdt"]) > 0]
    losses = [-float(t["pnl_usdt"]) for t in win_trades if float(t["pnl_usdt"]) < 0]
    notionals = [float(t.get("entry_price") or 0) * float(t.get("amount") or 0)
                 for t in win_trades]
    notionals = [n for n in notionals if n > 0]
    if wins and losses and notionals:
        W = sum(wins) / len(wins)
        L = sum(losses) / len(losses)
        N = sum(notionals) / len(notionals)
        measured_rt = (sum(rt_fees) / sum(rt_notionals)) if rt_notionals else None
        print(f"Trades in window with gross pnl: {len(win_trades)} "
              f"(wins={len(wins)}, losses={len(losses)})")
        print(f"avg gross win W=${W:.4f}  avg gross loss L=${L:.4f}  "
              f"avg notional N=${N:.2f}")
        scen = []
        if measured_rt is not None:
            scen.append(("MEASURED (live fills)", measured_rt))
        scen.append(("canonical 0.12% taker RT", CANONICAL_TAKER_RT))
        scen.append(("full-maker 0.02% RT", FULL_MAKER_RT))
        results = {}
        for name, rate in scen:
            F = rate * N
            be = (L + F) / (W + L)
            results[name] = be
            print(f"  {name:<28} fee/trade=${F:.4f}  breakeven WR={100*be:.2f}%")
        if measured_rt is not None:
            d1 = results["canonical 0.12% taker RT"] - results["MEASURED (live fills)"]
            d2 = results["MEASURED (live fills)"] - results["full-maker 0.02% RT"]
            print(f"Headroom: measured vs canonical = {100*d1:.2f} WR pts; "
                  f"measured vs full-maker = {100*d2:.2f} WR pts")

    # ---- save summary
    summary = {
        "generated_at": int(now),
        "window": {"first_fill": fmt(first_ts), "last_fill": fmt(last_ts),
                   "days": round(window_days, 2)},
        "fills": len(all_fills),
        "maker": bucket_stats(makers),
        "taker": bucket_stats(takers),
        "entry": bucket_stats(roles["entry"]),
        "exit": bucket_stats(roles["exit"]),
        "unmatched": bucket_stats(roles["unmatched"]),
        "total_fees": round(tot_fees, 6),
        "total_notional": round(tot_notional, 4),
        "annualized_window": round(ann_window, 2),
        "annualized_30d": round(fees_30/30*365, 2),
        "rt_trades_full": len(full_rt_keys),
        "rt_fee_rate_mean_pct": round(100*avg_rt, 6) if rt_rates else None,
        "rt_fee_rate_median_pct": round(100*med_rt, 6) if rt_rates else None,
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary saved -> {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
