"""Sandbox evaluator — replay a config over recorded data for RELATIVE ranking.

Simulates ST2.0 exactly as live: short when (imbalance >= imb_min AND
buy_ratio >= br_min AND trade_count >= min_trades) and every entry-filter
passes; one position per symbol; fixed-% SL/TP; ~15-min maker hold. Produces
relative metrics (net, WR, Kelly). NOT an absolute-PnL forecaster — the
recorded stream + crude fills mean this ranks A-vs-B only (see spec).

Entry-filter semantics: each filter returns True to ALLOW the trade. If any
filter returns False, entry is vetoed.
"""
from __future__ import annotations

from . import config as C
from .safe_exec import compile_filter, Rejection


def _build_filters(cfg: dict):
    """Compile a config's filter list. Raises Rejection if any is unsafe/malformed."""
    fns = []
    for f in cfg.get("filters", []) or []:
        code = f.get("code") if isinstance(f, dict) else f
        fns.append(compile_filter(code))
    return fns


def _entry_ok(rec: dict, p: dict, filters) -> bool:
    if rec["imbalance"] < p["imb_min"]:
        return False
    if rec["buy_ratio"] < p["br_min"]:
        return False
    if rec["trade_count"] < p["min_trades"]:
        return False
    for fn in filters:
        if not fn(rec):
            return False
    return True


# entry-context features recorded per trade (for failure diagnostics)
_FEATURES = ("imbalance", "buy_ratio", "trade_count", "cvd_slope",
             "large_trade_bias", "spread_pct", "divergence_bullish",
             "divergence_bearish", "hour")


def _replay(cfg: dict, by_symbol: dict[str, list]) -> list[dict]:
    """Replay cfg and return per-trade records: {<entry features>, net}.
    Raises Rejection if a filter is unsafe."""
    p = cfg["params"]
    filters = _build_filters(cfg)
    sl_frac = p["sl_pct"] / 100.0
    tp_frac = p["tp_pct"] / 100.0
    notional = C.MARGIN_USDT * C.LEVERAGE
    fee = C.FEE_RT_PCT / 100.0 * notional

    syms = cfg.get("symbols")
    items = (by_symbol.items() if not syms
             else [(s, by_symbol[s]) for s in syms if s in by_symbol])

    trades: list[dict] = []
    for sym, recs in items:
        pos = None
        for rec in recs:
            price = rec["price"]
            if pos is None:
                if _entry_ok(rec, p, filters):
                    pos = {"entry_ts": rec["ts"], "entry": price,
                           "sl": price * (1 + sl_frac), "tp": price * (1 - tp_frac),
                           "feat": {k: rec.get(k, 0) for k in _FEATURES}}
                continue
            exit_price = None
            if price >= pos["sl"]:
                exit_price = pos["sl"]
            elif price <= pos["tp"]:
                exit_price = pos["tp"]
            elif rec["ts"] - pos["entry_ts"] >= p["hold_secs"]:
                exit_price = price
            if exit_price is not None:
                move = (pos["entry"] - exit_price) / pos["entry"]
                trades.append({**pos["feat"], "net": move * notional - fee})
                pos = None
        if pos is not None and recs:
            move = (pos["entry"] - recs[-1]["price"]) / pos["entry"]
            trades.append({**pos["feat"], "net": move * notional - fee})
    return trades


