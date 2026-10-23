import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from pipeline import pdf_pipeline as p
from pipeline.vision_extraction import Box,NFPA,PageResult,enrich

class VisionTests(unittest.TestCase):
 def test_bbox_and_nfpa_validation(self):
  with self.assertRaises(ValidationError):Box(x0=.7,y0=.1,x1=.2,y1=.3)
  with self.assertRaises(ValidationError):NFPA(health=5,flammability=0,reactivity=0,special_raw='-')
  self.assertEqual(NFPA(health=None,flammability=0,reactivity=1,special_raw='-').special_raw,'-')
 def test_dictionary_mapping_does_not_follow_bad_source_code(self):
  result=PageResult.model_validate({'fields':{k:None for k in ['substance_name','physical_state','odor','color','formula','cas_number']},'nfpa':{'health':None,'flammability':None,'reactivity':None,'special_raw':None},'icons':[{'symbol':'corrosion','bbox':{'x0':.1,'y0':.1,'x1':.2,'y1':.2},'uncertain':False,'visual_description':'부식'}],'unreadable_regions':[],'warnings':[]})
  row=enrich(result)['icons'][0]
  self.assertEqual(row['canonical_code'],'GHS05');self.assertEqual(row['legend_source_label'],'GHS08')
 def test_reference_is_explicit_and_hash_checked(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.pdf';ref=root/'guide.pdf';source.write_bytes(b'%PDF-source');ref.write_bytes(b'%PDF-guide')
   cfg={'input_root':root,'documents':[{'filename':'source.pdf','doc_id':'x','sha256':p.digest(source)}],'recognition_references':[{'filename':'guide.pdf','sha256':p.digest(ref),'rag_ingest':False,'purpose':'recognition_reference_only'}]}
   p.audit(cfg)
   cfg['recognition_references'][0]['rag_ingest']=True
   with self.assertRaises(ValueError):p.audit(cfg)
   cfg['recognition_references'][0]['rag_ingest']=False;ref.write_bytes(b'%PDF-changed')
   with self.assertRaises(ValueError):p.audit(cfg)
 def test_pdf_reference_not_in_chunk_input(self):
  cfg=p.config_at(p.ROOT/'pipeline/config.json')
  self.assertEqual(len(cfg['documents']),2)
  self.assertEqual(len(cfg['recognition_references']),1)
  self.assertNotIn(cfg['recognition_references'][0]['filename'],[d['filename'] for d in cfg['documents']])
