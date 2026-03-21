# Trading Desk Visual Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Sims-style 3D trading floor dashboard (`trading_desk.py`) to COD-quality realistic visuals using GLTF models, while preserving the scene structure, event system, and data pipeline.

**Architecture:** The dashboard is a standalone Python HTTP server that serves an inline HTML page with THREE.js. The upgrade replaces procedural character/furniture geometry with GLTF models loaded via GLTFLoader, upgrades materials to PBR, adds SSAO + color grading post-processing, and maps bot events to Mixamo motion-capture animations. Zero bot imports, zero API calls — reads `trading_state.json` + `logs/bot.log` only.

**Tech Stack:** Python 3 (HTTP server), THREE.js r160+ (via CDN), GLTF/GLB models (Mixamo + Sketchfab), HDRI environment maps.

**Spec:** `docs/superpowers/specs/2026-03-20-trading-desk-visual-overhaul-design.md`

**CRITICAL CONSTRAINT:** This is a dashboard — it must NEVER import bot modules or make exchange API calls. See `memory/feedback_dashboard_isolation.md`.

**NOTE ON TESTING:** This is a visual/3D project rendered in a browser. There are no unit tests. Each task is verified by running the dashboard (`python trading_desk.py`) and visually confirming the changes in the browser at `http://127.0.0.1:8060`. The current file is 7159 lines with the HTML/JS inlined as `HTML_PAGE` string constant.

**NOTE ON ASSETS:** Mixamo character models and animations must be downloaded manually from [mixamo.com](https://www.mixamo.com) (free Adobe account required). The plan includes placeholder fallbacks so the dashboard runs even before assets are downloaded. Sketchfab CC0 furniture models must also be downloaded manually. The HDRI can be downloaded from [polyhaven.com](https://polyhaven.com).

---

## File Structure

```
Phmex-S/
├── trading_desk.py              # MODIFY — the main dashboard (7159 lines)
│   ├── Python backend (lines 1-260) — HTTP server, log parsing, API
│   │   └── Add /assets/* static file route with path traversal protection
│   └── HTML_PAGE string (lines 261-7110) — THREE.js scene
│       ├── Imports — add GLTFLoader, SSAOPass, RGBELoader, ShaderPass
│       ├── Asset loading system — GLTFLoader pipeline + progress bar
│       ├── Character system — replace procedural geometry with GLTF models
│       ├── Animation system — replace sine-wave math with AnimationMixer
│       ├── Furniture — replace procedural desks/chairs with GLTF models
│       ├── Materials — upgrade floor, glass, ceiling, monitors
│       ├── Environment — upgrade panorama, add HDRI env map
│       ├── Post-processing — add SSAO, color grading, tune bloom
│       ├── Event animations — 3-tier system with new clip triggers
│       ├── Status indicators — replace plumbobs with monitor glow + LED + labels
│       ├── Agent roster — rename characters, update positions, add Position Monitor
│       └── Dialogue trees — rewrite for new agent names/roles
├── assets/                      # CREATE — asset directory
│   ├── characters/              # 9 × .glb files from Mixamo
│   ├── animations/              # 12 × .glb animation clips from Mixamo
│   ├── furniture/               # desk.glb, chair.glb, monitor.glb, lamp.glb
│   └── environment/             # sf_bay_hdri.hdr from Poly Haven
└── docs/superpowers/specs/      # EXISTS — design spec
```

**Important:** `trading_desk.py` is a single 7159-line file. The HTML/JS is an inline Python string (`HTML_PAGE`). All THREE.js code lives inside this string. Changes are made by editing the JavaScript within this string, NOT by creating separate JS files.

---

## Task 1: Asset Directory + HTTP Static File Serving

**Purpose:** Create the asset directory structure and update the Python HTTP server to serve static files from `assets/`. This unblocks all subsequent tasks that load GLTF/HDRI assets.

**Files:**
- Create: `assets/characters/.gitkeep`, `assets/animations/.gitkeep`, `assets/furniture/.gitkeep`, `assets/environment/.gitkeep`
- Modify: `trading_desk.py` lines 7112-7145 (Python `Handler.do_GET`)

- [ ] **Step 1: Create asset directory structure**

```bash
cd ~/Desktop/Phmex-S
mkdir -p assets/characters assets/animations assets/furniture assets/environment
touch assets/characters/.gitkeep assets/animations/.gitkeep assets/furniture/.gitkeep assets/environment/.gitkeep
```

- [ ] **Step 2: Add static file route to HTTP handler**

In `trading_desk.py`, add a MIME type map and asset serving route to the `Handler` class. Insert BEFORE the `else: 404` block (line 7143):

```python
import mimetypes
import posixpath

# Add at module level, after the existing imports (line 11):
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MIME_OVERRIDES = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".hdr": "application/octet-stream",
}
```

In `do_GET`, add this elif block before the final `else`:

```python
        elif self.path.startswith("/assets/"):
            # Static file serving with path traversal protection
            rel_path = self.path[len("/assets/"):]
            if ".." in rel_path or rel_path.startswith("/"):
                self.send_response(403)
                self.end_headers()
                return
            file_path = os.path.join(ASSET_DIR, rel_path)
            real_path = os.path.realpath(file_path)
            if not real_path.startswith(os.path.realpath(ASSET_DIR)):
                self.send_response(403)
                self.end_headers()
                return
            if not os.path.isfile(real_path):
                self.send_response(404)
                self.end_headers()
                return
            ext = os.path.splitext(real_path)[1].lower()
            content_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(real_path)[0] or "application/octet-stream"
            try:
                with open(real_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(500)
                self.end_headers()
```

- [ ] **Step 3: Verify static file serving works**

```bash
# Create a test file
echo '{"test": true}' > assets/test.json
# Start the server
cd ~/Desktop/Phmex-S
python trading_desk.py &
sleep 2
# Test asset route
curl -s http://127.0.0.1:8060/assets/test.json
# Expected: {"test": true}
# Test path traversal protection
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8060/assets/../.env
# Expected: 403
# Cleanup
kill %1
rm assets/test.json
```

- [ ] **Step 4: Commit**

```bash
git add assets/ trading_desk.py
git commit -m "feat(dashboard): add asset directory and static file serving for GLTF models"
```

---

## Task 2: Agent Roster Rename + Position Monitor

**Purpose:** Update the 8 existing agent names/positions to match the new bot subsystem mapping and add the 9th agent (Position Monitor). This is a text-replacement task across the HTML_PAGE string.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (agent definitions, desk positions, dialogue, labels)

- [ ] **Step 1: Rename agents in deskPositions object**

Find the `deskPositions` object (around line 4727-4736) and update:

| Old Name | New Name | Position (keep/change) |
|----------|----------|----------------------|
| `claude` | `ensemble` | (0, 0, 0.5) — keep |
| `scanner` | `scanner` | (-2.2, 0, -1.5) — keep |
| `risk` | `risk` | (2.2, 0, -1.5) — keep |
| `tape` | `tape` | (-2.2, 0, 2.5) — keep |
| `jonas` | `jonas` | (2.2, 0, 2.5) — keep |
| `trend` | `executor` | (-4.0, 0, 0.5) — keep |
| `range` | `strategy` | (4.0, 0, 0.5) — keep |
| `therapist` | `ws_feed` | (4.5, 0, 4.2) — keep |
| (new) | `pos_monitor` | (0, 0, 2.5) — ADD |

- [ ] **Step 2: Update all agent name references**

Search the HTML_PAGE string for every occurrence of `claude`, `trend`, `range`, `therapist` used as agent identifiers and replace with `ensemble`, `executor`, `strategy`, `ws_feed`. Be careful to only replace agent references, not other uses of these words. Key locations:
- Character creation functions (search for `createCharacter`)
- Agent clothing/appearance definitions
- Emoji label mappings
- Speech bubble positioning
- Animation trigger targets
- Social event participant lists and dialogue arrays (around lines 549-584)
- Walk system globals: rename `claudeTarget`/`claudeWalking`/`claudeWalkStart`/`claudeWalkFrom`/`claudeWalkTo` (around lines 482-486) to generic names like `agentWalkState` map, since the walk system needs to support multiple agents walking simultaneously for Task 7

- [ ] **Step 3: Add Position Monitor agent**

Add `pos_monitor` to:
- `deskPositions` object with position `{x: 0, y: 0, z: 2.5}`
- Character creation with appearance: watchful, alert, 2 monitors
- Agent label/emoji mapping
- Social event participant lists

- [ ] **Step 4: Update display names and roles**

Update the name labels and role descriptions shown above each character:
- Ensemble: "ENSEMBLE — Confidence Gate"
- Executor: "EXECUTOR — Order Placement"
- Strategy: "STRATEGY — Signal Generation"
- WS Feed: "WS FEED — Connectivity"
- Position Monitor: "POS MONITOR — Exit Logic"

- [ ] **Step 5: Verify in browser**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: 9 characters visible, correct names, Position Monitor at center
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): rename agents to match bot subsystems, add Position Monitor"
```

---

## Task 3: GLTFLoader Import + Asset Loading System

**Purpose:** Add the GLTFLoader import, create a loading progress bar, and build the asset loading pipeline that loads characters, animations, furniture, and HDRI on startup.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (imports section + new loading system)

- [ ] **Step 1: Add GLTFLoader and RGBELoader imports**

Find the THREE.js import section (around line 460-475) and add:

```javascript
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
```

- [ ] **Step 2: Create loading progress bar HTML/CSS**

Add a loading overlay div before the `<script>` tag:

```html
<div id="loading-overlay" style="
  position: fixed; inset: 0; background: #0a0e17; z-index: 9999;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  font-family: 'Fira Code', monospace; color: #ccc;
