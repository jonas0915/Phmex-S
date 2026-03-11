"""
backtest.py — Standalone backtesting script for Phmex-S trading strategies.

Fetches historical OHLCV data from Phemex public API (no API key required),
applies the same indicators and combined strategy used by the live bot, and
simulates realistic trade execution with fees, slippage, partial TP, and
trailing stops.

Usage:
    python backtest.py
    python backtest.py --pairs ETH/USDT:USDT SOL/USDT:USDT --days 30 --timeframe 1m
    python backtest.py --strategy ema_scalp --days 7
"""

import argparse
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import ccxt
import pandas as pd

from indicators import add_all_indicators
from strategies import STRATEGIES, Signal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAKER_FEE_PCT  = 0.06   # 0.06% per side
SLIPPAGE_PCT   = 0.05   # 0.05% simulated slippage
SL_PCT         = 3.00   # stop-loss 3% from entry
TP_PCT         = 6.00   # take-profit 6% from entry
PARTIAL_CLOSE  = 0.50   # close 50% of position at TP
TRAILING_TRAIL = 2.00   # trailing stop trails 2% below/above high-water mark
TRADE_SIZE_USD = 1000.0 # notional position size in USD per trade

DEFAULT_PAIRS     = ["ETH/USDT:USDT", "SOL/USDT:USDT", "BTC/USDT:USDT"]
DEFAULT_DAYS      = 30
DEFAULT_TIMEFRAME = "1m"
DEFAULT_STRATEGY  = "combined"

# ccxt limit per single fetch_ohlcv call (Phemex caps at 1000)
FETCH_LIMIT = 1000

OUTPUT_FILE = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_results.txt"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Position:
    pair:           str
    direction:      str          # "long" or "short"
    entry_price:    float
    entry_time:     pd.Timestamp
    size_usd:       float        # full notional in USD
    remaining_frac: float = 1.0  # fraction of position still open (starts at 1.0)
    sl_price:       float = 0.0
    tp_price:       float = 0.0
    partial_hit:    bool  = False
    trailing_active: bool = False
    trail_ref:      float = 0.0  # high-water mark for trailing stop


@dataclass
class ClosedTrade:
    pair:        str
    direction:   str
    entry_price: float
    exit_price:  float
    entry_time:  pd.Timestamp
    exit_time:   pd.Timestamp
    pnl_pct:     float   # net PnL as % of notional (after fees)
    pnl_usd:     float   # net PnL in USD
    exit_reason: str     # "sl", "tp_partial", "tp_full", "trailing", "end_of_data"


# ---------------------------------------------------------------------------
# Fee & slippage helpers
# ---------------------------------------------------------------------------

def apply_slippage(price: float, direction: str, entering: bool) -> float:
    """Worsen fill price by slippage in the direction that hurts the trader."""
    factor = SLIPPAGE_PCT / 100.0
    if direction == "long":
        return price * (1 + factor) if entering else price * (1 - factor)
    else:  # short
        return price * (1 - factor) if entering else price * (1 + factor)


def round_trip_fee(notional_usd: float) -> float:
    """Total taker fees for one round trip (entry + exit)."""
    return notional_usd * 2 * TAKER_FEE_PCT / 100.0


