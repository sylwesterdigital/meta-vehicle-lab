# v0.3.0 — Aerodynamic vehicle geometry, wheel workbench, terrain maps and drive cinematics (2026-11-08)

- Aerodynamic cabin loft: independent front/rear windshield rake and narrower upper roof, tapered side glazing, side window divisions and dedicated front/back glass panels; two explicit outward-opening door modes (side-hinged and gullwing). Procedural modules remain parametric.
- Click-to-select front/rear wheels. Floating wheel workbench with six geometrical rim styles, independent axle radius/thickness/outset/spokes/sidewall/alloy settings; GLB wheel and optional hubcap imports stored in IndexedDB with fitting to the current wheel envelope and Draco/Meshopt support. 3D model geometry is **not** a new physical wheel collider; radius/width remain the collider blueprint.
- Five offscreen studio previews use temporary bright key/fill/hemisphere lighting and restored renderer state. Backdrops: studio, gradient, rainbow, solid, white, black or transparent PNG. Preview images are bounded for the 256-KiB SQLite blueprint limit. This is browser-based preview rendering, not the Blender render service.
- Drive cameras: orbit/chase/cinematic/overhead/in-cab camera, terrain-aware camera altitude, C to cycle. Driving mode can hide editing windows and restore them on return. Optional same-car *visual* ghost following a recorded trajectory 3 seconds late. Upright recovery is implemented per Cannon/Rapier/Ammo adapter; U button/shortcut.
- Visual instanced shader grass (wind and vehicle-proximity bending), shrubs and scattered rocks with adjustable instance budgets and seeded placement; ground terrain and weather are retained. No vertex-by-vertex CPU grass animation.
- Floating topographic test-map editor: place custom hills, puddles, cones, stones, barriers, cuboids, pyramids, ramps, raised bridges and a **static** balance beam, save/load map presets or IndexedDB maps, import/export `vehiclelab-testmap/v1` JSON. Obstacles use a shared collider specification across the three physics adapters. Static beam does **not** tilt; a physics hinge is a future milestone.
- Selected theme buttons now derive foreground ink from the active accent and expose keyboard focus. Add Lux3D isolated-wheel component prompt and allow public gallery JPEG or PNG heroes.
- Extend map/preview state preservation across history, saved blueprints and old-layout load. No database migration beyond IndexedDB `test-maps` object store v3. Server SQLite schema is unchanged.
- Validation: Node parser, stdlib SQLite regression suite, watcher dry-run, ZIP hashes and static interaction checks. In-browser WebGL rendering, real Rapier/Ammo contact behavior, imported wheel orientation and WebXR/AI jobs require manual device/account acceptance tests. No production installation claimed.

# v0.2.9 — Lux3D key diagnostics and component-oriented 3D generation (2026-11-08)

- Add a dedicated Lux3D testing and generation page inside the AI configuration drawer; select international or China region, test key, inspect recent task count/status.
- The documented GET task list operation validates credentials WITHOUT creating generation tasks. The published Lux3D OpenAPI does not expose a balance endpoint: the UI reports it as unavailable rather than inventing credits or using a billable call.
- Add explicit charge acknowledgement before generating text-to-3D. Generate body shells without wheels, separate front/rear bumpers or light assemblies, with G1/G1-Turbo and documented style controls. Reference image is optional.
- Flask proxies provider requests to fixed documented gateways, never stores API keys, validates guest authorization and request bounds, limits repeated generations, polls by task ID, and returns provider download links (not an unsafe arbitrary-URL proxy).
- Generated GLB must be downloaded and imported through the existing Import GLB action; provider output quality (such as actual absence of tyres) is not guaranteed by the prompt. Model output/credit billing remain subject to Lux3D's service.
- Existing Tripo backend remains an unimplemented integration contract. No account-balance read operation is documented for Lux3D, and no paid API calls or real provider-key tests were performed in the authoring environment.
- Local JavaScript syntax, SQLite regressions, new mocked Flask tests (when Flask available), archive integrity and watcher dry run are the release gates; real provider browser and server deployment require runtime acceptance.

# v0.2.8 — Compressed GLB loading, wheel editor compatibility and physics parity (2026-11-08)

