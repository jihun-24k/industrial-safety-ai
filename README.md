# SafeOps · industrial-safety-ai

## 1. 프로젝트 소개

SafeOps는 산업안전 문서에서 근거를 검색해 물질의 위험성, 사고 대응 절차, 보고 경로와 연락처를 안내하는 다국어 질의응답 서비스입니다.

- **근거 기반 검색:** 한국어 PDF를 추출·청킹하고 FAISS 의미 검색과 최대 5단계의 관계 그래프 탐색을 결합합니다. 물질·사고·절차·기관·연락처의 연결 근거를 답변에 제공합니다.
- **다국어 입력:** 외국어 텍스트나 음성 인식 결과를 한국어로 번역한 뒤 대화 맥락 연결, 사고 판단, 물질명 보정과 RAG 검색에 사용합니다. 입력 원문과 한국어 처리용 질문은 분리 저장합니다.
- **음성 대화:** 로컬 Whisper로 음성을 인식하고, 답변은 한국어·영어·중국어·일본어·베트남어로 번역해 TTS로 재생합니다.
- **안전 안내 UI:** 답변을 섹션 카드와 출처 배지로 표시하고, 기관명·운영 안내·전화 버튼도 선택 언어로 제공합니다. 전화번호와 전화 연결 주소는 원본 값을 유지합니다.
- **대화 관리:** 회원가입·로그인, 대화 기록 저장, 후속 질문의 맥락 연결과 답변 스트리밍을 지원합니다.

```text
텍스트 입력 ─────────┐
음성 입력 → STT ─────┘
          ↓
한국어 질문 정규화 → 이전 대화 맥락 연결
          ↓
사고·물질 분석 → FAISS + 관계 그래프 검색
          ↓
근거 기반 한국어 답변 → 선택 언어 번역·연락처 카드·TTS
```

| 구성 | 기술 / 경로 |
| --- | --- |
| 프론트엔드 | Vue 3, Vite · `frontend/` |
| 인증 서버 | Java, JWT · `workplace/` |
| RAG API | FastAPI, LangChain, OpenAI · `rag-code-template_ext/` |
| 데이터·검색 파이프라인 | pypdf, FAISS, 출처 기반 관계 그래프 · `pipeline/` |
| 음성 API | FastAPI, faster-whisper, OpenAI TTS · `voice-ai_code/` |
| 저장소·실행 환경 | MariaDB 11.4, Docker Compose |

서비스는 문서에 근거한 정보 확인을 돕습니다. 사고 심각도의 확정, 전문 안전 판단, 기관 연락처의 현재성 확인을 대신하지 않습니다. 전화 버튼은 확인 절차 후 기기의 전화 앱을 열며 자동 발신하지 않습니다.

## 2. 실행방법

