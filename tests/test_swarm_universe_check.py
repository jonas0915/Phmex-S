"""universe_check: pure tradeability check over a ccxt markets dict + CLI. No network anywhere here —
the markets dict is a fake fixture and the CLI is driven with --markets-json."""
import json
import subprocess
import sys

import pytest

from research.swarm.lib import universe_check as uc

REPO = uc.REPO_ROOT


@pytest.fixture
def markets():
    """One active market, one delisted (active=False, info.status Delisted), one absent (GHOST)."""
    return {
        "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "active": True, "info": {"status": "Listed"}},
        "GIGGLE/USDT:USDT": {"symbol": "GIGGLE/USDT:USDT", "active": False, "info": {"status": "Delisted"}},
    }


@pytest.fixture
def thesis(tmp_path):
    t = {"id": "t_universe", "spec": {"dataset": "long_1h", "universe": ["BTC", "GIGGLE", "GHOST"]}, "signal_py": "def signals(df): ..."}
    p = tmp_path / "thesis.json"
    p.write_text(json.dumps(t))
    return p


# --- to_exchange_symbol -------------------------------------------------------------------

def test_to_exchange_symbol_forms():
    assert uc.to_exchange_symbol("GIGGLE") == "GIGGLE/USDT:USDT"
    assert uc.to_exchange_symbol("btc") == "BTC/USDT:USDT"
    assert uc.to_exchange_symbol("ETH_USDT_USDT") == "ETH/USDT:USDT"
    assert uc.to_exchange_symbol("ETH/USDT:USDT") == "ETH/USDT:USDT"
    assert uc.to_exchange_symbol("1000PEPE") == "1000PEPE/USDT:USDT"


# --- check / all_tradeable / untradeable ------------------------------------------------------

def test_check_is_pure_and_per_symbol(markets):
    r = uc.check(["BTC", "GIGGLE", "GHOST"], markets)
    recs = {x["input"]: x for x in r["symbols"]}
    assert recs["BTC"] == {"input": "BTC", "symbol": "BTC/USDT:USDT", "found": True, "active": True, "status": "Listed"}
    assert recs["GIGGLE"] == {"input": "GIGGLE", "symbol": "GIGGLE/USDT:USDT", "found": True, "active": False, "status": "Delisted"}
    assert recs["GHOST"] == {"input": "GHOST", "symbol": "GHOST/USDT:USDT", "found": False, "active": False, "status": None}
    assert [x["input"] for x in r["symbols"]] == ["BTC", "GIGGLE", "GHOST"]   # input order kept
    assert r["tradeable"] == ["BTC"]
    assert r["untradeable"] == ["GIGGLE/USDT:USDT", "GHOST/USDT:USDT"]
    assert r["all_tradeable"] is False


def test_check_accepts_exchange_form_input(markets):
    r = uc.check(["BTC/USDT:USDT"], markets)
    assert r["symbols"][0]["found"] is True and r["all_tradeable"] is True


def test_helpers(markets):
    ok = uc.check(["BTC"], markets)
    assert uc.all_tradeable(ok) is True and uc.untradeable(ok) == []
    bad = uc.check(["GIGGLE", "BTC", "GHOST"], markets)
    assert uc.all_tradeable(bad) is False
    assert uc.untradeable(bad) == ["GIGGLE/USDT:USDT", "GHOST/USDT:USDT"]
    empty = uc.check([], markets)
    assert uc.all_tradeable(empty) is False and uc.untradeable(empty) == []


def test_status_missing_info_is_none():
    r = uc.check(["X"], {"X/USDT:USDT": {"active": True}})
    assert r["symbols"][0]["status"] is None and r["symbols"][0]["active"] is True


def test_active_none_is_not_tradeable():
    r = uc.check(["X"], {"X/USDT:USDT": {"active": None, "info": {"status": "Listed"}}})
    assert r["symbols"][0]["active"] is False and r["all_tradeable"] is False


def test_prune_thesis_drops_untradeable(markets):
    t = {"spec": {"universe": ["BTC", "GIGGLE", "GHOST"]}}
    r = uc.check(t["spec"]["universe"], markets)
    pruned, dropped = uc.prune_universe(t, r)
    assert pruned["spec"]["universe"] == ["BTC"]
    assert dropped == [{"symbol": "GIGGLE/USDT:USDT", "status": "Delisted"}, {"symbol": "GHOST/USDT:USDT", "status": "NOT_FOUND"}]
    assert t["spec"]["universe"] == ["BTC", "GIGGLE", "GHOST"]   # input not mutated


