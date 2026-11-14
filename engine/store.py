"""Local SQLite document catalog and FTS5 index. No network dependencies."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3

DB_RELATIVE_PATH = Path('.local') / 'documents.sqlite3'

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    source_role TEXT NOT NULL CHECK(source_role IN ('inputs', 'references')),
    file_type TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    locator TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(document_id, ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS chunks_after_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_before_delete BEFORE DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_after_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
END;
'''


def db_path(project_dir: Path) -> Path:
    local = project_dir / '.local'
    if local.is_symlink() or (local.exists() and not local.is_dir()):
        raise ValueError('.local must be a non-symlink directory')
    local.mkdir(exist_ok=True)
    path = local / 'documents.sqlite3'
    if path.is_symlink():
        raise ValueError('Refusing to open symlinked local database')
    return path


@contextmanager
def connect(project_dir: Path):
    connection = sqlite3.connect(str(db_path(project_dir)))
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        connection.executescript(SCHEMA)
        yield connection
    finally:
        connection.close()


def inventory(project_dir: Path) -> list[dict]:
    with connect(project_dir) as con:
        rows = con.execute('''SELECT d.relative_path, d.source_role, d.file_type,
           d.content_sha256, d.indexed_at, COUNT(c.id) AS chunks
           FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
           GROUP BY d.id ORDER BY d.source_role, d.relative_path''').fetchall()
        return [dict(row) for row in rows]


def search(project_dir: Path, query: str, role: str = 'all', limit: int = 8, match_all: bool = False) -> list[dict]:
    """Safe FTS5 input construction; never concatenate untrusted text as SQL."""
    if role not in {'all', 'inputs', 'references'}:
        raise ValueError('role must be all, inputs or references')
    if not 1 <= limit <= 50:
        raise ValueError('limit must be 1–50')
    terms = re.findall(r'[^\W_]+', query.casefold(), flags=re.UNICODE)[:20]
    if not terms:
        return []
    # Each quoted token is an FTS5 literal, never operator syntax.
    fts_query = (' AND ' if match_all else ' OR ').join('"' + t.replace('"', '""') + '"' for t in terms)
    with connect(project_dir) as con:
        rows = con.execute('''
          SELECT d.relative_path, d.source_role, c.locator, c.kind,
            c.content, snippet(chunks_fts, 0, '[', ']', '…', 25) AS excerpt,
            bm25(chunks_fts) AS score
          FROM chunks_fts
          JOIN chunks c ON c.id=chunks_fts.rowid
          JOIN documents d ON d.id=c.document_id
          WHERE chunks_fts MATCH ? AND (?='all' OR d.source_role=?)
          ORDER BY score ASC, d.relative_path, c.ordinal
          LIMIT ?''', (fts_query, role, role, limit)).fetchall()
        return [dict(row) for row in rows]
