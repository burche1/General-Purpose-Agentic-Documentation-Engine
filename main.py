"""Local-first Stage 1 entry point. No document ingestion or execution occurs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from engine.context import parse_context
from engine.planner import plan_project
from engine.review import get_status, record_decision, save_draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan a local documentation project from context.md")
    parser.add_argument("--project", type=Path, required=True, help="Folder containing context.md")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--approve", action="store_true", help="Record explicit approval of existing plan")
    action.add_argument("--reject", action="store_true", help="Reject existing plan, requires --comment")
    action.add_argument("--status", action="store_true", help="Read current plan review status")
    parser.add_argument("--comment", default="", help="Comment for approval or rejection")
    parser.add_argument("--planner", choices=["rules", "ollama"], default="rules")
    parser.add_argument("--model", default="qwen2.5:7b", help="Local Ollama model if --planner ollama")
    args = parser.parse_args(argv)
    try:
        ctx = parse_context(args.project)
        if args.status:
            print(f"Plan status for {ctx.title}: {get_status(ctx)}")
            return 0
        if args.approve or args.reject:
            file_path, decision = record_decision(ctx, approved=args.approve, comment=args.comment)
            print(f"Plan {decision['status']}. Decision saved: {file_path}")
            print("No document processing has been executed.")
            return 0
        plan = plan_project(ctx, planner=args.planner, model=args.model)
        json_path, md_path = save_draft(ctx, plan)
        print(f"Project: {ctx.title}")
        print(f"Planner: {args.planner} | Proposed tasks: {len(plan['tasks'])}")
        print(f"JSON plan: {json_path}")
        print(f"Review-friendly plan: {md_path}")
        print("Status: draft. Read plan.md and then run with --approve or --reject.")
        print("No input documents were read and no tasks were executed.")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
