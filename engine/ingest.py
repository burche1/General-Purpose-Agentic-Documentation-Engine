"""Incremental project-local ingestion preserving immutable source file provenance."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from datetime import datetime, timezone
import json

from .extractors import SUPPORTED, extract_document, split_blocks
from .store import connect


def iter_sources(project_dir: Path):
    for role in ('inputs', 'references'):
        root = project_dir / role
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f'{role}/ must be an ordinary directory')
        for path in sorted(root.rglob('*')):
            if path.is_symlink() or not path.is_file():
                continue
            if not path.resolve().is_relative_to(root.resolve()):
                continue
            if any(part.startswith('.') for part in path.relative_to(root).parts):
                continue
            if path.suffix.lower() in SUPPORTED:
                yield role, path


def ingest_project(project_dir: Path) -> dict:
    """Index all supported files; failures are listed, never silently suppressed.

    An errored file is removed from the index to avoid stale retrieval.
    Removed files are also purged from the index.
    """
    project_dir = project_dir.resolve(strict=True)
    report = {'indexed': [], 'unchanged': [], 'removed': [], 'errors': [], 'empty': []}
    sources = list(iter_sources(project_dir))
    found = {str(p.relative_to(project_dir)) for _, p in sources}
    with connect(project_dir) as con:
        existing = {r['relative_path']: r['content_sha256'] for r in con.execute('SELECT relative_path,content_sha256 FROM documents')}
        for role, path in sources:
            rel = str(path.relative_to(project_dir))
            try:
                # For MVP, reject large source files before reading or hashing.
                from .extractors import MAX_FILE_BYTES
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise ValueError('Exceeds 25 MiB source limit')
                file_bytes = path.read_bytes()
                digest = sha256(file_bytes).hexdigest()
                if existing.get(rel) == digest:
                    report['unchanged'].append(rel)
                    continue
                chunks = split_blocks(extract_document(path))
                # Do not accept a file which contains no extractable text as successfully indexed.
                if not chunks:
                    raise ValueError('No extractable text (scanned/image-only file or empty document)')
                # Transaction per document to avoid partial indexed content.
                with con:
                    con.execute('DELETE FROM documents WHERE relative_path=?', (rel,))
                    row = con.execute('''INSERT INTO documents(relative_path,source_role,file_type,content_sha256,bytes)
                                         VALUES(?,?,?,?,?)''', (rel, role, path.suffix.lower(), digest, len(file_bytes)))
                    doc_id = row.lastrowid
                    con.executemany('''INSERT INTO chunks(document_id,ordinal,locator,kind,content)
                                       VALUES (?,?,?,?,?)''', [(doc_id, i, b.locator, b.kind, b.text) for i,b in enumerate(chunks, 1)])
                report['indexed'].append({'path': rel, 'chunks': len(chunks)})
            except Exception as exc:
                # Remove stale content from earlier versions if this revision cannot be indexed.
                with con:
                    con.execute('DELETE FROM documents WHERE relative_path=?', (rel,))
                report['errors'].append({'path': rel, 'error': f'{type(exc).__name__}: {exc}'})
        for rel in existing.keys() - found:
            with con:
                con.execute('DELETE FROM documents WHERE relative_path=?', (rel,))
            report['removed'].append(rel)
    report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['document_count'] = len(found)
    local = project_dir / '.local'
    path = local / 'ingestion_report.json'
    if path.is_symlink():
        raise ValueError('Refusing to overwrite symlinked report')
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report
