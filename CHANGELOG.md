## v0.3.19 — November 10, 2026
- Added bounded heightfield terrain sculpt brush: Raise/Carve, radius/strength controls, map canvas and optional 3D painting, `[ ]` radius adjustments, wireframe sphere preview and per-stroke map history.
- Separated terrain plateau elevation from independent sea plane/sea altitude; beaches retain their previous sea. Vegetation, water and physics consume the same terrain height calculation, preserving BUILD/DRIVE editing.
- Map exports, local saves, owner-scoped cloud backups and vehicle blueprints carry a compact versioned 1.5-m sculpt height grid. v1/v2 map imports remain accepted; malformed height payloads are bounded and rejected.
- Reorganized Terrain, Sea, Sky, Ground and Vegetation lil-gui folders.
- Replaced 15 window-minimize glyphs with a centered currentColor SVG based on the supplied collapse icon. Added borders/shadows theme pills and normalized Configuration button typography/sizing. Imported older themes default to effects enabled.
- No new server libraries, database migrations, paid AI operations or watcher schema changes; live WebGL/physics and deployment remain unverified.

## v0.3.18 — November 10, 2026
- Duplicated 3D/map objects spawn above, not inside, their source; preserve original's rotation and selection, with translate gizmo on the clone.
- Exact axis-oriented Blender-like numpad navigation uses the present camera radius instead of re-framing far away. Includes camera mode, orthographic toggle, orbit, zoom, frame selected, local view, view menu and optional laptop emulation.
- Vehicle gallery cards show full-bleed photos, overlay labels and tooltipped accessible theme-colour SVG action icons; hover cycles multi-view photos every 500 ms and resets on exit.
- Existing customized top-row camera shortcuts migrate where applicable. New features are client-side only; existing private data, API routes, paid integrations, database schema, deployment watcher and dependencies unchanged.
- Static regressions and isolated browser tests run locally; production WebGL/input testing remains required.

## v0.3.17 — November 9, 2026
- Font/theme changes now reach all lil-gui controllers. Searchable non-modal font gallery previews editable sample text in a grid and optionally enumerates installed local fonts with user permission.
- Map/object-specific undo/redo prevents accidental vehicle undo and BUILD-mode switching. Terrain/map changes refresh the physics adapter while retaining DRIVE layout and current car pose/velocity.
- G/R/E choose transform gizmo modes only; Shift+D clones the selection without cursor-follow grabbing or rotating the original. A gizmo-release guard prevents erroneous source re-selection.
- Strong physical rear-wheel parking brake in each engine, toggled by Shift+B or the Actions button; chassis can still slip on steep surfaces and is never immobilized kinematically.
- Editable, validated/persisted keyboard shortcuts with defaults recovery, duplicate/red errors, and import/export JSON. Default camera reset changes from R to Shift+R to eliminate conflict with object rotation.
- No backend API, database schema, AI provider, profile, model asset, server dependency or watcher changes. Browser/physics/device acceptance must still be performed on HTTPS deployment.

## v0.3.16 — November 9, 2026
- Configuration → Windows & workspace: BUILD and DRIVE selector pills, 14 named window visibility controls, and mode-specific visible/minimized state.
- Apply saved BUILD layout on startup; apply DRIVE/BUILD layouts consistently when switching modes, no longer bypassed by the old hide-editor switch.
- Include both mode presets in workspace JSON v2 export/import; accept existing position-only v1 exports.
- Preserve prior window positions, blueprints, vehicle editor state, profile data, AI APIs, backend and SQLite without new requirements.

## v0.3.15 — November 9, 2026
- AI-generated reference images auto-save privately in optimized JPEG form with authenticated SQLite media IDs and thumbnails.
- The My Media cloud car list returns saved hero previews rather than an unrelated SVG placeholder.
- BUILD and DRIVE support separately persisted visible/minimized panel presets in Configuration.
- The map exposes World edge mode in the toolbar (bounce/uphill/wrap/connected cells/cliff).
- AI image and Lux3D buttons show running state; 3D jobs support explicit 1–3 sequential billed batches with in-page queue status and cancellation of pending tasks.
- No user identities, API keys, paid prompts, or private media are published by these features.
- Batch execution requires the browser tab to remain open; the queue is not a durable server worker.

# v0.3.14 — Radio, personal media and terrain-aware autopilot (2026-11-09)

