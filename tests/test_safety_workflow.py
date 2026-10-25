import unittest
from unittest.mock import Mock, patch
import httpx
from pipeline import official_web as w
from pipeline.safety_workflow import assemble, coverage
from pipeline.document_links import query_topics
from pipeline.structured_ingestion import match_materials


class SafetyWorkflowTests(unittest.TestCase):
    def test_missing_pictogram_does_not_trigger_web_when_health_source_exists(self):
        material = {'name_raw': '염화수소', 'cas_raw': '7647-01-0', 'pdf_page': 56}
        health = {'chunk_id': 'health', 'text': 'Official health and first aid reference',
                  'doc_id': 'official_web', 'doc_type': 'official_web', 'content_type': 'official_web',
                  'cas_raw': '7647-01-0', 'graph_group': 'web'}
        lookup = Mock(side_effect=AssertionError('Pictogram-only web lookup must not run'))
        _, report = assemble([], {'matched_materials': [material], 'results': [health]},
                             web_enabled=True, lookup=lookup)
        lookup.assert_not_called()
        self.assertIn('pictograms', report['coverage']['missing'])
        self.assertEqual(report['web']['status'], 'not_needed')
        self.assertEqual(report['web']['unresolved'], [])

    def test_health_search_remains_enabled_regardless_of_pictogram_availability(self):
        material = {'name_raw': '가성소다', 'cas_raw': '1310-73-2', 'pdf_page': 54}
        for icons in ([], [{'canonical_code': 'GHS05'}]):
            with self.subTest(icons=icons):
                native = {'chunk_id': 'material', 'text': 'Material evidence',
                          'doc_id': 'lab_safety_manual', 'pdf_page_start': 54, 'icons': icons}
                lookup = Mock(return_value={'status': 'no_verified_source', 'results': [], 'errors': []})
                _, report = assemble([], {'matched_materials': [material], 'results': [native]},
                                     web_enabled=True, lookup=lookup)
                lookup.assert_called_once_with([material], ['official_health_reference'], enabled=True)
                self.assertEqual(report['web']['unresolved'], ['official_health_reference'])

    def test_alias_boundary_and_colloquial_leaks(self):
        catalog = [{'aliases_from_source': ['염화수소'], 'cas_raw': '7647-01-0'}]
        self.assertEqual(match_materials('염산을 쏟았어', catalog), catalog)
        self.assertEqual(match_materials('HCl 누출', catalog), catalog)
        self.assertEqual(match_materials('염산염 분석', catalog), [])
        self.assertIn('gas_leak', query_topics('암모니아 가스가 누출됐어요'))
        self.assertIn('spill', query_topics('황산이 새고 있어'))
        self.assertIn('handling', query_topics('화학약품을 사용하기 전에'))

    def test_web_redirects_never_leave_official_hosts(self):
        requests = []
        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError):
                w.fetch_html(client, 'https://www.cdc.gov/niosh/npg/npgd0332.html')
        self.assertEqual(len(requests), 1)
        self.assertFalse(w.allowed_url('https://www.cdc.gov.evil.example/page'))
        self.assertFalse(w.allowed_url('https://secret@www.cdc.gov/page'))

    def test_web_verifies_body_not_search_snippet_and_never_leaks_keys(self):
        seen = []
        def handler(request):
            seen.append(request)
            if request.url.host == 'openapi.naver.com':
                return httpx.Response(200, json={'items': [{'link': 'https://evil.example/page', 'description': '7647-01-0 First Aid'}]})
            return httpx.Response(200, headers={'content-type':'text/html'}, text='<main>Hydrogen chloride CAS 7647-01-0<h2>First Aid</h2>Eye: Irrigate immediately</main>')
        material = {'cas_raw':'7647-01-0', 'name_raw':'염화수소'}
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
             patch.dict('os.environ', {'NAVER_CLIENT_ID':'test-id','NAVER_CLIENT_SECRET':'test-secret'}), \
             patch.object(w, 'cdc_index', return_value={'7647-01-0':'https://www.cdc.gov/niosh/npg/npgd0332.html'}):
            result = w.lookup([material], ['health'], client=client)
        self.assertEqual(result['status'], 'supplemented')
        self.assertIn('Irrigate', result['results'][0]['text'])
        self.assertTrue(all('x-naver-client-secret' not in req.headers for req in seen if req.url.host != 'openapi.naver.com'))
        self.assertEqual(result['queries'], ['7647-01-0 chemical safety first aid site:cdc.gov/niosh/npg'])

    def test_wrong_cas_and_network_failure_stay_unresolved(self):
        material = {'cas_raw':'7647-01-0','name_raw':'염화수소'}
        def handler(request):
            return httpx.Response(200, headers={'content-type':'text/html'}, text='CAS 7664-41-7 First Aid')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
             patch.dict('os.environ', {'NAVER_CLIENT_ID':'','NAVER_CLIENT_SECRET':''}), \
             patch.object(w,'cdc_index',return_value={'7647-01-0':'https://www.cdc.gov/niosh/npg/npgd0032.html'}):
            result=w.lookup([material],['health'],client=client)
        self.assertEqual(result['results'], [])
        self.assertEqual(result['unresolved'], ['health'])
        with patch.object(w,'cdc_index',side_effect=httpx.ConnectError('offline')), patch.dict('os.environ', {'NAVER_CLIENT_ID':'','NAVER_CLIENT_SECRET':''}):
            result=w.lookup([material],['health'])
        self.assertIn('cdc_index_unavailable',result['errors'])

    def test_context_budget_reserves_department_and_hospital(self):
        rows = [{'chunk_id':str(i),'text':'x'*500,'doc_id':'lab_safety_manual','pdf_page_start':56} for i in range(30)]
        contacts = [{'chunk_id':role,'text':'contact evidence','content_type':'contact_record','contact':{'role_raw':role},'graph_group':'contact'} for role in ('연구실 안전관리','병원')]
        graph = {'matched_materials':[{'name_raw':'염화수소','cas_raw':'7647-01-0','pdf_page':56}], 'query_topics':['spill'], 'results':contacts+rows[:3]}
        selected, report=assemble(rows,graph,web_enabled=False,max_docs=8,max_chars=4000)
        self.assertTrue({'연구실 안전관리','병원'}.issubset({r['chunk_id'] for r in selected}))
        self.assertIn('pictograms',report['coverage']['missing'])
        self.assertLessEqual(len(selected),8)
        self.assertEqual(report['web']['status'],'disabled')
        self.assertTrue(coverage(selected,graph['matched_materials'],[])['materials'][0]['pictograms_available'] is False)

    def test_evaluation_context_excludes_unselected_candidates(self):
        from pipeline.retrieval_context import evidence_rows
        self.assertEqual(evidence_rows({'results':[{'chunk_id':'unused'}], 'context_results':[{'chunk_id':'used'}]}), [{'chunk_id':'used'}])

    def test_missing_contact_is_appended_with_source_and_hours(self):
        from pipeline.safety_workflow import ensure_contact_details
        rows = [{'chunk_id':'hospital-record', 'contact':{
            'role_raw':'병원','organization_raw':'원문 병원', 'phone_numbers_raw':['741-0114'],
            'availability_raw':'주간/야간'}}]
        answer, ids = ensure_contact_details('초기 답변', rows)
        self.assertIn('741-0114',answer)
        self.assertIn('주간/야간',answer)
        self.assertIn('[hospital-record]',answer)
        self.assertEqual(ids,['hospital-record'])
        unchanged, ids = ensure_contact_details(answer,rows)
        self.assertEqual(unchanged,answer)
        self.assertEqual(ids,[])
        api, _ = ensure_contact_details('초기 답변',rows,citation_style='number')
        self.assertIn('(문서 1)',api)


if __name__ == '__main__': unittest.main()
