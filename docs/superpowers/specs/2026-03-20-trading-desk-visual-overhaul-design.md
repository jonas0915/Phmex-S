# Trading Desk Visual Overhaul — Design Spec

**Date:** 2026-03-20
**File:** `trading_desk.py` (port 8060)
**Goal:** Upgrade the Sims-style 3D trading floor to COD-quality realistic visuals while preserving the existing scene structure, event system, and data pipeline.

---

## Constraints

- **Dashboard isolation**: Zero bot imports, zero API calls. Reads `trading_state.json` + `logs/bot.log` only.
- **Performance**: 30+ FPS on integrated GPU. Must not compete with the bot for resources.
- **Structure preserved**: Same room dimensions (12×10×4), desk positions, camera angle, HUD layout, social events, sleep system, lower floors.

---

## 1. Approach: GLTF Model Assets + THREE.js

Replace all procedural character geometry (sphere/cylinder/capsule combos) with pre-made rigged GLTF humanoid models. Replace procedural furniture with GLTF office assets. Upgrade environment with HDRI skybox and improved procedural panorama.

This is the industry-standard way to achieve realistic 3D in a browser.

---

## 2. Characters

### 2.1 Agent Roster (9 characters)

| # | Agent | Bot Subsystem | Desk Position (current) | Appearance |
|---|-------|--------------|------------------------|------------|
| 1 | **Jonas** | Head Trader / CEO | (2.2, 0, 2.5) — standing command station | Casual tech CEO: hoodie + jeans. Face modeled from `jonas_avatar.jpg`. Slightly taller (boss presence). 6 monitors. |
| 2 | **Scanner** | Dynamic pair selection, volume ranking | (-2.2, 0, -1.5) | Professional, crew-cut hair. 2 monitors. |
| 3 | **Risk Manager** | Kelly sizing, drawdown limits, cooldowns, regime filter | (2.2, 0, -1.5) | Formal, glasses. 2 monitors. |
| 4 | **Ensemble** | 6-layer confidence gate (HTF, VWAP, CVD, Hurst, funding, OB) | Replaces Claude at (0, 0, 0.5) | Analytical look, scale 1.2×. 3 monitors. |
| 5 | **Executor** | Order placement, SL/TP, fill tracking | Replaces Trend at (-4.0, 0, 0.5) | Sharp, focused. 2 monitors. |
| 6 | **Strategy** | 4 strategies (trend_pullback, keltner, momentum_cont, vwap_reversion) | Replaces Range at (4.0, 0, 0.5) | Thoughtful, casual. 2 monitors. |
| 7 | **Tape Reader** | Aggressor ratio, order flow | (-2.2, 0, 2.5) | Focused, headphones. 2 monitors. |
| 8 | **WS Feed** | WebSocket connectivity, data freshness | Replaces Therapist at (4.5, 0, 4.2) | Tech/IT look. 2 monitors. |
| 9 | **Position Monitor** | Open position tracking, exit logic (early_exit, flat_exit, time_exit) | (0, 0, 2.5) — between Jonas and Tape Reader | Watchful, alert. 2 monitors. |

### 2.2 Model Source

- **Mixamo** (Adobe, free): Rigged humanoid models with realistic proportions.
- **Format**: `.glb` (binary GLTF, compact).
- **Size**: ~1-2MB per character, ~12-15MB total for 9 characters.
- Each character gets a distinct body type, skin tone, and outfit baked into the GLTF.
- Jonas: custom UV-mapped face texture generated from `jonas_avatar.jpg`.
- **Skeleton standardization**: All 9 characters MUST use the same Mixamo base skeleton (same bone hierarchy, same bone names) to ensure animation clip sharing via `THREE.AnimationMixer`. Download all characters with the standard Mixamo armature.

### 2.3 Animation Clips (Mixamo)

Shared animation clips applied to any character via `THREE.AnimationMixer`. Crossfade between clips with 0.3s blend time.

| Animation | Use | Duration |
|-----------|-----|----------|
| `idle-seated` | Default state at desk | Loop |
| `typing` | Normal operation | Loop |
| `walking` | Moving between locations | Loop |
| `standing-up` | Reacting to events | 1.5s |
| `sitting-down` | Returning to desk | 1.5s |
| `celebrating` | Win / streak | 3s |
| `head-shake` | Stop loss / rejection | 2s |
| `pointing` | Signal detected | 2s |
| `phone-talk` | Scanner updating | Loop |
| `high-five` | 3+ win streak (2 characters) | 2s |

