"""Evaluate immutable, saved RAG answers using RAGAS. No answer generation."""
import os
os.environ['RAGAS_DO_NOT_TRACK']='true'
os.environ['LANGSMITH_TRACING']='false'
import asyncio, hashlib, json, math, uuid
from datetime import datetime, timezone
from pathlib import Path
from pipeline.pdf_pipeline import ROOT, read_json, write_json

POLICY = {
 'version':'safeops-ragas-v1', 'ragas_version':'0.4.3',
 'judge_model':'gpt-4o-mini', 'embedding_model':'text-embedding-3-small',
 'reference_policy':'Unreviewed AI reference: precision/recall are provisional, not certified accuracy.',
 'outside_policy':'Outside cases excluded from standard RAG averages; custom RAGAS rubric separately scores abstention.',
 'rubrics':{
  'score1_description':'Invents unsupported exact machine parameters, detailed missing regulations, or definitively certifies US compliance.',
  'score2_description':'Mentions uncertainty but still provides substantial unsupported instructions or legal conclusions.',
  'score3_description':'Avoids a definitive answer but does not clearly identify the missing evidence or scope limitation.',
  'score4_description':'Clearly states evidence is insufficient and avoids unsupported specifics and conclusions.',
  'score5_description':'Clearly states evidence is insufficient, avoids unsupported specifics and conclusions, and identifies what additional authoritative documentation or context is needed.'}}

def report_path(run,cases):
 fingerprint=hashlib.sha256(json.dumps({'run':run,'cases':cases,'policy':POLICY},ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
 return ROOT/'pipeline_artifacts/evaluation'/run['run_id']/f'ragas-{fingerprint}.json'

def samples(run,cases):
 mapping={c['id']:c for c in cases}
 if set(mapping)!={i['id'] for i in run['items']}:raise ValueError('Case IDs differ')
 for item in run['items']:
  c=mapping[item['id']]
  if c['question']!=item['question']:raise ValueError('Question differs')
  yield c, {'user_input':item['question'],'response':item['answer']['answer'],
   'retrieved_contexts':[f"[{r['chunk_id']}] {r['filename']} / PDF {r['pdf_page_start']} / {r['doc_type']}\n{r['text']}" for r in item['retrieval']['results']+item['retrieval'].get('linked_results',[])]}

async def evaluate_saved(run,cases,live=False):
 path=report_path(run,cases)
 report=read_json(path) if path.exists() else {'run_id':run['run_id'],'policy':POLICY,'started_at':datetime.now(timezone.utc).isoformat(),'rows':[]}
 if not live:return report if path.exists() else None
 from dotenv import dotenv_values
 from openai import AsyncOpenAI
 from ragas.llms import llm_factory
 from ragas.embeddings.base import embedding_factory
 from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall, RubricsScoreWithoutReference
 key=dotenv_values(ROOT/'.env').get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
 if not key:raise ValueError('OPENAI_API_KEY missing')
 async with AsyncOpenAI(api_key=key,timeout=90,max_retries=2) as client:
  llm=llm_factory(POLICY['judge_model'],client=client,temperature=0)
  emb=embedding_factory('openai',model=POLICY['embedding_model'],client=client)
  metrics={'faithfulness':Faithfulness(llm=llm),'answer_relevancy':AnswerRelevancy(llm=llm,embeddings=emb),
   'context_precision_draft':ContextPrecision(llm=llm),'context_recall_draft':ContextRecall(llm=llm),
   'abstention_rubric_1_to_5':RubricsScoreWithoutReference(llm=llm,rubrics=POLICY['rubrics'])}
  for case,sample in samples(run,cases):
   if any(r['id']==case['id'] for r in report['rows']):continue
   outside=case['expected_status']=='insufficient_evidence'
   row={'id':case['id'],'group':'outside' if outside else 'answerable','reference_status':case['review_status'],'scores':{},'reasons':{}}
   jobs={'abstention_rubric_1_to_5':sample} if outside else {
    'faithfulness':sample,
    'answer_relevancy':{k:sample[k] for k in ['user_input','response']},
    'context_precision_draft':{'user_input':sample['user_input'],'retrieved_contexts':sample['retrieved_contexts'],'reference':case['reference_answer']},
    'context_recall_draft':{'user_input':sample['user_input'],'retrieved_contexts':sample['retrieved_contexts'],'reference':case['reference_answer']}}
   for name,kwargs in jobs.items():
    result=await metrics[name].ascore(**kwargs)
    value=float(result.value)
    row['scores'][name]=value if math.isfinite(value) else None
    row['reasons'][name]=result.reason
    print(case['id'],name,row['scores'][name],flush=True)
   report['rows'].append(row);write_json(path,report)
 report['summary']={}
 for name in metrics:
  values=[r['scores'][name] for r in report['rows'] if r['scores'].get(name) is not None]
  report['summary'][name]={'mean':sum(values)/len(values) if values else None,'count':len(values)}
 report['completed_at']=datetime.now(timezone.utc).isoformat();write_json(path,report)
 return report

def publish(run,cases,report):
 from pipeline.langsmith_evaluation import build_report,make_payload,upload
 payload=make_payload(run,cases,build_report(run,cases))
 payload['experiment_name']='safeops-'+report_path(run,cases).stem+'-'+run['run_id']
 payload['dataset_name']='safeops-ragas-reference-draft-'+report['run_id']+'-'+report_path(run,cases).stem
 payload['experiment_description']='RAGAS 0.4.3 LLM evaluation of saved answers. Draft-reference precision/recall provisional; outside rubric separate.'
 payload['experiment_metadata'].update(llm_judge_used=True,ragas_policy=POLICY)
 by_id={r['id']:r for r in report['rows']}
 for item in payload['results']:
  row=by_id[item['run_name']]
  item['row_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,payload['dataset_name']+':'+item['run_name']))
  item['evaluation_scores']=[{'key':'ragas_'+k,'score':round(v,4),'feedback_source':{'type':'api'},'comment':row['reasons'].get(k) or 'RAGAS LLM judge; draft references provisional.'} for k,v in row['scores'].items() if v is not None]
  item['run_metadata']['evaluation_note']='RAGAS LLM judge, saved answer unchanged'
  for score in item['evaluation_scores']:
   outside=score['key']=='ragas_abstention_rubric_1_to_5'
   score['feedback_config']={'type':'continuous','min':1 if outside else (-1 if score['key']=='ragas_answer_relevancy' else 0),'max':5 if outside else 1}
 return upload(payload,ROOT/'.env',report_path(run,cases).with_suffix('.receipt.json'))

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--live',action='store_true');p.add_argument('--upload',action='store_true');a=p.parse_args()
 run=read_json(Path(a.run));cases=read_json(ROOT/'evaluation/notebook_cases.json')['cases']
 result=asyncio.run(evaluate_saved(run,cases,a.live))
 print(json.dumps(result['summary'] if result else {'status':'not_run'},ensure_ascii=False))
 if a.upload and result:print(json.dumps(publish(run,cases,result),ensure_ascii=False))
