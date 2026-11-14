# Execution Plan — Embedded Software Architecture Consolidation

**Status:** Draft — awaiting human approval

**Planner:** rules
**Context SHA-256:** `aae5fa60b6a583a814d3a15b84d514b41f6310f169019243af2d7b945beb4815`

## Objective

Create one coherent embedded software architecture specification from several overlapping technical notes. Resolve duplicated explanations, identify contradictions, and clearly flag undecided design choices.

## Proposed tasks

| ID | Capability | Purpose | Depends on |
|---|---|---|---|
| T01 | Inventory documents | Identify sources, document roles, and versions. | — |
| T02 | Extract document content | Parse and normalize source content and source locations. | T01 |
| T03 | Build local retrieval index | Enable exact and semantic retrieval over local sources. | T02 |
| T04 | Analyze documents | Identify concepts, structures, responsibilities, and findings. | T02 |
| T05 | Compare documents and references | Map evidence, differences, and contradictions. | T03, T04 |
| T06 | Consolidate information | Merge overlapping material while tracking its provenance. | T04 |
| T07 | Design document structure | Define the proposed outline and document interfaces. | T04, T05, T06 |
| T08 | Generate document drafts | Produce output drafts from approved sources and structure. | T07 |
| T09 | Validate outputs | Verify source support and stated quality criteria. | T04, T05, T06, T08 |
| T10 | Review and approve outputs | Require a human decision before publication. | T09 |
| T11 | Publish local artifacts | Write approved outputs under the local project folder. | T10 |

## Scope

- Boot sequence, drivers, middleware and application modules.
- Preserve unresolved interface questions and alternatives.

## Expected deliverables

- Unified architecture specification (Markdown).
- Conflicting statements and open questions (Markdown).

## Quality criteria

- Preserve links to source notes.
- Flag uncertain design choices rather than inventing decisions.

## Constraints

- Everything stored locally.
- Do not overwrite the source notes.

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
