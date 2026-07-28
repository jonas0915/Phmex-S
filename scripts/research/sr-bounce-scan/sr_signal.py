"""Rejection trigger + structural trade geometry (spec §2, frozen)."""


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
