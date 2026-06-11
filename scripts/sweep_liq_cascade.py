#!/usr/bin/env python3
"""Parameter sweep + out-of-sample validation for liquidation_cascade_strategy.

Pure-OHLCV strategy, so fully backtestable on history. Methodology to resist
overfitting (per lessons.md / research warnings):
  - IN-SAMPLE  = backtest_data/      (Jan 10 - Apr 10, 5 symbols)
  - OUT-SAMPLE = backtest_data_may/  (May 8 - 30, 16 symbols)
  Sweep on in-sample, then validate the top configs on out-of-sample.
  Deploy ONLY if a config is net-positive after fees in BOTH with meaningful n.

Exit model (conservative, faithful to live .env): fixed SL/TP resolved on candle
high/low, round-trip fees = (TAKER*2 + SLIPPAGE*2) of notional. No early_exit/
trailing modeled — for a momentum strategy that OMITS upside (trailing would let
runners run), so results are a PESSIMISTIC lower bound. That's the safe direction.

Reports net PnL, WR, profit factor, trade count, expectancy/trade per config.
Read-only on data; writes nothing except stdout.
"""
import os
import sys
import glob
import itertools

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicators import add_all_indicators

# --- live economics (.env) ---
LEVERAGE = 10
MARGIN = 10.0
NOTIONAL = MARGIN * LEVERAGE
TAKER = 0.0006
SLIP = 0.0005
ROUND_TRIP_FEE_USD = NOTIONAL * (TAKER * 2 + SLIP * 2)  # ~$0.22/trade
SL_PCT = 0.012   # .env STOP_LOSS_PERCENT
TP_PCT = 0.016   # .env TAKE_PROFIT_PERCENT
MAX_HOLD = 48    # candles (~4h on 5m) — live hard time exit
MIN_STRENGTH = 0.80  # .env SCALP_MIN_STRENGTH

IN_DIR = "backtest_data"
OUT_DIR = "backtest_data_may"
WARMUP = 50


def load(dir_path):
    """Return {symbol: df_with_indicators} for *_5m.csv in dir_path."""
    out = {}
    for f in sorted(glob.glob(os.path.join(dir_path, "*_5m.csv"))):
        sym = os.path.basename(f).replace("_5m.csv", "")
        df = pd.read_csv(f)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        df = add_all_indicators(df)
        if len(df) > WARMUP:
            out[sym] = df
    return out


def signal(row, prev_vol_avg, p):
    """Replica of liquidation_cascade_strategy with sweepable params p.
    Returns (direction, strength) or (None, 0)."""
    close, op = row["close"], row["open"]
    high, low = row["high"], row["low"]
    vol = row["volume"]
    rsi = row.get("rsi", 50)
    adx = row.get("adx", 0)
    if not all([close, op, high, low]) or prev_vol_avg <= 0:
        return None, 0
    vol_ratio = vol / prev_vol_avg
    if vol_ratio < p["vol"]:
        return None, 0
    rng = high - low
    if rng == 0:
        return None, 0
    if abs(close - op) / rng < p["body"]:
        return None, 0
    if adx < p["adx"]:
        return None, 0
    direction = "long" if close > op else "short"
    if direction == "long" and rsi < p["rsi_long"]:
        return None, 0
    if direction == "short" and rsi > p["rsi_short"]:
        return None, 0
    strength = 0.82 + (0.05 if vol_ratio > 3.5 else 0) + (0.05 if vol_ratio > 5 else 0) + (0.03 if adx > 40 else 0)
    return direction, min(strength, 0.95)


def backtest(data, p):
    """One config across all symbols. Returns dict of aggregate stats."""
    trades = []
    for sym, df in data.items():
        vol = df["volume"].values
        n = len(df)
        i = WARMUP
        while i < n - 1:
            row = df.iloc[i]
            prev_vol_avg = vol[i - 20:i].mean() if i >= 20 else 0
            direction, strength = signal(row, prev_vol_avg, p)
            if direction is None or strength < MIN_STRENGTH:
                i += 1
                continue
            # enter at next candle open (no lookahead on the signal candle's close)
            entry = float(df.iloc[i + 1]["open"]) if i + 1 < n else float(row["close"])
            entry *= (1 + SLIP) if direction == "long" else (1 - SLIP)
            if direction == "long":
                sl = entry * (1 - SL_PCT); tp = entry * (1 + TP_PCT)
            else:
                sl = entry * (1 + SL_PCT); tp = entry * (1 - TP_PCT)
            # resolve exit forward
            exit_px, held = None, 0
            for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
                c = df.iloc[j]; held = j - i
                if direction == "long":
                    if c["low"] <= sl: exit_px = sl; break
                    if c["high"] >= tp: exit_px = tp; break
                else:
                    if c["high"] >= sl: exit_px = sl; break
                    if c["low"] <= tp: exit_px = tp; break
            if exit_px is None:
                exit_px = float(df.iloc[min(i + MAX_HOLD, n - 1)]["close"])
            if direction == "long":
                gross = (exit_px - entry) / entry * NOTIONAL
            else:
                gross = (entry - exit_px) / entry * NOTIONAL
            net = gross - ROUND_TRIP_FEE_USD
            trades.append(net)
            i = i + held + 1  # no overlapping positions per symbol
    if not trades:
        return {"n": 0, "net": 0.0, "wr": 0.0, "pf": 0.0, "exp": 0.0}
    wins = [t for t in trades if t > 0]; losses = [t for t in trades if t <= 0]
    gp = sum(wins); gl = abs(sum(losses))
    return {
        "n": len(trades),
        "net": sum(trades),
        "wr": len(wins) / len(trades) * 100,
        "pf": (gp / gl) if gl > 0 else float("inf"),
        "exp": sum(trades) / len(trades),
    }


