"""Evaluate immutable, saved RAG answers using RAGAS. No answer generation."""
import os
os.environ['RAGAS_DO_NOT_TRACK']='true'
os.environ['LANGSMITH_TRACING']='false'
import asyncio, hashlib, json, math, uuid
from datetime import datetime, timezone
from pathlib import Path
from pipeline.retrieval_context import evidence_rows
from pipeline.pdf_pipeline import ROOT, read_json, write_json

POLICY = {
 'version':'safeops-ragas-v3-korean-relevancy', 'ragas_version':'0.4.3',
 'judge_model':'gpt-4o-mini', 'embedding_model':'text-embedding-3-small',
 'judge_max_tokens':8192, 'case_concurrency':4,
 'answer_relevancy_language':'ko', 'answer_relevancy_strictness':3,
 'language_policy':'한국어 질문·답변의 관련성은 한국어 역질문으로 평가한다. 이전 영어 역질문 결과는 별도 보존한다.',
 'reference_policy':'Unreviewed AI reference: precision/recall are provisional, not certified accuracy.',
 'outside_policy':'Outside cases excluded from standard RAG averages; custom RAGAS rubric separately scores abstention.',
 'rubrics':{
  'score1_description':'Invents unsupported exact machine parameters, detailed missing regulations, or definitively certifies US compliance.',
  'score2_description':'Mentions uncertainty but still provides substantial unsupported instructions or legal conclusions.',
  'score3_description':'Avoids a definitive answer but does not clearly identify the missing evidence or scope limitation.',
  'score4_description':'Clearly states evidence is insufficient and avoids unsupported specifics and conclusions.',
  'score5_description':'Clearly states evidence is insufficient, avoids unsupported specifics and conclusions, and identifies what additional authoritative documentation or context is needed.'}}

def configure_korean_relevancy(metric):
 """Use the same Korean question-generation policy in default and diagnostic evaluation."""
 from ragas.metrics.collections.answer_relevancy.util import AnswerRelevanceInput, AnswerRelevanceOutput
 metric.prompt.instruction='주어진 답변으로 답할 수 있는 질문 하나를 반드시 한국어로 생성하세요. 답변이 회피적이거나 모호하면 noncommittal=1, 구체적인 내용을 담으면 0입니다. 원래 질문을 추측해 추가 사실을 만들지 말고 답변 내용에서 질문을 만드세요.'
 metric.prompt.examples=[
  (AnswerRelevanceInput(response='알베르트 아인슈타인은 독일에서 태어났습니다.'),AnswerRelevanceOutput(question='알베르트 아인슈타인은 어디에서 태어났나요?',noncommittal=0)),
  (AnswerRelevanceInput(response='프랑스의 수도는 건축과 문화로 유명한 파리입니다.'),AnswerRelevanceOutput(question='프랑스의 수도는 어디인가요?',noncommittal=0)),
  (AnswerRelevanceInput(response='2022년 이후 정보가 없어 2023년 출시된 스마트폰의 새로운 기능은 모릅니다.'),AnswerRelevanceOutput(question='2023년 출시된 스마트폰의 새로운 기능은 무엇인가요?',noncommittal=1))]
 return metric


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
   'retrieved_contexts':[f"[{r['chunk_id']}] {r['filename']} / PDF {r['pdf_page_start']} / {r['doc_type']}\n{r['text']}" for r in evidence_rows(item['retrieval'])]}

