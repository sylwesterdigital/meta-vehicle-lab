#!/usr/bin/env bash
# META VEHICLE LAB self-updating ZIP watcher. Install at the root of meta-vehicle-lab.
# Usage: ./watcher-meta-vehicle.sh [--dry-run|--once|--status|--interval 3]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 - "$ROOT" "$@" <<'VEHICLE_WATCH_PY'
import argparse
import datetime as dt
import traceback
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

ROOT = Path(sys.argv[1]).resolve()
sys.argv = [sys.argv[0]] + sys.argv[2:]
UPDATES = ROOT / 'updates'
STATE = ROOT / '.vehiclelab'
REPO_SSH = 'git@github.com:sylwesterdigital/meta-vehicle-lab.git'
SSH_HOST = os.environ.get('VEHICLELAB_SSH_HOST', 'root@vehiclelab.xyz')
SSH_PORT = os.environ.get('VEHICLELAB_SSH_PORT', '333')
WEBROOT = '/var/www/vehiclelab.xyz'
SITE = 'https://vehiclelab.xyz/'
PUBLISH = ('index.html', 'version.json')
APP_FILES = frozenset(('index.html', 'version.json', 'README.md', 'CHANGELOG.md', '.gitignore'))
BACKEND_FILES = frozenset((
    'backend/__init__.py','backend/app.py','backend/storage.py','backend/wsgi.py',
    'backend/requirements.txt','deploy/install.py','deploy/vehiclelab.service',
    'tests/test_storage.py','tests/test_flask_api.py','tests/test_nginx_config.py'
))
ALLOWED = APP_FILES | BACKEND_FILES

def release_files(stage):
    return APP_FILES | (BACKEND_FILES if (stage/'backend/app.py').is_file() else frozenset())

def is_flask(stage):
    return (stage/'backend/app.py').is_file()
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
VALID_ZIP_RE = re.compile(r'^META_VEHICLE_LAB_(?:RELEASE|UPDATE|SETUP)_v\d+\.\d+\.\d+(?:_[A-Z0-9]+)*\.zip$')
WATCHER_BUILD = '2.3.0'
RESTART_REQUESTED = False
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
LOG_FILE = None
# Terminal rendering and durable plaintext release logs are intentionally separate.
# --color always helps when terminals are wrapped by an IDE or log viewer.
VERBOSE = False
COLOR_MODE = 'auto'
ANSI = {
    'INFO': '\033[1;36m',      # cyan
    'STEP': '\033[1;34m',      # blue
    'DETAIL': '\033[2;37m',    # subdued (verbose output)
    'PASS': '\033[1;32m',      # green
    'WARN': '\033[1;33m',      # yellow
    'FAIL': '\033[1;97;41m',   # high-contrast white on red
    'START': '\033[1;97;44m',  # white on blue
    'SUCCESS': '\033[1;97;42m',# white on green
    'PARTIAL': '\033[1;30;103m',# black on yellow
}
RESET = '\033[0m'

def use_color():
    if COLOR_MODE == 'never': return False
    if COLOR_MODE == 'always': return True
    if os.getenv('NO_COLOR') is not None: return False
    if os.getenv('FORCE_COLOR') not in (None, '', '0'): return True
    if os.getenv('CLICOLOR_FORCE') not in (None, '', '0'): return True
    return sys.stdout.isatty() and os.getenv('TERM','')!='dumb'

def paint(text, level):
    return (ANSI.get(level,'') + text + RESET) if use_color() and level in ANSI else text

def clock():
    return dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z').rstrip()

def emit_block(lines, color):
    raw='\n'.join(lines)
    print(paint(raw, color),flush=True)
    if LOG_FILE:
        with LOG_FILE.open('a',encoding='utf-8') as f:
            f.write(raw+'\n')

def banner(phase, version, *, filename='', mode='', duration=None,
           status='SUCCESS', details=''):
    line='━'*72
    if phase=='START':
        lines=['',line,
               f'  ▶ RELEASE START  v{version}  |  {clock()}',
               f'  ZIP: {filename}  |  MODE: {mode}  |  WATCHER: v{WATCHER_BUILD}',
               f'  FULL LOG: {LOG_FILE}',line,'']
        emit_block(lines,'START')
        return
    elapsed=f'{duration:.1f}s' if duration is not None else '?'
    label={'SUCCESS':'SUCCESS / LIVE', 'FAILURE':'FAILED / RELEASE NOT LIVE',
           'DRY RUN':'DRY RUN / VALIDATION ONLY',
           'PARTIAL':'ORIGIN DEPLOYED / PUBLIC NOT VERIFIED'}.get(status,status)
    theme='FAIL' if status=='FAILURE' else 'PARTIAL' if status=='PARTIAL' else 'SUCCESS'
    lines=['',line,
           f'  ■ RELEASE END  v{version}  |  {clock()}',
           f'  RESULT: {label}',
           f'  DURATION: {elapsed}',
           f'  FULL LOG: {LOG_FILE}']
    if details:lines.append(f'  DETAILS: {details}')
    lines.extend([line,''])
    emit_block(lines,theme)

class ReleaseError(Exception):
    pass

class ArchiveError(ReleaseError):
    """Invalid ZIP: quarantine, rather than repeatedly attempting it."""

def log(message, level='INFO'):
    now=dt.datetime.now().astimezone()
    for fragment in str(message).splitlines() or ['']:
        terminal = f'{now:%H:%M:%S} [{level:6}] {fragment}'
        print(paint(terminal,level),flush=True)
        if LOG_FILE:
            with LOG_FILE.open('a',encoding='utf-8') as f:
                f.write(f'{now:%Y-%m-%d %H:%M:%S%z} [{level:6}] {fragment}\n')

