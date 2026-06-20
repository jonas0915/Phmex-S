"""Causal feature engineering over the lab's per-symbol snapshot stream.

Derives a richer feature set than the raw ST2.0 trio (imbalance / buy_ratio /
trade_count): multi-snapshot deltas, trailing regimes, price momentum, and realized
volatility. Absorption is an INPUT here, not the signal — the model (Step 3) searches
this set for sub-conditions.

ISOLATION: pure stdlib, no bot.py import, no I/O. NO LOOKAHEAD — every engineered
feature at index i is a function of recs[:i+1] only. A feature that reads a future
snapshot would leak the forward-return label and manufacture an artifact (the exact
failure the lab exists to avoid). Each engineered key is documented inline with its
definition; raw record fields pass through unchanged.
"""
from __future__ import annotations

# Engineered feature keys this module adds to each record (raw fields pass through).
_FEATURE_NAMES = (
    "imbalance_delta",   # imbalance[i] - imbalance[i-1]      (0 at the first row)
    "buy_ratio_delta",   # buy_ratio[i] - buy_ratio[i-1]      (0 at the first row)
    "cvd_accel",         # cvd_slope[i] - cvd_slope[i-1]      (CVD acceleration; 0 at first)
    "price_mom",         # (price[i] - price[i-lookback]) / price[i-lookback]; 0 if i<lookback
    "imb_mean",          # trailing mean imbalance over the last lookback+1 snapshots
    "spread_regime",     # spread_pct[i] / trailing-median spread (1.0 = normal)
    "realized_vol",      # population stdev of trailing simple returns (0 if <2 returns)
)


def feature_names() -> tuple[str, ...]:
    """The engineered feature keys compute_features() adds to every record."""
    return _FEATURE_NAMES


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def compute_features(recs: list[dict], lookback: int = 5) -> list[dict]:
    """Return a NEW list parallel to `recs`; each dict is the original record plus the
    engineered features in feature_names(). Computed causally: index i uses only
    recs[:i+1]. `recs` must be time-ordered ascending (caller's responsibility)."""
    out: list[dict] = []
    for i, rec in enumerate(recs):
        prev = recs[i - 1] if i >= 1 else None
        lo = max(0, i - lookback)
        window = recs[lo:i + 1]                      # trailing window incl. current

        imb = float(rec.get("imbalance", 0.0))
        spread = float(rec.get("spread_pct", 0.0))
        price = float(rec.get("price", 0.0))

        imb_window = [float(r.get("imbalance", 0.0)) for r in window]
        spread_window = [float(r.get("spread_pct", 0.0)) for r in window]
        med_spread = _median(spread_window)

        # trailing simple returns within the window (causal)
        rets = []
        for a, b in zip(window, window[1:]):
            pa = float(a.get("price", 0.0))
            if pa > 0:
                rets.append((float(b.get("price", 0.0)) - pa) / pa)
        if len(rets) >= 2:
            mean_r = sum(rets) / len(rets)
            realized_vol = (sum((r - mean_r) ** 2 for r in rets) / len(rets)) ** 0.5
        else:
            realized_vol = 0.0

        if i >= lookback:
            base = float(recs[i - lookback].get("price", 0.0))
            price_mom = (price - base) / base if base > 0 else 0.0
        else:
            price_mom = 0.0

        feats = {
            "imbalance_delta": imb - float(prev.get("imbalance", 0.0)) if prev else 0.0,
            "buy_ratio_delta": float(rec.get("buy_ratio", 0.0)) - float(prev.get("buy_ratio", 0.0)) if prev else 0.0,
            "cvd_accel": float(rec.get("cvd_slope", 0.0)) - float(prev.get("cvd_slope", 0.0)) if prev else 0.0,
            "price_mom": price_mom,
            "imb_mean": sum(imb_window) / len(imb_window) if imb_window else 0.0,
            "spread_regime": spread / med_spread if med_spread > 0 else 1.0,
            "realized_vol": realized_vol,
        }
        out.append({**rec, **feats})
    return out
