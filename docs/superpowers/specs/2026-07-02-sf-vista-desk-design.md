# Trading Desk — SF/Bay Area Vista + Performance Overhaul

**Date:** 2026-07-02
**Status:** Approved by Jonas (verbal, session 2026-07-02)
**Scope:** `trading_desk.py` (port 8060 visualization) only. Cosmetic + performance. Zero bot code, zero data-path changes, all truthful-monitor invariants untouched.

## Problem

The desk's "city outside the windows" is four 2D canvas paintings (2048×768) wrapped on cylinder segments at the window radius (`trading_desk.py:2671-2703`). It has no depth or parallax — reads as wallpaper. Performance is poor: full panorama repaints on hour changes, UnrealBloom + SMAA post-processing every frame, PCFSoft shadows, and per-frame closure allocations force a frame-skip hack capping the scene at ~30fps on the M3 Air's integrated GPU.

## Goal

The view from the penthouse reads as San Francisco and the Bay Area seen from Salesforce Tower (415 Mission St, ~800 ft), built from real city data, with living ambience — at a real 60fps target.

## Design

### 1. Real city geometry (replaces painted murals)

- **Bake script** `scripts/desk_city_bake.py` (run once now, kept for reproducibility): fetches OpenStreetMap building footprints + heights (Overpass API) for downtown SF, waterfront, and surrounding geography, centered on 415 Mission St. Output: compact `assets/environment/sf_city.json` (quantized coords, per-building height + rough category). Served by the existing `/assets/` route so the main file doesn't balloon.
- **Client rendering:** extrude footprints into merged `BufferGeometry` in 3 distance rings — near FiDi (detailed), mid (simplified), far (blocks). One draw call per ring. No shadows on the city. `FogExp2` provides depth. Vertex colors carry facade tone + baked window-light pattern.
- **Hand-detailed landmarks** (procedural three.js, not OSM boxes): Transamerica Pyramid, Bay Bridge (west+east spans, towers, light strings), Coit Tower, Ferry Building clock tower, Sutro Tower, Golden Gate Bridge (distant), Alcatraz, Oakland port cranes, East Bay hills + Marin ridgelines (low-poly terrain bands).
- **Viewpoint/scale:** penthouse floor maps to ~800 ft; city scaled so real bearings hold (Bay Bridge ENE, Transamerica NNW, Twin Peaks/Sutro WSW, Oakland E across the bay).
- The old `createSFPanorama` mural system and its per-hour 4-canvas repaints are removed.

### 2. Living ambience (instanced / shader, all cheap)

- **Bay water:** single plane, animated shimmer (scrolling normal/spec in a small shader or offset map). 
- **Boats:** a few instanced container ships/ferries on fixed slow routes.
- **Traffic:** instanced light-dot streams along the Bay Bridge path (headlights/taillights, night-weighted) + faint dots on 2-3 major streets.
- **Sky life:** 2-3 plane sprites on SFO/OAK approach paths with blinking strobes; drifting cloud sprites; small bird flocks by day.
- **Karl the Fog:** large soft alpha planes drifting in from the west; density higher at night/early morning.
- **Day/night:** stays synced to real clock. Sky dome gradient + window-light intensity cross-fade via shader uniforms per hour — no geometry rebuilds, no canvas repaints.

### 3. Performance pass

- **Drop EffectComposer** (RenderPass + UnrealBloom + SMAA + OutputPass) — render directly with native MSAA (`antialias:true` already set). Screen/LED glow replaced by emissive materials + cheap additive sprites. Bloom left behind a single re-enable flag at half resolution if the look is missed.
- **Shadows interior-only:** shadow camera already tight (±8); ensure no city/ambience meshes cast/receive.
- **Fix per-frame allocations:** precompute character/agent arrays instead of `Object.entries(...).forEach` closures in `animate()`.
- **Remove the every-other-frame skip** as default; keep it as an automatic fallback when measured fps < ~45 (perf chip already samples fps/draw calls every 5 s).
- Monitor CanvasTexture redraw cadence unchanged (3 s poll) — that is data-truth territory, not touched.

## Invariants preserved

- Desk stays a standalone read-only process: reads `trading_state.json` + `logs/bot.log` only, zero bot imports.
- No fabricated data anywhere; city/ambience is decorative and carries no bot-data meaning.
- Interior scene, characters, story behaviors, monitors, HUD: unchanged (except glow implementation).

## Verification

- Server-side tests (`tests/test_trading_desk_v2.py`) still pass; add none-to-minimal tests for the `/assets/environment/sf_city.json` route + bake-script output schema.
- Drive `http://127.0.0.1:8060/` in Chrome: read perf chip fps/draw-calls/triangles before vs after; screenshot the vista N/E/S/W and day vs night.
- Success: recognizable SF vista with parallax, ambience animating, steady ~60fps (≥45 floor) on the M3 Air.

## Non-goals

- No interior restyle, no character rework, no websocket migration, no change to poll cadence or API shape.
