"""Dashboard v2 "Terminal Pro" shell tests (Task 1)."""
import re
import sys

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")


def test_shell_structure():
    import web_dashboard as wd
    html = wd.build_html()
    # chart node must live OUTSIDE the swapped #content div
    content_pos = html.index('id="content"')
    equity_pos = html.index('id="equity-root"')
    assert equity_pos > html.index("<body")
    content_div = re.search(r'<div id="content".*?</div>\s*<!-- /content -->', html, re.S)
    assert content_div is not None
    assert 'id="equity-root"' not in content_div.group(0)
    # terminal palette present, old palette gone
    assert "#000204" in html and "#f0a500" in html
    assert "fonts.googleapis.com" not in html


def test_ticker_present():
    import web_dashboard as wd
    c = wd.build_content()
    assert 'class="ticker"' in c or 'id="ticker"' in wd.build_html()


def test_equity_endpoint_shape(tmp_path, monkeypatch):
    import web_dashboard as wd
    data = wd.build_equity_series("all")
    assert set(data.keys()) == {"t", "v", "meta"}
    assert len(data["t"]) == len(data["v"]) == len(data["meta"])
    if data["meta"]:
        m = data["meta"][0]
        assert {"sym", "strat", "pnl", "reason", "win"} <= set(m.keys())


def test_equity_sentinel_era_subset():
    import web_dashboard as wd
    a = wd.build_equity_series("all"); s = wd.build_equity_series("sentinel")
    assert len(s["t"]) <= len(a["t"])


def test_merged_blotter_rows():
    import web_dashboard as wd
    rows = wd.collect_blotter_rows(limit=500)
    assert isinstance(rows, list)
    if rows:
        r = rows[0]
        assert {"id", "time_pt", "sym", "side", "strat", "net", "reason", "owner"} <= set(r.keys())
        ts = [x["ts"] for x in rows]
        assert ts == sorted(ts, reverse=True)  # newest first


def test_trade_detail_endpoint():
    import web_dashboard as wd
    rows = wd.collect_blotter_rows(limit=5)
    if rows:
        d = wd.build_trade_detail(rows[0]["id"])
        assert "snapshot" in d  # dict or the string "no snapshot recorded"


def test_trade_detail_resolves_dotted_slot_id(tmp_path, monkeypatch):
    # Slot ids can contain a dot (live example: "ST2.0"). The blotter id is
    # "owner:index", so the drill-down must resolve "ST2.0:0". Regression: the
    # owner-validation regex used to reject the dot, so EVERY ST2.0 trade detail
    # returned {"error": "not found"} (and the flaky endpoint test failed whenever
    # the newest blotter row was an ST2.0 trade).
    import json
    import web_dashboard as wd
    state = {"closed_trades": [{"symbol": "ETH/USDT:USDT", "side": "short",
             "strategy": "ST2.0", "entry_snapshot": {"ob": {"imbalance": 0.4}}}]}
    (tmp_path / "trading_state_ST2.0.json").write_text(json.dumps(state))
    monkeypatch.setattr(wd, "PROJECT_DIR", str(tmp_path))
    d = wd.build_trade_detail("ST2.0:0")
    assert "error" not in d
    assert "snapshot" in d
    assert d["trade"]["owner"] == "ST2.0"


def test_trade_detail_rejects_path_traversal_owner():
    # owner is interpolated into a filename — a slash / traversal must stay rejected
    # even though the dot is now an allowed owner character.
    import web_dashboard as wd
    assert wd.build_trade_detail("../secret:0") == {"error": "not found"}
    assert wd.build_trade_detail("a/b:0") == {"error": "not found"}


SAMPLE_LOG = """
2026-06-12 09:52:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.3)
2026-06-12 09:52:09 [DEBUG] [STRAT] l2_anticipation: 1h ADX 23.2 < 25
2026-06-12 09:52:09 [DEBUG] [HOLD] INJ/USDT:USDT — No confluence signal (1h ADX=23.2)
2026-06-12 09:53:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.9)
"""


