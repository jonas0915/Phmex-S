import html
import os
import requests

BOT_NAME = "Phmex-S"

def send(message: str):
    token   = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception as e:
        import logging
        logging.getLogger("DegenCryt").debug(f"[TG] Send failed: {e}")

def _env_float(name: str, default: float) -> float:
    """Import-light config read (notifier deliberately does not import Config)."""
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default

def notify_startup(balance: float, pairs: list, mode: str, strategy: str):
    # Config.STRATEGY still reads "confluence", but since the 5/02 strategy cull the
    # confluence router emits only htf_l2_anticipation — report what actually trades.
    send(
        f"🤖 <b>{BOT_NAME} Started</b>\n"
        f"Mode: {mode.upper()} | Strategy: htf_l2_anticipation (confluence router)\n"
        f"Leverage: {os.getenv('LEVERAGE', '10')}x | Margin/trade: ${os.getenv('TRADE_AMOUNT_USDT', '8')}\n"
        f"Balance: <b>${balance:.2f} USDT</b>\n"
        f"Pairs: {', '.join(p.split('/')[0] for p in pairs)}"
    )

def _tp_backstop_hint() -> str:
    """When partial-TP is armed, the resting exchange TP is only a backstop —
    real exit management scales half at +PARTIAL_TP_ROI and re-targets the
    runner to +PARTIAL_RUNNER_TP_ROI. Empty when partial-TP is off."""
    ptp = _env_float("PARTIAL_TP_ROI", 0.0)
    if ptp <= 0:
        return ""
    runner = _env_float("PARTIAL_RUNNER_TP_ROI", 0.0)
    runner_txt = f", runner +{runner:.0f}%" if runner > 0 else ""
    return f"  (backstop — scales ½ at +{ptp:.0f}% ROI{runner_txt})"

def notify_entry(symbol: str, side: str, price: float, margin: float, sl: float, tp: float, strength: float, reason: str, strategy: str = "", confidence=None):
    emoji = "🟢" if side == "long" else "🔴"
    direction = "LONG" if side == "long" else "SHORT"
    signal_line = ""
    if strategy:
        conf_txt = f" ({confidence}/7)" if confidence is not None else ""
        signal_line = f"Signal:   <b>{html.escape(strategy)}</b>{conf_txt}\n"
    send(
        f"{emoji} <b>[LIVE] {direction} ENTRY — {symbol}</b>  [{BOT_NAME}]\n"
        f"{signal_line}"
        f"Price:    ${price:.4f}\n"
        f"Margin:   ${margin:.2f} USDT\n"
        f"SL:       ${sl:.4f}  ({(sl-price)/price*100:+.1f}%)\n"
        f"TP:       ${tp:.4f}  ({(tp-price)/price*100:+.1f}%){_tp_backstop_hint()}\n"
        f"Strength: {strength:.2f}\n"
        f"Reason:   {reason}"
    )

def notify_exit(symbol: str, side: str, entry: float, exit_price: float, pnl: float, pnl_pct: float, reason: str):
    # Slot live exits arrive as e.g. "take_profit [slot 5m_mean_revert]" — strip the
    # suffix before matching so the pretty label/emoji still render, then re-display
    # the suffix after the label.
    base = reason
    suffix = ""
    idx = reason.find(" [slot ")
    if idx != -1 and reason.endswith("]"):
        base, suffix = reason[:idx], reason[idx:]
    if base == "take_profit" or base == "partial_tp":
        emoji = "✅"
        label = "TAKE PROFIT" if base == "take_profit" else "PARTIAL TP"
    elif base == "stop_loss":
        emoji = "🔴"
        label = "STOP LOSS"
    elif base == "early_exit":
        emoji = "⚡"
        label = "EARLY EXIT"
    elif base == "trailing_stop":
        emoji = "🎯"
        label = "TRAILING STOP"
    elif base == "durable_sl":
        emoji = "🛡"
        label = "DURABLE SL"
    else:
        emoji = "⏹"
        label = base.upper()
    sign = "+" if pnl >= 0 else ""
    send(
        f"{emoji} <b>[LIVE] {label}{suffix} — {symbol}</b>  [{BOT_NAME}]\n"
        f"Entry: ${entry:.4f}  →  Exit: ${exit_price:.4f}\n"
        f"PnL:   <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        f"Reason: {reason}"
    )

