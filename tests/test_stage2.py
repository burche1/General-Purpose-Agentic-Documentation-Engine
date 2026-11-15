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

# Stage 4 tests: integrated QA/release + remote API approval (no network calls).
from engine.review import (review_generated_draft, decide_generated_draft,
                           publish_generated_draft)
from engine.ollama import (preview_remote, approve_remote, interpret_remotely,
                           RemoteApprovalError)
from engine.store import Evidence


class StageFourTests(unittest.TestCase):
    setUp = StageThreeTests.setUp
    approve = StageThreeTests.approve
    def _run(self):
        self.approve()
        ingest_project(self.project)
        return run_stage3(self.project)

    def test_requested_run_folder_format_and_release(self):
        item = self._run()
        self.assertRegex(item['run_id'], r'^draft-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}-\d{2}(?:-\d{2})?$')
        report = review_generated_draft(self.project, item['run_id'])
        self.assertEqual(report['blockers'], [])
        self.assertTrue(report['source_coverage_complete'])
        decision = decide_generated_draft(self.project, item['run_id'], approved=True,
                                          comment='Manually checked citations and generated sections.')
        self.assertEqual(decision['decision'], 'approved')
        released = publish_generated_draft(self.project, item['run_id'])
        self.assertEqual(released['status'], 'published_locally')
        self.assertTrue((Path(released['release_dir']) / 'draft.md').exists())
        self.assertTrue((Path(released['release_dir']) / 'release.json').exists())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            publish_generated_draft(self.project, item['run_id'])

    def test_partial_selection_requires_acknowledgement(self):
        for i in range(10):
            (self.inputs if hasattr(self, 'inputs') else self.project / 'inputs').joinpath(f'section{i}.md').write_text(
                '# Heading\n\nThis process has multiple meaningful requirements and verification activities.\n', encoding='utf-8')
        self.approve()
        ingest_project(self.project)
        item = run_stage3(self.project, max_evidence=4)
        report = review_generated_draft(self.project, item['run_id'])
        self.assertFalse(report['source_coverage_complete'])
        with self.assertRaisesRegex(ValueError, 'Partial source coverage'):
            decide_generated_draft(self.project, item['run_id'], approved=True,
                                   comment='Checked sources')
        decision = decide_generated_draft(self.project, item['run_id'], approved=True,
                                          allow_partial=True,
                                          comment='I accept that this is only an exploratory partial sample.')
        self.assertEqual(decision['scope'], 'partial_exploratory')
        self.assertEqual(publish_generated_draft(self.project, item['run_id'])['scope'], 'partial_exploratory')

    def test_tampered_draft_rejected(self):
        item = self._run()
        draft = Path(item['output_dir']) / 'draft.md'
        draft.write_text(draft.read_text() + '\nUnauthorized change\n', encoding='utf-8')
        report = review_generated_draft(self.project, item['run_id'])
        self.assertTrue(any('modified' in b.lower() for b in report['blockers']))
        with self.assertRaisesRegex(ValueError, 'blocking QA'):
            decide_generated_draft(self.project, item['run_id'], approved=True, comment='Reviewed')

    def test_changed_source_after_approval_blocks_release(self):
        item = self._run()
        decide_generated_draft(self.project, item['run_id'], approved=True, comment='Reviewed content.')
        (self.project / 'inputs' / 'procedure.md').write_text('Changed source', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale or QA blockers'):
            publish_generated_draft(self.project, item['run_id'])

    def test_rejection_blocks_release(self):
        item = self._run()
        result = decide_generated_draft(self.project, item['run_id'], approved=False, comment='Needs revision.')
        self.assertEqual(result['decision'], 'rejected')
        with self.assertRaisesRegex(ValueError, 'rejected'):
            publish_generated_draft(self.project, item['run_id'])

    def test_external_preview_explicit_approval_and_exact_payload(self):
        self.approve()
        ingest_project(self.project)
        with patch('engine.ollama.build_opener') as network:
            preview = run_stage3(self.project, llm='openai', model='gpt-mini', preview_api=True)
            self.assertTrue(preview['no_api_call'])
            self.assertIn('gpt-5.4-mini', preview['model'])
            network.assert_not_called()
            # Explicit approval must be bound to that exact payload and model.
            with self.assertRaisesRegex(RemoteApprovalError, 'does not match'):
                run_stage3(self.project, llm='openai', model='gpt-pro', approve_api=preview['request_sha256'])
            approval = run_stage3(self.project, llm='openai', model='gpt-mini',
                                  approve_api=preview['request_sha256'])
            self.assertTrue(approval['no_api_call'])
            network.assert_not_called()

    def test_no_remote_api_without_preview_and_grant(self):
        self.approve()
        ingest_project(self.project)
        with patch('engine.ollama.build_opener') as network:
            with self.assertRaisesRegex(RemoteApprovalError, 'previewed'):
                run_stage3(self.project, llm='openai', model='gpt-mini')
            network.assert_not_called()

    def test_remote_payload_changes_after_input_index_update(self):
        self.approve()
        ingest_project(self.project)
        preview = run_stage3(self.project, llm='openai', model='gpt-mini', preview_api=True)
        (self.project / 'inputs' / 'procedure.md').write_text('# Changed\n\nNew engineering information.', encoding='utf-8')
        ingest_project(self.project)
        with self.assertRaisesRegex(RemoteApprovalError, 'does not match'):
            run_stage3(self.project, llm='openai', model='gpt-mini', approve_api=preview['request_sha256'])

    def test_one_time_remote_permission_with_mocked_openai_response(self):
        import io
        import os
        self.approve()
        ingest_project(self.project)
        requested = run_stage3(self.project, llm='openai', model='gpt-mini', preview_api=True)
        run_stage3(self.project, llm='openai', model='gpt-mini', approve_api=requested['request_sha256'])
        response = {
            'status': 'completed',
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({
                'findings': [{'kind': 'observation', 'text': 'Requirements are described.', 'evidence_ids': ['E0001']}],
                'draft_sections': []
            })}]}],
            'usage': {'input_tokens': 100, 'output_tokens': 40},
        }
        fake_response = io.BytesIO(json.dumps(response).encode('utf-8'))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-never-reveal'}), \
             patch('engine.ollama.build_opener') as mocked:
            mocked.return_value.open.return_value = fake_response
            generated = run_stage3(self.project, llm='openai', model='gpt-mini')
            self.assertEqual(generated['llm'], 'openai')
            called_request = mocked.return_value.open.call_args.args[0]
            self.assertEqual(called_request.full_url, 'https://api.openai.com/v1/responses')
            self.assertEqual(json.loads(called_request.data.decode('utf-8'))['store'], False)
            mocked.reset_mock()
            with self.assertRaisesRegex(RemoteApprovalError, 'overwrite'):
                run_stage3(self.project, llm='openai', model='gpt-mini')
            mocked.assert_not_called()


