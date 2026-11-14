"""Execution capability registry. Stage 1 plans tasks; it does not run them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    id: str
    title: str
    description: str


CATALOG: tuple[Capability, ...] = (
    Capability("inventory", "Inventory documents", "Identify sources, document roles, and versions."),
    Capability("extract", "Extract document content", "Parse and normalize source content and source locations."),
    Capability("retrieve", "Build local retrieval index", "Enable exact and semantic retrieval over local sources."),
    Capability("analyze", "Analyze documents", "Identify concepts, structures, responsibilities, and findings."),
    Capability("compare", "Compare documents and references", "Map evidence, differences, and contradictions."),
    Capability("gaps", "Identify gaps", "Separate missing information, conflicting evidence, and confirmed gaps."),
    Capability("consolidate", "Consolidate information", "Merge overlapping material while tracking its provenance."),
    Capability("design", "Design document structure", "Define the proposed outline and document interfaces."),
    Capability("generate", "Generate document drafts", "Produce output drafts from approved sources and structure."),
    Capability("validate", "Validate outputs", "Verify source support and stated quality criteria."),
    Capability("review", "Review and approve outputs", "Require a human decision before publication."),
    Capability("publish", "Publish local artifacts", "Write approved outputs under the local project folder."),
)
BY_ID = {cap.id: cap for cap in CATALOG}
ORDER = {cap.id: idx for idx, cap in enumerate(CATALOG)}


def choose_capabilities(raw: str, task_text: str) -> list[str]:
    """Heuristic baseline, useful without any model; sections are prioritized."""
    t = (task_text or raw).lower()
    selected = {"inventory", "extract", "analyze"}
    patterns = {
        "retrieve": ("search", "retrieve", "references", "reference material", "traceability", "citation"),
        "compare": ("compare", "against", "aligned with", "alignment", "consistency", "contradict", "differences", "versus"),
        "gaps": ("gap", "missing", "compliance", "incomplete", "shortcoming", "requirement coverage"),
        "consolidate": ("consolidat", "merge", "combine", "deduplicat", "unif", "overlap"),
        "design": ("design", "architecture", "structure", "outline", "propos", "organize", "restructur"),
        "generate": ("generat", "creat", "produc", "draft", "write", "improv", "rewrite", "deliver"),
    }
    for cap, tokens in patterns.items():
        if any(token in t for token in tokens):
            selected.add(cap)
    # Even summary-only jobs should produce a requested artifact. We use generate
    # when the objective asks for a report, summary, document, or output.
    if any(k in raw.lower() for k in ("output", "report", "summary", "document", "deliverable")):
        selected.add("generate")
    if "compare" in selected or "gaps" in selected:
        selected.add("retrieve")
    if "generate" in selected:
        selected.add("design")
    selected.update({"validate", "review", "publish"})
    return sorted(selected, key=lambda item: ORDER[item])


# Stage 3: reusable extractive document capabilities
from collections import defaultdict
from .context import ProjectContext
from .store import Evidence, words


def _sample(text: str, size: int = 220) -> str:
    result = ' '.join(text.split())
    return result if len(result) <= size else result[:size-1].rstrip() + '…'


def _safe_heading(text: str) -> str:
    return ' '.join(text.replace('\r', ' ').replace('\n', ' ').split())


def analyze(evidence: list[Evidence], stats: dict) -> str:
    groups: dict[str, list[Evidence]] = defaultdict(list)
    for e in evidence:
        groups[e.relative_path].append(e)
    lines = [
        '# Document analysis (extractive)', '',
        '> Draft for human review. Extracted text is source evidence, not an adopted instruction.', '',
        f"Indexed documents: **{stats['indexed_documents']}**; indexed chunks: **{stats['indexed_chunks']}**; "
        f"selected evidence chunks: **{stats['selected_chunks']}**.", '',
    ]
    if stats['unindexed_paths']:
        lines.extend(['**Unindexed input/reference paths:**', ''])
        lines.extend('- ' + item for item in stats['unindexed_paths'])
        lines.append('')
    if stats['omitted_chunks']:
        lines.extend([f"**Coverage limitation:** {stats['omitted_chunks']} chunks omitted by the evidence limit. "
                      'Absence of a match is not proof of absence in the source material.', ''])
    for path, items in sorted(groups.items()):
        lines.extend([f'## {_safe_heading(path)}', ''])
        for e in items:
            lines.append(f'- {e.citation} **{e.locator}**: {_sample(e.content)}')
        lines.append('')
    if stats['unrepresented_documents']:
        lines.extend(['## Unrepresented documents', ''])
        lines.extend(f'- `{path}`' for path in stats['unrepresented_documents'])
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def compare(evidence: list[Evidence]) -> tuple[str, list[dict]]:
    """Suggest topical overlaps without claiming requirements are satisfied/missing."""
    inputs = [e for e in evidence if e.source_role == 'inputs']
    references = [e for e in evidence if e.source_role == 'references']
    other = references if references else inputs
    pairs = []
    for left in inputs:
        for right in other:
            if left.id == right.id or (not references and left.id >= right.id):
                continue
            common = words(left.content) & words(right.content)
            if len(common) >= 2:
                pairs.append({'source_ids': [left.id, right.id],
                              'topics': sorted(common)[:12],
                              'score': len(common),
                              'classification': 'candidate_topic_overlap'})
    pairs = sorted(pairs, key=lambda row: (-row['score'], row['source_ids']))[:20]
    lines = ['# Comparison candidates', '',
             '> These are keyword-based candidate relationships, not confirmed contradictions, gaps, or compliance results.', '']
    if not inputs:
        lines.extend(['No `inputs/` evidence was selected. Comparison with current documents was not possible.', ''])
    elif not pairs:
        lines.extend(['No candidate overlaps were found in the selected chunks. This is **not** evidence that a requirement is absent.', ''])
    else:
        for item in pairs:
            lines.append('- ' + ', '.join('[' + k + ']' for k in item['source_ids']) +
                         ': possible shared topics — ' + ', '.join(item['topics']))
        lines.append('')
    return '\n'.join(lines), pairs


def gaps(evidence: list[Evidence], comparisons: list[dict]) -> str:
    refs = [e for e in evidence if e.source_role == 'references']
    inputs = [e for e in evidence if e.source_role == 'inputs']
    linked = {pair['source_ids'][1] for pair in comparisons if len(pair['source_ids']) > 1}
    lines = ['# Open gap-analysis questions', '',
             '> **Not a compliance assessment.** A missing keyword match is not a confirmed gap.', '']
    if not refs:
        lines.extend(['There are no indexed reference chunks in the selected evidence. Add reference material to evaluate requirements.', ''])
    elif not inputs:
        lines.extend(['There are no selected input chunks to compare against the reference material.', ''])
    else:
        for ref in refs:
            if ref.id not in linked:
                lines.append(f'- {ref.citation} Could not identify a topical match in the selected inputs; verify manually against the full source collection.')
        if len(lines) == 4:
            lines.append('- All selected reference chunks have at least one candidate topical match. This does not establish satisfaction or completeness.')
        lines.append('')
    return '\n'.join(lines)


def consolidate(evidence: list[Evidence]) -> str:
    """Extractive consolidation: exact duplicates removed, citations retained."""
    chosen = [e for e in evidence if e.source_role == 'inputs']
    if not chosen:
        return '# Consolidated source excerpts\n\nNo input documents were selected; no consolidation was possible.\n'
    seen: dict[str, list[str]] = {}
    content: dict[str, str] = {}
    for e in chosen:
        normalized = ' '.join(e.content.casefold().split())
        seen.setdefault(normalized, []).append(e.id)
        content[normalized] = e.content
    lines = ['# Consolidated source excerpts', '',
             '> Extractive draft only. Exact duplicate chunks are grouped; conflicting design decisions are not resolved.', '']
    for i, (key, ids) in enumerate(seen.items(), 1):
        lines.extend([f'## Excerpt {i}', '', content[key].rstrip(), '',
                      'Sources: ' + ', '.join('[' + code + ']' for code in ids), ''])
    return '\n'.join(lines)


def draft(ctx: ProjectContext, evidence: list[Evidence], findings: list[dict], sections: list[dict]) -> str:
    """Draft with grounded model sections, or a deterministic source-linked outline."""
    lines = [f'# Draft — {_safe_heading(ctx.title)}', '',
             '> **Unapproved draft.** Human review required. Not a regulatory assessment.', '',
             '## Objective', '', ctx.content('objective', 'objectives', 'goals', 'goal'), '',
             '## Proposed content', '']
    if sections:
        for section in sections:
            lines.extend([f"### {_safe_heading(section['heading'])}", '',
                          section['text'] + ' ' + ' '.join('[' + e + ']' for e in section['evidence_ids']), ''])
    else:
        # No LLM: provenance-preserving outline, not fictitious authored prose.
        for e in evidence:
            if e.source_role == 'inputs':
                lines.extend([f'### {_safe_heading(e.relative_path)} — {_safe_heading(e.locator)}', '',
                              _sample(e.content, 800), '', 'Source: ' + e.citation, ''])
    if findings:
        lines.extend(['## Model-proposed observations (unverified)', ''])
        for finding in findings:
            lines.append('- ' + finding['text'] + ' ' +
                         ' '.join('[' + e + ']' for e in finding['evidence_ids']))
        lines.append('')
    lines.extend(['## Unresolved questions', '',
                  '- Are all relevant documents and revisions included?',
                  '- Are the source interpretations correct?',
                  '- Which changes or decisions require document-owner approval?', ''])
    return '\n'.join(lines)


def design_outline(ctx: ProjectContext, deliverables: list[str]) -> str:
    """Turn the approved Stage 1 deliverable list into a reviewable outline."""
    lines = ['# Proposed document structure', '',
             '> This outline is generated from the approved plan, not inferred requirements.', '',
             '## Project objective', '',
             ctx.content('objective', 'objectives', 'goals', 'goal'), '',
             '## Requested deliverables', '']
    for index, item in enumerate(deliverables, 1):
        lines.extend([f'### {index}. {_safe_heading(item)}', '',
                      '- Purpose and scope',
                      '- Source-supported content',
                      '- Open assumptions, contradictions and decisions',
                      '- Reviewer sign-off (Stage 4)', ''])
    return '\n'.join(lines)