def test_parse_pair_adx():
    import web_dashboard as wd
    adx = wd.parse_pair_adx(SAMPLE_LOG.strip().splitlines())
    assert adx["ZEC/USDT:USDT"] == 15.9     # newest wins
    assert adx["INJ/USDT:USDT"] == 23.2
    assert "DOGE/USDT:USDT" not in adx      # absent pair stays absent — never guess


def test_guardrail_panel_math(tmp_path, monkeypatch):
    import web_dashboard as wd
    html = wd._build_slots_guardrails()
    assert "SLOTS" in html.upper()
    # if 5m_mean_revert is live, headroom string present
    import json, os
    mode = os.path.join(wd.PROJECT_DIR, "trading_state_5m_mean_revert_mode.json")
    if os.path.exists(mode) and not json.load(open(mode)).get("paper_mode", True):
        assert "headroom" in html.lower() or "HDRM" in html


def test_sentinel_deploy_ts_matches_2026_04_02_06_01_utc():
    """Sentinel deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC.
    (Moved from test_sentinel_chart.py — the PNG chart is gone, but this
    constant is now the era cutoff for /api/equity?era=sentinel.)"""
    from datetime import datetime, timezone
    import web_dashboard as wd
    expected = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
    assert wd.SENTINEL_DEPLOY_TS == expected


def test_htf_l2_signal_box_present():
    """HTF_L2 slot (2026-07-18, renamed from HTF_L2_PAPER at the 7/20 go-live)
    must surface on the dashboard (project rule: every bot update propagates
    to Telegram AND dashboard). The box maps
    slot_id -> trading_state_HTF_L2.json via the generic signal-card
    loop, and its title must stay distinct from the legacy main-path htf_l2 box."""
    import web_dashboard as wd
    boxes = {b[0]: b[1] for b in wd._SIGNAL_BOXES}
    assert "HTF_L2" in boxes
    # Retitled 2026-07-31 after the permanent owner kill (was "SLOT (PAPER)")
    assert "KILLED" in boxes["HTF_L2"]
    assert boxes["HTF_L2"] != boxes["5m_scalp"]   # main-live box untouched
    # Retitled 2026-07-28: main path is LIVE again (un-halted 7/21, $5 gated era)
    assert "FULL HISTORY" in boxes["5m_scalp"]


def test_main_path_status_halted(tmp_path, monkeypatch):
    """5m_scalp badge must show HALTED while .halt_main_entries exists —
    the process being alive must not render the halted main book as LIVE."""
    import web_dashboard as wd
    monkeypatch.setattr(wd, "PROJECT_DIR", str(tmp_path))
    (tmp_path / ".halt_main_entries").touch()
    html = wd._slot_status_html("5m_scalp", [], {"5m_scalp"}, {})
    assert "HALTED" in html and "LIVE" not in html
    (tmp_path / ".halt_main_entries").unlink()
    html = wd._slot_status_html("5m_scalp", [], {"5m_scalp"}, {})
    assert "LIVE" in html


def test_sr_bounce_signal_box_present():
    """SR_BOUNCE (Task 5, 2026-07-28): the scan's backtest kill-gate said
    DO-NOT-BUILD, but the owner ordered a paper forward test anyway to
    measure real fill selection. The box must be a live-capable card
    (generic _build_signal_card, reading trading_state_SR_BOUNCE.json via
    read_all_slot_states), not the old pre-build tombstone."""
    import web_dashboard as wd
    boxes = {b[0]: b[1] for b in wd._SIGNAL_BOXES}
    assert "SR_BOUNCE" in boxes
    # v2 fixed-geometry era (2026-07-30): card title updated with the re-arm.
    assert "FIXED GEOMETRY" in boxes["SR_BOUNCE"]


def test_sr_bounce_tombstone_branch_removed():
    """The static KILLED-PRE-BUILD tombstone branch must be gone from the
    render loop — SR_BOUNCE now goes through the same generic
    _build_signal_card path as every other slot."""
    import inspect
    import web_dashboard as wd
    src = inspect.getsource(wd._build_signals_section)
    assert "SR_BOUNCE" not in src
    assert "KILLED PRE-BUILD" not in src


