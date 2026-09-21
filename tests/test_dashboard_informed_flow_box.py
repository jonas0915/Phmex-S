"""Dashboard surfaces for the informed_flow_btc_alt_cascade_v2 paper slot
(2026-09-20 build). Project rule (CLAUDE.md): every bot update propagates to
the dashboard — the STRATEGIES card list (_SIGNAL_BOXES) is hand-maintained
(2026-09-08 Donchian regression), so the new slot is pinned here the same way
tests/test_dashboard_donchian_boxes.py pins its siblings.

Fixture-only: no bot import, no network, no state file in the project dir
(tmp_path stands in for PROJECT_DIR)."""
import json
import os

import pytest

import web_dashboard as wd

SLOT = "informed_flow_btc_alt_cascade_v2"
PREREG = "docs/superpowers/specs/2026-09-20-informed_flow_btc_alt_cascade_v2-prereg.md"
REG_TS = 1789933835  # adjudicate.EXPERIMENTS[SLOT]["registered_ts"]


def _fixture_state():
    """Two closed paper trades (risk_manager paper close shape: no mode key,
    net_pnl fee-inclusive) + one open short, all after registered_ts and the
    8/5 honest-price cutoff."""
    t0 = REG_TS + 3600
    return {
        "peak_balance": 0,
        "closed_trades": [
            {"symbol": "DOGE/USDT:USDT", "side": "short", "entry_price": 0.10,
             "exit_price": 0.0975, "pnl_usdt": 5.0, "fees_usdt": 0.24,
             "funding_usdt": 0.0, "net_pnl": 4.76, "reason": "take_profit",
             "exit_reason": "take_profit", "strategy": SLOT,
             "opened_at": t0, "closed_at": t0 + 3 * 3600, "margin": 200.0},
            {"symbol": "XRP/USDT:USDT", "side": "short", "entry_price": 0.50,
             "exit_price": 0.5075, "pnl_usdt": -3.0, "fees_usdt": 0.24,
             "funding_usdt": 0.0, "net_pnl": -3.24, "reason": "stop_loss",
             "exit_reason": "stop_loss", "strategy": SLOT,
             "opened_at": t0 + 7200, "closed_at": t0 + 4 * 3600, "margin": 200.0},
        ],
        "positions": {
            "LINK/USDT:USDT": {"side": "short", "entry_price": 12.0, "amount": 16.667,
                               "margin": 200.0, "stop_loss": 12.18, "take_profit": 11.7,
                               "opened_at": t0 + 5 * 3600, "strategy": SLOT},
        },
    }


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Point the dashboard at an empty project dir holding only the new slot's
    state file — nothing else on disk, so the render is the fixture alone."""
    (tmp_path / f"trading_state_{SLOT}.json").write_text(json.dumps(_fixture_state()))
    (tmp_path / "trading_state.json").write_text(json.dumps({"peak_balance": 0, "closed_trades": []}))
    monkeypatch.setattr(wd, "PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(wd, "STATE_FILE", str(tmp_path / "trading_state.json"))
    return tmp_path


# ── STRATEGIES card registration (hand-maintained list) ──────────────────────

def test_slot_is_a_registered_signal_box():
    ids = [slot_id for slot_id, _t, _d in wd._SIGNAL_BOXES]
    assert SLOT in ids


def test_signal_box_title_and_desc_carry_the_frozen_facts():
    boxes = {b[0]: (b[1], b[2]) for b in wd._SIGNAL_BOXES}
    title, desc = boxes[SLOT]
    assert "LAGGARD" in title.upper() and "PAPER" in title.upper()
    # plain-English mechanism + frozen geometry
    assert "150 bps" in desc and "50%" in desc
    assert "TP 250" in desc and "SL 150" in desc
    assert "max hold 7h" in desc and "16 alts" in desc
    # BTC reference-feed note (owner decision 2026-09-20)
    assert "BTC" in desc and "1h" in desc
    # frozen verdict line, prereg path, holdout record
    assert "n&ge;50" in desc or "n>=50" in desc
    assert "$10" in desc and "n=100" in desc
    assert "CI lower" in desc.lower() or "ci95 lower" in desc.lower()
    assert PREREG in desc
    assert "+59.2 bps" in desc and "[+21.0, +98.2]" in desc


def test_signals_section_renders_the_card_from_a_fixture_state(project_dir):
    html = wd._build_signals_section()          # reads the tmp project dir
    assert f'id="sig-{SLOT}"' in html
    card = html.split(f'id="sig-{SLOT}"', 1)[1].split('<div class="panel sig-box"', 1)[0]
    assert "PAPER" in card                       # status badge (no mode sidecar → paper)
    assert "trades</td><td>2" in card            # both closed trades counted
    assert "1W" in card and "1L" in card
    assert "$+1.52" in card                      # 4.76 − 3.24, net_pnl as-is (no fee re-subtract)
    assert "LINK short @ 12" in card             # open paper position on the card


def test_slots_guardrails_panel_lists_the_slot_as_paper(project_dir):
    html = wd._build_slots_guardrails()
    row = html.split(SLOT, 1)[1].split("</tr>", 1)[0]
    assert "paper" in row
    assert "2t" in row and "50%" in row and "$+1.52" in row


def test_read_all_slot_states_discovers_the_state_file_generically(project_dir):
    states = wd.read_all_slot_states()
    assert SLOT in states
    assert len(states[SLOT]["closed_trades"]) == 2
    # the slot's own sidecars are NOT trading_state_* files — never phantom slots
    assert not any(k.startswith(SLOT + "_") for k in states)


# ── blotter / positions strategy label ───────────────────────────────────────

def test_strategy_tag_has_a_readable_chip_label_and_tooltip():
    label, tip = wd._strat_display(SLOT)
    assert label != SLOT                         # raw id truncates to 16 chars in the chip
    assert len(label) <= 16
    assert "laggard" in label.lower()
    assert "TP 250" in tip and "SL 150" in tip and PREREG in tip


def test_blotter_rows_carry_the_slot_as_owner(project_dir):
    rows = wd.collect_blotter_rows(50)
    ours = [r for r in rows if r["owner"] == SLOT]
    assert len(ours) == 2
    assert {r["strat"] for r in ours} == {SLOT}
    assert all(r["mode"] != "live" for r in ours)   # paper book — never a live row
    html = wd._build_blotter_panel(50)
    assert f'data-strat="{SLOT}"' in html
