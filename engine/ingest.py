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


# Stage 5 — resumable, reference-first full-document analysis.
# This remains a deterministic state machine; it is not yet a LangGraph runtime.
from .store import full_evidence_batches, evidence_display
from .ollama import (preview_remote, approve_remote, interpret_remotely,
                     interpret_locally, _remote_path)
import os


def _full_digest(batch: list[Evidence]) -> str:
    return sha256(''.join(evidence_display(e) for e in batch).encode('utf-8')).hexdigest()


def _full_state_location(ctx: ProjectContext, draft_id: str) -> Path:
    if not re.fullmatch(r'draft-[0-9A-Za-z-]{12,90}', draft_id):
        raise Stage3Error('Invalid --resume-draft name')
    root = _safe_output_base(ctx)
    folder = root / draft_id
    if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):
        raise Stage3Error('Full-analysis draft folder missing or symlinked')
    return folder


def _atomic_json(path: Path, value: dict | list) -> None:
    if path.is_symlink():
        raise Stage3Error('Refusing to overwrite a symlink')
    tmp = path.with_name(path.name + '.write-tmp')
    if tmp.exists() or tmp.is_symlink():
        raise Stage3Error('Stale temporary state file; inspect before retrying')
    try:
        with tmp.open('x', encoding='utf-8') as writer:
            writer.write(_json(value))
            writer.flush()
            os.fsync(writer.fileno())
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _full_prepare(path: Path, batch_chars: int) -> tuple[ProjectContext, dict, list[list[Evidence]], dict, str]:
    ctx, plan, capabilities = _validated_project(path)
    if 'analyze' not in capabilities:
        raise Stage3Error('Approved Stage 1 plan must include document analysis')
    batches, stats = full_evidence_batches(ctx, batch_chars=batch_chars)
    if not batches:
        raise Stage3Error('No indexed source content to analyze')
    hashes = [_full_digest(batch) for batch in batches]
    overall = sha256(_json({'hashes': hashes, 'context_sha256': ctx.sha256,
                            'plan_sha256': plan['plan_sha256']}).encode('utf-8')).hexdigest()
    return ctx, plan, batches, stats, overall


