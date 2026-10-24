"""SQLite catalog. One connection per thread."""
import json
import sqlite3
import threading

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY, kind TEXT, path TEXT UNIQUE, size INTEGER, mtime REAL,
  location TEXT, part_group TEXT, part_no INTEGER, state TEXT DEFAULT 'queued',
  entries INTEGER DEFAULT 0, scanned INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS media(
  id INTEGER PRIMARY KEY, source_id INTEGER, inner TEXT, name TEXT, folder TEXT, dirkey TEXT,
  ext TEXT, kind TEXT, size INTEGER, sidecar_id INTEGER, live_pair INTEGER, hidden INTEGER DEFAULT 0,
  sha256 TEXT, phash TEXT, width INTEGER, height INTEGER,
  cands TEXT, resolved TEXT, ts REAL, status TEXT DEFAULT 'pending', reasons TEXT DEFAULT '[]',
  manual TEXT, excluded INTEGER DEFAULT 0, scanned INTEGER DEFAULT 0, error TEXT, has_exif INTEGER DEFAULT 0,
  UNIQUE(source_id, inner));
CREATE INDEX IF NOT EXISTS media_ts ON media(ts);
CREATE INDEX IF NOT EXISTS media_status ON media(status, kind);
CREATE INDEX IF NOT EXISTS media_sha ON media(sha256);
CREATE INDEX IF NOT EXISTS media_dir ON media(dirkey);
CREATE INDEX IF NOT EXISTS media_src ON media(source_id, kind, scanned);
CREATE TABLE IF NOT EXISTS dup_index(sha TEXT PRIMARY KEY, c INTEGER, sz INTEGER);
CREATE TABLE IF NOT EXISTS dup_choice(media_id INTEGER PRIMARY KEY, role TEXT);
CREATE TABLE IF NOT EXISTS edits(batch INTEGER, media_id INTEGER, prev TEXT);
CREATE TABLE IF NOT EXISTS exports(
  id INTEGER PRIMARY KEY, created REAL, dest TEXT, options TEXT, state TEXT);
CREATE TABLE IF NOT EXISTS export_items(
  export_id INTEGER, media_id INTEGER, state TEXT, dest_path TEXT, note TEXT,
  PRIMARY KEY(export_id, media_id));
"""


def conn() -> sqlite3.Connection:
    path = str(config.db_path())
    c = getattr(_local, "c", None)
    if c is None or getattr(_local, "path", None) != path:
        config.ensure()
        c = sqlite3.connect(path, timeout=60, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
        try:
            c.execute("ALTER TABLE media ADD COLUMN has_exif INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        _local.c, _local.path = c, path
    return c


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def run(sql, args=()):
    cur = conn().execute(sql, args)
    conn().commit()
    return cur


def many(sql, rows):
    conn().executemany(sql, rows)
    conn().commit()


def jl(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default
