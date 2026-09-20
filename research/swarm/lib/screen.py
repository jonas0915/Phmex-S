"""Pre-registered screen runner (spec §5 step 5). Reads a FROZEN spec, refuses tampering,
refuses lookahead (causality check), simulates closed-bar trades with the desk's cost model,
and writes out.json — the only artifact downstream phases are allowed to cite.

Controller ruling (2026-09-16, Task 5 pre-flight): run_screen writes the brief's plain
filenames (out.json, trades.csv) only for era=="train"; any other era (e.g. "holdout")
writes era-suffixed files (out.<era>.json, trades.<era>.csv) in the same screens/<id>/
folder so a later holdout run never clobbers the train-era artifacts that the audit,
committee, and knowledge base cite by path.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import bootstrap_ci as bc
from . import fee_math as fm
from . import load_data as ld
from . import registrar as rg


class LookaheadError(Exception):
    pass


def load_signal_fn(signal_path: Path):
    spec = importlib.util.spec_from_file_location(f"sig_{signal_path.stem}_{abs(hash(str(signal_path)))}", signal_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.signals


def causality_check(signals_fn, df: pd.DataFrame, n_points: int = 12, seed: int = 0,
                     symbol: str | None = None) -> None:
    """Whole-prefix causality check (review fix round 1): a signal may not depend on any
    bar beyond the truncation point. For every truncation index i, signals(df.iloc[:i+1])
    reindexed onto df.index[:i+1] / NaN-filled-0 / cast-int must equal the full-frame
    signal (same reindex/fill/cast) sliced to [:i+1] — the WHOLE prefix, not just index i,
    so a signal that only mutates a handful of far-away bars (e.g. shift(-2) gated to
    hour==0) still gets caught even though index i itself matches.

    Truncation points: every bar where the full signal is nonzero (seeded sample of 40 if
    more than 40 exist), plus 20 uniform indices from [10, len-1) without replacement;
    frames shorter than 60 bars use every index in [10, len-1) instead. `n_points` is
    kept for interface compatibility but is no longer the knob — the point counts above
    are fixed by the controller's fix ruling.

    Reference symbols (2026-09-20): every signals_fn call here runs under
    ld.reference_until(<last bar of the frame it is handed>), so a signal's
    load_reference/load_reference_funding rows are clipped to that prefix's end. Without
    that clip a forward transform confined to the reference series (e.g.
    ref.close.shift(-3)) is identical in every prefix and would pass undetected.
    """
    with ld.reference_until(df.index.max()):
        full = signals_fn(df).reindex(df.index).fillna(0).astype(int)
    n = len(df)
    rng = np.random.default_rng(seed)
    if n < 60:
        idxs = list(range(10, max(10, n - 1)))
    else:
        nonzero_idx = np.flatnonzero(full.to_numpy() != 0)
        if len(nonzero_idx) > 40:
            nonzero_idx = rng.choice(nonzero_idx, 40, replace=False)
        uniform_range = np.arange(10, n - 1)
        uniform_idx = rng.choice(uniform_range, size=min(20, len(uniform_range)), replace=False)
        idxs = sorted(set(int(x) for x in nonzero_idx) | set(int(x) for x in uniform_idx))
    for i in idxs:
        with ld.reference_until(df.index[i]):
            trunc = signals_fn(df.iloc[: i + 1]).reindex(df.index[: i + 1]).fillna(0).astype(int)
        ref = full.iloc[: i + 1]
        if not trunc.equals(ref):
            mism = (trunc != ref).to_numpy().nonzero()[0]
            bad_ts = trunc.index[mism[0]]
            who = f"{symbol} " if symbol else ""
            raise LookaheadError(
                f"signal {who}at {bad_ts} (truncation index {i}) changes when future bars are removed")


def simulate(df: pd.DataFrame, sig: pd.Series, tp_bps: float, sl_bps: float, max_hold_bars: int,
             cost_bps: float = fm.C_BPS) -> pd.DataFrame:
    """Closed-bar simulator (frozen tie rules): signal on closed bar i enters at
    open[i+1]; each later bar checks SL then TP against low/high (SL wins ties,
    conservative); max_hold_bars exits at that bar's close. The position is flat at the
    exit bar's close, so a signal on the exit bar enters at the next open — one position
    per symbol at a time, but no dead zone on the exit bar itself."""
    o, h, l, c = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    s = sig.reindex(df.index).fillna(0).astype(int).to_numpy()
    rows, i, n = [], 0, len(df)
    while i < n - 1:
        side = int(s[i])
        if side == 0:
            i += 1; continue
        entry_i, entry = i + 1, o[i + 1]
        tp = entry * (1 + side * tp_bps / 1e4)
        sl = entry * (1 - side * sl_bps / 1e4)
        exit_i, exit_px, reason = None, None, None
        last = min(entry_i + max_hold_bars, n - 1)
        for j in range(entry_i, last + 1):
            hit_sl = l[j] <= sl if side == 1 else h[j] >= sl
            hit_tp = h[j] >= tp if side == 1 else l[j] <= tp
            if hit_sl:                       # SL first on ties — conservative
                exit_i, exit_px, reason = j, sl, "SL"; break
            if hit_tp:
                exit_i, exit_px, reason = j, tp, "TP"; break
            if j == last:
                exit_i, exit_px, reason = j, c[j], "TIME"
        if exit_i is None:
            break
        gross = side * (exit_px / entry - 1) * 1e4
        rows.append({"entry_ts": df.index[entry_i], "exit_ts": df.index[exit_i], "side": side, "entry": float(entry),
                     "exit": float(exit_px), "gross_bps": float(gross), "net_bps": float(gross - cost_bps), "exit_reason": reason})
        i = exit_i                            # flat at exit bar's close; its own signal can still open the next trade
    return pd.DataFrame(rows, columns=["entry_ts", "exit_ts", "side", "entry", "exit", "gross_bps", "net_bps", "exit_reason"])


def run_screen(frozen_path: Path, run_dir: Path, era: str = "train", token: str | None = None) -> dict:
    frozen_path, run_dir = Path(frozen_path), Path(run_dir)
    if not rg.verify(frozen_path):
        raise ValueError(f"frozen spec failed sha verification: {frozen_path}")
    frozen = json.loads(frozen_path.read_text())
    th, spec = frozen["thesis"], frozen["thesis"]["spec"]
    sdir = run_dir / "screens" / th["id"]
    signal_path = sdir / "signal.py"
    if signal_path.read_text() != th["signal_py"]:
        raise ValueError("signal.py differs from frozen signal_py")
    signals_fn = load_signal_fn(signal_path)

    frames, sigs, all_trades, per_symbol = {}, {}, [], {}
    # Every signals_fn call (the full-frame call and the causality check's prefix reruns)
    # runs inside the screen-era context, so a signal that loads a REFERENCE symbol via
    # ld.load_reference / ld.load_reference_funding gets the same era (and token) as the
    # frame it was handed — never a hard-coded train frame that empties the holdout
    # intersection (LESSONS 2026-09-19). The context is restored when the block exits.
    with ld.screen_context(era, token):
        for sym in spec["universe"]:
            df = ld.load_ohlcv(sym, spec["timeframe"], era=era, dataset=spec["dataset"], token=token)
            frames[sym] = df
            with ld.reference_until(df.index.max()):   # full frame: reference clipped to its last bar
                sig = signals_fn(df).reindex(df.index).fillna(0).astype(int)
            bad = sig[~sig.isin((-1, 0, 1))]
            if not bad.empty:
                raise ValueError("signal values must be in {-1,0,1}")
            sigs[sym] = sig
        # causality is checked for EVERY symbol, before any simulate() call, so a lookahead
        # signal is refused no matter which symbol in the universe carries it.
        for sym, df in frames.items():
            causality_check(signals_fn, df, symbol=sym)
    for sym, df in frames.items():
        tr = simulate(df, sigs[sym], spec["tp_bps"], spec["sl_bps"], spec["max_hold_bars"])
        tr.insert(0, "symbol", sym)
        per_symbol[sym] = int(len(tr))
        all_trades.append(tr)
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    n = int(len(trades))
    span_start = min(df.index.min() for df in frames.values()); span_end = max(df.index.max() for df in frames.values())
    weeks = max((span_end - span_start).total_seconds() / (7 * 86400), 1e-9)
    notional = fm.position_notional()
    out = {
        "id": th["id"], "spec_sha256": frozen["sha256"], "era": era, "n": n,
        "net_bps_mean": float(trades["net_bps"].mean()) if n else None,
        "ci95": list(bc.mean_ci(trades["net_bps"].to_numpy())) if n >= 2 else None,
        "wr": float((trades["net_bps"] > 0).mean()) if n else None,
        "p_star": fm.p_star(spec["tp_bps"]),
        "trades_per_week": n / weeks,
        # n==0 -> fee_math.time_to_verdict_weeks returns math.inf, which json.dumps would
        # emit as the non-strict-JSON token `Infinity`; null keeps out.json strict JSON.
        "time_to_verdict_weeks": None if n == 0 else fm.time_to_verdict_weeks(n / weeks),
        "lot_check": {sym: fm.lot_check(sym, notional) for sym in spec["universe"]},
        "per_symbol": per_symbol,
        "train_span": [str(span_start), str(span_end)],
        "causality": "PASS",
        "signal_sha256": hashlib.sha256(th["signal_py"].encode()).hexdigest(),
    }
    sdir.mkdir(parents=True, exist_ok=True)
    # Controller ruling: only era=="train" gets the plain filenames the audit/committee/kb
    # cite by path; any other era is written era-suffixed so it never clobbers train.
    json_name = "out.json" if era == "train" else f"out.{era}.json"
    csv_name = "trades.csv" if era == "train" else f"trades.{era}.csv"
    trades.to_csv(sdir / csv_name, index=False)
    (sdir / json_name).write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("frozen"); ap.add_argument("run_dir"); ap.add_argument("--era", default="train"); ap.add_argument("--token", default=None)
    a = ap.parse_args()
    print(json.dumps(run_screen(Path(a.frozen), Path(a.run_dir), a.era, a.token), indent=2, default=str))
