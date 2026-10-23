import unittest
from pipeline import pdf_pipeline as p
from pipeline.document_links import compile_links,sections_for,query_topics

class DocumentLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg=p.config_at(p.ROOT/'pipeline/config.json')
        from pypdf import PdfReader
        cls.pages=[]
        for doc in cfg['documents']:
            reader=PdfReader(cfg['input_root']/doc['filename'])
            for number,page in enumerate(reader.pages,1):
                text,_=p.clean_page(page.extract_text() or '',set())
                cls.pages.append({'doc_id':doc['doc_id'],'filename':doc['filename'],
                                  'doc_type':doc['doc_type'],'source_sha256':doc['sha256'],
                                  'pdf_page':number,'cleaned_text':text})
        cls.links=compile_links(cls.pages)
    def test_every_excerpt_returns_to_source_span(self):
        pages={(r['doc_id'],r['pdf_page']):r['cleaned_text'] for r in self.pages}
        for r in self.links['sections']:
            span=r['source_spans'][0]
            self.assertEqual(r['text'],pages[(r['doc_id'],span['pdf_page'])][span['start']:span['end']])
    def test_skin_exposure_does_not_pull_gas_controls(self):
        rows=sections_for(self.links,['body_contamination'])
        self.assertIn('body_contamination',[r['section_id'] for r in rows])
        self.assertFalse(any('가스밸브' in r['text'] for r in rows))
        self.assertTrue(any('033-741-0114' in r['text'] for r in rows))
    def test_fire_restrictions_are_mandatory(self):
        rows=sections_for(self.links,['fire'])
        self.assertEqual({r['section_id'] for r in rows},{'fire_general','fire_limits'})
        self.assertTrue(any('소화전 사용금지' in r['text'] for r in rows))
    def test_gas_continuation_and_law_separation(self):
        rows=sections_for(self.links,['gas_leak'])
        self.assertEqual([r['pdf_page_start'] for r in rows],[29,30])
        self.assertFalse(any('베이거나' in r['text'] for r in rows))
        rows=sections_for(self.links,['waste'])
        self.assertEqual({r['doc_type'] for r in rows},{'law','manual'})
        self.assertIn('waste_law_scope',[r['section_id'] for r in rows])
    def test_unknown_topic_is_not_guessed(self):
        self.assertEqual(sections_for(self.links,['unknown']),[])
        self.assertIn('body_contamination',query_topics('가성소다가 눈에 들어간 경우'))
