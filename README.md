# Vehicle Lab — procedural 3D vehicle studio

**Version 0.2.6 (2026-11-08)**. Browser-native modular vehicle editor built with Three.js, lil-gui, three alternative physics engines, optional GLB imports, Flask and SQLite. Project: https://github.com/sylwesterdigital/meta-vehicle-lab. Website: https://vehiclelab.xyz/.

This README deliberately contains the **About, Install, Roadmap, Ideas and LLM Handover** sections in a single allowed release file. The current watcher validates an exact 15-file manifest, so adding standalone documentation to a watcher release without first migrating its manifest schema would reject the ZIP. A separate optional documentation archive contains those sections as individual Markdown files.

## About / product scope

Vehicle Lab is a prototype for procedurally assembling visually plausible city cars, buses, municipal vehicles, heavy trucks, construction equipment, agricultural machinery and warehouse vehicles from parameterized hull modules and equipment. Parameters cover width/height/depth/scale/rotation/offset, body materials, wheels, axles, doors/windows, passenger slots, engines and driving physics. Modules can later be transferred into a shared 3D world as an independent blueprint generator. This is **not** an engineering-grade physics simulator.

## Features in v0.2.6

- Full-size Three.js canvas. Draggable, resizable, minimizable actions/tools/catalog/gallery/parameters/log windows. Right-side configuration and profile drawers, custom theme/typography and text/icon button modes.
- Circular uploaded/webcam profile picture, optional passwordless identity, bearer-secret JSON backup. Credentials must remain private. Public gallery is **opt-in**; private layouts remain owner-scoped.
- 40 presets, three hull modules plus equipment, procedural materials, number of doors/windows/seats, wheel radius/tyre width/outset/front and rear axle offsets, imported GLB visual body/occupants.
- Three independent driving solvers: Cannon-es, Rapier WASM and Ammo.js/Bullet raycast vehicles. Non-physics baseline mode. Orbit-follow camera, 60Hz benchmark, CSV.
- BUILD ↔ DRIVE preserves camera direction/zoom, with explicit camera reset. Rotation toggle highlights active state and persists. Preset/parameter edit history supports Undo/Redo (Cmd/Ctrl+Z, Shift+Z), searchable Cmd/Ctrl+/ shortcut dialog.
- Mobile-friendly Save modal with metadata and five deterministic JPEG camera views. Local/cloud/public gallery with search, XL/M/S, edit/copy/delete and dock left/right/bottom. JSON/GLB exports include profile/vehicle/time/version in filenames.
- Terrain profiles flat, bumps, hills, extreme, moon, beach, adjustable terrain extent and solid/gradient/simple-cloud/night sky. Beach water visual only — not fluid physics or buoyancy.
- Local IndexedDB and private/public Flask/SQLite persistence, versioned release watcher, health endpoint and scoped logs.

## Run / install

Place exactly **`META_VEHICLE_LAB_UPDATE_v0.2.6.zip`** in:

`/Users/smielniczuk/Documents/works/meta-vehicle-lab/updates/META_VEHICLE_LAB_UPDATE_v0.2.6.zip`

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

## Roadmap — staged priorities

**P0 acceptance:** independently test v0.2.6 browser startup, Rapier/Ammo loading, photo capture/stream stop, screenshot capture, gallery privacy, camera invariant, undo/redo, mobile interactions and server deployment.

**P1 blueprint v4:** split components into modules; stable IDs and hard-point anchors for wheels, doors, seats, windows and lights; wheel tread/suspension/dual wheel sets; real door/window cutouts; independent collider/visual shapes. Replace bounded snapshot history with a semantic persistent operation log.

**P2 driving worlds:** terrain-material friction, wheel tracks, loose sand, potholes/obstacles, water volume drag/buoyancy, wave/splash effects, night lighting and repeatable identical benchmark courses with recorded solver timings.