- Personal audio library with validated uploads, ID3/MP4 metadata and cover art, SQLite playlists, native HTTP Range streaming, short-lived signed stream URLs, and owner isolation.
- Compact floating radio with mixed-track playlists, shuffle-track/playlist, repeat-one, pause, stop, previous/next, volume. Empty admin-only demo station (no bundled copyrighted audio).
- Media browser adds Music and Public tabs. Vehicle gallery cloud cards gain explicit Publish/Unpublish; redundant preset-pane layout lists hidden.
- Material Studio automatically targets selected map objects, with in-place color updates.
- Optional terrain-aware autopilot uses bounded local pathfinding to avoid hills, obstacles and terrain edges. Live physics validation required.
- No new 3D assets or licensed music. Backend adds radio.py and mutagen dependency. Cloud user data is preserved.

# v0.3.13 — Edge-safe worlds, optional Umami, personal media and Quest driving (2026-11-09)

- Async, non-blocking Umami page/event analytics, fail-open with privacy-safe event names.
- Configurable physical world borders, steep uphill limit, opposite-edge wrap, and an editable bounded nine-cell landscape. Save/reload cell maps privately; no claimed infinite streaming support.
- Cars/Models/Images/Maps media window with search, local/device and authenticated SQLite personal storage. Thumbnail route for personal images; no public sharing without explicit vehicle publication.
- WebXR Quest controller mapping for seated driving, analog controls, horn, exit, recenter, camera, reset; requires actual hardware acceptance testing.
- Added local regression tests for owner isolation, map persistence, world/XR contracts. Existing blueprint and database files retained; SQLite adds `user_media` table.

## v0.3.12 — Deduplicate loaded chassis GLBs (2026-11-09)

- Fix repeated reimports: every save/load or cloud restore used to assign a fresh random chassis-library ID, even when the GLB binary was unchanged.
- SHA-256 of the GLB identifies identical assets; reuse the existing decoded scene and gallery entry on later imports and layout loads.
- Collapse already duplicated legacy IndexedDB chassis cards without deleting any existing binary or altering a user's layouts, gallery, profiles or API keys.
- Models with the same filename but different file content remain separate. No Flask migration; no changes to vehicle physics.
- Requires live browser acceptance; ZIP/watch validation cannot prove IndexedDB runtime behavior.



## v0.3.11 — Editable generated-shell alignment, white references and cloud GLB recovery (2026-11-09)

- Replace the fixed imported-body offset with front/rear compatible local transforms: X/Y/Z position and orientation, uniform scale and reset to wheel-plane fit.
- Add direct GLB and reference-image downloads without stage resizing; request a clean white seamless front-left three-quarter AI reference.
- Read and validate cloud GLB **before** switching the active vehicle; preserve a local IndexedDB cache keyed by the private server asset ID, with explicit network failure diagnostics.
- Preserve existing Flask/SQLite blueprints, private/public library data, binary files and physics separation.
- Local source and database tests pass; production CDN, large-model streaming and actual browser rendering are not independently verified.

# v0.3.10 — Avatar scale 2.0 and Lux3D large-reference handling (2026-11-09)

- Increase imported avatar scale control maximum from 1.6 to 2.0.
- Automatically validate and resize/quantize large generated chassis-reference images on the Flask server, using Pillow, before triggering any potentially billable Lux3D task. Retain a preview of the exact optimized reference. Allow PNG/JPEG/WebP source images up to 20 MiB encoded, enforce 24 MP and 2 MiB output limits.
- Add non-billable, profile-authenticated Lux3D reference-optimization endpoint. Recheck on the backend at paid task creation; never log or persist API keys or image payloads.
- Add regression coverage for image formats, oversized source, color transparency and invalid input, plus explicit release-version consistency check.

# v0.3.9 — Version badge consistency (2026-11-09)

- Fix hardcoded v0.3.7 badge in v0.3.8 release. Display the same current version constant used elsewhere in the app.
- Restore v0.3.8 in the application release-history overlay.
- No functional vehicle, profile, backend or database changes.

---

# v0.3.8 — Meta Muse Image and self-contained chassis AI studio (2026-11-09)

- Enable official Meta Muse Image (`muse-image-1.0`) image generation and reference-guided editing via the same Meta Model API bearer key used by the successful model-list test. Keep image requests profile-scoped and the credential in memory only.
- Chassis Workshop now contains a visible 3D-design brief, four editable concept starters, image-provider selection (Meta/OpenAI/xAI), in-panel key entry, isolated wheel-free body capture/upload and actual image preview; generation uses the visible brief rather than an unexplained hard-coded generic prompt.
- Provide reviewed concept-image → Lux3D G1/G1-Turbo workflow directly in Chassis Workshop, with configurable style/region, read-only key test, explicit paid-task authorization, visible polling status, and same-origin automatic GLB import that retains procedural wheels and physics.
- Extend the compact wheel image-provider dropdown to Meta. Select the most recently tested image provider for later image generation; accept bounded provider image URLs from the verified xAI image CDN when the API does not return embedded base64.
- Regression coverage checks duplicate IDs, form nesting, Meta image generation/edit request routing, chassis-workshop control wiring and retained Flask/SQLite functionality. No database migration, no installation of third-party server packages.
- **Limits:** Actual provider image generation, billing, Lux3D conversion and imported GLB fit cannot be tested without the user's API keys and live browser. Successful read-only key tests do not guarantee image model entitlement.

