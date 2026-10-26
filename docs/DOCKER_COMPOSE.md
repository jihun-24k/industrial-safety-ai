# 전체 서비스 Docker Compose 실행

Docker Desktop(또는 Docker Engine + Compose)이 켜져 있어야 합니다. 루트 `compose.yaml`은 MariaDB, Java 인증, RAG, STT/TTS, Vue 개발 서버를 함께 실행합니다.

## 최초 설정

```bash
# 저장소 루트에서 실행. 기존 .env가 있다면 복사로 덮어쓰지 마세요.
cp .env.example .env
openssl rand -hex 32
```

루트 `.env`에 다음 값을 입력합니다.

- `DB_PASSWORD`: 새 Compose DB의 애플리케이션 계정 비밀번호
- `JWT_SECRET`: 위 명령으로 생성한 값. 인증·음성 서버에 동일하게 전달
- `OPENAI_API_KEY`: 기존 `rag-code-template_ext/.env`에서 사용하던 키를 입력
- `DB_ROOT_PASSWORD`: 선택 사항. 비어 있으면 DB_PASSWORD 사용

루트 `.env`는 Git과 Docker 빌드 컨텍스트에서 제외합니다. 이미지에 실제 키·가상환경·캐시를 복사하지 않습니다. 필수 값이 비어 있으면 Compose가 시작 전에 오류를 냅니다. 새 Compose 실행은 루트 `.env`를 사용하며 서비스별 `.env`를 자동으로 합치지 않습니다.

## 실행·확인·종료

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

| 서비스 | 기본 호스트 주소 | 내부 주소 |
| --- | --- | --- |
| Vue | http://127.0.0.1:5173 | frontend:5173 |
| 인증 | http://127.0.0.1:8080 | auth:8080 |
| RAG 문서 | http://127.0.0.1:8001/docs | rag:8001 |
| 음성 문서 | http://127.0.0.1:8008/docs | voice:8008 |
| MariaDB | 127.0.0.1:53301 | mariadb:3306 |

브라우저는 Vue 주소로 접속합니다. Vue 프록시가 인증·RAG·음성 컨테이너로 요청을 전달합니다. DB가 준비된 다음 인증·RAG 서버가 시작되고, 모든 API가 준비되면 Vue가 시작됩니다.

음성 서버는 처음 시작할 때 Whisper 모델을 내려받으므로 몇 분 걸릴 수 있습니다. 모델 다운로드에는 임베딩/LLM API 호출이 없습니다. 모델은 볼륨에 저장되어 이후 실행에서 재사용됩니다. `docker compose logs -f voice`로 확인하세요.

```bash
# 서비스별 로그
docker compose logs -f auth rag voice

# 일시 중지 / 다시 실행
docker compose stop
docker compose start

# 컨테이너·네트워크 정리. DB·모델 볼륨과 호스트 인덱스는 보존
docker compose down
```

`docker compose down -v`는 DB·모델·업로드 볼륨을 삭제하므로 데이터 초기화가 목적일 때만 사용합니다.

## 기존 실행과 함께 사용할 때

현재 직접 실행한 서버가 5173·8080·8001·8008을 사용 중이면 해당 터미널에서 Ctrl+C로 종료한 뒤 실행하세요. 기존 MariaDB가 53301을 사용하면 기존 컨테이너를 중지하거나 새 `.env`의 `DB_PORT`를 바꾸세요. 이 설정은 기존 서버를 자동으로 중지하지 않습니다.

기존 환경을 계속 켜 두려면 새 `.env`에서 다음처럼 호스트 포트만 변경할 수 있습니다. 컨테이너 간 통신 주소는 바뀌지 않습니다.

```dotenv
FRONTEND_PORT=15173
AUTH_PORT=18080
RAG_PORT=18001
VOICE_PORT=18008
DB_PORT=15331
```

프로젝트 이름은 `industrial-safety-stack`입니다. 과거 별도 구성에서 생성한 DB 컨테이너·볼륨은 자동으로 재사용하거나 업그레이드하지 않습니다. 과거 DB의 데이터가 필요하면 별도 백업·복원 후 전환하세요. 기존 볼륨은 이번 구성 정리로 삭제되지 않습니다. DB·음성 전용 Compose 파일은 제거했으며, 일부 서비스만 실행할 때도 루트 `compose.yaml`을 사용합니다.

