# Vehicle Lab — procedural 3D vehicle studio

**Version 0.3.4 (2026-11-09)**. Browser-native modular vehicle editor built with Three.js, lil-gui, three alternative physics engines, optional GLB imports, Flask and SQLite. Project: https://github.com/sylwesterdigital/meta-vehicle-lab. Website: https://vehiclelab.xyz/.

This README deliberately contains the **About, Install, Roadmap, Ideas and LLM Handover** sections in a single allowed release file. The current watcher validates an exact 15-file manifest, so adding standalone documentation to a watcher release without first migrating its manifest schema would reject the ZIP. A separate optional documentation archive contains those sections as individual Markdown files.

## About / product scope

Vehicle Lab is a prototype for procedurally assembling visually plausible city cars, buses, municipal vehicles, heavy trucks, construction equipment, agricultural machinery and warehouse vehicles from parameterized hull modules and equipment. Parameters cover width/height/depth/scale/rotation/offset, body materials, wheels, axles, doors/windows, passenger slots, engines and driving physics. Modules can later be transferred into a shared 3D world as an independent blueprint generator. This is **not** an engineering-grade physics simulator.

## Features through v0.3.5

- Full-size Three.js canvas. Draggable, resizable, minimizable actions/tools/catalog/gallery/parameters/log windows. Right-side configuration and profile drawers, custom theme/typography and text/icon button modes.
- Circular uploaded/webcam profile picture, optional passwordless identity, bearer-secret JSON backup. Credentials must remain private. Public gallery is **opt-in**; private layouts remain owner-scoped.
- 40 presets, three hull modules plus equipment, procedural materials, number of doors/windows/seats, independent front/rear wheel radius/tyre width/rim style/outset/front and rear axle offsets, imported GLB visual body/occupants.
- Three independent driving solvers: Cannon-es, Rapier WASM and Ammo.js/Bullet raycast vehicles; no kinematic baseline. Each backend uses its own raycast-wheel physics. Orbit-follow camera, 60Hz benchmark, CSV.
- BUILD ↔ DRIVE preserves camera direction/zoom, with explicit camera reset. Rotation toggle highlights active state and persists. Preset/parameter edit history supports Undo/Redo (Cmd/Ctrl+Z, Shift+Z), searchable Cmd/Ctrl+/ shortcut dialog.
- Mobile-friendly Save modal with metadata and five deterministic JPEG camera views. Local/cloud/public gallery with search, XL/M/S, edit/copy/delete and dock left/right/bottom. JSON/GLB exports include profile/vehicle/time/version in filenames.
- Terrain profiles flat, bumps, hills, extreme, moon and beach, selectable tiled procedural ground maps (asphalt/grass/dirt/gravel/sand/snow/moon), FBM animated cloud/night shader, water shader, puddles, wheel marks, splashes, and **approximate water drag/buoyancy**. Water is not a fluid solver.
- Local IndexedDB and private/public Flask/SQLite persistence, versioned release watcher, health endpoint and scoped logs.

## v0.3.5 interaction and scope notes

- Windows keep their own minimized state across BUILD and DRIVE. The test map uses compact icon controls, a bottom-overlay settings dock and constant map-scale projection when resizing its window; mouse wheel/pinch or +/- changes zoom explicitly.
- Shift+A opens a small pointer-positioned searchable object palette. Selected scene objects support Shift+D duplicate, X remove, G move, R rotate and E scale; static object Y may be below ground elevation. Static obstacle edits avoid expensive terrain and vegetation rebuilds. Hills/dunes still require rebuilding terrain colliders, and Rapier/Ammo may briefly reconstruct the active physics adapter.
- The audio inspector supports live engine-sound changes and independent JSON import/export of sound presets, with collision and rollover sound cues. Audio must be enabled by browser user interaction.
- Multiple cars can be visible in one scene via gallery **＋** and the Scene vehicles panel. One car is active for BUILD/DRIVE; parked cars use static collision-box approximations. Independent simultaneous active vehicle physics, ownership synchronization and multiplayer are future work.
- A wheel AI Create tile uses a configured provider key when available. Paid provider tasks remain explicit and authorization is required; missing keys must be configured before generation. No AI generation is automatically billed on selection alone.
- This remains a procedural prototype. Browser graphics, drive physics, audio and remote AI integrations have not been verified in this release environment. Do not present it as production-ready.