def _replay_adverse(cfg: dict, by_symbol: dict[str, list], af: dict) -> list[dict]:
    """Replay with an adverse-selection maker-fill model (research: arxiv 2407.16527).

    A short posts a sell at offer = signal_price * (1 + maker_edge). It fills ONLY if
    an uptick lifts the offer within `fill_window_snaps` forward snapshots (adverse
    selection). If price drops away from the offer for the whole window, the resting
    order never fills and the signal is DROPPED — that is the favorable case the naive
    100%-fill model wrongly keeps. Filled positions then evolve through SL/TP/hold from
    the (higher) offer price. Coarse data (~74s) => directional stress test, not a
    tick-precise forecaster."""
    p = cfg["params"]
    filters = _build_filters(cfg)
    sl_frac = p["sl_pct"] / 100.0
    tp_frac = p["tp_pct"] / 100.0
    notional = C.MARGIN_USDT * C.LEVERAGE
    fee = C.FEE_RT_PCT / 100.0 * notional
    win = max(1, int(af.get("fill_window_snaps", 1)))
    edge = af.get("maker_edge_pct", 0.0) / 100.0

    syms = cfg.get("symbols")
    items = (by_symbol.items() if not syms
             else [(s, by_symbol[s]) for s in syms if s in by_symbol])

    trades: list[dict] = []
    for sym, recs in items:
        n = len(recs)
        i = 0
        while i < n:
            rec = recs[i]
            if not _entry_ok(rec, p, filters):
                i += 1
                continue
            offer = rec["price"] * (1 + edge)
            # First forward snapshot (within window) whose price lifts the offer = fill.
            fill_j = None
            for j in range(i + 1, min(i + 1 + win, n)):
                if recs[j]["price"] >= offer:
                    fill_j = j
                    break
            if fill_j is None:
                i += 1          # never lifted -> no fill -> favorable signal correctly missed
                continue
            entry = offer
            entry_ts = recs[fill_j]["ts"]
            sl = entry * (1 + sl_frac)
            tp = entry * (1 - tp_frac)
            feat = {k: rec.get(k, 0) for k in _FEATURES}
            exit_price, k = None, fill_j + 1
            while k < n:
                px = recs[k]["price"]
                if px >= sl:
                    exit_price = sl; break
                if px <= tp:
                    exit_price = tp; break
                if recs[k]["ts"] - entry_ts >= p["hold_secs"]:
                    exit_price = px; break
                k += 1
            if exit_price is None:          # ran out of data -> close at last seen price
                exit_price = recs[-1]["price"]
                k = n - 1
            move = (entry - exit_price) / entry
            trades.append({**feat, "net": move * notional - fee})
            i = k + 1                       # one position per symbol; resume after close
    return trades


def evaluate(cfg: dict, by_symbol: dict[str, list], loop_cfg: dict = None,
             adverse: dict = None) -> C.Metrics:
    """Replay cfg over the dataset and return relative-ranking Metrics.
    adverse: pass an ADVERSE_FILL-shaped dict with enabled=True to use the
    adverse-selection maker-fill model instead of the naive 100%-fill replay."""
    loop_cfg = loop_cfg or C.DEFAULTS
    try:
        if adverse and adverse.get("enabled"):
            trades = _replay_adverse(cfg, by_symbol, adverse)
        else:
            trades = _replay(cfg, by_symbol)
    except Rejection:
        return C.Metrics()  # invalid config -> unrankable, score -inf
    return _metrics([t["net"] for t in trades], loop_cfg)


def evaluate_with_trades(cfg: dict, by_symbol: dict[str, list], loop_cfg: dict = None,
                         adverse: dict = None):
    """Like evaluate() but also returns the per-trade records (for diagnostics)."""
    loop_cfg = loop_cfg or C.DEFAULTS
    try:
        if adverse and adverse.get("enabled"):
            trades = _replay_adverse(cfg, by_symbol, adverse)
        else:
            trades = _replay(cfg, by_symbol)
    except Rejection:
        return C.Metrics(), []
    return _metrics([t["net"] for t in trades], loop_cfg), trades


def _metrics(nets: list[float], loop_cfg: dict) -> C.Metrics:
    n = len(nets)
    m = C.Metrics(trades=n)
    if n == 0:
        return m
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    m.wins, m.losses = len(wins), len(losses)
    m.net = round(sum(nets), 4)
    m.expectancy = round(sum(nets) / n, 4)
    m.wr = round(len(wins) / n, 4)
    m.avg_win = round(sum(wins) / len(wins), 4) if wins else 0.0
    m.avg_loss = round(sum(losses) / len(losses), 4) if losses else 0.0
    if wins and losses:
        rr = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
        m.kelly = round(m.wr - (1 - m.wr) / rr, 4) if rr > 0 else -1.0
    elif not wins:
        m.kelly = -1.0
    else:
        m.kelly = 1.0
    m.rankable = n >= loop_cfg.get("min_trades_eval", C.DEFAULTS["min_trades_eval"])
    return m