def command(args, *, cwd=None, timeout=120, stdin=None, check=True):
    argv=[str(x) for x in args]
    started=time.monotonic()
    safe_cmd=shlex.join(argv)
    if VERBOSE:
        log('$ '+safe_cmd+(f'  [cwd={cwd}]' if cwd else ''),'DETAIL')
    try:
        p=subprocess.run(argv,cwd=cwd,input=stdin,text=True,capture_output=True,
                         timeout=timeout,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
    except subprocess.TimeoutExpired as exc:
        raise ReleaseError(f'{argv[0]} timed out after {timeout}s') from exc
    elapsed=time.monotonic()-started
    if LOG_FILE:
        with LOG_FILE.open('a',encoding='utf-8') as f:
            f.write(f'COMMAND START {clock()} {safe_cmd} [cwd={cwd}]\n')
            f.write((p.stdout or '')+(p.stderr or '')+'\n')
            f.write(f'COMMAND END exit={p.returncode} duration={elapsed:.2f}s\n')
    if VERBOSE:
        log(f'Command exit={p.returncode} elapsed={elapsed:.2f}s: {argv[0]}','DETAIL')
        output=((p.stdout or '')+'\n'+(p.stderr or '')).strip()
        if output:
            lines=output.splitlines()
            if len(lines)>65:
                log(f'Command output ({len(lines)} lines, showing last 65; full output in log):','DETAIL')
                lines=lines[-65:]
            for line in lines:
                log('│ '+line[:500],'DETAIL')
    if check and p.returncode:
        output=((p.stdout or '')+'\n'+(p.stderr or '')).strip()
        lines=output.splitlines()
        tail='\n'.join(lines[-55:])
        if len(lines)>55:tail='[showing last 55 lines; see full release log]\n'+tail
        raise ReleaseError(f'{argv[0]} failed (exit {p.returncode}, {elapsed:.1f}s):\n{tail[-8500:]}')
    return p

def ssh(script, timeout=70):
    return command(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                    '-o','ConnectTimeout=10','-p',SSH_PORT,SSH_HOST,'bash','-se'],
                   stdin='set -euo pipefail\n'+script+'\n',timeout=timeout).stdout.strip()

def h(data):
    return hashlib.sha256(data).hexdigest()

def vt(s):
    return tuple(map(int,s.split('.')))

def last_deployed():
    try:
        value=json.loads((STATE/'deployed.json').read_text()).get('version','')
        return value if VERSION_RE.fullmatch(value) else '0.0.0'
    except (OSError,ValueError,TypeError):
        return '0.0.0'

def check_watcher(path):
    """Validate bounded self-update payload before it can replace executable code.

    Checksums verify integrity, not provenance: accept ZIPs only from a trusted producer.
    """
    source = path.read_text(encoding='utf-8')
    marker = re.search(r"^WATCHER_BUILD\s*=\s*'([0-9]+\.[0-9]+\.[0-9]+)'$", source, re.M)
    if not marker or not VERSION_RE.fullmatch(marker.group(1)):
        raise ReleaseError('Self-update missing watcher build marker')
    if vt(marker.group(1)) < vt(WATCHER_BUILD):
        raise ReleaseError('Refusing watcher downgrade')
    current = ROOT/'watcher-meta-vehicle.sh'
    previous=(re.search(r"^WATCHER_BUILD\s*=\s*'([0-9]+\.[0-9]+\.[0-9]+)'$",
                        current.read_text(encoding='utf-8'),re.M)
              if current.is_file() else None)
    if (previous and previous.group(1)==marker.group(1) and
        h(current.read_bytes()) != h(path.read_bytes())):
        raise ReleaseError('Changed watcher must bump WATCHER_BUILD')
    command(['bash','-n',str(path)],timeout=15)
    match=re.search(r"<<'VEHICLE_WATCH_PY'\n(.*)\nVEHICLE_WATCH_PY\s*$",source,re.S)
    if not match: raise ReleaseError('Watch script missing Python body')
    with tempfile.TemporaryDirectory(prefix='vehiclelab-watch-test-') as scratch:
        extracted=Path(scratch)/'watcher.py'
        extracted.write_text(match.group(1)+'\n',encoding='utf-8')
        command(['python3','-m','py_compile',str(extracted)],timeout=15)
    for token in ('StrictHostKeyChecking=yes','SHA-256 mismatch','git_preflight','smoke_public',
                  'install_watcher','WATCHER_BUILD', 'RELEASE END', 'FULL LOG:',
                  '--color', '--tail', '--verbose'):
        if token not in source:raise ReleaseError('Watcher regression check missing: '+token)
    log('Watcher shell/Python syntax and version checks passed','PASS')

def unwrap_legacy_setup(archive, scratch):
    """Read older four-file setup ZIPs directly from updates; never install old watcher."""
    with zipfile.ZipFile(archive) as z:
        info=z.infolist()
        if len(info)>12 or sum(i.file_size for i in info)>15*1024*1024:
            raise ReleaseError('Setup ZIP exceeds safety limits')
        names=[i.filename for i in info if not i.is_dir()]
        if len(names)!=len(set(names)):raise ReleaseError('Duplicate setup ZIP member')
        allowed={'watcher-meta-vehicle.sh','index.html','INSTALL_META_VEHICLE_LAB.txt'}
        nested=[name for name in names if re.fullmatch(r'META_VEHICLE_LAB_RELEASE_v\d+\.\d+\.\d+\.zip',name)]
        if len(nested)!=1 or set(names)-allowed-set(nested):
            raise ReleaseError('Unsupported setup ZIP contents')
        for member in info:
            if ('/' in member.filename or '\\' in member.filename or
                (member.external_attr>>16 & 0o170000)==0o120000):
                raise ReleaseError('Unsafe setup ZIP path')
        inner=scratch/nested[0]
        inner.write_bytes(z.read(nested[0]))
        # Legacy setup included an unmanifested watcher. Do not overwrite the
        # newer self-updating watcher with that unauthenticated older copy.
        log('Unpacked legacy setup; ignoring its old watcher, validating nested release')
        return inner

