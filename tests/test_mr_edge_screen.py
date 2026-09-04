"""TDD for scripts/slot_lab/mr_edge_screen.py — Phase D train/holdout screen.

Synthetic signal tables only (the real reports/mr_edge_2026/signals.json does not
exist yet). The live bot is never imported. Every run writes to tmp_path.
"""
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone

import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts", "slot_lab"))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

import mr_edge_screen as mes  # noqa: E402
import mean_revert_filters as mrf  # noqa: E402

N_BOOT = 150  # small for test speed; production default is 2000
PREREG = os.path.join(BOT_DIR, "docs", "superpowers", "specs",
                      "2026-09-03-mr-edge-search-prereg.md")
H5_COUNT = len(mrf._buckets([{"side": "long", "rsi": 20.0, "vol_mult": 1.5, "adx": 10.0,
                               "hour_pt": 3, "bb_width_pct": 1.0}]))


def _utc(y, m, d, H=0, M=0, S=0):
    return int(datetime(y, m, d, H, M, S, tzinfo=timezone.utc).timestamp())


# ---------------------------------------------------------------------------
# synthetic signal table
# ---------------------------------------------------------------------------

TP = (1.0, 1.6, 2.0, 2.4, 3.0)
SL = (0.8, 1.2, 1.6, 2.0)
TH = (2, 4, 6, 8)
CELLS = [f"tp{tp}_sl{sl}_t{t}h" for tp in TP for sl in SL for t in TH]
SYMS = ["AAA/USDT:USDT", "BBB/USDT:USDT", "CCC/USDT:USDT"]


def make_rows(seed=1, n=600, base_mean=0.3, bad_mean=-1.0, sd=0.5, noise=False,
              t0=None, t1=None, plant="h3"):
    """~n rows spread uniformly over the whole window with a PLANTED effect:
    plant="h3": shorts with flow.buy_ratio >= 0.90 (and trade_count > 20) have mean
    `bad_mean`; plant="h6": rows with confirmed_at_close False have mean `bad_mean`;
    everything else `base_mean`. noise=True -> every row N(0, 1).
    Every grid cell = live + N(0, 0.05) (no cell beats live); the live twin
    cell equals live exactly."""
    rnd = random.Random(seed)
    t0 = t0 or _utc(2026, 6, 1)
    t1 = t1 or _utc(2026, 9, 2, 23)
    rows = []
    for i in range(n):
        ts = int(t0 + rnd.random() * (t1 - t0))
        side = "short" if rnd.random() < 0.5 else "long"
        r = rnd.random()
        if r < 0.10:
            flow = None
        else:
            flow = {"buy_ratio": round(0.5 + 0.5 * rnd.random(), 4),
                    "imbalance": round(rnd.uniform(-0.5, 0.5), 3),
                    "trade_count": 10 if r < 0.15 else 50,
                    "cvd_slope": 0.0, "divergence": None,
                    "large_trade_bias": 0.0, "spread_pct": 0.05, "dt_s": 30}
        # prereg amendment v2: forming-bar timing fields (~5% null each)
        fire_minute = None if rnd.random() < 0.05 else rnd.randint(1, 5)
        confirmed = None if rnd.random() < 0.05 else (rnd.random() < 0.6)
        if plant == "h3":
            planted_bad = (side == "short" and flow is not None
                           and flow["buy_ratio"] >= 0.90 and flow["trade_count"] > 20)
        else:  # "h6": the closed-bar strategy NOT confirming the entry is the bad cohort
            planted_bad = confirmed is False
        if noise:
            live = rnd.gauss(0.0, 1.0)
        else:
            live = rnd.gauss(bad_mean if planted_bad else base_mean, sd)
        net = {"live": round(live, 4)}
        for c in CELLS:
            net[c] = round(live if c == mes.LIVE_TWIN else live + rnd.gauss(0, 0.05), 4)
        fr = rnd.random()
        rows.append({
            "symbol": SYMS[i % 3], "ts": ts, "side": side,
            "entry_px": 1.0 + rnd.random(),
            "rsi": rnd.uniform(70, 92) if side == "short" else rnd.uniform(8, 30),
            "rsi_fast": rnd.uniform(5, 95),
            "vol_ratio": rnd.uniform(1.0, 3.5),
            "bb_width_pct": rnd.uniform(0.3, 6.0),
            "adx5m": rnd.uniform(5, 34),
            "adx1h": None if rnd.random() < 0.08 else rnd.uniform(10, 65),
            "hour_pt": rnd.randrange(24), "session": "us",
            "flow": flow, "scanner_active": rnd.random() < 0.3,
            "funding_rate": None if fr < 0.1 else rnd.uniform(-0.0007, 0.0007),
            "funding_ts": ts - 3600,
            "fire_minute": fire_minute, "confirmed_at_close": confirmed,
            "net_by_cell": net,
            "exit_by_cell": {c: rnd.choice(["tp", "sl", "time"]) for c in net},
        })
    rows.sort(key=lambda r: r["ts"])
    return rows


