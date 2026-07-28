"""SR_BOUNCE kill-gate scan runner. Usage:
    python3 run_scan.py            # fetch/cache data, replay, write report
DOA line (pre-registered 2026-07-28): DO NOT BUILD if holdout
net-per-trade <= $0 fee-inclusive OR holdout trades < 20 (pooled)."""
import datetime
import os
import pandas as pd
from fetch_data import load_candles, scan_pairs
from engine import replay
from overlap import zone_proximity_report

HOLDOUT_DAYS = 30
BOT_DIR = os.path.expanduser("~/Desktop/Phmex-S")


def main():
    all_rows = []
    for sym in scan_pairs():
        df1h = load_candles(sym, "1h")
        df5m = load_candles(sym, "5m")
        if df5m.empty or df1h.empty:
            print(f"skip {sym}: no data")
            continue
        trades = replay(df1h, df5m, sym)
        all_rows.extend(trades)
        print(f"{sym}: {len(trades)} trades")
    df = pd.DataFrame(all_rows)
    date = datetime.date.today().isoformat()
    out = [f"# SR_BOUNCE kill-gate scan — {date}", ""]
    if df.empty:
        out.append("ZERO trades produced across all pairs → **DO-NOT-BUILD** (< 20 holdout trades).")
        verdict = "DO-NOT-BUILD"
    else:
        cut = df["exit_ts"].max() - HOLDOUT_DAYS * 86_400_000
        hold, train = df[df["signal_ts"] >= cut], df[df["signal_ts"] < cut]
        def stats(d, label):
            if d.empty:
                return f"**{label}**: 0 trades"
            wr = (d["net_usd"] > 0).mean() * 100
            return (f"**{label}**: {len(d)} trades | WR {wr:.1f}% | "
                    f"net ${d['net_usd'].sum():+.2f} | per-trade ${d['net_usd'].mean():+.4f} | "
                    f"avg risk {d['risk_pct'].mean():.2f}% / reward {d['reward_pct'].mean():.2f}%")
        out += [stats(train, "TRAIN (diagnostics only)"), "",
                stats(hold, "HOLDOUT (the verdict)"), ""]
        doa = hold.empty or len(hold) < 20 or hold["net_usd"].mean() <= 0
        verdict = "DO-NOT-BUILD" if doa else "BUILD"
        out.append(f"## VERDICT vs pre-registered DOA line: **{verdict}**")
        out.append("- line: holdout net-per-trade <= $0 fee-incl OR holdout n < 20")
        out += ["", "## Per-pair (all trades)"]
        for sym, g in df.groupby("symbol"):
            out.append(f"- {sym}: {len(g)} trades, net ${g['net_usd'].sum():+.2f}")
    out += ["", "## Bonus: real-trade zone-proximity diagnostic (report-only)"]
    try:
        r = zone_proximity_report(os.path.join(BOT_DIR, "trading_state.json"))
        out.append(f"- winners n={r['n_win']} median dist {r['median_win_dist']:.2f} ATR | "
                   f"losers n={r['n_loss']} median {r['median_loss_dist']:.2f} ATR | "
                   f"p={r['p']:.4f} | excluded {r['excluded']}")
    except Exception as e:
        out.append(f"- diagnostic failed: {e}")
    path = os.path.join(BOT_DIR, "reports", f"{date}-sr-bounce-scan.md")
    open(path, "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nreport → {path}")


if __name__ == "__main__":
    main()