">
  <div style="font-size: 18px; margin-bottom: 20px; color: #4fc3f7;">PHMEX-S TRADING DESK</div>
  <div style="width: 300px; height: 4px; background: #1a2a3a; border-radius: 2px; overflow: hidden;">
    <div id="loading-bar" style="width: 0%; height: 100%; background: #4fc3f7; transition: width 0.3s;"></div>
  </div>
  <div id="loading-text" style="margin-top: 10px; font-size: 11px; color: #666;">Loading assets...</div>
</div>
```

- [ ] **Step 3: Create asset manifest and loading function**

Add after the scene setup, before character creation:

```javascript
const ASSET_MANIFEST = {
  characters: [
    'jonas', 'scanner', 'risk_manager', 'ensemble', 'executor',
    'strategy', 'tape_reader', 'ws_feed', 'pos_monitor'
  ],
  animations: [
    'idle-seated', 'typing', 'walking', 'standing-up', 'sitting-down',
    'celebrating', 'head-shake', 'pointing', 'phone-talk',
    'high-five', 'desk-slam', 'arms-crossed'
  ],
  furniture: ['desk', 'chair', 'monitor', 'lamp'],
  environment: ['sf_bay_hdri']
};

const loadedAssets = { characters: {}, animations: {}, furniture: {}, environment: {} };
const gltfLoader = new GLTFLoader();
const rgbeLoader = new RGBELoader();