def make_signals(rows, prereg_sha):
    return {
        "meta": {"window": "2026-06-01..2026-09-03 UTC", "universe": SYMS,
                 "margin": 15, "notional": 150, "maker_fee": 0.0001,
                 "taker_fee": 0.0006, "trail_arm": 8.0, "cells": ["live"] + CELLS,
                 "generated_at": "2026-09-03T00:00:00Z", "prereg_sha": prereg_sha,
                 "caveats": ["fill-all at close: every dollar is an upper bound"]},
        "rows": rows,
    }


@pytest.fixture
def rig(tmp_path):
    """Helper that writes a signals table stamped with the REAL prereg sha and
    runs the phases against tmp_path."""
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    out = tmp_path / "out"

    class Rig:
        prereg_path = PREREG
        prereg_sha = sha
        out_dir = str(out)
        signals_path = str(tmp_path / "signals.json")
        tmp = tmp_path

        def write(self, rows, sha_override=None):
            with open(self.signals_path, "w") as f:
                json.dump(make_signals(rows, sha_override or sha), f)
            return self.signals_path

        def train(self):
            return mes.run_train(self.signals_path, self.prereg_path, self.out_dir,
                                 n_boot=N_BOOT, seed=0)

        def holdout(self):
            return mes.run_holdout(self.signals_path, self.prereg_path, self.out_dir,
                                   n_boot=N_BOOT, seed=0)

    return Rig()


# ---------------------------------------------------------------------------
# split / embargo
# ---------------------------------------------------------------------------

def test_split_and_embargo_boundaries():
    def row(ts):
        return {"ts": ts}
    cases = {
        _utc(2026, 5, 31, 23, 59, 59): "dropped",
        _utc(2026, 6, 1, 0, 0, 0): "train",
        _utc(2026, 8, 3, 23, 59, 59): "train",
        _utc(2026, 8, 4, 0, 0, 0): "dropped",        # embargo start
        _utc(2026, 8, 4, 7, 59, 59): "dropped",       # inside 8 h embargo
        _utc(2026, 8, 4, 8, 0, 0): "holdout",         # embargo end (inclusive)
        _utc(2026, 9, 2, 23, 59, 59): "holdout",
        _utc(2026, 9, 3, 0, 0, 0): "dropped",         # holdout end (exclusive)
    }
    train, holdout, dropped = mes.split_rows([row(t) for t in cases])
    got = {}
    for r in train:
        got[r["ts"]] = "train"
    for r in holdout:
        got[r["ts"]] = "holdout"
    for r in dropped:
        got[r["ts"]] = "dropped"
    assert got == cases
    assert mes.HOLDOUT_START == _utc(2026, 8, 4) + 8 * 3600


# ---------------------------------------------------------------------------
# trial construction + null handling
# ---------------------------------------------------------------------------

def test_h1_cells_exclude_live_and_live_twin():
    cells = mes.h1_cells(["live"] + CELLS)
    assert len(cells) == 79
    assert "live" not in cells
    assert mes.LIVE_TWIN == "tp1.6_sl1.2_t4h"
    assert mes.LIVE_TWIN not in cells


def test_h2_null_adx1h_excluded_from_both_cohorts():
    rows = [{"adx1h": 30.0}, {"adx1h": 45.0}, {"adx1h": None}, {"adx1h": 50.0}]
    kept, removed, null = mes.apply_h2(rows, 40)
    assert kept == [0]
    assert removed == [1, 3]
    assert null == [2]


def test_h3_shorts_only_null_flow_and_low_trade_count_kept():
    rows = [
        {"side": "short", "flow": {"buy_ratio": 0.95, "trade_count": 50}},  # removed
        {"side": "short", "flow": {"buy_ratio": 0.95, "trade_count": 20}},  # kept: count not > 20
        {"side": "short", "flow": None},                                    # kept: null flow
        {"side": "long", "flow": {"buy_ratio": 0.99, "trade_count": 50}},   # kept: long
        {"side": "short", "flow": {"buy_ratio": 0.89, "trade_count": 50}},  # kept: below X
        {"side": "short", "flow": {"buy_ratio": 0.90, "trade_count": 21}},  # removed: >= X
    ]
    kept, removed, null = mes.apply_h3(rows, 0.90)
    assert removed == [0, 5]
    assert kept == [1, 2, 3, 4]
    assert null == []


