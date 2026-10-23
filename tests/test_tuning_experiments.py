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
  base=pp.resolve_pointer(cfg['output_root'],'prepared.json')
  pages=pp.read_lines(base/'pages.jsonl')
  original=(cfg['output_root']/'current.json').read_bytes()
  with tempfile.TemporaryDirectory() as folder:
   out=Path(folder);prepared=out/'base';prepared.mkdir()
   for name in ['manifest.json','report.json']:(prepared/name).write_bytes((base/name).read_bytes())
   pp.write_json(out/'prepared.json',{'path':'base'})
   trial=t.isolated_config({**cfg,'output_root':out},pages,t.VARIANTS[2])
   self.assertTrue(trial['output_root'].is_relative_to(out/'tuning'))
   target=pp.resolve_pointer(trial['output_root'],'prepared.json')
   manifest=pp.read_json(target/'manifest.json')
   self.assertEqual(manifest['chunk_count'],len(pp.read_lines(target/'chunks.jsonl')))
   pp.verify_files(target,manifest)
  self.assertEqual(original,(cfg['output_root']/'current.json').read_bytes())