**P3 occupants/interiors:** owner-scoped occupant GLB assets, bones/rig maps, Sitting/Driving/Enter/Exit/DoorOpen/DoorClose state machine, physical door hinges, steering wheel, seating and dashboards.

**P4 immersive WebXR:** device feature detection, spectator/XR mode, controller floor raycast for safe teleportation, vehicle portal, sit/exit, interactive interior displays, mirrors and in-cab cameras; maintain desktop fallback.

**P5 services:** optional password/WebAuthn accounts, verified email/phone, recovery tokens with rate limits, real mail delivery, image-generation job workers, controlled provider spend and gallery moderation.

## Ideas

Procedural body profiles; advanced suspension families and 2/4/6/12+ wheel platforms; diverse tires/treads/track systems; camera-based interiors and AR tabletop scale; animated boarding; vehicle-to-vehicle comparison; immutable gallery media, tags/collections/remix lineage; LOD/culling and offline dependency vendoring; semantic LLM edits with approval, diff and rollback.

## LLM handover / engineering invariants

- **Source of truth:** `index.html`, `backend/app.py`, `backend/storage.py`, `deploy/install.py`, `watcher-meta-vehicle.sh` and tests. Begin by reading them; don't rely on this summary when source contradicts it.
- **Portable JSON:** `procedural-vehicle/v3`, meters, Y up, +Z forward. `cfg` is mutable configuration, `mods` transforms by `front/cabin/rear/equipment`, separate GLB replacement mesh, `occupants`, `simulation` backend and metadata. Secret keys/credentials never enter blueprints. New schema must retain legacy import paths.
- **Server trust boundary:** passwordless user profile UUID is not a credential. Bearer secret is hashed server-side; guest routes `/api/identity/*`, `/api/me/*` own resources, `/api/gallery` publicly published only, `/api/admin/logs` administrator token only. Preserve SQLite data and user assets during deploy/rollback.
- **Physics architecture:** Cannon/Rapier/Ammo use raycast-wheel controllers with different tuning; the non-physics kinematic reference is not comparable for physical fidelity. Terrain uses matching sampled collider mesh, though night/sky/water are visual. Never claim true buoyancy or full wheel/door articulation before implemented.
- **UI invariants:** 3D stage fills viewport; top-right roundels open right-side drawers; no blocking forms nested; windows float, minimize, drag, resize, persist. Editor camera angle/zoom stays unchanged across build-drive toggles unless explicit Reset Camera. Rotation persists separately. Save dialog is custom and captures five fixed views without rotating main camera.
- **Undo:** bounded 160-entry local snapshots grouped after idle, not a durable multiplayer transaction log; GLB references are memory-only in history and IndexedDB stores binaries. Future plan is semantic operation log and server media assets.
- **Docs/watch compatibility:** current watcher accepts the original exact 15 app files; to add deployable docs, first update watcher manifest support. Never put documentation-only ZIP into `updates/`.
- **Deployment:** user downloads a *single release ZIP* to `updates/`; avoid separate `.sh` downloads. GitHub `main`; SSH port 333; versioned `/opt/vehiclelab` service; logs `.vehiclelab/logs/`. Provide exact download destination, preserve unrelated Nginx sites, do not silently modify Postfix.
- **Validation:** Python storage/Nginx tests run offline; Flask API tests require pinned venv. JavaScript syntax is checked with Node after extracting inline module. Live target-browser acceptance and public deployment **not verified here**; obtain actual test evidence, don't invent it.

For a deeper handoff with detailed contracts, checkpoints, dependencies and test matrices see the optional standalone `LLM_HANDOVER.md`, `ROADMAP.md`, `IDEAS.md`, `INSTALL.md` and `ABOUT.md` documentation ZIP.

## Changelog

See `CHANGELOG.md`. Current packaged version is **0.2.6** and must not be described as publicly deployed until the watcher reports successful GitHub/server/health verification.
