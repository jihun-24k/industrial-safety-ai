import unittest
from pipeline import pdf_pipeline as p
from pipeline.reviewed_pictograms import reviewed_chunks

class ReviewedPictogramTests(unittest.TestCase):
    def test_only_approved_icon_supplements(self):
        cfg=p.config_at(p.ROOT/'pipeline/config.json')
        rows=reviewed_chunks(cfg)
        self.assertEqual([r['pdf_page_start'] for r in rows],[54,55])
        self.assertEqual([[i['canonical_code'] for i in r['icons']] for r in rows],
                         [['GHS05','GHS07'],['GHS02','GHS06','GHS08','GHS05']])
        for row in rows:
            self.assertEqual(row['review_scope'],'pictogram_identity_count_order_only')
            self.assertEqual(row['source_spans'],[])
            self.assertNotIn('NFPA',row['text'])
            self.assertNotIn('색상',row['text'])
        self.assertEqual(reviewed_chunks({}),[])
        with self.assertRaises(ValueError):
            reviewed_chunks({**cfg,'reviewed_pictograms_sha256':'changed'})
        changed={**cfg,'documents':[{**d,'sha256':'changed'} for d in cfg['documents']]}
        with self.assertRaises(ValueError): reviewed_chunks(changed)
