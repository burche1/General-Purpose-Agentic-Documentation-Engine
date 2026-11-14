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


# Stage 3: approved-plan document analysis and draft generation
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re

from .context import ProjectContext, parse_context
from .review import get_status, read_draft
from .store import inventory
from .catalog import analyze, compare, consolidate, draft, gaps, design_outline
from .store import Evidence, select_evidence, check_fresh_index
from .ollama import interpret_locally


class Stage3Error(ValueError):
    pass


def _validated_project(path: Path) -> tuple[ProjectContext, dict, set[str]]:
    ctx = parse_context(path)
    status = get_status(ctx)
    if status != 'approved':
        raise Stage3Error(f'Current Stage 1 plan is not approved ({status}). Run main.py --project ... then --approve.')
    plan = read_draft(ctx)
    capabilities = {task['capability'] for task in plan['tasks']}
    return ctx, plan, capabilities


def _json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + '\n'


def _render_llm_findings(findings: list[dict]) -> str:
    lines = ['# Model-proposed observations', '',
             '> Every observation requires human review; citation presence does not establish factual correctness.', '']
    if not findings:
        lines.append('The local model returned no observations.\n')
    for item in findings:
        lines.append(f"- **{item['kind']}**: {item['text']} " +
                     ' '.join('[' + e + ']' for e in item['evidence_ids']))
    return '\n'.join(lines).rstrip() + '\n'


def _checked_references(files: dict[str, str], allowed: set[str]) -> dict:
    """Syntactic citation validator; semantic validation is deferred to Stage 4."""
    errors = []
    cited = set()
    for name, content in files.items():
        for identifier in re.findall(r'\[(E\d{4})\]', content):
            cited.add(identifier)
            if identifier not in allowed:
                errors.append(f'{name}: unknown citation [{identifier}]')
    return {
        'passed': not errors,
        'citation_ids_used': sorted(cited),
        'errors': errors,
        'warning': 'Citation integrity is syntactic only; source entailment is not automatically proven.',
        'status': 'draft_for_human_review',
    }


def _safe_output_base(ctx: ProjectContext) -> Path:
    root = ctx.project_dir / 'outputs'
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise Stage3Error('outputs/ must be an ordinary directory')
    sub = root / 'stage3'
    if sub.is_symlink() or (sub.exists() and not sub.is_dir()):
        raise Stage3Error('outputs/stage3/ must be an ordinary directory')
    root.mkdir(exist_ok=True)
    sub.mkdir(exist_ok=True)
    return sub


