"""SR_BOUNCE higher-timeframe re-scan runner (2026-07-29 pre-registration:
docs/superpowers/specs/2026-07-29-sr-bounce-htf-rescan-prereg.md).

Runs the 3 frozen configs (A: 4h zone/15m entry, B: 4h zone/1h entry,
C: 1d zone/1h entry) against ~400 days of the same 10-pair universe used by
the original sr-bounce-scan, using the generalized htf_engine.replay().

Selection rule (frozen, from the prereg -- do not alter):
  - TRAIN = first ~70% by calendar time, HOLDOUT = last ~30%.
  - Config ELIGIBLE iff train net/trade > $0 (fee+funding-inclusive) AND
    pooled train frequency >= 1.5 trades/day AND train n >= 150.
  - If >=1 config eligible: the SINGLE best (by train net/trade) gets ONE
    holdout run. Others' holdouts are never read.
  - If none eligible: DO-NOT-BUILD at higher TF, no holdout reads at all.

Usage:
    python3 run_htf_scan.py fetch     # cache all candle data needed
    python3 run_htf_scan.py A|B|C     # run one config, cache its trades
    python3 run_htf_scan.py report    # write the report from cached trades
    python3 run_htf_scan.py all       # fetch + all 3 configs + report
"""
import datetime
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sr-bounce-scan"))

from fetch_data import scan_pairs, load_candles  # noqa: E402 (reused as-is)
from htf_engine import replay  # noqa: E402

DATA_DIR = os.path.join(HERE, "data")
CACHE_DIR = os.path.join(HERE, "htf_scan_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

BOT_DIR = os.path.expanduser("~/Desktop/Phmex-S")

DAYS = 400
FEE_RT = 0.0012
NOTIONAL = 50.0
HOLDOUT_FRACTION = 0.30

MIN_TRAIN_NET_PER_TRADE = 0.0     # strictly > 0
MIN_TRAIN_FREQ_PER_DAY = 1.5
MIN_TRAIN_TRADES = 150

CONFIGS = {
    "A": {"zone_tf": "4h", "entry_tf": "15m", "zone_tf_ms": 4 * 3_600_000,
          "desc": "4h zone / 15m entry"},
    "B": {"zone_tf": "4h", "entry_tf": "1h", "zone_tf_ms": 4 * 3_600_000,
          "desc": "4h zone / 1h entry"},
    "C": {"zone_tf": "1d", "entry_tf": "1h", "zone_tf_ms": 24 * 3_600_000,
          "desc": "1d zone / 1h entry"},
}


def save_json(name: str, obj):
    with open(os.path.join(CACHE_DIR, name), "w") as f:
        json.dump(obj, f)


def load_json(name: str):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_all():
    """Fetch/cache every (pair, timeframe) combo needed across the 3 configs.
    4h serves both A and B; 1h serves B and C; each pair/timeframe fetched
    once regardless of how many configs need it (fetch_data.py's cache is
    keyed by symbol+timeframe, so this is naturally deduplicated)."""
    pairs = scan_pairs()
    needed_tfs = sorted({cfg["zone_tf"] for cfg in CONFIGS.values()} |
                         {cfg["entry_tf"] for cfg in CONFIGS.values()})
    print(f"Fetching {len(pairs)} pairs x {needed_tfs} @ {DAYS}d each "
          f"(cache-first, data_dir={DATA_DIR})...", flush=True)
    for tf in needed_tfs:
        for sym in pairs:
            t0 = time.time()
            df = load_candles(sym, tf, days=DAYS, data_dir=DATA_DIR)
            print(f"  {sym} {tf}: {len(df)} bars ({time.time() - t0:.1f}s)", flush=True)


# ---------------------------------------------------------------------------
# Replay (per-pair parallelized, per lever_lab.py's pattern)
# ---------------------------------------------------------------------------

def _run_one(args):
    sym, zone_tf, entry_tf, zone_tf_ms = args
    df_zone = load_candles(sym, zone_tf, days=DAYS, data_dir=DATA_DIR)
    df_entry = load_candles(sym, entry_tf, days=DAYS, data_dir=DATA_DIR)
    if df_zone.empty or df_entry.empty:
        return sym, []
    t0 = time.time()
    trades = replay(df_zone, df_entry, sym, notional=NOTIONAL, fee_rt=FEE_RT,
                     zone_tf_ms=zone_tf_ms)
    return sym, trades


def run_config(label: str, workers: int) -> list[dict]:
    cached = load_json(f"{label}_trades.json")
    if cached is not None:
        print(f"[{label}] using cached {len(cached)} trades", flush=True)
        return cached
    cfg = CONFIGS[label]
    pairs = scan_pairs()
    jobs = [(sym, cfg["zone_tf"], cfg["entry_tf"], cfg["zone_tf_ms"]) for sym in pairs]
    all_trades = []
    print(f"[{label}] launching {len(pairs)} pair replays ({cfg['desc']}) "
          f"across {workers} workers...", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_run_one, j): j[0] for j in jobs}
        for fut in as_completed(futs):
            sym = futs[fut]
            sym_out, trades = fut.result()
            all_trades.extend(trades)
            print(f"[{label}]   {sym_out}: {len(trades)} trades", flush=True)
    print(f"[{label}] TOTAL {len(all_trades)} trades in {time.time() - t0:.1f}s", flush=True)
    save_json(f"{label}_trades.json", all_trades)
    return all_trades