def test_sr_bounce_missing_state_renders_zero_trades():
    """With no trading_state_SR_BOUNCE.json on disk, the generic card must
    render an n=0 PAPER card (not crash, not fall back to the old tombstone)."""
    import web_dashboard as wd
    slot_states = {}  # no SR_BOUNCE key, mirrors a missing state file
    live_ids = wd._live_slot_ids()
    modes = wd._slot_modes()
    state = slot_states.get("SR_BOUNCE") or {"closed_trades": [], "positions": {}}
    card = wd._build_signal_card("SR_BOUNCE", "SR_BOUNCE", state, live_ids, modes, None, "")
    assert ">0<" in card or "trades</td><td>0" in card


def test_sr_bounce_honest_only():
    """SR_BOUNCE card (2026-08-12, owner order): pre-8/5 paper rows were
    flattered by the stale cached-price phantom-entry bug (fixed 2026-08-05
    9:47 PM PT, PID 27868). The card shows ONLY honest-era stats (opened_at
    >= wd.PAPER_HONEST_TS). Pre-fix rows get no stats — just a dim
    excluded-count so the card still reconciles with the n=50 verdict line,
    which counts every v2 trade. Zero-TP tell stays visible in exit mix."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [
        # pre-fix: flattered winner — must contribute NOTHING to shown stats
        {"opened_at": FIX - 1000, "pnl_usdt": 4.00, "exit_reason": "take_profit"},
        # honest era: time-exit winner + SL loser, zero TPs
        {"opened_at": FIX + 1000, "pnl_usdt": 1.00, "exit_reason": "hard_time_exit"},
        {"opened_at": FIX + 2000, "pnl_usdt": -0.50, "exit_reason": "stop_loss"},
    ]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("SR_BOUNCE", "SR_BOUNCE", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    # honest stats only: 1W/1L, +$0.50 net
    assert "honest" in card.lower()
    assert "$+0.50" in card
    # pre-fix PnL/WR must NOT appear anywhere — only an excluded row count
    assert "$+4.00" not in card
    assert "excluded" in card.lower()
    assert "1 " in card and "stale" in card.lower()
    # exit-mix line with the zero-TP tell (honest era only)
    assert "0 TP" in card
    assert "1 time" in card and "1 SL" in card


def test_sr_bounce_honest_only_all_prefix_rows():
    """All-pre-fix book (or missing opened_at → treated pre-fix): honest era
    renders n=0 without crashing (division-by-zero guard) and shows no
    pre-fix PnL."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [{"opened_at": FIX - 5000, "pnl_usdt": 2.00, "exit_reason": "take_profit"},
              {"pnl_usdt": 1.00, "exit_reason": "take_profit"}]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("SR_BOUNCE", "SR_BOUNCE", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "honest" in card.lower()
    assert "$+3.00" not in card and "$+2.00" not in card
    assert "excluded" in card.lower()


def test_generic_paper_card_excludes_stale_rows():
    """ALL paper cards (owner order 2026-08-12 'FIX IT ALL'): pre-8/5 paper
    rows are stale-price flattered on every paper book, not just SR_BOUNCE.
    Generic-branch cards must show honest-era stats only + an excluded count."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [
        {"opened_at": FIX - 1000, "pnl_usdt": 7.77, "exit_reason": "take_profit"},
        {"opened_at": FIX + 1000, "pnl_usdt": 1.00, "exit_reason": "take_profit"},
        {"opened_at": FIX + 2000, "pnl_usdt": -0.25, "exit_reason": "stop_loss"},
    ]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("DONCHIAN_BTC", "DONCHIAN BTC", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "$+7.77" not in card and "7.77" not in card
    assert "$+0.75" in card          # honest net only
    assert "excluded" in card.lower()
    assert "1W" in card and "1L" in card


def test_mixed_card_keeps_prefix_live_rows():
    """Live-mode rows are real fills — NEVER excluded, whatever their date.
    Only paper sims opened pre-fix drop out of the shown stats."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [
        {"opened_at": FIX - 9000, "pnl_usdt": 2.00, "mode": "live"},   # real, kept
        {"opened_at": FIX - 1000, "pnl_usdt": 5.55},                   # stale sim, dropped
        {"opened_at": FIX + 1000, "pnl_usdt": -1.00},                  # honest sim, kept
    ]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("HTF_L2", "HTF_L2", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "$+2.00" in card          # live net intact
    assert "5.55" not in card        # stale sim gone
    assert "$-1.00" in card          # honest paper net
    assert "excluded" in card.lower()


def test_main_book_card_never_filtered():
    """5m_scalp = the main book: every row is real money (no mode field).
    The honest-paper filter must not touch it — old rows all still counted."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [{"opened_at": FIX - 50000, "pnl_usdt": 1.00},
              {"opened_at": FIX + 1000, "pnl_usdt": 1.00}]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("5m_scalp", "MAIN", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "2 total" in card
    assert "excluded" not in card.lower()


def test_guardrails_sim_stats_exclude_stale():
    """SLOTS+GUARDRAILS panel: sim stat lines exclude pre-fix paper rows and
    carry a stale-excluded note; the honest sim record is what renders."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    slot_states = {"TESTSLOT_HONEST": {"closed_trades": [
        {"opened_at": FIX - 1000, "pnl_usdt": 9.99},
        {"opened_at": FIX + 1000, "pnl_usdt": 0.40},
    ], "positions": {}}}
    html = wd._build_slots_guardrails(slot_states)
    assert "9.99" not in html
    assert "$+0.40" in html
    assert "stale" in html.lower()


