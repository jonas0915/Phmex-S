# SF Vista + Performance Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the trading desk's window view read as San Francisco/Bay Area from Salesforce Tower, at real interactive framerates, by deleting the occluding 2D mural layer, upgrading the existing (currently invisible) 3D city, adding living ambience, and removing the post-processing chain.

**Architecture:** `trading_desk.py` is a standalone read-only HTTP server (port 8060) with the whole three.js scene embedded in the `HTML_PAGE` string. A complete procedural 3D SF city already exists at `// ── 3D CITY BUILDINGS AROUND SALESFORCE TOWER ──` but is hidden behind opaque canvas-mural cylinders at the window radius. We remove the murals, fix the render pipeline, then improve what's revealed.

**Tech Stack:** three.js r160 (CDN importmap), vanilla JS, Python stdlib server. No new dependencies.

## Global Constraints

- Desk stays read-only: reads `trading_state.json` + `logs/bot.log` only; zero bot imports; no fabricated data (spec `docs/superpowers/specs/2026-07-02-sf-vista-desk-design.md`).
- Interior scene, characters, monitors, story behaviors, HUD, `/api/data` shape: unchanged.
- Target hardware: M3 Air 8GB integrated GPU. Smoothness beats fidelity (existing in-file rule at the glassMat comment).
- This is NOT the trading bot — no pre-restart-audit needed; the desk process can be restarted freely.
- All edits are inside the `HTML_PAGE` string in `trading_desk.py` unless stated. After every edit: `python3 -c "import trading_desk"` must succeed and `pytest tests/test_trading_desk_v2.py` must pass.

## Ground truth from recon (2026-07-02)

- Mural layer: `createSFPanorama` (`trading_desk.py:983` → the `return new THREE.CanvasTexture(c);}` immediately before `// ── SKY DOME ──` at ~2381). Four opaque BackSide cylinder meshes at `PENTHOUSE_RAD - 0.02` (in the `wallQuadrants.forEach` block ~2690-2704). Photo override IIFE `loadPhotoPanorama` (~2739-2771) loads `assets/environment/sf_panorama.jpg` — a 24,449×3,162 px, 7MB image cloned into 4 GPU textures (main freeze cause at load; file already renamed to `.disabled`).
- Existing 3D city: `// ── 3D CITY BUILDINGS AROUND SALESFORCE TOWER ──` (~3741) through `// ── HELPER FUNCTIONS ──` (~5984). Has GROUND_Y=−50 world, SF hills, Transamerica, Coit, Ferry Building, Golden Gate, Bay Bridge, Alcatraz, Angel Island, Embarcadero Center, Marin, Oakland hills, Golden Gate Park, InstancedMesh fill system. Never visible from inside.
- Perf chip lies under EffectComposer: `renderer.info` auto-resets per render() call, so with composer the chip reports only the final fullscreen-quad pass (`calls=1 tris=0k`). Composer passes at ~8701-8716; `composer.render()` at ~9587.
- Frame-skip hack `if(frameCount % 2 !== 0) return;` at ~9039; slow bucket `frameCount % 8` at ~9044; per-frame `Object.entries(charGroups)` closures at ~9063.

---

### Task 1: Delete the mural layer (reveal the 3D city)

**Files:**
- Modify: `trading_desk.py` (HTML_PAGE string)
- Delete: `assets/environment/sf_panorama.jpg.disabled`
- Test: `tests/test_trading_desk_v2.py` (existing) + browser screenshot

**Interfaces:**
- Produces: glass walls now transparent to the 3D city. `panPlaneMeshes` global and `createSFPanorama` no longer exist — later tasks must not reference them.

- [ ] **Step 1:** Delete `function createSFPanorama(facing, hour) {...}` — from the comment line `// ── SF PANORAMA TEXTURE — time-synced, photorealistic 2K resolution ──` (after the `skinMat` line) down to (not including) `// ── SKY DOME — environment sphere visible when zoomed out ──`.
- [ ] **Step 2:** Delete the `panTex` declaration block (`const panTex = { north: createSFPanorama(...), ... };`) and, inside `wallQuadrants.forEach`, the "Panorama behind glass" block (`const panGeo = ... panPlaneMeshes[wq.facing] = panMesh;`). Keep the glass pane, mullions, ring frames. Delete the `const panPlaneMeshes = {};` declaration (~891) and every remaining reference (grep `panPlaneMeshes`, `isPanorama`).
- [ ] **Step 3:** Delete the entire `(function loadPhotoPanorama() {...})();` IIFE including its `// ── PHOTO PANORAMA` comment headers.
- [ ] **Step 4:** In `updateTimeOfDay()` (~8719), delete the "Regenerate panoramas" `['north','south','east','west'].forEach(...)` block. Keep sky dome regeneration and lighting adjustments.
- [ ] **Step 5:** Glass material check — `glassMat` opacity 0.06 stays; verify no other opaque shell exists at the window radius (grep `PENTHOUSE_RAD - 0.0`).
- [ ] **Step 6:** `git rm` the disabled photo; `rm` is fine since git tracks the original name — remove both tracked file and on-disk `.disabled`.
- [ ] **Step 7:** Run: `python3 -c "import trading_desk"` → no output. `python3 -m pytest tests/test_trading_desk_v2.py -q` → all pass.
- [ ] **Step 8:** Restart desk server; screenshot from default camera in Chrome (foreground tab). Expected: 3D city + sky visible through glass, no gray mural.
- [ ] **Step 9:** Commit: `feat(desk): remove 2D mural layer + 77MP photo override; reveal 3D city`

