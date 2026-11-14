"""Turn a Markdown project context into a validated, dependency-ordered task plan."""
from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

from .catalog import BY_ID, ORDER, choose_capabilities
from .context import ProjectContext, lines_as_items
from .ollama import select_with_ollama


def _read_objective(ctx: ProjectContext) -> str:
    objective = ctx.content("objective", "objectives", "goal", "goals", "mission", "purpose")
    if not objective:
        objective = ctx.content("introduction")
    if not objective.strip():
        raise ValueError("context.md needs a '## Objective' section or an introductory goal paragraph")
    return objective


def _ensure_capabilities(selection: list[str]) -> list[str]:
    """Constrain both deterministic and LLM plans to a safe, valid catalog."""
    selected = set(selection)
    if selected - BY_ID.keys():
        raise ValueError(f"Unsupported capabilities: {selected - BY_ID.keys()}")
    selected.update({"inventory", "extract", "analyze", "validate", "review", "publish"})
    if "gaps" in selected:
        selected.add("compare")
    if "compare" in selected:
        selected.add("retrieve")
    if "generate" in selected:
        selected.add("design")
    return sorted(selected, key=lambda item: ORDER[item])


def _dependencies(cap: str, selected: set[str]) -> list[str]:
    prior = {
        "inventory": [],
        "extract": ["inventory"],
        "retrieve": ["extract"],
        "analyze": ["extract"],
        "compare": ["analyze", "retrieve"],
        "gaps": ["compare"],
        "consolidate": ["analyze"],
        "design": ["analyze", "gaps", "consolidate", "compare"],
        "generate": ["design"],
        "validate": ["generate", "gaps", "consolidate", "compare", "analyze"],
        "review": ["validate"],
        "publish": ["review"],
    }
    return sorted({value for value in prior[cap] if value in selected}, key=lambda item: ORDER[item])


def plan_project(ctx: ProjectContext, planner: str = "rules", model: str = "qwen2.5:7b") -> dict[str, Any]:
    if planner not in {"rules", "ollama"}:
        raise ValueError("Planner must be 'rules' or 'ollama'")
    objective = _read_objective(ctx)
    task_text = ctx.content("tasks", "requested tasks", "workflow", "activities")
    quality = lines_as_items(ctx.content("quality criteria", "quality requirements", "acceptance criteria"))
    constraints = lines_as_items(ctx.content("constraints", "restrictions", "security", "policies"))
    outputs = lines_as_items(ctx.content("output requirements", "outputs", "deliverables", "desired outputs"))
    scope = lines_as_items(ctx.content("scope", "boundaries"))
    warnings: list[str] = []
    assumptions: list[str] = []
    if not task_text:
        assumptions.append("Task capabilities inferred from the objective because no ## Tasks section was supplied.")
    if not outputs:
        assumptions.append("No deliverables specified. Propose a general findings report; confirm before execution.")
        outputs = ["Findings report (Markdown)"]
    if not quality:
        assumptions.append("No project-specific quality criteria supplied; use generic source-grounding checks.")
        quality = ["Statements about source materials must be evidence-linked.",
                   "Separate assumptions from confirmed findings."]

    if planner == "ollama":
        selected, llm_notes = select_with_ollama(ctx.raw, model)
        assumptions.extend(f"Local model note: {note}" for note in llm_notes)
    else:
        selected = choose_capabilities(ctx.raw, task_text + "\n" + objective)
        assumptions.append("Rule-based planning is heuristic; review its capability selection.")
    selected = _ensure_capabilities(selected)
    selected_set = set(selected)
    # Stage 1 inspects only folder existence, not document contents.
    for folder in ("inputs", "references", "templates"):
        if not (ctx.project_dir / folder).is_dir():
            warnings.append(f"Optional project directory not found: {folder}/")
    warnings.append("Planning only proposes tasks; use --ingest and --run for local document processing.")
    warnings.append("External LLM calls are not implemented. Ollama mode uses local loopback only.")

    task_ids = {cap: f"T{idx:02d}" for idx, cap in enumerate(selected, start=1)}
    tasks = [
        {
            "id": task_ids[cap],
            "capability": cap,
            "title": BY_ID[cap].title,
            "purpose": BY_ID[cap].description,
            "depends_on": [task_ids[p] for p in _dependencies(cap, selected_set)],
            "status": "not_started",
        }
        for cap in selected
    ]
    base = {
        "schema_version": "1.0",
        "project": ctx.title,
        "context_file": "context.md",
        "context_sha256": ctx.sha256,
        "planner": {"mode": planner, "model": model if planner == "ollama" else None},
        "objective": objective,
        "scope": scope,
        "source_roles": {"inputs": "Current/project documents", "references": "Reference and normative material", "templates": "Optional output layouts"},
        "requested_deliverables": outputs,
        "quality_criteria": quality,
        "constraints": constraints,
        "tasks": tasks,
        "assumptions": assumptions,
        "warnings": warnings,
        "external_inference": {"enabled": False, "policy": "explicit_approval_required"},
        "requires_human_approval": True,
        "status": "draft",
    }
    base["plan_sha256"] = plan_digest(base)
    validate_plan(base)
    return base