## v0.2.8 material, terrain, avatar and XR architecture

- **Material studio:** floating reusable picker with native `input[type=color]`, palette families, material targets (body, glass, trim, tyres, rims, seats, interior), per-target procedural patterns, octave/lacunarity/gain/warp/scale/contrast/micro-detail/tiling controls and live geometry refresh. Custom generated themes derive ink color from computed contrast and font presets may enumerate local fonts with explicitly granted `queryLocalFonts()` permission in supported browsers.
- **Wheels:** per-front and per-rear radius, tyre width, lateral offset, rim style (`alloy`, `steel`, `disc`, `spoke`, `turbine`, `mesh`, `beadlock`), per-axle spokes, sidewalls, alloy colors and instanced 3D tread depth and axle longitudinal offsets; the same hardpoint and radii properties feed visual wheels and Cannon/Rapier/Ammo controllers. These are graphical/raycast approximations rather than a fully independently sprung mechanical assembly.
- **Environment:** terrain albedo and normal maps from independently adjustable multi-octave FBM noise and surface-specific friction coefficients. Sky is a layered FBM cloud shader, night lighting uses stars, ocean/puddles use animated shader planes. Wheel tracks are bounded instanced decals and splashes are bounded particle pools. Simplified water drag/lift is not actual hydrodynamics.
- **Occupants:** uploaded GLB blobs and clip-name maps are retained in local IndexedDB (v2 schema); each seat can bind a separate avatar. Clip matching uses names `Driving`, `Sitting`, `Walking`, `Entering`, `Exiting`, `OpenDoor`, `CloseDoor`; absent clips leave simple geometric interpolation only. Door motion and boarding are *visual approximations*; steering wheel geometry rotates, but full avatar hand/pedal IK and physical passenger constraints are still future tasks. Portable JSON saves only model references, **not** embedded avatar assets: export GLB files separately when migrating browsers.
- **Experimental WebXR:** `navigator.xr` detects immersive-VR support on HTTPS, controller rays attempt teleport to terrain or toggle vehicle doors, cabin button relocates the headset. Requires capable headset/browser and must be tested there before being treated as production ready.
- **Performance:** bounded track instances and splash particle buffers, dynamically created material texture maps disposed with vehicles, single renderer canvas and opt-in physics engine loading. Material previews use a 288x192 offscreen target and restore renderer viewport/scissor/full stage dimensions after five viewpoints.

## Run / install

Place exactly **`META_VEHICLE_LAB_UPDATE_v0.3.5.zip`** in:

`/Users/smielniczuk/Documents/works/meta-vehicle-lab/updates/META_VEHICLE_LAB_UPDATE_v0.3.5.zip`

From repository root:

```sh
./watcher-meta-vehicle.sh --dry-run
./watcher-meta-vehicle.sh --once
# Continuous: ./watcher-meta-vehicle.sh --interval 3
# Diagnostics: ./watcher-meta-vehicle.sh --tail
```

Mac watcher checks versioned ZIP hashes/tests, verified GitHub main, SSH `-p 333 root@vehiclelab.xyz`, public `/var/www/vehiclelab.xyz` plus versioned Flask service. SQLite and binary assets persist under `/var/lib/vehiclelab`, outside code releases. Flask/Gunicorn at `127.0.0.1:8766` behind Nginx `/api/` proxy. Python deps: Flask 3.1.1, Gunicorn 23.0.0, Pillow 11.3.0. Browser needs Internet for pinned Three/physics imports and HTTPS for webcam permission.

## Controls

- Rotate camera with canvas drag, zoom with scroll/pinch; driving camera follows from chosen orbit.
- Drive with arrow keys or touch joystick, Space/touch brake.
- Cmd/Ctrl+Z undo; Cmd/Ctrl+Shift+Z redo; Cmd/Ctrl+/ searchable shortcut dialog; Cmd/Ctrl+S opens custom Save; D toggles Drive; R explicitly resets camera.
- Config/Profile roundels are always top-right; gallery can dock or float; editor windows remember their position on refresh.

