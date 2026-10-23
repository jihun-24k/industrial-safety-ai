"""Isolated, staged PDF/chunk/retrieval experiments. Never promotes an index."""
from copy import deepcopy
from collections import Counter
import hashlib,json
from pathlib import Path
from pipeline import pdf_pipeline as pp

VARIANTS=[{'name':'baseline_1000_100','chunk_size':1000,'chunk_overlap':100},
          {'name':'small_600_60','chunk_size':600,'chunk_overlap':60},
          {'name':'large_1400_140','chunk_size':1400,'chunk_overlap':140},
          {'name':'overlap_1000_200','chunk_size':1000,'chunk_overlap':200}]

def page_audit(pages):
    rows=[]
    for p in pages:
        flags=p['quality_flags'];text=p['raw_text']
        low='low_text' in flags;image='image_content_requires_review' in flags
        action=('OCR 비교 우선 후보; 표지/빈 페이지 여부 먼저 확인' if low and image else
                '짧은 페이지 원본 확인; OCR 필요 여부 미확정' if low else
                '그림/표 시각 검토; 텍스트 충분해도 이미지 속 설명 누락 가능' if image else
                '텍스트 순서·조건·수치 표본 검토')
        rows.append({'doc_id':p['doc_id'],'pdf_page':p['pdf_page'],'characters':len(text),
                     'image_flag':image,'low_text':low,'action':action})
    return rows

def local_comparison(cfg,pages,cases):
    import tiktoken
    enc=tiktoken.encoding_for_model(cfg['embedding_model'])
    rows=[]
    from pipeline.notebook_evaluation import evidence_hits
    for v in VARIANTS:
        chunks=pp.chunk_pages(pages,{**cfg,**v})
        sizes=sorted(len(c['text']) for c in chunks)
        evidence=[evidence_hits(c,chunks)['candidate_recall_at_k'] for c in cases if c['evidence']]
        original_chars=sum(len(p['cleaned_text']) for p in pages)
        rows.append({**v,'chunks':len(chunks),'median_chars':sizes[len(sizes)//2],
           'max_chars':max(sizes),'embedding_input_tokens':sum(len(enc.encode(c['text'])) for c in chunks),
           'duplicated_character_ratio':sum(sizes)/original_chars,
           'candidate_evidence_containment':sum(evidence)/len(evidence),
           'source_spans_valid':all(p['cleaned_text'][s['start']:s['end']]==c['text']
             for c in chunks for s in c['source_spans'] for p in pages
             if p['doc_id']==c['doc_id'] and p['pdf_page']==s['pdf_page'])})
    return rows

def isolated_config(cfg,pages,variant):
    if variant not in VARIANTS:raise ValueError('Unknown experiment variant')
    base=pp.resolve_pointer(cfg['output_root'],'prepared.json')
    manifest=pp.read_json(base/'manifest.json')
    identity=hashlib.sha256(json.dumps({'source':manifest,'variant':variant,'model':cfg['embedding_model']},sort_keys=True).encode()).hexdigest()[:16]
    out=cfg['output_root']/'tuning'/identity
    exp={**deepcopy(cfg),**variant,'output_root':out}
    prepared=out/'prepared'/'trial';prepared.mkdir(parents=True,exist_ok=True)
    chunks=pp.chunk_pages(pages,exp)
    pp.write_lines(prepared/'pages.jsonl',pages);pp.write_lines(prepared/'chunks.jsonl',chunks)
    report=pp.read_json(base/'report.json')
    report.update(build_id='tuning-'+identity,chunk_count=len(chunks))
    for d in report['documents']:d['chunk_count']=sum(c['doc_id']==d['doc_id'] for c in chunks)
    pp.write_json(prepared/'report.json',report)
    manifest.update(build_id='tuning-'+identity,chunk_count=len(chunks),splitter={**manifest['splitter'],'chunk_size':exp['chunk_size'],'chunk_overlap':exp['chunk_overlap']})
    manifest['files']={n:pp.digest(prepared/n) for n in ['pages.jsonl','chunks.jsonl','report.json']}
    pp.write_json(prepared/'manifest.json',manifest)
    pp.publish_pointer(out,'prepared.json','prepared/trial')
    return exp

async def run_trials(cfg,pages,cases,selected_names,top_ks=(5,),live=False,max_trials=2):
    from pipeline.notebook_evaluation import run_cases
    from pipeline.ragas_evaluation import evaluate_saved,report_path
    selected=[v for name in selected_names for v in VARIANTS if v['name']==name]
    if len(selected)!=len(selected_names) or len(set(selected_names))!=len(selected_names):raise ValueError('Variant names invalid or duplicated')
    if not top_ks or any(not 1<=k<=20 for k in top_ks):raise ValueError('top_k must be 1..20')
    if len(selected)*len(top_ks)>max_trials:raise ValueError('비용 보호: max_trials를 초과했습니다. 실험 수를 줄이거나 한도를 명시적으로 수정하세요.')
    results=[]
    for variant in selected:
        # Baseline uses the exact existing production-development index; no new embedding.
        exp=cfg if variant['name']=='baseline_1000_100' else isolated_config(cfg,pages,variant)
        if not (exp['output_root']/'current.json').exists():
            if not live:
                results.append({'variant':variant['name'],'state':'인덱스 미구축 — RUN_TUNING=True 필요'});continue
            pp.build(exp,pp.embeddings(exp,pp.ROOT/'.env'))
        for k in top_ks:
            questions=[{x:c[x] for x in ['id','question','difficulty']} for c in cases]
            run=run_cases(exp,questions,model='gpt-4o',top_k=k,env_file=pp.ROOT/'.env',run_live=live,use_cache=True)
            if not run:
                results.append({'variant':variant['name'],'top_k':k,'state':'답변 캐시 없음'});continue
            report=await evaluate_saved(run,cases,live=live)
            row={'variant':variant['name'],'top_k':k,'run_id':run['run_id'],'state':'완료' if report and report.get('completed_at') else 'RAGAS 미실행',
                 'mean_context_chars':sum(sum(len(c['text']) for c in item['retrieval']['results']) for item in run['items'])/len(run['items']),
                 'mean_latency_seconds':sum(i['latency_seconds'] for i in run['items'])/len(run['items'])}
            if report:
                row.update({n:v['mean'] for n,v in report.get('summary',{}).items()});row['report']=str(report_path(run,cases))
            results.append(row)
    out=cfg['output_root']/'tuning';out.mkdir(exist_ok=True)
    pp.write_json(out/'last-comparison.json',results)
    return results