def partial_fee(notional_usd: float) -> float:
    """Taker fee for one leg (e.g., partial close)."""
    return notional_usd * TAKER_FEE_PCT / 100.0


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_ohlcv_full(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    days: int,
) -> pd.DataFrame:
    """
    Fetch up to `days` worth of OHLCV data for `symbol` from Phemex.
    Paginates automatically if needed. Returns a DataFrame with a UTC
    DatetimeIndex.
    """
    tf_ms = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
        "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }
    if timeframe not in tf_ms:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    candle_ms   = tf_ms[timeframe]
    total_ms    = days * 24 * 3600 * 1000
    total_needed = total_ms // candle_ms
    now_ms      = int(datetime.now(timezone.utc).timestamp() * 1000)
    since_ms    = now_ms - total_ms

    all_ohlcv = []
    current_since = since_ms

    print(f"  Fetching {symbol} | {timeframe} | {days}d (~{total_needed} candles)...")

    while True:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=FETCH_LIMIT)
        except ccxt.RateLimitExceeded:
            print("  Rate limit hit, sleeping 10s...")
            time.sleep(10)
            continue
        except ccxt.NetworkError as e:
            print(f"  Network error: {e}. Retrying in 5s...")
            time.sleep(5)
            continue
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            break

        if not batch:
            break

        all_ohlcv.extend(batch)

        last_ts = batch[-1][0]
        if last_ts >= now_ms - candle_ms or len(batch) < FETCH_LIMIT:
            break

        current_since = last_ts + candle_ms
        time.sleep(0.3)  # polite rate limiting

    if not all_ohlcv:
        return pd.DataFrame()

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # Trim to requested range
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    df = df[df.index >= cutoff]

    print(f"  Got {len(df)} candles for {symbol}.")
    return df


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

def open_position(pair: str, signal: Signal, entry_price: float, entry_time: pd.Timestamp) -> Position:
    direction = "long" if signal == Signal.BUY else "short"
    fill = apply_slippage(entry_price, direction, entering=True)

    if direction == "long":
        sl = fill * (1 - SL_PCT / 100)
        tp = fill * (1 + TP_PCT / 100)
    else:
        sl = fill * (1 + SL_PCT / 100)
        tp = fill * (1 - TP_PCT / 100)

    return Position(
        pair=pair,
        direction=direction,
        entry_price=fill,
        entry_time=entry_time,
        size_usd=TRADE_SIZE_USD,
        remaining_frac=1.0,
        sl_price=sl,
        tp_price=tp,
        partial_hit=False,
        trailing_active=False,
        trail_ref=fill,
    )


def update_position(pos: Position, candle: pd.Series, candle_time: pd.Timestamp) -> Optional[ClosedTrade]:
    """
    Evaluate one candle against an open position.
    Returns a ClosedTrade if the position is fully closed, else None
    (position is mutated in place for partial closes).
    """
    high  = candle["high"]
    low   = candle["low"]
    close = candle["close"]

    if pos.direction == "long":
        # --- Stop-loss check ---
        if low <= pos.sl_price:
            exit_px = apply_slippage(pos.sl_price, "long", entering=False)
            return _close_trade(pos, exit_px, candle_time, "sl")

        # --- Partial TP at 50% ---
        if not pos.partial_hit and high >= pos.tp_price:
            # Partially close half at TP price
            partial_exit = apply_slippage(pos.tp_price, "long", entering=False)
            partial_notional = pos.size_usd * PARTIAL_CLOSE
            fee = partial_fee(partial_notional)
            raw_pnl_pct = (partial_exit - pos.entry_price) / pos.entry_price
            partial_pnl_usd = partial_notional * raw_pnl_pct - fee

            # Now activate trailing stop on the remainder
            pos.partial_hit    = True
            pos.remaining_frac = 1.0 - PARTIAL_CLOSE
            pos.trailing_active = True
            pos.trail_ref       = high  # high-water mark

            # Store the partial pnl on the position object to accumulate
            pos._partial_pnl_usd = partial_pnl_usd  # type: ignore[attr-defined]
            pos._partial_pnl_pct = raw_pnl_pct * PARTIAL_CLOSE  # type: ignore[attr-defined]
            return None

        # --- Trailing stop (only active after partial TP) ---
        if pos.trailing_active:
            # Update high-water mark
            if high > pos.trail_ref:
                pos.trail_ref = high
            trail_stop = pos.trail_ref * (1 - TRAILING_TRAIL / 100)
            if low <= trail_stop:
                exit_px = apply_slippage(trail_stop, "long", entering=False)
                return _close_trade(pos, exit_px, candle_time, "trailing")

    else:  # SHORT
        # --- Stop-loss check ---
        if high >= pos.sl_price:
            exit_px = apply_slippage(pos.sl_price, "short", entering=False)
            return _close_trade(pos, exit_px, candle_time, "sl")

        # --- Partial TP at 50% ---
        if not pos.partial_hit and low <= pos.tp_price:
            partial_exit = apply_slippage(pos.tp_price, "short", entering=False)
            partial_notional = pos.size_usd * PARTIAL_CLOSE
            fee = partial_fee(partial_notional)
            raw_pnl_pct = (pos.entry_price - partial_exit) / pos.entry_price
            partial_pnl_usd = partial_notional * raw_pnl_pct - fee

            pos.partial_hit    = True
            pos.remaining_frac = 1.0 - PARTIAL_CLOSE
            pos.trailing_active = True
            pos.trail_ref       = low  # low-water mark

            pos._partial_pnl_usd = partial_pnl_usd  # type: ignore[attr-defined]
            pos._partial_pnl_pct = raw_pnl_pct * PARTIAL_CLOSE  # type: ignore[attr-defined]
            return None

        # --- Trailing stop ---
        if pos.trailing_active:
            if low < pos.trail_ref:
                pos.trail_ref = low
            trail_stop = pos.trail_ref * (1 + TRAILING_TRAIL / 100)
            if high >= trail_stop:
                exit_px = apply_slippage(trail_stop, "short", entering=False)
                return _close_trade(pos, exit_px, candle_time, "trailing")

    return None


