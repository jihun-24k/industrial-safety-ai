"""Source-span links, not new safety instructions or inferred procedure edges."""
import hashlib
import re

VERSION='document-links-v1'
MANUAL='lab_safety_manual'

def compile_links(pages):
    by={(p['doc_id'],p['pdf_page']):p for p in pages}
    sections=[]
    def add(sid,page,start=None,end=None,doc=MANUAL):
        p=by[(doc,page)];text=p['cleaned_text']
        a=text.index(start) if start else 0
        b=text.index(end,a+1) if end else len(text)
        value=text[a:b].rstrip();b=a+len(value)
        sections.append({'section_id':sid,'chunk_id':hashlib.sha256(f'{VERSION}:{p["source_sha256"]}:{page}:{a}:{b}'.encode()).hexdigest()[:24],
                        'doc_id':doc,'filename':p['filename'],'doc_type':p['doc_type'],'source_sha256':p['source_sha256'],
                        'pdf_page_start':page,'pdf_page_end':page,'source_spans':[{'pdf_page':page,'start':a,'end':b}],
                        'text':value,'content_type':'linked_source_section','review_status':'source_span_verified_application_requires_review',
                        'freshness_status':'unverified','usage':'development_review_only'})
    add('fire_limits',28)
    add('chemical_spill',29,'■ 화학물질 누출시 행동요령','■ 독성가스 누출시 행동요령')
    add('gas_leak_start',29,'■ 독성가스 누출시 행동요령')
    add('gas_leak_continuation',30,None,'■ 안전사고 발생 시 행동요령')
    add('body_contamination',30,'1. 유해','2. 베이거나 찔린 경우')
    add('cut_puncture',30,'2. 베이거나 찔린 경우')
    add('fire_general',31,'1. 화재 발생시','2. 응급환자 발생시')
    add('emergency_patient',31,'2. 응급환자 발생시','3. 비상시를 대비한 확인사항')
    add('emergency_preparation',31,'3. 비상시를 대비한 확인사항')
    add('contact_directory',32)
    add('chemical_rules',39)
    add('waste_manual',44)
    add('waste_law_scope',2,'제3조(적용 범위)','제3조의2',doc='waste_management_act')
    add('waste_law_principles',2,'제3조의2','제4조',doc='waste_management_act')
    routes={
      'spill':['chemical_spill'],
      'body_contamination':['body_contamination','chemical_spill'],
      'gas_leak':['gas_leak_start','gas_leak_continuation'],
      'cut_puncture':['cut_puncture'],
      'fire':['fire_general','fire_limits'],
      'emergency_patient':['emergency_patient'],
      'preparation':['emergency_preparation'],
      'waste':['waste_manual','waste_law_scope','waste_law_principles']}
    edges=[{'from':'fire_general','to':'fire_limits','relation':'read_together_for_restrictions_not_execution_order'},
           {'from':'gas_leak_start','to':'gas_leak_continuation','relation':'explicit_heading_continuation'},
           {'from':'body_contamination','to':'contact_directory','relation':'contact_cross_reference_not_phone_equivalence'},
           {'from':'waste_manual','to':'waste_law_principles','relation':'educational_comparison_not_legal_compliance_determination'}]
    # Whole-corpus topic inventory is only a discovery aid, never automatic applicability.
    terms={'exposure':['오염','흡입','응급','화상'],'fire':['화재','소화','대피'],
           'storage':['보관','저장'],'waste':['폐기물','폐액'],'contacts':['연락','전화','신고'],'equipment':['기계','설비','장치']}
    inventory=[{'doc_id':p['doc_id'],'pdf_page':p['pdf_page'],'topics':[k for k,words in terms.items() if any(w in p['cleaned_text'] for w in words)],'link_status':'keyword_candidate_only'} for p in pages]
    return {'version':VERSION,'sections':sections,'routes':routes,'relations':edges,'page_topic_inventory':inventory,
            'contact_observations':[{'source_section':'body_contamination','organization_raw':'원주세브란스 기독병원','phone_raw':'033-741-0114','current_validity':'unverified'},
                                    {'source_section':'body_contamination','role_raw':'연구실 안전환경관리자','phone_raw':'2796','phone_kind':'구내','equivalence_to_directory_number':'unverified'}],
            'scope':'source-specific links; no automatic conflict resolution, no current legal/medical verification'}


def sections_for(bundle,topics):
    ids=list(dict.fromkeys(sid for topic in topics for sid in bundle['routes'].get(topic,[])))
    lookup={s['section_id']:s for s in bundle['sections']}
    return [lookup[sid] for sid in ids]


def query_topics(question):
    """Retrieval hints only: a mention/negation is not an actual incident fact."""
    hints={'fire':('화재','소화','불이'), 'body_contamination':('신체 오염','피부','눈에','세안','몸에'),
           'gas_leak':('가스 누출','가스누출'), 'spill':('쏟','누출'),
           'cut_puncture':('베이','베였','찔','자상'), 'emergency_patient':('응급환자','구조 요청'),
           'preparation':('비상시 대비','비상 준비'), 'waste':('폐기물','폐액')}
    return [topic for topic,terms in hints.items() if any(t in question for t in terms)]