## Data and security

v3 blueprint uses Three.js Y-up +Z-forward geometry, `vehicle` and independent `modules`, `simulation`, `occupants`, `metadata` (category/description/five preview JPEGs). Each parameter is bounded by GUI and backed by collision/visual geometry as appropriate. Imported GLB binary is **not** embedded in JSON; local IndexedDB preserves body/occupant file(s). User-owned body GLB can be uploaded to SQLite; occupant GLB server asset storage is a future milestone.

Profile identity is a random bearer secret (not UUID-based login). JSON profile backups include credentials and must not be shared. No verified password/email recovery, SMTP activation or Postfix configuration. OpenAI and xAI image generation and edits use authenticated fixed HTTPS API routes with user-provided keys kept in browser memory; Lux3D handles billable 3D creation. Tripo 3D endpoints remain unimplemented. Provider model-list diagnostics are separately read-only. Admin logs require a legacy administrator token; guests cannot access them.

## Lux3D integration (v0.2.9)

Open Configuration → **Lux3D · chassis generator & API diagnostics**. Choose region and enter a Lux3D API key. **Test key · no generation** sends only `GET /generate/task/list?page=1&pagesize=3` through the authenticated Flask backend. **This cannot return credit balance:** the currently published AHOLO OpenAPI does not expose an account-balance endpoint. Check credits in your Lux3D account/dashboard instead. The key lives in browser memory only and never enters the profile, SQLite, blueprint or browser storage.

The component generator composes prompts for a car exterior body shell without wheels and tyres, or separate bumpers and lights. Choose G1/G1-Turbo, style and optionally a reference image; explicitly acknowledge potentially billable generation. Flask submits to the documented asynchronous Lux3D text-to-3D endpoint, polls read-only status and exposes provider output URLs. Download GLB and import in Tools → Import GLB to replace the visual body; physics and separately generated wheels remain procedural. Generated geometry separation requires inspection because prompts cannot guarantee object exclusion. Supports international `https://api.aholo.ai/global/lux3d/v1` and China `https://api.aholo3d.cn/lux3d/v1` with `Authorization: <key>` (not Bearer). Task URLs may expire after two hours.

Actual production API-key use, quality, billing and GLB integration **have not been tested** with a real Lux3D account. Lux3D homepage docs: https://lux3d.aholo.ai/docs and the published OpenAPI: https://labs.aholo.ai/api-docs/en/openapi.json . Tripo generation still requires its missing server integration.

## Roadmap — staged priorities

**P0 acceptance:** independently test v0.2.8 browser startup, Rapier/Ammo loading, photo capture/stream stop, screenshot capture, gallery privacy, camera invariant, undo/redo, mobile interactions and server deployment.

**P1 blueprint v4:** split components into modules; stable IDs and hard-point anchors for wheels, doors, seats, windows and lights; wheel tread/suspension/dual wheel sets; real door/window cutouts; independent collider/visual shapes. Replace bounded snapshot history with a semantic persistent operation log.

**P2 driving worlds:** replace v0.2.8 approximate surface-grip/water drag, visual tracks and splash particles with physically validated contact materials, sediment deformation, water volumes, buoyancy forces and wave coupling; benchmark solver comparisons under controlled identical conditions.

**P3 occupants/interiors:** build on current per-seat IndexedDB GLB assets, clip mapping, simple timed boarding movement, animated doors, dashboard and steering wheel. Add server asset sync, retargetable rigs, IK steering hands/pedals, pathfinding and collision-checked entry/exit, actual physical door hinges, detailed interiors and animations for no-clip models.

**P4 immersive WebXR:** validate v0.2.8 experimental immersive-VR feature gating, controller-ray teleportation and cabin relocation against supported devices; add obstacle-checked teleport, vehicle access/exit, richer interior displays, mirrors and in-cab cameras while retaining desktop fallback.

**P5 services:** optional password/WebAuthn accounts, verified email/phone, recovery tokens with rate limits, real mail delivery, image-generation job workers, controlled provider spend and gallery moderation.

## Ideas

