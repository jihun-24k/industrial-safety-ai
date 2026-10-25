import ast
import asyncio
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from pipeline import pdf_pipeline as p
from pipeline.knowledge_graph import (
    compile_graph, evidence_eligible, graph_from_folder, retrieve, validate_graph,
)
from pipeline.retrieval_context import evidence_rows, path_text, select_context_rows


class TestEmbeddings(Embeddings):
    """Offline vectors for index plumbing only, not semantic-quality evaluation."""
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float('암모니아' in text), float('화재' in text), 0.1]


class GraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.cfg = {**p.config_at(p.ROOT / 'pipeline/config.json'), 'output_root': Path(cls.temp.name),
                   'embedding_model': 'offline-test-only', 'embedding_dimension': 3}
        p.prepare(cls.cfg)
        cls.prepared = p.resolve_pointer(cls.cfg['output_root'], 'prepared.json')
        cls.graph = graph_from_folder(cls.prepared)
        p.build(cls.cfg, TestEmbeddings())
        cls.folder = p.resolve_pointer(cls.cfg['output_root'], 'current.json')

    def test_real_documents_compile_entities_and_provenance(self):
        stats = self.graph['statistics']['node_types']
        self.assertEqual(stats['material'], 50)
        self.assertEqual(stats['procedure'], 3)
        self.assertEqual(stats['contact'], 8)
        validate_graph(self.graph)
        self.assertTrue(all(e['basis'] for e in self.graph['edges']))
        result = retrieve(self.graph, '암모니아가 누출됐어요. 보고 절차와 연락처는?')
        self.assertEqual({r['graph_group'] for r in result['results']},
                         {'material', 'guidance', 'procedure', 'contact', 'hazard'})
        self.assertEqual({r['pdf_page_start'] for r in result['results'] if r['graph_group'] == 'material'}, {55})
        self.assertTrue(any(pth['hops'] >= 3 for r in result['results'] for pth in r['graph_paths']))
        contact = next(r for r in result['results'] if r.get('contact_id') == 'lab_safety')
        self.assertTrue(any(path['node_ids'][0].startswith('material:') for path in contact['graph_paths']))

    def test_hop_limit_and_edge_removal_change_retrieval(self):
        q = '화재'
        shallow = retrieve(self.graph, q, max_hops=1)
        self.assertFalse(any(r.get('contact_id') for r in shallow['results']))
        full = retrieve(self.graph, q)
        self.assertIn('fire_station', [r.get('contact_id') for r in full['results']])
        graph = deepcopy(self.graph)
        graph['edges'] = [e for e in graph['edges'] if e['target'] != 'contact:fire_station']
        changed = retrieve(graph, q)
        self.assertNotIn('fire_station', [r.get('contact_id') for r in changed['results']])

    def test_material_profile_and_all_scenario_source_anchors(self):
        from pipeline.safety_workflow import assemble
        from pipeline.notebook_evaluation import evidence_hits
        result = retrieve(self.graph, '가성소다 주의사항')
        selected, report = assemble([],result,web_enabled=False)
        self.assertTrue({'hospital','lab_safety'}.issubset({r.get('contact_id') for r in selected}))
        self.assertTrue(any(r.get('ghs_code') == 'GHS05' for r in selected))
        self.assertIn('personal_precautions',report['coverage']['source_ids'])
        for case in p.read_json(p.ROOT/'evaluation/notebook_cases.json')['cases']:
            if not case['evidence']:
                continue
            result = retrieve(self.graph,case['question'])
            selected, _ = assemble([],result,web_enabled=False)
            self.assertEqual(evidence_hits(case,selected)['candidate_recall_at_k'],1,case['id'])

    def test_restrictions_continuations_and_unrelated_materials(self):
        fire = retrieve(self.graph, '가성소다 화재')
        self.assertTrue({'fire_general', 'fire_limits'}.issubset({r.get('section_id') for r in fire['results']}))
        gas = retrieve(self.graph, '가스 누출')
        self.assertTrue({'gas_leak_start', 'gas_leak_continuation'}.issubset({r.get('section_id') for r in gas['results']}))
        matched = retrieve(self.graph, '질산암모늄')
        self.assertEqual(len(matched['matched_materials']), 1)
        self.assertEqual(matched['matched_materials'][0]['pdf_page'], 72)
        unknown = retrieve(self.graph, '관련 없는 텍스트')
        self.assertEqual(unknown['results'], [])

    def test_filters_and_direct_role_query(self):
        scoped = retrieve(self.graph, '화재', institution_scope='different_institution')
        self.assertFalse(any(r.get('contact_id') for r in scoped['results']))
        day = retrieve(self.graph, '연구실 안전관리 연락처', at='2026-10-23T11:00:00+09:00')
        self.assertEqual([r.get('contact_id') for r in day['results']], ['lab_safety'])
        night = retrieve(self.graph, '연구실 안전관리 연락처', at='2026-10-23T19:00:00+09:00')
        self.assertEqual(night['results'], [])
        classified = retrieve(self.graph, '누출 사고 보고', accident_classification='non_major')
        self.assertEqual({r['lane_id'] for r in classified['results'] if 'lane_id' in r}, {'center', 'right'})
        with self.assertRaises(ValueError):
            retrieve(self.graph, '화재', at='2026-10-23T11:00:00')

    def test_organization_and_cycle_traversal(self):
        result = retrieve(self.graph, '대학본부 연락처')
        self.assertEqual({r['contact_id'] for r in result['results']}, {'lab_safety', 'fire_safety', 'waste'})
        graph = deepcopy(self.graph)
        e = next(e for e in graph['edges'] if e['source'] == 'incident:fire')
        graph['edges'].append({**e, 'id': 'test-cycle', 'source': e['target'], 'target': e['source']})
        cycled = retrieve(graph, '화재')
        self.assertLessEqual(cycled['visited_node_count'], len(graph['nodes']))

    def test_index_integration_and_graph_hash_validation(self):
        result = p.search(self.cfg, TestEmbeddings(), '암모니아 누출 보고', 3)
        self.assertTrue(result['graph_results'])
        self.assertEqual(result['graph_retrieval']['algorithm'], 'typed_directed_bfs')
        self.assertTrue(all(r['pdf_page_start'] == 55 for r in result['results']))
        disabled = p.search({**self.cfg, 'graph': {'enabled': False}}, TestEmbeddings(), '암모니아 누출', 3)
        self.assertEqual(disabled['graph_results'], [])
        manifest = p.read_json(self.folder / 'manifest.json')
        self.assertIn('knowledge_graph.json', manifest['files'])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'knowledge_graph.json').write_text('{}')
            p.write_json(folder / 'manifest.json', {'files': {'knowledge_graph.json': manifest['files']['knowledge_graph.json']}})
            with self.assertRaises(ValueError):
                graph_from_folder(folder)

    def test_legacy_index_graph_fallback_uses_saved_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = p.read_json(self.folder / 'manifest.json')
            names = ['documents.jsonl', 'material_catalog.json', 'structure_snapshot.json', 'document_links.json']
            for name in names:
                (folder / name).write_bytes((self.folder / name).read_bytes())
            p.write_json(folder / 'manifest.json', {'files': {n: manifest['files'][n] for n in names}})
            graph = graph_from_folder(folder)
            self.assertTrue(retrieve(graph, '화재')['results'])
            self.assertFalse((folder / 'knowledge_graph.json').exists())

    def test_graph_citations_context_coverage_and_filters(self):
        result = p.search(self.cfg, TestEmbeddings(), '가성소다 화재 보고', 5)
        rows = evidence_rows(result)
        self.assertEqual(len(rows), len({r['chunk_id'] for r in rows}))
        selected = select_context_rows(result['results'] * 8, result['graph_results'])
        self.assertTrue(any(r.get('contact_id') for r in selected))
        self.assertTrue(any(r.get('lane_id') for r in selected))
        self.assertTrue(any(path_text(r) for r in selected))
        contact = next(r for r in rows if r.get('contact_id') == 'lab_safety')
        self.assertFalse(evidence_eligible(contact, timing={'period': 'nighttime'}))
        self.assertFalse(evidence_eligible({'doc_id': 'lab_safety_manual', 'pdf_page_start': 32},
                                           institution_scope='another'))
        from pipeline.notebook_evaluation import structural_checks
        item = {'retrieval': result, 'answer': {'status': 'answered', 'citation_ids': [contact['chunk_id']]}}
        self.assertTrue(structural_checks({'evidence': [], 'expected_status': 'answered'}, item)['citations_exist_in_context'])
        from pipeline.ragas_evaluation import samples
        run = {'items': [{**item, 'id': 'test', 'question': '화재', 'answer': {**item['answer'], 'answer': '답변'}}]}
        _, sample = next(samples(run, [{'id': 'test', 'question': '화재'}]))
        self.assertTrue(any(contact['text'] in text for text in sample['retrieved_contexts']))

    def test_api_context_and_response_include_graph_paths(self):
        # Load only pure API functions; do not start DB/auth/network clients.
        source_path = p.ROOT / 'rag-code-template_ext/rag_external-web_pdf_closed_llm.py'
        tree = ast.parse(source_path.read_text())
        names = {'prepare_rag', 'make_context', 'doc_label', 'finish_rag'}
        module = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                 and n.name in names], type_ignores=[])
        result = p.search(self.cfg, TestEmbeddings(), '암모니아 누출 보고', 3)
        vector_docs = [(Document(page_content=r['text'], metadata={k: v for k, v in r.items() if k != 'text'}), r['distance'])
                       for r in result['results']]
        scope = {'asyncio': asyncio, 'hashlib': hashlib, 'Document': Document, 'RAGRequest': object,
                 'USE_TEAM_INDEX': True, 'TEAM_CFG': {**self.cfg, 'official_web': {'enabled': False}}, 'team_pipeline': p,
                 'VECTORSTORE_PDF': None, 'VECTORSTORE_WEB': None, 'USE_SEARCH_PLAN': False,
                 'MAX_PLAN_QUERIES': 8, 'PLAN_TOP_K': 3, 'MAX_CONTEXT_DOCS': 12, 'MAX_DISTANCE': 0,
                 'is_emergency': lambda q: False, 'is_incident': lambda q: True,
                 'retrieve_one': lambda *args: vector_docs, 'path_text': path_text,
                 'select_context_rows': select_context_rows, 'evidence_eligible': evidence_eligible,
                 'assemble_safety': __import__('pipeline.safety_workflow', fromlist=['assemble']).assemble,
                 'json': __import__('json'),
                 'generation_requirements': __import__('pipeline.safety_workflow',fromlist=['generation_requirements']).generation_requirements,
                 'ensure_contact_details': __import__('pipeline.safety_workflow',fromlist=['ensure_contact_details']).ensure_contact_details}
        exec(compile(module, str(source_path), 'exec'), scope)
        request = SimpleNamespace(prompt='암모니아 누출 보고', source='pdf', top_k=3,
                                  institution_scope=None, accident_classification=None, contact_at=None)
        state = asyncio.run(scope['prepare_rag'](request))
        self.assertIn('그래프 경로', state['context'])
        self.assertIn('760-2796', state['context'])
        self.assertTrue(state['graph_retrieval']['context_paths'])
        scope.update(re=__import__('re'), extract_by_marker=lambda x: x)
        answer = scope['finish_rag'](state, '근거 내용 (문서 1)')
        self.assertEqual(answer['graph_retrieval'], state['graph_retrieval'])
        scope['retrieve_one'] = lambda *args: []
        request.prompt = '관련 없는 텍스트'
        empty = asyncio.run(scope['prepare_rag'](request))
        self.assertEqual(empty['docs'], [])
        self.assertEqual(empty['context'], '')  # Metadata alone must not trigger answer generation.

    def test_api_rejects_naive_contact_time(self):
        from pydantic import AwareDatetime, BaseModel, Field, ValidationError
        from typing import Literal, Optional
        source_path = p.ROOT / 'rag-code-template_ext/rag_external-web_pdf_closed_llm.py'
        tree = ast.parse(source_path.read_text())
        request_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RAGRequest')
        scope = dict(AwareDatetime=AwareDatetime, BaseModel=BaseModel, Field=Field, Literal=Literal, Optional=Optional)
        exec(compile(ast.Module(body=[request_class], type_ignores=[]), str(source_path), 'exec'), scope)
        model = scope['RAGRequest']
        with self.assertRaises(ValidationError):
            model(prompt='화재', source='pdf', contact_at='2026-10-26T11:00:00')
        request = model(prompt='화재', source='pdf', contact_at='2026-10-26T11:00:00+09:00')
        self.assertIsNotNone(request.contact_at.utcoffset())


if __name__ == '__main__':
    unittest.main()
