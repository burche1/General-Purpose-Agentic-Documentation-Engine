# Document Engineering Agent — v0.5 (Stages 1–5)

A **local-first, context-driven documentation engine** with one entry point (`main.py`) and one README. It ingests PDF/DOCX/Markdown and other supported documents into local SQLite, plans work from `context.md`, drafts local documentation, and requires human review for release. Stage 5 adds **lossless, reference-first, multi-batch analysis of the complete indexed collection**, with resumable execution.

> **Important:** This remains a prototype, **not an ASPICE compliance assessor**. Even when all indexed source text has been delivered to a model, its findings are not automatically correct. Stage 5 does not yet perform rigorous reference-to-company requirement adjudication or semantic entailment verification. The application is a deterministic Python workflow, **not yet a LangGraph runtime**.

## Upgrade existing Stage 4 in place

From the same Git working folder as `main.py`:

```bash
cd ~/Documents/General-Purpose-Agentic-Documentation-Engine
# Recommended: commit or back up your current work first.
unzip -o ~/Downloads/document_agent_stage5_in_place_update.zip -d .
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

The update replaces existing application files only. There is no separate Stage 5 launcher, extra guide, deleted code, or bundled company material. Existing project folders, `context.md`, `.env`, `.local/` indexes, plan approvals, and generated outputs remain untouched. An installed venv is reused.

## Project organization

```text
projects/aspice/
  context.md                     # Objectives and quality rules
  references/                    # Authoritative normative sources, e.g. ASPICE 4.1
  inputs/                        # Current company processes (nested folders allowed)
  reviews/                       # Plan and approval
  .local/                        # SQLite index and local external-API previews
  outputs/
    stage3/
      draft-dd-mm-yyyy-hh-mm-ss/ # Old Stage 3/4 drafts and new Stage 5 run folders
         progress.json           # Stage 5 resumable state
         .batches/              # Completed model calls stored locally
         ...                     # Final files written only after all batches succeed
    approved/                    # Separate human-reviewed publication copies
```

Keep `references/` distinct from `inputs/`. Stage 5 analyzes **references first**, then all input documents, maintaining source locations and document hashes.

## Stages 1–4 (unchanged commands)

```bash
python main.py --project projects/aspice                      # Plan from context.md
python main.py --project projects/aspice --approve            # Approve plan
python main.py --project projects/aspice --ingest             # Local incremental index
python main.py --project projects/aspice --search requirements
python main.py --project projects/aspice --check              # Stage 3 sampler check
python main.py --project projects/aspice --run --llm ollama   # Old exploratory mode
```

Stage 3 `--run` retains its previous sampled 40-chunk behavior to preserve backwards compatibility. **Use `--run-full` for Stage 5.**

## Stage 5: see how much work the full collection requires

```bash
python main.py --project projects/aspice --full-plan --llm ollama --model qwen2.5:1.5b
```

No model call and no draft are created. The result includes indexed documents, chunks, source characters, reference batches, total batches, and an approximate input-token range (not a cost guarantee). **There is no arbitrary 40-chunk cap in this mode.**

Data is split into small, lossless segments with evidence IDs and original source locators, placed into bounded batches one document at a time. Larger chunks are split into contiguous character ranges, never truncated. Every indexed source passage is prepared, and reference documents are always first. Unsupported and unindexed sources are explicitly reported.

**All docs can require many inference calls.** On a CPU-only laptop, use limited batches and resume deliberately. Stage 5 does not schedule work in the background.

### Local Ollama run — default

```bash
python main.py --project projects/aspice --run-full \
  --llm ollama --model qwen2.5:1.5b --batch-limit 8
```

The response includes the new draft folder name, e.g. `draft-14-11-2026-18-32-21`, and completion counts. This run will typically remain `in_progress` after the first 8 batches.

To continue **the same run**:

```bash
python main.py --project projects/aspice --run-full \
  --llm ollama --model qwen2.5:1.5b \
  --resume-draft draft-14-11-2026-18-32-21 --batch-limit 8
```

Check status at any time:

```bash
python main.py --project projects/aspice --full-status \
  --resume-draft draft-14-11-2026-18-32-21
```

The default `--batch-chars 1800` fits the small Qwen2.5 local context and its JSON retry budget. Ollama mode refuses values above 1900 because the legacy retry logic could otherwise omit source segments. If the LLM fails, progress from already completed batches remains on disk; no external fallback is used. Do not alter indexed sources, plan, inference model, or batch-size settings during a run. A change blocks resumption.

To finish without calling an LLM (source traversal and deterministic audit only):

```bash
python main.py --project projects/aspice --run-full --llm none \
  --model none --batch-limit 100000
