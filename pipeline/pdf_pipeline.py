"""Page-preserving PDF preparation and versioned FAISS development indexes.

Run from any directory: python /path/to/pipeline/pdf_pipeline.py prepare
No server startup, automatic ingestion or LLM generation is performed here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VERSION = '2'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_lines(path, rows):
    with Path(path).open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def read_lines(path):
    with Path(path).open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def config_at(path):
    path = Path(path).resolve()
    cfg = read_json(path)
    # Paths are relative to the project, never the caller's working directory.
    project = path.parent.parent
    cfg['input_root'] = (project / cfg['input_directory']).resolve()
    cfg['output_root'] = (project / cfg['output_directory']).resolve()
    if not 0 <= cfg['chunk_overlap'] < cfg['chunk_size']:
        raise ValueError('chunk_overlap must be smaller than chunk_size')
    return cfg


def audit(cfg):
    root = cfg['input_root'].resolve()
    seen_names, seen_ids, seen_hashes = set(), set(), set()
    if not root.is_dir():
        raise ValueError('입력 폴더가 없습니다.')
    for item in cfg['documents']:
        name = item['filename']
        path = root / name
        if Path(name).name != name or path.resolve().parent != root:
            raise ValueError('입력 경로가 허용 폴더 밖입니다.')
        if name in seen_names or item['doc_id'] in seen_ids:
            raise ValueError('등록 이름 또는 ID가 중복됩니다.')
        if not path.is_file():
            raise ValueError(f'입력 파일이 없습니다: {name}')
        with path.open('rb') as f:
            if f.read(5) != b'%PDF-':
                raise ValueError(f'PDF 파일이 아닙니다: {name}')
        value = digest(path)
        if value != item['sha256']:
            raise ValueError(f'원본 해시 변경: {name}')
        if value in seen_hashes:
            raise ValueError('동일 내용의 PDF가 중복됩니다.')
        seen_names.add(name)
        seen_ids.add(item['doc_id'])
        seen_hashes.add(value)
    references = set()
    for item in cfg.get('recognition_references', []):
        name = item['filename']
        path = root / name
        if (Path(name).name != name or path.resolve().parent != root or name in seen_names
                or name in references or item.get('rag_ingest') is not False
                or item.get('purpose') != 'recognition_reference_only'):
            raise ValueError('인식용 참고자료 등록 오류')
        if not path.is_file() or digest(path) != item['sha256']:
            raise ValueError('인식용 참고자료 누락 또는 해시 변경')
        references.add(name)
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.suffix.lower() == '.pdf'}
    if actual != seen_names | references:
        raise ValueError('미등록 PDF가 있습니다. 입력 목록을 검토하세요.')


def clean_page(raw, repeated_edges):
    # Keep line order, numbers, negation and paragraph breaks. No inferred prose.
    lines = raw.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    removable = set(nonempty[:2] + nonempty[-2:])
    removed = []
    output = []
    for i, line in enumerate(lines):
        if i in removable and (line.strip() in repeated_edges or re.fullmatch(r'-\s*\d+\s*-', line.strip()) or re.fullmatch(r'법제처\s+\d+\s+국가법령정보센터', line.strip())):
            removed.append(line.strip())
            continue
        output.append(line.rstrip())
    return '\n'.join(output).strip(), removed


HEADING = re.compile(r'^\s*(?:제\s*\d+\s*조(?:의\d+)?\s*\([^\n]+\)|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[.\s].+|\d+\.\s+[^\n]{2,60})$')
LAW_HEADING = re.compile(r'^\s*제\s*\d+\s*조(?:의\d+)?\s*\([^\n]+?\)')
ARTICLE = re.compile(r'제\s*\d+\s*조(?:의\d+)?')


def chunk_pages(pages, cfg):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=cfg['chunk_size'], chunk_overlap=cfg['chunk_overlap'],
        separators=['\n\n', '\n', '. ', ' ', ''], add_start_index=True, strip_whitespace=False)
    chunks = []
    active_law_heading = {}
    for page in pages:
        text = page['cleaned_text']
        if not text.strip():
            continue
        # Page boundaries are deliberately retained in v1. Continuations are marked
        # for review; no fabricated association across pages or unrelated articles.
        boundaries = [0]
        offset = 0
        for line in text.splitlines(keepends=True):
            if (LAW_HEADING.match(line) if page['doc_type'] == 'law' else HEADING.match(line.rstrip('\n'))) and offset:
                boundaries.append(offset)
            offset += len(line)
        boundaries.append(len(text))
        for begin, end in zip(boundaries, boundaries[1:]):
            block = text[begin:end]
            heading = block.splitlines()[0] if block else ''
            if page['doc_type'] == 'law':
                found = LAW_HEADING.match(heading)
                if found:
                    active_law_heading[page['doc_id']] = found.group().strip()
                heading = active_law_heading.get(page['doc_id'])
            else:
                heading = heading if HEADING.match(heading) else None
            article = ARTICLE.search(heading or '')
            for doc in splitter.create_documents([block]):
                value = doc.page_content
                if not value.strip():
                    continue
                start = begin + doc.metadata['start_index']
                stop = start + len(value)
                if start < begin or text[start:stop] != value:
                    raise ValueError('청크 원문 위치 검증에 실패했습니다.')
                identity = f"{page['source_sha256']}:{VERSION}:{cfg['chunk_size']}:{cfg['chunk_overlap']}:{page['pdf_page']}:{start}:{stop}"
                chunks.append({
                    'chunk_id': hashlib.sha256(identity.encode()).hexdigest()[:24],
                    'doc_id': page['doc_id'], 'filename': page['filename'],
                    'source_sha256': page['source_sha256'], 'doc_type': page['doc_type'],
                    'effective_date': page['effective_date'], 'freshness_status': 'unverified',
                    'language': 'ko', 'pdf_page_start': page['pdf_page'], 'pdf_page_end': page['pdf_page'],
                    'printed_page': None, 'section_title': heading,
                    'article_number': article.group() if article else None,
                    'source_spans': [{'pdf_page': page['pdf_page'], 'start': start, 'end': stop}],
                    'text': value, 'review_status': 'pending_content_review',
                    'quality_flags': page['quality_flags'], 'usage': 'development_review_only',
                })
    if len({x['chunk_id'] for x in chunks}) != len(chunks):
        raise ValueError('청크 ID 중복')
    return chunks


def preview(path, pages, report):
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>PDF 추출 검토</title>',
        '<style>body{max-width:1100px;margin:40px auto;font-family:sans-serif;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:16px}summary{cursor:pointer;padding:12px} .flag{color:#9b3800}</style>',
        '<h1>PDF 추출 검토</h1><p>개발 검토용. 원문 의미, 표와 그림, 최신성은 아직 검증되지 않았습니다.</p>',
        '<pre>' + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre>']
    for page in pages:
        label = f"{page['filename']} | PDF {page['pdf_page']}쪽 | {', '.join(page['quality_flags']) or '자동 이상 신호 없음'}"
        parts += ['<details><summary>' + html.escape(label) + '</summary>',
                  '<h3>추출 원문</h3><pre>' + html.escape(page['raw_text']) + '</pre>',
                  '<h3>정제문</h3><pre>' + html.escape(page['cleaned_text']) + '</pre></details>']
    Path(path).write_text('\n'.join(parts) + '</html>', encoding='utf-8')


def publish_pointer(root, name, relative):
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f'.{name}.{uuid.uuid4().hex}.tmp'
    write_json(temporary, {'path': relative})
    os.replace(temporary, root / name)


def resolve_pointer(root, name):
    path = (root / read_json(root / name)['path']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('저장 경로가 출력 폴더 밖입니다.')
    return path


def verify_files(directory, manifest):
    for name, expected in manifest['files'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest(path) != expected:
            raise ValueError('생성 파일 무결성 검사 실패')


def prepare(cfg):
    from pypdf import PdfReader
    try:
        from .reviewed_pictograms import reviewed_chunks
    except ImportError:
        from reviewed_pictograms import reviewed_chunks
    audit(cfg)
    supplements = reviewed_chunks(cfg)
    try:
        from .structured_ingestion import make_chunks, material_catalog
        from .document_links import compile_links
        from .knowledge_graph import compile_graph
        from .safety_structure import load as load_structure
    except ImportError:
        from structured_ingestion import make_chunks, material_catalog
        from document_links import compile_links
        from pipeline.knowledge_graph import compile_graph
        from pipeline.safety_structure import load as load_structure
    structured_chunks, structure = make_chunks(cfg)
    pages = []
    for item in cfg['documents']:
        reader = PdfReader(cfg['input_root'] / item['filename'])
        extracted = []
        for n, page in enumerate(reader.pages, 1):
            flags = []
            try:
                raw = page.extract_text() or ''
                status = 'extracted'
            except Exception as exc:
                raw = ''
                status = 'failed'
                flags.append('extraction_error:' + type(exc).__name__)
            if len(raw.strip()) < 80:
                flags.append('low_text')
            if '\ufffd' in raw:
                flags.append('replacement_character')
            try:
                xobjects = page.get('/Resources', {}).get('/XObject', {})
                if hasattr(xobjects, 'get_object'):
                    xobjects = xobjects.get_object()
                if any(obj.get_object().get('/Subtype') == '/Image' for obj in xobjects.values()):
                    flags.append('image_content_requires_review')
            except Exception:
                flags.append('image_detection_incomplete')
            extracted.append((n, raw, status, flags))
        counts = Counter()
        for _, raw, _, _ in extracted:
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            counts.update(set(lines[:2] + lines[-2:]))
        # Remove only short recurring edges; legal article/heading lines survive.
        repeated = {line for line, count in counts.items() if count >= max(3, len(extracted) * .6)
                    and len(line) <= 120 and not ARTICLE.search(line) and not HEADING.match(line)}
        for n, raw, status, flags in extracted:
            cleaned, removed = clean_page(raw, repeated)
            if cleaned and not re.search(r'[.!?。다요]\s*$', cleaned):
                flags.append('possible_page_continuation')
            pages.append({'doc_id': item['doc_id'], 'filename': item['filename'], 'doc_type': item['doc_type'],
                'source_sha256': item['sha256'], 'effective_date': item.get('effective_date'),
                'pdf_page': n, 'printed_page': None, 'raw_text': raw, 'cleaned_text': cleaned,
                'extraction_method': 'pypdf', 'extraction_status': status if status == 'failed' else ('review_required' if flags else 'extracted'),
                'quality_flags': flags, 'removed_edges': removed, 'review_status': 'pending_content_review'})
    chunks = chunk_pages(pages, cfg)
    chunks.extend(supplements)
    chunks.extend(structured_chunks)
    if not chunks:
        raise ValueError('추출된 청크가 없습니다.')
    build_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    folder = cfg['output_root'] / 'prepared' / build_id
    folder.mkdir(parents=True)
    write_lines(folder / 'pages.jsonl', pages)
    catalog = material_catalog(pages)
    links = compile_links(pages)
    policy = load_structure('operating_policy.json')
    graph = compile_graph(chunks, catalog, structure, links, policy)
    write_json(folder / 'material_catalog.json', catalog)
    write_json(folder / 'document_links.json', links)
    write_json(folder / 'operating_policy.json', policy)
    write_json(folder / 'knowledge_graph.json', graph)
    write_json(folder / 'structure_snapshot.json', structure)
    write_lines(folder / 'chunks.jsonl', chunks)
    documents = []
    for item in cfg['documents']:
        pp = [p for p in pages if p['doc_id'] == item['doc_id']]
        cc = [c for c in chunks if c['doc_id'] == item['doc_id']]
        documents.append({**item, 'page_count': len(pp), 'chunk_count': len(cc),
            'raw_characters': sum(len(p['raw_text']) for p in pp),
            'cleaned_characters': sum(len(p['cleaned_text']) for p in pp),
            'status_counts': dict(Counter(p['extraction_status'] for p in pp)),
            'flagged_pages': [{'page': p['pdf_page'], 'flags': p['quality_flags']} for p in pp if p['quality_flags']]})
    report = {'build_id': build_id, 'usage': 'development_review_only', 'documents': documents,
              'page_count': len(pages), 'chunk_count': len(chunks), 'external_api_called': False,
              'reviewed_pictogram_supplement_count': len(supplements),
              'structured_safety_supplement_count': len(structured_chunks),
              'excluded_empty_pages': [f"{p['doc_id']}:{p['pdf_page']}" for p in pages if not p['cleaned_text'].strip()],
              'limitations': ['OCR 미실행', '표/그림 의미와 최신성 미검증', '페이지 간 문맥 병합 미구현', '전체 내용 전문검토 전']}
    write_json(folder / 'report.json', report)
    preview(folder / 'preview.html', pages, report)
    manifest = {'build_id': build_id, 'pipeline_version': VERSION,
        'graph_version': graph['version'], 'graph_statistics': graph['statistics'],
        'reviewed_pictograms_sha256': cfg.get('reviewed_pictograms_sha256'),
        'structured_safety_sha256': cfg.get('structured_safety_sha256'),
        'created_at': datetime.now(timezone.utc).isoformat(), 'usage': 'development_review_only',
        'source_hashes': {x['doc_id']: x['sha256'] for x in cfg['documents']},
        'splitter': {'chunk_size': cfg['chunk_size'], 'chunk_overlap': cfg['chunk_overlap'], 'unit': 'characters', 'page_boundaries': 'preserved'},
        'chunk_count': len(chunks), 'page_count': len(pages),
        'library_versions': {n: importlib.metadata.version(n) for n in ['pypdf', 'langchain-text-splitters']},
        'files': {name: digest(folder / name) for name in ['pages.jsonl', 'chunks.jsonl', 'report.json', 'material_catalog.json', 'structure_snapshot.json', 'document_links.json', 'knowledge_graph.json', 'operating_policy.json']}}
    write_json(folder / 'manifest.json', manifest)
    publish_pointer(cfg['output_root'], 'prepared.json', str(folder.relative_to(cfg['output_root'])))
    return {'prepared_path': str(folder), 'pages': len(pages), 'chunks': len(chunks),
            'graph': graph['statistics'], 'usage': report['usage']}


def embeddings(cfg, env_file=None):
    from dotenv import load_dotenv
    from langchain_openai import OpenAIEmbeddings
    if env_file:
        load_dotenv(Path(env_file).resolve(), override=False)
    if not os.getenv('OPENAI_API_KEY'):
        raise ValueError('OPENAI_API_KEY가 없습니다. 환경변수 또는 --env-file을 지정하세요.')
    return OpenAIEmbeddings(model=cfg['embedding_model'], max_retries=2, request_timeout=60, chunk_size=64)


def load_index(folder, embedder, model, dimension):
    import faiss
    from langchain_community.docstore.in_memory import InMemoryDocstore
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    manifest = read_json(folder / 'manifest.json')
    if manifest['embedding_model'] != model or manifest['vector_dimension'] != dimension:
        raise ValueError('임베딩 모델 또는 차원이 인덱스와 다릅니다.')
    verify_files(folder, manifest)
    rows = read_lines(folder / 'documents.jsonl')
    index = faiss.read_index(str(folder / 'index.faiss'))
    if index.d != dimension or index.ntotal != len(rows):
        raise ValueError('벡터 수/차원 검증 실패')
    docs = {x['chunk_id']: Document(page_content=x['text'], metadata={k:v for k,v in x.items() if k != 'text'}) for x in rows}
    if len(docs) != len(rows):
        raise ValueError('청크 ID 중복')
    return FAISS(embedder, index, InMemoryDocstore(docs), {i:row['chunk_id'] for i,row in enumerate(rows)})


def build(cfg, embedder):
    import faiss
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    audit(cfg)
    prepared = resolve_pointer(cfg['output_root'], 'prepared.json')
    pm = read_json(prepared / 'manifest.json')
    verify_files(prepared, pm)
    if pm['source_hashes'] != {x['doc_id']:x['sha256'] for x in cfg['documents']}:
        raise ValueError('추출 버전과 현재 원본이 다릅니다. prepare를 다시 실행하세요.')
    if (pm['splitter']['chunk_size'], pm['splitter']['chunk_overlap']) != (cfg['chunk_size'], cfg['chunk_overlap']):
        raise ValueError('분할 설정 변경: prepare를 다시 실행하세요.')
    rows = read_lines(prepared / 'chunks.jsonl')
    if pm.get('reviewed_pictograms_sha256') != cfg.get('reviewed_pictograms_sha256'):
        raise ValueError('그림 검토 기록 변경: prepare를 다시 실행하세요.')
    if pm.get('structured_safety_sha256') != cfg.get('structured_safety_sha256'):
        raise ValueError('Structured safety data changed; prepare again')
    report = read_json(prepared / 'report.json')
    if any(d['status_counts'].get('failed', 0) for d in report['documents']):
        raise ValueError('추출 실패 페이지를 해결한 뒤 구축하세요.')
    # Reuse verified vectors for unchanged text; send only new text for embedding.
    cached = {}
    reused_from = None
    if (cfg['output_root'] / 'current.json').exists():
        previous = resolve_pointer(cfg['output_root'], 'current.json')
        old_manifest = read_json(previous / 'manifest.json')
        if (old_manifest['embedding_model'] == cfg['embedding_model']
                and old_manifest['vector_dimension'] == cfg['embedding_dimension']):
            old_store = load_index(previous, embedder, cfg['embedding_model'], cfg['embedding_dimension'])
            for i, old in enumerate(read_lines(previous / 'documents.jsonl')):
                cached[old['text']] = old_store.index.reconstruct(i).tolist()
            reused_from = old_manifest['build_id']
    missing = list(dict.fromkeys(row['text'] for row in rows if row['text'] not in cached))
    if missing:
        vectors = embedder.embed_documents(missing)
        if len(vectors) != len(missing):
            raise ValueError('임베딩 결과 개수가 다릅니다.')
        cached.update(zip(missing, vectors))
    store = FAISS.from_embeddings([(x['text'], cached[x['text']]) for x in rows], embedder,
        metadatas=[{k:v for k,v in x.items() if k != 'text'} for x in rows], ids=[x['chunk_id'] for x in rows])
    if store.index.d != cfg['embedding_dimension']:
        raise ValueError('설정과 실제 임베딩 차원이 다릅니다.')
    build_id = pm['build_id'] + '-' + uuid.uuid4().hex[:8]
    folder = cfg['output_root'] / 'indexes' / build_id
    folder.mkdir(parents=True)
    # JSON docstore avoids loading a pickle file from an untrusted upload.
    faiss.write_index(store.index, str(folder / 'index.faiss'))
    write_lines(folder / 'documents.jsonl', rows)
    extra_files=[]
    for name in ('material_catalog.json','structure_snapshot.json','document_links.json',
                 'knowledge_graph.json','operating_policy.json'):
        if (prepared/name).exists():
            (folder/name).write_bytes((prepared/name).read_bytes())
            extra_files.append(name)
    manifest = {**pm, 'build_id': build_id, 'prepared_build_id': pm['build_id'],
        'embedding_new_text_count': len(missing), 'vectors_reused_from': reused_from,
        'created_at': datetime.now(timezone.utc).isoformat(), 'embedding_model': cfg['embedding_model'],
        'vector_dimension': store.index.d, 'distance_metric': 'squared_L2', 'normalization': 'provider_output',
        'validation_status': 'structural_checks_passed_content_review_pending',
        'library_versions': {**pm['library_versions'], **{n:importlib.metadata.version(n) for n in ['langchain-community', 'langchain-openai', 'faiss-cpu']}},
        'files': {name:digest(folder / name) for name in ['index.faiss', 'documents.jsonl']+extra_files}}
    write_json(folder / 'manifest.json', manifest)
    load_index(folder, embedder, cfg['embedding_model'], cfg['embedding_dimension'])
    # Atomic pointer replacement, only after complete write and reload validation.
    publish_pointer(cfg['output_root'], 'current.json', str(folder.relative_to(cfg['output_root'])))
    return {'index_path': str(folder), 'chunks': len(rows), 'dimension': store.index.d, 'usage': 'development_review_only'}


def graph_search(cfg, question, *, institution_scope=None, accident_classification=None, at=None):
    """Graph-only query against the current index; no embedding API call."""
    from pipeline.knowledge_graph import graph_from_folder, retrieve
    options = cfg.get('graph', {})
    if not options.get('enabled', True):
        return {'enabled': False, 'results': []}
    folder = resolve_pointer(cfg['output_root'], 'current.json')
    return retrieve(graph_from_folder(folder), question,
                    max_hops=options.get('max_hops', 5), max_results=options.get('max_results', 24),
                    institution_scope=institution_scope, accident_classification=accident_classification, at=at)


def search(cfg, embedder, question, k, *, include_graph=True, material_filter=True):
    if not question.strip() or not 1 <= k <= 20:
        raise ValueError('질문과 top-k(1~20)를 확인하세요.')
    folder = resolve_pointer(cfg['output_root'], 'current.json')
    store = load_index(folder, embedder, cfg['embedding_model'], cfg['embedding_dimension'])
    try:
        from .structured_ingestion import match_materials
    except ImportError:
        from structured_ingestion import match_materials
    catalog=read_json(folder/'material_catalog.json') if (folder/'material_catalog.json').exists() else []
    materials=match_materials(question,catalog)
    kwargs={}
    if material_filter and len(materials)==1:
        target=materials[0]['pdf_page']
        kwargs={'filter':lambda m: m.get('doc_id')=='lab_safety_manual' and m.get('pdf_page_start')==target,
                'fetch_k':store.index.ntotal}
    found=store.similarity_search_with_score(question,k=k,**kwargs)
    base_rows=[{'distance':float(score),'text':doc.page_content,**doc.metadata} for doc,score in found]
    links_path=folder/'document_links.json'
    topic_rows=[]
    if links_path.exists():
        try:
            from .document_links import query_topics, sections_for
        except ImportError:
            from document_links import query_topics, sections_for
        topic_rows=[{**r,'distance':None,'retrieval_reason':'query_topic_candidate_not_incident_fact'}
                    for r in sections_for(read_json(links_path),query_topics(question))]
    # Keep native semantic ranking in results; linked source passages are a separate evidence set.
    # This preserves the meaning of vector top-k and never drops mandatory restrictions.

    graph = graph_search(cfg, question) if include_graph else {'enabled': False, 'results': []}
    return {'question': question, 'usage': 'development_review_only', 'score_meaning': 'squared_L2_not_confidence',
            'material_matches':materials,'material_filter_applied':material_filter and len(materials)==1,
            'graph_results': graph['results'], 'graph_retrieval': {key: value for key, value in graph.items() if key != 'results'},
            'linked_results':topic_rows,
            'results': [{'rank': i, 'distance': float(score), 'text': doc.page_content, **doc.metadata}
                        for i, (doc, score) in enumerate(found, 1)]}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'pipeline/config.json'))
    parser.add_argument('--env-file', help='기존 .env를 읽기 전용으로 사용하며 값을 출력하지 않습니다.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    sub.add_parser('build')
    query = sub.add_parser('search')
    query.add_argument('question')
    query.add_argument('--top-k', type=int, default=5)
    args = parser.parse_args()
    try:
        cfg = config_at(args.config)
        if args.command == 'prepare':
            result = prepare(cfg)
        else:
            embedder = embeddings(cfg, args.env_file)
            result = build(cfg, embedder) if args.command == 'build' else search(cfg, embedder, args.question, args.top_k)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Provider exception bodies may contain request contents. Do not echo them.
        detail = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else '외부 호출 또는 처리 실패. 키 값과 요청 본문은 출력하지 않습니다.'
        print(json.dumps({'error': type(exc).__name__, 'detail': detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
