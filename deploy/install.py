#!/usr/bin/env python3
"""Transactional, single-site vehiclelab.xyz Flask deployment. Run via reviewed watcher.

Root only. Never changes other Nginx site files; SQLite lives outside releases.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pwd
import re
import secrets
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.request
from pathlib import Path

BASE=Path('/opt/vehiclelab')
RELEASES=BASE/'releases'
CURRENT=BASE/'current'
SITE_LINK=Path('/etc/nginx/sites-enabled/vehiclelab.xyz')
UNIT=Path('/etc/systemd/system/vehiclelab-flask.service')
ENVFILE=Path('/etc/vehiclelab/vehiclelab.env')
DATA=Path('/var/lib/vehiclelab')
BACKUPS=DATA/'deploy-backups'
WEBROOT=Path('/var/www/vehiclelab.xyz')
VERSION_RE=re.compile(r'^\d+\.\d+\.\d+$')
BEGIN='# VEHICLELAB API BEGIN'
END='# VEHICLELAB API END'
API_LOCATION='''
    # VEHICLELAB API BEGIN
    location ^~ /api/ {
        proxy_pass http://127.0.0.1:8766;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 85m;
        proxy_read_timeout 120s;
    }
    # VEHICLELAB API END
'''


def shell(*cmd, timeout=180, cwd=None):
    # Preserve the underlying traceback / unittest assertion on deployment
    # failure. The old CalledProcessError only showed an exit status and hid the
    # actionable reason for the remote Flask regression failure.
    result=subprocess.run(cmd, check=False, text=True, timeout=timeout,
                          capture_output=True, cwd=cwd)
    if result.returncode:
        diagnostic=((result.stdout or '')+'\n'+(result.stderr or '')).strip()
        label=' '.join(map(str,cmd))
        raise RuntimeError(f'Command failed ({result.returncode}): {label}\n'
                           f'--- COMMAND OUTPUT (last 12000 characters) ---\n'
                           f'{diagnostic[-12000:]}')
    return result


def find_server_spans(config):
    """Locate server blocks with brace counting outside quoted strings and comments."""
    spans=[]
    for m in re.finditer(r'\bserver\s*\{',config):
        start=m.start();brace=config.find('{',start)
        i=brace+1;depth=1;quote=None;comment=False;escape=False
        while i<len(config) and depth:
            c=config[i]
            if comment:
                if c=='\n':comment=False
            elif escape:escape=False
            elif c=='\\':escape=True
            elif quote:
                if c==quote:quote=None
            elif c=='#':comment=True
            elif c in ('"',"'"):quote=c
            elif c=='{':depth+=1
            elif c=='}':depth-=1
            i+=1
        if depth:raise ValueError('Unmatched Nginx server brace')
        spans.append((start,i,i-1))
    return spans


def insert_api_location(config):
    """Insert one guarded API location into the matching HTTPS vhost only."""
    matches=[]
    for start,end,close in find_server_spans(config):
        block=config[start:end]
        if (re.search(r'\bserver_name\s+vehiclelab\.xyz\s*;',block) and
            re.search(r'\blisten\s+(?:\[[^]]+\]:)?443\s+ssl\b',block)):
            matches.append((start,end,close))
    if len(matches)!=1:
        raise ValueError('Expected exactly one vehiclelab.xyz TLS server block')
    start,end,close=matches[0];block=config[start:end]
    if BEGIN in block and END in block:
        return config  # Already installed: leave unrelated directives untouched.
    if BEGIN in block or END in block or re.search(r'location\s+(?:\^~\s+)?/api/?\s*\{',block):
        raise ValueError('Unmanaged/conflicting /api location; do not overwrite')
    return config[:close]+API_LOCATION+config[close:]


def atomic_write(path,contents,mode=0o644):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name('.'+path.name+'.vehiclelab-next')
    try:
        with tmp.open('wb') as f:
            f.write(contents);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,mode)
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def restore_file(target, source):
    target=Path(target)
    if source is None:
        target.unlink(missing_ok=True)
    else:
        atomic_write(target,Path(source).read_bytes(),Path(source).stat().st_mode & 0o777)


def rollback(receipt):
    info=json.loads(Path(receipt).read_text())
    errors=[]
    # Stop the just-started API before restoring the previous unit/symlink.
    subprocess.run(['systemctl','stop','vehiclelab-flask'],capture_output=True)
    for target,backup in info['files'].items():
        try:restore_file(target,backup)
        except Exception as error:errors.append(f'Restore {target}: {error}')
    try:
        old=info['previous_current']
        if old is None:CURRENT.unlink(missing_ok=True)
        else:
            next_link=BASE/'.current-rollback'
            next_link.unlink(missing_ok=True)
            next_link.symlink_to(old)
            os.replace(next_link,CURRENT)
    except Exception as error:errors.append(f'Restore current: {error}')
    if not info['unit_preexisting']:
        subprocess.run(['systemctl','disable','vehiclelab-flask'],capture_output=True)
    cmds=[('systemctl','daemon-reload')]
    if info['unit_preexisting']:cmds.append(('systemctl','restart','vehiclelab-flask'))
    cmds.extend([('nginx','-t'),('systemctl','reload','nginx')])
    for command in cmds:
        try:shell(*command,timeout=35)
        except Exception as error:errors.append(f'{" ".join(command)}: {error}')
    # Only remove the release directory that this deployment created, never the
    # previous active release, and never the persistent SQLite directory.
    failed_release=info.get('new_release')
    if failed_release and not errors:
        candidate=Path(failed_release)
        if candidate.parent==RELEASES and candidate.is_dir() and not CURRENT.resolve()==candidate:
            try:shutil.rmtree(candidate)
            except Exception as error:errors.append(f'Failed release cleanup: {error}')
    if errors:
        raise RuntimeError('Rollback incomplete: '+'; '.join(errors))
    print('Previous vehiclelab release/service/Nginx configuration restored; SQLite retained.')


def copy_release_payload(stage, target):
    """Copy the same runnable tree used for server-side regression tests.

    Nginx tests import deploy.install. Excluding deploy/ from the staged release
    caused v0.2.0 and v0.2.1 to fail with ModuleNotFoundError after a successful
    GitHub push, even though the source tree passed local tests.
    """
    stage=Path(stage)
    target=Path(target)
    for directory in ('backend', 'deploy', 'tests'):
        shutil.copytree(stage/directory, target/directory)
    for filename in ('index.html', 'version.json'):
        shutil.copy2(stage/filename, target/filename)


def report_mail_prerequisites():
    """Read-only Postfix inspection. Never alter another site's SMTP service.

    Email/phone are unverified profile metadata in this release. A working
    password-reset sender requires DNS SPF/DKIM/DMARC/PTR, verified outbound
    delivery and abuse controls. Installing/configuring SMTP automatically from
    the app's release watcher could disrupt existing domains on this host.
    """
    if not shutil.which('postconf'):
        print('MAIL CHECK: Postfix not installed. Recovery emails DISABLED. '
              'DNS and outbound SMTP require administrator setup.',flush=True)
        return
    result=subprocess.run(['postconf','-h','myhostname'],capture_output=True,text=True,timeout=8)
    name=(result.stdout or '').strip()[:120] if result.returncode==0 else 'unknown'
    service=subprocess.run(['systemctl','is-active','postfix'],capture_output=True,text=True,timeout=8)
    print('MAIL CHECK: Postfix present; hostname='+name+'; service='+(service.stdout or '').strip()+
          '. No global MTA changes made. Password recovery DISABLED.',flush=True)


def activate(stage,version,release_id):
    if os.geteuid()!=0:raise RuntimeError('Must run as root on the server')
    if not VERSION_RE.fullmatch(version):raise ValueError('Invalid version')
    if not re.fullmatch(r'[0-9a-zA-Z._-]{1,100}',release_id):raise ValueError('Invalid receipt ID')
    stage=Path(stage).resolve(strict=True)
    if SITE_LINK.is_symlink():
        site=SITE_LINK.resolve(strict=True)
    elif SITE_LINK.is_file():site=SITE_LINK
    else:raise RuntimeError('Site config not found; refusing to create unknown vhost')
    if not str(site).startswith('/etc/nginx/'):
        raise RuntimeError('Site config resolves outside /etc/nginx')
    if not (WEBROOT.is_dir() and (stage/'backend/app.py').is_file()):
        raise RuntimeError('Missing site root or backend payload')
    if CURRENT.exists() and not CURRENT.is_symlink():
        raise RuntimeError('Refusing to replace a non-symlink backend current directory')
    if not (stage/'version.json').is_file() or json.loads((stage/'version.json').read_text()).get('version')!=version:
        raise RuntimeError('Staged version mismatch')
    for dependency in ('nginx','systemctl','python3'):
        if shutil.which(dependency) is None:raise RuntimeError('Missing server prerequisite: '+dependency)
    # Fail before modifying any active service if venv tooling is absent.
    if shell('python3','-m','venv','--help',timeout=20).returncode:
        raise RuntimeError('python3-venv not available')

    RELEASES.mkdir(parents=True,exist_ok=True)
    next_release=RELEASES/('v'+version)
    if next_release.exists():
        raise RuntimeError('Backend release path already exists; refuse overwrite: '+str(next_release))
    next_release.mkdir(mode=0o755)
    try:
        copy_release_payload(stage,next_release)
        shell('python3','-m','venv',str(next_release/'.venv'),timeout=75)
        shell(str(next_release/'.venv/bin/python'),'-m','pip','install','--disable-pip-version-check',
              '--no-input','-r',str(next_release/'backend/requirements.txt'),timeout=240)
        # Explicitly require the production Flask app to be importable.
        shell(str(next_release/'.venv/bin/python'), '-c',
              'from backend.app import create_app; assert callable(create_app)',
              cwd=next_release,timeout=25)
        # Run Flask test-client and SQLite/Nginx regressions in the exact new venv.
        tested=shell(str(next_release/'.venv/bin/python'),'-m','unittest','discover',
                     '-s','tests','-v',cwd=next_release,timeout=90)
        print('SERVER UNIT TESTS PASSED: '+(tested.stderr or tested.stdout).strip().splitlines()[-1], flush=True)
    except Exception:
        # This release has never been activated; safe to discard incomplete files.
        shutil.rmtree(next_release)
        raise

    www=pwd.getpwnam('www-data')
    DATA.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chown(DATA,www.pw_uid,www.pw_gid)
    (DATA/'assets').mkdir(exist_ok=True,mode=0o700)
    os.chown(DATA/'assets',www.pw_uid,www.pw_gid)
    BACKUPS.mkdir(mode=0o700,exist_ok=True)
    ENVFILE.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
    try:os.chown(ENVFILE.parent,0,www.pw_gid)
    except PermissionError:pass
    if not ENVFILE.exists():
        content='VEHICLELAB_DATA_DIR='+str(DATA)+'\nVEHICLELAB_API_TOKEN='+secrets.token_urlsafe(48)+'\n'
        atomic_write(ENVFILE,content.encode(),0o640)
        os.chown(ENVFILE,0,www.pw_gid)
    else:
        if ENVFILE.is_symlink():raise RuntimeError('Refusing symlink in environment path')
        if 'VEHICLELAB_API_TOKEN=' not in ENVFILE.read_text():
            raise RuntimeError('Existing environment file missing VEHICLELAB_API_TOKEN')
    old_current=str(CURRENT.resolve()) if CURRENT.is_symlink() else None
    receipt=BACKUPS/(release_id+'.json')
    if receipt.exists():raise RuntimeError('Deployment receipt already exists: '+str(receipt))
    backup_dir=BACKUPS/release_id
    backup_dir.mkdir(mode=0o700)
    originals={}
    targets=[WEBROOT/'index.html',WEBROOT/'version.json',UNIT,site]
    for i,target in enumerate(targets):
        if target.is_symlink():raise RuntimeError('Refusing deployment target symlink '+str(target))
        if target.exists():
            backup=backup_dir/('file-'+str(i))
            shutil.copy2(target,backup)
            originals[str(target)]=str(backup)
        else:
            originals[str(target)]=None
    info={'version':version,'release_id':release_id,'new_release':str(next_release),'previous_current':old_current,
          'unit_preexisting':UNIT.exists(),'files':originals}
    atomic_write(receipt,json.dumps(info,indent=2).encode(),0o600)
    try:
        next_link=BASE/'.current-next'
        next_link.unlink(missing_ok=True)
        next_link.symlink_to(next_release)
        os.replace(next_link,CURRENT)
        atomic_write(UNIT,(stage/'deploy/vehiclelab.service').read_bytes())
        shell('systemctl','daemon-reload')
        shell('systemctl','enable','--now','vehiclelab-flask',timeout=60)
        shell('systemctl','restart','vehiclelab-flask',timeout=60)
        # Verify the actual running Flask release and open SQLite before touching Nginx.
        latest_error=None
        for _ in range(18):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8766/api/health',timeout=2) as resp:
                    health=json.load(resp)
                if health.get('ok') and health.get('version')==version and health.get('storage')=='sqlite':
                    latest_error=None
                    break
                latest_error='Backend health version/storage mismatch'
            except Exception as error:latest_error=str(error)
            time.sleep(1)
        if latest_error:raise RuntimeError('Flask health check failed: '+latest_error)
        patched=insert_api_location(site.read_text())
        if patched!=site.read_text():
            atomic_write(site,patched.encode())
            shell('nginx','-t',timeout=30)
            shell('systemctl','reload','nginx',timeout=30)
        for name in ('index.html','version.json'):
            atomic_write(WEBROOT/name,(stage/name).read_bytes())
        report_mail_prerequisites()
        # Read-only Blender status during deployments. Installing large Ubuntu
        # packages on this multi-site server is deliberately a separate, explicit
        # maintenance action: python deploy/install.py --blender-install.
        blender=shutil.which('blender')
        print('BLENDER ASSET WORKER: '+(blender or
              'not installed (offline rendering disabled; run separate admin install)'),flush=True)
        print('DEPLOYED '+version+'; Flask healthy; SQLite data preserved; receipt='+str(receipt))
        return receipt
    except Exception:
        rollback(receipt)
        raise


# Offline, administrator-operated Blender renderer. Kept in the existing
# deployment module to remain compatible with watcher v2.3.1 ZIP manifests.
# No public HTTP route accepts untrusted GLB jobs or shares the Flask secrets.
BLENDER_WORKER_SOURCE = "from pathlib import Path\nfrom mathutils import Vector\nimport sys\nimport json\nimport argparse\n\ndef render_with_bpy(source: Path, target: Path, decimate: float):\n    import bpy\n    from mathutils import Vector\n    bpy.ops.object.select_all(action='SELECT')\n    bpy.ops.object.delete(use_global=False)\n    bpy.ops.import_scene.gltf(filepath=str(source))\n    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']\n    if not meshes:\n        raise ValueError('Imported GLB contains no mesh')\n    if decimate < 0.999:\n        for obj in meshes:\n            bpy.context.view_layer.objects.active = obj\n            obj.select_set(True)\n            # Do not decimate skinned or shape-key meshes; preserve animations.\n            if not obj.vertex_groups and not obj.data.shape_keys:\n                mod = obj.modifiers.new('VehicleLab decimation', 'DECIMATE')\n                mod.ratio = decimate\n                try: bpy.ops.object.modifier_apply(modifier=mod.name)\n                except RuntimeError: obj.modifiers.remove(mod)\n            obj.select_set(False)\n    target.mkdir(parents=True, exist_ok=True)\n    dest = target / 'optimized.glb'\n    kwargs = dict(filepath=str(dest), export_format='GLB', export_animations=True)\n    try:\n        bpy.ops.export_scene.gltf(**kwargs, export_draco_mesh_compression_enable=True,\n                                  export_draco_mesh_compression_level=6)\n        compressor = 'draco'\n    except (TypeError, RuntimeError):\n        bpy.ops.export_scene.gltf(**kwargs)\n        compressor = 'none (Blender glTF exporter unavailable)'\n    bpy.context.view_layer.update()\n    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]\n    mini = Vector(tuple(min(v[i] for v in points) for i in range(3)))\n    maxi = Vector(tuple(max(v[i] for v in points) for i in range(3)))\n    center = (mini + maxi) * .5\n    extent = max((maxi - mini).length, 1.0)\n    bpy.ops.object.camera_add(location=center + Vector((extent, -extent, extent)))\n    camera = bpy.context.object\n    camera.data.type = 'ORTHO'\n    camera.data.ortho_scale = extent * 1.35\n    bpy.context.scene.camera = camera\n    for position,energy,size in [((1.2,-.8,1.5),1100,5),((-1,.7,.8),650,6),((0,1.5,1.0),650,8)]:\n        bpy.ops.object.light_add(type='AREA', location=center+Vector(position)*extent)\n        light=bpy.context.object\n        light.data.energy=energy\n        light.data.shape='DISK'\n        light.data.size=size\n        direction=center-light.location\n        light.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()\n    world=bpy.data.worlds.new('Vehicle Lab studio')\n    world.use_nodes=True\n    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.24,.32,.40,1)\n    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.85\n    bpy.context.scene.world=world\n    scene=bpy.context.scene\n    engines={entry.identifier for entry in scene.bl_rna.properties['render'].fixed_type.properties} if False else []\n    try: scene.render.engine='BLENDER_EEVEE_NEXT'\n    except TypeError: scene.render.engine='BLENDER_EEVEE'\n    scene.render.image_settings.file_format='PNG'\n    scene.render.film_transparent=False\n    scene.render.resolution_x=960\n    scene.render.resolution_y=720\n    scene.render.resolution_percentage=100\n    views = {'hero':(1,-1.45,.75),'front':(0,-1.6,.30),'rear':(0,1.6,.30),\n             'side':(1.8,0,.25),'top':(0,-.0001,2.1)}\n    for name,axis in views.items():\n        camera.location=center+Vector(axis).normalized()*extent*1.55\n        camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()\n        scene.render.filepath=str(target/(name+'.png'))\n        bpy.ops.render.render(write_still=True)\n    (target/'render.json').write_text(json.dumps({'views':list(views),'optimized':dest.name,\n         'compression':compressor,'source':source.name},indent=2), encoding='utf-8')\n\n\n\nparser=argparse.ArgumentParser()\nparser.add_argument('--input',required=True,type=Path)\nparser.add_argument('--output',required=True,type=Path)\nparser.add_argument('--decimate',type=float,default=1.0)\nargs=parser.parse_args(sys.argv[sys.argv.index('--')+1:])\nrender_with_bpy(args.input,args.output,args.decimate)\n"


def check_blender():
    binary=shutil.which('blender')
    print('BLENDER: '+(binary or 'not installed')+' (offline admin asset tool only)',flush=True)
    return binary


def install_blender():
    if check_blender():return
    if os.geteuid()!=0 or not Path('/etc/os-release').exists() or 'ubuntu' not in Path('/etc/os-release').read_text().lower():
        raise RuntimeError('Only an Ubuntu administrator can install Blender')
    # Never run apt during a release deployment; --blender-install is explicit.
    shell('apt-get','update',timeout=300)
    shell('apt-get','install','-y','--no-install-recommends','blender',timeout=900)
    if not check_blender():raise RuntimeError('Blender was not found after installation')


def offline_render_blender(input_file,output_dir,decimate=1.0):
    binary=check_blender()
    if not binary:raise RuntimeError('Blender not installed; use --blender-install as Ubuntu root')
    source=Path(input_file).resolve(strict=True)
    if not source.is_file() or source.suffix.lower()!='.glb' or not 12<=source.stat().st_size<=80*1024*1024:
        raise RuntimeError('Input must be GLB of 12 bytes to 80 MiB')
    if not .1<=decimate<=1.0:raise RuntimeError('Decimation range is 0.1..1.0')
    target=Path(output_dir).resolve()
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vehiclelab-blender-') as tmp:
        script=Path(tmp)/'render_asset.py';script.write_text(BLENDER_WORKER_SOURCE)
        # Remove application credential environment variables from this process.
        env={key:value for key,value in os.environ.items() if key not in
             ('VEHICLELAB_API_TOKEN','MODEL_API_KEY') and not key.endswith('_API_KEY')}
        result=subprocess.run([binary,'-b','--factory-startup','-t','2','--python',str(script),
               '--','--input',str(source),'--output',str(target),'--decimate',str(decimate)],
               capture_output=True,text=True,timeout=420,env=env)
        if result.returncode:
            raise RuntimeError('Blender failed: '+((result.stderr or '')+'\n'+(result.stdout or ''))[-2200:])
        if not all((target/(view+'.png')).is_file() for view in ('hero','front','rear','side','top')):
            raise RuntimeError('Blender did not produce all five views')
        if not (target/'optimized.glb').is_file():raise RuntimeError('Blender did not export GLB')
        print('BLENDER COMPLETE: '+str(target),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage')
    parser.add_argument('--version')
    parser.add_argument('--id')
    parser.add_argument('--rollback')
    parser.add_argument('--blender-check',action='store_true')
    parser.add_argument('--blender-install',action='store_true')
    parser.add_argument('--blender-render')
    parser.add_argument('--blender-output')
    parser.add_argument('--blender-decimate',type=float,default=1.0)
    args=parser.parse_args()
    if args.blender_check:check_blender();return
    if args.blender_install:install_blender();return
    if args.blender_render:
        if not args.blender_output:parser.error('--blender-output required')
        offline_render_blender(args.blender_render,args.blender_output,args.blender_decimate);return
    if args.rollback:
        rollback(Path(args.rollback));return
    if not args.stage or not args.version or not args.id:
        parser.error('activation requires --stage --version --id')
    activate(args.stage,args.version,args.id)

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('DEPLOY ERROR: '+str(error),file=sys.stderr)
        sys.exit(1)
