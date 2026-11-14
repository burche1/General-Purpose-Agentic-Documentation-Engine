# Document Agent — Stage 2: Generic Ingestion & Local Retrieval

A local-first, context-driven documentation project. **Stage 1** generates and approves a task plan from `context.md` (without reading documents). **Stage 2** extracts documents from `inputs/` and `references/`, creates a local SQLite FTS5 search index, and returns source-linked search results. There are no document-generating agents yet.

No cloud service, network connection, Ollama or LangGraph is required for Stage 2. Optional local Ollama planning from Stage 1 is preserved. Ollama is a separate system program; it does not need to be installed inside your `.venv`.

## Installation (Ubuntu)

Requires Python 3.10+ (Ubuntu 24.04 works).

```bash
cd document-agent-stage2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Quick start

```bash
# Stage 1: plan and approve (no documents read)
python main.py --project projects/aspice
cat projects/aspice/reviews/plan.md
python main.py --project projects/aspice --approve

# Add your own local documents under inputs/ and references/.
# Or use illustrative sample documents to test:
cp samples/example_swe1.md projects/aspice/inputs/
cp samples/example_reference.md projects/aspice/references/

# Stage 2: extract, index, inspect and search locally
python main.py --project projects/aspice --ingest
python main.py --project projects/aspice --list-docs
python main.py --project projects/aspice --search "requirements review"
python main.py --project projects/aspice --search "accountable roles" --role references
```

Outputs: `projects/aspice/.local/documents.sqlite3` (search index) and `.local/ingestion_report.json` (warnings/errors). Each search result contains the source role, relative document path, location (page, paragraph, slide, sheet row or line range), text excerpt, and ranking score. Run `--ingest` again after adding/editing/removing documents; unchanged documents are skipped and removed files are purged.

## Supported formats

- `.md`, `.markdown`, `.txt`, `.rst`: line-ranged text blocks
- `.pdf`: searchable text by page (PyMuPDF); image-only scans need later OCR support
- `.docx`: paragraph/table rows (python-docx)
- `.html`, `.htm`: visible text blocks (HTMLParser; scripts/styles ignored)
- `.csv`: row-by-row text (Python CSV)
- `.xlsx`: row text and sheet coordinates (openpyxl)
- `.pptx`: slide text and table rows (python-pptx)

For rich formats, this is **text extraction**, not perfect semantic document understanding: formulas, images, embedded diagrams, slide relationships, DOCX headers and footers are not interpreted. Location labels reflect the parser's view, not canonical citations. Unsupported files, oversized files (>25 MiB), and PDFs without extractable text produce errors. Source errors do not become empty evidence of noncompliance.

## Stage 2 architecture

- `engine/extractors.py`: format parsers, each yielding `{text, locator, kind}` blocks, with bounded chunking.
- `engine/ingest.py`: traverses only project `inputs/` and `references/`, hashes local files, extracts, increments index, records ingestion report.
- `engine/store.py`: project-local SQLite catalog with FTS5 indexing, metadata and source-located keyword retrieval.
- `main.py`: shared Stage 1 planner/review commands and Stage 2 ingestion/search commands.

## Safety and privacy

- All data stays in project-local files. Stage 2 has **no LLM calls and no network I/O**.
- `context.md` and file contents are **not executable instructions**. Parsing will never invoke shell commands or follow symlinks in input directories.
- Ingestion requires approval of the exact current Stage 1 plan. A changed `context.md` invalidates approval.
- `inputs/`, `references/`, `.local/`, review files, and generated output files should not be Git committed by default; verify `.gitignore` rules before pushing.
- Source-file hashes and source locations are preserved in the database. For the MVP, the original source files themselves are not copied into a separate immutable archive; treat them as the authority.
- Local Ollama can optionally interpret Stage 1 context only: `ollama pull qwen2.5:1.5b`, then `python main.py --project projects/aspice --planner ollama --model qwen2.5:1.5b`. No automatic external API fallback is implemented.

## Next stage

Stage 3 will connect the indexed evidence to reusable analysis and generation capabilities, adding grounded claims, citations, and model-assisted processing with human review. A deterministic coverage engine remains separate from any model judgment.

## Tests

```bash
python -m unittest discover -s tests -v
```