def validate_archive(archive, stage):
    with zipfile.ZipFile(archive) as z:
        info=z.infolist()
        if len(info)>64 or sum(x.file_size for x in info)>25*1024*1024:
            raise ReleaseError('Archive exceeds release safety limits')
        names=[x.filename for x in info if not x.is_dir()]
        if len(names)!=len(set(names)) or 'manifest.json' not in names:
            raise ReleaseError('Missing manifest.json or duplicate ZIP member')
        for x in info:
            parts=PurePosixPath(x.filename)
            mode=x.external_attr>>16
            if (x.filename.startswith('/') or '\\' in x.filename or '..' in parts.parts
                or any(part=='.git' for part in parts.parts)
                or (mode & 0o170000)==0o120000):
                raise ReleaseError('Unsafe ZIP member: '+x.filename)
            if not x.is_dir() and x.filename not in ('manifest.json','watcher-meta-vehicle.sh','bootstrap.py'):
                if x.filename not in {'app/'+p for p in ALLOWED}:
                    raise ReleaseError('Unexpected application file: '+x.filename)
        manifest=json.loads(z.read('manifest.json'))
        version=manifest.get('version','')
        if not isinstance(version,str) or not VERSION_RE.fullmatch(version):
            raise ReleaseError('Invalid manifest version')
        match=re.search(r'(?:^|_)v(\d+\.\d+\.\d+)(?:_|\.|$)',archive.name)
        if not match or match.group(1)!=version:
            raise ReleaseError('Archive filename must contain matching v'+version)
        if vt(version)<=vt(last_deployed()):
            raise ReleaseError(f'v{version} is not newer than last deployed v{last_deployed()}')
        hashes=manifest.get('sha256')
        if not isinstance(hashes,dict) or set(hashes) not in (APP_FILES,ALLOWED):
            raise ReleaseError('SHA-256 manifest must list exactly the static or full Flask app files')
        expected={'manifest.json'}|{'app/'+name for name in hashes}
        update=manifest.get('watcher')
        if update is not None:
            if (not isinstance(update,dict) or update.get('path')!='watcher-meta-vehicle.sh'
                or not isinstance(update.get('sha256'),str)
                or not SHA_RE.fullmatch(update['sha256'])):
                raise ReleaseError('Invalid watcher update checksum/metadata')
            expected.add('watcher-meta-vehicle.sh')
        boot=manifest.get('bootstrap')
        if boot is not None:
            if (not isinstance(boot,dict) or boot.get('path')!='bootstrap.py'
                or not isinstance(boot.get('sha256'),str)
                or not SHA_RE.fullmatch(boot['sha256'])):
                raise ReleaseError('Invalid bootstrap checksum/metadata')
            expected.add('bootstrap.py')
        if set(names)!=expected:
            raise ReleaseError('Archive contents and checksum manifest disagree')
        if not isinstance(manifest.get('changes'),list) or not manifest['changes']:
            raise ReleaseError('Manifest has no change notes')
        for rel, expected in hashes.items():
            if not isinstance(expected,str) or not SHA_RE.fullmatch(expected):
                raise ReleaseError('Invalid checksum for '+rel)
            content=z.read('app/'+rel)
            if h(content)!=expected:
                raise ReleaseError('SHA-256 mismatch: '+rel)
            target=stage/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(content)
        check_app(stage,version)
        if set(hashes)==ALLOWED:check_backend(stage)
        if update is not None:
            content=z.read('watcher-meta-vehicle.sh')
            if h(content)!=update['sha256']:
                raise ReleaseError('SHA-256 mismatch: watcher-meta-vehicle.sh')
            candidate=stage/'watcher-meta-vehicle.sh'
            candidate.write_bytes(content)
            check_watcher(candidate)
        if boot is not None:
            content=z.read('bootstrap.py')
            if h(content)!=boot['sha256']:
                raise ReleaseError('SHA-256 mismatch: bootstrap.py')
            with tempfile.TemporaryDirectory(prefix='vehiclelab-bootstrap-check-') as scratch:
                candidate=Path(scratch)/'bootstrap.py';candidate.write_bytes(content)
                command(['python3','-m','py_compile',str(candidate)],timeout=15)
        return manifest

class Tags(HTMLParser):
    def __init__(self):
        super().__init__();self.stack=[];self.forms=0;self.passwords=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='form':self.forms+=1
        if tag=='input' and a.get('type')=='password':
            self.passwords+=1
            if not self.forms:raise ReleaseError('Password input outside form')
    def handle_endtag(self,tag):
        if tag=='form':self.forms=max(0,self.forms-1)

def check_app(stage,version):
    doc=(stage/'index.html').read_text(encoding='utf-8')
    meta=re.search(r'<meta\s+name="vehicle-lab-version"\s+content="([^"]+)"\s*/?>',doc)
    if not meta or meta.group(1)!=version:
        raise ReleaseError('index.html version marker mismatch')
    data=json.loads((stage/'version.json').read_text())
    if data.get('version')!=version or data.get('project')!='meta-vehicle-lab':
        raise ReleaseError('version.json mismatch')
    if '<!DOCTYPE html>' not in doc or '</html>' not in doc:
        raise ReleaseError('Incomplete HTML')
    form=doc.find('<form id="credentialsForm"')
    mount=doc.find('<div id="guiMount"')
    form_end=doc.find('</form>',form) if form>=0 else -1
    if not (0 <= form < mount < form_end):
        raise ReleaseError('AI key fields require a containing form')
    Tags().feed(doc)
    found=re.search(r'<script\s+type="importmap"\s*>\s*(.*?)\s*</script>',doc,re.S)
    if not found:raise ReleaseError('Missing browser import map')
    imports=json.loads(found.group(1)).get('imports',{})
    if not all(key in imports for key in ('three','three/addons/','cannon-es','lil-gui')):
        raise ReleaseError('Missing required pinned 3D dependencies')
    inline=re.search(r'<script\s+type="module"\s*>(.*?)</script>',doc,re.S)
    if not inline or len(inline.group(1))<1000:
        raise ReleaseError('Missing JavaScript application module')
    source=inline.group(1)
    if 'let selectedPart=' not in source or 'function updateHighlight()' not in source:
        raise ReleaseError('Selected-module regression guard missing')
    for required in ('RaycastVehicle','OrbitControls','indexedDB.open','function followCamera',
                     'function buildVehicle','function enterDrive','function leaveDrive'):
        if required not in source:raise ReleaseError('App smoke check: missing '+required)
    with tempfile.TemporaryDirectory(prefix='vehiclelab-js-') as t:
        f=Path(t)/'vehicle.mjs';f.write_text(source)
        command(['node','--check',str(f)],timeout=25)
    log('JavaScript syntax, manifest, import map and app smoke checks passed','PASS')

