"""Post-fill adverse-drift diagnostic for ST2.0 (research: arxiv 2407.16527,
"The Negative Drift of a Limit Order Fill").

A passive maker SHORT fills when price ticks UP through its resting offer — adverse
by construction. This MEASURES that on our own money: for each real ST2.0 live fill,
find the L2 mid `DRIFT_HORIZON_S` seconds after the fill and compute
    drift = mark_horizon - fill_price.
For a short, POSITIVE drift = adverse (price rose after we sold). If the mean is
consistently positive, the negative-drift thesis is confirmed on Phemex data; if it
is NOT adverse on our data, that is a meaningful positive signal about fill quality.

This turns "execution is adversely selected" from a literature belief into a measured
internal number (see reference_st2_execution_research / 2026-06-22 nightly Tweak B).

DATA: fine-grained L2 ticks live at logs/l2_ticks/<SYM>/<UTC-date>.jsonl[.gz] at
millisecond resolution — but ONLY for the recorded symbols (BTC/ETH/INJ/ARB). Trades
on other symbols have no sub-minute price path and are reported as UNCOVERED, never
guessed (the coarse ~87s flow_capture cadence cannot support a 30s mark). OFFLINE
ONLY — reads state files + recorded ticks; never imports bot.py, never trades.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
from datetime import datetime, timezone

from . import config as C

ST2_STATE = os.path.join(C.BOT_DIR, "trading_state_ST2.0.json")
L2_DIR = os.path.join(C.BOT_DIR, "logs", "l2_ticks")

DRIFT_HORIZON_S = 30      # post-fill mark horizon (seconds)
_MATCH_TOL_S = 120        # max gap between target time and nearest tick; else uncovered


def _l2_symbol_dir(symbol: str) -> str:
    """'ETH/USDT:USDT' -> 'ETH_USDT_USDT' (the l2_ticks subdir naming)."""
    return symbol.replace("/", "_").replace(":", "_")


def _utc_date(ts_s: float) -> str:
    return datetime.fromtimestamp(ts_s, tz=timezone.utc).strftime("%Y-%m-%d")


def _open_day(sym_dir: str, date: str):
    """Open a daily L2 file (plain .jsonl for today, .jsonl.gz once rotated), or None."""
    base = os.path.join(L2_DIR, sym_dir, date)
    if os.path.exists(base + ".jsonl"):
        return open(base + ".jsonl", "rt", errors="ignore")
    if os.path.exists(base + ".jsonl.gz"):
        return gzip.open(base + ".jsonl.gz", "rt", errors="ignore")
    return None


def _fast_ts_ms(line: str) -> int | None:
    """Pull the leading {"ts": <ms>, ...} without full JSON parse (700k lines/day)."""
    try:
        return int(line.split(",", 1)[0].split(":", 1)[1])
    except (IndexError, ValueError):
        return None


def _mid_from_line(line: str) -> float | None:
    try:
        d = json.loads(line)
        b, a = d.get("b"), d.get("a")
        if b and a:
            return (float(b[0][0]) + float(a[0][0])) / 2.0
    except (json.JSONDecodeError, IndexError, TypeError, ValueError):
        pass
    return None


def l2_mid_at(symbol: str, target_s: float, tol_s: int = _MATCH_TOL_S) -> tuple | None:
    """First L2 mid at or after target_s for `symbol`. Daily files are UTC-dated and
    ts-ascending; we scan the target's UTC day, then spill into the next day if the
    target lands near a day boundary. Returns (mid, actual_offset_s) or None if no
    tick exists within tol_s of the target (or the symbol isn't L2-recorded)."""
    sym_dir = _l2_symbol_dir(symbol)
    if not os.path.isdir(os.path.join(L2_DIR, sym_dir)):
        return None
    target_ms = target_s * 1000.0
    # candidate UTC days, de-duped, in order: the target day and the following day
    days = []
    for s in (target_s, target_s + tol_s + 1):
        d = _utc_date(s)
        if d not in days:
            days.append(d)
    for date in days:
        fh = _open_day(sym_dir, date)
        if fh is None:
            continue
        with fh:
            for line in fh:
                ts_ms = _fast_ts_ms(line)
                if ts_ms is None or ts_ms < target_ms:
                    continue
                offset = (ts_ms / 1000.0) - target_s
                if offset > tol_s:
                    return None            # nearest tick too far away -> uncovered
                mid = _mid_from_line(line)
                return (mid, offset) if mid is not None else None
    return None


def _live_short_trades(state_file: str = None) -> list[dict]:
    state_file = state_file or ST2_STATE
    if not os.path.exists(state_file):
        return []
    try:
        ct = json.load(open(state_file)).get("closed_trades", [])
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for t in ct:
        if t.get("mode") != "live":
            continue
        ep, oa = t.get("entry_price"), t.get("opened_at")
        if ep and oa:
            out.append(t)
    return out


def load_drifts(state_file: str = None, horizon_s: int = DRIFT_HORIZON_S) -> list[dict]:
    """One drift record per real ST2.0 live trade. `covered` rows carry a measured
    post-fill mark; uncovered rows (no L2 for that symbol/time) are kept for honest
    accounting but excluded from the drift stats."""
    out = []
    for t in _live_short_trades(state_file):
        sym, side = t["symbol"], t.get("side", "short")
        fill, oa = float(t["entry_price"]), float(t["opened_at"])
        net = t.get("net_pnl")
        net = float(net) if net is not None else float(t.get("pnl_usdt", 0) or 0)
        rec = {"symbol": sym, "side": side, "fill": fill, "net": net,
               "covered": False, "drift_bps": None, "mark": None,
               "offset_s": None, "fill_mark_bps": None}
        hit = l2_mid_at(sym, oa + horizon_s)
        if hit is not None:
            mark, offset = hit
            sign = 1.0 if side == "short" else -1.0   # short: price up = adverse (+)
            rec["covered"] = True
            rec["mark"] = mark
            rec["offset_s"] = round(offset, 2)
            rec["drift_bps"] = round(sign * (mark - fill) / fill * 1e4, 3)
            # join sanity: L2 mid AT fill time vs the recorded fill price
            fhit = l2_mid_at(sym, oa)
            if fhit is not None:
                rec["fill_mark_bps"] = round(abs(fhit[0] - fill) / fill * 1e4, 2)
        out.append(rec)
    return out


def drift_summary(drifts: list[dict], horizon_s: int = DRIFT_HORIZON_S) -> dict:
    cov = [d for d in drifts if d["covered"]]
    n_total, n_cov = len(drifts), len(cov)
    base = {"trades": n_total, "covered": n_cov, "uncovered": n_total - n_cov,
            "horizon_s": horizon_s}
    if not cov:
        return {**base, "mean_drift_bps": None}
    bps = [d["drift_bps"] for d in cov]
    adverse = [d for d in cov if d["drift_bps"] > 0]
    win_bps = [d["drift_bps"] for d in cov if d["net"] > 0]
    loss_bps = [d["drift_bps"] for d in cov if d["net"] < 0]
    sane = [d["fill_mark_bps"] for d in cov if d["fill_mark_bps"] is not None]
    return {
        **base,
        "mean_drift_bps": round(statistics.mean(bps), 3),
        "median_drift_bps": round(statistics.median(bps), 3),
        "pct_adverse": round(len(adverse) / n_cov * 100, 1),
        "mean_drift_winners_bps": round(statistics.mean(win_bps), 3) if win_bps else None,
        "mean_drift_losers_bps": round(statistics.mean(loss_bps), 3) if loss_bps else None,
        "n_winners": len(win_bps),
        "n_losers": len(loss_bps),
        "join_sanity_bps": round(statistics.mean(sane), 2) if sane else None,
    }


def format_report(summary: dict) -> str:
    if summary["covered"] == 0:
        return (f"post-fill drift: 0/{summary['trades']} trades have L2 coverage "
                f"(only BTC/ETH/INJ/ARB are tick-recorded)")
    s = summary
    sign = "ADVERSE" if s["mean_drift_bps"] > 0 else "favorable"
    parts = [
        f"post-fill {s['horizon_s']}s drift: mean {s['mean_drift_bps']:+.2f} bps "
        f"({sign}), median {s['median_drift_bps']:+.2f}, {s['pct_adverse']:.0f}% adverse "
        f"[{s['covered']}/{s['trades']} L2-covered]"
    ]
    if s["mean_drift_losers_bps"] is not None or s["mean_drift_winners_bps"] is not None:
        w = f"{s['mean_drift_winners_bps']:+.2f}" if s["mean_drift_winners_bps"] is not None else "n/a"
        l = f"{s['mean_drift_losers_bps']:+.2f}" if s["mean_drift_losers_bps"] is not None else "n/a"
        parts.append(f"  winners {w} bps (n={s['n_winners']}) vs losers {l} bps (n={s['n_losers']})")
    if s["join_sanity_bps"] is not None:
        parts.append(f"  join sanity (|L2 mid@fill − recorded fill|): {s['join_sanity_bps']:.1f} bps")
    return "\n".join(parts)


if __name__ == "__main__":   # python -m scripts.st2_lab.drift
    drifts = load_drifts()
    print(format_report(drift_summary(drifts)))
    print("\nper-trade:")
    for d in drifts:
        if d["covered"]:
            print(f"  {d['symbol'].split('/')[0]:8s} {d['side']:5s} fill={d['fill']:<12g} "
                  f"drift={d['drift_bps']:+7.2f}bps (mark@+{d['offset_s']:.1f}s) net={d['net']:+.3f}")
        else:
            print(f"  {d['symbol'].split('/')[0]:8s} {d['side']:5s} fill={d['fill']:<12g} "
                  f"UNCOVERED (no L2)            net={d['net']:+.3f}")