def _close_trade(pos: Position, exit_px: float, exit_time: pd.Timestamp, reason: str) -> ClosedTrade:
    """Build a ClosedTrade from a position being fully exited."""
    remaining_notional = pos.size_usd * pos.remaining_frac
    fee = partial_fee(remaining_notional)  # exit leg only (entry was accounted at open conceptually)
    # We account entry fee too for the remaining fraction
    entry_fee = partial_fee(remaining_notional)

    if pos.direction == "long":
        raw_pnl_pct = (exit_px - pos.entry_price) / pos.entry_price
    else:
        raw_pnl_pct = (pos.entry_price - exit_px) / pos.entry_price

    remainder_pnl_usd = remaining_notional * raw_pnl_pct - fee - entry_fee

    # Accumulate partial pnl if any
    partial_pnl_usd = getattr(pos, "_partial_pnl_usd", 0.0)
    partial_pnl_pct = getattr(pos, "_partial_pnl_pct", 0.0)

    # Entry fee for the partial portion (entry leg)
    partial_notional = pos.size_usd * PARTIAL_CLOSE if pos.partial_hit else 0.0
    partial_entry_fee = partial_fee(partial_notional) if pos.partial_hit else 0.0
    partial_pnl_usd -= partial_entry_fee

    total_pnl_usd = partial_pnl_usd + remainder_pnl_usd
    total_pnl_pct = total_pnl_usd / pos.size_usd * 100

    return ClosedTrade(
        pair=pos.pair,
        direction=pos.direction,
        entry_price=pos.entry_price,
        exit_price=exit_px,
        entry_time=pos.entry_time,
        exit_time=exit_time,
        pnl_pct=total_pnl_pct,
        pnl_usd=total_pnl_usd,
        exit_reason=reason,
    )


def force_close_position(pos: Position, close_px: float, close_time: pd.Timestamp) -> ClosedTrade:
    """Close a position at end-of-data."""
    exit_px = apply_slippage(close_px, pos.direction, entering=False)
    return _close_trade(pos, exit_px, close_time, "end_of_data")


# ---------------------------------------------------------------------------
# Core backtest loop
# ---------------------------------------------------------------------------