def check_backend(stage):
    """Run stdlib regression tests and compile every backend/installer module.

    Flask API integration tests run on the server after pip installation; local
    validation does not silently assume Flask is installed on the Mac.
    """
    deps=(stage/'backend/requirements.txt').read_text().splitlines()
    if not any(line.startswith('Flask==') for line in deps) or not any(line.startswith('gunicorn==') for line in deps):
        raise ReleaseError('Flask/Gunicorn pinned requirements are missing')
    for rel in sorted(BACKEND_FILES):
        if rel.endswith('.py'):
            command(['python3','-m','py_compile',str(stage/rel)],timeout=20)
    result=command(['python3','-m','unittest','discover','-s','tests','-v'],cwd=stage,timeout=50)
    if 'test_create_read_update_and_delete' not in result.stderr and 'test_create_read_update_and_delete' not in result.stdout:
        raise ReleaseError('SQLite regression tests did not run')
    for required in ('insert_api_location','rollback','vehiclelab-flask','/var/lib/vehiclelab'):
        if required not in (stage/'deploy/install.py').read_text() and required!='vehiclelab-flask':
            raise ReleaseError('Installer regression guard missing '+required)
    if '/opt/vehiclelab/current' not in (stage/'deploy/vehiclelab.service').read_text():
        raise ReleaseError('Systemd service missing versioned backend entrypoint')
    # Never ship generated bytecode: the remote payload must match the manifest.
    for cache in stage.rglob('__pycache__'):
        if cache.is_dir():shutil.rmtree(cache)
    log('Python syntax, SQLite regressions and deployment module checks passed','PASS')

def git_preflight(stage):
    if not (ROOT/'.git').exists():raise ReleaseError('Run the watcher inside the cloned Git repository')
    if command(['git','branch','--show-current'],cwd=ROOT).stdout.strip()!='main':
        raise ReleaseError('Only branch main is eligible for automatic deployment')
    origin=command(['git','remote','get-url','origin'],cwd=ROOT).stdout.strip()
    if origin not in (REPO_SSH,'ssh://git@github.com/sylwesterdigital/meta-vehicle-lab.git'):
        raise ReleaseError('Unexpected Git origin: '+origin)
    command(['git','var','GIT_AUTHOR_IDENT'],cwd=ROOT)
    # Protect user changes. Finder's .DS_Store files are metadata, not application
    # source, so ignore ONLY untracked files with that exact basename (including
    # nested directories). Never stash/reset/delete them or disregard other edits.
    status=command(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT).stdout
    for line in status.splitlines():
        path=line[3:]
        if line.startswith('?? ') and Path(path).name=='.DS_Store':
            log('Ignoring macOS Finder metadata: '+path)
            continue
        if line.startswith('?? ') and (path.startswith('updates/') or
                                       path.startswith('.vehiclelab/')):
            continue
        # The active watcher is a managed release artifact and is committed in
        # push_git(); allow its own tracked or untracked updates, but not deletion.
        if (path=='watcher-meta-vehicle.sh' and
            'D' not in line[:2] and (ROOT/path).is_file() and not (ROOT/path).is_symlink()):
            continue
        raise ReleaseError('Protecting local changes; commit/stash first: '+line)
    remote=command(['git','ls-remote','origin','refs/heads/main'],cwd=ROOT,timeout=50).stdout.strip()
    if remote:
        command(['git','fetch','--no-tags','origin','main'],cwd=ROOT,timeout=60)
        head=command(['git','rev-parse','--verify','HEAD'],cwd=ROOT,check=False)
        if head.returncode!=0 or command(['git','merge-base','--is-ancestor','FETCH_HEAD','HEAD'],
                                          cwd=ROOT,check=False).returncode!=0:
            raise ReleaseError('origin/main is not an ancestor of local HEAD; reconcile manually')
    ssh(f'test -d {shlex.quote(WEBROOT)} && test -w {shlex.quote(WEBROOT)} && command -v sha256sum >/dev/null')
    remote_version=ssh(f'''if [ -f {shlex.quote(WEBROOT+'/version.json')} ]; then
      cat {shlex.quote(WEBROOT+'/version.json')}; fi''')
    if remote_version:
        try:current=json.loads(remote_version).get('version','')
        except ValueError:raise ReleaseError('Server version.json is not valid JSON')
        version=json.loads((stage/'version.json').read_text())['version']
        if VERSION_RE.fullmatch(str(current)) and vt(version)<=vt(current):
            raise ReleaseError(f'Release v{version} must be newer than server v{current}')
    log('Git main, clean working tree, origin and server preflight passed','PASS')