def test_h4_funding_directional_null_kept():
    rows = [
        {"side": "short", "funding_rate": -0.0004},  # removed (<= -X)
        {"side": "short", "funding_rate": +0.0004},  # kept
        {"side": "long", "funding_rate": +0.0004},   # removed (>= +X)
        {"side": "long", "funding_rate": -0.0004},   # kept
        {"side": "long", "funding_rate": None},      # kept: null
        {"side": "short", "funding_rate": -0.0003},  # removed: boundary inclusive
    ]
    kept, removed, null = mes.apply_h4(rows, 0.0003)
    assert removed == [0, 2, 5]
    assert kept == [1, 3, 4]
    assert null == []


def test_h5_reuses_mean_revert_filters_buckets():
    rows = make_rows(seed=3, n=200)
    buckets = mes.h5_buckets(rows)
    shim = [mes._h5_shim(r, i) for i, r in enumerate(rows)]
    expected = mrf._buckets([s for s in shim if s is not None])
    assert list(buckets.keys()) == list(expected.keys())
    assert len(buckets) == H5_COUNT == 22
    # adapter maps the signal-table keys onto what _buckets expects
    sh = mes._h5_shim(rows[5], 5)
    assert sh["rsi"] == rows[5]["rsi_fast"]
    assert sh["vol_mult"] == rows[5]["vol_ratio"]
    assert sh["adx"] == rows[5]["adx5m"]
    assert sh["side"] == rows[5]["side"] and sh["hour_pt"] == rows[5]["hour_pt"]
    assert sh["bb_width_pct"] == rows[5]["bb_width_pct"]
    # a null feature excludes the row from every bucket AND from the H5 universe
    rows[0]["adx5m"] = None
    kept, removed, null = mes.apply_h5(rows, "side=long", mes.h5_buckets(rows))
    assert 0 in null and 0 not in kept and 0 not in removed
    assert set(kept) | set(removed) | set(null) == set(range(len(rows)))


def test_h5_bbwidth_thresholds_frozen_from_train_in_holdout():
    rows = make_rows(seed=4, n=300)
    b_train = mes.h5_buckets(rows[:150])
    thr = mes.h5_bb_thresholds(rows[:150])
    b_hold = mes.h5_buckets(rows[150:], bb_thresholds=thr)
    lo = b_hold["bbwidth low"]
    assert all(r["bb_width_pct"] <= thr[0] for r in lo)
    assert len(b_train) == len(b_hold) == H5_COUNT


def test_trial_total_is_79_plus_9_plus_h5_count():
    rows = make_rows(seed=5, n=200)
    assert mes.trial_total(["live"] + CELLS, rows) == 79 + 3 + 3 + 3 + H5_COUNT + 3 == 113


def test_h6_variants_and_null_excluded_from_both_cohorts():
    rows = [
        {"fire_minute": 1, "confirmed_at_close": True},
        {"fire_minute": 2, "confirmed_at_close": False},
        {"fire_minute": 3, "confirmed_at_close": None},
        {"fire_minute": None, "confirmed_at_close": True},
        {"fire_minute": 5, "confirmed_at_close": False},
    ]
    assert mes.apply_h6(rows, "confirmed_at_close") == ([0, 3], [1, 4], [2])
    assert mes.apply_h6(rows, "fire_minute<=2") == ([0, 1], [2, 4], [3])
    assert mes.apply_h6(rows, "fire_minute>=3") == ([2, 4], [0, 1], [3])
    assert mes.H6_VARIANTS == ("confirmed_at_close", "fire_minute<=2", "fire_minute>=3")
    with pytest.raises(ValueError):
        mes.apply_h6(rows, "fire_minute>=9")


# ---------------------------------------------------------------------------
# train phase
# ---------------------------------------------------------------------------

def test_train_bh_is_pooled_once_over_all_trials(rig, monkeypatch):
    calls = []
    real = mes.ST.benjamini_hochberg

    def spy(pvalues, alpha=0.05):
        calls.append((list(pvalues), alpha))
        return real(pvalues, alpha)

    monkeypatch.setattr(mes.ST, "benjamini_hochberg", spy)
    rig.write(make_rows(seed=7))
    res = rig.train()
    assert len(calls) == 1
    assert len(calls[0][0]) == res["trial_total"] == 113
    assert calls[0][1] == pytest.approx(0.10)