def run_backtest_pair(
    pair: str,
    df_raw: pd.DataFrame,
    strategy_name: str,
) -> list[ClosedTrade]:
    """
    Run the backtest for a single pair on pre-fetched OHLCV data.
    Returns a list of ClosedTrade objects.
    """
    strategy_fn = STRATEGIES[strategy_name]

    # Apply all indicators to the full dataset first
    df = add_all_indicators(df_raw)

    if df.empty or len(df) < 50:
        print(f"  [{pair}] Not enough data after indicator warmup ({len(df)} rows). Skipping.")
        return []

    trades: list[ClosedTrade] = []
    open_pos: Optional[Position] = None

    # We need at least 200 candles of warmup for indicators to stabilize,
    # but add_all_indicators already drops NaN rows, so df is clean.
    # We still give a minimum lookback window before issuing signals.
    WARMUP = 200

    total = len(df)
    indices = df.index

    for i in range(WARMUP, total):
        candle_time = indices[i]
        candle      = df.iloc[i]

        # --- Manage open position first (check current candle for exits) ---
        if open_pos is not None:
            closed = update_position(open_pos, candle, candle_time)
            if closed is not None:
                trades.append(closed)
                open_pos = None

        # --- Check for new signal only if flat ---
        if open_pos is None:
            # Slice up to and including current candle (no lookahead)
            window = df.iloc[: i + 1]

            try:
                signal_result = strategy_fn(window)
            except Exception:
                continue

            if signal_result.signal in (Signal.BUY, Signal.SELL):
                entry_price = candle["close"]
                open_pos = open_position(pair, signal_result.signal, entry_price, candle_time)

    # Force-close any open position at end of data
    if open_pos is not None:
        last_candle = df.iloc[-1]
        closed = force_close_position(open_pos, last_candle["close"], indices[-1])
        trades.append(closed)

    return trades


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@dataclass
class PairStats:
    pair:        str
    total_trades: int
    wins:         int
    losses:       int
    win_rate:     float
    total_pnl_usd: float
    avg_win_usd:   float
    avg_loss_usd:  float
    profit_factor: float
    max_drawdown:  float  # as % of running equity
    sharpe:        float


