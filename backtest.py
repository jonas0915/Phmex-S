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

import os
import sys

from indicators import add_all_indicators
from strategies import Signal, TradeSignal, confluence_strategy, htf_confluence_pullback

# Flow replay (offline calibration) — scripts/flow_replay.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
try:
    from flow_replay import passes_flow_gates as _passes_flow_gates
    from flow_replay import replay_confidence as _replay_confidence
except Exception:
    _passes_flow_gates = None
    _replay_confidence = None

# ---------------------------------------------------------------------------
# Constants (match .env)
# ---------------------------------------------------------------------------

TAKER_FEE_PCT = 0.06       # 0.06% per side
SLIPPAGE_PCT = 0.05         # 0.05% simulated slippage
LEVERAGE = 10
TRADE_SIZE_USD = 10.0       # margin per trade (matches .env TRADE_AMOUNT_USDT)
STARTING_BALANCE = 74.38    # approximate current balance (updated 2026-04-15)
SCALP_MIN_STRENGTH = 0.80   # matches live .env SCALP_MIN_STRENGTH (synced 2026-05-30; was stale 0.75)
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

# Adverse exit (matches live .env: ADVERSE_EXIT_THRESHOLD / ADVERSE_EXIT_CYCLES).
# Default mirrors current live state (disabled at -999.0 since 2026-05-07).
# Override via --ae-threshold / --ae-cycles to test variants in calibration.
DEFAULT_AE_THRESHOLD_ROI = -999.0   # ROI percent; trade exits when roi <= this AND cycles >= AE_MIN_CYCLES
DEFAULT_AE_MIN_CYCLES = 10           # 10 live cycles (~10 min) before AE can fire

# Per-pair cooldown after ANY loss (matches live bot.py:1032 — 600s = 10 candles on 1m).
PAIR_LOSS_COOLDOWN_CANDLES = 10

# Time-of-day filter (matches live bot.py:1172, 417-trade analysis).
# Blocked UTC hours: 0,1,2,9,17,18,19,20. PT-equivalent listed in live code.
BLOCKED_HOURS_UTC = {0, 1, 2, 9, 17, 18, 19, 20}

# HTF cluster throttle (matches live bot.py:1182). 30 min between any htf entry.
HTF_CLUSTER_THROTTLE_CANDLES = 30
HTF_STRATEGIES = {"htf_confluence_pullback", "htf_l2_anticipation"}


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
    # Order matters: check more-specific HTF strategies before generic substrings
    if "confluence pullback" in r:
        return "htf_confluence_pullback"
    if "l2 anticipation" in r:
        return "htf_l2_anticipation"
    if "confluence vwap" in r:
        return "htf_confluence_vwap"
    if "momentum continuation" in r:
        return "momentum_continuation"
    if "kc squeeze" in r or "keltner" in r:
        return "keltner_squeeze"
    if "bb" in r or "mean reversion" in r:
        return "bb_mean_reversion"
    if "trend pullback" in r:
        return "trend_pullback"
    if "trend scalp" in r or "trend_scalp" in r:
        return "trend_scalp"
    return "unknown"


