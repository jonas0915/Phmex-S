"""Main-book PAPER mode on the dashboard (.paper_main sentinel, owner
demotion order 2026-08-26).

Conventions under test (TASKS.md 8/26, mirrored from bot.py's build):
- Sentinel `.paper_main` in the repo root, checked fresh: present = the main
  book (trading_state.json / 5m_scalp + its main_gated view) runs PAPER —
  badge must never read LIVE, size is sim sizing, 5m_scalp leaves the live set.
- Row-level truth is the trade's OWN mode field, never the sentinel:
  no mode field = REAL MONEY (historical rows predate the tag),
  mode="paper" = demotion-era sim. Paper and real-money numbers never blend
  (owner hard rule 2026-08-12).
- Historical no-mode rows must NEVER be dropped by the PAPER_HONEST_TS
  honest-paper cutoff, sentinel present or not — running them through
  _honest_paper would silently drop every real trade before 2026-08-06
  (the 2026-08-12 main_gated leak class).
"""
import sys
import time

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")


def _wd(tmp_path, monkeypatch, sentinel: bool):
    import web_dashboard as wd
    monkeypatch.setattr(wd, "PROJECT_DIR", str(tmp_path))
    if sentinel:
        (tmp_path / ".paper_main").touch()
    return wd


def _main_trades(wd):
    """2 real rows (one historical pre-honest-cutoff, NO mode field) +
    1 paper sim row. Real net = +$3.00; blended would be +$10.77."""
    FIX = wd.PAPER_HONEST_TS
    return [
        {"opened_at": FIX - 50000, "pnl_usdt": 1.00, "side": "short"},
        {"opened_at": FIX + 1000, "pnl_usdt": 2.00, "side": "short"},
        {"opened_at": FIX + 2000, "pnl_usdt": 7.77, "side": "short",
         "mode": "paper"},
    ]


def test_live_slot_ids_sentinel_aware(tmp_path, monkeypatch):
    """.paper_main present => 5m_scalp is NOT in the live set; removed =>
    it is again (fresh os.path.exists check, no cache)."""
    wd = _wd(tmp_path, monkeypatch, sentinel=False)
    assert "5m_scalp" in wd._live_slot_ids()
    (tmp_path / ".paper_main").touch()
    assert "5m_scalp" not in wd._live_slot_ids()
    (tmp_path / ".paper_main").unlink()
    assert "5m_scalp" in wd._live_slot_ids()


def test_main_badges_paper_not_live(tmp_path, monkeypatch):
    """Both main-book badges (5m_scalp + the main_gated view) read PAPER,
    never LIVE, while the sentinel exists."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    live_ids = wd._live_slot_ids()
    html = wd._slot_status_html("5m_scalp", [], live_ids, {})
    assert "PAPER" in html and "LIVE" not in html
    gated = wd._slot_status_html("main_gated", [], live_ids, {})
    assert "PAPER" in gated and "LIVE" not in gated
    assert "view of MAIN PATH" in gated  # still labeled as a view, not a book


def test_paper_badge_keeps_halt_note(tmp_path, monkeypatch):
    """Both sentinels coexist during the demotion transition: the PAPER badge
    must still surface the entries halt (and never read LIVE)."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    (tmp_path / ".halt_main_entries").touch()
    html = wd._slot_status_html("5m_scalp", [], wd._live_slot_ids(), {})
    assert "PAPER" in html and "HALTED" in html and "LIVE" not in html


def test_no_sentinel_badge_regression(tmp_path, monkeypatch):
    """Sentinel absent => behavior identical to today (LIVE / HALTED logic)."""
    wd = _wd(tmp_path, monkeypatch, sentinel=False)
    html = wd._slot_status_html("5m_scalp", [], {"5m_scalp"}, {})
    assert "LIVE" in html and "PAPER" not in html
    (tmp_path / ".halt_main_entries").touch()
    html = wd._slot_status_html("5m_scalp", [], {"5m_scalp"}, {})
    assert "HALTED" in html and "LIVE" not in html


