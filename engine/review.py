"""Persist plan drafts and fail-closed human approval decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from .context import ProjectContext
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
