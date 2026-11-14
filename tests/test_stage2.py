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


if __name__ == '__main__':
    unittest.main()