def install_watcher(stage):
    """Install the reviewed watcher atomically and retain the previous copy."""
    global RESTART_REQUESTED
    incoming=stage/'watcher-meta-vehicle.sh'
    if not incoming.is_file(): return False
    dest=ROOT/'watcher-meta-vehicle.sh'
    if dest.is_symlink(): raise ReleaseError('Refusing watcher symlink')
    content=incoming.read_bytes()
    if dest.is_file() and dest.read_bytes()==content: return False
    backups=STATE/'watcher-backups'
    backups.mkdir(mode=0o700,exist_ok=True)
    if dest.is_file():
        backup=backups/(dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sh')
        shutil.copy2(dest,backup)
        backup.chmod(0o600)
    with tempfile.NamedTemporaryFile(prefix='.watcher-next-',dir=ROOT,delete=False) as out:
        temp=Path(out.name)
        out.write(content)
        out.flush();os.fsync(out.fileno())
    try:
        temp.chmod(0o755)
        os.replace(temp,dest)
    finally:
        if temp.exists():temp.unlink()
    log('Installed reviewed watcher; previous script saved in .vehiclelab/watcher-backups/','PASS')
    RESTART_REQUESTED=True
    return True

def push_git(stage,version):
    for name in sorted(release_files(stage)):
        target=ROOT/name
        if target.is_symlink():raise ReleaseError('Refusing local symlink: '+name)
        # No untracked application files may be overwritten without explicit approval.
        exists=command(['git','ls-files','--error-unmatch','--',name],cwd=ROOT,check=False).returncode==0
        if target.exists() and not exists:
            raise ReleaseError('Refusing to overwrite an untracked local file: '+name)
        if name=='.gitignore' and exists:
            # Preserve a repository owner's existing patterns; add only watcher exclusions.
            original=target.read_text(encoding='utf-8')
            lines=set(original.splitlines())
            additions=[p for p in ('/updates/','/.vehiclelab/','.DS_Store') if p not in lines]
            if additions:
                target.write_text(original.rstrip('\n')+'\n'+'\n'.join(additions)+'\n')
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(stage/name,target)
    updated=install_watcher(stage)
    stage_names=sorted(release_files(stage))
    if (ROOT/'watcher-meta-vehicle.sh').is_file():stage_names.append('watcher-meta-vehicle.sh')
    command(['git','add','--',*stage_names],cwd=ROOT)
    diff=command(['git','diff','--cached','--quiet'],cwd=ROOT,check=False)
    if diff.returncode==1:
        command(['git','commit','-m',f'Release Meta Vehicle Lab v{version}'],cwd=ROOT)
    elif diff.returncode!=0:raise ReleaseError('Git staged diff could not be inspected')
    expected=command(['git','rev-parse','HEAD'],cwd=ROOT).stdout.strip()
    sent=command(['git','push','-u','origin','main'],cwd=ROOT,timeout=110,check=False)
    # A rejected/ambiguous push must not be interpreted as deployment success.
    remote=command(['git','ls-remote','origin','refs/heads/main'],cwd=ROOT,timeout=50).stdout.strip()
    if not remote.startswith(expected+'\t'):
        raise ReleaseError('GitHub main did not verify at local HEAD; server left untouched. '+(sent.stderr or '')[-280:])
    log('GitHub main verified at '+expected[:12],'PASS')
    return updated

def public_baseline():
    """Snapshot HTTP availability *before* publishing new bytes.

    An already-broken external reverse proxy must not repeatedly undo verified
    origin files. A newly broken public endpoint must still trigger rollback.
    """
    try:
        public_get('index.html')
        public_get('version.json')
        return True, ''
    except Exception as error:
        return False, f'{type(error).__name__}: {error}'


def publish(stage,version):
    was_public_healthy, prior_public_error = public_baseline()
    if not was_public_healthy:
        log('Public HTTPS failed BEFORE release: '+prior_public_error[:480], 'WARN')
    token=f'{version}-{int(time.time())}-{secrets.token_hex(4)}'
    work='/var/www/.vehiclelab-staging-'+token
    backup='/var/www/.vehiclelab-backups/'+token
    qwork,qbackup,qroot=map(shlex.quote,(work,backup,WEBROOT))
    backup_ready=False
    try:
        ssh(f'mkdir -m 700 -p {qwork}')
        checks=''.join(f'{h((stage/name).read_bytes())}  {name}\n' for name in PUBLISH)
        (stage/'deploy.sha256').write_text(checks)
        command(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                 '-P',SSH_PORT,*(str(stage/name) for name in PUBLISH),str(stage/'deploy.sha256'),
                 f'{SSH_HOST}:{work}/'],timeout=120)
        ssh(f'cd {qwork} && sha256sum -c deploy.sha256')
        # Backup is created before any public file is altered.
        ssh(f'''mkdir -p -m 700 {qbackup}
           for f in {' '.join(PUBLISH)}; do
             test ! -L {qroot}/"$f" || {{ echo 'Refusing server symlink'; exit 1; }}
             if test -e {qroot}/"$f"; then cp -p {qroot}/"$f" {qbackup}/"$f"; fi
           done''')
        backup_ready=True
        ssh(f'''for f in {' '.join(PUBLISH)}; do
            install -m 644 {qwork}/"$f" {qroot}/".$f.{token}.tmp"
            mv -f {qroot}/".$f.{token}.tmp" {qroot}/"$f"
           done''')
        # Verify installed files in the destination, not just the staging dir.
        # This proves correct bytes at origin even when the public site/CDN
        # already has a redirect loop outside this app's release control.
        ssh(f'cd {qroot} && sha256sum -c {qwork}/deploy.sha256')
        try:
            smoke_public(version)
        except Exception as error:
            if was_public_healthy:
                # A new external failure is a release regression, so rollback.
                raise ReleaseError('Public HTTPS failed AFTER release (was healthy before): '+str(error)) from error
            log('Origin v'+version+' installed and SHA-256 verified. Public URL was already failing before deployment; HTTPS remains UNVERIFIED: '+str(error)[:440], 'WARN')
            return False
        log(f'Public HTTPS smoke passed; previous files backed up in {backup}','PASS')
        return True
    except Exception:
        if backup_ready:
            try:
                ssh(f'''for f in {' '.join(PUBLISH)}; do
                     if test -f {qbackup}/"$f"; then
                       cp -p {qbackup}/"$f" {qroot}/".$f.rollback.tmp"
                       mv -f {qroot}/".$f.rollback.tmp" {qroot}/"$f"
                     else rm -f {qroot}/"$f"; fi
                   done''')
                log('Server rollback completed from pre-release backup','WARN')
            except Exception as err:
                log('URGENT: automatic server rollback failed: '+str(err),'FAIL')
        raise
    finally:
        try:ssh(f'rm -rf -- {qwork}')
        except Exception as e:log('Remote staging cleanup needed: '+str(e),'WARN')