**Multi-character animation note**: High-five requires two characters to meet. Implementation approach: both characters walk to a midpoint between their desks (using existing walk system), play matching Mixamo "clapping" clips facing each other at the meeting point, then walk back. Use two separate single-character clips (not a paired animation), synchronized by starting both at the same frame.
| `desk-slam` | Big loss | 1.5s |
| `arms-crossed` | Cooldown / regime pause | Loop |

---

## 3. Event-Driven Animation System

### 3.1 Three Behavior Tiers

**Tier 1 — Professional Baseline:** Default state. Characters sit at desks, type, check monitors, subtle head movements. Calm office energy.

**Tier 2 — Active Trading:** Signals fire, positions open/close. Characters stand up, point at screens, lean forward, type fast. Energy picks up.

**Tier 3 — Wolf of Wall Street:** Streaks, big wins/losses, milestones. High-fives, desk slams, team huddles, celebrations.

### 3.2 Event → Animation Map

| Bot Event | Tier | Who Reacts | Animation |
|-----------|------|------------|-----------|
| Normal cycle | T1 | All | Seated typing, subtle head bobs, occasional monitor glance |
| `[SCANNER]` update | T1 | Scanner | Picks up phone, talks briefly. Monitor flashes new pair data. |
| `[WS]` reconnect | T1 | WS Feed | Leans forward, types rapidly. Monitor shows red → green. |
| `[COOLDOWN]` active | T1 | Risk Manager | Arms crossed, leaning back. Monitor shows countdown. |
| Signal detected | T2 | Strategy → Ensemble | Strategy stands, points at screen, turns to Ensemble. Ensemble leans in. |
| `[ENSEMBLE]` pass | T2 | Ensemble → Executor | Ensemble nods, turns to Executor. Executor sits up, hands on keyboard. |
| `[ENSEMBLE SKIP]` | T2 | Ensemble | Shakes head, waves dismissively. Strategy sits back down. |
| `[ENTRY]` position opened | T2 | Executor, Pos Monitor, Jonas | Executor types fast then leans back. Pos Monitor screen lights up. Jonas looks up. |
| `[TAPE]` / `[OB]` check | T2 | Tape Reader | Leans close to monitor, traces data with finger. |
| Position closed (profit) | T2 | Executor, Pos Monitor | Executor pumps fist (subtle). Pos Monitor nods. Nearby agents glance over. |
| Position closed (loss) | T2 | Executor, Risk Manager | Executor shakes head. Risk Manager checks monitors intently. |
| 3+ win streak | T3 | Executor + nearest agent | High-five! Both stand, walk to each other, clap hands. |
| 5+ win streak | T3 | ALL | Team celebration. Jonas claps. Fist pumps around the room. 5s celebration. |
| Big loss (> $2) | T3 | Executor, Risk Manager | Executor slams desk. Risk Manager walks to Executor's desk for review. |
| 3 consecutive losses | T3 | Risk Manager, Jonas | Risk Manager "stop" gesture. Jonas walks over for huddle. All agents tense. |
| Drawdown > 10% | T3 | ALL | Tension mode. Head-in-hands. Jonas pacing. Risk Manager standing, arms crossed. |
| New balance ATH | T3 | ALL | Big celebration. Jonas raises arms. Clapping, high-fives, pointing at main display. |

### 3.3 Social Events (Preserved)

All existing social events kept with same intervals:
- **Coffee breaks**: Every 2 min — random agent to break room
- **Facility visits**: Every 45s — gym, cafeteria, rec room
- **1-on-1 meetings**: Every 30 min — Jonas + agent in conference room
- **Team meetings**: Every 1 hr — all agents in conference room
- **Team events**: Every 5 min — lunch, happy hour, jacuzzi
- **Sleep mode**: 11pm-6am — characters sleep at desks

### 3.4 Status Indicators (Replacing Plumbobs)

Sims plumbobs replaced with realistic indicators:
- **Monitor glow**: Each desk monitor reflects agent status — green (active), amber (waiting), red (alert), blue (scanning).
- **Desk LED strip**: Subtle LED under desk edge, changes color with agent state.
- **Floating label**: Clean CSS2D label above each character — name, role, current status text (replaces emoji).

---

## 4. Environment