def notify_partial_tp(symbol: str, side: str, exit_price: float, pnl: float, pnl_pct: float):
    sign = "+" if pnl >= 0 else ""
    send(
        f"⚡ <b>[LIVE] PARTIAL TP — {symbol}</b>  [{BOT_NAME}]\n"
        f"Half banked @ ${exit_price:.4f} (+{_env_float('PARTIAL_TP_ROI', 10):.0f}% ROI target)\n"
        f"PnL on half: <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        # Truthful copy (risk_manager.partial_close_position): the stop is deliberately
        # NOT moved — the runner keeps the original SL / trail floor, TP re-targets.
        f"Runner keeps ORIGINAL SL/trail — targets +{_env_float('PARTIAL_RUNNER_TP_ROI', 25):.0f}% ROI"
    )

def notify_sl_move_fail(symbol: str, target_sl: float, resting_sl: float, error: str):
    send(
        f"🚨 <b>SL MOVE FAILED — {symbol}</b>  [{BOT_NAME}]\n"
        f"Could not ratchet exchange SL to ${target_sl:.4f}\n"
        f"Old SL still resting at ${resting_sl:.4f} — position is NOT naked\n"
        f"Error: {error[:200]}"
    )

def notify_drawdown(drawdown: float, balance: float, peak: float):
    send(
        f"⚠️ <b>DRAWDOWN WARNING</b>  [{BOT_NAME}]\n"
        f"Current equity: ${balance:.2f} USDT\n"
        f"Peak equity:    ${peak:.2f} USDT\n"
        f"Drawdown:       <b>{drawdown:.1f}%</b>\n"
        f"Action: Trading halted until manual review"
    )

def notify_ban_mode(duration_minutes: int):
    send(
        f"🚨 <b>CONNECTION BLOCKED</b>  [{BOT_NAME}]\n"
        f"Phemex CDN rate limit hit (403)\n"
        f"Bot paused for {duration_minutes} minutes\n"
        f"Will auto-resume when clear"
    )

def notify_ban_lifted():
    send(f"✅ <b>Connection Restored</b>  [{BOT_NAME}]\nBot is back online and trading.")

def notify_ban_stuck(minutes: int, diag: dict | None = None):
    diag_str = ""
    if diag:
        diag_str = f"\nNetwork: {diag.get('network', '?')} | VPN: {diag.get('vpn', '?')}"
    send(
        f"⚠️ <b>BAN MODE STUCK</b>  [{BOT_NAME}]\n"
        f"Bot stuck in ban mode for {minutes}+ minutes.{diag_str}\n"
        f"Manual check recommended."
    )

def notify_shutdown(open_positions: list, balance: float):
    pos_str = ', '.join(open_positions) if open_positions else 'None'
    send(
        f"🛑 <b>{BOT_NAME} Stopped</b>\n"
        f"Open positions: {pos_str}\n"
        f"Balance: ${balance:.2f} USDT"
    )

def notify_paper_entry(symbol: str, side: str, price: float, margin: float, strength: float, reason: str, slot: str = ""):
    emoji = "🔵" if side == "long" else "🟣"
    direction = "LONG" if side == "long" else "SHORT"
    slot_tag = f"[{slot}] " if slot else ""
    send(
        f"{emoji} <b>[PAPER] {slot_tag}{direction} ENTRY — {symbol}</b>  [{BOT_NAME}]\n"
        f"Price:    ${price:.4f}\n"
        f"Margin:   ${margin:.2f} USDT (simulated)\n"
        f"Strength: {strength:.2f}\n"
        f"Reason:   {reason}"
    )

def notify_paper_exit(symbol: str, side: str, entry: float, exit_price: float, pnl: float, pnl_pct: float, reason: str, slot: str = ""):
    emoji = "🔷" if pnl >= 0 else "🔶"
    sign = "+" if pnl >= 0 else ""
    slot_tag = f"[{slot}] " if slot else ""
    send(
        f"{emoji} <b>[PAPER] {slot_tag}EXIT — {symbol}</b>  [{BOT_NAME}]\n"
        f"Entry: ${entry:.4f}  →  Exit: ${exit_price:.4f}\n"
        f"PnL:   <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        f"Reason: {reason}"
    )