def test_train_planted_effect_selects_h3_090_only(rig):
    rig.write(make_rows(seed=11))
    res = rig.train()
    assert res["trial_total"] == 113
    assert res["prereg_sha"] == rig.prereg_sha
    w = res["winners"]
    assert set(w) == {"H1", "H2", "H3", "H4", "H5", "H6"}
    assert w["H3"] is not None
    assert w["H3"]["label"] == "short_skip_buy_ratio>=0.90"
    assert w["H1"] is None  # every cell == live + noise
    assert w["H2"] is None and w["H4"] is None and w["H5"] is None and w["H6"] is None
    h3 = {t["label"]: t for t in res["families"]["H3"]["trials"]}
    t = h3["short_skip_buy_ratio>=0.90"]
    assert t["removed"]["ci"][1] < 0
    assert t["kept"]["mean"] > res["baseline"]["mean"]
    assert t["bh_pass"] and t["dsr"] > 0.95 and t["wf_signs"] == [True, True, True]
    assert t["min_n_ok"] and t["selected"]
    # artifacts
    assert os.path.exists(os.path.join(rig.out_dir, "train_results.json"))
    md = open(os.path.join(rig.out_dir, "train_report.md")).read()
    assert "short_skip_buy_ratio>=0.90" in md
    for c in CELLS:
        if c != mes.LIVE_TWIN:
            assert c in md
    assert mes.LIVE_TWIN not in {t["label"] for t in res["families"]["H1"]["trials"]}
    assert len(res["families"]["H1"]["trials"]) == 79
    assert "conservative" in md.lower()


def test_train_planted_confirmed_at_close_selects_h6a(rig):
    rig.write(make_rows(seed=12, plant="h6"))
    res = rig.train()
    w = res["winners"]
    assert w["H6"] is not None
    assert w["H6"]["label"] == "confirmed_at_close"
    assert w["H1"] is None and w["H3"] is None
    h6 = {t["label"]: t for t in res["families"]["H6"]["trials"]}
    assert len(h6) == 3
    t = h6["confirmed_at_close"]
    assert t["selected"] and t["removed"]["ci"][1] < 0 and t["n_null"] > 0
    assert not h6["fire_minute<=2"]["selected"] and not h6["fire_minute>=3"]["selected"]
    md = open(os.path.join(rig.out_dir, "train_report.md")).read()
    assert "## H6" in md and "fire_minute<=2" in md and "fire_minute>=3" in md
    # holdout reads the H6 winner only and locks it
    hres = rig.holdout()
    assert set(hres["evaluated"]) == {"H6"}
    assert hres["evaluated"]["H6"]["verdict"] in ("WEAK", "STRONG")
    assert hres["evaluated"]["H6"]["verdict"] == "WEAK"  # planted +0.3 < $0.50
    assert os.path.exists(os.path.join(rig.out_dir, "holdout_read_H6.lock"))


def test_train_pure_noise_has_no_winners(rig):
    rig.write(make_rows(seed=13, noise=True))
    res = rig.train()
    assert all(v is None for v in res["winners"].values())
    for fam in res["families"].values():
        assert not any(t["selected"] for t in fam["trials"])


def test_train_refuses_on_prereg_sha_mismatch(rig):
    rig.write(make_rows(seed=15), sha_override="0" * 64)
    with pytest.raises(mes.GuardError):
        rig.train()


# ---------------------------------------------------------------------------
# holdout guards
# ---------------------------------------------------------------------------

def test_holdout_refuses_without_train_results(rig):
    rig.write(make_rows(seed=17))
    with pytest.raises(mes.GuardError, match="train_results"):
        rig.holdout()


def test_holdout_refuses_wrong_prereg_sha(rig):
    rig.write(make_rows(seed=19))
    rig.train()
    # prereg edited after registration -> sha no longer matches meta.prereg_sha
    edited = rig.tmp / "prereg_edited.md"
    edited.write_text(open(PREREG).read() + "\n(edited after the fact)\n")
    with pytest.raises(mes.GuardError, match="sha"):
        mes.run_holdout(rig.signals_path, str(edited), rig.out_dir, n_boot=N_BOOT, seed=0)
    assert not os.path.exists(os.path.join(rig.out_dir, "holdout_read_H3.lock"))


def test_holdout_refuses_when_meta_sha_is_not_the_registered_prereg(rig):
    # signals.json stamped with some other sha -> holdout never runs (train also refuses,
    # so plant a valid train_results first, then swap the signals file)
    rig.write(make_rows(seed=20))
    rig.train()
    rig.write(make_rows(seed=20), sha_override="deadbeef" * 8)
    with pytest.raises(mes.GuardError, match="sha"):
        rig.holdout()