def _full_progress(folder: Path) -> dict:
    file = folder / 'progress.json'
    if file.is_symlink() or not file.is_file():
        raise Stage3Error('Full analysis progress.json missing or symlinked')
    try:
        data = json.loads(file.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Stage3Error('Unreadable full analysis state') from exc
    if data.get('stage') != 5 or data.get('run_id') != folder.name:
        raise Stage3Error('Invalid full analysis state')
    return data


def _full_context(path: Path, *, draft_id: str | None, llm: str, model: str,
                  batch_chars: int) -> tuple[ProjectContext, dict, list[list[Evidence]], dict, Path, dict]:
    ctx, plan, batches, stats, overall = _full_prepare(path, batch_chars)
    if draft_id:
        folder = _full_state_location(ctx, draft_id)
        state = _full_progress(folder)
        if (state.get('batch_plan_sha256') != overall or
                state.get('context_sha256') != ctx.sha256 or
                state.get('plan_sha256') != plan['plan_sha256'] or
                state.get('backend') != llm or state.get('model') != model or
                state.get('batch_chars') != batch_chars):
            raise Stage3Error('Full run configuration or indexed documents changed; cannot resume this draft')
    else:
        root = _safe_output_base(ctx)
        run_id = 'draft-' + datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
        folder = root / run_id
        number = 2
        while folder.exists() or folder.is_symlink():
            folder = root / f'{run_id}-{number:02d}'
            number += 1
        folder.mkdir(mode=0o700)
        (folder / '.batches').mkdir(mode=0o700)
        state = {
            'stage': 5, 'run_id': folder.name, 'project': ctx.title,
            'backend': llm, 'model': model, 'batch_chars': batch_chars,
            'context_sha256': ctx.sha256, 'plan_sha256': plan['plan_sha256'],
            'batch_plan_sha256': overall, 'total_batches': len(batches),
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'in_progress', 'last_completed_batch': 0,
            'processed_batches': 0, 'processed_segments': 0,
            'processed_source_characters': 0,
        }
        _atomic_json(folder / 'progress.json', state)
    for i in range(1, len(batches) + 1):
        previous = folder / '.batches' / f'batch-{i:06d}.json'
        if previous.is_symlink():
            raise Stage3Error('Symlink in completed batch records')
        if previous.exists():
            record = json.loads(previous.read_text(encoding='utf-8'))
            if (record.get('batch_sha256') != _full_digest(batches[i-1]) or
                    record.get('batch_number') != i or
                    record.get('evidence_ids_supplied') != ([e.id for e in batches[i-1]] if llm != 'none' else [])):
                raise Stage3Error('A saved batch record does not match indexed evidence')
    # Completed files, not a mutable counter, determine where to resume.
    state['processed_batches'] = sum((folder / '.batches' / f'batch-{i:06d}.json').is_file()
                                      for i in range(1, len(batches) + 1))
    return ctx, plan, batches, stats, folder, state


def full_plan(path: Path, *, batch_chars: int = 1800, llm: str = 'ollama',
              model: str = 'qwen2.5:1.5b') -> dict:
    if llm == 'ollama' and batch_chars > 1900:
        raise Stage3Error('Local Ollama mode requires --batch-chars <= 1900')
    ctx, plan, batches, stats, _ = _full_prepare(path, batch_chars)
    total_prompt_chars = sum(sum(len(evidence_display(e)) for e in batch) for batch in batches)
    return {
        'project': ctx.title, 'backend': llm, 'model': model,
        'source_priority': 'references before inputs',
        'indexed_documents': stats['indexed_documents'],
        'reference_documents': stats['reference_documents'],
        'input_documents': stats['input_documents'],
        'indexed_chunks': stats['indexed_chunks'],
        'source_characters': stats['indexed_source_characters'],
        'prepared_segments': stats['prepared_segments'],
        'batches_required': len(batches),
        'reference_batches_first': stats['reference_batches'],
        'approx_evidence_input_tokens': f"{total_prompt_chars // 5}–{total_prompt_chars // 3}",
        'warning': 'Estimate excludes prompts/output/retries; API fees and local runtime can be significant',
        'unindexed_paths': stats['unindexed_paths'],
        'no_llm_call': True, 'no_new_draft': True,
    }


def full_status(path: Path, draft_id: str) -> dict:
    ctx = parse_context(path)
    folder = _full_state_location(ctx, draft_id)
    state = _full_progress(folder)
    count = len(list((folder / '.batches').glob('batch-*.json')))
    return {**state, 'saved_batch_records': count,
            'remaining_batches': max(0, state['total_batches'] - count),
            'resume_command': f'python main.py --project {path} --run-full --resume-draft {draft_id} '
                              f'--llm {state["backend"]} --model {state["model"]} --batch-chars {state["batch_chars"]}'}


def _full_window(ctx: ProjectContext, folder: Path, batches: list[list[Evidence]],
                 *, model: str, max_batches: int) -> tuple[list[tuple[int, list[Evidence]]], list[dict], str]:
    missing = [(i, b) for i, b in enumerate(batches, 1)
               if not (folder / '.batches' / f'batch-{i:06d}.json').exists()]
    selected = missing[:max_batches]
    previews: list[dict] = []
    for i, batch in selected:
        preview = preview_remote(ctx, batch, model, budget=_full_progress(folder)['batch_chars'])
        if set(preview['evidence_ids']) != {e.id for e in batch}:
            raise Stage3Error('Remote request would omit source evidence; reduce --batch-chars')
        previews.append({'batch_number': i, 'batch_sha256': _full_digest(batch),
                         'request_sha256': preview['request_sha256'],
                         'preview_file': preview['full_payload_for_review']})
    signature = sha256(_json({'run_id': folder.name, 'model': model,
                              'batch_plan_sha256': _full_progress(folder)['batch_plan_sha256'],
                              'requests': [{k: entry[k] for k in ('batch_number', 'batch_sha256', 'request_sha256')}
                                           for entry in previews]}).encode('utf-8')).hexdigest()
    return selected, previews, signature


def full_api_preview(path: Path, *, draft_id: str, model: str,
                     batch_chars: int = 1800, max_batches: int = 8) -> dict:
    if not 1 <= max_batches <= 50:
        raise Stage3Error('--batch-limit must be between 1 and 50 for remote previews')
    ctx, plan, batches, stats, folder, state = _full_context(
        path, draft_id=draft_id, llm='openai', model=model, batch_chars=batch_chars)
    selected, previews, digest = _full_window(ctx, folder, batches, model=model, max_batches=max_batches)
    if not previews:
        raise Stage3Error('No remaining batches to preview')
    file = _remote_path(ctx) / f'full-window-{digest}.json'
    if file.is_symlink():
        raise Stage3Error('Refusing external window preview symlink')
    if not file.exists():
        _atomic_json(file, {'run_id': folder.name, 'model': model, 'window_sha256': digest,
                            'batch_plan_sha256': state['batch_plan_sha256'],
                            'requests': previews})
        file.chmod(0o600)
    return {'status': 'awaiting_api_window_approval', 'window_sha256': digest,
            'requests': len(previews), 'batch_numbers': [r['batch_number'] for r in previews],
            'review_manifest': str(file), 'request_previews': [p['preview_file'] for p in previews],
            'no_api_call': True, 'note': 'Inspect EVERY listed request preview before approving'}


def full_api_approve(path: Path, *, draft_id: str, model: str, digest: str,
                     batch_chars: int = 1800, max_batches: int = 8) -> dict:
    ctx, plan, batches, stats, folder, state = _full_context(
        path, draft_id=draft_id, llm='openai', model=model, batch_chars=batch_chars)
    _, previews, actual = _full_window(ctx, folder, batches, model=model, max_batches=max_batches)
    if actual != digest:
        raise Stage3Error('Window request hashes changed; preview again and reapprove')
    window_path = _remote_path(ctx) / f'full-window-{digest}.json'
    if window_path.is_symlink() or not window_path.is_file():
        raise Stage3Error('Window was not previewed')
    saved = json.loads(window_path.read_text(encoding='utf-8'))
    if saved.get('window_sha256') != digest or saved.get('requests') != previews:
        raise Stage3Error('Window preview file has changed; approval refused')
    for row in previews:
        approve_remote(ctx, batches[row['batch_number'] - 1], model, row['request_sha256'], budget=batch_chars)
    return {'status': 'full_window_approved', 'requests_authorized_once': len(previews),
            'batch_numbers': [r['batch_number'] for r in previews],
            'next_command': f'python main.py --project {path} --run-full --resume-draft {draft_id} '
                            f'--llm openai --model {model} --batch-chars {batch_chars} --batch-limit {len(previews)}',
            'no_api_call': True}


def _full_finalization(ctx: ProjectContext, plan: dict, folder: Path,
                       batches: list[list[Evidence]], stats: dict, state: dict) -> None:
    all_evidence = [item for b in batches for item in b]
    all_findings: list[dict] = []
    all_sections: list[dict] = []
    batch_metrics: list[dict] = []
    for i, batch in enumerate(batches, 1):
        path = folder / '.batches' / f'batch-{i:06d}.json'
        if not path.is_file() or path.is_symlink():
            raise Stage3Error('Cannot finalize; incomplete or unsafe batch records')
        entry = json.loads(path.read_text(encoding='utf-8'))
        all_findings.extend(entry['findings'])
        all_sections.extend(entry['sections'])
        batch_metrics.append({'batch': i, 'document': batch[0].relative_path,
                              'role': batch[0].source_role,
                              'evidence_segments': len(batch),
                              'source_characters': sum(len(e.content) for e in batch),
                              'model_evidence_ids': entry['evidence_ids_supplied']})
    all_ids = {item.id for item in all_evidence}
    all_delivered = {identifier for row in batch_metrics for identifier in row['model_evidence_ids']}
    model_complete = (all_ids == all_delivered and state['backend'] != 'none')
    if state['backend'] != 'none' and not model_complete:
        raise Stage3Error('Model delivery audit does not cover every source segment')
    stats = dict(stats)
    stats.update({'selected_chunks': stats['indexed_chunks'],
                  'processed_segments': len(all_evidence),
                  'omitted_chunks': 0, 'unrepresented_documents': [],
                  'coverage_complete': not stats['unindexed_paths'],
                  'processed_batches': len(batches),
                  'processed_source_characters': stats['indexed_source_characters'],
                  'model_input_coverage_complete': model_complete})
    docs = stats['documents']
    overview = ['# Full-collection source analysis', '',
                '> Every indexed chunk was prepared. Model interpretations remain unverified.', '',
                f"Indexed documents: **{stats['indexed_documents']}**; indexed chunks: **{stats['indexed_chunks']}**;",
                f"source text characters: **{stats['indexed_source_characters']}**; model-delivered: **{model_complete}**.", '',
                '## Authoritative / reference sources', '']
    for role in ('references', 'inputs'):
        if role == 'inputs':
            overview += ['## Existing documents', '']
        for doc, row in docs.items():
            if row['role'] == role:
                overview.append(f"- `{doc}` — {row['indexed_chunks']} chunks; {row['segments']} segments; {row['characters']} characters")
        overview.append('')
    if stats['unindexed_paths']:
        overview += ['## Unsupported sources', ''] + [f'- {p}' for p in stats['unindexed_paths']]
    observation = _render_llm_findings(all_findings)
    lines = [f'# Draft — {ctx.title}', '',
             '> Generated from bounded full-collection passes. Human review required; this is not a compliance assessment.', '',
             '## Objective', '', ctx.content('objective', 'objectives', 'goals', 'goal'), '',
             '## Reference-first model notes', '']
    if all_sections:
        by_id = {e.id: e for e in all_evidence}
        last_document = None
        for section in all_sections:
            first = section['evidence_ids'][0]
            src = by_id[first]
            if src.relative_path != last_document:
                lines += ['', f'### {src.relative_path}', '']
                last_document = src.relative_path
            lines += [f"**{section['heading']}**", '', section['text'] + ' ' +
                      ' '.join('[' + e + ']' for e in section['evidence_ids']), '']
    else:
        lines += ['No model-generated sections. Raw source text is available in evidence.json.', '']
    lines += ['## Limitations', '',
              '- Model findings reflect bounded section-level reading, not a verified cross-document requirement mapping.',
              '- A source citation is not proof that a claim is entailed by that source.',
              '- Normative correctness, applicability and organizational compliance require expert review.', '']
    files: dict[str, str] = {
        'analysis.md': '\n'.join(overview).rstrip() + '\n',
        'comparison.md': '# Cross-source comparison\n\nFull source collection was read in separate batches. '
                         'A source-to-requirement adjudication is **not** yet implemented; '
                         'absence of a finding must not be treated as absence of evidence.\n',
        'open_gap_questions.md': '# Open questions\n\n- Which source passages substantiate each proposed gap?\n'
                                 '- Which reference provisions are applicable?\n'
                                 '- Were any relevant source formats not indexed?\n',
        'document_outline.md': design_outline(ctx, plan.get('requested_deliverables', [])),
        'draft.md': '\n'.join(lines).rstrip() + '\n',
        'model_observations.md': observation,
        'model_findings.json': _json(all_findings),
        'comparison_candidates.json': _json([]),
        'evidence.json': _json([e.as_dict() for e in all_evidence]),
        'source_coverage.json': _json({'run_id': folder.name, 'source_stats': stats,
                                      'batch_deliveries': batch_metrics}),
        'review_checklist.md': '# Review checklist\n\n- [ ] Read reference material and validate interpretation.\n'
                               '- [ ] Review all claims against the original local files.\n'
                               '- [ ] Validate cross-document relationships, requirements, and applicability.\n'
                               '- [ ] Confirm unsupported/unindexed file list is acceptable.\n',
    }
    files['validation.json'] = _json(_checked_references(
        {name: val for name, val in files.items() if name.endswith('.md')}, all_ids))
    manifest = {
        'stage': 5, 'run_id': folder.name, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'project': ctx.title, 'context_sha256': ctx.sha256, 'plan_sha256': plan['plan_sha256'],
        'document_hashes': {d['relative_path']: d['content_sha256'] for d in inventory(ctx.project_dir)},
        'evidence_selection': stats,
        'inference': {'provider': state['backend'], 'model': state['model'],
                      'model_input_coverage_complete': model_complete},
        'approval_status': 'draft_only', 'no_external_api_used': state['backend'] != 'openai',
        'source_coverage_file': 'source_coverage.json',
        'files': {name: sha256(content.encode('utf-8')).hexdigest() for name, content in files.items()},
    }
    files['manifest.json'] = _json(manifest)
    for name, content in files.items():
        target = folder / name
        if target.exists() or target.is_symlink():
            raise Stage3Error(f'Output file already exists, refusing overwrite: {name}')
        target.write_text(content, encoding='utf-8')
    state['status'] = 'draft_for_review'
    state['last_completed_batch'] = len(batches)
    state['processed_batches'] = len(batches)
    state['processed_segments'] = len(all_evidence)
    state['processed_source_characters'] = stats['indexed_source_characters']
    _atomic_json(folder / 'progress.json', state)


def run_full(path: Path, *, llm: str = 'ollama', model: str = 'qwen2.5:1.5b',
             batch_chars: int = 1800, batch_limit: int = 8,
             resume_draft: str | None = None) -> dict:
    if llm not in {'none', 'ollama', 'openai'}:
        raise Stage3Error('Unknown inference backend')
    if llm == 'ollama' and batch_chars > 1900:
        raise Stage3Error('For the small local model, --batch-chars must be <= 1900 to avoid silent retry truncation')
    if not 0 <= batch_limit <= 100000:
        raise Stage3Error('--batch-limit must be between 0 and 100000')
    ctx, plan, batches, stats, folder, state = _full_context(
        path, draft_id=resume_draft, llm=llm, model=model, batch_chars=batch_chars)
    if state['status'] == 'draft_for_review':
        return {'status': 'draft_for_review', 'run_id': folder.name,
                'output_dir': str(folder), 'completed_batches': len(batches), 'total_batches': len(batches)}
    todo = [(i, b) for i, b in enumerate(batches, 1)
            if not (folder / '.batches' / f'batch-{i:06d}.json').exists()]
    # A zero batch limit creates a resumable draft without any LLM calls.
    for index, batch in todo[:batch_limit]:
        try:
            if llm == 'none':
                findings, sections = [], []
                inference = {'provider': 'none', 'evidence_ids_supplied': []}
            elif llm == 'ollama':
                findings, sections, inference = interpret_locally(ctx, batch, model)
                if set(inference['evidence_ids_supplied']) != {e.id for e in batch}:
                    raise Stage3Error('Local model prompt lost evidence (including retry); no batch was recorded')
            else:
                findings, sections, inference = interpret_remotely(ctx, batch, model, budget=batch_chars)
                if set(inference['evidence_ids_supplied']) != {e.id for e in batch}:
                    raise Stage3Error('Remote model prompt lost evidence; no batch was recorded')
        except (ValueError, RuntimeError, KeyError) as exc:
            raise Stage3Error(f'Full analysis {folder.name} paused at batch {index}; previous batches remain saved. '
                              f'Resume with --resume-draft {folder.name} after resolving: {exc}') from exc
        _atomic_json(folder / '.batches' / f'batch-{index:06d}.json', {
            'batch_number': index, 'batch_sha256': _full_digest(batch),
            'evidence_ids_supplied': [e.id for e in batch] if llm != 'none' else [],
            'source_characters': sum(len(e.content) for e in batch),
            'findings': findings, 'sections': sections,
            'inference': inference,
            'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        })
        state['last_completed_batch'] = index
        state['processed_batches'] += 1
        state['processed_segments'] += len(batch)
        state['processed_source_characters'] += sum(len(e.content) for e in batch)
        _atomic_json(folder / 'progress.json', state)
    done = len(list((folder / '.batches').glob('batch-*.json')))
    if done == len(batches):
        check_fresh_index(ctx)
        _full_finalization(ctx, plan, folder, batches, stats, state)
        status = 'draft_for_review'
    else:
        status = 'in_progress'
    return {
        'status': status, 'run_id': folder.name, 'output_dir': str(folder),
        'backend': llm, 'model': model, 'reference_batches_first': stats['reference_batches'],
        'completed_batches': done, 'total_batches': len(batches),
        'remaining_batches': len(batches) - done,
        'indexed_documents': stats['indexed_documents'], 'indexed_chunks': stats['indexed_chunks'],
        'model_input_coverage_complete': status == 'draft_for_review' and llm != 'none',
        'next_command': (f'python main.py --project {path} --run-full --resume-draft {folder.name} '
                         f'--llm {llm} --model {model} --batch-chars {batch_chars}'
                         if status == 'in_progress' else None),
    }
