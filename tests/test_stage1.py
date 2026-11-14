import json
from pathlib import Path
import shutil
import tempfile
import unittest

from engine.context import parse_context
from engine.planner import plan_project, validate_plan
from engine.review import get_status, read_draft, record_decision, save_draft
from main import main

ROOT = Path(__file__).resolve().parents[1]


class StageOneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "sample"
        self.project.mkdir()
        (self.project / "context.md").write_text(
            "# Context\n\n## Project\nName: Example architecture consolidation\n\n"
            "## Objective\nConsolidate design notes into a single architecture document.\n\n"
            "## Tasks\n- Compare inconsistent interfaces\n- Merge overlapping descriptions\n"
            "- Generate architecture draft\n\n## Outputs\n- Architecture report (Markdown)\n",
            encoding="utf-8",
        )

    def test_parse_and_plan_are_generic(self):
        ctx = parse_context(self.project)
        self.assertEqual(ctx.title, "Example architecture consolidation")
        self.assertEqual(ctx.content("outputs"), "- Architecture report (Markdown)")
        plan = plan_project(ctx)
        caps = {task["capability"] for task in plan["tasks"]}
        self.assertIn("compare", caps)
        self.assertIn("consolidate", caps)
        self.assertIn("generate", caps)
        self.assertIn("review", caps)
        self.assertNotIn("gaps", caps)
        self.assertEqual(plan["external_inference"]["enabled"], False)
        validate_plan(plan)

    def test_approval_lifecycle_and_staleness(self):
        ctx = parse_context(self.project)
        plan = plan_project(ctx)
        save_draft(ctx, plan)
        self.assertEqual(get_status(ctx), "awaiting_review")
        record_decision(ctx, approved=True)
        self.assertEqual(get_status(ctx), "approved")
        with (self.project / "context.md").open("a", encoding="utf-8") as handle:
            handle.write("\n## Constraints\n- All local\n")
        new_ctx = parse_context(self.project)
        self.assertEqual(get_status(new_ctx), "stale_or_invalid_plan")
        with self.assertRaisesRegex(ValueError, "changed"):
            record_decision(new_ctx, approved=True)
        save_draft(new_ctx, plan_project(new_ctx))
        self.assertEqual(get_status(new_ctx), "awaiting_review")

    def test_plan_tampering_blocks_approval(self):
        ctx = parse_context(self.project)
        path, _ = save_draft(ctx, plan_project(ctx))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tasks"][0]["capability"] = "remote_upload"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            read_draft(ctx)

    def test_missing_objective_fails(self):
        (self.project / "context.md").write_text("# Context\n\n## Scope\n- Software\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Objective"):
            plan_project(parse_context(self.project))

    def test_rejection_requires_explanation(self):
        ctx = parse_context(self.project)
        save_draft(ctx, plan_project(ctx))
        with self.assertRaisesRegex(ValueError, "requires --comment"):
            record_decision(ctx, approved=False)
        record_decision(ctx, approved=False, comment="Need a better outline")
        self.assertEqual(get_status(ctx), "rejected")

    def test_stage1_does_not_open_input_files(self):
        (self.project / "inputs").mkdir()
        (self.project / "inputs" / "invalid.pdf").write_bytes(b"\x00\xFF\x00\xFE")
        ctx = parse_context(self.project)
        plan = plan_project(ctx)
        self.assertEqual(plan["status"], "draft")
        self.assertEqual((self.project / "inputs" / "invalid.pdf").read_bytes(), b"\x00\xFF\x00\xFE")

    def test_main_cli(self):
        self.assertEqual(main(["--project", str(self.project)]), 0)
        self.assertEqual(main(["--project", str(self.project), "--approve"]), 0)
        self.assertEqual(get_status(parse_context(self.project)), "approved")

    def test_second_independent_example(self):
        a = plan_project(parse_context(ROOT / "projects" / "aspice"))
        b = plan_project(parse_context(ROOT / "projects" / "architecture"))
        a_caps = [task["capability"] for task in a["tasks"]]
        b_caps = [task["capability"] for task in b["tasks"]]
        self.assertIn("gaps", a_caps)
        self.assertIn("consolidate", b_caps)
        self.assertNotEqual(a_caps, b_caps)


if __name__ == "__main__":
    unittest.main()