async function loadAllAssets() {
  const totalItems = ASSET_MANIFEST.characters.length +
    ASSET_MANIFEST.animations.length +
    ASSET_MANIFEST.furniture.length +
    ASSET_MANIFEST.environment.length;
  let loaded = 0;

  function updateProgress(name) {
    loaded++;
    const pct = (loaded / totalItems * 100).toFixed(0);
    document.getElementById('loading-bar').style.width = pct + '%';
    document.getElementById('loading-text').textContent = 'Loading ' + name + '...';
  }

  // Load characters (parallel within category)
  await Promise.allSettled(
    ASSET_MANIFEST.characters.map(name =>
      gltfLoader.loadAsync('/assets/characters/' + name + '.glb')
        .then(gltf => { loadedAssets.characters[name] = gltf; updateProgress(name); })
        .catch(e => { console.warn('Failed to load character:', name, e); loadedAssets.characters[name] = null; updateProgress(name); })
    )
  );

  // Load animations (parallel)
  await Promise.allSettled(
    ASSET_MANIFEST.animations.map(name =>
      gltfLoader.loadAsync('/assets/animations/' + name + '.glb')
        .then(gltf => { loadedAssets.animations[name] = gltf.animations[0]; updateProgress(name); })
        .catch(e => { console.warn('Failed to load animation:', name, e); loadedAssets.animations[name] = null; updateProgress(name); })
    )
  );

  // Load furniture (parallel)
  await Promise.allSettled(
    ASSET_MANIFEST.furniture.map(name =>
      gltfLoader.loadAsync('/assets/furniture/' + name + '.glb')
        .then(gltf => { loadedAssets.furniture[name] = gltf.scene; updateProgress(name); })
        .catch(e => { console.warn('Failed to load furniture:', name, e); loadedAssets.furniture[name] = null; updateProgress(name); })
    )
  );

  // Load HDRI environment
  try {
    const hdr = await rgbeLoader.loadAsync('/assets/environment/sf_bay_hdri.hdr');
    hdr.mapping = THREE.EquirectangularReflectionMapping;
    scene.environment = hdr; // PBR reflections only
    loadedAssets.environment.hdri = hdr;
  } catch (e) {
    console.warn('Failed to load HDRI:', e);
  }
  updateProgress('environment');

  // Hide loading overlay
  document.getElementById('loading-overlay').style.display = 'none';
}
```

- [ ] **Step 4: Call loadAllAssets on startup**

Replace the existing init block (around line 7104-7107):

```javascript
// ── INIT ──
loadAllAssets().then(() => {
  console.log('Assets loaded, initializing scene');
  buildScene(); // wrap existing character/furniture creation in this function
  fetchData();
  setInterval(fetchData, 3000);
  animate();
}).catch(err => {
  console.error('Asset loading failed, running with fallbacks:', err);
  document.getElementById('loading-overlay').style.display = 'none';
  buildScene();
  fetchData();
  setInterval(fetchData, 3000);
  animate();
});
```

- [ ] **Step 5: Verify loading system works (with missing assets)**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Expected: Loading bar appears briefly, then falls through to fallbacks
# Dashboard should render with current procedural characters (graceful degradation)
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): add GLTFLoader pipeline with progress bar and fallbacks"
```

---

## Task 4: Download and Place Mixamo Assets

**Purpose:** Download character models and animation clips from Mixamo, furniture from Sketchfab, and HDRI from Poly Haven. Place them in the `assets/` directory.

**Files:**
- Create: All `.glb` and `.hdr` files in `assets/`

- [ ] **Step 1: Download Mixamo character models**

