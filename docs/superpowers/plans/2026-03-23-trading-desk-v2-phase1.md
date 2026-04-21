# Trading Desk v2 Phase 1 — Building & Environment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the square building with a curved glass tower, upgrade the SF skyline with detailed varied buildings, fix the Golden Gate Bridge cutoff, improve bay water with reflections, and enhance hills/terrain.

**Architecture:** All changes are in the 3D scene section of trading_desk.py (lines 2302-4425). The file is a single Python file serving inline HTML/JS with Three.js. Each task modifies a specific line range with no overlap.

**Tech Stack:** Three.js 0.160.0, Python http.server, Canvas2D for procedural textures

**CRITICAL:** Dashboard must remain read-only — no API calls, no bot performance impact. Test by opening http://localhost:8060 after each change.

---

### Task 1: Curved Glass Tower (Replace Square Building)

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/trading_desk.py:2302-2520`

**Context:** Current tower is built with BoxGeometry (rectangular). Replace with CylinderGeometry for the main body, tapered toward the top like Salesforce Tower. Keep the floor slabs, glass material, and window lights but adapt to cylindrical shape.

- [ ] **Step 1: Replace main tower body with CylinderGeometry**

Replace the BoxGeometry tower body (lines 2311-2316) with:
```javascript
// Curved tower body — Salesforce-inspired tapered cylinder
const towerGeo = new THREE.CylinderGeometry(
    ROOM_W * 0.42,    // top radius (slightly narrower)
    ROOM_W * 0.48,    // bottom radius
    TOWER_H,           // height
    32,                // radial segments (smooth curve)
    1,                 // height segments
    true               // open-ended (we add caps separately)
);
```

- [ ] **Step 2: Update floor slabs for circular shape**

Replace BoxGeometry floor slabs (lines 2320-2326) with CircleGeometry or CylinderGeometry discs.

- [ ] **Step 3: Update glass walls to wrap around cylinder**

Replace flat panorama planes (lines 2180-2242) with curved planes that follow the cylinder surface. Use a partially-unwrapped cylinder for each wall section.

- [ ] **Step 4: Add architectural crown/top**

Replace boxy crown (lines 2398-2412) with a tapered cone or dome cap piece.

- [ ] **Step 5: Update window light placement for curved surface**

Adapt window lights (lines 2433-2536) to follow the cylinder surface using polar coordinates.

- [ ] **Step 6: Test — verify tower renders correctly**

Run: Kill and restart trading_desk.py, open http://localhost:8060
Expected: Curved glass tower visible, no rendering glitches

---

### Task 2: SF Skyline — Detailed Varied Buildings

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/trading_desk.py:3500-4410` (procedural building zones)
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/trading_desk.py:744-1897` (panorama texture)

**Context:** Current 3D buildings are gray/brown boxes. Need varied heights, glass textures, lit windows at night, and recognizable shapes. The panorama texture (2D backdrop) also needs upgrading.

- [ ] **Step 1: Improve 3D building variety**

For each building zone (FiDi, SoMa, Waterfront, East), add:
- Varied heights (20-60 units instead of uniform)
- Mix of BoxGeometry, CylinderGeometry (round towers), tapered shapes
- Glass material with slight blue tint and reflectivity
- Emissive window lights (small bright rectangles on faces)

- [ ] **Step 2: Add building detail — setbacks, crowns, antennas**

Top 20% of buildings get architectural details:
- Setbacks (narrower top sections)
- Antenna/spire on tallest buildings
- Rooftop lights (red aviation warning lights at night)

- [ ] **Step 3: Improve panorama texture buildings**

In createSFPanorama() (lines 744-1897), update drawBuilding():
- More glass reflection effect
- Varied window patterns (not uniform grid)
- Better color palette (blue-gray glass, not brown/gray)

- [ ] **Step 4: Add city lights at night**

Buildings emit window light after dusk. Use emissive materials or small point lights on building faces. Time-synced with existing day/night cycle.

- [ ] **Step 5: Test — verify skyline looks premium**

Expected: Varied, detailed skyline with glass towers, lit windows at night, recognizable SF feel

---

### Task 3: Full Golden Gate Bridge

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/trading_desk.py:4114-4330`

