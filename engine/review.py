"""Persist plan drafts and fail-closed human approval decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from .context import ProjectContext, parse_context
from .planner import validate_plan, render_plan


def _reviews_path(ctx: ProjectContext) -> Path:
    path = ctx.project_dir / "reviews"
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("reviews/ must be an ordinary directory, not a symlink or file")
    path.mkdir(exist_ok=True)
    return path


def save_draft(ctx: ProjectContext, plan: dict) -> tuple[Path, Path]:
    validate_plan(plan)
    path = _reviews_path(ctx)
    json_path = path / "plan.json"
    markdown_path = path / "plan.md"
    if json_path.is_symlink() or markdown_path.is_symlink():
        raise ValueError("Refusing to write to a symlinked output file")
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_plan(plan), encoding="utf-8")
    return json_path, markdown_path


def read_draft(ctx: ProjectContext) -> dict:
    path = _reviews_path(ctx) / "plan.json"
    if not path.exists():
        raise FileNotFoundError("No draft plan exists. Run `python main.py --project ...` first.")
    if path.is_symlink():
        raise ValueError("Refusing to read symlinked plan")
    plan = json.loads(path.read_text(encoding="utf-8"))
    validate_plan(plan)
    if plan["context_sha256"] != ctx.sha256:
        raise ValueError("context.md has changed since planning. Generate a new plan before approval.")
    return plan


def record_decision(ctx: ProjectContext, approved: bool, comment: str = "") -> tuple[Path, dict]:
    plan = read_draft(ctx)
    if not approved and not comment.strip():
        raise ValueError("A rejection requires --comment explaining what needs revision")
    event = {
        "status": "approved" if approved else "rejected",
        "plan_sha256": plan["plan_sha256"],
        "context_sha256": ctx.sha256,
        "decided_at_utc": datetime.now(timezone.utc).isoformat(),
        "comment": comment,
    }
    path = _reviews_path(ctx) / "decision.json"
    if path.is_symlink():
        raise ValueError("Refusing to overwrite symlinked decision")
    path.write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, event


def get_status(ctx: ProjectContext) -> str:
    try:
        plan = read_draft(ctx)
    except FileNotFoundError:
        return "no_plan"
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return "stale_or_invalid_plan"
    path = _reviews_path(ctx) / "decision.json"
    if not path.is_file() or path.is_symlink():
        return "awaiting_review"
    try:
        decision = json.loads(path.read_text(encoding="utf-8"))
        if decision.get("plan_sha256") != plan["plan_sha256"]:
            return "awaiting_review"
        if decision.get("context_sha256") != ctx.sha256:
            return "awaiting_review"
        return decision["status"] if decision.get("status") in {"approved", "rejected"} else "awaiting_review"
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return "awaiting_review"

# Stage 4 — independent local QA review, approval, and immutable release copies.
# Model-generated claims are never considered factually verified by these checks.
from hashlib import sha256
import re
import shutil
from .store import check_fresh_index, inventory


def _as_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def _draft_path(project_dir: Path, draft_id: str | None = None) -> Path:
    base = project_dir / 'outputs' / 'stage3'
    if base.is_symlink() or not base.is_dir():
        raise ValueError('No generated drafts under outputs/stage3/')
    if draft_id:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,100}', draft_id):
            raise ValueError('--draft-id must be a plain folder name')
        folder = base / draft_id
    else:
        options = [d for d in base.iterdir() if d.is_dir() and not d.is_symlink()
                   and (d / 'manifest.json').is_file() and not (d / 'manifest.json').is_symlink()]
        if not options:
            raise ValueError('No draft run found')
        folder = max(options, key=lambda d: (d.stat().st_mtime_ns, d.name))
    if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(base.resolve()):
        raise ValueError('Draft folder is missing or outside project outputs')
    return folder


def _load_manifest(folder: Path) -> dict:
    manifest = folder / 'manifest.json'
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError('Draft manifest missing or symlinked')
    result = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(result, dict) or not isinstance(result.get('files'), dict):
        raise ValueError('Invalid draft manifest')
    if result.get('run_id') != folder.name:
        raise ValueError('Draft folder name does not match manifest')
    return result


def _quality_assessment(project_dir: Path, draft_id: str | None) -> tuple[Path, dict]:
    ctx = parse_context(project_dir)
    folder = _draft_path(ctx.project_dir, draft_id)
    manifest = _load_manifest(folder)
    blockers: list[str] = []
    warnings: list[str] = []
    files = manifest['files']
    for filename, expected in files.items():
        if filename in {'.', '..'} or '/' in filename or '\\' in filename:
            blockers.append(f'Invalid filename in manifest: {filename}')
            continue
        fpath = folder / filename
        if fpath.is_symlink() or not fpath.is_file():
            blockers.append(f'Missing or symlinked output: {filename}')
        elif sha256(fpath.read_bytes()).hexdigest() != expected:
            blockers.append(f'Draft modified since generation: {filename}')
    if manifest.get('context_sha256') != ctx.sha256:
        blockers.append('context.md changed after draft generation')
    try:
        if get_status(ctx) != 'approved':
            blockers.append('Current context execution plan is no longer approved')
        plan = read_draft(ctx)
        if plan.get('plan_sha256') != manifest.get('plan_sha256'):
            blockers.append('Approved execution plan differs from the draft')
    except (OSError, ValueError, KeyError) as e:
        blockers.append('Cannot verify approved execution plan: ' + str(e))
    try:
        current_docs = {r['relative_path']: r['content_sha256'] for r in check_fresh_index(ctx)}
        if manifest.get('document_hashes') != current_docs:
            blockers.append('Indexed document versions differ from the draft')
    except (OSError, ValueError) as e:
        blockers.append('Source document freshness check failed: ' + str(e))
    evidence_file = folder / 'evidence.json'
    evidence_ids: set[str] = set()
    evidence: list[dict] = []
    try:
        if evidence_file.is_symlink():
            raise ValueError('evidence.json is symlinked')
        evidence = json.loads(evidence_file.read_text(encoding='utf-8'))
        if not isinstance(evidence, list):
            raise ValueError('Evidence must be a list')
        for entry in evidence:
            eid = entry['id']
            if eid in evidence_ids or not re.fullmatch(r'E\d{4,}', eid):
                blockers.append(f'Duplicate/invalid evidence ID: {eid}')
            evidence_ids.add(eid)
            if manifest.get('document_hashes', {}).get(entry.get('relative_path')) != entry.get('document_sha256'):
                blockers.append(f'Evidence source hash mismatch for {eid}')
    except (OSError, ValueError, KeyError, TypeError) as e:
        blockers.append('Cannot validate evidence mapping: ' + str(e))
    found_citations: set[str] = set()
    for filename in files:
        if not filename.endswith('.md') or '/' in filename or '\\' in filename:
            continue
        path = folder / filename
        if path.is_symlink() or not path.is_file():
            continue
        found_citations.update(re.findall(r'\[(E\d{4,})\]', path.read_text(encoding='utf-8')))
    missing_citations = found_citations - evidence_ids
    if missing_citations:
        blockers.append('Unknown document citations: ' + ', '.join(sorted(missing_citations)))
    try:
        findings = json.loads((folder / 'model_findings.json').read_text(encoding='utf-8'))
        for row in findings:
            if not row.get('evidence_ids') or any(cid not in evidence_ids for cid in row['evidence_ids']):
                blockers.append('Model finding has invalid/empty evidence IDs')
    except (OSError, ValueError, TypeError, KeyError) as e:
        blockers.append('Cannot validate model findings: ' + str(e))
    selection = manifest.get('evidence_selection', {})
    partial = (not selection.get('coverage_complete', False) or
               selection.get('omitted_chunks', 0) > 0 or
               bool(selection.get('unrepresented_documents')) or
               bool(selection.get('unindexed_paths')))
    if partial:
        warnings.append(f"Exploratory source selection only: {selection.get('selected_chunks', 0)}/"
                        f"{selection.get('indexed_chunks', 0)} chunks; "
                        f"{selection.get('omitted_chunks', 0)} omitted. Not exhaustive.")
    if selection.get('unindexed_paths'):
        warnings.append('Unsupported/unindexed paths: ' + ', '.join(selection['unindexed_paths'][:10]))
    if manifest.get('stage') == 5:
        # Stage 5 separates full indexed-text traversal from successful model delivery.
        model_input_complete = bool(selection.get('model_input_coverage_complete', False))
        if not model_input_complete:
            warnings.append('Full indexed-text traversal did not deliver all source text to an LLM (e.g. deterministic mode).')
        if selection.get('reference_documents', 0) == 0:
            warnings.append('No authoritative references indexed; reference-based comparisons are not established')
        try:
            report_file = folder / 'source_coverage.json'
            if report_file.is_symlink():
                raise ValueError('Coverage report is symlinked')
            detailed = json.loads(report_file.read_text(encoding='utf-8'))
            metrics = detailed['source_stats']
            if (metrics.get('indexed_chunks') != selection.get('indexed_chunks') or
                    metrics.get('indexed_source_characters') != selection.get('indexed_source_characters') or
                    len(detailed['batch_deliveries']) != selection.get('processed_batches')):
                blockers.append('Detailed Stage 5 coverage report disagrees with manifest')
            if not isinstance(detailed.get('batch_deliveries'), list):
                blockers.append('Invalid Stage 5 batch delivery report')
        except (OSError, ValueError, TypeError, KeyError) as e:
            blockers.append('Cannot validate full analysis coverage: ' + str(e))
        warnings.append('Source text passed through bounded batches; full semantic entailment and cross-source comparison are not established.')
    if not found_citations:
        warnings.append('No evidence citations found in generated Markdown')
    if not any(str(e.get('relative_path', '')).startswith('inputs/') for e in evidence if isinstance(e, dict)):
        warnings.append('No company input sources represented; not a comparative process assessment')
    if not any(str(e.get('relative_path', '')).startswith('references/') for e in evidence if isinstance(e, dict)):
        warnings.append('No reference sources represented; normative comparison not established')
    warnings.append('Citations checked syntactically, not for semantic entailment; a human must verify claims.')
    warnings.append('Generated outputs are exploratory and may not cover every requested deliverable.')
    from .context import lines_as_items
    quality_criteria = lines_as_items(ctx.content('quality criteria', 'acceptance criteria', 'quality requirements'))
    result = {
        'draft_id': folder.name,
        'project': ctx.title,
        'blockers': sorted(set(blockers)),
        'warnings': sorted(set(warnings)),
        'source_coverage_complete': not partial,
        'model_input_coverage_complete': selection.get('model_input_coverage_complete') if manifest.get('stage') == 5 else None,
        'selected_chunks': selection.get('selected_chunks'),
        'indexed_chunks': selection.get('indexed_chunks'),
        'quality_criteria_for_manual_review': quality_criteria,
        'source_citations_used': sorted(found_citations),
        'human_fact_check_required': True,
        'document_checks_passed': not blockers,
    }
    digest = sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    result['assessment_sha256'] = digest
    return folder, result


def review_generated_draft(project_dir: Path, draft_id: str | None = None) -> dict:
    folder, report = _quality_assessment(project_dir, draft_id)
    for filename, content in {
        'quality_report.json': _as_json(report),
        'quality_report.md': (
            '# Draft quality report\n\n'
            + f"Run: `{folder.name}`\n\n"
            + f"Source coverage: **{'complete selection' if report['source_coverage_complete'] else 'partial selection'}**\n\n"
            + '## Blockers\n\n' + ('\n'.join('- ' + x for x in report['blockers']) or '- None') + '\n\n'
            + '## Warnings and limitations\n\n' + '\n'.join('- ' + x for x in report['warnings']) + '\n\n'
            + '## Acceptance criteria requiring human review\n\n'
            + ('\n'.join('- [ ] ' + x for x in report['quality_criteria_for_manual_review']) or '- [ ] Review against project context') + '\n'
        ),
    }.items():
        output = folder / filename
        if output.is_symlink():
            raise ValueError('Refusing symlinked QA report')
        output.write_text(content, encoding='utf-8')
    report['report_path'] = str(folder / 'quality_report.json')
    return report


def decide_generated_draft(project_dir: Path, draft_id: str | None, *,
                           approved: bool, comment: str, allow_partial: bool = False) -> dict:
    from getpass import getuser
    folder, result = _quality_assessment(project_dir, draft_id)
    if approved:
        if result['blockers']:
            raise ValueError('Cannot approve a draft with blocking QA issues: ' + '; '.join(result['blockers']))
        if not result['source_coverage_complete'] and (not allow_partial or not comment.strip()):
            raise ValueError('Partial source coverage: approval requires --allow-partial and --comment describing accepted limitations')
        if not comment.strip():
            raise ValueError('Approval requires --comment confirming manual evidence/quality review')
    elif not comment.strip():
        raise ValueError('Rejection requires --comment')
    decision = {
        'draft_id': folder.name, 'decision': 'approved' if approved else 'rejected',
        'scope': 'partial_exploratory' if approved and not result['source_coverage_complete'] else 'reviewed_draft',
        'reviewer_local_user': getuser(),
        'assessment_sha256': result['assessment_sha256'],
        'source_coverage_complete': result['source_coverage_complete'],
        'approved_at_utc': datetime.now(timezone.utc).isoformat(),
        'comment': comment,
        'does_not_certify_compliance': True,
    }
    path = folder / 'draft_decision.json'
    if path.is_symlink():
        raise ValueError('Refusing symlinked decision file')
    path.write_text(_as_json(decision), encoding='utf-8')
    return {'decision_file': str(path), **decision}


def publish_generated_draft(project_dir: Path, draft_id: str | None) -> dict:
    folder, current = _quality_assessment(project_dir, draft_id)
    decision_path = folder / 'draft_decision.json'
    if decision_path.is_symlink() or not decision_path.is_file():
        raise ValueError('Draft has not been approved by a human')
    decision = json.loads(decision_path.read_text(encoding='utf-8'))
    if decision.get('decision') != 'approved':
        raise ValueError('Draft was rejected or has no valid approval')
    if current['blockers'] or decision.get('assessment_sha256') != current['assessment_sha256']:
        raise ValueError('Draft approval is stale or QA blockers exist; review and approve again')
    if not current['source_coverage_complete'] and decision.get('scope') != 'partial_exploratory':
        raise ValueError('Partial source selection not explicitly acknowledged')
    # Rebuild a release copy of the quality report from source facts.
    review_generated_draft(project_dir, folder.name)
    root = folder.parent.parent / 'approved'
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError('Approved output root must be an ordinary directory')
    root.mkdir(exist_ok=True)
    destination = root / folder.name.replace('draft-', 'approved-', 1)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Approved release already exists; refusing to overwrite')
    destination.mkdir()
    manifest = _load_manifest(folder)
    for name in list(manifest['files']) + ['draft_decision.json', 'quality_report.json', 'quality_report.md']:
        source = folder / name
        if source.exists():
            if source.is_symlink():
                raise ValueError('Refusing symlinked release artifact')
            shutil.copyfile(source, destination / name)
    (destination / 'release.json').write_text(_as_json({
        'source_run_id': folder.name,
        'release_status': 'human_reviewed_partial' if not current['source_coverage_complete'] else 'human_reviewed',
        'does_not_certify_compliance': True,
        'released_at_utc': datetime.now(timezone.utc).isoformat(),
        'assessment_sha256': current['assessment_sha256'],
    }), encoding='utf-8')
    return {'status': 'published_locally', 'release_dir': str(destination),
            'scope': decision['scope'], 'does_not_certify_compliance': True}