Procedural body profiles; advanced suspension families and 2/4/6/12+ wheel platforms; diverse tires/treads/track systems; camera-based interiors and AR tabletop scale; animated boarding; vehicle-to-vehicle comparison; immutable gallery media, tags/collections/remix lineage; LOD/culling and offline dependency vendoring; semantic LLM edits with approval, diff and rollback.

## LLM handover / engineering invariants

- **Source of truth:** `index.html`, `backend/app.py`, `backend/storage.py`, `deploy/install.py`, `watcher-meta-vehicle.sh` and tests. Begin by reading them; don't rely on this summary when source contradicts it.
- **Portable JSON:** `procedural-vehicle/v3`, meters, Y up, +Z forward. `cfg` is mutable configuration, `mods` transforms by `front/cabin/rear/equipment`, separate GLB replacement mesh, `occupants`, `simulation` backend and metadata. Secret keys/credentials never enter blueprints. New schema must retain legacy import paths.
- **Server trust boundary:** passwordless user profile UUID is not a credential. Bearer secret is hashed server-side; guest routes `/api/identity/*`, `/api/me/*` own resources, `/api/gallery` publicly published only, `/api/admin/logs` administrator token only. Preserve SQLite data and user assets during deploy/rollback.
- **Physics architecture:** Cannon/Rapier/Ammo use raycast-wheel controllers with different tuning; the non-physics kinematic reference is not comparable for physical fidelity. Terrain uses sampled colliders, raycast-wheel support and an approximate water drag/lift heuristic. Night/sky/water shaders are visual effects; neither fluid simulation nor engineering-grade buoyancy is implemented. Never claim full wheel/door articulation or robust VR headset verification before measured tests.
- **UI invariants:** 3D stage fills viewport; top-right roundels open right-side drawers; no blocking forms nested; windows float, minimize, drag, resize, persist. Editor camera angle/zoom stays unchanged across build-drive toggles unless explicit Reset Camera. Rotation persists separately. Save dialog is custom and captures five fixed views without rotating main camera.
- **Undo:** bounded 160-entry local snapshots grouped after idle, not a durable multiplayer transaction log; GLB references are memory-only in history and IndexedDB stores binaries. Future plan is semantic operation log and server media assets.
- **Docs/watch compatibility:** current watcher accepts the original exact 15 app files; to add deployable docs, first update watcher manifest support. Never put documentation-only ZIP into `updates/`.
- **Deployment:** user downloads a *single release ZIP* to `updates/`; avoid separate `.sh` downloads. GitHub `main`; SSH port 333; versioned `/opt/vehiclelab` service; logs `.vehiclelab/logs/`. Provide exact download destination, preserve unrelated Nginx sites, do not silently modify Postfix.
- **Validation:** Python storage/Nginx tests run offline; Flask API tests require pinned venv. JavaScript syntax is checked with Node after extracting inline module. Browser startup, real physics solvers, imported-rig animations, GPU shaders, WebXR, and public deployment **have not been validated here**. Do not substitute static validation for live execution evidence.

For a deeper handoff with detailed contracts, checkpoints, dependencies and test matrices see the optional standalone `LLM_HANDOVER.md`, `ROADMAP.md`, `IDEAS.md`, `INSTALL.md` and `ABOUT.md` documentation ZIP.

## Changelog

See `CHANGELOG.md`. Current packaged version is **0.2.6** and must not be described as publicly deployed until the watcher reports successful GitHub/server/health verification.

## Offline Blender asset worker (administrator only)

This release includes an **opt-in** Blender CLI in `deploy/install.py`; it does not expose public remote code execution through Flask. On the Ubuntu host, the existing deployment prints the Blender installation status. To perform setup during an explicit maintenance window:

```sh
python3 /opt/vehiclelab/current/deploy/install.py --blender-check
sudo python3 /opt/vehiclelab/current/deploy/install.py --blender-install
python3 /opt/vehiclelab/current/deploy/install.py --blender-render /path/to/vehicle.glb --blender-output /path/to/renders --blender-decimate 0.90
```

