# Vehicle Lab — procedural 3D vehicle studio

**Version 0.2.8 (2026-11-08)**. Browser-native modular vehicle editor built with Three.js, lil-gui, three alternative physics engines, optional GLB imports, Flask and SQLite. Project: https://github.com/sylwesterdigital/meta-vehicle-lab. Website: https://vehiclelab.xyz/.

This README deliberately contains the **About, Install, Roadmap, Ideas and LLM Handover** sections in a single allowed release file. The current watcher validates an exact 15-file manifest, so adding standalone documentation to a watcher release without first migrating its manifest schema would reject the ZIP. A separate optional documentation archive contains those sections as individual Markdown files.

## About / product scope

Vehicle Lab is a prototype for procedurally assembling visually plausible city cars, buses, municipal vehicles, heavy trucks, construction equipment, agricultural machinery and warehouse vehicles from parameterized hull modules and equipment. Parameters cover width/height/depth/scale/rotation/offset, body materials, wheels, axles, doors/windows, passenger slots, engines and driving physics. Modules can later be transferred into a shared 3D world as an independent blueprint generator. This is **not** an engineering-grade physics simulator.

## Features in v0.2.8

- Full-size Three.js canvas. Draggable, resizable, minimizable actions/tools/catalog/gallery/parameters/log windows. Right-side configuration and profile drawers, custom theme/typography and text/icon button modes.
- Circular uploaded/webcam profile picture, optional passwordless identity, bearer-secret JSON backup. Credentials must remain private. Public gallery is **opt-in**; private layouts remain owner-scoped.
- 40 presets, three hull modules plus equipment, procedural materials, number of doors/windows/seats, independent front/rear wheel radius/tyre width/rim style/outset/front and rear axle offsets, imported GLB visual body/occupants.
- Three independent driving solvers: Cannon-es, Rapier WASM and Ammo.js/Bullet raycast vehicles; no kinematic baseline. Each backend uses its own raycast-wheel physics. Orbit-follow camera, 60Hz benchmark, CSV.
- BUILD ↔ DRIVE preserves camera direction/zoom, with explicit camera reset. Rotation toggle highlights active state and persists. Preset/parameter edit history supports Undo/Redo (Cmd/Ctrl+Z, Shift+Z), searchable Cmd/Ctrl+/ shortcut dialog.
- Mobile-friendly Save modal with metadata and five deterministic JPEG camera views. Local/cloud/public gallery with search, XL/M/S, edit/copy/delete and dock left/right/bottom. JSON/GLB exports include profile/vehicle/time/version in filenames.
- Terrain profiles flat, bumps, hills, extreme, moon and beach, selectable tiled procedural ground maps (asphalt/grass/dirt/gravel/sand/snow/moon), FBM animated cloud/night shader, water shader, puddles, wheel marks, splashes, and **approximate water drag/buoyancy**. Water is not a fluid solver.
- Local IndexedDB and private/public Flask/SQLite persistence, versioned release watcher, health endpoint and scoped logs.

## v0.2.8 material, terrain, avatar and XR architecture

- **Material studio:** floating reusable picker with native `input[type=color]`, palette families, material targets (body, glass, trim, tyres, rims, seats, interior), per-target procedural patterns, octave/lacunarity/gain/warp/scale/contrast/micro-detail/tiling controls and live geometry refresh. Custom generated themes derive ink color from computed contrast and font presets may enumerate local fonts with explicitly granted `queryLocalFonts()` permission in supported browsers.
- **Wheels:** per-front and per-rear radius, tyre width, lateral offset, rim style (`alloy`, `steel`, `disc`, `spoke`, `turbine`, `mesh`, `beadlock`), per-axle spokes, sidewalls, alloy colors and instanced 3D tread depth and axle longitudinal offsets; the same hardpoint and radii properties feed visual wheels and Cannon/Rapier/Ammo controllers. These are graphical/raycast approximations rather than a fully independently sprung mechanical assembly.
- **Environment:** terrain albedo and normal maps from independently adjustable multi-octave FBM noise and surface-specific friction coefficients. Sky is a layered FBM cloud shader, night lighting uses stars, ocean/puddles use animated shader planes. Wheel tracks are bounded instanced decals and splashes are bounded particle pools. Simplified water drag/lift is not actual hydrodynamics.
- **Occupants:** uploaded GLB blobs and clip-name maps are retained in local IndexedDB (v2 schema); each seat can bind a separate avatar. Clip matching uses names `Driving`, `Sitting`, `Walking`, `Entering`, `Exiting`, `OpenDoor`, `CloseDoor`; absent clips leave simple geometric interpolation only. Door motion and boarding are *visual approximations*; steering wheel geometry rotates, but full avatar hand/pedal IK and physical passenger constraints are still future tasks. Portable JSON saves only model references, **not** embedded avatar assets: export GLB files separately when migrating browsers.
- **Experimental WebXR:** `navigator.xr` detects immersive-VR support on HTTPS, controller rays attempt teleport to terrain or toggle vehicle doors, cabin button relocates the headset. Requires capable headset/browser and must be tested there before being treated as production ready.
- **Performance:** bounded track instances and splash particle buffers, dynamically created material texture maps disposed with vehicles, single renderer canvas and opt-in physics engine loading. Material previews use a 288x192 offscreen target and restore renderer viewport/scissor/full stage dimensions after five viewpoints.

## Run / install

Place exactly **`META_VEHICLE_LAB_UPDATE_v0.2.8.zip`** in:

`/Users/smielniczuk/Documents/works/meta-vehicle-lab/updates/META_VEHICLE_LAB_UPDATE_v0.2.8.zip`

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

Profile identity is a random bearer secret (not UUID-based login). JSON profile backups include credentials and must not be shared. No verified password/email recovery, SMTP activation or Postfix configuration. AI generator endpoints remain contracts, while API-key model-list diagnostics are separate. Admin logs require a legacy administrator token; guests cannot access them.

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
