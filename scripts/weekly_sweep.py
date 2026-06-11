"""Weekly backtester parameter sweep — runs Sunday 8 PM PT via com.phmex.weekly-sweep.

Grid: AE on/off, hour-blocklist on/off, AE threshold variants. Each variant runs the
calibrated (OHLCV-portable gates) backtester on the rolling 30d ETH/USDT window and
ranks by net PnL. Output ranked candidate list to reports/sweep_YYYY-MM-DD.md and
Telegrams a 5-line summary.

NOTE: backtester still overfires by ~10x without flow-replay (per 2026-05-10 calibration).
Use rankings to SCREEN candidates — absolute PnL is not trustworthy yet.
"""
from __future__ import annotations

import datetime
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import ccxt  # noqa: E402

import notifier  # noqa: E402
from backtest import fetch_ohlcv_full, run_backtest  # noqa: E402

REPORTS_DIR = REPO_ROOT / "reports"
SYMBOL = "ETH/USDT:USDT"
WINDOW_DAYS = 30

VARIANTS = [
    # (label, ae_threshold, ae_cycles)
    ("baseline_ae_off",     -999.0, 10),
    ("ae_-2.0",                -2.0, 10),
    ("ae_-3.0",                -3.0, 10),
    ("ae_-4.0",                -4.0, 10),
    ("ae_-5.0",                -5.0, 10),
    ("ae_-3.0_cycles5",        -3.0, 5),
    ("ae_-3.0_cycles20",       -3.0, 20),
]


@dataclass
class Result:
    label: str
    trades: int
    net_pnl: float
    wr: float


def run_one(label: str, df_5m, df_1h, ae_threshold: float, ae_cycles: int) -> Result:
    trades = run_backtest(
        {SYMBOL: df_5m},
        htf_data={SYMBOL: df_1h},
        no_gates=False,
        calibration_mode=True,
        ae_threshold=ae_threshold,
        ae_cycles=ae_cycles,
    )
    net = sum(t.pnl_usd for t in trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    wr = wins / len(trades) * 100 if trades else 0.0
    return Result(label=label, trades=len(trades), net_pnl=net, wr=wr)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()

    ex = ccxt.phemex({"enableRateLimit": True})
    try:
        ex.load_markets()
    except Exception as e:
        print(f"load_markets warn: {e}")

    print(f"Fetching {WINDOW_DAYS}d OHLCV for {SYMBOL}...")
    df_5m = fetch_ohlcv_full(ex, SYMBOL, "1m", WINDOW_DAYS)
    df_1h = fetch_ohlcv_full(ex, SYMBOL, "1h", WINDOW_DAYS)
    if df_5m.empty or df_1h.empty:
        print("OHLCV fetch returned empty. Aborting.")
        return 1

    results: list[Result] = []
    for label, ae_t, ae_c in VARIANTS:
        print(f"\n--- {label} (ae_t={ae_t}, ae_c={ae_c}) ---")
        r = run_one(label, df_5m, df_1h, ae_t, ae_c)
        print(f"  trades={r.trades} net=${r.net_pnl:+.2f} wr={r.wr:.1f}%")
        results.append(r)

    results.sort(key=lambda x: x.net_pnl, reverse=True)
    elapsed = time.time() - start

    today = datetime.date.today().isoformat()
    report_path = REPORTS_DIR / f"sweep_{today}.md"
    lines = [
        f"# Weekly Sweep — {today}",
        f"Window: rolling {WINDOW_DAYS}d ETH/USDT | Elapsed: {elapsed:.0f}s",
        "",
        "⚠️ Backtester still overfires ~10x vs live without flow replay.",
        "Use ranking only; ignore absolute PnL until flow-replay is wired.",
        "",
        "| Rank | Variant | Trades | Net PnL | WR |",
        "|------|---------|--------|---------|----|",
    ]
    for i, r in enumerate(results, start=1):
        lines.append(f"| {i} | `{r.label}` | {r.trades} | ${r.net_pnl:+.2f} | {r.wr:.1f}% |")
    report_path.write_text("\n".join(lines) + "\n")

    # Telegram summary
    top3 = results[:3]
    tg = [f"[SWEEP {today}] {len(results)} variants, {elapsed:.0f}s"]
    tg.append("Top 3 (ranking-only):")
    for i, r in enumerate(top3, start=1):
        tg.append(f"  {i}. {r.label}: ${r.net_pnl:+.2f} ({r.trades}t, {r.wr:.0f}%)")
    tg.append(f"Full: reports/sweep_{today}.md")
    try:
        notifier.send("\n".join(tg))
    except Exception as e:
        print(f"telegram send failed: {e}")

    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
