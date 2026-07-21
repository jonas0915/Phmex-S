import signal
import time
import datetime
import subprocess
import os
import json
import re
import threading
from collections import deque
from config import Config
from exchange import Exchange
from indicators import add_all_indicators
from risk_manager import RiskManager
from strategy_slot import StrategySlot
from strategies import STRATEGIES, Signal, TradeSignal, st2_absorption

# ST2.0 book×tape absorption short — fixed ~15-min hold (900s / 60s cycle = 15 cycles),
# matching the backtested exit (docs/2026-06-13-wider-setup-search.md).
ST2_HOLD_CYCLES = 15
# Per-slot hold overrides (cycles). ST2.0 holds ~20 min (1200s) since the 2026-06-16
# LIVE promotion (proposal 8df1250186dd); falls back to ST2_HOLD_CYCLES otherwise.
ST2_HOLD_CYCLES_BY_SLOT = {"ST2.0": 20}
# ETH-TSM-28 slow-horizon slot (2026-07-06 build). Signal math + frozen spec
# constants live in tsm_slot.py; bot.py only orchestrates (see _evaluate_eth_tsm).
import tsm_slot
from tsm_slot import (TSM_SLOT_ID, TSM_SYMBOL, TSM_AMOUNT_ETH, TSM_LEVERAGE,
                      TSM_STOP_PCT, TSM_OHLCV_LIMIT, TSM_TAKER_FALLBACK_S)
# Donchian-ensemble slots (2026-07-16 build). Signal math + frozen spec
# constants live in donchian_slot.py; bot.py only orchestrates (see
# _evaluate_donchian). Referenced via the module namespace — the constants are
# per-coin maps, not scalars like the TSM ones.
import donchian_slot
from scanner import scan_top_gainers, volatility_scan, start_background_scan, get_scan_result
from logger import setup_logger
from ws_feed import WSDataFeed
import notifier

logger = setup_logger()


_RSI_REASON_RE = re.compile(r"RSI\(7\)=([\d.]+)")


def _rsi_from_reason(reason) -> float | None:
    """RSI(7) value embedded in a signal reason string, or None if absent."""
    m = _RSI_REASON_RE.search(reason or "")
    return float(m.group(1)) if m else None


def _requote_drift_pct(direction: str, signal_price: float, touch: float) -> float:
    """Adverse drift (percent of signal price) of the current touch vs the
    signal price. Positive = price ran AWAY from the entry (worse fill for a
    re-quote); negative = price came back (better fill)."""
    raw = (touch - signal_price) / signal_price * 100
    return raw if direction == "long" else -raw


def _equity_for_drawdown(exchange_equity: float, free_plus_main_margin: float) -> float:
    """Equity value for drawdown/peak/daily-halt tracking. Prefer the EXCHANGE's
    own total equity (free + ALL used margin, whoever placed the order) — the
    old `free + main-bot margin_in_use` sum was blind to live SLOT positions'
    margin (risk.positions only tracks the main bot), reading equity $10-15 low
    whenever a slot held a live trade. That fired 9 false [DRAWDOWN] pauses
    June 23 - July 7, including the 2026-07-07 7:20 AM "32.1% - SEVERE" 1.5h
    block (true drawdown was 8%). Fall back to the old sum only when the equity
    cache is unset (get_equity returns 0.0 before the first successful fetch)."""
    return exchange_equity if exchange_equity > 0 else free_plus_main_margin


def _meets_min_strength(strength: float, minimum: float) -> bool:
    """Float-safe min-strength gate. The short penalty (0.84 - 0.04) and the
    additive strength ladders inside strategies produce IEEE-754 dust like
    0.7999999999999999 — which displays as 0.80 yet fails `< 0.80`. XLM lost
    11 boundary signals to this on 2026-07-07. Round to 4dp before comparing
    so dust can't flip the gate; a genuine 0.7999 still fails."""
    return round(strength, 4) >= minimum


def _extract_strategy_name(reason: str) -> str:
    """Derive strategy key from signal reason string for time exit lookup."""
    r = reason.lower()
    if "kc squeeze" in r or "keltner" in r:
        return "keltner_squeeze"
    if "bb" in r or "mean reversion" in r:
        return "bb_mean_reversion"
    if "trend pullback" in r:
        return "trend_pullback"
    if "trend scalp" in r or "trend_scalp" in r:
        return "trend_scalp"
    if "momentum cont" in r or "momentum_continuation" in r:
        return "momentum_continuation"
    if "vwap reversion" in r or "vwap_reversion" in r:
        return "vwap_reversion"
    if "vwap cross" in r:
        return "vwap_sma_cross"
    if "l2 anticipation" in r:
        return "htf_l2_anticipation"
    if "confluence pullback" in r:
        return "htf_confluence_pullback"
    if "confluence vwap" in r:
        return "htf_confluence_vwap"
    if "liq_cascade" in r:
        return "liq_cascade"
    return ""


def _compute_today_net_pnl(closed_trades: list) -> float:
    """Sum today's net_pnl (or pnl_usdt fallback). Uses America/Los_Angeles day boundary."""
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
    today_str = _dt.now(PT).strftime("%Y-%m-%d")
    total = 0.0
    for t in closed_trades:
        closed_at = t.get("closed_at")
        if not closed_at:
            continue
        if _dt.fromtimestamp(closed_at, tz=PT).strftime("%Y-%m-%d") != today_str:
            continue
        net = t.get("net_pnl")
        if net is None:
            net = t.get("pnl_usdt", 0.0)
        total += float(net or 0.0)
    return total


def _should_halt_daily_loss(today_net: float, balance: float, threshold_pct: float = 3.0,
                            floor_usdt: float = 5.0) -> bool:
    """Daily-loss kill switch: halt when today's net <= -max(threshold_pct% of
    balance, floor_usdt). The $5 floor (Jonas directive 2026-07-07) exists
    because at $15 margin one full SL (~-$2.05) exceeded 3% of a ~$60 balance
    (-$1.79) — a single normal stop was ending the whole trading day (r2
    research 2026-07-06 projected ~32% of days would trip). Floor lets ~2 full
    stops through; the percent branch takes over above ~$167 balance."""
    if balance <= 0:
        return False
    threshold = max(balance * threshold_pct / 100.0, floor_usdt)
    return today_net <= -threshold


def _should_halt_consecutive_losses(loss_streak: int, threshold: int = 5) -> bool:
    return loss_streak >= threshold


def _snap_val(row, col: str):
    """F7 snapshot helper: numeric value from an indicator row, None-safe."""
    try:
        if row is None:
            return None
        v = row.get(col)
        return round(float(v), 3) if v is not None else None
    except Exception:
        return None


def _snap_dist_pct(row, col: str, price: float):
    """F7 snapshot helper: signed % distance of price from the row's level
    (negative = price below level). None when the level is missing/zero."""
    try:
        if row is None:
            return None
        level = row.get(col)
        if not level:
            return None
        return round((float(price) - float(level)) / float(level) * 100, 4)
    except Exception:
        return None


def _first_wall_price(walls):
    """F7 snapshot helper: price of the first wall entry ([price, size] pair or
    dict), None when absent."""
    try:
        if not walls:
            return None
        w = walls[0]
        if isinstance(w, dict):
            return w.get("price")
        return float(w[0])
    except Exception:
        return None


def _daily_loss_override_active(path: str = ".daily_loss_override") -> bool:
    """True only on the PT calendar date written in the override file.

    Lets an operator authorize trading for the rest of a single day after the
    daily-loss kill switch has fired. Self-expires at PT midnight (the date in
    the file no longer matches), so every future day keeps the full daily-loss
    protection (max of -3% / -$5 floor) automatically. Reversible at any time
    by deleting the file.
    """
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            override_date = f.readline().strip()
    except OSError:
        return False
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    today_str = _dt.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    return override_date == today_str


def _pause_sentinel_is_daily_loss(path: str = ".pause_trading") -> bool:
    """True if the .pause_trading sentinel was written by the daily-loss kill switch.

    Used so the daily-loss override neutralizes ONLY a daily-loss pause — a manual
    Telegram /pause or a consecutive-loss halt (different reason text) is left alone.
    """
    try:
        with open(path) as f:
            f.readline()  # line 1: timestamp
            reason = f.readline().strip()  # line 2: reason
    except OSError:
        return False
    return reason.startswith("DAILY LOSS HALT")


def _underwater_positions(positions: dict, price_lookup) -> list:
    """[(symbol, drift_pct)] for open positions whose side-signed drift from
    entry is negative right now.

    Drives the concurrent-entry drift gate (r1 A.3, OOS-confirmed 2026-07-12:
    htf_l2 entries opened onto an underwater book ran 11% WR fresh vs 100% on a
    green book; gate costs ~14% of flow). price_lookup(sym) -> (price, age_s)
    or None; positions with missing or stale (>120s) prices are treated as NOT
    underwater — fail-open so a WS outage can't freeze entries.
    """
    out = []
    # list() snapshot — the live-exit watcher thread pops from this dict
    for sym, pos in list(positions.items()):
        try:
            lp = price_lookup(sym)
            if not lp:
                continue
            price, age_s = lp
            if age_s > 120 or not price or not getattr(pos, "entry_price", 0):
                continue
            drift = (price - pos.entry_price) / pos.entry_price
            if getattr(pos, "side", "long") == "short":
                drift = -drift
            if drift < 0:
                out.append((sym, drift * 100))
        except Exception:
            continue
    return out


def _tape_gate_blocks_buy_ratio(strat_name: str, direction: str, buy_ratio: float) -> bool:
    """Slot tape-gate buy_ratio check, with the bb_mean_reversion SHORT carve-out.

    Fading a buying frenzy IS the MR short thesis. Replay of all 25 tape-blocked
    MR signals (2026-07-12, validated sim): buy_ratio-blocked shorts n=10 +$6.19
    CI [+0.11, +1.08]; blocked longs were net NEGATIVE — so longs keep the gate.
    """
    if strat_name == "bb_mean_reversion" and direction == "short":
        return False
    if direction == "long" and buy_ratio < 0.45:
        return True
    if direction == "short" and buy_ratio > 0.55:
        return True
    return False


# ExpressVPN server rotation list — cycled through on each CDN ban
_VPN_SERVERS = [
    "usa-new-york",
    "usa-chicago",
    "usa-los-angeles-1",
    "usa-dallas",
    "usa-seattle",
    "usa-miami",
    "usa-atlanta",
    "usa-denver",
]
_vpn_index = 1  # start at 1 — index 0 (usa-new-york) is the default connect server


def _rotate_vpn() -> bool:
    """Disconnect and reconnect ExpressVPN to a new server. Returns True if connected."""
    global _vpn_index
    server = _VPN_SERVERS[_vpn_index % len(_VPN_SERVERS)]
    _vpn_index += 1
    logger.info(f"[VPN] Rotating to {server}...")
    try:
        subprocess.run(["expressvpnctl", "disconnect"], timeout=15, check=False)
        time.sleep(3)
        subprocess.run(["expressvpnctl", "connect", server], timeout=30, check=False)
        time.sleep(5)
        result = subprocess.run(["expressvpnctl", "status"], capture_output=True, text=True, timeout=10)
        status_line = result.stdout.splitlines()[0] if result.stdout else "status unknown"
        logger.info(f"[VPN] {status_line}")
        connected = "Connected" in status_line or "connected" in status_line
        if not connected:
            logger.warning(f"[VPN] Rotation to {server} may have failed — status: {status_line}")
        return connected
    except Exception as e:
        logger.warning(f"[VPN] Rotation failed: {e}")
        return False


def _diagnose_connectivity() -> dict:
    """Quick connectivity diagnosis: network reachable? VPN connected?"""
    diag = {"network": "unknown", "vpn": "unknown"}
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, timeout=5
        )
        diag["network"] = "ok" if result.returncode == 0 else "down"
    except Exception:
        diag["network"] = "down"
    try:
        result = subprocess.run(
            ["expressvpnctl", "status"],
            capture_output=True, text=True, timeout=5
        )
        status = result.stdout.strip() if result.stdout else ""
        if "Connected" in status or "connected" in status:
            diag["vpn"] = "connected"
        elif "Not connected" in status or "not connected" in status:
            diag["vpn"] = "disconnected"
        else:
            diag["vpn"] = status[:50] if status else "unknown"
    except Exception:
        diag["vpn"] = "unknown"
    return diag


def _check_htf_trend_flip_exit(side: str, htf_df) -> tuple[bool, str]:
    """Check if 1h EMA21/EMA50 has flipped against position direction.

    Returns (should_exit, reason). Used by htf_confluence_pullback positions only.
    """
    if htf_df is None or len(htf_df) == 0:
        return False, ""
    last = htf_df.iloc[-1]
    ema21 = last.get("ema_21")
    ema50 = last.get("ema_50")
    if ema21 is None or ema50 is None:
        return False, ""
    if side == "long" and ema21 < ema50:
        return True, "htf_trend_flip_exit"
    if side == "short" and ema21 > ema50:
        return True, "htf_trend_flip_exit"
    return False, ""


