---
name: Existing Trading Infrastructure
description: L2 orderbook and tape/flow systems already built in Phmex-S — check before proposing new features
type: reference
---

## L2 Orderbook (ALREADY EXISTS)
- Method: exchange.get_order_book(symbol) → exchange.py:77-118
- Returns: imbalance, bid_walls, ask_walls, spread_pct, illiquid flag, best_bid/ask
- Wall detection: >5x average level volume
- Fetched at entry time: bot.py:707 (stored in `ob` variable)
- Strategy gate: ±0.3 imbalance block (strategies.py:116-145)
- Ensemble layer: ±0.1 imbalance → confidence boost (bot.py:253)
- Strength booster: ±0.15 imbalance → +0.02 strength (strategies.py:839-840)

## Tape / Order Flow (ALREADY EXISTS)
- WebSocket: ws_feed.py streams trades via ccxt.pro watch_trades()
- Per-candle aggregation: buy_volume, sell_volume, buy_ratio, delta, CVD, cvd_slope, divergence, large_trade_count, large_trade_bias
- REST fallback: exchange.get_recent_trades() and exchange.get_cvd()
- Ensemble layer 7: buy_ratio >0.55 (long) / <0.45 (short) → bot.py:258-260
- Extreme veto: buy_ratio <0.30 blocks long, >0.70 blocks short (bot.py:786-798)
- Dashboard: "TAPE READER" station in war_room.py

## PREVIOUSLY UNDERUSED — NOW ACTIVE (Sentinel v11, deployed 2026-04-01)
- cvd_slope: now gated at ±0.3 (blocks entries when selling/buying accelerating)
- divergence: now gated (blocks long on "bearish", short on "bullish")
- large_trade_bias: now gated at ±0.3 (blocks entries against whale flow)
- Wall-based veto: now active (blocks long with unmatched ask wall, vice versa)
- Spread veto: now active at >0.15% (blocks entries in illiquid conditions)
- Strategy OB gate: tightened from ±0.3 to ±0.25
- Buy ratio veto: tightened from 0.30/0.70 to 0.45/0.55
