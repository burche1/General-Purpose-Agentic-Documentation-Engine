"""Local-first documentation planner, retrieval, and draft-generation CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from engine.context import parse_context
from engine.ingest import (ingest_project, run_stage3, full_plan, full_status,
                           run_full, full_api_preview, full_api_approve)
from engine.planner import plan_project
from engine.review import (get_status, record_decision, save_draft, review_generated_draft,
                           decide_generated_draft, publish_generated_draft)
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
    action.add_argument("--check", action="store_true", help="Check if approved plan and indexed evidence are ready for Stage 3")
    action.add_argument("--run", action="store_true", help="Generate a local draft")
    action.add_argument("--full-plan", action="store_true", help="Estimate exhaustive reference-first batches, no inference")
    action.add_argument("--run-full", action="store_true", help="Run or resume full collection analysis in batches")
    action.add_argument("--full-status", action="store_true", help="Inspect progress of a Stage 5 draft")
    action.add_argument("--preview-full-api", action="store_true", help="Preview next remote batch window; no API call")
    action.add_argument("--approve-full-api", metavar="WINDOW_SHA256", help="Approve next exact API batch window")
    action.add_argument("--preview-api", action="store_true", help="Save exact OpenAI request locally for approval; does not call API")
    action.add_argument("--approve-api", metavar="REQUEST_SHA256", help="Approve one exact previewed API payload and model")
    action.add_argument("--review-draft", action="store_true", help="Validate a generated draft and report limitations")
    action.add_argument("--approve-draft", action="store_true", help="Human-approve the specified generated draft")
    action.add_argument("--reject-draft", action="store_true", help="Reject a generated draft with a comment")
    action.add_argument("--publish-draft", action="store_true", help="Copy an approved draft into local approved outputs")
    parser.add_argument("--llm", choices=["none", "ollama", "openai"], default="ollama",
                        help="Inference backend; local Ollama is default. OpenAI requires exact payload approval")
    parser.add_argument("--resume-draft", help="Resume a Stage 5 draft or inspect its API batch window")
    parser.add_argument("--batch-chars", type=int, default=1800,
                        help="Maximum source evidence characters per batch including source locations (default 1800)")
    parser.add_argument("--batch-limit", type=int, default=8,
                        help="Maximum batches executed per invocation; zero creates a resumable run")
    parser.add_argument("--draft-id", help="Generated run folder name to review/approve/publish (defaults to latest)")
    parser.add_argument("--allow-partial", action="store_true", help="Explicitly acknowledge incomplete source selection on approval")
    parser.add_argument("--max-evidence", type=int, default=40,
                        help="Maximum source chunks used for Stage 3 (4–200)")
    parser.add_argument("--role", choices=["all", "inputs", "references"], default="all")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--match-all", action="store_true", help="Require all search terms")
    parser.add_argument("--comment", default="", help="Review comment")
    parser.add_argument("--planner", choices=["rules", "ollama"], default="rules")
    parser.add_argument("--model", default=None, help="Ollama model (default qwen2.5:1.5b); OpenAI: gpt-mini/gpt-pro aliases or full ID")
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
        if args.review_draft:
            result = review_generated_draft(ctx.project_dir, args.draft_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if not result["blockers"] else 1
        if args.approve_draft or args.reject_draft:
            result = decide_generated_draft(ctx.project_dir, args.draft_id,
                                            approved=args.approve_draft,
                                            comment=args.comment, allow_partial=args.allow_partial)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.publish_draft:
            result = publish_generated_draft(ctx.project_dir, args.draft_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.full_plan:
            result = full_plan(ctx.project_dir, batch_chars=args.batch_chars, llm=args.llm,
                               model=args.model or ("gpt-5.4-mini" if args.llm == "openai" else "qwen2.5:1.5b"))
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.full_status:
            if not args.resume_draft:
                raise ValueError('--full-status requires --resume-draft')
            print(json.dumps(full_status(ctx.project_dir, args.resume_draft), indent=2, ensure_ascii=False))
            return 0
        if args.run_full:
            result = run_full(ctx.project_dir, llm=args.llm,
                              model=args.model or ("gpt-5.4-mini" if args.llm == "openai" else "qwen2.5:1.5b"),
                              batch_chars=args.batch_chars, batch_limit=args.batch_limit,
                              resume_draft=args.resume_draft)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.preview_full_api or args.approve_full_api:
            if args.llm != 'openai' or not args.resume_draft:
                raise ValueError('Full OpenAI preview/approval requires --llm openai and --resume-draft')
            model = args.model or 'gpt-5.4-mini'
            if args.preview_full_api:
                result = full_api_preview(ctx.project_dir, draft_id=args.resume_draft,
                                          model=model, batch_chars=args.batch_chars,
                                          max_batches=args.batch_limit)
            else:
                result = full_api_approve(ctx.project_dir, draft_id=args.resume_draft,
                                          model=model, digest=args.approve_full_api,
                                          batch_chars=args.batch_chars,
                                          max_batches=args.batch_limit)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.run or args.check or args.preview_api or args.approve_api:
            result = run_stage3(ctx.project_dir, llm=args.llm,
                                model=args.model or ("qwen2.5:1.5b" if args.llm != "openai" else "gpt-5.4-mini"),
                                max_evidence=args.max_evidence, dry_run=args.check,
                                preview_api=args.preview_api, approve_api=args.approve_api)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.list_docs:
            print(json.dumps(inventory(ctx.project_dir), indent=2, ensure_ascii=False))
            return 0
        if args.search is not None:
            print(json.dumps(search(ctx.project_dir, args.search, role=args.role,
                                    limit=args.limit, match_all=args.match_all),
                             indent=2, ensure_ascii=False))
            return 0
        plan = plan_project(ctx, planner=args.planner, model=args.model or "qwen2.5:1.5b")
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
