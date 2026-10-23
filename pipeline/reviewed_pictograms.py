"""Build source-linked supplements from explicitly approved pictograms only."""
import hashlib
import json
from pathlib import Path


def reviewed_chunks(cfg):
    expected = cfg.get('reviewed_pictograms_sha256')
    if not expected:
        return []
    root = Path(__file__).resolve().parent
    raw = (root / 'reviewed_pictograms.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('그림 검토 기록 변경: 승인된 버전을 확인하세요.')
    review = json.loads(raw)
    dictionary = (root / 'ghs_dictionary.json').read_bytes()
    if hashlib.sha256(dictionary).hexdigest() != review['dictionary_sha256']:
        raise ValueError('GHS 사전 변경: 매핑을 재검토하세요.')
    symbols = {s['symbol']: s for s in json.loads(dictionary)['symbols']}
    source = next(d for d in cfg['documents'] if d['doc_id'] == review['doc_id'])
    if source['sha256'] != review['source_sha256']:
        raise ValueError('그림 검토 기록과 PDF 버전이 다릅니다.')
    rows = []
    for page in review['pages']:
        if page['review_status'] != 'user_confirmed' or page['review_scope'] != 'pictogram_identity_count_order_only':
            raise ValueError('승인되지 않은 그림 검토 기록입니다.')
        lines = [f"{source['filename']} PDF {page['pdf_page']}쪽 (인쇄 {page['printed_page']}쪽)",
                 f"{page['substance']} 유해 그림문자: {len(page['icons'])}개, 왼쪽부터 다음 순서."]
        for i, icon in enumerate(page['icons']):
            s = symbols[icon['symbol']]
            if (icon['region_id'] != i or icon['canonical_code'] != s['code']
                    or icon['source_legend_label'] != s['source_legend_label']):
                raise ValueError('그림 순서 또는 GHS 코드 매핑 불일치')
            lines.append(f"영역 {i}: {s['name_ko']} 그림. 매뉴얼 105쪽 범례 번호 {icon['source_legend_label']}, 공식 GHS 코드 {icon['canonical_code']}.")
        lines.append('매뉴얼 범례 번호와 공식 코드는 구분한다. 이 보충자료는 원문 그림의 종류, 개수, 순서에 대한 사용자 확인 기록이다. 물질의 세부 위험등급이나 최신 SDS 분류를 확정하지 않는다.')
        text = '\n'.join(lines)
        rows.append(dict(chunk_id=hashlib.sha256(f"{expected}:{page['pdf_page']}:{text}".encode()).hexdigest()[:24],
            doc_id=source['doc_id'], filename=source['filename'], source_sha256=source['sha256'],
            doc_type=source['doc_type'], effective_date=None, freshness_status='unverified', language='ko',
            pdf_page_start=page['pdf_page'], pdf_page_end=page['pdf_page'], printed_page=page['printed_page'],
            section_title='사용자 검토 완료 유해 그림문자', article_number=None, source_spans=[],
            text=text, review_status='user_confirmed_pictograms_only', quality_flags=[],
            usage='development_review_only', content_type='reviewed_pictogram_supplement',
            review_sha256=expected, dictionary_sha256=review['dictionary_sha256'],
            review_scope=page['review_scope'], icons=page['icons'], vision_response_id=page['response_id']))
    return rows