### Task 2: Fix render pipeline + perf instrumentation

**Files:**
- Modify: `trading_desk.py`

**Interfaces:**
- Consumes: scene from Task 1.
- Produces: direct `renderer.render(scene, camera)` path (no composer); truthful perf chip; `PERF_HALF_RATE` adaptive flag later tasks must respect for any per-frame work they add.

- [ ] **Step 1:** Remove composer: delete `EffectComposer/RenderPass/UnrealBloomPass/OutputPass/SMAAPass` imports, the `const composer = new EffectComposer(renderer);` block, the pass-adding block (~8701-8716), and the resize handler's composer/SSAO updates. Replace `composer.render();` with `renderer.render(scene, camera);`.
- [ ] **Step 2:** Emissive compensation: monitors and LED/status materials that relied on bloom get `emissiveIntensity` raised (monitor screen MeshBasicMaterial already self-lit; bump LED emissive from current value to ~2.0 — locate via `updateAgentLED` and desk LED strip materials).
- [ ] **Step 3:** Perf chip truth: set `renderer.info.autoReset = false;` after renderer creation and add `renderer.info.reset()` at the top of each rendered frame in `animate()` so calls/tris cover the full frame.
- [ ] **Step 4:** Frame pacing: remove `if(frameCount % 2 !== 0) return;`. Add adaptive fallback: keep `_fpsTick()` 5s sampling; if sampled fps < 24 for two consecutive samples, set `PERF_HALF_RATE = true` (re-enables the %2 skip); if > 40, clear it. Keep the `slowTick` bucket but derive it from rendered frames.
- [ ] **Step 5:** Allocation fix: hoist `Object.entries(charGroups)` to a `charGroupList` array rebuilt only when characters are added (after GLTF loads), and iterate with a `for` loop in `animate()`.
- [ ] **Step 6:** `python3 -c "import trading_desk"`; pytest; restart; screenshot + perf chip reading with the tab foregrounded. Expected: real calls/tris now visible; fps ≥ 30 on battery.
- [ ] **Step 7:** Commit: `perf(desk): drop composer/bloom/SMAA, truthful renderer.info, adaptive frame pacing`

### Task 3: City quality pass — make it read as SF from Salesforce Tower

**Files:**
- Modify: `trading_desk.py` (3D city section ~3741-5984)

**Interfaces:**
- Consumes: visible city from Task 1, direct pipeline from Task 2.
- Produces: `CITY` config object (`const CITY = { groundY, unitsPerMeter }`) that Task 4 ambience uses for placement.

- [ ] **Step 1:** Screenshot audit from inside the penthouse toward N/E/S/W (camera via OrbitControls drag; capture 4 shots). List visual defects (scale, bearing, color, density, popping).
- [ ] **Step 2:** Bearing/height audit — compute real bearings/distances from 415 Mission St (37.7897, −122.3972) with this script, then compare against the landmark positions in code (scene: +x=east, −z=north):

```python
import math
L = {"transamerica": (37.7952, -122.4028), "coit": (37.8024, -122.4058),
     "ferry": (37.7955, -122.3937), "bb_west_anchor": (37.7867, -122.3872),
     "yerba_buena": (37.8100, -122.3580), "golden_gate": (37.8199, -122.4783),
     "alcatraz": (37.8267, -122.4230), "sutro": (37.7552, -122.4528),
     "oakland_dt": (37.8044, -122.2712), "twin_peaks": (37.7544, -122.4477)}
lat0, lon0 = 37.7897, -122.3972
for name, (lat, lon) in L.items():
    dn = (lat - lat0) * 111320
    de = (lon - lon0) * 111320 * math.cos(math.radians(lat0))
    brg = (math.degrees(math.atan2(de, dn)) + 360) % 360
    print(f"{name:15s} {math.hypot(de,dn)/1000:5.1f} km  bearing {brg:5.1f}°  scene(x={de:+.0f}m, z={-dn:+.0f}m)")
```

