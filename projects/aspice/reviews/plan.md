# Execution Plan — Automotive Software Process Engineering

**Status:** Draft — awaiting human approval

**Planner:** rules
**Context SHA-256:** `d84f34ae43f48db02ab08d0e51722346ef2ec0221727f69e1f5e74dc9804898f`

## Objective

Analyze our existing software development processes and draft improved process documentation aligned with the supplied Automotive SPICE 4.1 source material. Preserve valid existing practices and distinguish gaps from missing evidence.

## Proposed tasks

| ID | Capability | Purpose | Depends on |
|---|---|---|---|
| T01 | Inventory documents | Identify sources, document roles, and versions. | — |
| T02 | Extract document content | Parse and normalize source content and source locations. | T01 |
| T03 | Build local retrieval index | Enable exact and semantic retrieval over local sources. | T02 |
| T04 | Analyze documents | Identify concepts, structures, responsibilities, and findings. | T02 |
| T05 | Compare documents and references | Map evidence, differences, and contradictions. | T03, T04 |
| T06 | Identify gaps | Separate missing information, conflicting evidence, and confirmed gaps. | T05 |
| T07 | Design document structure | Define the proposed outline and document interfaces. | T04, T05, T06 |
| T08 | Generate document drafts | Produce output drafts from approved sources and structure. | T07 |
| T09 | Validate outputs | Verify source support and stated quality criteria. | T04, T05, T06, T08 |
| T10 | Review and approve outputs | Require a human decision before publication. | T09 |
| T11 | Publish local artifacts | Write approved outputs under the local project folder. | T10 |

## Scope

- SWE.1 to SWE.6 software engineering processes.
- Include roles, process interfaces, work products and traceability.
- Do not claim an official capability rating or assessment outcome.

## Expected deliverables

- As-is process inventory (Markdown).
- Evidence and traceability matrix (CSV).
- Gap and inconsistency report (Markdown).
- Proposed process procedures (Markdown).
- Open questions for human review (Markdown).

## Quality criteria

- Cite source document and location for every substantive finding.
- Keep normative indicators distinct from actual mandatory requirements.
- Do not equate documented process design with demonstrated implementation.
- Do not invent requirements or project evidence.

## Constraints

- Store and process documents locally.
- Use only a local LLM unless an external payload is separately authorized.
- Never overwrite input or reference documents.
- Human approval is required before final publication.

## Assumptions — confirm

- Rule-based planning is heuristic; review its capability selection.

## Limitations and warnings

- Stage 1 creates and reviews a plan only; document processing is not implemented yet.
- External LLM calls are not implemented. Ollama mode uses local loopback only.

## Approval

Review this file and `plan.json`. To record approval:

```bash
python main.py --project <project-dir> --approve
```

Approval is a recorded decision only. Stage 1 never executes document operations.
