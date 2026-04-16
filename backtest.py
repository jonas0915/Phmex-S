"""
backtest.py — Production backtester for Phmex-S scalping bot.

Replicates the live entry pipeline (bot.py), exit logic (risk_manager.py),
and adaptive strategy selection (strategies.py) on historical OHLCV data.

Usage:
    python backtest.py                          # adaptive, 14 pairs, 7 days
    python backtest.py --days 30                # 30 days
    python backtest.py --pairs ETH/USDT:USDT   # single pair
    python backtest.py --no-gates               # raw signals, no entry gates
"""

import argparse
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import ccxt
import numpy as np
import pandas as pd

from indicators import add_all_indicators
from strategies import Signal, TradeSignal, adaptive_strategy

# ---------------------------------------------------------------------------
# Constants (match .env)
# ---------------------------------------------------------------------------

TAKER_FEE_PCT = 0.06       # 0.06% per side
SLIPPAGE_PCT = 0.05         # 0.05% simulated slippage
LEVERAGE = 10
TRADE_SIZE_USD = 10.0       # margin per trade (matches .env TRADE_AMOUNT_USDT)
STARTING_BALANCE = 74.38    # approximate current balance (updated 2026-04-15)
SCALP_MIN_STRENGTH = 0.75   # matches live bot min_strength (raised Mar 20)
MAX_OPEN_TRADES = 3

DEFAULT_PAIRS = [
    # SOL, NEAR, FET, OP, TIA, TRUMP, BNB blacklisted — excluded from backtest
    "BTC/USDT:USDT", "ETH/USDT:USDT", "DOGE/USDT:USDT",
    "XRP/USDT:USDT", "WIF/USDT:USDT", "SUI/USDT:USDT",
    "RENDER/USDT:USDT", "ARB/USDT:USDT",
    "INJ/USDT:USDT", "LINK/USDT:USDT",
]
DEFAULT_DAYS = 7
DEFAULT_TIMEFRAME = "1m"

WARMUP = 250        # 200 for EMA-200 + 50 for ATR avg
FETCH_LIMIT = 1000  # ccxt pagination limit for Phemex

OUTPUT_FILE = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_results.txt"

# Regime-adaptive SL/TP multipliers (match risk_manager.py open_position)
REGIME_MULTS = {
    "low":     {"sl": 1.2, "tp_ratio": 2.0},
    "medium":  {"sl": 1.5, "tp_ratio": 2.0},
    "high":    {"sl": 2.0, "tp_ratio": 2.0},
    "extreme": {"sl": 2.5, "tp_ratio": 2.0},
}

# SL floor/cap: 1.2% of entry price, cap at 3x floor
SL_FLOOR_PCT = 1.2  # percent
TP_CAP_PCT = 1.6    # max TP distance (matches .env TAKE_PROFIT_PERCENT)

# Strategy time exits — values in CYCLES (15s each) from live bot.
# Convert to 1m candles: candles = cycles / 4
STRATEGY_TIME_EXITS_CYCLES = {
    "keltner_squeeze":   {"soft": 80,  "hard": 180},
    "trend_pullback":    {"soft": 60,  "hard": 150},
    "trend_scalp":       {"soft": 80,  "hard": 180},
    "bb_mean_reversion": {"soft": 80,  "hard": 180},
}
DEFAULT_TIME_EXIT_CYCLES = {"soft": 80, "hard": 180}

# Flat exit: 80 cycles = 20 candles
FLAT_EXIT_CANDLES = 10  # 40 cycles / 4 = 10 min

# Global cooldown between trades: 2 candles (30s / 15s = 2 cycles → ~0.5 candles, round to 2)
GLOBAL_COOLDOWN_CANDLES = 2

# Per-pair cooldown after 3 consecutive losses: 40 candles
PAIR_COOLDOWN_CANDLES = 40

# Regime filter: 60 candles pause after 4 of last 6 trades were losses
REGIME_PAUSE_CANDLES = 60  # ~15 min equivalent


