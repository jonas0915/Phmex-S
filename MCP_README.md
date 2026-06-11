# Phmex-S MCP Server

Exposes the live trading bot's state and safe controls to MCP-compatible clients
(Claude Code terminal, Claude Desktop, claude.ai web/mobile via HTTP).

## Tools

### Read-only
- `phmex_status()` — running, PID, last cycle, today's PnL, paused status
- `phmex_open_positions()` — current positions w/ side, entry, SL, TP, age
- `phmex_recent_trades(limit)` — last N closed trades
- `phmex_pnl(period)` — aggregated PnL for `today`/`week`/`month`/`all`
- `phmex_lessons_search(query)` — full-text search across `memory/lessons.md`
- `phmex_memory_search(query)` — search across all `memory/*.md`
- `phmex_memory_list()` — list memory files w/ size + mtime
- `phmex_recent_log(lines, level)` — tail `logs/bot.log`, filter by level
- `phmex_params()` — current `.env` config (API keys redacted)

### Control (require `confirm=True`)
- `phmex_pause_bot(reason, confirm)` — writes `.pause_trading` sentinel
- `phmex_resume_bot(confirm)` — clears the sentinel
- `phmex_kill_slot(slot_id, confirm)` — writes `.kill_<slot_id>` sentinel
- `phmex_run_backtest(strategy, days, confirm)` — detached subprocess, log path returned

## Safeguards
- `confirm=True` required on every destructive action
- Every call audited to `logs/mcp_audit.log`
- Rate limit: 1 destructive action per 10 sec
- Server **does not place new orders** — entry decisions stay with the bot
- HTTP transport requires `MCP_API_KEY` (≥16 chars) env var
- HTTP defaults to `127.0.0.1` only

## Install

```bash
cd ~/Desktop/Phmex-S
pip3 install -r mcp_requirements.txt
```

## Run

### stdio (Claude Code launches it as subprocess)
Don't run manually — register it in Claude Code (see below).

### HTTP (claude.ai web/mobile/Desktop)
```bash
export MCP_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
echo "Save this: $MCP_API_KEY"
python3 ~/Desktop/Phmex-S/mcp_server.py --http --port 7878
```

## Register with Claude Code

Add to `~/.claude.json` (global) or `<project>/.claude.json`:

```json
{
  "mcpServers": {
    "phmex-s": {
      "command": "python3",
      "args": ["/Users/jonaspenaso/Desktop/Phmex-S/mcp_server.py"]
    }
  }
}
```

Or use the CLI:
```bash
claude mcp add phmex-s python3 /Users/jonaspenaso/Desktop/Phmex-S/mcp_server.py
```

## Usage example (in Claude)

```
You: what's my PnL today?
Claude: [calls phmex_pnl(period="today")]
        Today: 4 trades (3W/1L), net +$1.82, win rate 75%.

You: pause the bot, dinner
Claude: [calls phmex_pause_bot(reason="dinner", confirm=True)]
        ✅ Paused. Bot will stop new entries within 60s.
```

## Audit log

```bash
tail -f logs/mcp_audit.log
```
