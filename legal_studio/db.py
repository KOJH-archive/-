"""Local-first SQLite persistence. No network and no implicit cloud sync."""
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback on context exit, then release the Windows file handle."""

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    def initialize(self):
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS documents(
                document_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                source_url TEXT,
                source_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                hash_sha256 TEXT NOT NULL,
                fetched_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS research_jobs(
                job_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS event_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                action TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS source_snapshots(
                job_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY(job_id, source_id),
                FOREIGN KEY(job_id) REFERENCES research_jobs(job_id) ON DELETE CASCADE
              );
              CREATE INDEX IF NOT EXISTS ix_jobs_time ON research_jobs(created_at DESC);
              CREATE INDEX IF NOT EXISTS ix_docs_kind ON documents(kind,source_type);
            ''')
            try:
                db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(document_key UNINDEXED, title, content, tokenize="unicode61")')
            except sqlite3.OperationalError:
                # Some custom builds omit FTS5. The application remains usable.
                pass

    def put_document(self, kind: str, source_id: str, title: str, content: str,
                     source_url: str='', source_type: str='MOLEG', metadata=None):
        key = f'{source_type}:{kind}:{source_id}'
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        with self.connect() as db:
            db.execute('''INSERT INTO documents(document_key,kind,source_id,title,source_url,source_type,
                       content,metadata_json,hash_sha256,fetched_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(document_key) DO UPDATE SET
                         title=excluded.title,source_url=excluded.source_url,
                         content=excluded.content,metadata_json=excluded.metadata_json,
                         hash_sha256=excluded.hash_sha256,fetched_at=excluded.fetched_at''',
                       (key,kind,source_id,title,source_url,source_type,content,
                        json.dumps(metadata or {}, ensure_ascii=False),digest,iso_now()))
            if self.has_fts(db):
                db.execute('DELETE FROM documents_fts WHERE document_key=?', (key,))
                db.execute('INSERT INTO documents_fts(document_key,title,content) VALUES(?,?,?)', (key,title,content))
        return key

    @staticmethod
    def has_fts(db):
        return db.execute("SELECT 1 FROM sqlite_master WHERE name='documents_fts'").fetchone() is not None

    def get_document(self, key: str):
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE document_key=?', (key,)).fetchone()
            return dict(row) if row else None

    def local_search(self, query: str, limit=15, source_type='MOLEG'):
        terms = [t for t in query.split() if len(t) > 1][:8]
        if not terms:
            return []
        with self.connect() as db:
            if self.has_fts(db):
                # FTS5 phrase-escaped terms: no raw input is interpolated into SQL.
                expression = ' OR '.join('"'+t.replace('"', '""')+'"' for t in terms)
                try:
                    rows = db.execute('''SELECT d.* FROM documents_fts f
                                        JOIN documents d ON d.document_key=f.document_key
                                        WHERE documents_fts MATCH ? AND d.source_type=?
                                        ORDER BY bm25(documents_fts) LIMIT ?''',
                                      (expression,source_type,limit)).fetchall()
                    return [dict(row) for row in rows]
                except sqlite3.OperationalError:
                    pass
            pat = '%' + terms[0].replace('%', '\\%').replace('_','\\_') + '%'
            rows = db.execute('SELECT * FROM documents WHERE source_type=? AND (title LIKE ? ESCAPE "\\" OR content LIKE ? ESCAPE "\\") LIMIT ?',
                              (source_type, pat, pat,limit)).fetchall()
            return [dict(r) for r in rows]

    def save_job(self, result):
        payload = result.model_dump_json()
        with self.connect() as db:
            db.execute('''INSERT INTO research_jobs(job_id,question,status,result_json,created_at,updated_at)
                           VALUES(?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET
                           status=excluded.status,result_json=excluded.result_json,updated_at=excluded.updated_at''',
                       (result.job_id,result.question,result.status,payload,iso_now(),iso_now()))

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT result_json FROM research_jobs WHERE job_id=?', (job_id,)).fetchone()
            return json.loads(row['result_json']) if row else None

    def recent_jobs(self, limit=30):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT job_id,question,status,created_at,updated_at FROM research_jobs ORDER BY updated_at DESC LIMIT ?', (limit,))]

    def add_log(self, action, message='', job_id=None):
        with self.connect() as db:
            db.execute('INSERT INTO event_logs(job_id,action,message,created_at) VALUES(?,?,?,?)',
                       (job_id,action,message[:2000],iso_now()))

    def logs(self, limit=50):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM event_logs ORDER BY id DESC LIMIT ?', (limit,))]

    def clear_all(self):
        """User-triggered local deletion; no silent deletion on startup."""
        with self.connect() as db:
            db.execute('DELETE FROM research_jobs')
            db.execute('DELETE FROM documents')
            db.execute('DELETE FROM event_logs')
            if self.has_fts(db):
                db.execute('DELETE FROM documents_fts')

    def save_snapshot(self, job_id, source_id, content, metadata):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO source_snapshots VALUES(?,?,?,?)',
                       (job_id,source_id,content,json.dumps(metadata,ensure_ascii=False)))

    def snapshots(self, job_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM source_snapshots WHERE job_id=?',(job_id,))]
