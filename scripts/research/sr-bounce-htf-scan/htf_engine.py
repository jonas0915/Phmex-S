"""Generalized chronological replay for the SR_BOUNCE higher-timeframe
re-scan (pre-registration: docs/superpowers/specs/2026-07-29-sr-bounce-htf-
rescan-prereg.md).

Byte-faithful to the frozen scripts/research/sr-bounce-scan/engine.py's
trade-selection and fill/exit rules (strict-through fills, both-touched-in-
one-candle -> counts as stop_loss, one position per symbol, zone cache keyed
per new zone-TF bar, ADX(zone-TF) < 30 regime gate, entry signal only on a
CLOSED entry-TF candle), generalized in exactly two ways:

  1. The no-lookahead zone-context filter's bar duration (hardcoded
     3_600_000 for 1h in the frozen engine) is now the `zone_tf_ms`
     parameter, so 4h and 1d zone frames replay correctly. The entry-TF
     duration does NOT need its own parameter anywhere in this module: ATR
     and pivot math operate on price arrays / index windows, not on
     absolute timestamp deltas, so whichever candle series is passed as
     `df_entry` (15m or 1h) is handled correctly as-is.
  2. A funding cost is charged on every closed trade, always as a cost
     (never a credit), per the prereg: 0.01% of notional per 8h of hold
     time. Hold time is measured from the fill (position actually opens)
     to the exit (SL/TP), not from the earlier signal timestamp -- see
     .superpowers/sdd/htf-rescan-report.md methodology section for why
     this implementation choice (not explicitly specified by the prereg)
     was made this way.

Imports the frozen signal/level math directly -- never modifies it.
"""
import os
import sys

import pandas as pd

_SR_BOUNCE_SCAN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sr-bounce-scan")
if _SR_BOUNCE_SCAN_DIR not in sys.path:
    sys.path.insert(0, _SR_BOUNCE_SCAN_DIR)

from sr_levels import atr, adx, validated_zones  # noqa: E402  (frozen math)
from sr_signal import confirmed_rejection, plan_trade  # noqa: E402  (frozen math)

MIN_ZONE_BARS = 100     # same threshold as the frozen engine's MIN_1H
ZONE_TAIL = 500          # same lookback cap as the frozen engine's .tail(500)
ENTRY_ATR_WINDOW = 100   # same window as the frozen engine's i-100:i+1 slice

FUNDING_RATE_PER_8H = 0.0001   # 0.01% of notional per 8h, per prereg
FUNDING_PERIOD_S = 28_800      # 8h in seconds


def funding_cost(notional: float, hold_seconds: float,
                  funding_rate_per_8h: float = FUNDING_RATE_PER_8H,
                  funding_period_s: int = FUNDING_PERIOD_S) -> float:
    """Always non-negative -- funding is charged as a pure cost per the
    prereg (real funding is signed, but that's unmeasured and the bot's own
    funding capture is a known gap, so this scan can't assume a tailwind)."""
    if hold_seconds <= 0:
        return 0.0
    return notional * funding_rate_per_8h * (hold_seconds / funding_period_s)


def zone_context(df_zone: pd.DataFrame, current_ts: int, zone_tf_ms: int,
                  tail: int = ZONE_TAIL) -> pd.DataFrame:
    """Zone-TF candles that have fully CLOSED (open_ts + zone_tf_ms) at or
    before current_ts -- the no-lookahead filter, generalized."""
    return df_zone[df_zone["ts"] + zone_tf_ms <= current_ts].tail(tail).reset_index(drop=True)


def replay(df_zone: pd.DataFrame, df_entry: pd.DataFrame, symbol: str,
           notional: float = 50.0, fee_rt: float = 0.0012,
           zone_tf_ms: int = 3_600_000,
           funding_rate_per_8h: float = FUNDING_RATE_PER_8H,
           funding_period_s: int = FUNDING_PERIOD_S) -> list[dict]:
    trades, open_pos, pending = [], None, None
    zone_cache_key, zones, cur_adx = None, [], None

    for i in range(len(df_entry)):
        c = df_entry.iloc[i]
        candle = {"open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}

        # Zone-TF context: candles CLOSED at/before this entry candle's open
        # (no lookahead), generalized bar duration via zone_tf_ms.
        ctx = zone_context(df_zone, int(c["ts"]), zone_tf_ms)
        if len(ctx) < MIN_ZONE_BARS:
            continue
        key = int(ctx["ts"].iloc[-1])
        if key != zone_cache_key:
            zone_cache_key = key
            zones = validated_zones(ctx)
            cur_adx = float(adx(ctx).iloc[-1])

        # pending fill from last candle's signal
        if pending is not None:
            filled = (candle["low"] < pending["entry"] if pending["side"] == "long"
                      else candle["high"] > pending["entry"])
            open_pos = dict(pending, fill_i=i, fill_ts=int(c["ts"])) if filled else None
            pending = None

        # exit check
        if open_pos is not None:
            side, sl, tp = open_pos["side"], open_pos["sl"], open_pos["tp"]
            hit_sl = candle["low"] <= sl if side == "long" else candle["high"] >= sl
            hit_tp = candle["high"] >= tp if side == "long" else candle["low"] <= tp
            if hit_sl or hit_tp:
                reason = "stop_loss" if hit_sl else "take_profit"   # both -> SL
                px = sl if hit_sl else tp
                sgn = 1 if side == "long" else -1
                ret = sgn * (px - open_pos["entry"]) / open_pos["entry"]
                exit_ts = int(c["ts"])
                hold_s = max(0.0, (exit_ts - open_pos["fill_ts"]) / 1000.0)
                funding_usd = funding_cost(notional, hold_s, funding_rate_per_8h,
                                            funding_period_s)
                trades.append({
                    "symbol": symbol, "side": side, "signal_ts": open_pos["signal_ts"],
                    "entry": open_pos["entry"], "sl": sl, "tp": tp,
                    "exit_ts": exit_ts, "exit_price": px, "exit_reason": reason,
                    "fill_ts": open_pos["fill_ts"], "hold_s": hold_s,
                    "funding_usd": funding_usd,
                    "net_usd": notional * ret - notional * fee_rt - funding_usd,
                    "risk_pct": abs(open_pos["entry"] - sl) / open_pos["entry"] * 100,
                    "reward_pct": abs(tp - open_pos["entry"]) / open_pos["entry"] * 100,
                })
                open_pos = None
            continue

        # new signal (flat only, regime-gated)
        if cur_adx is None or cur_adx >= 30:
            continue
        atr_entry = float(atr(df_entry.iloc[max(0, i - ENTRY_ATR_WINDOW):i + 1]).iloc[-1])
        for z in zones:
            if confirmed_rejection(candle, z):
                plan = plan_trade(z, zones, atr_entry, entry=float(candle["close"]))
                if plan is not None:
                    pending = dict(plan, entry=float(candle["close"]),
                                   signal_ts=int(c["ts"]))
                    break
    return trades