async def evaluate_saved(run,cases,live=False):
 path=report_path(run,cases)
 report=read_json(path) if path.exists() else {'run_id':run['run_id'],'policy':POLICY,'started_at':datetime.now(timezone.utc).isoformat(),'rows':[]}
 if not live:return report if path.exists() else None
 from dotenv import dotenv_values
 from openai import AsyncOpenAI
 from ragas.llms import llm_factory
 from ragas.llms.base import InstructorBaseRagasLLM
 from ragas.embeddings.base import embedding_factory
 from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall, RubricsScoreWithoutReference
 key=dotenv_values(ROOT/'.env').get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
 if not key:raise ValueError('OPENAI_API_KEY missing')
 async with AsyncOpenAI(api_key=key,timeout=90,max_retries=2) as client:
  class TracedLLM(InstructorBaseRagasLLM):
   def __init__(self, delegate):
    self.delegate, self.outputs = delegate, []
   def generate(self, prompt, response_model):
    result=self.delegate.generate(prompt,response_model)
    self.outputs.append({'schema':response_model.__name__,'output':result.model_dump()})
    return result
   async def agenerate(self, prompt, response_model):
    result=await self.delegate.agenerate(prompt,response_model)
    self.outputs.append({'schema':response_model.__name__,'output':result.model_dump()})
    return result
  async def score_case(case, sample):
   llm=TracedLLM(llm_factory(POLICY['judge_model'],client=client,temperature=0,max_tokens=POLICY['judge_max_tokens']))
   emb=embedding_factory('openai',model=POLICY['embedding_model'],client=client)
   metrics={'faithfulness':Faithfulness(llm=llm),'answer_relevancy':configure_korean_relevancy(AnswerRelevancy(llm=llm,embeddings=emb,strictness=POLICY['answer_relevancy_strictness'])),
    'context_precision_draft':ContextPrecision(llm=llm),'context_recall_draft':ContextRecall(llm=llm),
    'abstention_rubric_1_to_5':RubricsScoreWithoutReference(llm=llm,rubrics=POLICY['rubrics'])}
   outside=case['expected_status']=='insufficient_evidence'
   row={'id':case['id'],'group':'outside' if outside else 'answerable',
        'category':case.get('category','outside' if outside else 'document_baseline'),
        'reference_status':case['review_status'],'scores':{},'reasons':{},'details':{}}
   jobs={'abstention_rubric_1_to_5':sample} if outside else {
    'faithfulness':sample,
    'answer_relevancy':{k:sample[k] for k in ['user_input','response']},
    'context_precision_draft':{'user_input':sample['user_input'],'retrieved_contexts':sample['retrieved_contexts'],'reference':case['reference_answer']},
    'context_recall_draft':{'user_input':sample['user_input'],'retrieved_contexts':sample['retrieved_contexts'],'reference':case['reference_answer']}}
   for name,kwargs in jobs.items():
    llm.outputs=[]
    result=await metrics[name].ascore(**kwargs)
    value=float(result.value)
    row['scores'][name]=value if math.isfinite(value) else None
    row['reasons'][name]=result.reason
    row['details'][name]=llm.outputs
    print(case['id'],name,row['scores'][name],flush=True)
   return row
  pending=[(case,sample) for case,sample in samples(run,cases) if not any(r['id']==case['id'] for r in report['rows'])]
  # Independent cases run in bounded batches; each case has isolated judge traces.
  for offset in range(0,len(pending),POLICY['case_concurrency']):
   async def score_and_save(case,sample):
    row=await score_case(case,sample)
    report['rows'].append(row)
    order={case['id']:i for i,case in enumerate(cases)}
    report['rows'].sort(key=lambda r:order[r['id']])
    write_json(path,report)
   async with asyncio.TaskGroup() as group:
    for case,sample in pending[offset:offset+POLICY['case_concurrency']]:
     group.create_task(score_and_save(case,sample))
 report['summary']={}
 for name in ('faithfulness','answer_relevancy','context_precision_draft','context_recall_draft','abstention_rubric_1_to_5'):
  values=[r['scores'][name] for r in report['rows'] if r['scores'].get(name) is not None]
  report['summary'][name]={'mean':sum(values)/len(values) if values else None,'count':len(values)}
 report['by_category']={}
 for category in sorted({r.get('category','uncategorized') for r in report['rows']}):
  subset=[r for r in report['rows'] if r.get('category','uncategorized')==category]
  report['by_category'][category]={}
  for name in ('faithfulness','answer_relevancy','context_precision_draft','context_recall_draft','abstention_rubric_1_to_5'):
   values=[r['scores'][name] for r in subset if r['scores'].get(name) is not None]
   if values:report['by_category'][category][name]={'mean':sum(values)/len(values),'count':len(values)}
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
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--live',action='store_true');p.add_argument('--upload',action='store_true')
 p.add_argument('--cases',default=str(ROOT/'evaluation/notebook_cases.json'));a=p.parse_args()
 run=read_json(Path(a.run));cases=read_json(Path(a.cases))['cases']
 result=asyncio.run(evaluate_saved(run,cases,a.live))
 print(json.dumps(result['summary'] if result else {'status':'not_run'},ensure_ascii=False))
 if a.upload and result:print(json.dumps(publish(run,cases,result),ensure_ascii=False))


