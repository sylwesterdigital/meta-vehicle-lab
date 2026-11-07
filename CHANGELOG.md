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
