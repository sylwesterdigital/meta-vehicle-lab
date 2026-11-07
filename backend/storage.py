"""SQLite vehicle blueprint store. No Flask dependency; testable with stdlib."""
from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from pathlib import Path

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
            ''')

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

    def add_asset(self, *, identifier, filename, size, sha256):
        validate_uuid(identifier)
        if not isinstance(size,int) or not 20<=size<=80*1024*1024:raise InvalidLayout('Invalid model asset size')
        if not isinstance(filename,str) or len(filename)>120:raise InvalidLayout('Invalid model filename')
        with self.connect() as db:
            db.execute('INSERT INTO assets(id,filename,bytes,sha256,created_at) VALUES (?,?,?,?,?)',
                       (identifier,filename,size,sha256,int(time.time()*1000)))

    def get_asset(self,identifier):
        validate_uuid(identifier)
        with self.connect() as db:
            row=db.execute('SELECT * FROM assets WHERE id=?',(identifier,)).fetchone()
            return dict(row) if row else None
