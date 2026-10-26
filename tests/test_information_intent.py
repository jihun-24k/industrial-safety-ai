import unittest
from pipeline.safety_workflow import is_information_only, generation_requirements

class InformationIntentTests(unittest.TestCase):
    def test_comparison(self):
        q = '가성소다와 암모니아의 NFPA 값을 건강·화재·반응 위험성별로 비교해줘'
        self.assertTrue(is_information_only(q))
        self.assertIn('연락처를 덧붙이지 않는다', generation_requirements([], [{'name_raw':'암모니아'}], question=q))
    def test_incident_and_contacts_override(self):
        for q in ['염산을 쏟았어 위험성도 알려줘', '암모니아 누출됐어', '위험성 비교와 담당 연락처 알려줘']:
            self.assertFalse(is_information_only(q))
