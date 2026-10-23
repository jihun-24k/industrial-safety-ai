import unittest
from copy import deepcopy
from pipeline import pdf_pipeline as p
from pipeline.structured_ingestion import make_chunks,material_catalog,match_materials

class StructuredIngestionTests(unittest.TestCase):
    def test_source_and_snapshot_guard(self):
        cfg=p.config_at(p.ROOT/'pipeline/config.json')
        rows,snapshot=make_chunks(cfg)
        self.assertEqual(len(rows),11)
        self.assertEqual(len([r for r in rows if r['content_type']=='procedure_lane']),3)
        self.assertTrue(all(r['source_spans']==[] for r in rows))
        self.assertEqual([len(r['nodes']) for r in rows[:3]],[6,7,6])
        with self.assertRaises(ValueError):make_chunks({**cfg,'structured_safety_sha256':'bad'})
        bad=deepcopy(cfg);bad['documents'][0]['sha256']='changed'
        with self.assertRaises(ValueError):make_chunks(bad)
    def test_exact_material_match_and_unknown(self):
        rows=[{'doc_id':'lab_safety_manual','pdf_page':n,'source_sha256':'test','cleaned_text':f'{name}({eng})\n물질 기본 특성\nCAS번호 {cas}'} for n,name,eng,cas in [(54,'가성소다','Sodium hydroxide','1310-73-2'),(55,'암모니아','Ammonia','7664-41-7'),(57,'질산','Nitric acid','7697-37-2'),(72,'질산암모늄','Ammonium nitrate','6484-52-2')]]
        cat=material_catalog(rows)
        self.assertEqual(match_materials('가성소다를 쏟았어요',cat)[0]['pdf_page'],54)
        self.assertEqual([x['pdf_page'] for x in match_materials('질산암모늄을 쏟았어요',cat)],[72])
        self.assertEqual(len(match_materials('가성소다와 암모니아',cat)),2)
        self.assertEqual(match_materials('모르는 액체',cat),[])
        self.assertEqual(match_materials('1310-73-2',cat)[0]['pdf_page'],54)