Go to [mixamo.com](https://www.mixamo.com) (free Adobe account):

1. For each of the 9 agents, pick a character that matches the spec appearance:
   - **Jonas**: Male, casual (hoodie). Select a base model, download as FBX → convert to GLB (or use a GLB exporter).
   - **Scanner**: Male, professional, crew-cut
   - **Risk Manager**: Male, formal, glasses
   - **Ensemble**: Male or female, analytical look
   - **Executor**: Male, sharp/focused
   - **Strategy**: Male or female, thoughtful/casual
   - **Tape Reader**: Male or female, headphones
   - **WS Feed**: Male or female, tech/IT look
   - **Position Monitor**: Male or female, watchful/alert

2. Download each as **FBX Binary (.fbx)** with **T-Pose**, then convert to GLB using:
   ```bash
   # Install fbx2gltf if needed: npm install -g fbx2gltf
   fbx2gltf -i character.fbx -o assets/characters/agent_name.glb
   ```

3. **Alternative**: Use [readyplayer.me](https://readyplayer.me) for characters (downloads directly as GLB with Mixamo-compatible skeleton).

- [ ] **Step 2: Download Mixamo animation clips**

On Mixamo, with ANY character selected:
1. Search for and download each animation:
   - `idle-seated` → search "Sitting Idle"
   - `typing` → search "Typing"
   - `walking` → search "Walking"
   - `standing-up` → search "Standing Up"
   - `sitting-down` → search "Sitting Down"
   - `celebrating` → search "Victory" or "Celebration"
   - `head-shake` → search "Disappointed" or "Head Shake"
   - `pointing` → search "Pointing"
   - `phone-talk` → search "Talking On Phone"
   - `high-five` → search "Clapping" (single character)
   - `desk-slam` → search "Angry" or use "Fist Pump" inverted
   - `arms-crossed` → search "Arms Crossed Idle"

2. Download each as **FBX Binary, Without Skin** (animation only), convert to GLB:
   ```bash
   for f in assets/animations/*.fbx; do
     fbx2gltf -i "$f" -o "${f%.fbx}.glb"
     rm "$f"
   done
   ```

- [ ] **Step 3: Download furniture models**

From [sketchfab.com](https://sketchfab.com) (filter by CC0/Public Domain, download as GLTF):
- Search "office desk modern" → download → save as `assets/furniture/desk.glb`
- Search "office chair modern" → download → save as `assets/furniture/chair.glb`
- Search "computer monitor" → download → save as `assets/furniture/monitor.glb`
- Search "desk lamp modern" → download → save as `assets/furniture/lamp.glb`

Scale each model appropriately (desk ~0.78m wide, chair ~0.5m, monitor ~0.44m).

- [ ] **Step 4: Download HDRI environment map**

From [polyhaven.com](https://polyhaven.com):
- Search for "san francisco" or "city skyline" or "bay"
- Download as `.hdr` at 2K or 4K resolution
- Save as `assets/environment/sf_bay_hdri.hdr`

- [ ] **Step 5: Verify all assets load**

```bash
cd ~/Desktop/Phmex-S
ls -la assets/characters/*.glb  # Should show 9 files
ls -la assets/animations/*.glb  # Should show 12 files
ls -la assets/furniture/*.glb   # Should show 4 files
ls -la assets/environment/*.hdr # Should show 1 file
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Expected: Loading bar fills, assets load, scene renders with GLTF models
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add assets/
git commit -m "feat(dashboard): add Mixamo characters, animations, furniture, and HDRI assets"
```

---

## Task 5: Replace Procedural Characters with GLTF Models

**Purpose:** Replace the procedural sphere/cylinder/capsule character geometry with loaded GLTF models. Keep the procedural geometry as a fallback for missing assets.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (character creation function)

- [ ] **Step 1: Refactor character creation to support GLTF**

Find the `createCharacter` function (search for it in the HTML_PAGE). Wrap the existing procedural geometry in an `else` block and add GLTF loading as the primary path:

```javascript
function createCharacterFromGLTF(name, gltfData, config) {
  const model = gltfData.scene.clone();

  // Scale to match scene units (~1.35 for normal, ~1.5 for Jonas)
  const scale = config.scale || 0.01; // Mixamo models are typically in cm
  model.scale.set(scale, scale, scale);

  // Enable shadows
  model.traverse((child) => {
    if (child.isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
      // Upgrade materials to PBR if not already
      if (child.material) {
        child.material.envMapIntensity = 0.5;
      }
    }
  });

  // Create animation mixer
  const mixer = new THREE.AnimationMixer(model);
  model.userData.mixer = mixer;
  model.userData.clips = {};
  model.userData.currentAction = null;
  model.userData.agentName = name;

  return model;
}
```

- [ ] **Step 2: Update character placement loop**

Modify the loop that creates and places characters at desks. For each agent:

```javascript
function buildCharacters() {
  Object.entries(deskPositions).forEach(([name, pos]) => {
    let character;
    const gltfData = loadedAssets.characters[name];

    if (gltfData) {
      // Use GLTF model
      character = createCharacterFromGLTF(name, gltfData, {
        scale: name === 'jonas' ? 0.012 : 0.01 // Jonas slightly taller
      });
    } else {
      // Fallback to procedural
      character = createProceduralCharacter(name);
    }

    character.position.set(pos.x, 0, pos.z);
    scene.add(character);
    characters[name] = character;
  });
}
```

- [ ] **Step 3: Preserve existing procedural character code as fallback**

Rename the current `createCharacter` to `createProceduralCharacter`. Keep all existing procedural geometry code intact — it serves as the fallback when GLTF files are missing.

- [ ] **Step 4: Verify GLTF characters render at correct positions**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: GLTF characters appear at correct desk positions
# If no GLTF files yet, procedural fallback characters should appear
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): replace procedural characters with GLTF models (procedural fallback)"
```

---

## Task 6: Animation System (AnimationMixer)

**Purpose:** Replace the sine-wave arm/leg rotation animation system with THREE.AnimationMixer using Mixamo clips. Map animation clips to characters and implement crossfade transitions.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (animation loop + character animation functions)

- [ ] **Step 1: Load animation clips into each character's mixer**

After characters are created, attach animation clips:

```javascript
function attachAnimations(character) {
  const mixer = character.userData.mixer;
  if (!mixer) return;

  const clips = {};
  Object.entries(loadedAssets.animations).forEach(([name, clip]) => {
    if (clip) {
      const action = mixer.clipAction(clip);
      clips[name] = action;
      // Configure loop behavior
      if (['idle-seated', 'typing', 'walking', 'phone-talk', 'arms-crossed'].includes(name)) {
        action.loop = THREE.LoopRepeat;
      } else {
        action.loop = THREE.LoopOnce;
        action.clampWhenFinished = true;
      }
    }
  });
  character.userData.clips = clips;

  // Start with idle-seated
  if (clips['idle-seated']) {
    clips['idle-seated'].play();
    character.userData.currentAction = clips['idle-seated'];
  }
}
```

- [ ] **Step 2: Create animation transition function**

```javascript
function playAnimation(character, animName, fadeTime = 0.3) {
  const clips = character.userData.clips;
  const newAction = clips[animName];
  if (!newAction) return;

  const current = character.userData.currentAction;
  if (current === newAction) return; // already playing

  if (current) {
    current.fadeOut(fadeTime);
  }

  newAction.reset();
  newAction.fadeIn(fadeTime);
  newAction.play();
  character.userData.currentAction = newAction;

  // For one-shot animations, return to idle when done
  if (newAction.loop === THREE.LoopOnce) {
    const onFinished = () => {
      mixer.removeEventListener('finished', onFinished);
      playAnimation(character, character.userData.isSeated ? 'idle-seated' : 'typing');
    };
    character.userData.mixer.addEventListener('finished', onFinished);
  }
}
```

- [ ] **Step 3: Update the animate() loop to use AnimationMixer**

Find the `animate()` function. Replace the per-character sine-wave animation code with mixer updates:

```javascript
// In the animate() function, replace the manual arm/leg rotation code with:
const delta = clock.getDelta();
Object.values(characters).forEach(character => {
  if (character.userData.mixer) {
    character.userData.mixer.update(delta);
  }
});
```

Keep the existing walk interpolation system (`position.lerpVectors`) — it handles movement between locations. The AnimationMixer handles the body animation while the character moves.

- [ ] **Step 4: Preserve fallback animation for procedural characters**

If a character is procedural (no mixer), keep the existing sine-wave animation code running for it. Gate with:

```javascript
if (character.userData.mixer) {
  character.userData.mixer.update(delta);
} else {
  // existing procedural animation code (sine-wave arms, legs, head bob)
  animateProceduralCharacter(character, t);
}
```

- [ ] **Step 5: Verify animations play**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: Characters play idle-seated animation at desks
# Walking characters should blend to walking clip
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): replace sine-wave animations with Mixamo AnimationMixer clips"
```

---

## Task 7: Event-Driven Animation Triggers (3 Tiers)

**Purpose:** Map bot events from the log feed to character animation triggers using the 3-tier system (Professional → Active Trading → Wolf of Wall Street).

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (event handling + animation triggers)

- [ ] **Step 1: Create event-to-animation dispatcher**

Add after the animation system:

```javascript
// Track streaks for T3 triggers
let winStreak = 0;
let lossStreak = 0;

function handleBotEvent(event) {
  const type = event.type;

  // ── TIER 1: Professional ──
  if (type === 'scanner') {
    playAnimation(characters.scanner, 'phone-talk');
    setTimeout(() => playAnimation(characters.scanner, 'typing'), 4000);
  }
  if (type === 'ws') {
    playAnimation(characters.ws_feed, 'typing');
  }
  if (type === 'cooldown') {
    playAnimation(characters.risk, 'arms-crossed');
  }

  // ── TIER 2: Active Trading ──
  if (type === 'ensemble') {
    playAnimation(characters.strategy, 'standing-up');
    playAnimation(characters.strategy, 'pointing');
    setTimeout(() => {
      playAnimation(characters.ensemble, 'pointing');
      playAnimation(characters.executor, 'typing');
    }, 1000);
    setTimeout(() => playAnimation(characters.strategy, 'sitting-down'), 3000);
  }
  if (type === 'ensemble_skip') {
    playAnimation(characters.ensemble, 'head-shake');
  }
  if (type === 'entry') {
    playAnimation(characters.executor, 'typing');
    setTimeout(() => playAnimation(characters.executor, 'idle-seated'), 2000);
  }
  if (type === 'tape' || type === 'orderbook') {
    playAnimation(characters.tape, 'pointing');
    setTimeout(() => playAnimation(characters.tape, 'typing'), 2000);
  }

  // ── Close events (profit/loss) ──
  if (type === 'close') {
    if (event.pnl > 0) {
      // Win
      winStreak++;
      lossStreak = 0;
      playAnimation(characters.executor, 'celebrating');

      // T3: Win streak
      if (winStreak >= 5) {
        // Team celebration
        Object.values(characters).forEach(c => playAnimation(c, 'celebrating'));
        setTimeout(() => {
          Object.values(characters).forEach(c => playAnimation(c, 'idle-seated'));
        }, 5000);
      } else if (winStreak >= 3) {
        // High-five: executor + nearest agent walk to midpoint
        triggerHighFive(characters.executor, characters.ensemble);
      }
    } else {
      // Loss
      lossStreak++;
      winStreak = 0;
      playAnimation(characters.executor, 'head-shake');
      playAnimation(characters.risk, 'pointing'); // reviewing

      // T3: Big loss
      if (Math.abs(event.pnl) > 2) {
        playAnimation(characters.executor, 'desk-slam');
        triggerWalkTo(characters.risk, characters.executor); // risk walks to executor
      }

      // T3: 3 consecutive losses
      if (lossStreak >= 3) {
        playAnimation(characters.risk, 'arms-crossed');
        triggerWalkTo(characters.jonas, characters.risk); // Jonas walks to risk for huddle
        Object.values(characters).forEach(c => {
          if (c !== characters.jonas && c !== characters.risk) {
            playAnimation(c, 'arms-crossed');
          }
        });
      }
    }
  }
}
```

- [ ] **Step 2: Add high-five and walk-to helper functions**

```javascript
// Per-agent walk state (replaces old single-agent claudeWalking/claudeTarget globals)
// Each entry: { walking: bool, from: Vector3, to: Vector3, start: number, duration: number, onArrive: Function }
const agentWalkState = {};

function startWalk(character, targetPos, onArrive) {
  const name = character.userData.agentName;
  agentWalkState[name] = {
    walking: true,
    from: character.position.clone(),
    to: targetPos,
    start: performance.now() / 1000,
    duration: 3.5, // WALK_DURATION from existing code
    onArrive: onArrive || null,
    deskPos: deskPositions[name] // save desk position for return
  };
  playAnimation(character, 'walking');
  // Face the target
  character.rotation.y = Math.atan2(
    targetPos.x - character.position.x,
    targetPos.z - character.position.z
  );
}

function walkBackToDesk(character) {
  const name = character.userData.agentName;
  const deskPos = agentWalkState[name]?.deskPos || deskPositions[name];
  startWalk(character, new THREE.Vector3(deskPos.x, 0, deskPos.z), () => {
    playAnimation(character, 'idle-seated');
  });
}

// In animate(), add walk interpolation for all agents:
// Object.entries(agentWalkState).forEach(([name, state]) => {
//   if (!state.walking) return;
//   const elapsed = performance.now() / 1000 - state.start;
//   const progress = Math.min(elapsed / state.duration, 1);
//   // Quad ease-in-out (match existing easing)
//   const eased = progress < 0.5 ? 2*progress*progress : 1 - Math.pow(-2*progress+2,2)/2;
//   characters[name].position.lerpVectors(state.from, state.to, eased);
//   if (progress >= 1) {
//     state.walking = false;
//     if (state.onArrive) state.onArrive();
//   }
// });

function triggerHighFive(char1, char2) {
  const midpoint = new THREE.Vector3().lerpVectors(char1.position, char2.position, 0.5);

  startWalk(char1, midpoint.clone(), () => {
    playAnimation(char1, 'high-five');
    setTimeout(() => walkBackToDesk(char1), 2500);
  });
  startWalk(char2, midpoint.clone(), () => {
    playAnimation(char2, 'high-five');
    setTimeout(() => walkBackToDesk(char2), 2500);
  });
}

function triggerWalkTo(walker, target) {
  const targetPos = target.position.clone();
  targetPos.x += 0.5; // stand next to, not on top of
  startWalk(walker, targetPos, () => {
    playAnimation(walker, 'arms-crossed');
    setTimeout(() => walkBackToDesk(walker), 8000);
  });
}
```

- [ ] **Step 3: Add drawdown and ATH triggers**

```javascript
function handleStatsUpdate(stats) {
  // T3: Drawdown > 10%
  if (stats.drawdown > 10) {
    Object.values(characters).forEach(c => playAnimation(c, 'arms-crossed'));
    // Jonas paces — use walking animation at his desk area
    playAnimation(characters.jonas, 'walking');
  }

  // T3: New ATH — check if balance > peak
  if (stats.balance > (lastPeakBalance || 0)) {
    lastPeakBalance = stats.balance;
    Object.values(characters).forEach(c => playAnimation(c, 'celebrating'));
    setTimeout(() => {
      Object.values(characters).forEach(c => playAnimation(c, 'idle-seated'));
    }, 5000);
  }
}
```

- [ ] **Step 4: Wire events to the dispatcher**

In the `fetchData` callback where events are processed, call `handleBotEvent` for new events:

```javascript
// In the fetch callback, after processing events:
newEvents.forEach(event => handleBotEvent(event));
if (latestStats) handleStatsUpdate(latestStats);
```

- [ ] **Step 5: Verify event animations trigger**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Watch the dashboard while the bot runs — characters should react to events
# If bot is not running, check the log for recent events
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): add 3-tier event-driven animation system"
```

---

## Task 8: Replace Procedural Furniture with GLTF Models

**Purpose:** Replace the procedural desk/chair/monitor/lamp geometry with loaded GLTF models. Use geometry instancing for performance.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (furniture creation code)

- [ ] **Step 1: Create GLTF furniture placement function**

```javascript
function placeFurniture(name, pos, config) {
  const gltfScene = loadedAssets.furniture[name];
  if (!gltfScene) return createProceduralFurniture(name, pos, config); // fallback

  const model = gltfScene.clone();
  model.position.set(pos.x, pos.y || 0, pos.z);
  if (config.rotation) model.rotation.y = config.rotation;
  if (config.scale) model.scale.setScalar(config.scale);

  model.traverse((child) => {
    if (child.isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });

  scene.add(model);
  return model;
}
```

- [ ] **Step 2: Replace desk/chair/monitor/lamp creation loops**

Find the existing furniture creation code (search for desk, chair, monitor, lamp creation). Replace each with calls to `placeFurniture`:

```javascript
// For each agent desk position:
Object.entries(deskPositions).forEach(([name, pos]) => {
  const deskScale = name === 'ensemble' ? 1.2 : 1.0;
  placeFurniture('desk', pos, { scale: deskScale });
  placeFurniture('chair', { x: pos.x, y: 0, z: pos.z + 0.4 }, { scale: 1.0 });

  // Monitor counts per spec: Jonas=6, Ensemble=3, everyone else=2
  const monitorCount = name === 'jonas' ? 6 : (name === 'ensemble' ? 3 : 2);
  for (let i = 0; i < monitorCount; i++) {
    const offset = (i - (monitorCount - 1) / 2) * 0.25;
    placeFurniture('monitor', { x: pos.x + offset, y: 0.78, z: pos.z - 0.15 }, { scale: 0.8 });
  }

  placeFurniture('lamp', { x: pos.x - 0.35, y: 0.78, z: pos.z + 0.15 }, { scale: 0.5 });
});
```

- [ ] **Step 3: Keep procedural furniture as fallback**

Rename existing furniture creation functions to `createProceduralDesk`, `createProceduralChair`, etc. Call them when GLTF is missing.

- [ ] **Step 4: Verify furniture renders**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: Desks, chairs, monitors, lamps render at correct positions
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): replace procedural furniture with GLTF models"
```

---

## Task 9: Material Upgrades (Floor, Glass, Ceiling, Monitors)

**Purpose:** Upgrade the flat-color materials to PBR with normal maps, proper glass transmission, and environment-mapped reflections.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (material definitions)

- [ ] **Step 1: Upgrade floor material**

Find the floor material (search for `#6a6560` or `floor`). Replace with normal-mapped polished concrete:

```javascript
// Create procedural concrete normal map
const concreteCanvas = document.createElement('canvas');
concreteCanvas.width = 512; concreteCanvas.height = 512;
const cCtx = concreteCanvas.getContext('2d');
// Generate noise texture for concrete grain
for (let x = 0; x < 512; x++) {
  for (let y = 0; y < 512; y++) {
    const v = 128 + (Math.random() - 0.5) * 30;
    cCtx.fillStyle = `rgb(${v},${v},${v})`;
    cCtx.fillRect(x, y, 1, 1);
  }
}
const concreteNormal = new THREE.CanvasTexture(concreteCanvas);
concreteNormal.wrapS = concreteNormal.wrapT = THREE.RepeatWrapping;
concreteNormal.repeat.set(4, 4);

const floorMaterial = new THREE.MeshStandardMaterial({
  color: 0x6a6560,
  roughness: 0.45,
  metalness: 0.05,
  normalMap: concreteNormal,
  normalScale: new THREE.Vector2(0.3, 0.3),
});
```

- [ ] **Step 2: Upgrade glass wall material**

Find the glass wall material (search for `opacity: 0.04` or `glass`). Replace with physically-based glass:

```javascript
const glassMaterial = new THREE.MeshPhysicalMaterial({
  color: 0x88aacc,
  transmission: 0.95,
  ior: 1.5,
  clearcoat: 1.0,
  clearcoatRoughness: 0.05,
  roughness: 0.0,
  metalness: 0.0,
  side: THREE.DoubleSide,
  transparent: true,
});

// Performance fallback — check frame time after 5 seconds
let glassPerformanceChecked = false;
setTimeout(() => {
  if (!glassPerformanceChecked) {
    glassPerformanceChecked = true;
    // If FPS < 30, swap to simple glass
    if (renderer.info.render.frame / (performance.now() / 1000) < 25) {
      console.warn('Glass transmission too expensive, falling back to opacity');
      glassMaterial.transmission = 0;
      glassMaterial.opacity = 0.04;
      glassMaterial.transparent = true;
      glassMaterial.needsUpdate = true;
    }
  }
}, 5000);
```

- [ ] **Step 3: Upgrade ceiling and monitor materials**

```javascript
// Ceiling — acoustic panel texture
const ceilingMaterial = new THREE.MeshStandardMaterial({
  color: 0x2e2e35,
  roughness: 0.9,
  metalness: 0.0,
  // Add subtle grid normal map for acoustic panels
  normalMap: createGridNormalMap(256, 8), // helper to create grid texture
  normalScale: new THREE.Vector2(0.2, 0.2),
});

// Monitor bezels — environment-mapped reflection
const monitorBezelMaterial = new THREE.MeshStandardMaterial({
  color: 0x111111,
  roughness: 0.15,
  metalness: 0.9,
  envMapIntensity: 0.8,
});
```

- [ ] **Step 4: Apply materials to existing geometry**

Find each mesh creation and swap in the new materials. The geometry stays the same — only materials change.

- [ ] **Step 5: Verify materials look correct**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: Floor has subtle grain, glass walls show refraction, monitors reflect
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): upgrade materials to PBR (concrete floor, glass, ceiling)"
```

---

## Task 10: Environment Upgrades (Panorama + HDRI + Water)

**Purpose:** Upgrade the procedural SF panorama with detailed landmarks, add HDRI environment map for reflections, and animate bay water.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (panorama generation + sky dome + water)

- [ ] **Step 1: Upgrade procedural panorama renderer**

Find `createSFPanorama` function. Enhance building generation with:
- Recognizable Salesforce Tower, Transamerica Pyramid, Golden Gate Bridge shapes
- Window grid patterns on buildings
- Atmospheric fog/haze gradient near horizon
- Higher resolution canvas (4096×2048 instead of 2048×768)

The view is FROM the Salesforce Tower looking out, so:
- North face: Golden Gate Bridge + Marin hills
- East face: Bay Bridge + Oakland
- South face: SoMa buildings below
- West face: Downtown SF buildings (shorter, we're at the top)

- [ ] **Step 2: Set HDRI as scene environment**

The HDRI was already loaded in Task 3. Verify it's applied:

```javascript
// Already in loadAllAssets():
scene.environment = hdr; // This provides PBR reflections on all materials
// Do NOT set scene.background = hdr — the procedural panorama is the visual backdrop
```

- [ ] **Step 3: Add animated bay water plane**

```javascript
// Create water plane below the main floor, visible through glass
const waterGeom = new THREE.PlaneGeometry(200, 200, 32, 32);
const waterMat = new THREE.MeshStandardMaterial({
  color: 0x2a5a7a,
  roughness: 0.3,
  metalness: 0.4,
  transparent: true,
  opacity: 0.8,
});
const waterMesh = new THREE.Mesh(waterGeom, waterMat);
waterMesh.rotation.x = -Math.PI / 2;
waterMesh.position.y = -2;
scene.add(waterMesh);

// In animate(), add subtle wave animation:
const positions = waterMesh.geometry.attributes.position;
for (let i = 0; i < positions.count; i++) {
  const x = positions.getX(i);
  const z = positions.getZ(i);
  positions.setY(i, Math.sin(t * 0.5 + x * 0.1) * 0.1 + Math.cos(t * 0.3 + z * 0.15) * 0.08);
}
positions.needsUpdate = true;
```

- [ ] **Step 4: Verify environment**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: SF landmarks visible, glass reflects HDRI, water animates
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): upgrade SF panorama with landmarks, HDRI reflections, animated water"
```

---

## Task 11: Post-Processing Pipeline (SSAO + Color Grading)

**Purpose:** Add SSAOPass for ambient occlusion, tune bloom down, add cinematic color grading with vignette.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (post-processing setup)

- [ ] **Step 1: Import SSAOPass**

Add to imports:

```javascript
import { SSAOPass } from 'three/addons/postprocessing/SSAOPass.js';
// ShaderPass import was already added in Task 3 Step 1
```

- [ ] **Step 2: Add SSAOPass to composer**

Find the EffectComposer setup (search for `EffectComposer` or `composer`). Add SSAO after RenderPass, before bloom:

```javascript
// Half resolution for performance — pass half dimensions to constructor
const ssaoPass = new SSAOPass(scene, camera, Math.floor(window.innerWidth / 2), Math.floor(window.innerHeight / 2));
ssaoPass.kernelRadius = 8;
ssaoPass.minDistance = 0.005;
ssaoPass.maxDistance = 0.1;
ssaoPass.output = SSAOPass.OUTPUT.Default;
composer.addPass(ssaoPass);

// Auto-disable if FPS drops
let ssaoEnabled = true;
let lowFpsFrames = 0;
```

- [ ] **Step 3: Tune bloom down**

Find the bloom pass (search for `UnrealBloomPass` or `bloomPass`). Change strength:

```javascript
bloomPass.strength = 0.08; // was 0.15 — subtler for realism
```

- [ ] **Step 4: Add color grading shader pass**

```javascript
const colorGradeShader = {
  uniforms: {
    tDiffuse: { value: null },
    vignetteStrength: { value: 0.3 },
    warmth: { value: 0.05 },
  },
  vertexShader: `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: `
    uniform sampler2D tDiffuse;
    uniform float vignetteStrength;
    uniform float warmth;
    varying vec2 vUv;
    void main() {
      vec4 color = texture2D(tDiffuse, vUv);
      // Warm highlights, cool shadows
      color.r += warmth * color.r;
      color.b -= warmth * 0.5 * (1.0 - color.b);
      // Vignette
      vec2 center = vUv - 0.5;
      float dist = length(center);
      color.rgb *= 1.0 - vignetteStrength * dist * dist;
      gl_FragColor = color;
    }
  `
};
const colorGradePass = new ShaderPass(colorGradeShader);
composer.addPass(colorGradePass);
```

- [ ] **Step 5: Add SSAO auto-disable for performance**

In the `animate()` function, add FPS monitoring:

```javascript
// After rendering, check performance
if (ssaoEnabled) {
  const fps = 1 / delta;
  if (fps < 25) {
    lowFpsFrames++;
    if (lowFpsFrames > 90) { // ~3 seconds at 30fps
      console.warn('SSAO disabled for performance');
      ssaoPass.enabled = false;
      ssaoEnabled = false;
    }
  } else {
    lowFpsFrames = 0;
  }
}
```

- [ ] **Step 6: Update renderer settings**

```javascript
renderer.shadowMap.mapSize.width = 2048;  // was 1024
renderer.shadowMap.mapSize.height = 2048; // was 1024
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // was 1.0
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0; // was 1.1
```

- [ ] **Step 7: Verify post-processing**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: Soft shadows under desks (SSAO), subtle vignette, warm color grade
# Check FPS in browser dev tools (should be 30+)
kill %1
```

- [ ] **Step 8: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): add SSAO, color grading, tune bloom, upgrade renderer settings"
```

---

## Task 12: Status Indicators (Replace Plumbobs)

**Purpose:** Replace the Sims plumbob dots with realistic status indicators: monitor glow colors, desk LED strips, and clean floating name/role labels.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (plumbob code + label code)

- [ ] **Step 1: Remove plumbob creation and animation**

Search for `plumbob` in the HTML_PAGE. Remove:
- Plumbob CSS2D element creation
- Plumbob pulsing animation
- Plumbob color-change logic

- [ ] **Step 2: Add desk LED strip**

For each desk, add a thin emissive strip along the front edge:

```javascript
function createDeskLED(pos, name) {
  const ledGeom = new THREE.BoxGeometry(0.7, 0.01, 0.02);
  const ledMat = new THREE.MeshStandardMaterial({
    color: 0x00ff88,
    emissive: 0x00ff88,
    emissiveIntensity: 0.5,
  });
  const led = new THREE.Mesh(ledGeom, ledMat);
  led.position.set(pos.x, 0.76, pos.z - 0.2); // front edge of desk
  scene.add(led);
  return led;
}

