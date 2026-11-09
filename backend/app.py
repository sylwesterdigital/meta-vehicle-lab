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
import urllib.error
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, request, send_file, g
from werkzeug.exceptions import RequestEntityTooLarge

from .storage import InvalidLayout, StaleLayout, Storage, validate_uuid

PROJECT_ROOT=Path(__file__).resolve().parents[1]
MAX_ASSET=80*1024*1024


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
        guest_paths=('/api/identity/', '/api/me/', '/api/gallery', '/api/providers/test', '/api/providers/lux3d/')
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
        if reference is not None and (not isinstance(reference,str) or len(reference)>2*1024*1024
             or not reference.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,'))):
            return jsonify(error='Reference must be a PNG/JPEG/WebP data URL below 2 MB'),400
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
        return jsonify(ok=True,task_id=str(task_id),region=region,potentially_billable=True),202

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

    @app.post('/api/vehicle/generate-image')
    @app.post('/api/vehicle/tripo/start')
    @app.get('/api/vehicle/tripo/status/<task_id>')
    def ai_not_configured(task_id=None):
        return jsonify(error='AI providers are not configured on this backend. Use a dedicated provider adapter.'),501

    return app


if __name__=='__main__':
    # Local development only; production must run under Gunicorn.
    create_app().run(host='127.0.0.1',port=8766,debug=False)