---

# v0.3.7 — interpolated orbit cameras and stable grass (2026-11-09)

- FIX: Orbit-follow now translates both camera and OrbitControls target by the same delta each frame, keeping the selected angle and zoom while following the moving car. Free stays stationary; driver stays vehicle-attached.
- FIX: Store previous/current fixed-physics poses and interpolate rendered body and wheel positions to reduce visual micro-jitter at otherwise smooth frame rates.
- FIX: Smart/chase terrain lift is temporary, not baked into OrbitControls pitch; add horizontal/vertical/clearance response controls.
- FIX: Replace the periodically teleported grass circle with deterministic world-coordinate cells. Neighboring cells retain identical blade locations as the car crosses tile boundaries.
- No backend or database changes. Live CDN-backed physics/browser driving is not independently verified in this environment.

---

# v0.3.6 — camera controls, dynamic parked vehicles, object editing, chassis library (2026-11-09)

- Add stationary/free camera, terrain-aware following camera with orbit+zoom and mode label; remove top camera. Restore full vehicle pose at world origin on demand.
- Autopilot scripted oval/figure-eight/wander routes with manual interruption and bounded target area; not a navigation/obstacle-avoidance engine.
- Give non-controlled scene vehicles true dynamic collider masses in Cannon, Rapier and Ammo and synchronize their poses after impacts. Only the selected car accepts input.
- Correct wheel spin visual direction and flip right-side imported GLB wheel display; preserve solver suspension positions.
- Chassis workshop: imported shell library with isolated GLB previews and IndexedDB persistence, procedural restoration, configurable rake and roof width.
- Per-seat XYZ rig offsets and sitting clip priority; hollow floor / chassis sill for visible legroom.
- Fix split server-log layout, lil-gui defaults, header hover and resize grips; preserve drive-map/inspector visibility after collider rebuilds; bridge parts selected as a group; cursor-based G/R/E transforms and Esc cancel.
- GPU-instanced near-field grass with distant culling and configurable ground roughness.
- No database migration. Offline validation only; physics simulations and avatar positions require real browser acceptance.

---

# v0.3.5 — wheel GLB previews, alignment and physics API correction (2026-11-09)

- Fix Rapier initialization crash: use the documented `setIndexForwardAxis` setter rather than a getter-only property.
- Align Ammo engine-force direction with blueprint forward (+Z); reduce brake impulse. Physics behavior still needs live driving checks.
- Detect wheel GLB axle from model bounds, orient it to X, then fit wheel diameter/width in normalized local space.
- Replace raw filename wheel buttons with a preview-thumbnail library. Provide explicit 90° X/Y/Z corrections and auto-align; persist asset metadata in IndexedDB.
- Make wheel AI generation a first-tile action when a key is ready, with an inline image preview; keep potentially billable 3D generation opt-in.
- Clarify the administrator token location and separate it from creator profiles and AI provider credentials.

---

# v0.3.4 — Compact map UI, responsive edits, scene vehicles, sound presets (2026-11-09)

- Preserve each floating window's minimized state while entering and leaving DRIVE. Reduce header/tool rail sizes, compress map controls to icons, and dock editable map settings above the bottom edge with collapsible panel.
- Make Shift+A a pointer-near, searchable object palette rather than a full-screen modal. Add Shift+D duplicate, X delete, G move, R rotate, and E scale for selected objects; changes to numeric Y may position static geometry below terrain.
- Separate lightweight map-object collider updates from terrain/vegetation regeneration, and throttle minimap redraws. Resizing the map changes the visible area while retaining world scale; zoom remains explicit.
- Add engine sound preset import/export JSON and immediately update active WebAudio voices when editing lil-gui parameters. Include additional impact/damage cues based on vehicle motion.
- Add a selectable scene-vehicle list and plus action on gallery cards. Multiple vehicles can be placed visibly; **only one is actively driven** while others have static collision representations. Simultaneous multi-driver simulation is not implemented.
- Tighten gallery overlays, compact wheel workshop field layout and AI entry point, add button hover feedback; document known limits. Full browser driving, multiple vehicles, GPU rendering, and audio still require live acceptance testing.
- Regression gate: 38 local tests (12 Flask-dependent tests skipped), Node JavaScript syntax, archive checks and release watcher dry-run. No live server deployment claimed.

