# industrial-safety-ai
RAG 기반 산업안전 매뉴얼 검색, 다국어 음성 질의응답 및 재난 대응을 지원하는 AI 서비스

## 전체 서비스 실행

루트 `.env.example`을 `.env`로 복사한 뒤 `DB_PASSWORD`, `JWT_SECRET`, `OPENAI_API_KEY`를 설정하고 실행합니다.

```bash
docker compose up -d --build
```

Vue: http://127.0.0.1:5173/ · [환경 설정·포트 충돌·데이터 보존 안내](docs/DOCKER_COMPOSE.md)

한국어 PDF 데이터 파이프라인의 실행 방법과 검증 범위는 [데이터 파이프라인 안내](docs/DATA_PIPELINE.md)를 참고하세요. 현재는 두 PDF의 개발용 추출, FAISS 구축과 근거 검색 단계이며 서비스 API와의 연결은 후속 작업입니다.

[질문별 답변 검증 노트북](notebooks/safepath_question_validation.ipynb)에서 7개 질문의 근거, 모범답안 초안과 생성 답변을 비교하고 RAGAS로 자동 평가합니다. 검색 정밀도·재현율은 모범답안 초안 기준의 잠정 점수이며, 자료 밖 질문은 별도 보류 루브릭으로 평가합니다. VS Code에서 이 프로젝트의 `.venv/bin/python` 커널을 선택하세요. 실제 답변 생성은 `RUN_LIVE=True`, RAGAS 평가 실행은 `RUN_RAGAS=True`입니다. 기본값은 저장 결과 재사용이며 새 실행에는 API 비용이 발생합니다.

## 표·GHS 이미지 인식

[이미지 판독 파이프라인](docs/VISION_PIPELINE.md)을 추가했습니다. 노트북 09절에서 전체 페이지 판독과 개별 그림 확대 판독의 실제 결과를 비교합니다. `data/SafeOps_GHS_인식참고_v1.pdf`는 인식 사전용 파생자료이며 `recognition_references`에 등록되어 기본 RAG 색인에서는 제외합니다. 확인된 GHS 그림, 사고 절차와 연락망을 포함해 379개 청크를 구축하며, 문서 간 연결 근거는 별도로 보존합니다.

## 로컬 서비스 실행

전체 서비스는 다음 포트를 사용합니다.

| 구성 요소 | 포트 | 실행 위치 |
| --- | ---: | --- |
| MariaDB | 53301 | Docker Compose |
| Java 인증 서버 | 8080 | `workplace/` |
| RAG API | 8001 | `rag-code-template_ext/` |
| 음성 API | 8008 | Docker Compose (`voice-ai_code/`) |
| Vue/Vite 프론트엔드 | 5173 | `frontend/` |

### 1. 최초 준비

JDK 17, Python 3.11, Node.js, Docker Desktop을 준비합니다. 프로젝트 루트의 `.env`에는 최소한 `DB_PASSWORD`, `JWT_SECRET`, `ASYNC_DB_URL`, `OPENAI_API_KEY`가 필요합니다. `JWT_SECRET`은 `voice-ai_code` 코드에 설정된 JWT 검증 키와 같아야 합니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r notebooks/requirements.txt -r rag-code-template_ext/requirements-e.txt

cd frontend
npm ci
cd ..
```

### 2. PDF 검색 인덱스 준비

`data/`의 등록된 PDF를 사용합니다. `prepare`는 로컬 추출이고, `build`는 OpenAI 임베딩 API를 호출하므로 비용이 발생합니다. 원본 PDF나 파이프라인 설정이 바뀌었을 때 다시 실행합니다.

```bash
.venv/bin/python -m pipeline.pdf_pipeline prepare
.venv/bin/python -m pipeline.pdf_pipeline --env-file .env build
```

정상 실행 시 `pipeline_artifacts/current.json`과 버전된 FAISS 인덱스가 생성됩니다. 인덱스를 새로 빌드했다면 **RAG API를 재시작**해야 합니다.

### 3. MariaDB 실행

```bash
docker compose --env-file .env -f docker-compose.mariadb.yml up -d
docker compose --env-file .env -f docker-compose.mariadb.yml ps
```

### 4. Java 인증 서버 실행

새 터미널에서 실행하고 터미널을 열어 둡니다. Python `.venv`가 활성화된 상태여도 Gradle 실행에는 영향이 없습니다.

```bash
cd /path/to/industrial-safety-ai
set -a
source .env
set +a

