"""Pure S/R level math for the SR_BOUNCE kill-gate scan.
Frozen parameters live in the spec (2026-07-28); no tuning here."""
import pandas as pd


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
