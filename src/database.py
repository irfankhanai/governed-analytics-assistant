import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, request_id TEXT NOT NULL,
            action TEXT NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT NOT NULL REFERENCES decisions(id),
            timestamp TEXT NOT NULL, reviewer TEXT NOT NULL, status TEXT NOT NULL,
            comments TEXT NOT NULL, attestations TEXT NOT NULL);
    ''')
    try:
        with db:
            yield db
    finally:
        db.close()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def save_decision(path, result):
    decision_id = 'DEC-' + uuid.uuid4().hex[:12]
    with connect(path) as db:
        db.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?)',
                   (decision_id, utcnow(), result['request']['request_id'], result['action'], 'pending', json.dumps(result)))
    return decision_id


def list_decisions(path):
    with connect(path) as db:
        return [dict(row) for row in db.execute('SELECT id, created_at, request_id, action, status FROM decisions ORDER BY created_at DESC')]


def get_decision(path, decision_id):
    with connect(path) as db:
        row = db.execute('SELECT * FROM decisions WHERE id=?', (decision_id,)).fetchone()
        if not row: raise ValueError('Unknown decision.')
        result = dict(row)
        result['snapshot'] = json.loads(result['snapshot'])
        result['reviews'] = [dict(r) for r in db.execute('SELECT * FROM reviews WHERE decision_id=? ORDER BY id', (decision_id,))]
        return result