def test_blotter_rows_tag_stale_paper():
    """Blotter: pre-fix paper rows carry stale=True (rendered as a stale sim
    mode cell + excluded from chip win rates); live and post-fix rows don't."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    slot_states = {
        "5m_scalp": {"closed_trades": [
            {"opened_at": FIX - 1000, "closed_at": FIX - 900, "pnl_usdt": 1.0,
             "symbol": "BTC/USDT:USDT", "side": "long", "strategy": "main"}]},
        "TESTSLOT": {"closed_trades": [
            {"opened_at": FIX - 1000, "closed_at": FIX - 900, "pnl_usdt": 2.0,
             "symbol": "ETH/USDT:USDT", "side": "long", "strategy": "t"},
            {"opened_at": FIX + 1000, "closed_at": FIX + 1100, "pnl_usdt": 3.0,
             "symbol": "SOL/USDT:USDT", "side": "long", "strategy": "t"}]},
    }
    rows = wd.collect_blotter_rows(100, slot_states)
    by_sym = {r["sym"]: r for r in rows}
    assert not by_sym["BTC"]["stale"]     # main book row: real, never stale
    assert by_sym["ETH"]["stale"]         # pre-fix paper sim
    assert not by_sym["SOL"]["stale"]     # honest-era paper sim
    panel = wd._build_blotter_panel(100, slot_states)
    assert "stale" in panel.lower()


def test_main_gated_view_never_filtered():
    """main_gated is a filtered VIEW of the main book — real money, no mode
    field. Regression 2026-08-12: the honest-paper filter wrongly dropped 34
    real pre-8/5 trades from the CURRENT TEST card on first deploy."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [{"opened_at": FIX - 50000, "pnl_usdt": 1.00},
              {"opened_at": FIX + 1000, "pnl_usdt": -0.40}]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("main_gated", "MAIN GATED", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "excluded" not in card.lower()
    assert ">2<" in card or "trades</td><td>2" in card


def test_main_card_side_split_rows():
    """Owner split order 2026-08-12: main-book cards show the long and short
    half-books as separate rows (real money, per-side W/L + net)."""
    import web_dashboard as wd
    trades = [
        {"opened_at": 1786000000, "pnl_usdt": -1.00, "side": "long"},
        {"opened_at": 1786000100, "pnl_usdt": -2.00, "side": "long"},
        {"opened_at": 1786000200, "pnl_usdt": 1.50, "side": "short"},
    ]
    card = wd._build_signal_card("5m_scalp", "MAIN", {"closed_trades": trades,
                                 "positions": {}}, set(), {}, None, "")
    assert "longs" in card and "shorts" in card
    assert "$-3.00" in card    # long half-book net
    assert "$+1.50" in card    # short half-book net


def test_mr_card_live_side_split_rows():
    """Mixed live/paper cards (5m_MR): the LIVE record splits by side; paper
    sims stay a single aggregate row."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [
        {"opened_at": FIX + 10, "pnl_usdt": 2.00, "mode": "live", "side": "short"},
        {"opened_at": FIX + 20, "pnl_usdt": -0.75, "mode": "live", "side": "long"},
        {"opened_at": FIX + 30, "pnl_usdt": 0.30},   # paper sim
    ]
    card = wd._build_signal_card("5m_mean_revert", "MR", {"closed_trades": trades,
                                 "positions": {}}, set(), {}, None, "")
    assert "longs" in card and "shorts" in card
    assert "$+2.00" in card and "$-0.75" in card


def test_all_live_slot_book_gets_side_rows():
    """Regression 2026-08-12: once the honest filter drops every stale paper
    row, 5m_MR's remaining book is ALL live-mode → generic branch. The live
    side split must render there too, not only in the mixed branch."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [
        {"opened_at": FIX + 10, "pnl_usdt": 3.00, "mode": "live", "side": "short"},
        {"opened_at": FIX + 20, "pnl_usdt": -1.00, "mode": "live", "side": "long"},
    ]
    card = wd._build_signal_card("5m_mean_revert", "MR", {"closed_trades": trades,
                                 "positions": {}}, set(), {}, None, "")
    assert "longs" in card and "shorts" in card
    assert "$+3.00" in card and "$-1.00" in card