# ---------------------------------------------------------------------------
# Split, stats, eligibility
# ---------------------------------------------------------------------------

def compute_cut_ts(entry_tf: str) -> tuple[int, int, int]:
    """Calendar-based ~70/30 split from the entry-TF data's own time range
    (mirrors lever_lab.py's compute_cut_ts pattern) -- not from trade
    timestamps, so the split holds regardless of how many trades a config
    produces. Returns (min_ts, max_ts, cut_ts)."""
    pairs = scan_pairs()
    min_ts, max_ts = None, 0
    for sym in pairs:
        df = load_candles(sym, entry_tf, days=DAYS, data_dir=DATA_DIR)
        if df.empty:
            continue
        lo, hi = int(df["ts"].min()), int(df["ts"].max())
        min_ts = lo if min_ts is None else min(min_ts, lo)
        max_ts = max(max_ts, hi)
    span = max_ts - min_ts
    cut_ts = min_ts + int(round((1 - HOLDOUT_FRACTION) * span))
    return min_ts, max_ts, cut_ts


def stats(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "wr": float("nan"), "net": 0.0, "net_per_trade": float("nan")}
    wins = sum(1 for t in trades if t["net_usd"] > 0)
    net = sum(t["net_usd"] for t in trades)
    return {"n": n, "wr": 100.0 * wins / n, "net": net, "net_per_trade": net / n}


def eligibility(train_stats: dict, train_days: float) -> dict:
    freq = train_stats["n"] / train_days if train_days > 0 else 0.0
    cond_net = train_stats["n"] > 0 and train_stats["net_per_trade"] > MIN_TRAIN_NET_PER_TRADE
    cond_freq = freq >= MIN_TRAIN_FREQ_PER_DAY
    cond_n = train_stats["n"] >= MIN_TRAIN_TRADES
    return {"freq_per_day": freq, "cond_net": cond_net, "cond_freq": cond_freq,
            "cond_n": cond_n, "eligible": cond_net and cond_freq and cond_n}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(results: dict):
    date = datetime.date.today().isoformat()
    lines = [f"# SR_BOUNCE higher-timeframe re-scan — {date}", "",
             "Pre-registration: "
             "`docs/superpowers/specs/2026-07-29-sr-bounce-htf-rescan-prereg.md` "
             "(frozen grid, split, selection rule, funding model, anti-fishing "
             "clause). Engine: `scripts/research/sr-bounce-htf-scan/htf_engine.py` "
             "(generalized, byte-faithful copy of the frozen "
             "`sr-bounce-scan/engine.py`). Signal math unmodified "
             "(`sr_levels.py`, `sr_signal.py` imported directly).", ""]

    lines += ["## Per-config TRAIN results (all 3, reported regardless of verdict)", "",
              "| Config | Zone/Entry TF | Train n | WR | Net | Net/trade | "
              "Trades/day | Train days |",
              "|---|---|---|---|---|---|---|---|"]
    for label in ("A", "B", "C"):
        r = results[label]
        s = r["train_stats"]
        if s["n"] == 0:
            lines.append(f"| {label} | {CONFIGS[label]['desc']} | 0 | - | - | - | - | "
                         f"{r['train_days']:.0f} |")
        else:
            lines.append(f"| {label} | {CONFIGS[label]['desc']} | {s['n']} | "
                         f"{s['wr']:.1f}% | ${s['net']:+.2f} | ${s['net_per_trade']:+.4f} | "
                         f"{r['elig']['freq_per_day']:.2f} | {r['train_days']:.0f} |")

    lines += ["", "## Eligibility checklist (pre-registered bars)", "",
              "Eligible iff: (1) train net/trade > $0 fee+funding-inclusive, "
              "(2) pooled train frequency >= 1.5 trades/day, "
              "(3) train n >= 150.", "",
              "| Config | net/trade > $0 | freq >= 1.5/day | n >= 150 | ELIGIBLE |",
              "|---|---|---|---|---|"]
    for label in ("A", "B", "C"):
        e = results[label]["elig"]
        chk = lambda b: "PASS" if b else "FAIL"
        lines.append(f"| {label} | {chk(e['cond_net'])} | {chk(e['cond_freq'])} "
                     f"({e['freq_per_day']:.2f}/day) | {chk(e['cond_n'])} | "
                     f"{'**ELIGIBLE**' if e['eligible'] else 'not eligible'} |")

    eligible_labels = [l for l in ("A", "B", "C") if results[l]["elig"]["eligible"]]
    lines += ["", "## Selection & holdout", ""]
    if not eligible_labels:
        lines.append("**No config eligible on TRAIN.** Per the pre-registered selection "
                     "rule, no holdout is read for any config. "
                     "**Verdict: DO-NOT-BUILD at higher TF** -- the timeframe thesis is "
                     "answered negative for this mechanism; per the prereg, no third "
                     "scan without a new mechanism.")
    else:
        winner = max(eligible_labels,
                     key=lambda l: results[l]["train_stats"]["net_per_trade"])
        lines.append(f"Eligible configs: {', '.join(eligible_labels)}. "
                     f"Best by TRAIN net/trade: **{winner}** "
                     f"(${results[winner]['train_stats']['net_per_trade']:+.4f}/trade). "
                     f"Per the pre-registered rule, this is the ONE config that gets a "
                     f"holdout read; the others' holdouts are never read.")
        hs = results[winner]["holdout_stats"]
        lines += ["", f"### HOLDOUT result for {winner} (single read, honesty-gated)", "",
                  f"n={hs['n']}, WR {hs['wr']:.1f}%, net ${hs['net']:+.2f}, "
                  f"net/trade ${hs['net_per_trade']:+.4f}", ""]
        passed = hs["n"] > 0 and hs["net_per_trade"] > 0
        lines.append(f"**Holdout {'PASS' if passed else 'FAIL'}** vs bar (net/trade > $0).")
        if passed:
            lines.append("Pre-committed action: spec a paper slot at this config "
                         "(new slot, new registration).")
        else:
            lines.append("Pre-committed action: written to memory as final -- the S/R "
                         "bounce mechanism is closed at ALL tested timeframes without a "
                         "new mechanism.")

    lines += ["", "## Methodology notes", "",
              "- Fees 0.12% RT of notional (unchanged). Funding: 0.01% of notional per "
              "8h of hold time, always charged as a cost (never a credit), per the "
              "prereg. Hold time measured fill-to-exit (see build report for the "
              "documented reasoning on this implementation choice).",
              "- TRAIN/HOLDOUT split is a calendar ~70/30 split of each config's own "
              "entry-TF data range (not a trade-count split), so it holds regardless "
              "of how many trades a config produces.",
              "- Selection happened on TRAIN ONLY, one winner, one holdout read -- "
              "per the pre-registration's anti-fishing clause. No added configs, no "
              "threshold changes, no re-slicing after results.", ""]

    path = os.path.join(BOT_DIR, "reports", f"{date}-sr-bounce-htf-scan.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nreport -> {path}")
    return path


