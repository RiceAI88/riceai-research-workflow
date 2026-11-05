import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/riceai-research-workflow/scripts/paperflow.py'
spec = importlib.util.spec_from_file_location('paperflow', SCRIPT)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / 'vault'
        pf.init_vault(str(self.vault))

    def tearDown(self):
        self.tmp.cleanup()

    def test_reinitialization_preserves_human_notes_and_templates(self):
        template = self.vault / 'templates/paper-note.md'
        template.write_text('my custom template')
        note = self.vault / 'notes/my-note.md'
        note.write_text('human writing')
        pf.init_vault(str(self.vault))
        self.assertEqual(template.read_text(), 'my custom template')
        self.assertEqual(note.read_text(), 'human writing')

    def test_import_refresh_preserves_pdf_and_same_title_distinct_ids(self):
        records = [{'key': k, 'data': {'key': k, 'title': 'same title'}} for k in ['ABC12345', 'DEF12345']]
        pf.merge(self.vault, records)
        source = self.root / 'a.pdf'; source.write_bytes(b'%PDF-demo')
        pf.add_pdf(self.vault, str(source), 'z0-ABC12345')
        pf.merge(self.vault, records)
        lib = pf.read_library(self.vault)['papers']
        self.assertEqual(len(lib), 2)
        self.assertEqual(lib['z0-ABC12345']['sha256'], pf.digest(source))

    def test_conflicting_pdf_refuses_overwrite(self):
        a = self.root / 'a.pdf'; a.write_bytes(b'first')
        b = self.root / 'b.pdf'; b.write_bytes(b'second')
        pf.add_pdf(self.vault, str(a), 'paper-1')
        with self.assertRaises(ValueError): pf.add_pdf(self.vault, str(b), 'paper-1')
        self.assertEqual((self.vault / 'papers/paper-1.pdf').read_bytes(), b'first')

    def test_same_pdf_stable_id(self):
        a = self.root / 'a.pdf'; a.write_bytes(b'same')
        b = self.root / 'b.pdf'; b.write_bytes(b'same')
        self.assertEqual(pf.add_pdf(self.vault, str(a), None)['id'], pf.add_pdf(self.vault, str(b), None)['id'])
        self.assertEqual(len(pf.read_library(self.vault)['papers']), 1)

    def test_pagination_and_limit(self):
        source = list(range(205))
        def mock_api(route, start, limit): return source[start:start+limit]
        with patch.object(pf, 'api', side_effect=mock_api) as call:
            self.assertEqual(pf.fetch_pages('/items/top', 151), source[:151])
            self.assertEqual(call.call_count, 2)

    def test_search_reports_physical_page(self):
        text = self.vault / '.paperflow/text/demo.md'
        text.write_text('# Title\n\n## PDF page 1\nUnrelated\n\n## PDF page 2\nknowledge distillation result\n')
        lib = pf.read_library(self.vault)
        lib['papers']['demo'] = {'title': 'Demo', 'text': '.paperflow/text/demo.md'}
        pf.save_library(self.vault, lib)
        result = pf.search(self.vault, 'knowledge distillation', 3)
        self.assertEqual(result['hits'][0]['section'], '## PDF page 2')
        self.assertEqual(pf.search(self.vault, 'absent', 3)['hits'], [])

    def test_integrity_detects_modified_pdf_and_stale_note(self):
        a = self.root / 'a.pdf'; a.write_bytes(b'old')
        pf.add_pdf(self.vault, str(a), 'demo')
        (self.vault / 'notes/demo.md').write_text('old note with no provenance')
        (self.vault / 'papers/demo.pdf').write_bytes(b'new')
        result = pf.check(self.vault)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['errors']), 2)

    def test_attachment_must_belong_to_selected_paper(self):
        pf.merge(self.vault, [{'key': 'ABC12345', 'data': {'title': 'Paper'}}])
        with patch.object(pf, 'fetch_pages', return_value=[]):
            with self.assertRaises(ValueError): pf.import_attachment(self.vault, 'z0-ABC12345', 'NOTMINE1')

    def test_user_library_with_real_id_attachment_import(self):
        source = self.root / 'paper.pdf'; source.write_bytes(b'%PDF-test')
        pf.merge(self.vault, [{'key': 'ABC12345', 'library': {'id': 1234, 'type': 'user'}, 'data': {'title': 'Paper'}}])
        children = [{'key': 'PDFKEY12', 'data': {'contentType': 'application/pdf'}}]
        with patch.object(pf, 'fetch_pages', return_value=children), patch.object(pf, 'api', return_value=source.as_uri()):
            result = pf.import_attachment(self.vault, 'z1234-ABC12345', 'PDFKEY12')
        self.assertTrue(Path(result['pdf']).is_file())

    def test_plain_text_file_url_api_response(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'file:///tmp/paper.pdf'
        with patch.object(pf.OPENER, 'open', return_value=response):
            self.assertEqual(pf.api('/items/ABC/file/view/url'), 'file:///tmp/paper.pdf')

    def test_path_traversal_id_rejected(self):
        a = self.root / 'a.pdf'; a.write_bytes(b'pdf')
        with self.assertRaises(ValueError): pf.add_pdf(self.vault, str(a), '../outside')

    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'requires optional pypdf')
    def test_real_pdf_extraction_and_page_evidence(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        for message in ['First page evidence', 'Second page result']:
            page = writer.add_blank_page(width=300, height=300)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject(); stream.set_data(f'BT /F1 12 Tf 10 200 Td ({message}) Tj ET'.encode())
            page[NameObject('/Contents')] = writer._add_object(stream)
        source = self.root / 'real.pdf'
        with source.open('wb') as f: writer.write(f)
        pid = pf.add_pdf(self.vault, str(source), None)['id']
        result = pf.extract(self.vault, pid)
        self.assertEqual(result['pages'], 2)
        self.assertEqual(result['empty_pages'], [])
        hits = pf.search(self.vault, 'Second', 3)['hits']
        self.assertEqual(hits[0]['section'], '## PDF page 2')
        self.assertTrue(pf.check(self.vault)['ok'])


if __name__ == '__main__': unittest.main()