def test_crumb_rows_excluded_from_card_stats():
    """min_margin_skip rows are bookkeeping crumbs, not trades (owner order
    2026-08-25): they never count toward a card's trade count or WR, and the
    card says how many were excluded."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    trades = [
        {"opened_at": FIX + 1000, "pnl_usdt": 2.00, "mode": "live", "side": "short"},
        {"opened_at": FIX + 2000, "pnl_usdt": -1.00, "mode": "live", "side": "short"},
        {"opened_at": FIX + 3000, "pnl_usdt": -0.10, "mode": "live", "side": "short",
         "exit_reason": "min_margin_skip"},
    ]
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("5m_mean_revert", "5M MR", state,
                                 wd._live_slot_ids(), wd._slot_modes(), None, "")
    assert "50% WR" in card                    # 1W/1L — crumb not a loss
    assert "1 crumb skips excluded" in card
    assert "$-0.10" not in card                # crumb PnL not rendered as a trade


def test_crumb_rows_excluded_from_guardrails_stats():
    """SLOTS+GUARDRAILS: displayed count/WR skip crumbs for every slot,
    main book included."""
    import web_dashboard as wd
    real = [{"pnl_usdt": 1.00}, {"pnl_usdt": -2.00}]
    crumb = [{"pnl_usdt": 0.0, "reason": "min_margin_skip"}]
    panel = wd._build_slots_guardrails(
        {"5m_scalp": {"closed_trades": real + crumb}})
    assert "2t" in panel and "3t" not in panel


def test_crumbs_do_not_flip_kill_badge():
    """Badge classification stays on the FULL ledger: a paper slot with 50
    rows where one is a crumb must still classify at n=50 (parity with
    strategy_slot.is_killed), not slip under the threshold."""
    import web_dashboard as wd
    FIX = wd.PAPER_HONEST_TS
    # 10 winning + 39 losing honest paper rows + 1 crumb = 50 ledger rows;
    # kelly = 0.2 - 0.8/0.5 < 0 (all-loss ledgers return 0.0 by parity)
    trades = ([{"opened_at": FIX + i, "pnl_usdt": 0.5, "net_pnl": 0.5}
               for i in range(10)]
              + [{"opened_at": FIX + 100 + i, "pnl_usdt": -1.0, "net_pnl": -1.0}
                 for i in range(39)])
    trades.append({"opened_at": FIX + 99, "pnl_usdt": 0.0,
                   "exit_reason": "min_margin_skip"})
    state = {"closed_trades": trades, "positions": {}}
    card = wd._build_signal_card("SOME_SLOT", "X", state, set(), {}, None, "")
    assert "KILLED" in card
