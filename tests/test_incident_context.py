from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from pipeline import pdf_pipeline as p
from pipeline.structured_ingestion import make_chunks
from pipeline.incident_context import assemble

class IncidentContextTests(unittest.TestCase):
    def test_exposure_unknown_and_no_wrong_material(self):
        cfg=p.config_at(p.ROOT/'pipeline/config.json')
        rows,snapshot=make_chunks(cfg)
        material={'chunk_id':'material54','text':'가성소다 원문','doc_id':'lab_safety_manual','pdf_page_start':54,'filename':'test.pdf'}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'index';folder.mkdir()
            p.write_json(folder/'structure_snapshot.json',snapshot)
            p.write_json(folder/'material_catalog.json',[{'aliases_from_source':['가성소다','1310-73-2'],'pdf_page':54}])
            p.write_lines(folder/'documents.jsonl',rows+[material])
            p.write_json(folder/'manifest.json',{'build_id':'test','files':{n:p.digest(folder/n) for n in ('structure_snapshot.json','material_catalog.json','documents.jsonl')}})
            p.publish_pointer(Path(temp),'current.json','index')
            facts={'substance':'가성소다','people_exposed':True,'fire_present':False,'institution_scope':'lab_safety_manual_institution_unverified'}
            local={**cfg,'output_root':Path(temp)}
            b=assemble(local,None,facts,datetime.fromisoformat('2026-10-23T11:00:00+09:00'))
            self.assertIn('people_exposed',b['attention_flags'])
            self.assertNotIn('화재시 대처요령',b['requested_sections'])
            self.assertEqual([r['lane_id'] for r in b['evidence'] if r.get('content_type')=='procedure_lane'],['center'])
            self.assertEqual(b['contacts'][0]['selected'][0]['contact_id'],'lab_safety')
            b=assemble(local,None,{**facts,'substance':'미상'},datetime.fromisoformat('2026-10-23T19:00:00+09:00'))
            self.assertFalse(any(r['chunk_id']=='material54' for r in b['evidence']))
            self.assertEqual(b['contacts'][0]['selected'],[])
            with self.assertRaises(ValueError):assemble(local,None,{**facts,'fire_present':'false'},datetime.now().astimezone())
