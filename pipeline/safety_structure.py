"""Local review and deterministic contact selection. No calls, reports or LLM requests."""
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
import json

ROOT=Path(__file__).resolve().parent/'structured'
MISSING_REASONS={'not_stated','unreadable','ambiguous','not_applicable','unverified'}

def load(name):
    return json.loads((ROOT/name).read_text())

def classify_time(at, policy=None):
    policy=policy or load('operating_policy.json')
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('Timezone-aware datetime required')
    local=at.astimezone(ZoneInfo(policy['timezone']))
    clock=local.time().replace(tzinfo=None)
    daytime=(local.weekday() in policy['day_weekdays'] and
             time.fromisoformat(policy['day_start'])<=clock<time.fromisoformat(policy['day_end_exclusive']))
    return {'local_time':local.isoformat(),'policy_id':policy['policy_id'],
            'basis':'user_operating_rule_not_document_hours','holiday_handling':'not_applied',
            'period':'daytime' if daytime else 'nighttime',
            'reason':'weekday_time_window' if daytime else 'outside_weekday_daytime_window'}


def select_contacts(role_raw, institution_scope, at, contact_records=None):
    """Exact-role lookup; no automatic role, institution or phone completion."""
    timing=classify_time(at)
    candidates=[]
    for c in (contact_records if contact_records is not None else load('contacts.json')['contacts']):
        if c['institution_scope']!=institution_scope or c['role_raw']!=role_raw:
            continue
        hours=c['availability_normalized']
        eligible=hours=='all_times' or hours==timing['period']
        candidates.append({**c,'time_eligible':eligible,'eligibility_basis':timing,
                           'call_enabled':False,'response_guaranteed':False})
    return {'role':role_raw,'timing':timing,'candidates':candidates,
            'selected':[c for c in candidates if c['time_eligible'] is True],
            'status':'time_eligible_unverified_contacts' if any(c['time_eligible'] is True for c in candidates) else 'needs_contact_confirmation',
            'automatic_fallback_used':False}


def procedure_context(node_id):
    graph=load('procedure.json')
    node=next(n for n in graph['nodes'] if n['node_id']==node_id)
    lane=next(l for l in graph['lanes'] if l['lane_id']==node['lane_id'])
    return {'lane':lane,'nodes':[n for n in graph['nodes'] if n['node_id'] in lane['nodes']],
            'edges':[e for e in graph['edges'] if e['from'] in lane['nodes']],
            'related_contact_candidates':[x for x in load('role_links.json')['links'] if x['node_id']==node_id],
            'contact_link_status':'not_verified_no_automatic_person_mapping',
            'review_status':graph['review_status']}

def validate():
    graph=load('procedure.json'); contacts=load('contacts.json')['contacts']
    nodes={n['node_id']:n for n in graph['nodes']}
    errors=[]
    if len(nodes)!=len(graph['nodes']):errors.append('duplicate node IDs')
    for edge in graph['edges']:
        if edge['from'] not in nodes or edge['to'] not in nodes:errors.append('dangling edge')
        elif nodes[edge['from']]['lane_id']!=nodes[edge['to']]['lane_id']:errors.append('cross lane edge')
    expected={(a,b) for lane in graph['lanes'] for a,b in zip(lane['nodes'],lane['nodes'][1:])}
    if {(e['from'],e['to']) for e in graph['edges']}!=expected:errors.append('missing or invented edge')
    if nodes['center.report1']['evidence']['raw_text']!=nodes['center.report2']['evidence']['raw_text']:errors.append('repeated report modified')
    for nid in ('left.report','right.submit'):
        if '부총장' in nodes[nid]['recipients_raw'] or '부서장' not in nodes[nid]['recipients_raw']:errors.append('recipient changed')
    if any(n['execution_status'] is not None for n in nodes.values()):errors.append('invented execution')
    for c in contacts:
        if not all(isinstance(p,str) for p in c['phone_numbers_raw']):errors.append('non-string phone')
        if c['dialable_numbers'] is not None:errors.append('unverified dialable number')
    return {'passed':not errors,'errors':errors,'node_count':len(nodes),'edge_count':len(graph['edges']),
            'contact_records':len(contacts),'bbox_validation':'pending','semantic_review':'pending_final_review',
            'external_api_called':False,'automatic_calls':False,'active_rag_ingestion':'see_versioned_index_manifest'}

if __name__=='__main__':
    report=validate()
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:raise SystemExit(1)