## 필요한 서비스만 실행

로컬 개발과 전체 컨테이너 실행에 같은 프로젝트·환경변수·데이터 볼륨을 사용합니다.

```bash
# DB만 실행
docker compose up -d mariadb

# 인증·RAG·프론트엔드는 로컬에서 실행하고, DB·음성만 컨테이너 사용
docker compose up -d --build mariadb voice

# 선택한 서비스만 중지. 볼륨은 유지
docker compose stop mariadb voice
```

전체 구성을 켜 둔 상태에서 로컬 서버로 전환하려면 `docker compose stop auth rag frontend`로 해당 컨테이너를 먼저 중지합니다. 호스트에서 실행하는 인증·RAG 서버는 기본 주소 `127.0.0.1:53301`, DB 사용자 `safety`, `.env`의 `DB_PASSWORD`로 연결합니다. 호스트 포트를 바꿨다면 로컬 서버의 DB 연결 주소도 맞춰야 합니다. `DB_ROOT_PASSWORD`는 DB 관리용이며 애플리케이션 로그인에 사용하지 않습니다.

## Docker 파일 구성

| 파일 | 용도 |
| --- | --- |
| `compose.yaml` | 전체 서비스와 선택 실행, 네트워크·볼륨·상태 확인 정의 |
| `frontend/Dockerfile` | Vue/Vite 개발 서버 이미지 |
| `workplace/Dockerfile` | Java 인증 서버 빌드·실행 이미지 |
| `rag-code-template_ext/Dockerfile` | 루트 빌드 컨텍스트에서 RAG·pipeline·원본 자료 구성 |
| `voice-ai_code/Dockerfile` | Whisper·ffmpeg·TTS 실행 이미지 |
| 루트 및 서비스별 `.dockerignore` | 각 빌드 컨텍스트에서 비밀 설정·캐시·생성 파일 제외 |
| `voice-ai_code/requirements-docker.txt` | 음성 컨테이너에 필요한 Python 의존성 |

네 Dockerfile은 루트 Compose에서 실제로 참조하므로 유지합니다. `.dockerignore`도 빌드 컨텍스트가 달라 각각 필요합니다.

## 데이터와 개발 반영

- DB: `mariadb_data` 명명 볼륨. 신규 DB에만 `database/init/` SQL 자동 적용
- Whisper: `whisper_models` 명명 볼륨
- 녹음·TTS 파일: `voice_uploads` 명명 볼륨
- 기존 FAISS: 호스트 `rag-code-template_ext/faiss_db/`를 RAG 컨테이너에 마운트
- 파이프라인 산출물: 호스트 `pipeline_artifacts/`를 마운트
- 원본 자료와 pipeline 코드는 RAG 이미지에 포함. 인덱스 자동 구축이나 서비스 API 자동 연결은 수행하지 않음

Vue `frontend/src/` 수정은 개발 서버에 바로 반영됩니다. 패키지·Vite 설정·백엔드 소스가 바뀌면 `docker compose up -d --build`로 재빌드합니다. 이 구성은 로컬 개발용이며 Vue는 Vite 개발 서버를 사용합니다.

원래 호스트에서 실행하는 방식도 유지됩니다. Vite 프록시 기본값은 localhost이고 Compose에서만 서비스 이름을 전달합니다. Java는 기본 root 계정 대신 `DB_URL`, `DB_USER=safety`, `DB_PASSWORD`를 명시해 Compose DB에 연결합니다. 음성 서버는 `JWT_SECRET` 환경변수 또는 자신의 `.env`가 필요합니다.

상태 확인은 서비스 시작·HTTP 응답 기준입니다. 실제 OpenAI 키 유효성, 검색 인덱스 내용, 답변 품질·음성 생성 품질을 보증하지 않습니다. RAG·TTS 호출 시에는 기존과 같이 API 비용이 발생합니다.
