import unittest
from pipeline.langsmith_evaluation import build_report,make_payload,feedback_scores


class SavedEvaluationTests(unittest.TestCase):
    def fixture(self):
        case={'id':'Q1','question':'q','difficulty':'Outside','review_status':'pending',
              'reference_answer':'draft','required_points':[],'forbidden_claims':[],'evidence':[],
              'expected_status':'insufficient_evidence','reference_author':'AI_draft'}
        item={'id':'Q1','question':'q','latency_seconds':2,'retrieval':{'results':[]},
              'answer':{'answer':'unknown','status':'insufficient_evidence','citation_ids':[]}}
        run={'run_id':'test','created_at':'2026-10-22T08:00:00+00:00','answer_model':'test','items':[item]}
        return run,[case]

    def test_missing_ground_truth_and_human_scores_not_fabricated(self):
        run,cases=self.fixture();report=build_report(run,cases)
        self.assertIsNone(report['summary']['candidate_recall_at_k']['value'])
        self.assertIsNone(report['summary']['citations_exist_in_context']['value'])
        self.assertEqual(report['summary']['human_reviewed_count'],0)
        payload=make_payload(run,cases,report)
        row=payload['results'][0]
        self.assertEqual(row['actual_outputs']['answer'],'unknown')
        self.assertEqual(row['expected_outputs']['review_status'],'pending')
        self.assertNotIn('human_weighted_score',[s['key'] for s in row['evaluation_scores']])
        self.assertEqual(row['start_time'],'2026-10-22T08:00:00+00:00')
        self.assertEqual(row['end_time'],'2026-10-22T08:00:02+00:00')

    def test_question_change_is_not_silently_evaluated(self):
        run,cases=self.fixture();cases[0]['question']='different'
        with self.assertRaises(ValueError):build_report(run,cases)


if __name__=='__main__':unittest.main()