def test_paper_main_card_splits_real_and_paper(tmp_path, monkeypatch):
    """5m_scalp card with the sentinel: real aggregates exclude the
    mode='paper' row, the sims render on their own clearly-badged row, and
    the historical no-mode row is never honest-dropped."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    card = wd._build_signal_card(
        "5m_scalp", "MAIN", {"closed_trades": _main_trades(wd), "positions": {}},
        wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "PAPER (sim fills)" in card and "LIVE" not in card
    assert "$+3.00" in card                # real-money era net, paper excluded
    assert "$+10.77" not in card           # never blended
    assert "paper (sim)" in card and "$+7.77" in card  # sims on their own row
    assert "excluded" not in card.lower()  # historical real row kept
    assert "2 total" in card               # real trade count excludes the sim


def test_paper_main_gated_card(tmp_path, monkeypatch):
    """main_gated view inherits PAPER and applies the same real/paper split."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    card = wd._build_signal_card(
        "main_gated", "MAIN GATED",
        {"closed_trades": _main_trades(wd), "positions": {}},
        wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "PAPER (sim fills)" in card and "LIVE" not in card
    assert "view of MAIN PATH" in card
    assert "$+3.00" in card                # net PnL = real rows only
    assert "$+10.77" not in card
    assert "paper (sim)" in card and "$+7.77" in card
    assert "excluded" not in card.lower()


def test_no_sentinel_card_regression(tmp_path, monkeypatch):
    """Sentinel absent + no mode-tagged rows => card identical to today:
    LIVE badge, no paper row, full count, nothing honest-dropped."""
    wd = _wd(tmp_path, monkeypatch, sentinel=False)
    FIX = wd.PAPER_HONEST_TS
    trades = [{"opened_at": FIX - 50000, "pnl_usdt": 1.00, "side": "short"},
              {"opened_at": FIX + 1000, "pnl_usdt": 2.00, "side": "short"}]
    card = wd._build_signal_card(
        "5m_scalp", "MAIN", {"closed_trades": trades, "positions": {}},
        wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "LIVE" in card and "PAPER" not in card
    assert "2 total" in card
    assert "paper (sim)" not in card
    assert "excluded" not in card.lower()


def test_historical_no_mode_rows_never_dropped(tmp_path, monkeypatch):
    """REGRESSION (2026-08-12 leak class): main-book rows without a mode
    field are real money and must never be dropped by the PAPER_HONEST_TS
    cutoff — in BOTH sentinel states, on BOTH main cards."""
    import web_dashboard as wd
    monkeypatch.setattr(wd, "PROJECT_DIR", str(tmp_path))
    FIX = wd.PAPER_HONEST_TS
    trades = [{"opened_at": FIX - 90000, "pnl_usdt": 1.00},
              {"opened_at": FIX - 80000, "pnl_usdt": -0.40}]
    for sentinel in (False, True):
        if sentinel:
            (tmp_path / ".paper_main").touch()
        for sid in ("5m_scalp", "main_gated"):
            card = wd._build_signal_card(
                sid, "X", {"closed_trades": trades, "positions": {}},
                wd._live_slot_ids(), wd._slot_modes(), None, "")
            assert "excluded" not in card.lower(), (sid, sentinel)
            assert ("2 total" in card
                    or "trades</td><td>2" in card), (sid, sentinel)


def test_guardrails_paper_main_row(tmp_path, monkeypatch):
    """SLOTS+GUARDRAILS with the sentinel: main shows a PAPER row with its
    real record kept separate from the sim stats row."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    FIX = wd.PAPER_HONEST_TS
    real = [{"pnl_usdt": 1.00}, {"pnl_usdt": -2.00}]
    sims = [{"opened_at": FIX + 1000, "pnl_usdt": 0.40, "mode": "paper"}]
    panel = wd._build_slots_guardrails(
        {"5m_scalp": {"closed_trades": real + sims}})
    assert "PAPER" in panel and "LIVE" not in panel
    assert "real 2t" in panel              # real record on its own row
    assert "$-1.00" in panel               # real net (paper excluded)
    assert "$+0.40" in panel               # sim row net
    assert "$-0.60" not in panel           # never blended


def test_paper_main_never_renders_killed(tmp_path, monkeypatch):
    """REGRESSION guard: with 5m_scalp out of the live set, the lifetime-
    negative main ledger must NOT fall through to the generic negative-Kelly
    'killed' tombstone branch."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    trades = ([{"pnl_usdt": 0.5, "net_pnl": 0.5} for _ in range(10)]
              + [{"pnl_usdt": -1.0, "net_pnl": -1.0} for _ in range(45)])
    panel = wd._build_slots_guardrails({"5m_scalp": {"closed_trades": trades}})
    assert "killed" not in panel.lower()
    assert "PAPER" in panel


def test_guardrails_no_sentinel_regression(tmp_path, monkeypatch):
    """Sentinel absent => guardrails panel unchanged: main renders LIVE with
    its full (no-mode) record."""
    wd = _wd(tmp_path, monkeypatch, sentinel=False)
    real = [{"pnl_usdt": 1.00}, {"pnl_usdt": -2.00}]
    panel = wd._build_slots_guardrails({"5m_scalp": {"closed_trades": real}})
    assert "LIVE" in panel
    assert "2t" in panel and "$-1.00" in panel


