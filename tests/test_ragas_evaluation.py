import copy
import unittest
from pipeline.ragas_evaluation import samples, report_path

class RagasInputTests(unittest.TestCase):
    def setUp(self):
        self.cases=[{'id':'Q1','question':'질문','reference_answer':'평가 전용 초안'}]
        self.run={'run_id':'fixture','items':[{'id':'Q1','question':'질문','answer':{'answer':'실제 답변'},'retrieval':{'results':[{'chunk_id':'c1','filename':'원문.pdf','pdf_page_start':2,'doc_type':'manual','text':'실제 PDF 구간'}]}}]}
    def test_inputs_preserve_answer_and_exclude_reference(self):
        original=copy.deepcopy(self.run)
        case,sample=next(samples(self.run,self.cases))
        self.assertEqual(sample['response'],'실제 답변')
        self.assertIn('실제 PDF 구간',sample['retrieved_contexts'][0])
        self.assertNotIn('reference',sample)
        self.assertEqual(original,self.run)
    def test_changed_answer_or_reference_invalidates_cache(self):
        first=report_path(self.run,self.cases)
        self.run['items'][0]['answer']['answer']='새 답변'
        self.assertNotEqual(first,report_path(self.run,self.cases))
        second=report_path(self.run,self.cases)
        self.cases[0]['reference_answer']='검토 후 기준'
        self.assertNotEqual(second,report_path(self.run,self.cases))
    def test_mismatched_question_rejected(self):
        self.cases[0]['question']='다른 질문'
        with self.assertRaises(ValueError):list(samples(self.run,self.cases))
