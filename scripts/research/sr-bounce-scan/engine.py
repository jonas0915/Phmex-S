"""Chronological replay with pessimistic fill/exit realism (spec §3)."""
import pandas as pd
from sr_levels import atr, adx, validated_zones
from sr_signal import confirmed_rejection, plan_trade

MIN_1H = 100


def replay(df1h: pd.DataFrame, df5m: pd.DataFrame, symbol: str,
           notional: float = 50.0, fee_rt: float = 0.0012) -> list[dict]:
    trades, open_pos, pending = [], None, None
    zone_cache_key, zones, cur_adx = None, [], None

    for i in range(len(df5m)):
        c = df5m.iloc[i]
        candle = {"open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}

        # 1h context: candles CLOSED at/before this 5m candle's open (no lookahead)
        ctx = df1h[df1h["ts"] + 3_600_000 <= c["ts"]].tail(500).reset_index(drop=True)
        if len(ctx) < MIN_1H:
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
            open_pos = dict(pending, fill_i=i) if filled else None
            pending = None
            if open_pos:
                # same-candle exit check happens below
                pass

        # exit check
        if open_pos is not None:
            side, sl, tp = open_pos["side"], open_pos["sl"], open_pos["tp"]
            hit_sl = candle["low"] <= sl if side == "long" else candle["high"] >= sl
            hit_tp = candle["high"] >= tp if side == "long" else candle["low"] <= tp
            if hit_sl or hit_tp:
                reason = "stop_loss" if hit_sl else "take_profit"   # both → SL
                px = sl if hit_sl else tp
                sgn = 1 if side == "long" else -1
                ret = sgn * (px - open_pos["entry"]) / open_pos["entry"]
                trades.append({
                    "symbol": symbol, "side": side, "signal_ts": open_pos["signal_ts"],
                    "entry": open_pos["entry"], "sl": sl, "tp": tp,
                    "exit_ts": int(c["ts"]), "exit_price": px, "exit_reason": reason,
                    "net_usd": notional * ret - notional * fee_rt,
                    "risk_pct": abs(open_pos["entry"] - sl) / open_pos["entry"] * 100,
                    "reward_pct": abs(tp - open_pos["entry"]) / open_pos["entry"] * 100,
                })
                open_pos = None
            continue

        # new signal (flat only, regime-gated)
        if cur_adx is None or cur_adx >= 30:
            continue
        atr5 = float(atr(df5m.iloc[max(0, i - 100):i + 1]).iloc[-1])
        for z in zones:
            if confirmed_rejection(candle, z):
                plan = plan_trade(z, zones, atr5, entry=float(candle["close"]))
                if plan is not None:
                    pending = dict(plan, entry=float(candle["close"]),
                                   signal_ts=int(c["ts"]))
                    break
    return trades
