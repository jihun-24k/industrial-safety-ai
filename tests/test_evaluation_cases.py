"""Validate evaluation coverage and source anchors without calling a model."""
import json
from pathlib import Path
import unittest

from pipeline import pdf_pipeline as p
from pipeline.notebook_evaluation import normalize, structural_checks


class EvaluationCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = p.read_json(p.ROOT / 'evaluation/notebook_cases.json')
        cls.cases = cls.dataset['cases']
        cls.cfg = p.config_at(p.ROOT / 'pipeline/config.json')
        from pypdf import PdfReader
        cls.pages = {}
        wanted = {(e['doc_id'], e['pdf_page']) for c in cls.cases for e in c['evidence']}
        for doc in cls.cfg['documents']:
            reader = PdfReader(cls.cfg['input_root'] / doc['filename'])
            for doc_id, page in wanted:
                if doc_id == doc['doc_id']:
                    cls.pages[(doc_id,page)] = normalize(reader.pages[page-1].extract_text() or '')

    def test_source_anchors_exist_and_references_have_provenance(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                self.assertTrue(case['reference_answer'])
                if case['difficulty'] != 'Outside':
                    self.assertTrue(case['evidence'])
                for e in case['evidence']:
                    self.assertIn(normalize(e['required_text']), self.pages[(e['doc_id'],e['pdf_page'])])

    def test_one_outside_and_distinct_hazard_coverage(self):
        self.assertEqual(len({c['id'] for c in self.cases}),len(self.cases))
        self.assertEqual(sum(c['difficulty']=='Outside' for c in self.cases),1)
        tags={tag for c in self.cases for tag in c.get('risk_tags',[])}
        self.assertTrue({'acid','alkali','eyes','skin','inhalation','flammable','water_reactive',
                         'oxidizer','mixture','reporting','nighttime','missing_facts'}.issubset(tags))
        self.assertTrue(any(c['question']=='염산을 쏟았는데 어떡해야 해?' for c in self.cases))
        old=p.read_json(p.ROOT/'evaluation/notebook_cases_v1.json')['cases']
        self.assertEqual(len(old),7)
        self.assertEqual({c['id'] for c in old if c['difficulty']=='Outside'},{'Q05a','Q05b','Q05c'})

    def test_transport_reference_includes_second_source_page(self):
        case=next(c for c in self.cases if c['id']=='Q01')
        self.assertEqual({e['pdf_page'] for e in case['evidence']},{20,43})
        self.assertIn('조정기',case['reference_answer'])

    def test_combined_recall_distinguishes_graph_from_vector_and_accepts_clarification(self):
        case={'expected_status':'needs_clarification','accepted_statuses':['answered','needs_clarification'],
              'evidence':[{'doc_id':'manual','pdf_page':29,'required_text':'상황전파'}]}
        row={'chunk_id':'graph-source','doc_id':'manual','pdf_page_start':29,'pdf_page_end':29,'text':'상황전파'}
        item={'retrieval':{'results':[],'graph_results':[row]},
              'answer':{'status':'answered','citation_ids':['graph-source']}}
        checks=structural_checks(case,item)
        self.assertEqual(checks['candidate_recall_at_k'],0)
        self.assertEqual(checks['combined_candidate_recall'],1)
        self.assertEqual(checks['graph_candidate_recall'],1)
        self.assertTrue(checks['status_matches_draft'])


if __name__=='__main__':
    unittest.main()
