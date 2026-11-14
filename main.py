"""Local-first documentation planner and Stage 2 document retrieval CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from engine.context import parse_context
from engine.ingest import ingest_project
from engine.planner import plan_project
from engine.review import get_status, record_decision, save_draft
from engine.store import inventory, search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan, ingest and search a local documentation project")
    parser.add_argument("--project", type=Path, required=True, help="Project folder containing context.md")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--approve", action="store_true", help="Approve the current plan")
    action.add_argument("--reject", action="store_true", help="Reject the plan (requires --comment)")
    action.add_argument("--status", action="store_true", help="Read current approval status")
    action.add_argument("--ingest", action="store_true", help="Read inputs/references into local SQLite search index")
    action.add_argument("--list-docs", action="store_true", help="List indexed documents")
    action.add_argument("--search", metavar="TEXT", help="Search indexed content")
    parser.add_argument("--role", choices=["all", "inputs", "references"], default="all")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--match-all", action="store_true", help="Require all search terms")
    parser.add_argument("--comment", default="", help="Review comment")
    parser.add_argument("--planner", choices=["rules", "ollama"], default="rules")
    parser.add_argument("--model", default="qwen2.5:1.5b", help="Local Ollama model for optional planning")
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
        if args.ingest:
            if get_status(ctx) != "approved":
                raise ValueError("Approve the current plan before ingestion: run plan, review plan.md, then --approve")
            result = ingest_project(ctx.project_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["errors"] else 0
        if args.list_docs:
            print(json.dumps(inventory(ctx.project_dir), indent=2, ensure_ascii=False))
            return 0
        if args.search is not None:
            print(json.dumps(search(ctx.project_dir, args.search, role=args.role,
                                    limit=args.limit, match_all=args.match_all),
                             indent=2, ensure_ascii=False))
            return 0
        plan = plan_project(ctx, planner=args.planner, model=args.model)
        json_path, md_path = save_draft(ctx, plan)
        print(f"Project: {ctx.title}")
        print(f"Planner: {args.planner} | Proposed tasks: {len(plan['tasks'])}")
        print(f"JSON plan: {json_path}")
        print(f"Review-friendly plan: {md_path}")
        print("Status: draft. Read plan.md, then run with --approve or --reject.")
        print("No input documents were read and no tasks were executed.")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, ImportError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
