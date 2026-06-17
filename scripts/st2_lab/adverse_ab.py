"""A/B the ST2.0 champion (and base signal) under naive 100%-fill vs the
adverse-selection maker-fill model (research: arxiv 2407.16527, "The Negative
Drift of a Limit Order Fill").

The naive sandbox fills every passing signal at the benign snapshot price — an
upper bound. A real maker SHORT only fills when an uptick lifts its offer
(adverse selection); favorable cases where price drops away never fill. This
runner quantifies how much of the sandbox "edge" survives realistic fills.

Run:  cd scripts && python3 -m st2_lab.adverse_ab
Read-only: loads the dataset + champion, prints a table. Touches no state.
"""
from __future__ import annotations

from . import dataset as ds
from .evaluator import evaluate
from .champion import load as load_champ


def run(limit: int | None = None) -> None:
    champ = load_champ()
    data = ds.load_dataset(limit=limit)
    ntot = sum(len(v) for v in data.values())
    loop_cfg = {"min_trades_eval": 15}
    base = dict(champ)
    base["filters"] = []

    print(f"dataset: {ntot} snapshots, {len(data)} symbols")
    print(f"champion filters: {[f['code'] for f in champ['filters']]}")
    print(f"{'mode':30s} {'trades':>7} {'exp':>9} {'WR':>7} {'net':>9} {'kelly':>7}")

    def row(label: str, cfg: dict, adverse: dict | None) -> None:
        m = evaluate(cfg, data, loop_cfg, adverse=adverse)
        print(f"{label:30s} {m.trades:7d} {m.expectancy:+9.4f} "
              f"{m.wr*100:6.1f}% {m.net:+9.2f} {m.kelly:+7.3f}")

    print("-- champion --")
    row("naive (100% fill, UPPER BOUND)", champ, None)
    for w in (1, 2, 3):
        row(f"adverse fill (window={w})", champ, {"enabled": True, "fill_window_snaps": w})
    print("-- base ST2.0 signal (no filters) --")
    row("base naive", base, None)
    row("base adverse (window=1)", base, {"enabled": True, "fill_window_snaps": 1})
    print("\nNote: real measured maker fill rate ~41% (fills.py); window=1 retains more "
          "than that, so live is harsher still. This is a directional stress test on "
          "coarse ~74s snapshots, not a tick-precise forecaster.")


if __name__ == "__main__":
    run()
