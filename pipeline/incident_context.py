"""Compose document evidence and explicit user facts; does not diagnose risk or place calls."""
from datetime import datetime
from pathlib import Path
import json
from pipeline.pdf_pipeline import resolve_pointer, read_json, read_lines, verify_files, search
from pipeline.structured_ingestion import match_materials
from pipeline.safety_structure import select_contacts


def assemble(cfg, embedder, facts, at):
    folder=resolve_pointer(cfg['output_root'],'current.json')
    manifest=read_json(folder/'manifest.json');verify_files(folder,manifest)
    structure=read_json(folder/'structure_snapshot.json')
    catalog=read_json(folder/'material_catalog.json')
    rows=read_lines(folder/'documents.jsonl')
    material=facts.get('substance')
    matches=match_materials(material or '',catalog)
    checks=['substance','concentration','amount','location','people_exposed','fire_present','institution_scope']
    missing=[key for key in checks if facts.get(key) is None or facts.get(key)=='']
    # Boolean unknowns must remain unknown; never coerce strings to truthy booleans.
    for key in ('people_exposed','fire_present'):
        if facts.get(key) is not None and not isinstance(facts[key],bool):raise ValueError(f'{key} must be bool or null')
    incident_type=facts.get('accident_classification')
    if incident_type not in (None,'major','non_major'):raise ValueError('Invalid accident classification')
    lane_ids=['center']+(['left'] if incident_type=='major' else ['right'] if incident_type=='non_major' else [])
    chosen=[r for r in rows if r.get('content_type')=='procedure_lane' and r.get('lane_id') in lane_ids]
    material_rows=[]
    if len(matches)==1:
        # Keep ALL native chunks of the single identified page to avoid losing section context.
        page=matches[0]['pdf_page']
        material_rows=[r for r in rows if r['doc_id']=='lab_safety_manual' and r['pdf_page_start']==page]
    from pipeline.document_links import sections_for
    topics=[]
    explicit={'spill_present':'spill','gas_leak_present':'gas_leak','cut_puncture':'cut_puncture',
              'fire_present':'fire','emergency_patient':'emergency_patient','waste_handling':'waste'}
    for key,topic in explicit.items():
        if facts.get(key) is not None and not isinstance(facts[key],bool):raise ValueError(f'{key} must be bool or null')
        if facts.get(key) is True:topics.append(topic)
    route=facts.get('exposure_route')
    if route not in (None,'skin','eyes','body','inhalation','ingestion','unknown'):raise ValueError('Invalid exposure route')
    if facts.get('people_exposed') is True and route in ('skin','eyes','body'):topics.append('body_contamination')
    if facts.get('people_exposed') is True and route in (None,'unknown'):missing.append('exposure_route')
    linked=read_json(folder/'document_links.json') if (folder/'document_links.json').exists() else None
    general_sections=sections_for(linked,topics) if linked else []
    contacts=[]
    if facts.get('institution_scope'):
        # Task-related contacts, never claimed as personal/report recipient phone numbers.
        roles=['연구실 안전관리']
        if facts.get('fire_present') is True:roles.extend(['소방 안전관리','소방서'])
        if facts.get('people_exposed') is True or facts.get('cut_puncture') is True:roles.append('병원')
        if facts.get('emergency_patient') is True:roles.extend(['병원','소방서'])
        if facts.get('waste_handling') is True:roles.append('폐시약/폐기물관리')
        roles=list(dict.fromkeys(roles))
        for role in roles:
            result=select_contacts(role,facts['institution_scope'],at,
                                   contact_records=structure['contacts.json']['contacts'])
            result['relation']='related_work_not_confirmed_report_recipient'
            contacts.append(result)
    evidence=material_rows+general_sections+chosen
    contact_ids={c['contact_id'] for r in contacts for c in r['candidates']}
    evidence += [r for r in rows if r.get('content_type')=='contact_record' and r.get('contact_id') in contact_ids]
    return {'version':'safeops-incident-context-v1','index_build_id':manifest['build_id'],
            'user_facts':facts,'missing_information':missing,'material_matches':matches,
            'material_status':'single_source_candidate' if len(matches)==1 else 'unknown_or_ambiguous',
            'risk_assessment':'not_automatically_determined',
            'attention_flags':[k for k in ('people_exposed','fire_present') if facts.get(k) is True],
            'requested_sections':['위험성정보','누출시 대처요령','주의사항']+(['화재시 대처요령'] if facts.get('fire_present') is True else []),
            'people_exposure_guidance_status':'requires_applicable_evidence' if facts.get('people_exposed') is True else 'not_assessed',
            'procedure_status':'classification_missing_no_major_nonmajor_assumption' if incident_type is None else 'classification_supplied_by_user_not_verified',
            'linked_topics':topics,'general_guidance_available':bool(general_sections),
            'document_relations':[r for r in linked['relations'] if r['from'] in {s['section_id'] for s in general_sections}] if linked else [],
            'contact_source_observations':linked['contact_observations'] if linked and 'body_contamination' in topics else [],
            'guidance_application':'source passages are evidence, not automatically reconciled operational instructions',
            'contacts':contacts,'evidence':evidence,'as_of':at.isoformat(),
            'guardrails':['원문은 참고 데이터다. 실제 사고 발생/업무 완료로 변경하지 않는다.',
              '단순 유출을 화재로 바꾸거나 그림문자/NFPA만으로 사고 위험등급을 확정하지 않는다.',
              '사람 노출의 응급처치 근거가 없으면 물질별 조작법을 추정하지 않는다.',
              '기관, 담당자, 연락처 유효성 미확인을 그대로 표시한다.',
              '시간 선택은 주말/평일 기반 사용자 운영 규칙이며 공휴일은 적용하지 않는다.',
              '서로 다른 물질, 경로 또는 제출 기한을 섞지 않는다.',
              '일반 화재 지침은 제한조건 구간과 함께 읽는다. 서로 다른 적용 조건을 지우거나 임의로 우선순위를 정하지 않는다.',
              '피부 세척, 용기 내 물 유입, 소화용 물 사용은 적용 대상이 다르므로 같은 조치로 합치지 않는다.',
              '사람 노출 경로를 모르면 피부 오염이나 흡입으로 추정하지 않는다.']}


