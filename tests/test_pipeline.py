import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from langchain_core.embeddings import Embeddings
from pipeline import pdf_pipeline as p


class LocalEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float('가스' in text), float('폐기물' in text), 0.1]


class PipelineTests(unittest.TestCase):
    def test_negation_numbers_and_spans_survive(self):
        text, removed = p.clean_page('머리말\n제2조(정의)\n가스 10 kg을 혼합하지 않는다.\n\n1. 조건 확인\n머리말', {'머리말'})
        self.assertIn('10 kg을 혼합하지 않는다.', text)
        self.assertEqual(len(removed), 2)
        page = dict(cleaned_text=text, doc_id='a', filename='a.pdf', source_sha256='abc',
                    doc_type='law', effective_date=None, pdf_page=2, quality_flags=[])
        chunks = p.chunk_pages([page], dict(chunk_size=35, chunk_overlap=5))
        for chunk in chunks:
            span = chunk['source_spans'][0]
            self.assertEqual(text[span['start']:span['end']], chunk['text'])
            self.assertEqual(chunk['pdf_page_start'], 2)
        self.assertEqual(chunks, p.chunk_pages([page], dict(chunk_size=35, chunk_overlap=5)))

    def test_atomic_index_reload_failure_and_model_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared = root/'prepared'/'sample'
            prepared.mkdir(parents=True)
            rows = [{'chunk_id':'a', 'text':'가스 점검', 'doc_id':'manual', 'pdf_page_start':3},
                    {'chunk_id':'b', 'text':'폐기물 정의', 'doc_id':'law', 'pdf_page_start':2}]
            p.write_lines(prepared/'chunks.jsonl', rows)
            p.write_json(prepared/'report.json', {'documents':[{'status_counts':{'extracted':2}}]})
            pm = {'build_id':'sample', 'source_hashes':{'manual':'abc'}, 'splitter':{'chunk_size':1000,'chunk_overlap':100},
                  'library_versions':{}, 'files':{n:p.digest(prepared/n) for n in ['chunks.jsonl','report.json']}}
            p.write_json(prepared/'manifest.json', pm)
            p.publish_pointer(root, 'prepared.json', 'prepared/sample')
            cfg = dict(output_root=root, documents=[dict(doc_id='manual',sha256='abc')],
                       chunk_size=1000,chunk_overlap=100,embedding_dimension=3,embedding_model='test-only')
            with patch.object(p, 'audit'):
                p.build(cfg, LocalEmbeddings())
                result = p.search(cfg, LocalEmbeddings(), '가스', 1)
                self.assertEqual(result['results'][0]['doc_id'], 'manual')
                before = (root/'current.json').read_bytes()
                with patch.object(p, 'load_index', side_effect=ValueError('reload failure')):
                    with self.assertRaises(ValueError):
                        p.build(cfg, LocalEmbeddings())
                self.assertEqual(before, (root/'current.json').read_bytes())
                p.build(cfg, LocalEmbeddings())
                result = p.search(cfg, LocalEmbeddings(), '폐기물', 5)
                self.assertEqual(len(result['results']), 2)
                with self.assertRaises(ValueError):
                    p.search({**cfg,'embedding_model':'wrong'}, LocalEmbeddings(), '질문', 5)
                folder = p.resolve_pointer(root, 'current.json')
                (folder/'documents.jsonl').write_text('tampered')
                with self.assertRaises(ValueError):
                    p.search(cfg, LocalEmbeddings(), '질문', 5)

    def test_source_drift_and_extra_input_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pdf=root/'one.pdf'
            pdf.write_bytes(b'%PDF-fixture')
            cfg=dict(input_root=root, documents=[dict(filename='one.pdf',doc_id='one',sha256=p.digest(pdf))])
            p.audit(cfg)
            (root/'extra.pdf').write_bytes(b'%PDF-other')
            with self.assertRaises(ValueError): p.audit(cfg)
            (root/'extra.pdf').unlink()
            pdf.write_bytes(b'%PDF-changed')
            with self.assertRaises(ValueError): p.audit(cfg)

    def test_pointer_escape_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p.write_json(root/'current.json', {'path':'../outside'})
            with self.assertRaises(ValueError): p.resolve_pointer(root,'current.json')


if __name__ == '__main__':
    unittest.main()
