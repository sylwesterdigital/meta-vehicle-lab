> **v0.2.2 server test fix:** The installer now copies `deploy/` into the versioned backend release, together with `backend/` and `tests/`. This resolves the previously reproduced `ModuleNotFoundError: No module named 'deploy'` failure (five tests, one error). A relocation regression checks the staged test imports before any deployment. Flask imports are also checked explicitly after installation. Existing data and prior release safeguards remain intact.

> **v0.2.1:** The watcher logs a dated START/END banner, elapsed seconds and colored terminal statuses. Failed remote Python tests now include their real unittest traceback in the release log. The first v0.2.0 server-side test failure could not be reproduced without its server traceback; deployment still aborts safely if tests fail.

# Meta Vehicle Lab — Flask + SQLite v0.2.2

The 3D procedural studio remains one `index.html` using pinned Three.js, cannon-es and lil-gui. A Flask 3.1 API and SQLite database now provide persistent server layout storage, revision-controlled updates and GLB asset uploads. IndexedDB local saves and JSON/GLB export are unchanged.

## Architecture

- **Frontend:** `index.html` (served by Nginx in production; Flask can also serve it in local development), procedural vehicles, terrain, lights, physics and orbit camera.
- **Backend:** `backend/app.py` (Flask routes), `backend/storage.py` (stdlib SQLite transactions), `backend/wsgi.py` (Gunicorn entrypoint).
- **SQLite:** `/var/lib/vehiclelab/vehiclelab.sqlite3` on the server; local default `.data/vehiclelab.sqlite3`. Model assets stored separately under `assets/` with SHA-256 metadata in SQLite. This directory is not in the webroot and never copied into Git.
- **Server:** versioned `/opt/vehiclelab/releases/v0.2.2`, symlink `/opt/vehiclelab/current`, `vehiclelab-flask.service` bound to `127.0.0.1:8766`; Nginx proxies only `/api/` to Flask and continues serving the frontend directly.
- **Authentication:** Bearer token required for all layout, asset and placeholder AI endpoints. It is generated on first install in `/etc/vehiclelab/vehiclelab.env` (root-owned, www-data readable). Enter it in lil-gui → **12 · SQLite server → Access token**, then choose **Refresh SQLite**. The token is never persisted in the browser, the JSON blueprint or SQLite.

## API

| Route | Action |
| --- | --- |
| `GET /api/health` | Public JSON readiness and release version; checks SQLite |
| `GET /api/layouts` | Authenticated recent layout list |
| `POST /api/layouts` | Create a blueprint record |
| `GET /api/layouts/<uuid>` | Retrieve blueprint, revisions and asset ID |
| `PUT /api/layouts/<uuid>` | Update only with matching `revision`; conflicts return 409 |
| `DELETE /api/layouts/<uuid>` | Delete only with matching `revision` |
| `POST /api/assets` | Upload validated GLB (up to 80 MiB) |
| `GET /api/assets/<uuid>` | Download GLB |

AI image/Tripo endpoints deliberately return `501 Not Implemented` until provider adapters and policy/rate limiting are implemented. A working Flask/SQLite backend is not equivalent to a configured AI image-generation service.

## Local development

```bash
cd /Users/smielniczuk/Documents/works/meta-vehicle-lab
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
export VEHICLELAB_API_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
.venv/bin/python -m backend.app
```

Open `http://127.0.0.1:8766/`. The separate UI/server access-token entry must match the exported value. Avoid binding the development process to a public interface.

Check the SQLite/core installer tests before deployment:

```bash
python3 -m unittest discover -s tests -v
```

Flask route tests require Flask to be installed; without it they are explicitly skipped. Production installs exact versions of Flask and Gunicorn through a release-specific virtualenv and checks its `/api/health` endpoint before switching Nginx.

## Deployment: two automatic ZIP phases

The *existing* watcher v2.0.x allows only five frontend application files. It cannot verify the new backend source in a ZIP until it has self-updated. Accordingly, drop **both** versioned ZIPs directly into `updates/` while the watcher is running continuously:

1. `META_VEHICLE_LAB_UPDATE_v0.1.3.zip`: compatibility release, upgrades watcher from v2.0.x to v2.1.0, deploying the existing frontend.
2. `META_VEHICLE_LAB_UPDATE_v0.2.0.zip`: the Flask + SQLite application, tests and systemd/Nginx installer.

