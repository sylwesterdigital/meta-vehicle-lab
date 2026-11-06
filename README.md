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

## Deploy via release watcher

The repository-root `watcher-meta-vehicle.sh` runs on the development Mac. It
only watches `updates/*.zip`, not other folders. A release must contain:

```
manifest.json                # version, changes[], SHA-256 map
app/index.html              # single-page app
app/version.json            # matches the manifest version
app/README.md
app/CHANGELOG.md
app/.gitignore
watcher-meta-vehicle.sh   # optional, checksum-verified self-update
bootstrap.py              # optional one-time updater; never executed by the watcher
```

Archive filenames must contain matching `vX.Y.Z`. Versions must increase
strictly beyond the last confirmed deployment. The watcher validates all
checksums, archive paths, imports, JavaScript syntax and core app features.
It refuses dirty tracked files, wrong Git origins, divergent main branches,
server version downgrades and symlinks in deployment targets.

From the cloned repository root, with Python 3, Node.js, Git, SSH and SCP:

```sh
chmod +x watcher-meta-vehicle.sh
mkdir -p updates
cp META_VEHICLE_LAB_UPDATE_v0.1.2.zip updates/
./watcher-meta-vehicle.sh --dry-run
./watcher-meta-vehicle.sh --once
# or continuous operation: ./watcher-meta-vehicle.sh
```

Required connection: GitHub SSH origin `git@github.com:sylwesterdigital/meta-vehicle-lab.git`
(branch `main`), and key-based SSH using `ssh -p 333 root@vehiclelab.xyz`
for the web root `/var/www/vehiclelab.xyz`. The watcher defaults to port 333;
override via `VEHICLELAB_SSH_PORT=...` if needed. Before deployment, the destination vhost
must already serve `https://vehiclelab.xyz/` with a valid certificate.

Watcher behavior: verified release -> GitHub commit/push + verify HEAD ->
checksum-checked server staging -> backup the two public files -> replace
only `index.html` and `version.json` -> public HTTPS check -> record success.
It leaves every other server file in place. A failed public check triggers
rollback of those two files. GitHub may be ahead of the server if deployment
fails after push; re-drop the failed ZIP after fixing the issue. Local logs
are in `.vehiclelab/logs/`, processed ZIPs go to `updates/processed/`, and
invalid ZIPs go to `updates/failed/`. Failed Git or SSH deployments leave
the verified ZIP in `updates/` for retry (60-second cooldown in watch mode). The watcher does not upload secrets,
credentials, arbitrary untracked content or IndexedDB/browser data.

**Testing status:** Source syntax and ZIP/watcher dry-run were checked before
release. Live browser use, authenticated GitHub push, and deployment to the
remote host have not been verified from this environment.

## ZIP-only watcher updates (v2)

Drop a `META_VEHICLE_LAB_UPDATE_vX.Y.Z.zip` into `updates/` and the watcher
validates the application files and the optional `watcher-meta-vehicle.sh`
against `manifest.json`. On a successful deploy it installs the verified
watcher atomically, retains a local backup and reloads the watcher when running
continuously. The older `META_VEHICLE_LAB_RELEASE_*.zip` files still work.
Old-format `META_VEHICLE_LAB_SETUP_*.zip` files with a nested release ZIP are
recognized; their older, unchecksummed watcher is never installed.

**One-time bootstrap:** Legacy watcher v1 cannot update itself because it rejects
watcher-containing ZIPs. To install v2 once, extract only the watcher script
from the first trusted UPDATE ZIP in `updates/` and run `bash -n` on the file
before replacing the old watcher. Thereafter only drop UPDATE ZIPs into
`updates/`. Self-update integrity checks do not authenticate a release
producer, so only accept ZIPs from a trusted source.

For the v1 → v2 upgrade, download **only** the UPDATE ZIP into `updates/` then
run this one-time command in the repository root (with the old watcher stopped):

```sh
unzip -p updates/META_VEHICLE_LAB_UPDATE_v0.1.2.zip bootstrap.py | python3 - updates/META_VEHICLE_LAB_UPDATE_v0.1.2.zip
```

The bootstrap validates checksums and watcher shell syntax, keeps a backup,
installs the new watcher, runs a complete dry-run and then attempts deployment.
For all later updates simply drop new versioned ZIPs into `updates/`.

## Public HTTPS diagnosis

The watcher now probes the public HTTPS endpoint before changing production files.
If the URL already fails (for example, a 301 redirect loop), the watcher
confirms the SHA-256 of deployed files on the SSH origin, reports **PUBLIC
HTTPS NOT VERIFIED**, and does not undo an otherwise verified upload.
If HTTPS worked before deployment and fails afterward, the watcher rolls
back the two deployed files. This does not automatically repair DNS, Nginx,
Cloudflare SSL/TLS mode, or redirect rules. Fix those separately.
