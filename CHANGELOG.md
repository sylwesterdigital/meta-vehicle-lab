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
