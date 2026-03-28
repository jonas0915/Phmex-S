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

def notify_startup(balance: float, pairs: list, mode: str, strategy: str):
    send(
        f"🤖 <b>{BOT_NAME} Started</b>\n"
        f"Mode: {mode.upper()} | Strategy: {strategy}\n"
        f"Leverage: {os.getenv('LEVERAGE', '10')}x | Margin/trade: ${os.getenv('TRADE_AMOUNT_USDT', '8')}\n"
        f"Balance: <b>${balance:.2f} USDT</b>\n"
        f"Pairs: {', '.join(p.split('/')[0] for p in pairs)}"
    )

def notify_entry(symbol: str, side: str, price: float, margin: float, sl: float, tp: float, strength: float, reason: str, shadow_skip: bool = False):
    emoji = "🟢" if side == "long" else "🔴"
    direction = "LONG" if side == "long" else "SHORT"
    shadow_tag = " ⏳ SHADOW ZONE" if shadow_skip else ""
    send(
        f"{emoji} <b>[LIVE] {direction} ENTRY — {symbol}</b>  [{BOT_NAME}]{shadow_tag}\n"
        f"Price:    ${price:.4f}\n"
        f"Margin:   ${margin:.2f} USDT\n"
        f"SL:       ${sl:.4f}  ({(sl-price)/price*100:+.1f}%)\n"
        f"TP:       ${tp:.4f}  ({(tp-price)/price*100:+.1f}%)\n"
        f"Strength: {strength:.2f}\n"
        f"Reason:   {reason}"
    )

def notify_exit(symbol: str, side: str, entry: float, exit_price: float, pnl: float, pnl_pct: float, reason: str, shadow_skip: bool = False):
    if reason == "take_profit" or reason == "partial_tp":
        emoji = "✅"
        label = "TAKE PROFIT" if reason == "take_profit" else "PARTIAL TP"
    elif reason == "stop_loss":
        emoji = "🔴"
        label = "STOP LOSS"
    elif reason == "early_exit":
        emoji = "⚡"
        label = "EARLY EXIT"
    else:
        emoji = "⏹"
        label = reason.upper()
    sign = "+" if pnl >= 0 else ""
    shadow_tag = "\n⏳ <i>Shadow zone trade</i>" if shadow_skip else ""
    send(
        f"{emoji} <b>[LIVE] {label} — {symbol}</b>  [{BOT_NAME}]\n"
        f"Entry: ${entry:.4f}  →  Exit: ${exit_price:.4f}\n"
        f"PnL:   <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        f"Reason: {reason}{shadow_tag}"
    )

def notify_partial_tp(symbol: str, side: str, exit_price: float, pnl: float, pnl_pct: float):
    sign = "+" if pnl >= 0 else ""
    send(
        f"⚡ <b>[LIVE] PARTIAL TP — {symbol}</b>  [{BOT_NAME}]\n"
        f"Closed 50% @ ${exit_price:.4f}\n"
        f"PnL on half: <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        f"Remaining 50% running with SL at breakeven"
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

def notify_shutdown(open_positions: list, balance: float):
    pos_str = ', '.join(open_positions) if open_positions else 'None'
    send(
        f"🛑 <b>{BOT_NAME} Stopped</b>\n"
        f"Open positions: {pos_str}\n"
        f"Balance: ${balance:.2f} USDT"
    )

def notify_paper_entry(symbol: str, side: str, price: float, margin: float, strength: float, reason: str):
    emoji = "🔵" if side == "long" else "🟣"
    direction = "LONG" if side == "long" else "SHORT"
    send(
        f"{emoji} <b>[PAPER] {direction} ENTRY — {symbol}</b>  [{BOT_NAME}]\n"
        f"Price:    ${price:.4f}\n"
        f"Margin:   ${margin:.2f} USDT (simulated)\n"
        f"Strength: {strength:.2f}\n"
        f"Reason:   {reason}"
    )

def notify_paper_exit(symbol: str, side: str, entry: float, exit_price: float, pnl: float, pnl_pct: float, reason: str):
    emoji = "🔷" if pnl >= 0 else "🔶"
    sign = "+" if pnl >= 0 else ""
    send(
        f"{emoji} <b>[PAPER] EXIT — {symbol}</b>  [{BOT_NAME}]\n"
        f"Entry: ${entry:.4f}  →  Exit: ${exit_price:.4f}\n"
        f"PnL:   <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        f"Reason: {reason}"
    )
