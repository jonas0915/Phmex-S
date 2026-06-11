"""
Calibration comparison: backtester vs live PnL on a held-out window.

Reads `trading_state.json`, filters live closed_trades by symbol + strategy + date
range, then runs the backtester in --calibration mode on the same window and prints
both numbers + the delta. Pass criterion (per spec): PnL within ±15% AND
trade count within ±30% of live baseline on at least one strategy × symbol × 30d slice.

Usage:
    python scripts/calibrate_compare.py \\
        --symbol ETH/USDT:USDT \\
        --strategy htf_confluence_pullback \\
        --start 2026-04-02 --end 2026-05-02
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import ccxt  # noqa: E402

from backtest import fetch_ohlcv_full, run_backtest  # noqa: E402

STATE_PATH = REPO_ROOT / "trading_state.json"

PNL_TOL = 0.15
COUNT_TOL = 0.30


def parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def load_live(symbol: str, strategy: str, start: datetime, end: datetime) -> dict:
    state = json.loads(STATE_PATH.read_text())
    trades = state.get("closed_trades", [])
    in_win = [
        t for t in trades
        if t.get("symbol") == symbol
        and t.get("strategy") == strategy
        and start.timestamp() <= t.get("closed_at", 0) <= end.timestamp()
    ]
    net = sum(t.get("net_pnl", t.get("pnl_usdt", 0.0)) for t in in_win)
    gross = sum(t.get("pnl_usdt", 0.0) for t in in_win)
    wins = sum(1 for t in in_win if t.get("net_pnl", t.get("pnl_usdt", 0)) > 0)
    return {
        "n": len(in_win),
        "net_pnl": net,
        "gross_pnl": gross,
        "win_rate": (wins / len(in_win) * 100) if in_win else 0.0,
    }


def run_sim(symbol: str, start: datetime, end: datetime, ae_threshold: float, ae_cycles: int) -> dict:
    days_from_now = max(1, (datetime.now(timezone.utc) - start).days + 2)
    print(f"  Fetching {days_from_now}d of OHLCV for {symbol}...", flush=True)

    exchange = ccxt.phemex({"enableRateLimit": True})
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"  [WARN] load_markets failed: {e}")

    df_5m = fetch_ohlcv_full(exchange, symbol, "1m", days_from_now)
    df_1h = fetch_ohlcv_full(exchange, symbol, "1h", days_from_now)
    if df_5m.empty or df_1h.empty:
        raise SystemExit("OHLCV fetch returned empty.")

    print(f"  Running backtest in calibration mode (AE threshold={ae_threshold}, cycles={ae_cycles})...", flush=True)
    trades = run_backtest(
        {symbol: df_5m},
        htf_data={symbol: df_1h},
        no_gates=False,
        calibration_mode=True,
        ae_threshold=ae_threshold,
        ae_cycles=ae_cycles,
    )

    def _utc(ts):
        return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")

    in_win = [t for t in trades if start <= _utc(t.exit_time) <= end]
    net = sum(t.pnl_usd for t in in_win)
    wins = sum(1 for t in in_win if t.pnl_usd > 0)
    return {
        "n": len(in_win),
        "net_pnl": net,
        "win_rate": (wins / len(in_win) * 100) if in_win else 0.0,
    }


def pct_delta(sim: float, live: float) -> str:
    if live == 0:
        return "n/a (live=0)" if sim == 0 else f"sim=${sim:+.2f} vs live=$0"
    delta = (sim - live) / abs(live) * 100
    return f"{delta:+.1f}%"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="ETH/USDT:USDT")
    p.add_argument("--strategy", default="htf_confluence_pullback")
    p.add_argument("--start", required=True, help="ISO date e.g. 2026-04-02")
    p.add_argument("--end", required=True, help="ISO date e.g. 2026-05-02")
    p.add_argument("--ae-threshold", type=float, default=-3.0,
                   help="AE threshold for sim (live had -3.0 in calibration window).")
    p.add_argument("--ae-cycles", type=int, default=10)
    args = p.parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end)

    print(f"\n=== Calibration Compare: {args.symbol} / {args.strategy} ===")
    print(f"Window: {start.date()} → {end.date()}\n")

    print("[1/2] Live baseline from trading_state.json:")
    live = load_live(args.symbol, args.strategy, start, end)
    print(f"  trades   : {live['n']}")
    print(f"  net_pnl  : ${live['net_pnl']:+.2f}")
    print(f"  gross_pnl: ${live['gross_pnl']:+.2f}")
    print(f"  win_rate : {live['win_rate']:.1f}%")

    if live["n"] == 0:
        print("\n  [WARN] No live trades in window. Cannot calibrate.")
        return

    print("\n[2/2] Backtester in calibration mode:")
    sim = run_sim(args.symbol, start, end, args.ae_threshold, args.ae_cycles)
    print(f"  trades   : {sim['n']}")
    print(f"  net_pnl  : ${sim['net_pnl']:+.2f}")
    print(f"  win_rate : {sim['win_rate']:.1f}%")

    print("\n=== Deltas ===")
    pnl_delta_pct = (sim["net_pnl"] - live["net_pnl"]) / abs(live["net_pnl"]) * 100 if live["net_pnl"] else float("nan")
    count_delta_pct = (sim["n"] - live["n"]) / live["n"] * 100 if live["n"] else float("nan")
    print(f"  PnL delta  : {pct_delta(sim['net_pnl'], live['net_pnl'])} (sim ${sim['net_pnl']:+.2f} vs live ${live['net_pnl']:+.2f})")
    print(f"  Count delta: {count_delta_pct:+.1f}% (sim {sim['n']} vs live {live['n']})")

    pnl_pass = abs(pnl_delta_pct) <= PNL_TOL * 100 if live["net_pnl"] else None
    count_pass = abs(count_delta_pct) <= COUNT_TOL * 100

    print("\n=== Verdict ===")
    print(f"  PnL within ±{PNL_TOL*100:.0f}%   : {'PASS' if pnl_pass else 'FAIL' if pnl_pass is False else 'N/A'}")
    print(f"  Count within ±{COUNT_TOL*100:.0f}%: {'PASS' if count_pass else 'FAIL'}")
    overall = pnl_pass and count_pass
    print(f"  CALIBRATION   : {'PASS' if overall else 'FAIL — needs Step 5 correction factor'}")


if __name__ == "__main__":
    main()