**Context:** Current bridge is cut off at edges. Need the full span visible — both towers, full deck from SF to Marin, proper suspension cables.

- [ ] **Step 1: Extend bridge deck to full length**

Increase deck geometry to span the full distance. Current deck is truncated — extend both ends to reach land on both sides.

- [ ] **Step 2: Add both main towers at correct positions**

Two iconic red towers (International Orange color #c0362c). Each tower: two vertical columns connected by horizontal braces at top and mid-height.

- [ ] **Step 3: Add proper suspension cables**

Main cables: catenary curve from tower to tower to anchorage. Suspender cables: vertical lines from main cable down to deck at regular intervals. Use TubeGeometry or line segments.

- [ ] **Step 4: Add approach roads on both sides**

SF side: approach ramp connecting to Presidio. Marin side: road connecting to Marin Headlands.

- [ ] **Step 5: Add bridge lighting**

Red aviation lights on tower tops. Deck lights along the roadway. Visible at night.

- [ ] **Step 6: Test — verify full bridge is visible**

Expected: Complete Golden Gate Bridge, both towers, full span, proper cables, not cut off

---

### Task 4: Bay Water Improvements

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/trading_desk.py:3267-3281`

**Context:** Current water is a flat MeshPhysicalMaterial plane. Need animated waves and city light reflections.

- [ ] **Step 1: Add vertex displacement for wave animation**

In the animation loop, displace water plane vertices using sine waves:
```javascript
// In animate()
const waterVerts = waterMesh.geometry.attributes.position;
const time = clock.getElapsedTime();
for (let i = 0; i < waterVerts.count; i++) {
    const x = waterVerts.getX(i);
    const z = waterVerts.getZ(i);
    waterVerts.setY(i, Math.sin(x * 0.3 + time * 0.5) * 0.15 + Math.cos(z * 0.2 + time * 0.3) * 0.1);
}
waterVerts.needsUpdate = true;
```

- [ ] **Step 2: Improve water material for reflections**

Update material properties: increase clearcoat, add envMap for sky reflection, adjust color based on time of day.

- [ ] **Step 3: Add fog layers over water**

Enhance existing fog layers (lines 4414-4424) with animated opacity based on time of day. Thicker at dawn/dusk (SF fog signature).

- [ ] **Step 4: Test — verify water animates and reflects**

Expected: Gentle wave animation, subtle reflections, fog at dawn/dusk

---

### Task 5: Hills & Terrain Improvements

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/trading_desk.py:3283-3378`

**Context:** Current hills are basic ConeGeometry. Need smoother, more realistic terrain.

- [ ] **Step 1: Replace cone hills with smooth terrain meshes**

Use SphereGeometry (half-sphere, flattened) instead of ConeGeometry for a more natural hill shape. Apply green/brown gradient material.

- [ ] **Step 2: Add vegetation color to hills**

Hills closer to camera get a green tint. Distant hills get blue-gray atmospheric haze.

- [ ] **Step 3: Improve ground plane**

Replace flat gray-brown ground with a textured surface:
- Street grid pattern near downtown
- Parks/green areas (Golden Gate Park, Dolores Park)
- Residential areas with lighter color

- [ ] **Step 4: Test — verify terrain looks natural**

Expected: Smooth rolling hills, green vegetation, SF's hilly character visible

---

## Testing

After all tasks complete:
1. Kill and restart trading_desk.py
2. Open http://localhost:8060
3. Verify: curved tower, detailed skyline, full GG bridge, animated water, smooth hills
4. Check day/night cycle still works (wait or manually adjust time)
5. Check performance — should maintain 30fps on MacBook
6. Verify dashboards still display data correctly (HUD, Intel, Agent Comms)
