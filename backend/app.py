"""Flask JSON API and local development host for Meta Vehicle Lab."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file
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

    @app.post('/api/vehicle/generate-image')
    @app.post('/api/vehicle/tripo/start')
    @app.get('/api/vehicle/tripo/status/<task_id>')
    def ai_not_configured(task_id=None):
        return jsonify(error='AI providers are not configured on this backend. Use a dedicated provider adapter.'),501

    return app


if __name__=='__main__':
    # Local development only; production must run under Gunicorn.
    create_app().run(host='127.0.0.1',port=8766,debug=False)