def publish_flask(stage, version):
    """Install one isolated Flask release, server-owned SQLite and API proxy.

    Nginx config changes are performed only by deploy/install.py, which retains
    originals and can revert current symlink, service, site config and statics.
    """
    was_public_healthy, prior_error=public_baseline()
    if not was_public_healthy:
        log('Public HTTPS failed BEFORE release: '+prior_error[:440],'WARN')
    token=f'{version}-{int(time.time())}-{secrets.token_hex(4)}'
    work='/var/www/.vehiclelab-staging-'+token
    qwork=shlex.quote(work)
    receipt='/var/lib/vehiclelab/deploy-backups/'+token+'.json'
    source_files=sorted(BACKEND_FILES)
    hashes={name:h((stage/name).read_bytes()) for name in source_files}
    hashes.update({name:h((stage/name).read_bytes()) for name in PUBLISH})
    checks=''.join(f'{digest}  {name}\n' for name,digest in sorted(hashes.items()))
    (stage/'deploy.sha256').write_text(checks)
    try:
        ssh(f'mkdir -m 700 -p {qwork}')
        command(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                 '-P',SSH_PORT,'-r',str(stage/'backend'),str(stage/'deploy'),
                 str(stage/'tests'),str(stage/'index.html'),str(stage/'version.json'),
                 str(stage/'deploy.sha256'),f'{SSH_HOST}:{work}/'],timeout=140)
        ssh(f'cd {qwork} && sha256sum -c deploy.sha256')
        log('Installing pinned Flask/Gunicorn release and configuring vehiclelab API…')
        installer_output=ssh(f'python3 {qwork}/deploy/install.py --stage {qwork} '
            f'--version {shlex.quote(version)} --id {shlex.quote(token)}',timeout=360)
        for line in installer_output.splitlines():
            if line.startswith(('SERVER UNIT TESTS PASSED:', 'DEPLOYED ')):
                log('Remote installer: '+line,'PASS')
        # Server-side install has already checked the loopback health endpoint.
        try:
            smoke_public(version)
            data=json.loads(public_get('api/health'))
            if data.get('version')!=version or data.get('storage')!='sqlite' or not data.get('ok'):
                raise ReleaseError('Public Flask/SQLite health endpoint is not serving this version')
        except Exception as error:
            if was_public_healthy:
                raise ReleaseError('Public verification failed after Flask install: '+str(error)) from error
            log('Flask/SQLite installed and verified on origin. Public HTTPS was already failing: '+str(error)[:440],'WARN')
            return False
        log('Public Flask/SQLite and HTTPS smoke passed','PASS')
        return True
    except Exception:
        try:
            ssh(f'''if test -f {shlex.quote(receipt)}; then
              python3 {qwork}/deploy/install.py --rollback {shlex.quote(receipt)}
              fi''',timeout=120)
            log('Flask release rollback attempted; SQLite database retained','WARN')
        except Exception as error:
            log('URGENT: remote Flask rollback failed: '+str(error),'FAIL')
        raise
    finally:
        try:ssh(f'rm -rf -- {qwork}')
        except Exception as e:log('Remote staging cleanup needed: '+str(e),'WARN')

def public_get(path):
    url=SITE+path+'?vehiclelab_release_check='+str(int(time.time()))
    request=urllib.request.Request(url,headers={'Cache-Control':'no-cache','User-Agent':'VehicleLabReleaseWatcher/1.0'})
    with urllib.request.urlopen(request,timeout=20) as resp:
        if resp.status!=200:raise ReleaseError('HTTP '+str(resp.status)+': '+path)
        return resp.read(5_000_000)

def smoke_public(version):
    data=json.loads(public_get('version.json'))
    if data.get('version')!=version or data.get('project')!='meta-vehicle-lab':
        raise ReleaseError('Public version.json mismatch after upload')
    html=public_get('index.html').decode('utf-8')
    if f'<meta name="vehicle-lab-version" content="{version}">' not in html or 'lil-gui' not in html:
        raise ReleaseError('Public index.html mismatch after upload')

