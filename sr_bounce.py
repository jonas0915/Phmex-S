"""Ported 2026-07-28 from the kill-gate scan (reports/2026-07-28-sr-bounce-scan.md)
— scan verdict DO-NOT-BUILD; this module powers the owner-ordered paper forward
test. Parameters FROZEN; edit only with a new spec."""
import pandas as pd

# Zone/ADX cache (2026-07-28 review fix, I1): the scan this module ports
# recomputes validated_zones+adx per 1h bar; evaluate() was recomputing them
# every ~90s bot cycle per symbol over 500 rows even though the underlying
# htf_df only changes once an hour (see _fetch_sr_bounce_htf's own per-hour
# cache in bot.py) — scan-parity work wasted 39/40 times an hour. Keyed by
# (cache_key, htf bar identity); capped so a long-running bot can't leak
# unbounded symbol/hour combinations.
_zone_cache: dict = {}
_ZONE_CACHE_MAX = 64


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    tr = atr(df, n)
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def find_pivots(df: pd.DataFrame, k: int = 3) -> tuple[list[int], list[int]]:
    lows, highs = df["low"].values, df["high"].values
    lo_idx, hi_idx = [], []
    for i in range(k, len(df) - k):
        wl = lows[i - k:i + k + 1]
        if lows[i] == wl.min() and (wl < lows[i]).sum() == 0 and (wl == lows[i]).sum() == 1:
            lo_idx.append(i)
        wh = highs[i - k:i + k + 1]
        if highs[i] == wh.max() and (wh == highs[i]).sum() == 1:
            hi_idx.append(i)
    return lo_idx, hi_idx


def cluster_zones(prices: list[float], width: float) -> list[tuple[float, float]]:
    if not prices:
        return []
    prices = sorted(prices)
    zones, cur = [], [prices[0]]
    for p in prices[1:]:
        if p - cur[0] <= width:
            cur.append(p)
        else:
            zones.append((cur[0], cur[-1]))
            cur = [p]
    zones.append((cur[0], cur[-1]))
    return zones


def count_touches(df: pd.DataFrame, lo: float, hi: float, min_gap: int = 3) -> int:
    touches, last = 0, -10**9
    for i, row in df.iterrows():
        enters = row["low"] <= hi and row["high"] >= lo
        closes_out = row["close"] > hi or row["close"] < lo
        if enters and closes_out and (i - last) >= min_gap:
            touches += 1
            last = i
    return touches


def validated_zones(df: pd.DataFrame, k: int = 3, width_mult: float = 0.25,
                    min_touches: int = 2) -> list[dict]:
    width = width_mult * float(atr(df).iloc[-1])
    lo_idx, hi_idx = find_pivots(df, k)
    out = []
    for side, idxs, col in (("support", lo_idx, "low"), ("resistance", hi_idx, "high")):
        for zlo, zhi in cluster_zones([float(df[col].iloc[i]) for i in idxs], width):
            t = count_touches(df, zlo, zhi)
            if t >= min_touches:
                out.append({"lo": zlo, "hi": zhi, "side": side, "touches": t})
    return out


def confirmed_rejection(candle: dict, zone: dict) -> bool:
    if zone["side"] == "support":
        return candle["low"] <= zone["hi"] and candle["close"] > zone["hi"]
    return candle["high"] >= zone["lo"] and candle["close"] < zone["lo"]


def plan_trade(zone: dict, all_zones: list[dict], atr5: float, entry: float):
    if zone["side"] == "support":
        sl = zone["lo"] - 0.25 * atr5
        risk = entry - sl
        opposing = sorted(z["lo"] for z in all_zones
                          if z["side"] == "resistance" and z["lo"] > entry)
        if risk <= 0 or not opposing or (opposing[0] - entry) < risk:
            return None
        return {"side": "long", "sl": sl, "tp": min(opposing[0], entry + 3 * risk)}
    sl = zone["hi"] + 0.25 * atr5
    risk = sl - entry
    opposing = sorted((z["hi"] for z in all_zones
                       if z["side"] == "support" and z["hi"] < entry), reverse=True)
    if risk <= 0 or not opposing or (entry - opposing[0]) < risk:
        return None
    return {"side": "short", "sl": sl, "tp": max(opposing[0], entry - 3 * risk)}


def _hold(reason: str) -> dict:
    return {"signal": "hold", "reason": reason, "strength": 0.0,
            "sl_price": None, "tp_price": None}


def evaluate(df: pd.DataFrame, orderbook=None, htf_df: pd.DataFrame = None,
             cache_key=None) -> dict:
    """SR_BOUNCE paper-forward-test signal. Returns a plain dict (no TradeSignal
    import here — strategies.py imports this module, so this module must not
    import strategies.py). See module docstring for scan provenance.

    cache_key (2026-07-28 review fix, I1): when provided (bot.py passes the
    symbol), validated_zones()+adx() are cached per (cache_key, htf bar
    identity) instead of recomputed every call — the htf_df this is fed only
    changes once an hour (bot.py's _fetch_sr_bounce_htf per-hour cache), so
    recomputing on every ~90s bot cycle was pure waste. cache_key=None
    (tests, ad-hoc callers) always recomputes, matching prior behavior."""
    if df is None or len(df) < 3:
        return _hold("sr_bounce: insufficient 5m data")

    if htf_df is None or len(htf_df) < 100:
        return _hold("sr_bounce: no/short 1h context")

    if cache_key is not None:
        bar_id = (int(htf_df["ts"].iloc[-1]) if "ts" in htf_df.columns
                   else len(htf_df))
        key = (cache_key, bar_id)
        hit = _zone_cache.get(key)
        if hit is not None:
            zones, htf_adx = hit
        else:
            htf_adx = adx(htf_df).iloc[-1]
            zones = validated_zones(htf_df)
            _zone_cache[key] = (zones, htf_adx)
            while len(_zone_cache) > _ZONE_CACHE_MAX:
                _zone_cache.pop(next(iter(_zone_cache)))
    else:
        htf_adx = adx(htf_df).iloc[-1]
        zones = validated_zones(htf_df)

    if htf_adx >= 30:
        return _hold(f"sr_bounce: 1h ADX {htf_adx:.1f} >= 30 (trending)")

    if not zones:
        return _hold("sr_bounce: no validated zones")

    last = df.iloc[-2]  # last CLOSED 5m candle; iloc[-1] is the forming candle
    candle = {"open": last["open"], "high": last["high"],
              "low": last["low"], "close": last["close"]}

    for zone in zones:
        if confirmed_rejection(candle, zone):
            atr5 = float(atr(df.tail(100)).iloc[-1])
            plan = plan_trade(zone, zones, atr5, entry=candle["close"])
            if plan is None:
                return _hold("sr_bounce: rejection at zone but no room (skip rule)")
            side = "buy" if plan["side"] == "long" else "sell"
            reason = (f"SR BOUNCE {side} | zone {zone['lo']:.6g}-{zone['hi']:.6g} "
                      f"({zone['touches']} touches) | SL {plan['sl']:.6g} TP {plan['tp']:.6g}")
            return {"signal": side, "reason": reason, "strength": 0.82,
                    "sl_price": plan["sl"], "tp_price": plan["tp"]}

    return _hold("sr_bounce: no rejection at validated zones")