def _write_l2_snapshot(snapshot_dict: dict, path: str = "l2_snapshot.json") -> None:
    """Atomic write of L2 snapshot for dashboard. Silent on failure."""
    try:
        payload = {
            "updated_at": time.time(),
            "symbols": snapshot_dict,
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception as e:
        logger.debug(f"[L2_SNAPSHOT] write failed: {e}")


def _build_position_owners(main_risk, slots):
    """symbol -> (owner_risk_manager, slot_or_None) for every EXCHANGE-BACKED position.
    Main bot positions map to (main_risk, None); live-slot positions map to
    (slot.risk, slot). Paper slots are simulation-only and excluded.
    Used by _sync_exchange_closes so reconciliation is slot-aware."""
    owners = {s: (main_risk, None) for s in main_risk.positions}
    for slot in slots:
        if slot.paper_mode:
            continue
        for s in slot.risk.positions:
            if s not in owners:
                owners[s] = (slot.risk, slot)
            else:
                logger.warning(f"[SYNC] {s} held by both main bot and slot {slot.slot_id} — slot copy excluded from sync this cycle")
    return owners


# ── "Bot is blind" monitor ─────────────────────────────────────────────────
# Built 2026-07-06 after two silent DNS outages the same day (5:34–7:53 AM and
# 3:07–3:35 PM PT): WS feeds went stale, cycles stalled, the bot recovered on
# its own and nobody was told. Same failure family as the June host-sleep loss.
# Two detectors, both Telegram-only (no trading behavior changes):
#   1. WS-blind: ALL subscribed symbols' WS data stale for > BLIND_AFTER_S
#      → one [BLIND] alert, re-alerted at most once per REALERT_COOLDOWN_S,
#      with a [BLIND-CLEARED] message on recovery.
#   2. Cycle stall: gap between cycle starts > STALL_GAP_S → retroactive
#      [BLIND-RECOVERED] notice (covers host sleep / process freeze, where
#      the bot can only report after the fact).
# Pure state machine — `notify` is injected so tests run with no network.
class BlindMonitor:
    BLIND_AFTER_S = 300.0        # all feeds stale this long → blind
    REALERT_COOLDOWN_S = 3600.0  # at most one [BLIND] alert per hour
    STALL_GAP_S = 300.0          # cycle-start gap beyond this → stall notice

    def __init__(self, notify=None):
        self._notify = notify or notifier.send
        self.blind_since: float | None = None    # when all feeds first went stale
        self.blind_alerted = False               # [BLIND] sent for current episode
        self.last_blind_alert_ts = 0.0           # cooldown anchor (spans episodes)
        self.last_cycle_ts: float | None = None  # previous cycle start
        self.last_stall_notice_ts = 0.0          # [BLIND-RECOVERED] cooldown anchor

    @staticmethod
    def _fmt_pt(ts: float, with_date: bool = False) -> str:
        """12-hour PT string for a unix timestamp (never label raw local times PT)."""
        from zoneinfo import ZoneInfo
        dt = datetime.datetime.fromtimestamp(ts, tz=ZoneInfo("America/Los_Angeles"))
        return dt.strftime("%b %-d %-I:%M %p" if with_date else "%-I:%M %p")

    def _send(self, msg: str):
        logger.warning(f"[BLIND] {msg}")
        try:
            self._notify(msg)
        except Exception as e:
            logger.debug(f"[BLIND] notify failed: {e}")

    def check_cycle_gap(self, now: float) -> bool:
        """Call at every cycle start. Sends a retroactive [BLIND-RECOVERED]
        notice when the gap since the previous cycle start exceeds STALL_GAP_S
        (normal gap is ~60-180s: cycle + LOOP_INTERVAL sleep, watchdog-bounded).
        Returns True if the notice was sent."""
        prev, self.last_cycle_ts = self.last_cycle_ts, now
        if prev is None or (now - prev) <= self.STALL_GAP_S:
            return False
        # Debounce: a flapping link produces many separate >STALL_GAP_S stalls
        # back-to-back (2026-07-13 DNS flap sent four [BLIND-RECOVERED] in ~2h).
        # Collapse them — at most one recovery notice per REALERT_COOLDOWN_S, the
        # same window the WS-blind path uses. Baseline still updates every call.
        if (now - self.last_stall_notice_ts) < self.REALERT_COOLDOWN_S:
            return False
        from zoneinfo import ZoneInfo
        pt = ZoneInfo("America/Los_Angeles")
        cross_day = (datetime.datetime.fromtimestamp(prev, tz=pt).date()
                     != datetime.datetime.fromtimestamp(now, tz=pt).date())
        gap_min = (now - prev) / 60.0
        self._send(
            f"👁 <b>[BLIND-RECOVERED]</b>  [{notifier.BOT_NAME}]\n"
            f"Bot was stalled/blind {gap_min:.0f} min "
            f"({self._fmt_pt(prev, cross_day)}–{self._fmt_pt(now, cross_day)} PT), now resumed.\n"
            f"Entries were paused during the stall; exchange SL stayed armed."
        )
        self.last_stall_notice_ts = now
        return True

    def check_ws_blind(self, all_stale: bool, now: float) -> None:
        """Call every cycle with `all_stale` = every subscribed symbol's WS data
        is stale. Alerts once after BLIND_AFTER_S of continuous blindness, then
        at most once per REALERT_COOLDOWN_S (cooldown spans flapping episodes so
        an unstable link can't spam). Sends a clear message on recovery."""
        if not all_stale:
            if self.blind_alerted:
                blind_min = (now - self.blind_since) / 60.0 if self.blind_since else 0.0
                self._send(
                    f"✅ <b>[BLIND-CLEARED]</b>  [{notifier.BOT_NAME}]\n"
                    f"WS feeds fresh again as of {self._fmt_pt(now)} PT "
                    f"(was blind ~{blind_min:.0f} min). Entries re-enabled."
                )
            self.blind_since = None
            self.blind_alerted = False
            return
        if self.blind_since is None:
            self.blind_since = now
            return
        if (now - self.blind_since) < self.BLIND_AFTER_S:
            return
        if (now - self.last_blind_alert_ts) < self.REALERT_COOLDOWN_S:
            return
        self._send(
            f"👁 <b>[BLIND]</b>  [{notifier.BOT_NAME}]\n"
            f"All WS feeds stale since {self._fmt_pt(self.blind_since)} PT — "
            f"entries effectively paused, exchange SL still armed.\n"
            f"Likely network/DNS outage; will report recovery."
        )
        self.blind_alerted = True
        self.last_blind_alert_ts = now


class Phmex2Bot:
    def __init__(self):
        Config.validate()
        self.exchange = Exchange()
        self.risk = RiskManager()
        self.strategy_fn = STRATEGIES.get(Config.STRATEGY, STRATEGIES["confluence"])
        self.running = False
        self.cycle_count = 0
        self.active_pairs = Config.TRADING_PAIRS[:]
        self._leverage_set: set = set()  # track symbols that already have leverage configured
        self.consecutive_errors = 0
        self.ban_mode = False
        self.ban_mode_until = 0
        self.ban_extensions = 0
        self._ws_feed: WSDataFeed | None = None
        self._blind = BlindMonitor()  # "bot is blind" Telegram alerts (2026-07-06)
        self._empty_price_cycles = 0  # consecutive cycles with no ticker data (CDN ban detection)
        self._loss_streak = 0    # consecutive losses for streak-based sizing
        self._pair_cooldown: dict[str, float] = {}  # symbol -> timestamp when cooldown expires
        self._pair_loss_streak: dict[str, int] = {}  # symbol -> consecutive loss count
        self._last_entry_time: float = 0  # global cooldown between any new entry
        self._last_htf_entry_time: float = 0  # cluster throttle: 1 htf entry per 30 min
        self._trade_results: deque = deque(self.risk.trade_results, maxlen=5)  # rolling window of last 5 trade results (True=win, False=loss)
        self._regime_pause_until: float = 0  # timestamp when regime pause expires
        self._htf_cache: dict[str, tuple] = {}  # symbol -> (DataFrame, fetch_timestamp) for 1h candles
        self._funding_cache: dict[str, tuple] = {}  # symbol -> (data, fetch_timestamp) for funding rates
        self._divergence_cooldown: dict[str, dict] = {}  # symbol -> {"blocked_at": float, "clean_cycles": int}
        self._ob_depth_cache: dict[str, dict] = {}  # symbol -> depth data, populated by main loop, read by live writer thread
        # symbol -> (intended_reason, ts): set when a slot maker-exit fills but the
        # close races to a reduceOnly abort (the order never returns), so the next
        # [SYNC] reconcile can attribute the real reason (e.g. st2_hold) instead of
        # the generic exchange_close. Short-lived; consumed by _sync_exchange_closes.
        self._slot_pending_exit_reason: dict[str, tuple] = {}
        # Shadow adverse-exit: dedup state {(symbol, entry_cycle): set(thresholds logged)}
        # and the sidecar path. LOGGING ONLY — records what a deep-red loser-cut WOULD do
        # without changing live exits (which run at ADVERSE_EXIT_THRESHOLD=-999). The old
        # shadow lived inside should_adverse_exit() which never fires at -999, so it emitted
        # nothing; this records crossings independently (fixed 2026-06-19).
        self._shadow_ae_seen: dict = {}
        self._shadow_ae_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "logs", "shadow_adverse.jsonl")

        # Strategy slots framework — independent trading units (additive, main loop still uses self.risk)
        self.slots = [
            StrategySlot(
                # NOT an independent trader: live trading runs on self.risk (the main
                # loop), and "5m_scalp" is the LABEL the dashboard + entry snapshots
                # use for it (web_dashboard.py maps 5m_scalp -> trading_state.json).
                # max_positions/capital_pct here are dead config (audit 2026-06-11).
                slot_id="5m_scalp",
                strategy_name="confluence",
                timeframe="5m",
                max_positions=2,
                capital_pct=0.4,  # 40% of balance
            ),
            StrategySlot(
                slot_id="5m_mean_revert",
                strategy_name="bb_mean_reversion",
                timeframe="5m",
                max_positions=1,      # conservative — mean reversion is riskier
                capital_pct=0.3,      # 30% allocation (less than momentum/scalp)
                paper_mode=True,      # Paper mode first (promoted live via mode sidecar)
                requote_attempts=1,   # 2026-07-02: one maker re-quote on PostOnly miss
                                      # (fill rate was 2/13; misses were net winners —
                                      # reports/mr_missed_fills.json). Drift-capped.
                entry_patience_s=45.0,  # 2026-07-03: rest 45s not 20s — 9/11 missed
                                        # winners returned through the limit within 60s;
                                        # mean-reversion fills on the way back. Worst-case
                                        # stall (45s + 20s re-quote) is bounded to ONE
                                        # patient attempt per cycle (see _patient_missed),
                                        # keeping the cycle under the ~120s watchdog
                                        # budget (alarm(180) spans cycle + 60s sleep).
                durable_trail_enabled=True,  # 2026-06-24: ratchet the resting exchange SL up
                                             # as the trail arms (Config.TRAIL_ARM_ROI). Closes the gap that
                                             # let an XLM short round-trip +7% -> -14.2% with only
                                             # a static SL. OHLCV replay on live history: -$3.33
                                             # -> -$0.85 (rescues 4 losers, caps 1 winner). Per-slot.
            ),
            StrategySlot(
                slot_id="5m_liq_cascade",
                strategy_name="liq_cascade",
                timeframe="5m",
                max_positions=1,
                capital_pct=0.0,  # 0% for now — paper only
                paper_mode=True,
            ),
            # 5m_narrow — shadow slot that mirrors the live primary strategy but applies
            # three extra rejection filters (symbol blacklist, hour block, ensemble tightening).
            # Pure paper — never executes live orders. See strategy_slot.py:bump_blocked.
            StrategySlot(
                slot_id="5m_narrow",
                strategy_name="confluence",  # same primary strategy the live bot uses
                timeframe="5m",
                max_positions=2,
                capital_pct=0.0,
                paper_mode=True,
            ),
            # ST2.0 — book×tape absorption short. BOUNDED LIVE EXPERIMENT (2026-06-15):
            # measure REAL maker fills + feed real outcomes to scripts/st2_lab. Negative
            # out-of-sample as-is, so deliberately capped. Rails: max 2 positions, $5
            # margin/trade, auto-demote at -$10 total (budget) OR negative live Kelly @10
            # trades (strategy_slot.py). Runs the OOS-positive imb_min=0.35 (strategies.py).
            # Bypasses OB+tape gates by design; ~15 min hold. Rollback: `touch .demote_ST2.0`.
            StrategySlot(
                slot_id="ST2.0",
                strategy_name="ST2.0",
                timeframe="5m",
                max_positions=2,
                capital_pct=0.0,
                paper_mode=False,
                trade_amount_usdt=5.0,   # bounded live experiment: $5 margin/trade
                loss_cap_usdt=-10.0,     # hard budget: auto-demote at -$10 total net
                kelly_min_trades=40,     # let the -$10 budget govern; neg-Kelly arms at 40 (not 10)
                adverse_exit_roi=-6.0,   # loss-cut: dump a losing short at -6% ROI (taker) instead
                                         # of riding to the -12% SL. 2026-06-23 both-sided replay on
                                         # 30 real trades: -$3.44->-$1.73, all 4 big losers cut, ~1
                                         # winner clipped (losers go straight down, winners rarely dip <-6%).
                adverse_exit_cycles=2,   # arm ~2 cycles (~2 min) after entry
                durable_trail_enabled=False,  # EXCLUDED by design: ST2.0 is a fixed ~20-min
                                              # maker hold (the backtested exit), and a trail is
                                              # INERT on it (reference_st2_exit_replay 2026-06-15:
                                              # ST2.0 trades never clear +2% ROI, max +1.8%). A
                                              # taker trail would also corrupt the maker-fill
                                              # measurement that is the whole point of ST2.0.
            ),
            # ETH_TSM_28 — slow-horizon long-only trend (Han/Kang/Ryu 28/5 tercile),
            # one fixed 0.01-ETH position, min-hold 5d, −8% resting exchange stop as
            # the ONLY protective exit. Pre-registered: docs/overnight-2026-07-05/
            # r5_slow_horizon_research.md §7; build: r6_eth_tsm_build.md.
            # strategy_name is deliberately NOT in STRATEGIES: _evaluate_slots skips
            # the whole slot (strategy_fn None → continue BEFORE its exit block), so
            # NO scalper exit (SL/TP/time/flat/adverse/trail/st2_hold) can ever touch
            # this position. All entries/exits run in _evaluate_eth_tsm instead.
            StrategySlot(
                slot_id=TSM_SLOT_ID,
                strategy_name="eth_tsm_28",  # not a STRATEGIES key — see note above
                timeframe="1d",
                max_positions=1,
                capital_pct=0.0,
                paper_mode=True,          # ships paper-safe; promote via .promote_ETH_TSM_28
                trade_amount_usdt=None,   # unused — sizing is a FIXED 0.01 ETH, no Kelly
                loss_cap_usdt=-999.0,     # rails opt-out: kill criteria are ADJUDICATOR-tracked
                                          # (scripts/lab_adjudicator, net −$10 line), not slot-automated
                kelly_min_trades=10**9,   # neg-Kelly auto-demote never arms (10-20 trades of a
                                          # 48%-deployment strategy is noise to that rail)
                durable_trail_enabled=False,  # spec: NO trail — signal exit or −8% stop only
            ),
            # DONCHIAN_BTC / DONCHIAN_ETH — Concretum 9-lookback Donchian trend
            # ensemble (close-only channels, ratcheting midline stops, 25% vol
            # target), long/flat, paper $100 base notional × weight. Spec (frozen):
            # docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md.
            # strategy_name is deliberately NOT in STRATEGIES: _evaluate_slots skips
            # the whole slot (strategy_fn None → continue BEFORE its exit block), so
            # NO scalper exit (SL/TP/time/flat/adverse/trail/st2_hold) can ever touch
            # these positions. All entries/exits/stops run in _evaluate_donchian on
            # daily closes instead — same trick as ETH_TSM_28 above.
            StrategySlot(
                slot_id="DONCHIAN_BTC",
                strategy_name="donchian_ensemble",  # not a STRATEGIES key — see note above
                timeframe="1d",
                max_positions=1,
                capital_pct=0.0,
                paper_mode=True,          # ships paper-safe; promote via .promote_DONCHIAN_BTC
                trade_amount_usdt=None,   # unused — sizing is BASE_NOTIONAL × w, no Kelly
                loss_cap_usdt=-999.0,     # rails opt-out: kill criteria are spec-tracked
                                          # (paper net −$15 line, fidelity vs replica series)
                kelly_min_trades=10**9,   # neg-Kelly auto-demote never arms (rebalance
                                          # close-and-reopens would feed it paper noise)
                durable_trail_enabled=False,  # spec: the ratcheting Donchian stop IS the
                                              # exit — close-only, evaluated at the daily eval
            ),
            StrategySlot(
                slot_id="DONCHIAN_ETH",
                strategy_name="donchian_ensemble",  # not a STRATEGIES key — see note above
                timeframe="1d",
                max_positions=1,
                capital_pct=0.0,
                paper_mode=True,          # ships paper-safe; promote via .promote_DONCHIAN_ETH
                trade_amount_usdt=None,   # unused — sizing is BASE_NOTIONAL × w, no Kelly
                loss_cap_usdt=-999.0,     # rails opt-out (same as DONCHIAN_BTC)
                kelly_min_trades=10**9,   # neg-Kelly auto-demote never arms
                durable_trail_enabled=False,  # spec: close-only Donchian stop, no trail
            ),
        ]
        # HTF_L2 (2026-07-18, renamed from HTF_L2_PAPER at 7/20 go-live):
        # registered conditionally — builder returns
        # None when Config.HTF_L2_ENABLED is false (env kill, no code edit).
        _htf_l2 = self._build_htf_l2_slot()
        if _htf_l2 is not None:
            self.slots.append(_htf_l2)
        # VWAP_CROSS (2026-07-20): owner-designed strategy, PAPER forward
        # test — registered conditionally, builder returns None when
        # Config.VWAP_CROSS_ENABLED is false (env kill, no code edit).
        _vwap_cross = self._build_vwap_cross_slot()
        if _vwap_cross is not None:
            self.slots.append(_vwap_cross)
        # ETH-TSM-28 runtime state: sidecar mirror + per-cycle entry-in-flight flag
        # (read by _tsm_locks_symbol so the main bot never grabs ETH mid-entry).
        self._tsm_state = tsm_slot.load_state()
        self._tsm_entry_active = False
        # Ownership-interaction Telegram dedup: {kind: "YYYY-MM-DD"} — owner sees
        # every interaction once per UTC day per kind (owner directive 2026-07-06).
        self._tsm_ownership_notified: dict[str, str] = {}
        # Donchian-ensemble runtime state: per-coin persisted ensemble state
        # (sub-model stops/positions, executed weight, day-roll guard) + one-shot
        # per-day dedup for the not-implemented-live warning.
        self._donchian_state = donchian_slot.load_state()
        self._donchian_live_warned: dict[str, str] = {}

    @staticmethod
    def _build_htf_l2_slot():
        """HTF_L2 — htf_l2_anticipation resurrected as a slot probe (2026-07-18,
        born HTF_L2_PAPER; renamed HTF_L2 at the 7/20 go-live).
        Main path stays HALTED (.halt_main_entries); this slot carries the F5
        thin∧ADX gate + slot-local exit geometry (action plan D1). strategy_name
        IS a STRATEGIES key, so unlike TSM/Donchian this slot runs the full
        generic scalper path: slot SL/TP, trend-flip (already wired for htf_l2
        at the slot exit block), hard-240 time exit. Kill criteria are
        ADJUDICATOR-graded; loss cap is the hard live rail (owner go-live
        2026-07-20 — promoted via the promote sentinel, 5m_mean_revert
        precedent: auto-demote to paper at -$5 slot net).
        Returns None when Config.HTF_L2_ENABLED is false (slot absent)."""
        if not Config.HTF_L2_ENABLED:
            return None
        return StrategySlot(
            slot_id="HTF_L2",
            strategy_name="htf_l2_anticipation",   # STRATEGIES key — strategies.py:939
            timeframe="5m",
            max_positions=2,
            capital_pct=0.0,
            paper_mode=True,
            trade_amount_usdt=None,                # None → Config.TRADE_AMOUNT_USDT
            loss_cap_usdt=-5.0,                    # hard rail: auto-demote at -$5 net (live precedent)
            kelly_min_trades=10**9,
            durable_trail_enabled=False,
            sl_percent=Config.HTF_L2_SL_PCT,
            tp_percent=Config.HTF_L2_TP_PCT,
        )

    @staticmethod
    def _build_vwap_cross_slot():
        """VWAP_CROSS — owner-designed strategy (2026-07-20), PAPER forward
        test. 9/15 SMA cross + dual session-VWAP filter (5m + 15m, same
        midnight-UTC anchor; see strategies.vwap_sma_cross). strategy_name IS
        a STRATEGIES key, so the slot runs the full generic scalper path (slot
        SL/TP, hard-240 time exit) under the STANDARD generic slot gates only
        — the thin∧ADX gate and ensemble hard block are htf_l2-specific and
        deliberately NOT applied here (this slot tests the owner's rule as
        designed). Kill lines are OWNER-SET pending; the adjudicator grades
        REPORT-ONLY, so rails are opted out (loss cap -999, Kelly never arms).
        Returns None when Config.VWAP_CROSS_ENABLED is false (slot absent)."""
        if not Config.VWAP_CROSS_ENABLED:
            return None
        return StrategySlot(
            slot_id="VWAP_CROSS",
            strategy_name="vwap_sma_cross",        # STRATEGIES key — strategies.py
            timeframe="5m",
            max_positions=2,
            capital_pct=0.0,
            paper_mode=True,
            trade_amount_usdt=None,                # None → Config.TRADE_AMOUNT_USDT
            loss_cap_usdt=-999.0,                  # paper — rails via adjudicator
            kelly_min_trades=10**9,
            durable_trail_enabled=False,
            sl_percent=Config.VWAP_CROSS_SL_PCT,
            tp_percent=Config.VWAP_CROSS_TP_PCT,
        )

    def _fetch_htf_data(self, symbol: str):
        """Fetch 1h candle data with 5-minute cache. Returns indicator-enriched DataFrame or None."""
        cached = self._htf_cache.get(symbol)
        if cached:
            df, ts = cached
            if time.time() - ts < 300:  # 5 min cache
                return df
        try:
            df_raw = self.exchange.get_ohlcv(symbol, "1h", limit=100)
            if df_raw is not None and len(df_raw) >= 30:
                df = add_all_indicators(df_raw)
                self._htf_cache[symbol] = (df, time.time())
                return df
        except Exception as e:
            logger.debug(f"[HTF] Failed to fetch 1h data for {symbol}: {e}")
        return cached[0] if cached else None  # return stale cache over nothing

    def _fetch_funding_rate(self, symbol: str) -> dict | None:
        """Fetch funding rate with 4-hour cache. Returns stale cache on REST failure."""
        cached = self._funding_cache.get(symbol)
        if cached:
            data, ts = cached
            if time.time() - ts < 14400:  # 4 hr cache
                return data
        data = self.exchange.get_funding_rate(symbol)
        if data is not None:
            self._funding_cache[symbol] = (data, time.time())
            return data
        return cached[0] if cached else None

    def _compute_confidence(self, direction: str, df, ob: dict | None, htf_df=None,
                            cvd_data: dict | None = None, hurst_val: float = 0.5,
                            funding_data: dict | None = None,
                            strategy: str = "", flow: dict | None = None) -> tuple[int, list[str]]:
        """Count independent confirmation layers for the signal direction.
        Returns (count, list_of_confirmed_layers).
        Layers: HTF trend, VWAP position, CVD direction, Hurst regime, Funding rate, OB imbalance."""
        confirmed = []
        last = df.iloc[-1]
        is_long = direction == "long"

        # 1. HTF trend — 1h EMA slope confirms direction
        if htf_df is not None and len(htf_df) >= 2:
            htf_last = htf_df.iloc[-1]
            htf_ema50 = htf_last.get("ema_50", 0)
            htf_ema50_prev = htf_df.iloc[-2].get("ema_50", 0)
            if htf_ema50 and htf_ema50_prev:
                htf_slope = (htf_ema50 - htf_ema50_prev) / htf_ema50_prev if htf_ema50_prev else 0
                if (is_long and htf_slope > 0) or (not is_long and htf_slope < 0):
                    confirmed.append("htf_trend")

        # 2. VWAP position — price above VWAP for longs, below for shorts
        vwap_val = last.get("vwap", 0)
        close_val = last.get("close", 0)
        if vwap_val and close_val:
            if (is_long and close_val > vwap_val) or (not is_long and close_val < vwap_val):
                confirmed.append("vwap_pos")

        # 3. CVD direction — buying pressure for longs, selling for shorts
        #    Divergence upgrades the label but doesn't add a second count
        if cvd_data:
            cvd_slope = cvd_data.get("cvd_slope", 0)
            div = cvd_data.get("divergence")
            if (is_long and div == "bullish") or (not is_long and div == "bearish"):
                confirmed.append("cvd_divergence")  # strongest form
            elif (is_long and cvd_slope > 0) or (not is_long and cvd_slope < 0):
                confirmed.append("cvd")

        # 4. Hurst regime match — must align with strategy type
        reversion_strats = {"vwap_reversion", "htf_confluence_vwap", "bb_mean_reversion"}
        trend_strats = {"momentum_continuation", "trend_pullback", "keltner_squeeze", "htf_confluence_pullback", "htf_l2_anticipation"}
        if hurst_val and not (hurst_val != hurst_val):  # not NaN
            if hurst_val > 0.55 and (not strategy or strategy in trend_strats):
                confirmed.append("hurst_trend")
            elif hurst_val < 0.45 and (not strategy or strategy in reversion_strats):
                confirmed.append("hurst_revert")

        # 5. Funding rate — contrarian signal
        if funding_data:
            fsig = funding_data.get("signal")
            if (is_long and fsig == "long") or (not is_long and fsig == "short"):
                confirmed.append("funding")

        # 6. Order book imbalance — bid-heavy for longs, ask-heavy for shorts
        if ob:
            imb = ob.get("imbalance", 0)
            if (is_long and imb > 0.1) or (not is_long and imb < -0.1):
                confirmed.append("ob_imbalance")

        # 7. Order flow — real-time buy/sell aggressor ratio
        if flow and flow.get("trade_count", 0) > 10:
            buy_ratio = flow.get("buy_ratio", 0.5)
            if (is_long and buy_ratio > 0.55) or (not is_long and buy_ratio < 0.45):
                confirmed.append("order_flow")

        logger.info(f"[ENSEMBLE] {direction} confidence={len(confirmed)}/{7} layers={','.join(confirmed) or 'none'}")
        return len(confirmed), confirmed

    def start(self):
        logger.info(f"Phmex-S Scalp Bot starting | Mode: {Config.MODE.upper()} | Strategy: {Config.STRATEGY}")
        logger.info(f"Leverage: {Config.LEVERAGE}x | Margin/trade: ${Config.TRADE_AMOUNT_USDT} | Timeframe: {Config.TIMEFRAME}")

        # Warm balance/equity cache — retry up to 5x with 15s delay if rate-limited
        balance = 0.0
        for _attempt in range(5):
            balance = self.exchange.get_balance(Config.BASE_CURRENCY)
            if balance > 0:
                break
            logger.warning(f"Balance fetch returned 0 (attempt {_attempt+1}/5), retrying in 15s...")
            time.sleep(15)
        self.exchange.get_equity(Config.BASE_CURRENCY)  # prime the equity cache
        self.risk.set_initial_balance(balance)
        logger.info(f"Starting balance: {balance:.2f} {Config.BASE_CURRENCY}")

        if Config.SCANNER_ENABLED:
            logger.info(f"Volume scanner ON — top {Config.SCANNER_TOP_N} pairs, min vol ${Config.SCANNER_MIN_VOLUME:,.0f}, refresh every {Config.SCANNER_REFRESH_CYCLES} cycles (~{Config.SCANNER_REFRESH_CYCLES * Config.LOOP_INTERVAL}s)")
            if not self.active_pairs:
                logger.info("[SCANNER] No static pairs configured — running initial scan synchronously...")
                for _scan_attempt in range(3):
                    initial_pairs = volatility_scan(self.exchange.client)
                    if initial_pairs:
                        self.active_pairs = initial_pairs
                        logger.info(f"[SCANNER] Initial pairs: {', '.join(self.active_pairs)}")
                        break
                    logger.warning(f"[SCANNER] Initial scan attempt {_scan_attempt+1}/3 failed, retrying in 15s...")
                    time.sleep(15)
                if not self.active_pairs:
                    logger.error("[SCANNER] All initial scan attempts failed — bot will retry via background scanner")
        logger.info(f"Trading pairs: {', '.join(self.active_pairs)}")
        notifier.notify_startup(balance, self.active_pairs, Config.MODE, Config.STRATEGY)

        if Config.is_live():
            logger.info("[WS] Starting WebSocket data feed...")
            self._ws_feed = WSDataFeed(self.active_pairs, Config.TIMEFRAME)
            self._ws_feed.start()
            logger.info("[WS] Seeding cache with REST history...")
            seeded = self._ws_feed.seed(self.exchange.client, limit=Config.CANDLE_LOOKBACK)
            logger.info(f"[WS] Seed complete — {seeded}/{len(self.active_pairs)} pairs ready")

        if Config.is_live():
            open_pos = None
            for _attempt in range(3):
                open_pos = self.exchange.get_open_positions()
                if open_pos is not None:
                    break
                logger.warning(f"Could not fetch open positions (attempt {_attempt+1}/3), retrying in 15s...")
                time.sleep(15)
            if open_pos is None:
                logger.warning("Could not sync open positions at startup — entering ban mode for 2 min to avoid duplicate entries.")
                self.ban_mode = True
                self.ban_mode_until = time.time() + 120
                self.ban_extensions = 0
            elif open_pos:
                # Ownership filter (2026-07-06, ETH-TSM-28 build): LIVE-slot positions
                # persist in their own state files across restarts. Without this filter
                # the main bot would ALSO adopt them here and re-pin scalper SL/TP
                # (1.2%/1.6%) over the slot's exchange orders — for the TSM slot that
                # would destroy the −8% disaster stop and add a TP the spec forbids.
                # Slot copies stay under their slot's RiskManager; per-cycle
                # _sync_exchange_closes reconciles them via _build_position_owners.
                _slot_owned = {s for slot in self.slots if not slot.paper_mode
                               for s in slot.risk.positions}
                main_pos = [p for p in open_pos if p["symbol"] not in _slot_owned]
                _excluded = [p["symbol"] for p in open_pos if p["symbol"] in _slot_owned]
                if _excluded:
                    logger.info(f"[SYNC] Startup: {', '.join(_excluded)} owned by live slot(s) — excluded from main-bot sync")
                # Sync ALL open positions — don't filter by active_pairs
                # (positions may exist on pairs not yet in the scanner/config list)
                if main_pos:
                    self.risk.sync_positions(main_pos, current_cycle=self.cycle_count)
                    logger.info(f"Synced {len(main_pos)} open position(s) from exchange")
                    # Refresh peak_price — may be stale if bot was down while price moved
                    for sym, pos in self.risk.positions.items():
                        try:
                            ticker = self.exchange.get_ticker(sym)
                            if ticker and "last" in ticker:
                                pos.update_trailing_stop(float(ticker["last"]))
                        except Exception as e:
                            logger.debug(f"Could not refresh peak_price for {sym}: {e}")
                    # Place exchange SL/TP for synced positions (they have sl_order_id=None)
                    for sym, pos in self.risk.positions.items():
                        if pos.sl_order_id is None:
                            self.exchange.cancel_open_orders(sym)
                            sl_tp = self.exchange.place_sl_tp(sym, pos.side, pos.amount, pos.stop_loss, pos.take_profit)
                            pos.sl_order_id = sl_tp.get("sl_order_id")
                            pos.tp_order_id = sl_tp.get("tp_order_id")
                            if pos.sl_order_id:
                                pos.exchange_sl_price = pos.stop_loss
                                logger.info(f"[SYNC] Placed exchange SL/TP for {sym} — SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")
                            else:
                                pos.sl_order_id = "software"
                                logger.warning(f"[SYNC] Exchange SL failed for {sym} — using software SL@{pos.stop_loss:.4f}")
                    # Add synced symbols to active pairs so they get monitored
                    synced_symbols = {p["symbol"] for p in open_pos}
                    new_symbols = synced_symbols - set(self.active_pairs)
                    if new_symbols:
                        self.active_pairs = list(set(self.active_pairs) | synced_symbols)
                        logger.info(f"[SYNC] Added {len(new_symbols)} symbol(s) to active pairs: {', '.join(new_symbols)}")
                else:
                    logger.info("No open positions found on exchange.")

        def _cycle_timeout_handler(signum, frame):
            raise TimeoutError("Cycle exceeded 120s — likely hung API call")

        # Set running flag before starting thread so loop guard evaluates correctly
        self.running = True

        # Live exit watcher (tier 2): enforce software exit levels at ~1s against
        # the WS price. Claims in self._closing prevent double-closes with the
        # cycle. Spec: docs/superpowers/specs/2026-06-11-live-exit-watcher-design.md
        self._pos_lock = threading.Lock()
        self._closing: set = set()
        # First-skip timestamps for the watcher's TP strand guard (symbol -> ts)
        self._tp_skip_since: dict = {}
        if Config.is_live() and Config.LIVE_EXIT_WATCHER and self._ws_feed:
            threading.Thread(target=self._live_exit_watcher_loop, daemon=True,
                             name="live-exit-watcher").start()
            logger.info("[LIVE EXIT] watcher enabled (1s interval, WS price, enforcement-only)")

        # Start L2 snapshot live writer thread (updates every 5s for real-time dashboard)
        threading.Thread(
            target=self._l2_live_writer_loop,
            daemon=True,
            name="l2-live-writer",
        ).start()
        logger.info("[L2_LIVE] Snapshot writer thread started (5s interval)")
        try:
            while self.running:
                try:
                    signal.signal(signal.SIGALRM, _cycle_timeout_handler)
                    signal.alarm(180)  # 120s cycle + 60s sleep
                    self._run_cycle()
                    self.consecutive_errors = 0
                    time.sleep(Config.LOOP_INTERVAL)
                    signal.alarm(0)  # cancel watchdog after sleep completes
                except TimeoutError as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.error(f"[WATCHDOG] Cycle timed out ({self.consecutive_errors}): {e}")
                except Exception as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.exception(f"Cycle error ({self.consecutive_errors})")
                if self.consecutive_errors >= 5:
                    self.ban_mode = True
                    self.ban_mode_until = time.time() + 600
                    self.ban_extensions = 0
                    logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                    self.consecutive_errors = 0
                    notifier.notify_ban_mode(10)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
        finally:
            self._shutdown()

    def _set_pause_sentinel(self, reason: str) -> None:
        """Create the .pause_trading sentinel file with a reason note."""
        try:
            with open(".pause_trading", "w") as f:
                f.write(f"{int(time.time())}\n{reason}\n")
        except Exception as e:
            logger.warning(f"Failed to write pause sentinel: {e}")

    def _process_sentinels(self):
        """Check for sentinel files and act on them. One-shot: read, act, delete."""
        import glob as _glob

        # Global pause
        if os.path.exists(".pause_trading"):
            # Daily-loss override: neutralize ONLY a daily-loss halt for the
            # operator-authorized PT day. Manual/Telegram and consecutive-loss
            # pauses (different reason text) are left fully in force.
            if _daily_loss_override_active() and _pause_sentinel_is_daily_loss():
                try:
                    os.remove(".pause_trading")
                except OSError:
                    pass
                self._trading_paused = False
                self._pause_logged = False
                if not getattr(self, '_daily_loss_override_logged', False):
                    msg = ("DAILY LOSS OVERRIDE active — daily-loss halt cleared for "
                           "today; entries allowed. Auto-expires at midnight PT.")
                    logger.warning(f"[KILL SWITCH] {msg}")
                    try:
                        notifier.send(f"⚠️ {msg}")
                    except Exception:
                        pass
                    self._daily_loss_override_logged = True
            else:
                if not hasattr(self, '_pause_logged') or not self._pause_logged:
                    logger.info("[SENTINEL] .pause_trading active — skipping all entries (exits still processed)")
                    self._pause_logged = True
                self._trading_paused = True
                # F2 (2026-07-17): one-shot sweep of resting ENTRY orders on the
                # pause transition edge — a resting PostOnly entry that fills
                # mid-halt creates a ghost position. reduceOnly SL/TP untouched.
                if (Config.CANCEL_ENTRIES_ON_PAUSE
                        and not getattr(self, "_pause_orders_swept", False)):
                    self._pause_orders_swept = True
                    _swept = 0
                    for _sym in list(getattr(self, "active_pairs", []) or []):
                        try:
                            _swept += self.exchange.cancel_entry_orders(_sym)
                        except Exception as _e:
                            logger.warning(f"[ENTRY SWEEP] sweep failed for {_sym}: {_e}")
                    if _swept:
                        logger.warning(f"[ENTRY SWEEP] Cancelled {_swept} resting entry order(s) on pause")
                        try:
                            notifier.send(f"🧹 Cancelled {_swept} resting entry order(s) on halt/pause")
                        except Exception:
                            pass
        else:
            self._trading_paused = False
            self._pause_logged = False
            self._pause_orders_swept = False

        # Reset the override one-shot notice whenever the override is not active,
        # so a fresh override on a later PT day notifies again (and never spams).
        if not _daily_loss_override_active():
            self._daily_loss_override_logged = False

        # Per-slot kills
        for path in _glob.glob(".kill_*"):
            slot_id = path.replace(".kill_", "")
            _kill_failed = False
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.enabled = False
                    for sym in list(slot.risk.positions.keys()):
                        pos = slot.risk.positions[sym]
                        # PAPER slots must never touch the exchange (2026-07-16 review
                        # finding): the old unconditional close_long/close_short sent a
                        # real reduceOnly order that could REDUCE a REAL position if the
                        # main bot happened to hold the same symbol. Close in the paper
                        # book instead, at the freshest price available this early in
                        # the cycle (WS cache; entry price as last resort).
                        if slot.paper_mode:
                            _lp = self.ws_feed.last_price(sym) if self.ws_feed else None
                            _px = _lp[0] if _lp else pos.entry_price
                            self._close_slot_position(slot, sym, pos, _px, "killed")
                            logger.info(f"[SENTINEL] Paper position {sym} closed in book for killed slot {slot_id} @ {_px}")
                            continue
                        if pos.side == "long":
                            order = self.exchange.close_long(sym, pos.amount)
                        else:
                            order = self.exchange.close_short(sym, pos.amount)
                        if not order:
                            # Keep the sentinel file so next cycle retries the close —
                            # deleting it here would strand the position with the slot disabled
                            _kill_failed = True
                            logger.error(f"[SENTINEL] Close FAILED for {sym} (slot {slot_id}) — sentinel kept, retrying next cycle")
                            continue
                        self.exchange.cancel_open_orders(sym)
                        logger.info(f"[SENTINEL] Closing {sym} for killed slot {slot_id}")
                    if _kill_failed:
                        logger.warning(f"[SENTINEL] Slot '{slot_id}' disabled but a position close FAILED — retrying next cycle")
                        notifier.send(f"⚠️ Slot <b>{slot_id}</b> kill: position close FAILED — retrying next cycle, verify manually")
                    else:
                        logger.warning(f"[SENTINEL] Slot '{slot_id}' KILLED")
                        notifier.send(f"🔪 Slot <b>{slot_id}</b> killed via sentinel")
                    break
            if _kill_failed:
                continue
            try:
                os.remove(path)
            except OSError:
                pass

        # Per-slot pauses (auto-expire after 24 hrs)
        for path in _glob.glob(".pause_*"):
            if path == ".pause_trading":
                continue
            slot_id = path.replace(".pause_", "")
            mtime = os.path.getmtime(path)
            if time.time() - mtime > 86400:
                os.remove(path)
                logger.info(f"[SENTINEL] Pause expired for slot '{slot_id}' (24 hrs)")
                continue
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.enabled = False

        # Promote: paper → live
        for path in _glob.glob(".promote_*"):
            slot_id = path.replace(".promote_", "")
            try:
                with open(path) as f:
                    data = json.load(f)
                capital_pct = data.get("capital_pct", 0.10)
            except Exception:
                capital_pct = 0.10
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    # Flush open PAPER positions BEFORE flipping the mode (2026-07-06,
                    # ETH-TSM-28 build): a paper position has no exchange backing, but
                    # after set_live the owner map (_build_position_owners) treats every
                    # slot position as exchange-backed — the next _sync_exchange_closes
                    # would "close" the phantom and record a fabricated LIVE trade.
                    # Near-certain for ETH_TSM_28 (long-horizon, ~48% deployment).
                    if slot.paper_mode:
                        for _psym in list(slot.risk.positions.keys()):
                            _ppos = slot.risk.positions[_psym]
                            _ppx = _ppos.entry_price
                            try:
                                _pt = self.exchange.get_ticker(_psym)
                                if _pt and _pt.get("last"):
                                    _ppx = float(_pt["last"])
                            except Exception:
                                pass
                            slot.risk.close_position(_psym, _ppx, "promote_reset")
                            logger.warning(f"[SENTINEL] {slot_id} paper position {_psym} "
                                           f"closed at promote (promote_reset @ {_ppx})")
                    slot.set_live(capital_pct=capital_pct)
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' PROMOTED to live at {capital_pct*100:.0f}%")
                    notifier.send(f"🚀 Slot <b>{slot_id}</b> promoted to live ({capital_pct*100:.0f}% capital)")
                    break
            try:
                os.remove(path)
            except OSError:
                pass

        # Demote: live → paper
        for path in _glob.glob(".demote_*"):
            slot_id = path.replace(".demote_", "")
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    # _demote_slot closes real positions, flips mode, and sends the Telegram alert
                    self._demote_slot(slot, "manual sentinel")
                    break
            try:
                os.remove(path)
            except OSError:
                pass

    def _run_cycle(self):
        import time as _time_module
        # "Bot is blind" alerts (2026-07-06): stall-recovery notice + WS-blind
        # state machine. Runs BEFORE the ban-mode early-return so outage cycles
        # are still covered. Telegram-only — never touches trading logic.
        _blind_now = _time_module.time()
        try:
            self._blind.check_cycle_gap(_blind_now)
            if self._ws_feed and self.active_pairs:
                _all_stale = all(self._ws_feed.is_stale(s) for s in self.active_pairs)
                self._blind.check_ws_blind(_all_stale, _blind_now)
        except Exception as _blind_err:
            logger.debug(f"[BLIND] monitor error: {_blind_err}")
        if self.ban_mode:
            if _time_module.time() < self.ban_mode_until:
                return
            # Use WS connectivity check instead of REST endpoint test
            if self._ws_feed and self._ws_feed.is_connected:
                recovery_failed = False
            else:
                sym = self.active_pairs[0] if self.active_pairs else None
                test = self.exchange.get_ohlcv(sym, Config.TIMEFRAME, limit=5) if sym else None
                recovery_failed = test is None or test.empty
            if recovery_failed:
                # Diagnose why recovery failed
                diag = _diagnose_connectivity()
                self.ban_extensions += 1
                logger.warning(
                    f"[BAN MODE] Still blocked (extension #{self.ban_extensions}) — "
                    f"network={diag['network']} vpn={diag['vpn']}"
                )
                # Re-rotate VPN every 2 failed recoveries
                if self.ban_extensions % 2 == 0:
                    logger.info(f"[BAN MODE] Re-rotating VPN after {self.ban_extensions} failed recoveries")
                    _rotate_vpn()
                # Telegram escalation after 60 min (6 extensions)
                if self.ban_extensions > 0 and self.ban_extensions % 6 == 0:
                    notifier.notify_ban_stuck(self.ban_extensions * 10, diag)
                self.ban_mode_until = _time_module.time() + 600
                return
            else:
                self.ban_mode = False
                self.consecutive_errors = 0
                self.ban_extensions = 0
                logger.info("[BAN MODE] Connection restored, resuming trading")
                notifier.notify_ban_lifted()

        self._process_sentinels()
        self.cycle_count += 1
        logger.info(f"Cycle #{self.cycle_count} | Positions: {len(self.risk.positions)}")

        # Refresh volatility scan periodically (non-blocking background thread)
        if Config.SCANNER_ENABLED and self.cycle_count % Config.SCANNER_REFRESH_CYCLES == 0:
            logger.info("[SCANNER] Launching background volatility scan...")
            start_background_scan()  # uses its own dedicated ccxt client

        # Pick up background scan results when ready
        if Config.SCANNER_ENABLED:
            scan_result = get_scan_result()
            if scan_result:
                held = set(self.risk.positions.keys())
                self.active_pairs = list(held | set(scan_result))
                # Subscribe WS to any new pairs so they stream live candles
                if self._ws_feed:
                    self._ws_feed.subscribe(self.active_pairs)
                logger.info(f"[SCANNER] Updated pairs: {', '.join(self.active_pairs)}")

        # Fetch OHLCV for all pairs. WS feed is tried first; falls back to REST
        # for symbols not yet in the WS cache (e.g. freshly scanned pairs).
        ohlcv_cache = {}
        prices = {}
        # Include slot open-position symbols (paper AND live) so their exits always
        # get a price — without this, a slot position on a no-longer-scanned pair
        # never exits (the 5m_narrow DOGE freeze, audit 2026-06-11).
        slot_pos_symbols = {s for slot in self.slots
                            for s in slot.risk.positions.keys()}
        all_symbols = list(set(self.active_pairs) | set(self.risk.positions.keys()) | slot_pos_symbols)
        for symbol in all_symbols:
            df_raw = None
            if self._ws_feed and not self._ws_feed.is_stale(symbol):
                df_raw = self._ws_feed.get_ohlcv(symbol, limit=Config.CANDLE_LOOKBACK)
            if df_raw is None:
                df_raw = self.exchange.get_ohlcv(symbol, Config.TIMEFRAME, limit=Config.CANDLE_LOOKBACK)
                time.sleep(0.5)  # throttle REST fallback to avoid CDN ban
            if df_raw is not None and len(df_raw) >= 2:
                ohlcv_cache[symbol] = df_raw
                prices[symbol] = float(df_raw.iloc[-1]["close"])

        # CDN ban detection: if all OHLCV fetches failed, pause to let ban expire.
        # Skip during first 5 cycles — WebSocket cache may not have 2+ candles yet.
        # Also skip if WebSocket is connected — data shortage means candle history is
        # still accumulating, not a CDN ban.
        if all_symbols and not prices:
            if self.cycle_count <= 5:
                logger.info(f"[WARMUP] No OHLCV data yet (cycle {self.cycle_count}/5), waiting for WebSocket cache...")
                return
            if self._ws_feed and self._ws_feed.is_connected:
                logger.info("[WARMUP] WebSocket connected, waiting for candle history to accumulate...")
                return
            self._empty_price_cycles += 1
            if self._empty_price_cycles >= 3:
                self.ban_mode = True
                self.ban_mode_until = time.time() + 600
                self._empty_price_cycles = 0
                self.ban_extensions = 0
                logger.warning("[BAN MODE] All OHLCV fetches failed 3 cycles — CDN ban detected, rotating VPN and pausing 10 min")
                _rotate_vpn()
                notifier.notify_ban_mode(10)
            return
        self._empty_price_cycles = 0

        # Partial take-profit — scale out half at +PARTIAL_TP_ROI margin-ROI, then let
        # the runner half continue under the existing trail/TP/durable-SL machinery.
        # Banks gains the trail currently gives back (2026-06-19 audit: winners peak
        # +6-10% ROI but trail out ~+2.9%). Flag-gated (PARTIAL_TP_ROI=0 disables).
        # Does NOT cancel resting orders: the exchange SL/TP are reduceOnly and
        # auto-cap to the remaining half. Main-bot positions only.
        if Config.PARTIAL_TP_ROI > 0:
            for symbol, pos in list(self.risk.positions.items()):
                price = prices.get(symbol)
                if not price or getattr(pos, "scaled_out", False):
                    continue
                if pos.pnl_percent(price) < Config.PARTIAL_TP_ROI:
                    continue
                with self._pos_lock:
                    if symbol in self._closing or symbol not in self.risk.positions:
                        continue  # watcher mid-close / already gone
                    self._closing.add(symbol)
                try:
                    half = pos.amount / 2
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, half)
                    else:
                        order = self.exchange.close_short(symbol, half)
                    if not order:
                        if self.exchange.pop_reduce_only_abort(symbol):
                            logger.info(f"[PARTIAL TP] {symbol} half-close aborted (reduceOnly) — position closing elsewhere")
                        else:
                            logger.error(f"[PARTIAL TP] half-close order failed for {symbol} — position unchanged")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    fee = self.exchange.extract_order_fee(order, symbol)
                    # Capture the trigger ROI BEFORE partial_close_position halves
                    # pos.margin (else the logged ROI reads ~2x the real trigger).
                    trigger_roi = pos.pnl_percent(fill_price)
                    result = self.risk.partial_close_position(symbol, fill_price, fees_usdt=fee)
                    if result:
                        pnl, pnl_pct = result
                        logger.info(f"[PARTIAL TP] {symbol} scaled out half @ {fill_price:.4f} (+{trigger_roi:.1f}% ROI) — runner continues")
                        # Runner TP: partial_close_position lifted pos.take_profit to the
                        # runner target. Cancel the stale entry-time exchange TP (resting
                        # at the original level) and let the software/watcher enforce the
                        # new target. Only flip to "software" on a CONFIRMED cancel — a
                        # failed cancel leaves the old TP resting (runner caps at the old
                        # level) rather than risking two live TPs.
                        if Config.PARTIAL_RUNNER_TP_ROI > 0 and pos.tp_order_id and pos.tp_order_id != "software":
                            if self.exchange.cancel_order_by_id(symbol, pos.tp_order_id):
                                pos.tp_order_id = "software"
                                logger.info(f"[PARTIAL TP] {symbol} runner TP -> {pos.take_profit:.4f} (+{Config.PARTIAL_RUNNER_TP_ROI:.0f}% ROI, software-enforced)")
                            else:
                                logger.warning(f"[PARTIAL TP] {symbol} could not cancel stale exchange TP — runner keeps original TP level")
                        try:
                            notifier.notify_partial_tp(symbol, pos.side, fill_price, pnl, pnl_pct)
                        except Exception as ne:
                            logger.warning(f"[PARTIAL TP] Telegram notify failed for {symbol}: {ne}")
                except Exception as e:
                    logger.error(f"[PARTIAL TP] scale-out failed for {symbol}: {e}")
                finally:
                    with self._pos_lock:
                        self._closing.discard(symbol)

        # Early exit check — momentum reversal while in profit
        for symbol, pos in list(self.risk.positions.items()):
            if symbol in self._closing:
                continue  # live exit watcher is mid-close on this symbol
            price = prices.get(symbol)
            df_check = ohlcv_cache.get(symbol)
            if not price or df_check is None:
                continue
            try:
                df_check = add_all_indicators(df_check)
                if pos.should_exit_early(price, df_check):
                    logger.info(f"[EARLY EXIT] {symbol} — momentum reversal at {pos.pnl_percent(price):.1f}% profit")
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, pos.amount)
                    else:
                        order = self.exchange.close_short(symbol, pos.amount)
                    if not order:
                        logger.error(f"[EARLY EXIT] Close order failed for {symbol} — position still open on exchange")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                    self.risk.close_position(symbol, fill_price, "early_exit", fees_usdt=self.exchange.extract_order_fee(order, symbol))
                    self.exchange.cancel_open_orders(symbol)
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "early_exit")
            except Exception as e:
                logger.debug(f"Early exit check failed for {symbol}: {e}")

        # Flat exit — cut indecisive positions after 20 min
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions or symbol in self._closing:
                continue  # already closed by early_exit above / watcher mid-close
            price = prices.get(symbol)
            if not price:
                continue
            if pos.should_flat_exit(self.cycle_count, price):
                roi = pos.pnl_percent(price)
                cycles_held = self.cycle_count - pos.entry_cycle
                held_min = cycles_held * Config.LOOP_INTERVAL / 60
                logger.info(f"[FLAT EXIT] {symbol} — {roi:.1f}% ROI after {held_min:.0f}min (no momentum)")
                # No protective deadline — worth resting a maker limit first
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount, urgent=False)
                else:
                    order = self.exchange.close_short(symbol, pos.amount, urgent=False)
                if not order:
                    logger.error(f"[FLAT EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, "flat_exit", fees_usdt=self.exchange.extract_order_fee(order, symbol))
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "flat_exit")

        # Trend-flip exit — close htf_confluence_pullback positions when 1h EMA flips
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions or symbol in self._closing:
                continue
            if pos.strategy not in ("htf_confluence_pullback", "htf_l2_anticipation"):
                continue
            price = prices.get(symbol)
            if not price:
                continue
            htf_df_tuple = self._htf_cache.get(symbol)
            htf_df = htf_df_tuple[0] if htf_df_tuple else None
            should_flip, flip_reason = _check_htf_trend_flip_exit(pos.side, htf_df)
            if should_flip:
                logger.info(f"[TREND-FLIP EXIT] {symbol} {pos.side} — 1h EMA flipped, closing")
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount)
                else:
                    order = self.exchange.close_short(symbol, pos.amount)
                if not order:
                    logger.error(f"[TREND-FLIP EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, flip_reason, fees_usdt=self.exchange.extract_order_fee(order, symbol))
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), flip_reason)
                continue

        # Adverse exit — bail out of wrong-direction trades early
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions or symbol in self._closing:
                continue  # already closed by earlier exit this cycle / watcher mid-close
            price = prices.get(symbol)
            if not price:
                continue
            if pos.should_adverse_exit(self.cycle_count, price):
                cycles_held = self.cycle_count - pos.entry_cycle
                held_min = cycles_held * Config.LOOP_INTERVAL / 60
                roi = pos.pnl_percent(price)
                logger.info(f"[ADVERSE EXIT] {symbol} — {roi:.1f}% ROI after {held_min:.0f}min")
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount)
                else:
                    order = self.exchange.close_short(symbol, pos.amount)
                if not order:
                    logger.error(f"[ADVERSE EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, "adverse_exit", fees_usdt=self.exchange.extract_order_fee(order, symbol))
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "adverse_exit")
                continue

        # Shadow adverse-exit logging (logging only; never closes a position).
        self._log_shadow_adverse_triggers(prices)

        # Bidirectional exchange sync — detect (A) closed-on-exchange positions AND
        # (B) untracked orphan positions. Must run even when self.risk.positions is empty,
        # because the orphan case by definition means bot thinks there are none.
        if Config.is_live():
            self._sync_exchange_closes(prices)
            # F3 (2026-07-17): retry entry-order cancels that failed at entry
            # time — an unconfirmed-dead resting order can fill mid-halt and
            # create a ghost position (4/13 / 6/14 incident class).
            try:
                for _rec in self.exchange.sweep_pending_cancels():
                    try:
                        notifier.send(f"⚠️ Resting entry order {_rec.get('order_id')} on "
                                      f"{_rec.get('symbol')} unresolved for >24h — "
                                      f"cancel manually on Phemex and verify no ghost position")
                    except Exception:
                        pass
            except Exception as _e:
                logger.warning(f"[CANCEL SWEEP] cycle sweep failed: {_e}")

        # Verify SL orders still active — re-place if cancelled (skip software-managed)
        for symbol, pos in list(self.risk.positions.items()):
            if symbol in self._closing:
                continue  # watcher mid-close — cancel_open_orders here could kill its in-flight close order
            if pos.sl_order_id == "software":
                continue  # managed by bot's check_positions loop
            if pos.sl_order_id and not self.exchange.verify_sl_order(symbol, pos.sl_order_id):
                logger.warning(f"[SL CHECK] SL order missing for {symbol} — re-placing")
                self.exchange.cancel_open_orders(symbol)
                # Restore the ratcheted durable level if one was set, not the looser base stop
                replace_sl = pos.exchange_sl_price if pos.exchange_sl_price is not None else pos.stop_loss
                sl_tp = self.exchange.place_sl_tp(symbol, pos.side, pos.amount, replace_sl, pos.take_profit or pos.entry_price)
                pos.sl_order_id = sl_tp.get("sl_order_id")
                pos.tp_order_id = sl_tp.get("tp_order_id")
                if pos.sl_order_id:
                    pos.exchange_sl_price = replace_sl
                if not pos.sl_order_id:
                    # Fall back to software SL/TP — preserve existing SL/TP values
                    # (may be ATR-based or breakeven-adjusted, don't overwrite with Config %)
                    pos.sl_order_id = "software"
                    logger.warning(f"[SL FALLBACK] Re-place failed for {symbol} — switching to software SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")

        # Time-based exit — close stale positions (strategy-specific thresholds)
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions or symbol in self._closing:
                continue  # already closed by early_exit/flat_exit this cycle / watcher mid-close
            price = prices.get(symbol)
            if not price:
                continue
            should_exit, is_hard = pos.should_time_exit(self.cycle_count, current_price=price)
            if should_exit:
                pnl_pct = pos.pnl_percent(price)
                # Soft exit: only if in the red. Hard exit: unconditional.
                if is_hard or pnl_pct < 0:
                    cycles_held = self.cycle_count - pos.entry_cycle
                    held_min = cycles_held * Config.LOOP_INTERVAL / 60
                    exit_type = "hard_time_exit" if is_hard else "time_exit"
                    logger.info(f"[{exit_type.upper()}] {symbol} — {pnl_pct:.1f}% PnL after {held_min:.0f}min (strat={pos.strategy or 'default'})")
                    # No protective deadline — worth resting a maker limit first
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, pos.amount, urgent=False)
                    else:
                        order = self.exchange.close_short(symbol, pos.amount, urgent=False)
                    if not order:
                        logger.error(f"[{exit_type.upper()}] Close order failed for {symbol} — position still open on exchange")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                    self.risk.close_position(symbol, fill_price, exit_type, fees_usdt=self.exchange.extract_order_fee(order, symbol))
                    self.exchange.cancel_open_orders(symbol)
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), exit_type)

        # Break-even and trailing stop updates → durable exchange SL ratchet.
        # Replaces the old cancel-then-place sequence (naked-window bug): the resting
        # SL is moved via atomic amend (move_stop_loss) and is NEVER cancelled before
        # a replacement is confirmed. TP is never touched on this path.
        # Spec: docs/superpowers/specs/2026-06-08-breakeven-sl-solidify-design.md (Part A)
        #     + 2026-06-08-part-b-trailing-protection-plan.md (fast-track addendum).
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions or symbol in self._closing:
                continue  # already closed earlier this cycle / watcher mid-close
            price = prices.get(symbol)
            if not price:
                continue
            old_sl = pos.stop_loss
            pos.check_breakeven(price)
            pos.update_trailing_stop(price)
            if not pos.sl_order_id or pos.sl_order_id == "software":
                continue  # software-managed SL — check_positions handles exits
            # Durable backstop: wide band from peak once the trail is armed. Software
            # tiers (0.3-0.5% price from peak) still exit first via the 60s loop; the
            # resting order caps inter-cycle reversals that used to ride to -12%.
            band = Config.DURABLE_TRAIL_BAND_PCT / 100.0
            durable_floor = None
            if pos.trailing_stop_price is not None and pos.peak_price > 0:
                durable_floor = pos.peak_price * (1 - band) if pos.side == "long" else pos.peak_price * (1 + band)
            # Q2 coordination: resting order is never looser than the breakeven lock.
            candidates = [v for v in (pos.stop_loss, durable_floor) if v is not None]
            target = max(candidates) if pos.side == "long" else min(candidates)
            # Exchange order currently rests at exchange_sl_price (or this cycle's
            # pre-ratchet stop_loss for positions opened before this field existed).
            current_resting = pos.exchange_sl_price if pos.exchange_sl_price is not None else old_sl
            # Ratchet-only + >=0.1% throttle (spec guardrail — avoid amend spam)
            improvement = (target - current_resting) if pos.side == "long" else (current_resting - target)
            if improvement <= 0 or improvement / price < 0.001:
                continue
            try:
                new_id = self.exchange.move_stop_loss(symbol, pos.side, pos.amount, target, pos.sl_order_id)
                pos.sl_order_id = new_id
                pos.exchange_sl_price = target
                pos.sl_ratcheted = True
                logger.info(
                    f"[DURABLE SL] {symbol} exchange SL ratcheted to {target:.4f} "
                    f"(breakeven={pos.stop_loss:.4f}, durable_floor={round(durable_floor, 4) if durable_floor is not None else None})"
                )
            except Exception as e:
                # Old SL is still resting (move_stop_loss guarantees it) — alert loudly,
                # do NOT downgrade to "software": that would lie about protection state.
                logger.error(f"[SL-MOVE-FAIL] {symbol} could not move exchange SL to {target:.4f}: {e} — old SL still resting at {current_resting:.4f}")
                try:
                    notifier.notify_sl_move_fail(symbol, target, current_resting, str(e))
                except Exception as ne:
                    logger.warning(f"[SL-MOVE-FAIL] Telegram alert failed for {symbol}: {ne}")

        # Check exit conditions for open positions
        to_close = self.risk.check_positions(prices)
        for symbol, reason in to_close:
            if symbol in self._closing:
                continue  # live exit watcher is mid-close on this symbol
            price = prices.get(symbol)
            if price:
                pos = self.risk.positions.get(symbol)
                if pos:
                    # take_profit is in-the-money with no protective deadline — patient
                    # maker close; stop_loss/trailing_stop must hit market immediately
                    urgent = reason != "take_profit"
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, pos.amount, urgent=urgent)
                    else:
                        order = self.exchange.close_short(symbol, pos.amount, urgent=urgent)
                    if not order:
                        logger.error(f"[SOFTWARE SL/TP] Close order failed for {symbol} — position still open on exchange")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), reason)
                    self.risk.close_position(symbol, fill_price, reason, fees_usdt=self.exchange.extract_order_fee(order, symbol))
                    self.exchange.cancel_open_orders(symbol)

        # Part B shadow-logger — read-only trail instrumentation, must never break the cycle
        try:
            self._log_shadow_trail(prices, ohlcv_cache)
        except Exception as e:
            logger.debug(f"[SHADOW TRAIL] logging failed: {e}")

        # Check for new entry signals
        available = self.exchange.get_balance(Config.BASE_CURRENCY)     # free balance for trade sizing
        margin_in_use = sum(pos.margin for pos in self.risk.positions.values())
        # Drawdown/peak/halt tracking uses exchange-reported TOTAL equity (cached
        # by the get_balance call above) — free+main-margin is blind to live slot
        # positions' margin and fired 9 false [DRAWDOWN] pauses (see helper doc).
        # Paper mode passes 0 to force the fallback sum: paper_balances is already
        # margin-debited and paper positions ARE in risk.positions, so the old
        # free+margin math is exactly right there (review 2026-07-08 catch).
        _exchange_equity = (self.exchange.get_equity(Config.BASE_CURRENCY)
                            if Config.is_live() else 0.0)
        real_balance = _equity_for_drawdown(_exchange_equity, available + margin_in_use)
        self.risk.update_peak_balance(real_balance)

        # STATS must print BEFORE the regime-pause/_trading_paused/.halt_main_entries
        # early returns: monitor_daemon, web_dashboard, trading_desk, and
        # daily_report all parse this line for balance/drawdown, and the 7/13
        # entries halt starved them to $0 when it lived at end-of-cycle (2026-07-16).
        self._maybe_print_stats(real_balance, available, margin_in_use)

        # Regime filter — pause all entries after consecutive losses
        if time.time() < self._regime_pause_until:
            remaining = int(self._regime_pause_until - time.time())
            if self.cycle_count % 20 == 0:  # log every ~5 min
                logger.info(f"[REGIME] Entries paused — {remaining}s remaining")
            return  # skip entire entry section, but exits still processed above

        # Pre-compute indicators for entry signals
        indicator_cache = {}
        for sym in self.active_pairs:
            if sym in self.risk.positions:
                continue
            df_raw = ohlcv_cache.get(sym)
            if df_raw is None or len(df_raw) < 50:
                continue
            df_ind = add_all_indicators(df_raw)
            if len(df_ind) < 14:
                continue
            indicator_cache[sym] = df_ind

        if getattr(self, '_trading_paused', False):
            # F1 (2026-07-17): service slots (their software exits + SL ratchet)
            # before returning — mirrors the .halt_main_entries branch below.
            # Without this, a global pause froze the LIVE slot's exit stack for
            # the pause duration (only the exchange-resting SL protected it).
            # Slot ENTRIES stay blocked: both entry branches in _evaluate_slots
            # check _slot_entries_blocked().
            self._evaluate_all_slots(prices)
            return  # main exits already processed above, skip main entries

        # Operator halt of MAIN-BOT entries only (2026-07-13). Stops the
        # confluence/htf_l2 scalper (gross-negative — see session audit / TASKS.md)
        # while the live 5m_mean_revert slot and the ETH-TSM paper probe keep trading
        # and ALL exits keep firing. Distinct from .pause_trading, whose return above
        # fires BEFORE the slot evaluators and would freeze slot software-exits.
        # Reversible with no restart: delete the .halt_main_entries file.
        if os.path.exists(".halt_main_entries"):
            if not getattr(self, '_halt_main_logged', False):
                logger.warning("[SENTINEL] .halt_main_entries active — main-bot entries "
                               "halted; slots + exits still run")
                try:
                    notifier.send("⛔ <b>Main-bot entries HALTED</b> (.halt_main_entries) — "
                                  "5m_mean_revert + ETH-TSM still running, exits intact")
                except Exception:
                    pass
                self._halt_main_logged = True
            self._evaluate_all_slots(prices)
            return  # skip main entry loop; slots (incl. their exits) serviced above
        else:
            self._halt_main_logged = False

        # --- Extended kill switches (daily loss + consecutive loss) ---
        today_net = _compute_today_net_pnl(self.risk.closed_trades)
        if _should_halt_daily_loss(today_net, real_balance):
            _halt_thr = max(real_balance * 0.03, 5.0)  # mirror _should_halt_daily_loss
            if _daily_loss_override_active():
                if not getattr(self, "_daily_loss_override_logged", False):
                    msg = (f"DAILY LOSS OVERRIDE active — today net ${today_net:.2f} past "
                           f"-${_halt_thr:.2f} (max of 3% / $5 floor) of ${real_balance:.2f}, "
                           f"but operator override for today is "
                           f"set; entries allowed. Auto-expires at midnight PT.")
                    logger.warning(f"[KILL SWITCH] {msg}")
                    try:
                        notifier.send(f"⚠️ {msg}")
                    except Exception:
                        pass
                    self._daily_loss_override_logged = True
            else:
                reason = (f"DAILY LOSS HALT: today net ${today_net:.2f} exceeds "
                          f"-${_halt_thr:.2f} (max of 3% / $5 floor) of ${real_balance:.2f}")
                self._set_pause_sentinel(reason)
                logger.warning(f"[KILL SWITCH] {reason}")
                try:
                    notifier.send(f"⛔ {reason}")
                except Exception:
                    pass
                return

        if _should_halt_consecutive_losses(self._loss_streak):
            reason = f"CONSECUTIVE LOSS HALT: {self._loss_streak} losses in a row — 4h cooldown"
            self._set_pause_sentinel(reason)
            logger.warning(f"[KILL SWITCH] {reason}")
            try:
                notifier.send(f"⛔ {reason}")
            except Exception:
                pass
            return

        for symbol in self.active_pairs:
            if symbol in self.risk.positions:
                continue
            # ETH ownership rule (ETH-TSM-28, 2026-07-06): Phemex one-way mode
            # ("posSide=Merged") merges all positions per symbol, so while the TSM
            # slot owns ETH (live position held / entry in flight today / its 3x
            # leverage flip not yet restored to 10x) the main bot must NOT enter
            # ETH — a main-bot fill would merge into the slot's position AND be
            # sized wrong at 3x (amount math assumes Config.LEVERAGE=10x).
            _tsm_lock = self._tsm_locks_symbol(symbol)
            if _tsm_lock:
                self._tsm_notify_ownership(
                    "main_skip", f"main-bot ETH entry skipped ({_tsm_lock})")
                continue
            # Global cooldown: 2 min between any new entry (continue, not break)
            if time.time() - self._last_entry_time < 120:
                continue
            # Per-pair cooldown: skip pair after losses
            if symbol in self._pair_cooldown and time.time() < self._pair_cooldown[symbol]:
                continue
            # Daily symbol cap — ENFORCED as of 2026-06-11 audit. CLAUDE.md and .env
            # claimed DAILY_SYMBOL_CAP=3 for weeks while this was log-only.
            day_start = time.time() - (time.time() % 86400)  # midnight UTC
            daily_trades = sum(1 for t in self.risk.closed_trades
                               if t.get("symbol") == symbol and t.get("opened_at", 0) > day_start
                               and t.get("exit_reason") != "min_margin_skip")  # partial-fill ghosts don't consume cap slots (review 2026-06-11)
            daily_trades += 1 if symbol in self.risk.positions else 0  # count open positions too
            if daily_trades >= Config.DAILY_SYMBOL_CAP:
                logger.info(f"[DAILY CAP] {symbol} — {daily_trades} trades today (cap {Config.DAILY_SYMBOL_CAP}) — entry skipped")
                continue

            if not self.risk.can_open_trade(real_balance):
                break

            if symbol not in self._leverage_set:
                self.exchange.ensure_leverage(symbol)
                self._leverage_set.add(symbol)

            df = indicator_cache.get(symbol)
            if df is None:
                df_raw = ohlcv_cache.get(symbol)
                if df_raw is None or len(df_raw) < 50:
                    logger.warning(f"Not enough data for {symbol}, skipping.")
                    continue
                df = add_all_indicators(df_raw)
                if len(df) < 14:
                    continue

            try:
                atr_val = float(df.iloc[-1]["atr"])
                if atr_val != atr_val:  # NaN check
                    atr_val = 0.0
            except (KeyError, ValueError, TypeError):
                atr_val = 0.0

            # Determine volatility regime (no extreme skip in v4.0)
            atr_pct_val = float(df.iloc[-1].get("atr_pct", 50))
            if atr_pct_val > 80:
                regime = "high"
            elif atr_pct_val > 25:
                regime = "medium"
            else:
                regime = "low"

            # Fetch orderbook, HTF data, and tape flow for strategy confirmation
            ob = self.exchange.get_order_book(symbol)
            # Cache depth for live L2 writer thread (no API cost — data is already fetched)
            if ob:
                self._ob_depth_cache[symbol] = {
                    "bid_depth_usdt": ob.get("bid_depth_usdt"),
                    "ask_depth_usdt": ob.get("ask_depth_usdt"),
                    "imbalance":      ob.get("imbalance", 0),
                    "updated_at":     time.time(),
                }
            htf_df = self._fetch_htf_data(symbol)
            flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
            # Capture flow+OB snapshot per scan for offline backtester replay (capture-forward decision 2026-05-10)
            self._log_flow_snapshot(symbol, ob, flow, price=float(df.iloc[-1]["close"]) if df is not None and len(df) > 0 else None)
            try:
                signal = self.strategy_fn(df, ob, htf_df=htf_df, flow=flow)
            except TypeError:
                try:
                    signal = self.strategy_fn(df, ob, htf_df=htf_df)
                except TypeError:
                    signal = self.strategy_fn(df, ob)

            if signal.signal == Signal.HOLD:
                logger.debug(f"[HOLD] {symbol} — {signal.reason}")

            if signal.signal != Signal.HOLD and ob is not None:
                logger.info(f"[OB] {symbol} imb={ob.get('imbalance', 0):+.2f} spread={ob.get('spread_pct', 0):.3f}% walls=B{len(ob.get('bid_walls', []))}A{len(ob.get('ask_walls', []))}")

            # Short penalty: -0.04 strength (reduced from -0.08 — was blocking market-open shorts)
            if signal.signal == Signal.SELL:
                signal = TradeSignal(signal.signal, signal.reason, signal.strength - 0.04)

            # Min strength check (float-safe: 0.84 - 0.04 dust must count as 0.80)
            if signal.signal != Signal.HOLD and not _meets_min_strength(signal.strength, Config.SCALP_MIN_STRENGTH):
                logger.debug(f"Signal too weak for {symbol}: {signal.strength:.2f}, skipping")
                continue

            price = prices.get(symbol, df.iloc[-1]["close"])

            if signal.signal in (Signal.BUY, Signal.SELL):
                direction = "long" if signal.signal == Signal.BUY else "short"

                # Build cvd_data from order flow (backward compatible with ensemble layer 3)
                cvd_data = None
                if flow and flow.get("trade_count", 0) > 0:
                    cvd_data = {
                        "cvd": flow.get("cvd", 0),
                        "cvd_slope": flow.get("cvd_slope", 0),
                        "divergence": flow.get("divergence"),
                    }
                else:
                    # Fallback to REST CVD when WS trades unavailable
                    cvd_data = self.exchange.get_cvd(symbol)
                funding_data = self._fetch_funding_rate(symbol)
                hurst_val = float(df.iloc[-1].get("hurst", 0.5))
                if hurst_val != hurst_val:  # NaN check
                    hurst_val = 0.5

                if cvd_data:
                    logger.info(f"[CVD] {symbol} cvd={cvd_data['cvd']:.0f} slope={cvd_data['cvd_slope']:.0f} div={cvd_data.get('divergence', 'none')}")
                if funding_data:
                    logger.info(f"[FUNDING] {symbol} rate={funding_data['rate']:.6f} signal={funding_data.get('signal', 'none')}")
                logger.info(f"[HURST] {symbol} H={hurst_val:.3f}")

                # Ensemble confidence gate
                strat_name = _extract_strategy_name(signal.reason)
                confidence, layers = self._compute_confidence(
                    direction, df, ob, htf_df=htf_df,
                    cvd_data=cvd_data, hurst_val=hurst_val, funding_data=funding_data,
                    strategy=strat_name, flow=flow
                )
                # Strategy-aware confidence thresholds (raised to 4/7 on 2026-04-07)
                CONFIDENCE_THRESHOLDS = {
                    "htf_confluence_pullback": 4,
                    "htf_confluence_vwap": 4,
                    "vwap_reversion": 4,
                    "bb_mean_reversion": 4,
                    "momentum_continuation": 4,
                    "trend_pullback": 4,
                    "keltner_squeeze": 4,
                    "liq_cascade": 4,
                }
                min_confidence = CONFIDENCE_THRESHOLDS.get(strat_name, 4)

                if confidence < min_confidence:
                    logger.info(
                        f"[ENSEMBLE SKIP] {symbol} {direction} — BLOCKED: ensemble confidence {confidence}/7 "
                        f"< {min_confidence}/7 minimum (strat={strat_name})"
                    )
                    # F6 (2026-07-17): gotAway-log ensemble blocks — they were
                    # invisible to every prior gate analysis (never logged there).
                    self._log_gotaway("ensemble_confidence", symbol, direction, strat_name,
                                      signal.strength, confidence, price, ob, flow, df)
                    continue

                # Divergence cooldown — require 3 clean cycles OR 10 min after a divergence block
                if symbol in self._divergence_cooldown:
                    _dc = self._divergence_cooldown[symbol]
                    _dc_elapsed = time.time() - _dc["blocked_at"]
                    if _dc_elapsed >= 600 or _dc["clean_cycles"] >= 3:
                        del self._divergence_cooldown[symbol]  # cooldown expired, allow through
                    else:
                        # Count clean cycles (cycles where divergence is absent for this symbol)
                        if not (flow and flow.get("divergence")):
                            self._divergence_cooldown[symbol]["clean_cycles"] += 1
                        logger.info(
                            f"[DIVERGENCE COOLDOWN] {symbol} {direction} blocked — "
                            f"{_dc['clean_cycles']}/3 clean cycles, {_dc_elapsed:.0f}s elapsed")
                        continue

                # Order flow / tape veto — block entry if real money strongly disagrees
                if not (flow and flow.get("trade_count", 0) > 20):
                    logger.info(f"[TAPE GATE SKIP] {symbol} {direction} — low volume (trade_count={flow.get('trade_count', 0) if flow else 'no_flow'}) — tape gates inactive")
                    # Soft gate: even at low volume, block on extreme seller/buyer dominance
                    if flow and 5 <= flow.get("trade_count", 0) <= 20:
                        _soft_ratio = flow.get("buy_ratio", 0.5)
                        if direction == "long" and _soft_ratio < 0.40:
                            logger.info(
                                f"[TAPE GATE SOFT] {symbol} LONG blocked — buy_ratio {_soft_ratio:.0%} "
                                f"(thin tape, {flow.get('trade_count')} trades, sellers overwhelming)")
                            continue
                        if direction == "short" and _soft_ratio > 0.60:
                            logger.info(
                                f"[TAPE GATE SOFT] {symbol} SHORT blocked — buy_ratio {_soft_ratio:.0%} "
                                f"(thin tape, {flow.get('trade_count')} trades, buyers overwhelming)")
                            continue
                if flow and flow.get("trade_count", 0) > 20:
                    buy_ratio = flow.get("buy_ratio", 0.5)
                    cvd_slope = flow.get("cvd_slope", 0.0)
                    divergence = flow.get("divergence")
                    lt_bias = flow.get("large_trade_bias", 0.0)
                    if direction == "long" and buy_ratio < 0.45:
                        logger.info(
                            f"[TAPE GATE] {symbol} LONG blocked — buy_ratio {buy_ratio:.0%} "
                            f"({flow.get('trade_count', 0)} trades, sellers dominating)")
                        continue
                    if direction == "short" and buy_ratio > 0.55:
                        logger.info(
                            f"[TAPE GATE] {symbol} SHORT blocked — buy_ratio {buy_ratio:.0%} "
                            f"({flow.get('trade_count', 0)} trades, buyers dominating)")
                        continue
                    # cvd_slope absolute gate — skip for pullback/reversion strategies
                    # Pullbacks have negative CVD by definition (sellers pushing the dip),
                    # so this gate would systematically block legitimate pullback longs.
                    # The divergence gate below is the contextual version that handles this correctly.
                    if strat_name not in ("htf_confluence_pullback", "bb_mean_reversion"):
                        if direction == "long" and cvd_slope < -0.3:
                            logger.info(f"[TAPE GATE] {symbol} LONG blocked — CVD slope {cvd_slope:.2f} (selling accelerating)")
                            continue
                        if direction == "short" and cvd_slope > 0.3:
                            logger.info(f"[TAPE GATE] {symbol} SHORT blocked — CVD slope {cvd_slope:.2f} (buying accelerating)")
                            continue
                    if direction == "long" and divergence == "bearish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        logger.info(f"[TAPE GATE] {symbol} LONG blocked — bearish divergence (price up, sellers gaining)")
                        continue
                    if direction == "short" and divergence == "bullish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — bullish divergence (price down, buyers gaining)")
                        continue
                    if direction == "long" and lt_bias < -0.3:
                        logger.info(f"[TAPE GATE] {symbol} LONG blocked — large trade bias {lt_bias:.2f} (whales selling)")
                        continue
                    if direction == "short" and lt_bias > 0.3:
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — large trade bias {lt_bias:.2f} (whales buying)")
                        continue

                # Standalone divergence check — always active, even when tape gates skipped
                # Divergence = price direction vs CVD direction; valid at any volume
                # When trade_count > 20, the check inside the tape gate block (above) fires first.
                # This is the safety net for low-volume conditions where tape gates are skipped.
                if flow and flow.get("divergence"):
                    _div = flow["divergence"]
                    if direction == "long" and _div == "bearish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        self._log_gotaway("divergence_bearish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} LONG blocked — bearish divergence (always-on)")
                        continue
                    if direction == "short" and _div == "bullish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        self._log_gotaway("divergence_bullish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} SHORT blocked — bullish divergence (always-on)")
                        continue

                # Apply funding rate strength modifier
                if funding_data and funding_data.get("strength_mod"):
                    signal = TradeSignal(signal.signal, signal.reason, signal.strength + funding_data["strength_mod"])

                # Candle-boundary entry bias: prefer entries near 5m candle opens
                # Research: +0.58bps at candle boundaries (t-stat > 9)
                now_min = datetime.datetime.now(datetime.timezone.utc).minute
                candle_offset = now_min % 5  # 0 = candle just opened, 4 = about to close
                if candle_offset >= 3:  # Last 2 minutes of candle — skip, wait for next open
                    logger.debug(f"[TIMING] {symbol} — skipping entry, {5-candle_offset}min to next candle open")
                    continue

                # Time-of-day filter: config-driven, empty = 24-hour trading (Jonas 2026-06-30).
                # Old Apr-era block (from a 417-trade ALL-STRATEGY sample, contaminated by dead
                # strategies; gate-quantify 2026-06-13 found NO significant time edge) was:
                #   UTC {0,1,2,9,17,18,19,20} = 5-7 PM / 2 AM / 10 AM-1 PM PT.
                # Restore by setting TRADING_BLOCKED_HOURS_UTC=0,1,2,9,17,18,19,20 in .env.
                _BLOCKED_HOURS_UTC = Config.TRADING_BLOCKED_HOURS_UTC
                _utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
                _pt_hour = (_utc_hour - 7) % 24
                if _utc_hour in _BLOCKED_HOURS_UTC:
                    _pt_label = f"{_pt_hour % 12 or 12}:00 {'AM' if _pt_hour < 12 else 'PM'}"
                    logger.info(f"[TIME BLOCK] {symbol} {direction} skipped — {_pt_label} PT is blocked")
                    continue

                # Cluster throttle: max 1 htf_confluence_pullback entry per 30 min
                # Data: 27/57 htf cluster entries = -$14.10. Solo entries = -$0.37 (breakeven).
                if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation") and time.time() - self._last_htf_entry_time < 1800:
                    logger.info(f"[HTF THROTTLE] {symbol} {direction} skipped — htf entry {(time.time() - self._last_htf_entry_time)/60:.0f}min ago, need 30min gap")
                    continue

                # Concurrent-entry drift gate (r1 A.3; OOS 2026-07-12): don't add a
                # new htf_l2 entry while any open position is underwater — fresh-data
                # underwater-book entries ran 11% WR (9/9 of the 7/10-7/11 chain losers).
                # Blocks ~14% of flow; sim net saved +$14.22 CI [+4.36, +23.37].
                if (Config.DRIFT_GATE_ENABLED and strat_name == "htf_l2_anticipation"
                        and self.risk.positions and self._ws_feed):
                    _uw = _underwater_positions(self.risk.positions, self._ws_feed.last_price)
                    if _uw:
                        _uw_sym, _uw_drift = _uw[0]
                        self._log_gotaway("drift_gate", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(
                            f"[DRIFT GATE] {symbol} {direction.upper()} blocked — "
                            f"{_uw_sym.split('/')[0]} underwater {_uw_drift:.2f}%"
                        )
                        continue

                # F5 (2026-07-17): htf_l2 thin-tape ∧ high-1h-ADX toxic-cell block
                _f5_adx = (float(htf_df.iloc[-1].get("adx", 0))
                           if htf_df is not None and len(htf_df) > 0 else None)
                if self._thin_adx_blocked(strat_name, flow, _f5_adx):
                    self._log_gotaway("thin_adx", symbol, direction, strat_name,
                                      signal.strength, confidence, price, ob, flow, df)
                    logger.info(
                        f"[THIN-ADX] {symbol} {direction.upper()} blocked — "
                        f"htf_adx {_f5_adx:.1f} >= {Config.HTF_BLOCK_ADX_MIN:.0f} on thin tape "
                        f"(tc={(flow or {}).get('trade_count', 0)} <= {Config.HTF_BLOCK_TAPE_MAX})"
                    )
                    continue

                # Phase 2b Gate A: pullback per-hour bleed filter (30d data-driven)
                # UTC {5,8,13,14,16} = 10PM/1AM/6AM/7AM/9AM PT — 5 unblocked hours where pullback runs 22% WR vs 47% breakeven
                # Shadow-log when PULLBACK_SESSION_GATE=false; hard-block when true
                if strat_name == "htf_confluence_pullback":
                    _pb_utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
                    _PULLBACK_BLEED_HOURS_UTC = {5, 8, 13, 14, 16}
                    if _pb_utc_hour in _PULLBACK_BLEED_HOURS_UTC:
                        _pb_pt = (_pb_utc_hour - 7) % 24
                        _pb_label = f"{_pb_pt % 12 or 12}:00 {'AM' if _pb_pt < 12 else 'PM'}"
                        self._log_gotaway("pullback_hour_bleed", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(
                            f"[PHASE2B] {symbol} {direction.upper()} pullback hour bleed — "
                            f"{_pb_label} PT ({'BLOCKED' if Config.PULLBACK_SESSION_GATE else 'shadow-tagged'})"
                        )
                        if Config.PULLBACK_SESSION_GATE:
                            continue

                # Kelly-aware position sizing (uses $2 min margin during bootstrap)
                margin = self.risk.calculate_kelly_margin(available, confidence=confidence)

                # Weekend sizing boost: +85-92% weekend returns (p < 0.001)
                if datetime.datetime.now(datetime.timezone.utc).weekday() in (5, 6):  # Saturday=5, Sunday=6
                    margin = min(margin * 1.3, 15.0)  # cap at $15 (TRADE_AMOUNT_USDT — keep weekend size equal to weekday, Jonas 2026-07-05)

                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue

                # Bump margin to exchange minimum if needed (ensures BTC/ETH can trade)
                try:
                    market = self.exchange.client.market(symbol)
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                    if min_amount and price > 0:
                        min_margin_needed = (min_amount * price) / Config.LEVERAGE
                        if margin < min_margin_needed:
                            old_margin = margin
                            margin = min(min_margin_needed * 1.1, available * 0.3)  # 10% buffer, cap at 30% of balance
                            if margin > available:
                                logger.debug(f"[SKIP] {symbol} — need ${min_margin_needed:.2f} but only ${available:.2f} available")
                                continue
                            logger.info(f"[MARGIN BUMP] {symbol} — ${old_margin:.2f} → ${margin:.2f} (exchange min qty)")
                except Exception:
                    pass

                # L2 Orderbook gate — block entry on adverse book conditions
                if ob is not None:
                    ob_imb = ob.get("imbalance", 0.0)
                    ob_bwalls = ob.get("bid_walls", [])
                    ob_awalls = ob.get("ask_walls", [])
                    ob_spread = ob.get("spread_pct", 0.0)
                    if direction == "long" and ob_imb < -0.25:
                        logger.info(f"[OB GATE] {symbol} LONG blocked — ask imbalance {ob_imb:.2f}")
                        continue
                    if direction == "short" and ob_imb > 0.25:
                        logger.info(f"[OB GATE] {symbol} SHORT blocked — bid imbalance {ob_imb:.2f}")
                        continue
                    if direction == "long" and ob_awalls and not ob_bwalls:
                        logger.info(f"[OB GATE] {symbol} LONG blocked — unmatched ask wall")
                        continue
                    if direction == "short" and ob_bwalls and not ob_awalls:
                        logger.info(f"[OB GATE] {symbol} SHORT blocked — unmatched bid wall")
                        continue
                    if ob_spread > 0.15:
                        logger.info(f"[OB GATE] {symbol} blocked — wide spread {ob_spread:.3f}%")
                        continue

                # QUIET regime gate — block low-momentum entries
                # QUIET = 5m ADX 20-25, no EMA stack alignment (0% WR in 48hr audit)
                # Flow-confirmation exemption CLOSED 2026-06-12: exempt cohort ran
                # 44.4% WR / -$5.45 over 18 entries (audit 2026-06-11), and its
                # criterion (aligned cvd_slope > 0.2) selects the worst-performing
                # cvd bucket on the live book (-$0.197/trade). QUIET always blocks.
                _regime_snap = self._classify_regime(df.iloc[-1], df)
                if _regime_snap.get("label") == "QUIET":
                    self._log_gotaway("quiet_regime", symbol, direction, strat_name,
                                      signal.strength, confidence, price, ob, flow, df)
                    logger.info(f"[REGIME GATE] {symbol} {direction.upper()} blocked — QUIET regime "
                                f"(5m ADX={_regime_snap.get('adx', '?')})")
                    continue

                # Phase 3 shadow gates (2026-06-11): tag-only, NEVER block. Records
                # what each candidate gate would have done so the forward live book
                # validates the in-sample sims (Method 1 pRnd / Method 2 replay)
                # before any hard gate ships. Decision target: ~June 23 with the
                # durable-trail verdict.
                _shadow_gates = {}
                try:
                    _lt = float((flow or {}).get("large_trade_bias") or 0.0)
                    _aligned_lt = _lt if direction == "long" else -_lt
                    _adx5 = _regime_snap.get("adx")
                    _hour_utc = datetime.datetime.utcnow().hour
                    _shadow_gates = {
                        "sg_ltbias040": _aligned_lt >= 0.40,
                        "sg_adx25": _adx5 is not None and float(_adx5) >= 25.0,
                        "sg_conf_lt5": confidence < 5,
                        "sg_utc2123": _hour_utc in (21, 22, 23),
                    }
                except Exception as _sge:
                    logger.debug(f"[SHADOW GATES] tag computation failed: {_sge}")

                # Phase 2b Gate B: VOLATILE 5m regime shadow-tag (pullback-specific, shadow only — no hard-gate path)
                # Reuses _regime_snap from QUIET block above; VOLATILE label = atr_pct > 1.5% or vol_ratio > 2.5x
                if strat_name == "htf_confluence_pullback" and _regime_snap.get("label") == "VOLATILE":
                    self._log_gotaway("pullback_volatile_5m", symbol, direction, strat_name,
                                      signal.strength, confidence, price, ob, flow, df)
                    logger.debug(
                        f"[PHASE2B] {symbol} {direction.upper()} pullback volatile 5m — "
                        f"ATR={_regime_snap.get('atr_pct', 0):.3%} vol={_regime_snap.get('vol_ratio', 0):.1f}x "
                        f"(shadow-tagged only)"
                    )

                order = self.exchange.open_long(symbol, margin, price) if direction == "long" else self.exchange.open_short(symbol, margin, price)
                if order:
                    fill_price = self._extract_fill_price(order, price)
                    self.risk.open_position(symbol, fill_price, margin, side=direction, atr=atr_val, regime=regime, cycle=self.cycle_count, strategy=strat_name)
                    pos = self.risk.positions[symbol]
                    fill_amount = self._extract_fill_amount(order, pos.amount)
                    actual_margin = (fill_amount * fill_price) / Config.LEVERAGE
                    _min_margin = float(os.getenv("MIN_TRADE_MARGIN", "10.0")) * 0.5
                    if actual_margin < _min_margin:
                        # Partial fill below minimum — close immediately to free the slot
                        logger.warning(f"[SKIP] {symbol} partial fill ${actual_margin:.4f} < ${_min_margin:.2f} min — closing to free slot")
                        self.exchange.cancel_open_orders(symbol)
                        close_ok = (
                            self.exchange.close_long(symbol, fill_amount)
                            if direction == "long"
                            else self.exchange.close_short(symbol, fill_amount)
                        )
                        if close_ok:
                            self.risk.close_position(symbol, fill_price, "min_margin_skip")
                        else:
                            logger.error(f"[SKIP] {symbol} emergency close failed — leaving in tracker for exit loop")
                        continue
                    pos.amount = fill_amount
                    pos.margin = actual_margin
                    pos.entry_strength = signal.strength
                    pos.confidence = confidence
                    pos.ensemble_layers = ",".join(layers)
                    sl_tp = self.exchange.place_sl_tp(symbol, direction, fill_amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    if pos.sl_order_id:
                        pos.exchange_sl_price = pos.stop_loss
                    if not pos.sl_order_id:
                        pos.sl_order_id = "software"
                        logger.warning(f"[SL FALLBACK] Exchange SL failed for {direction.upper()} {symbol} — using software SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")
                    available -= pos.margin
                    self._last_entry_time = time.time()
                    if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation"):
                        self._last_htf_entry_time = time.time()
                    logger.info(f"[ENTRY] {direction.upper()} {symbol} | Fill: {fill_price:.4f} | Margin: ${pos.margin:.2f} | Conf: {confidence}/7 | {signal.reason} | Strength: {signal.strength:.2f}")
                    _htf_adx_val = float(htf_df.iloc[-1].get("adx", 0)) if htf_df is not None and len(htf_df) > 0 else None
                    pos.entry_snapshot = self._log_entry_snapshot(symbol, direction, "5m_scalp", strat_name, signal.strength, fill_price, confidence, ob, flow, ohlcv_last=df.iloc[-1], ohlcv_df=df, htf_adx=_htf_adx_val, extra_tags=_shadow_gates or None)
                    # F6 (2026-07-17): tag entered trades — gate_tags was None on
                    # every main-path trade (all 235 htf_l2), blinding forensics.
                    # "none" (not None) when clean, so 'no active tags' is
                    # distinguishable from 'telemetry missing'.
                    _active_tags = [k for k, v in (_shadow_gates or {}).items() if v]
                    if _htf_adx_val is not None and _htf_adx_val >= Config.HTF_BLOCK_ADX_MIN:
                        _active_tags.append("sg_htf_adx_hi")
                    if (flow or {}).get("trade_count", 0) <= Config.HTF_BLOCK_TAPE_MAX:
                        _active_tags.append("sg_thin_tape")
                    pos.gate_tags = ",".join(_active_tags) if _active_tags else "none"
                    try:
                        self.risk._save_state()
                    except Exception as _e:
                        logger.debug(f"[SNAPSHOT] live save_state after entry failed: {_e}")
                    notifier.notify_entry(symbol, direction, fill_price, margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason, strategy=strat_name, confidence=confidence)
                else:
                    # Before declaring "signal lost", verify no position materialized on-exchange.
                    # Race window: our order-tracking thinks nothing filled, but a late fill
                    # could have created an orphan (real-money incident 2026-04-13).
                    # CRITICAL: use the pre-snapshot amount captured by _try_limit_entry so we
                    # don't mis-adopt a pre-existing manual position as "our fill".
                    if Config.is_live():
                        pre_snap = getattr(self.exchange, "_last_entry_pre_amount", None) or {}
                        pre_amt = 0.0
                        if pre_snap.get("symbol") == symbol and pre_snap.get("side") == direction:
                            pre_amt = float(pre_snap.get("pre_amount") or 0.0)
                        try:
                            gt = self.exchange._position_ground_truth(symbol, direction, pre_amount=pre_amt)
                        except Exception as _e:
                            gt = None
                            logger.error(f"[ENTRY SAFETY] ground-truth check failed for {symbol}: {_e}")
                        if gt:
                            gt_entry = float(gt.get("average") or price)
                            gt_amount = float(gt.get("filled") or 0)
                            if gt_amount <= 0:
                                logger.error(f"[ENTRY SAFETY] {symbol} ground-truth returned zero amount — refusing to adopt, logging 'signal lost'")
                                logger.error(f"[ENTRY] Order FAILED for {direction.upper()} {symbol} — signal lost")
                                continue
                            logger.warning(
                                f"[ENTRY SAFETY] {symbol} {direction.upper()} orphan detected after 'signal lost' — "
                                f"adopting position @ {gt_entry} (amount={gt_amount})"
                            )
                            self.risk.open_position(symbol, gt_entry, margin, side=direction, atr=atr_val, regime=regime, cycle=self.cycle_count, strategy=strat_name)
                            pos = self.risk.positions[symbol]
                            pos.amount = gt_amount
                            pos.margin = (gt_amount * gt_entry) / Config.LEVERAGE
                            pos.entry_strength = signal.strength
                            pos.confidence = confidence
                            pos.ensemble_layers = ",".join(layers)
                            sl_tp = self.exchange.place_sl_tp(symbol, direction, pos.amount, pos.stop_loss, pos.take_profit)
                            pos.sl_order_id = sl_tp.get("sl_order_id")
                            pos.tp_order_id = sl_tp.get("tp_order_id")
                            if pos.sl_order_id:
                                pos.exchange_sl_price = pos.stop_loss
                            if not pos.sl_order_id:
                                pos.sl_order_id = "software"
                            available -= pos.margin
                            self._last_entry_time = time.time()
                            if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation"):
                                self._last_htf_entry_time = time.time()
                            try:
                                self.risk._save_state()
                            except Exception as _e:
                                logger.warning(f"[ENTRY SAFETY] _save_state after orphan-adopt failed for {symbol}: {_e}")
                            try:
                                notifier.send(
                                    f"⚠️ ORPHAN ADOPTED on entry\n"
                                    f"{symbol} {direction.upper()}\n"
                                    f"Entry: {gt_entry} | Amount: {pos.amount}\n"
                                    f"SL: {pos.stop_loss:.4f} | TP: {pos.take_profit:.4f}"
                                )
                            except Exception as _e:
                                logger.warning(f"[ENTRY SAFETY] Telegram alert for orphan-adopt failed: {_e}")
                            notifier.notify_entry(symbol, direction, gt_entry, pos.margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason + " (orphan-adopted)", strategy=strat_name, confidence=confidence)
                            continue
                    logger.error(f"[ENTRY] Order FAILED for {direction.upper()} {symbol} — signal lost")

        # Evaluate strategy slots (paper slots simulate; live slots place real orders)
        # + ETH-TSM daily evaluator. Extracted to _evaluate_all_slots so the
        # .halt_main_entries path can service slots identically (2026-07-13).
        self._evaluate_all_slots(prices)

        # Log slot status
        for slot in self.slots:
            s = slot.stats_summary()
            mode = "PAPER" if slot.paper_mode else "LIVE"
            status = "KILLED" if slot.is_killed else "ACTIVE" if slot.is_active else "DISABLED"
            logger.info(f"[SLOT] {slot.slot_id} ({mode}/{status}) | {s['trades']} trades | WR: {s['wr']}% | PnL: ${s['pnl']}")

    def _thin_adx_blocked(self, strat_name: str, flow: dict | None,
                          htf_adx: float | None) -> bool:
        """F5 (2026-07-17): htf_l2 toxic-cell block — thin tape (trade_count
        <= HTF_BLOCK_TAPE_MAX) AND extended 1h trend (htf_adx >=
        HTF_BLOCK_ADX_MIN). Only the CONJUNCTION blocks: thin-only was +$6.86
        lifetime, high-ADX on an active tape only mildly negative; the
        conjunction was −$29.22 lifetime and 99% of July 2026's bleed
        (verified, in-sample — forward grading pre-registered for any
        un-halt). Missing tape data counts as thin (conservative); missing
        ADX allows (can't confirm the toxic half)."""
        if not Config.HTF_THIN_ADX_BLOCK_ENABLED:
            return False
        if strat_name != "htf_l2_anticipation":
            return False
        if htf_adx is None:
            return False
        return (htf_adx >= Config.HTF_BLOCK_ADX_MIN
                and (flow or {}).get("trade_count", 0) <= Config.HTF_BLOCK_TAPE_MAX)

    def _slot_entries_blocked(self) -> bool:
        """Fresh (per-call) global entry block for ALL slot entries, paper AND
        live: the .pause_trading sentinel or the main drawdown pause. Fresh
        file check on purpose — a sentinel written mid-cycle blocks the same
        cycle's slot entries, unlike the once-per-cycle _trading_paused flag."""
        _rm = getattr(self, "risk", None)
        return (os.path.exists(".pause_trading")
                or (_rm is not None
                    and getattr(_rm, "_drawdown_pause_until", 0) > time.time()))

    def _maybe_print_stats(self, real_balance: float, available: float,
                           margin_in_use: float) -> None:
        """Every-10-cycles `=== STATS ===` log line. Called early in _run_cycle,
        before any entry-halt early return, because four consumers parse it for
        balance/drawdown (monitor_daemon, web_dashboard, trading_desk,
        daily_report)."""
        if self.cycle_count % 10 != 0:
            return
        # Skip STATS when get_balance returned 0 with open positions —
        # almost certainly an API failure (401 / network). Logging
        # real_balance = 0 + margin_in_use causes false drawdown alerts
        # downstream (monitor_daemon parses STATS Balance — 2026-04-26 incident).
        if available > 0 or margin_in_use == 0:
            self.risk.print_stats(real_balance)
        else:
            logger.warning(
                f"[STATS] Skipping log — get_balance returned 0 with "
                f"${margin_in_use:.2f} margin in use (likely API failure)"
            )

    def _l2_live_writer_loop(self, interval_sec: float = 5.0) -> None:
        """Daemon thread: writes l2_snapshot.json every `interval_sec` from in-memory caches.
        No API calls — reads ws_feed (live) and _ob_depth_cache (populated by main loop)."""
        while self.running:
            try:
                pairs = list(self.active_pairs)
                accum: dict[str, dict] = {}
                for symbol in pairs:
                    flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
                    lp = self._ws_feed.last_price(symbol) if self._ws_feed else None
                    depth = self._ob_depth_cache.get(symbol, {})
                    accum[symbol] = {
                        "buy_ratio":         (flow or {}).get("buy_ratio"),
                        "cvd_slope":         (flow or {}).get("cvd_slope"),
                        "bid_depth_usdt":    depth.get("bid_depth_usdt"),
                        "ask_depth_usdt":    depth.get("ask_depth_usdt"),
                        "large_trade_bias":  (flow or {}).get("large_trade_bias"),
                        "trade_count":       (flow or {}).get("trade_count", 0),
                        "last_price":        lp[0] if lp else None,
                        "updated_at":        time.time(),
                    }
                _write_l2_snapshot(accum)
            except Exception as e:
                logger.debug(f"[L2_LIVE] writer tick failed: {e}")
            time.sleep(interval_sec)

    def _evaluate_all_slots(self, prices: dict):
        """Run the slot evaluators (generic strategy slots + the ETH-TSM and
        Donchian-ensemble daily state machines). Extracted 2026-07-13 so the
        .halt_main_entries path can service slots
        and their exits identically to the normal end-of-cycle call. Exception handling
        and log levels are preserved verbatim from the original inline call sites."""
        try:
            self._evaluate_slots(self.active_pairs, prices)
        except Exception as e:
            logger.debug(f"[PAPER] Slot evaluation error: {e}")
        # ETH-TSM-28 daily evaluator (2026-07-06): once-per-cycle state machine —
        # daily signal at the UTC day roll, entry/exit intents, leverage restore.
        # ERROR (not debug) on failure: this slot has no other evaluation path.
        try:
            self._evaluate_eth_tsm(prices)
        except Exception as e:
            logger.error(f"[TSM] evaluation error: {e}", exc_info=True)
        # Donchian-ensemble daily evaluator (2026-07-16): per-coin ensemble advance
        # at the UTC day roll + paper position sizing to BASE_NOTIONAL × w.
        # ERROR (not debug) on failure: these slots have no other evaluation path.
        try:
            self._evaluate_donchian(prices)
        except Exception as e:
            logger.error(f"[DONCHIAN] evaluation error: {e}", exc_info=True)

    def _evaluate_slots(self, active_pairs: list, prices: dict):
        """Evaluate strategy slots — paper slots simulate; live (promoted) slots place real orders."""
        for slot in self.slots:
            # NOTE: killed slots (is_active False) still run the EXIT block below —
            # skipping them entirely froze a DOGE position in 5m_narrow from 4/24 to
            # 6/11 (audit finding). The is_active guard now sits before entries only.

            strategy_fn = STRATEGIES.get(slot.strategy_name)
            if not strategy_fn:
                continue

            # --- Slot exits first (check existing slot positions, paper AND live) ---
            # Paper: all exits simulated here. Live: SL/TP enforced by exchange resting
            # orders + reconcile Path A (software touch-close would double-fire), but
            # cycle exits (trend-flip / adverse / time) execute real market closes.
            for symbol in list(slot.risk.positions.keys()):
                if symbol not in slot.risk.positions:
                    continue  # a demote triggered earlier in this loop already closed it
                price = prices.get(symbol)
                if not price:
                    logger.debug(f"[PAPER] {slot.slot_id} no price for {symbol}, skipping exit check")
                    continue
                pos = slot.risk.positions[symbol]

                # ST2.0: fixed-time hold (the backtested exit) takes priority. Hold is
                # per-slot via ST2_HOLD_CYCLES_BY_SLOT (ST2.0 = 20 cycles since 2026-06-16).
                if slot.strategy_name == "ST2.0":
                    _hold_cycles = ST2_HOLD_CYCLES_BY_SLOT.get(slot.slot_id, ST2_HOLD_CYCLES)
                    _held = self.cycle_count - getattr(pos, "entry_cycle", self.cycle_count)
                    if _held >= _hold_cycles:
                        self._close_slot_position(slot, symbol, pos, price, "st2_hold")
                        continue

                if slot.paper_mode:
                    # Check SL (paper only — live SL rests on the exchange)
                    if (pos.side == "long" and price <= pos.stop_loss) or \
                       (pos.side == "short" and price >= pos.stop_loss):
                        self._close_slot_position(slot, symbol, pos, price, "stop_loss")
                        continue

                    # Check TP (paper only — live TP rests on the exchange)
                    if (pos.side == "long" and price >= pos.take_profit) or \
                       (pos.side == "short" and price <= pos.take_profit):
                        self._close_slot_position(slot, symbol, pos, price, "take_profit")
                        continue

                # Trend-flip exit for htf_confluence_pullback positions
                if slot.strategy_name in ("htf_confluence_pullback", "htf_l2_anticipation"):
                    htf_df_tuple = self._htf_cache.get(symbol)
                    htf_df = htf_df_tuple[0] if htf_df_tuple else None
                    should_flip, flip_reason = _check_htf_trend_flip_exit(pos.side, htf_df)
                    if should_flip:
                        tag = "PAPER" if slot.paper_mode else "SLOT LIVE"
                        logger.info(f"[{tag} TREND-FLIP EXIT] {slot.slot_id} {symbol} {pos.side} — 1h EMA flipped")
                        self._close_slot_position(slot, symbol, pos, price, flip_reason)
                        continue

                # Check adverse exit — per-slot threshold (ST2.0 = -6% loss-cut; other
                # slots pass None and inherit the global -999/off). The loss-cut MUST
                # fill, so _close_slot_position forces a taker exit for "adverse_exit".
                if pos.should_adverse_exit(self.cycle_count, price,
                                           threshold=slot.adverse_exit_roi,
                                           cycles=slot.adverse_exit_cycles):
                    self._close_slot_position(slot, symbol, pos, price, "adverse_exit")
                    continue

                # Check time exit
                should_exit, is_hard = pos.should_time_exit(self.cycle_count, price)
                if should_exit:
                    reason = "hard_time_exit" if is_hard else "time_exit"
                    self._close_slot_position(slot, symbol, pos, price, reason)
                    continue

                # Durable trail ratchet — LIVE opt-in slots only (no-op otherwise).
                # Runs AFTER the exit checks above: if any fired it already `continue`d,
                # so this never amends an SL on a position being closed this cycle. The
                # amend rests on the exchange, so the profit-lock survives a host sleep.
                self._ratchet_slot_durable_sl(slot, symbol, pos, price)

            # --- Paper entries ---
            if not slot.is_active:
                continue  # killed slots close out open positions above but never re-enter
            _patient_missed = False  # one long-patience entry attempt per slot per
                                     # cycle: bounds the worst-case cycle stall
                                     # (~45+20s) under the ~120s watchdog budget
                                     # (alarm(180) covers cycle + 60s sleep)
            for symbol in active_pairs:
                if _patient_missed:
                    break
                if not slot.can_enter(symbol, self.slots):
                    continue

                price = prices.get(symbol)
                if not price:
                    continue

                try:
                    # Reuse WebSocket candle data (same as live bot — no extra REST calls)
                    if self._ws_feed and not self._ws_feed.is_stale(symbol):
                        df = self._ws_feed.get_ohlcv(symbol, limit=Config.CANDLE_LOOKBACK)
                    else:
                        df = self.exchange.get_ohlcv(symbol, slot.timeframe, limit=Config.CANDLE_LOOKBACK)
                    if df is None or len(df) < 50:
                        continue
                    df = add_all_indicators(df)
                    ob = self.exchange.get_order_book(symbol)
                    htf_df = self._fetch_htf_data(symbol)
                    _flow_for_strat = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None

                    # Build candidate signal list.
                    # For 5m_narrow ONLY: mirror every sub-strategy the live `confluence`
                    # router considers, so narrow filters can accept/reject each independently
                    # (instead of only seeing the single strongest signal confluence returns).
                    # Other slots keep their single-strategy behavior unchanged.
                    candidate_signals = []
                    if slot.slot_id == "5m_narrow":
                        try:
                            from strategies import (
                                htf_confluence_pullback,
                                htf_l2_anticipation,
                                htf_confluence_vwap,
                                bb_mean_reversion_strategy,
                                momentum_continuation_strategy,
                                liquidation_cascade_strategy,
                                htf_momentum_strategy,
                            )
                            _htf_adx = htf_df.iloc[-1].get("adx", 25) if htf_df is not None and len(htf_df) > 0 else 25
                            _hurst_v = df.iloc[-1].get("hurst", 0.5) if "hurst" in df.columns else 0.5
                            # Same gating confluence_strategy applies before routing
                            _chop_v = df.iloc[-1].get("chop", 50)
                            _confluence_ok = (htf_df is not None and len(htf_df) >= 30 and _chop_v <= 65 and len(df) >= 30)
                            if _confluence_ok:
                                if _htf_adx >= 20:
                                    candidate_signals.append(htf_confluence_pullback(df, ob, htf_df))
                                    candidate_signals.append(htf_l2_anticipation(df, ob, htf_df, _flow_for_strat))
                                if _htf_adx >= 25:
                                    candidate_signals.append(momentum_continuation_strategy(df, ob))
                                if _htf_adx < 25:
                                    candidate_signals.append(htf_confluence_vwap(df, ob, htf_df))
                                    if _hurst_v < 0.50:
                                        candidate_signals.append(bb_mean_reversion_strategy(df, ob))
                            # Top-level strategies the bot has registered but confluence doesn't call
                            try:
                                candidate_signals.append(htf_momentum_strategy(df, ob, htf_df=htf_df))
                            except TypeError:
                                candidate_signals.append(htf_momentum_strategy(df, ob))
                            candidate_signals.append(liquidation_cascade_strategy(df, ob))
                        except Exception as _narrow_build_err:
                            logger.debug(f"[PAPER] [NARROW] {symbol} candidate build failed: {_narrow_build_err}")
                            continue
                    elif slot.strategy_name == "ST2.0":
                        # ST2.0 needs BOTH book (ob) and tape (flow) — the generic
                        # call path doesn't pass flow, so build the signal directly.
                        candidate_signals.append(st2_absorption(df, ob, _flow_for_strat))
                    elif slot.strategy_name == "htf_l2_anticipation":
                        # htf_l2 needs tape (flow) — the generic call path doesn't
                        # pass it (same gap ST2.0 hit above).
                        candidate_signals.append(strategy_fn(df, ob, htf_df=htf_df, flow=_flow_for_strat))
                    else:
                        try:
                            _s = strategy_fn(df, ob, htf_df=htf_df)
                        except TypeError:
                            _s = strategy_fn(df, ob)
                        candidate_signals.append(_s)
                except Exception as e:
                    logger.debug(f"[PAPER] {slot.slot_id} error on {symbol}: {e}")
                    continue

                # Iterate each candidate signal (1 for standard slots, N for 5m_narrow)
                _entered_this_symbol = False
                for signal in candidate_signals:
                    if _entered_this_symbol:
                        break  # slot capacity respected — one entry per symbol per cycle
                    if signal is None or signal.signal == Signal.HOLD:
                        if signal is not None and "SMA+VWAP gate" in signal.reason:
                            logger.debug(f"[PAPER] {slot.slot_id} {symbol}: {signal.reason}")
                        continue
                    if not _meets_min_strength(signal.strength, 0.80):
                        logger.debug(f"[PAPER] {slot.slot_id} {symbol}: strength {signal.strength:.2f} < 0.80")
                        continue

                    direction = "long" if signal.signal == Signal.BUY else "short"

                    # --- 5m_narrow extra filters (shadow-only, never affects live) ---
                    if slot.slot_id == "5m_narrow":
                        try:
                            # Filter 1: symbol blacklist extension
                            if "SUI" in symbol or "LINK" in symbol:
                                slot.bump_blocked("blocked_symbol")
                                logger.debug(f"[PAPER] [NARROW FILTER] {symbol} blocked_symbol")
                                continue
                            # Filter 2: hour block extension (UTC hour 0 = PT 5 PM PDT, UTC hour 17 = PT 10 AM PDT)
                            _narrow_hr = datetime.datetime.now(datetime.timezone.utc).hour
                            if _narrow_hr in (0, 17):
                                slot.bump_blocked("blocked_hour")
                                logger.debug(f"[PAPER] [NARROW FILTER] {symbol} blocked_hour UTC{_narrow_hr}")
                                continue
                            # Filter 3: ensemble tightening for htf_confluence_pullback (>=5/7 vs live 4/7)
                            _narrow_strat = _extract_strategy_name(signal.reason)
                            if _narrow_strat == "htf_confluence_pullback":
                                _narrow_conf, _ = self._compute_confidence(
                                    direction, df, ob, htf_df=htf_df,
                                    cvd_data=self._ws_feed.get_order_flow(symbol) if self._ws_feed else None,
                                    hurst_val=None, funding_data=None,
                                    strategy=_narrow_strat,
                                    flow=self._ws_feed.get_order_flow(symbol) if self._ws_feed else None,
                                )
                                if _narrow_conf < 5:
                                    slot.bump_blocked("blocked_ensemble")
                                    logger.debug(f"[PAPER] [NARROW FILTER] {symbol} blocked_ensemble {_narrow_conf}/7<5")
                                    continue
                        except Exception as _ne:
                            logger.debug(f"[PAPER] [NARROW FILTER] {symbol} filter error (skipping signal): {_ne}")
                            continue

                    # --- ST2.0 LIVE entry filters (promoted 2026-06-16, proposal
                    # 8df1250186dd, owner-approved): extra gates on top of the base
                    # absorption signal. These now GATE REAL-MONEY entries. NOTE
                    # spread_pct>=0.039 is artifact-suspect (wide spread -> worse real
                    # fills) — deployed live per explicit owner approval; being watched. ---
                    if slot.slot_id == "ST2.0":
                        _f = _flow_for_strat or {}
                        _cvd = _f.get("cvd_slope", 0.0)
                        _br = _f.get("buy_ratio", 0.5)
                        _tc = _f.get("trade_count", 0)
                        _spread = (ob or {}).get("spread_pct", 0.0)
                        if not (_cvd <= -0.374 and _spread >= 0.039 and _br <= 0.85):  # trade_count>=24 dropped 2026-06-16 to match approved proposal 8df1250186dd
                            slot.bump_blocked("st2_filter")
                            logger.debug(f"[SLOT] [ST2.0 FILTER] {symbol} blocked "
                                         f"(cvd={_cvd:.3f} spread={_spread:.4f} br={_br:.2f} tc={_tc})")
                            continue

                    # --- 5m_mean_revert RSI floor (2026-07-02, owner-approved
                    # forward-test of the 2026-06-30 90d replay lead): deep-oversold
                    # longs are the falling-knife cohort (RSI<22 n=21 maker −$4.08;
                    # band 22–30 n=132 +$12.05 — reports/mr_replay_90d.json). Blocks
                    # LONGS with RSI(7) below the floor; shorts and other slots
                    # untouched. 0.0 disables. Fails open when no RSI in reason. ---
                    if (slot.slot_id == "5m_mean_revert" and direction == "long"
                            and Config.MEAN_REVERT_LONG_RSI_MIN > 0.0):
                        _mr_rsi = _rsi_from_reason(signal.reason)
                        if _mr_rsi is not None and _mr_rsi < Config.MEAN_REVERT_LONG_RSI_MIN:
                            slot.bump_blocked("mr_rsi_floor")
                            logger.debug(f"[SLOT] [MR RSI FLOOR] {symbol} LONG blocked — "
                                         f"RSI(7)={_mr_rsi:.1f} < {Config.MEAN_REVERT_LONG_RSI_MIN:.1f}")
                            continue

                    # 1h ADX for this signal — used by the HTF_L2 thin∧ADX
                    # gate below and carried into the entry snapshot for EVERY
                    # slot (telemetry parity with the main path, 2026-07-18).
                    _slot_htf_adx = (float(htf_df.iloc[-1].get("adx", 0))
                                     if htf_df is not None and len(htf_df) > 0 else None)

                    # --- HTF_L2 ACTIVE thin-tape ∧ high-1h-ADX gate
                    # (2026-07-18): the F5 block the halted main path carries,
                    # ACTIVE here so the slot forward-tests the residual
                    # book (toxic cell excluded), not the known loss engine. ---
                    if slot.slot_id == "HTF_L2":
                        if self._thin_adx_blocked("htf_l2_anticipation", _flow_for_strat, _slot_htf_adx):
                            slot.bump_blocked("thin_adx")
                            self._log_gotaway("thin_adx_slot", symbol, direction,
                                              "htf_l2_anticipation", signal.strength, 0, price,
                                              ob, _flow_for_strat, df)
                            logger.info(f"[PAPER] [THIN-ADX] HTF_L2 {symbol} {direction.upper()} blocked "
                                        f"(adx={_slot_htf_adx}, tc={(_flow_for_strat or {}).get('trade_count', 0)})")
                            continue

                    margin = (slot.trade_amount_usdt if slot.trade_amount_usdt is not None
                              else Config.TRADE_AMOUNT_USDT)
                    atr_val = df.iloc[-2].get("atr", 0) if len(df) > 1 else 0

                    # Apply OB + Tape gates to slots. ST2.0 BYPASSES these — its
                    # whole thesis is to short into the bid-heavy + buying setup that
                    # these gates exist to block (short blocked if imb>0.25/buy_ratio>0.55).
                    # L2 Orderbook gate
                    if slot.strategy_name != "ST2.0" and ob is not None:
                        ob_imb = ob.get("imbalance", 0.0)
                        ob_bwalls = ob.get("bid_walls", [])
                        ob_awalls = ob.get("ask_walls", [])
                        ob_spread = ob.get("spread_pct", 0.0)
                        if direction == "long" and ob_imb < -0.25:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} LONG blocked — ask imbalance {ob_imb:.2f}")
                            continue
                        if direction == "short" and ob_imb > 0.25:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} SHORT blocked — bid imbalance {ob_imb:.2f}")
                            continue
                        if direction == "long" and ob_awalls and not ob_bwalls:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} LONG blocked — unmatched ask wall")
                            continue
                        if direction == "short" and ob_bwalls and not ob_awalls:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} SHORT blocked — unmatched bid wall")
                            continue
                        if ob_spread > 0.15:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} blocked — wide spread {ob_spread:.3f}%")
                            continue
                    # Tape gate (ST2.0 bypasses — see OB gate note above)
                    flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
                    if slot.strategy_name != "ST2.0" and flow and flow.get("trade_count", 0) > 20:
                        buy_ratio = flow.get("buy_ratio", 0.5)
                        cvd_slope = flow.get("cvd_slope", 0.0)
                        divergence = flow.get("divergence")
                        lt_bias = flow.get("large_trade_bias", 0.0)
                        _paper_strat = _extract_strategy_name(signal.reason)
                        # buy_ratio check via helper — bb_mean_reversion SHORTS exempt
                        # (replay-gated carve-out 2026-07-12, see _tape_gate_blocks_buy_ratio)
                        if _tape_gate_blocks_buy_ratio(_paper_strat, direction, buy_ratio):
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} {direction.upper()} blocked — buy_ratio {buy_ratio:.0%}")
                            continue
                        # CVD slope gate — carve-out for pullback/reversion (matches live bot line 1037)
                        if _paper_strat not in ("htf_confluence_pullback", "bb_mean_reversion"):
                            if direction == "long" and cvd_slope < -0.3:
                                logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — CVD slope {cvd_slope:.2f}")
                                continue
                            if direction == "short" and cvd_slope > 0.3:
                                logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — CVD slope {cvd_slope:.2f}")
                                continue
                        if direction == "long" and divergence == "bearish":
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — bearish divergence")
                            continue
                        if direction == "short" and divergence == "bullish":
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — bullish divergence")
                            continue
                        if direction == "long" and lt_bias < -0.3:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — large trade bias {lt_bias:.2f}")
                            continue
                        if direction == "short" and lt_bias > 0.3:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — large trade bias {lt_bias:.2f}")
                            continue

                    # Shadow-tag: which LIVE gates would have blocked this trade?
                    _gate_tags = []
                    _strat_name = _extract_strategy_name(signal.reason)
                    _conf, _layers = self._compute_confidence(
                        direction, df, ob, htf_df=htf_df,
                        cvd_data=self._ws_feed.get_order_flow(symbol) if self._ws_feed else None,
                        hurst_val=None, funding_data=None,
                        strategy=_strat_name, flow=flow
                    )
                    # HTF_L2 ensemble HARD block (2026-07-18): the main
                    # path enforces conf>=4 before entry — the slot must trade
                    # the same book, so conf<4 blocks here (not shadow-tagged).
                    if slot.slot_id == "HTF_L2" and _conf < 4:
                        slot.bump_blocked("ensemble_confidence")
                        logger.info(f"[PAPER] [ENSEMBLE] HTF_L2 {symbol} {direction.upper()} "
                                    f"blocked — confidence {_conf}/7 < 4")
                        continue
                    if _conf < 4:
                        _gate_tags.append(f"confidence:{_conf}/7<4")
                    _utc_hr = datetime.datetime.now(datetime.timezone.utc).hour
                    # Mirror the LIVE config (24h trading = empty set → tag never fires);
                    # was a hardcoded copy of the retired blocked-hours set.
                    if _utc_hr in Config.TRADING_BLOCKED_HOURS_UTC:
                        _gate_tags.append(f"time_block:UTC{_utc_hr}")
                    if time.time() - self._last_entry_time < 120:
                        _gate_tags.append("global_cooldown")
                    _regime_snap = self._classify_regime(df.iloc[-1], df)
                    if _regime_snap.get("label") == "QUIET":
                        # Mirrors the live gate: QUIET blocks unconditionally since
                        # 2026-06-12 (flow-confirmation exemption closed)
                        _gate_tags.append("quiet_regime")
                    if flow and flow.get("divergence"):
                        if direction == "long" and flow["divergence"] == "bearish":
                            _gate_tags.append("divergence_bearish")
                        if direction == "short" and flow["divergence"] == "bullish":
                            _gate_tags.append("divergence_bullish")
                    _would_block = len(_gate_tags) > 0
                    # F6 cell tags for HTF_L2 entered trades (2026-07-18):
                    # mirror the main-path convention (sg_htf_adx_hi/sg_thin_tape)
                    # AFTER _would_block — these are cell markers, not gates, so
                    # they must not print a [WOULD BLOCK] label.
                    if slot.slot_id == "HTF_L2":
                        if _slot_htf_adx is not None and _slot_htf_adx >= Config.HTF_BLOCK_ADX_MIN:
                            _gate_tags.append("sg_htf_adx_hi")
                        if (flow or {}).get("trade_count", 0) <= Config.HTF_BLOCK_TAPE_MAX:
                            _gate_tags.append("sg_thin_tape")
                    _tag_str = ",".join(_gate_tags) if _gate_tags else "none"

                    # For 5m_narrow, record the actual routed sub-strategy, not the slot's
                    # generic "confluence" label — preserves per-strategy attribution in logs.
                    _entry_strategy_name = _strat_name if (slot.slot_id == "5m_narrow" and _strat_name) else slot.strategy_name

                    _block_label = f" [WOULD BLOCK: {_tag_str}]" if _would_block else ""

                    if slot.paper_mode:
                        # F1: global pause blocks ALL entries, paper included —
                        # the sentinel's own log line says "skipping all
                        # entries", and paper entries during a pause would
                        # pollute paper ledgers and slot stats.
                        if self._slot_entries_blocked():
                            logger.info(f"[PAPER] {slot.slot_id} {symbol} entry blocked — account halt")
                            continue
                        slot.risk.open_position(
                            symbol, price, margin, side=direction,
                            atr=atr_val, regime="medium",
                            cycle=self.cycle_count,
                            strategy=_entry_strategy_name,
                            sl_pct=slot.sl_percent, tp_pct=slot.tp_percent
                        )
                        notifier.notify_paper_entry(
                            symbol, direction, price, margin,
                            signal.strength, signal.reason, slot=slot.slot_id
                        )
                        logger.info(
                            f"[PAPER] {slot.slot_id} ENTRY {direction.upper()} {symbol} | "
                            f"Price: {price:.4f} | Strength: {signal.strength:.2f} | {signal.reason}{_block_label}"
                        )
                    else:
                        # --- LIVE slot entry (spec 2026-06-12) ---
                        # account halts: pause sentinel + main drawdown pause (risk_manager.py:351)
                        if self._slot_entries_blocked():
                            logger.info(f"[SLOT LIVE] {slot.slot_id} {symbol} entry blocked — account halt")
                            continue
                        # ETH ownership rule (ETH-TSM-28, 2026-07-06): same skip the main
                        # entry path applies — one-way mode would merge a scalper-slot ETH
                        # fill into the TSM position (and at the wrong 3x leverage).
                        _tsm_lock = self._tsm_locks_symbol(symbol)
                        if _tsm_lock:
                            self._tsm_notify_ownership(
                                f"slot_skip_{slot.slot_id}",
                                f"slot {slot.slot_id} ETH entry skipped ({_tsm_lock})")
                            continue
                        try:
                            # Per-slot entry patience (2026-07-03): first attempt may
                            # rest longer than the 20s default; the re-quote below
                            # deliberately keeps the 20s default so the worst-case
                            # entry stall stays bounded (~45+20s per signal).
                            _patience = (slot.entry_patience_s
                                         if slot.entry_patience_s else 20.0)
                            order = (self.exchange.open_long(symbol, margin, price,
                                                             patience_s=_patience)
                                     if direction == "long"
                                     else self.exchange.open_short(symbol, margin, price,
                                                                   patience_s=_patience))
                            # --- Bounded maker re-quote (2026-07-02, owner-approved): the
                            # slot's PostOnly entries missed 11/13 attempts and the misses
                            # were net winners (+$3.55, reports/mr_missed_fills.json). On a
                            # miss, re-place at the fresh touch — still PostOnly, never
                            # taker — unless price ran adversely past the drift cap.
                            # Slot-keyed (default off; only 5m_mean_revert opts in);
                            # exchange._try_limit_entry untouched -> main bot unaffected. ---
                            if not order and slot.requote_attempts > 0:
                                for _rq in range(slot.requote_attempts):
                                    # Zombie guard (review hardening): if the first
                                    # order still rests (cancel AND status fetch both
                                    # failed), never stack a second entry on it. On any
                                    # doubt, skip the re-quote — miss is the safe state.
                                    try:
                                        _resting = self.exchange.client.fetch_open_orders(symbol) or []
                                    except Exception as _zg_err:
                                        logger.info(f"[SLOT LIVE] [MR REQUOTE] {slot.slot_id} {symbol} "
                                                    f"zombie-check failed ({_zg_err}) — skipping re-quote")
                                        break
                                    _entry_side = "buy" if direction == "long" else "sell"
                                    if any(o.get("side") == _entry_side
                                           and not (o.get("reduceOnly")
                                                    or (o.get("info") or {}).get("reduceOnly"))
                                           for o in _resting):
                                        slot.bump_blocked("requote_abort_zombie")
                                        logger.info(f"[SLOT LIVE] [MR REQUOTE] {slot.slot_id} {symbol} "
                                                    f"first order still resting — skipping re-quote")
                                        break
                                    _rq_ob = self.exchange.get_order_book(symbol, depth=5)
                                    _touch = (_rq_ob or {}).get(
                                        "best_bid" if direction == "long" else "best_ask")
                                    if not _touch:
                                        break
                                    _rq_drift = _requote_drift_pct(direction, price, _touch)
                                    if _rq_drift > Config.SLOT_REQUOTE_MAX_DRIFT_PCT:
                                        slot.bump_blocked("requote_abort_drift")
                                        logger.info(
                                            f"[SLOT LIVE] [MR REQUOTE] {slot.slot_id} {symbol} "
                                            f"{direction} abort — adverse drift {_rq_drift:.3f}% "
                                            f"> {Config.SLOT_REQUOTE_MAX_DRIFT_PCT}%")
                                        break
                                    logger.info(
                                        f"[SLOT LIVE] [MR REQUOTE] {slot.slot_id} {symbol} "
                                        f"{direction} attempt {_rq + 1}/{slot.requote_attempts} "
                                        f"@ {_touch} (drift {_rq_drift:+.3f}%)")
                                    order = (self.exchange.open_long(symbol, margin, _touch)
                                             if direction == "long"
                                             else self.exchange.open_short(symbol, margin, _touch))
                                    if order:
                                        slot.bump_blocked("requote_fill")
                                        logger.info(
                                            f"[SLOT LIVE] [MR REQUOTE] {slot.slot_id} {symbol} "
                                            f"{direction} FILLED on re-quote")
                                        break
                                    slot.bump_blocked("requote_miss")
                            if not order:
                                # Log the entry conditions present at a MISS (mirrors the fill
                                # line below, whose {signal.reason} carries imb/br/tc for ST2.0)
                                # so fill-vs-miss can finally be compared — the instrumentation
                                # gap that blocked the 2026-06-20 execution analysis.
                                logger.info(f"[SLOT LIVE] {slot.slot_id} {symbol} {direction} — no fill (PostOnly miss), skipping | {signal.reason}")
                                if _patience > 20.0:
                                    _patient_missed = True  # no second patient stall this cycle
                                    break
                                continue
                            fill_price = self._extract_fill_price(order, price)
                            slot.risk.open_position(symbol, fill_price, margin, side=direction,
                                                    atr=atr_val, regime="medium",
                                                    cycle=self.cycle_count,
                                                    strategy=_entry_strategy_name,
                                                    sl_pct=slot.sl_percent, tp_pct=slot.tp_percent)
                            live_pos = slot.risk.positions[symbol]
                            fill_amount = self._extract_fill_amount(order, live_pos.amount)
                            actual_margin = (fill_amount * fill_price) / Config.LEVERAGE
                            _slot_amt = (slot.trade_amount_usdt if slot.trade_amount_usdt is not None
                                         else float(os.getenv("MIN_TRADE_MARGIN", "10.0")))
                            _min_margin = _slot_amt * 0.5
                            if actual_margin < _min_margin:
                                logger.warning(f"[SLOT LIVE] {slot.slot_id} {symbol} partial fill ${actual_margin:.4f} < ${_min_margin:.2f} — closing crumb")
                                self.exchange.cancel_open_orders(symbol)
                                closed = (self.exchange.close_long(symbol, fill_amount) if direction == "long"
                                          else self.exchange.close_short(symbol, fill_amount))
                                if closed:
                                    slot.risk.close_position(symbol, fill_price, "min_margin_skip", mode="live")
                                else:
                                    logger.error(f"[SLOT LIVE] {slot.slot_id} {symbol} crumb close FAILED — reconcile will catch")
                                continue
                            live_pos.amount = fill_amount
                            live_pos.margin = actual_margin
                            live_pos.entry_strength = signal.strength
                            sl_tp = self.exchange.place_sl_tp(symbol, direction, fill_amount,
                                                              live_pos.stop_loss, live_pos.take_profit)
                            live_pos.sl_order_id = sl_tp.get("sl_order_id") or "software"
                            live_pos.tp_order_id = sl_tp.get("tp_order_id")
                            if sl_tp.get("sl_order_id"):
                                live_pos.exchange_sl_price = live_pos.stop_loss
                            else:
                                logger.warning(f"[SLOT LIVE] [SL FALLBACK] {slot.slot_id} {symbol} exchange SL failed — software SL@{live_pos.stop_loss:.4f}")
                            notifier.notify_entry(symbol, direction, fill_price, live_pos.margin,
                                                  live_pos.stop_loss, live_pos.take_profit,
                                                  signal.strength, f"[slot {slot.slot_id}] {signal.reason}",
                                                  strategy=_entry_strategy_name)
                            logger.info(f"[SLOT LIVE] {slot.slot_id} ENTRY {direction.upper()} {symbol} | Fill: {fill_price:.4f} | Margin: ${live_pos.margin:.2f} | {signal.reason}")
                            # A live slot fill is a real account entry — arm the global
                            # anti-clustering cooldown just like main-bot entries do.
                            self._last_entry_time = time.time()
                        except Exception as _le:
                            logger.error(f"[SLOT LIVE] {slot.slot_id} {symbol} entry sequence failed: {_le} — "
                                         f"any landed fill will be adopted by the orphan scanner; forcing global cooldown")
                            self._last_entry_time = time.time()
                            try:
                                notifier.send(f"⚠️ [SLOT LIVE] {slot.slot_id} {symbol} entry sequence error: {str(_le)[:120]} — check for naked position")
                            except Exception:
                                pass
                            continue

                    # --- Shared tail (paper + live) ---
                    slot.total_entries += 1
                    _entered_this_symbol = True
                    entry_px = price if slot.paper_mode else fill_price
                    # ob (fetched at the top of this symbol loop, used by the OB gate +
                    # confidence calc) MUST be passed here — a hardcoded None was the
                    # ob:null bug that blinded the ST2.0 lab (Phase 0 fix 2026-06-19).
                    # Telemetry parity (2026-07-18): slot snapshots used to log a
                    # literal confidence=0 and no htf_adx — the computed _conf and
                    # the 1h ADX now flow through, matching the main path.
                    snap = self._log_entry_snapshot(symbol, direction, slot.slot_id, _entry_strategy_name, signal.strength, entry_px, _conf, ob, flow, ohlcv_last=df.iloc[-1] if len(df) > 0 else None, ohlcv_df=df if len(df) >= 20 else None, htf_adx=_slot_htf_adx)
                    if symbol in slot.risk.positions:
                        slot.risk.positions[symbol].entry_snapshot = snap
                        slot.risk.positions[symbol].gate_tags = _tag_str
                        try:
                            slot.risk._save_state()
                        except Exception as _e:
                            logger.debug(f"[SNAPSHOT] {slot.slot_id} save_state after entry failed: {_e}")

    @staticmethod
    def _classify_regime(last, df=None) -> dict:
        """Classify market regime from OHLCV indicator row. Pure data, no gates."""
        try:
            close = float(last.get("close", 0))
            adx = float(last.get("adx", 0))
            atr = float(last.get("atr", 0))
            ema9 = float(last.get("ema_9", 0))
            ema21 = float(last.get("ema_21", 0))
            ema50 = float(last.get("ema_50", 0))
            ema200 = float(last.get("ema_200", 0))
            vol = float(last.get("volume", 0))
            vol_avg = float(df["volume"].iloc[-20:].mean()) if df is not None and len(df) >= 20 else 0
        except (TypeError, ValueError):
            return {"label": "UNKNOWN"}

        atr_pct = (atr / close) if close > 0 else 0
        vol_ratio = (vol / vol_avg) if vol_avg > 0 else 1.0
        above_ema200 = close > ema200 if ema200 > 0 else True
        stack_bull = ema9 > ema21 > ema50 > 0
        stack_bear = 0 < ema9 < ema21 < ema50

        if atr_pct > 0.015 or vol_ratio > 2.5:
            label = "VOLATILE"
        elif adx >= 25 and stack_bull and above_ema200:
            label = "TRENDING_UP"
        elif adx >= 25 and stack_bear and not above_ema200:
            label = "TRENDING_DOWN"
        elif adx < 20:
            label = "CHOPPY"
        else:
            label = "QUIET"

        return {
            "label": label,
            "adx": round(adx, 1),
            "atr_pct": round(atr_pct, 5),
            "above_ema200": above_ema200,
            "ema_stack_bull": stack_bull,
            "ema_stack_bear": stack_bear,
            "vol_ratio": round(vol_ratio, 2),
        }

    def _log_gotaway(self, reason: str, symbol: str, direction: str, strategy: str,
                     strength: float, confidence: int, price: float,
                     ob: dict | None, flow: dict | None, df=None):
        """Log a trade that was blocked by defensive gates for later analysis."""
        import json as _json
        entry = {
            "ts": int(time.time()),
            "reason": reason,
            "symbol": symbol,
            "direction": direction,
            "strategy": strategy,
            "strength": round(strength, 3),
            "confidence": confidence,
            "price": round(price, 6),
            "ob": {
                "imbalance": round(ob.get("imbalance", 0), 3),
                "spread_pct": round(ob.get("spread_pct", 0), 4),
            } if ob else None,
            "flow": {
                "buy_ratio": round(flow.get("buy_ratio", 0), 3),
                "cvd_slope": round(flow.get("cvd_slope", 0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
                "trade_count": flow.get("trade_count", 0),
            } if flow else None,
            "regime": self._classify_regime(df.iloc[-1], df) if df is not None and len(df) > 0 else None,
        }
        try:
            with open("logs/gotAway.jsonl", "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception:
            pass

    def _log_flow_snapshot(self, symbol: str, ob: dict | None, flow: dict | None,
                           price: float | None = None) -> None:
        """Append per-cycle flow + orderbook snapshot to JSONL for backtester replay.
        Captures EVERY pair scan (not just entries) so the offline backtester can
        reconstruct what the bot saw at any moment. See docs/superpowers/specs/
        2026-05-07-calibrated-backtester-design.md (capture-forward decision)."""
        if flow is None or flow.get("trade_count", 0) == 0:
            return  # skip empty flow (WS still seeding)

        def _safe(v, default=None):
            """Coerce NaN/inf to default — stdlib json.dumps raises on NaN by default."""
            if v is None:
                return default
            try:
                f = float(v)
                if f != f or f in (float("inf"), float("-inf")):
                    return default
                return f
            except (TypeError, ValueError):
                return v

        snap = {
            "ts": int(time.time()),
            "symbol": symbol,
            "price": round(_safe(price, 0.0), 6) if price is not None else None,
            "ob": {
                "imbalance": round(_safe(ob.get("imbalance"), 0.0), 3),
                "bid_walls": len(ob.get("bid_walls", [])),
                "ask_walls": len(ob.get("ask_walls", [])),
                "spread_pct": round(_safe(ob.get("spread_pct"), 0.0), 4),
                "bid_depth_usdt": _safe(ob.get("bid_depth_usdt")),
                "ask_depth_usdt": _safe(ob.get("ask_depth_usdt")),
                "illiquid": bool(ob.get("illiquid", False)),
            } if ob else None,
            "flow": {
                "buy_ratio": round(_safe(flow.get("buy_ratio"), 0.5), 3),
                "cvd_slope": round(_safe(flow.get("cvd_slope"), 0.0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(_safe(flow.get("large_trade_bias"), 0.0), 3),
                "trade_count": int(flow.get("trade_count", 0)),
            },
        }
        try:
            with open("logs/flow_capture.jsonl", "a") as f:
                f.write(json.dumps(snap) + "\n")
        except Exception as e:
            logger.debug(f"[FLOW CAPTURE] write failed: {e}")

    def _live_exit_watcher_loop(self) -> None:
        """Tier 2: enforce software exit levels (trailing/SL/TP) against the live
        WS price every ~1s. Enforcement-only — never ratchets levels (that stays
        on the 60s cycle). Claims symbols in self._closing so the cycle and the
        watcher can never double-close. Additive: any failure leaves the position
        for the 60s cycle to handle exactly as before.
        Spec: docs/superpowers/specs/2026-06-11-live-exit-watcher-design.md
        KNOWN TRADE-OFF (Mar 26 lesson): 1s enforcement fires on intra-minute
        wicks at the current trail level that the 60s loop would have survived —
        measured forward via [LIVE EXIT] logs vs cycle exits."""
        fail_cooldown: dict = {}   # symbol -> retry-not-before ts (failed closes back off 30s)
        last_err_alert = 0.0       # throttle Telegram on persistent iteration errors
        while self.running:
            try:
                time.sleep(1.0)
                if not self.risk.positions or self._ws_feed is None:
                    continue
                for symbol in list(self.risk.positions.keys()):
                    if time.time() < fail_cooldown.get(symbol, 0):
                        continue  # recent failed close — let the 60s cycle retry, don't hammer at 1Hz
                    lp = self._ws_feed.last_price(symbol)
                    if lp is None or lp[1] > 10.0:
                        continue  # stale/no WS — the 60s cycle stays the authority
                    price = lp[0]
                    with self._pos_lock:
                        if symbol in self._closing or symbol not in self.risk.positions:
                            self._tp_skip_since.pop(symbol, None)
                            continue
                        reason = self.risk.evaluate_exit(symbol, price)
                        if reason is None:
                            # Breach gone — reset the strand-guard clock so an old
                            # timestamp can't trigger instant enforcement later
                            self._tp_skip_since.pop(symbol, None)
                            continue
                        if reason == "take_profit":
                            # TP race fix: an exchange limit TP resting at this level
                            # always wins (maker, already queued) — enforcing here just
                            # double-closes into 11011. If it filled, the 60s [SYNC]
                            # reconciles; software-managed TPs still enforced.
                            # Strand guard: a live limit the market has crossed must
                            # fill within seconds — if the breach persists 90s the
                            # order is gone (cancelled/rejected), so enforce anyway.
                            tp_id = self.risk.positions[symbol].tp_order_id
                            if tp_id and tp_id != "software":
                                _first = self._tp_skip_since.setdefault(symbol, time.time())
                                if time.time() - _first < 90:
                                    continue
                                logger.warning(f"[LIVE EXIT] {symbol} TP breach >90s with resting TP unfilled — order presumed gone, enforcing")
                        self._tp_skip_since.pop(symbol, None)
                        self._closing.add(symbol)
                    try:
                        pos = self.risk.positions.get(symbol)
                        if pos is None:
                            continue
                        logger.info(f"[LIVE EXIT] {symbol} {reason} @ {price:.6f} (WS age {lp[1]:.1f}s)")
                        if pos.side == "long":
                            order = self.exchange.close_long(symbol, pos.amount)
                        else:
                            order = self.exchange.close_short(symbol, pos.amount)
                        if not order:
                            fail_cooldown[symbol] = time.time() + 30.0
                            if self.exchange.pop_reduce_only_abort(symbol):
                                # Phemex 11011/TE_REDUCE_ONLY_ABORT: nothing left to reduce —
                                # a resting TP/SL or racing close got there first. Not a
                                # failure; the 60s [SYNC] reconciles. No Telegram noise.
                                logger.info(f"[LIVE EXIT] {symbol} close aborted (reduceOnly) — position is being closed elsewhere")
                                continue
                            logger.error(f"[LIVE EXIT] close failed for {symbol} — position intact, cycle will retry")
                            try:
                                notifier.send(f"⚠️ [LIVE EXIT] close order failed for {symbol} ({reason}) — position intact, 60s cycle is backstop")
                            except Exception:
                                pass
                            continue
                        fill_price = self._extract_fill_price(order, price, is_exit=True)
                        self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                        self.risk.close_position(symbol, fill_price, reason, fees_usdt=self.exchange.extract_order_fee(order, symbol))
                        self.exchange.cancel_open_orders(symbol)
                        notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), reason)
                    finally:
                        with self._pos_lock:
                            self._closing.discard(symbol)
            except Exception as e:
                logger.error(f"[LIVE EXIT] watcher iteration error: {e}")
                if time.time() - last_err_alert > 300:
                    last_err_alert = time.time()
                    try:
                        notifier.send(f"⚠️ [LIVE EXIT] watcher error: {str(e)[:150]} — cycle exits still active")
                    except Exception:
                        pass
                time.sleep(5)
        logger.info("[LIVE EXIT] watcher stopped")

    def _log_shadow_trail(self, prices: dict, ohlcv_cache: dict) -> None:
        """Part B shadow-logger: forward-log armed trailing stops so we can later
        measure how an exchange-resting trail would have behaved on intra-candle
        wicks vs the 60s software loop. READ-ONLY — touches no orders, no SL/TP,
        no exit logic. See docs/superpowers/specs/
        2026-06-08-part-b-trailing-protection-plan.md (GO/NO-GO gate)."""
        if not hasattr(self, "_shadow_trail_armed"):
            self._shadow_trail_armed = {}  # symbol -> last tick record this run

        def _safe(v):
            """Coerce NaN/inf/non-numeric to None — json.dumps raises on NaN."""
            try:
                f = float(v)
                return f if f == f and f not in (float("inf"), float("-inf")) else None
            except (TypeError, ValueError):
                return None

        records = []

        # Exit events — armed symbols that left the book this cycle (all exit
        # paths run before this call, so the closed trade record already exists).
        for sym in [s for s in self._shadow_trail_armed if s not in self.risk.positions]:
            last_tick = self._shadow_trail_armed.pop(sym)
            trade = next((t for t in reversed(self.risk.closed_trades)
                          if t.get("symbol") == sym), None)
            records.append({
                "event": "exit", "ts": int(time.time()), "symbol": sym,
                "side": last_tick.get("side"),
                "entry": last_tick.get("entry"),
                "last_trail": last_tick.get("trail"),
                "last_peak": last_tick.get("peak"),
                "exit_reason": trade.get("exit_reason") if trade else None,
                "exit_price": _safe(trade.get("exit_price")) if trade else None,
                "net_pnl": _safe(trade.get("net_pnl")) if trade else None,
            })

        # Tick events — every open position with the trail armed (arms at +5%
        # peak ROI: trailing_stop_price is set by update_trailing_stop).
        for sym, pos in self.risk.positions.items():
            if pos.trailing_stop_price is None:
                continue
            price = prices.get(sym)
            df = ohlcv_cache.get(sym)
            # No REST ticker here: prices[] is the WS forming-candle close (= latest
            # trade), and a hung fetch_ticker can block ~30s/call via executor
            # teardown (exchange.py:47-55) — audit finding 2026-06-11.
            tick = {
                "event": "tick", "ts": int(time.time()), "symbol": sym,
                "side": pos.side,
                "entry": pos.entry_price,
                "trail": pos.trailing_stop_price,
                "peak": pos.peak_price,
                "sl": pos.stop_loss,
                "candle_close": _safe(price),
                "candle_high": _safe(df.iloc[-1]["high"]) if df is not None and len(df) > 0 else None,
                "candle_low": _safe(df.iloc[-1]["low"]) if df is not None and len(df) > 0 else None,
                "roi": round(pos.pnl_percent(price), 3) if price else None,
            }
            records.append(tick)
            self._shadow_trail_armed[sym] = tick

        if not records:
            return
        try:
            with open("logs/shadow_trail.jsonl", "a") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
        except Exception as e:
            logger.debug(f"[SHADOW TRAIL] write failed: {e}")

    def _log_entry_snapshot(self, symbol: str, direction: str, slot_id: str,
                            strategy: str, strength: float, price: float,
                            confidence: int, ob: dict | None, flow: dict | None,
                            ohlcv_last=None, ohlcv_df=None, htf_adx: float = None,
                            extra_tags: dict | None = None) -> dict:
        """Append entry conditions snapshot to JSONL for post-hoc analysis.
        Returns the snapshot dict so it can be attached to the Position."""
        import json as _json
        snapshot = {
            "ts": int(time.time()),
            "symbol": symbol,
            "direction": direction,
            "slot": slot_id,
            "strategy": strategy,
            "strength": round(strength, 3),
            "confidence": confidence,
            "price": round(price, 6),
            "ob": {
                "imbalance": round(ob.get("imbalance", 0), 3),
                "bid_walls": len(ob.get("bid_walls", [])),
                "ask_walls": len(ob.get("ask_walls", [])),
                "spread_pct": round(ob.get("spread_pct", 0), 4),
                # F7 (2026-07-17): raw depths + first wall PRICES — wall counts
                # alone made depth/wall questions unanswerable in the signal R&D.
                "bid_depth_usdt": ob.get("bid_depth_usdt"),
                "ask_depth_usdt": ob.get("ask_depth_usdt"),
                "first_bid_wall": _first_wall_price(ob.get("bid_walls")),
                "first_ask_wall": _first_wall_price(ob.get("ask_walls")),
            } if ob else None,
            "flow": {
                "buy_ratio": round(flow.get("buy_ratio", 0), 3),
                "cvd_slope": round(flow.get("cvd_slope", 0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
                "trade_count": flow.get("trade_count", 0),
            } if flow else None,
            "regime": self._classify_regime(ohlcv_last, ohlcv_df) if ohlcv_last is not None else None,
            "htf_adx": round(htf_adx, 1) if htf_adx is not None else None,
            # F7 (2026-07-17): RSI + pullback-geometry axes — absent from every
            # historical snapshot, which made the signal R&D's RSI-band and
            # pullback-depth hypotheses UNVERIFIABLE. Distances are % of the
            # reference level, signed (negative = price below it).
            "rsi": _snap_val(ohlcv_last, "rsi"),
            "rsi_fast": _snap_val(ohlcv_last, "rsi_fast"),
            "ema21_dist_pct": _snap_dist_pct(ohlcv_last, "ema_21", price),
            "ema50_dist_pct": _snap_dist_pct(ohlcv_last, "ema_50", price),
            "vwap_dist_pct": _snap_dist_pct(ohlcv_last, "vwap", price),
        }
        if extra_tags:
            snapshot.update(extra_tags)
        try:
            with open("logs/entry_snapshots.jsonl", "a") as f:
                f.write(_json.dumps(snapshot) + "\n")
        except Exception as e:
            logger.debug(f"[SNAPSHOT] Failed to write: {e}")
        return snapshot

    def _set_cooldown_if_loss(self, symbol: str, pnl_pct: float):
        """Set cooldown on a pair after loss: 10 min per loss, 4 hr after 3 consecutive.
        Also tracks global loss streak for regime filter."""
        if pnl_pct < 0:
            # Per-pair cooldown
            self._pair_loss_streak[symbol] = self._pair_loss_streak.get(symbol, 0) + 1
            streak = self._pair_loss_streak[symbol]
            if streak >= 3:
                self._pair_cooldown[symbol] = time.time() + 14400  # 4 hr after 3 consecutive losses
                self._pair_loss_streak[symbol] = 0
                logger.info(f"[BLACKLIST] {symbol} blocked for 4 hours after {streak} consecutive losses")
            else:
                self._pair_cooldown[symbol] = time.time() + 600  # 10 min after any loss
                logger.info(f"[RATE GATE] {symbol} blocked for 10 min (streak: {streak})")
            # Global regime filter: 3 of last 5 trades lost → 30 min pause
            self._trade_results.append(False)
            losses = sum(1 for r in self._trade_results if not r)
            if len(self._trade_results) >= 5 and losses >= 3:
                self._regime_pause_until = time.time() + 1800  # 30 min pause
                logger.warning(f"[REGIME] Rolling window: {losses}/5 losses — pausing 30 min")
                notifier.notify_ban_mode(30)  # reuse ban notification for regime pause
                self._trade_results.clear()  # reset window after pause
            self._persist_trade_results()
        else:
            self._pair_loss_streak[symbol] = 0  # reset on win
            self._trade_results.append(True)  # record win in rolling window
            self._persist_trade_results()

    def _persist_trade_results(self):
        """Sync rolling trade results to risk manager for persistence."""
        self.risk.trade_results = list(self._trade_results)
        self.risk._save_state()

    # Shadow ROI thresholds to record (a deep-red loser-cut at each WOULD exit here).
    _SHADOW_AE_THRESHOLDS = (-4.0, -5.0, -6.0, -8.0, -10.0)

    def _log_shadow_adverse_triggers(self, prices: dict):
        """LOGGING ONLY — never closes a position. For each open position past
        ADVERSE_EXIT_CYCLES, record (once per threshold) the first time its ROI crosses a
        shadow threshold, i.e. where a deep-red loser-cut would have exited. Live exits are
        unchanged (ADVERSE_EXIT_THRESHOLD=-999). Triggers are matched to real closes offline
        for both-sides PnL. The old shadow lived inside should_adverse_exit() which never
        fires at -999, so it emitted nothing (fixed 2026-06-19)."""
        for symbol, pos in list(self.risk.positions.items()):
            if symbol in self._closing:
                continue
            price = prices.get(symbol)
            if not price:
                continue
            if (self.cycle_count - pos.entry_cycle) < Config.ADVERSE_EXIT_CYCLES:
                continue
            roi = pos.pnl_percent(price)
            if roi > self._SHADOW_AE_THRESHOLDS[0]:
                continue  # hasn't crossed the shallowest threshold yet
            seen = self._shadow_ae_seen.setdefault((symbol, pos.entry_cycle), set())
            for thr in self._SHADOW_AE_THRESHOLDS:
                if roi <= thr and thr not in seen:
                    seen.add(thr)
                    self._record_shadow_adverse(symbol, pos, roi, price, thr)
        # Prune dedup state for positions no longer open.
        if self._shadow_ae_seen:
            _open = {(s, p.entry_cycle) for s, p in self.risk.positions.items()}
            for _k in [k for k in self._shadow_ae_seen if k not in _open]:
                del self._shadow_ae_seen[_k]

    def _record_shadow_adverse(self, symbol, pos, roi, price, threshold):
        """Append a shadow adverse-exit TRIGGER to logs/shadow_adverse.jsonl (logging only).

        A trigger means the open trade first reached roi <= `threshold` after
        ADVERSE_EXIT_CYCLES — i.e. a deep-red loser-cut at `threshold` WOULD have exited
        here. Does NOT close the position. Each record carries (symbol, opened_at) so it can
        be joined to the trade's real close in trading_state.json to compute both-sides PnL
        (losers the cut would save vs winners it would clip)."""
        cycles_held = self.cycle_count - pos.entry_cycle
        held_min = round(cycles_held * Config.LOOP_INTERVAL / 60, 1)
        rec = {
            "ts": time.time(), "symbol": symbol, "side": pos.side,
            "entry_price": pos.entry_price, "opened_at": pos.opened_at,  # join key
            "trigger_price": price, "trigger_roi": round(roi, 2),
            "threshold": threshold, "cycles_held": cycles_held, "held_min": held_min,
        }
        try:
            with open(self._shadow_ae_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:
            logger.warning(f"[SHADOW ADVERSE] sidecar write failed: {e}")
        logger.info(f"[SHADOW ADVERSE] {symbol} {pos.side} ROI {roi:.1f}% <= {threshold:.0f}% "
                    f"after {held_min:.0f}min — deep-red cut would exit here (logging only)")

    def _sync_exchange_closes(self, prices: dict):
        """Bidirectional per-cycle position reconciliation against the exchange:

          (A) Exchange-closed positions that the bot still tracks (SL/TP fired) — close them locally.
          (B) Exchange-OPEN positions that the bot does NOT track (orphans) — auto-adopt with
              ATR/% SL + TP placed on the exchange, send Telegram alert.

          Case (B) added 2026-04-13 after a BTC short orphan ran to -45% unrealized because
          a race in _try_limit_entry let a late fill slip through without being recorded.
          Defense in depth: exchange.py adds a ground-truth check, bot.py adds entry-failure
          adoption, this function is the belt-and-suspenders catch-all.
        """
        try:
            exchange_positions = self.exchange.get_open_positions()
        except Exception as e:
            logger.warning(f"[SYNC] fetch_positions failed: {e} — skipping sync this cycle")
            return
        if exchange_positions is None:
            return  # API failed, skip sync this cycle (treat as unknown, not as "no positions")
        exchange_map = {p["symbol"]: p for p in exchange_positions}
        exchange_symbols = set(exchange_map.keys())

        # --- (A) Closes: tracked locally but gone from exchange ---
        # Owner map covers main bot AND live-slot positions (paper slots excluded);
        # it is materialized up front, so close_position calls inside the loop are safe.
        try:
            _owners = _build_position_owners(self.risk, self.slots)
        except Exception as e:
            logger.error(f"[SYNC] (A) owner-map build failed: {e} — skipping close-detection "
                         f"this cycle, continuing to orphan scan", exc_info=True)
            _owners = {}
        for symbol, (owner_risk, slot) in _owners.items():
            try:
                # _closing is only populated by the live-exit watcher, which iterates
                # self.risk.positions (main bot) only — slot positions can never be
                # mid-watcher-close, so the guard applies to main-owned symbols only.
                if slot is None and symbol in getattr(self, "_closing", set()):
                    continue  # watcher mid-close — its fill will record the trade (watcher manages main positions only)
                if symbol not in exchange_symbols:
                    pos = owner_risk.positions[symbol]
                    # Try to get actual fill price from recent trades
                    exit_price = prices.get(symbol, pos.entry_price)
                    sync_fee = 0.0
                    try:
                        recent = self.exchange.client.fetch_my_trades(symbol, limit=10)
                        if recent:
                            # Filter to trades after position entry to avoid picking up the entry fill
                            entry_ts_ms = int(pos.opened_at * 1000)
                            close_trades = [tr for tr in recent if (tr.get("timestamp") or 0) > entry_ts_ms]
                            last_trade = close_trades[-1] if close_trades else None
                            if last_trade:
                                fill = float(last_trade.get("price", 0))
                                if fill > 0:
                                    exit_price = fill
                                    logger.info(f"[SYNC] {symbol} real exit fill: {exit_price}")
                                # Sum fees from the confirmed close trade
                                try:
                                    fee = last_trade.get("fee") or {}
                                    if fee.get("cost") is not None:
                                        sync_fee = abs(float(fee.get("cost") or 0))
                                    else:
                                        for f in last_trade.get("fees") or []:
                                            if f.get("cost") is not None:
                                                sync_fee += abs(float(f.get("cost") or 0))
                                except Exception:
                                    pass
                            else:
                                logger.debug(f"[SYNC] {symbol} no post-entry close trade found yet — using mark price")
                    except Exception:
                        pass
                    if slot is None:
                        # Main-bot position — behavior unchanged.
                        # Tag fills at a ratcheted durable-SL level as durable_sl so they
                        # don't pollute the exchange_close (rode-to-disaster) bucket.
                        close_reason = "exchange_close"
                        if getattr(pos, "sl_ratcheted", False) and pos.exchange_sl_price:
                            if abs(exit_price - pos.exchange_sl_price) / pos.exchange_sl_price <= 0.005:
                                close_reason = "durable_sl"
                        logger.info(f"[SYNC] {symbol} closed on exchange (SL/TP triggered) — removing from tracker (reason={close_reason})")
                        self.exchange.cancel_open_orders(symbol)
                        self._set_cooldown_if_loss(symbol, pos.pnl_percent(exit_price))
                        notifier.notify_exit(symbol, pos.side, pos.entry_price, exit_price, pos.pnl_usdt(exit_price), pos.pnl_percent(exit_price), close_reason)
                        self.risk.close_position(symbol, exit_price, close_reason, fees_usdt=sync_fee)
                    else:
                        # Live-slot position. durable_trail_enabled slots CAN ratchet now
                        # (2026-06-24) — a fill near the ratcheted level is tagged durable_sl
                        # below so it doesn't pollute the exchange_close (rode-to-disaster) bucket.
                        # _set_cooldown_if_loss intentionally omitted: that's the MAIN bot's
                        # per-pair cooldown; slot cooldown semantics live in the slot.
                        # If a slot maker-exit just filled-then-aborted, attribute the real
                        # reason (e.g. st2_hold) instead of the generic exchange_close.
                        # TTL 300s comfortably covers the 1-cycle gap (sync runs the
                        # cycle AFTER the abort; a cycle can stretch to the 180s
                        # watchdog) while staying far below a slot's 15-min hold, so a
                        # later unrelated close can't inherit a stale reason.
                        _pending = self._slot_pending_exit_reason.pop(symbol, None)
                        slot_reason = (_pending[0] if _pending and time.time() - _pending[1] <= 300
                                       else "exchange_close")
                        # A ratcheted slot SL that fills near its level is a durable_sl
                        # profit-protect, not a rode-to-disaster exchange_close.
                        if (slot_reason == "exchange_close" and getattr(pos, "sl_ratcheted", False)
                                and pos.exchange_sl_price
                                and abs(exit_price - pos.exchange_sl_price) / pos.exchange_sl_price <= 0.005):
                            slot_reason = "durable_sl"
                        _trig = "maker exit reconciled" if slot_reason != "exchange_close" else "SL/TP triggered"
                        logger.info(f"[SYNC] {symbol} closed on exchange (slot {slot.slot_id} {_trig}) "
                                    f"— removing from slot tracker (reason={slot_reason})")
                        self.exchange.cancel_open_orders(symbol)
                        notifier.notify_exit(symbol, pos.side, pos.entry_price, exit_price, pos.pnl_usdt(exit_price), pos.pnl_percent(exit_price), f"{slot_reason} [slot {slot.slot_id}]")
                        owner_risk.close_position(symbol, exit_price, slot_reason, fees_usdt=sync_fee, mode="live")
                        self._maybe_auto_demote(slot)
            except Exception as e:
                # A tracked position may be closed on the exchange but unrecorded locally
                # (stale state, real-money relevant) — log LOUD with a full traceback instead
                # of burying it as a warning. Isolated per-symbol: other tracked symbols and
                # the (B) orphan scan still run, preserving the (A)⊥(B) invariant below. This
                # replaced a broad warning-level except that silently hid a real AttributeError
                # for days (missing _slot_pending_exit_reason; see memory/lessons.md 2026-06-16).
                # exc_info on a *persistent* per-symbol fault repeats the traceback each 60s
                # cycle — accepted on purpose: it's an incident you want loud, it's bounded by
                # the RotatingFileHandler (10MB×5) and surfaced at ERROR for overwatch/code-health
                # to catch and fix fast. Per-cycle throttle state was rejected to avoid the
                # __init__-attribute drift trap documented in lessons.md.
                logger.error(f"[SYNC] (A) close-detection failed for {symbol}: {e} "
                             f"— other symbols + orphan scan unaffected", exc_info=True)
                continue

        # --- (B) Orphans: open on exchange but not tracked locally ---
        # Snapshotted after (A) so any positions just closed locally are excluded.
        # Runs independently of (A) — a bug in close-detection must not block orphan discovery.
        try:
            tracked_symbols = set(_build_position_owners(self.risk, self.slots).keys())
            # NOTE: list comprehension is materialized before _adopt_orphan_position can mutate
            # self.risk.positions. Safe, but if refactored to a generator this becomes a bug.
            orphans = [p for p in exchange_positions if p["symbol"] not in tracked_symbols]
            for orphan in orphans:
                try:
                    self._adopt_orphan_position(orphan)
                except Exception as e:
                    logger.error(f"[ORPHAN] Failed to adopt {orphan.get('symbol')}: {e}")
        except Exception as e:
            logger.warning(f"[SYNC] (B) orphan-scan path failed: {e}")

    def _maybe_auto_demote(self, slot):
        """Auto-demote check after every live slot close (loss cap / negative Kelly)."""
        if slot.paper_mode:
            return  # already demoted (e.g. earlier this cycle)
        demote, reason = slot.should_auto_demote()
        if demote:
            self._demote_slot(slot, reason)

    def _demote_slot(self, slot, reason: str):
        """Demote a live slot to paper: close its real positions at market, cancel
        orders, flip mode. Never leaves a frozen position (DOGE-freeze lesson 2026-06-11)."""
        logger.warning(f"[SLOT DEMOTE] {slot.slot_id} → paper ({reason})")
        for symbol in list(slot.risk.positions.keys()):
            if symbol not in slot.risk.positions:
                continue  # already closed by another path this cycle
            pos = slot.risk.positions[symbol]
            try:
                self.exchange.cancel_open_orders(symbol)
                order = (self.exchange.close_long(symbol, pos.amount) if pos.side == "long"
                         else self.exchange.close_short(symbol, pos.amount))
                if order:
                    fill = self._extract_fill_price(order, pos.entry_price, is_exit=True)
                    slot.risk.close_position(symbol, fill, "slot_demote", mode="live",
                                             fees_usdt=self.exchange.extract_order_fee(order, symbol))
                else:
                    logger.error(f"[SLOT DEMOTE] {slot.slot_id} {symbol} close FAILED — reconcile will catch")
            except Exception as e:
                logger.error(f"[SLOT DEMOTE] {slot.slot_id} {symbol} error: {e}")
        slot.set_paper()
        try:
            notifier.send(f"⬇️ Slot <b>{slot.slot_id}</b> demoted to paper — {reason}")
        except Exception:
            pass

    def _ratchet_slot_durable_sl(self, slot, symbol, pos, price):
        """Durable trailing-stop ratchet for a LIVE slot position — mirror of the
        main-bot [DURABLE SL] block (bot.py:987-1032) on slot.risk positions.

        As the trail arms (Config.TRAIL_ARM_ROI), amend the resting exchange SL up toward the
        breakeven lock / wide durable band. The amend rests on Phemex, so the
        profit-lock survives a host sleep — which is exactly the gap that let the
        XLM 5m_mean_revert short round-trip +7% -> -14.2% on 2026-06-24.

        No-op for paper slots, slots without durable_trail_enabled, software-managed
        SLs, or positions mid-close this cycle. Ratchet-only + 0.1% throttle (same
        guardrails as the main block — avoid amend spam). Per-slot opt-in.
        """
        if slot.paper_mode or not getattr(slot, "durable_trail_enabled", False):
            return
        if symbol in self._closing:
            return  # a close is already in flight this cycle
        if not pos.sl_order_id or pos.sl_order_id == "software":
            return  # software-managed SL — nothing resting on the exchange to amend
        old_sl = pos.stop_loss
        pos.check_breakeven(price)
        pos.update_trailing_stop(price)
        # Durable backstop: wide band from peak once the trail is armed (TRAIL_ARM_ROI).
        band = Config.DURABLE_TRAIL_BAND_PCT / 100.0
        durable_floor = None
        if pos.trailing_stop_price is not None and pos.peak_price > 0:
            durable_floor = pos.peak_price * (1 - band) if pos.side == "long" else pos.peak_price * (1 + band)
        # Q2 coordination: resting order never looser than the breakeven lock.
        candidates = [v for v in (pos.stop_loss, durable_floor) if v is not None]
        target = max(candidates) if pos.side == "long" else min(candidates)
        current_resting = pos.exchange_sl_price if pos.exchange_sl_price is not None else old_sl
        # Ratchet-only + >=0.1% throttle (mirror of bot.py:1011-1014).
        improvement = (target - current_resting) if pos.side == "long" else (current_resting - target)
        if improvement <= 0 or improvement / price < 0.001:
            return
        try:
            new_id = self.exchange.move_stop_loss(symbol, pos.side, pos.amount, target, pos.sl_order_id)
            pos.sl_order_id = new_id
            pos.exchange_sl_price = target
            pos.sl_ratcheted = True
            # Persist immediately so exchange_sl_price/sl_ratcheted survive (correct
            # durable_sl tagging + the ratcheted level on record). NOTE: sl_order_id is
            # not in the state schema, so after a full RESTART the ratchet pauses until a
            # new SL id is populated — but the ratcheted SL itself keeps resting on Phemex
            # and protecting the position. Across a SLEEP (process suspended, not killed)
            # the in-memory id is retained and ratcheting resumes normally on wake.
            slot.risk._save_state()
            logger.info(
                f"[SLOT DURABLE SL] {slot.slot_id} {symbol} exchange SL ratcheted to {target:.4f} "
                f"(breakeven={pos.stop_loss:.4f}, durable_floor={round(durable_floor, 4) if durable_floor is not None else None})"
            )
        except Exception as e:
            # Old SL is still resting (move_stop_loss guarantees it) — alert loudly,
            # do NOT downgrade to software: that would lie about the protection state.
            logger.error(f"[SLOT SL-MOVE-FAIL] {slot.slot_id} {symbol} could not move exchange SL to {target:.4f}: {e} — old SL still resting at {current_resting:.4f}")
            try:
                notifier.notify_sl_move_fail(symbol, target, current_resting, str(e))
            except Exception as ne:
                logger.warning(f"[SLOT SL-MOVE-FAIL] Telegram alert failed for {symbol}: {ne}")

    # ── ETH-TSM-28 slow-horizon slot (2026-07-06 build) ────────────────────
    # Spec: docs/overnight-2026-07-05/r5_slow_horizon_research.md §7 (frozen).
    # Build doc: docs/overnight-2026-07-05/r6_eth_tsm_build.md.
    # All signal math is in tsm_slot.py (pure, unit-tested); these methods only
    # orchestrate. No threads, no cron: _evaluate_eth_tsm runs once per main
    # cycle and does the daily work when the UTC date rolls.

    def _tsm_slot(self):
        for slot in self.slots:
            if slot.slot_id == TSM_SLOT_ID:
                return slot
        return None

    def _tsm_locks_symbol(self, symbol: str):
        """Ownership rule: reason-string when the main bot / other live slots must
        stay off `symbol` because ETH_TSM_28 owns it, else None. Phemex one-way
        ("Merged") mode merges same-symbol positions, and while the slot owns ETH
        the symbol leverage is 3x (scalper sizing assumes Config.LEVERAGE=10x)."""
        if symbol != TSM_SYMBOL:
            return None
        slot = self._tsm_slot()
        if slot is None:
            return None
        if not slot.paper_mode and symbol in slot.risk.positions:
            return f"{TSM_SLOT_ID} holds a live ETH position"
        if self._tsm_state.get("leverage_3x_set"):
            return f"ETH leverage still {TSM_LEVERAGE}x from {TSM_SLOT_ID} (restore pending)"
        if self._tsm_entry_active:
            return f"{TSM_SLOT_ID} entry in flight today"
        return None

    def _tsm_notify_ownership(self, kind: str, msg: str) -> None:
        """Telegram notice for every ETH ownership interaction (owner directive
        2026-07-06: he sees each one), deduped to once per UTC day per kind so a
        60s cycle can't spam. In-memory dedup — a restart re-sends once, which
        errs on the side of visibility. Always logs regardless of dedup."""
        logger.info(f"[TSM OWNERSHIP] {msg}")
        today = tsm_slot.utc_date_str()
        if self._tsm_ownership_notified.get(kind) == today:
            return
        self._tsm_ownership_notified[kind] = today
        try:
            notifier.send(f"🔒 [TSM] {msg}")
        except Exception as e:
            logger.debug(f"[TSM] ownership notify failed: {e}")

    def _tsm_restore_leverage(self) -> bool:
        """Restore ETH to Config.LEVERAGE after the slot's 3x flip. Complete-or-
        retry: on failure the sidecar flag stays set, which keeps the main bot
        (and other live slots) locked out of ETH via _tsm_locks_symbol — a
        mis-leveraged scalper entry is worse than a skipped one."""
        try:
            self.exchange.set_symbol_leverage(TSM_SYMBOL, Config.LEVERAGE)
            self._tsm_state["leverage_3x_set"] = False
            tsm_slot.save_state(self._tsm_state)
            self._leverage_set.add(TSM_SYMBOL)  # main-bot cache: already configured
            logger.info(f"[TSM] {TSM_SYMBOL} leverage restored to {Config.LEVERAGE}x")
            return True
        except Exception as e:
            logger.error(f"[TSM] leverage restore to {Config.LEVERAGE}x FAILED: {e} — "
                         f"ETH stays locked for main bot; retrying next cycle")
            return False

    def _evaluate_eth_tsm(self, prices: dict):
        """Per-cycle TSM state machine (runs after _evaluate_slots):
          0. leverage-restore retry (runs even if slot disabled/demoted/killed)
          1. paper disaster-stop replica (live stop rests on the exchange)
          2. daily signal evaluation when the UTC date rolls
          3. pending signal-exit retry   4. pending entry attempts
        """
        slot = self._tsm_slot()
        if slot is None:
            return
        st = self._tsm_state
        sym = TSM_SYMBOL
        self._tsm_entry_active = False  # recomputed below

        # (0) leverage restore — after ANY exit path (signal exit, disaster stop
        # reconciled by _sync_exchange_closes, demote, kill). Unconditional on
        # slot mode/enabled so a demoted slot can't strand ETH at 3x.
        if st.get("leverage_3x_set") and not (not slot.paper_mode and sym in slot.risk.positions):
            self._tsm_restore_leverage()

        # (1) paper disaster-stop: the live stop is a resting exchange order; the
        # paper book replicates it here (generic _evaluate_slots SL check never
        # runs for this slot — strategy_fn is None by design).
        if slot.paper_mode and sym in slot.risk.positions:
            pos = slot.risk.positions[sym]
            price = prices.get(sym)
            if price and price <= pos.stop_loss:
                logger.info(f"[TSM] paper disaster stop hit @ {pos.stop_loss:.2f}")
                if self._close_slot_position(slot, sym, pos, pos.stop_loss, "disaster_stop"):
                    st["entry_date"] = None
                    st["exit_pending"] = False
                    tsm_slot.save_state(st)

        # (1b) live SL heal: the −8% exchange stop is this position's ONLY
        # protective exit — if placement failed at entry, retry every cycle.
        if not slot.paper_mode and sym in slot.risk.positions:
            pos = slot.risk.positions[sym]
            if pos.sl_order_id in (None, "software"):
                sl_id = self.exchange.place_stop_loss(sym, "long", pos.amount, pos.stop_loss)
                if sl_id:
                    pos.sl_order_id = sl_id
                    pos.exchange_sl_price = pos.stop_loss
                    slot.risk._save_state()
                    logger.warning(f"[TSM] disaster stop (re)placed @ {pos.stop_loss:.2f}")
                else:
                    logger.error(f"[TSM] disaster stop STILL missing for {sym} — retrying next cycle")

        # (2) daily evaluation at the UTC day roll (also first cycle after restart)
        today = tsm_slot.utc_date_str()
        if st.get("last_eval_date") != today:
            self._tsm_daily_eval(slot, st, today, prices)

        # (3) pending signal exit (decided at daily eval; retried until closed)
        if st.get("exit_pending"):
            if sym in slot.risk.positions:
                pos = slot.risk.positions[sym]
                price = prices.get(sym) or pos.entry_price
                if self._close_slot_position(slot, sym, pos, price, "signal_exit"):
                    st["exit_pending"] = False
                    st["entry_date"] = None
                    tsm_slot.save_state(st)
                    if not slot.paper_mode and st.get("leverage_3x_set"):
                        self._tsm_restore_leverage()
                # reduceOnly-abort race: _close_slot_position returned False but
                # stashed the reason — _sync_exchange_closes reconciles the fill,
                # and this branch clears exit_pending next cycle (position gone).
            else:
                st["exit_pending"] = False  # already closed (stop / demote / sync)
                st["entry_date"] = None
                tsm_slot.save_state(st)

        # (4) pending entry (signal ON today, still flat, day not skipped)
        if (st.get("entry_pending_date") == today and slot.is_active
                and sym not in slot.risk.positions and not st.get("exit_pending")):
            self._tsm_try_entry(slot, st, today, prices)

    def _tsm_price(self, prices: dict):
        """Best current ETH price: cycle price map, else one REST ticker."""
        price = prices.get(TSM_SYMBOL)
        if price:
            return float(price)
        try:
            t = self.exchange.get_ticker(TSM_SYMBOL)
            if t and t.get("last"):
                return float(t["last"])
        except Exception as e:
            logger.debug(f"[TSM] ticker fetch failed: {e}")
        return None

    def _tsm_daily_eval(self, slot, st: dict, today: str, prices: dict):
        """Compute the daily signal from COMPLETE 1d candles and set intents.
        On fetch failure last_eval_date is NOT stamped, so this retries every
        cycle until the day's signal is computed (no thread, no cron)."""
        df = self.exchange.get_ohlcv(TSM_SYMBOL, "1d", limit=TSM_OHLCV_LIMIT)
        closes = tsm_slot.complete_daily_closes(df)
        sig = tsm_slot.compute_signal(closes)
        if sig is None:
            logger.warning(f"[TSM] daily eval {today}: insufficient history "
                           f"({len(closes)} complete candles) — retrying next cycle")
            return

        # Parallel BTC replica signal (spec §7.1 — logged, never traded). Best-effort.
        btc = None
        try:
            btc_df = self.exchange.get_ohlcv(tsm_slot.TSM_BTC_SYMBOL, "1d", limit=TSM_OHLCV_LIMIT)
            btc = tsm_slot.compute_signal(tsm_slot.complete_daily_closes(btc_df))
        except Exception as e:
            logger.debug(f"[TSM] BTC replica signal failed: {e}")

        rep = tsm_slot.advance_replica(st, sig["signal_on"], today)
        holding = TSM_SYMBOL in slot.risk.positions
        note = ""

        if holding:
            if not sig["signal_on"]:
                if tsm_slot.min_hold_met(st.get("entry_date"), today):
                    st["exit_pending"] = True
                    note = "signal left top tercile after min-hold — exit pending"
                else:
                    note = (f"signal off but min-hold "
                            f"({tsm_slot.held_days(st['entry_date'], today)}/"
                            f"{tsm_slot.TSM_MIN_HOLD_DAYS}d) — holding")
            else:
                note = "signal on — holding"
        elif sig["signal_on"] and slot.is_active:
            # Ownership check BOTH directions (investigation #1): if the main bot
            # (or any other live slot) already holds ETH, the TSM slot SKIPS the day.
            other_owner = None
            if TSM_SYMBOL in self.risk.positions:
                other_owner = "main bot"
            else:
                for other in self.slots:
                    if (other.slot_id != TSM_SLOT_ID and not other.paper_mode
                            and TSM_SYMBOL in other.risk.positions):
                        other_owner = f"slot {other.slot_id}"
                        break
            if other_owner and not slot.paper_mode:
                note = f"SKIP-DAY: {other_owner} holds ETH"
                self._tsm_notify_ownership(
                    "tsm_skip", f"TSM entry skipped for {today} ({other_owner} holds ETH)")
            else:
                st["entry_pending_date"] = today
                st["entry_first_attempt_ts"] = None
                note = "signal on — entry pending"
        elif sig["signal_on"]:
            note = "signal on but slot disabled/killed — no entry"
        else:
            note = "signal off — flat"

        st.update({"last_eval_date": today, "signal_on": sig["signal_on"],
                   "ret_28d": sig["ret_28d"], "threshold": sig["threshold"]})
        tsm_slot.append_day(st, {
            "date": today,
            "signal_on": sig["signal_on"],
            "ret_28d": round(sig["ret_28d"], 6),
            "threshold": round(sig["threshold"], 6),
            "n_history": sig["n_history"],
            "close": sig["close"],
            "replica_position": bool(rep.get("position")),
            "actual_position": holding,
            "mode": "paper" if slot.paper_mode else "live",
            "note": note,
            "btc_signal_on": (btc or {}).get("signal_on"),
            "btc_ret_28d": round(btc["ret_28d"], 6) if btc else None,
        })
        tsm_slot.save_state(st)
        logger.info(f"[TSM] daily eval {today}: ret28={sig['ret_28d']:+.4f} "
                    f"thr={sig['threshold']:+.4f} (n={sig['n_history']}) "
                    f"signal={'ON' if sig['signal_on'] else 'OFF'} | {note}")

    def _tsm_try_entry(self, slot, st: dict, today: str, prices: dict):
        """One entry attempt per cycle: PostOnly maker at the touch; after 30 min
        of misses (spec §7.2) a single market (taker) order. Fixed 0.01 ETH."""
        price = self._tsm_price(prices)
        if not price:
            self._tsm_entry_active = not slot.paper_mode
            return

        if slot.paper_mode:
            # F1 follow-up (2026-07-17 audit): paper entries honor the global
            # pause too — sentinel promises "skipping all entries". The
            # pending-entry machinery retries after the pause clears.
            if self._slot_entries_blocked():
                logger.info("[TSM] paper entry blocked — account halt")
                return
            # Paper: fill at current price, sim book only. Margin recorded at the
            # spec's 3x so ROI% matches what live would report.
            margin = TSM_AMOUNT_ETH * price / TSM_LEVERAGE
            pos = slot.risk.open_position(TSM_SYMBOL, price, margin, side="long",
                                          atr=0.0, regime="medium",
                                          cycle=self.cycle_count, strategy="eth_tsm_28")
            pos.amount = TSM_AMOUNT_ETH
            pos.margin = margin
            pos.stop_loss = price * (1 - TSM_STOP_PCT / 100)   # −8% disaster stop
            pos.take_profit = None                             # spec: NO take profit
            slot.risk._save_state()
            st["entry_pending_date"] = None
            st["entry_date"] = today
            tsm_slot.save_state(st)
            slot.total_entries += 1
            notifier.notify_paper_entry(TSM_SYMBOL, "long", price, margin, 1.0,
                                        f"TSM-28 top-tercile (ret28={st.get('ret_28d'):+.4f})",
                                        slot=TSM_SLOT_ID)
            logger.info(f"[PAPER] {TSM_SLOT_ID} ENTRY LONG {TSM_SYMBOL} @ {price:.2f} "
                        f"| 0.01 ETH | stop {pos.stop_loss:.2f} (−{TSM_STOP_PCT}%)")
            return

        # --- LIVE entry ---
        if os.path.exists(".pause_trading") or self.risk._drawdown_pause_until > time.time():
            logger.info(f"[TSM] live entry blocked — account halt")
            return
        if TSM_SYMBOL in self.risk.positions:
            # Main bot grabbed ETH between the daily eval and now → skip the day.
            st["entry_pending_date"] = None
            tsm_slot.save_state(st)
            self._tsm_notify_ownership(
                "tsm_skip", f"TSM entry skipped for {today} (main bot holds ETH)")
            return
        # Belt-and-suspenders merge guard (owner directive 2026-07-06): never trust
        # local bookkeeping alone — re-fetch positions from the EXCHANGE and abort
        # if ANY ETH position already exists on the account (manual trade, orphan,
        # desynced state). One-way mode would merge our fill into it. A failed
        # fetch also aborts: unknown state = no order.
        try:
            _exch_pos = self.exchange.get_open_positions()
        except Exception as _gt_err:
            logger.warning(f"[TSM] pre-entry exchange position check failed: {_gt_err} — no order this cycle")
            self._tsm_entry_active = True
            return
        if _exch_pos is None:
            logger.warning("[TSM] pre-entry exchange position check returned None — no order this cycle")
            self._tsm_entry_active = True
            return
        _eth_on_exch = [p for p in _exch_pos if p.get("symbol") == TSM_SYMBOL]
        if _eth_on_exch:
            st["entry_pending_date"] = None
            tsm_slot.save_state(st)
            _p0 = _eth_on_exch[0]
            self._tsm_notify_ownership(
                "tsm_abort_exchange",
                f"TSM entry ABORTED for {today} — exchange already shows an ETH position "
                f"({_p0.get('side')} {_p0.get('amount')} @ {_p0.get('entry_price')}) "
                f"not attributed to the TSM slot; merge risk, skipping day")
            return
        self._tsm_entry_active = True  # main bot stays off ETH while we work

        # Leverage FIRST (investigation #2): flag is persisted BEFORE the flip so a
        # crash can never leave ETH at 3x unflagged. Complete-or-skip: no order is
        # placed unless the isolated-3x call succeeded (0.01 ETH at 3x ≈ $5.90
        # margin; liq ≈ −32% — far beyond the −8% stop; at 10x liq ≈ −9% is too
        # close, hence the flip).
        if not st.get("leverage_3x_set"):
            st["leverage_3x_set"] = True
            tsm_slot.save_state(st)
            try:
                self.exchange.set_symbol_leverage(TSM_SYMBOL, TSM_LEVERAGE)
                logger.info(f"[TSM] {TSM_SYMBOL} leverage set to {TSM_LEVERAGE}x isolated")
            except Exception as e:
                logger.error(f"[TSM] set_leverage {TSM_LEVERAGE}x failed: {e} — no order placed, retry next cycle")
                # flag stays set: leverage state on the exchange is UNKNOWN, so the
                # ownership lock must hold until a restore confirms 10x.
                return

        first = st.get("entry_first_attempt_ts") or time.time()
        if st.get("entry_first_attempt_ts") is None:
            st["entry_first_attempt_ts"] = first
            tsm_slot.save_state(st)

        try:
            if time.time() - first <= TSM_TAKER_FALLBACK_S:
                # Maker attempt: open_long computes amount = margin*Config.LEVERAGE/price,
                # so margin is back-computed to yield EXACTLY 0.01 ETH (one min-step —
                # partial fills below the step are impossible).
                margin_for_amount = TSM_AMOUNT_ETH * price / Config.LEVERAGE
                order = self.exchange.open_long(TSM_SYMBOL, margin_for_amount, price)
            else:
                logger.info(f"[TSM] maker window ({TSM_TAKER_FALLBACK_S/60:.0f} min) exhausted — taker fallback")
                order = self.exchange.open_long_market(TSM_SYMBOL, TSM_AMOUNT_ETH)
        except Exception as e:
            logger.error(f"[TSM] entry order error: {e} — any landed fill is caught by the orphan scanner")
            self._last_entry_time = time.time()
            return
        if not order:
            logger.info(f"[TSM] entry no fill (PostOnly miss) — retrying next cycle "
                        f"({(time.time()-first)/60:.0f} min into maker window)")
            return

        fill = self._extract_fill_price(order, price)
        amount = self._extract_fill_amount(order, TSM_AMOUNT_ETH)
        margin = amount * fill / TSM_LEVERAGE  # actual isolated margin at 3x
        pos = slot.risk.open_position(TSM_SYMBOL, fill, margin, side="long",
                                      atr=0.0, regime="medium",
                                      cycle=self.cycle_count, strategy="eth_tsm_28")
        pos.amount = amount
        pos.margin = margin
        pos.stop_loss = fill * (1 - TSM_STOP_PCT / 100)
        pos.take_profit = None  # spec: no TP; exits are signal-exit or the −8% stop
        # Persist ownership BEFORE the stop placement: a crash in this window must
        # leave the position attributed to this slot on restart, or the startup sync
        # adopts it into the main bot and re-pins scalper 1.2/1.6 brackets over the
        # −8% disaster stop while the leverage-restore path flips a live position
        # (review finding 2026-07-06). The stop itself heals next cycle via (1b).
        slot.risk._save_state()
        sl_id = self.exchange.place_stop_loss(TSM_SYMBOL, "long", amount, pos.stop_loss)
        if sl_id:
            pos.sl_order_id = sl_id
            pos.exchange_sl_price = pos.stop_loss
        else:
            pos.sl_order_id = "software"  # heals via (1b) next cycle; alert loudly now
            logger.error(f"[TSM] disaster-stop placement FAILED — position live WITHOUT its only protective exit; retrying next cycle")
            try:
                notifier.send(f"⚠️ [TSM] {TSM_SYMBOL} entry filled but −{TSM_STOP_PCT}% stop placement FAILED — retrying each cycle")
            except Exception:
                pass
        slot.risk._save_state()
        st["entry_pending_date"] = None
        st["entry_date"] = today
        tsm_slot.save_state(st)
        slot.total_entries += 1
        self._last_entry_time = time.time()  # global anti-cluster cooldown, like other live entries
        logger.info(f"[SLOT LIVE] {TSM_SLOT_ID} ENTRY LONG {TSM_SYMBOL} | Fill: {fill:.2f} | "
                    f"{amount} ETH @ {TSM_LEVERAGE}x (margin ${margin:.2f}) | stop {pos.stop_loss:.2f}")
        try:
            notifier.send(
                f"🟢 <b>[LIVE] LONG ENTRY — {TSM_SYMBOL}</b>  [slot {TSM_SLOT_ID}]\n"
                f"Signal:   <b>TSM-28 top tercile</b> (ret28 {st.get('ret_28d'):+.2%})\n"
                f"Price:    ${fill:.2f}\n"
                f"Size:     {amount} ETH ({TSM_LEVERAGE}x isolated, margin ${margin:.2f})\n"
                f"Stop:     ${pos.stop_loss:.2f} (−{TSM_STOP_PCT:.0f}%, exchange-resting)\n"
                f"Exit:     daily signal, min hold {tsm_slot.TSM_MIN_HOLD_DAYS}d — no TP, no trail"
            )
        except Exception:
            pass

    # ── Donchian ensemble slots (2026-07-16 build) ──────────────────────────
    # Spec: docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md
    # (frozen). All signal math is in donchian_slot.py (pure, reference-parity
    # verified against the validated replay); these methods only orchestrate.
    # No threads, no cron: _evaluate_donchian runs once per main cycle and does
    # the daily work when the UTC date rolls — same trigger as _evaluate_eth_tsm.
    # Paper-only build: fills simulate at the current cycle price; ALL exits
    # (ratcheting close-only stops, flat signal, rebalances) are computed on
    # COMPLETE daily closes inside the daily eval — no resting orders, and the
    # scalper exit engine never sees these slots (strategy_fn is None by design).

    def _donchian_slot(self, slot_id: str):
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        return None

    def _donchian_price(self, symbol: str, prices: dict):
        """Best current price: cycle price map, else one REST ticker."""
        price = prices.get(symbol)
        if price:
            return float(price)
        try:
            t = self.exchange.get_ticker(symbol)
            if t and t.get("last"):
                return float(t["last"])
        except Exception as e:
            logger.debug(f"[DONCHIAN] ticker fetch failed for {symbol}: {e}")
        return None

    def _evaluate_donchian(self, prices: dict):
        """Per-cycle driver: for each coin, run the daily evaluation when the
        UTC date rolls (epoch/UTC-derived — never the local clock; the Mac's
        timezone travels). Per-coin isolation: one coin's failure must not
        starve the other. On failure the day is NOT stamped, so the eval
        retries every cycle until the signal is computed and the paper book
        matches it (mirrors the TSM retry shape)."""
        today = donchian_slot.utc_date_str()
        for symbol in donchian_slot.SYMBOLS:
            slot = self._donchian_slot(donchian_slot.SLOT_IDS[symbol])
            if slot is None:
                continue
            st = self._donchian_state.setdefault(symbol, donchian_slot.default_coin_state())
            if st.get("last_eval_utc_date") == today:
                continue
            try:
                self._donchian_daily_eval(slot, symbol, st, today, prices)
            except Exception as e:
                logger.error(f"[DONCHIAN] {slot.slot_id} daily eval error: {e} — "
                             f"retrying next cycle", exc_info=True)

    def _donchian_daily_eval(self, slot, symbol: str, st: dict, today: str, prices: dict):
        """Fold the newly completed daily close(s) into the persisted ensemble
        state, write the pure-rule replica record(s), then express the executed
        weight as the slot's paper position (notional = BASE_NOTIONAL × w).
        last_eval_utc_date is stamped ONLY once the book matches the weight, so
        any failure retries next cycle — advance_state is idempotent (closes
        already folded in are never re-processed)."""
        df = self.exchange.get_ohlcv(symbol, "1d", limit=donchian_slot.OHLCV_LIMIT)
        dates, closes = donchian_slot.complete_daily_bars(df)
        if len(closes) < donchian_slot.MIN_BARS:
            logger.warning(f"[DONCHIAN] {slot.slot_id} daily eval {today}: insufficient "
                           f"history ({len(closes)} complete candles < "
                           f"{donchian_slot.MIN_BARS}) — retrying next cycle")
            return
        infos = donchian_slot.advance_state(st, dates, closes)
        if any(i.get("stop_fired") for i in infos):
            # Latched until the book syncs: a failed cycle between the fold and
            # the position adjustment must not demote a stop-driven close to a
            # generic signal_exit on the retry (advance_state re-returns nothing).
            st["stop_fired_pending"] = True
        donchian_slot.save_state(self._donchian_state)  # persist the fold before book work
        donchian_slot.append_signal_days(symbol, [
            {"date": i["date"],
             "w": round(i["w"], 8),
             "w_target": round(i["w_target"], 8),
             "submodel_pos": i["submodel_pos"],
             "n_long": i["n_long"],
             "vol_scalar": round(i["vol_scalar"], 8) if i["vol_scalar"] is not None else None,
             "close": i["close"],
             "stop_fired": i["stop_fired"],
             **({"note": i["note"]} if i.get("note") else {})}
            for i in infos])

        w = float(st.get("w") or 0.0)
        n_long = int(sum(st.get("submodel_pos") or []))
        stop_fired = bool(st.get("stop_fired_pending"))

        price = self._donchian_price(symbol, prices)
        if price is None:
            logger.warning(f"[DONCHIAN] {slot.slot_id} daily eval {today}: no price for "
                           f"{symbol} — retrying next cycle")
            return
        note = self._donchian_adjust_position(slot, symbol, w, price, stop_fired, today)
        if note is None:
            return  # book not in line yet — retry next cycle, day stays unstamped
        st["stop_fired_pending"] = False  # book synced — latch released
        st["last_eval_utc_date"] = today
        donchian_slot.save_state(self._donchian_state)
        logger.info(f"[DONCHIAN] {slot.slot_id} daily eval {today}: w={w:.4f} "
                    f"({n_long}/9 long) close={closes[-1]:.2f} | {note}")

    def _donchian_adjust_position(self, slot, symbol: str, w: float, price: float,
                                  stop_fired: bool, today: str):
        """Make the slot's paper book express notional = BASE_NOTIONAL × w.
        Resizes are close-and-reopen at the new size — the simplest faithful
        paper expression of a weight change (the realized PnL slice at each
        rebalance is a book artifact, not a strategy event; the sidecar w
        series is the fidelity benchmark per the spec's kill criteria).
        Returns a status note on success, None when the book could not be
        brought in line (caller retries next cycle)."""
        if not slot.paper_mode:
            # Live sizing is decided AT promotion (spec non-goal: not in this
            # build) — never place real orders from this path. One warning per
            # UTC day per slot; the signal series keeps accruing regardless.
            if self._donchian_live_warned.get(slot.slot_id) != today:
                self._donchian_live_warned[slot.slot_id] = today
                logger.error(f"[DONCHIAN] {slot.slot_id} is LIVE but live execution is "
                             f"not implemented — no orders placed; demote with "
                             f".demote_{slot.slot_id}")
            return "LIVE mode unsupported — book untouched"

        target = donchian_slot.BASE_NOTIONAL_USDT * w
        pos = slot.risk.positions.get(symbol)

        # F1 follow-up (2026-07-17 audit): during a global pause never INCREASE
        # paper exposure (open/up-size); reductions and closes still run so the
        # book can de-risk. Deferred adjustments retry next cycle — fidelity
        # |w−replica| tolerates sub-day lag (kill needs >0.10 for >3d of 14d).
        if self._slot_entries_blocked():
            _cur_notional = (pos.amount * price) if pos is not None else 0.0
            if target > _cur_notional:
                logger.info(f"[DONCHIAN] {slot.slot_id} up-size deferred — account halt")
                return None

        if pos is None:
            if target <= 0:
                return "flat — no position"
            if not slot.is_active:
                return f"w={w:.4f} but slot disabled/killed — no entry"
            self._donchian_open_paper(slot, symbol, price, target, w)
            return f"opened ${target:.2f} notional"

        if target <= 0:
            # All sub-models flat. Stop-driven (a ratcheting Donchian stop fired
            # on a folded close) vs vol/history-driven flat — distinct exit tags.
            reason = "donchian_stop" if stop_fired else "signal_exit"
            if self._close_slot_position(slot, symbol, pos, price, reason):
                return f"closed ({reason})"
            return None

        current = pos.margin  # 1x paper: margin == notional recorded at (re)open
        if abs(target - current) <= 1e-9:
            return f"holding ${current:.2f} notional"
        if not self._close_slot_position(slot, symbol, pos, price, "donchian_rebalance"):
            return None
        if not slot.is_active:
            return f"rebalance closed ${current:.2f} but slot disabled/killed — no reopen"
        self._donchian_open_paper(slot, symbol, price, target, w)
        return f"rebalanced ${current:.2f} → ${target:.2f} notional"

    def _donchian_open_paper(self, slot, symbol: str, price: float,
                             notional: float, w: float):
        """Paper fill at the current price. 1x sizing (spec: no leverage in
        paper): margin is recorded AS the notional, so ROI% == price move %,
        matching the unlevered weight semantics of the validated replay."""
        n_long = int(sum(self._donchian_state[symbol].get("submodel_pos") or []))
        pos = slot.risk.open_position(symbol, price, notional, side="long",
                                      atr=0.0, regime="medium",
                                      cycle=self.cycle_count,
                                      strategy="donchian_ensemble")
        pos.amount = notional / price
        pos.margin = notional
        pos.stop_loss = 0.0     # no intraday/resting stop — the ensemble's close-only
                                # stops are evaluated in _donchian_daily_eval
        pos.take_profit = None  # spec: no TP; exits are w→0 / rebalance only
        slot.risk._save_state()
        slot.total_entries += 1
        notifier.notify_paper_entry(symbol, "long", price, notional, w,
                                    f"Donchian ensemble w={w:.3f} ({n_long}/9 long)",
                                    slot=slot.slot_id)
        logger.info(f"[PAPER] {slot.slot_id} ENTRY LONG {symbol} @ {price:.2f} "
                    f"| ${notional:.2f} notional (w={w:.4f}, {n_long}/9 long) "
                    f"| no TP, close-only daily stops")

    def _close_slot_position(self, slot, symbol, pos, price, reason):
        """Close a slot position — simulated for paper, real market order for live.
        Returns True if closed."""
        pnl = pos.pnl_usdt(price)
        pnl_pct = pos.pnl_percent(price)
        if slot.paper_mode:
            slot.risk.close_position(symbol, price, reason)
            notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, reason, slot=slot.slot_id)
            return True
        try:
            self.exchange.cancel_open_orders(symbol)
            # ST2.0's edge is maker-only — close patiently (maker) so the round trip
            # stays maker-maker. Other slots close urgently (taker) as before.
            # ETH_TSM_28 signal exits are also maker-first (spec §7.3): patient limit
            # at the touch, market fallback within the same call — no protective
            # deadline on a signal exit, and 5bp saved matters on an $18 notional.
            # EXCEPTION: an adverse-exit loss-cut MUST fill now — a patient maker cut
            # would just ride to the -12% SL — so force taker regardless of slot.
            _urgent = (slot.strategy_name not in ("ST2.0", "eth_tsm_28")
                       or reason == "adverse_exit")
            order = (self.exchange.close_long(symbol, pos.amount, urgent=_urgent) if pos.side == "long"
                     else self.exchange.close_short(symbol, pos.amount, urgent=_urgent))
            if not order:
                if self.exchange.pop_reduce_only_abort(symbol):
                    # Phemex 11011/reduceOnly abort: the patient maker exit already
                    # filled (cancel raced the fill → OM_ORDER_NOT_FOUND → market
                    # fallback found nothing left to reduce). The position is
                    # closing, not stuck — the per-cycle [SYNC] reconciles the real
                    # fill. Mirrors the main live-exit path (bot.py LIVE EXIT) so a
                    # successful maker exit is no longer mislogged as a failure.
                    # Stash the intended reason so [SYNC] tags the real fill as
                    # e.g. st2_hold (maker exit) instead of the generic exchange_close.
                    self._slot_pending_exit_reason[symbol] = (reason, time.time())
                    logger.info(f"[SLOT LIVE] {slot.slot_id} {symbol} {reason} close aborted "
                                f"(reduceOnly) — maker exit filled / closing elsewhere, sync reconciles")
                    return False
                logger.error(f"[SLOT LIVE] {slot.slot_id} {symbol} {reason} close FAILED — retry next cycle")
                return False
            fill = self._extract_fill_price(order, price, is_exit=True)
            slot.risk.close_position(symbol, fill, reason, mode="live",
                                     fees_usdt=self.exchange.extract_order_fee(order, symbol))
            notifier.notify_exit(symbol, pos.side, pos.entry_price, fill,
                                 pos.pnl_usdt(fill), pos.pnl_percent(fill),
                                 f"{reason} [slot {slot.slot_id}]")
            self._maybe_auto_demote(slot)
            return True
        except Exception as e:
            logger.error(f"[SLOT LIVE] {slot.slot_id} {symbol} {reason} close error: {e} — retry next cycle")
            return False

    def _adopt_orphan_position(self, orphan: dict):
        """Adopt an exchange-visible position that the bot isn't tracking.

        - Calls risk.open_position to register it (with % SL fallback — ATR isn't available post-hoc)
        - Places SL/TP on exchange
        - Adds symbol to active_pairs so it's priced every cycle
        - Sends Telegram alert (real-money event — must not be silent)
        """
        symbol = orphan["symbol"]
        side = orphan["side"]
        entry_price = float(orphan["entry_price"])
        amount = float(orphan["amount"])
        margin = float(orphan.get("margin") or (amount * entry_price / max(Config.LEVERAGE, 1)))

        logger.warning(
            f"[ORPHAN] Adopting untracked position: {symbol} {side.upper()} "
            f"@ {entry_price} amount={amount} margin=${margin:.2f}"
        )

        # Register with risk manager (falls through to configured % SL since atr=0)
        self.risk.open_position(
            symbol, entry_price, margin,
            side=side, atr=0.0, regime="medium",
            cycle=self.cycle_count, strategy="orphan_adopted",
        )
        pos = self.risk.positions[symbol]
        pos.amount = amount
        pos.margin = margin
        # F4 provenance: this is an ADOPTION, not a signal entry — opened_at is
        # discovery time, the true entry time is unknowable post-hoc.
        pos.adopted = True
        pos.adopted_at = time.time()

        # Place SL/TP on the exchange so the broker protects this position
        try:
            sl_tp = self.exchange.place_sl_tp(symbol, side, amount, pos.stop_loss, pos.take_profit)
            pos.sl_order_id = sl_tp.get("sl_order_id")
            pos.tp_order_id = sl_tp.get("tp_order_id")
            if pos.sl_order_id:
                pos.exchange_sl_price = pos.stop_loss
            if not pos.sl_order_id:
                pos.sl_order_id = "software"
                logger.warning(f"[ORPHAN] Exchange SL placement failed for {symbol} — software SL@{pos.stop_loss:.4f}")
        except Exception as e:
            pos.sl_order_id = "software"
            logger.error(f"[ORPHAN] SL/TP placement failed for {symbol}: {e} — software SL@{pos.stop_loss:.4f}")

        # Make sure this symbol is priced on future cycles
        try:
            if symbol not in self.active_pairs:
                self.active_pairs.append(symbol)
        except Exception:
            pass

        # Persist immediately so a restart doesn't re-orphan it
        try:
            self.risk._save_state()
        except Exception as e:
            logger.debug(f"[ORPHAN] _save_state after adoption failed: {e}")

        # Telegram alert — this is a real-money event, must not be silent
        try:
            notifier.send(
                f"⚠️ ORPHAN POSITION ADOPTED (per-cycle scan)\n"
                f"{symbol} {side.upper()}\n"
                f"Entry: {entry_price} | Amount: {amount} | Margin: ${margin:.2f}\n"
                f"SL: {pos.stop_loss:.4f} | TP: {pos.take_profit:.4f}\n"
                f"Cycle: #{self.cycle_count}"
            )
        except Exception:
            pass

    def _extract_fill_price(self, order: dict, fallback: float, is_exit: bool = False) -> float:
        """Get real fill price from exchange.

        For ENTRIES: fetch position entryPrice (source of truth).
        For EXITS: fetch order fill or last trade (position is already closed).
        """
        symbol = order.get("symbol") if order else None
        if not symbol:
            return fallback

        time.sleep(1.5)  # let the order settle on exchange

        if is_exit:
            # --- EXIT path: position is closed, fetch fill from order or trades ---
            order_id = order.get("id") if order else None

            # 1. Try fetch_order to get the actual average fill price
            if order_id:
                try:
                    fetched = self.exchange.client.fetch_order(order_id, symbol)
                    avg = fetched.get("average") if fetched else None
                    if avg is not None:
                        avg = float(avg)
                        if avg > 0:
                            logger.info(f"[FILL] {symbol} exit fill (fetch_order): {avg}")
                            return avg
                except Exception as e:
                    logger.debug(f"[FILL] fetch_order failed for {symbol}: {e}")

            # 2. Try fetch_my_trades to get the last trade's fill price
            try:
                trades = self.exchange.client.fetch_my_trades(symbol, limit=1)
                if trades:
                    trade_price = float(trades[-1].get("price", 0))
                    if trade_price > 0:
                        logger.info(f"[FILL] {symbol} exit fill (last trade): {trade_price}")
                        return trade_price
            except Exception as e:
                logger.debug(f"[FILL] fetch_my_trades failed for {symbol}: {e}")

            # 3. Try order response average field directly
            if order:
                fill = order.get("average")
                try:
                    fill = float(fill)
                    if fill > 0:
                        logger.info(f"[FILL] {symbol} exit fill (order response): {fill}")
                        return fill
                except (TypeError, ValueError):
                    pass

            logger.warning(f"[FILL] {symbol} exit using fallback price: {fallback}")
            return fallback

        # --- ENTRY path: fetch position entryPrice (source of truth) ---
        try:
            positions = self.exchange.client.fetch_positions([symbol])
            for p in positions:
                if p.get("symbol") == symbol and float(p.get("contracts", 0)) > 0:
                    entry = float(p.get("entryPrice", 0))
                    if entry > 0:
                        logger.info(f"[FILL] {symbol} real entry price: {entry}")
                        return entry
        except Exception as e:
            logger.warning(f"[FILL] Could not fetch position for {symbol}: {e}")

        # Fallback: try order average
        if order:
            fill = order.get("average")
            try:
                fill = float(fill)
                if fill > 0:
                    return fill
            except (TypeError, ValueError):
                pass

        logger.warning(f"[FILL] {symbol} entry using fallback price: {fallback}")
        return fallback

    def _extract_fill_amount(self, order: dict, fallback: float) -> float:
        """Extract actual filled amount from exchange order response. Falls back to calculated amount."""
        if not order:
            return fallback
        filled = order.get("filled") or order.get("amount")
        try:
            filled = float(filled)
            if filled > 0:
                return filled
        except (TypeError, ValueError):
            pass
        return fallback

    def _shutdown(self):
        if self._ws_feed:
            self._ws_feed.stop()
        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        logger.info(f"Shutting down. Open positions: {list(self.risk.positions.keys())}")
        self.risk.print_stats(balance)
        notifier.notify_shutdown(list(self.risk.positions.keys()), balance)