이 절은 **로컬에서 서비스를 개별 실행하는 개발 방식**입니다. 전체 서비스를 컨테이너로 실행하려면 [3. Compose 실행법](#3-compose-실행법)을 사용하세요. 두 방식을 같은 기본 포트로 동시에 실행하지 않습니다.

### 2.1. 환경 준비

Python 3.11, JDK 17 이상, Node.js 22.12 이상, Docker Desktop 또는 Docker Engine + Compose를 준비합니다. 명령은 macOS/Linux 셸 기준이며 프로젝트 루트에서 시작합니다.

```bash
# 기존 .env가 있으면 유지합니다.
test -f .env || cp .env.example .env

# JWT_SECRET에 넣을 값을 생성합니다.
openssl rand -hex 32

python3.11 -m venv .venv
.venv/bin/python -m pip install -r notebooks/requirements.txt -r rag-code-template_ext/requirements-e.txt
npm --prefix frontend ci
```

`.env`의 `DB_PASSWORD`, `JWT_SECRET`, `OPENAI_API_KEY`를 설정합니다. 실제 키와 비밀번호는 커밋하지 않습니다. 인증 서버와 음성 서버의 `JWT_SECRET`은 같아야 합니다.

선택 설정은 `.env.example`을 참고하세요. `TRANSLATION_MODEL`은 입력·답변 번역 모델, `TTS_MODEL`과 `TTS_VOICE`는 음성 생성 설정, `WHISPER_MODEL`은 로컬 음성 인식 모델입니다. 기본 PDF 검색에는 Naver API 키가 필요하지 않습니다.

### 2.2. PDF 검색 인덱스 준비

```bash
.venv/bin/python -m pipeline.pdf_pipeline prepare
.venv/bin/python -m pipeline.pdf_pipeline --env-file .env build
```

`prepare`는 로컬 PDF 추출과 그래프 준비를 수행합니다. `build`는 OpenAI 임베딩 API를 호출하므로 비용이 발생합니다. 정상 완료 시 `pipeline_artifacts/current.json`과 버전된 인덱스가 생성됩니다. 원본 PDF·파이프라인 설정을 바꿔 인덱스를 갱신했다면 RAG API를 재시작합니다.

### 2.3. DB와 음성 API 실행

```bash
docker compose up -d --build mariadb voice
```

루트 `compose.yaml`에서 DB와 음성 서비스만 선택해 실행합니다. DB 기본값은 `127.0.0.1:53301`, 사용자 `safety`, 비밀번호는 `.env`의 `DB_PASSWORD`입니다. 전체 구성이 이미 실행 중이라면 먼저 `docker compose stop auth rag frontend`로 로컬에서 직접 실행할 서비스의 컨테이너를 중지합니다. 음성 서버는 최초 실행 시 Whisper 모델을 다운로드할 수 있습니다.

### 2.4. 인증 서버 실행

새 터미널에서 프로젝트 루트로 이동한 뒤 실행합니다.

```bash
set -a
source .env
set +a

cd workplace
DB_URL=jdbc:mariadb://127.0.0.1:53301/sql_db DB_USER=safety \
  ./gradlew :app:run --no-configuration-cache
```

### 2.5. RAG API 실행

다른 터미널의 프로젝트 루트에서 실행합니다.

```bash
set -a
source .env
set +a

cd rag-code-template_ext
DB_HOST=127.0.0.1 DB_PORT=53301 DB_USER=safety DB_NAME=sql_db \
  ../.venv/bin/python -m uvicorn 'rag_external-web_pdf_closed_llm:app' \
  --host 127.0.0.1 --port 8001 --reload
```

`ASYNC_DB_URL`을 별도로 설정한 경우 위 DB 개별 설정보다 우선합니다. 시작 로그의 `PDF 검색: 팀 파이프라인 인덱스 사용`을 확인하세요. `faiss_db/pdf 사용`이 표시되면 2.2절의 인덱스 생성 상태를 확인합니다.

### 2.6. 프론트엔드 실행과 사용

또 다른 터미널에서 실행합니다.

```bash
npm --prefix frontend run dev
```

`http://127.0.0.1:5173/`에서 회원가입·로그인 후 질문합니다. 기본 자료는 이미 인덱스에 포함되므로 PDF를 다시 업로드할 필요가 없습니다. 상단에서 출력 언어를 선택하고 **번역하고 듣기**를 누르면 번역된 본문과 연락처 카드를 확인할 수 있습니다. 미리보기 모드는 실제 검색·번역 API를 호출하지 않습니다.

종료할 때는 인증·RAG·Vite 터미널에서 각각 `Ctrl+C`를 누르고, DB·음성 컨테이너는 다음 명령으로 중지합니다.

```bash
docker compose stop mariadb voice
```

## 3. Compose 실행법

루트 `compose.yaml`은 MariaDB, 인증 서버, RAG API, 음성 API, Vue 개발 서버를 함께 실행합니다. 호스트의 Python·JDK·Node.js 설치 없이 Docker로 실행할 수 있습니다. Docker 실행 정의는 이 파일 하나로 관리하며, 일부 서비스만 필요하면 서비스 이름을 지정합니다.

### 3.1. 설정과 전체 실행

```bash
# 프로젝트 루트. 기존 .env는 덮어쓰지 않습니다.
test -f .env || cp .env.example .env
```

`.env`에 `DB_PASSWORD`, `JWT_SECRET`, `OPENAI_API_KEY`를 입력한 뒤 실행합니다. `JWT_SECRET`은 `openssl rand -hex 32`로 생성할 수 있습니다.

```bash
docker compose up -d --build
docker compose ps
```

### 3.2. 최초 검색 인덱스 생성

새 체크아웃에는 생성된 인덱스가 포함되지 않습니다. 인덱스가 없다면 RAG 컨테이너에서 다음 명령을 실행합니다. 이미 2.2절에서 만든 호스트 인덱스가 있다면 재사용하므로 이 단계를 생략할 수 있습니다.

```bash
docker compose exec rag python -m pipeline.pdf_pipeline prepare
docker compose exec rag python -m pipeline.pdf_pipeline build
docker compose restart rag
```

임베딩 API 비용이 발생하며, 생성 결과는 호스트의 `pipeline_artifacts/`에 보존됩니다. Compose가 검색 인덱스를 자동으로 구축하지는 않습니다.

### 3.3. 접속과 상태 확인

| 서비스 | 기본 접속 주소 |
| --- | --- |
| 웹 화면 | http://127.0.0.1:5173/ |
| 인증 서버 | http://127.0.0.1:8080/ |
| RAG API 문서 | http://127.0.0.1:8001/docs |
| 음성 API 문서 | http://127.0.0.1:8008/docs |
| MariaDB | `127.0.0.1:53301` |

브라우저는 웹 화면으로 접속합니다. 프론트엔드 프록시가 인증·RAG·음성 요청을 각 컨테이너로 전달합니다. 초기 Whisper 모델 다운로드에는 시간이 걸릴 수 있습니다.

```bash
docker compose logs -f --tail=100
docker compose logs -f rag voice
```

포트 충돌이 있으면 `.env`의 `FRONTEND_PORT`, `AUTH_PORT`, `RAG_PORT`, `VOICE_PORT`, `DB_PORT`를 변경합니다. 로컬 개발과 전체 컨테이너 실행 모두 같은 Compose 프로젝트와 데이터 볼륨을 사용합니다. 과거 별도 Compose로 생성한 DB 볼륨은 자동으로 가져오지 않습니다.

### 3.4. 변경 반영과 종료

```bash
# 백엔드 코드·환경변수 변경 반영
docker compose up -d --build

# 일시 중지 / 재실행
docker compose stop
docker compose start

# 컨테이너·네트워크 종료. 데이터 볼륨은 유지
docker compose down
```

`frontend/src/`의 변경은 개발 서버에 바로 반영됩니다. DB는 `mariadb_data`, Whisper 모델은 `whisper_models`, 음성 파일은 `voice_uploads` 볼륨에 보존됩니다. `docker compose down -v`는 이 볼륨들을 삭제하므로 초기화할 때만 사용합니다. 세부 설정은 [Compose 안내](docs/DOCKER_COMPOSE.md)를 참고하세요.

## 4. 데이터 출처

기본 RAG는 프로젝트에 제공된 두 PDF를 사용합니다. 파일 목록·SHA-256·자료 구분은 [pipeline/config.json](pipeline/config.json)에 기록합니다.

| 자료 | 저장 위치 / 출처 | 사용 범위 |
| --- | --- | --- |
| 연구실 안전관리 매뉴얼 | [원본 PDF](<data/연구실 안전관리 매뉴얼.pdf>) | 물질별 위험 정보, 사고 대응, 보고 절차, 기관 연락망 |
| 폐기물관리법 제21467호 PDF | [원본 PDF](<data/폐기물관리법(법률)(제21467호)(20260918).pdf>) | 폐기물 관리 관련 문서 근거. 설정의 시행일 `2026-09-18`은 제공 PDF 헤더 기준이며 현행 법령 여부를 실시간 검증한 값은 아님 |
| GHS 인식 참고자료 | [파생 PDF](data/SafeOps_GHS_인식참고_v1.pdf) | 매뉴얼 PDF 105쪽의 그림을 추출한 인식 참고용 자료. 기본 RAG 문서 색인에서는 제외 |
| GHS 코드 대조 | [출처가 기록된 기호 사전](pipeline/ghs_dictionary.json) | Safe Work Australia의 GHS 안내를 기준으로 기호 코드를 연결 |
| 절차·연락망 구조화 자료 | [pipeline/structured/](pipeline/structured/) | 매뉴얼을 바탕으로 전사한 절차·연락처·역할 연결 및 별도 운영 정책. 독립적인 외부 원본 자료와 구분 |
| 공식 웹 보완 | [pipeline/official_web.py](pipeline/official_web.py) | 물질 식별자 기반으로 CDC/NIOSH 등 허용된 공식 도메인의 건강·대응 정보를 보완. 확보하지 못하면 로컬 근거 유지 |

제공 PDF의 원 배포기관·다운로드 URL은 현재 문서 설정에 기록되어 있지 않습니다. 자료의 법적·안전상 유효성과 연락처의 최신성은 별도 확인이 필요합니다. 구조화한 정책과 원문에서 직접 확인한 내용을 같은 종류의 근거로 취급하지 않습니다.

추출·청킹·색인은 [데이터 파이프라인](docs/DATA_PIPELINE.md), 관계 탐색은 [GraphRAG](docs/GRAPH_RAG.md), 표·그림 판독은 [이미지 판독](docs/VISION_PIPELINE.md), 원문과 구조화 자료의 연결은 [통합 파이프라인](docs/STRUCTURED_SAFETY_PIPELINE.md) 문서에서 확인할 수 있습니다.

## 5. 평가 결과

### 5.1. 평가 구성

- 질문 세트: [evaluation/notebook_cases.json](evaluation/notebook_cases.json)의 기본 4문항, 위험 상황 15문항, 자료 밖 질문 1문항으로 총 20문항.
- 자료 범위 내 19문항: 실제 저장 답변과 검색 근거를 RAGAS로 평가.
- 자료 밖 1문항: 일반 평균에서 제외하고 별도의 보류 응답 루브릭으로 평가.
- 평가 모델: `gpt-4o-mini`, 관련성 평가 임베딩: `text-embedding-3-small`.

### 5.2. 기록된 측정값

| 지표 | 범위 내 19문항 평균 | 해석 |
| --- | ---: | --- |
| Faithfulness | 0.8869 | 답변이 제공된 근거에 의해 뒷받침되는 정도 |
| Answer relevancy | 0.6666 | 기본 역질문 방식으로 측정한 답변 관련성 |
| Context precision | 0.7473 | 기준 답안 초안에 따른 검색 근거의 정밀도 |
| Context recall | 0.7193 | 기준 답안 초안의 정보를 검색 근거가 지원하는 정도 |

자료 밖 질문은 사용자 정의 보류 응답 루브릭에서 **4/5점**을 받았습니다.

별도의 로컬 검색 검사에서는 19문항의 지정 원문 구간·문자열 평균 재현율이 72.8% → 100%로 개선됐습니다.

### 5.3. 평가 재현

2.1절의 Python 환경을 준비한 뒤 실행합니다.

```bash
# 외부 API 호출 없이 노트북 구조·미실행 상태 확인
.venv/bin/python -m pipeline.run_notebook_evaluation --offline

# 임베딩·답변 생성·RAGAS 평가 실행: API 비용 발생
.venv/bin/python -m pipeline.run_notebook_evaluation --live --build-index
```

[검증 노트북](notebooks/safepath_question_validation.ipynb)을 직접 실행할 때는 `RUN_LIVE`와 `RUN_RAGAS` 플래그를 확인하세요. 생성 답변·평가 점수·이미지 캐시는 `pipeline_artifacts/`에 저장되며 Git에서 제외됩니다. 새 체크아웃에는 과거 평가 산출물이 없을 수 있으므로 미실행 상태를 측정 결과로 간주하지 않습니다. 자세한 재현 조건은 [노트북 안내](notebooks/README.md)를 참고하세요.

## 6. 팀원별 담당 내용

아래는 Git 커밋에서 확인되는 이름·계정과 기여 내용 기준입니다. 공식 이름과 최종 역할 분장은 팀 확인 후 보완할 수 있습니다. 자동화 도구의 커밋은 별도 팀원으로 집계하지 않았습니다.

| 팀원  | 담당 내용 |
| --- | --- |
| 김지훈 | 서비스 통합, 초기 Vue 화면과 회원가입·음성 질문 연동, 실시간 STT 및 무음 후 질문 전송, 전체 Docker Compose 구성 |
| 박시현 | RAG API, 사고 질문 검색 계획, 팀 파이프라인 인덱스 연결, 물질명 오탈자 보정, 출처·인용 및 입력 검증 개선 |
| 최유정 | 출처 연결 데이터 파이프라인, GraphRAG와 안전 대응 검색 보강, 평가·검증 자료, SafeOps UI와 반응형 답변·연락처 카드 개선 |
| 이병길 | MariaDB 인증 환경 구성, Vue 컴포넌트·API 모듈화, RAG 응답 스트리밍, 채팅 세션과 대화 기록 저장 |