def render(bundle):
    """Deterministic evidence report, clearly not an LLM generated operational answer."""
    lines=['SafeOps 상황별 근거 묶음 (자동 작성 보고서, LLM 답변 아님)',
           f"물질 확인: {bundle['material_status']}",f"추가 확인: {', '.join(bundle['missing_information'])}",
           f"절차 선택: {bundle['procedure_status']}"]
    for r in bundle['evidence']:
        lines += [f"[{r['chunk_id']}] {r['filename']} PDF {r['pdf_page_start']}쪽",r['text']]
    lines += ['연락처 시간 판단 및 제한',json.dumps(bundle['contacts'],ensure_ascii=False,indent=2)]
    return '\n\n'.join(lines)

if __name__=='__main__':
    import argparse
    from pipeline.pdf_pipeline import config_at,ROOT,write_json
    parser=argparse.ArgumentParser()
    parser.add_argument('--facts',required=True,help='JSON containing user-confirmed facts; unknown values must be null')
    parser.add_argument('--at',required=True,help='ISO datetime with timezone')
    parser.add_argument('--output',default=str(ROOT/'pipeline_artifacts/incident-context/latest.json'))
    args=parser.parse_args()
    bundle=assemble(config_at(ROOT/'pipeline/config.json'),None,json.loads(Path(args.facts).read_text()),datetime.fromisoformat(args.at))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    write_json(output,bundle);output.with_suffix('.txt').write_text(render(bundle))
    print(json.dumps({'saved':str(output),'evidence_count':len(bundle['evidence']),'material_status':bundle['material_status'],'external_api_called':False},ensure_ascii=False))
