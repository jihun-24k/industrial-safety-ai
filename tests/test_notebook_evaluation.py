import csv
import json
from unittest.mock import patch, MagicMock
import tempfile
import unittest
from pathlib import Path
from pipeline import notebook_evaluation as e


class HumanEvaluationTests(unittest.TestCase):
    def row(self,**kw):
        return {'review_complete':'true','reviewer':'test','reviewed_at':'2026-10-22',
                **{key:4 for key in e.WEIGHTS},'critical_fail':'false',**kw}

    def test_human_scores_only_and_critical_fail_separate(self):
        self.assertIsNone(e.weighted_score({}))
        self.assertEqual(e.weighted_score(self.row())['weighted_score'],100)
        result=e.weighted_score(self.row(accuracy=0,critical_fail='true'))
        self.assertEqual(result,dict(weighted_score=70,critical_fail=True))
        for changes in [dict(accuracy=''),dict(accuracy=5),dict(accuracy=float('nan')),dict(reviewer=''),dict(critical_fail='')]:
            with self.assertRaises(ValueError):e.weighted_score(self.row(**changes))

    def test_pending_feedback_persisted_without_overwrite_and_run_guard(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'feedback.csv'
            run={'run_id':'run1','items':[{'id':'Q1'}]}
            e.initialize_feedback(path,run,[{'id':'Q1'}])
            before=path.read_bytes()
            e.initialize_feedback(path,run,[{'id':'Q1'}])
            self.assertEqual(before,path.read_bytes())
            result=e.summarize_feedback(path,run)
            self.assertIsNone(result[0]['weighted_score'])
            with self.assertRaises(ValueError):e.summarize_feedback(path,{'run_id':'run2','items':[{'id':'Q1'}]})

    def test_id_existence_does_not_imply_meaning(self):
        case={'expected_status':'answered','evidence':[{'doc_id':'manual','pdf_page':20,'required_text':'안전한 손수레'}]}
        # Wrong content with a real citation still passes only the ID check.
        item={'retrieval':{'results':[{'chunk_id':'x','doc_id':'manual','pdf_page_start':20,'pdf_page_end':20,'text':'unrelated'}]},
              'answer':{'status':'answered','citation_ids':['x']}}
        checks=e.structural_checks(case,item)
        self.assertTrue(checks['citations_exist_in_context'])
        self.assertEqual(checks['candidate_recall_at_k'],0)
        item['answer']['citation_ids']=['invented']
        self.assertFalse(e.structural_checks(case,item)['citations_exist_in_context'])

    def test_reference_changes_create_new_review_version(self):
        original=[{'id':'Q1','reference_answer':'first'}]
        changed=[{'id':'Q1','reference_answer':'revised'}]
        self.assertNotEqual(e.review_version(original), e.review_version(changed))

    def test_generation_cache_and_no_reference_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            index=root/'indexes'/'one'
            index.mkdir(parents=True)
            e.write_json(root/'current.json',{'path':'indexes/one'})
            e.write_json(index/'manifest.json',{'build_id':'one'})
            cfg={'output_root':root,'embedding_model':'test-only'}
            case={'id':'Q1','difficulty':'Easy','question':'test question',
                  'reference_answer':'SECRET_GOLD_ANSWER','evidence':[], 'expected_status':'answered'}
            context={'results':[{'chunk_id':'real','filename':'test.pdf','doc_type':'manual',
                                'pdf_page_start':1,'pdf_page_end':1,'text':'Retrieved content'}]}
            response=MagicMock()
            response.content=json.dumps({'answer':'Test response [real]','status':'answered','citation_ids':['real']})
            response.usage_metadata=None
            with patch.object(e,'embeddings'),patch.object(e,'safety_retrieve',return_value={**context,'safety_workflow':{}}),patch('langchain_openai.ChatOpenAI') as llm:
                llm.return_value.invoke.return_value=response
                run=e.run_cases(cfg,[case],run_live=True)
                messages=llm.return_value.invoke.call_args.args[0]
                self.assertNotIn('SECRET_GOLD_ANSWER',' '.join(m.content for m in messages))
                self.assertEqual(len(run['items']),1)
                first_prompt=[m.content for m in messages]
                changed={**case,'reference_answer':'CHANGED_GOLD', 'required_points':['LEAK_REQUIREMENT'],
                         'forbidden_claims':['LEAK_FORBIDDEN'],'expected_status':'needs_review'}
                e.run_cases(cfg,[changed],run_live=True,use_cache=False)
                second_prompt=[m.content for m in llm.return_value.invoke.call_args.args[0]]
                self.assertEqual(first_prompt,second_prompt)
                self.assertNotIn('LEAK_REQUIREMENT',' '.join(second_prompt))
                self.assertNotIn('LEAK_FORBIDDEN',' '.join(second_prompt))
                cached=e.run_cases(cfg,[case],run_live=False)
                self.assertEqual(cached['items'][0]['answer'],run['items'][0]['answer'])
                self.assertEqual(llm.return_value.invoke.call_count,2)
                self.assertIsNone(e.run_cases(cfg,[case],model='changed-model',run_live=False))


if __name__=='__main__':unittest.main()