cd workplace
./gradlew :app:run --no-configuration-cache
```

`Server started at http://localhost:8080`이 표시되면 정상입니다.

### 5. RAG API 실행

새 터미널에서 실행하고 터미널을 열어 둡니다.

```bash
cd /path/to/industrial-safety-ai
set -a
source .env
set +a

cd rag-code-template_ext
../.venv/bin/python -m uvicorn 'rag_external-web_pdf_closed_llm:app' \
  --host 127.0.0.1 \
  --port 8001 \
  --reload
```

시작 로그에 `✅ PDF 검색: 팀 파이프라인 인덱스 사용`이 표시되어야 `data/`에서 구축한 인덱스를 검색합니다. `faiss_db/pdf 사용`이 표시되면 2단계의 인덱스 빌드를 확인하고 RAG API를 재시작합니다. 기본 `data/` 자료를 질의할 때는 프론트엔드에서 PDF를 다시 업로드할 필요가 없습니다.

### 6. 음성 API 실행

음성 입력·답변 듣기를 사용할 때 실행합니다. 텍스트 질의만 확인할 때는 생략할 수 있습니다.

```bash
docker compose --env-file .env -f voice-ai_code/docker-compose.yml up -d --build
docker compose --env-file .env -f voice-ai_code/docker-compose.yml ps
```

### 7. 프론트엔드 실행

새 터미널에서 실행하고 터미널을 열어 둡니다.

```bash
cd /path/to/industrial-safety-ai/frontend
npm run dev
```

브라우저에서 `http://127.0.0.1:5173/`으로 접속한 뒤 회원가입 또는 로그인하고 질문합니다. 화면 미리보기 모드는 실제 RAG·음성 API를 호출하지 않습니다.

### 상태 확인과 종료

```bash
lsof -nP -iTCP:5173 -iTCP:8080 -iTCP:8001 -iTCP:8008 -iTCP:53301 -sTCP:LISTEN
```

Java·RAG·Vite는 각 터미널에서 `Ctrl+C`로 종료합니다. Docker 서비스는 다음 명령으로 종료합니다. `down`만 사용하면 MariaDB 이름 볼륨의 데이터는 유지됩니다.

```bash
docker compose --env-file .env -f voice-ai_code/docker-compose.yml down
docker compose --env-file .env -f docker-compose.mariadb.yml down
```

## 데이터 파이프라인·검증 실행

Python 3.11 환경에서 실행합니다. 원본 PDF와 인식 참고자료는 `data/`에 포함돼 있습니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r notebooks/requirements.txt
.venv/bin/python -m pipeline.pdf_pipeline prepare
.venv/bin/python -m unittest discover -s tests -q
# OPENAI_API_KEY를 로컬 .env에 설정한 뒤 실행 (임베딩 비용 발생)
.venv/bin/python -m pipeline.pdf_pipeline --env-file .env build
```

`.env`, `.harness/`, `pipeline_artifacts/`와 노트북 실행 출력은 커밋하지 않습니다. 따라서 새로 받은 저장소에는 과거 생성 답변/점수/이미지 캐시가 없습니다. 노트북 전체 실행 전에 해당 자료를 생성해야 하며, 미실행 상태를 실제 답변으로 간주하지 않습니다. 문서 연결과 상황별 근거 묶음의 범위 및 한계는 [통합 파이프라인 안내](docs/STRUCTURED_SAFETY_PIPELINE.md)를 참고하세요.
