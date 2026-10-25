"""Source-backed property graph and bounded multi-hop retrieval for SafeOps.

JSON is the storage format; retrieval traverses typed edges in an adjacency index.
No graph server, embedding call or LLM is needed for graph compilation/traversal.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path

from pipeline.document_links import query_topics
from pipeline.structured_ingestion import match_materials

VERSION = 'safeops-knowledge-graph-v2'
DEFAULT_MAX_HOPS = 5
DEFAULT_MAX_RESULTS = 24
TOPIC_LABELS = {
    'spill': '화학물질 누출', 'gas_leak': '가스 누출',
    'body_contamination': '신체 오염', 'cut_puncture': '베임·찔림',
    'fire': '화재', 'emergency_patient': '응급환자',
    'preparation': '비상 준비', 'waste': '폐기물 처리', 'reporting': '사고 보고',
    'handling': '물질 취급·보관', 'transport': '가스용기 운반',
}
# These are retrieval-routing rules, separately labelled from PDF relationships.
TOPIC_ROLES = {
    'spill': ['연구실 안전관리', '병원'], 'gas_leak': ['연구실 안전관리', '병원'],
    'body_contamination': ['연구실 안전관리', '병원'],
    'cut_puncture': ['연구실 안전관리', '병원'],
    'fire': ['연구실 안전관리', '소방 안전관리', '소방서'],
    'emergency_patient': ['병원', '소방서'],
    'waste': ['폐시약/폐기물관리'], 'reporting': ['연구실 안전관리'],
}


def stable_id(kind, *values):
    value = json.dumps(values, ensure_ascii=False, sort_keys=True)
    return kind + ':' + hashlib.sha256(value.encode()).hexdigest()[:20]


def compile_graph(rows, catalog, structure, links, operating_policy=None):
    """Compile source entities/edges. Routing edges carry explicit provenance."""
    nodes, edges = {}, {}
    evidence = {r['chunk_id']: dict(r) for r in rows}
    for section in (links or {}).get('sections', []):
        evidence[section['chunk_id']] = dict(section)

    def node(nid, kind, label, evidence_ids=(), **props):
        nodes[nid] = {'id': nid, 'type': kind, 'label': label,
                      'evidence_ids': list(evidence_ids), **props}
        return nid

    def edge(source, target, relation, basis, evidence_ids=(), **props):
        eid = stable_id('edge', source, target, relation, props)
        edges[eid] = {'id': eid, 'source': source, 'target': target,
                      'relation': relation, 'basis': basis,
                      'evidence_ids': list(evidence_ids), **props}

    for r in evidence.values():
        node('evidence:' + r['chunk_id'], 'evidence',
             r.get('section_id') or r.get('section_title') or r['chunk_id'],
             [r['chunk_id']], doc_id=r.get('doc_id'), pdf_page=r.get('pdf_page_start'))
    for topic, label in TOPIC_LABELS.items():
        node('incident:' + topic, 'incident_type', label, topic=topic)

    material_nodes = []
    dictionary = json.loads((Path(__file__).parent / 'ghs_dictionary.json').read_text())
    symbols = {s['code']: s for s in dictionary['symbols']}
    for material in catalog:
        mid = stable_id('material', material.get('source_sha256'), material['pdf_page'],
                        material['aliases_from_source'])
        node(mid, 'material', material.get('name_raw') or material['aliases_from_source'][0],
             material=material)
        material_nodes.append(mid)
        material_rows = [r for r in rows if r.get('doc_id') == 'lab_safety_manual'
                         and r.get('pdf_page_start') == material['pdf_page']]
        for r in material_rows:
            edge(mid, 'evidence:' + r['chunk_id'], 'described_by', 'source_page', [r['chunk_id']])
            for icon in r.get('icons', []):
                code = icon['canonical_code']
                symbol = symbols[code]
                eid = 'ghs-definition-' + code
                evidence[eid] = {'chunk_id': eid, 'doc_id': 'ghs_dictionary',
                    'filename': 'GHS 공식 코드 사전', 'doc_type': 'reference',
                    'pdf_page_start': None, 'pdf_page_end': None,
                    'source_url': dictionary['standard_mapping_source'],
                    'content_type': 'ghs_definition', 'ghs_code': code,
                    'text': f"{code} {symbol['name_ko']}: {symbol['general_meaning']}. 그림 종류의 일반 의미이며 개별 제품의 농도·위험등급·보호구 사양은 제품 SDS에서 확인한다."}
                node('ghs:' + code, 'hazard_symbol', code + ' ' + symbol['name_ko'], [eid])
                edge(mid, 'ghs:' + code, 'has_reviewed_pictogram', 'reviewed_source_pictogram', [r['chunk_id']])
        # A documented topic is a navigation relation, not a claim that an event occurred.
        for topic, pattern in [('spill', r'누출\s*시'), ('fire', r'화재\s*시')]:
            ids = [r['chunk_id'] for r in material_rows if re.search(pattern, r['text'])]
            if ids:
                edge(mid, 'incident:' + topic, 'has_guidance_topic', 'source_heading', ids,
                     topic=topic)

    sections = {s['section_id']: s for s in (links or {}).get('sections', [])}
    # Preventive guidance remains conditional: material identification is not evidence of exposure.
    for mid in material_nodes:
        for sid in ('body_contamination', 'chemical_rules'):
            if sid in sections:
                edge(mid, 'evidence:' + sections[sid]['chunk_id'], 'personal_precaution_reference',
                     'retrieval_policy_conditional_exposure', [sections[sid]['chunk_id']])
        for code in symbols:
            if 'ghs:' + code in nodes and code in ('GHS05', 'GHS06', 'GHS07', 'GHS08'):
                if 'body_contamination' in sections:
                    edge('ghs:' + code, 'evidence:' + sections['body_contamination']['chunk_id'],
                         'exposure_guidance_candidate', 'retrieval_policy_not_symbol_specific_treatment')
    for topic, section_ids in (links or {}).get('routes', {}).items():
        if 'incident:' + topic not in nodes:
            continue
        for sid in section_ids:
            section = sections[sid]
            edge('incident:' + topic, 'evidence:' + section['chunk_id'],
                 'has_guidance', 'document_link_route', [section['chunk_id']])
    for relation in (links or {}).get('relations', []):
        a, b = sections[relation['from']], sections[relation['to']]
        edge('evidence:' + a['chunk_id'], 'evidence:' + b['chunk_id'],
             relation['relation'], 'source_section_relation', [a['chunk_id'], b['chunk_id']])

    structure = structure or {}
    procedure = structure.get('procedure.json', {})
    lane_rows = {r['lane_id']: r for r in rows if r.get('content_type') == 'procedure_lane'}
    for lane in procedure.get('lanes', []):
        lid = lane['lane_id']
        ids = [lane_rows[lid]['chunk_id']] if lid in lane_rows else []
        node('procedure:' + lid, 'procedure', lane.get('condition_raw') or '안전관리 부서 절차',
             ids, lane_id=lid, condition=lane.get('condition_raw'))
        for topic in TOPIC_ROLES:
            if topic == 'waste':
                continue
            edge('incident:' + topic, 'procedure:' + lid, 'reporting_procedure',
                 'retrieval_policy', ids, classification={'left': 'major', 'right': 'non_major'}.get(lid))
    for step in procedure.get('nodes', []):
        ids = [lane_rows[step['lane_id']]['chunk_id']] if step['lane_id'] in lane_rows else []
        sid = node('step:' + step['node_id'], 'procedure_step', step['evidence']['raw_text'],
                   ids, lane_id=step['lane_id'], source_evidence=step['evidence'])
        edge('procedure:' + step['lane_id'], sid, 'contains_step', 'source_lane', ids)
    for relation in procedure.get('edges', []):
        source, target = 'step:' + relation['from'], 'step:' + relation['to']
        edge(source, target, 'next_step', relation.get('basis', 'source_arrow'),
             nodes[source]['evidence_ids'])

    contact_rows = {r['contact_id']: r for r in rows if r.get('content_type') == 'contact_record'}
    for contact in structure.get('contacts.json', {}).get('contacts', []):
        cid = contact['contact_id']
        ids = [contact_rows[cid]['chunk_id']] if cid in contact_rows else []
        scope = contact['institution_scope']
        institution = stable_id('institution', scope)
        node(institution, 'institution', scope, institution_scope=scope)
        org = stable_id('organization', scope, contact['organization_raw'], contact.get('department_raw'))
        label = ' / '.join(x for x in [contact['organization_raw'], contact.get('department_raw')] if x)
        node(org, 'organization', label, institution_scope=scope)
        edge(org, institution, 'within_institution', 'contact_record', ids)
        role = stable_id('role', contact['role_raw'])
        node(role, 'role', contact['role_raw'])
        service = stable_id('service', org, role)
        node(service, 'service', label + ' / ' + contact['role_raw'], institution_scope=scope)
        edge(role, service, 'provided_by', 'contact_record', ids)
        edge(service, org, 'at_organization', 'contact_record', ids)
        contact_node = node('contact:' + cid, 'contact',
                            contact['role_raw'] + ' / ' + ', '.join(contact['phone_numbers_raw']),
                            ids, institution_scope=scope, contact=contact)
        edge(service, contact_node, 'has_contact', 'contact_record', ids)
        edge(contact_node, org, 'belongs_to', 'contact_record', ids)
    for topic, roles in TOPIC_ROLES.items():
        for role in roles:
            rid = stable_id('role', role)
            if rid in nodes:
                edge('incident:' + topic, rid, 'related_work', 'retrieval_policy')
    for mid in material_nodes:
        for role in ('연구실 안전관리', '병원'):
            rid = stable_id('role', role)
            if rid in nodes:
                edge(mid, rid, 'related_work', 'retrieval_policy_conditional_handoff')
    for relation in structure.get('role_links.json', {}).get('links', []):
        source, target = 'step:' + relation['node_id'], 'contact:' + relation['contact_id']
        if source in nodes and target in nodes:
            edge(source, target, relation['relation'], 'reviewed_role_link',
                 nodes[source]['evidence_ids'] + nodes[target]['evidence_ids'],
                 status=relation.get('status'))

    graph = {'version': VERSION, 'nodes': list(nodes.values()), 'edges': list(edges.values()),
             'evidence': list(evidence.values()), 'operating_policy': operating_policy,
             'retrieval_policy': {'topic_roles': TOPIC_ROLES, 'default_max_hops': DEFAULT_MAX_HOPS},
             'statistics': {'nodes': len(nodes), 'edges': len(edges),
                            'node_types': dict(Counter(n['type'] for n in nodes.values()))}}
    validate_graph(graph)
    return graph


def validate_graph(graph):
    if graph.get('version') != VERSION:
        raise ValueError('Unsupported knowledge graph version; rebuild the graph')
    nodes = {n['id']: n for n in graph['nodes']}
    evidence = {r['chunk_id'] for r in graph['evidence']}
    if len(nodes) != len(graph['nodes']) or len(evidence) != len(graph['evidence']):
        raise ValueError('Duplicate graph node/evidence IDs')
    if len({e['id'] for e in graph['edges']}) != len(graph['edges']):
        raise ValueError('Duplicate graph edge IDs')
    for edge in graph['edges']:
        if edge['source'] not in nodes or edge['target'] not in nodes:
            raise ValueError('Dangling graph edge')
    for item in graph['nodes'] + graph['edges']:
        if not set(item.get('evidence_ids', [])).issubset(evidence):
            raise ValueError('Missing graph evidence')


def evidence_eligible(row, *, institution_scope=None, accident_classification=None, timing=None):
    """Apply the same structured filters to graph and vector evidence."""
    contact = row.get('contact')
    if contact:
        if institution_scope and contact['institution_scope'] != institution_scope:
            return False
        if timing and contact['availability_normalized'] not in ('all_times', timing['period']):
            return False
    lane = row.get('lane_id')
    if lane and accident_classification:
        if lane not in ('center', 'left' if accident_classification == 'major' else 'right'):
            return False
    # Raw table/page chunks bypass row filters; use the structured records instead.
    if row.get('doc_id') == 'lab_safety_manual':
        if row.get('pdf_page_start') == 32 and not contact and (institution_scope or timing):
            return False
        if row.get('pdf_page_start') == 34 and not lane and accident_classification:
            return False
    return True


def retrieve(graph, question, *, max_hops=DEFAULT_MAX_HOPS, max_results=DEFAULT_MAX_RESULTS,
             institution_scope=None, accident_classification=None, at=None):
    """Entity linking followed by bounded BFS on typed, directed property edges."""
    validate_graph(graph)
    if not 1 <= max_hops <= 8 or not 1 <= max_results <= 50:
        raise ValueError('Graph max_hops must be 1..8 and max_results 1..50')
    if accident_classification not in (None, 'major', 'non_major'):
        raise ValueError('Invalid accident classification')
    timing = None
    if at is not None:
        from pipeline.safety_structure import classify_time
        if isinstance(at, str):
            at = datetime.fromisoformat(at)
        if graph.get('operating_policy') is None:
            raise ValueError('Graph has no versioned operating policy')
        timing = classify_time(at, graph['operating_policy'])
    nodes = {n['id']: n for n in graph['nodes']}
    evidence = {r['chunk_id']: r for r in graph['evidence']}
    outgoing = defaultdict(list)
    for edge in graph['edges']:
        outgoing[edge['source']].append(edge)
    # Prefer the general work relationship when equally short contact paths exist,
    # so a conditional reporting branch does not become the default explanation.
    priority = {'has_guidance': 0, 'related_work': 1, 'reporting_procedure': 2}
    for edges in outgoing.values():
        edges.sort(key=lambda edge: priority.get(edge['relation'], 0))
    materials = [n for n in nodes.values() if n['type'] == 'material'
                 and match_materials(question, [n['material']])]
    topics = query_topics(question)
    if any(t in question for t in ('보고', '사고')):
        topics.append('reporting')
    topics = list(dict.fromkeys(topics))
    seeds = [n['id'] for n in materials] + ['incident:' + t for t in topics]
    # Direct role/organization questions can also enter the graph.
    seeds += [n['id'] for n in nodes.values() if n['type'] in ('role', 'organization')
              and len(n['label']) >= 2 and n['label'] in question]
    # Preserve both records in explicit comparison questions (e.g. 시설 당직실 vs 당직실 시설).
    seeds += [n['id'] for n in nodes.values() if n['type'] == 'role'
              and len(n['label'].split()) > 1
              and all(word in question for word in n['label'].split())]
    # Organization queries follow incoming service membership, then directed traversal.
    org_seeds = {s for s in seeds if nodes.get(s, {}).get('type') == 'organization'}
    seeds += [e['source'] for e in graph['edges'] if e['relation'] == 'at_organization' and e['target'] in org_seeds]
    if any(w in question for w in ('연락망', '비상연락', '전화번호', '연락처')):
        if not topics and not any(nodes[s]['type'] in ('role', 'organization', 'service') for s in seeds):
            seeds += [n['id'] for n in nodes.values() if n['type'] == 'role']
    seeds = list(dict.fromkeys(s for s in seeds if s in nodes))
    lanes = {'center'} | ({'left'} if accident_classification == 'major' else
                          {'right'} if accident_classification == 'non_major' else {'left', 'right'})

    def allowed(n):
        if institution_scope and n.get('institution_scope') not in (None, institution_scope):
            return False
        if n.get('lane_id') and n['lane_id'] not in lanes:
            return False
        if n['type'] == 'contact' and timing:
            return n['contact']['availability_normalized'] in ('all_times', timing['period'])
        return True

    # One shortest path per (seed, node), so cycles terminate and alternate seeds remain visible.
    queue = deque((seed, seed, [seed], []) for seed in seeds if allowed(nodes[seed]))
    visited, paths_by_evidence = set(), defaultdict(list)
    visited_nodes, traversed = set(), set()
    while queue:
        seed, nid, path_nodes, path_edges = queue.popleft()
        if (seed, nid) in visited:
            continue
        visited.add((seed, nid)); visited_nodes.add(nid)
        n = nodes[nid]
        for eid in n['evidence_ids']:
            if not evidence_eligible(evidence[eid], institution_scope=institution_scope,
                                     accident_classification=accident_classification, timing=timing):
                continue
            # Keep distinct entry entities rather than filling all slots with the
            # same incident seed reaching a lane through several of its steps.
            if (len(paths_by_evidence[eid]) < 3
                    and not any(p['node_ids'][0] == seed for p in paths_by_evidence[eid])):
                paths_by_evidence[eid].append({
                    'node_ids': path_nodes, 'labels': [nodes[x]['label'] for x in path_nodes],
                    'relations': [e['relation'] for e in path_edges],
                    'edge_ids': [e['id'] for e in path_edges],
                    'bases': [e['basis'] for e in path_edges],
                    'conditions': [nodes[x].get('condition') for x in path_nodes if nodes[x].get('condition')],
                    'statuses': [e['status'] for e in path_edges if e.get('status')],
                    'hops': len(path_edges)})
        if len(path_edges) >= max_hops:
            continue
        for edge in outgoing[nid]:
            target = nodes[edge['target']]
            if target['type'] == 'incident_type' and target['topic'] not in topics:
                continue
            if not allowed(target):
                continue
            traversed.add(edge['id'])
            queue.append((seed, target['id'], path_nodes + [target['id']], path_edges + [edge]))

    # Reserve coverage across material, guidance, procedure and contact evidence.
    groups = defaultdict(list)
    for eid, paths in paths_by_evidence.items():
        row = evidence[eid]
        kind = row.get('content_type', 'material')
        group = {'procedure_lane': 'procedure', 'contact_record': 'contact', 'ghs_definition': 'hazard',
                 'linked_source_section': 'guidance'}.get(kind, 'material')
        groups[group].append({**row, 'distance': None, 'retrieval_reason': 'graph_traversal',
                              'graph_group': group, 'graph_paths': paths,
                              'graph_time_filter': timing, 'graph_institution_scope': institution_scope})
    for group in groups.values():
        group.sort(key=lambda r: min(p['hops'] for p in r['graph_paths']))
    ordered = []
    while any(groups.values()) and len(ordered) < max_results:
        for name in ('material', 'guidance', 'procedure', 'contact', 'hazard'):
            if groups[name] and len(ordered) < max_results:
                ordered.append(groups[name].pop(0))
    return {'version': VERSION, 'algorithm': 'typed_directed_bfs', 'max_hops': max_hops,
            'seed_nodes': [{'id': s, 'type': nodes[s]['type'], 'label': nodes[s]['label']} for s in seeds],
            'matched_materials': [n['material'] for n in materials], 'query_topics': topics,
            'visited_node_count': len(visited_nodes), 'traversed_edge_count': len(traversed),
            'candidate_evidence_count': len(paths_by_evidence),
            'truncated': len(paths_by_evidence) > len(ordered), 'timing': timing, 'results': ordered}


def graph_from_folder(folder):
    """Read a versioned graph, or compile legacy snapshots without mutating the index."""
    from pipeline.pdf_pipeline import read_json, read_lines, verify_files
    manifest = read_json(folder / 'manifest.json')
    verify_files(folder, manifest)
    if 'knowledge_graph.json' in manifest['files']:
        graph = read_json(folder / 'knowledge_graph.json')
    else:
        def optional(name, default):
            return read_json(folder / name) if name in manifest['files'] else default
        row_file = 'documents.jsonl' if 'documents.jsonl' in manifest['files'] else 'chunks.jsonl'
        graph = compile_graph(read_lines(folder / row_file), optional('material_catalog.json', []),
                              optional('structure_snapshot.json', None), optional('document_links.json', None),
                              optional('operating_policy.json', None))
    validate_graph(graph)
    return graph


def main():
    import argparse
    from pipeline.pdf_pipeline import ROOT, config_at, resolve_pointer
    parser = argparse.ArgumentParser(description='Local graph retrieval; no embedding/LLM API calls')
    parser.add_argument('question')
    parser.add_argument('--config', default=str(ROOT / 'pipeline/config.json'))
    parser.add_argument('--prepared', action='store_true', help='Use prepared data before embedding')
    parser.add_argument('--max-hops', type=int, default=DEFAULT_MAX_HOPS)
    parser.add_argument('--max-results', type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument('--institution-scope')
    parser.add_argument('--classification', choices=['major', 'non_major'])
    parser.add_argument('--at', help='ISO datetime with timezone for contact hours')
    args = parser.parse_args()
    cfg = config_at(args.config)
    folder = resolve_pointer(cfg['output_root'], 'prepared.json' if args.prepared else 'current.json')
    result = retrieve(graph_from_folder(folder), args.question, max_hops=args.max_hops,
                      max_results=args.max_results, institution_scope=args.institution_scope,
                      accident_classification=args.classification, at=args.at)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
