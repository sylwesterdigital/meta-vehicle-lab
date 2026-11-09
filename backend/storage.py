"""SQLite vehicle blueprint store. No Flask dependency; testable with stdlib."""
from __future__ import annotations

import json
import io
import math
import sqlite3
import time
import uuid
import hashlib
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
            rows=db.execute('SELECT id,name,revision,asset_id,visibility,created_at,updated_at FROM user_layouts '
                            'WHERE profile_id=? ORDER BY updated_at DESC LIMIT ?',
                            (validate_uuid(owner),min(100,max(1,int(limit))))).fetchall()
            return [dict(row) for row in rows]

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
