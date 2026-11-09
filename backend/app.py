"""Flask JSON API and local development host for Meta Vehicle Lab."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
import io
import logging
import time
import zipfile
import socket
import ipaddress
from urllib.parse import urlsplit
import urllib.error
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, request, send_file, g
from werkzeug.exceptions import RequestEntityTooLarge

from .storage import InvalidLayout, StaleLayout, Storage, validate_uuid, prepare_lux_reference

PROJECT_ROOT=Path(__file__).resolve().parents[1]
MAX_ASSET=80*1024*1024



# Results are provider-issued, short-lived URLs obtained from an authenticated
# task-status query. Never accept an arbitrary URL supplied by the browser.
_LUX_CDN_SUFFIXES=(
    '.aholo.ai', '.aholo3d.cn', '.kujiale.com', '.kujiale.cn',
    '.aliyuncs.com', '.cloudfront.net', '.amazonaws.com',
    '.myqcloud.com', '.qcloud.com', '.qunhe.com', '.qunhe.com.cn',
)

class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _validate_lux_asset_url(url):
    parsed=urlsplit(url)
    host=(parsed.hostname or '').lower().rstrip('.')
    if (parsed.scheme!='https' or parsed.username or parsed.password or
        parsed.port not in (None,443) or not host or len(url)>4096 or
        not any(host.endswith(suffix) or host==suffix[1:] for suffix in _LUX_CDN_SUFFIXES)):
        raise ValueError('Lux3D result host is not on the approved provider CDN list')
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError('Result URL could not be resolved')
        for entry in addresses:
            ip=ipaddress.ip_address(entry[4][0])
            if not ip.is_global:
                raise ValueError('Result URL resolves to a non-public network address')
    except (socket.gaierror,OSError) as exc:
        raise ValueError('Provider result host resolution failed') from exc
    return url

def _extract_lux_glb(blob):
    # No filesystem extraction and no trusting ZIP sizes/paths. Avoid zip bombs.
    if blob[:4]==b'glTF':
        glb=blob
    elif blob[:4]==b'PK\x03\x04':
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                items=[i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith('.glb')]
                if len(archive.infolist())>256 or not items:
                    raise ValueError('Lux3D ZIP does not contain a GLB model')
                item=min(items,key=lambda i:i.file_size)
                if item.file_size>MAX_ASSET or item.file_size<20:
                    raise ValueError('Lux3D ZIP GLB is outside allowed size')
                with archive.open(item) as input_file:
                    glb=input_file.read(MAX_ASSET+1)
        except (zipfile.BadZipFile,RuntimeError) as exc:
            raise ValueError('Lux3D returned an invalid ZIP') from exc
    else:
        raise ValueError('Lux3D result is neither GLB nor ZIP')
    if (len(glb)<20 or len(glb)>MAX_ASSET or glb[:4]!=b'glTF' or
        int.from_bytes(glb[4:8],'little')!=2 or
        int.from_bytes(glb[8:12],'little')!=len(glb)):
        raise ValueError('Lux3D GLB header or length is invalid')
    return glb

def _download_lux_glb(url):
    url=_validate_lux_asset_url(url)
    opener=urllib.request.build_opener(_RejectRedirect())
    request_obj=urllib.request.Request(url,headers={'Accept':'model/gltf-binary,application/zip,application/octet-stream'})
    try:
        with opener.open(request_obj,timeout=22) as response:
            if int(response.headers.get('Content-Length') or 0)>MAX_ASSET:
                raise ValueError('Lux3D result exceeds 80 MB')
            result=response.read(MAX_ASSET+1)
    except urllib.error.HTTPError as exc:
        raise ValueError('Lux3D result transfer was rejected (HTTP %s)'%exc.code) from None
    except (urllib.error.URLError,OSError,TimeoutError) as exc:
        raise ValueError('Lux3D result transfer unavailable') from exc
    if len(result)>MAX_ASSET:
        raise ValueError('Lux3D result exceeds 80 MB')
    return _extract_lux_glb(result)


def create_app(config=None):
    app=Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=MAX_ASSET+1024*1024)
    if config:app.config.update(config)
    data_dir=app.config.get('DATA_DIR') or os.environ.get('VEHICLELAB_DATA_DIR') or PROJECT_ROOT/'.data'
    store=Storage(data_dir)
    app.extensions['vehicle_store']=store
    log_dir=Path(data_dir)/'logs'
    log_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    runtime_log=log_dir/'app.log'
    handler=RotatingFileHandler(runtime_log,maxBytes=2*1024*1024,backupCount=4,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    def guest_or_error():
        token=request.headers.get('Authorization','')
        member=store.identity(token[7:]) if token.startswith('Bearer ') else None
        if not member:return None,(jsonify(error='Guest credential missing or invalid. Import a profile backup or create a guest.'),401)
        return member,None

    # Different owners never share a session token. No token, email, IP or
    # provider credential is written into application logs.
    @app.after_request
    def request_audit(response):
        if request.path.startswith('/api/') and request.path!='/api/health':
            code=response.status_code
            level=logging.ERROR if code>=500 else logging.WARNING if code>=400 else logging.INFO
            path=request.path[:170]
            app.logger.log(level,'api %s %s => %d',request.method,path,code)
        return response

    @app.after_request
    def no_store(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return jsonify(error='Request exceeds upload limit'),413

    @app.errorhandler(InvalidLayout)
    def invalid(error):
        return jsonify(error=str(error)),400

    @app.errorhandler(StaleLayout)
    def stale(error):
        return jsonify(error=str(error)),409

    @app.get('/')
    @app.get('/index.html')
    def index():
        return send_file(PROJECT_ROOT/'index.html',mimetype='text/html')

    @app.get('/version.json')
    def version():
        return send_file(PROJECT_ROOT/'version.json',mimetype='application/json')

    @app.get('/api/health')
    def health():
        with store.connect() as conn:
            conn.execute('SELECT 1').fetchone()
        release=json.loads((PROJECT_ROOT/'version.json').read_text(encoding='utf-8'))
        return jsonify(ok=True,version=release['version'],storage='sqlite',auth_enabled=bool(app.config.get('API_TOKEN') or os.environ.get('VEHICLELAB_API_TOKEN')))

    @app.before_request
    def authenticate():
        if not request.path.startswith('/api/') or request.path=='/api/health':
            return None
        # Public gallery and guest profile routes have scoped, per-profile
        # authentication below. Never let them fall through to the server
        # administrator's legacy layout token.
        guest_paths=('/api/identity/', '/api/me/', '/api/gallery', '/api/providers/test', '/api/providers/lux3d/', '/api/vehicle/generate-image')
        if request.path.startswith(guest_paths):
            if request.method not in ('GET','HEAD'):
                origin=request.headers.get('Origin')
                if origin:
                    from urllib.parse import urlsplit
                    parsed=urlsplit(origin)
                    if parsed.scheme not in ('http','https') or parsed.netloc!=request.host:
                        return jsonify(error='Cross-origin writes are not permitted'),403
            return None
        if request.path.startswith('/api/layouts') and request.content_length and request.content_length>512*1024:
            return jsonify(error='Blueprint payload exceeds 512 KiB'),413
        configured=app.config.get('API_TOKEN') or os.environ.get('VEHICLELAB_API_TOKEN') or ''
        if not configured:
            return jsonify(error='Server layout API token is not configured'),503
        header=request.headers.get('Authorization','')
        if not header.startswith('Bearer ') or not hmac.compare_digest(header[7:],configured):
            return jsonify(error='Invalid or missing server access token'),401
        # Browser origin protection, in addition to bearer token, for mutations.
        if request.method not in ('GET','HEAD'):
            origin=request.headers.get('Origin')
            if origin:
                from urllib.parse import urlsplit
                parsed=urlsplit(origin)
                if parsed.scheme not in ('http','https') or parsed.netloc!=request.host:
                    return jsonify(error='Cross-origin writes are not permitted'),403
        return None

    @app.get('/api/layouts')
    def list_layouts():
        return jsonify(layouts=store.list_layouts())

    @app.post('/api/layouts')
    def add_layout():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected JSON object'),400
        identifier=data.get('id') or str(uuid.uuid4())
        if store.get_layout(identifier) is not None:
            return jsonify(error='Layout exists; use PUT with revision'),409
        value=store.save_layout(identifier=identifier,name=data.get('name'),blueprint=data.get('blueprint'),asset_id=data.get('asset_id'))
        return jsonify(layout=value),201

    @app.get('/api/layouts/<identifier>')
    def get_layout(identifier):
        entry=store.get_layout(identifier)
        if entry is None:return jsonify(error='Layout not found'),404
        return jsonify(layout=entry)

    @app.put('/api/layouts/<identifier>')
    def put_layout(identifier):
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected JSON object'),400
        # A deleted layout is not automatically recreated by a stale PUT.
        if store.get_layout(identifier) is None:
            return jsonify(error='Layout not found'),404
        entry=store.save_layout(identifier=identifier,name=data.get('name'),blueprint=data.get('blueprint'),asset_id=data.get('asset_id'),revision=data.get('revision'))
        return jsonify(layout=entry)

    @app.delete('/api/layouts/<identifier>')
    def delete_layout(identifier):
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected revision JSON'),400
        if not store.delete_layout(identifier,data.get('revision')):
            return jsonify(error='Layout not found'),404
        return '',204

    @app.post('/api/assets')
    def upload_asset():
        if 'file' not in request.files:return jsonify(error='Expected multipart file'),400
        file=request.files['file']
        filename=(file.filename or 'model.glb').rsplit('/',1)[-1].rsplit('\\',1)[-1]
        if not filename.lower().endswith('.glb') or len(filename)>120:
            return jsonify(error='GLB file required'),400
        identifier=str(uuid.uuid4())
        destination=store.assets/(identifier+'.glb')
        hasher=hashlib.sha256()
        size=0
        try:
            with destination.open('xb') as target:
                while chunk:=file.stream.read(1024*1024):
                    size+=len(chunk)
                    if size>MAX_ASSET:raise InvalidLayout('GLB exceeds 80 MB')
                    hasher.update(chunk)
                    target.write(chunk)
            with destination.open('rb') as source: head=source.read(12)
            if len(head)!=12 or head[:4]!=b'glTF' or int.from_bytes(head[4:8],'little')!=2 or int.from_bytes(head[8:12],'little')!=size:
                raise InvalidLayout('Invalid GLB header or length')
            store.add_asset(identifier=identifier,filename=filename,size=size,sha256=hasher.hexdigest())
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return jsonify(asset={'id':identifier,'bytes':size,'sha256':hasher.hexdigest()}),201

    @app.get('/api/assets/<identifier>')
    def download_asset(identifier):
        meta=store.get_asset(identifier)
        if meta is None:return jsonify(error='Asset not found'),404
        path=store.assets/(validate_uuid(identifier)+'.glb')
        if not path.is_file():return jsonify(error='Asset file unavailable'),404
        return send_file(path,mimetype='model/gltf-binary',as_attachment=True,download_name='vehicle.glb')

    # Guest identities do not require email or password. A generated UUID is
    # not a credential; the secret is returned once and kept hashed on disk.
    @app.post('/api/identity/guest')
    def new_guest():
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict):return jsonify(error='Expected JSON object'),400
        profile,token=store.create_guest(data.get('name',''))
        app.logger.info('guest profile created')
        return jsonify(profile=profile,token=token,backup_required=True),201

    @app.get('/api/identity/me')
    def guest_me():
        member,error=guest_or_error()
        return error if error else jsonify(profile=member)

    @app.put('/api/identity/me')
    def guest_profile_update():
        member,error=guest_or_error()
        if error:return error
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected profile object'),400
        return jsonify(profile=store.update_profile(member['id'],data))

    @app.post('/api/identity/avatar')
    def upload_avatar():
        member,error=guest_or_error()
        if error:return error
        img=request.files.get('file')
        if not img:return jsonify(error='Image file required'),400
        data=img.stream.read(2*1024*1024+1)
        if len(data)>2*1024*1024:return jsonify(error='Avatar must be 2 MB or smaller'),413
        # Decode and re-encode raster pixels to prevent content spoofing.
        from PIL import Image,UnidentifiedImageError
        try:
            picture=Image.open(io.BytesIO(data));picture.load()
            if picture.format not in ('PNG','JPEG','WEBP') or max(picture.size)>4096:
                raise ValueError('Unsupported image size or format')
            picture=picture.convert('RGB');picture.thumbnail((256,256))
            target=store.dir/'profiles'
            target.mkdir(mode=0o700,exist_ok=True)
            dest=target/(member['id']+'.webp');tmp=target/(member['id']+'.next')
            picture.save(tmp,format='WEBP',quality=82,method=4)
            tmp.replace(dest)
        except (OSError,ValueError,UnidentifiedImageError):
            return jsonify(error='Invalid avatar image'),400
        store.set_avatar(member['id'],'webp')
        return jsonify(profile=store.get_profile(member['id']))

    @app.get('/api/identity/avatar/<identifier>')
    def get_avatar(identifier):
        profile=store.get_profile(identifier)
        if not profile or not profile['avatar_url']:return jsonify(error='Avatar not found'),404
        file=store.dir/'profiles'/(identifier+'.webp')
        if not file.is_file():return jsonify(error='Avatar unavailable'),404
        response=send_file(file,mimetype='image/webp',max_age=300)
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.get('/api/me/layouts')
    def my_layouts():
        member,error=guest_or_error()
        if error:return error
        return jsonify(layouts=store.own_layouts(member['id']))

    @app.post('/api/me/layouts')
    def my_new_layout():
        member,error=guest_or_error()
        if error:return error
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected layout object'),400
        identifier=data.get('id') or str(uuid.uuid4())
        if store.own_layout(member['id'],identifier):return jsonify(error='Already exists'),409
        item=store.user_save_layout(member['id'],identifier,data.get('name'),data.get('blueprint'),
                                    visibility=data.get('visibility','private'),asset_id=data.get('asset_id'))
        return jsonify(layout=item),201

    @app.get('/api/me/layouts/<identifier>')
    def my_get_layout(identifier):
        member,error=guest_or_error()
        if error:return error
        entry=store.own_layout(member['id'],identifier)
        return jsonify(layout=entry) if entry else (jsonify(error='Layout not found'),404)

    @app.put('/api/me/layouts/<identifier>')
    def my_put_layout(identifier):
        member,error=guest_or_error()
        if error:return error
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected layout object'),400
        if not store.own_layout(member['id'],identifier):return jsonify(error='Layout not found'),404
        item=store.user_save_layout(member['id'],identifier,data.get('name'),data.get('blueprint'),
                                    visibility=data.get('visibility','private'),revision=data.get('revision'),
                                    asset_id=data.get('asset_id'))
        return jsonify(layout=item)

    @app.delete('/api/me/layouts/<identifier>')
    def my_delete_layout(identifier):
        member,error=guest_or_error()
        if error:return error
        data=request.get_json(silent=True) or {}
        return ('',204) if store.user_delete_layout(member['id'],identifier,data.get('revision')) else (jsonify(error='Layout not found'),404)

    @app.get('/api/gallery')
    def gallery_list():
        return jsonify(layouts=store.gallery())

    @app.get('/api/gallery/<identifier>')
    def gallery_item(identifier):
        item=store.gallery_layout(identifier)
        if not item:return jsonify(error='Public layout not found'),404
        item.pop('profile_id',None)
        return jsonify(layout=item)

    @app.post('/api/me/assets')
    def upload_member_asset():
        member,error=guest_or_error()
        if error:return error
        file=request.files.get('file')
        if not file:return jsonify(error='GLB file required'),400
        name=(file.filename or 'model.glb').rsplit('/',1)[-1].rsplit('\\',1)[-1]
        if not name.lower().endswith('.glb') or len(name)>120:
            return jsonify(error='GLB file required'),400
        identifier=str(uuid.uuid4());dest=store.assets/(identifier+'.glb')
        hasher=hashlib.sha256();size=0
        try:
            with dest.open('xb') as target:
                while chunk:=file.stream.read(1024*1024):
                    size+=len(chunk)
                    if size>MAX_ASSET:raise InvalidLayout('GLB exceeds 80 MB')
                    hasher.update(chunk);target.write(chunk)
            with dest.open('rb') as content:header=content.read(12)
            if len(header)!=12 or header[:4]!=b'glTF' or int.from_bytes(header[4:8],'little')!=2 or int.from_bytes(header[8:12],'little')!=size:
                raise InvalidLayout('Invalid GLB header or length')
            store.add_asset(identifier=identifier,filename=name,size=size,sha256=hasher.hexdigest(),owner_id=member['id'])
        except Exception:
            dest.unlink(missing_ok=True);raise
        return jsonify(asset={'id':identifier,'bytes':size}),201

    @app.get('/api/me/assets/<identifier>')
    def my_get_asset(identifier):
        member,error=guest_or_error()
        if error:return error
        item=store.get_asset(identifier)
        if not item or item['owner_id']!=member['id']:return jsonify(error='Asset not found'),404
        return send_file(store.assets/(identifier+'.glb'),mimetype='model/gltf-binary',as_attachment=True,download_name='vehicle.glb')

    @app.get('/api/gallery/<identifier>/asset')
    def public_gallery_asset(identifier):
        item=store.gallery_layout(identifier)
        if not item or not item['asset_id']:return jsonify(error='Public asset not found'),404
        return send_file(store.assets/(item['asset_id']+'.glb'),mimetype='model/gltf-binary',as_attachment=True,download_name='vehicle.glb')

    @app.get('/api/admin/logs')
    def log_tail():
        # This is intentionally admin-only. Guest identities cannot see other
        # users' requests or server diagnostics.
        try:limit=max(10,min(300,int(request.args.get('limit','120'))))
        except (ValueError,TypeError):return jsonify(error='Invalid log limit'),400
        try:
            from collections import deque
            with runtime_log.open(encoding='utf-8',errors='replace') as f:
                lines=list(deque(f,maxlen=limit))
        except OSError:lines=[]
        return jsonify(lines=[row.rstrip('\n') for row in lines],scope='application',
                       note='Gunicorn/systemd and Mac watcher logs require server/local administrator access.')

    # International AHOLO OpenAPI uses /global; China uses the domestic gateway.
    # No account-balance endpoint is defined in the published Lux3D OpenAPI.
    LUX3D_ENDPOINTS = {
        'international': 'https://api.aholo.ai/global/lux3d/v1',
        'china': 'https://api.aholo3d.cn/lux3d/v1',
    }
    lux3d_last_create = {}

    def lux3d_request(key, region, endpoint, payload=None):
        if region not in LUX3D_ENDPOINTS:
            raise ValueError('Select international or China region')
        if not isinstance(key, str) or not 8 <= len(key) <= 512 or any(c in key for c in '\r\n'):
            raise ValueError('Lux3D API key is missing or invalid')
        if endpoint not in ('/generate/task/list?page=1&pagesize=3',
                            '/generate/text-to-3d/task/create') and not (
             endpoint.startswith('/generate/task/get?taskid=') and
             endpoint.partition('taskid=')[2].isdigit() and len(endpoint.partition('taskid=')[2]) <= 18):
            raise ValueError('Lux3D operation not permitted')
        content = None if payload is None else json.dumps(payload, separators=(',', ':')).encode('utf-8')
        req = urllib.request.Request(
            LUX3D_ENDPOINTS[region] + endpoint, data=content,
            headers={'Authorization':key, 'Accept':'application/json',
                     **({'Content-Type':'application/json'} if content is not None else {})},
            method='POST' if content is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                if int(response.headers.get('Content-Length', '0')) > 512000:
                    raise ValueError('Lux3D response exceeds expected size')
                response_data = response.read(512001)
                if len(response_data) > 512000:
                    raise ValueError('Lux3D response exceeds expected size')
                data = json.loads(response_data)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Lux3D returned HTTP {exc.code}; check API key and region') from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise RuntimeError('Could not read Lux3D response (' + type(exc).__name__ + ')') from None
        if not isinstance(data, dict) or str(data.get('c', '')) != '0':
            code=str(data.get('c', '?'))[:45] if isinstance(data,dict) else '?'
            raise RuntimeError('Lux3D API did not accept the operation (code ' + code + ')')
        return data.get('d')

    def lux3d_credential():
        member, error = guest_or_error()
        if error: return None, None, None, error
        obj = request.get_json(silent=True)
        if not isinstance(obj, dict): return None, None, None, (jsonify(error='Expected JSON object'),400)
        region = obj.get('region', 'international')
        key = obj.get('key', '')
        if region not in LUX3D_ENDPOINTS or not isinstance(key,str) or not 8 <= len(key) <= 512:
            return None, None, None, (jsonify(error='Region or API key invalid'),400)
        return member, key, region, None

    @app.post('/api/providers/lux3d/test')
    def lux3d_probe():
        member, key, region, error = lux3d_credential()
        if error:return error
        try:
            result = lux3d_request(key,region,'/generate/task/list?page=1&pagesize=3')
        except RuntimeError as exc:
            return jsonify(ok=False, error=str(exc), balance_available=False),502
        except ValueError as exc:
            return jsonify(ok=False,error=str(exc)),400
        if not isinstance(result,dict):return jsonify(error='Unexpected Lux3D task-list response'),502
        tasks=result.get('items',[])
        return jsonify(ok=True,authenticated=True,provider='lux3d',region=region,
                       check='GET task list (read-only, no generation task)',
                       total_tasks=result.get('total'),
                       recent_tasks=[{'id':t.get('taskId'),'status':t.get('status')} for t in tasks[:3]
                                     if isinstance(t,dict)] if isinstance(tasks,list) else [],
                       balance=None,balance_available=False,
                       balance_note='Lux3D OpenAPI does not document a read-only account balance endpoint.'),200

    @app.post('/api/providers/lux3d/optimize-reference')
    def lux3d_optimize_reference():
        # No provider request or credits spent. The authenticated creator sees
        # the exact resized/quantized reference before opting into a 3D task.
        member,error=guest_or_error()
        if error:return error
        obj=request.get_json(silent=True)
        if not isinstance(obj,dict):return jsonify(error='Expected reference image JSON'),400
        try:
            result,info=prepare_lux_reference(obj.get('reference_image'))
        except ValueError as exc:
            return jsonify(error=str(exc)),400
        return jsonify(ok=True,reference_image=result,**info)

    @app.post('/api/providers/lux3d/create')
    def lux3d_create_chassis():
        member, key, region, error = lux3d_credential()
        if error:return error
        obj=request.get_json(silent=True)
        if obj.get('spend_ack') is not True:
            return jsonify(error='Explicit acknowledgment of potential credits charge required'),400
        user_prompt=obj.get('prompt','')
        version=obj.get('version','G1')
        style=obj.get('style','photorealistic')
        if not isinstance(user_prompt,str) or not 10 <= len(user_prompt.strip()) <= 1000:
            return jsonify(error='Prompt must contain 10 to 1000 characters'),400
        if version not in ('G1','G1-Turbo') or style not in ('photorealistic','cartoon','anime','hand_painted','cyberpunk','fantasy','glass'):
            return jsonify(error='Unsupported model or style'),400
        # Prevent rapid duplicate charged submissions from the same profile.
        now=time.monotonic()
        if now-lux3d_last_create.get(member['id'],0)<35:
            return jsonify(error='Wait at least 35 seconds between Lux3D generation requests'),429
        reference=obj.get('reference_image')
        reference_info=None
        if reference is not None:
            try:reference,reference_info=prepare_lux_reference(reference)
            except ValueError as exc:return jsonify(error=str(exc)),400
        component=obj.get('component','chassis')
        component_prompts={
            'chassis':('A single isolated automotive EXTERIOR BODY SHELL ONLY. No wheels, tyres, rims, '
              'suspension, axles or undercarriage. No complete car assembly or people. Define precise wheel '
              'arches, functional door seams and window apertures, roof, hood and rear hatch. The body shell '
              'must fit separately procedural wheels and chassis.'),
            'bumper':'A SINGLE removable FRONT bumper assembly ONLY. No body shell, tyres or complete car.',
            'rear-bumper':'A SINGLE removable REAR bumper assembly ONLY. No body shell, tyres or complete car.',
            'headlight':'A SINGLE standalone automotive FRONT headlight module ONLY. No body shell or wheels.',
            'taillight':'A SINGLE standalone automotive REAR taillight module ONLY. No body shell or wheels.',
            'wheel':('ONE isolated automotive wheel assembly only. Accurate circular tyre with tread and alloy rim, '
                     'without any car chassis or body. Axis horizontal, centered and suitable for separate modular attachment.'),
        }
        if component not in component_prompts:
            return jsonify(error='Unsupported vehicle component'),400
        component_prompt=component_prompts[component]+' Design brief: '+user_prompt.strip()
        payload={'prompt':component_prompt,'style':style,'version':version,
                 'outputFormat':['glb','zip'] if version=='G1' else ['glb']}
        if reference:payload['img']=reference
        lux3d_last_create[member['id']]=now
        try:task_id=lux3d_request(key,region,'/generate/text-to-3d/task/create',payload)
        except RuntimeError as exc:return jsonify(error=str(exc)),502
        except ValueError as exc:return jsonify(error=str(exc)),400
        if not isinstance(task_id,(int,str)) or not str(task_id).isdigit():
            return jsonify(error='Unexpected Lux3D task identifier'),502
        app.logger.info('lux3d user generation submitted (no key or prompt logged)')
        return jsonify(ok=True,task_id=str(task_id),region=region,potentially_billable=True,reference_info=reference_info),202

    @app.post('/api/providers/lux3d/status')
    def lux3d_status():
        member,key,region,error=lux3d_credential()
        if error:return error
        task_id=request.get_json(silent=True).get('task_id','')
        if not str(task_id).isdigit() or len(str(task_id))>18:
            return jsonify(error='Invalid task identifier'),400
        try:result=lux3d_request(key,region,'/generate/task/get?taskid='+str(task_id))
        except RuntimeError as exc:return jsonify(error=str(exc)),502
        except ValueError as exc:return jsonify(error=str(exc)),400
        if not isinstance(result,dict):return jsonify(error='Unexpected task response'),502
        status=result.get('status')
        urls=[]
        for item in result.get('outputs',[]) if isinstance(result.get('outputs'),list) else []:
            if isinstance(item,dict):
                value=item.get('content','')
                if isinstance(value,str) and value.startswith('https://') and len(value)<4096:
                    urls.append(value)
        # These are provider-generated signed URLs, not same-origin proxy URLs.
        return jsonify(ok=True,task_id=str(task_id),status=status,
                       state={0:'queued',1:'running',3:'success',4:'failed',6:'canceled'}.get(status,'unknown'),
                       download_urls=urls[:6])

    @app.post('/api/providers/lux3d/import')
    def lux3d_import():
        # Server fetch is intentionally read-only: provider key belongs to this
        # request only. Download URLs are re-obtained from the provider task.
        member,key,region,error=lux3d_credential()
        if error:return error
        task_id=request.get_json(silent=True).get('task_id','')
        if not str(task_id).isdigit() or len(str(task_id))>18:
            return jsonify(error='Invalid Lux3D task ID'),400
        try:
            result=lux3d_request(key,region,'/generate/task/get?taskid='+str(task_id))
            if not isinstance(result,dict) or result.get('status')!=3:
                return jsonify(error='Lux3D task has not completed successfully'),409
            outputs=result.get('outputs',[])
            if not isinstance(outputs,list):return jsonify(error='Invalid Lux3D result list'),502
            urls=[]
            for item in outputs:
                if isinstance(item,dict):
                    u=item.get('content')
                    if isinstance(u,str) and u.startswith('https://'):
                        urls.append(u)
            if not urls:return jsonify(error='Lux3D task has no downloadable GLB or ZIP'),404
            # Prefer an explicit .glb, but some providers deliver signed URLs
            # without an extension or pack GLB in ZIP.
            urls.sort(key=lambda u:0 if '.glb' in urlsplit(u).path.lower() else 1 if '.zip' in urlsplit(u).path.lower() else 2)
            last_error='No compatible GLB result returned'
            for url in urls[:5]:
                try:
                    glb=_download_lux_glb(url)
                    app.logger.info('Lux3D completed GLB transferred to profile (bytes=%d)',len(glb))
                    return send_file(io.BytesIO(glb),mimetype='model/gltf-binary',as_attachment=True,
                                     download_name='lux3d-'+str(task_id)+'.glb')
                except ValueError as exc:
                    last_error=str(exc)
            return jsonify(error=last_error),422
        except RuntimeError as exc:return jsonify(error=str(exc)),502
        except ValueError as exc:return jsonify(error=str(exc)),400

    @app.post('/api/providers/test')
    def test_provider():
        member,error=guest_or_error()
        if error:return error
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Invalid test request'),400
        provider=data.get('provider');token=data.get('key','')
        endpoints={'openai':'https://api.openai.com/v1/models',
                   'xai':'https://api.x.ai/v1/models',
                   'meta':'https://api.meta.ai/v1/models'}
        if provider not in endpoints:
            return jsonify(error='Model listing is not supported for this provider. No request was sent.'),422
        if not isinstance(token,str) or not 5<len(token)<500:
            return jsonify(error='Invalid key length'),400
        req=urllib.request.Request(endpoints[provider],headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=9) as resp:
                result=json.load(resp)
        except urllib.error.HTTPError as exc:
            return jsonify(error='Provider rejected the key or request',provider=provider,http_status=exc.code),502
        except (TimeoutError,urllib.error.URLError,ValueError) as exc:
            app.logger.warning('provider test unavailable (%s)',type(exc).__name__)
            return jsonify(error='Provider connection failed or returned invalid JSON'),502
        data_list=result.get('data',result.get('models',[])) if isinstance(result,dict) else []
        models=[r['id'] for r in data_list if isinstance(r,dict) and isinstance(r.get('id'),str)] if isinstance(data_list,list) else []
        return jsonify(ok=True,provider=provider,count=len(models),models=models[:50],truncated=len(models)>50)

    # User-initiated image creation is scoped to a profile, not the admin API.
    # Only fixed HTTPS endpoints are permitted. Keys are forwarded in
    # memory only, never put in a database, source control or runtime log.
    image_generation_last = {}

    @app.post('/api/vehicle/generate-image')
    def generate_reference_image():
        member,error=guest_or_error()
        if error:return error
        obj=request.get_json(silent=True)
        if not isinstance(obj,dict):return jsonify(error='Expected JSON object'),400
        provider=obj.get('provider')
        key=request.headers.get('X-Provider-Key','')
        prompt=obj.get('prompt','')
        if provider not in ('openai','xai','meta'):
            return jsonify(error='Supported image providers: Meta Muse Image, OpenAI, xAI'),422
        if not isinstance(key,str) or not 12<=len(key)<=512 or '\n' in key or '\r' in key:
            return jsonify(error='Invalid provider credential'),400
        if not isinstance(prompt,str) or not 8<=len(prompt.strip())<=2500:
            return jsonify(error='Image prompt must be 8–2,500 characters'),400
        reference=obj.get('reference_image')
        if reference is not None:
            if (not isinstance(reference,str) or not reference.startswith((
                'data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')) or
                len(reference)>2*1024*1024):
                return jsonify(error='Reference must be a PNG/JPEG/WebP image under 2 MB'),400
        now=time.monotonic()
        if now-image_generation_last.get(member['id'],0)<20:
            return jsonify(error='Wait at least 20 seconds between image requests'),429
        image_generation_last[member['id']]=now
        if provider=='openai':
            endpoint='https://api.openai.com/v1/images/edits' if reference else 'https://api.openai.com/v1/images/generations'
            payload={'model':'gpt-image-2.5-flare','prompt':prompt.strip(),'n':1,
                     'size':'1024x1024','quality':'medium','output_format':'png'}
            if reference:payload['images']=[{'image_url':reference}]
        elif provider=='meta':
            # Official Meta Muse Image one-shot JSON API, not the text model
            # Responses endpoint. Text-to-image and guided image edit share
            # the same model key from the read-only /models authentication test.
            endpoint='https://api.meta.ai/v1/images/edits' if reference else 'https://api.meta.ai/v1/images/generations'
            payload={'model':'muse-image-1.0','prompt':prompt.strip(),
                     'n':1,'response_format':'b64_json','output_format':'png',
                     'reasoning_strength':'low'}
            if reference:payload['images']=[{'image_url':reference}]
        else:
            endpoint='https://api.x.ai/v1/images/edits' if reference else 'https://api.x.ai/v1/images/generations'
            payload={'model':'grok-imagine-image-2.0','prompt':prompt.strip(),
                     'n':1,'response_format':'b64_json','aspect_ratio':'1:1'}
            if reference:payload['image']={'url':reference,'type':'image_url'}
        upstream=urllib.request.Request(endpoint,
            data=json.dumps(payload,separators=(',',':')).encode('utf-8'),method='POST',
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'})
        try:
            with urllib.request.urlopen(upstream,timeout=120) as response:
                if int(response.headers.get('Content-Length') or 0)>20*1024*1024:
                    return jsonify(error='Generated image exceeds response limit'),502
                body=response.read(20*1024*1024+1)
                if len(body)>20*1024*1024:
                    return jsonify(error='Generated image exceeds response limit'),502
                result=json.loads(body)
        except urllib.error.HTTPError as exc:
            return jsonify(error='Image provider rejected request (HTTP %s)'%exc.code),502
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
            app.logger.warning('image provider request failed (%s)',type(exc).__name__)
            return jsonify(error='Image generation response unavailable'),502
        item=(result.get('data') or [{}])[0] if isinstance(result,dict) else {}
        encoded=item.get('b64_json') if isinstance(item,dict) else None
        # xAI may return a short-lived hosted image URL rather than b64_json.
        # Restrict retrieval to the provider-controlled image domain to avoid
        # letting an untrusted API response turn this server into an SSRF relay.
        if not encoded and provider=='xai' and isinstance(item,dict) and item.get('url'):
            from urllib.parse import urlsplit
            image_url=item['url'];parsed=urlsplit(image_url)
            if parsed.scheme!='https' or parsed.hostname!='imgen.x.ai' or parsed.port not in (None,443):
                return jsonify(error='Image provider returned an unexpected download host'),502
            try:
                with urllib.request.urlopen(urllib.request.Request(image_url,headers={'Accept':'image/png,image/jpeg,image/webp'}),timeout=20) as image_response:
                    # Guard possible redirects, not just the original URL.
                    final=urlsplit(image_response.geturl())
                    if final.scheme!='https' or final.hostname!='imgen.x.ai':
                        return jsonify(error='Image download redirected outside trusted provider'),502
                    image_bytes=image_response.read(14*1024*1024+1)
                    if len(image_bytes)>14*1024*1024:
                        return jsonify(error='Image provider response too large'),502
                import base64
                encoded=base64.b64encode(image_bytes).decode('ascii')
            except (urllib.error.URLError,TimeoutError,OSError) as exc:
                app.logger.warning('provider image retrieval failed (%s)',type(exc).__name__)
                return jsonify(error='Image provider download failed'),502
        if not isinstance(encoded,str) or not encoded or len(encoded)>19*1024*1024:
            return jsonify(error='Image provider returned no embedded image'),502
        # Validate base64 and image magic before returning to the browser.
        import base64
        try:bytes_image=base64.b64decode(encoded,validate=True)
        except (ValueError,base64.binascii.Error):return jsonify(error='Provider image was not valid base64'),502
        mime=('image/png' if bytes_image.startswith(b'\x89PNG\r\n\x1a\n') else
              'image/jpeg' if bytes_image.startswith(b'\xff\xd8\xff') else
              'image/webp' if bytes_image[:4]==b'RIFF' and bytes_image[8:12]==b'WEBP' else None)
        if not mime or len(bytes_image)>14*1024*1024:return jsonify(error='Provider image format was invalid'),502
        app.logger.info('reference image completed (provider=%s, bytes=%d)',provider,len(bytes_image))
        return jsonify(ok=True,image='data:'+mime+';base64,'+encoded,provider=provider)

    @app.post('/api/vehicle/tripo/start')
    @app.get('/api/vehicle/tripo/status/<task_id>')
    def ai_not_configured(task_id=None):
        return jsonify(error='AI providers are not configured on this backend. Use a dedicated provider adapter.'),501

    return app


if __name__=='__main__':
    # Local development only; production must run under Gunicorn.
    create_app().run(host='127.0.0.1',port=8766,debug=False)
