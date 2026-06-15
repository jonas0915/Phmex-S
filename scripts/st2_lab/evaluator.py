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


def evaluate(cfg: dict, by_symbol: dict[str, list], loop_cfg: dict = None) -> C.Metrics:
    """Replay cfg over the dataset and return relative-ranking Metrics."""
    loop_cfg = loop_cfg or C.DEFAULTS
    p = cfg["params"]
    try:
        filters = _build_filters(cfg)
    except Rejection:
        return C.Metrics()  # invalid config -> unrankable, score -inf

    sl_frac = p["sl_pct"] / 100.0
    tp_frac = p["tp_pct"] / 100.0
    notional = C.MARGIN_USDT * C.LEVERAGE
    fee = C.FEE_RT_PCT / 100.0 * notional

    nets: list[float] = []
    for sym, recs in by_symbol.items():
        pos = None  # {entry_ts, entry, sl, tp}
        for rec in recs:
            price = rec["price"]
            if pos is None:
                if _entry_ok(rec, p, filters):
                    pos = {
                        "entry_ts": rec["ts"],
                        "entry": price,
                        "sl": price * (1 + sl_frac),   # short: stop above entry
                        "tp": price * (1 - tp_frac),   # short: target below entry
                    }
                continue
            # in a short position: decide exit (SL > TP priority; then time)
            exit_price = None
            if price >= pos["sl"]:
                exit_price = pos["sl"]
            elif price <= pos["tp"]:
                exit_price = pos["tp"]
            elif rec["ts"] - pos["entry_ts"] >= p["hold_secs"]:
                exit_price = price
            if exit_price is not None:
                move = (pos["entry"] - exit_price) / pos["entry"]  # short
                nets.append(move * notional - fee)
                pos = None
        # close any dangling position at the last seen price
        if pos is not None and recs:
            last = recs[-1]["price"]
            move = (pos["entry"] - last) / pos["entry"]
            nets.append(move * notional - fee)

    return _metrics(nets, loop_cfg)


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