def plan_digest(plan: dict[str, Any]) -> str:
    contents = {key: value for key, value in plan.items() if key != "plan_sha256"}
    payload = json.dumps(contents, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != "1.0":
        raise ValueError("Unsupported plan schema")
    if plan.get("plan_sha256") != plan_digest(plan):
        raise ValueError("Plan file hash mismatch (possibly edited). Re-run planning.")
    if plan.get("external_inference", {}).get("enabled") is not False:
        raise ValueError("External inference must be disabled in Stage 1")
    if plan.get("requires_human_approval") is not True:
        raise ValueError("Plan must require human approval")
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Plan has no tasks")
    task_ids = set()
    seen_caps = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Invalid task")
        if task.get("id") in task_ids or task.get("capability") in seen_caps:
            raise ValueError("Duplicate task or capability")
        if task.get("capability") not in BY_ID:
            raise ValueError("Unsupported task capability")
        if task.get("status") != "not_started":
            raise ValueError("Stage 1 plans cannot report executed work")
        if any(dep not in task_ids for dep in task.get("depends_on", [])):
            raise ValueError("Task dependencies must reference earlier tasks")
        task_ids.add(task["id"])
        seen_caps.add(task["capability"])
    if "review" not in seen_caps or "validate" not in seen_caps:
        raise ValueError("Review/validation requirements are missing")
    if plan.get("status") != "draft":
        raise ValueError("Stage 1 draft plan must remain in draft state")


def render_plan(plan: dict[str, Any]) -> str:
    def clean(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value)).replace("|", "\\|")

    lines = [
        f"# Execution Plan — {plan['project']}", "",
        "**Status:** Draft — awaiting human approval", "",
        f"**Planner:** {plan['planner']['mode']}",
        f"**Context SHA-256:** `{plan['context_sha256']}`", "",
        "## Objective", "", plan["objective"], "",
        "## Proposed tasks", "",
        "| ID | Capability | Purpose | Depends on |", "|---|---|---|---|",
    ]
    for task in plan["tasks"]:
        lines.append(f"| {task['id']} | {clean(task['title'])} | {clean(task['purpose'])} | {', '.join(task['depends_on']) or '—'} |")
    for key, title in (
        ("scope", "Scope"), ("requested_deliverables", "Expected deliverables"),
        ("quality_criteria", "Quality criteria"), ("constraints", "Constraints"),
        ("assumptions", "Assumptions — confirm"), ("warnings", "Limitations and warnings"),
    ):
        lines.extend(["", f"## {title}", ""])
        values = plan[key]
        if values:
            lines.extend(f"- {item}" for item in values)
        else:
            lines.append("- Not specified")
    lines += [
        "", "## Approval", "",
        "Review this file and `plan.json`. To record approval:", "",
        "```bash", "python main.py --project <project-dir> --approve", "```", "",
        "Approval is a recorded decision only. Stage 1 never executes document operations.", "",
    ]
    return "\n".join(lines)
