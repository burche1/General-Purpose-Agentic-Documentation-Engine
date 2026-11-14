# Document Agent — Stage 1: Context Parser & Execution Planner

This stage produces a **reviewable execution plan**, not generated documents.
It is domain-independent. ASPICE is an example project, not a hard-coded engine dependency.

## Requirements

- Python 3.10+ (standard library only)
- Optional: Ollama installed locally with a model such as `qwen2.5:7b`

## Quick start (no installs, no LLM required)

From the repository directory:

```bash
python3 main.py --project projects/aspice
cat projects/aspice/reviews/plan.md
python3 main.py --project projects/aspice --status
python3 main.py --project projects/aspice --approve
python3 main.py --project projects/aspice --status
```

Try a **second independent project**:

```bash
python3 main.py --project projects/architecture
cat projects/architecture/reviews/plan.md
```

To reject and explain a required change:

```bash
python3 main.py --project projects/aspice --reject --comment "Revise the expected deliverables"
```

Revise the project's `context.md`, run `python3 main.py --project ...` again, review the newly generated plan, and approve it.
Changing `context.md` invalidates prior approval. Editing `plan.json` also invalidates its hash. Editing `plan.md` does not change the executable plan; revise `context.md` instead.

## Optional local LLM planning

To let a local model choose among the **same safe, registered task capabilities**:

```bash
ollama pull qwen2.5:7b
# Ensure Ollama is serving locally on port 11434.
python3 main.py --project projects/aspice --planner ollama --model qwen2.5:7b
```

No remote endpoint is configurable or supported. The Ollama integration uses `http://127.0.0.1:11434/api/generate`. Ollama uses the structured JSON `format` capability documented in its official API. If the local service is unavailable, the command **fails closed**: it does not silently call another provider. Ollama mode is not tested end-to-end in the included environment.

## Project convention

```text
projects/<project>/
    context.md             # editable natural-language goals and constraints
    inputs/                # existing documents (not read until Stage 2)
    references/            # authoritative sources (not read until Stage 2)
    templates/             # optional document formats (not read until Stage 2)
    reviews/
        plan.json          # validated, dependency-ordered draft tasks
        plan.md            # readable plan for review
        decision.json      # approval/rejection for the exact plan/context
    outputs/               # not written at Stage 1
```

## How it works

1. `engine/context.py` reads `context.md`, preserving sections and a SHA-256 fingerprint.
2. `engine/catalog.py` provides generic capabilities and a deterministic planner baseline.
3. Optionally, `engine/ollama.py` proposes capability IDs using a **local** model.
4. `engine/planner.py` enforces supported operations, dependencies, quality criteria, and a draft-only state.
5. `engine/review.py` persists the JSON and Markdown plans and records explicit human approval.

There is **no LangGraph task execution yet**. LangGraph comes when tasks become executable in later stages. Stage 1 produces the validated task specification consumed by that future runtime. No arbitrary Python, shell commands, or file operation instructions from `context.md` are executed.

## Limitations

- The deterministic planner relies on simple keywords; free-form objectives benefit from local Ollama.
- This prototype recognizes headings such as Objective, Scope, Tasks, Outputs, Quality Criteria and Constraints; unknown sections remain preserved but are not all semantically interpreted by the rule-based planner.
- The structured plan validates capability IDs and task dependencies, not whether the objective is technically achievable.
- The first stage does not parse PDF/DOCX, index sources, run agents, or generate documents.
- No external LLM API fallback exists yet. A future explicit-approval adapter must display the exact model, destination, and text payload before transmission.
- Input files and review records are ignored by Git by default; verify any corporate repository and backup policies separately.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