def compute_stats(trades: list[ClosedTrade], pair: str) -> Optional[PairStats]:
    if not trades:
        return None

    total = len(trades)
    wins  = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]

    win_rate  = len(wins) / total * 100
    total_pnl = sum(t.pnl_usd for t in trades)
    avg_win   = sum(t.pnl_usd for t in wins) / len(wins) if wins else 0.0
    avg_loss  = sum(t.pnl_usd for t in losses) / len(losses) if losses else 0.0

    gross_wins   = sum(t.pnl_usd for t in wins)
    gross_losses = abs(sum(t.pnl_usd for t in losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Max drawdown on cumulative equity curve
    equity = 0.0
    peak   = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_usd
        if equity > peak:
            peak = equity
        dd = (peak - equity) / abs(peak) * 100 if peak != 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Sharpe: group pnl by day, compute mean/std of daily returns
    if len(trades) >= 2:
        trade_df = pd.DataFrame([
            {"date": t.exit_time.date(), "pnl": t.pnl_usd}
            for t in trades
        ])
        daily = trade_df.groupby("date")["pnl"].sum()
        base  = TRADE_SIZE_USD  # reference for % return
        daily_ret = daily / base
        mean_ret = daily_ret.mean()
        std_ret  = daily_ret.std()
        sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    return PairStats(
        pair=pair,
        total_trades=total,
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        total_pnl_usd=total_pnl,
        avg_win_usd=avg_win,
        avg_loss_usd=avg_loss,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        sharpe=sharpe,
    )


def compute_global_sharpe(all_trades: list[ClosedTrade]) -> float:
    if len(all_trades) < 2:
        return 0.0
    trade_df = pd.DataFrame([
        {"date": t.exit_time.date(), "pnl": t.pnl_usd}
        for t in all_trades
    ])
    daily    = trade_df.groupby("date")["pnl"].sum()
    base     = TRADE_SIZE_USD * max(1, len(set(t.pair for t in all_trades)))
    daily_ret = daily / base
    mean_ret  = daily_ret.mean()
    std_ret   = daily_ret.std()
    return (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 72

def format_report(
    all_trades:     list[ClosedTrade],
    pair_stats:     list[PairStats],
    strategy_name:  str,
    timeframe:      str,
    days:           int,
    pairs:          list[str],
) -> str:
    lines = []

    lines.append(SEPARATOR)
    lines.append("  PHMEX-S BACKTEST RESULTS")
    lines.append(SEPARATOR)
    lines.append(f"  Strategy   : {strategy_name}")
    lines.append(f"  Pairs      : {', '.join(pairs)}")
    lines.append(f"  Timeframe  : {timeframe}")
    lines.append(f"  Period     : last {days} days")
    lines.append(f"  Run at     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"  Position   : ${TRADE_SIZE_USD:,.0f} notional per trade")
    lines.append(f"  SL / TP    : {SL_PCT}% / {TP_PCT}% (50% partial at TP, trailing on rest)")
    lines.append(f"  Fees       : {TAKER_FEE_PCT}% taker per side + {SLIPPAGE_PCT}% slippage")
    lines.append("")

    # --- Per-pair breakdown ---
    lines.append(SEPARATOR)
    lines.append("  PER-PAIR BREAKDOWN")
    lines.append(SEPARATOR)

    for ps in pair_stats:
        lines.append(f"\n  {ps.pair}")
        lines.append(f"    Trades     : {ps.total_trades}  (W:{ps.wins} / L:{ps.losses})")
        lines.append(f"    Win Rate   : {ps.win_rate:.1f}%")
        lines.append(f"    Total PnL  : ${ps.total_pnl_usd:+.2f}")
        lines.append(f"    Avg Win    : ${ps.avg_win_usd:+.2f}   Avg Loss: ${ps.avg_loss_usd:+.2f}")
        lines.append(f"    Prof Factor: {ps.profit_factor:.2f}" if ps.profit_factor != float("inf")
                     else f"    Prof Factor: ∞ (no losses)")
        lines.append(f"    Max DD     : {ps.max_drawdown:.2f}%")
        lines.append(f"    Sharpe     : {ps.sharpe:.3f}")

    # --- Aggregate ---
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("  AGGREGATE SUMMARY")
    lines.append(SEPARATOR)

    total_trades = sum(ps.total_trades for ps in pair_stats)
    total_wins   = sum(ps.wins for ps in pair_stats)
    total_losses = sum(ps.losses for ps in pair_stats)
    total_pnl    = sum(ps.total_pnl_usd for ps in pair_stats)
    overall_wr   = total_wins / total_trades * 100 if total_trades else 0

    gross_wins_all   = sum(t.pnl_usd for t in all_trades if t.pnl_usd > 0)
    gross_losses_all = abs(sum(t.pnl_usd for t in all_trades if t.pnl_usd <= 0))
    overall_pf = gross_wins_all / gross_losses_all if gross_losses_all > 0 else float("inf")

    # Global max drawdown
    equity = 0.0
    peak   = 0.0
    global_max_dd = 0.0
    for t in sorted(all_trades, key=lambda x: x.exit_time):
        equity += t.pnl_usd
        if equity > peak:
            peak = equity
        dd = (peak - equity) / abs(peak) * 100 if peak != 0 else 0.0
        if dd > global_max_dd:
            global_max_dd = dd

    global_sharpe = compute_global_sharpe(all_trades)

    lines.append(f"  Total Trades : {total_trades}  (W:{total_wins} / L:{total_losses})")
    lines.append(f"  Win Rate     : {overall_wr:.1f}%")
    lines.append(f"  Total PnL    : ${total_pnl:+.2f}")
    lines.append(f"  Profit Factor: {overall_pf:.2f}" if overall_pf != float("inf")
                 else "  Profit Factor: ∞ (no losses)")
    lines.append(f"  Max Drawdown : {global_max_dd:.2f}%")
    lines.append(f"  Sharpe Ratio : {global_sharpe:.3f}  (annualised, daily grouping)")

    if pair_stats:
        best  = max(pair_stats, key=lambda p: p.total_pnl_usd)
        worst = min(pair_stats, key=lambda p: p.total_pnl_usd)
        lines.append(f"  Best Pair    : {best.pair}  (${best.total_pnl_usd:+.2f})")
        lines.append(f"  Worst Pair   : {worst.pair}  (${worst.total_pnl_usd:+.2f})")

    # --- Exit reason distribution ---
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("  EXIT REASON DISTRIBUTION")
    lines.append(SEPARATOR)
    reasons: dict[str, int] = {}
    for t in all_trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    for r, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
        pct = cnt / total_trades * 100 if total_trades else 0
        lines.append(f"  {r:<20} {cnt:>5}  ({pct:.1f}%)")

    # --- Trade log (last 30 trades) ---
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("  RECENT TRADES (last 30)")
    lines.append(SEPARATOR)
    lines.append(f"  {'Pair':<22} {'Dir':<6} {'Entry':>10} {'Exit':>10} "
                 f"{'PnL%':>7} {'PnL$':>9} {'Reason':<16} {'Exit Time'}")
    lines.append("  " + "-" * 98)
    recent = sorted(all_trades, key=lambda x: x.exit_time)[-30:]
    for t in recent:
        lines.append(
            f"  {t.pair:<22} {t.direction:<6} {t.entry_price:>10.4f} {t.exit_price:>10.4f}"
            f" {t.pnl_pct:>+7.2f}% {t.pnl_usd:>+9.2f} {t.exit_reason:<16}"
            f" {t.exit_time.strftime('%Y-%m-%d %H:%M')}"
        )

    lines.append("")
    lines.append(SEPARATOR)
    lines.append("  END OF REPORT")
    lines.append(SEPARATOR)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phmex-S backtesting engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=DEFAULT_PAIRS,
        metavar="PAIR",
        help="Trading pairs in Phemex futures format (e.g. ETH/USDT:USDT)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Number of historical days to fetch",
    )
    parser.add_argument(
        "--timeframe",
        default=DEFAULT_TIMEFRAME,
        help="OHLCV timeframe (e.g. 1m, 5m, 15m, 1h)",
    )
    parser.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY,
        choices=list(STRATEGIES.keys()),
        help="Strategy to backtest",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print()
    print(SEPARATOR)
    print("  PHMEX-S BACKTEST ENGINE")
    print(SEPARATOR)
    print(f"  Strategy  : {args.strategy}")
    print(f"  Pairs     : {', '.join(args.pairs)}")
    print(f"  Timeframe : {args.timeframe}")
    print(f"  Period    : {args.days} days")
    print()

    # --- Init exchange (public endpoints only) ---
    exchange = ccxt.phemex({
        "enableRateLimit": True,
    })
    # Load markets so symbol lookups work
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"[WARN] Could not load markets: {e}")

    all_trades:  list[ClosedTrade] = []
    pair_stats:  list[PairStats]   = []

    # --- Process each pair ---
    for pair in args.pairs:
        print(f"\n[{pair}] Fetching data...")
        df_raw = fetch_ohlcv_full(exchange, pair, args.timeframe, args.days)

        if df_raw.empty:
            print(f"  [{pair}] No data returned. Skipping.")
            continue

        print(f"[{pair}] Running strategy '{args.strategy}'...")
        trades = run_backtest_pair(pair, df_raw, args.strategy)
        print(f"[{pair}] {len(trades)} trades closed.")

        stats = compute_stats(trades, pair)
        if stats is not None:
            pair_stats.append(stats)

        all_trades.extend(trades)

        time.sleep(0.5)  # brief pause between pairs

    # --- Generate report ---
    print()
    if not all_trades:
        print("No trades were generated across all pairs. Try a longer period or different strategy.")
        return

    report = format_report(
        all_trades=all_trades,
        pair_stats=pair_stats,
        strategy_name=args.strategy,
        timeframe=args.timeframe,
        days=args.days,
        pairs=args.pairs,
    )

    # Print to console
    print(report)

    # Save to file
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
            fh.write(report)
            fh.write("\n")
        print(f"\n  Results saved to: {OUTPUT_FILE}")
    except OSError as e:
        print(f"\n  [WARN] Could not write results file: {e}")


if __name__ == "__main__":
    main()