The last command writes `optimized.glb` and five 960x720 PNG renders (hero, front, rear, side, top). Draco compression is attempted when supported by the installed Blender exporter; Meshopt requires a separate gltfpack/meshoptimizer pass. The Blender tool is intentionally not a guest-facing API and is **not yet connected to the application's Save button**, which retains browser-side previews. Running Blender on untrusted GLBs requires sandboxing, resource limits, authorization, and abuse controls before it can be exposed to the public gallery.

## Browser acceptance gates before production claims

1. Load a Draco-compressed GLB with a skinned animated avatar, a Meshopt-compressed GLB, and a KTX2-textured GLB; verify no decoder errors.
2. Open a v0.2.6 layout and verify all front/rear wheel fields are populated, adjustable and survive BUILD → DRIVE → BUILD.
3. Repeat the same fixed-step drive on Cannon, Rapier and Ammo; verify positive +Z acceleration and correct steering, then compare CSV samples.
4. Import a rigged avatar to seat 1, map Driving/Sitting/Walking clips, board/exit the selected seat and reload the saved layout.
5. Edit octaves, lacunarity, noise scale, texture tiling and terrain normal strength and confirm visibly different material results.
6. Generate five previews; verify the full stage and orbit camera remain intact. Check private/public gallery visibility and cross-user ownership.
7. Verify the offline Blender asset tool separately with a trusted, sufficiently small GLB before considering any public processing service.

## Vehicle Lab 0.3.2 — operator guide

**Aerodynamics:** BUILD → Parameters → `01b · Aerodynamic glazing / roof`. `Front windshield rake m` and `Rear windshield rake m` independently change the front and back top-edge insets (positive Z is forward). `Upper cabin width ratio` tapers side windows. `Door opening type` selects outward `swing` or `gullwing`. Current doors are surface-level procedural geometry and animation rather than physically hinged rigid bodies or cut-through vehicle apertures. Exported blueprint uses `procedural-vehicle/v3` with new config keys.

**Wheel workshop:** While in BUILD mode click a wheel on the canvas or select Tools → Wheel workshop. Pick front or rear axle, choose a procedural rim card and modify axle geometry. Importing a wheel GLB or optional cap GLB stores the bytes under the browser's IndexedDB `avatar-assets` object store (`kind=wheel/cap`), separate from avatar records. The viewer scales GLB geometry to the axle's specified diameter and width; this does not inspect hub bolt patterns, generate an accurately matched collision mesh or guarantee that a generated tire has the correct mechanical topology. A wheel can be restored to procedural. The `AI wheel asset pipeline` delegates to existing image/Tripo/Lux3D components and requires real API endpoints and explicit paid-generation consent; Tripo image-to-3D remains a backend placeholder. Import the resulting wheel GLB directly using Wheel workshop.

**Gallery:** Five preview captures are rendered with temporarily brighter studio lights. Customize scene-independent backdrop and exposure under Parameters → `02b · Gallery render studio`. Transparent uses PNG; other backdrops produce JPEG. The canvas renderer state and full-size viewport are restored after capture. Gallery previews are compressed to fit the bounded SQLite blueprint payload; use server-side Blender separately for high-quality production render output.

**Drive world:** Parameters → `08 · Physics solver & camera` selects orbit, chase, cinematic, top or driver, optional terrain clearance, a delayed visual ghost, and panel auto-hide. Tools/Actions → Camera cycles with `C`, Upright restores a flipped car with `U`; in-camera free-orbit still works in `orbit` mode. The ghost is intentionally translucent playback of prior positions, not a second physical car.

**Procedural vegetation:** Parameters → `09b · Instanced grass / shrubs / rocks`. The grass shader bends in wind and near the car, with one instanced draw call, bounded blade count and no per-blade JavaScript updates. Shrubs and rocks are visual scatter; to create **collidable** rocks, place them using Test map.

**Drive test map:** Tools → Test map. Drag from a starting point to a destination on the overhead canvas after selecting a placement tool. `Hill` modifies terrain heightfield for every physics engine; `Puddle` contributes a water shader and grip/splash checks; solid obstacles have static collision descriptions reused by Cannon/Rapier/Ammo. Choose a named preset or save maps locally to IndexedDB. Export/import schema: `vehiclelab-testmap/v1`. Editing a map in DRIVE returns safely to BUILD before rebuilding the physics heightfield. The beam is static, not a torque-driven seesaw. Race-track racing barriers, multi-segment drawing, buoyancy research and tilting beam hinges remain next milestones.

