#!/usr/bin/env python3
"""
ETH/USDT 12x Leverage — Live Paper Simulation
Uses real Phemex market data, no orders placed.
Runs until TARGET_TRADES completed trades are reached.
"""
import sys
import time
import ccxt
import pandas as pd
from datetime import datetime

sys.path.insert(0, ".")
from indicators import add_all_indicators
from strategies import combined_strategy, Signal

# ── Config ───────────────────────────────────────────────────────────────────
SYMBOL        = "ETH/USDT"
TIMEFRAME     = "15m"
LEVERAGE      = 12
BALANCE       = 10_000.0      # starting USDT
TRADE_PCT     = 2.0           # % of balance used as margin per trade
SL_PCT        = 2.0           # stop-loss % (price move)
TP_PCT        = 4.0           # take-profit % (price move)
TARGET_TRADES = 100
POLL_SECS     = 60            # check every 60s (Phemex rate limit friendly)
# ─────────────────────────────────────────────────────────────────────────────


def connect():
    ex = ccxt.phemex({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    ex.load_markets()
    return ex


def fetch_candles(ex) -> pd.DataFrame:
    ohlcv = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    return df


def print_trade(t: dict):
    sign = "+" if t["pnl_usdt"] >= 0 else ""
    print(
        f"  [{t['trade']:>3}] {t['reason']:2s} | "
        f"Entry {t['entry']:>9.2f} → Exit {t['exit']:>9.2f} | "
        f"PnL {sign}{t['pnl_usdt']:>8.2f} USDT  ({sign}{t['pnl_pct']:>5.1f}%)  "
        f"Balance: {t['balance']:>10.2f}"
    )


def print_summary(trades: list, final_balance: float):
    wins   = [t for t in trades if t["pnl_usdt"] > 0]
    losses = [t for t in trades if t["pnl_usdt"] <= 0]
    total  = sum(t["pnl_usdt"] for t in trades)
    wr     = len(wins) / len(trades) * 100
    avg_w  = sum(t["pnl_usdt"] for t in wins)  / len(wins)  if wins   else 0
    avg_l  = sum(t["pnl_usdt"] for t in losses) / len(losses) if losses else 0
    rr     = abs(avg_w / avg_l) if avg_l else float("inf")
    best   = max(trades, key=lambda t: t["pnl_usdt"])
    worst  = min(trades, key=lambda t: t["pnl_usdt"])

    peak = BALANCE
    max_dd = 0.0
    bal = BALANCE
    for t in trades:
        bal += t["pnl_usdt"]
        peak = max(peak, bal)
        dd = (peak - bal) / peak * 100
        max_dd = max(max_dd, dd)

    print("\n" + "=" * 64)
    print(f"  SIMULATION COMPLETE — ETH/USDT  {LEVERAGE}x Leverage")
    print("=" * 64)
    print(f"  Trades          : {len(trades)}")
    print(f"  Starting Balance: ${BALANCE:,.2f}")
    print(f"  Final Balance   : ${final_balance:,.2f}")
    print(f"  Net PnL         : ${total:+,.2f}  ({(final_balance/BALANCE-1)*100:+.2f}%)")
    print(f"  Win Rate        : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Avg Win         : ${avg_w:+.2f}")
    print(f"  Avg Loss        : ${avg_l:+.2f}")
    print(f"  Reward/Risk     : {rr:.2f}x")
    print(f"  Best Trade      : ${best['pnl_usdt']:+.2f}  ({best['pnl_pct']:+.1f}% leveraged)")
    print(f"  Worst Trade     : ${worst['pnl_usdt']:+.2f}  ({worst['pnl_pct']:+.1f}% leveraged)")
    print(f"  Max Drawdown    : {max_dd:.1f}%")
    print("=" * 64)
    print(f"  SL: {SL_PCT}% price → {SL_PCT*LEVERAGE:.0f}% of margin")
    print(f"  TP: {TP_PCT}% price → {TP_PCT*LEVERAGE:.0f}% of margin")
    print(f"  Margin/trade   : {TRADE_PCT}% of balance")
    print("=" * 64 + "\n")


def main():
    print("=" * 64)
    print(f"  ETH/USDT  {LEVERAGE}x Leverage  — Live Paper Simulation")
    print(f"  Target: {TARGET_TRADES} trades  |  Timeframe: {TIMEFRAME}")
    print(f"  SL: {SL_PCT}%  TP: {TP_PCT}%  Margin: {TRADE_PCT}% of balance")
    print("=" * 64)
    print("  Connecting to Phemex (live data, no orders placed)...\n")

    ex = connect()

    balance   = BALANCE
    trades    = []
    in_trade  = False
    entry_price = sl = tp = margin = leveraged_size = 0.0
    entry_time  = None
    last_candle_time = None

    print(f"  Watching {SYMBOL} — press Ctrl+C to stop early\n")
    print(f"  {'#':>3}  {'Reason':2}  {'Entry':>9}  {'Exit':>9}  {'PnL USDT':>10}  {'PnL%':>7}  Balance")
    print("  " + "-" * 60)

    while len(trades) < TARGET_TRADES and balance > 0:
        try:
            df = fetch_candles(ex)
        except Exception as e:
            print(f"  [fetch error] {e} — retrying in {POLL_SECS}s")
            time.sleep(POLL_SECS)
            continue

        # Only act on a new closed candle
        latest_ts = df.index[-2]  # -1 is still forming, -2 is last closed
        if latest_ts == last_candle_time:
            time.sleep(POLL_SECS)
            continue
        last_candle_time = latest_ts

        candle = df.iloc[-2]   # last closed candle
        high  = candle["high"]
        low   = candle["low"]
        close = candle["close"]

        if in_trade:
            hit_sl = low  <= sl
            hit_tp = high >= tp

            if hit_sl or hit_tp:
                exit_price = tp if (hit_tp and not hit_sl) else sl
                reason     = "TP" if exit_price == tp else "SL"

                pnl_usdt = (exit_price - entry_price) / entry_price * leveraged_size
                balance += pnl_usdt

                trade = {
                    "trade":    len(trades) + 1,
                    "entry":    entry_price,
                    "exit":     exit_price,
                    "margin":   margin,
                    "pnl_usdt": round(pnl_usdt, 2),
                    "pnl_pct":  round((exit_price - entry_price) / entry_price * LEVERAGE * 100, 2),
                    "balance":  round(balance, 2),
                    "reason":   reason,
                }
                trades.append(trade)
                in_trade = False
                print_trade(trade)

                if len(trades) >= TARGET_TRADES or balance <= 0:
                    break

        if not in_trade:
            window = add_all_indicators(df.iloc[:-1].copy())  # exclude forming candle
            if len(window) < 2:
                time.sleep(POLL_SECS)
                continue

            signal = combined_strategy(window)

            if signal.signal == Signal.BUY:
                entry_price    = close
                margin         = balance * (TRADE_PCT / 100)
                leveraged_size = margin * LEVERAGE
                sl             = entry_price * (1 - SL_PCT / 100)
                tp             = entry_price * (1 + TP_PCT / 100)
                entry_time     = latest_ts
                in_trade       = True
                print(f"\n  [ENTRY] {datetime.now().strftime('%H:%M:%S')}  {SYMBOL} @ {entry_price:.2f}"
                      f"  SL={sl:.2f}  TP={tp:.2f}  Margin=${margin:.2f}  Reason: {signal.reason}\n")

        time.sleep(POLL_SECS)

    print_summary(trades, balance)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Simulation stopped by user.")