- [ ] **Step 3:** Fix worst-offender placements/scales found in Steps 1-2 (edit existing landmark builders in place; distance compression beyond ~2km is acceptable and expected — preserve bearings, compress radii).
- [ ] **Step 4:** Material/lighting pass on the city: night window-light density, fog color/density sync with `updateTimeOfDay`, bay water color day/night. No new textures larger than 512px.
- [ ] **Step 5:** Restart; 4-direction screenshots day + night (night via temporary `let currentHour = 22` override — add a `?hour=` URL debug param: `const HOUR_OVERRIDE = parseFloat(new URLSearchParams(location.search).get('hour'));` and use it in `getTimeOfDay()` when finite). Keep the param — it is verification infrastructure, marked debug-only in a comment.
- [ ] **Step 6:** Commit: `feat(desk): SF city bearing/scale/lighting quality pass + ?hour debug param`

**Decision gate:** if after this task the instanced fill still reads as fake boxes, execute optional Task 6 (OSM bake). Otherwise skip it (YAGNI).

### Task 4: Living ambience

**Files:**
- Modify: `trading_desk.py`

**Interfaces:**
- Consumes: `CITY` config from Task 3; `PERF_HALF_RATE`/`slowTick` from Task 2.
- Produces: `updateAmbience(t, dt)` called once per rendered frame from `animate()`.

- [ ] **Step 1:** Karl the Fog — 4-6 large `PlaneGeometry` sprites (256px radial-gradient canvas alpha texture, one shared texture), positioned west/northwest at hill height, drifting east ~2 units/min, opacity scaled by hour (0.6 night/morning, 0.15 midday). Billboard toward camera each slow tick.
- [ ] **Step 2:** Bay water shimmer — locate existing water plane in the city section; add gentle vertex-less shimmer by scrolling a small (128px) generated normal-ish map via `map.offset` per frame, or a 2-layer semi-transparent plane with opposing slow offsets. No shaders beyond built-in materials.
- [ ] **Step 3:** Boats — one `InstancedMesh` (hull box + cabin box merged, ≤60 tris) × 5 instances on straight routes across the bay (SF↔Oakland, SF↔Sausalito headings); per-slow-tick matrix updates; ~0.5 units/s.
- [ ] **Step 4:** Bridge + street traffic — two `InstancedMesh` point-quad sets (white headlights, red taillights), ~60 instances each, moving along the Bay Bridge deck path both directions; opacity 0 by day, 1 at night. 2-3 street paths downtown with dimmer dots.
- [ ] **Step 5:** Sky life — 2 plane sprites (triangle-ish, ≤20 tris) on descending approach paths with 1Hz blinking strobe (emissive toggle); 1-2 drifting cloud sprites reusing the fog texture at high altitude; skip birds if fps budget is tight (note in commit if skipped).
- [ ] **Step 6:** All ambience updates inside `updateAmbience(t, dt)`; matrix writes on `slowTick` only, except water offset (cheap, per frame).
- [ ] **Step 7:** Restart; verify each element visible in screenshots (day + `?hour=22` night); perf chip fps unchanged ±5 vs Task 2 reading.
- [ ] **Step 8:** Commit: `feat(desk): bay ambience — Karl the Fog, boats, bridge traffic, sky life`

### Task 5: Final verification + docs + memory

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-sf-vista-desk-design.md` (addendum), memory files

- [ ] **Step 1:** Full pytest run (whole `tests/` suite): expected all pass (291 baseline).
- [ ] **Step 2:** Browser drive: default view, zoom out, orbit 360°, day + night; confirm no console errors (`read_console_messages onlyErrors`); record perf chip fps/calls/tris; confirm monitors still show live truthful data and story events still fire.
- [ ] **Step 3:** Verify Jonas-facing polish: double-click reset still works; HUD unchanged.
- [ ] **Step 4:** Update spec with implementation addendum (mural discovery, photo root cause, OSM demoted to conditional); update project memory file + MEMORY.md index.
- [ ] **Step 5:** Commit: `docs(desk): SF vista implementation addendum + memory`

### Task 6 (CONDITIONAL — only if Task 3 gate fails): OSM footprint bake

**Files:**
- Create: `scripts/desk_city_bake.py`, `assets/environment/sf_city.json`
- Test: `tests/test_desk_city_asset.py`

- [ ] **Step 1:** Write failing test: asset exists, JSON parses, `buildings` array ≥ 500 entries, each `[cx_m, cz_m, w_m, d_m, h_m, rot_deg]`, Transamerica present (height 200-280m within 1km of center).
- [ ] **Step 2:** Bake script: Overpass query (mirrors: overpass-api.de, overpass.kumi.systems) bbox (37.775, −122.425, 37.808, −122.383), `building` ways with `height` or `building:levels` (levels×3.2m); oriented-bounding-box each footprint; drop h<15m beyond 800m from center; cap 2500 sorted by h·area; emit meters relative to 415 Mission.
- [ ] **Step 3:** Run bake (network); run test → pass.
- [ ] **Step 4:** Client: replace the procedural fill (keep hand-built landmarks) with one merged BufferGeometry per distance ring (<1km, <2.5km, rest) built from the JSON boxes; vertex colors for facade/night windows; apply the same radial compression as landmarks.
- [ ] **Step 5:** Restart, screenshot, pytest, commit: `feat(desk): OSM-accurate downtown fill`