def _classify_regime_label(last, df=None) -> str:
    """Port of bot.py:1810 _classify_regime (label only — that's all the gate uses)."""
    try:
        close = float(last.get("close", 0))
        adx = float(last.get("adx", 0))
        atr = float(last.get("atr", 0))
        ema9 = float(last.get("ema_9", 0))
        ema21 = float(last.get("ema_21", 0))
        ema50 = float(last.get("ema_50", 0))
        ema200 = float(last.get("ema_200", 0))
        vol = float(last.get("volume", 0))
        vol_avg = float(df["volume"].iloc[-20:].mean()) if df is not None and len(df) >= 20 else 0
    except (TypeError, ValueError):
        return "UNKNOWN"
    atr_pct = (atr / close) if close > 0 else 0
    vol_ratio = (vol / vol_avg) if vol_avg > 0 else 1.0
    above_ema200 = close > ema200 if ema200 > 0 else True
    stack_bull = ema9 > ema21 > ema50 > 0
    stack_bear = 0 < ema9 < ema21 < ema50
    if atr_pct > 0.015 or vol_ratio > 2.5:
        return "VOLATILE"
    if adx >= 25 and stack_bull and above_ema200:
        return "TRENDING_UP"
    if adx >= 25 and stack_bear and not above_ema200:
        return "TRENDING_DOWN"
    if adx < 20:
        return "CHOPPY"
    return "QUIET"


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
    entry_epoch: float = 0.0    # epoch seconds of entry (bar close) — live exit model
    entry_meta: dict = field(default_factory=dict)  # entry-time diagnostics (cohort-gate sims)

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
    entry_meta: dict = field(default_factory=dict)  # entry-time diagnostics (cohort-gate sims)


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
    max_tp_dist = entry_price * (TP_CAP_PCT / 100)
    # R:R >= 1:1 cap (risk_manager.py:508-512) — was MISSING here, letting sim SL
    # run up to 3.6% while live SL is hard-pinned. With TP cap 1.6% and tp_ratio 2.0
    # this collapses live SL to exactly the 1.2% floor and TP to 1.6% — confirmed by
    # live trades in the 5/11-5/30 window clustering at -13%/+16% ROI on exchange fills.
    max_sl_for_rr = max_tp_dist / mults["tp_ratio"]
    sl_dist = min(sl_dist, max(min_sl_dist, max_sl_for_rr))
    tp_dist = sl_dist * mults["tp_ratio"]
    # Cap TP at configured max so it's reachable on 1m scalp
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
    ae_threshold: float = DEFAULT_AE_THRESHOLD_ROI,
    ae_cycles: int = DEFAULT_AE_MIN_CYCLES,
) -> Optional[tuple[float, str]]:
    """
    Check all exit conditions for an open position.
    Returns (exit_price, reason) or None.
    Checks in priority order matching the live bot.

    ae_threshold/ae_cycles: adverse-exit. Default disabled (-999.0) to mirror
    current live config. Pass e.g. -3.0 / 10 to test live's pre-2026-05-07 behavior.
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
    # 2.5. Adverse exit (matches live risk_manager.py):
    #      roi <= ae_threshold AND cycles_held >= ae_cycles.
    #      Disabled by default (-999.0) to mirror live's 2026-05-07 setting.
    # ---------------------------------------------------------------
    roi = pos.roi(close)
    if candles_held >= ae_cycles and roi <= ae_threshold:
        exit_px = apply_slippage(close, pos.direction, entering=False)
        return exit_px, "adverse_exit"

    # ---------------------------------------------------------------
    # 3. Early exit: ROI >= 10% AND 2+ reversal signals
    # ---------------------------------------------------------------
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
# Live-fidelity exit engine (flow-replay calibration, 2026-06-11)
#
# Replaces the bar-close exit model above when flow replay is active. Mirrors
# the live 60s loop:
#   bot.py:680  early_exit        -> risk_manager.py:119 should_exit_early
#   bot.py:704  flat_exit         -> risk_manager.py:237 (240 cycles, -4<=roi<4)
#   bot.py:733  htf_trend_flip    -> bot.py:144-160 (1h ema21/ema50 flip)
#   bot.py:757  adverse_exit      -> risk_manager.py:207 (roi<=thresh after N cycles)
#   bot.py:815  hard_time_exit    -> risk_manager.py:218 (240 cycles, 1.5x ext if roi>=5)
#   bot.py:850  breakeven+trailing-> risk_manager.py:248 / risk_manager.py:44 tiers
#   bot.py:890  check_positions   -> risk_manager.py:670-691 software TP/SL/trailing
# plus the RESTING exchange SL/TP orders which fire intra-bar between cycles
# (live tags those fills "exchange_close" via _sync_exchange_closes).
#
# Intra-bar price path = captured flow snapshot prices (~75s cadence,
# FlowIndex.prices_between). Bars with no snapshot fall back to bar-close as a
# single cycle point + OHLC wick check (counted in stats["fallback_bars"]).
#
# Approximations (documented, unavoidable offline):
#   - early-exit indicator signals (rsi/macd/ema9) read the CURRENT 5m bar's
#     final values for intra-bar cycles (up to 5 min lookahead on those three
#     signals only; the dominant peak-drawdown + ROI conditions use snapshot
#     prices with no lookahead).
#   - when SL and TP are both inside one path segment / wick range, SL fills
#     first (pessimistic).
#   - live bot restarts reset cycle counters (time-based exits stretch); not modeled.
# ---------------------------------------------------------------------------

EARLY_EXIT_MIN_ROI = 3.0      # risk_manager.py:125 (override: --early-exit-min-roi)
FLAT_EXIT_CYCLES_LIVE = 240   # risk_manager.py:241 (240 x 60s = 4h)
HARD_TIME_CYCLES_LIVE = 240   # risk_manager.py:223

# --- Research exit knobs (2026-06-12 Phase 1 A/Bs; defaults = live parity) ---
TRAIL_ARM_ROI = 5.0           # risk_manager.py:47 arm threshold (override: --trail-arm-roi)
TRAIL_TIER1_LOCK = 2.0        # lock_in pct of the lowest trail tier AND fallthrough
                              # default (override: --trail-tier1-lock; pass -999 to
                              # remove the lock floor -> pure 3% trail in tier 1)
SL_RATCHET: list[tuple[float, float]] = []   # [(cycles, sl_pct_of_entry)] sorted asc;
                                             # empty = off (override: --sl-ratchet)
DEEP_RED_ROI: Optional[float] = None         # deep-red cut: exit when roi <= this ...
DEEP_RED_CYCLES = 120.0                      # ... after this many cycles. None = off.


def parse_sl_ratchet(spec: str) -> list[tuple[float, float]]:
    """Parse '60:0.8,120:0.6' -> [(60.0, 0.8), (120.0, 0.6)], sorted by cycles."""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        cyc, pct = part.split(":")
        out.append((float(cyc), float(pct)))
    return sorted(out)


def apply_exit_overrides(args) -> None:
    """Set the module-level exit knobs from an argparse namespace (shared by the
    CLI below and scripts/calibrate_exits.py). Only touches knobs present on args."""
    g = globals()
    for attr, name in [
        ("sl_floor_pct", "SL_FLOOR_PCT"),
        ("tp_cap_pct", "TP_CAP_PCT"),
        ("early_exit_min_roi", "EARLY_EXIT_MIN_ROI"),
        ("trail_arm_roi", "TRAIL_ARM_ROI"),
        ("trail_tier1_lock", "TRAIL_TIER1_LOCK"),
        ("deep_red_roi", "DEEP_RED_ROI"),
        ("deep_red_cycles", "DEEP_RED_CYCLES"),
    ]:
        v = getattr(args, attr, None)
        if v is not None:
            g[name] = v
    spec = getattr(args, "sl_ratchet", None)
    if spec:
        g["SL_RATCHET"] = parse_sl_ratchet(spec)


def _live_update_trailing(pos: BTPosition, price: float) -> None:
    """Port of risk_manager.py:44-98 update_trailing_stop (tiered, ROI-based)."""
    roi = pos.roi(price)
    if roi < TRAIL_ARM_ROI:
        return
    tiers = [
        (20.0, 15.0, 5.0),
        (15.0, 10.0, 5.0),
        (10.0,  6.0, 4.0),
        ( 8.0,  4.0, 4.0),
        ( 5.0, TRAIL_TIER1_LOCK, 3.0),
    ]
    lock_in_pct, trail_pct = TRAIL_TIER1_LOCK, 3.0
    for threshold, lock, trail in tiers:
        if roi >= threshold:
            lock_in_pct, trail_pct = lock, trail
            break
    if pos.direction == "long":
        if price > pos.peak_price or pos.peak_price == 0.0:
            pos.peak_price = price
        trail_price = pos.peak_price * (1 - trail_pct / 100 / LEVERAGE)
        lock_price = pos.entry_price * (1 + lock_in_pct / 100 / LEVERAGE)
        new_trail = max(trail_price, lock_price)
        if pos.trailing_stop_price is None or new_trail > pos.trailing_stop_price:
            pos.trailing_stop_price = new_trail
    else:
        if price < pos.peak_price or pos.peak_price == 0.0:
            pos.peak_price = price
        trail_price = pos.peak_price * (1 + trail_pct / 100 / LEVERAGE)
        lock_price = pos.entry_price * (1 - lock_in_pct / 100 / LEVERAGE)
        new_trail = min(trail_price, lock_price)
        if pos.trailing_stop_price is None or new_trail < pos.trailing_stop_price:
            pos.trailing_stop_price = new_trail


def _live_check_breakeven(pos: BTPosition, price: float) -> None:
    """Port of risk_manager.py:248-263 check_breakeven (1R -> entry +/- 0.25%)."""
    r_distance = abs(pos.entry_price - pos.sl_price)
    if r_distance <= 0:
        return
    if pos.direction == "long":
        if price >= pos.entry_price + r_distance:
            new_sl = pos.entry_price * 1.0025
            if new_sl > pos.sl_price:
                pos.sl_price = new_sl
    else:
        if price <= pos.entry_price - r_distance:
            new_sl = pos.entry_price * 0.9975
            if new_sl < pos.sl_price:
                pos.sl_price = new_sl


def _live_should_exit_early(pos: BTPosition, price: float,
                            last: pd.Series, prev: pd.Series) -> bool:
    """Port of risk_manager.py:119-193 should_exit_early (incl. peak tracking)."""
    roi = pos.roi(price)
    if roi < EARLY_EXIT_MIN_ROI:
        return False

    # Peak update inline (risk_manager.py:128-132)
    if pos.direction == "long" and price > pos.peak_price:
        pos.peak_price = price
    elif pos.direction == "short" and (price < pos.peak_price or pos.peak_price == 0.0):
        pos.peak_price = price

    signals = 0
    # Signal 1: RSI reversal
    rsi_v = last.get("rsi", 50)
    if pos.direction == "long":
        if rsi_v < 45:
            signals += 1
    else:
        if rsi_v > 55:
            signals += 1
    # Signal 2: MACD fresh crossover against position
    if "macd" in last and "macd_signal" in last:
        if pos.direction == "long":
            if last["macd"] < last["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
                signals += 1
        else:
            if last["macd"] > last["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
                signals += 1
    # Signal 3: price beyond EMA-9 two candles
    if "ema_9" in last and "ema_9" in prev:
        if pos.direction == "long":
            if last["close"] < last["ema_9"] and prev["close"] < prev["ema_9"]:
                signals += 1
        else:
            if last["close"] > last["ema_9"] and prev["close"] > prev["ema_9"]:
                signals += 1
    # Signal 4: peak drawdown (risk_manager.py:164-183)
    peak_roi = 0.0
    drawdown_from_peak = 0.0
    if pos.peak_price > 0 and pos.peak_price != pos.entry_price:
        if pos.direction == "long":
            peak_roi = (pos.peak_price - pos.entry_price) / pos.entry_price * 100 * LEVERAGE
            drawdown_from_peak = (pos.peak_price - price) / pos.peak_price * 100 * LEVERAGE
        else:
            peak_roi = (pos.entry_price - pos.peak_price) / pos.entry_price * 100 * LEVERAGE
            drawdown_from_peak = (price - pos.peak_price) / pos.peak_price * 100 * LEVERAGE
        if peak_roi >= 8.0 and drawdown_from_peak >= 3.0:
            return True  # Tier 1: immediate
        if peak_roi >= 5.0 and drawdown_from_peak >= 2.0:
            signals += 1  # Tier 2: counts as one signal

    if roi >= 8.0:
        return signals >= 1
    return signals >= 2


def _effective_stop(pos: BTPosition) -> float:
    """Live should_stop_loss (risk_manager.py:100-105): once the trail is armed
    it replaces the base SL (trail >= breakeven lock > base SL by construction)."""
    return pos.trailing_stop_price if pos.trailing_stop_price is not None else pos.sl_price


def _resting_order_hit(pos: BTPosition, seg_lo: float, seg_hi: float) -> Optional[tuple[float, str]]:
    """Did the price path segment [seg_lo, seg_hi] touch a RESTING exchange order?
    Fills between 60s cycles are what live tags 'exchange_close'.

    May-window vintage (verified in logs/bot.log.5+4+3): the exchange SL only
    ever moved on BREAKEVEN ('[BREAKEVEN] ... exchange SL updated'); the tiered
    trailing stop was SOFTWARE-ONLY (checked at 60s cycle prices). So intra-bar
    touches use pos.sl_price (breakeven-ratcheted base SL) — NOT the trail.
    Pessimistic: SL wins when both SL and TP are inside the segment."""
    if seg_lo <= pos.sl_price <= seg_hi:
        return pos.sl_price, "exchange_close"
    if seg_lo <= pos.tp_price <= seg_hi:
        return pos.tp_price, "exchange_close"
    return None


def check_exits_live(
    pos: BTPosition,
    candle: pd.Series,
    idx: int,
    df: pd.DataFrame,
    htf_window: Optional[pd.DataFrame],
    cycle_points: list[tuple[int, float]],
    bar_close_ts: int,
    ae_threshold: float,
    ae_cycles: int,
    stats: dict,
) -> Optional[tuple[float, str]]:
    """One 5m bar of the live exit pipeline. Returns (exit_price, reason) or None.

    cycle_points: [(epoch_s, price)] captured flow snapshots inside this bar —
    the 60s-cadence software exit checks run at each of these. Empty -> fall
    back to a single bar-close cycle + OHLC wick check (and count it).
    """
    open_p = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])

    last = df.iloc[idx]
    prev = df.iloc[idx - 1] if idx >= 1 else last

    points = [(t, p) for (t, p) in cycle_points if t > pos.entry_epoch]
    if points:
        stats["flow_bars"] = stats.get("flow_bars", 0) + 1
    else:
        stats["fallback_bars"] = stats.get("fallback_bars", 0) + 1
        points = [(bar_close_ts, close)]

    # HTF trend-flip state for this bar (bot.py:144-160) — htf_l2_anticipation
    # and htf_confluence_pullback only (bot.py:726).
    flip = False
    if pos.strategy in HTF_STRATEGIES and htf_window is not None and len(htf_window):
        h_last = htf_window.iloc[-1]
        ema21, ema50 = h_last.get("ema_21"), h_last.get("ema_50")
        if ema21 is not None and ema50 is not None and ema21 == ema21 and ema50 == ema50:
            if pos.direction == "long" and ema21 < ema50:
                flip = True
            elif pos.direction == "short" and ema21 > ema50:
                flip = True

    prev_p = open_p
    for t, p in points:
        # --- 0. Resting exchange SL/TP touched between cycles (intra-bar) ---
        hit = _resting_order_hit(pos, min(prev_p, p), max(prev_p, p))
        if hit:
            return hit
        prev_p = p

        roi = pos.roi(p)
        cycles_held = (t - pos.entry_epoch) / 60.0  # live cycle == 60s

        # --- 1. early_exit (bot.py:680) ---
        if _live_should_exit_early(pos, p, last, prev):
            return p, "early_exit"

        # --- 2. flat_exit (bot.py:704, risk_manager.py:237-246) ---
        if cycles_held >= FLAT_EXIT_CYCLES_LIVE and -4.0 <= roi < 4.0:
            return p, "flat_exit"

        # --- 3. HTF trend-flip exit (bot.py:733) ---
        if flip:
            return p, "htf_trend_flip_exit"

        # --- 4. adverse_exit (bot.py:757, risk_manager.py:207-216) ---
        if cycles_held >= ae_cycles and roi <= ae_threshold:
            return p, "adverse_exit"

        # --- 4b. deep-red cut (research knob, off unless --deep-red-roi set).
        # NOT the rejected AE-threshold family: AE swept thresholds at 10 cycles;
        # this fires only on deep losers held a long time (default 120 cycles). ---
        if DEEP_RED_ROI is not None and cycles_held >= DEEP_RED_CYCLES and roi <= DEEP_RED_ROI:
            return p, "deep_red_cut"

        # --- 5. hard time exit (bot.py:815, risk_manager.py:218-235) ---
        if cycles_held >= HARD_TIME_CYCLES_LIVE:
            if roi >= 5.0:
                if cycles_held >= HARD_TIME_CYCLES_LIVE * 1.5:
                    return p, "hard_time_exit"
            else:
                return p, "hard_time_exit"

        # --- 6. breakeven + trailing ratchet (bot.py:850-851) ---
        _live_check_breakeven(pos, p)
        _live_update_trailing(pos, p)

        # --- 6b. time-based SL ratchet (research knob, --sl-ratchet "60:0.8,120:0.6"):
        # after N cycles, tighten the effective RESTING SL to pct% of entry.
        # Tighten-only (never loosens, never undoes breakeven). The tightened
        # sl_price participates in the intra-bar resting-order checks above. ---
        if SL_RATCHET:
            r_pct = None
            for r_cycles, r_p in SL_RATCHET:
                if cycles_held >= r_cycles:
                    r_pct = r_p
            if r_pct is not None:
                if pos.direction == "long":
                    cand = pos.entry_price * (1 - r_pct / 100)
                    if cand > pos.sl_price:
                        pos.sl_price = cand
                else:
                    cand = pos.entry_price * (1 + r_pct / 100)
                    if cand < pos.sl_price:
                        pos.sl_price = cand

        # --- 7. software TP/SL/trailing at cycle price (risk_manager.py:670-691) ---
        if pos.direction == "long":
            tp_hit, sl_hit = p >= pos.tp_price, p <= _effective_stop(pos)
        else:
            tp_hit, sl_hit = p <= pos.tp_price, p >= _effective_stop(pos)
        if tp_hit:
            return p, "take_profit"
        if sl_hit:
            in_profit = pos.pnl_usd(p) > 0
            if pos.trailing_stop_price is not None and in_profit:
                return p, "trailing_stop"
            if in_profit:
                return p, "take_profit"
            return p, "stop_loss"

    # --- End of bar: wick check beyond the sampled path (resting orders) ---
    hit = _resting_order_hit(pos, low, high)
    if hit:
        return hit
    return None


# ---------------------------------------------------------------------------
# Core backtest engine
# ---------------------------------------------------------------------------

def run_backtest(
    pair_data: dict[str, pd.DataFrame],
    htf_data: dict[str, pd.DataFrame] | None = None,
    no_gates: bool = False,
    calibration_mode: bool = False,
    ae_threshold: float = DEFAULT_AE_THRESHOLD_ROI,
    ae_cycles: int = DEFAULT_AE_MIN_CYCLES,
    flow_index=None,
    flow_replay: bool = False,
    live_exit_model: Optional[bool] = None,
    fee_rt_pct: float = (TAKER_FEE_PCT + SLIPPAGE_PCT) * 2,
    block_ltbias: Optional[float] = None,
    block_adx5m: Optional[float] = None,
    min_conf: Optional[int] = None,
    extra_blocked_hours: Optional[set] = None,
    no_whale_boost: bool = False,
) -> list[ClosedTrade]:
    """
    Run the full backtest across all pairs simultaneously.
    Processes candles sequentially, checking all pairs each candle.

    htf_data: optional 1h dataframes per pair. Required for htf_confluence_pullback /
              htf_l2_anticipation strategies — without it, confluence_strategy returns HOLD.
    calibration_mode: if True, bypass confluence_strategy router and call
                     htf_confluence_pullback directly. Used for backtester calibration
                     against live PnL when l2_anticipation can't be replayed (no flow).
    live_exit_model: use the 60s-cadence live exit pipeline (check_exits_live) with
                     captured flow prices as the intra-bar path. Defaults to ON when
                     flow_replay is on. Fee model becomes risk_manager.py:611 paper
                     model: net = gross - notional * fee_rt_pct/100 (0.22% RT default),
                     no separate price slippage on entry/exit fills.

    Phase-3 cohort-gate flags (2026-06-11 edge plan §6, ALL default-off — existing
    calibration runs are unaffected). Candidate entry gates simulated, NOT live:
    block_ltbias:        skip entry when ALIGNED large_trade_bias >= X (aligned =
                         raw lt_bias for longs, negated for shorts). Needs flow_replay.
    block_adx5m:         skip entry when the 5m ADX at entry >= X.
    min_conf:            override the replay ensemble floor (live 4/7). NOTE replay
                         confidence caps at 6/7 (funding layer not captured).
    extra_blocked_hours: set of extra UTC hours appended to BLOCKED_HOURS_UTC.
    no_whale_boost:      undo the aligned-whale strength boost (+0.03,
                         strategies.py:601-606) post-hoc before the min-strength
                         check — the sim calls the real strategy, so the boost is
                         reversed here in the harness (strategies.py untouched).
                         Exact because the 0.92 strength cap can never bind for
                         htf_l2_anticipation in replay (max 0.82+0.03+0.02+0.02=0.89).
    """
    htf_data = htf_data or {}
    if live_exit_model is None:
        live_exit_model = flow_replay

    # Compute indicators on full datasets upfront (5m and 1h)
    pair_dfs: dict[str, pd.DataFrame] = {}
    htf_dfs: dict[str, pd.DataFrame] = {}
    for pair, df_raw in pair_data.items():
        df = add_all_indicators(df_raw)
        if df.empty or len(df) < WARMUP:
            print(f"  [{pair}] Not enough data after indicator warmup ({len(df)} rows). Skipping.")
            continue
        pair_dfs[pair] = df
        htf_raw = htf_data.get(pair)
        if htf_raw is not None and not htf_raw.empty:
            htf_with_ind = add_all_indicators(htf_raw)
            if not htf_with_ind.empty and len(htf_with_ind) >= 30:
                htf_dfs[pair] = htf_with_ind

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
    last_htf_entry_candle = -HTF_CLUSTER_THROTTLE_CANDLES  # htf cluster throttle
    pair_loss_streak: dict[str, int] = {}
    pair_cooldown_until: dict[str, int] = {}  # pair -> candle index when cooldown expires
    trade_results: deque = deque(maxlen=6)
    regime_pause_until = 0  # candle index when regime pause expires
    drawdown_pause_until = 0  # candle index when drawdown pause expires
    virtual_candle = 0  # global candle counter
    exit_stats: dict = {}  # live exit model: flow_bars / fallback_bars counters

    # Bar duration (sec) per pair — needed to anchor entry_epoch / cycle clocks
    bar_seconds: dict[str, int] = {}
    for pair, df in pair_dfs.items():
        diffs = pd.Series(df.index).diff().dropna()
        bar_seconds[pair] = int(diffs.median().total_seconds()) if len(diffs) else 300

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

            if live_exit_model:
                if idx <= pos.entry_candle:
                    continue  # exits start the bar after entry (live: position opens mid-loop)
                bar_open_ts = int(df.index[idx].timestamp())
                bar_close_ts = bar_open_ts + bar_seconds.get(pair, 300)
                cycle_points = (
                    flow_index.prices_between(pair, bar_open_ts, bar_close_ts)
                    if flow_index is not None else []
                )
                # HTF window for trend-flip exit (sliced to current time, no lookahead)
                htf_df_full_x = htf_dfs.get(pair)
                htf_window_x = None
                if htf_df_full_x is not None and pos.strategy in HTF_STRATEGIES:
                    h_idx = htf_df_full_x.index.searchsorted(candle_time, side="right") - 1
                    if h_idx >= 1:
                        htf_window_x = htf_df_full_x.iloc[max(0, h_idx - 2):h_idx + 1]
                result = check_exits_live(
                    pos, candle, idx, df, htf_window_x, cycle_points, bar_close_ts,
                    ae_threshold=ae_threshold, ae_cycles=ae_cycles, stats=exit_stats,
                )
            else:
                result = check_exits(pos, candle, idx, df_window, ae_threshold=ae_threshold, ae_cycles=ae_cycles)
            if result is not None:
                exit_price, reason = result
                gross_pnl = pos.pnl_usd(exit_price)
                # Fee model: live exit model uses the risk_manager.py:611 paper round
                # trip (taker 0.06% + slippage 0.05% per side on notional, 0.22% RT);
                # legacy model keeps explicit price slippage + taker-only fees.
                if live_exit_model:
                    fees = pos.size_usd * fee_rt_pct / 100.0
                else:
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
                    entry_meta=pos.entry_meta,
                )
                closed_trades.append(trade)
                balance += net_pnl
                if balance > peak_balance:
                    peak_balance = balance
                pairs_to_close.append(pair)

                # Track cooldowns (matches live bot.py:1032 — 10 min after ANY loss + 4hr blacklist on 3-streak)
                is_loss = net_pnl < 0
                if is_loss:
                    pair_cooldown_until[pair] = max(
                        pair_cooldown_until.get(pair, 0),
                        virtual_candle + PAIR_LOSS_COOLDOWN_CANDLES,
                    )
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

            # Call strategy with HTF context (single pass — no OB re-run)
            win_start = max(0, idx - 200)
            df_window = df.iloc[win_start:idx + 1]

            # Slice 1h HTF window up to current candle_time
            htf_df_full = htf_dfs.get(pair)
            htf_window = None
            if htf_df_full is not None:
                htf_idx = htf_df_full.index.searchsorted(candle_time, side="right") - 1
                if htf_idx >= 30:
                    htf_window = htf_df_full.iloc[max(0, htf_idx - 200):htf_idx + 1]

            # Flow replay: look up captured ob+flow for this candle so the live
            # flow-dependent strategy + gates can fire. No snapshot -> skip (can't
            # faithfully replay flow we never captured).
            ob_rp, flow_rp = (None, None)
            if flow_replay:
                if flow_index is None:
                    continue
                ob_rp, flow_rp = flow_index.get(pair, int(candle_time.timestamp()))
                if flow_rp is None:
                    continue

            try:
                if flow_replay:
                    signal = confluence_strategy(df_window, ob_rp, htf_df=htf_window, flow=flow_rp)
                elif calibration_mode:
                    # Calibration: call htf_confluence_pullback directly (OHLCV-only,
                    # no flow needed). Bypass confluence_strategy router which would
                    # otherwise route to htf_l2_anticipation (requires flow → HOLD).
                    signal = htf_confluence_pullback(df_window, None, htf_window)
                else:
                    signal = confluence_strategy(df_window, None, htf_df=htf_window)
            except Exception:
                continue

            if signal.signal == Signal.HOLD:
                continue

            strategy_name = _extract_strategy_name(signal.reason)
            _dir = "long" if signal.signal == Signal.BUY else "short"
            _entry_conf = None  # diagnostics (set below when flow gates run)

            # --- Cohort gate A' (--no-whale-boost, default OFF): reverse the
            # aligned-whale +0.03 strength boost (strategies.py:601-606) post-hoc.
            # The sim calls the real strategy, so the boost is undone here in the
            # harness instead of editing strategies.py. Exact: the min(strength,
            # 0.92) cap never binds for htf_l2_anticipation in replay (walls are
            # sanitized to [], max possible = 0.82+0.03+0.02+0.02 = 0.89).
            raw_strength = signal.strength
            if no_whale_boost and flow_replay and strategy_name == "htf_l2_anticipation" and flow_rp:
                _lt_nb = flow_rp.get("large_trade_bias", 0.0) or 0.0
                if (_dir == "long" and _lt_nb > 0.2) or (_dir == "short" and _lt_nb < -0.2):
                    raw_strength -= 0.03

            # Short penalty (bot.py:1051-1053): -0.04 strength on SELL signals,
            # applied BEFORE the min-strength check. Was never ported — root cause
            # of the ZEC 10x overfire (sim 30 shorts vs live 15; longs matched 22=22).
            # NOTE: keep the live float semantics (0.84-0.04 = 0.7999... < 0.80 blocks).
            sig_strength = raw_strength - 0.04 if signal.signal == Signal.SELL else raw_strength

            # Min strength check (live: Config.SCALP_MIN_STRENGTH)
            if sig_strength < SCALP_MIN_STRENGTH:
                continue

            # --- Flow gate port (live bot.py:1082-1143), replayed from capture ---
            if flow_replay and not no_gates and _passes_flow_gates is not None:
                # Live uses one-bar-back EMA for slope (bot.py:289) -> iloc[-2].
                _htf_last = htf_window.iloc[-1] if htf_window is not None and len(htf_window) else None
                _htf_prev = htf_window.iloc[-2] if htf_window is not None and len(htf_window) >= 2 else _htf_last
                _ok, _ = _passes_flow_gates(strategy_name, _dir, ob_rp, flow_rp, candle,
                                            _htf_last, _htf_prev, min_conf=min_conf)
                if not _ok:
                    continue
                if _replay_confidence is not None:
                    _entry_conf, _ = _replay_confidence(candle, ob_rp, flow_rp,
                                                        _htf_last, _htf_prev, _dir,
                                                        strat_name=strategy_name)

                # QUIET regime gate (bot.py:1303-1322 + _classify_regime bot.py:1810):
                # ADX in [20,25) with no EMA stack/trend and not volatile -> block
                # unless flow CVD confirms direction. Was never ported (second ZEC
                # overfire contributor — live blocked ZEC shorts in QUIET chop).
                if _classify_regime_label(candle, df_window) == "QUIET":
                    _flow_confirms = False
                    if flow_rp and flow_rp.get("trade_count", 0) > 5:
                        if _dir == "long" and flow_rp.get("cvd_slope", 0) > 0.2:
                            _flow_confirms = True
                        if _dir == "short" and flow_rp.get("cvd_slope", 0) < -0.2:
                            _flow_confirms = True
                    if not _flow_confirms:
                        continue

            # --- Phase-3 cohort gate A (--block-ltbias, default OFF): skip entry
            # when ALIGNED large_trade_bias >= threshold. Aligned = raw lt_bias for
            # longs, negated for shorts (audit 2026-06-11 §2.1: the >=0.36 aligned
            # tercile is the worst cohort, -$9.97 / 35.5% WR). Missing key -> 0.0
            # (gate passes); presence is measured via entry_meta coverage.
            if block_ltbias is not None and flow_replay and flow_rp is not None:
                _lt_a = flow_rp.get("large_trade_bias", 0.0) or 0.0
                _aligned_lt = _lt_a if _dir == "long" else -_lt_a
                if _aligned_lt >= block_ltbias:
                    continue

            # --- Phase-3 cohort gate B (--block-adx5m, default OFF): skip entry
            # when the 5m ADX at entry >= threshold (audit §2.5: ADX>=25 cohort
            # 38.7% WR vs 53-63% below). NaN ADX passes (no data, no gate).
            if block_adx5m is not None:
                _adx5 = float(candle.get("adx", float("nan")))
                if _adx5 == _adx5 and _adx5 >= block_adx5m:
                    continue

            # --- Cooldowns (skip in no-gates mode) ---
            if not no_gates:
                # Global cooldown: 2 candles between any trades (continue, not break)
                if virtual_candle - last_entry_candle < GLOBAL_COOLDOWN_CANDLES:
                    continue

                # Per-pair cooldown
                if pair in pair_cooldown_until and virtual_candle < pair_cooldown_until[pair]:
                    continue

                # Time-of-day filter (matches live bot.py:1172, 417-trade analysis)
                # Phase-3 cohort gate D (--extra-blocked-hours, default OFF) appends
                # extra UTC hours (audit §2.6: UTC 21-23 = 2-4 PM PT, -$9.34/n=22).
                _utc_hour = candle_time.hour if hasattr(candle_time, "hour") else 0
                if _utc_hour in BLOCKED_HOURS_UTC:
                    continue
                if extra_blocked_hours and _utc_hour in extra_blocked_hours:
                    continue

                # HTF cluster throttle (matches live bot.py:1182, 30 min between any htf entry)
                if strategy_name in HTF_STRATEGIES:
                    if virtual_candle - last_htf_entry_candle < HTF_CLUSTER_THROTTLE_CANDLES:
                        continue

            # --- Open position ---
            entry_price = float(candle["close"])
            direction = "long" if signal.signal == Signal.BUY else "short"
            # Live exit model charges slippage inside the 0.22% RT fee (risk_manager
            # paper model) — don't also worsen the fill price.
            fill_price = entry_price if live_exit_model else apply_slippage(entry_price, direction, entering=True)

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

            # Entry-time diagnostics for the cohort-gate sims (carried onto the
            # ClosedTrade; lets the sweep report measure gate coverage + cohorts).
            entry_meta = {}
            if flow_replay:
                _lt_m = flow_rp.get("large_trade_bias") if flow_rp else None
                _adx_m = float(candle.get("adx", float("nan")))
                entry_meta = {
                    "lt_bias": _lt_m,
                    "aligned_lt": (_lt_m if direction == "long" else -_lt_m) if _lt_m is not None else None,
                    "adx5m": _adx_m if _adx_m == _adx_m else None,
                    "conf": _entry_conf,
                    "hour_utc": int(candle_time.hour) if hasattr(candle_time, "hour") else None,
                    "trade_count": flow_rp.get("trade_count") if flow_rp else None,
                    "strength": round(sig_strength, 4),
                    "flow_age_s": (flow_index.snapshot_age(pair, int(candle_time.timestamp()))
                                   if flow_index is not None and hasattr(flow_index, "snapshot_age") else None),
                }

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
                entry_epoch=int(df.index[idx].timestamp()) + bar_seconds.get(pair, 300),
                entry_meta=entry_meta,
            )
            open_positions[pair] = pos
            last_entry_candle = virtual_candle
            if strategy_name in HTF_STRATEGIES:
                last_htf_entry_candle = virtual_candle

    # ===================================================================
    # Force-close remaining positions at end of data
    # ===================================================================
    for pair, pos in open_positions.items():
        df = pair_dfs[pair]
        last_candle = df.iloc[-1]
        if live_exit_model:
            exit_price = float(last_candle["close"])
            fees = pos.size_usd * fee_rt_pct / 100.0
        else:
            exit_price = apply_slippage(float(last_candle["close"]), pos.direction, entering=False)
            fees = round_trip_fees(pos.size_usd)
        gross_pnl = pos.pnl_usd(exit_price)
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
            entry_meta=pos.entry_meta,
        )
        closed_trades.append(trade)
        balance += net_pnl

    if live_exit_model:
        fb = exit_stats.get("fallback_bars", 0)
        fl = exit_stats.get("flow_bars", 0)
        tot = fb + fl
        pct = fb / tot * 100 if tot else 0.0
        print(f"\n  [exit model] live 60s-cadence pipeline | bars with flow price path: {fl} | "
              f"bar-close fallback (no snapshot in bar): {fb} ({pct:.1f}%)")

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
    lines.append(f"  Strategy   : confluence{' (no gates)' if no_gates else ''}")
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
    lines.append("  - No tape data (no aggressor/large trade gate, no ensemble confidence)")
    lines.append("  - No dynamic scanner (static pair list)")
    lines.append("  - No daily-symbol-cap, per-pair-loss-cooldown, or profitable-hours filter")
    lines.append("  - Slippage estimated at 0.05%")
    lines.append("  - CALIBRATION (2026-05-11, ETH 45d htf_confluence_pullback):")
    lines.append("      Fire rate ~10x live (sim 342 trades vs live 34, +906%)")
    lines.append("      PnL ~64x live loss (sim -$63.84 vs live -$0.99)")
    lines.append("      Correction factor: divide sim trade count by ~10 to approximate live rate")
    lines.append("      Engine is structurally correct but missing live entry gates (tape/ensemble/daily-cap)")
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
    parser.add_argument(
        "--calibration",
        action="store_true",
        default=False,
        help="Calibration mode: bypass confluence_strategy router, call htf_confluence_pullback directly. "
             "Used for backtester calibration vs live PnL — htf_l2_anticipation cannot be replayed without live flow.",
    )
    parser.add_argument(
        "--ae-threshold",
        type=float,
        default=DEFAULT_AE_THRESHOLD_ROI,
        help="Adverse-exit ROI threshold (percent). Trade exits when roi <= this AND cycles_held >= --ae-cycles. "
             "Default mirrors current live (-999.0 = disabled). Set -3.0 to test live's pre-2026-05-07 behavior.",
    )
    parser.add_argument(
        "--ae-cycles",
        type=int,
        default=DEFAULT_AE_MIN_CYCLES,
        help="Minimum candles held before adverse-exit can fire (matches live ADVERSE_EXIT_CYCLES).",
    )
    # --- Phase-1 exit-rule A/B knobs (2026-06-12 edge plan). Defaults None =
    # keep live-parity module constants; research tooling only, live bot reads none.
    parser.add_argument(
        "--sl-floor-pct",
        type=float,
        default=None,
        metavar="PCT",
        help="SL floor as %% of entry (live 1.2). A/B 1: 0.9 / 0.8.",
    )
    parser.add_argument(
        "--tp-cap-pct",
        type=float,
        default=None,
        metavar="PCT",
        help="Max TP distance as %% of entry (live 1.6).",
    )
    parser.add_argument(
        "--early-exit-min-roi",
        type=float,
        default=None,
        metavar="ROI",
        help="Min ROI %% before early_exit signals can fire (live 3.0). A/B 4: 6.0.",
    )
    parser.add_argument(
        "--trail-arm-roi",
        type=float,
        default=None,
        metavar="ROI",
        help="ROI %% at which the tiered trail arms (live 5.0). A/B 5: 8.0.",
    )
    parser.add_argument(
        "--trail-tier1-lock",
        type=float,
        default=None,
        metavar="PCT",
        help="Tier-1 lock-in ROI %% (live 2.0). Pass -999 to remove the lock floor "
             "(pure 3%% trail in tier 1).",
    )
    parser.add_argument(
        "--sl-ratchet",
        type=str,
        default=None,
        metavar="C:P,...",
        help='Time-ratchet the resting SL: "60:0.8,120:0.6" = tighten SL to 0.8%% of '
             "entry after 60 cycles, 0.6%% after 120. Tighten-only. Off by default.",
    )
    parser.add_argument(
        "--deep-red-roi",
        type=float,
        default=None,
        metavar="ROI",
        help="Deep-red cut: exit when ROI <= this after --deep-red-cycles (A/B 3: -6.0 "
             "at 120 cycles). Off by default. Distinct from the rejected 10-cycle AE sweep.",
    )
    parser.add_argument(
        "--deep-red-cycles",
        type=float,
        default=None,
        metavar="N",
        help="Cycles held before the deep-red cut can fire (default 120).",
    )
    # --- Phase-3 cohort-gate flags (2026-06-11 edge plan §6). ALL default-off:
    # existing runs / calibration are unaffected unless explicitly passed. The
    # flow-dependent ones (--block-ltbias, --no-whale-boost, --min-conf) only act
    # in flow-replay runs (driven via scripts/, not this network-fetch CLI path).
    parser.add_argument(
        "--block-ltbias",
        type=float,
        default=None,
        metavar="X",
        help="Skip entry when ALIGNED large_trade_bias >= X (raw for longs, negated for shorts). "
             "Audit nominal: 0.35. Flow-replay runs only.",
    )
    parser.add_argument(
        "--block-adx5m",
        type=float,
        default=None,
        metavar="X",
        help="Skip entry when 5m ADX at entry >= X. Audit nominal: 25.",
    )
    parser.add_argument(
        "--min-conf",
        type=int,
        default=None,
        metavar="N",
        help="Override the ensemble confidence floor (live 4/7). Audit nominal: 5. "
             "Replay confidence caps at 6/7 (funding layer not captured).",
    )
    parser.add_argument(
        "--extra-blocked-hours",
        type=str,
        default=None,
        metavar="H,H,...",
        help='Extra UTC hours appended to BLOCKED_HOURS_UTC, e.g. "21,22,23".',
    )
    parser.add_argument(
        "--no-whale-boost",
        action="store_true",
        default=False,
        help="Reverse the aligned large_trade_bias +0.03 strength boost (strategies.py:601-606) "
             "post-hoc in the sim harness. Flow-replay runs only.",
    )
    parser.add_argument(
        "--fee-rt",
        type=float,
        default=None,
        metavar="PCT",
        help="Round-trip fee %% of notional for the live exit model (measured live: 0.0663, "
             "docs/2026-06-11-fee-ground-truth.md). Default keeps the 0.22 paper model.",
    )
    parser.add_argument(
        "--starting-balance",
        type=float,
        default=STARTING_BALANCE,
        help="Override starting balance. Used to match live balance at the start of a calibration window.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        metavar="PATH",
        help="Dump summary JSON to PATH after run (trades, total_pnl, win_rate, by_strategy). "
             "Consumed by scripts/calibrate_compare.py.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.starting_balance != STARTING_BALANCE:
        globals()["STARTING_BALANCE"] = args.starting_balance

    apply_exit_overrides(args)

    print()
    print(SEPARATOR)
    print("  PHMEX-S BACKTEST ENGINE")
    print(SEPARATOR)
    print(f"  Pairs     : {len(args.pairs)} pairs")
    print(f"  Timeframe : {args.timeframe}")
    print(f"  Period    : {args.days} days")
    print(f"  Gates     : {'OFF (raw signals)' if args.no_gates else 'ON (full pipeline)'}")
    print(f"  Start bal : ${STARTING_BALANCE:.2f}")
    print()

    # Init exchange (public endpoints only)
    exchange = ccxt.phemex({"enableRateLimit": True})
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"[WARN] Could not load markets: {e}")

    # Fetch data for all pairs (5m for entry, 1h for HTF context)
    pair_data: dict[str, pd.DataFrame] = {}
    htf_data: dict[str, pd.DataFrame] = {}
    for pair in args.pairs:
        print(f"\n[{pair}] Fetching data...")
        df_raw = fetch_ohlcv_full(exchange, pair, args.timeframe, args.days)
        if df_raw.empty:
            print(f"  [{pair}] No 5m data returned. Skipping.")
            continue
        time.sleep(0.3)
        df_htf = fetch_ohlcv_full(exchange, pair, "1h", args.days)
        if df_htf.empty:
            print(f"  [{pair}] No 1h HTF data returned. Skipping.")
            continue
        pair_data[pair] = df_raw
        htf_data[pair] = df_htf
        time.sleep(0.3)

    if not pair_data:
        print("\nNo data fetched for any pair. Exiting.")
        return

    # Run backtest
    print(f"\n{'=' * 40}")
    print("  RUNNING BACKTEST")
    print(f"{'=' * 40}")

    _extra_hours = None
    if args.extra_blocked_hours:
        _extra_hours = {int(h) for h in args.extra_blocked_hours.split(",") if h.strip() != ""}

    _rb_kwargs = {}
    if args.fee_rt is not None:
        _rb_kwargs["fee_rt_pct"] = args.fee_rt

    trades = run_backtest(
        pair_data,
        htf_data=htf_data,
        no_gates=args.no_gates,
        calibration_mode=args.calibration,
        ae_threshold=args.ae_threshold,
        ae_cycles=args.ae_cycles,
        block_ltbias=args.block_ltbias,
        block_adx5m=args.block_adx5m,
        min_conf=args.min_conf,
        extra_blocked_hours=_extra_hours,
        no_whale_boost=args.no_whale_boost,
        **_rb_kwargs,
    )

    if args.output_json:
        _dump_summary_json(trades, args)

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


def _dump_summary_json(trades: list, args: argparse.Namespace) -> None:
    import json

    by_strategy: dict[str, dict] = {}
    by_pair: dict[str, dict] = {}
    for t in trades:
        strat = getattr(t, "strategy", "unknown") or "unknown"
        by_strategy.setdefault(strat, {"trades": 0, "total_pnl": 0.0, "wins": 0})
        by_strategy[strat]["trades"] += 1
        by_strategy[strat]["total_pnl"] += t.pnl_usd
        if t.pnl_usd > 0:
            by_strategy[strat]["wins"] += 1
        pair = getattr(t, "pair", "unknown") or "unknown"
        by_pair.setdefault(pair, {"trades": 0, "total_pnl": 0.0})
        by_pair[pair]["trades"] += 1
        by_pair[pair]["total_pnl"] += t.pnl_usd

    total = len(trades)
    total_pnl = sum(t.pnl_usd for t in trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    summary = {
        "trades": total,
        "total_pnl": round(total_pnl, 4),
        "win_rate": round(wins / total * 100, 2) if total else 0.0,
        "wins": wins,
        "losses": total - wins,
        "by_strategy": {k: {**v, "total_pnl": round(v["total_pnl"], 4)} for k, v in by_strategy.items()},
        "by_pair": {k: {**v, "total_pnl": round(v["total_pnl"], 4)} for k, v in by_pair.items()},
        "args": {
            "pairs": args.pairs,
            "days": args.days,
            "timeframe": args.timeframe,
            "calibration": args.calibration,
            "no_gates": args.no_gates,
            "ae_threshold": args.ae_threshold,
            "ae_cycles": args.ae_cycles,
            "starting_balance": STARTING_BALANCE,
        },
    }
    try:
        with open(args.output_json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"\n  Summary JSON: {args.output_json}")
    except OSError as e:
        print(f"\n  [WARN] Could not write summary JSON: {e}")


if __name__ == "__main__":
    main()