def main():
    print("Loading in-sample (Jan-Apr)...", flush=True)
    insample = load(IN_DIR)
    print(f"  {len(insample)} symbols: {', '.join(insample)}")
    print("Loading out-of-sample (May)...", flush=True)
    oos = load(OUT_DIR)
    print(f"  {len(oos)} symbols")

    grid = {
        "vol": [2.0, 2.5, 3.0, 4.0],
        "body": [0.6, 0.7, 0.8],
        "adx": [25, 30, 35],
        "rsi_long": [50, 55, 60],
        "rsi_short": [50, 45, 40],
    }
    keys = list(grid)
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print(f"\nSweeping {len(combos)} configs on in-sample...\n", flush=True)

    results = []
    for combo in combos:
        p = dict(zip(keys, combo))
        r = backtest(insample, p)
        results.append((p, r))

    # rank by in-sample expectancy, require meaningful n
    ranked = sorted([x for x in results if x[1]["n"] >= 20],
                    key=lambda x: x[1]["exp"], reverse=True)

    print("=== TOP 10 IN-SAMPLE (n>=20, by expectancy) ===")
    print(f"{'vol':>4} {'body':>4} {'adx':>3} {'rL':>3} {'rS':>3} | {'n':>4} {'net':>8} {'WR':>5} {'PF':>5} {'exp':>7}")
    for p, r in ranked[:10]:
        print(f"{p['vol']:>4} {p['body']:>4} {p['adx']:>3} {p['rsi_long']:>3} {p['rsi_short']:>3} | "
              f"{r['n']:>4} {r['net']:>+8.2f} {r['wr']:>5.1f} {r['pf']:>5.2f} {r['exp']:>+7.3f}")

    print("\n=== OUT-OF-SAMPLE VALIDATION of top 10 in-sample configs ===")
    print(f"{'vol':>4} {'body':>4} {'adx':>3} {'rL':>3} {'rS':>3} | "
          f"{'IS_n':>4} {'IS_exp':>7} | {'OOS_n':>5} {'OOS_net':>8} {'OOS_WR':>6} {'OOS_PF':>6} {'OOS_exp':>7}")
    deployable = []
    for p, r in ranked[:10]:
        o = backtest(oos, p)
        flag = ""
        if r["exp"] > 0 and o["exp"] > 0 and o["n"] >= 20:
            flag = "  <-- POSITIVE BOTH (n>=20)"
            deployable.append((p, r, o))
        print(f"{p['vol']:>4} {p['body']:>4} {p['adx']:>3} {p['rsi_long']:>3} {p['rsi_short']:>3} | "
              f"{r['n']:>4} {r['exp']:>+7.3f} | {o['n']:>5} {o['net']:>+8.2f} {o['wr']:>6.1f} "
              f"{o['pf']:>6.2f} {o['exp']:>+7.3f}{flag}")

    print("\n=== VERDICT ===")
    if deployable:
        print(f"{len(deployable)} config(s) positive in BOTH in-sample and out-of-sample (n>=20).")
        best = max(deployable, key=lambda x: x[2]["exp"])
        p, r, o = best
        print(f"BEST: {p}")
        print(f"  in-sample:  n={r['n']} net=${r['net']:+.2f} WR={r['wr']:.1f}% PF={r['pf']:.2f} exp=${r['exp']:+.3f}")
        print(f"  out-sample: n={o['n']} net=${o['net']:+.2f} WR={o['wr']:.1f}% PF={o['pf']:.2f} exp=${o['exp']:+.3f}")
    else:
        print("NO config is net-positive after fees in BOTH samples with n>=20.")
        print("=> Per the discipline bar, DEPLOY NOTHING. liq_cascade has no validated edge.")


if __name__ == "__main__":
    main()