def run_stage3(path: Path, *, llm: str = 'none', model: str = 'qwen2.5:1.5b',
               max_evidence: int = 40, dry_run: bool = False, preview_api: bool = False,
               approve_api: str | None = None) -> dict:
    if llm not in {'none', 'ollama', 'openai'}:
        raise Stage3Error('Unknown inference backend')
    if (preview_api or approve_api) and llm != 'openai':
        raise Stage3Error('--preview-api and --approve-api require --llm openai')
    if preview_api and approve_api:
        raise Stage3Error('Preview and approval must be separate commands')
    ctx, plan, capabilities = _validated_project(path)
    evidence, stats = select_evidence(ctx, max_evidence=max_evidence)
    if dry_run:
        return {
            'project': ctx.title, 'mode': llm,
            'planned_capabilities': [t['capability'] for t in plan['tasks']],
            'executable_now': sorted(capabilities & {'analyze', 'compare', 'gaps', 'consolidate', 'design', 'generate'}),
            'document_count': stats['indexed_documents'],
            'evidence_selection': stats,
            'writes_anything': False,
        }
    if preview_api or approve_api:
        from .ollama import preview_remote, approve_remote
        if preview_api:
            return preview_remote(ctx, evidence, model)
        return approve_remote(ctx, evidence, model, approve_api)
    if 'analyze' not in capabilities:
        raise Stage3Error('The approved plan does not request document analysis')

    # Pure capability functions. An optional model cannot modify references.
    files: dict[str, str] = {'analysis.md': analyze(evidence, stats)}
    comparisons: list[dict] = []
    if 'compare' in capabilities:
        comparison_text, comparisons = compare(evidence)
        files['comparison.md'] = comparison_text
    if 'gaps' in capabilities:
        files['open_gap_questions.md'] = gaps(evidence, comparisons)
    if 'consolidate' in capabilities:
        files['consolidated_excerpts.md'] = consolidate(evidence)
    if 'design' in capabilities:
        files['document_outline.md'] = design_outline(ctx, plan['requested_deliverables'])

    findings: list[dict] = []
    sections: list[dict] = []
    inference = {'provider': 'none', 'model': None, 'notes': 'Deterministic extractive mode; no LLM calls'}
    if llm == 'ollama':
        findings, sections, inference = interpret_locally(ctx, evidence, model)
        files['model_observations.md'] = _render_llm_findings(findings)
    elif llm == 'openai':
        from .ollama import interpret_remotely
        findings, sections, inference = interpret_remotely(ctx, evidence, model)
        files['model_observations.md'] = _render_llm_findings(findings)
    if 'generate' in capabilities:
        files['draft.md'] = draft(ctx, evidence, findings, sections)

    files['review_checklist.md'] = (
        '# Stage 3 review checklist\n\n'
        '- [ ] Confirm every excerpt and locator against the original local file.\n'
        '- [ ] Confirm potential gaps/conflicts against the **full** source collection.\n'
        '- [ ] Distinguish reference requirements from organizational practices.\n'
        '- [ ] Check completeness, errors, terminology, and unsupported assertions.\n'
        '- [ ] Resolve unrepresented source documents and omitted evidence, if any.\n'
        '- [ ] Approve separately in Stage 4; nothing here is published or approved.\n'
    )
    evidence_json = [item.as_dict() for item in evidence]
    files['evidence.json'] = _json(evidence_json)
    files['comparison_candidates.json'] = _json(comparisons)
    files['model_findings.json'] = _json(findings)
    validation = _checked_references({key: val for key, val in files.items() if key.endswith('.md')},
                                     {item.id for item in evidence})
    if not validation['passed']:
        raise Stage3Error('Citation validation failed: ' + '; '.join(validation['errors']))
    files['validation.json'] = _json(validation)

    # Local wall-clock time as requested; monotonic suffix only on collisions.
    run_id = 'draft-' + datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
    manifest = {
        'stage': 3, 'run_id': run_id, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'project': ctx.title, 'context_sha256': ctx.sha256,
        'plan_sha256': plan['plan_sha256'],
        'capabilities_in_plan': [t['capability'] for t in plan['tasks']],
        'executed_capabilities': sorted(capabilities & {'analyze', 'compare', 'gaps', 'consolidate', 'design', 'generate'}),
        'stage4_pending_capabilities': sorted(capabilities & {'validate', 'review', 'publish'}),
        'document_hashes': {row['relative_path']: row['content_sha256']
                            for row in inventory(ctx.project_dir)},
        'evidence_selection': stats, 'inference': inference,
        'approval_status': 'draft_only', 'no_external_api_used': llm != 'openai',
        'files': {name: sha256(text.encode('utf-8')).hexdigest() for name, text in files.items()},
    }
    files['manifest.json'] = _json(manifest)
    # Catch modifications made after evidence selection, including during model inference.
    check_fresh_index(ctx)
    base = _safe_output_base(ctx)
    destination = base / run_id
    count = 2
    while destination.exists():
        destination = base / f'{run_id}-{count:02d}'
        count += 1
    run_id = destination.name
    manifest['run_id'] = run_id
    files['manifest.json'] = _json(manifest)
    destination.mkdir(exist_ok=False)
    for name, content in files.items():
        output_path = destination / name
        output_path.write_text(content, encoding='utf-8', errors='strict')
    return {'project': ctx.title, 'run_id': run_id, 'output_dir': str(destination),
            'files_created': sorted(files), 'evidence_selection': stats,
            'llm': inference['provider'], 'status': 'draft_for_review'}
