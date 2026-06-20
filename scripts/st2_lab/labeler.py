"""Adverse-fill-aware labeled dataset — the supervised examples the ranker scores.

Builds, for every ST2.0-style base signal in the snapshot stream, a labeled example
ONLY IF a resting maker SHORT offer would actually have filled under the adverse-
selection model (mirrors evaluator._replay_adverse, arxiv 2407.16527). A signal whose
price drops away from the offer never fills and is DROPPED — never counted as a free
win. That favorable-but-unfilled case is exactly what the naive 100%-fill replay kept
and inflated (sandbox +0.31/trade vs live -0.14/trade). Real LIVE trades (true PnL,
they genuinely filled) are union'd in with higher weight.

Each example carries the engineered features.compute_features() set at the signal
snapshot, plus realized net (dollars), net_roi (net / margin), and provenance.

ISOLATION: pure stdlib, offline; no bot.py import, no live touch. Economics constants
come from config so fee/notional match the evaluator exactly.
"""
from __future__ import annotations

from . import config as C
from . import features as feat


def _entry_ok(rec: dict, p: dict) -> bool:
    """ST2.0 base entry conditions (the signal universe; sub-conditions come later
    from features + the model). Mirrors evaluator._entry_ok minus candidate filters."""
    return (rec.get("imbalance", 0.0) >= p["imb_min"]
            and rec.get("buy_ratio", 0.0) >= p["br_min"]
            and rec.get("trade_count", 0) >= p["min_trades"])


def _fill_and_exit(recs: list[dict], i: int, p: dict, win: int, edge: float,
                   notional: float, fee: float):
    """Adverse-fill + SL/TP/hold exit for a SINGLE signal at index i.
    Returns (filled: bool, net_dollars: float | None). net is None when unfilled.
    One-to-one with evaluator._replay_adverse's per-signal geometry."""
    offer = recs[i]["price"] * (1 + edge)
    n = len(recs)
    fill_j = None
    for j in range(i + 1, min(i + 1 + win, n)):
        if recs[j]["price"] >= offer:        # an uptick lifts the resting offer -> fill
            fill_j = j
            break
    if fill_j is None:
        return False, None                   # never lifted -> favorable signal correctly missed

    entry = offer
    entry_ts = recs[fill_j]["ts"]
    sl = entry * (1 + p["sl_pct"] / 100.0)   # short stop is ABOVE entry
    tp = entry * (1 - p["tp_pct"] / 100.0)   # short tp is BELOW entry
    exit_price = None
    k = fill_j + 1
    while k < n:
        px = recs[k]["price"]
        if px >= sl:
            exit_price = sl
            break
        if px <= tp:
            exit_price = tp
            break
        if recs[k]["ts"] - entry_ts >= p["hold_secs"]:
            exit_price = px
            break
        k += 1
    if exit_price is None:                    # ran out of data -> close at last seen price
        exit_price = recs[-1]["price"]
    move = (entry - exit_price) / entry       # short: profit when price falls
    return True, move * notional - fee


def _economics(adverse: dict):
    win = max(1, int(adverse.get("fill_window_snaps", 1)))
    edge = float(adverse.get("maker_edge_pct", 0.0)) / 100.0
    notional = C.MARGIN_USDT * C.LEVERAGE
    fee = C.FEE_RT_PCT / 100.0 * notional
    return win, edge, notional, fee


def label_dataset(by_symbol: dict[str, list], params: dict, adverse: dict,
                  real_records: list[dict] = None, real_weight: float = 3.0,
                  feature_lookback: int = 5) -> dict:
    """Return the labeled dataset:
        {
          "examples": [ {<engineered features>, "net", "net_roi", "win",
                         "filled": True, "tradeable": True, "weight", "source"} ],
          "n_signals": int,   # base signals seen (filled + unfilled)
          "n_filled": int,    # signals that filled under the adverse model
          "fill_rate": float, # n_filled / n_signals
          "n_real": int,      # real LIVE trades union'd in
        }
    Unfilled signals are dropped (not in examples). `examples` holds filled sim
    examples (weight 1.0) plus real trades (weight `real_weight`)."""
    p = params
    win, edge, notional, fee = _economics(adverse)

    examples: list[dict] = []
    n_signals = n_filled = 0
    for sym, recs in by_symbol.items():
        if not recs:
            continue
        feated = feat.compute_features(recs, lookback=feature_lookback)
        for i, rec in enumerate(recs):
            if not _entry_ok(rec, p):
                continue
            n_signals += 1
            filled, net = _fill_and_exit(recs, i, p, win, edge, notional, fee)
            if not filled:
                continue                       # DROP — unfilled is never a free win
            n_filled += 1
            ex = dict(feated[i])
            ex.update({
                "net": round(net, 6),
                "net_roi": round(net / C.MARGIN_USDT, 6),
                "win": net > 0,
                "filled": True,
                "tradeable": True,
                "weight": 1.0,
                "source": "sim",
            })
            examples.append(ex)

    n_real = 0
    for r in (real_records or []):
        net = float(r.get("net", 0.0))
        ex = dict(r)
        ex.update({
            "net": round(net, 6),
            "net_roi": round(net / C.MARGIN_USDT, 6),
            "win": net > 0,
            "filled": True,                    # real trades genuinely filled
            "tradeable": True,
            "weight": float(real_weight),
            "source": "real",
        })
        examples.append(ex)
        n_real += 1

    return {
        "examples": examples,
        "n_signals": n_signals,
        "n_filled": n_filled,
        "fill_rate": round(n_filled / n_signals, 6) if n_signals else 0.0,
        "n_real": n_real,
    }


def _sim_fill_rate(by_symbol: dict[str, list], params: dict, adverse: dict) -> float:
    """Fraction of base signals that fill under `adverse` (no exit simulation needed)."""
    p = params
    win, edge, notional, fee = _economics(adverse)
    sig = filled = 0
    for sym, recs in by_symbol.items():
        for i, rec in enumerate(recs):
            if not _entry_ok(rec, p):
                continue
            sig += 1
            f, _ = _fill_and_exit(recs, i, p, win, edge, notional, fee)
            if f:
                filled += 1
    return (filled / sig) if sig else 0.0


# default calibration grid: window depth × maker price-improvement
_DEFAULT_GRID = [{"fill_window_snaps": w, "maker_edge_pct": e}
                 for w in (1, 2, 3) for e in (0.0, 0.02, 0.05, 0.1)]


def calibrate_adverse(by_symbol: dict[str, list], params: dict,
                      target_fill_rate: float, grid: list[dict] = None) -> dict:
    """Pick the ADVERSE_FILL params whose SIMULATED fill rate is closest to the
    MEASURED live target (e.g. ~0.43 from fills.measured_fill_stats). The recorded
    stream cannot tell us queue position, so we calibrate the model to the one number
    real logs do give us. Returns {enabled, fill_window_snaps, maker_edge_pct,
    sim_fill_rate}."""
    grid = grid or _DEFAULT_GRID
    best = None
    for g in grid:
        rate = _sim_fill_rate(by_symbol, params, g)
        dist = abs(rate - target_fill_rate)
        cand = {"enabled": True,
                "fill_window_snaps": int(g["fill_window_snaps"]),
                "maker_edge_pct": float(g["maker_edge_pct"]),
                "sim_fill_rate": round(rate, 6)}
        if best is None or dist < best[0]:
            best = (dist, cand)
    return best[1] if best else {"enabled": True, "fill_window_snaps": 1,
                                 "maker_edge_pct": 0.0, "sim_fill_rate": 0.0}