**UI accessibility:** accent-colored selected buttons use computed foreground ink, rather than hard-coded dark text. User profile/gallery endpoints and earlier private/public authorization rules are unchanged.

## Outstanding production acceptance tests

Test on actual HTTPS/WebGL hardware before deploying as a verified feature: wheel GLB imports using Draco/Meshopt, selection raycasts and rebuilt axle meshes, repeated BUILD ↔ DRIVE on Cannon/Rapier/Ammo, contact with each map obstacle, webcam/identity, public JPEG/PNG previews, browser viewport recovery after 5 captures, iOS/Android window dragging, profile backup recovery and WebXR headset teleport. This package has not been run with an external AI billing account and cannot confirm provider credit usage. Run server `python -m unittest discover -s tests -v` in the pinned Flask venv and watcher `--dry-run` before production installation.


### v0.3.2 — Precision world editing workflow

- Open **Test map** from Tools or the workspace controls. Wheel/pinch to zoom at the cursor, use **+ / −** or Fit. Use the hand tool or drag with the middle/right mouse button to pan; grid labels remain in world metres. The map stays 1:1 even when the window is resized.
- Use the left rail to choose a hill, puddle, traffic cone, tree cluster, hedge, dunes, grass or sand. Draw rectangles/ellipses or choose **Freehand** with **Closed polygon** for areas and **Open curve / ribbon** for paths. Height controls sculpt hills/dunes into the shared terrain collider; water and vegetation patches are meshes/instances, not particle-only approximations.
- **Shift+A** opens a searchable add-object menu (as in Blender). Enter adds the first matching object to the visible ground near the camera target, with basic overlap checks. Click any authored obstacle in BUILD or in the map to open **Object inspector**. Change translation/rotation/scale with Three.js gizmos or exact numeric inputs. Set static/dynamic/no physics, mass, friction, bounce, material color and texture.
- Select and drag on the map to move an object; grab empty map space to pan. Physics collider changes during DRIVE rebuild the selected solver while preserving vehicle position, heading and velocity. This is not a continuous collaborative map-authoring engine, and dynamic object trajectories are not replayable across sessions.
- Save maps to browser IndexedDB or export `vehiclelab-testmap/v2`. Import accepts v1 and v2. Vehicle blueprints carry authored objects, and editor Undo/Redo includes course-object changes.
- **Limits:** non-box colliders use approximate box shapes; trees are instanced visuals; bridges and balance beams are static prototypes rather than articulated hinges; water patches are approximate shader surfaces, not full fluid dynamics. Physics/transform interactions require an actual browser acceptance pass on each supported engine.

### v0.3.1 — Reference and map workflows

**Generate a chassis without tyres:** Configuration → Lux3D → set model/style/prompt. Select **Capture body-only 3/4 view** to render an isolated, well-lit body shell, or **Upload reference image** to use PNG/JPEG/WebP. Verify the preview and **Include this reference image** before explicitly authorising a potentially chargeable task. This image is transmitted to Lux3D only on generation. Never submit a paid task merely to test an API key.

**Load the resulting model:** On task success, Vehicle Lab attempts to import a GLB through the same-origin Flask endpoint `/api/providers/lux3d/import` when **Automatically import** is selected. The backend obtains the task's official temporary output URL after authenticating your profile and Lux3D key. It only accepts GLB and ZIP-with-GLB and only downloads from a restricted set of provider/CDN domains; unsupported providers or expired links require manual download/import. Result GLBs replace the visual vehicle shell, not its procedural suspension or wheels. Generated wheel GLBs go to the wheel workshop instead of the body.

**Design a test map:** Open **Test map**, select **Relief / contours** or **Precision plan / symbols**, and use the narrow left-side icon toolbar. Every view stays exactly 1:1 independent of window resizing. Change footprint type, drag on the map, save locally or export JSON. Editing a map while driving rebuilds the physics world and restores the last vehicle pose/velocity. Temporary suspension resets/reconfiguration should be checked in each backend.

