"""Versioned source-linked procedure/contact supplements and exact material lookup."""
import hashlib
import json
import re
from pathlib import Path

DATA=Path(__file__).resolve().parent/'structured'
FILES=('procedure.json','contacts.json','role_links.json')

def snapshot():
    return {name:json.loads((DATA/name).read_text()) for name in FILES}

def snapshot_hash(value=None):
    return hashlib.sha256(json.dumps(value or snapshot(),ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def make_chunks(cfg):
    expected=cfg.get('structured_safety_sha256')
    if not expected:return [],None
    data=snapshot()
    if snapshot_hash(data)!=expected:raise ValueError('Structured source changed; review config hash before preparing')
    source=next(d for d in cfg['documents'] if d['doc_id']=='lab_safety_manual')
    graph=data['procedure.json'];contacts=data['contacts.json']['contacts']
    for entry in graph['nodes']+contacts:
        if entry['evidence']['source_sha256']!=source['sha256']:raise ValueError('Structured PDF source version mismatch')
    chunks=[]
    def row(text,page,kind,identity,**meta):
        return dict(chunk_id=hashlib.sha256(f'{expected}:{identity}:{text}'.encode()).hexdigest()[:24],
                    text=text,doc_id=source['doc_id'],filename=source['filename'],source_sha256=source['sha256'],
                    doc_type='manual',pdf_page_start=page,pdf_page_end=page,printed_page=33 if page==34 else None,
                    effective_date=None,freshness_status='unverified',language='ko',source_spans=[],
                    quality_flags=['structured_transcription_coordinates_pending'],review_status='source_transcribed_not_current_validity_verified',
                    usage='development_review_only',content_type=kind,structure_snapshot_hash=expected,**meta)
    for lane in graph['lanes']:
        nodes=[n for n in graph['nodes'] if n['node_id'] in lane['nodes']]
        lines=[f"연구실 안전사고 처리 절차 / {lane['lane_id']} 경로 / 적용 조건: {lane['condition_raw'] or '담당 부서 업무, 사고 유형 조건은 각 상자 참조'}",
               '각 열 내부 순서만 표시. 열 사이의 실행 순서, 사고 발생이나 업무 완료를 의미하지 않는다.']
        lines += [f"단계 {n['node_id']}: {n['evidence']['raw_text']}" for n in nodes]
        lines += ['미확인: 첫 중대사고 조건의 인원 숫자, 연구실 사고 범위, 반복 보고 의도, 기한 계산 기준. 담당자가 해당 상자에 없으면 추정하지 않는다.',
                  '왼쪽 즉시 보고와 오른쪽 사고경위서 제출 수신자는 부서장이다. 부총장으로 바꾸지 않는다.']
        chunks.append(row('\n'.join(lines),34,'procedure_lane',lane['lane_id'],lane_id=lane['lane_id'],node_ids=lane['nodes'],nodes=nodes))
    for c in contacts:
        text=(f"비상연락망 / {c['organization_raw']} / {c['department_raw'] or ''} / 업무: {c['role_raw']}\n"
              f"원문 전화번호: {(' 또는 ' if c['number_relation']=='alternative' else ', ').join(c['phone_numbers_raw'])}\n"
              f"원문 이용 시간: {c['availability_raw']}\n"
              '이 매뉴얼 기관의 연락처이며 현행 유효성과 통화용 번호는 미검증. 부서장 직통번호로 단정하지 않는다. 번호 순서는 우선순위가 아니다. 실제 시간 선택은 별도 사용자 평일/주말 운영 규칙으로 계산하며 공휴일은 적용하지 않는다.')
        chunks.append(row(text,32,'contact_record',c['contact_id'],contact_id=c['contact_id'],contact=c))
    return chunks,data


def material_catalog(pages):
    """Extract identifiers only, not inferred chemistry or operational advice."""
    catalog=[]
    for p in pages:
        if p['doc_id']!='lab_safety_manual':continue
        text=p['cleaned_text']
        if '물질 기본 특성' not in text:continue
        head=text.split('물질 기본 특성',1)[0].strip().splitlines()[-1]
        match=re.fullmatch(r'(.+?)\(([^()]+)\)',head)
        cas=re.search(r'\b\d{2,7}-\d{2}-\d\b',text[:600])
        if not match or not cas:continue
        names=[match[1].strip(),match[2].strip(),cas[0]]
        catalog.append({'name_raw':head,'aliases_from_source':names,'cas_raw':cas[0],
                        'pdf_page':p['pdf_page'],'source_sha256':p['source_sha256'],
                        'identity_status':'source_identifier_candidate_not_independently_verified'})
    return catalog


def match_materials(query,catalog):
    matches=[]
    for entry in catalog:
        found=[]
        for alias in entry['aliases_from_source']:
            # Reject substring collisions, e.g. 질산 vs 질산암모늄; permit Korean particles.
            pattern=r'(?<![\w])'+re.escape(alias)+r'(?=$|[^\w]|(?:을|를|이|가|은|는|에|의|도|와|과|로|으로)(?:\s|$|[?!.,]))'
            if re.search(pattern,query,re.I):found.append(alias)
        if found:matches.append(entry)
    return matches
