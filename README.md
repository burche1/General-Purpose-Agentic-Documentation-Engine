# Document Engineering Agent — v0.4 (Stages 1–4)

A local-first, context-driven documentation engine. **One application** (`main.py`), **one README**, and the same project folders across stages. Stage 4 adds independent deterministic checks, human approval, immutable publication copies and optional explicitly approved OpenAI inference. Source documents and indexes remain local.

> **Status:** this is an exploratory documentation engineering tool, **not** an ASPICE compliance assessor. Validation checks file integrity, source identifiers and staleness; only human reviewers can establish whether claims are supported, current, complete and correct. The software does not use LangGraph yet.

## Updating an existing Stage 3 installation

Back up your work, then extract the **in-place Stage 4 update** from the root folder containing `main.py`:

```bash
cd ~/Documents/General-Purpose-Agentic-Documentation-Engine
unzip -o ~/Downloads/document_agent_stage4_in_place_update.zip -d .
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

This update modifies existing application files only. It does not delete or ship project documents, `context.md`, stored indexes, previous run folders, or your `.env` file. It does **not** contain extra launch scripts or separate guides. Previous Stage 3 run directories can still be reviewed.

If you prefer not to create a backup README in the project, back it up outside this folder.

## Project directory

```text
projects/aspice/
  context.md           # Project objectives and quality criteria
  inputs/              # Current organizational material
  references/          # Normative/source references
  reviews/             # Approved execution plan
  .local/              # SQLite index, ingestion metadata and API consent (Git ignored)
  outputs/
    stage3/draft-dd-mm-yyyy-hh-mm-ss/  # Unapproved new drafts
    approved/approved-dd-mm-yyyy-hh-mm-ss/  # Human-reviewed release copies
```

## Stage 1 — plan from context.md alone

```bash
python main.py --project projects/aspice
cat projects/aspice/reviews/plan.md
python main.py --project projects/aspice --approve
```

If `context.md` changes, create and approve a new plan. Approving a Stage 1 **plan** does not approve Stage 4 **document outputs**.

## Stage 2 — ingest & search locally

```bash
python main.py --project projects/aspice --ingest
python main.py --project projects/aspice --list-docs
python main.py --project projects/aspice --search 'requirements'
```

PDF, DOCX, Markdown, TXT, HTML, CSV, XLSX and PPTX extraction stays local. Scanned-only PDFs/complex diagrams may need manual extraction. Indexing is incremental on unchanged file hashes. Modified or additional documents require `--ingest` before generating and approving drafts.

## Stage 3 — generate a draft

Local Ollama is the **default LLM provider** for `--run`, and does not make cloud calls:

```bash
python main.py --project projects/aspice --check
python main.py --project projects/aspice --run --llm ollama --model qwen2.5:1.5b
```

Without any LLM:

```bash
python main.py --project projects/aspice --run --llm none
```

For a somewhat wider deterministic source sample (not an exhaustive analysis):

```bash
python main.py --project projects/aspice --run --llm none --max-evidence 200
```

The output uses your computer's local time, e.g. `draft-14-11-2026-17-30-20`. A `-02` suffix is added if two runs begin in the same second. Older run names remain reviewable. Each run contains `draft.md`, analysis, evidence, validation, and a manifest; no original source files are overwritten.

**Coverage caveat:** selecting 40 of 438 indexed chunks is not a full document analysis. Even when source selection is complete, the Ollama prompt may include only a smaller bounded sample. Never interpret a valid citation or generated prose as a verified normative interpretation.

## Stage 4 — validate, approve, and publish

Use a specific draft ID returned by Stage 3, or omit `--draft-id` for the latest run:

```bash
python main.py --project projects/aspice --review-draft \
    --draft-id draft-14-11-2026-17-30-20
```

Read `quality_report.md` inside the draft folder. It verifies source hashes, approved context/plan, references, basic output integrity and source coverage; it lists quality criteria for *manual* inspection.

**For a complete evidence selection**, after examining the full source material and all claims:

```bash
python main.py --project projects/aspice --approve-draft \
    --draft-id draft-14-11-2026-17-30-20 \
    --comment 'I reviewed the evidence, claims, and applicable criteria.'