---

# v0.3.3 — Rapier/driver-state repairs, audio, AI wheel workflow and editor ergonomics (2026-11-09)

- Use a pinned compatible Rapier ESM build, correct up/forward axes, wheel-local/world transforms and wheel force tuning; include staged failure messages. Real Rapier drive behavior remains **browser-unverified**.
- Swap procedural wheel visuals without resetting passenger rigs; maintain camera state during BUILD/DRIVE; increase collider coverage over roof. Chassis and full-car reference captures fit model bounds in an isolated offscreen studio.
- Add adjustable procedural WebAudio engine preset synthesis (electric, petrol, diesel, turbine), live noise/filter/harmonic controls, braking and impacts.
- Compact object-inspector XYZ and dimension controls with active range sliders, 1–7 camera views and +/- zoom. Map undo/redo, higher-zoom vector contours, non-scaling map canvas and environment edits without reconstructing occupants.
- Add chassis/seat/dashboard/lamp editing groups. Wheel workshop offers first-tile AI actions and inline provider keys; route Lux3D completed wheel GLBs to selected axle. OpenAI/xAI image reference generation/edit endpoints added with guest authorization, input size caps and no key storage; these are potentially billable. Meta image generation and Tripo 3D remain explicitly unimplemented.
- Validation: Node JavaScript syntax, Python syntax, stdlib tests and watcher ZIP checks. Real WebGL driving, sound playback, avatar animation, GPU rendering and paid provider calls are not independently tested.

---

# v0.3.2 — Precision terrain and physics object editing (2026-11-09)

- 1:1 square precision map now supports wheel zoom centered at pointer, pinch-to-zoom, explicit +/- and Fit, right/middle drag and hand pan, selectable and movable objects, dynamic coordinate grid and vector-outline footprints. Relief/contour raster is a background; geometry stays vector-precise.
- Blender-inspired **Shift+A** searchable primitive palette places objects on the camera-visible terrain, checks the chassis and other obstacle footprints, and opens a floating object inspector. Click mapped or 3D objects to select; Three.js TransformControls offers position/rotation/scale. Explicit inspector fields include XYZ, dimensions, angle, color, texture, mass, friction and bounce.
- A shared course-object record drives visual geometry, topographic map and physics adapters. Static/dynamic/no-collision modes are reflected in Cannon-es, Rapier and Ammo/Bullet. Non-box objects use documented box collision approximations. Dynamic positions are captured when leaving DRIVE, and vehicle pose is preserved while editing a map during DRIVE.
- Area/freehand polygon and open smoothed line modes create sculpted hills, dunes, grass/sand patches, water outlines, tree clusters and hedges. Puddle detection and surface grip use the actual edited polygon/path footprint rather than a generic circle.
- Test-map JSON upgraded to `vehiclelab-testmap/v2`, with backward-compatible v1 import. Existing layouts and Flask/SQLite storage are unchanged. Undo/Redo history retains course object descriptions.
- Tests: JS syntax, local Python storage/deploy regression suite and Node geometry/projection assertions, headless Chromium offline layout checks at desktop/tablet/mobile widths. **Full WebGL engine driving and server deployment have not been independently tested.**

---

# v0.3.1 — Lux3D reference workflows, direct GLB import, and precision test maps (2026-11-09)

- Lux3D chassis generator now offers an explicit isolated body-only 3/4 reference capture (no wheels or passengers), photo upload, preview, clearing, and a clearly controlled include-reference checkbox. Capture uses an offscreen render target without resizing the main stage.
- Completed tasks offer **Import into Vehicle Lab**, optionally automatic. An owner-authenticated same-origin Flask endpoint retrieves the finished task's GLB or safely extracts the GLB from a ZIP without re-uploading. A limited approved-provider CDN list, blocked private-network addresses, payload validation and 80 MiB limits restrict downloads. Official download links remain as a fallback.
- Drive test map remains **square at any window size**; a left-side icon rail provides drawing tools. The map offers topographic shaded-relief/contour mode or geometric-plan mode, precise oval/circle/square/line footprints, a 10m grid, and a live coordinate readout.
- Editing or loading a map during DRIVE preserves car position, orientation and linear velocity while terrain and obstacle physics colliders are reconstructed. Brief physics reconstruction may interrupt motion. A full running-frame browser acceptance pass is still required.
- Better administrator-token error text distinguishes provider AI keys, profile identity, and admin-only server logs.
- Tests: JavaScript syntax; desktop Chromium CSS/DOM checks for a 1:1 map at multiple window widths; Python storage and Nginx regressions. New Flask import endpoint tests require the server's pinned Python environment; **no live Lux3D generation or real CDN transfer was tested**.

---

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