The first update runs, the continuous watcher restarts into its new version, and the second update is then validated and deployed. **Do not run the old watcher with `--once` against both ZIPs**: it cannot understand the second archive until it restarts. If you use `--once`, run it separately for each version.

Requirements: Mac Git/SSH/Node/Python, remote Ubuntu Python 3 + `python3-venv`, network access to PyPI for pinned packages, Nginx with an existing `vehiclelab.xyz` HTTPS site and SSL certificate, and systemd. The watcher logs failures and retains valid ZIPs for retry. It will not install an entire Python runtime or alter any other virtual host. It never places API secrets or database files in Git.

Inspect the generated access token after successful deployment on **your own terminal**:

```bash
ssh -p 333 root@vehiclelab.xyz 'grep ^VEHICLELAB_API_TOKEN= /etc/vehiclelab/vehiclelab.env'
```

Keep it private. Enter only the value after `=` in lil-gui. Do not post the output to GitHub or chats.

Useful checks:

```bash
ssh -p 333 root@vehiclelab.xyz 'systemctl status vehiclelab-flask --no-pager; ls -lh /var/lib/vehiclelab/vehiclelab.sqlite3'
curl --noproxy '*' -fsS https://vehiclelab.xyz/api/health
```

## Security / limits

- SQLite uses parameterized SQL and WAL journaling. Revision numbers protect against unintended overwrites. A server API token gates reads as well as writes; there is **no user account separation** in this prototype.
- Browser keys and token remain in memory and are never included in blueprint exports or server saves. Server rejects credential-like property names inside blueprint objects.
- Uploaded GLBs are checked for a valid GLB version-2 header and advertised byte length. They are stored by random UUID outside the website directory.
- Assets are not automatically garbage-collected when a layout is deleted. There is no account-level ownership, billing, audit logging, rate limiting or AI provider implementation yet.
- Nginx install patches **only** the HTTPS `vehiclelab.xyz` server block, retains a backup, and refuses ambiguous/conflicting configurations. Only application, own service, own API block and own release symlink are rollback targets. Existing SQLite data is intentionally never rolled back.

The automated tests performed for this release cover local JavaScript syntax, manifest/checksum validation, Python syntax, SQLite persistence/concurrency, and safe Nginx vhost insertion. Live browser integration and actual Ubuntu/GitHub deployment must be verified after deployment. See `CHANGELOG.md`.

---

## Existing procedural editor reference

# Meta Vehicle Lab

A single-page procedural Three.js + cannon-es vehicle editor. Includes an editable
front/cabin/rear/equipment assembly, lil-gui controls, PBR paint + noise finishes,
RaycastVehicle driving, orbit-follow camera, elevated terrain, vehicle lights,
procedural occupants, IndexedDB layout saves, JSON/GLB export and GLB visual replacement.

## Local use

Start a static web server in the repository root:

```sh
python3 -m http.server 8080
```

Open http://localhost:8080/ in Chrome, Safari or another recent WebGL browser.
An internet connection is required for the **pinned** Three.js v0.180.0,
cannon-es v0.20.0, and lil-gui v0.21.0 dependencies from jsDelivr.

Use the vehicle list at left. Select BUILD/DRIVE from the header. Drag or touch
orbit controls to rotate around the vehicle in both modes, scroll or pinch to
zoom. Arrow Up/Down accelerate/reverse, Left/Right steer, Space brakes. The
on-screen joystick and brake button work with touch. Auto-rotation is only
active in BUILD and can be toggled from the header. Folders start closed.

Use Save layout for browser IndexedDB. Export JSON for the portable procedural
blueprint (the imported GLB binary is *not* embedded in the JSON). Export an
assembled GLB using the GLB folder. Imported GLBs replace the **visual body**
while physics, wheels, doors and occupants remain controlled by the procedural
blueprint. Vehicle classes beyond cars are intentionally conceptual: machinery
attachments are not articulated or simulated with dedicated colliders, and
two-wheel/track-specific physics are simplified with raycast-wheel chassis.

The AI/Tripo controls are integration hooks, not a working AI service. Configure
an authenticated, appropriately rate-limited same-origin backend implementing:
`POST /api/vehicle/generate-image`, `POST /api/vehicle/tripo/start`, and
`GET /api/vehicle/tripo/status/{task_id}`. The backend must proxy GLB downloads
on the same origin. API keys entered in the UI are kept in memory and sent to
that backend per request; they are not saved in JSON or IndexedDB. Do not enter
private keys on a host that is not fully under your control.