// Store LED references for status updates
const deskLEDs = {};
Object.entries(deskPositions).forEach(([name, pos]) => {
  deskLEDs[name] = createDeskLED(pos, name);
});
```

- [ ] **Step 3: Add status color update function**

```javascript
function updateAgentStatus(name, status) {
  const led = deskLEDs[name];
  if (!led) return;

  const colors = {
    active: 0x00ff88,    // green
    waiting: 0xffaa00,   // amber
    alert: 0xff4444,     // red
    scanning: 0x4488ff,  // blue
    idle: 0x333333,      // dim
  };

  const color = colors[status] || colors.idle;
  led.material.color.setHex(color);
  led.material.emissive.setHex(color);
}
```

- [ ] **Step 4: Update floating labels**

Replace emoji labels with clean name/role text:

```javascript
function createAgentLabel(name, role) {
  const div = document.createElement('div');
  div.style.cssText = `
    background: rgba(10, 14, 23, 0.85);
    padding: 4px 8px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 10px;
    color: #ccc;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.1);
    pointer-events: none;
  `;
  div.innerHTML = `<div style="color: #4fc3f7; font-weight: bold;">${name.toUpperCase()}</div>
    <div style="color: #666; font-size: 8px;">${role}</div>`;

  const label = new CSS2DObject(div);
  label.position.set(0, 1.6, 0); // above character head
  return label;
}
```

- [ ] **Step 5: Add monitor glow status indicator**

Each desk has monitor canvas textures (stored in `monitorCanvases` around line 478). Add a colored border/glow that reflects agent status:

```javascript
function updateMonitorGlow(name, status) {
  const canvas = monitorCanvases[name];
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const colors = {
    active: '#00ff88',
    waiting: '#ffaa00',
    alert: '#ff4444',
    scanning: '#4488ff',
    idle: '#333333',
  };
  const color = colors[status] || colors.idle;

  // Draw colored border on monitor canvas
  ctx.strokeStyle = color;
  ctx.lineWidth = 4;
  ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4);
  canvas.texture.needsUpdate = true; // flag THREE.js to re-upload
}
```

- [ ] **Step 6: Wire status updates to bot events**

In `handleBotEvent`:

```javascript
// Update LED + monitor glow status based on events
if (type === 'scanner') {
  updateAgentStatus('scanner', 'scanning');
  updateMonitorGlow('scanner', 'scanning');
}
if (type === 'entry') {
  updateAgentStatus('executor', 'active');
  updateMonitorGlow('executor', 'active');
}
if (type === 'cooldown') {
  updateAgentStatus('risk', 'alert');
  updateMonitorGlow('risk', 'alert');
}
if (type === 'close') {
  const status = event.pnl > 0 ? 'active' : 'alert';
  updateAgentStatus('executor', status);
  updateMonitorGlow('executor', status);
  setTimeout(() => {
    updateAgentStatus('executor', 'waiting');
    updateMonitorGlow('executor', 'waiting');
  }, 3000);
}
```

- [ ] **Step 7: Verify indicators**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Verify: No plumbobs, desk LEDs visible, clean name/role labels above characters
kill %1
```

