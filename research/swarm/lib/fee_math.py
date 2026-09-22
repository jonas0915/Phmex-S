"""Break-even arithmetic for the desk (spec §3). Every WR / time-to-verdict number
an agent reports must come from here, not from hand arithmetic."""
from __future__ import annotations

import math

FEES_RT_BPS = 7.0        # maker 0.01% + taker 0.06% per side (bot's real mix)
ADVERSE_BPS = 4.5        # measured post-fill adverse selection
C_BPS = FEES_RT_BPS + ADVERSE_BPS

# USD notional of one lot (Phemex USDT perps, 03_exchange_economics.md:57-68)
LOT_MIN_USD = {"BTC": 77.74, "ETH": 24.9738, "SOL": 1.0143, "XRP": 1.0044, "DOGE": 1.0010}
MIN_ORDER_VALUE_USD = 1.0


def base_symbol(symbol: str) -> str:
    """'BTC', 'BTC_USDT_USDT', 'BTC/USDT:USDT', 'btc/usdt' -> 'BTC'."""
    return symbol.replace("/", "_").replace(":", "_").split("_")[0].upper()


def p_star(target_bps: float, cost_bps: float = C_BPS) -> float:
    """Required win rate for a symmetric TP/SL of `target_bps` after round-trip cost."""
    if target_bps <= 0:
        raise ValueError("target_bps must be > 0")
    return (target_bps + cost_bps) / (2.0 * target_bps)


def net_bps(gross_bps: float, cost_bps: float = C_BPS) -> float:
    return gross_bps - cost_bps


def time_to_verdict_weeks(trades_per_week: float, n_required: int = 50) -> float:
    if trades_per_week <= 0:
        return math.inf
    return n_required / trades_per_week


def position_notional(capital_usd: float = 200.0, risk_frac: float = 0.10, leverage: int = 10) -> float:
    return capital_usd * risk_frac * leverage


def lot_check(symbol: str, notional_usd: float) -> dict:
    base = base_symbol(symbol)
    lot_usd = LOT_MIN_USD.get(base)
    if lot_usd is None:
        return {"ok": notional_usd >= MIN_ORDER_VALUE_USD, "lots": int(notional_usd // MIN_ORDER_VALUE_USD), "lot_usd": None}
    lots = int(notional_usd // lot_usd)
    return {"ok": lots >= 1, "lots": lots, "lot_usd": lot_usd}


def max_concurrent(sl_bps: float, notional_usd: float | None = None, kill_net_usd: float = 10.0,
                   cost_bps: float = C_BPS) -> int:
    """Portfolio concurrency cap: the most positions that may be open at once so that ONE
    simultaneous cluster of stops (every open position hitting its SL together, cost
    included) cannot alone breach the paper dollar kill cap.

        stop_loss_usd  = notional_usd * (sl_bps + cost_bps) / 1e4
        max_concurrent = max(1, floor(kill_net_usd / stop_loss_usd))

    Defaults: notional_usd = position_notional() ($200), kill_net_usd = 10.0 (build.js
    KILL_NET_USD magnitude), cost_bps = C_BPS. Added 2026-09-21 after the
    informed_flow_btc_alt_cascade_v2 paper kill: 5 concurrent $200 shorts (sl 150 bps) all
    stopped on one BTC pump for -$16.20 against a -$10 cap that had been sized to a single
    position. registrar.freeze fills spec.max_concurrent from this; screen.run_screen admits
    trades under it; the slot enforces it live (STANDARDS #17).
    """
    if notional_usd is None:
        notional_usd = position_notional()
    if sl_bps <= 0 or notional_usd <= 0 or kill_net_usd <= 0:
        raise ValueError("sl_bps, notional_usd and kill_net_usd must be > 0")
    stop_loss_usd = notional_usd * (sl_bps + cost_bps) / 1e4
    return max(1, int(math.floor(kill_net_usd / stop_loss_usd)))
