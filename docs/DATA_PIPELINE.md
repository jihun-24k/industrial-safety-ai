# SafeOps 한국어 PDF 데이터 파이프라인

## 현재 범위

books/data에 등록된 연구실 안전관리 매뉴얼과 폐기물관리법을 처리한다. 교수 제공 코드의 pypdf, RecursiveCharacterTextSplitter, OpenAIEmbeddings, FAISS를 재사용했다. 원본 파일을 변경하지 않고 문서 해시로 입력 버전을 확인한다. 이 파이프라인은 개발용 추출/색인/검색 도구이며 기존 FastAPI, 인증, 화면과 아직 연결되지 않았다.

## 실행

프로젝트 루트에서 아래 명령을 실행한다. Python 3.11 환경을 기준으로 확인했다. 로컬에는 교수 코드의 `../share/rag-code-template_ext/.venv/bin/python` 환경을 재사용했다. 독립 환경에서는 `pipeline/requirements.txt`를 설치한다. 비밀값 없는 `pipeline/config.json`이 실행 설정이며 로컬 하네스는 실행에 필요하지 않다.

```bash
python -m pipeline.pdf_pipeline prepare
python -m pipeline.pdf_pipeline --env-file /path/to/private.env build
python -m pipeline.pdf_pipeline --env-file /path/to/private.env search '지정폐기물의 정의는 무엇인가요?'
python -m pipeline.smoke_search --env-file /path/to/private.env
python -m unittest discover -s tests -v
```

다른 디렉터리에서는 `python /absolute/path/to/pipeline/pdf_pipeline.py prepare`처럼 파일 경로로 실행해도 같은 입력/출력 경로를 사용한다. 환경변수 OPENAI_API_KEY가 있으면 --env-file을 생략할 수 있다. .env를 복사하지 않고 지정한 파일에서 읽는다. build와 search는 외부 임베딩 API를 호출하며 비용이 발생한다. prepare와 테스트는 외부 API를 호출하지 않는다.

## 단계와 출력

- prepare: 등록 목록, PDF 헤더와 해시 검사 → 페이지별 원문 추출 → 반복 머리말/꼬리말 정제 → 페이지와 조문 경계를 고려한 청킹 → 원문 위치 대조 → 보고서와 미리보기.
- build: 추출 결과의 해시 검증 → 1000자/100자 기준의 청크를 명시적 text-embedding-ada-002 모델로 임베딩 → FAISS와 JSON 문서 저장 → 재로딩 검증 → current.json 교체.
- search: 모델/차원과 파일 무결성 확인 → 한국어 질문 임베딩 → 상위 5개 근거와 문서/페이지/조문/거리 반환. 답변 생성은 수행하지 않는다.

생성 파일은 Git에서 제외한 pipeline_artifacts 아래에 저장된다.

```text
prepared.json                  최근 추출 버전 포인터
prepared/<build_id>/
  pages.jsonl                  모든 페이지의 원문과 정제문, 상태
  chunks.jsonl                 청크와 정확한 페이지 내 위치
  report.json                  집계와 검토 후보
  preview.html                 추출문/정제문 비교 화면
  manifest.json                원본과 출력 해시, 설정, 버전
current.json                   검증된 개발 인덱스 포인터
indexes/<build_id>/
  index.faiss                  벡터
  documents.jsonl              문서 내용과 출처 메타데이터
  manifest.json                모델, 차원, 버전과 파일 해시
```

두 문서를 한 번에 전체 재구축한다. 재실행하면 새 버전이 생성되고 같은 인덱스에 청크를 추가하지 않는다. 임베딩/쓰기/재로딩 실패 전에는 current.json을 바꾸지 않으므로 기존 정상 버전을 유지한다. 남은 이전 버전은 자동 삭제하지 않는다. FAISS 문서 저장소를 JSON으로 복원하므로 pickle 역직렬화를 사용하지 않는다.

## 품질 상태와 제한

모든 청크에 development_review_only와 pending_content_review를 표시한다. 자동 이상 신호가 없다는 것과 안전 내용 검증 완료는 다르다. 실제 서비스 인덱스로 자동 연결하지 않는다.

- 1부터 시작하는 PDF 페이지 번호를 저장한다. 인쇄 페이지는 아직 수동 확정하지 않아 null이다.
- 문자 수가 적거나 이미지가 있는 페이지, 대체문자와 문맥 연속 가능성을 검토 후보로 남긴다. 글자가 적다고 OCR 실패로 확정하지 않는다.
- OCR과 표 구조 복원은 아직 수행하지 않는다. 그림 안의 지침은 누락될 수 있으므로 원문 검토가 필요하다.
- v1은 페이지 경계를 유지한다. 페이지를 넘는 절차/조건의 자동 합치기는 후속 단계다. 긴 조문은 청크로 나뉘지만 조문 메타데이터를 이어 붙인다. 부칙과 인용 조문의 복잡한 구조는 검토가 필요하다.
- 근거 없는 질문에도 벡터 검색은 결과를 반환할 수 있다. 검색 결과 존재만으로 답변 가능 판정을 하지 않는다.
- 거리는 squared L2이며 신뢰 확률이 아니다. 최신 법령 여부와 현장 적용 여부를 검증하지 않는다.
- 긴급 안내, LLM 답변/출처 검증, 20쌍 정답 평가, JWT 및 화면 연동은 후속 작업이다.

## 테스트

외부 호출 없는 테스트로 원문 부정 표현/수치와 청크 위치 보존, 원본 변조와 미등록 입력 차단, 경로 이탈 차단, 실제 로컬 FAISS 저장/재로딩, 모델 불일치, 생성 파일 변조, 재구축 중복 방지, 재로딩 실패 시 포인터 보존을 확인한다. 테스트용 임베딩은 단순 고정 벡터이며 실제 검색 품질의 증거가 아니다.