- All chassis/driver/avatar GLB loading shares pinned Three.js Draco, Meshopt and KTX2/Basis decoders; compression errors are surfaced clearly.
- Legacy saved vehicle configurations normalize missing wheel and texture properties before lil-gui controller creation. Fix the empty Front axle folder when loading pre-v0.2.7 saves; show independent front/rear wheel controls.
- Physically modeled tyre face/sidewall, rim discs and spoke/bolt patterns; instanced geometry treads with per-axle colors, thickness, radii, offsets, tread depth and spoke counts.
- Rapier controller axle orientation and steering are aligned with the +Z vehicle blueprint; engine-force magnitude raised for comparison. Remove the no-physics baseline selection. Exact solver parity **requires browser driving tests**.
- Add a configurable multi-octave FBM texture editor: base frequency, octaves, lacunarity, gain, warp, contrast, micro-detail, tiling, UV scale and normal-map intensity. Generate terrain albedo and normal textures, and reuse FBM for paint and upholstery.
- Occupant panel is reachable from Tools; seat 1 is Driver, model/animation clips are per-seat and boarding/exiting act on the selected seat. Seat occupancy is included in blueprint and edit history.
- Versioned offline Blender admin tool generates five studio images and optimized GLB with optional Draco export. Blender installation is explicit (not automatic during deployments on a multi-site host); public untrusted GLB processing is not enabled.
- Regression tests for decoder registration, wheel defaults, physics selector, selected-seat behavior, noise parameters and Blender tool entry points. No SQLite schema migrations; existing layouts remain compatible.
- **Validation boundary:** JavaScript syntax and local Python/SQLite tests passed; CDN decoding, WebGL render, browser driving and remote Blender execution still require actual device/server acceptance.

# v0.2.7 — Materials, independent axles, driving terrain, occupant library, viewport fix, WebXR (2026-11-08)

- Fix gallery capture leaving the 3D stage at 288×192 by preserving and restoring render target, viewport, scissor, scissor test, full canvas dimensions and camera aspect. Exclude water, tracks and splash effects from snapshots.
- Round profile-avatar buttons open image picker directly; webcam capture still requires explicit permission. Add a font-name selector, opt-in Local Font Access API enumeration and luminance-aware generated UI themes with accessible contrasting labels.
- Add a reusable floating Material Studio with native color spectrum, six palette families, independent body/glass/seat/interior/tyre/rim/trim materials and seeded procedural finishes.
- Add independent front/rear wheel radii, tyre widths, lateral offsets and rim styles, retaining longitudinal axle offsets and using matching radii/positions in Cannon/Rapier/Ammo adapters.
- Add procedurally textured asphalt/grass/dirt/gravel/sand/snow/moon surfaces, layered FBM cloud and night-sky shaders, animated puddles/beach water, wheel tracks, splash particles, approximate low-grip surfaces and water drag/lift approximations.
- Store separate imported rigged GLB avatars in IndexedDB, associate models and clip names with seats, support named sitting/driving/walking/entering/exiting/door animations when available, visual door-opening and staged boarding, and cockpit steering wheel/dash models. Assets are not embedded in portable JSON.
- Add experimental WebXR immersive-VR mode with controller ray and terrain teleport, door interaction and cabin relocation. Not device-verified; robust XR collision, physically articulated door/passenger bodies and animation retargeting remain future work.
- No Flask/SQLite schema migration, authentication or SMTP changes. The application and watcher retain their existing release deployment behavior.
- Offline verification: syntax and Python storage/Nginx regressions. Live browser/VR/physics engine acceptance and production deployment remain unverified; do not describe this package as browser-tested.

# v0.2.6 — Profile photo, camera continuity, history, vehicle gallery and terrain (2026-11-08)

- Profile creation offers a circular image upload or opt-in webcam capture, with explicit camera teardown; UI copy uses **profile** rather than **guest profile**. API route names remain backward compatible.
- Settings roundel opens the right drawer using corrected CSS specificity. Action toolbar supports text, icon + text or icon only. Rotation is a highlighted, persistent toggle.
- BUILD/DRIVE preserves chosen orbit direction and zoom. Reset Camera remains explicit; previous automatic return-to-build resets were removed.
- Toolbar Undo/Redo, Cmd/Ctrl+Z/Shift+Z/Y and a searchable Cmd/Ctrl+/ shortcuts overlay. Bounded coalesced edit snapshots persist in local browser storage; this is not an engine-independent event-sourced history.
- Custom mobile save dialog for name/category/description, five fixed-perspective JPEG previews per save, local/cloud/public gallery with search, XL/M/S and float/left/right/bottom docking, metadata edits and local copy/delete.
- JSON/GLB export name includes creator, vehicle, ISO timestamp and release version; blueprint metadata includes screenshots where within strict server size cap.
- Wheel tire width, lateral offset and fore/aft axle anchors added to rendering and raycast controllers; terrain flat/bumps/hills/extreme/moon/beach and configurable size, solid/gradient/cloud/night sky. Beach water is **visual only**, not buoyancy or hydrodynamics.
- Optional local occupant GLB replacement for procedural passenger figures; named Driving/Sitting animations attempted when present. Occupant model binaries are retained in IndexedDB and not yet uploaded as server assets.
- Public SQLite gallery thumbnail and category added to public listing while keeping all private/profile/contact information protected. New storage tests cover public previews and 256 KiB blueprint limits.
- README includes About, Install, Roadmap, Ideas and LLM engineering handover sections. Standalone documentation is additionally packaged separately because the installed watcher only accepts exact application file paths.