```

This will mark indexed text as traversed, **not** model-analyzed. The coverage report distinguishes these states.

### OpenAI full runs — explicit reviewed batch windows

**Never use company-confidential files with a remote model unless authorized.** OpenAI calls transmit selected exact source passages; local file storage does not prevent transmission. The application sends `store: false`, but this is not a zero-retention guarantee. It performs no remote file uploads or hosted indexing.

1. Save `OPENAI_API_KEY=...` in a Git-ignored `.env` (file permission `chmod 600 .env`); then `set -a; source .env; set +a` in the current terminal. Do not share or commit the key.
2. Estimate complete processing with `--full-plan --llm openai --model gpt-mini --batch-chars 12000`. Unlike local Ollama, the API backend supports up to 24,000 source-evidence characters per batch, reducing the number of requests. Use the **same** batch-size value for creation, preview, approval and execution.
3. Create a **resumable full run without sending data**:

```bash
python main.py --project projects/aspice --run-full \
  --llm openai --model gpt-mini --batch-chars 12000 --batch-limit 0
```

Copy the returned `run_id` in the next commands.

4. Preview the **exact next 8 requests**. This saves a local window manifest and individual complete request previews:

```bash
python main.py --project projects/aspice --preview-full-api \
  --llm openai --model gpt-mini \
  --resume-draft YOUR_RUN_ID --batch-chars 12000 --batch-limit 8
```

5. **Inspect every listed request preview** (endpoint, model, exact document excerpts). If acceptable and company-authorized, approve the window digest from the preview result:

```bash
python main.py --project projects/aspice --approve-full-api WINDOW_SHA256 \
  --llm openai --model gpt-mini \
  --resume-draft YOUR_RUN_ID --batch-chars 12000 --batch-limit 8
```

6. Execute **only these eight authorized requests**:

```bash
python main.py --project projects/aspice --run-full \
  --llm openai --model gpt-mini \
  --resume-draft YOUR_RUN_ID --batch-chars 12000 --batch-limit 8
```

Repeat preview, approval, run until completed. The window digest binds the exact model, payload contents, document snapshot, and batch numbers. Every API request has **single-use authorization**. If a network attempt fails, that request must be reapproved before retrying; completed earlier batches are reused. Approving a window authorizes up to the displayed number of paid requests; check your API budget before approving. No automatic remote fallback or retries occur.

Existing aliases: `gpt-mini` → `gpt-5.4-mini`, `gpt-pro` → `gpt-5.5-pro`. Pro is considerably more expensive; model availability depends on the account. The displayed input-token estimate excludes instruction tokens, output, reasoning, and provider-specific pricing. **The program does not enforce a dollar-denominated spending cap.**

### Outputs and quality checks

Only after **all planned batches complete** does Stage 5 create `manifest.json`, `draft.md`, `analysis.md`, `model_observations.md`, `model_findings.json`, `evidence.json`, `source_coverage.json`, and other report files in the same run folder. Intermediate `.batches/*.json` and `progress.json` remain available for audit.

`source_coverage.json` includes per-document chunk counts, number of source characters, source segment counts, and per-batch model evidence IDs. `evidence.json` preserves original text segments, locators and source hashes. This allows checking that the model prompt received **all indexed source text over multiple calls** instead of an arbitrarily selected sample. It does *not* establish that the model understood, synthesized or accurately compared it all. The final draft is a compilation of local batch-level findings, **not** a validated, comprehensive cross-document process design.

Once the status becomes `draft_for_review`:

```bash
python main.py --project projects/aspice --review-draft --draft-id YOUR_RUN_ID
```

The Stage 4 approval and publication flow is unchanged (`--approve-draft`, then `--publish-draft`). Human review must verify factual claims, normative applicability, contradictions, process interfaces and whether the desired deliverables have actually been produced. Source coverage and semantic correctness are separate dimensions.

## Security and limitations

- All source documents, indexes, prompts for API approval, batch results and final artifacts live locally. LLM requests are sent only to Ollama loopback or explicitly approved OpenAI payloads.
- The existing extraction quality and format coverage limitations remain; unsupported files are listed. Source hash checks prevent stale indexes and modified documents from being analyzed silently.
- A `context.md` plan alone cannot guarantee the correctness of normative interpretation. Source data are treated as untrusted content, not instructions.
- A very large collection may produce hundreds/thousands of batch requests; use `--full-plan` before committing resources.
- Batch outputs and syntactically valid citations **are not** requirement coverage or a regulatory assessment. A future phase should implement reference-to-input evidence matching and semantic verification before making compliance conclusions.
- LangGraph has not yet been wired into the runnable application; Stage 5 uses a resumable deterministic state machine compatible with future LangGraph migration.

## Test suite

```bash
python -m unittest discover -s tests -v
```

The tests cover the preexisting Stages 1–4 and Stage 5 source traversal, reference priority, lossless splitting, resume behavior, invalid results, local/no-LLM modes, full API preview/approval and source changes. Live Ollama and authenticated OpenAI full-run execution require testing on your machine.
