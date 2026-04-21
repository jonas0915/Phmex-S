# Trading Desk v2 — Full Overhaul Design Spec

**Date:** 2026-03-23
**Status:** Approved by Jonas (brainstorming session)

## Vision
Transform the trading desk dashboard into a premium SF fintech hedge fund command center. Curved glass tower (Salesforce-inspired) with a penthouse trading floor, holographic data displays, 9 animated agents, full SF Bay Area environment, and comprehensive real-time trading data.

---

## 1. Architecture — The Building

### Current
- Square/blocky building geometry
- Flat, simple construction

### Target
- **Curved glass tower** — cylindrical/tapered like Salesforce Tower
- Floor-to-ceiling glass panels with subtle reflections
- Soft ambient glow from interior lights visible through glass
- Tower sits prominently in the SF skyline
- Camera can show establishing shot of tower, then transitions to penthouse interior
- Penthouse (top floor) is where the trading floor lives

---

## 2. Interior — Trading Floor

### Current
- Isometric desk stations with basic monitors and chairs
- Square room layout

### Target
- **Open-plan penthouse** with curved glass walls (matching tower shape)
- **Holographic displays** floating above desks — PnL, charts, trade feeds projected in mid-air
- Blue/cyan holographic aesthetic (Tony Stark lab meets Bloomberg terminal)
- Premium desk surfaces (dark wood/glass)
- Ambient LED underglow on desks (status-colored: green=active, orange=waiting, red=alert)
- Curved panoramic windows showing the SF skyline
- Modern fintech office feel — standing desks, lounge seating areas

### Facilities (Keep All — SF Fintech Culture)
- **Gym** — agents work out during low-volume periods
- **Bar/Lounge** — after-hours socializing
- **Jacuzzi** — rooftop amenity
- **Cafeteria/Kitchen** — lunch breaks
- **Break Room** — coffee, casual chat
- **Conference Room** — agent team meetings before big trades

---

## 3. Characters — 9 Agents + Jonas

Each agent represents a real component of the bot:

| Agent | Role | Bot Component | Personality |
|-------|------|---------------|-------------|
| **Ensemble** | Portfolio Manager | Final trade decisions, ensemble gating | Confident, decisive |
| **Scanner** | Analyst | Pair discovery, volume scanning | Curious, data-driven |
| **Risk** | Risk Officer | SL/TP, drawdown, Kelly sizing | Cautious, strict |
| **Executor** | Trader | Order placement, fill prices | Fast, precise |
| **Strategy** | Quant | confluence_pullback, momentum_cont | Analytical, quiet |
| **Tape** | Flow Analyst | Order book, aggressor flow, CVD | Intense, focused |
| **WS Feed** | Data Engineer | WebSocket streams, data freshness | Calm, reliable |
| **Pos Monitor** | Operations | Open position tracking, sync | Vigilant, organized |
| **Jonas** | CEO/Founder | Human oversight | Custom avatar |

### Agent Behaviors
- Work at desks during active trading
- Visit facilities during quiet periods
- Gather at conference room before large position decisions
- Speech bubbles show what they're doing ("Scanning BTC volume...", "Kelly says $8.50 margin")
- Walk between areas with smooth animations

---

## 4. Environment — SF Bay Area

### Current Problems
- Gray/brown block buildings — looks cheap
- Bridges cut off at edges
- Flat, lifeless skyline
- No recognizable SF landmarks

### Target
- **Full Golden Gate Bridge** — visible and complete, not cut off
- **Bay Bridge** visible from another angle
- **SF Skyline** — varied building heights, glass towers, recognizable shapes
  - Transamerica Pyramid
  - Salesforce Tower (our building, front and center)
  - Other mixed-height towers with lit windows
- **Bay water** — animated with subtle waves, reflections of city lights at night
- **Alcatraz** — visible island in the bay
- **SF Hills** — terrain has elevation changes (Nob Hill, Twin Peaks silhouette)
- **Fog** — procedural fog that rolls in, especially evening/morning (signature SF weather)
- **City lights at night** — windows glow, street lights, car headlights on bridges
- **Better textures** — glass reflections, concrete variation, not flat colored blocks

---

## 5. Data Panels — Comprehensive Trading Data

