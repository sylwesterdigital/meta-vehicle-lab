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

    def safety_snapshot(self):
        """Automatic, non-destructive SQLite snapshot; rate-limited across workers.

        Snapshot is on the same host, NOT an offsite disaster-recovery backup.
        The source is copied via sqlite3.backup to preserve SQLite WAL consistency.
        """
        import fcntl
        backups=self.dir/'db-backups'
        backups.mkdir(mode=0o700,parents=True,exist_ok=True)
        with (backups/'.lock').open('a+b') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            existing=sorted(backups.glob('snapshot-*.sqlite3'))
            if existing and (time.time()-existing[-1].stat().st_mtime)<900:
                return existing[-1]
            import tempfile
            fd,name=tempfile.mkstemp(prefix='.pending-',suffix='.sqlite3',dir=backups)
            os.close(fd)
            temporary=Path(name)
            try:
                # sqlite3.Connection.__exit__ commits/rolls back but does NOT
                # close the connection. Close both source and destination
                # explicitly; macOS Python 3.15 otherwise reaches EMFILE when
                # validating many storage operations in one process.
                from contextlib import closing
                with self.connect() as source, closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                        raise OSError('SQLite safety snapshot is not valid')
                # Fully durable file before exposing as a completed backup.
                with temporary.open('rb') as binary:os.fsync(binary.fileno())
                final=backups/('snapshot-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime())+'.sqlite3')
                os.replace(temporary,final)
                for stale in sorted(backups.glob('snapshot-*.sqlite3'))[:-48]:
                    stale.unlink(missing_ok=True)
                return final
            finally:
                temporary.unlink(missing_ok=True)

    @contextmanager
    def connect(self):
        """Transactional SQLite connection with deterministic cleanup.

        A bare ``with sqlite3.connect(...)`` finalizes the transaction but
        intentionally leaves the file descriptor open. Every Storage caller
        uses ``with self.connect() as db``; this wrapper keeps the same
        commit/rollback semantics and closes the handle in all paths.
        """
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

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
            CREATE TABLE IF NOT EXISTS community_shares (
              id TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('map','model','world')),
              source_id TEXT NOT NULL, car_id TEXT,
              created_at INTEGER NOT NULL,
              FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
              UNIQUE(profile_id,kind,source_id,car_id)
            );
            CREATE INDEX IF NOT EXISTS ix_community_owner ON community_shares(profile_id,created_at DESC);
            CREATE TABLE IF NOT EXISTS geology_presets (
              id TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
              name TEXT NOT NULL, values_json TEXT NOT NULL,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
              FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_geology_owner ON geology_presets(profile_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS note_folders (
              id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, name TEXT NOT NULL,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
              FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_note_folders_owner ON note_folders(profile_id,name);
            CREATE TABLE IF NOT EXISTS user_notes (
              id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, folder_id TEXT,
              title TEXT NOT NULL, body TEXT NOT NULL,
              priority TEXT NOT NULL DEFAULT 'idea' CHECK(priority IN ('urgent','ongoing','idea')),
              revision INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
              FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
              FOREIGN KEY (folder_id) REFERENCES note_folders(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS ix_user_notes_owner ON user_notes(profile_id,updated_at DESC);
            ''')
            cols={row['name'] for row in db.execute('PRAGMA table_info(assets)')}
            if 'owner_id' not in cols:db.execute('ALTER TABLE assets ADD COLUMN owner_id TEXT')
            if 'kind' not in cols:db.execute("ALTER TABLE assets ADD COLUMN kind TEXT NOT NULL DEFAULT 'chassis'")
            if 'client_id' not in cols:db.execute('ALTER TABLE assets ADD COLUMN client_id TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS ix_assets_owner_client ON assets(owner_id,client_id)')

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
            rows=db.execute('SELECT id,filename AS name,bytes,created_at,kind,client_id,sha256 FROM assets '
                            'WHERE owner_id=? ORDER BY created_at DESC LIMIT ?',
                            (validate_uuid(owner),min(100,max(1,int(limit))))).fetchall()
            return [dict(row) for row in rows]


    # Notes are private profile assets, not a browser-only scratchpad. All mutations
    # are explicit SQLite transactions; deletes are owner-scoped and never cascade
    # through a folder deletion (the notes are moved to the Inbox instead).
    def notes_snapshot(self, owner):
        owner=validate_uuid(owner)
        with self.connect() as db:
            folders=[dict(r) for r in db.execute(
                'SELECT id,name,created_at,updated_at FROM note_folders WHERE profile_id=? ORDER BY name COLLATE NOCASE',(owner,))]
            notes=[dict(r) for r in db.execute(
                'SELECT id,folder_id,title,body,priority,revision,created_at,updated_at '
                'FROM user_notes WHERE profile_id=? ORDER BY updated_at DESC',(owner,))]
        return {'folders':folders,'notes':notes}

    def notes_folder(self,owner,name,identifier=None):
        owner=validate_uuid(owner)
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise InvalidLayout('Folder name must be 1–80 characters')
        name=name.strip()
        identifier=validate_uuid(identifier) if identifier else str(uuid.uuid4())
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT profile_id FROM note_folders WHERE id=?',(identifier,)).fetchone()
            if row and row['profile_id']!=owner:raise InvalidLayout('Folder is owned by another profile')
            if not row:
                if db.execute('SELECT count(*) FROM note_folders WHERE profile_id=?',(owner,)).fetchone()[0]>=60:
                    raise InvalidLayout('Maximum 60 folders per profile')
                db.execute('INSERT INTO note_folders VALUES(?,?,?,?,?)',(identifier,owner,name,now,now))
            else:
                db.execute('UPDATE note_folders SET name=?,updated_at=? WHERE id=? AND profile_id=?',(name,now,identifier,owner))
        return {'id':identifier,'name':name,'updated_at':now}

    def notes_delete_folder(self,owner,identifier):
        owner=validate_uuid(owner);identifier=validate_uuid(identifier)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT 1 FROM note_folders WHERE id=? AND profile_id=?',(identifier,owner)).fetchone()
            if not row:return False
            db.execute('UPDATE user_notes SET folder_id=NULL WHERE folder_id=? AND profile_id=?',(identifier,owner))
            db.execute('DELETE FROM note_folders WHERE id=? AND profile_id=?',(identifier,owner))
            return True

    def notes_upsert(self,owner,identifier,title,body,priority,folder_id=None,revision=None):
        owner=validate_uuid(owner);identifier=validate_uuid(identifier)
        if not isinstance(title,str) or len(title.strip())>140:raise InvalidLayout('Note title exceeds 140 characters')
        if not isinstance(body,str) or len(body)>16000:raise InvalidLayout('Note text exceeds 16000 characters')
        if not title.strip() and not body.strip():raise InvalidLayout('Cannot save an empty note')
        if priority not in ('urgent','ongoing','idea'):raise InvalidLayout('Invalid note priority')
        folder_id=validate_uuid(folder_id) if folder_id else None
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if folder_id and not db.execute('SELECT 1 FROM note_folders WHERE id=? AND profile_id=?',(folder_id,owner)).fetchone():
                raise InvalidLayout('Folder unavailable in this profile')
            row=db.execute('SELECT profile_id,revision,created_at FROM user_notes WHERE id=?',(identifier,)).fetchone()
            if row:
                if row['profile_id']!=owner:raise InvalidLayout('Note belongs to another profile')
                if isinstance(revision,bool) or revision!=row['revision']:
                    raise StaleLayout('Note was changed elsewhere. Copy the draft before refreshing.')
                newrev=revision+1;created=row['created_at']
                db.execute('UPDATE user_notes SET folder_id=?,title=?,body=?,priority=?,revision=?,updated_at=? '
                           'WHERE id=? AND profile_id=?',(folder_id,title.strip(),body,priority,newrev,now,identifier,owner))
            else:
                if revision not in (None,0):raise StaleLayout('Note no longer exists; draft preserved')
                if db.execute('SELECT COUNT(*) FROM user_notes WHERE profile_id=?',(owner,)).fetchone()[0]>=500:
                    raise InvalidLayout('Maximum 500 notes per profile')
                newrev=1;created=now
                db.execute('INSERT INTO user_notes(id,profile_id,folder_id,title,body,priority,revision,created_at,updated_at) '
                           'VALUES(?,?,?,?,?,?,?,?,?)',(identifier,owner,folder_id,title.strip(),body,priority,1,now,now))
        return dict(id=identifier,folder_id=folder_id,title=title.strip(),body=body,priority=priority,
                    revision=newrev,created_at=created,updated_at=now)

    def notes_bulk(self,owner,ids,action,folder_id=None,revisions=None):
        owner=validate_uuid(owner)
        if not isinstance(ids,list) or not 1<=len(ids)<=200 or len(set(ids))!=len(ids):
            raise InvalidLayout('Select 1–200 distinct notes')
        ids=[validate_uuid(i) for i in ids]
        if action not in ('move','delete','merge'):raise InvalidLayout('Unknown bulk action')
        folder_id=validate_uuid(folder_id) if folder_id else None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT * FROM user_notes WHERE profile_id=? AND id IN ('+','.join('?' for _ in ids)+')',
                            [owner,*ids]).fetchall()
            if len(rows)!=len(ids):raise InvalidLayout('Some selected notes are missing or not owned by this profile')
            if action in ('move','delete'):
                if not isinstance(revisions,dict) or any(not isinstance(revisions.get(row['id']),int) or
                      isinstance(revisions.get(row['id']),bool) or revisions[row['id']]!=row['revision'] for row in rows):
                    raise StaleLayout('Selected notes changed elsewhere; refresh before moving or deleting')
            if action=='move':
                if folder_id and not db.execute('SELECT 1 FROM note_folders WHERE id=? AND profile_id=?',(folder_id,owner)).fetchone():
                    raise InvalidLayout('Target folder unavailable')
                now=int(time.time()*1000)
                db.executemany('UPDATE user_notes SET folder_id=?,revision=revision+1,updated_at=? WHERE id=? AND profile_id=?',
                               [(folder_id,now,i,owner) for i in ids]);return {'count':len(ids)}
            if action=='delete':
                db.executemany('DELETE FROM user_notes WHERE id=? AND profile_id=?',[(i,owner) for i in ids]);return {'count':len(ids)}
            # Merge is intentionally non-destructive; originals remain recoverable.
            if len(rows)<2:raise InvalidLayout('Select at least two notes to merge')
            rows.sort(key=lambda r:(r['created_at'],r['id']))
            combined='\n\n'.join('--- '+(r['title'] or 'Untitled')+' ---\n'+r['body'] for r in rows)
            if len(combined)>16000:raise InvalidLayout('Merged note would exceed 16000 characters')
            if db.execute('SELECT COUNT(*) FROM user_notes WHERE profile_id=?',(owner,)).fetchone()[0]>=500:
                raise InvalidLayout('Maximum 500 notes per profile')
            merged_id=str(uuid.uuid4());now=int(time.time()*1000)
            db.execute('INSERT INTO user_notes(id,profile_id,folder_id,title,body,priority,revision,created_at,updated_at) '
                       'VALUES(?,?,?,?,?,?,?,?,?)',
                       (merged_id,owner,folder_id,'Merged notes ('+str(len(rows))+')',combined,'ongoing',1,now,now))
            return {'count':len(rows),'merged_id':merged_id,'originals_retained':True}

    def notes_delete(self,owner,identifier,revision):
        owner=validate_uuid(owner);identifier=validate_uuid(identifier)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM user_notes WHERE profile_id=? AND id=?',(owner,identifier)).fetchone()
            if not row:return False
            if revision!=row['revision']:raise StaleLayout('Note changed elsewhere; deletion cancelled')
            db.execute('DELETE FROM user_notes WHERE id=? AND profile_id=?',(identifier,owner))
            return True

    @staticmethod
    def blueprint_asset_client_ids(blueprint):
        """Public dependency allowlist is derived from a published car, not user input.

        The caller must also check that each referenced asset belongs to that car's
        owner. Never enumerate/return private assets that the car does not use.
        """
        if not isinstance(blueprint,dict):return []
        config=blueprint.get('vehicle') or {}
        bindings=blueprint.get('avatarBindings') or {}
        candidates=[]
        if isinstance(bindings,dict):
            candidates.extend((value,'avatar') for value in bindings.values())
        for key,kind in [('frontWheelModel','wheel'),('rearWheelModel','wheel'),
                         ('frontCapModel','cap'),('rearCapModel','cap')]:
            candidates.append((config.get(key),kind))
        result=[];seen=set()
        for identifier,kind in candidates:
            try:ident=validate_uuid(identifier)
            except (TypeError,ValueError):continue
            if ident not in seen:result.append((ident,kind));seen.add(ident)
        return result[:48]

    @classmethod
    def public_car_dependencies(cls,db,owner,blueprint):
        dependencies=[];missing=[]
        refs=cls.blueprint_asset_client_ids(blueprint)
        # Existing public cars were published before linked-avatar consent
        # existed. Never retroactively expose their other private GLBs.
        if blueprint.get('publishPartsConsent') is not True:
            return [],[{'client_id':client_id,'kind':kind} for client_id,kind in refs]
        for client_id,expected in refs:
            row=db.execute('SELECT id,filename,kind,client_id,sha256 FROM assets '
                           'WHERE owner_id=? AND client_id=? ORDER BY created_at DESC LIMIT 1',
                           (owner,client_id)).fetchone()
            if not row or (expected=='avatar' and row['kind'] not in ('avatar','passenger')) or \
               (expected!='avatar' and row['kind']!=expected):
                missing.append({'client_id':client_id,'kind':expected})
            else:dependencies.append(dict(row))
        return dependencies,missing

    def public_car_part(self,car_id,client_id):
        car_id=validate_uuid(car_id);client_id=validate_uuid(client_id)
        with self.connect() as db:
            row=db.execute('SELECT id,profile_id,blueprint FROM user_layouts WHERE id=? AND visibility=?',
                           (car_id,'public')).fetchone()
            if not row:return None
            blueprint=json.loads(row['blueprint'])
            if client_id not in {ref for ref,_ in self.blueprint_asset_client_ids(blueprint)}:return None
            valid,_=self.public_car_dependencies(db,row['profile_id'],blueprint)
            return next((entry for entry in valid if entry['client_id']==client_id),None)

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
            if not row:return None
            entry={**dict(row),'blueprint':json.loads(row['blueprint'])}
            entry['dependencies'],entry['missing_dependencies']=self.public_car_dependencies(db,row['profile_id'],entry['blueprint'])
            return entry

    def find_owned_client_asset(self,owner,client_id):
        owner=validate_uuid(owner);client_id=validate_uuid(client_id)
        with self.connect() as db:
            row=db.execute('SELECT * FROM assets WHERE owner_id=? AND client_id=? ORDER BY created_at DESC LIMIT 1',
                           (owner,client_id)).fetchone()
            return dict(row) if row else None

    def add_asset(self, *, identifier, filename, size, sha256, owner_id=None, kind='chassis', client_id=None):
        validate_uuid(identifier)
        if not isinstance(size,int) or not 20<=size<=80*1024*1024:raise InvalidLayout('Invalid model asset size')
        if not isinstance(filename,str) or len(filename)>120:raise InvalidLayout('Invalid model filename')
        if owner_id:validate_uuid(owner_id)
        if kind not in ('wheel','cap','chassis','avatar','passenger'):
            raise InvalidLayout('Invalid 3D asset category')
        if client_id:validate_uuid(client_id)
        with self.connect() as db:
            db.execute('INSERT INTO assets(id,filename,bytes,sha256,created_at,owner_id,kind,client_id) VALUES (?,?,?,?,?,?,?,?)',
                       (identifier,filename,size,sha256,int(time.time()*1000),owner_id,kind,client_id))

    # Private, named geological styles. Presets contain only bounded scalar values
    # and validated hex colours; there are no executable expressions or file paths.
    GEO_PRESET_DEFAULTS = {
      'biomeEnabled': False, 'biomePalette':'alpine','biomeBlendMode':'mix',
      'biomeRelativeSea':False, 'biomeBlend':.88,'biomeSlope':.6,'biomeExposure':.45,
      'biomeValleyAltitude':-12,'biomeRockAltitude':15,'biomeSnowAltitude':34,
      'biomeValleyColor':'#252d36','biomeGroundColor':'#688754',
      'biomeRockColor':'#838d96','biomeSnowColor':'#f2f7ff'
    }

    @classmethod
    def validate_geology(cls, values):
        if not isinstance(values,dict) or set(values) != set(cls.GEO_PRESET_DEFAULTS):
            raise InvalidLayout('Geological preset must contain only the known colour and altitude settings')
        output={}
        for key,value in values.items():
            if key in ('biomeEnabled','biomeRelativeSea'):
                if type(value) is not bool:raise InvalidLayout('Geological toggle must be boolean')
            elif key=='biomePalette':
                if value not in ('alpine','canyon','volcanic','custom'):raise InvalidLayout('Unknown geology palette')
            elif key=='biomeBlendMode':
                if value not in ('mix','multiply','overlay'):raise InvalidLayout('Unknown texture blend mode')
            elif key.endswith('Color'):
                if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):raise InvalidLayout('Invalid geology colour')
            else:
                if type(value) not in (float,int) or not math.isfinite(value):raise InvalidLayout('Invalid geology number')
                low,high=(-50,120) if key.endswith('Altitude') else (0,1)
                if not low<=value<=high:raise InvalidLayout('Geology value outside permitted range')
            output[key]=value
        if not output['biomeValleyAltitude'] < output['biomeRockAltitude'] < output['biomeSnowAltitude']:
            raise InvalidLayout('Geological elevations must increase from valley to snow')
        return output

    def geology_list(self,owner):
        with self.connect() as db:
            rows=db.execute('SELECT id,name,values_json,created_at,updated_at FROM geology_presets WHERE profile_id=? ORDER BY updated_at DESC LIMIT 80',
                            (validate_uuid(owner),)).fetchall()
            return [{**{key:row[key] for key in ('id','name','created_at','updated_at')},'values':json.loads(row['values_json'])} for row in rows]

    def geology_save(self,owner,name,values):
        owner=validate_uuid(owner);name=validate_name(name);values=self.validate_geology(values)
        identifier=str(uuid.uuid4());now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count=db.execute('SELECT COUNT(*) FROM geology_presets WHERE profile_id=?',(owner,)).fetchone()[0]
            if count>=80:raise InvalidLayout('Maximum 80 geological presets per profile')
            db.execute('INSERT INTO geology_presets(id,profile_id,name,values_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                       (identifier,owner,name,json.dumps(values,separators=(',',':')),now,now))
        return {'id':identifier,'name':name,'values':values,'created_at':now,'updated_at':now}

    def geology_delete(self,owner,identifier):
        with self.connect() as db:
            cursor=db.execute('DELETE FROM geology_presets WHERE profile_id=? AND id=?',
                              (validate_uuid(owner),validate_uuid(identifier)))
            return cursor.rowcount>0

    # Explicit public links: private media/model bytes never become public merely
    # by being uploaded. A share is a separate, revocable, profile-owned record.
    def community_list(self,owner=None):
        with self.connect() as db:
            if owner:
                rows=db.execute('SELECT s.*,p.name AS creator_name FROM community_shares s JOIN profiles p ON p.id=s.profile_id '
                                'WHERE s.profile_id=? ORDER BY s.created_at DESC LIMIT 90',(validate_uuid(owner),)).fetchall()
            else:
                rows=db.execute('SELECT s.*,p.name AS creator_name FROM community_shares s JOIN profiles p ON p.id=s.profile_id '
                                'ORDER BY s.created_at DESC LIMIT 120').fetchall()
            entries=[]
            for row in rows:
                item=dict(row)
                if row['kind'] in ('map','world'):
                    target=db.execute('SELECT name FROM user_media WHERE id=? AND profile_id=? AND kind=?',
                                      (row['source_id'],row['profile_id'],'map')).fetchone()
                    if row['kind']=='world':
                        car=db.execute('SELECT name FROM user_layouts WHERE id=? AND profile_id=? AND visibility=?',
                                       (row['car_id'],row['profile_id'],'public')).fetchone()
                        if car:item['name']=car['name']+' + '+(target['name'] if target else 'Map')
                        else:target=None
                    elif target:item['name']=target['name']
                else:
                    target=db.execute('SELECT filename FROM assets WHERE id=? AND owner_id=?',
                                      (row['source_id'],row['profile_id'])).fetchone()
                    if target:item['name']=target['filename']
                if not target:continue
                item.pop('profile_id',None)
                entries.append(item)
            return entries

    def community_create(self,owner,kind,source_id,car_id=None):
        owner=validate_uuid(owner);source_id=validate_uuid(source_id)
        if kind not in ('map','model','world'):raise InvalidLayout('Unknown share category')
        if kind=='world':car_id=validate_uuid(car_id)
        elif car_id is not None:raise InvalidLayout('Unexpected linked vehicle')
        now=int(time.time()*1000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count=db.execute('SELECT COUNT(*) FROM community_shares WHERE profile_id=?',(owner,)).fetchone()[0]
            if count>=60:raise InvalidLayout('Maximum 60 public shares per profile')
            if kind in ('map','world'):
                target=db.execute('SELECT id FROM user_media WHERE id=? AND profile_id=? AND kind=?',
                                  (source_id,owner,'map')).fetchone()
                if not target:raise InvalidLayout('Save the map to your private server library before publishing')
            else:
                target=db.execute('SELECT id FROM assets WHERE id=? AND owner_id=?',
                                  (source_id,owner)).fetchone()
                if not target:raise InvalidLayout('Only your own uploaded 3D model can be shared')
            if kind=='world' and not db.execute(
                'SELECT 1 FROM user_layouts WHERE id=? AND profile_id=? AND visibility=?',(car_id,owner,'public')).fetchone():
                raise InvalidLayout('Publish the linked car first, then publish this world')
            existing=db.execute('SELECT id,created_at FROM community_shares WHERE profile_id=? AND kind=? AND source_id=? AND car_id IS ?',
                                (owner,kind,source_id,car_id)).fetchone()
            if existing:return {'id':existing['id'],'kind':kind,'source_id':source_id,'car_id':car_id,'created_at':existing['created_at']}
            ident=str(uuid.uuid4())
            db.execute('INSERT INTO community_shares(id,profile_id,kind,source_id,car_id,created_at) VALUES(?,?,?,?,?,?)',
                       (ident,owner,kind,source_id,car_id,now))
            return {'id':ident,'kind':kind,'source_id':source_id,'car_id':car_id,'created_at':now}

    def community_delete(self,owner,identifier):
        with self.connect() as db:
            result=db.execute('DELETE FROM community_shares WHERE id=? AND profile_id=?',
                              (validate_uuid(identifier),validate_uuid(owner)))
            return result.rowcount>0

    def community_content(self,identifier):
        with self.connect() as db:
            row=db.execute('SELECT * FROM community_shares WHERE id=?',(validate_uuid(identifier),)).fetchone()
            if not row:return None
            if row['kind']=='model':
                asset=db.execute('SELECT id,filename FROM assets WHERE id=? AND owner_id=?',
                                 (row['source_id'],row['profile_id'])).fetchone()
                return {'kind':'model','asset_id':asset['id'],'filename':asset['filename']} if asset else None
            entry=db.execute('SELECT name,payload FROM user_media WHERE id=? AND profile_id=? AND kind=?',
                             (row['source_id'],row['profile_id'],'map')).fetchone()
            if not entry:return None
            content={'kind':row['kind'],'map':json.loads(entry['payload']),'map_name':entry['name']}
            if row['kind']=='world':
                car=db.execute('SELECT id,name,blueprint,asset_id FROM user_layouts WHERE id=? AND profile_id=? AND visibility=?',
                               (row['car_id'],row['profile_id'],'public')).fetchone()
                if not car:return None
                blueprint=json.loads(car['blueprint'])
                deps,missing=self.public_car_dependencies(db,row['profile_id'],blueprint)
                content['car']={'id':car['id'],'name':car['name'],'blueprint':blueprint,
                                'asset_id':car['asset_id'],'dependencies':deps,'missing_dependencies':missing}
            return content

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
