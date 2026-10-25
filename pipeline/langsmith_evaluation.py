"""Evaluate saved RAG outputs deterministically and publish an external experiment.
No generation, embeddings or LLM judge calls. Human scores remain human-only.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
from urllib.parse import urlparse
from dotenv import dotenv_values
import httpx
from pipeline.retrieval_context import evidence_rows
from pipeline.pdf_pipeline import ROOT,read_json,write_json
from pipeline.notebook_evaluation import structural_checks,review_version,summarize_feedback


def build_report(run,cases,feedback_path=None):
    case_map={c['id']:c for c in cases}
    if set(case_map)!={i['id'] for i in run['items']}:
        raise ValueError('실행 결과와 질문 목록이 다릅니다.')
    for i in run['items']:
        if i['question']!=case_map[i['id']]['question']:raise ValueError('질문 문구가 변경되었습니다.')
    human={}
    if feedback_path and Path(feedback_path).exists():
        human={r['id']:r for r in summarize_feedback(feedback_path,run)}
    rows=[]
    for item in run['items']:
        case=case_map[item['id']]
        checks=structural_checks(case,item)
        # No citations is not a perfect citation-validity score; mark N/A.
        if not item['answer']['citation_ids']:checks['citations_exist_in_context']=None
        rows.append({'id':item['id'],'difficulty':case['difficulty'],'reference_status':case['review_status'],
                     'actual_status':item['answer']['status'],'checks':checks,
                     'human':human.get(item['id'],{'review_status':'pending','weighted_score':None,'critical_fail':None})})
    def mean(key):
        values=[r['checks'][key] for r in rows if r['checks'].get(key) is not None]
        return {'value':sum(values)/len(values) if values else None,'count':len(values)}
    summary={k:mean(k) for k in ['candidate_hit_at_k','candidate_recall_at_k','citations_exist_in_context','status_matches_draft']}
    summary['human_reviewed_count']=sum(r['human']['review_status']=='completed' for r in rows)
    summary['approved_reference_count']=sum(c['review_status']=='approved' for c in cases)
    return {'run_id':run['run_id'],'review_version':review_version(cases),'rows':rows,'summary':summary,
            'evaluation_type':'deterministic_candidate_metrics_and_human_feedback',
            'limitations':['정답 근거는 미확정 후보이면 공식 검색 정확도가 아니다.',
                           '출처 ID 존재와 답변 주장에 대한 의미적 지지는 다르다.',
                           '문서 밖 질문의 검색 재현율은 N/A다.',
                           '상태 일치는 상태 문자열 비교이며 보류 답변의 의미를 검증하지 않는다.',
                           'RAGAS LLM 지표와 사람 대신 채점하는 평가자는 실행하지 않았다.']}


def feedback_scores(row):
    scores=[]
    for key,value in row['checks'].items():
        if value is None or key=='note':continue
        scores.append({'key':key,'score':float(value),'feedback_source':{'type':'api'},
                       'comment':'코드로 계산한 후보 근거/응답 형식 검사. 사람 검토 전에는 정식 정확도가 아닙니다.'})
    if row['human']['review_status']=='completed':
        scores.extend([{'key':'human_weighted_score','score':row['human']['weighted_score'],
                        'feedback_source':{'type':'api'},'comment':'실제 사람이 입력한 루브릭 점수의 가중 합산'},
                       {'key':'human_critical_fail','score':float(row['human']['critical_fail']),
                        'feedback_source':{'type':'api'},'comment':'실제 사람이 입력한 중대한 오류 여부'}])
    return scores


def make_payload(run,cases,report):
    version=report['review_version']
    rows=[]
    cursor=datetime.fromisoformat(run['created_at'])
    start=cursor
    for item,score in zip(run['items'],report['rows']):
        case=next(c for c in cases if c['id']==item['id'])
        end=cursor+timedelta(seconds=item['latency_seconds'])
        rows.append({'row_id':str(uuid.uuid5(uuid.NAMESPACE_URL,'safepath:'+version+':'+item['id'])),
            'inputs':{'question':item['question']},
            'expected_outputs':{'reference_answer_draft':case['reference_answer'],
                'required_points_draft':case['required_points'],'forbidden_claims_draft':case['forbidden_claims'],
                'evidence_candidates':case['evidence'],'expected_status_draft':case['expected_status'],
                'review_status':case['review_status'],'reference_author':case['reference_author']},
            'actual_outputs':{**item['answer'],'retrieved_contexts':evidence_rows(item['retrieval'])},
            'evaluation_scores':feedback_scores(score),
            'start_time':cursor.isoformat(),'end_time':end.isoformat(),'run_name':item['id'],
            'run_metadata':{'case_id':item['id'],'difficulty':case['difficulty'],'reference_status':case['review_status'],
                'human_review_status':score['human']['review_status'],'original_run_id':run['run_id'],
                'answer_model':run['answer_model'],'usage_recorded':item.get('usage'),
                'timestamp_note':'시작/종료 시각은 원래 실행 시작과 사례별 측정 지연으로 재구성한 추정치',
                'evaluation_note':'답변 재생성/LLM 채점 없음; 원래 저장된 결과를 가져옴'}})
        cursor=end
    return {'experiment_name':'safepath-candidate-'+run['run_id']+'-'+version,
            'dataset_name':'safepath-ko-reference-draft-'+version,
            'dataset_description':'7개 질문과 AI 작성 모범답안 초안. 사람 검토 상태를 반드시 확인하세요.',
            'experiment_description':'기존 PDF RAG 실행 가져오기. 후보 근거와 출처 형식만 코드 평가; 사람 채점 미입력은 대기.',
            'experiment_start_time':start.isoformat(),'experiment_end_time':cursor.isoformat(),
            'experiment_metadata':{'original_run_id':run['run_id'],'review_version':version,
                                  'llm_judge_used':False,'reference_answers_sent_to_generator':False},
            'results':rows}


def connection(env_file):
    values=dotenv_values(env_file)
    def get(name):return os.getenv(name) or values.get(name)
    key=get('LANGSMITH_API_KEY')
    endpoint=get('LANGSMITH_ENDPOINT') or 'https://api.smith.langchain.com'
    if not key:raise ValueError('LangSmith API 키가 없습니다. LANGSMITH_API_KEY를 확인하세요.')
    parsed=urlparse(endpoint)
    if parsed.scheme!='https' or parsed.hostname not in {'api.smith.langchain.com','eu.api.smith.langchain.com'}:
        raise ValueError('등록된 공식 LangSmith HTTPS endpoint인지 확인하세요.')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('endpoint 형식을 확인하세요.')
    return key,endpoint.rstrip('/')


def upload(payload,env_file,receipt_path):
    receipt_path=Path(receipt_path)
    if receipt_path.exists():return read_json(receipt_path)
    pending=receipt_path.with_suffix('.pending.json')
    if pending.exists():raise ValueError('이전 업로드 결과가 미확정입니다. LangSmith에서 확인 후 재시도하세요.')
    key,endpoint=connection(env_file)
    headers={'x-api-key':key}
    # Read-only authentication check before sending source text.
    with httpx.Client(timeout=90,follow_redirects=False) as client:
        check=client.get(endpoint+'/api/v1/datasets',params={'limit':1},headers=headers)
        if check.status_code!=200:raise ValueError(f'LangSmith 인증 확인 실패: HTTP {check.status_code}')
        write_json(pending,{'experiment_name':payload['experiment_name'],'dataset_name':payload['dataset_name'],
                            'requested_at':datetime.now(timezone.utc).isoformat()})
        response=client.post(endpoint+'/api/v1/datasets/upload-experiment',json=payload,headers=headers)
        if response.status_code>=400:
            # Keep uncertain 5xx outcomes pending. For definite 4xx record the code only.
            if 400<=response.status_code<500:pending.unlink()
            error_body = response.json() if 400 <= response.status_code < 500 else {}
            details = error_body.get('detail', error_body.get('error', []))
            locations = [{'loc': d.get('loc'), 'type': d.get('type'), 'msg': d.get('msg')} for d in details if isinstance(d, dict)] if isinstance(details, list) else []
            diagnostic = details.replace(key, '[REDACTED]')[:500] if isinstance(details, str) else json.dumps(details, ensure_ascii=False).replace(key, '[REDACTED]')[:1000]
            raise ValueError(f'LangSmith 업로드 실패: HTTP {response.status_code}. 검증 오류: {diagnostic}; fields={list(error_body)}')
        data=response.json()
    dataset=data['dataset'];experiment=data['experiment']
    host='https://eu.smith.langchain.com' if 'eu.api.' in endpoint else 'https://smith.langchain.com'
    tenant=dataset.get('tenant_id') or experiment.get('tenant_id')
    receipt={'dataset_id':dataset['id'],'experiment_id':experiment['id'],
             'dataset_name':dataset.get('name',payload['dataset_name']),
             'experiment_name':experiment.get('name',payload['experiment_name']),
             'dataset_url':f"{host}/o/{tenant}/datasets/{dataset['id']}" if tenant else host,
             'experiment_url':f"{host}/o/{tenant}/datasets/{dataset['id']}/compare?selectedSessions={experiment['id']}" if tenant else host,
             'uploaded_at':datetime.now(timezone.utc).isoformat(),'row_count':len(payload['results'])}
    write_json(receipt_path,receipt);pending.unlink()
    return receipt


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',required=True)
    parser.add_argument('--upload',action='store_true')
    args=parser.parse_args()
    path=Path(args.run).resolve();run=read_json(path)
    cases=read_json(ROOT/'evaluation/notebook_cases.json')['cases']
    version=review_version(cases)
    report=build_report(run,cases,path.parent/f'human_feedback-{version}.csv')
    payload=make_payload(run,cases,report)
    write_json(path.parent/f'code-evaluation-{version}.json',report)
    write_json(path.parent/f'langsmith-payload-{version}.json',payload)
    print(json.dumps(report['summary'],ensure_ascii=False))
    if args.upload:
        receipt=upload(payload,ROOT/'.env',path.parent/f'langsmith-receipt-{version}.json')
        print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else '처리 실패. 비밀값과 원문 응답은 출력하지 않습니다.'
        print(json.dumps({'error':type(exc).__name__,'detail':message},ensure_ascii=False))
        raise SystemExit(1)