def _replay_and_split(label: str, workers: int) -> dict:
    trades = run_config(label, workers)
    cfg = CONFIGS[label]
    min_ts, max_ts, cut_ts = compute_cut_ts(cfg["entry_tf"])
    train = [t for t in trades if t["signal_ts"] < cut_ts]
    hold = [t for t in trades if t["signal_ts"] >= cut_ts]
    train_days = (cut_ts - min_ts) / 86_400_000
    tstats = stats(train)
    elig = eligibility(tstats, train_days)
    save_json(f"{label}_meta.json", {
        "min_ts": min_ts, "max_ts": max_ts, "cut_ts": cut_ts,
        "train_days": train_days, "train_stats": tstats, "elig": elig,
        "holdout_n": len(hold),
    })
    return {"trades": trades, "train": train, "holdout": hold,
            "train_stats": tstats, "train_days": train_days, "elig": elig}


def _load_cached_result(label: str) -> dict | None:
    trades = load_json(f"{label}_trades.json")
    meta = load_json(f"{label}_meta.json")
    if trades is None or meta is None:
        return None
    cut_ts = meta["cut_ts"]
    return {"trades": trades,
            "train": [t for t in trades if t["signal_ts"] < cut_ts],
            "holdout": [t for t in trades if t["signal_ts"] >= cut_ts],
            "train_stats": meta["train_stats"], "train_days": meta["train_days"],
            "elig": meta["elig"]}


def _finalize_and_write_report(results: dict):
    """Apply the pre-registered selection rule (single winner, single holdout
    read) and write the report."""
    eligible_labels = [l for l in ("A", "B", "C") if results[l]["elig"]["eligible"]]
    if eligible_labels:
        winner = max(eligible_labels,
                     key=lambda l: results[l]["train_stats"]["net_per_trade"])
        results[winner]["holdout_stats"] = stats(results[winner]["holdout"])
    write_report(results)


def main():
    workers = min(8, os.cpu_count() or 4)
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"

    if phase not in ("all", "fetch", "report", *CONFIGS):
        print(f"unknown phase {phase}")
        return

    if phase in ("all", "fetch"):
        fetch_all()
        if phase == "fetch":
            return

    if phase in CONFIGS:
        r = _replay_and_split(phase, workers)
        print(f"done: {phase} (n={len(r['trades'])}, train={r['train_stats']})")
        return

    if phase == "report":
        results = {}
        for label in CONFIGS:
            r = _load_cached_result(label)
            if r is None:
                print(f"report: missing cached data for {label}, run it first")
                return
            results[label] = r
        _finalize_and_write_report(results)
        return

    # phase == "all": fetch (done above) -> replay all 3 configs -> report
    results = {label: _replay_and_split(label, workers) for label in CONFIGS}
    _finalize_and_write_report(results)


if __name__ == "__main__":
    main()
