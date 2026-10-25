import unittest, asyncio, tempfile
from pathlib import Path
from pipeline import pdf_pipeline as pp
from pipeline import tuning_experiments as t

class TuningTests(unittest.TestCase):
 def test_ocr_flags_are_candidates(self):
  row=t.page_audit([{'doc_id':'x','pdf_page':1,'raw_text':'','quality_flags':['low_text','image_content_requires_review']}])[0]
  self.assertIn('후보',row['action'])
 def test_budget_guard_before_mutation(self):
  with self.assertRaises(ValueError):
   asyncio.run(t.run_trials({},[],[],[v['name'] for v in t.VARIANTS],live=False,max_trials=1))
 def test_isolation_and_manifest_counts(self):
  cfg=pp.config_at(pp.ROOT/'pipeline/config.json')
  pages=[{'doc_id':'fixture','filename':'fixture.pdf','source_sha256':'test',
          'doc_type':'manual','effective_date':None,'pdf_page':1,'quality_flags':[],
          'raw_text':'문서 내용.','cleaned_text':'문서 내용.'}]
  with tempfile.TemporaryDirectory() as folder:
   out=Path(folder);prepared=out/'base';prepared.mkdir()
   pp.write_json(prepared/'manifest.json',{'build_id':'fixture','splitter':{},'files':{}})
   pp.write_json(prepared/'report.json',{'documents':[{'doc_id':'fixture'}]})
   pp.write_json(out/'prepared.json',{'path':'base'})
   pp.write_json(out/'current.json',{'path':'base'})
   original=(out/'current.json').read_bytes()
   trial=t.isolated_config({**cfg,'output_root':out},pages,t.VARIANTS[2])
   self.assertTrue(trial['output_root'].is_relative_to(out/'tuning'))
   target=pp.resolve_pointer(trial['output_root'],'prepared.json')
   manifest=pp.read_json(target/'manifest.json')
   self.assertEqual(manifest['chunk_count'],len(pp.read_lines(target/'chunks.jsonl')))
   pp.verify_files(target,manifest)
   self.assertEqual(original,(out/'current.json').read_bytes())