# --- CLI ---------------------------------------------------------------------------------------

def _cli(*argv, markets_path):
    return subprocess.run([sys.executable, "-m", "research.swarm.lib.universe_check", "--markets-json", str(markets_path), *argv],
                          cwd=REPO, capture_output=True, text=True)


@pytest.fixture
def markets_path(tmp_path, markets):
    p = tmp_path / "markets.json"
    p.write_text(json.dumps(markets))
    return p


def test_cli_ok_exit_0(markets_path):
    r = _cli("BTC", markets_path=markets_path)
    assert r.returncode == 0, r.stderr
    assert "BTC/USDT:USDT active status=Listed" in r.stdout
    assert r.stdout.rstrip().splitlines()[-1] == "UNIVERSE OK"


def test_cli_untradeable_exit_1(markets_path):
    r = _cli("BTC", "GIGGLE", "GHOST", markets_path=markets_path)
    assert r.returncode == 1
    lines = r.stdout.rstrip().splitlines()
    assert "GIGGLE/USDT:USDT DELISTED status=Delisted" in lines
    assert "GHOST/USDT:USDT NOT_FOUND status=None" in lines
    assert lines[-1] == "UNIVERSE UNTRADEABLE: GIGGLE/USDT:USDT, GHOST/USDT:USDT"


def test_cli_json(markets_path):
    r = _cli("--json", "BTC", "GIGGLE", markets_path=markets_path)
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert d["all_tradeable"] is False and d["untradeable"] == ["GIGGLE/USDT:USDT"] and d["tradeable"] == ["BTC"]
    assert {x["input"] for x in d["symbols"]} == {"BTC", "GIGGLE"}


def test_cli_frozen_reads_spec_universe(tmp_path, markets_path):
    frozen = tmp_path / "x.frozen.json"
    frozen.write_text(json.dumps({"thesis": {"id": "x", "spec": {"universe": ["BTC", "GIGGLE"]}}, "sha256": "0"}))
    r = _cli("--frozen", str(frozen), markets_path=markets_path)
    assert r.returncode == 1
    assert r.stdout.rstrip().splitlines()[-1] == "UNIVERSE UNTRADEABLE: GIGGLE/USDT:USDT"
    frozen_ok = tmp_path / "ok.frozen.json"
    frozen_ok.write_text(json.dumps({"thesis": {"id": "ok", "spec": {"universe": ["BTC"]}}, "sha256": "0"}))
    assert _cli("--frozen", str(frozen_ok), markets_path=markets_path).returncode == 0


def test_cli_thesis_prune_writes_pruned_copy(tmp_path, thesis, markets_path):
    out = tmp_path / "pruned.json"
    r = _cli("--json", "--thesis", str(thesis), "--prune-to", str(out), markets_path=markets_path)
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert d["dropped_symbols"] == [{"symbol": "GIGGLE/USDT:USDT", "status": "Delisted"}, {"symbol": "GHOST/USDT:USDT", "status": "NOT_FOUND"}]
    assert d["pruned_path"] == str(out)
    pruned = json.loads(out.read_text())
    assert pruned["spec"]["universe"] == ["BTC"]
    assert pruned["id"] == "t_universe" and pruned["signal_py"] == "def signals(df): ..."
    assert json.loads(thesis.read_text())["spec"]["universe"] == ["BTC", "GIGGLE", "GHOST"]   # original untouched


def test_cli_thesis_prune_all_untradeable_writes_nothing(tmp_path, markets_path):
    t = tmp_path / "t.json"
    t.write_text(json.dumps({"id": "dead", "spec": {"universe": ["GIGGLE", "GHOST"]}}))
    out = tmp_path / "pruned.json"
    r = _cli("--json", "--thesis", str(t), "--prune-to", str(out), markets_path=markets_path)
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert d["tradeable"] == [] and d["pruned_path"] is None
    assert not out.exists()


def test_cli_no_symbols_is_usage_error(markets_path):
    r = _cli(markets_path=markets_path)
    assert r.returncode == 2


def test_cli_save_markets_roundtrip(tmp_path, markets_path, markets):
    saved = tmp_path / "saved.json"
    r = _cli("--save-markets", str(saved), "BTC", markets_path=markets_path)
    assert r.returncode == 0
    assert json.loads(saved.read_text()) == markets
