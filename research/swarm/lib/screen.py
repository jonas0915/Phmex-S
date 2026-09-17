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


def causality_check(signals_fn, df: pd.DataFrame, n_points: int = 12, seed: int = 0) -> None:
    """signals(df)[i] must equal signals(df[:i+1])[i] — a signal may not depend on later bars."""
    full = signals_fn(df).fillna(0).astype(int)
    rng = np.random.default_rng(seed)
    pts = rng.integers(max(50, len(df) // 10), len(df) - 1, size=n_points)
    for i in pts:
        trunc = signals_fn(df.iloc[: i + 1]).fillna(0).astype(int)
        if int(trunc.iloc[-1]) != int(full.iloc[i]):
            raise LookaheadError(f"signal at {df.index[i]} changes when future bars are removed")


def simulate(df: pd.DataFrame, sig: pd.Series, tp_bps: float, sl_bps: float, max_hold_bars: int,
             cost_bps: float = fm.C_BPS) -> pd.DataFrame:
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
        i = exit_i + 1                        # one position per symbol at a time
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

    frames, all_trades, per_symbol = {}, [], {}
    for sym in spec["universe"]:
        df = ld.load_ohlcv(sym, spec["timeframe"], era=era, dataset=spec["dataset"], token=token)
        frames[sym] = df
    first_sym = spec["universe"][0]
    causality_check(signals_fn, frames[first_sym])
    for sym, df in frames.items():
        sig = signals_fn(df).fillna(0).astype(int)
        tr = simulate(df, sig, spec["tp_bps"], spec["sl_bps"], spec["max_hold_bars"])
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
        "time_to_verdict_weeks": fm.time_to_verdict_weeks(n / weeks),
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
