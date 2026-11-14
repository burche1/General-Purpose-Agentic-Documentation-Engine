"""Stage 2 regression tests: local ingestion and source-located retrieval."""
from pathlib import Path
import tempfile
import unittest

from engine.context import parse_context
from engine.ingest import ingest_project
from engine.planner import plan_project
from engine.review import record_decision, save_draft
from engine.store import inventory, search
from main import main


class StageTwoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / 'demo'
        self.project.mkdir()
        self.inputs = self.project / 'inputs'
        self.references = self.project / 'references'
        self.inputs.mkdir()
        self.references.mkdir()
        (self.project / 'context.md').write_text(
            '# Generic Documentation\n\n## Objective\n'
            'Compare existing documentation against references and generate a report.\n',
            encoding='utf-8'
        )

    def approve(self):
        ctx = parse_context(self.project)
        save_draft(ctx, plan_project(ctx))
        record_decision(ctx, approved=True)

    def test_approval_required_before_ingest(self):
        (self.inputs / 'a.md').write_text('# Report\n\nRequirements review in DOORS.', encoding='utf-8')
        self.assertEqual(main(['--project', str(self.project), '--ingest']), 1)
        self.approve()
        self.assertEqual(main(['--project', str(self.project), '--ingest']), 0)
        self.assertEqual(len(inventory(self.project)), 1)
        # Once context changes, previous approval is invalid.
        with (self.project / 'context.md').open('a', encoding='utf-8') as stream:
            stream.write('\n## Constraints\nNo cloud.\n')
        self.assertEqual(main(['--project', str(self.project), '--ingest']), 1)

    def test_local_index_incremental_search_and_delete(self):
        (self.inputs / 'procedure.md').write_text('# Procedure\n\nDOORS requirements review\n\nArchitecture handoff', encoding='utf-8')
        (self.references / 'standard.txt').write_text('All requirement changes should be reviewed.\n', encoding='utf-8')
        report = ingest_project(self.project)
        self.assertEqual(len(report['indexed']), 2)
        self.assertEqual(report['errors'], [])
        hits = search(self.project, 'requirements review', role='inputs')
        self.assertGreater(len(hits), 0)
        self.assertTrue(any(h['relative_path'] == 'inputs/procedure.md' for h in hits))
        self.assertTrue(all(h['locator'].startswith('lines ') for h in hits))
        self.assertEqual(search(self.project, 'reviewed', role='references')[0]['relative_path'], 'references/standard.txt')
        self.assertEqual(len(ingest_project(self.project)['unchanged']), 2)
        (self.inputs / 'procedure.md').write_text('New architecture allocation rules', encoding='utf-8')
        ingest_project(self.project)
        self.assertEqual(search(self.project, 'DOORS', role='inputs'), [])
        self.assertEqual(len(search(self.project, 'allocation', role='inputs')), 1)
        (self.references / 'standard.txt').unlink()
        report = ingest_project(self.project)
        self.assertEqual(report['removed'], ['references/standard.txt'])
        self.assertEqual(search(self.project, 'requirement changes'), [])
        self.assertEqual(len(inventory(self.project)), 1)

    def test_csv_html_text_parsing_and_bounded_chunking(self):
        (self.inputs / 'matrix.csv').write_text('id,status\nSWE.1,reviewed\nSWE.2,pending\n', encoding='utf-8')
        (self.inputs / 'manual.html').write_text('<html><script>EVILIGNORE</script><h1>Architecture</h1><p>Safety engineering</p></html>', encoding='utf-8')
        (self.inputs / 'large.txt').write_text('transformation ' * 200, encoding='utf-8')
        report = ingest_project(self.project)
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(report['indexed']), 3)
        self.assertEqual(search(self.project, 'EVILIGNORE'), [])
        self.assertEqual(search(self.project, 'reviewed')[0]['locator'], 'row 2')
        self.assertTrue(any('HTML text block' in r['locator'] for r in search(self.project, 'Safety')))
        self.assertGreater(len(search(self.project, 'transformation', limit=50)), 1)

    def test_pdf_docx_pptx_text_extraction(self):
        import pymupdf
        from docx import Document
        from pptx import Presentation
        from pptx.util import Inches
        pdf_path = self.references / 'guideline.pdf'
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((72, 72), 'Architecture verification guideline')
        pdf.save(str(pdf_path))
        pdf.close()

        doc = Document()
        doc.add_heading('Engineering procedure', level=1)
        doc.add_paragraph('Requirements allocated to software')
        doc.save(self.inputs / 'procedure.docx')

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
        shape.text = 'Integration testing workflow'
        prs.save(self.inputs / 'presentation.pptx')

        report = ingest_project(self.project)
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(report['indexed']), 3)
        self.assertIn('page 1', search(self.project, 'verification')[0]['locator'])
        self.assertTrue(any(h['locator'].startswith('paragraph') for h in search(self.project, 'allocated')))
        self.assertTrue(any(h['locator'].startswith('slide ') for h in search(self.project, 'Integration')))

    def test_bad_file_is_reported_and_not_retained(self):
        file = self.inputs / 'data.pdf'
        file.write_bytes(b'not a PDF')
        report = ingest_project(self.project)
        self.assertEqual(len(report['errors']), 1)
        self.assertEqual(len(inventory(self.project)), 0)
        self.assertTrue((self.project / '.local' / 'ingestion_report.json').exists())
        self.assertTrue(report['errors'][0]['path'].endswith('data.pdf'))

    def test_symlink_is_not_followed(self):
        secret = Path(self.temp.name) / 'secret.txt'
        secret.write_text('my-private-password-in-secret-file', encoding='utf-8')
        (self.inputs / 'linked.txt').symlink_to(secret)
        ingest_project(self.project)
        self.assertEqual(inventory(self.project), [])
        self.assertEqual(search(self.project, 'my-private-password-in-secret-file'), [])

    def test_query_sanitization_and_role_checks(self):
        (self.inputs / 'notes.txt').write_text('This is a verification process', encoding='utf-8')
        ingest_project(self.project)
        # Operator-like syntax is treated as terms, never as SQL.
        self.assertEqual(search(self.project, '*'), [])
        self.assertTrue(search(self.project, '"verification" OR process'))
        with self.assertRaises(ValueError):
            search(self.project, 'verification', role='another')
        with self.assertRaises(ValueError):
            search(self.project, 'verification', limit=300)


