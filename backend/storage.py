"""SQLite vehicle blueprint store. No Flask dependency; testable with stdlib."""
from __future__ import annotations

import json
import io
import math
import sqlite3
import time
import uuid
import hashlib
import hmac
import os
from contextlib import contextmanager
import re
import secrets
from pathlib import Path

# Lux3D accepts small image data URLs. Image models often return multi-megabyte PNGs.
# Normalize those on our own server BEFORE a billable provider task is started.
# No provider key, source image, or returned image content is logged or persisted.
_LUX_REFERENCE_LIMIT=2*1024*1024
_LUX_REFERENCE_INPUT_LIMIT=20*1024*1024
_LUX_REFERENCE_MIMES={'image/png':'PNG','image/jpeg':'JPEG','image/webp':'WEBP'}

def prepare_lux_reference(reference):
    import base64
    import binascii
    from PIL import Image, ImageOps, features, UnidentifiedImageError

    if not isinstance(reference,str) or len(reference)>_LUX_REFERENCE_INPUT_LIMIT:
        raise ValueError('Reference image is too large to process (maximum 20 MiB encoded)')
    header,sep,encoded=reference.partition(',')
    if not sep or not header.startswith('data:') or not header.endswith(';base64'):
        raise ValueError('Reference must be a PNG/JPEG/WebP base64 data URL')
    mime=header[5:-7]
    if mime not in _LUX_REFERENCE_MIMES:
        raise ValueError('Reference format must be PNG, JPEG or WebP')
    try:
        binary=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error) as exc:
        raise ValueError('Reference image is not valid base64') from exc
    if not binary or len(binary)>15*1024*1024:
        raise ValueError('Reference decoded image exceeds 15 MiB')
    try:
        with Image.open(io.BytesIO(binary)) as original:
            if original.format!=_LUX_REFERENCE_MIMES[mime]:
                raise ValueError('Reference MIME type does not match image data')
            if original.width*original.height>24_000_000:
                raise ValueError('Reference exceeds 24 megapixels')
            original.load()
            width,height=original.size
            if len(reference)<=_LUX_REFERENCE_LIMIT:
                return reference,{'optimized':False,'original_bytes':len(binary),'output_bytes':len(binary),
                                  'width':width,'height':height,'format':mime}
            image=ImageOps.exif_transpose(original)
            has_alpha='A' in image.getbands() or 'transparency' in image.info
            if has_alpha:
                image=image.convert('RGBA')
                if not features.check('webp'):
                    background=Image.new('RGBA',image.size,(239,244,247,255))
                    background.alpha_composite(image)
                    image=background.convert('RGB')
                    has_alpha=False
            else:
                image=image.convert('RGB')
            # Reduce color detail first, then dimensions; never upscale.
            for maximum in (2560,2048,1792,1536,1280,1024,896,768,640):
                ratio=min(1.0,maximum/max(image.size))
                size=(max(1,round(image.width*ratio)),max(1,round(image.height*ratio)))
                trial=image if size==image.size else image.resize(size,Image.Resampling.LANCZOS)
                for quality in (92,86,79,70,60,48):
                    output=io.BytesIO()
                    if has_alpha:
                        trial.save(output,format='WEBP',quality=quality,method=5)
                        output_mime='image/webp'
                    else:
                        try:
                            trial.save(output,format='JPEG',quality=quality,optimize=True,progressive=True,
                                       subsampling=0 if quality>=86 else 2)
                        except OSError:
                            # libjpeg may reject optimize+progressive scans of
                            # high-entropy images; use a portable baseline encode.
                            output=io.BytesIO()
                            trial.save(output,format='JPEG',quality=quality,subsampling=2)
                        output_mime='image/jpeg'
                    optimized=base64.b64encode(output.getvalue()).decode('ascii')
                    normalized='data:'+output_mime+';base64,'+optimized
                    if len(normalized)<=_LUX_REFERENCE_LIMIT-4096:
                        return normalized,{'optimized':True,'original_bytes':len(binary),
                            'output_bytes':output.tell(),'width':trial.width,'height':trial.height,
                            'format':output_mime}
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
        raise ValueError('Reference image cannot be decoded safely') from exc
    raise ValueError('Reference could not be optimized below the Lux3D 2 MiB limit')

MAX_BLUEPRINT_BYTES = 256 * 1024
SCHEMAS = {'procedural-vehicle/v1', 'procedural-vehicle/v2', 'procedural-vehicle/v3'}
DANGEROUS_NAMES = {'apikey', 'api_key', 'secret', 'password', 'authorization', 'bearer', 'access_token', 'private_key'}

class InvalidLayout(ValueError):
    pass

class StaleLayout(Exception):
    pass


def validate_uuid(identifier: str) -> str:
    if not isinstance(identifier, str):
        raise InvalidLayout('Invalid layout ID')
    try:
        value = uuid.UUID(identifier)
    except (ValueError, AttributeError) as exc:
        raise InvalidLayout('Invalid layout ID') from exc
    if str(value) != identifier:
        raise InvalidLayout('Layout ID must be a canonical UUID')
    return identifier


