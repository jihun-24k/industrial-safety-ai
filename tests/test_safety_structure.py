import unittest
from datetime import datetime
from copy import deepcopy
from pipeline.safety_structure import classify_time,select_contacts,procedure_context,validate,load

def at(s):return datetime.fromisoformat(s+'+09:00')
SCOPE='lab_safety_manual_institution_unverified'
class SafetyStructureTests(unittest.TestCase):
    def test_weekday_boundaries(self):
        for stamp,expected in [('2026-10-19T08:59','nighttime'),('2026-10-19T09:00','daytime'),('2026-10-19T17:59','daytime'),('2026-10-19T18:00','nighttime'),('2026-10-24T14:00','nighttime'),('2026-10-21T11:00','daytime')]:
            with self.subTest(stamp=stamp):self.assertEqual(classify_time(at(stamp))['period'],expected)
    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError): classify_time(datetime(2026,10,19,11))
    def test_no_wrong_role_or_institution_fallback(self):
        result=select_contacts('연구실 안전관리',SCOPE,at('2026-10-19T19:00'))
        self.assertEqual(result['selected'],[])
        self.assertEqual(result['candidates'][0]['contact_id'],'lab_safety')
        self.assertEqual(select_contacts('연구실 안전관리','another_school',at('2026-10-19T11:00'))['candidates'],[])
    def test_all_times_is_not_response_or_dialability_guarantee(self):
        result=select_contacts('당직실 본부',SCOPE,at('2026-10-19T11:00'))
        c=result['selected'][0]
        self.assertFalse(c['call_enabled']);self.assertFalse(c['response_guaranteed'])
        self.assertEqual(c['phone_numbers_raw'],['760-2624','760-2119'])
    def test_graph_and_conditions(self):
        self.assertTrue(validate()['passed'])
        c=procedure_context('right.submit')
        self.assertTrue(all(n['lane_id']=='right' for n in c['nodes']))
        self.assertEqual(c['related_contact_candidates'][0]['status'],'unverified')
        nodes={n['node_id']:n for n in load('procedure.json')['nodes']}
        self.assertIsNone(nodes['left.conditions']['conditions'][0]['person_count'])
        self.assertEqual(nodes['left.conditions']['conditions'][1]['treatment_duration_months_min'],3)
        self.assertEqual(nodes['right.submit']['deadline_raw'],'3일 이내')
        self.assertIsNone(nodes['right.submit']['deadline_start'])
    def test_duplicate_number_roles_preserved(self):
        records=[c for c in load('contacts.json')['contacts'] if '760-2119' in c['phone_numbers_raw']]
        self.assertEqual(len(records),2)
        self.assertEqual({c['availability_raw'] for c in records},{'주간/야간','주간'})