- [ ] **Step 8: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): replace plumbobs with desk LEDs, monitor glow, and clean labels"
```

---

## Task 13: Dialogue Tree Rewrite

**Purpose:** Update all dialogue/speech bubble content to reference the new agent names and their actual bot subsystem roles.

**Files:**
- Modify: `trading_desk.py` — HTML_PAGE string (dialogue arrays/objects)

- [ ] **Step 1: Find all dialogue content**

Search the HTML_PAGE for dialogue arrays, speech bubble text, agent conversation scripts. Key search terms: `dialogue`, `speech`, `bubble`, `chat`, `convo`, `meeting`.

- [ ] **Step 2: Rewrite agent dialogues**

Replace all references to old agent names with new ones and update dialogue to reflect actual bot roles:

| Old Agent | New Agent | Example Dialogue |
|-----------|-----------|-----------------|
| Claude | Ensemble | "6 layers confirmed, confidence at 5/6. Green light." |
| Trend | Executor | "Order placed. Limit entry, postOnly. Waiting for fill." |
| Range | Strategy | "Keltner squeeze releasing. Momentum continuation setup." |
| Therapist | WS Feed | "All 7 feeds connected. Data fresh, latency 45ms." |
| (new) | Position Monitor | "Watching BTC long. ROI at 8.2%, early_exit threshold approaching." |

- [ ] **Step 3: Add Position Monitor to dialogue rotations**

Include `pos_monitor` in meeting dialogues, coffee break small talk, and team event conversations.

- [ ] **Step 4: Verify dialogues display correctly**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 2
open http://127.0.0.1:8060
# Wait for a meeting or coffee break event — verify speech bubbles show correct names
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): rewrite dialogue trees for new agent names and roles"
```