def check_blueprint(blueprint: dict) -> str:
    if not isinstance(blueprint, dict):
        raise InvalidLayout('Blueprint must be an object')
    if blueprint.get('schema') not in SCHEMAS:
        raise InvalidLayout('Unsupported blueprint schema')
    if not isinstance(blueprint.get('vehicle'), dict) or not isinstance(blueprint.get('modules'), dict):
        raise InvalidLayout('Blueprint needs vehicle and modules')
    def recurse(node, depth=0):
        if depth > 24:
            raise InvalidLayout('Blueprint nesting too deep')
        if isinstance(node, dict):
            for key, val in node.items():
                if not isinstance(key, str):
                    raise InvalidLayout('Object keys must be strings')
                if any(s in key.lower() for s in DANGEROUS_NAMES):
                    raise InvalidLayout('Credentials must not be saved in blueprints')
                recurse(val, depth + 1)
        elif isinstance(node, list):
            for value in node:
                recurse(value, depth + 1)
        elif isinstance(node, float) and not math.isfinite(node):
            raise InvalidLayout('Blueprint contains a non-finite number')
        elif node is not None and not isinstance(node, (str, int, float, bool)):
            raise InvalidLayout('Unsupported blueprint value')
    recurse(blueprint)
    occupants=blueprint.get('occupants', 0)
    if not isinstance(occupants, int) or isinstance(occupants, bool) or not 0 <= occupants <= 128:
        raise InvalidLayout('Invalid occupant count')
    encoded = json.dumps(blueprint, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > MAX_BLUEPRINT_BYTES:
        raise InvalidLayout('Blueprint exceeds 256 KiB')
    return encoded


def validate_name(name):
    if not isinstance(name, str):
        raise InvalidLayout('Layout name must be text')
    name = name.strip()
    if not (1 <= len(name) <= 100) or any(ord(c) < 32 for c in name):
        raise InvalidLayout('Layout name must be 1–100 printable characters')
    return name


class Storage:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.dir / 'vehiclelab.sqlite3'
        self.assets = self.dir / 'assets'
        self.assets.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.init()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def init(self):
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS assets (
              id TEXT PRIMARY KEY,
              filename TEXT NOT NULL,
              bytes INTEGER NOT NULL,
              sha256 TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS layouts (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              blueprint TEXT NOT NULL,
              asset_id TEXT,
              revision INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              FOREIGN KEY (asset_id) REFERENCES assets(id)
            );
            CREATE INDEX IF NOT EXISTS ix_layouts_updated ON layouts(updated_at DESC);
            CREATE TABLE IF NOT EXISTS profiles (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '',
              links TEXT NOT NULL DEFAULT '{}', email TEXT NOT NULL DEFAULT '',
              phone TEXT NOT NULL DEFAULT '', avatar_ext TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profile_sessions (
              hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS user_layouts (
              id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, name TEXT NOT NULL,
              blueprint TEXT NOT NULL, asset_id TEXT, visibility TEXT NOT NULL DEFAULT 'private',
              revision INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
              FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
              FOREIGN KEY (asset_id) REFERENCES assets(id)
            );
            CREATE INDEX IF NOT EXISTS ix_user_layout_owner ON user_layouts(profile_id,updated_at DESC);
            CREATE INDEX IF NOT EXISTS ix_user_layout_gallery ON user_layouts(visibility,updated_at DESC);
            CREATE TABLE IF NOT EXISTS user_media (
              id TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('map','image')),
              name TEXT NOT NULL, payload BLOB NOT NULL,
              mime TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
              FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_user_media_owner ON user_media(profile_id,kind,updated_at DESC);
            ''')
            cols={row['name'] for row in db.execute('PRAGMA table_info(assets)')}
            if 'owner_id' not in cols:db.execute('ALTER TABLE assets ADD COLUMN owner_id TEXT')

    @staticmethod
    def summary(row):
        return {k: row[k] for k in ('id', 'name', 'revision', 'created_at', 'updated_at', 'asset_id')}

    def list_layouts(self, limit=100):
        with self.connect() as db:
            rows = db.execute('SELECT id,name,revision,created_at,updated_at,asset_id FROM layouts ORDER BY updated_at DESC LIMIT ?', (min(100,max(1,int(limit))),)).fetchall()
            return [self.summary(row) for row in rows]

    def get_layout(self, identifier):
        validate_uuid(identifier)
        with self.connect() as db:
            row = db.execute('SELECT * FROM layouts WHERE id=?', (identifier,)).fetchone()
            if not row: return None
            return {**self.summary(row), 'blueprint': json.loads(row['blueprint'])}

    def save_layout(self, *, identifier, name, blueprint, asset_id=None, revision=None):
        identifier=validate_uuid(identifier)
        name=validate_name(name)
        encoded=check_blueprint(blueprint)
        if asset_id is not None:
            validate_uuid(asset_id)
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if asset_id and db.execute('SELECT 1 FROM assets WHERE id=?',(asset_id,)).fetchone() is None:
                raise InvalidLayout('Unknown model asset')
            row=db.execute('SELECT revision,created_at FROM layouts WHERE id=?',(identifier,)).fetchone()
            if row:
                if revision is None or isinstance(revision,bool) or int(revision)!=row['revision']:
                    raise StaleLayout('Layout changed; refresh before overwriting')
                new_revision=row['revision']+1
                db.execute('UPDATE layouts SET name=?,blueprint=?,asset_id=?,revision=?,updated_at=? WHERE id=?',
                           (name,encoded,asset_id,new_revision,now,identifier))
                created=row['created_at']
            else:
                if revision not in (None,0):
                    raise StaleLayout('Layout no longer exists; save as a copy')
                new_revision=1
                db.execute('INSERT INTO layouts(id,name,blueprint,asset_id,revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                           (identifier,name,encoded,asset_id,new_revision,now,now))
                created=now
            return {'id':identifier,'name':name,'revision':new_revision,'created_at':created,'updated_at':now,'asset_id':asset_id}

    def delete_layout(self, identifier, revision):
        validate_uuid(identifier)
        if not isinstance(revision,int) or isinstance(revision,bool):
            raise InvalidLayout('Revision required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM layouts WHERE id=?',(identifier,)).fetchone()
            if row is None:return False
            if row['revision']!=revision:raise StaleLayout('Layout changed; refresh before deleting')
            db.execute('DELETE FROM layouts WHERE id=?',(identifier,))
            return True

    # Guest credentials are random 256-bit bearer secrets. UUIDs are identifiers,
    # never authentication. SQLite only stores a SHA-256 digest of the secret.
    @staticmethod
    def public_profile(row):
        return {'id':row['id'],'name':row['name'],'bio':row['bio'],
                'links':json.loads(row['links']), 'email':row['email'],
                'phone':row['phone'],'avatar_url':
                    '/api/identity/avatar/'+row['id'] if row['avatar_ext'] else None,
                'created_at':row['created_at'],'updated_at':row['updated_at']}

    def create_guest(self,name):
        name=validate_name(name)
        if len(name)>50:raise InvalidLayout('Username must be 50 characters or less')
        token=secrets.token_urlsafe(40)
        identifier=str(uuid.uuid4())
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('INSERT INTO profiles(id,name,created_at,updated_at) VALUES(?,?,?,?)',
                       (identifier,name,now,now))
            db.execute('INSERT INTO profile_sessions(hash,profile_id,created_at) VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(),identifier,now))
        return self.get_profile(identifier),token

    def identity(self,token):
        if not isinstance(token,str) or not 40<=len(token)<=160:return None
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row=db.execute('SELECT p.* FROM profiles p JOIN profile_sessions s ON s.profile_id=p.id WHERE s.hash=?',
                           (token_hash,)).fetchone()
            return self.public_profile(row) if row else None

    def get_profile(self,identifier):
        validate_uuid(identifier)
        with self.connect() as db:
            row=db.execute('SELECT * FROM profiles WHERE id=?',(identifier,)).fetchone()
            return self.public_profile(row) if row else None

    def update_profile(self,owner,values):
        identifier=validate_uuid(owner)
        name=validate_name(values.get('name'))
        if len(name)>50:raise InvalidLayout('Username too long')
        def clean(key,maxlen):
            value=values.get(key,'')
            if not isinstance(value,str) or len(value)>maxlen or any(ord(ch)<32 and ch not in '\n\t' for ch in value):
                raise InvalidLayout('Invalid '+key)
            return value.strip()
        bio=clean('bio',600);email=clean('email',120);phone=clean('phone',40)
        if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise InvalidLayout('Invalid email')
        links=values.get('links',{})
        if not isinstance(links,dict) or len(links)>8:raise InvalidLayout('Invalid social links')
        for key,value in links.items():
            if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,24}',key):raise InvalidLayout('Invalid link name')
            if not isinstance(value,str) or len(value)>300 or (value and not value.startswith('https://')):
                raise InvalidLayout('Links must be HTTPS addresses')
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('UPDATE profiles SET name=?,bio=?,links=?,email=?,phone=?,updated_at=? WHERE id=?',
                (name,bio,json.dumps(links),email,phone,now,identifier))
        return self.get_profile(identifier)

    def set_avatar(self,identifier,ext):
        if ext not in ('png','jpg','webp'):raise InvalidLayout('Invalid avatar type')
        with self.connect() as db:
            db.execute('UPDATE profiles SET avatar_ext=?,updated_at=? WHERE id=?',
                (ext,int(time.time()*1000),validate_uuid(identifier)))

    def own_layouts(self,owner,limit=100):
        with self.connect() as db:
            rows=db.execute('SELECT id,name,revision,asset_id,visibility,created_at,updated_at,blueprint FROM user_layouts '
                            'WHERE profile_id=? ORDER BY updated_at DESC LIMIT ?',
                            (validate_uuid(owner),min(100,max(1,int(limit))))).fetchall()
            result=[]
            for row in rows:
                item=dict(row)
                try:
                    metadata=json.loads(item.pop('blueprint')).get('metadata') or {}
                    images=metadata.get('images') or []
                    hero=images[0].get('data') if images and isinstance(images[0],dict) else None
                    item['preview']=hero if isinstance(hero,str) and len(hero)<125000 and hero.startswith((
                        'data:image/jpeg;base64,','data:image/png;base64,')) else None
                    item['category']=metadata.get('category') or 'Vehicle'
                except (ValueError,TypeError,AttributeError,IndexError):
                    item['preview']=None
                result.append(item)
            return result

    def own_layout(self,owner,identifier):
        with self.connect() as db:
            row=db.execute('SELECT * FROM user_layouts WHERE profile_id=? AND id=?',
                           (validate_uuid(owner),validate_uuid(identifier))).fetchone()
            return {**dict(row),'blueprint':json.loads(row['blueprint'])} if row else None

    def user_save_layout(self,owner,identifier,name,blueprint,visibility='private',revision=None,asset_id=None):
        owner=validate_uuid(owner);identifier=validate_uuid(identifier)
        name=validate_name(name);encoded=check_blueprint(blueprint)
        if visibility not in ('public','private'):raise InvalidLayout('Invalid visibility')
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if asset_id:
                validate_uuid(asset_id)
                asset=db.execute('SELECT owner_id FROM assets WHERE id=?',(asset_id,)).fetchone()
                if not asset or asset['owner_id']!=owner:raise InvalidLayout('Model asset is not owned by this profile')
            row=db.execute('SELECT profile_id,revision,created_at FROM user_layouts WHERE id=?',(identifier,)).fetchone()
            if row:
                if row['profile_id']!=owner:raise InvalidLayout('Layout is owned by another profile')
                if type(revision)!=int or revision!=row['revision']:raise StaleLayout('Layout changed; reload before editing')
                newrev=row['revision']+1;created=row['created_at']
                db.execute('UPDATE user_layouts SET name=?,blueprint=?,asset_id=?,visibility=?,revision=?,updated_at=? WHERE id=?',
                           (name,encoded,asset_id,visibility,newrev,now,identifier))
            else:
                if revision not in (None,0):raise StaleLayout('Deleted layout cannot be recreated by stale update')
                newrev=1;created=now
                db.execute('INSERT INTO user_layouts(id,profile_id,name,blueprint,asset_id,visibility,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                           (identifier,owner,name,encoded,asset_id,visibility,newrev,now,now))
        return {'id':identifier,'name':name,'asset_id':asset_id,'visibility':visibility,
                'revision':newrev,'created_at':created,'updated_at':now}

    def user_delete_layout(self,owner,identifier,revision):
        if type(revision)!=int:raise InvalidLayout('Revision required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM user_layouts WHERE id=? AND profile_id=?',
                           (validate_uuid(identifier),validate_uuid(owner))).fetchone()
            if not row:return False
            if revision!=row['revision']:raise StaleLayout('Layout changed; reload before deleting')
            db.execute('DELETE FROM user_layouts WHERE id=?',(identifier,))
        return True

    def own_media_list(self,owner,kind=None,limit=100):
        owner=validate_uuid(owner)
        if kind not in (None,'map','image'):raise InvalidLayout('Invalid media category')
        with self.connect() as db:
            if kind:
                rows=db.execute('SELECT id,kind,name,mime,length(payload) AS bytes,created_at,updated_at '
                                'FROM user_media WHERE profile_id=? AND kind=? '
                                'ORDER BY updated_at DESC LIMIT ?',
                                (owner,kind,min(max(int(limit),1),200))).fetchall()
            else:
                rows=db.execute('SELECT id,kind,name,mime,length(payload) AS bytes,created_at,updated_at '
                                'FROM user_media WHERE profile_id=? '
                                'ORDER BY updated_at DESC LIMIT ?',
                                (owner,min(max(int(limit),1),200))).fetchall()
            summaries=[dict(row) for row in rows]
            # Small private vector-map previews, not full map payloads.
            for item in summaries:
                if item['kind']!='map':continue
                row=db.execute('SELECT payload FROM user_media WHERE id=? AND profile_id=?',
                               (item['id'],owner)).fetchone()
                if not row:continue
                try:
                    raw=json.loads(row['payload'])
                    item['preview']={'objects':[{k:o[k] for k in ('kind','x','z','w','d','angle') if k in o}
                            for o in raw.get('objects',[])[:70]]}
                except (ValueError,TypeError,KeyError):item['preview']={'objects':[]}
            return summaries

    def own_media(self,owner,identifier):
        with self.connect() as db:
            row=db.execute('SELECT id,kind,name,mime,payload FROM user_media WHERE profile_id=? AND id=?',
                           (validate_uuid(owner),validate_uuid(identifier))).fetchone()
            return dict(row) if row else None

    def save_media(self,owner,kind,name,payload,mime,identifier=None):
        owner=validate_uuid(owner)
        if kind not in ('map','image'):raise InvalidLayout('Invalid media category')
        name=validate_name(name)
        if len(name)>100:raise InvalidLayout('Media name too long')
        if not isinstance(payload,(bytes,bytearray)):raise InvalidLayout('Invalid media data')
        maximum=256*1024 if kind=='map' else 2*1024*1024
        if not 1<=len(payload)<=maximum:raise InvalidLayout('Media exceeds category size limit')
        if kind=='map':
            if mime!='application/json':raise InvalidLayout('Map must be JSON')
            try:
                obj=json.loads(payload)
                if obj.get('schema') not in ('vehiclelab-testmap/v2','vehiclelab-testmap/v3'):
                    raise InvalidLayout('Unsupported map schema')
                if not isinstance(obj.get('objects'),list) or len(obj['objects'])>250:
                    raise InvalidLayout('Invalid map objects')
            except (ValueError,UnicodeError,AttributeError,TypeError) as e:
                raise InvalidLayout('Invalid map JSON') from e
        elif mime not in ('image/png','image/jpeg','image/webp'):
            raise InvalidLayout('Unsupported image MIME')
        identifier=validate_uuid(identifier) if identifier else str(uuid.uuid4())
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count=db.execute('SELECT count(*) FROM user_media WHERE profile_id=?',(owner,)).fetchone()[0]
            exists=db.execute('SELECT id FROM user_media WHERE id=? AND profile_id=?',(identifier,owner)).fetchone()
            if not exists and count>=250:raise InvalidLayout('Media library limit reached')
            if exists:
                db.execute('UPDATE user_media SET kind=?,name=?,mime=?,payload=?,updated_at=? WHERE id=? AND profile_id=?',
                           (kind,name,mime,bytes(payload),now,identifier,owner))
            else:
                db.execute('INSERT INTO user_media(id,profile_id,kind,name,mime,payload,created_at,updated_at) '
                           'VALUES(?,?,?,?,?,?,?,?)',(identifier,owner,kind,name,mime,bytes(payload),now,now))
        return {'id':identifier,'kind':kind,'name':name,'bytes':len(payload),'updated_at':now}

    def delete_media(self,owner,identifier):
        with self.connect() as db:
            cursor=db.execute('DELETE FROM user_media WHERE profile_id=? AND id=?',
                              (validate_uuid(owner),validate_uuid(identifier)))
            return cursor.rowcount>0

    def own_models_list(self,owner,limit=100):
        with self.connect() as db:
            rows=db.execute('SELECT id,filename AS name,bytes,created_at FROM assets '
                            'WHERE owner_id=? ORDER BY created_at DESC LIMIT ?',
                            (validate_uuid(owner),min(100,max(1,int(limit))))).fetchall()
            return [dict(row) for row in rows]

    def gallery(self,limit=40):
        with self.connect() as db:
            rows=db.execute('SELECT l.id,l.name,l.revision,l.created_at,l.updated_at,l.asset_id,l.blueprint,p.name AS creator_name,p.id AS creator_id '
                            'FROM user_layouts l JOIN profiles p ON l.profile_id=p.id '
                            "WHERE l.visibility='public' ORDER BY l.updated_at DESC LIMIT ?",(min(80,max(1,int(limit))),)).fetchall()
            results=[]
            for row in rows:
                value=dict(row)
                blueprint=json.loads(value.pop('blueprint'))
                metadata=blueprint.get('metadata') or {}
                images=metadata.get('images') or []
                hero=images[0].get('data') if images and isinstance(images[0],dict) else None
                value['preview']=hero if isinstance(hero,str) and len(hero)<65000 and hero.startswith(('data:image/jpeg;base64,','data:image/png;base64,')) else None
                value['category']=metadata.get('category') or (blueprint.get('vehicle') or {}).get('category') or 'Vehicle'
                results.append(value)
            return results

    def gallery_layout(self,identifier):
        with self.connect() as db:
            row=db.execute('SELECT l.*,p.name AS creator_name FROM user_layouts l JOIN profiles p ON l.profile_id=p.id '
                           'WHERE l.id=? AND l.visibility=?',(validate_uuid(identifier),'public')).fetchone()
            return {**dict(row),'blueprint':json.loads(row['blueprint'])} if row else None

    def add_asset(self, *, identifier, filename, size, sha256, owner_id=None):
        validate_uuid(identifier)
        if not isinstance(size,int) or not 20<=size<=80*1024*1024:raise InvalidLayout('Invalid model asset size')
        if not isinstance(filename,str) or len(filename)>120:raise InvalidLayout('Invalid model filename')
        if owner_id:validate_uuid(owner_id)
        with self.connect() as db:
            db.execute('INSERT INTO assets(id,filename,bytes,sha256,created_at,owner_id) VALUES (?,?,?,?,?,?)',
                       (identifier,filename,size,sha256,int(time.time()*1000),owner_id))

    def get_asset(self,identifier):
        validate_uuid(identifier)
        with self.connect() as db:
            row=db.execute('SELECT * FROM assets WHERE id=?',(identifier,)).fetchone()
            return dict(row) if row else None


# ===== PRIVATE VEHICLE RADIO v0.3.14 =====
MAX_TRACK = 35 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
MAX_TRACKS = 150
EXT_MIME = {'.mp3':'audio/mpeg','.m4a':'audio/mp4','.mp4':'audio/mp4',
            '.wav':'audio/wav','.ogg':'audio/ogg','.opus':'audio/ogg','.flac':'audio/flac'}

class RadioError(ValueError):
    pass


def metadata(path: Path, fallback_title='Audio track'):
    """Read metadata from the actual codec, never trust uploaded tags as HTML."""
    from mutagen import File as AudioFile
    from PIL import Image
    try:
        original=AudioFile(str(path))
        if original is None or not getattr(original,'info',None):
            raise RadioError('Audio codec or file is not supported')
        duration=float(getattr(original.info,'length',0))
        if not .1 < duration < 5*3600:raise RadioError('Invalid track duration')
        easy=AudioFile(str(path),easy=True)
        def tag(key):
            values=easy.get(key,[]) if easy is not None else []
            return str(values[0])[:180] if values else ''
        title=tag('title') or fallback_title[:160]
        artist=tag('artist') or 'Unknown artist'
        album=tag('album') or 'Unknown album'
        art=None
        tags=getattr(original,'tags',None)
        if tags is not None:
            try:
                if hasattr(tags,'getall'):
                    frames=tags.getall('APIC')
                    if frames:art=frames[0].data
                if not art and 'covr' in tags:
                    covers=tags['covr'];art=bytes(covers[0]) if covers else None
            except (KeyError,IndexError,TypeError,AttributeError):pass
        if not art and getattr(original,'pictures',None):
            art=original.pictures[0].data
        cover=None
        if art and len(art)<8*1024*1024:
            try:
                with Image.open(io.BytesIO(art)) as image:
                    if image.width*image.height<12_000_000:
                        image=image.convert('RGB');image.thumbnail((320,320))
                        output=io.BytesIO();image.save(output,'JPEG',quality=78,optimize=True)
                        cover=output.getvalue()
            except (OSError,ValueError):pass
        return title,artist,album,round(duration,2),cover
    except RadioError:raise
    except Exception as exc:raise RadioError('Invalid or unsupported audio stream') from exc


class RadioStore:
    def __init__(self, data_dir):
        self.dir=Path(data_dir)/'radio'
        self.dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=self.dir/'radio.sqlite3'
        self.files=self.dir/'audio';self.files.mkdir(exist_ok=True,mode=0o700)
        self.secret_file=self.dir/'signing-key'
        if not self.secret_file.exists():
            try:
                fd=os.open(self.secret_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as f:f.write(secrets.token_bytes(32))
            except FileExistsError:pass
        self.key=self.secret_file.read_bytes()
        if len(self.key)!=32:raise RadioError('Invalid radio signing key')
        self.init()

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=15)
        try:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=10000')
            with db:
                yield db
        finally:
            db.close()

    def init(self):
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS tracks(
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                artist TEXT NOT NULL, album TEXT NOT NULL, duration REAL NOT NULL,
                mime TEXT NOT NULL, suffix TEXT NOT NULL, bytes INTEGER NOT NULL,
                cover BLOB, created INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS tracks_owner ON tracks(owner,created DESC);
            CREATE TABLE IF NOT EXISTS playlists(
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                demo INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, updated INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS playlists_owner ON playlists(owner,updated DESC);
            CREATE TABLE IF NOT EXISTS playlist_items(
                playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                position INTEGER NOT NULL, PRIMARY KEY(playlist_id,position));
            ''')
            if not db.execute('SELECT id FROM playlists WHERE demo=1').fetchone():
                now=int(time.time());db.execute('INSERT INTO playlists VALUES(?,?,?,?,?,?)',
                  (str(uuid.uuid4()),'admin','Vehicle Lab Demo Radio',1,now,now))

    def tracks_for(self,owner):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,owner,title,artist,album,duration,mime,bytes,created, '
                '(cover IS NOT NULL) AS has_cover FROM tracks WHERE owner IN (?,?) ORDER BY created DESC',
                (owner,'admin'))]

    def track(self,identifier):
        with self.connect() as db:
            row=db.execute('SELECT * FROM tracks WHERE id=?',(identifier,)).fetchone()
            return dict(row) if row else None

    def playlists_for(self,owner):
        with self.connect() as db:
            playlists=db.execute('SELECT * FROM playlists WHERE owner IN (?,?) ORDER BY demo DESC,updated DESC',
                (owner,'admin')).fetchall()
            return [{**dict(row),'track_ids':[r['track_id'] for r in db.execute(
                'SELECT track_id FROM playlist_items WHERE playlist_id=? ORDER BY position',(row['id'],))]}
                for row in playlists]

    def add_track(self,owner,uploaded):
        filename=(uploaded.filename or '').rsplit('/',1)[-1].rsplit('\\',1)[-1]
        suffix=Path(filename).suffix.lower()
        if suffix not in EXT_MIME:raise RadioError('Use MP3, WAV, M4A, OGG, Opus or FLAC')
        with self.connect() as db:
            row=db.execute('SELECT COUNT(*) AS total,COALESCE(SUM(bytes),0) AS size FROM tracks WHERE owner=?',(owner,)).fetchone()
            if row['total']>=MAX_TRACKS:raise RadioError('Track limit reached')
            if row['size']>=MAX_TOTAL:raise RadioError('Audio storage limit reached')
        identifier=str(uuid.uuid4());target=self.files/(identifier+suffix)
        size=0
        try:
            with target.open('xb') as output:
                os.chmod(target,0o600)
                while True:
                    chunk=uploaded.stream.read(65536)
                    if not chunk:break
                    size+=len(chunk)
                    if size>MAX_TRACK:raise RadioError('Track exceeds 35 MB')
                    output.write(chunk)
            if size<128:raise RadioError('Empty audio file')
            title,artist,album,duration,cover=metadata(target,Path(filename).stem)
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT COALESCE(SUM(bytes),0) AS total FROM tracks WHERE owner=?',(owner,)).fetchone()
                if row['total']+size>MAX_TOTAL:raise RadioError('Storage quota exceeded')
                db.execute('INSERT INTO tracks VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (identifier,owner,title,artist,album,duration,EXT_MIME[suffix],suffix,size,cover,int(time.time())))
            return {'id':identifier,'title':title,'artist':artist,'album':album,'duration':duration,
                    'owner':owner,'has_cover':bool(cover),'bytes':size}
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def delete_track(self,owner,identifier):
        track=self.track(identifier)
        if not track or track['owner']!=owner:return False
        with self.connect() as db:db.execute('DELETE FROM tracks WHERE id=? AND owner=?',(identifier,owner))
        (self.files/(identifier+track['suffix'])).unlink(missing_ok=True)
        return True

    def save_playlist(self,owner,name,track_ids,identifier=None,demo=False):
        if not isinstance(name,str) or not 1<=len(name.strip())<=90:raise RadioError('Playlist name must be 1–90 characters')
        if not isinstance(track_ids,list) or len(track_ids)>300 or any(not isinstance(x,str) for x in track_ids):
            raise RadioError('Invalid playlist tracks')
        identifier=identifier or str(uuid.uuid4());now=int(time.time())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT owner,demo FROM playlists WHERE id=?',(identifier,)).fetchone()
            if existing and (existing['owner']!=owner or bool(existing['demo'])!=bool(demo)):
                raise RadioError('Playlist is not editable by this user')
            for track in track_ids:
                row=db.execute('SELECT owner FROM tracks WHERE id=?',(track,)).fetchone()
                if not row or row['owner'] not in (owner,'admin'):
                    raise RadioError('Playlist contains a track not available to this user')
            if existing:db.execute('UPDATE playlists SET name=?,updated=? WHERE id=?',(name.strip(),now,identifier))
            else:db.execute('INSERT INTO playlists VALUES(?,?,?,?,?,?)',(identifier,owner,name.strip(),int(demo),now,now))
            db.execute('DELETE FROM playlist_items WHERE playlist_id=?',(identifier,))
            db.executemany('INSERT INTO playlist_items VALUES(?,?,?)',[(identifier,x,i) for i,x in enumerate(track_ids)])
        return identifier

    def delete_playlist(self,owner,identifier):
        with self.connect() as db:
            cur=db.execute('DELETE FROM playlists WHERE id=? AND owner=? AND demo=0',(identifier,owner))
            return bool(cur.rowcount)

    def sign(self,identifier,expires):
        message=f'{identifier}:{int(expires)}'.encode()
        return hmac.new(self.key,message,hashlib.sha256).hexdigest()

    def verify(self,identifier,expires,signature):
        try:until=int(expires)
        except (ValueError,TypeError):return False
        if until<time.time() or until>time.time()+3700:return False
        return isinstance(signature,str) and hmac.compare_digest(self.sign(identifier,until),signature)


def register_radio(app,data_dir,guest_or_error):
    """Register routes; /api/radio/ paths must bypass the legacy admin before_request."""
    from flask import jsonify, request, send_file
    store=RadioStore(data_dir)
    app.extensions['vehicle_radio']=store
    def owner():
        member,error=guest_or_error()
        return (member['id'],None) if member else (None,error)
    def admin():
        configured=app.config.get('API_TOKEN') or os.environ.get('VEHICLELAB_API_TOKEN') or ''
        header=request.headers.get('Authorization','')
        if not configured or not header.startswith('Bearer ') or not hmac.compare_digest(header[7:],configured):
            return jsonify(error='Administrator authorization required'),401
        return None
    def signed_entry(track):
        expiry=int(time.time()+3300)
        return {'stream_url':f'/api/radio/stream/{track["id"]}?expires={expiry}&sig={store.sign(track["id"],expiry)}',
                'cover_url':f'/api/radio/cover/{track["id"]}?expires={expiry}&sig={store.sign(track["id"],expiry)}' if track.get('has_cover') else None}
    def make_library(user):
        tracks=store.tracks_for(user)
        return {'tracks':[{k:v for k,v in track.items() if k!='owner'} | signed_entry(track) | {'demo':track['owner']=='admin'} for track in tracks],
                'playlists':store.playlists_for(user)}

    @app.get('/api/radio/library')
    def radio_library():
        user,error=owner()
        if error:return error
        return jsonify(make_library(user))

    @app.post('/api/radio/tracks')
    def radio_upload():
        user,error=owner()
        if error:return error
        file=request.files.get('file')
        if not file:return jsonify(error='Audio file required'),400
        try:return jsonify(track=store.add_track(user,file)),201
        except RadioError as exc:return jsonify(error=str(exc)),400

    @app.delete('/api/radio/tracks/<identifier>')
    def radio_delete(identifier):
        user,error=owner()
        if error:return error
        return ('',204) if store.delete_track(user,identifier) else (jsonify(error='Track not found'),404)

    @app.post('/api/radio/playlists')
    def radio_new_playlist():
        user,error=owner()
        if error:return error
        data=request.get_json(silent=True) or {}
        try:
            identifier=store.save_playlist(user,data.get('name'),data.get('track_ids',[]))
            return jsonify(id=identifier),201
        except RadioError as exc:return jsonify(error=str(exc)),400

    @app.put('/api/radio/playlists/<identifier>')
    def radio_update_playlist(identifier):
        user,error=owner()
        if error:return error
        data=request.get_json(silent=True) or {}
        try:
            # Explicit existence check prevents changing IDs into new records.
            if not any(p['id']==identifier and p['owner']==user for p in store.playlists_for(user)):
                return jsonify(error='Playlist not found'),404
            store.save_playlist(user,data.get('name'),data.get('track_ids',[]),identifier=identifier)
            return jsonify(id=identifier)
        except RadioError as exc:return jsonify(error=str(exc)),400

    @app.delete('/api/radio/playlists/<identifier>')
    def radio_remove_playlist(identifier):
        user,error=owner()
        if error:return error
        return ('',204) if store.delete_playlist(user,identifier) else (jsonify(error='Playlist not found'),404)

    @app.get('/api/radio/stream/<identifier>')
    def radio_stream(identifier):
        track=store.track(identifier)
        if not track or not store.verify(identifier,request.args.get('expires'),request.args.get('sig')):
            return jsonify(error='Audio link expired or invalid'),403
        path=store.files/(identifier+track['suffix'])
        if not path.is_file():return jsonify(error='Audio unavailable'),404
        response=send_file(path,mimetype=track['mime'],conditional=True,as_attachment=False,
            download_name='track'+track['suffix'],max_age=0)
        response.headers['Accept-Ranges']='bytes'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='private, max-age=0'
        return response

    @app.get('/api/radio/cover/<identifier>')
    def radio_cover(identifier):
        if not store.verify(identifier,request.args.get('expires'),request.args.get('sig')):
            return jsonify(error='Cover link expired'),403
        track=store.track(identifier)
        if not track or not track.get('cover'):return jsonify(error='Cover unavailable'),404
        return send_file(io.BytesIO(track['cover']),mimetype='image/jpeg')

    @app.get('/api/radio/admin/library')
    def radio_admin_library():
        error=admin()
        if error:return error
        return jsonify(make_library('admin'))

    @app.post('/api/radio/admin/tracks')
    def radio_admin_upload():
        error=admin()
        if error:return error
        file=request.files.get('file')
        if not file:return jsonify(error='Audio file required'),400
        try:
            track=store.add_track('admin',file)
            demo=next((p for p in store.playlists_for('admin') if p['demo']),None)
            if demo:store.save_playlist('admin',demo['name'],demo['track_ids']+[track['id']],identifier=demo['id'],demo=True)
            return jsonify(track=track),201
        except RadioError as exc:return jsonify(error=str(exc)),400

    @app.put('/api/radio/admin/demo')
    def radio_admin_demo():
        error=admin()
        if error:return error
        data=request.get_json(silent=True) or {}
        demo=next((p for p in store.playlists_for('admin') if p['demo']),None)
        if not demo:return jsonify(error='Demo playlist unavailable'),404
        try:
            store.save_playlist('admin',data.get('name','Vehicle Lab Demo Radio'),data.get('track_ids',[]),identifier=demo['id'],demo=True)
            return jsonify(id=demo['id'])
        except RadioError as exc:return jsonify(error=str(exc)),400