def _cycles_to_candles(cycles: int) -> int:
    """Convert 15-second cycle counts to 1-minute candle counts."""
    return max(1, cycles // 4)


def _get_time_exits(strategy: str) -> dict:
    """Get soft/hard time exit thresholds in candles for a strategy."""
    raw = STRATEGY_TIME_EXITS_CYCLES.get(strategy, DEFAULT_TIME_EXIT_CYCLES)
    return {
        "soft": _cycles_to_candles(raw["soft"]),
        "hard": _cycles_to_candles(raw["hard"]),
    }


# ---------------------------------------------------------------------------
# Strategy name extraction (match bot.py)
# ---------------------------------------------------------------------------

def _extract_strategy_name(reason: str) -> str:
    r = reason.lower()
    if "kc squeeze" in r or "keltner" in r:
        return "keltner_squeeze"
    if "bb" in r or "mean reversion" in r:
        return "bb_mean_reversion"
    if "trend pullback" in r:
        return "trend_pullback"
    if "trend scalp" in r or "trend_scalp" in r:
        return "trend_scalp"
    return "unknown"


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------

@dataclass
class BTPosition:
    pair: str
    direction: str              # "long" or "short"
    entry_price: float
    entry_candle: int           # index into df
    size_usd: float             # notional = margin * leverage
    margin: float               # USDT margin
    sl_price: float
    tp_price: float
    strategy: str
    peak_price: float = 0.0
    breakeven_moved: bool = False
    trailing_stop_price: Optional[float] = None

    def roi(self, current_price: float) -> float:
        """ROI as % of margin (leveraged)."""
        if self.direction == "long":
            price_pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        else:
            price_pnl_pct = (self.entry_price - current_price) / self.entry_price * 100
        return price_pnl_pct * LEVERAGE

    def pnl_usd(self, exit_price: float) -> float:
        """Gross PnL in USD (before fees)."""
        if self.direction == "long":
            return (exit_price - self.entry_price) / self.entry_price * self.size_usd
        else:
            return (self.entry_price - exit_price) / self.entry_price * self.size_usd

    def r_distance(self) -> float:
        """1R = distance from entry to original SL."""
        return abs(self.entry_price - self.sl_price)


@dataclass
class ClosedTrade:
    pair: str
    direction: str
    entry_price: float
    exit_price: float
    entry_candle: int
    exit_candle: int
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    pnl_usd: float             # net PnL after fees
    roi_pct: float              # ROI as % of margin
    exit_reason: str
    strategy: str
    margin: float


# ---------------------------------------------------------------------------
# Fee & slippage helpers
# ---------------------------------------------------------------------------

def apply_slippage(price: float, direction: str, entering: bool) -> float:
    """Worsen fill price by slippage."""
    factor = SLIPPAGE_PCT / 100.0
    if direction == "long":
        return price * (1 + factor) if entering else price * (1 - factor)
    else:
        return price * (1 - factor) if entering else price * (1 + factor)


def round_trip_fees(notional: float) -> float:
    """Total taker fees for entry + exit."""
    return notional * 2 * TAKER_FEE_PCT / 100.0


# ---------------------------------------------------------------------------
# Data fetching (kept from original)
# ---------------------------------------------------------------------------

def fetch_ohlcv_full(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    days: int,
) -> pd.DataFrame:
    """
    Fetch up to `days` worth of OHLCV data for `symbol` from Phemex.
    Paginates automatically if needed.
    """
    tf_ms = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
        "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }
    if timeframe not in tf_ms:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    candle_ms = tf_ms[timeframe]
    total_ms = days * 24 * 3600 * 1000
    total_needed = total_ms // candle_ms
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    since_ms = now_ms - total_ms

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
        time.sleep(0.3)

    if not all_ohlcv:
        return pd.DataFrame()

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    df = df[df.index >= cutoff]

    print(f"  Got {len(df)} candles for {symbol}.")
    return df


# ---------------------------------------------------------------------------
# SL/TP calculation (match risk_manager.py open_position)
# ---------------------------------------------------------------------------

def calculate_sl_tp(
    entry_price: float,
    direction: str,
    atr_val: float,
    regime: str,
) -> tuple[float, float]:
    """Calculate SL and TP prices matching the live bot's regime-adaptive logic."""
    mults = REGIME_MULTS.get(regime, REGIME_MULTS["medium"])

    sl_dist = mults["sl"] * atr_val
    # Floor = 1.2% of entry, Cap = 3x floor
    min_sl_dist = entry_price * (SL_FLOOR_PCT / 100)
    max_sl_dist = min_sl_dist * 3
    sl_dist = max(min_sl_dist, min(sl_dist, max_sl_dist))
    tp_dist = sl_dist * mults["tp_ratio"]
    # Cap TP at configured max so it's reachable on 1m scalp
    max_tp_dist = entry_price * (TP_CAP_PCT / 100)
    tp_dist = min(tp_dist, max_tp_dist)

    if direction == "long":
        sl_price = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        sl_price = entry_price + sl_dist
        tp_price = entry_price - tp_dist

    return sl_price, tp_price


# ---------------------------------------------------------------------------
# Exit pipeline
# ---------------------------------------------------------------------------

def check_exits(
    pos: BTPosition,
    candle: pd.Series,
    candle_idx: int,
    df_window: pd.DataFrame,
) -> Optional[tuple[float, str]]:
    """
    Check all exit conditions for an open position.
    Returns (exit_price, reason) or None.
    Checks in priority order matching the live bot.
    """
    high = candle["high"]
    low = candle["low"]
    close = candle["close"]
    candles_held = candle_idx - pos.entry_candle

    # ---------------------------------------------------------------
    # 1. Stop Loss
    # ---------------------------------------------------------------
    if pos.direction == "long" and low <= pos.sl_price:
        exit_px = apply_slippage(pos.sl_price, "long", entering=False)
        # If trailing stop was active and triggered, label it
        if pos.trailing_stop_price and low <= pos.trailing_stop_price:
            return exit_px, "trailing_stop"
        return exit_px, "stop_loss"

    if pos.direction == "short" and high >= pos.sl_price:
        exit_px = apply_slippage(pos.sl_price, "short", entering=False)
        if pos.trailing_stop_price and high >= pos.trailing_stop_price:
            return exit_px, "trailing_stop"
        return exit_px, "stop_loss"

    # ---------------------------------------------------------------
    # 2. Take Profit
    # ---------------------------------------------------------------
    if pos.direction == "long" and high >= pos.tp_price:
        exit_px = apply_slippage(pos.tp_price, "long", entering=False)
        return exit_px, "take_profit"

    if pos.direction == "short" and low <= pos.tp_price:
        exit_px = apply_slippage(pos.tp_price, "short", entering=False)
        return exit_px, "take_profit"

    # ---------------------------------------------------------------
    # 3. Early exit: ROI >= 10% AND 2+ reversal signals
    # ---------------------------------------------------------------
    roi = pos.roi(close)
    if roi >= 10.0 and len(df_window) >= 3:
        signals_count = 0
        last = df_window.iloc[-1]
        prev = df_window.iloc[-2]

        if pos.direction == "long":
            if last.get("rsi", 50) < 45:
                signals_count += 1
            if "macd" in last and "macd_signal" in last:
                if last["macd"] < last["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
                    signals_count += 1
            if "ema_9" in last:
                if last["close"] < last["ema_9"] and prev["close"] < prev["ema_9"]:
                    signals_count += 1
        else:
            if last.get("rsi", 50) > 55:
                signals_count += 1
            if "macd" in last and "macd_signal" in last:
                if last["macd"] > last["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
                    signals_count += 1
            if "ema_9" in last:
                if last["close"] > last["ema_9"] and prev["close"] > prev["ema_9"]:
                    signals_count += 1

        if signals_count >= 2:
            exit_px = apply_slippage(close, pos.direction, entering=False)
            return exit_px, "early_exit"

    # ---------------------------------------------------------------
    # 4. Flat exit: only when ROI covers fees (2.5-4% ROI)
    # ---------------------------------------------------------------
    if 2.5 <= roi < 4.0 and candles_held >= FLAT_EXIT_CANDLES:
        exit_px = apply_slippage(close, pos.direction, entering=False)
        return exit_px, "flat_exit"

    # ---------------------------------------------------------------
    # 5. Time exit: remove 2x extension, keep original soft limits
    # ---------------------------------------------------------------
    time_exits = _get_time_exits(pos.strategy)

    # Hard exit (extend 50% if ROI >= 5%)
    hard_limit = time_exits["hard"]
    if candles_held >= hard_limit:
        if roi >= 5.0:
            extended = int(hard_limit * 1.5)
            if candles_held >= extended:
                exit_px = apply_slippage(close, pos.direction, entering=False)
                return exit_px, "hard_time_exit"
        else:
            exit_px = apply_slippage(close, pos.direction, entering=False)
            return exit_px, "hard_time_exit"

    # Early cut: deeply losing after half soft
    soft_limit = time_exits["soft"]
    if candles_held >= soft_limit // 2 and roi < -6.0:
        exit_px = apply_slippage(close, pos.direction, entering=False)
        return exit_px, "time_exit"

    # Soft exit: anything below 3% ROI at soft limit (no 2x extension)
    if candles_held >= soft_limit and roi < 3.0:
        exit_px = apply_slippage(close, pos.direction, entering=False)
        return exit_px, "time_exit"

    # ---------------------------------------------------------------
    # 7-9. Breakeven / Profit lock / Trailing (mutate position, no exit)
    # ---------------------------------------------------------------
    r_dist = pos.r_distance()

    # Trailing stop: at 1R profit, trail at 0.7R from peak
    if r_dist > 0:
        if pos.direction == "long":
            if close >= pos.entry_price + r_dist:
                # Update peak
                if close > pos.peak_price:
                    pos.peak_price = close
                trail_dist = r_dist * 0.7
                new_trail = pos.peak_price - trail_dist
                if pos.trailing_stop_price is None or new_trail > pos.trailing_stop_price:
                    pos.trailing_stop_price = new_trail
                # Ratchet SL up to trailing stop
                if pos.trailing_stop_price > pos.sl_price:
                    pos.sl_price = pos.trailing_stop_price
        else:  # short
            if close <= pos.entry_price - r_dist:
                if close < pos.peak_price or pos.peak_price == pos.entry_price:
                    pos.peak_price = close
                trail_dist = r_dist * 0.7
                new_trail = pos.peak_price + trail_dist
                if pos.trailing_stop_price is None or new_trail < pos.trailing_stop_price:
                    pos.trailing_stop_price = new_trail
                if pos.trailing_stop_price < pos.sl_price:
                    pos.sl_price = pos.trailing_stop_price

    # Breakeven: at 1R profit -> move SL to entry + 0.15% (profit-lock removed in v4.0)
    if not pos.breakeven_moved and r_dist > 0:
        if pos.direction == "long":
            if close >= pos.entry_price + r_dist:
                new_sl = pos.entry_price + (pos.entry_price * 0.0025)
                if new_sl > pos.sl_price:
                    pos.sl_price = new_sl
                    pos.breakeven_moved = True
        else:
            if close <= pos.entry_price - r_dist:
                new_sl = pos.entry_price - (pos.entry_price * 0.0025)
                if new_sl < pos.sl_price:
                    pos.sl_price = new_sl
                    pos.breakeven_moved = True

    return None


# ---------------------------------------------------------------------------
# Core backtest engine
# ---------------------------------------------------------------------------

def run_backtest(
    pair_data: dict[str, pd.DataFrame],
    no_gates: bool = False,
) -> list[ClosedTrade]:
    """
    Run the full backtest across all pairs simultaneously.
    Processes candles sequentially, checking all pairs each candle.
    """
    # Compute indicators on full datasets upfront
    pair_dfs: dict[str, pd.DataFrame] = {}
    for pair, df_raw in pair_data.items():
        df = add_all_indicators(df_raw)
        if df.empty or len(df) < WARMUP:
            print(f"  [{pair}] Not enough data after indicator warmup ({len(df)} rows). Skipping.")
            continue
        pair_dfs[pair] = df

    if not pair_dfs:
        return []

    # Find common time range across all pairs
    all_starts = [df.index[WARMUP] for df in pair_dfs.values()]
    all_ends = [df.index[-1] for df in pair_dfs.values()]
    global_start = max(all_starts)
    global_end = min(all_ends)

    # State
    balance = STARTING_BALANCE
    peak_balance = STARTING_BALANCE
    open_positions: dict[str, BTPosition] = {}  # pair -> position
    closed_trades: list[ClosedTrade] = []
    last_entry_candle = -GLOBAL_COOLDOWN_CANDLES  # global cooldown
    pair_loss_streak: dict[str, int] = {}
    pair_cooldown_until: dict[str, int] = {}  # pair -> candle index when cooldown expires
    trade_results: deque = deque(maxlen=6)
    regime_pause_until = 0  # candle index when regime pause expires
    drawdown_pause_until = 0  # candle index when drawdown pause expires
    virtual_candle = 0  # global candle counter

    # For each pair, find start/end indices within its own df
    pair_ranges: dict[str, tuple[int, int]] = {}
    for pair, df in pair_dfs.items():
        # Find indices corresponding to global_start..global_end
        start_idx = df.index.searchsorted(global_start)
        end_idx = df.index.searchsorted(global_end, side="right")
        if start_idx >= end_idx:
            continue
        pair_ranges[pair] = (start_idx, end_idx)

    if not pair_ranges:
        return []

    # Use one pair's index as the time reference
    ref_pair = list(pair_ranges.keys())[0]
    ref_df = pair_dfs[ref_pair]
    ref_start, ref_end = pair_ranges[ref_pair]
    total_candles = ref_end - ref_start

    print(f"\n  Simulating {total_candles} candles across {len(pair_ranges)} pairs...")
    print(f"  Period: {ref_df.index[ref_start]} to {ref_df.index[ref_end - 1]}")
    print(f"  Starting balance: ${balance:.2f}\n")

    progress_interval = max(1, total_candles // 20)

    for step in range(total_candles):
        virtual_candle += 1
        ref_idx = ref_start + step
        candle_time = ref_df.index[ref_idx]

        if step % progress_interval == 0 and step > 0:
            pct = step / total_candles * 100
            open_count = len(open_positions)
            print(f"  [{pct:5.1f}%] candle {step}/{total_candles} | "
                  f"balance=${balance:.2f} | open={open_count} | trades={len(closed_trades)}")

        # ===================================================================
        # PHASE 1: Check exits on all open positions
        # ===================================================================
        pairs_to_close = []
        for pair, pos in list(open_positions.items()):
            if pair not in pair_dfs:
                continue
            df = pair_dfs[pair]
            p_start, p_end = pair_ranges.get(pair, (0, 0))
            # Map global step to this pair's candle index
            # Find the candle at or just before candle_time
            idx = df.index.searchsorted(candle_time, side="right") - 1
            if idx < 0 or idx >= len(df):
                continue

            candle = df.iloc[idx]
            # Window for early exit check (last few candles)
            win_start = max(0, idx - 5)
            df_window = df.iloc[win_start:idx + 1]

            result = check_exits(pos, candle, idx, df_window)
            if result is not None:
                exit_price, reason = result
                gross_pnl = pos.pnl_usd(exit_price)
                fees = round_trip_fees(pos.size_usd)
                net_pnl = gross_pnl - fees
                roi_pct = net_pnl / pos.margin * 100

                trade = ClosedTrade(
                    pair=pair,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    entry_candle=pos.entry_candle,
                    exit_candle=idx,
                    entry_time=df.index[pos.entry_candle],
                    exit_time=candle_time,
                    pnl_usd=net_pnl,
                    roi_pct=roi_pct,
                    exit_reason=reason,
                    strategy=pos.strategy,
                    margin=pos.margin,
                )
                closed_trades.append(trade)
                balance += net_pnl
                if balance > peak_balance:
                    peak_balance = balance
                pairs_to_close.append(pair)

                # Track cooldowns
                is_loss = net_pnl < 0
                if is_loss:
                    pair_loss_streak[pair] = pair_loss_streak.get(pair, 0) + 1
                    streak = pair_loss_streak[pair]
                    if streak >= 3:
                        pair_cooldown_until[pair] = virtual_candle + PAIR_COOLDOWN_CANDLES
                        pair_loss_streak[pair] = 0
                    trade_results.append(False)
                    # Regime filter check
                    if len(trade_results) >= 6:
                        losses = sum(1 for r in trade_results if not r)
                        if losses >= 4:
                            regime_pause_until = virtual_candle + REGIME_PAUSE_CANDLES
                            trade_results.clear()
                else:
                    pair_loss_streak[pair] = 0
                    trade_results.append(True)

        for pair in pairs_to_close:
            del open_positions[pair]

        # ===================================================================
        # PHASE 2: Check entries
        # ===================================================================
        # Drawdown halt with cooldown (matches live bot: pause then reset peak)
        if not no_gates:
            if virtual_candle < drawdown_pause_until:
                continue  # still in drawdown cooldown
            if drawdown_pause_until > 0 and virtual_candle >= drawdown_pause_until:
                # Cooldown expired — reset peak to current balance (fresh start)
                peak_balance = balance
                drawdown_pause_until = 0
            drawdown_pct = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0
            if drawdown_pct >= 30.0:
                drawdown_pause_until = virtual_candle + 90  # 1.5 hours
                continue
            elif drawdown_pct >= 25.0:
                drawdown_pause_until = virtual_candle + 60  # 1 hour
                continue
            elif drawdown_pct >= 20.0:
                drawdown_pause_until = virtual_candle + 30  # 30 min
                continue

            # Regime pause
            if virtual_candle < regime_pause_until:
                continue

        for pair in pair_ranges:
            # Skip if already in position on this pair
            if pair in open_positions:
                continue
            # Max open trades limit (v4.0)
            if len(open_positions) >= MAX_OPEN_TRADES:
                break

            df = pair_dfs[pair]
            # Find this pair's candle at current time
            idx = df.index.searchsorted(candle_time, side="right") - 1
            if idx < WARMUP or idx >= len(df):
                continue

            candle = df.iloc[idx]

            # --- v4.0 Simplified entry pipeline ---

            # Get ATR
            atr_val = float(candle.get("atr", 0))
            if atr_val != atr_val:  # NaN check
                atr_val = 0.0
            if atr_val <= 0:
                continue

            # Determine volatility regime (no extreme skip in v4.0)
            atr_pct_val = float(candle.get("atr_pct", 50))
            if atr_pct_val != atr_pct_val:
                atr_pct_val = 50
            if atr_pct_val > 80:
                regime = "high"
            elif atr_pct_val > 25:
                regime = "medium"
            else:
                regime = "low"

            # Call adaptive_strategy (single pass — no OB re-run)
            win_start = max(0, idx - 200)
            df_window = df.iloc[win_start:idx + 1]

            try:
                signal = adaptive_strategy(df_window, None)
            except Exception:
                continue

            if signal.signal == Signal.HOLD:
                continue

            # Min strength check (v4.0: 0.70)
            if signal.strength < SCALP_MIN_STRENGTH:
                continue

            # --- Cooldowns (skip in no-gates mode) ---
            if not no_gates:
                # Global cooldown: 2 candles between any trades (continue, not break)
                if virtual_candle - last_entry_candle < GLOBAL_COOLDOWN_CANDLES:
                    continue

                # Per-pair cooldown
                if pair in pair_cooldown_until and virtual_candle < pair_cooldown_until[pair]:
                    continue

            # --- Open position ---
            entry_price = float(candle["close"])
            direction = "long" if signal.signal == Signal.BUY else "short"
            fill_price = apply_slippage(entry_price, direction, entering=True)

            strategy_name = _extract_strategy_name(signal.reason)
            sl_price, tp_price = calculate_sl_tp(fill_price, direction, atr_val, regime)

            margin = TRADE_SIZE_USD
            # Half-size in choppy markets
            if not no_gates:
                adx_val = float(candle.get("adx", 25))
                chop_val = float(candle.get("chop", 50))
                if adx_val < 25 and chop_val >= 55:
                    margin *= 0.5

            # Check we have enough balance
            if margin > balance:
                continue

            notional = margin * LEVERAGE
            pos = BTPosition(
                pair=pair,
                direction=direction,
                entry_price=fill_price,
                entry_candle=idx,
                size_usd=notional,
                margin=margin,
                sl_price=sl_price,
                tp_price=tp_price,
                strategy=strategy_name,
                peak_price=fill_price,
            )
            open_positions[pair] = pos
            last_entry_candle = virtual_candle

    # ===================================================================
    # Force-close remaining positions at end of data
    # ===================================================================
    for pair, pos in open_positions.items():
        df = pair_dfs[pair]
        last_candle = df.iloc[-1]
        exit_price = apply_slippage(float(last_candle["close"]), pos.direction, entering=False)
        gross_pnl = pos.pnl_usd(exit_price)
        fees = round_trip_fees(pos.size_usd)
        net_pnl = gross_pnl - fees

        trade = ClosedTrade(
            pair=pair,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_candle=pos.entry_candle,
            exit_candle=len(df) - 1,
            entry_time=df.index[pos.entry_candle],
            exit_time=df.index[-1],
            pnl_usd=net_pnl,
            roi_pct=net_pnl / pos.margin * 100,
            exit_reason="end_of_data",
            strategy=pos.strategy,
            margin=pos.margin,
        )
        closed_trades.append(trade)
        balance += net_pnl

    return closed_trades


# ---------------------------------------------------------------------------
# Statistics & Report
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 78


def format_report(
    trades: list[ClosedTrade],
    timeframe: str,
    days: int,
    pairs: list[str],
    no_gates: bool,
) -> str:
    lines: list[str] = []

    if not trades:
        return "No trades generated."

    # Sort by exit time
    trades.sort(key=lambda t: t.exit_time)

    total = len(trades)
    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]
    total_pnl = sum(t.pnl_usd for t in trades)
    win_rate = len(wins) / total * 100 if total > 0 else 0
    avg_win = sum(t.pnl_usd for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl_usd for t in losses) / len(losses) if losses else 0

    gross_wins = sum(t.pnl_usd for t in wins)
    gross_losses = abs(sum(t.pnl_usd for t in losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Max drawdown on equity curve
    equity = STARTING_BALANCE
    peak_eq = equity
    max_dd_usd = 0.0
    max_dd_pct = 0.0
    equity_curve = [equity]
    for t in trades:
        equity += t.pnl_usd
        equity_curve.append(equity)
        if equity > peak_eq:
            peak_eq = equity
        dd = peak_eq - equity
        dd_pct = dd / peak_eq * 100 if peak_eq > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_usd = dd

    final_balance = equity

    # Sharpe ratio (daily, annualized)
    sharpe = 0.0
    if len(trades) >= 2:
        trade_df = pd.DataFrame([
            {"date": t.exit_time.date(), "pnl": t.pnl_usd}
            for t in trades
        ])
        daily = trade_df.groupby("date")["pnl"].sum()
        if len(daily) >= 2:
            daily_ret = daily / STARTING_BALANCE
            mean_ret = daily_ret.mean()
            std_ret = daily_ret.std()
            sharpe = (mean_ret / std_ret * math.sqrt(365)) if std_ret > 0 else 0.0

    # Max consecutive wins/losses
    max_consec_wins = 0
    max_consec_losses = 0
    cur_wins = 0
    cur_losses = 0
    for t in trades:
        if t.pnl_usd > 0:
            cur_wins += 1
            cur_losses = 0
            max_consec_wins = max(max_consec_wins, cur_wins)
        else:
            cur_losses += 1
            cur_wins = 0
            max_consec_losses = max(max_consec_losses, cur_losses)

    # Avg trade duration in candles
    avg_duration = sum(t.exit_candle - t.entry_candle for t in trades) / total if total > 0 else 0

    # ---------------------------------------------------------------
    # HEADER
    # ---------------------------------------------------------------
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("  PHMEX-S BACKTEST RESULTS")
    lines.append(SEPARATOR)
    lines.append(f"  Strategy   : adaptive{' (no gates)' if no_gates else ''}")
    lines.append(f"  Pairs      : {len(pairs)} pairs")
    lines.append(f"  Timeframe  : {timeframe}")
    lines.append(f"  Period     : last {days} days")
    lines.append(f"  Run at     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"  Margin     : ${TRADE_SIZE_USD:.0f}/trade | {LEVERAGE}x leverage | ${TRADE_SIZE_USD * LEVERAGE:.0f} notional")
    lines.append(f"  SL/TP      : Regime-adaptive ATR (floor {SL_FLOOR_PCT}%, R:R 1:2)")
    lines.append(f"  Fees       : {TAKER_FEE_PCT}% taker/side + {SLIPPAGE_PCT}% slippage")
    lines.append(f"  Start bal  : ${STARTING_BALANCE:.2f}")
    lines.append("")

    # ---------------------------------------------------------------
    # AGGREGATE SUMMARY
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  AGGREGATE SUMMARY")
    lines.append(SEPARATOR)
    lines.append(f"  Total Trades     : {total}  (W:{len(wins)} / L:{len(losses)})")
    lines.append(f"  Win Rate         : {win_rate:.1f}%")
    lines.append(f"  Total PnL        : ${total_pnl:+.2f}")
    lines.append(f"  Final Balance    : ${final_balance:.2f}")
    lines.append(f"  Avg Win          : ${avg_win:+.2f}")
    lines.append(f"  Avg Loss         : ${avg_loss:+.2f}")
    pf_str = f"{profit_factor:.2f}" if profit_factor != float("inf") else "inf (no losses)"
    lines.append(f"  Profit Factor    : {pf_str}")
    lines.append(f"  Max Drawdown     : {max_dd_pct:.1f}% (${max_dd_usd:.2f})")
    lines.append(f"  Sharpe Ratio     : {sharpe:.3f}  (annualized, daily)")
    lines.append(f"  Max Consec Wins  : {max_consec_wins}")
    lines.append(f"  Max Consec Losses: {max_consec_losses}")
    lines.append(f"  Avg Duration     : {avg_duration:.1f} candles ({avg_duration:.0f} min)")
    lines.append("")

    # ---------------------------------------------------------------
    # EXIT REASON BREAKDOWN
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  EXIT REASON BREAKDOWN")
    lines.append(SEPARATOR)
    reason_counts: dict[str, int] = {}
    reason_pnl: dict[str, float] = {}
    for t in trades:
        reason_counts[t.exit_reason] = reason_counts.get(t.exit_reason, 0) + 1
        reason_pnl[t.exit_reason] = reason_pnl.get(t.exit_reason, 0) + t.pnl_usd

    lines.append(f"  {'Reason':<20} {'Count':>6} {'%':>7} {'PnL':>10}")
    lines.append("  " + "-" * 45)
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        pnl = reason_pnl[reason]
        lines.append(f"  {reason:<20} {count:>6} {pct:>6.1f}% ${pnl:>+9.2f}")
    lines.append("")

    # ---------------------------------------------------------------
    # PER-STRATEGY BREAKDOWN
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  PER-STRATEGY BREAKDOWN")
    lines.append(SEPARATOR)
    strat_trades: dict[str, list[ClosedTrade]] = {}
    for t in trades:
        strat_trades.setdefault(t.strategy, []).append(t)

    lines.append(f"  {'Strategy':<22} {'Trades':>7} {'WR':>6} {'PnL':>10} {'AvgWin':>8} {'AvgLoss':>8}")
    lines.append("  " + "-" * 63)
    for strat in sorted(strat_trades.keys()):
        st = strat_trades[strat]
        s_total = len(st)
        s_wins = [t for t in st if t.pnl_usd > 0]
        s_wr = len(s_wins) / s_total * 100 if s_total > 0 else 0
        s_pnl = sum(t.pnl_usd for t in st)
        s_avg_w = sum(t.pnl_usd for t in s_wins) / len(s_wins) if s_wins else 0
        s_losses = [t for t in st if t.pnl_usd <= 0]
        s_avg_l = sum(t.pnl_usd for t in s_losses) / len(s_losses) if s_losses else 0
        lines.append(f"  {strat:<22} {s_total:>7} {s_wr:>5.1f}% ${s_pnl:>+9.2f} ${s_avg_w:>+7.2f} ${s_avg_l:>+7.2f}")
    lines.append("")

    # ---------------------------------------------------------------
    # PER-PAIR BREAKDOWN
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  PER-PAIR BREAKDOWN")
    lines.append(SEPARATOR)
    pair_trades: dict[str, list[ClosedTrade]] = {}
    for t in trades:
        pair_trades.setdefault(t.pair, []).append(t)

    lines.append(f"  {'Pair':<22} {'Trades':>7} {'WR':>6} {'PnL':>10}")
    lines.append("  " + "-" * 47)
    for pair in sorted(pair_trades.keys()):
        pt = pair_trades[pair]
        p_total = len(pt)
        p_wins = len([t for t in pt if t.pnl_usd > 0])
        p_wr = p_wins / p_total * 100 if p_total > 0 else 0
        p_pnl = sum(t.pnl_usd for t in pt)
        lines.append(f"  {pair:<22} {p_total:>7} {p_wr:>5.1f}% ${p_pnl:>+9.2f}")
    lines.append("")

    # ---------------------------------------------------------------
    # DAILY PNL TABLE
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  DAILY PNL")
    lines.append(SEPARATOR)
    daily_data: dict[str, list[ClosedTrade]] = {}
    for t in trades:
        day = t.exit_time.strftime("%Y-%m-%d")
        daily_data.setdefault(day, []).append(t)

    lines.append(f"  {'Date':<12} {'Trades':>7} {'Wins':>6} {'WR':>6} {'PnL':>10} {'Cum PnL':>10}")
    lines.append("  " + "-" * 53)
    cum_pnl = 0.0
    for day in sorted(daily_data.keys()):
        dt = daily_data[day]
        d_total = len(dt)
        d_wins = len([t for t in dt if t.pnl_usd > 0])
        d_wr = d_wins / d_total * 100 if d_total > 0 else 0
        d_pnl = sum(t.pnl_usd for t in dt)
        cum_pnl += d_pnl
        lines.append(f"  {day:<12} {d_total:>7} {d_wins:>6} {d_wr:>5.1f}% ${d_pnl:>+9.2f} ${cum_pnl:>+9.2f}")
    lines.append("")

    # ---------------------------------------------------------------
    # LONG vs SHORT BREAKDOWN
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  DIRECTION BREAKDOWN")
    lines.append(SEPARATOR)
    longs = [t for t in trades if t.direction == "long"]
    shorts = [t for t in trades if t.direction == "short"]
    for label, subset in [("LONG", longs), ("SHORT", shorts)]:
        s_total = len(subset)
        if s_total == 0:
            lines.append(f"  {label}: 0 trades")
            continue
        s_wins = len([t for t in subset if t.pnl_usd > 0])
        s_wr = s_wins / s_total * 100
        s_pnl = sum(t.pnl_usd for t in subset)
        lines.append(f"  {label:<6} : {s_total} trades | WR: {s_wr:.1f}% | PnL: ${s_pnl:+.2f}")
    lines.append("")

    # ---------------------------------------------------------------
    # RECENT TRADES (last 30)
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  RECENT TRADES (last 30)")
    lines.append(SEPARATOR)
    lines.append(f"  {'Pair':<18} {'Dir':<6} {'Entry':>10} {'Exit':>10} "
                 f"{'ROI%':>7} {'PnL$':>9} {'Reason':<16} {'Strategy':<18} {'Exit Time'}")
    lines.append("  " + "-" * 120)
    recent = trades[-30:]
    for t in recent:
        lines.append(
            f"  {t.pair:<18} {t.direction:<6} {t.entry_price:>10.4f} {t.exit_price:>10.4f}"
            f" {t.roi_pct:>+7.1f}% ${t.pnl_usd:>+8.2f} {t.exit_reason:<16} {t.strategy:<18}"
            f" {t.exit_time.strftime('%m-%d %H:%M')}"
        )
    lines.append("")

    # ---------------------------------------------------------------
    # LIMITATIONS BANNER
    # ---------------------------------------------------------------
    lines.append(SEPARATOR)
    lines.append("  LIMITATIONS")
    lines.append(SEPARATOR)
    lines.append("  - No order book data (no imbalance/depth gate)")
    lines.append("  - No tape data (no aggressor/large trade gate)")
    lines.append("  - No dynamic scanner (static pair list)")
    lines.append("  - Slippage estimated at 0.05%")
    lines.append("  - Live performance may differ +/-5-10% due to missing OB/tape confirmations")
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("  END OF REPORT")
    lines.append(SEPARATOR)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phmex-S backtesting engine (production)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=DEFAULT_PAIRS,
        metavar="PAIR",
        help="Trading pairs (e.g. ETH/USDT:USDT)",
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
        help="OHLCV timeframe (e.g. 1m, 5m, 15m)",
    )
    parser.add_argument(
        "--no-gates",
        action="store_true",
        default=False,
        help="Disable entry gates (cooldowns, regime filter, drawdown halt). Strength gate remains.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print()
    print(SEPARATOR)
    print("  PHMEX-S BACKTEST ENGINE")
    print(SEPARATOR)
    print(f"  Pairs     : {len(args.pairs)} pairs")
    print(f"  Timeframe : {args.timeframe}")
    print(f"  Period    : {args.days} days")
    print(f"  Gates     : {'OFF (raw signals)' if args.no_gates else 'ON (full pipeline)'}")
    print()

    # Init exchange (public endpoints only)
    exchange = ccxt.phemex({"enableRateLimit": True})
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"[WARN] Could not load markets: {e}")

    # Fetch data for all pairs
    pair_data: dict[str, pd.DataFrame] = {}
    for pair in args.pairs:
        print(f"\n[{pair}] Fetching data...")
        df_raw = fetch_ohlcv_full(exchange, pair, args.timeframe, args.days)
        if df_raw.empty:
            print(f"  [{pair}] No data returned. Skipping.")
            continue
        pair_data[pair] = df_raw
        time.sleep(0.3)

    if not pair_data:
        print("\nNo data fetched for any pair. Exiting.")
        return

    # Run backtest
    print(f"\n{'=' * 40}")
    print("  RUNNING BACKTEST")
    print(f"{'=' * 40}")

    trades = run_backtest(pair_data, no_gates=args.no_gates)

    if not trades:
        print("\nNo trades were generated. Try a longer period or different settings.")
        return

    # Generate report
    report = format_report(
        trades=trades,
        timeframe=args.timeframe,
        days=args.days,
        pairs=args.pairs,
        no_gates=args.no_gates,
    )

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