class StageFiveTests(unittest.TestCase):
    """Stage 5 regression: exhaustive batching, privacy and resumability."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / 'project'
        self.project.mkdir()
        (self.project / 'inputs').mkdir()
        (self.project / 'references').mkdir()
        (self.project / 'context.md').write_text(
            '# Engineering Documentation\n\n## Objective\nCompare against reference requirements '
            'and generate improved documentation.\n\n## Tasks\n- Analyze all supplied materials\n'
            '- Compare existing with references\n- Generate updated process descriptions\n',
            encoding='utf-8',
        )
        ctx = parse_context(self.project)
        save_draft(ctx, plan_project(ctx))
        record_decision(ctx, approved=True)

    def sources(self):
        (self.project / 'references' / 'standard.md').write_text(
            '# Normative reference\n\n' + ('REQUIREMENT traceability verification.\n' * 75),
            encoding='utf-8',
        )
        (self.project / 'inputs' / 'current.md').write_text(
            '# Current procedures\n\n' + ('Current requirements review via DOORS.\n' * 60),
            encoding='utf-8',
        )
        ingest_project(self.project)

    def test_all_chunks_preserved_and_references_first(self):
        from engine.store import full_evidence_batches, connect
        self.sources()
        ctx = parse_context(self.project)
        batches, stats = full_evidence_batches(ctx, batch_chars=1100)
        self.assertGreater(len(batches), 2)
        self.assertEqual(batches[0][0].source_role, 'references')
        first_input = next(i for i, batch in enumerate(batches) if batch[0].source_role == 'inputs')
        self.assertTrue(all(b[0].source_role == 'references' for b in batches[:first_input]))
        with connect(self.project) as con:
            original = con.execute('''SELECT d.relative_path, c.ordinal, c.content
                                     FROM chunks c JOIN documents d ON d.id=c.document_id
                                     ORDER BY d.relative_path,c.ordinal''').fetchall()
        by_chunk = {}
        for batch in batches:
            self.assertLessEqual(sum(len(__import__('engine.store', fromlist=['evidence_display']).evidence_display(e)) for e in batch), 1100)
            for e in batch:
                key = (e.relative_path, int(e.locator.split('[chunk ')[1].split(',')[0]))
                by_chunk.setdefault(key, []).append(e.content)
        for row in original:
            self.assertEqual(''.join(by_chunk[(row['relative_path'], row['ordinal'])]), row['content'])
        self.assertEqual(stats['indexed_chunks'], len(original))
        self.assertTrue(stats['all_indexed_text_prepared'])

    def test_full_plan_is_read_only_and_requires_approved_sources(self):
        from engine.ingest import full_plan
        self.sources()
        result = full_plan(self.project, batch_chars=1400)
        self.assertEqual(result['reference_documents'], 1)
        self.assertGreater(result['batches_required'], 1)
        self.assertFalse((self.project / 'outputs').exists())
        self.assertTrue(result['no_llm_call'])

    def test_full_deterministic_resume_and_review(self):
        from engine.ingest import run_full, full_status
        from engine.review import review_generated_draft
        self.sources()
        first = run_full(self.project, llm='none', model='none', batch_chars=1400, batch_limit=1)
        self.assertEqual(first['status'], 'in_progress')
        draft_id = first['run_id']
        progress = full_status(self.project, draft_id)
        self.assertEqual(progress['saved_batch_records'], 1)
        final = run_full(self.project, llm='none', model='none', batch_chars=1400,
                         batch_limit=999, resume_draft=draft_id)
        self.assertEqual(final['status'], 'draft_for_review')
        folder = Path(final['output_dir'])
        self.assertTrue((folder / 'manifest.json').exists())
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['evidence_selection']['omitted_chunks'], 0)
        self.assertFalse(manifest['evidence_selection']['model_input_coverage_complete'])
        self.assertEqual(manifest['evidence_selection']['processed_source_characters'],
                         manifest['evidence_selection']['indexed_source_characters'])
        review = review_generated_draft(self.project, draft_id)
        self.assertTrue(review['document_checks_passed'])
        self.assertTrue(review['source_coverage_complete'])
        self.assertFalse(review['model_input_coverage_complete'])

    def test_local_model_must_receive_all_segments_and_can_resume(self):
        from engine.ingest import run_full
        self.sources()
        def fake_model(ctx, evidence, model):
            ids = [e.id for e in evidence]
            return ([{'kind': 'observation', 'text': 'Source evidence was examined.',
                      'evidence_ids': [ids[0]]}], [],
                    {'provider': 'local_ollama', 'model': model,
                     'evidence_ids_supplied': ids})
        with patch('engine.ingest.interpret_locally', side_effect=fake_model):
            first = run_full(self.project, llm='ollama', model='qwen2.5:1.5b',
                             batch_chars=1500, batch_limit=2)
            finished = run_full(self.project, llm='ollama', model='qwen2.5:1.5b',
                                batch_chars=1500, batch_limit=999,
                                resume_draft=first['run_id'])
        self.assertEqual(finished['status'], 'draft_for_review')
        manifest = json.loads((Path(finished['output_dir']) / 'manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest['evidence_selection']['model_input_coverage_complete'])
        self.assertEqual(manifest['evidence_selection']['reference_batches'],
                         sum(1 for row in json.loads((Path(finished['output_dir'])/'source_coverage.json').read_text())['batch_deliveries']
                             if row['role'] == 'references'))

    def test_local_model_partial_response_does_not_claim_coverage(self):
        from engine.ingest import run_full, Stage3Error
        self.sources()
        with patch('engine.ingest.interpret_locally', return_value=([], [],
             {'provider': 'local_ollama', 'evidence_ids_supplied': []})):
            with self.assertRaisesRegex(Stage3Error, 'lost evidence'):
                run_full(self.project, llm='ollama', model='qwen2.5:1.5b',
                         batch_chars=1500, batch_limit=1)
        folder = next((self.project / 'outputs' / 'stage3').iterdir())
        self.assertEqual(list((folder/'.batches').glob('batch-*.json')), [])
        self.assertFalse((folder/'manifest.json').exists())

    def test_changed_source_disallows_resume(self):
        from engine.ingest import run_full
        self.sources()
        first = run_full(self.project, llm='none', model='none', batch_chars=1300, batch_limit=0)
        (self.project / 'inputs' / 'current.md').write_text('Now changed!', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'modified since indexing'):
            run_full(self.project, llm='none', model='none', batch_chars=1300,
                     batch_limit=1, resume_draft=first['run_id'])

    def test_full_remote_preview_no_network_and_exact_window(self):
        from engine.ingest import run_full, full_api_preview, full_api_approve
        self.sources()
        first = run_full(self.project, llm='openai', model='gpt-mini', batch_chars=1300, batch_limit=0)
        with patch('engine.ollama.build_opener', side_effect=AssertionError('network should not run')):
            preview = full_api_preview(self.project, draft_id=first['run_id'], model='gpt-mini',
                                       batch_chars=1300, max_batches=2)
            self.assertEqual(preview['requests'], 2)
            self.assertTrue(Path(preview['review_manifest']).is_file())
            approved = full_api_approve(self.project, draft_id=first['run_id'], model='gpt-mini',
                                        digest=preview['window_sha256'],
                                        batch_chars=1300, max_batches=2)
        self.assertEqual(approved['requests_authorized_once'], 2)
        for request_path in preview['request_previews']:
            request = json.loads(Path(request_path).read_text(encoding='utf-8'))['request']
            self.assertFalse(request['store'])
            self.assertIn('SOURCE EVIDENCE', request['input'])

    def test_unsupported_source_flagged_even_if_all_indexed_text_done(self):
        from engine.ingest import run_full
        self.sources()
        (self.project / 'references' / 'image.unknownformat').write_bytes(b'x')
        finished = run_full(self.project, llm='none', model='none', batch_chars=1200, batch_limit=999)
        manifest = json.loads((Path(finished['output_dir'])/'manifest.json').read_text())
        self.assertFalse(manifest['evidence_selection']['coverage_complete'])
        self.assertTrue(manifest['evidence_selection']['unindexed_paths'])

    def test_full_remote_requests_are_single_use_and_resumable(self):
        from engine.ingest import run_full, full_api_preview, full_api_approve
        import io
        import os
        self.sources()
        first = run_full(self.project, llm='openai', model='gpt-mini', batch_chars=1300, batch_limit=0)
        preview = full_api_preview(self.project, draft_id=first['run_id'], model='gpt-mini',
                                   batch_chars=1300, max_batches=2)
        full_api_approve(self.project, draft_id=first['run_id'], model='gpt-mini',
                         digest=preview['window_sha256'], batch_chars=1300, max_batches=2)
        response = {'status': 'completed', 'output': [{'type': 'message',
                    'content': [{'type': 'output_text', 'text': json.dumps({
                        'findings': [], 'draft_sections': []})}]}],
                    'usage': {'input_tokens': 190, 'output_tokens': 20}}
        requests = []
        class FakeOpener:
            def open(self, request, timeout=None):
                requests.append(request)
                return io.BytesIO(json.dumps(response).encode('utf-8'))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch('engine.ollama.build_opener', return_value=FakeOpener()):
            result = run_full(self.project, llm='openai', model='gpt-mini',
                              batch_chars=1300, batch_limit=2,
                              resume_draft=first['run_id'])
        self.assertEqual(result['completed_batches'], 2)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.full_url == 'https://api.openai.com/v1/responses' for request in requests))
        self.assertTrue(all(json.loads(request.data)['store'] is False for request in requests))
        # Attempt #3 was never approved and must fail before making another network call.
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch('engine.ollama.build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'paused at batch 3'):
                run_full(self.project, llm='openai', model='gpt-mini',
                         batch_chars=1300, batch_limit=1,
                         resume_draft=first['run_id'])
            network.assert_not_called()

    def test_full_run_cli_integration(self):
        self.sources()
        self.assertEqual(main(['--project', str(self.project), '--full-plan',
                               '--llm', 'none', '--batch-chars', '1200']), 0)
        self.assertEqual(main(['--project', str(self.project), '--run-full',
                               '--llm', 'none', '--model', 'none', '--batch-chars', '1200',
                               '--batch-limit', '100000']), 0)
        folders = list((self.project / 'outputs' / 'stage3').iterdir())
        self.assertEqual(len(folders), 1)
        self.assertRegex(folders[0].name, r'^draft-\d\d-\d\d-\d{4}-\d\d-\d\d-\d\d')
        self.assertEqual(main(['--project', str(self.project), '--review-draft',
                               '--draft-id', folders[0].name]), 0)

    def test_large_remote_window_contains_every_source_segment(self):
        from engine.ingest import run_full, full_api_preview, full_api_approve
        from engine.store import full_evidence_batches
        self.sources()
        first = run_full(self.project, llm='openai', model='gpt-mini',
                         batch_chars=12000, batch_limit=0)
        ctx = parse_context(self.project)
        batches, stats = full_evidence_batches(ctx, batch_chars=12000)
        preview = full_api_preview(self.project, draft_id=first['run_id'],
                                   model='gpt-mini', batch_chars=12000, max_batches=1)
        request = json.loads(Path(preview['request_previews'][0]).read_text())['request']
        for segment in batches[0]:
            self.assertIn(segment.id, request['input'])
            self.assertIn(segment.content, request['input'])
        self.assertEqual(request['max_output_tokens'], 6000)
        approval = full_api_approve(self.project, draft_id=first['run_id'],
                                    model='gpt-mini', digest=preview['window_sha256'],
                                    batch_chars=12000, max_batches=1)
        self.assertEqual(approval['requests_authorized_once'], 1)