async def evaluate_relevance_language(run, cases, live=False):
 """Separate Korean reverse-question diagnostic; never overwrite standard RAGAS scores."""
 policy={'version':'ko-reverse-question-v1','judge':'gpt-4o-mini','embedding':'text-embedding-3-small',
         'strictness':3,'changes':'Korean instruction and translated examples only; saved responses unchanged'}
 fingerprint=hashlib.sha256(json.dumps({'run':run,'policy':policy},ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
 path=ROOT/'pipeline_artifacts/evaluation'/run['run_id']/f'relevance-language-{fingerprint}.json'
 report=read_json(path) if path.exists() else {'run_id':run['run_id'],'policy':policy,'rows':[]}
 if not live:return report if path.exists() else None
 from dotenv import dotenv_values
 from openai import AsyncOpenAI
 from ragas.llms import llm_factory
 from ragas.llms.base import InstructorBaseRagasLLM
 from ragas.embeddings.base import embedding_factory
 from ragas.metrics.collections import AnswerRelevancy
 from ragas.metrics.collections.answer_relevancy.util import AnswerRelevanceInput,AnswerRelevanceOutput
 key=dotenv_values(ROOT/'.env').get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
 if not key:raise ValueError('OPENAI_API_KEY missing')
 async with AsyncOpenAI(api_key=key,timeout=90,max_retries=2) as client:
  async def one(case,sample):
   class Trace(InstructorBaseRagasLLM):
    def __init__(self):
     self.delegate=llm_factory(policy['judge'],client=client,temperature=0,max_tokens=1024)
     self.outputs=[]
    def generate(self,prompt,response_model):
     result=self.delegate.generate(prompt,response_model);self.outputs.append(result.model_dump());return result
    async def agenerate(self,prompt,response_model):
     result=await self.delegate.agenerate(prompt,response_model);self.outputs.append(result.model_dump());return result
   llm=Trace()
   metric=AnswerRelevancy(llm=llm,embeddings=embedding_factory('openai',model=policy['embedding'],client=client),strictness=3)
   configure_korean_relevancy(metric)
   score=await metric.ascore(user_input=sample['user_input'],response=sample['response'])
   report['rows'].append({'id':case['id'],'answer_relevancy_ko':float(score.value),'reverse_questions':llm.outputs})
   write_json(path,report)
   print(case['id'],'answer_relevancy_ko',score.value,flush=True)
  pending=[(c,s) for c,s in samples(run,cases) if c['expected_status']!='insufficient_evidence' and not any(r['id']==c['id'] for r in report['rows'])]
  for offset in range(0,len(pending),4):
   async with asyncio.TaskGroup() as group:
    for c,s in pending[offset:offset+4]:group.create_task(one(c,s))
 report['mean']=sum(r['answer_relevancy_ko'] for r in report['rows'])/len(report['rows']) if report['rows'] else None
 report['completed_at']=datetime.now(timezone.utc).isoformat();write_json(path,report)
 return report
