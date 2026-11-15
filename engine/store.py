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


# Stage 3: local evidence selection, document freshness, source provenance
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re

from .context import ProjectContext
from .extractors import SUPPORTED

MAX_INDEXED_CHUNKS = 12000
STOPWORDS = frozenset(
    "the and for with from this that have will should into their about which "
    "when where there these those your current documents document documentation "
    "against using local generate create analyze identify process review report "
    "input inputs references reference existing source sources based project "
    "information material objective scope tasks output requirements".split()
)


@dataclass(frozen=True)
class Evidence:
    id: str
    source_role: str
    relative_path: str
    locator: str
    kind: str
    content: str
    document_sha256: str
    relevance: int

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def citation(self) -> str:
        return f"[{self.id}]"


def words(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
        if len(token) >= 4 and token not in STOPWORDS
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def check_fresh_index(ctx: ProjectContext) -> list[dict]:
    """Refuse stale/partial indexes, including modified/deleted/additional files."""
    from .ingest import iter_sources
    project = ctx.project_dir
    report_path = project / '.local' / 'ingestion_report.json'
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError('No completed Stage 2 ingestion report. Run main.py --ingest first.')
    import json
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('Stage 2 ingestion report could not be read') from exc
    if report.get('errors'):
        raise ValueError('Stage 2 ingestion has errors; fix source files and rerun --ingest before Stage 3')
    rows = inventory(project)
    if not rows:
        raise ValueError('No indexed documents. Add local documents, then run Stage 2 --ingest.')
    recorded = {item['relative_path']: item for item in rows}
    actual = {}
    for _, path in iter_sources(project):
        relative = path.relative_to(project).as_posix()
        actual[relative] = _sha256_file(path)
    if set(recorded) != set(actual):
        diff = sorted(set(recorded).symmetric_difference(actual))
        raise ValueError('Document collection differs from indexed files. Rerun --ingest. Changed paths: ' + ', '.join(diff[:8]))
    for path, fingerprint in actual.items():
        if fingerprint != recorded[path]['content_sha256']:
            raise ValueError(f'Document modified since indexing: {path}. Rerun --ingest.')
        if recorded[path]['chunks'] < 1:
            raise ValueError(f'Indexed document has no extractable chunks: {path}')
    return rows


def find_skipped_paths(project: Path) -> list[str]:
    """Report non-indexable source files; do not follow links or hidden files."""
    skipped = []
    for role in ('inputs', 'references'):
        root = project / role
        if not root.is_dir() or root.is_symlink():
            continue
        for file in sorted(root.rglob('*')):
            relative = file.relative_to(project).as_posix()
            if any(part.startswith('.') for part in file.relative_to(root).parts):
                continue
            if file.is_symlink():
                skipped.append(relative + ' (symlink not followed)')
            elif file.is_file() and file.suffix.lower() not in SUPPORTED:
                skipped.append(relative + ' (unsupported file type)')
    return skipped


def select_evidence(ctx: ProjectContext, max_evidence: int = 40) -> tuple[list[Evidence], dict]:
    if not 4 <= max_evidence <= 200:
        raise ValueError('--max-evidence must be between 4 and 200')
    documents = check_fresh_index(ctx)
    theme = words(ctx.content('objective', 'goals') + '\n' + ctx.content('scope', 'boundaries'))
    with connect(ctx.project_dir) as con:
        raw = con.execute('''
            SELECT d.relative_path, d.source_role, d.content_sha256,
                   c.ordinal, c.locator, c.kind, c.content
            FROM chunks c JOIN documents d ON c.document_id=d.id
            ORDER BY d.source_role, d.relative_path, c.ordinal
            LIMIT ?
        ''', (MAX_INDEXED_CHUNKS + 1,)).fetchall()
    if len(raw) > MAX_INDEXED_CHUNKS:
        raise ValueError(f'Index has more than {MAX_INDEXED_CHUNKS} chunks; narrow the project for this MVP')

    groups: dict[str, list[tuple[int, int, dict]]] = {}
    for row in raw:
        item = dict(row)
        relevance = len(words(item['content']) & theme)
        groups.setdefault(item['relative_path'], []).append((relevance, item['ordinal'], item))
    # Always include first chunk of each document when possible; then select the
    # highest-scoring chunks from each document round-robin to avoid domination.
    queues: dict[str, list[tuple[int, int, dict]]] = {}
    for rel, items in groups.items():
        first = min(items, key=lambda x: x[1])
        rest = sorted((item for item in items if item != first), key=lambda x: (-x[0], x[1]))
        queues[rel] = [first] + rest
    ordered_paths = sorted(queues, key=lambda p: (0 if p.startswith('inputs/') else 1, p))
    chosen = []
    while len(chosen) < max_evidence and any(queues.values()):
        for rel in ordered_paths:
            if queues[rel] and len(chosen) < max_evidence:
                chosen.append(queues[rel].pop(0))
    evidence = []
    for number, (score, _, item) in enumerate(chosen, start=1):
        evidence.append(Evidence(
            id=f'E{number:04d}',
            source_role=item['source_role'],
            relative_path=item['relative_path'],
            locator=item['locator'],
            kind=item['kind'],
            content=item['content'],
            document_sha256=item['content_sha256'],
            relevance=score,
        ))
    selected_docs = {ev.relative_path for ev in evidence}
    skipped = find_skipped_paths(ctx.project_dir)
    stats = {
        'unindexed_paths': skipped,
        'indexed_documents': len(documents),
        'indexed_chunks': len(raw),
        'selected_chunks': len(evidence),
        'omitted_chunks': len(raw) - len(evidence),
        'unrepresented_documents': sorted(set(groups) - selected_docs),
        'selection_policy': 'First chunk then lexical relevance, round-robin by document; exploratory, not exhaustive',
        'coverage_complete': len(raw) == len(evidence) and not skipped,
    }
    return evidence, stats

# Stage 5 — exhaustive reference-first source traversal; never samples indexed chunks.
def evidence_display(item: Evidence) -> str:
    return f"{item.id} | {item.source_role}/{item.relative_path} @ {item.locator}\n{item.content}\n"


def full_evidence_batches(ctx: ProjectContext, *, batch_chars: int = 1800) -> tuple[list[list[Evidence]], dict]:
    """Create lossless model-sized batches of all indexed source text.

    Document role and source order are preserved. No source text is discarded.
    A *complete* model analysis is only claimed after every batch succeeds.
    """
    if not 600 <= batch_chars <= 24000:
        raise ValueError('--batch-chars must be between 600 and 24000')
    documents = check_fresh_index(ctx)
    with connect(ctx.project_dir) as con:
        rows = con.execute("""
            SELECT d.relative_path, d.source_role, d.content_sha256,
                   c.ordinal, c.locator, c.kind, c.content
            FROM chunks c JOIN documents d ON c.document_id=d.id
            ORDER BY CASE d.source_role WHEN 'references' THEN 0 ELSE 1 END,
                     d.relative_path, c.ordinal
        """).fetchall()
    batches: list[list[Evidence]] = []
    current: list[Evidence] = []
    current_len = 0
    last_source: str | None = None
    total_chars = 0
    segment_count = 0
    doc_stats: dict[str, dict] = {
        d['relative_path']: {'role': d['source_role'], 'indexed_chunks': d['chunks'],
                              'segments': 0, 'characters': 0} for d in documents
    }
    for row in rows:
        item = dict(row)
        content = item['content']
        total_chars += len(content)
        path = item['relative_path']
        start = 0
        while start < len(content):
            next_id = f'E{segment_count + 1:06d}'
            locator_prefix = f"{item['locator']} [chunk {item['ordinal']}, chars {start + 1}-"
            overhead = len(next_id) + 4 + len(item['source_role']) + len(path) + len(locator_prefix) + 35
            space = batch_chars - overhead
            if space < 1:
                raise ValueError('Source path/locator is too long for --batch-chars; increase the budget')
            end = min(len(content), start + min(900, space))
            segment = Evidence(
                id=next_id, source_role=item['source_role'], relative_path=path,
                locator=f"{item['locator']} [chunk {item['ordinal']}, chars {start + 1}-{end}]",
                kind=item['kind'], content=content[start:end],
                document_sha256=item['content_sha256'], relevance=0,
            )
            display_len = len(evidence_display(segment))
            if display_len > batch_chars:
                raise AssertionError('Evidence splitter exceeded batch budget')
            if current and (current_len + display_len > batch_chars or last_source != path):
                batches.append(current)
                current = []
                current_len = 0
            current.append(segment)
            current_len += display_len
            last_source = path
            segment_count += 1
            doc_stats[path]['segments'] += 1
            doc_stats[path]['characters'] += len(segment.content)
            start = end
    if current:
        batches.append(current)
    if sum(len(e.content) for batch in batches for e in batch) != total_chars:
        raise AssertionError('Source text coverage invariant failed')
    skipped = find_skipped_paths(ctx.project_dir)
    stats = {
        'indexed_documents': len(documents),
        'indexed_chunks': len(rows),
        'indexed_source_characters': total_chars,
        'prepared_segments': segment_count,
        'total_batches': len(batches),
        'reference_documents': sum(1 for d in documents if d['source_role'] == 'references'),
        'input_documents': sum(1 for d in documents if d['source_role'] == 'inputs'),
        'reference_batches': sum(1 for b in batches if b[0].source_role == 'references'),
        'unindexed_paths': skipped,
        'documents': doc_stats,
        'selection_policy': 'Exhaustive indexed text, document by document; references first; no chunk limit',
        'all_indexed_text_prepared': True,
    }
    return batches, stats
