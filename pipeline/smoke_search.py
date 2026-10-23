"""Small retrieval smoke check; not the assignment's grounded 20-case evaluation."""
import argparse
import json
from pathlib import Path
from pipeline.pdf_pipeline import ROOT, config_at, embeddings, search, write_json, resolve_pointer

CASES = [
    {'question':'제공된 폐기물관리법에서 지정폐기물의 정의는 무엇인가요?',
     'doc_id':'waste_management_act', 'page':1, 'required_text':'4. “지정폐기물”'},
    {'question':'연구실 매뉴얼의 기계 공통 안전수칙에서 기계를 점검하거나 수리할 때의 조건은 무엇인가요?',
     'doc_id':'lab_safety_manual', 'page':45, 'required_text':'기계를 정지시킨 상태'},
    {'question':'연구실 배기후드와 환기설비의 점검사항은 무엇인가요?',
     'doc_id':'lab_safety_manual', 'page':47, 'required_text':'환기설비의 점검사항'},
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file')
    args=parser.parse_args()
    cfg=config_at(ROOT/'pipeline/config.json')
    embedder=embeddings(cfg,args.env_file)
    results=[]
    for case in CASES:
        output=search(cfg,embedder,case['question'],5)
        matches=[r['rank'] for r in output['results'] if r['doc_id']==case['doc_id']
                 and r['pdf_page_start']<=case['page']<=r['pdf_page_end'] and case['required_text'] in r['text']]
        results.append({'expected':case,'hit_at_5':bool(matches),'matching_ranks':matches, 'retrieval':output})
    report={'kind':'retrieval_smoke_not_full_evaluation','index_path':str(resolve_pointer(cfg['output_root'],'current.json')),
            'cases':results,'passed':sum(x['hit_at_5'] for x in results),'total':len(results),
            'limitations':['3개 원문 구간의 검색 동작만 확인','LLM 답변과 안전성 미평가','문서 밖 질문 판정 미구현']}
    write_json(cfg['output_root']/'retrieval-smoke.json',report)
    print(json.dumps({'passed':report['passed'],'total':report['total'],
                      'ranks':[x['matching_ranks'] for x in results]},ensure_ascii=False))
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__, 'detail':'검색 점검 실패. API 키와 요청 내용은 출력하지 않습니다.'},ensure_ascii=False))
        raise SystemExit(1)