def test_holdout_refuses_existing_lock(rig):
    rig.write(make_rows(seed=21))
    rig.train()
    lock = os.path.join(rig.out_dir, "holdout_read_H3.lock")
    with open(lock, "w") as f:
        f.write("already read\n")
    with pytest.raises(mes.GuardError, match="lock"):
        rig.holdout()


def test_holdout_second_read_refused_after_first(rig):
    rig.write(make_rows(seed=23))
    rig.train()
    rig.holdout()
    assert os.path.exists(os.path.join(rig.out_dir, "holdout_read_H3.lock"))
    with pytest.raises(mes.GuardError, match="lock"):
        rig.holdout()


# ---------------------------------------------------------------------------
# holdout verdicts
# ---------------------------------------------------------------------------

def test_holdout_weak_verdict_for_planted_0_3(rig):
    rig.write(make_rows(seed=25, base_mean=0.3))
    rig.train()
    res = rig.holdout()
    assert set(res["evaluated"].keys()) == {"H3"}  # only train winners are read
    v = res["evaluated"]["H3"]
    assert v["label"] == "short_skip_buy_ratio>=0.90"
    assert v["kept"]["n"] >= 20
    assert v["kept"]["ci"][0] > 0
    assert v["kept"]["mean"] < 0.50
    assert v["verdict"] == "WEAK"
    assert "removed_n_ok" in v  # removed floor is reported in holdout, not a verdict gate
    assert os.path.exists(os.path.join(rig.out_dir, "holdout_results.json"))
    md = open(os.path.join(rig.out_dir, "holdout_report.md")).read()
    assert "WEAK" in md and "H3" in md


def test_holdout_strong_verdict_for_planted_0_8(rig):
    rig.write(make_rows(seed=27, base_mean=0.8))
    rig.train()
    res = rig.holdout()
    v = res["evaluated"]["H3"]
    assert v["kept"]["mean"] >= 0.50
    assert v["kept"]["ci"][0] > 0
    assert v["wf_full_signs"] == [True, True, True]
    assert v["verdict"] == "STRONG"


def test_holdout_null_when_effect_vanishes(rig):
    # planted in train only; holdout rows are pure noise -> NULL
    train_rows = make_rows(seed=29, n=450, t1=_utc(2026, 8, 3, 23))
    hold_rows = make_rows(seed=31, n=150, noise=True, t0=_utc(2026, 8, 4, 8))
    rig.write(sorted(train_rows + hold_rows, key=lambda r: r["ts"]))
    rig.train()
    res = rig.holdout()
    assert res["evaluated"]["H3"]["verdict"] == "NULL"


def test_holdout_verdict_null_when_kept_below_20(rig):
    # thin holdout: only 12 rows land after the embargo -> kept < 20 -> NULL (min_n)
    train_rows = make_rows(seed=37, n=500, t1=_utc(2026, 8, 3, 23))
    hold_rows = make_rows(seed=38, n=12, t0=_utc(2026, 8, 4, 8))
    rig.write(sorted(train_rows + hold_rows, key=lambda r: r["ts"]))
    rig.train()
    v = rig.holdout()["evaluated"]["H3"]
    assert v["kept"]["n"] < 20 and v["verdict"] == "NULL" and v["verdict_reasons"] == ["min_n"]


def test_holdout_with_no_train_winners_reads_nothing(rig):
    rig.write(make_rows(seed=33, noise=True))
    rig.train()
    res = rig.holdout()
    assert res["evaluated"] == {}
    assert not any(f.startswith("holdout_read_") for f in os.listdir(rig.out_dir))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_train_then_holdout(rig):
    rig.write(make_rows(seed=35))
    rc = mes.main(["--phase", "train", "--signals", rig.signals_path,
                   "--prereg", rig.prereg_path, "--out", rig.out_dir,
                   "--n-boot", str(N_BOOT)])
    assert rc == 0
    rc = mes.main(["--phase", "holdout", "--signals", rig.signals_path,
                   "--prereg", rig.prereg_path, "--out", rig.out_dir,
                   "--n-boot", str(N_BOOT)])
    assert rc == 0
    # guard failures exit non-zero instead of raising
    rc = mes.main(["--phase", "holdout", "--signals", rig.signals_path,
                   "--prereg", rig.prereg_path, "--out", rig.out_dir,
                   "--n-boot", str(N_BOOT)])
    assert rc == 2


def test_isolation_never_imports_live_bot_modules():
    for name in ("bot", "exchange", "config", "risk_manager"):
        assert name not in sys.modules
    src = open(os.path.join(BOT_DIR, "scripts", "slot_lab", "mr_edge_screen.py")).read()
    for name in ("import bot", "import exchange", "import config", "import risk_manager"):
        assert name not in src