**Verification:** local JavaScript syntax, storage/Nginx tests and watcher dry-run required. Browser camera/physics, server-side Flask tests, and live deployment have not been exercised in the authoring environment. Future: actual floor-teleport WebXR, physically animated doors/boarding, terrain tracks/splash/drag/buoyancy, mail recovery, provider AI generation.

---

# v0.2.5 — Full-stage workspace, guest profiles and three physics backends (2026-11-08)

- Full-browser 3D stage, with independently draggable, touch-resizable and minimizable action, tools, library, parameters and diagnostic windows.
- Profile and configuration drawers opened by fixed upper-right roundels, compact theme/font pills, editable accent and panel colors, plus independent theme/workspace JSON import/export.
- Fix Rapier browser 404 import with pinned ESM host and second-CDN fallback; offer Bullet/Ammo as third optional 3D raycast vehicle engine.
- Add passwordless guest identity with random server-verified secret, JSON recovery backup, avatar and editable profile, isolated SQLite vehicle ownership and opt-in public gallery.
- Add browser diagnostics and admin-scoped rotating Flask application-log viewer, plus protected provider model-list key tests for OpenAI, xAI and Meta.
- Add first-visit release history modal; separate credential forms to address Chromium form warnings.
- Watcher self-update v2.3.1 validates dedicated forms and runs an informational Postfix readiness check without altering server mail configuration.
- Preserve existing Flask/SQLite admin layout API and vehicle blueprints; password/email/phone verification and full AI generation remain future work.

# v0.2.4 — Switchable physics and grouped vehicle library (2026-11-08)

- Add selectable Cannon-es and Rapier WASM raycast-wheel physics, plus an explicitly non-physics kinematic reference.
- Use the same 60 Hz timestep, wheels, chassis dimensions and polygonal terrain for engine tests; lazy-load Rapier.
- Report physics-only step timings and FPS; offer a controlled 5–30 second driving benchmark and CSV export.
- Replace the left flat vehicle list with collapsed lil-gui category folders, searchable presets and active selection.
- Persist the chosen solver separately from geometric vehicle parameters in blueprint JSON / SQLite / IndexedDB.
- Preserve existing Flask/SQLite backend, authentication, AI integration contracts, and watcher deployment mechanics.

# v0.2.4 — Switchable physics and grouped vehicle library (2026-11-08)

- Add selectable Cannon-es and Rapier WASM raycast-wheel physics, plus an explicitly non-physics kinematic reference.
- Use the same 60 Hz timestep, wheels, chassis dimensions and polygonal terrain for engine tests; lazy-load Rapier.
- Report physics-only step timings and FPS; offer a controlled 5–30 second driving benchmark and CSV export.
- Replace the left flat vehicle list with collapsed lil-gui category folders, searchable presets and active selection.
- Persist the chosen solver separately from geometric vehicle parameters in blueprint JSON / SQLite / IndexedDB.
- Preserve existing Flask/SQLite backend, authentication, AI integration contracts, and watcher deployment mechanics.

# v0.2.3 — Watcher release visibility and durable diagnostics (2026-11-07)

- High-contrast terminal status, with red failed releases, green verified releases, and yellow origin-only partial outcomes. Release START/END banners include version, full date/time, duration, source ZIP, installed watcher build and exact log pathname.
- Default terminal output includes numbered ZIP validation, preflight, GitHub and server verification phases with elapsed times; use `--verbose` for command/output detail and `--color always` for terminal wrappers that do not expose TTY capability. The watcher prints its active build on startup to distinguish on-disk self-update from the old running process.
- Complete per-attempt plaintext logs under `.vehiclelab/logs/` retain each external command, output, return code and runtime; `--logs` lists recent files and `--tail` reads the latest. ANSI color codes never enter logs.
- Activate a reviewed watcher after an attempt even when the deployment phase fails, with persistent retry cooldown across restarts to avoid rapid retry storms. Move older superseded ZIPs to `updates/superseded/` without treating an already-deployed version as a new failure. Existing SHA-256 archive validation, clean Git preflight, atomic watcher backup, Flask rollback and SQLite preservation are maintained.
- Vehicle geometry, driving, backend API and schema remain unchanged. This version primarily makes deployment status observable.

# v0.2.2 — Repair missing deploy package in staged Flask tests (2026-11-07)