**Access tokens:** Your passwordless Vehicle Lab profile authorizes private/public layouts and Lux3D import. Provider keys are separate, used only when contacting the selected provider, and kept in browser memory. Server-log access requires a distinct administrator token. Successful OpenAI model listing does not grant permission for admin logs.

**Acceptance limitations:** No live generated model, signed provider result URL, CORS CDN, or driving physics roundtrip has been verified in a real deployed browser. These must be tested after deployment; version and syntax checks are not substitutes for full interaction testing.

## v0.3.3 repair scope (2026-11-09)

- Align Rapier compatibility build (`rapier.mjs` v0.21), vehicle wheel accessors and physics error staging with the current Three.js Rapier vehicle-controller example. **Runtime parity is not established until a real browser test succeeds.**
- Wheel style/material changes replace only wheel meshes and avoid reconstructing the driver/cabin. Chassis reference uses a separate offscreen orthographic camera fitted to model bounds, with explicit body-only vs whole-vehicle options.
- Add procedural WebAudio engine sound with start, idle, throttle harmonic/noise, braking and impact parameters (electric, petrol, diesel, turbine presets). Audio starts only with a user gesture and is silent in BUILD.
- Add compact XYZ and dimension inspector rows with focused sliders; object orthographic views 1–7 and +/- zoom. Avoid reconstructing occupants on ordinary course edits. Add parameter groups for cockpit seats, dashboard and lamps.
- Improve higher-zoom map contours and preserve fixed map pixel resolution when resizing the window. Map edits are attached to the existing Undo/Redo history.
- The wheel workshop offers in-place AI prompts, tab-only provider keys, and Lux3D auto-import of finished wheel GLBs. OpenAI (`gpt-image-2.5-flare`) and xAI (`grok-imagine-image-2.0`) reference-image generation and edit routes use owner-scoped credentials and explicit calls; these routes are not free, and no real paid task is tested.
- Tripo image-to-3D remains a disabled backend contract, and the physics realism of roof impacts/door joints is not engineering-certified. The release has static/code/test validation, not a full WebGL interactive acceptance pass.


## v0.3.5 — wheel model library and diagnostics

**Administrator access (on your own Ubuntu host only):** the protected Flask token is in
`/etc/vehiclelab/vehiclelab.env`, named `VEHICLELAB_API_TOKEN`. View it in your own shell
with `ssh -t -p 333 root@vehiclelab.xyz "sudo grep '^VEHICLELAB_API_TOKEN=' /etc/vehiclelab/vehiclelab.env"`.
The value after `=` authorizes administrator-only server logs and legacy admin APIs.
Never export this token in profiles, commits, screenshots or public support requests.
Provider API keys and profile credentials are unrelated.

**Imported wheel models:** wheel GLBs are now shown as shaded 192px thumbnails inside
Wheel workshop, produced in an isolated browser WebGL renderer without changing the
main stage. A new GLB is saved into the existing IndexedDB 3D asset library and can be
assigned to front or rear wheels. Axis auto-detection chooses the shortest model dimension
as the axle and rotates that axis onto Vehicle Lab's X-axis wheel spindle. Use the selected
wheel's `X ↻ 90°`, `Y ↻ 90°`, or `Z ↻ 90°` controls to correct unusual asset axes.
Each imported asset's orientation and thumbnail are persisted in IndexedDB. The vehicle's
wheel radius/width and raycast collider remain independently procedural. This does not
produce a precise physical tyre collider from arbitrary GLB geometry.

**Production image generation:** the optional Blender CLI described above remains a
separate administrator tool; a secure public rendering queue is not yet installed.
The workshop uses local GLB thumbnail rendering immediately. No Blender installation is
triggered automatically during deployment or when users import models.

**Rapier:** the controller now uses the documented setter property `setIndexForwardAxis`
instead of writing the getter-only `indexForwardAxis` field. **Ammo:** corrected the
engine-force convention to positive forward (+Z) and moderated braking impulse. Browser
road-test calibration of the three engines is still required; a successful syntax test
is not a proof of driving parity.