### Current
- Bottom HUD (balance, PnL, WR, drawdown, positions, trades, cycle, Kelly, confidence)
- Intel panel top-left (Kelly, Hurst, CVD, strategies, exit reasons)
- Agent comms top-right (chat log)
- Live feed (last 8 events)

### New Additions (ALL of these)

#### A. Live Equity Curve
- Line chart showing account balance over time
- Overlays: trade entry/exit markers, drawdown shading
- Timeframe toggle (1h, 4h, 1d, 7d, all-time)

#### B. Per-Pair Performance Cards
- Mini card for each active pair (BTC, ETH, SOL, BNB, XRP)
- Shows: current price, WR, PnL, # trades, last signal
- Color-coded border (green=profitable, red=losing)

#### C. Real-Time Order Book Visualization
- Depth chart or bid/ask heatmap for the currently selected pair
- Shows support/resistance clusters

#### D. Detailed Trade History Feed
- Scrollable list of recent trades
- Each entry: pair, side, entry/exit price, PnL, duration, strategy, exit reason
- Color-coded (green wins, red losses)
- Click to expand for full details

#### E. Market Overview
- BTC dominance %
- Total crypto market cap
- Fear & Greed index
- Funding rates for active pairs

#### F. Strategy Leaderboard
- Table: strategy name, # trades, WR, total PnL, avg PnL
- Sorted by profitability
- Real-time updates as trades close

#### G. Pair Performance Heat Map
- Grid of pairs × time periods
- Color intensity = PnL (green = profit, red = loss)
- Quick visual of what's working where

### Data Panel Design
- **Modern fintech aesthetic** — dark theme, glassmorphism panels, subtle blur backgrounds
- **Holographic integration** — key metrics (PnL, balance, open positions) displayed as holographic projections above the trading floor
- **Collapsible/draggable panels** — user can arrange layout
- **High data density** — inspired by Bloomberg Terminal but cleaner

---

## 6. Visual Style

### Colors
- Dark navy/charcoal base (#0a0f1a, #111827)
- Cyan/teal accents (#00d4ff, #67e8f9) — holographic glow
- Green for profit (#10b981)
- Red for loss (#ef4444)
- Warm amber for alerts (#f59e0b)
- Glassmorphism panels (semi-transparent with blur)

### Typography
- Nunito for UI text
- Fira Code / JetBrains Mono for data/numbers
- Clean, readable at small sizes

### Lighting
- Keep dynamic 24-hour day/night cycle
- Add city lights that turn on at dusk
- Holographic glow illuminates the trading floor
- Fog effects during dawn/dusk

---

## 7. Technical Constraints

### CRITICAL — Dashboard Isolation Rule (Jonas directive)
- Dashboard must NEVER make API calls to the exchange
- Read-only access to: trading_state.json, logs/bot.log
- Must not affect bot performance in any way
- Keep 3-second refresh interval

### Performance
- Target 30fps on MacBook
- Lazy-load heavy 3D elements
- Optimize draw calls for the expanded city scene
- LOD (level of detail) for distant buildings

### Framework
- Keep Three.js for 3D rendering
- Keep vanilla JS (no React/Vue overhead)
- Keep Python HTTP server (ThreadingHTTPServer)

---

## 8. Implementation Priority

### Phase 1 — Building & Environment
- Curved glass tower geometry
- SF skyline with varied buildings
- Full Golden Gate Bridge
- Bay water with reflections
- Hills/terrain

### Phase 2 — Interior & Holographics
- Penthouse interior redesign
- Holographic display system
- Updated desk layout
- Agent character improvements

### Phase 3 — Data Panels
- Equity curve chart
- Per-pair cards
- Strategy leaderboard
- Trade history feed
- Market overview
- Heat map
- Order book visualization

### Phase 4 — Polish
- Fog effects
- City lights at night
- Panel glassmorphism
- Animations and transitions
- Performance optimization

---

## Data Sources

All data comes from existing read-only sources:
- `trading_state.json` — closed trades, peak balance, state
- `logs/bot.log` — real-time events, stats, signals
- No new API calls or data feeds needed
- Market overview data (BTC dominance, fear/greed) would need a lightweight external fetch — OR can be parsed from existing bot data if available

---

## Estimated Scope
- ~3-4 implementation sessions
- trading_desk.py is currently 7,736 lines — will grow significantly
- Consider splitting into modules (scene.js, panels.js, agents.js, data.js) served as separate files
