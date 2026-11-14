# Document Agent — Local-First Documentation Engine (Stages 1–3)

One Python application, one `README.md`, one `main.py`. The project reads `context.md`, plans documentation work, extracts and indexes local documents, and produces source-linked **drafts for human review**. It is deliberately not a formal compliance assessor.

## Requirements and setup

Python 3.10+ on Ubuntu or another supported platform. In your existing working folder:

```bash
python3 -m venv .venv                 # only if not yet created
source .venv/bin/activate
python -m pip install -e .
```

The package overwrites only existing source-code paths and leaves `projects/`, `.local/`, `reviews/`, `inputs/`, `references/`, `templates/`, and `outputs/` unchanged. Your repository should not track confidential files by default.

## Complete workflow

```bash
# 1. Read context.md, propose a task plan, and review it
python main.py --project projects/aspice
cat projects/aspice/reviews/plan.md
python main.py --project projects/aspice --approve

# 2. Supply local documents in inputs/ and references/, then ingest them
python main.py --project projects/aspice --ingest
python main.py --project projects/aspice --list-docs
python main.py --project projects/aspice --search "requirements"

# 3. Validate the approved plan and source index (no generated files)
python main.py --project projects/aspice --check

# 4. Generate source-linked draft artifacts without an LLM
python main.py --project projects/aspice --run

# 5. Optional: locally inferred observations and prose sections
#    Requires Ollama installed separately and the model pulled locally.
ollama pull qwen2.5:1.5b
python main.py --project projects/aspice --run --llm ollama --model qwen2.5:1.5b
```

All Stage 1/2 commands remain available. When documents change, run `--ingest` again. When `context.md` changes, regenerate and approve a new plan first. The `--check` and `--run` flags fail closed if the plan is not approved, the ingestion report has errors, or the indexed documents have changed. An `--ingest` command still requires Stage 1 approval.

## Stage 3 generated artifacts

Each `--run` creates a new folder under `projects/<name>/outputs/stage3/<run-id>/`, containing applicable artifacts:

- `analysis.md` — extracted local evidence with source IDs and locations
- `comparison.md` and `comparison_candidates.json` — candidate topical overlaps, **not** verified contradictions
- `open_gap_questions.md` — questions to investigate, **not** confirmed missing requirements
- `consolidated_excerpts.md` — deduplicated original excerpts when consolidation was planned
- `document_outline.md` — outline based on requested deliverables
- `draft.md` — extractive draft or optional local-model prose draft
- `evidence.json` — source IDs, exact locations, file hashes and selected chunks
- `validation.json` — syntactic citation checks only
- `review_checklist.md` and `manifest.json` — review questions and reproducibility metadata

Some files appear only when their capability is included in the **approved** plan. The engine selects bounded evidence: the output is never a guarantee of exhaustive coverage. Inspect `manifest.json` and `analysis.md` for omitted/unindexed material.

## Document formats and limitations

Stage 2 handles searchable PDF, DOCX, Markdown, TXT, HTML, CSV, XLSX and PPTX text. Scanned PDFs and embedded diagrams are not fully interpreted. FTS5 search is lexical; semantic vector retrieval is not implemented yet. The rule-based Stage 3 analysis is exploratory and does not infer compliance or final correctness. The small local model can propose observations and draft text but cannot verify technical truth. Every draft requires human review; formal validation and publishing remain Stage 4 tasks.

## Privacy

All documents, indexes and output files remain on the local computer. Stage 3 permits no external API fallback. `--llm ollama` communicates only with `127.0.0.1:11434` using an allowlist (`qwen2.5:1.5b`, `qwen2.5:3b`); avoid installing cloud-proxied Ollama models. No document contents are treated as executable instructions. Unapproved plan changes, stale indexes, and source failures stop analysis.

## Architecture within existing files

- `main.py`: common CLI for all stages (planning, approval, ingestion, search, check, run)
- `engine/context.py`: parse human-authored `context.md`
- `engine/planner.py`: capability selection and validated execution plan
- `engine/review.py`: human plan approval and status
- `engine/extractors.py`: local document format extraction
- `engine/store.py`: SQLite/FTS5, local evidence selection and source freshness checks
- `engine/catalog.py`: reusable deterministic analysis/comparison/consolidation/drafting capabilities
- `engine/ollama.py`: optional local-only task planning and document interpretation
- `engine/ingest.py`: document index maintenance and the Stage 3 execution workflow

This is a **single-project, local Python MVP**. It intentionally does not require LangGraph yet; Stage 4 may introduce resumable graph orchestration and document sign-off. The modular functions are callable from a LangGraph graph later.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Updating an existing Stage 2 installation

First restore your exact Stage 2 Git commit and remove the old Stage 3 add-on files after backing up any work. Extract the replacement ZIP into the repository root with **overwrite** enabled (`unzip -o`), then run the tests. The ZIP has only files already present in Stage 2; it does not include project data or introduce a separate Stage 3 guide or launcher.