def test_blotter_main_paper_rows_tagged_paper():
    """Blotter: main no-mode rows stay live/real (never stale); main
    mode='paper' rows render as sims (and are post-cutoff, so not stale)."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    slot_states = {"5m_scalp": {"closed_trades": [
        {"opened_at": FIX - 1000, "closed_at": FIX - 900, "pnl_usdt": 1.0,
         "symbol": "BTC/USDT:USDT", "side": "long", "strategy": "main"},
        {"opened_at": FIX + 2000, "closed_at": FIX + 2100, "pnl_usdt": 0.5,
         "symbol": "SOL/USDT:USDT", "side": "short", "strategy": "main",
         "mode": "paper"},
    ]}}
    rows = wd.collect_blotter_rows(100, slot_states)
    by_sym = {r["sym"]: r for r in rows}
    assert by_sym["BTC"]["mode"] == "live" and not by_sym["BTC"]["stale"]
    assert by_sym["SOL"]["mode"] == "paper" and not by_sym["SOL"]["stale"]


def test_equity_curve_excludes_main_paper(monkeypatch):
    """The equity curve is REAL MONEY only: main mode='paper' rows never
    plot; no-mode rows stay on the curve."""
    import web_dashboard as wd
    real = {"opened_at": 1786500000, "closed_at": 1786500100, "pnl_usdt": 1.25,
            "symbol": "BTC/USDT:USDT", "side": "long"}
    sim = {"opened_at": 1786500200, "closed_at": 1786500300, "pnl_usdt": 9.99,
           "symbol": "ETH/USDT:USDT", "side": "long", "mode": "paper"}
    monkeypatch.setattr(wd, "read_state",
                        lambda: {"closed_trades": [real, sim]})
    monkeypatch.setattr(wd, "read_all_slot_states", lambda: {})
    data = wd.build_equity_series("all")
    assert [m["pnl"] for m in data["meta"]] == [1.25]


def test_today_pnl_excludes_main_paper(monkeypatch):
    """Ticker today-PnL sits next to the real balance: main mode='paper'
    sims never count."""
    import web_dashboard as wd
    now = time.time()
    state = {"closed_trades": [
        {"closed_at": now, "pnl_usdt": 1.25},
        {"closed_at": now, "pnl_usdt": 9.99, "mode": "paper"},
    ]}
    monkeypatch.setattr(wd, "read_all_slot_states", lambda: {})
    assert abs(wd._today_net_pnl(state) - 1.25) < 1e-9


def test_size_row_paper_label(tmp_path, monkeypatch):
    """Size row on main cards: sentinel present => labeled paper sim sizing
    (nobody reads it as money at risk); absent => today's real-sizing row."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    row = wd._size_row_html("5m_scalp", wd._live_slot_ids())
    assert "PAPER" in row and "no money at risk" in row
    (tmp_path / ".paper_main").unlink()
    row = wd._size_row_html("5m_scalp", wd._live_slot_ids())
    assert "PAPER" not in row and "margin/trade" in row


def test_positions_panel_labels_paper_main_position(tmp_path, monkeypatch):
    """Main positions stay visible while on paper, labeled by the POSITION's
    own paper tag (never by the sentinel)."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    slot_states = {"5m_scalp": {
        "positions": {"BTC/USDT:USDT": {
            "side": "long", "entry_price": 50000.0, "amount": 0.001,
            "opened_at": 1786500000, "paper": True,
            "strategy": "htf_l2_anticipation"}},
        "closed_trades": []}}
    panel = wd._build_positions_panel(lines=[], slot_states=slot_states)
    assert "main (PAPER)" in panel
    # untagged position in the same state (opened before the cut) stays "main"
    slot_states["5m_scalp"]["positions"]["ETH/USDT:USDT"] = {
        "side": "short", "entry_price": 3000.0, "amount": 0.01,
        "opened_at": 1786500000, "strategy": "htf_l2_anticipation"}
    panel = wd._build_positions_panel(lines=[], slot_states=slot_states)
    assert "main (PAPER)" in panel and ">main</td>" in panel


def test_open_pos_count_excludes_paper_positions(tmp_path, monkeypatch):
    """Ticker POS = real exposure only: paper-tagged main positions never
    count (untagged rows always do — sentinel-independent)."""
    wd = _wd(tmp_path, monkeypatch, sentinel=True)
    state = {"positions": {"BTC/USDT:USDT": {"paper": True},
                           "ETH/USDT:USDT": {}}}
    assert wd._open_pos_count(state, {}) == 1