- Fix repeated server rollback during unit tests: `deploy/install.py` was not copied into `/opt/vehiclelab/releases/vX.Y.Z/`, although `tests/test_nginx_config.py` imports `deploy.install`. This was reproduced locally with the exact observed summary `Ran 5 tests` / `FAILED (errors=1)`.
- Stage `backend/`, `deploy/` and `tests/` together before invoking the Python test suite. Add a relocation regression that checks the real staged module can be imported, avoiding future false-positive local validation.
- Require the production Flask module to import explicitly after venv installation. Only skip local Flask tests when Flask itself is missing, not when backend imports are broken.
- Preserve existing watcher colors and per-iteration START/END logs, versioned deployment, Git integrity checks, rollback and persistent SQLite data.

# v0.2.1 — Release watcher telemetry and diagnostic-safe Flask installer (2026-11-07)

- Add colored INFO/PASS/WARN/FAIL terminal lines and distinct versioned START/END banners with full date/time, duration and final result for each ZIP attempt. Local log files remain clean, searchable text without ANSI escapes.
- On failed server-side Python tests, surface the real unittest output and traceback instead of only `CalledProcessError` exit 1. Log the successful regression suite summary.
- Keep SHA-256 integrity, Git working-tree safeguards, self-update, backup/rollback, SQLite data protection and existing procedural editor behavior.
- The underlying v0.2.0 remote test failure remains undiagnosed until the full server traceback is available. This release does not claim to have fixed an unknown test failure.

# v0.2.0 — Flask + SQLite server migration (2026-11-07)

- Add Flask / Gunicorn API and a server-owned SQLite database with WAL journaling and revision-controlled procedural blueprint CRUD.
- Add GLB upload/download with UUID-named asset storage outside the website root; SQLite stores asset metadata and SHA-256 hashes.
- Extend the compact lil-gui interface with volatile-memory SQLite token, remote save, refresh, load, revision-safe delete, and cloud GLB persistence, preserving IndexedDB workflows.
- Add bearer-token authentication, same-origin write guard, request size limits, credential-field rejection, and absence of embedded provider keys.
- Package versioned backend virtualenv, systemd unit, single-site Nginx `/api/` proxy, origin health checks and rollback of service/code/config without reverting persisted data.
- Include stdlib SQLite and Nginx configuration regressions plus Flask integration tests (the latter require Flask installed).
- AI generation endpoints are **501 placeholders**, not functional third-party integrations.

# v0.1.3 — Watcher bridge

- Upgrades the legacy five-file watcher to accept and deploy versioned backend releases.

---

## Earlier releases

# Meta Vehicle Lab — release notes

## v0.1.2 (2026-11-06)

- Diagnose public HTTPS problems before publishing, distinguishing pre-existing
  redirect loops from new failures caused by a release.
- Verify SHA-256 checksums in the live server directory after deployment.
- Preserve verified origin deployment when the public URL was already broken;
  report public HTTPS as UNVERIFIED without misrepresenting it as LIVE.
- Continue rolling back if server-side checksum validation fails or a previously
  healthy public endpoint regresses after deployment.
- Watcher 2.0.1 self-updates from the next single ZIP. No vehicle simulation
  or blueprint changes.

## v0.1.1 (2026-11-06)

- Add a versioned all-in-one UPDATE ZIP with application, self-updating watcher and one-time ZIP-contained bootstrap.
- Validate watcher SHA-256 and shell/Python syntax before installing it.
- Automatically back up and atomically replace the watcher, include it in
  GitHub release commits, and reload the watcher after successful deployments.
- Accept legacy nested setup archives without installing older unverified watchers.
- Retain valid release ZIPs for retry after GitHub/SSH failures instead of moving them to failed/.
- Preserve the v0.1.0 vehicle studio and its procedural-physics features.

## v0.1.0 (2026-11-06)

- Adopt index3 as the single-file Three.js, cannon-es and lil-gui prototype.
- Fix initial and return-to-build `selectedPart is not defined` exception.
- Put dynamically created API password inputs inside a real non-submitting form.
- Fix boarding and exiting while parked so the car remains at its physics location;
  passenger visibility and simulated chassis mass update without a world reset.
- Add parameterized urban, micromobility, robotics, agriculture, construction and
  mining vehicle presets and visual equipment variants; retained prior presets.
- Keep compact closed GUI folders and browser-side IndexedDB layout persistence.
- Retain orbit-follow driving camera, terrain, PBR materials, lights, GLB swap,
  export and explicit same-origin AI backend integration contract.
- Introduce version.json and SHA-256-manifest release ZIP intended for the
  secure watcher/GitHub/SSH staging workflow.

### Known limitations

- No production AI provider backend is included; AI/Tripo actions need server routes.
- Articulated machinery and passenger collisions are visual approximations.
- Different wheel arrangements and bike/track dynamics require dedicated physics.
- The imported model's binary is not part of JSON blueprint exports; save locally
  in IndexedDB or export a separate GLB.
- Browser rendering and remote deployment require validation in the target environment.
