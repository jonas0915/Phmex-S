"""Fill-rate analysis from REAL logs — the ground truth the sandbox cannot invent.

ST2.0 is maker-only; whether a passive order fills depends on queue position and
who is ahead of us in the book, which NO recorded dataset captures. So fill rate
can only be MEASURED from real fill/miss events, never simulated to truth. This
module parses the live [SLOT LIVE] ST2.0 ENTRY / "no fill (PostOnly miss)" lines
(the bot double-writes each log line — we dedupe) and reports the real fill rate,
overall and by symbol, plus the conditions present on real fills.
"""
from __future__ import annotations

import os
import re

from . import config as C

_BOT_LOG = os.path.join(C.BOT_DIR, "logs", "bot.log")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_FILL = re.compile(
    r"\[SLOT LIVE\] ST2\.0 ENTRY SHORT (\S+) \| Fill: ([\d.]+).*?"
    r"imb=([-\d.]+) br=([\d.]+) tc=(\d+)"
)
# Miss lines now carry the same imb/br/tc signal conditions as fills (the
# instrumentation gap the 2026-06-20 execution analysis was blocked by). The
# imb/br/tc group is OPTIONAL — older miss lines (pre-richer-reason) lack it and
# still match on symbol alone (groups 2-4 = None).
_MISS = re.compile(
    r"\[SLOT LIVE\] ST2\.0 (\S+) short .*?no fill \(PostOnly miss\)"
    r"(?:.*?imb=([-\d.]+) br=([\d.]+) tc=(\d+))?"
)


def measured_fill_stats(log_path: str = None) -> dict:
    """Parse real ST2.0 maker fills vs PostOnly misses. Returns measured ground truth."""
    log_path = log_path or _BOT_LOG
    fills, misses = [], []
    miss_conds = []   # imb/br/tc present at PostOnly misses (mirrors fill_conditions)
    by_symbol: dict[str, dict] = {}
    prev = None
    if not os.path.exists(log_path):
        return {"fills": 0, "misses": 0, "attempts": 0, "rate": 0.0,
                "by_symbol": {}, "fill_conditions": [], "miss_conditions": [],
                "source": log_path}
    with open(log_path, errors="ignore") as f:
        for raw in f:
            line = _ANSI.sub("", raw).rstrip("\n")
            if line == prev:
                continue  # collapse the bot's duplicate (color + plain) writes
            prev = line
            m = _FILL.search(line)
            if m:
                sym = m.group(1)
                fills.append(sym)
                by_symbol.setdefault(sym, {"fills": 0, "misses": 0})["fills"] += 1
                continue
            m = _MISS.search(line)
            if m:
                sym = m.group(1)
                misses.append(sym)
                by_symbol.setdefault(sym, {"fills": 0, "misses": 0})["misses"] += 1
                if m.group(2) is not None:   # richer miss line with signal conditions
                    miss_conds.append({"symbol": sym, "imb": float(m.group(2)),
                                       "br": float(m.group(3)), "tc": int(m.group(4))})
    # capture conditions on fills (a second pass keeps the loop simple)
    conds = []
    prev = None
    with open(log_path, errors="ignore") as f:
        for raw in f:
            line = _ANSI.sub("", raw).rstrip("\n")
            if line == prev:
                continue
            prev = line
            m = _FILL.search(line)
            if m:
                conds.append({"symbol": m.group(1), "imb": float(m.group(3)),
                              "br": float(m.group(4)), "tc": int(m.group(5))})
    nf, nm = len(fills), len(misses)
    attempts = nf + nm
    return {
        "fills": nf,
        "misses": nm,
        "attempts": attempts,
        "rate": round(nf / attempts, 4) if attempts else 0.0,
        "by_symbol": by_symbol,
        "fill_conditions": conds,
        "miss_conditions": miss_conds,
        "source": log_path,
    }


def _mean(xs: list) -> float | None:
    return sum(xs) / len(xs) if xs else None


def fill_vs_miss(stats: dict) -> dict:
    """Compare mean entry conditions on FILLS vs MISSES. The adverse-selection
    question: do fills cluster at different imb/br/tc than misses? (e.g. do we only
    fill when buying is heavier — the adverse moment?). Returns {} until both sides
    have richer-line samples."""
    fc, mc = stats.get("fill_conditions", []), stats.get("miss_conditions", [])
    if not fc or not mc:
        return {}
    out = {}
    for k in ("imb", "br", "tc"):
        fv, mv = _mean([c[k] for c in fc]), _mean([c[k] for c in mc])
        out[k] = {"fill": fv, "miss": mv, "delta": (fv - mv) if (fv is not None and mv is not None) else None}
    out["n_fill"], out["n_miss"] = len(fc), len(mc)
    return out


def format_report(stats: dict) -> str:
    if stats["attempts"] == 0:
        return "fill-rate: no real ST2.0 maker attempts logged yet"
    lines = [
        f"REAL maker fill rate: {stats['rate']*100:.0f}% "
        f"({stats['fills']} fill / {stats['misses']} miss / {stats['attempts']} attempts)"
    ]
    for sym, d in sorted(stats["by_symbol"].items(), key=lambda kv: -(kv[1]["fills"] + kv[1]["misses"])):
        tot = d["fills"] + d["misses"]
        if tot:
            lines.append(f"  {sym.split('/')[0]}: {d['fills']}/{tot} "
                         f"({d['fills']/tot*100:.0f}%)")
    fvm = fill_vs_miss(stats)
    if fvm:
        lines.append(
            f"  cond fill-vs-miss (n={fvm['n_fill']}f/{fvm['n_miss']}m): "
            f"imb {fvm['imb']['fill']:.2f}/{fvm['imb']['miss']:.2f} "
            f"br {fvm['br']['fill']:.2f}/{fvm['br']['miss']:.2f} "
            f"tc {fvm['tc']['fill']:.0f}/{fvm['tc']['miss']:.0f}")
    return "\n".join(lines)