def process(archive,dry_run):
    global RESTART_REQUESTED
    with tempfile.TemporaryDirectory(prefix='vehiclelab-validate-',dir=STATE) as tmp:
        work=Path(tmp)
        stage=work/'stage';stage.mkdir()
        started=time.monotonic()
        log('[1/4] VERIFY ZIP, CHECKSUMS, JAVASCRIPT AND PYTHON','STEP')
        log('Archive: '+str(archive))
        source=archive
        if archive.name.startswith('META_VEHICLE_LAB_SETUP_'):
            # Old setup archives nest a normal release ZIP. Newer updates carry
            # manifest.json directly and can safely update the watcher too.
            with zipfile.ZipFile(archive) as z:
                if 'manifest.json' not in z.namelist():
                    source=unwrap_legacy_setup(archive,work)
        try:
            manifest=validate_archive(source,stage)
        except Exception as exc:
            raise ArchiveError(str(exc)) from exc
        version=manifest['version']
        log(f'[1/4] VERIFIED v{version}: {len(manifest["sha256"])} files, SHA-256 and tests ({time.monotonic()-started:.1f}s)','PASS')
        if dry_run:
            log('[2/4] GIT PREFLIGHT SKIPPED (dry run)','INFO')
            log('[3/4] GITHUB PUSH SKIPPED (dry run)','INFO')
            log('[4/4] SERVER DEPLOY SKIPPED (dry run)','INFO')
            return {'status':'DRY RUN','details':'No GitHub or server changes'}

        step=time.monotonic()
        log('[2/4] GIT AND SSH PREFLIGHT','STEP')
        git_preflight(stage)
        log(f'[2/4] PREFLIGHT PASSED ({time.monotonic()-step:.1f}s)','PASS')

        step=time.monotonic()
        log('[3/4] COMMIT + PUSH GITHUB MAIN','STEP')
        changed_watcher=push_git(stage,version)
        log(f'[3/4] GITHUB VERIFIED ({time.monotonic()-step:.1f}s)','PASS')

        step=time.monotonic()
        log('[4/4] DEPLOY '+('FLASK + SQLITE + FRONTEND' if is_flask(stage) else 'STATIC FRONTEND')+' + VERIFY','STEP')
        try:
            public_verified=publish_flask(stage,version) if is_flask(stage) else publish(stage,version)
        except Exception:
            log('GitHub may already contain this release. Server rolled back if possible. Release retained for retry.','WARN')
            raise
        (STATE/'deployed.json').write_text(json.dumps({'version':version,
          'publicVerified':public_verified,
          'utc':dt.datetime.now(dt.timezone.utc).isoformat()},indent=2)+'\n')
        if public_verified:
            log(f'[4/4] PUBLIC SITE VERIFIED (HTTPS, Flask/SQLite) ({time.monotonic()-step:.1f}s)','PASS')
            log(f'LIVE v{version} — {SITE} — GitHub main updated','PASS')
        else:
            log(f'[4/4] ORIGIN VERIFIED ({time.monotonic()-step:.1f}s), BUT PUBLIC HTTPS NOT VERIFIED','WARN')
            log(f'ORIGIN DEPLOYED v{version} — GitHub main updated; PUBLIC HTTPS NOT VERIFIED','WARN')
        if changed_watcher:RESTART_REQUESTED=True
        return {'status':'SUCCESS' if public_verified else 'PARTIAL',
                'details':f'GitHub main updated | HTTPS {"VERIFIED" if public_verified else "NOT VERIFIED"}'}

def latest_logs():
    return sorted((STATE/'logs').glob('*.log'),key=lambda p:p.stat().st_mtime,reverse=True)

def save_retry_times(mapping):
    data={name:until for name,until in mapping.items()
          if isinstance(until,(int,float)) and until>time.time() and VALID_ZIP_RE.fullmatch(name)}
    path=STATE/'retry-times.json'
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)

def load_retry_times():
    try:
        data=json.loads((STATE/'retry-times.json').read_text(encoding='utf-8'))
        if not isinstance(data,dict):return {}
        return {name:until for name,until in data.items()
                if isinstance(until,(int,float)) and until>time.time() and VALID_ZIP_RE.fullmatch(name)}
    except (ValueError,OSError,TypeError):
        return {}