```

**For a partial source selection** (such as your 40/438 example), acceptance requires an explicit limitation acknowledgement. The release remains labeled `partial_exploratory`, never as complete/ASPICE-compliant:

```bash
python main.py --project projects/aspice --approve-draft \
    --draft-id draft-14-11-2026-17-30-20 \
    --allow-partial \
    --comment 'Exploratory draft only: 398 chunks not covered; not a compliance conclusion.'
```

To reject:

```bash
python main.py --project projects/aspice --reject-draft \
    --draft-id draft-14-11-2026-17-30-20 \
    --comment 'The source interpretation needs revision.'
```

After approval:

```bash
python main.py --project projects/aspice --publish-draft \
    --draft-id draft-14-11-2026-17-30-20
```

Publication creates a **new local copy** under `outputs/approved/` and does not overwrite a previously published release. Changes to source documents, `context.md`, the plan, or any generated file invalidate the release gate. Review/approval is intentionally separate from the Stage 1 plan approval.

## Optional OpenAI API — disabled unless explicitly approved

The application defaults to local Ollama for inference. It never automatically switches to OpenAI after a local model error.

Friendly model aliases:

| Alias | OpenAI API model ID | Use |
| --- | --- | --- |
| `gpt-mini` | `gpt-5.4-mini` | Lower-cost, focused drafting |
| `gpt-pro` | `gpt-5.5-pro` | Expensive, demanding analysis |

Model accessibility depends on your API account. Check the OpenAI model catalog and billing before choosing Pro.

### A. Store credentials locally

Create a `.env` in the **repository root** using a local text editor:

```bash
nano .env
```

Put exactly one line in the file:

```dotenv
OPENAI_API_KEY=YOUR_KEY_HERE
```

Then restrict access and load it into the shell when needed:

```bash
chmod 600 .env
set -a
source .env
set +a
```

`.env` is ignored by Git. **Do not commit or paste the API key into `context.md`, prompts, terminal commands, screenshots, or chat.** The program reads `OPENAI_API_KEY` from the environment only when sending an already approved remote request. The API key is never saved in request previews or result manifests.

### B. Preview the exact payload (no network call)

```bash
python main.py --project projects/aspice --llm openai --model gpt-mini --preview-api
```

This creates a local, Git-ignored `.local/external_requests/<SHA256>.preview.json` file with the **complete exact prompt, excerpts, model, and destination URL**; file mode is `0600`. Read it carefully before approving and confirm your organization permits transmitting those excerpts to OpenAI.

### C. Approve this exact model and payload (still no network call)

```bash
python main.py --project projects/aspice --llm openai --model gpt-mini \
    --approve-api <REQUEST_SHA256_FROM_PREVIEW>
```

A change to any prompt text, evidence, context, or model invalidates this approval. **Each approval authorizes one network attempt.** If an attempt fails, explicitly approve the same preview again before retrying.

### D. Execute the authorized API request

```bash
python main.py --project projects/aspice --llm openai --model gpt-mini --run
```

This sends a small, selected sample of source excerpts (not the full local documents) to `https://api.openai.com/v1/responses` over HTTPS. The request sets `store:false`, uses a structured response, and has **no hosted file upload, search tool, or hosted vector store**. The resulting files are saved locally.

**Privacy:** the API call still transfers selected content to OpenAI. `store:false` does not mean zero provider-side retention or no abuse monitoring logs; see the [OpenAI API data controls documentation](https://developers.openai.com/api/docs/guides/your-data). Do not use external inference with unauthorized confidential materials.

**Cost:** all OpenAI API usage can incur charges; Pro is especially expensive. The engine does not make any automatic API retry or fallback calls.

## Verification

```bash
python -m unittest discover -s tests -v
```

The project uses the same `main.py` and existing `engine/` modules. The Stage 4 update has been tested using local deterministic workflows and mocked OpenAI responses. **Live Ollama and authenticated OpenAI API calls require testing on your computer.**