---

## Task 14: Final Integration + Performance Verification

**Purpose:** Final integration pass — verify all systems work together, check performance budget, clean up any loose ends.

**Files:**
- Modify: `trading_desk.py` — any final fixes

- [ ] **Step 1: Full integration test**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
python trading_desk.py &
sleep 3
open http://127.0.0.1:8060
```

Verify each system:
- [ ] 9 characters visible at correct positions
- [ ] GLTF models render (or procedural fallback works)
- [ ] Idle-seated animation plays for all characters
- [ ] Walking animation plays when characters move
- [ ] Event animations trigger correctly (watch for entries/exits in log)
- [ ] Social events fire (coffee breaks, meetings)
- [ ] Desk LEDs change color with agent status
- [ ] Clean name/role labels above characters (no plumbobs)
- [ ] SF panorama shows landmarks
- [ ] Glass walls have proper transparency/refraction
- [ ] Floor has concrete grain
- [ ] Post-processing visible (subtle vignette, soft shadows)
- [ ] HUD stats bar shows correct data
- [ ] Comms panel shows events with correct agent names
- [ ] Intel panel shows Apex data
- [ ] FPS is 30+ (check browser dev tools → Performance tab)

- [ ] **Step 2: Performance check**

Open browser dev tools → Performance tab:
- Target: 30+ FPS sustained
- If below 25 FPS: SSAO should auto-disable (check console for warning)
- If still below 25 FPS: check glass transmission fallback triggered
- Memory: should stabilize, no leaks (check heap in Performance tab)

- [ ] **Step 3: Fix any issues found**

Address any bugs, visual glitches, or performance issues discovered during integration testing.

- [ ] **Step 4: Final commit**

```bash
git add trading_desk.py
git commit -m "feat(dashboard): trading desk visual overhaul complete — COD-quality upgrade"
```

---

## Execution Notes

- **Always `rm -rf __pycache__`** before restarting the dashboard after code changes (known stale bytecode issue).
- **The bot must NOT be affected** — the dashboard is a separate process. If the bot is running, leave it alone.
- **Asset downloads are manual** — Task 4 requires human interaction with Mixamo/Sketchfab/Poly Haven websites.
- **The file is 7159 lines** — use search/grep to find the right sections. Line numbers may shift as edits are made. Search for unique strings near the edit points.
- **Test incrementally** — after each task, verify in the browser before moving on.
