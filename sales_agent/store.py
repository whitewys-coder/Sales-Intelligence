import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class Store:
    TABLES = {'accounts', 'drafts', 'runs', 'events', 'messages', 'contacts', 'settings'}

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            for table in self.TABLES:
                db.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, body TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, table, item):
        assert table in self.TABLES
        with self.connect() as db:
            db.execute(f'INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                       (item['id'], json.dumps(item, ensure_ascii=False)))
        return item

    def get(self, table, ident):
        assert table in self.TABLES
        with self.connect() as db:
            row = db.execute(f'SELECT body FROM {table} WHERE id=?', (ident,)).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, table):
        assert table in self.TABLES
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(f'SELECT body FROM {table} ORDER BY rowid DESC')]

    def event(self, agent, status, detail, run_id=''):
        return self.put('events', dict(id=uid(), time=now(), agent=agent, status=status,
                                      detail=detail, run_id=run_id))
