"""Failure diagnostics — find WHERE the absorption signal loses, across all symbols,
and turn each loss-cluster into a targeted, safe entry-filter.

Method (deliberately simple + explainable, not a black box):
  * for each entry-context feature, try cut points (quantiles of the feature among
    real trades); for each cut, consider vetoing the high tail (`feature <= cut`)
    or the low tail (`feature >= cut`);
  * keep a candidate only if the vetoed region is genuinely worse and both sides
    have enough support (guards against fitting noise);
  * score = expectancy of the KEPT trades minus overall expectancy.

These are HYPOTHESES on recorded data — the loop still re-evaluates each filter on
expectancy and only adopts a winner; paper-confirm remains the truth gate (in-sample
improvement can be overfit). The proposer caps how many it emits per iteration.
"""
from __future__ import annotations

from .safe_exec import compile_filter, Rejection

CONT_FEATURES = ["imbalance", "buy_ratio", "cvd_slope", "large_trade_bias",
                 "spread_pct", "trade_count", "hour"]
BOOL_FEATURES = ["divergence_bullish", "divergence_bearish"]
_INT_FEATURES = {"trade_count", "hour"}

MIN_SUPPORT = 20    # kept trades must be >= this (don't fit a tiny remainder)
MIN_VETOED = 10     # must actually exclude something meaningful


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    i = max(0, min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def _round(feature, v):
    return int(round(v)) if feature in _INT_FEATURES else round(v, 3)


def analyze_failures(trades: list[dict]) -> list[dict]:
    """Return candidate vetoes, best-first: {feature, code, kept_exp, improvement,
    kept_n, vetoed_n, vetoed_exp}."""
    if len(trades) < MIN_SUPPORT + MIN_VETOED:
        return []
    overall = _mean([t["net"] for t in trades])
    cands: dict[str, dict] = {}  # feature -> best candidate

    def consider(feature, code, kept, vetoed):
        if len(kept) < MIN_SUPPORT or len(vetoed) < MIN_VETOED:
            return
        kexp = _mean([t["net"] for t in kept])
        vexp = _mean([t["net"] for t in vetoed])
        if vexp >= kexp:           # only veto a region worse than what's kept
            return
        imp = kexp - overall
        if imp <= 0:
            return
        try:
            compile_filter(code)   # must be safe-compilable
        except Rejection:
            return
        cur = cands.get(feature)
        if cur is None or imp > cur["improvement"]:
            cands[feature] = {"feature": feature, "code": code, "kept_exp": round(kexp, 4),
                              "vetoed_exp": round(vexp, 4), "improvement": round(imp, 4),
                              "kept_n": len(kept), "vetoed_n": len(vetoed)}

    for feat in CONT_FEATURES:
        vals = sorted(t[feat] for t in trades)
        for q in (0.25, 0.5, 0.75):
            cut = _round(feat, _quantile(vals, q))
            if cut is None:
                continue
            # veto the HIGH tail: keep feature <= cut
            consider(feat, f"{feat} <= {cut}",
                     [t for t in trades if t[feat] <= cut],
                     [t for t in trades if t[feat] > cut])
            # veto the LOW tail: keep feature >= cut
            consider(feat, f"{feat} >= {cut}",
                     [t for t in trades if t[feat] >= cut],
                     [t for t in trades if t[feat] < cut])

    for feat in BOOL_FEATURES:
        consider(feat, f"not {feat}",
                 [t for t in trades if not t[feat]],
                 [t for t in trades if t[feat]])

    return sorted(cands.values(), key=lambda d: -d["improvement"])


def propose_filter_codes(trades: list[dict], existing_codes: set, max_n: int) -> list[dict]:
    """Top-N diagnostic filters not already present, best improvement first."""
    out = []
    for c in analyze_failures(trades):
        if c["code"] in existing_codes:
            continue
        out.append(c)
        if len(out) >= max_n:
            break
    return out