# Stage 3: integrated workflow regression tests
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine.context import parse_context
from engine.ingest import ingest_project
from engine.planner import plan_project
from engine.review import record_decision, save_draft
from engine.ollama import LocalModelError, validate_model_output
from engine.ingest import run_stage3
from main import main as stage3_main


class StageThreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / 'work'
        self.project.mkdir()
        (self.project / 'inputs').mkdir()
        (self.project / 'references').mkdir()
        (self.project / 'context.md').write_text(
            '# Example\n\n## Project\nName: Engineering Documentation\n\n'
            '## Objective\nCompare current procedures against references and generate improved draft documentation.\n\n'
            '## Tasks\n1. Analyze source documents.\n2. Compare existing procedures against references.\n'
            '3. Identify potential gaps.\n4. Generate document drafts.\n\n'
            '## Outputs\n- Process proposal (Markdown)\n- Open questions\n', encoding='utf-8')
        (self.project / 'inputs' / 'procedure.md').write_text(
            '# Current procedure\n\nTeam records requirement reviews in DOORS.\n\n'
            'Software architecture receives reviewed requirements.\n', encoding='utf-8')
        (self.project / 'references' / 'guideline.md').write_text(
            '# Demonstration guideline\n\nRequirements review should have assigned responsible roles.\n',
            encoding='utf-8')

    def approve(self):
        ctx = parse_context(self.project)
        save_draft(ctx, plan_project(ctx))
        record_decision(ctx, approved=True)

    def test_stage3_requires_approved_plan_and_index(self):
        self.assertEqual(stage3_main(['--project', str(self.project), '--check']), 1)
        self.approve()
        self.assertEqual(stage3_main(['--project', str(self.project), '--check']), 1)
        ingest_project(self.project)
        self.assertEqual(stage3_main(['--project', str(self.project), '--check']), 0)

    def test_run_creates_cited_drafts_and_manifest_without_touching_sources(self):
        self.approve()
        ingest_project(self.project)
        original = (self.project / 'inputs' / 'procedure.md').read_bytes()
        first = run_stage3(self.project)
        base = Path(first['output_dir'])
        self.assertTrue((base / 'draft.md').exists())
        self.assertTrue((base / 'analysis.md').exists())
        self.assertTrue((base / 'comparison.md').exists())
        self.assertTrue((base / 'open_gap_questions.md').exists())
        self.assertTrue((base / 'document_outline.md').exists())
        self.assertFalse((base / 'consolidated_excerpts.md').exists())
        evidence = json.loads((base / 'evidence.json').read_text())
        self.assertGreater(len(evidence), 0)
        self.assertTrue(all(e['id'].startswith('E') and e['document_sha256'] for e in evidence))
        self.assertTrue(any(e['source_role'] == 'references' for e in evidence))
        self.assertTrue(json.loads((base / 'validation.json').read_text())['passed'])
        self.assertEqual(json.loads((base / 'manifest.json').read_text())['approval_status'], 'draft_only')
        self.assertEqual((self.project / 'inputs' / 'procedure.md').read_bytes(), original)
        second = run_stage3(self.project)
        self.assertNotEqual(first['output_dir'], second['output_dir'])
        self.assertTrue(base.exists())

    def test_dry_run_is_side_effect_free_for_output_folder(self):
        self.approve()
        ingest_project(self.project)
        self.assertFalse((self.project / 'outputs').exists())
        result = run_stage3(self.project, dry_run=True)
        self.assertFalse(result['writes_anything'])
        self.assertFalse((self.project / 'outputs').exists())

    def test_refuses_changed_source_until_reingestion(self):
        self.approve()
        ingest_project(self.project)
        (self.project / 'inputs' / 'procedure.md').write_text('Modified new content', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'modified since indexing'):
            run_stage3(self.project)
        ingest_project(self.project)
        self.assertEqual(run_stage3(self.project, dry_run=True)['document_count'], 2)

    def test_refuses_new_file_until_reingestion(self):
        self.approve()
        ingest_project(self.project)
        (self.project / 'inputs' / 'new.txt').write_text('New artifact', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'differs from indexed files'):
            run_stage3(self.project)

    def test_refuses_changed_context_until_new_approval(self):
        self.approve()
        ingest_project(self.project)
        (self.project / 'context.md').write_text('# Different\n\n## Objective\nSummarize documents.\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'not approved'):
            run_stage3(self.project)

    def test_conflicting_output_symlink_refused(self):
        self.approve()
        ingest_project(self.project)
        (self.project / 'outputs').symlink_to(self.project / 'inputs', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'ordinary directory'):
            run_stage3(self.project)

    def test_model_identifier_denied_without_network(self):
        self.approve()
        ingest_project(self.project)
        with patch('engine.ollama.build_opener') as opener:
            with self.assertRaisesRegex(LocalModelError, 'not allowlisted'):
                run_stage3(self.project, llm='ollama', model='some-cloud-model:cloud')
            opener.assert_not_called()

    def test_model_cannot_invent_citations(self):
        with self.assertRaisesRegex(LocalModelError, 'missing/unapproved'):
            validate_model_output({'findings': [{'kind': 'observation', 'text': 'A',
                                                 'evidence_ids': ['E9999']}],
                                   'draft_sections': []}, {'E0001'})


    def test_local_model_recovers_from_truncated_json(self):
        from engine.ollama import interpret_locally, LocalModelError
        from engine.store import Evidence
        evidence = [Evidence(id='E0001', source_role='inputs', relative_path='source.md',
                             locator='lines 1-3', kind='text', content='Software requirements reviewed.',
                             document_sha256='abc', relevance=5)]
        ctx = parse_context(self.project)
        valid = {'findings': [{'kind': 'observation', 'text': 'Requirements are reviewed.',
                              'evidence_ids': ['E0001']}], 'draft_sections': []}
        with patch('engine.ollama._request_ollama_json', side_effect=[
            LocalModelError('Ollama returned incomplete JSON'), valid
        ]) as request:
            findings, sections, meta = interpret_locally(ctx, evidence, 'qwen2.5:1.5b')
        self.assertEqual(request.call_count, 2)
        self.assertEqual(meta['attempts'], 2)
        self.assertEqual(findings[0]['evidence_ids'], ['E0001'])
        self.assertEqual(sections, [])

    def test_local_model_fails_closed_on_invalid_json_twice(self):
        from engine.ollama import interpret_locally, LocalModelError
        from engine.store import Evidence
        evidence = [Evidence(id='E0001', source_role='inputs', relative_path='source.md',
                             locator='lines 1-3', kind='text', content='Software requirements reviewed.',
                             document_sha256='abc', relevance=5)]
        ctx = parse_context(self.project)
        with patch('engine.ollama._request_ollama_json', side_effect=LocalModelError('Malformed JSON')):
            with self.assertRaisesRegex(LocalModelError, 'after 2 bounded attempts'):
                interpret_locally(ctx, evidence, 'qwen2.5:1.5b')

    def test_generic_architecture_project_uses_consolidation(self):
        (self.project / 'context.md').write_text(
            '# Context\n\n## Objective\nConsolidate overlapping architecture notes and generate an architecture draft.\n'
            '\n## Tasks\n- Merge duplicated sections.\n- Generate a unified specification.\n',
            encoding='utf-8')
        (self.project / 'inputs' / 'second.md').write_text('Bootloader initializes the kernel.\n', encoding='utf-8')
        self.approve()
        ingest_project(self.project)
        result = run_stage3(self.project)
        base = Path(result['output_dir'])
        self.assertTrue((base / 'consolidated_excerpts.md').is_file())
        self.assertFalse((base / 'open_gap_questions.md').exists())

    def test_unsupported_file_is_reported_not_silently_ignored(self):
        self.approve()
        (self.project / 'inputs' / 'drawing.dwg').write_bytes(b'unsupported-example')
        ingest_project(self.project)
        result = run_stage3(self.project, dry_run=True)
        self.assertFalse(result['evidence_selection']['coverage_complete'])
        self.assertIn('unsupported file type', result['evidence_selection']['unindexed_paths'][0])

    def test_partial_selection_is_reported_and_never_called_exhaustive(self):
        self.approve()
        long_text = '\n\n'.join('## Item %d\n\nRequirements review and traceability topic %d.' % (i, i)
                                 for i in range(40))
        (self.project / 'inputs' / 'procedure.md').write_text(long_text, encoding='utf-8')
        ingest_project(self.project)
        result = run_stage3(self.project, max_evidence=4)
        stats = result['evidence_selection']
        self.assertGreater(stats['omitted_chunks'], 0)
        self.assertFalse(stats['coverage_complete'])
        analysis = (Path(result['output_dir']) / 'analysis.md').read_text()
        self.assertIn('Coverage limitation', analysis)



if __name__ == '__main__':
    unittest.main()