### 4.1 Setting: Salesforce Tower, High Floor

The office is located at the Salesforce Tower in San Francisco. The panorama through the glass walls shows the view FROM a high floor looking out over:
- **North**: Golden Gate Bridge, Marin Headlands
- **East**: Bay Bridge, Oakland hills, East Bay
- **South**: SoMa rooftops, 101 freeway
- **West**: Downtown SF buildings below (we're at the top)

### 4.2 Panorama Upgrade

**Current**: Procedural canvas 2048×768 with flat building silhouettes.

**Upgraded**:
- **HDRI environment map** (equirectangular, 4096×2048) used ONLY as `scene.environment` for PBR material reflections on glass/metal surfaces. This is NOT the visual backdrop — it provides indirect lighting and reflections.
- **Procedural panorama** (the visual backdrop) remains rendered on the existing sky dome mesh, upgraded with: detailed building silhouettes with window grids, recognizable SF landmarks (Golden Gate Bridge, Transamerica Pyramid, Bay Bridge), atmospheric fog/haze layers. The HDRI and procedural panorama are complementary — HDRI for reflections, panorama for what you see through the glass.
- Time-of-day system preserved — same sky-dome approach with higher fidelity textures.
- Bay water: animated normal-mapped plane with subtle wave movement and building reflections.

### 4.3 Room Structure (Preserved)

- **Dimensions**: 12×10×4 (ROOM_W × ROOM_D × ROOM_H) — unchanged
- **Glass walls**: 4 sides with mullions — upgraded to MeshPhysicalMaterial with transmission 0.95, IOR 1.5, clearcoat (real glass refraction)
- **Stairwell**: 2×2 opening at (-5.5, 4.2) with safety railings — unchanged
- **Break room**: Back-left corner — unchanged
- **Conference room**: Back-right corner — unchanged
- **Lower floors**: B1 (y=-3.5) and B2 (y=-7.0) with gym, cafeteria, rec room, bar, bedrooms, jacuzzi — unchanged

---

## 5. Rendering Pipeline

### 5.1 Renderer Settings

| Setting | Current | Upgraded |
|---------|---------|----------|
| Shadow map | 1024×1024 | 2048×2048 |
| Shadow type | PCFSoft | PCFSoft (same) |
| Pixel ratio | 1.0 | `Math.min(devicePixelRatio, 2)` (retina) |
| Tone mapping | ACESFilmic @ 1.1 | ACESFilmic @ 1.0 (more natural) |
| FPS target | ~30 (skip frames) | ~30 (same budget) |

### 5.2 Post-Processing Stack (EffectComposer)

1. **RenderPass** — base scene (existing)
2. **SSAOPass** (NEW) — screen-space ambient occlusion at half resolution. Soft shadow in crevices (under desks, wall-floor joints, between limbs). **Quality toggle**: off by default on integrated GPU, on for discrete GPU. Auto-detect via frame time measurement — if FPS drops below 25 for 3+ seconds, disable SSAO automatically.
3. **UnrealBloomPass** — tuned from 0.15 → 0.08 (subtler for realism)
4. **SMAAPass** — anti-aliasing (existing)
5. **ShaderPass - Color Grading** (NEW) — cinematic color grade: warm highlights, cool shadows, subtle vignette. "Hedge fund promo video" aesthetic.

### 5.3 Material Upgrades

| Surface | Current | Upgraded |
|---------|---------|----------|
| Floor | Flat #6a6560 | Normal-mapped polished concrete (procedural noise texture) |
| Glass walls | MeshPhysical, opacity 0.04 | MeshPhysical, transmission 0.95, IOR 1.5, clearcoat. **Perf fallback**: if transmission kills FPS below 30, revert to current opacity-based approach. |
| Desk tops | MeshPhysical, clearcoat | Same + normal map for wood/leather grain |
| Monitors | Flat emissive | Emissive screen + bezel reflection (env map) |
| Ceiling | Flat dark | Acoustic panel texture (subtle grid normal map) |

### 5.4 Lighting (Preserved Structure)

Same 7-light setup with upgraded shadow resolution. Ceiling LEDs and spots still dim during sleep hours. No additional lights needed — the GLTF models' PBR materials will respond better to existing lights.

---

## 6. Asset Pipeline

### 6.1 Asset Directory

```
Phmex-S/
├── assets/
│   ├── characters/
│   │   ├── jonas.glb          (~2MB, custom face)
│   │   ├── scanner.glb        (~1.5MB)
│   │   ├── risk_manager.glb   (~1.5MB)
│   │   ├── ensemble.glb       (~1.5MB)
│   │   ├── executor.glb       (~1.5MB)
│   │   ├── strategy.glb       (~1.5MB)
│   │   ├── tape_reader.glb    (~1.5MB)
│   │   ├── ws_feed.glb        (~1.5MB)
│   │   └── pos_monitor.glb    (~1.5MB)
│   ├── animations/
│   │   ├── idle-seated.glb
│   │   ├── typing.glb
│   │   ├── walking.glb
│   │   ├── standing-up.glb
│   │   ├── sitting-down.glb
│   │   ├── celebrating.glb
│   │   ├── head-shake.glb
│   │   ├── pointing.glb
│   │   ├── phone-talk.glb
│   │   ├── high-five.glb
│   │   ├── desk-slam.glb
│   │   └── arms-crossed.glb
│   ├── furniture/
│   │   ├── desk.glb           (~200KB)
│   │   ├── chair.glb          (~150KB)
│   │   ├── monitor.glb        (~100KB)
│   │   └── lamp.glb           (~50KB)
│   └── environment/
│       └── sf_bay_hdri.hdr    (~2-4MB)
├── trading_desk.py            (upgraded)
└── ...
```

**Total estimated size**: ~15-20MB

### 6.2 Loading Strategy

- `THREE.GLTFLoader` (imported from `three/addons/loaders/GLTFLoader.js`) loads all assets on page startup. Note: if GLB files use Draco compression, also import `DRACOLoader` from `three/addons/loaders/DRACOLoader.js`. Prefer non-Draco GLBs from Mixamo to avoid this dependency.
- Loading progress bar displayed until all assets ready.
- Browser caches assets after first load — subsequent visits load in <1s.
- Fallback: if any character GLTF fails to load, fall back to a simplified procedural character (capsule body, sphere head — minimal but functional with the animation system). For furniture/environment failures, use colored box placeholders.
- Python HTTP server in `trading_desk.py` serves assets from `assets/` directory alongside the HTML page.

### 6.3 HTTP Static File Serving

The current `do_GET` handler only serves `/`, `/api/data`, and `/jonas_avatar.jpg`. Add a static file route for assets:

- **Route**: `/assets/<path>` — maps to `assets/` directory on disk.
- **Path traversal protection**: Reject any path containing `..` or absolute paths. Resolve and verify the final path is within the `assets/` directory.
- **MIME types**: `.glb` → `model/gltf-binary`, `.hdr` → `application/octet-stream`, `.jpg/.png` → `image/jpeg` / `image/png`.
- **Cache headers**: `Cache-Control: public, max-age=86400` (24hr browser cache).
- **404 fallback**: Return 404 for any non-matching path.

### 6.4 Performance Optimizations

- **LOD**: Characters outside camera frustum skip animation updates.
- **SSAO at half resolution**: Render AO at 50% then upscale.
- **Shadow casting**: Main directional light only (same as current).
- **Animation mixer**: Only active clips consume CPU — idle characters use single looping clip.
- **Geometry instancing**: Shared desk/chair/monitor models instanced across 9 positions.

---

## 7. HUD & Overlay (Preserved)

Same HUD layout, same data sources, same update rates:
- **Bottom status bar** (72px): Balance, PnL, Win Rate, Drawdown, Positions, Trades, Cycle, Kelly $, Confidence
- **Right comms panel**: Event feed (last 30 events), Fira Code monospace
- **Left intel panel**: Apex system stats (ensemble, CVD, Hurst, Kelly, funding)
- **Speech bubbles**: Same trigger system, same styling. **Note**: All dialogue trees must be rewritten to reference the new agent names and roles (Ensemble instead of Claude, Executor instead of Trend, Strategy instead of Range, WS Feed instead of Therapist, Position Monitor is new). Content should reflect each agent's actual bot subsystem role.

---

## 8. Data Pipeline (Unchanged)

- Reads `trading_state.json` for trade history, peak balance
- Reads `logs/bot.log` (last 150-200 lines) for events
- Same regex parsing (`_parse_log_events`)
- Same `/api/data` endpoint polled every 1s by frontend
- Zero exchange API calls, zero bot imports
- Separate process on port 8060