def main():
    global LOG_FILE, VERBOSE, COLOR_MODE
    parser=argparse.ArgumentParser(description='Meta Vehicle Lab ZIP watcher and verified deployer')
    options=parser.add_mutually_exclusive_group()
    options.add_argument('--once',action='store_true',help='Process all ZIPs then stop')
    options.add_argument('--dry-run',action='store_true',help='Validate ZIPs locally without network writes')
    options.add_argument('--status',action='store_true',help='Report deployed version and public HTTP status')
    options.add_argument('--logs',action='store_true',help='List recent release logs')
    options.add_argument('--tail',action='store_true',help='Show latest complete release log tail')
    parser.add_argument('--lines',type=int,default=100,help='Number of lines for --tail (default: 100)')
    parser.add_argument('--interval',type=int,default=3,help='Polling interval in seconds')
    parser.add_argument('--verbose',action='store_true',help='Print commands and output in the terminal')
    parser.add_argument('--color',choices=('auto','always','never'),default='auto',
                        help='Terminal ANSI colors: auto (TTY), always, or never')
    args=parser.parse_args()
    VERBOSE=args.verbose
    COLOR_MODE=args.color
    if args.interval<1 or args.lines<1:parser.error('interval and lines must be positive')
    UPDATES.mkdir(exist_ok=True);STATE.mkdir(exist_ok=True)
    for d in ('processed','failed','superseded'):(UPDATES/d).mkdir(exist_ok=True)
    (STATE/'logs').mkdir(mode=0o700,exist_ok=True)
    (STATE/'logs').chmod(0o700)
    if args.logs:
        paths=latest_logs()
        if not paths:log('No release logs yet','WARN')
        for path in paths[:15]:
            size=path.stat().st_size
            content=path.read_text(encoding='utf-8',errors='replace')
            results=re.findall(r'RESULT: ([^\n]+)',content)
            outcome=results[-1] if results else 'INCOMPLETE / INTERRUPTED'
            shade=('PASS' if 'SUCCESS' in outcome or 'DRY RUN' in outcome else
                   'WARN' if 'PUBLIC NOT VERIFIED' in outcome else 'FAIL')
            log(f'{outcome:40} {path} ({size:,} bytes)',shade)
        return 0
    if args.tail:
        paths=latest_logs()
        if not paths:
            log('No release logs yet','WARN');return 1
        path=paths[0]
        log(f'LATEST RELEASE LOG: {path}','STEP')
        with path.open(encoding='utf-8',errors='replace') as f:
            from collections import deque
            lines=deque(f,maxlen=args.lines)
        print(''.join(lines),end='',flush=True)
        return 0
    if args.status:
        log('Installed watcher: v'+WATCHER_BUILD,'PASS')
        log('Last confirmed origin deploy: v'+last_deployed())
        try:
            deployed=json.loads((STATE/'deployed.json').read_text())
            if not deployed.get('publicVerified',False):
                log('Last deployment did NOT confirm working public HTTPS','WARN')
        except (ValueError,OSError):pass
        paths=latest_logs()
        if paths:log('Latest full log: '+str(paths[0]))
        try:
            data=json.loads(public_get('version.json'))
            log('Public site reports v'+str(data['version']),'PASS')
        except Exception as exc:
            log('Could not verify public site: '+str(exc),'WARN')
        return 0
    with (STATE/'watch.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ReleaseError('Another watcher is already running')
        log(f'WATCHER v{WATCHER_BUILD} ACTIVE | color={"ON" if use_color() else "OFF"} | verbose={"ON" if VERBOSE else "OFF"}','PASS')
        log('Watching '+str(UPDATES)+' | GitHub main | '+SSH_HOST+':'+WEBROOT)
        log('Release logs: '+str(STATE/'logs')+' | View latest: ./watcher-meta-vehicle.sh --tail')
        failed=False
        ignored=set()
        retry_after=load_retry_times()
        while True:
            all_archives=sorted(UPDATES.glob('*.zip'))
            candidates=[]
            for archive in all_archives:
                if VALID_ZIP_RE.fullmatch(archive.name):
                    candidates.append(archive)
                elif archive.name not in ignored:
                    ignored.add(archive.name)
                    log('Ignoring unrelated ZIP '+archive.name+' (expect RELEASE, UPDATE or SETUP)','WARN')
            if (args.once or args.dry_run) and not candidates:
                log('No update ZIP found in updates/. Expected META_VEHICLE_LAB_{RELEASE,UPDATE,SETUP}_vX.Y.Z.zip','WARN')
                return 1
            for archive in candidates:
                known=re.search(r'_v(\d+\.\d+\.\d+)',archive.name)
                installed=last_deployed()
                if known and vt(known.group(1))<=vt(installed):
                    dest=UPDATES/'superseded'/archive.name
                    if dest.exists():
                        dest=dest.with_name(dest.stem+'-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.zip')
                    archive.rename(dest)
                    retry_after.pop(archive.name,None)
                    save_retry_times(retry_after)
                    log(f'SKIPPED SUPERSEDED v{known.group(1)} (already deployed v{installed}); preserved at {dest}','WARN')
                    continue
                if not (args.once or args.dry_run) and time.time()<retry_after.get(archive.name,0):
                    continue
                if not (args.once or args.dry_run) and time.time()-archive.stat().st_mtime<4:
                    continue # Ignore partial file transfers.
                stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                LOG_FILE=STATE/'logs'/(stamp+'-'+re.sub(r'[^a-zA-Z0-9_.-]','_',archive.stem)+'.log')
                LOG_FILE.touch(mode=0o600,exist_ok=False)
                release_version=re.search(r'_v(\d+\.\d+\.\d+)',archive.name)
                release_version=release_version.group(1) if release_version else 'unknown'
                started=time.monotonic()
                result={'status':'FAILURE','details':'Deployment did not complete'}
                banner('START',release_version,filename=archive.name,
                       mode='DRY RUN' if args.dry_run else 'DEPLOY')
                try:
                    result=process(archive,args.dry_run)
                    if not args.dry_run:
                        destination=UPDATES/'processed'/archive.name
                        if destination.exists():destination=destination.with_name(destination.stem+'-'+stamp+'.zip')
                        archive.rename(destination)
                        retry_after.pop(archive.name,None)
                        save_retry_times(retry_after)
                except Exception as exc:
                    failed=True
                    lines=str(exc).splitlines()
                    log('RELEASE FAILED: '+(lines[0] if lines else type(exc).__name__),'FAIL')
                    for line in lines[1:]:log(line,'FAIL')
                    result={'status':'FAILURE','details':f'{type(exc).__name__}: '+(lines[0] if lines else '')[:200]}
                    if VERBOSE:log(traceback.format_exc(),'DETAIL')
                    if not args.dry_run and isinstance(exc,ArchiveError):
                        destination=UPDATES/'failed'/archive.name
                        if destination.exists():destination=destination.with_name(destination.stem+'-'+stamp+'.zip')
                        archive.rename(destination)
                        retry_after.pop(archive.name,None)
                        save_retry_times(retry_after)
                        log('Invalid ZIP moved to '+str(destination),'WARN')
                    elif not args.dry_run:
                        retry_after[archive.name]=time.time()+60
                        save_retry_times(retry_after)
                        log('Verified ZIP remains in updates/; automatic retry in ≥60 seconds','WARN')
                finally:
                    banner('END',release_version, status=result['status'],
                           details=result.get('details',''),duration=time.monotonic()-started)
                    LOG_FILE=None
                if RESTART_REQUESTED and not (args.once or args.dry_run):
                    log('ACTIVATING VERIFIED WATCHER v'+WATCHER_BUILD+' FROM DISK','PASS')
                    program=str(ROOT/'watcher-meta-vehicle.sh')
                    argv=[program,'--interval',str(args.interval),'--color',args.color]
                    if args.verbose:argv.append('--verbose')
                    os.execv(program,argv)
            if args.once or args.dry_run:return int(failed)
            time.sleep(args.interval)

if __name__=='__main__':
    try:sys.exit(main())
    except KeyboardInterrupt:print('\nWatcher stopped.');sys.exit(0)
    except Exception as error:log(str(error),'FAIL');sys.exit(1)
VEHICLE_WATCH_PY
